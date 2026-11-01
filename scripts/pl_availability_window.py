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

Exit status: 0 printed; 2 a refusal.
Run:  python3 scripts/pl_availability_window.py [--read [--no-fetch]]
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
    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
