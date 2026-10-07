## 2026-10-07 (#0000: daily-class — NCAA midweek timer, mirror settings from .env, missing key refused, nhl_probe.jsonl ignored)
- `sp-ncaa-market.timer` gains Tue + Wed 16:00 UTC, so midweek FBS games get a host fixtures file. A changed timer is installed on the host by hand after the tag's deploy (`docs/specs/hosting-h1.md`).
- `sp_common.setting` reads the environment, then host.env, then the checkout's `.env` (the environment wins). `exports_mirror.py` reads REMOTE / KEY / ROLE / DIR / AUTHOR through it, so the laptop's `.env` carries them.
- `exports_mirror.py push` REFUSES (exit 2) an SSH remote whose key file does not exist, naming the path, before any git step. It never pushes keyless. `docs/specs/exports-mirror.md` corrects the laptop key name to the default `~/.ssh/sp_exports_deploy_key`.
- `.gitignore`: `/nhl_probe.jsonl` (the NHL probe's `--out` in the repo root).
