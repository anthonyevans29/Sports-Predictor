"""#615 (ARCHITECT 2026-10-19, addendum 137 item 4), on an isolated throwaway DB, verbatim: "MLB's and PL's odds syncs
never store the provider's update time (`_mlb_store_odds`, `sync_odds`), so their stamp age cannot be measured. Issue
+ a small data PR: both syncs write `source_updated_at` from the provider's own update field, as `sync-odds-football`
does, no backfill; the 24-hour rule then applies to them forward."

The writers store whatever source time the adapter's row carries (None = unknown, never our clock): each odds row its
own, each appended snapshot the oldest over the rows the close priced (close.priced_rows, the set book_stamp reads).
Addendum 140 item 3 reading (4), pre-committed before a PL stamp is stored: "a three-way board: the book close stays,
`close_stale_unswitched` saying why". And results-tally reads Kalshi's two-way rows (comment 6270315541), so a close
priced from a Kalshi mid reproduces its stored value and is VERIFIED, not retained-legacy.

The stamp columns are unmapped (addendum 35 item 2): the fixture adds them to the isolated DB and points the column
check (database._engine) at it, as migrate_odds_source_updated_at.py would; `absent` leaves them out."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.adapters.normalized import NormalizedOdds
from src.db.schema import Sport


@pytest.fixture
def iso(tmp_path, monkeypatch, request):
    from src.db import database
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    Base.metadata.create_all(eng)
    if getattr(request, "param", "present") == "present":
        with eng.begin() as c:
            for t in ("odds", "odds_snapshots"):
                c.execute(text(f"ALTER TABLE {t} ADD COLUMN source_updated_at DATETIME"))
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True, expire_on_commit=False))
    monkeypatch.setattr(database, "_engine", eng)           # has_source_time reads the column from this engine
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    eng.dispose()


def _now():
    from src.timeutil import utc_now_naive
    return utc_now_naive().replace(microsecond=0)


def _match(s, key, ko, *, sport=Sport.MLB, code="MLB", status="SCHEDULED", ext=None):
    from src.db.schema import Competition, Match, MatchStatus, Team
    c = s.query(Competition).filter_by(code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
    h, a = Team(sport=sport, name=f"ST {key} H"), Team(sport=sport, name=f"ST {key} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=c.id, season="2026", utc_date=ko, status=getattr(MatchStatus, status),
              home_team_id=h.id, away_team_id=a.id, external_ids=ext or {})
    if status == "FINISHED":
        m.home_score, m.away_score = 5, 2
    s.add(m)
    s.flush()
    return m


def _stamps(s, rows):
    from src.db.database import attach_source_times
    return [r.source_updated_at for r in attach_source_times(s, rows)]


def _stored(match_id):
    from src.db.database import session_scope
    from src.db.schema import Odds, OddsSnapshot
    with session_scope() as s:
        odds = sorted(s.query(Odds).filter(Odds.match_id == match_id), key=lambda o: (o.bookmaker, o.selection))
        snaps = sorted(s.query(OddsSnapshot).filter(OddsSnapshot.match_id == match_id), key=lambda x: x.selection)
        return ([(o.bookmaker, o.selection, t) for o, t in zip(odds, _stamps(s, odds))],
                [(x.selection, t) for x, t in zip(snaps, _stamps(s, snaps))])


def _mlb_rows(ko, *, b2_away=40):
    """Two complete books (stamped 30 h and 40 h before kickoff) and a one-sided third book stamped older still:
    the third quoted HOME only, so the close never priced it and its stamp is not the snapshot's."""
    def ow(bk, sel, px, h):
        return NS(market="1X2", selection=sel, bookmaker=bk, price_decimal=px, line=None,
                  source_updated_at=None if h is None else ko - timedelta(hours=h))
    return [ow("bk1", "HOME", 1.8, 30), ow("bk1", "AWAY", 2.1, 30),
            ow("bk2", "HOME", 1.9, 40), ow("bk2", "AWAY", 2.0, b2_away),
            ow("bk3", "HOME", 1.85, 50)]


# ------------------------------------------------------------------------------------- MLB: _mlb_store_odds ----

def test_mlb_rows_carry_their_own_stamp_and_the_snapshot_the_oldest_the_close_priced(iso):
    from src.db.database import session_scope
    from src.ingestion.service import _mlb_store_odds
    ko = _now() + timedelta(days=2)
    with session_scope() as s:
        m = _match(s, "mlb", ko)
        assert _mlb_store_odds(s, m, _mlb_rows(ko)) == (5, True)
        mid = m.id
    odds, snaps = _stored(mid)
    h = lambda n: ko - timedelta(hours=n)
    assert odds == [("bk1", "AWAY", h(30)), ("bk1", "HOME", h(30)), ("bk2", "AWAY", h(40)), ("bk2", "HOME", h(40)),
                    ("bk3", "HOME", h(50))]
    assert snaps == [("AWAY", h(40)), ("HOME", h(40))]          # bk2's, the oldest priced; never bk3's one side


def test_one_unknown_row_the_close_priced_makes_the_snapshot_unknown(iso):
    from src.db.database import session_scope
    from src.ingestion.service import _mlb_store_odds
    ko = _now() + timedelta(days=2)
    with session_scope() as s:
        m = _match(s, "mlb-null", ko)
        _mlb_store_odds(s, m, _mlb_rows(ko, b2_away=None))
        mid = m.id
    odds, snaps = _stored(mid)
    assert [t for bk, sel, t in odds if (bk, sel) == ("bk2", "AWAY")] == [None]
    assert {t for _, t in snaps} == {None}                      # unknown is never read as fresh (addendum 32 item 3)


@pytest.mark.parametrize("iso", ["absent"], indirect=True)
def test_without_the_columns_the_mlb_sync_writes_its_rows_and_snapshots_and_nothing_else(iso):
    from src.db.database import session_scope
    from src.ingestion.service import _mlb_store_odds
    ko = _now() + timedelta(days=2)
    with session_scope() as s:
        m = _match(s, "mlb-absent", ko)
        assert _mlb_store_odds(s, m, _mlb_rows(ko)) == (5, True)
        mid = m.id
    odds, snaps = _stored(mid)
    assert len(odds) == 5 and len(snaps) == 2
    assert {t for *_, t in odds} == {None} and {t for _, t in snaps} == {None}


def test_a_row_type_without_the_field_stores_unknown(iso):
    """The adapter's row carries no provider time until its parse is read from a kept answer (Law 1): NULL."""
    from src.db.database import session_scope
    from src.ingestion.service import _mlb_store_odds
    ko = _now() + timedelta(days=2)
    rows = [NS(market="1X2", selection=sel, bookmaker="bk", price_decimal=px, line=None)
            for sel, px in (("HOME", 1.8), ("AWAY", 2.1))]
    with session_scope() as s:
        m = _match(s, "mlb-bare", ko)
        _mlb_store_odds(s, m, rows)
        mid = m.id
    odds, snaps = _stored(mid)
    assert {t for *_, t in odds} == {None} and {t for _, t in snaps} == {None}


def test_the_odds_close_and_the_snapshot_close_read_one_stamp(iso):
    """book_stamp reads the odds rows the close priced, or the snapshot's legs (close.priced_rows): the same time."""
    from src.db.database import session_scope
    from src.db.schema import Match, Odds, OddsSnapshot
    from src.ingestion.service import _mlb_store_odds
    from src.walters.close import BINARY, book_stamp, close_1x2, close_from_snapshots
    ko = _now() + timedelta(days=2)
    with session_scope() as s:
        m = _match(s, "mlb-one", ko)
        _mlb_store_odds(s, m, _mlb_rows(ko))
        mid = m.id
    with session_scope() as s:
        m = s.get(Match, mid)
        by_odds = book_stamp(close_1x2(list(s.query(Odds).filter(Odds.match_id == mid)), m.utc_date, BINARY), s)
        by_snap = book_stamp(close_from_snapshots(list(s.query(OddsSnapshot).filter(OddsSnapshot.match_id == mid)),
                                                  m.utc_date, BINARY), s)
    assert by_odds == by_snap == ko - timedelta(hours=40)


def test_the_24_hour_rule_then_applies_to_mlb_forward(iso):
    """A stamp the MLB sync stored 40 h before first pitch: the close is the session's Kalshi two-sided mid."""
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    from src.ingestion.service import _mlb_store_odds
    from src.walters.close import grading_close
    ko = _now() + timedelta(days=2)
    with session_scope() as s:
        m = _match(s, "mlb-rule", ko)
        _mlb_store_odds(s, m, _mlb_rows(ko))
        s.flush()
        at = s.query(OddsSnapshot).filter(OddsSnapshot.match_id == m.id).first().captured_at + timedelta(seconds=5)
        for sel, bid, ask in (("HOME", 0.60, 0.61), ("AWAY", 0.39, 0.40)):
            s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=0.5, n_books=1, captured_at=at,
                               source="kalshi", yes_bid=bid, yes_ask=ask))
        mid = m.id
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
    assert (cl["source"], cl["reference"]) == ("kalshi", "kalshi") and cl["fair"]["HOME"] == pytest.approx(0.605)
    assert cl["book_stamp_age_h"] == pytest.approx(40.0)


# ----------------------------------------------------------------------------- PL: IngestionService.sync_odds ----

class _FakeSoccerOdds:
    source_name = "fakeodds"

    def __init__(self, rows):
        self.rows = rows

    def list_odds(self, source_id):
        return list(self.rows)


def _pl_rows(ko, at, *, hours=(30, 40)):
    def no(bk, sel, px, h):
        return NormalizedOdds(match_source_id="g1", source="fakeodds", bookmaker=bk, market="1X2", selection=sel,
                              price_decimal=px, captured_at=at,
                              source_updated_at=None if h is None else ko - timedelta(hours=h))
    return [no(bk, sel, px, h) for bk, h in zip(("bk1", "bk2"), hours)
            for sel, px in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8))]


def test_the_pl_sync_stores_the_stamps_and_a_stale_three_way_close_keeps_its_book_and_says_why(iso):
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.ingestion.service import IngestionService
    from src.walters.close import graded_block, grading_close, priced
    ko, at = _now() + timedelta(days=2), _now()
    with session_scope() as s:
        mid = _match(s, "pl", ko, sport=Sport.SOCCER, code="PL", ext={"fakeodds": "g1"}).id
    r = IngestionService(_FakeSoccerOdds(_pl_rows(ko, at))).sync_odds("PL")
    assert r.created == 1
    odds, snaps = _stored(mid)
    h = lambda n: ko - timedelta(hours=n)
    assert [t for bk, _, t in odds] == [h(30)] * 3 + [h(40)] * 3
    assert snaps == [("AWAY", h(40)), ("DRAW", h(40)), ("HOME", h(40))]
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
    assert priced(cl) and cl.get("source") != "kalshi" and cl["stale_unswitched"].startswith("three-way board")
    g = graded_block(cl, ko)
    assert g["close_reference"] == "books" and g["close_book_stamp_age_h"] == 40.0
    assert g["close_stale_unswitched"] == cl["stale_unswitched"]


@pytest.mark.parametrize("iso", ["absent"], indirect=True)
def test_without_the_columns_the_pl_sync_writes_its_rows_and_snapshots_and_nothing_else(iso):
    from src.db.database import session_scope
    from src.ingestion.service import IngestionService
    ko, at = _now() + timedelta(days=2), _now()
    with session_scope() as s:
        mid = _match(s, "pl-absent", ko, sport=Sport.SOCCER, code="PL", ext={"fakeodds": "g1"}).id
    IngestionService(_FakeSoccerOdds(_pl_rows(ko, at))).sync_odds("PL")
    odds, snaps = _stored(mid)
    assert len(odds) == 6 and len(snaps) == 3
    assert {t for *_, t in odds} == {None} and {t for _, t in snaps} == {None}


def test_a_fresh_pl_stamp_keeps_the_book_close_with_no_label(iso):
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.ingestion.service import IngestionService
    from src.walters.close import graded_block, grading_close
    ko, at = _now() + timedelta(days=2), _now()
    with session_scope() as s:
        mid = _match(s, "pl-fresh", ko, sport=Sport.SOCCER, code="PL", ext={"fakeodds": "g1"}).id
    IngestionService(_FakeSoccerOdds(_pl_rows(ko, at, hours=(6, 8)))).sync_odds("PL")
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
    g = graded_block(cl, ko)
    assert g["close_reference"] == "books" and g["close_book_stamp_age_h"] == 8.0
    assert "close_stale_unswitched" not in g


# ------------------------------------------------- results-tally: a Kalshi-mid close is VERIFIED (comment 6270315541) ----

def _graded_mlb(s, key, ko, p, *, book_stamp_h=None):
    """A finished, predicted MLB game whose stored divergence is p minus the Kalshi mid 0.605 (bid 0.60, ask 0.61, five
    seconds after the book session): with two books stamped `book_stamp_h` hours before first pitch (the stale-book
    close), or with no book capture at all (book_stamp_h None: the 2026-10-05 kalshi_only close)."""
    from src.db.database import write_source_times
    from src.db.schema import Odds, OddsSnapshot, Prediction, PredictionOutcome, Result
    m = _match(s, key, ko, status="FINISHED")
    book_at = ko - timedelta(minutes=35)
    if book_stamp_h is not None:
        rows = [Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                     source="api_baseball", captured_at=book_at)
                for bk in ("bk1", "bk2") for sel, px in (("HOME", 1.8), ("AWAY", 2.1))]
        s.add_all(rows)
        s.flush()
        write_source_times(s, "odds", [(o.id, ko - timedelta(hours=book_stamp_h)) for o in rows])
    at = book_at + timedelta(seconds=5)
    for sel, bid, ask in (("HOME", 0.60, 0.61), ("AWAY", 0.39, 0.40)):
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=0.5, n_books=1, captured_at=at,
                           source="kalshi", yes_bid=bid, yes_ask=ask))
    pr = Prediction(match_id=m.id, model_version="st-probe", home_win_prob=p, draw_prob=None, away_win_prob=1 - p)
    s.add(pr)
    s.flush()
    s.add(PredictionOutcome(prediction_id=pr.id, actual_result=Result.HOME, actual_home_score=5, actual_away_score=2,
                            top_pick_hit=True, log_loss=0.4, clv=p - 0.605))


def test_results_tally_reads_the_kalshi_rows_so_a_kalshi_mid_close_is_verified(iso):
    from src.db.database import session_scope
    from src.walters.export import results_tally
    ko = _now() - timedelta(days=2)
    with session_scope() as s:
        _graded_mlb(s, "rt-stale", ko, 0.70, book_stamp_h=32.0)           # the stale-book rule's kalshi close
        _graded_mlb(s, "rt-konly", ko + timedelta(hours=1), 0.65)        # the kalshi_only close
    out = iso / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    mlb = out.read_text().split("## MLB", 1)[1].split("\n## ", 1)[0]
    want = ((0.70 - 0.605) + (0.65 - 0.605)) / 2 * 100
    assert f"- Mean model-close divergence, verified close: {want:+.2f}pp (n=2)" in mlb
    assert "Retained-legacy" not in mlb
