## 2026-11-12 (#000: 360-observe-enabled-record — RECORDS (ARCHITECT 2026-11-12 16:00 ET, addendum 360 item 5): the release record follows the host the same day. sp-availability-observe has been enabled since 15:23Z, and the first fixtures_NHL pair is CLEAN.)
- **docs/RELEASES.md, v1.6.7:** "After the deploy" becomes "After the tag". It records three things:
  - `sp-availability-observe.timer` ENABLED on the host at 15:23–15:25Z by the architect's own block (354 item 1, verbatim in part). The first tick, at 15:25:02Z, wrote observation #5. The timer set read CLEAN at 21.
  - The first fixtures_NHL pair under v1.6.7's comparator: CLEAN, status `success` on the host's 16:00:38Z push (355 item 2, verbatim, as Release Issue #949 carries it).
  - The old sentence "stays disabled until its own block" is gone. A reader took it to mean the NHL watch was not collecting (360 item 5).
- **docs/specs/hosting-h1.md:** the sp-availability-observe recipe gains the line that it was enabled on the host 2026-11-12 at 15:23–15:25Z (354 item 1), with the timer set at 21. The recipe stays as the block's shape for a fresh host.
- **Unchanged:** every date, bar, lane, step and timer list; no code.
