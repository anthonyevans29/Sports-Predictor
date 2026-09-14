"""
FlashScore adapter — STUB.

FlashScore has no official API and scraping it violates their ToS.
Implemented in Phase 2 as an OPTIONAL supplementary source:
  - Live in-play stats for matches already in our DB
  - Match details for competitions our primary API doesn't cover (FA Cup, etc.)

Implementation will use Playwright with aggressive rate limiting and
caching to minimize requests. The adapter pattern means the rest of the
app is unaffected by whether FlashScore is available or not.

DO NOT use this as a primary data source. It will break.
"""
from __future__ import annotations

from src.adapters.base import DataAdapter
from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedTeam,
)
from src.db.schema import Sport


class FlashScoreAdapter(DataAdapter):
    source_name = "flashscore"
    supported_sports = frozenset({Sport.SOCCER})

    def list_competitions(self, sport: Sport) -> list[NormalizedCompetition]:
        raise NotImplementedError("FlashScore adapter is a Phase 2 stub.")

    def list_teams(self, competition_code: str, season: str | None = None) -> list[NormalizedTeam]:
        raise NotImplementedError("FlashScore adapter is a Phase 2 stub.")

    def list_matches(
        self,
        competition_code: str,
        season: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[NormalizedMatch]:
        raise NotImplementedError("FlashScore adapter is a Phase 2 stub.")

    def get_match_stats(self, match_source_id: str) -> list[NormalizedMatchStats]:
        raise NotImplementedError("FlashScore adapter is a Phase 2 stub.")
