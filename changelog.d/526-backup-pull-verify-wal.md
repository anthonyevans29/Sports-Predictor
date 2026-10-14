## 2026-10-14 (#526: backup-pull-verify-wal — ARCHITECT addendum 68 item 2, #517)
- deploy/hosting/pull_backup.py: the verify opens the pulled COPY with `?mode=ro&immutable=1`, through the new `sp_common.copy_integrity`.
  - The laptop's (macOS) SQLite cannot open a WAL-mode copy with no -shm beside it as mode=ro ("unable to open database file").
  - Immutable reads the copy as it is and creates nothing beside it.
  - The live DB is never opened immutable: `ro_connect` stays mode=ro (#340).
- Tests: tests/test_hosting_pack.py (1 new):
  - a WAL `.backup` copy with no sidecars verifies with integrity ok through the immutable path, and the folder is left as found (the final file and its .sha256);
  - `ro_connect` holds no immutable open.
  - On the old mode=ro verify it fails (Linux would leave the -shm and -wal).
