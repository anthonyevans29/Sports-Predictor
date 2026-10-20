# tests/fixtures/odds_payloads: the providers' own odds answers, trimmed (#615)

ARCHITECT 2026-10-20 10:04 ET, addendum 147 item 1, verbatim: "The fixture for the test is the kept PL file trimmed (one
bookmaker, one bet, the update field kept), as the Kalshi fixtures were trimmed from their kept payloads."

`api_football_odds_fixture_1557437.json` is read by tests/test_book_source_times_615.py. It is the operator's read-only
probe answer `exports/probe_pl.json` on branch `laptop/odds-payloads-1020` (ee84a62): `scripts/odds_payload_probe.py
--sport soccer --competition PL` for match 9239, i.e. `GET /odds?fixture=1557437`, fetched 2026-10-20T14:03:01Z.

**Kept as fetched:** `get`, `parameters`, `errors`, `results`, `paging`, and from `response[0]` its `league`,
`fixture` and `update` objects/values.

**Trimmed:** `response[0].bookmakers` keeps one bookmaker of the ten (Bet365, id 8), and that bookmaker keeps one bet of
its list (Match Winner, id 1) with its three values as fetched.

The file holds public fields only: no key, no row of any database, no host name. The MLB answer (`exports/probe_mlb.json`)
stays on the laptop branch as the receipt that api-baseball's odds answer carries no update field (addendum 147 item 2);
it is not a fixture.
