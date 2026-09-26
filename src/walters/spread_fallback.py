"""
Spread -> win-probability fallback (architect spec, 2026-09-26, gate-class-lite).

Where a game carries NO 1X2 (moneyline) book consensus but books DO post
point spreads, the market reference fair price is derived from the consensus
spread via the normal-margin transform:

    home margin ~ N(-s, sigma)   =>   P(home wins) = Phi(-s / sigma)

where s is the consensus HOME spread line (negative = home favoured — the
api-american-football adapter stores "Home -3.5" as selection HOME,
line -3.5, sign preserved; see APIAmericanFootballAdapter._normalize_selection).

Scope: american-football family ONLY (Sport.NFL; competition codes NFL and
NCAA — NCAA football is stored under Sport.NFL with Competition.code "NCAA").
This is a MARKET REFERENCE only: it never feeds a model (doctrine: the market
is a reference, never a model feature). Output is labelled
fair_source = "spread_derived" so it is never mistaken for a 1X2 consensus.
"""
from __future__ import annotations

import math
import statistics

# Normal-margin sigmas, points. Frozen a-priori (architect 2026-09-26), never tuned.
SIGMA_NFL = 13.45
SIGMA_NCAA = 16.5

SIGMA_BY_COMPETITION = {"NFL": SIGMA_NFL, "NCAA": SIGMA_NCAA}

# Stored odds vocabulary (enumerated from the american-football adapter's
# _MARKET_MAP / _normalize_selection — law 1).
ML_MARKET = "1X2"
SPREAD_MARKET = "SPREADS"

FAIR_SOURCE_1X2 = "1X2"
FAIR_SOURCE_SPREAD = "spread_derived"

# Acceptance bar, frozen before any results exist (architect 2026-09-26).
ACCEPTANCE_MEAN_ABS_PP = 3.0


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def spread_to_home_prob(home_line: float, sigma: float) -> float:
    """P(home wins) from the home spread line s (negative = home favoured)."""
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    return _phi(-float(home_line) / sigma)


def sigma_for(competition_code: str | None) -> float | None:
    """Frozen sigma for an american-football competition; None = out of scope."""
    return SIGMA_BY_COMPETITION.get((competition_code or "").upper())


def latest_pre_kickoff(odds_rows, kickoff, market: str, with_line: bool = False) -> dict:
    """Latest capture per (bookmaker, selection[, line]) for one market,
    in-game captures (at/after kickoff) excluded — the fixtures-export rule."""
    latest: dict[tuple, object] = {}
    for o in odds_rows:
        if o.market != market:
            continue
        if kickoff is not None and o.captured_at is not None and o.captured_at >= kickoff:
            continue
        key = (o.bookmaker, o.selection, o.line) if with_line else (o.bookmaker, o.selection)
        cur = latest.get(key)
        if (cur is None or (o.captured_at is not None
                            and (cur.captured_at is None or o.captured_at > cur.captured_at))):
            latest[key] = o
    return latest


def book_home_line(rows) -> float | None:
    """
    One book's main HOME spread line from its SPREADS rows.

    Books may post alternate lines. Pairing rule: a HOME row at line L pairs
    with the AWAY row at line -L; the main line is the pair whose two prices
    are most balanced (smallest |1/p_home - 1/p_away|). With no complete pair,
    a HOME row (price closest to even) is used, else an AWAY row's line
    negated. Rows without a line are ignored.
    """
    home = [(o.line, o.price_decimal) for o in rows
            if o.selection == "HOME" and o.line is not None]
    away = [(o.line, o.price_decimal) for o in rows
            if o.selection == "AWAY" and o.line is not None]
    pairs = []
    for hl, hp in home:
        for al, ap in away:
            if abs(al + hl) < 1e-9 and hp and ap:
                pairs.append((abs(1.0 / hp - 1.0 / ap), hl))
    if pairs:
        return min(pairs)[1]
    if home:
        return min(home, key=lambda r: abs((r[1] or 0) - 2.0))[0]
    if away:
        return -min(away, key=lambda r: abs((r[1] or 0) - 2.0))[0]
    return None


def consensus_home_spread(spread_rows) -> tuple[float, int] | None:
    """Median across books of each book's main HOME line -> (line, n_books)."""
    by_book: dict[str, list] = {}
    for o in spread_rows:
        by_book.setdefault(o.bookmaker, []).append(o)
    lines = [ln for ln in (book_home_line(r) for r in by_book.values()) if ln is not None]
    if not lines:
        return None
    return float(statistics.median(lines)), len(lines)


def derive_spread_market(spread_rows, competition_code: str | None) -> dict | None:
    """
    Spread-derived market block, or None when out of scope / no usable spread.
    Shape mirrors the 1X2 market block (bookmaker_count, fair_prob) plus the
    labelled source and the inputs that produced it.
    """
    sigma = sigma_for(competition_code)
    if sigma is None:
        return None
    cons = consensus_home_spread(spread_rows)
    if cons is None:
        return None
    line, n_books = cons
    p_home = spread_to_home_prob(line, sigma)
    return {
        "bookmaker_count": n_books,
        "fair_prob": {"HOME": round(p_home, 4), "AWAY": round(1.0 - p_home, 4)},
        "fair_source": FAIR_SOURCE_SPREAD,
        "consensus_home_spread": line,
        "spread_sigma": sigma,
    }


def ml_fair_home(latest_1x2: dict) -> float | None:
    """De-vigged HOME fair from latest 1X2 rows — the export's existing method
    (MarketSnapshot.average_implied, normalized by the summed implied)."""
    from src.walters.value import MarketSnapshot
    by_sel: dict[str, list[tuple[str, float]]] = {}
    for o in latest_1x2.values():
        by_sel.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
    if not {"HOME", "AWAY"} <= set(by_sel):
        return None  # one-sided 1X2 cannot be de-vigged honestly
    implied = MarketSnapshot(market=ML_MARKET, by_selection=by_sel).average_implied()
    over = sum(implied.values())
    if over <= 0:
        return None
    return implied["HOME"] / over


def spread_fallback_check(competition_code: str, start: str | None = None,
                          end: str | None = None) -> dict:
    """
    READ-ONLY acceptance receipt: over games carrying BOTH a two-sided 1X2
    consensus AND spreads (pre-kickoff captures only), compare the
    spread-derived home prob to the 1X2 de-vigged home fair.
    """
    from datetime import datetime as _dt, timedelta as _td

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Odds

    sigma = sigma_for(competition_code)
    if sigma is None:
        raise ValueError(f"{competition_code}: not an american-football competition "
                         f"(in scope: {', '.join(SIGMA_BY_COMPETITION)})")
    rows = []
    with session_scope() as s:
        comp = s.execute(select(Competition).where(
            Competition.code == competition_code.upper())).scalars().first()
        if comp is None:
            raise ValueError(f"unknown competition {competition_code}")
        q = select(Match).where(Match.competition_id == comp.id)
        if start:
            q = q.where(Match.utc_date >= _dt.fromisoformat(start))
        if end:
            q = q.where(Match.utc_date < _dt.fromisoformat(end) + _td(days=1))
        for m in s.execute(q.order_by(Match.utc_date, Match.id)).scalars():
            odds = list(s.execute(select(Odds).where(Odds.match_id == m.id)).scalars())
            if not odds:
                continue
            ml = ml_fair_home(latest_pre_kickoff(odds, m.utc_date, ML_MARKET))
            if ml is None:
                continue
            sp = latest_pre_kickoff(odds, m.utc_date, SPREAD_MARKET, with_line=True)
            cons = consensus_home_spread(sp.values())
            if cons is None:
                continue
            derived = spread_to_home_prob(cons[0], sigma)
            rows.append({
                "match_id": m.id,
                "date": m.utc_date.date().isoformat(),
                "game": (f"{m.away_team.name if m.away_team else '?'} @ "
                         f"{m.home_team.name if m.home_team else '?'}"),
                "spread": cons[0], "spread_books": cons[1],
                "ml_fair_home": ml, "derived_home": derived,
                "abs_diff_pp": abs(derived - ml) * 100,
            })
    n = len(rows)
    mean = sum(r["abs_diff_pp"] for r in rows) / n if n else None
    fav_agree = sum(1 for r in rows
                    if (r["derived_home"] - 0.5) * (r["ml_fair_home"] - 0.5) >= 0)
    return {"competition": competition_code.upper(), "sigma": sigma, "rows": rows,
            "n": n, "mean_abs_pp": mean, "favourite_agree": fav_agree,
            "bar_pp": ACCEPTANCE_MEAN_ABS_PP,
            "pass": (mean is not None and mean <= ACCEPTANCE_MEAN_ABS_PP)}
