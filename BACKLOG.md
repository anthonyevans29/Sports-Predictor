# Backlog

Living document — items deferred from earlier sessions plus future ideas with
the reasoning for the deferral. Update when items ship or new ideas land.

## Active themes

### Data foundation (current focus)
Building out player, team, and environmental data coverage so future modeling
work has rich features to draw from. Examples in progress or queued below.

### Daily ops + iteration
Predict → evaluate → improve → export, with incremental fixes as exports surface
issues. Park factors and reliever-as-starter fix shipped recently in this mode.

---

## Feature backlog

Roughly ordered by expected value vs effort. Items marked **[DEFERRED]** have a
specific reason they're not being built now.

### MLB / baseball

- **FULL-LOOP RULING 2026-09-26 (architect): the recommendation layer
  gains a SECOND ENGINE so every dual-venue sport emits positions.
  Extends the Cockpit v0.4 build; POLICY BUMPS v1.0 -> v1.1 (evidence-
  set unchanged for model_edge; venue_edge added in SHADOW).**
  (1) LEDGER SCHEMA: every call carries `engine: "model_edge" |
  "venue_edge"`; all existing capture = model_edge.
  (2) VENUE-EDGE ENGINE (Desk tab; market-only rows stop being
  skipped): rows with BOTH a book consensus (bookmaker_count >= 4) AND
  kalshi two_sided -> venue divergence = book_fair - kalshi_prob per
  side; a candidate exists when |divergence| >= 5.0pp (FROZEN
  a-priori). Call = the side books say Kalshi UNDERPRICES, FIXED 0.25u,
  tier "shadow", venue_hint kalshi. UNL and any single-venue row:
  excluded, labelled "single venue — no pair". In-play never. Parlays
  remain model_edge-only (frozen).
  (3) CAPTURE + GRADING: venue-edge calls log via the same button,
  grade via the same results intake; the Ledger tab reports BY ENGINE
  — the two income lines the mission needs, separated.
  (4) NON-CLAIM footer addition: venue-edge P&L uses the stored kalshi
  prob as a price proxy until the K-track delivers executable bid/ask
  accounting; first 50 graded calls PER ENGINE before any sizing change
  is proposable.
  EXECUTOR NOTES (read-before-build): the fixtures export already
  carries a top-level `kalshi` block per row (`status`, per-side `prob`
  = de-vigged, `captured_at`) beside `market.bookmaker_count` +
  `market.fair_prob`, so the venue divergence is computable from
  existing export fields — no export-contract change needed. The repo
  cockpit's normalize() currently reads only the kalshi STATUS
  (`input_quality.kalshi`) for market-only rows; the build must read
  `f.kalshi.prob`. Spread-derived fair never qualifies as book_fair
  while the fallback is dark (FALLBACK_LIVE = False). BUILD STATUS:
  held — docs/specs/cockpit-v04-pnl-organ.md (the v0.4 base spec) is
  not yet in the repo; the venue-edge extension lands with or stacked
  on the v0.4 build once it arrives.
- **HOSTING H0 DRAFT 2026-09-26 (docs-only, for architect review — not
  a decision):** docs/specs/hosting-h0.md. VPS candidates (Hetzner /
  DigitalOcean / Akamai-Linode / Vultr, prices approx., verify at
  purchase); Tailscale-only posture (no public ports; web UI stays on
  127.0.0.1 behind an SSH tunnel because guards.py's require_localhost
  would be widened to the whole tailnet by `tailscale serve`); systemd
  unit inventory mapped from docs/CLI.md + pl_weekly_routine.md chains
  (backup-before-chain via Requires/After; soccer-refresh pulls its own
  pre-refresh .backup; OnFailure notifier; flock'd DB lock); migration
  runbook (.backup -> sha256 both ends -> scp over tailnet -> integrity
  + row-count receipts; 7-day parallel run with the laptop as writer of
  record and the host copy DISPOSABLE; cutover = a second fresh
  .backup); receipts JSON-lines spec. LAW 1 RECEIPT: all CLI.md command
  names exist among cli.py's 82 @cli.command decorators; discrepancies
  D1-D8 logged in the doc (notably `sync-matches --date` has no such
  option; `sync-kalshi-ncaa` undocumented in CLI.md; CLI.md still says
  weekly backup). 21 ARCHITECT-RULE questions. Nothing built or bought.
  Queue position unchanged (T-track groundwork behind v0.4/K/B).

- **SPREAD->WIN-PROB FALLBACK (gate-class-lite, architect spec
  2026-09-26) — built; acceptance receipt pending Anthony's real run;
  bar 3.0pp frozen before results.** Where an american-football game
  (NFL, NCAA — NCAA is Sport.NFL + Competition.code "NCAA") has NO 1X2
  consensus but SPREADS exist, the market-reference fair is derived by
  the normal-margin transform P(home) = Phi(-s/sigma), s = median across
  books of each book's main HOME line (negative = home favoured; the
  adapter stores "Home -3.5" as HOME/-3.5, sign preserved). Sigmas
  frozen a-priori, never tuned: NFL 13.45, NCAA 16.5. Main line per book
  = the HOME L / AWAY -L pair with the most balanced prices (alternates
  ignored); pre-kickoff latest capture per (book, selection, line).
  Export contract, additive only: every market block now carries
  `fair_source` ("1X2" | "spread_derived"); derived blocks also carry
  `consensus_home_spread` + `spread_sigma`. Applies in `export-fixtures`
  (NFL/NCAA) and the NFL predictions export. DELIBERATE: the NFL
  `market_divergence_pp` / `quarantine` contract stays computed on the
  1X2 consensus only — spread-derived fair does NOT feed it (architect
  to rule if it should). Receipt: `python cli.py spread-fallback-check
  --competition NFL [--start YYYY-MM-DD --end YYYY-MM-DD]` (and NCAA) —
  read-only; on games carrying BOTH markets prints the table + n, mean
  |derived - 1X2 fair| pp, VERDICT vs <= 3.0pp. Code:
  src/walters/spread_fallback.py; tests/test_spread_fallback.py.

- **data/ mkdir moved import-time -> connect-time 2026-09-26 (lane 4 of
  the architect's expanded parallel authorization; the CI-hygiene nit
  from #19):** `src/db/database.py` created the SQLite directory at
  IMPORT, so `import cli` (CI's import smoke) left an empty data/ behind.
  The mkdir now runs in a `do_connect` engine event — before the first
  DBAPI connect — so the first real connection still finds its
  directory. Receipts: the new subprocess test fails on the old code
  (import created the dir) and passes now; `import cli` leaves no data/.
  Engine, pragmas and DATABASE_URL handling otherwise unchanged.
- **`sync-odds-nfl` RENAMED -> `sync-odds-football` 2026-09-26 (lane 3
  of the architect's expanded parallel authorization; cosmetic):** the
  command's Sport.NFL family filter already covers NCAA (verified in
  `sync_odds_nfl`: `Match.sport == Sport.NFL`; the Sport enum has no
  separate NCAA member), so the old name misled an operator. The old
  name stays registered as an ALIAS (same click Command object), so
  existing chains keep working. Console line now reads "Football odds
  (NFL+NCAA)". The service function name is unchanged (internal).
  docs/CLI.md + README updated.
- **NCAA BOOK-MARKET FINDING + two queued items 2026-09-26 (architect,
  from near-kickoff receipts):**
  (1) FINDING: the provider DOES carry college odds — labels seen
  1X2 x~45 vs SPREADS x665, TOTALS x1029 — but college books post
  SPREADS, not moneylines (US convention; no ML on 20-point favorites,
  e.g. Texas-Tennessee unpriced at T-60). Our consensus joins 1X2 only
  -> 12/116 fixtures carry a book consensus while Kalshi covers 99/116
  (154 prices, 59 two-sided). Kalshi-primary doctrine for college
  CONFIRMED at matchday scale.
  (2) RULED + QUEUED (K-track, architect-specced, AFTER Cockpit v0.4):
  spread -> win-probability conversion as the fair-price FALLBACK where
  1X2 is absent. It is an EXPORT-CONTRACT change; the spec comes from
  the architect. NOT built now.
  (3) COSMETIC QUEUED for the next daily batch: rename `sync-odds-nfl`
  -> `sync-odds-football`, keeping the old name as an alias. Its
  Sport.NFL family filter already covers NCAA; the name predates the
  sixth family and caused an operator double-check today. Not done in
  this docs-only PR.
- **NFL MODEL PATHS HARD-SCOPED TO competition "NFL" 2026-09-26 (lane
  6, architect PRIORITY, adjudicating #26's scope flag before Sunday's
  predict-nfl):** READ receipts (pre-fix): NCAA football is stored under
  Sport.NFL with Competition.code "NCAA", and EVERY NFL model path
  filtered on `Match.sport == Sport.NFL` ONLY — rating build
  (`nfl_predict._current_ratings`), the backtest/gate pot
  (`nfl_backtest.run_backtest`), the prediction set (`predict_nfl`),
  `export_nfl_predictions`, `grade_nfl`, `export_nfl_results`.
  home_advantage is a FIXED config constant (48.0 Elo), not data-derived
  — no contamination path there. Consequences had NCAA rows been present:
  college games in the gate's baseline + scored sets (the synthetic
  receipt reproduces it: 68 games = 64 NFL + 4 NCAA); NCAA fixtures
  getting nfl_elo_v1 Prediction rows, exported and graded as NFL. NFL
  games' OWN probabilities were not moved (Elo updates are pairwise and
  the two team sets are disjoint), but the prediction/export/grade sets
  and the backtest verdict were exposed. FIX: one helper,
  `nfl_backtest.nfl_scoped()`, joins Competition and pins
  `Competition.code == "NFL"` on every path above. RECEIPT: predict-nfl
  prints `scope[ratings]` + `scope[prediction set]`, nfl-backtest prints
  `scope[nfl-backtest]` — `teams=N, games=N, competitions={...}`, with a
  SCOPE ALERT suffix whenever competitions != {NFL} or teams != 32.
  TIMELINE (architect): the live Week-3/4 exports predate NCAA's
  backfill — no polluted artifact exists; this closes the gap before
  the first at-risk run (Sunday). Out of scope, left as-is: sync-odds-
  football (family-wide by design), capture-weather-nfl (tracking only;
  NCAA home teams already skip the stadium lookup).
- **H2 GOALIE PROBE VERDICT — NEGATIVE, definitively (architect,
  2026-09-26, from Anthony's run of the fixed probe):** the hockey
  provider rejects /games/lineups, /games/players, /players, /injuries
  and every statistics endpoint ("do not exist"); only /games/events
  answers (goals/penalties, NO goalies), deep to 2023+.
  (1) H2 REOPENING CONDITION RESTATED: an EXTERNAL goalie/lineup data
  source entering the stack — a future sourcing decision; there is no
  queued item against the current provider. NHL stays MARKET-ONLY
  INDEFINITELY.
  (2) NEGATIVE-RESULT DOCTRINE: a probe returning "no" is a success —
  26 requests closed a track's open question.
  (3) LEDGER ONLY (not queued): /games carries per-period score splits,
  currently unstored — a possible future data item.
  The 2026-09-26 bounded authorization is FULLY CLOSED (items 1-4
  done). Stand down: next architect contact is the revised score-90
  tribunal PR reported green, then nothing until the Cockpit v0.4 spec.
- **migrate_score_90 INVARIANT REVISED 2026-09-26 (architect ruling,
  daily-class):** Anthony's first run printed BREACHED, but FT 370/370
  (90' == stored) says score.fulltime = 90' semantics are LIKELY RIGHT
  and the invariant LIKELY WRONG: the pot's AET/PEN rows include
  TWO-LEGGED qualifying ties, where ET triggers on AGGREGATE level — a
  second leg need not be level at 90'. Revised law: FT 90' == stored
  stays MANDATORY; every AET/PEN row asserts 90' <= stored per side (ET
  can only add goals); level-at-90' applies ONLY to SINGLE-match ties,
  classified by STAGE (FAC/CS/WC/EURO every round; any "Final";
  EFL all but the semis; UEFA club comps only "Preliminary Round";
  UNL finals four). Unknown stages stay UNCLASSIFIED (universal check
  only — never guessed into the strict law). The receipt now PRINTS
  every breaching row verbatim (comp, season, stage, date, teams,
  stored, fulltime, class, leg1 = a reverse fixture earlier in the
  comp+season) plus the AET/PEN stage-classification vocabulary table,
  and the verdict line re-prints HOLD/BREACHED under the revised law.
  No column changes. Anthony re-runs the migration after merge; rows +
  verdict go to the architect.
- **MORNING FINDINGS 2026-09-26 (architect, from Anthony's real runs):**
  (1) STATUS_RAW SPLITS (after #16's migrate + full NHL sync): 20-25%
  of NHL games are decided past regulation — 2024: 1194 FT / 229 AOT /
  79 AP; 2025: 1128 FT / 242 AOT / 128 AP. This is the MEASURED
  mechanism behind the ~0.691 schedule-only floor, and H2's SECOND
  conditioning variable (after the goalie). (2) LINEUP PROBE VERDICT
  GREEN: XI + formation from ~2015 (EFL / CL / UEL / PL / ELC);
  per-player minutes from ~2018, domestic-English only; FAC has
  early-round holes. Winter rotation R-track FEASIBLE; the T-60
  re-price architecture stands. No implementation implied — the
  tracks' specs come from the architect.
- **H2 PROBE FIX 2026-09-26 (architect-directed):** the probe crashed
  in `_game_ids` — hockey /games items carry "date" as an ISO STRING
  (with a top-level "timestamp"), not football's {"timestamp": ...}
  dict. The probe violated law 1 on the very payload it was probing
  (and its test fixture guessed the same wrong shape). Fix: print ONE
  raw /games object verbatim FIRST (the vocabulary receipt), then parse
  date/timestamp tolerant of both shapes (unparseable -> 0, never
  raises); the test fixture now uses the real flat shape and
  reproduces the crash on the old code. PR #17 had already merged, so
  this rides a NEW PR from the same branch restarted on main.
- **Soccer ET flag + 90-minute score STORED 2026-09-26 (authorization
  item 2 of 4, daily-class; the fix-v2 ET label-contamination data item,
  architect ruling 2026-09-25 "store API-Football score.fulltime and the
  raw AET/PEN status going forward"):** the football adapter now sets
  matches.status_raw (FT / AET / PEN ... verbatim; absent stays NULL —
  captured before the parser's "NS" default) and stores score.fulltime
  in NEW nullable matches.home_score_90 / away_score_90. The ET flag IS
  status_raw in (AET, PEN) — no extra column. home/away_score (`goals`,
  incl. ET) and full_time_result are UNCHANGED: storage only, nothing
  reads the new columns (labels/model/export untouched). Ingestion
  never blanks a stored 90' score. `migrate_score_90.py` (idempotent
  ADD COLUMN) prints soccer FINISHED rows by status_raw plus two
  law-1 INVARIANTS verifying that score.fulltime really is 90': AET/PEN
  rows level at 90', FT rows 90' == stored score. Populates going
  forward; any competition re-sync backfills it.
- **Lineup-history PROBE shipped 2026-09-26 (authorization item 4
  of 4, daily-class, read-only):** `scripts/lineup_history_probe.py`.
  Question: what historical soccer lineup data does API-Football hold
  per match, how far back, which fields — the cup R-track's reopening
  groundwork (rotation-aware candidate on as-of lineup data). League
  ids come from the adapter's own `_CODE_TO_LEAGUE_ID` (law 1). Per
  comp (default EFL, FAC, CL, UEL, UECL, PL, ELC; `--comps` overrides):
  Q1 the provider's DECLARED per-season coverage flags (fixtures.lineups
  / statistics_players / players) incl. gaps; Q2 SPOT CHECKS on one
  finished fixture in the latest finished, middle and earliest declared
  season — /fixtures/lineups (XI, subs, formation, coach, player id /
  pos / grid counts) and /fixtures/players (minutes, position,
  substitute flag). Throttled to API_FOOTBALL_RPM; ~10 requests/comp.
  No writes, no wiring. Note for the architect: provider lineups are
  published ~1h pre-kickoff, so history is post-hoc truth — "as-of" for
  a candidate means the lineup known at prediction time, which the probe
  does not (cannot) establish. Receipt is Anthony's real run.
- **H2 goalie/lineup PROBE shipped 2026-09-26 (authorization item 3
  of 4, daily-class, read-only):** `scripts/h2_goalie_probe.py`, the
  ncaa_phase0 pattern. Question: does the hockey provider
  (v1.hockey.api-sports.io, NHL league 57) expose starting goalies /
  lineups? Enumerates candidate endpoints (games/events, games/players,
  games/lineups, games/statistics, games/players/statistics, players,
  injuries) on the latest finished 2025 game, prints every field path
  plus goalie-hinting paths, checks historical depth on the earliest
  finished game of 2025/2024/2023 for endpoints that answered, and
  checks the next upcoming game for pre-game availability. No writes,
  no wiring, never raises past a failed endpoint. Receipt is Anthony's
  real run pasted to the architect — the H2 reopening condition for the
  NHL model track is judged there, not here.
- **ARCHITECT BOUNDED AUTHORIZATION 2026-09-26 (daily-class, in order,
  branch+PR each, NOTHING beyond):** (1) NHL raw status storage; (2)
  soccer 90-minute/extra-time storage; (3) H2 probe script (hockey
  starting goalies/lineups, read-only); (4) lineup-history probe script
  (soccer, read-only). Guardrails: no model/pricing changes, no
  export-contract changes, no threshold/queue edits, no policy files.

- **ITEM 1 — NHL RAW STATUS STORAGE 2026-09-26:** new nullable column
  matches.status_raw (VARCHAR 16) = the provider's status code verbatim;
  NormalizedMatch.status_raw; ingestion writes it on create and on
  update (never blanks a stored code with an absent one); the hockey
  adapter now passes FT / AOT / AP through — OT/SO wins become
  distinguishable (H2 reopening groundwork). LAW-1 CATCH: the parser
  defaults a missing status to "NS", so the raw code is captured BEFORE
  that default — the 16 status-less 2024 games stay NULL, not a faked
  "NS". Mapped vocabulary + score-presence inference unchanged.
  MIGRATION: `python migrate_status_raw.py` (additive ADD COLUMN,
  idempotent) MUST run after merge, before any chain (the ORM maps the
  column). BACKFILL: the next full NHL sync populates existing rows;
  re-running the migration prints the per-season FT/AOT/AP receipt.

- **MISSION DECLARED 2026-09-26 (architect):** "Generate consistent
  income from sports predictions — sports as commodities, every game an
  asset class, optimized for prediction markets (Kalshi-native).
  Operationally: edge × stake × volume, survived — positive EV
  measured, not felt; CLV the leading indicator; the P&L ledger the
  income statement every policy change must cite. The gates become
  MORE binding under an income goal, never less." Logged as CLAUDE.md's
  top section. QUEUE RE-RANKS (mission consequences; specs to follow
  from the architect one at a time): (1) Cockpit v0.4 P&L/self-grading
  organ PROMOTED to the queue's head — it is the mission's measuring
  instrument; (2) K-TRACK OPENED: Kalshi-executable edge accounting
  (model_p vs stored ask, fee-adjusted floors, liquidity-aware sizing)
  — spec after v0.4; (3) B-TRACK OPENED: bankroll doctrine (daily
  exposure cap, drawdown circuit-breaker, cross-ticket correlation) —
  spec after K. T-track scheduler and H2/lineup probes hold their
  places behind these. No implementation yet. (CLAUDE.md queue: the
  closed cup-exam and NHL Phase 2 items moved to a "Closed (record)"
  list, status lines intact.)

- **NHL MARKET-ONLY LAUNCH WIRING 2026-09-25 (daily-class; the fifth
  sport's launch vehicle, before Oct 6):** `export-fixtures --competition
  NHL` = schedule + book consensus + Kalshi presence in the fixtures
  shape the Cockpit renders (UNL/NCAA pattern). LAW 1 READ: the NHL odds
  rows could not be read from here (no DB), so the WRITER was read —
  api_hockey._MARKET_MAP stores the moneyline as market "1X2" ("Home/Away"
  and "Moneyline" both), selections HOME/AWAY only (draw legs and
  unmapped bets dropped) — and the command now PRINTS the (market,
  selection) labels it actually finds and warns loudly if odds exist but
  none are "1X2": Anthony's first run is the row-level receipt. CONSENSUS
  HYGIENE (all fixtures files): latest capture per (book, selection),
  captures at/after kickoff excluded (the predictions export's in-game
  guard), then the de-vigged mean — the old join averaged every stale
  capture. KALSHI: latest pre-kickoff OddsSnapshot(source="kalshi") per
  selection -> two_sided / one_sided / absent (the predictions export's
  vocabulary), under `kalshi` + `input_quality`. PER-COMPETITION NOTE:
  NHL's file states the suspension; cups theirs. COCKPIT (repo copy;
  republish = architect): fixtures cards now read input_quality.kalshi,
  and the PRE-EXISTING header bug is fixed — the fixtures branch read
  doc.sport||doc.competition while the export has always written
  competition_code, so every market-only file rendered under a "?"
  header (headless before/after: "?" -> "NHL"). DOCS: CLI.md market-only
  section + the NHL daily chain; README market-only line.

- **NHL PHASE 2 CLOSED — MODEL TRACK SUSPENDED (architect, 2026-09-25,
  per the pre-logged ruling):** v4 FAIL ratified (0.6907, margin only;
  selection CONVERGED TO v1's exact params). FOUR-LINE LEDGER (2025
  log-loss vs the 0.6866 bar): v1 0.6909 / v2 0.6921 / v3 0.6952 /
  v4 0.6907. FLOOR FINDING: the four-candidate ledger measures the
  schedule-only floor at ~0.691 vs the 0.6866 bar — tuning cannot buy
  the missing information. No v5; NHL launches Oct 7 MARKET-ONLY
  (NCAA/UNL pattern); the H2 goalie-feed probe is the REOPENING
  CONDITION. The bar did not move.

- **INFORMATION-FLOOR SYMMETRY (architect, 2026-09-25):** both new-sport
  model tracks hit NAMED information floors the same day — NHL:
  goalies; cups: lineups — as the deep-research disposition predicted.
  Schedule/identity-only models may sit below each bar's information
  floor, and the bars do not move to meet them.

- **CUP FIX-V2 RE-EXAM: FAIL — CUP MODEL TRACK SUSPENDED (architect,
  2026-09-25):** 14.76pp, sign 60% — inversion CLEARED and the
  improvement real (cross-league 19.51 -> 14.87, interior tuned coeffs).
  RULING: the residual is uniform across contexts and concentrated in
  mature-fit rows (ManU-Brighton -30.3 class) = ROTATION information
  floor — the market prices expected XIs, we price league identities.
  EFL/CL/UEL stay MARKET-ONLY for the season; fix-v2's machinery stays
  merged; the exam harness stands ready. REOPENING CONDITION (verbatim):
  "a rotation-aware candidate conditioned on as-of lineup data (R-track,
  winter — requires historical lineup backfill)."

- **NHL CANDIDATE v4 BUILT — THE LAST SCHEDULE-ONLY CANDIDATE
  (protocol note logged BEFORE v4 runs; architect ruling 2026-09-25):**
  the ledger's structural read — single-season selection does not
  transfer in this sport; large grids are done. v4 = shrink-direction
  only, tiny grid FROZEN a priori: k_factor {3,4,5,6} x home_advantage
  {35,40,45} x mov_base fixed 2.2 x NO rest terms x regression 0.25 =
  12 points; the v1 model form exactly (nhl_elo_v4); v3's walk-forward
  selection (60% fit / 40% validation inside 2024), full-2024 refit,
  2025 scored ONCE through the unchanged gate. HYPOTHESIS = the
  calibration signature: less reactive ratings compress the
  overconfident upper bands. IF V4 FAILS: NO v5 — the Oct 7
  market-only fallback fires as already logged (NCAA/UNL pattern) and
  the NHL model track SUSPENDS pending richer data; the H2 goalie-feed
  probe becomes the REOPENING CONDITION (goaltending is the missing
  signal class; schedule-only may sit below the bar's information
  floor, and the bar does not move to meet it). Run: `python cli.py
  nhl-backtest --candidate v4` (seconds).

- **NHL REJECTION LEDGER — nhl_elo_v3 FAIL (architect, 2026-09-25):**
  2025 log-loss 0.6952 — the third straight fail, and v1's untuned
  params remain the best 2025 scorer; upper bands -10.3 / -12.0pp =
  overconfidence only at the top. RECEIPT OWED (executor, from the
  merged code): home_advantage = 55 WAS in v2's grid — V2_GRID
  (commit 2154b30) = (15, 25, 35, 45, 55) — and v3 carried that axis
  UNCHANGED (V3_GRID, bd49bcf); the v3 spec extended only k /
  mov_base / b2b_penalty / rest_per_day, so nothing was added above an
  old maximum.

- **ARCHITECT RULINGS on fix-v2's two findings (2026-09-25):**
  (1) ET LABEL CONTAMINATION — ACCEPTED: queue the 90-minute-score /
  extra-time-flag DATA ITEM (store API-Football score.fulltime and the
  raw AET/PEN status going forward) — the football twin of the NHL
  OT/SO status-storage gap (H-track data item). TUNE-TO-MARKET DECLINED
  on doctrine (the market is a reference, never a model feature — it
  is not a tuning target either); fix-v2 keeps the outcome target.
  (2) S18 RETIRED as already-shipped (dixon_coles_rho = -0.10, applied
  2026-08-14) — architect's miss. Dynamic-rho only ever enters with a
  motivating receipt.

- **DEEP-RESEARCH DISPOSITION (architect, 2026-09-25):** the literature
  review validated core doctrine — layered architecture, proper scoring
  rules + calibration bands, simple-models-survive, small-sample
  threshold dangers. NEW DOCTRINE (CLAUDE.md notes): the market is a
  reference, never a model feature — spread-blending improves forecasts
  but kills edge detection; the product is the disagreement. QUEUE
  ADDITIONS (tail, after cup unlock + NHL v3): S18 Dixon-Coles
  low-score correction (soccer candidate, existing gate); S19 time-decay
  match weighting (separate candidate, same gate); S20 RPS reported
  alongside log-loss in soccer backtest output (metric addition, bars
  unchanged); H2 NHL goalie track — probe the provider's starting-
  goalie/lineup feed first (data item), goalie-aware candidate post-v3;
  NHL context line: MoneyPuck public benchmark 0.648-0.661 (bar
  unchanged — our gate certifies better-than-schedule-naive, not
  market-competitive). DECLINED on record: xG/tracking/boosting (no
  data ownership), threshold re-tuning from small graded samples.
  EXECUTOR NOTE (law 1, for the architect): a Dixon-Coles low-score
  correction already SHIPPED — PoissonConfig.dixon_coles_rho, "APPLIED
  2026-08-14: rho = -0.10 set on production soccer_elo_poisson v13" and
  "rho=-0.10 JOINTLY confirmed" at the 0.0008 coeff (2026-08-15). S18
  may mean a rho re-examination or a different correction — scope it
  before it becomes a candidate.

- **CUP FIX-V2 BUILT 2026-09-25 (gate-class; spec FROZEN before any
  run):** SPEC (architect): retune the cup path's elo_goal_coeff in TWO
  contexts — same-league ties and cross-league ties — by as-of
  leave-self-out log-loss on PRIOR cup matches in the pot EXCLUDING the
  exam's competition-seasons (EFL/CL/UEL current seasons out; prior cup
  seasons + other cups in); league (non-cup) pricing provably untouched;
  rulings 5 and 6 unchanged; the frozen exam (unchanged bar, floor 45)
  is the sole test. If cross-league context alone can't clear the bar,
  the next candidate is a league-bonus refit — one candidate at a time.
  FROZEN GRID (a priori, ascending from the status quo so ties keep the
  smaller value): {0.0008, 0.0012, 0.0016, 0.0020, 0.0024, 0.0030,
  0.0040, 0.0050}, same grid for both contexts. BUILT: context =
  same_league when both clubs' DOMESTIC leagues (the cup strength
  source's) are equal, else cross_league; the contexts are separable
  (a fixture's coeff comes from its own context), so each takes its
  own argmin of mean 3-way log-loss; tuning prices every pool fixture
  on the EXACT shipped cup path (report-only, as-of, ruling B) at every
  grid coeff in one pass; `cup-exam` tunes first (read-only, receipts
  printed) then prices the exam at the chosen pair (`--cup-coeffs
  base` reproduces the previous exam). Nothing persisted: live cup
  pricing reads params["cup_elo_goal_coeff"] (TOP-LEVEL — never inside
  "poisson", whose PoissonConfig(**) would reject the key), absent =
  base coeff = unchanged; the unlock PR persists the chosen pair.
  EXECUTOR CALLS (ARCHITECT-RULE in the PR): exclusion = every
  EFL/CL/UEL + EL-alias competition in every season the key covers
  (the key has 0 UEL rows; the adapter maps EL and UEL to the same
  league); LABEL CONTAMINATION FOUND — API-Football `goals` (stored as
  home/away_score) include EXTRA TIME (pens excluded), and neither
  score.fulltime nor the raw AET/PEN status is stored, so knockout ties
  level at 90' and decided in ET are labelled wins against a 90-minute
  1X2 price (pens-decided ties stay draws; league-phase games clean) —
  the target is as specified, the contamination is named, and a
  vs-market target would be a small switch if ruled; residual
  look-ahead = today's Elo state prices prior-season cup games (the
  ruling-7 class, now inside the tuning pool too).

- **CUP RE-EXAM VERDICT: FAIL (architect, 2026-09-25):** sign inversion
  tripwire fired (2/5), mean 18.11pp. Structural receipts perfect (0/50
  self-fit, 5 ruling-B rows, floor honored) — the honest exam unmasked
  what self-fit hid. ANATOMY: (1) cross-tier inversion class — own-
  league-relative strengths delegate cross-league separation to
  Elo+bonus per ruling 6, but elo_goal_coeff 0.0008 (PL-tuned) mutes the
  delegate: strong lower-division sides price as tier-equals (Fleetwood
  42.9 vs mkt 18.8; City-Norwich 55.3 vs 85.8). (2) Early-season domestic
  thinness (Aug rows n=1-2) — accepted under ruling 5, no change now.
  -> FIX-V2 (above).

- **NHL STANDING FALLBACK (architect, 2026-09-25):** if no candidate
  passes the frozen gate by Oct 6, NHL launches Oct 7 MARKET-ONLY (the
  NCAA/UNL pattern); the model joins when it passes. The opener is a
  date, not a gate.

- **NHL PROTOCOL AMENDMENT — v3 SELECTION (architect, 2026-09-25;
  logged BEFORE any v3 run, per gates-decide):** candidate parameters
  are SELECTED BY WALK-FORWARD VALIDATION INSIDE 2024: fit on the first
  60% of the 2024 sequence (chronological; warm-up, update only),
  select by sequential loss on the remaining 40% (validation never in
  the fit), REFIT on all of 2024 at the chosen params, then score 2025
  ONCE through the unchanged gate. GRID (frozen, 8,400 points): the v2
  ranges kept, extended DOWNWARD/CENTER only — nothing above the old
  maxima (the corners already testified): k {2,3,4,5,6,7,8,10} ·
  mov_base {0.5,1.0,1.6,2.2,3.0,4.0} · home_advantage {15,25,35,45,55}
  (unchanged) · b2b_penalty {0,5,10,15,20,30,45} · rest_per_day
  {0,2.5,5,7.5,10}. Regression stays 0.25. THE BAR IS NOT TOUCHED —
  the calibration criterion is doing its job. Model form = v2's
  (nhl_elo_v3 = v2 form, new selection). EXECUTOR CALL (ARCHITECT-RULE):
  "sequential loss on the 40%" = predict-then-update through the
  validation games (each priced BEFORE its own result updates the
  ratings) — the same walk-forward protocol that scores 2025; frozen
  ratings across the 40% would score stale Elo no deployed model uses.
  Run: `python cli.py nhl-backtest --candidate v3` (~1 min).

- **NHL REJECTION LEDGER — nhl_elo_v2 FAIL (architect, 2026-09-25):**
  2024-internal 0.6741 -> 0.6699 but 2025 REGRESSED to 0.6921 (worse
  than v1's 0.6909); calibration FAILED all three gated upper bands
  (overconfident); 4/5 params at grid edges. DIAGNOSIS: full-internal
  single-season tuning rewards sharpness with no counterweight —
  selection overfit. -> v3 protocol amendment (above).

- **CUP FIX — ARCHITECT RULINGS on the seven executor calls
  (2026-09-25):** (1) RATIFIED — the fix applies to live cup pricing;
  the exam must test what ships; cups stay locked regardless, unlock is
  a separate post-PASS PR. (2) RATIFIED WITH ONE AMENDMENT — market-only
  rows are excluded from scoring and from the INVALID count (policy,
  not missing data), BUT a COVERAGE FLOOR: scored n below 45 of 55 =
  exam INVALID (insufficient coverage); the five known out-of-pot rows
  leave n = 50, and the floor guards the exam's meaning if ruling B
  ever eats more. BUILT: MIN_SCORED = 45 (inclusive — 45 is valid);
  precedence drift-INVALID > coverage-INVALID > inversion > bar.
  (3) RATIFIED — no Elo OR no synced league both trigger ruling B.
  (4) RATIFIED — a synced-league team with no games yet prices at
  neutral strength with its real Elo; honest, not excludable.
  (5) RATIFIED — no last-season fallback; the removed same-cup
  prior-season fallback was part of the noise; early-season thinness
  is honest thinness. (6) RATIFIED — own-league-relative strengths;
  cross-league separation belongs to Elo + bonus. (7) ACKNOWLEDGED —
  residual Elo/injury look-ahead stays out of scope; already priced
  into the exam's necessary-not-sufficient semantics.

- **CUP FIX BUILT 2026-09-25 (gate-class; architect CUP FIX SPEC after
  the --detail receipts closed the diagnosis — 34/83 teams n=1, 29 n=2,
  55/55 self-fit, mirrored n=1 pairs = noise symmetry).** SPEC (as ruled):
  (1) EXAM HONESTY — as-of-date, leave-self-out fits: the priced match
  and later matches never enter any fit (measurement fix; live already
  sees only prior games). (2) STRENGTH SOURCE REFORM — cup attack/
  defense = the team's DOMESTIC league-season fit (same season,
  as-of-date), blended toward the cup-season fit by n/(n+K), K = 5
  frozen a priori; no synced domestic league = ruling B, market-only.
  (3) elo_goal_coeff STAYS 0.0008 — if the re-exam still fails MAE with
  real strengths, the weight is fix-v2, its own candidate. Re-exam bar
  UNCHANGED (8.0pp / 13 rows / 80% sign / INVALID > 2). BUILT:
  src/models/cup_strengths.py (as-of fits, strictly before kickoff;
  blend = estimate_strengths' existing n/(n+5) shrinkage with the
  domestic fit as TARGET instead of 1.0 — one shrink, no double count;
  cup n = 0 -> pure domestic); poisson.estimate_strengths gains an
  optional prior (None = byte-identical for every existing caller);
  training.py cup branch only (league competitions never enter it).
  EXECUTOR CALLS (ARCHITECT-RULE in the PR): reform applies to cup
  competitions in BOTH modes (one code path = the exam tests what the
  unlock ships; cups stay locked); ruling B triggers on unrated (no
  Elo) OR no domestic league-season, and in the exam is its own
  MARKET-ONLY category outside the INVALID budget (policy, not drift);
  domestic league = the LEAGUE competition with most fixtures this
  season (any status); synced league with 0 games as-of -> neutral 1.0
  prior (not ruling B); no prior-season domestic fallback; prior-season
  CUP backfill dropped for cups; remaining exam look-ahead = v22 Elo
  state + current injuries table (fits are now as-of, Elo is not).
  NEXT: after merge Anthony runs `python cli.py cup-exam --detail`;
  the architect rules.

- **NHL CANDIDATE v2 BUILT 2026-09-25 (architect scope; tuning grid
  FROZEN before any run):** `python cli.py nhl-backtest --candidate v2`
  (v1 stays the default = reproduces the ratified FAIL). Scope exactly
  as ruled: retuned params + ONE feature, rest days. REST: hours between
  each team's consecutive game STARTS over every loaded NHL game
  (preseason INCLUDED — fatigue is physical; ARCHITECT-RULE), hours not
  UTC dates (7pm ET then 7pm PT next day = 27h = back-to-back though two
  UTC dates apart). Adjustment (additive Elo, inside the expected score
  for predict AND update so ratings don't absorb fatigue): < 36h =
  -b2b_penalty; else +rest_per_day per extra day beyond one day off
  (half-up days, cap +2); no previous game / >= 5 days = +2 days.
  FROZEN GRID (720 points, simplest-first so exact ties pick the simpler
  setting): k {4,6,8,10} · mov_base {1.0,2.2,4.0} · home_advantage
  {15,25,35,45,55} · b2b_penalty {0,15,30,45} · rest_per_day {0,5,10}.
  season_regression NOT tunable on 2024-internal loss (2024 is the first
  season in the DB — no transition inside it) -> stays 0.25
  (ARCHITECT-RULE). Tuner receives the train games only (test proves
  2025 data cannot move the chosen params); 2025 scored ONCE through
  the unchanged gate. Output carries the top-5 grid rows, v1's params on
  the same 2024 loss for reference, the chosen params and all three
  criteria. LEDGER: v2's row lands here when Anthony's run is ruled.

- **NHL CANDIDATE PROTOCOL + v1 REJECTION (architect, 2026-09-25):**
  REJECTION LEDGER — nhl_elo_v1 (k 6, mov_base 2.2, regression 0.25,
  home_adv from 2024 rate): FAIL on the real DB — test log-loss 0.6909
  vs need <= 0.6866; calibration ALL PASS incl. the 50-60 band at
  exactly -5.0pp (decided by the inclusive-boundary fix); ratings sane;
  boundary receipts clean, opener rulings closed as verified. THE BAR
  DOES NOT MOVE. PROTOCOL (effective now): (1) parameter tuning on
  2024-internal sequential loss ONLY; 2025 evaluated ONCE per candidate;
  every candidate's params + all three criteria land in the command
  output and a rejection-ledger entry here (the MLB pattern). (2) v2
  scope, nothing else: retuned K / mov_base / home_adv / regression +
  ONE feature, rest days from the schedule already in the DB (zero new
  data), simple additive Elo adjustment with back-to-back emphasis.
  (3) The OT/SO status-storage PR stays queued as an H-track data item,
  not part of v2.
- **CUP PRICING HYPOTHESIS CHECK 2026-09-25 (architect item A; receipts,
  NO fix):** --detail FAIL stands, cups stay locked. CODE RECEIPTS:
  (1) WHERE CUP STRENGTHS COME FROM — training.py
  `_generate_predictions_soccer`: attack/defense are fit on FINISHED
  matches of THIS competition + THIS season only; backfill (up to 500
  matches of the SAME competition's prior seasons) fires only when the
  pool < MIN_MATCHES_FOR_STRENGTHS=30 — league form never enters.
  poisson.estimate_strengths = raw goals-for/against averages shrunk by
  n/(n+5): a cup team with n=1-2 is 17-29% its own tiny cup record.
  HYPOTHESIS CONFIRMED BY CODE. (2) EXAM ARTIFACT — in report-only mode
  the priced fixture sits INSIDE its own fit window (plus any later
  rounds): with n=1 a team's only data point IS the result being
  scored. Production pre-kickoff pricing never has that row, so part of
  the in-pot incoherence is exam look-ahead, not live behavior — the
  new `self` column counts it. (3) UNDER-DISPERSION MECHANISM —
  v22 elo_goal_coeff = 0.0008 (resolved 2026-08-15 on PL LEAGUE games,
  where strengths do the separating). With neutral strengths (what n<=2
  shrinks to), predict_match at 0.0008 prices a 351-pt effective Elo gap
  (Ipswich 1534 v Leicester 1183) at H 51.2% vs the gap's own 88.3%
  win-expectancy; 500 pts -> 55.4%. At the 0.0023 default: 69.2% /
  79.2%. Elo is nearly muted exactly where strengths are empty. DB
  RECEIPTS PENDING: `cup-exam --detail` now prints per row each side's
  fit n / attack / defense / promoted-prior flag, self-in-fit, pool size
  + backfill, and a summary (per-team n buckets, self-in-fit count,
  coeff). Anthony re-runs it; the Watford / Ipswich / Fleetwood rows'
  fitted values come from that output.

- **ARCHITECT RULING B — OUT-OF-POT POLICY (architect, 2026-09-25, for
  the eventual cup fix PR):** the model never prices an unrated team;
  such cup fixtures export market-only rows permanently
  (conservative-unknowns doctrine).

- **NHL ELO v1 BUILT 2026-09-25 (after the gate; parameters FIXED A
  PRIORI, before any real-data run, never tuned on 2025):**
  src/models/nhl_elo.py — MOV + per-team season regression, nothing
  else. k 6.0 (NFL's 20 scaled for 82-game seasons), mov_base 2.2 (NFL
  form ln(|m|+1)·base/(base+gap·0.001); OT/SO wins = 1-goal margins,
  no special weighting), regression 0.25 toward 1500 at a club's OWN
  first game of a new season (NFL clone), home advantage DERIVED from
  the 2024 train home rate (400·log10(p/(1-p))) — no memory constant.
  Writes nothing; no ModelVersion row. EXECUTOR FINDING: the hockey
  adapter's docstring claims the FT/AOT/AP distinction is kept "via
  Match.stage capture", but stage stores the provider's game.stage,
  not status.short — the DB cannot tell a regulation win from an
  OT/SO win. Harmless for v1 (all decided); the R-track OT/SO
  hypothesis needs a raw-status capture first. NEXT: Anthony runs
  `python cli.py nhl-backtest` on the real DB (the output carries its
  own preseason-boundary receipt), the architect rules.

- **NHL PHASE 2 GATE FROZEN 2026-09-25 (architect; written BEFORE any
  model exists):** harness = NFL shape (src/walters/nhl_backtest.py,
  `python cli.py nhl-backtest`; writes nothing). Stream: NHL
  competition only, FINISHED + scored; FT/AOT/AP all decided games;
  outcome = binary home win INCLUSIVE of OT/SO (moneyline); OT/SO
  weighting = R-track, NOT v1. Preseason EXCLUDED by stage marker
  ("pre") OR date before the season's opener. Train 2024 (warm-up,
  update only), test 2025 (predict-then-update). Baselines printed on
  the test season: constant 0.5 and league home rate (realized in
  2024, frozen before scoring). FROZEN ACCEPTANCE: (1) candidate test
  log-loss beats the home-rate baseline by >= 0.010 (inclusive; a tie
  is a rejection); (2) every 10pp probability band with n >= 100
  calibrates within ±5pp; (3) final ratings all within 1200-1800 —
  any outlier FAILS unless the architect names a reason. Then Elo v1:
  MOV + per-team season regression from birth, nothing else. Anthony
  runs the gate on the real DB; the architect rules before promotion.
- **CUP EXAM VERDICT: FAIL (architect, 2026-09-25) + DIAGNOSTIC PR:**
  real-DB run FAILED all three axes — mean |Δ_H| 13.86pp, sign 60%;
  CUPS STAY LOCKED. Architect's reading: NOT inversion. (1) every
  mega-miss (>25pp) has an out-of-pot opponent (Sabah, Slovan
  Bratislava, Viking, Bodo/Glimt, Shakhtar) — suspect default Elo /
  unmapped-league bonus making minnows mid-table; (2) general cup-path
  under-dispersion — same-tier favorites compress toward 0.5
  (Newcastle-WBA -29, Spurs-Charlton -23.8, Liverpool-Atletico -16.2)
  while true coin-flips price within 2pp. DIAGNOSTIC (daily-class, NO
  pricing change): `cup-exam --detail` prints per row home/away
  effective Elo, home/away league, home/away bonus (`*` = default
  input), tier; summary splits mean |Δ_H| by in-pot vs out-of-pot and
  same-/cross-tier/unmapped, and names the teams priced at exactly the
  default league Elo. Report rows gained raw inputs (in_pot, league/cup
  Elo, default); plain `cup-exam` output byte-identical. EXECUTOR READ
  (code, not data — the detail run confirms): every LEAGUE-typed code
  the adapter syncs (17) HAS a bonus entry, so the mega-miss clubs'
  domestic leagues (NOR/SVK/AZE/UKR) are simply not synced -> no
  team_to_league -> DEFAULT_LEAGUE_BONUS -100 on top of the 1500
  starting rating = ~1400 effective. NEXT: Anthony runs
  `python cli.py cup-exam --detail`; the fix spec follows the read.

- **CUP ACCEPTANCE EXAM BUILT 2026-09-25 (gate-class PR; spec frozen by
  the architect BEFORE results, law 3):** `include_finished: bool = False`
  threaded to `_generate_predictions_soccer`; True = REPORT-ONLY (FINISHED
  priced alongside SCHEDULED, rows returned, never persisted — no
  Prediction delete/insert, session rolled back). New `cup-exam` command:
  exact `match_id` join to exports/cup_answer_key.csv (no name matching);
  UNMATCHED/UNPRICED rows print and are excluded, > 2 = exam INVALID
  (data drift — stop and report). Pricing = production v22 as-is (no
  parameter change, no retrain). Output per fixture: date, comp, stage,
  home, away, fair_H, model_H, delta_pp, flag; summary: n scored, mean
  |Δ_HOME|, mean |Δ| all-outcomes, count >8pp, worst row. FROZEN BAR:
  PASS = mean |Δ_HOME| <= 8.0pp AND <= 13 of 55 fixtures over 8pp AND
  sign check PASS — EFL round-2 subset (key `stage`; fallback Sept 16-17
  date cluster, selector printed) model favorite == market favorite in
  >= 80%; < 50% = systematic inversion = automatic FAIL regardless of
  MAE (the league-bonus defect detector). RATIFIED CALLS: favorite =
  home vs away only (draw never favorite; EVEN matches only EVEN); ">8pp"
  count uses |Δ_HOME|; UNPRICED counts toward the > 2 budget; the 13 cap
  stays absolute when n < 55; the command prints the model version for
  the v22 confirmation; round-2 stage vocabulary resolved by the first
  real run's printed values. ARCHITECT VERDICT SEMANTICS (verbatim,
  2026-09-25, on the look-ahead item): "accepted as-designed with AMENDED
  VERDICT SEMANTICS — the exam is necessary-not-sufficient; FAIL is
  damning, PASS certifies "no gross cup-path defect" only (not
  out-of-sample accuracy); the sign/inversion check is the decisive
  organ; on PASS, cups unlock at cup-doctrine stakes (market-anchored,
  conservative, divergence fields on every row), with honest forward
  validation accruing from live cup predictions starting CL MD2."
  (Look-ahead named: strengths window = the whole competition-season's
  finished matches, v22 Elo may carry these results, current
  injuries/lineups.) Receipts: 29 pytest (report-only leaves EVERY
  table's count unchanged; twin proves the default path still writes;
  report mode prices a scheduled match identically to production;
  mutant that persists in report mode fails both guards). tools/
  betting_desk.html + predictions_card.html DELETED (superseded,
  known-XSS copies); tools/cockpit.html is the only live surface. FLOW:
  Anthony runs `python cli.py cup-exam` on the real DB -> pastes to the
  architect -> verdict -> merge. Unlock wiring (EFL/CL/UEL predict +
  export) = a SECOND PR, existing only after a PASS.

- **ARCHITECT DISPOSITION — stale-entry audit 2026-09-25 (architect,
  verbatim; logged by the executor per the arrangement):** "ARCHITECT
  DISPOSITION of the executor's stale-entry audit (2026-09-25): the
  backlog is an append-only ledger — old entries are records, not
  tickets, and stay untouched. Confirmed resolved-in-place: WC scoping,
  CLV review, Kalshi aliases, kalshi-disagreement, M11, S10/S15/S17,
  sentinel gap, temperature-scaling listing, weekly-backup (superseded
  by daily law), league-coverage closure, competition-context framing
  (date lapsed), holdout expansion (moot post-backtest), S13 duplicate
  (second entry is the record). ID collision: the L142 'U2' is retired;
  U2 = export enrichment henceforth. Two genuinely open items adopted
  into the queue tail: NFL-export Kalshi field (folds into U2) and the
  totals-model Step-1 verdict (owed a written verdict at the next MLB
  deep-dive)."

- **SECURITY WARM-UP PR 2026-09-25 (Claude Code's first PR; rulings 1+2):**
  scan receipts — pip-audit 0 known CVEs; history (50 commits) clean of
  keys/.env/DBs; bandit 8 LOW only (3 false positives, 5 swallowed
  exceptions — left). Four web-layer fixes, none on a prediction path:
  (1) CSRF — require_localhost never stopped a hostile page in the
  operator's own browser (its requests come FROM 127.0.0.1); every
  unsafe method now needs Origin/Referer naming our host — covers
  /admin/jobs/*, /pin-team, AND /matches/{id}/refresh (the unguarded
  re-predict route, found during this read). (2) DNS rebinding —
  TrustedHostMiddleware, loopback names + non-wildcard WEB_HOST.
  (3) Zero third-party scripts — Tailwind Play CDN replaced by a
  pre-built stylesheet (v3.4.17 CLI, config in src/web/), htmx 1.9.10
  + Chart.js 4.4.0 vendored from npm (tarball integrity verified by
  npm). (4) Cockpit XSS — repo copy escapes file/model text into
  innerHTML (proven live on the old copy: tier payload executed, 4
  injected nodes; new copy: 0). The LIVE cockpit is chat-published ->
  republish is the architect's call. WORKFLOW AMENDED in CLAUDE.md:
  Claude Code = branch+PR for everything, Anthony merges. tests/ born
  (17 pytest, throwaway SQLite, data/ untouched) + CI runs them.

- **WORKING ARRANGEMENT v2 2026-09-25 (user): Claude Code joins as the
  EXECUTOR.** Division: this chat = architect + institutional memory
  (doctrine, gate verdicts, receipt reads, backlog stewardship, the
  Cockpit artifact, prescriptive specs); Claude Code = sole
  implementer on the repo (direct filesystem access retires the
  tarball round-trip and its entire failure class — the incident's
  vector is gone). CLAUDE.md shipped at repo root = the constitution
  Claude Code boots with: six laws, workflow (PR doctrine + CI),
  production state per sport, the committed queue WITH SPECS (cup exam
  first, exact bar), operational notes. Chat-side container copy goes
  read-only-for-analysis (pull-first if ever touched); tarballs retire
  except artifact updates. THIS is the last tarball of the old era.

- **NCAA MARKET DISCOVERY 2026-09-25 (pre-4PM receipts):** an
  INVERSION — Kalshi is the PRIMARY college market source: KXNCAAFGAME
  real first-guess (fourth family on the shared matcher), 480 markets,
  166 matched legs (~83 games two-sided), 67 ambiguous = the collision
  class at college scale, sentinel refusing honestly. Books: thin+LATE
  for college — 8/105 roster games priced (tonight's pair at 7 books
  incl. Temple-Army 4PM; Saturday marquees 1-2 books or unposted) ->
  college books post near kickoff; morning re-export catches the fill.
  Window receipt: 160 upcoming family games. Roster (105 rows) ships
  via the Cockpit's market-only path, gaps honest.

- **COCKPIT: MARKET-ONLY FILES RENDER 2026-09-25 (user finding — UNL
  invisible):** normalize() only read "predictions"; the gated family's
  exports carry "fixtures". Fixed: fixtures-shaped docs render on the
  Card as the BOOKS' FAIR bars with a market-only chip and a doctrine
  why-line; the Desk excludes them from policy entirely (no model = no
  calls). Covers UNL today, NCAA tonight, cups at unlock. The whole
  gated family is now visible where the person looks.

- **NCAA MARKET PLUMBING 2026-09-25 (Friday 4PM slate):** odds = ZERO
  new code — sync_odds_nfl windows on Sport.NFL, the family enum NCAA
  rows carry, so college games price alongside NFL (NOTE: the window
  now holds ~350 games -> a couple minutes of per-game calls at the
  paid RPM; empty-quick if the provider lacks college odds).
  export-fixtures is selection-generic (no draw requirement) -> NCAA
  roster works as-is. Built: sync-kalshi-ncaa (KXNCAAFGAME on the
  shared matcher, signature READ this time — the competition kwarg I
  first guessed does not exist; matcher name-matches within the sport
  window). Read-before-edit caught my own kwarg guess pre-ship.

- **NCAA CERTIFIED FIRST-AUDIT 2026-09-25: 9,245 games / 743 programs /
  3 seasons.** Null-score check TRUE ZERO immediately (nested score
  dicts — no falsy trap in this family); 50 skips IDENTICAL on retry =
  M12-class phantom listings (3% tail, logged, left); 132+6 SCHEDULED
  ghosts in completed seasons = the None-status class staying out by
  conservative design (correct, no fix). 2026 CURRENT: 533 finished =
  weeks 0-4, Saturday's slate trackable. Scale note: modern coverage
  sweeps ~743 programs / ~3,800 games/season — the biggest family in
  the DB. The NHL's three-audit education compressed into ONE clean
  pass here: the laws transfer.

- **NCAA WIRED 2026-09-25 (on Phase 0 receipts):** adapter gains a
  code->league map (NFL=1, NCAA=2 receipted), list_competitions returns
  both, per-call league resolution, normalized rows carry their own
  code; cli routes NCAA into the nfl family (int seasons). DOCTRINE:
  data + market-only; no model transfer. PHASE 1 CAVEATS: the
  provider's seasons array runs NEWEST-FIRST (probe fallback grabbed
  2022 — wiring unaffected, but the first backfill must verify how
  current NCAA coverage runs; if it lags the live season, NCAA is
  backfill-until-current, labeled); 260 teams = FBS+FCS mixed (kept,
  size class noted, ~1,500 games/season); 69 None-status games =
  handled by score-presence inference + conservative-unknown by
  design. Kalshi KXNCAAFGAME discovery at first sync.

- **NCAA TRACK OPENED 2026-09-25 (user): college football, the sixth
  competition family.** Enters by the now-standard door: Phase 0 probe
  BEFORE wiring (scripts/ncaa_phase0_probe.py — league id by famous-
  program receipt, season format + status/week vocabulary enumerated
  from data, games-scale measured since FBS vs FBS+FCS changes the
  size class). DOCTRINE SET: NCAA = DATA + MARKET-ONLY at entry;
  nfl_elo_v1 does NOT transfer (NFL-trained); college model = its own
  frozen gate later, with R-track notes pre-filed (huge spread,
  neutral sites, FCS mismatches, 40+pt ranked blowouts). Kalshi series
  discovery (KXNCAAFGAME guess) at wiring time via the console probe
  pattern. Wiring lands on the pasted receipts, not before.

- **POLICY v1.0 — KNOBS RETIRED 2026-09-25 (user ratified the rollout):**
  the sliders are gone; per-sport evidence-set configs in their place,
  each number provenance-annotated in the Cockpit's policy card:
  SOCCER floor 4pp / prob>=0.50 / >=10pp -> DC ladder + half-units
  (cohort 6/16, die-by-draw); NFL floor 4pp / quarantine>=15pp NEVER a
  straight play (wk1-2 mega-edges 1-5) / QB-flagged games half-units;
  MLB floor 4pp, road unrestricted (380-row watch-not-penalty), totals
  untouched; NHL pass-all pre-gate. Base 1u; parlays 0.25u <=3 legs.
  CHANGES ONLY via audit-backed version bump — the model-gate culture
  now governs the consumer layer. v0.4's reinforcement organ remains
  the committed next Cockpit session (its self-grading is what
  proposes v1.1).

- **COCKPIT FEEDBACK ROUND 1 FIXED 2026-09-25 (four user findings):**
  (1) bars + why-lines + Desk pick cells now name TEAMS, never
  HOME/AWAY; (2) game labels always "Away @ Home" (the length-based
  "home v away" flip removed — it caused the vs/@ inconsistency and
  reversed reading order); (3) Ask + per-game reads were calling
  sampleNS.sample(...) while the capability is CALLABLE —
  sampleNS(prompt,{onText}) per the working audit button; both now
  mirror it, errors stringify properly. The season's FIFTH
  guessed-interface, caught by screenshot. (4) On the record: the
  Desk's mechanical policy PASSED the Falcons game hours before the
  model's 70.7% lost it — layers doing their jobs. Prompts instruct
  team-name-only language.

- **COCKPIT GOES INTERACTIVE 2026-09-24 late (user asks 2 of 3
  shipped):** (1) PER-GAME CLAUDE READS — the audit flow now also
  requests a per-game verdict JSON (lean/pass/watch + key risk, 18
  words) and appends each game's read into its signals expander;
  (2) ASK THE COCKPIT — free-text box with full slate + parlay context
  under house doctrine: dynamic parlay rebuilds, cuts, sizing questions
  answered in place. (3) RESULTS INTAKE + SELF-GRADING deliberately
  HELD for the committed desk-v0.4 session — honest grading requires
  the call-persistence layer (artifact storage) so the desk grades what
  it actually called; rushing it tonight would fake the reinforcement
  organ. Cockpit remains ONE artifact at the same URL;
  tools/cockpit.html updated.

- **COCKPIT CONSOLIDATION 2026-09-24 night (user's architecture
  challenge accepted — "three things is too many"):** the desk absorbed
  the card as a TABBED SINGLE ARTIFACT at the desk's existing URL —
  Card tab (model story: bars, per-outcome edges, quarantine badges,
  QB/totals chips) + Desk tab (policy/parlays/audit), ONE intake
  feeding both, per-game "signals & reasoning" expander (derived why-
  line + the raw input_quality block, truncated). The standalone
  predictions-card artifact is SUPERSEDED (link harmless but dead-end);
  in-repo: tools/cockpit.html replaces both prior files. Surface count
  post-GPT: TWO, each with a distinct job — the cockpit (browser,
  file-fed, consumer story) and the DB web UI (operator console).
  GRANULARITY LIMIT NAMED: exports carry signals, not model internals;
  Elo-gap/factor "why" fields = U2 export enrichment, queued — the
  cockpit displays them the day the files do.

- **PREDICTIONS CARD SHIPPED 2026-09-24 evening (U1 bridge, user ask:
  "the desk doesn't tell half the information"):** second artifact —
  the desk's sibling, multi-file intake over the same exports,
  rendering the MODEL's story sport-aware: probability bars (3-way for
  soccer, 2-way else) with per-outcome market fair + edge, tier chips,
  QUARANTINE badges + divergence, totals 50-60-band flag, QB flags,
  books/kalshi presence with gaps highlighted red, LIVE-vs-internal
  badge from the rehearsal flag, kickoff-sorted. Works for NHL exports
  the day they exist (generic 2-way path). Versioned in-repo
  (tools/predictions_card.html). POST-GPT COCKPIT = desk (policy) +
  card (model). The in-app server-rendered U1 (unified page +
  doubleheader badges) REMAINS the committed fresh session — this is
  the bridge that makes tonight's live file visible.

- **SDLC RIGOR DROP 2026-09-24 (user ask): community standards + CI +
  PR doctrine.** Files shipped: CONTRIBUTING.md = the project's laws
  codified (read-before-edit, receipts, gates, conservative unknowns,
  packaging/backup laws, track-by-artifact); CODE_OF_CONDUCT (argue
  from receipts); SECURITY (no secrets in repo, private advisories);
  MIT LICENSE (Anthony Evans 2026 — swap if another license preferred);
  issue templates (bug-with-receipts + finding/incident mirroring our
  root-cause format); PR template with the receipts checklist; CI
  workflow (compileall + dep install + IMPORT SMOKE — the mkt_block
  class of defect now caught server-side on every push). PR DOCTRINE
  SETTLED: direct-to-main for daily ops (cadence is a strength);
  BRANCH+PR for gate-class changes (model logic, training, acceptance,
  export contracts) with backtest receipts in the PR body; CI required
  everywhere. First CI run = the push of this very drop.

- **TWO CLOSING ITEMS 2026-09-24 midday:** (1) RESULTS.md NFL header
  retitled "(rehearsal)" -> "(live since Week 3, 2026-09-22)" BEFORE
  tomorrow's first live grading writes under it. (2) INTERNATIONAL
  SEASON-FORMAT DOCTRINE SETTLED: international competitions store
  whatever the soccer route produces; the STANDING RULE per competition
  is documented at wiring time (WC="2026", UNL="2026/27" — both noted
  in CLI.md's season-format table at next docs touch); no data churn,
  no normalizer surgery — per-team regression made the formats
  behaviorally equivalent, so the doctrine is documentation, not code.
  BUILD QUEUE HONESTLY FRESH-SESSION-SHAPED beyond this: cup exam
  surgery, NHL Phase 2 gate, desk v0.4, U1 cards, S14 Stage-2 — the
  stop here is the discipline, same as Wednesday's.

- **NHL FOUNDATION CERTIFIED (round 3) + KALSHI LIVE 2026-09-24:**
  2024 = 1502 FINISHED + 1 CANC (79 AP ghosts recovered), 2025 = 1498
  clean (all 128), nulls = TRUE ZERO. 4,410 complete-scored games,
  statuses fully mapped, FT/AOT/AP classes explicit. PHASE 2 UNFROZEN.
  Kalshi: KXNHLGAME real on first guess — 54 markets, 30 matched
  (Kalshi LISTS PRESEASON: the shakedown banks live two-sided snapshots
  on stakes-free games), ambiguous 0, sentinel on watch. Books skip
  preseason (expected; October prices). Phase 2 next: frozen gate
  first, then Elo v1 — the NFL sequence, on certified data.

- **NHL MARKET WIRING (phase 1c) 2026-09-24:** sync-kalshi-nhl added —
  the parameterized matcher's third sport (KXNHLGAME guess; the
  available-sports console line is the discovery probe, NFL pattern;
  the shared-path sentinel covers it from birth). Odds need ZERO new
  code (adapter routes). First run today = preseason shakedown getting
  market legs. Launch-morning cosmetic fixed: export success string
  now says LIVE format. NOTE: sync-odds --competition NHL uses season
  2026 (int-family).

- **UNL SEASON-STRING FINDING 2026-09-24:** the soccer route normalized
  the international single-year label to "2026/27" at sync time — the
  odds filter on "2026" found zero (defect named by one row
  inspection). UNBLOCK: UNL commands use "2026/27" (the stored truth).
  INCONSISTENCY LOGGED: WC stores "2026" while UNL stores "2026/27" —
  international comps' season-format policy needs one line of doctrine
  at the next quiet slot (harmless to training post-v22 either way).
  Nations roster: 54 entrants (16 WC-overlap updates), 156 fixtures,
  famous-nation receipt passed on sight.

- **UNL WIRED 2026-09-24 (user: Nations League kicks off today):**
  id 5, CUP-typed, MARKET-ONLY per cup doctrine (national teams, no
  club history -> no predictions); single-year "2026" season string =
  the WC format, harmless post-v22 (noted at the map). Famous-nation
  receipt check on first sync (France/Spain/Germany or stop). Enters
  the training pot as its own team-id island — soccer-refresh gates
  adjudicate at the next weekly transition, not today.

- **LAUNCH-MORNING CRASH + FIX 2026-09-24: the live export died on
  NameError mkt_block — Claude's ratification edit used a regex-assumed
  variable name; the real scope name is `market` (None-initialized,
  read this time). The season's FOURTH guessed-name incident, this one
  on launch morning — the read-before-edit law now explicitly covers
  regex-matched anchors: a regex hit is a HYPOTHESIS, not a read.
  Predictions were unaffected (17 in DB); only the file build crashed;
  fixed with scope-ordering verification. NHL certification round 3
  still pending (tail not yet run). MLB same morning: 10/16, ZERO
  nulls (Wednesday's 7 gaps all healed overnight), M16 2/7 (band
  cooling continues), v142 rejected. RESULTS.md "(rehearsal)" header
  = cosmetic, retitles at next tally after a live export exists.

- **USER ENHANCEMENTS FILED 2026-09-23 night (three, with design):**
  (1) U1-DH — MLB daily card must disambiguate DOUBLEHEADERS: today two
  same-matchup rows render indistinguishable; card gets "Gm 1 (1:05)" /
  "Gm 2 (7:05)" badges (ordinal by start time within matchup+date;
  carry provider game-number into the export if available). Joins the
  U1 card session. (2) DESK KNOBS RETIRED AT ROLLOUT — the sliders were
  shadow-tuning scaffolding only; replace with VERSIONED POLICY CONFIGS
  (policy v1.0 frozen from divergence evidence + audits; thereafter
  changes ONLY via the B-track gate: audit-driven proposal -> backtest
  on graded history -> version bump with receipts — the model-gate
  culture applied to the consumer layer). UI shows active policy
  version + provenance, not sliders. (3) DESK THREE-PART CLOSED LOOP —
  the current gap is retrospection: add part three, REINFORCEMENT:
  desk persists its own daily calls (artifact storage), intakes the
  next day's RESULTS files, self-grades in units BY RULE (floor plays
  vs ladders vs haircuts vs parlays vs passes-that-won), and emits TWO
  feedback streams: (a) desk-layer — which rules earn/lose -> evidenced
  policy-version proposals; (b) predictions-layer — systematic model
  biases seen through the betting lens (extends SIGNALS FEEDBACK from
  prospective to retrospective). This IS B2's graded-policy harness,
  living in the desk. Sequencing: desk v0.4 (results intake +
  persistence + self-grading) in a post-NFL-launch session; knob
  removal ships WITH evidence-set policy v1.0 once shadow days
  accumulate.

- **GHOSTS NAMED + FINAL FIX 2026-09-23 night: AP (after
  penalty-shootout), 79+128 = 207 real scored games held SCHEDULED by
  the conservative-unknown rule doing its job. Root: ASO was a
  memory-guessed status code; the vocabulary Counter names the real
  one. LESSON FILED: enumerate provider vocabularies from data before
  writing maps — the season's third guess-caught-by-receipt. AP mapped;
  final re-sync + audit = certification round 3: expect 2024 =
  1502 FINISHED + 1 CANC, 2025 = 1498 FINISHED, nulls 0. Shootout
  games (AP) carry regulation+SO final scores — Phase 2's OT/SO
  handling question now has its data classes explicit (FT/AOT/AP).

- **NHL DEFECT SOLVED: THE FALSY-ZERO TRAP (2026-09-23 night).** The
  probe's contradiction cracked it — feed clean (1,502/1,503 parse) yet
  DB holds 302 nulls: the adapter's `or {}` turned a shutout side's
  bare-int 0 into {} -> parsed None. 302/2,793 finished = 10.8% ~ the
  NHL shutout rate exactly. Same root cause explains the scattered
  SCHEDULED ghosts (0-score + absent status -> inference blocked). Also
  owned: the probe's parse-mirror omitted the `or {}` — it validated
  the FEED, not the parser; the ok-shapes + zero-fails contradiction
  still named the bug. FIXED (bare gets; shutout-zero test passes).
  HEAL: re-sync 3 seasons (updates in place), re-run the UPPERCASE
  audit — expect nulls=0 for real and the ghosts collapsing to
  FINISHED. Certification round 2 pending those receipts. Phase 2
  still holds until green.

- **NHL CERTIFICATION FAILED — DEFECT CAUGHT BY USER'S SANITY INSTINCT
  2026-09-23 late:** the corrected null-score check returns 302 FINISHED
  games with missing scores (Claude's first check used lowercase status
  values -> vacuous 0 declared "perfect" — owned; the user's push for
  receipts forced the re-issue that found the truth). Ghost hypothesis
  dead: completed-season SCHEDULED rows scatter Oct-Apr, not preseason
  clusters. ONE suspected cause: hockey score-block shape variant the
  cloned parser misreads (parse-null + status-present = the 302;
  parse-null + status-absent = the scattered SCHEDULED). PHASE 2 HOLDS
  until green. scripts/nhl_score_probe.py shipped: prints raw
  status/scores JSON side-by-side for parsing vs failing games — the
  shape names itself, then the adapter patch + re-sync heals in place
  (updates path). NFL launch untouched (isolated paths, by design).

- **NHL BACKFILL COMPLETE 2026-09-23 evening: 4,410 games / 3 seasons /
  32 franchises, ZERO skips.** Counts fingerprint correctly (1,409
  in-progress incl. ~97 preseason; 1,498 + 1,503 completed = regular +
  playoffs). One bootstrap miss owned (sync-competitions absent from
  the first block — the warning run doubled as an adapter dress
  rehearsal: perfect fetches, correct skip behavior). Sync speed:
  ~1s/season — the morning's prefetch cache's first new-sport
  beneficiary. H-track state: Phase 1 data layer DONE; next sitting =
  odds wiring + Kalshi KXNHLGAME discovery + injuries; then Phase 2
  gate-frozen-before-model.

- **NHL PHASE 1 (DATA LAYER) SHIPPED 2026-09-23 evening — live-eve-safe
  by design (isolated new files, zero shared paths with tomorrow's NFL
  launch):** src/adapters/api_hockey.py cloned from the proven
  american-football shape (id 57 hard-coded from the certified receipt;
  key family API_HOCKEY_KEY -> AMERICAN_FOOTBALL -> FOOTBALL; hockey
  status map with FT/AOT/ASO -> FINISHED per probe vocabulary, unknowns
  stay SCHEDULED; score-presence-beats-status-absence inference
  inherited; preseason captured NOT filtered — exclusion at train time
  per the NFL law). Wired: registry (source + nhl/hockey defaults), cli
  sport router (NHL -> nhl), --seasons int branch (nhl joins
  baseball/nfl). Verified end-to-end in-container: get_adapter('nhl')
  dispatches, enum + statuses assert. NEXT: user runs the Phase-1
  backfill (teams x3 + matches --seasons 3, ~4k games incl. ~97
  preseason); odds/Kalshi-discovery/injuries = the following block.

- **NHL PHASE 0 COMPLETE — GO FOR PHASE 1 (2026-09-23 receipts):**
  plan covers hockey; ID 57 CERTIFIED by famous-club receipt (Bruins/
  Canadiens/Rangers/Maple Leafs; 32 teams); 4 Nations Face-Off at id
  271 noted for EXCLUSION (EFL-Trophy instinct). SEASON FORMAT:
  single-year int (2026 = the 26-27 season) — joins the MLB/NFL int
  family in the --seasons helper; harmless to training (own pot +
  per-team regression). GAMES: 1,409 listed, arithmetic fingerprints
  check (1,312 regular + ~97 preseason); status vocabulary already
  shows FT and AOT — the OT/SO handling question has concrete field
  values pre-build; preseason tagging via stage/status = a Phase 1
  capture requirement. Phase 1 (next major session): adapter clone,
  registry, 3-season int backfill (~4k games), odds/injuries, Kalshi
  KXNHLGAME discovery, preseason-excluded-but-shakedown.

- **NHL PHASE 0 PROBE SHIPPED 2026-09-23 (afternoon):**
  scripts/nhl_phase0_probe.py — read-only recon answering Phase 1's
  three dependencies with receipts: plan coverage of the hockey
  product (key family: API_HOCKEY_KEY -> AMERICAN_FOOTBALL -> FOOTBALL,
  mirroring the adapter pattern), the NHL league id verified by
  famous-club check (Maple Leafs/Bruins or STOP — never memory), and
  the season-string format from the API's own seasons list (the WC
  law). Zero wiring; the pasted output is the Phase 1 go/no-go.

- **ANSWER KEY BANKED 2026-09-23: 55 fixtures (EFL 36, CL 19, UEL 0).**
  Richer than the ~34 estimate: EFL spans BOTH rounds — the round-2
  inversion ties probe the league-bonus defect directly; CL 19 = the
  full cross-league set with the extreme mismatches. UEL 0 = the
  incident's concrete cost: those nine games' pre-kickoff books died
  with the DB and are unrecoverable by nature; future matchdays add
  pages. exports/cup_answer_key.csv reproducible via the extractor.
  Next session: report-only pricing mode + the +/-8pp scoring.

- **CUP EXAM: SAFE HALF SHIPPED, SURGICAL HALF SCOPED 2026-09-23.**
  Reading the predict path settled the design: the pricing core lives in
  _generate_predictions_soccer (scheduled-only, stateful) — the exam
  needs an include_finished REPORT-ONLY mode (never writing Prediction
  rows for played games, which would pollute the graded ledger). That
  surgery is model-adjacent and stays the committed lead of the NEXT
  fresh session, per doctrine (no rushed model-adjacent code on
  live-launch eve). SHIPPED NOW: scripts/extract_cup_key.py — read-only
  answer-key extractor (finished EFL/CL/UEL fixtures with pre-kickoff
  books; latest-per-book-per-selection, median, overround-stripped fair
  1X2, result, book count) -> exports/cup_answer_key.csv. User runs it
  today; next session is pure scoring against the +/-8pp frozen bar.

- **PERF ROOT CAUSE (structural) + FIX 2026-09-23:** the 10-minute MLB
  sync was O(n^2) — _find_match_by_source full-scans the table's JSON
  external_ids PER ROW ("fine for now" written at ~11k matches; the
  expansion doubled the table and the quadratic expired): 2,512 lookups
  x ~21k-row scans every morning. FIX: per-sync prefetch cache — one
  competition-scoped scan builds a source_id map, lookups O(1);
  creations join the cache; non-cached callers keep the old path.
  Expected: the write phase drops to seconds AT ANY table size (NHL's
  4k matches pre-absorbed). SEPARATE same-day items: (a) today's
  extra slowness = environment (user diagnostics issued: wal size,
  TRUNCATE checkpoint, lsof for a holding process); (b) CHAIN CHANGE —
  morning grading uses a 2-day sync window (~30 rows), full-season
  weekly only. Container note: even my greps timed out this session —
  the 300s hang was container-side, unrelated to his machine.

- **H-TRACK OPENED 2026-09-23 (user): NHL — the fifth sport.** Preseason
  underway; regular season ~early Oct = the same runway the NFL turned
  into a 17-day launch. THE NFL PLAYBOOK APPLIES WHOLESALE: Phase 0
  probes first (league-id famous-club check — Leafs/Bruins or stop;
  season-string semantics verified BEFORE any sync, WC-lesson
  mandatory); Phase 1 data (adapter cloned from american-football shape,
  3-season backfill ~4k games, odds/injuries, Kalshi KXNHLGAME
  discovery; PRESEASON EXCLUDED from training/backtest but USED as
  live-fire pipeline shakedown); Phase 2 gate-frozen-before-model, then
  Elo v1 (MOV + per-team regression from birth; hockey R-track
  hypotheses held for evidence: OT/SO handling, back-to-back rest — the
  strongest rest signal in sports, goalie-as-QB in the injury surface);
  Phase 3 the proven arc (backtest ~Oct 1, internal week 1,
  rehearsal+dry-read week 2, live decision on the Monday table) with
  the quarantine-field contract available day one. SEQUENCING: cup
  acceptance exam still leads the next session; NHL Phase 0+1 = the
  major block behind it.

- **NFL LIVE — RATIFIED 2026-09-22 (Anthony: "we should move forward").**
  The rehearsal era closes after its designed arc: gate-passed backtest
  (0.6361 vs 0.6811), two graded weeks (19/33; calibrated middle
  on-model; mega-edges 1-5), consumer dry read, asks tested-and-declined
  with receipts, quarantine rule earned by detonation (ATL 34-3).
  STRUCTURAL CHANGES: rehearsal flag -> false with live_since stamp;
  every priced row now carries market_divergence_pp and quarantine=true
  when |divergence| >= 15pp — the contract rule as a FIELD, not prose.
  First live export: Thursday's Week-3 pre-opener chain. Fourth sport
  reaches production 17 days after its first line of code.

- **REBUILD COMPLETE + v22 RE-PROMOTED 2026-09-21 (the mountain,
  climbed twice):** restore from 09-17 backup (integrity ok, 16,133
  matches) -> Phase 2 backfills IDENTICAL to Friday's fingerprints
  (all created, zero skips) -> Phase 3 banked everything since Thursday
  (UEL league phase recreated; NFL block regenerated: 5,822 anchors,
  17/17 weather, MNF prediction rewritten) -> Phase 4: spread guard
  101%, Southampton drift replay (235 this time — feeders shift the fit
  too), documented override -> v22 PROMOTED on 16,546 matches / 376
  teams — the FULL 24-competition pot, i.e. the model the mountain
  finale always intended; the incident merged two transitions into one.
  Known permanent losses logged (Thu-Sun odds snapshots + in-DB
  prediction/outcome rows for those days; graded record survives in
  exports/git). Daily-backup era begins tomorrow; packaging law in
  force. The system's worst day and its most disciplined recovery,
  same morning.

- **DATABASE DESTRUCTION INCIDENT 2026-09-21 — Claude's fault, full
  stop.** Mechanism: the morning pragma-verification connected the app
  engine IN THE CONTAINER -> SQLite created an empty 4KB data/sports.db
  there -> the tarball packaged it -> extraction OVERWROTE the 83MB
  production DB at 08:58; the old -wal/-shm against the new empty file
  produced "database disk image is malformed." The --exclude='.git'
  discipline existed; a data/ exclusion did not. PERMANENT FIXES:
  container data/ purged; .gitignore hardened (data/* except
  preferences.json); PACKAGING LAW — every tar now excludes BOTH .git
  and data, and the tarball listing is verified data-free before
  presenting. BACKUP LAW UPGRADED: daily .backup in the morning chain +
  mandatory .backup immediately before any soccer-refresh (weekly
  cadence just proved insufficient). RECOVERY: restore Thursday
  2026-09-17 .backup (consistent by API); PERMANENTLY LOST: Thu-Sun
  odds snapshots (Week-2 NFL closers, MW5 closers) — the graded record
  SURVIVES in exported JSONs, RESULTS.md, and git history. REBUILD
  (all steps documented in history): expansions re-backfill, refresh
  re-adjudicates (v22-equivalent re-earned through the same gates),
  current-day syncs re-run.

- **DESK v0.3 SHIPPED 2026-09-21 (user asks: parlays, multi-sport,
  deeper audit):** (1) MULTI-FILE INTAKE — select all of a day's export
  JSONs at once; rows pool with per-row sport tags; policy stays
  sport-aware. (2) PARLAY BUILDER — 2-3 leg tickets from live (non-PASS)
  rows only; shared-team legs screened; cross-sport combos ranked first
  then combined edge (Π model − Π market); positive-edge tickets only;
  top 3 rendered at 0.25u each (parlays are lottery-shaped — doctrine
  sizing). (3) AUDIT v3 — game-by-game notes, PARLAY CRITIQUE (grade/
  kill tickets, catch correlations the screen missed), and SIGNALS
  FEEDBACK addressed to the prediction layer (per-row input-quality
  digest — books/kalshi/injuries/QB flags — feeds the prompt).
  Republished same URL; in-repo copy updated. MLB block 3 same morning:
  11/15 Sunday, v143 = 34th rejection, away picks 5/7 (pattern-watch
  answered same-day AGAIN: watch, not quarantine).

- **MORNING-LAG ROOT CAUSE + FIX 2026-09-21:** db-tune's WAL persisted
  in the file but synchronous=NORMAL is PER-CONNECTION — app connections
  since ran WAL+FULL (fsync per commit; the 2,511-row MLB update loop =
  the minute-plus lag, WORSE than pre-tune). Fixed at the engine level:
  connect-event pragmas (WAL + NORMAL + busy_timeout=5000) on every
  SQLite connection. First patch attempt spliced create_engine via a
  guessed anchor — caught by syntax check, reverted via git, re-applied
  against read code (the container repo's .git earning its keep).
  RECEIPT: tomorrow's sync-matches(MLB) write phase should drop well
  under the old baseline, not just under today's.

- **WEEK 2 GRADED + LIVE-WEEK-3 TABLE 2026-09-21 (mountain block 2):**
  Sunday 8/14 (Week 2 ~9/15 pre-MNF; rolling 17/29, LL 0.6831 vs
  backtest 0.6361 — elevation entirely from mega-miss rows; middle
  bands on-model). THE QUARANTINE DETONATION: Atlanta +23.7 lost 34-3
  (66.4% on a 31-point loser) — incumbent benched it on live QB news =
  freshness confirmation #4, the most emphatic. Houston +14.0 lost
  20-6; Seattle +15.4 won; double-digit disagreements now 1-5 over two
  weeks. Market-agreeing rows carried the day again. RECOMMENDATION
  DELIVERED: GO LIVE Week 3 — model as-is (calibrated middle earned
  it), rehearsal flag drops, market-disagreement quarantine formalized
  as consumer-side contract rule (>=15pp = watch-flagged). Anthony to
  ratify. Two weeks, zero pipeline defects.

- **MW5 GRADED 2026-09-21 (mountain block 1): 3/9 — v22's debut week,
  the season's harshest.** HULL LOST OUTRIGHT 2-1 at Newcastle (+24.1pp
  all-time-record edge; X2 also lost; unbeaten run ended). Leeds 0-0
  (+16.3, the shadow-argued row) — INCUMBENT'S freshness quarantine
  VALIDATED BY RESULT vs the desk's 0.5u loss = third freshness
  confirmation, first with money-shaped grading. Spurs-Villa draw pick
  (+13.9) lost 2-3; Forest (+6.0) lost home to Coventry. Hits = the
  market-agreeing/cold rows (Everton, City, Liverpool). COHORT: 6/16
  (37.5%), failure mode DIVERSIFIED (outright losses join die-by-draw);
  negative-edge rows 3/4. Season 25/49. NO model action — the n=30
  pre-committed read stands; but this is the strongest single-week
  evidence yet for market-first discipline on double-digit
  disagreements.

- **SHADOW DAY 1 COMPLETE (3 sports) + AWAY-EDGE QUESTION ANSWERED
  2026-09-20:** the desk's MLB audit asked whether MLB away edges 4-7pp
  share the soccer die-by-draw pattern — answered same-day from 380
  graded rows: in-band away 5/9 vs home 5/8 (n-tiny); ALL away picks
  77/137 (56%) vs home 147/243 (60%) — away runs ~4pp cooler (PATTERN-
  WATCH granted, continues with M15) but 56% winners is nothing like
  the soccer cohort's failure; different animal CONFIRMED empirically.
  Shadow day 1 final: three sports, three audits, two policy defects
  found+fixed (v0.2), input-freshness confirmed twice as the incumbent's
  structural edge, one calibration question asked and answered from
  data in hand. The ritual works.

- **SHADOW DAY 1, NFL EDITION + DESK v0.2 2026-09-20:** the desk's own
  audit arm caught TWO REAL DEFECTS in policy v0.1 on its first 2-way
  slate: (1) the ladder rule is a soccer artifact — double-chance has no
  instrument without a draw leg; (2) sizing incoherence — ladder(>=10pp)
  kept full units while haircut(>=15pp) halved, so 12.9pp out-sized
  22.6pp. FIXED in v0.2 (republished, same URL, now versioned in-repo at
  tools/betting_desk.html): sport-aware ladder (2-way boards route to
  reduced-size straight, labeled honestly), monotone sizing (>= ladder
  threshold = half units), near-floor tempering (edge within 1pp of
  floor = half units, per the audit's Titans pushback), correlation
  note in the summary (same team on multiple live rows flagged as one
  exposure line). DIVERGENCE VS INCUMBENT: they filtered to Week-2 rows
  themselves (good consumer behavior), landed near-identical passes on
  the market-agreeing rows, and QUARANTINED Atlanta (+23.7) on live QB
  news (Rush starting, Penix out) — input-freshness verification AGAIN
  the structural differentiator, second slate running. B1 requirement
  list unchanged and reconfirmed.

- **FIRST DIVERGENCE REPORT 2026-09-20 (shadow ritual, day one):**
  CONVERGED on slate shape (Leeds lone candidate, 3 passes on price) —
  the codified doctrine transferred; the desk's own audit even
  recovered incumbent conservatism (suggested DC-ladder-as-smaller).
  DIVERGED on three STRUCTURAL rules no knob expresses — now B1 code
  requirements: (1) INPUT-FRESHNESS VERIFICATION — incumbent caught the
  export's stale Palace absences (Sarr/Nketiah back Thursday; file
  still suppresses -25% xG) making the 16.3pp edge partly phantom;
  (2) CONSENSUS-QUALITY GATE — all Leeds prices attributed to ONE book;
  min-distinct-books-per-selection before trusting fair; (3) TWO-STAGE
  CLEARANCE — selection quality vs entry-price quality graded
  separately. Net divergence: desk 0.5u vs incumbent 0u-pending.
  APP-SIDE ITEM from the same audit: "fresh timestamp != fresh inputs"
  — provider injury-feed lag survives clean syncs; queue a big-edge
  injury-recency flag in exports.

- **B1 SHADOW VEHICLE SHIPPED 2026-09-20 (Claude artifact "Betting
  Desk"):** browser-local policy engine over the daily exports — PLAY/
  LADDER/PASS with explicit reasons, edge vs book fair, double-chance
  routing (>=10pp away/draw), market-is-right half-unit haircut
  (>=15pp), tunable persisted knobs, optional Claude narrative audit via
  the artifact sample capability. Policy v0.1 = DRAFT codification of
  the GPT's audited rules; the SHADOW RITUAL = run both layers on the
  same export daily, tune knobs to close divergence, note rules knobs
  can't express (-> B1 code requirements). Constants graduate into
  src/betting/ when divergence stabilizes. Artifact lives outside the
  repo; policy source of truth moves in-repo at B1-code time.

- **B-TRACK OPENED 2026-09-20 (user, prompted by ChatGPT Custom-GPT
  retirement news): native betting layer.** Doctrine: the BOUNDARY was
  always the asset; the GPT was its tenant. Design commitments:
  policy-as-code (deterministic, versioned, gated like a model) in
  src/betting/ consuming the same export contracts; the months of GPT
  audits = the requirements doc (actionability gates, portfolio/ladder
  construction, entry-price discipline, CLV-jointly-with-results);
  LLM kept only as a replaceable API adapter for narrative audit.
  MIGRATION: B1 codify current rules + paper-trade SHADOW alongside the
  living GPT -> daily divergence report = acceptance test vs the
  incumbent; B2 policy backtest harness over the season's graded
  history (all data in hand); cutover only when shadow matches/beats.
  Non-goals for now: order execution, real bankroll. Sequencing: after
  the committed queue (cup acceptance exam, U1 cards) unless platform
  deadline forces reprioritization.

- **DB LAG INVESTIGATED 2026-09-20 (user-reported):** single-column FK
  indexes all EXIST — the story is (a) never-ANALYZEd planner, (b)
  default journal mode (lock stalls under concurrent sync/read), (c)
  STRUCTURAL: odds rows accumulate per match across capture days and
  evaluators read all history per match to compute closes — work grows
  linearly all season. SHIPPED: db-tune (WAL + synchronous=NORMAL +
  ANALYZE + three composite indexes + optional --vacuum + before/after
  probe timing). QUEUED for a proper session: snapshot pruning/rollup
  design (keep latest-per-book-per-day + close; archive the rest) —
  the real long-term fix for the accumulation curve. "Scale to
  Postgres" = not yet warranted; SQLite+WAL+stats handles this era.

- **NINE-CLUB ID CHECK COMPLETE 2026-09-20: all feeder ids CERTIFIED.**
  Eight verified first pass (Salzburg/Brugge/Sparta Praha/Sparta
  Rotterdam/Benfica/Celtic/Basel/Galatasaray in their right leagues);
  GRE "miss" was the c/k transliteration in the query pattern —
  Olympiakos Piraeus + PAOK + AEK + Panathinaikos confirm id 197.
  Expansion fully verified: 24 competitions, every id proven by club
  names, Monday's refresh trains on certified data.

- **THE 2:04 METRONOME 2026-09-20 (user-spotted):** every odds sync took
  exactly 2:04 = 20 games x 6.0s spacing = the FREE-TIER 10/min pace
  hardcoded, throttling a paid plan ~50x below allowance. Fixed:
  API_FOOTBALL_RPM env (default 10, conservative); .env.example
  documented; 429 backoff stays as the safety net. User sets their
  plan's rate -> the sweep's odds legs drop from ~12 min to seconds.

- **FEEDER BACKFILL COMPLETE 2026-09-19 (evening): ~7,988 matches, zero
  skips; nine league-format fingerprints verify shape (Belgian split
  306/321/315, Scottish post-split 234s, Austrian/Swiss championship
  rounds, Czech playoff groups). Registry created=9. MONDAY'S POT:
  ~20,600 matches / 24 competitions / 14 countries — one gated refresh.
  Remaining check issued: famous-club-per-league SQL (receipts print
  counts not names; a wrong id needs a name to falsify).

- **FEEDER-LEAGUE EXPANSION 2026-09-19 (evening, user-scoped): nine
  CL/UEL feeder leagues wired DATA-ONLY** — NED POR BEL SCO TUR AUT SUI
  GRE CZE (ids 88/94/144/179/203/218/207/197/345), meta + strength
  priors (-55 to -130, pending the acceptance exam's pricing check).
  Purpose: rating enrichment for European opponents we already price —
  NO prediction/export obligations, no shadow burden. All enters
  MONDAY'S SINGLE REFRESH (one transition absorbs everything; drift
  adjudication will be busier — the documented-override precedent
  stands). DEFERRED with reason: calendar-year leagues (NOR/SWE) use
  single-year season strings — v22's per-team regression is immune, but
  the --seasons helper would generate wrong strings; they wait for the
  format accommodation, not a workaround. VERIFICATION: sync-teams
  receipts (club names) instantly falsify any wrong league id.

- **EXPANSION BACKFILL COMPLETE 2026-09-19 (same afternoon):** 4,468
  matches, ZERO skips (per-season teams strategy perfect at scale);
  league-size fingerprints verify authenticity (380x3 for 20-team
  PD/SA; 306+308+308 for 18-team BL1/FL1 incl. relegation playoffs).
  ~70 new clubs; weekend fixtures priced in all four countries (17-20
  per window); ELC activated (11 odds, 138 injuries). DB now spans 15
  competitions / 5 countries; Monday's refresh pot ~12,600. Doctrine
  unchanged: refresh HELD to Monday's mountain as one gated transition;
  foreign leagues shadow next matchweek; ELC enables at the refresh.

- **COVERAGE EXPANSION DECIDED 2026-09-19 (user): PD, SA, BL1, FL1 + ELC
  activation.** Finding: ZERO code needed — adapter ids/meta and
  league_strength tiers (PD -10 / SA -20 / BL1 -25 / FL1 -50) pre-wired
  since the Europe era; registry auto-includes. Ops plan: per-season
  sync-teams x3 per league (promoted/relegated coverage — pyramid
  lesson) + --seasons 3 matches + forward odds; ELC = odds+injuries
  rhythm only (history already trained into v22). DOCTRINE: next
  soccer-refresh (HELD until Monday's mountain) pulls ~4.5k matches in
  as ONE gated transition — expect justified drift for CL/UEL clubs
  gaining domestic history; foreign leagues SHADOW one matchweek
  (exports verified vs books, unshipped) before going live; ELC can
  enable at the refresh. Kalshi per-league series discovery = later
  bonus. Strategic payoff: European opponents get domestically-informed
  ratings — exactly what cup acceptance and CL/UEL pricing lacked.

- **v22 PROMOTED 2026-09-19 — THE COMPRESSION SAGA CLOSES.** Culprit
  confessed: WC, 100 matches, season "2026", June 11-July 12 — its rows
  interleaving with "2026/27" qualifying produced the toggles; explains
  v18-healthy-v19-collapsed exactly (v18 predates the WC sync). Fixed
  train() passed the spread guard 320 vs 323 (99%). Drift rejection on
  v21 investigated and JUSTIFIED: Southampton +201 = fifty Championship
  matches entering the pot (50 ELC vs 38 PL) — evidence-based re-rating;
  --max-drift 350 override documented for the one-time pot-doubling
  transition; v22 promoted with all guards passing on merits. Production
  soccer: v22 on 8,137 matches, per-team regression, pyramid + Euro +
  WC history. REFRESH REOPENED after 3 parked weeks. CONSEQUENCES:
  (1) 2pm MW5 refresh ships v22's first live rows — hand-off flags the
  model change; the v18->v22 edge delta on identical fixtures (Hull
  +23.4 row above all — their ELC history just landed too) is the first
  direct measurement of the fix. (2) CUP ACCEPTANCE EXAM = next session
  build: v22 cup-path vs stored books on the ~34-fixture answer key,
  +/-8pp frozen bar; also adjudicates whether the league-bonus misapply
  was independent or a compression symptom.

- **COMPRESSION CONVICTED + FIX SHIPPED 2026-09-19 (probe verdict, same
  day).** The probe caught it directly: a block of soccer matches labeled
  season "2026" (single-year string) interleaves with "2026/27" fixtures
  at the stream tail — the global last_season toggle fired SIX regressions
  in ~120 matches (several ONE match apart), spread 333 -> 79 (0.75^6 ~
  0.18 = the v19/v20 collapse exactly). PYRAMID EXONERATED: pot A (no
  pyramid) collapses identically (185 vs 165) — the backfill was innocent;
  v18's 323 predates the "2026" block's arrival. Culprit-naming SQL
  issued (summer-2026 tournament with single-year labels — WC-shaped).
  FIX: per-team season regression in elo.train (regress_team + per-team
  last_season map; global apply_season_regression kept for back-compat) —
  the NFL model's semantics from birth, immune to interleaving by
  construction; smoke test proves uninvolved teams' spread survives
  toggles. NEXT: user runs soccer-refresh — v21 faces the SAME gates
  (spread guard should now pass ~300+; drift vs v18 adjudicates); a pass
  reopens the refresh AND puts the cup acceptance exam on the table.

- **COMPRESSION PROBE SHIPPED 2026-09-19 (the instrumentation session,
  delivered as a script):** scripts/compression_probe.py runs the EXACT
  train() loop twice — pot A excludes pyramid comps (ELC/EL1/EL2), pot B
  everything — dumping PL-team spread every 250 matches and marking every
  season-regression firing inline. The collapse point becomes visible
  directly: departure at a regression line = season-string interleaving;
  gradual departure after pyramid entry = cross-pot rating flow through
  cup ties; similar finals = mechanism elsewhere. Read-only, in-memory,
  ~90s run. Container reset mid-build was recovered via git clone from
  main in one command — the repo-as-state-recovery design working as
  intended. U1 (daily cards + unified page) FORMALLY COMMITTED as the
  next dedicated build session per user prioritization — multi-file UI
  work deserving a non-matchday session; leads the queue after the probe
  verdict. NFL-live reminder: Monday's table decides Week 3; every game
  already predicted internally.

- **[ACTIVE MEASUREMENT — started 2026-06-24, REVIEW ~2026-07-08] Closing-line-
  value: does the model actually beat the market?** This is THE question for
  the income thesis. The model is well-calibrated but has NO demonstrated edge
  over the market — the blend exists precisely because its disagreements were
  anti-predictive. Calibration ≠ profitability; a perfectly calibrated model
  still loses to vig with no edge over the close. CLV is the test that
  distinguishes "good thermometer" from "edge."
  RUNNING NOW: `capture-odds` fires 4×/day (8/12/4/8 local via launchd,
  scripts/setup_clv_capture.sh) writing de-vigged consensus snapshots to the
  OddsSnapshot table. Started banking data 2026-06-24 ~20:20Z.
  TO DO at review (~2 weeks out, when multi-capture data has accrued):
    1. `python cli.py clv-report --sport mlb --since 2026-06-24`
    2. Read the TOWARD/AWAY tally on the model's picks, focusing on the
       DISAGREEMENT games (where model ≠ market) — that subset is the whole
       question, and it's a fraction of each slate, so it needs the full ~2 wks.
    3. Sanity-check logs/capture_odds.log in the first day or two to confirm
       the 4 launchd jobs are actually firing (machine-awake dependency).
  DECISION GATE — be honest about all three outcomes:
    • TOWARD reliably > away → model is early to real info → there IS an edge,
      and the disagreement slice is the product worth building a pipeline/slate
      around. THEN (and only then) revisit slate consolidation + bet logging.
    • roughly even / AWAY → model is a calibrated thermometer that tracks the
      market → NOT an income engine → do NOT build slate/parlay tooling on a
      non-edge. Honest verdict, worth knowing.
  HARD CONSTRAINT carried forward: parlays are HIGHER variance / LOWER
  repeatability than the singles they're built from — never build frictionless
  parlay tooling without showing the combined EV + variance cost in the same
  view. Singles are where the calibration edge (if any) lives.
  KNOWN DATA GAP (low priority): Mets/Cubs doubleheaders show as "unmatched 2"
  every sync — the matcher can't disambiguate same-day same-teams games. Costs
  2 games of odds/snapshots per affected day. Pre-existing matcher quirk,
  unrelated to CLV; fix only if doubleheader CLV data is ever needed.
  RELATED PARKED ITEM (future project, needs sample): find the signal that
  distinguishes the model's GOOD disagreements (real market errors) from bad
  ones — if CLV shows edge, THIS is how you isolate the profitable slice.
  **UPDATE 2026-08-14:** the July 8 verdict (disagreements anti-predictive,
  −0.71pp) picked up its first COUNTER-observations: 8/13 DET (+6.5pp CLV, won)
  and MIA (+5.8pp CLV, lost 1-13) — the two largest model-vs-both-markets
  disagreements of the week, and the market moved TOWARD the model on both.
  One day, not a verdict reversal — but the parked "classify good vs bad
  disagreements" project now has a concrete new feature source: the exported
  kalshi.vs_book_pp column (book-vs-Kalshi split per side). Hypothesis worth
  testing at sample: model disagreements where BOTH independent markets sit
  together (small vs_book_pp) may behave differently from ones where the
  sources also split. Also tracking slate-wide CLV daily as the drift metric
  (Aug 11-13: −1.16 / −1.12 / +1.64pp).

- **[ARCHITECTURE, HIGH PRIORITY — surfaced 2026-06-06] Config-freeze +
  log-loss-only promotion gate blocks calibration fixes.**
  **[2026-06-07 — addressed via Approach B]** Made config editing a
  first-class operation, separate from retrain/promote. New CLI: `set-config
  --field F --value V` edits the production model's frozen BaseballConfig in
  place (whitelisted fields with sane ranges so a typo can't poison the live
  model; audited in params.manual_config_edits; reversible). `set-home-boost`
  is now a thin wrapper. `show-config` displays the live config + edit
  history. Rationale: a config edit is a RECALIBRATION of the existing model,
  not a new model, so forcing it through the retrain→log-loss gate was a
  category error. The retrain gate is left UNTOUCHED (still correct for its
  real job: deciding whether a retrained candidate replaces production).
  Validation of a config edit happens AFTER (run a week → calibration-deep),
  not via a pre-promotion holdout score.
  STILL OPEN (deliberately not done — would be over-engineering for a
  single-user local app now): (a) making the retrain gate itself
  calibration-aware (Approach A) — note it also needs pitching wired into the
  holdout replay, which is currently neutral-pitching; (b) fully separating
  live-config from the frozen training snapshot as schema (Approach C) — the
  someday-architecture if this becomes multi-model or hosted-at-scale. The
  discovery of WHICH config to change stays a human-in-the-loop step (read
  calibration-deep, decide, apply) — appropriate pre-hosting.

- **[RESOLVED 2026-06-29 — REJECTED, do not build] Taper bullpen recent-form
  weight on extreme swings.** See the 2026-06-29 shipped entry: the
  overrated-favorite defect was the PRE-run-shrink model; post-shrink big-swing
  games are +2.4pp (if anything under-confident). A taper would push calibrated
  games under water. Kept here (struck) so the idea isn't re-proposed from the
  stale framing below. ORIGINAL ITEM (historical): The model fix for the overconfidence finding now surfaced by the
  bullpen-swing flag (see Shipped 2026-06-05). Currently 12.4 blends recent
  (10-day) bullpen ERA at a flat 30%. Problem: when recent diverges hugely
  from season (>=1.5-2+ ERA), that 10-day window is mostly small-sample noise
  that mean-reverts, but 30% weight is enough to swing predictions into
  overconfidence (big-swing games: -19.6pp calibration gap; -13.3pp
  post-12.5). FIX: make the recent-form weight TAPER as the swing grows —
  keep most weight for a ~1-run swing, heavily discount a 3-run swing. e.g.
  effective_recent_weight = 0.30 * clamp(1 - (swing - 1.0)/K, floor, 1.0).
  Build behind a BaseballConfig toggle with a documented revert path (mirror
  the 12.5 pattern: pitcher_anchor_mode / pitcher_damping). VALIDATE against
  calibration before/after — do NOT ship on the current thin sample (n=13
  post-12.5). Decision gate: the June 7 calibration check + a few more
  big-swing games. If the taper improves big-swing calibration without
  hurting the well-calibrated no-swing bucket (-0.8pp now), keep it.

- **[INVESTIGATE] Probable-pitcher freshness vs FlashScore (observed 2026-06-01)**
  User saw all starters confirmed on FlashScore while our pipeline still
  flagged some as projected/unknown when the pre-game chain ran. We pull
  probables from MLB Stats API (`/schedule?hydrate=probablePitcher`), which
  can LAG faster aggregators by 1-2h. Two distinct causes look identical in
  output (`starter_known: false`):
    (a) MLB-feed lag — starter confirmed elsewhere but MLB's field hasn't
        flipped yet. Fix = timing (run chain later / per-match refresh), or
        consider a secondary probables source for cross-check.
    (b) Name present but no usable ERA (rookie/recall) → correct cap, working
        as designed, NOT a freshness bug.
  DIAGNOSTIC before any change: when a game is flagged unconfirmed but
  FlashScore shows a starter, re-run `sync-pitchers` later — if it flips to
  confirmed, it's (a) lag; if not, it's (b) or a parse gap. Characterize the
  pattern over several days before touching the sync — do NOT re-architect on
  a single observation. If (a) proves common, options: (1) later default
  pre-game timing, (2) add a fallback probables source, (3) widen the
  hydrate/parse. Low-effort first step is just timing guidance.
  **UPDATE 2026-06-02:** clean case observed — Mets 9:40pm game, starter
  genuinely unnamed everywhere (incl. FlashScore); our data correctly had
  away_pitcher=None, starter_known=False, tier capped to lean. Cap working
  as designed — NOT our lag, the info doesn't exist yet. BUT found a real
  LOGGING bug: sync_pitchers logged that match "confirmed (2 pitchers)"
  while only ONE pitcher resolved (Mets side null). The "confirmed
  (N pitchers)" log line over-reports — should say "partial (1 pitcher)" or
  "projected" when a side is null, and the count should reflect
  actually-resolved starters. Harmless to predictions (cap caught it) but
  the log misleads, which erodes trust in the pipeline. Easy fix.
  **UPDATE 2026-08-13:** root cause of the systematic West-Coast "projected"
  labels found and fixed — sync_pitchers bucketed by UTC date while MLB's
  schedule API speaks local business date, AND "confirmed" was a <=4h
  countdown. Both now run on business date (UTC-8h); day-of probables =
  confirmed. STILL OPEN (small): the "confirmed (N pitchers)" log line still
  over-reports when a side is null (should say "partial (1 pitcher)"), and the
  per-date log label still prints UTC date (cosmetic).

- **[QUEUED 2026-08-14] Kalshi team-name aliases + unmatched-title reporting.**
  TB@Athletics is the one persistently unmatched game — suspected cause: the
  A's play out of Sacramento and Kalshi likely titles the market "Sacramento",
  which shares zero tokens with our "Athletics" (strict-gate false negative,
  working as designed but fixable). Fix: small known-alias map
  (sacramento/oakland → athletics) in the matcher, and — per the
  reported-not-silent philosophy — print the titles of unmatched
  CURRENT-WINDOW markets so coverage gaps name themselves. ~1 hour.

- **[QUEUED 2026-08-14] kalshi-disagreement run on clean data (~2026-08-19).**
  The Step-1 verdict command exists (built 8/10) but has never run on
  trustworthy data — pre-matcher-fix rows were purged 8/12. After ~a week of
  clean two-sided captures, run `kalshi-disagreement` for the
  redundant-vs-independent verdict. Early manual reads: book-Kalshi corr 0.979
  with mean |gap| ~1.1pp (mostly redundant) BUT splits up to 2.2pp exist and
  the first graded split (TEX@LAA 8/12) resolved to Kalshi's side. Step 2
  (who's closer when they disagree) needs these grades accumulating.
  **STEP-1 VERDICT 2026-08-17 (n=214 paired sides, clean post-matcher data):**
  Kalshi is largely REDUNDANT as a second opinion — mean |diff| 1.00pp,
  signed +0.18pp (no lean), 6% of sides >=3pp, 3% >=5pp. Per the
  pre-committed rule: STOP — no Step-2 grading loop built. TWO CAVEATS kept
  on the record: (1) this table measures OVERLAP quality only — Kalshi's
  demonstrated value this week was COVERAGE (priced 3 Monday games the book
  feed never did, priced DH legs early, and unpaired games don't appear in
  this read at all) plus two single-game cases of being closer to close
  (TEX@LAA split, DH G1 books collapsing toward Kalshi's number); coverage
  value stands regardless of redundancy. (2) vs_book_pp keeps accumulating
  passively in exports at zero cost — revisit only if the >=3pp share grows
  or a lean appears. IMPLICATION FOR S3/S4: soccer Kalshi build proceeds on
  the coverage argument (single book provider there), but the 3-way
  disagreement columns ship as plain instrumentation — no prominence, no
  grading machinery.

- **NFL EXPORT GAP (user exchange 2026-09-17): no Kalshi surface.** The
  NFL rehearsal export's market block is books-only — MLB/soccer formats
  carry input_quality.kalshi + prices; NFL doesn't, though snapshots are
  already banked by sync-kalshi-nfl. Small add (read OddsSnapshot per
  match, two-sided), queued for the next NFL build slot — NOT rushed on
  opener day. Also: pre-kickoff re-export CONFIRMED as the standing NFL
  matchday pattern (model rows identical without new results; market
  blocks freshen — the Leeds-refresh precedent applied); the identity of
  model probs across same-day regenerations doubles as an integrity
  check.

- **N1 PHASE 1 SHIPPED 2026-09-17 (same quiet slot):** capture-weather-nfl
  — 32-team stadium map KEYED BY HOME TEAM (venue strings untrusted for
  NFL; tuple contract matches VENUE_COORDS), 11 roofed entries (9 domes/
  retractables + SoFi canopy + shared-stadium dupes), coords-based
  fetch_weather_at reusing the MLB Open-Meteo path, GameWeather storage
  mirrored. Tracking-only per the phase design — no model consumes it;
  the banked history compounds toward the totals work. Chain placement:
  after sync-odds-nfl in the weekly NFL rhythm. First-run verification:
  captured≈window size, roofed games stored as indoor(roof). Coordinate
  precision ±0.02deg (weather-adequate); corrections welcome if any
  stadium reads wrong.

- **S14 STAGE-1 COMPLETE 2026-09-17 (in-container, counterfactual on the
  46 graded games).** Baseline totals-direction was 39% (18/46) — the
  bucket bias has cost the direction record all season (their D+ grades
  vindicated). FLAT BEATS GRADED (bucket-shaped confirmed twice).
  CANDIDATE SELECTED: flat +1.0 goals on uncertain-winner games
  (top_pick<0.45) — residual +1.17->+0.17, confident bucket untouched,
  direction 24/46 (within one of best). IN-SAMPLE caveat owned: fitted on
  the diagnosing data. STAGE-2 ACCEPTANCE FROZEN NOW, before any number:
  on held-out prior seasons via the backtest harness, the adjustment
  ships iff (a) uncertain-bucket signed residual moves toward zero,
  (b) overall totals-direction does not degrade, (c) confident-bucket
  residual stays within ±0.15 of its unadjusted value. Implementation
  (Stage-2 session): predict-time bump behind config
  s14_uncertain_totals_bump, through the normal gates.

- **CAP-VARIANT VERDICTS 2026-09-17 (same morning): ALL FOUR DECLINED —
  baseline v1 stands unchanged.** cap 0.72: LL 0.6382 (worse; its 70-80
  band nicety 4.3->3.5pp cost real information). cap 0.75: 0.6388. cap
  0.80: 0.6384. shrink 0.90: LL 0.6347 (BETTER) but 40-50 band 6.6->
  7.6pp = degraded >0.5pp and breached 7pp — the gate printed FAIL
  itself; the two-part bar caught exactly the LL-for-calibration trap it
  was written for. BONUS FINDING: the 0.80 cap forced the first n=30
  80-90 band — stated 0.800 REALIZED 0.833: the >0.80 zone was UNDER-
  confident on 2025, not overheated; Week 1's 1-1 split on >0.80 rows =
  noise. GPT's cap ask: tested and declined with receipts (their other
  two asks untestable-declined earlier). Week-2 rehearsal file generates
  from UNMODIFIED v1; dry-read note carries all five verdicts. The
  rejection culture extends to the NFL R-track on its first trial.

- **CAP-VARIANT HARNESS SHIPPED 2026-09-17 (opener morning, before any
  variant result exists).** nfl-backtest-caps tests baseline vs cap 0.72
  (GPT ask) / 0.75 / 0.80 (our validated-zone edge) / logit-shrink 0.90,
  applied at scoring time only (identical walked stream). ACCEPTANCE
  FROZEN PRE-RESULTS: a variant ships iff LL beats baseline AND no n>=30
  band's calibration gap worsens by >0.5pp. UNTESTABLE ASKS DECLINED
  WITH REASON: road-inversion cap (defined vs market; backtest has no
  historical odds) and divisional cap (no division map) — untestable =
  unshippable; revisit when live market-anchored weeks accrue. Sentinel
  extended to the shared MLB/NFL Kalshi path (soccer-only gap closed).
  SEQUENCE: user runs caps this morning -> verdicts vs frozen bar ->
  surviving variant (if any) wired into predict-nfl -> Week-2 rehearsal
  file generated -> formal GPT dry read BEFORE tonight's opener.
  CUP ANSWER KEY UPGRADED same morning: Wednesday 2/4 incl. Fleetwood
  19% home-dog WIN and Brighton at Old Trafford — the key now contains
  real upsets, so acceptance grades PRICING vs stored books, not
  result-matching (a 19% price that loses passes; a 45% price that wins
  fails). Key: 25/33 favorites across four cup slates. 7 next-round EFL
  ties already created.

- **EFL TUESDAY SLATE MISSED-WINDOW 2026-09-16 (Claude's error, owned):**
  the layover roster used --start 09-16; the actual slate was 09-15 —
  five ties (incl. Liverpool-Spurs, Ipswich-Arsenal) went un-rostered;
  GPT layer traded unassisted "really well" AGAIN (baseline grows).
  Two-day export heals the record: consensus 4/5 graded with stored
  books = five more answer-key pages. LESSON: cup rosters use two-day
  windows by default (cup rounds straddle days).

- **LAYOVER CONSOLE NOTE: sentinel coverage gap.** The matched-zero
  alarm lives only in sync_kalshi_soccer; the NFL/MLB shared path lacks
  it (today's NFL 0/32 was benign future-week listings, but the guard
  should cover every sport that can go dark). Three-line add to the
  shared function — next quiet slot. EFL roster shipped: 4 ties incl.
  Coventry home-dog to Villa + Fleetwood 19% v Sheffield Utd — premium
  cross-division acceptance evidence, 11-12 books each.

- **S14 VERDICT 2026-09-16 (read at n=46, computed from results files
  after the CLI diagnostics proved MLB-only): HYPOTHESIS CONFIRMED —
  BUCKET-SHAPED.** Uncertain-winner games (top pick <45%) under-project
  +1.17 goals (n=25); confident-winner +0.08 (n=21); all-games +0.67;
  projection-band cut corroborates (<2.5: +0.85; >=2.5: -0.04). The
  model couples winner-uncertainty with totals suppression. S-TRACK:
  uncertainty-conditioned totals adjustment (NOT a blanket raise — the
  +0.08 bucket would be punished), designed + Stage-1 backtested before
  production; queued with the NFL cap variants. CATALOG CORRECTION:
  totals-check / calibration-series are MLB-only (--sport choices
  mlb/baseball) — docs/CLI.md rows corrected; soccer totals diagnostics
  = future S-track tooling if the fix ships.

- **HAND-OFF RITUAL RULE (user, 2026-09-15):** every packaged tarball is
  presented WITH the exact command block — extract + git add/commit/push
  with a descriptive commit message — so the repo history narrates every
  drop. No bare tarballs.

- **NFL WEEK-1 AUDIT 2026-09-15: FIRST MODEL ASKS — and correctly so
  (rehearsal phase = when consumer input belongs).** Their evidence: 4
  biggest disagreements 0-4; positive-CLV picks 6-6 (their "CLV != win
  equity" = our convention caveat, independently derived). ASKS: early-
  season caps (72% general / 65% divisional / 58% road-inversion),
  disagreement quarantine, margin layer before spreads. R-TRACK PLAN
  (next session, BEFORE the Week-2 rehearsal file): backtest each cap
  variant on the existing harness; PRE-COMMITTED ACCEPTANCE — a cap
  ships iff backtest log-loss improves AND no calibration band degrades.
  72% cap has directional support (70-80% band leaned over-confident;
  >80% zone was never sample-validated — capping unvalidated
  extrapolation = the tier-freeze principle on probabilities).
  Divisional variant needs a division map (small build); road-inversion
  testable now. Margin/spread layer: declined for now — sides-only v1,
  logged as future phase. Survivors ship with receipts; rejects declined
  with receipts.

- **MW4 WEEKLY AUDIT 2026-09-15 (GPT layer): CONVERGENCE.** Their
  Protection A- IS our misses-by-draw finding found independently —
  double-chance converted the exact rows the ledger flagged (Forest X2,
  Everton X2, avoided LIV/CHE MLs). Closing rec explicitly NOT "pick
  winners better"; zero model asks again. Their Tail-calibration D+
  (signed +0.42 vs absolute 1.90 = too NARROW, not too low) lands as
  S14's PRE-COMMITTED READ COMES DUE: n=40 graded (needed 30). Read
  issued (totals-check --since 2026-08-14 + calibration-series);
  verdict against the filed rule; any change via backtest, S-track.

- **MOUNTAIN MORNING 2026-09-15 + two rhythm builds.** MW4: 5/10 (season
  22/40); GIANT EDGES SPLIT — Forest +20.6 WON, Hull +27.3 and Everton
  +31.3 both MISSED BY DRAW -> cohort 6/12 with FOUR of six misses by
  draw: the model's big away edges are right about underdog strength,
  wrong about win conversion. Derby City +8.9 HIT; Leeds 4-1 HIT.
  NFL Week 1 FINAL: 9/16, LL 0.6755 (Denver row lost — BOTH max-
  conviction disagreements failed 0-2; the KC row alone moved LL past
  backtest); CLV-convention caveat logged (positive pick-vs-close on
  wrong-side rows is not a virtue — read jointly with results). MLB 7/10,
  v136 = 27th rejection. BUILDS: export-nfl-results (consumer results
  shape, rehearsal-flagged; joins the morning rhythm after nfl-grade) and
  results-tally -> RESULTS.md (rolling 30d per-sport record, README-
  linked, auto-generated; morning rhythm addition). Docs updated per
  standing rule.

- **NFL WEEK-1 GRADED 2026-09-14 (nfl-grade inaugural run, 15 games, MNF
  pending):** sides 9/15, LOG-LOSS 0.6441 vs backtest 0.6361 — the
  gate-passed performance TRANSFERRED live; mean pick-vs-close +3.91pp
  (consistent off-market confidence, unpunished wk1). Extremes: >0.80
  zone split (JAX 0.830 won 34-10; LAC 0.801 lost — market 0.792 missed
  equally). BIGGEST DISAGREEMENT LOST: MIA@LV (model 65% MIA, market 59%
  LV, Raiders won) — 2025-Elo-memory cautionary exhibit; twin row DEN@KC
  resolves tonight. QB-FLAG VINDICATION: the SF@LAR miss (model 68.7%
  Rams, SF won 27-7) carried Caldwell in qb_listed — the flag marked the
  fragility that decided the game. REHEARSAL: proceed as sequenced
  (Week-2 rehearsal + dry read; live Week 3 earliest). Injuries skips
  179 (Monday churn; skip-cause characterization still casual-backlog).

- **CLI CATALOG SHIPPED 2026-09-14 (user request):** docs/CLI.md —
  command inventory extracted FROM SOURCE (45 via regex + core chains),
  organized by workflow (setup / syncs / MLB daily / soccer weekly / NFL
  rehearsal / gated cups / eval / diagnostics / web), with the
  required-services matrix (per-provider endpoints + env vars + the
  fallback-key chain + subscription licensing notes) and local
  components incl. the DB-backup line. README links it. Doc-drift note:
  regenerate the inventory when commands are added — the extraction
  snippet lives in the conversation record; a `cli-docs` generator
  command is a possible future nicety.

- **N1. NFL WEATHER CAPTURE [user-spotted gap 2026-09-14; not previously
  logged].** MLB's capture-weather (venue coords, roofed handling,
  capture stamps) has no NFL sibling — and NFL is the sport where weather
  matters most (wind >15mph suppresses passing/kicking; late-season cold
  moves totals markets). PHASES: (1) capture layer — NFL stadium coord
  map (~30 venues) + domes/retractables list (ATL DAL DET HOU IND LV MIN
  NO AZ; SoFi canopy counts roofed) + weekly chain step; worth building
  SOON because banked history compounds and the games where it matters
  arrive with the cold. (2) export context field (wind/temp per game,
  consumer-side — their totals reads off our captured lines). (3) model
  input ONLY when an NFL totals model exists (distant; sides-only v1
  doesn't consume it). Build slot: next quiet slot post-Week-1 grading.
  Current-model impact of the gap: zero (Elo consumes no weather); the
  cost is unbanked history, which is why phase 1 shouldn't wait for
  October.

- **DOCS REFRESHED 2026-09-14 (user request):** README rewritten to
  current four-sport reality (was May-era soccer-only); CHANGELOG.md
  created and seeded with the season's milestones. STANDING RULE going
  forward: every drop updates CHANGELOG.md (summary) alongside BACKLOG.md
  (detail) before packaging — documentation is part of the ship, not an
  afterthought.

- **U3 CLOSED 2026-09-14: GitHub repo live** (private,
  anthonyevans29/Sports-Predictor, first push 130 objects / 448 KiB =
  code+docs only, .gitignore verified working). Pre-push vulnerability
  scan: CLEAN — no secrets (env template only, all keys via getenv; lone
  key-shaped literal is Kalshi's public Tie-strike UUID), no data, no
  PII. Private retained deliberately: BACKLOG.md is the edge, not a
  vulnerability. Ritual gains half-step: extract -> commit -> push, with
  commit messages documenting each drop. Auth via fine-grained PAT
  (contents-only, single-repo). REMAINING PERSISTENCE ITEM: weekly DB
  backup (sqlite3 .backup) — the one irreplaceable artifact git doesn't
  cover.

- **BUILT 09-14 (pre-slate quiet slot), three items:** (1) nfl-grade
  command — Week grading vs finished games + banked closer consensus
  (sides, log-loss, per-pick CLV), read-only; makes tomorrow's Week-1
  read automatic and feeds the Week-2 rehearsal decision. (2) Soccer
  Kalshi matched-zero SENTINEL — loud warning when games AND markets
  present but matched==0 (the two-dark-matchweeks lesson). (3) In-play
  guard keyed on OUR kickoff at capture (derby lesson: occurrence is
  close-time). First two edit attempts MISSED their anchors (guessed
  code); caught by assertion, re-applied against read code — the
  read-before-edit rule enforced by its own tooling.

- **NFL WEEK-1 GAME-DAY COMPARISON 2026-09-13 (internal; the rehearsal
  evidence file):** 15 priced games, mean model-vs-book gap ~-1.6pp =
  NOT systematically hot; >0.80 rows behaved (+1.0/+5.9/+5.8 vs books).
  THE STORY: two -24pp disagreements (model makes MIA and DEN live road
  threats vs clear home-favorite books — 2025-Elo memory vs offseason
  knowledge), largest divergences in system history; graded tonight.
  Kalshi Week-1 board listed overnight: matched 28 / 14 games two-sided /
  ambiguous 0 (parameterized matcher at full NFL coverage). QB feature
  full flower: Tua AND Rush listed for ATL (controversy signal), Bagent,
  Darnold+Milroe, Rourke, Morton. 12,300 closing-anchor odds rows banked.
  DERBY KALSHI POSTSCRIPT same day: snapshots existed but were captured
  in-play (DB kickoff 15:30Z vs Kalshi occurrence 18:30Z — occurrence is
  close-time, not start); export's post-kickoff filter correctly refused
  = defense in depth held. Fix-session item: in-play gate should also
  check matched game's utc_date at capture.

- **MW4 FALSE ALARM 2026-09-12 — full reversal, on the record.** Claude
  called HOLD on the MW4 export (edges +27/+31/+21pp, inversion-shaped)
  and advanced two theories; BOTH FALSIFIED by probes within the hour:
  (1) compressed-Elo leak — model_versions probe shows v18 production
  intact (1368-1691), v19/v20 properly rejected; (2) data mutation — the
  "28 finished" is two POSTPONED fixtures, all played games healthy.
  Standing explanation: v18 behaving AS DESIGNED — heavy current-season
  weighting on 28 games (Hull UNBEATEN, Chelsea/Spurs cold starts) plus
  post-break injury pile-up on big clubs = the thermometer's anti-
  predictive-shape edge at maximum amplitude. FILE SHIPPED with caution
  note at full strength; quarantine reversed — Monday grades normally and
  MW4 becomes the pick-edge ledger's most informative matchweek: maximum
  model conviction vs maximum market disagreement, graded in 72h.
  LESSON LOGGED: verify before withholding — a 40-minute hold on
  legitimate output; the probes, not the alarm, made the decision.

- **FIRST LIVE CONSUMPTION OF MARKET-ONLY FORMAT 2026-09-11:** GPT layer
  traded the cup rosters off market context + own football reads (self-
  audit: A- football logic, C entry-price discipline — their layer, their
  jurisdiction). Boundary HELD: no predictions existed to consume; the
  layered design's "winner logic vs betting logic" separation was
  independently rediscovered in their own audit. Their 19/24 consensus
  read matches our review exactly (two graders, one answer key). BANKED:
  this week = the consumer's UNASSISTED cup baseline — post-acceptance,
  model value-add over market-context-alone becomes directly measurable.

- **CUP WEEK REVIEW 2026-09-11 — acceptance answer key COMPLETE.** 24
  graded fixtures with stored pre-game books (14 each): EFL R3 favorites
  6/6 (pure chalk, incl. cross-division); CL MD1 favorites 13/18, ALL
  extreme mismatches held (80-90% band 3/3: Barcelona/United/Bayern;
  90%+ 1/1), misses confined to sub-60% coin-flips, 2 draws. CHALK WEEK =
  BOOKS WERE RIGHT = the +/-8pp acceptance bar has no soft spots; no
  upset noise to excuse a miss. Rosters shipped to GPT layer as the cup
  ledger. The fixed cup model's exam is now fully written and waiting.

- **NFL DAY-2 INTERNAL READ 2026-09-10:** QB feature live end-to-end
  (Caldwell/Rams named IN the one priced game). Frozen tiers didn't soften
  the slate — 11/16 still strong at 0.68: the DISTRIBUTION is hot, not the
  labels; rows >0.80 are unvalidated extrapolation (backtest bands stop at
  80). Weekend book postings will price the overheat row-by-row; a
  probability cap above the validated range becomes a rehearsal question
  IF the gaps confirm. Market ledger day 2: +4.6pp (SF@LAR). Provider
  publishes per-gameday (opener left window; Friday game freshly priced;
  14 await). NEXT NFL BUILD (Claude, before Week-2 rehearsal): evaluate
  path for NFL — sides + CLV vs banked closers — so rehearsal weeks grade
  automatically instead of by hand.

- **NFL TIER THRESHOLDS FROZEN 2026-09-10 (pre-Week-1 results, per the
  shakedown finding):** strong >=0.68, lean >=0.57, else toss-up. Frozen
  BEFORE any live NFL outcome exists so results cannot tune the vocabulary;
  the shakedown's 11/16-strong slate re-tiers to a meaningful spread. Any
  future change goes through a pre-committed read, same as everything.

- **NFL SHAKEDOWN FINDINGS 2026-09-09 (Week-1 internal file, nothing
  shipped):** machinery works end to end. THREE FINDINGS: (1) tier
  distribution too hot — 11/16 strong under MLB-inherited thresholds;
  NFL-specific tiers to be PRE-COMMITTED before the Week-2 rehearsal
  (proposal: strong >=0.68, lean >=0.57); backtest's own 70-80% band
  leaned over-confident (74.1 stated / 69.8 realized) and nothing >80%
  was sample-validated; Week 1 is Elo's stalest week (offseason roster
  turnover invisible). (2) RESOLVED same evening: the injuries
  endpoint carries NO position field at all (player = id/name/image —
  raw probe). Fix: list_injuries now fetches the team roster alongside
  and joins position by provider player id (best-effort, one extra
  request/team); re-run sync-injuries to heal all rows, verify with the
  GROUP BY. Free extra finding: empty-team responses are clean, so
  synced_at:null conflates healthy-roster with never-synced — per-team
  sync stamp regardless of rows = rehearsal-review refinement. (3) Market ledger opens: model hotter than books on both
  priced games (+10.8pp SEA, +4.6pp LAR) — matches the over-confidence
  shading; comparison accrues as Week-1 books post.

- **NFL PREDICTION PATH BUILT 2026-09-09 (same day as the gate pass).**
  predict-nfl: full-stream ratings (preseason excluded) -> upcoming-game
  probs -> MATCH-ONLY upsert (S13 semantics from birth). export-nfl-
  predictions: rehearsal-format file — model probs + tier, market fair
  probs, QB status front-and-center in input_quality (qb_listed names per
  side + injury counts + sync stamp), rehearsal:true flag + note until the
  Week-2 rehearsal passes. SHAKEDOWN PLAN: generate against Week 1
  internally (we inspect, nothing ships); Week 2 = formal rehearsal + GPT
  dry read; live Week 3 earliest.

- **NFL GATE VERDICT 2026-09-09 (same day): PASS — decisively.** Model
  0.6361 vs baseline 0.6911 (margin 0.055 = 5.5x required); all four
  n>=30 bands calibrated <=7pp (worst 6.6pp in 40-50% — stated 45.5%
  realized 38.9%, road-favorite shading, WATCH at rehearsal, not defect).
  HONEST FRAME: baseline was weak by construction (no historical odds) —
  this establishes signal, NOT market-beating; the market comparison
  accrues from Week-1's banked closers onward. EARNED: Week-2 dress
  rehearsal. NEXT BUILD (Claude): NFL prediction path — predictions-table
  writes, export format with QB-status input_quality, tier semantics —
  so the rehearsal generates real files. Live Week 3 earliest, after
  rehearsal + GPT dry read. Gate numbers were frozen pre-model and held.

- **NFL PHASE 2 GATE — WRITTEN 2026-09-09 BEFORE ANY MODEL CODE EXISTS.**
  Protocol: walk-forward over finished NFL games in utc_date order,
  PRESEASON EXCLUDED from training and scoring (rotation noise — the EFL
  Trophy principle). Warm-up: season 2024 (ratings accrue, nothing
  scored). Scored window: season 2025 regular+post (~285 games).
  Baseline (honest limitation: NO historical odds exist in the backfill —
  provider serves pre-match windows only — so no market baseline is
  possible): constant home-probability fitted on the WARM-UP season's
  realized home win rate only. PASS REQUIRES BOTH:
  (1) model mean log-loss <= baseline mean log-loss MINUS 0.010;
  (2) calibration: in every 10pp band with n>=30, |realized - stated
  mean| <= 7pp.
  FAIL on either -> model does not ship, iterate or park; Week-2
  rehearsal only after a pass; live only after rehearsal + GPT dry read.
  These numbers are frozen now — the backtest may not be re-read
  against friendlier criteria.

- **NFL PHASE 1c CLOSED 2026-09-09 — Week 1 tracking LIVE pre-kickoff.**
  Kalshi debut: matched 4 / ambiguous 0 (two early-listed games, both
  sides; 60 future-week legs date-refused) — the parameterized matcher
  served NFL unmodified. Injuries: 296 rows (QB-status pipeline live,
  ~9/team; 117 skips to characterize casually later). Books: NEW
  sync-odds-nfl command (built same morning — the Week-1 CLV-anchor gap
  found and closed pre-kickoff) captured 548 rows across the two
  posted games (~274/game: full NFL depth incl. spread/total lines);
  14 games await provider publication through the week. Cups results
  banked same console. WEEK-1 STANCE RESTATED: tracking only — no NFL
  model exists yet (phase 2 queued behind compression work by design);
  the opener's story is data end to end, and the model earns its slot
  against exactly this data. Weekly rhythm: sync-odds-nfl + sync-kalshi-nfl
  every day or two through the week as lines post.

- **U2. EXPORT CONTEXT FIELDS: prev/next fixture awareness [user request
  2026-09-08; export-only, zero model risk].** Per team per row: previous
  result + date + COMPETITION, next fixture + date + competition + venue;
  rest-days for each side AND the differential; congestion (matches in
  last 14d). Phase 2: last-5 form string. Consumer-side behavioral signals
  (post-cup letdown, congestion asymmetry, rotation pressure); NOT model
  inputs — if GPT-layer use proves predictive they enter the S-track
  normally. Pure DB reads; U1-class safety; buildable any day.

- **DIAGNOSIS UPDATE 2026-09-08 (verdict count): transitions = 8 — suspect
  NOT convicted.** Old stream carried ~4-6 at the same boundaries and
  produced spread 323; similar counts cannot explain 4.4x collapse alone.
  Per-team regression fix remains right-in-principle (wrong semantics on
  an interleaved stream) but is no longer claimed as the cure. NEXT:
  decisive instrumented double-train (old pot vs new pot, per-team rating
  trajectory dump) — script next session, five-minute run user-side,
  locates the collapse point empirically. Round-3 books (16 ties) + CL
  MD1 odds (18 legs) banked for the acceptance test.

- **COMPRESSION DIAGNOSIS 2026-09-08: MECHANISM FOUND (pending one count).**
  train() applies season regression on EVERY season-string TRANSITION in
  the single chronologically-interleaved multi-competition stream (global
  last_season toggle). Misaligned competition calendars (summer European
  qualifying labeled next-season vs playoff/final stragglers, cups leading
  leagues) toggle the string repeatedly; each toggle pulls ALL teams 25%
  to 1500. Five toggles = spread x0.23 = 323->74 observed. Only
  state-shrinking operation in the file; deterministic; matches v19/v20.
  VERDICT SQL issued (count transitions in the real stream). FIX (correct
  regardless of count, prepped for review): per-TEAM season regression —
  a club regresses when ITS new season starts, immune to stream
  interleaving. Then: bonus-application read -> gated retrain (spread
  guard) -> acceptance vs round-2 + round-3 stored books -> CL-matchday
  dress rehearsal THIS WEEK if all passes. Round 3 itself: data-only,
  ruling held under calendar pressure.

- **EFL TROPHY: CONSCIOUSLY EXCLUDED (user question 2026-09-08).** Not
  registered (API league 46 — one line if ever wanted) and should stay out:
  U21 academy sides -> skip walls or junk team rows; heavy rotation makes
  results low-signal about true strength; and the trainer consumes ALL
  soccer matches, so Trophy results would contaminate pyramid club ratings
  — the exact ratings the cup project is fixing. Re-entry condition: a
  training-exclusion flag (competition-level exclude_from_training) built
  FIRST, then registration. CL same day: teams+matches+odds synced
  (data-only per ruling; odds deliberately captured as acceptance-test
  evidence for cross-league pricing).

- **FA CUP PLAN (user question 2026-09-07, qualifying rounds underway):
  DO NOT sync qualifying — near-pure cost** (non-league both-sides ->
  skip walls; sync-teams would balloon the table with hundreds of clubs;
  signal value ~nil since league play is the strength source and NL isn't
  in the league table). API keeps history -> waiting is free; deep-running
  non-league sides get targeted retro-backfill when relevant. TRIGGERS:
  (1) Round 1, November — EFL clubs enter, sync then; (2) MANDATORY before
  Round 3, January — PL entry, prediction-relevant, gated behind the cup
  acceptance test like EFL/CL. Phase-4 note: add a National League tier
  below EL2 (-360) to league_strength as part of explicit-unknown-league
  handling.

- **MW3 CLOSED 2026-09-07: sides 3/10 (season 17/30) — worst matchweek;
  BOTH giant edges (Forest +15.4, Hull +14.6) missed BY DRAW, both with
  POSITIVE CLV (+15.2/+14.2: market moved toward the model, reality drew
  anyway). Forward positive-edge cohort: 4/8 — the MW2 counter-trend
  regressed on schedule; the haircut discipline's clearest vindication.
  n=30 read unchanged. Draw-miss pattern noted for the ledger.

- **SPREAD GUARD FIRST LIVE FIRING 2026-09-07: v20 REJECTED with the
  designed message** ("candidate 74 vs production 323 over 27 common teams
  (23%) — fit collapsed toward the mean"). v19: 63. COMPRESSION IS
  DETERMINISTIC — same collapse, same data, twice. Gate design validated;
  production v18; break-window diagnosis begins from a confirmed
  reproducible target. Refresh stays parked until the fit-dynamics read
  lands.

- **M17 (observation only): first total provider odds outage, 2026-09-06.**
  Entire 15-game Sunday slate bookless — bulk pull healthy (10,906 rows /
  76 games on OTHER days), per-game fallback probed all 15 with clean "no
  odds yet", DB shows ZERO rows ever captured for today's games (no wipe;
  never listed). Provider-side publication gap, fully characterized in one
  console by the sentinel stack. System response correct throughout:
  honest book_odds=0, Kalshi two_sided 15/15 (Step-1 redundancy verdict's
  biggest day — full slate on the backup source), consumer notified.
  Expectation: null-CLV day tomorrow unless closers publish late; M11b
  heals whenever they land. NO ACTION — filed as the reference case for
  what a provider outage looks like vs a code fault.

- **U1. UNIFIED DAILY CARD ACROSS SPORTS [user request 2026-09-06; UI-only,
  zero model risk, buildable any day incl. matchdays].** The MLB card
  (src/walters/card.py build_card + /card route + CLI parity — fact
  assembler with honest flags) extends to soccer and NFL. Scoping (read):
  sport coupling is ONE query line, but fields are baseball-shaped — the
  real work is per-sport field vocabulary through shared bones:
  soccer = draw prob, injury/xG notes, promoted_this_season, Kalshi
  three-way, cohort flags; NFL = schedule/odds/injury rows pre-model
  (tracking-first phase gets a card too), model fields when one earns a
  slot. PHASES: (a) build_card(sport=...) + soccer card parity;
  (b) THE UNIFIED "TODAY" PAGE — every game, every sport, tier/flags/
  market-disagreement at a glance, per-game drill-down: mission control
  for the actual daily workflow (three sports, N files); (c) NFL column.
  Priority: high-value, never displaces gated items (phase 4, NFL model);
  natural interleave work for break windows and matchday-freeze days.
  Old deferred "match-view UI" item folds into this.

- **NFL 1c FIELD VERIFICATION 2026-09-06 — all four probes reported:**
  (1) ODDS MAP VERIFIED PERFECT: provider serves Home/Away, Asian Handicap,
  Over/Under verbatim (3Way Result deliberately unmapped — NFL moneylines
  are two-sided here). (2) KXNFLGAME CONFIRMED: 64 live markets; matched 0
  = the EPL listing pattern (sample market Sept 21 — future weeks only,
  outside now+7d; Week-1 markets expected to list near Thursday; Tue/Wed
  re-run confirms). (3) BUG FIXED: /injuries rejects the season param
  entirely (current-status feed, team-only) — param dropped, signature
  kept for the service contract. (4) BUG FIXED: new cli command printed
  "None markets" (wrong summary key). Also: the 16 status-less games
  healed via the seasons re-run (updated=334x2). Remaining before Week 1:
  Tue/Wed sync-kalshi-nfl + sync-injuries re-run = phase 1c closes.
  CL SCOPE RULING (same day, user flagged CL starts Tuesday): Champions
  League prediction sits behind the SAME phase-4 gate as EFL Cup — no
  continental leagues synced means opponents resolve to league None ->
  the -100 default bug class; data syncs run, NO CL rows ship until the
  cup acceptance test (now extended: cross-division AND cross-league legs
  must price sanely). Phase 4 now unlocks THREE competitions (EFL, CL,
  FA Cup early rounds incl. pyramid clubs) — priority raised accordingly.

- **NFL PHASE 1c SHIPPED 2026-09-06 (Sunday quiet slot):** (1) Kalshi sync
  PARAMETERIZED, not copied — sync_kalshi_mlb gains sport + series_override;
  the two-sided matcher (city collisions, ticker parse, in-play guard,
  doubleheader handling) serves NFL unchanged; new cli sync-kalshi-nfl
  passes Sport.NFL + "KXNFLGAME", and an empty result self-reports Kalshi's
  available sports (the console IS the series-discovery probe).
  (2) NFL list_injuries on the adapter (provider /injuries is a
  current-status feed; service contract mirrored; the 14-day freshness
  filter applies unchanged) — QB status now flows to the same Injury table
  as soccer's team news. (3) Odds-map verification probe issued for the
  moment Week-1 lines post. First-run verifications: sync-kalshi-nfl
  console (series guess + matcher stats) and sync-injuries --competition
  NFL console (provider response shape vs assumed keys) — both are
  probe-shaped by design; either failing loudly is the plan working.

- **NFL PHASE 1b COMPLETE 2026-09-05 (same day as 1a).** 989 games banked
  across 3 seasons (701 FINISHED incl. quarter-parsed totals; 288 scheduled
  = the 2026 season). 32 teams. Two same-day fixes en route: season-string
  format collision (--seasons generated soccer-shaped "2026/27" for NFL;
  generator now sport-aware AND adapter tolerates both — third format
  lesson, structural fix) and a FALSE ALARM on statuses that was Claude's
  receipt SQL querying enum VALUE ('finished') where SQLite stores the NAME
  ('FINISHED') — a RECURRING trap now named (hedged correctly in the
  rollover-fallback query weeks ago, forgotten in the receipt; hedge it
  everywhere or don't write raw-SQL receipts). The conservative status map
  worked as designed throughout. Residue RESOLVED same day: the 16
  rows have NO status block upstream (short=None, full totals present) —
  adapter now infers FINISHED when status is absent AND both totals exist
  (score-presence beats status-absence; never overrides an explicit short).
  Heals on the next --seasons 3 re-run. Aggregate skip line worked cross-sport
  unmodified (7+1+1 skips, HOF-game-shaped). PHASE 1c NEXT (Claude, early
  week): Kalshi KXNFLGAME sync, injuries/QB-status wiring, odds-map
  verification probe on a Week-1 game once lines post.

- **NFL PROJECT OPENED 2026-09-05 — phase 1a SHIPPED (user go-ahead; season
  starts next week).** Foundation pre-existed (Sport.NFL in schema; player
  table designed for QBs; Kalshi discovery multi-sport). Shipped today:
  APIAmericanFootballAdapter (full DataAdapter: teams/games/odds vs
  v1.american-football.api-sports.io, NFL league id 1, single-year seasons,
  conservative status map — unknowns stay SCHEDULED); NormalizedOdds gains
  optional `line` (spreads/totals; sign preserved — the -3.5/+3.5 bug was
  caught by unit test before shipping); registry + cli routing (NFL code ->
  nfl adapter). Unit suite passes (moneyline/totals/spreads normalization,
  draw leg refused).
  PLAN, pre-committed: Phase 1b (user, weekend): sync-competitions ->
  sync-teams -> sync-matches --seasons 3 (~850 games) + one odds probe on
  an upcoming game to verify the provider's actual bet names against
  _MARKET_MAP. Phase 1c (Claude, early next week): Kalshi NFL sync
  (KXNFLGAME discovery, thin variant of the MLB path) + injuries wiring
  (QB status = the pitcher-confirmation of NFL, core input_quality from
  day one). Phase 2: model (Elo+margin v1) built on backfill, BACKTESTED
  with a gate WRITTEN BEFORE THE BACKTEST RUNS. Phase 3: Week-1 dress
  rehearsal (predictions generated, verified, GPT dry read, NOT consumed);
  live only after a pass — never rushed for kickoff. Tracking (market
  captures, CLV anchors, injury snapshots) starts Week 1 REGARDLESS —
  export-the-gap applies to a whole sport. Queue order for the break:
  compression diagnosis -> NFL 1b/1c -> pyramid retrain+acceptance ->
  NFL backtest.

- **MW3 KALSHI GAP 09-04: not a bug — no MW3 listings exist.** The zero-
  match Friday sync was the matcher being RIGHT: probe showed all 63 open
  KXEPLGAME markets are Sept 13+ fixtures (MUN-MCI, LEE-NEW, BRE-CFC);
  Kalshi simply has not listed this weekend's games (post-break listing
  gap or marquee-early pattern). Books+API-Football agree MW3 is live this
  weekend (full odds created). Books-only matchweek unless listings open;
  Saturday refresh is the monitor — if matched jumps, they listed late.
  No code change; "data-shape delta" hypothesis WRONG, logged as such.
  Probe note: Claude's first probe accidentally took the MLB path
  (hasattr short-circuit) — the soccer console's own sample line would
  have answered faster; ask for it first next time.

- **M-LEDGER 09-02 (graded 09-03): sides 4/15 — worst day of tracking,
  absorbed cleanly.** v124 rejected on the 409-game holdout (15th straight;
  the morning after the worst day is the gate's proof). Machinery all
  green: aggregate skip line firing, backfill healed 1, zero nulls. GPT
  14th audit: HOLD under maximum temptation. M16 BAND: 5/6 overs -> forward
  10/13 vs historical 40% — BUT second consecutive elevated-scoring night
  (5 blowups, means +3.04/+1.53): the streak rides the environment.
  COVARIATE NOTE ADDED TO THE M16 READ (pre-committed now): at n=200,
  condition band hit rate on league run environment so a scoring surge
  cannot masquerade as calibration. Verdict unchanged, tally recorded.

- **M13 v3 candidate [low priority, quiet-slot]:** v2's prefix heuristic
  resolves name-prefix codes (HOU/MIL/TEX — Saturday's live pass) but not
  INITIALISM codes (NYY/LAA scored zero on 09-01's collision -> correct
  refusal, one_sided cost). Fix = small explicit code table for initialism
  franchises (NYY, NYM, LAA, LAD, CWS, CHC, SD, SF, TB, KC...), used as an
  additional exact-token check in _seg_hits. Refuse-safe posture unchanged.
  Also 09-01: doubleheader-guarded fallback first clean single-game pass
  (one id, once, honest empty); M12 aggregation verification deferred to
  the morning chain (evening sync fetches slate-window only, skipped=0);
  FOUR M16 over-lean rows flagged to consumer (BOS 0.579 = band max).

- **BUILT 09-01 (pre-MLB quiet slot), four items:** (1) S17 SHIPPED —
  results-export label now includes draw; draw_prob emitted; label/grade
  assertion logs ERROR loudly on inconsistency. Test: re-export
  --date 2026-08-29, Bournemouth row must read top_pick=draw 0.3389.
  (2) M12 aggregation SHIPPED — per-match skip warnings demoted to DEBUG;
  ONE summary WARNING with count + id range per sync. Test: tomorrow's
  morning chain shows a single line instead of 53. (3) Gate rating-spread
  guard SHIPPED — candidate Elo spread over common teams < 60% of
  production's = reject ("fit collapsed toward the mean"); v19's ~19%
  ratio would have tripped it even without the drift check. (4) EL->UEL
  normalization: SQL issued to user (one UPDATE + cleanup of the empty
  legacy competition row).

- **MW2 CLOSED 2026-09-01: sides 8/10 (season 14/20).** THE TWO +19pp
  ROWS BOTH HIT: Hull 1-0 at Coventry (close 4.92, CLV +20.9pp — ledger
  max), Newcastle 2-0 at Spurs (CLV +19.3pp). Bournemouth draw lean hit;
  Brentford +5.8 missed (1-1). Forward positive-edge cohort (>=+5pp picks):
  4/6 across MW1-2 — opposite sign to the 680-game backtest. NO VERDICT
  CHANGE ON n=6. PRE-COMMITTED: thermometer forward re-read at n=30
  positive-edge picks (hit rate + mean CLV vs backtest 42-49% bands).
  Consumer note unchanged.

- **PYRAMID GATE 2026-09-01: v19 REJECTED — CORRECT.** Trained on 8,061
  (4,574 league / 3,487 cup). SCOPE QUESTION ANSWERED: elo n=96 (was 27) —
  trainer universe widens with data; phase 4 shrinks to the bonus fix.
  REAL ISSUE REVEALED: rating range COLLAPSED 1368-1691 -> 1469-1532; the
  179-pt drift on team_id=8 (Arsenal) is the symptom of a near-flat table,
  not corrupted scores. Fit-dynamics diagnosis (scoping, K-factor,
  iteration depth, cup/European feed into PL ratings) = phase-4 item (a),
  Claude's, this week. Production v18. NO RE-RUN until diagnosed.
  GATE DESIGN NOTE: range compression was visible but unchecked — add a
  rating-spread guard beside the drift guard.

- **S17. Results export mislabels draw top-picks [fix-session queue; GPT
  layer caught it].** Bournemouth-Everton: true argmax = draw (0.3389 vs
  0.3383 home); match drew; grading CORRECT (hit=true, CLV vs draw close
  4.01) but export label says top_pick=home_win — label derived from
  home/away only. Fix: include draw in label logic, emit draw_prob, add
  assertion top_pick_hit == (top_pick matches result), fail loudly.

- **S14 TALLY after MW2: 20/30 games.** Matchweek under-projected ~+1.0
  goal (Chelsea 1.95->7, City 2.21->5, Liverpool 2.16->4, United 2.79->7)
  — NOT bucket-shaped yet (two confident favorites among the misses).
  GPT's "tail width at ~2 xG" framing added as a second cut at n=30.
  Routed, not built.

- **AUG-31 REVIEW VERDICT — full window (--since 2026-07-20, 509 games):**
  run_shrink_frac=0.35 CONFIRMED: mean error -0.06 +/- 0.20 (unbiased
  level). High-projection over-lean watch item CLOSED as noise: 8.5-9.5
  band -0.38 +/- 0.26 (<1.5 SE), very-high band reverts to +0.06 — no
  gradient. NEW CALIBRATION FINDING M16 — over-prob SHAPE: model over-prob
  50-60% band (n=109) realized only 40% over (+/-5%, ~3 SE below stated
  54%); 30-50% bands fine (41%, 48%); overall over-rate vs line 45.2%.
  Model's over-leans are anti-predictive, mirroring positive side edges.
  CONSUMER NOTE ISSUED: treat over_prob>50% as caution, not lean.
  PRE-COMMITTED TEST: re-read at n=200 in the 50-60% band; if realized
  over-rate still <45% -> Stage-1 backtest of distribution shape (NegBin
  dispersion / line-relative read) before any production change.
  Section-3 "normal games -0.79" noted as partly selection artifact
  (conditioning on actual band); unconditional -0.06 is the level truth.
  Section-4 market-edge screen: none, correct default.

- **AUG-31 REVIEW (forward tail, 132 joined games Aug 20-30):**
  LEDGER (1) starter effective-IP cap — CLOSED, working: capped n=28 hit
  50.0% vs 59.6% rest, worse logloss (0.689 vs 0.668) but BETTER CLV
  (-0.19 vs -0.99pp) = genuine uncertainty, no manufactured mispricing.
  LEDGER (2) bullpen swing flag — CLOSED, keep 0.30: flagged n=52 hit
  53.8% / logloss 0.696 vs 60.0% / 0.657 (flag identifies volatile games,
  as consumed by the fragile tag); CLV similar across split (-0.74 vs
  -0.88) = weight not mistuned.
  LEDGER (3) totals preview — mean +0.14 (unbiased), median -0.73,
  non-blowup -0.82 = right-skew, not bias; HIGH BAND DOES NOT STAND OUT
  (>=9.0 n=35 non-blowup -0.57; mid band -1.16 is the worse one). Watch
  item reads as noise on the tail; run_shrink_frac=0.35 reads correct.
  Full-window --since 2026-07-20 issued as the verdict.
  NEW TRACKING ITEM M15 — strong-tier under-rating: strong n=13 hit 12/13
  (92%) with mean CLV -4.2pp (market priced favorites higher; outcomes
  sided with market). PRE-COMMITTED TEST: at n=40 strong-tier games, if
  realized rate > stated mean prob by >10pp AND mean CLV < -3pp ->
  Stage-1 investigation of favorite compression in the Pythag blend.
  Otherwise nothing. Toss-ups calibrated perfectly (50.0%, CLV -0.03).

- **[ACTIVE LEDGERS — review late Aug 2026]** Three forward measurements now
  accruing, all read from export/results files: (1) starter effective-IP cap —
  games where starter_detail shows effective_ip < ip, graded vs rest (enabled
  2026-08-14, expect a trickle; multi-week horizon); (2) bullpen swing-flag
  games vs rest (tests whether the 0.30 recent-form weight is mistuned — the
  only honest test available, no as-of-date history); (3) totals-calibration
  --since 2026-07-20 — the REAL verdict on run_shrink_frac=0.35 and the
  high-projection-band watch item (daily high-band reads ran −/+/− Aug 11-13 =
  noise; stop reading dailies, wait for the --since sample).

- **Lineup strength** (batter quality, not just team aggregate)
  Sync each team's daily lineup, derive offensive power from individual batter
  stats. Probably lower impact than bullpen given team RPG already captures
  much of this. ~2-3 days. Requires API-Baseball or scraping (MLB Stats API
  doesn't expose lineup easily pre-game).

- **Wrigley wind direction** — **[SUPERSEDED by 2026-06-29 weather work]**
  wind direction + park orientation shipped as a TRACKED signal
  (park_wind.wind_effect in unused_context). Deliberately NOT wired into
  predictions: wiring is gated on a totals-specific Stage-1 pass (the
  tracking-first discipline). The remaining item is that Stage-1 test, not
  plumbing.

- **Park-pitcher interactions**
  Flyball pitchers fare worse at Coors. Real signal but small effect-size,
  hard to compute. **[DEFERRED]** — needs more season data first.

- **Temperature effect on home runs**
  Hot air = balls travel farther. ~2-3% per 20°F. Small. **[DEFERRED]** —
  add after weather wiring confirms the baseline approach works.

### Soccer

- **League coverage closure (PREREQUISITE for CL/EL predictions)**
  **[DISCOVERED 2026-05-30 on the CL final]** — La Liga, Serie A, Bundesliga,
  Ligue 1 and every non-PL league show 0 matches in the DB; only PL is
  populated. Any CL/EL match with a non-PL team applies a **-100 Elo
  "unknown league" penalty** fallback. The PSG–Arsenal final came out
  Arsenal 55.7% purely because PSG's Ligue 1 isn't ingested (PSG -100,
  Arsenal 0), while the 13-book market had PSG favorite. Confidently wrong
  on corrupted input.

  **The requirement is a CLOSURE PROPERTY, not a league list:** the set of
  ingested leagues must be a superset of every league that sources a team
  into any competition we predict. CL alone pulls 36 teams from ~15-20
  domestic leagues — ingesting only the Big Five still mis-rates teams from
  Portugal, Netherlands, Belgium, Scotland, Greece, Turkey, etc. Derive the
  required set from the competitions on the roadmap, don't enumerate
  abstractly. Bounded and self-defining.

  **But "track everything" is wrong** — a thinly-ingested league produces a
  skewed Elo and weak cross-league calibration, i.e. a confident-looking
  wrong number (worse than today's *visible* bug). So design as TIERED
  confidence, not binary:
    1. Fully rated — enough history for trustworthy cross-league Elo (Big
       Five + strong secondaries that send deep CL runs: POR, NED, maybe BEL)
    2. Lightly rated — ingested but thin → compute Elo BUT widen prediction
       variance so the model expresses doubt (pulls toward draw/coin-flip),
       not false confidence
    3. Unknown (not ingested) — fallback must be **league-average Elo +
       max uncertainty**, NOT -100. "I lack data about you" must never
       render as "you are weak." This fix is cheap and strictly correct
       regardless of what we ingest — do it FIRST, independent of the
       ingestion work.

  Note: World Cup needs national-team Elo — a SEPARATE rating pool from
  club football, not covered by league ingestion (own workstream, mid-June).

- **[FRAMING — revisit after June 7] Competition-context-aware uncertainty
  (cups vs leagues).** The model's core assumptions are LEAGUE assumptions:
  Elo accumulated over a long season, recent-form over last N games,
  calibration over hundreds of matches, home-field advantage. Cups violate
  these — and not uniformly. A "cup" is really a FAMILY of game-types, each
  breaking league assumptions differently:
    - Knockout (single elim): no regression-to-mean second chance, higher
      variance by design, often neutral venue (home-field adj is wrong),
      end-state behaviour differs (teams play 0-0 in the 80th differently).
    - Two-legged tie: aggregate scoring, managing a lead across 180 min.
    - Group stage: mini-table but tiny sample (3 games), resting once through.
    - Cross-competition entrants: teams from un-ingested leagues → the
      closure-property + tiered-confidence fallback above.
    - International tournaments: national-team Elo pool + squad continuity
      (assembled for weeks, club form doesn't transfer).
  KEY INSIGHT: don't treat "cup" as a single mode, and don't build
  competition-specific MODELS. Instead make "competition context" a
  first-class input that adjusts the model's behaviour and ESPECIALLY its
  expressed UNCERTAINTY: venue neutrality, single vs two-leg, sample-size
  driven variance widening, squad continuity. A cup match shouldn't just get
  a different Elo — it should get WIDER variance because we have less to go
  on and the format is higher-variance. Same principle as the unknown-league
  tiered-confidence fallback: when we know less, SAY less confidently. The
  World Cup underdog-path idea and this cups-vs-leagues question are the same
  question at different scales; the unifying answer is context-aware
  uncertainty, not per-competition models.
  (The World Cup underdog-path tool itself: read FAVORITE straight from the
  market, build a qualitative underdog-scenario/scouting layer on top —
  explicitly EXPLORATORY, NOT calibrated like MLB, likely a SEPARATE app so
  it never pollutes the MLB calibration discipline. 64 games = no calibration
  possible, so it must not set precedent for the core model.)

- **[SCOPED — build next session] World Cup 2026 (market-derived, walled off)**
  Feasibility confirmed 2026-06-07: API-Football (same vendor we use) carries
  it as **league id=1, season=2026**, coverage object shows `odds: true`.
  DESIGN (a "third pick" alongside mlb/soccer, walled off):
    - It IS Sport.SOCCER, but a WORLD CUP COMPETITION flagged to route to a
      MARKET-DERIVED predict path — NOT the club Elo/Poisson model. The wall
      is a competition-level routing flag, not a fake Sport enum value (World
      Cup is soccer; faking the sport would break soccer-generic logic). This
      routing is what structurally prevents the −100 unknown-league penalty:
      the club model never runs on these matches.
    - No training, no promotion gate, no calibration. Market-derived only,
      labeled "market-derived, not a model prediction" everywhere it shows.
  DECISIONS LOCKED (2026-06-07):
    1. NO winner shown when the market has none — if odds absent/thin (common
       early per API-Football's per-match caveat), show nothing. No fallback.
    2. Underdog-path layer stays MANUAL for now — qualitative matchup
       reasoning on request, zero build. (Semi-structured/metrics version is
       a later maybe, explicitly deferred.)
    3. De-vig method = simple proportional (divide out the overround). Std,
       sufficient, no need for anything fancier.
    - Skip null-team knockout fixtures until both teams qualified (API returns
      home/away_team null pre-knockout, with a source object).
  BUILD = competition ingestion (reuse soccer odds path) + proportional de-vig
  fn + routing flag + display label. ~1-2 days, no modeling risk. Bracket-sim
  (see Monte Carlo note) is the natural later add for "who reaches each round."

- **Travel & rest**
  Days since last match + competition of last match → fatigue multiplier.
  Midweek European games are known to hurt PL teams. Data we already have.
  ~half day.

- **Weather wiring into predictions**
  Heavy rain/wind reduces xG. We display it on match preview already.
  Coefficients are well-known in soccer analytics literature. ~half day per
  sport.

- **Holdout window expansion** (30 → 90 days)
  Soccer holdout is 50 matches — too small for `improve` to detect real
  signal. Bumping the window would improve calibration of model
  improvements. ~2 hours but requires a backfill of historical predictions.
  Mentioned previously, deferred for post-PL season.

- **Player form weighting** (recent vs season-average)
  Currently player power scores are season-aggregate. Hot/cold streaks
  matter. **[DEFERRED]** — effect size small relative to noise; do after
  travel/rest.

- **Positional matchups**
  Pace winger vs slow fullback gets no special treatment currently.
  **[DEFERRED]** — complex feature engineering for modest gain over existing
  XI strength signal.

- **Manager / tactics / formation**
  **[DEFERRED INDEFINITELY]** — data not available structurally; not worth
  manual curation.

### UI / presentation

- **Prediction highlights in match overview**
  Surface the 2-3 most important prediction drivers (pitcher edge, bullpen
  edge, hot/cold streak, park factor) as highlights near the top of the
  match page, rather than only inside the prediction panel lower down. Make
  the "why" visible at a glance. ~half day. Layout decision: pick the top
  drivers by magnitude and render as compact highlight chips.

- **Player props (predicted)**
  Predict individual player outcomes (pitcher K totals, batter hits, etc.)
  not just team outcomes. **[DEFERRED — needs player-level modeling]**.
  This is downstream of lineup strength + the player-level direction (see
  "Long-term direction" below). The pitcher ERA/WHIP/K9 we surface now is
  *input* to the team model, NOT a player prop prediction — props need
  dedicated per-player projection models. Pairs naturally with NFL work.

### Cross-sport / infrastructure

- **Random Forest / ensemble modeling**
  **[DEFERRED]** — interesting but premature. Three reasons:
  1. Sample size too small (~800 MLB games this season, ~4000 historical
     soccer matches). RFs typically want 5,000+ training instances per
     feature dimension to be reliable.
  2. The features an RF would use are already encoded in the structural
     model. Adding RF on the same features mostly re-derives existing math
     with worse interpretability.
  3. Loss of factor-breakdown narrative — RF is a black box vs our current
     transparent "Elo gap → xG → win prob" path.

  When to revisit:
  - End of MLB season (2+ year of data accumulated)
  - Logistic regression baseline added first as data-efficient comparison
  - Use case = "second opinion" / disagreement flagging, not replacement

- **Global temperature scaling** (calibration correction)
  Calibration diagnostic (2026-05-28) found 60-70% bins overconfident by
  11-23pp. Fixed structural causes first (missing-starter 12.3, pitcher
  double-count 12.5) rather than apply temperature.
  **RE-CHECK 2026-05-31 (173 scored, full-season export of 879 confirmed
  the same 173 have stored predictions):** 60-65% bin healed (-10.7 → -4.5pp).
  65-70% bin STILL shows -22pp overconfident on 20 games — BUT splitting by
  pitcher_anchor_mode revealed 17 of those 20 are PRE-12.5 (old `league`
  anchor). Pre/post split across all high-conf (≥60%) picks:
    • PRE-12.5 (52 games): predicted 66.6%, actual 53.8% → -12.8pp (the defect)
    • POST-12.5 (12 games): predicted 65.7%, actual 75.0% → +9.3pp (fine/under)
  CONCLUSION: the cumulative 65-70% overconfidence is largely a GHOST of the
  pre-double-count model. The 12.5 fix appears to have resolved high-conf
  overconfidence at the source. **NO temperature correction applied — would
  have corrected an already-fixed defect and likely overcorrected the
  current model.** Post-12.5 sample (12 high-conf games) is small; let it
  grow and re-check ~2026-06-07.
  **[CLOSED 2026-08-14]** — superseded by the June 14 recal clamp (60-70% band
  compression) and run-shrink; the 2026-06-29 --since read showed the current
  model no longer produces the inflated band. Global temperature scaling is
  not needed and would double-correct.

- **Logistic regression as second model**
  Lower-risk path to "multiple model outputs" than RF. Interpretable
  coefficients, data-efficient, would catch structural-model bugs by
  cross-checking. ~1 day to build, ongoing maintenance light.
  **[DEFERRED]** — pending baseball foundation work and soccer holdout
  expansion.

- **Confidence intervals via bootstrap**
  Vary inputs (ERA ±10%, form weighting ±20%) and report the resulting
  prediction band. "Home win 53% ± 8pp" tells you which calls to trust.
  ~half day. Cheaper than a second model and arguably more useful for the
  daily review workflow.

- **Tail-risk probabilities**
  We have a full score matrix already. Extracting P(blowout ≥ 4 margin),
  P(close ≤ 1 margin), P(under 5 total) is computationally free.
  ~2 hours to compute + surface in match preview.

- **Closing-line value (CLV) for spreads/totals**
  Currently 1X2 only. Extending to totals and run-line would give richer
  post-mortem evaluation. ~half day per market.

- **Doubleheader matching improvement** — **[HALF-SHIPPED 2026-07-20]**
  start-time-proximity disambiguation built with a >=1h safety guard (see
  shipped entry). STILL OPEN: confirm whether the API-Baseball odds feed
  publishes separate lines per DH game at all; if it lumps them, flag DH games
  "no reliable market context" rather than force a match. NOTE 2026-08-12: the
  rewritten Kalshi matcher time-gates on occurrence_datetime, so Kalshi prices
  DO resolve DH legs correctly — Kalshi may end up the more reliable market
  source on DH days.

- **Nightly scheduler**
  Automated daily pipeline (sync-matches → evaluate → improve → predict)
  instead of manual CLI invocations. **[DEFERRED]** — single-user app, the
  manual flow is fine and gives Anthony a checkpoint for review.

- **Timezone handling**
  All times currently in UTC display. Could allow override to ET / local
  via cookie. **[DEFERRED]** — convenience improvement, not blocking.

---

## Modeling philosophy notes

**Why structural beats statistical at our scale:** the structural model encodes
real domain knowledge (negative binomial for runs, Poisson for goals, park
factors as multipliers). It needs less data because the math constraint does
the work data would otherwise need to do. A random forest given 800 MLB games
to learn 15+ features can't recover those constraints from raw outcomes.

**Where ML will eventually win:** when we have enough data (2+ years), and the
question becomes about edge cases the structural model can't articulate
(e.g. specific batter-pitcher matchup patterns that don't fit a multiplier).

**Where ML never wins for us:** the narrative / factor breakdown. We need to
say "model picked Brentford because Liverpool has 8 injuries, weak XI strength,
and recent form is mediocre." An RF can't tell you that — feature importance
is global, not per-prediction.

---

## Long-term direction: player-level modeling

**The vision (Anthony, 2026-05-28):** progress from team-level predictions
to player-level predictions over time. Get to the point where the model
reasons about individual players — their form, matchups, and contribution —
not just team aggregates. Player props become a natural output. American
Football (starting later in 2026) is a primary motivation, since NFL is
heavily player-driven.

**Sequencing principle (agreed):** exhaust team-level signal FIRST. Go to
player-level when we hit a demonstrable bottleneck — when two teams with
similar aggregates have genuinely different expected outcomes that the team
model can't distinguish. Don't add player granularity speculatively; add it
where the data supports it AND the team model provably falls short.

**Why this ordering is right:**
- Team aggregates capture most of the signal cheaply (run profiles, bullpen
  ERA, Elo, XI strength). The marginal player-level lift is real but smaller
  than the initial team-level lift.
- Player-level means more parameters and less data per parameter — higher
  overfitting risk. Doing it too early makes the model WORSE.
- The bottleneck is real though: team models blur individual matchups. Two
  rotations with identical season ERA can have very different expected
  outcomes based on who's actually pitching to whom.

**Shared architectural backbone:** MLB lineup strength, soccer player power
ratings (already exist, Phase 6a/6b), and eventual NFL player modeling all
want the same thing — a per-player projection layer that FEEDS the team
prediction rather than replacing it. Build that backbone once, well; sport-
specific player models sit on top. The team structural model stays as the
spine; player-level adjusts it.

**Sport-specific notes:**
- **MLB**: next step is lineup strength (batter quality) — already in backlog.
  Then batter-vs-pitcher matchup, then player props (K totals, hits, etc.).
- **NFL** (later 2026): strongest case for player-level (one QB injury swings
  everything) BUT the hardest — only 17 games/season means severe data
  sparsity per player. Player-level matters most here and data scarcity hurts
  most here. Will likely need heavy priors / position-level pooling rather
  than pure per-player fitting. Separate workstream when NFL season approaches.
- **Soccer**: player power ratings already feed XI strength. Extensions
  (player form weighting, positional matchups) are smaller increments.

**[DEFERRED — long-term direction, not a single phase]** — this is the
through-line for many future phases, revisited as team-level hits ceilings.

---

## Monte Carlo simulation as a prediction engine

**[FRAMING — not a near-term build]** Idea: run match/tournament simulations
to capture variance, path-dependence, and tail outcomes. Worth doing for
SPECIFIC things, NOT as a replacement for the current model.

Key reframe — simulation is not a new prediction philosophy, it's the right
ENGINE for two things already on the roadmap:

1. **Bracket / tournament simulation (cheap, high-value, near-term-able).**
   "P(team reaches semifinal)" is a tree of conditional matches — nearly
   impossible analytically, natural for simulation. Crucially it can be
   driven by MARKET-implied per-match win probs (free), so it needs NO
   event-level model. This is the cheap entry point and pairs directly with
   the World Cup underdog-path idea. Build this FIRST if simulation happens.

2. **Per-event (per-at-bat / per-possession) simulation = the DELIVERY
   MECHANISM for player-level modeling.** Not a separate idea: once player
   projections exist, simulating at-bats/possessions is the natural way to
   aggregate them into game outcomes WITH correlation (pitcher's bad night +
   bullpen usage + run total are linked — closed-form can't do this well).
   So this is downstream of the player-level direction above, not independent.

IMPORTANT CAVEATS (why NOT to rush it):
- The current NegBin/bivariate-Poisson model is ALREADY an analytic
  simulation — it integrates over an outcome distribution. Explicit sim only
  adds value if the PER-EVENT model captures something the per-GAME model
  can't. Simulating from the same team-level rates = same answer, 1000x the
  compute. "Garbage in, chaos out."
- Sim produces outcome DISTRIBUTIONS, not narratives. The "narrative" (how an
  underdog wins) is something a human reads into a cluster of sims — for
  narrative/scenario output, the qualitative underdog-path analysis is more
  direct. Don't expect sim to generate stories.
- Compute is NOT the constraint (a few thousand sims/game = seconds). The real
  cost is building a credible event-level model — which is the deferred
  player-level work. So sim's deep version is gated on player-level anyway.

Sequencing: (a) bracket-sim is the only near-term-reasonable piece, and only
if World Cup work happens; (b) match-level sim waits for player-level modeling
and is really part of that workstream. Neither precedes MLB calibration
stability.

---

## How to update this file

When shipping an item:
1. Move it to a "Shipped" section at the bottom with a one-line summary and date
2. Note any followup work created in the same session

When adding a new item:
1. Place under the relevant sport/cross-sport section
2. Mark **[DEFERRED]** with reason if not immediate
3. Include rough effort estimate

When user (Anthony) brings up an idea that's not the current focus, capture
here rather than push back on it. The conversation is the source of truth;
this file is the persistence layer.

---

- **2026-06-23** — Run-input regression-to-mean (run_shrink). Post-blend
  re-check (`recheck`, n=65): blend WORKED (disagreement gap -20pp→-7.8pp), no
  over-correction, but a separate defect remained — high-offense-PROJECTION
  favorites overconfident (-8.1pp at n=85). Ruled out three mechanisms:
  stale RPG (cancels in win-prob), recency overshoot (hot≈steady in data),
  fixed dispersion (wrong sign in math). The `offense-mechanism` second cut
  found it COMPOUNDS: fav-offense-high alone -6.2pp, opp-weak alone -9.6pp,
  BOTH -23.5pp (n=12), both-normal +7.3pp. home_xr=(RS*opp_RA)/league is a
  PRODUCT of two regression-prone inputs; midseason the small-sample shrink
  (n/(n+10)) is ~off so extremes multiply un-regressed. FIX: regress RS/RA
  toward league mean (4.4) before multiplying, frac=0.25 (DERIVED from
  luck/talent variance split ~0.41 reliability, defaulted conservative, NOT
  fit to the n=12 cell). Leaves average inputs untouched (both-high p_home
  0.754→0.702, both-normal 0.533→0.528). Config-driven run_shrink_enabled/
  frac/mean, DISABLED by default, reversible. Three-way converged (calibration
  + post-mortems + mechanism). CAVEAT: killer cell n=12, magnitude noisy —
  measure 1-2 wks, watch normal games don't break.
- **2026-06-29 (Bucket 1: total-gap + bet-suitability fields)** — Surfaced
  explicit totals-edge data the card was previously inferring from over-prob.
  Added to build_card(): model_total (proj_home+proj_away), market_total,
  total_gap (signed), total_side, bettable_total_edge (bool). The bettable test
  uses a CUSHION that scales with line height (_total_gap_cushion: 9.5+→0.75,
  8.5→0.85, 8.0→1.00, ≤7.5→1.20) because low lines need a bigger gap (one-run
  variance dominates, each run is a larger share). Derived from 6/28 thin-under
  losses (BOS/NYY Under 8.0 gap −0.23; CLE/SEA Under 7.5 gap −0.36 — both lost,
  both over-ranked). New rule correctly separates them: both losers flagged
  "thin lean", both winners (STL/MIA −1.06, SD/LAD −1.00) clear as bettable.
  Also added bet_suitability + recommended_market metadata (item 10) — derived
  PURELY from existing flags (no new judgement), so "model likes it" can't
  silently become "bet it". A totals-stronger game with thin gap now gets a
  caution flag. Surfaced in CLI card render + card.html. CRITICAL FRAMING
  UNCHANGED: cushion gates "worth tracking", NOT "+EV" — CLV still decides edge.
  Thresholds are module constants in card.py.

- **2026-06-25 (card UI + shared logic)** — Surfaced the card in the web UI.
  Refactored card logic OUT of the CLI into src/walters/card.py `build_card()`
  — ONE source of truth so CLI and web can't drift (the exact drift bug hit
  twice: export computed flags one way, card read DB another). CLI `card` and
  new web route /card both call build_card(). Added src/web/routes/card.py,
  templates/card.html (Tailwind ladder + per-game fact cards, edge color-coded),
  registered in app.py, nav link (baseball only). Same honest-flags design:
  disagreement = caution not edge. Thresholds (MARKET_DISAGREE_PP=3.0,
  BULLPEN_SWING_CAUTION=1.5, BETTABLE_MIN_PROB=0.525) are module constants in
  card.py — change once, both surfaces update.
- **2026-06-25 (card command)** — Built `card`: deterministic daily card
  assembler (confidence ladder + per-game fact blocks + honest flags). Replaces
  the manual assembly the external betting model did. KEY DESIGN: FACT
  ASSEMBLER, not rationale generator — surfaces numbers the model already
  computes (proj runs, SP ERAs, bullpen ERA+swing, recent RS/RA, market edge,
  totals line/over-prob, tier) and tags cautions by EXPLICIT rules (|market
  edge|≥3 → disagreement caution; bullpen swing ≥1.5 → not a parlay anchor;
  close-game → single only; starter cap; sub-52.5% → prediction-only). Ranks by
  a transparent sort score (NOT a probability, never feeds predictions).
  CRITICAL: market disagreement flagged as CAUTION not EDGE — does NOT
  manufacture "dog value" like the external model (won't present a model-below-
  market dog as +Xpp value; that's the anti-predictive disagreement the blend
  corrects). If CLV (July review) proves disagreements have closing-line value,
  flip those flags caution→opportunity THEN, with evidence. Interpretation
  human-in-the-loop. Read-only; reads live DB, computes edge like
  market-alignment.
- **2026-06-24 (CLV infrastructure)** — Built odds-snapshotting for closing-
  line-value tracking, the measurement that speaks to the income question (does
  the model beat the CLOSE, not just calibrate). Context: model is well-
  calibrated but has NO demonstrated edge over market — the blend exists because
  its disagreements were anti-predictive — so before any betting/slate/pipeline
  tooling, we need to know if real edge exists. CLV is the test. Constraint:
  odds aren't up much before the morning run, one sync/day, so open-vs-close
  needs scheduled captures. Design (Anthony's call): 4 captures/day at 8/12/4/8
  local (catches day + night games with lead + near-close), MARKET-ONLY
  snapshots (model joined at analysis time, keeps market record independent),
  de-vigged consensus. Built: OddsSnapshot table (append-only); `capture-odds`
  (odds-only sync + de-vig write, does NOT predict/disturb live preds);
  `clv-report` (per finished game: first→last move on model's pick, toward/away
  tally — the key signal); scripts/setup_clv_capture.sh (4 launchd jobs,
  catch-up-on-wake). EXPECTATION: first ~2 wks just establishes if a signal is
  readable; movement is noisy, disagreement-games subset is what matters.
  Honest framing held: likely outcome is "no edge, calibrated thermometer not
  income engine" and we should be willing to find that. Parlays flagged as
  HIGHER variance / lower repeatability than singles. NOTE: capture-odds auto-
  creates odds_snapshots on first run.
- **2026-06-24** — Totals-unavailable fix (from 6/23 betting post-mortem, the
  Coors failure). When NO real market total exists, the model was falling back
  to 8.5 AND still presenting it as actionable (Rockies/Red Sox flagged
  stronger_expression=total, over_prob 63.33%, on a phantom 8.5). Fix:
  predict_game sets totals_available=False when no market line passed; MLB
  predict path stores over_under_line/over_prob/under_prob = None then; export
  surfaces totals_available and side-vs-total expression can't pick "total"
  when over_prob is None. "Unavailable" instead of a phantom line. No schema
  change (null line = unavailable signal). Sides unaffected. NOTE first
  run-shrink-live graded slate (6/23): raw sides 10-5, actionable 4-2, and per
  Anthony the 10-5 came WITHOUT fake 65-70% favorites — right SHAPE (edge
  intact, confidence compressed), but n=15 not significance; ~2-wk recheck is
  the real test. Market-total fix validated live — killed 3 bad totals
  (NYY/DET under 7.5→final 7, CLE/CWS under 7.5→2-1, MIL/CIN over 9.5→2-0).
- **2026-06-23 (totals session)** — Fixed the hardcoded-8.5 over/under bug:
  predict_game now takes market_total_line and computes O/U against the real
  book total (median of synced TOTALS odds per match), falling back to 8.5 only
  when no line exists. Confirmed live — export lines now span 7.5/8.0/8.5/9.5
  per matchup instead of uniform 8.5. ALSO: investigated the RPG-lag "totals run
  low" theory and CLOSED IT as a non-issue — built `totals-check`, which showed
  projected total − actual = −0.12 mean / +0.39 median over n=247 (unbiased),
  and O/U calibration +1.1pp. The league_runs_per_game 8.83-vs-9.3 "lag" is a
  NORMALIZER (denominator), self-consistent with the team rates it divides;
  raising it would LOWER projections and INTRODUCE a bias where none exists.
  Bumping RPG via set-config was the WRONG fix (sign backwards) — measurement
  caught it. RPG lag affects nothing measurable in totals or win-prob; do NOT
  chase it again. New diagnostic: `totals-check` (projected vs actual totals +
  O/U calibration). Caveat: O/U calibration was graded on old all-8.5
  predictions; re-run totals-check after ~2 wks of real-line predictions for a
  true read.
- **2026-06-18** — Market-blend (the real fix for the post-recal -13pp).
  Anthony noticed the recal only RELABELED bad 60-70% picks into 55-60% (same
  wrong games, lower bucket) and suggested more aggressive recal. Testing
  first (calibration-market command, using clv = model prob − market de-vigged
  prob, NOT the never-populated best_value_edge_pct) showed it would've been
  the WRONG lever: post-recal split (n=56) is +5pp when model AGREES with
  market (calibrated!), -20pp when it disagrees, -35pp on >8pp disagreements.
  The defect is MISDIRECTION not miscalibration — the model's edge over the
  market is anti-predictive in this range (it's missing market info:
  scratches, weather, sharp money), so compressing confidence can't fix a
  wrong-SIDE problem. FIX: market blend p=(1-w)·p_model+w·p_market, which
  self-targets disagreement (no-op when model≈market). Conservative w=0.5
  PRESERVES the model as an independent voice — deliberately does NOT collapse
  to market (Anthony: "I'd hate to just be picking the market every time" —
  the goal is still to catch games the market gets wrong). At w=0.5 the model
  keeps its side in ~all realistic cases, only moderating confidence; flips
  need w>0.88. Config-driven (market_blend_enabled/_w), DISABLED by default,
  enable via set-config. OPEN QUESTION once blend proven: does it make recal
  redundant (both pull confident picks down)? Decide with data. SEPARATE
  future project (needs n>>31): find a signal distinguishing the model's GOOD
  disagreements (real market errors) from bad ones — that's how you actually
  hunt market mistakes vs just discounting all disagreement.
  code defaults. Re-check (n=355): overconfidence entirely in 60-70% (-11.6 /
  -23.8pp); 50-60% and 70%+ calibrated. Ruled out FOUR mechanisms first
  (bullpen-swing, series position [Anthony's hypothesis — gradient ran
  BACKWARDS, game 1 worst], home/road, run environment) — all uniformly bad,
  so it's a band-shape problem with no hidden variable. First fix attempt (a
  single smooth shrink across the whole 60%+ range) was wrong: it dragged the
  calibrated 70%+ band down too, because 65-70% (wins 44%) and 70%+ (wins 76%)
  need to move in opposite directions and no single monotonic curve does that.
  Anthony pushed back on the over-engineering; the resolution is a CLAMP:
  recalibrate ONLY [0.60,0.70) — compress it into [0.555,0.60) — and leave
  50-60% and 70%+ as exact identity. Small discontinuity at 0.70 is immaterial
  (negligible mass there). Conservative target: maps 67% -> ~0.59, NOT the raw
  noisy 43.6% (n=39) — corrects real overconfidence without overfitting the
  thin extreme cell or inverting picks. Config-driven (recal_enabled/lo/hi/
  target), tunable/reversible via set-config, applies to favorite side with
  underdog as complement. NOTE: code default now enabled, but the LIVE model
  reads STORED config — activate on production v2 via set-config (see below).

- **2026-06-14 (earlier)** — Close-game flag, calibration-series command (4
  slices), market-agreement slice pending edge_pct. [see entries below]

- **2026-06-13** — Close-game transparency flag (reporting, NOT calibration).
  The NegBin model already builds the full score matrix but discarded margin
  info. Now computes `p_one_run` (P game decided by exactly one run) and
  surfaces `close_game_flag` when a confident pick (≥58%) sits on a high
  one-run-mass game (≥0.185). Motivation (Anthony, 6/13): a 63% pick that
  loses a close 8-5 game isn't miscalibrated — 63% is supposed to lose 37% —
  but it IS worth highlighting as high-variance/could-tip. Surfaces that
  texture WITHOUT changing the probability (whether 63% itself is right is the
  calibration re-check's job, answered in aggregate not per-game). Threshold
  0.185 is a median-ish default; tune CLOSE_GAME_ONE_RUN_MIN after real slates.
  Persisted in factor_breakdown + exported. Baseball only (soccer untouched).

- **2026-06-08 (pt 3)** — Completed the season fix: `_apply_match_updates`
  never updated `season` on existing rows, so the pt-2 fix didn't correct
  already-stored matches on re-sync (they stayed "2026/27" despite the
  adapter now producing "2026" — diagnostic confirmed all 72 WC rows correct
  on status/date/external_id, ONLY season wrong). Fix: the update path now
  rewrites season when the adapter reports a different non-empty value. A
  re-sync of WC now corrects the rows. (General fix — applies to any re-sync
  that needs to repair a season.)

- **2026-06-08 (pt 2)** — Fixed single-year season-format bug blocking World
  Cup (and any international tournament). `_parse_fixture` stamped EVERY
  fixture's season as a two-year league span ("2026" → "2026/27"), correct
  for domestic leagues but wrong for single-year tournaments. Result: 72 WC
  matches got stored under "2026/27" while sync-odds/predict-worldcup query
  "2026" → silent zero-match (looked like missing odds; was a season
  mismatch). FIX: `_SINGLE_YEAR_SEASON_CODES` set (WC, UEFA_EURO, WCQ_*,
  FRIENDLIES_INT) store the plain year; leagues keep "YYYY/YY". Request side
  (`_season_to_year`) was already fine. NOTE: existing mis-stamped rows need a
  re-sync to correct (sync-matches re-run after the fix).

- **2026-06-08** — World Cup core (MARKET-DERIVED, walled off) — LIVE. New
  self-contained `src/models/worldcup.py` (imports NOTHING from the club Elo/
  Poisson model — the wall is physical) + `cli.py predict-worldcup`. For each
  scheduled WC (competition WC = API-Football league 1) match it de-vigs the
  1X2 bookmaker odds (simple proportional) into honest H/D/A probabilities and
  reports the market favorite. Locked rules all implemented & unit-tested:
  (1) NO winner when market absent/thin → returns None, never guesses;
  (2) null-team knockout fixtures skipped; (3) proportional de-vig. Output
  (console table + exports/worldcup_<date>.json) labelled "market-derived,
  not a model prediction" throughout. Underdog-path stays MANUAL (no build).
  STILL TODO (deferred, not blocking Thursday start): match-view UI
  integration (currently CLI+JSON only); a daily sync step for WC odds.

- **2026-06-06 (pt 2)** — Made the home-field fix actually LIVE + found a
  config-architecture issue. The pt-1 change (lowering DEFAULT_HOME_RUN_BOOST)
  did NOT affect the production model: BaseballConfig is frozen into each
  model-version's stored `parameters` at train time, and predictions read
  that frozen dict — so a code-default change only affects newly-trained
  versions, which the log-loss promotion gate keeps rejecting. Production was
  still predicting with 0.15 (confirmed: 6/6 slate avg home prob still 51.0%).
  FIX: added `cli.py set-home-boost --value 0.08` to update the production
  version's stored baseball_config.home_run_boost IN PLACE (reversible via
  --value 0.15; keeps an audit trail in params.manual_config_edits). Also now
  record home_run_boost in prediction factor_breakdown (was missing → showed
  None). To activate: run set-home-boost then re-run predict.
  **[ARCHITECTURE FLAG — see backlog]** the config-freeze + log-loss-only
  promotion gate will block ANY calibration fix (calibration ≠ log-loss), not
  just this one. Needs addressing before relying on more config changes.

- **2026-06-06** — Home-field advantage recalibration (MODEL CHANGE, behind
  config + revert). June 7 calibration (251 games) overturned last week's
  read: post-12.5 high-conf is STILL -12.8pp overconfident (identical to
  pre-12.5) — the double-count fix did NOT resolve high-conf overconfidence;
  last week's +9.3pp was small-sample noise (12 games). Investigation found
  the real driver: HOME picks overconfident (-4.5pp overall, -13pp high-conf)
  while AWAY picks calibrated (+0.1pp); model implied 51.7% home win rate vs
  49.1% actual. Root cause = home_run_boost too large (0.15) for 2026's
  shrunken home advantage. FIX: home_run_boost 0.15 → 0.08. Revert: set back
  to 0.15 (PRIOR_HOME_RUN_BOOST constant kept; recorded per-prediction via
  cfg.as_dict in factor_breakdown for pre/post analysis). HONEST STATUS: this
  is correct and addresses the CAUSE of the home/away asymmetry, but is a
  MODEST correction (~0.9pp on avg game, ~0.8pp on strong home favorite) —
  does NOT fully close the -13pp high-conf gap alone. Residual overconfidence
  remains (high-total games -14.4pp, big market-edge games -12.6pp — likely
  separate structural causes still to find). Bullpen-swing was NOT the main
  driver (only ~6 of 45 overconfident 60-70% games had a swing).
  NEXT: (a) the empirical piecewise upper-range shrink as a complementary
  safety net for the residual (see below), (b) investigate high-total &
  market-disagreement overconfidence for their structural causes.

- **2026-06-05** — Bullpen recent-form swing flag (reporting only, NO
  probability change). Surfaces predictions that lean on a large bullpen
  recent-form swing (>=1.5 ERA divergence between 10-day recent and season).
  Export gains `bullpen_swing_flag` + `max_bullpen_swing` (JSON + CSV); match
  view gets an amber "⚑ Bullpen recent-form caution" badge. Verified: fires
  on 6/4 Brewers 74% (Giants pen 6.37 vs 4.09 = 2.28 swing, the slate's worst
  miss) and catches 15/173 historical predictions — the same set behind the
  finding below. WHY: diagnostic on 2026-06-05 found big-swing predictions
  overconfident — predicted 59.6%, actual 40.0% (-19.6pp; -13.3pp on 13
  post-12.5 games, so a LIVE current-model issue, not a pre-12.5 ghost).
  Mechanism: 10-day bullpen window (~30-40 IP) is noisy; a 2+ run divergence
  is often small-sample noise that mean-reverts, but 12.4 weights it 30%.
  Likely contributor to the 5-day log-loss rise (more divergent windows
  accumulate as the season goes). Flagging now; model fix DEFERRED (below).

- **2026-06-02** — Starter-aware tier cap (label coherence, NO probability
  change). A pick with an unknown/null starter is now capped at "lean" tier
  even if its post-shrink probability clears 60%. Surfaced as
  `tier_capped_by_starter` in the export and an amber "⚑ starter
  unconfirmed" badge in the match view. Rationale: follows directly from
  12.3's premise (unknown starter = less trustworthy); calling such a pick
  "strong" contradicted that. Verified on 6/1 slate: Reds 63% and Mariners
  62% (both unknown-starter) dropped strong→lean; all confirmed-starter
  strong picks unchanged. NOTE: deliberately did NOT apply the post-mortem's
  statistical downgrade (lowering the probability further) — only n=2
  confident unknown-starter games exist in history, far too thin to justify
  a probability change. This is purely a labeling fix.

- **2026-06-01** — Reporting clarity (NO model change): (1) confidence tiers
  — every prediction labeled toss-up (<53%, not actionable) / lean
  (53-60%) / strong (60%+), surfaced in export JSON+CSV and as a match-view
  badge. Lets post-mortems separate actionable picks from coin-flips
  (5/31 was 12-3 overall but 10-1 on actionable picks). (2) Side-vs-total
  expression signal — flags when the model's total conviction (|over_prob
  -0.5|) exceeds its side conviction by ≥8pp, i.e. "the real read is the
  total, not the side" (the recurring Coors pattern). Both derive from
  probabilities the model already produced; thresholds in preview.py are
  tunable. Calibration unaffected.

- **2026-05-29** — Phase 12.5: fixed pitcher double-count. The opposing
  team's runs_allowed_per_game already encodes their pitching, but the
  pitcher ERA multiplier was ALSO anchored to flat league ERA — counting
  pitching twice and inflating confidence on pitching-edge games (likely
  contributor to the 60-70% overconfidence the calibration diagnostic
  found). Now the multiplier anchors to the team's own RA, so only the
  deviation of this start from the team norm adjusts runs. Damping lowered
  0.5 → 0.35 to match the tighter anchor.
  **REVERT PATH** (if calibration re-check shows this hurt): in
  BaseballConfig set `pitcher_anchor_mode="league"` and
  `pitcher_damping=0.5` — exactly reproduces pre-12.5 behavior. Anchor mode
  is recorded per-prediction in factor_breakdown for A/B traceability.
  **VALIDATE**: re-run `cli.py calibration --sport mlb` in ~3-5 days; the
  60-70% bins should move toward calibration without the 50-60% bins
  degrading. If 60-70% improves → keep. If it overcorrects (60-70% now
  UNDERconfident) → raise damping toward 0.42. If worse → revert.
- **2026-05-28** — Phase 12.4: recent bullpen form. sync-bullpen-stats now
  pulls a rolling 10-day relief window alongside season aggregate; predict
  blends them 70/30 (effective bullpen ERA). Captures a bullpen caving or
  locking in that the season number is too slow to reflect. Makes daily
  bullpen sync meaningful. Narrative flags caving/locked-in when recent vs
  season diverges ≥1.0 ERA. Sync logs the divergence too.
- **2026-05-28** — Phase 12.3: missing-starter uncertainty. When a starter
  is unknown (null or reliever-as-opener), win probabilities are shrunk
  toward 50/50 (0.88 one side, 0.76 both) instead of silently treating the
  missing data as league-average. Addresses overconfidence found in the
  60-70% calibration bins. Also added `calibration` CLI command (reliability
  table + ECE + temperature suggestion) as a read-only diagnostic.
- **2026-05-27** — Phase 12.2: bullpen quality wired into MLB predictions.
  New `bullpen_season_stats` table; sync-bullpen-stats CLI command;
  effective_team_era blends starter (61%) + bullpen (39%) at predict time.
  Surfaces `home_bullpen_era` / `away_bullpen_era` in factor breakdown +
  narrative.
- **2026-05-26** — Phase 12.1: recent-form weighting on MLB team run profiles
  (70% season / 30% last 10 games). Surfaces season vs recent in factor
  breakdown; narrative flags cold/hot streaks when |delta| >= 1.0 R/G.
- **2026-05-25** — Park factors for MLB (Coors 1.21, Petco 0.91, etc.) with
  venue name aliases (Camden Yards, Rate Field). Wired through
  `FactorAdjustment` into predict_game. Narrative surfaces for extreme parks
  only.
- **2026-05-25** — Reliever-as-starter filter: pitchers with 0 games started
  are treated as neutral ERA in predict to avoid using bullpen ERA inflation.
- **2026-05-24** — Export tool with auto-status filter (past = finished,
  future = scheduled, today = all).
- **2026-05-24** — Prediction export CLI (JSON + CSV formats).
- **2026-05-23** — MLB probable pitchers switched to schedule hydrate endpoint
  (1 batch call per date vs 30 per-game calls). St. Louis name normalization
  fix.
- **2026-05-22** — Phase 11: pitcher ERA wiring into MLB predictions; CLV
  tracking on PredictionOutcome.
- **2026-05-22** — API-Baseball integration for MLB odds (filled the MLB Stats
  API gap).
- **2026-05-21** — Phase 10: source column on Odds for multi-provider coexistence.
- **2026-05-20** — Phase 9: match preview (form, H2H, weather, narrative,
  pitcher panel, starting XI).
- **2026-05-19** — UI clarification work for value edges vs upcoming fixtures
  vs most-likely-score (resolving the Liverpool-Brentford apparent
  contradiction).

- **2026-06-29 (Bucket 2 tracking: umpire instrument)** — Started the "track,
  don't feed" data-collection layer. Added UmpireGame table (umpire_games,
  append-only, unique by source_game_id), adapter.get_game_umpire_environment()
  (reads plate ump from boxscore `officials` + run/K/BB from teamStats —
  defensive, degrades to None), and CLI `sync-umpires` (--backfill seeds the
  season, --recent tops up 3d; calls init_db to create the table) +
  `umpire-report` (per-ump R/G vs league, ALWAYS shows n, flags small-n as
  noise). NOTHING feeds the model — pure instrument, same pattern as
  OddsSnapshot/CLV. Caveat baked into report: ~25-30 plate games/ump/season →
  useless until large n. Next in chain: weather table, bullpen/starter tracker,
  then prediction-context snapshot that freezes all unused signals onto each
  prediction (Anthony's key idea) + validation report scoring which unused
  signal moves results. See docs/bucket2_tracking_plan.md.

- **2026-06-29 (Bucket 2 tracking: weather instrument)** — Added GameWeather
  table (game_weather, append-only) + `capture-weather` command. KEY FINDING
  reconfirmed: weather was DISPLAY-ONLY (src/web/weather.py powers a UI panel;
  model never saw it). capture-weather reuses the existing Open-Meteo client +
  venue coord/roof map (already complete for MLB) to snapshot temp/wind/precip/
  condition near first pitch into a frozen record. Indoor venues recorded with
  roof_state rather than dropped. GAP: fetch_weather() exposes wind SPEED but
  not DIRECTION (out/in to CF is the real totals driver) — wind_dir_deg column
  reserved (None for now), add when we extend the Open-Meteo call. Nothing feeds
  the model. Run near first pitch; could add to launchd later. Chain remaining:
  bullpen/starter usage tracker → prediction-context snapshot freezing all unused
  signals onto each prediction + validation report.

- **2026-06-29 (Bucket 2 tracking: bullpen/starter usage instrument)** — Added
  PitcherAppearance table (pitcher_appearances, append-only, unique by
  game+pitcher) + adapter.get_game_pitcher_appearances() (per-pitcher
  pitches/outs/starter-flag from boxscore players block) + `sync-appearances`
  (--backfill seeds season, --recent last 5d) + `bullpen-availability` report
  (per-team relievers used / heavy outings / back-to-back arms, last N days,
  DERIVED at read time from raw appearances). Stores RAW appearances, not a
  computed gassed/available flag, so the rule is tunable later. Serves the
  depleted-bullpen-favorite hypothesis both forward (this tracker) and
  retroactively (diagnostic over these rows once backfilled). Nothing feeds the
  model. NOTE: season-aggregate bullpen ERA endpoint already existed but can't
  give per-game usage — this is the new pipeline.
  CHAIN STATUS: umpire ✓, weather ✓, bullpen/starter ✓ — NEXT is the payoff:
  prediction-context snapshot (freeze all unused signals onto each prediction at
  predict time) + validation report (score which unused signal moves results).
- **2026-06-29 (FOLLOW-UP queued, Anthony approved): wind direction + stadium
  orientation.** Extend Open-Meteo call to pull wind_direction_10m; add per-park
  field orientation (home plate→CF bearing) so we can compute wind out/in/cross
  relative to the field — the actual totals driver (speed alone is ambiguous).
  Fill the reserved game_weather.wind_dir_deg. Do as part of making weather a
  real totals input (post-CLV).

- **2026-06-29 (bullpen hypothesis: retroactive diagnostic)** — Built
  `bullpen-diagnostic` (src/walters/bullpen_diagnostic.py) to test Anthony's
  "depleted bullpens → overrated favorites" hypothesis on HISTORICAL data
  before building any feature. For each graded favorite-prediction, reconstructs
  the favorite's bullpen state in the prior N days (reliever appearances + heavy
  outings from pitcher_appearances) and compares mean predicted win-prob vs
  ACTUAL win-rate, bucketed rested vs depleted (median + tertile splits).
  Hypothesis supported ONLY if depleted favorites show a more-negative gap.
  Honest gating: "supports" message requires ≥4pp difference AND n≥60, with
  small-sample + multiple-cut-fishing caveats printed. Read-only. This is the
  aggressive-but-disciplined move — test the sharp idea on existing data now
  rather than wait weeks for the forward tracker. Outcome will decide whether
  bullpen availability earns a feature build.

- **2026-06-29 (RESOLVED — bullpen taper REJECTED, run-shrink VALIDATED post-ship)**
  Chased the "depleted bullpens → overrated favorites" hypothesis to ground with
  data. (1) bullpen-diagnostic: depleted-vs-rested favorite gap was −2.5pp and
  NON-MONOTONIC across tertiles (low −3.7, mid −6.4, high −4.6) → noise, not a
  causal effect. (2) calibration-deep full history: overconfidence was REAL but
  localized to the 60-70% bands (−10.9pp, −26.0pp). (3) calibration-deep --since
  2026-06-23 (run-shrink era, n=84): the 60-70% bands are now nearly EMPTY (n=2)
  — the current model no longer PRODUCES inflated favorites; 50-55% (+1.7pp) and
  55-60% (−0.6pp) are well-calibrated, and big-swing post-shrink is +2.4pp
  (n=30, if anything under-confident). CONCLUSION: the overrated-favorite defect
  was the PRE-run-shrink model; run-shrink already fixed it. Do NOT build a
  bullpen taper (would push calibrated games under water). Do NOT mine the old
  −26pp band — it's a ghost of old versions. Run-shrink validated on independent
  post-ship data (directional at n=84; confirm at July review). The tracking
  instruments (umpire/weather/bullpen/starter) remain as append-only data
  accruing toward the prediction-context experiment — NOT to be fed into a model
  that currently shows no defect to fix.

- **2026-06-29 (prediction-context: unused signals ride alongside predictions)**
  Built src/walters/prediction_context.py build_unused_context() + wired into
  export. Each exported prediction now carries an `unused_context` block:
  weather (from game_weather), plate_umpire (+ that ump's tracked R/G and n),
  bullpen_availability (home/away relievers used / appearances / heavy outings
  in prior 3d, derived from pitcher_appearances). Every block stamped
  `used_in_model: false` with a _note that these are tracked/unvalidated and NOT
  in the model's probability — so the betting layer can SEE what we compute vs
  what the model uses, and factor them in at its own discretion. Joined at
  export time from the tracking tables (batched, no N+1); wrapped in try/except
  so context never breaks the export. NOTHING changed in the model. This is the
  bridge that makes the trackers visible without feeding them in. NEXT (the
  payoff): validation report scoring which unused signal correlates with model
  misses on frozen data — that's how a signal earns its way INTO the model
  later, with evidence + baseline, rather than being force-fed into a currently-
  calibrated model.

- **2026-06-29 (weather FINISHED: wind direction + park orientation)** — Closed
  the weather gap. (1) fetch_weather() now requests wind_direction_10m and
  returns wind_dir_deg. (2) capture-weather now persists wind_dir_deg (was
  None). (3) New src/walters/park_wind.py: PARK_CF_BEARING table (home-plate→CF
  bearing per park, from public orientation refs, approximate ±10-15°; domed
  parks omitted) + wind_effect() classifying wind as out/in/cross with the
  component mph along the plate→CF axis (the number a totals model wants).
  Convention handled carefully: Open-Meteo gives wind FROM-direction; "out" =
  wind from behind the plate. Verified: Wrigley S-wind→out 13mph, N-wind→in,
  E-wind→cross (matches the famous Wrigley wind behavior). (4) unused_context
  weather block now carries wind_effect{component,out_mph,label,approx}. Still
  used_in_model: false — this makes weather a PROPERLY-SHAPED signal for the
  later validation/feature step, not an input yet. Bearings are approximate;
  refine per-park from satellite if weather ever proves a real edge. Web panel
  shows speed only (effect not surfaced in UI — data-layer focus).

- **2026-07-02 (blowup-probability field: p_blowup)** — Built the one genuinely
  useful idea from the 6/30 betting-model audit. p_blowup = P(either team ≥ 7
  runs), read directly off the model's existing NegBin score distribution (the
  same score_matrix that already yields over_prob/p_one_run) — so it's a new
  OUTPUT, not a new input; the model's probabilities are unchanged. Threads
  through all layers following p_one_run's exact path: computed in
  models/baseball.py predict_game (marginal-tail formula, verified identical to
  matrix read), stored in factor_breakdown at training, surfaced in export as
  prediction.p_blowup, and flagged in the card. NEW CARD FLAG: an under lean
  with p_blowup ≥ 0.45 → "fragile under: P(either ≥7) = X% — one-team blowup
  risk". Threshold calibrated: p(either≥7) ≈ 0.23 for two 3.5-rpg teams, ~0.38
  at league-avg 4.4, ~0.48+ when a side projects 5+ — so 0.45 fires only when
  real scoring environment sits under an under lean (the 6/30 trap: Rays 10,
  Marlins 14). Directly targets the fragile-under failure mode. Only populates
  for predictions generated AFTER this ships (stored at predict time, not
  retroactive). Still model-blind — routing signal only.

- **2026-07-03 (tracking: won-last-game)** — Added per-team won_last_game
  booleans to unused_context (Anthony request). For each side, True/False for
  whether they won their most-recent completed game before this one; None if no
  prior game on record (kept distinct from False). Derived from Match rows
  (finished + scores) we already have — no new feed, batched per-team index, no
  N+1. Rides in unused_context stamped used_in_model: false like everything
  else. Populates from next export/predict forward. Pure tracking — accrues for
  later validation (does streak/last-result carry signal the model lacks?).

- **2026-07-05 (team KPI: avg winning streak length)** — Added streak KPIs as a
  TEAM-PROFILE stat (Anthony request; explicitly NOT a prediction input). New
  src/walters/team_streaks.py computes per-team from finished games: avg winning
  streak length (mean length of winning runs), longest streak, current streak
  (signed), win%. Surfaced two ways: CLI `team-streaks --sort avg|longest|
  current|winpct` (all clubs, ranked) and on the existing /teams/{id} profile
  page as KPI cards. Pure profile/tracking stat — does NOT touch the model or
  card. (Kept scope tight: KPI only, no prediction wiring, per Anthony.)

- **2026-07-05 (blowup split: per-team p_home_blowup / p_away_blowup)** — Fixed
  the one-sided-risk blind spot the betting model found 7/4 (Seattle under lost
  11-0; combined p_blowup was low because Toronto was quiet, but Seattle's own
  blowup risk was high). Surfaced p_home_blowup + p_away_blowup as separate
  exported fields (already computed inside predict_game as p_home_big/p_away_big
  — just exposed). Card fragile-under flag now fires on MAX(home,away) ≥ 0.30
  rather than combined ≥ 0.45 (0.30 single-team ≈ a 5.3+ rpg offense, the level
  that blows up unders; league-avg 4.4 team sits at 0.21 and won't trip it).
  Falls back to combined for older predictions lacking per-team fields. Still
  model-blind. Populates from next predict forward.

- **2026-07-05 (streak context in predict export)** — Per Anthony: surface
  seasonal winning-streak KPIs in each prediction's unused_context, conditional
  on a team being ON a winning streak (won last game). streak_context.{home,away}
  = {on_winning_streak, current_streak (games into current run),
  avg_win_streak_len (season), longest_win_streak (season)} — or None if that
  side didn't win its last game. Reuses team_streaks.streak_kpis over the team's
  prior games as-of the game date. Framed as a complement to bullpen form for
  spotting how a club manages long runs of games (rest/rotation patterns beyond
  players). used_in_model: false — tracking/validation only, NOT a model input.
  Populates from next export forward.

- **2026-07-06 (CLV aligned-vs-disagreement split)** — Extended clv-report with
  a bucket split: each model pick classified aligned (model picked market's
  favorite, first-capture devig ≥50%) vs disagree (picked market's underdog,
  <50%). Toward/away/flat tally + mean move shown PER BUCKET, plus a Bucket
  column in the per-game table. Tests the sharper question the interim report
  (21 toward/38 away/50 flat, mean −0.31pp overall) hinted at: is the
  anti-predictiveness concentrated in the DISAGREE bucket (the −5.6 Milwaukee-
  type moves)? Expected reads: disagree away>>toward + negative mean = model's
  market-fights are anti-predictive (confirms blend premise, and the "no edge"
  verdict); aligned ≈0 = agreeing with market isn't edge either. Ready for the
  July 8 rerun. Same honest framing: one window, confirm before concluding.

- **2026-07-06 (historical backfill: backbone + weather archive)** — Groundwork
  for a prior-season historical DB (gives the input-search idea a real training
  runway; see docs/historical_backfill_assessment.md). FINDINGS: schedule/
  results, umpires, and pitcher-appearances backfill for 2025 with NO code
  change — sync-matches/sync-umpires/sync-appearances already take --season and
  filter Match.season. The one real build: historical WEATHER. Added
  fetch_weather_historical() (Open-Meteo ARCHIVE endpoint archive-api.open-
  meteo.com/v1/archive, same vars incl. wind_direction, same return shape) +
  `backfill-weather --season 2025` (walks finished games, skips existing,
  rate-limited 0.4s, writes game_weather). TIER LIMITS (honest): odds/CLV canNOT
  backfill (line movement not reconstructable — CLV stays forward-only);
  re-running predict on 2025 = a BACKTEST (calibration/training only, not live
  edge). Sequencing: backfill is safe groundwork; still gate hard model-change
  decisions on the July 8 CLV review.

- **2026-07-06 (pre-game umpire capture: sync-umpires --today)** — Confirmed via
  live test that the MLB Stats API boxscore officials block populates PRE-game
  once the crew checks in (~a few hours before first pitch): at 11:16 ET only
  the 14:10 game had its ump (Jim Wolf), evening games pending — coverage is
  time-to-first-pitch dependent, exactly as expected. Added --today flag to
  sync-umpires: targets TODAY's SCHEDULED games, writes the plate umpire where
  posted (partial row — run environment left null, fills in post-game via the
  normal finished-game sync), and on re-run UPDATES null-umpire rows rather than
  skipping (so running it closer to first pitch fills in late-posting games).
  Slots into pre-game routine next to capture-weather (run after sync-pitchers).
  Export's unused_context.plate_umpire then populates for games whose ump is
  posted at run-time, carrying the season R/G we already track. Still model-
  blind. Coverage is inherently partial (late games post later) — by design.

- **2026-07-08 (CLV REVIEW COMPLETE + Stage 1 signal validation)** — CLV rerun
  (n=187, --since 2026-06-24): overall toward 43/away 71/flat 73, mean −0.28pp
  (interim was −0.31pp — STABLE). Aligned-vs-disagree split: DISAGREE bucket
  toward 14/away 38, mean −0.71pp (anti-predictive, confirmed at sample);
  aligned ≈ neutral. VERDICT: model is well-calibrated but does NOT beat the
  close; its market disagreements are anti-predictive. "Calibrated thermometer,
  not income engine." No demonstrated edge. Decision: keep model unchanged;
  betting-income thesis set down pending any Stage-1 signal that proves out.
  Anthony wants to test whether missing INPUTS explain it. Built Stage 1:
  `signal-residuals` (src/walters/signal_residuals.py) — for each tracked signal
  (bullpen fatigue, wind, temperature, umpire run-env), buckets the model's
  RESIDUAL (actual − predicted on its pick) and reports mean±SE per bucket +
  spread. A signal carries NEW info only if residual VARIES across buckets
  beyond noise (spread ≥6pp flags a Stage-2 candidate). Honest framing baked in:
  most signals expected flat (redundant w/ team quality); passing Stage 1 =
  calibration info NOT market edge (market may already price it); historical =
  hypothesis, confirm out-of-sample in Stage 2 before touching model. Bullpen
  fatigue is the one to watch. Model stays untouched regardless until a signal
  passes BOTH stages.

- **2026-07-08 (miss-analysis: exploratory category sweep)** — Built
  `miss-analysis` (src/walters/miss_analysis.py) — the disciplined version of
  "categorize what we got wrong." Buckets ALL graded predictions across ~9
  dimensions (confidence tier, favorite side, market agree/disagree, run
  environment, day/night, one-run risk, starter known, totals availability,
  park) and shows actual vs PREDICTED win rate + gap ± SE per bucket. Does NOT
  bucket losses alone (that always finds spurious patterns) — compares to the
  model's own predicted prob, controlling for base rates. Flags a bucket only if
  gap < −2×SE AND n≥min. HARD multiple-comparisons discipline baked into output:
  ~25 buckets tested → expect ~1 false positive; a flag is a HYPOTHESIS needing
  gradient + out-of-sample confirmation, a lone flag is probably noise (the
  lesson from the non-monotonic bullpen/umpire Stage-1 results). Prior: mostly
  noise, given CLV verdict + flat Stage 1 — but it's the broad exploratory sweep
  that catches anything the 4-signal test missed. Model stays untouched.

- **2026-07-08 (backtest: leakage-free historical validation)** — Built
  `backtest` (src/walters/backtest.py) to validate the confidence-tier
  overconfidence gradient on 2025 (independent data) before tuning run-shrink.
  Confirmed 2025 has NO predictions (backfill brought games/results only), so a
  backtest must GENERATE them. CRITICAL: leakage-free — walks games in date
  order, predicts each using ONLY prior games to build run profiles, adds the
  game to history only AFTER predicting (verified ordering). Loads production
  config so run-shrink/recal match live. Prints calibration-by-tier + an
  explicit gradient verdict (monotonic + strong gap <−3pp = CONFIRMED, tune
  run-shrink; else = recent-window artifact, don't tune). HONEST LIMITATION
  (documented): team profiles are point-in-time but pitcher ERAs are NOT
  reconstructed as-of-date — backtest runs without pitcher adjustment, so it
  tests the structural/run-profile calibration (which is what the confidence-
  tier gradient IS a property of), not the full pitcher-aware pipeline. Min 40
  prior games before predicting (thin early-season history guard). Does NOT
  write Prediction rows or touch the model. Foundation for Stage 2 input-testing
  too.

- **2026-07-08 (honest scenario layer)** — Built a what-if scenario layer AFTER
  prediction (Anthony's idea), src/walters/scenarios.py build_scenarios().
  Leaves the model untouched. Two parts: (a) distribution_scenarios — real
  slices of the model's OWN score distribution (favorite-wins / upset / one-run
  / blowout / per-team explosion), each carrying the model's actual probability;
  (b) context_flags — tracked conditions (streak, bullpen fatigue, wind, umpire)
  shown for awareness with effect=None and an explicit "context only, no
  validated predictive effect" tag (bullpen even labels "failed Stage-1"). The
  hard rule enforced + unit-verified: NO scenario or flag carries a fabricated
  probability — (a) numbers are the model's, (b) numbers don't exist. Surfaced
  via `scenarios [--date]` CLI (prob bars + basis per scenario) and attached to
  each export row as row["scenarios"]. This is the honest version of Anthony's
  "storytelling layer": richer what-if picture, real numbers only, and the
  natural home for any condition that eventually VALIDATES (graduates from
  context-flag to weighted) via Stage 2 / upset-log. Refused the generative
  version (LLM/vibes confidence scores) — convincingly-wrong is worse than
  obviously-wrong.

- **2026-07-12 (venue rename fix: Rate Field + UNIQLO Dodger)** — Two parks
  missing from weather coord map because the feed now sends renamed venues:
  "Rate Field" (CWS, was Guaranteed Rate Field) and "UNIQLO Field at Dodger
  Stadium" (LAD naming rights). Both were IN the maps under old names. Fixed via
  explicit alias table in lookup_venue() + prefix-strip ("<Sponsor> Field at X"
  → X) fallback, and added both new names to park_wind PARK_CF_BEARING so wind
  classification also resolves. Same class as the earlier Daikin Park rename.

- **2026-07-12 (calibration-fine: configurable bands + honest error bars)** —
  Anthony wanted finer bands (1-point: 50/51/52%) over ~30 days. Built
  `calibration-fine` (src/walters/fine_calibration.py) with --width (default
  0.01), --days (default 30) / --since, --actionable-only. Manages the
  resolution-vs-noise tension honestly: fine bands for texture, each with n +
  Wilson 95% interval (thin bands <20 games dimmed, read as directional);
  coarse 5pp bands alongside for the statistically honest read; monotonic-trend
  check over well-sampled coarse bands (the signal that survives noise). Verified
  a 25-game band → ±18pp interval (visible "don't over-read"), 400-game → ±5pp.
  Guidance printed: run --days 30 (recent) AND --since 2025-03-01 (full ~3,900-
  game history) — contrast shows drift vs noise. Read-only; no model change.

- **2026-07-12 (input-candidate framework folded into improve, weekly cadence)**
  Anthony's insight: "we never promote" + "can't test inputs" = ONE problem —
  improve only proposes same-structure retrains. Widened the candidate axis:
  improve now ALSO evaluates production+input candidates through the SAME
  promotion gate, folded into the daily command but self-throttled to a WEEKLY
  cadence (src/walters/input_candidates.py; state in ~/.sports_predictor_input_
  candidates.json; --input-cadence-days, --force-input-eval). Daily = fast
  same-structure check as before; weekly = input-candidate eval. Rationale:
  inputs move slowly + daily testing is a multiple-comparisons machine that
  eventually promotes noise (weekly cuts false-positive risk ~7x). HONEST SCOPE
  (not hidden): the run-profile Pythag/NegBin model has no consumption slot for
  weather/umpire/streak, and none is reconstructed as-of-date, so the consumable
  set is currently EMPTY by design — the framework lists each input + why it's
  not yet consumable (all failed Stage-1 or collinear w/ team quality). It's the
  READY mechanism: when a signal passes validation + gets a slot, it plugs in
  and flows through the same gate. Reminder: a promotion here = better-calibrated
  PREDICTOR, not market edge (CLV verdict independent of model quality).

- **2026-07-12 (bullpen EFFECTIVENESS tracking — reliever run-prevention)**
  Anthony: track how relievers PERFORM, not just availability. Gap identified:
  pitcher_appearances had usage (pitches/outs) but NOT effectiveness. Built:
  (1) adapter now extracts per-appearance earned_runs/hits/walks/strikeouts from
  the boxscore (same call, was already there); (2) 4 new nullable columns on
  pitcher_appearances + migrate_bullpen_effectiveness.py (idempotent ALTER);
  (3) sync-appearances --refresh (deletes+rewrites existing games to populate
  new fields — needed since normal sync skips captured games); (4)
  src/walters/bullpen_effectiveness.py: team reliever-only ERA/WHIP/K-9 over
  trailing 30d, leakage-safe (strictly before as_of); (5) surfaced in
  unused_context.bullpen_effectiveness (home/away) alongside availability; (6)
  `bullpen-effectiveness` report (--window/--sort). Team-level now; per-appearance
  rows keep pitcher_id so reliever-level (like starter tracking) can build on
  same data later w/o re-capture. used_in_model: FALSE. HONEST CAVEAT stated
  throughout: bullpen quality is PARTIALLY already in team RA (bullpen innings ARE
  team runs-allowed); the real question is whether RECENT bullpen form adds signal
  BEYOND season RA — test via Stage-1 (residuals controlling for RA) before it's
  ever a model candidate. "Better predictor" possible; "edge" is the higher bar
  (market prices bullpens too). Migration+refresh runbook: migrate → sync-
  appearances --refresh --backfill for 2025 & 2026.

- **2026-07-13 (cosmetic: verbose sync-matches progress)** — sync-matches could
  run 5+ min silently; added a progress callback threaded through
  IngestionService.sync_matches (optional `progress` param, back-compatible).
  Now prints: fetch-phase announcement (flags it as the slow part), then a
  running "…N/total (X%) — created/updated/skipped" ~10x through the DB write,
  then Done. CLI passes a dim-printing callback. Purely cosmetic — no behavior
  change. (All-Star break: no games 7/13, ASG 7/14, dark 7/15, 1 game 7/16, full
  slate resumes 7/17.)

- **2026-07-20 (bullpen_effectiveness added to input-candidate registry)** —
  Fixed the omission: bullpen EFFECTIVENESS (reliever ERA/WHIP/K-9, trailing 30d)
  is now a listed tracked input in input_candidates.TRACKED_INPUTS. Still
  consumable=False (accruing, not Stage-1 tested, partially collinear w/ team RA,
  no consumption slot) — but now formally in the weekly candidate report + queued
  for eventual Stage-1 testing (does recent bullpen form add signal beyond season
  RA?). Data was already capturing + riding in unused_context; this just
  completes the registry.
- **2026-07-20 (doubleheader logic — SCOPED, not yet built)** — Anthony asked re
  better DH handling. Symptom: odds matcher keys on (date, teams) → collides for
  same-day same-team games, so DH games lack odds/market context (predictions
  still generate). Real but small (few per season, only market-join fails). Right
  fix: include gameNumber/gamePk in match key (MLB API distinguishes; each DH game
  has distinct gamePk + gameNumber 1/2). CAVEAT to check FIRST: whether the odds
  feed (API-Baseball) separates the two games at all — if it lumps them, a better
  match key only half-fixes it and the honest move is to FLAG DH games as "no
  reliable market context" rather than force a fragile match. Decision: confirm
  odds-feed behavior before building.

- **2026-07-20 (doubleheader match-key fix — the safe half)** — Fixed the DH
  collision in match_lookup.find_match_by_teams_and_time(). Was: 2 candidates
  (same-day same-teams) → return None → both games skipped, no odds. Now:
  disambiguate by START-TIME PROXIMITY — each DH game has a distinct utc_date;
  the odds' commence_time is closest to its own game (G1 ~1pm, G2 ~7pm), so pick
  the nearest. SAFETY GUARD: only disambiguates when the two games are ≥1h apart
  AND the odds are ≥1h closer to one than the other; otherwise still returns None
  (skip) rather than risk mis-attaching a line — mis-attribution would be WORSE
  than no odds. Verified: odds@7pm→G2, odds@1pm→G1, games 30min apart→skip. This
  is the match-side fix (correct regardless of odds-feed behavior). STILL OPEN:
  whether the API-Baseball odds feed publishes separate lines per DH game at all
  — if it lumps them, this helps only when it does separate; confirm on a live DH
  before assuming full coverage.

- **2026-07-20 (totals calibration — the accuracy work we never did)** — Anthony:
  how much have we validated the totals NUMBER? Answer: almost none — all rigor
  went to sides. Built `totals-calibration` (src/walters/totals_calibration.py),
  3 reads on graded games with a REAL market line: (1) projected-vs-actual bias
  (mean error ± SE, MAE, bucketed by projected level — is the number centered or
  biased?); (2) over/under PROBABILITY calibration (says X% over → does over hit
  X%? off-diagonal = NegBin dispersion/shape miscalibration); (3) run-environment
  cut (with the honest caveat that ≤6/≥13 buckets MUST show error since point
  projection can't predict blowups — look at NORMAL 7-9 for the real signal).
  KEY framing: totals markets are softer than sides, so unlike the side (already
  clean, market-efficient) a totals miscalibration could be real AND fixable —
  this is the one place the investigation might turn up something actionable.
  Measures ACCURACY; "beats the market" (totals CLV) is a separate later question.
  Read-only, no model change.

- **2026-07-20 (totals bias — backtest confirmation added)** — 2026 totals-
  calibration surfaced a REAL, coherent low-projection bias: monotonic gradient
  (low proj +1.06, mid +0.54, high ~0, all ≥2SE, n=781) confirmed independently
  by the over-prob read (30-40% over-band: predicted 36% / actual 54%, n=134).
  Same defect from 2 angles: model UNDER-projects low-scoring games. Unlike the
  side (clean), this is fixable — BUT same-window risk as the confidence-tier
  gradient that evaporated, so must confirm on 2025 first. Extended backtest:
  now captures proj_total + actual_total per game, totals_bias_by_band() +
  printed in `backtest --season 2025` with a reproduce/not-reproduce verdict
  (low>+0.4, mid>+0.2, descending gradient = CONFIRMED → justify low-total upward
  calibration / revisit run-shrink's effect on low totals; else = window
  artifact, don't touch). Leakage-free (backtest builds proj from prior games
  only). NEXT: run backtest --season 2025, read the totals verdict.

- **2026-07-20 (shrink-tuning sweep — path from confirmed bias to fix)** — 2025
  backtest CONFIRMED the totals bias AND revealed it's two-sided: low proj +0.84
  (under-projects) AND very-high proj −0.91 (over-projects) on 2441 games. Real
  diagnosis: projections are OVER-DISPERSED — both tails overshoot, want more
  shrinkage toward league mean. Not a one-sided low nudge. Mechanism already
  exists (run_shrink_frac=0.25); finding says it may be too WEAK. Built
  `shrink-sweep --season 2025 --fracs 0.25,0.35,0.45`: re-runs leakage-free
  backtest at each shrink strength, reports totals bias by band + win-prob tier
  calibration for each, + a summary picking the frac that minimizes tail
  imbalance (|low|+|very-high|) WHILE keeping worst side-tier gap small. Config
  override via dataclasses.replace (doesn't mutate production). DISCIPLINE: the
  backtest is the judge — pick the frac that flattens BOTH totals tails without
  degrading side calibration; if flattening totals breaks sides, it's a trade-off
  to weigh not an auto-change. Then set-config run_shrink_frac + verify forward.
  NOTE: improves totals ACCURACY, not proven totals-market edge (separate CLV Q).
  This is the FIRST actionable model finding of the whole investigation — real,
  reproduced, fixable.

- **2026-07-21 (bugfix: 500 on prediction detail — NameError _result_letter)**
  UI prediction/match detail view 500'd with "NameError: name '_result_letter'
  is not defined". Root cause: preview.py called _result_letter(match, team_id)
  in two places (form summary + H2H) but the helper was never defined (lost in a
  prior edit) — NOT related to the run_shrink config change (timing was
  coincidental). Fix: defined _result_letter at module level — returns W/L/D from
  the team's perspective, None for unplayed games (null scores, so they don't
  miscount). Verified logic on all cases. Isolated one-function fix; no other
  behavior touched.

- **2026-07-29 (totals-calibration --since flag — verify-forward tooling)** —
  Added --since YYYY-MM-DD to totals-calibration (filters _collect by
  Prediction.computed_at). Purpose: isolate post run_shrink_frac=0.35 games
  (--since 2026-07-20) so the pre-change 0.25-era bias doesn't dilute the read.
  This is the verify-forward instrument for the shrink change: run it to check
  whether the confirmed low/mid projection under-bias (+1.06/+0.54 pre-change)
  has flattened on live post-change games. ~9 days / ~130 games accrued at build
  time — directional not definitive yet, but the right moment to start looking.
  Read-only, threaded since through _collect + totals_calibration + CLI.

- **2026-07-29 (totals-calibration read #4: residual by MARKET line)** — Anthony's
  addition. Prior reads bucket by the model's PROJECTED total (internal
  calibration). This new read buckets by the MARKET's line and shows, per line
  band: market resid (actual − line = did games at this line level go over/under
  the market) AND model resid (actual − projection = model's own error there).
  Divergence = where the model reads a line level differently than the market —
  the betting-relevant cut the projection buckets can't show. Flags market resid
  >2SE. Honest framing baked in: a biased market resid + centered model resid =
  line-level EDGE CANDIDATE (track, don't bet, until sample confirms); still an
  ACCURACY read, not proof of CLV. Data already in _collect (line/actual/
  projected); works with --since too. Read-only.

- **2026-07-29 (edge-candidate flag on read #4 — anti-noise guardrail)** —
  Anthony's idea: auto-flag that refuses to cry "edge" until preconditions met.
  Added model−market column (projection − line = model's DISAGREEMENT with the
  line) and a per-band flag firing ONLY if all five hold: |market resid|>0.75,
  |model resid|<0.40, |model−market|>0.50, SAME direction (model disagreed the
  way the market missed — added, not in Anthony's original, essential to rule out
  both-wrong-but-lucky), n≥150 (raised from his 75 — beating a market line is an
  extraordinary claim). Prints "Candidate structural market bias detected"
  (labeled TRACK-forward, not confirmed) or the honest default "No evidence of
  persistent market-level edge." Unit-tested all 6 pass/fail cases. Guardrail
  against future-us chasing noise, baked into the tool. Works with --since.

- **2026-08-01 (export-results — yesterday's graded games for the GPT layer)** —
  Gap: morning run EVALUATES yesterday's games (writes outcomes to DB) but never
  EXPORTED them to a file the external prediction model could consume. Built
  export_results() (src/walters/export.py) + `export-results` CLI. Backward-
  looking companion to export-predictions: pairs each graded game's PREDICTION
  (top pick, probs, projected total, o/u line, over prob) with ACTUAL (scores,
  total, result) and GRADED (top_pick_hit, total_correct, total_error, log_loss,
  brier, clv, closing_price), keyed by match_id so the consumer joins to the
  prediction file it already has. Defaults to YESTERDAY (what the morning run
  just evaluated), 08:00-UTC slate-day window (matches export-predictions),
  writes exports/mlb_MLB_results_<date>.json. Add to morning chain after
  evaluate: `export-results --sport mlb`. Record shown (top-pick n/N, totals
  n/N) is labeled variance-not-signal, for the consumer to grade against.

- **2026-08-02 (totals model — Step 1 scaffold + head-to-head)** — Anthony's
  "two models competing" → scoped to the one defensible version: a totals-
  specific model (totals is the soft market + where the real bias was found).
  Built src/walters/totals_model.py project_total() — projects TOTAL runs
  directly, park-factor-adjusted (park_factors.py already existed), as explicit
  alternative to the incumbent byproduct total (home_xr+away_xr from the win-prob
  model). Step 1 ONLY: minimal (team run rates + park + league env), must BEAT
  incumbent on leakage-free OOS MAE/bias before adding anything. Extended
  run_backtest with return_totals_rows flag (additive 10-tuple: p,won,inc_total,
  actual_total,hrs,hra,ars,ara,lg,venue — existing 4-tuple results path
  UNCHANGED so shrink-sweep/totals-bias unaffected). `totals-model-test --season
  2025 --park-weight N` prints MAE/bias head-to-head + verdict (beats by >0.02
  MAE = proceed to Step 2 totals-specific Stage-1 for weather/bullpen/umpire;
  worse/tied = incumbent hard to beat, stop). Honest framing: park is the one new
  input in Step 1; weather/bullpen/umpire are Step 2 and must pass a totals-
  specific Stage-1 (predict TOTAL-runs residuals) to earn a slot IN THE TOTALS
  MODEL. Better number ≠ totals-market edge (separate CLV). NEXT: run
  totals-model-test, and sweep --park-weight to see if park helps.

- **2026-08-04 (daily totals pulse — robust diagnostics on export-results)** —
  Anthony's enhancement: the daily mean total_error is blowup-distorted (today
  +1.93 from two 11-12 run explosions, while the TYPICAL game was slightly OVER-
  projected). Added a 5-number pulse to the export-results summary (does NOT
  change calibration logic — diagnostic only): mean · median · trimmed mean ·
  blowups(>6)/n · typical-game MAE (on |err|<=6 games). Separates central
  tendency / robustness / outlier frequency. Fix during build: 10% trim is 0
  games at small slate sizes, so floor k at 1 when n>=6 so the trim actually
  bites; typical-MAE explicitly excludes blowups rather than relying on trim.
  Verified today: mean +1.93 → median -1.70, trimmed +1.35, typ-MAE 2.8, 3
  blowups — honest picture. Standing reminder in output: mean/median divergence =
  outlier day not bias; --since calibration read is the real verdict.

- **2026-08-04 (totals_pulse SERIALIZED into results export — audit-layer fix)** —
  Anthony caught that the pulse was console-print only, invisible to the audit
  layer that reads the FILE. Fixed: _compute_totals_pulse() now runs inside
  export_results() and the block is a top-level "totals_pulse" key in the JSON
  payload: games, mean_error, median_error, trimmed_mean_error, blowup_count,
  blowup_threshold(6.0), non_blowup_mean_error, non_blowup_mae. CLI now READS the
  block back from the payload for its console print (single source of truth — file
  and console identical). Confirmed on 8/3 data: mean +1.93 but non_blowup_mean
  -2.84 (typical game OVER-projected; mean driven by 3 blowups). Audit layer can
  now distinguish outlier-driven daily averages from real projection behavior
  directly from the file.

- **2026-08-10 (Kalshi Step 1 — second market source + disagreement read)** —
  Anthony has Kalshi API access, asked if prediction-market prices add value on
  top of bookmaker odds. Framed honestly: Kalshi price = implied prob, same as
  de-vig book line; most likely REDUNDANT for liquid MLB, but potentially a
  valuable SECOND independent market consensus (sharpens CLV; thinner markets
  *might* be softer). Discipline: measure disagreement first, don't wire to model
  or bet on it. Built Step 1: (a) src/adapters/kalshi.py — public market data, NO
  auth needed (auth only for trading); discovers MLB series at runtime (never
  hardcodes ticker — they change, e.g. KX* Klear prefix); implied_prob from
  yes_bid/ask midpoint (cents/100). (b) src/ingestion/kalshi_sync.py — pulls open
  MLB markets, matches to scheduled games by team name (best-effort, REPORTS
  matched/unmatched not silent), stores each side as OddsSnapshot(source=
  "kalshi") — reuses existing snapshot table (already has `source` col), so the
  read is a clean self-join. (c) `sync-kalshi` + `kalshi-disagreement` CLI: the
  read self-joins kalshi vs book consensus by match+selection, reports mean/median
  signed diff, mean ABS diff, %≥3pp and %≥5pp gaps, with verdict: small/few =
  REDUNDANT (stop); sizable = worth Step 2 (when they disagree, which is closer to
  actual outcome — CLV-style). NOT wired to model/bets. NEXT: run sync-kalshi
  alongside sync-odds for a few days, then kalshi-disagreement to see if it's a
  second copy of the book or a genuinely different signal.

- **2026-08-10 (Kalshi fix: wrong series endpoint path)** — sync-kalshi 404'd:
  I'd built it as GET /series/list (from a search snippet) but the real endpoint
  is GET /series (confirmed in API ref). Fixed the path; find_mlb_series now
  tries category=Sports, tags=MLB, then unfiltered. Also added sports_filters()
  using /search/filters_by_sport (Anthony's link — maps sports→competitions, a
  cleaner discovery aid) and made the sync REPORT what it found (available
  sports, MLB series tickers) so an empty result is diagnosable rather than
  blank. Markets endpoint (GET /markets?series_ticker=) was already correct.

- **2026-08-10 (Kalshi fix 2: target game series, kill 429s, diagnose matching)**
  First real run exposed 3 issues: (1) keyword filter matched 207 "MLB" series
  (HR derby, MVP, season wins, NPB/KBO/WBC/NCAA, props — all noise); (2) fetching
  all 207 tripped Kalshi rate limit (429 Too Many Requests); (3) even fetched
  markets matched 0 games (title-substring matching didn't catch Kalshi's team
  encoding). Fix: target ONLY KXMLBGAME (daily game moneyline series) via
  adapter.GAME_SERIES + game_series_markets(), which kills the 429s and the noise.
  Matching now checks title+subtitle+ticker (normalized). Added a DIAGNOSTIC that
  prints one sample market's keys + ticker/title/subtitle/bid/ask so we can see
  how Kalshi actually encodes teams and finalize matching. NEXT: run sync-kalshi,
  read the sample-market line to confirm KXMLBGAME structure + whether matching
  now works.

- **2026-08-10 (Kalshi fix 3: real field names + token matching — should work now)**
  Sample market from the live API revealed the actual structure: prices are
  yes_bid_dollars/yes_ask_dollars (already 0-1, NOT cents/100), and my old code
  read yes_bid/yes_ask → got None → skipped every market (0 stored). Team is in
  yes_sub_title (e.g. "Texas", "Los Angeles A"); ticker like
  KXMLBGAME-26AUG122210TEXLAA-TEX (date+matchup+winner-side). Fixed implied_prob
  to use *_dollars fields (+ handle one-sided quotes + last_price_dollars
  fallback); added yes_team(). Matching now uses yes_sub_title token-overlap vs
  our team names (so "Texas"→"Texas Rangers", "Los Angeles A"→"Los Angeles
  Angels" via shared city/nickname tokens), requiring ≥1 shared token, best
  overlap wins. Unit-verified prices + overlaps. NEXT: run sync-kalshi — should
  now store >0; then sync alongside sync-odds a few days + kalshi-disagreement.

- **2026-08-10 (Kalshi fix 4: dollar fields are STRINGS)** — sync failed with
  "unsupported operand type(s) for /: 'str' and 'float'" — Kalshi returns
  *_dollars as strings ("0.55") not floats. Added float coercion in implied_prob
  (safe _f() helper, returns None on empty/garbage). Fixed diagnostic to print
  the real *_dollars fields. Unit-verified string prices → 0.56 etc. NEXT: run
  sync-kalshi — should finally store >0.

- **2026-08-11 (SOCCER: leakage-free backtest — the load-bearing fix)** — Bringing
  soccer up to MLB discipline for PL season (starts in 10 days). AUDIT FINDING:
  the existing holdout eval (_score_model_on_holdout_soccer, training.py ~1601)
  LEAKS BADLY — computes strengths from ALL finished season matches (incl. the
  target game + everything after, no date filter line 1606) AND loads Elo from
  FINAL trained state. So every soccer calibration number to date is contaminated
  /untrustworthy. Production PREDICT path (predicting SCHEDULED games from all
  finished) is leakage-SAFE — those predictions are legit. Only eval leaked.
  FIX: built src/walters/soccer_backtest.py — walks season in DATE ORDER, predicts
  each match using ONLY prior games: Elo walked game-by-game (update_after_match
  AFTER each predict), strengths recomputed from strictly-prior finished matches,
  min_prior=40 guard (like MLB). `soccer-backtest --competition PL --season` prints
  1X2 calibration (home/draw/away bands, pred vs actual ±SE), multiclass log-loss
  (vs 1.099 uninformed) + Brier, AND base-rate-vs-mean-pred (flags the classic
  Poisson under-prediction of DRAWS). Verified walk ordering is strictly-prior
  (0,1,2,3,4). Model itself (Elo+Poisson, soccer_elo_poisson family) is sound.
  NEXT: run soccer-backtest on last PL season → first HONEST read on soccer
  calibration; watch draw prediction especially.

- **2026-08-11 (SOCCER: Dixon-Coles draw correction + sweep)** — Leakage-free
  backtest (340 PL 2024/25 games) confirmed 2 real fixable issues: (1) DRAW
  under-prediction — actual 24.4% vs pred 20.9%, model never predicts a draw >40%
  (235 draw-preds cluster 20-30%); (2) favorite OVERCONFIDENCE — 70-90% home-win
  bands actual only ~48-53% (well-sampled n=19/21). Model otherwise well-calibrated
  in 20-70% middle + beats uninformed (log-loss 1.009 vs 1.099). Both likely flow
  from independent-Poisson mishandling draws. FIX: added Dixon-Coles low-score
  correction to poisson.predict_match — PoissonConfig.dixon_coles_rho (0=old pure
  Poisson; rho<0 inflates 0-0 & 1-1, deflates 1-0/0-1). Standard DC tau on the 4
  low cells, clip≥0, then existing normalization. Added run_soccer_backtest
  dixon_coles_rho override + `dixon-coles-sweep --rhos` (reports per rho: log-loss,
  pred vs actual draw%, draw gap, 70-90% favorite actual win%). Verified rho more
  negative → draw prob up monotonically (25.5%→29.1% at lam1.5/mu1.2). NEXT: run
  dixon-coles-sweep on 2024/25, pick rho that closes draw gap w/o hurting log-loss
  + helps favorite bands, then soccer-backtest at that rho to confirm before
  setting it in the soccer production config.

- **2026-08-11 (SOCCER: rho decision + set-soccer-config)** — Dixon-Coles sweep
  (PL 2024/25, leakage-free): draw gap closes monotonically 0→-0.15 (-3.5→-0.7pp)
  AND log-loss improves through -0.10 (1.0092→1.0079) then ticks up at -0.15
  (1.0083). DECISION: rho = -0.10 — largest correction at BEST log-loss (halves
  draw gap -3.5→-1.6pp); -0.15 is over-correction (log-loss climbing), same logic
  as picking 0.35 over 0.45 for MLB shrink. CRITICAL FINDING: Dixon-Coles did NOT
  fix favorite overconfidence (70-90% band actual ~61-62% across whole sweep vs
  predicted 74-84%) — that's a SEPARATE problem (Elo/strength spread too aggressive),
  needs its own probability recalibration, deferred to weekend. Built
  set-soccer-config CLI (edits production soccer model params['poisson'], audited
  + reversible, whitelisted fields dixon_coles_rho[-0.30,0]/elo_goal_coeff/
  default_total_line). Predict path already reads PoissonConfig(**params['poisson'])
  so rho takes effect next predict run.
  **APPLIED 2026-08-14:** rho = -0.10 set on production soccer_elo_poisson v13
  (confirmed via CLI, audited). Weekend plan superseded by the full readiness
  section below (added 2026-08-15).

## SOCCER — PL 2026/27 READINESS (target: complete before opening weekend ~Aug 21-22)

Ordered by (correctness risk x time pressure). S1 and S2 gate opening weekend;
S3/S4 improve it; S5 is ops. All calibration numbers come from the leakage-free
soccer-backtest ONLY (the old holdout eval is contaminated — see 2026-08-11).

- **S1. Favorite-overconfidence recalibration [MODEL, blocks quality, ~half day]**
  The one open calibration defect: 70-90% home-win bands land ~61-62% actual vs
  74-84% predicted (well-sampled, stable across the whole rho sweep — Dixon-Coles
  is orthogonal to it). Suspected mechanism: Elo/strength spread too aggressive
  when mapped to goal lambdas. PLAN, mechanism-first (house style):
  (a) sweep `elo_goal_coeff` (already set-soccer-config whitelisted) on
  soccer-backtest PL 2024/25 — report per value: 70-90% band pred-vs-actual,
  log-loss, draw gap (watch rho interaction — re-verify rho=-0.10 still right at
  the chosen coeff, they both act on lambdas);
  (b) only if damping the source can't close the band without hurting log-loss:
  post-hoc band recalibration (MLB recal-clamp pattern) on 1X2 with draw
  renormalization — more knobs, less mechanism, last resort.
  ACCEPTANCE: 70-90% band gap within ~1 SE at n>=20; log-loss <= 1.0079
  (current rho=-0.10 baseline). Then set-soccer-config, log decision here.
  Uses only 2024/25 data — can run TODAY, no dependency on new-season sync.
  **RESOLVED 2026-08-15 — elo_goal_coeff = 0.0008** (from default 0.0023), by
  pre-committed rule (largest coeff where BOTH seasons pass pick-edge <= +2pp
  AND draw gap in [-1.0,+0.3]): 24/25 edge +4.06 -> +0.56pp, 23/24 +6.00 ->
  +1.94pp; log-loss 1.0079 -> 0.9956 and 0.9715 -> 0.9605; draw gaps -0.2 /
  +0.1pp so rho=-0.10 is JOINTLY confirmed at the new coeff (no re-sweep
  needed — nothing left to close). 0.0010 failed 23/24's edge bar; 0.0004-6
  over-corrects draws on 23/24 and is grid-edge chasing. Two-season selection
  (680 games, 2023/24 ingested as held-out check) — the overfit guard MLB
  sweeps never had. NOT built: the recal band clamp — the 70-90% band
  catastrophe did NOT replicate (23/24: 78%->71-76%, near 1 SE; pooled ~1.9
  SE, borderline) so stacking a second correction is the bullpen-taper
  mistake; re-examine only if the S6 weekly gate shows the band failing
  in-season. STRUCTURAL RESIDUAL, both seasons, all coeffs: model-above-close
  picks hit 42-49% vs claims of +8-11pp; model-below-close hit 56-70% — the
  soccer thermometer verdict. CONSUMER NOTE for the GPT layer (S4 docs):
  positive model-vs-market edges in soccer are historically ANTI-predictive;
  treat market-disagreement as market-is-right by default, opposite of a
  value signal. Sweep tooling: elo-coeff-sweep (market-scoreboard columns),
  soccer-backtest now defaults to production rho.

- **S2. Season 2026/27 cold start + promoted teams [CORRECTNESS, time-critical, ~half day]**
  VERIFIED GOOD: predict path backfills strengths from prior season when <30
  finished matches (training.py MIN_MATCHES_FOR_STRENGTHS) — opening weekend
  won't run on empty strengths. OPEN SUBITEMS:
  (a) sync PL 2026/27: teams first (three promoted clubs are new rows), then
  fixtures; VERIFY the api-football season key format for the new season and
  that matchweek-1 fixtures + odds actually land — dry-run THIS WEEKEND, not
  opening day.
  (b) Promoted-team priors: unseen teams get default Elo (1500) + no strength
  rows -> confirm what the Poisson layer actually assigns (likely neutral 1.0),
  and DECIDE: leave neutral (simple, slightly overrates promoted sides
  historically) vs a conservative promoted-team prior. Whichever way: EXPORT
  the fact (see S4 strengths_source) so the GPT layer can discount matchweek-1
  rows involving promoted clubs rather than us silently guessing.
  **DRY-RUN 2026-08-15:** teams created=0/updated=20 (all promoted clubs had
  prior PL spells in DB — verify the 20 match the real 2026/27 table); 380
  fixtures created clean; odds 6/20 (bookmaker timing); backfill ENGAGED
  (0 finished -> 500 prior); predict wrote 306/380 — the 74-game gap =
  exactly TWO clubs absent from the strengths window (2x38-2). Silent skip
  fixed same day (predict warns with club names + counts). Soccer export
  needs explicit window: --start 2026-08-21 --end 2026-08-24.
  **(b) DECIDED + BUILT 2026-08-15 (prior-plus-label, Anthony approved):**
  PoissonConfig.promoted_attack_prior=0.85 / promoted_defense_prior=1.15
  (set-soccer-config whitelisted, 0.60-1.00 / 1.00-1.40): no-strengths clubs
  get the conservative profile instead of dropped rows; predict logs which
  clubs; factor_breakdown carries home/away_strengths_source
  ("matches" | "promoted_default") per side — for the GPT layer AND our own
  records: promoted_default rows are their own grading cohort once the
  season starts; tune 0.85/1.15 only from that ledger. Integration-tested
  (promoted game predicted H .47/D .25/A .28 vs established side, labels
  correct, established games untouched). S4 lifts strengths_source into
  input_quality.
  (c) Confirm Elo state carried in v13 params covers all 17 returning clubs
  (spot-check a few ratings are non-default).

- **S3. Kalshi soccer extension [~half day, payload-first]**
  Discover the EPL game series ticker (sports filter "Soccer" confirmed
  available; do NOT assume KXEPLGAME — list series and INSPECT A REAL PAYLOAD
  before writing any code; the MLB integration's surprises were all
  payload-shape). Soccer is 3-WAY: expect per-team win markets and possibly an
  explicit draw market — the MLB two-sided normalization DOES NOT TRANSFER.
  Storage: OddsSnapshot(source="kalshi", market="1X2", selection
  HOME/AWAY/DRAW). Export: normalize over legs only when ALL THREE present
  (normalized flag semantics extend, not reuse); vs_book_pp against the 3-way
  de-vigged book fair prob. Matcher: occurrence gating + both-teams-in-title +
  refuse-ambiguity all transfer; club-name aliasing is WORSE than MLB
  ("Man City"/"Spurs"/"Wolves" vs canonical names) — build the alias map
  sport-generic and fold in the queued MLB sacramento/athletics fix in the
  same pass (one mechanism, two sports).
  **RECON 2026-08-17 (payload-first, via new kalshi-probe command):** spec
  confirmed from real payloads — 54 soccer events across leagues + targeted
  KXEPLGAME probe (60 open markets = 2 matchweeks incl. the opener).
  (1) THREE binary markets per game sharing an event_ticker: Home / Away /
  explicit "Tie" leg (resolves Yes on 90'+stoppage draw; cancel/reschedule
  rules stated). Store HOME/AWAY/DRAW, normalize only when all 3 legs
  present. (2) NAMING WIN: EPL uses FULL club names ("Manchester United",
  "Aston Villa", "Ipswich Town"), titles "X vs Y Winner?" — alias map nearly
  unnecessary for EPL (keep for Spurs/Wolves-style shorts if they appear).
  (3) custom_strike.soccer_team = stable club UUID; the Tie legs share one
  constant UUID (seen identical across leagues) — after one observation pass,
  matching can go exact-ID, stronger than MLB's name matching. (4) NEW
  REQUIREMENT — SPREAD GUARD: far-out/unliquid legs show bid/ask like
  0.03/0.81; a midpoint on that spread is noise, not a price. Sync must skip
  (and count) legs with spread above a bound (~0.10) — MLB never needed this
  (its spreads ran 1-2c) but weekend-cluster soccer syncs days ahead will.
  Ticker grammar: date+abbrs, no time component, no G-suffix. occurrence_
  datetime present -> time gate + in-play gate transfer unchanged.
  **BUILT 2026-08-18:** sync-kalshi-soccer (CLI) — 3 legs per game stored as
  OddsSnapshot(source=kalshi, market=1X2, HOME/AWAY/DRAW); all four MLB gates
  inherited + the NEW spread guard (skip-and-count legs with ask-bid >
  max_spread, default 0.10); Tie legs detected by sub_title with the constant
  Tie-UUID as cross-check; window now-1d..now+7d (weekend cadence). Export
  _summarize_kalshi generalized: full outcome set = 3 when a DRAW leg exists,
  partial sets ship raw with normalized=false (never inflate present legs);
  model_edge/vs_book include DRAW. The MLB matcher tokenizer now routes
  through team_aliases (sacramento/oakland -> athletics), closing the
  TB@Athletics gap in the same pass — one alias mechanism, all sports.
  Tested: full-3-leg normalize, wide-spread skip, in-play refusal, unmatched
  fixture, partial-set export. Instrumentation-only per the Step-1 verdict.

- **S4. Soccer export parity for the GPT layer [~2-3 hours]**
  input_quality is currently baseball-gated (correctly — no starter garbage on
  soccer rows) so soccer rows have NONE. Build the soccer variant: book_odds
  count, kalshi status (three_way/partial/absent), strengths_source
  (season / prior-season-backfill / none — the cold-start visibility from S2),
  new_to_league flags per side. VERIFY (don't assume): tier thresholds make
  sense for 3-way (a 45% favorite is strong in soccer; baseball thresholds may
  mislabel), top_pick handling when draw is modal (rare but possible at
  rho=-0.10), goals O/U line ingestion + over_prob path, and that evaluate /
  export-results / CLV grade 3-way picks correctly (CLV against the pick's 1X2
  closing price). Fix what fails; log what passes.
  **BUILT 2026-08-19 (with S7 + S8 in the same pass):** soccer rows now carry
  their own input_quality — strengths_source per side (matches |
  promoted_default), new_to_league flags, lineups:"none" stated per S7,
  book_odds count, kalshi three_way/partial/absent. Baseball-only fields
  (bullpen_swing, tier_capped_by_starter, p_one_run/p_blowup, close_game)
  REMOVED from soccer rows. S8 EXECUTED: totals_available=false with
  over_under_line/over_prob nulled on soccer rows (values persist in DB for
  future goals-pulse work; stronger_expression coerced off "totals"). Tier
  thresholds VERIFIED sane for 3-way on the live opening-slate export (strong
  at 61.7%/71.2% vs ~43% home base rate) — no change made. Tested incl. MLB
  regression (unchanged shape). Thursday dress rehearsal exercises it
  end-to-end.

- **S5. Weekly cadence ops [~1 hour, written not coded]**
  PL is weekend-clustered, not daily: define the routine (Fri sync + predict +
  export ahead of Sat 12:30 BST kickoff; Sat morning re-run for team news;
  results + grading Mon). Confirm MLB-only steps (umpires, weather, bullpen,
  pitchers) are skipped gracefully by the soccer chain, and the Kalshi window
  (now-1d/now+2d) covers a full weekend slate from a Friday run. Document in
  README next to the MLB routine.
  **WRITTEN 2026-08-20: docs/pl_weekly_routine.md** — Friday pre-matchweek
  chain, Saturday pre-kickoff refresh (the closing-ish CLV capture), Monday
  grading + soccer-refresh, midweek variant, consumer notes for the GPT
  handoff, and the deliberate exclusions (totals, lineups, cups, config
  changes). Soccer Kalshi window is now-1d..now+7d (weekend cadence), not the
  MLB +2d. Validated by the Thursday dress rehearsal; amend from practice.
  **DRESS REHEARSAL RUN 2026-08-20 — two findings, both amended into the doc
  same day:** (1) PROCESS: the run executed on Wednesday's mid-session code
  (re-extract skipped), shipping an export without strengths_backfilled /
  current_season_matches — detected by key-diff against packaged source.
  "Step zero: re-extract" now opens the routine doc. (2) SUBSTANTIVE: the
  soccer predict path applies a live injury xG adjustment (e.g. "home
  missing 3 (-9% xG)" on the Arsenal opener) but the Friday chain had NO
  sync-injuries step — the model was adjusting on injury data of unknown
  vintage while the export stayed silent about it. sync-injuries added to
  Friday + Saturday chains; consumer note (3) rewritten to distinguish
  lineups (absent by design) from injuries (live input, freshness by
  routine). Everything else passed: 10/10 rows, three-way Kalshi across the
  slate (wide-spread skips 28->25 as spreads tightened), promoted flags on
  the right sides, totals nulled, no baseball fields, first live
  soccer-refresh promotion clean (v15->v16, drift 0).
  **RE-RUN SAME DAY (corrected chain, latest code):** both findings closed —
  backfill keys present on 10/10; fresh injury sync (38 rows, reconciles
  exactly to per-team export counts, no double-count vs old rows) replaced
  Arsenal's STALE list (White/Merino -> Saliba/Timber) and moved
  probabilities on 6 of 10 games. Hull City hit the injury cap (-25% xG, 9
  out incl. keeper) — verified designed behavior (position-weighted, capped
  in factors.py); the adjustment moves the model TOWARD the market, residual
  Hull-optimism is the promoted_default prior's cohort to grade. Rehearsal
  COMPLETE; practice export handed to the GPT layer for its dry read.
  **DRY READ VERDICT 2026-08-20:** GPT layer parsed 10/10, all reads
  numerically verified against the file (no fabrications). Consumer notes
  DEMONSTRABLY ingested: rejected Hull despite model-actionable (promoted
  prior + no current-season data + injury cap named as the reason), and
  binned the two largest positive edges (Brentford +14.9pp, Ipswich
  +13.5pp) as untrusted-by-default per the anti-predictive verdict — these
  two rows open the forward pick-edge-sign ledger; Monday grades them.
  NOTE: the GPT independently asked for XI confirmation as its primary
  Friday check — the consumer just voted for S7 Stage-1 lineup ingestion
  unprompted. Convergence logged as priority evidence for the post-launch
  ordering. Thursday dress rehearsal CLOSED end to end.

- **S6. In-season model refresh + gate [LOAD-BEARING — without it everything
  goes stale, ~half day]** Soccer Elo is FROZEN in v13 params at train time;
  nothing updates it as matches finish (verified: predict path loads static
  EloState). MLB has nightly retrain + 0.005 log-loss gate; soccer has neither.
  BUILD: weekly refresh after each matchweek (retrain Elo+strengths from all
  finished matches) gated by the LEAKAGE-FREE soccer-backtest (the old holdout
  eval is contaminated and must not be the gate). Same accept/reject discipline
  and audit trail as MLB improve. Cadence: Mon after weekend grading.
  **BUILT 2026-08-16 — and it uncovered a latent landmine in BOTH sports:**
  _train_fresh_soccer AND _train_fresh_mlb stamped candidates with dataclass
  DEFAULTS, not production's tuned config. Every MLB candidate v101-v105 has
  carried run_shrink_frac=0.25/no cap — production's tuned values survived
  only because every candidate kept LOSING; one promotion past the noisy
  0.005 holdout gate would have silently reverted weeks of recalibration
  (soccer: rho and the 0.0008 coeff likewise). FIXED: both trainers now
  inherit production config (defaults only as base layer for new fields) and
  carry manual_config_edits audit history through promotion; tested both
  sports. THE REFRESH ITSELF: `soccer-refresh` (CLI) retrains Elo/contexts
  weekly and promotes via a SANITY gate, not a performance gate — honest
  reason: config-identical candidates score IDENTICALLY on the leakage-free
  backtest (it re-walks Elo internally) and the legacy holdout is self-graded
  homework, so for same-config/fresher-state the real risk is DATA CORRUPTION.
  Gate: data monotonicity, byte-exact config inheritance, Elo health
  (finite/band/mean-conservation), bounded per-team drift vs production
  (default 80 pts/week — calibrated: normal week <~40, fabricated 19-0 run
  measured 99; JSON key-type normalization required or drift silently reads 0
  — found by test). Rejection leaves production untouched with named reason.
  Performance verdicts remain forward grading + market-scored backtest for
  config changes. Division of labor documented in the command help.

- **M-LEDGER 2026-08-20 (graded 08-21): the +17.4pp game.** WSH@TEX — the
  largest MLB model-vs-market disagreement recorded (model 56.9% Nationals;
  Kalshi 60.5% Rangers; zero book odds, Kalshi sole anchor). Resolved
  MARKET-RIGHT: deGrom shutout, 2-0 TEX. Driver was Texas's recent-RS slump
  (2.8/g last 10) outweighing deGrom in the blend — legitimate output, wrong
  argument to win. MLB counterpart to the soccer thermometer verdict; one
  sample, logged not concluded. Same night: LAA 18-3 over HOU (model 59%
  home, p_blowup 0.35 + swing flag 2.06 + close_game_flag all pre-flagged)
  — GPT layer's "fragile favorite" tag born from it, consuming existing
  export fields only. Scope split held: no model asks. Totals pulse for the
  fix window: trimmed 0.00, non-blowup MAE 1.6, 4-blowup outlier day (mean
  +0.61 / median -1.30 divergence = variance). v110 rejected at even
  log-loss — gate held after a 5/9 day.

- **M-LEDGER 2026-08-21 (graded 08-22): best sides day of tracking, 13/15.**
  Gate rejected v111 at +0.0001 vs 0.0050 bar — second straight even-line
  rejection, discipline held after the big day. TOTALS: uniform
  over-projection day (mean -1.07 / median -0.85 / trimmed -1.11, ZERO
  blowups, non-blowup MAE 2.5) — first clean forward appearance of the
  high-projection over-lean watch item (HOU 9.63->4, MIA 8.79->5, TEX
  8.18->3). Aug 31 --since read now has both shapes on file: outlier day
  (08-20) and lean day (08-21). COSMETIC: export-results prints the
  "outlier-driven, not bias" note unconditionally — inaccurate on this day
  (all three centers agree); make the note conditional on mean/median
  divergence. GPT audit verified numerically (CLV cites exact); Detroit =
  2nd-best CLV on slate, lost — cleanest one-game case for price-vs-outcome
  separation. Zero model asks; scope split held.

- **S-NEGATIVE 2026-08-22: the injury "contamination" false alarm.** Matchday-1
  export showed Bruno Guimaraes on Arsenal's injury list and Woolfenden on
  Coventry's; Claude diagnosed cross-team attribution corruption in the
  adapter (76 rows vs Thursday's 38 read as scrambled doubling). Raw-response
  diagnostic DISPROVED it: every row carries the requested team's own id,
  dedupe works (6 raw -> 3 stored), and the players genuinely moved in the
  summer 2026 window — the live API was right and the reviewer's pre-summer
  world knowledge was stale. 38->76 = matchday reporting depth; arithmetic
  reconciles exactly. LESSON (now standing): consumer note (2) applies to
  reviewers as well as the model — before declaring upstream data corrupt,
  verify player-club facts against live sources, not memory. Zero code
  changed; diagnostic-before-fix prevented a wrong matchday hotfix.
  Harmless observation filed: /injuries returns each row twice on matchdays;
  adapter dedupe absorbs it.

- **S11. Export status semantics on past-inclusive windows.** cli auto
  filter: past dates -> finished, future -> scheduled, today-inclusive ->
  all. A Saturday run with Friday's window therefore exports "all" —
  stale played-game rows included by design. Routine doc Saturday window
  (--start SAT) plus explicit --status scheduled is the consumer-safe form;
  consider making the Saturday doc line carry --status scheduled verbatim.
  (Also: 08-22 chain re-run was issued with Friday's window by Claude —
  process miss on our side, caught same morning.)

- **M11. Two-game moneyline gap [OPEN — diagnostic mid-flight].** WSH@TEX
  (5776) and LAA@HOU showed book_odds=0 at export AND null CLV at grading,
  but 5776 holds 176 odds rows in the DB — date-window theory DISPROVEN
  (rows pre-existed; retry sync was a no-op: sync-odds has no --date-from).
  Remaining suspects: (a) no 1X2/moneyline rows for those games (API-side;
  export-the-gap is correct behavior) or (b) market-label mismatch in the
  matcher (one-line fix). Per-market GROUP BY on 5776 vs healthy 5775
  decides it. No code until then.

- **M11 UPDATE 08-22: pattern now 5/5.** Today's bookless games (5804 CIN@ARI,
  5805 CLE@COL, 5806 MIN@SD) are all UTC-rollover starts (00:10-00:40 UTC),
  matching Thursday's two exactly. Every book_odds=0 instance ever crosses
  UTC midnight; none that don't. NEW THEORY (c): series games share a UTC
  calendar date with the next day's game — a (teams, date) odds matcher
  would collide them, one match row eating both games' rows (would explain
  5776 holding 176 rows yet exporting 0 books). Expanded diagnostic issued:
  per-market GROUP BY on all five + top-8 row counts as collision detector.

- **S13 RESOLVED 2026-08-23 (was: triplicate snapshots).** Diagnostic
  verdict: rows were v13/v15/v16 — ONE per model version, not per run. The
  (match_id, model_version) upsert key orphans predictions from prior
  production versions on every promotion; evaluate grades all rows.
  Latent in MLB too (v2 all season — would fire on first promotion), same
  invisibility class as the trainer-config bug. FIX: upsert keyed on
  match_id only (both sports, training.py) — predictions current-only per
  match, history lives in outcomes. One-time cleanup deletes soccer
  non-v16 ghosts + their outcomes (preview-then-delete SQL issued); both
  MW1 results files re-exported clean. Evaluate-side latest-only guard
  noted as optional hardening, not done (minimal change).

- **[superseded] S13 original entry follows:**
- **S13. Triplicate prediction snapshots defeating grading [OPEN — diagnostic
  issued, blocks clean soccer ledger].** First soccer results export
  (08-22 file) held 3 rows/match: Fri run + Sat 09:53 + Sat recovery all
  survived despite the (match_id, model_version) delete-then-insert upsert
  (all v16 — those deletes should have fired). MLB never surfaced it
  (one predict/slate); soccer's 3 same-day runs exposed it. evaluate graded
  all 18 rows; export + totals_pulse triple-counted (console 6/15 = true
  2/5). GPT layer independently detected and deduped-to-latest — correct
  consumer behavior. Diagnostic: GROUP BY match_id, model_version on
  predictions decides between version-string mismatch / session-ordering /
  other. FIX AFTER DIAGNOSTIC ONLY — wrong fix corrupts ledger foundation.
  Note: Arsenal 08-21 results file never exported (default --date =
  yesterday); command issued.

- **NO-ODDS TAXONOMY EXTENDED 08-29 + fallback doubleheader guard.**
  Saturday doubleheaders revealed the provider's late-publication class is
  broader than UTC-rollover: SAME-DAY second games and adjacent listings
  also wait (BOS@NYY 23:15 and the ARI@SF opener both bookless). Coverage
  non-event (5/5 two_sided Kalshi; closers via next bulk sync). PATCH: the
  fallback name-matcher queried provider id 180062 for BOTH ARI@SF rows
  (twins sit 6h apart, inside the 12h window) — bulk path safe (find_match
  refuses ambiguity) but fallback would have cross-attached on publication
  day. Added nearest-time selection + claimed-id uniqueness guard, logged
  skip line. M12 REMINDER STANCE CHANGED: probe has slipped four sessions —
  dropping the nags; item stays logged dormant. Independent mitigation
  (aggregate the 53 daily WARNINGs into one line) queued for the next
  quiet-slot build, needs no identification.

- **M-LEDGER 08-28 (graded 08-29): sides 9/15; v119 rejected DESPITE
  beating production (0.6899 vs 0.6900 — second sign-flip hold, 9th
  consecutive rejection). Zero null CLV in the fresh file (backfill steady
  state = normal mornings now). Totals shape #9: mild lean, 3 blowups,
  conditional note fired correctly on the blowup condition. GPT 9th audit:
  no model asks FROM A PROFITABLE SLATE (declining to change while winning
  = the harder discipline). MONDAY: Aug-31 totals review runs
  totals-calibration --since 2026-07-20 (pre-committed date) — adjudicates
  run_shrink_frac=0.35 + the high-projection over-lean watch item on nine
  forward shapes with full CLV context.

- **MW2 FILE SHIPPED 08-28: all three build verifications GREEN.**
  promoted_this_season T/T on exactly the derby row (F/F elsewhere);
  injury stamps 10/10; fitted strengths + v18 + csm=10 throughout. FIRST
  FULL-BOARD KALSHI MATCHWEEK: three_way 10/10, wide-spread 0. Hand-off
  watchlist: FOUR anti-predictive-shape rows — Hull away +19.8pp (the
  promoted derby, both sides cohort-flagged: the exact row the season-long
  flag was built for), Newcastle away +19.6pp, Bournemouth draw +7.4pp,
  Brentford away +5.9pp. Market-respect rows: Liverpool -20.4pp, Chelsea
  -13.2pp. MLB same-day: patched fallback first live pass clean (5/5 ids,
  zero duplicate queries, filled 0/5 honest). M12 probe slipped a third
  session — folded into Saturday's paste.

- **M13 v2 VERIFIED LIVE 08-27 (evening slate): ambiguous 0 on a
  simultaneous NY collision** (NYY 7:05 / NYM 7:10 — the five-minute-apart
  case time filters cannot touch; identical configuration produced
  ambiguous 8 + one_sided rows two days prior). Both games two_sided;
  opponent-prefix resolution working as unit-tested. City-collision
  coverage tax repealed. All three 08-27 builds now verified or scheduled:
  M13 v2 live-pass, registry exercised by phase 2, promoted flag verifies
  in Friday's MW2 export.

- **PHASE 2 CLOSED 08-27 (complete-with-annotation).** Final UEL 2025/26
  pull: 271 fetched, all UPDATED yet absent from the UEL GROUP BY rows —
  they pre-exist under a LEGACY competition code from the original
  historical backfill (writer matches by external id without reassigning
  competition). Named 08-27: legacy code EL
  ("UEFA Europa League") from the original backfill — one competition under
  two codes, seasons split (2024/25 under UEL, 2025/26 under EL).
  Normalization = one UPDATE re-attributing EL rows to UEL; folded into the
  phase-4 session (competition-scoped Elo work), NOT run pre-matchday.
  Impact ~zero for current scope
  (training pot is code-agnostic; team_to_league is league-only); costs
  only competition-scoped Elo attribution IF Europa prediction ever ships —
  normalization task for that day, annotated not urgent.

- **PHASE 2 CERTIFICATE 08-27: complete pending one UEL season.** GROUP BY
  reconciled: pyramid 3x3 seasons all present (552-558 each); CL four
  seasons (2023/24 from the ORIGINAL historical backfill); EFL prior
  seasons PRE-EXISTED via same backfill — the season-format suspicion was
  WRONG (single-year "2025" aliases to "2025/26"; both formats fine;
  earlier updated=93 lines were re-touches of old rows). UEL 2025/26
  missing — one command issued. KEY REFRAME -> TUESDAY WATCH-ITEM: EFL
  history was always in the pot, yet S16 showed pyramid clubs at exactly
  1400 — because the trained Elo table is PL-scoped (gate line "elo: n=27"
  all season). Tuesday's gate: if n jumps toward ~150, trainer universe
  widens with data and phase 4 shrinks to the bonus fix; if n stays 27,
  scope is hardcoded and widening joins phase 4. One gate line answers it.

- **[superseded detail] PYRAMID PHASE 2 LANDED 08-27 (afternoon): 3,332 new league matches.**
  EL1/EL2 each 552+557+557 across 3 seasons (identical-looking counts are
  structural: three 24-team divisions) — CREATED not updated, so league ids
  41/42 pulled distinct correct divisions. All pyramid clubs pre-existed
  from FA Cup history; syncs attached league membership = team_to_league
  feedstock. EUROPE (user-expanded scope): UEL newly registered (id 3);
  CL/UEL prior seasons pre-existed via historical backfill (updated
  281/279/196); current-season re-pull post-team-sync issued for the
  52+67 foreign-team skips. OPEN: EFL prior-season format question
  (updated=93 twice, created=0 — suspected single-year cup format; probe
  issued) + GROUP BY completion certificate. Tuesday's gated refresh pot
  heading toward ~7,600+; drift read with extra care, one run, no retry.

- **BUILT 08-27 (pre-MW2 quiet slot):** (1) M13 v2 SHIPPED — simultaneous
  city collisions resolved via ticker matchup-segment opponent prefixes;
  strict-unique-maximum rule, five-case unit suite passes incl. the
  degenerate both-supported case refusing. Tonight's slate = live test:
  expect ambiguous to drop toward 0 when NY/CHI/LA collide. First edit
  attempt shipped with scaffolding debris (caught by own syntax check,
  rewritten clean; soccer block shares loop text — first-occurrence
  scoping required). (2) Pyramid phase 1 SHIPPED: EL1(41)/EL2(42)
  registered beside ELC — weekend backfill syncs unblocked.
  (3) promoted_this_season SHIPPED same day (user decision: season-long).
  Design: season-keyed registry ("PL:2026/27" -> {Coventry, Hull City}) so
  the removal mechanism is the CALENDAR — flag expires automatically when
  the season string rolls; maintenance = add new promoted set each August.
  Both sides flagged independently in input_quality; new_to_league
  unchanged (reflects current strengths source only). Consumer note 3b
  added to routine doc. VERIFY in Friday's MW2 export: Hull-at-Coventry
  derby row must show promoted_this_season true/true with
  strengths_source matches/matches.

- **M-LEDGER 08-26 (graded 08-27): sides 8/15, v116 rejected even (7th
  straight), totals 7th shape (balanced: centers ~0, 3 blowups). CLV
  STEADY STATE FULLY OPERATIONAL: backfill healed Tuesday's 6 on schedule
  AND today's fresh file has ZERO nulls — the near-boundary rollover game
  graded same-day. GPT audit (7th consecutive zero model asks) now uses
  CLV-vs-outcome separation as native vocabulary throughout — the
  backfill's downstream payoff, two days after shipping. M12 probe v3
  folded into Friday's session.

- **M11 BOUNDARY REFINED 08-26 (evening slate).** First rollover game ever
  to arrive WITH books in the bulk pull: MIN@ATH 01:05 UTC, 9 books
  (partial vs usual 12-13). All prior bookless games started 01:38+. The
  provider's publication boundary is FUZZY (~01:00-01:35 UTC), not a hard
  midnight — near-boundary games leak partial coverage. Patched fallback
  behaved exactly right: nothing missing, so silence. Coverage 15/15
  books, 14/15 two_sided — best day of the season. No action.

- **LEDGER CLV-COMPLETE 2026-08-26.** Three re-exports delivered; every
  historical null filled. HEADLINE FROM THE NULLS: 5776 (WSH@TEX, the
  season's largest disagreement at +17.4pp) graded at +18.7pp CLV — the
  ledger's largest — closing price drifted to 2.65 AGAINST the pick
  (disagreement widened to the close), resolved market-right 2-0. The
  anti-predictive cohort's anchor row, now fully priced. Permanent
  asymmetry documented: backfill fills moneyline CLV only; rollover games'
  total_correct stays null forever (no line existed at predict time —
  retro-grading would be fabrication; "(N no line)" discloses).

- **FIX SESSION FULLY VERIFIED 2026-08-26: six for six.** M11b's first run
  backfilled 92 outcomes — the null-CLV debt was LEDGER-WIDE, not just the
  eight tracked rollover games; paid in one pass. Steady state documented:
  each morning's fresh file carries nulls on the prior night's rollover
  games (closers arrive with the evening sync), self-healing next morning —
  permanent one-day CLV lag, automatic. Conditional console note passed its
  first live test on a genuine outlier day (divergence 1.04, 4 blowups —
  correct branch). Re-exports issued for 08-20/08-22/08-24 to make the
  downstream ledger CLV-complete. Weekly input-candidate report ran its
  expanded honest-state output (six tracked, none consumable, all reasons
  stated; bullpen_effectiveness sole accruer). M-LEDGER 08-25: sides 5/15
  (worst day; variance), v115 rejected at even 0.6900 (6th straight),
  totals 6th shape: outlier day. GPT audit -$95.55, correctly self-assigned
  to portfolio construction; SIXTH consecutive zero model asks.

- **M11 CLOSED 2026-08-25 (evening): fully characterized.** Live per-game
  experiment: all 21 ids resolved, provider returned "no odds" for every
  one — the data does not exist upstream until the provider's day rolls.
  No request shape can fix it. Complete mitigation already shipped: Kalshi
  = designed live coverage for rollover slots + M11b CLV backfill for
  closers. Fallback retained as a sentinel (logs "filled" if provider
  behavior ever changes). SAME-NIGHT PATCH: first live run exposed
  name-only matching cross-attaching series neighbors (game 179999 queried
  by two match rows) — added 12h date-proximity check (tz-correct) and
  tightened window 28h->12h to stop querying tomorrow's slate. Caught by
  the fallback's own logging, patched before any odds could mis-attach.

- **M13 VERDICT 08-25: partial by design of the collision.** Time-based
  disambiguation works only for STAGGERED city collisions; tonight's are
  simultaneous (HOU@NYY 7:05 vs MIL@NYM 7:10 — 5 minutes apart), so the
  refusal is correct and unavoidable by timestamp. ambiguous 6, Yankees +
  White Sox + Cubs rows one_sided. v2 idea filed: tie-break via ticker
  matchup segment vs the DIFFERING team's name prefix (refuse-safe: only
  resolves when exactly one candidate matches) — small, post-MW2.

- **S16. EFL CUP: NOT LAUNCH-READY — dress rehearsal hard fail 2026-08-25.**
  First live run of the cup path produced systematically INVERTED
  probabilities (Chelsea 19% home v Luton; lower-division side favored in
  every cross-division tie). Three layered causes: (1) COLD START — zero
  EFL Cup rows existed pre-run (all 60 created today); per-competition Elo
  means every lower-league club at exactly 1400.0. The "trained on 3,069
  cup matches" comfort was FAC/CL rows, not EFL — reviewer error, caught by
  the rehearsal wrapper, file never reached the GPT layer. (2) The
  promoted-default prior mechanically matched eleven PL clubs ("no matches
  in this competition"). (3) REAL LATENT BUG: team_to_league resolves to
  None for pyramid clubs -> league_bonus emits a -100.0 sentinel that lands
  with INVERTED effect (penalized side favored throughout) — never surfaced
  in backtests because those ran where league mapping resolves.
  PATH TO READY — refined 08-25 into the PYRAMID PROJECT (user-proposed
  data exercise; target = ROUND 3, mid-September):
  (1) registry: add EL1/EL2 to adapter competition map (the league table
  already carries "if we sync it" bonuses: ELC -130, EL1 -260, EL2 -360);
  (2) data: sync-matches --seasons 2 for ELC/EL1/EL2 (~3,300 league
  matches — THE signal: team_to_league builds from most-recent LEAGUE
  match) + EFL --seasons 2 (cup Elo warms; promoted-prior stops misfiring);
  (3) retrain DELIBERATELY: backfill+refresh is a model change via data —
  gated step, drift watched, sequenced AFTER MW2 Friday, never casually;
  (4) code fix: bonus application at predict time — Bradford(49%)>Burnley
  with both sides real-sourced proves data alone cannot cure it ("-100" is
  the documented unknown-league default, not a sentinel; earlier framing
  corrected — the bug is in application);
  (5) PRE-COMMITTED ACCEPTANCE (defined 08-25, before any fix): re-run the
  round-2 export vs the 13 books stored on these ties — pass = zero
  cross-division ties favoring the lower side against >60% book consensus,
  AND model within +/-8pp of book fair on every cross-division favorite.
  Then dress rehearsal -> GPT dry read -> live round 3.
  Until pass: EFL Cup out of scope; PL-only remains the soccer product. Minor also-founds: soccer odds sync date window left the
  three Wednesday games bookless (same family as M11); Kalshi correctly
  absent (KXEPLGAME is PL-only).

- **FIX SESSION SHIPPED 2026-08-25 (soccer dark day; MLB 5:30 chain = live
  test bed).** Six items, all previously diagnosed, zero speculative:
  M11a rollover fallback (bulk /odds has NO date param — provider-side
  omission; added per-game targeted requests for upcoming zero-odds
  matches, logged either way: tonight's console answers whether the
  provider serves rollover odds on request or hasn't published);
  M11b CLV backfill in evaluate (null-clv outcomes re-graded in place when
  closers arrive; idempotent; heals 5776/5777/5804-6 tomorrow morning —
  re-export 08-20 and 08-22 MLB results after);
  M13 ticker-timestamp fallback (city ties form only when
  occurrence_datetime is missing; ticker embeds ET start stamp — parse
  verified against all three observed real tickers; unparseable = today's
  refuse-safe behavior; expect ambiguous->0 on collision slates);
  S10 injuries_synced_at in soccer input_quality (MAX refreshed_at across
  both teams; null = no rows, itself informative);
  S15 refresh skip-guard (pre-train count check; skip message instead of
  twin versions; new cyan console branch);
  Milwaukee rename aliased in ALL THREE park maps (weather coords,
  park_wind exposure, park_factors — same park, new name);
  console totals note now conditional (divergence>=0.75 or blowups>0 ->
  outlier text, else uniform-lean text).

- **S13 EXAM PASSED 2026-08-25.** First predict across a version promotion:
  duplicates query EMPTY, end state v18|370 live + v16|10 preserved graded
  history. The exact scenario that minted the v13/v15 ghosts now provably
  clean.

- **S15. Refresh skip-guard on unchanged data [fix-session queue].** From
  user design question after the v18 twin: soccer-refresh promotes on
  sane-retrain (correct for a refresh-flow model — an MLB-style improvement
  bar would block absorbing real matchweek info; the two gates are shaped
  differently on purpose). But retraining on UNCHANGED data can only mint a
  deterministic twin (v18 vs v17: drift 0 proves it) and leaves phantom
  versions in the ledger (v17 predicted nothing, ever). Guard: if
  completed-match count hasn't grown since production trained, skip the
  retrain with a message. Joins the fix session, not hotfixed.

- **FIRST IN-SEASON REFRESH 2026-08-25: v17 PROMOTED — weekly loop closed
  end to end.** +10 matches (exactly MW1), Elo pool 25->27 (Coventry, Hull
  graduate from flat prior to fitted entries — MW2 promoted-club rows run
  on blended real signal), drift max 53/80 — the drift check's first
  encounter with real movement, passed with headroom. VERIFICATION: first
  predict under the new version is the fixed upsert's real exam (a version
  promotion is what minted the v13/v15 ghosts). CORRECTED CHECK 08-25 (the
  original version-only GROUP BY was mis-specified and false-alarmed):
  refresh writes NO predictions, so pre-predict the table legitimately
  holds old-version rows; and finished games KEEP their graded old-version
  rows forever (history, not ghosts). Real test: GROUP BY match_id HAVING
  COUNT(*)>1 must return EMPTY after predict; version mix v_new|371 +
  v16|9 is the correct end state. ALSO 08-25: refresh re-run minted v18
  (no-op twin of v17: same data, drift 0) — refresh is not
  version-idempotent; once weekly, never retry-if-unsure. Production: v18.

- **MW1 CLOSED (2026-08-21..24): sides 6/10, mean pick-CLV ~ -3pp.** Fri 1/1,
  Sat 2/5, Sun 2/3, Mon 1/1 (Chelsea 3-2 hit at 40.5%, liked LESS than
  market, CLV -9.1pp). Outcomes fine, prices consistently worse than close —
  the thermometer verdict's opening statement. Finale graded as exactly ONE
  row: S13 fix verified end to end.

- **S14. Totals under-compression in uncertain-winner games [TRACKING —
  first genuine cross-boundary ask, from GPT MW1 audit].** Evidence:
  Brighton 2.1->4, NUFC 2.4->4, Fulham 2.19->5 (all close side splits, all
  big positive total error; internal totals, S8 keeps them unshipped).
  PRE-COMMITTED TEST (defined 08-25, before more data): bucket PL games by
  top-pick prob <45% vs >=45%; compare mean total error after 30 graded
  games; promote to model work ONLY if uncertain bucket shows >= +0.75
  mean error with the confident bucket near zero. GPT's asymmetric-injury
  proposal (defender out -> raise opponent ceiling/variance, not lower own
  mean) filed alongside S7 Stage-1 scope — good idea, same door as every
  idea: tracked, not reactive.

- **M-NOTE 08-25: v114 rejection was the gate's first sign-flip test** —
  candidate BEAT production 0.6883 vs 0.6884, still 50x under the 0.0050
  bar. Held. Also first 10/10 CLV day incl. rollover games (closers became
  fetchable post-UTC-midnight = M11 mechanism favorably; confirm whether an
  evening sync ran). Totals 5th shape: mixed (+0.36 mean / -1.71 median).

- **M14 RESOLVED 08-24 (same evening): subscription renewed by user; sync
  healthy at 17:38 (15,150 rows). Fastest open-to-close in backlog history
  (~7 min). Original entry: [URGENT — user action:
  api-sports dashboard/billing].** 08-24 17:31 sync rejected: "Free plans do
  not have access to this season." Worked 21h earlier (Sun 00:10 UTC
  capture). Soccer/API-Football unaffected (separate sub). Until restored:
  Kalshi is MLB's only live market source (Step-1 redundancy verdict now a
  real fallback), stale Sunday prices survive on early games only (failed
  fetch doesn't wipe), CLV grading null for affected slates.

- **M11 MECHANISM CONFIRMED 08-24 (accidentally, by the outage).** With
  today's sync dead, Sunday evening's rows show the clean split: Monday's
  early games hold books=12, Monday's UTC-rollover games hold 0 — the odds
  request is UTC-day-scoped; rollover games get ZERO rows (not just missing
  1X2 — also explains their null totals lines) until their UTC date becomes
  "today", arriving as closers. FIX (post-restore, post-freeze session):
  extend request window +1 UTC day; pair with the evaluate CLV backfill.

- **S13 CODA 08-24: one sequencing straggler, healed by re-export.** The
  Sunday (08-23) results file was graded at 11:56 UTC, three minutes BEFORE
  the 11:59 cleanup — evaluate read the dirty table one last time (9
  outcomes = 3 versions x 3 games). Not a fix failure: the cleanup deleted
  those ghost outcomes moments later; re-export of --date 2026-08-23 issued
  (expected 3 rows). LESSON for multi-step remediations: cleanup before any
  same-morning grading, or re-export everything graded that morning.

- **S-LEDGER 2026-08-23 (v16 only): Sunday 2/3. MW1 through Sunday: 5/9.**
  City 2-1 (archetype behaved), Brighton 4-0 as a 35.2% toss-up pick (side
  right, margin very wrong: +1.9 total error), Newcastle-Liverpool 2-2
  drew past the away pick. First soccer under-projection totals day (0/9
  internal, everything over). Finale tonight closes the matchweek.

- **M-LEDGER 2026-08-23 (graded 08-24): sides 12/15 — 2nd best day.**
  v113 rejected at even line, FOURTH consecutive; production 0.6908->0.6885
  on data accrual alone. Totals 4th point: mixed (median 0.00, 2 blowups;
  Cubs 19-2 was a city-collision one_sided game). GPT audit: fifth straight
  with zero model asks.

- **S13 CLEANUP CONFIRMED 08-24.** Preview revealed full archaeology (v3/v5/
  v9 dev relics + v13/v15 season ghosts); all non-v16 soccer rows + outcomes
  deleted. Re-exports clean: MW1 Friday 1/1 (Arsenal), Saturday 2/5 —
  superseding files delivered to GPT layer. Upsert fix live; first exercised
  by the 08-24 pre-game predict run.

- **M11 REFRAMED 08-24: odds table is wipe-and-replace.** captured_at probe
  showed MIN==MAX==last night's sync for BOTH healthy and broken games —
  the sync replaces rows per match every run; no history retained;
  Thursday's state unrecoverable. Consequence: 5776 HAS moneylines NOW
  (closed-game final lines backfill on later syncs) but its outcome froze
  with clv=null because evaluate grades once and never revisits. FIX
  DIRECTION: CLV backfill pass in evaluate for null-clv outcomes whose
  closers arrived late (next non-match session). Mechanism probe moved to
  live observation: post-sync GROUP BY on future games issued for tonight's
  slate.

- **M11 UPDATE 08-23: theory (c) collision DEAD (top-8 counts are soccer
  matches, no MLB doubling); moneylines EXIST in DB for all five games
  (1X2|22-26, same shape as healthy games). Since _summarize_market has no
  filter that could reject them, the remaining theory is ARRIVAL TIME:
  1X2 rows for UTC-rollover games arrive with the NEXT morning's sync
  (closing-line backfill), i.e. after both the prediction export AND the
  7am results grading. Supporting: Sunday's all-daytime slate had zero
  bookless games. captured_at MIN/MAX probe issued — decisive. If
  confirmed, fix = re-grade CLV when closers arrive late (results-side),
  not a sync change.

- **S-LEDGER 2026-08-21 (graded 08-23, deduped to v16): Arsenal 3-0
  Coventry — season's first row hit.** Sides 1/1, totals 1/1 (2.68 proj,
  3 actual). CLV -8.2pp (model 72.2% vs 80.6% close) — market righter on
  magnitude even when the model is right on direction; the promoted-prior
  cohort's first graded row. Note: file as first exported was triplicated
  (v13/v15/v16 ghosts) — superseded by post-cleanup re-export.

- **S-LEDGER 2026-08-22 (PL matchweek 1 Saturday, deduped): sides 2/5.**
  Thermometer's first forward split: Ipswich +13.5pp edge pick LOST (first
  confirming point for anti-predictive verdict); Brentford +14.9pp edge WON
  3-0 with +16.3pp CLV (counterpoint); Hull (unpicked home edge, max-caution
  cohort) beat United 2-0. Verdict posture unchanged per GPT: diagnostic,
  never promotional. Totals texture strong (Everton, Forest unders) —
  internal totals grading is tracking-first working; stays excluded from
  consumer export per S8. GPT hard rules all betting-layer; S7 (XI) now has
  a FOURTH independent vote (every new hard rule cites missing XI).

- **M-LEDGER 2026-08-22 (graded 08-23): sides 8/15.** Houston strong-tier
  fragile favorite lost AGAIN (2nd straight day the fragile tag would have
  paid). v112 rejected at even line — third consecutive. Totals 3rd forward
  point: lean shape (median -2.44, 2 blowups). M11 data cost compounding:
  5804-6 null CLV joins 5776-7 — five games unpriceable for CLV, diagnostic
  STILL pending.

- **M13. Kalshi city-collision disambiguation via ticker [post-freeze
  enhancement].** 08-22: ambiguity guard's first live firing — 8 legs
  refused on a day with NYY/NYM, CWS/CHC, LAA/LAD all active; four games
  degraded to one_sided rather than risk wrong-franchise prices. Correct
  behavior, but resolvable: event tickers encode both team codes
  (KXMLBGAME-26AUG242145CINSF-SF), so the matcher can disambiguate by
  ticker parse instead of title. Weekly recurrence expected (city
  collisions every Saturday-shaped slate).

- **M12. sync_matches skipped 53 unknown-team matches (ext IDs 849xxx),
  first seen 2026-08-21.** Correct skip, nothing in DB; WATCH — if the same
  53 warn daily, add an aggregate one-liner instead of 53 WARNING rows.
  API-side listing oddity, low priority.
  UPDATE 08-22: same 53 skipped again — persistent, not transient. GPT layer
  flagged training-sample risk; direction corrected: skips can't contaminate
  (nothing enters DB) but could MISS legit games. Identity diagnostic issued
  (fetch one 849xxx game, read team/league names). If exhibition/alt-league:
  correct skip, quiet the log. If MLB under variant names: alias fix.
  08-24: per-id lookup returns empty (200, no errors — key fine, id not
  standalone-queryable); probe v3 issued: filter the season listing locally,
  print the 53 matches' team names.

- **S10. Injury freshness in input_quality [small, post-launch — from the
  2026-08-20 rehearsal]** Injuries are a live model input (xG adjustment in
  the predict path) but input_quality doesn't state when they were last
  synced. Export-the-gap rule applies: add injuries.last_synced (or a
  staleness flag vs the predict timestamp) so the GPT layer can discount an
  adjustment made on old data. Interim mitigation: sync-injuries is now a
  mandatory step in the Friday/Saturday chains (S5 doc). NOT a rehearsal-day
  change — code freeze held.

- **S7. Team news = soccer's pitcher confirmation [export-the-gap now,
  Stage-1 later]** The starting XI (announced ~1h pre-kickoff) is soccer's
  biggest information asymmetry — rotation, European hangovers, rested
  strikers. v1 tracks NONE of it, and that's fine ONLY if exported:
  input_quality says lineups:none explicitly (house rule — missing information
  gets exported, not hidden). DISCOVERY 2026-08-15: the API-Football adapter
  ALREADY wraps /injuries and /fixtures/lineups — Stage-1 lineup/injury
  ingestion needs no new integration, just consumption + tracking-first
  plumbing (unused_context, NOT the model). Flagship post-launch Stage-1
  candidate alongside xG strengths.

- **S8. Soccer totals scope decision [decide before launch, ~1 hour]** MLB
  totals ship with full instrumentation (projection, pulse, shrink config,
  high-band ledger). Soccer O/U 2.5 has NONE of that machinery
  (totals-calibration is baseball-flavored). Shipping side predictions with
  half-instrumented totals violates measure-everything-you-emit. DECIDE:
  extend the pulse to goals, or explicitly EXCLUDE totals from the soccer
  export v1. LEAN: exclude-then-extend — over_prob/line fields null with a
  totals_available:false flag, extend the pulse as a post-launch item.

- **S9. Data sources beyond API-Football [survey done 2026-08-15]**
  API-Football (ENABLED, tested locally by Anthony) is the primary: fixtures,
  teams, odds, standings + already-wrapped injuries/lineups/statistics
  (statistics typically includes per-team xG — VERIFY on the active key with
  one finished 2025/26 fixture before counting on it). Gap-fillers, MLB-style:
  (a) football-data.co.uk — free historical CSVs incl. CLOSING ODDS
  (B365 etc.) back many seasons. HIGH VALUE: joins the leakage-free backtest
  to real closing prices -> an honest historical model-vs-market read for
  soccer BEFORE a single live bet — the MLB side never had this pre-launch.
  ~Half day: CSV ingest + join on date+teams + backtest CLV column. Do this
  one; it converts the July-8-style CLV verdict from "wait months" to
  "compute this week."
  **BUILT 2026-08-15:** `soccer-odds-history` (ingest, Pinnacle-close
  preferred -> B365C -> AvgC, is_closing=True, date+both-teams matching via
  the new sport-generic team_aliases module, ambiguity refused, unmatched
  named) + `market_comparison` wired into soccer-backtest output (model vs
  de-vigged close: log-loss gap, per-outcome |gap|, pick edge split by sign
  with hit rates). team_aliases.py is the S3 alias home — MLB
  sacramento/oakland entries already seeded. NEXT: run ingest for 2024/25,
  then soccer-backtest — soccer's own thermometer verdict, pre-launch.
  **VERDICT 2026-08-15 (PL 2024/25, n=340, rho=0 — see caveat):** the market
  read is unambiguous and it is the MLB July-8 shape, worse: model log-loss
  1.0092 vs close 0.9735 (+0.036); mean |model−close| 8.7pp(H)/8.4pp(A) —
  the model sits FAR from consensus on win legs; mean pick edge vs close
  +5.0pp with 70% of picks (237/340) claiming +10.9pp average edge and
  hitting only 47.7%, while model-below-close picks hit 57.3%. BOTH tails of
  the disagreement graded to the market. This is the favorite-overconfidence
  defect expressed in market terms — S1 is not a nicety, it is THE launch
  item. CAVEAT: run used rho=0 (soccer-backtest didn't load production
  config — FIXED same day: --rho defaults to production's stored value);
  rho=-0.10 improves log-loss to ~1.008 but the sweep already showed
  overconfidence is rho-independent. S1 ACCEPTANCE now market-based, in
  priority order: (1) mean pick edge vs close collapses +5.0pp -> within
  ±2pp; (2) positive-edge bucket's claimed-vs-actual gap closes; (3) 70-90%
  home bands within ~1 SE; (4) log-loss gap to close narrows from +0.036;
  (5) draw gap stays <=2pp (don't undo rho). Re-run the market comparison at
  each candidate elo_goal_coeff — the sweep now has a market-referenced
  scoreboard, a luxury no MLB recalibration ever had.
  (b) football-data.org free tier — fixtures/results redundancy (the
  MLB-Stats-API analog: free second source when API-Football hiccups).
  (c) Understat/FBref — free xG per match if API-Football's tier lacks it;
  scraping-based, fragile, POST-LAUNCH only and only if (a)+S6 justify the
  strengths upgrade.
  (d) Open-Meteo — already integrated; soccer weather effect is marginal.
  Skip for v1.

- **TRANSFER WARNINGS (from the MLB discipline stack, written down so they're
  not re-litigated):** (1) soccer earns its OWN CLV verdict — the July 8
  "thermometer, not income engine" conclusion is an MLB finding; inheriting it
  in either direction is unearned (S9a makes the soccer verdict computable
  from history). (2) PL-ONLY scope guard — the cup/Elo machinery makes CL/FAC
  tempting; multi-competition before PL discipline is proven is exactly the
  creep the MLB side avoided.


- **2026-08-11 (fix: set-soccer-config AttributeError)** — _current_production_version
  returns the version STRING, not the ModelVersion object (I assumed the object).
  Fixed to query the ModelVersion row by version (same 2-step the MLB
  _apply_production_config_edit uses). Compiles; ModelVersion.parameters confirmed.

- **2026-08-11 (Kalshi in exports — the missing serialization)** — Diagnosed why
  export files showed no Kalshi despite sync storing prices: export's
  _summarize_market read the Odds table only; sync-kalshi writes
  OddsSnapshot(source="kalshi", market="ML"). Fix: collector loads latest Kalshi
  snapshot per (match, selection); market block gains a "kalshi" sub-block —
  raw_yes_prob + raw_sum, sum-normalized "prob" (two-sided only, normalized flag
  otherwise), model_edge_pp vs normalized Kalshi, vs_book_pp (book-vs-Kalshi
  disagreement, the classifier-relevant column), captured_at. Kalshi-only games
  export the block even with no book odds. Kept STRUCTURALLY SEPARATE from book
  consensus (never blended). Unit + scratch-DB integration tested.

- **2026-08-12 (Kalshi matcher rewrite — date gating + refusing ambiguity)** —
  First export with Kalshi blocks exposed the matcher assigning prices to WRONG
  games: no date constraint (80 open markets span days; Friday STL market
  matched tonight's STL game), shared-city ties resolved by iteration order
  ("New York Y"/"New York M" both tokenize to {new,york} — a Mets ~44% price
  landed on the Yankees), and the single-letter disambiguator Kalshi provides
  was filtered out by the len>1 token rule. Rewrite: three-stage gate —
  (1) occurrence_datetime within 5h of first pitch (also resolves DH legs);
  (2) BOTH title teams must overlap different sides of the candidate game;
  (3) side via yes_sub_title with initial-letter tiebreak (c→Cubs, w→White
  Sox); ties REFUSED and counted as ambiguous, never guessed. Dedupe one price
  per (game, side)/run. CLI reports ambiguous separately. "Matched 78" was
  false confidence; honest counts are lower and correct. Pre-fix
  source="kalshi" rows purged (untrustworthy record). Nine matcher tests.

- **2026-08-13 (sync_pitchers business-date fix)** — Anthony spotted the daily
  sync misbehaving past midnight UTC. Two defects, one root cause: batch
  probables fetch bucketed by UTC date while MLB's schedule API interprets
  dates as LOCAL business dates (log tell: "15/9", "14/19" batch/bucket
  mismatches — worked only via accidental dict merging); and confirmed-vs-
  projected was a <=4h countdown, permanently branding West Coast games
  "projected" on afternoon runs. Both now use business date = UTC-8h (no MLB
  game starts 00:00-08:00 UTC). confirmed = game is on today's slate. Audited
  the rest of the daily chain: sync-matches, sync-umpires --today,
  capture-weather all already correct (local-date comparisons). Tested at the
  exact failing run time. Next-day verification: "15/15" clean logs, 15/15
  confirmed in export.

- **2026-08-14 (starter shrinkage on starter-RELEVANT innings, config-gated)** —
  Code-read correction: the proposed "add starter shrinkage" ALREADY EXISTED
  (30 IP halflife + 61/39 bullpen blend + opener handling). Real gap: shrink
  denominates on TOTAL IP, so converted relievers (Drew Anderson: 67.3 IP but
  3 GS, mostly relief innings) enter ~70% unshrunk on a sample that mostly
  doesn't transfer (times-through-order). Built starter_eff_ip_enabled /
  starter_ip_per_start on BaseballConfig (run_shrink template: off by default,
  set-config whitelisted, flows into stored params). effective_ip =
  min(ip, per_start x GS). Baseline slate data CORRECTED the default: 6.0
  clipped workhorse aces (Yamamoto 6.63 IP/start); shipped at 7.0, which spares
  every full-time starter and still bites relief-heavy profiles. Pure helper
  starter_shrink_weight() unit-tested incl. legacy bit-identity. ENABLED on
  production 2026-08-14 after a same-DB-state before/after diff (exactly one
  starter capped — Pfaadt 85.7 IP/11 GS — matching the math to the digit).
  VERIFICATION IS FORWARD-ONLY: backtest cannot see the pitcher layer (no
  as-of-date pitcher stats — same constraint documented in input_candidates),
  so this follows the set-config protocol: forward ledger of games where the
  cap bit (visible in starter_detail) vs the rest, multi-week horizon, revert
  to false if the ledger shows nothing.

- **2026-08-14 (export visibility: starter_detail + input_quality)** — Two
  export additions so the GPT layer sees what the model KNOWS, not just raw
  stats: (1) factor_breakdown.home/away_starter_detail — raw ERA, IP, GS,
  effective_ip, shrink_w, shrunk starter-component ERA (the raw→shrunk→blended
  trail; the missing middle step is how both audit layers misread Anderson's
  handling). (2) input_quality block per row — per-side starter listed/kind/
  stats-present/ip/gs/shrink_w/ip_capped, starters_known, missing_starter_
  shrink, book_odds count, kalshi two_sided/one_sided/absent. Motivating case:
  two Kalshi-only games where the model said ~50/50 on thin inputs and nothing
  in the row said "trust this less." Descriptive, NOT a score — consumer
  applies its own discount. Also fixed export-results summary to count only
  graded totals ("3/7 (2 no line)" not "3/9").

- **2026-08-14 (bullpen recent-form: already-in-model correction)** — Second
  code-read correction this week: "fold bullpen recent form into win
  probability" was proposed and REFUSED because it's already there —
  BullpenSeasonStats.recent_era blends at 0.30 into effective bullpen ERA
  (Phase 12.4), ~12% of the recent-vs-season gap on whole-game ERA. Open
  questions (weight tuning, partial double-count vs team RA) are historically
  untestable (current-snapshot stats). Disposition: change nothing; grade
  swing-flag games vs rest on the forward ledger via the exported
  bullpen_detail. Pattern note for future sessions: three times this week a
  proposed change already existed or the proposed test couldn't see the layer
  — READ THE CODE FIRST before turning suggestions into commands.
