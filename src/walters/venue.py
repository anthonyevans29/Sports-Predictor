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
# the series is listed; the game series' M values were RULED on #93
# (2026-09-30, KALSHI_FEE_M below). ROUNDING
# DIFFERS: Kalshi rounds fee + position cost UP TO THE CENTICENT, with a
# per-order accumulator that rebates whole cents. The per-contract ceil to the
# cent below OVERSTATES the fee (by up to ~1c; +0.32pp at P = 0.60). Left
# unchanged pending the architect's ruling (#88). K-TRACK: INFORMATIONAL UNTIL THE
# EXECUTABLE-EDGE RULING.
# ---------------------------------------------------------------------------
KALSHI_FEE_RATE = 0.07      # taker rate: VERIFIED 2026-09-29 (rounding: see above)
KALSHI_MAKER_RATE = 0.0175  # maker rate: the same published schedule
K_TRACK_NOTE = "K-track: informational until the executable-edge ruling"

# #93 RESOLVED (architect 2026-09-30, from Kalshi's fee schedule): the game
# series' multipliers M. Game series (NFL/NHL/EPL/UCL/NCAAF/MLB): taker M=1,
# maker M=0.25; MLB PRE-LIVE M=0.5 for both (taker $0.04-$0.88, maker
# $0.01-$0.22 per 100 contracts); MLB live M=1 is never priced here, because
# MLB is never executed live (doctrine, ruling (4)). Combos: maker = 50% of
# taker (fills classification only). Our exports are pre-kickoff captures
# only (in-play never), so the pre-live M applies. UCL is in the ruling, but
# no UCL series is wired, so no ticker is guessed for it.
KALSHI_FEE_M = {                       # series -> (taker M, maker M), pre-live
    "KXNFLGAME": (1.0, 0.25), "KXNHLGAME": (1.0, 0.25), "KXNCAAFGAME": (1.0, 0.25),
    "KXEPLGAME": (1.0, 0.25), "KXMLBGAME": (0.5, 0.5),
}
# Competition code -> the Kalshi game series its quotes come from (cli
# sync-kalshi-* and adapters/kalshi.py SOCCER_GAME_SERIES). A code missing
# here gets the schedule's default taker M=1 and NO maker cost: the maker M of
# an unlisted series is not assumed (conservative unknowns).
KALSHI_SERIES_BY_COMPETITION = {
    "NFL": "KXNFLGAME", "NHL": "KXNHLGAME", "NCAA": "KXNCAAFGAME",
    "PL": "KXEPLGAME", "MLB": "KXMLBGAME",
}


def kalshi_fee(price: float | None, m: float = 1.0, rate: float = KALSHI_FEE_RATE) -> float | None:
    """Per-contract fee in dollars (= probability points): rate x M x P x (1-P),
    rounded UP to the cent. The rounding is unchanged and still pending the
    ruling on #88. It overstates both costs; the maker fee most, because it is
    under 0.2c exact and is modelled as 1c."""
    if price is None or not (0.0 <= price <= 1.0):
        return None
    raw = rate * m * price * (1.0 - price) * 100.0
    return math.ceil(raw - 1e-9) / 100.0   # epsilon: float noise must not add a cent


def kalshi_exec(bid: float | None, ask: float | None, competition: str | None = None) -> dict:
    """The HOME contract's quotes + both executable costs (ruling 2026-09-30 on #93):
      exec_cost_taker = ask + 0.07 x M_taker x P(1-P), P = ask
      exec_cost_maker = (bid + 1c) + 0.0175 x M_maker x P(1-P), P = bid + 1c
    exec_cost_maker is null when there is no bid, when bid + 1c reaches the
    ask (a 1c spread: joining = taking, so no maker price exists), or when the
    series' maker M is unknown. kalshi_exec_cost is kept as a DEPRECATED alias
    of exec_cost_taker (the pre-split meaning) until the published Cockpit
    reads the two fields."""
    series = KALSHI_SERIES_BY_COMPETITION.get(competition or "")
    m_taker, m_maker = KALSHI_FEE_M.get(series, (1.0, None))
    fee_t = kalshi_fee(ask, m_taker)
    taker = round(ask + fee_t, 4) if ask is not None and fee_t is not None else None
    maker = None
    if bid is not None and m_maker is not None:
        join = round(bid + 0.01, 2)
        if (ask is None or join < ask - 1e-9) and join <= 1.0:
            fee_m = kalshi_fee(join, m_maker, KALSHI_MAKER_RATE)
            maker = round(join + fee_m, 4) if fee_m is not None else None
    return {"kalshi_bid": bid, "kalshi_ask": ask,
            "exec_cost_taker": taker, "exec_cost_maker": maker,
            "kalshi_exec_cost": taker,            # deprecated alias (= taker)
            "fee_series": series, "fee_m_taker": m_taker, "fee_m_maker": m_maker,
            "k_track": K_TRACK_NOTE}


# The null block for rows without a two-sided Kalshi set (same keys as kalshi_exec).
KALSHI_EXEC_NULL = {"kalshi_bid": None, "kalshi_ask": None, "exec_cost_taker": None,
                    "exec_cost_maker": None, "kalshi_exec_cost": None}


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
