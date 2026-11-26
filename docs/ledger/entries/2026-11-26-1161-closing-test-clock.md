**2026-11-26 — A #1161 test that failed after 12:00 UTC is fixed (a test fix; DEV 2, Lane B; #0000).**
- **Finding:** `tests/test_1102_stale_price_rule.py::test_a_closings_file_has_no_f1_reads_off_no_run_start_and_carries_f2_to_f4` (merged with #1161) seeded today's 12:00 UTC as the kickoff. After that hour the export skips the started game, so the test failed on every run from 12:00 to midnight UTC. Seen on clean main 8de2a3ac by 503's PR 2 build.
- **Fix:** the kickoff is two hours from the clock, cut to the minute; nothing else in the test or the code changes.
