**2026-10-07 — sync-pitchers count line: one population on both sides (#341).**
- **Finding (ARCHITECT, addendum 5, daily-class, verbatim):** "sync-pitchers printed \"4/3 games with probable pitchers\" at 21:59Z. The numerator counts every game on the date and the denominator only upcoming ones."
- **Built:** the line is `<with>/<upcoming> upcoming games with probable pitchers (<n> date-wide, started games included)`, where `<n>` counts the date's games with a probable (the batch holds no others). `<with>` counts this run's upcoming games whose source id the date's batch carries. Test: `tests/test_sync_pitchers_count.py`.
- **Effect:** a log line only; no data and no policy change.
