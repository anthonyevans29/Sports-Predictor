"""
Cup strength source (cup fix spec, architect 2026-09-25).

The cup path's Poisson attack/defense used to come from the cup's own
competition-season pool — n <= 2 per team, and (in exam mode) including the
priced match itself. This module replaces that for CUP/INTL competitions:

  1. AS-OF-DATE, LEAVE-SELF-OUT: every fit uses only matches that kicked off
     strictly before the fixture being priced. The priced match and any later
     match never enter any fit. (Live pricing already only sees prior games;
     this makes the exam measure the same thing.)
  2. DOMESTIC BORROW: each team's attack/defense is its DOMESTIC league-season
     fit (same season string as the cup fixture, as-of-date), blended toward
     its cup-season fit only as its cup n grows: weight n/(n+K), K = 5 frozen
     a priori — implemented as estimate_strengths' shrinkage target
     (prior=domestic), whose weight is exactly n/(n+5). Cup n = 0 -> pure
     domestic.
  3. RULING B: a team with no trained Elo rating, or no synced domestic
     league-season, is never priced — the fixture is market-only.

Domestic strengths are relative to the team's own league average; cross-
league strength is still Elo + league bonus's job (unchanged).
Pure except load_cup_strength_source.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from src.models.poisson import CompetitionScoringContext, TeamStrength, estimate_strengths

CUP_CONFIDENCE_K = 5  # frozen a priori (spec); == estimate_strengths' shrink constant


@dataclass(frozen=True)
class FitMatch:
    match_id: int
    home_id: int
    away_id: int
    home_score: int
    away_score: int
    utc_date: datetime


@dataclass(frozen=True)
class SideStrength:
    strength: TeamStrength
    dom_league: str
    dom_n: int      # the team's domestic matches in the as-of fit
    cup_n: int      # the team's cup matches in the as-of fit
    cup_w: float    # n/(n+K): weight on the cup-season fit


def _rows(ms: list[FitMatch]) -> list[dict]:
    return [{"home_team_id": m.home_id, "away_team_id": m.away_id,
             "home_score": m.home_score, "away_score": m.away_score} for m in ms]


def _n_by_team(ms: list[FitMatch]) -> Counter:
    c: Counter = Counter()
    for m in ms:
        c[m.home_id] += 1
        c[m.away_id] += 1
    return c


class CupStrengthSource:
    def __init__(self, cup_matches: list[FitMatch], cup_context: CompetitionScoringContext,
                 league_matches: dict[str, list[FitMatch]],
                 league_contexts: dict[str, CompetitionScoringContext],
                 team_league: dict[int, str], rated: set[int]):
        self.cup_matches = cup_matches
        self.cup_context = cup_context
        self.league_matches = league_matches
        self.league_contexts = league_contexts
        self.team_league = team_league
        self.rated = rated
        self._dom_cache: dict[tuple[str, datetime], tuple[dict, Counter, set]] = {}

    @staticmethod
    def _before(ms: list[FitMatch], as_of: datetime) -> list[FitMatch]:
        return [m for m in ms if m.utc_date < as_of]

    def _domestic(self, code: str, as_of: datetime):
        key = (code, as_of)
        if key not in self._dom_cache:
            pool = self._before(self.league_matches.get(code, []), as_of)
            ctx = self.league_contexts.get(code, CompetitionScoringContext())
            self._dom_cache[key] = (estimate_strengths(_rows(pool), ctx), _n_by_team(pool),
                                    {m.match_id for m in pool})
        return self._dom_cache[key]

    def market_only_reason(self, home_id: int, away_id: int) -> str | None:
        for side, tid in (("home", home_id), ("away", away_id)):
            if tid not in self.rated:
                return f"{side} team unrated (no trained Elo)"
            if tid not in self.team_league:
                return f"{side} team has no synced domestic league-season"
        return None

    def for_fixture(self, home_id: int, away_id: int, as_of: datetime):
        """(home SideStrength, away SideStrength, receipts) — or a market-only
        reason string (ruling B)."""
        why = self.market_only_reason(home_id, away_id)
        if why:
            return why
        prior, dom_n, used_ids = {}, {}, set()
        for tid in (home_id, away_id):
            code = self.team_league[tid]
            fit, n, ids = self._domestic(code, as_of)
            prior[tid] = fit.get(tid, TeamStrength(attack=1.0, defense=1.0))
            dom_n[tid] = n.get(tid, 0)
            used_ids |= ids
        cup_pool = self._before(self.cup_matches, as_of)
        blended = estimate_strengths(_rows(cup_pool), self.cup_context, prior=prior)
        cup_n = _n_by_team(cup_pool)
        used_ids |= {m.match_id for m in cup_pool}
        sides = []
        for tid in (home_id, away_id):
            n = cup_n.get(tid, 0)
            # n == 0: the team is absent from the cup fit -> pure domestic prior
            st = blended.get(tid, prior[tid])
            sides.append(SideStrength(st, self.team_league[tid], dom_n[tid], n,
                                      n / (n + CUP_CONFIDENCE_K)))
        return sides[0], sides[1], {"cup_pool_n": len(cup_pool), "used_ids": used_ids}


def load_cup_strength_source(s, comp, season: str, contexts: dict,
                             rated: set[int]) -> CupStrengthSource:
    """Read-only DB load: the cup's finished matches this season, every
    LEAGUE-typed soccer competition's finished matches this season, and each
    team's domestic league (the league it has the most fixtures in this
    season, any status — membership doesn't wait for a first result)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, Sport

    def fm(m) -> FitMatch:
        return FitMatch(m.id, m.home_team_id, m.away_team_id, m.home_score, m.away_score, m.utc_date)

    scored = (Match.status == MatchStatus.FINISHED, Match.home_score.is_not(None),
              Match.away_score.is_not(None))
    cup = [fm(m) for m in s.execute(select(Match).where(
        Match.competition_id == comp.id, Match.season == season, *scored)).scalars()]

    leagues = {c.id: c.code for c in s.execute(select(Competition).where(
        Competition.sport == Sport.SOCCER, Competition.type == "LEAGUE")).scalars()}
    league_matches: dict[str, list[FitMatch]] = {}
    fixtures: dict[int, Counter] = {}
    for m in s.execute(select(Match).where(
            Match.competition_id.in_(list(leagues)), Match.season == season)).scalars():
        code = leagues[m.competition_id]
        for tid in (m.home_team_id, m.away_team_id):
            fixtures.setdefault(tid, Counter())[code] += 1
        if (m.status == MatchStatus.FINISHED and m.home_score is not None
                and m.away_score is not None):
            league_matches.setdefault(code, []).append(fm(m))
    team_league = {tid: c.most_common(1)[0][0] for tid, c in fixtures.items()}
    return CupStrengthSource(
        cup, contexts.get(comp.code, CompetitionScoringContext()), league_matches,
        {code: contexts.get(code, CompetitionScoringContext()) for code in league_matches},
        team_league, rated)
