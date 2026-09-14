"""
Scenario layer — an HONEST what-if decomposition that sits AFTER prediction.

It does not alter the model and it never invents a probability. Every scenario
is either:
  (a) a real slice of the model's own score distribution (blowout, one-run
      game, favorite-comfortable, upset) — the number IS the model's, or
  (b) a tracked CONTEXT condition (bullpen fatigue, wind, streak) shown for
      awareness with an explicit "unvalidated — no measured effect" tag, and
      NO probability attached, because none of these has passed validation.

The distinction is the whole point: (a) carries measured numbers, (b) carries
context but never a fabricated weight. If a condition ever validates (Stage 2 /
upset-log), it graduates from (b) to a real adjustment — but until then it is
presented as context, not edge.

This gives a richer picture of HOW a game could go without manufacturing false
precision. Confidence on each (a) scenario = its actual probability from the
distribution. Confidence on (b) items = None (explicitly "context only").
"""
from __future__ import annotations


def build_scenarios(pred: dict, unused_context: dict | None = None) -> dict:
    """
    pred: the exported 'prediction' dict (top_pick, probs, p_blowup, p_one_run,
          per-team blowup, expected runs).
    unused_context: the game's unused_context block (weather/bullpen/streak/ump).

    Returns {"distribution_scenarios": [...], "context_flags": [...],
             "_note": "..."} — distribution scenarios carry real probabilities;
    context flags carry no probability (unvalidated).
    """
    probs = pred.get("probabilities") or {}
    p_home = probs.get("home_win")
    p_away = probs.get("away_win")
    top = pred.get("top_pick")
    top_prob = pred.get("top_pick_prob")
    p_blowup = pred.get("p_blowup")
    p_home_bl = pred.get("p_home_blowup")
    p_away_bl = pred.get("p_away_blowup")
    p_one_run = pred.get("p_one_run")
    eh = pred.get("expected_home")
    ea = pred.get("expected_away")

    fav_is_home = (top == "home_win")
    fav_label = "home" if fav_is_home else "away"
    dog_label = "away" if fav_is_home else "home"
    fav_prob = top_prob
    dog_prob = (p_away if fav_is_home else p_home)

    scen = []  # each: {name, probability (real), basis}

    # --- 1. favorite holds vs upset (the core split, straight from win probs) ---
    if fav_prob is not None:
        scen.append({
            "name": f"{fav_label} favorite wins",
            "probability": round(fav_prob, 3),
            "basis": "model win probability",
        })
    if dog_prob is not None:
        scen.append({
            "name": f"{dog_label} upset",
            "probability": round(dog_prob, 3),
            "basis": "model win probability (underdog side)",
        })

    # --- 2. game-shape scenarios from the score distribution ---
    if p_one_run is not None:
        scen.append({
            "name": "one-run nailbiter",
            "probability": round(p_one_run, 3),
            "basis": "score distribution: P(decided by 1 run)",
        })
    if p_blowup is not None:
        scen.append({
            "name": "blowout (either team ≥7 runs)",
            "probability": round(p_blowup, 3),
            "basis": "score distribution: P(either team ≥7)",
        })
    # per-team explosion, whichever side is the bigger blowup risk
    if p_home_bl is not None and p_away_bl is not None:
        if p_home_bl >= p_away_bl:
            scen.append({
                "name": "home team explodes (≥7 runs)",
                "probability": round(p_home_bl, 3),
                "basis": "score distribution: P(home ≥7)",
            })
        else:
            scen.append({
                "name": "away team explodes (≥7 runs)",
                "probability": round(p_away_bl, 3),
                "basis": "score distribution: P(away ≥7)",
            })

    # sort distribution scenarios by probability desc for readability
    scen.sort(key=lambda x: -(x["probability"] or 0))

    # --- 3. context flags: tracked conditions, NO probability (unvalidated) ---
    flags = []
    uc = unused_context or {}

    wl = uc.get("won_last_game") or {}
    streak = uc.get("streak_context") or {}
    for side in ("home", "away"):
        sc = streak.get(side)
        if sc and sc.get("on_winning_streak"):
            flags.append({
                "condition": f"{side} team on a {sc.get('current_streak')}-game winning streak "
                             f"(season avg {sc.get('avg_win_streak_len')}, max {sc.get('longest_win_streak')})",
                "effect": None,
                "status": "context only — streak carries no validated predictive effect",
            })

    bull = uc.get("bullpen_availability") or {}
    for side in ("home", "away"):
        b = bull.get(side)
        if b and isinstance(b, dict) and b.get("heavy_outings", 0) >= 2:
            flags.append({
                "condition": f"{side} bullpen: {b.get('heavy_outings')} heavy outings in last 3d "
                             f"({b.get('relievers_used')} relievers used)",
                "effect": None,
                "status": "context only — bullpen fatigue failed Stage-1 validation (noise)",
            })

    weather = uc.get("weather") or {}
    we = weather.get("wind_effect")
    if we and abs(we.get("out_mph", 0)) >= 4:
        flags.append({
            "condition": f"wind {we.get('label')}",
            "effect": None,
            "status": "context only — wind effect not validated as predictive",
        })

    ump = uc.get("plate_umpire") or {}
    if ump.get("name") and ump.get("tracked_n", 0) >= 20:
        flags.append({
            "condition": f"plate umpire {ump['name']}: {ump.get('tracked_runs_per_game')} R/G "
                         f"over {ump.get('tracked_n')} games",
            "effect": None,
            "status": "context only — umpire run-env not validated as predictive",
        })

    return {
        "distribution_scenarios": scen,
        "context_flags": flags,
        "_note": ("Distribution scenarios carry the MODEL'S OWN probabilities "
                  "(real slices of its score distribution). Context flags carry "
                  "NO probability — they are tracked conditions with no validated "
                  "predictive effect, shown for awareness only. Nothing here alters "
                  "the prediction."),
    }
