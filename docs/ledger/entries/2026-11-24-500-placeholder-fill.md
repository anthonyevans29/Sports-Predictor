**2026-11-24 — The placeholder fill, built (ARCHITECT 2026-11-24, addendum 500 Q1 to Q5 and Q10; 493 item 2(c); the fix round, ARCHITECT 2026-11-25, addendum 527 item 2; Refs #1108): in the sync's update by id, in the college competition (527 item 2 answer 2), a stored row whose differing side(s) are the provider's placeholder team (provider id 345) takes the listed team(s), the other side equal, on the same pass, listed on its own receipt line; a flip and another game stay refused.**
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

- **Ruling (527 item 2), verbatim:**

  > 2. #1119 (THE FILL) AT 611d5f02, YOUR SIX:
  >    1   A HALF-FILL IS A FILL: RULE IT IN. (P,P) listed as (X,P) meets Q1's words side by side,
  >        and a bracket names its teams one at a time. The row then reads as the provider's does.
  >    2   THE COLLEGE COMPETITION ONLY, for now: the narrower one line. The finding and every
  >        counted row are college's. If a count of mine shows a placeholder row of another
  >        competition, I rule that competition in by name.
  >    3   REFUSE ON THE SWAPPED PAIR TOO, as the re-key does. It is the narrower reading.
  >    4   NO STATUS CONDITION, as built. It is what lets a finished placeholder row heal once the
  >        fill has shipped: the window compares the two kickoffs, not the clock.
  >    5   THE ECHO STAYS. A fill that reaches the receipt is the point of "never silent".
  >    6   THE TWIN GUARD IS ITS OWN PR and is not dated yet. DEV 3: a plan for it on #1108, 40 lines
  >        at most, by Wednesday 2026-12-09 17:00 ET: the guard with the date-search half it
  >        needs, from the code, nothing run. The college orphan plan stays unapplied (Q6).

- **What landed:** `placeholder.PLACEHOLDER_TEAM_ID = "345"` and `is_placeholder_team` beside the kickoff's definition (Q2); the pure verdict `score_orientation.placeholder_fill` (Q1; the half-fill a fill, 527 item 2 answer 1); `IngestionService._fill_placeholder`, called once in `_upsert_match`'s update-by-id branch before the unchanged `_scores_by_team` (Q3, Q4); `SyncResult.placeholder_filled` and the line `placeholder_filled N: <match ids>` (sync-matches, both paths, and the admin job), printed only when N > 0. The receipts downstream: sp_run's `_SYNC_LINES` and `sync_counts` (key `placeholder_filled`, {n, ids}, each line adding) put it on a sync step's receipt; the laptop routine keeps it in the step's echo.
- **Refused as today (the unchanged MISMATCH path):** a flip, another game, an unstored filled team, a filled team that is the row's other team, a served kickoff more than PLACEHOLDER_RESOLVE_H from the stored one, and a live row of the season holding the filled pair or its reverse within TWIN_H of the served kickoff (Q5: both imported, and no constant is new; the swapped pair ruled (527 item 2 answer 3), as the re-key reads `same` and `swapped`). Scope: the api_american_football source, the provider whose team 345 is (item 1(a)), where the run builds its pair index (REKEY_SOURCES, the re-key's own condition), and the college competition only, ruled (527 item 2 answer 2): one line, `comp.code not in PLACEHOLDER_REKEY_COMPETITIONS`, the college set ({"NCAA"}) the re-key already holds. A row of another competition of the source (an NFL row holding the team) is refused as main refuses it; another source's team carrying "345" is no placeholder. refresh-by-id untouched (Q4).
- **The half-fill, ruled (527 item 2 answer 1):** a (P,P) row listed (X,P) or (P,X) takes X on the same pass, the kept side the placeholder still, and the pair then reads SAME (the row reads as the provider's does); a later listing naming the second team fills that side as (P,B) to (X,B) does.
- **Q10:** the docstring of tests/test_scores_by_team.py `test_a_placeholder_kickoff_row_keeps_its_own_path` now names the placeholder team as the fill's rule; its body is unchanged.
- **Q6 (the twin guard), ruled (527 item 2 answer 6):** its own PR, not dated yet; DEV 3 plans it on #1108 (40 lines at most, by Wednesday 2026-12-09 17:00 ET, the guard with the date-search half it needs); the college orphan plan stays unapplied (Q6).
- **The choices named for the architect, ruled (527 item 2):** the half-fill is a fill (answer 1); the college competition only (answer 2); the swapped pair refuses too (answer 3); no status condition, as built (answer 4); the echo stays, as built: the fill count is on each sync step's receipt, with no chain-level total, summary mark or digest line (answer 5); the twin guard its own PR (answer 6).
- **Tests of the fix round:** the half-fill both ways then its second team; the TWIN_H boundary for the swapped pair after and before the served kickoff, at TWIN_H + 1h and CANCELLED; the scope unpatched (the real "NCAA" fills; another competition of the source and another source refused). A test of the fill's own rules stands its code in for the college competition through the `college` fixture (PLACEHOLDER_REKEY_COMPETITIONS monkeypatched for that test only); the fill section adds one "NCAA" row, the scope test's.
- **Timing (500 Q1):** the placeholder rows stay refused through 12-04 and 12-05; this build is not hurried into the sync for them (item 3(b): a reviewable head by 2026-12-08; the tag is the architect's). The fix round keeps the 2026-12-08 date (527 item 3).
- Nothing here moves a bar, a date or a held timer.
