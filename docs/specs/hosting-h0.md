# Hosting H0 — always-on host for the chains (draft)

**Status: DRAFT for architect review — not a decision.** Nothing here is
built, bought, or scheduled. Every open choice is marked
**ARCHITECT-RULE** and collected at the end. Written 2026-09-26 from the
repo as it stands on `main` (docs/CLI.md, docs/pl_weekly_routine.md,
cli.py, config.py, .env.example, scripts/setup_clv_capture.sh, CLAUDE.md,
BACKLOG.md). Queue position: this is groundwork for the T-track scheduler
item, which holds its place behind Cockpit v0.4, K and B; H0 does not jump
the queue.

---

## 1. Goals and non-goals

**Goals**
- Run the existing CLI chains on an always-on Linux host so they stop
  depending on a laptop being awake (the launchd CLV-capture jobs
  already carry that caveat: "It won't fire if the machine is fully
  powered off through the window").
- Keep every chain exactly as documented: the host runs `python cli.py
  <command>` with the same commands and options docs/CLI.md gives. No new
  model logic, no new commands, no changed export contracts.
- Make every scheduled run leave a receipt (law 2) that Anthony can paste
  to the architect without opening a shell.
- Zero public attack surface: the host is reachable only over Tailscale.

**Non-goals**
- Not a decision to automate gated steps. `improve` and `soccer-refresh`
  are gate-bearing; whether they run unattended is an ARCHITECT-RULE
  (section 4.3).
- Not hosting the Cockpit. The Cockpit stays a chat-published artifact;
  the host only produces the export files it consumes.
- Not a change to data doctrine. The database never travels casually
  (law 5). **The migration in section 5 is the one sanctioned move**, and
  it goes through the SQLite `.backup` API only — never `cp`, `tar`,
  `rsync` of a live DB file, or any packaging of `data/`.
- Not a multi-user deployment, not a public API, not containers (a plain
  venv + systemd matches how the app runs today).

---

## 2. VPS candidates

Sizing basis: the production DB was ~83 MB at the 2026-09-21 incident
(BACKLOG); the heaviest workloads are `soccer-refresh` (Elo/Poisson
retrain over ~16.5k matches) and `improve` (numpy/pandas/scipy). 2 vCPU /
4 GB RAM / 40 GB disk is comfortable headroom; 1 vCPU / 2 GB is the
floor. Region matters little for the chains (all providers are HTTP APIs)
but US-East sits closest to Kalshi and to the MLB/NFL/NHL slate clock.

**All prices are approx., verify at purchase** — no live pricing was
checked for this draft; figures are recalled list prices and providers
revise them (Hetzner revised its cloud line in 2025).

| Option | Plan (approx.) | vCPU / RAM / disk | Approx. monthly | Regions of note | Notes |
|---|---|---|---|---|---|
| A. Hetzner Cloud | CX22-class (shared, Intel/AMD) | 2 / 4 GB / 40 GB | ~EUR 4-5 (+ ~EUR 1 backup option) | EU only for the CX line (Falkenstein, Nuremberg, Helsinki) | Cheapest by far. US regions (Ashburn, Hillsboro) exist only for the pricier CPX line (~EUR 8-15). Plan names may have changed — verify. |
| B. Hetzner Cloud | CX32-class | 4 / 8 GB / 80 GB | ~EUR 7-9 | EU | Headroom if `improve`/refresh run long. |
| C. DigitalOcean | Basic droplet, regular | 2 / 4 GB / 80 GB (1 / 2 GB at ~USD 12) | ~USD 24 | NYC, SFO, TOR, AMS, LON, FRA | Simple UI, weekly-backup add-on ~20% of droplet price. |
| D. Akamai / Linode | Shared 4 GB | 2 / 4 GB / 80 GB | ~USD 24 | Newark, Atlanta, Dallas, Fremont, EU | Comparable to DO. |
| E. Vultr | Regular cloud compute | 2 / 4 GB / 80 GB (1 / 2 GB at ~USD 10) | ~USD 20 | New Jersey, Chicago, many | Comparable; hourly billing. |

Draft lean (not a ruling): A for cost if EU-hosted is acceptable, else
C/D/E at ~USD 20-24 in a US-East region. Provider snapshots are NOT a
substitute for the `.backup` law — a disk snapshot of a live SQLite file
has the same hazard as `cp`.

- **ARCHITECT-RULE H0-1:** provider + plan + region (EU-cheap vs
  US-East).
- **ARCHITECT-RULE H0-2:** monthly budget ceiling for hosting (including
  any off-host backup storage).

---

## 3. Tailscale-only posture

| Control | Setting |
|---|---|
| Ingress | `ufw default deny incoming`, `ufw default allow outgoing`; allow in on `tailscale0` only. No public ports at all — not 22, not 8000. Provider cloud firewall mirrors this (deny-all inbound) as a second layer. |
| SSH | Either Tailscale SSH (`tailscale up --ssh`, ACL-scoped to Anthony's devices), or OpenSSH with `ListenAddress <tailnet IP>`, key-only, `PermitRootLogin no`. One of the two, not both. |
| Web UI | `python main.py` stays bound to `127.0.0.1:8000` (`WEB_HOST=127.0.0.1`, `OPEN_BROWSER=false`). Reached from Anthony's machine by `ssh -L 8000:127.0.0.1:8000 <host>` over the tailnet. Rationale in the note below. |
| Secrets | Root-owned `/etc/sports-predictor/env`, mode `0600`, loaded by each unit via `EnvironmentFile=`. No `.env` in the repo checkout. Variable NAMES in use (values never written into docs): `API_FOOTBALL_KEY`, `API_FOOTBALL_HOST`, `API_FOOTBALL_RPM`, `API_BASEBALL_KEY`, `API_AMERICAN_FOOTBALL_KEY`, `API_HOCKEY_KEY`, `ODDS_API_KEY`, `DATABASE_URL`, `WEB_HOST`, `WEB_PORT`, `OPEN_BROWSER`, `LOG_LEVEL`. (`API_AMERICAN_FOOTBALL_KEY` and `API_HOCKEY_KEY` are read in `src/` but are absent from `.env.example` — see section 8.) |
| Service user | Dedicated unprivileged `sp` user owns the checkout, venv, `data/`, `exports/`, logs. Units run `User=sp`. `data/` is `0700`. |
| Patching | `unattended-upgrades` for security updates; automatic reboot window set outside all timers (e.g. 04:30 UTC) — ARCHITECT-RULE H0-3 on whether auto-reboot is allowed at all. |
| Code deploy | `git pull --ff-only origin main` in the checkout, by hand, only after Anthony merges. The host never builds from a branch, never pushes, and has no tarball step (the tarball flow and its packaging law stay on the laptop side). Read-only deploy key. |
| Cockpit | Stays chat-published. The host serves no artifact. |

**Why an SSH tunnel and not `tailscale serve` or a tailnet bind (read
from `src/web/guards.py`):** the admin routes use `require_localhost`
(client address must be loopback) and the app installs
`TrustedHostMiddleware` with `allowed_hosts(settings.host)`.
- Binding `WEB_HOST` to the tailnet IP: every tailnet client is non-
  loopback, so `/admin` returns 403 — safe but loses admin.
- `tailscale serve` proxies from localhost: every tailnet peer would
  arrive as loopback and pass `require_localhost` — that silently
  widens the admin guard to the whole tailnet, and the `*.ts.net` Host
  header is not in the allowlist, so it would also need a config change.
- SSH `-L`: requests arrive as loopback only for someone who already
  holds a shell on the box. No code change, guard semantics unchanged.

- **ARCHITECT-RULE H0-4:** web UI access mode (SSH tunnel as drafted,
  vs `tailscale serve` with a deliberate guard change, vs not running
  the web UI on the host at all).

---

## 4. systemd unit inventory

### 4.1 Conventions (proposed, nothing built)

- Every chain unit is `Type=oneshot`, `User=sp`,
  `WorkingDirectory=/opt/sports-predictor`,
  `EnvironmentFile=/etc/sports-predictor/env`,
  `OnFailure=sp-notify@%n.service`, `TimeoutStartSec=` generous (2h for
  refresh/improve).
- Every chain step runs through one small wrapper, `sp-run` (proposed;
  does not exist yet), which: takes the DB lock (`flock
  /run/sports-predictor/db.lock`) so no two chains write SQLite at once;
  runs the listed `python cli.py ...` steps in order and stops at the
  first non-zero exit; appends one receipts line per step and one per
  chain (section 6).
- Timers use `Persistent=true` (a missed firing runs at next boot, the
  launchd catch-up behaviour) and `RandomizedDelaySec=` 0 for
  kickoff-anchored chains.
- Schedules below are given in UTC. systemd `OnCalendar=` accepts an
  IANA zone suffix (e.g. `Sat 09:30 Europe/London`), which is the
  proposed way to keep kickoff-anchored soccer runs stable across the UK
  clock change (BST ends 2026-10-25) and US-anchored runs across the US
  change (2026-11-01). UTC equivalents shown are for the current (summer)
  offsets.
- Relative dates (`<yesterday>`, `<SAT-date>`) are computed by `sp-run`
  with `date -u`; the command text is otherwise verbatim from the docs.
- **Backup-before-chain:** `sp-backup.service` is a oneshot that writes
  a `.backup` copy plus its sha256. The morning chain declares
  `Requires=sp-backup.service` + `After=sp-backup.service`, so a failed
  backup blocks the morning chain (CLAUDE.md: "Morning chains open with
  the backup line"). `soccer-refresh` gets its own
  `sp-backup-prerefresh.service` with the same `Requires/After`, so the
  refresh is always preceded by a backup taken seconds before it, never
  by the morning one (law 5: "mandatory before any soccer-refresh").
  Note from cli.py: `soccer-refresh` itself does not check for a backup
  — the guarantee lives only in the unit ordering, so the unit is the
  enforcement point.

Backup command (CLI.md's line, made daily and UTC-dated; `.backup` API
only):
`sqlite3 data/sports.db ".backup /var/backups/sports-predictor/sports_$(date -u +%F).db"`
then `sha256sum` of the backup file into the receipt. Pre-refresh
backups use a `_prerefresh_<HHMM>` suffix so they never overwrite the
daily one. Requires the `sqlite3` CLI package on the host.

### 4.2 Inventory

Schedule rationale anchors: MLB first pitches ~16:00-17:00 UTC at the
earliest (day games), most ~23:00 UTC; PL Saturday early kickoff 12:30 UK
(11:30 UTC in BST); NFL Sunday slate from ~17:00 UTC; NHL puck drops
~23:00 UTC.

| # | Unit (.service + .timer) | ExecStart steps (`python cli.py ...`, as CLI.md gives them) | Schedule (UTC) | Rationale | Deps |
|---|---|---|---|---|---|
| 0 | `sp-backup` | `sqlite3 data/sports.db ".backup ..."` + sha256 | daily 09:30 | Opens the morning; before any writer. | Conflicts with nothing; takes the DB lock. |
| 1 | `sp-mlb-morning` | `sync-matches` (MLB, yesterday window) -> `evaluate --sport mlb` -> `improve --sport mlb` -> `sync-appearances --recent` -> `sync-umpires --recent` -> `export-results --sport mlb` -> `results-tally` | daily 09:45 | West-coast finals are in; grading before pre-slate. `results-tally` added at the end (CLI.md lists it under evaluation, not in a chain — ARCHITECT-RULE H0-9). | `Requires=`+`After=sp-backup`. `improve` unattended: H0-5. |
| 2 | `sp-mlb-preslate` | `sync-matches --date` (see discrepancy D1) -> `sync-bullpen-stats` -> `sync-pitchers` -> `sync-pitcher-stats` -> `sync-odds` -> `sync-kalshi` -> `predict` -> `sync-umpires` -> `capture-weather` -> `export-predictions` (MLB options: `--competition MLB --season 2026`, `--sport mlb`) | daily 14:30 | ~1.5-2h before the earliest day game; probables and lines posted. | `After=sp-mlb-morning`. Seasonal: H0-8. |
| 3 | `sp-clv-capture` (timer with 4 `OnCalendar=` lines) | `capture-odds --sport mlb --competition MLB --season 2026` (verbatim from scripts/setup_clv_capture.sh) | 4x/day, launchd used 08/12/16/20 **local**; UTC equivalents depend on Anthony's zone | Replaces the 4 launchd jobs one-for-one. | None beyond the DB lock. Local zone: H0-7. |
| 4 | `sp-soccer-friday` | `sync-matches --competition PL --season "2026/27"` -> `sync-odds` -> `sync-injuries` -> `sync-kalshi-soccer` -> `predict --sport soccer --competition PL --season "2026/27"` -> `export-predictions --sport soccer --competition PL --start <SAT> --end <MON+1> --status scheduled` | Fri 14:00 | pl_weekly_routine.md "~afternoon UK time". Midweek rounds need a Tue-Thu variant (H0-10). | Lock only. |
| 5 | `sp-soccer-saturday` | same six steps as #4 | Sat 09:30 (i.e. `Sat 10:30 Europe/London`, ~2h before a 12:30 kickoff) | This capture is the de-facto closing-ish price for CLV — must not be skipped. | Lock only. |
| 6 | `sp-soccer-morning-after` | `sync-matches` (PL) -> `evaluate --sport soccer` -> `export-results --sport soccer --competition PL` | Sun/Mon/Tue 09:50 (after the daily backup) | Interim matchday grading per pl_weekly_routine.md. | `After=sp-backup`. |
| 7 | `sp-soccer-refresh` (**service only, no timer as drafted**) | `soccer-refresh` | operator-started (`systemctl start`) after the final-fixture morning-after | A rejection is stop-and-investigate; drift overrides have been documented by hand. | `Requires=`+`After=sp-backup-prerefresh` and `After=sp-soccer-morning-after`. H0-6. |
| 7b | `sp-backup-prerefresh` | `.backup` with `_prerefresh_<HHMM>` suffix + sha256 | pulled in by #7 only | Law 5. | — |
| 8 | `sp-nfl-lines` | `sync-odds-nfl` -> `sync-kalshi-nfl` | daily 15:00 | CLI.md: "every day or two as lines post". `sync-odds-nfl` also prices NCAA (BACKLOG 2026-09-25). | Lock only. |
| 9 | `sp-nfl-grade` | `sync-matches --competition NFL --season 2026` -> `nfl-grade` -> `export-nfl-results` | Fri, Mon, Tue 10:00 | Mornings after TNF / Sunday / MNF. | `After=sp-backup`. |
| 10 | `sp-nfl-predict` | `capture-weather-nfl` -> `predict-nfl` -> `export-nfl-predictions` | Thu 18:00, Sun 14:00 | Before TNF and the Sunday slate. CLI.md still says "internal until the dress rehearsal passes"; CLAUDE.md says LIVE since Week 3 (D4). | `After=sp-nfl-lines`. |
| 11 | `sp-nhl-daily` (from 2026-10-07) | `sync-matches --competition NHL --season 2026 --date-from <yesterday> --date-to <tomorrow>` -> `sync-odds --competition NHL --season 2026` -> `sync-kalshi-nhl` -> `export-fixtures --competition NHL` | daily 16:00 | CLI.md "NHL daily"; before evening puck drops. Market-only. | `After=sp-backup`. |
| 12 | `sp-ncaa-market` (**not in CLI.md** — D2) | `sync-kalshi-ncaa` -> `export-fixtures --competition NCAA` | Fri 16:00, Sat 13:00 | Kalshi is NCAA's primary market and posts near kickoff. | Only if H0-11 approves. |
| 13 | `sp-weekly-fullseason` | `sync-matches --competition <C> --season <S>` for each live competition (full season, no date window) | Sun 06:00 | CLAUDE.md: "2-day sync windows daily; full-season weekly". Competition list: H0-12. | `After=sp-backup`. |
| 14 | `sp-web` (long-running, no timer) | `python main.py` with `WEB_HOST=127.0.0.1`, `OPEN_BROWSER=false` | always on | Local UI via SSH tunnel (section 3). | `Restart=on-failure`. |
| 15 | `sp-notify@.service` (template) | posts `%i` + last 30 journal lines to Anthony's notification channel | on any unit failure (`OnFailure=`) | Failures must reach a human the same morning. | Channel: H0-13. |
| 16 | `sp-backup-prune` | deletes backups older than the retention window (never the newest 7 dailies, never a `_prerefresh_` less than 30 days old) | daily 05:00 | Disk hygiene. | Retention + off-host copy: H0-14. |

Deliberately **not** scheduled (on-demand only, as today): `init-db`,
`sync-competitions`, `sync-teams`, `db-tune` (CLI.md: "one-shot"; `--vacuum`
"not daily"), `wipe-injuries` (destructive), `set-config`,
`show-config`, `backfill-weather`, `soccer-odds-history`,
`predict-worldcup`, `backtest`, `nfl-backtest`, every diagnostics
command, and cup/UNL `export-fixtures` runs (CLI.md gives no chain for
them).

### 4.3 Gate-bearing steps

`improve` (MLB) is in CLI.md's morning chain and its outcome is a gate
verdict ("Rejection is the normal outcome"); unattended, it would still
promote only through the frozen gate, but no human reads the verdict
line before the pre-slate chain uses the result. `soccer-refresh` is
drafted as operator-started only.
- **ARCHITECT-RULE H0-5:** may `improve --sport mlb` run unattended in
  the morning unit, or does it move to an operator-started unit like
  `soccer-refresh`?
- **ARCHITECT-RULE H0-6:** does `soccer-refresh` stay operator-started
  (drafted), or get a Monday timer that stops at a rejection and pages?

---

## 5. Migration runbook (the one sanctioned move)

Principle: the laptop DB is authoritative until the cutover minute. The
host's copy during the parallel run is a **rehearsal copy and is thrown
away**; cutover is a second, fresh `.backup` migration. This avoids
merging two diverged DBs (point-in-time odds snapshots cannot be
re-synced, so a diverged host DB would silently lack the laptop's
captures).

### 5.1 Prepare the host (no data yet)
1. Provision per section 2; apply section 3 (ufw, Tailscale, SSH, `sp`
   user, `unattended-upgrades`).
2. `git clone` main into `/opt/sports-predictor`; create venv; `pip
   install -r requirements.txt`; install the `sqlite3` CLI.
3. Write `/etc/sports-predictor/env` (0600, root) by hand from the
   variable-name list in section 3.
4. Run `python -m pytest -q` on the host (throwaway SQLite per
   tests/conftest.py) — receipt: pass count. Then `rmdir data` if the
   run created an empty one; `data/` must not exist before step 5.3.

### 5.2 Take the source copy (laptop)
1. Stop launchd CLV jobs for the window (`bash
   scripts/setup_clv_capture.sh --uninstall`) and run no chain.
2. `sqlite3 data/sports.db ".backup /tmp/sp_migrate_$(date -u +%FT%H%M).db"`
   — never `cp` of the live file, never the `-wal`/`-shm` files.
3. `sqlite3 /tmp/sp_migrate_*.db "PRAGMA integrity_check;"` -> must be `ok`.
4. `sha256sum /tmp/sp_migrate_*.db` -> receipt S1.
5. Row-count receipt R1 on the copy: `SELECT COUNT(*)` for each key
   table. Draft list (ARCHITECT-RULE H0-15 to confirm, and names must be
   enumerated from the schema at run time — law 1): competitions, teams,
   matches, predictions, prediction outcomes, odds snapshots, injuries,
   model versions. Plus `python cli.py status` output pointed at the copy
   (via `DATABASE_URL=sqlite:////tmp/sp_migrate_...db`).

### 5.3 Transfer over the tailnet only
6. `scp /tmp/sp_migrate_*.db sp@<host-tailnet-name>:/opt/sports-predictor/data/sports.db.incoming`
   (or `rsync -a --checksum`), over the Tailscale address. No cloud
   bucket, no email, no chat upload.
7. On the host: `sha256sum data/sports.db.incoming` -> receipt S2. **S2
   must equal S1**, else delete and repeat from step 6.
8. `mv data/sports.db.incoming data/sports.db` (host is not running
   anything yet); `chmod 600`.
9. On the host: `PRAGMA integrity_check;` -> `ok`; row counts R2 via the
   same queries; **R2 must equal R1 exactly**; `python cli.py status`
   matches. Delete `/tmp/sp_migrate_*.db` on the laptop once receipts
   are pasted.
10. Re-install launchd CLV jobs on the laptop; the laptop resumes as
    authoritative.

### 5.4 Seven-day parallel run
11. Enable host timers. Both hosts run their chains for 7 consecutive
    days covering at least one full PL weekend (Fri/Sat/morning-after)
    and one NFL Sunday+Monday.
12. Daily comparison receipt: per chain, both hosts' exit codes; export
    file diff (same command, same day) — row counts and a field-level
    diff of `exports/*.json` excluding timestamps; `status` counts delta.
    Divergence that is not explained by capture timing is logged in
    BACKLOG.
13. API quota: the api-sports products are metered (`API_FOOTBALL_RPM`
    exists for rate). Running both hosts doubles calls. Options for
    **ARCHITECT-RULE H0-16**: (a) accept 2x for 7 days if plan headroom
    allows (check the provider dashboard first — receipt); (b) host runs
    only the Kalshi (public, unmetered per CLI.md) and grading steps
    against its rehearsal copy, and full chains only on 2-3 designated
    days; (c) host runs everything, laptop drops to backup-only for the
    week (the host becomes de facto authoritative early — rejected by
    this draft's principle, listed for completeness).
14. Writer of record during the week: the **laptop**. Only laptop
    exports go to the consumer/Cockpit. Host exports are written to
    `exports/` on the host and are comparison-only (**ARCHITECT-RULE
    H0-17** to confirm, or name the host as writer of record).

### 5.5 Cutover criteria (proposed; frozen before the parallel run starts, law 3)
- 7/7 days with every host timer firing on schedule (receipts log shows
  each expected unit line).
- Zero unexplained host-side failures; any `OnFailure` notification
  was received and triaged same day.
- Export diffs clean on the last 3 days (differences only from capture
  timing, each explained).
- A test restore performed on the host: pick one daily host backup,
  `integrity_check` = ok, sha256 matches its receipt.
- Anthony has pulled at least one export from the host via the tailnet
  and loaded it in the Cockpit.
- Ties/partial passes are rejections: extend the parallel run, do not
  cut over.
- **ARCHITECT-RULE H0-18:** approve or amend these criteria before day 1.

### 5.6 Cutover (one morning, before any chain)
15. Laptop: uninstall launchd jobs; stop all chains.
16. Host: disable timers; move the rehearsal DB aside as
    `data/rehearsal_<date>.db` (then delete after cutover receipts).
17. Repeat 5.2-5.3 (fresh `.backup`, S1=S2, R1=R2, integrity ok).
18. Enable host timers. First host backup (unit #0) receipt pasted.
19. Laptop keeps its last `.backup` file cold for 30 days (rollback
    point); its `data/sports.db` is not used for writes again.

### 5.7 Rollback
- Trigger: any host failure that loses a capture window, or a receipt
  mismatch after cutover.
- Steps: disable host timers -> host `.backup` of its current DB ->
  sha256 -> scp to laptop over the tailnet -> integrity + counts on
  laptop -> laptop resumes as authoritative (reinstall launchd). The
  reverse move uses the same `.backup` + checksum + counts protocol; no
  shortcut in either direction.

---

## 6. Receipts-log format

One append-only JSON-lines file: `/var/log/sports-predictor/receipts.jsonl`
(owner `sp`, 0640). `sp-run` writes one `step` line per CLI step and one
`chain` line per unit run. The journal keeps the full stdout; the
receipts line keeps what a reviewer needs.

```json
{"ts":"2026-10-08T09:47:12Z","host":"sp-vps-1","kind":"step","unit":"sp-mlb-morning.service","run_id":"20261008T094500Z-mlb-morning","step":3,"command":"python cli.py improve --sport mlb","exit":0,"duration_s":184.2,"git_sha":"abc1234","tail":["✗ Candidate ... REJECTED — ..."]}
{"ts":"2026-10-08T09:52:40Z","host":"sp-vps-1","kind":"chain","unit":"sp-mlb-morning.service","run_id":"20261008T094500Z-mlb-morning","exit":0,"steps_ok":7,"steps_total":7,"duration_s":475.9,"backup":{"file":"sports_2026-10-08.db","sha256":"<64 hex>","integrity":"ok"},"counts":{"matches":"<n>","predictions":"<n>","odds_snapshots":"<n>"},"exports":["exports/mlb_results_2026-10-07.json"]}
```

Field rules:
- `ts` UTC ISO-8601 with `Z`; `exit` is the process exit code; a chain's
  `exit` is the first non-zero step exit or 0.
- `tail`: the last <=5 console lines of the step verbatim (these carry
  the CLI's own receipts: "✓ Evaluated N predictions", promotion /
  rejection lines, Kalshi matched/unmatched/ambiguous counts). Never
  env values; `sp-run` redacts any line matching a key-shaped pattern.
- `counts`: a fixed small set of table counts read after the chain
  (read-only `SELECT COUNT(*)`), so day-over-day growth is visible.
  Unknown/unavailable counts are `null`, never 0 (law 4).
- `backup` appears on chain lines whose unit depends on a backup unit
  and on backup units' own lines.

Rotation: monthly `logrotate` (`rotate 12`, `compress`,
`dateext`); the file is never truncated in place.

Handoff to the architect: `sp-receipts --since 24h` (proposed; a jq
one-liner) prints a compact table — unit, exit, duration, key tail line,
backup sha256 prefix — that Anthony pastes into chat as-is. Failures are
listed first. Morning ritual: SSH in over the tailnet, run it, paste.

- **ARCHITECT-RULE H0-19:** is the pasted table enough, or should the
  host also write a daily receipts file into `exports/` for the Cockpit
  to ingest (a Cockpit v0.4 intake question)?

---

## 7. Exports path to the Cockpit

Exports land in `/opt/sports-predictor/exports/` on the host (gitignored,
as today). The Cockpit is chat-published and has no route to the host.
Options: Anthony pulls files over the tailnet (`scp`, or Taildrop) and
loads them as today; or a later spec defines a push. This draft assumes
the pull.
- **ARCHITECT-RULE H0-20:** export delivery mechanism host -> Cockpit.

---

## 8. Discrepancies found (CLI.md vs cli.py vs other docs)

Every command name in docs/CLI.md was checked against the
`@cli.command("...")` decorators in cli.py (82 commands): **all CLI.md
command names exist.** Option- and doc-level discrepancies:

- **D1.** CLI.md's MLB pre-slate chain and core-sync table give
  `sync-matches --date`; cli.py's `sync-matches` has `--competition
  --season --seasons --date-from --date-to` and **no `--date` option**.
  The unit would have to use `--date-from <today> --date-to <today>`
  (or whatever Anthony actually types) — to confirm before any unit is
  written.
- **D2.** `sync-kalshi-ncaa` exists in cli.py (and BACKLOG 2026-09-25
  records it as built) but is **absent from CLI.md**; CLI.md also has no
  NCAA chain.
- **D3.** CLI.md's Required-local-components says "Back up weekly";
  CLAUDE.md law 5 and BACKLOG (2026-09-21 upgrade) say **daily plus
  mandatory before soccer-refresh**. CLI.md is stale.
- **D4.** CLI.md's NFL section says prediction generation "is internal
  until the dress rehearsal passes"; CLAUDE.md says nfl_elo_v1 is LIVE
  since Week 3, and cli.py's `export-nfl-predictions` prints "LIVE
  format: rehearsal=false".
- **D5.** CLI.md's external-services table lists Kalshi series MLB/NFL/
  EPL only; CLAUDE.md names four game series (adds KXNHLGAME,
  KXNCAAFGAME).
- **D6.** `API_AMERICAN_FOOTBALL_KEY` (in CLI.md) and `API_HOCKEY_KEY`
  are read in `src/` but are not in `.env.example`; the host env file
  must carry them.
- **D7.** cli.py commands not documented in CLI.md (research/gate tools
  — no scheduling impact): calibration, calibration-deep,
  calibration-fine, calibration-market, cup-exam, dixon-coles-sweep,
  elo-coeff-sweep, kalshi-probe, nfl-backtest-caps, nhl-backtest,
  offense-mechanism, recheck, set-home-boost, set-soccer-config,
  shrink-sweep, soccer-backtest, sync-kalshi-ncaa (D2), sync-lineups,
  sync-players, sync-stats, team-streaks, totals-calibration,
  totals-model-test, train.
- **D8.** docs/pl_weekly_routine.md "STEP ZERO" (re-extract the tarball)
  has no meaning on the host, which deploys by `git pull` of merged
  main.

Proposed disposition: a separate docs-only CLI.md refresh PR for D1-D6
after the architect reviews this draft (not bundled here).

---

## 9. Open questions (ARCHITECT-RULE)

- **ARCHITECT-RULE H0-1:** provider, plan, and region (EU-cheap Hetzner
  vs US-East DO/Linode/Vultr).
- **ARCHITECT-RULE H0-2:** monthly hosting budget ceiling, including
  off-host backup storage.
- **ARCHITECT-RULE H0-3:** unattended-upgrades automatic reboots allowed,
  and in which window?
- **ARCHITECT-RULE H0-4:** web UI access mode (SSH tunnel as drafted /
  `tailscale serve` with a deliberate guard change / no web UI on host).
- **ARCHITECT-RULE H0-5:** `improve --sport mlb` unattended in the
  morning unit, or operator-started?
- **ARCHITECT-RULE H0-6:** `soccer-refresh` operator-started (drafted) or
  timer-driven with stop-at-rejection?
- **ARCHITECT-RULE H0-7:** Anthony's local time zone for the four CLV
  captures (launchd fired at 08/12/16/20 local) — keep local-anchored via
  `OnCalendar=... <zone>` or re-anchor to UTC / to slate times?
- **ARCHITECT-RULE H0-8:** seasonal enablement — who flips MLB units off
  after the postseason, and NHL on for 2026-10-07; timers carry an
  explicit enabled/disabled calendar in the doc, or manual `systemctl`?
- **ARCHITECT-RULE H0-9:** add `results-tally` to the morning unit (not
  in any CLI.md chain today)?
- **ARCHITECT-RULE H0-10:** midweek PL rounds — separate Tue-Thu timers,
  or operator-started runs of the same units with a date argument?
- **ARCHITECT-RULE H0-11:** schedule NCAA (`sync-kalshi-ncaa` +
  `export-fixtures --competition NCAA`) now, or only after CLI.md
  documents an NCAA chain (D2)?
- **ARCHITECT-RULE H0-12:** exact competition list for the weekly
  full-season sync (per-comp season strings from the DB, not assumed).
- **ARCHITECT-RULE H0-13:** failure-notification channel for
  `sp-notify@` (email, push service, other) — and which secrets it adds.
- **ARCHITECT-RULE H0-14:** backup retention window and whether an
  encrypted off-host copy is required (the DB never travels casually —
  does an automatic off-host backup count as sanctioned travel?).
- **ARCHITECT-RULE H0-15:** the key-table list for migration row-count
  receipts.
- **ARCHITECT-RULE H0-16:** API quota handling during the 7-day parallel
  run (accept 2x / partial host chains / other).
- **ARCHITECT-RULE H0-17:** writer of record during the parallel run
  (drafted: laptop; host exports comparison-only).
- **ARCHITECT-RULE H0-18:** freeze (or amend) the cutover criteria in
  5.5 before day 1.
- **ARCHITECT-RULE H0-19:** receipts handoff — pasted table only, or a
  daily receipts file the Cockpit v0.4 intake reads?
- **ARCHITECT-RULE H0-20:** export delivery host -> Cockpit (pull over
  tailnet as drafted, or a later push spec).
- **ARCHITECT-RULE H0-21:** does H0 wait behind Cockpit v0.4 / K / B in
  the queue (drafted: yes, groundwork only), or is the laptop-uptime
  risk to CLV capture enough to pull hosting forward?
