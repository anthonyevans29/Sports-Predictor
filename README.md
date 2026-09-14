# Sports Predictor

A **local browser app** for Walters-style sports prediction modeling. Runs entirely on your machine: FastAPI server on `localhost`, SQLite on disk, browser as the UI.

Starts with soccer (Arsenal's competitions) and is built to extend to NFL, MLB, and NHL.

> **This is a prediction tool, not betting advice.** Outputs are model probabilities and value edges vs. market odds.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (Chrome / Safari / Firefox) — localhost:8000       │
│    Dashboard · Competitions · Teams · Matches               │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP
┌──────────────────────────────┴──────────────────────────────┐
│  FastAPI + Jinja2 + Tailwind + HTMX                          │
│    Server-rendered HTML. No build step.                      │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│  Walters Engine (Phase 2) — handicapping, value, staking     │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│  Modeling layer (Phase 2) — Elo, Poisson xG, factors         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│  Data layer — API-Football → normalized → SQLite             │
└─────────────────────────────────────────────────────────────┘
```

Adapter pattern is retained even though we have one source today, so adding NFL/MLB/NHL adapters in Phase 5 is mechanical work.

## Project structure

```
sports_predictor/
├── README.md
├── requirements.txt
├── .env.example
├── config.py                  # Settings from env
├── cli.py                     # Data sync commands
├── main.py                    # `python main.py` → boots server + opens browser
└── src/
    ├── db/                    # SQLAlchemy schema, session
    ├── adapters/              # API-Football + base contract
    ├── ingestion/             # Adapter → DB orchestration
    ├── models/                # Phase 2: Elo, Poisson xG
    ├── walters/               # Phase 2: handicapping, value, staking
    └── web/
        ├── app.py             # FastAPI app factory
        ├── routes/            # home, competitions, teams, matches
        ├── templates/         # Jinja2 + Tailwind classes
        └── static/            # CSS, JS
```

## Setup (macOS)

Requires Python 3.11+. If you don't have it:

```bash
brew install python@3.12
```

Then:

```bash
# 1. Unzip and enter
tar -xzf sports_predictor.tar.gz && cd sports_predictor

# 2. Create + activate a virtual environment
python3 -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your .env (DO NOT commit this file)
cp .env.example .env
# Then open .env and paste in your API_FOOTBALL_KEY.
# If your key is from RapidAPI rather than direct api-sports.io,
# set API_FOOTBALL_HOST=api-football-v1.p.rapidapi.com

# 5. Initialize the local database
python cli.py init-db
```

### Load data

The CLI handles all data ingestion. The web app is read-only — it shows what's already in your DB.

```bash
# Pull the curated competition list
python cli.py sync-competitions

# Teams for the current season — do this for each competition
python cli.py sync-teams --competition PL  --season 2024/25
python cli.py sync-teams --competition CL  --season 2024/25
python cli.py sync-teams --competition FAC --season 2024/25
python cli.py sync-teams --competition EFL --season 2024/25
python cli.py sync-teams --competition EL  --season 2024/25

# Matches: backfill multiple seasons. With a paid plan you can pull
# 3-5 seasons without hitting rate limits.
python cli.py sync-matches --competition PL  --seasons 3
python cli.py sync-matches --competition CL  --seasons 3
python cli.py sync-matches --competition FAC --seasons 2
python cli.py sync-matches --competition EFL --seasons 2
python cli.py sync-matches --competition EL  --seasons 2

# Detailed per-match stats (shots, possession, xG, cards).
# Costs 1 API request per match — use --limit to control burn rate.
python cli.py sync-stats --competition PL --season 2024/25 --limit 100

# Check status
python cli.py status
```

### Run the model

After you've loaded matches (Phase 1 setup above), you can train a model and start producing predictions:

```bash
# 1. Fit a fresh model from all historical data
python cli.py train

# 2. The first train run creates a "candidate" — promote it to production:
python cli.py improve
# (With no existing production model, the candidate is auto-promoted.)

# 3. Generate predictions for upcoming fixtures
python cli.py predict --competition PL --season 2024/25
python cli.py predict --competition CL --season 2024/25

# 4. (Optional) Pull bookmaker odds so value detection has prices to compare against
python cli.py sync-odds --competition PL --season 2024/25 --limit 20

# 5. After fixtures have finished, score the predictions
python cli.py evaluate

# 6. The full improvement loop — run nightly (or whenever you want)
#    Evaluates → trains a new candidate → compares to production → promotes if better
python cli.py improve

# Inspect: list trained model versions
python cli.py model-versions

# Inspect: read the post-mortem feed for recent evaluated predictions
python cli.py model-report --limit 30
```

### MLB (Phase 5)

Baseball uses the official MLB Stats API — free, no API key required. Workflow mirrors soccer but with the `--sport baseball` flag where applicable, and competition codes `MLB` (regular season + postseason) or `MLB_SPRING` (Spring Training):

```bash
# Register the MLB competition
python cli.py sync-competitions --sport mlb

# Pull all 30 MLB teams for the current season
python cli.py sync-teams --competition MLB --season 2026

# Full season schedule (one API call — fast)
python cli.py sync-matches --competition MLB --season 2026

# Train a baseball model and promote it
python cli.py train --sport mlb
python cli.py improve --sport mlb

# Generate predictions for upcoming games
python cli.py predict --sport mlb --competition MLB --season 2026

# After games finish
python cli.py evaluate --sport mlb
```

Or — easier — run all of this from the **Admin page** (`http://localhost:8000/admin`). The forms have a Sport selector for the sport-aware actions, and the sync commands auto-route to the right adapter based on competition code.

### Launch the app

```bash
python main.py
```

Your default browser opens to `http://localhost:8000`. If you want to launch without auto-opening a tab, set `OPEN_BROWSER=false` in `.env`.

For development with auto-reload:

```bash
uvicorn src.web.app:app --reload
```

## Supported competitions

Canonical codes used throughout the app (CLI + URLs):

| Code   | Competition              |
|--------|--------------------------|
| PL     | Premier League           |
| ELC    | Championship             |
| FAC    | FA Cup                   |
| EFL    | EFL (Carabao) Cup        |
| CS     | Community Shield         |
| CL     | UEFA Champions League    |
| EL     | UEFA Europa League       |
| UECL   | UEFA Conference League   |
| PD     | La Liga                  |
| SA     | Serie A                  |
| BL1    | Bundesliga               |
| FL1    | Ligue 1                  |

To add another competition: look up its league ID at `/leagues?name=...` on api-football.com, then add to `_CODE_TO_LEAGUE_ID` in `src/adapters/api_football.py`.

## Walters methodology, mapped (Phase 2)

| Walters concept              | Module                   | Soccer adaptation                                |
|------------------------------|--------------------------|--------------------------------------------------|
| Power ratings (spread)       | `models/elo.py`          | Elo rating + Poisson goal expectation            |
| Player values / injuries     | `models/factors.py`      | Squad availability deltas vs full-strength xG    |
| Home advantage, rest, travel | `models/factors.py`      | League-calibrated home boost, days-rest curves   |
| Line shopping / value        | `walters/value.py`       | Model probability vs implied odds across books   |
| Unit sizing / bankroll       | `walters/staking.py`     | Fractional Kelly with conservative cap           |
| **Post-mortem review**       | `walters/evaluation.py`  | Score every prediction once the match finishes; surface what went right/wrong |
| **Model improvement loop**   | `walters/training.py`    | Auto-retrain ratings + factor weights from yesterday's residuals; version & promote |

## Prediction tracking & model improvement (Phase 2 — captured)

Two features that need to inform Phase 2's design from the start:

### 1. Historical prediction results

Every prediction we make gets stored in the existing `predictions` table with a `model_version`. After matches finish, an evaluation pass writes back per-prediction scoring into a new `prediction_outcomes` table:

- `actual_result` (H/D/A), `actual_home_score`, `actual_away_score`
- `log_loss`, `brier_score`, `rps` (ranked probability score)
- `top_pick_hit` (did the highest-probability outcome happen)
- `value_realized_pct` (if we logged a market price at prediction time)
- `notes` (auto-generated post-mortem: "predicted Arsenal -1.5 too confidently — model didn't see the Saliba injury")

A `/predictions` page in the UI will show:
- Recent prediction accuracy per model version
- Calibration plot (predicted 70% should win ~70% of the time)
- Worst misses with factor breakdowns — *what the model weighted heavily and shouldn't have*
- Win/draw/loss accuracy by competition (model may be sharp on PL, weak on FAC)

### 2. Model improvement loop

A `walters/training.py` module runs a nightly pass over yesterday's finished matches:

1. **Score** all predictions against actuals (writes `prediction_outcomes`).
2. **Diagnose** systematic errors — are we over-confident on big home favorites? Under-rating recent-form swings? This is a regression of residuals against the factor inputs.
3. **Update** rating parameters: Elo K-factor, home advantage, attack/defense priors per team, factor weights. Done as a Bayesian update so we don't whipsaw on noise.
4. **Version** the new model: insert a row in a `model_versions` table with parents + parameters. Keep the old version live until the new one beats it over a holdout window.
5. **Promote** the new version when its rolling log-loss is meaningfully better than production. Otherwise it stays a candidate.

The UI surfaces all of this: model lineage, which version is live, candidate models in flight, and the decision boundary that promotes one. This is the Walters edge — the model is never finished, it's always reacting to what it just got wrong.

## Roadmap

- [x] **Phase 1** — Data foundation (API-Football adapter, normalized schema, ingestion CLI)
- [x] **Phase 1.5** — Local browser UI (FastAPI dashboard, competitions/teams/matches views)
- [x] **Phase 2** — Modeling engine + evaluation + improvement loop:
  - Elo + Poisson xG baseline model (`src/models/`)
  - Factor adjustments (rest days; injuries/weather stubs ready for Phase 3)
  - Value detection vs bookmaker odds (`src/walters/value.py`)
  - Fractional Kelly staking with hard cap (`src/walters/staking.py`)
  - **Prediction outcome tracking** (`src/walters/evaluation.py`) — log loss, Brier, RPS, top-pick accuracy, templated post-mortems
  - **Model improvement loop** (`src/walters/training.py`) — nightly: score → train candidate → compare → promote if better
  - Model versioning in DB (`ModelVersion` + `PredictionOutcome` tables)
- [x] **Phase 2.5** — League-first dashboard:
  - **Home page is a league dashboard**: pick a league (PL default), see upcoming fixtures, league table, recent results
  - **Drill-down to clubs**: click any team in any league context to go to that club's focused view
  - League selector in the nav, persisted in cookie + preferences
  - "My clubs" sidebar (Arsenal pinned by default) for quick context-switching
- [x] **Phase 3** — Predictions in the UI:
  - Probability badges on every fixture in the league dashboard
  - Match detail page: full prediction panel (1X2 bar, xG, most-likely score, factor breakdown, odds vs model with edge highlighting)
  - `/predictions` page: per-model accuracy stats, calibration plot, post-mortem feed
  - Value-edge alerts panel on the dashboard (when odds are loaded)
  - **Live injury data** wired in: `sync-injuries` command, `injuries` table, `factors.injury_adjustment` computes xG impact from real player availability
- [x] **Phase 4** — UI-driven operations:
  - `/admin` page with action buttons for every sync / model command
  - Background job runner with live polling status feed
  - Localhost-only guard on admin endpoints
  - **Lineup ingestion**: projected (recent starters heuristic) before kickoff, confirmed at T-20min
  - **Soccer expansion**: FIFA World Cup, World Cup Qualifiers (all 6 confederations), International Friendlies, UEFA Euros
- [x] **Phase 5** — Multi-sport: MLB (baseball):
  - **MLB Stats API adapter** (`src/adapters/mlb_stats_api.py`) — official free endpoint, no API key
  - **Baseball scoring model** (`src/models/baseball.py`) — Pythagorean win expectation + negative binomial run distribution + starting pitcher impact
  - Sport-aware training: soccer Elo+Poisson and MLB Pythag+negbin live side-by-side; the improvement loop and evaluation handle both
  - `MatchParticipant` table (sport-agnostic): stores MLB starting pitchers, extensible to NFL QBs / NHL goalies
  - **Sport switcher** in the nav: ⚽ Soccer ↔ ⚾ Baseball pill toggle
  - Baseball-style standings (W-L-Pct, run differential) when viewing MLB
  - CLI commands take `--sport` flag where relevant; sync commands auto-route by competition code
- [ ] **Phase 6** — NFL (SportsDataIO), NHL adapters + spread-based models. Same sport-aware pattern.

## Troubleshooting

**`No teams matching 'Arsenal'` on the dashboard** — you haven't synced any teams yet. Run `python cli.py sync-teams --competition PL --season 2024/25`.

**`401 Unauthorized` from the API** — your `API_FOOTBALL_KEY` is wrong or your `API_FOOTBALL_HOST` doesn't match your key's provider (direct vs RapidAPI). Double-check both.

**`Competition PL not in DB`** — run `python cli.py sync-competitions` first. The CLI sub-commands run in this order: competitions → teams → matches → stats.

**Port 8000 already in use** — set `WEB_PORT=8001` in `.env`.

**Browser doesn't auto-open** — that's fine, just navigate to the URL printed in the terminal.
