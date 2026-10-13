"""
Kalshi sync — pulls MLB game markets and stores each team's implied win prob as
an OddsSnapshot row with source="kalshi", parallel to the bookmaker de-vig
consensus (source="consensus"/book sources). This lets the disagreement read be
a clean self-join on odds_snapshots by (match, selection).

Where a market is stored is decided by ONE placement, src/ingestion/kalshi_match.place (the switch, ARCHITECT
addendum 50 item 6(b), called on the read-only replay's console): both paths here load the stored games of the
series' own competition on the events' days and store what place() places. Every refusal is counted by its reason
and printed (kalshi_match.console_lines), never silent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from src.adapters.kalshi import KalshiAdapter
from src.db.database import session_scope, write_kalshi_tickers
from src.db.schema import Competition, Match, OddsSnapshot
from src.ingestion import kalshi_match as km
from src.timeutil import utc_now_naive

log = logging.getLogger(__name__)


def series_competition(series: str) -> str | None:
    """The series' own competition: venue.KALSHI_SERIES_BY_COMPETITION read the other way. One map of series to
    competition for the syncs and the replay (addendum 51 item 7). None when the map does not name it once."""
    from src.walters.venue import KALSHI_SERIES_BY_COMPETITION
    comps = [c for c, s in KALSHI_SERIES_BY_COMPETITION.items() if s == series]
    return comps[0] if len(comps) == 1 else None


def stored_games(sess, comp_ids, markets: list[dict]) -> list:
    """The stored games place() reads: every row of the competition(s) whose kickoff falls in the span of the
    events' days (kalshi_match.day_span), of any status (kalshi_match.is_game drops the rows that are not games).
    The run's window is not read here: place() applies it inside the one pair."""
    span = km.day_span(markets)
    if span is None or not comp_ids:
        return []
    return [g for g in sess.execute(
        select(Match).where(Match.competition_id.in_(list(comp_ids)), Match.utc_date >= span[0],
                            Match.utc_date <= span[1])).scalars() if g.utc_date]


def _alarm(sess, comp_ids, res: km.Result, markets: list[dict], now, lo, hi, report) -> bool:
    """The zero-placement alarm (ARCHITECT 2026-10-12, addendum 54 item 3), verbatim: "The alarm is for a run that had
    a game to price and priced none. It prints when no market is placed although markets were read and a game of the
    competition that has not started is inside the run's window. A game outside the window does not count, nor one
    that has started, nor a row that is not a game." Started is read on our kickoff, as the in-play refusal reads it."""
    if res.placed or not markets or not comp_ids:
        return False
    due = [g for g in sess.execute(
        select(Match).where(Match.competition_id.in_(list(comp_ids)), Match.utc_date >= lo, Match.utc_date <= hi,
                            Match.utc_date > now)).scalars() if km.is_game(g)]
    if not due:
        return False
    report(f"  ⚠ MATCHED ZERO with {len(markets)} markets read and {len(due)} unstarted game(s) of the competition "
           "inside the run's window — matcher may be broken (see 2026-09-13 title-format incident). Probe the "
           "payload before trusting 'absent'.")
    return True


def _store(sess, res: km.Result, *, now, market: str, implied_prob, yes_quotes) -> int:
    """Store each placed leg as an OddsSnapshot(source="kalshi") with its quotes and its market ticker."""
    stored_legs = []                                 # ORDER LINE: (snapshot, ticker)
    for (match_id, side), mk in res.placed.items():
        bid, ask = yes_quotes(mk)
        snap = OddsSnapshot(
            match_id=match_id, market=market, selection=side,
            devig_prob=round(implied_prob(mk), 4), line=None, n_books=1,
            captured_at=now, source="kalshi",
            yes_bid=bid, yes_ask=ask,
        )
        sess.add(snap)
        stored_legs.append((snap, mk.get("ticker")))
    if stored_legs:                                  # the ticker column is unmapped (see schema)
        sess.flush()
        write_kalshi_tickers(sess, [(sn.id, t) for sn, t in stored_legs])
    return len(stored_legs)


def sync_kalshi_mlb(date_from=None, date_to=None, progress=None,
                   sport=None, series_override: str | None = None) -> dict:
    """
    Pull open Kalshi game markets of a two-way series (MLB by default; NFL, NHL,
    NCAA by `series_override`), place them with kalshi_match.place on the stored
    games of the series' own competition (`sport` is kept for the callers and
    read nowhere), store each side's implied prob as an OddsSnapshot(source="kalshi").
    Returns a summary dict. Does NOT devig (Kalshi yes/no is already ~a
    probability; for a two-sided game we store each team's yes-prob and also a
    normalized pair so the comparison is apples-to-apples with the book devig).
    """
    def report(m):
        if progress:
            progress(m)

    adapter = KalshiAdapter()

    # connectivity + discover the MLB series (never hardcode the ticker)
    report("Checking Kalshi status…")
    st = adapter.status()
    if not st.get("trading_active", False):
        report("Note: Kalshi trading not currently active (prices may be stale/closed).")

    # Name the series actually discovered (2026-10-07: every sport printed "MLB").
    _series_label = series_override or ", ".join(adapter.GAME_SERIES)
    report(f"Discovering {_series_label} game series…")
    # optional: show what sports Kalshi exposes (helps debugging coverage)
    sf = adapter.sports_filters()
    if sf and sf.get("sport_ordering"):
        sports = sf.get("sport_ordering", [])
        report(f"  Kalshi sports available: {', '.join(sports[:12])}")

    # Target ONLY the daily game moneyline series — not all 200+ MLB series
    # (which trips the rate limit and is 99% props/awards/futures noise).
    # NFL phase 1c (2026-09-06): the two-sided matcher serves any US-team-
    # sport series — parameterized rather than copied. Non-MLB callers pass
    # their series ticker (KXNFLGAME); empty results report available sports.
    report(f"  fetching game series {_series_label}…")
    all_markets = (adapter.open_markets_for_series(series_override)
                   if series_override else adapter.game_series_markets())
    if not all_markets:
        return {"ok": False, "reason": f"no open markets in {_series_label} "
                "(series ticker may have changed — check available series)",
                "sports_available": sf.get("sport_ordering", []) if sf else []}
    report(f"  {len(all_markets)} open game markets")
    # DIAGNOSTIC: show one raw market so we can see how teams/prices are encoded
    if all_markets:
        s0 = all_markets[0]
        report(f"  sample market keys: {sorted(s0.keys())}")
        report(f"  sample: ticker={s0.get('ticker')!r} title={s0.get('title')!r} "
               f"yes_sub_title={s0.get('yes_sub_title')!r} "
               f"yes_bid_dollars={s0.get('yes_bid_dollars')!r} "
               f"yes_ask_dollars={s0.get('yes_ask_dollars')!r} "
               f"last={s0.get('last_price_dollars')!r}")

    # the games: the series' own competition, on the events' days (the switch: kalshi_match.place decides)
    series_list = [series_override] if series_override else list(adapter.GAME_SERIES)
    comp_codes = {series_competition(x) for x in series_list}
    if None in comp_codes:
        return {"ok": False, "series": _series_label,
                "reason": f"no competition for {_series_label} in venue.KALSHI_SERIES_BY_COMPETITION"}
    now = utc_now_naive()                           # stamped after the fetch: the in-play read is this moment's
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=2))
    with session_scope() as sess:
        comps = dict(sess.execute(select(Competition.code, Competition.id).where(Competition.code.in_(comp_codes))).all())
        missing = sorted(comp_codes - set(comps))
        if missing:                                  # as the soccer path answers (addendum 54 item 4(b))
            return {"ok": False, "series": _series_label, "reason": f"competition {', '.join(missing)} not in DB"}
        comp_ids = list(comps.values())
        games = stored_games(sess, comp_ids, all_markets)
        report(f"  {len(games)} stored {'/'.join(sorted(comp_codes))} games on the events' days")
        res = km.place(all_markets, games, now=now, lo=lo, hi=hi, implied_prob=adapter.implied_prob)
        for ln in km.console_lines(res):
            report(ln)
        stored = _store(sess, res, now=now, market="ML", implied_prob=adapter.implied_prob, yes_quotes=adapter.yes_quotes)
        # Sentinel (2026-09-17, extending the soccer guard to the shared path); its condition as addendum 54 item 3
        # rules it
        alarm = _alarm(sess, comp_ids, res, all_markets, now, lo, hi, report)
    counts = km.legacy_counts(res)
    return {"ok": True, "series": _series_label, "markets": len(all_markets), **counts, "stored": stored,
            "alarm": alarm}


def sync_kalshi_soccer(competition_code: str = "PL", date_from=None, date_to=None,
                       max_spread: float = 0.10, progress=None, series_override: str | None = None) -> dict:
    """
    Pull open Kalshi soccer game markets (3 legs per game: Home / Away / Tie)
    and store pre-game implied probs as OddsSnapshot(source="kalshi",
    market="1X2", selection HOME/AWAY/DRAW).

    Placed by kalshi_match.place, as the shared path is (the event's two names
    from its sibling legs, the ticker's day, the run's window last, in play on
    our kickoff), with the soccer path's own two: the Tie leg is placed as DRAW
    on the event's game, and the SPREAD GUARD — far-out legs quote e.g.
    0.03/0.81; a midpoint of that is noise, not a price. Legs with
    ask−bid > max_spread are refused and counted, never stored.

    Per the 2026-08-17 Step-1 verdict: this is a COVERAGE source and plain
    instrumentation — no disagreement machinery beyond the export columns.
    """
    def report(m):
        if progress:
            progress(m)

    adapter = KalshiAdapter()
    report("Checking Kalshi status…")
    st = adapter.status()
    if not st.get("trading_active", False):
        report("Note: Kalshi trading not currently active (prices may be stale).")

    series, how = adapter.resolve_soccer_series(competition_code, series_override)
    if not series:
        return {"ok": False, "reason": how}
    report(f"  game series {series} ({how}) — fetching…")
    try:
        all_markets = adapter.open_markets_for_series(series)
    except Exception as e:
        return {"ok": False, "reason": f"market fetch failed: {e}"}
    if not all_markets:
        return {"ok": False, "reason": f"no open markets in {series}"}
    report(f"  {len(all_markets)} open game markets")

    now = utc_now_naive()                           # stamped after the fetch: the in-play read is this moment's
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=7))   # weekend cadence: cover the matchweek

    with session_scope() as sess:
        comp = sess.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return {"ok": False, "reason": f"competition {competition_code} not in DB"}
        games = stored_games(sess, [comp.id], all_markets)
        report(f"  {len(games)} stored {competition_code} games on the events' days")
        res = km.place(all_markets, games, now=now, lo=lo, hi=hi, implied_prob=KalshiAdapter.implied_prob,
                       is_tie=adapter.is_tie_market, spread=adapter.spread_dollars, max_spread=max_spread)
        for ln in km.console_lines(res):
            report(ln)
        stored = _store(sess, res, now=now, market="1X2", implied_prob=KalshiAdapter.implied_prob,
                        yes_quotes=KalshiAdapter.yes_quotes)
        # Sentinel (2026-09-14): two matchweeks went dark before anyone noticed; its condition as addendum 54 item 3
        # rules it
        alarm = _alarm(sess, [comp.id], res, all_markets, now, lo, hi, report)
    counts = km.legacy_counts(res)
    return {"ok": True, "series": series, "series_how": how, "markets": len(all_markets), **counts,
            "wide_spread": res.refused.get(km.WIDE_SPREAD, 0), "stored": stored, "alarm": alarm}
