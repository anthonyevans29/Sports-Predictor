# NHL-xG v7: the frozen declaration (#153; a correctness fix to v6)

**Status: DECLARED 2026-10-02 by ruling. Nothing has been run.** Registry
id `nhl-v7` (#212). The run refuses unless this declaration is in the
registry and has not run.

## The ruling (ARCHITECT 2026-10-02, verbatim)

"v6 VERDICT STANDS — FAIL 0.6886 vs 0.6866, calibration FAIL (50-70% bands
−6.4/−6.5pp); SHOT INFORMATION +0.0023, the first positive increment of six
NHL candidates. Record in the registry (prior reads now 6).
DEFECT: xG level shot:na (+3.02) is a label leak — missing shot type occurs
only on ~0.3% of goals. Correctness fix, not a tune: declare v7 = v6 with the
"na" level REMOVED (events without shot type take the baseline level),
nothing else changed, same bar, same splits. One run after declaration. If v7
still fails, the shot-quality floor is measured at this representation; the
next information class is goalie × shot quality (goals saved above expected
per goalie, as-of), declared separately as v8."

## v7 = v6 with one change

- **The change:** the xG model's shot-type factor loses its `na` level.
  - An event without a shot type takes the **baseline level** (all
    shot-type dummies 0).
  - The baseline is chosen as before (the most frequent level), but now
    among the typed levels and `other` only.
  - Implemented as `nhl_xg.fit(..., na_level=False)` and
    `XGModel.na_level = False`.
- **Why it is a correctness fix:** a missing shot type is not a property of
  the shot. It is a property of the outcome: the feed omits it on non-goal
  events far more often than on goals (~0.3% of goals). The level therefore
  encoded the label (+3.02 in v6).
- **Everything else is exactly v6** (`docs/specs/nhl-xg-v6.md`, ratified):
  - rules R1–R7;
  - the 2023-24-only fit, with the predates-training assertion;
  - the features: distance, angle, situation class, and the nullable shot
    type minus `na`;
  - IRLS with ridge 1.0;
  - game xG;
  - the Elo (`NHLEloV7` is `NHLEloV6`, renamed): the xG-margin direction,
    |xG margin| through ln(margin+1), and v1's constants;
  - the fallback to goals;
  - the no-same-game-leakage property.
- **Same bar, same splits:**
  - train 2024, test 2025, preseason cut;
  - log-loss ≤ **0.6866**;
  - the calibration bands (10pp, n ≥ 100, ±5pp);
  - ratings 1200–1800;
  - v1 reported beside it, with shot information = v1 − v7;
  - RPS reported.
- **Registry:** the 2025 test set carries **6 prior reads** at v7's run
  (v1–v5, and v6 once its run record is committed). The confirmation plan is
  v6's: the first 150 NHL 2026-27 regular-season games after the verdict;
  log-loss ≤ 0.6866 **and** strictly below v1 on the same games.

## If v7 fails

The shot-quality floor is then measured at this representation. The next
information class is **goalie × shot quality** (goals saved above expected
per goalie, as-of). It is declared separately as v8, with nothing carried
over silently.

## Run order (operator)

1. Commit the laptop's v6 run record (`docs/registry/experiments.json` +
   `docs/registry/ids/nhl-v6.txt`). The v6 verdict is then recorded on it.
2. `.backup`.
3. `python cli.py nhl-backtest --candidate v7`, **once**. Paste the output
   and the `docs/registry/` diff.
