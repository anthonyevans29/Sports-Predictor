**2026-11-16 — The NCAA listing probe: the provider's raw college football rows per date, beside what our side would do with each (addendum 414 item 3; #1035; #1038).**
- **Ruling (414 item 3, verbatim in part):** "THE PROBE: BUILD IT, as your (b) costs it. One small PR, lane A, read-only tooling under the stop rule. (a) One script under scripts/: for each date given, ONE GET of the provider's games for league 2, season 2026 and that date, through the adapter's own _get, and the RAW rows printed before any parsing ... (b) Beside each row, what our side would do with it, by your own table ... (c) THE FENCE: no write anywhere, no file made ..."
- **What landed:** `scripts/ncaa_listing_probe.py`, its test and its scripts/README.md row.
  - One `_get("games", {league 2, season 2026, date D})` per date, at most seven dates a run. The count of provider calls is printed first (planned) and last (made, in HTTP requests, so a 429's retry shows).
  - Each raw row is printed with its game id, date, time, timestamp, status, week, stage, and home and away ids and names.
  - Beside each row: drops #1, #2 and #3 of DEV 1's table on #1035; with `--db`, #6, the stored match holding the id (with its season), or NOT STORED.
  - The key is named, never printed. A provider error prints, stops and exits 1. A refusal exits 2 before any call.
  - The fence: no sync, re-key or repair module is loaded (a test holds it in a fresh interpreter); no bytecode file; the copy is opened mode=ro&immutable=1.
  - The test runs on invented rows only (414 item 3(d)).
- **Next:** the architect's block of Thursday 2026-11-19, for 2026-11-21, 2026-11-27 and 2026-11-28 against that morning's copy (three calls). The ruling on #1038 follows it (414 item 4(a)).
