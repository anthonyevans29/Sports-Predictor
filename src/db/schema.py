"""
SQLAlchemy schema for the sports predictor.

Design principles:
  1. Sport-aware. Every team/competition/match carries a `sport` enum so the
     same DB serves soccer, NFL, MLB, NHL.
  2. Source-agnostic. `external_ids` (JSON) maps source_name -> source_id, so
     the same logical entity can be cross-referenced from Football-Data.org,
     API-Football, FlashScore, etc.
  3. Flexible stats. `match_stats.extra_stats` is JSON — sport-specific metrics
     (xG, EPA, advanced hockey stats) live there without schema churn.
  4. Predictions are first-class. Every model run is logged so we can backtest
     and version models over time.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from src.timeutil import utc_now_naive


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Sport(str, enum.Enum):
    SOCCER = "soccer"
    NFL = "nfl"
    MLB = "mlb"
    NHL = "nhl"


class MatchStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    # ARCHITECT 2026-10-03 (dedupe-matches --orphans): a SCHEDULED row whose
    # provider id is retired (NOT FOUND), with no live twin and no provider
    # game for the pair: never deleted, never a fixture, never an odds target.
    STALE_ORPHAN = "stale_orphan"


class Result(str, enum.Enum):
    HOME = "H"
    DRAW = "D"
    AWAY = "A"


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


class Competition(Base):
    """A league or cup — e.g. Premier League, Champions League, NFL, etc."""

    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(Enum(Sport), index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)  # PL, CL, FAC, NFL
    name: Mapped[str] = mapped_column(String(128))
    area: Mapped[str] = mapped_column(String(64))  # England, Europe, USA
    type: Mapped[str] = mapped_column(String(32))  # LEAGUE, CUP, INTL
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    teams: Mapped[list["Team"]] = relationship(
        secondary="competition_teams", back_populates="competitions"
    )
    matches: Mapped[list["Match"]] = relationship(back_populates="competition")

    __table_args__ = (UniqueConstraint("sport", "code", name="uq_competition_sport_code"),)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(Enum(Sport), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    short_name: Mapped[str | None] = mapped_column(String(64))
    tla: Mapped[str | None] = mapped_column(String(8))  # Three-letter abbreviation, e.g. ARS
    area: Mapped[str | None] = mapped_column(String(64))
    founded: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String(128))
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    competitions: Mapped[list[Competition]] = relationship(
        secondary="competition_teams", back_populates="teams"
    )
    home_matches: Mapped[list["Match"]] = relationship(
        foreign_keys="Match.home_team_id", back_populates="home_team"
    )
    away_matches: Mapped[list["Match"]] = relationship(
        foreign_keys="Match.away_team_id", back_populates="away_team"
    )
    players: Mapped[list["Player"]] = relationship(back_populates="team")
    ratings: Mapped[list["TeamRating"]] = relationship(back_populates="team")


class CompetitionTeam(Base):
    """Association: which teams play in which competition in which season."""

    __tablename__ = "competition_teams"

    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    season: Mapped[str] = mapped_column(String(16), primary_key=True)  # "2024/25"


# ---------------------------------------------------------------------------
# Matches & stats
# ---------------------------------------------------------------------------


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(Enum(Sport), index=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str] = mapped_column(String(16), index=True)
    matchday: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str | None] = mapped_column(String(64))  # GROUP_STAGE, ROUND_OF_16, etc.

    utc_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), index=True)
    # The provider's own status code, verbatim (e.g. hockey FT / AOT / AP,
    # soccer FT / AET / PEN). `status` is our mapped vocabulary; this keeps
    # the distinction the mapping collapses (2026-09-26). NULL = not synced
    # since the column was added. Added by migrate_status_raw.py.
    status_raw: Mapped[str | None] = mapped_column(String(16))

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)

    # Scores — nullable until played
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    home_score_ht: Mapped[int | None] = mapped_column(Integer)
    away_score_ht: Mapped[int | None] = mapped_column(Integer)
    # Soccer: API-Football score.fulltime verbatim — the 90-minute score
    # (home/away_score are `goals`, which INCLUDE extra time). NULL = not
    # synced since the column was added, or not a soccer row. The ET flag
    # is status_raw in (AET, PEN). Added by migrate_score_90.py (2026-09-26).
    home_score_90: Mapped[int | None] = mapped_column(Integer)
    away_score_90: Mapped[int | None] = mapped_column(Integer)
    full_time_result: Mapped[Result | None] = mapped_column(Enum(Result))

    venue: Mapped[str | None] = mapped_column(String(128))
    referee: Mapped[str | None] = mapped_column(String(128))
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    competition: Mapped[Competition] = relationship(back_populates="matches")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id], back_populates="home_matches")
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id], back_populates="away_matches")
    stats: Mapped[list["MatchStats"]] = relationship(back_populates="match")
    odds: Mapped[list["Odds"]] = relationship(back_populates="match")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")

    __table_args__ = (
        Index("ix_match_date_status", "utc_date", "status"),
        Index("ix_match_competition_season", "competition_id", "season"),
    )


class MatchStats(Base):
    """Per-team stats for a match. extra_stats holds sport-specific metrics."""

    __tablename__ = "match_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)

    # Common (mostly soccer-shaped — leave null for other sports)
    shots: Mapped[int | None] = mapped_column(Integer)
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    possession_pct: Mapped[float | None] = mapped_column(Float)
    corners: Mapped[int | None] = mapped_column(Integer)
    fouls: Mapped[int | None] = mapped_column(Integer)
    yellow_cards: Mapped[int | None] = mapped_column(Integer)
    red_cards: Mapped[int | None] = mapped_column(Integer)
    xg: Mapped[float | None] = mapped_column(Float)

    # Flex: { "epa": 0.12, "save_pct": 0.93, ... }
    extra_stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    match: Mapped[Match] = relationship(back_populates="stats")

    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_match_team_stats"),)


# ---------------------------------------------------------------------------
# Players & lineups (lightweight; expand later)
# ---------------------------------------------------------------------------


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(Enum(Sport), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    position: Mapped[str | None] = mapped_column(String(64))
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime)
    nationality: Mapped[str | None] = mapped_column(String(64))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    team: Mapped[Team | None] = relationship(back_populates="players")


# ---------------------------------------------------------------------------
# Odds & predictions
# ---------------------------------------------------------------------------


class Odds(Base):
    """A snapshot of bookmaker prices for a match."""

    __tablename__ = "odds"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(32))  # "1X2", "AH", "OU_2.5", "ML", "SPREAD", "TOTALS", "SPREADS"
    selection: Mapped[str] = mapped_column(String(32))  # "HOME", "DRAW", "AWAY", "OVER", etc.
    price_decimal: Mapped[float] = mapped_column(Float)
    # Phase 10: line value for totals (e.g. 8.5) and spreads (±1.5).
    # NULL for 1X2 / moneyline markets where line is implicit.
    line: Mapped[float | None] = mapped_column(Float)
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    is_closing: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    # Phase 10: which data source produced this row. Lets us coexist
    # multiple odds providers without overlap (e.g. soccer from API-Football,
    # MLB from API-Baseball) and replace odds per-source idempotently.
    source: Mapped[str | None] = mapped_column(String(32), index=True)

    match: Mapped[Match] = relationship(back_populates="odds")


class OddsSnapshot(Base):
    """
    A point-in-time snapshot of the DE-VIGGED CONSENSUS market for a match,
    captured several times a day (8/12/4/8) to measure intraday line movement
    and closing-line value. Unlike the Odds table (one row per bookmaker per
    market), this stores one row per selection per capture: the consensus
    implied probability across books, with the vig removed. Append-only — the
    day's captures accumulate as distinct rows keyed by captured_at.

    Deliberately MARKET-ONLY: we do not store the model's prediction here. The
    model's prob for a game is fixed at morning predict time, so storing it in
    every snapshot is redundant and would entangle the market record with the
    model. The model is joined in at analysis time (clv-report), keeping this a
    clean independent record of what the market did.
    """

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    market: Mapped[str] = mapped_column(String(32))      # "1X2", "TOTALS"
    selection: Mapped[str] = mapped_column(String(32))   # "HOME","AWAY","OVER","UNDER"
    # SEMANTICS (K0 receipt, 2026-09-27 — NOT renamed, to avoid churn): for
    # BOOK rows this is the de-vigged consensus prob. For source="kalshi"
    # rows it is NOT de-vigged: it is the yes bid/ask MIDPOINT when both are
    # quoted, else the single quoted side (a raw bid OR ask), else the last
    # price — one contract's raw price; the exports sum-normalize the sides.
    devig_prob: Mapped[float] = mapped_column(Float)
    line: Mapped[float | None] = mapped_column(Float)    # totals line; NULL for 1X2
    n_books: Mapped[int] = mapped_column(Integer, default=0)  # how many books in the consensus
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    source: Mapped[str | None] = mapped_column(String(32), index=True)
    # K-track (2026-09-27): the executable quotes behind a kalshi snapshot, in
    # dollars (0.00-1.00). NULL for book rows, for kalshi rows captured before
    # this column existed (no backfill is possible), or when a side wasn't
    # quoted. Added by migrate_kalshi_quotes.py.
    yes_bid: Mapped[float | None] = mapped_column(Float)
    yes_ask: Mapped[float | None] = mapped_column(Float)
    # ORDER LINE (ARCHITECT 2026-10-04): the Kalshi market ticker of this leg,
    # resolved by sync-kalshi-* (NULL for book rows and earlier captures). Added
    # by migrate_kalshi_ticker.py. DEFERRED and written / read only when the
    # column exists (src.db.database.has_kalshi_ticker), so a deploy that
    # precedes the migration keeps every odds_snapshots query working.
    market_ticker: Mapped[str | None] = mapped_column(String(64), deferred=True)

    match: Mapped[Match] = relationship()


class UmpireGame(Base):
    """
    TRACKING-ONLY, append-only: one row per finished game recording the plate
    umpire and the game's run/K/BB environment. We are BUILDING a dataset to
    later answer "does this umpire affect run scoring?" — we are NOT feeding it
    into predictions. Nothing reads this into the model; an umpire-report joins
    it at analysis time and always shows sample size (a plate ump works only
    ~25-30 games/season, so per-ump numbers are noise until n is large).

    Same discipline as OddsSnapshot: instrument first, conclude later. Store the
    raw outcome numbers; derive any tendency at read time so the rule can be
    tuned without re-capturing.
    """

    __tablename__ = "umpire_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), index=True)
    source_game_id: Mapped[str] = mapped_column(String(32), index=True)  # MLB gamePk
    game_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    plate_umpire: Mapped[str | None] = mapped_column(String(96), index=True)
    home_team: Mapped[str | None] = mapped_column(String(96))
    away_team: Mapped[str | None] = mapped_column(String(96))
    total_runs: Mapped[int | None] = mapped_column(Integer)
    total_line: Mapped[float | None] = mapped_column(Float)  # market O/U if known
    strikeouts: Mapped[int | None] = mapped_column(Integer)  # both teams
    walks: Mapped[int | None] = mapped_column(Integer)       # both teams
    home_runs: Mapped[int | None] = mapped_column(Integer)   # both teams
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match | None] = relationship()

    __table_args__ = (
        # one row per game; re-running the sync upserts rather than duplicates
        Index("ix_umpire_game_source", "source_game_id", unique=True),
    )


class GameWeather(Base):
    """
    TRACKING-ONLY, append-only: weather captured near first pitch for a game.
    Snapshots the conditions as they were forecast/observed at capture time so
    later analysis has a FROZEN record (don't reconstruct weather months later).
    Nothing feeds the model — weather is currently DISPLAY-ONLY in the app; this
    table is the instrument that will let us test whether it SHOULD be an input
    for totals. Indoor venues are recorded with roof_state so we can exclude or
    flag them rather than silently dropping.

    Same discipline as OddsSnapshot/UmpireGame: capture raw, conclude later.
    """

    __tablename__ = "game_weather"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), index=True)
    source_game_id: Mapped[str | None] = mapped_column(String(32), index=True)
    game_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    venue: Mapped[str | None] = mapped_column(String(96))
    roof_state: Mapped[str | None] = mapped_column(String(16))  # outdoor/indoor(roof)
    temperature_f: Mapped[float | None] = mapped_column(Float)
    wind_mph: Mapped[float | None] = mapped_column(Float)
    wind_dir_deg: Mapped[float | None] = mapped_column(Float)  # reserved; None for now
    precipitation_in: Mapped[float | None] = mapped_column(Float)
    condition: Mapped[str | None] = mapped_column(String(48))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match | None] = relationship()

    __table_args__ = (
        Index("ix_game_weather_match", "match_id", "captured_at"),
    )


class PitcherAppearance(Base):
    """
    TRACKING-ONLY, append-only: one row per pitcher per finished game, recording
    pitches thrown + outs + starter flag. This is the RAW from which bullpen
    AVAILABILITY and starter WORKLOAD are derived at read time (who pitched
    yesterday, who's on back-to-back, pitch counts last N days). We store raw
    appearances rather than a computed 'available/unavailable' flag so the
    availability rule can be tuned later without re-capturing.

    Nothing feeds the model. Same discipline as OddsSnapshot/UmpireGame/
    GameWeather. Serves the 'depleted-bullpen favorites are overrated'
    hypothesis — going forward via this tracker, and retroactively via a
    diagnostic over these same rows once backfilled.
    """

    __tablename__ = "pitcher_appearances"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), index=True)
    source_game_id: Mapped[str] = mapped_column(String(32), index=True)
    game_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    team_source_id: Mapped[str | None] = mapped_column(String(32), index=True)
    pitcher_id: Mapped[str | None] = mapped_column(String(32), index=True)
    pitcher_name: Mapped[str | None] = mapped_column(String(96))
    pitches: Mapped[int | None] = mapped_column(Integer)
    outs: Mapped[int | None] = mapped_column(Integer)
    is_starter: Mapped[bool] = mapped_column(default=False)
    # effectiveness (per-appearance) — bullpen PERFORMANCE, distinct from usage.
    # nullable: older rows predate this capture and stay null.
    earned_runs: Mapped[int | None] = mapped_column(Integer)
    hits_allowed: Mapped[int | None] = mapped_column(Integer)
    walks_allowed: Mapped[int | None] = mapped_column(Integer)
    strikeouts: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match | None] = relationship()

    __table_args__ = (
        # one row per pitcher per game
        Index("ix_appearance_game_pitcher", "source_game_id", "pitcher_id", unique=True),
    )


class NHLGoalieAppearance(Base):
    """
    NHL-GOALIE lane (architect 2026-09-30): one row per goalie per NHL game,
    from the NHL's own API (api-web.nhle.com gamecenter boxscore). The H2
    reopening source: api-sports' hockey product has no goalie data.

    Append-and-refresh, never deleted. `match_id` links to OUR NHL match when
    the game maps uniquely (date ± 12h + both team names); games outside our
    DB (e.g. 2023-24 warm-up history) keep match_id NULL and still feed a
    goalie's as-of history. `is_starter` is the API's own starter flag —
    NULL when the flag was not found (never inferred). Stats stay NULL when
    not found (law 4). Nothing here is a model feature until a candidate
    passes the frozen NHL gate.
    """

    __tablename__ = "nhl_goalie_appearances"

    id: Mapped[int] = mapped_column(primary_key=True)
    nhl_game_id: Mapped[int] = mapped_column(Integer, index=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), index=True)
    game_start: Mapped[datetime] = mapped_column(DateTime, index=True)   # UTC, naive
    game_type: Mapped[int | None] = mapped_column(Integer)               # the API's gameType (2 regular, 3 playoffs)
    side: Mapped[str] = mapped_column(String(4))                         # "home" / "away"
    team_abbrev: Mapped[str | None] = mapped_column(String(8))
    goalie_id: Mapped[int] = mapped_column(Integer, index=True)          # the NHL playerId
    goalie_name: Mapped[str | None] = mapped_column(String(96))
    is_starter: Mapped[bool | None] = mapped_column(Boolean)
    shots_against: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    goals_against: Mapped[int | None] = mapped_column(Integer)
    toi_seconds: Mapped[int | None] = mapped_column(Integer)
    decision: Mapped[str | None] = mapped_column(String(4))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match | None] = relationship()

    __table_args__ = (
        Index("ix_nhl_goalie_game_goalie", "nhl_game_id", "goalie_id", unique=True),
    )


class NHLShotEvent(Base):
    """
    NHL-xG lane (1) INGEST, architect 2026-09-30: one row per shot-type
    event (shot on goal / missed / blocked / goal — any play whose event type
    names a shot or goal) from the NHL's own play-by-play
    (api-web.nhle.com /v1/gamecenter/<id>/play-by-play), 2023-24 onward.

    Keyed to OUR matches through the goalie-sync mapping: `match_id` is the
    nhl_goalie_appearances link for the same nhl_game_id when one exists,
    else the same refusal-on-ambiguity matcher; NULL when neither maps.
    Raw values only — no derived distance/angle/situation class here (those
    belong to the frozen v6 declaration). Every field the API did not carry
    stays NULL (law 4): shot type is OPTIONAL by ruling (absent on blocked
    shots by nature). `side` is the SHOOTER's side from the game's roster;
    `owner_side` is the play's owner team, kept separately because the two
    need not agree (e.g. on blocked shots) — never reconciled by guessing.
    Nothing here is a model feature until a candidate passes the frozen gate.
    """

    __tablename__ = "nhl_shot_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    nhl_game_id: Mapped[int] = mapped_column(Integer, index=True)
    event_id: Mapped[int] = mapped_column(Integer)                        # the API's per-game event id
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), index=True)
    game_start: Mapped[datetime] = mapped_column(DateTime, index=True)   # UTC, naive
    game_type: Mapped[int | None] = mapped_column(Integer)
    period: Mapped[int | None] = mapped_column(Integer)
    period_type: Mapped[str | None] = mapped_column(String(8))           # REG / OT / SO as the API says
    time_in_period_s: Mapped[int | None] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))                  # e.g. shot-on-goal / missed-shot / goal
    shot_type: Mapped[str | None] = mapped_column(String(24))            # OPTIONAL (ruling)
    side: Mapped[str | None] = mapped_column(String(4))                  # shooter's side, from the roster
    owner_side: Mapped[str | None] = mapped_column(String(4))            # the play's owner team side
    team_abbrev: Mapped[str | None] = mapped_column(String(8))           # of `side`
    shooter_id: Mapped[int | None] = mapped_column(Integer, index=True)
    goalie_id: Mapped[int | None] = mapped_column(Integer)               # goalie in net (NULL = empty net or absent)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    zone_code: Mapped[str | None] = mapped_column(String(4))
    home_defending_side: Mapped[str | None] = mapped_column(String(8))
    situation_code: Mapped[str | None] = mapped_column(String(8))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match | None] = relationship()

    __table_args__ = (
        Index("ix_nhl_shot_game_event", "nhl_game_id", "event_id", unique=True),
    )


class MatchNeutralDerived(Base):
    """
    National-team lane (#220, ARCHITECT 2026-10-02): "Neutral derivation RULED
    YES: ... derive neutral = venue city != home team's ground city, store as
    `neutral_derived` with the rule stated — never as a provider fact."

    One row per match the intl ingest stored. `neutral_derived` is OUR
    inference under `rule` (the full rule text, verbatim, so a row explains
    itself); NULL when either city is missing (law 4: unknown stays unknown).
    The two inputs are kept as served, so a re-derivation needs no new calls.
    Nothing here is a provider field.
    """

    __tablename__ = "match_neutral_derived"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    neutral_derived: Mapped[bool | None] = mapped_column(Boolean)
    rule: Mapped[str] = mapped_column(String(512))
    venue_city: Mapped[str | None] = mapped_column(String(128))         # fixture.venue.city, as served
    home_ground_city: Mapped[str | None] = mapped_column(String(128))   # /teams venue.city, same comp-season
    source: Mapped[str] = mapped_column(String(32), default="api_football")
    derived_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match] = relationship()


class IntlMatchVenue(Base):
    """
    intl-neutral-v3 (ARCHITECT 2026-10-02; intl-elo-v2 (b)): "neutral rule v3
    (venue country != home team's country) replaces v2 — route B, 218 calls,
    run on the laptop as an ingest step before v2's run; derived, labelled."

    One row per stored national-team match: the fixture's venue id as served
    (from the saved /fixtures response), the venue's COUNTRY as served by
    /venues?country=<home country> (route B), and the home team's /teams
    country (teams.area). `neutral_v3` is OUR derivation under `rule`
    (stated in full), NULL when either country is unknown. Never a provider
    fact.
    """

    __tablename__ = "intl_match_venue"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    venue_id: Mapped[int | None] = mapped_column(Integer, index=True)
    venue_country: Mapped[str | None] = mapped_column(String(64))       # /venues country, as served
    home_country: Mapped[str | None] = mapped_column(String(64))        # /teams team.country (teams.area)
    neutral_v3: Mapped[bool | None] = mapped_column(Boolean)
    rule: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(32), default="api_football")
    derived_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    match: Mapped[Match] = relationship()


class TeamRating(Base):
    """Time-series of team ratings (Elo, xG attack/defense, etc.)"""

    __tablename__ = "team_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id"))
    rating_type: Mapped[str] = mapped_column(String(32))  # "elo", "xg_attack", "xg_defense"
    value: Mapped[float] = mapped_column(Float)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    model_version: Mapped[str | None] = mapped_column(String(32))

    team: Mapped[Team] = relationship(back_populates="ratings")

    __table_args__ = (Index("ix_rating_team_type_date", "team_id", "rating_type", "as_of_date"),)


class Prediction(Base):
    """A single model's prediction for a match."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    # 1X2 probabilities (soccer) / win probabilities (other sports)
    home_win_prob: Mapped[float] = mapped_column(Float)
    draw_prob: Mapped[float | None] = mapped_column(Float)
    away_win_prob: Mapped[float] = mapped_column(Float)

    # Expected scoreline (soccer/baseball/hockey)
    expected_home_score: Mapped[float | None] = mapped_column(Float)
    expected_away_score: Mapped[float | None] = mapped_column(Float)

    # Spread/handicap (NFL/NBA-style)
    predicted_spread: Mapped[float | None] = mapped_column(Float)
    predicted_total: Mapped[float | None] = mapped_column(Float)

    # Over/under (totals) probabilities — set when the Poisson model produces them.
    # We store a single canonical line (e.g. 2.5) per prediction; multi-line totals
    # are computed on the fly from expected goals when needed.
    over_under_line: Mapped[float | None] = mapped_column(Float)
    over_prob: Mapped[float | None] = mapped_column(Float)
    under_prob: Mapped[float | None] = mapped_column(Float)

    # Phase 7 — cup knockout "to advance" probabilities (post-ET-pens).
    # Only populated for cup matches in knockout rounds. For 90-minute draws,
    # we redistribute the draw probability mass into ET/pens (roughly 50/50,
    # with a slight home edge in penalty shootouts).
    to_advance_home_prob: Mapped[float | None] = mapped_column(Float)
    to_advance_away_prob: Mapped[float | None] = mapped_column(Float)

    # Walters-style value detection: edge vs best market price
    best_value_market: Mapped[str | None] = mapped_column(String(32))
    best_value_selection: Mapped[str | None] = mapped_column(String(32))
    best_value_edge_pct: Mapped[float | None] = mapped_column(Float)
    recommended_unit_size: Mapped[float | None] = mapped_column(Float)  # Fractional Kelly output

    # Free-form: feature values, factor breakdown
    factor_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    match: Mapped[Match] = relationship(back_populates="predictions")
    outcome: Mapped["PredictionOutcome | None"] = relationship(
        back_populates="prediction", uselist=False
    )

    __table_args__ = (
        Index("ix_prediction_match_version", "match_id", "model_version"),
    )


# ---------------------------------------------------------------------------
# Model versioning & evaluation (Phase 2)
# ---------------------------------------------------------------------------


class ModelVersion(Base):
    """
    A versioned snapshot of a trained model.

    Every time we train (fresh or incremental), we create one of these. The
    `parameters` JSON holds whatever the model needs to reproduce its state
    — Elo K-factor, home advantage, factor weights, etc.

    `status` tracks the lifecycle:
      - "candidate" — just trained, not yet validated
      - "production" — currently serving live predictions
      - "shelved" — used to be live, kept for reproducibility
      - "rejected" — trained but never promoted (lost the holdout test)
      - "held" — PASSED the gate under improve's hold_on_pass (H0-5): not
        promoted; only `ratify-candidate` moves it to production

    Only ONE row per (sport, model_family) should have status="production"
    at any time. Enforcing that as a constraint is overkill; the promotion
    logic in walters/training.py handles it.
    """

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(Enum(Sport), index=True)
    model_family: Mapped[str] = mapped_column(String(64), index=True)  # "soccer_elo_poisson"
    version: Mapped[str] = mapped_column(String(64), index=True)  # "v1.0.0", "v1.0.1", etc.
    parent_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)

    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(String(1024))

    # Training metrics (computed at train time)
    train_size: Mapped[int | None] = mapped_column(Integer)
    train_log_loss: Mapped[float | None] = mapped_column(Float)
    train_brier: Mapped[float | None] = mapped_column(Float)

    # Holdout metrics (computed when comparing candidates to production)
    holdout_size: Mapped[int | None] = mapped_column(Integer)
    holdout_log_loss: Mapped[float | None] = mapped_column(Float)
    holdout_brier: Mapped[float | None] = mapped_column(Float)
    holdout_top_pick_acc: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("sport", "model_family", "version", name="uq_model_family_version"),
    )


class PredictionOutcome(Base):
    """
    Per-prediction scoring once the match has finished.

    Built by walters/evaluation.py. One row per Prediction. Stores both
    quantitative scores (log loss, Brier, RPS) and a qualitative auto-generated
    post-mortem so users can scan a "what went wrong" feed.
    """

    __tablename__ = "prediction_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictions.id"), unique=True, index=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    # Actuals
    actual_result: Mapped[Result | None] = mapped_column(Enum(Result))
    actual_home_score: Mapped[int | None] = mapped_column(Integer)
    actual_away_score: Mapped[int | None] = mapped_column(Integer)

    # 1X2 scoring
    log_loss: Mapped[float | None] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)
    rps: Mapped[float | None] = mapped_column(Float)  # Ranked Probability Score
    top_pick_hit: Mapped[bool | None] = mapped_column(Boolean)

    # Totals scoring (if predicted)
    total_correct: Mapped[bool | None] = mapped_column(Boolean)  # over/under called right

    # Value realization (if a bet would have been placed)
    value_realized_pct: Mapped[float | None] = mapped_column(Float)

    # Phase 11: Closing-line value. The difference between our predicted
    # probability for our top pick and the bookmaker's de-vigged closing
    # implied probability for that same selection. Positive = we were on
    # the value side (market eventually agreed with us, at least partly).
    # Stored as a percentage-point delta (e.g. 0.05 = we had +5pp of value).
    # NULL when we have no closing odds for the match.
    clv: Mapped[float | None] = mapped_column(Float)
    closing_price: Mapped[float | None] = mapped_column(Float)
    closing_bookmaker: Mapped[str | None] = mapped_column(String(64))

    # Auto-generated post-mortem text. Templated, not LLM-generated.
    notes: Mapped[str | None] = mapped_column(String(1024))

    prediction: Mapped[Prediction] = relationship(back_populates="outcome")

    __table_args__ = (Index("ix_outcome_evaluated", "evaluated_at"),)


# ---------------------------------------------------------------------------
# Injuries (Phase 3)
# ---------------------------------------------------------------------------


class Injury(Base):
    """
    Current player availability issue.

    API-Football's /injuries endpoint returns these per team. We refresh by
    deleting all rows for a team and re-inserting — the upstream feed is the
    source of truth and we don't try to track injury history.

    Used by models/factors.injury_adjustment to estimate the xG impact of
    unavailable players.
    """

    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    player_name: Mapped[str] = mapped_column(String(128))
    player_position: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(128))  # "Knee Injury", "Suspended"
    type: Mapped[str | None] = mapped_column(String(32))  # "Missing Fixture", "Questionable"
    fixture_source_id: Mapped[str | None] = mapped_column(String(64))  # which fixture this applies to (if any)
    source: Mapped[str] = mapped_column(String(64), default="api_football")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)

    __table_args__ = (Index("ix_injury_team_refreshed", "team_id", "refreshed_at"),)


# ---------------------------------------------------------------------------
# Lineups (Phase 4)
# ---------------------------------------------------------------------------


class Lineup(Base):
    """
    Per-match team lineup. One row per starting/bench slot per team.

    `kind` distinguishes:
      - "projected" — heuristic guess (recent starting XI minus injuries)
      - "confirmed" — official lineup, available ~T-20min from kickoff

    When sync-lineups runs, all rows for a given (match, team) are deleted
    and rewritten. We don't track lineup history.
    """

    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="projected")  # projected | confirmed

    formation: Mapped[str | None] = mapped_column(String(16))  # "4-3-3", "3-5-2"
    is_starter: Mapped[bool] = mapped_column(Boolean, default=True)
    player_name: Mapped[str] = mapped_column(String(128))
    player_position: Mapped[str | None] = mapped_column(String(32))
    shirt_number: Mapped[int | None] = mapped_column(Integer)

    source: Mapped[str] = mapped_column(String(64), default="api_football")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)

    __table_args__ = (
        Index("ix_lineup_match_team_kind", "match_id", "team_id", "kind"),
    )


# ---------------------------------------------------------------------------
# Match participants — starter roles per sport (Phase 5)
# ---------------------------------------------------------------------------


class MatchParticipant(Base):
    """
    A player playing a specific role in a match.

    Sport-agnostic abstraction for "this player matters for this match":
      - baseball: role="starting_pitcher", "closer"
      - soccer:   role="goalkeeper" (when we care about specific keepers)
      - nfl:      role="starting_qb"

    `kind` mirrors Lineup: "projected" (probable, days before) vs "confirmed"
    (officially announced, hours before).

    For now MLB starting pitchers are the only use case. Schema is intentionally
    flexible so we don't migrate again when adding NFL QBs or NHL goalies.
    """

    __tablename__ = "match_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))  # "starting_pitcher", etc.
    kind: Mapped[str] = mapped_column(String(16), default="projected")
    player_source_id: Mapped[str | None] = mapped_column(String(64))
    player_name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(64), default="mlb_stats_api")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    __table_args__ = (
        Index("ix_participant_match_team_role", "match_id", "team_id", "role"),
    )


# ---------------------------------------------------------------------------
# Player season stats (Phase 6a — player power ratings)
# ---------------------------------------------------------------------------


class PlayerSeasonStats(Base):
    """
    One row per (player, team, season). Aggregate stats for that span.

    The "team" dimension matters because mid-season transfers create two rows
    for the same player in the same season — useful for rating decay logic
    (e.g. weighting current-team performance higher than prior-team).

    Stats are sport-agnostic in name but the *meaning* is sport-specific:
      - Soccer: minutes, goals, assists, shots, key_passes, tackles, etc.
      - Baseball: maybe later — for now the rating model is team-rate based.

    All counting stats are season-to-date snapshots. Rates (per-90, per-game)
    are computed on demand from these counters + minutes/appearances.
    """

    __tablename__ = "player_season_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(16), index=True)
    competition_code: Mapped[str | None] = mapped_column(String(32), index=True)

    # Time on pitch
    appearances: Mapped[int] = mapped_column(Integer, default=0)
    lineups: Mapped[int] = mapped_column(Integer, default=0)  # times in starting XI
    minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Attacking
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    shots: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)

    # Creation / playmaking
    key_passes: Mapped[int] = mapped_column(Integer, default=0)
    pass_accuracy: Mapped[float | None] = mapped_column(Float)  # 0..1
    dribble_success: Mapped[int] = mapped_column(Integer, default=0)

    # Defending
    tackles: Mapped[int] = mapped_column(Integer, default=0)
    interceptions: Mapped[int] = mapped_column(Integer, default=0)
    duels_won: Mapped[int] = mapped_column(Integer, default=0)
    fouls_committed: Mapped[int] = mapped_column(Integer, default=0)
    fouls_drawn: Mapped[int] = mapped_column(Integer, default=0)

    # Cards / discipline
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)

    # Goalkeeping (null for outfield)
    saves: Mapped[int | None] = mapped_column(Integer)
    goals_conceded: Mapped[int | None] = mapped_column(Integer)
    clean_sheets: Mapped[int | None] = mapped_column(Integer)

    # API-Football's own rating (helpful sanity check but not authoritative)
    rating_avg: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(64), default="api_football")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    player: Mapped[Player] = relationship()
    team: Mapped[Team] = relationship()

    __table_args__ = (
        Index("ix_pss_player_team_season", "player_id", "team_id", "season", unique=True),
        Index("ix_pss_team_season", "team_id", "season"),
    )


# ---------------------------------------------------------------------------
# MLB pitcher season stats (Phase 11 — pitcher-aware run predictions)
# ---------------------------------------------------------------------------


class PitcherSeasonStats(Base):
    """
    Season-to-date pitching aggregates for an MLB pitcher.

    Separate from PlayerSeasonStats because the stat shape doesn't overlap
    (ERA/WHIP/IP/K vs goals/assists/tackles). Keeps schema honest about
    what each table actually contains rather than forcing a one-table-fits-all.

    Sourced from MLB Stats API (the trusted source). Refreshed by
    `sync-pitcher-stats`. Used at predict time to compute a pitcher-aware
    run-allowed multiplier on the opponent's run profile.
    """

    __tablename__ = "pitcher_season_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    # MLB Stats API's `person.id` for the pitcher. Stored as string for
    # consistency with other source IDs. We don't FK to Player because
    # we don't necessarily have a Player row for every pitcher (we only
    # sync probable starters into MatchParticipant; deeper player table
    # is a soccer-only thing for now).
    player_source_id: Mapped[str] = mapped_column(String(64), index=True)
    player_name: Mapped[str] = mapped_column(String(128))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(16), index=True)

    # Core counters
    games: Mapped[int] = mapped_column(Integer, default=0)
    games_started: Mapped[int] = mapped_column(Integer, default=0)
    innings_pitched: Mapped[float] = mapped_column(Float, default=0.0)
    earned_runs: Mapped[int] = mapped_column(Integer, default=0)
    runs_allowed: Mapped[int] = mapped_column(Integer, default=0)
    hits_allowed: Mapped[int] = mapped_column(Integer, default=0)
    walks: Mapped[int] = mapped_column(Integer, default=0)
    strikeouts: Mapped[int] = mapped_column(Integer, default=0)
    home_runs_allowed: Mapped[int] = mapped_column(Integer, default=0)

    # Derived rates (also stored to avoid recomputation, but trust the
    # counters above as source of truth — these can drift if recomputed).
    era: Mapped[float | None] = mapped_column(Float)
    whip: Mapped[float | None] = mapped_column(Float)
    k_per_9: Mapped[float | None] = mapped_column(Float)
    bb_per_9: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(64), default="mlb_stats_api")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    team: Mapped[Team | None] = relationship()

    __table_args__ = (
        Index("ix_pss_pitcher_season", "player_source_id", "season", unique=True),
    )


# ---------------------------------------------------------------------------
# MLB bullpen aggregate stats (Phase 12.2 — late-game pitching signal)
# ---------------------------------------------------------------------------


class BullpenSeasonStats(Base):
    """
    Season-to-date aggregate bullpen pitching stats for one MLB team.

    The bullpen handles ~40% of innings in a typical modern MLB game. Our
    prior modeling used only the starter's ERA, implicitly treating the
    bullpen as league-average. This table backs the bullpen component of
    the effective team ERA used in predictions.

    One row per (team, season). Sourced from MLB Stats API's pitching
    splits endpoint with type=bullpen. Refreshed by `sync-bullpen-stats`.
    """

    __tablename__ = "bullpen_season_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(16), index=True)

    # Core aggregates
    games: Mapped[int] = mapped_column(Integer, default=0)
    innings_pitched: Mapped[float] = mapped_column(Float, default=0.0)
    earned_runs: Mapped[int] = mapped_column(Integer, default=0)
    runs_allowed: Mapped[int] = mapped_column(Integer, default=0)
    hits_allowed: Mapped[int] = mapped_column(Integer, default=0)
    walks: Mapped[int] = mapped_column(Integer, default=0)
    strikeouts: Mapped[int] = mapped_column(Integer, default=0)
    home_runs_allowed: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    blown_saves: Mapped[int] = mapped_column(Integer, default=0)

    # Derived rates
    era: Mapped[float | None] = mapped_column(Float)
    whip: Mapped[float | None] = mapped_column(Float)
    k_per_9: Mapped[float | None] = mapped_column(Float)
    bb_per_9: Mapped[float | None] = mapped_column(Float)

    # Phase 12.4: recent bullpen form (rolling window, e.g. last 10 days).
    # Captures a bullpen that's caving (or locking in) recently — the
    # season aggregate is too slow to reflect a week-long collapse. Blended
    # 70/30 with season ERA at predict time. None when the recent window
    # has too few innings to be meaningful.
    recent_era: Mapped[float | None] = mapped_column(Float)
    recent_innings_pitched: Mapped[float | None] = mapped_column(Float)
    recent_window_days: Mapped[int | None] = mapped_column(Integer)
    recent_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime)

    source: Mapped[str] = mapped_column(String(64), default="mlb_stats_api")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    team: Mapped[Team] = relationship()

    __table_args__ = (
        Index("ix_bss_team_season", "team_id", "season", unique=True),
    )
