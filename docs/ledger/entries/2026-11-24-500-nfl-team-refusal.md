**2026-11-24 — the NFL-team refusal: a college listing either of whose teams holds a membership of the NFL competition is refused at create and at update, counted with its id, never stored (addendum 500 Q9 and item 3(a); the finding 493 item 2(d); #1108).**
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
- **What landed:** one check in `IngestionService._upsert_match`, after the unknown-team branch and before the lookup by id, so the update by id, both re-keys (the 12h rule and the placeholder window) and the create are all refused by it. A refused listing writes nothing: no row, no provider_orientation key, no cache entry, no re-key claim.
- **The membership read:** `_nfl_members` reads the team ids holding a competition_teams row of the NFL competition, in any season, once per run (sync_matches' prefetch cache). Outside the college competition the set is empty and no query runs. No new constant.
- **The count line:** `nfl_team_refused N: <listing ids>` (service.nfl_team_refused_line), printed by sync-matches only when N > 0, also counted in `skipped`. The admin job's summary carries it; sp_run.sync_counts puts `nfl_team_refused` {n, ids} on a step's receipt (every such line adds); the laptop routine echoes it under step 9.
- **Not in this PR:** no row is deleted, rewritten or retired. Match 66178 and the two memberships are retired later by the architect's OPERATOR ONLY block, after this rule is on main (Q9). refresh-by-id, sync-teams, the adapter, the exports and --match-ids are unchanged. NCAA has no model: no prediction output changes, no gate applies.
- **Choices named for the architect:**
  - Any season of the NFL competition counts (Q9 names none; item 4 counts "over every season"). Pinned by a test with a 2092 NFL membership.
  - The line names the listing's provider id, not the stored match id: a create refusal has no match id, so 66178 shows on the line by its provider id.
  - The check sits after the unknown-team branch. A listing with one NFL member and one team not in the DB is refused on the existing skipped-listing line, not on `nfl_team_refused`, and 297 C's mismatch path for it is unchanged.
  - NEEDS A RULING: the check runs before the lookup by id, so a listing naming an NFL member, found against a stored college row whose pair differs, no longer writes 297 C(ii)'s `provider_orientation=mismatch` key on that row or lists it under `teams_mismatch_refused`. sync_odds_nfl skips only rows carrying that key. Whether the key is still written there (Q9's "never stored" covers the listing; 297 C(ii) records what the listing says about our row) is the architect's call; this PR does not write it.
  - refresh-by-id updates stored SCHEDULED college rows by their own id with no membership check. This PR reads Q9's "a listing ... at update" as the sync's upsert alone; whether "at update" reaches refresh-by-id is the architect's call. Exposure today: 66178 is FINISHED, so that path does not select it.
  - If the placeholder team (team 1636, provider id 345) held a membership of the NFL competition, every college listing still naming it would be refused. That is a database read for the architect's block, not one this PR makes.
  - sync-matches --match-ids on a stored row refused by this rule prints the row under "not in the provider's answer" (STRICT, exit 1 as before): `nfl_team_refused` holds listing ids, which `_strict_split` does not read. No closing chain names college games.
- **Tests:** tests/test_nfl_team_refusal.py (18; every fixture team holds a college membership, the NFL-member ones the 66178 shape), plus one in tests/test_sync_counts_scores_by_team.py and one in tests/test_laptop_routine.py. Nothing run on either machine.
