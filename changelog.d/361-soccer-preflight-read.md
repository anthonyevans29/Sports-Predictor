## 2026-10-08 (#361: soccer-expansion-v1 first preflight read; ledger only)
- Ledger note, nothing built. The architect read the first `soccer-expansion-gate --preflight` (laptop, c3a3744).
- The PL backtest is identical before and after #326.
- F3 placements are confirmed for the test seasons.
- 2023/24 is stored for none of the five leagues, so the run would refuse today. The operator syncs it (teams, then matches) and ingests the football-data closes for the ten test league-seasons.
- The one run follows the architect's read of the second preflight, not before Friday morning.
- The 2023/24 backfill joins the soccer-refresh pot: Monday's refresh drift line is read with that in mind.
