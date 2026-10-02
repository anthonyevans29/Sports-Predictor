"""
#113 BEFORE/AFTER RECEIPT (architect 2026-09-30) — read-only.

The correction: a SOCCER game whose Kalshi capture lacks a leg (usually the
TIE) is INCOMPLETE — no longer normalized as a two-way set. After the fix the
export ships prob null, normalized false, input_quality.kalshi "partial" and
null kalshi_bid / kalshi_ask / exec_cost_taker.

This runs the REAL soccer prediction export (export_predictions, current
code) over a window, takes every row now marked incomplete
(market.kalshi.missing_legs), and rebuilds what the PRE-FIX export said for
that row from the same exported raw capture (raw_yes_prob) with a frozen copy
of the old rule. The old exec cost is re-derived from the stored HOME quote.

    python3 scripts/kalshi_soccer_incomplete_receipt.py --start 2026-08-01 --end 2026-10-15 [--competition PL]

Database: read-only. Writes nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def old_rule(raw: dict) -> dict:
    """The pre-fix _summarize_kalshi rule, frozen: set size from the snapshots present."""
    total = sum(raw.values())
    expected = 3 if "DRAW" in raw else 2
    two = len(raw) >= expected and total > 0
    return {"normalized": two,
            "prob": {k: round(v / total, 4) for k, v in raw.items()} if two else dict(raw)}


def old_exec(match_id: int) -> float | None:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    from src.walters.venue import kalshi_exec
    with session_scope() as s:
        m = s.get(Match, match_id)
        snaps = s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id == match_id, OddsSnapshot.source == "kalshi",
            OddsSnapshot.selection == "HOME").order_by(OddsSnapshot.captured_at.desc())).scalars()
        home = next((x for x in snaps if x.captured_at is None or m.utc_date is None
                     or x.captured_at < m.utc_date), None)
        return kalshi_exec(home.yes_bid, home.yes_ask)["exec_cost_taker"] if home else None


def receipt(start: datetime, end: datetime, competition: str | None) -> dict:
    from src.db.schema import Sport
    from src.walters.export import export_predictions
    rows = json.loads(export_predictions(sport=Sport.SOCCER, start_date=start, end_date=end,
                                         competition_code=competition))["predictions"]
    with_k = [r for r in rows if ((r.get("market") or {}).get("kalshi"))]
    out = []
    for r in with_k:
        k = r["market"]["kalshi"]
        if not k.get("missing_legs"):
            continue
        before = old_rule(k.get("raw_yes_prob") or {})
        out.append({"match_id": r["match_id"], "game": f"{r['away_team']} @ {r['home_team']}",
                    "utc": r["utc_date"], "competition": r.get("competition"),
                    "legs": sorted((k.get("raw_yes_prob") or {}).keys()), "missing": k["missing_legs"],
                    "before": {**before, "exec_cost": old_exec(r["match_id"]) if before["normalized"] else None},
                    "after": {"normalized": k["normalized"], "prob": k["prob"],
                              "input_quality": (r.get("input_quality") or {}).get("kalshi"),
                              "exec_cost": r.get("exec_cost_taker")}})
    return {"rows": len(rows), "with_kalshi": len(with_k), "affected": out,
            "changed": sum(1 for x in out if x["before"]["normalized"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#113 soccer Kalshi incomplete-set correction: before/after (read-only)")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusive")
    ap.add_argument("--competition", default=None)
    a = ap.parse_args(argv)
    r = receipt(datetime.fromisoformat(a.start), datetime.fromisoformat(a.end), a.competition)
    print(f"#113 RECEIPT soccer {a.competition or 'all'} {a.start} .. {a.end}: rows {r['rows']} · "
          f"with Kalshi {r['with_kalshi']} · incomplete now {len(r['affected'])} · "
          f"CHANGED (were normalized two-way) {r['changed']}")
    for x in r["affected"]:
        b, f = x["before"], x["after"]
        print(f"  #{x['match_id']} {x['utc'][:16]} {x['competition']} {x['game']}: legs {x['legs']} missing {x['missing']}")
        print(f"     BEFORE normalized={b['normalized']} prob={b['prob']} exec_cost={b['exec_cost']}")
        print(f"     AFTER  normalized={f['normalized']} prob={f['prob']} input_quality={f['input_quality']} "
              f"exec_cost={f['exec_cost']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
