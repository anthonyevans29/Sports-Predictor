"""ARCHITECT 2026-10-23, addendum 158 item 3(a): cups Step B, the LIVE T-15 observation store (observe-cup-lineups),
on a throwaway SQLite file (the fresh_db fixture below) with a fake adapter and a fake clock (no network)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.db.schema import MatchStatus, Sport
from src.ingestion import cup_lineups_live as live

pytestmark = pytest.mark.usefixtures("fresh_db")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB of its own (tests/test_lineups_history.py's fresh_db): the app's engine, its sessions and the
    mode=ro reader (venue_quote_age.db_file_path) all point at it; cwd = tmp_path."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.walters import venue_quote_age
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.setattr(venue_quote_age, "db_file_path", lambda: path)
    monkeypatch.chdir(tmp_path)
    db.init_db()
    yield path
    eng.dispose()

KO = datetime(2026, 10, 28, 20, 0)
HOME_SRC, AWAY_SRC = "541", "529"


def _setup(migrated=True, fixture_id="1500100", status=MatchStatus.SCHEDULED):
    from sqlalchemy import text

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="CL", name="CL", area="X", type="CUP")
        h = Team(sport=Sport.SOCCER, name="Real Madrid", external_ids={"api_football": int(HOME_SRC)})
        a = Team(sport=Sport.SOCCER, name="Barcelona", external_ids={"api_football": int(AWAY_SRC)})
        s.add_all([c, h, a])
        s.flush()
        s.add(Match(id=900, sport=Sport.SOCCER, competition_id=c.id, season="2026/27", utc_date=KO, status=status,
                    home_team_id=h.id, away_team_id=a.id,
                    external_ids={"api_football": fixture_id} if fixture_id else {}))
        if migrated:
            s.execute(text(f"CREATE TABLE {live.MIGRATION_MARKER} (id INTEGER PRIMARY KEY, script TEXT, "
                           "migrated_at DATETIME)"))
            s.execute(text(f"INSERT INTO {live.MIGRATION_MARKER} VALUES (1, 'migrate_cup_lineup_observations.py', "
                           "'2026-10-23 00:00:00')"))


def _slots(team, names, starter=True):
    return [{"team_source_id": team, "formation": "4-3-3", "is_starter": starter, "player_name": n,
             "player_position": "M", "shirt_number": i} for i, n in enumerate(names, 1)]


ELEVEN_H = [f"H{i}" for i in range(11)]
ELEVEN_A = [f"A{i}" for i in range(11)]


class FakeAdapter:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def list_lineup_confirmed(self, fid):
        self.calls.append(fid)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def _rows():
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import CupLineupObservation as Obs
    with session_scope() as s:
        rows = list(s.execute(select(Obs).order_by(Obs.scheduled_at)).scalars())
        s.expunge_all()
    return rows


def test_the_label_poll_the_first_complete_and_a_correction_are_appended_never_replaced():
    _setup()
    full = _slots(HOME_SRC, ELEVEN_H) + _slots(AWAY_SRC, ELEVEN_A) + _slots(HOME_SRC, ["HB1"], starter=False)
    changed = _slots(HOME_SRC, ELEVEN_H[:10] + ["H-late-change"]) + _slots(AWAY_SRC, ELEVEN_A)
    ad = FakeAdapter([full, full, changed])
    t15 = live.tick(KO - timedelta(minutes=15), adapter=ad, clock=lambda: KO - timedelta(minutes=14, seconds=50))
    assert [r["poll_label"] for r in t15.rows] == ["T-15"] and t15.remaining == 2
    live.tick(KO - timedelta(minutes=5), adapter=ad, clock=lambda: KO - timedelta(minutes=5))
    live.tick(KO + timedelta(minutes=10), adapter=ad, clock=lambda: KO + timedelta(minutes=10))
    rows = _rows()
    assert [(r.poll_label, r.status, r.is_first_complete, r.differs_from_first) for r in rows] == [
        ("T-15", "complete", True, None), ("T-5", "complete", False, False), ("T+10", "complete", False, True)]
    first = rows[0]
    assert first.scheduled_at == KO - timedelta(minutes=15) and first.observed_at == KO - timedelta(minutes=14, seconds=50)
    assert first.home_starters == 11 and first.away_starters == 11 and not first.late
    assert len(first.lineup["home"]["starters"]) == 11 and first.lineup["home"]["bench"][0]["name"] == "HB1"
    assert "H-late-change" not in {p["name"] for p in first.lineup["home"]["starters"]}   # the first is kept as it was
    assert ad.calls == ["1500100"] * 3


def test_a_rerun_never_asks_a_poll_that_has_a_row():
    _setup()
    ad = FakeAdapter([_slots(HOME_SRC, ELEVEN_H) + _slots(AWAY_SRC, ELEVEN_A)])
    live.tick(KO - timedelta(minutes=14), adapter=ad)
    t = live.tick(KO - timedelta(minutes=13), adapter=ad)
    assert t.due == 0 and not t.rows and ad.calls == ["1500100"]


def test_failed_partial_empty_late_and_missed_rows_are_explicit():
    _setup()
    ad = FakeAdapter([RuntimeError("HTTP 500"), _slots(HOME_SRC, ELEVEN_H[:9]) + _slots("999", ELEVEN_A), []])
    live.tick(KO - timedelta(minutes=15), adapter=ad)                                       # T-15: the call raises
    live.tick(KO - timedelta(minutes=5), adapter=ad, clock=lambda: KO + timedelta(minutes=1))   # T-5 asked 6 min late
    live.tick(KO + timedelta(minutes=10), adapter=ad)                                       # T+10: empty answer
    rows = {r.poll_label: r for r in _rows()}
    assert rows["T-15"].status == "failed" and rows["T-15"].error == "RuntimeError: HTTP 500"
    assert rows["T-5"].status == "partial" and rows["T-5"].late and rows["T-5"].unmapped_sides == 1
    assert (rows["T-5"].home_starters, rows["T-5"].away_starters) == (9, 0)
    assert rows["T+10"].status == "empty" and not any(r.is_first_complete for r in rows.values())


def test_a_poll_long_past_its_time_gets_a_missed_row_and_no_call():
    _setup()
    ad = FakeAdapter([])
    t = live.tick(KO + timedelta(minutes=50), adapter=ad)        # every poll is past its time by more than 30 minutes
    rows = {r.poll_label: r for r in _rows()}
    assert ad.calls == [] and t.due == 3 and {r.status for r in rows.values()} == {"missed"}
    assert rows["T-15"].observed_at is None and not rows["T-15"].late


def test_it_refuses_without_the_migration_and_a_dry_run_writes_nothing():
    _setup(migrated=False)
    with pytest.raises(live.Refused, match="migrate_cup_lineup_observations.py has not run"):
        live.tick(KO - timedelta(minutes=15), adapter=FakeAdapter([]))
    ad = FakeAdapter([])
    t = live.tick(KO - timedelta(minutes=15), dry_run=True, adapter=ad)
    assert ad.calls == [] and t.rows[0]["status"] == "(dry run: would ask)" and _rows() == []
    assert "DRY RUN: no call, nothing written" in live.tick_lines(t, True)[0]


def test_not_games_and_no_fixture_id_are_handled():
    _setup(status=MatchStatus.POSTPONED)
    assert live.tick(KO - timedelta(minutes=15), adapter=FakeAdapter([])).fixtures == 0


def test_a_fixture_with_no_provider_id_gets_a_failed_row_and_no_call():
    _setup(fixture_id=None)
    ad = FakeAdapter([])
    live.tick(KO - timedelta(minutes=15), adapter=ad)
    (row,) = _rows()
    assert row.status == "failed" and "no API-Football fixture id" in row.error and ad.calls == []


def test_drop_db_drops_the_marker(tmp_path, monkeypatch):
    """init-db --force: drop_all() drops mapped tables only, so the unmapped marker is dropped by name (the
    ncaa_cfbd_labels_migration convention, Codex on #333); otherwise init_db() recreates an empty table that reads
    as migrated. On a DB of its own: drop_db() acts on the module engine."""
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.walters import venue_quote_age
    eng = create_engine(f"sqlite:///{tmp_path / 'drop.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(venue_quote_age, "db_file_path", lambda: tmp_path / "drop.db")
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    _setup()
    assert inspect(eng).has_table(live.MIGRATION_MARKER)
    db.drop_db()
    db.init_db()
    assert not inspect(eng).has_table(live.MIGRATION_MARKER)
    with pytest.raises(live.Refused, match="migrate_cup_lineup_observations.py has not run"):
        live.tick(KO - timedelta(minutes=15), adapter=FakeAdapter([]))


# ---- Codex on #662 ---------------------------------------------------------------------------------------------------

def test_codex_662_a_missing_db_file_is_refused_and_never_created(tmp_path, monkeypatch):
    """P2: session_scope() on a missing SQLite file creates it (the engine's connect hooks). A dry run and a run that
    will refuse both refuse before any session opens, and leave no file behind; the dry run reads mode=ro."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.walters import venue_quote_age
    missing = tmp_path / "nope.db"            # its directory exists: SQLite would create the file on a connect
    eng = create_engine(f"sqlite:///{missing}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.setattr(venue_quote_age, "db_file_path", lambda: missing)
    for dry in (True, False):
        with pytest.raises(live.Refused, match="no DB file at"):
            live.tick(KO - timedelta(minutes=15), dry_run=dry, adapter=FakeAdapter([]))
    assert not missing.exists()


def test_codex_662_a_dry_run_reads_through_the_read_only_session(monkeypatch):
    """P2: --dry-run never opens the app's session_scope (which commits and runs the connect hooks)."""
    import src.db.database as db
    _setup()

    def no_scope():
        raise AssertionError("a dry run opened session_scope()")
    monkeypatch.setattr(db, "session_scope", no_scope)
    t = live.tick(KO - timedelta(minutes=15), dry_run=True, adapter=FakeAdapter([]))
    assert t.fixtures == 1 and [r["status"] for r in t.rows] == ["(dry run: would ask)"]


def test_codex_662_no_key_refuses_before_any_row_is_written(monkeypatch):
    """P1: at T+20 the T-15 poll is missed (no call) and T-5 / T+10 need the provider; with no API key the adapter
    refuses BEFORE the missed row is written, so a refusal writes nothing."""
    import dataclasses

    from src.adapters import api_football
    monkeypatch.setattr(api_football, "settings", dataclasses.replace(api_football.settings, api_football_key=""))
    _setup()
    with pytest.raises(live.Refused, match="API-Football key is required"):
        live.tick(KO + timedelta(minutes=20))
    assert _rows() == []


def test_codex_662_no_provider_call_due_builds_no_adapter(monkeypatch):
    """P1, the other side: a plan with no provider call (every poll missed) never builds the adapter, so a missing
    key does not stop the explicit missed rows."""
    import dataclasses

    from src.adapters import api_football
    monkeypatch.setattr(api_football, "settings", dataclasses.replace(api_football.settings, api_football_key=""))
    _setup()
    t = live.tick(KO + timedelta(minutes=50))
    assert {r.status for r in _rows()} == {"missed"} and len(t.rows) == 3


def test_codex_662_a_re_dated_fixture_starts_a_fresh_poll_set_and_keeps_the_old_rows():
    """P1: the rows are keyed by the kickoff instance. After a schedule sync moves Match.utc_date, the new kickoff's
    polls are due (the old kickoff's rows do not block them), its first complete row is its own, and a later poll
    compares against THAT first; the old rows are kept as they were (append-only)."""
    from src.db.database import session_scope
    from src.db.schema import Match
    _setup()
    old = _slots(HOME_SRC, ["OLD"] + ELEVEN_H[1:]) + _slots(AWAY_SRC, ELEVEN_A)
    new = _slots(HOME_SRC, ELEVEN_H) + _slots(AWAY_SRC, ELEVEN_A)
    ad = FakeAdapter([old, new, new])
    live.tick(KO - timedelta(minutes=15), adapter=ad)
    ko2 = KO + timedelta(days=1)
    with session_scope() as s:
        s.get(Match, 900).utc_date = ko2
    t = live.tick(ko2 - timedelta(minutes=15), adapter=ad)
    assert t.due == 1 and t.rows[0]["kickoff_at"] == ko2
    live.tick(ko2 - timedelta(minutes=5), adapter=ad)
    rows = _rows()
    assert [(r.kickoff_at, r.poll_label, r.status, r.is_first_complete, r.differs_from_first) for r in rows] == [
        (KO, "T-15", "complete", True, None),
        (ko2, "T-15", "complete", True, None),
        (ko2, "T-5", "complete", False, False)]
    assert "OLD" in {p["name"] for p in rows[0].lineup["home"]["starters"]}     # the old row, as it was
    assert ad.calls == ["1500100"] * 3


def test_codex_662_the_unique_key_holds_the_kickoff_instance():
    from src.db.schema import CupLineupObservation as Obs
    (uq,) = [c for c in Obs.__table__.constraints if c.name == "uq_cup_lineup_obs_match_kickoff_poll"]
    assert [c.name for c in uq.columns] == ["match_id", "kickoff_at", "poll_label"]
    assert Obs.__table__.c.kickoff_at.nullable is False


def test_codex_662_a_real_tick_holds_the_db_lock_across_check_call_and_insert():
    """P1: the due-check, the provider call and the insert run under sp_common.sync_lock (the chains' DB lock, #569),
    as sync-teams / sync-matches do; a dry run takes no lock."""
    _setup()
    held = []

    class Probe(FakeAdapter):
        def list_lineup_confirmed(self, fid):
            import sp_common
            held.append(sp_common.lock_held_by_caller())
            return super().list_lineup_confirmed(fid)
    live.tick(KO - timedelta(minutes=15), adapter=Probe([_slots(HOME_SRC, ELEVEN_H) + _slots(AWAY_SRC, ELEVEN_A)]))
    assert held == [True]


def test_codex_662_an_insert_another_run_beat_is_counted_already_observed_not_a_crash():
    """P1: a row stored for the same (match, kickoff, poll) between our due-check and our insert (a writer outside
    the lock) is skipped and counted, never a crash; its row stands and later polls compare against it."""
    from src.db.database import session_scope
    from src.db.schema import CupLineupObservation as Obs
    _setup()
    full = _slots(HOME_SRC, ELEVEN_H) + _slots(AWAY_SRC, ELEVEN_A)

    class Racer(FakeAdapter):
        def list_lineup_confirmed(self, fid):
            with session_scope() as s:      # the other run stores the T-15 poll first
                s.add(Obs(match_id=900, competition="CL", fixture_source_id=fid, kickoff_at=KO, poll_label="T-15",
                          scheduled_at=KO - timedelta(minutes=15), observed_at=KO - timedelta(minutes=15),
                          status="complete", lineup=live.lineup_of(full, live._fixtures(s, ("CL",), KO)[0])[0],
                          home_starters=11, away_starters=11, unmapped_sides=0, is_first_complete=True))
            return super().list_lineup_confirmed(fid)
    t = live.tick(KO - timedelta(minutes=15), adapter=Racer([full]))
    assert t.already == 1 and t.rows == [] and len(_rows()) == 1
    assert "already observed 1" in live.tick_lines(t, False)[0]


def test_a_tick_with_no_poll_due_takes_no_lock_and_still_refuses_an_unmigrated_store(monkeypatch):
    """ARCHITECT 2026-10-27, addendum 169 item 4(i): the host's timer ticks every five minutes; a tick with nothing due
    reads mode=ro and ends without the chains' DB lock, and an unmigrated store is still refused as a real tick does."""
    _setup()
    taken = []

    class Lock:
        def __enter__(self):
            taken.append(True)

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(live, "_db_lock", Lock)
    t = live.tick(KO - timedelta(hours=1), adapter=FakeAdapter([]))        # every poll still ahead
    assert t.due == 0 and t.remaining == 3 and taken == [] and _rows() == []
    t = live.tick(KO - timedelta(hours=5), adapter=FakeAdapter([]))        # no fixture within 3 h
    assert t.fixtures == 0 and taken == []
    full = _slots(HOME_SRC, ELEVEN_H) + _slots(AWAY_SRC, ELEVEN_A)
    t = live.tick(KO - timedelta(minutes=15), adapter=FakeAdapter([full]))   # the T-15 poll due: the lock, a row
    assert taken == [True] and len(_rows()) == 1


def test_a_lock_free_tick_still_refuses_an_unmigrated_store(tmp_path):
    _setup(migrated=False)
    with pytest.raises(live.Refused, match="migrate_cup_lineup_observations.py has not run"):
        live.tick(KO - timedelta(hours=1), adapter=FakeAdapter([]))
