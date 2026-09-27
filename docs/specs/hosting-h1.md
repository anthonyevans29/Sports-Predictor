# Hosting H1: the unit pack and Anthony's provisioning runbook

**Status: artifacts only. Nothing runs anywhere until Anthony provisions the
host.** This PR ships files. It buys nothing, schedules nothing and moves
nothing. H0 rulings were made 2026-09-27 (see the table at the end). Design
source: `docs/specs/hosting-h0.md`.

Every step below carries a label:
- **BROWSER** means you click it in a provider or GitHub web UI.
- **TERMINAL (laptop)** means you type it on the Mac.
- **TERMINAL (host)** means you type it on the VPS. Use the provider's web
  console until Tailscale is up, then SSH over the tailnet.

`<host>` is the droplet's Tailscale MagicDNS name. The runbook assumes
`sp-vps-1`.

---

## 0. What ships (deploy/hosting/)

| File | Role |
|---|---|
| `chains.py` | The one place chain commands live. Each step is verbatim from docs/CLI.md and pl_weekly_routine.md, with options made explicit. CI checks every command and every option against cli.py (law 1). |
| `sp_run.py` | Runs a chain under the DB lock. Stops at the first failing step. Writes a receipt per step and per chain. Enforces the backup rule (daily, or a fresh prerefresh). Pages on `SP-PAGE:` lines. Refuses operator-only chains without `--operator`. Handles `active_from` windows and H0-16(b) designated days. `--dry-run` prints the resolved commands. |
| `sp_backup.py` | SQLite online-backup API (`Connection.backup`, the same mechanism as the CLI's `.backup`). Then integrity_check on the copy, sha256, a `.sha256` sidecar and a receipt. Never `cp`; refuses any target under `data/`. |
| `sp_migrate.py` | The sanctioned move in three steps: `pack` (laptop), `verify`, `install` (host). Manifest per H0-15. |
| `compare_exports.py` | Parallel-week export diff (masks timestamps). |
| `sp_receipts.py` | The paste-ready table (H0-19). |
| `sp_notify.py` | Failure and PASS-hold paging. Receipt and journal always; HTTP only if `SP_NOTIFY_URL` is set (H0-13 open). |
| `sp_boot_receipt.py` | One receipt per boot (H0-3). |
| `sp_prune.py` | Backup retention. Report-only until H0-14 is ruled. |
| `sp_deploy.py` | Fast-forward to merged `origin/main` only, with a receipt. |
| `systemd/` | `sp-chain@.service` template, 14 timers, backup, prune, notify@, boot-receipt, web, and `sp-soccer-refresh.service` (no timer). |
| `etc/` | host.env template, full-season list template, unattended-upgrades reboot window, logrotate. |
| `install.sh` | Copies units and config into place. **Enables nothing.** |

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
| sp-nhl-daily | nhl-daily (inactive before 2026-10-07) | daily 16:00 UTC | daily |
| sp-ncaa-market | ncaa-market (**not enabled**: open item 4) | Fri 16:00, Sat 13:00 UTC | — |
| sp-nfl-predict | nfl-predict | Thu 18:00, Sun 14:00 UTC | — |
| sp-clv-capture | clv-capture | 08/12/16/20 America/New_York (open item 1) | — |
| sp-weekly-fullseason | weekly-fullseason | Sun 06:00 UTC | daily |
| sp-backup-prune | (retention, report-only) | daily 05:30 UTC | — |
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
- **Receipt:** screenshot the live price at checkout. It must be at or
  under **$30/mo all-in**, including any off-host backup (open item 3).

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

**P4. TERMINAL (host): SSH hardening (H0-4).**
- Put your Mac's key in `/home/sp/.ssh/authorized_keys` (mode 0600, owned
  by sp).
- In `/etc/ssh/sshd_config` set `PasswordAuthentication no` and
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
`data/` must not exist before M4. `import cli` no longer creates it; that was
fixed 2026-09-27. If `data/` does exist, run `rmdir data` (it would be empty).

**P7. TERMINAL (host): install the pack. It enables nothing.**
```
cd /opt/sports-predictor && sudo bash deploy/hosting/install.sh
```
Receipt: the list of `sp-*` unit files, all `disabled`.

---

## M. The migration (H0-15 manifest: .backup DB, .env, exports/, receipts log)

The laptop stays writer of record for the whole parallel week (H0-17).
The host's copy is a rehearsal copy and is thrown away at cutover (see C).

**M1. TERMINAL (laptop):**
- Stop the launchd CLV jobs: `bash scripts/setup_clv_capture.sh --uninstall`.
- Run no chain.
- Run any pending `migrate_*.py` named in the merge notes (after that
  morning's backup) so the laptop DB is on current schema.

**M2. TERMINAL (laptop), from the repo root with the venv active:**
```
python deploy/hosting/sp_migrate.py pack --out /tmp/sp_pack_$(date -u +%Y%m%dT%H%M)
```
- **Receipt S1/R1:** the printed db sha256, integrity=ok, and row counts
  for **every** table (enumerated from sqlite_master).
- `absent:` lists any manifest item that did not exist (for example, no
  laptop receipts log yet). It is labelled, never faked.

**M3. TERMINAL (laptop): transfer over the tailnet only.**
```
scp -r /tmp/sp_pack_<stamp> sp@sp-vps-1:/home/sp/
```
No cloud bucket, email or chat upload.

**M4. TERMINAL (host):**
```
cd /opt/sports-predictor
sudo -u sp venv/bin/python deploy/hosting/sp_migrate.py verify  --pack /home/sp/sp_pack_<stamp>
sudo -u sp venv/bin/python deploy/hosting/sp_migrate.py install --pack /home/sp/sp_pack_<stamp>
sudo -u sp venv/bin/python cli.py status
```
- **Receipt S2/R2:** `✓ PASS verify` and `✓ PASS install`. S2 = S1, and
  every table's R2 = R1.
- Any `✗` means: delete the pack on the host and repeat from M2.

**M5. Clean up and resume.**
- Delete the pack on both machines (`rm -rf`). It holds a DB copy and
  `.env`.
- Laptop: `bash scripts/setup_clv_capture.sh`. The laptop resumes as
  authoritative.

---

## T. Turn the host on (parallel week)

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

**T11. TERMINAL (host): enable.**
```
TIMERS="sp-backup.timer sp-backup-prune.timer sp-mlb-morning.timer sp-mlb-preslate.timer
  sp-clv-capture.timer sp-soccer-friday.timer sp-soccer-saturday.timer sp-soccer-morning-after.timer
  sp-nfl-lines.timer sp-nfl-grade.timer sp-nfl-predict.timer sp-nhl-daily.timer sp-weekly-fullseason.timer"
echo $TIMERS | sudo tee /etc/sports-predictor/timers.enabled   # the list C2/C4 reuse
systemctl enable --now sp-boot-receipt.service sp-web.service
systemctl enable --now $TIMERS
systemctl list-timers 'sp-*' --no-pager     # receipt: next-elapse for each
```
- Not enabled: `sp-ncaa-market.timer` (open item 4).
- No timer exists for soccer-refresh (H0-6).

**Each parallel-week morning:**
- TERMINAL (host): `sudo -u sp venv/bin/python deploy/hosting/sp_receipts.py --since 24h`,
  then paste the table (H0-19).
- Exports (H0-20, pull over the tailnet). TERMINAL (laptop):
  ```
  scp -r sp@sp-vps-1:/opt/sports-predictor/exports ~/sp_host_exports
  python deploy/hosting/compare_exports.py exports ~/sp_host_exports --glob '*<date>*'
  ```
  Paste the result. Each `✗` needs a capture-timing explanation or a
  BACKLOG entry.
- Only **laptop** exports go to the Cockpit this week (H0-17). Host
  exports are comparison-only.

---

## C. Cutover (criteria FROZEN, H0-18, approved as drafted 2026-09-27)

- 7/7 days with every host timer firing on schedule (the receipts log shows
  each expected unit line).
- Zero unexplained host-side failures; any `OnFailure` notification was
  received and triaged the same day.
- Export diffs clean on the last 3 days (differences only from capture
  timing, each explained).
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

**Cutover morning, before any chain:**
1. TERMINAL (laptop): `bash scripts/setup_clv_capture.sh --uninstall`. Run no chains.
2. TERMINAL (host): `systemctl stop $(cat /etc/sports-predictor/timers.enabled)`.
3. Repeat M2 to M4 with a **fresh** pack, installing with
   `install --replace`. This moves the rehearsal DB aside as
   `data/rehearsal_<ts>.db`; delete it after the receipts.
4. TERMINAL (host): set `SP_PARALLEL_MODE=full` in host.env. Then
   `systemctl start $(cat /etc/sports-predictor/timers.enabled)`. Then `systemctl start sp-backup.service`
   and paste its receipt.
5. The laptop keeps its last `.backup` file cold for 30 days (the rollback
   point). Its `data/sports.db` is not written again.

**Rollback** uses the same protocol in reverse:
1. Stop the host timers.
2. Host: `sp_migrate.py pack`.
3. Transfer the pack to the laptop over the tailnet.
4. Laptop: `verify`, then `install --replace`.
5. Reinstall launchd.

---

## O. Operations after cutover

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
- **Deploying a merge.** TERMINAL (host):
  `sudo -u sp venv/bin/python deploy/hosting/sp_deploy.py`. It
  fast-forwards only and lists any new `migrate_*.py`. For those: first
  `systemctl start sp-backup.service`, then run each migration by hand.
- **Midweek PL round (H0-10), operator-started.**
  `sudo -u sp venv/bin/python deploy/hosting/sp_run.py soccer-prematch --set sat=<first-day> --set sat_plus3=<day-after-last>`.
- **Seasons (H0-8).**
  - NHL turns itself on at 2026-10-07 (`active_from`).
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
| H0-7 | **Open (item 1).** Shipped America/New_York. |
| H0-8 | Resolved per H0-6's principle (operator control). NHL is encoded as `active_from` 2026-10-07; MLB off is an operator `systemctl disable` after the World Series, BACKLOG-recorded. |
| H0-9 | results-tally at the end of mlb-morning. |
| H0-10 | Resolved: operator-started `soccer-prematch --set` runs; no midweek timers. |
| H0-11 | **Open (item 4).** Unit shipped, not enabled. |
| H0-12 | Resolved per law 1: the list is generated from a read-only DB query (T9), never assumed. A missing list fails loudly. |
| H0-13 | **Open (item 2).** |
| H0-14 | **Open (item 3).** Prune is report-only. |
| H0-15 | Manifest = .backup DB + .env + exports/ + receipts log. Row-count receipts cover every table (sqlite_master), so no hand list is needed. The laptop's `~/.sports_predictor_input_candidates.json` cadence stamp is outside the manifest, so the weekly input evaluation runs on the first host morning (nothing is consumable, so no effect). |
| H0-16 | (a) only on a dashboard headroom receipt, else (b) designated days. Never (c). Encoded as `SP_PARALLEL_MODE`, with conservative default (b) and no days. |
| H0-17 | Laptop is writer of record all week. |
| H0-18 | Cutover criteria frozen (section C, verbatim). |
| H0-19 | Pasted table (`sp_receipts.py`). An exports-ingestible file is H2. |
| H0-20 | Pull over the tailnet (scp/Taildrop). Push is H2. |
| H0-21 | Resolved by the H1 authorization: artifacts now, provisioning at Anthony's timing. |
| D1-D6 | Already fixed on main by `dbd9322` (2026-09-27). The H1 PR re-verifies them; see its receipts. |

## Open (return to the architect)

1. **H0-7:** the CLV captures ship at 08/12/16/20 **America/New_York**
   (slate clock). Confirm, or name Anthony's launchd zone.
2. **H0-13:** paging channel for failures and held PASSes. H0-5 depends on
   it: until `SP_NOTIFY_URL` is set, a held PASS pages only to the receipts
   log and journal.
3. **H0-14:** backup retention (shipped report-only: 7 newest dailies,
   14 days, prerefresh 30 days), and the off-host copy inside $30. Options:
   DO weekly droplet backups at +20% (about $4.80, so about $28.80 total;
   they capture the consistent `.backup` files, not the live DB), or a
   laptop pull over the tailnet ($0).
4. **H0-11:** enable `sp-ncaa-market.timer` (market-only, Kalshi primary)?
