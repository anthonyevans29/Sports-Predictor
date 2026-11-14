## 2026-11-14 (#999: 853-nflverse-shapes — the nflverse feed's two failure shapes from #853, fixed fail-first (ARCHITECT, addendum 381 item 3(iv)).)
- **F1: a `--file` that cannot be read into its temporary copy is a refusal.** This covers four cases: the original is unreadable, the original is gone since the run checked it, `mkstemp` fails, or the copy hits a full disk. The run exits 2 with nothing copied and nothing written. Before, the raw `OSError` escaped `run()` as a traceback and the command exited 1, the failed-observation code, with no output. The message names the error's type and text, never the temporary path (`src/availability/nflverse.py`, `_run_args`).
- **F2: a header-only payload is the previous payload of its endpoint.** `nflverse.previous_payload` now reads `empty` observations beside complete and partial ones. So the next call sends the header-only file's ETag, never the older non-empty one; a byte-identical 200 is not kept again; and a 304 carries it. `record.ASSERTING` is unchanged: an `empty` observation still asserts nothing.
- **docs/specs/availability-record.md (section 9):** "the last payload" and the `--file` read carry both rules.
- **Tests (`tests/test_availability_nflverse.py`, seven, each failing on fbc33b23):**
  - F1's four cases, each through `run()` and the command;
  - F2 by fetch: two header-only 200s then a 304;
  - F2 after a complete payload;
  - the `--file` analogue.
- No date moved, and no bar moved.
