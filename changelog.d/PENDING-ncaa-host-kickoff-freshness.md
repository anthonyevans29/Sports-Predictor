## 2026-10-09 (#PENDING: NCAA kickoff freshness on the host: a daily forward-week sync, ARCHITECT addendum 19 item 3)
- Ruling and cause: verbatim in `docs/ledger/entries/2026-10-09-ncaa-host-kickoff-freshness.md`.
- New host chain `ncaa-schedule` (`deploy/hosting/chains.py`): `sync-matches --competition NCAA --season 2026 --date-from D --date-to D` for D = today .. today+7, single-day calls (the american-football adapter sends `date` only when from == to). Sync only: no Kalshi, no export, no model step. `NCAA_FORWARD_DAYS = 7`.
- New timer `sp-ncaa-schedule.timer`: every day, 10:35 and 22:35 UTC (outside the H0-3 reboot buffer). Twice a day, so one failed run still leaves every stored kickoff under a day old. Added to the runbook's T11 `TIMERS` list, with the install steps for a live host (`docs/specs/hosting-h1.md`).
- `sp_run.date_vars` gains `{today_plus1}`..`{today_plus7}` (`{today_plus3}` unchanged).
- `ncaa-market`, the window service and the adapter are unchanged.
- Docs: `docs/CLI.md` (NCAA kickoff freshness paragraph), `docs/specs/hosting-h1.md` (timer table, T11, live-host install).
- Test: `tests/test_hosting_pack.py::test_every_ncaa_kickoff_in_the_next_seven_days_is_refreshed_every_day`. For each weekday it resolves every chain whose timer fires that day and requires single-day NCAA syncs covering today..today+7. On the old chains it fails on Monday with all eight dates missing (no NCAA sync fires on Monday).
- Host action after the tag that carries it is deployed: install and enable the new timer (runbook), then run `sp_run.py ncaa-schedule` once.
