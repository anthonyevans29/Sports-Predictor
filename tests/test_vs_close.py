"""The record against the close (ARCHITECT 2026-10-13, addendum 63 item 3): the shared helper every family uses."""
import math

import pytest

from src.walters import vs_close as vc


def test_no_game_has_every_key_and_no_figure():
    b = vc.block([])
    assert b == {"games": 0, "model_log_loss": None, "close_log_loss": None, "close_minus_model": None, "ci95": None,
                 "model_beat_close": 0, "resamples": 10_000, "seed": 20261013}
    assert vc.line(b) == "vs close: no decided game with a close"


def test_the_figures_are_the_means_and_close_minus_model_is_positive_when_the_model_is_ahead():
    pairs = [(0.7, 0.6), (0.4, 0.5), (0.8, 0.6)]
    b = vc.block(pairs)
    lm = [-math.log(m) for m, _ in pairs]
    lc = [-math.log(c) for _, c in pairs]
    assert b["games"] == 3
    assert b["model_log_loss"] == round(sum(lm) / 3, 4)
    assert b["close_log_loss"] == round(sum(lc) / 3, 4)
    assert b["close_minus_model"] == round(sum(c - m for m, c in zip(lm, lc)) / 3, 4)
    assert b["close_minus_model"] > 0
    assert b["model_beat_close"] == 2            # the 0.4-vs-0.5 game is the close's


def test_a_tie_is_not_a_beat():
    assert vc.block([(0.6, 0.6), (0.6, 0.6)])["model_beat_close"] == 0


def test_the_floor_is_1e_12():
    assert vc.log_loss(0.0) == pytest.approx(-math.log(1e-12))
    assert vc.block([(0.0, 0.5)])["model_log_loss"] == round(-math.log(1e-12), 4)


def test_the_interval_is_seeded_and_holds_the_mean():
    pairs = [(0.55 + 0.01 * (i % 7), 0.5 + 0.01 * (i % 5)) for i in range(40)]
    a, b = vc.block(pairs), vc.block(pairs)
    assert a["ci95"] == b["ci95"] and len(a["ci95"]) == 2
    lo, hi = a["ci95"]
    assert lo <= a["close_minus_model"] <= hi
    assert vc.block(pairs, seed=1)["ci95"] != a["ci95"]       # the seed is what pins it


def test_one_game_has_no_interval():
    b = vc.block([(0.6, 0.5)])
    assert b["games"] == 1 and b["ci95"] is None
    assert "no interval under two games" in vc.line(b)
    assert vc.line(b).startswith("vs close: 1 game · ")


def test_the_line_prints_every_figure():
    b = {"games": 46, "model_log_loss": 0.6104, "close_log_loss": 0.6419, "close_minus_model": 0.0315,
         "ci95": [-0.029, 0.091], "model_beat_close": 26, "resamples": 10_000, "seed": 20261013}
    assert vc.line(b) == ("vs close: 46 games · model 0.6104 · close 0.6419 · close − model +0.0315 (95% -0.0290 to "
                          "+0.0910, 10,000 resamples, seed 20261013) · model beat the close 26/46")


def test_ten_thousand_resamples_of_a_season_are_quick():
    import time
    pairs = [(0.5 + (i % 9) / 100, 0.5 + (i % 11) / 100) for i in range(2500)]
    t = time.perf_counter()
    b = vc.block(pairs)
    assert b["ci95"] is not None
    assert time.perf_counter() - t < 10


# ---- rows as the exports write them -------------------------------------------------------------------------------

def _row(result, close, *, home=0.6, draw=None, away=None, push=False, hs=None, aw=None):
    pred = {"home_win_prob": home}
    if draw is not None or away is not None:
        pred.update({"draw_prob": draw, "away_win_prob": away})
    return {"predicted": pred, "actual": {"result": result, "home_score": hs, "away_score": aw},
            "graded": {"push": push, "close_fair": close}}


def test_a_two_way_row_reads_the_away_side_as_one_minus_home():
    assert vc.pair_from_row(_row("A", {"HOME": 0.55, "AWAY": 0.45})) == (pytest.approx(0.4), 0.45)
    assert vc.pair_from_row(_row("H", {"HOME": 0.55, "AWAY": 0.45})) == (0.6, 0.55)


def test_a_push_a_tie_no_result_and_no_close_are_not_fed():
    assert vc.pair_from_row(_row("T", {"HOME": 0.5, "AWAY": 0.5}, push=True)) is None
    assert vc.pair_from_row(_row("T", {"HOME": 0.5, "AWAY": 0.5})) is None
    assert vc.pair_from_row(_row(None, {"HOME": 0.5, "AWAY": 0.5})) is None
    assert vc.pair_from_row(_row("H", None)) is None


def test_a_three_way_draw_reads_the_draw_legs():
    r = _row("D", {"HOME": 0.45, "DRAW": 0.29, "AWAY": 0.26}, home=0.5, draw=0.28, away=0.22)
    assert vc.pair_from_row(r) == (0.28, 0.29)


def test_a_draw_with_no_draw_probability_is_not_fed():
    r = _row("D", {"HOME": 0.45, "DRAW": 0.29, "AWAY": 0.26}, home=0.5, draw=None, away=0.22)
    assert vc.pair_from_row(r) is None


def test_a_null_result_on_a_scored_game_reads_the_scores():
    r = _row(None, {"HOME": 0.55, "AWAY": 0.45}, home=0.6, away=0.4, hs=2, aw=5)
    assert vc.pair_from_row(r) == (0.4, 0.45)


def test_block_from_rows_feeds_only_decided_rows_with_a_close():
    rows = [_row("H", {"HOME": 0.55, "AWAY": 0.45}), _row("A", None), _row("T", {"HOME": 0.5, "AWAY": 0.5}, push=True)]
    b = vc.block_from_rows(rows)
    assert b["games"] == 1 and b["model_beat_close"] == 1
