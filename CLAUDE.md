# CLAUDE.md — read this before touching anything

You are working on **sports_predictor**: a multi-sport prediction and
calibration system (Python/SQLite/SQLAlchemy, CLI-driven) feeding a
browser Cockpit (tools/cockpit.html, published separately as a Claude
artifact — do not treat the repo copy as the live one). The operator is
Anthony; architectural decisions, gate verdicts, and enhancement specs
come from his Claude chat ("the architect"). Your job is disciplined
execution of those specs. When a spec and this file conflict, stop and
ask.

## Mission (architect, declared 2026-09-26)
"Generate consistent income from sports predictions — sports as
commodities, every game an asset class, optimized for prediction markets
(Kalshi-native). Operationally: edge × stake × volume, survived —
positive EV measured, not felt; CLV the leading indicator; the P&L
ledger the income statement every policy change must cite. The gates
become MORE binding under an income goal, never less."

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
   Every known limitation, finding and queued lane is ALSO an Issue
   (the state ledger, docs/LEDGER.md): "log attributed in BACKLOG" in a
   ruling means BACKLOG entry + Issue.

## Workflow
- **Claude Code: ALL work flows through branch + PR, daily-class
  included; Anthony merges.** (Ruling 2026-09-25, trust-building
  phase: CI exercises everything, the architect gets a review surface.)
  Never push to `main`. CI (parse + import smoke + pytest) must pass.
- **Release model (ruling 2026-09-30):** `main` = BETA (the laptop);
  PRODUCTION = tagged releases only (`vX.Y.Z`; the host deploys tags,
  never `main`). A tag is cut only by the architect's ruling after the
  day's laptop-vs-host compare passes; hotfix = a patch tag, same ritual.
  Claude Code never cuts or pushes a tag. docs/RELEASES.md.
- Anthony's own hand-edits keep the direct-to-`main` lane for
  daily/operational changes, descriptive messages carrying receipts.
- **Gate-class changes** (model logic, training, acceptance criteria,
  export contracts): branch + PR with the template; backtest/gate
  output pasted in the PR body BEFORE merge.
- **The ledger (ruling 2026-09-29):** a PR that resolves an Issue says
  `Closes #N` (a limitation also needs `Resolves limitation`); an Issue
  never closes by hand without a linked PR or a quoted architect ruling.
  Labels come from the fixed set only (one track:/class:/sport:/size:).
- **Codex reviews (ruling 2026-10-05):** Codex reviews are INPUT under
  the fence, handled exactly like Anthony's review comments: verify, then
  fix-and-reply on trivia (correctness bugs in the PR's own code,
  nits); ESCALATE anything policy/gate/ledger-semantic to the architect
  (`needs-ruling`), never act on it. A Codex suggestion never changes a
  frozen threshold or a verdict.
  Tagging (ARCHITECT, 2026-10-05): the ONLY mention is the review-request
  phrase `@codex review`, posted once as its own comment after pushing
  fixes for Codex's findings. Thread replies NEVER contain the handle, in
  any formatting (backticks and quotes included): any other mention starts
  a Codex cloud task, which tried to run on all nine tagged replies of
  2026-10-05 and on one reply that only quoted the phrase.
- **REVIEW STOP RULE (ARCHITECT, 2026-10-08, addendum 7 item 2, standing,
  verbatim):** "Reviews are input; the architect rules merge-readiness. (1) A
  PR is merge-ready when CI is green and every P1 has a fix or a ruling. (2) P2
  findings get one fix round. After the second review round, remaining and new
  P2s on read-only code (receipts, probes, reports, docs, tests) go to ONE
  follow-up Issue for that PR and do not block; on money-path code (the Desk,
  models, exports the Desk reads, the ledger, deploy scripts) list them for the
  architect, who says which block. (3) Hard cap: three review rounds per PR,
  then request no more reviews and report 'round cap reached' with the open
  list. (4) A rebase or merge-from-main push needs green CI, not a new review
  round. (5) A PR that carries a policy change and tooling ships the policy
  change first, as its own small PR." Evidence: #340 took 154 findings (148
  P2, 6 P1) over 62 commits; its follow-up home is #347.
- **PR text (ARCHITECT, 2026-10-06, standing rule):** quoted heredocs only
  (`<<'EOF'`) for PR bodies, comments and commit messages. An unquoted heredoc
  runs every backticked span as a shell command: on 2026-10-06 one ran
  `python cli.py nfl-grade`, which created an empty DB under the container's
  data/ and blanked the span in #290's body.
- **Sweep (ARCHITECT, 2026-10-05):** an UNANSWERED Codex thread on a
  MERGED PR is a finding in its own right: verify it, then fix it in a
  follow-up PR or escalate it. #278's missed P1 left a grading close that
  never fired on main for three hours (fixed in #288).
  After the review stop rule's cap, an open thread is answered with the
  PR's follow-up Issue number, not another fix round (amended ARCHITECT
  2026-10-08, addendum 7 item 2).
- Tests live in `tests/` and run against a throwaway SQLite file
  (tests/conftest.py sets DATABASE_URL before any import) — never
  against data/.
- Never push a change that alters prediction outputs without running
  the relevant backtest/gate and including its verdict.

## Current production state (2026-09-25)
- **MLB**: model v2 live; ~57% sides over 400+ graded; candidate
  `improve` rejections are routine and CORRECT (bar: 0.0050 log-loss).
  Predictions are a LAPTOP duty (PHASE B negative, 2026-09-29); the host
  keeps MLB history from the api-sports fallback (PHASE A).
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
  (`nhl-backtest`). **PHASE 2 CLOSED 2026-09-25:** v1-v4 all FAILED
  (0.6909 / 0.6921 / 0.6952 / 0.6907 vs the 0.6866 bar — the
  schedule-only floor is ~0.691). MODEL TRACK SUSPENDED; NHL runs
  MARKET-ONLY via `export-fixtures --competition NHL` (season gate
  2026-09-29, the operator-confirmed opening day). The goalie probe came
  back NEGATIVE (2026-09-26): the reopening condition is an EXTERNAL
  goalie/lineup source. The bar did not move.
- **NCAA**: data certified (9,245 games, 743 programs); market-only
  doctrine; Kalshi (KXNCAAFGAME) is the PRIMARY college market source,
  books post thin and near-kickoff. NO model; own gate later.
  ncaa-elo-v1r (v1's constants on the CFBD both-FBS stream, test 2025) FAILED its
  gate 2026-10-09 on the spread test: slope 1.42 against 0.80 to 1.20, too timid;
  margin, level and range passed. 2025 is RETIRED as a college test season; the
  next candidate declares the 2026 regular season as it accrues. No college
  shadow and no ncaa-backtest until then. The bar did not move.
- **UNL / cups (EFL, CL, UEL)**: market-only. CUP MODEL TRACK
  SUSPENDED 2026-09-25 (fix-v2 re-exam FAIL, 14.76pp: a rotation
  information floor). EFL/CL/UEL stay market-only for the season; the
  exam harness + fix-v2 machinery stay merged. Reopens only via a
  rotation-aware candidate on as-of lineup data (R-track, winter).
  UNL likely market-only permanently.
- Season strings: soccer clubs "2026/27"; WC "2026"; UNL "2026/27";
  MLB/NFL/NHL/NCAA int-style "2026". Per-comp truth is what the DB
  stores — check, don't assume.

## Queue
The queue's ORDER lives on the GitHub Project board "sports_predictor
queue"; open state is the Issue list (docs/LEDGER.md). Read order from the
board, never from chat. The pre-board queue text is history (git log).

## Operational notes
- Morning chains open with the backup line. 2-day sync windows daily;
  full-season weekly. The O(n^2) match-sync was fixed via a per-sync
  prefetch cache — do not regress it.
- sync-competitions must run before a new sport's first team/match
  sync (the NHL bootstrap lesson).
- sync-teams before sync-matches for EVERY new competition-season.
  sync-matches skips listings whose clubs are not in the DB. The laptop
  was short 67 UEL 2024/25 games since July (qualifying-round clubs never
  team-synced; H1a finding 2026-09-27). The host bootstrap already does
  this; laptop routines must match.
- Kalshi: shared parameterized matcher, four series
  (KXMLBGAME/KXNFLGAME/KXNHLGAME/KXNCAAFGAME); ambiguous matches are
  REFUSED by design (sentinel). Do not "fix" refusals into guesses.
- BACKLOG.md newest-first is the project's memory. Read the top 30
  entries before starting anything.
- DECLINED (architect deep-research disposition 2026-09-25): xG /
  tracking / boosting (no data ownership), threshold re-tuning from small
  graded samples, tuning to the market (doctrine). RETIRED: S18
  (Dixon-Coles shipped, rho = -0.10; dynamic rho only with a receipt).
- **The market is a reference, never a model feature.** Spread-blending
  improves forecasts but kills edge detection; the product is the
  disagreement. (Architect doctrine, 2026-09-25.)
- NHL context: the MoneyPuck public benchmark is 0.648-0.661 log-loss;
  our gate certifies better-than-schedule-naive, not market-competitive
  (bar unchanged).
