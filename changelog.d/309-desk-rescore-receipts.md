## 2026-10-06 (#309: desk-rescore-receipts — ARCHITECT rulings recorded)
- `desk-rescore` writes its receipt into `docs/receipts/` (default `desk-rescore-<UTC stamp>.md`; `--out` to name it). It never writes under `data/` and never overwrites: the file is created exclusively.
- Recorded rulings:
  - An edited copy of a migration is a new migration.
  - The migration-plan lane is closed (#305 at 00eac85).
  - The 10-06 K-track receipt stays as partial-window evidence. A FINAL receipt is re-run after 10-08 and committed beside it.
