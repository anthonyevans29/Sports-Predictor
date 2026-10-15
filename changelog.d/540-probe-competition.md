## 2026-10-15 (#540: probe-competition — ARCHITECT addendum 75 item 3(a))
- scripts/lineup_timing_probe.py takes `--competition CL|UEL|EFL` (default CL): the stored competition code whose rows on the day are polled. The polls, the late rule and the summary are the same for each, and the header and the D0 lines name the code read.
- tests/test_lineup_timing_probe.py: 2 new. A UEL row on the day is polled only under `--competition UEL` and CL stays the default; a code outside the three is refused by the parser.
