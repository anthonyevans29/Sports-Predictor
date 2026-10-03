## 2026-10-03 (#268: HOTFIX: backup verify falls back to a plain read when the read-only URI open fails)
- **`_verify_backup`** (`dedupe-matches --apply`, `clv-restate --apply`) tries two open forms in order, and the receipt names the one that read the backup:
  1. the read-only URI (`Path.as_uri() + "?mode=ro"`, `integrity_check`);
  2. if that raises, a plain `sqlite3.connect(path)` with `PRAGMA query_only = ON` (no writes possible) and `quick_check`.
- On macOS an existing 248 MB backup refused the URI form with "unable to open database file". The success line now reads `opened via <form> (after: <URI error>) · integrity ok (<check>) · journal_mode <mode> · <table> n = live`. If both forms fail, the refusal lists both errors.
- tests/test_backup_verify.py (+3): a macOS-style absolute path whose URI open raises falls back and verifies (the backup bytes are unchanged); both forms failing names both; `query_only` blocks writes.
