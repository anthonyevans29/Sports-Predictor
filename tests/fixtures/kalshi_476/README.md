# tests/fixtures/kalshi_476: the TB @ CLE markets of #476, from the operator's relayed replay

ARCHITECT 2026-10-18 09:58 ET, addendum 127 item 3(b), verbatim: "REGRESSION TESTS, a tests-only PR: the Saturday set
verbatim (2 no-game-on-date + 2 behind), states A1 and A2, the Sunday shape (2 in play), the Friday control (4
placed), the ALCS tests unchanged — today's answers pinned whatever the receipt says."

`tbcle_markets.json` is read by tests/test_kalshi_476_regression.py. It holds public market fields only: no row of
any database, no host name, no path. It is written as `json.dumps(indent=1, sort_keys=True)` with no trailing newline.

The source is the operator's relay of Sunday 2026-10-18: the morning block's KALSHI-REPLAY KXMLBGAME section, fetched
at 11:37:58Z, and main's own `sync-kalshi` lines of that morning. No raw payload was kept, and the session's proxy
refuses Kalshi's host, so every field here comes from a console line.

**Copied from the consoles:**
- **The two events and four tickers.** KXMLBGAME-26OCT161800TBCLE-TB / -CLE and KXMLBGAME-26OCT172000TBCLE-TB / -CLE,
  as the replay's "legs that differ" list names them.
- **The event's two names.** 'Cleveland' and 'Tampa Bay', as the replay lists them for KXMLBGAME-26OCT172000TBCLE.
- **The TB leg of 26OCT172000TBCLE**, as main's sample line printed it: `title` 'Tampa Bay wins', `yes_sub_title`
  'Tampa Bay', `yes_bid_dollars` '0.5400', `yes_ask_dollars` '0.5500', `last_price_dollars` '0.5500'. The quote is kept
  under `quotes`, keyed by the fetch time; it is the only quote the consoles carry.

**Written in the shape of that leg** (no console line shows them):
- each other leg's `title` ("<yes_sub_title> wins");
- the names of 26OCT161800TBCLE. That event was not open on Sunday. Main stored its TB leg as AWAY and its CLE leg as
  HOME on match 50548 on Friday, which these two names give.
- each `event_ticker`: the ticker less its side, as the matcher reads it (the replay prints
  KXMLBGAME-26OCT172000TBCLE's).

**What the tests write themselves, in memory** (no fixture file is edited):
- **A stand-in quote** (0.4900 / 0.5100, no last price) for every leg whose quote the consoles do not carry. The MLB
  path has no spread guard, so the matcher reads only that a leg has a price, and no pinned answer depends on its value.
- **Which events are open at each clock:**
  - Friday 23:25:59Z and Saturday: both events. Main stored four legs on Friday, and addendum 127 item 1 rules the
    Saturday set.
  - Sunday 11:37:58Z: 26OCT172000TBCLE alone, per the replay's "2 open markets in 1 events".
- **The order** in which Kalshi serves the markets on Saturday is not in the consoles. The fixture's order is by event
  date, each event's TB leg first, as Kalshi served Sunday's event (main's sample line is its TB leg). No test serves
  another order: that is beyond addendum 127 item 3(b), and the ledger entry lists it for the architect.
- **The rows and main's four Friday legs:** match, side, ticker and capture time, as the replay lists them. Their
  prices are stand-ins that no test reads.
- **The clocks:**
  - Saturday: step 6's start in each of the three closing receipts that reached it (run_start plus steps 1-5).
  - Friday: main's capture time.
  - Sunday: the replay's fetch time.
