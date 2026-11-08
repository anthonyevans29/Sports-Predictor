"""ARCHITECT 2026-11-08 09:55 ET, addendum 294 item D (#883), verbatim in part: "(i) `export-results` gains `--days N`,
default 1, which is today's behaviour. For each slate day in the N days ending yesterday, it writes that day's
`<sport>_<comp>_results_<day>.json` when the day has at least one graded game. Yesterday's file is always written, as
today. (ii) soccer-morning-after passes `--days 7`. (iii) Code verifies (law 1, in the PR body) that `evaluate --sport
soccer` grades every FINISHED ungraded PL game whatever its date. [...] (iv) The first run after the merge back-writes
the missing days inside the window, 11-06 among them."

Pinned here, each on its own throwaway SQLite file (SessionLocal rebound under tmp_path; data/ is never touched):
- --days 1 is today's command: the file is byte-identical to the bare command's and to --date's for the same day, it is
  the writer's own payload for yesterday's 08:00-08:00 UTC window, and the console is the golden captured from
  origin/main 030d1bb8 on the same rows (GOLDEN_OUTPUT; the run is in the PR body).
- --days 7 writes each earlier slate day that holds a graded game and yesterday's always; a day with no graded game
  other than yesterday writes nothing; a day before the window is never read; yesterday is written last; a rewritten
  older day keeps its name; the console's window line names every day.
- --days above 1 with --date or --out refuses, exit 2, nothing written; --days 0 is refused by click; an unknown
  competition code still refuses, exit 2, nothing written.
- soccer-morning-after's step carries --days 7, and no other chain's export-results changes.
- The Friday case (iv): a Friday game (Everton v Coventry, 2026-11-06) with no Saturday run is graded by Sunday's
  evaluate and exported by Sunday's export-results --days 7; under --days 1 (the chain before this PR) its file is
  never written (the control).
- (iii): evaluate --sport soccer grades a FINISHED ungraded PL game whatever its date (one four weeks old included).
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.schema import Sport

PINNED_AT = datetime(2026, 11, 8, 9, 50, 0)       # the Sunday run's clock, fixed so the files compare byte for byte
PINNED_SHA = "0" * 40
SUNDAY = date(2026, 11, 8)                         # sp-soccer-morning-after: Sun,Mon,Tue 09:50 UTC
YESTERDAY = SUNDAY - timedelta(days=1)             # Saturday 2026-11-07


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    from src.db import database
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                     expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    eng.dispose()


@pytest.fixture
def pinned(monkeypatch):
    """The writer's two clocks of the run (exported_at, git_sha) and export-results' yesterday, fixed."""
    import cli
    from src.walters import export
    monkeypatch.setattr(export, "utc_now_naive", lambda: PINNED_AT)
    monkeypatch.setattr(export, "_git_sha", lambda: PINNED_SHA)
    monkeypatch.setattr(cli, "_results_yesterday", lambda: YESTERDAY)


def _pl(s):
    from src.db.schema import Competition
    c = Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England", type="LEAGUE")
    s.add(c)
    s.flush()
    return c


def seed_game(s, c, key, ko, hs, aw, probs=(0.45, 0.28, 0.27), *, graded=True, priced=True):
    """One FINISHED PL game with a v22-shaped prediction (home, draw, away) and, when priced, two complete three-way
    books one hour before the start. graded: its prediction_outcomes row is written here, as evaluate writes it;
    otherwise the game waits for evaluate."""
    import math

    from src.db.schema import Match, MatchStatus, Odds, Prediction, PredictionOutcome, Result, Team
    home, away = key if isinstance(key, tuple) else (f"{key} H", f"{key} A")
    h, a = Team(sport=Sport.SOCCER, name=home), Team(sport=Sport.SOCCER, name=away)
    s.add_all([h, a])
    s.flush()
    res = Result.HOME if hs > aw else Result.AWAY if aw > hs else Result.DRAW
    m = Match(sport=Sport.SOCCER, competition_id=c.id, season="2026/27", matchday=11, utc_date=ko,
              status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=aw,
              full_time_result=res)
    s.add(m)
    s.flush()
    if priced:
        for bk in ("bk1", "bk2"):
            for sel, px in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)):
                s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                           captured_at=ko - timedelta(hours=1)))
    ph, pd, pa = probs
    pr = Prediction(match_id=m.id, model_version="soccer_elo_poisson_v22", home_win_prob=ph, draw_prob=pd,
                    away_win_prob=pa)
    s.add(pr)
    s.flush()
    if graded:
        p = {"H": ph, "D": pd, "A": pa}
        top = max(p, key=p.get)
        s.add(PredictionOutcome(prediction_id=pr.id, actual_result=res, actual_home_score=hs, actual_away_score=aw,
                                top_pick_hit=top == res.value, log_loss=-math.log(p[res.value])))
    return m.id


def seed_golden(s):
    """The golden's rows (also run against origin/main for GOLDEN_OUTPUT): three graded games on slate day 11-07
    (one at 06:30 UTC on 11-08, unpriced, still 11-07's slate) and one graded on 11-06."""
    c = _pl(s)
    seed_game(s, c, "G1", datetime(2026, 11, 7, 15, 0), 2, 1)
    seed_game(s, c, "G2", datetime(2026, 11, 7, 17, 30), 1, 1, (0.30, 0.36, 0.34))
    seed_game(s, c, "G3", datetime(2026, 11, 8, 6, 30), 0, 2, priced=False)
    seed_game(s, c, "G4", datetime(2026, 11, 6, 20, 0), 3, 0)
    return c


def _run(*args):
    import cli
    return CliRunner().invoke(cli.cli, ["export-results", "--sport", "soccer", "--competition", "PL", *args])


def _files(root: Path) -> dict[str, bytes]:
    ex = root / "exports"
    return {p.name: p.read_bytes() for p in sorted(ex.glob("*.json"))} if ex.is_dir() else {}


def _writer(day: date) -> bytes:
    """The writer's own payload for the slate day (08:00 UTC to 08:00 UTC), exactly as export-results writes it."""
    from src.walters.export import export_results
    start = datetime(day.year, day.month, day.day, 8, 0)
    return export_results(sport=Sport.SOCCER, start_date=start, end_date=start + timedelta(days=1),
                          competition_code="PL", output_format="json").encode()


# THE GOLDEN: the console of origin/main 030d1bb8's `export-results --sport soccer --competition PL --date 2026-11-07`
# on seed_golden's rows with the two clocks pinned (captured on venv310 and venv312; the PR body has the run and the
# file's sha256, identical on main and on this branch). The file itself is compared with the writer's own payload.
GOLDEN_OUTPUT = (
    "✓ Wrote 3 results to exports/soccer_PL_results_2026-11-07.json\n"
    "  top-pick 2/3 · totals-direction 0/0 (3 no line) (record is variance, not \n"
    "signal — for the consumer to grade against)\n"
    "  vs close: 2 games · model 0.9101 · close 1.0141 · close − model +0.1041 (95% -0.0496 to +0.2578, 10,000 "
    "resamples, seed 20261013) · model beat the close 1/2\n"
    "  void: re-dated 0 · placeholder kickoff 0 (kept in the file, out of every tally above)\n"
    "  graded export: closing 0 · slate 0 · none 3\n"
)


# ---- (i) --days 1 is today's behaviour, byte for byte -----------------------------------------------------------

def test_days_1_is_byte_identical_to_the_bare_command_and_to_the_writer(iso_db, pinned):
    from src.db.database import session_scope
    with session_scope() as s:
        seed_golden(s)
    outs, files = [], []
    for args in ([], ["--days", "1"], ["--date", "2026-11-07"], ["--date", "2026-11-07", "--days", "1"]):
        for p in (iso_db / "exports").glob("*.json") if (iso_db / "exports").is_dir() else []:
            p.unlink()
        r = _run(*args)
        assert r.exit_code == 0, r.output
        outs.append(r.output)
        files.append(_files(iso_db))
    assert all(f == files[0] for f in files) and all(o == outs[0] for o in outs)
    assert list(files[0]) == ["soccer_PL_results_2026-11-07.json"]               # one file, yesterday's, as before
    body = files[0]["soccer_PL_results_2026-11-07.json"]
    assert body == _writer(YESTERDAY)                                            # the writer's payload, unchanged
    doc = json.loads(body)
    assert doc["count"] == 3 and doc["start_date"] == "2026-11-07T08:00:00" and doc["end_date"] == "2026-11-08T08:00:00"
    # the golden, origin/main's console on these rows (no window line at --days 1)
    assert outs[0] == GOLDEN_OUTPUT
    assert "results window:" not in outs[0]


def test_a_zero_game_yesterday_is_written_at_days_1_as_before(iso_db, pinned):
    from src.db.database import session_scope
    with session_scope() as s:
        _pl(s)
    r = _run()
    assert r.exit_code == 0, r.output
    assert list(_files(iso_db)) == ["soccer_PL_results_2026-11-07.json"]
    assert json.loads(_files(iso_db)["soccer_PL_results_2026-11-07.json"])["count"] == 0
    assert "No graded games for 2026-11-07" in r.output


# ---- (i) --days 7 -------------------------------------------------------------------------------------------------

def test_days_7_writes_the_days_with_graded_games_and_yesterday(iso_db, pinned):
    from src.db.database import session_scope
    with session_scope() as s:
        c = seed_golden(s)
        seed_game(s, c, "M2", datetime(2026, 11, 2, 20, 0), 1, 0)               # Monday 11-02: in the window
        seed_game(s, c, "B1", datetime(2026, 11, 1, 7, 30), 1, 2)               # 11-01 07:30 = slate day 10-31: out
        seed_game(s, c, "O1", datetime(2026, 10, 30, 20, 0), 0, 0)              # Friday 10-30: before the window
    r = _run("--days", "7")
    assert r.exit_code == 0, r.output
    got = _files(iso_db)
    assert list(got) == ["soccer_PL_results_2026-11-02.json", "soccer_PL_results_2026-11-06.json",
                         "soccer_PL_results_2026-11-07.json"]
    for name, body in got.items():                                               # each the writer's day, unchanged
        assert body == _writer(date.fromisoformat(name[-15:-5]))
    assert [json.loads(b)["count"] for b in got.values()] == [1, 1, 3]
    line = [ln for ln in r.output.splitlines() if ln.startswith("results window:")]
    assert line == ["results window: --days 7, slate days 2026-11-01 .. 2026-11-07 (08:00 UTC each) · written 3 "
                    "(2026-11-02, 2026-11-06, 2026-11-07), yesterday's always · no graded game, not written 4 "
                    "(2026-11-01, 2026-11-03, 2026-11-04, 2026-11-05) · failed 0"]
    ex = iso_db / "exports"                                                      # written oldest first, yesterday last
    ns = [(ex / n).stat().st_mtime_ns for n in got]
    assert ns == sorted(ns)


def test_a_day_with_no_graded_game_other_than_yesterday_writes_nothing(iso_db, pinned):
    from src.db.database import session_scope
    with session_scope() as s:
        c = _pl(s)
        seed_game(s, c, "U1", datetime(2026, 11, 4, 19, 45), 2, 2, graded=False)   # finished, not yet graded
    r = _run("--days", "7")
    assert r.exit_code == 0, r.output
    got = _files(iso_db)
    assert list(got) == ["soccer_PL_results_2026-11-07.json"]                   # yesterday's, always; 11-04 not
    assert json.loads(got["soccer_PL_results_2026-11-07.json"])["count"] == 0
    assert "No graded games for 2026-11-07" in r.output and "2026-11-04" in r.output.split("not written")[1]


def test_a_rewritten_older_day_keeps_its_name(iso_db, pinned):
    from src.db.database import session_scope
    with session_scope() as s:
        c = _pl(s)
        seed_game(s, c, "R1", datetime(2026, 11, 3, 19, 30), 1, 0)
    assert _run("--days", "7").exit_code == 0
    first = _files(iso_db)
    with session_scope() as s:                                                   # a second game graded on 11-03
        from src.db.schema import Competition
        from sqlalchemy import select
        seed_game(s, s.execute(select(Competition)).scalar_one(), "R2", datetime(2026, 11, 3, 20, 0), 0, 1)
    assert _run("--days", "7").exit_code == 0
    second = _files(iso_db)
    assert list(first) == list(second) == ["soccer_PL_results_2026-11-03.json", "soccer_PL_results_2026-11-07.json"]
    assert json.loads(first["soccer_PL_results_2026-11-03.json"])["count"] == 1
    assert json.loads(second["soccer_PL_results_2026-11-03.json"])["count"] == 2  # rewritten in place, same name


# ---- refusals -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [["--date", "2026-11-07"], ["--out", "x.json"]])
def test_days_above_1_with_date_or_out_refuses_and_writes_nothing(iso_db, pinned, extra):
    from src.db.database import session_scope
    with session_scope() as s:
        seed_golden(s)
    r = _run("--days", "7", *extra)
    assert r.exit_code == 2 and r.output.startswith("REFUSED: --days 7 ")
    assert _files(iso_db) == {} and not (iso_db / "x.json").exists()


def test_days_must_be_at_least_1(iso_db, pinned):
    r = _run("--days", "0")
    assert r.exit_code == 2 and _files(iso_db) == {}


def test_an_unknown_competition_still_refuses_under_days_7(iso_db, pinned):
    import cli
    from src.db.database import session_scope
    with session_scope() as s:
        seed_golden(s)
    r = CliRunner().invoke(cli.cli, ["export-results", "--sport", "soccer", "--competition", "NOPE", "--days", "7"])
    assert r.exit_code == 2 and "REFUSED: unknown competition code 'NOPE'" in r.output
    assert _files(iso_db) == {}


# ---- (ii) the chain -----------------------------------------------------------------------------------------------

def test_soccer_morning_after_carries_days_7_and_no_other_chain_changes():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy" / "hosting"))
    import chains

    import cli
    steps = chains.CHAINS["soccer-morning-after"]["steps"]
    assert chains.PL_RESULTS_STEP == ["export-results", "--sport", "soccer", "--competition", "PL", "--days", "7"]
    assert [s for s in steps if s[0] == "export-results"] == [chains.PL_RESULTS_STEP]
    i = steps.index(chains.PL_RESULTS_STEP)
    assert steps[i - 1] == ["evaluate", "--sport", "soccer"]                    # after the grade, as before
    assert steps[i + 1] == chains.SHADOW_EXPORT_STEP and steps[-1] == chains.HOST_TALLY_STEP
    others = {n: [s for s in ch.get("steps") or [] if s and s[0] == "export-results"]
              for n, ch in chains.CHAINS.items() if n != "soccer-morning-after"}
    assert {n: v for n, v in others.items() if v} == {
        "mlb-morning": [["export-results", "--sport", "mlb", "--competition", "MLB"]],
        "soccer-refresh": [["export-results", "--sport", "soccer", "--competition", "PL"]]}
    # law 1: --days is a real click option of export-results (the hosting pack's option check reads the same set)
    opts = {o for p in cli.cli.commands["export-results"].params for o in (*p.opts, *p.secondary_opts)}
    assert "--days" in opts
    days = next(p for p in cli.cli.commands["export-results"].params if p.name == "days")
    assert days.default == 1


# ---- (iv) the Friday game; (iii) evaluate grades whatever the date -----------------------------------------------

def test_a_friday_game_is_graded_and_exported_by_the_next_sundays_run(iso_db, pinned):
    """Everton v Coventry, Friday 2026-11-06 20:00 UTC: no Saturday run (the timer is Sun,Mon,Tue). Sunday 11-08's
    chain runs evaluate, then export-results --days 7: the Friday file is written with the game graded. The control,
    the chain's step before this PR (--days 1), writes yesterday's file only and the Friday file never exists."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import PredictionOutcome
    from sqlalchemy import func, select
    with session_scope() as s:
        c = _pl(s)
        fri = seed_game(s, c, ("Everton", "Coventry City"), datetime(2026, 11, 6, 20, 0), 2, 0, graded=False)
        seed_game(s, c, "S1", datetime(2026, 11, 7, 15, 0), 1, 2, graded=False)
        old = seed_game(s, c, "W1", datetime(2026, 10, 9, 19, 0), 0, 0, graded=False)  # four weeks old, ungraded
    ev = CliRunner().invoke(cli.cli, ["evaluate", "--sport", "soccer"])             # Sunday's evaluate
    assert ev.exit_code == 0, ev.output
    with session_scope() as s:                                                      # (iii): every one, whatever the date
        assert s.execute(select(func.count()).select_from(PredictionOutcome)).scalar_one() == 3
    # the control: the chain as it was (--days 1) leaves the Friday file unwritten
    assert _run().exit_code == 0
    assert list(_files(iso_db)) == ["soccer_PL_results_2026-11-07.json"]
    # the chain as it is now: --days 7 back-writes the Friday day
    r = _run("--days", "7")
    assert r.exit_code == 0, r.output
    got = _files(iso_db)
    assert list(got) == ["soccer_PL_results_2026-11-06.json", "soccer_PL_results_2026-11-07.json"]
    rows = json.loads(got["soccer_PL_results_2026-11-06.json"])["results"]
    assert [(x["match_id"], x["home_team"], x["away_team"]) for x in rows] == [(fri, "Everton", "Coventry City")]
    assert rows[0]["graded"]["top_pick_hit"] is True and rows[0]["actual"]["result"] == "H"
    # 10-09 is outside the seven days: graded, never back-written by this run (the one-off command's, not the chain's)
    assert not any("2026-10-0" in n for n in got) and old
