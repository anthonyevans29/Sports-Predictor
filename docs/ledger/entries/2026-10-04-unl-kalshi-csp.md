**2026-10-04 — UNL Kalshi markets (ARCHITECT): series discovered, not guessed; published-Cockpit CSP blocks api.github.com.**
- **Ruling (verbatim):** "(1) published-artifact CSP blocks api.github.com, so "Load latest from host" fails there; note in docs, consider a local-file Cockpit launcher. (2) sync-kalshi-soccer only discovers KXEPLGAME; UNL has Kalshi markets (fills exist) — discover the UNL series and store them so the venue engine can see UNL ladders. Small."
- **(2) Built:**
  - The UNL series is resolved at run time from Kalshi's `/series` listing (keywords "nations league", game-winner series only). Exactly one candidate is required, else the sync refuses and names the candidates.
  - This build environment cannot reach Kalshi (egress policy), so no ticker was confirmed here and none is hard-coded. The fills fixture's `KXUEFANLGAME` is only the test's example.
  - **The first live run's receipt line ("game series … discovered …") is the confirmation.** Pin it with `--series` if wanted.
  - Legs are stored as PL's are.
  - Fees: `venue.KALSHI_SERIES_BY_COMPETITION` has no UNL entry, so UNL takes the default taker M=1 with NO maker cost assumed (conservative unknowns) until a fee receipt.
  - The Desk's venue-edge policy text still lists "UNL … never"; storing the quotes makes UNL sets visible, and whether UNL becomes venue-edge eligible is a policy ruling, not part of this change.
- **(1) Built:** the doc note, and `scripts/cockpit_local.py` (127.0.0.1-only static server, saved artifact copy via `--html`, per-origin ledger caveat).
