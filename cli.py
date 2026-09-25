"""
Command-line interface for data operations.

Usage:
    python cli.py init-db
    python cli.py sync-competitions
    python cli.py sync-teams    --competition PL  --season 2024/25
    python cli.py sync-matches  --competition PL  --seasons 3
    python cli.py sync-stats    --competition PL  --season 2024/25 --limit 50
    python cli.py status

After data is loaded, run `python main.py` to open the web UI.
"""
from __future__ import annotations

import logging
from datetime import datetime

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from sqlalchemy import func, select

from config import settings
from src.adapters.registry import get_adapter
from src.db.database import drop_db, init_db, session_scope
from src.db.schema import Competition, Match, MatchStats, MatchStatus, Sport, Team
from src.ingestion.service import IngestionService

console = Console()


# Competitions that route to the baseball adapter. Everything else is soccer.
_BASEBALL_COMP_CODES = {"MLB", "MLB_SPRING"}


def _sport_for_competition(code: str) -> str:
    """Returns 'soccer', 'baseball', or 'nfl' based on the competition code."""
    if code.upper() in _BASEBALL_COMP_CODES:
        return "baseball"
    if code.upper() in ("NFL", "NCAA"):  # NFL 09-05; NCAA 09-25
        return "nfl"
    if code.upper() == "NHL":  # NHL phase 1, 2026-09-23
        return "nhl"
    return "soccer"


def _adapter_for_competition(code: str):
    """Pick the right adapter automatically based on the competition code."""
    return get_adapter(sport=_sport_for_competition(code))


def _setup_logging():
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


@click.group()
def cli():
    """Sports Predictor — data ingestion CLI."""
    _setup_logging()


@cli.command("init-db")
@click.option("--force", is_flag=True, help="Drop and recreate (DESTRUCTIVE).")
def init_db_cmd(force: bool):
    """Initialize the local database."""
    if force:
        click.confirm("This will DELETE all existing data. Continue?", abort=True)
        drop_db()
        console.print("[red]Dropped all tables.[/red]")
    init_db()
    console.print(f"[green]✓ Database initialized at {settings.database_url}[/green]")


@cli.command("sync-competitions")
@click.option("--sport", default="soccer", type=click.Choice([s.value for s in Sport]))
def sync_competitions_cmd(sport: str):
    """Pull the curated competition list."""
    service = IngestionService(get_adapter(sport=sport))
    result = service.sync_competitions(Sport(sport))
    console.print(f"[green]✓ Competitions: {result}[/green]")


@cli.command("sync-teams")
@click.option("--competition", "competition_code", required=True, help="Code, e.g. PL, FAC, CL, MLB")
@click.option("--season", default=None, help="e.g. 2024/25 (soccer), 2026 (MLB)")
def sync_teams_cmd(competition_code: str, season: str | None):
    """Pull all teams for a competition (in a given season)."""
    service = IngestionService(_adapter_for_competition(competition_code))
    result = service.sync_teams(competition_code, season)
    console.print(f"[green]✓ Teams ({competition_code}): {result}[/green]")


@cli.command("sync-matches")
@click.option("--competition", "competition_code", required=True, help="Code, e.g. PL, FAC, CL, MLB")
@click.option("--season", default=None, help="Single season, e.g. 2024/25 (soccer), 2026 (MLB)")
@click.option("--seasons", default=0, type=int, help="Backfill N most recent seasons.")
@click.option("--date-from", default=None, help="YYYY-MM-DD")
@click.option("--date-to", default=None, help="YYYY-MM-DD")
def sync_matches_cmd(
    competition_code: str,
    season: str | None,
    seasons: int,
    date_from: str | None,
    date_to: str | None,
):
    """Pull matches by season or date range."""
    service = IngestionService(_adapter_for_competition(competition_code))

    if seasons > 0:
        current_year = datetime.utcnow().year
        if datetime.utcnow().month < 7:
            current_year -= 1
        # Season-string format is sport-shaped (2026-09-05, NFL phase 1b):
        # soccer uses "2026/27"; MLB and NFL use single years. The EFL
        # aliasing quirk showed both formats can work for cups, but leagues
        # are strict — generate the right shape per sport.
        _single_year = _sport_for_competition(competition_code) in ("baseball", "nfl", "nhl")
        for offset in range(seasons):
            year = current_year - offset
            season_str = str(year) if _single_year else f"{year}/{str(year + 1)[-2:]}"
            console.print(f"[cyan]→ Syncing {competition_code} season {season_str}[/cyan]")
            result = service.sync_matches(competition_code, season=season_str)
            console.print(f"  {result}")
        return

    def _progress(msg):
        console.print(f"[dim]{msg}[/dim]")

    result = service.sync_matches(
        competition_code, season=season, date_from=date_from, date_to=date_to,
        progress=_progress,
    )
    console.print(f"[green]✓ Matches ({competition_code}): {result}[/green]")


@cli.command("sync-stats")
@click.option("--competition", "competition_code", required=True, help="Code, e.g. PL")
@click.option("--season", required=True, help="e.g. 2024/25")
@click.option(
    "--limit",
    default=50,
    show_default=True,
    type=int,
    help="Max matches to fetch stats for in this run. Each = 1 API request.",
)
@click.option("--only-missing/--all", default=True, help="Skip matches that already have stats.")
def sync_stats_cmd(competition_code: str, season: str, limit: int, only_missing: bool):
    """
    Pull per-match team statistics for FINISHED matches.

    One API request per match. Use --limit to control burn rate.
    """
    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            console.print(
                f"[red]Competition {competition_code} not in DB. "
                f"Run sync-competitions first.[/red]"
            )
            return

        match_q = select(Match).where(
            Match.competition_id == comp.id,
            Match.season == season,
            Match.status == MatchStatus.FINISHED,
        )
        matches = s.execute(match_q).scalars().all()

        if only_missing:
            matches = [m for m in matches if not m.stats]

        target = matches[:limit]
        match_keys = [
            (m.id, (m.external_ids or {}).get(adapter.source_name)) for m in target
        ]
        match_keys = [(mid, sid) for mid, sid in match_keys if sid]

    if not match_keys:
        console.print(
            "[yellow]Nothing to fetch. "
            "Either no eligible matches or none have external_ids for this source.[/yellow]"
        )
        return

    console.print(
        f"[cyan]Will sync stats for {len(match_keys)} matches "
        f"(≈ {len(match_keys)} API requests).[/cyan]"
    )

    written = 0
    for match_id, source_id in match_keys:
        try:
            stats_list = adapter.get_match_stats(source_id)
        except Exception as e:
            console.print(f"[red]  ✗ match {match_id}: {e}[/red]")
            continue
        with session_scope() as s2:
            service.persist_match_stats(s2, match_id, stats_list, adapter.source_name)
        written += 1
        if written % 10 == 0:
            console.print(f"[dim]  ...{written} written[/dim]")

    console.print(f"[green]✓ Wrote stats for {written} matches.[/green]")


@cli.command("sync-odds")
@click.option("--competition", "competition_code", required=True)
@click.option("--season", default=None)
@click.option("--limit", default=20, show_default=True, type=int,
              help="Max matches to fetch odds for (soccer). Ignored for MLB (daily-grouped pulls).")
@click.option("--days-ahead", default=7, show_default=True, type=int,
              help="For MLB: how many days of upcoming games to fetch odds for.")
def sync_odds_cmd(competition_code: str, season: str | None, limit: int, days_ahead: int):
    """
    Pull bookmaker odds for upcoming fixtures.

    Soccer comps use API-Football (per-match). MLB uses API-Baseball
    (per-day) to fill the gap that MLB Stats API doesn't cover.
    """
    if competition_code.upper() == "MLB":
        # API-Baseball path
        if not season:
            console.print("[red]✗ MLB sync-odds requires --season (year, e.g. 2026)[/red]")
            return
        try:
            season_int = int(season)
        except ValueError:
            console.print(f"[red]✗ Invalid MLB season {season!r} — must be a year[/red]")
            return
        # Service uses MLB Stats API adapter for matches, but odds sync
        # uses the API-Baseball client directly.
        adapter = _adapter_for_competition(competition_code)
        service = IngestionService(adapter)
        result = service.sync_odds_mlb(season=season_int, days_ahead=days_ahead)
        console.print(f"[green]✓ MLB odds: {result}[/green]")
        return

    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)
    result = service.sync_odds(competition_code, season=season, limit=limit)
    console.print(f"[green]✓ Odds ({competition_code}): {result}[/green]")


@cli.command("sync-injuries")
@click.option("--competition", "competition_code", required=True)
@click.option("--season", required=True, help="e.g. 2025/26 (soccer), 2026 (MLB)")
def sync_injuries_cmd(competition_code: str, season: str):
    """
    Refresh current injury list for every team in a competition/season.

    Soccer competitions use API-Football.

    MLB: NOT SUPPORTED. API-Baseball doesn't expose an injuries endpoint
    (only football/NFL/rugby have one). MLB Stats API doesn't expose one
    either. Best alternatives if you want this later: scrape MLB.com
    injury report, or subscribe to SportsDataIO.
    """
    if competition_code.upper() == "MLB":
        console.print(
            "[yellow]⚠ MLB injuries aren't available from API-Baseball or MLB Stats API.[/yellow]\n"
            "  No alternative source is wired. Skipping."
        )
        return

    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)
    result = service.sync_injuries(competition_code, season=season)
    console.print(f"[green]✓ Injuries ({competition_code}): {result}[/green]")


@cli.command("wipe-injuries")
@click.option("--confirm", is_flag=True, help="Required to actually wipe.")
def wipe_injuries_cmd(confirm: bool):
    """
    DESTRUCTIVE: clear the entire injuries table.

    Use this once after upgrading to the deduped/filtered injury sync
    (Phase 8). The old data has fixture-by-fixture duplicates which
    inflate counts massively. After wiping, run sync-injuries to refill
    with proper one-row-per-currently-injured-player data.
    """
    from src.db.database import session_scope
    from src.db.schema import Injury
    if not confirm:
        console.print("[yellow]Add --confirm to actually wipe. Showing current row counts:[/yellow]")
        with session_scope() as s:
            from sqlalchemy import func, select
            from src.db.schema import Team
            rows = list(s.execute(
                select(Team.name, func.count(Injury.id))
                .join(Injury, Injury.team_id == Team.id, isouter=True)
                .group_by(Team.id, Team.name)
                .having(func.count(Injury.id) > 0)
                .order_by(func.count(Injury.id).desc())
                .limit(10)
            ))
            for name, n in rows:
                console.print(f"  {name:30s} {n}")
        return
    with session_scope() as s:
        n = s.query(Injury).delete()
    console.print(f"[green]✓ Wiped {n} injury rows. Now run:")
    console.print(f"[green]    python cli.py sync-injuries --competition PL --season 2025/26[/green]")


@cli.command("sync-pitchers")
@click.option("--competition", "competition_code", required=True, help="e.g. MLB")
@click.option("--season", required=True, help="e.g. 2026")
@click.option("--limit", default=30, show_default=True, type=int,
              help="Max games to fetch. Each = 1 API request.")
def sync_pitchers_cmd(competition_code: str, season: str, limit: int):
    """
    Pull probable starting pitchers for upcoming MLB games.

    Stores them as MatchParticipant rows with role='starting_pitcher'.
    Auto-upgrades 'projected' → 'confirmed' as game time approaches (<4h).
    """
    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)
    result = service.sync_pitchers(competition_code, season=season, limit=limit)
    console.print(f"[green]✓ Pitchers ({competition_code}): {result}[/green]")


@cli.command("sync-pitcher-stats")
@click.option("--season", required=True, type=int, help="e.g. 2026")
def sync_pitcher_stats_cmd(season: int):
    """
    Pull season-to-date stats for all probable starting pitchers in
    upcoming MLB games (ERA, WHIP, IP, K/9 etc.).

    Targets only the ~30 pitchers scheduled to start in the next week's
    games, rather than every active arm. Run after sync-pitchers so the
    target set is current.

    Source: MLB Stats API (trusted source). Free and unlimited.
    """
    from src.adapters.registry import get_adapter
    adapter = get_adapter(sport="baseball")
    service = IngestionService(adapter)
    result = service.sync_pitcher_stats(season=season)
    console.print(f"[green]✓ Pitcher stats: {result}[/green]")


@cli.command("sync-bullpen-stats")
@click.option("--season", required=True, type=int, help="e.g. 2026")
def sync_bullpen_stats_cmd(season: int):
    """
    Pull season-to-date bullpen aggregate stats for all 30 MLB teams.

    Used at predict time to blend with starter ERA into an effective
    pitcher ERA. The bullpen handles ~40% of innings in modern MLB games.

    Source: MLB Stats API (trusted source). Free and unlimited.
    Run weekly — bullpen aggregates are stable, daily refresh not needed.
    """
    from src.adapters.registry import get_adapter
    adapter = get_adapter(sport="baseball")
    service = IngestionService(adapter)
    result = service.sync_bullpen_stats(season=season)
    console.print(f"[green]✓ Bullpen stats: {result}[/green]")


@cli.command("sync-lineups")
@click.option("--competition", "competition_code", required=True, help="e.g. PL")
@click.option("--season", required=True, help="e.g. 2025/26")
@click.option("--limit", default=20, show_default=True, type=int,
              help="Max upcoming games to fetch. Each = 1 API request.")
def sync_lineups_cmd(competition_code: str, season: str, limit: int):
    """
    Pull starting lineups for upcoming soccer fixtures.

    Within ~20min of kickoff, the adapter returns confirmed lineups.
    Earlier, we build a projected XI from the last 5 starting lineups
    (minus current injuries). Stored as Lineup rows; idempotent on
    (match_id, team_id).
    """
    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)
    result = service.sync_lineups(competition_code, season=season, limit=limit)
    console.print(f"[green]✓ Lineups ({competition_code}): {result}[/green]")


@cli.command("sync-players")
@click.option("--competition", "competition_code", required=True, help="e.g. PL")
@click.option("--season", required=True, help="e.g. 2025/26")
def sync_players_cmd(competition_code: str, season: str):
    """
    Pull full squad + season-to-date stats for every team in this
    competition/season. Powers the player power-rating system.

    Cost: 1-2 API requests per team (~30-40 calls for the full PL).
    """
    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)
    result = service.sync_players(competition_code, season=season)
    console.print(f"[green]✓ Players ({competition_code}): {result}[/green]")


# ---------------------------------------------------------------------------
# Modeling commands (Phase 2)
# ---------------------------------------------------------------------------


@cli.command("train")
@click.option("--sport", default="soccer", show_default=True,
              type=click.Choice(["soccer", "mlb"]),
              help="Which sport to train for.")
@click.option("--notes", default=None, help="Optional notes attached to this model version.")
def train_cmd(sport: str, notes: str | None):
    """Train a fresh model on all available historical data."""
    from src.walters.training import train_fresh
    from src.db.schema import Sport
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    result = train_fresh(sport=sport_enum, notes=notes)
    console.print(
        f"[green]✓ Trained candidate model {result.version} "
        f"on {result.train_size} matches.[/green]"
    )
    console.print("[dim]Run `python cli.py improve` to evaluate against production.[/dim]")


@cli.command("predict")
@click.option("--sport", default="soccer", show_default=True,
              type=click.Choice(["soccer", "mlb"]))
@click.option("--competition", "competition_code", required=True, help="e.g. PL, CL, MLB")
@click.option("--season", required=True, help="e.g. 2024/25 (soccer) or 2026 (MLB)")
@click.option("--version", default=None, help="Model version (default: production)")
def predict_cmd(sport: str, competition_code: str, season: str, version: str | None):
    """Generate predictions for all SCHEDULED matches in a competition/season."""
    from src.walters.training import generate_predictions
    from src.db.schema import Competition, Match, MatchStatus, Sport
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    n = generate_predictions(competition_code, season, model_version=version, sport=sport_enum)
    if n == 0:
        # Diagnose: is the season missing? all matches finished? no strengths?
        with session_scope() as s:
            comp = s.execute(
                select(Competition).where(Competition.code == competition_code)
            ).scalar_one_or_none()
            if not comp:
                console.print(
                    f"[red]Competition '{competition_code}' not in DB.[/red] "
                    f"Run `python cli.py sync-competitions` first."
                )
                return
            counts = dict(s.execute(
                select(Match.status, func.count())
                .where(Match.competition_id == comp.id, Match.season == season)
                .group_by(Match.status)
            ).all())
        total = sum(counts.values()) if counts else 0
        scheduled = counts.get(MatchStatus.SCHEDULED, 0)
        if total == 0:
            console.print(
                f"[yellow]No matches in DB for {competition_code} {season}. "
                f"Run `python cli.py sync-matches --competition {competition_code} "
                f"--season {season}` first.[/yellow]"
            )
        elif scheduled == 0:
            console.print(
                f"[yellow]No SCHEDULED matches in {competition_code} {season} "
                f"(found {total} total, all finished/postponed).[/yellow]"
            )
            console.print(
                f"[dim]Tip: today is {datetime.utcnow().strftime('%Y-%m-%d')}. "
                f"Try a more recent season.[/dim]"
            )
        else:
            console.print(
                f"[yellow]Found {scheduled} scheduled matches but predicted 0. "
                f"Likely cause: no historical scoring data to estimate team strengths. "
                f"Sync more finished matches.[/yellow]"
            )
        return
    console.print(f"[green]✓ Wrote {n} predictions for {competition_code} {season}.[/green]")


@cli.command("predict-worldcup")
@click.option("--season", default="2026", show_default=True)
@click.option("--competition", "competition_code", default="WC", show_default=True)
@click.option("--out", default=None, help="Output JSON path (default exports/worldcup_<date>.json)")
def predict_worldcup_cmd(season: str, competition_code: str, out: str | None):
    """
    MARKET-DERIVED World Cup predictions — NOT the club model.

    Deliberately separate from `predict`: this path NEVER touches the club
    Elo/Poisson model. For each scheduled WC match it de-vigs the 1X2
    bookmaker odds into honest probabilities and reports the market favorite.

    Rules (locked 2026-06-07): no winner shown when the market has none;
    null-team (unqualified knockout) fixtures skipped; simple proportional
    de-vig. Output is labelled market-derived, not a model prediction.
    """
    import json
    from datetime import date
    from src.db.schema import Competition, Match, MatchStatus, Odds
    from src.models.worldcup import market_prediction_for_match
    from sqlalchemy.orm import selectinload

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            console.print(f"[yellow]Competition '{competition_code}' not in DB. Run "
                          f"`sync-matches --competition {competition_code} "
                          f"--season {season}` first.[/yellow]")
            return
        matches = list(s.execute(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team),
                     selectinload(Match.odds))
            .where(Match.competition_id == comp.id,
                   Match.season == season,
                   Match.status == MatchStatus.SCHEDULED)
            .order_by(Match.utc_date)
        ).scalars().all())

        if not matches:
            console.print(f"[yellow]No scheduled {competition_code} {season} matches. "
                          f"Run sync-matches + sync-odds first.[/yellow]")
            return

        results = []
        skipped_null = 0
        skipped_nomarket = 0
        for m in matches:
            home = m.home_team.name if m.home_team else None
            away = m.away_team.name if m.away_team else None
            # only 1X2 rows feed the de-vig
            odds_1x2 = [o for o in m.odds if o.market == "1X2"]
            pred = market_prediction_for_match(m.id, home, away, odds_1x2)
            if pred is None:
                if home is None or away is None:
                    skipped_null += 1
                else:
                    skipped_nomarket += 1
                continue
            results.append(pred)

    # Console summary
    console.print(f"\n[bold]World Cup {season} — market-derived reads[/bold]")
    console.print("[dim]De-vigged bookmaker odds. NOT a model prediction. "
                  "National teams are not rated by the club model.[/dim]\n")
    if results:
        t = Table(show_header=True, header_style="bold")
        for c in ("Match", "Favorite", "Fav %", "Draw %", "Dog %", "Books"):
            t.add_column(c, justify="left" if c == "Match" else "right")
        for p in results:
            fav_name = p.home_team if p.favorite == "HOME" else p.away_team
            fav_p = p.p_home if p.favorite == "HOME" else p.p_away
            dog_p = p.p_away if p.favorite == "HOME" else p.p_home
            t.add_row(f"{p.home_team} v {p.away_team}", fav_name,
                      f"{fav_p*100:.0f}%", f"{p.p_draw*100:.0f}%",
                      f"{dog_p*100:.0f}%", str(p.n_bookmakers))
        console.print(t)
    else:
        console.print("[yellow]No matches with a usable market yet.[/yellow]")
    console.print(f"\n  Predictions: {len(results)} | "
                  f"skipped (no market): {skipped_nomarket} | "
                  f"skipped (teams TBD): {skipped_null}\n")

    # Write JSON
    out_path = out or f"exports/worldcup_{date.today().isoformat()}.json"
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"competition": competition_code, "season": season,
                   "source": "market-derived",
                   "predictions": [p.as_dict() for p in results]}, f, indent=2)
    console.print(f"[green]✓ Wrote {len(results)} market-derived reads to {out_path}.[/green]")


@cli.command("evaluate")
@click.option("--sport", default="soccer", show_default=True,
              type=click.Choice(["soccer", "mlb"]))
def evaluate_cmd(sport: str):
    """Score predictions for finished matches that don't have outcomes yet."""
    from src.walters.training import evaluate_finished
    from src.db.schema import Sport
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    n = evaluate_finished(sport=sport_enum)
    console.print(f"[green]✓ Evaluated {n} predictions.[/green]")


@cli.command("improve")
@click.option("--sport", default="soccer", show_default=True,
              type=click.Choice(["soccer", "mlb"]))
@click.option("--holdout-days", default=30, show_default=True, type=int)
@click.option("--min-delta", default=0.005, show_default=True, type=float,
              help="Min log-loss improvement to promote candidate.")
@click.option("--input-cadence-days", default=7, show_default=True, type=int,
              help="How often (days) the input-candidate evaluation runs within improve.")
@click.option("--force-input-eval", is_flag=True, default=False,
              help="Run the input-candidate evaluation now regardless of cadence.")
def improve_cmd(sport: str, holdout_days: int, min_delta: float,
                input_cadence_days: int, force_input_eval: bool):
    """
    Full improvement loop: evaluate → train candidate → compare → promote if
    better. The same-structure retrain runs daily (fast). The INPUT-CANDIDATE
    evaluation — testing production+input variants through the same promotion
    gate — is folded in but self-throttles to a weekly cadence (inputs move
    slowly; daily testing manufactures false positives).
    """
    from src.walters.training import improve
    from src.db.schema import Sport
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    result = improve(sport=sport_enum, holdout_days=holdout_days, min_delta=min_delta)
    color = "green" if result.promoted else "yellow"
    label = "PROMOTED" if result.promoted else "REJECTED"
    console.print(f"[{color}]✓ Candidate {result.candidate_version}: {label}[/{color}]")
    console.print(f"  [dim]{result.reasoning}[/dim]")
    if result.candidate_log_loss is not None and result.production_log_loss is not None:
        t = Table(show_header=True)
        t.add_column("Model")
        t.add_column("Log loss", justify="right")
        t.add_column("Holdout size", justify="right")
        t.add_row("Production", f"{result.production_log_loss:.4f}", str(result.holdout_size))
        t.add_row("Candidate", f"{result.candidate_log_loss:.4f}", str(result.holdout_size))
        console.print(t)

    # --- input-candidate evaluation (cadence-gated, MLB only) ---
    if sport_enum == Sport.MLB:
        from src.walters.input_candidates import (
            due_for_input_eval, mark_input_eval_done, evaluate_input_candidates,
            TRACKED_INPUTS)
        if force_input_eval or due_for_input_eval(input_cadence_days):
            console.print("\n[bold]Input-candidate evaluation[/bold] "
                          "[dim](weekly cadence — widened candidate axis)[/dim]")
            statuses = evaluate_input_candidates(sport_enum, holdout_days, min_delta)
            consumable = [s for s in statuses if s.model_consumable]
            if not consumable:
                console.print("  [dim]No tracked input is currently model-consumable. Each "
                              "needs (a) Stage-1 validation, (b) as-of-date historical "
                              "reconstruction, and (c) a feature slot in the run-profile "
                              "model. Status:[/dim]")
                for s in statuses:
                    console.print(f"    • [yellow]{s.name}[/yellow]: {s.reason}")
                console.print("  [dim]This is the honest current state — nothing has earned a "
                              "model slot (all failed Stage-1 / are collinear with team "
                              "quality). The framework is READY: when a signal passes "
                              "validation, it plugs in here and flows through the same "
                              "promotion gate. Widening the candidate axis is what will let "
                              "improve promote — but only an input that genuinely helps.[/dim]")
            else:
                for s in consumable:
                    verdict = "PROMOTE" if s.beat_production else "reject"
                    console.print(f"    • {s.name}: candidate {s.holdout_log_loss:.4f} vs "
                                  f"prod {s.production_log_loss:.4f} → {verdict}")
            mark_input_eval_done()
        else:
            console.print("\n[dim]Input-candidate evaluation: not due "
                          f"(runs every {input_cadence_days}d; use --force-input-eval to run "
                          "now).[/dim]")


# --------------------------------------------------------------------------
# Production model config editing (first-class, separate from retrain/promote)
# --------------------------------------------------------------------------
# A config edit is a RECALIBRATION of the existing model, not a new model, so
# it deliberately does NOT go through the train→promote→log-loss gate (which
# is built for retrains and is blind to calibration-only improvements). These
# edits are surgical, audited, and reversible. Validate against calibration
# AFTER applying (run a week, then calibration-deep), not via a pre-promotion
# holdout score.

# Editable BaseballConfig fields, with a type and a sanity range. Anything not
# listed is rejected — a general editor needs guardrails so a typo can't
# silently poison the live model.
_EDITABLE_BASEBALL_FIELDS = {
    "home_run_boost":       (float, 0.0, 0.5),
    "pitcher_damping":      (float, 0.0, 1.0),
    "dispersion_k":         (float, 1.0, 12.0),
    "league_runs_per_game": (float, 6.0, 12.0),
    "league_era":           (float, 2.5, 6.0),
    "pyth_exponent":        (float, 1.0, 2.5),
    "default_total_line":   (float, 6.0, 12.0),
    "max_runs":             (int,   15, 40),
    "recal_lo":             (float, 0.55, 0.65),
    "recal_hi":             (float, 0.65, 0.80),
    "recal_target":         (float, 0.50, 0.62),
    "market_blend_w":       (float, 0.0, 1.0),
    "run_shrink_frac":      (float, 0.0, 0.6),
    "run_shrink_mean":      (float, 3.5, 5.5),
    "starter_ip_per_start": (float, 3.0, 9.0),
    # pitcher_anchor_mode is a string toggle, validated separately below
    # recal_enabled, market_blend_enabled, run_shrink_enabled,
    # starter_eff_ip_enabled bools below
}
_ANCHOR_MODES = {"team_ra", "league"}


def _apply_production_config_edit(sport_enum, field, value, yes):
    """
    Shared core for editing the production model's frozen BaseballConfig.
    Returns True if a change was applied. Validates field + range, prints a
    before/after, asks for confirmation (unless yes), writes an audit entry.
    """
    import copy
    from src.db.schema import ModelVersion
    from src.walters.training import _family_for, _current_production_version

    # Validate field + coerce/range-check value
    if field == "pitcher_anchor_mode":
        if value not in _ANCHOR_MODES:
            console.print(f"[red]pitcher_anchor_mode must be one of {_ANCHOR_MODES}.[/red]")
            return False
        coerced = value
    elif field in ("recal_enabled", "market_blend_enabled", "run_shrink_enabled",
                   "starter_eff_ip_enabled"):
        if str(value).lower() in ("true", "1", "yes", "on"):
            coerced = True
        elif str(value).lower() in ("false", "0", "no", "off"):
            coerced = False
        else:
            console.print(f"[red]{field} must be true/false.[/red]")
            return False
    elif field in _EDITABLE_BASEBALL_FIELDS:
        typ, lo, hi = _EDITABLE_BASEBALL_FIELDS[field]
        try:
            coerced = typ(value)
        except (TypeError, ValueError):
            console.print(f"[red]{field} must be of type {typ.__name__}.[/red]")
            return False
        if not (lo <= coerced <= hi):
            console.print(f"[red]{field}={coerced} is outside the sane range "
                          f"[{lo}, {hi}]. Refusing to set a likely-bad value.[/red]")
            return False
    else:
        editable = sorted(list(_EDITABLE_BASEBALL_FIELDS) + ["pitcher_anchor_mode"])
        console.print(f"[red]'{field}' is not an editable config field.[/red]")
        console.print(f"  Editable fields: {', '.join(editable)}")
        return False

    with session_scope() as s:
        prod_version = _current_production_version(s, sport_enum)
        if prod_version is None:
            console.print("[red]No production model version found.[/red]")
            return False
        mv = s.execute(
            select(ModelVersion).where(
                ModelVersion.sport == sport_enum,
                ModelVersion.model_family == _family_for(sport_enum),
                ModelVersion.version == prod_version,
            )
        ).scalar_one()

        params = copy.deepcopy(mv.parameters or {})
        bc = params.get("baseball_config")
        if bc is None:
            console.print("[red]Production version has no baseball_config — nothing to update.[/red]")
            return False
        old = bc.get(field)
        if old == coerced:
            console.print(f"[yellow]{field} is already {coerced} on {prod_version}. No change.[/yellow]")
            return False

        console.print(f"\n[bold]Production model:[/bold] {prod_version}")
        console.print(f"  {field}: [yellow]{old}[/yellow] → [green]{coerced}[/green]")
        console.print(f"  (Reversible: re-run with the old value {old!r} to restore.)\n")
        if not yes and not click.confirm("Apply this change to the production model?"):
            console.print("Aborted. No change made.")
            return False

        bc = dict(bc)
        bc[field] = coerced
        params["baseball_config"] = bc
        edits = list(params.get("manual_config_edits", []))
        edits.append({"field": field, "from": old, "to": coerced,
                      "at": datetime.utcnow().isoformat()})
        params["manual_config_edits"] = edits
        mv.parameters = params
        s.add(mv)

    console.print(f"[green]✓ Updated {prod_version}: {field} = {coerced}.[/green]")
    console.print("  Next: run `python cli.py predict --sport mlb --competition MLB "
                  "--season 2026` to regenerate predictions with the new value.\n")
    return True


@cli.command("show-config")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
def show_config_cmd(sport: str):
    """
    Show the PRODUCTION model's live BaseballConfig and any manual edits.

    Read-only. Use this to see what the live model is actually using and the
    history of recalibration edits (set-config / set-home-boost), so a config
    change is always visible and auditable rather than hidden in the DB.
    """
    from src.db.schema import Sport, ModelVersion
    from src.walters.training import _family_for, _current_production_version
    sport_enum = Sport.MLB if sport in ("mlb", "baseball") else Sport.SOCCER
    with session_scope() as s:
        prod_version = _current_production_version(s, sport_enum)
        if prod_version is None:
            console.print("[red]No production model version found.[/red]")
            return
        mv = s.execute(
            select(ModelVersion).where(
                ModelVersion.sport == sport_enum,
                ModelVersion.model_family == _family_for(sport_enum),
                ModelVersion.version == prod_version,
            )
        ).scalar_one()
        params = mv.parameters or {}
        bc = params.get("baseball_config", {})
        console.print(f"\n[bold]Production model:[/bold] {prod_version}")
        t = Table(show_header=True, header_style="bold")
        t.add_column("Config field"); t.add_column("Live value", justify="right")
        for k in sorted(bc):
            t.add_row(k, str(bc[k]))
        console.print(t)
        edits = params.get("manual_config_edits", [])
        if edits:
            console.print(f"\n[bold]Manual recalibration edits ({len(edits)}):[/bold]")
            for e in edits:
                console.print(f"  {e.get('at','?')[:19]}  {e['field']}: {e['from']} → {e['to']}")
        else:
            console.print("\n[dim]No manual config edits — running as trained.[/dim]")
        console.print()


@cli.command("set-config")
@click.option("--field", required=True, help="BaseballConfig field to edit (e.g. home_run_boost).")
@click.option("--value", required=True, help="New value.")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
def set_config_cmd(field: str, value: str, sport: str, yes: bool):
    """
    Edit a parameter on the PRODUCTION model's frozen BaseballConfig, in place.

    A config edit is a RECALIBRATION of the existing model, not a new model —
    so it intentionally bypasses the train→promote→log-loss gate, which is
    built for retrains and can't see calibration-only improvements. Surgical,
    audited (params.manual_config_edits), and reversible (re-run with the old
    value). Validate AFTER, by running a week and re-checking calibration-deep.

    Editable fields are whitelisted with sane ranges so a typo can't poison
    the live model. Run with an invalid --field to see the list.
    """
    from src.db.schema import Sport
    sport_enum = Sport.MLB if sport in ("mlb", "baseball") else Sport.SOCCER
    _apply_production_config_edit(sport_enum, field, value, yes)


@cli.command("set-home-boost")
@click.option("--value", type=float, required=True,
              help="New home_run_boost (e.g. 0.08 for the fix, 0.15 to revert).")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
def set_home_boost_cmd(value: float, sport: str, yes: bool):
    """
    Convenience wrapper for `set-config --field home_run_boost`.
    Kept because home_run_boost is the most common recalibration lever.
    """
    from src.db.schema import Sport
    sport_enum = Sport.MLB if sport in ("mlb", "baseball") else Sport.SOCCER
    _apply_production_config_edit(sport_enum, "home_run_boost", value, yes)




@cli.command("model-versions")
def model_versions_cmd():
    """Show trained model versions and their status."""
    from src.db.schema import ModelVersion
    with session_scope() as s:
        rows = list(s.execute(
            select(ModelVersion).order_by(ModelVersion.created_at.desc())
        ).scalars())
        if not rows:
            console.print("[yellow]No model versions yet. Run `python cli.py train`.[/yellow]")
            return
        t = Table(show_header=True)
        t.add_column("Version", style="cyan")
        t.add_column("Family")
        t.add_column("Status")
        t.add_column("Train size", justify="right")
        t.add_column("Holdout loss", justify="right")
        t.add_column("Created")
        for mv in rows:
            status_color = {
                "production": "green",
                "candidate": "cyan",
                "rejected": "yellow",
                "shelved": "dim",
            }.get(mv.status, "white")
            t.add_row(
                mv.version,
                mv.model_family,
                f"[{status_color}]{mv.status}[/{status_color}]",
                str(mv.train_size or "—"),
                f"{mv.holdout_log_loss:.4f}" if mv.holdout_log_loss is not None else "—",
                mv.created_at.strftime("%Y-%m-%d %H:%M") if mv.created_at else "",
            )
        console.print(t)


@cli.command("model-report")
@click.option("--limit", default=20, show_default=True, type=int)
def model_report_cmd(limit: int):
    """Show recent prediction outcomes (right/wrong post-mortem feed)."""
    from src.db.schema import Match, Prediction, PredictionOutcome
    with session_scope() as s:
        rows = list(s.execute(
            select(PredictionOutcome, Prediction, Match)
            .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
            .join(Match, Match.id == Prediction.match_id)
            .order_by(PredictionOutcome.evaluated_at.desc())
            .limit(limit)
        ).all())
        if not rows:
            console.print(
                "[yellow]No evaluated predictions yet. "
                "Run `python cli.py evaluate` after fixtures finish.[/yellow]"
            )
            return

        t = Table(show_header=True)
        t.add_column("Date")
        t.add_column("Match")
        t.add_column("Result")
        t.add_column("Top pick?", justify="center")
        t.add_column("Log loss", justify="right")
        t.add_column("Note", style="dim")
        for outcome, pred, match in rows:
            hit = "✓" if outcome.top_pick_hit else "✗"
            color = "green" if outcome.top_pick_hit else "red"
            ll = f"{outcome.log_loss:.3f}" if outcome.log_loss is not None else "—"
            home = match.home_team.name if match.home_team else "?"
            away = match.away_team.name if match.away_team else "?"
            t.add_row(
                match.utc_date.strftime("%Y-%m-%d"),
                f"{home} vs {away}",
                f"{match.home_score}-{match.away_score}",
                f"[{color}]{hit}[/{color}]",
                ll,
                outcome.notes or "",
            )
        console.print(t)


@cli.command("calibration")
@click.option("--sport", type=click.Choice(["soccer", "mlb", "baseball"]), required=True)
@click.option("--days", "window_days", default=None, type=int,
              help="Only include matches in the last N days. Default: all scored predictions.")
def calibration_cmd(sport: str, window_days: int | None):
    """
    Show a calibration / reliability table for scored predictions.

    Bins predictions by top-pick probability and compares predicted
    confidence to actual hit rate. A well-calibrated model has these
    roughly equal in each bin.

    Reports Expected Calibration Error (ECE) and, if the data shows
    systematic overconfidence, suggests a temperature-scaling factor
    for review (not auto-applied).
    """
    from src.db.schema import Sport
    from src.walters.calibration import compute_calibration, suggested_temperature

    sport_enum = Sport.MLB if sport in ("mlb", "baseball") else Sport.SOCCER
    report = compute_calibration(sport=sport_enum, window_days=window_days)

    if report.total == 0:
        console.print("[yellow]No scored predictions found for that filter.[/yellow]")
        return

    window_str = f"last {window_days} days" if window_days else "all time"
    console.print(f"\n[bold]Calibration report — {report.sport.upper()} ({window_str})[/bold]")
    console.print(f"  Scored predictions: {report.total}")
    console.print(f"  Overall hit rate:   {report.overall_hit_rate*100:.1f}%")
    console.print(f"  Avg log-loss:       {report.avg_log_loss:.4f}")
    console.print(f"  Expected Calibration Error (ECE): {report.ece*100:.2f}pp")
    console.print()

    from rich.table import Table
    t = Table(show_header=True, header_style="bold")
    t.add_column("Conf bin")
    t.add_column("N", justify="right")
    t.add_column("Predicted", justify="right")
    t.add_column("Actual", justify="right")
    t.add_column("Gap", justify="right")
    t.add_column("Note")

    for b in report.bins:
        gap = b.gap
        gap_str = f"{gap*100:+.1f}pp"
        # Color the gap: green if small, yellow if moderate, red if large+reliable
        if not b.reliable:
            note = "sparse — ignore"
            gap_display = f"[dim]{gap_str}[/dim]"
        elif abs(gap) >= 0.08:
            note = "[red]overconfident[/red]" if gap < 0 else "[cyan]underconfident[/cyan]"
            gap_display = f"[bold]{gap_str}[/bold]"
        elif abs(gap) >= 0.04:
            note = "mild"
            gap_display = gap_str
        else:
            note = "[green]well-calibrated[/green]"
            gap_display = gap_str
        t.add_row(
            f"{b.low*100:.0f}-{b.high*100:.0f}%",
            str(b.count),
            f"{b.predicted_avg*100:.1f}%",
            f"{b.actual_rate*100:.1f}%",
            gap_display,
            note,
        )
    console.print(t)

    # Temperature suggestion
    temp = suggested_temperature(report)
    console.print()
    if temp is None:
        console.print("[green]No systematic overconfidence detected in reliable bins "
                      "(or insufficient data). No calibration adjustment suggested.[/green]")
    else:
        console.print(f"[yellow]⚠ Reliable bins show systematic overconfidence.[/yellow]")
        console.print(f"  Suggested temperature factor: [bold]{temp}[/bold]")
        console.print(f"  Adjustment would be: p_adj = 0.5 + (p_raw - 0.5) × {temp}")
        console.print(f"  (This is a suggestion for review, NOT auto-applied.)")
    console.print()


@cli.command("calibration-deep")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--actionable-only", is_flag=True, default=False,
              help="Exclude toss-ups (top pick < 0.53) — grade only picks that claimed an edge.")
@click.option("--since", default=None,
              help="Only predictions COMPUTED on/after this date (YYYY-MM-DD). "
                   "Use to isolate a config era, e.g. run-shrink went live 2026-06-23.")
def calibration_deep_cmd(sport: str, actionable_only: bool, since: str):
    """
    Combined calibration read for the June-7-style checkpoint.

    One pass, three views over the same scored predictions:
      1. Band-by-band calibration (predicted vs actual by confidence bin)
      2. Split by model version: PRE-12.5 (league anchor) vs POST-12.5
         (team_ra anchor) — separates the current model from the old one's
         ghost (the 65-70% bin defect was mostly pre-12.5).
      3. Split by bullpen-swing flag: big-swing (>=1.5 ERA divergence) vs
         not — tests whether the overconfidence found 2026-06-05 holds.

    --since filters by Prediction.computed_at so you can isolate a config era
    (e.g. only run-shrink-era predictions) and ask whether a defect seen across
    all history survives in the CURRENT model.

    Read-only. No probability is changed.
    """
    from src.db.schema import Sport, Match, Prediction, PredictionOutcome

    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since)

    with session_scope() as s:
        q = (
            select(Prediction, PredictionOutcome)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.top_pick_hit.isnot(None))
        )
        if since_dt is not None:
            q = q.where(Prediction.computed_at >= since_dt)
        rows = s.execute(q).all()

        recs = []
        for pred, outcome in rows:
            probs = {"home_win": pred.home_win_prob, "away_win": pred.away_win_prob}
            if pred.draw_prob is not None:
                probs["draw"] = pred.draw_prob
            non_null = {k: v for k, v in probs.items() if v is not None}
            if not non_null:
                continue
            top_prob = max(non_null.values())
            fb = pred.factor_breakdown or {}
            # bullpen swing
            swing = 0.0
            for side in ("home", "away"):
                det = fb.get(f"{side}_bullpen_detail")
                if det and det.get("season_era") is not None and det.get("recent_era") is not None:
                    swing = max(swing, abs(det["recent_era"] - det["season_era"]))
            recs.append({
                "top_prob": top_prob,
                "hit": bool(outcome.top_pick_hit),
                "post125": fb.get("pitcher_anchor_mode") == "team_ra",
                "big_swing": swing >= 1.5,
                "p_one_run": fb.get("p_one_run"),
                "home_boost": fb.get("home_run_boost"),
            })

    if actionable_only:
        recs = [r for r in recs if r["top_prob"] >= 0.53]

    if not recs:
        console.print("[yellow]No scored predictions found.[/yellow]")
        return

    def summarize(rs):
        n = len(rs)
        if n == 0:
            return None
        pred = sum(r["top_prob"] for r in rs) / n * 100
        act = sum(1 for r in rs if r["hit"]) / n * 100
        return n, pred, act, act - pred

    filt = " (actionable only, ≥53%)" if actionable_only else ""
    if since:
        filt += f" (computed ≥ {since})"
    console.print(f"\n[bold]Deep calibration — MLB{filt}[/bold]")
    console.print(f"  Total scored predictions: {len(recs)}\n")

    # View 1: band-by-band
    from rich.table import Table
    t1 = Table(show_header=True, header_style="bold", title="1. By confidence band")
    for c in ("Band", "N", "Predicted", "Actual", "Gap", "Note"):
        t1.add_column(c, justify="right" if c != "Band" and c != "Note" else "left")
    bands = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.01)]
    for lo, hi in bands:
        rs = [r for r in recs if lo <= r["top_prob"] < hi]
        sm = summarize(rs)
        if not sm:
            continue
        n, pred, act, gap = sm
        if n < 10:
            note = "sparse"
        elif gap <= -8:
            note = "[red]overconfident[/red]"
        elif gap >= 8:
            note = "[cyan]underconfident[/cyan]"
        elif abs(gap) >= 4:
            note = "mild"
        else:
            note = "[green]well-calibrated[/green]"
        label = f"{lo*100:.0f}-{hi*100:.0f}%" if hi <= 1 else f"{lo*100:.0f}%+"
        t1.add_row(label, str(n), f"{pred:.1f}%", f"{act:.1f}%", f"{gap:+.1f}pp", note)
    console.print(t1)
    console.print()

    # View 2: pre/post 12.5
    t2 = Table(show_header=True, header_style="bold", title="2. By model version (anchor)")
    for c in ("Cohort", "N", "Predicted", "Actual", "Gap"):
        t2.add_column(c, justify="right" if c != "Cohort" else "left")
    for label, rs in [("PRE-12.5 (league)", [r for r in recs if not r["post125"]]),
                      ("POST-12.5 (team_ra)", [r for r in recs if r["post125"]])]:
        sm = summarize(rs)
        if sm:
            n, pred, act, gap = sm
            t2.add_row(label, str(n), f"{pred:.1f}%", f"{act:.1f}%", f"{gap:+.1f}pp")
    # also high-conf only within each
    console.print(t2)
    console.print("  [dim](high-conf ≥60% within each cohort:)[/dim]")
    for label, rs in [("PRE-12.5", [r for r in recs if not r["post125"] and r["top_prob"] >= 0.60]),
                      ("POST-12.5", [r for r in recs if r["post125"] and r["top_prob"] >= 0.60])]:
        sm = summarize(rs)
        if sm:
            n, pred, act, gap = sm
            console.print(f"    {label}: n={n}, predicted {pred:.1f}%, actual {act:.1f}%, gap {gap:+.1f}pp")
    console.print()

    # View 3: bullpen swing
    t3 = Table(show_header=True, header_style="bold", title="3. By bullpen recent-form swing")
    for c in ("Cohort", "N", "Predicted", "Actual", "Gap"):
        t3.add_column(c, justify="right" if c != "Cohort" else "left")
    for label, rs in [("BIG swing (≥1.5)", [r for r in recs if r["big_swing"]]),
                      ("small/no swing", [r for r in recs if not r["big_swing"]])]:
        sm = summarize(rs)
        if sm:
            n, pred, act, gap = sm
            t3.add_row(label, str(n), f"{pred:.1f}%", f"{act:.1f}%", f"{gap:+.1f}pp")
    console.print(t3)
    # post-12.5 big-swing isolated — the cleanest test for the taper decision
    bs_post = [r for r in recs if r["big_swing"] and r["post125"]]
    sm = summarize(bs_post)
    if sm:
        n, pred, act, gap = sm
        console.print(f"  [dim]big-swing AND post-12.5 (taper decision cohort): "
                      f"n={n}, predicted {pred:.1f}%, actual {act:.1f}%, gap {gap:+.1f}pp[/dim]")
    console.print()
    console.print("[dim]Read: if POST-12.5 high-conf is calibrated AND big-swing+post-12.5 "
                  "is still overconfident → build the bullpen taper. If big-swing has "
                  "regressed to calibrated → hold, it was noise.[/dim]")
    console.print()

    # View 4: CROSS the 60-70% defect band against bullpen-swing and close-game.
    # Goal: are the 60-70% overconfidence and the bullpen-swing overconfidence
    # the SAME games (one fix) or DIFFERENT (two fixes)? Only build what the
    # data says is distinct.
    band6070 = [r for r in recs if 0.60 <= r["top_prob"] < 0.70]
    console.print("[bold]4. Crossing the 60-70% defect band[/bold]")
    if len(band6070) < 10:
        console.print("  [yellow]60-70% band too sparse to cross.[/yellow]\n")
    else:
        sm = summarize(band6070)
        n, pred, act, gap = sm
        console.print(f"  60-70% overall: n={n}, predicted {pred:.1f}%, actual {act:.1f}%, gap {gap:+.1f}pp\n")
        t4 = Table(show_header=True, header_style="bold")
        for c in ("Split", "N", "Predicted", "Actual", "Gap"):
            t4.add_column(c, justify="right" if c != "Split" else "left")
        # by bullpen swing within 60-70
        for label, rs in [
            ("  swing ≥1.5", [r for r in band6070 if r["big_swing"]]),
            ("  small/no swing", [r for r in band6070 if not r["big_swing"]]),
        ]:
            sm = summarize(rs)
            if sm:
                n, pred, act, gap = sm
                t4.add_row(label, str(n), f"{pred:.1f}%", f"{act:.1f}%", f"{gap:+.1f}pp")
        # by close-game (one-run mass) within 60-70 — only rows that have p_one_run
        has1r = [r for r in band6070 if r.get("p_one_run") is not None]
        if has1r:
            for label, rs in [
                ("  close (1run ≥.185)", [r for r in has1r if r["p_one_run"] >= 0.185]),
                ("  not close", [r for r in has1r if r["p_one_run"] < 0.185]),
            ]:
                sm = summarize(rs)
                if sm:
                    n, pred, act, gap = sm
                    t4.add_row(label, str(n), f"{pred:.1f}%", f"{act:.1f}%", f"{gap:+.1f}pp")
        else:
            t4.add_row("  (close-game: no p_one_run", "—", "yet in", "scored", "set)")
        console.print(t4)
        console.print("  [dim]If the gap concentrates in ONE split (e.g. swing games carry "
                      "it, non-swing are clean) → one targeted fix. If both splits are "
                      "uniformly bad → the 60-70% band itself needs recalibration, not a "
                      "per-mechanism patch.[/dim]")
    console.print()


@cli.command("calibration-market")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--since", default="2026-06-14",
              help="Only predictions on/after this date (default: recal go-live).")
def calibration_market_cmd(sport: str, since: str):
    """
    Adjudicate "be more aggressive with recal" vs "trust the market more".

    Splits scored predictions by whether the model AGREES or DISAGREES with the
    market favorite, using best_value_edge_pct (stored only on recent preds).
    Read-only.

      - If losses are spread EVENLY across agree/disagree → genuine band
        overconfidence (or cold variance) → more aggressive recal is the lever.
      - If losses CONCENTRATE in disagree games → MISDIRECTION: the model picks
        the wrong side when it fights the market. Recal can't fix that (it just
        buries a wrong pick); the fix is to blend toward the market when they
        disagree.

    `since` defaults to recal go-live (2026-06-14) so this measures the
    post-recal games specifically — the ones in the current tally.
    """
    from datetime import datetime
    from src.db.schema import Sport, Match, Prediction, PredictionOutcome
    since_dt = datetime.fromisoformat(since)

    with session_scope() as s:
        rows = s.execute(
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   Match.utc_date >= since_dt,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all()

    recs = []
    for pred, outcome, m in rows:
        probs = {"home_win": pred.home_win_prob, "away_win": pred.away_win_prob}
        nn = {k: v for k, v in probs.items() if v is not None}
        if not nn:
            continue
        top_prob = max(nn.values())
        # clv = model top-pick prob - market de-vigged prob for same selection.
        # Positive = model ABOVE market (model disagrees, likes it more than the
        # book). Near zero = model agrees with the market. This is populated by
        # `evaluate` and is exactly the model-vs-market signal we need.
        recs.append({"top_prob": top_prob, "hit": bool(outcome.top_pick_hit),
                     "edge": outcome.clv})

    if not recs:
        console.print(f"[yellow]No scored predictions since {since}.[/yellow]")
        return

    def summarize(rs):
        n = len(rs)
        if n == 0:
            return None
        pred = sum(r["top_prob"] for r in rs) / n * 100
        act = sum(1 for r in rs if r["hit"]) / n * 100
        return n, pred, act, act - pred

    n, pred, act, gap = summarize(recs)
    console.print(f"\n[bold]Post-recal calibration & market split (since {since})[/bold]")
    console.print(f"  All scored: n={n}, predicted {pred:.1f}%, actual {act:.1f}%, "
                  f"gap {gap:+.1f}pp\n")

    have_edge = [r for r in recs if r["edge"] is not None]
    if not have_edge:
        console.print("[yellow]No clv stored on these preds — run `evaluate` first "
                      "(clv is computed at evaluation time).[/yellow]\n")
        return

    from rich.table import Table
    t = Table(show_header=True, header_style="bold")
    for c in ("Model vs market", "N", "Predicted", "Actual", "Gap"):
        t.add_column(c, justify="right" if c != "Model vs market" else "left")
    # clv is a fraction: model_prob - market_devigged_prob. Positive = model
    # above market (disagrees in its own favor). Define agreement as |clv|<=0.02.
    for label, rs in [
        ("agree (|clv| <= 2pp)", [r for r in have_edge if abs(r["edge"]) <= 0.02]),
        ("model above mkt (clv > 2pp)", [r for r in have_edge if r["edge"] > 0.02]),
        ("  strongly above (>8pp)", [r for r in have_edge if r["edge"] > 0.08]),
        ("model below mkt (clv < -2pp)", [r for r in have_edge if r["edge"] < -0.02]),
    ]:
        sm = summarize(rs)
        if sm:
            gn, gp, ga, gg = sm
            flag = " ⚠" if gn < 12 else ""
            t.add_row(label + flag, str(gn), f"{gp:.1f}%", f"{ga:.1f}%", f"{gg:+.1f}pp")
    console.print(t)
    console.print("  [dim]'model above mkt' = model picked a side the market rates "
                  "lower (disagreement). If the gap concentrates there → misdirection "
                  "(the model is wrong when it fights the book) → blend toward market. "
                  "Even gap → overconfidence/variance → recal is the lever. "
                  "(⚠ = thin, n<12, directional only.)[/dim]\n")


@cli.command("calibration-series")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--lo", default=0.60, help="Band lower bound (default 0.60).")
@click.option("--hi", default=0.70, help="Band upper bound (default 0.70).")
def calibration_series_cmd(sport: str, lo: float, hi: float):
    """
    Diagnose WHY the 60-70% band is overconfident, via four pre-motivated
    slices. Read-only — changes no probabilities. Each slice is a falsifiable
    structural hypothesis, not a fishing expedition (we deliberately do NOT
    grid-search every field, which would surface spurious splits at this n).

    Slices, all crossed against the defect band:
      1. SERIES POSITION (Anthony's hypothesis): is the favorite in game 1 vs
         game 2 vs game 3+ of a series? Tests whether moderate favorites erode
         as a series progresses (fatigue, must-win opposing aces, revenge
         dynamics) — a macro variable the per-game model is blind to.
      2. FAVORITE HOME/ROAD: did the home fix overshoot, or are road favorites
         specifically the overconfident ones?
      3. MARKET AGREEMENT: is the model overconfident specifically when it
         DISAGREES with the market (large positive edge)? Tests the
         "model can't see what the market sees" channel.
      4. RUN ENVIRONMENT: are high-park-factor / high-total games the
         overconfident ones? (June-7 flagged high-total games at -14pp.)

    Series position is reconstructed from match dates + team pairing (no
    explicit series field exists): consecutive games between the same two
    teams within 4 days are treated as one series.
    """
    from src.db.schema import Sport, Match, Prediction, PredictionOutcome
    from datetime import timedelta

    with session_scope() as s:
        rows = s.execute(
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.top_pick_hit.isnot(None))
            .order_by(Match.utc_date)
        ).all()

        # --- Reconstruct series position from team-pair + date proximity ---
        # Group all (home,away) unordered pairs, walk chronologically, and
        # number consecutive games within 4 days as game 1,2,3... of a series.
        from collections import defaultdict
        pair_games = defaultdict(list)  # frozenset({hid,aid}) -> [(date, match_id)]
        for pred, outcome, m in rows:
            pair_games[frozenset((m.home_team_id, m.away_team_id))].append(
                (m.utc_date, m.id))
        series_pos = {}  # match_id -> 1,2,3...
        for pair, games in pair_games.items():
            games.sort()
            pos = 0
            last_date = None
            for dt, mid in games:
                if last_date is None or (dt - last_date) > timedelta(days=4):
                    pos = 1
                else:
                    pos += 1
                series_pos[mid] = pos
                last_date = dt

        recs = []
        for pred, outcome, m in rows:
            probs = {"home_win": pred.home_win_prob, "away_win": pred.away_win_prob}
            non_null = {k: v for k, v in probs.items() if v is not None}
            if not non_null:
                continue
            top_prob = max(non_null.values())
            fb = pred.factor_breakdown or {}
            top_is_home = pred.home_win_prob is not None and \
                pred.home_win_prob >= (pred.away_win_prob or 0)
            recs.append({
                "top_prob": top_prob,
                "hit": bool(outcome.top_pick_hit),
                "series_pos": series_pos.get(m.id),
                "fav_home": top_is_home,
                "edge_pct": pred.best_value_edge_pct,
                "park_factor": fb.get("park_factor"),
            })

    band = [r for r in recs if lo <= r["top_prob"] < hi]
    console.print(f"\n[bold]Series & structural diagnosis — {lo*100:.0f}-{hi*100:.0f}% band[/bold]")
    if len(band) < 10:
        console.print(f"  [yellow]Band too sparse (n={len(band)}).[/yellow]\n")
        return

    def summarize(rs):
        n = len(rs)
        if n == 0:
            return None
        pred = sum(r["top_prob"] for r in rs) / n * 100
        act = sum(1 for r in rs if r["hit"]) / n * 100
        return n, pred, act, act - pred

    n, pred, act, gap = summarize(band)
    console.print(f"  Band overall: n={n}, predicted {pred:.1f}%, actual {act:.1f}%, "
                  f"gap {gap:+.1f}pp\n")

    from rich.table import Table

    def slice_table(title, groups):
        t = Table(show_header=True, header_style="bold", title=title)
        for c in ("Split", "N", "Predicted", "Actual", "Gap"):
            t.add_column(c, justify="right" if c != "Split" else "left")
        for label, rs in groups:
            sm = summarize(rs)
            if sm:
                gn, gp, ga, gg = sm
                flag = " ⚠" if gn < 12 else ""
                t.add_row(label + flag, str(gn), f"{gp:.1f}%", f"{ga:.1f}%", f"{gg:+.1f}pp")
        console.print(t)

    # 1. Series position
    slice_table("1. By series position (⚠ = thin, n<12)", [
        ("game 1", [r for r in band if r["series_pos"] == 1]),
        ("game 2", [r for r in band if r["series_pos"] == 2]),
        ("game 3+", [r for r in band if r["series_pos"] and r["series_pos"] >= 3]),
    ])
    console.print("  [dim]If game 1 is calibrated and game 2/3+ carry the gap → series "
                  "erosion is real and the model's series-blindness is the mechanism.[/dim]\n")

    # 2. Favorite home/road
    slice_table("2. By favorite home/road", [
        ("home favorite", [r for r in band if r["fav_home"]]),
        ("road favorite", [r for r in band if not r["fav_home"]]),
    ])
    console.print()

    # 3. Market agreement (edge_pct: large positive = model above market)
    have_edge = [r for r in band if r["edge_pct"] is not None]
    if have_edge:
        slice_table("3. By market agreement (model edge vs market)", [
            ("big edge ≥8pp (disagree)", [r for r in have_edge if r["edge_pct"] >= 8]),
            ("small edge <8pp (agree)", [r for r in have_edge if r["edge_pct"] < 8]),
        ])
        console.print("  [dim]If the gap concentrates in big-edge games → the model is "
                      "overconfident exactly when fighting the market.[/dim]\n")
    else:
        console.print("[dim]3. Market agreement: no edge_pct stored on these preds.[/dim]\n")

    # 4. Run environment (park factor)
    have_park = [r for r in band if r["park_factor"] is not None]
    if have_park:
        med = sorted(r["park_factor"] for r in have_park)[len(have_park) // 2]
        slice_table(f"4. By run environment (park factor, median {med:.3f})", [
            (f"high park ≥{med:.3f}", [r for r in have_park if r["park_factor"] >= med]),
            (f"low park <{med:.3f}", [r for r in have_park if r["park_factor"] < med]),
        ])
        console.print()
    else:
        console.print("[dim]4. Run environment: no park_factor stored.[/dim]\n")

    console.print("[dim]Discipline: a slice only 'explains' the defect if one group is "
                  "clearly calibrated while the other carries the gap. Uniformly-bad "
                  "splits mean that variable is NOT the mechanism.[/dim]\n")


@cli.command("recheck")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--since", default="2026-06-18",
              help="Post-blend start (default: market-blend go-live 2026-06-18).")
def recheck_cmd(sport: str, since: str):
    """
    One-pass post-blend re-check. Read-only. Answers the agenda we set:
      1. Post-blend calibration overall + by band (did blend+recal land honest,
         or OVER-correct into under-confidence?).
      2. Market split (did the disagreement gap close vs the pre-blend -20pp?).
      3. Recal-vs-blend overlap (is recal still doing work, or redundant now?).
      4. Offense-projection cross (do high-offense-projection favorites
         underperform their probability — even when market AGREES?).
      5. Run-environment recency (is league_runs_per_game lagging recent
         scoring — the 'juiced ball' question, tested in our own data?).
    """
    from datetime import datetime, timedelta
    from src.db.schema import (Sport, Match, Prediction, PredictionOutcome,
                               ModelVersion, MatchStatus)
    since_dt = datetime.fromisoformat(since)

    def summarize(rs):
        n = len(rs)
        if n == 0:
            return None
        pred = sum(r["top_prob"] for r in rs) / n * 100
        act = sum(1 for r in rs if r["hit"]) / n * 100
        return n, pred, act, act - pred

    from rich.table import Table

    with session_scope() as s:
        rows = s.execute(
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   Match.utc_date >= since_dt,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all()

        recs = []
        for pred, outcome, m in rows:
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            top_side = max(nn, key=nn.get)
            top_prob = nn[top_side]
            # favorite's projected runs (offense-projection cross)
            fav_proj = (pred.expected_home_score if top_side == "home"
                        else pred.expected_away_score)
            recs.append({
                "top_prob": top_prob,
                "hit": bool(outcome.top_pick_hit),
                "clv": outcome.clv,
                "fav_proj": fav_proj,
            })

        # ---- run-environment recency (item 5) ----
        # actual RPG over trailing windows vs the model's league_runs_per_game
        prod = s.execute(
            select(ModelVersion).where(
                ModelVersion.sport == Sport.MLB,
                ModelVersion.model_family == "mlb_pythag_negbin",
                ModelVersion.status == "production",
            )
        ).scalars().first()
        model_rpg = None
        if prod and prod.parameters:
            bc = prod.parameters.get("baseball_config") or {}
            model_rpg = bc.get("league_runs_per_game")

        def actual_rpg(days):
            cutoff = datetime.utcnow() - timedelta(days=days)
            played = s.execute(
                select(Match).where(Match.sport == Sport.MLB,
                                    Match.status == MatchStatus.FINISHED,
                                    Match.utc_date >= cutoff,
                                    Match.home_score.isnot(None))
            ).scalars().all()
            if not played:
                return None, 0
            tot = sum((mm.home_score or 0) + (mm.away_score or 0) for mm in played)
            return tot / len(played), len(played)

    if not recs:
        console.print(f"[yellow]No scored predictions since {since}.[/yellow]")
        return

    console.print(f"\n[bold]═══ POST-BLEND RE-CHECK (since {since}) ═══[/bold]\n")

    # ---- 1. overall + by band ----
    n, pred, act, gap = summarize(recs)
    verdict = ("UNDER-confident (over-corrected!)" if gap > 4
               else "over-confident" if gap < -4 else "calibrated")
    console.print(f"[bold]1. Calibration[/bold]  n={n}, predicted {pred:.1f}%, "
                  f"actual {act:.1f}%, gap {gap:+.1f}pp → [bold]{verdict}[/bold]")
    bands = [("50-55%", 0.50, 0.55), ("55-60%", 0.55, 0.60),
             ("60-65%", 0.60, 0.65), ("65-70%", 0.65, 0.70), ("70%+", 0.70, 1.01)]
    t1 = Table(show_header=True, header_style="bold")
    for c in ("Band", "N", "Predicted", "Actual", "Gap"):
        t1.add_column(c, justify="right" if c != "Band" else "left")
    for label, lo, hi in bands:
        sm = summarize([r for r in recs if lo <= r["top_prob"] < hi])
        if sm:
            bn, bp, ba, bg = sm
            flag = " ⚠" if bn < 10 else ""
            t1.add_row(label + flag, str(bn), f"{bp:.1f}%", f"{ba:.1f}%", f"{bg:+.1f}pp")
    console.print(t1)
    console.print("  [dim]Post-blend most picks compress to 50-60%; that's expected. "
                  "Watch for gap > +4pp (we over-corrected) or still < -4pp (under-done).[/dim]\n")

    # ---- 2. market split ----
    console.print("[bold]2. Market split — did the disagreement gap close?[/bold]")
    have = [r for r in recs if r["clv"] is not None]
    if have:
        t2 = Table(show_header=True, header_style="bold")
        for c in ("Model vs market", "N", "Predicted", "Actual", "Gap"):
            t2.add_column(c, justify="right" if c != "Model vs market" else "left")
        for label, rs in [
            ("agree (|clv|<=2pp)", [r for r in have if abs(r["clv"]) <= 0.02]),
            ("model above (>2pp)", [r for r in have if r["clv"] > 0.02]),
            ("  strongly above (>8pp)", [r for r in have if r["clv"] > 0.08]),
            ("model below (<-2pp)", [r for r in have if r["clv"] < -0.02]),
        ]:
            sm = summarize(rs)
            if sm:
                gn, gp, ga, gg = sm
                flag = " ⚠" if gn < 10 else ""
                t2.add_row(label + flag, str(gn), f"{gp:.1f}%", f"{ga:.1f}%", f"{gg:+.1f}pp")
        console.print(t2)
        console.print("  [dim]Pre-blend: agree +5pp, disagree -20pp, strongly-above -35pp. "
                      "If 'model above' is now near 0 → blend WORKED. If still deeply "
                      "negative → blend too weak (raise w).[/dim]\n")
    else:
        console.print("  [yellow]No clv stored — run evaluate.[/yellow]\n")

    # ---- 3. recal-vs-blend overlap ----
    console.print("[bold]3. Recal-vs-blend overlap[/bold]")
    band6070 = summarize([r for r in recs if 0.60 <= r["top_prob"] < 0.70])
    if band6070:
        bn, bp, ba, bg = band6070
        console.print(f"  Picks still landing in 60-70% post-blend: n={bn}, "
                      f"actual {ba:.1f}%, gap {bg:+.1f}pp")
        console.print("  [dim]With blend live, few picks should reach 60-70% via "
                      "disagreement. If this band is now ~empty or calibrated, recal "
                      "is likely redundant → candidate to turn OFF and let blend work. "
                      "If still overconfident, recal still earning its place.[/dim]\n")
    else:
        console.print("  60-70% band is ~empty post-blend → recal likely redundant, "
                      "candidate to retire (blend is doing the compression).\n")

    # ---- 4. offense-projection cross ----
    console.print("[bold]4. Offense-projection cross (the converged lead)[/bold]")
    have_proj = [r for r in recs if r["fav_proj"] is not None]
    if have_proj:
        t4 = Table(show_header=True, header_style="bold")
        for c in ("Favorite proj runs", "N", "Predicted", "Actual", "Gap"):
            t4.add_column(c, justify="right" if c != "Favorite proj runs" else "left")
        for label, rs in [
            ("high (>= 5.25)", [r for r in have_proj if r["fav_proj"] >= 5.25]),
            ("normal (< 5.25)", [r for r in have_proj if r["fav_proj"] < 5.25]),
        ]:
            sm = summarize(rs)
            if sm:
                gn, gp, ga, gg = sm
                flag = " ⚠" if gn < 10 else ""
                t4.add_row(label + flag, str(gn), f"{gp:.1f}%", f"{ga:.1f}%", f"{gg:+.1f}pp")
        console.print(t4)
        console.print("  [dim]If high-offense-projection favorites underperform while "
                      "normal ones are calibrated → real defect (model over-projects "
                      "favorite offense), separate from market disagreement. If both "
                      "calibrated → the Yankees/Dodgers misses were variance.[/dim]\n")
    else:
        console.print("  [yellow]No projected scores stored.[/yellow]\n")

    # ---- 5. run-environment recency ----
    console.print("[bold]5. Run-environment recency (the 'ball drift' question)[/bold]")
    if model_rpg is not None:
        r14, n14 = actual_rpg(14)
        r30, n30 = actual_rpg(30)
        console.print(f"  model league_runs_per_game: {model_rpg:.2f}")
        if r14:
            console.print(f"  actual RPG last 14d: {r14:.2f} (n={n14})  "
                          f"→ model {'LAGS' if r14 - model_rpg > 0.3 else 'tracks'} recent")
        if r30:
            console.print(f"  actual RPG last 30d: {r30:.2f} (n={n30})")
        console.print("  [dim]If 14d actual >> model RPG (gap > ~0.3) → model is slow to "
                      "the offensive surge; add recency weighting to league-RPG (mirror "
                      "team-form/bullpen weighting). If they track → 'ball drift' isn't "
                      "showing up as a model lag; chatter is just chatter.[/dim]\n")
    else:
        console.print("  [yellow]No league_runs_per_game in production params.[/yellow]\n")

    console.print("[bold]═══ end re-check ═══[/bold]\n")


@cli.command("offense-mechanism")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--since", default="2026-06-04",
              help="Start date (default reaches back for more sample).")
def offense_mechanism_cmd(sport: str, since: str):
    """
    Investigate WHY high-offense-projection favorites are overconfident (-9.5pp
    in the re-check). The stale RPG was ruled out mathematically (it cancels in
    win-prob). This tests the next candidate: RECENT-FORM OVERSHOOT — is the
    favorite's high projection propped up by a recent hot streak (rs_recent >>
    rs_season) that regresses? Read-only.

    Splits high-offense-projection favorites by whether the favorite's offense
    is recency-inflated (recent much hotter than season) vs steady. If the
    overconfidence concentrates in the recency-inflated group → the 0.30
    recent-weight is overshooting on hot streaks → mechanism found. If both
    groups are equally overconfident → recent-form is NOT the driver, look
    elsewhere (e.g. the RS×RA/league formula over-rewarding high-RS teams).
    """
    from datetime import datetime
    from src.db.schema import Sport, Match, Prediction, PredictionOutcome
    since_dt = datetime.fromisoformat(since)

    def summarize(rs):
        n = len(rs)
        if n == 0:
            return None
        pred = sum(r["top_prob"] for r in rs) / n * 100
        act = sum(1 for r in rs if r["hit"]) / n * 100
        return n, pred, act, act - pred

    with session_scope() as s:
        rows = s.execute(
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   Match.utc_date >= since_dt,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all()

        recs = []
        for pred, outcome, m in rows:
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            top_side = max(nn, key=nn.get)
            top_prob = nn[top_side]
            fav_proj = (pred.expected_home_score if top_side == "home"
                        else pred.expected_away_score)
            fb = pred.factor_breakdown or {}
            # the favorite's own offense: recent vs season
            rs_recent = fb.get(f"{top_side}_rs_recent")
            rs_season = fb.get(f"{top_side}_rs_season")
            recs.append({
                "top_prob": top_prob,
                "hit": bool(outcome.top_pick_hit),
                "fav_proj": fav_proj,
                "rs_recent": rs_recent,
                "rs_season": rs_season,
            })

    # high-offense-projection favorites only
    hi = [r for r in recs if r["fav_proj"] is not None and r["fav_proj"] >= 5.25]
    console.print(f"\n[bold]Offense-projection mechanism — high-proj favorites (>=5.25 runs)[/bold]")
    sm = summarize(hi)
    if not sm:
        console.print("  [yellow]No high-projection favorites in range.[/yellow]\n")
        return
    n, pred, act, gap = sm
    console.print(f"  All high-proj favorites: n={n}, predicted {pred:.1f}%, "
                  f"actual {act:.1f}%, gap {gap:+.1f}pp\n")

    have = [r for r in hi if r["rs_recent"] is not None and r["rs_season"] is not None]
    if not have:
        console.print("  [yellow]No recent/season splits stored on these.[/yellow]\n")
        return

    from rich.table import Table
    t = Table(show_header=True, header_style="bold",
              title="Split by favorite's recent-form inflation")
    for c in ("Favorite offense", "N", "Predicted", "Actual", "Gap"):
        t.add_column(c, justify="right" if c != "Favorite offense" else "left")
    # recency-inflated = recent hotter than season by >=0.5 r/g
    for label, rs in [
        ("recency-hot (recent-season >= +0.5)",
         [r for r in have if r["rs_recent"] - r["rs_season"] >= 0.5]),
        ("steady (within +/-0.5)",
         [r for r in have if abs(r["rs_recent"] - r["rs_season"]) < 0.5]),
        ("recency-cold (recent-season <= -0.5)",
         [r for r in have if r["rs_recent"] - r["rs_season"] <= -0.5]),
    ]:
        sm = summarize(rs)
        if sm:
            gn, gp, ga, gg = sm
            flag = " ⚠" if gn < 8 else ""
            t.add_row(label + flag, str(gn), f"{gp:.1f}%", f"{ga:.1f}%", f"{gg:+.1f}pp")
    console.print(t)
    console.print("  [dim]If 'recency-hot' favorites carry the overconfidence while "
                  "'steady' ones are calibrated → the 0.30 recent-weight overshoots on "
                  "hot streaks (mechanism found). If all groups are equally "
                  "overconfident → recent-form is NOT the driver; the RS×RA/league "
                  "formula itself is over-rewarding high-RS teams. (⚠ = thin, n<8.)[/dim]\n")

    # Second cut: WHAT drives the high projection? The favorite's own offense
    # (fav_RS high) or the OPPONENT's weak run-prevention (opp_RA high)?
    # projection = (fav_RS * opp_RA)/league, so a high projection can come from
    # either. This discriminates "over-projects favorite offense" from
    # "over-trusts weak opponents" (the cold-opponent-fade failure pattern).
    have2 = []
    with session_scope() as s2:
        rows2 = s2.execute(
            select(Prediction, PredictionOutcome, Match)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   Match.utc_date >= since_dt,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all()
        for pred, outcome, m in rows2:
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            top_side = max(nn, key=nn.get)
            top_prob = nn[top_side]
            fav_proj = (pred.expected_home_score if top_side == "home"
                        else pred.expected_away_score)
            if fav_proj is None or fav_proj < 5.25:
                continue
            fb = pred.factor_breakdown or {}
            opp = "away" if top_side == "home" else "home"
            fav_rs = fb.get(f"{top_side}_rs_pg")
            opp_ra = fb.get(f"{opp}_ra_pg")
            have2.append({"top_prob": top_prob, "hit": bool(outcome.top_pick_hit),
                          "fav_rs": fav_rs, "opp_ra": opp_ra})

    have2 = [r for r in have2 if r["fav_rs"] is not None and r["opp_ra"] is not None]
    if have2:
        # League-ish reference: RS/RA ~4.4/game in this environment. Classify
        # each game by which factor is the bigger contributor to the high proj.
        med_rs = sorted(r["fav_rs"] for r in have2)[len(have2) // 2]
        med_ra = sorted(r["opp_ra"] for r in have2)[len(have2) // 2]
        t2 = Table(show_header=True, header_style="bold",
                   title="Split by what drives the high projection")
        for c in ("Projection driver", "N", "Predicted", "Actual", "Gap"):
            t2.add_column(c, justify="right" if c != "Projection driver" else "left")
        for label, rs in [
            (f"fav offense high (RS>={med_rs:.1f}), opp normal",
             [r for r in have2 if r["fav_rs"] >= med_rs and r["opp_ra"] < med_ra]),
            (f"opp weak (RA>={med_ra:.1f}), fav normal",
             [r for r in have2 if r["opp_ra"] >= med_ra and r["fav_rs"] < med_rs]),
            ("both high", [r for r in have2 if r["fav_rs"] >= med_rs and r["opp_ra"] >= med_ra]),
            ("both normal", [r for r in have2 if r["fav_rs"] < med_rs and r["opp_ra"] < med_ra]),
        ]:
            sm = summarize(rs)
            if sm:
                gn, gp, ga, gg = sm
                flag = " ⚠" if gn < 8 else ""
                t2.add_row(label + flag, str(gn), f"{gp:.1f}%", f"{ga:.1f}%", f"{gg:+.1f}pp")
        console.print(t2)
        console.print("  [dim]If 'opp weak' games carry the overconfidence while 'fav "
                      "offense high' are calibrated → the model over-trusts weak-opponent "
                      "run-prevention numbers (the cold-opponent-fade failure), NOT "
                      "favorite offense. Fix = regress opponent RA harder. If 'fav "
                      "offense high' carries it → genuinely over-projecting favorite "
                      "offense. (⚠ = thin, n<8.)[/dim]\n")


@cli.command("market-alignment")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--date", default=None, help="YYYY-MM-DD (default: next scheduled slate).")
def market_alignment_cmd(sport: str, date: str):
    """
    Show, for each upcoming game, the model's pick & prob vs the de-vigged
    market — so you can see whether the model is just reprinting the book or
    keeping an independent voice. Read-only.
    """
    from datetime import datetime
    from src.db.schema import Sport, Match, Prediction, Odds, MatchStatus
    from src.walters.value import MarketSnapshot

    with session_scope() as s:
        q = (select(Prediction, Match)
             .join(Match, Match.id == Prediction.match_id)
             .where(Match.sport == Sport.MLB,
                    Match.status == MatchStatus.SCHEDULED))
        if date:
            day = datetime.fromisoformat(date)
            q = q.where(Match.utc_date >= day,
                        Match.utc_date < day.replace(hour=23, minute=59))
        rows = s.execute(q.order_by(Match.utc_date)).all()
        # only the latest prediction per match
        seen = {}
        for pred, m in rows:
            seen[m.id] = (pred, m)

        out = []
        for mid, (pred, m) in seen.items():
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            top_side = max(nn, key=nn.get)
            top_prob = nn[top_side]
            # resolve team names INSIDE the session (they're relationships)
            home_name = m.home_team.name if m.home_team else f"team{m.home_team_id}"
            away_name = m.away_team.name if m.away_team else f"team{m.away_team_id}"
            odds = list(s.execute(
                select(Odds).where(Odds.match_id == mid, Odds.market == "1X2")
            ).scalars())
            mkt_prob = None
            if odds:
                by_sel = {}
                for o in odds:
                    by_sel.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
                imp = MarketSnapshot(market="1X2", by_selection=by_sel).average_implied()
                over = sum(imp.values())
                if over > 0:
                    sel = "HOME" if top_side == "home" else "AWAY"
                    if sel in imp:
                        mkt_prob = imp[sel] / over
            out.append({"home": home_name, "away": away_name,
                        "side": top_side, "mp": top_prob, "mkp": mkt_prob})

    if not out:
        console.print("[yellow]No scheduled predictions with odds found.[/yellow]")
        return

    from rich.table import Table
    t = Table(show_header=True, header_style="bold",
              title="Model vs market — upcoming slate")
    for c in ("Matchup", "Pick", "Model", "Market", "Edge", "Note"):
        t.add_column(c, justify="right" if c not in ("Matchup", "Pick", "Note") else "left")
    n_agree = n_above = n_below = n_flip = 0
    edges = []
    for r in out:
        side, mp, mkp = r["side"], r["mp"], r["mkp"]
        pick = (r["home"] if side == "home" else r["away"])[:14]
        match = f"{r['home'][:9]} v {r['away'][:9]}"
        if mkp is None:
            t.add_row(match, pick, f"{mp*100:.0f}%", "—", "—", "no odds")
            continue
        edge = (mp - mkp) * 100
        edges.append(edge)
        note = ""
        if abs(edge) <= 2:
            note = "agree"; n_agree += 1
        elif edge > 2:
            note = "model higher"; n_above += 1
        else:
            note = "model lower"; n_below += 1
        if mkp < 0.5:
            note += " ⚑against mkt fav"; n_flip += 1
        t.add_row(match, pick, f"{mp*100:.0f}%", f"{mkp*100:.0f}%",
                  f"{edge:+.1f}pp", note)
    console.print(t)
    if edges:
        import statistics
        console.print(f"\n  n={len(edges)}  mean |edge|={statistics.mean(abs(e) for e in edges):.1f}pp  "
                      f"agree={n_agree} model-higher={n_above} model-lower={n_below}  "
                      f"picks-against-market-favorite={n_flip}")
        console.print("  [dim]If mean |edge| is tiny and picks-against-market-favorite≈0, "
                      "the model is basically reprinting the book. Healthy independence = "
                      "some real edges and a few against-favorite picks, without the wild "
                      "overconfident disagreements the blend was built to tame.[/dim]")


@cli.command("totals-check")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--since", default="2026-06-04")
def totals_check_cmd(sport: str, since: str):
    """
    Grade the model's run-total projections against actual combined runs, and
    the over/under probability against actual over/under results. Tells us
    whether projected totals run HIGH or LOW vs reality — the prerequisite for
    deciding if (and which way) the run-environment normalizer needs changing.
    Read-only.
    """
    from datetime import datetime
    from src.db.schema import Sport, Match, Prediction, MatchStatus
    since_dt = datetime.fromisoformat(since)

    with session_scope() as s:
        rows = s.execute(
            select(Prediction, Match)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   Match.status == MatchStatus.FINISHED,
                   Match.utc_date >= since_dt,
                   Match.home_score.isnot(None))
        ).all()

        proj_err = []      # projected total - actual total
        ou_graded = []     # (over_prob, actual_over) where line known
        line_is_real = 0
        line_is_default = 0
        for pred, m in rows:
            if pred.expected_home_score is None or pred.expected_away_score is None:
                continue
            proj_total = pred.expected_home_score + pred.expected_away_score
            actual_total = m.home_score + m.away_score
            proj_err.append(proj_total - actual_total)
            if pred.over_under_line is not None:
                if abs(pred.over_under_line - 8.5) < 1e-6:
                    line_is_default += 1
                else:
                    line_is_real += 1
                if pred.over_prob is not None:
                    actual_over = 1.0 if actual_total > pred.over_under_line else 0.0
                    ou_graded.append((pred.over_prob, actual_over))

    n = len(proj_err)
    if n == 0:
        console.print("[yellow]No finished games with projections in range.[/yellow]")
        return
    import statistics
    mean_err = statistics.mean(proj_err)
    med_err = sorted(proj_err)[n // 2]
    console.print(f"\n[bold]Totals check — n={n} finished games since {since}[/bold]")
    console.print(f"  Projected total − actual total:  mean {mean_err:+.2f} runs, "
                  f"median {med_err:+.2f} runs")
    if mean_err > 0.3:
        console.print("  → model projects MORE runs than actually score (totals run HIGH)")
    elif mean_err < -0.3:
        console.print("  → model projects FEWER runs than actually score (totals run LOW)")
    else:
        console.print("  → projected totals roughly track actual (within ±0.3)")

    console.print(f"\n  Over/under lines used: {line_is_real} real market lines, "
                  f"{line_is_default} default-8.5 fallback")
    if line_is_default > line_is_real and line_is_real == 0:
        console.print("  [dim](All 8.5 — these predictions predate the market-line fix; "
                      "re-run predict after syncing odds to use real lines.)[/dim]")

    if ou_graded:
        avg_over_prob = statistics.mean(p for p, _ in ou_graded) * 100
        actual_over_rate = statistics.mean(a for _, a in ou_graded) * 100
        console.print(f"\n  Over/under calibration (n={len(ou_graded)}): "
                      f"predicted over {avg_over_prob:.1f}%, actual over {actual_over_rate:.1f}%, "
                      f"gap {actual_over_rate - avg_over_prob:+.1f}pp")
    console.print("  [dim]The projected-total error is the key number: it says whether run "
                  "MAGNITUDES are biased, and which way — before we touch the run-environment "
                  "normalizer. (Win-prob is unaffected by this; totals only.)[/dim]\n")


@cli.command("capture-odds")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--competition", default="MLB")
@click.option("--season", default="2026")
def capture_odds_cmd(sport: str, competition: str, season: str):
    """
    Lightweight odds-only capture for CLV tracking. Syncs the latest MLB odds,
    then writes a DE-VIGGED CONSENSUS snapshot per upcoming game into
    odds_snapshots (append-only, timestamped). Designed to run several times a
    day (8/12/4/8 via launchd) to measure intraday line movement. Does NOT
    predict or re-sync pitchers/bullpen — it only touches odds, so it can run
    alongside the morning routine without disturbing live predictions.
    """
    from datetime import datetime
    from src.db.schema import Sport, Match, Odds, OddsSnapshot, MatchStatus
    from src.walters.value import MarketSnapshot
    from src.ingestion.service import IngestionService
    # ensure the snapshot table exists (no-op if already created; safe on a
    # live DB — create_all only adds missing tables, never drops/alters)
    from src.db.database import init_db
    init_db()

    svc = IngestionService(_adapter_for_competition(competition))
    try:
        res = svc.sync_odds_mlb(season=int(season))
        console.print(f"[dim]odds synced: {res}[/dim]")
    except Exception as e:
        console.print(f"[yellow]odds sync warning: {e} — snapshotting whatever is in DB[/yellow]")

    now = datetime.utcnow()
    written = 0
    games = 0
    with session_scope() as s:
        upcoming = list(s.execute(
            select(Match).where(Match.sport == Sport.MLB,
                                Match.status == MatchStatus.SCHEDULED)
        ).scalars())
        for m in upcoming:
            for market in ("1X2", "TOTALS"):
                odds = list(s.execute(
                    select(Odds).where(Odds.match_id == m.id, Odds.market == market)
                ).scalars())
                if not odds:
                    continue
                by_sel = {}
                line_by_sel = {}
                for o in odds:
                    by_sel.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
                    if o.line is not None:
                        line_by_sel[o.selection] = o.line
                snap = MarketSnapshot(market=market, by_selection=by_sel)
                imp = snap.average_implied()
                over = sum(imp.values())
                if over <= 0:
                    continue
                n_books = max((len(v) for v in by_sel.values()), default=0)
                wrote_any = False
                for sel, p in imp.items():
                    s.add(OddsSnapshot(
                        match_id=m.id,
                        market=market,
                        selection=sel,
                        devig_prob=p / over,
                        line=line_by_sel.get(sel),
                        n_books=n_books,
                        captured_at=now,
                        source="api_baseball",
                    ))
                    written += 1
                    wrote_any = True
                if wrote_any:
                    games += 1
    # Storage stays UTC (consistent for ordering/analysis); the console line
    # prints LOCAL time so it's readable at a glance and doesn't look like the
    # job fired on UTC.
    from datetime import timezone
    local_str = now.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    console.print(f"✓ Captured {written} snapshot rows across {games} game-markets at "
                  f"{local_str}")


@cli.command("clv-report")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--since", default="2026-06-24")
@click.option("--market", default="1X2", type=click.Choice(["1X2", "TOTALS"]))
def clv_report_cmd(sport: str, since: str, market: str):
    """
    Closing-line-value report. For each finished game with multiple odds
    snapshots, shows how the consensus line MOVED from first capture to last,
    and — for 1X2 — whether it moved TOWARD or AWAY from the model's morning
    pick. The toward/away tally is the key signal: if the market reliably moves
    toward the model's edge, that's evidence of real (early) edge; if it moves
    away, the model is the one that's wrong. Read-only.

    Needs snapshots to have accrued across multiple captures per game, so this
    is meaningful only after capture-odds has been running for a while. Flags
    games with only one snapshot (can't measure movement).
    """
    from datetime import datetime
    from src.db.schema import (Sport, Match, Prediction, OddsSnapshot,
                               MatchStatus)
    since_dt = datetime.fromisoformat(since)

    with session_scope() as s:
        finished = list(s.execute(
            select(Match).where(Match.sport == Sport.MLB,
                                Match.status == MatchStatus.FINISHED,
                                Match.utc_date >= since_dt,
                                Match.home_score.isnot(None))
        ).scalars())

        rows = []
        single_snap = 0
        no_snap = 0
        toward = away = flat = 0
        moves = []
        bucket_tally = {"aligned": {"toward": 0, "away": 0, "flat": 0},
                        "disagree": {"toward": 0, "away": 0, "flat": 0}}
        bucket_moves = {"aligned": [], "disagree": []}
        for m in finished:
            snaps = list(s.execute(
                select(OddsSnapshot).where(OddsSnapshot.match_id == m.id,
                                           OddsSnapshot.market == market)
                .order_by(OddsSnapshot.captured_at.asc())
            ).scalars())
            if not snaps:
                no_snap += 1
                continue
            # group by capture time
            by_time = {}
            for sn in snaps:
                by_time.setdefault(sn.captured_at, {})[sn.selection] = sn
            times = sorted(by_time.keys())
            if len(times) < 2:
                single_snap += 1
                continue
            first, last = by_time[times[0]], by_time[times[-1]]

            home_name = m.home_team.name if m.home_team else f"team{m.home_team_id}"
            away_name = m.away_team.name if m.away_team else f"team{m.away_team_id}"

            if market == "1X2":
                # model's morning pick
                pred = s.execute(
                    select(Prediction).where(Prediction.match_id == m.id)
                    .order_by(Prediction.computed_at.asc())
                ).scalars().first()
                if not pred:
                    continue
                probs = {"HOME": pred.home_win_prob, "AWAY": pred.away_win_prob}
                nn = {k: v for k, v in probs.items() if v is not None}
                if not nn:
                    continue
                pick = max(nn, key=nn.get)
                if pick not in first or pick not in last:
                    continue
                p0 = first[pick].devig_prob
                p1 = last[pick].devig_prob
                move = (p1 - p0) * 100  # market move on the model's pick, pp
                moves.append(move)

                # aligned vs disagreement: did the model pick the market's
                # favorite (p0 >= 50%, aligned) or its underdog (p0 < 50%,
                # disagreement)? Disagreements are the only place edge could
                # live — and the interim report hinted they're where the
                # anti-predictiveness concentrates. Split CLV by bucket.
                is_disagree = p0 < 0.50
                bucket = "disagree" if is_disagree else "aligned"

                # toward = market came up toward the model's side
                if move > 0.5:
                    toward += 1; direction = "toward"
                    bucket_tally[bucket]["toward"] += 1
                elif move < -0.5:
                    away += 1; direction = "away"
                    bucket_tally[bucket]["away"] += 1
                else:
                    flat += 1; direction = "flat"
                    bucket_tally[bucket]["flat"] += 1
                bucket_moves[bucket].append(move)
                won = ((pick == "HOME" and m.home_score > m.away_score) or
                       (pick == "AWAY" and m.away_score > m.home_score))
                rows.append((f"{home_name[:9]} v {away_name[:9]}",
                             pick, f"{p0*100:.0f}%", f"{p1*100:.0f}%",
                             f"{move:+.1f}", direction,
                             "disagree" if is_disagree else "aligned",
                             "W" if won else "L"))

    if market == "1X2":
        from rich.table import Table
        t = Table(show_header=True, header_style="bold",
                  title=f"CLV — market move on model's pick (since {since})")
        for c in ("Matchup", "Pick", "First", "Last", "Move pp", "Dir", "Bucket", "Result"):
            t.add_column(c, justify="right" if c not in ("Matchup", "Pick", "Dir", "Bucket", "Result") else "left")
        for r in rows:
            t.add_row(*r)
        if rows:
            console.print(t)
        console.print(f"\n  games with movement measured: {len(rows)}  "
                      f"(toward model {toward}, away {away}, flat {flat})")
        if moves:
            import statistics
            console.print(f"  mean move on model's pick: {statistics.mean(moves):+.2f}pp")
            console.print("  [dim]TOWARD = market drifted to the model's side after capture "
                          "(model was early → evidence of real edge). AWAY = market moved "
                          "against the model (model likely wrong). This needs sample — read "
                          "the toward/away balance, not any single game.[/dim]")

        # --- aligned vs disagreement split ---
        console.print("\n  [bold]CLV split — aligned vs disagreement picks[/bold]")
        console.print("  [dim]aligned = model picked the market's favorite; disagree = model "
                      "picked the market's underdog. Disagreements are the only place edge "
                      "could live. If disagree shows AWAY >> toward and negative mean, the "
                      "model's fights with the market are anti-predictive (confirms the blend's "
                      "premise). Aligned CLV ≈ 0 is expected (agreeing with the market isn't "
                      "edge either).[/dim]")
        for bucket in ("aligned", "disagree"):
            bt = bucket_tally[bucket]
            bm = bucket_moves[bucket]
            n = bt["toward"] + bt["away"] + bt["flat"]
            if n == 0:
                console.print(f"    {bucket:9s}: no games")
                continue
            import statistics as _st
            mean_m = _st.mean(bm) if bm else 0.0
            # a crude read on which way this bucket points
            tag = ""
            if bucket == "disagree":
                if bt["away"] > bt["toward"] and mean_m < -0.2:
                    tag = " [yellow]← anti-predictive (as hypothesized)[/yellow]"
                elif bt["toward"] > bt["away"] and mean_m > 0.2:
                    tag = " [green]← toward-model (would be real edge)[/green]"
            console.print(f"    {bucket:9s}: n={n:<3d} toward {bt['toward']}, "
                          f"away {bt['away']}, flat {bt['flat']}  |  "
                          f"mean {mean_m:+.2f}pp{tag}")
        console.print("  [dim]Read the disagree bucket carefully — that's the whole edge "
                      "question. Even a clean split here is one window; confirm at the next "
                      "review before drawing conclusions.[/dim]")

        console.print(f"  [dim]skipped: {single_snap} single-snapshot games (no movement "
                      f"measurable), {no_snap} with no snapshots.[/dim]\n")
    else:
        console.print("[yellow]TOTALS CLV view not built yet — start with 1X2.[/yellow]")


@cli.command("sync-umpires")
@click.option("--competition", "competition_code", default="MLB")
@click.option("--season", default="2026")
@click.option("--limit", default=2000, help="Max finished games to process.")
@click.option("--backfill/--recent", default=True,
              help="backfill: all finished games missing an umpire row. "
                   "recent: only the last ~3 days.")
@click.option("--today", is_flag=True, default=False,
              help="Pre-game mode: capture plate umpire for TODAY's scheduled "
                   "games (posts a few hours before first pitch). Writes the "
                   "umpire only; run environment fills in later post-game.")
def sync_umpires_cmd(competition_code, season, limit, backfill, today):
    """
    TRACKING-ONLY: record the plate umpire + run/K/BB environment for finished
    games into the umpire_games table. Append/upsert by gamePk — re-running is
    safe. Does NOT touch predictions. Backfill seeds the season; --recent tops
    up the last few days; --today captures pre-game umpires for the current
    slate (partial rows — umpire now, environment when the game finishes).
    """
    from datetime import timedelta, timezone
    from src.db.schema import UmpireGame, Competition
    from src.db.database import init_db
    init_db()  # ensure umpire_games exists (new table; create_all adds it, leaves others)
    adapter = get_adapter(sport="baseball")

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            console.print(f"[red]Competition {competition_code} not in DB.[/red]")
            return

        if today:
            # pre-game: today's SCHEDULED games; refresh rows that still lack a
            # posted umpire (don't skip them — that's the whole point).
            local_today = datetime.now(timezone.utc).astimezone().date()
            all_sched = s.execute(select(Match).where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.SCHEDULED,
            )).scalars()
            matches = [m for m in all_sched if m.utc_date and
                       m.utc_date.replace(tzinfo=timezone.utc).astimezone().date() == local_today]
            # rows that already have a NON-NULL umpire → skip; null/absent → retry
            have_ump = set(s.execute(
                select(UmpireGame.source_game_id).where(UmpireGame.plate_umpire.isnot(None))
            ).scalars())
        else:
            q = select(Match).where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status == MatchStatus.FINISHED,
            )
            matches = list(s.execute(q).scalars())
            have_ump = set(s.execute(select(UmpireGame.source_game_id)).scalars())

        if not backfill and not today:
            cutoff = datetime.utcnow() - timedelta(days=3)
            matches = [m for m in matches if m.utc_date and m.utc_date >= cutoff]

        targets = []
        for m in matches:
            sid = (m.external_ids or {}).get(adapter.source_name)
            if not sid:
                continue
            if str(sid) in have_ump:
                continue
            targets.append((m, sid))
        targets = targets[:limit]

    if not targets:
        msg = ("No scheduled games today need an umpire yet." if today
               else "No finished games need umpire capture (all present or no source IDs).")
        console.print(f"[yellow]{msg}[/yellow]")
        return

    console.print(f"[cyan]{'Pre-game umpire check' if today else 'Capturing umpire/environment'} "
                  f"for {len(targets)} games (≈{len(targets)} API calls).[/cyan]")
    written = 0
    for m, sid in targets:
        try:
            env = adapter.get_game_umpire_environment(sid)
        except Exception as e:
            console.print(f"[red]  ✗ game {sid}: {e}[/red]")
            continue
        if not env:
            continue
        with session_scope() as s2:
            # guard against a race / duplicate
            exists = s2.execute(
                select(UmpireGame).where(UmpireGame.source_game_id == str(sid))
            ).scalar_one_or_none()

            if today:
                # pre-game: only write when an umpire is actually posted.
                ump = env.get("plate_umpire") if env else None
                if not ump:
                    continue  # not posted yet — leave for a later run
                if exists:
                    if exists.plate_umpire is None:
                        exists.plate_umpire = ump  # fill in the now-posted umpire
                        written += 1
                    continue
                s2.add(UmpireGame(
                    match_id=m.id, source_game_id=str(sid),
                    game_date=m.utc_date or datetime.utcnow(),
                    plate_umpire=ump,
                    home_team=env.get("home_team"), away_team=env.get("away_team"),
                    # run environment left null — fills in post-game
                ))
                written += 1
                continue

            if exists:
                continue
            s2.add(UmpireGame(
                match_id=m.id, source_game_id=str(sid),
                game_date=m.utc_date or datetime.utcnow(),
                plate_umpire=env.get("plate_umpire"),
                home_team=env.get("home_team"), away_team=env.get("away_team"),
                total_runs=env.get("total_runs"), strikeouts=env.get("strikeouts"),
                walks=env.get("walks"), home_runs=env.get("home_runs"),
            ))
        written += 1
        if written % 25 == 0:
            console.print(f"[dim]  ...{written} captured[/dim]")

    if today:
        console.print(f"[green]✓ Pre-game umpires posted for {written} games "
                      f"(the rest not announced yet — re-run closer to first pitch, "
                      f"or the post-game sync will fill them).[/green]")
    else:
        console.print(f"[green]✓ Captured umpire/environment for {written} games "
                      f"(skipped {len(targets) - written} with no data).[/green]")


@cli.command("umpire-report")
@click.option("--min-games", default=1, help="Only show umpires with ≥ this many games.")
def umpire_report_cmd(min_games):
    """
    Per-umpire run environment from tracked data. ALWAYS shows sample size:
    a plate ump works ~25-30 games/season, so small-n figures are NOISE. This
    is a measurement readout, not a betting signal — do not fade an umpire on a
    handful of games.
    """
    from collections import defaultdict
    from src.db.schema import UmpireGame
    from rich.table import Table

    with session_scope() as s:
        rows = list(s.execute(select(UmpireGame)).scalars())

    if not rows:
        console.print("[yellow]No umpire data yet. Run sync-umpires first.[/yellow]")
        return

    by_ump = defaultdict(list)
    for r in rows:
        if r.plate_umpire:
            by_ump[r.plate_umpire].append(r)

    agg = []
    for ump, gs in by_ump.items():
        n = len(gs)
        if n < min_games:
            continue
        runs = [g.total_runs for g in gs if g.total_runs is not None]
        ks = [g.strikeouts for g in gs if g.strikeouts is not None]
        bbs = [g.walks for g in gs if g.walks is not None]
        agg.append((ump, n,
                    sum(runs) / len(runs) if runs else None,
                    sum(ks) / len(ks) if ks else None,
                    sum(bbs) / len(bbs) if bbs else None))
    agg.sort(key=lambda x: (x[2] is None, -(x[2] or 0)))

    league_runs = [g.total_runs for g in rows if g.total_runs is not None]
    lg_avg = sum(league_runs) / len(league_runs) if league_runs else None

    t = Table(title=f"Umpire run environment  ({len(rows)} games tracked"
                    + (f", league avg {lg_avg:.2f} R/G" if lg_avg else "") + ")",
              show_header=True, header_style="bold")
    for c, j in (("Umpire", "left"), ("n", "right"), ("R/G", "right"),
                 ("K/G", "right"), ("BB/G", "right"), ("vs lg", "right"), ("", "left")):
        t.add_column(c, justify=j)
    for ump, n, rpg, kpg, bbpg in agg:
        diff = (rpg - lg_avg) if (rpg is not None and lg_avg) else None
        noise = "[dim]noise (small n)[/dim]" if n < 15 else ""
        t.add_row(ump[:24], str(n),
                  f"{rpg:.2f}" if rpg is not None else "—",
                  f"{kpg:.1f}" if kpg is not None else "—",
                  f"{bbpg:.1f}" if bbpg is not None else "—",
                  f"{diff:+.2f}" if diff is not None else "—", noise)
    console.print(t)
    console.print("[dim]Reminder: ump tendency needs large n to mean anything. "
                  "This is tracked data for later validation, not a bet signal.[/dim]")


@cli.command("sync-appearances")
@click.option("--competition", "competition_code", default="MLB")
@click.option("--season", default="2026")
@click.option("--limit", default=2000)
@click.option("--backfill/--recent", default=True,
              help="backfill: all finished games missing appearance rows. "
                   "recent: only last ~5 days (enough for availability windows).")
@click.option("--refresh", is_flag=True, default=False,
              help="Re-capture games that ALREADY have rows (deletes + rewrites) "
                   "— needed to populate newly-added effectiveness fields on "
                   "historical games.")
def sync_appearances_cmd(competition_code, season, limit, backfill, refresh):
    """
    TRACKING-ONLY: record per-pitcher appearances (pitches/outs/starter) for
    finished games into pitcher_appearances. The RAW for deriving bullpen
    availability + starter workload. Append/upsert by (game, pitcher). Does NOT
    feed the model.
    """
    from datetime import timedelta
    from src.db.schema import PitcherAppearance, Competition
    from src.db.database import init_db
    init_db()
    adapter = get_adapter(sport="baseball")

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            console.print(f"[red]Competition {competition_code} not in DB.[/red]")
            return
        matches = list(s.execute(
            select(Match).where(Match.competition_id == comp.id,
                                Match.season == season,
                                Match.status == MatchStatus.FINISHED)
        ).scalars())
        have_games = set(s.execute(
            select(PitcherAppearance.source_game_id).distinct()
        ).scalars())

        if not backfill:
            cutoff = datetime.utcnow() - timedelta(days=5)
            matches = [m for m in matches if m.utc_date and m.utc_date >= cutoff]

        targets = []
        for m in matches:
            sid = (m.external_ids or {}).get(adapter.source_name)
            if not sid:
                continue
            if sid in have_games and not refresh:
                continue  # already captured; skip unless refreshing
            targets.append((m, sid))
        targets = targets[:limit]

        # in refresh mode, delete existing rows for the target games so the
        # re-capture rewrites them with the full (effectiveness) field set.
        if refresh and targets:
            target_sids = [sid for _, sid in targets]
            existing = s.execute(
                select(PitcherAppearance).where(
                    PitcherAppearance.source_game_id.in_(target_sids))
            ).scalars().all()
            for row in existing:
                s.delete(row)
            s.flush()

    if not targets:
        console.print("[yellow]No finished games need appearance capture.[/yellow]")
        return

    console.print(f"[cyan]Capturing appearances for {len(targets)} games "
                  f"(≈{len(targets)} API calls).[/cyan]")
    games_done = rows_written = 0
    for m, sid in targets:
        try:
            apps = adapter.get_game_pitcher_appearances(sid)
        except Exception as e:
            console.print(f"[red]  ✗ game {sid}: {e}[/red]")
            continue
        if not apps:
            continue
        with session_scope() as s2:
            for a in apps:
                if not a.get("pitcher_id"):
                    continue
                exists = s2.execute(
                    select(PitcherAppearance).where(
                        PitcherAppearance.source_game_id == str(sid),
                        PitcherAppearance.pitcher_id == a["pitcher_id"])
                ).scalar_one_or_none()
                if exists:
                    continue
                s2.add(PitcherAppearance(
                    match_id=m.id, source_game_id=str(sid),
                    game_date=m.utc_date or datetime.utcnow(),
                    team_source_id=a.get("team_source_id"),
                    pitcher_id=a.get("pitcher_id"), pitcher_name=a.get("pitcher_name"),
                    pitches=a.get("pitches"), outs=a.get("outs"),
                    is_starter=bool(a.get("is_starter")),
                    earned_runs=a.get("earned_runs"), hits_allowed=a.get("hits_allowed"),
                    walks_allowed=a.get("walks_allowed"), strikeouts=a.get("strikeouts"),
                ))
                rows_written += 1
        games_done += 1
        if games_done % 25 == 0:
            console.print(f"[dim]  ...{games_done} games, {rows_written} appearances[/dim]")

    console.print(f"[green]✓ Captured {rows_written} appearances across "
                  f"{games_done} games.[/green]")


@cli.command("bullpen-availability")
@click.option("--date", default=None, help="As-of date YYYY-MM-DD (default: today).")
@click.option("--days", default=3, help="Lookback window for 'recent usage'.")
@click.option("--heavy", default=30, help="Pitches in one game that count as a heavy outing.")
def bullpen_availability_cmd(date, days, heavy):
    """
    Per-team bullpen usage in the last N days, derived from pitcher_appearances.
    Shows relievers used, those on back-to-back, and heavy-outing arms — the
    'who's likely gassed' read. ALWAYS a derived view over raw appearances;
    nothing is precomputed or fed to the model. Tracking/diagnostic only.
    """
    from datetime import timedelta, timezone
    from collections import defaultdict
    from src.db.schema import PitcherAppearance, Team
    from rich.table import Table

    if date:
        asof = datetime.fromisoformat(date)
    else:
        asof = datetime.now(timezone.utc)
    start = asof - timedelta(days=days)

    with session_scope() as s:
        rows = list(s.execute(
            select(PitcherAppearance).where(
                PitcherAppearance.game_date >= start,
                PitcherAppearance.game_date <= asof,
                PitcherAppearance.is_starter == False)  # relievers only
        ).scalars())
        # map team_source_id → readable name if we can
        team_names = {}
        for t in s.execute(select(Team)).scalars():
            sid = (t.external_ids or {}).get("mlb_stats_api")
            if sid:
                team_names[str(sid)] = t.name

    if not rows:
        console.print("[yellow]No reliever appearances in window. "
                      "Run sync-appearances first.[/yellow]")
        return

    by_team = defaultdict(list)
    for r in rows:
        by_team[r.team_source_id].append(r)

    t = Table(title=f"Bullpen usage, last {days}d as of {asof.date()} "
                    f"(heavy ≥ {heavy} pitches)", show_header=True, header_style="bold")
    for c, j in (("Team", "left"), ("relievers used", "right"),
                 ("appearances", "right"), ("heavy outings", "right"),
                 ("back-to-back arms", "right")):
        t.add_column(c, justify=j)

    summary = []
    for team_sid, apps in by_team.items():
        pitchers = defaultdict(list)
        for a in apps:
            pitchers[a.pitcher_id].append(a)
        n_relievers = len(pitchers)
        n_apps = len(apps)
        heavy_arms = sum(1 for a in apps if (a.pitches or 0) >= heavy)
        b2b = 0
        for pid, ap in pitchers.items():
            dates = sorted({a.game_date.date() for a in ap})
            for i in range(1, len(dates)):
                if (dates[i] - dates[i-1]).days == 1:
                    b2b += 1
                    break
        name = team_names.get(team_sid, team_sid or "?")
        summary.append((name, n_relievers, n_apps, heavy_arms, b2b))
    summary.sort(key=lambda x: -x[2])  # busiest pens first
    for name, nr, na, hv, b2b in summary:
        t.add_row(name[:22], str(nr), str(na), str(hv), str(b2b))
    console.print(t)
    console.print("[dim]Derived from raw appearances; 'gassed' is a judgment over "
                  "these numbers, not a stored flag. Tracking only — not fed to the "
                  "model until validated.[/dim]")


@cli.command("capture-weather")
@click.option("--date", default=None, help="YYYY-MM-DD local (default: today).")
def capture_weather_cmd(date):
    """
    TRACKING-ONLY: snapshot weather near first pitch for a day's scheduled games
    into game_weather (append-only). Reuses the existing Open-Meteo client (the
    same one that currently only powers the display panel). Does NOT feed the
    model. Run it close to first pitch for the freshest conditions; multiple
    runs in a day just add snapshots (we keep the frozen record).

    NOTE: weather is currently DISPLAY-ONLY in the app — this is the instrument
    that lets us later test whether it should drive the totals projection.
    """
    from datetime import timezone
    from src.db.schema import GameWeather
    from src.db.database import init_db
    from src.web.weather import fetch_weather, lookup_venue
    init_db()  # ensure game_weather exists

    if date:
        target = datetime.fromisoformat(date).date()
    else:
        target = datetime.now(timezone.utc).astimezone().date()

    captured = skipped_indoor = skipped_novenue = 0
    with session_scope() as s:
        rows = list(s.execute(
            select(Match).where(Match.sport == Sport.MLB,
                                Match.status == MatchStatus.SCHEDULED)
        ).scalars())
        todays = []
        for m in rows:
            if not m.utc_date:
                continue
            local_d = m.utc_date.replace(tzinfo=timezone.utc).astimezone().date()
            if local_d == target:
                todays.append(m)

        for m in todays:
            venue_info = lookup_venue(m.venue)
            if venue_info is None:
                skipped_novenue += 1
                continue
            _, _, is_indoor = venue_info
            roof_state = "indoor(roof)" if is_indoor else "outdoor"
            wx = None
            if not is_indoor:
                try:
                    wx = fetch_weather(m.venue, m.utc_date)
                except Exception:
                    wx = None
            sid = (m.external_ids or {}).get("mlb_stats_api") \
                or (m.external_ids or {}).get("api_baseball")
            s.add(GameWeather(
                match_id=m.id, source_game_id=str(sid) if sid else None,
                game_date=m.utc_date, venue=m.venue, roof_state=roof_state,
                temperature_f=(wx or {}).get("temperature_f"),
                wind_mph=(wx or {}).get("wind_mph"),
                wind_dir_deg=(wx or {}).get("wind_dir_deg"),
                precipitation_in=(wx or {}).get("precipitation_in"),
                condition=(wx or {}).get("condition")
                          or ("indoor" if is_indoor else None),
            ))
            captured += 1
            if is_indoor:
                skipped_indoor += 1

    console.print(f"[green]✓ Weather snapshots: {captured} games "
                  f"({skipped_indoor} indoor recorded as roofed, "
                  f"{skipped_novenue} skipped: venue not in coord map).[/green]")


@cli.command("backfill-weather")
@click.option("--competition", "competition_code", default="MLB")
@click.option("--season", required=True, help="e.g. 2025")
@click.option("--limit", default=3000)
def backfill_weather_cmd(competition_code, season, limit):
    """
    HISTORICAL weather backfill for a past season via Open-Meteo's archive
    endpoint. Walks finished games, pulls reanalysis weather at first pitch,
    writes game_weather rows (skips games that already have one). Rate-limited
    by the archive API — a full season is slow but one-time. Does NOT feed the
    model; this is the tracking backbone for making weather a trainable signal.
    """
    import time
    from src.db.schema import GameWeather, Competition
    from src.db.database import init_db
    from src.web.weather import fetch_weather_historical, lookup_venue
    init_db()

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            console.print(f"[red]Competition {competition_code} not in DB.[/red]")
            return
        matches = list(s.execute(
            select(Match).where(Match.competition_id == comp.id,
                                Match.season == season,
                                Match.status == MatchStatus.FINISHED)
            .order_by(Match.utc_date)
        ).scalars())
        have = set(s.execute(
            select(GameWeather.match_id).where(GameWeather.match_id.isnot(None))
        ).scalars())
        targets = [m for m in matches if m.id not in have][:limit]

    if not targets:
        console.print("[yellow]No finished games need weather backfill "
                      "(all present or none for that season).[/yellow]")
        return

    console.print(f"[cyan]Backfilling weather for {len(targets)} games "
                  f"(archive API, rate-limited — this is slow).[/cyan]")
    captured = indoor = novenue = failed = 0
    for i, m in enumerate(targets, 1):
        venue_info = lookup_venue(m.venue)
        if venue_info is None:
            novenue += 1
            continue
        _, _, is_indoor = venue_info
        roof_state = "indoor(roof)" if is_indoor else "outdoor"
        wx = None
        if not is_indoor:
            try:
                wx = fetch_weather_historical(m.venue, m.utc_date)
            except Exception:
                wx = None
            if wx is None:
                failed += 1
            time.sleep(0.4)  # be gentle with the free archive endpoint
        sid = (m.external_ids or {}).get("mlb_stats_api")
        with session_scope() as s2:
            s2.add(GameWeather(
                match_id=m.id, source_game_id=str(sid) if sid else None,
                game_date=m.utc_date, venue=m.venue, roof_state=roof_state,
                temperature_f=(wx or {}).get("temperature_f"),
                wind_mph=(wx or {}).get("wind_mph"),
                wind_dir_deg=(wx or {}).get("wind_dir_deg"),
                precipitation_in=(wx or {}).get("precipitation_in"),
                condition=(wx or {}).get("condition")
                          or ("indoor" if is_indoor else None),
            ))
        captured += 1
        if is_indoor:
            indoor += 1
        if i % 100 == 0:
            console.print(f"[dim]  ...{i}/{len(targets)} ({captured} written, "
                          f"{failed} weather-fetch failures)[/dim]")

    console.print(f"[green]✓ Weather backfilled: {captured} games written "
                  f"({indoor} indoor, {novenue} unknown venue, "
                  f"{failed} fetch failures left null).[/green]")


@cli.command("bullpen-diagnostic")
@click.option("--lookback", default=3, help="Days before game to assess bullpen state.")
@click.option("--heavy", default=30, help="Pitches counting as a heavy outing.")
def bullpen_diagnostic_cmd(lookback, heavy):
    """
    Test the hypothesis: are favorites with DEPLETED bullpens overrated by the
    model? Compares predicted win-prob vs ACTUAL win-rate for favorites,
    bucketed by their bullpen workload in the prior N days. A negative 'gap'
    (actual < predicted) that is BIGGER for depleted bullpens = evidence the
    model overrates tired-pen favorites. Read-only diagnostic.
    """
    from src.walters.bullpen_diagnostic import run_bullpen_diagnostic
    from rich.table import Table

    res = run_bullpen_diagnostic(lookback_days=lookback, heavy_pitches=heavy)
    if not res:
        console.print("[yellow]No data. Need graded predictions + appearances "
                      "(run evaluate and sync-appearances --backfill first).[/yellow]")
        return

    console.print(f"\n[bold]Bullpen-depletion diagnostic[/bold]  "
                  f"({res['total']} favorite-predictions, lookback {lookback}d, "
                  f"heavy ≥ {heavy}p, median depletion score = {res['median_depletion']})")
    console.print("[dim]gap = actual win-rate − mean predicted prob. Negative = "
                  "favorites won LESS than the model said. The hypothesis predicts "
                  "a MORE negative gap for depleted bullpens.[/dim]\n")

    t = Table(title="Two-way split (median)", show_header=True, header_style="bold")
    for c in ("Bucket", "n", "predicted", "actual", "gap"):
        t.add_column(c, justify="left" if c == "Bucket" else "right")
    for k in ("rested (≤ median)", "depleted (> median)"):
        b = res["two_way"][k]
        if not b:
            continue
        color = "red" if b["gap"] < -0.03 else ("green" if b["gap"] > 0.03 else "white")
        t.add_row(k, str(b["n"]), f"{b['predicted']*100:.1f}%",
                  f"{b['actual']*100:.1f}%", f"[{color}]{b['gap']*100:+.1f}pp[/{color}]")
    console.print(t)

    t2 = Table(title="Three-way split (tertiles)", show_header=True, header_style="bold")
    for c in ("Bucket", "n", "predicted", "actual", "gap"):
        t2.add_column(c, justify="left" if c == "Bucket" else "right")
    for k in ("low", "mid", "high"):
        b = res["three_way"][k]
        if not b:
            continue
        color = "red" if b["gap"] < -0.03 else ("green" if b["gap"] > 0.03 else "white")
        t2.add_row(f"{k} depletion", str(b["n"]), f"{b['predicted']*100:.1f}%",
                   f"{b['actual']*100:.1f}%", f"[{color}]{b['gap']*100:+.1f}pp[/{color}]")
    console.print(t2)

    # honest interpretation
    tw = res["two_way"]
    rested = tw.get("rested (≤ median)")
    depleted = tw.get("depleted (> median)")
    console.print("")
    if rested and depleted:
        diff = depleted["gap"] - rested["gap"]
        console.print(f"[bold]Depleted-minus-rested gap difference: {diff*100:+.1f}pp[/bold]")
        if diff < -0.04 and depleted["n"] >= 60:
            console.print("[yellow]→ Directionally supports the hypothesis: depleted "
                          "favorites underperform more. BUT check n and remember this "
                          "is one cut of historical data — confirm it holds as sample "
                          "grows before building a feature.[/yellow]")
        elif abs(diff) <= 0.04:
            console.print("[dim]→ No meaningful difference. The hypothesis is NOT "
                          "supported by current data — depleted and rested favorites "
                          "miss their predicted rate about equally. Likely noise, not "
                          "a feature.[/dim]")
        else:
            console.print("[dim]→ Difference is in the UNEXPECTED direction or too "
                          "small/noisy to act on. Not support for the hypothesis.[/dim]")
    console.print("[dim]Caveat: small per-bucket n makes any single number noisy; "
                  "multiple-cut fishing inflates false positives. Treat as a screen, "
                  "not proof.[/dim]\n")


@cli.command("team-streaks")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--season", default="2026")
@click.option("--sort", type=click.Choice(["avg", "longest", "current", "winpct"]),
              default="avg", help="Sort KPI (default: avg winning-streak length).")
def team_streaks_cmd(sport, season, sort):
    """
    Team-level streak KPIs (tracking/profile only — NOT a prediction input).
    Average winning-streak length per club, plus longest streak, current
    streak, and win%. Derived on demand from finished games.
    """
    from src.db.schema import Sport, Team
    from src.walters.team_streaks import team_streak_kpis
    from rich.table import Table

    with session_scope() as s:
        teams = list(s.execute(
            select(Team).where(Team.sport == Sport.MLB)
        ).scalars())
        rows = []
        for t in teams:
            k = team_streak_kpis(s, t.id, season=season)
            if k["games"] == 0:
                continue
            rows.append((t.name, k))

    if not rows:
        console.print("[yellow]No finished games found for this season.[/yellow]")
        return

    keymap = {"avg": "avg_win_streak_len", "longest": "longest_win_streak",
              "current": "current_streak", "winpct": "win_pct"}
    sk = keymap[sort]
    rows.sort(key=lambda r: (r[1].get(sk) is None, -(r[1].get(sk) or 0)))

    t = Table(title=f"Team streak KPIs — {season} (sorted by {sort})",
              show_header=True, header_style="bold")
    for c, j in (("Team", "left"), ("G", "right"), ("Win%", "right"),
                 ("Avg win streak", "right"), ("Longest", "right"),
                 ("Current", "right")):
        t.add_column(c, justify=j)
    for name, k in rows:
        cur = k["current_streak"]
        cur_s = f"[green]W{cur}[/green]" if cur > 0 else (f"[red]L{-cur}[/red]" if cur < 0 else "—")
        avg = k["avg_win_streak_len"]
        t.add_row(name[:24], str(k["games"]),
                  f"{k['win_pct']*100:.0f}%" if k["win_pct"] is not None else "—",
                  f"{avg:.2f}" if avg is not None else "—",
                  str(k["longest_win_streak"]), cur_s)
    console.print(t)
    console.print("[dim]KPI only — team-profile stat, not fed into predictions.[/dim]")


@cli.command("signal-residuals")
def signal_residuals_cmd():
    """
    Stage 1: does any TRACKED signal predict the model's residuals (misses)
    after controlling for what the model already knows? For each signal, shows
    mean residual per bucket (residual = actual − predicted; negative = the
    model overrated that bucket). A signal only carries NEW information if the
    residual VARIES across buckets by more than noise. Read-only diagnostic on
    historical data — a signal passing here is a Stage-2 candidate, not proof.
    """
    from src.walters.signal_residuals import run_signal_residuals
    from rich.table import Table

    res = run_signal_residuals()
    if not res:
        console.print("[yellow]No data. Need graded predictions + tracked signals.[/yellow]")
        return

    console.print("\n[bold]Stage 1 — signal residual analysis[/bold]")
    console.print("[dim]residual = actual win (1/0) − model predicted prob, on the model's "
                  "pick. Mean ≈ 0 per bucket = model already accounts for it (redundant). "
                  "Residual that VARIES across buckets (beyond ±SE) = signal carries info "
                  "the model lacks → Stage 2 candidate. Most signals SHOULD be flat.[/dim]\n")

    for name, data in res.items():
        rows = data["rows"]
        spread = data["spread"]
        t = Table(title=name, show_header=True, header_style="bold")
        for c in ("Bucket", "n", "mean residual", "± SE"):
            t.add_column(c, justify="left" if c == "Bucket" else "right")
        for label, n, m, se in rows:
            if m is None:
                t.add_row(label, str(n), "—", "—")
                continue
            color = ""
            if se and abs(m) > 2 * se:
                color = "yellow"  # bucket residual distinguishable from 0
            mtxt = f"[{color}]{m*100:+.1f}pp[/{color}]" if color else f"{m*100:+.1f}pp"
            t.add_row(label, str(n), mtxt, f"{se*100:.1f}pp" if se else "—")
        console.print(t)
        if spread is not None:
            verdict = ""
            if spread >= 0.06:
                verdict = "[yellow]← buckets differ by ≥6pp — POSSIBLE signal, take to Stage 2[/yellow]"
            elif spread >= 0.03:
                verdict = "[dim]← modest spread (3-6pp), borderline — watch[/dim]"
            else:
                verdict = "[dim]← flat (<3pp spread) — redundant with model, no new info[/dim]"
            console.print(f"  spread across well-sampled buckets: {spread*100:.1f}pp {verdict}\n")
        else:
            console.print("  [dim](insufficient sample for a spread verdict)[/dim]\n")

    console.print("[dim]Reminder: passing Stage 1 = has calibration information, NOT proven "
                  "market edge (market may already price it). Confirm any candidate out-of-"
                  "sample in Stage 2 before touching the model.[/dim]\n")


@cli.command("miss-analysis")
@click.option("--min-n", default=20, help="Only flag buckets with at least this many games.")
def miss_analysis_cmd(min_n):
    """
    Exploratory: bucket ALL graded predictions across many categories and show
    actual vs predicted win rate per bucket. A real 'miss category' is one where
    actual materially trails predicted BEYOND noise (gap < -2×SE), ideally with a
    gradient across an ordered dimension. Controls for base rates by comparing to
    the model's OWN predicted prob, not raw loss counts. Read-only.
    """
    from src.walters.miss_analysis import run_miss_analysis
    from rich.table import Table

    out = run_miss_analysis()
    if not out:
        console.print("[yellow]No graded predictions found.[/yellow]")
        return

    console.print("\n[bold]Miss analysis — actual vs predicted by category[/bold]")
    console.print("[dim]gap = actual − predicted win rate. Negative = model overrated that "
                  "bucket (a miss category). Flagged only if gap < −2×SE AND n ≥ "
                  f"{min_n}. REMEMBER: testing many buckets means 1-2 flag by chance — "
                  "trust a flag only if the gap is large, well-sampled, and part of a "
                  "gradient, not one lone bucket.[/dim]\n")

    flagged = []
    # show dimensions in a stable, meaningful order; park last (many buckets)
    order = ["confidence_tier", "favorite_side", "market", "run_environment",
             "day_night", "one_run_risk", "starter_known", "totals_availability", "park"]
    for dim in order:
        if dim not in out:
            continue
        rows = out[dim]
        t = Table(title=dim, show_header=True, header_style="bold")
        for c in ("Bucket", "n", "actual", "predicted", "gap", "±SE"):
            t.add_column(c, justify="left" if c == "Bucket" else "right")
        for label, n, actual, predicted, gap, se in rows:
            if dim == "park" and n < min_n:
                continue  # skip tiny park buckets from display noise
            flag = ""
            if se and n >= min_n and gap < -2 * se:
                flag = "yellow"
                flagged.append((dim, label, n, gap, se))
            gaptxt = f"[{flag}]{gap*100:+.1f}pp[/{flag}]" if flag else f"{gap*100:+.1f}pp"
            t.add_row(label, str(n), f"{actual*100:.1f}%", f"{predicted*100:.1f}%",
                      gaptxt, f"{se*100:.1f}pp" if se else "—")
        console.print(t)
        console.print("")

    if flagged:
        console.print("[bold]Flagged buckets (gap < −2×SE):[/bold]")
        for dim, label, n, gap, se in flagged:
            console.print(f"  • {dim} / {label}: {gap*100:+.1f}pp (n={n}, SE {se*100:.1f}pp)")
        console.print(f"\n[dim]{len(flagged)} flag(s). With ~25 buckets tested, expect ~1 false "
                      "positive by chance. Treat each as a HYPOTHESIS: does it show a gradient? "
                      "Is it large AND well-sampled? Re-test out-of-sample before believing "
                      "it. A lone flag is probably noise.[/dim]")
    else:
        console.print("[green]No bucket underperforms its predicted rate beyond noise. "
                      "The model's misses are variance, not a fixable category.[/green]")
    console.print("")


@cli.command("backtest")
@click.option("--season", default="2025")
@click.option("--competition", "competition_code", default="MLB")
def backtest_cmd(season, competition_code):
    """
    Leakage-free historical backtest: re-run the current model across a past
    season using only prior games for each prediction. Validates the
    confidence-tier overconfidence gradient on INDEPENDENT data before we tune
    run-shrink. Structural/run-profile calibration only (no pitcher layer — see
    module docstring). Does not write predictions or touch the model.
    """
    from src.walters.backtest import (run_backtest, calibration_by_tier,
                                       totals_bias_by_band)
    from rich.table import Table

    console.print(f"[cyan]Backtesting {season} (leakage-free, point-in-time "
                  f"profiles)... this walks the full season, give it a moment.[/cyan]")
    results = run_backtest(season=season, competition_code=competition_code)
    if not results:
        console.print(f"[yellow]No backtest results for {season} "
                      "(no finished games, or none in DB).[/yellow]")
        return

    console.print(f"[green]✓ Backtested {len(results)} games.[/green]\n")
    console.print("[bold]Backtest calibration by confidence tier[/bold]")
    console.print(f"[dim]{season} data, current model, no leakage. gap = actual − predicted. "
                  "The 2026 miss-analysis showed a monotonic overconfidence gradient "
                  "(strong picks underperform most). If the SAME gradient appears here on "
                  "independent data, it's real and we tune run-shrink. If not, it was a "
                  "recent-window artifact.[/dim]\n")

    tiers = calibration_by_tier(results)
    t = Table(show_header=True, header_style="bold")
    for c in ("Tier", "n", "actual", "predicted", "gap", "±SE"):
        t.add_column(c, justify="left" if c == "Tier" else "right")
    gaps = []
    for label, n, actual, predicted, gap, se in tiers:
        if n == 0:
            t.add_row(label, "0", "—", "—", "—", "—")
            continue
        flag = "yellow" if (se and gap < -2 * se) else ""
        gaptxt = f"[{flag}]{gap*100:+.1f}pp[/{flag}]" if flag else f"{gap*100:+.1f}pp"
        t.add_row(label, str(n), f"{actual*100:.1f}%", f"{predicted*100:.1f}%",
                  gaptxt, f"{se*100:.1f}pp" if se else "—")
        gaps.append((label, n, gap))
    console.print(t)

    # gradient check
    ordered = [g for (_, n, g) in gaps if n >= 20]
    if len(ordered) >= 3:
        monotonic = all(ordered[i] >= ordered[i+1] for i in range(len(ordered)-1))
        strong_gap = gaps[-1][2] if gaps and gaps[-1][1] >= 20 else None
        console.print("")
        if monotonic and strong_gap is not None and strong_gap < -0.03:
            console.print("[yellow]→ CONFIRMED: monotonic overconfidence gradient holds on "
                          f"{season} independent data (worsens toward strong picks). This is "
                          "a real calibration gap — tuning run-shrink harder at the top is "
                          "justified.[/yellow]")
        elif strong_gap is not None and strong_gap < -0.03:
            console.print("[dim]→ Strong picks underperform here too, but not cleanly "
                          "monotonic. Suggestive; worth a careful run-shrink test.[/dim]")
        else:
            console.print("[green]→ NOT confirmed: the gradient does NOT reproduce on "
                          f"{season}. The 2026 pattern was likely a recent-window artifact — "
                          "do NOT tune run-shrink off it.[/green]")
    console.print("")

    # --- totals bias confirmation (the 2026 low-projection gradient) ---
    tb = totals_bias_by_band(results)
    console.print(f"[bold]Totals bias by projected band — {season} (independent)[/bold]")
    console.print("[dim]2026 showed a monotonic LOW-projection bias: +1.06 (low), +0.54 "
                  "(mid), ~0 (high) — model under-projects low-scoring games. Does it "
                  "reproduce here? (mean error = actual − projected; + = under-projected)[/dim]")
    tt = Table(show_header=True, header_style="bold")
    for c in ("Projected band", "n", "mean error", "±SE"):
        tt.add_column(c, justify="left" if c == "Projected band" else "right")
    tb_vals = []
    for label, n, m, se in tb:
        if n == 0:
            tt.add_row(label, "0", "—", "—")
            continue
        flag = "yellow" if (se and abs(m) > 2 * se) else ""
        mtxt = f"[{flag}]{m:+.2f}[/{flag}]" if flag else f"{m:+.2f}"
        tt.add_row(label, str(n), mtxt, f"{se:.2f}" if se else "—")
        tb_vals.append((label, n, m))
    console.print(tt)

    # verdict: is low/mid meaningfully positive and gradient descending?
    low = next((m for (l, n, m) in tb_vals if l.startswith("low") and n >= 30), None)
    mid = next((m for (l, n, m) in tb_vals if l.startswith("mid") and n >= 30), None)
    high = next((m for (l, n, m) in tb_vals if l.startswith("high") and n >= 30), None)
    if low is not None and mid is not None and high is not None:
        reproduces = (low > 0.4 and mid > 0.2 and low > mid > high - 0.15)
        if reproduces:
            console.print("[yellow]→ CONFIRMED: the low-projection under-bias reproduces on "
                          f"{season}. Real, fixable — the model under-projects low-scoring "
                          "games on independent data. A low-total upward calibration (or "
                          "revisiting run-shrink's effect on low totals) is justified.[/yellow]")
        else:
            console.print("[green]→ NOT confirmed: the low-projection bias does NOT cleanly "
                          f"reproduce on {season}. The 2026 pattern was likely a window "
                          "artifact — do NOT adjust low-total projections off it.[/green]")
    else:
        console.print("[dim]→ Insufficient sample in the projected bands for a verdict.[/dim]")
    console.print("")


@cli.command("shrink-sweep")
@click.option("--season", default="2025")
@click.option("--fracs", default="0.25,0.35,0.45",
              help="Comma-separated run_shrink_frac values to test (0.25 is current).")
def shrink_sweep_cmd(season, fracs):
    """
    Run-shrink tuning sweep: re-run the leakage-free backtest at several shrink
    strengths and report, for each, the TOTALS bias by band AND the win-prob tier
    calibration. Finds the shrink level that flattens both totals tails (the
    confirmed low +0.84 / very-high −0.91 dispersion bias) WITHOUT breaking side
    calibration. Evidence-based way to pick the new frac — the backtest is the
    judge, not intuition.
    """
    from src.walters.backtest import (run_backtest, calibration_by_tier,
                                       totals_bias_by_band)
    from rich.table import Table

    frac_list = [float(x.strip()) for x in fracs.split(",")]
    console.print(f"[cyan]Shrink sweep on {season}: testing frac = {frac_list} "
                  "(leakage-free; each is a full-season walk, give it time).[/cyan]\n")

    summary = []
    for frac in frac_list:
        results = run_backtest(season=season, shrink_frac_override=frac)
        if not results:
            console.print(f"[yellow]frac {frac}: no results.[/yellow]")
            continue
        tb = totals_bias_by_band(results)
        tiers = calibration_by_tier(results)

        console.print(f"[bold]── run_shrink_frac = {frac}"
                      f"{'  (current production)' if abs(frac-0.25) < 1e-9 else ''} ──[/bold]")
        # totals bias
        tt = Table(show_header=True, header_style="bold")
        for c in ("Projected band", "n", "mean error", "±SE"):
            tt.add_column(c, justify="left" if c == "Projected band" else "right")
        low = mid = high = vhigh = None
        for label, n, m, se in tb:
            if n == 0:
                tt.add_row(label, "0", "—", "—"); continue
            flag = "yellow" if (se and abs(m) > 2 * se) else ""
            mtxt = f"[{flag}]{m:+.2f}[/{flag}]" if flag else f"{m:+.2f}"
            tt.add_row(label, str(n), mtxt, f"{se:.2f}" if se else "—")
            if label.startswith("low"): low = m
            elif label.startswith("mid"): mid = m
            elif label.startswith("high"): high = m
            elif label.startswith("very"): vhigh = m
        console.print(tt)
        # side calibration health: worst |gap| among well-sampled tiers
        worst_gap = 0.0
        for lbl, n, actual, predicted, gap, se in tiers:
            if n and n >= 50 and gap is not None and abs(gap) > abs(worst_gap):
                worst_gap = gap
        # tail flatness score: how close low & very-high are to zero
        tail_score = None
        if low is not None and vhigh is not None:
            tail_score = abs(low) + abs(vhigh)
        console.print(f"  [dim]tail imbalance |low|+|very-high| = "
                      f"{tail_score:.2f} (lower=flatter); worst side-tier gap = "
                      f"{worst_gap*100:+.1f}pp (keep small)[/dim]\n")
        summary.append((frac, low, vhigh, tail_score, worst_gap))

    if summary:
        console.print("[bold]Sweep summary[/bold]")
        t = Table(show_header=True, header_style="bold")
        for c in ("frac", "low band", "very-high band", "tail imbalance", "worst side gap"):
            t.add_column(c, justify="left" if c == "frac" else "right")
        best = min(summary, key=lambda r: (r[3] if r[3] is not None else 9,
                                           abs(r[4])))
        for frac, low, vhigh, tail, wg in summary:
            mark = "  ←best tail flatness" if (frac, low, vhigh, tail, wg) == best else ""
            t.add_row(f"{frac}{mark}",
                      f"{low:+.2f}" if low is not None else "—",
                      f"{vhigh:+.2f}" if vhigh is not None else "—",
                      f"{tail:.2f}" if tail is not None else "—",
                      f"{wg*100:+.1f}pp")
        console.print(t)
        console.print("[dim]Pick the frac that minimizes tail imbalance (flattens both totals "
                      "extremes) WHILE keeping the worst side-tier gap small (side calibration "
                      "must not degrade). If the flattest-totals frac also keeps sides clean, "
                      "that's the new value — set via set-config run_shrink_frac, then verify "
                      "forward on live games. If flattening totals breaks sides, it's a trade-"
                      "off to weigh, not an automatic change.[/dim]\n")


@cli.command("totals-model-test")
@click.option("--season", default="2025")
@click.option("--park-weight", default=1.0,
              help="How strongly park factor applies (0=off, 1=full). Sweep to "
                   "see if park helps.")
def totals_model_test_cmd(season, park_weight):
    """
    Step 1 totals-model head-to-head: does a direct park-adjusted totals
    projection beat the current byproduct total (home_xr+away_xr) on leakage-free
    out-of-sample MAE/bias? If it can't clear the bar on the basics, we stop here.
    """
    from src.walters.backtest import run_backtest
    from src.walters.totals_model import compare_totals_models, project_total
    from rich.table import Table

    console.print(f"[cyan]Totals-model head-to-head on {season} (leakage-free)... "
                  "walking the season.[/cyan]")
    rows = run_backtest(season=season, return_totals_rows=True)
    if not rows:
        console.print(f"[yellow]No backtest rows for {season}.[/yellow]")
        return

    # apply park_weight by recomputing model errors at the chosen weight
    import math
    inc_err, mdl_err = [], []
    for (_, _, inc_total, actual_total, hrs, hra, ars, ara, lg, venue) in rows:
        if actual_total is None or inc_total is None:
            continue
        inc_err.append(actual_total - inc_total)
        mdl_total = project_total(hrs, hra, ars, ara, lg, venue, park_weight=park_weight)
        mdl_err.append(actual_total - mdl_total)

    def _stats(errs):
        n = len(errs)
        mae = sum(abs(e) for e in errs) / n
        me = sum(errs) / n
        sd = (sum((e - me) ** 2 for e in errs) / (n - 1)) ** 0.5 if n > 1 else 0
        return n, mae, me, (sd / math.sqrt(n) if n else 0)

    in_n, in_mae, in_me, in_se = _stats(inc_err)
    md_n, md_mae, md_me, md_se = _stats(mdl_err)

    t = Table(title=f"Totals model vs incumbent — {season} (park_weight={park_weight})",
              show_header=True, header_style="bold")
    for c in ("Model", "n", "MAE", "mean bias", "±SE"):
        t.add_column(c, justify="left" if c == "Model" else "right")
    t.add_row("Incumbent (byproduct total)", str(in_n), f"{in_mae:.3f}",
              f"{in_me:+.3f}", f"{in_se:.3f}")
    t.add_row("Step-1 totals model", str(md_n), f"{md_mae:.3f}",
              f"{md_me:+.3f}", f"{md_se:.3f}")
    console.print(t)

    mae_delta = md_mae - in_mae
    console.print("")
    if mae_delta < -0.02:
        console.print(f"[green]→ Totals model BEATS incumbent on MAE by {-mae_delta:.3f} "
                      "runs/game. Clears the Step-1 bar — worth proceeding to Step 2 "
                      "(totals-specific Stage-1 tests for weather/bullpen/umpire).[/green]")
    elif mae_delta > 0.02:
        console.print(f"[yellow]→ Totals model is WORSE than incumbent by {mae_delta:.3f} "
                      "runs/game MAE. Does not clear the bar. The byproduct total is already "
                      "good; a direct model (at this park_weight) doesn't help. Stop or "
                      "try a different park_weight.[/yellow]")
    else:
        console.print(f"[dim]→ Essentially tied (MAE Δ {mae_delta:+.3f}). No clear win for the "
                      "direct model on the basics. Park factor alone isn't moving the needle; "
                      "a totals model would need Step-2 inputs to justify itself — but the "
                      "honest read is the incumbent total is hard to beat structurally.[/dim]")
    console.print("[dim]MAE = mean absolute error per game (lower=better); mean bias = "
                  "actual − projected (0=centered). Beating the number is ACCURACY, not "
                  "totals-market edge (separate CLV question).[/dim]\n")


@cli.command("export-nfl-results")
def export_nfl_results_cmd():
    """Graded NFL results file for the consumer (rehearsal-flagged)."""
    from src.walters.nfl_predict import export_nfl_results
    path = export_nfl_results()
    console.print(f"[green]✓ Wrote {path}[/green]")


@cli.command("results-tally")
@click.option("--days", default=30, type=int, help="Rolling window size.")
def results_tally_cmd(days):
    """Regenerate RESULTS.md — rolling per-sport record."""
    from src.walters.export import results_tally
    path = results_tally(days=days)
    console.print(f"[green]✓ Wrote {path}[/green]")


@cli.command("nfl-grade")
def nfl_grade_cmd():
    """Grade NFL predictions vs finished games and banked closers (read-only)."""
    from src.walters.nfl_predict import grade_nfl
    r = grade_nfl(progress=lambda msg: console.print(msg))
    if not r.get("ok"):
        console.print(f"[yellow]{r.get('reason')}[/yellow]")


@cli.command("predict-nfl")
def predict_nfl_cmd():
    """Write NFL v1 predictions for upcoming games (rehearsal machinery)."""
    from src.walters.nfl_predict import predict_nfl
    n = predict_nfl()
    console.print(f"[green]✓ Wrote {n} NFL predictions (nfl_elo_v1)[/green]")


@cli.command("export-nfl-predictions")
def export_nfl_predictions_cmd():
    """Rehearsal-format NFL predictions export (NOT for consumption yet)."""
    from src.walters.nfl_predict import export_nfl_predictions
    path = export_nfl_predictions()
    console.print(f"[green]✓ Wrote {path}[/green] [dim](LIVE format: rehearsal=false, quarantine fields)[/dim]")


@cli.command("nfl-backtest-caps")
def nfl_backtest_caps_cmd():
    """R-track: test confidence-cap/shrink variants vs the uncapped baseline.

    Pre-committed acceptance (frozen 2026-09-17 BEFORE results): a variant
    ships iff its log-loss beats baseline AND no n>=30 band's calibration
    gap worsens by more than 0.5pp."""
    from src.walters.nfl_backtest import run_backtest
    variants = [("baseline", None, None), ("cap 0.72", 0.72, None),
                ("cap 0.75", 0.75, None), ("cap 0.80", 0.80, None),
                ("shrink 0.90", None, 0.90)]
    rows = []
    for label, cap, shrink in variants:
        console.print(f"[bold]── {label} ──[/bold]")
        r = run_backtest(progress=lambda msg: console.print(msg),
                         cap=cap, shrink=shrink)
        rows.append((label, r.get("ll_model")))
    console.print("\n[bold]VARIANT SUMMARY (read bands above vs baseline):[/bold]")
    for label, ll in rows:
        console.print(f"  {label:12} log-loss {ll}")


@cli.command("nfl-backtest")
def nfl_backtest_cmd():
    """Walk-forward NFL v1 backtest against the frozen phase-2 gate."""
    from src.walters.nfl_backtest import run_backtest
    r = run_backtest(progress=lambda msg: console.print(msg))
    if not r.get("ok"):
        console.print(f"[yellow]✗ {r.get('reason')}[/yellow]")
    elif r["pass"]:
        console.print("[green]✓ GATE PASS[/green] — next: Week-2 dress rehearsal (NOT live).")
    else:
        console.print("[yellow]✗ GATE FAIL[/yellow] — model does not ship; iterate or park.")


@cli.command("capture-weather-nfl")
def capture_weather_nfl_cmd():
    """Tracking-only weather capture for upcoming NFL games (N1 phase 1).

    Keyed by home team (32 stadiums; 9 roofed + SoFi canopy). Roofed games
    store roof_state only; open-air games get an Open-Meteo snapshot near
    kickoff. Weather is banked history for the eventual totals work — no
    model consumes it."""
    from datetime import timedelta
    from src.web.weather import fetch_weather_at, lookup_nfl_stadium
    from src.db.schema import GameWeather
    init_db()
    captured = skipped = 0
    with session_scope() as s2:
        now = datetime.utcnow()
        rows = list(s2.execute(
            select(Match).where(Match.sport == Sport.NFL,
                                Match.status == MatchStatus.SCHEDULED,
                                Match.utc_date >= now,
                                Match.utc_date <= now + timedelta(days=8))
        ).scalars())
        for m2 in rows:
            info = lookup_nfl_stadium(m2.home_team.name if m2.home_team else None)
            if info is None:
                skipped += 1
                continue
            lat, lon, roofed = info
            wx = None if roofed else fetch_weather_at(lat, lon, m2.utc_date)
            s2.add(GameWeather(
                match_id=m2.id,
                source_game_id=str((m2.external_ids or {}).get("api_american_football") or ""),
                game_date=m2.utc_date, venue=m2.home_team.name,
                roof_state="indoor(roof)" if roofed else "outdoor",
                temperature_f=(wx or {}).get("temperature_f"),
                wind_mph=(wx or {}).get("wind_mph"),
                wind_dir_deg=(wx or {}).get("wind_dir_deg"),
                precipitation_in=(wx or {}).get("precipitation_in"),
                condition=(wx or {}).get("condition") or ("indoor" if roofed else None),
            ))
            captured += 1
    console.print(f"[green]✓ NFL weather: captured={captured} skipped={skipped}[/green]")


@cli.command("sync-odds-nfl")
def sync_odds_nfl_cmd():
    """Capture book odds for upcoming NFL games (per-game; Week-N tracking)."""
    from src.ingestion.service import sync_odds_nfl
    r = sync_odds_nfl(progress=lambda msg: console.print(msg))
    console.print(f"[green]✓ NFL odds: created={r['created']} across {r['games']} games[/green]")


@cli.command("sync-kalshi-ncaa")
def sync_kalshi_ncaa_cmd():
    """Pull open Kalshi NCAA football game markets (KXNCAAFGAME) and store
    snapshots — fourth sport family on the shared matcher; the console's
    available-sports line is the discovery probe if the series guess is
    wrong (the NFL/NHL pattern). Market-only doctrine: these prices feed
    the fixtures roster, no predictions."""
    from src.ingestion.kalshi_sync import sync_kalshi_mlb
    from src.db.schema import Sport
    r = sync_kalshi_mlb(progress=lambda m: console.print(m),
                        sport=Sport.NFL, series_override="KXNCAAFGAME")
    if r.get("ok"):
        console.print(f"[green]✓ Kalshi NCAA: {r.get('stored', 0)} prices stored[/green]")
        console.print(f"  series {r.get('series')} · {r.get('markets')} markets · "
                      f"matched {r.get('matched')} · unmatched {r.get('unmatched')} "
                      f"(ambiguous {r.get('ambiguous')}) · in-play {r.get('in_play')} ")
    else:
        console.print(f"[red]✗ Kalshi NCAA: {r.get('error')}[/red]")


@cli.command("sync-kalshi-nhl")
def sync_kalshi_nhl_cmd():
    """Pull open Kalshi NHL game markets (KXNHLGAME) and store snapshots.

    H-track phase 1c: the parameterized two-sided matcher's third sport.
    Preseason listings (if any) are shakedown material; the series guess
    is verified by the console's available-sports line — that IS the
    discovery probe (the NFL pattern)."""
    from src.ingestion.kalshi_sync import sync_kalshi_mlb
    from src.db.schema import Sport
    r = sync_kalshi_mlb(progress=lambda m: console.print(m),
                        sport=Sport.NHL, series_override="KXNHLGAME")
    if r.get("ok"):
        console.print(f"[green]✓ Kalshi NHL: {r.get('stored', 0)} prices stored[/green]")
        console.print(f"  series {r.get('series')} · {r.get('markets')} markets · "
                      f"matched {r.get('matched')} · unmatched {r.get('unmatched')} "
                      f"(ambiguous {r.get('ambiguous')}) · in-play {r.get('in_play')} ")
    else:
        console.print(f"[red]✗ Kalshi NHL: {r.get('error')}[/red]")


@cli.command("sync-kalshi-nfl")
def sync_kalshi_nfl_cmd():
    """Pull open Kalshi NFL game markets (KXNFLGAME) and store snapshots.

    NFL phase 1c: reuses the parameterized two-sided matcher. If the series
    ticker guess is wrong, the summary lists Kalshi's available sports —
    that console IS the discovery probe."""
    from src.ingestion.kalshi_sync import sync_kalshi_mlb
    from src.db.schema import Sport
    r = sync_kalshi_mlb(progress=lambda m: console.print(m),
                        sport=Sport.NFL, series_override="KXNFLGAME")
    if r.get("ok"):
        console.print(f"[green]✓ Kalshi NFL: {r.get('stored', 0)} prices stored[/green]")
        console.print(f"  series {r.get('series')} · {r.get('markets')} markets · "
                      f"matched {r.get('matched')} · unmatched {r.get('unmatched')} "
                      f"(ambiguous {r.get('ambiguous')}) · in-play {r.get('in_play')} ")
    else:
        console.print(f"[yellow]✗ Kalshi NFL: {r.get('reason')}[/yellow]")
        if r.get("sports_available"):
            console.print(f"  Kalshi sports: {', '.join(r['sports_available'][:12])}")


@cli.command("sync-kalshi")
@click.option("--date-from", "date_from", default=None, help="YYYY-MM-DD lower bound")
@click.option("--date-to", "date_to", default=None, help="YYYY-MM-DD upper bound")
def sync_kalshi_cmd(date_from, date_to):
    """
    Pull Kalshi MLB game markets as a SECOND market source (stored as
    OddsSnapshot source='kalshi', parallel to the bookmaker consensus). Step 1
    of the Kalshi investigation: instrument the second market so we can measure
    disagreement. Public data — no auth. Does NOT touch the model or bets.
    """
    from datetime import datetime
    from src.ingestion.kalshi_sync import sync_kalshi_mlb

    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = datetime.strptime(date_to, "%Y-%m-%d") if date_to else None

    def prog(m):
        console.print(f"[dim]{m}[/dim]")

    try:
        r = sync_kalshi_mlb(date_from=df, date_to=dt, progress=prog)
    except Exception as e:
        console.print(f"[red]✗ Kalshi sync failed: {e}[/red]")
        console.print("[dim]If this is a network/DNS error, Kalshi's API host may need "
                      "to be reachable from your network.[/dim]")
        return

    if not r.get("ok"):
        console.print(f"[yellow]Kalshi sync: {r.get('reason')}[/yellow]")
        if r.get("series"):
            console.print(f"[dim]MLB series seen: {r['series']}[/dim]")
        return
    console.print(f"[green]✓ Kalshi: {r['stored']} prices stored[/green]")
    console.print(f"  [dim]series {r['series']} · {r['markets']} markets · "
                  f"matched {r['matched']} · unmatched {r['unmatched']} "
                  f"(of which ambiguous {r.get('ambiguous', 0)}) · "
                  f"in-play skipped {r.get('in_play', 0)} — "
                  "unmatched = wrong date for our window, no scheduled game, "
                  "or a team/side tie we refused to guess[/dim]")


@cli.command("kalshi-disagreement")
@click.option("--since", default=None, help="YYYY-MM-DD; only snapshots on/after")
def kalshi_disagreement_cmd(since):
    """
    THE Step-1 read: how often, and by how much, does Kalshi disagree with the
    bookmaker de-vig consensus on the same game/side? Self-joins odds_snapshots
    (source='kalshi' vs book consensus) by match+selection, nearest capture.
    If they agree ~always → Kalshi is redundant, stop. If systematic
    disagreement → worth Step 2 (which market predicts better).
    """
    from datetime import datetime
    from collections import defaultdict
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import OddsSnapshot, Match, Sport
    from rich.table import Table

    since_dt = datetime.fromisoformat(since) if since else None

    from src.db.schema import Odds

    with session_scope() as s:
        # Kalshi legs: latest PRE-GAME capture per (match, selection).
        # (Original design assumed book rows would also live in OddsSnapshot
        # under market="ML" — nothing ever writes those; the book consensus
        # lives in the Odds table. Pair against its de-vig instead — the same
        # math the export's vs_book_pp uses — so this reads the data that
        # actually exists.)
        q = (select(OddsSnapshot, Match.utc_date)
             .join(Match, Match.id == OddsSnapshot.match_id)
             .where(Match.sport == Sport.MLB,
                    OddsSnapshot.market == "ML",
                    OddsSnapshot.source == "kalshi"))
        if since_dt:
            q = q.where(OddsSnapshot.captured_at >= since_dt)
        kalshi_latest: dict = {}
        match_ids = set()
        for sn, start in s.execute(q):
            if start is not None and sn.captured_at is not None and sn.captured_at >= start:
                continue  # in-game price, not a pre-game one
            key = (sn.match_id, sn.selection)
            prev = kalshi_latest.get(key)
            if prev is None or sn.captured_at > prev.captured_at:
                kalshi_latest[key] = sn
            match_ids.add(sn.match_id)

        # Book de-vig fair prob per (match, selection) from the Odds table
        # (best price per side, proportional de-vig — mirrors the export).
        best: dict = {}
        for o in s.execute(select(Odds).where(
                Odds.match_id.in_(match_ids), Odds.market == "1X2",
                Odds.selection.in_(["HOME", "AWAY"]))).scalars():
            if o.price_decimal and o.price_decimal > 1.0:
                k2 = (o.match_id, o.selection)
                if k2 not in best or o.price_decimal > best[k2]:
                    best[k2] = o.price_decimal

    book_fair: dict = {}
    for mid in match_ids:
        ph, pa = best.get((mid, "HOME")), best.get((mid, "AWAY"))
        if not ph or not pa:
            continue
        inv_h, inv_a = 1.0 / ph, 1.0 / pa
        tot = inv_h + inv_a
        book_fair[(mid, "HOME")] = inv_h / tot
        book_fair[(mid, "AWAY")] = inv_a / tot

    diffs = []
    paired = 0
    for key, sn in kalshi_latest.items():
        b = book_fair.get(key)
        if b is None or sn.devig_prob is None:
            continue
        diffs.append((sn.devig_prob - b) * 100.0)  # pp, kalshi − book
        paired += 1

    if not diffs:
        console.print("[yellow]No paired Kalshi/book snapshots yet. Run sync-kalshi "
                      "alongside sync-odds on the same games first, then re-check.[/yellow]")
        return

    import statistics
    n = len(diffs)
    mean_d = statistics.mean(diffs)
    med_d = statistics.median(diffs)
    mean_abs = statistics.mean(abs(x) for x in diffs)
    big = sum(1 for x in diffs if abs(x) >= 3.0)   # ≥3pp disagreements
    huge = sum(1 for x in diffs if abs(x) >= 5.0)

    console.print(f"\n[bold]Kalshi vs bookmaker consensus — {paired} paired sides[/bold]\n")
    t = Table(show_header=True, header_style="bold")
    for c in ("Metric", "Value"):
        t.add_column(c, justify="left")
    t.add_row("mean signed diff (kalshi − book)", f"{mean_d:+.2f} pp")
    t.add_row("median signed diff", f"{med_d:+.2f} pp")
    t.add_row("mean ABSOLUTE diff", f"{mean_abs:.2f} pp")
    t.add_row("disagreements ≥3pp", f"{big}/{n} ({big/n*100:.0f}%)")
    t.add_row("disagreements ≥5pp", f"{huge}/{n} ({huge/n*100:.0f}%)")
    console.print(t)

    console.print("")
    if mean_abs < 1.0 and big / n < 0.10:
        console.print("[yellow]→ Kalshi largely AGREES with the book (small mean abs diff, few "
                      "≥3pp gaps). Likely REDUNDANT — a second copy of the consensus. Honest "
                      "read: not worth a Step 2 yet; stop and revisit if this changes.[/yellow]")
    else:
        console.print("[green]→ Meaningful disagreement exists (sizable mean abs diff and/or a "
                      "real share of ≥3pp gaps). Worth Step 2: when they disagree, which market "
                      "is closer to the actual outcome? That's the CLV-style test that says "
                      "whether Kalshi is a BETTER signal or just noisier.[/green]")
    console.print("[dim]Signed mean near 0 with nonzero abs diff = no systematic lean, just "
                  "scatter (two markets wobbling around the same consensus). A systematic signed "
                  "lean would mean one market persistently prices higher — more interesting. "
                  "This is instrumentation; not a bet signal until Step 2.[/dim]\n")


@cli.command("soccer-backtest")
@click.option("--competition", "competition_code", default="PL")
@click.option("--season", default=None, help="e.g. 2024/25; omit for all seasons")
@click.option("--min-prior", default=40, help="Prior finished matches required before scoring")
@click.option("--rho", "rho", default=None, type=float,
              help="Dixon-Coles rho override. Default: the PRODUCTION soccer model's "
                   "stored value, so the backtest evaluates the model you'd actually ship.")
def soccer_backtest_cmd(competition_code, season, min_prior, rho):
    """
    LEAKAGE-FREE soccer backtest — the disciplined equivalent of the MLB backtest.
    Walks the season in date order, predicts each match using ONLY prior matches
    (Elo walked game-by-game, strengths from prior games only). Reports 1X2
    calibration (home/draw/away), multiclass log-loss + Brier. This is the honest
    read on the soccer model we never trustworthily had (the old holdout eval
    leaked). Read-only.
    """
    from src.walters.soccer_backtest import run_soccer_backtest, soccer_calibration
    from rich.table import Table

    console.print(f"[cyan]Leakage-free soccer backtest: {competition_code} "
                  f"{season or '(all seasons)'}, min_prior={min_prior}…[/cyan]")
    if rho is None:
        # default to PRODUCTION config, not the dataclass default (0.0) —
        # otherwise the backtest quietly evaluates a model we don't ship.
        from src.walters.training import _resolve_model_version
        from src.db.database import session_scope as _scope
        try:
            with _scope() as _s:
                _mv = _resolve_model_version(_s, None, Sport.SOCCER)
                rho = float(((_mv.parameters or {}).get("poisson") or {})
                            .get("dixon_coles_rho", 0.0))
        except Exception:
            rho = 0.0
    console.print(f"  [dim]dixon_coles_rho = {rho} "
                  "(production default; override with --rho)[/dim]")
    results = run_soccer_backtest(competition_code, season, min_prior,
                                  dixon_coles_rho=rho)
    if not results:
        console.print("[yellow]No results — competition/season not found or too few "
                      "finished matches.[/yellow]")
        return
    cal = soccer_calibration(results)
    console.print(f"\n[bold]Soccer calibration — {competition_code} "
                  f"({cal['n']} leakage-free predictions)[/bold]\n")
    console.print(f"  multiclass log-loss: {cal['log_loss']:.4f}  "
                  f"[dim](lower=better; 1.099 = uninformed 3-way guess)[/dim]")
    console.print(f"  Brier score: {cal['brier']:.4f}  [dim](lower=better)[/dim]\n")

    # base-rate vs mean-prediction sanity
    br, mp = cal["base_rates"], cal["mean_pred"]
    console.print("[bold]Base rate vs mean prediction[/bold] "
                  "[dim](model's average probs should ≈ actual outcome frequencies)[/dim]")
    t0 = Table(show_header=True, header_style="bold")
    for c in ("Outcome", "actual freq", "mean predicted"):
        t0.add_column(c, justify="left" if c == "Outcome" else "right")
    for k, label in (("H", "Home win"), ("D", "Draw"), ("A", "Away win")):
        t0.add_row(label, f"{br[k]*100:.1f}%", f"{mp[k]*100:.1f}%")
    console.print(t0)
    console.print("[dim]If mean-predicted draw % is well below actual draw % → the model "
                  "under-predicts draws (the classic Poisson soccer failure). That's the "
                  "first thing to check.[/dim]\n")

    # per-outcome calibration
    for key, label in (("home_bins", "Home-win"), ("draw_bins", "Draw"), ("away_bins", "Away-win")):
        rows = cal[key]
        if not rows:
            continue
        console.print(f"[bold]{label} probability calibration[/bold]")
        t = Table(show_header=True, header_style="bold")
        for c in ("Prob band", "n", "predicted", "actual", "±SE"):
            t.add_column(c, justify="left" if c == "Prob band" else "right")
        for band, n, avg_pred, act, se in rows:
            flag = "yellow" if (se and abs(act - avg_pred) > 2 * se) else ""
            acttxt = f"[{flag}]{act*100:.0f}%[/{flag}]" if flag else f"{act*100:.0f}%"
            ntxt = f"[dim]{n}[/dim]" if n < 20 else str(n)
            t.add_row(band, ntxt, f"{avg_pred*100:.0f}%", acttxt, f"{se*100:.0f}%" if se else "—")
        console.print(t)
        console.print("")
    console.print("[dim]Flagged bands (>2·SE off diagonal) on WELL-SAMPLED buckets = real "
                  "miscalibration. Thin bands (<20, dimmed) are noise. This is the honest "
                  "read the leaking holdout eval never gave.[/dim]\n")

    # --- model vs closing market (requires soccer-odds-history ingest) ---
    from src.walters.soccer_backtest import market_comparison
    mc = market_comparison(results)
    if mc:
        console.print(f"\n[bold]Model vs closing market[/bold] "
                      f"[dim]({mc['games']} games with fdcuk_close odds; "
                      "market = proportionally de-vigged closing 1X2)[/dim]")
        console.print(f"  log-loss — model {mc['model_log_loss']:.4f} vs "
                      f"market {mc['market_log_loss']:.4f} "
                      f"[dim](gap {mc['model_log_loss']-mc['market_log_loss']:+.4f}; "
                      "beating the close is rare — the question is how close)[/dim]")
        g = mc['mean_abs_gap_pp']
        console.print(f"  mean |model−market|: H {g['HOME']:.1f}pp · D {g['DRAW']:.1f}pp · "
                      f"A {g['AWAY']:.1f}pp")
        console.print(f"  mean pick edge vs close: {mc['mean_pick_edge_pp']:+.2f}pp")
        pe, ne = mc['positive_edge'], mc['non_positive_edge']
        if pe['n']:
            console.print(f"  picks where model > close (n={pe['n']}): "
                          f"mean edge +{pe['mean_edge_pp']:.2f}pp, hit rate {pe['hit_rate']*100:.1f}%")
        if ne['n']:
            console.print(f"  picks where model ≤ close (n={ne['n']}): "
                          f"mean edge {ne['mean_edge_pp']:.2f}pp, hit rate {ne['hit_rate']*100:.1f}%")
        console.print("  [dim]This is soccer's own thermometer-vs-income-engine read — "
                      "judge it here, not by inheriting the MLB verdict.[/dim]")
    else:
        console.print("\n[dim]No closing odds stored for these games — run "
                      "soccer-odds-history first for the model-vs-market read.[/dim]")



@cli.command("dixon-coles-sweep")
@click.option("--competition", "competition_code", default="PL")
@click.option("--season", default=None)
@click.option("--rhos", default="0.0,-0.03,-0.06,-0.10,-0.15",
              help="Comma-separated rho values (0=off/pure Poisson).")
def dixon_coles_sweep_cmd(competition_code, season, rhos):
    """
    Sweep the Dixon-Coles rho (draw correction) through the leakage-free backtest
    and report, for each: mean predicted DRAW% vs actual, log-loss, and the
    favorite-band overconfidence. Finds the rho that best fixes the confirmed draw
    under-prediction WITHOUT hurting overall calibration. Evidence-based, like the
    MLB shrink-sweep. rho=0 is the current (pure Poisson) baseline.
    """
    from src.walters.soccer_backtest import run_soccer_backtest, soccer_calibration
    from rich.table import Table

    rho_list = [float(x.strip()) for x in rhos.split(",")]
    console.print(f"[cyan]Dixon-Coles sweep on {competition_code} {season or '(all)'}: "
                  f"rho = {rho_list}[/cyan]\n")

    t = Table(show_header=True, header_style="bold")
    for c in ("rho", "n", "log-loss", "pred draw%", "actual draw%", "draw gap",
              "fav 70-90% actual"):
        t.add_column(c, justify="left" if c == "rho" else "right")

    best = None
    for rho in rho_list:
        results = run_soccer_backtest(competition_code, season, dixon_coles_rho=rho)
        if not results:
            continue
        cal = soccer_calibration(results)
        actual_draw = cal["base_rates"]["D"] * 100
        pred_draw = cal["mean_pred"]["D"] * 100
        gap = pred_draw - actual_draw
        # favorite overconfidence: actual win-rate in the 70-90% home+away bands
        fav_hits = fav_n = 0
        for r in results:
            for pk, ak in (("p_home", "H"), ("p_away", "A")):
                if 0.70 <= r[pk] < 0.90:
                    fav_n += 1
                    fav_hits += 1 if r["actual"] == ak else 0
        fav_actual = (fav_hits / fav_n * 100) if fav_n else None
        tag = "  ← baseline" if rho == 0.0 else ""
        t.add_row(f"{rho}{tag}", str(cal["n"]), f"{cal['log_loss']:.4f}",
                  f"{pred_draw:.1f}%", f"{actual_draw:.1f}%",
                  f"{gap:+.1f}pp",
                  f"{fav_actual:.0f}% (n={fav_n})" if fav_actual is not None else "—")
        # track best by |draw gap| then log-loss
        score = (abs(gap), cal["log_loss"])
        if best is None or score < best[0]:
            best = (score, rho, cal["log_loss"], gap)
    console.print(t)
    if best:
        _, rho_b, ll_b, gap_b = best
        console.print(f"\n[green]→ Best draw calibration at rho={rho_b} "
                      f"(draw gap {gap_b:+.1f}pp, log-loss {ll_b:.4f}).[/green]")
        console.print("[dim]Pick the rho that closes the draw gap while keeping log-loss ≤ "
                      "baseline. If a rho fixes draws AND lowers log-loss AND brings the "
                      "70-90% favorite band closer to its predicted level, that's the value "
                      "to set. Then re-run soccer-backtest at that rho to confirm the full "
                      "calibration picture before trusting it.[/dim]\n")


@cli.command("soccer-odds-history")
@click.option("--competition", "competition_code", default="PL")
@click.option("--season", default=None, help="DB season string, e.g. 2024. Also derives the football-data.co.uk URL (2024 -> mmz4281/2425/E0.csv).")
@click.option("--csv", "csv_path", default=None, help="Path to a downloaded E0.csv (skips fetching).")
@click.option("--url", default=None, help="Override the derived CSV URL.")
def soccer_odds_history_cmd(competition_code, season, csv_path, url):
    """Ingest historical CLOSING 1X2 odds from football-data.co.uk.

    Stores per game: bookmaker=fdcuk_close, HOME/DRAW/AWAY closing prices
    (Pinnacle preferred, then Bet365, then market average). Joined to the
    leakage-free backtest, this gives soccer an honest model-vs-market read
    across a whole past season BEFORE launch. Idempotent per game."""
    from src.ingestion.soccer_odds_history import sync_soccer_closing_odds
    r = sync_soccer_closing_odds(
        competition_code=competition_code, season=season,
        csv_path=csv_path, url=url, progress=lambda m: console.print(f"  [dim]{m}[/dim]"),
    )
    if not r.get("ok"):
        console.print(f"[yellow]soccer-odds-history: {r.get('reason')}[/yellow]")
        return
    console.print(f"[green]✓ Closing odds stored for {r['stored_games']} games[/green] "
                  f"[dim](csv rows {r['csv_rows']} · already-had {r['skipped_existing']} · "
                  f"no closing cols {r['no_closing_cols']} · unmatched {r['unmatched']} "
                  f"of which ambiguous {r['ambiguous']})[/dim]")
    if r["unmatched_sample"]:
        console.print("  [yellow]unmatched sample:[/yellow] " + "; ".join(r["unmatched_sample"]))


@cli.command("elo-coeff-sweep")
@click.option("--competition", "competition_code", default="PL")
@click.option("--season", default=None)
@click.option("--coeffs", default="0.0023,0.0019,0.0016,0.0013,0.0010",
              help="Comma-separated elo_goal_coeff values (0.0023 = current default).")
@click.option("--rho", default=None, type=float,
              help="Dixon-Coles rho held FIXED across the sweep. Default: production value.")
def elo_coeff_sweep_cmd(competition_code, season, coeffs, rho):
    """
    S1: sweep elo_goal_coeff through the leakage-free backtest WITH the
    model-vs-closing-market scoreboard (requires soccer-odds-history ingest).

    The confirmed defect: 70-90% favorite bands land ~50-55% actual, and 65%+
    of picks claim ~+10pp edge over the close while hitting under 50%. The
    coefficient is the mechanistic lever (exp(coeff*elo_diff/2) goal mult) —
    damping it compresses win-leg probs toward consensus. Acceptance, in
    order: (1) mean pick edge vs close -> within ±2pp; (2) positive-edge
    bucket claimed-vs-actual closes; (3) 70-90% home band within ~1 SE;
    (4) log-loss gap to close narrows from +0.034; (5) draw gap stays <=2pp.
    """
    from src.walters.soccer_backtest import (run_soccer_backtest, soccer_calibration,
                                             market_comparison)
    from rich.table import Table

    if rho is None:
        from src.walters.training import _resolve_model_version
        from src.db.database import session_scope as _scope
        try:
            with _scope() as _s:
                _mv = _resolve_model_version(_s, None, Sport.SOCCER)
                rho = float(((_mv.parameters or {}).get("poisson") or {})
                            .get("dixon_coles_rho", 0.0))
        except Exception:
            rho = 0.0
    console.print(f"[cyan]elo_goal_coeff sweep — {competition_code} "
                  f"{season or '(all)'} at rho={rho}[/cyan]")

    t = Table(show_header=True, header_style="bold")
    for c in ("coeff", "log-loss", "vs close", "draw gap", "70-90% home",
              "pick edge", "+edge bucket", "-edge bucket"):
        t.add_column(c, justify="right")

    for raw in coeffs.split(","):
        coeff = float(raw.strip())
        results = run_soccer_backtest(competition_code, season,
                                      dixon_coles_rho=rho, elo_goal_coeff=coeff)
        if not results:
            console.print("[yellow]no results[/yellow]")
            return
        cal = soccer_calibration(results)
        draw_gap = (cal["mean_pred"]["D"] - cal["base_rates"]["D"]) * 100
        # 70-90% home band: predicted vs actual, pooled
        hi = [r for r in results if 0.70 <= r["p_home"] < 0.90]
        if hi:
            band_pred = sum(r["p_home"] for r in hi) / len(hi) * 100
            band_act = sum(1 for r in hi if r["actual"] == "H") / len(hi) * 100
            band = f"{band_pred:.0f}%→{band_act:.0f}% (n={len(hi)})"
        else:
            band = "—"
        mc = market_comparison(results)
        if mc:
            vs_close = f"{mc['model_log_loss']-mc['market_log_loss']:+.4f}"
            edge = f"{mc['mean_pick_edge_pp']:+.2f}pp"
            pe, ne = mc["positive_edge"], mc["non_positive_edge"]
            peb = (f"n={pe['n']} +{pe['mean_edge_pp']:.1f}pp hit {pe['hit_rate']*100:.0f}%"
                   if pe["n"] else "—")
            neb = (f"n={ne['n']} {ne['mean_edge_pp']:.1f}pp hit {ne['hit_rate']*100:.0f}%"
                   if ne["n"] else "—")
        else:
            vs_close = edge = peb = neb = "no odds"
        t.add_row(f"{coeff:.4f}", f"{cal['log_loss']:.4f}", vs_close,
                  f"{draw_gap:+.1f}pp", band, edge, peb, neb)
    console.print(t)
    console.print("[dim]Pick the coeff that collapses pick-edge toward 0 and closes the "
                  "70-90% band WITHOUT log-loss regressing or the draw gap reopening. "
                  "Then set-soccer-config --field elo_goal_coeff and log the decision. "
                  "If no coeff clears the bars, the recal-clamp fallback is next.[/dim]")


@cli.command("soccer-refresh")
@click.option("--max-drift", default=80.0, help="Max allowed Elo movement per team since production (pts).")
def soccer_refresh_cmd(max_drift):
    """S6: weekly soccer state refresh (Elo + contexts) with a SANITY gate.

    Run Mondays after weekend grading. Retrains from all finished matches,
    INHERITS production's poisson config verbatim (rho, elo_goal_coeff,
    promoted priors survive), and promotes only if: data grew, config
    inherited exactly, Elo distribution healthy, and no team drifted more
    than --max-drift since production. Config changes are NOT this command's
    job — those go through the market-scored backtest + set-soccer-config."""
    from src.walters.training import soccer_weekly_refresh
    r = soccer_weekly_refresh(max_rating_drift=max_drift)
    for c in r.get("checks", []):
        console.print(f"  [dim]{c}[/dim]")
    if r.get("skipped"):
        console.print(f"[cyan]○ Refresh skipped[/cyan] — {r['reason']}")
    elif r["promoted"]:
        prev = f" (was {r['previous']})" if r.get("previous") else ""
        console.print(f"[green]✓ Promoted {r['candidate']}{prev}[/green] — {r['reason']}")
    else:
        console.print(f"[yellow]✗ Candidate {r['candidate']} REJECTED[/yellow] — {r['reason']}")
        console.print("  [dim]Production unchanged. Investigate before re-running.[/dim]")


@cli.command("cup-exam")
@click.option("--key", "key_path", default="exports/cup_answer_key.csv", show_default=True,
              help="Answer key from scripts/extract_cup_key.py.")
@click.option("--detail", is_flag=True,
              help="Diagnostics: per-row Elo/league/bonus inputs + |Δ_HOME| splits "
                   "(pot, tier) + default-Elo teams. No pricing change.")
def cup_exam_cmd(key_path, detail):
    """Cup acceptance exam (spec frozen 2026-09-25): price the answer key's
    FINISHED fixtures with production soccer pricing in REPORT-ONLY mode
    (nothing written) and score vs the books' fair: mean |Δ_HOME| <= 8.0pp,
    <= 13 fixtures over 8pp, EFL round-2 favorite agreement >= 80%."""
    from src.walters.cup_exam import (MAX_MISSING, detail_splits, load_key,
                                      score_exam, tier_of)
    from src.walters.training import _generate_predictions_soccer

    key = load_key(key_path)
    print(f"cup-exam · key {key_path} · {len(key)} rows")
    ids = [k["match_id"] for k in key]
    key_comp = {k["match_id"]: k["comp"] for k in key}
    with session_scope() as s:
        found = s.execute(
            select(Match.id, Match.season, Competition.code)
            .join(Competition, Match.competition_id == Competition.id)
            .where(Match.id.in_(ids))
        ).all()
    # Exact match_id join; a comp disagreement is drift, not a match.
    known = {mid for mid, _, code in found if code == key_comp[mid]}
    groups = sorted({(code, season) for mid, season, code in found if mid in known})

    priced: dict[int, dict] = {}
    versions = set()
    for code, season in groups:
        rows = _generate_predictions_soccer(code, season, include_finished=True)
        print(f"  priced {code} {season}: {len(rows)} fixtures (report-only)")
        for r in rows:
            versions.add(r["model_version"])
            if r["match_id"] in known:
                priced[r["match_id"]] = r
    print(f"  model version(s): {', '.join(sorted(versions)) or '—'}")

    res = score_exam(key, priced, known)

    for m in res.missing:
        print(f"  {m['why']}: match_id={m['match_id']} {m['date']} {m['comp']} "
              f"{m['home']} v {m['away']}")

    hdr = f"{'date':<10} {'comp':<4} {'stage':<18} {'home':<22} {'away':<22} " \
          f"{'fair_H':>6} {'model_H':>7} {'delta_pp':>8}  flag"
    print("\n" + hdr + "\n" + "-" * len(hdr))
    for r in res.rows:
        print(f"{r['date']:<10} {r['comp']:<4} {r['stage'][:18]:<18} {r['home'][:22]:<22} "
              f"{r['away'][:22]:<22} {r['fair_H']:>6.3f} {r['model_H']:>7.3f} "
              f"{r['delta_pp']:>+8.1f}  {r['flag']}")

    fmt = lambda v: "—" if v is None else f"{v:.2f}pp"
    print("\nSUMMARY")
    print(f"  n scored                {res.n_scored}  (missing {len(res.missing)}; "
          f"> {MAX_MISSING} = INVALID)")
    print(f"  mean |Δ_HOME|           {fmt(res.mae_home_pp)}  (bar <= 8.00pp) "
          f"{'ok' if res.mae_pass else 'MISS'}")
    print(f"  mean |Δ| all-outcomes   {fmt(res.mae_all_pp)}")
    print(f"  count >8pp              {res.n_over}  (bar <= 13) "
          f"{'ok' if res.over_pass else 'MISS'}")
    if res.worst:
        w = res.worst
        print(f"  worst row               {w['date']} {w['comp']} {w['home']} v {w['away']} "
              f"Δ_HOME {w['delta_pp']:+.1f}pp")
    print(f"  EFL stages seen         {res.efl_stages_seen or '—'}")
    share = "—" if res.sign_share is None else f"{res.sign_share:.0%}"
    print(f"  sign check ({res.sign_selector}): {res.sign_agree}/{res.sign_n} "
          f"favorites agree = {share}  (pass >= 80%; < 50% = inversion) "
          f"{'ok' if res.sign_pass else 'MISS'}")
    if detail:
        _print_cup_exam_detail(res, detail_splits(res), tier_of)

    print(f"\nVERDICT: {res.verdict}")
    # Amended semantics (architect, 2026-09-25): necessary-not-sufficient.
    print("  (exam is necessary-not-sufficient: FAIL is damning; PASS certifies "
          "no gross cup-path defect only, NOT out-of-sample accuracy — pricing "
          "sees same-season results. The sign check is the decisive organ.)")


def _print_cup_exam_detail(res, splits, tier_of):
    """cup-exam --detail block. `*` marks a default input: league Elo at the
    starting rating (team not in the trained pot), or a bonus from a league
    code missing from LEAGUE_ELO_BONUS (DEFAULT_LEAGUE_BONUS)."""
    from src.models.league_strength import LEAGUE_ELO_BONUS

    def elo(r, side):
        v = r.get(f"{side}_elo")
        star = "*" if not r.get(f"{side}_in_pot") else " "
        return "—" if v is None else f"{v:.0f}{star}"

    def lg(r, side):
        return r.get(f"{side}_league") or "—"

    def bonus(r, side):
        v = r.get(f"{side}_league_bonus")
        code = r.get(f"{side}_league")
        star = " " if code and code.upper() in LEAGUE_ELO_BONUS else "*"
        return "—" if v is None else f"{v:+.0f}{star}"

    hdr = (f"{'date':<10} {'home':<20} {'away':<20} {'delta_pp':>8} "
           f"{'home_elo':>8} {'away_elo':>8} {'home_lg':<7} {'away_lg':<7} "
           f"{'home_bon':>8} {'away_bon':>8}  tier")
    print("\nDETAIL  (elo = effective cup Elo: 0.7·league + 0.3·cup + bonus; "
          "* = default input)")
    print(hdr + "\n" + "-" * len(hdr))
    for r in res.rows:
        print(f"{r['date']:<10} {r['home'][:20]:<20} {r['away'][:20]:<20} "
              f"{r['delta_pp']:>+8.1f} {elo(r, 'home'):>8} {elo(r, 'away'):>8} "
              f"{lg(r, 'home'):<7} {lg(r, 'away'):<7} "
              f"{bonus(r, 'home'):>8} {bonus(r, 'away'):>8}  {tier_of(r)}")

    fmt = lambda v: "—" if v is None else f"{v:.2f}pp"
    print("\nDETAIL SPLITS  (mean |Δ_HOME|)")
    for name, (n, m) in splits["pot"].items():
        print(f"  {name:<24} n={n:<3} {fmt(m)}")
    for name, (n, m) in splits["tier"].items():
        print(f"  {name:<24} n={n:<3} {fmt(m)}")
    teams = splits["default_elo_teams"]
    print(f"  teams at exactly-default Elo: {len(teams)}"
          + (f"  ({', '.join(teams)})" if teams else ""))

    # Strength-fit receipts (architect hypothesis check 2026-09-25): where the
    # Poisson attack/defense behind each row came from.
    from src.walters.cup_exam import fit_summary

    def st(r, side):
        n = r.get(f"{side}_fit_n")
        if n is None:
            return "—"
        src = "P" if r.get(f"{side}_strengths_source") == "promoted_default" else ""
        return f"n={n}{src} a{r[f'{side}_attack']:.2f} d{r[f'{side}_defense']:.2f}"

    hdr = (f"{'date':<10} {'home':<20} {'away':<20} {'delta_pp':>8}  "
           f"{'home strengths':<22} {'away strengths':<22} self pool")
    print("\nSTRENGTHS  (n = team's matches in the fit pool; a/d = attack/defense "
          "after n/(n+5) shrinkage; P = promoted-default prior; self = fixture "
          "is inside its own fit)")
    print(hdr + "\n" + "-" * len(hdr))
    for r in res.rows:
        print(f"{r['date']:<10} {r['home'][:20]:<20} {r['away'][:20]:<20} "
              f"{r['delta_pp']:>+8.1f}  {st(r, 'home'):<22} {st(r, 'away'):<22} "
              f"{'Y' if r.get('self_in_fit') else 'n':<4} {r.get('fit_pool_n', '—')}"
              f"{'b' if r.get('strengths_backfilled') else ''}")
    fs = fit_summary(res)
    print("\nSTRENGTH-FIT SUMMARY")
    print(f"  pools (comp, n matches, backfilled): {fs['pools']}")
    print(f"  per-team fit n over {fs['teams']} teams: {fs['team_fit_n_buckets']}")
    print(f"  fixtures inside their own fit: {fs['self_in_fit']}/{len(res.rows)}")
    print(f"  promoted-default sides: {fs['promoted_default_sides']} · "
          f"elo_goal_coeff: {fs['elo_goal_coeff']}")
@cli.command("nhl-backtest")
@click.option("--season-start", "season_starts", multiple=True, metavar="SEASON=YYYY-MM-DD",
              help="Override a regular-season opener (preseason cut), e.g. 2024=2024-10-08.")
def nhl_backtest_cmd(season_starts):
    """NHL Phase 2 gate (frozen 2026-09-25): train 2024, test 2025, preseason
    excluded; prints the stream receipts, both baselines and — once a
    candidate exists — the verdict. Writes nothing."""
    from datetime import date as _date
    from src.walters import nhl_backtest as nb

    starts = dict(nb.SEASON_STARTS)
    for spec in season_starts:
        season, _, d = spec.partition("=")
        starts[season.strip()] = _date.fromisoformat(d.strip())
    stream = nb.build_stream(nb.load_games(), starts)
    base = nb.baselines(stream)
    if base.verdict:  # INVALID stream: nothing to score a candidate against
        nb.report(stream, base)
        return
    from src.models.nhl_elo import NHLEloConfig, NHLEloV1, home_advantage_from_rate
    cfg = NHLEloConfig(home_advantage=home_advantage_from_rate(base.home_rate))
    model = NHLEloV1(cfg)
    result = nb.run_gate(stream, model)
    nb.report(stream, result, model_name=(
        f"{model.name} (k={cfg.k_factor}, mov_base={cfg.mov_base}, "
        f"regression={cfg.season_regression}, home_adv={cfg.home_advantage:.1f} "
        f"from {nb.TRAIN_SEASON} home rate)"))


@cli.command("kalshi-probe")
@click.option("--keywords", default="epl,premier league,soccer,football",
              help="Comma-separated keywords to match against series title/tags/ticker.")
@click.option("--series", "series_ticker", default=None,
              help="Probe this exact series ticker directly (skips discovery — one API call).")
@click.option("--grep", "title_grep", default=None,
              help="Only dump markets whose title contains this (case-insensitive) substring.")
@click.option("--markets", "show_markets", default=2, help="How many raw sample markets to dump per matching series (0 = series list only).")
def kalshi_probe_cmd(keywords, series_ticker, title_grep, show_markets):
    """S3 recon: discover Kalshi series by keyword and dump RAW sample markets.

    Payload-first discipline: every MLB Kalshi surprise (string dollars,
    yes_sub_title naming, G1/G2 suffixes, in-play markets) lived in payload
    shape. Run this BEFORE building any new sport's matcher. Read-only; no DB
    writes."""
    import json as _json
    from src.adapters.kalshi import KalshiAdapter
    ad = KalshiAdapter()
    try:
        st = ad.status()
        console.print(f"[dim]exchange status: trading_active={st.get('trading_active')}[/dim]")
    except Exception as e:
        console.print(f"[yellow]status check failed: {e}[/yellow]")
    if series_ticker:
        kws = [series_ticker]
        series = [{"ticker": series_ticker, "title": "(direct)", "category": "", "tags": []}]
    else:
        kws = [k.strip() for k in keywords.split(",") if k.strip()]
        series = ad.find_series(kws)
    if not series:
        console.print(f"[yellow]No series matched {kws}. Kalshi may not have "
                      "opened these markets yet — re-probe closer to the event, "
                      "or broaden keywords.[/yellow]")
        return
    console.print(f"[green]✓ {len(series)} series matched {kws}[/green]")
    for sr in series:
        console.print(f"\n[bold]{sr.get('ticker')}[/bold] — {sr.get('title')} "
                      f"[dim](category={sr.get('category')}, tags={sr.get('tags')})[/dim]")
        if show_markets <= 0:
            continue
        try:
            mkts = ad.open_markets_for_series(sr.get("ticker"))
        except Exception as e:
            console.print(f"  [yellow]market fetch failed: {e}[/yellow]")
            continue
        if title_grep:
            g = title_grep.lower()
            mkts = [m for m in mkts if g in (m.get("title") or "").lower()
                    or g in (m.get("ticker") or "").lower()]
        console.print(f"  [dim]{len(mkts)} open markets"
                      + (f" matching {title_grep!r}" if title_grep else "")
                      + f"; showing {min(show_markets, len(mkts))} raw:[/dim]")
        for mk in mkts[:show_markets]:
            console.print(_json.dumps(mk, indent=2, default=str))


@cli.command("sync-kalshi-soccer")
@click.option("--competition", "competition_code", default="PL")
@click.option("--max-spread", default=0.10, help="Skip legs with ask-bid wider than this (unliquid = noise, not a price).")
def sync_kalshi_soccer_cmd(competition_code, max_spread):
    """Pull Kalshi soccer game markets (Home/Away/Tie legs) as pre-game
    OddsSnapshots. Coverage source per the 2026-08-17 Step-1 verdict —
    disagreement columns are instrumentation only. Run with the Friday chain
    and again pre-kickoff Saturday (spreads tighten as matches near)."""
    from src.ingestion.kalshi_sync import sync_kalshi_soccer
    r = sync_kalshi_soccer(competition_code=competition_code, max_spread=max_spread,
                           progress=lambda m: console.print(f"  [dim]{m}[/dim]"))
    if not r.get("ok"):
        console.print(f"[yellow]Kalshi soccer sync: {r.get('reason')}[/yellow]")
        return
    console.print(f"[green]✓ Kalshi soccer: {r['stored']} prices stored[/green]")
    console.print(f"  [dim]series {r['series']} · {r['markets']} markets · matched {r['matched']} · "
                  f"unmatched {r['unmatched']} (ambiguous {r['ambiguous']}) · "
                  f"in-play {r['in_play']} · wide-spread skipped {r['wide_spread']}[/dim]")


@cli.command("set-soccer-config")
@click.option("--field", required=True,
              help="Soccer PoissonConfig field (e.g. dixon_coles_rho, elo_goal_coeff).")
@click.option("--value", required=True)
@click.option("--yes", is_flag=True, help="Skip confirmation.")
def set_soccer_config_cmd(field, value, yes):
    """
    Edit the production SOCCER model's frozen Poisson config (params['poisson']).
    Audited + reversible, like set-config for MLB. Whitelisted fields with sane
    ranges. Currently the key one is dixon_coles_rho (the draw correction).
    """
    import copy
    from sqlalchemy import select
    from src.db.schema import ModelVersion
    from src.walters.training import _current_production_version, _family_for

    EDITABLE = {
        "dixon_coles_rho": (float, -0.30, 0.0),
        "elo_goal_coeff": (float, 0.0, 0.02),
        "default_total_line": (float, 1.5, 4.5),
        "promoted_attack_prior": (float, 0.60, 1.00),
        "promoted_defense_prior": (float, 1.00, 1.40),
    }
    if field not in EDITABLE:
        console.print(f"[red]'{field}' not editable. Options: {', '.join(EDITABLE)}[/red]")
        return
    typ, lo, hi = EDITABLE[field]
    try:
        coerced = typ(value)
    except (TypeError, ValueError):
        console.print(f"[red]{field} must be {typ.__name__}.[/red]")
        return
    if not (lo <= coerced <= hi):
        console.print(f"[red]{field}={coerced} outside sane range [{lo}, {hi}]. Refusing.[/red]")
        return

    with session_scope() as s:
        prod_version = _current_production_version(s, Sport.SOCCER)
        if prod_version is None:
            console.print("[red]No production soccer model found. Train one first.[/red]")
            return
        prod = s.execute(
            select(ModelVersion).where(
                ModelVersion.sport == Sport.SOCCER,
                ModelVersion.model_family == _family_for(Sport.SOCCER),
                ModelVersion.version == prod_version,
            )
        ).scalar_one_or_none()
        if prod is None:
            console.print("[red]Production soccer model row not found.[/red]")
            return
        params = copy.deepcopy(prod.parameters or {})
        poisson = params.get("poisson", {})
        old = poisson.get(field, "(default)")
        console.print(f"\nProduction soccer model: {prod.model_family} {prod.version}")
        console.print(f"  {field}: {old} → {coerced}")
        console.print(f"  [dim](Reversible: re-run with the old value.)[/dim]")
        if not yes:
            if not click.confirm("Apply this change to the production soccer model?"):
                console.print("[yellow]No change made.[/yellow]")
                return
        poisson[field] = coerced
        params["poisson"] = poisson
        edits = params.get("manual_config_edits", [])
        edits.append({"ts": datetime.utcnow().isoformat(), "field": f"poisson.{field}",
                      "from": old, "to": coerced})
        params["manual_config_edits"] = edits
        prod.parameters = params
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(prod, "parameters")
        s.commit()
        console.print(f"[green]✓ Updated soccer {prod.version}: {field} = {coerced}.[/green]")
        console.print("  [dim]Takes effect on the next predict run.[/dim]")


@cli.command("scenarios")
@click.option("--date", "date_str", default=None, help="YYYY-MM-DD (default: today).")
def scenarios_cmd(date_str):
    """
    Honest what-if scenario layer: decompose each game's prediction into real
    slices of the model's own distribution (favorite-holds / upset / one-run /
    blowout / team-explosion) with the MODEL'S probabilities, plus tracked
    context flags shown WITHOUT fabricated weights. Reads predictions; does not
    alter them.
    """
    import json as _json
    from datetime import datetime, timezone, timedelta
    from src.walters.scenarios import build_scenarios
    from src.walters.export import export_predictions
    from src.db.schema import Sport, MatchStatus

    target = date_str or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    day = datetime.strptime(target, "%Y-%m-%d")
    # Match export CLI: treat a slate-day as 08:00 UTC → 08:00 UTC next day, so
    # West Coast late games stay grouped with the same calendar day.
    start = day.replace(hour=8, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    raw = export_predictions(
        sport=Sport.MLB,
        start_date=start,
        end_date=end,
        competition_code="MLB",
        statuses=[MatchStatus.SCHEDULED],
        output_format="json",
    )
    payload = _json.loads(raw)
    preds = payload.get("predictions") or []
    if not preds:
        console.print(f"[yellow]No scheduled games for {target}.[/yellow]")
        return

    console.print(f"\n[bold]Scenario decomposition — {target}[/bold]")
    console.print("[dim]Distribution scenarios = the model's OWN probabilities (real slices "
                  "of its score distribution). Context flags = tracked conditions, NO "
                  "fabricated probability. Nothing here alters the prediction.[/dim]\n")

    for p in preds:
        sc = build_scenarios(p.get("prediction") or {}, p.get("unused_context"))
        console.print(f"[bold cyan]{p['away_team']} @ {p['home_team']}[/bold cyan]")
        for s in sc["distribution_scenarios"]:
            prob = s["probability"]
            bar = "█" * int(round((prob or 0) * 20))
            console.print(f"   {prob*100:5.1f}%  {s['name']:<34s} [dim]{bar}[/dim]")
            console.print(f"          [dim]{s['basis']}[/dim]")
        if sc["context_flags"]:
            console.print("   [yellow]context (no validated effect):[/yellow]")
            for f in sc["context_flags"]:
                console.print(f"     • {f['condition']}")
                console.print(f"       [dim]{f['status']}[/dim]")
        console.print("")


@cli.command("calibration-fine")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--days", default=30, help="Look back this many days (default 30). "
              "Ignored if --since is given.")
@click.option("--since", default=None, help="Explicit start date YYYY-MM-DD "
              "(overrides --days). Use an early date for the full-history read.")
@click.option("--width", default=0.01, help="Band width, e.g. 0.01 for 1-point "
              "bands (default), 0.02 for 2-point.")
@click.option("--actionable-only", is_flag=True, default=False,
              help="Only picks ≥53% (games that claimed an edge).")
def calibration_fine_cmd(sport, days, since, width, actionable_only):
    """
    Fine-grained calibration with configurable band width + honest error bars.
    Fine bands give resolution; each shows n and a 95% interval so thin bands
    read as directional. Coarse (5pp) bands + a monotonic-trend check give the
    statistically honest verdict. Suggested: run once with --days 30 (recent)
    and once with --since 2025-03-01 (full history) — the contrast is telling.
    """
    from datetime import datetime, timedelta
    from src.walters.fine_calibration import fine_calibration
    from rich.table import Table

    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since)
        label = f"since {since}"
    else:
        since_dt = datetime.utcnow() - timedelta(days=days)
        label = f"last {days} days"

    res = fine_calibration(since=since_dt, width=width,
                           actionable_min=0.53 if actionable_only else None)
    if res["n_total"] == 0:
        console.print(f"[yellow]No graded predictions in window ({label}).[/yellow]")
        return

    console.print(f"\n[bold]Fine calibration — MLB ({label}, {int(width*100)}-point bands)[/bold]")
    console.print(f"  {res['n_total']} graded predictions"
                  f"{' (actionable ≥53%)' if actionable_only else ''}\n")

    # --- fine bands ---
    t = Table(title=f"{int(width*100)}-point bands (resolution view)", show_header=True,
              header_style="bold")
    for c in ("Band", "n", "predicted", "actual", "gap", "95% interval"):
        t.add_column(c, justify="left" if c == "Band" else "right")
    for r in res["fine"]:
        # gap is only meaningful if the CI doesn't straddle predicted by a mile;
        # color only when the band is reasonably sampled AND gap is real
        thin = r["n"] < 20
        gaptxt = f"{r['gap']*100:+.1f}pp"
        if not thin and (r["ci_hi"] < r["predicted"] or r["ci_lo"] > r["predicted"]):
            gaptxt = f"[yellow]{r['gap']*100:+.1f}pp[/yellow]"  # CI excludes predicted
        ntxt = f"[dim]{r['n']}[/dim]" if thin else str(r["n"])
        t.add_row(f"{r['lo']*100:.0f}-{r['hi']*100:.0f}%", ntxt,
                  f"{r['predicted']*100:.1f}%", f"{r['actual']*100:.1f}%",
                  gaptxt, f"{r['ci_lo']*100:.0f}–{r['ci_hi']*100:.0f}%")
    console.print(t)
    console.print("[dim]Dimmed n = thin band (<20 games), wide interval — read as directional "
                  "only. Yellow gap = 95% interval excludes the predicted rate (a real "
                  "miss at this sample), rare on fine bands.[/dim]\n")

    # --- coarse bands (the honest read) ---
    t2 = Table(title="5-point bands (statistically honest read)", show_header=True,
               header_style="bold")
    for c in ("Band", "n", "predicted", "actual", "gap", "95% interval"):
        t2.add_column(c, justify="left" if c == "Band" else "right")
    for r in res["coarse"]:
        excludes = (r["ci_hi"] < r["predicted"] or r["ci_lo"] > r["predicted"])
        gaptxt = f"[yellow]{r['gap']*100:+.1f}pp[/yellow]" if (excludes and r["n"] >= 25) else f"{r['gap']*100:+.1f}pp"
        t2.add_row(f"{r['lo']*100:.0f}-{r['hi']*100:.0f}%", str(r["n"]),
                   f"{r['predicted']*100:.1f}%", f"{r['actual']*100:.1f}%",
                   gaptxt, f"{r['ci_lo']*100:.0f}–{r['ci_hi']*100:.0f}%")
    console.print(t2)

    if res["monotonic"] is True:
        console.print("[green]→ Actual win rate rises with predicted across well-sampled "
                      "bands (monotonic). Calibration trend is sound — individual fine bands "
                      "that look off are sampling noise.[/green]")
    elif res["monotonic"] is False:
        console.print("[yellow]→ Actual win rate does NOT rise monotonically with predicted "
                      "across well-sampled bands. Could be a real calibration wobble or still "
                      "noise — check the n's and re-run on the full history to confirm.[/yellow]")
    else:
        console.print("[dim]→ Not enough well-sampled coarse bands for a trend verdict "
                      "(widen the window or use --since on the full history).[/dim]")
    console.print("[dim]Recency vs truth: --days 30 shows RECENT calibration; "
                  "--since 2025-03-01 uses the full ~3,900-game history for the tight read. "
                  "Run both — the contrast tells you if anything recent is drift vs noise.[/dim]\n")


@cli.command("bullpen-effectiveness")
@click.option("--window", default=30, help="Trailing days (default 30).")
@click.option("--sort", type=click.Choice(["era", "whip", "k9"]), default="era")
def bullpen_effectiveness_cmd(window, sort):
    """
    TRACKING: team bullpen effectiveness (reliever-only ERA/WHIP/K-9) over a
    trailing window, from captured per-appearance effectiveness. Distinct from
    availability. NOT in the model — tracked to test whether it beats what team
    RA already carries. Needs effectiveness-capturing appearances (run
    sync-appearances after this ships to populate the new fields).
    """
    from datetime import datetime, timezone
    from src.walters.bullpen_effectiveness import all_teams_bullpen_effectiveness
    from src.db.schema import Team, Sport
    from rich.table import Table

    now = datetime.now(timezone.utc)
    with session_scope() as s:
        name_by_sid = {}
        for t in s.execute(select(Team).where(Team.sport == Sport.MLB)).scalars():
            sid = (t.external_ids or {}).get("mlb_stats_api")
            if sid:
                name_by_sid[str(sid)] = t.name
        eff = all_teams_bullpen_effectiveness(s, now, window_days=window)

    if not eff:
        console.print("[yellow]No bullpen effectiveness data yet. Run "
                      "`sync-appearances --recent` after this update to capture the "
                      "new per-reliever ER/H/BB/K fields, then retry.[/yellow]")
        return

    key = {"era": "bullpen_era", "whip": "whip", "k9": "k_per_9"}[sort]
    reverse = (sort == "k9")  # higher K/9 is better
    rows = [(name_by_sid.get(tid, tid), v) for tid, v in eff.items()]
    rows = [r for r in rows if r[1].get(key) is not None]
    rows.sort(key=lambda r: r[1][key], reverse=reverse)

    t = Table(title=f"Team bullpen effectiveness — last {window}d (reliever-only)",
              show_header=True, header_style="bold")
    for c in ("Team", "Bullpen ERA", "WHIP", "K/9", "IP", "App"):
        t.add_column(c, justify="left" if c == "Team" else "right")
    for name, v in rows:
        t.add_row(name[:24],
                  f"{v['bullpen_era']:.2f}" if v.get("bullpen_era") is not None else "—",
                  f"{v['whip']:.2f}" if v.get("whip") is not None else "—",
                  f"{v['k_per_9']:.1f}" if v.get("k_per_9") is not None else "—",
                  f"{v['innings']:.1f}", str(v["appearances"]))
    console.print(t)
    console.print("[dim]Tracking only — NOT a model input. Bullpen quality is partially "
                  "already in team RA; this is tracked to test (Stage-1) whether recent "
                  "bullpen form adds signal BEYOND what RA carries.[/dim]")


@cli.command("totals-calibration")
@click.option("--since", default=None,
              help="YYYY-MM-DD — only predictions computed on/after this date. "
                   "Use 2026-07-20 to isolate post run_shrink_frac=0.35 games.")
def totals_calibration_cmd(since):
    """
    Totals accuracy analysis — the calibration work we did for SIDES but never
    for the totals number. Three reads: projected-vs-actual bias, over/under
    probability calibration, and a run-environment cut. Measures ACCURACY of the
    total (does it beat the market is a separate CLV question). Read-only.
    --since isolates a config era (e.g. post-0.35-shrink) so the pre-change bias
    doesn't dilute the read.
    """
    from datetime import datetime
    from src.walters.totals_calibration import totals_calibration
    from rich.table import Table

    since_dt = datetime.fromisoformat(since) if since else None
    r = totals_calibration(since=since_dt)
    if not r:
        console.print("[yellow]No graded predictions with a real market total"
                      f"{' in that window' if since else ''}.[/yellow]")
        return
    if since:
        console.print(f"[dim]Filtered to predictions computed on/after {since} "
                      f"({r['n']} games).[/dim]")

    console.print(f"\n[bold]Totals calibration — MLB[/bold]  ({r['n']} games with a market line)\n")

    # 1. bias
    me, se, mae = r["mean_err"], r["se_err"], r["mae"]
    bias_flag = ""
    if se and abs(me) > 2 * se:
        bias_flag = "  [yellow]← systematic bias (|mean err| > 2·SE)[/yellow]"
    console.print("[bold]1. Projected total vs actual[/bold]")
    console.print(f"   mean error (actual − projected): {me:+.2f} runs "
                  f"(±{se:.2f} SE){bias_flag}")
    console.print(f"   mean ABSOLUTE error: {mae:.2f} runs per game "
                  f"[dim](typical miss size; ~3 is normal for MLB totals)[/dim]")
    t1 = Table(show_header=True, header_style="bold")
    for c in ("Projected band", "n", "mean error", "±SE"):
        t1.add_column(c, justify="left" if c == "Projected band" else "right")
    for k, nb, m, se_b in r["proj_rows"]:
        flag = "yellow" if (se_b and abs(m) > 2 * se_b) else ""
        mtxt = f"[{flag}]{m:+.2f}[/{flag}]" if flag else f"{m:+.2f}"
        t1.add_row(k, str(nb), mtxt, f"{se_b:.2f}" if se_b else "—")
    console.print(t1)
    console.print("[dim]Negative = model projected HIGHER than actual (overprojects runs); "
                  "positive = underprojects. A gradient across bands = level-dependent bias.[/dim]\n")

    # 2. over/under prob calibration
    console.print("[bold]2. Over/under probability calibration[/bold]")
    if r["over_rate"] is not None:
        console.print(f"   overall over-rate vs line: {r['over_rate']*100:.1f}% "
                      f"(of {r['n_decided']} decided) "
                      f"[dim](≈50% expected if the line-relative read is unbiased)[/dim]")
    t2 = Table(show_header=True, header_style="bold")
    for c in ("Model over-prob", "n", "predicted", "actual over%", "±SE"):
        t2.add_column(c, justify="left" if c == "Model over-prob" else "right")
    for band, nb, pred_p, act_p, se_b in r["ou_rows"]:
        flag = "yellow" if (se_b and nb >= 20 and abs(act_p - pred_p) > 2 * se_b) else ""
        gaptxt = f"[{flag}]{act_p*100:.0f}%[/{flag}]" if flag else f"{act_p*100:.0f}%"
        ntxt = f"[dim]{nb}[/dim]" if nb < 20 else str(nb)
        t2.add_row(band, ntxt, f"{pred_p*100:.0f}%", gaptxt, f"{se_b*100:.0f}%" if se_b else "—")
    console.print(t2)
    console.print("[dim]When the model says X% over, does the over hit X%? Off-diagonal = "
                  "distribution-shape (dispersion) miscalibration. Thin bands (<20) dimmed.[/dim]\n")

    # 3. run-environment
    console.print("[bold]3. Bias by actual run environment[/bold]")
    t3 = Table(show_header=True, header_style="bold")
    for c in ("Environment", "n", "mean error", "±SE"):
        t3.add_column(c, justify="left" if c == "Environment" else "right")
    for k, nb, m, se_b in r["env_rows"]:
        flag = "yellow" if (se_b and abs(m) > 2 * se_b) else ""
        mtxt = f"[{flag}]{m:+.2f}[/{flag}]" if flag else f"{m:+.2f}"
        t3.add_row(k, str(nb), mtxt, f"{se_b:.2f}" if se_b else "—")
    console.print(t3)
    console.print("[dim]Expected: the model can't project a blowup, so ≥13 will show large "
                  "positive error and ≤6 large negative — that's inherent to point projection, "
                  "NOT a fixable bias. Look instead at whether NORMAL (7-9) games are "
                  "centered — that's the honest calibration signal.[/dim]\n")

    # 4. residual by market line
    console.print("[bold]4. Residual by market total line[/bold]")
    console.print("[dim]Bucketed by the MARKET's line (not the model's projection). "
                  "'market resid' = actual − line (did games at this line level go over/under "
                  "the market). 'model resid' = actual − projection (model's own error there). "
                  "Where the two DIVERGE is where the model reads a line level differently than "
                  "the market — the betting-relevant cut.[/dim]")
    t4 = Table(show_header=True, header_style="bold")
    for c in ("Market line band", "n", "market resid", "±SE", "model resid", "±SE",
              "model−market", "over% vs line", "flag"):
        t4.add_column(c, justify="left" if c == "Market line band" else "right")
    for k, nb, mkt_m, mkt_se, mdl_m, mdl_se, mm_m, over_b, is_cand in r["line_rows"]:
        mkt_flag = "yellow" if (mkt_se and abs(mkt_m) > 2 * mkt_se) else ""
        mkt_txt = f"[{mkt_flag}]{mkt_m:+.2f}[/{mkt_flag}]" if mkt_flag else f"{mkt_m:+.2f}"
        cand_txt = "[green]candidate[/green]" if is_cand else ""
        t4.add_row(k, str(nb), mkt_txt, f"{mkt_se:.2f}" if mkt_se else "—",
                   f"{mdl_m:+.2f}", f"{mdl_se:.2f}" if mdl_se else "—",
                   f"{mm_m:+.2f}", f"{over_b*100:.0f}%" if over_b is not None else "—",
                   cand_txt)
    console.print(t4)
    console.print("[dim]market resid = actual − line; model resid = actual − projection; "
                  "model−market = projection − line (the model's DISAGREEMENT with the line). "
                  "A band is a 'candidate' ONLY if all five hold: |market resid|>0.75, "
                  "|model resid|<0.40, |model−market|>0.50, same direction, n≥150.[/dim]")

    # the automatic verdict — the guardrail against chasing noise
    mkt_min, mdl_max, diff_min, n_min = r["flag_thresholds"]
    if r["any_candidate"]:
        console.print("[bold green]⚑ Candidate structural market bias detected.[/bold green] "
                      "[dim]A line band met all five conditions. This is a TRACK-forward "
                      "candidate, not a confirmed edge — re-run as sample grows and confirm it "
                      "persists (same band, same direction, tightening error) before trusting "
                      "it. Beating a market line is an extraordinary claim; one snapshot isn't "
                      "proof.[/dim]")
    else:
        console.print("[bold]No evidence of persistent market-level edge.[/bold] "
                      f"[dim](No band met all of: |market resid|>{mkt_min}, "
                      f"|model resid|<{mdl_max}, |model−market|>{diff_min}, same direction, "
                      f"n≥{n_min}. This is the expected, honest default — it prevents chasing "
                      "noise. Most bands won't reach n≥{n_min} for a while yet.)[/dim]")
    console.print("")

    console.print("[dim]This measures ACCURACY, not market edge. If the number is biased "
                  "here, that's a fixable model calibration (unlike sides, which were already "
                  "clean). If it's centered but still loses to the line, that's totals-market "
                  "efficiency — a separate CLV question.[/dim]\n")


@cli.command("card")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--date", default=None, help="YYYY-MM-DD (default: today).")
def card_cmd(sport: str, date: str):
    """
    Assemble a structured daily card: a confidence ladder + per-game fact blocks
    + honest flags. This is a FACT ASSEMBLER, not a rationale generator — it
    surfaces the numbers the model already computes and tags cautions by
    explicit rules. It deliberately does NOT generate prose 'edges' for market
    disagreements: until CLV proves the model beats the close, a disagreement is
    flagged as CAUTION, not opportunity. Interpretation stays human-in-the-loop.
    Read-only.
    """
    from src.walters.card import build_card
    target = datetime.fromisoformat(date).date() if date else None
    card = build_card(target_date=target)
    day = card["date"]
    games = card["games"]

    if not games:
        console.print(f"[yellow]No scheduled games found for {day}.[/yellow]")
        return


    # ---- Confidence ladder ----
    from rich.table import Table
    console.print(f"\n[bold]═══ CARD — {day} ({len(games)} games) ═══[/bold]")
    console.print("[dim]Fact assembler. Flags are deterministic cautions, NOT bet advice. "
                  "Market disagreement is flagged as caution, not edge, until CLV proves "
                  "otherwise. Interpretation is yours.[/dim]\n")
    lad = Table(show_header=True, header_style="bold", title="Confidence ladder")
    for c in ("#", "Pick", "Model", "Mkt edge", "Tier", "Top flag"):
        lad.add_column(c, justify="right" if c in ("#", "Model", "Mkt edge") else "left")
    for i, g in enumerate(games, 1):
        edge = f"{g['mkt_edge']:+.1f}pp" if g["mkt_edge"] is not None else "—"
        topflag = next((f"⚠ {m}" for lvl, m in g["flags"] if lvl == "caution"), "")
        if not topflag:
            topflag = next((m for lvl, m in g["flags"] if lvl == "note"), "clean")
        lad.add_row(str(i), g["pick"][:20], f"{g['prob']*100:.1f}%", edge,
                    g["tier"] or "?", topflag)
    console.print(lad)

    # ---- Per-game fact blocks ----
    console.print("\n[bold]Per-game facts[/bold]")
    for i, g in enumerate(games, 1):
        fb = g["fb"]
        console.print(f"\n[bold]{i}. {g['match']}[/bold]  → pick [bold]{g['pick']}[/bold] "
                      f"{g['prob']*100:.1f}% ({g['tier']})")
        edge = f"{g['mkt_edge']:+.1f}pp" if g["mkt_edge"] is not None else "n/a"
        console.print(f"   proj runs: {g['proj_home']:.2f} home / {g['proj_away']:.2f} away  |  "
                      f"market edge on pick: {edge}")
        hp = fb.get("home_pitcher", "?"); ap = fb.get("away_pitcher", "?")
        console.print(f"   SP: {hp} (ERA {fb.get('home_pitcher_era','?')}) vs "
                      f"{ap} (ERA {fb.get('away_pitcher_era','?')})")
        console.print(f"   bullpen ERA: {fb.get('home_bullpen_era','?')} home / "
                      f"{fb.get('away_bullpen_era','?')} away  |  swing {g['bp_swing'] or 0:.2f}")
        console.print(f"   recent RS/RA: home {fb.get('home_rs_recent','?')}/{fb.get('home_ra_recent','?')}  "
                      f"away {fb.get('away_rs_recent','?')}/{fb.get('away_ra_recent','?')}")
        if g["totals_available"]:
            gap_str = ""
            if g.get("total_gap") is not None:
                edge_tag = "[green]bettable edge[/green]" if g["bettable_total_edge"] \
                    else "[dim]thin (lean only)[/dim]"
                gap_str = (f"  | model {g['model_total']:.2f} vs mkt {g['market_total']} "
                           f"= gap {g['total_gap']:+.2f} {edge_tag}")
            console.print(f"   total: line {g['ou_line']}  over {g['over_prob']*100:.0f}%  "
                          f"stronger: {g['stronger']}{gap_str}")
        else:
            console.print(f"   total: [dim]unavailable (no market line)[/dim]")
        for lvl, msg in g["flags"]:
            tag = "[yellow]⚠[/yellow]" if lvl == "caution" else "[dim]·[/dim]"
            console.print(f"   {tag} {msg}")
        console.print(f"   [bold]→ suitability:[/bold] {g['bet_suitability']}  "
                      f"[bold]recommended:[/bold] {g['recommended_market']}")
    console.print("")


@cli.command("data-freshness")
@click.option("--sport", type=click.Choice(["mlb", "baseball"]), default="mlb")
@click.option("--season", default="2026")
def data_freshness_cmd(sport: str, season: str):
    """
    Diagnose whether the model's INPUTS are current.

    A monotonic rise in holdout log-loss on an unchanged model can mean
    inputs are quietly going stale. This checks the three things MLB
    predictions depend on:
      1. Finished matches — team run profiles are computed live from these,
         so if results aren't being ingested, profiles freeze.
      2. Bullpen stats refreshed_at / recent_refreshed_at.
      3. Pitcher stats refreshed_at.

    Reports the most-recent timestamp and how many rows are stale (older
    than 2 days) for each. Read-only.
    """
    from datetime import timedelta
    from src.db.schema import (
        Match, MatchStatus, Sport, BullpenSeasonStats, PitcherSeasonStats,
    )
    now = datetime.utcnow()
    stale_cut = now - timedelta(days=2)

    console.print(f"\n[bold]Data freshness — {sport.upper()} {season}[/bold]")
    console.print(f"  Now (UTC): {now:%Y-%m-%d %H:%M}\n")

    with session_scope() as s:
        # 1. Most recent finished match (drives team run profiles)
        last_finished = s.execute(
            select(func.max(Match.utc_date)).where(
                Match.sport == Sport.MLB,
                Match.status == MatchStatus.FINISHED,
            )
        ).scalar_one_or_none()
        # Count finished games in the last 3 days
        recent_finished = s.execute(
            select(func.count()).select_from(Match).where(
                Match.sport == Sport.MLB,
                Match.status == MatchStatus.FINISHED,
                Match.utc_date >= now - timedelta(days=3),
            )
        ).scalar_one()

        t = Table(show_header=True, header_style="bold")
        t.add_column("Input")
        t.add_column("Most recent")
        t.add_column("Age")
        t.add_column("Health")

        def age_str(ts):
            if ts is None:
                return "—"
            d = now - ts
            h = d.total_seconds() / 3600
            return f"{h:.0f}h" if h < 48 else f"{d.days}d"

        def health(ts, thresh_h=48):
            if ts is None:
                return "[red]MISSING[/red]"
            h = (now - ts).total_seconds() / 3600
            return "[green]fresh[/green]" if h <= thresh_h else f"[yellow]stale ({h:.0f}h)[/yellow]"

        t.add_row("Last finished match", f"{last_finished:%Y-%m-%d %H:%M}" if last_finished else "—",
                  age_str(last_finished), health(last_finished))

        # 2. Bullpen season + recent
        bp_season = s.execute(select(func.max(BullpenSeasonStats.refreshed_at))
                              .where(BullpenSeasonStats.season == season)).scalar_one_or_none()
        bp_recent = s.execute(select(func.max(BullpenSeasonStats.recent_refreshed_at))
                              .where(BullpenSeasonStats.season == season)).scalar_one_or_none()
        bp_stale = s.execute(select(func.count()).select_from(BullpenSeasonStats).where(
            BullpenSeasonStats.season == season,
            BullpenSeasonStats.refreshed_at < stale_cut)).scalar_one()
        t.add_row("Bullpen (season)", f"{bp_season:%Y-%m-%d %H:%M}" if bp_season else "—",
                  age_str(bp_season), health(bp_season))
        t.add_row("Bullpen (recent form)", f"{bp_recent:%Y-%m-%d %H:%M}" if bp_recent else "—",
                  age_str(bp_recent), health(bp_recent))

        # 3. Pitcher stats
        pit = s.execute(select(func.max(PitcherSeasonStats.refreshed_at))
                        .where(PitcherSeasonStats.season == season)).scalar_one_or_none()
        pit_stale = s.execute(select(func.count()).select_from(PitcherSeasonStats).where(
            PitcherSeasonStats.season == season,
            PitcherSeasonStats.refreshed_at < stale_cut)).scalar_one()
        t.add_row("Pitcher stats", f"{pit:%Y-%m-%d %H:%M}" if pit else "—",
                  age_str(pit), health(pit))

        console.print(t)
        console.print()
        console.print(f"  Finished MLB games ingested in last 3 days: {recent_finished}")
        console.print(f"  Bullpen rows stale (>2d): {bp_stale}/30")
        console.print(f"  Pitcher rows stale (>2d): {pit_stale}")
        console.print()
        # Verdict
        problems = []
        if last_finished and (now - last_finished).total_seconds()/3600 > 48:
            problems.append("finished matches are stale — team run profiles are frozen")
        if recent_finished == 0:
            problems.append("NO finished games ingested in 3 days — sync-matches may be failing")
        if bp_season and (now - bp_season).total_seconds()/3600 > 72:
            problems.append("bullpen season stats stale")
        if bp_recent is None or (bp_recent and (now - bp_recent).total_seconds()/3600 > 72):
            problems.append("bullpen recent-form stale or missing")
        if problems:
            console.print("[yellow]⚠ Possible staleness:[/yellow]")
            for p in problems:
                console.print(f"    - {p}")
        else:
            console.print("[green]✓ All inputs fresh — log-loss drift is NOT from stale inputs.[/green]")
        console.print()


@cli.command("db-tune")
@click.option("--vacuum", is_flag=True, help="Also VACUUM (rewrites the file; run occasionally, not daily).")
def db_tune_cmd(vacuum):
    """One-shot DB health pass (2026-09-20, lag investigation): WAL mode,
    planner statistics, and composite indexes for the per-match
    latest-snapshot pattern. Idempotent; safe mid-season."""
    import sqlite3 as _sq
    import time as _t
    path = "data/sports.db"
    con = _sq.connect(path)
    cur = con.cursor()
    t0 = _t.time()
    probe = ("SELECT COUNT(*) FROM odds o WHERE o.match_id = "
             "(SELECT id FROM matches ORDER BY utc_date DESC LIMIT 1)")
    cur.execute(probe); n = cur.fetchone()[0]
    before = _t.time() - t0
    console.print(f"  probe before: {before*1000:.0f}ms ({n} odds rows on newest match)")
    cur.execute("PRAGMA journal_mode=WAL")
    console.print(f"  journal_mode -> {cur.fetchone()[0]}")
    cur.execute("PRAGMA synchronous=NORMAL")
    for ddl in (
        "CREATE INDEX IF NOT EXISTS ix_odds_match_book_sel ON odds(match_id, bookmaker, selection, captured_at)",
        "CREATE INDEX IF NOT EXISTS ix_snap_match_captured ON odds_snapshots(match_id, captured_at)",
        "CREATE INDEX IF NOT EXISTS ix_pred_match_model ON predictions(match_id, model_version)",
    ):
        cur.execute(ddl)
        console.print(f"  ✓ {ddl.split(' ON ')[0].split('EXISTS ')[1]}")
    cur.execute("ANALYZE")
    console.print("  ✓ ANALYZE (planner statistics built)")
    if vacuum:
        con.commit(); con.isolation_level = None
        cur.execute("VACUUM")
        console.print("  ✓ VACUUM complete")
    con.commit()
    t0 = _t.time(); cur.execute(probe); cur.fetchone()
    console.print(f"  probe after: {(_t.time()-t0)*1000:.0f}ms")
    con.close()
    console.print("[green]✓ db-tune complete[/green]")


@cli.command("status")
def status_cmd():
    """Show what's in the local DB."""
    with session_scope() as s:
        table = Table(title="Database Status", show_header=True)
        table.add_column("Entity", style="cyan")
        table.add_column("Count", justify="right", style="green")

        for model, label in [
            (Competition, "Competitions"),
            (Team, "Teams"),
            (Match, "Matches"),
            (MatchStats, "Match stat rows"),
        ]:
            count = s.execute(select(func.count()).select_from(model)).scalar_one()
            table.add_row(label, str(count))
        console.print(table)

        rows = s.execute(
            select(Competition.code, Competition.name, func.count(Match.id))
            .join(Match, Match.competition_id == Competition.id, isouter=True)
            .group_by(Competition.id)
            .order_by(func.count(Match.id).desc())
        ).all()

        if rows:
            t2 = Table(title="Matches per competition", show_header=True)
            t2.add_column("Code", style="cyan")
            t2.add_column("Name")
            t2.add_column("Matches", justify="right", style="green")
            for code, name, count in rows:
                t2.add_row(code, name, str(count))
            console.print(t2)


@cli.command("find-team")
@click.argument("name_fragment")
def find_team_cmd(name_fragment: str):
    """Quick search to verify a team is in your DB."""
    with session_scope() as s:
        teams = (
            s.execute(select(Team).where(Team.name.ilike(f"%{name_fragment}%")))
            .scalars().all()
        )
        if not teams:
            console.print(f"[yellow]No teams matching '{name_fragment}'[/yellow]")
            return
        table = Table(show_header=True)
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("TLA")
        table.add_column("Area")
        table.add_column("External IDs")
        for t in teams:
            table.add_row(
                str(t.id), t.name, t.tla or "", t.area or "", str(t.external_ids)
            )
        console.print(table)


@cli.command("export-results")
@click.option("--sport", type=click.Choice(["mlb", "baseball", "soccer"]), default="mlb")
@click.option("--competition", "competition_code", default="MLB")
@click.option("--date", "date_str", default=None,
              help="YYYY-MM-DD to export (default: yesterday — what the morning "
                   "run just evaluated).")
@click.option("--out", "out_path", default=None,
              help="File path. Defaults to exports/<sport>_results_<date>.json.")
def export_results_cmd(sport, competition_code, date_str, out_path):
    """
    Export yesterday's GRADED games (prediction + actual outcome + how it graded)
    as a JSON file for the external prediction model to consume. Backward-looking
    companion to export-predictions. Run after evaluate in the morning chain.
    """
    from datetime import datetime, timedelta, date as _date
    from pathlib import Path
    from src.walters.export import export_results
    from src.db.schema import Sport

    sport_enum = Sport.MLB if sport in ("mlb", "baseball") else Sport.SOCCER
    if date_str:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        day = datetime.combine(_date.today() - timedelta(days=1), datetime.min.time())
    # slate-day window: 08:00 UTC → 08:00 UTC next day (matches export-predictions)
    start = day.replace(hour=8, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    try:
        payload = export_results(
            sport=sport_enum, start_date=start, end_date=end,
            competition_code=competition_code, output_format="json",
        )
    except Exception as e:
        console.print(f"[red]✗ Results export failed: {e}[/red]")
        return

    if out_path is None:
        Path("exports").mkdir(exist_ok=True)
        stamp = day.strftime("%Y-%m-%d")
        comp_part = f"_{competition_code}" if competition_code else ""
        out_path = f"exports/{sport_enum.value}{comp_part}_results_{stamp}.json"

    with open(out_path, "w") as f:
        f.write(payload)

    import json as _json
    data = _json.loads(payload)
    n = data["count"]
    if n == 0:
        console.print(f"[yellow]No graded games for {day.strftime('%Y-%m-%d')} "
                      "(not evaluated yet, or none that day).[/yellow]")
        return
    hits = sum(1 for r in data["results"] if r["graded"]["top_pick_hit"])
    tot_graded = [r for r in data["results"]
                  if r["graded"]["total_correct"] is not None]
    tot_ok = sum(1 for r in tot_graded if r["graded"]["total_correct"])
    console.print(f"[green]✓ Wrote {n} results to {out_path}[/green]")
    console.print(f"  [dim]top-pick {hits}/{n} · totals-direction {tot_ok}/{len(tot_graded)} "
                  f"({n - len(tot_graded)} no line) "
                  "(record is variance, not signal — for the consumer to grade against)[/dim]")

    # totals pulse now lives in the payload (audit layer reads it from the file);
    # print it from there so console and file are the same single source of truth.
    tp = data.get("totals_pulse")
    if tp:
        nb_mae = tp.get("non_blowup_mae")
        console.print("  [dim]totals pulse — "
                      f"mean {tp['mean_error']:+.2f} · median {tp['median_error']:+.2f} · "
                      f"trimmed {tp['trimmed_mean_error']:+.2f} · "
                      f"blowups(>{tp['blowup_threshold']:.0f}) {tp['blowup_count']}/{tp['games']}"
                      + (f" · non-blowup MAE {nb_mae:.1f}" if nb_mae is not None else "")
                      + "[/dim]")
        # Conditional (2026-08-25): the outlier-day note printed
        # unconditionally and mislabeled uniform-lean days (08-21: all three
        # centers agreed at ~-1). Print the diagnosis that matches the shape.
        _div = abs(tp["mean_error"] - tp["median_error"])
        if _div >= 0.75 or (tp.get("blowup_count") or 0) > 0:
            console.print("  [dim](mean vs median/trimmed divergence = outlier-driven day, "
                          "not bias; blowups are unpredictable by a point model — the "
                          "--since calibration read is the real verdict)[/dim]")
        else:
            console.print("  [dim](centers agree — uniform lean day, no outlier "
                          "distortion; direction accrues to the --since "
                          "calibration read)[/dim]")


@cli.command("export-fixtures")
@click.option("--competition", "competition_code", required=True, help="e.g. EFL, CL")
@click.option("--start", default=None, help="YYYY-MM-DD")
@click.option("--end", default=None, help="YYYY-MM-DD")
def export_fixtures_cmd(competition_code, start, end):
    """Market-only fixtures export (no predictions) for gated competitions."""
    from src.walters.export import export_fixtures
    path = export_fixtures(competition_code, start=start, end=end)
    console.print(f"[green]✓ Wrote market-only fixtures to {path}[/green]")


@cli.command("export-predictions")
@click.option("--sport", type=click.Choice(["soccer", "mlb", "baseball"]), required=True,
              help="Sport to export.")
@click.option("--date", "date_str", default=None,
              help="Single UTC date YYYY-MM-DD. Defaults to today.")
@click.option("--start", "start_str", default=None,
              help="Range start YYYY-MM-DD (overrides --date).")
@click.option("--end", "end_str", default=None,
              help="Range end YYYY-MM-DD inclusive (overrides --date).")
@click.option("--competition", "competition_code", default=None,
              help="Optional competition filter (e.g. PL, MLB, CL).")
@click.option("--status", "status_filter", default="auto",
              type=click.Choice(["all", "scheduled", "finished", "auto"]),
              help="Match status filter. Default: auto — past dates → finished, future → scheduled, today's range → all.")
@click.option("--format", "output_format", default="json",
              type=click.Choice(["json", "csv"]),
              help="Output format. JSON preserves all structure; CSV is flat headline columns.")
@click.option("--out", "out_path", default=None,
              help="File path to write to. Defaults to exports/<sport>_<date>.<ext>.")
def export_predictions_cmd(sport, date_str, start_str, end_str, competition_code,
                           status_filter, output_format, out_path):
    """
    Export a day's (or date range's) predictions, with prediction probabilities,
    factor breakdown, market data with edge math, and recent form. Use to bulk
    review what the model thinks across a slate.

    Examples:
      python cli.py export-predictions --sport mlb
      python cli.py export-predictions --sport soccer --competition PL --format csv
      python cli.py export-predictions --sport mlb --start 2026-05-23 --end 2026-05-24
      python cli.py export-predictions --sport mlb --status finished  (for post-mortem)
    """
    from datetime import datetime, timedelta
    from pathlib import Path
    from src.db.schema import MatchStatus, Sport
    from src.walters.export import export_predictions

    sport_enum = Sport.MLB if sport in ("mlb", "baseball") else Sport.SOCCER

    # Date range resolution.
    #
    # MLB slates span the calendar in awkward ways: a Wednesday slate has
    # afternoon games in ET and late games on the West Coast that don't
    # end until ~01:00 ET Thursday. In UTC, those games are stamped
    # 2026-05-28 02:10 even though they're part of Wednesday's slate.
    #
    # To handle this, we treat each day as starting at 08:00 UTC (~ 4 AM
    # ET / 1 AM PT) — early enough that no game is in progress, late
    # enough that all of "yesterday's" late games are clearly behind us.
    # All West Coast games on a given calendar day fall in the same
    # window as the East Coast afternoon games of the same calendar day.
    DAY_START_HOUR_UTC = 8

    if start_str and end_str:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(
                hour=DAY_START_HOUR_UTC
            )
            # end_date is exclusive — bump to start of next day at the same offset
            end_date = (datetime.strptime(end_str, "%Y-%m-%d")
                        + timedelta(days=1)).replace(hour=DAY_START_HOUR_UTC)
        except ValueError as e:
            console.print(f"[red]✗ Date parse error: {e}[/red]")
            return
    else:
        target = date_str or datetime.utcnow().strftime("%Y-%m-%d")
        try:
            start_date = datetime.strptime(target, "%Y-%m-%d").replace(
                hour=DAY_START_HOUR_UTC
            )
        except ValueError as e:
            console.print(f"[red]✗ Date parse error: {e}[/red]")
            return
        end_date = start_date + timedelta(days=1)

    # Auto status: past dates → finished, future → scheduled, today's
    # range → all. The previous default of 'scheduled' silently returned
    # empty exports for past dates and confused the UX.
    # Use 08:00 UTC as the day boundary so "today" lines up with the ET
    # operational day (matches the start_date / end_date logic above).
    now_utc = datetime.utcnow()
    today = now_utc.replace(hour=DAY_START_HOUR_UTC, minute=0, second=0, microsecond=0)
    if now_utc.hour < DAY_START_HOUR_UTC:
        today = today - timedelta(days=1)
    if status_filter == "auto":
        if end_date <= today:
            resolved_status = "finished"
        elif start_date >= today + timedelta(days=1):
            resolved_status = "scheduled"
        else:
            resolved_status = "all"
        console.print(f"[dim]Status filter (auto): {resolved_status}[/dim]")
    else:
        resolved_status = status_filter

    statuses_map = {
        "all": None,
        "scheduled": [MatchStatus.SCHEDULED],
        "finished": [MatchStatus.FINISHED],
    }
    statuses = statuses_map[resolved_status]

    try:
        payload = export_predictions(
            sport=sport_enum,
            start_date=start_date,
            end_date=end_date,
            competition_code=competition_code,
            statuses=statuses,
            output_format=output_format,
        )
    except ValueError as e:
        console.print(f"[red]✗ Export failed: {e}[/red]")
        return

    # Resolve output path
    if out_path is None:
        Path("exports").mkdir(exist_ok=True)
        suffix = "csv" if output_format == "csv" else "json"
        # filename includes date so multiple exports same day don't clobber
        stamp = start_date.strftime("%Y-%m-%d")
        if start_str and end_str and start_str != end_str:
            stamp = f"{start_str}_to_{end_str}"
        comp_part = f"_{competition_code}" if competition_code else ""
        out_path = f"exports/{sport_enum.value}{comp_part}_{stamp}.{suffix}"

    with open(out_path, "w") as f:
        f.write(payload)

    # Friendly summary
    if output_format == "json":
        import json as _json
        data = _json.loads(payload)
        count = data.get("count", 0)
        if count == 0:
            console.print(f"[yellow]⚠ Wrote 0 predictions to {out_path} — "
                          f"no matches found in window with status {resolved_status!r}. "
                          f"Try --status all or check date range.[/yellow]")
        else:
            console.print(f"[green]✓ Wrote {count} predictions to {out_path}[/green]")
    else:
        lines = payload.count("\n")
        console.print(f"[green]✓ Wrote {max(lines - 1, 0)} rows to {out_path}[/green]")


if __name__ == "__main__":
    cli()