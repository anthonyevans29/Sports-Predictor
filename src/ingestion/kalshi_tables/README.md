# Kalshi name tables (ARCHITECT 2026-11-15, addendum 387 item 3, (B))

A file `<SERIES>.json` in this folder DECLARES that series' name table (387 item 3(a)). Its events are then placed by
the table alone (`src/ingestion/kalshi_match.py`, `place(tables=...)`; `src/ingestion/kalshi_table.py`):
- a tabled name fits its one team, found by the provider's key and id through `Team.external_ids`;
- a name the table does not hold refuses its event under a reason naming it;
- a line whose id is not one stored team of the series' competition refuses, and says so.

A series with no file here is matched by the scorer as before, to the last character.

**The tables here:** `KXNCAAMBGAME.json`, 313 lines: the 253 proposed lines as the architect read them (ARCHITECT
2026-11-15, addendum 392 item 2), then the 60 marked names, each ruled by hand on its stored game against the event's
other name (addenda 393 item 2 and 394 item 1).
PR one of 387 item 3 was the machinery and no data; each table arrives as data in a PR of its own, from the
architect's read of the proposer's console (`python cli.py kalshi-table-propose`). Every line is read by the architect
before it is data (387 item 3(e)).
`KXNCAAFGAME.json`, 264 lines: every name of the series' open markets of 2026-11-16, each proved by the architect's
reading on one stored game against its event's other name (ARCHITECT 2026-11-16, addendum 412 item 2; 236 the
proposer proposed, 28 it marked). KXNCAAFGAME is live on the host: this table is declared only beside a replay that
shows its placements against the scorer's on the SAME kept markets, each difference read by name (387 item 3(f);
412 item 3(c)).

The file, strict (any other field, a name twice, two names that differ only by case, or an id that is not a string
refuses the whole table, and every event of the series is then refused, never matched by the scorer):

```json
{
  "series": "KXNCAAMBGAME",
  "ruled": "ARCHITECT <date>, addendum <N> item <i>",
  "lines": [
    {"name": "Alabama St.", "key": "api_basketball", "id": "<the provider's team id>"}
  ]
}
```

`name` is the Kalshi name as the matcher takes it: the market's `yes_sub_title`, stripped.
