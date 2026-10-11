**2026-10-09 — RECORD + BUILD (ARCHITECT 2026-10-09 19:02 ET, addendum 32 items 2, 3 and 5; Issue #399): the odds payload has been read (American football carries response[].update, one per game, and the adapter drops it; hockey has no such field), what `update` is is RULED, and the odds payload probe gains soccer (api_football) and MLB (api_baseball).**

- **Item 2 (the odds payload read; recorded for Issue #399, whose odds question it answers for match 32740), verbatim:**

> 2. THE ODDS PAYLOAD HAS BEEN READ. It is build step 1 of 2026-10-07 (#339), run by the operator at ed5ecbb at
> 22:58Z; the lines that bear on it are in RECEIPTS below, verbatim. Record them on #399 and in its entry.
> - American football (NCAA, game 23616): the answer carries response[].update, one per game, here
>   "2026-10-08T02:15:10+00:00". The adapter drops it.
> - Hockey (NHL, game 444666): no such field. Every time-like key it has belongs to the game: its date, time,
>   timestamp and time zone.
> - So the prices our sync stamped 22:07Z tonight on match 32740 (id 23616) were last updated by the provider at
>   least 43 hours and 52 minutes before. That is #399's odds question answered for that row: frozen, and stamped
>   as fresh.

- **Item 3 (the ruling on what `update` is), verbatim:**

> 3. RULED: WHAT update IS.
> "response[].update is the provider's own time for a game's odds: one per game, neither our fetch time nor the
> fixture's. It is read as the newest that any quote in the answer can be; a quote may be older. It is stored and
> shown as source_updated_at and described in those words, never as the time of a quote. A row without it has an
> unknown source time, and unknown is never read as fresh."

- **Item 5 (built in this PR), verbatim:**

> 5. THE PROBE GAINS SOCCER AND MLB. Its own small PR, mergeable at once. scripts/odds_payload_probe.py reads the
> odds answer of api_football and of api_baseball through each adapter's own odds call, as it does for the two it
> has, with the same refusals. Nothing is stored for a sport until its payload has been read.

- **Receipts (addendum 32, RECEIPTS, item 2, verbatim):**

```
RECEIPTS (item 2), the operator's console, 2026-10-09 22:58Z, the lines that bear on it, verbatim:
match 32740 -> provider game id 23616
ODDS PAYLOAD PROBE · NCAA · the endpoint sync-odds-football uses (APIAmericanFootballAdapter, provider id key 'api_american_football') · 2026-10-09T22:58:36Z
GET https://v1.american-football.api-sports.io/odds?game=23616 -> HTTP 200 · x-ratelimit-requests-remaining 5257
league verified from the payload: NCAA (2)
  response[].update  [str] x1  e.g. "2026-10-08T02:15:10+00:00"
TIME-LIKE KEY NAMES (update/time/date/last/stamp/modif/created/fetched/as_of/ts, on the keys present):
  response[].update  e.g. "2026-10-08T02:15:10+00:00"
DATE-TIME-LOOKING VALUES (any key):
  response[].update  e.g. "2026-10-08T02:15:10+00:00"
VERDICT (this payload): a time-like field is present and dropped by the adapter: response[].update — whether it is the QUOTE's own time (vs the response's or the fixture's) is for the ruling

match 27524 -> provider game id 444666
ODDS PAYLOAD PROBE · NHL · the endpoint sync-odds --competition NHL uses (APIHockeyAdapter, provider id key 'api_hockey') · 2026-10-09T22:58:39Z
GET https://v1.hockey.api-sports.io/odds?game=444666 -> HTTP 200 · x-ratelimit-requests-remaining 7363
league verified from the payload: NHL (57)
TIME-LIKE KEY NAMES (update/time/date/last/stamp/modif/created/fetched/as_of/ts, on the keys present):
  response[].game.date  e.g. "2026-10-10T00:00:00+00:00"
  response[].game.periods.overtime  e.g. null
  response[].game.time  e.g. "00:00"
  response[].game.timer  e.g. null
  response[].game.timestamp  e.g. 1791590400
  response[].game.timezone  e.g. "UTC"
DATE-TIME-LOOKING VALUES (any key):
  response[].game.date  e.g. "2026-10-10T00:00:00+00:00"
VERDICT (this payload): a time-like field is present and dropped by the adapter: response[].game.date, response[].game.periods.overtime, response[].game.time, response[].game.timer, response[].game.timestamp, response[].game.timezone — whether it is the QUOTE's own time (vs the response's or the fixture's) is for the ruling
```

- **What item 5 built (read from the code, law 1).** `scripts/odds_payload_probe.py` gains `--sport soccer` and `--sport mlb`, each making the request its sync makes through the adapter's own base URL, headers and key, with the same refusals as nhl/ncaa (non-2xx, a body that is not a JSON object, a non-empty `errors`, an unreadable `--from-file`, `--out` under `exports/` only, `--match-id` read-only via `mode=ro`, the competition and league checks):
  - soccer: `sync-odds --competition CODE` → `IngestionService.sync_odds` → `APIFootballAdapter.list_odds` (src/adapters/api_football.py:356) → `GET <base_url>/odds?fixture=<id>` (:371; `v3.football.api-sports.io` unless `API_FOOTBALL_HOST` names RapidAPI), provider id key `api_football` (`source_name`, read by sync_odds as `match.external_ids[self.source]`). `--competition` is required: the payload's `response[].league.id` must be that code's `_CODE_TO_LEAGUE_ID` entry (PL 39, ...).
  - MLB: `sync-odds --competition MLB --season S` → `IngestionService.sync_odds_mlb` → `APIBaseballClient.list_odds_window` (src/adapters/api_baseball.py:190) → `GET https://v1.baseball.api-sports.io/odds?league=1&season=S` (:207-208): one call for the whole window, no game id; the sync matches the games to ours by names and start time (find_match), not by a stored id. So the probe takes `--season` (required); `--game` / `--match-id` instead probes the sync's M11a rollover fallback `list_odds_for_game` (`...&game=<id>`, :245-247). `--match-id` reads `external_ids["api_baseball"]`, which only the host's api-sports fallback writes (src/ingestion/mlb_apisports.py SOURCE); a row without it is refused. League id 1 (`MLB_LEAGUE_ID`).
  - The read/drop listing is per adapter: soccer reads response[].bookmakers[].name / bets[].name / values[].value / odd (no bookmaker id); MLB also reads response[].game.id, game.date (commence_time), game.teams.home/away.name and values[].handicap. Usable quotes are counted by running each adapter's own parse offline on the payload (its `_get` replaced by the payload; no request, no key).
  - nhl / ncaa are unchanged in request and refusals; their printout now names the adapter call (`APIHockeyAdapter.list_odds reads N of these paths`, and the header line `(APIHockeyAdapter.list_odds, provider id key ...)`) where it said `list_odds` / the class.
  - Nothing is stored for either sport: the probe opens no DB except read-only for `--match-id`. Item 4 (store and show `source_updated_at`) touches American football only and is a separate PR.
