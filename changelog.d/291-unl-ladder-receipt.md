## 2026-10-05 (#291: `unl-ladder-receipt`: read-only per-game UNL ladder receipt + the frozen favorite-skew test — ARCHITECT #286)
- New CLI `unl-ladder-receipt` (`src/walters/unl_ladders.py`). Per UNL game after the freeze cutoff it shows the match, legs (bid/ask, spread, two-sided), capture time, series, book probability and favorite gap.
- The sample is the first 30 games qualifying under `docs/specs/unl-venue-skew-test.md`; exclusion reasons are listed. `--skew-test` runs the frozen bootstrap test once the sample is complete. `--out` writes to `docs/receipts/` and refuses `data/`. Read-only.
- Tests: `tests/test_unl_ladder_receipt.py` covers each exclusion reason, the three-leg normalized gap, a deterministic bootstrap (seed 20261005) and the CLI.
