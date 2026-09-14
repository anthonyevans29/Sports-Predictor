"""
Stage 1 signal validation — does a tracked signal carry information the MODEL
LACKS?

The honest test for "are we missing an input." For every graded prediction we
compute the model's residual on its pick:

    residual = actual_win (1/0) − model_predicted_prob

A residual near 0 on average means the model is calibrated (it is). The question
is whether any TRACKED signal (weather, bullpen fatigue, umpire, streak)
correlates with that residual. If depleted-bullpen favorites have a systematically
NEGATIVE residual (won less than predicted) beyond noise, the signal carries
information the model doesn't have → candidate for Stage 2 (train it in).

Key discipline:
  - We bucket each signal and report mean residual + n PER BUCKET. A signal only
    "carries information" if the residual VARIES across its buckets by more than
    sampling noise.
  - This is on HISTORICAL data (backfill). A signal passing here is a hypothesis
    for out-of-sample Stage 2, not proof.
  - Most signals will be flat (redundant with team quality the model has). That
    is the expected, honest result — and it means the model isn't missing them.
  - Even a signal that passes may already be priced by the market (won't create
    CLV edge) — Stage 1 tests calibration information, not market edge.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import (Match, Prediction, PredictionOutcome, Team, Sport,
                           GameWeather, UmpireGame, PitcherAppearance)


def _mean_sd_n(vals):
    n = len(vals)
    if n == 0:
        return None, None, 0
    m = sum(vals) / n
    if n < 2:
        return m, None, n
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return m, math.sqrt(var), n


def _bucket_report(name, buckets: dict):
    """buckets: label -> list of residuals. Returns printable rows + a verdict."""
    rows = []
    means = []
    for label, resids in buckets.items():
        m, sd, n = _mean_sd_n(resids)
        se = (sd / math.sqrt(n)) if (sd and n > 1) else None
        rows.append((label, n, m, se))
        if m is not None and n >= 20:
            means.append(m)
    # spread across well-sampled buckets = does the signal move the residual?
    spread = (max(means) - min(means)) if len(means) >= 2 else None
    return rows, spread


def run_signal_residuals(sport="mlb"):
    """
    Compute model residuals and cross them against each tracked signal.
    Returns a dict of {signal_name: {"rows": [...], "spread": float|None}}.
    """
    out = {}
    with session_scope() as s:
        team_sid = {}
        for t in s.execute(select(Team)).scalars():
            sid = (t.external_ids or {}).get("mlb_stats_api")
            if sid:
                team_sid[t.id] = str(sid)

        rows = list(s.execute(
            select(Prediction, Match, PredictionOutcome)
            .join(Match, Match.id == Prediction.match_id)
            .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(Match.sport == Sport.MLB,
                   PredictionOutcome.top_pick_hit.isnot(None))
        ).all())

        # index tracked signals by match
        weather = {w.match_id: w for w in s.execute(select(GameWeather)).scalars()}
        umps = {u.match_id: u for u in s.execute(select(UmpireGame)).scalars()}
        appe = list(s.execute(
            select(PitcherAppearance).where(PitcherAppearance.is_starter == False)  # noqa: E712
        ).scalars())
        appe_by_team = defaultdict(list)
        for a in appe:
            if a.team_source_id and a.game_date:
                appe_by_team[a.team_source_id].append(a)

        # umpire running R/G (to bucket high/low run-environment umps)
        ump_runs = defaultdict(list)
        for u in umps.values():
            if u.plate_umpire and u.total_runs is not None:
                ump_runs[u.plate_umpire].append(u.total_runs)
        ump_avg = {k: sum(v) / len(v) for k, v in ump_runs.items() if len(v) >= 15}

        # per-team finished games handled via appe_by_team above
        from datetime import timedelta

        # residual buckets per signal
        b_bullpen = defaultdict(list)
        b_weather_wind = defaultdict(list)
        b_temp = defaultdict(list)
        b_ump = defaultdict(list)
        b_wonlast = defaultdict(list)

        for pred, m, oc in rows:
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            side = max(nn, key=nn.get)
            p = nn[side]
            won = 1.0 if oc.top_pick_hit else 0.0
            resid = won - p  # + = won more than predicted, - = less
            fav_team_id = m.home_team_id if side == "home" else m.away_team_id

            # --- bullpen fatigue of the favorite (prior 3 days) ---
            sid = team_sid.get(fav_team_id)
            if sid and m.utc_date:
                gd = m.utc_date.date()
                recent = [a for a in appe_by_team.get(sid, [])
                          if gd - timedelta(days=3) <= a.game_date.date() < gd]
                heavy = sum(1 for a in recent if (a.pitches or 0) >= 30)
                napp = len(recent)
                if napp <= 6:
                    b_bullpen["rested (≤6 app)"].append(resid)
                elif napp <= 10:
                    b_bullpen["moderate (7-10)"].append(resid)
                else:
                    b_bullpen["depleted (>10)"].append(resid)

            # --- weather: wind out/in (needs venue in park map) ---
            w = weather.get(m.id)
            if w and w.wind_mph is not None and w.wind_dir_deg is not None:
                from src.walters.park_wind import wind_effect
                we = wind_effect(w.venue, w.wind_dir_deg, w.wind_mph)
                if we:
                    comp = we["component"]
                    b_weather_wind[comp].append(resid)
                if w.temperature_f is not None:
                    if w.temperature_f < 60:
                        b_temp["cold <60"].append(resid)
                    elif w.temperature_f < 80:
                        b_temp["mild 60-80"].append(resid)
                    else:
                        b_temp["hot ≥80"].append(resid)

            # --- umpire run environment ---
            u = umps.get(m.id)
            if u and u.plate_umpire in ump_avg:
                a = ump_avg[u.plate_umpire]
                if a >= 9.3:
                    b_ump["high-run ump (≥9.3)"].append(resid)
                elif a <= 8.5:
                    b_ump["low-run ump (≤8.5)"].append(resid)
                else:
                    b_ump["avg ump"].append(resid)

        results = {}
        for nm, b in (("bullpen_fatigue", b_bullpen),
                      ("wind", b_weather_wind),
                      ("temperature", b_temp),
                      ("umpire_run_env", b_ump)):
            r, spread = _bucket_report(nm, b)
            results[nm] = {"rows": r, "spread": spread}
        return results
