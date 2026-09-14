"""
Kalshi adapter — pulls MLB game market prices as a SECOND, independent market
consensus alongside the bookmaker de-vig line.

Purpose (Step 1): measure how often, and by how much, Kalshi disagrees with the
sportsbook consensus. If they agree ~always, Kalshi is redundant and we stop.
If they disagree systematically, that's a signal worth a Step-2 investigation
(which market predicts better). We are NOT feeding Kalshi into the model or
routing bets on it — instrument first, conclude later, same discipline as
OddsSnapshot / umpires.

Public market data needs NO auth (per Kalshi docs: the /markets, /events,
/series endpoints are open). Auth is only for trading/portfolio, which we don't
touch. Prices are in CENTS (0-100) = implied probability; yes_bid/yes_ask.

IMPORTANT: Kalshi's MLB series ticker is discovered at runtime, not hardcoded —
tickers change (e.g. the KX* Klear-clearinghouse prefix migration), and guessing
one would silently fetch nothing. We search the series list for MLB.
"""
from __future__ import annotations

import logging
from datetime import datetime

import requests

log = logging.getLogger(__name__)

BASE = "https://external-api.kalshi.com/trade-api/v2"


class KalshiAdapter:
    def __init__(self, base_url: str = BASE, timeout: int = 20):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base}/{path.lstrip('/')}"
        r = requests.get(url, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def status(self) -> dict:
        """Exchange heartbeat — quick connectivity check."""
        return self._get("exchange/status")

    def sports_filters(self) -> dict:
        """
        /search/filters_by_sport — maps each sport to its scopes + competitions.
        Cleaner MLB discovery than keyword-scanning series titles: we can read
        the baseball/MLB competition directly. Returns {} if unavailable.
        """
        try:
            return self._get("search/filters_by_sport")
        except Exception:
            return {}

    # The DAILY GAME moneyline series. Kalshi uses KXMLBGAME for individual
    # game winner markets — that's the ONLY series relevant to comparing against
    # our per-game bookmaker moneyline. Everything else (KXMLBHR, KXMLBWINS-*,
    # awards, NPB/KBO/WBC/NCAA, player props) is noise for this purpose, and
    # scanning all of them trips Kalshi's rate limit (429s). Configurable in case
    # the ticker changes.
    GAME_SERIES = ["KXMLBGAME"]

    def game_series_markets(self) -> list[dict]:
        """Open markets for the daily MLB game (moneyline) series only."""
        out = []
        for tick in self.GAME_SERIES:
            try:
                out.extend(self.open_markets_for_series(tick))
            except Exception as e:
                log.warning("Kalshi game series %s fetch failed: %s", tick, e)
        return out

    def find_series(self, keywords: list[str]) -> list[dict]:
        """
        Discover series whose title/category/tags/ticker mention any keyword
        (case-insensitive). Uses GET /series (NOT /series/list). Generic so
        soccer/NFL/etc. reuse the same discovery path as MLB — payload-first:
        look at what Kalshi actually offers before writing any matcher.
        """
        data = {}
        for params in ({"category": "Sports"}, None):
            try:
                data = self._get("series", params=params)
                if data.get("series"):
                    break
            except Exception:
                continue
        kws = [k.lower() for k in keywords]
        out = []
        for s in data.get("series", []):
            hay = " ".join([
                str(s.get("title", "")),
                str(s.get("category", "")),
                " ".join(s.get("tags") or []),
                str(s.get("ticker", "")),
            ]).lower()
            if any(k in hay for k in kws):
                out.append(s)
        return out

    def find_mlb_series(self) -> list[dict]:
        """Back-compat wrapper around find_series for MLB callers."""
        return self.find_series(["mlb", "baseball"])

    def open_markets_for_series(self, series_ticker: str) -> list[dict]:
        """All open markets for a series (each market = one tradable outcome)."""
        markets, cursor = [], None
        for _ in range(20):  # page-guard
            params = {"series_ticker": series_ticker, "status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("markets", params=params)
            markets.extend(data.get("markets", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        return markets

    @staticmethod
    def implied_prob(market: dict) -> float | None:
        """
        Mid implied probability from a market's yes bid/ask, in [0,1].
        Kalshi's *_dollars fields are 0.00-1.00 but returned as STRINGS
        (e.g. "0.55"), so coerce. Prefer the yes bid/ask midpoint; fall back to
        last price. Returns None if no usable price.
        """
        def _f(v):
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        bid = _f(market.get("yes_bid_dollars"))
        ask = _f(market.get("yes_ask_dollars"))
        prices = [p for p in (bid, ask) if p is not None]
        if len(prices) == 2:
            return (prices[0] + prices[1]) / 2.0
        if len(prices) == 1:
            return prices[0]
        last = _f(market.get("last_price_dollars"))
        if last is not None:
            return last
        return None

    @staticmethod
    def yes_team(market: dict) -> str:
        """The team this 'yes' contract pays on — cleanest from yes_sub_title."""
        return market.get("yes_sub_title") or ""

    @staticmethod
    def occurrence(market: dict):
        """
        Game start time (UTC datetime) from occurrence_datetime, or None.
        Kalshi returns ISO strings like '2026-08-14T18:20:00Z'. This is the
        anchor that ties a market to a specific GAME DATE — team names alone
        cannot, because the game series lists several days of markets at once.
        """
        from datetime import datetime, timezone
        raw = market.get("occurrence_datetime")
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def title_teams(market: dict) -> tuple[str, str] | None:
        """
        Both team strings from the market title, e.g.
        'St. Louis vs Chicago C Winner?' -> ('St. Louis', 'Chicago C').
        Returns None if the title doesn't look like 'A vs B ...'.
        """
        title = (market.get("title") or "").replace("Winner?", "").strip()
        for sep in (" vs ", " vs. ", " v "):
            if sep in title:
                a, b = title.split(sep, 1)
                return a.strip(), b.strip()
        return None

    SOCCER_GAME_SERIES = {"PL": "KXEPLGAME"}
    # The Tie legs across leagues share one constant strike UUID (observed
    # identical on EPL and MYSL samples 2026-08-17). yes_sub_title == "Tie"
    # is the primary detector; the UUID is a cross-check.
    TIE_STRIKE_UUID = "111193d4-9b1f-4bd8-ab7c-9de252737f05"

    @staticmethod
    def spread_dollars(market: dict) -> float | None:
        """Ask minus bid, in dollars. None if either side missing."""
        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        b, a = _f(market.get("yes_bid_dollars")), _f(market.get("yes_ask_dollars"))
        if b is None or a is None:
            return None
        return a - b

    @staticmethod
    def is_tie_market(market: dict) -> bool:
        if (market.get("yes_sub_title") or "").strip().lower() in ("tie", "draw"):
            return True
        strike = (market.get("custom_strike") or {}).get("soccer_team")
        return strike == KalshiAdapter.TIE_STRIKE_UUID
