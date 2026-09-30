"""
#88 FEE-ROUNDING RE-FIT (architect 2026-09-30). The first receipt was NOT met:
253/629 multi-contract legs reproduced to the cent under the per-fill CEILING,
and the 376 misses were ~all exactly 1c BELOW the ceiling, which a ceiling
cannot produce. So the per-fill fee is not rounded up. This script scores
every candidate rounding rule over the FULL set and adopts one only if it
reproduces >= 95%:

    raw cents = N x rate x M x P(1-P) x 100          (one fill of N contracts)
    ceil · nearest (half up) · floor (truncate) · bankers (half to even)

Rates: taker 0.07, maker 0.0175; M from venue.KALSHI_FEE_M (the #93 ruling;
MLB pre-live 0.5, plus MLB's live rate M=1, labelled). Combos (KXMVE...):
taker at the default M=1, maker = 50% of taker. A leg is reproduced under a
rule when ANY of its candidates matches its fee to the cent. A series outside
the ruling is skipped, never guessed.

Population (as ruled): every multi-contract leg (qty > 1) that paid a fee.
The open leg is priced at the entry price; the close leg only when it paid a
fee, at the exit price. EXCLUDED from the fit: legs priced 0.00 (P < 0.005,
the combo-shard artifacts such as "909.09 @ 0.00"), counted and printed.

If no rule reaches 95%, the residual distribution is printed (fee - raw, in
cents, against the nearest candidate) together with a table of raw's
fractional cent vs whether Kalshi rounded down or up, so the true rule can
be read off. That table is printed in every case.

    python3 scripts/kalshi_fee_fill_receipt.py --csv ~/Downloads/Kalshi-YTD.csv

Read-only: reads the CSV, writes nothing, no DB.
"""
import argparse
import csv
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.walters.venue import (KALSHI_FEE_M, KALSHI_FEE_RATE, KALSHI_MAKER_RATE,  # noqa: E402
                               ROUNDING_MODES, round_cents)

# The real export header (architect-confirmed 2026-09-27), the columns used here.
COLS = {"qty": "quantity_fp", "ticker": "market_ticker", "entry": "entry_price_dollars",
        "exit": "exit_price_dollars", "open_fee": "open_fees_dollars", "close_fee": "close_fees_dollars"}
ADOPT_AT = 0.95
SHARD_PRICE = 0.005     # a price that prints as 0.00: combo-shard artifact, out of the fit


def num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def candidates(ticker: str):
    """(series, [(label, rate, M)]) — [] when the series has no ruled M."""
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


def legs(rows, counts):
    """Multi-contract legs with a fee; shard-priced legs counted, not yielded."""
    for r in rows:
        qty = num(r.get(COLS["qty"]))
        t = (r.get(COLS["ticker"]) or "").strip()
        if not t or not qty or qty <= 1:
            continue
        for leg, pk, fk in (("open", "entry", "open_fee"), ("close", "exit", "close_fee")):
            p, fee = num(r.get(COLS[pk])), num(r.get(COLS[fk]))
            if fee is None or fee <= 0 or p is None or p >= 1:
                continue
            if p < SHARD_PRICE:
                counts["shard"] += 1
                continue
            yield {"ticker": t, "leg": leg, "qty": qty, "price": p, "fee_c": round(fee * 100)}


def raw_cents(x, rate, m):
    return x["qty"] * rate * m * x["price"] * (1 - x["price"]) * 100.0


def score(xs):
    """Per rounding mode: legs reproduced (any candidate matches to the cent)."""
    hits = {mode: 0 for mode in ROUNDING_MODES}
    old = 0
    for x in xs:
        for mode in ROUNDING_MODES:
            if any(round_cents(raw_cents(x, rate, m), mode) == x["fee_c"] for _, rate, m in x["cands"]):
                hits[mode] += 1
        # the pre-#88 model: N x ceil(per-contract)
        if any(round(x["qty"] * math.ceil(rate * m * x["price"] * (1 - x["price"]) * 100 - 1e-9)) == x["fee_c"]
               for _, rate, m in x["cands"]):
            old += 1
    return hits, old


def nearest_candidate(x):
    """The candidate whose raw cents lie closest to the fee (the residual's anchor)."""
    return min(((label, raw_cents(x, rate, m)) for label, rate, m in x["cands"]),
               key=lambda lr: abs(x["fee_c"] - lr[1]))


def residuals(xs):
    hist, frac_tab, labels = Counter(), {}, Counter()
    for x in xs:
        label, raw = nearest_candidate(x)
        labels[label] += 1
        hist[round(x["fee_c"] - raw, 1)] += 1
        fl = math.floor(raw + 1e-9)
        b = min(int((raw - fl) * 10 + 1e-9), 9)          # fractional cent in tenths
        way = ("down" if x["fee_c"] == fl else "up" if x["fee_c"] == fl + 1 else "other")
        frac_tab.setdefault(b, Counter())[way] += 1
    return hist, frac_tab, labels


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", required=True)
    a = ap.parse_args(argv)
    with open(os.path.expanduser(a.csv), newline="") as f:
        rd = csv.DictReader(f)
        missing = [c for c in COLS.values() if c not in (rd.fieldnames or [])]
        if missing:
            print(f"REFUSED: column(s) not found: {', '.join(missing)} — headers seen: {rd.fieldnames}")
            return 2
        rows = list(rd)
    counts = Counter()
    xs = []
    for x in legs(rows, counts):
        _, cands = candidates(x["ticker"])
        if not cands:
            counts["no_m"] += 1
            continue
        x["cands"] = cands
        xs.append(x)
    n = len(xs)
    print(f"#88 FEE-ROUNDING RE-FIT — {a.csv}: {len(rows)} rows · multi-contract legs with a fee: "
          f"{n + counts['no_m'] + counts['shard']}")
    print(f"  excluded: {counts['shard']} priced 0.00 (combo-shard artifacts) · "
          f"{counts['no_m']} series without a ruled M (never guessed) · IN THE FIT: {n}")
    if not n:
        print("RECEIPT: no legs to fit — NOT MET")
        return 1
    hits, old = score(xs)
    print("  reproduction to the cent, by per-fill rounding rule:")
    for mode in ROUNDING_MODES:
        print(f"    {mode:<8} {hits[mode]:>5}/{n}  {hits[mode] / n * 100:5.1f}%")
    print(f"    (pre-#88 per-contract ceiling: {old}/{n}  {old / n * 100:.1f}%)")
    hist, frac_tab, labels = residuals(xs)
    print("  fractional cent of raw (tenths) vs how Kalshi rounded it:")
    print("    frac   down     up  other")
    for b in range(10):
        c = frac_tab.get(b, Counter())
        print(f"    .{b}x  {c['down']:>5}  {c['up']:>5}  {c['other']:>5}")
    ranked = sorted(ROUNDING_MODES, key=lambda m_: -hits[m_])
    best = ranked[0]
    rate = hits[best] / n
    top = [m_ for m_ in ROUNDING_MODES if hits[m_] == hits[best]]
    # Tied rules that predict EVERY leg identically are indistinguishable on this
    # data (nearest vs bankers differ only on exact half-cents): adopt the first
    # in ROUNDING_MODES order and say the halves stay unresolved. Tied rules that
    # disagree on some leg are a real tie: no adoption.
    def hit(x, md):
        return any(round_cents(raw_cents(x, rt, m), md) == x["fee_c"] for _, rt, m in x["cands"])
    same = all(len({hit(x, md) for md in top}) == 1 for x in xs)
    if rate >= ADOPT_AT and same:
        halves = sum(1 for x in xs for _, rt, m in x["cands"]
                     if abs(raw_cents(x, rt, m) % 1 - 0.5) < 1e-9)
        note = (f" ({' ≡ '.join(top)} on this data: {halves} exact-half legs — ARCHITECT-RULE on halves)"
                if len(top) > 1 else "")
        print(f"RECEIPT (#88 re-fit, full set): '{best}' reproduces {hits[best]}/{n} = {rate * 100:.1f}% "
              f"— MEETS (>= {ADOPT_AT * 100:.0f}%). ADOPT: KALSHI_FEE_ROUNDING = \"{best}\"{note}")
        return 0
    if rate >= ADOPT_AT:
        print(f"RECEIPT (#88 re-fit, full set): TIE at {rate * 100:.1f}% between {', '.join(top)} — "
              "ARCHITECT-RULE (a tie is not an adoption)")
        return 1
    print(f"RECEIPT (#88 re-fit, full set): best '{best}' {hits[best]}/{n} = {rate * 100:.1f}% — NOT MET "
          f"(< {ADOPT_AT * 100:.0f}%). Residuals follow.")
    print("  residual = fee - raw, cents, against the nearest candidate (0.1c bins):")
    for k in sorted(hist):
        print(f"    {k:+5.1f}c  {hist[k]:>5}")
    print("  nearest candidate: " + " · ".join(f"{k} {v}" for k, v in labels.most_common()))
    return 1


if __name__ == "__main__":
    sys.exit(main())
