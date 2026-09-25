"""NHL candidate v4 — the last schedule-only candidate (architect, 2026-09-25)."""
from datetime import datetime

import pytest

from src.models.nhl_elo import NHLEloConfig, NHLEloV1, NHLEloV4
from src.walters import nhl_backtest as nb
from tests.test_nhl_v3 import _world


def test_grid_frozen_12_points_shrink_direction():
    assert nb.V4_GRID == {"k_factor": (3.0, 4.0, 5.0, 6.0),
                          "home_advantage": (35.0, 40.0, 45.0),
                          "mov_base": (2.2,)}
    n = 1
    for v in nb.V4_GRID.values():
        n *= len(v)
    assert n == 12
    assert max(nb.V4_GRID["k_factor"]) <= NHLEloConfig().k_factor          # never above v1's k
    assert all(list(v) == sorted(v) for v in nb.V4_GRID.values())         # smallest-first


def test_v4_is_the_v1_form_no_rest_terms():
    cfg = NHLEloConfig(k_factor=4, home_advantage=40)
    g = nb.Game(1, 2, "2024", datetime(2024, 11, 1), 3, 2, home_rest_h=20.0, away_rest_h=200.0)
    a, b = NHLEloV4(cfg), NHLEloV1(cfg)
    assert a.predict(g) == b.predict(g)          # rest hours are ignored entirely
    a.update(g); b.update(g)
    assert a.ratings() == b.ratings() and NHLEloV4.name == "nhl_elo_v4"


def test_v4_selection_is_walk_forward_and_never_sees_2025():
    a, b = _world(test_seed=100), _world(test_seed=999)
    best_a, rows, (fit, val) = nb.tune_v4(a.train)
    assert best_a == nb.tune_v4(b.train)[0] and len(rows) == 12
    loss, params = rows[0]
    assert set(params) == {"k_factor", "home_advantage", "mov_base"}
    assert loss == pytest.approx(nb.validation_loss(fit, val, NHLEloV4(NHLEloConfig(**params))))
