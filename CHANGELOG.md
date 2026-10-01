# Changelog

Human-readable record of what shipped, newest first. Deep detail and the
reasoning behind each change live in `BACKLOG.md`; this file is the summary.
Every drop adds an entry going forward.

## 2026-10-01 (#157: morning chain in two network phases; compare_exports --since)
- `docs/CLI.md`: the laptop morning chain runs in two phases. Phase 1 runs
  the statsapi steps under the VPN. Then quit the VPN and bring Tailscale
  up. Phase 2 runs the host pull/compare under Tailscale.
- `compare_exports.py --since N` (default 3) compares only exports dated
  within the last N UTC days, plus undated files, so settled exhibits stop
  re-printing. The skipped count is printed, and `--since 0` compares
  everything.

## 2026-09-30 (#148: release model — main = BETA, production = tags)
- `deploy/hosting/sp_deploy.py` deploys the latest `vX.Y.Z` tag (detached)
  or an exact `--tag`. It never pulls `main` and refuses when no tag exists.
- Every receipts line carries `release` (`v1.0.0` / `BETA main@sha` /
  `UNTAGGED@sha`). Boot, chain and `sp_receipts.py` output print it.
- `scripts/release_notes.py`: the CHANGELOG slice since the previous tag.
- Ledger: `release` label and a per-release milestone (`v1.0.0`).
  `docs/RELEASES.md` holds the promotion ritual and the hotfix path.
- Fixed #149: the deploy read a host-rewritten RESULTS.md as `ESULTS.md`
  and refused.
## 2026-09-30 (#79: NCAA data audit)
- `python cli.py ncaa-audit` (read-only; `--season`, `--limit`) — the audit
  the architect ordered before any NCAA v2 (v1 verdict PROVISIONAL: log-loss
  PASS, calibration FAIL, 2025 home rate 0.489 implausible vs 2026's 0.708).
  Over the gate's stream WITHOUT its exclusions, per season: home rate by
  verbatim stage and by UTC month, repeated/reversed pairings with dates,
  two labelled HEURISTICS (home side had fewer prior-season games; home rate
  when both sides are "established" >= 8 games vs not), an inventory of
  every stored field that could indicate a neutral site or division, and a
  suspects list. Infers nothing; writes nothing. Module
  `src/walters/ncaa_audit.py`; tests `tests/test_ncaa_audit.py`.

## 2026-09-30 (gate verdicts; NHL shot-quality probe + unlinked-games audit)
- Verdicts logged: S19 REJECT (+0.0005 vs 0.0050, #83 closed); NHL v5 FAIL
  (0.6912 vs 0.6866; goalie information −0.0003 = the goalie floor; NHL
  stays market-only, reopening now needs xG-class shot data); NCAA v1
  provisional pending a data audit.
- `scripts/nhl_pbp_probe.py`: read-only probe of NHL play-by-play shot
  events (location, type, shooter, situation), 2023-24 onward.
- `nhl-goalie-audit`: why NHL games are unlinked (UTC-boundary offsets and
  more), with an opt-in `nhl-goalie-sync --tolerance-hours`.

## 2026-09-30 (#138: plain soccer-backtest evaluates production params)
- `soccer-backtest` (plain report) now uses production's `elo_goal_coeff`
  (0.0008) as well as its `dixon_coles_rho`; it used the default 0.0023.
  **Historical plain-report numbers shift**: runs before this change are
  not comparable. The S19 gate verdict was already on production params
  and is unaffected.
- The #137 / #140 / #141 / #139 pre-commitments are ratified (BACKLOG).

## 2026-09-30 (#79 NCAA v1: frozen gate + Elo candidate)
- `python cli.py ncaa-backtest` — the NCAA v1 gate, frozen before any run:
  train 2025, test = the finished 2026 games at run time (n and date range
  printed), pre/postseason excluded. Pass = log-loss <= the 2025 home-rate
  baseline − 0.010, every 10pp band with n >= 100 within ±5pp, final
  ratings 1000-2000; fewer than 500 test games = INVALID. `--baselines-only`
  prints the bar before any candidate is scored.
- Candidate `ncaa_elo_v1` (src/models/ncaa_elo.py): plain Elo, MOV + season
  regression, constants fixed a priori (k 24, home 55, mov_base 2.2,
  regression 0.25, default 1500), no selection. Read-only: nothing is
  written, no export changes; NCAA stays market-only until the architect
  rules on a verdict.

## 2026-09-30 (S19 + S20: soccer time-decay candidate, RPS reported)
- S20 (#84): the soccer backtest reports the Ranked Probability Score
  (H<D<A ordered) beside log-loss: `soccer-backtest` (calibration and
  model-vs-close blocks), an RPS column in `dixon-coles-sweep` and
  `elo-coeff-sweep`, and both arms of the S19 comparison. It is reported
  only and is in no acceptance criterion.
- S19 (#83): `soccer-backtest --candidate time-decay` scores production
  and a time-decay candidate on the same matches. The candidate weights
  the attack/defense fit by 0.5^(age_days/365); the 365-day half-life
  (Dixon & Coles 1997, ~373 days) was frozen before any run. The existing
  gate decides: candidate log-loss better by >= 0.0050, ties reject.
  It is evaluated on PL 2023/24 + 2024/25 + 2025/26, pooled. Backtest-only:
  nothing is written and production (v22) is unchanged. The frozen
  half-life, the evaluation set and four more choices wait on architect
  ratification.
- FINDING: plain `soccer-backtest` scores at the default elo_goal_coeff
  (0.0023), not production's 0.0008. It is left unchanged here; the S19
  comparison uses production's value.

## 2026-09-30 (#89: NO-side exec cost for away picks)
- On two-way markets (NFL/NHL/NCAA/MLB) the exports now carry the AWAY side's
  Kalshi cost: the NO side of the home contract (NO ask = 1 − home bid, NO
  bid = 1 − home ask), taker and maker, with the same per-fill fee as the home
  side (`away_bid`, `away_ask`, `exec_cost_taker_away`, `exec_cost_maker_away`).
- Soccer (1X2) away fields stay null: NO on HOME is draw-or-away, not an away bet.
- The Desk prices an AWAY pick from it ("… maker (join 0.xx, NO side)") and
  the ledger records those costs; pre-#89 exports and soccer still show
  "exec —". Informational only: no call, unit or tier change.

## 2026-09-30 (NHL-GOALIE: NHL API goalie ingest + v5 candidate)
- New `nhl_goalie_appearances` table and `nhl-goalie-sync`: per-game goalie
  appearances (starter flag, shots / saves / goals against) from
  api-web.nhle.com, mapped to our NHL matches, 2023-24 onward.
  `nhl-goalie-coverage` is the receipt.
- `nhl-backtest --candidate v5`: v1 + each starter's shrunk, decayed save%
  over league average as an Elo adjustment, through the frozen NHL gate.
  Constants are fixed a priori and await ratification before the run.

## 2026-09-30 (#88 re-fit: Kalshi fee rounding is fitted, not assumed)
- The per-fill ceiling failed its receipt (253/629 legs; the misses sat 1¢
  below it). `scripts/kalshi_fee_fill_receipt.py` now scores ceil /
  nearest / floor / banker's over every multi-contract leg (shards priced
  0.00 excluded), prints each rule's rate, and adopts one only at >= 95%;
  otherwise it prints the residuals.
- ADOPTED: Kalshi rounds each fill's fee to the NEAREST cent (542/548 =
  98.9%; ceil 45.3%, floor 54.7%). Exec costs move down by at most 0.1¢
  per contract (NFL 0.55/0.58: taker 0.597, maker 0.561).

## 2026-09-30 (Desk: PASS reasons in two classes)
- A Desk PASS is now tagged "no reference" (no two-sided reference, or too
  few books: greyed, with a "re-run at T-60" hint) or "below floor" (a real
  edge measured and declined). Presentation only: no call, unit or policy
  change. The summary splits the pass count.

## 2026-09-30 (#88 ruled: Kalshi fees round per fill)
- Fees are modelled as one ceiling per FILL of N contracts; the Desk
  assumes N = 10 (provisional until the B-track sizes units). Exec costs
  now carry fractions of a cent (NFL 0.55/0.58: taker 0.598, maker 0.562)
  and the Cockpit shows them to 3 decimals.
- `scripts/kalshi_fee_fill_receipt.py --csv` reproduces multi-contract
  fill fees from the Kalshi CSV (the receipt: five to the cent).
- DEPRECATION: the export's `kalshi_exec_cost` (= `exec_cost_taker`) is
  retired two Cockpit republishes from now (architect 2026-09-30). Read
  `exec_cost_taker` / `exec_cost_maker`.

## 2026-09-30 (#93 ruled: Kalshi maker and taker costs)
- Exports carry `exec_cost_taker` and `exec_cost_maker` (the ruled fee
  multipliers: game series taker M=1 / maker M=0.25, MLB pre-live M=0.5).
  `kalshi_exec_cost` stays as the taker alias.
- The Desk's exec edge and "fee-clears?" use the maker cost by default,
  with the taker cost as the fallback. Calls and units are unchanged.
- The ledger records both costs; imported fills are classified maker /
  taker from their fee, with an alarm for MLB fills at the live rate
  (doctrine: MLB is never executed live).

## 2026-09-30 (NHL-API-PROBE: the H2 goalie-source probe)
- `scripts/nhl_api_probe.py` is read-only. It probes api-web.nhle.com
  (schedule, boxscore goalie stats, roster, pre-game starter and lead time,
  2023–2025 depth) and MoneyPuck's projected-starters CSV, then prints
  FEEDABLE / NOT per need and the H2 reopening line.
- Run it on the laptop and on the host (the datacenter-IP receipt).

## 2026-09-30 (NHL shadow: the failed v1 as a greyed reference model)
- `export-nhl-predictions` writes the FAILED `nhl_elo_v1` for every NHL
  game in the next 36h. Every row is stamped `engine: model_shadow` and
  `gate_verdict: FAILED 0.6909 vs 0.6866`. Nothing is written to the DB.
- The Cockpit shows them greyed under "Reference model — failed gate".
  They never become a Desk call, a venue input or a ledger entry, and the
  window card ignores them.
- `nhl-shadow-grade` and a RESULTS.md shadow section report live CLV only
  (pick-vs-close, value-side). The `nhl-daily` host chain gains the export.

## 2026-09-30 (CORRECTION: soccer Kalshi read as two-way in the fixtures export, window card and line-move)
- CORRECTION, not a feature (#117). On soccer rows the window card's Kalshi
  home price was H/(H+A) even with the TIE leg present. So its venue gap
  and STALE-BOOK? flag compared a two-way number with a three-way book fair.
- A soccer set missing a leg was also labelled two-sided in the fixtures
  export (cups, UNL).
- Soccer now reads P(home) over HOME + DRAW + AWAY. A set missing a leg is
  "partial": no Kalshi price, exec fields, venue gap or Kalshi line-move.
  The Cockpit reads Kalshi-only 1X2 fixtures three-way.
- NFL, NCAA, NHL and MLB are unchanged. Receipt:
  `scripts/kalshi_soccer_twoway_receipt.py`.

## 2026-09-30 (ledger: auto-close reads "Closes #N" lines only)
- The ledger bot matched a closing keyword anywhere in a PR description,
  so a prose mention ("…which closes #111…") closed #111 under the wrong
  PR's name.
- It now reads only lines that start with the keyword (optionally after
  "Ledger:" or a list marker), such as "Closes #1, #2 and #3".

## 2026-09-30 (CORRECTION: soccer Kalshi sets missing a leg were normalized as two-way)
- CORRECTION, not a feature (#113). A soccer prediction row whose Kalshi
  capture lacked a leg (usually the TIE) was normalized over HOME + AWAY
  and marked two-sided, so its exported Kalshi `prob` was inflated.
- Such rows now ship `normalized: false`, `prob: null`, `missing_legs`,
  `input_quality.kalshi: "partial"` and null Kalshi cost fields. Complete
  1X2 sets and MLB rows are unchanged.
- The before/after receipt is `scripts/kalshi_soccer_incomplete_receipt.py`.

## 2026-09-30 (ledger: the bot closes a merged PR's "Closes #N" itself)
- GitHub did not register the `Closes #N` links of Claude-opened PRs, so
  merged work left its Issues open. The ledger bot now closes them on
  merge (Done), keeps a limitation open unless the PR says "Resolves
  limitation", and can replay an already-merged PR (`close-merged`).

## 2026-09-30 (Cockpit: the fun book; Kalshi quotes on MLB/soccer exports)
- The fills importer has a "fun" book: NHL and UNL singles with no
  system call, MVE combos, and non-sport markets. "Off-book other" is
  retired; the REALIZED table and the Copy P&L block print every book.
- MLB and soccer prediction exports gain `kalshi_bid` / `kalshi_ask` /
  `kalshi_exec_cost` (HOME contract, two-sided only; additive), so the
  Desk's exec-edge and join-bid columns work for baseball and soccer.

## 2026-09-30 (Cockpit fills: side from the ticker suffix; a fourth book; no default order)
- The Kalshi fills importer resolves the side from the ticker suffix first
  (`KX{FAM}GAME-{date}{AWAY}{HOME}-{SIDE}`, TIE = draw) and the title second
  ("{Team} wins — {Team}"). Stored fills are re-derived at classification,
  so the 33 "side not resolvable" fills re-classify.
- A fourth book, "system-pick, unlogged": fills that match a stored
  prediction (harvested from results exports) when no ledger call exists.
- The Open calls table shows "—" instead of a default "limit 0.59" on rows
  without a Kalshi ladder.

## 2026-09-29 (the ledger: Issues = state, BACKLOG = history, one Project board = order)
- A fixed label taxonomy (track: / class: / sport: / size: plus
  needs-ruling / needs-operator) and six dated or condition-bound
  milestones, in `.github/ledger/taxonomy.json`.
- `scripts/ledger.py` + the `ledger` workflow:
  - an idempotent bootstrap (labels, milestones, the backfill Issues,
    the board in queue order);
  - an Issue label lint (comments, never blocks);
  - PR title prefix -> track label;
  - `Closes #N` -> In progress / Done;
  - limitations close only with "Resolves limitation"; no closing by
    hand without a PR or a quoted ruling.
- The backfill manifest covers the queue, the open rulings, the
  operator actions and every known limitation, each linked to its
  BACKLOG commit + line.
- CLAUDE.md's queue is now a pointer to the board; `docs/LEDGER.md`
  holds the rules and the six views.

## 2026-09-29 (MLB PHASE A rulings)
- The four PHASE A rulings are logged:
  - empty stage on host-created rows is ratified;
  - the three-status map stands (the observed vocabulary was FT / CANC /
    NS);
  - MLB market-only rows on the host window card are accepted;
  - the doubleheader game-2 difference is waived in the compare
    ("apisports doubleheader gap"). The runbook carries the compare
    line.

## 2026-09-29 (MLB PHASE A: api-sports fallback for host MLB history; PHASE B closed negative)
- `sync-matches` / `sync-teams --competition MLB` use api-sports Baseball
  wherever `SP_SKIP_FAMILIES` names MLB (the DO host); the laptop keeps
  statsapi. Gate met: 100.0% score parity.
- Stage is never read from the provider's `week`: created rows carry
  stage NULL, and paired statsapi rows keep theirs. Status mapping is
  conservative, and a finished row is never downgraded.
- Known limitation, receipted every run: doubleheader game 2 is absent
  from api-sports. Existing rows are marked "apisports-unavailable",
  never fabricated.
- Host chain `mlb-history` + `sp-mlb-history.timer` (10:30 UTC): sync
  only, no MLB predictions on the host.
- PHASE B verdict logged: api-sports Baseball has no pitcher, bullpen
  or umpire feed. MLB predictions stay on the laptop.

## 2026-09-29 (MLB PHASE B probe: pitchers / bullpen / umpires from api-sports?)
- `scripts/mlb_phase_b_probe.py` is read-only. It classifies candidate
  api-sports Baseball endpoints and flags pitcher / bullpen / umpire
  fields, with a verdict per need.
- To be run on the laptop. The receipt is pending.

## 2026-09-29 (MLB-PROBE verdict + follow-up)
- Architect verdict logged: api-sports Baseball is GREEN for MLB
  schedule/results and AMBER for predictions (no pitcher, umpire or
  bullpen data).
- The probe fix: our DB stores status "finished" (lowercase), so score
  parity was never computed.
- It now prints score parity against the 99.5% PHASE A gate, a sample of
  disagreements, and every unpaired finished game with a doubleheader /
  UTC-boundary suspect read.

## 2026-09-29 (cosmetics lane C: utcnow sweep, MVE combo fills, ntfy topic validation)
- `datetime.utcnow()` / `utcfromtimestamp()` are replaced everywhere by
  `src/timeutil.py` helpers. These are built on `now(timezone.utc)` and
  stay naive UTC, so there is no behavior change.
- The fills importer classifies Kalshi MVE combos by leg content:
  sports legs → off-book sports parlays.
- An ntfy topic containing whitespace is refused at startup: chains fail
  loudly and never page the wrong topic.

## 2026-09-29 (late-news follow-on: T-90 injuries in the imminent tier, quarantine-class line moves)
- The window service's imminent tier syncs injuries for the NFL/soccer
  games kicking off within 2h. The sync is scoped per team, and the
  T-90 check now compares injury content.
- Line-move pages ignore quiet hours and go out at high priority.
- `late-news?` is also on the MLB and soccer prediction exports.
- Known limits logged: soccer line-move is Kalshi-only; MLB follows
  capture cadence.

## 2026-09-29 (MLB-PROBE: api-sports Baseball vs statsapi, read-only)
- `scripts/mlb_apisports_probe.py` reports coverage vs our 2025/2026
  MLB matches, ID mapping via the odds join, status vocabulary and
  postseason game types. No wiring.
- To be run on the laptop. The receipt is pending.

## 2026-09-29 (hosting: bootstrap catch-up — laptop completeness sweep)
- `bootstrap.py catch-up --reference <host fingerprint>`: for each
  competition-season where the laptop counts fewer games, it runs
  sync-teams then sync-matches.
- Dry run by default. `--apply` backs up first, receipts each season
  before and after, and stops at the first failure.

## 2026-09-29 (K-track: Kalshi fee schedule receipt; K2 join bid + order type/fill)
- Fee schedule receipt (July 2026 schedule): taker 0.07 is confirmed.
  Maker is 0.0175 × M, with M = 0 unless the series is listed.
  - The game-series maker multiplier is NOT verified: the PDF is
    unreadable from the build environment.
  - Kalshi rounds to the centicent per order, so our per-contract cent
    rounding overstates the fee (logged; unchanged pending a ruling).
- Desk: join bid (bid + 1¢) beside exec cost. A 1¢ spread shows
  "joining = taking".
- Positions record order type (limit/market) and fill price.

## 2026-09-29 (Cockpit K2: executable-edge display)
- The Desk shows exec edge = model − Kalshi (ask + fee) beside the fair
  edge, with "fee-clears?" at ≥ 4pp. It is informational only: no
  sizing, tier or call change.
- Positions record the Kalshi exec cost at claim and at execution.

## 2026-09-29 (MNF QB verdict; line-move alarm; T-60 closing-freshen doctrine)
- QB audit verdict logged: the cause was sync timing plus provider
  latency. The Chicago starter was absent from the provider's report at
  both pre-game syncs. The detection code is exonerated.
- New line-move alarm:
  - inside T-3h, a ≥ 6pp net move on book or Kalshi (stored snapshots,
    no provider calls) marks the row `late-news?` in the window card
    and the NFL export;
  - it pages on the card topic and triggers `freshen:<family>`.
- CLI.md doctrine: the game-day T-60 closing freshen is mandatory for
  model sports while the laptop is writer of record.
- The host-journal receipt for Monday's T-90 check is pending, to be run
  on the host (commands in the PR).

## 2026-09-29 (#63 rulings: value-side anchor timestamp on every grade)
- The architect ratified all four #63 decisions: all-sport scope, the
  earliest pre-kickoff book anchor, tagged quarantine shadows, and
  snapshot growth deferred to pruning.
- `nfl-grade` value-side lines now show the anchor and prediction
  timestamps, and flag an anchor that came after the prediction.
- `export-nfl-results` rows carry the value-side fields and anchor
  timestamp (additive).

## 2026-09-29 (Week 4 MNF rulings: value-side shadow, value-side CLV, QB feed audit)
- Cockpit: the Desk evaluates edge on every side. A value side that is
  not the top pick and clears 4pp logs a `value_shadow` at 0.25u
  notional.
  - It is graded like quarantine shadows and never staked.
  - It has its own counterfactual line, with promotion review at 30
    graded (policy v1.2 candidate).
- `nfl-grade` and RESULTS.md print value-side-vs-close beside
  pick-vs-close.
  - `sync-odds-football` now appends a book-consensus snapshot on every
    sync, which serves as the anchor.
  - Games without one are counted as unanchored.
- NFL QB detection: positions resolve by id, then name, then a unique
  initial+surname. QB/Quarterback both count. Still-listed players are
  no longer dropped by the 14-day filter.
- The export gains `positions_unresolved`.
- New read-only `nfl-qb-audit` (with `--live` for the H1/H2/H3 verdict).
  The receipt on MNF data must run on the host/laptop.

## 2026-09-28 (hosting: sp_run transient-step retry)
- sp_run retries a step that fails TRANSIENTLY (connection errors,
  timeouts, HTTP 5xx/429) twice, 15s then 45s. The receipt says
  `retried N`.
- A step still failing pages as before. Other 4xx and exceptions in our
  own code never retry.

## 2026-09-28 (Cockpit: execution-timing rule, policy v1.1 addendum)
- Positions carry claim_at (frozen claim price) and executed_at (default:
  last freshen before kickoff; or an explicit, recorded "Execute now").
- Grading settles at the execution price, with a claim-price counterfactual.
  The P&L block gains a "claim vs exec" column and an EXECUTION TIMING
  section. No sizing changes.

## 2026-09-28 (hosting: ncaa-market Thursday run)
- sp-ncaa-market adds Thu 16:00 UTC (Thursday-night slates' fixtures
  file). On the host: re-run install.sh after the pull.

## 2026-09-28 (hosting: exhibit 1 fixes — injuries, keyed comparator, SHA-stamped exports)
- nfl-predict syncs NFL injuries first (chain gap); a CI guard audits every
  prediction chain (MLB exempt: no injury source).
- compare_exports keys game rows on (kickoff, home, away), not match_id,
  and names unmatched rows.
- Every JSON export carries its producing `git_sha`. "Code-version skew"
  is an explained class only when both SHAs are present and named.
- Exhibit 1's divergence log is recorded in the runbook.

## 2026-09-28 (hosting: nhl-daily single-day syncs)
- nhl-daily syncs yesterday/today/tomorrow as three single-day calls that
  the hockey adapter honours, instead of one silent whole-season pull.

## 2026-09-28 (hosting: NHL opening-day gate + season gates as config)
- nhl-daily activates 2026-09-29 (2026-27 opening day; was the 2025-derived
  2026-10-07).
- Season gates are configurable per chain (`SP_NHL_ACTIVE_FROM` in
  host.env; malformed fails loudly). Every run prints and receipts
  `active from <date> [<source>]`.

## 2026-09-28 (hosting: P4 Tailscale SSH status)
- Tailscale SSH is enabled server-side (`sudo tailscale set --ssh=true`
  returned silently). The invalid `tailscale status --json | grep -i ssh`
  receipt is dropped. Client-side verification is pending (Mac MagicDNS);
  the tailnet-IP door is the proven standard, and the P4 receipt uses it.

## 2026-09-28 (exports: current-slate windowing)
- Prediction exports default to the current slate: kickoffs in the next
  36h for NFL and soccer. MLB keeps its one 08:00-UTC slate-day (ruling:
  it plays daily). Use
  `--week` (NFL) / `--days N` for the full look-ahead. Explicit dates keep
  their slate-day meaning. Generation is unchanged; only the file's rows
  are scoped.
- A `window:` receipt line is printed. freshen:SOCCER now uses the 36h
  default (a one-slate closing file).

## 2026-09-28 (hosting: H1b day one + runbook field amendments)
- H1b parallel week started 2026-09-28 13:45 UTC: 12 host timers,
  SP_PARALLEL_MODE=full, MLB timers off by ruling. The earliest cutover
  decision is after 2026-10-05 13:45 UTC (criterion 1: 7/7 days).
- Runbook P4: sp gets NOPASSWD sudo + Tailscale SSH (receipt-gated) before
  root is sealed. The console is emergency-only after P4. Mac VPN clients
  conflict with Tailscale (quit them before tailnet steps).

## 2026-09-28 (hosting: pull-exports lane)
- `deploy/hosting/pull_exports.py`: the laptop pulls the host's exports/
  over the tailnet into exports/host/ (never its own exports/). The host
  comes from SP_HOST_ADDR. Newest-wins, idempotent, all-or-nothing on an
  unreachable host, receipted (pulled / unchanged / newest window_24h.json).
- `scripts/setup_export_pull.sh`: optional hourly launchd job at :10.
- Docs: CLI.md hosting table, runbook T12b (laptop pulls; push is H2).

## 2026-09-28 (Cockpit: ledger doubling fix)
- Root cause: re-logging a multi-day file on a later day re-captured every
  call under a new log_date key (reproduced: 12 → 24). Import ledger merged
  by stored id. The Kalshi CSV import only re-rendered the doubled totals.
- The ledger key is enforced on every write path; import merges by
  recomputed key. Unit of account = the POSITION (ratified): a re-log on a
  later day reprices that position in place, never a second row.
- New "Dedupe ledger" repair (reports how many it removed) + a stored-
  duplicates warning on the Ledger tab.
- Capture only before kickoff (multi-week files no longer log played
  games); "Copy ledger (JSON)" with a text-box fallback + "Import pasted".
- scripts/cockpit_ledger_verify.py: 21/21 (import twice → identical totals).

## 2026-09-27 (window service: freshen chains + proximity tiers)
- freshen:NFL / freshen:MLB / freshen:SOCCER defined; the window service
  triggers them on T-90 news (chain lock, one per family per hour, MLB
  never on the host), then rebuilds the card.
- Proximity tiers: far (>6h) schedule check only, near (2-6h) + odds and
  Kalshi, imminent (<2h) + T-90 detection; receipt counts steps skipped.

## 2026-09-27 (window service: Next-24h card + delta pages)
- Hourly `window` chain (sp-window.timer, enabled on H1b day 1): single-day
  match syncs, window-scoped odds + Kalshi, then `window-card` →
  exports/window_24h.json. No model runs; model fields copied from the
  canonical exports.
- Delta pages to a second ntfy topic (NTFY_CARD_TOPIC), quiet hours
  00-07 ET except quarantine flips, one 08:00 ET digest.
- Quota line on every chain receipt.
- Cockpit "Next 24h" tab (headless receipt 12/12).

## 2026-09-27 (H1a CERTIFIED PASS)
- Host bootstrap certified: compare clean, no waivers. The laptop was the
  side short 67 UEL 2024/25 games (clubs never team-synced), now fixed.
- Law recorded: sync-teams before sync-matches for every new
  competition-season (CLAUDE.md, CLI.md).
- compare rows label each count laptop / host.

## 2026-09-27 (fingerprint receipts + hardening)
- bootstrap explain / explain-diff: the counting predicate, the same rows
  counted four ways, and every uncounted row's status/status_raw/stage/
  external_ids, diffed laptop vs host.
- Fingerprint groups by competition_id (LEFT JOIN, orphans labelled),
  self-checks against raw COUNT(*); compare sums duplicate status entries.
- remove_allstar_rows dry-run prints the NFL teams with the fewest games.

## 2026-09-27 (host Pro Bowl cleanup, authorized)
- deploy/hosting/remove_allstar_rows.py: host-only, receipted removal of
  pre-exclusion Pro Bowl rows (dry-run default; --apply backs up first,
  cascades through declared FKs in one transaction, prints post-counts).
- Event backups (_precleanup_, _prerefresh_) never count as the daily.
- Waiver policy: real provider drift only; UEL 2024/25 needs none.

## 2026-09-27 (H1a compare rulings: Pro Bowl exclusion, waivers, EL1/EL2 refresh)
- NFL adapter excludes Pro Bowl / all-star games and teams, printing each
  excluded row.
- bootstrap compare --waive COMP:SEASON:reason: row still printed as
  WAIVED, recorded in the receipt.
- Monday soccer-refresh (chain + routine doc) syncs EL1/EL2 2026/27 first.
- Fingerprints embed the producing bootstrap.py git blob SHA; compare
  refuses version-mismatched or unstamped fingerprints (the UEL 269 vs 202
  delta was version skew, not data).

## 2026-09-27 (bootstrap --skip-family: MLB Stats API blocks datacenter ASNs)
- bootstrap.py --skip-family MLB: MLB sync-teams/sync-matches receipted
  SKIPPED-ASN, numbering unchanged (resume --from 8); compare reports the
  family N/A-host.
- Runbook: MLB is a laptop duty; host MLB timers off; post-cutover egress
  is an H2-era decision.

## 2026-09-27 (Hosting H1 phasing: fresh bootstrap first)
- Runbook re-ordered: H1a fresh bootstrap (host syncs its own DB;
  acceptance = BACKLOG fingerprints reproduced), H1b independent parallel
  week, H2 cutover = the one .backup migration (why it can't be skipped).
- deploy/hosting/bootstrap.py: fingerprint / plan / run / compare.
- compare_exports: divergence classes = capture timing + provider
  pagination.
- Model registry seed (ratified): production model_versions rows seeded
  at bootstrap (config only; books stay empty); compare verifies model
  identity; the four model-bearing timers enable with the rest.
- Cutover criterion 3 amended before day 1: "capture timing or explained
  provider pagination, each explained".

## 2026-09-27 (Hosting H0 final four; FOUND SAFETY GAP logged)
- Paging via ntfy.sh (NTFY_TOPIC in .env); held PASS pages and logs.
- Backups: DO weekly on + nightly laptop pull (deploy/hosting/pull_backup.py,
  scripts/setup_backup_pull.sh); host retention 14 dailies, prune
  report-only until the first manual prune is reviewed.
- CLV captures confirmed on America/New_York; NCAA timer enabled.
- On the record: improve auto-promoted on PASS (masked by 36 rejections);
  closed by hold-on-pass + ratify-candidate.

## 2026-09-27 (Hosting H1: systemd pack + runbook, inert until provisioning)
- deploy/hosting/: chain definitions (CI-checked against cli.py), sp_run
  receipts writer, .backup/prune/notify/boot-receipt/deploy scripts,
  migration pack/verify/install, parallel-week export diff, 21 systemd
  unit/timer files, install.sh (enables nothing).
- docs/specs/hosting-h1.md: provisioning runbook (BROWSER/TERMINAL),
  frozen cutover criteria, H0 rulings record, 4 open items.
- H0-5 guard: `improve --hold-on-pass` holds a PASS and pages;
  `ratify-candidate` promotes on explicit ratification. Default unchanged.
- CLI.md: pre-slate `sync-umpires --today`; improve/ratify rows.

## 2026-09-27 (Cockpit: Kalshi fills import, two-book accounting)
- Ledger tab: "Import Kalshi CSV" -> REALIZED section (system-matched /
  off-book sports / off-book other; staked, fees, pre-fee, net, avg fill,
  fees % of loss) + plausible-match review list; in the Copy P&L block.
- CSV mapping verified on the real Kalshi export header; trailing-30-day
  avg fill + fee per $ staked (ledger-level).
- scripts/cockpit_fills_verify.py (20/20, real header).

## 2026-09-27 (K1: Kalshi bid/ask stored; executable-cost fields)
- odds_snapshots.yes_bid / yes_ask filled by every Kalshi sync going
  forward. Run `python migrate_kalshi_quotes.py` after merge, before any
  chain.
- NFL predictions + fixtures exports add kalshi_bid, kalshi_ask,
  kalshi_exec_cost (ask + fee; fee formula ARCHITECT-VERIFY) —
  informational until the executable-edge ruling.

## 2026-09-27 (K0: Kalshi storage receipt)
- `scripts/k0_kalshi_storage_probe.py`: read-only probe of what a stored
  Kalshi snapshot holds. Code read: only a derived prob (bid/ask mid,
  single side, or last price) — bid/ask are not persisted.

## 2026-09-27 (cosmetics batch)
- nfl-backtest verdict text for the live era (provenance/regression);
  stale rehearsal docstrings updated.
- export-nfl-results no longer writes the fossil `"rehearsal": true`.
- docs/CLI.md: sync-matches options, sync-kalshi-ncaa, daily backup,
  NFL LIVE section, full Kalshi series list. .env.example: football and
  hockey API keys. api_hockey docstring matches its actual key fallback.

## 2026-09-27 (U2: NFL export "why" fields)
- NFL predictions export adds elo_home, elo_away, elo_gap,
  home_adv_applied, rest_days_home, rest_days_away. Additive only.
- export-nfl-predictions warns (ELO DRIFT) when an NFL game finished
  after the predictions were written; silent otherwise.

## 2026-09-26 (Cockpit v0.4 — P&L / self-grading organ, policy v1.1)
- tools/cockpit.html: Ledger tab (localStorage bd_ledger_v1, export/
  import), "Log today's calls", venue-edge engine (shadow, 0.25u),
  results/fixtures grading intake, by-engine reports, equity + quarantine
  counterfactual, per-rule attribution, Copy P&L block, non-claims.
- docs/specs/cockpit-v04-pnl-organ.md (spec, verbatim).
- scripts/cockpit_v04_verify.py: headless capture -> grade -> report
  check (24/24).
- Venue-edge charter narrowed (ruling): market-only family only (NHL,
  NCAA, cups when priced); model sports (NFL etc.) emit model_edge only.
- venue.py: doc line — fixtures' kalshi.prob is the raw stored value.

## 2026-09-26 (NFL export: STALE-BOOK? venue flag)
- NFL predictions export adds kalshi_prob, venue_gap_pp and venue_flag
  ("STALE-BOOK?" when |book fair - Kalshi| >= 8pp). Warning only —
  quarantine unchanged. export-nfl-predictions prints the flagged games.
- Logged: vetted verdicts (NFL FAIL, NCAA INSUFFICIENT-REF) and the
  stale-at-source football moneyline finding.

## 2026-09-26 (full-loop ruling logged: venue-edge engine)
- Docs only. Architect ruling: a second recommendation engine
  (venue_edge: book fair vs Kalshi, |div| >= 5.0pp, fixed 0.25u, shadow)
  beside model_edge; ledger reports by engine; policy -> v1.1. Build
  held for the v0.4 spec.

## 2026-09-26 (spread-fallback check vetted; fallback dark)
- `spread-fallback-check`: per-row ML_books + capture timestamps/gap;
  verdict on the vetted set only (ML_books >= 4, gap <= 24h; same 3.0pp
  bar); UNRELIABLE-REF rows printed; INSUFFICIENT-REF when vetted n < 10.
- Spread fallback gated DARK (`FALLBACK_LIVE = False`): exports carry
  1X2-sourced fair prices only until a vetted PASS.
- Logged: lane 6 closed (scope clean, gate 0.6361 PASS), score-90 HOLD,
  quarantine ruling ratified as built, #27 lands as a draft.

## 2026-09-26 (hosting H0 draft, for review)
- Docs only. `docs/specs/hosting-h0.md`: VPS candidates, Tailscale-only
  posture, systemd unit inventory from the CLI.md chains, `.backup`-API
  migration runbook (checksums, 7-day parallel run), receipts-log
  format, CLI.md/cli.py discrepancies, ARCHITECT-RULE open questions.
  Draft for architect review — not a decision; nothing deployed.

## 2026-09-26 (spread->win-prob fallback, american football)
- NFL/NCAA games with no 1X2 consensus but posted spreads now get a
  spread-derived fair (normal margin; median book home line; sigma
  frozen a-priori NFL 13.45 / NCAA 16.5). Additive export field
  `fair_source` ("1X2" | "spread_derived") on every market block, plus
  `consensus_home_spread` / `spread_sigma` on derived blocks. NFL
  quarantine/divergence unchanged (1X2 only). Receipt command:
  `python cli.py spread-fallback-check --competition NFL|NCAA`.
  Acceptance receipt pending Anthony's real run; bar 3.0pp frozen
  before results.

## 2026-09-26 (data/ created at connect time)
- Importing the package no longer creates an empty data/ directory; the
  SQLite directory is created on first connection instead.

## 2026-09-26 (sync-odds-football rename)
- `sync-odds-nfl` renamed `sync-odds-football` (covers NFL + NCAA); the
  old name remains an alias — no chain changes needed.

## 2026-09-26 (NCAA book-market finding logged)
- Docs only. College books post spreads, not moneylines: 12/116 book
  consensus vs Kalshi 99/116 — Kalshi-primary confirmed. Queued:
  spread->win-prob fallback (K-track, after Cockpit v0.4, architect
  spec); `sync-odds-nfl` -> `sync-odds-football` rename (next daily batch).

## 2026-09-26 (NFL model paths scoped to competition NFL)
- Ratings, backtest pot, prediction set, export and grading now select
  Competition.code == "NFL" explicitly (NCAA shares Sport.NFL).
  predict-nfl and nfl-backtest print a scope line (teams, games,
  competitions) with a SCOPE ALERT on contamination.

## 2026-09-26 (H2 goalie probe verdict: NEGATIVE)
- Docs only. The hockey provider has no goalie/lineup/player endpoints
  (only /games/events answers). H2 reopens only via an external data
  source; NHL market-only indefinitely. Bounded authorization closed.

## 2026-09-26 (migrate_score_90 invariant revised)
- Receipt prints breaching rows verbatim + the AET/PEN stage table.
  Revised law: FT 90'==score; AET/PEN 90'<=stored per side; level at
  90' only for single-match ties (stage-based). No column changes —
  re-run `python migrate_score_90.py` after merge.

## 2026-09-26 (H2 probe fix; morning findings logged)
- `scripts/h2_goalie_probe.py`: prints one raw /games object verbatim
  first; date/timestamp parsing tolerant of the hockey string shape
  (fixes the `_game_ids` crash).
- BACKLOG: architect findings — NHL 20-25% past-regulation (status_raw
  splits); lineup probe GREEN (XI from ~2015, minutes from ~2018).

## 2026-09-26 (soccer ET flag + 90-minute score)
- Football adapter stores status_raw (FT/AET/PEN) and score.fulltime in
  new matches.home_score_90 / away_score_90. Storage only — scores and
  results unchanged. Run `python migrate_score_90.py` after merge
  (receipt includes the 90-minute invariants).

## 2026-09-26 (lineup-history probe)
- `scripts/lineup_history_probe.py`: read-only probe of API-Football's
  per-match lineup history — declared coverage per season plus spot
  checks (lineups + per-player minutes). No DB access, no wiring.
  Anthony runs it and pastes the output to the architect.

## 2026-09-26 (H2 goalie/lineup probe)
- `scripts/h2_goalie_probe.py`: read-only probe of the hockey provider
  for starting-goalie / lineup data — endpoints, fields, historical
  depth, pre-game availability. No DB access, no wiring. Anthony runs
  it and pastes the output to the architect.

## 2026-09-26 (NHL raw status storage)
- matches.status_raw: the provider's status code kept verbatim; the
  hockey adapter stores FT/AOT/AP (OT/SO wins distinguishable). Run
  `python migrate_status_raw.py` after merge, then a full NHL sync.

## 2026-09-26 (mission declared)
- CLAUDE.md: Mission section (architect, verbatim) at the top; queue
  re-ranked — Cockpit v0.4 P&L/self-grading at the head, K-track
  (Kalshi-executable edge accounting) and B-track (bankroll doctrine)
  opened behind it; closed items moved to a record list. Docs only.

## 2026-09-25 (NHL Phase 2 closed; market-only launch wiring)
- nhl_elo_v4 FAIL ratified (0.6907). Ledger v1 0.6909 / v2 0.6921 /
  v3 0.6952 / v4 0.6907 — schedule-only floor ~0.691 vs bar 0.6866.
  NHL model track suspended; Oct 7 launch is market-only.
- `export-fixtures`: Kalshi presence, latest pre-kickoff book consensus,
  printed odds-label receipt; NHL-ready. Cockpit: fixtures header +
  Kalshi fixed. Docs: NHL daily market-only chain.

## 2026-09-25 (NHL candidate v4 — last schedule-only; cup track suspended)
- nhl_elo_v3 FAIL ratified (0.6952). `nhl-backtest --candidate v4`: v1
  form, 12-point shrink grid (k 3-6 x home adv 35/40/45), v3 selection,
  2025 once. If it fails: no v5, Oct 7 market-only, track suspends
  pending the H2 goalie probe.
- Cup fix-v2 re-exam FAIL (14.76pp; inversion cleared): cup model
  track SUSPENDED for the season (rotation information floor); EFL/CL/
  UEL market-only; machinery stays merged.
- CLAUDE.md production state + queue status updated.

## 2026-09-25 (cup fix-v2 — gate-class)
- Cup re-exam FAIL ratified (sign inversion 2/5, mean 18.11pp).
- Cup elo_goal_coeff by context (same-/cross-league), tuned on prior
  cup matches with the exam's seasons excluded; `cup-exam` tunes then
  prices (`--cup-coeffs base` reproduces the old exam). League pricing
  untouched; nothing persisted.
- CLAUDE.md: market-is-a-reference doctrine; queue tail S19-S20, H2,
  data items (football 90'/ET flag, NHL OT/SO); S18 retired as
  already-shipped; deep-research disposition logged.

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
