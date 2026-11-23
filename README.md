# Sports Predictor

Each statement here names its receipt: a path, a command, an addendum or an
Issue (addendum 276 item 2). This file describes; the rules are in
[CLAUDE.md](CLAUDE.md) and [CONTRIBUTING.md](CONTRIBUTING.md), repeated nowhere here.

## What it is

- A multi-sport prediction and calibration system (Python, SQLite and
  SQLAlchemy, CLI-driven) that feeds a browser Cockpit (CLAUDE.md, opening).
- The mission, quoted from CLAUDE.md "Mission" (architect, 2026-09-26):
  "Generate consistent income from sports predictions — sports as
  commodities, every game an asset class, optimized for prediction markets
  (Kalshi-native)."
- Sports and status: CLAUDE.md "Current production state" (MLB, soccer, NFL,
  NHL, NCAA, UNL, the cups, tennis, basketball), the one place status is kept (addendum 276 item
  2(c)). Lanes and dates: `python cli.py roadmap` (docs/roadmap.json).
- Key names: `.env.example`; docs/CLI.md "Required external services"
  describes the providers it lists. Desk sizing: docs/specs/desk-policy-v1.2.md (#732).

> Prediction tool, not betting advice. Outputs are model probabilities
> and their relationship to market prices.

## Where it runs

- **Laptop = BETA**, on `main`; **host = PRODUCTION**, on the latest `vX.Y.Z`
  tag, which `deploy/hosting/sp_deploy.py` checks out detached, never `main`
  (docs/RELEASES.md; its "Release record" has one line per tag).
- **Exports mirror.** A private repo, Sports-Predictor-exports. The host
  pushes `exports/` after every chain step and the laptop pushes to `laptop/`,
  each with `<date>/` folders and a `latest/<kind>.json` per kind
  (docs/specs/exports-mirror.md; `deploy/hosting/exports_mirror.py`).
- **Cockpit.** The operated surface (addendum 276 item 1) is a Claude artifact
  published separately; `tools/cockpit.html` is the repo copy (CLAUDE.md,
  opening). Since Cockpit v2 (addendum 307 item 2) the published page reads the
  mirror through the operator's own claude.ai GitHub connector, read-only: that
  is the primary path. The F2.5 token box stays, folded, as the fallback; the
  artifact's CSP blocks api.github.com, so the token path works only when served
  locally by `scripts/cockpit_local.py` (docs/specs/exports-mirror.md, setup
  step 6 and "Published artifact").
- **Web UI.** `python main.py` serves FastAPI on `localhost:8000` (docs/CLI.md
  "Web UI"; host unit `deploy/hosting/systemd/sp-web.service`).
- **Databases.** `data/` is gitignored (`.gitignore`). The host makes a daily
  `.backup` (`deploy/hosting/sp_backup.py`), and the laptop pulls it with
  `deploy/hosting/pull_backup.py` (docs/CLI.md "Hosting — laptop side").

## How work flows

The rules: CONTRIBUTING.md "Workflow" and CLAUDE.md "Workflow". The pieces:

- Branch and pull request, merged by the operator (ruling 2026-09-25); Codex
  reviews as input (ruling 2026-10-05); the review stop rule (addendum 7 item
  2). All three are in CLAUDE.md "Workflow".
- Merge by exact head: the architect's merge block names a head, and the
  operator merges at that head (addendum 276 item 1; BACKLOG.md, 2026-10-14,
  addendum 68 item 1).
- `laptop/` hand-off branches: the laptop's files arrive on an origin
  `laptop/<name>` branch, and Code's PR merges it (addendum 265 item 4;
  BACKLOG.md, 2026-10-09, addendum 28 item 5). The registry's cross-ref guard
  fetches origin `laptop/*` (#329; `src/walters/registry.py`).
- The main ruleset is GitHub ruleset 26733425, "main — no force push, no
  deletion" (addendum 276 item 5, recorded in BACKLOG.md's 2026-11-06 entry).
- CI: `.github/workflows/ci.yml` runs parse, import smoke, pytest, and the
  fragments and roadmap checks; `pr-body.yml` checks the body; `ledger.yml`
  runs the Issue automation (docs/LEDGER.md). The tag ritual: docs/RELEASES.md.

## Where the truth lives

- **Issues** are the state ledger, and the Project board holds the order
  (docs/LEDGER.md; CLAUDE.md "Queue").
- **BACKLOG.md** is the history of rulings and verdicts, newest first, and
  **CHANGELOG.md** the change record, written through docs/ledger/entries/ and
  changelog.d/ fragments (CONTRIBUTING.md law 6). `python scripts/ledger.py
  compile --commit` folds the fragments in and deletes them
  (docs/ledger/entries/README.md; changelog.d/README.md).
- **docs/roadmap.json** holds the dates, and `python cli.py roadmap` prints
  them read-only (CLAUDE.md "Queue").
- **docs/registry/** is the experiment registry: `experiments.json`, the
  `ids/` sidecars (docs/REGISTRY.md, #212) and the one-run reservations
  `<id>.started.json` (addendum 265 item 4).
- **RESULTS.md**: a regenerated snapshot of `python cli.py results-tally`, not
  authoritative in git (its header, ruling 2026-10-01).

## Quickstart

Python 3.10+ (docs/CLI.md "Required local components"; CI uses 3.12,
`.github/workflows/ci.yml`); sync order: CLAUDE.md "Operational notes".

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # key names: .env.example
python cli.py init-db           # the schema (docs/CLI.md "Setup & discovery")
python cli.py sync-competitions --sport soccer
python cli.py sync-teams --competition PL --season "2026/27"
python cli.py sync-matches --competition PL --season "2026/27"
python -m pytest -q tests       # throwaway SQLite (tests/conftest.py), never data/
```

## The chains as they run today

**Host.** The timer files on `main` in `deploy/hosting/systemd/` (times from
`OnCalendar=`, UTC unless a zone is named); the host runs the latest tag
(docs/RELEASES.md "Release record"). A chain timer starts the templated
`sp-chain` service, which runs `deploy/hosting/sp_run.py` over the chain's steps
in `deploy/hosting/chains.py` `CHAINS`. Of the 24 timers, hosting-h1 T11 lists 21
to enable and holds back 3 (`MLB_LAPTOP_ONLY`). `sp-availability-daily`,
`sp-nba-daily` and `sp-tennis-daily` reached `main` after v1.6.4; their enablement
is the architect's block (docs/specs/hosting-h1.md, T11; addendum 252 item 7;
addendum 271 item 3(h); addendum 284 item 1(b)).

| Timer | Runs | When |
|---|---|---|
| sp-backup · sp-backup-prune | `.backup` · retention | daily 09:30 · 05:30 |
| sp-soccer-friday · sp-soccer-saturday | chain soccer-prematch | Fri 14:00 UTC · Sat 10:30 Europe/London |
| sp-soccer-morning-after | chain soccer-morning-after | Sun-Tue 09:50 |
| sp-nfl-lines · sp-nfl-grade · sp-nfl-prematch | chains of those names | daily 15:00 · Mon, Tue, Fri 10:00 · Thu 18:00, Sun 14:00 |
| sp-nhl-daily · sp-intl-daily · sp-availability-daily | chains of those names | 16:00 · 07:20 · 08:45 |
| sp-nba-daily | chain nba-daily | 06:47 |
| sp-tennis-daily | chain tennis-daily | 06:53 |
| sp-ncaa-market · sp-ncaa-schedule · sp-mlb-history | chains of those names | Tue-Fri 16:00, Sat 13:00 · 10:35, 22:35 · 10:30 |
| sp-weekly-fullseason · sp-exports-squash | chain weekly-fullseason · mirror squash | Sun 06:00 · Sun 06:10 |
| sp-window · sp-cup-observe · sp-closing-watch | chain window · `observe-cup-lineups` · closing watch | :05 · every 5 min (both in hours 00-03, 06-23) · every minute |
| sp-mlb-morning · sp-mlb-preslate · sp-clv-capture | MLB chains | held back (`MLB_LAPTOP_ONLY`) |

`soccer-refresh` has a service and no timer, and the operator starts it
(`deploy/hosting/systemd/sp-soccer-refresh.service`; `deploy/hosting/chains.py`, H0-6).

**Laptop.** The morning routine's steps are one committed list and one
command (addendum 451 item 3): `python deploy/hosting/laptop_routine.py
[--weekly] [--dry-run]`. It refuses (exit 2, nothing run) unless the
machine's role reads `laptop`, and runs each step on the checkout's `cli.py`
in order, a failing step never stopping the next. The daily list, in its
order: MLB (`sync-matches` from 2026-10-15 to tomorrow, the
`retire-orphans` dry run, `evaluate`, `improve --hold-on-pass`,
`export-results`, `sync-kalshi`), NBA and NCAAMB one day at a time (today-2
to tomorrow), NCAA (`sync-teams`, `sync-matches` today-8 to yesterday, the
`dedupe-matches --orphans` dry run), NHL's three days, its fixtures export
and `nhl-goalie-sync`, ATP and WTA with their two Kalshi syncs, and
`results-tally`. `--weekly` adds the whole-season pass before NCAA's
`sync-teams`: `sync-teams` and `sync-matches` for every competition-season
in the laptop's database with a game from 2026-07-01, except MLB, ATP, WTA,
WC and NCAA. The list itself is `DAILY` in the module. The architect's
block keeps the rest (item 3(c)): the backup, first (the command is not
called if it failed), then `coverage`, then the command; the roadmap read,
the mirror push, the stale count and the read of the four guarded college
rows. No timer, no launchd job, no page, and never `soccer-refresh`. The
six MLB steps stay through the off-season; `mlb-preslate` is ruled when the
season nears (item 3(f) 7). docs/CLI.md "MLB daily operation" holds an
earlier two-phase text of the morning chain (architect 2026-10-01).

## CLI reference

The full command catalog is **[docs/CLI.md](docs/CLI.md)**, and
`python cli.py --help` lists every command.
