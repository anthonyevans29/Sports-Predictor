# MLB actionable receipt · season 2026 · run 2026-10-08T1336Z

READ-ONLY (ARCHITECT 2026-10-07, item 2; NO policy change). Tier (the prediction layer's `classify_tier`, src/web/preview.py: toss-up < 53% = actionable false) x edge bucket.

**THE EDGE IS AGAINST THE CLOSE, NOT THE DESK'S T-60 REFERENCE.** Edge = model p on the pick − close fair p on the same side (pp), the close = `grading_close` (last pre-first-pitch BOOK session, complete books de-vigged then averaged; src/walters/close.py). Prediction history exists only from 2026-10-06, so the close is a PROXY for the Desk's T-60 reference.

- graded MLB predictions (season 2026): 1753
- included (book close on the pick): 823
- EXCLUDED: 930
  - close is not a book close (reference=kalshi_only): 10
  - no close (no pre-first-pitch capture, or unpriced): 920
- included tiered lean by the starter cap (top p >= 60%, a starter unconfirmed): 8
- included with edge < 0 (the `<0` bucket): 527
- included whose stored prediction was computed at/after first pitch (kept, flagged): 3
- model versions (included): v2 823
- bootstrap: games resampled within the cell, B 10000, seed 20261007, percentile 95% CI; n < 2 -> —
- ROI: stake 1 at decimal odds 1/(close fair p) on the pick (zero-vig close price)

## Regular season (stage R) · n 810

| tier | edge vs close | n | mean model p | mean close fair p | hit rate | hit − close (pp) | 95% CI (pp) | ROI @ close fair |
|---|---|---:|---:|---:|---:|---:|---|---:|
| toss-up | <0pp | 152 | 0.516 | 0.541 | 0.592 | +5.1 | [-2.7, +12.8] | +9.3% |
| toss-up | 0-4pp | 101 | 0.514 | 0.498 | 0.594 | +9.6 | [-0.2, +19.4] | +19.7% |
| toss-up | 4-8pp | 24 | 0.515 | 0.463 | 0.542 | +7.9 | [-12.8, +28.6] | +16.9% |
| toss-up | 8-15pp | 1 | 0.502 | 0.360 | 0.000 | -36.0 | — | -100.0% |
| toss-up | >=15pp | 0 | — | — | — | — | — | — |
| toss-up | all | 278 | 0.515 | 0.518 | 0.586 | +6.8 | [+1.0, +12.4] | +13.4% |
| lean | <0pp | 300 | 0.567 | 0.593 | 0.590 | -0.3 | [-5.8, +5.1] | -0.7% |
| lean | 0-4pp | 150 | 0.556 | 0.542 | 0.540 | -0.2 | [-8.1, +7.8] | -0.6% |
| lean | 4-8pp | 8 | 0.555 | 0.504 | 0.375 | -12.9 | [-39.1, +24.6] | -24.9% |
| lean | 8-15pp | 3 | 0.580 | 0.476 | 0.667 | +19.0 | [-47.1, +52.4] | +39.2% |
| lean | >=15pp | 0 | — | — | — | — | — | — |
| lean | all | 461 | 0.563 | 0.574 | 0.570 | -0.3 | [-4.9, +4.1] | -0.8% |
| strong | <0pp | 67 | 0.619 | 0.661 | 0.687 | +2.5 | [-8.6, +13.0] | +3.1% |
| strong | 0-4pp | 4 | 0.681 | 0.656 | 0.750 | +9.4 | [-41.7, +38.1] | +15.3% |
| strong | 4-8pp | 0 | — | — | — | — | — | — |
| strong | 8-15pp | 0 | — | — | — | — | — | — |
| strong | >=15pp | 0 | — | — | — | — | — | — |
| strong | all | 71 | 0.623 | 0.661 | 0.690 | +2.9 | [-8.0, +13.3] | +3.8% |
| all | all | 810 | 0.552 | 0.562 | 0.586 | +2.4 | [-1.0, +5.8] | +4.4% |

## Postseason (stage F/D/L/W) · n 13

| tier | edge vs close | n | mean model p | mean close fair p | hit rate | hit − close (pp) | 95% CI (pp) | ROI @ close fair |
|---|---|---:|---:|---:|---:|---:|---|---:|
| toss-up | <0pp | 4 | 0.520 | 0.558 | 0.250 | -30.8 | [-57.6, +19.5] | -54.5% |
| toss-up | 0-4pp | 2 | 0.516 | 0.494 | 0.500 | +0.6 | [-48.9, +50.1] | +0.1% |
| toss-up | 4-8pp | 0 | — | — | — | — | — | — |
| toss-up | 8-15pp | 0 | — | — | — | — | — | — |
| toss-up | >=15pp | 0 | — | — | — | — | — | — |
| toss-up | all | 6 | 0.518 | 0.537 | 0.333 | -20.3 | [-55.3, +15.4] | -36.3% |
| lean | <0pp | 4 | 0.565 | 0.592 | 0.750 | +15.8 | [-32.4, +43.2] | +26.0% |
| lean | 0-4pp | 2 | 0.557 | 0.544 | 0.500 | -4.4 | [-52.4, +43.6] | -11.3% |
| lean | 4-8pp | 1 | 0.539 | 0.494 | 1.000 | +50.6 | — | +102.4% |
| lean | 8-15pp | 0 | — | — | — | — | — | — |
| lean | >=15pp | 0 | — | — | — | — | — | — |
| lean | all | 7 | 0.559 | 0.564 | 0.714 | +15.0 | [-15.7, +44.2] | +26.3% |
| strong | <0pp | 0 | — | — | — | — | — | — |
| strong | 0-4pp | 0 | — | — | — | — | — | — |
| strong | 4-8pp | 0 | — | — | — | — | — | — |
| strong | 8-15pp | 0 | — | — | — | — | — | — |
| strong | >=15pp | 0 | — | — | — | — | — | — |
| strong | all | 0 | — | — | — | — | — | — |
| all | all | 13 | 0.540 | 0.552 | 0.538 | -1.3 | [-26.1, +23.5] | -2.6% |

## Stage unknown (stage null or unmapped; never guessed) · n 0

| tier | edge vs close | n | mean model p | mean close fair p | hit rate | hit − close (pp) | 95% CI (pp) | ROI @ close fair |
|---|---|---:|---:|---:|---:|---:|---|---:|
| toss-up | <0pp | 0 | — | — | — | — | — | — |
| toss-up | 0-4pp | 0 | — | — | — | — | — | — |
| toss-up | 4-8pp | 0 | — | — | — | — | — | — |
| toss-up | 8-15pp | 0 | — | — | — | — | — | — |
| toss-up | >=15pp | 0 | — | — | — | — | — | — |
| toss-up | all | 0 | — | — | — | — | — | — |
| lean | <0pp | 0 | — | — | — | — | — | — |
| lean | 0-4pp | 0 | — | — | — | — | — | — |
| lean | 4-8pp | 0 | — | — | — | — | — | — |
| lean | 8-15pp | 0 | — | — | — | — | — | — |
| lean | >=15pp | 0 | — | — | — | — | — | — |
| lean | all | 0 | — | — | — | — | — | — |
| strong | <0pp | 0 | — | — | — | — | — | — |
| strong | 0-4pp | 0 | — | — | — | — | — | — |
| strong | 4-8pp | 0 | — | — | — | — | — | — |
| strong | 8-15pp | 0 | — | — | — | — | — | — |
| strong | >=15pp | 0 | — | — | — | — | — | — |
| strong | all | 0 | — | — | — | — | — | — |
| all | all | 0 | — | — | — | — | — | — |
