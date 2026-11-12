**2026-11-12 — FIXED (#950; ARCHITECT 2026-11-12 10:55 ET, addendum 354 item 2): the deploy's plan was silent when a schema change rode an existing idempotent migration (v1.6.7's poll key; also v1.1.0..v1.2.0 and v1.2.1..v1.2.2).**
- **The rule (354 item 2(a)):** a change to the stored schema ships with a NEW one-shot `migrate_<what>.py` in the same PR, which the plan already lists, orders and prints. It is in CONTRIBUTING.md.
- **The warning (354 item 2(b)):** on a forward deploy where `src/db/schema.py` changed and no new migration is listed, the dry run and the deploy print one `!` line with no command, and the receipt sets `schema_changed_no_migration`.
- **Open (354 item 2(c)):** whether CI refuses such a PR. The feasibility read is in the PR, and the architect rules on it.
