## 2026-10-06 (#296: host receipts carry the running release; deploy prints the exact migration command — ARCHITECT)
- `sp_common._git` passes `safe.directory` for the checkout. The host checkout is root-installed and the units run as `sp`, so git refused it ("dubious ownership"), `running_release()` returned None, and no receipt carried a release (cutover-readiness criterion (b)). A receipt whose release is still null now carries `release_error` with git's own message.
- `sp_deploy` prints, for each new migration, the exact by-hand command: as `sp`, with host.env loaded, `sp_backup.py daily &&` the migration.
- Tests: `test_running_release_reads_a_checkout_owned_by_another_user`, `test_a_null_release_carries_its_reason`, `test_deploy_prints_the_exact_migration_command`.
