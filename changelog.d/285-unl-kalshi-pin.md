## 2026-10-05 (#285: UNL Kalshi series pinned to KXUEFANLGAME; KXCONCACAFNLGAME reserved for CNL — ARCHITECT ruling)
- `src/adapters/kalshi.py`: UNL → `KXUEFANLGAME` in `SOCCER_GAME_SERIES`, the adapter default, so the window chain needs no `--series`. Discovery had refused on two candidates (KXUEFANLGAME, KXCONCACAFNLGAME).
- New `SOCCER_SERIES_RESERVED = {"CNL": "KXCONCACAFNLGAME"}` ("for later"): a CNL sync refuses and names the series until CNL is wired (#284).
- `SOCCER_SERIES_DISCOVERY` is now empty; the mechanism stays tested for a future unpinned competition.
- Tests: pin + reserve (no `/series` call for UNL), discovery exactly-one-or-refused on the 2026-10-05 listing, and a UNL sync storing a three-way set via "mapped" with both candidates listed. Docs: CLI.md.
