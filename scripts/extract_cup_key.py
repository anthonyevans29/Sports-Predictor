"""
Cup acceptance exam — ANSWER KEY EXTRACTOR (read-only).

Dumps every finished EFL/CL/UEL fixture that has stored pre-kickoff book
odds: teams, result, and the consensus fair 1X2 (median across books,
overround stripped). Output: exports/cup_answer_key.csv — the input the
exam script (next session) scores v22's cup path against, ±8pp bar.

Run:  python3 scripts/extract_cup_key.py
Writes nothing to the DB.
"""
import csv
import statistics
import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv(".env")

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds

CUPS = ("EFL", "CL", "UEL")


def main() -> None:
    rows_out = []
    with session_scope() as s:
        comps = {c.id: c.code for c in s.execute(select(Competition)).scalars()
                 if c.code in CUPS}
        matches = list(s.execute(
            select(Match).where(
                Match.competition_id.in_(list(comps)),
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
            ).order_by(Match.utc_date)
        ).scalars())
        for m in matches:
            odds = list(s.execute(
                select(Odds).where(
                    Odds.match_id == m.id,
                    Odds.market == "1X2",
                    Odds.captured_at < m.utc_date,
                )
            ).scalars())
            if not odds:
                continue
            # latest price per (bookmaker, selection), then median per selection
            latest = {}
            for o in odds:
                key = (o.bookmaker, o.selection)
                if key not in latest or o.captured_at > latest[key].captured_at:
                    latest[key] = o
            per_sel = {}
            for (bk, sel), o in latest.items():
                if o.price_decimal and o.price_decimal > 1.0:
                    per_sel.setdefault(sel, []).append(1.0 / o.price_decimal)
            if not all(k in per_sel for k in ("HOME", "DRAW", "AWAY")):
                continue
            med = {k: statistics.median(v) for k, v in per_sel.items()}
            over = sum(med.values())
            fair = {k: round(v / over, 4) for k, v in med.items()}
            res = ("HOME" if m.home_score > m.away_score
                   else "AWAY" if m.away_score > m.home_score else "DRAW")
            rows_out.append({
                "match_id": m.id,
                "date": m.utc_date.date().isoformat(),
                "comp": comps[m.competition_id],
                "stage": m.stage or "",
                "home": m.home_team.name if m.home_team else "?",
                "away": m.away_team.name if m.away_team else "?",
                "score": f"{m.home_score}-{m.away_score}",
                "result": res,
                "fair_home": fair["HOME"],
                "fair_draw": fair["DRAW"],
                "fair_away": fair["AWAY"],
                "books": len({bk for bk, _ in latest}),
            })
    path = "exports/cup_answer_key.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    print(f"✓ {len(rows_out)} answer-key fixtures -> {path}")
    by = {}
    for r in rows_out:
        by[r["comp"]] = by.get(r["comp"], 0) + 1
    print("  by competition:", by)


if __name__ == "__main__":
    main()
