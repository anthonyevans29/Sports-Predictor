## 2026-11-15 (#1012: 386-nhl-season-receipt — `nhl-goalie-coverage --db COPY`, the counts-only NHL season receipt (ARCHITECT 2026-11-15, addendum 386 item 2))
- **cli.py `nhl-goalie-coverage --db PATH`:**
  - It goes through the shared `--db` fence (`mlb_pitchers_gate.check_db` + `readonly_session`, mode=ro + immutable=1), with no `init_db()` on that path. A refusal exits 2.
  - Without `--db` the command is unchanged.
- **src/ingestion/nhl_goalies.py, `season_receipt`:** counts only, by season from the stored start, 2023-24 to 2026-27:
  - (a) the finished regular-season games (game type 2 as the rows say it, and the rows that do not say);
  - (b) both, exactly one, or no starter flagged;
  - (c) the unlinked appearances and the games they stand for;
  - (d) the relief share (TOI > 0; TOI not stored counted apart);
  - (e) 2026-27's latest stored game date.

  No goalie's name, no goalie id, no model figure.
- **docs/CLI.md's row.**
- **Tests:** tests/test_386_nhl_season_receipt.py, 3 tests on a synthetic copy. Each failed first on main.
