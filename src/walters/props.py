"""
Player prop projection & grading (Phase 13).

Informational only, same layer-separation rule as the rest of this system:
this projects a stat and compares it to a line someone else (PrizePicks or
any pick'em board) is offering. It never talks to PrizePicks, places a pick,
or moves money — the user types in what the board shows, this says what the
model thinks.

Method (deliberately simple — "honest gaps" over a fake-sophisticated model):
a recency-weighted rolling average of the player's own PlayerGameLog rows for
that stat_type, with a sample-size gate. No opponent adjustment yet — we
don't have enough per-team stat-allowed history to do that honestly, so it's
left out rather than faked. That's the natural next upgrade once
PlayerGameLog has a few weeks of data across a competition.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.schema import Match, MatchStatus, Player, PlayerGameLog, PropPick, Sport
from src.ingestion.team_aliases import norm_tokens

# Below this many recent games, we refuse to give a real verdict — a
# rolling average of 1-2 games is noise, not a projection.
MIN_SAMPLE_SIZE = 3
# Minimum |edge| to call a side rather than "pass" (line is close to fair).
EDGE_THRESHOLD_PCT = 8.0
DEFAULT_WINDOW = 10


@dataclass
class Projection:
    stat_type: str
    mean: float | None
    sample_size: int
    std_dev: float | None
    recent_values: list[float] = field(default_factory=list)
    method: str = f"rolling_avg_l{DEFAULT_WINDOW}"


def resolve_player(
    session: Session, sport: Sport, name_query: str, team_id: int | None = None,
) -> Player | None:
    """
    Token-overlap match against Player.name, scoped to `sport` (and `team_id`
    if given). REFUSES ambiguity: if two+ players tie for the best score,
    returns None rather than guessing — same discipline as the Kalshi/team
    matcher (a wrong player silently poisons the grade).
    """
    query_tokens = norm_tokens(name_query)
    if not query_tokens:
        return None

    stmt = select(Player).where(Player.sport == sport)
    if team_id is not None:
        stmt = stmt.where(Player.team_id == team_id)
    candidates = list(session.execute(stmt).scalars())

    scored: list[tuple[int, Player]] = []
    for p in candidates:
        score = len(query_tokens & norm_tokens(p.name))
        if score > 0:
            scored.append((score, p))
    if not scored:
        return None

    scored.sort(key=lambda t: t[0], reverse=True)
    best_score = scored[0][0]
    tied = [p for score, p in scored if score == best_score]
    if len(tied) != 1:
        return None
    return tied[0]


def project_player_stat(
    session: Session,
    player_id: int,
    stat_type: str,
    window: int = DEFAULT_WINDOW,
    before: datetime | None = None,
) -> Projection:
    """
    Rolling average of `stat_type` over the player's last `window`
    PlayerGameLog rows (most recent first). `before` lets callers project
    "as of" a past date for backtesting instead of always using today.
    """
    stmt = (
        select(PlayerGameLog)
        .where(PlayerGameLog.player_id == player_id)
        .order_by(PlayerGameLog.game_date.desc())
        .limit(window)
    )
    if before is not None:
        stmt = stmt.where(PlayerGameLog.game_date < before)
    rows = list(session.execute(stmt).scalars())

    values = [
        float(r.stats[stat_type])
        for r in rows
        if r.stats and stat_type in r.stats and r.stats[stat_type] is not None
    ]
    if not values:
        return Projection(stat_type=stat_type, mean=None, sample_size=0, std_dev=None)

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return Projection(
        stat_type=stat_type,
        mean=mean,
        sample_size=len(values),
        std_dev=variance ** 0.5,
        recent_values=values,
        method=f"rolling_avg_l{window}",
    )


def _verdict_and_confidence(
    projection: Projection, line: float,
) -> tuple[float | None, str | None, str | None, str | None]:
    """Returns (edge_pct, verdict, confidence, note)."""
    if projection.mean is None or projection.sample_size < MIN_SAMPLE_SIZE:
        return (
            None, "pass", "low",
            f"only {projection.sample_size} recent game(s) on file — "
            f"need {MIN_SAMPLE_SIZE}+ for a real read",
        )

    edge_pct = ((projection.mean - line) / line) * 100 if line else None

    # Volatile stats (std dev large relative to the mean) cap confidence —
    # a "high" rolling average with wide swings isn't a reliable prop lean.
    volatile = (
        projection.std_dev is not None
        and projection.mean > 0
        and (projection.std_dev / projection.mean) > 0.6
    )
    confidence = "high" if projection.sample_size >= 6 and not volatile else "medium"
    if projection.sample_size < 6:
        confidence = "medium"

    if edge_pct is None:
        return None, "pass", confidence, "line was 0 — can't compute an edge"
    if edge_pct >= EDGE_THRESHOLD_PCT:
        return edge_pct, "over", confidence, None
    if edge_pct <= -EDGE_THRESHOLD_PCT:
        return edge_pct, "under", confidence, None
    return edge_pct, "pass", confidence, "within threshold of the line — no real lean"


def grade_prop(
    session: Session,
    sport: Sport,
    player_name: str,
    stat_type: str,
    line: float,
    match_id: int | None = None,
    team_id: int | None = None,
    board_source: str = "prizepicks",
    window: int = DEFAULT_WINDOW,
) -> PropPick:
    """
    Resolve the player, project their stat_type, grade it against `line`,
    and persist the result as a PropPick row (so hit-rate can be tracked
    later the way match predictions are).
    """
    player = resolve_player(session, sport, player_name, team_id=team_id)
    pick = PropPick(
        sport=sport,
        player_id=player.id if player else None,
        player_name_raw=player_name,
        match_id=match_id,
        stat_type=stat_type,
        line=line,
        board_source=board_source,
    )

    if player is None:
        pick.verdict = "pass"
        pick.confidence = "low"
        pick.sample_size = 0
        pick.note = "player not found in DB — no game log to project from"
        session.add(pick)
        session.flush()
        return pick

    projection = project_player_stat(session, player.id, stat_type, window=window)
    edge_pct, verdict, confidence, note = _verdict_and_confidence(projection, line)

    pick.projected_mean = projection.mean
    pick.sample_size = projection.sample_size
    pick.method = projection.method
    pick.edge_pct = edge_pct
    pick.verdict = verdict
    pick.confidence = confidence
    pick.note = note

    session.add(pick)
    session.flush()
    return pick


# ---------------------------------------------------------------------------
# Board parsing — "paste today's PrizePicks board, grade every line"
# ---------------------------------------------------------------------------

# One line per pick: "Player Name, stat_type, line" (comma or tab separated).
# stat_type should already be in PlayerGameLog's stat vocabulary for that
# sport (e.g. "shots_on_target", "goals") — this does not guess translations
# from PrizePicks' own category labels.
_BOARD_LINE_RE = re.compile(r"^\s*([^,\t]+)[,\t]\s*([^,\t]+)[,\t]\s*([\d.]+)\s*$")


def parse_board_text(text: str) -> list[tuple[str, str, float]]:
    """Parses pasted board text into (player_name, stat_type, line) triples.
    Blank lines and lines that don't match the expected 3-field shape are
    skipped rather than raising — a partial board is still useful."""
    out: list[tuple[str, str, float]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        m = _BOARD_LINE_RE.match(raw_line)
        if not m:
            continue
        name, stat_type, line_str = m.groups()
        try:
            out.append((name.strip(), stat_type.strip(), float(line_str)))
        except ValueError:
            continue
    return out


def grade_board(
    session: Session,
    sport: Sport,
    board_text: str,
    board_source: str = "prizepicks",
    window: int = DEFAULT_WINDOW,
) -> list[PropPick]:
    """Grades every line in a pasted board. Skipped/unparsed lines are
    simply absent from the result — call parse_board_text separately if you
    need to report what didn't parse."""
    picks = []
    for name, stat_type, line in parse_board_text(board_text):
        picks.append(
            grade_prop(
                session, sport, name, stat_type, line,
                board_source=board_source, window=window,
            )
        )
    return picks


# ---------------------------------------------------------------------------
# Standalone projections — "just show me projected lines for upcoming games"
# ---------------------------------------------------------------------------


def project_upcoming(
    session: Session,
    sport: Sport,
    stat_type: str,
    days_ahead: int = 7,
    window: int = DEFAULT_WINDOW,
) -> list[dict]:
    """
    For every team with a scheduled match in the next `days_ahead` days,
    projects `stat_type` for each player who has recent game-log history on
    that team. No line to grade against — just the model's own number, for
    browsing rather than checking one board entry at a time.
    """
    now = datetime.utcnow()
    horizon = now + timedelta(days=days_ahead)
    matches = list(session.execute(
        select(Match)
        .where(
            Match.sport == sport,
            Match.status == MatchStatus.SCHEDULED,
            Match.utc_date >= now,
            Match.utc_date <= horizon,
        )
        .order_by(Match.utc_date)
    ).scalars())

    out: list[dict] = []
    seen: set[tuple[int, int]] = set()  # (player_id, match_id) pairs already projected
    for m in matches:
        for team_id, opponent_id, team_label in (
            (m.home_team_id, m.away_team_id, "home"),
            (m.away_team_id, m.home_team_id, "away"),
        ):
            if team_id is None:
                continue
            recent_player_ids = list(session.execute(
                select(PlayerGameLog.player_id)
                .where(PlayerGameLog.team_id == team_id)
                .order_by(PlayerGameLog.game_date.desc())
                .limit(50)
            ).scalars().unique())

            for player_id in recent_player_ids:
                key = (player_id, m.id)
                if key in seen:
                    continue
                seen.add(key)
                projection = project_player_stat(session, player_id, stat_type, window=window)
                if projection.mean is None or projection.sample_size < MIN_SAMPLE_SIZE:
                    continue
                player = session.get(Player, player_id)
                out.append({
                    "player_name": player.name if player else f"player {player_id}",
                    "player_id": player_id,
                    "match_id": m.id,
                    "match_label": f"{m.away_team.name if m.away_team else '?'} @ "
                                    f"{m.home_team.name if m.home_team else '?'}",
                    "utc_date": m.utc_date,
                    "team_side": team_label,
                    "stat_type": stat_type,
                    "projected_mean": round(projection.mean, 2),
                    "sample_size": projection.sample_size,
                })

    out.sort(key=lambda d: d["projected_mean"], reverse=True)
    return out
