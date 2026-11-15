# Kalshi name tables (ARCHITECT 2026-11-15, addendum 387 item 3, (B))

A file `<SERIES>.json` in this folder DECLARES that series' name table (387 item 3(a)). Its events are then placed by
the table alone (`src/ingestion/kalshi_match.py`, `place(tables=...)`; `src/ingestion/kalshi_table.py`):
- a tabled name fits its one team, found by the provider's key and id through `Team.external_ids`;
- a name the table does not hold refuses its event under a reason naming it;
- a line whose id is not one stored team of the series' competition refuses, and says so.

A series with no file here is matched by the scorer as before, to the last character.

**The tables here:** `KXNCAAMBGAME.json`, its first table (ARCHITECT 2026-11-15, addendum 392 item 2: the 253 proposed
lines as the architect read them; the 60 marked names are not in it and refuse by name until each is its own ruling).
PR one of 387 item 3 was the machinery and no data; each table arrives as data in a PR of its own, from the
architect's read of the proposer's console (`python cli.py kalshi-table-propose`). Every line is read by the architect
before it is data (387 item 3(e)).
KXNCAAFGAME, live on the host, stays without a table until its own is declared and a replay shows its placements
identical to main's but for removals, each removal a named gap of the table (387 item 3(f)).

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
