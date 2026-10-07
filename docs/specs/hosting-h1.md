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
| `sp_run.py` | Runs a chain under the DB lock. Retries a step that failed TRANSIENTLY (connection errors, timeouts, HTTP 5xx/429 — read from the traceback's terminal line) twice, 15s then 45s, and receipts it as `retried N`. Other 4xx and exceptions in our own code never retry. Stops at the first step still failing (it pages as before). Writes a receipt per step and per chain. Enforces the backup rule (daily, or a fresh prerefresh). Pages on `SP-PAGE:` lines. Refuses operator-only chains without `--operator`. Handles `active_from` windows and H0-16(b) designated days. `--dry-run` prints the resolved commands. |
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
| `systemd/` | `sp-chain@.service` template, 14 timers, backup, prune, notify@, boot-receipt, web, and `sp-soccer-refresh.service` (no timer). |
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
| sp-mlb-morning | mlb-morning (improve HOLDS on PASS; results-tally last) | daily 09:45 UTC | daily |
| sp-soccer-morning-after | soccer-morning-after | Sun/Mon/Tue 09:50 UTC | daily |
| sp-nfl-grade | nfl-grade | Mon/Tue/Fri 10:00 UTC | daily |
| sp-soccer-friday | soccer-prematch | Fri 14:00 UTC | — |
| sp-soccer-saturday | soccer-prematch | Sat 10:30 Europe/London | — |
| sp-mlb-preslate | mlb-preslate | daily 14:30 UTC | — |
| sp-nfl-lines | nfl-lines | daily 15:00 UTC | — |
| sp-nhl-daily | nhl-daily (inactive before 2026-09-29; override `SP_NHL_ACTIVE_FROM`) | daily 16:00 UTC | daily |
| sp-ncaa-market | ncaa-market (H0-11: enabled with the rest); from 2026-10-02 `sync-matches` NCAA yesterday + today runs first (#254) | Thu 16:00 (Thursday-night slates, added 2026-09-28), Fri 16:00, Sat 13:00 UTC | — |
| sp-nfl-predict | nfl-predict | Thu 18:00, Sun 14:00 UTC | — |
| sp-clv-capture | clv-capture | 08/12/16/20 America/New_York (H0-7 confirmed; DST follows the zone) | — |
| sp-weekly-fullseason | weekly-fullseason | Sun 06:00 UTC | daily |
| sp-backup-prune | (retention, report-only) | daily 05:30 UTC | — |
| sp-exports-squash | exports mirror weekly history squash (F2.5; a no-op until `SP_EXPORTS_MIRROR_REMOTE` is set) | Sun 06:10 UTC | — |
| *(none)* | soccer-refresh | **operator-started** (H0-6) | fresh prerefresh |

**H0-3 reboot window.** No timer fires between 04:15 and 05:15 UTC. CI
checks this for both DST states. Unattended-upgrades reboots at 04:30, and
every boot writes a receipt.

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
   to the adapter's series). Bid/ask are stored by the K1 path.
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
     2026-09-29).
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
  `sync-kalshi-nfl` → `predict-nfl` → `export-nfl-predictions`.
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
Generate it from the DB (read-only); never type it from memory:
```
sqlite3 -readonly /opt/sports-predictor/data/sports.db \
 "SELECT c.code || '|' || m.season FROM matches m JOIN competitions c ON c.id = m.competition_id
  WHERE m.utc_date BETWEEN datetime('now','-30 days') AND datetime('now','+30 days')
  GROUP BY c.code, m.season ORDER BY c.code;" | sudo tee -a /etc/sports-predictor/fullseason.list
```
Paste the list as the receipt. Delete any line you do not want synced
weekly. If the list is missing or empty, the chain fails loudly.

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
  sp-soccer-morning-after.timer sp-nfl-lines.timer sp-nfl-grade.timer sp-nfl-predict.timer
  sp-nhl-daily.timer sp-weekly-fullseason.timer sp-ncaa-market.timer sp-window.timer
  sp-mlb-history.timer sp-intl-daily.timer sp-exports-squash.timer"
MLB_LAPTOP_ONLY="sp-mlb-morning.timer sp-mlb-preslate.timer sp-clv-capture.timer"   # NOT enabled: statsapi 406 on the DO ASN (H1b note)
echo $TIMERS | sudo tee /etc/sports-predictor/timers.enabled   # the list H2 steps 2 and 6 reuse
systemctl enable --now sp-boot-receipt.service sp-web.service
systemctl enable --now $TIMERS
systemctl list-timers 'sp-*' --no-pager     # receipt: next-elapse for each
```
- Every shipped timer is on `TIMERS` or `MLB_LAPTOP_ONLY`; CI checks it.
- `TIMERS` includes the soccer model-bearing timers (B4, seeded registry)
  and `sp-ncaa-market.timer` (H0-11).
- The MLB timers stay off. They are shipped and CI-validated, ready for
  whichever H2-era egress decision is made.
- `sp-mlb-history.timer` (MLB PHASE A, 2026-09-29) is ON: it syncs MLB
  history only, from the api-sports fallback. On a live host that
  predates it, see "MLB PHASE A" below.
- No timer exists for soccer-refresh (H0-6).
- `sp-intl-daily.timer` (2026-10-02, 07:20 UTC): the incremental intl sync,
  the v3 venue step and the UNL shadow export (intl-elo-v2's confirmation
  window). On a live host that predates it: install the unit, then
  `systemctl enable --now sp-intl-daily.timer` and add it to
  `/etc/sports-predictor/timers.enabled`.

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
5. Delete the pack on both machines (`rm -rf`). It holds a DB copy and
   `.env`.
6. TERMINAL (host), in order:
   - Set `SP_WRITER_OF_RECORD=host` in host.env (ARCHITECT-RULE 2026-10-01; `sp_cutover.py flip`
     does it), then the same in the laptop's `.env`. `SP_PARALLEL_MODE` stays the quota mode.
   - Run `systemctl start $(cat /etc/sports-predictor/timers.enabled)`.
   - Run `systemctl start sp-backup.service` and paste its receipt.
7. The laptop keeps its last `.backup` file cold for 30 days (the rollback
   point). Its `data/sports.db` is not written again.
   - **H2-era decision, deliberately deferred:** how MLB reaches the host
     DB after cutover, given the statsapi ASN block (H1b note). Options
     named: a Tailscale exit node via the Mac, or a residential egress.
     Settle it before this step. Until then MLB stays on the laptop, and
     cutover must not strand it.

**Rollback** uses the same protocol in reverse:
1. Stop the host timers.
2. Host: `sp_migrate.py pack`.
3. Transfer the pack to the laptop over the tailnet.
4. Laptop: `verify`, then `install --replace`.
5. Reinstall launchd.

---

## O. Operations after cutover

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
  refuses when no tag exists. It lists any new `migrate_*.py`. For those:
  first `systemctl start sp-backup.service`, then run each migration by
  hand. Every receipt line names the running tag.
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
- **Midweek PL round (H0-10), operator-started.**
  `sudo -u sp venv/bin/python deploy/hosting/sp_run.py soccer-prematch --set sat=<first-day> --set sat_plus3=<day-after-last>`.
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
- **London NFL Sundays.** `nfl-predict` fires at 14:00 UTC, which is after a
  13:30 UTC London kickoff. On those weeks run
  `systemctl start sp-chain@nfl-predict.service` by hand before kickoff.
- **Web UI (H0-4).** TERMINAL (laptop):
  `ssh -L 8000:127.0.0.1:8000 sp@sp-vps-1`, then open http://localhost:8000.

---

## Rulings record (H0, 2026-09-27)

| Rule | Disposition |
|---|---|
| H0-1 | US-East required. DO NYC 2vCPU/4GB (about $24) default; Hetzner US CPX acceptable. Verify live price at purchase (P1). |
| H0-2 | $30/mo ceiling all-in, including off-host backup storage. |
| H0-3 | Auto-reboot allowed at 04:30 UTC. Every timer sits outside 04:15 to 05:15 (CI-checked). Boots are receipted. |
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
