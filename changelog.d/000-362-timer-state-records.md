## 2026-11-12 (#000: 362-timer-state-records — RECORDS (ARCHITECT 2026-11-12 17:20 ET, addendum 362 item 3): wherever the repo says a timer is disabled and the host says otherwise, the repo is corrected the same day.)
- **docs/specs/availability-record.md:**
  - The availability-daily section (line 770) gains its enabled line: **ENABLED on the host 2026-11-09 at 14:16Z**, on v1.6.5, from the deploy record of addendum 304 item 2.
  - The observe watch (line 914) gains its enabled line: **ENABLED 2026-11-12 at 15:23–15:25Z**, on v1.6.7 (354 item 1); the first tick, at 15:25:02Z, wrote observation #5; the timer set read CLEAN at 21.
- **docs/specs/hosting-h1.md:** the `sp-availability-daily.timer` and `sp-nba-daily.timer` recipes each gain the same 2026-11-09 14:16Z line (304 item 2). Both carried the "until then … not enabled" wording that 360 item 5 corrected for the observe watch. The observe watch's own line rides #971.
- **Unchanged:** every timer list, date, bar and lane; no code.
