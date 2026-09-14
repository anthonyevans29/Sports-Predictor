"""
Prediction-context assembly: gather the TRACKED-BUT-UNUSED signals for a set of
matches so they can ride ALONGSIDE each prediction in the export, clearly
stamped `used_in_model: false`.

This is the bridge between the tracking instruments (umpire/weather/bullpen/
starter tables) and the betting layer. The betting layer can SEE these signals
and factor them into its own routing if it wants — but they are explicitly NOT
in the model's probability. Nothing here changes any prediction; it only reads
the tracking tables and packages what we have.

Design: one batched query per signal over the match window (no N+1), returned
as {match_id: {...context...}}. Missing signals are simply absent — the export
marks each signal's availability so the betting layer never mistakes "not
captured" for "captured as zero".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from src.db.schema import (Match, Team, GameWeather, UmpireGame,
                           PitcherAppearance, MatchStatus)
from src.walters.team_streaks import streak_kpis


def build_unused_context(s, matches: list) -> dict[int, dict]:
    """
    For the given matches, assemble the unused-in-model context per match_id.

    Returns {match_id: {
        "used_in_model": False,
        "weather": {...} | None,
        "plate_umpire": {...} | None,
        "bullpen_availability": {home:..., away:...} | None,
        "won_last_game": {home: bool|None, away: bool|None},
        "streak_context": {home: {...}|None, away: {...}|None},  # only when on a win streak
        "_note": "...",
    }}
    """
    if not matches:
        return {}
    match_ids = [m.id for m in matches]

    # team.id -> mlb source id, and -> name (appearances keyed by source id)
    team_sid: dict[int, str] = {}
    for t in s.execute(select(Team)).scalars():
        sid = (t.external_ids or {}).get("mlb_stats_api")
        if sid:
            team_sid[t.id] = str(sid)

    # --- weather: latest snapshot per match ---
    weather_by_match: dict[int, GameWeather] = {}
    for w in s.execute(
        select(GameWeather)
        .where(GameWeather.match_id.in_(match_ids))
        .order_by(GameWeather.captured_at.desc())
    ).scalars():
        if w.match_id not in weather_by_match:
            weather_by_match[w.match_id] = w

    # --- umpire: row per finished game (only present post-game) ---
    ump_by_match: dict[int, UmpireGame] = {}
    for u in s.execute(
        select(UmpireGame).where(UmpireGame.match_id.in_(match_ids))
    ).scalars():
        ump_by_match[u.match_id] = u

    # --- per-umpire running R/G to date (so a name carries its tracked tendency) ---
    ump_rpg: dict[str, tuple[float, int]] = {}
    rows = list(s.execute(select(UmpireGame)).scalars())
    agg: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r.plate_umpire and r.total_runs is not None:
            agg[r.plate_umpire].append(r.total_runs)
    for name, runs in agg.items():
        if runs:
            ump_rpg[name] = (sum(runs) / len(runs), len(runs))

    # --- bullpen availability: relievers in prior 3d per team, per match date ---
    # preload all reliever appearances once, index by source team id
    appearances = list(s.execute(
        select(PitcherAppearance).where(PitcherAppearance.is_starter == False)  # noqa: E712
    ).scalars())
    appe_by_team: dict[str, list] = defaultdict(list)
    for a in appearances:
        if a.team_source_id and a.game_date:
            appe_by_team[a.team_source_id].append(a)

    def bullpen_state(team_id: int | None, game_dt) -> dict | None:
        sid = team_sid.get(team_id) if team_id is not None else None
        if not sid or game_dt is None:
            return None
        gdate = game_dt.date()
        start = gdate - timedelta(days=3)
        recent = [a for a in appe_by_team.get(sid, [])
                  if start <= a.game_date.date() < gdate]
        if not recent:
            return {"relievers_used": 0, "appearances": 0, "heavy_outings": 0,
                    "data": "none in window"}
        relievers = {a.pitcher_id for a in recent}
        heavy = sum(1 for a in recent if (a.pitches or 0) >= 30)
        return {"relievers_used": len(relievers), "appearances": len(recent),
                "heavy_outings": heavy}

    # --- won-last-game: index every finished game by team, sorted by date ---
    # Derived from Match rows we already have (no new feed). For each team we
    # keep an ordered list of (date, won?) so a match can look up each side's
    # most-recent completed game BEFORE it.
    finished = list(s.execute(
        select(Match).where(Match.status == MatchStatus.FINISHED,
                            Match.home_score.isnot(None),
                            Match.away_score.isnot(None))
    ).scalars())
    team_games: dict[int, list[tuple]] = defaultdict(list)
    for fm in finished:
        if fm.utc_date is None:
            continue
        home_won = fm.home_score > fm.away_score
        team_games[fm.home_team_id].append((fm.utc_date, home_won))
        team_games[fm.away_team_id].append((fm.utc_date, not home_won))
    for tid in team_games:
        team_games[tid].sort(key=lambda x: x[0])

    def won_last_game(team_id: int | None, game_dt) -> bool | None:
        if team_id is None or game_dt is None:
            return None
        prior = [w for (dt, w) in team_games.get(team_id, []) if dt < game_dt]
        if not prior:
            return None  # no completed prior game on record
        return prior[-1]  # most recent

    def streak_context(team_id: int | None, game_dt) -> dict | None:
        """
        Seasonal winning-streak context for a team, AS OF this game — but only
        when the team is CURRENTLY on a winning streak (won their last game).
        Complements bullpen form: how a club is managing a run of games.
        Returns None if they didn't win their last game (not on a streak) or
        have no prior games. used_in_model: false, like everything here.
        """
        if team_id is None or game_dt is None:
            return None
        prior = [w for (dt, w) in team_games.get(team_id, []) if dt < game_dt]
        if not prior or not prior[-1]:
            return None  # not currently on a winning streak
        k = streak_kpis(prior)
        return {
            "on_winning_streak": True,
            "current_streak": k["current_streak"],       # games into current run
            "avg_win_streak_len": k["avg_win_streak_len"],  # season avg
            "longest_win_streak": k["longest_win_streak"],  # season max
        }

    context: dict[int, dict] = {}
    for m in matches:
        w = weather_by_match.get(m.id)
        weather = None
        if w:
            from src.walters.park_wind import wind_effect
            we = wind_effect(w.venue, w.wind_dir_deg, w.wind_mph)
            weather = {
                "venue": w.venue, "roof_state": w.roof_state,
                "temperature_f": w.temperature_f, "wind_mph": w.wind_mph,
                "wind_dir_deg": w.wind_dir_deg,
                "wind_effect": we,  # out/in/cross + component mph, or None
                "precipitation_in": w.precipitation_in, "condition": w.condition,
            }

        u = ump_by_match.get(m.id)
        ump = None
        if u and u.plate_umpire:
            rpg = ump_rpg.get(u.plate_umpire)
            ump = {"name": u.plate_umpire,
                   "tracked_runs_per_game": round(rpg[0], 2) if rpg else None,
                   "tracked_n": rpg[1] if rpg else 0}

        bullpen = None
        bh = bullpen_state(m.home_team_id, m.utc_date)
        ba = bullpen_state(m.away_team_id, m.utc_date)
        if bh is not None or ba is not None:
            bullpen = {"home": bh, "away": ba}

        # bullpen EFFECTIVENESS (reliever run-prevention over trailing 30d) —
        # distinct from availability above. used_in_model: false; tracked to test
        # whether it beats what team RA already carries.
        from src.walters.bullpen_effectiveness import team_bullpen_effectiveness
        bp_eff = None
        h_sid = team_sid.get(m.home_team_id)
        a_sid = team_sid.get(m.away_team_id)
        eff_h = team_bullpen_effectiveness(s, h_sid, m.utc_date) if h_sid else None
        eff_a = team_bullpen_effectiveness(s, a_sid, m.utc_date) if a_sid else None
        if eff_h or eff_a:
            bp_eff = {"home": eff_h, "away": eff_a}

        # won-last-game: simple True/False per side (None if no prior game)
        won_last = {
            "home": won_last_game(m.home_team_id, m.utc_date),
            "away": won_last_game(m.away_team_id, m.utc_date),
        }

        # streak context: seasonal winning-streak KPIs, per side, ONLY when that
        # team is currently on a winning streak (complements bullpen form).
        streak_ctx = {
            "home": streak_context(m.home_team_id, m.utc_date),
            "away": streak_context(m.away_team_id, m.utc_date),
        }

        # only attach a context block if we actually have something
        if (weather or ump or bullpen or bp_eff or won_last["home"] is not None
                or won_last["away"] is not None):
            context[m.id] = {
                "used_in_model": False,
                "_note": ("Captured for tracking/validation only. NOT in the "
                          "model's probability. Betting layer may use at its own "
                          "discretion; these signals are unvalidated."),
                "weather": weather,
                "plate_umpire": ump,
                "bullpen_availability": bullpen,
                "bullpen_effectiveness": bp_eff,
                "won_last_game": won_last,
                "streak_context": streak_ctx,
            }
    return context
