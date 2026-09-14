"""
Admin routes — UI for running data syncs and model commands.

All endpoints here are gated by the require_localhost dependency. The
sync/train operations are kicked off as background jobs (see src/web/jobs.py).
Long-running jobs would otherwise hold the HTTP request open until they
finish — we want fire-and-forget with a polling status endpoint.

Endpoints:
    GET  /admin                          → page with action buttons
    POST /admin/jobs/{action_name}       → submit a job, returns job_id
    GET  /admin/jobs/{job_id}            → poll a job's status (HTMX-friendly)
    GET  /admin/jobs                     → list recent jobs
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from src.adapters.registry import get_adapter
from src.db.database import session_scope
from src.db.schema import Competition, Sport
from src.ingestion.service import IngestionService
from src.web.guards import require_localhost
from src.web.jobs import Job, runner

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_localhost)])


# Same routing as the CLI: MLB codes go to baseball adapter, everything else soccer.
_BASEBALL_COMP_CODES = {"MLB", "MLB_SPRING"}


def _adapter_for_competition(code: str):
    """Pick the right adapter automatically based on the competition code."""
    sport = "baseball" if code.upper() in _BASEBALL_COMP_CODES else "soccer"
    return get_adapter(sport=sport)


# --------------------------------------------------------------------------
# Job wrappers — each one matches a CLI command.
# Signatures take **kwargs so the runner's `job=` kwarg is absorbed.
# --------------------------------------------------------------------------


def _job_sync_competitions(*, sport: str = "soccer", **kwargs) -> str:
    """Sport defaults to soccer so existing callers don't break."""
    service = IngestionService(get_adapter(sport=sport))
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    result = service.sync_competitions(sport_enum)
    return f"created={result.created} updated={result.updated} skipped={result.skipped}"


def _job_sync_teams(*, competition_code: str, season: str, **kwargs) -> str:
    service = IngestionService(_adapter_for_competition(competition_code))
    result = service.sync_teams(competition_code, season)
    return f"created={result.created} updated={result.updated} skipped={result.skipped}"


def _job_sync_matches(
    *, competition_code: str, season: str | None, seasons: int, **kwargs
) -> str:
    service = IngestionService(_adapter_for_competition(competition_code))
    is_mlb = competition_code.upper() in _BASEBALL_COMP_CODES
    job: Job = kwargs.get("job")  # type: ignore[assignment]
    if seasons > 0:
        current_year = datetime.utcnow().year
        # Soccer seasons span two years (e.g. 2025/26); MLB seasons are single-year.
        # For soccer, we adjust by month — anything before July is "last season".
        if not is_mlb and datetime.utcnow().month < 7:
            current_year -= 1
        totals = {"created": 0, "updated": 0, "skipped": 0}
        for offset in range(seasons):
            year = current_year - offset
            if is_mlb:
                season_str = str(year)
            else:
                season_str = f"{year}/{str(year + 1)[-2:]}"
            if job:
                job.append_log(f"→ {competition_code} {season_str}")
            r = service.sync_matches(competition_code, season=season_str)
            totals["created"] += r.created
            totals["updated"] += r.updated
            totals["skipped"] += r.skipped
            if job:
                job.append_log(
                    f"  created={r.created} updated={r.updated} skipped={r.skipped}"
                )
        return (
            f"created={totals['created']} updated={totals['updated']} "
            f"skipped={totals['skipped']}"
        )
    r = service.sync_matches(competition_code, season=season)
    return f"created={r.created} updated={r.updated} skipped={r.skipped}"


def _job_sync_stats(*, competition_code: str, season: str, limit: int, **kwargs) -> str:
    adapter = _adapter_for_competition(competition_code)
    service = IngestionService(adapter)
    from src.db.schema import Match, MatchStats, MatchStatus

    job: Job = kwargs.get("job")  # type: ignore[assignment]
    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return f"competition {competition_code} not in DB"

        match_q = select(Match).where(
            Match.competition_id == comp.id,
            Match.season == season,
            Match.status == MatchStatus.FINISHED,
        )
        matches = s.execute(match_q).scalars().all()
        matches = [m for m in matches if not m.stats][:limit]
        keys = [
            (m.id, (m.external_ids or {}).get(adapter.source_name)) for m in matches
        ]
        keys = [(mid, sid) for mid, sid in keys if sid]

    if not keys:
        return "nothing to fetch (no eligible matches)"

    if job:
        job.append_log(f"fetching stats for {len(keys)} matches")
    written = 0
    for match_id, source_id in keys:
        try:
            stats_list = adapter.get_match_stats(source_id)
        except Exception as e:
            if job:
                job.append_log(f"  ✗ match {match_id}: {e}")
            continue
        with session_scope() as s2:
            service.persist_match_stats(s2, match_id, stats_list, adapter.source_name)
        written += 1
        if job and written % 10 == 0:
            job.append_log(f"  ...{written}/{len(keys)} written")

    return f"wrote stats for {written} matches"


def _job_sync_odds(
    *, competition_code: str, season: str | None, limit: int, **kwargs
) -> str:
    """
    Pull odds for a competition. Soccer uses API-Football (per-match);
    MLB uses API-Baseball (per-day window) to fill the MLB Stats API gap.
    """
    service = IngestionService(_adapter_for_competition(competition_code))
    if competition_code.upper() == "MLB":
        if not season:
            return "MLB requires season (year)"
        try:
            season_int = int(season)
        except ValueError:
            return f"Invalid MLB season {season!r}"
        r = service.sync_odds_mlb(season=season_int, days_ahead=7)
        return f"created={r.created} games={r.updated} skipped={r.skipped}"
    r = service.sync_odds(competition_code, season=season, limit=limit)
    return f"created={r.created} skipped={r.skipped}"


def _job_sync_injuries(*, competition_code: str, season: str, **kwargs) -> str:
    if competition_code.upper() == "MLB":
        return ("not supported — API-Baseball has no /injuries endpoint, "
                "MLB Stats API doesn't either")
    service = IngestionService(_adapter_for_competition(competition_code))
    r = service.sync_injuries(competition_code, season=season)
    return f"created={r.created} skipped={r.skipped}"


def _job_sync_lineups(
    *, competition_code: str, season: str, limit: int, **kwargs
) -> str:
    """Phase 4: pull projected lineups for upcoming fixtures + confirmed lineups
    for matches within 20 minutes of kickoff. (Soccer only.)"""
    service = IngestionService(_adapter_for_competition(competition_code))
    job: Job = kwargs.get("job")  # type: ignore[assignment]
    r = service.sync_lineups(
        competition_code, season=season, limit=limit, on_log=job.append_log if job else None
    )
    return f"projected={r.created} confirmed={r.updated} skipped={r.skipped}"


def _job_train(*, sport: str = "soccer", **kwargs) -> str:
    from src.walters.training import train_fresh
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    result = train_fresh(sport=sport_enum, notes="from admin UI")
    return f"trained {result.version} on {result.train_size} matches"


def _job_predict(*, competition_code: str, season: str, **kwargs) -> str:
    from src.walters.training import generate_predictions
    sport_enum = Sport.MLB if competition_code.upper() in _BASEBALL_COMP_CODES else Sport.SOCCER
    n = generate_predictions(competition_code, season, sport=sport_enum)
    return f"wrote {n} predictions"


def _job_evaluate(*, sport: str = "soccer", **kwargs) -> str:
    from src.walters.training import evaluate_finished
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    n = evaluate_finished(sport=sport_enum)
    return f"evaluated {n} predictions"


def _job_improve(*, sport: str = "soccer", **kwargs) -> str:
    from src.walters.training import improve
    sport_enum = Sport.SOCCER if sport == "soccer" else Sport.MLB
    r = improve(sport=sport_enum)
    promoted = "PROMOTED" if r.promoted else "REJECTED"
    return f"candidate {r.candidate_version} {promoted}: {r.reasoning}"


def _job_sync_pitchers(
    *, competition_code: str, season: str, limit: int, **kwargs
) -> str:
    """Pull probable starting pitchers for upcoming MLB games."""
    service = IngestionService(_adapter_for_competition(competition_code))
    job: Job = kwargs.get("job")  # type: ignore[assignment]
    r = service.sync_pitchers(
        competition_code, season=season, limit=limit,
        on_log=job.append_log if job else None,
    )
    return f"projected={r.created} confirmed={r.updated} skipped={r.skipped}"


def _job_sync_players(
    *, competition_code: str, season: str, **kwargs
) -> str:
    """Pull squad + season stats for every team in the competition."""
    service = IngestionService(_adapter_for_competition(competition_code))
    job: Job = kwargs.get("job")  # type: ignore[assignment]
    r = service.sync_players(
        competition_code, season=season,
        on_log=job.append_log if job else None,
    )
    return f"new_players={r.created} teams_synced={r.updated} skipped={r.skipped}"


# Mapping from action name → (callable, friendly description)
# The form_keys list tells the UI which inputs to send.
ACTIONS: dict[str, dict] = {
    "sync-competitions": {
        "fn": _job_sync_competitions,
        "description": "Refresh competition list",
        "form_keys": ["sport"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "sync-teams": {
        "fn": _job_sync_teams,
        "description": "Refresh teams in a competition/season",
        "form_keys": ["competition_code", "season"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "sync-matches": {
        "fn": _job_sync_matches,
        "description": "Sync matches for a competition/season",
        "form_keys": ["competition_code", "season", "seasons"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "sync-stats": {
        "fn": _job_sync_stats,
        "description": "Pull per-match stats (slow, 1 API request each)",
        "form_keys": ["competition_code", "season", "limit"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "sync-odds": {
        "fn": _job_sync_odds,
        "description": "Pull bookmaker odds for upcoming fixtures (soccer + MLB)",
        "form_keys": ["competition_code", "season", "limit"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "sync-injuries": {
        "fn": _job_sync_injuries,
        "description": "Refresh team injury lists (soccer only — MLB has no data source)",
        "form_keys": ["competition_code", "season"],
        "destructive": False,
        "sports": {"soccer"},
    },
    "sync-lineups": {
        "fn": _job_sync_lineups,
        "description": "Pull projected/confirmed lineups for upcoming fixtures",
        "form_keys": ["competition_code", "season", "limit"],
        "destructive": False,
        "sports": {"soccer"},
    },
    "sync-players": {
        "fn": _job_sync_players,
        "description": "Refresh full squads + season stats for power-rating computation",
        "form_keys": ["competition_code", "season"],
        "destructive": False,
        "sports": {"soccer"},
    },
    "sync-pitchers": {
        "fn": _job_sync_pitchers,
        "description": "Pull probable starting pitchers for upcoming games",
        "form_keys": ["competition_code", "season", "limit"],
        "destructive": False,
        "sports": {"baseball"},
    },
    "train": {
        "fn": _job_train,
        "description": "Train a fresh model from all historical data",
        "form_keys": ["sport"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "predict": {
        "fn": _job_predict,
        "description": "Generate predictions for upcoming fixtures",
        "form_keys": ["competition_code", "season"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "evaluate": {
        "fn": _job_evaluate,
        "description": "Score finished predictions",
        "form_keys": ["sport"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
    "improve": {
        "fn": _job_improve,
        "description": "Full loop: evaluate → train candidate → promote if better",
        "form_keys": ["sport"],
        "destructive": False,
        "sports": {"soccer", "baseball"},
    },
}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request):
    """The main admin page with action buttons and recent jobs feed."""
    from src.web.dependencies import resolve_sport, sport_for_competition
    from src.db.schema import Sport

    templates = request.state.templates
    active_sport = resolve_sport(request)  # "soccer" or "baseball"
    sport_enum = Sport.SOCCER if active_sport == "soccer" else Sport.MLB

    # Competitions for the dropdowns — filter to active sport so MLB users
    # don't see PL in their dropdown when running sync-pitchers, etc.
    with session_scope() as s:
        comps = list(
            s.execute(
                select(Competition)
                .where(Competition.sport == sport_enum)
                .order_by(Competition.area, Competition.name)
            ).scalars()
        )
        comps_dicts = [
            {"code": c.code, "name": c.name, "area": c.area} for c in comps
        ]

    # Filter actions to those applicable to the active sport
    visible_actions = {
        name: meta for name, meta in ACTIONS.items()
        if active_sport in meta.get("sports", {"soccer", "baseball"})
    }

    recent_jobs = [j.as_dict() for j in runner.list_recent(limit=15)]

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "comps": comps_dicts,
            "actions": visible_actions,
            "active_sport": active_sport,
            "recent_jobs": recent_jobs,
            "current_year": datetime.utcnow().year,
        },
    )


@router.post("/jobs/{action_name}")
async def submit_job(
    action_name: str,
    request: Request,
    competition_code: str | None = Form(default=None),
    season: str | None = Form(default=None),
    seasons: int | None = Form(default=None),
    limit: int | None = Form(default=None),
    sport: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
):
    """Submit a background job. Returns the job's status partial for HTMX swap."""
    action = ACTIONS.get(action_name)
    if action is None:
        raise HTTPException(status_code=404, detail=f"Unknown action {action_name}")

    if action.get("destructive") and confirm != "yes":
        raise HTTPException(
            status_code=400,
            detail="This action is destructive; confirmation required.",
        )

    kwargs: dict = {}
    for key in action["form_keys"]:
        val = locals().get(key)
        if val in (None, ""):
            raise HTTPException(status_code=400, detail=f"Missing field: {key}")
        kwargs[key] = val

    job = runner.submit(
        name=action_name,
        description=_format_description(action, kwargs),
        fn=action["fn"],
        **kwargs,
    )

    templates = request.state.templates
    return templates.TemplateResponse(
        request,
        "partials/job_card.html",
        {"job": job.as_dict()},
    )


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, request: Request):
    """Return the job's status partial. Polled by HTMX every couple seconds."""
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    templates = request.state.templates
    return templates.TemplateResponse(
        request,
        "partials/job_card.html",
        {"job": job.as_dict()},
    )


@router.get("/jobs")
async def list_jobs(request: Request):
    """Return the recent jobs feed partial."""
    templates = request.state.templates
    return templates.TemplateResponse(
        request,
        "partials/job_feed.html",
        {"recent_jobs": [j.as_dict() for j in runner.list_recent(limit=15)]},
    )


def _format_description(action: dict, kwargs: dict) -> str:
    base = action["description"]
    if kwargs:
        parts = [f"{k}={v}" for k, v in kwargs.items()]
        return f"{base} ({', '.join(parts)})"
    return base
