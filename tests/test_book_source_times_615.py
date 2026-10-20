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
import json
from datetime import datetime, timedelta
from pathlib import Path
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
    h = lambda n: ko - timedelta(hours=n)
    assert odds == [("bk1", "AWAY", h(30)), ("bk1", "HOME", h(30)), ("bk2", "AWAY", None), ("bk2", "HOME", h(40)),
                    ("bk3", "HOME", h(50))]                     # each row its own: bk2 HOME keeps 40 h beside its None
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


@pytest.mark.parametrize("shape", ["one-sided", "totals-only"])
def test_a_board_with_no_snapshot_still_stamps_each_row(iso, shape):
    """No complete book (one side quoted, or no 1X2 at all): no snapshot is appended, each odds row keeps its own."""
    from src.db.database import session_scope
    from src.ingestion.service import _mlb_store_odds
    ko = _now() + timedelta(days=2)
    h = lambda n: ko - timedelta(hours=n)
    tot = [NS(market="TOTALS", selection=sel, bookmaker="bk1", price_decimal=1.9, line=8.5, source_updated_at=h(n))
           for sel, n in (("OVER", 11), ("UNDER", 12))]
    one = [NS(market="1X2", selection="HOME", bookmaker="bk1", price_decimal=1.8, line=None, source_updated_at=h(10))]
    rows = (one + tot) if shape == "one-sided" else tot
    with session_scope() as s:
        m = _match(s, f"mlb-{shape}", ko)
        assert _mlb_store_odds(s, m, rows) == (len(rows), False)
        mid = m.id
    odds, snaps = _stored(mid)
    assert sorted(t for *_, t in odds) == sorted(r.source_updated_at for r in rows) and snaps == []


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


@pytest.mark.parametrize("shape", ["one-sided", "totals-only"])
def test_a_pl_board_with_no_snapshot_still_stamps_each_row(iso, shape):
    from src.db.database import session_scope
    from src.ingestion.service import IngestionService
    ko, at = _now() + timedelta(days=2), _now()
    h = lambda n: ko - timedelta(hours=n)
    no = lambda sel, market, n: NormalizedOdds(match_source_id="g1", source="fakeodds", bookmaker="bk1",
                                               market=market, selection=sel, price_decimal=2.0, captured_at=at,
                                               source_updated_at=h(n))
    ou = [no("OVER", "OU_2.5", 11), no("UNDER", "OU_2.5", 12)]
    rows = ([no("HOME", "1X2", 10)] + ou[:1]) if shape == "one-sided" else ou
    with session_scope() as s:
        mid = _match(s, f"pl-{shape}", ko, sport=Sport.SOCCER, code="PL", ext={"fakeodds": "g1"}).id
    assert IngestionService(_FakeSoccerOdds(rows)).sync_odds("PL").created == 1
    odds, snaps = _stored(mid)
    assert sorted(t for *_, t in odds) == sorted(r.source_updated_at for r in rows) and snaps == []


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

def _graded(s, m, p, close_fair):
    from src.db.schema import Prediction, PredictionOutcome, Result
    pr = Prediction(match_id=m.id, model_version="st-probe", home_win_prob=p, draw_prob=None, away_win_prob=1 - p)
    s.add(pr)
    s.flush()
    s.add(PredictionOutcome(prediction_id=pr.id, actual_result=Result.HOME, actual_home_score=5, actual_away_score=2,
                            top_pick_hit=True, log_loss=0.4, clv=p - close_fair))


def _graded_mlb(s, key, ko, p, *, book_stamp_h=None):
    """A finished, predicted MLB game whose stored divergence is p minus the Kalshi mid 0.605 (bid 0.60, ask 0.61, five
    seconds after the book session): with two books stamped `book_stamp_h` hours before first pitch (the stale-book
    close), or with no book capture at all (book_stamp_h None: the 2026-10-05 kalshi_only close)."""
    from src.db.database import write_source_times
    from src.db.schema import Odds, OddsSnapshot
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
    _graded(s, m, p, 0.605)


def _graded_mlb_snapshot(s, key, ko, p):
    """A finished MLB game with no odds rows and no Kalshi rows: one complete pre-first-pitch book snapshot session
    (0.58 / 0.42), the close the tally still reads from the book snapshots."""
    from src.db.schema import OddsSnapshot
    m = _match(s, key, ko, status="FINISHED")
    for sel, dp in (("HOME", 0.58), ("AWAY", 0.42)):
        s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=dp, n_books=2,
                           captured_at=ko - timedelta(minutes=30), source="api_baseball"))
    _graded(s, m, p, 0.58)


def test_results_tally_reads_the_kalshi_rows_so_a_kalshi_mid_close_is_verified(iso):
    from src.db.database import session_scope
    from src.walters.export import results_tally
    ko = _now() - timedelta(days=2)
    with session_scope() as s:
        _graded_mlb(s, "rt-stale", ko, 0.70, book_stamp_h=32.0)           # the stale-book rule's kalshi close
        _graded_mlb(s, "rt-konly", ko + timedelta(hours=1), 0.65)        # the kalshi_only close
        _graded_mlb_snapshot(s, "rt-snap", ko + timedelta(hours=2), 0.66)  # a book snapshot close, read as before
    out = iso / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    mlb = txt.split("## MLB", 1)[1].split("\n## ", 1)[0]
    want = ((0.70 - 0.605) + (0.65 - 0.605) + (0.66 - 0.58)) / 3 * 100
    assert f"- Mean model-close divergence, verified close: {want:+.2f}pp (n=3)" in mlb
    assert "Retained-legacy" not in mlb
    assert "it reproduces and counts as VERIFIED (#615)" in txt and "close_reference kalshi_only" in txt


# ------------------------------------------- the soccer adapter: response[].update (addendum 147 item 1, law 1) ----

FIXTURE = Path(__file__).parent / "fixtures" / "odds_payloads" / "api_football_odds_fixture_1557437.json"
KEPT_UPDATE = datetime(2026, 10, 19, 16, 35, 22)          # "2026-10-19T16:35:22+00:00", the kept answer's own update


def _soccer_adapter(monkeypatch, answer):
    from src.adapters import api_football
    ad = api_football.APIFootballAdapter(api_key="test-key")
    monkeypatch.setattr(ad, "_get", lambda path, params=None: answer)
    return ad


def test_the_soccer_adapter_reads_the_answers_update_onto_every_row(monkeypatch):
    answer = json.loads(FIXTURE.read_text())
    rows = _soccer_adapter(monkeypatch, answer).list_odds("1557437")
    assert [(r.market, r.selection, r.price_decimal) for r in rows] == [("1X2", "HOME", 1.36), ("1X2", "DRAW", 4.75),
                                                                       ("1X2", "AWAY", 7.5)]
    assert {r.source_updated_at for r in rows} == {KEPT_UPDATE}
    assert all(r.captured_at != KEPT_UPDATE for r in rows)               # never our clock


@pytest.mark.parametrize("update", [None, "", "2026-10-19T16:35:22", 1792850400, "not a time"])
def test_an_absent_or_unreadable_update_stores_unknown(monkeypatch, update):
    """parse_source_updated_at's pins (tests/test_odds_source_updated_at.py): absent, offset-less, an epoch integer or
    unparseable -> None, never the fixture's date, never our clock."""
    answer = json.loads(FIXTURE.read_text())
    if update is None:
        answer["response"][0].pop("update")
    else:
        answer["response"][0]["update"] = update
    rows = _soccer_adapter(monkeypatch, answer).list_odds("1557437")
    assert len(rows) == 3 and {r.source_updated_at for r in rows} == {None}


def test_the_kept_answer_through_sync_odds_stamps_rows_and_snapshots_and_labels_the_stale_board(iso, monkeypatch):
    """The answer's update is 117.4 h before the fixture's kickoff: the PL book close stays, labelled (addendum 140 item
    3 reading (4); addendum 147 item 4: "a three-way board keeps its book close labelled, never a Kalshi mid")."""
    from src.adapters import api_football
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.ingestion import service as svc
    from src.walters.close import graded_block, grading_close, priced
    fetched = datetime(2026, 10, 20, 14, 3, 1)
    monkeypatch.setattr(api_football, "utc_now_naive", lambda: fetched)
    monkeypatch.setattr(svc, "utc_now_naive", lambda: fetched)
    ko = datetime(2026, 10, 24, 14, 0)                                    # the answer's fixture.date
    with session_scope() as s:
        mid = _match(s, "pl-kept", ko, sport=Sport.SOCCER, code="PL", ext={"api_football": "1557437"}).id
    r = svc.IngestionService(_soccer_adapter(monkeypatch, json.loads(FIXTURE.read_text()))).sync_odds("PL")
    assert r.created == 1
    odds, snaps = _stored(mid)
    assert {t for *_, t in odds} == {KEPT_UPDATE} and len(odds) == 3
    assert snaps == [("AWAY", KEPT_UPDATE), ("DRAW", KEPT_UPDATE), ("HOME", KEPT_UPDATE)]
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
    assert priced(cl) and cl.get("source") != "kalshi" and cl["stale_unswitched"].startswith("three-way board")
    g = graded_block(cl, ko)
    assert g["close_reference"] == "books" and g["close_book_stamp_age_h"] == round((ko - KEPT_UPDATE).total_seconds()
                                                                                     / 3600, 2)


def test_the_baseball_adapter_reads_no_update_field():
    """Addendum 147 item 2: api-baseball's odds answer carries no quote-time field (its only time-like keys are the
    game's own start), so the MLB half is NOT built and nothing is substituted; MLB rows store NULL."""
    import inspect
    from src.adapters import api_baseball
    assert "source_updated_at" not in inspect.getsource(api_baseball)


def test_the_cohort_receipt_prints_before_and_after_from_one_db_state(iso, capsys):
    """scripts/results_tally_cohort_receipt.py (addendum 147 item 3): main's read leaves the Kalshi-only close's
    divergence in retained-legacy; as built it reproduces and is verified. The DB is opened mode=ro."""
    import importlib.util
    from src.db.database import session_scope
    ko = _now() - timedelta(days=2)
    with session_scope() as s:
        _graded_mlb(s, "rc-konly", ko, 0.65)                                       # the kalshi_only close
        _graded_mlb_snapshot(s, "rc-snap", ko + timedelta(hours=2), 0.66)          # a book snapshot close
    (iso / "exports").mkdir()
    spec = importlib.util.spec_from_file_location(
        "rtc", Path(__file__).resolve().parent.parent / "scripts" / "results_tally_cohort_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--db", str(iso / "iso.db"), "--exports", str(iso / "exports")]) == 0
    out = capsys.readouterr().out.splitlines()
    mlb = out[out.index("## MLB") + 1:]
    before = [x for x in mlb if x.strip().startswith("BEFORE")]
    after = [x for x in mlb if x.strip().startswith("AFTER")]
    assert any("verified close: +8.00pp (n=1)" in x for x in before)
    assert any("Retained-legacy" in x and "(n=1)" in x for x in before)
    want = ((0.65 - 0.605) + (0.66 - 0.58)) / 2 * 100
    assert any(f"verified close: {want:+.2f}pp (n=2)" in x for x in after)
    assert not any("Retained-legacy" in x for x in after)
    assert mod.main(["--db", str(iso / "missing.db"), "--exports", str(iso / "exports")]) == 2   # never created
    assert not (iso / "missing.db").exists()


def test_the_cohort_receipt_refuses_when_the_db_changes_between_its_passes(iso, capsys, monkeypatch):
    """The data_version guard: a commit landing between BEFORE and AFTER (a chain writing) is refused, exit 3, and
    nothing is printed as a receipt."""
    import importlib.util
    import sqlite3
    from src.db.database import session_scope
    from src.walters import export
    ko = _now() - timedelta(days=2)
    with session_scope() as s:
        _graded_mlb(s, "rc-konly", ko, 0.65)
        _graded_mlb_snapshot(s, "rc-snap", ko + timedelta(hours=2), 0.66)
    (iso / "exports").mkdir()
    db = iso / "iso.db"
    real, calls = export.results_tally, []

    def tally_then_write(*a, **k):
        out = real(*a, **k)
        if not calls:                                   # a chain commits between BEFORE and AFTER
            with sqlite3.connect(db) as c:
                c.execute("UPDATE matches SET venue = 'moved' WHERE id = (SELECT MIN(id) FROM matches)")
        calls.append(1)
        return out
    monkeypatch.setattr(export, "results_tally", tally_then_write)
    spec = importlib.util.spec_from_file_location(
        "rtc", Path(__file__).resolve().parent.parent / "scripts" / "results_tally_cohort_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--db", str(db), "--exports", str(iso / "exports")]) == 3
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: the DB changed during the receipt") and "## MLB" not in out and len(calls) == 2


def test_the_cohort_receipt_holds_one_clock_and_leaves_grading_close_as_main_runs_it(iso, capsys, monkeypatch):
    """BEFORE narrows only the cohort split's snapshots (clv_cohort), so grading_close keeps the Kalshi rows as main
    reads them; both passes cut the window at one instant; every patched global is restored."""
    import importlib.util
    from src.db.database import session_scope
    from src.walters import clv_restate, export
    ko = _now() - timedelta(days=2)
    with session_scope() as s:
        _graded_mlb(s, "rc-konly", ko, 0.65)
    (iso / "exports").mkdir()
    real, nows, kinds = export.results_tally, [], []

    def spy(*a, **k):
        nows.append(export.utc_now_naive())
        from src.walters.close import grading_close_block
        from src.db.schema import Match
        with session_scope() as s:
            kinds.append(grading_close_block(s, s.query(Match).one())["close_reference"])
        return real(*a, **k)
    monkeypatch.setattr(export, "results_tally", spy)
    before = (clv_restate.clv_cohort, export.utc_now_naive)
    spec = importlib.util.spec_from_file_location(
        "rtc", Path(__file__).resolve().parent.parent / "scripts" / "results_tally_cohort_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--db", str(iso / "iso.db"), "--exports", str(iso / "exports")]) == 0
    assert len(nows) == 2 and nows[0] == nows[1]
    assert kinds == ["kalshi_only", "kalshi_only"]          # main's grading_close in BEFORE too
    assert (clv_restate.clv_cohort, export.utc_now_naive) == before
