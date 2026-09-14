"""
Match preview helpers — Phase 9.

Builds the rich pre-match context that surrounds the prediction:
- Recent form per team (last N results)
- Head-to-head history between the two teams
- Standings position / record
- Prediction narrative (turn factor_breakdown into prose)

These functions return plain dicts/lists ready for templating. They don't
mutate DB state and don't depend on external APIs (weather lives in a
separate module).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from src.db.schema import Match, MatchStatus, Sport, Team


# How many games to show in the form panel per team. 10 is enough to see
# trends without being noisy.
FORM_LIMIT = 10
# How many head-to-head meetings to show. 5 is the standard.
H2H_LIMIT = 5

# ---------------------------------------------------------------------------
# Confidence tiers (Thing 1 — reporting only, NOT a model change)
# ---------------------------------------------------------------------------
# Classify the model's CONVICTION in its top pick so coin-flips aren't
# dressed up as recommendations. Thresholds informed by calibration data:
# the 50-53% range is barely off a coin-flip (not actionable); 53-60% is a
# real but modest lean; 60%+ is the high-confidence bucket (calibrated
# post-12.5). These are reporting labels — the model's probabilities are
# unchanged. Tunable as calibration data grows.
TIER_TOSSUP_MAX = 0.53   # below this → "toss-up" (no actionable side)
TIER_LEAN_MAX = 0.60     # 0.53–0.60 → "lean"; at/above → "strong"


def _result_letter(match: "Match", team_id: int) -> str | None:
    """
    Result of `match` from team_id's perspective: 'W', 'L', 'D', or None if the
    game hasn't been played (scores absent). Used by form/H2H summaries.
    """
    hs, as_ = match.home_score, match.away_score
    if hs is None or as_ is None:
        return None
    is_home = match.home_team_id == team_id
    mine = hs if is_home else as_
    theirs = as_ if is_home else hs
    if mine > theirs:
        return "W"
    if mine < theirs:
        return "L"
    return "D"


def classify_tier(top_prob: float, starter_known: bool = True) -> dict:
    """
    Return a conviction tier for a top-pick probability.

    {"tier": "toss-up"|"lean"|"strong", "actionable": bool, "label": str,
     "capped_by_starter": bool}

    Reporting only — does not alter the prediction probability. "actionable"
    is False for toss-ups so downstream reporting can separate "the model
    claimed an edge" from "the model is calling this a coin-flip."

    starter_known: when False (a starter is unknown / null), the tier is
    CAPPED at "lean" no matter how high the post-shrink probability is. This
    is a label-coherence rule, NOT a probability change: the missing-starter
    shrink (Phase 12.3) already pulled the probability toward 50/50; this
    just prevents the *label* from calling a pick "strong" when it rests on
    incomplete information. Follows directly from 12.3's own premise — a
    pick built on an unknown starter is inherently less trustworthy than the
    same number built on confirmed starters, so it shouldn't wear the
    "strong" badge. (No statistical downgrade is applied — the sample of
    confident unknown-starter games is far too small to justify one.)
    """
    if top_prob < TIER_TOSSUP_MAX:
        return {"tier": "toss-up", "actionable": False,
                "label": "Toss-up — no actionable side",
                "capped_by_starter": False}
    elif top_prob < TIER_LEAN_MAX:
        return {"tier": "lean", "actionable": True, "label": "Lean",
                "capped_by_starter": False}
    else:
        # Would be "strong" — but cap at "lean" if a starter is unknown.
        if not starter_known:
            return {"tier": "lean", "actionable": True,
                    "label": "Lean — capped (starter unconfirmed)",
                    "capped_by_starter": True}
        return {"tier": "strong", "actionable": True, "label": "Strong",
                "capped_by_starter": False}


def expression_signal(top_prob: float, over_prob: float | None) -> dict | None:
    """
    Thing 2 — which expression of the game the model is most confident in:
    the moneyline SIDE or the TOTAL (over/under).

    The model already computes both. "Conviction" = distance from 50%. When
    the total's conviction meaningfully exceeds the side's, the model's real
    read is the total, not the side (the recurring Coors pattern: a 50/50
    side but a confident over).

    Returns None when there's no over_prob or no meaningful divergence.
    Otherwise: {"stronger": "total"|"side", "side_conviction_pp": float,
                "total_conviction_pp": float, "note": str}
    Reporting only.
    """
    if over_prob is None:
        return None
    side_conv = abs(top_prob - 0.5)
    total_conv = abs(over_prob - 0.5)
    # Only flag when the total is the clearly stronger expression. An 8pp
    # conviction gap is the threshold — below that they're comparable and we
    # don't want to nag.
    GAP = 0.08
    if total_conv - side_conv >= GAP:
        direction = "over" if over_prob > 0.5 else "under"
        return {
            "stronger": "total",
            "side_conviction_pp": round(side_conv * 100, 1),
            "total_conviction_pp": round(total_conv * 100, 1),
            "note": (f"Model's stronger read is the TOTAL ({direction}, "
                     f"{over_prob*100:.0f}%) than the side "
                     f"({top_prob*100:.0f}%) — consider the total over the moneyline."),
        }
    return None


# ---------------------------------------------------------------------------
# Bullpen recent-form swing flag (reporting only — observed 2026-06-05)
# ---------------------------------------------------------------------------
# Diagnostic finding: predictions where a bullpen's recent (10-day) ERA
# diverges a lot from its season ERA are OVERCONFIDENT. Across stored
# scored games, big-swing (>=1.5 ERA) predictions hit 40% vs ~60% predicted
# (-19.6pp; -13.3pp on post-12.5 games alone). Mechanism: a 10-day bullpen
# window (~30-40 IP) is noisy — a 2+ run divergence is often small-sample
# noise that mean-reverts, but the 12.4 recent-form blend weights it 30%,
# enough to swing a prediction into overconfidence.
#
# This flag SURFACES the condition so it's visible and trackable. It does
# NOT change any probability — the model fix (tapering the recent-form
# weight on extreme swings) is deferred to the post-June-7 backlog so it
# can be validated against calibration data rather than rushed on a thin
# sample (n=13 post-12.5 at time of discovery).
BULLPEN_SWING_FLAG_ERA = 1.5  # ERA divergence at/above which we flag


def bullpen_swing_flag(factor_breakdown: dict) -> dict | None:
    """
    Flag a prediction that leans on a large bullpen recent-form swing.

    Looks at home/away bullpen_detail (season_era vs recent_era). Returns
    the largest swing and which team(s) when any side diverges by
    >= BULLPEN_SWING_FLAG_ERA, else None.

    Reporting only. Surfaces the overconfidence-risk condition identified
    2026-06-05; the model-side fix is deferred to post-June-7 calibration.

    Returns: {"max_swing": float, "teams": [..], "note": str} | None
    """
    flagged = []
    max_swing = 0.0
    for side in ("home", "away"):
        det = factor_breakdown.get(f"{side}_bullpen_detail")
        if not det:
            continue
        se, re = det.get("season_era"), det.get("recent_era")
        if se is None or re is None:
            continue
        swing = abs(re - se)
        if swing >= BULLPEN_SWING_FLAG_ERA:
            direction = "caving" if re > se else "locked in"
            flagged.append({"side": side, "swing": round(swing, 2),
                            "direction": direction,
                            "season_era": se, "recent_era": re})
        max_swing = max(max_swing, swing)
    if not flagged:
        return None
    parts = [f"{f['side']} bullpen {f['direction']} "
             f"({f['recent_era']:.2f} recent vs {f['season_era']:.2f} season)"
             for f in flagged]
    return {
        "max_swing": round(max_swing, 2),
        "teams": flagged,
        "note": ("Leans on a large bullpen recent-form swing — "
                 + "; ".join(parts)
                 + ". Recent 10-day bullpen ERA is a noisy signal; "
                 "treat this pick's confidence with extra caution."),
    }


#: A pick at or above this confidence whose one-run probability exceeds
#: CLOSE_GAME_ONE_RUN_MIN is flagged "close-game": the win probability may be
#: well-calibrated, but a large share of outcomes hinge on a one-run margin, so
#: the game is a near-coin-flip in run terms and could easily tip the other way.
CLOSE_GAME_CONF_MIN = 0.58       # lean-or-better picks only
CLOSE_GAME_ONE_RUN_MIN = 0.185   # one-run mass above this = notably close


def close_game_flag(top_prob: float, factor_breakdown: dict) -> dict | None:
    """
    Flag a confident pick that nonetheless sits on a close (one-run-margin)
    game. Uses p_one_run from the score matrix (already computed by the model).

    This is a TRANSPARENCY signal, not a calibration change: it does not alter
    the win probability. It surfaces the texture behind a number — a 63% pick
    where much of the mass is one-run games is a "could easily tip" pick, vs a
    63% pick that wins by a comfortable margin. Requested 2026-06-13 after the
    Yankees 63% / lost-8-5-but-close case: the kind of game worth highlighting
    as high-variance even when the probability is defensible.

    Returns {"p_one_run": float, "note": str} | None.
    """
    p_one_run = factor_breakdown.get("p_one_run")
    if p_one_run is None:
        return None
    if top_prob < CLOSE_GAME_CONF_MIN or p_one_run < CLOSE_GAME_ONE_RUN_MIN:
        return None
    return {
        "p_one_run": round(p_one_run, 4),
        "note": (f"Confident pick ({top_prob*100:.0f}%) on a close game: "
                 f"~{p_one_run*100:.0f}% of outcomes are decided by one run. "
                 "The probability may be sound, but the game is a near-coin-flip "
                 "in run terms and can tip on a single swing — high variance."),
    }


    """W / L / D from a team's perspective. Returns '' if no score yet."""
    if match.home_score is None or match.away_score is None:
        return ""
    is_home = match.home_team_id == perspective_team_id
    if match.home_score == match.away_score:
        # Baseball never draws but defensively handle
        return "D"
    if (is_home and match.home_score > match.away_score) or \
       (not is_home and match.away_score > match.home_score):
        return "W"
    return "L"


def compute_team_form(s, team: Team, limit: int = FORM_LIMIT) -> dict:
    """
    Recent results for a team across all their competitions.

    Returns:
        {
          "results": [...{date, opponent, home_or_away, result, score, competition, match_id}],
          "wins": int, "draws": int, "losses": int,
          "goals_scored": int, "goals_conceded": int,
        }
    """
    stmt = (
        select(Match)
        .options(
            selectinload(Match.home_team),
            selectinload(Match.away_team),
            selectinload(Match.competition),
        )
        .where(
            or_(
                Match.home_team_id == team.id,
                Match.away_team_id == team.id,
            ),
            Match.status == MatchStatus.FINISHED,
        )
        .order_by(Match.utc_date.desc())
        .limit(limit)
    )
    matches = list(s.execute(stmt).scalars())

    results = []
    wins = draws = losses = 0
    gs = gc = 0
    for m in matches:
        is_home = m.home_team_id == team.id
        opponent = m.away_team if is_home else m.home_team
        result = _result_letter(m, team.id)
        if result == "W":
            wins += 1
        elif result == "D":
            draws += 1
        elif result == "L":
            losses += 1
        # Goals/runs from this team's perspective
        if is_home:
            scored, conceded = m.home_score or 0, m.away_score or 0
        else:
            scored, conceded = m.away_score or 0, m.home_score or 0
        gs += scored
        gc += conceded
        results.append({
            "match_id": m.id,
            "date": m.utc_date,
            "opponent": opponent.name if opponent else "?",
            "opponent_id": opponent.id if opponent else None,
            "is_home": is_home,
            "result": result,
            "score": f"{scored}–{conceded}",
            "competition": m.competition.code if m.competition else "",
        })

    return {
        "results": results,
        "wins": wins, "draws": draws, "losses": losses,
        "goals_scored": gs, "goals_conceded": gc,
        "form_string": "".join(r["result"] for r in results[:5]),  # last 5 as e.g. "WWDLW"
    }


def compute_head_to_head(s, team_a: Team, team_b: Team, limit: int = H2H_LIMIT) -> dict:
    """
    Last N meetings between two teams.

    Returns:
        {
          "meetings": [...],
          "team_a_wins": int, "team_b_wins": int, "draws": int,
        }
    """
    stmt = (
        select(Match)
        .options(
            selectinload(Match.home_team),
            selectinload(Match.away_team),
            selectinload(Match.competition),
        )
        .where(
            or_(
                (Match.home_team_id == team_a.id) & (Match.away_team_id == team_b.id),
                (Match.home_team_id == team_b.id) & (Match.away_team_id == team_a.id),
            ),
            Match.status == MatchStatus.FINISHED,
        )
        .order_by(Match.utc_date.desc())
        .limit(limit)
    )
    matches = list(s.execute(stmt).scalars())

    a_wins = b_wins = draws = 0
    meetings = []
    for m in matches:
        result = _result_letter(m, team_a.id)
        if result == "W":
            a_wins += 1
        elif result == "L":
            b_wins += 1
        elif result == "D":
            draws += 1
        meetings.append({
            "match_id": m.id,
            "date": m.utc_date,
            "home": m.home_team.name if m.home_team else "?",
            "away": m.away_team.name if m.away_team else "?",
            "home_id": m.home_team_id,
            "away_id": m.away_team_id,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "competition": m.competition.code if m.competition else "",
            "a_was_home": m.home_team_id == team_a.id,
        })

    return {
        "meetings": meetings,
        "team_a_wins": a_wins,
        "team_b_wins": b_wins,
        "draws": draws,
    }


def compute_team_record(s, team: Team, competition_id: int | None, season: str | None) -> dict:
    """
    Aggregate W/L/D record for a team. If competition+season provided, scoped
    to that competition. Otherwise, all finished matches.

    For soccer: returns W/D/L + GF/GA + points (3W + 1D).
    For baseball: returns W/L + RS/RA + pct.
    """
    stmt = (
        select(Match)
        .where(
            or_(
                Match.home_team_id == team.id,
                Match.away_team_id == team.id,
            ),
            Match.status == MatchStatus.FINISHED,
        )
    )
    if competition_id is not None:
        stmt = stmt.where(Match.competition_id == competition_id)
    if season is not None:
        stmt = stmt.where(Match.season == season)

    matches = list(s.execute(stmt).scalars())

    wins = draws = losses = 0
    gs = gc = 0
    for m in matches:
        is_home = m.home_team_id == team.id
        scored = (m.home_score if is_home else m.away_score) or 0
        conceded = (m.away_score if is_home else m.home_score) or 0
        gs += scored
        gc += conceded
        if scored > conceded:
            wins += 1
        elif scored < conceded:
            losses += 1
        else:
            draws += 1

    is_baseball = team.sport == Sport.MLB
    total = wins + draws + losses
    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": gs,         # name kept generic; template renders sport-aware
        "goals_against": gc,
        "points": wins * 3 + draws,
        "pct": (wins / total) if total else None,
        "is_baseball": is_baseball,
    }


def build_prediction_narrative(
    pred,
    match,
    factor_breakdown: dict,
    home_form: dict,
    away_form: dict,
    h2h: dict,
) -> dict:
    """
    Turn the model's prediction + factors into prose for pre-match preview.

    Returns:
        {
          "summary": one-sentence prediction headline,
          "reasoning": [list of supporting points],
          "watch_for": [list of things to keep an eye on during the match],
        }
    """
    is_baseball = match.sport == Sport.MLB
    home_name = match.home_team.name
    away_name = match.away_team.name

    p_home = pred.home_win_prob or 0
    p_away = pred.away_win_prob or 0
    p_draw = pred.draw_prob

    # Top pick
    if p_draw is not None:
        candidates = [("H", p_home), ("D", p_draw), ("A", p_away)]
    else:
        candidates = [("H", p_home), ("A", p_away)]
    top_letter, top_p = max(candidates, key=lambda c: c[1])
    labels = {"H": f"{home_name} win", "D": "Draw", "A": f"{away_name} win"}

    # Confidence tier (Thing 1) — structured, reporting-only classification.
    # For baseball, treat the starter as "known" only if BOTH sides are
    # confirmed — if either is unknown, the pick rests on incomplete info and
    # the tier is capped at lean (label coherence with the 12.3 shrink).
    if is_baseball:
        starter_known = (factor_breakdown.get("home_starter_known", True)
                         and factor_breakdown.get("away_starter_known", True))
    else:
        starter_known = True
    tier = classify_tier(top_p, starter_known=starter_known)
    # Keep a human-readable confidence phrase for the summary line
    if tier["tier"] == "strong":
        confidence = "Strong lean"
    elif tier["tier"] == "lean":
        confidence = "Modest edge"
    else:
        confidence = "Toss-up"

    if tier["tier"] == "toss-up":
        summary = f"Toss-up: model slightly favors {labels[top_letter]} at {top_p * 100:.0f}% — not an actionable edge."
    else:
        summary = f"{confidence}: {labels[top_letter]} at {top_p * 100:.0f}%."

    # Expression signal (Thing 2) — is the total a stronger read than the side?
    over_prob = getattr(pred, "over_prob", None)
    expression = expression_signal(top_p, over_prob)

    # Bullpen recent-form swing flag (reporting only) — surfaces the
    # overconfidence-risk condition found 2026-06-05.
    bp_swing = bullpen_swing_flag(factor_breakdown) if is_baseball else None

    # Build reasoning lines
    reasoning = []

    # Form comparison
    home_w = home_form["wins"]
    home_l = home_form["losses"]
    away_w = away_form["wins"]
    away_l = away_form["losses"]
    if is_baseball:
        reasoning.append(
            f"Recent record: {home_name} {home_w}-{home_l}, "
            f"{away_name} {away_w}-{away_l} over last {len(home_form['results'])}/{len(away_form['results'])} games."
        )
    else:
        reasoning.append(
            f"Recent form (last {len(home_form['results'])}): "
            f"{home_name} {home_w}W-{home_form['draws']}D-{home_l}L · "
            f"{away_name} {away_w}W-{away_form['draws']}D-{away_l}L."
        )

    # Scoring trends
    if home_form["results"] and away_form["results"]:
        h_per_g = home_form["goals_scored"] / len(home_form["results"])
        a_per_g = away_form["goals_scored"] / len(away_form["results"])
        unit = "runs" if is_baseball else "goals"
        reasoning.append(
            f"{home_name} averaging {h_per_g:.1f} {unit}/game recently; "
            f"{away_name} {a_per_g:.1f}."
        )

    # Elo (soccer only — meaningful for that sport)
    if not is_baseball:
        elo_diff = (factor_breakdown.get("home_elo") or 0) - (factor_breakdown.get("away_elo") or 0)
        if abs(elo_diff) >= 75:
            stronger = home_name if elo_diff > 0 else away_name
            reasoning.append(
                f"Elo rating favors {stronger} by {abs(elo_diff):.0f} points."
            )

    # Cup mode callout
    if factor_breakdown.get("is_cup_mode"):
        h_bonus = factor_breakdown.get("home_league_bonus") or 0
        a_bonus = factor_breakdown.get("away_league_bonus") or 0
        if abs(h_bonus - a_bonus) >= 50:
            stronger_league = home_name if h_bonus > a_bonus else away_name
            reasoning.append(
                f"Cross-league cup tie: model adjusts for {stronger_league}'s "
                f"stronger home league."
            )

    # Lineup state (soccer)
    if not is_baseball:
        lk = factor_breakdown.get("lineup_kind")
        if lk == "confirmed":
            reasoning.append("Using confirmed lineups in prediction.")
        elif lk == "projected":
            reasoning.append("Lineups are projected — refresh closer to kickoff for confirmed XI.")

    # XI strength deltas (if meaningful)
    if not is_baseball:
        for side, name in (("home", home_name), ("away", away_name)):
            atk = factor_breakdown.get(f"{side}_xi_attack")
            base = factor_breakdown.get(f"{side}_baseline_attack")
            if atk is not None and base is not None and abs(atk - base) >= 5:
                direction = "below" if atk < base else "above"
                reasoning.append(
                    f"{name}'s announced XI is {direction} their season-average strength."
                )

    # Injuries
    if not is_baseball:
        h_inj = factor_breakdown.get("home_injuries_count") or 0
        a_inj = factor_breakdown.get("away_injuries_count") or 0
        if h_inj >= 4 or a_inj >= 4:
            reasoning.append(
                f"Injury count: {home_name} {h_inj} out, {away_name} {a_inj} out."
            )

    # MLB pitchers — include ERA when available, plus a brief read on quality
    if is_baseball:
        hp = factor_breakdown.get("home_pitcher")
        ap = factor_breakdown.get("away_pitcher")
        hp_era = factor_breakdown.get("home_pitcher_era")
        ap_era = factor_breakdown.get("away_pitcher_era")
        league_era = factor_breakdown.get("league_era") or 4.20
        if hp or ap:
            hp_str = hp or "—"
            ap_str = ap or "—"
            if hp_era is not None:
                hp_str = f"{hp_str} ({hp_era:.2f} ERA)"
            if ap_era is not None:
                ap_str = f"{ap_str} ({ap_era:.2f} ERA)"
            reasoning.append(f"Probable starters: {hp_str} (H) vs {ap_str} (A).")
            # Highlight pitcher edge if one side has a meaningfully better starter
            if hp_era is not None and ap_era is not None:
                gap = ap_era - hp_era  # positive = home pitcher better (lower ERA)
                if abs(gap) >= 1.0:
                    better = home_name if gap > 0 else away_name
                    reasoning.append(
                        f"Pitching edge: {better}'s starter is ~{abs(gap):.1f} ERA better."
                    )

        # Phase 12.2: bullpen quality callout when there's a meaningful gap.
        # Same 0.75 ERA threshold — bullpen aggregates have less spread so
        # a smaller difference is still notable.
        hb_era = factor_breakdown.get("home_bullpen_era")
        ab_era = factor_breakdown.get("away_bullpen_era")
        if hb_era is not None and ab_era is not None:
            bp_gap = ab_era - hb_era  # positive = home bullpen better
            if abs(bp_gap) >= 0.75:
                better = home_name if bp_gap > 0 else away_name
                reasoning.append(
                    f"Bullpen edge: {better}'s relief corps is ~{abs(bp_gap):.1f} ERA better."
                )

        # Phase 12.4: flag a bullpen that's caving or locked-in recently.
        for side, name in (("home", home_name), ("away", away_name)):
            detail = factor_breakdown.get(f"{side}_bullpen_detail")
            if not detail:
                continue
            season_era = detail.get("season_era")
            recent_era = detail.get("recent_era")
            if season_era is None or recent_era is None:
                continue
            delta = recent_era - season_era
            if abs(delta) >= 1.0:
                if delta > 0:
                    reasoning.append(
                        f"{name}'s bullpen has been caving lately "
                        f"({recent_era:.2f} recent ERA vs {season_era:.2f} season)."
                    )
                else:
                    reasoning.append(
                        f"{name}'s bullpen has been locked in lately "
                        f"({recent_era:.2f} recent ERA vs {season_era:.2f} season)."
                    )

        # Phase 12.3: flag reduced confidence when a starter is unknown.
        h_known = factor_breakdown.get("home_starter_known", True)
        a_known = factor_breakdown.get("away_starter_known", True)
        if not h_known or not a_known:
            if not h_known and not a_known:
                who = "Both starters"
            elif not h_known:
                who = f"{home_name}'s starter"
            else:
                who = f"{away_name}'s starter"
            reasoning.append(
                f"{who} unconfirmed — prediction confidence reduced to reflect "
                f"the missing information."
            )

        # Phase 12: park factor commentary
        pf = factor_breakdown.get("park_factor")
        venue = factor_breakdown.get("venue")
        if pf is not None and abs(pf - 1.0) >= 0.05 and venue:
            pct = (pf - 1.0) * 100
            if pct > 0:
                reasoning.append(
                    f"{venue} plays ~{pct:.0f}% above league average for run scoring — hitter's park."
                )
            else:
                reasoning.append(
                    f"{venue} plays ~{abs(pct):.0f}% below league average for run scoring — pitcher's park."
                )

        # Phase 12.1: cold/hot streak callouts. When a team's recent offensive
        # output diverges sharply from their season average, flag it. This is
        # the signal that drove the recent-form weighting change.
        for side, name in (("home", home_name), ("away", away_name)):
            rs_season = factor_breakdown.get(f"{side}_rs_season")
            rs_recent = factor_breakdown.get(f"{side}_rs_recent")
            games = factor_breakdown.get(f"{side}_games_recent") or 0
            if rs_season is None or rs_recent is None or games < 5:
                continue
            delta = rs_recent - rs_season
            if abs(delta) >= 1.0:
                direction = "cold" if delta < 0 else "hot"
                reasoning.append(
                    f"{name} {direction} streak: averaging {rs_recent:.1f} runs/game "
                    f"in last {games} (vs {rs_season:.1f} season)."
                )

    # H2H context (last 5 meetings)
    total_meetings = h2h["team_a_wins"] + h2h["team_b_wins"] + h2h["draws"]
    if total_meetings >= 3:
        h_wins, a_wins = h2h["team_a_wins"], h2h["team_b_wins"]
        if h_wins > a_wins * 2:
            reasoning.append(
                f"{home_name} have dominated the head-to-head ({h_wins}-{a_wins}{('-' + str(h2h['draws'])) if h2h['draws'] else ''} in last {total_meetings})."
            )
        elif a_wins > h_wins * 2:
            reasoning.append(
                f"{away_name} have dominated the head-to-head ({a_wins}-{h_wins}{('-' + str(h2h['draws'])) if h2h['draws'] else ''} in last {total_meetings})."
            )

    # ----- Watch-for: concrete in-game signals
    watch_for = []

    # Expected goals/runs callout
    xh = pred.expected_home_score
    xa = pred.expected_away_score
    if xh is not None and xa is not None:
        total = xh + xa
        if is_baseball:
            if total >= 9.0:
                watch_for.append(f"High total expected ({total:.1f} runs) — over 8.5 looks well supported.")
            elif total < 7.5:
                watch_for.append(f"Low total expected ({total:.1f} runs) — pitchers' duel feel.")
            else:
                watch_for.append(f"Total expected around {total:.1f} runs — close to standard line.")
        else:
            if total > 3.0:
                watch_for.append(f"High-scoring game expected ({total:.1f} xG total) — over 2.5 has model support.")
            elif total < 2.0:
                watch_for.append(f"Low-scoring game expected ({total:.1f} xG total) — tight defensive affair likely.")

    # Variance from draw (soccer)
    if p_draw is not None and p_draw >= 0.30:
        watch_for.append(f"Draw probability is high ({p_draw * 100:.0f}%) — single-result bets are risky.")

    # Big confidence gap
    if abs(p_home - p_away) >= 0.40:
        favorite = home_name if p_home > p_away else away_name
        watch_for.append(f"Heavy favorite ({favorite}) — upset variance is small but real.")

    # Thing 2: surface when the total is a stronger read than the side
    if expression is not None:
        watch_for.append(expression["note"])

    # Bullpen recent-form swing caution (reporting only)
    if bp_swing is not None:
        watch_for.append(bp_swing["note"])

    return {
        "summary": summary,
        "reasoning": reasoning,
        "watch_for": watch_for,
        "tier": tier,
        "expression": expression,
        "bullpen_swing": bp_swing,
    }
