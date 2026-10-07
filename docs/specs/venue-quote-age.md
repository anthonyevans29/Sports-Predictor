# Venue-edge: quote age (ARCHITECT 2026-10-07, addendum 4 E, gate-class)

## The ruling (verbatim)

> "FINDING: the venue engine fired on dead books. Receipts: the laptop (14:56:15Z, sha 65b8ce7) and the host (16:00:38Z, v1.3.0) each printed VENUE 0.25u on San Jose @ St. Louis (2026-10-09T00:00Z) from the SAME five-book consensus to four decimals (HOME 0.4735 / AWAY 0.5265) against Kalshi 0.545 / 0.455. The live price had already moved: DraftKings Blues -125 / Sharks +112 (about 0.541 / 0.459), which is Kalshi's price; the Sharks -115 line the provider still serves matches a page dated 2026-10-06. #91 tests the age of OUR fetch (odds.captured_at); the provider can serve an old quote on a fresh fetch, and no quote time is stored. RULED: #91 means the age of the QUOTE. A fetch time is not a quote age; where the quote's own time is not known the age is UNKNOWN, and the ratified rule for unknown age is NO REFERENCE. From today the operator places no VENUE order on either machine's files. In code, from the next tag: venue-edge emits no call (PASS, noref, 'book quote age unknown: no reference') and the venue block keeps its numbers for the record. No hotfix tag is cut for this before the cutover; v1.3.0 on the host keeps printing VENUE rows that this ruling holds. The engine resumes only when a quote time is stored and #91 is applied to it, by ruling."

Build order (verbatim): "(1) a read-only payload probe the operator runs for one NHL and one NCAA fixture: every field of the odds response, any update or timestamp field named (law 1; never guess a key). (2) If the payload carries a quote time: store it on the odds rows (nullable column, migration), carry it on the fixtures export beside captured_at, and make #91 test it. If it does not: say so, and propose a staleness test from our own captures (a consensus unchanged to four decimals across N captures) for a ruling. (3) A receipt over every VENUE call on file since 2026-10-02: the consensus at the call and at each later pre-kickoff capture, and whether it ever moved. (4) Report, do not change: how old the book quotes behind MODEL-sport references are at decision time (MLB, NFL, PL). That is the next ruling."

## (0) The code rule (from the next tag)

`src/walters/desk_policy.py`:

- `venue_edge()` holds every row the engine **computes**, meaning a row where a side and its divergence were measured. Such a row gets:
  - `eligible` false, kind `noref`, reason exactly `book quote age unknown: no reference`;
  - its numbers kept: `side`, `divPP`, `bookP`, `kalP`, and `execPP` / `execCost` under the #87 addendum;
  - the engine's would-be verdict recorded as `held` (eligible, kind, reason).
- `desk_block()` for a market-only row therefore always gives `call` PASS, `units` 0, `pass_kind` `noref`, that reason, and `order` null. `side`, `div_pp`, `book_p`, `kalshi_p` and `stale_book_zone` stay as computed.
- `venue_block()` keeps `side`, `div_pp`, `book_p`, `kalshi_p`, `exec_pp` and `exec_cost`. It adds `quote_age_hold`: `{rule, engine_eligible, engine_kind, engine_reason}`, which is the record of what the engine would have said.
- **Precedence (reading chosen).** A row that stops BEFORE the computation keeps its own reason, because each of these is already a no-call under its own rule:
  - model charter;
  - `single venue — no pair (UNL)`;
  - `in-play — never`;
  - `single venue — no pair`;
  - book capture unknown / after the decision time / older than 3h (#91);
  - `books N < 4 — pair too thin`.

  Every computed row is held, including below-floor and exec-floor rows, not only rows that would have been VENUE. No quote time is stored for ANY row, so none of them has a reference. Their former floor verdicts survive under `quote_age_hold`.
- **Switch.** `QUOTE_AGE_RULE = {"on": True}`.
  - `base_v11()` turns it off, together with the #87 addendum and the started rule. The frozen golden (`tests/golden/desk_js_v1_1.json.gz`) is therefore unchanged.
  - `quote_age_rule_off()` exists for the engine's own tests and the Cockpit verifies. No export uses it.
  - `desk_meta.venue_quote_age_rule` records the switch.
- **Window card.** `window_venue()` goes through the same `venue_edge()`, so the Next-24h card never shows "VENUE 0.25u (shadow)".
- **Parlays.** Legs come only from `evaluate()["calls"]`, which holds model rows only. A venue row was never a parlay leg, and still is not; a test pins this.
- **Cockpit** (`tools/cockpit.html`). It renders the file's venue block, and a held row shows as PASS · "no reference", greyed, with the file's numbers and reason and no order line. The auto-claim logs only eligible venue rows, so no claim is made. The one change: the "re-run at T-60" hint is suppressed on held rows (`quote_age_hold` present), because a re-run cannot clear the hold. Verify: `scripts/cockpit_venue_quote_age_verify.py` (11/11).
- **Not changed.** Files already written by v1.3.0 (the host) still carry VENUE rows. The Cockpit renders and auto-claims them as the file says. The ruling holds those rows operationally ("the operator places no VENUE order on either machine's files"). Whether the Cockpit should refuse or relabel pre-ruling VENUE rows, or keep them out of the ledger, is ledger/policy semantics, left for a ruling.

## (1) The payload probe

`scripts/odds_payload_probe.py` is READ-ONLY and opens no DB unless `--match-id` is given; in that case it opens the DB read-only with `mode=ro`. It calls the endpoint each sync uses:

| sport | sync | adapter | endpoint | key (never printed) |
|---|---|---|---|---|
| NHL | `sync-odds --competition NHL` (`IngestionService.sync_odds`) | `APIHockeyAdapter.list_odds` | `GET https://v1.hockey.api-sports.io/odds?game=<id>` | `API_HOCKEY_KEY`, else `API_FOOTBALL_KEY`, header `x-apisports-key` |
| NCAA | `sync-odds-football` (`sync_odds_nfl`, NFL+NCAA) | `APIAmericanFootballAdapter.list_odds` | `GET https://v1.american-football.api-sports.io/odds?game=<id>` | `API_AMERICAN_FOOTBALL_KEY`, else `API_FOOTBALL_KEY` |

`.env` is loaded through `config.py`, as `cli.py` does. The probe prints:

- every key path, with its types, samples and list lengths. EVERY list element is scanned (Codex on #340), so a key present only in a late bookmaker / bet / value is still collected. `--max-items` limits only the samples printed per path, and the date-time test runs on every value, not only on the printed samples;
- every key whose NAME contains update / time / date / last / stamp / modif / created / fetched / ts;
- every path whose VALUE looks like a date-time;
- the paths `list_odds` reads, against the paths that are present and dropped;
- a one-line verdict.

**Refusals (Codex on #340).** An unsuccessful response is refused with exit 2, its reason and NO verdict. A missing provider key and every `--match-id` preflight failure (non-SQLite URL, no DB file, unknown match, no provider id) are refusals the same way. These are the adapters' own `_get` checks (`src/adapters/api_hockey.py` / `api_american_football.py`: `raise_for_status`, then `errors` rejection):
- a non-2xx HTTP status (401 / 429 / 5xx). The probe does not retry a 429; it refuses it;
- a body that is not JSON, or not a JSON object;
- a non-empty `errors` field (a list, or an object with values).

A `--from-file` payload carrying a non-empty `errors` field is refused the same way. A refused response is never read as "no time-like field".

Options:
- `--from-file` re-reads a saved payload.
- `--out` writes the raw payload, key-redacted, under `exports/` only. A path under `data/`, or anywhere else, is refused.

**Provisional answer from the code.** Both adapters' `list_odds` read only:
- `response[] → bookmakers[] → name / id`;
- `bets[] → name`;
- `values[] → value / odd`.

They stamp every row `captured_at = utc_now_naive()` at fetch time:
- `src/adapters/api_hockey.py:233-261`, stamp at `:235` / `:258`;
- `src/adapters/api_american_football.py:310-338`, stamp at `:312` / `:335`.

Any other field in the response is dropped. The sync paths store that fetch stamp:
- `src/ingestion/service.py:738` and `:745` (NHL: the snapshot carries the session's fetch stamp);
- `:2001` / `:2030` / `:2040` (football: "stamped at FETCH time").

**The repo holds no stored odds payload.** No fixture, test or doc shows the provider's response, so whether the response carries a quote or last-update time is UNKNOWN from the code. It is the probe's question, answered only by the operator's live run.

## (2) The conditional branch: taken = NO COLUMN (uncertain)

The code cannot show a quote time (see above), so no column, migration or export field is added. The code rule (0) stands either way. If the probe finds a quote-time field, storing it is a follow-up for a ruling. That follow-up would be:
- a nullable column on `odds`, plus `odds_snapshots` for the session;
- a `migrate_*.py`;
- the adapter storing it;
- the fixtures export carrying it beside `captured_at`;
- #91 applied to it.

The ruling must also say whether the field is the QUOTE's own time, rather than the response's or the fixture's.

**Proposal for a ruling: a staleness test from our own captures.** A venue-edge book reference is STALE, and so has NO reference, when the consensus behind it is unchanged at four decimals across the last **N** captures. The consensus here is the same-source odds_snapshots session's de-vigged fair on every outcome, `round(p, 4)`. Two variants for the architect to choose between, with **N left to the architect**:
- across N captures that are all pre-kickoff and span at least T hours;
- across N captures only.

Inputs the receipts below provide:
- `venue-calls-receipt` gives each call's "identical since" run (the captures and the earliest stamp);
- `quote-age-report` gives the same run length for the model sports, as a base rate of how often a live consensus sits still.

Open points for the ruling:
1. A consensus can legitimately sit still on a quiet market, which gives false positives.
2. A fresh fetch of a stale provider page can still move by a book dropping out, which gives false negatives. Should `n_books` changes count as movement?
3. Does a reference that passes the staleness test resume the engine, or is a stored quote time still required? The ruling says the engine resumes "only when a quote time is stored and #91 is applied to it".

## (3) The receipt: `venue-calls-receipt`

`python cli.py venue-calls-receipt [--since 2026-10-02] [--exports-dir exports] [--ledger <bd_ledger_v1 export>] [--out docs/receipts/…]`. READ-ONLY (SELECTs only). `--out` refuses `data/`.

- **On file**:
  - every JSON under `--exports-dir`, recursively, so the host copies under `exports/host/` are read too, that has `desk_meta.as_of >= --since`;
  - every fixtures row whose `desk.call == "VENUE"` (engine `venue_edge`). One call per (sport, home, away, kickoff, as_of, side), a stable identity that never uses match_id. A copy in two files is one call listing both paths;
  - plus the ledger's `engine == "venue_edge"` claims. A claim of a call already on file marks it "in ledger". A ledger-only claim is matched to the DB by exact team names with kickoff ±12h; an ambiguous match or no match is "NO DB MATCH", never guessed.
  - **Claim time (Codex on #340).** The claim time is `claim_at`, the frozen first claim. The Cockpit's `upsertCalls()` re-log merges `{...cur, ...fresh}`, so the top-level `claim_as_of` / `captured_at` become the NEWEST log's. `stampTiming()` sets `claim_at` once and appends every capture to `reprices[]`. A position logged before the timing rule has no `claim_at`; it falls back to `claim_as_of`, else `captured_at`, labelled "unfrozen". The re-logs after the claim are listed on the position ("re-logged N time(s)") and in the totals, and are never counted as separate calls.
  - **Manual claims (Codex on #340, second review).** An auto-claim's clock is the file's `desk_meta.as_of`, so it matches its file call to the second. A MANUAL claim ("Log today's calls") is stamped at the button click, so it falls back to the position's identity (sport, teams, kickoff, side; the Cockpit's `instKey`). It merges onto the latest file call of that position at or before the click. If there is none, it is its own row, never guessed onto a later file.
- **Match identity (Codex on #340), both commands.** An export row's `match_id` is machine-local (`docs/specs/hosting-h1.md`: the comparator keys on (kickoff, home, away), never `match_id`).
  - A row from the laptop's own files uses its `match_id` only after the DB row's home/away names and kickoff (±12h) match the exported `home_team` / `away_team` / `utc_date`.
  - A row from a mirrored file (a path under `<exports-dir>/host/`, which is `pull_exports.py`'s destination) never uses its id; the id is recorded as foreign.
  - A mirrored row, an id missing from the DB, or an id naming a different game resolves by exact team names + kickoff ±12h.
  - Zero matches or more than one is unresolved ("NO DB MATCH" / excluded), reported with the reason and never guessed.
  - Limitation: `fixtures_<CODE>_<date>.json` is overwritten on each run that day, so only the last desk run per day per machine is on disk.
- **Consensus**:
  - a BOOK capture session in `odds_snapshots`: one (source, captured_at), market 1X2, every outcome present, `source != "kalshi"`;
  - fair = `devig_prob` normalised over the outcomes (`close_from_snapshots`' rule); books = max `n_books`;
  - compared at FOUR decimals.
- **At the call**:
  - the file's market block: fair to 4 dp, books, `captured_at`, `fair_source`;
  - the ANCHOR is the session at the file's `captured_at`. If there is none at that stamp, it is the last session before it, labelled. For a ledger-only call it is the last session at or before the claim time.
  - It also reports "file == anchor at 4dp" and the anchor's "identical since" run.
- **Later**: every same-source session after the anchor and before kickoff. Each is marked MOVED or unchanged.
- **Verdict**: NEVER MOVED (at least one later capture, none differing) / MOVED / NO LATER CAPTURE / NO ANCHOR / NO DB MATCH.
- **Totals**: calls; tested (calls with at least one later capture); never-moved count with its share of tested and its share of calls; re-logged ledger positions and re-log count (each position counted once).

## (4) The report: `quote-age-report`

`python cli.py quote-age-report [--since 2026-10-02] [--exports-dir exports] [--out docs/receipts/…]`. READ-ONLY. `--out` refuses `data/`. The report is labelled **capture-based PROXIES (our fetch times), NOT quote age**.

- **Rows**: every `--desk` prediction-export row of MLB / NFL / PL with `desk.engine == "model_edge"` and `desk.reference == "books"`. Started rows are excluded. One row per (sport, home, away, kickoff, as_of). Each row resolves to the DB by match identity, as above.
- **Capture age** = desk `as_of` − the last book capture session at or before `as_of` (and before kickoff). The prediction exports' market blocks carry no `captured_at`, so the session comes from odds_snapshots. "file fair == capture at 4dp" is counted as a check that the session found is the one behind the reference.
- **Unchanged age** = desk `as_of` − the earliest capture of the run of consecutive same-source captures that are identical at 4 dp and end at that session. A run that reaches the first capture on file is *censored*: the true age is at least that long.
- **Measured rows only (Codex on #340).** Only a row whose selected session is VERIFIED enters median / p90 / max, the above-3h count and the censored count. Verified means `file_matches` is true: the file's 1X2 fair equals the capture at 4 dp. These rows are counted and listed as EXCLUDED, each with its reason:
  - a mismatch (`file fair != the selected capture`), for example from multi-source history;
  - no 1X2 fair to compare (for example an NFL `spread_derived` reference);
  - no capture;
  - no DB match.
- **Per sport**: rows, rows with a capture, measured (verified) and excluded, the file-match / mismatch / no-file-fair counts, then median / p90 / max of both ages, the count with unchanged age above 3h, and the censored count, all over measured rows. Percentiles are nearest-rank on the sorted list, index round(q·(n−1)).

## Readings chosen (for the architect)

1. **Precedence.** Every computed row is held. Pre-computation no-reference reasons keep their own text.
2. **The engine's former verdict** is kept for the record under `venue.quote_age_hold`. It is not a call.
3. **Branch (2): no column.** The code shows no quote-time field, and the repo holds no payload to check, so the question is uncertain.
4. **"On file"** = `exports/` recursively (laptop and host copies), plus the ledger export when given.
5. **"Moved"** is measured against the anchor session from the same source, not against the file's numbers. The NCAA snapshot de-vig (`MarketSnapshot.average_implied`, `service.py:2034-2045`) differs from the export's per-book `close_1x2`, so comparing the file to a snapshot would show spurious movement. The file-vs-anchor match is reported separately.
6. **NO LATER CAPTURE** is its own verdict (law 4). It never counts as "never moved".
7. **The Cockpit** keeps rendering pre-ruling VENUE rows from v1.3.0 files as written. Any change there is for a ruling.
