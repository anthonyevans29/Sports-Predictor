## 2026-10-17 (#PRNUM: qb-news-by-id — #458, ARCHITECT addendum 112 item 10; the key, addendum 117 item 3)
- Schema: nullable `injuries.player_source_id` (VARCHAR(64)), the provider's own player id, NOT mapped in the ORM (the ORDER LINE note, as addendum 35 item 2 ruled for `odds.source_updated_at`: every chain reads `injuries`, and the release ritual runs migrations by hand after the checkout). src/db/database.py: `has_injury_player_id`, `write_injury_player_ids`, `read_injury_player_ids` (guarded Core SQL, only when the column exists; per call, never cached).
- Migration `migrate_injury_player_source_id.py` (new): additive, idempotent, behind the shared guard (`refuse_missing_db`, #524). Its receipt counts the rows that carry the id and the rows that do not, per source. No backfill. Run order: any (backup first, by hand). Laptop: `python migrate_injury_player_source_id.py`. Host: the `--run-migrations` line `sp_deploy.py` prints.
- src/adapters/api_american_football.py `list_injuries` (NFL, NCAA): each entry's dict carries `player_source_id`, the entry's own `response[].player.id` as a string (None when the entry has none). src/ingestion/service.py stores it on the row after the flush. It is a no-op until the migration.
- src/walters/window.py (`window-card`): each `qb_news` item carries `player_id`, the row's stored id (null where the row has none).
- deploy/hosting/sp_window_page.py: QB news is keyed by team id and provider id (`id:<team_id>|<id>`); the name is display only. The key as ruled (ARCHITECT 2026-10-17 16:55 ET, addendum 117 item 3), verbatim: "#458 — the key is (team id, provider player id). The ruling named the provider id to replace the name; a player listed on two teams' reports in one window (a trade, a provider error) is two entries, and collapsing them would hide one. Build it that way; the two-team test stays." One id on two teams' reports in one window is two entries, each paged on his own team's games. An item with no id keeps the old key, `<team_id>|<name>`, and its page line says `(no provider id)`. Items with no id that share a team and name become one entry holding every status, sorted (`(no provider id, N entries)`), so one never overwrites the other.
  - A change of key is not news. A player keyed by name in the previous state and by id now is carried to his id. Where two or more ids share the old name key, that name makes no delta that run when the ids' statuses are the name entry's (a baseline); otherwise the ids fold into one name-level line that pages.
  - The old state's one entry for two id-less same-name items, read against the entry that now holds both, is a baseline only when its status is the new last item's (where the old pager was silent too); otherwise it pages.
  - Ids arriving for a pair: a baseline only when their statuses are the name entry's; otherwise the ids fold into one name-level line that pages. The same the other way round.
  - The `(no provider id)` label follows the item: a player whose row loses its id keeps the label.
  - The receipt gains `qb_rekey` {`carried`, `baseline`}.
  - The `id:` prefix keeps the id key apart from the id-less `<team_id>|<name>` key. The key change finds a player's id key by the team-and-name `name_key` each entry carries, so it carries each team's listing to that team's id key.
- docs/CLI.md: the `sync-injuries` and `window-card` rows.
- tests:
  - test_qb_news_by_id.py (new, 22), led by the ruled test: two same-name quarterbacks on one team with different ids both appear, and a status change in either pages. Then the two-team tests (addendum 117 item 3):
    - one provider id on two teams' reports in one window is two entries, and a status change on either team pages for that team, on that team's games only;
    - when the first team's game leaves the card, nothing false pages for the other (on the id-alone key it paged `Out -> Questionable`, a change nobody made);
    - one id on both teams of one game is two entries;
    - the key change carries each team's listing to its own key.

    The other tests:
    - items with no id: keyed by team and name and labelled; two of them are never merged silently.
    - a deploy before the migration pages nothing new. An id-less same-name pair is a baseline only where the old pager was silent; otherwise it pages. A state this code wrote is never read as the old format.
    - a player whose row loses its id keeps the label.
    - the first run with ids pages only real changes. The collapsed pair is a baseline when its statuses are unchanged, then each pages by his own id; changed statuses page one folded line, both ways. `run()` receipts `qb_rekey`.
    - the adapter carries each entry's own id.
    - `sync-injuries` before the migration writes its rows and no id; after it, it stores the ids, and the card and page key by them.
    - the ORM never names the column.
    - the migration: additive, idempotent and receipted; it refuses without the table and with no database file.
  - test_qb_one_news_item.py: the helper's items carry a provider id. The card's item gains `player_id` (null for a row with none).
