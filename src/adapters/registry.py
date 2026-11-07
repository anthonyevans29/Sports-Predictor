"""
Adapter registry.

Soccer goes through API-Football; MLB goes through the official MLB Stats API.
Add new sport adapters by registering them here — call sites don't change.
"""
from __future__ import annotations

from src.adapters.api_football import APIFootballAdapter
from src.adapters.api_american_football import APIAmericanFootballAdapter
from src.adapters.api_basketball import APIBasketballAdapter
from src.adapters.api_hockey import APIHockeyAdapter
from src.adapters.base import DataAdapter
from src.adapters.kalshi_tennis import KalshiTennisAdapter
from src.adapters.mlb_stats_api import MLBStatsAPIAdapter

_REGISTRY: dict[str, type[DataAdapter]] = {
    APIHockeyAdapter.source_name: APIHockeyAdapter,
    APIFootballAdapter.source_name: APIFootballAdapter,
    APIAmericanFootballAdapter.source_name: APIAmericanFootballAdapter,
    MLBStatsAPIAdapter.source_name: MLBStatsAPIAdapter,
    APIBasketballAdapter.source_name: APIBasketballAdapter,     # addendum 271 item 3(a), lane basketball-market-only
    KalshiTennisAdapter.source_name: KalshiTennisAdapter,       # addendum 261 item 2(c), 269 items 1-3: lane tennis
}

#: The default adapter for a given sport. CLI/web use this when no
#: explicit source is passed. We accept both Sport enum values ("mlb")
#: and friendly-name aliases ("baseball") so callers can use either.
DEFAULT_FOR_SPORT: dict[str, str] = {
    "soccer": APIFootballAdapter.source_name,
    "baseball": MLBStatsAPIAdapter.source_name,
    "nfl": APIAmericanFootballAdapter.source_name,
    "nhl": APIHockeyAdapter.source_name,
    "hockey": APIHockeyAdapter.source_name,
    "mlb": MLBStatsAPIAdapter.source_name,
    "basketball": APIBasketballAdapter.source_name,             # Sport.BASKETBALL's value (sync-competitions --sport)
    "tennis": KalshiTennisAdapter.source_name,                  # Sport.TENNIS's value: Kalshi is the fixture source (269)
}


def available_sources() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_adapter(source: str | None = None, sport: str = "soccer") -> DataAdapter:
    """
    Resolve an adapter.

    - If `source` is given, return that adapter.
    - Otherwise return the default for the sport.
    """
    if source is None:
        source = DEFAULT_FOR_SPORT.get(sport)
        if source is None:
            raise ValueError(f"No default adapter registered for sport '{sport}'.")
    if source not in _REGISTRY:
        raise ValueError(
            f"Unknown adapter source '{source}'. Available: {available_sources()}"
        )
    return _REGISTRY[source]()
