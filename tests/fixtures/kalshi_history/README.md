# tests/fixtures/kalshi_history — the probe's kept payloads, trimmed

ARCHITECT 2026-10-14 (addendum 67 item 1): "Tests on the kept payloads (both shapes, the cutoff file, a settled page
and a historical page)". Addendum 68 item 5: "You read them from that branch, enumerate KEYS from them (settled_time
included), trim what the tests need into tests/fixtures/kalshi_history/ on #521's branch, and the raw branch is
deleted after #521 merges — the raw files never land on main."

The five kept files are scripts/kalshi_history_probe.py's payloads of 2026-10-14 11:54Z (public market data, no account
or key). The operator pushed them on laptop/kalshi-payloads-1014 (34723f1) under tests/fixtures/kalshi_history/raw/.
Each fixture here is its file trimmed, under the probe's suffix as its name:

| fixture | kept file (`kalshi_history_20261014T115440Z_…`) | sha256 of the kept file | kept → here |
| --- | --- | --- | --- |
| cutoff.json | `cutoff.json` | b3be27c45659312bde29548b0f1e8efaca9faecdc7120642eb02af92bf979449 | 201 bytes, byte for byte |
| historical_markets_page.json | `historical_markets_page.json` | e066bf64a4b9ee48b80e70f5872e28b773debf262e693fd8ce9c9828da805bfa | 200 markets → 6 |
| settled_markets_page.json | `settled_markets_page.json` | acfb35d878d70c501a6fe7264fb619551c197b90d2b07176db6efcf1c3aaba15 | 200 markets → 6 |
| historical_candlesticks.json | `historical_candlesticks.json` | 0ce60e70458170f96268eccfe365a84bd279530bef7059996998e57dd81cf20f | 292 candles → 112 |
| live_candlesticks.json | `live_candlesticks.json` | d7ce350ca602b76bebae9f9783e32c24fd98c4b356dadacf232af7176b0452e7 | 360 candles → 152 |

The trim keeps whole objects only, never an edited one, in the kept order and the kept format
(`json.dumps(indent=1, sort_keys=True)`, no trailing newline). Every other key of each file (each page's `cursor`, each
reply's `ticker`) is kept as sent.

- **Pages.** Each page is series KXNFLGAME, its list's first page (the newest 200 markets). The trim keeps the markets
  of three events per page:
  - historical: KXNFLGAME-26AUG13LACHOU, -26AUG13INDNE (a tie: result "scalar") and -26AUG13DETCIN;
  - settled: KXNFLGAME-26OCT12BUFLAR (the live reply's market), -26OCT11NYGWAS (a tie) and -26OCT11DETARI.
- **Candle replies.** The historical reply is KXNFLGAME-25JUL31LACDET-LAC and the live one KXNFLGAME-26OCT12BUFLAR-LAR.
  The trim keeps every candle up to the kickoff the tests store for the game (2025-08-01 00:00Z and 2026-10-13 00:15Z),
  and the first five after it. The rest of the in-play hours go.

What the tests write themselves, because the kept files do not hold it:
- the listing of the historical reply's market (older than the kept page);
- each list's end page;
- an empty reply for a market whose candles were not kept;
- the MLB clock shape (synthetic series KXZKHGAME).

The keys, as `src/ingestion/kalshi_history.KEYS` names them and the tests check against every kept market and candle:
- cutoff: `market_settled_ts`;
- lists: `markets` / `cursor`;
- markets: `ticker`, `event_ticker`, `yes_sub_title`, `result`, `close_time`, and `settlement_ts` (settled_time's key,
  which the receipt did not name);
- candle replies: `candlesticks`, `end_period_ts` (epoch seconds);
- historical candles: `yes_bid.close` / `yes_ask.close`;
- live candles: `yes_bid.close_dollars` / `yes_ask.close_dollars`.

Prices are dollar strings. A zero-volume minute carries a null `price` with its bid and ask present.
