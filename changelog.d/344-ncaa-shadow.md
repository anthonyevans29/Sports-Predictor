## 2026-10-07 (#344: NCAA shadow — ARCHITECT, addendum 6 item 1)
- New `export-ncaa-predictions` writes `exports/ncaa_shadow_<stamp>.json`: `ncaa_elo_v1r` (v1, constants untouched) for every FBS game in the next 36h.
  - Each row has `engine: model_shadow`, `competition: NCAA`, `family: NCAAF`, and `gate_verdict` "UNGATED — shadow only" until the registry records a verdict.
  - The fixtures market block sits beside the prediction.
  - It is never a call, never a venue input and never in the ledger.
- It REFUSES (exit 2) until `ncaa-elo-v1r` is declared with its `neutral_site_rule` and the CFBD side table covers 95% or more of the stream in both seasons.
- New `ncaa-shadow-grade` grades the last row before kickoff: results (hit rate, log-loss, Brier, on the CFBD score where labelled) and model-vs-close. It is labelled NOT gate evidence.
- Codex on #344: the declaration must also freeze `constants` = v1's untouched values; files are second-stamped and created exclusively; grading skips (and counts) an artifact row whose teams / kickoff / competition are not the match's; every grade line says NOT gate evidence.
- Not on any chain; spec docs/specs/ncaa-shadow.md (#343).
