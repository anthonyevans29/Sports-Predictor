"""
THE LEAGUES' COHORT READER (ARCHITECT 2026-10-30 09:30 ET, addendum 178, PR ORDER item 2: "The cohort reader per
R2–R4, R8."; lane leagues, #322) — read-only, COUNTS ONLY.

R2, verbatim: "BEFORE GAME 60 the reader prints counts only: members n of 60 since the declaration, exclusions by
cause, pending (scheduled, LIVE, un-ingested), rows present or missing; no running figure of either arm (law 3:
nothing is read before its pre-committed n). A counts-only reader IS "in hand" once its scoring path exists and is
test-pinned (the verdict at n = 60 is its function); it is merged before any league is declared."

Per league (SA, BL1, FL1, ELC), from src/walters/leagues_window.py: NOT DECLARED (no registry entry; nothing else is
printed), or the declaration's instant (declared_at, UTC) and frozen constants, members n of 60, the exclusions by
cause, the pending games by kind (R2's list: scheduled, LIVE, un-ingested; then finished with no usable result, i.e.
no score stored or a non-FT code with no 90-minute score, and a game at or before the instant not final, which every
member's walk reads once final; and the score disagreement, an FT or no-raw-code row whose stored 90-minute score differs from its
stored score, listed with both figures: ARCHITECT 2026-10-30, addendum 184 item 2, #736), the AWD / WO rows released from the walk and the members with no raw code (each
listed, ARCHITECT 2026-10-30, addendum 181 items 2 and 3), the postponed games not placed, the stored prospective rows
present or missing (none until the export PR), and the state: accruing, waiting (R4: a game before the 60th pending) or ready. At ready it
says the one read is addendum 178 PR ORDER item 5's PR and stops: nothing is scored by this script, at any n.

The DB is the one DATABASE_URL names (else ./data/sports.db), as scripts/leagues_close_receipt.py reads it. A path
with no file is REFUSED (exit 2) before any import that could open it: the reader never creates a database. One
mode=ro session per league (src.db.database.readonly_scope: no connect hook, no pragma, no commit); nothing written.

Exit status: 0 the counts printed; 2 a refusal (no database; or a declared league whose entry names another league
in its `competition` field (addendum 181 item 6), has no UTC declared_at, no frozen constants or constants that differ from the soccer-expansion-v1 run record's, or whose season stores a stage
label the code cannot place kicking off at or before the 60th member or the read clock, F3). A refused league prints its REFUSED line; the others still print.

Run:  python3 scripts/leagues_window.py [--exports exports]
Paste the whole output on #322.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFUSED = 2                                  # the exit status of a refusal, as scripts/leagues_close_receipt.py


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exports", default="exports",
                    help="the directory holding the shadow export's files, read for stored rows (default exports)")
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
    from src.walters import leagues_window as lw
    now = utc_now_naive()
    res = lw.read(lw.LEAGUES, now=now, export_dir=a.exports)
    for ln in lw.lines(res, now):
        print(ln)
    return REFUSED if any(w.get("refused") for w in res.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
