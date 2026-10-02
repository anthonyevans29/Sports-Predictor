# International Elo v2: the frozen declaration (#220)

**Status: DECLARED 2026-10-02 by ruling. Nothing has been run.** Registry id
`intl-elo-v2` (#212). The run refuses unless this declaration is in the
registry and has not run. v1 (`docs/specs/intl-elo-v1.md`) holds for
everything not changed here.

## The ruling (ARCHITECT 2026-10-02, verbatim)

"intl-elo-v1 VERDICT STANDS — FAIL on calibration; log-loss criterion PASSED
by 0.19 (0.8507 vs bar 1.0431; RPS 0.167 vs 0.237); bands show systematic
UNDER-confidence (favorites 50-90% realize +20-30pp above stated). Record;
prior reads of this test set = 1.
v2 DECLARATION: (a) the rating-to-probability scale and a global K
multiplier are FITTED BY MAXIMUM LIKELIHOOD ON THE TRAINING STREAM ONLY
(walk-forward within 2018-2024; grid declared; chosen before any test read)
— the same train-only remedy as NHL v8; (b) neutral rule v3 (venue country ≠
home team's country) replaces v2 — route B, 218 calls, run on the laptop as
an ingest step before v2's run; derived, labelled. Same bar, same bands, same
test set. Attribution of (a) vs (b) from train-season diagnostics, not from a
second test read. One run."

## (a) The train-only fit

- **"The rating-to-probability scale" (interpretation, stated so it can be
  corrected before the run).** In this model a rating difference becomes a
  probability **only** through the Elo→goals coefficient c of the soccer
  mapping (λ = μ·exp(±c·diff/2), §4 of v1).
  - The scale is therefore a multiplier on c: `c_mult`, with c = 0.0023 ×
    c_mult.
  - The update's expected score keeps v1's /400. It is the rating dynamics,
    not the probability the model states.
  - Under-confidence (favourites realising +20–30pp above stated) is
    exactly a c that is too small.
- **A global K multiplier, `k_mult`:** each class K (20/40/50/60) × k_mult.
- **The declared grid, frozen:**
  - c_mult ∈ {0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0}
  - k_mult ∈ {0.5, 0.75, 1.0, 1.25, 1.5, 2.0}
  - 48 pairs; v1's (1.0, 1.0) is on the grid.
- **Objective:** for each pair, a fresh model walks the **training stream
  only** (kickoff 2018-01-01 … 2024-08-31), predict-then-update, with v3
  neutral flags. The mean three-way log-loss is the negative log-likelihood,
  and the minimum wins.
  - **Ties:** an exact tie goes to the pair closest to (1.0, 1.0), c first.
  - **Edges:** a grid-edge choice is flagged, never widened.
  - **Isolation:** `intl_elo.fit_v2` refuses any game outside the training
    stream. The harness prints the choice and the best 10 **before any test
    read**.

## (b) Neutral rule v3

- **Rule:** `neutral_v3` = venue country ≠ the home team's country.
  - The venue country is API-Football `/venues`, as served.
  - The home country is `/teams` team.country (stored as `teams.area`).
  - Either unknown → unknown, priced +100 as in v1 §3.
- **Ingest (laptop, before the run):** `python cli.py intl-venue-sync
  --from-dir <the intl-sync --save dir> --venues-dir <dir>`.
  - Venue ids come from the saved `/fixtures` (0 calls).
  - Then `/venues?country=<home country>`, one call per distinct home
    country (route B, about 218 calls).
  - It writes `intl_match_venue` with the rule text and both countries.
    `--plan` prints the count first.
- **v3 replaces v2.** There is no cascade. The v3 RULE CHECK share is
  reported, not gated.

## Everything else is v1's

- the stream and the 90-minute labels;
- H +100 / 0 / unknown +100;
- the class K table (now × k_mult);
- mov = ln(max(|m|,1)+1) with the 2.2 gap factor, and draw S = 0.5;
- the Poisson mapping (ρ −0.10, μ from train);
- no season regression;
- the splits: train 2018-01-01..2024-08-31, test **UNL 2024/25 + WCQ_EU
  2025-03-01..2026-03-31**, the same test set;
- the naive baseline;
- **bar = naive − 0.010**, the same calibration bands, RPS reported;
- the 60-game confirmation plan.

## Attribution (train only)

The run prints the training-stream log-loss of four configurations, with no
test read:

1. v1 params + v2 neutral (v1 as run);
2. (a) only: fitted params + v2 neutral;
3. (b) only: v1 params + v3 neutral;
4. (a)+(b): fitted params + v3 neutral, the candidate.

## Registry and run order

- **Registry:** the test set carries **1 prior read** (intl-elo-v1) once v1's
  run record is spliced.
- **Run order:**
  1. Splice v1's run record + FAIL.
  2. `.backup`.
  3. `intl-venue-sync --plan`, then `intl-venue-sync`.
  4. `intl-elo-backtest --candidate v2 --preflight`.
  5. `intl-elo-backtest --candidate v2`, **once**. Paste the output and the
     `docs/registry/` diff.
