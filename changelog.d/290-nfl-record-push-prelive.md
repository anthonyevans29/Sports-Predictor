## 2026-10-05 (#290: NFL season record: ties are pushes; pre-live rows listed separately, never pooled — ARCHITECT)
- `export_nfl_results`: a tie is a PUSH (`result "T"`, `push: true`, `top_pick_hit: null`), out of the hit denominator and counted separately. Log loss keeps the frozen gate's tie convention.
- The season record starts at `live_since` 2026-09-22 (Week 3). Preseason and earlier rows sit under `pre_live` with their own record.
- `record` gains `live_since`, `decided` and `pushes`. Contract: `results`/`count` are live rows only.
- Test: `test_ties_are_pushes_and_pre_live_rows_are_never_pooled`.
- Review fixes (Codex on #290): the `export-nfl-results` receipt prints hits over DECIDED games with pushes shown separately (`W6 1/1 +1P`), prints the pre-live record on its own line, and `--match` finds pre-live rows ("IN the file (pre-live, not in the season record)"). The season-choice finding was already fixed via #289.
