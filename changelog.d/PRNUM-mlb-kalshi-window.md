## 2026-10-17 (#PRNUM: mlb-kalshi-window — #175, ARCHITECT addendum 112 item 8, addendum 117 item 1; Closes #175)
- deploy/hosting/chains.py: unchanged. The window's MLB Kalshi step stays `sync-kalshi --date-from {today} --date-to {tomorrow}`. Since #205 (2026-10-02), `--date-to D` reads the whole UTC day D (cli.py). Read from code, the step's window is our stored kickoffs from {today} 00:00Z up to {tomorrow}+1 day 00:00Z, which is the ruled end. It holds the 24 hours of every window run on {today}. The Issue's window (`--date-to` read as midnight, before #205) ended at {tomorrow} 00:00Z.
- docs/CLI.md: the `sync-kalshi` row says what `--date-from` / `--date-to` keep and where the window step's window ends.
- docs/specs/snapshot-retention.md: (F4) says #205 fixed the boundary it describes.
- tests:
  - test_hosting_pack.py: the window chain as sp_run resolves it on a UTC day D. The MLB Kalshi step is `--date-from D --date-to D+1`, every other step resolves to itself, and no other Kalshi step carries a date placeholder. Through the CLI, the step's window runs from D 00:00Z to D+2 00:00Z less a microsecond, past the 24 hours of the day's last window run.
  - test_kalshi_inplay_guard.py: a run at 23:05Z on D and a first pitch at 00:30Z on D+1. The step stores both legs; the Issue's window refuses them as outside the run's window.
