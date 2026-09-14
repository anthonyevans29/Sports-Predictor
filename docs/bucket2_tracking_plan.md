# Bucket 2 — Tracking Plan (2026-06-29)

Goal: start **logging** each data point into append-only tables now, with
**nothing feeding the model**. Same pattern as OddsSnapshot/CLV — instrument
first, conclude later, let each dataset earn its way in (or not) once it has
sample. Tracking carries no overfitting risk because predictions don't change.

Sorted by capture cleanliness. ✅ = clean capture from a feed we already use ·
⚠️ = capturable but derived/fiddly · ⛔ = needs new vendor/scraping (defer).

Existing assets that help: `src/adapters/mlb_stats_api.py` already calls
`/boxscore` (has the `officials` block) and `/feed/live`, and already has
bullpen-recent logic. `Lineup` and `BullpenSeasonStats` tables already exist.

---

## ✅ 1. Umpire tracking — CLEAN, build now
- **Source:** `/game/{gamePk}/boxscore` → `officials` block lists the plate
  umpire by name + role. Already the endpoint the adapter hits for final scores,
  so it's a field-extraction, not a new call. (Backfill: same endpoint works on
  completed games, so we can seed this season.)
- **Table `umpire_game`** (append-only, one row per finished game):
  game_id, date, plate_umpire, home_team, away_team, total_runs, total_line,
  strikeouts (both teams), walks (both teams), home_runs.
- **Tracks toward:** per-umpire runs/game, K/BB environment, over/under tendency.
- **Honest caveat:** ~25-30 plate games per ump per season → high variance →
  USELESS for months. Report must always show n. This is a measurement
  instrument, not a near-term input. Backfilling this season's completed games
  is the single biggest lever for making it useful sooner.

## ✅ 2. Weather tracking — CLEAN, build now (and it's a real gap)
- **Finding:** Open-Meteo is wired but **display-only** — `src/web/weather.py`
  + templates show it; the model/training path has ZERO weather references. We
  thought it was an input; it is not. So this is both a tracking task AND the
  most defensible eventual feature.
- **Source:** existing Open-Meteo client + a venue→lat/long table (~30 parks,
  static). Roof state for the ~7 retractable parks is the one gap (Open-Meteo
  can't see a closed roof) — default domes to closed, flag retractables.
- **Table `game_weather`** (one row per game, captured near first pitch):
  game_id, date, venue, temp_f, wind_speed, wind_dir, humidity, precip_prob,
  roof_state (known/assumed/open/closed), captured_at.
- **Tracks toward:** wind-out/temp vs actual total — and because weather is a
  *mechanistic* run driver (not a market-disagreement bet), it's the lowest-risk
  thing to eventually feed into the totals projection.

## ⚠️ 3. Bullpen availability — CAPTURABLE (derive), build the tracker
- **Source:** NO clean endpoint. Derive from `/boxscore` (or `/feed/live`) per
  game: which relievers appeared + pitch counts. Adapter already has
  bullpen-recent logic to extend. Roll over last 3 days per team.
- **Table `bullpen_usage`** (append-only, one row per reliever-appearance):
  game_id, date, team, pitcher, pitches, back_to_back flag (derived at report).
  Then a view/report computes per-team "arms used last 3d / on B2B / est.
  unavailable" for a given date.
- **Tracks toward:** your hypothesis — do depleted-bullpen favorites underperform
  their predicted win rate? (Can ALSO be tested retroactively via the diagnostic
  on existing game logs, separate from this forward tracker.)
- **Caveat:** appearance attribution is clean; "unavailable" is a judgment rule
  (e.g. 30+ pitches yesterday OR pitched 3 straight) — store the raw, derive the
  flag at read time so we can tune the rule later.

## ⚠️ 4. Starter workload / leash — CAPTURABLE (derive), pairs with #3
- **Source:** same game-log derivation as #3 — recent pitch counts per starter,
  days rest, IP trend. Probable pitchers already synced; this adds their history.
- **Table `starter_workload`**: pitcher, game_id, date, pitches, ip, days_rest.
  Shares the same nightly pull as bullpen usage — one job, two tables.
- **Tracks toward:** short-leash → totals/F5 routing. Lower priority than #3 but
  nearly free if we're already walking the game logs for bullpen.

## ⚠️ 5. Lineup confirmation quality — PARTLY EXISTS (Lineup table already there)
- **Source:** `/boxscore` + schedule hydrate gives confirmed lineups once posted
  (~3-4h pre-game). A `Lineup` table already exists — check what populates it.
- **Track:** confirmed-vs-projected flag, star-regular-missing flag (regular
  absent from posted lineup).
- **Caveat:** lineups post LATE — operationally fiddly for a morning card.
  Capturable, but timing means it's more useful as an at-game-time check than a
  morning input. Medium priority.

## ✅ 6. Travel / getaway / fatigue — CLEAN (derive from schedule we have)
- **Source:** 100% derivable from the schedule already in the DB — prior game
  location + time → travel distance, day-after-night, getaway day, doubleheader.
- **Table:** none needed — compute at report time from existing Match rows.
- **Caveat:** low predictive value (betting model said "small weight only").
  Cheap enough to add as a derived field whenever; no urgency, no new table.

## ⛔ 7. Defensive OAA / catcher framing — DEFER (new vendor)
- **Source:** Statcast-derived; NOT in the basic Stats API. Needs Baseball
  Savant scraping or a paid vendor. Real new dependency.
- **Value:** small, situational. Lowest value-per-effort on the list.
- **Verdict:** don't track yet. Revisit only if a validated edge demands it.

---

## Proposed build order (tracking only — nothing feeds the model)
1. **Umpire table + sync + backfill this season** (✅ cleanest, backfill makes it
   useful soonest, directly serves your umpire thesis).
2. **Weather table + capture** (✅ clean, and surfaces the real "we thought we had
   this" gap; sets up the most defensible future feature).
3. **Bullpen-usage + starter-workload tracker** (⚠️ one shared nightly job from
   game logs; serves the bullpen-favorite hypothesis going forward).
4. **Lineup-confirmation flags** (⚠️ extend existing Lineup table; lower urgency).
5. **Travel/fatigue** (✅ derived, no table — add whenever, low value).
6. **OAA/framing** (⛔ deferred).

## Two hard rules carried from everything else we've built
- **Append-only, model-blind.** Every table here is written by a sync command and
  read by a report command. NOTHING joins into predictions until a dataset has
  sample AND a reason (CLV or a diagnostic) to believe it's a real edge.
- **Reports always show n.** Per-umpire/per-team numbers are noise until sample is
  large. The report format must force the sample size next to every figure, so
  nobody fades an umpire on 8 games.

## Parallel (not a table): the retroactive bullpen diagnostic
Separately from the forward tracker, we can test the bullpen-favorite hypothesis
NOW against existing game logs: did favorites with depleted bullpens underperform
their predicted win rate? That's a measurement on data we already have — it can
rule the thesis in/out before the forward tracker has accrued anything.
