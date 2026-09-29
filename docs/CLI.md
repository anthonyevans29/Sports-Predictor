# CLI Reference

The CLI is the primary interface — the browser UI currently covers MLB and
soccer views only, so NFL and the cup competitions are operated entirely
from here. Every command: `python cli.py <command> [options]` from the
repo root with the venv active.

Conventions: soccer seasons are `"2026/27"`; MLB and NFL seasons are
`2026`. Competition codes: `PL`, `ELC`, `EL1`, `EL2`, `EFL` (League Cup),
`FAC`, `CL`, `UEL`, `CS`, `MLB`, `NFL`. Dates are `YYYY-MM-DD`.

---

## Setup & discovery

| Command | Options | Purpose |
|---|---|---|
| `init-db` | `--force` | Create the SQLite schema (`data/sports.db`). |
| `sync-competitions` | `--sport` | Register the curated competition list for a sport. |
| `sync-teams` | `--competition --season` | Pull all teams for a competition-season. |
| `status` | | What's in the local DB (row counts per table). |
| `find-team` | `<name>` | Verify a team exists and see its ids. |
| `db-tune` | `--vacuum` | One-shot DB health pass: WAL, ANALYZE, composite indexes, probe timing. |
| `data-freshness` | `--sport --season` | Diagnose whether model inputs are current. |
| `model-versions` | | Trained model versions and their status (production / held / rejected / shelved). |
| `show-config` / `set-config` | `--sport --field --value --yes` | Inspect / edit the production model's frozen config (gated; logs manual overrides). |

## Core data syncs (all sports)

| Command | Options | Purpose |
|---|---|---|
| `sync-matches` | `--competition --season --seasons N --date-from --date-to` | Schedules, scores, statuses. `--seasons N` backfills N seasons (sport-aware season strings). **Run `sync-teams` for the same competition-season first:** listings whose clubs are not in the DB are skipped (the skip line names the id range). |
| `sync-odds` | `--competition --season` | Book odds for upcoming games (soccer & MLB bulk path). |
| `sync-injuries` | `--competition --season` · `--kickoff-within-hours N` | Current injury/status report per team. NFL: positions joined from the roster endpoint. `--kickoff-within-hours N` (2026-09-29) scopes the sync to the teams in this competition's scheduled games kicking off within N hours. That is the window service's imminent-tier step. It makes no provider call when nothing is inside the window. |
| `capture-odds` | `--sport --competition --season` | Lightweight odds-only capture for CLV tracking. |
| `wipe-injuries` | `--confirm` | Destructive reset of the injuries table. |

## MLB daily operation

Pre-slate chain, in order: `sync-matches --competition MLB --date-from <today> --date-to <today>` → `sync-bullpen-stats` →
`sync-pitchers` → `sync-pitcher-stats` → `sync-odds` → `sync-kalshi` →
`predict` → `sync-umpires --today` → `capture-weather` → `export-predictions`.

Morning grading: `sync-matches` → `evaluate` → `improve` →
`sync-appearances --recent` → `sync-umpires --recent` → `export-results`.

| Command | Options | Purpose |
|---|---|---|
| `sync-pitchers` | `--competition --season` | Probable starters per game. |
| `sync-pitcher-stats` | `--season` | Season-to-date stats for probables. |
| `sync-bullpen-stats` | `--season` | Bullpen aggregates for all 30 teams. |
| `sync-appearances` | `--competition --season --recent` | Pitcher appearances (feeds bullpen availability). |
| `sync-umpires` | `--competition --season --recent --today` | Umpire assignments + environment. `--today` = today's scheduled games (pre-slate); `--recent` = recent finished games (morning). |
| `capture-weather` | `--date` | Tracking-only weather snapshot near first pitch. |
| `backfill-weather` | `--competition --season --limit` | Historical weather via Open-Meteo. |
| `sync-kalshi` | `--date-from --date-to` | Kalshi MLB game markets (second market source). |

## Soccer weekly operation

Pre-matchday chain: `sync-matches` → `sync-odds` → `sync-injuries` →
`sync-kalshi-soccer` → `predict` → `export-predictions --start --end
--status scheduled`. Morning-after: `sync-matches` → `evaluate` →
`export-results --date`. After the matchweek closes: `soccer-refresh`
(gated). Full routine: `docs/pl_weekly_routine.md`.

| Command | Options | Purpose |
|---|---|---|
| `sync-kalshi-soccer` | `--competition --max-spread` | Kalshi three-way markets (Home/Away/Tie), refuse-safe matching, in-play guard. |
| `soccer-refresh` | `--max-drift` | Weekly Elo/context retrain behind sanity gates (drift + spread-compression guards). |
| `soccer-odds-history` | `--competition --season --csv --url` | Ingest historical closing 1X2 odds (football-data.co.uk). |
| `predict-worldcup` | `--season --competition --out` | Market-derived tournament sheet — not the club model. |

## NFL operation (LIVE since Week 3, 2026-09-22)

Weekly rhythm: `sync-odds-football` + `sync-kalshi-nfl` every day or two as
lines post; after game days `sync-matches --competition NFL` then
`nfl-grade`. Predictions are LIVE (nfl_elo_v1): `predict-nfl` →
`export-nfl-predictions` before each slate.

> **DOCTRINE (architect, 2026-09-29): the game-day T-60 closing freshen is
> MANDATORY for model sports (NFL, MLB, soccer) on the laptop while it is
> writer of record.** Run the family's freshen sequence (the same steps as
> `freshen:<family>` in `deploy/hosting/chains.py`: injuries/odds/Kalshi →
> predict → export) about 60 minutes before each game-day slate. Earned by
> Week 4 MNF: the provider's injury report did not list the Chicago starter
> at either pre-game sync, and no closing freshen ran. The host's
> window-service freshen is NOT a substitute: its T-90 check only sees
> injury changes some other chain already synced, and the line-move alarm
> only fires on a >= 6pp market move.

| Command | Options | Purpose |
|---|---|---|
| `sync-odds-football` | | Per-game book odds for upcoming American-football games, NFL and NCAA (moneyline, spreads with sign, totals with lines). Old name `sync-odds-nfl` still works as an alias. |
| `sync-kalshi-nfl` | | Kalshi `KXNFLGAME` markets via the shared two-sided matcher. |
| `capture-weather-nfl` | | Tracking-only weather snapshot for upcoming NFL games (team-keyed stadium map; roofed games stored as indoor). |
| `predict-nfl` | | Write v1 Elo predictions for upcoming games (match-only upsert). |
| `export-nfl-predictions` | `--week` / `--days N` | LIVE export (`rehearsal: false`): quarantine contract, STALE-BOOK? venue check, Elo/rest "why" fields, QB status in input_quality. **Rows default to the current slate: kickoffs in the next 36h.** `--week` is the full 8-day look-ahead; `--days N` sets it explicitly. Prediction generation is unchanged; `predict-nfl` still stores the whole week for CLV. Prints venue-check lines plus a `window:` receipt line. |
| `nfl-backtest` | | Walk-forward backtest against the frozen phase-2 gate — in the live era a provenance/regression check; prints a scope line. |
| `nfl-grade` | | Grade predictions vs finished games + banked closer consensus (sides, log-loss, CLV). Also prints value-side-vs-close beside pick-vs-close: the value side is where model − market was positive at the earliest pre-kickoff **book** snapshot (which `sync-odds-football` now appends every sync); games with no snapshot are counted as unanchored, never guessed. Each graded line records the anchor timestamp beside the prediction's (`anchor=… pred=…`); an anchor later than the prediction is flagged `⚠ ANCHOR AFTER PREDICTION` and counted. `export-nfl-results` carries the same per row (`value_side`, `value_side_clv`, `value_shadow`, `value_anchor_at`, `value_prediction_at`). |
| `nfl-qb-audit` | `--team NAME` · `--live` · `--season` | QB-feed audit: the team's stored injury rows, the pre-fix vs fixed `qb_listed` read, unresolved positions, and sync timing vs the last kickoff. Read-only on the DB. `--live` spends 2 provider requests (injuries + roster) and classifies each listed player: H1 not on the report / H2 position did not resolve / H3 dropped by the old 14-day filter. |
| `export-nfl-results` | | Graded NFL results file for the consumer (standard results shape; live era — no rehearsal flag). |

## Market-only competitions (cups, UNL, NCAA, NHL)

No model output ships for these: the cup and NHL model tracks are
SUSPENDED (2026-09-25; cups at a rotation floor, NHL at the
schedule-only floor), UNL and NCAA are market-only by doctrine. Data
syncs run normally; the consumer receives market-only files:

| Command | Options | Purpose |
|---|---|---|
| `sync-kalshi-ncaa` | | Kalshi `KXNCAAFGAME` markets via the shared two-sided matcher (the primary college market source). |
| `export-fixtures` | `--competition --start --end` | Market-only fixtures file: schedule, results, book consensus (latest pre-kickoff price per book), Kalshi presence; `contains_predictions: false`. Prints the odds (market, selection) labels it saw. |

**NHL daily (from the 2026-09-29 market-only launch: the 2026-27 opening day; on the host the start is `SP_NHL_ACTIVE_FROM` in host.env):**
`sync-matches --competition NHL --season 2026 --date-from D --date-to D` for
each of D = yesterday, today, tomorrow (single-day calls: the hockey adapter
only honours a date when from == to, so a range pulls the whole season) →
`sync-odds --competition NHL --season 2026` → `sync-kalshi-nhl` →
`export-fixtures --competition NHL`. The Cockpit renders the file as
books' fair bars with a market-only chip and the Kalshi status.

## Prediction, evaluation, improvement

| Command | Options | Purpose |
|---|---|---|
| `predict` | `--sport --competition --season` | Write predictions for upcoming games (production model). |
| `evaluate` | `--sport` | Grade finished games (sides, totals, CLV; overnight closer backfill). |
| `improve` | `--sport --force-input-eval --hold-on-pass` | Train a candidate and gate it vs production on the frozen holdout. Rejection is the normal outcome. `--hold-on-pass` (or env `SP_IMPROVE_HOLD_ON_PASS=1`, set by the host units — H0-5): a PASS is HELD, not promoted, and prints an `SP-PAGE:` line. |
| `ratify-candidate` | `--sport --version --yes` | Promote a HELD candidate on explicit operator ratification; refused unless the production version it beat is still production. |
| `backtest` | `--season --competition` | Leakage-free historical re-run of the current model. |
| `export-predictions` | `--sport --competition --days --date --start --end --status` | Consumer prediction file with input_quality vocabulary. **Default rows: the current slate.** Soccer: kickoffs in the next 36h. **MLB: today's one 08:00-UTC slate-day** (ruling 2026-09-28: it plays daily, so 36h would drag in tomorrow's games before pitchers and lineups are confirmed). `--days N` is the explicit look-ahead. `--date` / `--start --end` keep their 08:00-UTC slate-day meaning (post-mortems, the soccer weekend chains). Prints a `window:` receipt line. |
| `export-results` | `--sport --competition --date` | Graded results file (top-pick, totals pulse annotations). |
| `results-tally` | `--days` | Regenerate `RESULTS.md` — rolling per-sport record (sides, log-loss, CLV). |
| `window-card` | `--hours --t90` | Next-24h consolidated card → `exports/window_24h.json`: every game in the window, kickoff-sorted, fixtures grammar + model p / edge / tier / quarantine / venue flag / engine. Model fields copied from the canonical exports (no model runs); market side repriced. Read-only against the DB. **Line-move alarm** (2026-09-29): inside T-3h, a net move ≥ 6pp in the home probability on the book consensus or Kalshi (from stored snapshots, no provider calls) sets `late_news_flag: "late-news?"` with the per-venue `line_move`; the window pager pages it and requests `freshen:<family>`. `export-nfl-predictions` carries the same two fields. |

## Diagnostics & research

| Command | Options | Purpose |
|---|---|---|
| `card` | `--sport --date` | Daily confidence ladder + per-game signal drill-down (MLB; multi-sport is backlog U1). |
| `market-alignment` | `--sport --date` | Model pick/prob vs market per upcoming game. |
| `clv-report` | `--sport --since --market` | Closing-line-value report over graded games. |
| `kalshi-disagreement` | `--since` | How often/how much Kalshi disagrees with books. |
| `totals-check` / `calibration-series` | `--sport {mlb} --since / --lo --hi` | Totals grading; band calibration diagnosis. **MLB-only** (soccer totals reads are computed from results exports pending S14 tooling). |
| `model-report` | `--limit` | Recent outcomes post-mortem feed. |
| `miss-analysis` | `--min-n` | Bucket all graded predictions across categories. |
| `signal-residuals` | | Do tracked signals predict model residuals? |
| `umpire-report` | `--min-games` | Per-umpire run environment (tracked data only). |
| `bullpen-availability` / `bullpen-effectiveness` / `bullpen-diagnostic` | various | Bullpen usage, effectiveness, and hypothesis tests. |
| `scenarios` | `--date` | What-if decomposition of a day's predictions. |
| `python3 scripts/mlb_apisports_probe.py` | `--seasons 2025 2026` · `--out` | MLB-PROBE (2026-09-29), a script not a cli command. It is read-only: can api-sports Baseball `/games` replace statsapi for MLB on the host? It reports coverage vs our matches, the odds-join id mapping, the status vocabulary and postseason game types. It costs 1 + one call per season; run it on the laptop. No wiring. |

## Hosting — laptop side (scripts, not cli.py)

| Command | Options | Purpose |
|---|---|---|
| `python deploy/hosting/pull_exports.py` | `--host --dest --transport {auto,rsync,scp}` | Pull the host's `exports/` over the tailnet into **`exports/host/`**, never the laptop's own `exports/` (writer of record through H1b). Host from `SP_HOST_ADDR` in `.env`. Newest-wins by mtime, idempotent, all-or-nothing (an unreachable host places nothing, exit ≠ 0). Receipt: pulled / unchanged / newest `window_24h.json`. On demand first; optional hourly launchd at :10 via `bash scripts/setup_export_pull.sh`. Laptop pulls; push is H2. |
| `python deploy/hosting/pull_backup.py` | `--host --dest` | Nightly pull of the host's newest daily `.backup` into `~/sp-backups` (sha256 + integrity verified); launchd via `scripts/setup_backup_pull.sh`. |

## Web UI

`python main.py` serves the local browser app (FastAPI on
`localhost:8000`) — dashboard, competitions, teams, matches, and the MLB
card. NFL and cup views are not yet built (backlog U1); the CLI is the
complete interface for those.

---

## Required external services

| Provider | Used for | Endpoints touched | Env var |
|---|---|---|---|
| **API-Football** (api-sports.io v3) | Soccer: fixtures, teams, injuries, odds, players | `/fixtures`, `/teams`, `/injuries`, `/odds`, `/players` | `API_FOOTBALL_KEY` (required) |
| **MLB Stats API** (statsapi.mlb.com) | MLB schedules, scores, probables, appearances, umpires | `/schedule`, `/game/.../boxscore`, probables feed | none (public) |
| **API-Baseball** (api-sports.io v1) | MLB odds only | `/odds` per game window | `API_BASEBALL_KEY` (falls back to `API_FOOTBALL_KEY`) |
| **API-American-Football** (api-sports.io v1) | NFL teams, games, odds, injuries, rosters | `/teams`, `/games`, `/odds`, `/injuries`, `/players` | `API_AMERICAN_FOOTBALL_KEY` (falls back to `API_FOOTBALL_KEY`) |
| **Kalshi** (public market API) | Second market source: MLB (`KXMLBGAME`), NFL (`KXNFLGAME`), NHL (`KXNHLGAME`), NCAA football (`KXNCAAFGAME`), EPL (`KXEPLGAME`) | series/markets listing | none (public read) |
| **Open-Meteo** | Weather capture/backfill (MLB; NFL is backlog N1) | forecast + archive | none (public) |

Subscription notes: api-sports products are licensed separately —
football, baseball-odds, and american-football each need coverage on
your plan (a bundled key may serve all three; the clients fall back to
`API_FOOTBALL_KEY` where blank). Copy `.env.example` → `.env` and fill.

## Required local components

- Python 3.10+ with: `sqlalchemy requests python-dotenv click rich`
  (CLI core) plus `fastapi uvicorn jinja2` (web UI).
- SQLite (bundled with Python) — `data/sports.db`, created by `init-db`,
  **gitignored and irreplaceable** (point-in-time odds snapshots cannot
  be re-synced). Back up DAILY, and mandatorily before any
  `soccer-refresh` (CLAUDE.md law 5; `.backup` API only):
  `sqlite3 data/sports.db ".backup ~/backups/sports_$(date +%F).db"`.
- `.env` from `.env.example` (gitignored).
