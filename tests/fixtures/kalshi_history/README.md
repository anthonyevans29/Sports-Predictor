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
| historical_markets_page.json | `historical_markets_page.json` | e066bf64a4b9ee48b80e70f5872e28b773debf262e693fd8ce9c9828da805bfa | 200 markets (100 events) → 6 (3) |
| settled_markets_page.json | `settled_markets_page.json` | acfb35d878d70c501a6fe7264fb619551c197b90d2b07176db6efcf1c3aaba15 | 200 markets (100 events) → 6 (3) |
| historical_candlesticks.json | `historical_candlesticks.json` | 0ce60e70458170f96268eccfe365a84bd279530bef7059996998e57dd81cf20f | 292 candles → 112 |
| live_candlesticks.json | `live_candlesticks.json` | d7ce350ca602b76bebae9f9783e32c24fd98c4b356dadacf232af7176b0452e7 | 360 candles → 152 |

The trim keeps whole objects only, never an edited one, in the kept order and the kept format
(`json.dumps(indent=1, sort_keys=True)`, no trailing newline). Every other key of each file (each page's `cursor`, each
reply's `ticker`) is kept as sent.

- **Pages.** Each page is series KXNFLGAME, its list's first page (the newest 200 markets). The trim keeps the markets
  of three events per page:
  - historical: KXNFLGAME-26AUG13LACHOU, -26AUG13INDNE (a tie: result "scalar") and -26AUG13DETCIN;
  - settled: KXNFLGAME-26OCT12BUFLAR (the live reply's market), -26OCT11DETARI and -26OCT11NYGWAS (a tie).
- **Candle replies.** The historical reply is KXNFLGAME-25JUL31LACDET-LAC and the live one KXNFLGAME-26OCT12BUFLAR-LAR.
  The trim keeps every candle up to the kickoff the tests store for the game (2025-08-01 00:00Z and 2026-10-13 00:15Z),
  and the first five after it. The rest of the in-play hours go.

What the tests write themselves, in memory, because the kept files do not hold it (no fixture file is edited):
- the listing of the historical reply's market (older than the kept page);
- each list's end page, a page whose cursor comes back, and the failures (a page refused 429; candle calls refused
  404 / 400 / 429 / 503 / 408);
- an empty reply for a market whose candles were not kept, and the kept historical reply from its first zero-volume
  minute;
- from a kept candle, copied: a minute with no ask, an empty side (a 0.00 bid or a 1.00 ask), a crossed quote;
- a candle whose end is in microseconds (unreadable, skipped);
- the MLB clock shape (synthetic series KXZKHGAME).

The keys, as `src/ingestion/kalshi_history.KEYS` names them and the tests check against every kept market and candle:
- cutoff: `market_settled_ts`;
- lists: `markets` / `cursor`;
- markets: `ticker`, `event_ticker`, `yes_sub_title`, `result`, `close_time`, and `settlement_ts` (settled_time's key,
  which the receipt did not name);
- candle replies: `candlesticks`, `end_period_ts` (epoch seconds);
- historical candles: `yes_bid.close` / `yes_ask.close`;
- live candles: `yes_bid.close_dollars` / `yes_ask.close_dollars`.

As the files send them:
- prices are dollar strings;
- times are ISO with a fraction of 0 to 6 digits;
- an empty side of a market's book is sent at size zero (every kept market), priced 0.00 for a bid and 1.00 for an
  ask (0.00 on the two legs of KXNFLGAME-26JAN25LASEA, raw page only);
- a zero-volume minute of the historical shape carries `price.close` / `open` / `high` / `low` / `mean` null, with
  `price.previous` set and its bid and ask present (42 of the 292 kept historical candles; the live reply has none).
