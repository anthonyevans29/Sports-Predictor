"""ARCHITECT 2026-10-05: "MLB 00:00Z rollover rows graded unpriced twice this weekend (PHI@ATL, ATL@LAD) —
the provider never posts pre-pitch ... Ruling: yes — when no book session exists pre-pitch and a two-sided
Kalshi capture does, grade against the Kalshi mid, labelled reference=kalshi_only."
Synthetic rows / throwaway DB only."""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, OddsSnapshot, Sport, Team
from src.walters.close import BINARY, THREE_WAY, close_from_kalshi, grading_close, grading_close_block, priced

KO = datetime(2091, 10, 4, 0, 5)


def k(sel, bid, ask, at, source="kalshi"):
    return NS(source=source, selection=sel, yes_bid=bid, yes_ask=ask, captured_at=at, market="1X2", devig_prob=0.5)


def test_mid_of_the_last_two_sided_pre_pitch_home_quote():
    snaps = [k("HOME", 0.40, 0.44, KO - timedelta(hours=3)),
             k("HOME", 0.45, 0.47, KO - timedelta(hours=1)),        # the last two-sided pre-pitch quote
             k("HOME", None, 0.48, KO - timedelta(minutes=20)),     # one-sided: never a mid
             k("HOME", 0.80, 0.82, KO + timedelta(minutes=30)),     # in-play: never the close
             k("AWAY", 0.50, 0.56, KO - timedelta(minutes=10))]     # the HOME contract carries the price
    cl = close_from_kalshi(snaps, KO, BINARY)
    assert cl["reference"] == "kalshi_only" and cl["source"] == "kalshi_only"
    assert cl["fair"]["HOME"] == pytest.approx(0.46) and cl["fair"]["AWAY"] == pytest.approx(0.54)
    assert cl["kalshi"]["spread_c"] == 2.0 and cl["best"] == {} and cl["books"] == 0
    assert cl["captured_at"] == KO - timedelta(hours=1)


def test_no_two_sided_quote_or_three_way_board_is_no_close():
    assert close_from_kalshi([k("HOME", None, 0.5, KO - timedelta(hours=1))], KO, BINARY) is None
    assert close_from_kalshi([k("HOME", 0.4, 0.5, KO - timedelta(hours=1))], KO, THREE_WAY) is None
    assert close_from_kalshi([k("HOME", 0.4, 0.5, KO - timedelta(hours=1), source="book")], KO, BINARY) is None


def _mlb(s, tag):
    c = s.query(Competition).filter_by(code="MLB").one_or_none()
    if c is None:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        s.add(c)
        s.flush()
    h, a = Team(sport=Sport.MLB, name=f"KO {tag} H"), Team(sport=Sport.MLB, name=f"KO {tag} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.MLB, competition_id=c.id, season="2091", utc_date=KO, status=MatchStatus.FINISHED,
              home_team_id=h.id, away_team_id=a.id, home_score=3, away_score=2)
    s.add(m)
    s.flush()
    return m


def _kalshi_rows(s, m):
    s.add(OddsSnapshot(match_id=m.id, market="1X2", selection="HOME", devig_prob=0.46, n_books=1,
                       captured_at=KO - timedelta(hours=1), source="kalshi", yes_bid=0.45, yes_ask=0.47))
    s.add(OddsSnapshot(match_id=m.id, market="1X2", selection="AWAY", devig_prob=0.54, n_books=1,
                       captured_at=KO - timedelta(hours=1), source="kalshi", yes_bid=0.52, yes_ask=0.55))


def test_grading_close_falls_to_kalshi_only_when_no_book_session_exists():
    init_db()
    with session_scope() as s:
        m = _mlb(s, "a")
        _kalshi_rows(s, m)
        s.flush()
        cl = grading_close(s, m)
        blk = grading_close_block(s, m)
    assert priced(cl) and cl["reference"] == "kalshi_only" and cl["fair"]["HOME"] == pytest.approx(0.46)
    assert blk["close_reference"] == "kalshi_only" and blk["close_fair"] == {"HOME": 0.46, "AWAY": 0.54}
    assert blk["close_kalshi"]["mid"] == pytest.approx(0.46) and "kalshi_only" in blk["close_source"]


def test_a_book_session_that_exists_but_cannot_price_stays_unpriced():
    """The ruling covers ABSENT books only: an incomplete pre-pitch book session is not replaced."""
    init_db()
    with session_scope() as s:
        m = _mlb(s, "b")
        _kalshi_rows(s, m)
        s.add(Odds(match_id=m.id, bookmaker="bk", market="1X2", selection="HOME", price_decimal=1.9,
                   captured_at=KO - timedelta(hours=2)))                        # one-sided book session
        s.flush()
        cl = grading_close(s, m)
    assert not priced(cl) and cl["missing"] == {"bk": ["AWAY"]}


def test_books_win_over_kalshi_and_say_so():
    init_db()
    with session_scope() as s:
        m = _mlb(s, "c")
        _kalshi_rows(s, m)
        s.add(OddsSnapshot(match_id=m.id, market="1X2", selection="HOME", devig_prob=0.6, n_books=4,
                           captured_at=KO - timedelta(hours=2), source="api_baseball"))
        s.add(OddsSnapshot(match_id=m.id, market="1X2", selection="AWAY", devig_prob=0.4, n_books=4,
                           captured_at=KO - timedelta(hours=2), source="api_baseball"))
        s.flush()
        cl = grading_close(s, m)
        blk = grading_close_block(s, m)
    assert cl["reference"] == "books" and cl["fair"]["HOME"] == pytest.approx(0.6)
    assert blk["close_reference"] == "books" and "close_kalshi" not in blk
