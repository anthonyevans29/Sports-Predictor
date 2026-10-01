"""MLB odds timing receipt (postseason night-game odds finding, 2026-09-30):
read-only, from our own append-only odds_snapshots. Throwaway DB, private
dates (2035) so nothing collides with other tests."""
from datetime import date, datetime

from click.testing import CliRunner

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, OddsSnapshot, Sport, Team
from src.walters import mlb_odds_timing as mt


def test_classify_rollover_night_and_verdicts():
    start = datetime(2035, 10, 3, 0, 8)              # 20:08 ET on 10-02: a UTC-rollover night game
    r = mt.classify(start, [(datetime(2035, 10, 2, 12, 0), 12), (datetime(2035, 10, 3, 0, 0), 12)])
    assert r["rollover"] and r["night"] and r["start_et"] == datetime(2035, 10, 2, 20, 8)
    assert r["verdict"] == "PRICED_PRE_START" and r["first_pre_start_after_utc_midnight"] is False
    assert r["lead_hours"] == 12.1 and r["captures_pre_start"] == 2 and r["max_books"] == 12
    r = mt.classify(start, [(datetime(2035, 10, 3, 0, 0), 9)])          # only the 20:00 ET capture
    assert r["first_pre_start_after_utc_midnight"] is True
    assert mt.classify(start, [(datetime(2035, 10, 3, 4, 0), 12)])["verdict"] == "PRICED_ONLY_AFTER_START"
    r = mt.classify(start, [])
    assert r["verdict"] == "NO_BOOKS_CAPTURED" and r["first_capture"] is None
    day = mt.classify(datetime(2035, 10, 2, 17, 8), [])                 # 13:08 ET
    assert not day["rollover"] and not day["night"]


def test_et_day_bounds_cross_dst():
    assert mt.et_day_bounds_utc(date(2035, 10, 2)) == (datetime(2035, 10, 2, 4), datetime(2035, 10, 3, 4))
    assert mt.et_day_bounds_utc(date(2035, 12, 2)) == (datetime(2035, 12, 2, 5), datetime(2035, 12, 3, 5))


def _team(s, name):
    t = Team(sport=Sport.MLB, name=name)
    s.add(t)
    s.flush()
    return t


def test_timing_end_to_end_and_cli():
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.MLB, code="MLBT35", name="timing test", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        a, b, c, d = (_team(s, f"Timing {x} 2035") for x in "ABCD")
        day = Match(sport=Sport.MLB, competition_id=comp.id, season="2035", utc_date=datetime(2035, 10, 2, 17, 8), stage="Postseason",
                    status=MatchStatus.FINISHED, home_team_id=a.id, away_team_id=b.id)
        night = Match(sport=Sport.MLB, competition_id=comp.id, season="2035", utc_date=datetime(2035, 10, 3, 0, 8), stage="Postseason",
                      status=MatchStatus.FINISHED, home_team_id=c.id, away_team_id=d.id)
        s.add_all([day, night])
        s.flush()
        for at in (datetime(2035, 10, 2, 12), datetime(2035, 10, 2, 16)):       # 08:00 and 12:00 ET captures
            for sel, p in (("HOME", 0.55), ("AWAY", 0.45)):
                s.add(OddsSnapshot(match_id=day.id, market="1X2", selection=sel, devig_prob=p, n_books=12,
                                   captured_at=at, source="api_baseball"))
        s.add(OddsSnapshot(match_id=night.id, market="ML", selection="HOME", devig_prob=0.5, n_books=0,
                           captured_at=datetime(2035, 10, 2, 16), source="kalshi"))
        s.add(Odds(match_id=day.id, market="1X2", selection="HOME", bookmaker="bk", price_decimal=1.8,
                   source="api_baseball", captured_at=datetime(2035, 10, 2, 16)))
    r = mt.timing(date(2035, 10, 2), date(2035, 10, 2))
    by = {g["game"]: g for g in r["games"]}
    assert by["Timing B 2035 @ Timing A 2035"]["verdict"] == "PRICED_PRE_START"
    assert by["Timing B 2035 @ Timing A 2035"]["captures"] == 2 and by["Timing B 2035 @ Timing A 2035"]["odds_table_books"] == 1
    n = by["Timing D 2035 @ Timing C 2035"]
    assert n["verdict"] == "NO_BOOKS_CAPTURED" and n["rollover"] and n["kalshi_pre_start"]
    assert r["summary"] == {"day PRICED_PRE_START": 1, "night/rollover NO_BOOKS_CAPTURED": 1}

    from cli import cli
    out = CliRunner().invoke(cli, ["mlb-odds-timing", "--start", "2035-10-02", "--only-missing"]).output
    flat = " ".join(out.split())
    assert "NO_BOOKS_CAPTURED" in flat and "NIGHT ROLLOVER" in flat and "Timing A 2035" not in flat
    assert "night/rollover NO_BOOKS_CAPTURED 1" in flat
