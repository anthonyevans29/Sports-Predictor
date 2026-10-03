"""P0-3 (#208): results rows carry q_close per side (close_block = the ruled close_1x2) so the Cockpit
can compute entry-price CLV on ledger positions; an unpriced or absent close is None, never inferred."""
from datetime import datetime, timedelta
from types import SimpleNamespace as O

from src.db.schema import Sport
from src.walters.close import close_block

KO = datetime(2026, 10, 4, 17, 0)


def odd(bk, sel, px, at):
    return O(market="1X2", bookmaker=bk, selection=sel, price_decimal=px, captured_at=at)


def test_close_block_is_the_ruled_close_per_side():
    at = KO - timedelta(hours=1)
    rows = [odd("a", "HOME", 1.8, at), odd("a", "AWAY", 2.1, at), odd("b", "HOME", 1.85, at), odd("b", "AWAY", 2.05, at),
            odd("a", "HOME", 1.5, KO + timedelta(minutes=5)), odd("a", "AWAY", 2.8, KO + timedelta(minutes=5))]
    b = close_block(rows, KO, Sport.NFL)
    assert set(b["close_fair"]) == {"HOME", "AWAY"} and abs(sum(b["close_fair"].values()) - 1) < 1e-3
    assert b["close_at"] == at.isoformat() and b["close_books"] == 2 and "close_1x2" in b["close_source"]
    assert b["close_fair"]["HOME"] > 0.5                       # the in-game 1.5 never counts


def test_unpriced_or_absent_close_is_none():
    at = KO - timedelta(hours=1)
    assert close_block([odd("a", "HOME", 1.8, at)], KO, Sport.NFL)["close_fair"] is None      # incomplete book
    assert close_block([], KO, Sport.NFL)["close_fair"] is None
