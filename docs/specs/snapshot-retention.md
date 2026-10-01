# Snapshot retention (#82): RULED 2026-10-01 (design; implementation is a later lane)

**Status: RULED 2026-10-01 (see "RULED" below; the original proposal follows for the record). Nothing here is built.** No
pruning code, no migration and no deleting command exist or ship with this
document. Every number below is either read from code (file and line cited),
derived from it with the arithmetic shown, or labelled UNKNOWN with the
read-only query that would measure it.

Lane, verbatim: "snapshot pruning/rollup — odds and Kalshi snapshots now grow
by thousands of rows a day; propose a retention policy (raw 30d, hourly
rollups beyond, closes kept forever) for ruling before any code."

Provenance:
- Issue #82 "Snapshot pruning / rollup design" (queue #6).
- BACKLOG "#63 DECISIONS RULED" (2026-09-29), ruling (d): "Snapshot growth is
  accepted. The cap rides the queued snapshot-pruning work."
- BACKLOG "DB LAG INVESTIGATED 2026-09-20": "odds rows accumulate per match
  across capture days and evaluators read all history per match ... QUEUED
  ... snapshot pruning/rollup design (keep latest-per-book-per-day + close;
  archive the rest)."
- Issue #99, an accepted limitation: "MLB line-move resolution follows the
  capture-odds cadence."

Schema names are read from `src/db/schema.py` (law 1): table
`odds_snapshots` (class `OddsSnapshot`) has the columns `id, match_id,
market, selection, devig_prob, line, n_books, captured_at, source, yes_bid,
yes_ask`. Table `odds` (class `Odds`) has `id, match_id, bookmaker, market,
selection, price_decimal, line, is_opening, is_closing, captured_at,
source`. `matches.utc_date` is the kickoff (naive UTC).

## RULED 2026-10-01 — this section supersedes the proposal below

ARCHITECT-RULE (verbatim): "Retention: NO hourly rollups — raw 30 days,
first + closing captures forever with Kalshi bid/ask; the window's hourly
captures already are the rollup. Revisit only if raw growth exceeds 1
GB/month. Close the other eight questions with that."

**The ruled policy:**
- **Raw rows are kept 30 days.** Eligibility is per match, as in §3.1.
- **Kept forever, raw:** FIRST (the earliest capture set per series) and
  CLOSE. For book sources, CLOSE is the last pre-kickoff capture set. For
  `kalshi`, it is the latest pre-kickoff row per selection, kept WITH its
  `yes_bid`/`yes_ask`.
- **Everything else** for an eligible match is deletable.
- **NO rollup table.** §3.2(B), §3.3 and the `odds_snapshot_rollups` DDL in
  §4 are NOT ADOPTED. The prune log stays useful for receipts.
- **Revisit trigger:** raw `odds_snapshots` growth above 1 GB/month (measure
  with §7's receipts plus the DB file size).

**The nine §6 questions, closed under the ruling:**

| # | Question | Disposition |
|---|---|---|
| 1 | Bucket width | Moot: no rollups. |
| 2 | Keep the T-3h reference / final-3h raw | Not kept. Historical line-move replay older than 30 days is lost; live use is unaffected (always inside 30 days). |
| 3 | Keep LAST OVERALL for `clv-report` | Not kept. For pruned matches, `clv-report`'s "last" becomes CLOSE (the last pre-kickoff capture). The implementation lane must label that in its output. |
| 4 | Host vs laptop pruning | Not decided by the ruling's text. The §6 proposal stands as the default: no applied prune before H2 completes, then the host prunes. Flag if wrong. |
| 5 | Timing vs H2 | As 4: no applied prune before the H2 cutover plus one clean week. |
| 6 | Does `odds` need anything | Yes, as its own lane: **#167** (priority, 2026-10-01). It is out of this policy. |
| 7 | VACUUM cadence / timer | The §5.6 default: operator-only VACUUM after a reviewed apply. No timer. |
| 8 | RAW_DAYS / GUARD_DAYS | 30 / 30 as proposed. |
| 9 | Eligibility by kickoff vs capture age | By kickoff date (§3.1), matching the "raw 30 days" intent per match. |

**Reader impact under the ruled policy** (replacing §3.4's rollup
assumptions):

| Reader | Effect |
|---|---|
| `mlb-odds-timing` | Older than 30 days, capture counts / pre-start counts / max books undercount. First capture and first pre-start survive only if they equal FIRST. Its output must label pruned matches **before the first applied prune** (an implementation-lane item). |
| `clv-report` | "last" becomes CLOSE for pruned matches (question 3). |
| line-move history replay | Lost beyond 30 days. |
| Everything else in §3.4 | Unchanged: the Kalshi exports, card, venue, kalshi-disagreement, value anchor, live line-move, evaluate, Cockpit ledger. |

Implementation is a separate lane. Nothing here is built.

---

## 1. Inventory: the growing tables

### 1.1 `odds_snapshots`: append-only, the subject of this policy

Every writer appends. Nothing in `src/` or `cli.py` deletes or updates
these rows (grep of `OddsSnapshot` and `odds_snapshots`, 2026-10-01).

| Writer | `source` | `market` / selections | Rows per game per run | Games per run |
|---|---|---|---|---|
| `capture-odds` (cli.py:2160-2235) | `api_baseball` | `1X2` HOME/AWAY + `TOTALS` OVER/UNDER (line set) | up to 4 (2 per market present; baseball has no draw) | every MLB match with `status == SCHEDULED` that has `odds` rows. **No date bound** (cli.py:2192-2195). |
| `sync-odds-football` → `sync_odds_nfl` (service.py:1755-1832) | `api_american_football` | `1X2` HOME/AWAY ("NFL moneylines have no draw leg", api_american_football.py `_normalize_selection`) | 2 | every `Sport.NFL` SCHEDULED match in the next 8 days with a provider id and posted odds. **`Sport.NFL` includes NCAA** (api_american_football.py:149 creates NCAA as `sport=Sport.NFL`). |
| `sync-kalshi` / `-nfl` / `-nhl` / `-ncaa` → `sync_kalshi_mlb` (kalshi_sync.py:31-350) | `kalshi` | `ML` HOME/AWAY, with `yes_bid`/`yes_ask` | 2 (one per matched side) | matched open markets on games with `utc_date` in [`date_from` or now−1d, `date_to` or now+2d] |
| `sync-kalshi-soccer` → `sync_kalshi_soccer` (kalshi_sync.py:353-560) | `kalshi` | `1X2` HOME/DRAW/AWAY, with `yes_bid`/`yes_ask` | up to 3 (legs wider than `--max-spread` are skipped) | matched SCHEDULED PL games in [now−1d, now+7d], kickoff still in the future |

There are no other writers. Soccer, NHL, the cups and UNL have **no book
snapshots** (the generic `sync_odds` writes only `odds`). BACKLOG records
this as the accepted "soccer line-move is Kalshi-only" limit.

**Cadence: captures per day.** These come from `deploy/hosting/systemd/*.timer`
and `deploy/hosting/chains.py` (host). The laptop counterparts are
`scripts/setup_clv_capture.sh` and the operator chains in docs/CLI.md.

| Writer | Host runs/day | Laptop runs/day |
|---|---|---|
| `capture-odds` | 4 (`sp-clv-capture`: 08/12/16/20 America/New_York) | 4 (launchd 08/12/16/20 local) |
| `sync-odds-football` | 1 (`nfl-lines`, 15:00 UTC) + 1 per `sp-window` run where NFL **or NCAA** is in the near/imminent tier (sp_run.py:125-131: one call for the whole american-football family) + 1 per `freshen:NFL` | operator-driven ("every day or two", docs/CLI.md) |
| `sync-kalshi` (MLB) | 1 (`mlb-preslate`) + 1 per window run with MLB near/imminent + 1 per `freshen:MLB` (skipped on the host: `SP_SKIP_FAMILIES`) | operator chain (preslate, T-60 freshen) |
| `sync-kalshi-nfl` | 1 (`nfl-lines`) + window + `freshen:NFL` | operator-driven |
| `sync-kalshi-nhl` | 1 (`nhl-daily`, 16:00 UTC) + window | operator-driven |
| `sync-kalshi-ncaa` | Thu/Fri/Sat 1 (`ncaa-market`) + window | operator-driven |
| `sync-kalshi-soccer` | Fri 1 + Sat 1 (`soccer-prematch`) + window + `freshen:SOCCER` | operator-driven |

`sp-window` fires at :05 on hours 00-03 and 06-23 UTC (`sp-window.timer`).
That is 4 + 18 = **22 runs/day** at most. A competition only gets odds and
Kalshi steps while its next kickoff inside the 24h window is at most 6h away
(`PROX_FAR_H = 6`). So the per-day Kalshi run count for a competition is
roughly the number of hours from 6h before its first kickoff to its last
kickoff. That count is UNKNOWN per day. The chain receipts' `proximity`
field records it.

**Estimated daily growth (formulas; the game counts are UNKNOWN).**
Write `G` for games in scope per run. `R` is runs/day from the table above.

- `capture-odds`: `4 runs × 4 rows × G_mlb_sched`. Ceiling for a full
  regular-season slate, with G = 15 (30 teams, structural): 4 × 4 × 15 =
  **240 rows/day**. This is higher if tomorrow's games already have `odds`
  rows. In the postseason (now) G ≤ 4: 4 × 4 × 4 = 64 rows/day. The timer is
  disabled after the World Series (hosting-h1 §O).
- `sync-odds-football`: `R_fb × 2 × G_fb8`. G_fb8 is NFL games (≤ 16 per
  week, structural) **plus NCAA games** with provider odds in the next 8
  days, which is UNKNOWN. NFL alone: 2 × 16 = 32 rows per run. College
  Saturdays keep the family in the near tier for many hours, so `R_fb` is
  largest exactly when `G_fb8` is.
- Kalshi, two-sided path: `R_k × 2 × G_k`. Example for MLB on the host:
  `sp-window` passes `--date-from {today} --date-to {tomorrow}`, so G_k is
  the matched games in that window (≤ 15 on a regular-season day). If MLB
  were near/imminent for 15 window runs: 15 × 2 × 15 = **450 rows/day**,
  plus the preslate run with the default −1d..+2d window. In that window
  G_k ≤ 45 (three days of a full slate): 2 × 45 = 90.
- Kalshi soccer: `R × 3 × G_PL7d`, with G ≤ 10 per matchweek (20 clubs):
  ≤ 30 rows per run.
- NHL: `R × 2 × G` with G ≤ 16 per day (32 teams) over the −1d..+2d window,
  so ≤ 2 × 48 = 96 rows per run at the structural ceiling.

These ceilings are consistent with "thousands of rows a day" on a day when
MLB, NHL and college football all sit in the window. **Real numbers come
from receipt R1 (§7), which must be run before the ruling.** This document
does not guess them.

**Bytes.** The only on-record size in the repo is the "83MB production DB"
(BACKLOG, incident of 2026-09-21). The host's backup receipts carry `bytes`
per daily (`sp_backup.run_backup`), so the growth curve already exists in
`receipts.jsonl`. The table's share of it is UNKNOWN; receipt R3
measures it. Backups use the `.backup` API, which copies every page,
including free pages. **A DELETE does not shrink the file or the backups.**
Only a `VACUUM` does (`db-tune --vacuum` exists, cli.py:5571). §5.6 covers
this.

### 1.2 `odds`: mixed write modes (NOT wipe-and-replace everywhere)

The lane assumed the `odds` table is wipe-and-replace per match and source.
**That holds for two of the four paths only:**

| Writer | Mode |
|---|---|
| `sync_odds_mlb` (service.py:1308, 1437) | wipe-and-replace per (match, `api_baseball`) |
| `sync_odds_nfl` (service.py:1806) | wipe-and-replace per (match, `api_american_football`) |
| generic `IngestionService.sync_odds` (service.py:494-561): soccer PL, cups, UNL, **NHL** | **APPEND**. Every run adds every book's rows with a fresh `captured_at` (api_football.py:365, api_hockey.py:236). `sp-window` runs it hourly for near/imminent competitions. |
| `soccer_odds_history` (historical CSVs) | one-time, idempotent, `is_closing=True` |

So `odds` also grows for soccer, the cups and NHL, at about (books ×
selections) rows per game per run. Readers depend on that history in
different ways (§2.2). This policy therefore **does not touch `odds`**; see
ARCHITECT-RULE 6.

Incidental findings from this read. They are not fixed here, and each needs
a BACKLOG entry and an Issue by whoever records this design (the brief bars
this lane from editing BACKLOG):
- (F1) `IngestionService.sync_odds` never passes `line=no.line` into `Odds(...)`
  (service.py:551-559). NHL `TOTALS`/`SPREADS` rows are stored with
  `line = NULL` even though `api_hockey.list_odds` parses it.
- (F2) `evaluate`'s CLV (training.py:1525-1548, and the M11b backfill at
  1600-1617) and `nhl_shadow.grade` (nhl_shadow.py:190-199) feed **every**
  `odds` 1X2 row for the match into `MarketSnapshot.average_implied`, which
  averages all offers. For an append-mode source, the "close" they compute
  is therefore a mean over all captures and books, not the latest
  pre-kickoff price. For wipe-and-replace sources (MLB, NFL) it is the last
  sync, which can be post-kickoff.
- (F3) `capture-odds` snapshots every `SCHEDULED` MLB match that has `odds`
  rows, with no date bound. Under law 4, unmapped statuses stay SCHEDULED,
  so a stale-status past game with odds would be re-snapshotted on every
  capture indefinitely. Whether any such game exists is UNKNOWN; receipt R1's
  per-match max-age column shows it.
- (F4) The window's MLB Kalshi step passes `--date-to {tomorrow}`.
  `strptime` makes that midnight, and the filter is `utc_date <= hi`
  (kalshi_sync.py:85-92). So a window run sees only games on today's UTC
  date. Night ET games (tomorrow's UTC date) enter the window's Kalshi
  capture only after 00:05 UTC. This was read from code, not verified
  against receipts. It is the M11 family; it bears on line-move coverage,
  not on retention.

### 1.3 Other tables with `captured_at` (out of scope)

`umpire_games`, `game_weather`, `pitcher_appearances` and
`nhl_goalie_appearances` carry `captured_at`, but they write per game, not
per capture. `game_weather` can take one row per capture-weather run per
game (cli.py:2884). These are tens of rows a day, not thousands. They are
not part of #82.

---

## 2. Readers: who reads what

### 2.1 `odds_snapshots` readers

| # | Reader | Rows it needs | Horizon |
|---|---|---|---|
| R-a | **Kalshi in the predictions export**: `_collect_rows` (export.py:177-200) → `_summarize_kalshi` | per (match, selection): latest `kalshi` row with `captured_at < kickoff`, with its `yes_bid`/`yes_ask` | any range passed to `export-predictions` (normally the current slate) |
| R-b | **Fixtures export and window card**: `_fixture_row` (export.py:1095-1101) + `kalshi_exec` | same as R-a: latest pre-kickoff `kalshi` row per selection, with HOME bid/ask | `export-fixtures`: now−2d..now+7d by default, any `--start/--end` |
| R-c | **`venue.kalshi_home_prob`** (venue.py:191): window card, NFL export, the #117 receipt | same as R-a, needing the complete leg set (HOME+AWAY, or HOME+DRAW+AWAY for soccer) | live, plus receipts over any range |
| R-d | **`line_move`** (line_move.py): window card, NFL export, MLB/soccer exports | ALL captures of both venues for the match, pre-kickoff and ≤ now. Uses the T-3h reference (last capture at or before kickoff−3h, else the first inside) and the latest capture. | **only while now ∈ [kickoff−3h, kickoff)** (`line_move_for_match` returns None otherwise) |
| R-e | **Value-side anchor** `nfl_predict._book_anchor` (nfl_predict.py:323): `nfl-grade`, `export-nfl-results`, `nhl_shadow.grade` | the EARLIEST non-kalshi `1X2` capture with `captured_at <= kickoff`, i.e. **all selections sharing that `captured_at`** (normalized over them) | `nfl-grade` default 8 days back; `nhl-shadow` default 30; any `--days` |
| R-f | **`clv-report`** (cli.py:2287-2430) | per finished MLB match and `--market` (1X2/TOTALS), **any source**: the FIRST capture set and the LAST capture set by `captured_at`. **No pre-kickoff filter.** Games with fewer than 2 distinct capture times count as `single_snap`. | `--since` defaults to 2026-06-24, the whole season |
| R-g | **`kalshi-disagreement`** (cli.py:3880-3990) | per (MLB match, selection): latest `kalshi` `ML` row with `captured_at < kickoff` (and `>= --since` when set) | whole history by default |
| R-h | **`mlb-odds-timing`** (mlb_odds_timing.py:75-115) | per MLB match, `api_baseball`: every DISTINCT `captured_at` with max `n_books` (count total, count pre-start, first, last, first pre-start, lead hours, max books). For `kalshi`: MIN(`captured_at`) only. | any `--start/--end` |
| R-i | NFL export Kalshi + line-move (nfl_predict.py:228-234) | R-c + R-d | live |
| R-j | Scripts: `k0_kalshi_storage_probe.py` (COUNT, MIN/MAX `captured_at` per kalshi market, one sample row); `kalshi_soccer_twoway_receipt.py` (R-b + R-c + the SET of legs ever captured pre-kickoff); `kalshi_soccer_incomplete_receipt.py` (latest pre-kickoff kalshi HOME row with bid/ask) | as stated | ad hoc |
| R-k | Ops counts: `sp_common.CHAIN_COUNT_TABLES` (`odds_snapshots` COUNT on every chain receipt); `bootstrap.py` fingerprint (`SELECT source, COUNT(*) FROM odds_snapshots GROUP BY source`) | raw row COUNTs | every chain; H1 compares |

**The Cockpit ledger.** `tools/cockpit.html` keeps its ledger (`bd_ledger_v1`)
in localStorage. Claim and exec prices (`claim_market_p`,
`claim_exec_cost`, `exec_cost`, …, cockpit.html:848-855) are **copied from
the export row at claim or execution time**. The page never reads the DB.
Retention cannot change a ledger entry. It can only change whether the
**DB row that produced a claim price can be found again later** for an
audit (§3.4).

**CLV grading (`evaluate`).** It reads the `odds` table, not snapshots
(training.py:1525, 1600). `odds_snapshots` retention does not affect stored
CLV or the M11b backfill.

### 2.2 `odds` readers that depend on accumulated history (why §3 leaves `odds` alone)

- `evaluate` CLV and the M11b backfill, plus `nhl_shadow.grade`: mean over ALL
  1X2 rows (F2). Pruning appended rows would change any CLV not yet written
  (backfill rows with `clv IS NULL`).
- `_fixture_row` book consensus: latest pre-kickoff row per (bookmaker,
  selection).
- `spread_fallback.latest_pre_kickoff`: latest pre-kickoff per key.
- `card.py`, `web/routes/home.py`, `web/routes/matches.py`,
  `miss_analysis.py`, `soccer_backtest.py` (`fdcuk_close` rows): all 1X2 rows
  per match. Their semantics were not audited for this lane.

---

## 3. The proposed policy (the architect's frame)

### 3.1 Eligibility: per MATCH, never per row age

A row's fate is decided by its **match**, so a match is never half-rolled.
A match M is *eligible* when all of these hold:
1. `matches.status = 'FINISHED'`. A match in any other status is HELD
   regardless of age (law 4). That includes SCHEDULED, LIVE, POSTPONED,
   CANCELLED and unmapped statuses left as SCHEDULED. HELD matches are
   counted in every receipt.
2. `matches.utc_date < now − RAW_DAYS` (RAW_DAYS = 30).
3. M is *settled*: every `predictions` row for M has a
   `prediction_outcomes` row. A match with no predictions (market-only)
   counts as settled.
4. M is not inside the grade-guard window: `utc_date < now − GUARD_DAYS`.
   Proposed GUARD_DAYS = RAW_DAYS = 30. This is above `nfl-grade`'s 8-day
   and `nhl-shadow`'s 30-day defaults. NFL and NHL grades live in exports,
   not `prediction_outcomes`, so the age guard is what protects them.

Eligible matches are processed in **day-buckets by kickoff UTC date**.

### 3.2 What happens to an eligible match's rows

For each (match, source, market, line) series:

**(A) KEEP FOREVER, raw and untouched in `odds_snapshots`.**
- **FIRST**: every row whose `captured_at` equals the series' earliest
  `captured_at`, i.e. the whole capture set. Per selection, also that
  selection's own earliest row, in case a leg first appeared later.
- **CLOSE**, defined per source:
  - *book sources* (`api_baseball`, `api_american_football`): every row
    whose `captured_at` equals the series' latest `captured_at` that is
    `< matches.utc_date` (the whole capture set), plus each selection's own
    latest pre-kickoff row.
  - *`kalshi`*: per selection, the latest row with `captured_at <
    matches.utc_date`, kept **with its `yes_bid`/`yes_ask`** (the row
    itself is kept, so nothing is re-derived). Legs are stored per side
    and some are skipped (soccer `--max-spread`), so a per-selection close
    is the only correct definition. That is exactly what R-a, R-b, R-c and
    R-g select.
- **T-3h REFERENCE** (proposed, ARCHITECT-RULE 2): per venue, the last
  capture at or before kickoff−3h, plus **all** pre-kickoff captures in
  [kickoff−3h, kickoff). This is the `line_move` input, so the alarm stays
  replayable on history. Its cost is bounded: at most about 3 window runs
  per match.
- **LAST OVERALL** (only if it differs from CLOSE): the series' latest
  capture set at or after kickoff. This keeps `clv-report`'s current
  "last" exact (§3.4, R-f).

**(B) ROLL UP.** ALL rows of the series, kept ones included, are
summarised into `odds_snapshot_rollups` buckets (§4). The rollup is
complete by itself: a reader can rebuild the whole series from it without
a union with the kept rows.

**(C) DELETE.** Rows that are in (B) and not in (A).

Re-running is idempotent. After a prune, the surviving raw rows are
exactly the keep set. Recomputing FIRST and CLOSE over the survivors gives
the same rows, and an already-rolled day-bucket is skipped (§5.3).

### 3.3 The rollup bucket

The key is per **(match_id, source, market, selection, line, bucket_start,
phase)**:
- `bucket_start`: `captured_at` floored to the hour (UTC).
- `phase`: `'pre'` if `captured_at < matches.utc_date`, else `'post'`. The
  hour that contains kickoff is split in two, so pre/post counts stay exact
  (R-h needs this).
- `line` is part of the key: a TOTALS 8.5 and a 9.0 price are different
  series. Averaging them would be meaningless.

The values are:
- `n_rows`, plus `n_captures` (distinct `captured_at`);
- `first_at`, `first_prob`, `last_at`, `last_prob`, `min_prob`, `max_prob`
  (all on `devig_prob`; for kalshi this is the raw per-contract mid, per the
  K0 receipt);
- `n_books_min`, `n_books_max`;
- kalshi only: `last_yes_bid` and `last_yes_ask` of the bucket's last
  capture (NULL on book rows, and on kalshi rows from before
  `migrate_kalshi_quotes.py`).

**The compression caveat for the ruling.** A rollup row saves space only
when a bucket holds more than one capture. The host's dense writer is
`sp-window`, which captures **once per hour** for a near/imminent
competition. `capture-odds` captures every 4 hours. Most hourly buckets
will therefore hold `n_captures = 1`, so an hourly rollup mostly
**re-encodes rows instead of reducing them**. The rollup row is also wider
than a raw row. Hourly rollups beyond 30 days cap nothing unless the bucket
is coarser than the capture cadence. Receipt R2 (§7) measures the true
captures-per-hour histogram per source. ARCHITECT-RULE 1 asks for the
bucket width with that receipt in hand. The options:
- (i) hourly, as framed (exact line-move-grade history; little saving);
- (ii) 6-hourly or daily beyond 30 days (real saving; intraday shape kept
  coarsely);
- (iii) tiered: hourly for days 31-90, daily after that.

The schema below carries `bucket_minutes`, so a coarser or tiered bucket
needs no schema change.

### 3.4 Per-reader verdict

| Reader | Needs | Preserved? |
|---|---|---|
| R-a / R-b / R-c / R-i Kalshi exports, card, venue | latest pre-kickoff kalshi per selection, with bid/ask | **YES**: CLOSE (kalshi) is that row, raw. The leg set is preserved because the close is per selection. |
| R-d `line_move` | all captures in the T-3h window plus the reference | **YES for live use**: it only runs inside [kickoff−3h, kickoff), so it is always far inside 30 days. Historical replay: **YES** if the T-3h REFERENCE keep (ARCHITECT-RULE 2) is ruled in. Otherwise it is lossy (from rollups only, at bucket resolution). |
| R-e value-side anchor | earliest book 1X2 capture set ≤ kickoff | **YES**: FIRST is the whole earliest capture set. If any capture is ≤ kickoff, the earliest overall is one. Boundary: `_book_anchor` uses `<=` and the others use `<`; FIRST is defined on the overall minimum, so both agree. |
| R-f `clv-report` | first and last capture sets by `captured_at`, any source, no kickoff filter | **YES** with the LAST OVERALL keep. Without it, a game whose last capture was post-kickoff (capture-odds snapshots any still-SCHEDULED game) would report last = CLOSE instead, which is a silent behaviour change. `single_snap` counts are preserved, because FIRST and the last capture keep two distinct times whenever two existed. |
| R-g `kalshi-disagreement` | latest pre-kickoff kalshi ML per selection | **YES** (CLOSE kalshi). The `--since` filter acts on `captured_at`, and the close row keeps its own timestamp. |
| R-h `mlb-odds-timing` | every distinct capture (counts, pre-start counts, last, max books); kalshi first | **BREAKS as written for ranges older than 30 days.** It queries raw `odds_snapshots` only, so after a prune it would see only the kept rows: `captures`, `captures_pre_start` and `max_books` would undercount, and verdicts that depend only on first, first pre-start and kalshi-first are unchanged. **The rollup preserves everything it needs** (`n_captures` per phase, `n_books_max`, `first_at`/`last_at`). The reader must be taught to read `odds_snapshot_rollups` for pruned matches. That is a code change that must land **before the first applied prune**. |
| R-j scripts | counts, the set of legs, latest pre-kickoff HOME | k0 probe: **COUNTs change** (by design); its MIN/MAX `captured_at` are preserved by FIRST and LAST. twoway/incomplete receipts: **YES**. |
| R-k ops counts | raw COUNT(*) | **CHANGE by design.** A prune makes `odds_snapshots` drop on chain receipts, and the H1 fingerprint diverges between a pruned and an unpruned DB. Receipts must print the prune so a drop is explained (§5.4), and any compare must count raw plus rolled (`SUM(n_rows)`). |
| Cockpit ledger | n/a (copied from exports) | **Unaffected.** Audit caveat: a claim price came from the kalshi row that was latest when its export ran. That row is kept raw only if it is the CLOSE or the FIRST, or lies inside the T-3h window. Otherwise only its bucket summary survives. The summary is exact when the claim's capture was its bucket's last (`last_prob`, `last_yes_bid/ask`), and inexact when two captures shared a bucket and the export ran between them. |
| `evaluate` CLV | `odds` table | **Unaffected** (`odds` is not touched). |

**The reader this policy would break, unmodified: `mlb-odds-timing` (R-h).**
It would also silently change `clv-report` (R-f) if the LAST OVERALL keep is
not adopted. Everything else is preserved.

---

## 4. Schema sketch and migration plan (DDL in this doc only)

```sql
-- odds_snapshot_rollups: one row per (match, source, market, selection,
-- line, bucket, phase). Raw FIRST/CLOSE/T-3h/LAST rows stay in
-- odds_snapshots; this table summarises ALL rows of a pruned match.
CREATE TABLE odds_snapshot_rollups (
    id              INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    source          VARCHAR(32),            -- same vocabulary as odds_snapshots.source
    market          VARCHAR(32) NOT NULL,
    selection       VARCHAR(32) NOT NULL,
    line            FLOAT,                  -- NULL for 1X2 / ML
    line_key        VARCHAR(16) NOT NULL,   -- '' when line IS NULL, else repr(line):
                                            -- SQLite UNIQUE treats NULLs as distinct
    bucket_start    DATETIME NOT NULL,      -- UTC, floored to bucket_minutes
    bucket_minutes  INTEGER NOT NULL,       -- 60 as framed (ARCHITECT-RULE 1)
    phase           VARCHAR(4) NOT NULL,    -- 'pre' | 'post' vs matches.utc_date
    n_rows          INTEGER NOT NULL,
    n_captures      INTEGER NOT NULL,       -- distinct captured_at
    first_at        DATETIME NOT NULL,
    first_prob      FLOAT,
    last_at         DATETIME NOT NULL,
    last_prob       FLOAT,
    min_prob        FLOAT,
    max_prob        FLOAT,
    n_books_min     INTEGER,
    n_books_max     INTEGER,
    last_yes_bid    FLOAT,                  -- kalshi: the bucket's last capture; else NULL
    last_yes_ask    FLOAT,
    kickoff_at      DATETIME NOT NULL,      -- matches.utc_date when rolled (audit)
    rolled_at       DATETIME NOT NULL,
    rollup_version  INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_osr_key ON odds_snapshot_rollups
    (match_id, source, market, selection, line_key, bucket_start, bucket_minutes, phase);
CREATE INDEX ix_osr_match ON odds_snapshot_rollups (match_id, source);

-- one row per applied day-bucket: the receipt in the DB, and the idempotency marker
CREATE TABLE odds_snapshot_prune_log (
    id               INTEGER PRIMARY KEY,
    kickoff_date     DATE NOT NULL,         -- the day-bucket (kickoff UTC date)
    source           VARCHAR(32),
    matches_rolled   INTEGER NOT NULL,
    rows_before      INTEGER NOT NULL,
    rows_kept        INTEGER NOT NULL,
    rows_deleted     INTEGER NOT NULL,
    rollup_rows      INTEGER NOT NULL,
    backup_file      VARCHAR(255) NOT NULL, -- the .backup this apply was covered by
    git_sha          VARCHAR(40),
    applied_at       DATETIME NOT NULL
);
CREATE UNIQUE INDEX ux_ospl_day ON odds_snapshot_prune_log (kickoff_date, source);
```

`source` is nullable to mirror `odds_snapshots.source`. Legacy rows with a
NULL source would be grouped and logged as `source IS NULL`; they are never
assumed to be a known source (law 4).

**Migration plan, in the repo's style. Additive only.**
1. Add the `OddsSnapshotRollup` and `OddsSnapshotPruneLog` ORM classes in
   `src/db/schema.py`. `init_db()` (`Base.metadata.create_all`) creates
   the missing tables and never alters existing ones (the pattern
   capture-odds already relies on, cli.py:2178-2181).
2. Add `migrate_snapshot_rollups.py`, modelled on `migrate_kalshi_quotes.py`.
   It inspects, creates the two tables and indexes if absent, prints a
   receipt (tables present, row counts), and is idempotent. It never
   deletes or rewrites. RUN ORDER in its docstring: the `.backup` first,
   then the migration, then nothing else changes until the ruling's apply
   step.
3. The read-side changes (`mlb-odds-timing` reading rollups for pruned
   matches; ops counts reporting raw plus rolled) ship in the **same PR as
   the CLI, in dry-run only**, before any apply.
4. On the host: `sp_deploy.py` lists the new `migrate_*.py`, and the
   operator runs it after `systemctl start sp-backup.service`
   (hosting-h1 §O).

---

## 5. Safety

### 5.1 Backup before any prune (law 5)
- `--apply` refuses to start without a fresh, verified **`.backup`-API**
  backup taken by the command itself. The proposal is
  `sp_backup.run_backup("preprune")`, writing
  `sports_YYYY-MM-DD_preprune_HHMM.db` plus `.sha256`, integrity-checked.
  This needs `"preprune"` added to `target_name`'s event kinds, which are
  `prerefresh` and `precleanup` today (sp_backup.py:31-35). The name
  contains `_pre`, so `sp_prune.py`'s existing rule keeps event backups 30
  days. On the laptop the same `.backup` API is used (never a
  file copy).
- The backup file name is written into every `odds_snapshot_prune_log` row.
- `refuse_under_data` semantics: the backup directory is never under
  `data/`, and the command never creates, copies or moves files under
  `data/`.

### 5.2 Dry-run first
`python cli.py snapshot-prune` (name proposed) is **dry-run by default**
and writes nothing. `--apply` is required to change anything. On the host
it is additionally gated by `SP_SNAPSHOT_PRUNE_APPLY=1`, mirroring
`SP_PRUNE_APPLY`. The first apply is operator-started and reviewed, never a
timer. The dry-run prints one line per (kickoff_date, source):

```
kickoff_date  source                 matches  raw_rows  keep_first  keep_close  keep_t3h  keep_last  would_roll  would_delete  rollup_rows
2026-08-29    kalshi                 ...
HELD: not FINISHED n · unsettled (prediction without outcome) n · inside guard n · stale-SCHEDULED older than RAW_DAYS n
```

The options are `--older-than-days` (default 30), `--source`, `--max-days`
(cap the buckets per run) and `--bucket-minutes` (default per ruling). With
no `--apply`, the command is pure SELECTs, like `k0_kalshi_storage_probe.py`.

### 5.3 Idempotent rollup-then-delete, one transaction per day-bucket
For each (kickoff_date, source) with no `odds_snapshot_prune_log` row:
1. `BEGIN IMMEDIATE` (takes the write lock; on the host, hold the chain
   flock too, so no sync writes mid-bucket).
2. Re-select the eligible matches inside the transaction (§3.1).
3. Compute the keep set (§3.2 A) and the rollup rows (§3.3) from the raw
   rows.
4. `INSERT` the rollups. A conflict on `ux_osr_key` **aborts the bucket**:
   a rollup can only be built from complete raw data, so a pre-existing
   rollup means a prior partial state and needs a human.
5. Assert, before any delete:
   - `SUM(n_rows)` over the new rollups equals the raw row count;
   - `keep + delete = raw`;
   - every match keeps ≥ 1 FIRST row and, when it had a pre-kickoff
     capture, ≥ 1 CLOSE row per source and selection.
   Any failure means ROLLBACK, a page, and a stop.
6. `DELETE FROM odds_snapshots WHERE id IN (<computed delete ids>)`, by
   explicit id list only. There is never a predicate-only delete.
7. `INSERT` the `odds_snapshot_prune_log` row, then `COMMIT`.

A crash at any point leaves the bucket either untouched or complete. A
re-run skips logged buckets and recomputes the rest from scratch.

### 5.4 Receipts
- Console: the dry-run table, then per bucket the applied counts, then
  totals and the backup name.
- Host: an `append_receipt({"kind": "snapshot_prune", "applied": …,
  "buckets": [...], "backup": …})` line, the same `receipts.jsonl` stream as
  the chains.
- Chain receipts' `counts.odds_snapshots` will drop after an apply. The
  receipt should carry `odds_snapshot_rollups` (rows and `SUM(n_rows)`)
  beside it, so raw plus rolled is monotonic and a drop is never
  unexplained.

### 5.5 Never prune near an ungraded match
§3.1 conditions 1, 3 and 4. A FINISHED match whose prediction lacks an
outcome is HELD at any age and counted, because the grader still owes it
its numbers.

### 5.6 Space is reclaimed only by VACUUM
SQLite reuses freed pages but does not shrink the file. `.backup` copies
the freelist. So neither the DB nor its backups get smaller until a
`VACUUM` (`db-tune --vacuum`), which rewrites the whole file and needs
about 2× free disk. The proposal: a VACUUM after the first applied prune,
then occasionally (ARCHITECT-RULE 7).

---

## 6. ARCHITECT-RULE items

1. **Bucket width beyond 30 days.** Hourly as framed, or coarser. Given
   §3.3's caveat (window capture is about hourly, so hourly buckets barely
   compress) and #99 ("line-move resolution follows the capture-odds
   cadence": MLB book series are 4-hourly anyway), the choice is between:
   hourly (fidelity, about 1× saving); 15-minute (finer than any capture
   cadence; pointless for space); 6-hourly or daily (real saving); or
   tiered (hourly for days 31-90, then daily). Rule after receipt R2.
2. **Keep the T-3h reference plus the final-3h captures raw forever**, so
   the line-move alarm stays replayable on history (bounded: at most about
   3 window captures per venue per match). Yes or no.
3. **Keep LAST OVERALL** (a post-kickoff last capture) so `clv-report`
   stays byte-identical. The alternative is to rule that `clv-report`
   should use CLOSE (last pre-kickoff), a separate reader fix that would
   change its historical output.
4. **Host and laptop: prune independently, or host only?** Through H1b the
   laptop is writer of record. At H2 the laptop's `.backup` **replaces**
   the host DB (hosting-h1 §H2), and the snapshots are named there as
   non-resyncable history. Proposal: **no applied prune anywhere before the
   H2 cutover completes.** After it, the host prunes. The laptop either
   keeps pruning its own DB independently (its MLB capture duty continues),
   or treats its DB as an unpruned archive. Rule which.
5. **Interaction with H2.** A prune before cutover would make the cutover
   `.backup` carry less history. A prune during the parallel week would
   make the bootstrap fingerprint (`odds_snapshots_by_source`) diverge
   between host and laptop for a non-pipeline reason. Proposal: prune
   lands after H2, plus one clean week, behind the dry-run review.
6. **Does `odds` need anything?** It is append-mode for soccer, the cups
   and NHL (§1.2), and some readers average all its rows (F2). Options:
   (a) leave it out (this proposal); (b) a separate lane for an `odds`
   policy (for example "latest per book per day plus close", BACKLOG
   2026-09-20) that first resolves F2, because evaluate's CLV semantics
   depend on the accumulated rows. Rule, and whether F1-F4 are logged as
   Issues.
7. **VACUUM cadence**, and whether an applied prune runs on a timer
   (after the first reviewed manual apply) or stays operator-only like
   `soccer-refresh`.
8. **RAW_DAYS and GUARD_DAYS**: 30 and 30 proposed. Should "ungraded"
   also hold NFL and NHL games with no exported grade? Those grades are
   not in `prediction_outcomes`, so the age guard is their only protection
   today.
9. **Eligibility by kickoff date (proposed) vs `captured_at` age.** By
   kickoff keeps a match whole and makes the day-bucket the transaction
   unit. By `captured_at` matches the lane's literal "raw kept 30 days",
   but splits matches across buckets.

---

## 7. Pre-ruling receipts (read-only; Anthony runs them, SQLite `mode=ro`)

These turn the UNKNOWNs above into numbers. They are SELECT-only. Run them
against the live DB opened read-only (as `k0_kalshi_storage_probe.py` does)
or against a `.backup` copy outside `data/`.

```sql
-- R1: daily growth by source/market, last 14 days (+ oldest kickoff captured, for F3)
SELECT date(s.captured_at) AS d, s.source, s.market, COUNT(*) AS rows,
       COUNT(DISTINCT s.captured_at) AS captures, COUNT(DISTINCT s.match_id) AS matches,
       MIN(m.utc_date) AS oldest_kickoff_captured
FROM odds_snapshots s JOIN matches m ON m.id = s.match_id
WHERE s.captured_at >= datetime('now', '-14 days')
GROUP BY d, s.source, s.market ORDER BY d, s.source, s.market;

-- R2: captures per hourly bucket (the rollup compression ratio, ARCHITECT-RULE 1)
SELECT source, n AS captures_in_bucket, COUNT(*) AS buckets FROM (
  SELECT match_id, source, market, selection, strftime('%Y-%m-%d %H', captured_at) AS h,
         COUNT(DISTINCT captured_at) AS n
  FROM odds_snapshots GROUP BY match_id, source, market, selection, h)
GROUP BY source, n ORDER BY source, n;

-- R3: bytes (needs SQLITE_ENABLE_DBSTAT_VTAB; else sqlite3_analyzer on a .backup copy)
SELECT name, SUM(pgsize) AS bytes FROM dbstat
WHERE name IN ('odds_snapshots', 'odds', 'ix_snap_match_captured',
               'ix_odds_match_book_sel') GROUP BY name;

-- R4: what a 30-day prune would touch today (rows on FINISHED matches older than 30d)
SELECT s.source, COUNT(*) AS rows, COUNT(DISTINCT s.match_id) AS matches
FROM odds_snapshots s JOIN matches m ON m.id = s.match_id
WHERE m.status = 'FINISHED' AND m.utc_date < datetime('now', '-30 days')
GROUP BY s.source;
```

(`matches.status` stores the enum NAME, `'FINISHED'`. sp_run.py's window
query filters on `m.status != 'FINISHED'`.)
