## 2026-10-02 (#153: NHL v8 declared — train-only fit of scale and k; the 2025 test set retired after it)
- `nhl-backtest --candidate v8`: v7's xG + Elo with the logistic divisor and k fitted by maximum likelihood on 2024 only over the declared grid (56 pairs; tie → (400, 6)); chosen and printed before any 2025 read. Registry `nhl-v8` declared; doc `docs/specs/nhl-xg-v8.md`.
- Doctrine: `registry.RETIRED_TEST_SETS` — after v8 the NHL 2025 test set refuses any declaration or run; later NHL candidates declare 2026-27 (≥ 600 games). `docs/REGISTRY.md` updated. (v6/v7 FAIL records: #239.)
