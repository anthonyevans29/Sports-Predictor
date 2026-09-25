"""NHL candidate v3: params selected by walk-forward validation inside 2024."""
import random
from datetime import datetime, timedelta

import pytest

from src.models.nhl_elo import NHLEloConfigV2, NHLEloV2, NHLEloV3
from src.walters import nhl_backtest as nb

SMALL = {"k_factor": (3.0, 8.0), "mov_base": (1.0,), "home_advantage": (35.0,),
         "b2b_penalty": (0.0, 30.0), "rest_per_day": (0.0,)}


def _world(seed=1, test_seed=None, n=700):
    rnd = random.Random(seed)
    true = {t: 1500 + 35 * (t - 8) for t in range(16)}
    games = []
    for season, start in (("2024", datetime(2024, 10, 8)), ("2025", datetime(2025, 10, 7))):
        r = rnd if season == "2024" or test_seed is None else random.Random(test_seed)
        t = start
        for _ in range(n):
            h, a = r.sample(range(16), 2)
            hw = r.random() < 1 / (1 + 10 ** ((true[a] - true[h] - 30) / 400))
            games.append(nb.Game(h, a, season, t, 3 if hw else 1, 1 if hw else 3))
            t += timedelta(hours=r.choice([3, 5, 8]))
    return nb.build_stream(nb.attach_rest(games))


def test_grid_frozen_superset_of_v2_nothing_above_old_maxima():
    assert nb.V3_GRID == {
        "k_factor": (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0),
        "mov_base": (0.5, 1.0, 1.6, 2.2, 3.0, 4.0),
        "home_advantage": (15.0, 25.0, 35.0, 45.0, 55.0),
        "b2b_penalty": (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0),
        "rest_per_day": (0.0, 2.5, 5.0, 7.5, 10.0),
    }
    for k, old in nb.V2_GRID.items():
        assert set(old) <= set(nb.V3_GRID[k])                 # every v2 value kept
        assert max(nb.V3_GRID[k]) == max(old)                 # nothing above the old max
        assert list(nb.V3_GRID[k]) == sorted(nb.V3_GRID[k])   # simplest-first ordering


def test_split_is_chronological_60_40_and_disjoint():
    st = _world()
    fit, val = nb.validation_split(list(reversed(st.train)))  # order-independent input
    assert len(fit) == int(len(st.train) * 0.6) and len(fit) + len(val) == len(st.train)
    assert max(g.utc_date for g in fit) < min(g.utc_date for g in val)
    assert not set(map(id, fit)) & set(map(id, val))


def test_validation_results_never_enter_the_fit():
    """The ratings entering validation depend on fit games only: rewriting every
    validation result leaves the first validation price unchanged."""
    st = _world()
    fit, val = nb.validation_split(st.train)
    flipped = [nb.Game(g.home_id, g.away_id, g.season, g.utc_date, g.away_score, g.home_score,
                       g.stage, g.home_rest_h, g.away_rest_h) for g in val]
    cfg = NHLEloConfigV2(k_factor=6, home_advantage=35)
    m1, m2 = NHLEloV2(cfg), NHLEloV2(cfg)
    for g in fit:
        m1.update(g); m2.update(g)
    assert m1.predict(val[0]) == m2.predict(flipped[0])
    # ...but the validation LOSS does see the validation results
    assert nb.validation_loss(fit, val, NHLEloV2(cfg)) != nb.validation_loss(fit, flipped, NHLEloV2(cfg))


def test_selection_scores_validation_only_and_never_sees_2025():
    a, b = _world(test_seed=100), _world(test_seed=999)       # same 2024, different 2025
    best_a, rows_a, (fit, val) = nb.tune_v3(a.train, SMALL)
    best_b, _, _ = nb.tune_v3(b.train, SMALL)
    assert best_a == best_b and len(rows_a) == 4
    loss, params = rows_a[0]
    assert loss == pytest.approx(nb.validation_loss(fit, val, NHLEloV2(NHLEloConfigV2(**params))))


def test_v3_model_is_v2_form_under_a_new_name():
    cfg = NHLEloConfigV2(k_factor=5, b2b_penalty=10)
    g = nb.Game(1, 2, "2024", datetime(2024, 11, 1), 3, 2, home_rest_h=24.0, away_rest_h=72.0)
    assert NHLEloV3(cfg).predict(g) == NHLEloV2(cfg).predict(g)
    assert NHLEloV3.name == "nhl_elo_v3"
