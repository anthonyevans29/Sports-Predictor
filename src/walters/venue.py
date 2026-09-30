"""
Venue divergence (2026-09-26, architect): book consensus vs Kalshi.

Arrives first as a LIE DETECTOR on the NFL predictions export: the
provider's football moneylines were found stale AT SOURCE (favourite
disagreements between deep, same-minute markets survived the vetted
spread check), and the same 1X2 rows feed fair / divergence / quarantine.
A large book-vs-Kalshi gap flags the book reference as suspect.

DISPLAY AND WARNING ONLY: nothing here changes the quarantine contract,
which still keys on the book divergence exactly as ratified. The Cockpit
v0.4 venue-edge engine reuses this math.
"""
from __future__ import annotations

import math

STALE_BOOK_GAP_PP = 8.0     # frozen a-priori (architect 2026-09-26)
STALE_BOOK_FLAG = "STALE-BOOK?"

# ---------------------------------------------------------------------------
# K-track (K1, 2026-09-27): executable cost of buying a Kalshi YES contract.
# Kalshi's published trading-fee schedule: fees = roundup(0.07 x C x P x (1-P))
# to the next cent, for C contracts at price P (dollars). Per ONE contract that
# is ceil(0.07 x P x (1-P) x 100) / 100 dollars = probability points.
# VERIFY RECEIPT (2026-09-29, BACKLOG "KALSHI FEE SCHEDULE"): the published
# schedule ("Fee Schedule for July 2026 - 7.7.26 Update") gives taker =
# roundup(M x 0.07 x C x P x (1-P)), M default 1, so the 0.07 constant is
# CONFIRMED. Maker = roundup(M x 0.0175 x C x P x (1-P)), M default 0 unless
# the series is listed; the per-series table is NOT yet verified. ROUNDING
# DIFFERS: Kalshi rounds fee + position cost UP TO THE CENTICENT, with a
# per-order accumulator that rebates whole cents. The per-contract ceil to the
# cent below OVERSTATES the fee (by up to ~1c; +0.32pp at P = 0.60). Left
# unchanged pending the architect's ruling. K-TRACK: INFORMATIONAL UNTIL THE
# EXECUTABLE-EDGE RULING.
# ---------------------------------------------------------------------------
KALSHI_FEE_RATE = 0.07      # taker rate: VERIFIED 2026-09-29 (rounding: see above)
K_TRACK_NOTE = "K-track: informational until the executable-edge ruling"


def kalshi_fee(price: float | None) -> float | None:
    """Per-contract taker fee in dollars (= probability points), rounded UP
    to the cent. ARCHITECT-VERIFY (see above)."""
    if price is None or not (0.0 <= price <= 1.0):
        return None
    raw = KALSHI_FEE_RATE * price * (1.0 - price) * 100.0
    return math.ceil(raw - 1e-9) / 100.0   # epsilon: float noise must not add a cent


def kalshi_exec(bid: float | None, ask: float | None) -> dict:
    """{kalshi_bid, kalshi_ask, kalshi_exec_cost (= ask + fee), k_track} —
    exec cost is null when no ask was quoted."""
    fee = kalshi_fee(ask)
    return {"kalshi_bid": bid, "kalshi_ask": ask,
            "kalshi_exec_cost": (round(ask + fee, 4) if ask is not None and fee is not None
                                 else None),
            "k_track": K_TRACK_NOTE}


def kalshi_home_prob(snapshots, kickoff, three_way: bool = False) -> dict | None:
    """Latest PRE-KICKOFF Kalshi price per side (the fixtures-export rule);
    complete sets only. Returns {"home": P(home) normalized over the FULL
    outcome set, "captured_at": latest capture} or None when a leg is missing.
    Sum-to-1 rescaling is the only form comparable to the de-vigged book fair
    (ratified 2026-09-26). NOTE: the fixtures export's `kalshi.prob` is the
    RAW stored per-side value, not rescaled — consumers normalize it.
    CORRECTION #117 (architect 2026-09-30): soccer (three_way) needs HOME,
    DRAW and AWAY and normalizes over all three. H/(H+A) on a 1X2 market is
    not a home-win probability, and a missing TIE leg is incomplete, never
    a two-way set."""
    legs = ("HOME", "DRAW", "AWAY") if three_way else ("HOME", "AWAY")
    latest: dict[str, object] = {}
    for snap in snapshots:
        if snap.source != "kalshi" or snap.selection not in legs:
            continue
        if kickoff is not None and snap.captured_at is not None and snap.captured_at >= kickoff:
            continue  # in-play never
        cur = latest.get(snap.selection)
        if (cur is None or (snap.captured_at is not None
                            and (cur.captured_at is None or snap.captured_at > cur.captured_at))):
            latest[snap.selection] = snap
    if set(latest) != set(legs):
        return None
    vals = [latest[k].devig_prob for k in legs]
    if any(v is None for v in vals) or sum(vals) <= 0:
        return None
    caps = [s.captured_at for s in latest.values() if s.captured_at is not None]
    home = latest["HOME"]
    return {"home": home.devig_prob / sum(vals), "captured_at": max(caps) if caps else None,
            # K-track: the HOME contract's quotes (None on pre-K1 snapshots)
            "home_bid": getattr(home, "yes_bid", None),
            "home_ask": getattr(home, "yes_ask", None)}


def venue_gap(book_home: float | None, kalshi_home: float | None) -> tuple[float | None, str | None]:
    """(|book_fair - kalshi| in pp, flag). Flag = STALE-BOOK? at >= 8.0pp."""
    if book_home is None or kalshi_home is None:
        return None, None
    gap = round(abs(book_home - kalshi_home) * 100, 1)
    return gap, (STALE_BOOK_FLAG if gap >= STALE_BOOK_GAP_PP else None)
