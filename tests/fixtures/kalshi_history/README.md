# tests/fixtures/kalshi_history — STAND-INS for the probe's kept payloads

ARCHITECT 2026-10-14 (addendum 67 item 1): "Tests on the kept payloads (both shapes, the cutoff file, a settled page
and a historical page)", and "read each by its own keys from the kept payloads of 2026-10-14 under logs/ (law 1:
enumerate the keys from those files, not from memory)".

The kept files (`logs/kalshi_history_<stamp>_{cutoff,historical_markets_page,settled_markets_page,
historical_candlesticks,live_candlesticks}.json`, the laptop's) had not reached the session that built the ingest
(this container cannot reach the exchange: its proxy refuses the CONNECT). These five files are stand-ins written to
the keys of the architect's receipt (addendum 66 item 6) and of scripts/kalshi_history_probe.py's reader, with
synthetic markets (series KXZKHGAME, teams Alpha / Beta / Gamma / Delta). They are replaced by the kept files, trimmed
to a few markets and candles and renamed to these five names, before the PR leaves draft; the tests then read the
real keys and src/ingestion/kalshi_history.KEYS is checked against them.
