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
    def ticker_start(market: dict):
        """
        Game start (naive UTC) from the ticker's ET stamp, or None. MLB tickers
        carry the scheduled first pitch: KXMLBGAME-26OCT012000PHIATL-PHI is
        2026-10-01 20:00 ET = 2026-10-02 00:00Z (M13, 2026-08-25; verified on
        the observed tickers). Unparseable -> None, never a guess.
        """
        import re
        from datetime import datetime
        from zoneinfo import ZoneInfo
        m = re.search(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
                      r"(\d{2})(\d{2})(\d{2})[A-Z]", market.get("ticker") or "")
        if not m:
            return None
        mon = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP",
               "OCT", "NOV", "DEC"].index(m.group(2)) + 1
        try:
            et = datetime(2000 + int(m.group(1)), mon, int(m.group(3)), int(m.group(4)),
                          int(m.group(5)), tzinfo=ZoneInfo("America/New_York"))
        except ValueError:
            return None
        return et.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

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

    # UNL PINNED (ARCHITECT 2026-10-05): discovery refused on 2 candidates,
    # KXUEFANLGAME and KXCONCACAFNLGAME; "UNL pins KXUEFANLGAME (the competition
    # is UEFA's)". Mapped here, so the window chain needs no --series flag.
    # soccer-expansion-v1 PINNED (ARCHITECT 2026-10-07, from the operator's
    # kalshi-probe receipt, 131 series matched): "PD -> KXLALIGAGAME; SA ->
    # KXSERIEAGAME (not KXBBSERIEAGAME, KXSERIEAWGAME or KXBRASILEIROGAME);
    # BL1 -> KXBUNDESLIGAGAME (not KXBUNDESLIGA2GAME, KXBBLGAME or
    # KXWDBBLGAME); FL1 -> KXLIGUE1GAME; ELC -> KXEFLCHAMPIONSHIPGAME ... A
    # pinned series never makes a league live." Capture only: the shadow chain
    # syncs them (deploy/hosting/chains.py KALSHI_CAPTURE_ONLY); nothing exports
    # those leagues' rows to the Desk until soccer-expansion-v1 is CONFIRMED.
    SOCCER_GAME_SERIES = {"PL": "KXEPLGAME", "UNL": "KXUEFANLGAME",
                          "PD": "KXLALIGAGAME", "SA": "KXSERIEAGAME", "BL1": "KXBUNDESLIGAGAME",
                          "FL1": "KXLIGUE1GAME", "ELC": "KXEFLCHAMPIONSHIPGAME"}
    # Ruled series with no wired competition or chain: recorded, never synced.
    # resolve_soccer_series refuses them, naming the series and the ruling.
    SOCCER_SERIES_RESERVED = {"CNL": "KXCONCACAFNLGAME",
                              "EL1": "KXEFLL1GAME", "EFL": "KXEFLCUPGAME", "CZE": "KXCZEFLGAME"}
    SOCCER_SERIES_RESERVED_RULING = {"CNL": "ARCHITECT 2026-10-05, 'for later'",
                                     "EL1": "ARCHITECT 2026-10-07, 'recorded, not wired'",
                                     "EFL": "ARCHITECT 2026-10-07, 'recorded, not wired'",
                                     "CZE": "ARCHITECT 2026-10-07, 'recorded, not wired'"}
    # ARCHITECT 2026-10-04: a competition with Kalshi markets but no receipted
    # ticker has its series DISCOVERED from Kalshi's own /series listing at run
    # time (law 1: vocabulary from the API, never guessed). The keywords select
    # candidates; only game-winner series (ticker ending "GAME", like every
    # wired series) count; exactly one or the sync refuses. UNL used this until
    # its 2026-10-05 pin; no competition uses it now.
    SOCCER_SERIES_DISCOVERY: dict[str, list[str]] = {}

    def resolve_soccer_series(self, competition_code: str, override: str | None = None
                              ) -> tuple[str | None, str]:
        """(series ticker | None, how it was resolved — a receipt line)."""
        if override:
            return override, f"series {override} (operator --series)"
        if competition_code in self.SOCCER_GAME_SERIES:
            return self.SOCCER_GAME_SERIES[competition_code], "mapped"
        if competition_code in self.SOCCER_SERIES_RESERVED:
            return None, (f"{competition_code}: series {self.SOCCER_SERIES_RESERVED[competition_code]} is reserved "
                          f"({self.SOCCER_SERIES_RESERVED_RULING[competition_code]}), not wired — no sync until it is")
        kws = self.SOCCER_SERIES_DISCOVERY.get(competition_code)
        if not kws:
            return None, f"no Kalshi series mapped or discoverable for {competition_code}"
        found = self.find_series(kws)
        games = sorted({s.get("ticker") for s in found if str(s.get("ticker", "")).upper().endswith("GAME")})
        listed = ", ".join(f"{s.get('ticker')} ({s.get('title')})" for s in found[:12]) or "none"
        if len(games) == 1:
            return games[0], f"discovered {games[0]} from /series {kws} (candidates: {listed})"
        return None, (f"{competition_code}: {len(games)} game series match {kws} — REFUSED (exactly one "
                      f"required; candidates: {listed}). Pin it with --series once receipted.")
    # The Tie legs across leagues share one constant strike UUID (observed
    # identical on EPL and MYSL samples 2026-08-17). yes_sub_title == "Tie"
    # is the primary detector; the UUID is a cross-check.
    TIE_STRIKE_UUID = "111193d4-9b1f-4bd8-ab7c-9de252737f05"

    @staticmethod
    def yes_quotes(market: dict) -> tuple[float | None, float | None]:
        """(yes_bid, yes_ask) in dollars (0.00-1.00), each None when absent.
        K-track (2026-09-27): stored per snapshot so executable edge can be
        computed against the ask, not the midpoint."""
        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        return _f(market.get("yes_bid_dollars")), _f(market.get("yes_ask_dollars"))

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
