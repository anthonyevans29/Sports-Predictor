## 2026-11-15 (#1017: 387-matcher-table — the Kalshi matcher's name tables, (B): the machinery and no data (ARCHITECT 2026-11-15, addendum 387 item 3; #955))
- **The rule:** a series DECLARES a name table by a file of its own, `src/ingestion/kalshi_tables/<SERIES>.json`. The folder holds none yet; its README says how one is declared.
- **How a declared series' events are placed (kalshi_match.place(tables=...); kalshi_table.py), by the table alone:**
  - a tabled name fits its one team, found by the provider's key and id through Team.external_ids (team_merge.source_ids), among the stored teams of the series' own competition;
  - no word is read, so no line can loosen a fit;
  - home and away come from the teams' own ids;
  - everything after the fit is as for every series (the day rule, the time gate, the window, in play, claims, behind).
- **New counted refusals:**
  - a name the table does not hold: `not in <SERIES>'s name table: <name>` (387 item 3(a));
  - a line no one stored team of the competition answers to: TABLE_LINE_UNRESOLVED, with a line saying which and why ((b));
  - an unreadable table: TABLE_UNREADABLE, every event of the series refused;
  - a caller that did not read a declared table: TABLE_UNREAD (place() reads the folder itself).

  Never the scorer.
- **A series with no table is matched as today.** PINS is unchanged ((c)).
- **The callers:** the shared and soccer syncs, kalshi-replay and the tennis sync pass `kalshi_table.tables_for`. The kalshi-history paths (run, place-held, place-chain and its listing) fit names with the scorer outside place(), so they refuse a declared series.
- **`kalshi-table-propose` (read-only; 387 item 3(d)-(e)):**
  - from a kept markets file and a .backup copy (`--db` fence, mode=ro + immutable=1, no sidecar), it prints each name with its proposed team, the provider's key and id, and its marks;
  - the hand lines are printed first;
  - a marked name is never proposed.
- **Tests:** tests/test_387_kalshi_name_table.py (47); docs/CLI.md's row.
