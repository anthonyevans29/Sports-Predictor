"""NCAA MEN'S BASKETBALL'S MARKET-ONLY WIRING, the Kalshi and host half (ARCHITECT 2026-11-12, addendum 352 items 2-4;
addendum 353 item 2; lane basketball-market-only, #839; 261 item 1(c)).

The series "NCAAMB": "KXNCAAMBGAME" READ from Kalshi's own listing by the operator (2026-11-12T15:36Z) and its fee M
(1.0, 1.0) RULED on that read (353 item 2); the shared matcher, ambiguity refused by its sentinel; `sync-kalshi-ncaamb`;
the capture tier; the chain ncaamb-daily and its timer, shipped on T11's TIMERS_BY_BLOCK, not enabled.

353 item 2's three sample markets are the receipt the Kalshi-side names and stamps come from: "San Jose St." and
"Alabama St." (KXNCAAMBGAME-26NOV15ALSTSJSU, occurrence 2026-11-16T05:00:00Z), "UTSA" (KXNCAAMBGAME-26NOV15TXSTUTSA,
occurrence 2026-11-16T04:00:00Z). "Texas St." (TXST's leg) is NOT on the receipt: it is written on the pattern of the
two "St." forms that are. The STORED team names (API-Sports' NCAA spellings) are SYNTHETIC, on no receipt yet: the
first load's console is where they are read. The throwaway DBs only (tests/conftest.py's); no network."""
from __future__ import annotations

import re
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

Z = datetime.fromisoformat                                         # naive UTC
_IDS: dict[str, int] = {}


def _team(name):
    return NS(id=_IDS.setdefault(name, len(_IDS) + 1), name=name)


def game(gid, away, home, kick, status="scheduled"):
    h, a = _team(home), _team(away)
    return NS(id=gid, utc_date=kick, home_team=h, away_team=a, home_team_id=h.id, away_team_id=a.id, status=status)


def event(stamp, legs, occurrence=None, series="KXNCAAMBGAME", bid="0.40", ask="0.42"):
    """One Kalshi event shaped as 353's sample: a market per (ticker suffix, yes_sub_title), each "<Team> wins"."""
    e = f"{series}-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "occurrence_datetime": occurrence, "yes_bid_dollars": bid, "yes_ask_dollars": ask} for sfx, name in legs]


NOW = Z("2026-11-15T15:00")
OCC_SJSU = "2026-11-16T05:00:00Z"                                  # 353 item 2: 00:00 ET on 11-16, a day off the ticker
OCC_UTSA = "2026-11-16T04:00:00Z"                                  # 353 item 2: 23:00 ET on 11-15, the ticker's own date
SJSU = [("SJSU", "San Jose St."), ("ALST", "Alabama St.")]


def run(markets, games, now=NOW, hours=48):
    return km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(hours=hours))


def placed(res):
    return {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()}


# ---- the series and its fee M (353 item 2) ---------------------------------------------------------------------------

def test_the_series_is_the_one_read_and_its_fee_m_is_the_ruled_one():
    """353 item 2: "KALSHI_SERIES_BY_COMPETITION["NCAAMB"] = "KXNCAAMBGAME"" and its fee M (1.0, 1.0), "the comment in
    venue.py quotes THIS console's line and date". KXNCAABGAME (dormant), KXNCAABBGAME (college baseball, whose prefix
    collides) and the women's and Division III series are not mapped."""
    from src.ingestion.kalshi_replay import shared_series
    from src.ingestion.kalshi_sync import series_competition
    assert venue.KALSHI_SERIES_BY_COMPETITION["NCAAMB"] == "KXNCAAMBGAME"
    assert series_competition("KXNCAAMBGAME") == "NCAAMB" and shared_series()["KXNCAAMBGAME"] == "NCAAMB"
    assert venue.KALSHI_FEE_M["KXNCAAMBGAME"] == (1.0, 1.0)
    for other in ("KXNCAABGAME", "KXNCAABBGAME", "KXNCAAWBGAME", "KXNCAAMBD3GAME"):
        assert other not in venue.KALSHI_SERIES_BY_COMPETITION.values() and other not in venue.KALSHI_FEE_M
    assert "NCAA" not in venue.KALSHI_SERIES_BY_COMPETITION or venue.KALSHI_SERIES_BY_COMPETITION["NCAA"] != "KXNCAAMBGAME"
    src = (ROOT / "src" / "walters" / "venue.py").read_text()
    assert ("KXNCAAMBGAME · Men's College Basketball Game · category\n    # Sports · tags ['Basketball'] · fee_type "
            "quadratic_with_maker_fees · fee_multiplier 1 · frequency custom") in src
    assert "2026-11-12T15:36Z" in src and "addendum 353 item 2" in src
    e = venue.kalshi_exec(0.53, 0.55, "NCAAMB", two_way=True)
    n = venue.kalshi_exec(0.53, 0.55, "NBA", two_way=True)
    assert (e["fee_series"], e["fee_m_taker"], e["fee_m_maker"]) == ("KXNCAAMBGAME", 1.0, 1.0)
    costs = ("exec_cost_taker", "exec_cost_maker", "exec_cost_taker_away", "exec_cost_maker_away")
    assert all(e[k] is not None for k in costs) and [e[k] for k in costs] == [n[k] for k in costs]


# ---- the matcher on 353's real spellings -----------------------------------------------------------------------------

def test_353s_sample_places_on_its_own_game_and_not_on_another_alabama():
    """353 item 2(b): "Alabama St." must not match Alabama or Alabama A&M. On the event's day all three Alabamas play
    (each against its own opponent): the event's two names fit one game one each, Alabama State's at San Jose State,
    both sides, nothing refused."""
    games = [game(9801, "Alabama State", "San Jose State", Z("2026-11-16T05:00")),
             game(9802, "Alabama", "Kentucky", Z("2026-11-16T00:00")),
             game(9803, "Alabama A&M", "Tennessee", Z("2026-11-16T01:00"))]
    res = run(event("26NOV15ALSTSJSU", SJSU, OCC_SJSU), games)
    assert placed(res) == {(9801, "HOME"): "SJSU", (9801, "AWAY"): "ALST"} and not res.refused, (res.refused, res.why)


def test_alabama_st_is_never_guessed_between_alabama_and_alabama_am():
    """The same two names against two stored games that each half-fit ("Alabama" v San Jose State, "Alabama A&M" v
    San Jose State, neither Alabama State's): the best fit is shared by two pairs -> PAIR_TIE, both markets refused and
    counted; with Alabama State's own game stored beside them, the whole-name fit takes the market."""
    wrong = [game(9811, "Alabama", "San Jose State", Z("2026-11-16T05:00")),
             game(9812, "Alabama A&M", "San Jose State", Z("2026-11-16T03:00"))]
    tie = run(event("26NOV15ALSTSJSU", SJSU, OCC_SJSU), wrong)
    assert not tie.placed and tie.refused == {km.PAIR_TIE: 2}
    right = game(9813, "Alabama State", "San Jose State", Z("2026-11-16T05:00"))
    best = run(event("26NOV15ALSTSJSU", SJSU, OCC_SJSU), [*wrong, right])
    assert placed(best) == {(9813, "HOME"): "SJSU", (9813, "AWAY"): "ALST"} and not best.refused
    # "St." reads as State (norm_tokens), so the stored "Alabama State" scores both words and plain "Alabama" one
    assert km.side_score("Alabama St.", "Alabama State") == 2 and km.side_score("Alabama St.", "Alabama") == 1
    assert km.side_score("Alabama St.", "Alabama A&M") == 1


# ---- the day rule on 353's stamps (addendum 44 item 1; addendum 52 item 4) -------------------------------------------

def test_the_ticker_date_is_the_events_day_and_the_occurrence_places_nothing():
    """26NOV15 is the ticker's date, read as a US Eastern day; the stored kickoff 2026-11-16T05:00Z reads 00:00 ET on
    11-16, a day either side, so it places (the module's rule, addendum 44 item 1). occurrence_datetime places nothing
    and refuses nothing (addendum 52 item 4): the same event with no occurrence, or one days away, places the same; a
    stored kickoff two US Eastern days off the ticker's date is NO_FIT whatever the occurrence says."""
    g = game(9821, "Alabama State", "San Jose State", Z("2026-11-16T05:00"))
    assert km.et_day(g.utc_date).isoformat() == "2026-11-16"
    want = {(9821, "HOME"): "SJSU", (9821, "AWAY"): "ALST"}
    for occ in (OCC_SJSU, None, "2026-11-20T05:00:00Z"):
        assert placed(run(event("26NOV15ALSTSJSU", SJSU, occ), [g])) == want, occ
    far = game(9822, "Alabama State", "San Jose State", Z("2026-11-17T05:00"))       # 11-17 ET: two days off
    res = run(event("26NOV15ALSTSJSU", SJSU, "2026-11-17T05:00:00Z"), [far])
    assert not res.placed and res.refused == {km.NO_FIT: 2}


def test_the_utsa_sample_is_on_the_tickers_own_date():
    """353's second event: occurrence 2026-11-16T04:00Z is 23:00 ET on 11-15, the ticker's own date; the stored kickoff
    at that instant places both sides. "Texas St." is written on the pattern of the receipt's "St." forms."""
    g = game(9831, "Texas State", "UTSA", Z("2026-11-16T04:00"))
    assert km.et_day(g.utc_date).isoformat() == "2026-11-15"
    res = run(event("26NOV15TXSTUTSA", [("UTSA", "UTSA"), ("TXST", "Texas St.")], OCC_UTSA), [g])
    assert placed(res) == {(9831, "HOME"): "UTSA", (9831, "AWAY"): "TXST"} and not res.refused


def test_a_game_with_a_non_division_i_side_is_stored_and_never_paired():
    """272 item 2: "A game with a non-D-I side has no Kalshi market and is a correct refusal; the sync still stores
    every served game." The non-D-I game (a synthetic name) takes no market; an event naming a team no stored game
    of the day holds is NO_FIT, counted, never placed on a half-fit."""
    nond1 = game(9841, "Synthland College", "Alabama State", Z("2026-11-15T23:00"))
    real = game(9842, "Alabama State", "San Jose State", Z("2026-11-16T05:00"))
    res = run(event("26NOV15ALSTSJSU", SJSU, OCC_SJSU), [nond1, real])
    assert set(placed(res)) == {(9842, "HOME"), (9842, "AWAY")} and not res.refused
    alone = run(event("26NOV15ZZZSJSU", [("SJSU", "San Jose St."), ("ZZZ", "Nowhere St.")], OCC_SJSU), [nond1])
    assert not alone.placed and alone.refused == {km.NO_FIT: 2}


# ---- sync-kalshi-ncaamb ----------------------------------------------------------------------------------------------

@pytest.fixture
def kalshi_fake(monkeypatch):
    from src.adapters.kalshi import KalshiAdapter
    box = {"markets": [], "asked": []}
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series",
                        lambda self, s: box["asked"].append(s) or box["markets"])
    return box


def _clear():
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, OddsSnapshot, Sport, Team
    with session_scope() as s:
        comp_ids = [c.id for c in s.query(Competition).filter(Competition.code == "NCAAMB")]
        ids = [m.id for m in s.query(Match).filter(Match.competition_id.in_(comp_ids))]
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.sport == Sport.BASKETBALL).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.code == "NCAAMB").delete(synchronize_session=False)


@pytest.fixture
def ncaamb_db():
    """conftest's throwaway DB, every NCAAMB row (and every basketball team) removed before and after."""
    from src.db.database import init_db
    init_db()
    _clear()
    yield
    _clear()


def _ncaamb(s, games):
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    comp = Competition(sport=Sport.BASKETBALL, code="NCAAMB", name="NCAA Men's Basketball (Division I)", area="USA",
                       type="LEAGUE")
    s.add(comp)
    s.flush()
    teams = {}
    for away, home, ko in games:
        for nm in (away, home):
            if nm not in teams:
                teams[nm] = Team(sport=Sport.BASKETBALL, name=nm)
                s.add(teams[nm])
        s.flush()
        s.add(Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026", utc_date=ko,
                    status=MatchStatus.SCHEDULED, home_team_id=teams[home].id, away_team_id=teams[away].id,
                    status_raw="NS"))
    s.flush()
    return comp


def test_sync_kalshi_ncaamb_refuses_without_the_competition(ncaamb_db, kalshi_fake):
    import cli
    kalshi_fake["markets"] = event("26NOV15ALSTSJSU", SJSU, OCC_SJSU)
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-ncaamb"])
    assert out.exit_code == 0 and "✗ Kalshi NCAAMB: competition NCAAMB not in DB" in out.output, out.output
    assert kalshi_fake["asked"] == ["KXNCAAMBGAME"]                   # one exact series, never a prefix


def test_sync_kalshi_ncaamb_stores_both_sides_and_counts_its_refusals(ncaamb_db, kalshi_fake, monkeypatch):
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(kalshi_sync, "utc_now_naive", lambda: NOW)
    with session_scope() as s:
        comp = _ncaamb(s, [("Alabama State", "San Jose State", Z("2026-11-16T05:00"))])
        mid = s.query(Match).filter(Match.competition_id == comp.id).one().id
    kalshi_fake["markets"] = (event("26NOV15ALSTSJSU", SJSU, OCC_SJSU, bid="0.30", ask="0.32")
                              + event("26NOV15TXSTUTSA", [("UTSA", "UTSA"), ("TXST", "Texas St.")], OCC_UTSA))
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-ncaamb"])
    assert out.exit_code == 0, out.output
    assert "✓ Kalshi NCAAMB: 2 prices stored" in out.output and "series KXNCAAMBGAME · 4 markets" in out.output, out.output
    assert km.NO_FIT in out.output                                    # UTSA's game is not stored: counted, printed
    with session_scope() as s:
        snaps = {x.selection: (x.market, x.source, x.yes_bid, x.yes_ask)
                 for x in s.query(OddsSnapshot).filter(OddsSnapshot.match_id == mid)}
    assert snaps == {"AWAY": ("ML", "kalshi", 0.30, 0.32), "HOME": ("ML", "kalshi", 0.30, 0.32)}


# ---- the chain, the capture tier, the timer (352 item 3(iii)) ---------------------------------------------------------

def test_ncaamb_daily_is_nba_dailys_three_single_day_shape_then_its_kalshi_sync():
    """352 item 3(iii): "A NEW CHAIN, `ncaamb-daily`, [...] on nba-daily's three single-day shape"; 3(iv): the 2026-27
    season only."""
    ch = chains.CHAINS["ncaamb-daily"]
    nba = chains.CHAINS["nba-daily"]
    assert [[("NCAAMB" if x == "NBA" else x) for x in st] for st in nba["steps"][:3]] == ch["steps"][:3]
    assert ch["steps"][3:] == [["sync-kalshi-ncaamb"]] and len(ch["steps"]) == 4
    assert all(st[st.index("--season") + 1] == "2026" for st in ch["steps"][:3])
    assert ch["backup"] == "daily" and chains.COVERAGE_STEP not in ch["steps"]
    assert "sync-kalshi-ncaamb" in chains.UNMETERED
    assert chains.WINDOW_KALSHI["NCAAMB"] == [["sync-kalshi-ncaamb"]]
    assert "NCAAMB" not in chains.WINDOW_KALSHI_CAPTURE_ONLY


def _calendars():
    return {p.stem: re.findall(r"^OnCalendar=(.+)$", p.read_text(), re.M)
            for p in sorted((HOSTING / "systemd").glob("*.timer"))}


def test_the_timer_minute_is_off_every_existing_timer_and_before_the_coverage_write():
    """352 item 3(iii): "its own timer at a UTC minute off every existing one (you list and pick)". 07:07 UTC: no
    other timer fires at :07, it is no five-minute mark (sp-window, sp-cup-observe, sp-availability-observe), and it is
    before intl-daily's 07:20 coverage write. sp-closing-watch ticks every minute (its exemption by name)."""
    cal = _calendars()
    assert cal["sp-ncaamb-daily"] == ["*-*-* 07:07:00 UTC"]
    assert "Unit=sp-chain@ncaamb-daily.service" in (HOSTING / "systemd" / "sp-ncaamb-daily.timer").read_text()
    minutes = set()
    for name, lines in cal.items():
        if name in ("sp-ncaamb-daily", "sp-closing-watch"):
            continue
        for ln in lines:
            for m in re.finditer(r"(\d{2}|\*):(\d{2})(?::\d{2})?", ln):
                minutes.add(int(m.group(2)))
    assert 7 not in minutes and 7 % 5 != 0, sorted(minutes)
    assert cal["sp-intl-daily"] == ["*-*-* 07:20:00 UTC"]


def test_the_timer_ships_on_timers_by_block_never_enabled_by_t11():
    """352 item 3(iii): "its timer goes on T11's TIMERS_BY_BLOCK (351 item 2)"; 352 item 4: "THE LOAD AND THE
    ENABLEMENT are mine". One Schedule row; the recipe ends with the timers.enabled line (addendum 168 item 2)."""
    import sp_common as c
    lists = c.t11_lists()
    assert "sp-ncaamb-daily.timer" in lists["TIMERS_BY_BLOCK"]
    assert "sp-ncaamb-daily.timer" not in lists["TIMERS"] and "sp-ncaamb-daily.timer" not in lists["MLB_LAPTOP_ONLY"]
    h1 = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    assert len(re.findall(r"^\| sp-ncaamb-daily \|", h1, re.M)) == 1
    assert "echo sp-ncaamb-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled" in h1
    assert "systemctl enable" not in (HOSTING / "install.sh").read_text()


def test_the_export_says_ncaamb_is_market_only():
    from src.walters import export
    why = export._MARKET_ONLY_REASON["NCAAMB"]
    assert "market-only" in why and "no call" in why
