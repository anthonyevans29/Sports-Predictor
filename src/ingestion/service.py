"""
Ingestion service.

Pulls data from adapters and persists it via SQLAlchemy.
Handles upserts on (source, source_id) so re-running a sync doesn't duplicate.

Design:
  - Service takes ONE adapter at a time. Multi-source orchestration is the
    caller's job (CLI / scheduler).
  - Idempotent: matches/teams/competitions are matched by external_ids[source].
  - Returns counts (created, updated) for visibility.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adapters.base import DataAdapter
from src.adapters.normalized import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedMatchStats,
    NormalizedTeam,
)
from src.db.database import session_scope
from src.db.schema import (
    Competition,
    CompetitionTeam,
    Injury,
    Lineup,
    Match,
    MatchParticipant,
    MatchStats,
    MatchStatus,
    Player,
    PlayerGameLog,
    Sport,
    Team,
)

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def __str__(self) -> str:
        return f"created={self.created} updated={self.updated} skipped={self.skipped}"


class IngestionService:
    def __init__(self, adapter: DataAdapter):
        self.adapter = adapter
        self.source = adapter.source_name

    # ------------------------------------------------------------------
    # Competitions
    # ------------------------------------------------------------------

    def sync_competitions(self, sport: Sport) -> SyncResult:
        comps = self.adapter.list_competitions(sport)
        result = SyncResult()
        with session_scope() as s:
            for nc in comps:
                self._upsert_competition(s, nc, result)
        log.info("sync_competitions: %s", result)
        return result

    def _upsert_competition(
        self, s: Session, nc: NormalizedCompetition, result: SyncResult
    ) -> Competition:
        # Match by (sport, code) — competitions are stable globally
        stmt = select(Competition).where(
            Competition.sport == nc.sport, Competition.code == nc.code
        )
        existing = s.execute(stmt).scalar_one_or_none()

        if existing:
            existing.name = nc.name
            existing.area = nc.area
            existing.type = nc.type
            ext = dict(existing.external_ids or {})
            ext[nc.source] = nc.source_id
            existing.external_ids = ext
            result.updated += 1
            return existing

        comp = Competition(
            sport=nc.sport,
            code=nc.code,
            name=nc.name,
            area=nc.area,
            type=nc.type,
            external_ids={nc.source: nc.source_id},
        )
        s.add(comp)
        s.flush()  # populate ID for downstream FKs in same transaction
        result.created += 1
        return comp

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------

    def sync_teams(self, competition_code: str, season: str | None = None) -> SyncResult:
        teams = self.adapter.list_teams(competition_code, season)
        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                log.warning(
                    "Competition %s not in DB; run sync_competitions first.", competition_code
                )
                result.skipped = len(teams)
                return result

            for nt in teams:
                team = self._upsert_team(s, nt, result)
                if season:
                    self._link_team_to_competition(s, team, comp, season)
        log.info("sync_teams(%s): %s", competition_code, result)
        return result

    def _upsert_team(self, s: Session, nt: NormalizedTeam, result: SyncResult) -> Team:
        team = self._find_team_by_source(s, nt.sport, nt.source, nt.source_id)

        if team:
            team.name = nt.name
            team.short_name = nt.short_name or team.short_name
            team.tla = nt.tla or team.tla
            team.area = nt.area or team.area
            team.founded = nt.founded or team.founded
            team.venue = nt.venue or team.venue
            ext = dict(team.external_ids or {})
            ext[nt.source] = nt.source_id
            team.external_ids = ext
            result.updated += 1
            return team

        team = Team(
            sport=nt.sport,
            name=nt.name,
            short_name=nt.short_name,
            tla=nt.tla,
            area=nt.area,
            founded=nt.founded,
            venue=nt.venue,
            external_ids={nt.source: nt.source_id},
        )
        s.add(team)
        s.flush()
        result.created += 1
        return team

    @staticmethod
    def _find_team_by_source(
        s: Session, sport: Sport, source: str, source_id: str
    ) -> Team | None:
        # JSON containment on SQLite is limited — fetch all teams of this sport and filter.
        # Fine for now (hundreds of teams); revisit if it gets slow.
        stmt = select(Team).where(Team.sport == sport)
        for team in s.execute(stmt).scalars():
            if (team.external_ids or {}).get(source) == source_id:
                return team
        return None

    @staticmethod
    def _link_team_to_competition(
        s: Session, team: Team, comp: Competition, season: str
    ) -> None:
        existing = s.get(CompetitionTeam, {"competition_id": comp.id, "team_id": team.id, "season": season})
        if not existing:
            s.add(CompetitionTeam(competition_id=comp.id, team_id=team.id, season=season))

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    def sync_matches(
        self,
        competition_code: str,
        season: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        progress=None,
    ) -> SyncResult:
        def _report(msg):
            if progress is not None:
                progress(msg)

        _report(f"Fetching match list for {competition_code} "
                f"({season or 'all'})… (this is the slow part — one API call)")
        matches = self.adapter.list_matches(competition_code, season, date_from, date_to)
        _report(f"Fetched {len(matches)} matches. Writing to DB…")

        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                log.warning(
                    "Competition %s not in DB; run sync_competitions first.", competition_code
                )
                result.skipped = len(matches)
                return result

            total = len(matches)
            step = max(1, total // 10)  # report ~10 times through the loop
            for i, nm in enumerate(matches, 1):
                self._upsert_match(s, nm, comp, result)
                if i % step == 0 or i == total:
                    pct = int(i / total * 100) if total else 100
                    _report(f"  …{i}/{total} ({pct}%) — "
                            f"created {result.created}, updated {result.updated}, "
                            f"skipped {result.skipped}")
        _sk = getattr(result, "_skipped_ids", None)
        if _sk:
            log.warning(
                "sync_matches(%s): skipped %d listing(s) whose team(s) are not "
                "in DB (ids %s..%s). Run sync-teams for %s if these are real "
                "fixtures; recurring identical skips are an upstream listing "
                "quirk (see backlog M12).",
                competition_code, len(_sk), min(_sk), max(_sk), competition_code)
        log.info("sync_matches(%s): %s", competition_code, result)
        _report("Done.")
        return result

    def _upsert_match(
        self, s: Session, nm: NormalizedMatch, comp: Competition, result: SyncResult
    ) -> Match | None:
        home = self._find_team_by_source(s, nm.sport, nm.source, nm.home_team_source_id)
        away = self._find_team_by_source(s, nm.sport, nm.source, nm.away_team_source_id)
        if not home or not away:
            # M12 aggregation (2026-09-01): the same 53 MLB listings warned
            # individually every morning for two weeks. Per-match detail goes
            # to DEBUG; the caller emits ONE summary line with the id range.
            log.debug("Skipping match %s: team(s) not in DB (comp %s).",
                      nm.source_id, comp.code)
            _skipped = getattr(result, "_skipped_ids", None)
            if _skipped is None:
                _skipped = []
                try:
                    result._skipped_ids = _skipped
                except Exception:
                    pass
            _skipped.append(str(nm.source_id))
            result.skipped += 1
            return None

        match = self._find_match_by_source(s, nm.source, nm.source_id)

        if match:
            self._apply_match_updates(match, nm)
            ext = dict(match.external_ids or {})
            ext[nm.source] = nm.source_id
            match.external_ids = ext
            result.updated += 1
            return match

        match = Match(
            sport=nm.sport,
            competition_id=comp.id,
            season=nm.season,
            matchday=nm.matchday,
            stage=nm.stage,
            utc_date=nm.utc_date,
            status=nm.status,
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=nm.home_score,
            away_score=nm.away_score,
            home_score_ht=nm.home_score_ht,
            away_score_ht=nm.away_score_ht,
            full_time_result=nm.full_time_result,
            venue=nm.venue,
            referee=nm.referee,
            external_ids={nm.source: nm.source_id},
        )
        s.add(match)
        result.created += 1
        return match

    @staticmethod
    def _apply_match_updates(match: Match, nm: NormalizedMatch) -> None:
        match.status = nm.status
        # Correct the season if the adapter now reports a different one. This
        # matters for re-syncs that fix a previously mis-stamped season (e.g.
        # the single-year-tournament fix: "2026/27" → "2026"). Guard against
        # blanking it if the adapter returns an empty season.
        if nm.season and nm.season != match.season:
            match.season = nm.season
        match.matchday = nm.matchday or match.matchday
        match.stage = nm.stage or match.stage
        match.utc_date = nm.utc_date
        # Only overwrite scores when present (don't blank a finished match)
        if nm.home_score is not None:
            match.home_score = nm.home_score
        if nm.away_score is not None:
            match.away_score = nm.away_score
        if nm.home_score_ht is not None:
            match.home_score_ht = nm.home_score_ht
        if nm.away_score_ht is not None:
            match.away_score_ht = nm.away_score_ht
        if nm.full_time_result is not None:
            match.full_time_result = nm.full_time_result
        if nm.referee:
            match.referee = nm.referee

    @staticmethod
    def _find_match_by_source(s: Session, source: str, source_id: str) -> Match | None:
        # Same caveat as teams — full scan on JSON. Fine for now.
        stmt = select(Match)
        for match in s.execute(stmt).scalars():
            if (match.external_ids or {}).get(source) == source_id:
                return match
        return None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_competition(s: Session, code: str) -> Competition | None:
        return s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Match stats
    # ------------------------------------------------------------------

    def persist_match_stats(
        self,
        s: Session,
        match_id: int,
        stats_list: list[NormalizedMatchStats],
        source: str,
    ) -> int:
        """
        Write per-team stats for a match. Upserts on (match_id, team_id).
        Returns the number of stats rows written/updated.
        """
        written = 0
        match = s.get(Match, match_id)
        if not match:
            log.warning("Match %d not found; skipping stats.", match_id)
            return 0

        for ns in stats_list:
            # Resolve team via its external source id
            team = self._find_team_by_source(s, match.sport, source, ns.team_source_id)
            if not team:
                log.warning(
                    "Stats for unknown team (source=%s source_id=%s); skipping.",
                    source, ns.team_source_id,
                )
                continue

            # Find existing stats row for this match/team
            existing = s.execute(
                select(MatchStats).where(
                    MatchStats.match_id == match_id,
                    MatchStats.team_id == team.id,
                )
            ).scalar_one_or_none()

            if existing:
                # Overwrite known fields; merge extra_stats
                for col in (
                    "shots", "shots_on_target", "possession_pct", "corners",
                    "fouls", "yellow_cards", "red_cards", "xg",
                ):
                    val = getattr(ns, col)
                    if val is not None:
                        setattr(existing, col, val)
                merged = dict(existing.extra_stats or {})
                merged.update(ns.extra_stats or {})
                existing.extra_stats = merged
            else:
                s.add(MatchStats(
                    match_id=match_id,
                    team_id=team.id,
                    shots=ns.shots,
                    shots_on_target=ns.shots_on_target,
                    possession_pct=ns.possession_pct,
                    corners=ns.corners,
                    fouls=ns.fouls,
                    yellow_cards=ns.yellow_cards,
                    red_cards=ns.red_cards,
                    xg=ns.xg,
                    extra_stats=ns.extra_stats or {},
                ))
            written += 1
        return written

    def sync_match_stats(
        self,
        competition_code: str,
        season: str | None = None,
        limit: int | None = None,
    ) -> SyncResult:
        """
        Fetch per-team match stats from this adapter for finished matches
        in the given competition+season. Only fetches stats for matches that
        already have a source_id from this adapter (i.e. that have been
        loaded via this source). Useful for stats-enrichment runs.

        `limit` caps the number of fixtures hit — important on the API-Football
        free tier (100 req/day).
        """
        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                log.warning("Competition %s not in DB.", competition_code)
                return result

            # Find finished matches in this competition/season that have a
            # source_id from this adapter AND don't yet have stats in DB.
            stmt = select(Match).where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.FINISHED,
            )
            if season:
                stmt = stmt.where(Match.season == season)

            candidates: list[Match] = []
            for match in s.execute(stmt).scalars():
                source_id = (match.external_ids or {}).get(self.source)
                if not source_id:
                    continue
                # Skip if we already have stats from any source
                existing = s.execute(
                    select(MatchStats).where(MatchStats.match_id == match.id)
                ).first()
                if existing:
                    continue
                candidates.append(match)

            if limit:
                candidates = candidates[:limit]

            log.info(
                "sync_match_stats: %d matches to enrich (competition=%s, season=%s)",
                len(candidates), competition_code, season,
            )

            for match in candidates:
                source_id = match.external_ids[self.source]
                try:
                    stats_list = self.adapter.get_match_stats(source_id)
                except Exception as e:
                    log.warning("Stats fetch failed for match %d (%s): %s", match.id, source_id, e)
                    result.skipped += 1
                    continue
                if not stats_list:
                    result.skipped += 1
                    continue
                written = self.persist_match_stats(s, match.id, stats_list, self.source)
                if written:
                    result.created += 1
                else:
                    result.skipped += 1
        log.info("sync_match_stats(%s): %s", competition_code, result)
        return result

    def sync_player_match_stats(
        self,
        competition_code: str,
        season: str | None = None,
        limit: int | None = None,
    ) -> SyncResult:
        """
        Phase 13: per-player, per-match stat lines (PlayerGameLog) for
        finished matches — the raw material player-prop projections are
        built from. Mirrors sync_match_stats but at player granularity via
        adapter.get_fixture_player_stats().

        Only adapters that expose get_fixture_player_stats support this
        (currently API-Football / soccer). Skips matches already logged.
        """
        if not hasattr(self.adapter, "get_fixture_player_stats"):
            log.info("Adapter %s doesn't expose get_fixture_player_stats.", self.source)
            return SyncResult()

        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                log.warning("Competition %s not in DB.", competition_code)
                return result

            stmt = select(Match).where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.FINISHED,
            )
            if season:
                stmt = stmt.where(Match.season == season)

            candidates: list[Match] = []
            for match in s.execute(stmt).scalars():
                source_id = (match.external_ids or {}).get(self.source)
                if not source_id:
                    continue
                existing = s.execute(
                    select(PlayerGameLog).where(PlayerGameLog.match_id == match.id)
                ).first()
                if existing:
                    continue
                candidates.append(match)

            if limit:
                candidates = candidates[:limit]

            log.info(
                "sync_player_match_stats: %d matches to fetch (competition=%s, season=%s)",
                len(candidates), competition_code, season,
            )

            for match in candidates:
                source_id = match.external_ids[self.source]
                try:
                    rows = self.adapter.get_fixture_player_stats(source_id)
                except Exception as e:
                    log.warning("Player stats fetch failed for match %d (%s): %s", match.id, source_id, e)
                    result.skipped += 1
                    continue
                if not rows:
                    result.skipped += 1
                    continue

                written = self._persist_player_game_logs(s, match, rows)
                if written:
                    result.created += written
                else:
                    result.skipped += 1
        log.info("sync_player_match_stats(%s): %s", competition_code, result)
        return result

    def _persist_player_game_logs(self, s: Session, match: Match, rows: list[dict]) -> int:
        """Get-or-create the Player (by sport+source+source_id, same rule as
        sync_players) for each row, then upsert one PlayerGameLog per player
        for this match."""
        written = 0
        for row in rows:
            sid = row.get("player_source_id")
            name = row.get("player_name")
            team_source_id = row.get("team_source_id")
            if not sid or not name or not team_source_id:
                continue

            team = s.execute(
                select(Team).where(Team.external_ids[self.source].as_string() == team_source_id)
            ).scalar_one_or_none()
            if team is None:
                continue

            player = s.execute(
                select(Player).where(
                    Player.sport == match.sport,
                    Player.external_ids[self.source].as_string() == sid,
                )
            ).scalar_one_or_none()
            if player is None:
                # SQLite's JSON operator doesn't always behave (same caveat
                # as sync_players) — fall back to a Python-side filter by
                # name before concluding this is really a new player.
                for cand in s.execute(
                    select(Player).where(Player.sport == match.sport, Player.name == name)
                ).scalars():
                    if (cand.external_ids or {}).get(self.source) == sid:
                        player = cand
                        break
            if player is None:
                player = Player(
                    sport=match.sport,
                    name=name,
                    team_id=team.id,
                    external_ids={self.source: sid},
                )
                s.add(player)
                s.flush()

            is_home = team.id == match.home_team_id
            opponent_team_id = match.away_team_id if is_home else match.home_team_id

            existing_log = s.execute(
                select(PlayerGameLog).where(
                    PlayerGameLog.player_id == player.id,
                    PlayerGameLog.match_id == match.id,
                )
            ).scalar_one_or_none()
            if existing_log is None:
                s.add(PlayerGameLog(
                    player_id=player.id,
                    match_id=match.id,
                    team_id=team.id,
                    opponent_team_id=opponent_team_id,
                    is_home=is_home,
                    game_date=match.utc_date,
                    minutes=row.get("minutes"),
                    stats=row.get("stats") or {},
                    source=self.source,
                ))
                written += 1
        return written

    def sync_odds(
        self,
        competition_code: str,
        season: str | None = None,
        limit: int | None = None,
        upcoming_only: bool = True,
    ) -> SyncResult:
        """
        Pull bookmaker odds for fixtures from this adapter.

        upcoming_only=True (default) limits to SCHEDULED matches — odds for
        finished matches are still useful for backtesting but cost API budget
        we usually don't want to spend.
        """
        from datetime import datetime
        from src.db.schema import Odds

        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                log.warning("Competition %s not in DB.", competition_code)
                return result

            stmt = select(Match).where(Match.competition_id == comp.id)
            if season:
                stmt = stmt.where(Match.season == season)
            if upcoming_only:
                stmt = stmt.where(
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= datetime.utcnow(),
                )
            candidates: list[Match] = []
            for match in s.execute(stmt).scalars():
                source_id = (match.external_ids or {}).get(self.source)
                if not source_id:
                    continue
                candidates.append(match)

            if limit:
                candidates = candidates[:limit]

            log.info("sync_odds: %d matches (competition=%s, season=%s)",
                     len(candidates), competition_code, season)

            for match in candidates:
                source_id = match.external_ids[self.source]
                try:
                    odds_list = self.adapter.list_odds(source_id)
                except Exception as e:
                    log.warning("Odds fetch failed for match %d: %s", match.id, e)
                    result.skipped += 1
                    continue
                if not odds_list:
                    result.skipped += 1
                    continue
                for no in odds_list:
                    s.add(Odds(
                        match_id=match.id,
                        bookmaker=no.bookmaker,
                        market=no.market,
                        selection=no.selection,
                        price_decimal=no.price_decimal,
                        captured_at=no.captured_at,
                        source=self.source,
                    ))
                result.created += 1
        log.info("sync_odds(%s): %s", competition_code, result)
        return result

    def sync_injuries(
        self,
        competition_code: str,
        season: str,
    ) -> SyncResult:
        """
        Refresh the injuries table for every team in a competition+season.

        Costs 1 API request per team (so ~20 for the PL). Old rows for each
        team are deleted and replaced — we treat the upstream feed as source
        of truth and don't track injury history.
        """
        from datetime import datetime
        from src.db.schema import CompetitionTeam, Injury

        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                log.warning("Competition %s not in DB.", competition_code)
                return result

            # Teams active in this competition/season
            teams_q = (
                select(Team)
                .join(CompetitionTeam, CompetitionTeam.team_id == Team.id)
                .where(
                    CompetitionTeam.competition_id == comp.id,
                    CompetitionTeam.season == season,
                )
            )
            teams = list(s.execute(teams_q).scalars())

            now = datetime.utcnow()
            for team in teams:
                self._sync_injuries_for_team(s, team, season, now, result)

        log.info("sync_injuries(%s): %s", competition_code, result)
        return result

    def sync_injuries_for_teams(
        self,
        team_ids: list[int],
        season: str,
    ) -> SyncResult:
        """
        Targeted version: refresh injuries for specific teams only.
        Used by the per-match refresh button — when only 2 teams are
        playing, hitting the API for all 20 PL teams is wasteful.
        """
        from datetime import datetime
        result = SyncResult()
        if not team_ids:
            return result
        with session_scope() as s:
            teams = list(s.execute(
                select(Team).where(Team.id.in_(team_ids))
            ).scalars())
            now = datetime.utcnow()
            for team in teams:
                self._sync_injuries_for_team(s, team, season, now, result)
        log.info("sync_injuries_for_teams(%s): %s", team_ids, result)
        return result

    def _sync_injuries_for_team(
        self, s, team, season: str, now, result: SyncResult,
    ) -> None:
        """Fetch and write injuries for a single team. Mutates `result`.

        Filters to *currently active* injuries: keep only the latest entry
        per player (adapter already dedupes), and drop entries whose fixture
        date is more than 14 days old (the player has presumably recovered
        and the API just hasn't dropped the historical record).
        """
        from datetime import datetime as _dt, timedelta as _td
        from src.db.schema import Injury

        source_id = (team.external_ids or {}).get(self.source)
        if not source_id:
            result.skipped += 1
            return
        try:
            injuries = self.adapter.list_injuries(source_id, season)
        except Exception as e:
            log.warning("Injury fetch failed for team %d: %s", team.id, e)
            result.skipped += 1
            return

        # Cutoff for "still active" — only keep injuries from the past 14 days
        # or fixtures still in the future. Injuries with no fixture_date keep
        # by default (defensive — we'd rather over-include than silently drop).
        STALE_INJURY_DAYS = 14
        cutoff = now - _td(days=STALE_INJURY_DAYS)

        # Wipe and replace this team's injuries
        s.query(Injury).filter(Injury.team_id == team.id).delete()
        kept = 0
        for inj in injuries:
            pname = inj.get("player_name")
            if not pname or not str(pname).strip():
                result.skipped += 1
                continue

            # Filter stale
            fixture_date_str = inj.get("fixture_date")
            if fixture_date_str:
                try:
                    fdate = _dt.fromisoformat(fixture_date_str.replace("Z", "+00:00"))
                    # Make naive (drop tz) so we can compare to `now`, which is naive
                    fdate = fdate.replace(tzinfo=None)
                    if fdate < cutoff:
                        # Stale record — player is most likely back. Skip.
                        result.skipped += 1
                        continue
                except (ValueError, AttributeError):
                    pass  # keep on parse failure

            s.add(Injury(
                team_id=team.id,
                player_name=str(pname).strip(),
                player_position=inj.get("player_position"),
                reason=inj.get("reason"),
                type=inj.get("type"),
                fixture_source_id=inj.get("fixture_source_id"),
                source=self.source,
                refreshed_at=now,
            ))
            result.created += 1
            kept += 1
        log.debug("team %d (%s): kept %d active injuries", team.id, team.name, kept)

    def sync_lineups(
        self,
        competition_code: str,
        season: str,
        limit: int = 30,
        on_log=None,
        only_match_id: int | None = None,
    ) -> SyncResult:
        """
        Pull lineups for upcoming matches in the given competition/season.

        Per-match logic:
          - If kickoff is within `CONFIRMED_LINEUP_WINDOW_MINUTES`, try to
            pull the confirmed lineup. If API has no data yet, fall back to projected.
          - Otherwise, build a projected lineup from each team's recent starters.

        If `only_match_id` is set, syncs that single match and ignores `limit`.
        Used by the per-match refresh button.

        result counts use a slight reinterpretation:
          - created  = projected lineups written
          - updated  = confirmed lineups written (overwrote projection)
          - skipped  = matches we couldn't process (no source_id, API error, etc.)
        """
        from datetime import datetime, timedelta
        from src.db.schema import Lineup

        CONFIRMED_LINEUP_WINDOW_MINUTES = 60  # API populates ~1hr pre-kickoff
        PROJECTED_LINEUP_LOOKAHEAD_DAYS = 7

        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                _log(f"competition {competition_code} not in DB")
                return result

            now = datetime.utcnow()
            window_end = now + timedelta(days=PROJECTED_LINEUP_LOOKAHEAD_DAYS)
            confirmed_cutoff = now + timedelta(minutes=CONFIRMED_LINEUP_WINDOW_MINUTES)

            match_q = (
                select(Match)
                .where(
                    Match.competition_id == comp.id,
                    Match.season == season,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now,
                    Match.utc_date <= window_end,
                )
                .order_by(Match.utc_date.asc())
                .limit(limit)
            )
            matches = list(s.execute(match_q).scalars())

            if only_match_id is not None:
                # Re-run with single-match filter, ignoring the window/limit.
                # A user manually refreshing wants to refresh THIS match even
                # if it's outside the default lookahead window.
                matches = list(s.execute(
                    select(Match).where(
                        Match.id == only_match_id,
                        Match.status == MatchStatus.SCHEDULED,
                    )
                ).scalars())

            if not matches:
                _log("no upcoming matches in window")
                return result

            _log(f"processing {len(matches)} upcoming matches")

            for match in matches:
                fixture_source_id = (match.external_ids or {}).get(self.source)
                if not fixture_source_id:
                    result.skipped += 1
                    continue

                kickoff_soon = match.utc_date <= confirmed_cutoff

                # Try confirmed lineup first if kickoff is close
                lineup_data: list[dict] = []
                lineup_kind = "projected"
                if kickoff_soon:
                    try:
                        lineup_data = self.adapter.list_lineup_confirmed(fixture_source_id)
                        if lineup_data:
                            lineup_kind = "confirmed"
                    except Exception as e:
                        _log(f"  ✗ confirmed lineup fetch failed for match {match.id}: {e}")

                # Fall back to projected
                if not lineup_data:
                    for team in (match.home_team, match.away_team):
                        if not team:
                            continue
                        team_source_id = (team.external_ids or {}).get(self.source)
                        if not team_source_id:
                            continue
                        try:
                            recent = self.adapter.list_recent_starters(
                                team_source_id, season, n=5
                            )
                            lineup_data.extend(recent)
                        except Exception as e:
                            _log(f"  ✗ projected lineup failed for team {team.id}: {e}")
                    lineup_kind = "projected"

                if not lineup_data:
                    result.skipped += 1
                    continue

                # Wipe old lineups for this match and re-insert
                s.query(Lineup).filter(Lineup.match_id == match.id).delete()
                # Resolve team_source_id → team_id
                source_to_team_id: dict[str, int] = {}
                for team in (match.home_team, match.away_team):
                    if team is None:
                        continue
                    sid = (team.external_ids or {}).get(self.source)
                    if sid:
                        source_to_team_id[str(sid)] = team.id

                written_this_match = 0
                for row in lineup_data:
                    team_id = source_to_team_id.get(row["team_source_id"])
                    if team_id is None:
                        continue
                    pname = row.get("player_name")
                    if not pname or not str(pname).strip():
                        # Skip malformed slots — Lineup.player_name is NOT NULL
                        continue
                    s.add(Lineup(
                        match_id=match.id,
                        team_id=team_id,
                        kind=lineup_kind,
                        formation=row.get("formation"),
                        is_starter=row.get("is_starter", True),
                        player_name=str(pname).strip(),
                        player_position=row.get("player_position"),
                        shirt_number=row.get("shirt_number"),
                        source=self.source,
                        refreshed_at=datetime.utcnow(),
                    ))
                    written_this_match += 1

                if written_this_match > 0:
                    if lineup_kind == "confirmed":
                        result.updated += 1
                    else:
                        result.created += 1
                    _log(f"  ✓ match {match.id}: {lineup_kind} ({written_this_match} players)")
                else:
                    result.skipped += 1

        _log(f"sync_lineups: created={result.created} updated={result.updated} skipped={result.skipped}")
        return result

    # ------------------------------------------------------------------
    # Pitchers (Phase 5 — MLB starting pitchers)
    # ------------------------------------------------------------------

    def sync_pitchers(
        self,
        competition_code: str,
        season: str,
        limit: int = 30,
        on_log=None,
        only_match_id: int | None = None,
    ) -> SyncResult:
        """
        Pull probable starting pitchers for upcoming MLB games.

        Iterates SCHEDULED games for (competition, season), in chronological
        order, and asks the adapter for probable pitchers.

        DATE HANDLING — everything here runs on MLB's BUSINESS DATE, not UTC.
        MLB's schedule API interprets dates as local game dates, and a West
        Coast night game (e.g. 02:38 UTC) belongs to the PREVIOUS day's slate.
        Business date = UTC minus 8h: no MLB game starts between 00:00 and
        08:00 UTC, so the subtraction cleanly folds post-midnight-UTC starts
        back onto their real slate. Bucketing by raw UTC date used to query
        the API for the wrong day and only worked because merged batch results
        papered over it (log lines like "15/9 games" were the tell).

        confirmed vs projected is a SLATE distinction, not a countdown:
        a probable for a game on TODAY'S business date is "confirmed" (MLB
        day-of probables are effectively announcements), while future dates
        stay "projected". This replaces the old <=4h-to-first-pitch rule,
        which permanently branded West Coast games projected on any afternoon
        run and biased anything downstream that reads the label.

        Stores results as MatchParticipant rows with role="starting_pitcher",
        kind in {"projected", "confirmed"}. Idempotent on
        (match_id, team_id, role): re-running upgrades projected → confirmed
        as the slate day arrives.
        """
        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        if not hasattr(self.adapter, "get_probable_pitchers"):
            _log(f"Adapter {self.adapter.source_name} doesn't expose probable pitchers.")
            return SyncResult()

        result = SyncResult()
        from datetime import datetime, timedelta

        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                _log(f"Competition {competition_code} not in DB.")
                return result

            now = datetime.utcnow()
            horizon = now + timedelta(days=14)

            stmt = (
                select(Match)
                .where(
                    Match.competition_id == comp.id,
                    Match.season == season,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now,
                    Match.utc_date <= horizon,
                )
                .order_by(Match.utc_date.asc())
                .limit(limit)
            )
            matches = list(s.execute(stmt).scalars())
            if only_match_id is not None:
                matches = [m for m in matches if m.id == only_match_id]
                if not matches:
                    # Fallback: load even if outside the default horizon
                    matches = list(s.execute(
                        select(Match).where(
                            Match.id == only_match_id,
                            Match.status == MatchStatus.SCHEDULED,
                        )
                    ).scalars())
            _log(f"Found {len(matches)} upcoming games to check for pitchers.")

            # Group matches by MLB BUSINESS date (UTC - 8h), because that is
            # the calendar the schedule API speaks. One batch call per unique
            # date — far cheaper than per-match (~30 games on a day = 1 call
            # instead of 30).
            from collections import defaultdict

            def business_date(dt) -> str:
                return (dt - timedelta(hours=8)).strftime("%Y-%m-%d")

            matches_by_date: dict[str, list[Match]] = defaultdict(list)
            for m in matches:
                matches_by_date[business_date(m.utc_date)].append(m)

            # For each date, fetch probables once. Index by source_id for lookup.
            probables_by_source_id: dict[str, dict[str, dict]] = {}
            use_batch = hasattr(self.adapter, "get_probable_pitchers_for_date")
            if use_batch:
                for date_iso, group in matches_by_date.items():
                    try:
                        batch = self.adapter.get_probable_pitchers_for_date(date_iso)
                    except Exception as e:
                        _log(f"  ✗ batch fetch {date_iso}: {e}")
                        continue
                    probables_by_source_id.update(batch)
                    _log(f"  ✓ {date_iso}: {len(batch)}/{len(group)} games "
                         f"with probable pitchers")

            for m in matches:
                ext = m.external_ids or {}
                source_id = ext.get(self.adapter.source_name)
                if not source_id:
                    _log(f"  · match {m.id} ({m.utc_date:%a %d %b}): no {self.adapter.source_name} source_id")
                    result.skipped += 1
                    continue

                # Try batch result first, fall back to per-game call
                probable = probables_by_source_id.get(str(source_id))
                if probable is None and not use_batch:
                    try:
                        probable = self.adapter.get_probable_pitchers(source_id)
                    except Exception as e:
                        _log(f"  ✗ match {m.id}: {e}")
                        result.skipped += 1
                        continue

                if not probable:
                    result.skipped += 1
                    continue

                # Slate day determines confirmed vs projected: a probable on
                # the game's own business date is day-of information —
                # "confirmed" — regardless of how many hours to first pitch.
                # (The old <=4h rule made afternoon runs permanently brand
                # West Coast games projected.)
                kind = ("confirmed"
                        if business_date(m.utc_date) <= business_date(now)
                        else "projected")

                wrote_this_match = 0
                for side, info in probable.items():
                    team_id = m.home_team_id if side == "home" else m.away_team_id
                    player_id = info.get("player_id") or ""
                    name = info.get("name") or "Unknown"
                    if not name or name == "Unknown":
                        continue

                    # Upsert on (match_id, team_id, role)
                    existing = s.execute(
                        select(MatchParticipant).where(
                            MatchParticipant.match_id == m.id,
                            MatchParticipant.team_id == team_id,
                            MatchParticipant.role == "starting_pitcher",
                        )
                    ).scalar_one_or_none()

                    if existing:
                        existing.player_name = name
                        existing.player_source_id = player_id
                        existing.kind = kind
                        existing.refreshed_at = now
                        result.updated += 1
                    else:
                        s.add(MatchParticipant(
                            match_id=m.id,
                            team_id=team_id,
                            role="starting_pitcher",
                            kind=kind,
                            player_source_id=player_id,
                            player_name=name,
                            source=self.adapter.source_name,
                            refreshed_at=now,
                        ))
                        result.created += 1
                    wrote_this_match += 1

                if wrote_this_match:
                    _log(f"  ✓ match {m.id} ({m.utc_date:%a %d %b}): {kind} ({wrote_this_match} pitchers)")
                else:
                    _log(f"  · match {m.id} ({m.utc_date:%a %d %b}): probables returned but all were Unknown/empty")
                    result.skipped += 1

        _log(f"sync_pitchers: created={result.created} updated={result.updated} skipped={result.skipped}")
        return result

    # ------------------------------------------------------------------
    # Players (Phase 6a — player power ratings foundation)
    # ------------------------------------------------------------------

    def sync_players(
        self,
        competition_code: str,
        season: str,
        on_log=None,
    ) -> SyncResult:
        """
        For every team in (competition, season), pull the full squad and
        season-to-date stats. Upserts on (player_source_id) for Player rows
        and (player, team, season) for PlayerSeasonStats.

        Cost: 1-2 API requests per team (pagination), so ~30-40 calls for
        a full PL squad refresh. Cheap.
        """
        from datetime import datetime as _dt
        from src.db.schema import (
            CompetitionTeam, Player, PlayerSeasonStats,
        )

        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        if not hasattr(self.adapter, "list_players"):
            _log(f"Adapter {self.source} doesn't expose list_players.")
            return SyncResult()

        result = SyncResult()
        with session_scope() as s:
            comp = self._get_competition(s, competition_code)
            if not comp:
                _log(f"Competition {competition_code} not in DB.")
                return result

            teams_q = (
                select(Team)
                .join(CompetitionTeam, CompetitionTeam.team_id == Team.id)
                .where(
                    CompetitionTeam.competition_id == comp.id,
                    CompetitionTeam.season == season,
                )
            )
            teams = list(s.execute(teams_q).scalars())
            _log(f"Will fetch players for {len(teams)} teams ({competition_code} {season}).")

            now = _dt.utcnow()
            for team in teams:
                team_source_id = (team.external_ids or {}).get(self.source)
                if not team_source_id:
                    _log(f"  ✗ {team.name}: no source_id, skipping")
                    result.skipped += 1
                    continue

                try:
                    players = self.adapter.list_players(team_source_id, season)
                except Exception as e:
                    _log(f"  ✗ {team.name}: {e}")
                    result.skipped += 1
                    continue

                written_this_team = 0
                for entry in players:
                    sid = entry.get("source_id")
                    name = entry.get("name")
                    if not sid or not name:
                        continue

                    # Find existing player by (sport, source_id)
                    existing_player = s.execute(
                        select(Player).where(
                            Player.sport == Sport.SOCCER,
                            Player.external_ids[self.source].as_string() == sid,
                        )
                    ).scalar_one_or_none()

                    # Fallback: SQLite JSON operator doesn't always behave —
                    # do a Python-side filter when above fails to find. Cheap
                    # for the volume we're at.
                    if existing_player is None:
                        candidates = s.execute(
                            select(Player).where(
                                Player.sport == Sport.SOCCER,
                                Player.name == name,
                            )
                        ).scalars()
                        for cand in candidates:
                            if (cand.external_ids or {}).get(self.source) == sid:
                                existing_player = cand
                                break

                    # Parse DOB
                    dob = None
                    dob_str = entry.get("date_of_birth")
                    if dob_str:
                        try:
                            dob = _dt.strptime(dob_str, "%Y-%m-%d")
                        except ValueError:
                            dob = None

                    if existing_player is None:
                        existing_player = Player(
                            sport=Sport.SOCCER,
                            name=name,
                            position=entry.get("position"),
                            date_of_birth=dob,
                            nationality=entry.get("nationality"),
                            team_id=team.id,
                            external_ids={self.source: sid},
                        )
                        s.add(existing_player)
                        s.flush()
                        result.created += 1
                    else:
                        existing_player.name = name
                        existing_player.position = entry.get("position") or existing_player.position
                        if dob and not existing_player.date_of_birth:
                            existing_player.date_of_birth = dob
                        existing_player.nationality = (
                            entry.get("nationality") or existing_player.nationality
                        )
                        # Track current team
                        existing_player.team_id = team.id
                        ext = dict(existing_player.external_ids or {})
                        ext[self.source] = sid
                        existing_player.external_ids = ext

                    # Upsert season stats
                    stats = entry.get("stats") or {}
                    pass_accuracy = entry.get("pass_accuracy")
                    existing_stats = s.execute(
                        select(PlayerSeasonStats).where(
                            PlayerSeasonStats.player_id == existing_player.id,
                            PlayerSeasonStats.team_id == team.id,
                            PlayerSeasonStats.season == season,
                        )
                    ).scalar_one_or_none()

                    if existing_stats:
                        # Replace counters with latest snapshot
                        for k, v in stats.items():
                            if hasattr(existing_stats, k):
                                setattr(existing_stats, k, v)
                        existing_stats.pass_accuracy = pass_accuracy
                        existing_stats.rating_avg = entry.get("rating_avg")
                        existing_stats.refreshed_at = now
                        # Recompute clean_sheets later if needed; API doesn't expose
                    else:
                        s.add(PlayerSeasonStats(
                            player_id=existing_player.id,
                            team_id=team.id,
                            season=season,
                            competition_code=None,
                            **{k: v for k, v in stats.items()
                               if k != "clean_sheets"},  # clean_sheets default 0/None already
                            pass_accuracy=pass_accuracy,
                            rating_avg=entry.get("rating_avg"),
                            source=self.source,
                            refreshed_at=now,
                        ))
                    written_this_team += 1

                if written_this_team:
                    _log(f"  ✓ {team.name}: {written_this_team} players")
                    result.updated += 1
                else:
                    result.skipped += 1

        _log(f"sync_players: created={result.created} updated={result.updated} skipped={result.skipped}")
        return result

    # ------------------------------------------------------------------
    # MLB odds (via API-Baseball — complement to MLB Stats API)
    # ------------------------------------------------------------------

    def sync_odds_mlb(
        self,
        season: int,
        days_ahead: int = 7,  # kept for signature compat; ignored
        on_log=None,
    ) -> SyncResult:
        """
        Pull MLB odds from API-Baseball and write them as Odds rows tagged
        source='api_baseball'.

        Uses the league/season-windowed /odds endpoint which returns all
        currently-available pre-match odds in one paginated walk. API-Baseball
        publishes odds 1-7 days before game time, so this naturally covers
        a week of upcoming fixtures.

        Doesn't touch matches/scores — those come from MLB Stats API. We
        only match odds to existing Match rows by (date, team names).

        API budget: typically 2-8 paginated requests total (not per-day).
        `days_ahead` is accepted but ignored, kept in the signature for
        backwards-compat with callers.

        Returns SyncResult with counts; logs unmatched events.
        """
        from datetime import datetime
        from src.adapters.api_baseball import APIBaseballClient, APIBaseballError
        from src.db.schema import Match, MatchStatus, Odds, Sport
        from src.ingestion.match_lookup import find_match

        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        client = APIBaseballClient.from_env()
        if client is None:
            _log("Skipping odds sync: no API_BASEBALL_KEY in env.")
            return SyncResult()

        result = SyncResult()
        unmatched_events: list[str] = []

        try:
            odds_rows = client.list_odds_window(season=season)
        except APIBaseballError as e:
            _log(f"✗ odds fetch: {e}")
            return SyncResult(skipped=1)

        if not odds_rows:
            _log(f"  · no odds returned for season {season} (window may be empty right now)")
            return result

        _log(f"Pulled {len(odds_rows)} odds rows, "
             f"{client.requests_remaining} requests remaining")

        with session_scope() as s:
            # Group by api_baseball_game_id so we delete-then-insert per game atomically
            by_game: dict[int, list] = {}
            for ow in odds_rows:
                by_game.setdefault(ow.api_baseball_game_id, []).append(ow)

            for game_id, rows in by_game.items():
                first = rows[0]
                match = find_match(
                    s, sport=Sport.MLB,
                    home_name=first.home_team,
                    away_name=first.away_team,
                    commence_time=first.commence_time,
                )
                if match is None:
                    unmatched_events.append(
                        f"{first.commence_time:%Y-%m-%d %H:%M} "
                        f"{first.home_team} vs {first.away_team}"
                    )
                    result.skipped += 1
                    continue

                # Wipe previous API-Baseball odds for this match,
                # leaving any other-source odds alone.
                s.query(Odds).filter(
                    Odds.match_id == match.id,
                    Odds.source == "api_baseball",
                ).delete()

                for ow in rows:
                    s.add(Odds(
                        match_id=match.id,
                        market=ow.market,
                        selection=ow.selection,
                        bookmaker=ow.bookmaker,
                        price_decimal=ow.price_decimal,
                        line=ow.line,
                        source="api_baseball",
                        captured_at=datetime.utcnow(),
                    ))
                    result.created += 1
                result.updated += 1

        _log(f"Matched {result.updated} games / "
             f"unmatched {len(unmatched_events)}")
        if unmatched_events:
            for ev in unmatched_events[:5]:
                _log(f"    - {ev}")
            if len(unmatched_events) > 5:
                _log(f"    ... and {len(unmatched_events) - 5} more")

        # M11a (2026-08-25): UTC-rollover fallback. The bulk /odds window
        # omits games whose provider-side date hasn't arrived (confirmed:
        # every book_odds=0 export row ever crossed UTC midnight; the bulk
        # request has no date param to widen). For upcoming matches that
        # still have zero api_baseball odds, resolve their provider game id
        # via the per-date games listing and request odds per game. If the
        # per-game endpoint also returns nothing, the provider simply has
        # not published yet — logged either way; tonight's console is the
        # experiment.
        from datetime import timedelta, timezone
        from src.ingestion.match_lookup import normalize_team_name

        with session_scope() as s:
            now = datetime.utcnow()
            missing = list(s.execute(
                select(Match).where(
                    Match.sport == Sport.MLB,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now,
                    Match.utc_date <= now + timedelta(hours=12),
                    ~Match.id.in_(
                        select(Odds.match_id).where(
                            Odds.source == "api_baseball")
                    ),
                )
            ).scalars())
            if missing:
                _log(f"  rollover fallback: {len(missing)} upcoming games "
                     f"with no odds — trying per-game requests…")
                dates = sorted({m.utc_date.strftime("%Y-%m-%d")
                                for m in missing})
                provider_games: list[dict] = []
                for d in dates:
                    try:
                        provider_games.extend(
                            client.list_games_on_date(season=season,
                                                      date_str=d))
                    except APIBaseballError as e:
                        _log(f"    ✗ games listing {d}: {e}")
                filled = 0
                claimed_gids: set[int] = set()
                for m in missing:
                    m_home = normalize_team_name(m.home_team.name)
                    m_away = normalize_team_name(m.away_team.name)
                    gid, gid_delta = None, None
                    for g in provider_games:
                        teams = g.get("teams") or {}
                        gh = normalize_team_name(
                            (teams.get("home") or {}).get("name") or "")
                        ga = normalize_team_name(
                            (teams.get("away") or {}).get("name") or "")
                        if gh != m_home or ga != m_away:
                            continue
                        # Patch (2026-08-25 evening): name-only matching let
                        # tomorrow's series game match tonight's provider id
                        # (game 179999 queried twice in the first live run).
                        # Require the provider's start time within 12h of
                        # our match so series neighbors can't cross-attach.
                        g_date = g.get("date")
                        # Doubleheader guard (2026-08-29): twin games sit
                        # ~6h apart, inside the 12h window — pick the
                        # NEAREST-time provider entry, and never let two of
                        # our matches claim the same provider id (first
                        # live doubleheader queried 180062 twice).
                        if g_date:
                            try:
                                g_dt = datetime.fromisoformat(
                                    g_date.replace("Z", "+00:00"))
                                if g_dt.tzinfo is not None:
                                    g_dt = g_dt.astimezone(
                                        timezone.utc).replace(tzinfo=None)
                                delta = abs((g_dt - m.utc_date).total_seconds())
                                if delta > 12 * 3600:
                                    continue
                            except ValueError:
                                continue
                        else:
                            delta = 0.0
                        if gid is None or delta < gid_delta:
                            gid, gid_delta = g.get("id"), delta
                    if gid in claimed_gids:
                        _log(f"    · provider id {gid} already claimed — "
                             f"skipping {m.away_team.name} @ "
                             f"{m.home_team.name} (doubleheader guard)")
                        continue
                    if gid is not None:
                        claimed_gids.add(gid)
                    if gid is None:
                        _log(f"    · no provider game id for "
                             f"{m.away_team.name} @ {m.home_team.name}")
                        continue
                    try:
                        rows = client.list_odds_for_game(season=season,
                                                         game_id=gid)
                    except APIBaseballError as e:
                        _log(f"    ✗ per-game odds {gid}: {e}")
                        continue
                    if not rows:
                        _log(f"    · provider has no odds yet for "
                             f"{m.away_team.name} @ {m.home_team.name} "
                             f"(game {gid})")
                        continue
                    s.query(Odds).filter(
                        Odds.match_id == m.id,
                        Odds.source == "api_baseball",
                    ).delete()
                    for ow in rows:
                        s.add(Odds(
                            match_id=m.id,
                            market=ow.market,
                            selection=ow.selection,
                            bookmaker=ow.bookmaker,
                            price_decimal=ow.price_decimal,
                            line=ow.line,
                            source="api_baseball",
                            captured_at=datetime.utcnow(),
                        ))
                        result.created += 1
                    filled += 1
                    result.updated += 1
                _log(f"  rollover fallback: filled {filled}/{len(missing)}")

        _log(f"sync_odds_mlb: created={result.created} "
             f"games={result.updated} skipped={result.skipped}")
        return result

    def sync_pitcher_stats(
        self,
        season: int,
        on_log=None,
    ) -> SyncResult:
        """
        Refresh season-to-date pitching stats for all probable starting
        pitchers currently in MatchParticipant for upcoming MLB games.

        Pull strategy: targets only pitchers we care about (those scheduled
        to start in upcoming games). Typically ~30 pitchers across today's
        slate, not all 450 active arms. Cheap and current.

        One API call per pitcher. Updates PitcherSeasonStats in-place.
        Returns SyncResult.
        """
        from datetime import datetime as _dt
        from src.db.schema import MatchParticipant, MatchStatus, PitcherSeasonStats

        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        if not hasattr(self.adapter, "get_pitcher_season_stats"):
            _log(f"Adapter {self.source} doesn't expose get_pitcher_season_stats.")
            return SyncResult()

        result = SyncResult()
        with session_scope() as s:
            # Find all unique pitcher source_ids in MatchParticipant for upcoming games
            now = _dt.utcnow()
            pitcher_rows = list(s.execute(
                select(MatchParticipant)
                .join(Match, Match.id == MatchParticipant.match_id)
                .where(
                    MatchParticipant.role == "starting_pitcher",
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now,
                )
            ).scalars())

            unique_pitchers: dict[str, MatchParticipant] = {}
            for mp in pitcher_rows:
                if mp.player_source_id and mp.player_source_id not in unique_pitchers:
                    unique_pitchers[mp.player_source_id] = mp

            _log(f"Pulling stats for {len(unique_pitchers)} unique starting pitchers.")

            for source_id, mp in unique_pitchers.items():
                try:
                    parsed = self.adapter.get_pitcher_season_stats(source_id, season)
                except Exception as e:
                    _log(f"  ✗ {mp.player_name}: {e}")
                    result.skipped += 1
                    continue
                if parsed is None:
                    _log(f"  · {mp.player_name}: no season data yet")
                    result.skipped += 1
                    continue

                # Match team_id if API gave us one
                team_id = mp.team_id
                if parsed.get("team_source_id"):
                    matched = s.execute(
                        select(Team).where(
                            Team.sport == Sport.MLB,
                            Team.external_ids[self.source].as_string() == parsed["team_source_id"],
                        )
                    ).scalar_one_or_none()
                    if matched:
                        team_id = matched.id

                existing = s.execute(
                    select(PitcherSeasonStats).where(
                        PitcherSeasonStats.player_source_id == source_id,
                        PitcherSeasonStats.season == str(season),
                    )
                ).scalar_one_or_none()

                fields = {
                    "player_source_id": source_id,
                    "player_name": parsed.get("player_name") or mp.player_name,
                    "team_id": team_id,
                    "season": str(season),
                    "games": parsed["games"],
                    "games_started": parsed["games_started"],
                    "innings_pitched": parsed["innings_pitched"],
                    "earned_runs": parsed["earned_runs"],
                    "runs_allowed": parsed["runs_allowed"],
                    "hits_allowed": parsed["hits_allowed"],
                    "walks": parsed["walks"],
                    "strikeouts": parsed["strikeouts"],
                    "home_runs_allowed": parsed["home_runs_allowed"],
                    "era": parsed["era"],
                    "whip": parsed["whip"],
                    "k_per_9": parsed["k_per_9"],
                    "bb_per_9": parsed["bb_per_9"],
                    "refreshed_at": _dt.utcnow(),
                }

                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    result.updated += 1
                else:
                    s.add(PitcherSeasonStats(**fields))
                    result.created += 1

        _log(f"sync_pitcher_stats: created={result.created} updated={result.updated} skipped={result.skipped}")
        return result

    # ------------------------------------------------------------------
    # MLB bullpen stats (Phase 12.2 — late-game pitching signal)
    # ------------------------------------------------------------------

    def sync_bullpen_stats(
        self,
        season: int,
        on_log=None,
        recent_window_days: int = 10,
        recent_min_ip: float = 10.0,
    ) -> SyncResult:
        """
        Refresh bullpen aggregate stats for all MLB teams.

        Pulls BOTH season-to-date and a recent rolling window (default last
        10 days) of relief pitching. The recent window captures a bullpen
        that's caving or locking in — the season aggregate is too slow to
        reflect a week-long collapse. Blended 70/30 at predict time.

        ~2 API calls per team (season + recent) = ~60 total. Free.
        Worth running DAILY now that there's a recent component — the
        recent window moves every day even though the season number is
        stable.

        Args:
          recent_window_days: rolling window length in days (default 10)
          recent_min_ip: skip recent weighting below this many IP (default 10)

        Returns SyncResult.
        """
        from datetime import datetime as _dt, timedelta as _td
        from src.db.schema import BullpenSeasonStats

        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        if not hasattr(self.adapter, "get_team_bullpen_stats"):
            _log(f"Adapter {self.source} doesn't expose get_team_bullpen_stats.")
            return SyncResult()

        has_recent = hasattr(self.adapter, "get_team_bullpen_recent")
        # Recent window bounds
        today = _dt.utcnow().date()
        start_date = (today - _td(days=recent_window_days)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        result = SyncResult()
        recent_count = 0
        with session_scope() as s:
            mlb_teams = list(s.execute(
                select(Team).where(Team.sport == Sport.MLB)
            ).scalars())

            _log(f"Pulling bullpen stats for {len(mlb_teams)} MLB teams "
                 f"(season + last {recent_window_days}d).")

            for team in mlb_teams:
                ext = team.external_ids or {}
                source_id = ext.get(self.source)
                if not source_id:
                    _log(f"  · {team.name}: no {self.source} source_id")
                    result.skipped += 1
                    continue

                try:
                    parsed = self.adapter.get_team_bullpen_stats(source_id, season)
                except Exception as e:
                    _log(f"  ✗ {team.name}: {e}")
                    result.skipped += 1
                    continue
                if parsed is None:
                    _log(f"  · {team.name}: no bullpen data yet")
                    result.skipped += 1
                    continue

                # Recent window (best-effort — failure here doesn't fail the row)
                recent_era = None
                recent_ip = None
                if has_recent:
                    try:
                        rec = self.adapter.get_team_bullpen_recent(
                            source_id, season, start_date, end_date,
                        )
                    except Exception as e:
                        rec = None
                        log.debug("recent bullpen fetch failed for %s: %s", team.name, e)
                    if rec and rec.get("innings_pitched", 0) >= recent_min_ip:
                        recent_era = rec.get("era")
                        recent_ip = rec.get("innings_pitched")
                        if recent_era is not None:
                            recent_count += 1
                            # Flag notable divergence in the log
                            season_era = parsed.get("era")
                            if season_era and abs(recent_era - season_era) >= 1.0:
                                direction = "caving" if recent_era > season_era else "locked in"
                                _log(f"  ⚠ {team.name} bullpen {direction}: "
                                     f"recent {recent_era:.2f} vs season {season_era:.2f}")

                existing = s.execute(
                    select(BullpenSeasonStats).where(
                        BullpenSeasonStats.team_id == team.id,
                        BullpenSeasonStats.season == str(season),
                    )
                ).scalar_one_or_none()

                fields = {
                    "team_id": team.id,
                    "season": str(season),
                    "games": parsed["games"],
                    "innings_pitched": parsed["innings_pitched"],
                    "earned_runs": parsed["earned_runs"],
                    "runs_allowed": parsed["runs_allowed"],
                    "hits_allowed": parsed["hits_allowed"],
                    "walks": parsed["walks"],
                    "strikeouts": parsed["strikeouts"],
                    "home_runs_allowed": parsed["home_runs_allowed"],
                    "saves": parsed["saves"],
                    "blown_saves": parsed["blown_saves"],
                    "era": parsed["era"],
                    "whip": parsed["whip"],
                    "k_per_9": parsed["k_per_9"],
                    "bb_per_9": parsed["bb_per_9"],
                    "recent_era": recent_era,
                    "recent_innings_pitched": recent_ip,
                    "recent_window_days": recent_window_days if recent_era is not None else None,
                    "recent_refreshed_at": _dt.utcnow() if recent_era is not None else None,
                    "refreshed_at": _dt.utcnow(),
                }

                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    result.updated += 1
                else:
                    s.add(BullpenSeasonStats(**fields))
                    result.created += 1

        _log(f"sync_bullpen_stats: created={result.created} updated={result.updated} "
             f"skipped={result.skipped} (recent form: {recent_count} teams)")
        return result

    # ------------------------------------------------------------------
    # MLB injuries (via API-Baseball — fills the MLB Stats API gap)
    # ------------------------------------------------------------------

    def sync_injuries_mlb(
        self,
        season: int,
        on_log=None,
    ) -> SyncResult:
        """
        MLB injuries are NOT supported by API-Baseball.

        API-Baseball (api-sports.io) doesn't expose an /injuries endpoint
        for their baseball product, only for football/NFL/etc. We verified
        this against their endpoint catalogue. Calls return:
            {"endpoint": "This endpoint do not exist."}

        Rather than silently fail with a misleading per-team loop, we log
        an honest "not supported" message and return an empty SyncResult.

        If/when API-Baseball adds the endpoint, we restore the per-team
        fetch logic that was here previously (see git history).

        Alternative sources we could wire later if desired:
          - MLB Stats API roster moves with `statusCode=IL10/IL15/IL60`
            (would mean parsing roster transactions, not a direct endpoint)
          - Scraping MLB.com injury report
          - Paid feed like SportsDataIO
        """
        def _log(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        _log("MLB injuries: API-Baseball doesn't expose an /injuries endpoint.")
        _log("  No alternative source wired yet. Skipping.")
        return SyncResult()


def sync_odds_nfl(progress=None) -> dict:
    """
    NFL book-odds capture (2026-09-09, closing the Week-1 tracking gap).
    Loops upcoming NFL games (next 8 days) and pulls per-game odds via the
    adapter — the provider's NFL odds endpoint is per-game, so this is the
    designed shape, not a fallback. Wipe-and-replace per match, same as
    every other odds path. ~16 requests per weekly slate.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from src.adapters.api_american_football import APIAmericanFootballAdapter
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds, Sport

    def report(msg):
        if progress:
            progress(msg)

    ad = APIAmericanFootballAdapter()
    created = games = 0
    with session_scope() as s:
        now = datetime.utcnow()
        upcoming = list(s.execute(select(Match).where(
            Match.sport == Sport.NFL,
            Match.status == MatchStatus.SCHEDULED,
            Match.utc_date >= now,
            Match.utc_date <= now + timedelta(days=8),
        ).order_by(Match.utc_date)).scalars())
        report(f"  NFL odds: {len(upcoming)} upcoming games in window")
        for m in upcoming:
            gid = (m.external_ids or {}).get("api_american_football")
            if not gid:
                report(f"    · no provider id for {m.away_team.name} @ {m.home_team.name}")
                continue
            try:
                rows = ad.list_odds(gid)
            except Exception as e:  # provider hiccup: skip, don't wipe
                report(f"    ✗ odds fetch {gid}: {e}")
                continue
            if not rows:
                report(f"    · no odds yet for {m.away_team.name} @ {m.home_team.name}")
                continue
            s.query(Odds).filter(Odds.match_id == m.id,
                                 Odds.source == ad.source_name).delete()
            for ow in rows:
                s.add(Odds(match_id=m.id, market=ow.market,
                           selection=ow.selection, bookmaker=ow.bookmaker,
                           price_decimal=ow.price_decimal, line=ow.line,
                           source=ad.source_name,
                           captured_at=datetime.utcnow()))
                created += 1
            games += 1
    return {"created": created, "games": games}
