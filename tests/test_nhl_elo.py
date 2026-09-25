"""NHL Elo v1: MOV + per-team season regression only, parameters a priori."""
import math
from datetime import datetime, timedelta

import pytest

from src.models.nhl_elo import NHLEloConfig, NHLEloV1, home_advantage_from_rate
from src.walters import nhl_backtest as nb


def G(h, a, season, hs, as_, i=0):
    return nb.Game(h, a, season, datetime(int(season), 11, 1) + timedelta(hours=i), hs, as_)


def test_frozen_parameters():
    c = NHLEloConfig()
    assert (c.k_factor, c.mov_base, c.season_regression, c.default_rating) == (6.0, 2.2, 0.25, 1500.0)


def test_home_advantage_reproduces_home_rate():
    ha = home_advantage_from_rate(0.54)
    m = NHLEloV1(NHLEloConfig(home_advantage=ha))
    assert m.predict(G(1, 2, "2024", 0, 0)) == pytest.approx(0.54)
    assert home_advantage_from_rate(0.5) == pytest.approx(0.0)


def test_updates_are_zero_sum_and_mov_scales():
    one, three = NHLEloV1(), NHLEloV1()
    one.update(G(1, 2, "2024", 2, 1))
    three.update(G(1, 2, "2024", 4, 1))
    assert one.rating(1) - 1500 == pytest.approx(1500 - one.rating(2))
    gain1, gain3 = one.rating(1) - 1500, three.rating(1) - 1500
    assert gain3 / gain1 == pytest.approx(math.log(4) / math.log(2))


def test_ot_so_win_counts_as_one_goal_win():
    m = NHLEloV1()
    m.update(G(1, 2, "2024", 3, 2))           # e.g. AOT/AP final 3-2
    assert m.rating(1) > 1500 > m.rating(2)


def test_per_team_regression_at_its_first_new_season_game():
    m = NHLEloV1()
    m._ratings.update({1: 1600.0, 2: 1400.0, 3: 1500.0})
    m._last_season.update({1: "2024", 2: "2024", 3: "2024"})
    p = m.predict(G(1, 3, "2025", 0, 0))      # team 1's first 2025 game
    assert m.rating(1) == pytest.approx(1575.0)   # 25% toward 1500
    assert m.rating(2) == pytest.approx(1400.0)   # hasn't played 2025 yet
    assert p == pytest.approx(1 / (1 + 10 ** ((1500 - 1575) / 400)))
    m.update(G(1, 3, "2025", 1, 0))
    before = m.rating(1)
    m.predict(G(1, 3, "2025", 0, 0, i=1))     # second 2025 game: no re-regression
    assert m.rating(1) == before


def test_elo_v1_beats_baseline_on_a_signal_stream():
    """Synthetic league with real strength gaps: the gate machinery + Elo v1
    produce a sane, passing read (plumbing receipt, not an accuracy claim)."""
    import random
    rnd = random.Random(7)
    strength = {t: 1500 + 40 * (t - 8) for t in range(16)}      # 1180..1780 true
    games, i = [], 0
    for season in ("2024", "2025"):
        for _ in range(1400):
            h, a = rnd.sample(range(16), 2)
            p = 1 / (1 + 10 ** ((strength[a] - strength[h] - 30) / 400))
            hw = rnd.random() < p
            margin = rnd.choice([1, 1, 1, 2, 2, 3])
            games.append(nb.Game(h, a, season, datetime(int(season), 10, 20) + timedelta(hours=i),
                                 (margin if hw else 0) + 1, (0 if hw else margin) + 1))
            i += 1
    st = nb.build_stream(games)
    base = nb.baselines(st)
    model = NHLEloV1(NHLEloConfig(home_advantage=home_advantage_from_rate(base.home_rate)))
    r = nb.run_gate(st, model)
    assert r.ll_model < r.ll_home < r.ll_const + 0.01
    assert r.crit_ll and r.crit_spread
