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
| `data-freshness` | `--sport --season` | Diagnose whether model inputs are current. |
| `model-versions` | | Trained model versions and their status (production / rejected / shelved). |
| `show-config` / `set-config` | `--sport --field --value --yes` | Inspect / edit the production model's frozen config (gated; logs manual overrides). |

## Core data syncs (all sports)

| Command | Options | Purpose |
|---|---|---|
| `sync-matches` | `--competition --season --seasons N --date-from --date-to --date` | Schedules, scores, statuses. `--seasons N` backfills N seasons (sport-aware season strings). |
| `sync-odds` | `--competition --season` | Book odds for upcoming games (soccer & MLB bulk path). |
| `sync-injuries` | `--competition --season` | Current injury/status report per team. NFL: positions joined from the roster endpoint. |
| `capture-odds` | `--sport --competition --season` | Lightweight odds-only capture for CLV tracking. |
| `wipe-injuries` | `--confirm` | Destructive reset of the injuries table. |

## MLB daily operation

Pre-slate chain, in order: `sync-matches --date` → `sync-bullpen-stats` →
`sync-pitchers` → `sync-pitcher-stats` → `sync-odds` → `sync-kalshi` →
`predict` → `sync-umpires` → `capture-weather` → `export-predictions`.

Morning grading: `sync-matches` → `evaluate` → `improve` →
`sync-appearances --recent` → `sync-umpires --recent` → `export-results`.

| Command | Options | Purpose |
|---|---|---|
| `sync-pitchers` | `--competition --season` | Probable starters per game. |
| `sync-pitcher-stats` | `--season` | Season-to-date stats for probables. |
| `sync-bullpen-stats` | `--season` | Bullpen aggregates for all 30 teams. |
| `sync-appearances` | `--competition --season --recent` | Pitcher appearances (feeds bullpen availability). |
| `sync-umpires` | `--competition --season --recent` | Umpire assignments + environment. |
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

## NFL operation (rehearsal phase)

Weekly rhythm: `sync-odds-nfl` + `sync-kalshi-nfl` every day or two as
lines post; after game days `sync-matches --competition NFL` then
`nfl-grade`. Prediction generation is internal until the dress rehearsal
passes.

| Command | Options | Purpose |
|---|---|---|
| `sync-odds-nfl` | | Per-game book odds for upcoming NFL games (moneyline, spreads with sign, totals with lines). |
| `sync-kalshi-nfl` | | Kalshi `KXNFLGAME` markets via the shared two-sided matcher. |
| `predict-nfl` | | Write v1 Elo predictions for upcoming games (match-only upsert). |
| `export-nfl-predictions` | | Rehearsal-format export (`rehearsal: true`; QB status in input_quality). |
| `nfl-backtest` | | Walk-forward backtest against the frozen phase-2 gate. |
| `nfl-grade` | | Grade predictions vs finished games + banked closer consensus (sides, log-loss, CLV). |
| `export-nfl-results` | | Graded NFL results file for the consumer (standard results shape, rehearsal-flagged). |

## Gated competitions (cups)

No predictions ship until the cup path passes its acceptance test. Data
syncs run normally; the consumer receives market-only files:

| Command | Options | Purpose |
|---|---|---|
| `export-fixtures` | `--competition --start --end` | Market-only fixtures file (matches + odds tables only; `contains_predictions: false`). |

## Prediction, evaluation, improvement

| Command | Options | Purpose |
|---|---|---|
| `predict` | `--sport --competition --season` | Write predictions for upcoming games (production model). |
| `evaluate` | `--sport` | Grade finished games (sides, totals, CLV; overnight closer backfill). |
| `improve` | `--sport --force-input-eval` | Train a candidate and gate it vs production on the frozen holdout. Rejection is the normal outcome. |
| `backtest` | `--season --competition` | Leakage-free historical re-run of the current model. |
| `export-predictions` | `--sport --competition --start --end --status` | Consumer prediction file with input_quality vocabulary. |
| `export-results` | `--sport --competition --date` | Graded results file (top-pick, totals pulse annotations). |
| `results-tally` | `--days` | Regenerate `RESULTS.md` — rolling per-sport record (sides, log-loss, CLV). |

## Diagnostics & research

| Command | Options | Purpose |
|---|---|---|
| `card` | `--sport --date` | Daily confidence ladder + per-game signal drill-down (MLB; multi-sport is backlog U1). |
| `market-alignment` | `--sport --date` | Model pick/prob vs market per upcoming game. |
| `clv-report` | `--sport --since --market` | Closing-line-value report over graded games. |
| `kalshi-disagreement` | `--since` | How often/how much Kalshi disagrees with books. |
| `totals-check` / `calibration-series` | `--sport --since / --lo --hi` | Totals grading; band calibration diagnosis. |
| `model-report` | `--limit` | Recent outcomes post-mortem feed. |
| `miss-analysis` | `--min-n` | Bucket all graded predictions across categories. |
| `signal-residuals` | | Do tracked signals predict model residuals? |
| `umpire-report` | `--min-games` | Per-umpire run environment (tracked data only). |
| `bullpen-availability` / `bullpen-effectiveness` / `bullpen-diagnostic` | various | Bullpen usage, effectiveness, and hypothesis tests. |
| `scenarios` | `--date` | What-if decomposition of a day's predictions. |

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
| **Kalshi** (public market API) | Second market source: MLB (`KXMLBGAME`), NFL (`KXNFLGAME`), EPL (`KXEPLGAME`) | series/markets listing | none (public read) |
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
  be re-synced). Back up weekly:
  `sqlite3 data/sports.db ".backup ~/backups/sports_$(date +%F).db"`.
- `.env` from `.env.example` (gitignored).
