"""Soccer ET flag + 90-minute score (2026-09-26): stored verbatim, never derived."""
from datetime import datetime

from sqlalchemy import create_engine, text

from src.adapters.api_football import APIFootballAdapter
from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, MatchStatus, Result, Sport, Team
from src.ingestion.service import IngestionService, SyncResult


def _fx(fid, short, goals, ft, home_wins=None):
    item = {"fixture": {"id": fid, "date": "2026-08-26T18:45:00+00:00", "venue": {}},
            "league": {"season": 2026, "round": "2nd Round"},
            "teams": {"home": {"id": 1, "winner": home_wins}, "away": {"id": 2, "winner":
                      (None if home_wins is None else not home_wins)}},
            "goals": {"home": goals[0], "away": goals[1]},
            "score": {"halftime": {"home": 0, "away": 0}}}
    if short is not None:
        item["fixture"]["status"] = {"short": short}
    if ft is not None:
        item["score"]["fulltime"] = {"home": ft[0], "away": ft[1]}
    return item


def test_football_adapter_stores_raw_status_and_90_minute_score():
    a = APIFootballAdapter(api_key="k")
    p = lambda it: a._parse_fixture(it, "EFL")
    ft = p(_fx(1, "FT", (2, 1), (2, 1), True))
    aet = p(_fx(2, "AET", (2, 1), (1, 1), True))       # won in ET, level at 90'
    pen = p(_fx(3, "PEN", (1, 1), (1, 1), True))
    ns = p(_fx(4, "NS", (None, None), (None, None)))
    none = p(_fx(5, None, (None, None), None))
    assert (ft.status_raw, aet.status_raw, pen.status_raw, ns.status_raw, none.status_raw) == \
        ("FT", "AET", "PEN", "NS", None)                  # absent stays NULL, not a faked "NS"
    assert (aet.home_score_90, aet.away_score_90) == (1, 1)
    assert (ns.home_score_90, none.home_score_90) == (None, None)
    # labels UNCHANGED: scores are still `goals` (incl. ET), result still the winner flag
    assert (aet.home_score, aet.away_score, aet.full_time_result) == (2, 1, Result.HOME)
    assert all(m.status == MatchStatus.FINISHED for m in (ft, aet, pen))
    assert ns.status == MatchStatus.SCHEDULED and none.status == MatchStatus.SCHEDULED


def test_ingestion_persists_and_never_blanks_90_minute_score():
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="S90", name="x", area="x", type="CUP")
        h = Team(sport=Sport.SOCCER, name="H90", external_ids={"api_football": "h90"})
        a = Team(sport=Sport.SOCCER, name="A90", external_ids={"api_football": "a90"})
        s.add_all([comp, h, a])
        s.flush()
        svc = IngestionService.__new__(IngestionService)
        nm = NormalizedMatch(sport=Sport.SOCCER, competition_code="S90", season="2026/27",
                             utc_date=datetime(2026, 8, 26), status=MatchStatus.FINISHED,
                             home_team_source_id="h90", away_team_source_id="a90",
                             source="api_football", source_id="f90", home_score=2, away_score=1,
                             status_raw="AET", home_score_90=1, away_score_90=1)
        cache: dict = {}
        m = svc._upsert_match(s, nm, comp, SyncResult(), cache)
        assert (m.status_raw, m.home_score_90, m.away_score_90) == ("AET", 1, 1)
        nm.home_score_90 = nm.away_score_90 = None          # a later payload without it
        svc._upsert_match(s, nm, comp, SyncResult(), cache)
        assert (m.home_score_90, m.away_score_90) == (1, 1)


def _old_db(tmp_path, with_status_raw=True):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    raw = ", status_raw VARCHAR(16)" if with_status_raw else ""
    with eng.begin() as c:
        c.execute(text("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code VARCHAR)"))
        c.execute(text("CREATE TABLE teams (id INTEGER PRIMARY KEY, name VARCHAR)"))
        c.execute(text("CREATE TABLE matches (id INTEGER PRIMARY KEY, sport VARCHAR, status VARCHAR, "
                       "competition_id INTEGER, season VARCHAR, stage VARCHAR, utc_date DATETIME, "
                       f"home_team_id INTEGER, away_team_id INTEGER, home_score INTEGER, away_score INTEGER{raw})"))
        c.execute(text("INSERT INTO competitions VALUES (1,'CL'),(2,'FAC'),(3,'NHL')"))
        c.execute(text("INSERT INTO teams VALUES (1,'Home FC'),(2,'Away FC')"))
        if with_status_raw:
            c.execute(text(
                "INSERT INTO matches VALUES "
                # CL 2nd-qualifying tie: leg 1 (FT 1-0), leg 2 AET not level at 90' (0-1 -> 0-2 aet)
                "(1,'SOCCER','FINISHED',1,'2025/26','2nd Qualifying Round','2025-07-22 18:00:00',1,2,1,0,'FT'),"
                "(2,'SOCCER','FINISHED',1,'2025/26','2nd Qualifying Round','2025-07-29 18:00:00',2,1,2,0,'AET'),"
                # FA Cup single match, AET
                "(3,'SOCCER','FINISHED',2,'2025/26','3rd Round','2026-01-10 15:00:00',1,2,2,1,'AET'),"
                "(4,'NHL','FINISHED',3,'2025',NULL,'2025-10-08 23:00:00',1,2,3,2,'AOT')"))
    return eng


def _set90(eng, mid, h, a):
    with eng.begin() as c:
        c.execute(text(f"UPDATE matches SET home_score_90={h}, away_score_90={a} WHERE id={mid}"))


def test_migration_adds_columns_idempotently(tmp_path, monkeypatch, capsys):
    import migrate_score_90 as mig

    eng = _old_db(tmp_path)
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "+ Adding matches.home_score_90" in out and "+ Adding matches.away_score_90" in out
    assert "AET" in out and "AOT" not in out                # soccer only
    assert "HOLD" in out                                    # nothing synced yet: vacuous
    with eng.connect() as c:
        assert c.execute(text("SELECT id, home_score FROM matches ORDER BY id")).all() == \
            [(1, 1), (2, 2), (3, 2), (4, 3)]                # data kept
    assert mig.main() == 0
    assert "already exists" in capsys.readouterr().out      # second run: no-op


def test_revised_invariants_two_legged_tie_holds(tmp_path, monkeypatch, capsys):
    """The architect's case: a two-legged 2nd leg AET is NOT level at 90' — that's fine."""
    import migrate_score_90 as mig

    eng = _old_db(tmp_path)
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    mig.main()
    capsys.readouterr()
    _set90(eng, 1, 1, 0)          # FT == stored
    _set90(eng, 2, 1, 0)          # leg 2: 1-0 at 90' (agg 1-1), 2-0 aet
    _set90(eng, 3, 1, 1)          # single match: level at 90'
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "CL     2nd Qualifying Round             two-legged        1" in out
    assert "FAC    3rd Round                        single            1" in out
    assert "(none)" in out and out.rstrip().splitlines()[-2].endswith("HOLD")


def test_revised_invariants_print_breaching_rows_verbatim(tmp_path, monkeypatch, capsys):
    import migrate_score_90 as mig

    eng = _old_db(tmp_path)
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    mig.main()
    capsys.readouterr()
    _set90(eng, 1, 0, 0)          # FT but 90' != stored
    _set90(eng, 2, 3, 0)          # 90' home 3 > stored 2: ET can't remove goals
    _set90(eng, 3, 2, 1)          # single-match AET not level at 90'
    mig.main()
    out = capsys.readouterr().out
    assert ("[AET 90'>stored] #2 CL 2025/26 | 2nd Qualifying Round | 2025-07-29 18:00:00 | "
            "Away FC v Home FC | AET stored 2-0 | fulltime 3-0 | class two-legged | leg1 Y") in out
    assert "[AET single not level] #3 FAC" in out and "leg1 n" in out
    assert "[FT 90'!=score] #1 CL" in out
    assert "BREACHED — AET 90'>stored: 1; AET single not level: 1; FT 90'!=score: 1" in out


def test_classify_stage():
    c = mig_classify()
    assert c("CL", "Final") == "single" and c("CL", "Preliminary Round") == "single"
    assert c("CL", "Round of 16") == "two-legged" and c("UEL", "Play-offs") == "two-legged"
    assert c("EFL", "Semi-finals") == "two-legged" and c("EFL", "2nd Round") == "single"
    assert c("FAC", "Semi-finals") == "single" and c("WC", "Round of 16") == "single"
    assert c("UNL", "Semi-finals") == "single" and c("UNL", "Quarter-finals") == "two-legged"
    assert c("ELC", "Play-offs") == "unclassified" and c("CL", None) == "unclassified"


def mig_classify():
    import migrate_score_90 as mig
    return mig.classify_stage


def test_migration_requires_status_raw(tmp_path, monkeypatch, capsys):
    import migrate_score_90 as mig

    monkeypatch.setattr(mig, "get_engine", lambda: _old_db(tmp_path, with_status_raw=False))
    assert mig.main() == 1 and "migrate_status_raw.py first" in capsys.readouterr().out
