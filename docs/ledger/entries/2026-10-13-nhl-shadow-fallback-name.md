**2026-10-13 — RULED + BUILT (ARCHITECT 2026-10-13 17:15 ET, addendum 63 item 2, #508): a hockey shadow whose walk took the goal-margin fallback is not v7, and the grade never pools it with v7. PR #509.**
- **The finding (the operator's review, attributed to him; read against the files and the code by the architect, addendum 63 item 1):** "the host's shadow file of 16:01Z says so itself, in its fit block: xg_updates 0, goal_margin_fallbacks 2879, xg_model "unavailable". The laptop's: xg_updates 2879. Both carry model_version nhl_elo_v7_xg_margin_no_na. The host's number is a different model under the same name."
- **Ruling (verbatim):** "A shadow run whose fit took the goal-margin fallback for any game is not v7. Its model_version reads nhl_elo_v7_goal_margin_fallback, on the file's header and on every row, and the fit block stays as it is. nhl-shadow-grade never pools a fallback file with a v7 file: it grades each name on its own and says which it graded." Small; a PR of its own. "The hold stands: the host's shadow is not read before the cutover, and NHL makes no call either way."
- **As built:**
  - `shadow_name(fit_block)` decides the name from the fit block. One fallback game is enough. A fit block with no count reads 0.
  - The name goes on the header and every row. A fallback file carries `not_v7`, and the export prints it.
  - The grade puts fallback calls on their own line, never pooled with v7's. It prints the calls graded under each name, on the console and in RESULTS.md.
- **Readings put to the architect in the PR (each one function if read otherwise):**
  1. No fit at all still names `nhl_elo_v1` with v1's numbers (addendum 49, on main since 5540adb). The host's 16:01Z file is that case. Production v1.3.0 predates addendum 49, so the host still writes v7's name.
  2. `gate_verdict` is unchanged on a fallback file: v7's declaration includes the fallback to goals (docs/specs/nhl-xg-v7.md, v6's rule).
  3. The fit block decides on the grade too, for older v7-named files.
- Closes #508.
