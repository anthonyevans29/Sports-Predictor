"""THE AVAILABILITY RECORD (ARCHITECT 2026-11-04 13:05 ET, addendum 252; lane availability-record): the schema PR's
acceptance set, item 6 (a), (b), (c), (g) and (h), on a throwaway SQLite file (the fresh_db fixture below) with
synthetic observations (the adapters are later PRs: no provider call, no payload file).

Item 6, verbatim in part: "(a) append-only — the ingest commands expose no update or delete path, and a test asserts
the tables' row counts only grow across a replay of saved payloads; (b) the as-of query under each clock on a synthetic
history with a flip, a backfilled row and a missed poll — the recorded clock never returns the backfilled row before
its fetch; (c) the five statuses on saved payloads: complete, partial (a team unmapped), empty, failed (a raised call),
missed (a scheduled poll with no call); [...] (g) the derived interval on a sequence of observations equals the flip
the history shows; (h) nothing under data/ after any test."
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import migrate_availability_record as mig
from src.availability import record as rec

REPO = Path(__file__).resolve().parents[1]
REPO_DATA_EXISTED = (REPO / "data").exists()

pytestmark = pytest.mark.usefixtures("fresh_db")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB of its own (tests/test_cup_lineups_live.py's fresh_db): the app's engine and its sessions point
    at it (the mode=ro read follows SessionLocal's bind); cwd = tmp_path. Item 6(h): after the test, no data/ under
    tmp_path, and the repo's data/ exists exactly as it did before the module ran."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    db.init_db()
    yield path
    eng.dispose()
    assert not list(tmp_path.rglob("data")), "item 6(h): nothing under data/"
    assert (REPO / "data").exists() == REPO_DATA_EXISTED, "item 6(h): the repo's data/ untouched"


def _migrate(capsys=None) -> str:
    assert mig.main() == 0
    return capsys.readouterr().out if capsys else ""


def _engine():
    import src.db.database as db
    return db._engine


def _counts() -> tuple[int, int]:
    with _engine().connect() as c:
        return tuple(c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in rec.TABLES)


NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.csv"
LANDING = "https://api-web.nhle.com/v1/gamecenter/2025020123/landing"
KO = datetime(2026, 11, 10, 0, 0)


def _depth(name, gsis, rank, stamp, team="BAL", slot=1, team_id=None):
    return {"kind": "depth_rank", "source_player_id": gsis, "player_name": name, "source_team": team,
            "team_id": team_id, "source_stamp": stamp,
            "attrs": {"pos_grp": "Offense", "pos_abb": "QB", "pos_slot": slot, "pos_rank": rank,
                      "dt_raw": stamp.isoformat() + "Z" if stamp else None}}


def _nfl(fetched_at, status="complete", **kw):
    return {"sport": "nfl", "source": "nflverse_depth_charts", "endpoint": NFLVERSE, "status": status,
            "fetched_at": fetched_at, **kw}


def _nhl(label, fetched_at, status="complete", match_id=77, **kw):
    off = {"T-120": 120, "T-60": 60, "T-30": 30, "T-0": 0, "T+20": -20}[label]
    return {"sport": "nhl", "source": "nhl_api_landing", "endpoint": LANDING, "match_id": match_id, "kickoff_at": KO,
            "poll_label": label, "scheduled_at": KO - timedelta(minutes=off), "fetched_at": fetched_at,
            "status": status, "http_status": 200 if status != "missed" else None, **kw}


def _goalie(pid, name, team_id, side, match_id=77, kind="projected_starter", source_team=None):
    return {"kind": kind, "source_player_id": str(pid), "player_name": name, "team_id": team_id,
            "source_team": source_team, "match_id": match_id, "attrs": {"side": side}}


def _ro():
    from src.db.database import readonly_scope
    return readonly_scope()


# ---- the migration ------------------------------------------------------------------------------------------------------

def test_migration_creates_the_triggers_and_the_marker_and_is_idempotent(capsys):
    out1 = _migrate(capsys)
    assert "· availability_observations already exists." in out1          # init_db made the mapped tables
    assert "+ Wrote migration marker availability_record_migration" in out1
    assert f"triggers on the record ({len(rec.TRIGGERS)})" in out1 and len(rec.TRIGGERS) == 6
    out2 = _migrate(capsys)
    assert "· Kept migration marker" in out2 and "+ Created trigger" not in out2
    with _engine().connect() as c:
        trg = sorted(r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger' "
                                                  "AND tbl_name LIKE 'availability_%'")))
        assert trg == sorted(rec.TRIGGERS)
        assert c.execute(text(f"SELECT COUNT(*) FROM {rec.MIGRATION_MARKER}")).scalar() == 1
    assert "availability_observations: 0 observation(s) stored" in out2


def test_the_migration_refuses_a_missing_db_and_creates_nothing(tmp_path, monkeypatch, capsys):
    """Item 6(h) and law 5: no DB file, exit 1, no file made (tests/test_migrate_guard.py runs it in a process too)."""
    from sqlalchemy import create_engine

    import src.db.database as db
    missing = tmp_path / "nope" / "sports.db"
    monkeypatch.setattr(db, "_engine", create_engine(f"sqlite:///{missing}", future=True))
    assert mig.main() == 1
    assert "a migration never creates one" in capsys.readouterr().out
    assert not missing.exists() and not missing.parent.exists()


def test_writes_refuse_an_unmigrated_store():
    with pytest.raises(rec.Refused, match="migrate_availability_record.py has not run"):
        rec.write_observation(_nfl(datetime(2026, 11, 5, 9)), [_depth("A", "00-1", 1, datetime(2026, 11, 5, 7))])
    assert _counts() == (0, 0)


def test_the_writer_refuses_a_missing_db_file_and_never_creates_it(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    missing = tmp_path / "gone.db"
    eng = create_engine(f"sqlite:///{missing}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True))
    with pytest.raises(rec.Refused, match="no DB file at .*never creates one"):
        rec.write_observation(_nfl(datetime(2026, 11, 5, 9)))
    assert not missing.exists()


# ---- 6(a) append-only ---------------------------------------------------------------------------------------------------

def test_6a_update_and_delete_abort_on_both_tables_whoever_runs_them():
    _migrate()
    r = rec.write_observation(_nfl(datetime(2026, 11, 5, 9)), [_depth("A", "00-1", 1, datetime(2026, 11, 5, 7))])
    assert r.written and r.assertions == 1
    for sql in ("UPDATE availability_observations SET status = 'empty'",
                "UPDATE availability_observations SET match_id = 5 WHERE id = 1",
                "DELETE FROM availability_observations",
                "UPDATE availability_assertions SET team_id = 9",
                "DELETE FROM availability_assertions WHERE id = 1",
                "INSERT OR REPLACE INTO availability_assertions (id, observation_id, sport, kind, source_team, "
                "player_name, recorded_at) SELECT 1, observation_id, sport, kind, 'X', 'Y', recorded_at "
                "FROM availability_assertions WHERE id = 1",
                "INSERT OR REPLACE INTO availability_observations (id, sport, source, endpoint, status, late, "
                "rows_asserted, fetched_at, created_at) SELECT id, sport, source, 'x', 'empty', 0, 0, fetched_at, "
                "created_at FROM availability_observations WHERE id = 1"):
        with pytest.raises(IntegrityError, match="append-only"):
            with _engine().begin() as c:
                c.execute(text(sql))
    assert _counts() == (1, 1)
    with _engine().connect() as c:
        assert c.execute(text("SELECT status, endpoint FROM availability_observations")).one() == ("complete",
                                                                                                   NFLVERSE)


def test_6a_the_module_exposes_no_update_delete_or_upsert_path():
    public = [n for n in dir(rec) if not n.startswith("_")]
    assert not [n for n in public if re.search(r"update|delete|upsert|replace|merge|remove|correct|amend", n, re.I)]
    writers = [n for n in public if n.startswith("write")]
    assert writers == ["write_observation"]                       # the only writer
    src = Path(rec.__file__).read_text()
    for pat in (r"\bOR\s+REPLACE\b", r"on_conflict", r"\.delete\(", r"\bupdate\(", r"\.merge\(",
                r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\s+FROM\b"):
        assert not re.search(pat, src), pat


def test_6a_row_counts_only_grow_across_a_replay():
    """A replay of the same synthetic payload sequence: league-wide fetches are new observations every time, a poll the
    store holds is "already" (its row stands), and the counts never fall."""
    _migrate()
    t = datetime(2026, 11, 5, 9)
    seq = [(_nfl(t), [_depth("A", "00-1", 1, t - timedelta(hours=2))]),
           (_nfl(t + timedelta(days=1)), []),                                    # byte-identical: complete, 0 rows
           (_nhl("T-60", KO - timedelta(minutes=59)), [_goalie(8478406, "G One", 1, "home")]),
           (_nhl("T-30", None, status="missed"), [])]
    seen = [_counts()]
    for rnd in range(2):
        for o, a in seq:
            r = rec.write_observation(o, a)
            if rnd == 1 and o.get("poll_label"):
                assert r.already and not r.written
            seen.append(_counts())
    assert all(b[0] >= a[0] and b[1] >= a[1] for a, b in zip(seen, seen[1:]))
    assert seen[-1] == (6, 3)                                    # 4 + the 2 league-wide replays; 2 + 1 assertions


# ---- 6(c) the five statuses ---------------------------------------------------------------------------------------------

def test_6c_the_five_statuses_are_recorded(monkeypatch):
    _migrate()
    monkeypatch.setenv("API_HOCKEY_KEY", "sekrit-hockey-123")
    got = {}
    got["complete"] = rec.write_observation(_nhl("T-120", KO - timedelta(minutes=119)),
                                            [_goalie(8478406, "G One", 1, "home"), _goalie(8479361, "G Two", 2,
                                                                                            "away")])
    # partial: the away team unmapped (law 4: NULL + the source's text), its goalie unmapped by id, name kept
    got["partial"] = rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60), status="partial"),
                                           [_goalie(8478406, "G One", 1, "home"),
                                            _goalie(8480045, "Karel Vejmelka", None, "away", source_team="UTA")])
    got["empty"] = rec.write_observation(_nhl("T-30", KO - timedelta(minutes=29), status="empty"))
    got["failed"] = rec.write_observation(_nhl("T-0", KO + timedelta(minutes=1), status="failed", http_status=None,
                                               error="ConnectionError: GET ...?apikey=abc123def456 failed; "
                                                     "key sekrit-hockey-123 rejected"))
    got["missed"] = rec.write_observation(_nhl("T+20", None, status="missed"))
    assert all(r.written for r in got.values())
    assert got["complete"].assertions == 2 and got["complete"].unmapped_teams == 0
    assert (got["partial"].assertions, got["partial"].unmapped_teams, got["partial"].unmapped_players) == (2, 1, 2)
    assert got["empty"].assertions == got["failed"].assertions == got["missed"].assertions == 0
    with _ro() as s:
        from sqlalchemy import select

        from src.db.schema import AvailabilityAssertion as A
        from src.db.schema import AvailabilityObservation as O
        rows = {o.status: o for o in s.execute(select(O)).scalars()}
        assert sorted(rows) == sorted(rec.STATUSES)
        assert rows["missed"].fetched_at is None and rows["missed"].scheduled_at == KO + timedelta(minutes=20)
        assert rows["failed"].error.startswith("ConnectionError") and "abc123def456" not in rows["failed"].error
        assert "sekrit-hockey-123" not in rows["failed"].error and "[REDACTED]" in rows["failed"].error
        assert {o.status: o.rows_asserted for o in rows.values()} == {"complete": 2, "partial": 2, "empty": 0,
                                                                      "failed": 0, "missed": 0}
        away = s.execute(select(A).where(A.source_team == "UTA")).scalar_one()
        assert (away.team_id, away.player_id, away.player_name, away.source_player_id) == (None, None,
                                                                                          "Karel Vejmelka", "8480045")
        assert away.recorded_at == rows["partial"].fetched_at                 # = the observation's fetched_at


@pytest.mark.parametrize("status", ["empty", "failed", "missed"])
def test_6c_a_status_with_no_facts_refuses_assertions_in_the_app_and_in_the_file(status):
    _migrate()
    fetched = None if status == "missed" else KO - timedelta(minutes=29)
    extra = {"error": "Timeout: read timed out"} if status == "failed" else {}
    with pytest.raises(rec.Refused, match=f"a {status} observation asserts nothing"):
        rec.write_observation(_nhl("T-30", fetched, status=status, **extra), [_goalie(1, "G", 1, "home")])
    assert _counts() == (0, 0)
    r = rec.write_observation(_nhl("T-30", fetched, status=status, **extra))
    with pytest.raises(IntegrityError, match="only a complete or partial observation asserts a fact"):
        with _engine().begin() as c:                                  # around the app: the trigger refuses too
            c.execute(text("INSERT INTO availability_assertions (observation_id, sport, kind, source_team, "
                           "player_name, recorded_at) VALUES (:o, 'NHL', 'projected_starter', 'X', 'Y', "
                           "'2026-11-09 23:31:00.000000')"), {"o": r.observation_id})


def test_6c_the_checks_refuse_what_the_ruling_forbids():
    _migrate()
    t = datetime(2026, 11, 5, 9)
    bad = [
        (_nfl(t, source="espn_depth"), [], "not in the vocabulary"),
        (_nfl(t, status="stale"), [], "status 'stale'"),
        (_nfl(t), [{**_depth("A", "1", 1, t), "kind": "starter"}], "kind 'starter'"),
        (_nfl(None), [], "has no fetched_at"),
        (_nhl("T-30", KO, status="missed"), [], "missed poll made no call"),
        (_nfl(t, status="failed"), [], "keeps its error"),
        (_nfl(t, endpoint=NFLVERSE + "?token=abc"), [], "carries a secret"),
        (_nfl(t, payload_path="data/availability/x.csv"), [], "under data/"),
        (_nfl(t, payload_path="logs/availability/nhl_api_landing/2026-11-05/x.csv"), [], "not under"),
        (_nfl(t, payload_path="/abs/logs/availability/nflverse_depth_charts/2026-11-05/x.csv"), [], "plain relative"),
        (_nfl(t, payload_path="logs/availability/nflverse_depth_charts/today/x.csv"), [], "not a date"),
        (_nfl(t, payload_sha256="ABC"), [], "64 lower-case hex"),
        (_nfl(t, rows_asserted=3), [], "rows_asserted is counted here"),
        (_nfl(t), [{**_depth("A", "1", 1, t), "recorded_at": t}], "sets recorded_at"),
        (_nfl(t), [{**_depth("A", "1", 1, t), "source_team": None}], "names no team"),
        (_nfl(t), [{"kind": "inactive", "team_id": 3}], "names no player"),
        (_nfl(t), [{**_depth("A", "1", 1, t), "gsis_id": "00-1"}], "names gsis_id"),
    ]
    for o, a, why in bad:
        with pytest.raises(rec.Refused, match=re.escape(why)):
            rec.write_observation(o, a)
    assert _counts() == (0, 0)
    ok = rec.write_observation(_nfl(t, payload_path="logs/availability/nflverse_depth_charts/2026-11-05/dc.csv",
                                    payload_sha256="0" * 64), [])
    assert ok.written and _counts() == (1, 0)


def test_6c_an_aware_stamp_is_stored_as_naive_utc():
    _migrate()
    et = timezone(timedelta(hours=-5))
    r = rec.write_observation(_nfl(datetime(2026, 11, 5, 4, tzinfo=et)),
                              [_depth("A", "00-1", 1, datetime(2026, 11, 5, 2, tzinfo=et))])
    with _ro() as s:
        (row,) = rec.load_rows(s, "nfl")
    assert (row.recorded_at, row.source_stamp, row.observation_id) == (datetime(2026, 11, 5, 9),
                                                                      datetime(2026, 11, 5, 7), r.observation_id)


# ---- 6(b) the as-of query under each clock --------------------------------------------------------------------------------

S0 = datetime(2026, 10, 20, 7)                 # C's source stamp: weeks before the first fetch (backfilled)
S1, T1 = datetime(2026, 11, 5, 7), datetime(2026, 11, 5, 9)
T2 = datetime(2026, 11, 6, 8, 45)              # the missed fetch's scheduled time
S3, T3 = datetime(2026, 11, 7, 7), datetime(2026, 11, 7, 9)
T4 = datetime(2026, 11, 8, 9)


def _history_b():
    """obs1 at T1: QB1 = A. obs2: the 11-06 fetch missed. obs3 at T3: QB1 = B (the flip). obs4 at T4: C at QB2,
    stamped S0, weeks before T1 (a backfilled row)."""
    _migrate()
    rec.write_observation(_nfl(T1), [_depth("A Starter", "00-A", 1, S1)])
    rec.write_observation(_nfl(None, status="missed", scheduled_at=T2))
    rec.write_observation(_nfl(T3), [_depth("B Starter", "00-B", 1, S3)])
    rec.write_observation(_nfl(T4), [_depth("C Backup", "00-C", 2, S0)])


def _names(facts):
    return sorted(f.interval.first.player_name for f in facts)


def test_6b_the_recorded_clock_never_returns_the_backfilled_row_before_its_fetch():
    _history_b()
    with _ro() as s:
        assert _names(rec.as_of(s, "nfl", T1 - timedelta(seconds=1))) == []
        assert _names(rec.as_of(s, "nfl", T1)) == ["A Starter"]
        assert _names(rec.as_of(s, "nfl", T3 - timedelta(seconds=1))) == ["A Starter"]
        assert _names(rec.as_of(s, "nfl", T3)) == ["B Starter"]                  # the flip
        for t in (S0, S1, T1, T2, T3, T4 - timedelta(seconds=1)):
            assert "C Backup" not in _names(rec.as_of(s, "nfl", t))             # never before its fetch
        after = rec.as_of(s, "nfl", T4)
        assert _names(after) == ["B Starter", "C Backup"]
        c = next(f for f in after if f.interval.first.player_name == "C Backup")
        assert c.backfilled is True and c.interval.first.recorded_at == T4 and c.interval.first.source_stamp == S0
        assert next(f for f in after if f.interval.first.player_name == "B Starter").backfilled is False
        line = rec.fact_line(c)
        assert "BACKFILLED" in line and "recorded_at 2026-11-08T09:00:00Z" in line
        assert "source_stamp 2026-10-20T07:00:00Z" in line and f"<{NFLVERSE}>" in line


def test_6b_the_source_clock_reads_the_source_stamp_and_labels_the_backfill():
    _history_b()
    with _ro() as s:
        assert _names(rec.as_of(s, "nfl", S0 - timedelta(seconds=1), clock="source")) == []
        early = rec.as_of(s, "nfl", S0, clock="source")
        assert _names(early) == ["C Backup"] and early[0].backfilled is True
        assert _names(rec.as_of(s, "nfl", S1, clock="source")) == ["A Starter", "C Backup"]
        assert _names(rec.as_of(s, "nfl", S3, clock="source")) == ["B Starter", "C Backup"]


def test_6b_the_missed_poll_changes_nothing_and_every_fact_carries_both_stamps():
    _history_b()
    with _ro() as s:
        before = [f.interval.first.id for f in rec.as_of(s, "nfl", T2 - timedelta(minutes=1))]
        after = [f.interval.first.id for f in rec.as_of(s, "nfl", T2 + timedelta(hours=1))]
        assert before == after and len(before) == 1
        for clock in rec.CLOCKS:
            for f in rec.as_of(s, "nfl", T4 + timedelta(days=1), clock=clock):
                line = rec.fact_line(f)
                assert "recorded_at 20" in line and "source_stamp 20" in line and "obs #" in line


def test_6b_a_null_source_stamp_is_not_read_under_the_source_clock():
    """The NHL landing gives no stamp: under the source clock its facts are not read (law 4: counted, never filled
    from recorded_at); under the recorded clock they are."""
    _migrate()
    rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60)), [_goalie(8478406, "G One", 1, "home")])
    with _ro() as s:
        assert len(rec.as_of(s, "nhl", KO)) == 1
        assert rec.as_of(s, "nhl", KO, clock="source") == []
        assert rec.unread_under_source_clock(s, "nhl") == 1


# ---- 6(g) the derived interval equals the history's flip --------------------------------------------------------------------

def test_6g_the_derived_intervals_are_the_flips_the_history_shows():
    """QB1 over five fetches: A, A (restated), B (the flip), B, A (the flip back): three intervals, each closed by the
    next holder of the slot, and history prints all five assertions in time order with the intervals' ends."""
    _migrate()
    days = [datetime(2026, 11, d, 9) for d in (1, 2, 3, 4, 5)]
    for t, who in zip(days, "AABBA"):
        rec.write_observation(_nfl(t), [_depth(f"{who} QB", f"00-{who}", 1, t - timedelta(hours=2))])
    with _ro() as s:
        ivs = rec.derive(rec.load_rows(s, "nfl"))
        hist = rec.history(s, "nfl", days[-1])
    assert [(iv.first.player_name, iv.start, iv.end, iv.restated) for iv in ivs] == [
        ("A QB", days[0], days[2], 1), ("B QB", days[2], days[4], 1), ("A QB", days[4], None, 0)]
    assert [iv.why_closed for iv in ivs] == ["slot asserted to someone else"] * 2 + [None]
    assert [r.player_name for r, _ in hist] == ["A QB", "A QB", "B QB", "B QB", "A QB"]
    flips = [i for i in range(1, len(hist)) if hist[i][0].player_name != hist[i - 1][0].player_name]
    assert [hist[i][0].recorded_at for i in flips] == [iv.start for iv in ivs[1:]]   # the flips the history shows
    lines = [rec.history_line(r, iv) for r, iv in hist]
    assert "opened" in lines[0] and "restated #" in lines[1] and "ended 2026-11-03T09:00:00Z" in lines[1]
    assert lines[-1].endswith("open")


def test_6g_as_of_is_the_history_cut_at_the_instant():
    """No second path (item 2): at every instant, as_of's facts are exactly the full derivation's intervals that
    started at or before it and had not ended."""
    _history_b()
    with _ro() as s:
        rows = rec.load_rows(s, "nfl")
        for clock in rec.CLOCKS:
            full = rec.derive(rows, clock)
            for t in sorted({S0, S1, S3, T1, T2, T3, T4} | {x + timedelta(seconds=d) for x in (S0, T1, T4)
                                                             for d in (-1, 1)}):
                cut = sorted(iv.first.id for iv in full if iv.start <= t and (iv.end is None or iv.end > t))
                assert sorted(f.interval.first.id for f in rec.as_of(s, "nfl", t, clock=clock)) == cut, (clock, t)


def test_6g_the_same_player_asserted_differently_closes_and_two_in_net_both_hold():
    _migrate()
    t = datetime(2026, 11, 1, 9)
    rec.write_observation(_nfl(t), [_depth("A QB", "00-A", 1, t)])
    rec.write_observation(_nfl(t + timedelta(days=1)), [_depth("A QB", "00-A", 2, t + timedelta(days=1))])
    rec.write_observation(_nhl("T+20", KO + timedelta(minutes=21)),
                          [_goalie(1, "G One", 1, "home", kind="eventual_starter"),
                           _goalie(2, "G Two", 1, "home", kind="eventual_starter")])
    with _ro() as s:
        nfl = rec.derive(rec.load_rows(s, "nfl"))
        assert [(iv.first.attrs["pos_rank"], iv.why_closed) for iv in nfl] == [(1, "asserted differently"),
                                                                               (2, None)]
        net = rec.as_of(s, "nhl", KO + timedelta(hours=1), kind="eventual_starter", match_id=77)
        assert _names(net) == ["G One", "G Two"] and all(f.post_hoc is True for f in net)
        assert rec.as_of(s, "nhl", KO + timedelta(hours=1), match_id=78) == []


def test_a_restatement_with_a_new_raw_stamp_is_not_a_flip():
    """attrs.dt_raw is the source's time text: a later day restating the same slot keeps one interval."""
    _migrate()
    for d in (1, 2):
        t = datetime(2026, 11, d, 9)
        rec.write_observation(_nfl(t), [_depth("A QB", "00-A", 1, t - timedelta(hours=2))])
    with _ro() as s:
        (iv,) = rec.derive(rec.load_rows(s, "nfl"))
    assert iv.restated == 1 and iv.end is None


# ---- the read-only command ------------------------------------------------------------------------------------------------

def _cli(*args):
    from click.testing import CliRunner

    import cli
    return CliRunner().invoke(cli.cli, ["availability", *args])


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_cli_prints_the_facts_and_the_history_and_writes_nothing(fresh_db):
    _history_b()
    before = _sha(fresh_db)
    r = _cli("--sport", "nfl", "--as-of", "2026-11-08T09:00:00Z")
    assert r.exit_code == 0, r.output
    lines = r.output.splitlines()
    assert lines[0] == "AVAILABILITY · nfl · as of 2026-11-08T09:00:00Z · clock recorded · 2 fact(s) in force"
    assert any("B Starter" in ln for ln in lines) and any("C Backup" in ln and "BACKFILLED" in ln for ln in lines)
    assert lines[-1] == "Depth charts: nflverse (CC BY 4.0)"
    h = _cli("--sport", "nfl", "--as-of", "2026-11-08T04:00:00-05:00", "--history", "--team", "BAL")
    assert h.exit_code == 0, h.output
    assert "3 assertion(s) · --history" in h.output.splitlines()[0] and "team BAL" in h.output
    early = _cli("--sport", "nfl", "--as-of", "2026-11-05T08:59:59Z")
    assert early.exit_code == 0 and "  no facts" in early.output and "nflverse (CC BY" not in early.output
    src = _cli("--sport", "nfl", "--as-of", "2026-10-21T00:00:00Z", "--clock", "source", "--kind", "depth_rank")
    assert src.exit_code == 0 and "C Backup" in src.output and "A Starter" not in src.output
    assert _sha(fresh_db) == before                                 # read-only: the file is unchanged


def test_cli_refusals_exit_2():
    r = _cli("--sport", "nfl", "--as-of", "2026-11-08T09:00:00Z")
    assert r.exit_code == 2 and "migrate_availability_record.py has not run" in r.output     # unmigrated
    _migrate()
    for args, why in ((("--as-of", "2026-11-08T09:00:00"), "with Z or an offset"),
                      (("--as-of", "tomorrow"), "not an ISO-8601 instant"),
                      (("--as-of", "2026-11-08T09:00:00Z", "--match-id", "5", "--team", "BAL"), "exclusive"),
                      (("--as-of", "2026-11-08T09:00:00Z", "--db", "/nowhere/copy.db"), "no file at")):
        r = _cli("--sport", "nfl", *args)
        assert r.exit_code == 2 and why in r.output, r.output


def test_cli_reads_a_backup_copy_through_db(fresh_db, tmp_path):
    _history_b()
    copy = tmp_path / "copy" / "sports.db"
    copy.parent.mkdir()
    src, dst = sqlite3.connect(fresh_db), sqlite3.connect(copy)
    src.backup(dst)
    src.close()
    dst.close()
    r = _cli("--sport", "nfl", "--as-of", "2026-11-07T09:00:00Z", "--db", str(copy))
    assert r.exit_code == 0, r.output
    assert "1 fact(s) in force" in r.output and "B Starter" in r.output


def test_cli_a_missing_db_is_refused_and_never_created(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    missing = tmp_path / "absent.db"
    eng = create_engine(f"sqlite:///{missing}", future=True)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True))
    r = _cli("--sport", "nhl", "--as-of", "2026-11-08T09:00:00Z")
    assert r.exit_code == 2 and "never creates one" in r.output and not missing.exists()


def test_merge_teams_refuses_a_pair_whose_retired_team_holds_record_rows(fresh_db):
    """team_id declares its reference to teams.id, so merge-teams knows the column (no "unknown" line); the update
    trigger refuses the re-point, the pair is left with its reason and the record row keeps its team id."""
    from src.db.database import session_scope
    from src.db.schema import Sport, Team
    from src.ingestion import team_merge as tm
    _migrate()
    with session_scope() as s:
        keep, other = Team(sport=Sport.NFL, name="Hawai'i"), Team(sport=Sport.NFL, name="Hawai&#x27;i")
        s.add_all([keep, other])
        s.flush()
        keep_id, other_id = keep.id, other.id
    rec.write_observation(_nfl(datetime(2026, 11, 5, 9)), [_depth("A", "00-1", 1, datetime(2026, 11, 5, 7),
                                                                  team="HAW", team_id=other_id)])
    con = sqlite3.connect(fresh_db, isolation_level=None)
    try:
        p = tm.plan(con)
        assert "availability_assertions.team_id" in p["refs"] and not p["unknown_refs"]
        res = tm.apply(con, "T", [(keep_id, other_id)])
        assert not res["merged"] and "append-only" in res["refused"][0]["why"], res
        assert con.execute("SELECT team_id FROM availability_assertions").fetchone() == (other_id,)
        assert con.execute("SELECT COUNT(*) FROM teams").fetchone() == (2,)
    finally:
        con.close()


def test_dedupe_matches_never_repoints_a_record_row():
    """match_id carries no foreign key: dedupe-matches re-points the foreign keys to matches.id only, so it never
    reaches the record (whose update trigger would abort its whole run); a record row keeps its match id as recorded."""
    from src.ingestion import match_dedupe
    assert not [t.name for t, _, _ in match_dedupe._fk_tables() if t.name in rec.TABLES]


def test_drop_db_drops_the_marker(tmp_path, monkeypatch):
    """init-db --force: drop_all() drops the mapped tables (and their triggers with them); the unmapped marker is
    dropped by name, so an init_db() after it reads as unmigrated."""
    import src.db.database as db
    from sqlalchemy import inspect
    _migrate()
    rec.write_observation(_nfl(datetime(2026, 11, 5, 9)), [_depth("A", "00-1", 1, datetime(2026, 11, 5, 7))])
    db.drop_db()
    db.init_db()
    assert not inspect(_engine()).has_table(rec.MIGRATION_MARKER)
    with pytest.raises(rec.Refused, match="has not run"):
        rec.write_observation(_nfl(datetime(2026, 11, 5, 9)))


# ---- the lane --------------------------------------------------------------------------------------------------------------

def test_the_lane_is_in_the_roadmap_with_no_competitions_and_no_moved_date():
    """Item 7: a new lane, no existing date moved; no competitions (coverage_map reads a lane's competitions as SHADOW
    evidence, and this lane prices nothing)."""
    from src import roadmap as rm
    doc = rm.load()
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "availability-record"]
    assert doc["lanes"][-1] is ln and "competitions" not in ln and ln["moved"] == [] and ln["earliest_live"] is None
    assert [(st["owner"], st["due"]) for st in ln["steps"]] == [
        ("code", "2026-11-10"), ("code", "2026-11-12"), ("architect", "2026-11-14"), ("code", "2026-11-17"),
        ("code", "2026-11-20"), ("code", "2026-11-21"), ("code", "2026-11-25")]
    assert rm.validate(doc) == []


# ---- the repairs: labels from the freshest member, source identity, late inserts, receipts, secrets ------------------------

def test_a_fact_first_seen_backfilled_then_restated_fresh_is_not_backfilled():
    """The first fetch carries weeks of history: A at QB1 stamped 20 days back and again 2 hours back. A live-era
    reader drops BACKFILLED facts, so a QB1 who never changed must not read BACKFILLED once a fresh row restates it;
    the fact enters the live-era record at the first fresh member's recorded_at."""
    _migrate()
    f1, f2 = datetime(2026, 11, 8, 9), datetime(2026, 11, 9, 9)
    rec.write_observation(_nfl(f1), [_depth("A QB", "00-A", 1, f1 - timedelta(days=20)),
                                     _depth("A QB", "00-A", 1, f1 - timedelta(hours=2))])
    rec.write_observation(_nfl(f2), [_depth("A QB", "00-A", 1, f2 - timedelta(hours=2))])
    rec.write_observation(_nfl(f2 + timedelta(hours=1)), [_depth("D Old", "00-D", 3, f1 - timedelta(days=30))])
    with _ro() as s:
        facts = rec.as_of(s, "nfl", f2 + timedelta(hours=2))
    a = next(f for f in facts if f.interval.first.player_name == "A QB")
    assert len([f for f in facts if f.interval.first.player_name == "A QB"]) == 1
    assert a.interval.restated == 2 and rec.backfilled(a.interval.first) is True
    assert a.backfilled is False and a.live_since == f1
    line = rec.fact_line(a)
    assert "BACKFILLED" not in line and "live-era from 2026-11-08T09:00:00Z" in line
    d = next(f for f in facts if f.interval.first.player_name == "D Old")       # only backfilled members: labelled
    assert d.backfilled is True and d.live_since is None and "BACKFILLED" in rec.fact_line(d)


def test_a_mapping_that_lands_between_fetches_never_splits_a_fact():
    """Day 1 partial (BAL unmapped): A QB1, B QB2. Day 2 complete (BAL mapped to team 1, A mapped to player 501): B QB1,
    A QB2. The facts and slots are keyed on the source's own identifiers, so day 2 closes day 1's: exactly the current
    two facts are in force, shown with our ids."""
    _migrate()
    d1, d2 = datetime(2026, 11, 5, 9), datetime(2026, 11, 6, 9)
    rec.write_observation(_nfl(d1, status="partial"), [_depth("A QB", "00-A", 1, d1 - timedelta(hours=2)),
                                                       _depth("B QB", "00-B", 2, d1 - timedelta(hours=2))])
    rec.write_observation(_nfl(d2), [{**_depth("B QB", "00-B", 1, d2 - timedelta(hours=2), team_id=1)},
                                     {**_depth("A QB", "00-A", 2, d2 - timedelta(hours=2), team_id=1),
                                      "player_id": 501}])
    with _ro() as s:
        facts = rec.as_of(s, "nfl", d2 + timedelta(hours=1))
        ivs = rec.derive(rec.load_rows(s, "nfl"))
    assert sorted((f.interval.first.player_name, f.interval.first.attrs["pos_rank"], f.interval.first.team_id)
                  for f in facts) == [("A QB", 2, 1), ("B QB", 1, 1)]
    assert [iv.why_closed for iv in ivs if iv.end is not None] == ["asserted differently"] * 2
    assert any("player #501" in rec.fact_line(f) and "team #1" in rec.fact_line(f) for f in facts)


def test_a_late_assertion_on_an_older_observation_is_refused_by_the_file():
    """No backdating (item 5): only the observation just inserted receives assertions, whoever writes."""
    _migrate()
    t = datetime(2026, 11, 8, 9)
    first = rec.write_observation(_nfl(t), [_depth("A", "00-1", 1, t - timedelta(hours=2))])
    rec.write_observation(_nfl(t + timedelta(days=1)), [])
    with pytest.raises(IntegrityError, match="only the newest observation receives assertions"):
        with _engine().begin() as c:
            c.execute(text("INSERT INTO availability_assertions (observation_id, sport, kind, source_player_id, "
                           "player_name, source_team, recorded_at) VALUES (:o, 'NFL', 'depth_rank', 'g9', 'Z', 'BAL', "
                           "'2026-11-08 09:00:00.000000')"), {"o": first.observation_id})
    assert _counts() == (2, 1)
    r = rec.write_observation(_nfl(t + timedelta(days=2)), [_depth("B", "00-2", 1, t + timedelta(days=2))])
    assert r.written and _counts() == (3, 2)                     # the writer's own path is unchanged


def test_the_migration_on_a_db_from_before_the_record_says_it_created_the_triggers(tmp_path, monkeypatch, capsys):
    """A DB built before this PR has neither table nor trigger: the first run creates both and says so (law 2); the
    second keeps them."""
    from sqlalchemy import create_engine, inspect

    import src.db.database as db
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'before.db'}", future=True)
    Base.metadata.create_all(eng, tables=[t for t in Base.metadata.sorted_tables if t.name not in rec.TABLES])
    with eng.connect() as c:
        assert not c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' "
                                  "AND name LIKE 'trg_availability_%'")).scalar()
    assert not any(inspect(eng).has_table(t) for t in rec.TABLES)
    monkeypatch.setattr(db, "_engine", eng)
    out1 = _migrate(capsys)
    assert out1.count("+ Created trigger") == 6 and "· Kept trigger" not in out1
    assert "+ Creating availability_observations..." in out1 and "+ Creating availability_assertions..." in out1
    out2 = _migrate(capsys)
    assert out2.count("· Kept trigger") == 6 and "+ Created trigger" not in out2
    eng.dispose()


@pytest.mark.parametrize("endpoint", [
    LANDING + "?api_token=abc123", LANDING + "?access_key=abc123", LANDING + "/abc123?client_secret=xyz",
    LANDING + "?apiKey=abc123", LANDING + "?season=2026&X-Api-Key=abc123", LANDING + "?sig=abc123",
    "https://user:hunter2pw@api.example.com/v3/nhl/goalies", "https://tok_9f8e7d6c5b4a@api.example.com/v3/nhl",
])
def test_the_endpoint_check_refuses_every_credential_shape(endpoint):
    _migrate()
    with pytest.raises(rec.Refused, match="carries a secret"):
        rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60), endpoint=endpoint))
    assert _counts() == (0, 0)


def test_the_endpoint_check_passes_the_feeds_plain_urls():
    for ep in (NFLVERSE, LANDING, "https://api-web.nhle.com/v1/schedule/2026-11-13",
               "https://example.com/v1/teams?hockey=1&monkey=2&design=3", "depth_charts_2025.csv"):
        assert rec._endpoint_secret(ep) is None, ep


@pytest.mark.parametrize("error, secret", [
    ("HTTPError 401: Authorization: Bearer tok_9f8e7d6c5b4a rejected", "tok_9f8e7d6c5b4a"),
    ("401 Unauthorized: Authorization: Bearer sk_live_ABCDEF123456", "sk_live_ABCDEF123456"),
    ("HTTPError 401 headers={'Authorization': 'Bearer tok_abc123456', 'Accept': 'json'}", "tok_abc123456"),
    ('HTTPError 403 {"api_key": "k_5544332211"}', "k_5544332211"),
    ("GET https://svc:pw_1234567@api.example.com/x failed", "pw_1234567"),
    ("GET https://x.example.com/g?api_token=tok_77665544&date=2026-11-13 failed", "tok_77665544"),
    ("GET https://x.example.com/g?access_key=ak_99887766 failed", "ak_99887766"),
    ("GET https://x.example.com/g?client_secret=cs_11223344 failed", "cs_11223344"),
])
def test_the_stored_error_column_holds_no_credential(error, secret):
    _migrate()
    r = rec.write_observation(_nhl("T-0", KO, status="failed", http_status=401, error=error))
    assert r.written
    with _engine().connect() as c:
        stored = c.execute(text("SELECT error FROM availability_observations")).scalar()
    assert secret not in stored and "[REDACTED]" in stored, stored


def test_cli_history_carries_the_backfilled_and_post_hoc_labels():
    _history_b()
    rec.write_observation(_nhl("T+20", KO + timedelta(minutes=21)),
                          [_goalie(1, "G One", 1, "home", kind="eventual_starter")])
    h = _cli("--sport", "nfl", "--as-of", "2026-11-08T09:00:00Z", "--history")
    assert h.exit_code == 0, h.output
    c_line = next(ln for ln in h.output.splitlines() if "C Backup" in ln)
    assert "BACKFILLED (source-stamped backtests only; never the live-era record)" in c_line
    assert not any("BACKFILLED" in ln for ln in h.output.splitlines() if "B Starter" in ln)
    n = _cli("--sport", "nhl", "--as-of", "2026-11-10T01:00:00Z", "--history")
    assert n.exit_code == 0 and any("G One" in ln and "POST HOC" in ln for ln in n.output.splitlines()), n.output
