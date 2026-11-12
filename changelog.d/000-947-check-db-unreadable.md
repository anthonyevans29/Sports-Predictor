## 2026-11-12 (#000: 947-check-db-unreadable — #942's follow-up (Codex round 3, two P2s): the `--db` fence refuses a data/ root or a `--db` it cannot stat, instead of reading either as absent.)
- **`src/walters/mlb_pitchers_gate.py`, `_data_tree`:** `os.path.lexists(data)` swallowed every `OSError`, so a data/ (or a parent of it) that could not be read read as absent, and no identity check ran. The fix is `os.lstat(data)`:
  - `FileNotFoundError` and `NotADirectoryError` mean nothing is there, as before.
  - Any other `OSError` refuses through the walk's own `unreadable`, naming the path.
- **`check_db`:** `os.stat(--db)` mapped every `OSError` to "no file", so a transient failure skipped the identity comparison. Now:
  - `FileNotFoundError` and `NotADirectoryError` still read as no file, refused below as "no file at".
  - Any other `OSError` refuses with "cannot stat --db … (law 4); nothing read".
- **Test:** `test_947_an_unreadable_data_root_or_db_stat_refuses_and_only_absence_reads_as_absent`. It patches the data/ root's `lstat` and the `--db`'s `stat` to raise `PermissionError`, and pins both refusals. A missing data/, a data/ under a file, and a missing `--db` keep their behaviour. The test fails on main, and reverting either fix alone fails it.
- **Not a verdict change:** each fix only adds a refusal where the fence passed on a path it could not read. Nothing refused today passes.
