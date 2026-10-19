"""THE NFL CLOSE, BEFORE AND AFTER (ARCHITECT 2026-10-19, addendum 137 item 4, #614), READ-ONLY.

"Gate-adjacent (the measurement contract): the PR's body carries the NFL record BEFORE and AFTER (season to date and
by week, the 59-game "vs close" line restated), posted before merge; the headline switches with the merge."

One run, one DB state, both records: the NFL results file as `export-nfl-results` writes it, twice, into a scratch
directory, once with the stale-book rule left out (src.walters.close.stale_book_close as the identity: main's close,
`close_1x2` on the odds table) and once as built; and `nfl-grade`'s summary both ways (the pick divergence, the value
side, the close's capture age). Printed: the season, every week and the pre-live line, BEFORE then AFTER; the counts
of the rule (stamp known / unknown, more than 24 h, switched, unpriced); every row whose close changed.

READ-ONLY: the DB file is opened with a mode=ro URI (no connect hook, no pragma; a missing file is refused, never
created), as venue_quote_age's receipts open it; the exports dir's closing_*.json files are copied into a scratch
directory (they void re-dated rows, redated.py) and nothing is written beside them. Run it from a worktree of the PR
branch, with the laptop checkout as the working directory, so the checkout itself is never switched (its closing watch
runs from it every minute):

    git fetch origin claude/nfl-close-kalshi
    git worktree add --detach /tmp/nfl614 origin/claude/nfl-close-kalshi
    python /tmp/nfl614/scripts/nfl_close_restate_receipt.py --db data/sports.db --exports exports
    git worktree remove /tmp/nfl614

`--db` is the file the laptop's DATABASE_URL names (data/sports.db by default). The output names no path."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _rows(doc: dict) -> dict:
    return {r["match_id"]: r for r in (doc.get("results") or []) + ((doc.get("pre_live") or {}).get("results") or [])}


def _beat(row: dict) -> bool | None:
    from src.walters.vs_close import pair_from_row
    p = pair_from_row(row)
    return None if p is None else p[0] > p[1]


def report(docs: dict, grades: dict) -> list[str]:
    from src.walters.vs_close import line
    out = []
    b, a = docs["BEFORE"]["record"], docs["AFTER"]["record"]
    out.append(f"season games {b.get('games')} · top-pick hits {b.get('hits')}/{b.get('decided')} decided · pushes "
               f"{b.get('pushes')} (the close does not move a hit)")
    out.append(f"  BEFORE  {line(b.get('vs_close'))}")
    out.append(f"  AFTER   {line(a.get('vs_close'))}")
    out.append("by week:")
    for w in b.get("by_week") or {}:
        out.append(f"  W{w} BEFORE  {line(b['by_week'][w].get('vs_close'))}")
        out.append(f"  W{w} AFTER   {line((a.get('by_week') or {}).get(w, {}).get('vs_close'))}")
    pb, pa = (((docs[k].get("pre_live") or {}).get("record") or {}) for k in ("BEFORE", "AFTER"))
    out.append(f"pre-live (never pooled) BEFORE  {line(pb.get('vs_close'))}")
    out.append(f"pre-live (never pooled) AFTER   {line(pa.get('vs_close'))}")
    for k in ("BEFORE", "AFTER"):
        g = grades[k]
        out.append(f"nfl-grade {k:6} mean model-close divergence {g.get('mean_clv_pp')}pp · value side "
                   f"{g.get('mean_value_side_clv_pp')}pp (n={g.get('value_side_n')}) · value-shadow "
                   f"{g.get('mean_value_shadow_clv_pp')}pp (n={g.get('value_shadow_n')}) · close capture age "
                   f"{g.get('close_minutes_before_start')}")
    rb, ra = _rows(docs["BEFORE"]), _rows(docs["AFTER"])
    ages = [((r["graded"] or {}).get("close_book_stamp_age_h")) for r in ra.values()]
    refs = [((r["graded"] or {}).get("close_reference")) for r in ra.values()]
    stale = sum(1 for x in ages if x is not None and x > 24)
    out.append(f"the rule over {len(ra)} graded rows: stamp known {sum(x is not None for x in ages)} · unknown "
               f"(NULL, absent, no close) {sum(x is None for x in ages)} · more than 24 h before kickoff {stale} · "
               f"switched to the session's Kalshi mid {refs.count('kalshi')} · unpriced (no two-sided Kalshi quote "
               f"within the cap in that session) {sum(1 for r in ra.values() if r['graded'].get('close_stale_book'))}"
               f" · three-way kept {sum(1 for r in ra.values() if r['graded'].get('close_stale_unswitched'))}")
    changed = [m for m in ra if (ra[m]["graded"].get("close_fair") != (rb.get(m) or {}).get("graded", {}).get("close_fair"))]
    out.append(f"rows whose close changed: {len(changed)}")
    out.append("| match | wk | kickoff (UTC) | game | stamp age h | BEFORE close HOME | AFTER | AFTER close HOME | "
               "Kalshi bid/ask | beat the close BEFORE → AFTER |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for m in sorted(changed, key=lambda x: ra[x]["utc_date"]):
        r, g0, g1 = ra[m], (rb[m]["graded"] if m in rb else {}), ra[m]["graded"]
        k = g1.get("close_kalshi") or {}
        h0 = (g0.get("close_fair") or {}).get("HOME")
        h1 = (g1.get("close_fair") or {}).get("HOME")
        out.append(f"| {m} | {r.get('week')} | {r['utc_date']} | {r['away_team']} @ {r['home_team']} | "
                   f"{g1.get('close_book_stamp_age_h')} | {h0} | {g1.get('close_reference') or 'UNPRICED'} | {h1} | "
                   f"{k.get('bid', '—')}/{k.get('ask', '—')} | {_beat(rb[m]) if m in rb else None} → {_beat(r)} |")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NFL record BEFORE and AFTER the stale-book close rule (read-only).")
    ap.add_argument("--db", required=True, help="the laptop DB file (opened mode=ro; a missing file is refused)")
    ap.add_argument("--exports", required=True, help="the exports dir holding closing_*.json (read, never written)")
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
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db import database
    from src.walters import close as close_mod
    from src.walters.nfl_predict import export_nfl_results, grade_nfl
    eng = create_engine(f"sqlite:///file:{db.as_posix()}?mode=ro&uri=true",
                        connect_args={"uri": True, "check_same_thread": False})
    saved = (database._engine, database.SessionLocal, close_mod.stale_book_close)
    database._engine = eng
    database.SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                         expire_on_commit=False)
    tmp = Path(tempfile.mkdtemp(prefix="nfl614-"))
    docs, grades = {}, {}
    try:
        for name, rule in (("BEFORE", False), ("AFTER", True)):
            d = tmp / name.lower()
            d.mkdir()
            for f in ex.glob("closing_*.json"):
                shutil.copy2(f, d / f.name)
            close_mod.stale_book_close = saved[2] if rule else (lambda s, m, cl, snaps=None: cl)
            docs[name] = json.load(open(export_nfl_results(out_dir=str(d))))
            grades[name] = grade_nfl(days_back=None, exports_dir=str(d))
    finally:
        database._engine, database.SessionLocal, close_mod.stale_book_close = saved
        eng.dispose()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"NFL close BEFORE / AFTER (addendum 137 item 4) · read-only: db {db.name} (mode=ro), "
          f"{len(list(ex.glob('closing_*.json')))} closing files read · BEFORE = main's close (close_1x2), "
          "AFTER = as built")
    for ln in report(docs, grades):
        print(ln)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
