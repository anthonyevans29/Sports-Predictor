"""#382 (ARCHITECT 2026-10-26 11:55 ET item (2); 2026-10-27 15:20 ET item 2): the book-stamp age receipt, on an
isolated throwaway DB opened mode=ro. The stamp columns are unmapped (addendum 35 item 2): the fixture adds them as
migrate_odds_source_updated_at.py would (`absent` leaves them out), as tests/test_book_source_times_615.py does."""
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bsa", ROOT / "scripts" / "book_stamp_age_receipt.py")
bsa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsa)

SUN = datetime(2026, 10, 25, 17, 0)        # Sunday 13:00 ET (EDT): "Sun early"


@pytest.fixture(params=["present"])
def iso(tmp_path, monkeypatch, request):
    from src.db import database
    from src.db.schema import Base
    db = tmp_path / "iso.db"
    eng = create_engine(f"sqlite:///{db}", future=True)
    Base.metadata.create_all(eng)
    if request.param == "present":
        with eng.begin() as c:
            for t in ("odds", "odds_snapshots"):
                c.execute(text(f"ALTER TABLE {t} ADD COLUMN source_updated_at DATETIME"))
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True, expire_on_commit=False))
    monkeypatch.setattr(database, "_engine", eng)
    monkeypatch.chdir(tmp_path)
    yield db
    eng.dispose()


def _comp(s, sport, code):
    from src.db.schema import Competition
    c = s.query(Competition).filter_by(code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def game(s, key, ko, *, sport="NFL", code="NFL", stage="Regular Season", books=(("bk1", 11), ("bk2", 11)),
         outcome=True, scored=True):
    """A finished, predicted game with one pre-kickoff 1X2 session: each book (name, stamp hours before kickoff or
    None) quotes the whole outcome set."""
    from src.db.schema import Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result, Sport, Team
    sp = getattr(Sport, sport)
    c = _comp(s, sp, code)
    h, a = Team(sport=sp, name=f"{key} H"), Team(sport=sp, name=f"{key} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sp, competition_id=c.id, season="2026", utc_date=ko, status=MatchStatus.FINISHED, stage=stage,
              home_team_id=h.id, away_team_id=a.id, home_score=21 if scored else None, away_score=17 if scored else None)
    s.add(m)
    s.flush()
    sels = ("HOME", "DRAW", "AWAY") if sport == "SOCCER" else ("HOME", "AWAY")
    for bk, hrs in books:
        for sel in sels:
            o = Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel,
                     price_decimal={"HOME": 1.9, "DRAW": 3.4, "AWAY": 2.0}[sel], captured_at=ko - timedelta(minutes=35))
            s.add(o)
            s.flush()
            if hrs is not None:
                s.execute(text("UPDATE odds SET source_updated_at = :t WHERE id = :i"),
                          {"t": (ko - timedelta(hours=hrs)).isoformat(sep=" "), "i": o.id})
    p = Prediction(match_id=m.id, model_version="t", home_win_prob=0.6, away_win_prob=0.4)
    s.add(p)
    s.flush()
    if outcome:
        s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME, actual_home_score=21,
                                actual_away_score=17, top_pick_hit=True, log_loss=0.5))
    return m.id


def run(**kw):
    out = []
    res = bsa.report(echo=out.append, **kw)
    return "\n".join(out), res


def test_every_graded_game_is_in_the_denominator_with_its_cause(iso):
    from src.db.database import session_scope
    with session_scope() as s:
        game(s, "eleven", SUN, books=(("bk1", 11), ("bk2", 11)))                 # 11 h: under the 24 h flag
        game(s, "thirty", SUN + timedelta(hours=3, minutes=25), books=(("bk1", 30),))   # stale: no Kalshi, unpriced
        game(s, "nobook", SUN + timedelta(days=1, hours=3), books=())             # no close at all: (d)
        game(s, "unstamped", SUN + timedelta(days=-3, hours=3), books=(("bk1", None),))   # (b) Thu
        game(s, "partial", SUN + timedelta(hours=7, minutes=20), books=(("bk1", 5), ("bk2", None)))   # (c) SNF
        game(s, "prelive", datetime(2026, 9, 14, 17, 0))                          # Week 2: pre-live, never counted
        game(s, "preseason", SUN, stage="Pre Season")                             # a preseason stage: never
    text_, res = run()
    nfl = res["NFL"]
    assert nfl["games"] == 5 and nfl["stamped"] == 2
    assert nfl["unknown"] == {"a": 0, "b": 1, "c": 1, "d": 1}
    assert "== NFL: 5 graded game(s) · stamped 2 · unknown 3 · re-dated (kept out) 0" in text_
    assert nfl["book_priced"] == 4                                            # addendum 172 item 3: (d) excluded
    assert ("  stamped share: of book-priced games (unknown a to c and stamped; d excluded) 2 of 4 (50.0%) · "
            "of all games (re-dated kept out) 2 of 5 (40.0%)") in text_
    assert "    12-24 h: 0 of 5 (unknowns in the denominator)" in text_
    assert "    6-12 h: 1 of 5 (unknowns in the denominator)" in text_ and "    24-48 h: 1 of 5" in text_
    assert "    more than STALE_BOOK_H (24 h, the code's switch): 1 of 5" in text_
    assert nfl["dist"]["min"] == pytest.approx(11.0) and nfl["dist"]["max"] == pytest.approx(30.0)
    assert "books, stale and unpriced 1" in text_ and "unpriced 1" in text_
    assert set(nfl["by_slot"]) == {"Sun early (12:00-14:59 ET)", "Sun late (15:00-18:59 ET)", "MNF (Mon)",
                                   "Thu day (before 19:00 ET)", "SNF (Sun 19:00 ET on)"}
    assert nfl["by_book"]["bk1"]["games"] == 4 and nfl["by_book"]["bk2"]["games"] == 2
    assert nfl["multi_stamp_games"] == 0 and nfl["first_stamped_kickoff"] == SUN.isoformat()
    line = next(x for x in text_.splitlines() if x.startswith("BOOK-STAMP-AGE-RECEIPT "))
    assert json.loads(line[len("BOOK-STAMP-AGE-RECEIPT "):])["NFL"]["games"] == 5


def test_pl_from_the_629_merge_three_way_never_switched_and_snapshot_closes_have_no_book(iso):
    from src.db.database import session_scope
    from src.db.schema import OddsSnapshot
    with session_scope() as s:
        game(s, "pl-stale", datetime(2026, 10, 25, 15, 0), sport="SOCCER", code="PL", books=(("bk1", 30),))
        game(s, "pl-before", datetime(2026, 10, 18, 14, 0), sport="SOCCER", code="PL")       # before --pl-since
        game(s, "pl-ungraded", datetime(2026, 10, 25, 14, 0), sport="SOCCER", code="PL", outcome=False)
        mid = game(s, "pl-snap", datetime(2026, 10, 26, 20, 0), sport="SOCCER", code="PL", books=())
        for sel, px in (("HOME", 0.5), ("DRAW", 0.25), ("AWAY", 0.25)):
            x = OddsSnapshot(match_id=mid, market="1X2", selection=sel, source="api_football", n_books=4,
                             devig_prob=px, captured_at=datetime(2026, 10, 26, 19, 25))
            s.add(x)
            s.flush()
            s.execute(text("UPDATE odds_snapshots SET source_updated_at = :t WHERE id = :i"),
                      {"t": "2026-10-26 18:00:00", "i": x.id})
    text_, res = run()
    pl = res["PL"]
    assert pl["games"] == 2 and pl["stamped"] == 2 and pl["snapshot_only"] == 1
    assert "books, stale and unswitched (three-way) 1" in text_          # a three-way board keeps its book close
    assert set(pl["by_slot"]) == {"Sun 15:00 UK", "Mon 20:00 UK"}       # GMT from 10-25
    assert set(pl["by_book"]) == {"bk1"} and pl["by_book"]["bk1"]["games"] == 1     # the snapshot close has none
    assert "games whose close is a book snapshot (consensus only, no bookmaker): 1" in text_


@pytest.mark.parametrize("iso", ["absent"], indirect=True)
def test_a_database_without_the_stamp_column_is_unknown_a_never_fresh(iso):
    from src.db.database import session_scope
    with session_scope() as s:
        game(s, "old", SUN, books=(("bk1", None),))
        game(s, "none", SUN + timedelta(days=1), books=())              # no priced close: stays (d) (review of #382)
    text_, res = run()
    assert res["NFL"]["unknown"]["a"] == 1 and res["NFL"]["unknown"]["d"] == 1 and res["NFL"]["stamped"] == 0
    assert ("odds.source_updated_at: ABSENT (every priced book close from odds reads unknown (a); a game with no "
            "priced book close stays (d))") in text_


def test_a_redated_game_is_listed_and_kept_out_with_exports(iso, tmp_path):
    from src.db.database import session_scope
    from tests.test_void_redated import write_closing
    with session_scope() as s:
        mid = game(s, "moved", SUN)
    write_closing(tmp_path / "ex", SUN - timedelta(days=3, minutes=35),
                  [{"match_id": mid, "home_team": "moved H", "away_team": "moved A",
                    "utc_date": (SUN - timedelta(days=3)).isoformat(), "desk": {}}], fam="NFL")
    text_, res = run(exports_dir=str(tmp_path / "ex"))
    assert res["NFL"]["redated"] == 1 and res["NFL"]["stamped"] == 0
    assert "re-dated, kept out: match" in text_


def test_the_database_is_read_only_and_a_missing_file_exits_2(iso, tmp_path, monkeypatch, capsys):
    from src.db import database
    from src.db.database import session_scope
    with session_scope() as s:
        game(s, "ro", SUN)
    before = iso.read_bytes()
    run()
    assert iso.read_bytes() == before
    missing = tmp_path / "none.db"
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{missing}"), future=True))
    assert bsa.main([]) == 2 and "REFUSED: no DB file" in capsys.readouterr().out and not missing.exists()


def test_the_slot_table():
    assert bsa.slot("NFL", datetime(2026, 10, 18, 13, 30)) == "Sun international (before 12:00 ET)"   # Wembley
    assert bsa.slot("NFL", datetime(2026, 10, 23, 0, 15)) == "TNF (Thu 19:00 ET on)"                    # Thu 20:15 ET
    assert bsa.slot("NFL", datetime(2026, 11, 26, 17, 30)) == "Thu day (before 19:00 ET)"               # Thanksgiving
    assert bsa.slot("NFL", datetime(2026, 11, 27, 1, 20)) == "TNF (Thu 19:00 ET on)"
    assert bsa.slot("NFL", datetime(2026, 10, 26, 0, 20)) == "SNF (Sun 19:00 ET on)"
    assert bsa.slot("NFL", datetime(2026, 10, 27, 0, 15)) == "MNF (Mon)"
    assert bsa.slot("PL", datetime(2026, 10, 24, 14, 0)) == "Sat 15:00 UK"                              # BST
    assert bsa.slot("PL", datetime(2026, 11, 1, 15, 0)) == "Sun 15:00 UK"                               # GMT
    assert bsa.bucket(-0.5).startswith("under 0 h") and bsa.bucket(24.0) == "24-48 h"



def test_review_of_382_offsets_refused_empty_exports_named_and_a_schemaless_file_refused(iso, tmp_path, monkeypatch,
                                                                                        capsys):
    """An offset --pl-since is refused (the bind drops it); an --exports dir with no closing file reads UNLABELLED,
    never "labelled"; a database file without the app's tables is refused, exit 2, never a traceback."""
    from src.db import database
    with pytest.raises(SystemExit) as e:
        bsa.main(["--pl-since", "2026-10-20T14:42:00-04:00"])
    assert e.value.code == 2 and "naive-UTC" in capsys.readouterr().err
    with pytest.raises(ValueError, match="naive-UTC"):
        bsa.report(pl_since="2026-10-20T14:42:00-04:00", echo=lambda *_: None)
    text_, res = run(exports_dir=str(tmp_path / "no-such-dir"))
    assert "re-dates: UNLABELLED (no closing file read in" in text_ and "labelled from" not in text_
    bare = tmp_path / "bare.db"
    eng = create_engine(f"sqlite:///{bare}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE x (a INT)"))
    eng.dispose()
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{bare}"), future=True))
    assert bsa.main([]) == 2 and "has no matches" in capsys.readouterr().out



def test_codex_round_1_on_720_teams_table_per_book_ages_and_the_column_per_table(iso, tmp_path, monkeypatch,
                                                                                capsys):
    """(1) a file without the teams table is refused, exit 2; (2) each book's age is read from its own rows (a newer
    book keeps its own age, an unstamped book is unknown alone); (3) the stamp column is checked on the close's own
    table: a snapshot close on a database whose odds_snapshots has no column is unknown (a), not (b)."""
    from src.db import database
    from src.db.database import session_scope
    with session_scope() as s:
        game(s, "two-stamps", SUN, books=(("bk1", 10), ("bk2", 30)))         # the game reads the oldest: 30 h
        game(s, "one-unstamped", SUN + timedelta(hours=3, minutes=25), books=(("bk1", 8), ("bk2", None)))
    text_, res = run()
    bb = res["NFL"]["by_book"]
    assert res["NFL"]["dist"]["max"] == pytest.approx(30.0) and res["NFL"]["multi_stamp_games"] == 1
    assert bb["bk1"]["games"] == 2 and bb["bk1"]["unknown"] == 0 and bb["bk1"]["max"] == pytest.approx(10.0)
    assert bb["bk2"]["games"] == 2 and bb["bk2"]["unknown"] == 1 and bb["bk2"]["min"] == pytest.approx(30.0)
    # (3) drop the snapshot column only: a PL snapshot close is (a)
    eng = database.SessionLocal.kw["bind"]
    with eng.begin() as c:
        c.execute(text("ALTER TABLE odds_snapshots DROP COLUMN source_updated_at"))
    from src.db.schema import OddsSnapshot
    with session_scope() as s:
        mid = game(s, "pl-snap", datetime(2026, 10, 26, 20, 0), sport="SOCCER", code="PL", books=())
        for sel, px in (("HOME", 0.5), ("DRAW", 0.25), ("AWAY", 0.25)):
            s.add(OddsSnapshot(match_id=mid, market="1X2", selection=sel, source="api_football", n_books=4,
                               devig_prob=px, captured_at=datetime(2026, 10, 26, 19, 25)))
    text_, res = run()
    assert res["PL"]["unknown"]["a"] == 1 and res["PL"]["unknown"]["b"] == 0
    assert "odds_snapshots.source_updated_at: ABSENT" in text_ and "odds.source_updated_at: present" in text_
    # (1) a file without teams
    bare = tmp_path / "noteams.db"
    e2 = create_engine(f"sqlite:///{bare}")
    from src.db.schema import Base
    Base.metadata.create_all(e2)
    with e2.begin() as c:
        c.execute(text("DROP TABLE teams"))
    e2.dispose()
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{bare}"), future=True))
    assert bsa.main([]) == 2 and "has no teams" in capsys.readouterr().out


def test_addendum_172_the_stamped_share_with_no_book_priced_game_reads_n_a(iso):
    from src.db.database import session_scope
    with session_scope() as s:
        game(s, "nobook", SUN, books=())                                         # (d) only
    text_, res = run()
    assert res["NFL"]["book_priced"] == 0
    assert ("stamped share: of book-priced games (unknown a to c and stamped; d excluded) 0 of 0 (n/a) · "
            "of all games (re-dated kept out) 0 of 1 (0.0%)") in text_
    assert ("stamped share: of book-priced games (unknown a to c and stamped; d excluded) 0 of 0 (n/a) · "
            "of all games (re-dated kept out) 0 of 0 (n/a)") in text_         # the PL section, no game
