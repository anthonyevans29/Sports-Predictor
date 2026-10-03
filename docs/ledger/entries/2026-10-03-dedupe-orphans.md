**2026-10-03 — NCAA re-key residue (ARCHITECT): the apply had re-keyed 962 in place; `dedupe-matches --orphans` built for 13 kickoff-moved duplicates and 142 stale orphans; the summary reports state.**
- **Ruling (verbatim):** "receipt in. (1) The apply DID re-key 962 rows in place (prev ids carried); its summary printed "merged 0" — fix the reporting. (2) Residue: 13 window duplicates where the kickoff moved >12h (twin test too tight for provider time corrections: widen to same home+away within 48h when one row is stale-scheduled and the other has a live id), and 142 stale SCHEDULED rows >6h past kickoff with no result — orphans under retired ids (Georgia@Alabama 32738 sid 22194 → provider NOT FOUND). Add `dedupe-matches --orphans` dry-run/apply: resolve each stale row's sid at the provider; NOT FOUND + a live twin → merge; NOT FOUND + no twin → mark status=stale_orphan (never delete). Receipt first. Georgia@Alabama must resolve to its live id before next Saturday."
- **Receipt facts (laptop, ncaa_rekey_receipt):** 962 rows carry `_prev`; 13 duplicates in the window more than 12h apart; 142 stale SCHEDULED rows more than 6h past kickoff with no result; Georgia@Alabama row 32738 (sid 22194) is NOT FOUND at the provider.
- **(1) Reporting:**
  - Summaries print state before and after (rows, deleted, carrying `_prev`, stale orphans, re-keys by provenance). A 0-pair run states the rows were already re-keyed.
  - Re-keys now log `<source>_rekeys` {from, to, via, at}, so who re-keyed is readable from the row. Rows re-keyed before this log show as "pre-log".
- **(2) `--orphans`:** the twin test is widened to 48h for this path only, where the provider supplies the live-id truth. The 12h `find_pairs` is unchanged.
  - NOT FOUND + one live twin → merge, whichever row is older keeping the references. If the stale row is the newer one, the live row keeps its own state and id.
  - NOT FOUND + no twin: before marking, the provider's games on the row's date ±2d are searched for the same home AND away. Exactly one game, with its id held by no row → RELINK in place. This is how Georgia@Alabama reaches its live id when the provider lists the game.
  - Only when the provider has no game for the pair is the row marked `STALE_ORPHAN`. It is never deleted and never exported.
  - Lookup errors stay UNRESOLVED (law 4). Ambiguous, swapped, held-elsewhere and already-claimed cases are refused and reported.
- **Interpretation recorded for review:** the relink step goes beyond the ruling's two branches. It serves "Georgia@Alabama must resolve to its live id": an orphan mark alone would leave the game with no row at all.
- **Operator sequence:**
  1. `dedupe-matches --competition NCAA --orphans` (dry-run receipt, paste);
  2. on the architect's go, `.backup`, then `dedupe-matches --competition NCAA --orphans --apply --backup PATH`;
  3. `sync-matches NCAA` (brings results for the live-resync rows);
  4. `export-fixtures --competition NCAA` (stale orphans excluded, counted).
