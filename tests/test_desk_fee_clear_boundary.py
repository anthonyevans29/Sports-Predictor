"""ARCHITECT 2026-10-06: an exact 4.00pp exec edge clears the Desk's K2 marker. (0.35 - 0.31) * 100 is
3.9999999999999982 in binary floats, which the unguarded `>= 4` read as a miss."""
from src.walters import desk_policy as D


def test_exact_four_point_edge_clears(monkeypatch):
    monkeypatch.setattr(D, "desk_cost_for", lambda r, side: {"cost": 0.31, "basis": "taker"})
    monkeypatch.setattr(D, "join_bid_for", lambda r, side: None)
    monkeypatch.setattr(D, "exec_cost_for", lambda r, side: 0.31)
    monkeypatch.setattr(D, "k_side", lambda r, side: {"no": False})
    r = {"kExec": {"cost": 0.31, "ask": 0.30, "maker": None}}
    blk = D.exec_block(r, "HOME", 0.35)
    assert blk["edge_pp"] < 4.0 and abs(blk["edge_pp"] - 4.0) < 1e-9
    assert blk["fee_clears"] is True
    under = D.exec_block(r, "HOME", 0.3499)                       # a real 3.99pp edge still misses
    assert under["fee_clears"] is False
