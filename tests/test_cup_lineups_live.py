"""ARCHITECT 2026-10-23, addendum 158 item 3(a): cups Step B, the LIVE T-15 observation store (observe-cup-lineups),
on a throwaway SQLite file (tests/test_record_vs_close.py iso_db) with a fake adapter and a fake clock (no network)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.db.schema import MatchStatus, Sport
from src.ingestion import cup_lineups_live as live
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

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
