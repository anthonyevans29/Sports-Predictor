# Historical Database — Feasibility Assessment (2026-07-06)

Question: can we pull last season (2025) and run our prediction + tracking
process across those games, to get a full-season subset instead of 2 weeks?

Short answer: **YES for the core data and most tracked signals — because the
MLB Stats API is free and has deep historical depth.** But data types tier by
retrievability. Below is what each backfill can and can't recover, so the
historical DB's contents are honest.

Retrievability tiers: ✅ fully historical · ⚠️ historical but heavier/partial ·
⛔ not recoverable for past games (live-only).

---

## ✅ TIER 1 — fully recoverable, this is the backbone
These come straight from MLB Stats API historical endpoints (free, deep):

- **Schedule + final scores** (`/schedule?season=2025`): every game, teams,
  date, venue, result. `sync-matches --season 2025` already takes the param.
- **Boxscores** (per game): umpires (officials block), per-pitcher appearances
  + pitch counts, team batting lines. So our umpire table AND bullpen/starter
  appearance tables backfill cleanly for all of 2025.
- **Probable/actual starters** and their stats.
- **Team + player season stats.**

This alone is huge: it means run-shrink inputs, bullpen availability, starter
workload, umpire environment, and won-last-game / streak KPIs ALL backfill for a
full prior season. That's the training runway the input-search idea needs.

## ⚠️ TIER 2 — recoverable but with caveats
- **Weather**: Open-Meteo has a HISTORICAL endpoint (archive API) — you can pull
  past weather by lat/long + date. So weather IS backfillable, but via a
  different Open-Meteo endpoint than the forecast one we use live, and it's a
  separate call per game. Doable, just more work + rate-limited. Wind direction
  included historically, so park_wind classification works retroactively.
- **Predictions themselves**: we can RE-RUN predict_game across 2025 games using
  the current model, producing a "what would the model have said" backfill. BUT
  (critical) — this uses the CURRENT model/config on past games. It's a
  backtest, not a record of live predictions. Useful for calibration/training;
  NOT a substitute for real forward CLV (you can't backfill what the market did
  vs a prediction that didn't exist at the time).

## ⛔ TIER 3 — NOT recoverable for past games
- **Odds / CLV snapshots**: this is the big one. The whole CLV apparatus depends
  on capturing the market AT MULTIPLE POINTS before each game. You cannot
  reconstruct 2025's line MOVEMENT after the fact — API-Baseball gives current
  odds, not a historical intraday movement archive we can trust. So the
  historical DB can have 2025 games, results, and closing-ish odds if available,
  but NOT the toward/away line-movement CLV signal. CLV stays forward-only.
- **Live lineup-confirmation timing** — irrelevant historically anyway.

---

## What a 2025 backfill actually gives us

A full prior season where we can, for every game:
- know the result, venue, umpire, both bullpens' recent usage, starter workload,
  weather (via archive endpoint), streak state;
- RE-RUN the current model to get its prediction (a backtest);
- → which means we can TRAIN and CALIBRATE candidate models (incl. ones using
  the tracked inputs) on ~2,400 games instead of ~1,350, and validate on real
  out-of-sample outcomes.

What it does NOT give us:
- real CLV history (line movement is not reconstructable);
- a record of what the model "would have predicted live" that's meaningful for
  edge — a backtest tells you calibration, not market-beating.

---

## Honest read on VALUE (not just feasibility)

The backfill is genuinely worth doing for ONE main reason: **it gives the
input-search idea a real training runway.** Right now weather/bullpen/streak
exist for ~2 weeks — too little to train a candidate on. Backfill 2025 and those
signals exist for a full season, so a candidate model using them can actually be
trained and held-out-scored. That's the precondition we said we needed.

Two honest cautions:
1. **It's a backtest, not live validation.** Re-running the model on 2025 tells
   us calibration and lets us train, but a signal looking predictive in-sample on
   2025 is a hypothesis, not proven edge — same discipline as always. Backtests
   overfit; out-of-sample (2026) confirmation still required.
2. **It doesn't touch the edge question.** No historical CLV means the backfill
   can make the model a better-calibrated thermometer but can't tell us if it
   beats the close. That answer still only comes from forward CLV.

## Recommended shape (if we build it)
1. `sync-matches --season 2025` → schedule + results (backbone).
2. Backfill boxscore-derived tables for 2025: umpires, appearances (extend the
   existing --backfill commands to accept --season 2025).
3. Weather backfill via Open-Meteo ARCHIVE endpoint (new adapter method, per
   game, rate-limited — the one real build).
4. A `backtest` command: re-run predict_game across 2025 games, store as a
   backtest cohort (clearly labelled NOT live), for calibration + training.
5. THEN the input-search `improve` mode has a real season to train/validate on.

Sequencing: still gate on the July 8 CLV review before deciding how hard to
chase model improvement — but the backfill itself is safe, useful groundwork
that makes any later input-search actually trainable.
