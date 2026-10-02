# NHL-xG v6: the frozen declaration (#153 part 2)

**Status: RATIFIED 2026-10-02 (with the update-direction clarification in §4). Nothing has been run.**
Ratified (verbatim): "Exclusions (blocked, empty-net, missing coords, shootouts), home-defending-side orientation, 2023-24-only fit with the predates-training check, the no-same-game-leakage proof, and the confirmation window (first 150 games of 2026-27 after the verdict) — all ratified. Bar unchanged 0.6866."
Registry id `nhl-v6` (#212). Every choice below is fixed before any data run
(law 3). The code reads these constants from `src/models/nhl_xg.py`, and the
run refuses unless this declaration is in the registry.

## Rulings this implements

- **2026-09-30 (#153):** "an xG model = logistic(distance, angle, situation
  class, event type) fitted ONLY on 2023-24 shots, frozen; team rolling
  xG-for/against per 60 (decay 60 days, shrunk); v6 = v1 Elo whose
  margin-of-victory input is replaced by xG margin (or updated on xG margin
  with the same k/mov_base) — declare which before the run. Same splits (train
  2024, test 2025), same bar <= 0.6866, calibration bands, RPS. Report v1
  beside it and 'shot information' = v1 − v6."
- **2026-10-01 (external review, P1-2, #210):** "event code = eligibility +
  target only; shotType = nullable feature; pre-commit empty-net,
  blocked-shot, orientation, missing-coordinate rules; fit on 2023-24 only;
  add a no-same-game-leakage proof."

## 1. Events: eligibility and target only

- **Eligible:** `shot-on-goal`, `missed-shot` and `goal`, i.e. unblocked
  attempts (Fenwick).
- **Target:** `goal` = 1, otherwise 0.
- **The event code is never a feature.** It decides only whether a play is
  an attempt and whether the attempt scored.

## 2. Pre-committed rules

The first rule that applies decides. Every exclusion is counted and printed in
the run receipt.

| Rule | When | Result |
|---|---|---|
| R1 blocked shot | `blocked-shot` | **excluded**: its coordinates are the block site, not the shot |
| R1 not an attempt | any other non-eligible type | excluded |
| R2 shootout | period type `SO`, or period >= 5 in the regular season | excluded |
| R3 shooter side | roster side, else the play owner; neither | excluded |
| R4 situation | `situationCode` missing or malformed (not 4 digits) | excluded |
| R5 empty net | the **defending** team's goalie digit is 0 | **excluded** (from the fit and from game xG) |
| R6 coordinates | x or y missing | **excluded** |
| R7 orientation | home attacks the net opposite `homeTeamDefendingSide` (left → x = +89, right → x = −89); away attacks the other. Missing side | excluded |

## 3. The xG model, frozen

- **Fit set:** stored shot events with 2023-10-01 <= game start < 2024-10-08
  (the 2024 train opener), game types 2 and 3. The fit refuses any shot
  outside this window.
- **Features:**
  - distance to the attacked net (ft);
  - angle (degrees, 0 = straight on);
  - situation class from the shooter's view: EV (equal skaters, the
    baseline), PP or SH;
  - **shot type, nullable:** a level of its own for each type with at least
    100 fit events; rarer types become `other`; a missing type becomes `na`.
    The baseline is the most frequent level.
- **Fit:** logistic regression by IRLS, ridge 1.0 on the non-intercept
  coefficients (for numerical stability only), at most 50 iterations.
- **Game xG:** the sum of xG over each side's rule-passing events, in all
  situations except empty net.

## 4. v6, and which reading of the ruling

**v6 = v1 updated ON THE xG MARGIN (RATIFIED 2026-10-02, verbatim):** "the
Elo update's DIRECTION comes from the sign of the xG margin and its MAGNITUDE
from |xG_home − xG_away| through the same ln(margin+1); the actual result is the
scoring label only. (Replacing outcome noise is the whole hypothesis; keeping
the actual winner as the update direction would be a half-measure.)"

- The update's result term is 1 when xG_home > xG_away and 0 when it is
  lower. An exact xG tie has margin 0, so ln(1) = 0 and nothing moves.
- The mov multiplier's winner gap is taken from the xG winner.
- The actual result is used only to score the prediction (log-loss, bands,
  RPS). It never moves a rating in an xG-covered game.

- v1's constants are unchanged: k 6.0, mov_base 2.2, season regression 0.25,
  home advantage from the 2024 home rate.
- A game with no rule-passing event falls back to v1 on goals: the goal
  result's direction and the goal margin. The count is printed.

**Rolling team xG** for and against, per 60 (half-life 60 days, shrunk toward
the league mean with a 10-game prior, per game at regulation length) is
**reported only**. It is not a v6 input.

## 5. No same-game leakage: the proof

- The xG model is fit on 2023-24 only. The run asserts the last fit game is
  before the first train game (2024 opener), or refuses.
- A game's xG margin is read **only in `update(g)`, after `predict(g)`**.
  `tests/test_nhl_xg_v6.py` proves it: changing a test game's own shots leaves
  that game's prediction identical, and changes only later games.

## 6. Gate (unchanged), registry and confirmation

- **Gate:** same stream (train 2024, test 2025, preseason cut), same gate:
  log-loss <= **0.6866** (beats the home rate by 0.010), the calibration bands
  (10pp, n >= 100, ±5pp), ratings 1200–1800. RPS is reported. v1 is reported
  beside it, with **shot information = v1 − v6**. A tie is a rejection.
- **Registry:** the run records its scored ids and result. The test set has
  **5 prior reads** (v1–v5), shown in the receipt. A second run is refused.
- **Confirmation window (doctrine #212; RATIFIED):** on a
  PASS, v6 is scored in shadow on the **first 150 NHL 2026 regular-season
  games after the verdict date** (about two weeks; never seen by any fit).
  - **CONFIRMED** only if its log-loss on those games is <= 0.6866 **and**
    strictly below v1's on the same games.
  - Anything else is NOT_CONFIRMED, and the bar does not move.
  - **Executable plan** (registry, #222 review fix): `{n_games: 150, metric: log_loss, bar: 0.6866, must_beat_reference: true, reference: v1 on the same games}`. The confirmation read records its 150 scored ids and both log-losses, and the outcome is computed. A read before the verdict, with fewer than 150 games, or containing any 2025 test-set game is refused.

## 7. Run order (operator)

1. `.backup`.
2. `python cli.py nhl-shot-sync --start 2023-10-01`, then paste the coverage
   block (P1–P6).
3. After ratification, run `python cli.py nhl-backtest --candidate v6` once,
   then paste the output and the changed `docs/registry/` files.
