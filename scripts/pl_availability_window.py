"""
THE PL AVAILABILITY WINDOW (ARCHITECT 2026-11-01 10:05 ET, addendum 198 items 3 and 5; lane pl-availability, #754) —
read-only, COUNTS ONLY before the 60th; the one read at it, once.

Item 3, verbatim: "the window opens at the first PL kickoff strictly after the shadow's FIRST HOST PAGE (the entry
records declared_at = this addendum's instant and window_opens_at = that kickoff, written by Code's PR when the deploy
receipt is in hand), and holds the first 60 FINISHED PL games with a three-way close from it, counted as the leagues'
reader counts (cancelled / AWD-WO / no close excluded by cause; LIVE or un-ingested waits; postponed by actual
kickoff); the Desk's floor and quarantine play no part in membership. The read at the 60th: mean three-way log-loss of
each arm, unrounded; PASS only if the candidate's is below v22's by at least 0.0050 (the house bar), less or a tie
REJECTS; the close's log-loss printed beside both and gating nothing; Brier and the per-club counts printed for the
record. One read; the fence: no other read of either arm on the window until the verdict (guards_backtest's
pattern)."

Without --read: the counts only (src/walters/pl_availability.read / lines): members n of 60, the exclusions by cause,
the pending games by kind, the postponed games not placed, the state (accruing, waiting, ready). Never a log-loss, a
probability or a hit of either arm, at any n. A null window_opens_at REFUSES (exit 2): the window has not opened.

--read: THE ONE READ, refused unless the state is ready (60 members, nothing pending before the 60th). It first
reserves the read (the shared cross-ref guard, #329, first: a reservation of this experiment on another ref refuses;
then an exclusive create of docs/registry/pl-availability-v1.started.json; a second --read is refused: the read is
spent; a failed write spends nothing), then re-derives the window in its own read-only transaction and scores it
(pl_availability.score: both arms from the one stored prediction row per game, at the grader's close, on the
90-minute outcome). It records nothing in the registry: the verdict is recorded by Code's PR after the architect reads it.

WHERE TO RUN IT: the candidate's arm exists only in the HOST's database (the training pass prices it on the host
only), so the window and the read are the host's. The DB is the one DATABASE_URL names (else ./data/sports.db), as
scripts/leagues_close_receipt.py reads it; a path with no file is REFUSED (exit 2) before any import that could open
it. One mode=ro session (src.db.database.readonly_scope); nothing written but the reservation.

--project --db COPY: THE COUNT FROM THE STORED SCHEDULE (ARCHITECT 2026-11-02 13:10 ET, addendum 220 item 6: "the
12-20/12-21 projection stands until Code's count from the stored schedule says otherwise"). Read-only, and it reads
fixtures and kickoffs only: the PL 2026/27 stored fixtures kicking off at or after the entry's window_opens_at
(cancelled / postponed / stale_orphan left out, kalshi_match.NOT_GAMES, as leagues_close_receipt's projection), in
kickoff order (kickoff, then id), and the 60th's kickoff UTC date, every game assumed to finish with a three-way close
(a projection, not a floor); fewer than 60 stored: the count and no date (law 4). Beside it: the fixtures per UTC
kickoff date up to the 60th (a midweek round shows as its own date), the stored fixtures kicking off between the first
host page's stamp and window_opens_at (addendum 198 item 3: the window opens at the first kickoff strictly after the
page, so 0 is expected and anything else is named), and the roadmap's step date for the 60th game with the
projection's distance from it in days (a moved line is the architect's; this prints, it moves nothing). No score,
status_raw, close, odds row or prediction is selected: the query names the id, the kickoff and the status columns only,
so the window's fence stands. --db is required with --project and refused without it: a .backup copy OUTSIDE data/
(mlb_pitchers_gate.check_db: never created, never under any data/ by path or by identity, never the app's configured
database), refused when a -wal, -shm or -journal file sits beside it (immutable=1 would ignore it: nfl_v2_gate.
check_db's rule), opened through mlb_pitchers_gate.readonly_session, a mode=ro&immutable=1 URI (addendum 198 item
6(ii)): nothing written, no sidecar. A copy that cannot be read as the schema the query needs (no competitions
table, a missing column, a status outside the enum) is REFUSED, not a traceback. --project takes --db only: --read
and --no-fetch beside it are refused.

Exit status: 0 printed; 2 a refusal.
Run:  python3 scripts/pl_availability_window.py [--read [--no-fetch]]
      python3 scripts/pl_availability_window.py --project --db COPY
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFUSED = 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--read", action="store_true",
                    help="the one read at the 60th member (refused unless ready; reserved before it scores; once)")
    ap.add_argument("--no-fetch", dest="no_fetch", action="store_true",
                    help="the reservation's cross-ref guard (#329) checks only the refs this clone knows (no fetch of "
                         "origin laptop/*); its receipt then says other clones were not checked")
    ap.add_argument("--project", action="store_true",
                    help="the count from the stored schedule: the 60th PL fixture kicking off at or after "
                         "window_opens_at (fixtures and kickoffs only; needs --db)")
    ap.add_argument("--db", default=None,
                    help="--project's database: a .backup copy outside data/, opened mode=ro&immutable=1")
    a = ap.parse_args(argv)
    if a.project or a.db is not None:
        if a.read or a.no_fetch or not a.project or a.db is None:
            print("REFUSED: --project takes --db COPY (a .backup copy outside data/) and nothing else; --db is "
                  "--project's only; the counts and the one read read DATABASE_URL")
            return REFUSED
        return project_main(a.db)
    import importlib.util                     # the close receipt's own DB resolution, loaded from its file
    spec = importlib.util.spec_from_file_location(
        "leagues_close_receipt", os.path.join(os.path.dirname(os.path.abspath(__file__)), "leagues_close_receipt.py"))
    receipt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receipt)
    f = receipt.db_file()
    if not f.is_file():
        print(f"REFUSED: no database at {f}: the reader never creates one")
        return REFUSED
    from src.timeutil import utc_now_naive
    from src.walters import pl_availability as pa
    now = utc_now_naive()
    res = pa.read(now=now)
    for ln in pa.lines(res, now):
        print(ln)
    if res.get("refused"):
        return REFUSED
    if not a.read:
        return 0
    if res.get("verdict_recorded"):
        print(f"REFUSED: the verdict is recorded in {pa.EID}: the one read is spent")
        return REFUSED
    if res["state"] != "ready":
        print(f"REFUSED: the one read is at the {pa.WINDOW_GAMES}th member with nothing pending before it (state "
              f"{res['state']})")
        return REFUSED
    try:
        path = pa.reserve(now, no_fetch=a.no_fetch, echo=lambda line: print(f"  {line}"))
        print(f"reserved: {os.path.relpath(path)} (the one read)")
        out = pa.score(res, now=now)
    except pa.WindowRefused as err:
        print(f"REFUSED: {err}")
        return REFUSED
    for ln in pa.read_lines(out):
        print(ln)
    return 0


# ------------------------------------------------------------------- --project: the count (addendum 220 item 6) --

SIDECARS = ("-wal", "-shm", "-journal")      # nfl_v2_gate.check_db's rule: immutable=1 would ignore each of them
STEP_60TH = "the 60th window game is final"  # the lane pl-availability's step, by the start of its what


def project(s, opens, page_at=None) -> dict:
    """The stored PL 2026/27 schedule from `opens` (window_opens_at, naive UTC): fixtures (NOT_GAMES left out) kicking
    off at or after it, in kickoff order (kickoff, then id); the 60th, or None when fewer are stored. Selects the id,
    the kickoff and the status only: no outcome of any game is read (the window's fence)."""
    from collections import Counter

    from sqlalchemy import select

    from src.db.schema import Competition, Match
    from src.ingestion.kalshi_match import NOT_GAMES
    from src.walters import pl_availability as pa
    rows = s.execute(select(Match.id, Match.utc_date, Match.status)
                     .join(Competition, Competition.id == Match.competition_id)
                     .where(Competition.code == pa.COMPETITION, Match.season == pa.SEASON)
                     .order_by(Match.utc_date, Match.id)).all()
    st = [(i, ko, str(getattr(x, "value", x) or "").lower()) for i, ko, x in rows]
    games = [(i, ko) for i, ko, x in st if x not in NOT_GAMES and ko is not None]
    after = [(i, ko) for i, ko in games if ko >= opens]
    upto = after[:pa.WINDOW_GAMES]
    return {"stored": len(st), "not_games": sum(x in NOT_GAMES for _, _, x in st),
            "before": len(games) - len(after), "from_window": len(after),
            "between": None if page_at is None else sum(page_at < ko < opens for _, ko in games),
            "first": after[0] if after else None,
            "nth": after[pa.WINDOW_GAMES - 1] if len(after) >= pa.WINDOW_GAMES else None,
            "by_date": sorted(Counter(ko.date() for _, ko in upto).items())}


def step_due() -> str | None:
    """The roadmap's due date of lane pl-availability's 60th-game step (src.roadmap.load), or None."""
    try:
        from src import roadmap as rm
        lane = next(x for x in rm.load()["lanes"] if x.get("lane") == "pl-availability")
        return next(st["due"] for st in lane["steps"] if str(st.get("what", "")).startswith(STEP_60TH))
    except Exception:                         # noqa: BLE001 - the comparison line says it could not be read
        return None


def project_lines(r: dict, opens, page: dict | None, label: str, due: str | None) -> list[str]:
    from src.walters import pl_availability as pa
    n = pa.WINDOW_GAMES
    L = [f"PL AVAILABILITY WINDOW — THE COUNT FROM THE STORED SCHEDULE ({pa.EID}; ARCHITECT 2026-11-02 13:10 ET, "
         f"addendum 220 item 6; #754) · read-only · fixtures and kickoffs only (no score, close or prediction read) · "
         f"season {pa.SEASON} · {label}",
         f"window opens {opens:%Y-%m-%dT%H:%M:%SZ} (the entry's window_opens_at) · the first host page "
         + (f"{page.get('file')} stamped {page.get('stamp')}" if page else "not recorded in the entry")]
    L.append(f"  - stored PL {pa.SEASON} games {r['stored']} · cancelled / postponed / stale_orphan {r['not_games']} "
             f"(left out) · kicking off before the window {r['before']} (never in it)")
    if r["between"] is not None:
        L.append(f"  - fixtures kicking off strictly between the first host page and the window: {r['between']} "
                 "(addendum 198 item 3: the window opens at the first PL kickoff strictly after the page; 0 expected)"
                 + ("" if r["between"] == 0 else " · NOT 0: named for the architect"))
    L.append("  - the first fixture at or after the window: "
             + (f"kickoff {r['first'][1]:%Y-%m-%dT%H:%M:%SZ} (match {r['first'][0]})" if r["first"] else "none stored"))
    if r["by_date"]:
        L.append(f"  - fixtures per UTC kickoff date, up to the {n}th: "
                 + " · ".join(f"{d:%m-%d} {c}" for d, c in r["by_date"]))
    if r["nth"] is None:
        L.append(f"  - the {n}th fixture at or after the window: not stored (only {r['from_window']} stored at or after "
                 "it); no date (law 4)")
        L.append(f"  - the roadmap's step ({STEP_60TH}): due {due or 'not read'}; no projected date to set beside it")
        return L
    d = r["nth"][1].date().isoformat()
    L.append(f"  - the {n}th fixture at or after the window: kickoff {d} (UTC date; {r['nth'][1]:%H:%M:%SZ}; match "
             f"{r['nth'][0]}) · {r['from_window']} stored at or after the window · every game assumed to finish with "
             "a three-way close: a projection, not a floor")
    L.append(f"  - the roadmap's step ({STEP_60TH}): due {due or 'not read'} · projected {d} · " + _versus(d, due)
             + " (the step's date and any moved line are the architect's; nothing moves here)")
    return L


def _versus(d: str, due: str | None) -> str:
    """The projected UTC date against the step's due date, in days: never a verdict on the date."""
    from datetime import date
    try:
        k = (date.fromisoformat(d) - date.fromisoformat(due)).days
    except (TypeError, ValueError):
        return "the step's date not read"
    if k == 0:
        return "the step's date"
    return f"{abs(k)} day{'s' if abs(k) != 1 else ''} {'before' if k < 0 else 'after'} the step's date"


def project_main(db) -> int:
    """--project --db COPY: the count, printed; exit 0, or 2 on a refusal (nothing read, nothing written)."""
    from src.walters import mlb_pitchers_gate as mp
    from src.walters import pl_availability as pa
    try:
        path = mp.check_db(db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        mp.open_ro(path).close()
        e = pa._entry()
        _, opens = pa.checked(e)
    except (mp.GateRefused, pa.WindowRefused) as err:
        print(f"REFUSED: {err}; nothing read")
        return REFUSED
    page = e.get("first_host_page") if isinstance(e.get("first_host_page"), dict) else None
    page_at = pa.parse_instant(page.get("stamp")) if page else None
    import sqlite3

    from sqlalchemy.exc import SQLAlchemyError
    try:
        with mp.readonly_session(path) as s:
            r = project(s, opens, page_at)
    except (SQLAlchemyError, sqlite3.Error, LookupError) as err:   # a copy without the schema the query needs
        why = (str(err).strip().splitlines() or [""])[0]
        print(f"REFUSED: --db {path}: cannot be read as the schema the projection needs ({type(err).__name__}: {why}); "
              "nothing read")
        return REFUSED
    for ln in project_lines(r, opens, page, f"db --db {path} (a .backup copy, opened "
                                            f"{mp.COPY_URI_QUERY.lstrip('?')})", step_due()):
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
