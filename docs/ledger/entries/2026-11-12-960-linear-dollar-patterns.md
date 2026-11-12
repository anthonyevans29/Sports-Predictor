**2026-11-12 — FIXED (#960; ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 4(1)): the shared #817 `DOLLAR` and `USD_WORD`'s digit and usd arms backtracked quadratically on a long run (slow, never wrong). Each now reads in linear time and matches exactly what it matched before.**
- **Proof of the same strings:** a seeded differential against main's patterns (60,000 random lines and 39 curated ones); every caller reads only whether a pattern matches.
- **Found while building:** CONTRACT_COUNT and POOL have the same class of defect; filed as #969 (needs-ruling), not in this PR.
