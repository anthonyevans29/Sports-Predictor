"""
THE RESTORE of the two provider-id collisions (ARCHITECT 2026-11-09, addendum 310 item 4 and addendum 312 item 3; #902).

Addendum 310 item 4, verbatim:

"a small read-then-write script Code ships in the fix PR (`scripts/restore_collided_rows.py --from <10-09 copy> --ids
36454,36753 --dry-run|--apply`): it reads the two rows' full content from the 10-09 copy (opened mode=ro +
immutable=1), refuses unless the live rows read exactly the 2026 state of item 1 (Utah v Cincinnati 2026-10-31 /
Alabama v LSU 2026-11-07, provider ids 18216/18240), then in ONE transaction: creates two NEW 2026 rows with the
LISTING's orientation (Cincinnati home / Utah away, 25-49; LSU home / Alabama away, 13-31; provider ids 18216/18240,
season 2026, status FINISHED, full_time_result by the new orientation), moves every odds_snapshots / odds / match_stats
row of 36454 and 36753 to the new ids, and rewrites 36454 and 36753 to their 10-09 content (season 2025, the 2025
kickoff, 45-14 and 20-9, provider ids kept, `provider_orientation` removed); prints before and after, every id.
`--dry-run` prints the plan and writes nothing; `--apply` is my block's word."

Addendum 312 item 3, verbatim:

"THE RESTORE SCRIPT — (a) the Kalshi odds_snapshots HOME/AWAY SWAP on the moved rows is RIGHT (#885: the side sits on
the stored home team's name; the new row's home is the old row's away) — ruled as built, with the dry run printing
each moved row's side before and after. (b) BOOK odds rows: the script takes `--book-rows {refuse,swap,keep}` (default
refuse) — my `--apply` block names the mode after the dry run's print of each row with its written_at against #885's
merge time (a row written after #885 is in the stored orientation → swap; before → the provider's, which IS the new
row's → keep); (c) rows in other referencing tables added since the copy (game_weather, kalshi_settled_markets, …) are
the 2026 game's and MOVE with it under `--move-added` (default refuse; the dry run lists them; my block passes the
flag). (d) availability_observations / availability_assertions are NFL-only today; printed, never moved, as built.
(e) THE HOST: the script identifies the two rows by PROVIDER ID and season (18216 → 2025 and 2026, 18240 → 2025 and
2026) and verifies by team names, kickoff dates and scores; row ids are read, never assumed (EXPECTED pins content,
not ids), so the same script runs on both machines. The host's `--from` is the host's own oldest daily copy that still
holds the 2025 rows intact (SP_BACKUP_DIR; my read block lists them first); if none does, the laptop's dry run
`--emit-json PATH` writes the two 2025 rows' fields (season, kickoff, status, teams by name, scores, provider id — no
row ids, nothing else) and the host's `--from-json` reads them: an extract of two rows is a receipt, not the database
(law 5 is about the file). Decided after the host's read."

    python scripts/restore_collided_rows.py --db data/sports_predictor.db --from <copy .backup> --dry-run
        # prints the plan; opens --db read-only (mode=ro); writes nothing to either database file
    python scripts/restore_collided_rows.py --db ... --from <copy> --dry-run --emit-json <PATH>
        # the same dry run; after every check passes, writes the two 2025 rows' fields to PATH (a receipt, created
        # exclusively: an existing PATH is refused) and prints PATH and the sha256 of the bytes written
    python scripts/restore_collided_rows.py --db ... --from <copy> [--ids A,B] [--book-rows refuse|swap|keep]
        [--move-added] --apply                    # the architect's block
    python scripts/restore_collided_rows.py --db ... --from-json <PATH> [--book-rows ...] [--move-added]
        --dry-run|--apply                         # the host with no copy holding the 2025 rows intact

Exactly one of --dry-run / --apply, and exactly one of --from / --from-json (else exit 2, nothing written). Exit 0 =
planned (dry run) or applied; exit 2 = refused, nothing written. The live DB is opened read-write only on --apply (one
transaction, BEGIN IMMEDIATE, every check read inside it, the row count written checked before the commit); --from
always mode=ro&immutable=1 (a copy nobody writes). "Writes nothing" is the database files' bytes: the live DB is a WAL
file (src/db/database.py), and SQLite itself may leave its empty -wal/-shm sidecars beside it on a mode=ro open, as for
every ro_connect reader. The live open is never immutable=1: that would skip WAL frames not yet written back into the
main file. The --emit-json extract is a receipt written beside the run, never a database file.

THE IDENTIFICATION (item 3(e)): by PROVIDER ID and season, never by an assumed row id. EXPECTED below is keyed by the
provider id and pins content only (team names, the live 2026 state, the 2025 state, the new orientation). Live: the
NCAA-competition row whose external_ids.api_american_football (compared as text: the stored value may be int or str)
equals the provider id and whose season reads the 2026 year (the leading-year rule of addendum 204 item 2) — exactly
one, else REFUSED; a live row with that provider id in 2025 is REFUSED (already restored, or never collided). The copy
(--from): the NCAA row with that provider id in season 2025 — exactly one, and its row id must equal the live row's (the
row was overwritten in place; a different id is another history: REFUSED). Row ids are read and printed. --ids is
optional: when given it must name exactly the live row ids found, each once. Then, as built: the live row must read the
2026 game (season, kickoff, provider id, the team names through the teams table, status FINISHED and the 2026 score by
team, written into the stored orientation by the chain of #884); the --from row must read the 2025 game (FINISHED and
the 2025 score). Everything WRITTEN is read from the copies: the new row is the live row with home/away (and every score
pair) swapped into the listing's orientation; the old row is the --from row, column for column.

--from-json PATH reads {"rows": [...]} as --emit-json wrote it: exactly the two pinned provider ids, each once, each
reading EXPECTED's 2025 state exactly (the kickoff naive UTC: any offset, or a "Z", is refused), else REFUSED. The restored row is then the LIVE row with the extract's season,
kickoff, status, scores (full_time_result from them), its own team ids (their names in the live teams table must be the
extract's: the 2025 game's stored orientation is the live row's) and external_ids without provider_orientation; id,
sport and competition_id kept; every other game-describing column the extract does not carry (NULLED below) written
NULL and printed on a "NULLED (not in the extract)" line naming the live value it replaces (law 4); a live column the
script does not know that holds a value is REFUSED, named.

WHAT MOVES, WHAT STAYS, WHAT REFUSES (law 4; enumerated from the live file's declared foreign keys to matches.id and
src/db/schema.py's, every table printed):
  * odds_snapshots / odds / match_stats (310 item 4): every row on the old id moves to the new id, each printed with its
    captured_at (where the table has one) and, where it has a selection, the selection before and after. With --from, a
    row the copy already held on that id was the 2025 game's: REFUSED (the ruling moves "every" row and does not say
    where a 2025 row goes); the table's live rows are still each printed (selection, book position) and the copy's
    rows listed. match_stats is by team_id: moved as is.
  * odds and odds_snapshots store their sides as HOME / AWAY (src/db/schema.py), not by team. A Kalshi snapshot (source
    "kalshi") was placed on the STORED home team's name (src/ingestion/kalshi_match.py), so on the new row, whose home
    is the stored away team, its HOME and AWAY swap (312 item 3(a): ruled as built). A BOOK row (every odds row with a
    HOME / AWAY side; an odds_snapshots row of any other source with one) follows --book-rows (312 item 3(b)): refuse
    (the default; the rows are printed and REFUSED), swap (HOME <-> AWAY on the move) or keep (moved as is) — one mode
    for every book row. Each is printed with its position against #885's merge (FIX_885_MERGED_AT): the tables have no
    written_at column, so captured_at, the time the writer stored the row, is the write stamp read here. After #885 it
    is in the stored orientation (-> swap); at or before it, the provider's, which is the new row's (-> keep). A side
    that names no team (DRAW, OVER, UNDER) moves as is.
  * every other table referencing the old id (312 item 3(c)), compared with the copy by the table's PRIMARY KEY (the
    integer pk, or the rowid where the table declares none), never by content: a row whose key the copy holds on that id
    with identical content is the 2025 game's and STAYS; a row whose key the copy does not hold on that id was ADDED
    since (the 2026 game's) and MOVES under --move-added (default: REFUSED, listed); a CHANGED row (same key, other
    content, or a value in a column only the live file holds, written since the copy) or a LOST row (in the copy, gone
    from the live file) is always REFUSED, named. With --from-json there is no copy: every such row is treated as added.
    An added row moves with its other columns as they are: the ruling names kalshi_settled_markets among the rows that
    move and names no swap outside the odds tables, so a value that reads by orientation (a value HOME / AWAY, or a
    value in a home/away column, e.g. kalshi_settled_markets.side) is moved as is and printed "ORIENTED" on the row's
    line, for the block to read.
  * the new rows' ids: matches.id is the rowid (no AUTOINCREMENT), so a new row takes max(id) + 1. A row of any table
    above already on that id (an orphan of a deleted match) would become the 2026 row's unplanned: REFUSED, named (the
    dry run checks the expected ids; the apply checks each created id again before any move).
  * availability_observations / availability_assertions carry match_id with NO foreign key and are append-only
    (addendum 254; triggers abort an UPDATE): printed, never moved (312 item 3(d)). Each id's count is printed (zeros
    included, the receipt); with --from, rows identical in the copy stay and a row added or changed since is REFUSED,
    named; with --from-json, any row is REFUSED, named (no copy shows it is the 2025 game's).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

SOURCE = "api_american_football"
ORIENTATION_KEY = "provider_orientation"          # src.ingestion.score_orientation.PROVIDER_ORIENTATION_KEY
COMPETITION = "NCAA"
MOVE_TABLES = ("odds_snapshots", "odds", "match_stats")          # item 4, verbatim
SIDED = ("HOME", "AWAY")
SWAP = {"HOME": "AWAY", "AWAY": "HOME"}
KALSHI = "kalshi"
SCORE_PAIRS = (("home_score", "away_score"), ("home_score_ht", "away_score_ht"), ("home_score_90", "away_score_90"))
# match_id columns with no foreign key (schema.py: "match_id is a plain integer, no foreign key"); append-only, never moved
UNKEYED = (("availability_observations", "match_id"), ("availability_assertions", "match_id"))
BOOK_MODES = ("refuse", "swap", "keep")
# #885 is an Issue, closed by PR #888, merged 2026-11-08T21:21:44Z (GitHub's merged_at for #888). Naive UTC, as
# captured_at is stored (src/db/schema.py: utc_now_naive). A row captured AFTER it was written by the stored-orientation
# writers; at or before it, by the provider's orientation.
FIX_885_MERGED_AT = datetime(2026, 11, 8, 21, 21, 44)
AFTER_885 = "after #885 (the stored orientation -> swap)"
BEFORE_885 = "before #885 (the provider's, which is the new row's -> keep)"
# --from-json: the extract's fields (provider id, season, kickoff, status, teams by name, scores; nothing else)
JSON_FIELDS = ("provider_id", "season", "kickoff", "status", "home", "away", "home_score", "away_score")
# --from-json: the game-describing columns of matches the extract does not carry, written NULL (law 4)
NULLED = ("status_raw", "home_score_ht", "away_score_ht", "home_score_90", "away_score_90", "venue", "referee",
          "matchday", "stage")
JSON_WRITTEN = ("season", "utc_date", "status", "home_team_id", "away_team_id", "home_score", "away_score",
                "full_time_result", "external_ids")
JSON_KEPT = ("id", "sport", "competition_id")
# src/ingestion/service.py season_year (addendum 204 item 2): the leading four-digit year; none -> unknown
_SEASON_YEAR = re.compile(r"(\d{4})(?!\d)")

# Item 1, the facts (stored orientation: the row's home team first), keyed by PROVIDER ID (312 item 3(e): "EXPECTED
# pins content, not ids"). `live`: the 2026 game as the row reads today (its score by team, the chain's write); `from`:
# the 2025 game, the row on 2026-10-09; `new`: the listing's orientation of the 2026 game.
EXPECTED = {
    "18216": {"home": "Utah", "away": "Cincinnati",
              "live": {"season": "2026", "kickoff": datetime(2026, 10, 31, 19, 45), "score": (49, 25)},
              "from": {"season": "2025", "kickoff": datetime(2025, 11, 2, 2, 15), "score": (45, 14)},
              "new": {"home": "Cincinnati", "away": "Utah", "score": (25, 49)}},
    "18240": {"home": "Alabama", "away": "LSU",
              "live": {"season": "2026", "kickoff": datetime(2026, 11, 7, 20, 30), "score": (31, 13)},
              "from": {"season": "2025", "kickoff": datetime(2025, 11, 9, 0, 30), "score": (20, 9)},
              "new": {"home": "LSU", "away": "Alabama", "score": (13, 31)}},
}


class Refused(Exception):
    """A check failed: exit 2, nothing written."""


def _uri(p: Path, query: str) -> str:
    return Path(p).resolve().as_uri() + "?" + query


def _qi(name: str) -> str:
    """An SQL identifier, quoted: the table and column names come from the live file (sqlite_master, its foreign
    keys), so an embedded double quote is doubled, never left to end the identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def open_from(p: Path) -> sqlite3.Connection:
    if not Path(p).is_file():
        raise Refused(f"--from {p}: no such file")
    con = sqlite3.connect(_uri(p, "mode=ro&immutable=1"), uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def open_live(p: Path, apply: bool) -> sqlite3.Connection:
    if not Path(p).is_file():
        raise Refused(f"--db {p}: no such file")
    if apply:
        # mode=rw: read-write on a file that exists, never created (a plain connect would create an empty file if the
        # path vanished after the check above: law 5's gravestone case)
        con = sqlite3.connect(_uri(p, "mode=rw"), uri=True, timeout=60, isolation_level=None)
        con.execute("PRAGMA foreign_keys = ON")
    else:
        con = sqlite3.connect(_uri(p, "mode=ro"), uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def _dt(v) -> datetime | None:
    if v is None:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def _naive(v) -> datetime | None:
    """--from-json's kickoff: an ISO 8601 text with NO offset (naive UTC, as --emit-json writes it), else None. The
    raw text is parsed as given: any offset ("+00:00", "-05:00") or a trailing "Z" (a ValueError on 3.10, an aware
    value on 3.11+) reads None, never a wall clock with its offset dropped."""
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    return dt if dt.tzinfo is None else None


def _ext(v) -> dict:
    if v is None:
        return {}
    try:
        out = json.loads(v) if isinstance(v, (str, bytes)) else dict(v)
    except (ValueError, TypeError):
        return {}
    return out if isinstance(out, dict) else {}


def season_year(season) -> int | None:
    """The leading four-digit year of a stored season string (src/ingestion/service.py season_year, addendum 204 item
    2): "2026", "2026/27", "2026-27" read 2026; no leading year reads unknown (None)."""
    if season is None:
        return None
    m = _SEASON_YEAR.match(str(season).strip())
    return int(m.group(1)) if m else None


def _columns(con, table) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info({_qi(table)})')]


def _pk(con, table) -> list[str]:
    """The table's declared primary-key columns, in key order ([] = none declared: the rowid is the key)."""
    return [r[1] for r in sorted((r for r in con.execute(f'PRAGMA table_info({_qi(table)})') if r[5]), key=lambda r: r[5])]


def _without_rowid(con, table) -> bool:
    r = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
    return bool(r and r[0] and "WITHOUT ROWID" in r[0].upper())


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def match_refs(con) -> list[tuple[str, str]]:
    """[(table, column)] for every column referencing matches.id: the live file's declared foreign keys (law 1) and
    src/db/schema.py's (a migration-built table may not declare one), for the tables the file holds."""
    out = set()
    have = _tables(con)
    for t in sorted(have):
        for fk in con.execute(f'PRAGMA foreign_key_list({_qi(t)})'):
            if fk[2] == "matches" and (fk[4] in (None, "id")):
                out.add((t, fk[3]))
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.db.schema import Base
        for t in Base.metadata.sorted_tables:
            if t.name not in have:
                continue
            for c in t.columns:
                if any(fk.target_fullname == "matches.id" for fk in c.foreign_keys):
                    out.add((t.name, c.name))
    except Exception as e:  # noqa: BLE001 — the file's own FKs stand; the miss is printed (law 2)
        print(f"  (schema.py not read: {type(e).__name__}: {e}; the file's declared foreign keys only)")
    return sorted(out)


def unkeyed_refs(con, refs) -> list[tuple[str, str]]:
    """UNKEYED's (table, column) pairs the live file holds and match_refs did not already name."""
    have = _tables(con)
    return [(t, c) for t, c in UNKEYED if t in have and c in _columns(con, t) and (t, c) not in refs]


def _refs_on(con, pairs, mid) -> list[tuple[str, str, int]]:
    """[(table, column, n)] for every (table, column) in `pairs` holding n > 0 rows on `mid`."""
    out = []
    for t, c in pairs:
        n = con.execute(f'SELECT COUNT(*) FROM {_qi(t)} WHERE {_qi(c)} = ?', (mid,)).fetchone()[0]
        if n:
            out.append((t, c, n))
    return out


def _team(con, tid) -> str | None:
    r = con.execute("SELECT name FROM teams WHERE id = ?", (tid,)).fetchone()
    return None if r is None else r[0]


def _row(con, mid) -> dict | None:
    r = con.execute("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
    return None if r is None else dict(r)


def _comp_code(con, cid) -> str | None:
    r = con.execute("SELECT code FROM competitions WHERE id = ?", (cid,)).fetchone()
    return None if r is None else r[0]


def find_rows(con, pid: str) -> list[dict]:
    """Every NCAA-competition row whose external_ids[SOURCE], read as text, is `pid` (the stored value may be an int or
    a str), as [{id, season, year}], by id."""
    comps = [r[0] for r in con.execute("SELECT id FROM competitions WHERE code = ?", (COMPETITION,))]
    out = []
    for cid in comps:
        for r in con.execute("SELECT id, season, external_ids FROM matches WHERE competition_id = ?", (cid,)):
            v = _ext(r["external_ids"]).get(SOURCE)
            if v is not None and not isinstance(v, bool) and str(v) == pid:
                out.append({"id": r["id"], "season": r["season"], "year": season_year(r["season"])})
    return sorted(out, key=lambda x: x["id"])


def describe(con, m: dict) -> str:
    return (f"season {m.get('season')} · {m.get('utc_date')} · {m.get('status')} · "
            f"{_team(con, m.get('home_team_id'))} {m.get('home_score')} v {_team(con, m.get('away_team_id'))} "
            f"{m.get('away_score')} · ftr {m.get('full_time_result')} · {SOURCE} {_ext(m.get('external_ids')).get(SOURCE)}"
            f" · external_ids {m.get('external_ids')}")


def check_state(con, m: dict | None, mid: int, pid: str, exp: dict, which: str) -> list[str]:
    """The refusals for one row against its pinned state (`which` "live" or "from"); [] = it reads exactly that."""
    if m is None:
        return [f"{which} row {mid} (provider id {pid}) does not exist"]
    want = exp[which]
    bad = []
    if _comp_code(con, m.get("competition_id")) != COMPETITION:
        bad.append(f"competition {_comp_code(con, m.get('competition_id'))!r}, not {COMPETITION}")
    if str(m.get("season")) != want["season"]:
        bad.append(f"season {m.get('season')!r}, not {want['season']!r}")
    if _dt(m.get("utc_date")) != want["kickoff"]:
        bad.append(f"kickoff {m.get('utc_date')!r}, not {want['kickoff']:%Y-%m-%d %H:%M}Z")
    if str(_ext(m.get("external_ids")).get(SOURCE)) != pid:
        bad.append(f"{SOURCE} {_ext(m.get('external_ids')).get(SOURCE)!r}, not {pid}")
    names = (_team(con, m.get("home_team_id")), _team(con, m.get("away_team_id")))
    if names != (exp["home"], exp["away"]):
        bad.append(f"teams {names[0]!r} v {names[1]!r}, not {exp['home']} v {exp['away']}")
    if m.get("status") != "FINISHED":
        bad.append(f"status {m.get('status')!r}, not FINISHED")
    if (m.get("home_score"), m.get("away_score")) != want["score"]:
        bad.append(f"score {m.get('home_score')}-{m.get('away_score')}, not {want['score'][0]}-{want['score'][1]}")
    return [f"{which} row {mid} (provider id {pid}): {b}" for b in bad]


def identify(live, frm, pid: str, out) -> tuple[int | None, list[str]]:
    """312 item 3(e): the live row id for `pid` (the 2026 row; no 2025 row in the live file; the copy's 2025 row on the
    SAME id), or None with the refusals. Every row found is printed with its id."""
    live_year, from_year = (season_year(EXPECTED[pid][k]["season"]) for k in ("live", "from"))
    found = find_rows(live, pid)
    out(f"FOUND {pid} live: " + (", ".join(f"row {r['id']} season {r['season']!r}" for r in found) or "no NCAA row"))
    bad = []
    now = [r for r in found if r["year"] == live_year]
    if len(now) != 1:
        bad.append(f"provider id {pid}: {len(now)} live NCAA row(s) in season year {live_year} "
                   f"({', '.join(str(r['id']) for r in now) or 'none'}), not exactly one")
    old = [r for r in found if r["year"] == from_year]
    if old:
        bad.append(f"provider id {pid}: the live file already holds a {from_year} row "
                   f"({', '.join(str(r['id']) for r in old)}): already restored, or never collided")
    unknown = [r for r in found if r["year"] is None]
    if unknown:
        bad.append(f"provider id {pid}: live row(s) {', '.join(str(r['id']) for r in unknown)} with no season year")
    if frm is not None:
        cfound = find_rows(frm, pid)
        out(f"FOUND {pid} from: " + (", ".join(f"row {r['id']} season {r['season']!r}" for r in cfound)
                                     or "no NCAA row"))
        c = [r for r in cfound if r["year"] == from_year]
        if len(c) != 1:
            bad.append(f"provider id {pid}: {len(c)} NCAA row(s) in season year {from_year} in the copy "
                       f"({', '.join(str(r['id']) for r in c) or 'none'}), not exactly one")
        elif len(now) == 1 and c[0]["id"] != now[0]["id"]:
            bad.append(f"provider id {pid}: the copy's {from_year} row is {c[0]['id']} and the live {live_year} row "
                       f"is {now[0]['id']}: the row was overwritten in place; a different id is another history")
    return (now[0]["id"] if not bad else None), bad


def _ftr(h, a) -> str | None:
    if h is None or a is None:
        return None
    return "HOME" if h > a else "AWAY" if a > h else "DRAW"


def new_row(live: dict) -> dict:
    """The live row in the LISTING's orientation: home/away and every score pair swapped, full_time_result by the new
    orientation, status FINISHED, provider_orientation removed; every other column as the live row (id assigned)."""
    out = {k: v for k, v in live.items() if k != "id"}
    out["home_team_id"], out["away_team_id"] = live["away_team_id"], live["home_team_id"]
    for h, a in SCORE_PAIRS:
        if h in live and a in live:
            out[h], out[a] = live[a], live[h]
    out["full_time_result"] = _ftr(out.get("home_score"), out.get("away_score"))
    out["status"] = "FINISHED"
    ext = _ext(live.get("external_ids"))
    ext.pop(ORIENTATION_KEY, None)
    out["external_ids"] = json.dumps(ext)
    return out


def restored_row(frm: dict, live_cols: list[str]) -> dict:
    """The --from row, column for column (the live file's columns; a column the copy lacks is refused upstream unless
    the live value is NULL), external_ids with provider_orientation removed (the copy's text kept when it has none)."""
    out = {k: frm[k] for k in live_cols if k in frm and k != "id"}
    ext = _ext(frm.get("external_ids"))
    if ORIENTATION_KEY in ext:
        ext.pop(ORIENTATION_KEY)
        out["external_ids"] = json.dumps(ext)
    return out


def _like(stored, dt: datetime) -> str:
    """`dt` in the stored value's own text shape (SQLAlchemy's "YYYY-MM-DD HH:MM:SS.ffffff" by default), so the
    restored kickoff sorts and compares with every other row's."""
    s = str(stored or "")
    sep = "T" if "T" in s else " "
    return dt.strftime(f"%Y-%m-%d{sep}%H:%M:%S" + (".%f" if "." in s or not s else ""))


def json_restored_row(live: dict, x: dict, live_cols: list[str]) -> tuple[dict, list[tuple[str, object]]]:
    """--from-json: the columns written on the live row (the extract's 2025 state on the live row's own team ids;
    external_ids without provider_orientation; NULLED written NULL) and [(column, the live value replaced)] of NULLED."""
    ext = _ext(live.get("external_ids"))
    ext.pop(ORIENTATION_KEY, None)
    out = {"season": x["season"], "utc_date": _like(live.get("utc_date"), _dt(x["kickoff"])), "status": x["status"],
           "home_team_id": live["home_team_id"], "away_team_id": live["away_team_id"],
           "home_score": x["home_score"], "away_score": x["away_score"],
           "full_time_result": _ftr(x["home_score"], x["away_score"]), "external_ids": json.dumps(ext)}
    nulled = [(c, live.get(c)) for c in NULLED if c in live_cols]
    out.update({c: None for c, _ in nulled})
    return out, nulled


def read_extract(path: Path) -> tuple[dict, list[str]]:
    """--from-json: ({provider id: row}, refusals). Exactly the two pinned provider ids, each once, each reading
    EXPECTED's 2025 state exactly (season, kickoff, status FINISHED, home/away names, scores), JSON_FIELDS only."""
    if not Path(path).is_file():
        raise Refused(f"--from-json {path}: no such file")
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Refused(f"--from-json {path}: not JSON ({e})")
    if not isinstance(doc, dict) or set(doc) != {"rows"} or not isinstance(doc["rows"], list):
        raise Refused(f"--from-json {path}: not {{\"rows\": [...]}} as --emit-json writes it")
    bad, rows = [], {}
    for i, r in enumerate(doc["rows"]):
        if not isinstance(r, dict) or set(r) != set(JSON_FIELDS):
            bad.append(f"extract row {i}: fields {sorted(r) if isinstance(r, dict) else type(r).__name__}, not "
                       f"{sorted(JSON_FIELDS)}")
            continue
        pid = r["provider_id"]
        if not isinstance(pid, str) or pid not in EXPECTED:
            bad.append(f"extract row {i}: provider id {pid!r} is not a pinned provider id {sorted(EXPECTED)}")
            continue
        if pid in rows:
            bad.append(f"extract: provider id {pid} more than once")
            continue
        rows[pid] = r
        exp = EXPECTED[pid]
        ko = _naive(r["kickoff"])
        scores = (r["home_score"], r["away_score"])
        if r["season"] != exp["from"]["season"]:
            bad.append(f"extract {pid}: season {r['season']!r}, not {exp['from']['season']!r}")
        if ko != exp["from"]["kickoff"]:
            bad.append(f"extract {pid}: kickoff {r['kickoff']!r}, not {exp['from']['kickoff'].isoformat()} (naive UTC)")
        if r["status"] != "FINISHED":
            bad.append(f"extract {pid}: status {r['status']!r}, not FINISHED")
        if (r["home"], r["away"]) != (exp["home"], exp["away"]):
            bad.append(f"extract {pid}: teams {r['home']!r} v {r['away']!r}, not {exp['home']} v {exp['away']}")
        if any(type(s) is not int for s in scores) or scores != exp["from"]["score"]:
            bad.append(f"extract {pid}: score {scores[0]!r}-{scores[1]!r}, not "
                       f"{exp['from']['score'][0]}-{exp['from']['score'][1]}")
    missing = sorted(set(EXPECTED) - set(rows))
    if missing:
        bad.append(f"extract: provider id(s) {missing} missing")
    return rows, bad


def emit_rows(frm, rows: dict) -> list[dict]:
    """--emit-json: the copy's 2025 rows' fields and nothing else (no row ids, no team ids), sorted by provider id."""
    out = []
    for pid in sorted(rows):
        fm = rows[pid]["from"]
        out.append({"provider_id": pid, "season": fm["season"], "kickoff": _dt(fm["utc_date"]).isoformat(),
                    "status": fm["status"], "home": _team(frm, fm["home_team_id"]),
                    "away": _team(frm, fm["away_team_id"]), "home_score": fm["home_score"],
                    "away_score": fm["away_score"]})
    return out


def write_extract(path: Path, rows: list[dict], out) -> None:
    data = (json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise Refused(f"--emit-json {path} exists; the extract is created exclusively, never overwritten")
    except OSError as e:
        raise Refused(f"--emit-json {path}: not created ({type(e).__name__}: {e}); the database files untouched")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except OSError as e:
        # this run created the file (O_EXCL): a partial extract is removed, never left as a receipt
        try:
            os.unlink(str(path))
        except OSError:
            pass
        raise Refused(f"--emit-json {path}: not written ({type(e).__name__}: {e}); removed; the database files "
                      f"untouched")
    out(f"EMITTED {path} · {len(rows)} row(s) · sha256 {hashlib.sha256(data).hexdigest()} (a receipt, not a database)")


def _summary(r: dict, col: str, width: int = 140) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in r.items() if k not in ("__rowid__", col) and v is not None)
    return s if len(s) <= width else s[:width - 3] + "..."


def _oriented(r: dict, col: str) -> list[str]:
    """The values that read by orientation: a HOME / AWAY value, or any value in a column named home/away."""
    return [f"{k}={v!r}" for k, v in r.items() if k not in ("__rowid__", col) and v is not None
            and (v in SIDED or "home" in k.lower() or "away" in k.lower())]


def _book_position(captured_at) -> str:
    ts = _dt(captured_at)
    if ts is None:
        return "captured_at unreadable (no position against #885)"
    return AFTER_885 if ts > FIX_885_MERGED_AT else BEFORE_885


def _who(r: dict) -> str:
    parts = [f"source {r.get('source')!r}"] if "source" in r else []
    if "bookmaker" in r:
        parts.append(f"bookmaker {r.get('bookmaker')!r}")
    if "market" in r:
        parts.append(f"market {r.get('market')!r}")
    if "captured_at" in r:
        parts.append(f"captured_at {r.get('captured_at')}")
    return ", ".join(parts)


def plan_refs(live, frm, refs, unkeyed, mid, book_rows: str, move_added: bool, out) -> tuple[list, list, list]:
    """(moves, stays, refusals) for every table referencing `mid`, every row printed as it is read (a refused one
    included). moves: (table, col, rowid, {col: new values}, row, kind) with kind "item4" or "added"; stays: (table, n);
    refusals: lines. `frm` None = --from-json (no copy)."""
    moves, stays, bad = [], [], []
    from_tables = _tables(frm) if frm is not None else set()
    for t, col in refs + unkeyed:
        is_unkeyed = (t, col) in unkeyed
        if _without_rowid(live, t):
            n = live.execute(f'SELECT COUNT(*) FROM {_qi(t)} WHERE {_qi(col)} = ?', (mid,)).fetchone()[0]
            if n:
                bad.append(f"{t}: {n} row(s) on {mid} in a WITHOUT ROWID table — not handled, not guessed")
            continue
        pk = _pk(live, t)
        lrows = [dict(r) for r in live.execute(f'SELECT rowid AS "__rowid__", * FROM {_qi(t)} WHERE {_qi(col)} = ?', (mid,))]
        has_copy = frm is not None and t in from_tables and col in _columns(frm, t)
        frows = [dict(r) for r in frm.execute(f'SELECT rowid AS "__rowid__", * FROM {_qi(t)} WHERE {_qi(col)} = ?',
                                              (mid,))] if has_copy else []

        def key(r, _pk=pk):
            return tuple(r.get(c) for c in _pk) if _pk else (r["__rowid__"],)

        def kname(k):
            return str(k[0]) if len(k) == 1 else str(k)

        if t in MOVE_TABLES:
            # every live row is printed (its selection before/after, a book row's position against #885) in every
            # case; with a 2025 row in the copy the table is refused, and nothing of it moves
            planned = []
            for r in lrows:
                _plan_move(t, col, r, mid, book_rows, planned, bad, out)
            if frows:
                for r in frows:
                    out(f"COPY {mid} {t} row {r['__rowid__']}: {_summary(r, col)} (in the copy on {mid}: the 2025 "
                        f"game's)")
                bad.append(f"{t}: the copy holds {len(frows)} row(s) on {mid} (the 2025 game's); item 4 moves every "
                           f"row to the new id and does not say where a 2025 row goes — not guessed")
                continue
            moves += planned
            continue
        if frm is None:
            if is_unkeyed:
                for r in lrows:
                    out(f"UNKEYED {mid} {t} row {kname(key(r))}: {_summary(r, col)} -> REFUSED (--from-json: no copy "
                        f"shows it is the 2025 game's; append-only, never moved)")
                if lrows:
                    bad.append(f"{t}: {len(lrows)} row(s) on {mid}; with --from-json no copy shows they are the 2025 "
                               f"game's, and the table is never moved — not guessed")
                continue
            added, changed, lost, same = lrows, [], [], []
        else:
            lcols = _columns(live, t)
            fcols = [c for c in lcols if has_copy and c in _columns(frm, t)]
            # a column only the live file holds (a migration after the copy): a value in it was written since the
            # copy, so the row is not the copy's (law 4, as for a matches column the copy lacks)
            lonly = [c for c in lcols if c not in fcols]
            fby = {key(r): r for r in frows}
            lby = {key(r): r for r in lrows}
            added = [r for k, r in lby.items() if k not in fby]
            diff = {}
            for k, r in lby.items():
                if k in fby:
                    d = [f"{c} {fby[k].get(c)!r} -> {r.get(c)!r}" for c in fcols if r.get(c) != fby[k].get(c)]
                    d += [f"{c} {r.get(c)!r} (not in the copy)" for c in lonly if r.get(c) is not None]
                    if d:
                        diff[k] = d
            changed = [r for k, r in lby.items() if k in diff]
            same = [r for k, r in lby.items() if k in fby and k not in diff]
            lost = [r for k, r in fby.items() if k not in lby]
        for r in changed:
            out(f"CHANGED {mid} {t} row {kname(key(r))}: {_summary(r, col)} -> REFUSED (same key as the copy's row, "
                f"other content: {'; '.join(diff[key(r)])})")
        for r in lost:
            out(f"LOST {mid} {t} row {kname(key(r))}: {_summary(r, col)} -> REFUSED (in the copy, gone from the live "
                f"file)")
        if changed or lost:
            bad.append(f"{t}: {len(changed)} row(s) on {mid} changed since the copy "
                       f"({', '.join(kname(key(r)) for r in changed) or 'none'}), {len(lost)} row(s) of the copy gone "
                       f"({', '.join(kname(key(r)) for r in lost) or 'none'}); the ruling does not say where they go — "
                       f"not guessed")
        refused_added = []
        for r in added:
            k = kname(key(r))
            orient = _oriented(r, col)
            # 312 item 3(c): an added row MOVES under --move-added, its other columns as they are (the ruling names
            # kalshi_settled_markets among them and names no swap outside the odds tables). A value that reads by
            # orientation is printed on the row's line so the block sees it; nothing is swapped.
            note = (f"; ORIENTED, moved as is (no ruling swaps it; the new row's home is the old row's away): "
                    f"{', '.join(orient)}" if orient else "")
            if is_unkeyed:
                out(f"ADDED {mid} {t} row {k}: {_summary(r, col)} -> REFUSED (append-only, never moved)")
                refused_added.append(k)
            elif move_added:
                out(f"ADDED {mid} {t} row {k}: {_summary(r, col)} -> MOVE to the new id (--move-added){note}")
                moves.append((t, col, r["__rowid__"], {col: "<new>"}, r, "added"))
            else:
                out(f"ADDED {mid} {t} row {k}: {_summary(r, col)} -> REFUSED (no --move-added){note}")
                refused_added.append(k)
        if refused_added:
            why = "the table is append-only, never moved" if is_unkeyed else "--move-added not given"
            bad.append(f"{t}: {len(refused_added)} row(s) on {mid} added since the copy "
                       f"({', '.join(refused_added)}); {why}")
        if same and not (changed or lost):
            stays.append((t, len(same)))
    return moves, stays, bad


def _plan_move(t, col, r, mid, book_rows, moves, bad, out) -> None:
    """One odds_snapshots / odds / match_stats row: the Kalshi swap (312 item 3(a)), a book row by --book-rows (3(b)),
    every other row as is. Printed with its selection before and after, whatever happens to it."""
    upd = {col: "<new>"}
    sel, src = r.get("selection"), r.get("source")
    how = "as is"
    if t in ("odds", "odds_snapshots") and sel in SIDED:
        if t == "odds_snapshots" and src == KALSHI:
            upd["selection"] = SWAP[sel]
            how = "swapped: Kalshi, on the stored home's name (addendum 312 item 3(a))"
        else:
            pos = _book_position(r.get("captured_at"))
            out(f"BOOK {mid} {t} row {r['__rowid__']}: {_who(r)}, selection {sel} · {pos} · --book-rows {book_rows}"
                + (": REFUSED" if book_rows == "refuse" else
                   f": selection {sel} -> {SWAP[sel] if book_rows == 'swap' else sel}"))
            if book_rows == "refuse":
                bad.append(f"{t} row {r['__rowid__']} ({_who(r)}, selection {sel!r}): a book side stored as HOME/AWAY "
                           f"({pos}); --book-rows refuse")
                return
            if book_rows == "swap":
                upd["selection"] = SWAP[sel]
                how = "swapped: --book-rows swap"
            else:
                how = "as is: --book-rows keep"
    moves.append((t, col, r["__rowid__"], upd, r, "item4"))
    out(f"PLAN {mid} MOVE {t} row {r['__rowid__']}: {col} {mid} -> the new id"
        + (f", selection {sel} -> {upd.get('selection', sel)} ({how})" if "selection" in r else "")
        + (f" ({_who(r)})" if _who(r) else ""))


def run(db: Path, frm_path: Path | None = None, ids: list[int] | None = None, apply: bool = False, *,
        from_json: Path | None = None, book_rows: str = "refuse", move_added: bool = False,
        emit_json: Path | None = None, out=print, _fail_at: str | None = None) -> int:
    out(f"restore_collided_rows (ARCHITECT 2026-11-09, addendum 310 item 4 and addendum 312 item 3; #902): "
        f"{'APPLY' if apply else 'DRY RUN'} · --db {db} "
        f"({'read-write, ONE transaction' if apply else 'read-only, mode=ro'}) · "
        + (f"--from {frm_path} (mode=ro&immutable=1)" if frm_path is not None else f"--from-json {from_json}")
        + f" · --book-rows {book_rows} · --move-added {'on' if move_added else 'off'} · --ids "
        + (", ".join(str(i) for i in ids) if ids else "(not given: the rows found by provider id)")
        + (f" · --emit-json {emit_json}" if emit_json is not None else ""))
    if (frm_path is None) == (from_json is None):
        raise Refused("exactly one of --from / --from-json")
    if book_rows not in BOOK_MODES:
        raise Refused(f"--book-rows {book_rows!r}, not one of {BOOK_MODES}")
    if emit_json is not None:
        if apply or frm_path is None:
            raise Refused("--emit-json only with --dry-run and --from")
        if os.path.lexists(emit_json):
            raise Refused(f"--emit-json {emit_json} exists; the extract is created exclusively, never overwritten")
        if not Path(emit_json).parent.is_dir():
            raise Refused(f"--emit-json {emit_json}: its directory {Path(emit_json).parent} does not exist")
    if frm_path is not None and Path(db).resolve() == Path(frm_path).resolve():
        raise Refused("--db and --from are the same file")
    if ids is not None and len(set(ids)) != len(ids):
        raise Refused(f"--ids names an id twice (given: {ids})")
    extract, xbad = read_extract(from_json) if from_json is not None else (None, [])
    if xbad:
        for b in xbad:
            out(f"REFUSED: {b}")
        raise Refused(f"--from-json {from_json}: {len(xbad)} check(s) failed; nothing written")
    frm = open_from(frm_path) if frm_path is not None else None
    live = open_live(db, apply)
    state: dict = {}
    try:
        if apply:
            live.execute("BEGIN IMMEDIATE")
        try:
            rc = _run(live, frm, extract, ids, apply, book_rows, move_added, out, _fail_at, state)
        except BaseException:
            if apply and live.in_transaction:
                live.execute("ROLLBACK")
                out("ROLLED BACK: nothing written")
            raise
        if apply:
            live.execute("COMMIT")
            out("COMMITTED")
        if emit_json is not None and rc == 0:
            emitted = emit_rows(frm, state["rows"])
        else:
            emitted = None
    finally:
        live.close()
        if frm is not None:
            frm.close()
    if emitted is not None:
        write_extract(Path(emit_json), emitted, out)
    return rc


def _run(live, frm, extract, ids, apply, book_rows, move_added, out, _fail_at, state) -> int:
    refs = match_refs(live)
    out(f"tables referencing matches.id (the live file's foreign keys and src/db/schema.py's): "
        f"{', '.join(f'{t}.{c}' for t, c in refs) or 'none'}")
    unkeyed = unkeyed_refs(live, refs)
    out(f"match_id columns with no foreign key (append-only, never moved): "
        f"{', '.join(f'{t}.{c}' for t, c in unkeyed) or 'none in this file'}")
    # 312 item 3(e): the rows by PROVIDER ID and season, never by an assumed row id
    bad, found = [], {}
    for pid in sorted(EXPECTED):
        mid, b = identify(live, frm, pid, out)
        bad += b
        if mid is not None:
            found[pid] = mid
            out(f"ROW {pid}: live row id {mid} (season {EXPECTED[pid]['live']['season']})"
                + (f"; the copy's {EXPECTED[pid]['from']['season']} row reads the same id" if frm is not None else ""))
    if not bad and ids is not None and sorted(ids) != sorted(found.values()):
        bad.append(f"--ids must name exactly the live row ids found by provider id "
                   f"{sorted(found.values())}, each once (given: {ids})")
    if bad:
        for b in bad:
            out(f"REFUSED: {b}")
        raise Refused(f"{len(bad)} check(s) failed; nothing written")
    pids = sorted(found)
    live_cols = _columns(live, "matches")
    from_cols = set(_columns(frm, "matches")) if frm is not None else set()
    rows = {}
    for pid in pids:
        mid, exp = found[pid], EXPECTED[pid]
        lm = _row(live, mid)
        out(f"BEFORE {mid} live: {describe(live, lm) if lm else 'absent'}")
        bad += check_state(live, lm, mid, pid, exp, "live")
        if frm is not None:
            fm = _row(frm, mid)
            out(f"BEFORE {mid} from: {describe(frm, fm) if fm else 'absent'}")
            bad += check_state(frm, fm, mid, pid, exp, "from")
            if lm and fm:
                for k in ("home_team_id", "away_team_id"):
                    if _team(live, fm[k]) != _team(frm, fm[k]):
                        bad.append(f"from row {mid}: {k} {fm[k]} reads {_team(frm, fm[k])!r} in the copy and "
                                   f"{_team(live, fm[k])!r} in the live file")
                for k in live_cols:
                    if k not in from_cols and lm.get(k) is not None:
                        bad.append(f"from row {mid}: column {k} is not in the copy and the live row holds "
                                   f"{lm.get(k)!r}")
            rows[pid] = {"mid": mid, "live": lm, "from": fm}
        else:
            x = extract[pid]
            out(f"BEFORE {mid} extract: {json.dumps(x, sort_keys=True)}")
            if lm:
                names = (_team(live, lm["home_team_id"]), _team(live, lm["away_team_id"]))
                if names != (x["home"], x["away"]):
                    bad.append(f"live row {mid}: its teams read {names[0]!r} v {names[1]!r} in the live teams table, "
                               f"not the extract's {x['home']} v {x['away']}")
                known = set(JSON_WRITTEN) | set(JSON_KEPT) | set(NULLED)
                for k in live_cols:
                    if k not in known and lm.get(k) is not None:
                        bad.append(f"live row {mid}: column {k} holds {lm.get(k)!r}; the extract does not carry it and "
                                   f"the ruling does not name it — not guessed")
            rows[pid] = {"mid": mid, "live": lm, "extract": x}
    moves, stays = {}, {}
    for pid in pids:
        mid = found[pid]
        mv, st, rf = plan_refs(live, frm, refs, unkeyed, mid, book_rows, move_added, out)
        moves[pid], stays[pid] = mv, st
        bad += [f"row {mid}: {x}" for x in rf]
        for t, col in unkeyed:
            n = live.execute(f'SELECT COUNT(*) FROM {_qi(t)} WHERE {_qi(col)} = ?', (mid,)).fetchone()[0]
            out(f"COUNT {mid} {t}.{col}: {n} row(s) (no foreign key; append-only, addendum 254: never moved)")
    # the ids the new rows will take: matches.id is the rowid (no AUTOINCREMENT), so the next insert takes
    # max(id) + 1. A row already on that id (an orphan of a deleted match: the availability tables have no foreign
    # key) would silently become the new row's, never planned or printed: REFUSED, named.
    top = live.execute("SELECT MAX(id) FROM matches").fetchone()[0] or 0
    for i, pid in enumerate(pids):
        nid = top + 1 + i
        held = _refs_on(live, refs + unkeyed, nid)
        out(f"NEW ID {nid} (expected for {found[pid]}): "
            + (", ".join(f"{t}.{c} {n} row(s)" for t, c, n in held) if held else "no row references it"))
        if held:
            bad.append(f"the new row's id {nid} (max(matches.id) + {1 + i}) is already referenced: "
                       f"{', '.join(f'{t}.{c} {n} row(s)' for t, c, n in held)}; they would become the 2026 row's "
                       f"unplanned — not guessed")
    if bad:
        for b in bad:
            out(f"REFUSED: {b}")
        raise Refused(f"{len(bad)} check(s) failed; nothing written")
    state["rows"] = rows
    created = {}
    changes_before = live.total_changes
    for pid in pids:
        mid, lm, exp = found[pid], rows[pid]["live"], EXPECTED[pid]
        nr = new_row(lm)
        if (nr["home_score"], nr["away_score"]) != exp["new"]["score"] or \
                (_team(live, nr["home_team_id"]), _team(live, nr["away_team_id"])) != (exp["new"]["home"],
                                                                                       exp["new"]["away"]):
            raise Refused(f"row {mid}: the new row would read {_team(live, nr['home_team_id'])} "
                          f"{nr['home_score']} v {_team(live, nr['away_team_id'])} {nr['away_score']}, not item 4's "
                          f"{exp['new']['home']} {exp['new']['score'][0]} v {exp['new']['away']} "
                          f"{exp['new']['score'][1]}")
        out(f"PLAN {mid} -> NEW 2026 row (the listing's orientation): {describe(live, nr)}")
        if frm is not None:
            rr = restored_row(rows[pid]["from"], live_cols)
            out(f"PLAN {mid} -> its copy's content: {describe(frm, rr)}")
        else:
            rr, nulled = json_restored_row(lm, rows[pid]["extract"], live_cols)
            out(f"PLAN {mid} -> the extract's 2025 state (--from-json): {describe(live, {**lm, **rr})}")
            for c, v in nulled:
                out(f"NULLED (not in the extract) {mid}.{c}: live value {v!r} -> NULL")
        by_table: dict = {}
        for t, col, rowid, upd, r, kind in moves[pid]:
            k = by_table.setdefault(t, {"rows": 0, "swapped": 0})
            k["rows"] += 1
            k["swapped"] += "selection" in upd and t == "odds_snapshots" and r.get("source") == KALSHI
        for t in MOVE_TABLES:
            k = by_table.get(t, {"rows": 0, "swapped": 0})
            out(f"PLAN {mid} MOVE {t}: {k['rows']} row(s) to the new id"
                + (f" ({k['swapped']} Kalshi HOME/AWAY swapped to the new orientation)" if t == "odds_snapshots" else ""))
        for t, k in sorted(by_table.items()):
            if t not in MOVE_TABLES:
                out(f"PLAN {mid} MOVE {t}: {k['rows']} row(s) added since the copy to the new id (--move-added)")
        for t, n in stays[pid]:
            out(f"PLAN {mid} STAY {t}: {n} row(s), identical in the copy (the 2025 game's), kept on {mid}")
        if not apply:
            continue
        cols = list(nr)
        cur = live.execute(f'INSERT INTO matches ({", ".join(_qi(c) for c in cols)}) '
                           f'VALUES ({", ".join("?" * len(cols))})', [nr[c] for c in cols])
        new_id = cur.lastrowid
        created[pid] = new_id
        out(f"CREATED {new_id} for {mid}")
        held = _refs_on(live, refs + unkeyed, new_id)
        if held:
            held_s = ", ".join(f"{t}.{c} {n} row(s)" for t, c, n in held)
            raise Refused(f"the new row {new_id} is already referenced ({held_s}); rolled back")
        if _fail_at == "after_create":
            raise RuntimeError("injected failure (test): after the create")
        for t, col, rowid, upd, _r, _kind in moves[pid]:
            sets = {**upd, col: new_id}
            live.execute(f'UPDATE {_qi(t)} SET {", ".join(f"{_qi(k)} = ?" for k in sets)} WHERE rowid = ?',
                         [*sets.values(), rowid])
        if _fail_at == "after_moves":
            raise RuntimeError("injected failure (test): after the moves")
        live.execute(f'UPDATE matches SET {", ".join(f"{_qi(k)} = ?" for k in rr)} WHERE id = ?',
                     [*rr.values(), mid])
    if not apply:
        out("DRY RUN: nothing written")
        return 0
    for pid in pids:
        mid, new_id = found[pid], created[pid]
        out(f"AFTER {mid}: {describe(live, _row(live, mid))}")
        out(f"AFTER {new_id} (new, for {mid}): {describe(live, _row(live, new_id))}")
        for t in MOVE_TABLES:
            if t in _tables(live):
                col = next(c for tt, c in refs if tt == t) if any(tt == t for tt, _ in refs) else "match_id"
                n_old = live.execute(f'SELECT COUNT(*) FROM {_qi(t)} WHERE {_qi(col)} = ?', (mid,)).fetchone()[0]
                n_new = live.execute(f'SELECT COUNT(*) FROM {_qi(t)} WHERE {_qi(col)} = ?', (new_id,)).fetchone()[0]
                out(f"AFTER {t}: {n_old} row(s) on {mid} · {n_new} row(s) on {new_id}")
        for t, col, rowid, upd, _r, _kind in moves[pid]:
            a = live.execute(f'SELECT * FROM {_qi(t)} WHERE rowid = ?', (rowid,)).fetchone()
            a = {} if a is None else dict(a)
            out(f"AFTER {t} row {rowid}: {col} {a.get(col)}"
                + (f", selection {a.get('selection')}" if "selection" in a else ""))
        lm = _row(live, mid)
        exp = EXPECTED[pid]
        bad_after = check_state(live, lm, mid, pid, exp, "from") + check_state(live, _row(live, new_id), new_id, pid, {
            **exp, "home": exp["new"]["home"], "away": exp["new"]["away"],
            "from": {**exp["live"], "score": exp["new"]["score"]}}, "from")
        if frm is None:
            bad_after += [f"{mid}.{c} reads {lm.get(c)!r}, not NULL" for c in NULLED if lm.get(c) is not None]
        if bad_after:
            raise Refused(f"row {mid}: the written state does not read as planned ({'; '.join(bad_after)}); "
                          f"rolled back")
    # the rows written, counted before the commit: two inserts, the moved rows (item 4's and the added ones under
    # --move-added), the two rewrites; anything else rolls back
    n_item4 = sum(1 for pid in pids for m in moves[pid] if m[5] == "item4")
    n_added = sum(1 for pid in pids for m in moves[pid] if m[5] == "added")
    want = len(pids) + n_item4 + n_added + len(pids)
    got = live.total_changes - changes_before
    out(f"ROWS WRITTEN: {got} (expected {want}: {len(pids)} created, {n_item4} moved, {n_added} added moved, "
        f"{len(pids)} restored)")
    if got != want:
        raise Refused(f"{got} row(s) written, not the {want} planned; rolled back")
    if _fail_at == "before_commit":
        raise RuntimeError("injected failure (test): before the commit")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--db", required=True, type=Path, help="the live DB (read-write only on --apply)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from", dest="frm", type=Path,
                     help="a .backup copy holding the two 2025 rows intact (opened mode=ro&immutable=1)")
    src.add_argument("--from-json", dest="from_json", type=Path,
                     help="the two 2025 rows' fields as --emit-json wrote them (no copy of the referencing tables)")
    ap.add_argument("--ids", help="optional: the live row ids, comma-separated; must be exactly the ids found by "
                                  "provider id")
    ap.add_argument("--book-rows", choices=BOOK_MODES, default="refuse",
                    help="book HOME/AWAY odds rows: refuse (default), swap, or keep (addendum 312 item 3(b))")
    ap.add_argument("--move-added", action="store_true",
                    help="move rows of other tables added since the copy to the new id (addendum 312 item 3(c))")
    ap.add_argument("--emit-json", dest="emit_json", type=Path,
                    help="with --dry-run and --from only: write the two 2025 rows' fields to this NEW path")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    mode.add_argument("--apply", action="store_true", help="write it, in ONE transaction (the architect's block)")
    a = ap.parse_args(argv)
    ids = None
    if a.ids is not None:
        try:
            ids = [int(x) for x in a.ids.split(",") if x.strip()]
        except ValueError:
            print(f"REFUSED: --ids {a.ids!r} is not a list of row ids; nothing written")
            return 2
        if not ids or len(set(ids)) != len(ids):
            print(f"REFUSED: --ids {a.ids!r} names no id, or one twice; nothing written")
            return 2
    try:
        return run(a.db, a.frm, ids, a.apply, from_json=a.from_json, book_rows=a.book_rows,
                   move_added=a.move_added, emit_json=a.emit_json)
    except Refused as e:
        print(f"REFUSED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
