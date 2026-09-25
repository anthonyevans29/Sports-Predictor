# Changelog

Human-readable record of what shipped, newest first. Deep detail and the
reasoning behind each change live in `BACKLOG.md`; this file is the summary.
Every drop adds an entry going forward.

## 2026-09-25 (NHL candidate v3 — gate-class)
- nhl_elo_v2 FAIL ratified (2025 0.6921, upper bands overconfident).
- `nhl-backtest --candidate v3`: params selected by walk-forward
  validation inside 2024 (60% fit / 40% validation), full-2024 refit,
  2025 scored once; grid extended downward/center only. Gate unchanged.
- Standing fallback logged: no pass by Oct 6 -> NHL opens Oct 7
  market-only.

## 2026-09-25 (cup fix — gate-class)
- Cup/intl pricing: attack/defense from each team's domestic
  league-season fit (as-of-date), blended toward the cup fit by n/(n+5);
  every fit leave-self-out, strictly before kickoff.
- Ruling B: unrated / no-domestic-league cup fixtures are market-only
  (never priced); the exam reports them separately, outside INVALID.
- elo_goal_coeff unchanged (0.0008). League pricing untouched.
- Coverage floor: fewer than 45 scored fixtures = exam INVALID
  (architect amendment).

## 2026-09-25 (NHL candidate v2 — gate-class)
- nhl_elo_v1 FAIL ratified (0.6909 vs <= 0.6866); bar unchanged.
- `nhl-backtest --candidate v2`: frozen 720-point grid tuned on
  2024-internal sequential loss only, then 2025 scored once. v2 = v1 +
  rest days (back-to-back emphasis) from the existing schedule.

## 2026-09-25 (cup pricing hypothesis check)
- `cup-exam --detail` adds strength-fit receipts: per-side fit n,
  attack/defense, promoted-prior flag, self-in-fit, pool/backfill,
  summary. No pricing change.
- BACKLOG: code receipts for the cup strength window and the
  elo_goal_coeff under-dispersion; architect ruling B (out-of-pot =
  market-only) logged.

## 2026-09-25 (NHL Phase 2 — gate, then Elo v1; gate-class)
- `python cli.py nhl-backtest`: frozen NHL gate (train 2024, test 2025,
  preseason excluded by stage/date, OT/SO-inclusive home win), both
  baselines, three acceptance criteria, verdict. Writes nothing.
- nhl_elo_v1: MOV + per-team season regression; parameters a priori,
  home advantage from the 2024 home rate.

## 2026-09-25 (cup exam diagnostics)
- Cup exam verdict FAIL (mean |Δ_H| 13.86pp, sign 60%): cups stay locked.
- `cup-exam --detail`: per-row Elo/league/bonus inputs, |Δ_H| splits
  by pot membership and tier, default-Elo team count. No pricing change.

## 2026-09-25 (cup acceptance exam — gate-class)
- `_generate_predictions_soccer(include_finished=True)`: report-only
  pricing of finished fixtures; returns rows, writes nothing.
- `python cli.py cup-exam`: scores production pricing against
  exports/cup_answer_key.csv on the frozen bar (±8pp MAE, <=13 over
  8pp, EFL round-2 sign check); necessary-not-sufficient semantics.
- Removed superseded tools/betting_desk.html and
  tools/predictions_card.html (cockpit.html is the live surface).
- BACKLOG: architect's stale-entry disposition logged verbatim.

## 2026-09-25 (security warm-up — first Claude Code PR)
- Web UI: cross-site (CSRF) check on all state-changing requests;
  Host allowlist against DNS rebinding; Tailwind pre-built and
  htmx/Chart.js vendored — the UI loads no third-party scripts.
- tools/cockpit.html: escapes file- and model-supplied text (XSS).
- tests/ + pytest in CI; CLAUDE.md workflow: Claude Code works
  branch + PR only, Anthony merges.

## 2026-09-25 (working arrangement v2)
- CLAUDE.md shipped: Claude Code onboarded as repo executor; chat
  remains architect. Tarball era closes.

## 2026-09-25 (NCAA)
- NCAA wired into the american-football adapter (league map, both
  competitions listed, per-code resolution); cli routes NCAA; data +
  market-only doctrine.

## 2026-09-24 (cockpit)
- Card + Desk merged into one tabbed cockpit artifact (same URL);
  per-game signal expanders; tools/cockpit.html supersedes both files.

## 2026-09-24 (predictions card)
- Predictions Card artifact: sport-aware model viewer over the exports
  (bars, edges, quarantine, QB, gaps) — the post-GPT cockpit's second
  organ; in-repo copy versioned.

## 2026-09-24 (SDLC)
- Community standards shipped (CONTRIBUTING = the laws, CoC, SECURITY,
  MIT LICENSE, issue/PR templates) + CI (parse + import smoke on every
  push). PR doctrine: direct-to-main daily; branch+PR for gate-class.

## 2026-09-24 (H-track 1c)
- sync-kalshi-nhl (third sport on the shared matcher); export success
  string updated to LIVE format.

## 2026-09-23 (NHL Phase 1)
- api_hockey adapter shipped (cloned from american-football; id 57,
  AOT/ASO handling, preseason captured); registry, sport router, and
  --seasons wired. Backfill block issued.

## 2026-09-23 (H-track)
- NHL Phase 0 probe shipped: read-only plan/id/season-format recon with
  famous-club receipts.

## 2026-09-23 (cup exam prep)
- scripts/extract_cup_key.py: read-only answer-key extractor for the
  cup acceptance exam; report-only pricing mode scoped for next session.

## 2026-09-23 (perf)
- Match-sync O(n^2) fixed: per-sync prefetch cache replaces per-row JSON
  full scans; morning chains move to 2-day sync windows (full-season
  weekly).

## 2026-09-23
- H-track opened: NHL onboarding planned on the NFL playbook (phased,
  gate-first, preseason-as-shakedown); sequenced behind the cup
  acceptance exam.

## 2026-09-22
- **NFL LIVE (Week 3 ratified):** rehearsal flag dropped; per-row
  market_divergence_pp + quarantine field (>=15pp) implements the
  contract rule structurally.

## 2026-09-21 (rebuild)
- DB destroyed by packaging incident; restored from 09-17 backup and
  fully rebuilt same morning. v22 re-promoted on the full 16,546-match
  / 24-competition pot (spread 101%, documented drift override).
  Packaging + backup laws now in force.

## 2026-09-21 (desk v0.3)
- Betting Desk v0.3: multi-sport multi-file intake, cross-sport parlay
  builder (correlation-screened, positive-edge, 0.25u), audit expanded
  to per-game notes + parlay critique + prediction-layer signals
  feedback.

## 2026-09-21
- Engine-level SQLite pragmas (WAL + synchronous=NORMAL + busy_timeout)
  on every connection — fixes the morning-lag regression from db-tune's
  per-connection NORMAL.

## 2026-09-20 (desk v0.2)
- Betting Desk v0.2: sport-aware ladder (no DC on 2-way boards),
  monotone sizing, near-floor tempering, correlation flag — both day-1
  NFL defects fixed by the desk's own audit arm; now versioned in-repo
  (tools/betting_desk.html).

## 2026-09-20 (shadow day 1)
- First divergence report: slate-shape convergence; three structural B1
  requirements identified (input freshness, consensus quality,
  two-stage clearance); app-side injury-recency flag queued.

## 2026-09-20 (B1)
- Betting Desk artifact shipped: browser-local policy engine + Claude
  audit over daily exports — the B1 shadow vehicle.

## 2026-09-20 (B-track)
- B-track opened: native betting layer design committed (policy-as-code,
  shadow-vs-GPT migration path, audits-as-requirements). Sequenced after
  cup acceptance + U1 unless platform deadlines force it.

## 2026-09-20 (db)
- `db-tune`: WAL mode, ANALYZE, composite indexes, optional VACUUM,
  probe timing — first response to season-scale DB lag; snapshot
  pruning/rollup queued as the structural fix.

## 2026-09-20
- API-Football request spacing now env-configurable (API_FOOTBALL_RPM;
  default 10/min): the 2:04-per-odds-sync metronome was the free-tier
  pace hardcoded — paid plans can cut the European sweep's odds legs
  from ~12 minutes to ~30 seconds. 429 backoff unchanged as safety net.

## 2026-09-19 (feeder backfill)
- Nine feeder leagues backfilled: ~7,988 matches, zero skips. Monday
  refresh pot ~20,600 across 24 competitions.

## 2026-09-19 (feeders)
- Nine CL/UEL feeder leagues wired data-only (NED POR BEL SCO TUR AUT
  SUI GRE CZE) with strength priors; Nordic calendar-year leagues
  deferred pending season-string support.

## 2026-09-19 (backfill)
- Expansion backfill complete: 4,468 matches / 4 leagues, zero skips;
  ELC activated. 15 competitions, 5 countries.

## 2026-09-19 (expansion)
- Coverage expansion decided: La Liga, Serie A, Bundesliga, Ligue 1 +
  ELC activation — no code needed (pre-wired); backfill plan issued,
  refresh held to Monday as one gated transition, shadow-matchweek
  doctrine applies.

## 2026-09-19 (v22)
- **v22 promoted** — first soccer model change since v18: per-team
  regression, 8,137-match pot (pyramid/Euro/WC), spread guard passed
  99%; Southampton drift justified (50 ELC matches entered) with a
  documented one-time --max-drift override. Refresh reopened.

## 2026-09-19 (later)
- Compression CONVICTED by the probe (interleaved "2026"/"2026/27"
  season strings firing six tail regressions; pyramid exonerated) and
  FIXED: per-team season regression in elo.train (NFL semantics).

## 2026-09-19
- `scripts/compression_probe.py`: instrumented double-train (pot A/B)
  with inline regression markers — locates the Elo collapse empirically.
- U1 (per-sport daily cards + unified page) committed as next dedicated
  build session.

## 2026-09-17
- `capture-weather-nfl` (N1 phase 1): 32-stadium map keyed by home team,
  roofed handling, Open-Meteo capture into GameWeather — tracking only.
- S14 Stage-1: flat +1.0 uncertain-bucket totals correction selected
  counterfactually (direction 39%->52% in-sample); Stage-2 out-of-sample
  acceptance frozen pre-results.
- Cap-variant verdicts: all four declined (caps cost log-loss; shrink
  degraded the weakest band) — v1 unchanged; bonus finding: the >0.80
  zone was under-confident on 2025 (0.800 stated / 0.833 realized).
- `nfl-backtest-caps`: R-track cap/shrink variant harness (acceptance
  frozen pre-results); untestable asks (road-inversion, divisional)
  declined with reasons. Matched-zero sentinel extended to the shared
  MLB/NFL Kalshi path.

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
