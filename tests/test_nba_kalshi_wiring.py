"""THE NBA'S MARKET-ONLY WIRING, the Kalshi and host half (ARCHITECT 2026-11-05, addendum 261 items 0 and 1(b);
2026-11-06, addendum 271 item 3(h), addendum 272 items 3-4; lane basketball-market-only, #839).

The series "NBA": "KXNBAGAME" READ on #839's series listing; no fee M until the published schedule is read; the shared
matcher on the 30 franchise names the provider serves, ambiguity refused by its sentinel; pairing by the stored kickoff
instant read as a US Eastern day and the two names, never the provider's date string; `sync-kalshi-nba`; the hourly
capture tier; the PAPER line and coverage's NBA line (totals SCHEDULED + FINISHED + POSTPONED, not CANCELLED; the day
the Kalshi ticker's date names); results-tally's close record on the two-way rule, as NHL's; the chain nba-daily and its
timer, shipped not enabled.

Every Kalshi market and every game here is SYNTHETIC: the Kalshi-side spellings (city forms, "Los Angeles L" / "Los
Angeles C" on the MLB pattern) and the ticker suffixes (AAA, BBB) are invented for the test, not read from any receipt;
only the 30 franchise names are public names (the list #839 served). The throwaway DBs only (tests/conftest.py's, or a
per-test file); no network."""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))

import chains  # noqa: E402

from src.ingestion import kalshi_match as km  # noqa: E402
from src.walters import venue  # noqa: E402
from tests import test_coverage_map as tcm  # noqa: E402
from tests.test_coverage_map import env  # noqa: E402,F401  (a fixture: the scratch coverage DB, roadmap, registry)
from tests.test_record_vs_close import iso_db  # noqa: E402,F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

# The 30 franchises as the provider names them (public names; #839's /teams listing for 'NBA' 2026-2027).
FRANCHISES = (
    "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", "Chicago Bulls", "Cleveland Cavaliers",
    "Dallas Mavericks", "Denver Nuggets", "Detroit Pistons", "Golden State Warriors", "Houston Rockets",
    "Indiana Pacers", "Los Angeles Clippers", "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat",
    "Milwaukee Bucks", "Minnesota Timberwolves", "New Orleans Pelicans", "New York Knicks", "Oklahoma City Thunder",
    "Orlando Magic", "Philadelphia 76ers", "Phoenix Suns", "Portland Trail Blazers", "Sacramento Kings",
    "San Antonio Spurs", "Toronto Raptors", "Utah Jazz", "Washington Wizards")


def city_form(name: str) -> str:
    """A SYNTHETIC Kalshi-side spelling: the city alone, the two Los Angeles franchises told apart by an initial (the
    MLB title pattern, "Los Angeles D"). Not a receipt: Kalshi's NBA yes_sub_title spellings are on none yet."""
    if name.startswith("Los Angeles "):
        return f"Los Angeles {name.split()[-1][0]}"
    return " ".join(name.split()[:-1]) if not name.endswith("Trail Blazers") else "Portland"


_IDS: dict[str, int] = {}


def _team(name):
    return NS(id=_IDS.setdefault(name, len(_IDS) + 1), name=name)


def game(gid, away, home, kick, status="scheduled"):
    h, a = _team(home), _team(away)
    return NS(id=gid, utc_date=kick, home_team=h, away_team=a, home_team_id=h.id, away_team_id=a.id, status=status)


def event(stamp, legs, series="KXNBAGAME", bid="0.40", ask="0.42"):
    """One synthetic Kalshi event: a market per (ticker suffix, yes_sub_title), each titled "<Team> wins"."""
    e = f"{series}-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "occurrence_datetime": None, "yes_bid_dollars": bid, "yes_ask_dollars": ask} for sfx, name in legs]


def run(markets, games, now, hours=48):
    return km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(hours=hours))


def placed(res):
    return {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()}


Z = datetime.fromisoformat                                         # naive UTC


# ---- the series and its fee M ----------------------------------------------------------------------------------------

def test_the_series_is_read_from_the_receipt_and_its_fee_m_is_not_assumed():
    """271 item 3(h): "NBA": "KXNBAGAME". 261 item 0 / 268 item 1(iii): the M from the published schedule, never the
    listing; the repo holds no schedule copy, so KXNBAGAME is unlisted. 261 item 0: "READ from the schedule, never
    assumed": a series that IS mapped but whose M is not listed carries no M and no executable cost (taker and maker,
    both sides); the quotes themselves are kept, since they are the venue's own."""
    from src.ingestion.kalshi_replay import shared_series
    from src.ingestion.kalshi_sync import series_competition
    assert venue.KALSHI_SERIES_BY_COMPETITION["NBA"] == "KXNBAGAME"
    assert series_competition("KXNBAGAME") == "NBA" and shared_series()["KXNBAGAME"] == "NBA"
    assert "KXNBAGAME" not in venue.KALSHI_FEE_M
    src = (ROOT / "src" / "walters" / "venue.py").read_text()
    assert "KXNBAGAME · 'NBA Game'" in src and "#839" in src           # the receipt cited beside the entry
    e = venue.kalshi_exec(0.53, 0.55, "NBA", two_way=True)
    assert (e["fee_series"], e["fee_m_taker"], e["fee_m_maker"]) == ("KXNBAGAME", None, None)
    assert (e["exec_cost_taker"], e["exec_cost_maker"], e["exec_cost_taker_away"], e["exec_cost_maker_away"]) == (
        None, None, None, None)
    assert (e["kalshi_bid"], e["kalshi_ask"], e["away_bid"], e["away_ask"]) == (0.53, 0.55, 0.45, 0.47)
    assert set(e) == set(venue.kalshi_exec(0.53, 0.55, "NHL", two_way=True))   # the row's shape is unchanged


def test_the_unread_m_rule_is_scoped_to_mapped_unlisted_series_only():
    """Every listed series keeps its ruled M (#93) and an UNMAPPED competition keeps today's default (taker M=1, maker
    null): the null-cost rule reaches only a series in KALSHI_SERIES_BY_COMPETITION with no KALSHI_FEE_M entry."""
    unread = [s for s in venue.KALSHI_SERIES_BY_COMPETITION.values() if s not in venue.KALSHI_FEE_M]
    assert unread == ["KXNBAGAME"]
    for comp, series in venue.KALSHI_SERIES_BY_COMPETITION.items():
        if series in venue.KALSHI_FEE_M:
            e = venue.kalshi_exec(0.53, 0.55, comp, two_way=True)
            assert (e["fee_m_taker"], e["fee_m_maker"]) == venue.KALSHI_FEE_M[series]
            assert e["exec_cost_taker"] is not None and e["exec_cost_taker_away"] is not None
    for comp in ("CL", "UNL", None):
        u = venue.kalshi_exec(0.53, 0.55, comp)
        assert (u["fee_series"], u["fee_m_taker"], u["fee_m_maker"]) == (None, 1.0, None)
        assert u["exec_cost_taker"] == venue.kalshi_exec(0.53, 0.55, "NHL")["exec_cost_taker"]


def test_an_nba_window_card_row_carries_no_taker_cost_until_the_m_is_read(iso_db, monkeypatch):
    """The hourly window card (window.build_card -> export._fixture_row -> kalshi_exec) is what the Cockpit renders:
    an NBA row with both Kalshi legs two-sided shows the venue's quotes and NO executable cost under KXNBAGAME."""
    from src.db import database
    from src.db.database import session_scope
    # iso_db swaps SessionLocal only; has_kalshi_ticker inspects the suite's shared engine, which an earlier test may
    # have migrated. This DB was made from the metadata, which has no market_ticker column: say so.
    monkeypatch.setattr(database, "has_kalshi_ticker", lambda: False)
    from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
    from src.timeutil import utc_now_naive
    from src.walters.window import build_card
    now = utc_now_naive()
    with session_scope() as s:
        comp = Competition(sport=Sport.BASKETBALL, code="NBA", name="NBA", area="Synthland", type="LEAGUE")
        h, a = Team(sport=Sport.BASKETBALL, name="Home Synth"), Team(sport=Sport.BASKETBALL, name="Away Synth")
        s.add_all([comp, h, a])
        s.flush()
        m = Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026", utc_date=now + timedelta(hours=5),
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        for sel, bid, ask in (("HOME", 0.55, 0.57), ("AWAY", 0.43, 0.45)):
            s.add(OddsSnapshot(match_id=m.id, source="kalshi", market="ML", selection=sel,
                               captured_at=now - timedelta(minutes=5), yes_bid=bid, yes_ask=ask,
                               devig_prob=(bid + ask) / 2, n_books=1))
    rows = [r for r in build_card(now=now, hours=24)["fixtures"] if r.get("competition") == "NBA"]
    assert len(rows) == 1, rows
    r = rows[0]
    assert (r["kalshi_bid"], r["kalshi_ask"]) == (0.55, 0.57)
    assert (r["fee_series"], r["fee_m_taker"], r["fee_m_maker"]) == ("KXNBAGAME", None, None)
    assert all(r[k] is None for k in ("exec_cost_taker", "exec_cost_maker", "exec_cost_taker_away",
                                      "exec_cost_maker_away")), r


def test_the_k_track_receipt_reads_an_nba_home_away_ladder_as_complete():
    """k-track-receipt reads every stored pre-kickoff Kalshi 1X2/ML snapshot of every competition, so the NBA's
    HOME+AWAY ladders reach its completeness rule: a two-way ladder of two legs is COMPLETE and two-sided, as NHL's,
    never 'incomplete ladder (a leg missing)'. The two-way set is the shared path's own (kalshi_replay.shared_series:
    the series map less soccer), so the five existing two-way competitions read exactly as before and PL stays
    three-way. The NBA's costs are null until its M is read (above), so neither basis prices it."""
    from src.walters.k_receipt import ladder_row
    two = {"HOME": NS(yes_bid=0.55, yes_ask=0.57), "AWAY": NS(yes_bid=0.43, yes_ask=0.45)}
    t = Z("2026-11-06T20:00")
    for comp in ("MLB", "NFL", "NHL", "NCAA", "NBA"):
        r = ladder_row(comp, t, two, [], [])
        assert (r["complete"], r["two_sided"]) == (True, True), (comp, r)
        assert r["fee_clear"]["book"] == {"reason": "no book session at or before the capture"}, (comp, r)
    nba = ladder_row("NBA", t, two, [], [])
    assert all(v["taker"] is None and v["maker"] is None for v in nba["legs"].values()), nba
    for comp in ("PL", "CL", "UNL"):
        assert ladder_row(comp, t, two, [], [])["complete"] is False      # a three-way ladder lacks its DRAW leg


def test_no_nba_call_exists_to_price():
    """The record is PAPER (261 item 1(f): no model declared): no Desk family, and the NBA's chains export nothing."""
    from src.walters import desk_policy
    assert not {"NBA", "BASKETBALL"} & set(desk_policy.POLICY)
    for name in ("nba-daily",):
        assert all(s[0] in ("sync-matches", "sync-kalshi-nba") for s in chains.CHAINS[name]["steps"])
    assert not any("NBA" in s and s[0].startswith(("export", "predict", "improve"))
                   for ch in chains.CHAINS.values() for s in ch.get("steps") or [])


# ---- the matcher on the 30 served names --------------------------------------------------------------------------------

PAIRS = [(FRANCHISES[i], FRANCHISES[i + 1]) for i in range(0, 30, 2)]   # 15 games, every franchise once
# the hardest same-day neighbours of the 30 put on one slate: the two Los Angeles franchises against each other, the
# two New Yorks' cities beside New Orleans, both Los Angeles and both "-a" cities in other games
PAIRS[6] = ("Los Angeles Clippers", "Los Angeles Lakers")


def _slate(form):
    t0 = Z("2026-11-06T00:30")                                     # 19:30 ET on 11-05: the ticker's date is 11-05
    games, markets = [], []
    for n, (away, home) in enumerate(PAIRS):
        games.append(game(9100 + n, away, home, t0 + timedelta(minutes=30 * (n % 4))))
        markets += event(f"26NOV05X{n:02d}AAABBB", [("AAA", form(away)), ("BBB", form(home))])
    return games, markets


@pytest.mark.parametrize("form", [lambda n: n, city_form], ids=["served-name", "synthetic-city-form"])
def test_every_franchise_is_placed_on_its_own_game_and_only_there(form):
    """271 item 3(h), "the matcher's NBA codes from the 30 served names": the shared matcher is name-based and holds no
    code table, so the codes ARE the stored names. A slate of all 30 (one day, both Los Angeles franchises in one game)
    places every event on its own game, both sides, nothing refused."""
    games, markets = _slate(form)
    res = run(markets, games, now=Z("2026-11-05T15:00"))
    assert not res.refused, (res.refused, res.why)
    want = {}
    for n in range(15):
        want[(9100 + n, "AWAY")] = "AAA"
        want[(9100 + n, "HOME")] = "BBB"
    assert placed(res) == want


def test_the_two_los_angeles_franchises_are_told_apart_by_the_initial_or_refused():
    """Lakers v Clippers: "Los Angeles L" / "Los Angeles C" fit one each (the initial-letter tiebreak); an event that
    names "Los Angeles" twice names one team, never a pair (NO_PAIR), never guessed."""
    g = game(9200, "Los Angeles Clippers", "Los Angeles Lakers", Z("2026-11-06T03:30"))
    ok = run(event("26NOV05AAABBB", [("AAA", "Los Angeles C"), ("BBB", "Los Angeles L")]), [g], now=Z("2026-11-05T15:00"))
    assert placed(ok) == {(9200, "AWAY"): "AAA", (9200, "HOME"): "BBB"} and not ok.refused
    flipped = run(event("26NOV05AAABBB", [("AAA", "Los Angeles L"), ("BBB", "Los Angeles C")]), [g],
                  now=Z("2026-11-05T15:00"))
    assert placed(flipped) == {(9200, "HOME"): "AAA", (9200, "AWAY"): "BBB"}
    same = run(event("26NOV05AAABBB", [("AAA", "Los Angeles"), ("BBB", "Los Angeles")]), [g], now=Z("2026-11-05T15:00"))
    assert not same.placed and same.refused == {km.NO_PAIR: 2}


def test_a_shared_best_fit_is_refused_by_the_sentinel_never_guessed():
    """'Los Angeles' + 'Boston' fits Celtics @ Lakers and Celtics @ Clippers alike (a day apart, both on the event's
    day window): two pairs share the best fit -> PAIR_TIE, both markets refused and counted."""
    a = game(9301, "Boston Celtics", "Los Angeles Lakers", Z("2026-11-06T03:30"))
    b = game(9302, "Boston Celtics", "Los Angeles Clippers", Z("2026-11-07T03:30"))
    res = run(event("26NOV05AAABBB", [("AAA", "Boston"), ("BBB", "Los Angeles")]), [a, b], now=Z("2026-11-05T15:00"))
    assert not res.placed and res.refused == {km.PAIR_TIE: 2}


# ---- pairing by the kickoff instant and the two names (272 item 4) ---------------------------------------------------

def test_pairing_reads_the_stored_kickoff_as_a_us_eastern_day_never_the_providers_date_string():
    """272 item 4: "the Kalshi matcher pairs by the kickoff instant and the two names, never by the provider's date
    string". The provider files the US evening of 11-05 under the UTC date 2026-11-06; the stored kickoff (from the
    served timestamp, naive UTC) is 2026-11-06 00:30Z = 19:30 ET on 11-05, the ticker's own date. The same pair's
    next meeting (stored 2026-11-07 00:30Z, 11-06 ET) takes the 26NOV06 event, not the 26NOV05 one."""
    first = game(9401, "Boston Celtics", "New York Knicks", Z("2026-11-06T00:30"))
    second = game(9402, "Boston Celtics", "New York Knicks", Z("2026-11-07T00:30"))
    names = [("AAA", "Boston"), ("BBB", "New York")]
    res = run(event("26NOV05AAABBB", names) + event("26NOV06AAABBB", names), [first, second],
              now=Z("2026-11-05T15:00"), hours=60)
    assert {k: mk["event_ticker"] for k, mk in res.placed.items()} == {
        (9401, "AWAY"): "KXNBAGAME-26NOV05AAABBB", (9401, "HOME"): "KXNBAGAME-26NOV05AAABBB",
        (9402, "AWAY"): "KXNBAGAME-26NOV06AAABBB", (9402, "HOME"): "KXNBAGAME-26NOV06AAABBB"}, res.refused
    assert km.et_day(first.utc_date).isoformat() == "2026-11-05"      # the UTC date 11-06 is never the day read
    # the games a sync reads carry no provider date string at all: Match has utc_date, never the served `date`
    from src.db.schema import Match
    assert "utc_date" in Match.__table__.c and "date" not in Match.__table__.c


def test_a_cancelled_or_postponed_row_takes_no_market():
    """A CANC listing (an FT twin's or a real cancellation) is not a game for the matcher (addendum 50 6(c))."""
    real = game(9501, "Boston Celtics", "New York Knicks", Z("2026-11-06T00:30"))
    canc = game(9502, "Boston Celtics", "New York Knicks", Z("2026-11-06T00:00"), status="cancelled")
    res = run(event("26NOV05AAABBB", [("AAA", "Boston"), ("BBB", "New York")]), [canc, real], now=Z("2026-11-05T15:00"))
    assert set(placed(res)) == {(9501, "AWAY"), (9501, "HOME")} and not res.refused


# ---- sync-kalshi-nba ----------------------------------------------------------------------------------------------------

@pytest.fixture
def kalshi_fake(monkeypatch):
    from src.adapters.kalshi import KalshiAdapter
    box = {"markets": [], "asked": []}
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series",
                        lambda self, s: box["asked"].append(s) or box["markets"])
    return box


@pytest.fixture
def nba_db():
    """conftest's throwaway DB (the one has_kalshi_ticker reads), every NBA row removed before and after."""
    from src.db.database import init_db
    init_db()
    _clear()
    yield
    _clear()


def _clear():
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, OddsSnapshot, Sport, Team
    with session_scope() as s:
        comp_ids = [c.id for c in s.query(Competition).filter(Competition.code == "NBA")]
        ids = [m.id for m in s.query(Match).filter(Match.competition_id.in_(comp_ids))]
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.sport == Sport.BASKETBALL).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.code == "NBA").delete(synchronize_session=False)


def _nba(s, games):
    """The NBA competition (sport BASKETBALL) and its games: [(id, away, home, kickoff, status, hs, as, raw)]."""
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    comp = Competition(sport=Sport.BASKETBALL, code="NBA", name="NBA", area="Synthland", type="LEAGUE")
    s.add(comp)
    s.flush()
    teams = {}
    for gid, away, home, ko, st, hs, as_, raw in games:
        for nm in (away, home):
            if nm not in teams:
                teams[nm] = Team(sport=Sport.BASKETBALL, name=nm)
                s.add(teams[nm])
        s.flush()
        s.add(Match(id=gid if gid >= 9700 else None, sport=Sport.BASKETBALL, competition_id=comp.id, season="2026", utc_date=ko,
                    status=st or MatchStatus.SCHEDULED, home_team_id=teams[home].id, away_team_id=teams[away].id,
                    home_score=hs, away_score=as_, status_raw=raw))
    s.flush()
    return comp


def test_sync_kalshi_nba_refuses_without_the_competition(nba_db, kalshi_fake):
    import cli
    kalshi_fake["markets"] = event("26NOV05AAABBB", [("AAA", "Boston"), ("BBB", "New York")])
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-nba"])
    assert out.exit_code == 0 and "✗ Kalshi NBA: competition NBA not in DB" in out.output, out.output
    assert kalshi_fake["asked"] == ["KXNBAGAME"]


def test_sync_kalshi_nba_stores_both_sides_on_the_ml_market(nba_db, kalshi_fake, monkeypatch):
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(kalshi_sync, "utc_now_naive", lambda: Z("2026-11-05T15:00"))
    with session_scope() as s:
        comp = _nba(s, [(9601, "Boston Celtics", "New York Knicks", Z("2026-11-06T00:30"), None, None, None, "NS")])
        mid = s.query(Match).filter(Match.competition_id == comp.id).one().id
    kalshi_fake["markets"] = (event("26NOV05AAABBB", [("AAA", "Boston"), ("BBB", "New York")], bid="0.30", ask="0.32")
                              + event("26NOV05CCCDDD", [("CCC", "Nowhere"), ("DDD", "Elsewhere")]))
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-nba"])
    assert out.exit_code == 0, out.output
    assert "✓ Kalshi NBA: 2 prices stored" in out.output and "series KXNBAGAME · 4 markets" in out.output, out.output
    assert km.NO_FIT in out.output                                    # the refusal counted by its reason, printed
    with session_scope() as s:
        snaps = {x.selection: (x.market, x.source, x.yes_bid, x.yes_ask)
                 for x in s.query(OddsSnapshot).filter(OddsSnapshot.match_id == mid)}
    assert snaps == {"AWAY": ("ML", "kalshi", 0.30, 0.32), "HOME": ("ML", "kalshi", 0.30, 0.32)}


# ---- the chain, the capture tier, the timer ---------------------------------------------------------------------------

def test_nba_daily_is_the_two_day_utc_window_then_its_kalshi_sync():
    ch = chains.CHAINS["nba-daily"]
    assert ch["steps"] == [
        ["sync-matches", "--competition", "NBA", "--season", "2026", "--date-from", "{yesterday}", "--date-to",
         "{yesterday}"],
        ["sync-matches", "--competition", "NBA", "--season", "2026", "--date-from", "{today}", "--date-to", "{today}"],
        ["sync-kalshi-nba"]]
    assert ch["backup"] == "daily" and "active_from" not in ch and "go_on" not in ch
    assert chains.COVERAGE_STEP not in ch["steps"]                     # intl-daily's write is the one (addendum 225)
    assert "sync-kalshi-nba" in chains.UNMETERED
    assert chains.WINDOW_KALSHI["NBA"] == [["sync-kalshi-nba"]] and "NBA" not in chains.WINDOW_KALSHI_CAPTURE_ONLY


def _calendars():
    out = {}
    for p in sorted((HOSTING / "systemd").glob("*.timer")):
        out[p.stem] = re.findall(r"^OnCalendar=(.+)$", p.read_text(), re.M)
    return out


def test_the_timer_minute_is_off_every_existing_timer_and_before_the_coverage_write():
    """261 item 1(b): "at a UTC minute off every existing timer". sp-closing-watch ticks every minute (its exemption
    by name) and sp-window / sp-cup-observe on the five-minute marks, so "off" reads: no other timer fires at :47, the
    minute is no five-minute mark, and 06:47 UTC is before intl-daily's 07:20 UTC `coverage --json`."""
    cal = _calendars()
    assert cal["sp-nba-daily"] == ["*-*-* 06:47:00 UTC"]
    assert "Unit=sp-chain@nba-daily.service" in (HOSTING / "systemd" / "sp-nba-daily.timer").read_text()
    minutes = set()
    for name, lines in cal.items():
        if name in ("sp-nba-daily", "sp-closing-watch"):
            continue
        for ln in lines:
            m = re.search(r"(\d{2}|\*):(\d{2}):00", ln)
            minutes.add(int(m.group(2)))
    assert 47 not in minutes and 47 % 5 != 0, sorted(minutes)
    assert cal["sp-intl-daily"] == ["*-*-* 07:20:00 UTC"]


def test_the_timer_ships_on_t11_timers_and_the_schedule_table():
    """Shipped as the repo ships a timer the architect's block enables: on T11's TIMERS (install.sh enables nothing),
    one Schedule row, and the live-host recipe ending with the timers.enabled line (addendum 168 item 2)."""
    import sp_common as c
    lists = c.t11_lists()
    assert "sp-nba-daily.timer" in lists["TIMERS"] and "sp-nba-daily.timer" not in lists["MLB_LAPTOP_ONLY"]
    h1 = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    assert len(re.findall(r"^\| sp-nba-daily \|", h1, re.M)) == 1
    assert "echo sp-nba-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled" in h1
    assert "systemctl enable" not in (HOSTING / "install.sh").read_text()          # install.sh enables nothing


def test_the_window_chain_captures_nba_kalshi_near_kickoff(tmp_path, monkeypatch):
    """The capture tier (261 item 0): an NBA game inside the window's near tier plans its schedule check and its
    Kalshi capture; the odds step is the base adapter's no-op (api_basketball reads no /odds)."""
    import sp_common as c
    import sp_run
    now = datetime(2026, 11, 5, 20, 0)
    db = tmp_path / "w.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE competitions(id INTEGER PRIMARY KEY, sport TEXT, code TEXT);"
                      "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, season TEXT, status TEXT,"
                      " utc_date TEXT);")
    con.execute("INSERT INTO competitions VALUES (1, 'BASKETBALL', 'NBA')")
    con.execute("INSERT INTO matches(competition_id, season, status, utc_date) VALUES (1, '2026', 'SCHEDULED', ?)",
                ((now + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),))
    con.commit()
    con.close()
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    steps = [" ".join(s) for s in sp_run.window_plan(now)["steps"]]
    assert "sync-matches --competition NBA --season 2026 --date-from 2026-11-05 --date-to 2026-11-05" in steps
    assert "sync-kalshi-nba" in steps
    from src.adapters.api_basketball import APIBasketballAdapter
    from src.adapters.base import DataAdapter
    assert APIBasketballAdapter.list_odds is DataAdapter.list_odds


# ---- the close's record and coverage's NBA line ------------------------------------------------------------------------

def test_the_close_record_scores_nba_on_the_two_way_rule_as_nhls(iso_db):
    """261 item 0: "results-tally's close record (the two-way rule, as NHL's)". FT and AOT totals both decide; a
    CANCELLED listing (an FT twin's) is never read, whatever quotes it holds."""
    import math
    from src.db.database import session_scope
    from src.db.schema import MatchStatus, OddsSnapshot
    from src.walters import paper
    ko = Z("2026-11-04T00:30")
    with session_scope() as s:
        _nba(s, [(9701, "Atlanta Hawks", "Boston Celtics", ko, MatchStatus.FINISHED, 112, 106, "FT"),
                 (9702, "Chicago Bulls", "Denver Nuggets", ko, MatchStatus.FINISHED, 118, 120, "AOT"),
                 (9703, "Atlanta Hawks", "Boston Celtics", ko - timedelta(minutes=30), MatchStatus.CANCELLED,
                  None, None, "CANC")])
        for mid, bid, ask in ((9701, 0.60, 0.61), (9702, 0.44, 0.45), (9703, 0.50, 0.51)):
            s.add(OddsSnapshot(match_id=mid, market="ML", selection="HOME", devig_prob=0.5, n_books=1,
                               captured_at=ko - timedelta(hours=1), source="kalshi", yes_bid=bid, yes_ask=ask))
    rec = paper.close_record(30, now=Z("2026-11-06T12:00"))
    r = rec["NBA"]
    assert r["kind"] == paper.KIND_TWO and r["finished"] == 2 and r["n"] == 2 and r["fav_w"] == 2
    # 9701 HOME won at a 0.605 close; 9702 (AOT) AWAY won, the close's AWAY = 1 - 0.445
    assert r["ll_sum"] == pytest.approx(-math.log(0.605) - math.log(1 - 0.445))
    assert "NBA n=2" in paper.close_record_console(rec, 30)


def test_coverage_prints_nba_market_only_with_paper_lines_and_counts_postponed_not_cancelled(env, monkeypatch):
    """272 item 3: "the coverage page's totals count SCHEDULED + FINISHED + POSTPONED, not CANCELLED". 272 item 4 /
    271 3(d): the coverage day is the venue's ticker date: a 00:30Z kickoff is on the previous US Eastern day. NBA is
    MARKET-ONLY from export._MARKET_ONLY_REASON, so its PAPER header and one PAPER line per counted game follow."""
    monkeypatch.setitem(tcm.COMPS, "NBA", 99)
    tcm.make_db(env, [(901, "NBA", "2026-10-17 23:00", "SCHEDULED"),       # 19:00 ET on 10-17
                     (902, "NBA", "2026-10-18 00:30", "FINISHED"),        # 20:30 ET on 10-17: the ticker's 10-17
                     (903, "NBA", "2026-10-17 23:30", "POSTPONED"),
                     (904, "NBA", "2026-10-17 23:30", "CANCELLED"),
                     (905, "NBA", "2026-10-17 03:30", "FINISHED"),        # 23:30 ET on 10-16: not this day
                     (501, "NHL", "2026-10-17 23:00", "POSTPONED")])      # NHL: closing.VOID unchanged
    rc, out = tcm.run("--date", tcm.DAY)
    assert rc == 0, out
    nba = tcm.line_of(out, "NBA")
    assert nba.startswith("NBA · 3 games (+1 void, not counted: 904 CANCELLED) · MARKET-ONLY ("), nba
    assert "export._MARKET_ONLY_REASON" in nba
    assert tcm.line_of(out, "NHL").startswith("NHL · 0 games (+1 void, not counted: 501 POSTPONED)")
    paper_lines = [x for x in out if x.startswith("NBA SLATE · PAPER · ")]
    assert [x.split(" · ")[2].split()[0] for x in paper_lines] == ["901", "903", "902"], paper_lines
    assert any(x.startswith("NBA SLATE · PAPER, never a call") and "3 games" in x for x in out), out


# ---- the docs name what was built ---------------------------------------------------------------------------------------

def test_the_docs_name_the_command_the_chain_and_the_basis():
    doc = (ROOT / "docs" / "CLI.md").read_text()
    assert "| `sync-kalshi-nba` |" in doc and "**NBA daily (host `sp-nba-daily`" in doc
    assert "paper.COVERAGE_COUNTS_POSTPONED" in doc and "| `python3 scripts/nba_certification_receipt.py` |" in doc
