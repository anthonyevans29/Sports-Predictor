# Changelog

Human-readable record of what shipped, newest first. Deep detail and the
reasoning behind each change live in `BACKLOG.md`; this file is the summary.
Every drop adds an entry going forward.

## 2026-09-16
- S14 verdict: soccer totals under-projection is bucket-shaped
  (uncertain-winner games +1.17 goals, confident +0.08, n=46) — fix
  hypothesis queued for Stage-1 backtest. CLI.md corrected:
  totals-check/calibration-series are MLB-only.

## 2026-09-15
- Hotfix: results-tally join corrected (outcomes link via prediction_id
  → Prediction → Match, not match_id) — caught on first run.
- **`results-tally`** → `RESULTS.md`: rolling 30-day per-sport record
  (sides, log-loss, CLV), auto-generated, linked from README; joins the
  morning rhythm.
- **`export-nfl-results`**: graded NFL results file in the standard
  consumer shape (rehearsal-flagged) — NFL joins the results-file rhythm.
- Week 1 NFL final: 9/16, log-loss 0.6755 (both max-conviction rows
  lost); MW4 soccer: 5/10, giant edges split — Forest won, Hull and
  Everton missed by draw (cohort 6/12, four misses-by-draw).

## 2026-09-14
- NFL Week 1 graded via `nfl-grade` (first live read): 9/15 sides,
  log-loss 0.6441 vs 0.6361 backtest — performance transferred live.
- **`docs/CLI.md`**: full CLI catalog (~55 commands with options),
  organized by workflow, plus the required-services matrix (providers,
  endpoints, env vars, subscription notes) and local component
  requirements. README links it as the primary interface reference.
- **README rewritten** to current four-sport reality; this CHANGELOG seeded.
- **`nfl-grade`**: grades NFL predictions vs finished games and banked
  closing consensus (sides, log-loss, CLV) — read-only, feeds the Week-2
  rehearsal decision.
- **Kalshi soccer hardening**: matched-zero sentinel (loud warning when
  games and markets are both present but nothing matches) and an in-play
  guard keyed on our own kickoff time at capture.
- **GitHub repo live** (this repo): pre-push security scan clean; tarball →
  extract → commit → push workflow established.

## 2026-09-13
- **Kalshi soccer matcher fixed** after an upstream title-format change
  ("A vs B Winner?" → "A wins") silently blinded it for two matchweeks:
  pairing now derived structurally from sibling legs sharing an
  event_ticker, old title parse kept as fallback. Matched 36/36 on return.
- NFL Week-1 game-day file: full model-vs-market comparison (15 priced
  games), Kalshi NFL board matched 28 legs / 14 games two-sided.

## 2026-09-10 → 09-12
- **NFL tier thresholds frozen** pre-results (strong ≥0.68, lean ≥0.57).
- Injury position enrichment: provider's injuries feed carries no
  positions; adapter now joins the team roster by player id (QB status
  live end-to-end).
- MW4 false alarm resolved on the record: two probe-falsified theories;
  file shipped; lesson logged (verify before withholding).

## 2026-09-09
- **NFL phase 2 in one day, gate-first**: backtest gate frozen before any
  model code; v1 Elo (margin-of-victory, per-team season regression)
  passed decisively (0.6361 vs 0.6911 baseline, all bands ≤7pp);
  prediction path + rehearsal-format export built; Week-1 shakedown run
  internally. `sync-odds-nfl` closed the book-capture gap.
- Kalshi sync parameterized (sport + series) — one matcher serves MLB and
  NFL; `sync-kalshi-nfl` added.

## 2026-09-05 → 09-08
- **NFL phase 1**: full data wiring from zero — adapter
  (api-american-football), registry/CLI routing, 3-season backfill
  (989 games), status inference (score-presence beats status-absence),
  spread-sign preservation, season-format hardening.
- **`export-fixtures`**: market-only files for gated competitions
  (matches + odds tables only; `contains_predictions: false`). First live
  consumption by the downstream layer same week.
- EFL Trophy consciously excluded (training-pot contamination); FA Cup
  sync deferred to its trigger rounds; CL ruled data-only behind the cup
  acceptance gate.
- Elo compression diagnosis narrowed: v19/v20 rejections deterministic;
  rating-spread guard added to the soccer gate.

## 2026-08-28 → 09-04
- S17: results export includes draw in top-pick labeling (+ assertion).
- M12: per-match skip warnings aggregated to one summary line.
- Doubleheader guard in the MLB odds fallback (nearest-time + claimed-id).
- EL→UEL competition normalization; pyramid (ELC/EL1/EL2) + CL/UEL
  history backfilled for the cup project.
- Aug-31 quality review: run_shrink_frac=0.35 confirmed on 509 games;
  starter-cap and bullpen-swing ledgers closed clean; M15/M16 tracking
  opened with pre-committed reads.

## 2026-08-11 → 08-27 (from the earlier phase)
- MLB production model v2 shipped behind the daily improve gate; CLV
  lifecycle automated (overnight closer backfill).
- Soccer v18 production through PL matchweeks; thermometer/pick-edge
  ledgers established.
- EFL Cup round-2 dress rehearsal caught the cup-path defects (league
  bonus misfire); S16 doctrine: no cup predictions until acceptance.
- Kalshi integration (MLB + soccer) with refuse-safe matching.
