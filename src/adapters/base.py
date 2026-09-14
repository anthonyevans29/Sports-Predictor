"""
The adapter contract.

Every data source — Football-Data.org, API-Football, FlashScore, etc. —
implements this interface. The ingestion service depends ONLY on this
abstract class. Add a new source = subclass DataAdapter, register it
in the service.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedOdds,
    NormalizedTeam,
)
from src.db.schema import Sport


class DataAdapter(ABC):
    """Abstract data source adapter."""

    #: Stable identifier for this source. Used as the key in `external_ids`.
    source_name: str

    #: Sports this adapter supports. Used by the ingestion service to route requests.
    supported_sports: frozenset[Sport]

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @abstractmethod
    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        """Return all competitions this adapter can serve for the given sport."""

    @abstractmethod
    def list_teams(self, competition_code: str, season: str | None = None) -> list[NormalizedTeam]:
        """List teams participating in a competition (optionally in a given season)."""

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    @abstractmethod
    def list_matches(
        self,
        competition_code: str,
        season: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[NormalizedMatch]:
        """List matches. Supports season-based or date-range queries."""

    @abstractmethod
    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        """Detailed per-team stats for a single match. May return [] if not supported."""

    # ------------------------------------------------------------------
    # Odds (optional — return [] if the source doesn't carry odds)
    # ------------------------------------------------------------------

    def list_odds(self, match_source_id: str) -> list[NormalizedOdds]:
        """Bookmaker prices for a match. Override in odds-capable adapters."""
        return []

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def supports(self, sport: Sport) -> bool:
        return sport in self.supported_sports
