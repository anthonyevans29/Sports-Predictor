"""
KALSHI LEG AUDIT (ARCHITECT 2026-10-10, addendum 37 item 4), READ-ONLY: "Over the stored Kalshi snapshots that carry a
ticker, by series and by day: the games whose legs come from two events and the events whose legs sit on two games,
each with match id, teams, kickoff, tickers and capture times. Then the totals, the first day each series shows one,
and, of the games listed, those with a graded prediction. Captures from before the ticker column cannot be checked:
the receipt says how many those are. The operator runs it on both machines, and both consoles go on the Issue."
(#413; #308's final receipt waits for it.)

A day is the capture's UTC date. Within one series and day, over the Kalshi snapshots that carry a ticker:
  TWO-EVENT GAME   a game whose legs captured that day name more than one event;
  SPLIT EVENT      an event whose legs captured that day sit on more than one game.
An event is a market ticker without its last '-' segment (the rule of src/walters/kalshi_legs.event_of, #414).
The series is the ticker's first segment. Captures with no ticker (before migrate_kalshi_ticker.py, or a leg the
matcher stored without one) are counted, never checked.

Opens the DB read-only (mode=ro URI; a copy that refuses mode=ro falls back to the plain path with PRAGMA query_only = ON, #421).
Writes nothing.

    python3 scripts/kalshi_leg_audit.py [--since YYYY-MM-DD] [--db PATH]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def event_of(ticker):
    if not ticker or "-" not in str(ticker):
        return None
    return str(ticker).rsplit("-", 1)[0]


def series_of(ticker):
    return str(ticker).split("-", 1)[0] if ticker else None


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
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the audit is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    if not p.exists():
        raise SystemExit(f"no database at {p}")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM odds_snapshots LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        # #421 RULED (ARCHITECT 2026-10-11, addendum 38): "A receipt opens the database mode=ro. Where a copy refuses
        # that, it opens the plain path with query_only set and prints which form it used [...] It opens the
        # database no third way."
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM odds_snapshots LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def has_ticker_column(con) -> bool:
    return any(r[1] == "market_ticker" for r in con.execute("PRAGMA table_info(odds_snapshots)"))


def audit(con, since: str | None = None) -> dict:
    """Pure over the connection: every finding, the totals and the untickered count."""
    where, params = "s.source = 'kalshi'", []
    if since:
        where += " AND s.captured_at >= ?"
        params.append(since)
    total = con.execute(f"SELECT COUNT(*) FROM odds_snapshots s WHERE {where}", params).fetchone()[0]
    # #419 (Codex on #416): every count straight from odds_snapshots; a snapshot whose match row is gone is an
    # orphan, counted on its own line (never silently read as tickered)
    orphans = con.execute(f"SELECT COUNT(*) FROM odds_snapshots s LEFT JOIN matches m ON m.id = s.match_id "
                          f"WHERE {where} AND m.id IS NULL", params).fetchone()[0]
    if not has_ticker_column(con):
        return {"ticker_column": False, "kalshi_snapshots": total, "untickered": total, "tickered": 0,
                "orphans": orphans, "two_event_games": [], "split_events": [], "first_day": {}, "graded": [],
                "graded_error": None, "by_series_day": {}}
    untickered = con.execute(f"SELECT COUNT(*) FROM odds_snapshots s WHERE {where} AND "
                             "(s.market_ticker IS NULL OR s.market_ticker = '')", params).fetchone()[0]
    rows = con.execute(
        "SELECT s.id, s.match_id, s.selection, s.market_ticker, s.captured_at, m.utc_date, "
        "COALESCE(h.name, '?'), COALESCE(a.name, '?') "
        "FROM odds_snapshots s JOIN matches m ON m.id = s.match_id "
        "LEFT JOIN teams h ON h.id = m.home_team_id LEFT JOIN teams a ON a.id = m.away_team_id "
        f"WHERE {where} ORDER BY s.captured_at, s.id", params).fetchall()
    games = {}
    # (series, day) -> match -> event -> [(selection, ticker, captured_at)]
    by_game: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    # (series, day) -> event -> match -> [(selection, ticker, captured_at)]
    by_event: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for sid, mid, sel, tic, cap, ko, home, away in rows:
        if not tic:
            continue
        ev, ser, day = event_of(tic), series_of(tic), str(cap)[:10]
        if not ev:
            continue
        games[mid] = {"match_id": mid, "home": home, "away": away, "kickoff": ko}
        leg = (sel, tic, str(cap))
        by_game[(ser, day)][mid][ev].append(leg)
        by_event[(ser, day)][ev][mid].append(leg)
    two_event, split, first_day, by_sd = [], [], {}, {}
    for key in sorted(set(by_game) | set(by_event)):
        ser, day = key
        n2 = ns = 0
        for mid, evs in sorted(by_game[key].items()):
            if len(evs) > 1:
                n2 += 1
                two_event.append({"series": ser, "day": day, **games[mid],
                                  "legs": {ev: legs for ev, legs in sorted(evs.items())}})
        for ev, mids in sorted(by_event[key].items()):
            if len(mids) > 1:
                ns += 1
                split.append({"series": ser, "day": day, "event": ev,
                              "games": [{**games[m], "legs": legs} for m, legs in sorted(mids.items())]})
        if n2 or ns:
            first_day.setdefault(ser, day)
            by_sd[f"{ser} {day}"] = {"two_event_games": n2, "split_events": ns}
    listed = sorted({g["match_id"] for g in two_event} | {g["match_id"] for e in split for g in e["games"]})
    graded, graded_error = [], None
    # #419 (Codex on #416): an error on the graded query is NOT CHECKED, never a quiet zero; chunked IN lists
    try:
        found: set = set()
        for k in range(0, len(listed), 500):
            chunk = listed[k:k + 500]
            q = ("SELECT DISTINCT p.match_id FROM predictions p JOIN prediction_outcomes o ON o.prediction_id = p.id "
                 f"WHERE p.match_id IN ({','.join('?' * len(chunk))})")
            found |= {r[0] for r in con.execute(q, chunk)}
        graded = sorted(found)
    except sqlite3.OperationalError as e:
        graded_error = f"{type(e).__name__}: {e}"
    return {"ticker_column": True, "kalshi_snapshots": total, "untickered": untickered,
            "tickered": total - untickered, "orphans": orphans, "two_event_games": two_event, "split_events": split,
            "first_day": first_day, "graded": [games[m] for m in graded], "graded_error": graded_error,
            "by_series_day": by_sd}


def _game(g) -> str:
    return f"{g['match_id']} {g['away']} @ {g['home']} {g['kickoff']}"


def report(r: dict, echo=print) -> None:
    echo(f"Kalshi snapshots: {r['kalshi_snapshots']} · with a ticker: {r['tickered']} · "
         f"WITHOUT a ticker (cannot be checked): {r['untickered']}")
    echo(f"of them with no match row (orphans; their legs are not placed on any game): {r.get('orphans', 0)}")
    if not r["ticker_column"]:
        echo("odds_snapshots.market_ticker does not exist (migrate_kalshi_ticker.py not run): nothing can be checked")
        echo(f"\nKALSHI-LEG-AUDIT two_event_games=0 split_events=0 graded=0 untickered={r['untickered']} tickered=0 "
             "ticker_column=absent")      # the summary line in both database shapes (Codex on #416)
        return
    echo(f"\nGAMES WHOSE LEGS COME FROM TWO EVENTS: {len(r['two_event_games'])}")
    for g in r["two_event_games"]:
        echo(f"  {g['series']} {g['day']}  {_game(g)}")
        for ev, legs in g["legs"].items():
            echo(f"      {ev}: " + "; ".join(f"{s} {t} @ {c}" for s, t, c in legs))
    echo(f"\nEVENTS WHOSE LEGS SIT ON TWO GAMES: {len(r['split_events'])}")
    for e in r["split_events"]:
        echo(f"  {e['series']} {e['day']}  {e['event']}")
        for g in e["games"]:
            echo(f"      {_game(g)}: " + "; ".join(f"{s} {t} @ {c}" for s, t, c in g["legs"]))
    echo("\nBY SERIES AND DAY")
    for k, v in r["by_series_day"].items():
        echo(f"  {k}: two-event games {v['two_event_games']} · split events {v['split_events']}")
    echo("\nFIRST DAY EACH SERIES SHOWS ONE")
    for ser, day in sorted(r["first_day"].items()):
        echo(f"  {ser}: {day}")
    if r.get("graded_error"):
        echo(f"\nLISTED GAMES WITH A GRADED PREDICTION: NOT CHECKED ({r['graded_error']})")
    else:
        echo(f"\nLISTED GAMES WITH A GRADED PREDICTION: {len(r['graded'])}")
        for g in r["graded"]:
            echo(f"  {_game(g)}")
    echo(f"\nKALSHI-LEG-AUDIT two_event_games={len(r['two_event_games'])} split_events={len(r['split_events'])} "
         f"graded={'NOT_CHECKED' if r.get('graded_error') else len(r['graded'])} untickered={r['untickered']} "
         f"tickered={r['tickered']} orphans={r.get('orphans', 0)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 37 item 4: the read-only Kalshi leg audit")
    ap.add_argument("--since", help="captures on or after this date (YYYY-MM-DD, UTC)")
    ap.add_argument("--db", help="SQLite file (default: DATABASE_URL from the environment or .env)")
    a = ap.parse_args(argv)
    if a.since is not None:            # #419 (Codex on #416): a malformed date never gives a quiet wrong window
        try:
            if datetime.strptime(a.since, "%Y-%m-%d").strftime("%Y-%m-%d") != a.since:
                raise ValueError
        except ValueError:
            print(f"REFUSED: --since {a.since!r} is not a date YYYY-MM-DD")
            return 2
    con, form = open_read(db_path(a.db))
    try:
        print(f"read-only open: {form}" + (f" · since {a.since}" if a.since else ""))
        r = audit(con, a.since)
        report(r)
    finally:
        con.close()
    return 1 if r.get("graded_error") else 0


if __name__ == "__main__":
    sys.exit(main())
