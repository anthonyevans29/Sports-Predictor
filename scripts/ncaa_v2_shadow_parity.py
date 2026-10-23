"""
NCAA v2 SHADOW PARITY RECEIPT (ARCHITECT 2026-10-23, addendum 158 item 1(b)) — read-only, synthetic.

Verbatim: "A read-only receipt on synthetic cases that the shadow's probabilities equal the gate path's."

On a seeded synthetic D2 stream (ncaa_shadow.synthetic_stream: 2024-2026, regular weeks then a postseason week, one
game in ten neutral, several games at each kickoff), ncaa_shadow.parity runs both paths at the frozen s:
  - the gate path: ncaa_v1r_gate.run_gate on ncaa-elo-v2's gate read, the declared model recorded;
  - the shadow path: for every game the gate scored, ncaa_shadow.walk over the stream games kicking off before it,
    then the prediction.
It prints the count compared, the unequal count and the largest |diff| (equal within 1e-12), and the pregame
difference (D8) on the neutral games, reported. No DB is read and nothing is written.

Run:  python3 scripts/ncaa_v2_shadow_parity.py [--seed 158] [--rows]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=158, help="the synthetic stream's seed (default 158)")
    ap.add_argument("--rows", action="store_true", help="print every compared game")
    a = ap.parse_args(argv)
    from src.walters import ncaa_shadow as sh
    r = sh.parity(sh.synthetic_stream(seed=a.seed))
    for line in sh.parity_lines(r, rows=a.rows):
        print(line)
    return 0 if r["compared"] and not r["unequal"] else 1


if __name__ == "__main__":
    sys.exit(main())
