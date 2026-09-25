"""NHL candidate v2: rest days (the one new feature), tuning on 2024 only."""
import random
from datetime import datetime, timedelta

import pytest

from src.models.nhl_elo import (NHLEloConfig, NHLEloConfigV2, NHLEloV1, NHLEloV2,
                                rest_adjustment)
from src.walters import nhl_backtest as nb


def G(h, a, season, dt, hs=3, as_=2, stage=""):
    return nb.Game(h, a, season, dt, hs, as_, stage)


def test_rest_hours_include_preseason_and_beat_the_utc_date_trap():
    games = [
        G(1, 2, "2024", datetime(2024, 10, 5, 23), stage="Pre Season"),   # preseason
        G(1, 3, "2024", datetime(2024, 10, 8, 23)),                       # 7pm ET
        G(4, 1, "2024", datetime(2024, 10, 10, 2)),                       # next night 7pm PT
    ]
    out = nb.attach_rest(games)
    assert out[0].home_rest_h is None                     # no earlier game
    assert out[1].home_rest_h == pytest.approx(72.0)      # rest counted from preseason
    # 27h apart but on UTC dates two days apart: still a back-to-back
    assert out[2].away_rest_h == pytest.approx(27.0)
    assert rest_adjustment(out[2].away_rest_h, 30, 10) == -30


def test_rest_adjustment_boundaries():
    f = lambda h: rest_adjustment(h, 30.0, 10.0)
    assert [f(35.9), f(36), f(59.9), f(60), f(84), f(119.9), f(120), f(None)] == \
           [-30, 0, 0, 10, 20, 20, 20, 20]


def test_v2_with_rest_off_equals_v1_exactly():
    rnd = random.Random(3)
    games = nb.attach_rest([G(rnd.randrange(8), 8 + rnd.randrange(8), "2024",
                              datetime(2024, 10, 20) + timedelta(hours=13 * i),
                              rnd.randrange(6), rnd.randrange(6)) for i in range(300)])
    games = [g for g in games if g.home_score != g.away_score]
    v1 = NHLEloV1(NHLEloConfig(k_factor=8, mov_base=1.0, home_advantage=35))
    v2 = NHLEloV2(NHLEloConfigV2(k_factor=8, mov_base=1.0, home_advantage=35))
    for g in games:
        assert v2.predict(g) == pytest.approx(v1.predict(g), abs=1e-15)
        v1.update(g); v2.update(g)
    assert v2.ratings() == pytest.approx(v1.ratings())


def test_rest_sits_inside_expected_so_ratings_do_not_absorb_fatigue():
    t0 = datetime(2024, 11, 1)
    g = nb.Game(1, 2, "2024", t0, 1, 3, home_rest_h=24.0, away_rest_h=72.0)  # tired home loses
    plain, rested = NHLEloV2(NHLEloConfigV2()), NHLEloV2(NHLEloConfigV2(b2b_penalty=45, rest_per_day=10))
    assert rested.predict(g) < plain.predict(g)
    plain.update(g); rested.update(g)
    assert 1500 - rested.rating(1) < 1500 - plain.rating(1)   # smaller hit: loss was expected


def test_grid_is_frozen():
    assert nb.V2_GRID == {
        "k_factor": (4.0, 6.0, 8.0, 10.0),
        "mov_base": (1.0, 2.2, 4.0),
        "home_advantage": (15.0, 25.0, 35.0, 45.0, 55.0),
        "b2b_penalty": (0.0, 15.0, 30.0, 45.0),
        "rest_per_day": (0.0, 5.0, 10.0),
    }


def _world(seed, b2b_effect, test_seed=None):
    """16 clubs, true strengths, a real schedule with back-to-backs; the
    tired side's true rating drops by b2b_effect."""
    rnd = random.Random(seed)
    true = {t: 1500 + 35 * (t - 8) for t in range(16)}
    raw = []
    for season, start in (("2024", datetime(2024, 10, 8)), ("2025", datetime(2025, 10, 7))):
        r = rnd if season == "2024" or test_seed is None else random.Random(test_seed)
        t = start
        for _ in range(700):
            h, a = r.sample(range(16), 2)
            raw.append((h, a, season, t))
            t += timedelta(hours=r.choice([3, 5, 8]))
    games = []
    last = {}
    for h, a, season, t in raw:
        tired = {x: (x in last and (t - last[x]).total_seconds() < 36 * 3600) for x in (h, a)}
        rng = rnd if season == "2024" or test_seed is None else random.Random(hash((test_seed, t)))
        d = true[h] + 30 - true[a] - b2b_effect * tired[h] + b2b_effect * tired[a]
        hw = rng.random() < 1 / (1 + 10 ** (-d / 400))
        games.append(G(h, a, season, t, 3 if hw else 1, 1 if hw else 3))
        last[h] = last[a] = t
    return nb.build_stream(nb.attach_rest(games))


def test_tuning_never_sees_2025():
    a = _world(1, 40.0, test_seed=100)
    b = _world(1, 40.0, test_seed=999)            # identical 2024, different 2025
    assert [(g.home_score, g.away_score) for g in a.train] == \
           [(g.home_score, g.away_score) for g in b.train]
    assert [g.home_score for g in a.test] != [g.home_score for g in b.test]
    assert nb.tune_v2(a.train)[0] == nb.tune_v2(b.train)[0]


def test_tuning_recovers_a_planted_back_to_back_effect():
    best, rows = nb.tune_v2(_world(5, 60.0).train)
    assert best["b2b_penalty"] > 0
    assert len(rows) == 4 * 3 * 5 * 4 * 3 and rows[0][0] <= rows[-1][0]
