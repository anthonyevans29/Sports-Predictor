## 2026-10-08 (#366: soccer-expansion-v1 closing-odds name pins; second preflight read)
- `team_aliases.TOKEN_SYNONYMS` gains five football-data entries (ARCHITECT 2026-10-08, addendum 12): bilbao -> athletic, espanol -> espanyol, m'gladbach -> mönchengladbach, hamburg -> hamburger, brest -> brestois. Nothing else in the matcher changes.
- The football-data closes ingest (`soccer_odds_history`) normalizes both names to Unicode NFC before scoring, so an NFD-stored Mönchengladbach still matches. The shared tokenizer is otherwise unchanged, because the Kalshi matchers run on it.
- Guard: ath, borussia and stade are never synonyms (pinned by a test).
- Tests cover the architect's hard cases, the NFD form, a re-run storing nothing, and a tie still refused.
- Ledger: the second soccer preflight read, and #363 (design-stage band-rule finding).
