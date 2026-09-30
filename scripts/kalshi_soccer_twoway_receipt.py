"""
#117 BEFORE/AFTER RECEIPT (architect 2026-09-30, HIGH: cups are on the
venue-edge charter) — read-only.

The correction: on SOCCER rows the fixtures export (cups, UNL, PL fixtures)
and the window card's Kalshi home-price no longer treat HOME + AWAY as a
two-sided set.
- A 1X2 set is complete only with HOME, DRAW and AWAY, and P(home) is
  normalized over all three.
- A set missing a leg is "partial": no exec fields, no Kalshi home price,
  no venue gap.

For every soccer match with Kalshi captures in the window this prints the
row's BEFORE read (the old two-way rule: status two_sided on HOME + AWAY,
home = H/(H+A)) beside the AFTER read (the real code path: _fixture_row +
venue.kalshi_home_prob), including the venue gap vs the book fair and the
STALE-BOOK? flag. Only rows where something changed are listed.

    python3 scripts/kalshi_soccer_twoway_receipt.py --start 2026-08-01 --end 2026-10-15 [--competition EFL]

Database: read-only. Writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def receipt(start: datetime, end: datetime, competition: str | None) -> dict:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, OddsSnapshot, Sport
    from src.walters.export import _fixture_row
    from src.walters.venue import kalshi_exec, kalshi_home_prob, venue_gap

    out, n_soccer, n_kal = [], 0, 0
    with session_scope() as s:
        q = select(Match).where(Match.sport == Sport.SOCCER, Match.utc_date >= start, Match.utc_date < end)
        if competition:
            q = q.join(Competition).where(Competition.code == competition)
        for m in s.execute(q.order_by(Match.utc_date)).scalars():
            n_soccer += 1
            snaps = list(s.execute(select(OddsSnapshot).where(
                OddsSnapshot.match_id == m.id, OddsSnapshot.source == "kalshi")).scalars())
            if not snaps:
                continue
            n_kal += 1
            code = m.competition.code if m.competition else "?"
            counts = Counter()
            row = _fixture_row(s, m, code, Counter(), counts)
            fair = ((row.get("market") or {}).get("fair_prob") or {}).get("HOME")
            old_k = kalshi_home_prob(snaps, m.utc_date)                       # pre-#117: H/(H+A)
            new_k = kalshi_home_prob(snaps, m.utc_date, three_way=True)
            pre = [x for x in snaps if x.captured_at is None or m.utc_date is None or x.captured_at < m.utc_date]
            legs = sorted({x.selection for x in pre})
            old_status = "two_sided" if {"HOME", "AWAY"} <= set(legs) else ("one_sided" if legs else "absent")
            old_exec = (kalshi_exec(old_k["home_bid"], old_k["home_ask"])["kalshi_exec_cost"]
                        if old_status == "two_sided" and old_k else None)
            og, of = venue_gap(fair, old_k["home"] if old_k else None)
            ng, nf = venue_gap(fair, new_k["home"] if new_k else None)
            before = {"status": old_status, "kalshi_home": round(old_k["home"], 4) if old_k else None,
                      "exec_cost": old_exec, "venue_gap_pp": og, "flag": of}
            after = {"status": (row.get("kalshi") or {}).get("status", "absent"),
                     "kalshi_home": round(new_k["home"], 4) if new_k else None,
                     "exec_cost": row.get("kalshi_exec_cost"), "venue_gap_pp": ng, "flag": nf}
            if before != after:
                out.append({"match_id": m.id, "competition": code, "utc": m.utc_date.isoformat(),
                            "game": f"{row['away_team']} @ {row['home_team']}", "legs": legs,
                            "book_fair_home": fair, "before": before, "after": after})
    flags = Counter((x["before"]["flag"], x["after"]["flag"]) for x in out)
    return {"soccer_matches": n_soccer, "with_kalshi": n_kal, "changed": out,
            "partial_now": sum(1 for x in out if x["after"]["status"] == "partial"),
            "stale_flag_before_after": {f"{b}->{a}": n for (b, a), n in flags.items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#117 soccer two-way shortcut correction: before/after (read-only)")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusive")
    ap.add_argument("--competition", default=None)
    a = ap.parse_args(argv)
    r = receipt(datetime.fromisoformat(a.start), datetime.fromisoformat(a.end), a.competition)
    print(f"#117 RECEIPT soccer {a.competition or 'all'} {a.start} .. {a.end}: matches {r['soccer_matches']} · "
          f"with Kalshi {r['with_kalshi']} · CHANGED {len(r['changed'])} · now partial {r['partial_now']} · "
          f"STALE-BOOK? before->after {r['stale_flag_before_after']}")
    for x in r["changed"]:
        b, f = x["before"], x["after"]
        print(f"  #{x['match_id']} {x['utc'][:16]} {x['competition']} {x['game']}: legs {x['legs']} "
              f"book fair H {x['book_fair_home']}")
        print(f"     BEFORE status={b['status']} kalshi_home={b['kalshi_home']} exec={b['exec_cost']} "
              f"gap={b['venue_gap_pp']} flag={b['flag']}")
        print(f"     AFTER  status={f['status']} kalshi_home={f['kalshi_home']} exec={f['exec_cost']} "
              f"gap={f['venue_gap_pp']} flag={f['flag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
