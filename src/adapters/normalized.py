"""
Source-agnostic data structures. Every adapter normalizes its API output
into these. The ingestion service only ever sees these — it has no idea
whether the data came from Football-Data.org, API-Football, or FlashScore.

Why dataclasses (not SQLAlchemy models)? Decoupling. Adapters produce data;
the ingestion service handles ORM concerns. Lets us test adapters without
a DB and lets us validate before persisting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.db.schema import MatchStatus, Result, Sport


@dataclass
class NormalizedCompetition:
    sport: Sport
    code: str
    name: str
    area: str
    type: str  # LEAGUE, CUP, INTL
    source: str  # which adapter produced this
    source_id: str  # the ID assigned by that source


@dataclass
class NormalizedTeam:
    sport: Sport
    name: str
    source: str
    source_id: str
    short_name: str | None = None
    tla: str | None = None
    area: str | None = None
    founded: int | None = None
    venue: str | None = None


@dataclass
class NormalizedMatch:
    sport: Sport
    competition_code: str  # e.g. "PL" — adapter must use the same code as its competition
    season: str  # "2024/25" or "2024" depending on sport
    utc_date: datetime
    status: MatchStatus
    home_team_source_id: str
    away_team_source_id: str
    source: str
    source_id: str

    matchday: int | None = None
    stage: str | None = None
    status_raw: str | None = None  # provider's status code verbatim (FT/AOT/AP/AET/PEN...)
    home_score: int | None = None
    away_score: int | None = None
    home_score_ht: int | None = None
    away_score_ht: int | None = None
    home_score_90: int | None = None  # soccer score.fulltime (90'); scores above include ET
    away_score_90: int | None = None
    full_time_result: Result | None = None
    venue: str | None = None
    referee: str | None = None
    # THE SERIES FIELDS (ARCHITECT 2026-10-18, addendum 130 item 2(b); #476, #478): statsapi's own seriesGameNumber,
    # gamesInSeries, seriesDescription and rescheduledFrom for THIS game, keyed by the matches column each is stored
    # in (src.db.database.SERIES_COLUMNS), None where the game's entry has none. None for the whole field = the
    # adapter reads no series fields (every adapter but statsapi, the api-sports fallback included): nothing is
    # written for the row.
    series: dict | None = None
    # THE SERVED ITEM, NOT KEPT (ARCHITECT 2026-11-06, addendum 274 item 2(10): "the transient reading STANDS; nothing
    # is kept, no file under exports/, no column"; 271 item 3(g) CORRECTED to "not persisted"). The provider's item
    # for THIS game as served, held on the normalized record for the sync's life only and not persisted: the
    # ingestion service never writes it (no column, no external_ids key, no file) and nothing on any path reads it
    # (no reader of a quarter exists; a lane that needs them declares the field when it exists). Filled by
    # api_basketball only; None everywhere else, so nothing changes for any other adapter.
    raw: dict | None = None
    # THE SETTLEMENT AS SERVED (ARCHITECT 2026-11-06, addendum 269 item 3(b): "'scalar' → [...] NO winner, the fraction
    # kept as the settlement value — it is the ledger's truth for any position"). {market ticker: {"result",
    # "settlement_value_dollars", "expiration_value"}}, each value verbatim as Kalshi serves it, for a KXATPMATCH /
    # KXWTAMATCH event with a settled market. The ingestion service writes it under the row's
    # external_ids["kalshi_settlement"] (SETTLEMENT_KEY); filled by kalshi_tennis only; None everywhere else, so nothing
    # changes for any other adapter.
    settlement: dict | None = None


@dataclass
class NormalizedMatchStats:
    """Per-team stats for one match."""

    match_source_id: str
    team_source_id: str
    source: str

    shots: int | None = None
    shots_on_target: int | None = None
    possession_pct: float | None = None
    corners: int | None = None
    fouls: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    xg: float | None = None
    extra_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedOdds:
    match_source_id: str
    source: str  # the odds-data source (e.g. "the_odds_api")
    bookmaker: str
    market: str
    selection: str
    price_decimal: float
    captured_at: datetime
    is_opening: bool = False
    is_closing: bool = False
    #: Handicap/total line (NFL spreads & totals; added 2026-09-05, NFL phase 1)
    line: float | None = None
    #: The provider's own time for the game's odds (ARCHITECT 2026-10-09,
    #: addendum 32 items 3-4): american football's response[].update, and
    #: api-football's (#615, addendum 147 item 1), naive UTC. The newest
    #: any quote in the answer can be; a quote may be older.
    #: Never the time of a quote, never our clock. None = unknown (absent,
    #: unreadable, or a provider whose payload carries no such field).
    source_updated_at: datetime | None = None
