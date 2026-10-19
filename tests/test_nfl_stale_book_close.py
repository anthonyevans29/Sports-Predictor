"""THE STALE BOOK CLOSE (ARCHITECT 2026-10-19, addendum 137 item 4, #614), on an isolated throwaway DB.

Verbatim: "FOR A GRADED GAME WHOSE BOOK QUOTE CARRIES A PROVIDER STAMP MORE THAN 24 HOURS BEFORE KICKOFF, THE RECORDED
CLOSE IS THE KALSHI TWO-SIDED MID CAPTURED IN THE SAME LAST PRE-KICKOFF SESSION, and the row says so
(`close_reference: kalshi`, with the book stamp's age in hours beside it; the `kalshi_only_closes` count in the record
block already exists for this). A NULL or absent stamp keeps the book close (unknown is not stale: law 4 labels it, it
does not switch it) until the stamp is stored. [...] Code: one PR, the nfl_predict grader first (it reads `close_1x2`
only today), export.export_results' `grading_close` the same rule."

The world is the closing run's: two complete books captured at T-35 (the odds step), the Kalshi legs seconds later
(the next step), the book quote's provider stamp from `response[].update` (write_source_times, the sync's own
writer). The stamp columns are unmapped (addendum 35 item 2): the fixture adds them to the isolated DB, and points the
column check (database._engine) at it, as migrate_odds_source_updated_at.py would; `absent` leaves them out."""
import json
import math
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.db.schema import Sport

H, A = 1.8, 2.1                                             # two books at 1.8 / 2.1, de-vigged per book
BOOK_H = round((1 / H) / (1 / H + 1 / A), 4)
BOOK_A = round((1 / A) / (1 / H + 1 / A), 4)


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


def _world(s, key, ko, *, stamp_h=32.0, kalshi=((0.60, 0.61, 5),), hs=27, aw=10, p=0.70, sport=Sport.NFL,
           code="NFL", week=6, three=False):
    """One finished, predicted game: two complete books at ko - 35 min whose provider stamp is `stamp_h` hours
    before kickoff (None: NULL); Kalshi captures as (home bid, home ask, seconds after the book capture) — the AWAY
    leg beside each, as the matcher stores it. Returns the match."""
    from src.db.database import write_source_times
    from src.db.schema import Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction, Team
    c = s.query(Competition).filter_by(code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="US", type="LEAGUE")
        s.add(c)
        s.flush()
    h, a = Team(sport=sport, name=f"SB {key} H"), Team(sport=sport, name=f"SB {key} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=c.id, season="2026", matchday=week, utc_date=ko,
              status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=aw)
    s.add(m)
    s.flush()
    book_at = ko - timedelta(minutes=35)
    sels = (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)) if three else (("HOME", H), ("AWAY", A))
    rows = [Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                 source="api_american_football", captured_at=book_at) for bk in ("bk1", "bk2") for sel, px in sels]
    s.add_all(rows)
    for bid, ask, after in kalshi:
        at = book_at + timedelta(seconds=after)
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=0.5, n_books=1, captured_at=at,
                           source="kalshi", yes_bid=bid, yes_ask=ask))
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection="AWAY", devig_prob=0.5, n_books=1, captured_at=at,
                           source="kalshi", yes_bid=None if ask is None else round(1 - ask, 4),
                           yes_ask=None if bid is None else round(1 - bid, 4)))
    s.add(Prediction(match_id=m.id, model_version="sb-probe", home_win_prob=p, draw_prob=None, away_win_prob=1 - p))
    s.flush()
    if stamp_h is not None:
        write_source_times(s, "odds", [(o.id, ko - timedelta(hours=stamp_h)) for o in rows])
    return m


def _ko():
    from src.timeutil import utc_now_naive
    return (utc_now_naive() - timedelta(days=2)).replace(microsecond=0)


def _close(m_id):
    from src.db.database import session_scope
    from src.db.schema import Match, Odds
    from src.walters.close import close_1x2, outcomes_for, stale_book_close
    with session_scope() as s:
        m = s.get(Match, m_id)
        odds = list(s.query(Odds).filter(Odds.match_id == m.id, Odds.market == "1X2"))
        return stale_book_close(s, m, close_1x2(odds, m.utc_date, outcomes_for(m.sport)))


# ------------------------------------------------------------------------------- the rule on one close ----

def test_a_stamp_more_than_24h_before_kickoff_grades_against_the_sessions_kalshi_mid(iso):
    from src.db.database import session_scope
    from src.walters.close import STALE_BOOK_RULING, graded_block, priced
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "stale", ko).id
    cl = _close(mid)
    assert priced(cl) and (cl["source"], cl["reference"]) == ("kalshi", "kalshi")
    assert cl["fair"]["HOME"] == pytest.approx(0.605) and cl["fair"]["AWAY"] == pytest.approx(0.395)
    assert cl["captured_at"] == ko - timedelta(minutes=35) + timedelta(seconds=5)          # the Kalshi capture
    assert cl["book_stamp_age_h"] == pytest.approx(32.0) and cl["kalshi"]["ruling"] == STALE_BOOK_RULING
    assert cl["book_fair"]["HOME"] == pytest.approx(BOOK_H, abs=1e-4) and cl["book_captured_at"] == ko - timedelta(minutes=35)
    blk = graded_block(cl, ko)
    assert blk["close_reference"] == "kalshi" and blk["close_book_stamp_age_h"] == 32.0
    assert blk["close_fair"] == {"HOME": 0.605, "AWAY": 0.395} and blk["close_books"] == 0
    assert blk["close_kalshi"] == {"bid": 0.60, "ask": 0.61, "mid": pytest.approx(0.605), "spread_c": 1.0,
                                   "book_fair": {"HOME": BOOK_H, "AWAY": BOOK_A},
                                   "book_at": (ko - timedelta(minutes=35)).isoformat()}
    assert blk["close_minutes_before_start"] == 34 and "addendum 137 item 4" in blk["close_source"]


@pytest.mark.parametrize("stamp_h, age", [(24.0, 24.0), (6.25, 6.25), (None, None)],
                         ids=["exactly-24h", "fresh", "NULL-stamp"])
def test_a_stamp_not_more_than_24h_old_or_unknown_keeps_the_book_close(iso, stamp_h, age):
    """"MORE THAN 24 HOURS": 24 h exactly keeps the book. A NULL stamp is unknown, not stale (law 4): the book."""
    from src.db.database import session_scope
    from src.walters.close import graded_block
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, f"keep{stamp_h}", ko, stamp_h=stamp_h).id
    cl = _close(mid)
    assert cl.get("reference") in (None, "books") and cl.get("source") != "kalshi"
    assert cl["fair"]["HOME"] == pytest.approx(BOOK_H, abs=1e-4)
    blk = graded_block(cl, ko)
    assert blk["close_book_stamp_age_h"] == age and blk["close_fair"] == {"HOME": BOOK_H, "AWAY": BOOK_A}
    assert "close_kalshi" not in blk


@pytest.mark.parametrize("iso", ["absent"], indirect=True)
def test_before_the_migration_every_stamp_is_unknown_and_nothing_raises(iso):
    from src.db.database import session_scope
    from src.walters.close import graded_block
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "premig", ko).id                   # write_source_times writes nothing: no column
    cl = _close(mid)
    assert cl["book_stamp"] is None and graded_block(cl, ko)["close_reference"] in (None, "books")
    assert cl["fair"]["HOME"] == pytest.approx(BOOK_H, abs=1e-4)


def test_the_same_session_is_the_book_closes_run_not_a_later_kalshi_capture(iso):
    """The closing run writes the book, then Kalshi seconds later; a later run's Kalshi sync (it stamps every placed
    game in its window) is another session. The book close's session's quote is the close, not the newest one."""
    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "later", ko, kalshi=((0.60, 0.61, 5), (0.70, 0.71, 25 * 60))).id
    cl = _close(mid)
    assert cl["reference"] == "kalshi" and cl["fair"]["HOME"] == pytest.approx(0.605)


@pytest.mark.parametrize("kalshi, why", [
    ((), "none"),
    (((None, 0.61, 5),), "one-sided"),
    (((0.60, 0.63, 5),), "3c wide"),
    (((0.60, 0.61, 11 * 60),), "another session (11 min after the book)"),
], ids=["no-kalshi", "one-sided", "over-the-cap", "outside-the-session"])
def test_a_stale_book_with_no_two_sided_kalshi_quote_in_its_session_is_unpriced(iso, kalshi, why):
    """The stale book is not the close and no other quote stands in for it: unpriced, the row says why."""
    from src.db.database import session_scope
    from src.walters.close import graded_block, priced
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, f"unp{why}", ko, kalshi=kalshi).id
    cl = _close(mid)
    assert not priced(cl) and cl["reference"] is None and cl["book_stamp_age_h"] == pytest.approx(32.0)
    blk = graded_block(cl, ko)
    assert blk["close_fair"] is None and blk["close_reference"] is None and blk["close_book_stamp_age_h"] == 32.0
    assert blk["close_stale_book"] == ("book stamp 32.00 h before kickoff; no two-sided Kalshi quote within the 2c "
                                       "cap in the book close's session")


def test_mismatched_kalshi_legs_are_no_close_here_either(iso, monkeypatch):
    """Addendum 37 item 3: no close from mismatched Kalshi legs (kalshi_legs.guard_snaps, as the kalshi_only close)."""
    from src.db.database import session_scope
    from src.walters import kalshi_legs
    from src.walters.close import priced
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "mism", ko).id
    monkeypatch.setattr(kalshi_legs, "mismatched", lambda conn, ids: {i: ["KXNFLGAME-X"] for i in ids})
    cl = _close(mid)
    assert not priced(cl) and cl["stale_book"]


def test_a_three_way_board_keeps_its_book_close_and_says_why(iso):
    """The rule names a two-sided mid; Kalshi's three-way legs have no derived price (close_from_kalshi)."""
    from src.db.database import session_scope
    from src.walters.close import graded_block, priced
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "three", ko, sport=Sport.SOCCER, code="PL", three=True).id
    cl = _close(mid)
    assert priced(cl) and cl.get("source") != "kalshi" and cl["stale_unswitched"].startswith("three-way board")
    assert graded_block(cl, ko)["close_stale_unswitched"] == cl["stale_unswitched"]


# ------------------------------------------------------------ the NFL grader, the file and RESULTS.md ----

def _season(s, ko):
    _world(s, "w-stale", ko)                                               # Kalshi 0.605 for the book's 0.5385
    _world(s, "w-fresh", ko + timedelta(hours=1), stamp_h=6.0, hs=10, aw=27, p=0.65)
    _world(s, "w-null", ko + timedelta(hours=2), stamp_h=None, hs=24, aw=3, p=0.60)
    _world(s, "w-unpriced", ko + timedelta(hours=3), kalshi=(), hs=24, aw=3, p=0.55)


def test_the_nfl_file_and_the_grade_read_one_close_and_count_the_kalshi_closes(iso):
    from src.db.database import session_scope
    from src.walters import vs_close as vc
    from src.walters.nfl_predict import export_nfl_results, grade_nfl
    ko = _ko()
    with session_scope() as s:
        _season(s, ko)
    doc = json.load(open(export_nfl_results(out_dir=str(iso / "x"))))
    by = {r["home_team"]: r["graded"] for r in doc["results"]}
    g = by["SB w-stale H"]
    assert (g["close_reference"], g["close_book_stamp_age_h"], g["close_home_prob"]) == ("kalshi", 32.0, 0.605)
    assert g["clv"] == round(0.70 - 0.605, 4) and g["close_kalshi"]["book_fair"]["HOME"] == BOOK_H
    f = by["SB w-fresh H"]
    assert (f["close_reference"], f["close_book_stamp_age_h"], f["close_home_prob"]) == ("books", 6.0, BOOK_H)
    n = by["SB w-null H"]
    assert (n["close_reference"], n["close_book_stamp_age_h"], n["close_home_prob"]) == ("books", None, BOOK_H)
    u = by["SB w-unpriced H"]
    assert (u["close_reference"], u["close_fair"], u["close_home_prob"], u["clv"]) == (None, None, None, None)
    assert u["close_stale_book"].startswith("book stamp 32.00 h before kickoff")
    want = {**vc.block([(0.70, 0.605), (0.35, BOOK_A), (0.60, BOOK_H)]), "kalshi_only_closes": 1}
    assert doc["record"]["vs_close"] == want and doc["record"]["by_week"]["6"]["vs_close"] == want
    lines = []
    r = grade_nfl(days_back=None, progress=lines.append, exports_dir=str(iso / "x"))
    assert r["vs_close"] == want                                          # ONE RECORD DEFINITION (2026-10-06)
    # the pick divergence moves with the close: home picks all three, against 0.605 (Kalshi) and the book twice
    assert r["mean_clv_pp"] == pytest.approx(((0.70 - 0.605) + (0.65 - BOOK_H) + (0.60 - BOOK_H)) / 3 * 100, abs=0.01)
    assert any(x == f"  ── {vc.line(want)}" for x in lines)
    assert vc.line(want).endswith(" · 1 of the closes the Kalshi-only mid")


def test_results_md_names_the_rule(iso):
    from src.walters.export import results_tally
    out = iso / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    assert "STALE BOOK CLOSE (ARCHITECT 2026-10-19, addendum 137 item 4)" in txt and "close_reference kalshi" in txt


# ------------------------------------------------------ grading_close (every family where a stamp exists) ----

def test_grading_close_and_the_clv_restate_apply_the_same_rule(iso):
    """export.export_results' grading_close (MLB, PL: no stamp is stored for them today, so it is inert there) and
    clv_restate's copy of it switch the same stale book close, and the results block says so."""
    from src.db.database import session_scope
    from src.db.schema import Match, Odds, OddsSnapshot
    from src.walters.clv_restate import _close_for
    from src.walters.close import grading_close, grading_close_block
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "gc", ko, sport=Sport.MLB, code="MLB").id
    with session_scope() as s:
        m = s.get(Match, mid)
        cl, blk = grading_close(s, m), grading_close_block(s, m)
        rc = _close_for(list(s.query(Odds).filter(Odds.match_id == mid)),
                        list(s.query(OddsSnapshot).filter(OddsSnapshot.match_id == mid)), m)
    assert (cl["source"], cl["reference"]) == ("kalshi", "kalshi") and cl["fair"]["HOME"] == pytest.approx(0.605)
    assert (rc["source"], rc["fair"]["HOME"]) == ("kalshi", pytest.approx(0.605))
    assert blk["close_reference"] == "kalshi" and blk["close_book_stamp_age_h"] == 32.0


def test_a_stale_book_snapshot_close_meets_the_rule_too(iso):
    """grading_close's snapshot fallback (an odds table with no pre-kickoff session): its legs' stamp is read."""
    from src.db.database import session_scope, write_source_times
    from src.db.schema import Match, Odds, OddsSnapshot
    from src.walters.close import grading_close
    ko = _ko()
    with session_scope() as s:
        m = _world(s, "snap", ko, sport=Sport.MLB, code="MLB")
        s.query(Odds).filter(Odds.match_id == m.id).delete()          # replace-on-sync lost the session
        at = ko - timedelta(minutes=35)
        legs = [OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=pv, n_books=2, captured_at=at,
                             source="api_baseball") for sel, pv in (("HOME", 0.54), ("AWAY", 0.46))]
        s.add_all(legs)
        s.flush()
        write_source_times(s, "odds_snapshots", [(x.id, ko - timedelta(hours=30)) for x in legs])
        mid = m.id
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
    assert cl["reference"] == "kalshi" and cl["book_stamp_age_h"] == pytest.approx(30.0)
    assert cl["book_fair"]["HOME"] == pytest.approx(0.54)


def test_a_kalshi_only_close_is_untouched_by_the_rule(iso):
    """No book session pre-kickoff (the 2026-10-05 ruling): the kalshi_only close has no book stamp to read."""
    from src.db.database import session_scope
    from src.db.schema import Match, Odds
    from src.walters.close import grading_close
    ko = _ko()
    with session_scope() as s:
        m = _world(s, "konly", ko, sport=Sport.MLB, code="MLB")
        s.query(Odds).filter(Odds.match_id == m.id).delete()
        mid = m.id
    with session_scope() as s:
        cl = grading_close(s, s.get(Match, mid))
    assert cl["reference"] == "kalshi_only" and "book_stamp_age_h" not in cl
    assert cl["fair"]["HOME"] == pytest.approx(0.605)          # the last two-sided pre-kickoff quote


def test_the_constants():
    from src.walters import close
    assert close.STALE_BOOK_H == 24 and close.CAPTURE_SESSION == timedelta(minutes=10)
    assert close.KALSHI_SOURCES == ("kalshi_only", "kalshi")
    assert math.isclose(BOOK_H + BOOK_A, 1.0, abs_tol=1e-4)


# ------------------------------------------------------- the BEFORE / AFTER receipt (read-only, one DB state) ----

def test_the_restate_receipt_prints_both_records_and_writes_nothing(iso, capsys):
    import hashlib
    import importlib.util
    from pathlib import Path

    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        _season(s, ko)
    db = iso / "iso.db"
    ex = iso / "exports"
    ex.mkdir()
    before_hash = hashlib.sha256(db.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location(
        "nfl_close_restate_receipt", Path(__file__).resolve().parent.parent / "scripts" / "nfl_close_restate_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--db", str(db), "--exports", str(ex)]) == 0
    out = capsys.readouterr().out
    assert "read-only: db iso.db (mode=ro)" in out and str(iso) not in out          # no path is printed
    # BEFORE: the four books; AFTER: the stale one is the Kalshi mid and the stale one with no Kalshi is out
    assert "  BEFORE  vs close: 4 games" in out and "  AFTER   vs close: 3 games" in out
    assert out.count("· 1 of the closes the Kalshi-only mid") == 2                    # the season and week 6, AFTER
    assert ("switched to the session's Kalshi mid 1 · unpriced (no two-sided Kalshi quote within the cap in that "
            "session) 1") in out
    assert "rows whose close changed: 2" in out and "| kalshi | 0.605 |" in out and "| UNPRICED | None |" in out
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before_hash                 # the DB content untouched
    assert list(ex.iterdir()) == []                                                    # nothing written beside it


def test_the_restate_receipt_refuses_a_missing_db_and_creates_none(tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "nfl_close_restate_receipt", Path(__file__).resolve().parent.parent / "scripts" / "nfl_close_restate_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--db", str(tmp_path / "nope.db"), "--exports", str(tmp_path)]) == 2
    assert "REFUSED: no DB file" in capsys.readouterr().out and not (tmp_path / "nope.db").exists()


@pytest.mark.parametrize("iso", ["absent"], indirect=True)
def test_the_column_check_reads_the_database_the_query_runs_on(iso, tmp_path, monkeypatch):
    """has_source_time checked the app's engine while attach_source_times queried the session's: an app database
    that ran the migration beside a session database that had not made the guarded SELECT raise ("no such column")
    instead of reading the stamp as unknown. The check reads the session's own bind."""
    from src.db import database
    from src.db.database import session_scope
    from src.db.schema import Base
    migrated = create_engine(f"sqlite:///{tmp_path / 'migrated.db'}", future=True)
    Base.metadata.create_all(migrated)
    with migrated.begin() as c:
        for t in ("odds", "odds_snapshots"):
            c.execute(text(f"ALTER TABLE {t} ADD COLUMN source_updated_at DATETIME"))
    monkeypatch.setattr(database, "_engine", migrated)      # the app's engine has the column; the session's DB not
    ko = _ko()
    with session_scope() as s:
        mid = _world(s, "binds", ko).id
    cl = _close(mid)
    assert cl["book_stamp"] is None and cl["fair"]["HOME"] == pytest.approx(BOOK_H, abs=1e-4)
    migrated.dispose()
