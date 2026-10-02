# NHL-xG v8: the frozen declaration (#153; the LAST candidate on the 2025 test season)

**Status: DECLARED 2026-10-02 by ruling. Nothing has been run.** Registry id
`nhl-v8` (#212). The run refuses unless this declaration is in the registry
and has not run. After v8, the 2025 test season is **retired**: the registry
refuses any further declaration or run on it (docs/REGISTRY.md).

## The ruling (ARCHITECT 2026-10-02, verbatim)

"v7 VERDICT STANDS — FAIL 0.6885 vs 0.6866, calibration FAIL (50-70% bands
−6.2/−6.8pp); shot information +0.0023 clean (na-leak effect 0.0001). Record.
Registry: main must show prior reads = 7 once v6/v7 records are spliced.
v8 DECLARATION (last candidate on this test season): v7's xG unchanged; the
Elo's two scale parameters — the logistic divisor (rating-to-probability) and
k — are FITTED BY MAXIMUM LIKELIHOOD ON THE 2024 TRAINING SEASON ONLY
(walk-forward within 2024, grid declared in the doc, chosen before any 2025
read); home_adv stays 45.6; regression 0.25. This is a train-only fit, not a
tune. Same bar, same bands. One run.
DOCTRINE (from the external review, now binding): the 2025 test season has
been read 7 times. After v8 it is RETIRED as a test set; any later NHL
candidate declares 2026-27 (as it accrues, >=600 games) as its test season.
Record in docs/REGISTRY.md."

## v8 = v7 with two fitted scale parameters

- **xG:** v7's, unchanged (`nhl_xg.fit(..., na_level=False)`, 2023-24 only).
- **Elo:** v7's update, unchanged: the xG-margin direction, and |xG margin|
  through ln(margin+1) with mov_base 2.2. `NHLEloV8` is `NHLEloV7` with one
  addition: the expected score uses `1 / (1 + 10^(diff / scale))` with a
  fitted `scale`. v1–v7 keep their fixed 400.
- **Fixed, not fitted:**
  - **home_advantage = v7's 45.6.** It is derived from the 2024 home rate
    exactly as before (`home_advantage_from_rate`). It stays in Elo points,
    so its implied home probability moves with the fitted scale, as ruled.
  - **season regression 0.25.**
- **Fitted (train-only maximum likelihood):**
  - **The declared grid**, frozen here, before any run:
    - scale ∈ {300, 350, 400, 450, 500, 550, 600}
    - k ∈ {3, 4, 5, 6, 7, 8, 10, 12}
    - That is 56 pairs, and v1's (400, 6) is on the grid.
  - **Objective:** for each pair, a fresh v8 model walks the **2024
    training stream only**, predict-then-update. Its mean log-loss is the
    negative log-likelihood, and the minimum wins.
  - **Ties:** an exact tie goes to the pair closest to v1's (400, 6),
    scale first.
  - **Edges:** a choice on a grid edge is printed as "ON THE GRID EDGE". The
    grid is **not** widened after the fact.
  - **Isolation:** `nhl_backtest.fit_v8_scale_k` refuses any game outside
    the training season. The harness runs the fit and prints its choice
    and the best 10 pairs **before** any model scores a 2025 game (the v1
    reference included).
- **Same bar, same splits, same bands:**
  - train 2024, test 2025, preseason cut;
  - log-loss ≤ **0.6866**;
  - calibration bands (10pp, n ≥ 100, ±5pp);
  - ratings 1200–1800;
  - v1 reported beside it, with shot information = v1 − v8;
  - RPS reported.
  - The confirmation plan is v6's and v7's.
- **One run:** `python cli.py nhl-backtest --candidate v8`. The run records
  the fitted scale and k with its result.

## Prior reads, and the retirement

- At v8's run the 2025 test set carries **7 prior reads**: v1–v5 (seeds), v6
  and v7 once their run records are spliced.
- After v8 the test set is retired. Any later NHL candidate declares
  **2026-27** as its test season (scored as it accrues; ≥ 600 games).
