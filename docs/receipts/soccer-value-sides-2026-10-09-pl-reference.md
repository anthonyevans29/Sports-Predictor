# PL reference — value sides against the close, PL 2024/25 + 2025/26

For reference only: the page of its own the declaration names (ARCHITECT 2026-10-09, addendum 21 item 6, amended by addendum 23 item 2; Issue #383). The declaration, the amendment and the reconciliation are on the receipt's main page. **PL's live read (#92) stands as declared and is not this.** Not gate evidence and not a policy. Generated 2026-10-09T21:00:12Z.

## Method

- Candidate as gated: production v22, rho -0.1, elo_goal_coeff 0.0008 (the run record's; never refit). The gate's own walk: run_soccer_backtest per league-season from a cold start, min_prior 40, regular-season rows (F3), same-kickoff fixtures predicted before any updates (F5).
- Close: fdcuk_close 1X2, de-vigged proportionally (1/price over the three legs), as market_side does.
- Value outcome: the largest model p minus close p (ties: first of home, draw, away). Top pick: the largest model p (same tie rule). Edge = the value outcome's model p minus close p, in pp; a bucket holds its lower edge at market_side's tolerance (1e-09): 5.0 is in 5 to 10; the value edge is never negative, so under 5 is 0 to 5.
- Hit: the value outcome happened (90-minute result as stored). Flat stake 1 on the value outcome at the close's fair decimal price 1/close p; return = mean profit per stake.
- Bootstrap: percentile 95% intervals; the unit is the match, resampled with replacement within the cell; 10000 resamples; numpy default_rng, seed 20261009 (fresh per cell); the return interval comes from the same draws. A cell of fewer than two matches prints no interval (—).
- PL rows: the same walk at the same params over PL 2024/25 and 2025/26 (each season from a cold start, pooled over its two seasons as each league is), every scored match; no reconciliation (PL has no run record).

Scored 680 · priced 340 (340 without a full fdcuk_close 1X2).

## Tables

### PL

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 56 | 0.544 | 0.516 | 41.1% | -10.50 [-22.52, +1.83] | -22.2% [-47.2%, +4.1%] |
| under 5pp | no | 83 | 0.244 | 0.217 | 16.9% | -4.88 [-12.64, +3.47] | -19.2% [-56.7%, +22.5%] |
| 5 to 10 | yes | 61 | 0.553 | 0.479 | 47.5% | -0.36 [-12.68, +11.97] | +4.1% [-26.1%, +35.1%] |
| 5 to 10 | no | 52 | 0.264 | 0.193 | 26.9% | +7.64 [-3.64, +20.01] | +30.7% [-28.0%, +93.9%] |
| 10 to 15 | yes | 46 | 0.557 | 0.430 | 41.3% | -1.66 [-15.25, +12.33] | -4.7% [-39.3%, +32.3%] |
| 10 to 15 | no | 17 | 0.288 | 0.169 | 29.4% | +12.47 [-6.32, +34.79] | +43.4% [-47.3%, +159.5%] |
| 15 and over | yes | 17 | 0.521 | 0.329 | 35.3% | +2.40 [-16.58, +22.82] | -11.3% [-67.3%, +51.4%] |
| 15 and over | no | 8 | 0.300 | 0.116 | 12.5% | +0.90 [-13.08, +25.88] | -13.4% [-100.0%, +159.9%] |
| 5 and over | yes | 124 | 0.550 | 0.440 | 43.5% | -0.46 [-8.62, +7.91] | -1.3% [-22.2%, +20.3%] |
| 5 and over | no | 77 | 0.273 | 0.180 | 26.0% | +8.01 [-1.03, +17.73] | +28.9% [-19.2%, +81.1%] |

### The 5-and-over row by the value outcome's kind

| league | value outcome | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| PL | home | 73 | 0.498 | 0.400 | 38.4% | -1.65 [-12.68, +9.43] | +0.3% [-32.4%, +35.7%] |
| PL | draw | 18 | 0.263 | 0.185 | 27.8% | +9.26 [-8.91, +31.07] | +46.1% [-59.7%, +168.0%] |
| PL | away | 110 | 0.438 | 0.326 | 37.3% | +4.66 [-3.45, +12.93] | +11.1% [-19.1%, +43.4%] |
