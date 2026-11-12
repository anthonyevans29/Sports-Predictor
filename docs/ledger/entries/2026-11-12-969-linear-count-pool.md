**2026-11-12 — FIXED (#969; ARCHITECT 2026-11-12 17:20 ET, addendum 362 item 4): the bulletin guard's CONTRACT_COUNT and POOL backtracked quadratically, or worse, on long runs (slow, never wrong). Each now reads in linear time and matches exactly what it matched before.**
- **The shapes:**
  - digit runs (CONTRACT_COUNT 15.6 s, POOL 3.4 s);
  - blanks after `contracts` (cubic);
  - underscore runs;
  - repeated `contract_`.
- **Proof of the same strings:** a seeded differential against main's patterns, and curated lines. Every caller reads only whether a pattern matches.
- **Found while building:** CSV_RUN and FRACTION have the same class of defect; filed as #979 (needs-ruling), not in this PR.
