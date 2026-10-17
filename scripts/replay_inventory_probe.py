"""
THE REPLAY INVENTORY (ARCHITECT 2026-10-15, addendum 79 item 3; for the K-track replay spec Tuesday 2026-10-20, #75),
READ-ONLY:

"Before I write the spec, what the DB can replay faithfully: `scripts/replay_inventory_probe.py` prints, per sport, for
the graded games since 2026-09-20: how many have a stored prediction row with computed_at before kickoff (and how many
versions per game, if prediction rows are kept per run or overwritten — read the schema and say which); how many have
book snapshots before kickoff (count per game, first and last capture age vs kickoff); how many have Kalshi snapshots
before kickoff (same); how many have a closing file on the laptop (exports/closing_*.json, matched by match id); how
many have all four. Keys used printed. The spec is built on what this prints, not on what I remember."

WHAT THE SCHEMA SAYS (read at main c51324d):
- predictions is CURRENT-ONLY per match: every writer deletes the match's rows (whatever the model_version) and inserts
  one, so a run OVERWRITES the last (soccer and MLB: src/walters/training.py _generate_predictions_*; NFL:
  src/walters/nfl_predict.py predict_nfl). predictions.match_id is not unique in the DB; one row is a writer convention.
- prediction_history is APPEND-ONLY: a Session after_flush hook copies every new Prediction (match_id, model_version,
  computed_at, the three probabilities; nothing else) (src/db/database.py). It came with #301 (merged 2026-10-06) with
  no backfill: before it, a game has at most its one current row. The versions per game are its rows before kickoff.
- Soccer and MLB re-predict every SCHEDULED fixture with no kickoff guard, so a current row can be computed after
  kickoff: counted on its own line. The writers of predictions rows are those three (src/walters/training.py takes any
  soccer competition code, cups included); the NHL and NCAA shadows write files only. One writer appends history with
  NO predictions row: the production INTL export (export-intl-predictions, src/walters/intl_production.py, refused
  until registry.production_allowed("intl-elo-v2")) appends one prediction_history row per exported UNL fixture
  (Codex on #547). No sport's count is assumed: every group is read from the tables.
- Book history lives in TWO tables. odds_snapshots: one de-vigged consensus session per sync (soccer, cups and NHL
  since #167, merged 2026-10-01; NFL/NCAA since 2026-09-29; MLB since 2026-10-02, capture-run copies before it). The
  odds table: since #167 each sync REPLACES a source's rows, so it holds the last session; before #167 the soccer,
  cup and NHL syncs APPENDED a full book set every run, and nothing deletes a finished game's rows, so for those games
  it is the only book history. The probe reads both (book rows: market "1X2", a source other than "kalshi", a NULL
  source counted as book as the Python readers count it; the football-data-uk historical closes are left out, their
  stamp being the insert time, not the price's) and prints each table's share.
- Kalshi history: odds_snapshots rows with source "kalshi" (market "ML" two-way, "1X2" soccer). A game whose current
  legs are MISMATCHED (their tickers name two events, or their event's legs sit on another game: addendum 37 item 3,
  src/walters/kalshi_legs.py) is read by no reader; it is counted apart and never as Kalshi history.
  kalshi_settled_markets (one row per market, from candles) is printed apart.
- A capture session, and when it is COMPLETE, is read the way the close reads each table (src/walters/close.py: an
  incomplete session is never a price); games with a complete session are printed apart. The outcome set is HOME and
  AWAY (soccer HOME, DRAW and AWAY).
  odds_snapshots (close_from_snapshots): a session is one captured_at; complete when it carries every outcome (the
  de-vigged legs summing above 0, as the close checks).
  The odds table (close_1x2, the #207 contract): a session is the last captured_at t before a cutoff and every row
  within CAPTURE_SESSION (10 minutes) before it, the latest row per (bookmaker, selection, line); complete when ONE
  bookmaker quoted every outcome at a price above 1.0. Books are never pooled (Codex on #547): three books quoting one
  leg each are no price. Sessions are counted as successive cutoffs see them, newest first; complete = some cutoff
  before kickoff gives a priced close. The two tables' sessions are printed apart, never added (one sync writes both).
  Kalshi: a session is one captured_at, complete when every leg is stored. That is a count of stored legs, not the
  Kalshi grading close (close_from_kalshi reads one two-sided HOME quote inside the Desk's 2c spread cap).
- Closing files: <exports>/closing_<FAMILY>_<start>.json, match ids in closing.match_ids (else predictions[].match_id).
  Files under <exports>/host/ come from the host, whose match ids are its own: counted, never matched.
- VOID: RE-DATED (ARCHITECT 2026-10-17, addendum 107 item A2): "Grading, the results exports and the replay inventory
  label a closing row whose recorded start differs from the match's current utc_date by more than DESK_CLOCK_DRIFT as
  "void: re-dated <old start> → <new start>" and exclude it from every tally; the fresh closing on the new date is the
  graded row." A game's closing is void, listed with the label and left out of closing and all four, when none of its
  closing rows' recorded starts (their utc_date) is within the rule of the kickoff and its latest closing row is
  re-dated by the rule (src/walters/redated.py void_label). A latest row whose start cannot be compared is not void.

THE KEYS (printed): a graded game = matches.status FINISHED with home_score and away_score, kickoff (matches.utc_date)
in [--since, --until). Before kickoff = julianday(the stamp) < julianday(matches.utc_date) (the stamp as stored, any
SQLite time format). Sport: the matches.sport name; NCAA = sport NFL with competition code NCAA; soccer is split by
competition code. "All four" = a stored prediction before kickoff (current row or history) + book history + Kalshi
history (not mismatched) before kickoff + a closing file.

Opens the database mode=ro (a copy that refuses it: the plain path with PRAGMA query_only = ON, #421) and never
creates one. Writes nothing.

    python3 scripts/replay_inventory_probe.py [--db PATH] [--since 2026-09-20] [--until YYYY-MM-DD] [--exports exports]
"""
from __future__ import annotations

import argparse
import json
from bisect import bisect_left, bisect_right
import os
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.walters.close import CAPTURE_SESSION  # noqa: E402  (the close's own session window, read, never restated)
from src.walters.redated import closing_starts, void_label  # noqa: E402  (addendum 107 item A2: the one rule)

SINCE = "2026-09-20"
CHUNK = 500
TWO_WAY, THREE_WAY = frozenset({"HOME", "AWAY"}), frozenset({"HOME", "DRAW", "AWAY"})
SESSION_MS = int(CAPTURE_SESSION.total_seconds() * 1000)
SNAP_SESSION = "a session = one captured_at"
ODDS_SESSION = "a session = the close's 10-minute window; complete = one book quoting every outcome"
KEYS = ("graded = matches.status FINISHED with home_score and away_score, kickoff matches.utc_date in [since, until) "
        "· sport = matches.sport; NCAA = sport NFL with competition code NCAA; soccer split by competition code "
        "· before kickoff = julianday(stamp) < julianday(matches.utc_date) · prediction = predictions.computed_at "
        "(current row) or prediction_history.computed_at · book = odds_snapshots and the odds table, market 1X2, "
        "source not kalshi (NULL counts; football-data-uk closes left out) · kalshi = odds_snapshots source kalshi, "
        "a game with mismatched legs (addendum 37 item 3) never counted · outcomes = HOME+AWAY (soccer +DRAW) · "
        "odds_snapshots session = one captured_at, complete = every outcome (close_from_snapshots) · "
        "odds table session = a captured_at t and the rows 10 minutes before it, latest per (bookmaker, selection, line), "
        "complete = ONE bookmaker quoting every outcome above 1.0, books never pooled (close_1x2) · kalshi session = one "
        "captured_at, complete = every leg stored (not the Kalshi grading close) · closing file = "
        "<exports>/closing_*.json closing.match_ids (else predictions[].match_id); a game with no closing row's "
        "utc_date within DESK_CLOCK_DRIFT of its kickoff and its latest re-dated is void: re-dated, never a closing "
        "(addendum 107 item A2)")


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
            url = os.getenv("DATABASE_URL")
        except ImportError:
            pass
    url = url or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the probe is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    """(connection, form): mode=ro first; a copy that refuses it, the plain path with query_only set (#421). Never
    creates a database."""
    if not p.is_file():
        raise SystemExit(f"no database at {p}: the probe never creates one")
    con = None
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        if con is not None:
            con.close()
        # #421 RULED (ARCHITECT 2026-10-11, addendum 38): "A receipt opens the database mode=ro. Where a copy refuses
        # that, it opens the plain path with query_only set and prints which form it used [...] It opens the
        # database no third way." (#421 put the -wal/-shm question, immutable or refusing, to the architect.)
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def has_table(con, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def graded_games(con, since: str, until: str) -> list[dict]:
    q = ("SELECT m.id, m.sport, c.code, m.utc_date, julianday(m.utc_date) FROM matches m "
         "JOIN competitions c ON c.id = m.competition_id "
         "WHERE m.status = 'FINISHED' AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL "
         "AND julianday(m.utc_date) >= julianday(?) AND julianday(m.utc_date) < julianday(?) ORDER BY m.utc_date, m.id")
    return [{"id": i, "sport": sport, "code": code, "kickoff": ko, "ko": jd}
            for i, sport, code, ko, jd in con.execute(q, (since, until)) if jd is not None]


def group_of(g: dict) -> str:
    sport = str(g["sport"] or "?").upper()
    if sport == "NFL" and g["code"] == "NCAA":
        return "NCAA"
    if sport == "SOCCER":
        return f"SOCCER {g['code']}"
    return sport


def by_match(con, sql: str, ids: list[int], extra: tuple = ()) -> dict[int, list]:
    """{match_id: [the row's other columns, ...]} over `ids`, in chunks (one query per chunk)."""
    out: dict[int, list] = {}
    for i in range(0, len(ids), CHUNK):
        part = ids[i:i + CHUNK]
        marks = ",".join("?" * len(part))
        for row in con.execute(sql.format(ids=marks), (*part, *extra)):
            out.setdefault(row[0], []).append(row[1:])
    return out


def closing_ids(exports: Path) -> dict:
    """The laptop's closing files: every match id they name; the host copies are counted only."""
    files = sorted(exports.glob("closing_*.json")) if exports.is_dir() else []
    ids, bad = set(), []
    for f in files:
        try:
            d = json.loads(f.read_text())
            cl = d.get("closing") or {}
            got = cl.get("match_ids") if isinstance(cl.get("match_ids"), list) else [
                r.get("match_id") for r in d.get("predictions") or [] if isinstance(r, dict)]
            ids.update(i for i in got if isinstance(i, int))
        except (OSError, ValueError, AttributeError):
            bad.append(f.name)
    host = sorted((exports / "host").glob("closing_*.json")) if (exports / "host").is_dir() else []
    return {"files": len(files), "ids": ids, "unreadable": bad, "host_files": len(host)}


def spread(xs: list[float], fmt="{:.1f}") -> str:
    if not xs:
        return "-"
    return "/".join(fmt.format(v) for v in (min(xs), statistics.median(xs), max(xs)))


def ms_of(jd: float) -> int:
    """A julian day as integer milliseconds (SQLite keeps a stamp to the millisecond): window edges compare exactly."""
    return round(jd * 86_400_000)


def stamp_sessions(rows: list, need) -> tuple[int, bool]:
    """odds_snapshots and Kalshi (close_from_snapshots): a session is one captured_at; it is COMPLETE when every outcome
    in `need` has a value (r[2]: devig_prob; Kalshi: 1, the stored leg) and the values sum above 0, as the close
    checks. rows: (julian day, selection, value), all before kickoff. -> (sessions, complete)."""
    sess: dict = {}
    for jd, sel, val in rows:
        legs = sess.setdefault(jd, {})
        if val is not None:
            legs[sel] = val
    return len(sess), any(all(k in legs for k in need) and sum(legs[k] for k in need) > 0 for legs in sess.values())


def window_sessions(rows: list, need) -> tuple[int, bool]:
    """The odds table as close_1x2 reads it (src/walters/close.py, the #207 contract): at a cutoff, the session is the
    last captured_at t before it and every row from t - CAPTURE_SESSION to t, the latest row per (bookmaker,
    selection, line) (on equal stamps the first read, as last_capture keeps it). It is COMPLETE when ONE bookmaker
    quoted every outcome in `need` at a price above 1.0; books are never pooled (Codex on #547). Sessions are counted
    as successive cutoffs see them: the newest t, then the newest stamp older than t - CAPTURE_SESSION, and so on.
    Complete = some cutoff before kickoff gives a priced close (every stamp is tried as t, newest first). rows: (julian
    day, selection, bookmaker, price, line) in id order, all before kickoff. -> (sessions, complete)."""
    pts = sorted(((ms_of(r[0]), n, r) for n, r in enumerate(rows)), key=lambda x: (x[0], x[1]))
    keys = [x[0] for x in pts]
    stamps = sorted(set(keys), reverse=True)
    sessions, edge = 0, None
    for t in stamps:
        if edge is None or t < edge:
            sessions, edge = sessions + 1, t - SESSION_MS
    for t in stamps:
        latest: dict = {}
        for ms, _, (_, sel, bk, px, line) in pts[bisect_left(keys, t - SESSION_MS):bisect_right(keys, t)]:
            k = (bk, sel, line)
            if k not in latest or ms > latest[k][0]:
                latest[k] = (ms, px)
        books: dict = {}
        for (bk, sel, _), (_, px) in latest.items():
            if sel in need and px is not None and px > 1.0:
                books.setdefault(bk, set()).add(sel)
        if any(need <= sels for sels in books.values()):
            return sessions, True
    return sessions, False


def summary(per_game: dict) -> dict:
    """{games, ids, complete, sessions per game, first and last capture age (hours), earliest} over per-game
    {first, last, sessions, complete, ko} (julian days). sessions None = not counted for that reading."""
    v = list(per_game.values())
    return {"games": len(v), "ids": set(per_game), "complete": sum(1 for x in v if x["complete"]),
            "complete_ids": {i for i, x in per_game.items() if x["complete"]},
            "sessions": [x["sessions"] for x in v if x["sessions"] is not None],
            "first_h": [(x["ko"] - x["first"]) * 24 for x in v], "last_h": [(x["ko"] - x["last"]) * 24 for x in v],
            "earliest": min((x["first"] for x in v), default=None), "per_game": per_game}


def captures(rows: dict[int, list], games: list[dict], need, sessions) -> dict:
    """Over the games with a capture before kickoff (r[0]: its julian day): sessions per game and whether one is
    COMPLETE (`sessions(the game's rows before kickoff, need(game))` -> (count, complete)), first and last capture age."""
    per_game = {}
    for g in games:
        pre = [r for r in rows.get(g["id"], []) if r[0] is not None and r[0] < g["ko"]]
        if not pre:
            continue
        n, ok = sessions(pre, need(g))
        per_game[g["id"]] = {"first": min(r[0] for r in pre), "last": max(r[0] for r in pre), "sessions": n,
                             "complete": ok, "ko": g["ko"]}
    return summary(per_game)


def union(a: dict, b: dict) -> dict:
    """Book history over both tables, per game: the first and last capture over both, complete in either. Sessions are
    not added across the tables (one sync writes both), so they are read per table."""
    per = {}
    for i in a["ids"] | b["ids"]:
        xs = [c["per_game"][i] for c in (a, b) if i in c["per_game"]]
        per[i] = {"first": min(x["first"] for x in xs), "last": max(x["last"] for x in xs), "sessions": None,
                  "complete": any(x["complete"] for x in xs), "ko": xs[0]["ko"]}
    return summary(per)


def jd_text(jd) -> str:
    """A julian day as UTC text (julianday 2440587.5 = 1970-01-01T00:00Z), to the nearest minute."""
    if jd is None:
        return "-"
    dt = datetime(1970, 1, 1) + timedelta(days=jd - 2440587.5) + timedelta(seconds=30)
    return dt.strftime("%Y-%m-%d %H:%M")


def need_of(g: dict):
    return THREE_WAY if str(g["sport"] or "").upper() == "SOCCER" else TWO_WAY


def inventory(con, since: str, until: str, exports: Path) -> dict:
    from src.walters import kalshi_legs
    games = graded_games(con, since, until)
    ids = [g["id"] for g in games]
    hist_ok, ksm_ok = has_table(con, "prediction_history"), has_table(con, "kalshi_settled_markets")
    pred = by_match(con, "SELECT match_id, julianday(computed_at) FROM predictions WHERE match_id IN ({ids})", ids)
    hist = by_match(con, "SELECT match_id, julianday(computed_at) FROM prediction_history WHERE match_id IN ({ids})",
                    ids) if hist_ok else {}
    outc = by_match(con, "SELECT p.match_id, o.id FROM prediction_outcomes o JOIN predictions p ON p.id = o.prediction_id "
                         "WHERE p.match_id IN ({ids})", ids)
    snap = by_match(con, "SELECT match_id, julianday(captured_at), selection, devig_prob FROM odds_snapshots WHERE "
                         "match_id IN ({ids}) AND market = '1X2' AND (source IS NULL OR source != 'kalshi')", ids)
    board = by_match(con, "SELECT match_id, julianday(captured_at), selection, bookmaker, price_decimal, line FROM odds "
                          "WHERE match_id IN ({ids}) AND market = '1X2' AND (source IS NULL OR (source != 'kalshi' "
                          "AND source NOT LIKE 'football-data-uk:%')) ORDER BY id", ids)
    kal = by_match(con, "SELECT match_id, julianday(captured_at), selection, 1 FROM odds_snapshots WHERE match_id IN "
                        "({ids}) AND source = 'kalshi'", ids)
    mism = kalshi_legs.mismatched(con, ids)
    kal_read = {i: rows for i, rows in kal.items() if i not in mism}
    ksm = by_match(con, "SELECT match_id, ticker FROM kalshi_settled_markets WHERE match_id IN ({ids})",
                   ids) if ksm_ok else {}
    cf = closing_ids(exports)
    starts = closing_starts(exports)["rows"]
    first_hist = (con.execute("SELECT MIN(julianday(computed_at)), COUNT(*) FROM prediction_history").fetchone()
                  if hist_ok else None)
    groups: dict[str, list] = {}
    for g in games:
        groups.setdefault(group_of(g), []).append(g)
    out = {}
    for name in sorted(groups):
        gs = groups[name]
        cur = {g["id"] for g in gs if any(r[0] is not None and r[0] < g["ko"] for r in pred.get(g["id"], []))}
        late = {g["id"] for g in gs if pred.get(g["id"]) and g["id"] not in cur}
        versions = {g["id"]: sum(1 for r in hist.get(g["id"], []) if r[0] is not None and r[0] < g["ko"]) for g in gs}
        hv = {i for i, n in versions.items() if n}
        either = cur | hv
        bs, bo = captures(snap, gs, need_of, stamp_sessions), captures(board, gs, need_of, window_sessions)
        b, k = union(bs, bo), captures(kal_read, gs, need_of, stamp_sessions)
        cl = {g["id"] for g in gs} & cf["ids"]
        # addendum 107 item A2: a closing whose every row is re-dated is void, out of closing and all four
        redated = sorted((g["id"], lab) for g in gs if g["id"] in cl
                         and (lab := void_label(starts.get(g["id"]), g["kickoff"])))
        cl -= {i for i, _ in redated}
        four = either & b["ids"] & k["ids"] & cl
        out[name] = {"graded": len(gs), "pred_current": len(cur), "pred_history": len(hv), "pred_either": len(either),
                     "pred_current_after_ko": len(late), "versions": [versions[i] for i in sorted(hv)],
                     "outcome_games": sum(1 for g in gs if outc.get(g["id"])), "book": b,
                     "book_snapshots": bs, "book_odds_table": bo,
                     "book_odds_table_only": len(bo["ids"] - bs["ids"]),
                     "book_complete_odds_table_only": len(bo["complete_ids"] - bs["complete_ids"]), "kalshi": k,
                     "kalshi_mismatched": sum(1 for g in gs if g["id"] in mism),
                     "settled_markets": sum(1 for g in gs if ksm.get(g["id"])), "closing": len(cl),
                     "all_four": len(four), "closing_redated": len(redated), "redated": redated}
    return {"games": len(games), "groups": out, "closing": cf, "history_table": hist_ok, "settled_table": ksm_ok,
            "first_history": first_hist, "tickers": kalshi_legs.has_tickers(con)}


def _cap(label: str, c: dict, sessions: str | None = None) -> str:
    if not c["games"]:
        return f"  {label}: 0 games"
    ses = sessions or f"sessions per game {spread(c['sessions'], '{:g}')}"
    return (f"  {label}: {c['games']} games ({c['complete']} with a complete session) · {ses} · first capture "
            f"{spread(c['first_h'])}h before kickoff · last capture {spread(c['last_h'])}h before kickoff "
            f"(min/median/max) · earliest {jd_text(c['earliest'])} UTC")


def _table(c: dict, session: str) -> str:
    return (f"{c['games']} games ({c['complete']} complete), sessions per game {spread(c['sessions'], '{:g}')} "
            f"({session})" if c["games"] else "0 games")


def report(inv: dict, form: str, since: str, until: str, exports: Path, echo=print) -> None:
    echo(f"REPLAY INVENTORY PROBE (ARCHITECT 2026-10-15, addendum 79 item 3; #75): read-only · {form} · graded games "
         f"with kickoff in [{since}, {until}) UTC: {inv['games']}")
    echo(f"keys: {KEYS}")
    fh = inv["first_history"]
    echo("schema: predictions is CURRENT-ONLY per match (every writer deletes the match's rows and inserts one: a run "
         "OVERWRITES) · prediction_history is APPEND-ONLY, one row per run per match, since #301 (2026-10-06, no "
         "backfill) · " + (f"prediction_history here: {fh[1]} rows, first computed_at {jd_text(fh[0])} UTC"
                           if inv["history_table"] else "prediction_history: NO such table in this database")
         + " · book history: odds_snapshots, and the odds table (the last session per source since #167, 2026-10-01; "
           "before it, soccer/cup/NHL syncs appended every run there)"
         + ("" if inv["tickers"] else " · odds_snapshots.market_ticker: NOT in this database, so no Kalshi leg can be "
                                      "judged mismatched"))
    cf = inv["closing"]
    echo(f"closing files: {exports}/closing_*.json {cf['files']} files, {len(cf['ids'])} match ids"
         + (f", unreadable {len(cf['unreadable'])} ({', '.join(cf['unreadable'])})" if cf["unreadable"] else "")
         + f" · {exports}/host/closing_*.json {cf['host_files']} files, not matched (the host's match ids are its own)")
    for name, g in inv["groups"].items():
        echo(f"{name}: graded {g['graded']}")
        echo(f"  stored prediction before kickoff: current row {g['pred_current']} · history {g['pred_history']} · "
             f"either {g['pred_either']} · current row computed at/after kickoff {g['pred_current_after_ko']} · "
             f"versions per game (history rows before kickoff) {spread(g['versions'], '{:g}')} (min/median/max over "
             f"{len(g['versions'])} games) · games with a prediction_outcomes row {g['outcome_games']}")
        echo(_cap("book history before kickoff", g["book"], "sessions per table below"))
        echo(f"    of it: odds_snapshots {_table(g['book_snapshots'], SNAP_SESSION)} · the odds table "
             f"{_table(g['book_odds_table'], ODDS_SESSION)} · in the odds table only: {g['book_odds_table_only']} "
             f"games, complete only there {g['book_complete_odds_table_only']}")
        echo(_cap("kalshi snapshots before kickoff", g["kalshi"])
             + f" · mismatched legs, never read (addendum 37 item 3): {g['kalshi_mismatched']} games")
        echo(f"  kalshi_settled_markets rows: "
             + (f"{g['settled_markets']} games" if inv["settled_table"] else "NO such table in this database"))
        echo(f"  closing file ({exports}/, by match id): {g['closing']} games")
        echo(f"  all four (a stored prediction + book history + kalshi history + a closing file): {g['all_four']}")
        echo(f"  closing void: re-dated (left out of closing and all four): {g['closing_redated']} games")
        for i, lab in g["redated"]:
            echo(f"    match {i}: {lab}")
    js = {name: {k: (v if not isinstance(v, dict) else {"games": v["games"], "complete": v["complete"],
                                                         "earliest": jd_text(v["earliest"])})
                 for k, v in g.items() if k not in ("versions", "redated")} for name, g in inv["groups"].items()}
    echo("REPLAY-INVENTORY " + json.dumps({"since": since, "until": until, "games": inv["games"], "groups": js,
                                           "closing_files": cf["files"], "host_closing_files": cf["host_files"],
                                           "closing_redated": sum(g["closing_redated"]
                                                                  for g in inv["groups"].values())},
                                          sort_keys=True))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 79 item 3: what the DB can replay, per sport")
    ap.add_argument("--db", default=None)
    ap.add_argument("--since", default=SINCE, help="first kickoff day, UTC (default 2026-09-20)")
    ap.add_argument("--until", default=None, help="kickoffs before this day, UTC (default: now)")
    ap.add_argument("--exports", default="exports", help="the laptop's exports folder (closing_*.json)")
    a = ap.parse_args(argv)
    until = a.until or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    con, form = open_read(db_path(a.db))
    try:
        report(inventory(con, a.since, until, Path(a.exports)), form, a.since, until, Path(a.exports))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
