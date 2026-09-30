"""
#88 RECEIPT (architect ruling 2026-09-30): Kalshi rounds the fee per FILL,
not per contract. Reproduce multi-contract fills' fees from the Kalshi YTD
CSV to the cent with the per-fill model

    fee = ceil(N x rate x M x P(1-P) x 100) / 100     (N contracts, one ceiling)

beside the old per-contract model (N x ceil(rate x M x P(1-P) x 100) / 100).
Rates: taker 0.07, maker 0.0175; M from venue.KALSHI_FEE_M (the #93 ruling;
MLB pre-live 0.5, and MLB's live rate M=1 is also tried, labelled). Combos
(KXMVE...): taker at the schedule's default M=1, maker = 50% of taker. A
series outside the ruling is listed as "no M" and never guessed.

Every multi-contract leg with a fee (the open leg at the entry price; the
close leg only when it paid a fee, at the exit price) is checked. The
receipt the ruling asks for is five such fills reproduced to the cent.

    python3 scripts/kalshi_fee_fill_receipt.py --csv ~/Downloads/Kalshi-YTD.csv [--show 5]

Read-only: reads the CSV, writes nothing, no DB.
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.walters.venue import (KALSHI_FEE_M, KALSHI_FEE_RATE, KALSHI_MAKER_RATE,  # noqa: E402
                               kalshi_order_fee)

# The real export header (architect-confirmed 2026-09-27), the columns used here.
COLS = {"qty": "quantity_fp", "ticker": "market_ticker", "entry": "entry_price_dollars",
        "exit": "exit_price_dollars", "open_fee": "open_fees_dollars", "close_fee": "close_fees_dollars"}


def num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def candidates(ticker: str):
    """[(label, rate, M)] for this ticker's series, or [] when it has no ruled M."""
    series = ticker.split("-")[0].upper()
    if series.startswith("KXMVE"):
        return series, [("combo taker", KALSHI_FEE_RATE, 1.0), ("combo maker (50%)", KALSHI_FEE_RATE, 0.5)]
    if series not in KALSHI_FEE_M:
        return series, []
    mt, mm = KALSHI_FEE_M[series]
    out = [("taker", KALSHI_FEE_RATE, mt), ("maker", KALSHI_MAKER_RATE, mm)]
    if series == "KXMLBGAME":
        out.append(("taker LIVE rate (M=1)", KALSHI_FEE_RATE, 1.0))
    return series, out


def per_contract_old(price, qty, rate, m):
    one = kalshi_order_fee(price, 1, m, rate)
    return None if one is None else round(one * qty, 2)


def legs(rows):
    for r in rows:
        qty = num(r.get(COLS["qty"]))
        t = (r.get(COLS["ticker"]) or "").strip()
        if not t or not qty or qty <= 1:
            continue
        for leg, pk, fk in (("open", "entry", "open_fee"), ("close", "exit", "close_fee")):
            p, fee = num(r.get(COLS[pk])), num(r.get(COLS[fk]))
            if fee is None or fee <= 0 or p is None or not (0 < p < 1):
                continue
            yield {"ticker": t, "leg": leg, "qty": qty, "price": p, "fee": round(fee, 2)}


def check_leg(x):
    series, cands = candidates(x["ticker"])
    n = int(x["qty"]) if float(x["qty"]).is_integer() else x["qty"]
    res = []
    for label, rate, m in cands:
        model = kalshi_order_fee(x["price"], n, m, rate) if isinstance(n, int) else None
        if model is None:   # fractional contracts: same ceiling on the raw product
            model = math.ceil(x["qty"] * rate * m * x["price"] * (1 - x["price"]) * 100 - 1e-9) / 100
        res.append({"label": label, "per_fill": model, "per_contract_old": per_contract_old(x["price"], x["qty"], rate, m),
                    "match": abs(model - x["fee"]) < 0.005,
                    "old_match": abs((per_contract_old(x["price"], x["qty"], rate, m) or -1) - x["fee"]) < 0.005})
    return series, res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", required=True)
    ap.add_argument("--show", type=int, default=5, help="reproduced fills to print (default 5)")
    a = ap.parse_args(argv)
    with open(os.path.expanduser(a.csv), newline="") as f:
        rd = csv.DictReader(f)
        missing = [c for c in COLS.values() if c not in (rd.fieldnames or [])]
        if missing:
            print(f"REFUSED: column(s) not found: {', '.join(missing)} — headers seen: {rd.fieldnames}")
            return 2
        rows = list(rd)
    checked = reproduced = old_reproduced = no_m = 0
    shown, misses = [], []
    for x in legs(rows):
        series, res = check_leg(x)
        if not res:
            no_m += 1
            continue
        checked += 1
        hit = [r for r in res if r["match"]]
        if hit:
            reproduced += 1
            if len(shown) < a.show:
                shown.append((x, hit))
        else:
            misses.append((x, res))
        if any(r["old_match"] for r in res):
            old_reproduced += 1
    print(f"#88 FEE RECEIPT — {a.csv}: {len(rows)} rows · multi-contract legs with a fee: {checked + no_m}"
          f" · series without a ruled M (skipped, never guessed): {no_m}")
    print(f"  per-FILL model reproduces {reproduced}/{checked} to the cent · old per-contract model {old_reproduced}/{checked}")
    for x, hit in shown:
        h = hit[0]
        print(f"  OK   {x['ticker']} {x['leg']} {x['qty']:g} @ {x['price']:.2f}: fee ${x['fee']:.2f} = "
              f"{h['label']} ceil -> ${h['per_fill']:.2f} (per-contract model ${h['per_contract_old']:.2f})")
    for x, res in misses[:10]:
        alts = " · ".join(f"{r['label']} ${r['per_fill']:.2f}" for r in res)
        print(f"  MISS {x['ticker']} {x['leg']} {x['qty']:g} @ {x['price']:.2f}: fee ${x['fee']:.2f} vs {alts}")
    if len(misses) > 10:
        print(f"  … {len(misses) - 10} more misses")
    print(f"RECEIPT: {min(reproduced, 5)}/5 multi-contract fills reproduced to the cent"
          + (" — MEETS the #88 receipt" if reproduced >= 5 else " — SHORT of the #88 receipt"))
    return 0 if reproduced >= 5 else 1


if __name__ == "__main__":
    sys.exit(main())
