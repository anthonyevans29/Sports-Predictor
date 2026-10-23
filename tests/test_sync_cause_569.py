"""#569 RULED (ARCHITECT 2026-10-21, addendum 153 item 2), the cause lane, verbatim: "The statsapi upsert looks a gamePk
up across the sport's rows, not the competition's, and a run holds the DB lock the host's chains hold (the laptop's
syncs today take none)."

The read behind it (#569): 43 MLB twin pairs, every row in competition 22 (the only competition holding MLB rows), so
the twins came from overlapping runs, each prefetching the rows before the other wrote. Covers: a gamePk already stored
on another MLB competition's row is updated, never created again; the competition-scoped lookup is unchanged for every
other source; db_lock marks the environment while held (and restores it); sync-teams and sync-matches take the lock by
hand, wait for it while a chain holds it, and take none as a step of a run that holds it."""
import fcntl
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "deploy" / "hosting"))
import sp_common as c  # noqa: E402

from tests.test_match_series_fields import CLE, TB, _adapter, fresh_db, game, schedule  # noqa: E402,F401


def _two_mlb_comps():
    """MLB (the one the sync names) and a second MLB competition row holding gamePk 849818 (our 50546)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        mlb = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
        other = Competition(sport=Sport.MLB, code="MLBX", name="MLB (another row)", area="USA", type="LEAGUE")
        s.add_all([mlb, other])
        t = {}
        for sid, name in (TB, CLE):
            t[sid] = Team(sport=Sport.MLB, name=name, external_ids={"mlb_stats_api": str(sid)})
            s.add(t[sid])
        s.flush()
        s.add(Match(id=50546, sport=Sport.MLB, competition_id=other.id, season="2026", stage="L",
                    utc_date=datetime(2026, 10, 15, 22, 8), status=MatchStatus.SCHEDULED, home_team_id=t[CLE[0]].id,
                    away_team_id=t[TB[0]].id, external_ids={"mlb_stats_api": "849818"}))
        return mlb.id, other.id


def _rows(pk):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        return [(m.id, m.competition_id, m.status.name, m.home_score, m.away_score) for m in s.execute(
            select(Match)).scalars() if (m.external_ids or {}).get("mlb_stats_api") == pk]


def _sync(monkeypatch, payload, env_held=None):
    import cli
    a = _adapter(payload)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: a)
    if env_held is None:
        monkeypatch.delenv(c.HELD_ENV, raising=False)
    else:
        monkeypatch.setenv(c.HELD_ENV, env_held)
    return CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "MLB", "--date-from", "2026-10-15",
                                        "--date-to", "2026-10-16"])


def test_a_gamepk_stored_on_another_mlb_competitions_row_is_updated_never_created_again(fresh_db, monkeypatch,
                                                                                         tmp_path):
    """Before: the prefetch read the MLB competition's rows only, so 849818 on the other row was not found and a
    second row was created (a twin). Now the statsapi lookup reads the sport's rows: the stored row is updated."""
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    _, other = _two_mlb_comps()
    r = _sync(monkeypatch, schedule(game(849818, "2026-10-15T22:08:00Z", "F", TB, CLE, 2, 3)))
    assert r.exit_code == 0, r.output
    assert "created=0 updated=1 skipped=0" in r.output, r.output
    assert _rows("849818") == [(50546, other, "FINISHED", 3, 2)]


def test_the_lookup_stays_the_competitions_own_for_every_other_source():
    from src.ingestion.service import REKEY_SOURCES, SPORT_WIDE_SOURCES
    assert SPORT_WIDE_SOURCES == frozenset({"mlb_stats_api"}) and not (SPORT_WIDE_SOURCES & REKEY_SOURCES)


def test_db_lock_marks_the_environment_while_held_and_restores_it(monkeypatch, tmp_path):
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    with c.db_lock():
        assert os.environ[c.HELD_ENV] == f"{os.getpid()}:{tmp_path / 'db.lock'}"
        assert c.lock_held_by_caller()
    assert c.HELD_ENV not in os.environ and not c.lock_held_by_caller()
    monkeypatch.setenv(c.HELD_ENV, "outer")
    with c.db_lock():
        assert os.environ[c.HELD_ENV] == f"{os.getpid()}:{tmp_path / 'db.lock'}"
    assert os.environ[c.HELD_ENV] == "outer"


def test_an_ancestors_marker_means_held_and_a_sibling_threads_does_not(monkeypatch, tmp_path):
    """Codex P1 on #650: the marker is process-wide, so it names the holder's pid. A step of a chain sees its
    ancestor's pid: held, no second lock. In the holder's own process, only the holding thread skips; another
    thread (the admin UI's job threads) waits its turn."""
    import threading
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.setenv(c.HELD_ENV, f"{os.getpid() + 100000}:/elsewhere/db.lock")
    assert c.lock_held_by_caller()
    monkeypatch.delenv(c.HELD_ENV)
    seen, order = {}, []
    inside, release = threading.Event(), threading.Event()

    def holder():
        with c.sync_lock():
            order.append("A in")
            inside.set()
            release.wait(5)
            order.append("A out")

    def other():
        seen["held"] = c.lock_held_by_caller()
        with c.sync_lock():
            order.append("B in")

    a = threading.Thread(target=holder)
    a.start()
    assert inside.wait(5)
    b = threading.Thread(target=other)
    b.start()
    b.join(0.5)
    assert b.is_alive() and seen["held"] is False and order == ["A in"]     # B waits on A's lock
    release.set()
    a.join(5)
    b.join(5)
    assert order == ["A in", "A out", "B in"]


def test_the_service_takes_the_lock_so_the_admin_jobs_do(fresh_db, monkeypatch, tmp_path):
    """Codex P1 on #650: src/web/routes/admin.py calls IngestionService.sync_matches directly, in a job thread. The
    lock is at the service: a sync through it takes it (and a sync inside the cli's lock takes no second one)."""
    from src.ingestion.service import IngestionService
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    _two_mlb_comps()
    taken = []
    real = c.db_lock

    def spy(**k):
        taken.append(k)
        return real(**k)

    monkeypatch.setattr(c, "db_lock", spy)
    payload = schedule(game(849818, "2026-10-15T22:08:00Z", "F", TB, CLE, 2, 3))
    IngestionService(_adapter(payload)).sync_matches("MLB", date_from="2026-10-15", date_to="2026-10-16")
    assert len(taken) == 1
    with c.sync_lock():
        IngestionService(_adapter(payload)).sync_matches("MLB", date_from="2026-10-15", date_to="2026-10-16")
    assert len(taken) == 2                                         # the outer lock only: the service took none


@pytest.mark.parametrize("cmd", ["sync-matches", "sync-teams"])
def test_a_sync_by_hand_takes_the_lock_and_a_step_of_a_holding_run_takes_none(monkeypatch, tmp_path, cmd):
    import cli
    taken = []

    class Spy:
        def __init__(self, **k):
            taken.append(k)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    ran = []
    monkeypatch.setattr(c, "db_lock", Spy)
    monkeypatch.setattr(cli, "_mlb_fallback", lambda code: True)                    # no provider, no DB write
    monkeypatch.setattr(cli, "_mlb_fallback_run", lambda *a, **k: ran.append(a))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    r = CliRunner().invoke(cli.cli, [cmd, "--competition", "MLB", "--season", "2026"])
    assert r.exit_code == 0, r.output
    assert len(taken) == 1 and len(ran) == 1
    monkeypatch.setenv(c.HELD_ENV, f"{os.getpid() + 100000}:{tmp_path / 'db.lock'}")    # an ancestor's lock
    r = CliRunner().invoke(cli.cli, [cmd, "--competition", "MLB", "--season", "2026"])
    assert r.exit_code == 0, r.output
    assert len(taken) == 1 and len(ran) == 2                                         # no second lock


def test_a_sync_by_hand_waits_while_a_chain_holds_the_lock(fresh_db, monkeypatch, tmp_path):
    """The lock held elsewhere (another open file description, as another process holds it): the sync prints that
    it waits and does not write until the lock is free; here the wait times out, so nothing is written."""
    lock = tmp_path / "db.lock"
    monkeypatch.setenv("SP_LOCK", str(lock))
    _two_mlb_comps()
    real = c.db_lock
    monkeypatch.setattr(c, "db_lock", lambda **k: real(timeout_s=0, **k))
    monkeypatch.setattr(c.time, "sleep", lambda s: None)
    with open(lock, "a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = _sync(monkeypatch, schedule(game(849818, "2026-10-15T22:08:00Z", "F", TB, CLE, 2, 3)))
        fcntl.flock(held, fcntl.LOCK_UN)
    assert isinstance(r.exception, TimeoutError)
    assert "… waiting for the DB lock" in r.output
    assert _rows("849818")[0][2] == "SCHEDULED"                                     # nothing written
