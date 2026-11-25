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


# THE ROWS AN ADAPTER DROPS BEFORE COUNTING (ARCHITECT 2026-11-24, addendum 497 Q7), verbatim: "YES, COUNT FIRST. The
# rows an adapter drops before counting get a printed count with their causes in the command's own output; no exit
# changes with it." api_basketball's line (addendum 271) is the shape every adapter shares: a reason -> [provider ids]
# dict, kept on the adapter as `last_dropped`, and one plain line printed only when something was dropped. An id of
# None (the row names none) is counted but not listed.
def dropped_line(source: str, what: str, dropped: dict[str, list]) -> str | None:
    """"<source> /<what>: N listing(s) not read (reason n · reason n): id, id", or None when nothing was dropped."""
    if not dropped:
        return None
    parts = " · ".join(f"{why} {len(ids)}" for why, ids in dropped.items())
    ids = [str(i) for v in dropped.values() for i in v if i is not None]
    return (f"{source} /{what}: {sum(len(v) for v in dropped.values())} listing(s) not read ({parts})"
            + (f": {', '.join(ids)}" if ids else ""))


def report_dropped(owner, what: str, dropped: dict[str, list], source: str | None = None) -> None:
    """Law 4: a listing the adapter cannot place is counted on a printed line, never silent. Sets
    `owner.last_dropped = dropped` and prints dropped_line (source: `source`, else `owner.source_name`) when there is
    one, plainly, so a step's own output carries it before the command's summary."""
    owner.last_dropped = dropped
    line = dropped_line(source or owner.source_name, what, dropped)
    if line:
        print(line, flush=True)


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
