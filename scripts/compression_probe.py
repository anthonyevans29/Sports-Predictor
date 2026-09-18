"""
Compression instrumentation probe (2026-09-19).

THE QUESTION: v19/v20 collapse PL Elo spread from ~323 to ~63-74,
deterministically. Season-transition counting (8) failed to convict.
This probe replaces inference with observation: run the EXACT train()
loop twice — pot A excludes the pyramid competitions (ELC/EL1/EL2),
pot B is everything — and dump the PL-team spread trajectory every 250
matches, plus every season-regression firing. The collapse point
becomes visible directly.

Run:  python3 scripts/compression_probe.py
Read-only; trains in memory; writes nothing.
"""
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport
from src.models.elo import (EloConfig, EloState, apply_season_regression,
                            update_after_match)

PYRAMID = {"ELC", "EL1", "EL2"}
DUMP_EVERY = 250


def load_stream():
    with session_scope() as s:
        comps = {c.id: c.code for c in s.execute(select(Competition)).scalars()}
        rows = list(s.execute(
            select(Match).where(
                Match.sport == Sport.SOCCER,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars())
        pl_ids = set()
        stream = []
        for m in rows:
            code = comps.get(m.competition_id, "?")
            if code == "PL":
                pl_ids.add(m.home_team_id)
                pl_ids.add(m.away_team_id)
            stream.append((code, m.season, m.home_team_id, m.away_team_id,
                           m.home_score, m.away_score))
    return stream, pl_ids


def run(stream, pl_ids, label):
    state = EloState(config=EloConfig())
    last_season = None
    regressions = 0
    print(f"\n── {label}: {len(stream)} matches ──")
    print(f"{'idx':>6} {'season':>8} {'PL spread':>10} {'PL n':>5} {'regr#':>6}")

    def pl_spread():
        vals = [state.ratings[t] for t in pl_ids if t in state.ratings]
        return (max(vals) - min(vals), len(vals)) if vals else (0.0, 0)

    for i, (code, season, h, a, hs, as_) in enumerate(stream, 1):
        if last_season is not None and season != last_season:
            apply_season_regression(state)
            regressions += 1
            sp, n = pl_spread()
            print(f"{i:>6} {season:>8} {sp:>10.0f} {n:>5} {regressions:>6}  <- regression fired (from {last_season})")
        last_season = season
        hr, ar = state.get(h), state.get(a)
        nh, na = update_after_match(hr, ar, hs, as_, state.config)
        state.set(h, nh)
        state.set(a, na)
        if i % DUMP_EVERY == 0:
            sp, n = pl_spread()
            print(f"{i:>6} {season:>8} {sp:>10.0f} {n:>5} {regressions:>6}")
    sp, n = pl_spread()
    print(f"{'FINAL':>6} {'':>8} {sp:>10.0f} {n:>5} {regressions:>6}")
    return sp


def main():
    stream, pl_ids = load_stream()
    a = [r for r in stream if r[0] not in PYRAMID]
    sp_a = run(a, pl_ids, "POT A (no pyramid)")
    sp_b = run(stream, pl_ids, "POT B (everything)")
    print(f"\nVERDICT DATA: pot A final PL spread {sp_a:.0f} vs pot B {sp_b:.0f}")
    print("Read: where B's spread departs from A's marks the mechanism —")
    print("at a regression line = season-string interleaving; gradual after")
    print("pyramid matches enter = cross-pot rating flow through cup ties;")
    print("similar finals = the collapse lives elsewhere (report both).")


if __name__ == "__main__":
    main()
