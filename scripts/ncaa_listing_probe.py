"""
THE NCAA LISTING PROBE (#1035; ARCHITECT 2026-11-16 12:49 ET, addendum 414 item 3). Read-only: one GET of the
provider's college football games per date given, the RAW rows printed before any parsing, and beside each row what
our side would do with it. No write anywhere and no file made.

414 item 3, verbatim:
  "THE PROBE: BUILD IT, as your (b) costs it. One small PR, lane A, read-only tooling under the stop rule.
   (a) One script under scripts/: for each date given, ONE GET of the provider's games for league 2, season 2026 and
       that date, through the adapter's own _get, and the RAW rows printed before any parsing: the provider's game id,
       its date or timestamp, its status, the home id and name, the away id and name.
   (b) Beside each row, what our side would do with it, by your own table: "no date" (#1), "no team id" (#2),
       "all-star or exhibition" (#3); and with an optional --db copy (mode=ro + immutable=1; a path under data/ or a
       copy with a sidecar refused): "team not in the copy" (#6), or the stored match id that holds this provider id,
       or NOT STORED.
   (c) THE FENCE: no write anywhere, no file made (my block keeps the console); at most seven dates a run, the count
       of provider calls printed first and last; the key by NAME only; a provider error prints and exits non-zero
       after what was read; nothing of sync, re-key or repair is imported for its side effects.
   (d) Provider rows are payload: they are printed on the laptop and read by me in the chat, and they do not go into
       an Issue, a PR body or a test. The test runs on rows you invent.
   (e) Name the command and its arguments in the PR body (198 item 6(i)). My block runs it Thursday for 2026-11-21,
       2026-11-27 and 2026-11-28 against that morning's copy: three calls."

THE CALL: APIAmericanFootballAdapter()._get("games", {"league": 2, "season": 2026, "date": D}), the call sync-matches
makes for a single-day window (api_american_football.list_matches with date_from == date_to), one per date, in the
order given. No timezone parameter is sent, as the sync sends none. _get retries once after 5 s on a 429; the count
printed last is of HTTP requests made, so a retry shows in it.

THE TABLE (DEV 1's answers to 413 item 2(a) on #1035), the drops checked per row, in the adapter's own order:
  #1 no date: no game.date.timestamp and no date string (api_american_football._parse_games).
  #2 no team id: no game id, or no home or no away team id (_parse_games).
  #3 all-star or exhibition: the adapter's own _non_competitive rule on week, stage and the two team names.
  #6 team not in the copy (--db only): a home or away team id that no stored team answers to (its own
     api_american_football id, or one a merge recorded on it under "api_american_football_also").
Every reason that applies is printed; the first is the one the sync stops at. With --db, every row also says which
stored NCAA match holds its provider id ("stored as match N", with that row's season, status and kickoff, and "another
season" when its season's year is not 2026, or "season unknown" when it has none, as service.season_year reads it), or
NOT STORED; NOT STORED also names a stored match that holds the id as a
previous one ("api_american_football_prev"). A row with no game id has no id to look up. Drops #4 (a team /teams
omits) and #5, #7 to #9 need the teams listing or the sync's own state, which this probe does not read.

--db: optional, a .backup copy outside the repo's data/ (mlb_pitchers_gate.check_db), refused with a -wal, -shm or
-journal beside it before the read and after it (intl_shadow.copy_sidecars), opened mode=ro&immutable=1 with sqlite3
directly. The copy is read before any provider call, so a refused copy costs no call.

THE FENCE, as the code holds it: no sync, re-key or repair code is imported or called (src.ingestion.service, its
re-key and orientation paths, match_dedupe and team_merge are never loaded; the test holds it in a fresh interpreter).
The one ingestion module loaded is src.ingestion.ncaa_cfbd, which the shared --db fence (mlb_pitchers_gate, through
ncaa_backtest) imports for every --db receipt; nothing in it runs. The adapter is imported for _get and its
_non_competitive rule only. Run as a script (the block's use), no bytecode file is made: Python never caches the
file it runs, and the flag at the top turns the cache off before any other import (a test runs it so and finds no
.pyc). Imported as a module (the test does), the import itself may cache this one file before the flag runs; the test
holds that off. .env is read, never written; nothing is written to the copy (SQLite refuses a write on mode=ro). The key is named, never printed.

Exit codes: 0 every date read and every row's verdict worked out; 1 a provider error (printed after the rows already
read; no later date is called), or a row whose verdict failed (that row is printed raw with "VERDICT FAILED" and the
run goes on); 2 refused before any call (the command line, the dates, the key, or the copy). Every exit prints the
count of provider calls made. An exception's text is printed with the key's value replaced by its variable's name.

    python3 scripts/ncaa_listing_probe.py --date 2026-11-21 --date 2026-11-27 --date 2026-11-28 --db /path/to/copy.db
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True                       # 414 item 3(c): no file made, a __pycache__ included

import argparse
import json
import os
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TAG = "NCAA-LISTING-PROBE"
SOURCE = "api_american_football"
ALSO = f"{SOURCE}_also"                              # team_merge.ALSO: ids a merge recorded on a kept team
PREV = f"{SOURCE}_prev"                              # the re-key history on a match
SEASON = 2026
MAX_DATES = 7
KEY_NAMES = ("API_AMERICAN_FOOTBALL_KEY", "API_FOOTBALL_KEY")   # the adapter's own order
OK, PROVIDER_ERROR, REFUSED = 0, 1, 2
_SEASON_YEAR = re.compile(r"(\d{4})(?!\d)")         # service._SEASON_YEAR, matched at the start as season_year does


def parse_dates(raw: list[str] | None) -> tuple[list[str], str | None]:
    """(the dates, in the order given; a refusal or None). One to MAX_DATES, each YYYY-MM-DD, none twice."""
    raw = list(raw or [])
    if not raw:
        return [], "no --date given (one to seven, YYYY-MM-DD)"
    if len(raw) > MAX_DATES:
        return [], f"{len(raw)} dates given; at most {MAX_DATES} a run (414 item 3(c))"
    seen = []
    for d in raw:
        try:
            ok = date.fromisoformat(d).isoformat() == d
        except ValueError:
            ok = False
        if not ok:
            return [], f"--date {d!r} is not a date written YYYY-MM-DD"
        if d in seen:
            return [], f"--date {d} given twice: one GET per date"
        seen.append(d)
    return seen, None


def key_name(env=None) -> str | None:
    """The NAME of the variable the adapter takes its key from (its own order), never the value; None if neither."""
    env = os.environ if env is None else env
    for name in KEY_NAMES:
        if env.get(name):
            return name
    return None


# ---------------------------------------------------------------------------------------------------------------
# The copy (--db)
# ---------------------------------------------------------------------------------------------------------------

def read_copy(db: str) -> tuple[dict, str]:
    """(the copy's lookups, its description). Raises mlb_pitchers_gate.GateRefused on a refused or unreadable copy."""
    import sqlite3

    from src.walters import intl_shadow
    from src.walters import mlb_pitchers_gate as mp

    path = mp.check_db(db)
    sides = _sidecars(intl_shadow, mp, path, db)
    if sides:
        raise mp.GateRefused(f"--db {db} has {', '.join(sides)} beside it: not a fresh .backup copy; immutable=1 "
                             "would ignore it and read a stale file; take a fresh .backup copy")
    con = mp.open_ro(path)
    try:
        comps = con.execute("SELECT id FROM competitions WHERE code = 'NCAA'").fetchall()
        if len(comps) != 1:
            raise mp.GateRefused(f"--db {db}: {len(comps)} competitions coded NCAA in the copy, not one")
        comp_id = comps[0][0]
        teams: dict[str, list[tuple[int, str]]] = {}
        for tid, name, ext in con.execute("SELECT id, name, external_ids FROM teams WHERE upper(sport) = 'NFL'"):
            e = _ext(ext)
            ids = ({str(e[SOURCE])} if e.get(SOURCE) is not None else set()) | {str(x) for x in (e.get(ALSO) or [])}
            for pid in ids:
                teams.setdefault(pid, []).append((tid, name))
        holders: dict[str, list[dict]] = {}
        prev: dict[str, list[int]] = {}
        n_rows = 0
        for mid, season, status, utc, ext in con.execute(
                "SELECT id, season, status, utc_date, external_ids FROM matches WHERE competition_id = ? ORDER BY id",
                (comp_id,)):
            n_rows += 1
            e = _ext(ext)
            if e.get(SOURCE) is not None:
                holders.setdefault(str(e[SOURCE]), []).append(
                    {"id": mid, "season": season, "status": status, "utc_date": utc})
            for old in (e.get(PREV) or []):
                prev.setdefault(str(old), []).append(mid)
    except sqlite3.Error as err:
        why = (str(err).strip().splitlines() or [""])[0]
        raise mp.GateRefused(f"--db {db}: cannot be read as the schema the probe needs ({type(err).__name__}: {why})")
    finally:
        con.close()
    sides = _sidecars(intl_shadow, mp, path, db)     # one appearing during the read can hold pages immutable ignored
    if sides:
        raise mp.GateRefused(f"--db {db}: {', '.join(sides)} appeared beside the copy during the read; take a fresh "
                             ".backup copy")
    look = {"teams": teams, "holders": holders, "prev": prev}
    text = (f"--db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')}): NCAA competition id {comp_id}, "
            f"{n_rows} stored matches, {len(holders)} provider ids held, {len(teams)} team provider ids")
    return look, text


def _sidecars(intl_shadow, mp, path, db) -> list[str]:
    """intl_shadow.copy_sidecars, its OSError (other than "no such file", e.g. ENAMETOOLONG on a long copy name) worded
    as this probe's refusal, as its docstring asks each caller to do: never a traceback, never read as absent."""
    try:
        return intl_shadow.copy_sidecars(path)
    except OSError as e:
        raise mp.GateRefused(f"--db {db}: cannot check for a -wal, -shm or -journal beside the copy "
                             f"({e.strerror or e})") from None


def season_year(season) -> int | None:
    """The leading four-digit year of a stored season string, as service.season_year reads it (its pattern, not its
    import: the probe loads no sync code). "2026" and "2026/27" read 2026; "20261", "" and None read unknown."""
    m = _SEASON_YEAR.match(str(season).strip()) if season is not None else None
    return int(m.group(1)) if m else None


def _ext(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return val if isinstance(val, dict) else {}


# ---------------------------------------------------------------------------------------------------------------
# One raw row
# ---------------------------------------------------------------------------------------------------------------

def raw_fields(g) -> dict:
    """The row's fields as the provider sent them, read the way _parse_games reads them, before any parsing."""
    g = g if isinstance(g, dict) else {}
    game = g.get("game") if isinstance(g.get("game"), dict) else g
    teams = g.get("teams") if isinstance(g.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    dt = game.get("date")
    if isinstance(dt, dict):
        when = {"date": dt.get("date"), "time": dt.get("time"), "timestamp": dt.get("timestamp")}
    else:
        when = {"date": dt, "time": None, "timestamp": None}
    st = game.get("status")
    status = ({"short": st.get("short"), "long": st.get("long")} if isinstance(st, dict)
              else {"short": st, "long": None})
    return {"id": game.get("id"), **when, **status, "week": game.get("week"), "stage": game.get("stage"),
            "home_id": home.get("id"), "home_name": home.get("name"),
            "away_id": away.get("id"), "away_name": away.get("name")}


def our_side(f: dict, look: dict | None) -> list[str]:
    """What our side would do with the row, by the table: every reason that applies, in the adapter's order."""
    import html

    from src.adapters.api_american_football import _non_competitive

    out = []
    if not f["timestamp"] and not f["date"]:
        out.append("DROPPED: no date (#1)")
    missing = [w for w, v in (("game id", f["id"]), ("home team id", f["home_id"]), ("away team id", f["away_id"]))
               if v is None]
    if missing:
        out.append(f"DROPPED: no team id (#2): no {', no '.join(missing)}")
    why = _non_competitive(f["week"], f["stage"],
                           team_names=(html.unescape(f["home_name"] or ""), html.unescape(f["away_name"] or "")))
    if why:
        out.append(f"DROPPED: all-star or exhibition (#3): {why}")
    if look is None:
        return out
    for side in ("home", "away"):
        pid = f[f"{side}_id"]
        if pid is not None and str(pid) not in look["teams"]:
            out.append(f"team not in the copy (#6): {side} {pid}")
    if f["id"] is None:
        return out
    held = look["holders"].get(str(f["id"]), [])
    for m in held:
        sy = season_year(m["season"])
        other = "" if sy == SEASON else (", season unknown" if sy is None else ", another season")
        out.append(f"stored as match {m['id']} (season {m['season']}{other}, {m['status']}, {m['utc_date']})")
    if not held:
        back = look["prev"].get(str(f["id"]), [])
        out.append("NOT STORED" + (f" (a previous id of match {', '.join(map(str, back))})" if back else ""))
    return out


def row_line(f: dict, verdict: list[str]) -> str:
    when = f"date={f['date']!r} time={f['time']!r} timestamp={f['timestamp']!r}"
    return (f"  game={f['id']!r} {when} status={f['short']!r}/{f['long']!r} week={f['week']!r} "
            f"stage={f['stage']!r} | home={f['home_id']!r} {f['home_name']!r} | away={f['away_id']!r} "
            f"{f['away_name']!r} -> {'; '.join(verdict) if verdict else 'kept by the parse'}")


# ---------------------------------------------------------------------------------------------------------------
# The calls
# ---------------------------------------------------------------------------------------------------------------

@contextmanager
def counted_requests():
    """Count every HTTP GET the adapter's _get makes (a 429's retry included), for the last line."""
    import requests

    real, box = requests.get, {"n": 0}

    def get(*a, **k):
        box["n"] += 1
        return real(*a, **k)

    requests.get = get
    try:
        yield box
    finally:
        requests.get = real


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """A command-line error is a refusal like any other: printed with the call count (0), exit 2, no usage dump."""

    def error(self, message):
        raise _ArgError(message)


def redactor(name: str | None, env=None):
    """A function that replaces the key's value, raw and as repr shows it, with its variable's name (414 item 3(c): the
    key by NAME only, in an exception's text too: requests puts a malformed header value in InvalidHeader's message)."""
    env = os.environ if env is None else env
    value = env.get(name) if name else None
    if not value:
        return lambda s: s
    forms = sorted({value, value.strip(), repr(value)[1:-1], repr(value.encode())[2:-1]} - {""}, key=len, reverse=True)

    def red(s: str) -> str:
        for v in forms:
            s = s.replace(v, f"<{name}>")
        return s
    return red


def main(argv=None, echo=print) -> int:
    ap = _Parser(description="414 item 3: the provider's raw NCAA listing for given dates, read-only")
    ap.add_argument("--date", action="append", help="YYYY-MM-DD; repeat for each date, at most seven a run")
    ap.add_argument("--db", default=None, help="an optional .backup copy outside the repo's data/, opened "
                                               "mode=ro&immutable=1")
    try:
        a = ap.parse_args(argv)
    except _ArgError as err:
        echo(f"{TAG} REFUSED: {err}; provider calls made: 0")
        return REFUSED
    dates, why = parse_dates(a.date)
    if why:
        echo(f"{TAG} REFUSED: {why}; provider calls made: 0")
        return REFUSED
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")                   # read only; an exported variable wins
    except ImportError:
        pass
    name = key_name()
    if name is None:
        echo(f"{TAG} REFUSED: no key in {' or '.join(KEY_NAMES)}; provider calls made: 0")
        return REFUSED
    look, db_text = None, "--db: none (no stored-side reads; #6 and the stored match are not checked)"
    if a.db is not None:
        from src.walters import mlb_pitchers_gate as mp
        try:
            look, db_text = read_copy(a.db)
        except mp.GateRefused as err:
            echo(f"{TAG} REFUSED: {err}; nothing read; provider calls made: 0")
            return REFUSED

    from src.adapters.api_american_football import _CODE_TO_LEAGUE, APIAmericanFootballAdapter
    league = _CODE_TO_LEAGUE["NCAA"]
    echo(f"{TAG}: provider calls planned: {len(dates)} (one GET games per date: league {league}, season {SEASON}; "
         f"_get retries once on a 429); key: {name} (by name)")
    echo(db_text)
    adapter = APIAmericanFootballAdapter()
    red = redactor(name)
    code, read, failed = OK, 0, 0
    with counted_requests() as box:
        for d in dates:
            params = {"league": league, "season": SEASON, "date": d}
            try:
                data = adapter._get("games", params)
            except Exception as err:                 # noqa: BLE001 - any provider failure: print and stop
                echo(red(f"DATE {d}: PROVIDER ERROR: {type(err).__name__}: {err}; no later date is called"))
                code = PROVIDER_ERROR
                break
            read += 1
            rows = data.get("response") if isinstance(data, dict) else None
            rows = rows if isinstance(rows, list) else []
            echo(red(f"DATE {d}: GET games league={league} season={SEASON} date={d}: "
                     f"results={data.get('results')!r} paging={data.get('paging')!r} rows={len(rows)}"))
            for g in rows:
                try:
                    f = raw_fields(g)
                except Exception as err:             # noqa: BLE001 - a row this probe cannot read: shown, not lost
                    failed += 1
                    echo(red(f"  row unreadable ({type(err).__name__}: {err}): {g!r}"))
                    continue
                try:
                    verdict = our_side(f, look)
                except Exception as err:             # noqa: BLE001 - the row is printed; its verdict names the failure
                    failed += 1
                    verdict = [f"VERDICT FAILED ({type(err).__name__}: {err}); the sync's own parse may raise on this row"]
                echo(red(row_line(f, verdict)))
    if failed and code == OK:
        code = PROVIDER_ERROR
    tail = []
    if failed:
        tail.append(f"{failed} row(s) whose verdict failed, each printed on its line")
    if code != OK:
        tail.append("exit 1 (" + ("a provider error" if read < len(dates) else "a row verdict failed") + ")")
    echo(f"{TAG}: dates read {read} of {len(dates)}; provider calls made: {box['n']} HTTP GET(s)"
         + "".join(f"; {x}" for x in tail))
    return code


if __name__ == "__main__":
    sys.exit(main())
