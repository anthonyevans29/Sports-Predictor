**2026-10-17 — RULED + BUILT (ARCHITECT 2026-10-17, addendum 112 item 5 and addendum 115 item 1; #426, #358): Hawai'i becomes one team row once the merge runs. The unescape at ingest is checked and tested, and the merge-teams block is written, not run. PR #PRNUM.**
- **Ruling (ARCHITECT 2026-10-17 10:40 ET, addendum 112 item 5), verbatim:** "#358 + #426 — Hawai'i as two team rows (an HTML-escaped name) and under two provider ids. RULED: one receipt listing both rows, their ids, external_ids and every match that references each; then a team merge through the existing merge path (keeper the row the 2026 schedule references), with the HTML-unescape fixed at ingest so it cannot recur. The merge runs on the laptop in a block with a backup, on my word — the PR carries the dry run."
- **The keeper (ARCHITECT 2026-10-17 11:30 ET, addendum 115 item 1; it overrides the keeper phrase above), verbatim:** "#358/#426 keeper — addendum 44 stands: the LOWER id keeps its row (1385, provider id 59). My phrase in addendum 112 ("the row the 2026 schedule references") is withdrawn: it was ambiguous on a split schedule and a standing rule is not re-ruled by a careless sentence. The merge moves 1744's nine 2026 games onto 1385 and carries provider id 901 into 1385's external_ids beside 59, so both provider ids resolve to one row from then on; the HTML-unescape at ingest stops a third row. `merge-teams` runs as built. Receipt first, as ruled."
- **The receipt:** the two blocks are posted on #426 (Block A, the rows and every match on each, read-only; Block B, the provider's 2026 listing, one call). Their consoles are not there yet: the operator pastes both on #426, verbatim. #358 points to it.
- **The unescape at ingest (built, read first):**
  - The one place this provider's team names enter is `APIAmericanFootballAdapter.list_teams` (src/adapters/api_american_football.py:205). It has unescaped them since #465 (addendum 44 item 3).
  - `sync-teams` writes, through `_upsert_team` (src/ingestion/service.py:256 on update, 273-284 on create), only what `list_teams` returns. The games listing (`_parse_games`) carries team ids, never a name to store. No other path writes a team row for this provider.
  - So no second unescape was added. The comment at that line now names it as the one place.
  - Not moved into the shared write: there it would also rename, at their next `sync-teams`, any stored name from api_football, api_hockey, mlb_stats_api or intl-sync that carries an entity, and a Kalshi pin or alias may be keyed on that name. Those providers' names are read raw today (src/adapters/api_football.py:295, api_hockey.py:122, mlb_stats_api.py:154, src/ingestion/intl_history.py:325 and 337). src/ingestion/mlb_apisports.py:234 writes MLB rows directly. The dry run's line "stored team names carrying an HTML entity, by sport" says whether any exist. No stored name is touched by this PR.
  - A stored row is found by its provider id, never by its name (`_find_team_by_source`, service.py:289-304). An unescaped name cannot miss its row and make a new one.
  - What stops a third row is the merge itself: after it, a listing carrying 59 or 901 finds 1385 (`team_merge.source_ids`, src/ingestion/team_merge.py:46-50). A listing found by 901 never replaces 1385's own id (service.py:263-268). The unescape keeps the escaped name off the row.
- **The merge, as built (merge-teams unchanged):**
  - The lower id keeps its row (team_merge.py:213), and a pair named the other way round is refused (254-256).
  - 901 is carried: 1385's external_ids get `api_american_football_also: ["901"]` beside `api_american_football: "59"`, and a `merged_from` entry with 1744's external_ids and the time (team_merge.py:65-72, written at 291-292).
  - Every reference read from the live DB is re-pointed (288-290), `matches.home_team_id` and `matches.away_team_id` among them (src/db/schema.py:156-157). The apply then checks that no reference names 1744 (293-300) and deletes it (301).
  - A same NCAA 2026 membership is dropped and counted (addendum 50 item 5(b)). A unique-table conflict, or a reference the command does not know, refuses the pair and names the table.
- **The laptop block (operator).** Part 1 runs now: it takes the backup, then the dry run. Its console is pasted on the PR before merge.

  ```bash
  cd ~/Downloads/sports_predictor
  if [ -f data/sports.db ]; then
    B="$HOME/backups/sports_$(date +%F)_premerge.db"
    sqlite3 data/sports.db ".backup $B" && ls -l "$B" && python cli.py merge-teams
  else
    echo "no database at $PWD/data/sports.db: nothing run (law 5)"
  fi
  ```

  Part 2 runs only on the architect's word, and only after the Block A and Block B consoles are on #426 and he has read them and the dry run (addendum 115: "Receipt first, as ruled"). Whether Part 2 also waits until Issue #585 (the finding below) is repaired is the architect's ruling: the merge itself does not trigger it, only a later `sync-teams` for a season 1385 has no membership in. It takes its own backup just before: `--backup` refuses a file whose teams count differs from the live DB's. It merges the one pair, then runs the dry run again as the after-receipt.

  ```bash
  cd ~/Downloads/sports_predictor
  if [ -f data/sports.db ]; then
    B="$HOME/backups/sports_$(date +%F)_premerge_$(date +%H%M).db"
    sqlite3 data/sports.db ".backup $B" && ls -l "$B" \
      && python cli.py merge-teams --apply --pair 1385:1744 --backup "$B" \
      && python cli.py merge-teams
  else
    echo "no database at $PWD/data/sports.db: nothing run (law 5)"
  fi
  ```

  - The backup line is docs/CLI.md's, with two changes:
    - The file has an event name (`_premerge`, as sp_backup.py names its `_pre…` backups, and as sports_preorphans.db was), so it does not overwrite the day's daily backup.
    - The path is `$HOME`: the shell does not expand `~` inside double quotes.
  - The pair is the one the ruling names and the dry run is expected to print (`[candidate] --pair 1385:1744 · NFL 'hawaii'`). If the dry run prints the pair as `[left]`, Part 2 does not run, and the architect reads why.
- **Expected after the apply:** `MERGED team 1744 into 1385`, with 1385's external_ids holding 59 and `api_american_football_also` ["901"]. Block A of the #426 receipt, run again, no longer lists 1744. ncaa-elo-v2's stream already reads 1744 as 1385 (J2, src/walters/ncaa_backtest.py:489-505, applied at 791), so the merge should leave its walked stream as it is.
- **Tests (tests/test_team_merge.py, 2 new):** the receipt's escaped name goes through the real adapter and the real `sync_teams` on a scratch file. It is stored as "Hawai'i", and a second sync of id 901 makes no row. The laptop's two rows resync by id with no new row. After the apply (901 beside 59, games moved), a sync carrying both ids finds the kept row for each: created 0, teams one fewer. Both tests fail with the adapter's unescape removed.
- **Finding, read while building (left as it is in this PR; for the architect; Issue #585):** after the merge, a `/teams` listing that carries both 59 and 901 in a season 1385 is not yet a member of makes `sync-teams` raise `IntegrityError: UNIQUE constraint failed: competition_teams...`. The whole competition's team sync rolls back.
  - Why: both ids find 1385, and `_link_team_to_competition` (service.py:307-312) adds the same membership twice in one session. SessionLocal's autoflush is off, so the second `s.get` does not see the first.
  - Reproduced on a scratch DB with season 2027.
  - 2026 is not affected: after the merge 1385 holds its 2026 membership.
  - Block A's memberships show whether the provider listed both ids in one season: both rows a member of NCAA 2026 means it did.
- #426 and #358 stay open until the merge has run on the laptop (addendum 44).
