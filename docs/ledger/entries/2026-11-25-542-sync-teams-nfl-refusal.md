**2026-11-25 — the NFL member at the team listing: in the college competition, sync-teams refuses a listing whose stored team holds a membership of the NFL competition, counted on its own line with the provider's team id; no membership stored, the team's row untouched, nothing removed, the placeholder exempt by its primary id (addendum 542 item 1(a) and (b); addendum 545 item 1 Q6 and item 2, PR-A; #1127).**
- **Ruling (542 item 1(a)), verbatim:**

  >    (a) THE RULE IS 500 Q9's, AT THE TEAM LISTING: in the college competition, sync-teams does not
  >        link a team that holds a membership of the NFL competition. The listing is refused,
  >        counted on its own receipt line with the provider's team id, and no membership is stored.
  >        The team's own row is not touched: it is the NFL's club and stays so.

- **Ruling (542 item 1(b)), verbatim:**

  >    (b) THE SYNC NEVER REMOVES. A membership already stored is not taken away by sync-teams, on
  >        any run. Taking it away is the retirement write's work alone, so that nothing is deleted
  >        by a step that runs every morning.

- **Ruling (545 item 1 Q6), verbatim:**

  >    Q6. YES: the placeholder is exempt, by its primary id, in PR-A and in the command's set,
  >        each pinned with a test in which the placeholder holds an NFL membership (527 item 1(7)).

- **Ruling (545 item 2, PR-A), verbatim:**

  >    PR-A, 542 item 1(a) alone (stop rule (5)): a reviewable head by Friday 2026-12-04 12:00 ET. It
  >        stops the list growing: two clubs on Tuesday, six on Wednesday.

- **What landed:**
  - `IngestionService.sync_teams`, for the college competition ("NCAA") only: before any write for a listed team, the stored team the listing names is resolved by the existing lookup (`_find_team_by_source`, an id a merge recorded included). If it holds a membership of the NFL competition in any season (`_nfl_members`, #1123's set, read once per run) and it is not the placeholder, the listing is refused (`_nfl_member_listed`): no college membership added, no team created, nothing of the team's row written (name, short name, tla, area, founded, venue, external ids). Its provider team id goes on `SyncResult.nfl_member_team_refused` (listing order) and `skipped` counts it once. A team not stored yet holds no membership and goes on as today.
  - The placeholder (545 Q6): the team whose own provider id of the listing's source (`external_ids[source]`, the primary id) is the provider's TBD team (`placeholder.is_placeholder_team`, "345") is never refused, as #1123's refusal and #1119's fill read it.
  - 542 item 1(b), read from the code: sync_teams never deletes a competition_teams row (`_link_team_to_competition` only adds); a refused team's stored college membership stays, every column unchanged, pinned.
  - The line: `nfl_member_team_refused N: <provider team id>, ...` (service.nfl_member_team_refused_line), printed plainly by sync-teams on its own line right after the `✓ Teams (CODE): ...` summary, only when N > 0; sync_teams' log line carries it too.
  - Readers: the admin job's sync-teams summary (` · nfl_member_team_refused N: ...`); sp_run `NFL_MEMBER_TEAM_REFUSED_LINE`, in `_SYNC_LINES`, and `sync_counts` key `nfl_member_team_refused` {n, ids}, every such line of a step adding; laptop_routine `_COUNT_LINES`, so step 8 (NCAA sync-teams) echoes it and its receipt carries it. TEAMS_LINE and every existing reader unchanged.
  - Outside the college competition nothing changes and no query runs; a college run with no NFL member stored looks each listing up once, as before.
- **Not in this PR:** the retirement command (PR-B, retire-college-nfl-rows, to DEV 3's plan as 545 rules it); no stored row is touched, deleted or rewritten (the six memberships and row 66178 stand until the architect's OPERATOR ONLY block); refresh-by-id and sync-matches unchanged; no stop rule, go_on or chain. NCAA has no model: no prediction output changes, no gate applies.
- **Choices named for the architect:**
  - The refusal also holds on a sync-teams run with no `--season`: such a run links nothing but writes the team's row, and 542 1(a) says the row is not touched.
  - A real NFL member that carries "345" only as an id a merge recorded is no placeholder (545 Q6: "by its primary id") and is refused, pinned.
  - The lookup sync_teams makes for the college competition is handed to `_upsert_team` (a new `found` argument, default unchanged for every other caller), so no listing is looked up twice; the lookup is made only when the NFL competition holds a member.
  - A team listed twice in one run is refused, and counted, once per listing.
  - The admin summary joins the line with " · ", as #1123's sync-matches job does (the names-kept line is joined with a space).
  - One existing test changed: tests/test_sync_teams_historical_names.py `test_memberships_across_two_competitions_of_the_same_sport_count` listed an NFL member in the college competition, the shape now refused; #764's cross-competition rule is pinned from the NFL side instead (an NCAA 2026 membership keeps an NFL 2025 listing's name).
- Nothing here moves a bar, a date or a held timer.
