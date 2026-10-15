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
  kickoff: counted on its own line. NHL, NCAA, UNL, cups and the expansion leagues write no prediction rows (shadow
  files or market-only): 0 by construction.
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
- A capture session is one captured_at: sessions per game = distinct captured_at before kickoff. A session is
  COMPLETE when it carries every outcome (HOME and AWAY; soccer HOME, DRAW and AWAY), the close's own rule
  (src/walters/close.py: an incomplete session is never a price); games with a complete session are printed apart.
- Closing files: <exports>/closing_<FAMILY>_<start>.json, match ids in closing.match_ids (else predictions[].match_id).
  Files under <exports>/host/ come from the host, whose match ids are its own: counted, never matched.

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
import os
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SINCE = "2026-09-20"
CHUNK = 500
TWO_WAY, THREE_WAY = frozenset({"HOME", "AWAY"}), frozenset({"HOME", "DRAW", "AWAY"})
KEYS = ("graded = matches.status FINISHED with home_score and away_score, kickoff matches.utc_date in [since, until) "
        "· sport = matches.sport; NCAA = sport NFL with competition code NCAA; soccer split by competition code "
        "· before kickoff = julianday(stamp) < julianday(matches.utc_date) · prediction = predictions.computed_at "
        "(current row) or prediction_history.computed_at · book = odds_snapshots and the odds table, market 1X2, "
        "source not kalshi (NULL counts; football-data-uk closes left out) · kalshi = odds_snapshots source kalshi, "
        "a game with mismatched legs (addendum 37 item 3) never counted · session = a distinct captured_at; complete = "
        "every outcome (HOME+AWAY; soccer +DRAW) · closing file = <exports>/closing_*.json closing.match_ids (else "
        "predictions[].match_id)")


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


def captures(rows: dict[int, list], games: list[dict], need) -> dict:
    """Over the games with a capture before kickoff: sessions per game (a session = one captured_at, its rows' julian
    day in r[0], its selection in r[1]), first and last capture age (hours), and the games with a COMPLETE session
    (every outcome `need(game)` names)."""
    per, first, last, earliest = [], [], [], None
    have, complete = set(), set()
    for g in games:
        sess: dict = {}
        for r in rows.get(g["id"], []):
            if r[0] is not None and r[0] < g["ko"]:
                sess.setdefault(r[0], set()).add(r[1])
        if not sess:
            continue
        stamps = sorted(sess)
        have.add(g["id"])
        if any(need(g) <= sels for sels in sess.values()):
            complete.add(g["id"])
        per.append(len(stamps))
        first.append((g["ko"] - stamps[0]) * 24)
        last.append((g["ko"] - stamps[-1]) * 24)
        earliest = stamps[0] if earliest is None else min(earliest, stamps[0])
    return {"games": len(have), "ids": have, "complete": len(complete), "sessions": per, "first_h": first,
            "last_h": last, "earliest": earliest}


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
    snap = by_match(con, "SELECT match_id, julianday(captured_at), selection FROM odds_snapshots WHERE match_id IN "
                         "({ids}) AND market = '1X2' AND (source IS NULL OR source != 'kalshi')", ids)
    board = by_match(con, "SELECT match_id, julianday(captured_at), selection FROM odds WHERE match_id IN ({ids}) "
                          "AND market = '1X2' AND (source IS NULL OR (source != 'kalshi' AND source NOT LIKE "
                          "'football-data-uk:%'))", ids)
    book = {i: snap.get(i, []) + board.get(i, []) for i in set(snap) | set(board)}
    kal = by_match(con, "SELECT match_id, julianday(captured_at), selection FROM odds_snapshots WHERE match_id IN "
                        "({ids}) AND source = 'kalshi'", ids)
    mism = kalshi_legs.mismatched(con, ids)
    kal_read = {i: rows for i, rows in kal.items() if i not in mism}
    ksm = by_match(con, "SELECT match_id, ticker FROM kalshi_settled_markets WHERE match_id IN ({ids})",
                   ids) if ksm_ok else {}
    cf = closing_ids(exports)
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
        b, k = captures(book, gs, need_of), captures(kal_read, gs, need_of)
        bs, bo = captures(snap, gs, need_of), captures(board, gs, need_of)
        cl = {g["id"] for g in gs} & cf["ids"]
        four = either & b["ids"] & k["ids"] & cl
        out[name] = {"graded": len(gs), "pred_current": len(cur), "pred_history": len(hv), "pred_either": len(either),
                     "pred_current_after_ko": len(late), "versions": [versions[i] for i in sorted(hv)],
                     "outcome_games": sum(1 for g in gs if outc.get(g["id"])), "book": b,
                     "book_snapshots": bs["games"], "book_odds_table": bo["games"],
                     "book_odds_table_only": len(bo["ids"] - bs["ids"]), "kalshi": k,
                     "kalshi_mismatched": sum(1 for g in gs if g["id"] in mism),
                     "settled_markets": sum(1 for g in gs if ksm.get(g["id"])), "closing": len(cl),
                     "all_four": len(four)}
    return {"games": len(games), "groups": out, "closing": cf, "history_table": hist_ok, "settled_table": ksm_ok,
            "first_history": first_hist, "tickers": kalshi_legs.has_tickers(con)}


def _cap(label: str, c: dict) -> str:
    if not c["games"]:
        return f"  {label}: 0 games"
    return (f"  {label}: {c['games']} games ({c['complete']} with a complete session) · sessions per game "
            f"{spread(c['sessions'], '{:g}')} · first capture {spread(c['first_h'])}h before kickoff · last capture "
            f"{spread(c['last_h'])}h before kickoff (min/median/max) · earliest {jd_text(c['earliest'])} UTC")


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
        echo(_cap("book history before kickoff", g["book"]))
        echo(f"    of it: odds_snapshots {g['book_snapshots']} games · the odds table {g['book_odds_table']} games "
             f"({g['book_odds_table_only']} in the odds table only)")
        echo(_cap("kalshi snapshots before kickoff", g["kalshi"])
             + f" · mismatched legs, never read (addendum 37 item 3): {g['kalshi_mismatched']} games")
        echo(f"  kalshi_settled_markets rows: "
             + (f"{g['settled_markets']} games" if inv["settled_table"] else "NO such table in this database"))
        echo(f"  closing file ({exports}/, by match id): {g['closing']} games")
        echo(f"  all four (a stored prediction + book history + kalshi history + a closing file): {g['all_four']}")
    js = {name: {k: (v if not isinstance(v, dict) else {"games": v["games"], "complete": v["complete"],
                                                         "earliest": jd_text(v["earliest"])})
                 for k, v in g.items() if k != "versions"} for name, g in inv["groups"].items()}
    echo("REPLAY-INVENTORY " + json.dumps({"since": since, "until": until, "games": inv["games"], "groups": js,
                                           "closing_files": cf["files"], "host_closing_files": cf["host_files"]},
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
