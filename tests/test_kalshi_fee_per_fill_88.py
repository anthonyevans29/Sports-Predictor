"""#88 RULED (architect 2026-09-30): Kalshi rounds the fee per FILL, not per
contract; the Desk prices an order of K_ORDER_CONTRACTS (provisional 10).
RE-FIT (same day): the ceiling receipt was NOT met, so the per-fill rounding
rule is re-fitted over the full CSV (ceil / nearest / floor / bankers) and
adopted only at >= 95%."""
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


def test_round_cents_modes():
    r = venue.round_cents
    assert [r(17.33, m) for m in venue.ROUNDING_MODES] == [18, 17, 17, 17]
    assert [r(17.5, m) for m in venue.ROUNDING_MODES] == [18, 18, 17, 18]     # half: up / up / down / to even
    assert [r(16.5, m) for m in venue.ROUNDING_MODES] == [17, 17, 16, 16]
    assert [r(17.0, m) for m in venue.ROUNDING_MODES] == [17, 17, 17, 17]
    assert venue.KALSHI_FEE_ROUNDING == "ceil"                                # in force until the re-fit names a rule
    assert venue.kalshi_order_fee(0.45, 10, rounding="floor") == 0.17         # 17.33c
    assert venue.kalshi_order_fee(0.45, 10) == 0.18


# (ticker, qty, entry, raw-generating rate/M) — fees are generated below under a chosen rule
LEGS = [("KXNFLGAME-26SEP28BUFKC-KC", 8, 0.60), ("KXNFLGAME-26SEP28BUFKC-BUF", 10, 0.45),
        ("KXNHLGAME-26OCT07BOSFLA-FLA", 25, 0.33), ("KXEPLGAME-26SEP27ARSCHE-TIE", 6, 0.27),
        ("KXNCAAFGAME-26SEP27AUBALA-ALA", 13, 0.41), ("KXNFLGAME-26OCT04LARSEA-SEA", 7, 0.52),
        ("KXNFLGAME-26OCT05DETGB-GB", 30, 0.50)]          # 52.5c exactly: nearest 53, bankers 52 (decides)


def _fees(rule):
    return [(t, q, p, 1.0, venue.round_cents(q * 0.07 * p * (1 - p) * 100, rule) / 100, 0.0) for t, q, p in LEGS]


def test_refit_adopts_the_rule_that_reproduces_the_full_set(tmp_path, capsys):
    rows = _fees("nearest") + [
        ("KXMVESPORTS-26OCT04-SHARD", 909.09, 0.001, 0.0, 0.01, 0.0),     # prints "@ 0.00": shard, out of the fit
        ("KXWNBAGAME-26SEP27LVANYL-LV", 5, 0.50, 1.0, 0.09, 0.0),          # no ruled M: never guessed
        ("KXNFLGAME-26SEP28BUFKC-KC", 1, 0.60, 1.0, 0.02, 0.0),            # single contract: not multi
    ]
    rc = rcpt.main(["--csv", _csv(tmp_path, rows)])
    out = capsys.readouterr().out
    assert "excluded: 1 priced 0.00 (combo-shard artifacts) · 1 series without a ruled M (never guessed) · IN THE FIT: 7" in out
    assert "    nearest      7/7  100.0%" in out
    assert "'nearest' reproduces 7/7 = 100.0% — MEETS (>= 95%). ADOPT: KALSHI_FEE_ROUNDING = \"nearest\"" in out
    assert "frac   down     up  other" in out and rc == 0


def test_refit_not_met_prints_the_residuals(tmp_path, capsys):
    rows = _fees("floor")[:3] + _fees("ceil")[3:]      # a mixed world: no rule reaches 95%
    rc = rcpt.main(["--csv", _csv(tmp_path, rows)])
    out = capsys.readouterr().out
    assert "NOT MET (< 95%). Residuals follow." in out and rc == 1
    assert "residual = fee - raw, cents, against the nearest candidate" in out
    assert "nearest candidate: taker 7" in out


def test_refit_indistinguishable_rules_adopt_the_first_and_flag_halves(tmp_path, capsys):
    rows = _fees("nearest")[:-1]           # no exact-half leg: nearest and bankers agree everywhere
    rc = rcpt.main(["--csv", _csv(tmp_path, rows)])
    out = capsys.readouterr().out
    assert ("ADOPT: KALSHI_FEE_ROUNDING = \"nearest\" (nearest ≡ bankers on this data: 0 exact-half legs"
            " — halves UNDETERMINED, ruled 2026-09-30)") in out and rc == 0


def test_refit_split_halves_are_not_met(tmp_path, capsys):
    # the same 17.5c raw rounded up once and down once: no single rule reproduces both
    rows = [("KXNFLGAME-26SEP28BUFKC-KC", 10, 0.50, 1.0, 0.18, 0.0),
            ("KXNFLGAME-26SEP28BUFKC-BUF", 10, 0.50, 1.0, 0.17, 0.0)]
    rc = rcpt.main(["--csv", _csv(tmp_path, rows)])
    out = capsys.readouterr().out
    assert "NOT MET (< 95%). Residuals follow." in out and "   .5x      1      1      0" in out and rc == 1


def test_receipt_refuses_an_unknown_header(tmp_path, capsys):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n")
    assert rcpt.main(["--csv", str(p)]) == 2
    assert "REFUSED: column(s) not found" in capsys.readouterr().out
