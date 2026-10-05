**2026-10-05 — RULED + BUILT (ARCHITECT): NFL season record, ties are pushes and pre-live rows are never pooled.**
- **Rulings (verbatim):** "TIES are a PUSH in the season record — neither hit nor miss, excluded from the hit denominator, counted separately; the frozen gate's tie convention is untouched. PRESEASON is EXCLUDED from the season record: the record starts at live_since (Week 3); preseason rows are listed under a separate "pre-live" heading, never pooled."
- **Built (`export_nfl_results`):**
  - A tied row reads `actual.result: "T"`, `graded.push: true`, `top_pick_hit: null`. Its `log_loss` keeps the gate's convention (tie = home loss).
  - `record` carries `live_since`, `games`, `decided` (the hit denominator), `hits` and `pushes`, overall and by week.
  - Rows before `NFL_LIVE_SINCE` (2026-09-22, Week 3), or with a preseason stage, move to `pre_live` (its own rows, count and record) and leave `results`.
- **Export contract:** `results`/`count` now hold live rows only. `pre_live` is new. Tied rows carry `push`.
- **Unchanged:** the gate, its tie convention, log loss, and every prediction.
- **Operator:** run `python cli.py export-nfl-results` after merge; the live record is Week 3 onward.
