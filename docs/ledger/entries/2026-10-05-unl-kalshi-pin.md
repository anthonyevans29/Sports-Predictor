**2026-10-05 — RULED + BUILT (ARCHITECT): UNL pins KXUEFANLGAME; CONCACAF series reserved for CNL.**
- **Ruling (verbatim):** "UNL Kalshi discovery refused on 2 candidates — KXUEFANLGAME and KXCONCACAFNLGAME. RULED: UNL pins KXUEFANLGAME (the competition is UEFA's); map the CONCACAF series to CNL for later. Make the pin the adapter default for UNL so the window chain doesn't need the flag."
- **Built:** `KalshiAdapter.SOCCER_GAME_SERIES` now maps UNL → `KXUEFANLGAME`. `sync-kalshi-soccer --competition UNL` resolves it as "mapped", with no `/series` call and no `--series` flag, so the window chain's UNL step is unchanged.
- `SOCCER_SERIES_RESERVED = {"CNL": "KXCONCACAFNLGAME"}` records the CNL mapping. A CNL sync refuses and names it until CNL is wired (#284).
- The discovery mechanism stays, with no competition on it.
- **Unchanged:** the matcher's refusals, the spread cap and the venue fee table. UNL's fee M stays at the conservative default (no maker cost assumed) until receipted.
