## 2026-10-17 (#571: lineups-save-fix — #565, ARCHITECT addendum 104 item 4)
- src/ingestion/lineups_history.py (`sync-lineups-history`), #538's two round-2 findings (#565):
  - `--save` keeps an HTTP error answer's decoded body. The request wrapper keeps every answer's body as it arrives, whatever its status, and the HTTPError branch saves it before the run stops (401, 403, a 429 after the adapter's own retry) or moves on (5xx). A body that does not decode keeps nothing, as before.
  - `refreshed_at` is taken per fixture, just before its store. It is no longer once for the whole run, which left a 100-call run's last rows about 10 minutes early.
- docs/CLI.md: the two sentences that describe `--save` and the rows' time.
- tests/test_lineups_history.py (+2): a 500 body kept while the run moves on, and a 429 body kept before it stops (the adapter's one retry counted); two fixtures each carry their own `refreshed_at`.
- Ledger only, from the same day's rulings: addendum 103 item 1 (#568), addendum 103 item 3 (the NCAA resync answer on #399; #570) and addendum 105 (MLB twin rows, #569).
