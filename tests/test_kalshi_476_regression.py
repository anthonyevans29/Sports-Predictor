"""#476 regression: the real MLB Kalshi sync on the Tampa Bay at Cleveland series of 2026-10-16..18, today's answers
pinned.

ARCHITECT 2026-10-18 09:58 ET, addendum 127 item 3(a), verbatim: "NO MLB MATCHER CHANGE (Branch 1). The out-of-step
rule refused the one market a clock key would have misplaced; the cost is the one ruled on 10-12 ("while Kalshi has
not settled yesterday's market of a pair, today's is refused"). Branch 2 is not built in any case: its own warning
paragraph is decisive — a clock fixed at market creation identifies nothing about a game that moved. Refusals are
never turned into guesses."
Item 3(b), verbatim: "REGRESSION TESTS, a tests-only PR: the Saturday set verbatim (2 no-game-on-date + 2 behind),
states A1 and A2, the Sunday shape (2 in play), the Friday control (4 placed), the ALCS tests unchanged — today's
answers pinned whatever the receipt says."

How each test runs: the real `python cli.py sync-kalshi`, the MLB closing's step 6, which passes no dates. It is
invoked in process through click, on a scratch SQLite DB of its own (the schema, plus migrate_kalshi_ticker.py's one
ALTER). Only two things are replaced, as in the cause read and its two reviewers' runs:
- the HTTP fetch, KalshiAdapter._get;
- the sync's clock, kalshi_sync.utc_now_naive.
The console is widened so that no line wraps. Every word printed is main's.

The markets are tests/fixtures/kalshi_476/tbcle_markets.json. Its README says what is copied from the operator's
relayed replay and what the tests write themselves.

The rows (the cause read's, section 2), Tampa Bay Rays at Cleveland Guardians:
- 50546: FINISHED, 2026-10-15 17:00Z (Thursday 13:00 ET).
- 50550: 2026-10-18 00:08Z (Saturday 20:08 ET), the start the Saturday receipts carry as stored. On Friday it was
  00:00Z, the first Saturday receipt's target.
- 50548, in each state:
  - the Friday control: SCHEDULED 2026-10-17 00:00Z (Friday 20:00 ET), the start of the receipts' last call on it;
  - the Saturday set (the cause read's state B): SCHEDULED 2026-10-18 21:00Z, moved to Sunday 17:00 ET (addendum 106);
  - state A1: SCHEDULED 2026-10-17 00:00Z, unmoved;
  - state A2: POSTPONED 2026-10-17 00:00Z;
  - the Sunday shape: SCHEDULED 2026-10-18 21:00Z.

Synthetic throwaway DBs only; nothing here reads or writes data/.
"""
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from rich.console import Console
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import cli
from src.adapters.kalshi import KalshiAdapter
from src.db.schema import Base, Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.ingestion import kalshi_sync

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import closing as mc  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "kalshi_476" / "tbcle_markets.json"
Z = datetime.fromisoformat                                                  # naive UTC
E16, E17 = "KXMLBGAME-26OCT161800TBCLE", "KXMLBGAME-26OCT172000TBCLE"

# A quote for every leg the receipts carry none for. On this path (sync_kalshi_mlb: no spread guard) the matcher reads
# only that a leg has a price; no answer below depends on its value.
STAND_IN = {"yes_bid_dollars": "0.4900", "yes_ask_dollars": "0.5100"}

FRIDAY = Z("2026-10-16T23:25:59.203319")         # main's capture of the four legs (replay.txt, "main's newest stored legs")
SUNDAY = Z("2026-10-18T11:37:58")                # the morning replay's fetch (replay.txt)
# Saturday's step 6 (`python cli.py sync-kalshi`) in each of the three closing receipts that reached it: run_start plus
# the seconds of steps 1-5, to the second (20261017T233343Z, -233535Z and -233733Z; the 23:25:29Z run stopped at
# step 1, "start moved").
SATURDAY = [Z("2026-10-17T23:34:24"), Z("2026-10-17T23:36:21"), Z("2026-10-17T23:38:20")]

# main's four legs of Friday 23:25:59Z, as the replay lists them: (match, side, ticker).
MAIN_FRIDAY_LEGS = [(50548, "AWAY", f"{E16}-TB"), (50548, "HOME", f"{E16}-CLE"),
                    (50550, "AWAY", f"{E17}-TB"), (50550, "HOME", f"{E17}-CLE")]
FRIDAY_AT = "2026-10-16 23:25:59.203319"

# main's own sync of 2026-10-18 11:37:58Z (replay.txt, section 3), verbatim.
SUNDAY_RECEIPT = [
    "  sample: ticker='KXMLBGAME-26OCT172000TBCLE-TB' title='Tampa Bay wins' yes_sub_title='Tampa Bay' "
    "yes_bid_dollars='0.5400' yes_ask_dollars='0.5500' last='0.5500'",
    "  series KXMLBGAME · 2 markets · matched 0 · unmatched 0 (of which ambiguous 0) · in-play skipped 2 — unmatched "
    "= wrong date for our window, no scheduled game, or a team/side tie we refused to guess",
]

LEGEND = " — unmatched = wrong date for our window, no scheduled game, or a team/side tie we refused to guess"
# the diagnostic line: the first market's keys, the fixture's fields and its quote's (the stand-in has no last price)
KEYS = "  sample market keys: ['event_ticker', 'ticker', 'title', 'yes_ask_dollars', 'yes_bid_dollars', 'yes_sub_title']"
KEYS_SUNDAY = ("  sample market keys: ['event_ticker', 'last_price_dollars', 'ticker', 'title', 'yes_ask_dollars', "
               "'yes_bid_dollars', 'yes_sub_title']")
HEAD = ["Checking Kalshi status…", "Discovering KXMLBGAME game series…", "  fetching game series KXMLBGAME…"]


def alarm(n_markets, n_due):
    return (f"  ⚠ MATCHED ZERO with {n_markets} markets read and {n_due} unstarted game(s) of the competition inside "
            "the run's window — matcher may be broken (see 2026-09-13 title-format incident). Probe the payload before "
            "trusting 'absent'.")


def summary(markets, matched, unmatched, ambiguous, in_play):
    return (f"  series KXMLBGAME · {markets} markets · matched {matched} · unmatched {unmatched} (of which ambiguous "
            f"{ambiguous}) · in-play skipped {in_play}{LEGEND}")


def sample(ticker, bid, ask, last):
    name = "Tampa Bay" if ticker.endswith("-TB") else "Cleveland"
    return (f"  sample: ticker='{ticker}' title='{name} wins' yes_sub_title='{name}' yes_bid_dollars={bid!r} "
            f"yes_ask_dollars={ask!r} last={last!r}")


# the refusal lines, as main prints them
NO_GAME_E16 = (f"  ✗ {E16}: ticker date 2026-10-16, clock 2026-10-16 18:00 ET; no game of the pair on that date; our "
               "kickoffs 50546 2026-10-15 13:00 ET; 50550 2026-10-17 20:08 ET: refused")
BEHIND_BOTH = (f"  ✗ {E17}: refused behind {E16}, out of step: no game of its two teams on its date 2026-10-16 and "
               "its date 2026-10-16 is before the day of the run 2026-10-17")
BEHIND_DATE = f"  ✗ {E17}: refused behind {E16}, out of step: its date 2026-10-16 is before the day of the run 2026-10-17"


def markets(open_events, at=None):
    """The fixture's markets of the events open at the run, each with its quote: the receipted one where the fixture
    holds one at `at`, else the stand-in."""
    data = json.loads(FIXTURE.read_text())
    quotes = data["quotes"].get(f"{at.isoformat()}Z", {}) if at else {}
    return [{**m, **copy.deepcopy(quotes.get(m["ticker"], STAND_IN))}
            for m in data["markets"] if m["event_ticker"] in open_events]


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A scratch SQLite of its own, with the schema and migrate_kalshi_ticker.py's one ALTER, behind session_scope."""
    import src.db.database as database
    eng = create_engine(f"sqlite:///{tmp_path / 'reg476.db'}", future=True)
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
    monkeypatch.setattr(database, "_engine", eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng, autoflush=False, autocommit=False,
                                                               future=True, expire_on_commit=False))
    yield eng
    eng.dispose()


def seed(eng, g48, s48=MatchStatus.SCHEDULED, g50=Z("2026-10-18T00:08"), s50=MatchStatus.SCHEDULED, legs=True):
    """The three rows of the pair; with `legs`, main's four legs of Friday 23:25:59Z on them (the receipts' stale
    legs: the closing's Desk read them on Saturday). Their prices are stand-ins: no test reads them."""
    with Session(eng) as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="USA", type="LEAGUE")
        cle = Team(sport=Sport.MLB, name="Cleveland Guardians")
        tb = Team(sport=Sport.MLB, name="Tampa Bay Rays")
        s.add_all([comp, cle, tb])
        s.flush()
        for mid, kick, status in ((50546, Z("2026-10-15T17:00"), MatchStatus.FINISHED), (50548, g48, s48),
                                  (50550, g50, s50)):
            s.add(Match(id=mid, sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=kick, status=status,
                        home_team_id=cle.id, away_team_id=tb.id))
        s.flush()
        snaps = []
        for mid, side, ticker in (MAIN_FRIDAY_LEGS if legs else []):
            sn = OddsSnapshot(match_id=mid, market="ML", selection=side, devig_prob=0.5, line=None, n_books=1,
                              captured_at=FRIDAY, source="kalshi", yes_bid=0.49, yes_ask=0.51)
            s.add(sn)
            snaps.append((sn, ticker))
        s.flush()
        for sn, ticker in snaps:
            s.execute(text("UPDATE odds_snapshots SET market_ticker = :t WHERE id = :i"), {"t": ticker, "i": sn.id})
        s.commit()


def stored_legs(eng):
    with eng.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "SELECT match_id, selection, market_ticker, captured_at FROM odds_snapshots WHERE source = 'kalshi' "
            "ORDER BY match_id, selection, captured_at"))]


def sync(monkeypatch, served, now):
    """`python cli.py sync-kalshi` at `now`, Kalshi serving `served`: (exit code, console lines, HTTP paths called)."""
    calls = []

    def _get(self, path, params=None):
        calls.append(path)
        if path == "exchange/status":
            return {"exchange_active": True, "trading_active": True}
        if path == "search/filters_by_sport":
            return {}
        assert path == "markets" and params == {"series_ticker": "KXMLBGAME", "status": "open", "limit": 200}, params
        return {"markets": copy.deepcopy(served), "cursor": ""}

    monkeypatch.setattr(KalshiAdapter, "_get", _get)
    monkeypatch.setattr(kalshi_sync, "utc_now_naive", lambda: now)
    monkeypatch.setattr(cli, "console", Console(width=1000, color_system=None))
    res = CliRunner().invoke(cli.cli, ["sync-kalshi"])
    return res.exit_code, res.output.splitlines(), calls


def ran_clean(code, lines, calls):
    """The step exits 0 and the closing reads no failure on its console (closing.reported_failure), as in every
    Saturday receipt: three HTTP calls, all served here."""
    assert code == 0, lines
    assert mc.reported_failure(["sync-kalshi"], lines) is None, lines
    assert calls == ["exchange/status", "search/filters_by_sport", "markets"], calls


def nothing_new_stored(eng):
    """The run stored no leg: the newest Kalshi legs are still main's of Friday 23:25:59Z."""
    assert stored_legs(eng) == [(m, s, t, FRIDAY_AT) for m, s, t in sorted(MAIN_FRIDAY_LEGS)]


# ------------------------------------------------------------------------------------------- the Friday control --

def test_the_friday_control_places_the_four_legs_main_stored(db, monkeypatch):
    """Friday 2026-10-16 23:25:59Z, both rows at their Friday times, both events open: the four legs main stored, on
    the rows main stored them on, captured at the run's clock.

    Addendum 130 item 1(c) has since found these rows crossed: "The four legs captured Friday 23:25Z sit on the wrong
    rows: 26OCT161800 belongs to 50550, 26OCT172000 to 50548." (#594). The pin is today's answer, as item 3(b) rules
    ("whatever the receipt says"); a change of the key, such as the game-number lane of addendum 130 item 2(b), moves
    it under its own ruling."""
    seed(db, Z("2026-10-17T00:00"), g50=Z("2026-10-18T00:00"), legs=False)
    served = markets({E16, E17})
    code, lines, calls = sync(monkeypatch, served, FRIDAY)
    ran_clean(code, lines, calls)
    assert lines == HEAD + [
        "  4 open game markets", KEYS, sample(f"{E16}-TB", "0.4900", "0.5100", None),
        "  3 stored MLB games on the events' days",
        "  refused: none",
        "✓ Kalshi: 4 prices stored",
        summary(4, 4, 0, 0, 0)]
    assert stored_legs(db) == [(m, s, t, FRIDAY_AT) for m, s, t in sorted(MAIN_FRIDAY_LEGS)]


# ---------------------------------------------------------------------------------------------- the Saturday set --

@pytest.mark.parametrize("now", SATURDAY, ids=[f"{t:%H%M%S}Z" for t in SATURDAY])
def test_the_saturday_set_is_two_no_game_on_the_date_and_two_behind(db, monkeypatch, now):
    """The cause read's state B, the state the laptop held at Saturday's step 6: 50548 moved to Sunday 17:00 ET.
    26OCT161800TBCLE fits no game on its date (50546 and 50550 are a day either side); it is out of step for both
    reasons, so 26OCT172000TBCLE, whose date gives it exactly one game (50550), is refused behind it. Nothing is placed,
    nothing counts as ambiguous, and 50550's newest legs are still Friday's: the Desk's "stale prices"."""
    seed(db, Z("2026-10-18T21:00"))
    code, lines, calls = sync(monkeypatch, markets({E16, E17}), now)
    ran_clean(code, lines, calls)
    assert lines == HEAD + [
        "  4 open game markets", KEYS, sample(f"{E16}-TB", "0.4900", "0.5100", None),
        "  3 stored MLB games on the events' days",
        "  refused, by reason:",
        "       2  behind an event of the same two names out of step",
        "       2  no game of the pair on the ticker's date",
        NO_GAME_E16,
        BEHIND_BOTH,
        alarm(4, 2),
        "✓ Kalshi: 0 prices stored",
        summary(4, 0, 4, 0, 0)]
    nothing_new_stored(db)


def test_the_saturday_set_in_the_other_order_gives_the_same_answer(db, monkeypatch):
    """Kalshi's order of Saturday's four markets is not in the receipts: served the other way round, the counts and
    both refusal lines are the same; only their order on the console follows the events'."""
    seed(db, Z("2026-10-18T21:00"))
    code, lines, calls = sync(monkeypatch, markets({E16, E17})[::-1], SATURDAY[0])
    ran_clean(code, lines, calls)
    assert lines[lines.index("  refused, by reason:"):] == [
        "  refused, by reason:",
        "       2  behind an event of the same two names out of step",
        "       2  no game of the pair on the ticker's date",
        BEHIND_BOTH,
        NO_GAME_E16,
        alarm(4, 2),
        "✓ Kalshi: 0 prices stored",
        summary(4, 0, 4, 0, 0)]
    nothing_new_stored(db)


# --------------------------------------------------------------------------------------------- states A1 and A2 --

def test_state_a1_unmoved_is_two_in_play_and_two_behind(db, monkeypatch):
    """50548 unmoved, SCHEDULED at Friday 20:00 ET: 26OCT161800TBCLE's date picks it and its kickoff has passed (in
    play); its date is before the run's day, so 26OCT172000TBCLE is refused behind it for that reason alone."""
    seed(db, Z("2026-10-17T00:00"))
    code, lines, calls = sync(monkeypatch, markets({E16, E17}), SATURDAY[0])
    ran_clean(code, lines, calls)
    assert lines == HEAD + [
        "  4 open game markets", KEYS, sample(f"{E16}-TB", "0.4900", "0.5100", None),
        "  3 stored MLB games on the events' days",
        "  refused, by reason:",
        "       2  behind an event of the same two names out of step",
        "       2  in play (our kickoff has passed)",
        BEHIND_DATE,
        alarm(4, 1),
        "✓ Kalshi: 0 prices stored",
        summary(4, 0, 2, 0, 2)]
    nothing_new_stored(db)


def test_state_a2_postponed_is_two_no_game_on_the_date_and_two_behind(db, monkeypatch):
    """50548 POSTPONED on Friday 20:00 ET: a postponed row is not a game (addendum 50 item 6(c)), so the answer is the
    Saturday set's, line for line, with one unstarted game in the window."""
    seed(db, Z("2026-10-17T00:00"), MatchStatus.POSTPONED)
    code, lines, calls = sync(monkeypatch, markets({E16, E17}), SATURDAY[0])
    ran_clean(code, lines, calls)
    assert lines == HEAD + [
        "  4 open game markets", KEYS, sample(f"{E16}-TB", "0.4900", "0.5100", None),
        "  3 stored MLB games on the events' days",
        "  refused, by reason:",
        "       2  behind an event of the same two names out of step",
        "       2  no game of the pair on the ticker's date",
        NO_GAME_E16,
        BEHIND_BOTH,
        alarm(4, 1),
        "✓ Kalshi: 0 prices stored",
        summary(4, 0, 4, 0, 0)]
    nothing_new_stored(db)


# ------------------------------------------------------------------------------------------------ the Sunday shape --

@pytest.mark.parametrize("s50", [MatchStatus.FINISHED, MatchStatus.SCHEDULED], ids=["50550-finished", "50550-scheduled"])
def test_the_sunday_shape_is_two_in_play_and_prints_main_s_own_lines(db, monkeypatch, s50):
    """Sunday 11:37:58Z: 26OCT161800TBCLE has left the open list; 26OCT172000TBCLE is open, its TB leg at the receipted
    0.54/0.55. Its date gives 50550, whose kickoff has passed: 2 in play, nothing behind, nothing placed. 50550's status
    at that hour is not in the receipts; the answer is the same either way. The sample line and the summary line are
    main's own of that morning, byte for byte."""
    seed(db, Z("2026-10-18T21:00"), s50=s50)
    code, lines, calls = sync(monkeypatch, markets({E17}, at=SUNDAY), SUNDAY)
    ran_clean(code, lines, calls)
    assert lines == HEAD + [
        "  2 open game markets", KEYS_SUNDAY, SUNDAY_RECEIPT[0],
        "  3 stored MLB games on the events' days",
        "  refused, by reason:",
        "       2  in play (our kickoff has passed)",
        alarm(2, 1),
        "✓ Kalshi: 0 prices stored",
        SUNDAY_RECEIPT[1]]
    nothing_new_stored(db)
