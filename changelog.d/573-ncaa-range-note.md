## 2026-10-17 (#573: ncaa-range-note — #570, ARCHITECT addendum 106 item 3, addendum 107 item A1)
- src/adapters/api_american_football.py (NCAA and NFL): `list_matches` prints one line before the fetch when `--date-from` ≠ `--date-to`: `RANGE A..B is not supported by this provider: reading and writing the whole <season> listing` (`range_note`). The provider's `/games` takes one `date`, so a range has always read and written the whole season. **No behaviour change**: the same call is made and the same listing written.
- cli.py `sync-matches --match-ids`: both strict lines carry the same words when the adapter could not send the range. The `✗ STRICT` label reads `(<code> A..B: RANGE …)`, and the `✓` line ends `(RANGE …)`.
- src/ingestion/resync_diff.py: `resync-diff` marks its adapter read-only, so its note says `reading`, not `reading and writing`.
- docs/CLI.md: the `sync-matches` row says so.
- tests/test_range_note.py (4): the note's words and where it prints (a range only; a single day and a season read print nothing); the line comes before the fetch and the call is unchanged; the STRICT label through `sync-matches` (#570's faked-provider receipt); `resync-diff` says `reading`.
