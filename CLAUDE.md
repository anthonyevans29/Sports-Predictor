# CLAUDE.md — read this before touching anything

You are working on **sports_predictor**: a multi-sport prediction and
calibration system (Python/SQLite/SQLAlchemy, CLI-driven) feeding a
browser Cockpit (tools/cockpit.html, published separately as a Claude
artifact — do not treat the repo copy as the live one). The operator is
Anthony; architectural decisions, gate verdicts, and enhancement specs
come from his Claude chat ("the architect"). Your job is disciplined
execution of those specs. When a spec and this file conflict, stop and
ask.

## The six laws (from CONTRIBUTING.md — they are incident-earned, not style)
1. **Read before edit.** A regex/memory match is a hypothesis. Anchors,
   column names, provider vocabularies: enumerate from the actual
   file/schema/API response first. (Four guessed-name incidents last
   week alone, one on launch morning.)
2. **Receipts over claims.** Print counts, paste consoles, verify
   listings. "Fast" or "fixed" without a receipt triggers an audit.
3. **Gates decide.** Model changes promote ONLY through frozen,
   pre-committed acceptance criteria written before results exist.
   Never loosen a threshold after a good week. Ties are rejections.
4. **Conservative unknowns.** Unmapped statuses stay SCHEDULED; missing
   data stays null and labeled. Never fake completeness.
5. **The database never travels and is never touched casually.**
   `data/` is gitignored and stays that way. Backups are `.backup`-API
   only: daily, plus mandatory before any `soccer-refresh`. NEVER
   create, copy, or commit any file under data/. NEVER run destructive
   SQL. The DB was destroyed once by a packaged empty file; the laws
   here are its gravestone.
6. **Track by artifact.** Every finding/change lands in BACKLOG.md
   (decision record, newest first) and CHANGELOG.md. No silent changes.

## Workflow
- **Claude Code: ALL work flows through branch + PR, daily-class
  included; Anthony merges.** (Ruling 2026-09-25, trust-building
  phase: CI exercises everything, the architect gets a review surface.)
  Never push to `main`. CI (parse + import smoke + pytest) must pass.
- Anthony's own hand-edits keep the direct-to-`main` lane for
  daily/operational changes, descriptive messages carrying receipts.
- **Gate-class changes** (model logic, training, acceptance criteria,
  export contracts): branch + PR with the template; backtest/gate
  output pasted in the PR body BEFORE merge.
- Tests live in `tests/` and run against a throwaway SQLite file
  (tests/conftest.py sets DATABASE_URL before any import) — never
  against data/.
- Never push a change that alters prediction outputs without running
  the relevant backtest/gate and including its verdict.

## Current production state (2026-09-25)
- **MLB**: model v2 live; ~57% sides over 400+ graded; candidate
  `improve` rejections are routine and CORRECT (bar: 0.0050 log-loss).
- **Soccer**: soccer_elo_poisson **v22** on the 16,546-match / 24-comp
  pot; PL predictions live; positive-edge cohort (>=+5pp vs market) is
  6/16 — big anti-market edges are ANTI-PREDICTIVE; n=30 pre-committed
  read pending. Market-first discipline is doctrine.
- **NFL**: nfl_elo_v1 **LIVE since Week 3** (2026-09-22). Export
  carries market_divergence_pp + quarantine (|div|>=15pp) — contract
  fields; consumer treats quarantined rows as never-straight-plays
  (mega-edges went 1-5 in weeks 1-2).
- **NHL**: data certified (4,410 games, FT/AOT/AP mapped, true-zero
  nulls); Kalshi KXNHLGAME live. NO MODEL YET — the frozen gate stands
  (`nhl-backtest`); v1, v2 and v3 FAILED (ledger in BACKLOG). **v4 is
  the LAST schedule-only candidate**; if it fails there is no v5: NHL
  opens Oct 7 MARKET-ONLY (NCAA/UNL pattern) and the model track
  SUSPENDS until the H2 goalie-feed probe reopens it. The bar does not
  move.
- **NCAA**: data certified (9,245 games, 743 programs); market-only
  doctrine; Kalshi (KXNCAAFGAME) is the PRIMARY college market source,
  books post thin and near-kickoff. NO model; own gate later.
- **UNL / cups (EFL, CL, UEL)**: market-only. CUP MODEL TRACK
  SUSPENDED 2026-09-25 (fix-v2 re-exam FAIL, 14.76pp: a rotation
  information floor). EFL/CL/UEL stay market-only for the season; the
  exam harness + fix-v2 machinery stay merged. Reopens only via a
  rotation-aware candidate on as-of lineup data (R-track, winter).
  UNL likely market-only permanently.
- Season strings: soccer clubs "2026/27"; WC "2026"; UNL "2026/27";
  MLB/NFL/NHL/NCAA int-style "2026". Per-comp truth is what the DB
  stores — check, don't assume.

## Committed queue (execute in order; specs from the architect)
1. **Cup acceptance exam** (gate-class -> branch+PR): add an
   `include_finished` REPORT-ONLY mode to the soccer prediction path
   (NEVER write Prediction rows for played games), then score v22
   against `exports/cup_answer_key.csv` (regenerable via
   scripts/extract_cup_key.py; 55 fixtures: EFL 36, CL 19). Frozen
   bar: ±8pp mean absolute vs the books' fair, plus sign-sanity on the
   round-2 EFL rows (the league-bonus defect probes). PASS unlocks
   EFL/CL/UEL predictions. **STATUS: built, run three times (FAIL ×3),
   track SUSPENDED 2026-09-25 — see production state above.**
2. **NHL Phase 2** (gate-class): clone the NFL backtest harness shape
   for hockey (train 2024, test 2025; preseason EXCLUDED by status/
   date); freeze acceptance BEFORE building Elo v1; then the NFL
   sequence (internal week, rehearsal+dry read, live decision).
   **STATUS: gate built; v1-v3 FAILED; v4 (last schedule-only) in
   flight; Oct 7 market-only fallback logged.**
3. **Cockpit v0.4** (artifact-side — coordinate with the architect;
   the live artifact is chat-published): results intake +
   call-persistence + self-grading by rule; two feedback streams.
4. NCAA model (own gate, no deadline), U2 export enrichment
   (model-internals "why" fields + NFL kalshi field), S14 Stage-2,
   snapshot pruning design.
5. Tail (architect deep-research disposition 2026-09-25; after cup
   unlock + NHL v3): S19 time-decay match weighting (soccer candidate,
   existing gate); S20 RPS reported alongside log-loss in the soccer
   backtest (metric only, bars unchanged); H2 NHL goalie track (probe
   the provider's starting-goalie/lineup feed first; goalie-aware
   candidate post-v3). DATA ITEMS: football 90-minute score + ET/PEN
   flag (store score.fulltime + raw status); NHL OT/SO raw status.
   RETIRED: S18 (Dixon-Coles already shipped, rho = -0.10; dynamic-rho
   only with a motivating receipt). DECLINED: xG/tracking/boosting (no
   data ownership), threshold re-tuning from small graded samples,
   tuning to the market (doctrine).

## Operational notes
- Morning chains open with the backup line. 2-day sync windows daily;
  full-season weekly. The O(n^2) match-sync was fixed via a per-sync
  prefetch cache — do not regress it.
- sync-competitions must run before a new sport's first team/match
  sync (the NHL bootstrap lesson).
- Kalshi: shared parameterized matcher, four series
  (KXMLBGAME/KXNFLGAME/KXNHLGAME/KXNCAAFGAME); ambiguous matches are
  REFUSED by design (sentinel). Do not "fix" refusals into guesses.
- BACKLOG.md newest-first is the project's memory. Read the top 30
  entries before starting anything.
- **The market is a reference, never a model feature.** Spread-blending
  improves forecasts but kills edge detection; the product is the
  disagreement. (Architect doctrine, 2026-09-25.)
- NHL context: the MoneyPuck public benchmark is 0.648-0.661 log-loss;
  our gate certifies better-than-schedule-naive, not market-competitive
  (bar unchanged).
