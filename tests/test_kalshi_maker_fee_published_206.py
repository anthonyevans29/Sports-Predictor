"""P0-1 (#206, external review 2026-10-01): the maker fee from Kalshi's
PUBLISHED schedule, not from the implementation. The schedule prices C
contracts at P as roundup(rate x M x C x P x (1-P)), taker rate 0.07, maker
rate 0.0175 (= 0.25 x taker): the maker discount is the rate, never a second
M. Game series M = 1; MLB pre-live M = 0.5. The fixtures are the schedule's
own dollar figures for 100 contracts; the schedule rounds UP, so they are
checked with rounding="ceil" (our per-fill NEAREST, #134, agrees where
noted)."""
import pytest

from src.walters import venue

GAME = ("KXNFLGAME", "KXNHLGAME", "KXNCAAFGAME", "KXEPLGAME")


def fee(series, side, price, n=100, rounding="ceil"):
    mt, mm = venue.KALSHI_FEE_M[series]
    m, rate = (mt, venue.KALSHI_FEE_RATE) if side == "taker" else (mm, venue.KALSHI_MAKER_RATE)
    return venue.kalshi_order_fee(price, n, m, rate, rounding=rounding)


@pytest.mark.parametrize("series", GAME)
def test_game_series_maker_100_at_50c_is_44_cents(series):
    assert fee(series, "maker", 0.50) == 0.44                     # the published $0.44
    assert fee(series, "maker", 0.50, rounding="nearest") == 0.44  # 43.75c -> 44c either way


@pytest.mark.parametrize("series", GAME)
def test_game_series_taker_100_at_50c_is_1_75(series):
    assert fee(series, "taker", 0.50) == 1.75


@pytest.mark.parametrize("series", GAME)
def test_maker_is_a_quarter_of_taker(series):
    for p in (0.10, 0.30, 0.50, 0.70, 0.90):
        raw = lambda side: fee(series, side, p, n=10_000, rounding="nearest")   # big n: rounding negligible
        assert raw("maker") == pytest.approx(raw("taker") * 0.25, abs=0.01)


def test_mlb_pre_live_published_range_per_100():
    # taker $0.04-$0.88, maker $0.01-$0.22 per 100 contracts (P from 1c to 50c)
    assert (fee("KXMLBGAME", "taker", 0.01), fee("KXMLBGAME", "taker", 0.50)) == (0.04, 0.88)
    assert (fee("KXMLBGAME", "maker", 0.01), fee("KXMLBGAME", "maker", 0.50)) == (0.01, 0.22)


def test_the_double_count_is_gone():
    """The pre-#206 table charged NFL maker 0.0175 x 0.25: $0.11 per 100 @ 50c."""
    assert fee("KXNFLGAME", "maker", 0.50) != 0.11
    assert venue.kalshi_order_fee(0.50, 100, 0.25, venue.KALSHI_MAKER_RATE, rounding="ceil") == 0.11
