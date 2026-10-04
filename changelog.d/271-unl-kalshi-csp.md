## 2026-10-04 (#271: UNL Kalshi series discovered and stored; published-Cockpit CSP noted, local launcher)
- **`sync-kalshi-soccer --competition UNL`:** the soccer sync knew only `KXEPLGAME`. UNL has Kalshi markets (operator fills exist) but no receipted ticker.
  - `KalshiAdapter.resolve_soccer_series` discovers the UNL series from Kalshi's own `/series` listing (keywords "nations league"; game-winner series only, i.e. tickers ending `GAME` like every wired series).
  - Exactly one match is required, else it refuses and lists the candidates (law 1: never a guessed ticker).
  - The legs are stored like PL's (Home/Away/Tie snapshots, same gates), so `export-fixtures --competition UNL` and the venue engine read UNL three-way sets.
  - `--series` pins the ticker once receipted, and the receipt line names how the series was resolved.
  - UNL is added to the window chain's Kalshi table; the CI pin now covers mapped plus discoverable series.
- **Published Cockpit:** its CSP blocks api.github.com, so "Load latest from host" fails there. `docs/specs/exports-mirror.md` says so, and the new `scripts/cockpit_local.py` serves a saved copy of the published artifact (or the repo copy, flagged) on 127.0.0.1, where the control works. The ledger is per origin: move it with Export/Import and keep the same port.
- tests/test_unl_kalshi_discovery.py (2): discovery exactly-one / refused (2 or 0) / override / unmapped; UNL legs stored as a three-way set with quotes (Kalshi mocked).
