## 2026-11-16 (#1033: 408-proposer-replay-lines — the proposer's marked section names events and ids; the replay names refused events (ARCHITECT 2026-11-16, addendum 408 item 5; #955))
- **kalshi-table-propose's marked section:**
  - under each hand-read name, each event's ticker with the event's other name;
  - beside each top-score team, its team id and its provider id under `--key` (`-` where it has no one id).

  `kalshi_table.names_of` keeps the events, and `propose` carries them (`Proposal.seen`, `Proposal.top_ids`). The PROPOSED section and every mark are unchanged.
- **kalshi-replay:** after the counts by reason, one line per refusal reason other than the window and play begun names that reason's event tickers (`kalshi_replay.refused_events_lines`). An event that placed other legs is marked "in part".
- **The fence (408 item 5(c)):** `place()`, the loader, the resolver, the table files and `kalshi_match.console_lines` are unchanged. No sync's console, placement or refusal changes.
- **Tests:** tests/test_408_proposer_replay_lines.py (7). Six failed first; the fence test passes on main by design.
