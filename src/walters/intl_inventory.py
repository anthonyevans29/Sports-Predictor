"""
#220 UNL lane, STEP 1 (law 1, read before the pre-commitment): what national-
team results the DB actually stores. ARCHITECT 2026-10-02: "an international-
team Elo candidate (national teams, stored results, home advantage declared a
priori, gate = better than the naive baseline by 0.010, same bands)." The
pre-commitment (naive baseline, home term, splits) is written FROM this
receipt, before any fit.

Read-only. Per national-team competition code and season: finished matches
with both scores, date span, distinct teams, raw home / draw / away shares and
venue completeness. Then: how much prior international history each UNL team
has (results before its first UNL match). Law 4: no neutral site is inferred —
the DB has no neutral flag; `venue` is reported as stored (share populated)
and never compared to a guessed "home ground".
"""
from __future__ import annotations

from collections import Counter, defaultdict

INTL_CODES = ("UNL", "WC", "UEFA_EURO", "WCQ_EU", "WCQ_SA", "WCQ_AF", "WCQ_AS", "WCQ_NA", "WCQ_OC",
              "FRIENDLIES_INT", "WCQ_IC", "UEFA_EURO_Q", "CONCACAF_NL")


def inventory(s) -> dict:
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus

    comps = {c.id: c.code for c in s.execute(select(Competition).where(Competition.code.in_(INTL_CODES))).scalars()}
    rows = s.execute(select(Match).where(Match.competition_id.in_(list(comps)))
                     .order_by(Match.utc_date, Match.id)).scalars().all() if comps else []
    by: dict = defaultdict(lambda: Counter())
    span: dict = {}
    teams: dict = defaultdict(set)
    scored = []
    for m in rows:
        key = (comps[m.competition_id], m.season)
        c = by[key]
        c["matches"] += 1
        teams[key].update((m.home_team_id, m.away_team_id))
        if m.status != MatchStatus.FINISHED or m.home_score is None or m.away_score is None:
            c["not_finished_or_unscored"] += 1
            continue
        c["finished_scored"] += 1
        c["home_win" if m.home_score > m.away_score else "draw" if m.home_score == m.away_score else "away_win"] += 1
        c["venue_populated"] += bool(m.venue)
        lo, hi = span.get(key, (m.utc_date, m.utc_date))
        span[key] = (min(lo, m.utc_date), max(hi, m.utc_date))
        scored.append((m.utc_date, comps[m.competition_id], m.home_team_id, m.away_team_id))
    table = []
    for key in sorted(by):
        c = by[key]
        n = c["finished_scored"]
        lo, hi = span.get(key, (None, None))
        table.append({"code": key[0], "season": key[1], "matches": c["matches"], "finished_scored": n,
                      "teams": len(teams[key]),
                      "from": lo.date().isoformat() if lo else None, "to": hi.date().isoformat() if hi else None,
                      "home_rate": c["home_win"] / n if n else None, "draw_rate": c["draw"] / n if n else None,
                      "away_rate": c["away_win"] / n if n else None,
                      "venue_populated": c["venue_populated"] / n if n else None})
    first_unl: dict = {}
    for t, code, h, a in scored:
        if code == "UNL":
            for tid in (h, a):
                first_unl.setdefault(tid, t)
    prior = Counter()
    for t, code, h, a in scored:
        for tid in (h, a):
            if tid in first_unl and t < first_unl[tid]:
                prior[tid] += 1
    hist = Counter()
    for tid in first_unl:
        n = prior.get(tid, 0)
        hist["0" if n == 0 else "1-9" if n < 10 else "10-29" if n < 30 else "30+"] += 1
    return {"competitions_found": sorted(set(comps.values())), "table": table,
            "unl_teams": len(first_unl), "unl_teams_prior_history": dict(hist),
            "total_scored": len(scored)}
