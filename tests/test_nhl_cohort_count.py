"""The NHL cohort count (DEV 4, Lane D; addendum 523 item 2; Refs #105): read-only counts on a .backup copy. Every
test builds its own throwaway file database under tmp_path with synthetic rows; nothing under data/ is created or
opened, and no row, model, rating or figure is printed."""
import hashlib
import importlib.util
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nhl_cohort_count.py"
spec = importlib.util.spec_from_file_location("nhl_cohort_count", SCRIPT)
ncc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ncc
spec.loader.exec_module(ncc)

SECRET_TEAM = "Zqxsecret Club"      # a team's name: it must never be printed


def _copy(tmp_path, six=6, intl_time=datetime(2027, 2, 5, 21, 0), folder="copy"):
    """A stand-in for a .backup copy of the laptop's database:
    - NHL 2026: two preseason games (one by stage, one by date), 10 regular games in October (6 FINISHED with
      scores, 1 FINISHED without, 3 SCHEDULED in the future), 4 SCHEDULED in November, 1 POSTPONED;
    - the six internationals among four clubs at 2027-02-05 21:00Z (or `six` of them);
    - an NHL 2025 game and a 4 Nations game (another competition code), both outside the cohort;
    - goalie rows: types 2, 3 and NULL linked to played games, one played game with none, and a type-2 game with no
      match id; shot events in 2026-27 (October, November) and 2023-24."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.db.schema import (Base, Competition, Match, MatchStatus, NHLGoalieAppearance, NHLShotEvent, Sport,
                               Team)
    path = tmp_path / folder / "sports.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine("sqlite:///{}".format(path), future=True)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        nhl = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
        fourn = Competition(sport=Sport.NHL, code="4NAT", name="4 Nations", area="World", type="CUP")
        s.add_all([nhl, fourn])
        s.flush()
        clubs = [Team(sport=Sport.NHL, name=SECRET_TEAM if i == 0 else "Club {}".format(i)) for i in range(6)]
        intl = [Team(sport=Sport.NHL, name="Nation {}".format(i)) for i in range(4)]
        s.add_all(clubs + intl)
        s.flush()

        def m(when, status, hs=None, as_=None, stage="Regular Season", season="2026", comp=nhl, h=0, a=1,
              raw=None, teams=clubs):
            row = Match(sport=Sport.NHL, competition_id=comp.id, season=season, utc_date=when, status=status,
                        status_raw=raw, home_team_id=teams[h].id, away_team_id=teams[a].id, home_score=hs,
                        away_score=as_, stage=stage)
            s.add(row)
            s.flush()
            return row

        F, S = MatchStatus.FINISHED, MatchStatus.SCHEDULED
        m(datetime(2026, 9, 30, 23), F, 3, 2, stage="Pre Season", raw="FT")          # preseason by stage
        m(datetime(2026, 9, 25, 23), F, 1, 0, stage=None, raw="FT")                  # preseason by date
        played = []
        for i in range(6):
            played.append(m(datetime(2026, 10, 8 + i, 23), F, 4, 2, raw="AOT" if i == 0 else "FT",
                            h=i % 6, a=(i + 1) % 6))
        m(datetime(2026, 10, 20, 23), F, None, None, raw="FT")                       # finished without both scores
        for i in range(3):
            m(datetime(2026, 10, 28 + i, 23), S, raw="NS")
        for i in range(4):
            m(datetime(2026, 11, 26 + i, 1), S, raw="NS", stage=None)                # ET: Nov 25 .. Nov 28
        m(datetime(2026, 11, 3, 23), MatchStatus.POSTPONED, raw="PST")
        pairs = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)][:six]
        for h, a in pairs:
            m(intl_time, S, raw="NS", stage=None, h=h, a=a, teams=intl)
        m(datetime(2025, 10, 9, 23), F, 2, 1, season="2025", raw="FT")               # another season
        m(datetime(2026, 2, 12, 20), F, 3, 2, comp=fourn, raw="FT")                  # another competition

        for gid, mt, gt in ((1, played[0], 2), (2, played[1], 2), (3, played[2], 2), (4, played[3], 3),
                            (5, played[4], None)):
            for k, side in enumerate(("home", "away")):
                s.add(NHLGoalieAppearance(nhl_game_id=2026020000 + gid, match_id=mt.id, game_start=mt.utc_date,
                                          game_type=gt, side=side, goalie_id=8000 + 10 * gid + k, is_starter=True))
        s.add(NHLGoalieAppearance(nhl_game_id=2026029999, match_id=None, game_start=datetime(2026, 10, 15, 23),
                                  game_type=2, side="home", goalie_id=8999, is_starter=True))

        ev = 0
        for gid, start, gt, mid in ((2026020001, played[0].utc_date, 2, played[0].id),
                                    (2026020002, played[1].utc_date, 2, None),
                                    (2026020077, datetime(2026, 11, 2, 0), 2, None),       # ET: Nov 1
                                    (2023020001, datetime(2023, 10, 11, 23), 2, None),
                                    (2023020002, datetime(2023, 10, 12, 23), 2, None),
                                    (2023030001, datetime(2024, 4, 25, 23), 3, None)):
            for _ in range(3):
                ev += 1
                s.add(NHLShotEvent(nhl_game_id=gid, event_id=ev, match_id=mid, game_start=start, game_type=gt,
                                   event_type="shot-on-goal"))
        s.commit()
    eng.dispose()
    return path


def run(argv):
    lines = []
    code = ncc.main(argv, out=lines.append)
    return code, "\n".join(lines)


def line(text, prefix):
    for ln in text.splitlines():
        if ln.strip().startswith(prefix):
            return ln
    raise AssertionError("no line starting " + prefix)


# ---- the counts -----------------------------------------------------------------------------------------------------


def test_the_counts_q0_to_q6(tmp_path):
    db = _copy(tmp_path)
    code, text = run(["--db", str(db), "--after", "2026-10-27", "--after", "2026-11-26"])
    assert code == 0, text
    assert "cohort = matches of competition code 'NHL', sport NHL, season '2026' (23 games stored)" in text
    # Q0: stage by status, as stored
    assert "  'Pre Season': FINISHED 1" in text
    assert "  'Regular Season': FINISHED 7 · POSTPONED 1 · SCHEDULED 3" in text
    assert "  (none): FINISHED 1 · SCHEDULED 10" in text
    assert "preseason by the shadow's rule: date 1 · stage 1" in text
    # Q1: the six, found and set apart
    assert "FOUND as 445 item 3(b) finds them: 4 clubs with no game before 2027-02-01, 6 games between them" in text
    assert "status SCHEDULED 6; status_raw 'NS' 6" in text
    # Q2: month by status, league games only (no preseason, no six)
    assert line(text, "2026-10:").startswith("  2026-10: FINISHED 7 · SCHEDULED 3 · played 6 · to come 3 · "
                                             "FINISHED without both scores 1")
    assert "FINISHED: 'AOT' 1 · 'FT' 6" in line(text, "2026-10:")
    assert line(text, "2026-11:").startswith("  2026-11: POSTPONED 1 · SCHEDULED 4 · played 0 · to come 4")
    assert "2027-02" not in text.split("Q2")[1].split("Q3")[0]
    assert "total: FINISHED 7 · POSTPONED 1 · SCHEDULED 7 · played 6 · to come 7" in text
    # Q3: played against the goalie table
    q3 = line(text, "Q3 ")
    assert "played 6" in q3 and "game type 2 3" in q3 and "game type 3 1" in q3
    assert "game type not stated 1" in q3 and "no goalie row linked 1" in q3
    assert ("the goalie table's 2026-27 games of type 2: 4 · linked to a played cohort game 3 · not: no match_id 1 · "
            "linked to more than one match 0 · played games linked to more than one goalie-table game 0") in text
    # Q4: the 2026-27 shot events by America/New_York month
    assert "2026-10: events 6 · games 2 (type 2 2) · games with no match_id 1" in text
    assert "2026-11: events 3 · games 1 (type 2 1) · games with no match_id 1" in text
    # Q5: to come after each date, by stored stage, unverified
    assert "after 2026-10-27: 7 to come · by stage (none) 4 · 'Regular Season' 3" in text
    assert "after 2026-11-26: 2 to come · by stage (none) 2" in text
    assert "a game to come is unverified until played" in text
    # Q6: the 2023-24 shot games
    assert "Q6 THE 2023-24 SHOT GAMES: games 3 (type 2 2 · type 3 1) · events 9 · games with no match_id 3" in text
    assert text.splitlines()[-1] == "END: exit 0"


def test_the_six_not_found_are_counted_for_nothing_and_set_apart_nowhere(tmp_path):
    db = _copy(tmp_path, six=5)
    code, text = run(["--db", str(db)])
    assert code == 0
    assert "NOT FOUND as 445 item 3(b) finds them: 5 games between them (445 item 3(b): 6)" in text
    assert "Nothing is counted for them and nothing is set apart" in text
    assert line(text, "2027-02:").startswith("  2027-02: SCHEDULED 5")


def test_the_six_at_another_time_are_not_found(tmp_path):
    db = _copy(tmp_path, intl_time=datetime(2027, 2, 6, 0, 0))
    code, text = run(["--db", str(db)])
    assert code == 0 and "6 of them not at 2027-02-05T21:00:00Z" in text and "NOT FOUND" in text


def test_no_after_date_says_so(tmp_path):
    code, text = run(["--db", str(_copy(tmp_path))])
    assert code == 0 and "no --after date given" in text


def test_nothing_of_a_row_is_printed(tmp_path):
    db = _copy(tmp_path)
    code, text = run(["--db", str(db), "--after", "2026-10-01"])
    assert code == 0
    assert SECRET_TEAM not in text and "Club 1" not in text and "Nation" not in text
    assert "2026020001" not in text and "8010" not in text      # no NHL game id, no goalie id


# ---- the copy -------------------------------------------------------------------------------------------------------


def test_the_copy_is_unchanged_and_nothing_is_written(tmp_path):
    db = _copy(tmp_path)
    before = sorted(p.name for p in db.parent.iterdir())
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    code, text = run(["--db", str(db)])
    assert code == 0
    assert "sha256 {} (the same after the read; no sidecar)".format(sha) in text
    assert hashlib.sha256(db.read_bytes()).hexdigest() == sha
    assert sorted(p.name for p in db.parent.iterdir()) == before


@pytest.mark.parametrize("name", ["data", "DATA", "Data"])
def test_a_copy_under_a_directory_named_data_is_refused(tmp_path, name):
    db = _copy(tmp_path, folder=name)
    code, text = run(["--db", str(db)])
    assert code == 2 and "REFUSED" in text and "directory named data" in text and "Q0" not in text


def test_the_checkout_data_dir_is_refused_and_never_created(tmp_path):
    target = ROOT / "data" / "no_such_copy_ncc.db"
    existed = (ROOT / "data").exists()
    code, text = run(["--db", str(target)])
    assert code == 2 and "REFUSED" in text
    assert not target.exists() and (ROOT / "data").exists() == existed


@pytest.mark.parametrize("sfx", ["-wal", "-shm", "-journal"])
def test_a_sidecar_refuses(tmp_path, sfx):
    db = _copy(tmp_path)
    (db.parent / (db.name + sfx)).write_bytes(b"")
    code, text = run(["--db", str(db)])
    assert code == 2 and "sidecar" in text and "Q0" not in text


def test_a_missing_table_refuses(tmp_path):
    db = _copy(tmp_path)
    con = sqlite3.connect(str(db))
    con.execute("DROP TABLE nhl_shot_events")
    con.commit()
    con.close()
    for sfx in ("-wal", "-shm", "-journal"):
        side = db.parent / (db.name + sfx)
        if side.exists():
            side.unlink()
    code, text = run(["--db", str(db)])
    assert code == 2 and "nhl_shot_events" in text


def test_a_missing_copy_refuses_and_is_never_created(tmp_path):
    target = tmp_path / "nope" / "sports.db"
    code, text = run(["--db", str(target)])
    assert code == 2 and "REFUSED" in text and not target.exists()


def test_a_copy_that_changes_during_the_read_refuses(tmp_path, monkeypatch):
    db = _copy(tmp_path)
    from src.walters import intl_shadow as us
    calls = []
    real = us.copy_sha256

    def sha(p):
        calls.append(p)
        return real(p) if len(calls) == 1 else "0" * 64
    monkeypatch.setattr(us, "copy_sha256", sha)
    code, text = run(["--db", str(db)])
    assert code == 2 and "changed during the read" in text and "Q0" not in text


@pytest.mark.parametrize("argv", [[], ["--db", "x.db", "--after", "2026-13-40"], ["--db", "x.db", "--after", "soon"],
                                  ["--db", "x.db", "--after", "2026-W01-1"], ["--db", "x.db", "--after", "20261127"]])
def test_bad_options_exit_2(argv):
    with pytest.raises(SystemExit) as e:
        ncc.main(argv, out=lambda s: None)
    assert e.value.code == 2


# ---- the names, pinned to their sources (law 1) ---------------------------------------------------------------------


def test_the_names_are_the_codes_own():
    from src.adapters import api_hockey
    from src.ingestion import nhl_goalies
    from src.walters import nhl_shadow
    assert nhl_shadow.LIVE_SEASON_STARTS["2026"] == date(2026, 9, 29)
    assert nhl_goalies.REGULAR == ncc.REGULAR_TYPE
    assert nhl_goalies.season_label(datetime(2026, 7, 1)) == ncc.SHOT_SEASON
    assert nhl_goalies.season_label(datetime(2024, 6, 30, 23)) == ncc.HISTORY_SEASON
    src = Path(api_hockey.__file__).read_text(encoding="utf-8")
    assert 'code="NHL"' in src and "2026 = the 26-27 season" in src


def test_america_new_york_dates():
    assert ncc.et_date(datetime(2026, 11, 26, 1)) == date(2026, 11, 25)       # 20:00 EST the evening before
    assert ncc.et_month(datetime(2026, 11, 1, 3)) == "2026-10"                 # 23:00 EDT on Oct 31
    assert ncc.et_date(datetime(2026, 7, 1, 12)) == date(2026, 7, 1)


def test_python_310_floor_no_fstrings_at_all():
    import io
    import tokenize
    src = SCRIPT.read_text(encoding="utf-8")
    compile(src, str(SCRIPT), "exec")
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        name = tokenize.tok_name[tok.type]
        assert name != "FSTRING_START", tok
        if name == "STRING":
            prefix = tok.string[: len(tok.string) - len(tok.string.lstrip("rRbBuUfF"))]
            assert "f" not in prefix.lower(), tok


# ---- the pre-PR review's findings, pinned ---------------------------------------------------------------------------


def _sql(db, *stmts):
    con = sqlite3.connect(str(db))
    for st in stmts:
        con.execute(st)
    con.commit()
    con.close()
    for sfx in ("-wal", "-shm", "-journal"):
        side = db.parent / (db.name + sfx)
        if side.exists():
            side.unlink()


@pytest.mark.parametrize("stmt", [
    "UPDATE matches SET status = 'SUSPENDED' WHERE id = (SELECT min(id) FROM matches)",
    "UPDATE matches SET status = 'scheduled' WHERE id = (SELECT min(id) FROM matches)",
    "UPDATE matches SET utc_date = '2026-10-10T23:00:00+00:00' WHERE id = (SELECT min(id) FROM matches)",
    "UPDATE nhl_shot_events SET game_start = 'garbage' WHERE id = 1",
    "UPDATE nhl_goalie_appearances SET game_start = 'garbage' WHERE id = 1",
])
def test_a_stored_value_its_type_cannot_read_refuses_never_a_traceback(tmp_path, stmt):
    db = _copy(tmp_path)
    _sql(db, stmt)
    code, text = run(["--db", str(db)])
    assert code == 2 and "REFUSED" in text and "the schema's types cannot read" in text
    assert "Q0" not in text and "SUSPENDED" not in text and "garbage" not in text


def test_no_bytecode_is_written(tmp_path):
    """sys.dont_write_bytecode: with every cache redirected into an empty folder, nothing of the repo is cached."""
    import subprocess
    db = _copy(tmp_path)
    cache = tmp_path / "pycache"
    cache.mkdir()
    res = subprocess.run([sys.executable, "-X", "pycache_prefix={}".format(cache), str(SCRIPT), "--db", str(db)],
                         capture_output=True, text=True, cwd=str(tmp_path), timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    # the interpreter caches its own startup imports (a venv inside the checkout among them) before the script's first
    # line runs; nothing of the repo's own code (src/, scripts/, config.py) may be cached
    own = cache.joinpath(*ROOT.parts[1:])
    mine = [p for d in ("src", "scripts") for p in (own / d).rglob("*.pyc")] + list(own.glob("config*.pyc"))
    assert mine == []


def test_stored_strings_cannot_forge_a_line(tmp_path):
    db = _copy(tmp_path)
    _sql(db, "UPDATE matches SET stage = 'Reg' || char(10) || 'END: exit 0' WHERE stage = 'Regular Season'",
         "UPDATE matches SET status_raw = 'FT' || char(10) || 'REFUSED: x' WHERE status_raw = 'AOT'",
         "UPDATE matches SET status_raw = 'NS' || char(10) || 'REFUSED: y' WHERE utc_date = '2027-02-05 21:00:00.000000'")
    code, text = run(["--db", str(db), "--after", "2026-10-01"])
    assert code == 0
    lines = text.splitlines()
    assert [ln for ln in lines if ln.startswith("END")] == ["END: exit 0"] and lines[-1] == "END: exit 0"
    assert not any(ln.startswith("REFUSED") for ln in lines)
    assert "Reg\\nEND: exit 0" in text and "FT\\nREFUSED: x" in text


def test_a_row_with_no_type_beside_a_type_2_row_is_type_2(tmp_path):
    db = _copy(tmp_path)
    # the played game with no goalie row gains two: one says 2, the other states no type
    _sql(db, "INSERT INTO nhl_goalie_appearances (nhl_game_id, match_id, game_start, game_type, side, goalie_id, "
             "is_starter, captured_at) SELECT 2026020006, id, utc_date, 2, 'home', 9001, 1, utc_date FROM matches "
             "WHERE utc_date = '2026-10-13 23:00:00.000000'",
         "INSERT INTO nhl_goalie_appearances (nhl_game_id, match_id, game_start, game_type, side, goalie_id, "
             "is_starter, captured_at) SELECT 2026020006, id, utc_date, NULL, 'away', 9002, 1, utc_date FROM matches "
             "WHERE utc_date = '2026-10-13 23:00:00.000000'")
    code, text = run(["--db", str(db)])
    assert code == 0
    q3 = line(text, "Q3 ")
    assert "game type 2 4" in q3 and "disagree" not in q3 and "no goalie row linked" not in q3


def test_links_that_are_not_one_to_one_are_counted(tmp_path):
    db = _copy(tmp_path)
    _sql(db, "INSERT INTO nhl_goalie_appearances (nhl_game_id, match_id, game_start, game_type, side, goalie_id, "
             "is_starter, captured_at) SELECT 2026020555, match_id, game_start, 2, 'home', 9100, 1, game_start "
             "FROM nhl_goalie_appearances WHERE nhl_game_id = 2026020003 AND side = 'home'")
    code, text = run(["--db", str(db)])
    assert code == 0
    assert "games of type 2: 5 · linked to a played cohort game 4" in text
    assert "played games linked to more than one goalie-table game 1" in text


# ---- the second pre-PR pass, pinned ---------------------------------------------------------------------------------


def test_a_quoted_stored_string_cannot_read_as_a_count(tmp_path):
    db = _copy(tmp_path)
    _sql(db, "UPDATE matches SET stage = 'X 9 · Regular Season' WHERE stage = 'Regular Season' AND status = 'SCHEDULED'")
    code, text = run(["--db", str(db), "--after", "2026-10-01"])
    assert code == 0 and "by stage (none) 4 · 'X 9 · Regular Season' 3" in text


def test_a_database_error_names_its_class_only(tmp_path):
    db = _copy(tmp_path)
    _sql(db, "UPDATE matches SET stage = CAST(X'5365637265745374616765FF' AS TEXT) WHERE stage = 'Regular Season'")
    code, text = run(["--db", str(db)])
    assert code == 2 and "SecretStage" not in text and "the copy could not be read (OperationalError)" in text


def test_a_missing_zone_refuses_before_any_read(tmp_path, monkeypatch):
    db = _copy(tmp_path)

    def no_zone():
        raise KeyError("America/New_York")
    monkeypatch.setattr(ncc, "_et", no_zone)
    code, text = run(["--db", str(db)])
    assert code == 2 and "zone cannot be loaded (KeyError)" in text and "--db" not in text.split("\n", 1)[1]


# ---- the PR's first review round, pinned ----------------------------------------------------------------------------


def test_a_stored_stage_that_reads_none_or_is_blank_is_never_merged_with_null(tmp_path):
    db = _copy(tmp_path)
    _sql(db, "UPDATE matches SET stage = '(none)' WHERE utc_date = '2026-10-28 23:00:00.000000'",
         "UPDATE matches SET stage = '  ' WHERE utc_date = '2026-10-29 23:00:00.000000'")
    code, text = run(["--db", str(db), "--after", "2026-10-27"])
    assert code == 0
    assert "  (none): FINISHED 1 · SCHEDULED 10" in text            # NULL alone
    assert "  '(none)': SCHEDULED 1" in text and "  '  ': SCHEDULED 1" in text
    assert "by stage (none) 4 · '  ' 1 · '(none)' 1 · 'Regular Season' 1" in text
