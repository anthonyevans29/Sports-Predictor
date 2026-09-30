"""#88 RULED (architect 2026-09-30): Kalshi rounds the fee per FILL, not per
contract. Model: order fee = ceil(N x rate x M x P(1-P) x 100) / 100; the Desk
prices an order of K_ORDER_CONTRACTS (provisional 10). The receipt script
reproduces multi-contract fills' fees from the CSV to the cent."""
from src.walters import venue
from scripts import kalshi_fee_fill_receipt as rcpt

HDR = ("subtrader_id,type,quantity_fp,market_ticker,side,entry_price_dollars,exit_price_dollars,"
       "open_fees_dollars,close_fees_dollars,realized_pnl_without_fees_dollars,"
       "realized_pnl_with_fees_dollars,close_timestamp,open_timestamp,product,period_start,market_title")


def test_order_fee_is_one_ceiling_per_fill():
    assert venue.K_ORDER_CONTRACTS == 10
    assert venue.kalshi_order_fee(0.60, 8) == 0.14          # 8 x 1.68c = 13.44c -> 14c (per contract: 8 x 2c = 16c)
    assert venue.kalshi_order_fee(0.60, 1) == 0.02
    assert venue.kalshi_order_fee(0.60, 10, 0.25, venue.KALSHI_MAKER_RATE) == 0.02   # 1.05c -> 2c
    assert venue.kalshi_order_fee(0.60, 0) is None and venue.kalshi_order_fee(None, 5) is None
    # maker within ~0.1c of exact at N=10 (the ruling's point): exact 0.105c/contract
    assert abs(venue.kalshi_fee(0.60, 0.25, venue.KALSHI_MAKER_RATE) - 0.0175 * 0.25 * 0.24) < 0.001
    assert venue.kalshi_exec(0.55, 0.58, "NFL")["fee_order_contracts"] == 10


def _csv(tmp_path, rows):
    p = tmp_path / "Kalshi.csv"
    lines = [HDR]
    for t, q, en, ex, of, cf in rows:
        lines.append(f'sub-1,trade,{q:.2f},{t},yes,{en:.8f},{ex:.8f},{of:.8f},{cf:.8f},0,0,'
                     f'2026-09-28T18:00:00-05:00,2026-09-27T07:00:00-05:00,predictions,2026-09-01,"x"')
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_receipt_reproduces_multi_contract_fills_to_the_cent(tmp_path, capsys):
    rows = [
        ("KXNFLGAME-26SEP28BUFKC-KC", 8, 0.60, 1.0, 0.14, 0.0),     # taker per fill 13.44c -> 14c (old model 16c)
        ("KXNFLGAME-26SEP28BUFKC-BUF", 10, 0.45, 0.0, 0.18, 0.0),   # 17.33c -> 18c (old 20c)
        ("KXMLBGAME-26SEP27NYYBOS-NYY", 20, 0.55, 1.0, 0.18, 0.0),  # MLB pre-live M=0.5: 17.33c -> 18c
        ("KXNHLGAME-26OCT07BOSFLA-FLA", 25, 0.50, 1.0, 0.03, 0.0),  # maker M=0.25: 25 x 0.109c = 2.73c -> 3c
        ("KXEPLGAME-26SEP27ARSCHE-TIE", 6, 0.25, 0.40, 0.08, 0.05),  # open taker 7.9c -> 8c; close sale 6 @ 0.40: fee 0.05 fits neither model (a miss)
        ("KXNCAAFGAME-26SEP27AUBALA-ALA", 1, 0.49, 0.0, 0.02, 0.0),  # single contract: not multi, skipped
        ("KXWNBAGAME-26SEP27LVANYL-LV", 5, 0.50, 1.0, 0.09, 0.0),    # no ruled M: skipped, never guessed
    ]
    rc = rcpt.main(["--csv", _csv(tmp_path, rows)])
    out = capsys.readouterr().out
    assert "series without a ruled M (skipped, never guessed): 1" in out
    assert "per-FILL model reproduces 5/6 to the cent · old per-contract model 0/6" in out
    assert "OK   KXNFLGAME-26SEP28BUFKC-KC open 8 @ 0.60: fee $0.14 = taker ceil -> $0.14 (per-contract model $0.16)" in out
    assert "MISS KXEPLGAME-26SEP27ARSCHE-TIE close 6 @ 0.40" in out
    assert "RECEIPT: 5/5 multi-contract fills reproduced to the cent — MEETS the #88 receipt" in out and rc == 0


def test_receipt_refuses_an_unknown_header(tmp_path, capsys):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n")
    assert rcpt.main(["--csv", str(p)]) == 2
    assert "REFUSED: column(s) not found" in capsys.readouterr().out
