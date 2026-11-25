**2026-11-24 — the NFL-team refusal: a college listing either of whose teams holds a membership of the NFL competition is refused at create and at update, counted with its id, never stored; a stored row of its season whose pair it names neither way takes 297 C(ii)'s mismatch key, and the placeholder team is exempt (addendum 500 Q9 and item 3(a); addendum 527 item 1; the finding 493 item 2(d); #1108).**
- **Ruling (500 item 1(c)), verbatim:**
  >    (c) MATCH 66178 IS THE PROVIDER'S ERROR, read by id: under the college league, stage FBS,
  >        season 2026, the same game id served one NFL game when we stored it and serves another
  >        NFL game today. Our row copies a real NFL game that the NFL competition already holds
  >        (match 15191, same kickoff). Its two teams carry a 2026 college membership they should
  >        not have.
- **Ruling (500 Q9), verbatim:**
  >    Q9. DONE TODAY (item 1(c)). And a membership does not tell such a row apart: the bad row's own
  >        teams hold one. THE RULE: in the college competition, a listing either of whose teams
  >        holds a membership of the NFL competition is refused at create and at update, counted
  >        with its id, never stored. Match 66178 and the two memberships are retired by my
  >        OPERATOR ONLY block after that rule is on main, by a reviewed write, never by hand SQL.
- **Ruling (500 item 3(a)), verbatim:**
  >    (a) THE NFL-TEAM REFUSAL of Q9, with its count line: a reviewable head by Tuesday 2026-12-08.
- **Ruling (527 item 1), verbatim:**
  > 1. #1123 (THE NFL-TEAM REFUSAL) AT 6d2ee27b, YOUR TEN, the body read whole:
  >    1 and 10  WRITE THE KEY, FOR mismatch ONLY. Q9's "never stored" is about the listing. 297
  >        C(ii)'s key is a fact about OUR row: its id no longer serves its pair. So a refused
  >        listing found by id against a stored row whose pair differs writes that row's mismatch
  >        key and lists it as a mismatch refusal, as main does, and stores nothing of the listing.
  >        A refused listing naming the stored pair or its reverse leaves the key as it is, as you
  >        built: that is the 66178 shape alone, and those rows are retired by my block.
  >    2   ANY SEASON, as built.
  >    3   YES, add it: the listing's id, and the stored match id beside it where a row carries it.
  >    4   AS BUILT. The not-in-the-DB path refuses it first and nothing is stored either way.
  >    5   refresh-by-id IS NOT REACHED. The only rows it could touch are of the 66178 shape, and my
  >        block retires every one this morning's count finds. That answers the review's second P1.
  >    6   NOT THIS PR. Open one Issue for it: sync-teams can link an NFL member to the college
  >        competition again. I rule it when I write the retirement block.
  >    7   THE PLACEHOLDER TEAM IS EXEMPT: the refusal never reads the placeholder team's own
  >        memberships. A listing is refused for a real team's NFL membership and for nothing
  >        else. Pin it with a test in which the placeholder holds an NFL membership.
  >    8 and 9  AS BUILT.
- **What landed:** one check in `IngestionService._upsert_match`, after the unknown-team branch and before the lookup by id, so the update by id, both re-keys (the 12h rule and the placeholder window) and the create are all refused by it. A refused listing writes nothing of the listing: no score, status, kickoff, team, cache entry or re-key claim.
- **The key (ruled 527 item 1, 1 and 10: "WRITE THE KEY, FOR mismatch ONLY"):** a refused listing found by id against the stored row of its own season (`_same_season_row`, the row the refusal already reads) whose pair the listing names neither way writes 297 C(ii)'s `provider_orientation=mismatch` key on that row through `score_orientation.with_orientation_key` (main's MISMATCH write), and the row is listed on `teams_mismatch_refused`, as main does. `skipped` counts the listing once. A refused listing naming the stored pair or its reverse leaves the key as it is. No row the re-keys find (id history, natural key) is reached.
- **The placeholder (ruled 527 item 1, 7: "THE PLACEHOLDER TEAM IS EXEMPT"):** a listed side whose team is the provider's TBD team is never checked against the NFL members; only a real team's NFL membership refuses, and the warning names only the real team(s). The placeholder is identified as #1119's fill identifies it: the team's own provider id of the listing's source, through `placeholder.is_placeholder_team`. `src/ingestion/placeholder.py` is #1119's file at 611d5f02, byte for byte, so the two PRs' hunks there are identical.
- **The membership read:** `_nfl_members` reads the team ids holding a competition_teams row of the NFL competition, in any season, once per run (sync_matches' prefetch cache). Outside the college competition the set is empty and no query runs. No new constant.
- **The count line (ruled 527 item 1, 3: "YES, add it"):** `nfl_team_refused N: <listing id> (match <stored id>), <listing id>, ...` (service.nfl_team_refused_line), the stored match id beside a listing id where a row of its season carries it, printed by sync-matches only when N > 0. N counts the listings. `SyncResult.nfl_team_refused` stays the listing ids; `SyncResult.nfl_team_refused_match` is beside it (same index, None where no row carries the id). The admin job's summary carries the line (its --seasons block keeps each match id beside its own listing id); sp_run.sync_counts puts `nfl_team_refused` {n, ids, matches} on a step's receipt (`ids` the listing ids, `matches` beside them; every such line adds); the laptop routine echoes it under step 9.
- **Not in this PR:** no row is deleted or retired; beyond 297 C(ii)'s mismatch key on a stored row whose pair the refused listing names neither way (527 item 1, 1 and 10), no stored row is written. Match 66178 and the two memberships are retired later by the architect's OPERATOR ONLY block, after this rule is on main (Q9). refresh-by-id, sync-teams, the adapter and the exports are unchanged. NCAA has no model: no prediction output changes, no gate applies.
- **The ten choices, ruled (527 item 1):**
  - 1 and 10, ruled (527): write the mismatch key, for `mismatch` only (above). The same pair or its reverse leaves the key as it is.
  - 2, ruled (527): any season of the NFL competition counts, as built. Pinned by a test with a 2092 NFL membership.
  - 3, ruled (527): the stored match id beside the listing id on the line (above).
  - 4, ruled (527): as built. The check sits after the unknown-team branch; a listing with one NFL member and one team not in the DB is refused first on the existing skipped-listing line, and nothing is stored either way.
  - 5, ruled (527): refresh-by-id is not reached, as built. The rows it could touch are of the 66178 shape, which the architect's block retires.
  - 6, ruled (527): not this PR. sync-teams can link an NFL member to the college competition again: Issue #1127, which the architect rules with the retirement block.
  - 7, ruled (527): the placeholder team is exempt (above). Pinned by tests in which the placeholder holds an NFL membership.
  - 8, ruled (527): as built. sync-matches --match-ids on a stored row refused by this rule: the row of the listing's season carrying the listing's id is printed on Q9's own STRICT REFUSED line (`SyncResult.nfl_team_refused_rows`), exit 1; a row that took the mismatch key is on main's REFUSED line, as main prints it. A row the re-keys would have claimed is not looked up, so it still prints under "not in the provider's answer".
  - 9, ruled (527): as built. A refused listing of unknown season (or one whose id only a stored row with no season year carries) is not added to `provider_id_season_unknown`; its id is on `nfl_team_refused`, and nothing is written either way.
- **Review round 1 (#1123):** Codex P2 fixed: sync-matches --match-ids STRICT prints a named same-season row refused by Q9 on its own REFUSED line (`SyncResult.nfl_team_refused_rows`), never as "not in the provider's answer". The first Codex P1 (write 297 C(ii)'s key on the stored row, thread 4687970461): ruled by 527 item 1 (1 and 10) and built in the 527 fix round. The second Codex P1 (apply the refusal to refresh-by-id, thread 4687970472): answered by 527 item 5, "refresh-by-id IS NOT REACHED"; not changed.
- **Fix round (527 item 3: "apply items 1 and 2 as one fix round on each PR, with its review"):** items 1 and 10, 3 and 7 above; the head keeps the 2026-12-08 date.
- **Tests:** tests/test_nfl_team_refusal.py (30; every fixture team holds a college membership, the NFL-member ones the 66178 shape; the placeholder fixture holds an NFL membership), plus two in tests/test_sync_counts_scores_by_team.py and one in tests/test_laptop_routine.py. Nothing run on either machine.
