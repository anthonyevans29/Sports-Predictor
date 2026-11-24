**2026-11-24 — The placeholder fill, built (ARCHITECT 2026-11-24, addendum 500 Q1 to Q5 and Q10; 493 item 2(c); Refs #1108): in the sync's update by id, a stored row whose differing side(s) are the provider's placeholder team (provider id 345) takes the listed team(s), the other side equal, on the same pass, listed on its own receipt line; a flip and another game stay refused.**
- **Addendum 500 item 1(a)-(b), verbatim:**

  >    (a) ONE stored placeholder team (our team id 1636; the provider's team id 345).
  >    (b) NINE college rows of 2026 hold it, ALL FCS, all on 2026-12-05: eight with it on one side,
  >        one with it on both (33608). NO FBS ROW HOLDS IT. The FBS rows stored from 12-01 on are
  >        four, each with two named teams. Eight of the nine sit at 04:00Z; 33608 at 19:00Z.

- **Addendum 500 Q1 to Q5, verbatim:**

  >    Q1. YES, A FILL IS A RULED CARVE-OUT, in your words of (b) and no wider: position by position,
  >        every side that differs is the stored placeholder, the other side is equal, each filled
  >        team is stored, is not the placeholder and is not the row's other team. A flip stays
  >        refused (292 item 3(d)); another game stays refused (3(a)). The fill is never silent: its
  >        own receipt line with the match ids. THE PLACEHOLDER ROWS STAY REFUSED THROUGH 12-04 AND
  >        12-05: none is an FBS game, and nothing is hurried into the sync for nine FCS rows.
  >    Q2. ONE ID, 345, held as data in placeholder.py beside the kickoff's definition, never
  >        matched by name. The kickoffs are answered in item 1(b).
  >    Q3. THE SAME PASS: after the fill the pair reads SAME and the unchanged SAME path writes what
  >        it writes today. The test shows the row then holds what a fresh create would, but its id.
  >    Q4. THE UPSERT ALONE. refresh-by-id is not touched and keeps refusing until the sync fills.
  >    Q5. NO NEW CONSTANT: the kickoff window is the placeholder's own (PLACEHOLDER_RESOLVE_H, 24
  >        hours as your plan reads it); the pair-collision window is the dry run's 48 (TWIN_H).

- **Addendum 500 Q10, verbatim:**

  >    Q10. YES to both: this addendum's record supersedes that premise, and the docstring changes
  >        in the fill's PR.

- **What landed:** `placeholder.PLACEHOLDER_TEAM_ID = "345"` and `is_placeholder_team` beside the kickoff's definition (Q2); the pure verdict `score_orientation.placeholder_fill` (Q1); `IngestionService._fill_placeholder`, called once in `_upsert_match`'s update-by-id branch before the unchanged `_scores_by_team` (Q3, Q4); `SyncResult.placeholder_filled` and the line `placeholder_filled N: <match ids>` (sync-matches, both paths, and the admin job), printed only when N > 0. The receipts downstream: sp_run's `_SYNC_LINES` and `sync_counts` (key `placeholder_filled`, {n, ids}, each line adding) put it on a sync step's receipt; the laptop routine keeps it in the step's echo.
- **Refused as today (the unchanged MISMATCH path):** a flip, another game, an unstored filled team, a filled team that is the row's other team, a served kickoff more than PLACEHOLDER_RESOLVE_H from the stored one, and a live row of the season holding the filled pair within TWIN_H of the served kickoff (Q5: both imported, no new constant). Also refused: a (P,P) row listed (X,P) or (P,X), a half-fill that leaves the placeholder on the row, which is not among (b)'s two filled shapes ((P,P) to (X,Y); (P,B) to (X,B)): refused until ruled (law 4; Q1 "no wider"). Scope: the api_american_football source, the provider whose team 345 is (item 1(a)), where the run builds its pair index (REKEY_SOURCES, the re-key's own condition); no competition list, as (b) names none, so an NFL row holding the team fills as a college one does; another source's team carrying "345" is no placeholder. refresh-by-id untouched (Q4).
- **Q10:** the docstring of tests/test_scores_by_team.py `test_a_placeholder_kickoff_row_keeps_its_own_path` now names the placeholder team as the fill's rule; its body is unchanged.
- **Q6 (the twin guard):** not in this PR; judged its own (the date-search arm and its ruled labels need a decision too).
- **For the architect:** whether a (P,P) row listed (X,P) is ever filled (refused here until ruled); the collision check covers the filled pair, not its swap; no status condition (none in the words); the fill count is on each sync step's receipt, with no chain-level total, summary mark or digest line (deploy code, not named by 500).
- **Timing (500 Q1):** the placeholder rows stay refused through 12-04 and 12-05; this build is not hurried into the sync for them (item 3(b): a reviewable head by 2026-12-08; the tag is the architect's).
- Nothing here moves a bar, a date or a held timer.
