## 2026-10-26 (#695: 691-flip-copy-private — ARCHITECT 2026-10-26 12:20 / 13:00 ET: the flip's host.env copy under #682's rule; a scrub-plan read error is a receipted refusal, #693)
- deploy/hosting/sp_cutover.py `step_flip`:
  - `host.env.pre-cutover-<ts>` was made with `shutil.copy2`. It is now created through `_write_private` (#682): 0600 with O_EXCL before any byte is written, then host.env's owner (as root) and mode through the descriptor, with copy2's times kept.
  - The temporary name `.host.env.cutover-tmp` is created the same way. A stale one is removed first, never written into.
  - A copy name taken in the race is refused, never overwritten. A copy or rewrite that cannot be written is a receipted refusal, with host.env as it was.
- deploy/hosting/sp_cutover.py `install` (#693, Codex round 5 on #682): `_scrub_plan`'s read errors are a receipted install refusal ("the .env settings could not be read … nothing installed"), on the in-process path and the root path, never a traceback.
- docs/specs/h2-cutover-runbook.md: the step table's flip and install rows say it.
- Tests: tests/test_h2_cutover.py `test_691_*` and `test_693_*`. Closes #691 and #693. No bar moves.
- Codex round 1 on #695 (three P2), fixed: the flip rewrites host.env from the bytes it read (surrogateescape both ways), so every other line is byte-identical whatever the locale, and a host.env the post-check cannot decode stops the flip before any write; a failed cleanup of the temporary name never hides the receipted refusal; an undecodable `.env` in the scrub plan is a receipted install refusal like an `OSError`.
