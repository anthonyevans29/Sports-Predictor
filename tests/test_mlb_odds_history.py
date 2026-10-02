"""MLB ODDS HISTORY (ARCHITECT 2026-10-02, priority). PHI@ATL game 3: 8
books captured at 22:55Z, 65 min before first pitch; graded unpriceable
because the morning sync REPLACED the odds rows with a post-game capture.
Now: a post-first-pitch capture never touches a game's odds; every pre-game
sync APPENDS one book-consensus OddsSnapshot (the #207 contract); the
grading close falls back to the last complete pre-first-pitch snapshot
session when the odds table cannot price."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction,
                           PredictionOutcome, Sport, Team)
from src.ingestion.service import _mlb_store_odds
from src.timeutil import utc_now_naive
from src.walters.close import BINARY, close_from_snapshots, grading_close, priced


def ow(book, sel, px):
    return NS(market="1X2", selection=sel, bookmaker=book, price_decimal=px, line=None)


EIGHT = [ow(f"bk{i}", sel, px) for i in range(8) for sel, px in (("HOME", 1.80 + i / 100), ("AWAY", 2.05))]


def _game(tag, ko):
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLBOH")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLBOH", name="MLBOH", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h = Team(sport=Sport.MLB, name=f"OH {tag} Braves", external_ids={"oh": f"{tag}h"})
        a = Team(sport=Sport.MLB, name=f"OH {tag} Phillies", external_ids={"oh": f"{tag}a"})
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=ko,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        return m.id


def test_pre_game_sync_replaces_odds_and_appends_a_contract_snapshot():
    mid = _game("pre", utc_now_naive() + timedelta(minutes=65))
    with session_scope() as s:
        m = s.get(Match, mid)
        assert _mlb_store_odds(s, m, EIGHT) == (16, True)
        assert _mlb_store_odds(s, m, EIGHT[:4]) == (4, True)                # a second sync: history grows
    with session_scope() as s:
        assert len(list(s.execute(select(Odds).where(Odds.match_id == mid)).scalars())) == 4   # current board
        snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == mid)).scalars())
        assert len(snaps) == 4 and {x.source for x in snaps} == {"api_baseball"}
        assert sorted(x.n_books for x in snaps) == [2, 2, 8, 8]
        by_t: dict = {}
        for x in snaps:
            by_t.setdefault(x.captured_at, {})[x.selection] = x.devig_prob
        assert all(sum(v.values()) == pytest.approx(1.0) for v in by_t.values())


def test_post_first_pitch_sync_never_touches_the_game():
    mid = _game("post", utc_now_naive() - timedelta(hours=10))
    with session_scope() as s:
        s.add(Odds(match_id=mid, bookmaker="bk", market="1X2", selection="HOME", price_decimal=1.9,
                   source="api_baseball", captured_at=utc_now_naive() - timedelta(hours=11)))
    with session_scope() as s:
        assert _mlb_store_odds(s, s.get(Match, mid), EIGHT) is None
    with session_scope() as s:
        rows = list(s.execute(select(Odds).where(Odds.match_id == mid)).scalars())
        assert [r.price_decimal for r in rows] == [1.9]                    # the pre-game row survives
        assert not list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == mid)).scalars())


def test_close_from_snapshots_rules():
    ko = utc_now_naive()
    t1, t2, live = ko - timedelta(hours=3), ko - timedelta(minutes=65), ko + timedelta(minutes=5)
    sn = lambda sel, p, t, src="api_baseball", n=8: NS(market="1X2", selection=sel, devig_prob=p,
                                                       captured_at=t, source=src, n_books=n)
    snaps = [sn("HOME", 0.55, t1), sn("AWAY", 0.45, t1),
             sn("HOME", 0.58, t2),                                          # t2 incomplete: never a price
             sn("HOME", 0.30, live), sn("AWAY", 0.70, live),                # in-game: never the close
             sn("HOME", 0.90, t2, src="kalshi"), sn("AWAY", 0.10, t2, src="kalshi")]   # Kalshi: never
    cl = close_from_snapshots(snaps, ko, BINARY)
    assert cl["captured_at"] == t1 and cl["fair"]["HOME"] == pytest.approx(0.55) and cl["source"] == "snapshot"
    assert close_from_snapshots(snaps[2:], ko, BINARY) is None


def test_phi_atl_shape_regrades_with_a_priced_close():
    """The live shape: 8 books at T-65 (sync appends the snapshot), then the
    OLD morning behaviour replaced the odds rows with a post-game capture and
    the game was graded with clv NULL. evaluate's backfill re-grades it from
    the snapshot session."""
    from src.walters.training import evaluate_finished
    ko = utc_now_naive() - timedelta(hours=14)
    mid = _game("phiatl", ko)
    t = ko - timedelta(minutes=65)
    with session_scope() as s:
        m = s.get(Match, mid)
        for sel, p in (("HOME", 0.5333), ("AWAY", 0.4667)):
            s.add(OddsSnapshot(match_id=mid, market="1X2", selection=sel, devig_prob=p, n_books=8,
                               captured_at=t, source="api_baseball"))
        for sel, px in (("HOME", 1.2), ("AWAY", 4.5)):                     # the post-game replacement
            s.add(Odds(match_id=mid, bookmaker="bk", market="1X2", selection=sel, price_decimal=px,
                       source="api_baseball", captured_at=ko + timedelta(hours=12)))
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 5, 3
        p = Prediction(match_id=mid, model_version="t", home_win_prob=0.56, draw_prob=None, away_win_prob=0.44)
        s.add(p)
        s.flush()
        s.add(PredictionOutcome(prediction_id=p.id, clv=None, top_pick_hit=True))
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
        assert priced(cl) and cl["source"] == "snapshot" and cl["captured_at"] == t and cl["books"] == 8
    evaluate_finished(sport=Sport.MLB)
    with session_scope() as s:
        clv = s.execute(select(PredictionOutcome.clv).join(Prediction).where(
            Prediction.match_id == mid)).scalar_one()
    assert clv == pytest.approx(0.56 - 0.5333)


def test_capture_odds_is_bounded_to_pre_first_pitch_and_writes_no_1x2(monkeypatch):
    """#174: a past game stuck in SCHEDULED is never captured; 1X2 snapshots
    come from the sync (contract) only — capture-odds keeps TOTALS."""
    from click.testing import CliRunner
    import cli
    from src.ingestion import service as svc
    monkeypatch.setattr(svc.IngestionService, "sync_odds_mlb", lambda self, season: "stubbed")
    stale = _game("stale", utc_now_naive() - timedelta(days=3))
    live = _game("cap", utc_now_naive() + timedelta(hours=3))
    with session_scope() as s:
        for mid in (stale, live):
            for sel, px, ln in (("HOME", 1.9, None), ("AWAY", 1.95, None), ("OVER", 1.9, 8.5), ("UNDER", 1.9, 8.5)):
                s.add(Odds(match_id=mid, bookmaker="bk", market="1X2" if ln is None else "TOTALS",
                           selection=sel, price_decimal=px, line=ln, source="api_baseball",
                           captured_at=utc_now_naive() - timedelta(minutes=5)))
    r = CliRunner().invoke(cli.cli, ["capture-odds"])
    assert r.exit_code == 0, r.output
    with session_scope() as s:
        snap = lambda mid: {(x.market, x.selection) for x in s.execute(
            select(OddsSnapshot).where(OddsSnapshot.match_id == mid)).scalars()}
        assert snap(stale) == set()
        assert snap(live) == {("TOTALS", "OVER"), ("TOTALS", "UNDER")}
