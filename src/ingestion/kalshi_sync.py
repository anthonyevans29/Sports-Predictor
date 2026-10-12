"""
Kalshi sync — pulls MLB game markets and stores each team's implied win prob as
an OddsSnapshot row with source="kalshi", parallel to the bookmaker de-vig
consensus (source="consensus"/book sources). This lets the disagreement read be
a clean self-join on odds_snapshots by (match, selection).

Placement is src/ingestion/kalshi_match.py (addendum 37 item 2 + addendum 44
item 1), one matcher for both paths: the event's two names fit a game of the
series' own competition on the event's day, and every refusal is counted by its
reason and printed, so coverage is seen rather than assumed.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from src.adapters.kalshi import KalshiAdapter
from src.db.database import session_scope, write_kalshi_tickers
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot
from src.timeutil import utc_now_naive

log = logging.getLogger(__name__)


def sync_kalshi_mlb(date_from=None, date_to=None, progress=None,
                   sport=None, series_override: str | None = None) -> dict:
    """
    Pull open Kalshi game markets of one two-way series (KXMLBGAME, or the
    override: KXNFLGAME / KXNHLGAME / KXNCAAFGAME), place them on the games of
    the series' own competition (venue.KALSHI_SERIES_BY_COMPETITION; `sport`
    is accepted from the callers and no longer scopes anything), and store
    each side's implied prob as an OddsSnapshot(source="kalshi").
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

    # The matcher (ARCHITECT 2026-10-10 addendum 37 item 2, with addendum 44 item 1's day rule): the event's two
    # names fit a game of the series' OWN competition on the event's day; the window and the time gate choose only
    # inside that one pair; every refusal is counted by its reason (src/ingestion/kalshi_match.py).
    from src.ingestion import kalshi_match as km
    from src.walters.venue import KALSHI_SERIES_BY_COMPETITION
    series = series_override or adapter.GAME_SERIES[0]
    comp_code = {v: k for k, v in KALSHI_SERIES_BY_COMPETITION.items()}.get(series)
    if comp_code is None:
        return {"ok": False, "series": _series_label,
                "reason": f"series {series} names no competition (KALSHI_SERIES_BY_COMPETITION): refused, "
                          "a market is placed only among its own competition's games"}
    now = utc_now_naive()
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=2))
    stored = 0
    with session_scope() as sess:
        comp = sess.execute(select(Competition).where(Competition.code == comp_code)).scalar_one_or_none()
        span = km.day_span(all_markets)
        games = [] if (comp is None or span is None) else [g for g in sess.execute(
            select(Match).where(Match.competition_id == comp.id,
                                Match.utc_date >= span[0], Match.utc_date <= span[1])
        ).scalars() if g.utc_date]
        report(f"  {len(games)} stored {comp_code} games on the events' days")
        res = km.place(all_markets, games, now=now, lo=lo, hi=hi, implied_prob=adapter.implied_prob)
        for ln in km.console_lines(res):
            report(ln)
        stored_legs = []                                 # ORDER LINE: (snapshot, ticker)
        for (match_id, side), mk in res.placed.items():
            bid, ask = adapter.yes_quotes(mk)
            snap = OddsSnapshot(
                match_id=match_id, market="ML", selection=side,
                devig_prob=round(adapter.implied_prob(mk), 4), line=None, n_books=1,
                captured_at=now, source="kalshi",
                yes_bid=bid, yes_ask=ask,
            )
            sess.add(snap)
            stored_legs.append((snap, mk.get("ticker")))
            stored += 1
        if stored_legs:                                  # the ticker column is unmapped (see schema)
            sess.flush()
            write_kalshi_tickers(sess, [(sn.id, t) for sn, t in stored_legs])
        in_window = [g for g in games if lo <= g.utc_date <= hi]

    counts = km.legacy_counts(res)
    # Sentinel (2026-09-17, extending the soccer guard to the shared path):
    # zero matches with BOTH sides present is an alarm, not a statistic.
    if counts["matched"] == 0 and in_window and all_markets:
        report("  ⚠ MATCHED ZERO with games AND markets present — matcher may "
               "be broken (see 2026-09-13 title-format incident). Probe the "
               "payload before trusting 'absent'.")
    return {"ok": True, "series": _series_label, "competition": comp_code,
            "markets": len(all_markets), **counts, "stored": stored}


def sync_kalshi_soccer(competition_code: str = "PL", date_from=None, date_to=None,
                       max_spread: float = 0.10, progress=None, series_override: str | None = None) -> dict:
    """
    Pull open Kalshi soccer game markets (3 legs per game: Home / Away / Tie)
    and store pre-game implied probs as OddsSnapshot(source="kalshi",
    market="1X2", selection HOME/AWAY/DRAW).

    Inherits every hard-won MLB gate, plus one soccer-specific requirement:

      * DAY rule — the ticker's date (soccer tickers carry no clock time);
        occurrence_datetime is an expected expiration and gates nothing
      * IN-PLAY gate — prices captured after kickoff are refused (soccer
        markets stay open during play; weekend clusters make this constant)
      * BOTH-TEAMS gate — both title teams must fit the same fixture
        (full club names per the 2026-08-17 recon; alias-map fallback)
      * SPREAD GUARD (new) — far-out legs quote e.g. 0.03/0.81; a midpoint of
        that is noise, not a price. Legs with ask−bid > max_spread are
        skipped and counted, never stored. MLB never needed this (1-2c
        spreads); days-ahead weekend syncs do.
      * ambiguity REFUSED; one price per (match, selection) per run

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

    now = utc_now_naive()
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=7))   # weekend cadence: cover the matchweek

    from src.ingestion import kalshi_match as km
    stored = 0
    with session_scope() as sess:
        comp = sess.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return {"ok": False, "reason": f"competition {competition_code} not in DB"}
        # The shared matcher (addendum 37 item 2 + addendum 44 item 1): the competition's scheduled games on the
        # events' days; the window chooses only inside the one pair. Legs: the two teams' markets (their
        # yes_sub_titles are the event's names, 2026-09-13) and the Tie leg, placed as DRAW on the event's game.
        span = km.day_span(all_markets)
        games = [] if span is None else [g for g in sess.execute(
            select(Match).where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.SCHEDULED,
                Match.utc_date >= span[0], Match.utc_date <= span[1])
        ).scalars() if g.utc_date]
        in_window = [g for g in games if lo <= g.utc_date <= hi]
        report(f"  {len(in_window)} scheduled {competition_code} games in window "
               f"({len(games)} on the events' days)")
        # Spread guard: far-out legs quote e.g. 0.03/0.81; a midpoint of that is noise, not a price. Occurrence is
        # an expected expiration (2026-09-14 derby: 3h after kickoff); in play is read on OUR kickoff only.
        res = km.place(all_markets, games, now=now, lo=lo, hi=hi, is_tie=adapter.is_tie_market,
                       implied_prob=KalshiAdapter.implied_prob, spread=adapter.spread_dollars,
                       max_spread=max_spread)
        for ln in km.console_lines(res):
            report(ln)

        stored_legs = []                                 # ORDER LINE: (snapshot, ticker)
        for (match_id, sel), mk in res.placed.items():
            bid, ask = KalshiAdapter.yes_quotes(mk)
            snap = OddsSnapshot(
                match_id=match_id, market="1X2", selection=sel,
                devig_prob=round(KalshiAdapter.implied_prob(mk), 4), line=None, n_books=1,
                captured_at=now, source="kalshi",
                yes_bid=bid, yes_ask=ask,
            )
            sess.add(snap)
            stored_legs.append((snap, mk.get("ticker")))
            stored += 1
        if stored_legs:                                  # the ticker column is unmapped (see schema)
            sess.flush()
            write_kalshi_tickers(sess, [(sn.id, t) for sn, t in stored_legs])

    counts = km.legacy_counts(res)
    # Sentinel (2026-09-14): two matchweeks went dark before anyone noticed —
    # zero matches with BOTH sides present is an alarm, not a statistic.
    if counts["matched"] == 0 and in_window and all_markets:
        report("  ⚠ MATCHED ZERO with games AND markets present — matcher may "
               "be broken (see 2026-09-13 title-format incident). Probe the "
               "payload before trusting 'absent'.")
    return {"ok": True, "series": series, "series_how": how, "markets": len(all_markets),
            **counts, "wide_spread": res.refused.get(km.WIDE_SPREAD, 0), "stored": stored}
