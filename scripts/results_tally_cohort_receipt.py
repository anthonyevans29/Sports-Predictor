"""RESULTS.md's DIVERGENCE COHORTS, BEFORE AND AFTER #615 (ARCHITECT 2026-10-20, addendum 147 item 3), READ-ONLY.

"The MLB verified/legacy counts move on the day it merges: the read-only before/after of RESULTS.md's MLB cohort line
from the laptop DB goes in the PR body before merge, as #619's did."

One run, one DB state, one clock, both cohort splits: `results_tally` writes RESULTS.md twice into a scratch
directory, once with main's snapshot read (1X2 snapshots, Kalshi rows left out: a close priced from a Kalshi mid never
reproduces, so its stored divergence reads retained-legacy) and once as built (`kalshi_close_market_filter`: every 1X2
snapshot plus Kalshi's two-way ML rows, as `clv-restate` reads them). Printed: each section's cohort lines (MLB,
Soccer (PL)), BEFORE then AFTER, and the section's Sides line, which the change never moves.

BEFORE narrows only what the cohort split reads: `clv_cohort` is handed the snapshots main's SQL kept (market 1X2,
source set and not kalshi; AFTER's set is a superset of it), so `grading_close` and every other line of the file run
as they do on main. Both passes read one `now` (export's clock is held for the run), so a game at the window's edge
cannot fall in one pass and out of the other.

READ-ONLY: the DB file is opened with a mode=ro URI (a missing file is refused, never created), as
scripts/nfl_close_restate_receipt.py opens it; the exports dir is read (its closing files void re-dated rows) and
nothing is written beside it; RESULTS.md goes to a scratch directory that is removed. Run it from a worktree of the PR
branch, with the laptop checkout as the working directory, so the checkout itself is never switched:

    git fetch origin claude/615-source-stamps
    git worktree add --detach /tmp/sp615 origin/claude/615-source-stamps
    python /tmp/sp615/scripts/results_tally_cohort_receipt.py --db data/sports.db --exports exports
    git worktree remove /tmp/sp615

`--db` is the file the laptop's DATABASE_URL names (data/sports.db by default). The output names no path."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COHORT_MARKS = ("- Sides:", "- Mean model-close divergence, verified close:", "- Retained-legacy model-close divergence")


def section_lines(text: str) -> dict:
    """{section title: [its Sides and cohort lines]} for every '## ' section that carries a cohort line."""
    out: dict = {}
    title = None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
        elif title and line.startswith(COHORT_MARKS):
            out.setdefault(title, []).append(line)
    return {t: ls for t, ls in out.items() if any(not x.startswith("- Sides:") for x in ls)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RESULTS.md's divergence cohorts BEFORE and AFTER #615 (read-only).")
    ap.add_argument("--db", required=True, help="the laptop DB file (opened mode=ro; a missing file is refused)")
    ap.add_argument("--exports", required=True, help="the exports dir holding closing_*.json (read, never written)")
    ap.add_argument("--days", type=int, default=30, help="results-tally's window (default 30, as the command)")
    a = ap.parse_args(argv)
    db = Path(a.db).expanduser().resolve()
    ex = Path(a.exports).expanduser().resolve()
    if not db.is_file():
        print(f"REFUSED: no DB file at --db {a.db!r}: a read-only receipt never creates one")
        return 2
    if not ex.is_dir():
        print(f"REFUSED: --exports {a.exports!r} is not a directory: no receipt, never an empty one")
        return 2
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db.as_posix()}")   # before src is imported: never ./data
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db import database
    from src.walters import clv_restate
    from src.walters import export as export_mod
    eng = create_engine(f"sqlite:///file:{db.as_posix()}?mode=ro&uri=true",
                        connect_args={"uri": True, "check_same_thread": False})
    saved = (database._engine, database.SessionLocal, clv_restate.clv_cohort, export_mod.utc_now_naive)
    database._engine = eng
    database.SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                         expire_on_commit=False)
    now = saved[3]()
    export_mod.utc_now_naive = lambda: now            # one clock: both passes cut the window at the same instant

    def main_read(oc, pred, m, odds, snaps=()):
        # BEFORE: the snapshots main's SQL kept, `_Snp.market == "1X2", _Snp.source != "kalshi"` (export.py before
        # #615; SQL's != drops a NULL source too)
        return saved[2](oc, pred, m, odds, [x for x in snaps if x.market == "1X2" and x.source is not None
                                            and x.source != "kalshi"])
    tmp = Path(tempfile.mkdtemp(prefix="sp615-"))
    texts = {}
    # ONE DB STATE, as #619's receipt: SQLite's data_version on a mode=ro connection before and after both passes
    probe = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    version = probe.execute("PRAGMA data_version").fetchone()[0]
    try:
        for name, built in (("BEFORE", False), ("AFTER", True)):
            clv_restate.clv_cohort = saved[2] if built else main_read   # results_tally imports it at call time
            out = tmp / f"RESULTS_{name}.md"
            export_mod.results_tally(days=a.days, out_path=str(out), exports_dir=str(ex))
            texts[name] = out.read_text()
        moved = probe.execute("PRAGMA data_version").fetchone()[0] != version
    finally:
        database._engine, database.SessionLocal, clv_restate.clv_cohort, export_mod.utc_now_naive = saved
        eng.dispose()
        probe.close()
        shutil.rmtree(tmp, ignore_errors=True)
    if moved:
        print("REFUSED: the DB changed during the receipt (a write landed between its passes), so BEFORE and AFTER "
              "are not one DB state: run it again when no chain is writing")
        return 3
    print(f"RESULTS.md divergence cohorts BEFORE / AFTER (#615, addendum 147 item 3) · read-only: db {db.name} "
          f"(mode=ro), window {a.days} days · BEFORE = main's snapshot read for the cohort split (Kalshi rows left "
          "out), AFTER = as built (kalshi_close_market_filter) · one DB state, one clock")
    b, af = section_lines(texts["BEFORE"]), section_lines(texts["AFTER"])
    for title in list(dict.fromkeys([*b, *af])):
        print(f"## {title}")
        for name, sec in (("BEFORE", b), ("AFTER", af)):
            for line in sec.get(title) or ["(no cohort line)"]:
                print(f"  {name:<6}  {line}")
    if not (b or af):
        print("no section carries a cohort line in the window (no graded MLB or PL game with a stored divergence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
