"""Cup strength source (cup fix spec 2026-09-25), pure: two synthetic leagues."""
from datetime import datetime, timedelta

import pytest

from src.models.cup_strengths import CUP_CONFIDENCE_K, CupStrengthSource, FitMatch
from src.models.poisson import CompetitionScoringContext, TeamStrength, estimate_strengths

T0 = datetime(2026, 8, 1, 15)
CTX = CompetitionScoringContext()


def fm(mid, h, a, hs, as_, day):
    return FitMatch(mid, h, a, hs, as_, T0 + timedelta(days=day))


def _world(cup=()):
    # League A: team 1 scores freely vs filler 9. League B: team 2 concedes a lot vs filler 8.
    league_a = [fm(100 + i, 1, 9, 3, 0, i) for i in range(6)]
    league_b = [fm(200 + i, 8, 2, 3, 1, i) for i in range(6)]
    return CupStrengthSource(list(cup), CTX, {"A": league_a, "B": league_b},
                             {"A": CTX, "B": CTX}, {1: "A", 9: "A", 2: "B", 8: "B"},
                             rated={1, 2, 8, 9})


def test_cup_n_zero_is_pure_domestic_as_of():
    src = _world()
    as_of = T0 + timedelta(days=3, hours=1)            # after league day 3 only
    home, away, info = src.for_fixture(1, 2, as_of)
    a_fit = estimate_strengths([{"home_team_id": 1, "away_team_id": 9, "home_score": 3,
                                 "away_score": 0}] * 4, CTX)
    assert home.dom_league == "A" and home.dom_n == 4 and home.cup_n == 0 and home.cup_w == 0.0
    assert home.strength == a_fit[1]
    assert away.dom_league == "B" and away.dom_n == 4
    assert info["cup_pool_n"] == 0 and info["used_ids"] == {100, 101, 102, 103, 200, 201, 202, 203}


def test_blend_weight_is_n_over_n_plus_5_toward_domestic():
    cup = [fm(300, 1, 2, 0, 4, 10), fm(301, 2, 1, 1, 0, 12)]   # team 1 poor in the cup
    src = _world(cup)
    home, _, _ = src.for_fixture(1, 2, T0 + timedelta(days=20))
    dom = src._domestic("A", T0 + timedelta(days=20))[0][1]
    raw_att = ((0 / CTX.home_field_goal_boost) + 0) / 2 / CTX.avg_goals_per_team_per_match
    w = 2 / (2 + CUP_CONFIDENCE_K)
    assert home.cup_n == 2 and home.cup_w == pytest.approx(w)
    assert home.strength.attack == pytest.approx(max(0.25, w * raw_att + (1 - w) * dom.attack))


def test_strictly_before_kickoff():
    cup = [fm(300, 1, 2, 5, 0, 10)]
    src = _world(cup)
    kick = T0 + timedelta(days=10)                     # the cup game's own kickoff
    home, _, info = src.for_fixture(1, 2, kick)
    assert 300 not in info["used_ids"] and home.cup_n == 0
    assert info["used_ids"] == set(range(100, 106)) | set(range(200, 206))  # all league days 0-5


def test_ruling_b_reasons():
    src = _world()
    src.rated.discard(2)
    assert src.for_fixture(1, 2, T0) == "away team unrated (no trained Elo)"
    src = _world()
    src.rated.add(77)
    assert src.for_fixture(77, 1, T0) == "home team has no synced domestic league-season"


def test_prior_none_is_byte_identical_to_the_old_fit():
    rows = [{"home_team_id": 1, "away_team_id": 2, "home_score": 2, "away_score": 1}] * 3
    assert estimate_strengths(rows, CTX) == estimate_strengths(rows, CTX, prior=None)
    shifted = estimate_strengths(rows, CTX, prior={1: TeamStrength(2.0, 0.5)})
    assert shifted[1] != estimate_strengths(rows, CTX)[1]
    assert shifted[2] == estimate_strengths(rows, CTX)[2]   # no prior for team 2 -> 1.0 target
