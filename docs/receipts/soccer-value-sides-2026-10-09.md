# Soccer value sides against the close — soccer-expansion-v1 scored ids

Read-only receipt (ARCHITECT 2026-10-09, addendum 21 item 6, amended by addendum 23 item 2; Issue #383). Generated 2026-10-09T21:00:12Z. **Not gate evidence and not a policy.**

## The declaration (as issued; the withdrawn sentence struck through, not deleted)

> "The operator's question is whether the model's value sides pay against the close. The gate's run record holds the count only (512 hits on 1,281 picks at 5pp or more), not the prices. Declared now so that it is not fished later (the #354 pattern). No other cut is added after the fact.
> - Matches: the gate's 3,445 scored ids, priced by the candidate as gated (the run record's rho and elo_goal_coeff, the gate's own walk), against the stored fdcuk_close, de-vigged as market_side does.
> - The value outcome of a match is the outcome with the largest model probability minus close probability.
> - Rows: league (PD, SA, BL1, FL1, ELC, and pooled) by edge bucket (under 5pp; 5 to 10; 10 to 15; 15 and over; and 5 and over as one row, ~~which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of 373~~ [WITHDRAWN, ARCHITECT 2026-10-09 addendum 23 (b)]) by whether the value outcome is the model's top pick.
> - One more table, for the 5-and-over row only: by the value outcome's kind (home, draw, away).
> - Columns: n, mean model p, mean close p, hit rate, hit minus close in pp with a seeded bootstrap 95% interval, flat-stake return at the close's fair price with its interval.
> - The same tables for PL 2024/25 and 2025/26 on a page of their own, for reference. PL's live read (#92) stands as declared and is not this.
> It is not gate evidence and not a policy. The operator runs it; the receipt goes to docs/receipts by PR."

## The amendment (ARCHITECT 2026-10-09, addendum 23 item 2, verbatim)

> "(a) What was known. For 'The gate's run record holds the count only (512 hits on 1,281 picks at 5pp or more), not the prices.' read: 'Known before this declaration, from the run record: per league, the model's top picks at 5pp or more over the close, with their count, hits and mean edge (PD 79 of 212 at 11.7pp, SA 88 of 225 at 11.3pp, BL1 115 of 266 at 12.4pp, FL1 93 of 205 at 11.2pp, ELC 137 of 373 at 11.7pp), and the model's and the close's log-loss on the same games. Not known: any price, any single match, any figure for a side that is not the top pick, any figure under 5pp or by bucket. The buckets are round numbers, chosen knowing that this cohort's mean edge is near 12pp.'
> (b) The cohort sentence is WITHDRAWN: 'which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of 373'. Those cohorts are the gate's own selection, the model's top pick at 5pp or more over the close (market_side). The value outcome is another selection, and it stays as declared. In its place, before any table: 'Reconciliation. Under market_side's own rule the receipt's walk reproduces, per league, the run record's n_priced, both log-losses, and the cohort's count, hits and mean edge. If it does not, the receipt prints the difference and stops: no table.'
> (c) The bootstrap. 'Percentile 95% interval. The unit is the match, resampled with replacement within the cell; 10,000 resamples; seed 20261009. The return interval comes from the same draws. A cell of fewer than two matches prints no interval.'
> (d) Bucket edges and ties. 'A bucket holds its lower edge, at the gate's own tolerance: 5.0 is in 5 to 10. The value outcome's edge is never negative, so under 5 is 0 to 5. Where two outcomes tie for the largest edge, the first of home, draw, away is taken.'
> (e) How to read it. 'About seventy cells are printed, each with its own uncorrected interval. Some will exclude zero by chance. The receipt describes; it tests nothing.'"

## Correction to (a) of the amendment (ARCHITECT 2026-10-09, addendum 27 item 1, verbatim; the amendment above stays as issued)

> "For 'and the model's and the close's log-loss on the same games.' read: 'and, per league, the model's and the close's log-loss over every priced match, not over that cohort: PD 1.0027 and 0.9529 on 680 games, SA 0.9980 and 0.9563 on 680, BL1 1.0230 and 0.9811 on 529, FL1 1.0057 and 0.9795 on 532, ELC 1.0589 and 1.0313 on 1,024. The close's is the lower in every league.'"

## Reconciliation

Under market_side's own rule the receipt's walk must reproduce, per league, the run record's n_priced, both log-losses, and the cohort's count, hits and mean edge (amendment (b); floats to 1e-09, counts exactly). Reading: the walk must also score exactly the ids file's ids and each league's recorded n.

- Scored ids: the walk scored 3445, the ids file holds 3445 (0 not in the file, 0 in the file not scored): reproduces.
- PD: scored n 680; n_priced 680; model log-loss 1.0027478726; close log-loss 0.9528771267; cohort n 212; cohort hits 79; cohort mean edge pp 11.7068782187: reproduces.
- SA: scored n 680; n_priced 680; model log-loss 0.9980373746; close log-loss 0.9562537928; cohort n 225; cohort hits 88; cohort mean edge pp 11.2676468986: reproduces.
- BL1: scored n 529; n_priced 529; model log-loss 1.0230365614; close log-loss 0.9810504411; cohort n 266; cohort hits 115; cohort mean edge pp 12.4218861579: reproduces.
- FL1: scored n 532; n_priced 532; model log-loss 1.0056620401; close log-loss 0.9795244062; cohort n 205; cohort hits 93; cohort mean edge pp 11.2119392002: reproduces.
- ELC: scored n 1024; n_priced 1024; model log-loss 1.0588814501; close log-loss 1.0313304667; cohort n 373; cohort hits 137; cohort mean edge pp 11.7315229452: reproduces.

**Reconciliation: PASS.**

## Method

- Candidate as gated: production v22, rho -0.1, elo_goal_coeff 0.0008 (the run record's; never refit). The gate's own walk: run_soccer_backtest per league-season from a cold start, min_prior 40, regular-season rows (F3), same-kickoff fixtures predicted before any updates (F5).
- Close: fdcuk_close 1X2, de-vigged proportionally (1/price over the three legs), as market_side does.
- Value outcome: the largest model p minus close p (ties: first of home, draw, away). Top pick: the largest model p (same tie rule). Edge = the value outcome's model p minus close p, in pp; a bucket holds its lower edge at market_side's tolerance (1e-09): 5.0 is in 5 to 10; the value edge is never negative, so under 5 is 0 to 5.
- Hit: the value outcome happened (90-minute result as stored). Flat stake 1 on the value outcome at the close's fair decimal price 1/close p; return = mean profit per stake.
- Bootstrap: percentile 95% intervals; the unit is the match, resampled with replacement within the cell; 10000 resamples; numpy default_rng, seed 20261009 (fresh per cell); the return interval comes from the same draws. A cell of fewer than two matches prints no interval (—).

Priced 3445 of 3445 scored ids (0 without a full fdcuk_close 1X2).

## Tables

### PD

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 102 | 0.487 | 0.457 | 40.2% | -5.54 [-14.62, +3.56] | -15.4% [-36.0%, +5.8%] |
| under 5pp | no | 189 | 0.263 | 0.234 | 23.8% | +0.42 [-5.47, +6.51] | +5.5% [-25.6%, +43.0%] |
| 5 to 10 | yes | 83 | 0.487 | 0.413 | 39.8% | -1.57 [-11.57, +8.49] | -4.7% [-31.6%, +22.7%] |
| 5 to 10 | no | 126 | 0.278 | 0.207 | 11.9% | -8.76 [-14.13, -2.82] | -47.4% [-71.7%, -20.5%] |
| 10 to 15 | yes | 82 | 0.492 | 0.370 | 40.2% | +3.26 [-6.69, +13.43] | +4.4% [-24.4%, +34.7%] |
| 10 to 15 | no | 51 | 0.296 | 0.179 | 19.6% | +1.71 [-8.53, +13.02] | +3.0% [-52.8%, +65.2%] |
| 15 and over | yes | 41 | 0.545 | 0.344 | 31.7% | -2.67 [-16.48, +11.99] | -0.6% [-47.0%, +52.0%] |
| 15 and over | no | 6 | 0.284 | 0.117 | 0.0% | -11.69 [-14.15, -9.24] | -100.0% [-100.0%, -100.0%] |
| 5 and over | yes | 206 | 0.501 | 0.382 | 38.3% | +0.13 [-6.28, +6.45] | -0.3% [-18.7%, +18.5%] |
| 5 and over | no | 183 | 0.283 | 0.196 | 13.7% | -5.94 [-10.72, -0.80] | -35.1% [-58.5%, -9.4%] |

### SA

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 101 | 0.504 | 0.475 | 54.5% | +6.97 [-2.69, +16.32] | +17.0% [-5.2%, +38.9%] |
| under 5pp | no | 155 | 0.266 | 0.236 | 23.2% | -0.41 [-6.69, +6.18] | -7.3% [-33.3%, +21.0%] |
| 5 to 10 | yes | 116 | 0.512 | 0.439 | 44.8% | +0.89 [-7.65, +9.52] | +0.3% [-21.3%, +22.0%] |
| 5 to 10 | no | 148 | 0.291 | 0.220 | 19.6% | -2.45 [-8.50, +4.17] | -10.7% [-39.2%, +20.7%] |
| 10 to 15 | yes | 50 | 0.518 | 0.398 | 40.0% | +0.16 [-13.02, +13.54] | +3.9% [-33.3%, +42.7%] |
| 10 to 15 | no | 40 | 0.298 | 0.183 | 17.5% | -0.82 [-11.35, +11.45] | -12.1% [-65.3%, +51.7%] |
| 15 and over | yes | 57 | 0.517 | 0.328 | 28.1% | -4.76 [-15.03, +6.43] | -25.3% [-56.9%, +10.4%] |
| 15 and over | no | 13 | 0.305 | 0.132 | 15.4% | +2.21 [-13.20, +23.92] | -12.7% [-100.0%, +116.2%] |
| 5 and over | yes | 223 | 0.515 | 0.402 | 39.5% | -0.72 [-6.63, +5.48] | -5.4% [-21.6%, +11.5%] |
| 5 and over | no | 201 | 0.293 | 0.207 | 18.9% | -1.83 [-7.13, +3.79] | -11.1% [-37.1%, +16.6%] |

### BL1

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 82 | 0.564 | 0.535 | 52.4% | -1.08 [-11.37, +9.08] | -2.3% [-23.9%, +19.5%] |
| under 5pp | no | 105 | 0.249 | 0.223 | 20.0% | -2.28 [-9.54, +5.43] | -15.5% [-48.7%, +19.6%] |
| 5 to 10 | yes | 109 | 0.561 | 0.485 | 42.2% | -6.25 [-15.16, +2.73] | -14.5% [-34.3%, +5.7%] |
| 5 to 10 | no | 56 | 0.271 | 0.202 | 12.5% | -7.75 [-15.61, +1.45] | -43.9% [-79.9%, -0.3%] |
| 10 to 15 | yes | 90 | 0.584 | 0.458 | 47.8% | +1.93 [-8.39, +11.91] | +8.9% [-16.1%, +34.7%] |
| 10 to 15 | no | 13 | 0.296 | 0.181 | 23.1% | +5.00 [-16.92, +29.34] | +42.6% [-100.0%, +212.6%] |
| 15 and over | yes | 67 | 0.618 | 0.417 | 38.8% | -2.90 [-13.79, +8.42] | -7.8% [-37.2%, +23.7%] |
| 15 and over | no | 7 | 0.305 | 0.125 | 14.3% | +1.80 [-13.18, +29.23] | -17.0% [-100.0%, +148.9%] |
| 5 and over | yes | 266 | 0.583 | 0.459 | 43.2% | -2.64 [-8.51, +3.26] | -4.9% [-19.2%, +9.5%] |
| 5 and over | no | 76 | 0.278 | 0.192 | 14.5% | -4.69 [-12.08, +3.51] | -26.6% [-66.2%, +18.1%] |

### FL1

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 88 | 0.549 | 0.518 | 50.0% | -1.80 [-12.13, +8.37] | -3.2% [-24.5%, +18.3%] |
| under 5pp | no | 121 | 0.247 | 0.218 | 22.3% | +0.47 [-6.63, +7.95] | +4.0% [-31.3%, +42.5%] |
| 5 to 10 | yes | 93 | 0.552 | 0.480 | 50.5% | +2.55 [-6.87, +12.20] | +4.8% [-17.6%, +28.2%] |
| 5 to 10 | no | 91 | 0.278 | 0.207 | 24.2% | +3.45 [-4.97, +12.23] | +10.9% [-29.3%, +54.0%] |
| 10 to 15 | yes | 79 | 0.560 | 0.439 | 44.3% | +0.42 [-10.03, +10.73] | +1.1% [-25.6%, +28.4%] |
| 10 to 15 | no | 27 | 0.287 | 0.171 | 11.1% | -5.98 [-16.32, +6.43] | -44.0% [-100.0%, +21.8%] |
| 15 and over | yes | 33 | 0.565 | 0.362 | 33.3% | -2.84 [-17.39, +12.48] | -11.1% [-56.3%, +40.2%] |
| 15 and over | no | 0 | — | — | — | — | — |
| 5 and over | yes | 205 | 0.557 | 0.445 | 45.4% | +0.86 [-5.53, +7.27] | +0.8% [-15.6%, +17.7%] |
| 5 and over | no | 118 | 0.280 | 0.199 | 21.2% | +1.29 [-5.54, +8.85] | -1.7% [-34.9%, +35.0%] |

### ELC

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 127 | 0.480 | 0.448 | 39.4% | -5.45 [-13.89, +2.85] | -10.1% [-30.3%, +9.9%] |
| under 5pp | no | 278 | 0.293 | 0.261 | 32.4% | +6.23 [+0.79, +11.84] | +25.0% [+3.5%, +47.1%] |
| 5 to 10 | yes | 171 | 0.460 | 0.386 | 33.9% | -4.66 [-11.48, +2.25] | -13.9% [-32.6%, +5.4%] |
| 5 to 10 | no | 205 | 0.303 | 0.234 | 19.0% | -4.39 [-9.71, +1.22] | -17.4% [-40.8%, +7.4%] |
| 10 to 15 | yes | 104 | 0.484 | 0.360 | 39.4% | +3.43 [-5.66, +12.99] | +10.1% [-16.9%, +38.7%] |
| 10 to 15 | no | 48 | 0.314 | 0.198 | 20.8% | +0.99 [-9.66, +12.91] | -2.3% [-53.9%, +54.6%] |
| 15 and over | yes | 89 | 0.518 | 0.320 | 39.3% | +7.29 [-2.83, +17.16] | +25.3% [-9.9%, +60.7%] |
| 15 and over | no | 2 | 0.318 | 0.155 | 100.0% | +84.49 [+83.96, +85.03] | +545.7% [+523.3%, +568.1%] |
| 5 and over | yes | 364 | 0.481 | 0.362 | 36.8% | +0.57 [-4.24, +5.43] | +2.5% [-12.2%, +17.4%] |
| 5 and over | no | 255 | 0.305 | 0.227 | 20.0% | -2.68 [-7.50, +2.30] | -10.1% [-31.9%, +12.7%] |

### pooled

| edge bucket | value = top pick | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| under 5pp | yes | 500 | 0.512 | 0.482 | 46.6% | -1.60 [-5.91, +2.66] | -3.2% [-13.0%, +6.6%] |
| under 5pp | no | 848 | 0.269 | 0.240 | 25.8% | +1.85 [-1.00, +4.77] | +6.7% [-6.3%, +20.6%] |
| 5 to 10 | yes | 572 | 0.509 | 0.435 | 41.3% | -2.22 [-6.05, +1.60] | -6.8% [-16.5%, +3.1%] |
| 5 to 10 | no | 626 | 0.289 | 0.219 | 17.9% | -3.97 [-6.90, -1.01] | -20.1% [-33.4%, -6.3%] |
| 10 to 15 | yes | 405 | 0.527 | 0.404 | 42.5% | +2.07 [-2.66, +6.70] | +6.2% [-6.9%, +19.2%] |
| 10 to 15 | no | 179 | 0.300 | 0.184 | 18.4% | +0.03 [-5.25, +5.74] | -6.0% [-33.8%, +24.5%] |
| 15 and over | yes | 287 | 0.551 | 0.353 | 35.2% | -0.07 [-5.22, +5.15] | -0.3% [-17.0%, +16.8%] |
| 15 and over | no | 28 | 0.302 | 0.129 | 17.9% | +5.01 [-8.01, +18.98] | +7.4% [-76.1%, +96.7%] |
| 5 and over | yes | 1264 | 0.524 | 0.406 | 40.3% | -0.36 [-2.93, +2.26] | -1.2% [-8.3%, +6.1%] |
| 5 and over | no | 833 | 0.292 | 0.208 | 18.0% | -2.81 [-5.35, -0.17] | -16.2% [-28.3%, -3.5%] |

### The 5-and-over row by the value outcome's kind

| league | value outcome | n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | flat-stake return at the close's fair price [95% CI] |
|---|---|---|---|---|---|---|---|
| PD | home | 76 | 0.479 | 0.384 | 36.8% | -1.59 [-11.01, +7.95] | -17.4% [-42.8%, +9.1%] |
| PD | draw | 69 | 0.286 | 0.213 | 11.6% | -9.72 [-16.68, -1.94] | -50.4% [-80.6%, -16.1%] |
| PD | away | 244 | 0.405 | 0.290 | 27.9% | -1.10 [-6.39, +4.30] | -6.8% [-27.2%, +14.4%] |
| SA | home | 124 | 0.504 | 0.396 | 36.3% | -3.28 [-11.53, +4.88] | -9.7% [-32.5%, +13.4%] |
| SA | draw | 120 | 0.306 | 0.227 | 20.8% | -1.90 [-8.89, +5.61] | -6.4% [-39.0%, +29.4%] |
| SA | away | 180 | 0.414 | 0.305 | 31.1% | +0.60 [-5.27, +6.91] | -8.2% [-29.7%, +15.5%] |
| BL1 | home | 122 | 0.605 | 0.497 | 41.0% | -8.76 [-17.06, -0.47] | -19.4% [-37.6%, -0.6%] |
| BL1 | draw | 10 | 0.264 | 0.194 | 10.0% | -9.45 [-22.78, +12.77] | -31.5% [-100.0%, +105.5%] |
| BL1 | away | 210 | 0.475 | 0.352 | 35.7% | +0.50 [-5.49, +6.63] | -3.1% [-23.1%, +17.7%] |
| FL1 | home | 106 | 0.536 | 0.435 | 41.5% | -2.00 [-10.35, +6.53] | -7.4% [-30.9%, +18.0%] |
| FL1 | draw | 37 | 0.272 | 0.201 | 18.9% | -1.19 [-12.47, +11.94] | -16.2% [-70.6%, +47.8%] |
| FL1 | away | 180 | 0.447 | 0.340 | 37.2% | +3.25 [-3.36, +10.03] | +7.6% [-15.0%, +31.1%] |
| ELC | home | 140 | 0.510 | 0.406 | 45.0% | +4.36 [-3.68, +12.60] | +12.2% [-9.8%, +34.6%] |
| ELC | draw | 175 | 0.322 | 0.248 | 21.7% | -3.11 [-8.93, +3.13] | -12.2% [-36.1%, +13.4%] |
| ELC | away | 304 | 0.411 | 0.294 | 27.6% | -1.77 [-6.67, +3.25] | -4.1% [-22.6%, +15.3%] |
| pooled | home | 568 | 0.530 | 0.426 | 40.5% | -2.11 [-6.03, +1.70] | -7.0% [-17.3%, +3.1%] |
| pooled | draw | 411 | 0.305 | 0.231 | 19.2% | -3.85 [-7.53, -0.05] | -17.7% [-34.0%, -0.8%] |
| pooled | away | 1118 | 0.428 | 0.313 | 31.3% | -0.01 [-2.51, +2.66] | -3.3% [-12.4%, +6.3%] |

The PL reference page: `docs/receipts/soccer-value-sides-2026-10-09-pl-reference.md`.
