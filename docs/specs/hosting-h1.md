# Hosting H1: the unit pack and Anthony's provisioning runbook

**Status: H1b LIVE.** The parallel week started 2026-09-28 13:45 UTC: 12
host timers are enabled, `SP_PARALLEL_MODE=full`, and the MLB timers stay
off by ruling. See the H1b day-one record. H1a was CERTIFIED PASS on
2026-09-27. Phase order amended 2026-09-27: H1a fresh bootstrap, then H1b
parallel week, then H2 cutover (the one migration). H0 rulings were made
2026-09-27 (see the table at the end). Design source:
`docs/specs/hosting-h0.md`.

Every step below carries a label:
- **BROWSER** means you click it in a provider or GitHub web UI.
- **TERMINAL (laptop)** means you type it on the Mac.
- **TERMINAL (host)** means you type it on the VPS. Use the provider's web
  console only until P4 is done, then SSH over the tailnet as `sp`.
  **After P4 the console is emergency-only** (field amendment 2026-09-28).
  It is the break-glass path when the tailnet is down, not a working
  terminal.

`<host>` is the droplet's Tailscale MagicDNS name. The runbook assumes
`sp-vps-1`. If MagicDNS names don't resolve on the Mac, use the host's
tailnet IP (100.x) wherever `sp-vps-1` appears. The tailnet-IP door is the
proven standard (2026-09-28).

---

## 0. What ships (deploy/hosting/)

| File | Role |
|---|---|
| `chains.py` | The one place chain commands live. Each step is verbatim from docs/CLI.md and pl_weekly_routine.md, with options made explicit. CI checks every command and every option against cli.py (law 1). |
| `sp_run.py` | Runs a chain under the DB lock. Retries a step that failed TRANSIENTLY (connection errors, timeouts, HTTP 5xx/429 — read from the traceback's terminal line) twice, 15s then 45s, and receipts it as `retried N`. Other 4xx and exceptions in our own code never retry. Stops at the first step still failing (it pages as before), except in the window chain (ARCHITECT 2026-10-16, addendum 84 item 2(b), #555): there a failed `sync-` step is receipted (`continued`) and the chain runs on, a failed card/export step still stops it, the chain's exit is the first failed step's (non-zero, so the notice fires), and the page post runs when only sync steps failed. In every chain a failed `sync-teams` step is receipted (`continued`) and the run goes on, the exit the first failure's (ARCHITECT 2026-11-01, addendum 207 item 4, #765/#728). In every chain, a run with a failed step names `failed_steps` ([{step, command, exit}]) and `stopped_at` (the step that ended the run; null when the only failures were `sync-teams` steps, or, in the window chain, sync steps) in its chain receipt, and its last output lines name each failed step with its command and last output line, so the failure page (the journal's last 30 lines) carries them. Writes a receipt per step and per chain. Enforces the backup rule (daily, or a fresh prerefresh). Pages on `SP-PAGE:` lines. Refuses operator-only chains without `--operator`. Handles `active_from` windows and H0-16(b) designated days. `--dry-run` prints the resolved commands. |
| `sp_backup.py` | SQLite online-backup API (`Connection.backup`, the same mechanism as the CLI's `.backup`). Then integrity_check on the copy, sha256, a `.sha256` sidecar and a receipt. Never `cp`; refuses any target under `data/`. |
| `sp_migrate.py` | The sanctioned move in three steps: `pack` (laptop), `verify`, `install` (host). Manifest per H0-15. |
| `compare_exports.py` | Parallel-week export diff (masks timestamps). |
| `sp_receipts.py` | The paste-ready table (H0-19). |
| `sp_notify.py` | Failure and PASS-hold paging (H0-13): a push to the private ntfy.sh topic `NTFY_TOPIC` from `.env`. The receipt and journal are always written, so a held PASS pages AND logs. Startup validation (2026-09-29): an `NTFY_TOPIC` / `NTFY_CARD_TOPIC` containing whitespace is refused. `sp_run` fails loudly (`kind: config_error`, exit 2) and `deliver` never posts to it (`error: invalid_topic_whitespace`). The topic value is never printed. |
| `sp_boot_receipt.py` | One receipt per boot (H0-3). |
| `sp_prune.py` | Backup retention: 14 dailies (H0-14). Report-only until the first manual prune has been reviewed. |
| `pull_backup.py` + `scripts/setup_backup_pull.sh` | **Laptop side.** Nightly pull of the host's newest daily `.backup` over the tailnet into `~/sp-backups`. Verified against the sha256 sidecar plus an integrity check, and receipted (H0-14 second layer, $0). |
| `pull_exports.py` + `scripts/setup_export_pull.sh` | **Laptop side.** Pulls the host's `exports/` over the tailnet into the laptop's `exports/host/`, never its own `exports/`. Host from `SP_HOST_ADDR`. Newest-wins by mtime, idempotent, all-or-nothing on an unreachable host. Receipted (pulled / unchanged / newest `window_24h.json`). On demand; the hourly launchd job at :10 is optional. |
| `sp_deploy.py` | Fast-forward to merged `origin/main` only, with a receipt. |
| `systemd/` | `sp-chain@.service` template, the timers of the Schedule table below (every one on a T11 list; CI-checked), backup, prune, notify@, boot-receipt, web, and `sp-soccer-refresh.service` (no timer). |
| `etc/` | host.env template, full-season list template, unattended-upgrades reboot window, logrotate. |
| `install.sh` | Copies units and config into place. **Enables nothing.** |
| `bootstrap.py` | H1a: `fingerprint` (read-only counts), `plan`, `run` (the wiring sequence, receipted and resumable), and `compare` (phase-1 acceptance: completed seasons exact plus the BACKLOG anchors). `catch-up --reference fp_host.json [--apply]` (laptop, 2026-09-29): the pre-cutover completeness sweep — sync-teams then sync-matches for every competition-season the laptop counts fewer games than the reference; dry run by default; `--apply` takes the daily backup first, receipts each season before/after (`kind: catch_up`), stops at the first failure. |

Code change riding along (H0-5 hard guard): `improve --hold-on-pass`, also
set by `SP_IMPROVE_HOLD_ON_PASS=1`, which the chain template sets.
- A PASS is marked `held`. Production is untouched.
- An `SP-PAGE:` line pages the operator.
- `python cli.py ratify-candidate --sport mlb --version <v> --yes`
  promotes it, and only if the production version it beat is still
  production (otherwise the verdict is stale and refused).
- Without the flag, laptop behaviour is byte-identical. The gate
  (threshold, holdout, scoring) is unchanged either way.

### Schedule (host TZ = UTC; zoned lines follow their zone's DST)

| Timer | Chain | When | Backup rule |
|---|---|---|---|
| sp-backup | (daily .backup) | daily 09:30 UTC | — |
| sp-availability-daily | availability-daily (ARCHITECT 2026-11-04, addendum 252 item 3(a); 259 item 2(d)): one step, `availability-nflverse --season 2026`, the nflverse depth-chart release file into the availability record (a conditional GET; UNMETERED: github.com, never api-sports); inside no other chain; `go_on`: its failure is receipted and paged as a sync-step failure, stopping nothing; needs `migrate_availability_record.py` run (else it refuses, exit 2, and pages); enabled only by the architect's block (252 item 7) | daily 08:45 UTC | — |
| sp-mlb-morning | mlb-morning (improve HOLDS on PASS; results-tally last) | daily 09:45 UTC | daily |
| sp-soccer-morning-after | soccer-morning-after: after `evaluate --sport soccer`, `export-results --sport soccer --competition PL --days 7` (ARCHITECT 2026-11-08, addendum 294 item D: the seven slate days ending yesterday, each day with a graded game written, yesterday's always; the timer has no Saturday or Wed-Fri run); after every sync the bare `export-soccer-expansion-shadow` (ARCHITECT 2026-10-30, addendum 185 D2: the shadow export closes every soccer sync chain; rows until the next chain's export: its fire + `EXPORT_WINDOW_MARGIN`, 2 h, addendum 188 item 4; each run its own new file), then, LAST, `results-tally --host-export` (addendum 230 item 2(b), 289 item 3: exports/RESULTS.md + exports/results_tally.json, the DB mode=ro, mirrored) | Sun/Mon/Tue 09:50 UTC | daily |
| sp-nfl-grade | nfl-grade | Mon/Tue/Fri 10:00 UTC | daily |
| sp-soccer-friday | soccer-prematch, no longer data only: the syncs (ARCHITECT 2026-10-25, addendum 166 item 6(B): the PL `predict` and the PL window `export-predictions` are retired; the closing watch's slate stage writes `soccer_PL_<start>_to_<end>.json`): the PL `sync-matches` / `sync-odds` / `sync-injuries`, the expansion leagues' `sync-matches` / `sync-odds`, their capture-only `sync-kalshi-soccer`, the PL `sync-kalshi-soccer`; then, last, the bare `export-soccer-expansion-shadow` (ARCHITECT 2026-10-30, addendum 185 D2; reads the DB only, UNMETERED) | Fri 14:00 UTC | — |
| sp-soccer-saturday | soccer-prematch, no longer data only: the syncs (as sp-soccer-friday, ARCHITECT 2026-10-25, addendum 166 item 6(B)), then, last, the host-only bare `export-soccer-expansion-shadow` (addendum 185 D2; R6) | Sat 10:30 Europe/London | — |
| sp-mlb-preslate | mlb-preslate | daily 14:30 UTC | — |
| sp-nfl-lines | nfl-lines | daily 15:00 UTC | — |
| sp-nhl-daily | nhl-daily (inactive before 2026-09-29; override `SP_NHL_ACTIVE_FROM`) | daily 16:00 UTC | daily |
| sp-nba-daily | nba-daily (ARCHITECT 2026-11-05, addendum 261 item 1(b); 271 item 3(d), (h): market-only, no model, no call): `sync-matches --competition NBA --season 2026` as three single-day UTC steps, `{yesterday}`, `{today}` and `{tomorrow}` (ARCHITECT 2026-11-06, addendum 274 item 2(3): "THE WINDOW — THREE UTC DAYS", nhl-daily's own; api_basketball sends a date only when from == to; 274 item 2(9): "6 calls a day"), then `sync-kalshi-nba` (KXNBAGAME, the shared matcher); no coverage step: it runs before intl-daily's 07:20 UTC `coverage --json` (#805, addendum 225 item 5: one writer), so that write reads the fresh NBA rows. Shipped on `TIMERS`; the architect's TERMINAL (host) block enables it (T11, below) | daily 06:47 UTC | daily |
| sp-tennis-daily | tennis-daily (ARCHITECT 2026-11-05, addendum 261 item 2(c); 2026-11-06, addendum 269 items 1-3: market-only, no model, no call; Kalshi's two tour series are the fixture source and the results source): `sync-matches --competition ATP` and `--competition WTA` over the ticker days `{yesterday}` .. `{tomorrow}` (the adapter `kalshi_tennis` reads each series to its last page, 269 item 3(d); the players first, from the same read; no `--season`: the ticker's year; never wider than 7 days, addendum 270 item 5: no backfill), then `sync-kalshi-atp` and `sync-kalshi-wta` (the shared matcher, then the player check); no coverage step: it runs before intl-daily's 07:20 UTC `coverage --json` (addendum 274 item 2(2): one writer). Shipped on `TIMERS`; the architect's TERMINAL (host) block enables it (T11, below) | daily 06:53 UTC | daily |
| sp-ncaa-market | ncaa-market (H0-11: enabled with the rest); from 2026-10-02 `sync-matches` NCAA yesterday + today runs first (#254), plus tomorrow from 2026-10-07 | Tue + Wed 16:00 (midweek FBS games, added 2026-10-07), Thu 16:00 (Thursday-night slates, added 2026-09-28), Fri 16:00, Sat 13:00 UTC | — |
| sp-ncaa-schedule | ncaa-schedule (ARCHITECT 2026-10-09, addendum 19 item 3: "the stored kickoff of every NCAA game in the next seven days is at most one day old"): `sync-matches` NCAA, single-day calls today..today+7, then `refresh-by-id --competition NCAA --days 7` (addendum 21 item 1: every stored SCHEDULED game in those days refreshed by its own id; the listing no longer carries games that have not started); then, last, `export-ncaa-predictions --id ncaa-elo-v2 --dormant-ok` (ARCHITECT 2026-11-03, addendum 230 item 1(b): the college shadow, dormant, exit 0 and nothing written, while the verdict is null or FAIL); the export runs whether or not `refresh-by-id` succeeded (`go_on`, ARCHITECT 2026-11-03, addendum 236 item 3(4): the chain's exit stays the refresh's, so it pages) | daily 10:35 + 22:35 UTC | — |
| sp-nfl-prematch | nfl-prematch (was sp-nfl-predict / nfl-predict; ARCHITECT 2026-10-25, addendum 166 item 6(B): `predict-nfl` and `export-nfl-predictions` are retired, the closing watch's slate stage writes `nfl_predictions_<date>.json`): `sync-injuries` NFL, `capture-weather-nfl` | Thu 18:00, Sun 14:00 UTC | — |
| sp-clv-capture | clv-capture | 08/12/16/20 America/New_York (H0-7 confirmed; DST follows the zone) | — |
| sp-weekly-fullseason | weekly-fullseason (per `SP_FULLSEASON_LIST` line: `sync-teams`, then `sync-matches`, #765, ARCHITECT 2026-11-01, addendum 204 item 3(a); a failed `sync-teams` does not stop the chain: its `sync-matches` and every later line still run, the exit is the first failure's and the summary line names the step, addendum 207 item 4); then, last, `ncaa-cfbd-labels --year 2026` (ARCHITECT 2026-11-03, addendum 240 item 4(b): the host's one CFBD read a week, metered, after the list's syncs because its joins read our stored NCAA fixtures (so that, when the list carries `NCAA|2026`, the week's sync of them runs first; the host list's NCAA line is not verified here); `go_on`: its failure is a sync-step failure that stops nothing after it, receipted, the chain's exit the first failure's, so it pages; needs `CFBD_API_KEY` in host.env, else it refuses with exit 2; it runs only when the list resolves (setting set, file present, a competition listed), the daily backup succeeds and no earlier `sync-matches` fails, else that week's read waits for a hand run or the next Sunday) | Sun 06:00 UTC | daily |
| sp-backup-prune | (retention, report-only) | daily 05:30 UTC | — |
| sp-exports-squash | exports mirror weekly history squash (F2.5; a no-op until `SP_EXPORTS_MIRROR_REMOTE` is set) | Sun 06:10 UTC | — |
| sp-intl-daily | intl-daily (the incremental intl sync, the v3 venue step, the UNL shadow export; then the cups' daily schedule read, `sync-matches` EFL, CL, UEL and FAC 2026/27, #707, ARCHITECT 2026-10-27, each cup's `sync-teams` immediately before it, #728, ARCHITECT 2026-11-01, addendum 204 item 3(b); a cup's failed `sync-teams` does not stop the chain: that cup's `sync-matches` and every later cup still run, the exit is the first failure's and the summary line names the step, addendum 207 item 4; then, LAST, `coverage --json`, #805, ARCHITECT 2026-11-03, addendum 225 item 5: read-only, it writes exports/coverage_<date>.json, which the step's mirror push carries to host/latest/coverage.json; its failure blocks no sync step, since none follows it, and the chain's exit carries it; a failed step that stops the chain before it, a cup's `sync-matches` or an intl step, or a failed daily backup before any step, sp_run then running no step, leaves that day without a host coverage file) | daily 07:20 UTC | daily |
| sp-mlb-history | mlb-history (MLB PHASE A: the api-sports fallback's MLB history; sync only) | daily 10:30 UTC | daily |
| sp-window | window (the next-24h card and delta pages); from the next deploy (ARCHITECT 2026-10-24, addendum 164 item 2(a)) also the capture-only Kalshi sync of PD `KXLALIGAGAME`, SA `KXSERIEAGAME`, BL1 `KXBUNDESLIGAGAME`, FL1 `KXLIGUE1GAME` and ELC `KXEFLCHAMPIONSHIPGAME` (`chains.WINDOW_KALSHI_CAPTURE_ONLY`: one `sync-kalshi-soccer --competition <code>` per league, one series per call, when the league's next kickoff is near or imminent; no export, no call, no venue line on the card) | hourly at :05, hours 00-03 and 06-23 UTC (H0-3) | — |
| sp-cup-observe | (cli.py observe-cup-lineups, one tick, all four cups; not a chain): cups Step B's live T-15 observation store (ARCHITECT 2026-10-27, addendum 169 item 4(i)); a tick with no poll due ends without the DB lock | every 5 minutes at :00..:55, hours 00-03 and 06-23 UTC (H0-3) | — |
| sp-availability-observe | (cli.py availability-nhl-observe, one tick; not a chain): the availability record's NHL landing watch (ARCHITECT 2026-11-04, addendum 252 item 3(b); 2026-11-11, addendum 340 item 3: "a STANDALONE unit on the cup-observe pattern"): the NHL schedule at most hourly per NHL day (no row), the landing page at T-120 .. T-0 and the boxscore at T+20 per game into the record; a poll more than five minutes past its time a `missed` row; a tick with no poll due takes no lock; needs `migrate_availability_record.py` run since #835 item 2's poll key (else it refuses, exit 2, and pages); enabled only by the architect's block (252 item 7; 340 item 3) | every 5 minutes at :00..:55, hours 00-03 and 06-23 UTC (H0-3) | — |
| sp-availability-graph | (cli.py availability-graph-rebuild; not a chain): the availability record's graph projection (ARCHITECT 2026-11-04, addendum 252 item 4; 2026-11-11, addendum 347 item 5: LadybugDB `ladybug` 0.22.3, host-only, requirements-graph.txt): rebuilt whole from the newest daily `.backup` copy in /var/backups/sports-predictor whose `.sha256` sidecar matches (refused when older than 26 h), opened mode=ro + immutable=1, into logs/availability/graph/availability.lbug, one line of rebuild.jsonl beside it per run; its own unit with no EnvironmentFile, PrivateNetwork, ProtectSystem=strict, one writable directory (347 item 5(b)); read by nothing (347 item 5(c)); enabled only by the architect's block | daily 10:20 UTC (after sp-backup 09:30) | — |
| sp-closing-watch | (closing.py watch, NFL and SOCCER; not a chain) — enabled at the cutover, 2026-10-26 13:47Z (T11 `TIMERS`; ARCHITECT 2026-10-26, addendum 168 item 5; held for the cutover ruling until then, C7) | every minute (the one H0-3 exemption, by name) | — |
| *(none)* | soccer-refresh | **operator-started** (H0-6) | fresh prerefresh |

**H0-3 reboot window.** No timer fires between 04:15 and 05:15 UTC. CI
checks this for both DST states. Unattended-upgrades reboots at 04:30, and
every boot writes a receipt.
- **The one exemption, by name (ARCHITECT 2026-10-12, addendum 45 P3):**
  `sp-closing-watch.timer`, every minute of every hour. "H0-3's buffer is
  for chains that write on a schedule. A tick with no start due reads the
  stored schedule and ends, so this one timer is exempt from the buffer by
  name [...] and no start time is ever without a tick." A reboot ends the
  tick that is running; the next tick retries (#408 item 4). Every other
  timer stays outside 04:15-05:15 UTC, CI-checked
  (tests/test_hosting_pack.py `H0_3_EXEMPT`, `test_closing_watch_timer_form`).

**Locking.** Chains serialize on one flock. A timer that fires while another
chain holds the lock waits; it is not skipped.

---

## P. Provision the host

**P1. BROWSER: create the droplet (H0-1, H0-2).**
- DigitalOcean → Create → Droplets.
- Settings: Region **New York** (NYC1 or NYC3); Ubuntu 24.04 LTS x64;
  Basic, Regular, **2 vCPU / 4 GB** (about $24/mo); SSH key authentication
  (upload the Mac's public key); hostname `sp-vps-1`.
- If you prefer Hetzner: a CPX-line plan in Ashburn is the acceptable
  substitute.
- **Backups: ON** (H0-14, weekly, +20%, about $4.80). This is
  droplet-level disaster recovery. With it the total is about $28.80.
- **Receipt:** screenshot the live price at checkout, droplet plus
  backups. It must be at or under **$30/mo all-in** (H0-2).
- **Restoring from a DO droplet backup:** the image carries a live
  `data/sports.db` captured mid-write, so **discard it**.
  - Before enabling any timer on the restored droplet, move
    `data/sports.db` (and any `-wal`/`-shm`) aside.
  - Restore from the newest file in `/var/backups/sports-predictor/`, or
    from the laptop's `~/sp-backups/` copy if that one is newer: build a
    pack from it and run H2 step 4's `verify` / `install --replace`.
  - The `.backup` files are consistent; the live file in an image is not.

**P2. BROWSER: cloud firewall.**
- Networking → Firewalls → Create.
- Inbound rules: **none** (delete the default SSH rule). Outbound: all.
- Apply it to `sp-vps-1`.
- The provider firewall and ufw are two layers, and both deny all inbound.

**P3. TERMINAL (host), via the provider's Droplet Console:**
```
timedatectl set-timezone UTC
apt update && apt -y upgrade
apt -y install git python3-venv python3-pip sqlite3 ufw unattended-upgrades
adduser --disabled-password --gecos "" sp
usermod -aG systemd-journal sp          # sp-notify reads unit journals
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up                              # BROWSER: approve the device in the Tailscale admin console
ufw default deny incoming && ufw default allow outgoing
ufw allow in on tailscale0
ufw enable && ufw status verbose          # receipt: only tailscale0 allowed
```
**Mac VPN clients conflict with Tailscale** (field amendment 2026-09-28).
Before any tailnet step from the laptop (P4 onward, and every later
`ssh sp@sp-vps-1`), quit any other VPN client on the Mac: disconnecting
it is not enough if it keeps its tunnel or DNS hooks. A host that
"stops answering" over the tailnet is checked for this first, before
anything on the host is touched.

**P4. TERMINAL (host): SSH hardening (H0-4).**
**Amended from the field 2026-09-28: `sp` gets working admin access BEFORE
root is sealed.** Otherwise sealing root leaves only the console, which is
emergency-only.
1. Give `sp` NOPASSWD sudo (sp has no password; `--disabled-password` in P3).
   This is the exact form run on the host, 2026-09-28:
   ```
   echo 'sp ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/sp && chmod 440 /etc/sudoers.d/sp && visudo -c
   ```
   Receipt: `parsed OK`.
2. Enable Tailscale SSH:
   ```
   sudo tailscale set --ssh=true             # success is SILENT (no output, exit 0)
   ```
   - **Console paste hazard:** the provider's web console can mangle pasted
     flags. `tailscale up --ssh` was rejected there as "invalid option". Type
     the command by hand, or run it over tailnet SSH once `sp` can sudo.
   - There is no server-side status receipt. `tailscale status --json` has
     no key containing "ssh", so grepping it proves nothing (the earlier
     receipt was dropped 2026-09-28). The proof is client-side: an
     `ssh sp@<tailnet-ip>` from the Mac that Tailscale SSH answers.
   - The tailnet policy's `ssh` rule decides who may connect as `sp`.
   - Under a `check`-mode rule, expect an occasional browser re-auth.
3. Put your Mac's key in `/home/sp/.ssh/authorized_keys` (mode 0600, owned
   by sp). OpenSSH over the tailnet stays as the second path.
4. **Receipt (laptop), BEFORE sealing root:**
   - `ssh sp@<tailnet-ip> 'sudo -n true && echo SUDO_OK'` prints `SUDO_OK`.
   - Use the host's tailnet IP (`tailscale ip -4` on the host). **The
     tailnet-IP door is proven and is the standard** (architect,
     2026-09-28); MagicDNS names are a convenience on top.
   - If it fails, stop here and fix it; do not seal root.
   - **Host status 2026-09-28:**
     - sudo is confirmed (parsed OK, working).
     - Tailscale SSH is **enabled server-side**: `sudo tailscale set
       --ssh=true` ran and returned silently (success).
     - **Client-side verification pending:** the Mac's MagicDNS isn't
       resolving tailnet names. This is a Mac-side issue; retest after a
       reboot. The tailnet-IP door works meanwhile.
5. Seal root: in `/etc/ssh/sshd_config` set `PasswordAuthentication no` and
   `PermitRootLogin no`, then `systemctl reload ssh`.
- Public port 22 is closed at both firewall layers, so SSH is reachable
  over the tailnet only.
- **Receipt (laptop):** `ssh sp@sp-vps-1 hostname` succeeds.
- **Receipt:** `nc -vz <public-ip> 22` from a non-tailnet network fails.

**P5. BROWSER: read-only deploy key.**
- TERMINAL (host) as sp: `ssh-keygen -t ed25519 -f ~/.ssh/sp_deploy -N ""`.
- Paste the `.pub` into GitHub → repo Settings → Deploy keys → Add. Leave
  **Allow write access unchecked.**

**P6. TERMINAL (host): checkout and venv.**
```
install -d -o sp -g sp /opt/sports-predictor
sudo -u sp GIT_SSH_COMMAND="ssh -i ~/.ssh/sp_deploy" \
  git clone git@github.com:anthonyevans29/sports-predictor.git /opt/sports-predictor
sudo -u sp git -C /opt/sports-predictor config core.sshCommand "ssh -i ~/.ssh/sp_deploy"
cd /opt/sports-predictor
sudo -u sp python3 -m venv venv
sudo -u sp venv/bin/pip install -r requirements.txt
sudo -u sp venv/bin/python -m pytest -q     # receipt: "N passed" (throwaway SQLite)
ls data 2>&1                                  # receipt: "No such file or directory"
```
`data/` must not exist before B2 (the bootstrap's `init-db` creates the DB). `import cli` no longer creates it; that was
fixed 2026-09-27. If `data/` does exist, run `rmdir data` (it would be empty).

**P7. TERMINAL (host): install the pack. It enables nothing.**
```
cd /opt/sports-predictor && sudo bash deploy/hosting/install.sh
```
Receipt: the list of `sp-*` unit files, all `disabled`.

---

## Phase order (amended 2026-09-27, operator proposal ratified with a guard)

**H1a: fresh bootstrap.** The host builds its own database from the
providers. No data transfer. Acceptance: the host's syncs reproduce the
certification fingerprints. **CERTIFIED PASS 2026-09-27** (compare
clean, no waivers). Timers remain OFF; the H1b start is a midweek
decision.

**H1b: parallel week.** Two independent pipelines. The laptop remains
writer of record. **STARTED 2026-09-28 13:45 UTC** (day-one record under
H1b).

**H2: cutover.** The ONE `.backup` migration: the laptop's history replaces
the host's rehearsal DB.

---

## H1a. Fresh bootstrap (no data transfer)

**B0. Paging and config (H0-13).**
- BROWSER/phone: install the ntfy app. Pick an unguessable topic name (for
  example `sp-` plus 20 random characters) and subscribe to it.
- TERMINAL (laptop): add `NTFY_TOPIC=<that name>` to the laptop `.env`.
- Copy the `.env` to the host over the tailnet. It is config, not data: the
  API keys, `API_FOOTBALL_RPM` and the topic.
  ```
  scp .env sp@sp-vps-1:/opt/sports-predictor/.env
  ssh sp@sp-vps-1 'chmod 600 /opt/sports-predictor/.env; grep ^DATABASE_URL /opt/sports-predictor/.env'
  ```
  The receipt must read `DATABASE_URL=sqlite:///./data/sports.db`, or show
  no line at all (the default). Fix any absolute laptop path before
  going on.

**B1. TERMINAL (laptop): the reference fingerprint.**
Read-only. Games and teams are counts only, never rows. It also carries the
production `model_versions` rows: the config-only seed ratified in B4.
The printed line names them.
```
python deploy/hosting/bootstrap.py fingerprint --out /tmp/fp_laptop.json
scp /tmp/fp_laptop.json sp@sp-vps-1:/home/sp/
```
It lists every stored (competition, season) pair and its season string,
so the host syncs exactly what the laptop holds. Nothing is assumed
(law 1).

**B2. TERMINAL (host): plan, then run.**
The standard wiring sequence per family:
- `init-db`
- **seed the model registry.** Install the reference's production
  `model_versions` rows (every column) and verify them by hash. These are
  production model identities and parameters, config only (B4). No odds, no
  predictions and no grades travel, so the host's books stay empty. The
  seed refuses a non-empty registry.
- `sync-competitions` per sport
- then, per (competition, season): `sync-teams`, then `sync-matches`
  (about 3 seasons per family, as stored on the laptop)
- then the **market day-one block**: a first `sync-odds` for every
  in-season competition, `sync-odds-football`, and all five Kalshi syncs.

Odds and Kalshi accumulate from day one, bid/ask included (the K1 sync
path).

Bootstrap uses metered calls freely as a **one-time spend**. Daily metered
mode still waits on the H0-16 dashboard receipt (T8).
```
cd /opt/sports-predictor
sudo -u sp venv/bin/python deploy/hosting/bootstrap.py plan --reference /home/sp/fp_laptop.json --skip-family MLB   # receipt: the step list
sudo systemd-run --unit=sp-bootstrap --uid=sp --working-directory=/opt/sports-predictor \
  /opt/sports-predictor/venv/bin/python deploy/hosting/bootstrap.py run --reference /home/sp/fp_laptop.json --skip-family MLB
journalctl -fu sp-bootstrap
```
- **`--skip-family MLB` is required on a DigitalOcean host.**
  statsapi.mlb.com returns 406 to the DO ASN (see the H1b notes).
  - MLB's `sync-teams` and `sync-matches` steps are receipted as
    `SKIPPED-ASN`.
  - Step numbers never change. The first bootstrap stopped at step 8 (MLB
    `sync-matches`), so it resumes with the same number:
    ```
    cd /opt/sports-predictor && sudo -u sp git pull --ff-only origin main
    sudo systemd-run --unit=sp-bootstrap-resume --uid=sp --working-directory=/opt/sports-predictor \
      /opt/sports-predictor/venv/bin/python deploy/hosting/bootstrap.py run \
      --reference /home/sp/fp_laptop.json --from 8 --skip-family MLB
    journalctl -fu sp-bootstrap-resume
    ```
  - The MLB market steps (`sync-odds --competition MLB` via api-sports,
    and `sync-kalshi`) still run. With no MLB games on the host they
    match nothing. They are harmless.
- `run` refuses if `data/sports.db` already exists (this is for a FRESH
  host).
- A failed step stops the run and prints the exact
  `--from N` resume line.
- Every step is receipted.

**B3. Phase-1 acceptance: the host reproduces the fingerprints.**
TERMINAL (host):
```
sudo -u sp venv/bin/python deploy/hosting/bootstrap.py fingerprint --out /home/sp/fp_host.json
sudo -u sp venv/bin/python deploy/hosting/bootstrap.py compare /home/sp/fp_laptop.json /home/sp/fp_host.json --skip-family MLB
```
**Waivers (ruling 2026-09-27).** An explained provider difference on a
completed season is waived with `--waive COMP:SEASON:reason`.
- The row still prints, with both counts, marked `~ … WAIVED: <reason>`.
- The waiver is recorded in the compare receipt, with `applied` true or
  false. A waiver on a matching row prints `waiver unused`.
- **Version guard (architect finding, 2026-09-27).** Both fingerprints
  must come from the same `bootstrap.py`. Every fingerprint embeds the
  producing file's git blob SHA, and `compare` REFUSES a mismatch, or an
  unstamped fingerprint, before comparing any row.
  - First H1a run: UEL 2024/25 read host 202 vs laptop 269, while sqlite
    held 269 on BOTH machines. That was fingerprint version skew (a
    pre-#42 laptop fingerprint against a post-#42 host one), not data.
  - So: pull `main` on both machines, regenerate BOTH fingerprints
    (laptop B1, host B3), then re-compare.
  - UEL 2024/25: **NO WAIVER** (architect ruling). The host's sqlite holds
    269, the same as the laptop.
  - **Waiver policy:** `--waive` stays, for real provider drift only. It is
    never used to paper over an instrument bug. Only a delta that survives
    a same-version compare and one host re-sync is a waiver candidate.
  - **Before ANY compare:** the laptop regenerates its fingerprint on
    current `main` (B1). The host does the same (B3).
  - **Receipt for a competition-season delta** (request 2026-09-27: UEL
    2024/25 still read host 202 vs laptop 269 on pinned fingerprints,
    while host sqlite counted 269). Run on BOTH machines, on the same
    `main`:
    ```
    python deploy/hosting/bootstrap.py explain --comp UEL --season 2024/25 --out /tmp/ex_<machine>.json
    ```
    It prints:
    - (a) the fingerprint's exact counting SQL;
    - the rows counted four ways: the predicate, raw by `competition_id`,
      by season-string variant, and by status / `status_raw` / stage;
    - (b) every row the fingerprint does NOT count, with status,
      `status_raw`, stage and `external_ids`.

    Copy one dump to the other machine (tailnet scp), then:
    `python deploy/hosting/bootstrap.py explain-diff /tmp/ex_laptop.json /tmp/ex_host.json`
    - (c) This joins the rows on `external_ids` and prints every stored
      field that differs.
  - **Fingerprint hardening in the same change:**
    - The predicate groups by the match's own `competition_id` with a LEFT
      JOIN, so an orphan row counts as `?#<id>` and is never dropped.
    - The fingerprint self-checks its grouped total against a raw
      `COUNT(*) FROM matches`, and refuses on a mismatch.
    - `compare` sums duplicate status entries instead of overwriting them.
- NFL: the Pro Bowl rows (AFC v NFC, +1 game per season, 34 teams) are
  now excluded at the adapter, and each exclusion prints a receipt. The
  scope_line SCOPE ALERT (teams != 32) was the protection that would have
  flagged them in any NFL model path.
  - Rows the host ingested BEFORE this fix remain; a re-sync updates in
    place and never deletes.
  - Removing them is a **targeted delete, AUTHORIZED** (architect ruling
    2026-09-27). The host DB is a rehearsal database by design, replaced
    wholesale at cutover, so this is not destruction of truth. The laptop
    is untouched; it never had these rows.
  - TERMINAL (host), dry-run first, then apply:
    ```
    cd /opt/sports-predictor && sudo -u sp git pull --ff-only origin main
    sudo -u sp venv/bin/python deploy/hosting/remove_allstar_rows.py            # prints every row it would remove
    sudo -u sp venv/bin/python deploy/hosting/remove_allstar_rows.py --apply    # backup -> delete -> post-counts
    ```
  - The script uses the adapter's own exhibition rule to find the AFC/NFC
    team rows and their games. It cascades through the DECLARED foreign
    keys (predictions, outcomes, odds, snapshots…), deleting children
    first, in one transaction under the DB lock.
  - `--apply` first takes a `_precleanup_` `.backup`. That is an event
    backup: never counted as a daily, kept 30 days.
  - It refuses to run without the host marker, so it cannot run on the
    laptop.
  - **Receipt:** the printed rows, plus pre/post counts. Expect -1 game
    per NFL season that had a Pro Bowl (e.g. 335 -> 334) and NFL teams
    34 -> 32. Paste them, then regenerate the host fingerprint and
    re-compare.
  - **If teams still read 34:**
    - The script's DEFAULT is a dry-run. Only `--apply` deletes.
    - Check the host receipts log:
      `grep '"kind": "cleanup"' /var/log/sports-predictor/receipts.jsonl`.
      No line means the script never ran (did the host pull `main`?).
      `"applied": false` means dry-run only, so re-issue with `--apply`.
    - The dry-run also prints the NFL teams with the fewest games. If it
      reports `all-star teams: none` while NFL has more than 32 teams, the
      provider's names differ from the AFC/NFC rule. Paste those names; no
      guess is made.

A skipped family prints as `N/A-host` (laptop-only). It is neither checked
nor counted as a failure. The model-identity check still covers MLB's
seeded production row: the seed is local and needs no statsapi call.
PASS requires all three of the following:
1. Every **completed** (competition, season) equals the laptop exactly, on
   total games and on FINISHED games.
2. **Model identity matches**: the same production version per (sport,
   family), with an identical parameters hash.
3. The **BACKLOG certification anchors** hold:

| Anchor | Source | Requirement |
|---|---|---|
| NHL 2024 = 1,502 FINISHED + 1 CANCELLED | round-3 certification, 2026-09-24 | exact |
| NHL 2025 = 1,498 FINISHED | round-3 certification | exact |
| NHL 3 seasons = 4,410 games | backfill, 2026-09-23 | at least; live season grows |
| NHL franchises = 32 | same | at least |
| NCAA 3 seasons = 9,245 games | first-audit certification, 2026-09-25 | at least |
| NCAA programs = 743 | same | at least |
| NFL 3 seasons = 989 games | phase 1b, 2026-09-05 | at least |
| NFL teams = 32 | same | at least |
| Soccer FINISHED pot = 16,546 (24 competitions) | v22 promotion, 2026-09-21 | at least |
| MLB | no fingerprint on record | N/A-host (laptop duty, ASN block); where a host can reach statsapi, completed seasons equal the laptop exactly |

- Current seasons print as informational; both sides move.
- Ties and partials are FAIL. Re-sync the named (competition, season) with
  `sync-matches --competition C --season S`, which updates in place, and
  re-compare.
- A residual mismatch needs a named cause (a provider correction, or
  pagination) and a BACKLOG entry before H1b starts.
- Paste the compare output. **That is the H1a acceptance.**

**B4. The model registry seed (RATIFIED 2026-09-27).**
- A fresh DB has no `model_versions` rows.
  - `predict` for MLB and soccer would raise "No production model yet"
    (`training._resolve_model_version`).
  - `improve --hold-on-pass` would HOLD and page on a default-config
    candidate every morning.
- Ruling: the production rows are seeded in B2, as a config-only seed.
  - The model registry is code-adjacent configuration, not history.
  - Without it, the parallel week cannot compare the very thing cutover
    certifies: MLB and soccer prediction parity.
  - The H2 migration stays necessary: the books (odds, predictions,
    grades) are not seeded.
- NFL is code-defined (`nfl_elo_v1`) and rebuilds from synced games either
  way.
- On the host, the next candidate version number follows the seeded
  production row, not the laptop's full history. Candidates are held on the
  host, never promoted, and the host DB is replaced at H2, so the numbering
  gap is harmless.
- All four model-bearing timers are enabled with the rest (T11).
- **AMENDED (ARCHITECT 2026-10-10, addendum 36 item 3; finding #410):** "The production soccer row's ratings and team_to_league are keyed by the team ids of the database that trained them. They are that database's state, not configuration, and a seeded copy is valid only where the team ids are the same. On the host they are not. Nothing is re-keyed there: the cutover replaces that database with the laptop's. Until then the host's soccer model rows are evidence of nothing, I name them in the compare as a class of their own, and no page built from them is a call."
  - The seed copied the laptop's rows, every column, into a database whose teams the host's own bootstrap had created under other ids; on the host 16 of 20 PL slots read the default 1500.0 and 4 another league's club (#410). The "config only" premise above holds for the poisson configuration, not for `elo.*.ratings` and `team_to_league`.
  - The cutover runbook (h2-cutover-runbook.md, section 1 step 4) checks the installed database's PL export against the laptop's last file before the writer flag flips.
  - **ENFORCED (ARCHITECT 2026-10-17, addendum 109 item 3; #410):** "when the writer-of-record role is host, every soccer model_edge row is PASS, pass_kind "host_fence" [...] The fence lifts with the cutover (the ruling that cuts over names it). No re-keying on the host (addendum 36 stands)." Built in `src/walters/desk_policy.py`: the role is the machine's `SP_EXPORTS_MIRROR_ROLE`, read from host.env first (a run typed by hand on the host is fenced too), then the environment, then the checkout's `.env`. Addendum 110 item 1 (RULED): "ONE FLIP (law 4, conservative unknowns): an unknown or missing role is FENCED, not open." Only an exact `laptop` leaves a row as it is; `host`, unset and any other value fence. The row's model numbers and `rating_source` stay in the file. The fence reads the switch `HOST_FENCE_RULE`, never `SP_WRITER_OF_RECORD`, and the cutover PR turns it off in the flip's change (addendum 114 item 3).

---

## Window service: `sp-window` (architect spec 2026-09-27; enabled on H1b day 1)

This hourly chain reprices the next 24 hours across every competition in
the DB and writes `exports/window_24h.json`, the consolidated card.
- The card uses the fixtures grammar, plus model p, book fair, Kalshi,
  edge, tier, quarantine, venue flag and engine.
- The Cockpit renders it in the **Next 24h** tab.
- `sp-window.timer` ships with the pack and is on the T11 enable list, so
  it starts with H1b day 1.
- It fires at :05 every hour except 04 and 05 UTC (H0-3 reboot window).

**Proximity tiers** (ruling 2026-09-27). Each competition's steps scale
with the time to its next kickoff inside the window:

| Tier | Next kickoff | What runs |
|---|---|---|
| far | more than 6h away | schedule check only (`sync-matches`: status and postponement); no odds |
| near | 2–6h away | the schedule check, plus odds (`--limit` = its games within 6h) and Kalshi |
| imminent | under 2h away | the same repricing, plus T-90 freshen detection. For the model families (NFL, soccer; never MLB) it also runs `sync-injuries --kickoff-within-hours 2` BEFORE the card, so the T-90 signature has fresh injuries to compare (ruling 2026-09-29). |

A competition with no game inside 24h contributes zero steps. The chain
receipt carries `proximity`: the competitions per tier and the steps
skipped by proximity (flat plan minus tiered plan).

**What each run does**, with steps planned at run time from the DB,
read-only:
1. `sync-matches --competition C --season S --date-from D --date-to D`,
   ONE UTC day per call, for every competition with non-finished games in
   the window. The hockey and american-football adapters honour a date
   window only when from == to; a range silently fetches the whole league.
2. `sync-odds --competition C --season S --limit <window game count>` per
   competition (`sync_odds` prices the next N scheduled games). The
   american-football family (NFL + NCAA) gets one `sync-odds-football`.
   Then the Kalshi sync for each competition in `WINDOW_KALSHI` (CI-pinned
   to the adapter's series). Bid/ask are stored by the K1 path. Then the
   capture-only Kalshi sync of each soccer-expansion league in
   `WINDOW_KALSHI_CAPTURE_ONLY` (PD, SA, BL1, FL1, ELC; ARCHITECT
   2026-10-24, addendum 164 item 2(a)), tiered the same way (near and
   imminent only), one series per step: captured for the record (the
   three-way close), no export, no call.
3. **No model runs.** `window-card` copies model p, tier and quarantine
   from the canonical chain-slot exports (joined on `match_id`) and
   reprices only the market side: book fair, Kalshi, venue gap and
   STALE-BOOK? (venue.py), and edge vs the book fair.
4. Writes the card atomically.
5. `sp_window_page` pages **card deltas** to the SECOND private topic
   `NTFY_CARD_TOPIC`:
   - Delta classes: new game priced / tier change / quarantine flip /
     STALE-BOOK? change / kickoff moved (or postponed) / T-90 news /
     line move (a row turned `late-news?`: ≥ 6pp net move on the book
     consensus or Kalshi inside T-3h, from stored snapshots; ruling
     2026-09-29). A capture-only league's move (PD, SA, BL1, FL1, ELC:
     `chains.WINDOW_KALSHI_CAPTURE_ONLY`, not in `WINDOW_KALSHI`) never
     pages and never requests a freshen (ARCHITECT 2026-10-24, addendum 165
     item 1: "A logged move is a receipt; a paged one is a false alarm"):
     it is one line in the window's log, `· capture-only line move
     (addendum 165 item 1): <competition> <series> <ticker> <from>-><to>
     (<move>pp) · <minutes> min to kickoff · venue <kalshi|book>`, and is
     listed in the `window_page` receipt's `capture_only_moves`.
   - One daily digest on the first run at or after 08:00 ET.
   - Quiet hours are 00:00–07:00 ET. Only the QUARANTINE-CLASS deltas page
     then, at high priority: quarantine flips, and line moves (ruling
     2026-09-29: early European kickoffs put T-3h inside quiet hours). The
     rest are receipted as suppressed.
   - The first run only records a baseline; it pages nothing.

**Receipts:**
- The chain line carries a `quota` block: metered / unmetered steps run and
  skipped. Provider call counts are `null`: not instrumented, never 0.
- The pager appends `kind: window_page` with the delta counts per class,
  suppressed count, paged/digest flags and `freshen_needed`.

**Host settings:**
- `SP_SKIP_FAMILIES=MLB` in host.env on a DO host. This drops MLB's
  `sync-matches` only (statsapi ASN block).
- `NTFY_CARD_TOPIC=<second unguessable topic>` in `.env`. Subscribe to it
  in the ntfy app separately from `NTFY_TOPIC`.
- Test the pager: `sudo -u sp venv/bin/python deploy/hosting/sp_window_page.py`.

**Freshen chains** (ruling 2026-09-27). These are the documented operator
sequences, defined in `chains.py` as `freshen:<family>`:
- `freshen:NFL`: `sync-injuries` NFL → `sync-odds-football` →
  `sync-kalshi-nfl` → `predict-nfl` → `export-nfl-predictions --out
  logs/<run id>.nfl_predictions_<date>.json`. #673 (ARCHITECT 2026-10-25,
  addendum 167 postscript (b), verbatim): "a file that carries Desk blocks is
  never replaced by one without them. The freshen writes to its own name (the
  alternative), and the slate's kept copy and receipt stay true; `--desk` is
  not added to the freshen (the closing page is the row that counts, the
  freshen is an input refresh)." The file is outside `exports/` (never the
  slate's `exports/nfl_predictions_<date>.json`, never mirrored); the freshen
  receipt names it (`wrote` {file, sha256}), and a path that already exists
  is refused, never written into.
- `freshen:MLB`: the documented 10-command pre-game chain. It is a laptop
  duty: on a host with `SP_SKIP_FAMILIES=MLB` it is logged as
  `freshen_needed` and never run.
- `freshen:SOCCER`: `sync-odds` PL → `sync-injuries` PL →
  `sync-kalshi-soccer` → `predict` soccer PL → `export-predictions` soccer
  PL (the 36h current slate, scheduled — export windowing 2026-09-28).
- Market-only families (NCAA, NHL, cups, UNL) have no freshen. The
  window repricing is their freshen.

On `freshen_needed` (T-90 news, or a line-move alarm), the window service
triggers the family's freshen:
- under the chain lock, receipted as `kind: freshen`;
- the `freshen` receipt names its `reasons` (`t90_news` / `line_move`);
- rate-guarded to at most one per family per hour, with state in
  `freshen_state.json` beside the receipts log;
- then it rebuilds the card.

A freshen re-writes that slot's prediction exactly as the laptop's T-60
freshens do today; the ledger's idempotent re-log absorbs it.

**Rulings:**
- The baseline-first pager is RATIFIED: no "everything is new" storm.
- Null provider-call counts are ACCEPTED. api-football exposes no quota
  headers, so the metered/unmetered step count is the honest accounting.
- The card's `engine` is `model_edge` or `market_only`. The venue-edge
  charter stays in Cockpit policy v1.1, and the Next 24h tab calls the
  same `venueEdge()`, so there is one copy of the policy.

## H1b. Parallel week (two independent pipelines)

**Day one: 2026-09-28 13:45 UTC** (architect record). The parallel-week
clock started here; the frozen cutover criteria (H0-18) count from this
moment.
- **Timers:** the 12 `TIMERS` of T11 were enabled on day one (sp-mlb-history
  joined the list 2026-09-29, MLB PHASE A): backup, backup-prune,
  soccer friday/saturday/morning-after, nfl lines/grade/predict,
  nhl-daily, weekly-fullseason, ncaa-market and window. The T11 list now
  holds 13.
- **MLB:** the `MLB_LAPTOP_ONLY` timers are OFF by ruling (statsapi 406 on
  the DO ASN).
- **Quota:** `SP_PARALLEL_MODE=full` (T8 option a).
- **Criterion 1** reads "7/7 days with every host timer firing on
  schedule". So the earliest possible cutover decision is after
  2026-10-05 13:45 UTC. A tie or partial pass extends the run; it is not
  a cutover.

**Parallel-week exhibits** (each divergence is classed as it lands; see
criterion 3):
- **Exhibit 1: 2026-09-28, host `nfl-predict` manual run.**
  - Result: a 1-row file under the 36h default. Scope was clean.
  - The Elo ratings pool had 588 games on the host versus 601 on the
    laptop. The gap is Sunday's results, which were not yet synced on the
    host.
  - Class: **capture timing**, an expected divergence (architect).
  - Mechanics: `sp-nfl-grade` fires Mon/Tue/Fri 10:00 UTC, but the timers
    were enabled at 13:45 UTC Monday, after that day's slot. A newly
    enabled timer has no stamp for `Persistent=true` to catch up. The
    host's first `nfl-grade` is therefore **Tue 2026-09-29 10:00 UTC**,
    which syncs Sunday + Monday results.
  - Expect the pools to converge after that run. Re-check the pool counts
    on the next exhibit.
  - **Divergence log (architect ruling, 2026-09-28):**

    | Divergence | Class | Explanation |
    |---|---|---|
    | Row count 17 (laptop) vs 1 (host) | **code-version skew** | The laptop file was produced pre-#53 (8-day window) and the host file post-#53 (36h window). |
    | `fair_prob`, `market_divergence_pp`, `venue_gap_pp` | **capture timing** | The two sides synced at 13:52 UTC and 18:19 UTC respectively. |
    | Injury inputs 280 (laptop) vs 0 (host) | **chain gap** (not an explained class) | Host `nfl-predict` lacked `sync-injuries`. FIXED: it is now step 1, and a CI guard audits every prediction chain. |
    | Model probabilities | identical | Neither team played Sunday, so the Elo inputs agree. |

  - The skew class above was ruled on the architect's receipts: exhibit 1's
    files predate the `git_sha` stamp. From the next pull, the class is
    claimable only through the comparator's guard, which requires both
    files to carry `git_sha` and the comparator to name the mismatch.
  - **CLOSED 2026-09-28 (architect).** The host `nfl-predict` was re-run at
    21:50 UTC, after the #58 pull:
    - injuries 6/5, equal to the laptop (the chain gap is fixed);
    - `git_sha` stamped;
    - model probabilities identical;
    - venues converged to 0.0pp at T-45 (the capture timing resolved as
      the syncs aligned).
    Nothing remains open.

- Both machines sync independently and both run their chains.
- The export diffs compare INDEPENDENT pipelines. Explained divergence
  classes are **capture timing** AND **provider-pagination differences**.
- The laptop remains writer of record (H0-17).
- The frozen cutover criteria are unchanged.

**H1b note: MLB is a LAPTOP duty (ruling 2026-09-27).**
- FINDING, attributed to the architect: bootstrap step 8 failed because
  statsapi.mlb.com returns **406** to the host for both the default and a
  browser User-Agent (curl receipts).
  - MLB blocks the DigitalOcean ASN outright; the laptop is unaffected.
  - The free MLB Stats API is datacenter-hostile.
  - The five commercial providers (api-sports x4, Kalshi) are unaffected.
- RULING:
  - MLB syncing remains a laptop duty for now.
  - The host MLB timers (`sp-mlb-morning`, `sp-mlb-preslate`,
    `sp-clv-capture`) stay OFF the enable list (T11).
  - Candidate fixes for after cutover (a Tailscale exit node via the Mac,
    or a residential egress) are H2-era decisions, deliberately deferred.

**MLB PHASE A: the host's MLB history from api-sports (ruling 2026-09-29).**
- GATE MET: score parity 100.0% on finished pairs (2476/2476, 2426/2426,
  the laptop probe). The host GRADES and KEEPS MLB history from api-sports
  Baseball; the laptop keeps statsapi; MLB predictions stay a laptop duty
  (PHASE B negative: no pitcher/bullpen/umpire/lineup endpoints).
- ENGAGEMENT: `sync-matches` / `sync-teams --competition MLB` route to
  `src/ingestion/mlb_apisports.py` whenever `SP_SKIP_FAMILIES` names MLB
  (host.env, already `MLB` on the DO host). No flag, no laptop change.
- Chain `mlb-history` (timer 10:30 UTC daily, backup first): sync-competitions
  `--sport mlb` (static list, no provider call), then `sync-matches` MLB
  2026 (teams, then the season's /games in ONE call). No predict, evaluate
  or improve step.
- STAGE: rows the fallback creates carry stage NULL. The provider's `week`
  labels the Wild Card round and the World Series both "Final", so it is
  never read into stage; a row paired to a statsapi row keeps that stage.
- KNOWN LIMITATION, receipted every run: doubleheader game 2 is absent
  from api-sports /games (13 games across 2025-2026). Never fabricated;
  where one of our rows exists for one it is marked
  `external_ids.api_baseball_note = "apisports-unavailable"`; the laptop's
  statsapi remains the record.
- The window service is unchanged: it still drops MLB `sync-matches`
  (SP_SKIP_FAMILIES) and keeps the already-ruled MLB odds/Kalshi steps,
  which become live now that the host has MLB rows. freshen:MLB stays
  logged-never-run.
- RULED (2026-09-29, on #73): the stage NULL is ratified; the three-status
  map stands (the probe saw only FT / CANC / NS across 4,916 rows); MLB
  market-only card rows on the host are accepted (the venue-edge charter
  excludes model sports).
- COMPARE (ruling (4)): the doubleheader game-2 rows are a provider-difference
  class, WAIVED with a receipt. Once the host holds MLB history, compare
  WITHOUT `--skip-family MLB` and with the waiver (the current season prints
  informationally and needs none):
```
python3 deploy/hosting/bootstrap.py compare fp_laptop.json fp_host.json \
  --waive "MLB:2025:apisports doubleheader gap"
```
  The waived row still prints both counts: the laptop-minus-host
  difference must equal that season's doubleheader game-2 count, and
  nothing more.
- ONE-TIME on a live host (receipts: the `MLB-FALLBACK-RECEIPT` lines):
```
sudo -u sp venv/bin/python deploy/hosting/sp_backup.py daily
sudo -u sp venv/bin/python cli.py sync-competitions --sport mlb
sudo -u sp venv/bin/python cli.py sync-matches --competition MLB --season 2025
sudo -u sp venv/bin/python cli.py sync-matches --competition MLB --season 2026
sudo systemctl enable --now sp-mlb-history.timer && echo sp-mlb-history.timer | sudo tee -a /etc/sports-predictor/timers.enabled
```

**T8. TERMINAL (host): H0-16 quota mode.**
- **BROWSER first:** open the api-sports dashboard and screenshot the
  quota headroom. This is the receipt.
- If the screenshot shows room for 2x traffic for 7 days (option a): in
  `/etc/sports-predictor/host.env` set `SP_PARALLEL_MODE=full`.
- Otherwise (option b): leave `SP_PARALLEL_MODE=designated` and set
  `SP_DESIGNATED_DAYS=Fri,Sat,Mon`. That covers a PL weekend and NFL
  Monday grading. On other days, metered steps are skipped and receipted.
  Kalshi and grading/export steps always run.
- Never option (c).
- As shipped, `designated` with no days is the conservative default:
  every metered step is skipped until you choose.

**T9. TERMINAL (host): the full-season competition list (H0-12).**
Generate it from the DB (read-only); never type it from memory. The command writes the list to a temp file, prints
it, then installs it over the list (owner root, group sp, mode 0640, as `install.sh` installs the example). It runs
in a subshell whose EXIT trap removes the temp file, so the block's exit status is the failing step's when the query,
the print or the install fails (the list then stays as it was), and 0 only when the list was installed:
```
( t=$(mktemp) && trap 'rm -f "$t"' EXIT && sqlite3 -readonly /opt/sports-predictor/data/sports.db \
 "SELECT c.code || '|' || m.season FROM matches m JOIN competitions c ON c.id = m.competition_id
  WHERE m.utc_date BETWEEN datetime('now','-30 days') AND datetime('now','+30 days') AND c.code NOT LIKE 'MLB%'
  GROUP BY c.code, m.season ORDER BY c.code;" > "$t" \
 && cat "$t" && sudo install -o root -g sp -m 0640 "$t" /etc/sports-predictor/fullseason.list )
```
Paste the list as the receipt. Delete any line you do not want synced
weekly. If the list is missing or empty, the chain fails loudly.
**Install over the list, never append (#593; ARCHITECT 2026-10-18, addendum 128 item 4: "the docs fix as proposed
(write to a temp file, print, install over the list)"):** until #593 this step ended `| sudo tee -a`, which kept the
installed example's comment lines and, on a second run, wrote every line again, so the chain would sync each
competition twice. The install replaces the file, the example's comment header with it (nothing reads it).
**T9 runs once (ARCHITECT 2026-10-18, addendum 128 item 4, verbatim):** "OPERATOR: block_1018_t9_host.txt is NEVER
re-run; today's one run wrote the 26 lines once, and a second run would double them and the chain would sync each
competition twice. If the list ever needs regenerating, I write a fresh block that installs over the file."
**MLB is left out (ARCHITECT 2026-10-18, addendum 122 item 3(a)):** the query's `AND c.code NOT LIKE 'MLB%'`
drops every MLB code (`MLB`, `MLB_SPRING`). "MLB is excluded by ruling: MLB is a laptop
duty to the season's last game; a host api-sports whole-season MLB write beside the laptop's statsapi rows is
#569's twin-row shape." T9 is a pre-cutover item, binding (h2-cutover-runbook.md section 0, block
`block_1018_t9_host.txt`); `cutover-readiness` reads the list (#586), and an MLB line on it binds: NOT-YET, with
the line named (ARCHITECT 2026-10-18, addendum 128 item 1(b)).

**T10. TERMINAL (host): dry-run receipts.**
Resolved commands only; nothing executes:
```
for c in mlb-morning mlb-preslate soccer-prematch nfl-grade nhl-daily weekly-fullseason; do
  sudo -u sp venv/bin/python deploy/hosting/sp_run.py $c --dry-run; done
```

**T10b. TERMINAL (host): page test (H0-13).**
```
sudo -u sp venv/bin/python deploy/hosting/sp_notify.py page "H1 page test"
```
Receipt: the push arrives on the phone, and the printed line says
`delivered=True`.

**T11. TERMINAL (host): enable.**
```
TIMERS="sp-backup.timer sp-backup-prune.timer sp-soccer-friday.timer sp-soccer-saturday.timer
  sp-soccer-morning-after.timer sp-nfl-lines.timer sp-nfl-grade.timer sp-nfl-prematch.timer
  sp-nhl-daily.timer sp-weekly-fullseason.timer sp-ncaa-market.timer sp-window.timer
  sp-mlb-history.timer sp-intl-daily.timer sp-exports-squash.timer sp-ncaa-schedule.timer
  sp-closing-watch.timer sp-cup-observe.timer sp-availability-daily.timer sp-nba-daily.timer
  sp-availability-observe.timer"
MLB_LAPTOP_ONLY="sp-mlb-morning.timer sp-mlb-preslate.timer sp-clv-capture.timer"   # NOT enabled: statsapi 406 on the DO ASN (H1b note)
TIMERS_BY_BLOCK="sp-availability-graph.timer sp-tennis-daily.timer"   # NOT enabled by T11: each by the architect's own block once its prerequisite is met (addendum 351 item 2)
echo $TIMERS | sudo tee /etc/sports-predictor/timers.enabled   # the list H2 steps 2 and 6 reuse
systemctl enable --now sp-boot-receipt.service sp-web.service
systemctl enable --now $TIMERS
systemctl list-timers 'sp-*' --no-pager     # receipt: next-elapse for each
```
- Every shipped timer is on exactly one of `TIMERS`, `MLB_LAPTOP_ONLY` and `TIMERS_BY_BLOCK`; CI checks it.
- **`TIMERS_BY_BLOCK`** (ARCHITECT 2026-11-12 10:50 ET, addendum 351 item 2, verbatim in part): "shipped, never
  enabled by T11's fresh-host line, enabled only by the architect's own block once its named prerequisite is met
  (today: sp-availability-graph.timer — the engine installed and its directory made; sp-tennis-daily.timer — 288
  item 5). T11's `systemctl enable --now` line and its timers.enabled write take `TIMERS` alone". Each timer on it
  keeps its own recipe below, which ends with its `timers.enabled` line; sp_deploy's receipt counts the list's timers
  not enabled as it counts `MLB_LAPTOP_ONLY`'s (held off by T11). The list replaces the ORDER note that kept
  `sp-availability-graph.timer` out of T11's enable by hand.
- **`sp-availability-daily.timer` on a fresh host: an ORDER** (259 item 2(c): "2025 IS IN SCOPE"). After
  `migrate_availability_record.py` and BEFORE the `systemctl enable --now $TIMERS` above, run the 2025 read
  (`sudo -u sp venv/bin/python cli.py availability-nflverse --season 2025`) and go on only on exit 0 with its rows
  asserted; otherwise leave `sp-availability-daily.timer` out of that enable (and of `timers.enabled`) until it has.
  The record's watermark is the source's: a first 2026 read loses the 2025 history to this feed for good.
- **The file's form (#725; ARCHITECT 2026-10-28, addendum 174 item 4: "hosting-h1's T11 recipes must not assume one
  timer name per line in timers.enabled (the file holds several per line)").** `timers.enabled` is a list of names
  separated by whitespace, not one per line: the `echo $TIMERS` above writes the whole list on ONE line, and each
  live-host recipe below appends one more line (`echo <name> | sudo tee -a`). Every reader takes it by name:
  `$(cat /etc/sports-predictor/timers.enabled)`, `sp_cutover` and `sp_deploy` (`.split()`). A recipe that counts,
  finds or removes a timer goes by name too, never by line (`wc -l`, or `grep -x` / `sed '/^name$/d'` on the file
  as written, miss every name on the TIMERS line). The names, one per line, as a receipt: `tr -s ' \t' '\n' < /etc/sports-predictor/timers.enabled | sed
  '/^$/d' | sort`. **A timer retired or renamed on a live host** (e.g. `sp-nfl-predict.timer` to
  `sp-nfl-prematch.timer`, #674) leaves the list by name, rewritten in place under sudo, after its `systemctl disable
  --now`. The new list replaces the file only when every stage of the read succeeded and the new list is not empty
  (`pipefail` in a subshell, then `[ -s ]`): a failed read leaves the file as it was, never an empty list:
  ```
  f=/etc/sports-predictor/timers.enabled; old=sp-nfl-predict.timer
  [ -s "$f" ] && ( set -o pipefail; tr -s ' \t' '\n' < "$f" | sed '/^$/d' | grep -vxF "$old" | tr '\n' ' ' | sed 's/ $/\n/' | sudo tee "$f.new" >/dev/null ) && [ -s "$f.new" ] && sudo mv "$f.new" "$f"
  tr -s ' \t' '\n' < "$f" | sed '/^$/d' | grep -cxF "$old"   # receipt: 0
  ```
- `sp-closing-watch.timer` is on `TIMERS` from the cutover (ARCHITECT 2026-10-26, addendum 168 item 5:
  "hosting-h1.md's T11 HELD_FOR_CUTOVER list: sp-closing-watch.timer moves to TIMERS (CI's check follows)"). Until
  then it was the one name on a third list, `HELD_FOR_CUTOVER` (ARCHITECT 2026-10-12, addendum 45 P3: "A third
  list in the T11 test names the units that are shipped and held for the cutover ruling"; C7: the cutover ruling
  decides when it runs). The host enabled it at h2-cutover-runbook.md section 1 step 5b, 2026-10-26 13:47Z
  (timers.enabled 17 names), and the third list is retired. install.sh still copies the unit and enables nothing.
- `TIMERS` includes the soccer model-bearing timers (B4, seeded registry)
  and `sp-ncaa-market.timer` (H0-11).
- The MLB timers stay off. They are shipped and CI-validated, ready for
  whichever H2-era egress decision is made.
- `sp-mlb-history.timer` (MLB PHASE A, 2026-09-29) is ON: it syncs MLB
  history only, from the api-sports fallback. On a live host that
  predates it, see "MLB PHASE A" below.
- No timer exists for soccer-refresh (H0-6).
- **The prediction timers, retired (ARCHITECT 2026-10-25, addendum 166 item 6(B), applying addendum 126 item 2(d)).**
  The host's fixed-time NFL and PL predict and slate-export steps are gone: the closing watch's slate stage writes
  the slate files (`nfl_predictions_<date>.json`, `soccer_PL_<start>_to_<end>.json`). The data syncs stay on their
  schedules: `sp-nfl-predict.timer` is renamed `sp-nfl-prematch.timer` (chain `nfl-prematch`: the NFL injury sync and
  the weather capture), and `sp-soccer-friday.timer` / `sp-soccer-saturday.timer` run `soccer-prematch`'s syncs,
  and since ARCHITECT 2026-10-30, addendum 185 D2, the host-only bare `export-soccer-expansion-shadow` as its last
  step (no longer data only: a shadow file, no prediction, no call).
  On a live host the unit change is the architect's TERMINAL (host) block, in the PR that ships it.
- `sp-intl-daily.timer` (2026-10-02, 07:20 UTC): the incremental intl sync,
  the v3 venue step and the UNL shadow export (intl-elo-v2's confirmation
  window); then the cups' daily schedule reads (#707, #728) and, last, `coverage --json` (#805, ARCHITECT
  2026-11-03, addendum 225 item 5: the host's writer of exports/coverage_<date>.json; no new timer). On a live host that predates it (the recipe ends with the timers.enabled line, ARCHITECT
  2026-10-26, addendum 168 item 2: a timer enabled by hand and never listed is one the cutover's pause leaves
  running):
  ```
  sudo install -m 0644 deploy/hosting/systemd/sp-intl-daily.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now sp-intl-daily.timer
  echo sp-intl-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled
  systemctl list-timers sp-intl-daily.timer --no-pager   # receipt: next elapse at 07:20 UTC
  ```
- `sp-ncaa-schedule.timer` (ARCHITECT 2026-10-09, addendum 19 item 3; daily 10:35 + 22:35 UTC): the
  NCAA forward-week kickoff sync. The provider files an unannounced kickoff at 04:00Z and announces it
  days later; without this the host refreshed a game's kickoff only once it was inside ncaa-market's
  yesterday..tomorrow or the window's 24 hours. The chain is the eight single-day listing reads, then
  `refresh-by-id --competition NCAA --days 7` (ARCHITECT 2026-10-09, addendum 21 item 1): the provider's
  listing no longer carries games that have not started, so every stored SCHEDULED game in those days
  is refreshed by its own id (one `GET /games?id=` each; a NOT FOUND is listed and untouched). Its
  receipt (kind `refresh_by_id`) lands in the receipts log beside the step receipts. On a live host that
  predates it, after the deploy of the tag that carries it:
  ```
  sudo install -m 0644 deploy/hosting/systemd/sp-ncaa-schedule.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now sp-ncaa-schedule.timer
  echo sp-ncaa-schedule.timer | sudo tee -a /etc/sports-predictor/timers.enabled
  systemctl list-timers sp-ncaa-schedule.timer --no-pager   # receipt: next elapse at 10:35 or 22:35 UTC
  sudo -u sp venv/bin/python deploy/hosting/sp_run.py ncaa-schedule   # first run now, receipted
  ```
- `sp-cup-observe.timer` (ARCHITECT 2026-10-27, addendum 169 item 4(i); every 5 minutes, hours 00-03 and 06-23 UTC):
  cups Step B's live store, one `observe-cup-lineups` tick for all four cups, no `--loop`. A tick with no poll due
  reads and ends without the DB lock. A refusal (no DB file, the store not migrated, no API-Football key) fails the
  unit, which pages through `sp-notify@cup-observe`. On a live host that predates it, after the deploy of the tag that
  carries it (until then the operator runs the loop by hand on cup days):
  ```
  sudo install -m 0644 deploy/hosting/systemd/sp-cup-observe.service deploy/hosting/systemd/sp-cup-observe.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo -u sp venv/bin/python cli.py observe-cup-lineups --dry-run   # receipt: the fixtures within 3 h and the polls due
  sudo systemctl enable --now sp-cup-observe.timer
  echo sp-cup-observe.timer | sudo tee -a /etc/sports-predictor/timers.enabled
  systemctl list-timers sp-cup-observe.timer --no-pager   # receipt: next elapse on a five-minute mark
  journalctl -u sp-cup-observe -n 20 --no-pager           # receipt: the first tick's line
  ```
- `sp-availability-daily.timer` (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(a); 259 item 2(d); daily 08:45
  UTC): the availability record's daily nflverse read, chain `availability-daily`, one step `availability-nflverse
  --season 2026`. Its ENABLEMENT IS THE ARCHITECT'S BLOCK (252 item 7: "the first host reads and the timers' enablement
  are my blocks"), as every timer before it on a live host: shipped on `TIMERS` (so the deploy receipt names it until
  it is enabled), installed and enabled only by this recipe, run in that block, after the deploy of the migration tag
  that carries `migrate_availability_record.py` (without it the step refuses, exit 2, and pages). The first run's
  receipt is the first host read; the first fetch of the 2026 file writes its whole history (every load before the fetch
  BACKFILLED, 259 item 2(c)). **The 2025 read is REQUIRED and FIRST** (259 item 2(c), verbatim: "2025 IS IN SCOPE:
  the adapter ingests depth_charts_2025.csv and depth_charts_2026.csv alike"). The watermark is the source's, so once
  any 2026 load is asserted the 2025 file can never be asserted by this feed (the adapter then refuses it, naming both
  instants, rather than reading `complete`). The block below stops at the first line unless it exits 0; the receipt
  to check is its `rows asserted` (above 0: the 2025 history; 0 with "byte-identical" only on a rerun of this
  recipe). Nothing after it runs on a non-zero exit (1: a failed read, retry later; 2: a refusal, read its reason):
  ```
  sudo -u sp venv/bin/python cli.py availability-nflverse --season 2025; rc=$?; echo "exit $rc"   # REQUIRED, FIRST
  [ "$rc" = 0 ] && sudo install -m 0644 deploy/hosting/systemd/sp-availability-daily.timer /etc/systemd/system/ \
    && sudo systemctl daemon-reload \
    && sudo systemctl enable --now sp-availability-daily.timer \
    && echo sp-availability-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled \
    && systemctl list-timers sp-availability-daily.timer --no-pager   # receipt: next elapse at 08:45 UTC
  [ "$rc" = 0 ] && sudo -u sp venv/bin/python deploy/hosting/sp_run.py availability-daily   # first 2026 run, receipted
  ```
- `sp-availability-observe.timer` (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(b); 2026-11-11 11:40 ET,
  addendum 340 item 3; every 5 minutes, hours 00-03 and 06-23 UTC): the availability record's NHL landing watch, one
  `availability-nhl-observe` tick (its own `sp-availability-observe.service`, not a chain; OnFailure pages through
  `sp-notify@availability-observe`). A poll scheduled inside the 04:00-05:59Z buffer is written as a `missed` row by
  the first tick after it (340 item 3). Its ENABLEMENT IS THE ARCHITECT'S BLOCK (252 item 7; 340 item 3: "shipped
  disabled, enabled by my block"), after the deploy of the tag that carries it and after `migrate_availability_record.py`
  has run on that tag (#835 item 2's poll key: without it a tick refuses, exit 2, and pages). Until then sp_deploy's
  receipt names it as a `TIMERS` timer not enabled. The commands the block runs, as Code names them (addendum 198 item
  6(i): the block itself is the architect's): install `sp-availability-observe.service` and `sp-availability-observe.timer`
  under /etc/systemd/system/, `systemctl daemon-reload`, `cli.py availability-nhl-observe --dry-run` as `sp` (its
  receipt: the window's games and the polls due), `systemctl enable --now sp-availability-observe.timer`, then
  `echo sp-availability-observe.timer | sudo tee -a /etc/sports-predictor/timers.enabled` (addendum 168 item 2), then
  `systemctl list-timers sp-availability-observe.timer` (next
  elapse on a five-minute mark) and `journalctl -u sp-availability-observe` (the first tick's line).
- `sp-availability-graph.timer` (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4; 2026-11-11 19:50 ET, addendum 347
  item 5; daily 10:20 UTC, after the 09:30 sp-backup whose copy it reads): the availability record's graph projection,
  `availability-graph-rebuild --backup-dir /var/backups/sports-predictor --out
  /opt/sports-predictor/logs/availability/graph/availability.lbug` (its own `sp-availability-graph.service`, not a chain;
  OnFailure pages through `sp-notify@availability-graph`). The unit carries 347 item 5(b): no EnvironmentFile, `PrivateNetwork=yes`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, the graph's directory the one writable path; because the sp user can still read what it owns, /etc/sports-predictor (host.env and an exports-mirror deploy key installed there) and data/ are inaccessible and the checkout's .env (config.py loads it on import) is /dev/null; `PrivateUsers=yes`, `ProtectProc=invisible` and `ProcSubset=pid` so another sp process's /proc/<pid>/environ and /proc/<pid>/root (its own unmasked view) are refused; `RestrictAddressFamilies=none` (PrivateNetwork leaves filesystem sockets reachable); `PrivateDevices=yes` and `PrivateIPC=yes` (no shared /dev/shm); /tmp and /var/tmp empty and read-only. The engine is HOST-ONLY (347 item
  5(a)): `requirements-graph.txt`, never requirements.txt; the laptop and CI do not install it. Its ENABLEMENT IS THE
  ARCHITECT'S BLOCK (347 item 6(D): "the unit ships disabled, enabled by my block"), after the deploy of the tag that
  carries it; it is on T11's `TIMERS_BY_BLOCK` (351 item 2), so until then sp_deploy's receipt counts it there, held off by
  T11. The commands the block runs, as
  Code names them (addendum 198 item 6(i): the block itself is the architect's): as `sp`, `venv/bin/pip install
  --require-hashes --only-binary :all: --no-deps -r requirements-graph.txt` (its line: `Successfully installed
  ladybug-0.22.3`; the wheel `ladybug-0.22.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`, the hash in the
  file) and `mkdir -p logs/availability/graph` (the unit's one writable directory, made at install and never by the
  rebuild); install `sp-availability-graph.service` and `sp-availability-graph.timer` under /etc/systemd/system/,
  `systemctl daemon-reload`, `systemctl start sp-availability-graph.service` (the first run, in the unit's own sandbox;
  its receipt: `journalctl -u sp-availability-graph` and the last line of logs/availability/graph/rebuild.jsonl),
  `systemctl enable --now sp-availability-graph.timer`, then
  `echo sp-availability-graph.timer | sudo tee -a /etc/sports-predictor/timers.enabled` (addendum 168 item 2), then
  `systemctl list-timers sp-availability-graph.timer` (next elapse at 10:20 UTC). The graph file is deletable without loss (252 item 4): the next run rebuilds it whole.
- `sp-nba-daily.timer` (ARCHITECT 2026-11-05, addendum 261 item 1(b): "the chain `nba-daily` [...] at a UTC minute
  off every existing timer (Code lists the timers and picks; my block enables it)"; daily 06:47 UTC): the NBA's
  market-only daily, three single-day `sync-matches` steps (`{yesterday}`, `{today}`, `{tomorrow}`, UTC; addendum
  274 item 2(3)) and `sync-kalshi-nba`. 06:47
  is off every chain timer's minute and off the five-minute marks of sp-window and sp-cup-observe (sp-closing-watch
  ticks every minute, its exemption by name), outside H0-3's buffer, and before intl-daily's 07:20 coverage write.
  On Sundays sp-weekly-fullseason (06:00) may still hold the lock at 06:47; the chain then waits (Locking, above).
  Enabling it is the architect's TERMINAL (host) block, after the deploy of the tag that carries it; until then
  sp_deploy's receipt names it as a `TIMERS` timer not enabled. The block's shape (the recipe ends with the
  timers.enabled line, addendum 168 item 2):
  ```
  sudo install -m 0644 deploy/hosting/systemd/sp-nba-daily.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now sp-nba-daily.timer
  echo sp-nba-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled
  systemctl list-timers sp-nba-daily.timer --no-pager   # receipt: next elapse at 06:47 UTC
  ```
- `sp-tennis-daily.timer` (ARCHITECT 2026-11-05, addendum 261 item 2(c): "the chain tennis-daily"; 2026-11-06,
  addendum 269 items 1-3; daily 06:53 UTC): the tennis market-only daily, `sync-matches` for ATP and WTA over the
  ticker days `{yesterday}` .. `{tomorrow}` and `sync-kalshi-atp`, `sync-kalshi-wta`. 06:53 is off every chain
  timer's minute and off the five-minute marks of sp-window and sp-cup-observe (sp-closing-watch ticks every minute,
  its exemption by name), outside H0-3's buffer, after nba-daily (06:47; the lock waits if it still runs) and before
  intl-daily's 07:20 coverage write. Enabling it is the architect's TERMINAL (host) block, after the deploy of the tag
  that carries it (the roadmap's 12-28 step: "the chain's timer enabled by the architect's block"); it is on T11's
  `TIMERS_BY_BLOCK` (351 item 2), so until then sp_deploy's receipt counts it there, held off by T11. The block's
  shape (the recipe ends with the
  timers.enabled line, addendum 168 item 2):
  ```
  sudo install -m 0644 deploy/hosting/systemd/sp-tennis-daily.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now sp-tennis-daily.timer
  echo sp-tennis-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled
  systemctl list-timers sp-tennis-daily.timer --no-pager   # receipt: next elapse at 06:53 UTC
  ```
- **A CHANGED timer on a live host** (e.g. `sp-ncaa-market.timer` gained Tue + Wed 16:00 UTC, ARCHITECT
  2026-10-07, addendum 2 item 8a). `sp_deploy.py` checks out the tag but does not install unit files, so
  after the deploy of the tag that carries the change:
  ```
  sudo install -m 0644 deploy/hosting/systemd/sp-ncaa-market.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl restart sp-ncaa-market.timer
  systemctl list-timers sp-ncaa-market.timer --no-pager   # receipt: next elapse on the next Tue/Wed/Thu 16:00 UTC
  ```
  Until that tag is deployed, a midweek slate gets its host fixtures file only by hand:
  `sudo -u sp venv/bin/python deploy/hosting/sp_run.py ncaa-market`.

**T12. TERMINAL (laptop): the nightly backup pull (H0-14 second layer).**
```
bash scripts/setup_backup_pull.sh sp-vps-1
venv/bin/python deploy/hosting/pull_backup.py --host sp-vps-1   # receipt: ✓ pull ... sha256=...
```
- Runs at 22:00 local via launchd, catching up on wake.
- Copies land in `~/sp-backups` (the laptop's own backed-up disk), never
  in `data/`. They are not pruned automatically.

**T12b. TERMINAL (laptop): the host-exports pull (pull-exports lane, 2026-09-28).**
**Laptop pulls host artifacts; push is H2.**
- Set `SP_HOST_ADDR` in the laptop's `.env` to the host's tailnet address.
  See `.env.example`; the address is never hardcoded.
- Pull on demand (first-class):
  ```
  venv/bin/python deploy/hosting/pull_exports.py
  ```
  Receipt: `✓ pull-exports from <host>: pulled N · unchanged M · newest window_24h.json <exported_at>`.
- Optional: an hourly launchd job at :10, five minutes after the host's :05
  window run:
  ```
  bash scripts/setup_export_pull.sh
  ```
- Copies land in `exports/host/`, a SEPARATE folder. The laptop's own
  `exports/` stays the writer of record (H0-17) and is never touched.
- The Cockpit's Next 24h tab can load `exports/host/window_24h.json`
  directly (no Cockpit change).
- An unreachable host is not an error to chase. The run prints a clear `✗`
  line, exits non-zero and places nothing; the previous pull stays as it
  was.

**Each parallel-week morning:**
- TERMINAL (host): `sudo -u sp venv/bin/python deploy/hosting/sp_receipts.py --since 24h`,
  then paste the table (H0-19).
- Exports (H0-20, pull over the tailnet). TERMINAL (laptop):
  ```
  venv/bin/python deploy/hosting/pull_exports.py
  python deploy/hosting/compare_exports.py exports exports/host   # --since 3 by default (2026-10-01)
  ```
  - Paste the result.
  - Each `✗` needs one of the explained classes:
    - **capture timing:** the two pipelines synced at different moments;
    - **provider pagination:** a different page/list boundary from the
      provider;
    - **code-version skew (guarded, exhibit 1 ruling):** only when both files
      carry `git_sha` and the comparator prints
      `code-version skew: laptop <sha> ≠ host <sha>`. A missing SHA prints
      `NOT claimable`.
  - The comparator keys game rows on (kickoff, home, away), never
    `match_id`, which is machine-local. It prints rows present on one side
    only BY NAME, and compares fields only between matched rows.
  - Otherwise the divergence needs a BACKLOG entry.
  - **Machine state (#592 RULED, ARCHITECT 2026-10-18, addendum 128 item 3):** the day's coverage file
    (kind coverage: `coverage_<date>.json`, and `coverage.json` in latest/) is never compared and never a
    divergence: the comparator lists it by presence on one line, `machine-state files: coverage laptop
    yes|no / host yes|no`, and it is never counted toward or against criterion (a).
- Only **laptop** exports go to the Cockpit this week (H0-17). Host
  exports are comparison-only.

---

## H2. Cutover: the ONE `.backup` migration

**Operator runbook (H2-PREP):** [`h2-cutover-runbook.md`](h2-cutover-runbook.md) covers `sp_cutover.py`, the scratch dry run, the fresh-fingerprint compare with waivers W1 and W2, and rollback. The cutover itself remains an architect ruling.

**Why it cannot be skipped.** The host's bootstrapped DB holds only what
providers still serve today. These are non-resyncable, and exist only on
the laptop:
- the point-in-time odds and Kalshi snapshots (the CLV and closing-line
  record);
- every prediction row;
- the graded ledger (prediction outcomes);
- the model registry's full history: every candidate, rejection and
  shelved version. The B4 seed carries production identities only.

A fresh host keeps no books. So at cutover the laptop's history
**replaces** the host's rehearsal DB. The rehearsal DB is disposed of as
drafted, and the host's parallel-week snapshots go with it. The laptop's
own captures cover that week.

### Cutover criteria (FROZEN, H0-18, approved as drafted 2026-09-27; criterion 3 amended 2026-09-27 before day 1)

- 7/7 days with every host timer firing on schedule (the receipts log shows
  each expected unit line).
- Zero unexplained host-side failures; any `OnFailure` notification was
  received and triaged the same day.
- Export diffs clean on the last 3 days (differences only from capture
  timing or explained provider pagination, each explained).

  **AMENDMENT (architect, 2026-09-27).** Criterion 3 was re-worded before
  the parallel run began. It is law-3 compliant: the freeze binds at day 1,
  which has not started. The previous text read "(differences only from
  capture timing, each explained)". The new text follows the H1b
  independent-pipeline design, whose explained divergence classes are
  capture timing and provider pagination. No other criterion changed.
- A test restore performed on the host: pick one daily host backup,
  `integrity_check` = ok, sha256 matches its receipt.
- Anthony has pulled at least one export from the host via the tailnet and
  loaded it in the Cockpit.
- Ties/partial passes are rejections: extend the parallel run, do not cut
  over.

Test restore (the fourth criterion). TERMINAL (host):
```
f=$(ls /var/backups/sports-predictor/sports_*.db | grep -v prerefresh | tail -1)
sqlite3 -readonly "$f" "PRAGMA integrity_check;"; sha256sum "$f"; cat "$f.sha256"
```

**Cutover morning, before any chain.** The manifest is H0-15: the
`.backup` DB, `.env`, `exports/` and the receipts log.
1. TERMINAL (laptop):
   - Uninstall the CLV jobs: `bash scripts/setup_clv_capture.sh --uninstall`.
   - Uninstall the closing watch: `bash scripts/setup_closing_watch.sh --uninstall`; the step's receipt shows it
     gone (#443 RULED, addendum 41 item 5; h2-cutover-runbook.md section 1 step 1).
   - Run no chains.
   - Run any pending `migrate_*.py` named in the merge notes (after that
     morning's backup), so the laptop DB is on current schema.
2. TERMINAL (host): `systemctl stop $(cat /etc/sports-predictor/timers.enabled)`.
3. TERMINAL (laptop), from the repo root with the venv active:
   ```
   python deploy/hosting/sp_migrate.py pack --out /tmp/sp_pack_$(date -u +%Y%m%dT%H%M)
   scp -r /tmp/sp_pack_<stamp> sp@sp-vps-1:/home/sp/          # tailnet only; no bucket/email/chat
   ```
   - **Receipt S1/R1:** the db sha256, integrity=ok, and row counts for
     **every** table.
   - `absent:` labels any manifest item that did not exist.
4. TERMINAL (host):
   ```
   cd /opt/sports-predictor
   sudo -u sp venv/bin/python deploy/hosting/sp_migrate.py verify  --pack /home/sp/sp_pack_<stamp>
   sudo -u sp venv/bin/python deploy/hosting/sp_migrate.py install --pack /home/sp/sp_pack_<stamp> --replace
   sudo -u sp venv/bin/python cli.py status
   ```
   - **Receipt S2/R2:** `✓ PASS verify` and `✓ PASS install`. S2 = S1,
     and every table's R2 = R1.
   - `--replace` moves the rehearsal DB aside as `data/rehearsal_<ts>.db`.
     Delete it after the receipts.
   - Any `✗` means: delete the pack and repeat from step 3.
   - **PL PREDICTION CHECK (ARCHITECT 2026-10-10, addendum 36 item 3; #410), before step 5 and before the
     writer flag flips in step 6:** "the host exports the PL predictions from the installed database, and the
     file equals the laptop's last file from that database, number for number." The commands and the PASS
     rule are h2-cutover-runbook.md section 1 step 4: the reference is written for the check on the laptop
     immediately before the pack, with `--start` / `--end` (#422); the host's file goes to a fresh directory;
     `compare_exports.py --ignore-keys desk,desk_meta,line_move,late_news_flag,exported_at --require-predictions` (#420,
     #422; the timestamp mask off; `exported_at` confirmed, addendum 41 item 4); CLEAN with at least one row with a prediction and its probabilities on each side. Not PASS: the
     cutover ends for that day, the host stays paused (timers stopped, flag `laptop`, nothing resumed or
     restored) until the architect has read the check.
5. Delete the pack on both machines (`rm -rf`). It holds a DB copy and
   `.env`. Only after the PL check (it reads the laptop's file that `install` copied from the pack).
6. TERMINAL (host), in order:
   - Set `SP_WRITER_OF_RECORD=host` in host.env (ARCHITECT-RULE 2026-10-01; `sp_cutover.py flip`
     does it), then the same in the laptop's `.env`. `SP_PARALLEL_MODE` stays the quota mode.
   - Run `systemctl start $(cat /etc/sports-predictor/timers.enabled)`.
   - Run `systemctl start sp-backup.service` and paste its receipt.
7. The laptop keeps its last `.backup` file cold for 30 days (the rollback
   point). **MLB after the flip (ARCHITECT 2026-10-12, addendum 45 item 4, RULED):** "MLB stays a laptop duty to
   the season's last game. After the flip the laptop's database is written by the MLB chains, the MLB capture
   jobs and the MLB watch, and by nothing else, and it is the record for MLB predictions and for nothing else.
   How MLB reaches the host is decided before Opening Day 2027; it no longer holds the cutover." The steps are
   h2-cutover-runbook.md section 1 step 7: once the host's closing-watch timer is enabled and its first tick has
   been read, the laptop reinstalls the CLV capture jobs (MLB only) and the closing watch with `--family MLB`;
   with no MLB game left in the season, nothing is reinstalled. The 2027 decision is Issue #97. CORRECTED
   (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 4(e), verbatim): "THE LAPTOP DB'S SCOPE: hosting-h1.md's "written by the MLB chains ... and by nothing else" (addendum 45 item 4) is corrected: the laptop's DB is written by the architect's morning block and nothing else — the MLB routine, the NCAA sync, the tennis daily step, and from this ruling NHL's three single-day syncs."

**Rollback** uses the same protocol in reverse:
1. Stop the host timers.
2. Host: `sp_migrate.py pack`.
3. Transfer the pack to the laptop over the tailnet.
4. Laptop: `verify`, then `install --replace`.
5. Reinstall launchd (the CLV jobs and the closing watch, addendum 41 item 5).

---

## O. Operations after cutover

- **Host packages (ARCHITECT 2026-11-09 19:00 ET, addendum 316 item 3, the standing policy, verbatim):** "host
  packages — security updates automatic via unattended-upgrades (installed, enabled, release + -security origins, ~~no
  automatic reboot — as read 11-09 22:07Z~~ [corrected in place by addendum 322 item 1: an automatic reboot at 04:30
  UTC when a security upgrade asks, H0-3 as shipped]); the full `apt-get upgrade --with-new-pkgs` monthly on a compare-pass
  morning, or sooner when a kernel, libsqlite3, python3 or tailscale update is listed, ALWAYS by the architect's block:
  a .backup first; no chain or backup timer due within 45 minutes; the upgrade detached under systemd-run (tailscaled's
  restart can drop the session) with confold and NEEDRESTART_MODE=a, logged to /var/log/sp-apt-upgrade.log; a reboot
  only when /var/run/reboot-required exists and the window still clears; the post-check (kernel, ~~19 sp timers active~~ [corrected in place by
  addendum 323 item 1: the sp timer SETS compared by name, expected = timers.enabled minus THE HELD LIST, observed =
  the active sp timers, passing only when `missing:` and `stray:` are both empty],
  held timers still disabled, tailscale up, the venv importing, `cli.py roadmap` exit 0, a read-only quick_check of the
  live DB)."
  - **The steps, in that order:**
    1. A `.backup` first, its integrity checked.
    2. Confirm that no chain or backup timer is due within 45 minutes.
    3. Run the upgrade detached under `systemd-run`, with confold and `NEEDRESTART_MODE=a`, logged to
       `/var/log/sp-apt-upgrade.log`. A dropped SSH session is expected when tailscaled restarts; the job runs on.
    4. Reboot only if `/var/run/reboot-required` exists and the window still clears.
    5. Run the post-check as quoted above. Its timer line is the set comparison below, never a count.
  - **The timer check (ARCHITECT 2026-11-10 13:35 ET, addendum 323 item 1, verbatim):** "the post-check and the
    runbook's step compare SETS by name: expected = the names in /etc/sports-predictor/timers.enabled minus THE HELD
    LIST (a list the runbook carries with each hold's addendum and its lifting condition; today: sp-ncaa-market.timer —
    310 item 2, until v1.6.6's #902 apply; sp-tennis-daily.timer — 288 item 5, until the tag that carries the map and
    the architect's block); observed = `systemctl
    list-units --type=timer --state=active` filtered to sp-; the check prints `missing: <names>` and `stray: <names>`
    and passes only when both are empty, with the counts beside them as information. The held list is also what the
    deploy's receipt reads when it reports timers not in timers.enabled. 316 item 3's "19 sp timers active" is
    corrected in place to this, with this addendum quoted". Why: T11 names 21 timers, and a fixed count also passes a host that is missing one
    expected timer and running one stray one (Codex on #914, confirmed).
    TERMINAL (host), in bash, as any user (it reads, it changes nothing). `HELD` copies THE HELD LIST below, by name:
    ```
    f=/etc/sports-predictor/timers.enabled
    HELD="sp-tennis-daily.timer"   # THE HELD LIST below, by name
    expected=$(tr -s ' \t\r' '\n' < "$f" | sed '/^$/d' | grep -vxF -f <(printf '%s\n' $HELD) | sort -u)
    observed=$(systemctl list-units --type=timer --state=active --no-legend --plain 'sp-*.timer' | awk '{print $1}' | sort -u)
    missing=$(comm -23 <(printf '%s\n' "$expected") <(printf '%s\n' "$observed") | sed '/^$/d')
    stray=$(comm -13 <(printf '%s\n' "$expected") <(printf '%s\n' "$observed") | sed '/^$/d')
    echo "missing:" $missing; echo "stray:" $stray
    echo "expected $(printf '%s\n' "$expected" | sed '/^$/d' | wc -l), observed $(printf '%s\n' "$observed" | sed '/^$/d' | wc -l) (information)"
    if [ ! -s "$f" ] || [ -z "$expected" ]; then echo "TIMERS: FAIL (timers.enabled unreadable, empty, or every name held)"
    elif [ -z "$missing" ] && [ -z "$stray" ]; then echo "TIMERS: PASS"; else echo "TIMERS: FAIL"; fi
    heldon=""; for t in $HELD; do st=$(systemctl show -p UnitFileState --value "$t" 2>&1) || st=unreadable
      echo "held $t: ${st:-no unit file} / $(systemctl is-active "$t" 2>&1)"
      case "$st" in disabled|masked|masked-runtime|"") ;; *) heldon="$heldon $t";; esac; done
    [ -z "$heldon" ] && echo "HELD: PASS (every held timer disabled)" || echo "HELD: FAIL (not disabled:$heldon)"
    ```
    - `timers.enabled` is read by name, never by line (T11, "The file's form").
    - `TIMERS:` is 323 item 1's verdict: the sets only. A held timer that is running shows under `stray:`.
    - `HELD:` is the post-check's separate "held timers still disabled" item: a held timer whose unit file is
      enabled fails it even while it is not running (it would start at the next boot). Disabled, masked, or no unit
      file (a held timer never installed) passes; a state systemctl cannot read fails. The `held` lines print each
      held timer's unit-file state and active state as the receipt.
    - An unreadable or empty `timers.enabled` fails, never passes on two empty sets (law 4).
  - **THE HELD LIST (addendum 323 item 1).** Each hold enters and leaves this list with its addendum. The recipe's
    `HELD` line copies it, by name:

    | Timer | Held by | Lifts when |
    |---|---|---|
    | `sp-tennis-daily.timer` | ARCHITECT 2026-11-08, addendum 288 item 5 | the tag that carries the map, and the architect's block |

    - **Lifted: `sp-ncaa-market.timer`** (held by addendum 310 item 2 on 2026-11-09, incident #902). The hold's lifting
      condition (ARCHITECT 2026-11-10, addendum 324 item 3(e), verbatim): "`systemctl enable --now
      sp-ncaa-market.timer` — the hold lifts only after (d)'s apply is read clean; the held list in the runbook loses
      that entry with this addendum quoted; sp-tennis-daily stays disabled (288 item 5's block is a separate ruling
      after the laptop's daily step has run a week)." The lift (ARCHITECT 2026-11-10 16:10 ET, addendum 329 item 3,
      verbatim): "THE HOLD LIFTS (324 item 3(e)): my block enables sp-ncaa-market.timer now (next run Wednesday
      16:00Z), prints the set comparison with the held list reduced to sp-tennis-daily, and posts the note on #902."
      The host's #902 apply was read clean at 20:57Z on 2026-11-10 (329 items 1 and 2).

    - **A hold on a sync path (ARCHITECT 2026-11-10 15:35 ET, addendum 325 item 1, verbatim, the architect's
      record):** "a hold on a sync path names EVERY chain that carries the step (grep chains.py for the step), never
      one timer." The 11-09 hold disabled `sp-ncaa-market.timer` only. Two other chains also ran
      `sync-matches --competition NCAA` and were not held: ncaa-schedule (`sp-ncaa-schedule.timer`) and the window
      chain (`sp-window.timer`). Both ran under v1.6.5's any-season lookup from 11-09 until the v1.6.6 deploy on 11-10.
      v1.6.6 closes them with the season-scoped key, so no entry is added for them (325 item 1(c)). CORRECTION
      (ARCHITECT 2026-11-10 18:55 ET, addendum 332 item 3, verbatim): "THREE paths beyond ncaa-market carry the step
      (ncaa-schedule, window, weekly-fullseason), not two; TWO of them ran in the 11-09 → 11-10 gap (weekly-fullseason
      fires Sundays 06:00Z and did not), and 327 item 1's exposure read — zero NCAA rows changed since 11-09 13:49Z —
      covers every path that ran."
      - **Lifting a hold (ARCHITECT 2026-11-10 16:20 ET, addendum 330 item 2, as qualified by ARCHITECT 2026-11-10
        18:55 ET, addendum 332 item 2, verbatim):** "lifting a hold on a Persistent timer THAT HAS FIRED BEFORE runs
        its missed firing at once — lift it when that run is welcome, off the :00–:10 minutes, and read the run; a
        timer that has never fired has no stamp and first runs at its next scheduled firing". CORRECTED (ARCHITECT
        2026-11-10 19:35 ET, addendum 333 item 2(b), verbatim): "the stamp: systemd writes it at a timer's first
        START, not its first firing, so the precise rule is "a timer that has never been started has no stamp";
        332 item 2's sentence is corrected to that wording in the follow-up PR, its conclusion for sp-tennis-daily
        unchanged (never started)." So the sentence reads: a timer that has never been started has no stamp and
        first runs at its next scheduled firing. A timer started once and stopped before its first firing has a
        stamp and catches up on lift, as the first clause's case does (the sub-bullet below). And (332 item 2(b),
        verbatim): "a first enable that wants an immediate run starts the service explicitly (`systemctl start
        sp-chain@<chain>.service`) and says so in its block; sp-tennis-daily's block (288 item 5, when it comes) does
        NOT: its first run is its next 06:53Z firing, read the morning after — the laptop's daily step covers the days
        before." This corrects 330 item 2's "the next instance: its block says so" (Codex on #918, #920).
        - Of the 24 timers the pack ships (read on this branch), 22 carry `Persistent=true`;
          `sp-closing-watch.timer` and `sp-cup-observe.timer` carry `Persistent=false`. Read the unit under
          `deploy/hosting/systemd/` before the lift. What decides the catch-up is systemd's stamp,
          `/var/lib/systemd/timers/stamp-<name>.timer` (`stat` it before the lift). systemd 255 (Ubuntu 24.04) writes
          it when the timer first STARTS and again at each firing. So a timer that was enabled once and stopped
          before its first firing also catches up; only a timer that has never been started has no stamp (the
          runbook's 09-28 nfl-grade note is that first-enable case, and sp-tennis-daily, installed and never enabled,
          is another).
        - The 11-10 lift of `sp-ncaa-market.timer` at 21:13Z ran the missed Tuesday 16:00Z firing at 21:13:38Z, under
          v1.6.6's season-scoped key. The read covers that run's receipt rows, its counting lines (created, updated,
          `provider_id_collision`, `orientation_reversed`, Kalshi matched, the export), its exit, and the timer's
          NEXT.
      - **How to find every chain (search the resolved steps, not the source text):** a literal grep of
        `deploy/hosting/chains.py` misses steps built from constants: `["sync-matches", *PL]` (chains.py:156 and 170)
        holds no `"PL"` string for a grep to find, though three timers run it (Codex on #918). So the search reads the
        resolved `CHAINS` and maps each chain to the timers whose `Unit=` names it. TERMINAL (laptop or host), in the
        checkout, read-only; `C` is the competition code the hold names:
        ```
        C=NCAA
        python3 - "$C" <<'PY'
        import sys, pathlib, re
        sys.path.insert(0, "deploy/hosting")
        from chains import CHAINS, CLOSING_FAMILIES
        from sp_common import t11_lists
        code = sys.argv[1]
        laptop_only = set(t11_lists()["MLB_LAPTOP_ONLY"])
        rb = pathlib.Path("docs/specs/hosting-h1.md").read_text()
        held = set(re.search(r'^ *HELD="([^"]*)"', rb, re.M).group(1).split())
        intl = code == "WCQ" or code in ("UNL", "CNL", "CNL_Q", "UEFA_EURO", "UEFA_EURO_Q", "FRIENDLIES_INT",
                                         "WCQ_EU", "WCQ_SA", "WCQ_AF", "WCQ_AS", "WCQ_NA", "WCQ_OC", "WCQ_IC")
        units = {}
        for t in sorted(pathlib.Path("deploy/hosting/systemd").glob("*.timer")):
            m = re.search(r"^Unit=sp-chain@(.+)\.service$", t.read_text(), re.M)
            if m:
                units.setdefault(m.group(1), []).append(t.name)
        svc = pathlib.Path("deploy/hosting/systemd/sp-closing-watch.service").read_text()
        watched = re.findall(r"--family (\S+)", re.search(r"^ExecStart=.*$", svc, re.M).group(0))
        family_of = {chain: fam for fam, chain in CLOSING_FAMILIES.items()}
        def triggers(name):
            if name in units:
                host = [t + (" (on THE HELD LIST: not enabled on the host)" if t in held else "")
                        for t in units[name] if t not in laptop_only]
                return host + (["the laptop's morning routine (the architect's block)"]
                               if len(host) < len(units[name]) else [])
            if name.startswith("freshen:"):
                fam = name.split(":", 1)[1]
                return [f"sp-window.timer (sp_run.run_freshens after the window page; skipped where SP_SKIP_FAMILIES names {fam})"]
            fam = family_of.get(name)
            if fam in watched:
                return [f"sp-closing-watch.timer (closing.py watch --family {fam})"]
            if fam == "MLB":
                return ["the laptop's launchd closing watch (MLB)"]
            return ["NO TRIGGER FOUND: read how this chain starts before the hold"]
        for name, ch in CHAINS.items():
            hits = [s for s in ch.get("steps", []) if s and s[0] == "sync-matches" and code in s]
            if hits:
                print(f"{name}: {' '.join(hits[0])} ({len(hits)} step(s)) · {', '.join(triggers(name))}")
        for name, ch in CHAINS.items():
            if ch.get("window_plan") or ch.get("fullseason"):
                how = "sp_run.window_plan" if ch.get("window_plan") else "sp_run.fullseason_resolve over SP_FULLSEASON_LIST"
                print(f"{name}: built at run time by {how} · {', '.join(triggers(name))}")
        if intl:
            what = ("WCQ_EU, WCQ_SA, WCQ_AF, WCQ_AS, WCQ_NA, WCQ_OC and WCQ_IC (a WCQ hold names all seven)"
                    if code == "WCQ" else code)
            print(f"intl-daily: intl-sync (no code on the step; it writes {what} through _upsert_match) · "
                  f"{', '.join(triggers('intl-daily'))}")
        PY
        ```
        On this branch, `C=NCAA` prints ncaa-market (sp-ncaa-market.timer) and ncaa-schedule (sp-ncaa-schedule.timer),
        then the two chains built at run time. `C=PL` prints soccer-prematch (sp-soccer-friday.timer,
        sp-soccer-saturday.timer), soccer-morning-after (sp-soccer-morning-after.timer) and soccer-closing
        (`sp-closing-watch.timer (closing.py watch --family SOCCER)`), then the same two. A closing chain resolves
        through `CLOSING_FAMILIES` and the `--family` arguments of `sp-closing-watch.service`'s `ExecStart` (NFL and
        SOCCER on the host); MLB's resolves to the laptop's launchd closing watch (Codex on #918, ruled by 332 item
        1). A freshen chain (`freshen:*`) resolves to `sp-window.timer`: `sp_run.run_freshens` (sp_run.py:678) is its
        only runner, called from the window chain's post step (sp_run.py:862), and it skips a family that
        `SP_SKIP_FAMILIES` names (MLB on the host; chains.py's FRESHEN CHAINS note). A chain the search cannot
        resolve prints NO TRIGGER FOUND, never a clean line.
        - **The laptop's MLB writers (ARCHITECT 2026-11-10 19:35 ET, addendum 333 item 3(i), verbatim):** "the
          search reads MLB_LAPTOP_ONLY and prints "the laptop's morning routine (the architect's block)" for
          mlb-morning and mlb-preslate, never a host timer that is not enabled". The search reads T11's lists with
          `sp_common.t11_lists()` (the parser the deploy receipt uses), so a timer on `MLB_LAPTOP_ONLY` is never
          printed. A chain whose timers are all on that list prints only the routine. A timer on THE HELD LIST
          (the set-check recipe's `HELD=` line) is printed with "(on THE HELD LIST: not enabled on the host)":
          today `C=ATP` and `C=WTA` print tennis-daily that way, since sp-tennis-daily is installed and never
          enabled (288 item 5). That marking extends 333 item 3(i)'s "never a host timer that is not enabled" from
          `MLB_LAPTOP_ONLY` to the held list; ACCEPTED (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 3(2),
          verbatim): "a held timer is printed marked "(on THE HELD LIST: not enabled on the host)"". `C=MLB` prints mlb-morning and
          mlb-preslate that way; mlb-history (`sp-mlb-history.timer`, on `TIMERS`: the host's api-sports fallback),
          freshen:MLB (`sp-window.timer`, skipped on the host by `SP_SKIP_FAMILIES`) and mlb-closing (the laptop's
          launchd closing watch) as before.
        - **National teams (ARCHITECT 2026-11-10 19:35 ET, addendum 333 item 3(iii), verbatim):** "the rule follows
          the WRITE PATH (_upsert_match), not the step's name: a hold on UNL, WCQ or Euro names sp-intl-daily.timer
          (intl-sync) beside whatever the search finds; the search prints it for those codes." `intl-sync` names no
          competition on its step (`["intl-sync", "--since", "{today}", ...]`, chains.py intl-daily), so the
          step-based search cannot find it. No stored competition is coded `WCQ`; `C=WCQ`, as the ruling words it,
          prints the seven `WCQ_*` codes the hold must name. It writes every code of `CODE_BY_NAME` in
          src/ingestion/intl_history.py through `IngestionService._upsert_match`: UNL, the seven `WCQ_*` codes,
          UEFA_EURO and UEFA_EURO_Q (the ruling's three), and CNL, CNL_Q and FRIENDLIES_INT (the same write path, so
          the same rule). For those thirteen codes (and `WCQ` as written in the ruling) the search prints
          `intl-daily: intl-sync (no code on the step; it writes <C> through _upsert_match) · sp-intl-daily.timer`.
          ACCEPTED (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 3(1), verbatim): "every code intl-sync writes
          through _upsert_match names sp-intl-daily.timer — all thirteen of the map's, the WCQ expansion included;
          333(iii) named three as examples". `C=UNL` prints that line after the two chains built at run time. tests/test_hold_search_recipe.py fails if
          `CODE_BY_NAME` gains or loses a code the search does not list.

        The two chains built at run time, read on 8aa27a89:
        - **window** (`sp-window.timer`, hourly): `CHAINS["window"]` has `"steps": []`. `sp_run.window_plan` adds a
          `sync-matches --competition <code> --season <season>` step for every competition with a game inside its
          24 hours.
        - **weekly-fullseason** (`sp-weekly-fullseason.timer`, Sun 06:00 UTC): `CHAINS["weekly-fullseason"]` declares
          only the CFBD step (`"fullseason": True`). `sp_run.fullseason_resolve` adds `sync-teams` then
          `sync-matches --competition CODE --season SEASON` for each line of the host's `SP_FULLSEASON_LIST`. T9's
          generator writes a line for every competition with matches within ±30 days, so whether NCAA is on it is
          read from the host's list, not assumed. Codex on #918 found this one; the grep misses it as it misses the
          window.

        No other code path builds the step on a timer: `bootstrap.py` is operator-started, and the closing freshen
        steps (`closing.py`) carry `--match-ids` for the closing families only.
      - **What a hold names (ARCHITECT 2026-11-10 18:55 ET, addendum 332 item 3, verbatim, the rule completed):** "a
        hold on a competition's sync path names (i) every static chain the resolved-CHAINS search finds carrying the
        step (ncaa-market and ncaa-schedule for NCAA; the PL set for PL), (ii) the closing watch when the competition
        is a closing family (NFL, SOCCER on the host; MLB on the laptop) — item 1's hunk, and (iii) the two
        DATA-DRIVEN chains, which carry the step for every competition in season and are not in chains.py's text:
        window (sp_run.window_plan — every competition with a game inside its 24 hours, hourly) and weekly-fullseason
        (sp_run.fullseason_resolve — every line of SP_FULLSEASON_LIST, Sundays 06:00Z). A hold that must stop the path
        COLD disables (iii) too, for hours never days (the window chain is the Desk's hourly repricing for every
        sport), and says for how long; a hold that can tolerate runs under the unfixed code leaves (iii) running and
        READS THEIR EXPOSURE afterward — rows whose season or pair differ against the last pre-hold copy, as 327 item
        1 did — and the procedure names which of the two it chose."
        - **The exposure read's fields, CORRECTED IN PLACE (ARCHITECT 2026-11-10 19:35 ET, addendum 333 item 3(ii),
          verbatim):** "332 item 3's "rows whose season or pair differ" was #902's read, right for a defect that
          rewrote season; the RULE is: the exposure read compares, against the last pre-hold copy and by row id,
          EVERY field the held step writes — season, the team pair, utc_date, status, home_score, away_score,
          full_time_result, external_ids — plus rows created since; each difference is listed and either explained (a
          game played or rescheduled during the hold, named) or is a finding; the hold's declaration names the fields
          its defect can touch, and the read is never narrower than those." So the words "rows whose season or pair
          differ against the last pre-hold copy, as 327 item 1 did" in 332 item 3 above read, from 333 on: every
          field the held step writes, by row id against the last pre-hold copy, plus the rows created since the
          copy. Each difference is listed, then explained by name (a game played or rescheduled during the hold) or
          recorded as a finding. The ruling names eight: season, the team pair (home_team_id, away_team_id),
          utc_date, status, home_score, away_score, full_time_result, external_ids. The write path writes more,
          read on this branch, and "every field" covers them:
          - `IngestionService._apply_match_updates` (src/ingestion/service.py:910-948): also status_raw, matchday,
            stage, home_score_ht, away_score_ht, home_score_90, away_score_90 and referee; a created row also
            carries venue.
          - `sync-matches` on the statsapi MLB source: the series columns through `write_match_series`
            (service.py:686-688).
          - `intl-sync`: the `match_neutral_derived` row of every match it upserts (src/ingestion/intl_history.py,
            after `_upsert_match`), team rows and competition memberships, and the `competitions` row it creates
            for a mapped code new to the DB (code, name, area, type, external id; intl_history.py:319-324; an
            existing competition row is never modified). The read lists such a row as created since the copy.
          Which of those a given hold's read must cover is the hold's declaration (the fields its defect can
          touch). RULED (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 3(3), verbatim): ""every field the held
          step writes" means every field the write path writes — the eight I listed plus status_raw, matchday,
          stage, the HT and 90-minute scores, referee, venue on a created row, the statsapi series columns and
          intl-sync's match_neutral_derived rows and created Competition rows (Codex's P2, fixed in 6bb4cb6c); a
          hold's declaration names the minimum its read covers, never fewer than its defect can touch. 333 item
          3(ii)'s list of eight is corrected to that reading with this item quoted." So 333 item 3(ii)'s eight above
          read as that list.
        - **The durable answer, declared (332 item 3):** a per-competition sync hold that the step itself honors,
          `SP_SYNC_HOLD`. It ships as its own small PR (#921). Until it merges, the procedure above stands. (333
          item 3(iii), verbatim): "SP_SYNC_HOLD (#921) honors the same path: its design covers intl-sync, or says in
          its body why not."
    - **The deploy's receipt:** 323 item 1 rules that the deploy's report of timers missing from `timers.enabled`
      reads this list. Today `sp_deploy.py` reads only T11's lists, so a held timer missing from the file still
      reads "!" under `TIMERS`. Teaching it this list is a deploy-script change, so it ships as its own PR after
      this one (addendum 7 item 2 (5): the policy first): #915.
    - **SP_SYNC_HOLD, the hold's first move (ARCHITECT 2026-11-10 18:55 ET, addendum 332 item 3, verbatim):** "THE
      DURABLE ANSWER is a per-competition sync hold the step itself honors: SP_SYNC_HOLD, a list of competition codes
      read by sync-teams and sync-matches, which print "HELD <code> (SP_SYNC_HOLD)" and exit 0 for a listed code, every
      chain and timer unchanged, the window and fullseason plans unchanged; a receipt line counts the held steps."
      As built (#921):
      - **Set it first.** On the host, add the code to `SP_SYNC_HOLD=` in `/etc/sports-predictor/host.env`; on the
        laptop, in the checkout's `.env`. No timer is touched. The setting is read on every check from three places:
        the process environment, host.env (`SP_HOST_ENV`) and the checkout's `.env`. A code named in any of them is
        held, so a run by hand outside a unit and the long-running admin UI see a hold set after they started, with no
        restart. Codes are separated by commas or blanks, any case. Lift by removing the code from every place that
        names it; a process that inherited it in its environment at start (a unit's `EnvironmentFile`) keeps holding
        it until that process ends, which for the chain units is the end of the run. The hold names the codes it set
        and the time. Every chain receipt records the setting as parsed (`sync_hold`, by place) and its summary line
        ends ` · SP_SYNC_HOLD <codes>` while one is set, so a misspelt code shows on the first run.
      - **ONE place per machine (ARCHITECT 2026-11-11 09:35 ET, addendum 336 item 2, verbatim):** "a hold is set in
        ONE place per machine — /etc/sports-predictor/host.env on the host, the checkout's .env on the laptop — never
        exported in a shell or a unit, so lifting is one edit and no process carries a stale copy; the receipt's
        by-place line is the check." The three places stay read (the union, accepted by the same item). Reading the
        by-place line: on the host, `environment` naming the same codes as host.env is expected (every unit loads
        host.env through its `EnvironmentFile`, and sp_run loads it into its own environment), and so is it on a
        laptop whose process loads the checkout's .env; the finding is a code named under a place that the
        machine's one file does not name (`environment` naming a code the file does not, or the other machine's
        file). A long-running process (the admin UI, sp-web) keeps the environment it started with, so after a lift
        it holds the lifted code until it restarts; the receipt's by-place line shows that as `environment` naming a
        code the file no longer names.
      - **Lifting a hold (ARCHITECT 2026-11-11 10:15 ET, addendum 337 item 2, verbatim):** "holding longer is the
        safe direction; the stale copy is real for a long-running process started with the code in its environment
        (the units read host.env through EnvironmentFile). RULED for the runbook's lift step, on #928 with the rest:
        "lifting a hold: remove the code from the machine's one place, restart every long-running service that loaded
        it (the admin UI's unit, named), then read the by-place line on the next chain receipt — a code still listed
        under `environment` is a process that was not restarted". 336 item 2's "no process carries a stale copy" is
        corrected to that. Chains are short-lived and need nothing." The admin UI's unit is `sp-web.service`. On the
        host:
        1. Remove the code from `SP_SYNC_HOLD=` in `/etc/sports-predictor/host.env`.
        2. `sudo systemctl restart sp-web.service`.
        3. Read the by-place line on the next chain receipt: the last `chain` receipt's `sync_hold`. The receipts
           table (`sp_receipts.py`) does not print it; this does:
           `sudo -u sp venv/bin/python -c "import json,sys; sys.path.insert(0,'deploy/hosting'); import sp_common as c; r=[x for x in map(json.loads, open(c.receipts_path())) if x.get('kind') == 'chain']; print(r[-1].get('sync_hold') if r else 'no chain receipt')"`
           (`None`: nothing held anywhere, or that run was refused before its steps: read the one before).
           The lifted code is listed under no place.
        4. **What step 3 cannot see (Code's review, put to the architect on #928):** a chain receipt's `environment`
           is the chain's own process, and every chain re-reads host.env at its start (the unit's `EnvironmentFile`,
           and sp_run's `load_host_env`). So the next chain receipt reads clean after the edit whether or not
           sp-web was restarted. What does see sp-web: its start time after the edit
           (`systemctl show -p ActiveEnterTimestamp sp-web.service`), or its own environment
           (`sudo tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value sp-web.service)/environ | grep SP_SYNC_HOLD`,
           which prints nothing once the code is lifted and sp-web restarted).
        On the laptop: remove it from the checkout's `.env`, and restart the admin UI if it is running. The chains are
        short-lived and need nothing.
      - **What honors it.** `sync-teams` and `sync-matches` on every source (the MLB api-sports fallback and the
        tennis path included, checked before either, after the arguments are validated), `--match-ids` included: a
        held closing read exits 0 (332 item 3's contract). **THE HELD CLOSING READ (ARCHITECT 2026-11-11 09:35 ET,
        addendum 336 item 1, verbatim):** "the CLOSING RUN, which already records the held step, treats a held A1
        schedule read exactly as it treats an A1 read that was not answered today — the same path, the same receipt
        fields, the same notice, nothing new invented — with the cause named `schedule_held (SP_SYNC_HOLD <code>)`. It
        does not go on with the stored schedule to an export, a page or a push for that family." As built: A1 is per
        family today (each family's closing covers one competition, and a read that did not answer fails the whole
        run), so a held read fails the family's run at that step: `failed` reads `step i (schedule read:
        schedule_held (SP_SYNC_HOLD <code>), A1)`, the step keeps `held` and its tail, the run keeps `sync_held`, a
        watch-started run sends the failed-run notice and counts the attempt, and nothing is exported, paged or pushed.
        The console prints `· HELD (SP_SYNC_HOLD) <codes>: step i wrote nothing; the schedule read was not made, so it
        reads as not answered (A1): the run stops here and nothing is priced on the stored schedule`. The schedule
        reads are the three closing chains' only steps that honor the hold. The closing watch's slate stage runs
        the same reads (slate_steps): a held slate read is recorded the same way (`held` on the step, `sync_held` on
        the slate receipt) and the slate goes on. **THE HELD SLATE (ARCHITECT 2026-11-11 10:15 ET, addendum 337 item
        1, verbatim):** "the slate GOES ON, as built, with the held read recorded on its receipt. A slate is a page of
        the day's games, not a call: the call is the closing's, and a held family's closing now fails as unanswered
        (336 item 1), so no bet can ride on a kickoff the slate did not re-read. What is missing is the label where
        the reader looks (law 4): the slate file and its page say "schedule not re-read: SP_SYNC_HOLD <code> —
        kickoffs as stored" on a held family's rows." As built (#928): every row of the held family's slate file
        carries `schedule_note` = that text. The labelled document is written to its own file beside the kept
        export, `logs/<run id>.<slate file stem>.schedule-note.json`, created once and never written over, and THAT
        file is linked into exports/. The export step's kept file is never written again (#442), so `export_written`
        {file, sha256} still verifies. The page carries the same text on its second line. The slate receipt keeps
        `schedule_note` {file, text, rows, sha256}, and `slate_file` names the labelled file's sha256. A label that
        cannot be written fails the slate as `slate rows not labelled`, its notice naming the cause, and nothing is
        linked, pushed or paged. The NCAA shadow's `refresh_seen` names a held refresh-by-id step: state `none`, `held` [codes], and
        `why` "the refresh-by-id step was HELD (SP_SYNC_HOLD <code>): it wrote nothing and no refresh_by_id
        receipt". By the write path (333 item
        3(iii)): `refresh-by-id` (NCAA,
        NFL), `intl-sync` (it writes nothing for a held code of its plan and prints one HELD line per code), and the
        admin UI's two sync jobs. A held step builds no adapter, makes no provider call and writes nothing.
      - **What it does not hold.** Steps that write other tables for the competition's rows: odds and Kalshi syncs,
        `capture-odds`, predictions and exports, `ncaa-cfbd-labels`. A defect in one of those is held by its timers,
        as above.
      - **The receipt.** Every chain receipt, and every freshen run's, carries `sync_held` {n, steps: [{step,
        command, codes}]}, 0 when none was held. A run that held a step adds ` · held steps (SP_SYNC_HOLD) N: step i CODE, ...` to its summary line
        and `; held steps (SP_SYNC_HOLD) N` to the receipts table's key line, and a held competition's receipt line
        reads `sync-teams HELD (SP_SYNC_HOLD)` and `sync-matches HELD (SP_SYNC_HOLD)`.
      - **Where it runs.** The laptop holds from this PR's merge (main). The host holds from the tag that carries it.
        Until then a host hold is the procedure above (timers), as 332 item 3 says.
  - **The read before the policy (addendum 316 item 3):** "Ubuntu 24.04.5, kernel 6.8.0-147 with 149 waiting, 24
    noble-updates packages, 3w4d uptime, disk 25%."
  - **First receipt (ARCHITECT 2026-11-10 12:20 ET, addendum 320 item 4, verbatim):** "THE HOST (the operator,
    16:26–17:06Z): a .backup first (sports_2026-11-10_162631.db, integrity ok); apt-get upgrade --with-new-pkgs
    detached under systemd-run: 28 upgraded, 6 newly installed, rc 0; the session dropped at tailscaled's restart as
    the block anticipated and the job finished on its own; reboot for 6.8.0-149 at 17:05:47Z with no chain due; the
    post-check's final read follows."
  - **The automatic reboot (ARCHITECT 2026-11-10 13:20 ET, addendum 322 item 1, verbatim):** "The 11-09 read grepped
    `Automatic-Reboot` in /etc/apt/apt.conf.d/50unattended-upgrades ONLY — the shipped file is 52sp-…, which that grep
    never opened — so the read did not contradict H0-3; it did not look. RULED: H0-3 STANDS as shipped:
    unattended-upgrades installs the security pocket daily and reboots at 04:30 UTC when a security upgrade asks
    (04:30Z is the quiet hour: the per-minute closing-watch only; no closing is ever due then; the first chain is prune
    at 05:30Z); the manual monthly upgrade of 316 item 3 covers the -updates pocket, which never auto-installs, and its
    reboot is the block's, in a window." 316 item 3's "no automatic reboot — as read 11-09 22:07Z" is WITHDRAWN.
    - **Two reboots, two owners:** the security pocket installs itself daily and reboots itself at 04:30 UTC when an
      upgrade asks (`deploy/hosting/etc/52sp-unattended-upgrades`, which `install.sh` installs into
      `/etc/apt/apt.conf.d/`). The -updates pocket never auto-installs: it is the monthly upgrade above, and its reboot is
      the block's, in a window.
    - **The effective config is read, not assumed.** TERMINAL (host), in the architect's next host block:
      `apt-config dump | grep -i -E "Automatic-Reboot|Unattended-Upgrade::Allowed|Origins-Pattern"` and
      `ls /etc/apt/apt.conf.d/ | grep -E "^5[0-9]"`. Effective config confirmed: 2026-11-10 (ARCHITECT 2026-11-10 16:40 ET, addendum 331 item 4,
      verbatim: "the host OS upgraded and rebooted (17:05Z, kernel 6.8.0-149) with the effective unattended-upgrades
      config confirmed").
- **The laptop's morning code update (ARCHITECT 2026-11-10 13:05 ET, addendum 321 item 3, verbatim):** "the
  fast-forward pulls the code and nothing installed new requirements — the first hand-render stopped on `No module
  named 'matplotlib'`. Closed: the morning block carries `pip install -q -r requirements.txt` after the fast-forward
  from tomorrow (idempotent)". TERMINAL (laptop), in the morning block, right after the fast-forward:
  `venv/bin/pip install -q -r requirements.txt`. The host is already covered: `sp_deploy.py` installs requirements.txt
  when it changed in the deployed range or the host has no install receipt for the target's file.
- **Retention (H0-14).** 14 dailies. `sp-backup-prune` only reports
  (`kind: prune`, `applied: false`).
  - After the first time it lists files, delete those files by hand and
    review the result.
  - Only after that review, set `SP_PRUNE_APPLY=1` in host.env and record
    it in BACKLOG.
- **Snapshot retention (#82): DESIGN ONLY, awaiting ruling.** The plan for
  `odds_snapshots` pruning and rollup is in
  [snapshot-retention.md](snapshot-retention.md). No prune exists; none
  runs before the ruling, and none before the H2 cutover.
- **Monday ritual (H0-6).** TERMINAL (host):
  `sudo systemctl start sp-soccer-refresh.service; journalctl -u sp-soccer-refresh -n 80 --no-pager`.
  A fresh prerefresh `.backup` is taken first, and a failed backup stops
  it. A REJECTION is stop-and-investigate.
- **A held PASS (H0-5).**
  - You get a page (or see a `page` receipt): `SP-PAGE: improve --sport mlb PASS HELD`.
  - Review it with the architect.
  - To ratify: `sudo -u sp venv/bin/python cli.py ratify-candidate --sport mlb --version <v> --yes`.
  - Otherwise leave it held. The next morning's candidate is gated against
    the same production.
- **Deploying a release** (release model, 2026-09-30: `main` = BETA,
  production = tags; docs/RELEASES.md). TERMINAL (host):
  `sudo -u sp venv/bin/python deploy/hosting/sp_deploy.py [--tag vX.Y.Z]`.
  It checks out the latest `vX.Y.Z` tag (detached) — never `main` — and
  refuses when no tag exists. It lists any new `migrate_*.py` and prints the
  one command that runs them: copy it verbatim (as the service user, host.env
  loaded, `sp_deploy.py --expect <sha> --run-migrations <names>`). That
  command holds ONE DB lock across the daily backup and every migration, in
  order, stopping at the first failure; a migration run on its own takes no
  lock, so a timer could interleave (ARCHITECT 2026-10-22, addendum 154 item 2;
  docs/RELEASES.md step 5: the dry run first, then the deploy, then the printed
  command). Never pass `--run-migrations` to the deploy call itself. Every
  receipt line names the running tag.
  - When `requirements.txt`, or a file it includes with `-r`/`-c`, changed in
    the range, or this host's last successful install (recorded in
    the venv, which survives log rotation) was not of exactly the target's
    files, the deploy runs
    `venv/bin/pip install -r requirements.txt` before the checkout. It runs in a
    temporary worktree of the target, so relative `-r`/`-c` includes resolve.
    It prints the command and writes a `deploy_requirements` receipt.
    (ARCHITECT 2026-10-06: the host lacked `cryptography` after v1.2.3.)
  - The install record covers the bootstrap: the deploy that ships this
    behaviour still runs the old deployer, so the next deploy installs.
  - A failed install refuses the deploy, and the code stays on its release.
    pip does not roll back packages it already upgraded in that run, so the
    venv may be partially updated. Fix the cause, run the printed command by
    hand from a checkout of the target, then deploy again.
  - A target without `requirements.txt` installs nothing and says so.
  - Only plain requirements files auto-install: comments, version specifiers,
    and `-r`/`-c` includes of tracked files. Anything else (editables, local
    paths, `--find-links`, `name @ …`, `$VARS`, continuations, other options)
    refuses the deploy with the reason. Install those by hand, then deploy with
    `--requirements-installed-by-hand` (receipted, and bound to that release:
    each new release that needs a by-hand install is acknowledged again).
  - An untracked host file where the target adds a tracked one refuses the
    deploy before anything is installed.
  - The install record lives inside the venv (`venv/.sp-requirements.installed`),
    so a recreated venv reinstalls on the next deploy.
  - The deploy installs no unit files. Its receipt line (and `timers_not_enabled` in the receipt) names, by
    name only, every timer the deployed tag ships that `/etc/sports-predictor/timers.enabled` does not list,
    under the T11 list that carries it (ARCHITECT 2026-10-23, addendum 155 item 8(b): the host ran without
    `sp-ncaa-schedule.timer` from 10-09 to 10-23). A `TIMERS` timer missing reads "!": install and enable it
    by T11's recipe for a live host. The `MLB_LAPTOP_ONLY` timers are off by T11: the line counts them, plain,
    never names them ("3 on MLB_LAPTOP_ONLY (held off by T11)"; ARCHITECT 2026-10-28, #725: "the deploy's timers
    line must name only the TIMERS timers missing"); alone they leave the line plain. A timer on no T11 list is
    named, "!", "(unlisted)". The lists are read as T11's block holds them, whatever their names: a list the code
    expects that the block lacks is noted on the line and never empties the others (`HELD_FOR_CUTOVER`, the third
    list, was retired at the cutover: addendum 168 item 5; the deploy runs the release it replaces, so the old
    code reads the new runbook). An unreadable `timers.enabled` prints "!" and no list; an unreadable T11 block
    prints "!" with its error, and every timer reads unlisted. That block, or one with no `TIMERS` list, prints
    "!" even with no timer missing, never "✓" (law 4).
    The same receipt (and `timers_active_not_listed`) names, by name only, every sp timer systemd lists as
    ACTIVE that `timers.enabled` does not list (ARCHITECT 2026-10-26, addendum 168 item 2: `sp-intl-daily.timer`
    and `sp-exports-squash.timer` ran enabled by hand with no list line, so the cutover's pause would have left
    them running): "!", add them to the list by hand; the deploy never writes it. None prints nothing more. A
    listing that cannot be read prints "!" and no list, never an empty one.
- **Midweek PL round (H0-10), operator-started.**
  `sudo -u sp venv/bin/python deploy/hosting/sp_run.py soccer-prematch` (no longer data only: since ARCHITECT
  2026-10-25, addendum 166 item 6(B), no step reads `--set sat=` / `sat_plus3=` any more, and its last step, the
  host-only expansion shadow export, writes its own new file, `exports/soccer_expansion_shadow_<stamp>.json`, with
  rows until the next timer's chain export, its fire + `EXPORT_WINDOW_MARGIN`, 2 h, addendum 185 D2 and addendum 188
  item 4; a refused league exits 2 after the file is written, D7). The round's slate file is the closing
  watch's slate stage's, in the midweek form (`closing.soccer_window`: a Wednesday to Friday day prices the day to the
  day + 3).
- **Seasons (H0-8).**
  - NHL turns itself on at 2026-09-29, the 2026-27 opening day (operator-confirmed
    2026-09-28; the old 2026-10-07 was 2025-derived).
  - Season gates are CONFIG: set `SP_NHL_ACTIVE_FROM=YYYY-MM-DD` in
    `/etc/sports-predictor/host.env` to move a start, with no code change.
  - Every run prints `· nhl-daily active from <date> [<source>]` and
    receipts it (`active_from` on the chain line).
  - A malformed value fails the chain loudly (OnFailure pages); it never
    silently skips.
  - **Before the first real run:** `sync-teams --competition NHL --season 2026`
    (law: sync-teams before sync-matches for EVERY new competition-season).
  - After the World Series:
    `systemctl disable --now sp-mlb-morning.timer sp-mlb-preslate.timer sp-clv-capture.timer`.
    Record it in BACKLOG.
- **London NFL Sundays.** Retired with the prediction timers (ARCHITECT 2026-10-25, addendum 166 item 6(B), applying addendum 126
  item 2(d): "The host's fixed-time timers (nfl-predict Sun 14:00Z — AFTER a 9:30 ET London kickoff) are retired by
  the cutover PR"). The closing watch's slate stage is due at the day's first kickoff less 150 minutes (06:00 ET at
  the earliest), London included; `sp-nfl-prematch.timer` (Sun 14:00 UTC) carries only the injury sync and the
  weather capture.
- **Web UI (H0-4).** TERMINAL (laptop):
  `ssh -L 8000:127.0.0.1:8000 sp@sp-vps-1`, then open http://localhost:8000.

---

## Rulings record (H0, 2026-09-27)

| Rule | Disposition |
|---|---|
| H0-1 | US-East required. DO NYC 2vCPU/4GB (about $24) default; Hetzner US CPX acceptable. Verify live price at purchase (P1). |
| H0-2 | $30/mo ceiling all-in, including off-host backup storage. |
| H0-3 | Auto-reboot allowed at 04:30 UTC. Every timer sits outside 04:15 to 05:15 (CI-checked). Boots are receipted. Amended 2026-10-12 (addendum 45 P3) for one timer, by name: `sp-closing-watch.timer` ticks every minute of every hour (a tick with no start due reads the stored schedule and ends); every other timer stays outside 04:15-05:15 UTC, CI-checked. |
| H0-4 | SSH tunnel (H1). tailscale-serve is an H3 question. |
| H0-5 | improve unattended with a hard guard: PASS is HELD and pages; `ratify-candidate` is the only promotion path on the host. |
| H0-6 | soccer-refresh is operator-started. No timer; `sp-chain@soccer-refresh` refuses without `--operator`. |
| H0-7 | CONFIRMED: 08/12/16/20 America/New_York. The operation's clock is Eastern, and DST follows the zone. |
| H0-8 | Resolved per H0-6's principle (operator control). NHL is encoded as `active_from` (ruled 2026-09-29, the 2026-27 opening day; host override `SP_NHL_ACTIVE_FROM`, amended 2026-09-28); MLB off is an operator `systemctl disable` after the World Series, BACKLOG-recorded. |
| H0-9 | results-tally at the end of mlb-morning. |
| H0-10 | Resolved: operator-started `soccer-prematch --set` runs; no midweek timers. |
| H0-11 | NCAA timer ON, enabled with the rest (a live sport with Saturday slates). |
| H0-12 | Resolved per law 1: the list is generated from a read-only DB query (T9), never assumed. A missing list fails loudly. |
| H0-13 | ntfy.sh private topic (`NTFY_TOPIC` in `.env`): zero cost, no account, works from any unit. The receipts log stays the permanent record; a held PASS pages AND logs. |
| H0-14 | Both layers. (1) DO weekly backups ON (droplet disaster recovery; a restore discards the live DB in favour of the newest `.backup`). (2) A nightly laptop pull of the latest `.backup` over the tailnet ($0, off-provider). Host retention is 14 dailies; prune stays report-only until the first manual prune is reviewed. |
| H0-15 | Manifest = .backup DB + .env + exports/ + receipts log. Row-count receipts cover every table (sqlite_master), so no hand list is needed. The laptop's `~/.sports_predictor_input_candidates.json` cadence stamp is outside the manifest, so the weekly input evaluation runs on the first host morning (nothing is consumable, so no effect). |
| H0-16 | (a) only on a dashboard headroom receipt, else (b) designated days. Never (c). Encoded as `SP_PARALLEL_MODE`, with conservative default (b) and no days. |
| H0-17 | Laptop is writer of record all week. |
| H0-18 | Cutover criteria frozen (section H2). Criterion 3 amended 2026-09-27, BEFORE day 1: "capture timing or explained provider pagination, each explained". |
| H1 phasing | Amended 2026-09-27 (operator proposal, ratified with a guard): H1a fresh bootstrap (acceptance = the host reproduces the BACKLOG fingerprints and the model identity), H1b independent parallel week, H2 = the one `.backup` migration. |
| B4 | RATIFIED 2026-09-27: the production `model_versions` rows are seeded in H1a (config only; the books stay empty). Compare verifies model identity. All four model-bearing timers are enabled with the rest, except the two MLB ones (see the ASN row). |
| MLB / ASN | 2026-09-27: statsapi.mlb.com returns 406 to the DO ASN (architect finding). MLB syncing is a LAPTOP duty. The host MLB timers (mlb-morning, mlb-preslate, clv-capture) stay OFF. Bootstrap uses `--skip-family MLB` (SKIPPED-ASN receipts; compare reports N/A-host). The post-cutover fix (Tailscale exit node via the Mac, or residential egress) is an H2-era decision, deferred. |
| H0-19 | Pasted table (`sp_receipts.py`). An exports-ingestible file is H2. |
| H0-20 | Pull over the tailnet (scp/Taildrop). Push is H2. |
| H0-21 | Resolved by the H1 authorization: artifacts now, provisioning at Anthony's timing. |
| D1-D6 | Already fixed on main by `dbd9322` (2026-09-27). The H1 PR re-verifies them; see its receipts. |

## Open (return to the architect)

None. B4 and the criterion-3 wording were ruled on 2026-09-27.

## On the record: FOUND SAFETY GAP (H0-5)

Reading `improve` for H0-5 found that a gate PASS **auto-promoted** in the
same call (`_shelve_current_production` then `_set_status("production")`),
and the no-production path did the same. 36 consecutive rejections had
masked a live auto-promotion trigger. In an unattended unit, a single PASS
would have changed the model serving the pre-slate chain with no human
reading the verdict. **Closed in this PR:**
- `--hold-on-pass`, forced on the host by `SP_IMPROVE_HOLD_ON_PASS=1`,
  marks a PASS `held` and pages.
- `ratify-candidate` is the only promotion path, and only against an
  unchanged baseline.
- The gate itself is unchanged. The architect cites this finding as the H0
  process's proof of value.
