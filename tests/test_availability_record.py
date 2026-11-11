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


def _depth(name, gsis, rank, stamp, team="BAL", slot=1, team_id=None, abb="QB"):
    return {"kind": "depth_rank", "source_player_id": gsis, "player_name": name, "source_team": team,
            "team_id": team_id, "source_stamp": stamp,
            "attrs": {"pos_grp": "Offense", "pos_abb": abb, "pos_slot": slot, "pos_rank": rank,
                      "dt_raw": stamp.isoformat() + "Z" if stamp else None}}


def _nfl(fetched_at, status="complete", **kw):
    return {"sport": "nfl", "source": "nflverse_depth_charts", "endpoint": NFLVERSE, "status": status,
            "fetched_at": fetched_at, **kw}


# THE SMALL FULL CHART (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1): "#831's one-row test histories that
# exercise nflverse semantics are rewritten as small full charts; the generic record tests on synthetic non-snapshot
# sources keep their shape (the rule is per source, not global)". The writer requires a payload hash on every nflverse
# observation that asserts a row, so each load below is a WHOLE chart of each team present (a snapshot), carrying a
# hash: the team's rows the test names, two filler rows of the same team, and a second team's three rows. The fillers
# and the second team are restated by every load, so the facts a test names behave as before; _names leaves them out.
FILL = (("Fill WR", "WR", 3), ("Fill TE", "TE", 4))          # the named team's other rows: the same every load
OTHER = (("Fill KC QB", "QB", 1), ("Fill KC WR", "WR", 3), ("Fill KC TE", "TE", 4))   # a second team, KC


def _chart(stamp, *named, team="BAL", team_id=None):
    """One SYNTHETIC load at `stamp`: the named rows (_depth), `team`'s filler rows, and KC's chart."""
    return (list(named)
            + [_depth(n, f"00-{team}-{abb}", 1, stamp, team, slot, team_id, abb) for n, abb, slot in FILL]
            + [_depth(n, f"00-KC-{abb}", 1, stamp, "KC", slot, None, abb) for n, abb, slot in OTHER])


def _loaded(fetched_at, rows, status="complete", **kw):
    """(an nflverse observation that asserts `rows`, carrying its payload's hash, 262 item 1; the rows): the hash of the
    synthetic payload (the rows and the fetch)."""
    sha = hashlib.sha256(repr((fetched_at, [sorted(r.items(), key=str) for r in rows])).encode()).hexdigest()
    return _nfl(fetched_at, status, payload_sha256=sha, **kw), rows


def _load(fetched_at, rows, status="complete", **kw):
    return rec.write_observation(*_loaded(fetched_at, rows, status, **kw))


def _bal_qb(facts_or_rows):
    """The named team's QB rows (facts, intervals, rows, or history's (row, interval) pairs): what the one-row
    histories asserted."""
    def row(x):
        if isinstance(x, tuple):
            return x[0]
        return x.interval.first if hasattr(x, "interval") else x.first if hasattr(x, "first") else x
    return [x for x in facts_or_rows if row(x).source_team == "BAL" and row(x).attrs["pos_abb"] == "QB"]


def _nhl(label, fetched_at, status="complete", match_id=77, **kw):
    off = {"T-120": 120, "T-60": 60, "T-30": 30, "T-0": 0, "T+20": -20}[label]
    return {"sport": "nhl", "source": "nhl_api_landing", "endpoint": LANDING, "match_id": match_id, "kickoff_at": KO,
            "poll_label": label, "scheduled_at": KO - timedelta(minutes=off), "fetched_at": fetched_at,
            "status": status, "http_status": 200 if status != "missed" else None, **kw}


GID = "2025020123"                             # the NHL gameId of LANDING (attrs.source_match_id)


def _goalie(pid, name, team_id, side, match_id=77, kind="projected_starter", source_team=None, gid=GID):
    return {"kind": kind, "source_player_id": str(pid), "player_name": name, "team_id": team_id,
            "source_team": source_team, "match_id": match_id, "attrs": {"side": side, "source_match_id": gid}}


def _ro():
    from src.db.database import readonly_scope
    return readonly_scope()


# ---- the migration ------------------------------------------------------------------------------------------------------

def test_migration_creates_the_triggers_and_the_marker_and_is_idempotent(capsys):
    out1 = _migrate(capsys)
    assert "· availability_observations already exists." in out1          # init_db made the mapped tables
    assert "+ Wrote migration marker availability_record_migration" in out1
    assert f"triggers on the record ({len(rec.TRIGGERS)})" in out1 and len(rec.TRIGGERS) == 8   # 262 item 1; #835 item 2 (258 item 2(2))
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
        _load(datetime(2026, 11, 5, 9), _chart(datetime(2026, 11, 5, 7), _depth("A", "00-1", 1,
                                                                           datetime(2026, 11, 5, 7))))
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
    r = _load(datetime(2026, 11, 5, 9), _chart(datetime(2026, 11, 5, 7), _depth("A", "00-1", 1,
                                                                               datetime(2026, 11, 5, 7))))
    assert r.written and r.assertions == 6
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
    assert _counts() == (1, 6)
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
    seq = [_loaded(t, _chart(t - timedelta(hours=2), _depth("A", "00-1", 1, t - timedelta(hours=2)))),
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
    assert seen[-1] == (6, 13)                                   # 4 + the 2 league-wide replays; 2 x 6 + 1 assertions


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
        (_nfl(t), _chart(t, _depth("A", "1", 1, t)), "keeps no payload_sha256"),          # addendum 262 item 1
    ]
    for o, a, why in bad:
        with pytest.raises(rec.Refused, match=re.escape(why)):
            rec.write_observation(o, a)
    assert _counts() == (0, 0)
    ok = rec.write_observation(_nfl(t, payload_path="logs/availability/nflverse_depth_charts/2026-11-05/dc.csv",
                                    payload_sha256="0" * 64), [])
    assert ok.written and _counts() == (1, 0)


def test_262_1_the_writer_refuses_a_snapshot_sources_rows_without_a_payload_hash():
    """ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1 (fail-first: on HEAD d327d299 the hashless chart was
    written): "for a SNAPSHOT source [...] the WRITER REQUIRES `payload_sha256` on every observation that asserts a row
    [...] An observation of a snapshot source with rows and no hash is REFUSED by the insert guard with its reason;
    `failed` and `missed` observations carry no payload and assert nothing, as before" -- "the rule is per source, not
    global". And "the snapshot gate as built (read as a snapshot only with a hash) stays"."""
    _migrate()
    t = datetime(2026, 11, 5, 9)
    s = t - timedelta(hours=2)
    for status in ("complete", "partial"):
        with pytest.raises(rec.Refused, match=r"the snapshot source nflverse_depth_charts asserts 6 row\(s\) and keeps "
                                              r"no payload_sha256: the hash is the load's identity.*262 item 1"):
            rec.write_observation(_nfl(t, status), _chart(s, _depth("A", "00-1", 1, s)))
    assert _counts() == (0, 0)
    # no row, no payload, as before: failed, missed, empty, and a complete fetch that asserts nothing
    for o in (_nfl(t, "failed", error="ConnectionError: synthetic"), _nfl(None, "missed", scheduled_at=t),
              _nfl(t, "empty"), _nfl(t + timedelta(hours=1))):
        assert rec.write_observation(o).written
    # per source: a non-snapshot source's rows need no hash
    assert rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60)), [_goalie(1, "G One", 1, "home")]).written
    # with the hash, the same chart is written
    r = _load(t + timedelta(hours=2), _chart(s, _depth("A", "00-1", 1, s)))
    assert r.written and r.assertions == 6 and _counts() == (6, 7)
    assert dict(rec.SNAPSHOT_SOURCES) == {"nflverse_depth_charts": "depth_rank"}
    # the gate as built: a group read without a hash (a store written before this rule) is not a load
    with _ro() as ro:
        g = [x for x in rec.load_rows(ro, "nfl") if x.observation_id == r.observation_id]
    from dataclasses import replace
    assert rec.snapshot_load(g) and not rec.snapshot_load([replace(x, payload_sha256=None) for x in g])


SNAP_GUARD = "trg_availability_assertions_snapshot_hash_guard"


def _raw_obs_and_row(c, source, sha, at, spid="1"):
    """Around the app: one raw observation of `source` (its payload_sha256 `sha`) and one raw assertion on it. `at`
    goes in as the stored text (python 3.12 deprecates sqlite3's default datetime adapter)."""
    at = at.strftime("%Y-%m-%d %H:%M:%S.%f")
    c.execute(text("INSERT INTO availability_observations (sport, source, endpoint, fetched_at, status, late, "
                   "rows_asserted, created_at, payload_sha256) VALUES ('NFL', :src, 'file:x.csv', :at, 'complete', "
                   "0, 1, :at, :sha)"), {"src": source, "at": at, "sha": sha})
    oid = c.execute(text("SELECT MAX(id) FROM availability_observations")).scalar()
    c.execute(text("INSERT INTO availability_assertions (observation_id, sport, kind, source_player_id, player_name, "
                   "source_team, recorded_at, source_stamp, attrs) VALUES (:o, 'NFL', 'depth_rank', :spid, 'P', "
                   "'BAL', :at, :at, '{}')"), {"o": oid, "at": at, "spid": spid})


def test_262_1_the_insert_guard_refuses_a_raw_hashless_snapshot_assertion():
    """Addendum 262 item 1: "An observation of a snapshot source with rows and no hash is REFUSED by the insert guard
    with its reason". The insert guards are the triggers (schema.AVAILABILITY_TRIGGERS): a raw INSERT, around the
    writer, is refused too (fail-first: on the first 262 build a raw hashless nflverse assertion was stored). Per
    source: a non-snapshot source's raw row needs no hash, and a hashed nflverse row goes in."""
    _migrate()
    at = datetime(2026, 11, 5, 9)
    with pytest.raises(IntegrityError, match=r"a snapshot source.*no payload_sha256.*addendum 262 item 1"):
        with _engine().begin() as c:
            _raw_obs_and_row(c, "nflverse_depth_charts", None, at)
    assert _counts() == (0, 0)
    with _engine().begin() as c:
        _raw_obs_and_row(c, "sportsdataio_goalies", None, at)
        _raw_obs_and_row(c, "nflverse_depth_charts", "c" * 64, at + timedelta(hours=1))
    assert _counts() == (2, 2)
    assert SNAP_GUARD in rec.TRIGGERS


def test_262_1_a_store_migrated_before_the_hash_guard_gains_it_on_a_rerun(tmp_path, monkeypatch, capsys):
    """The hash guard is a trigger of its own (CREATE TRIGGER IF NOT EXISTS cannot change the existing insert guard on
    a migrated store): a store migrated by #831 (six triggers) gains it on a rerun of migrate_availability_record.py,
    additive and idempotent, as the recorded-clock index does (262 item 4: one migration ritual); a third run keeps it.
    Then the raw hashless nflverse row is refused on that store."""
    _migrate(capsys)
    with _engine().begin() as c:                                   # a tmp store: #831's trigger set, without it
        c.execute(text(f"DROP TRIGGER {SNAP_GUARD}"))
    at = datetime(2026, 11, 5, 9)
    out1 = _migrate(capsys)
    assert f"+ Created trigger {SNAP_GUARD}" in out1 and out1.count("+ Created trigger") == 1
    assert out1.count("· Kept trigger") == len(rec.TRIGGERS) - 1 and "MISSING" not in out1
    out2 = _migrate(capsys)
    assert f"· Kept trigger {SNAP_GUARD}" in out2 and "+ Created trigger" not in out2
    with pytest.raises(IntegrityError, match="addendum 262 item 1"):
        with _engine().begin() as c:
            _raw_obs_and_row(c, "nflverse_depth_charts", None, at)
    assert _counts() == (0, 0)


def test_262_5_the_writer_refuses_a_snapshot_sources_row_with_no_source_player_id():
    """Addendum 262 item 5: a row with a blank `espn_id` is "never keyed by name". The adapter refuses it into its
    group's partial status; the writer, the record's only writer, refuses a snapshot source's assertion that carries
    no source_player_id (record.player_key would key it by name), with its reason, and so does assertion_refusal (the
    adapter's pre-check). Fail-first: on the first 262 build a hashed nflverse load with a name-only row was written
    and keyed ("name", ...). Per source: a non-snapshot source's name-only row is written as before."""
    _migrate()
    t = datetime(2026, 11, 5, 9)
    s = t - timedelta(hours=2)
    name_only = _depth("Name Only", None, 1, s)
    with pytest.raises(rec.Refused, match=r"assertion 1 of the snapshot source nflverse_depth_charts carries no "
                                          r"source_player_id.*never keyed by name.*262 item 5"):
        _load(t, _chart(s, name_only))
    assert _counts() == (0, 0)
    assert "never keyed by name" in rec.assertion_refusal(name_only, 1, "nflverse_depth_charts")
    assert rec.assertion_refusal(name_only, 1, "sportsdataio_goalies") is None
    assert rec.write_observation({"sport": "nfl", "source": "sportsdataio_goalies", "status": "complete",
                                  "endpoint": "https://example.invalid/goalies", "fetched_at": t},
                                 [{**name_only, "kind": "plays_for"}]).written


def test_6c_an_aware_stamp_is_stored_as_naive_utc():
    _migrate()
    et = timezone(timedelta(hours=-5))
    r = _load(datetime(2026, 11, 5, 4, tzinfo=et), _chart(datetime(2026, 11, 5, 2, tzinfo=et),
                                                          _depth("A", "00-1", 1, datetime(2026, 11, 5, 2, tzinfo=et))))
    with _ro() as s:
        rows = rec.load_rows(s, "nfl")
    assert len(rows) == 6 and {(row.recorded_at, row.source_stamp, row.observation_id) for row in rows} == {
        (datetime(2026, 11, 5, 9), datetime(2026, 11, 5, 7), r.observation_id)}


# ---- 6(b) the as-of query under each clock --------------------------------------------------------------------------------

S0 = datetime(2026, 10, 20, 7)                 # C's source stamp: weeks before the first fetch (backfilled)
S1, T1 = datetime(2026, 11, 5, 7), datetime(2026, 11, 5, 9)
T2 = datetime(2026, 11, 6, 8, 45)              # the missed fetch's scheduled time
S3, T3 = datetime(2026, 11, 7, 7), datetime(2026, 11, 7, 9)
T4 = datetime(2026, 11, 8, 9)


def _history_b():
    """Small full charts (262 item 1). obs1 at T1: QB1 = A, QB2 = X. obs2: the 11-06 fetch missed. obs3 at T3: QB1 = B
    (the flip), QB2 = X. obs4 at T4: the chart stamped S0, weeks before T1 (backfilled rows): QB1 = B, QB2 = C."""
    _migrate()
    _load(T1, _chart(S1, _depth("A Starter", "00-A", 1, S1), _depth("X Backup", "00-X", 2, S1)))
    rec.write_observation(_nfl(None, status="missed", scheduled_at=T2))
    _load(T3, _chart(S3, _depth("B Starter", "00-B", 1, S3), _depth("X Backup", "00-X", 2, S3)))
    _load(T4, _chart(S0, _depth("B Starter", "00-B", 1, S0), _depth("C Backup", "00-C", 2, S0)))


def _names(facts):
    """The named players in force (the small full charts' filler rows left out)."""
    return sorted(f.interval.first.player_name for f in facts if not f.interval.first.player_name.startswith("Fill"))


def test_6b_the_recorded_clock_never_returns_the_backfilled_row_before_its_fetch():
    _history_b()
    with _ro() as s:
        assert _names(rec.as_of(s, "nfl", T1 - timedelta(seconds=1))) == []
        assert _names(rec.as_of(s, "nfl", T1)) == ["A Starter", "X Backup"]
        assert _names(rec.as_of(s, "nfl", T3 - timedelta(seconds=1))) == ["A Starter", "X Backup"]
        assert _names(rec.as_of(s, "nfl", T3)) == ["B Starter", "X Backup"]      # the flip
        for t in (S0, S1, T1, T2, T3, T4 - timedelta(seconds=1)):
            assert "C Backup" not in _names(rec.as_of(s, "nfl", t))             # never before its fetch
        after = rec.as_of(s, "nfl", T4)
        assert _names(after) == ["B Starter", "C Backup"]
        c = next(f for f in after if f.interval.first.player_name == "C Backup")
        assert c.backfilled is True and c.interval.first.recorded_at == T4 and c.interval.first.source_stamp == S0
        assert next(f for f in after if f.interval.first.player_name == "B Starter").backfilled is False   # T3: fresh
        assert len(rec.as_of(s, "nfl", T4)) == 7                                 # and the chart's 5 filler rows
        line = rec.fact_line(c)
        assert "BACKFILLED" in line and "recorded_at 2026-11-08T09:00:00Z" in line
        assert "source_stamp 2026-10-20T07:00:00Z" in line and f"<{NFLVERSE}>" in line


def test_6b_the_source_clock_reads_the_source_stamp_and_labels_the_backfill():
    _history_b()
    with _ro() as s:
        assert _names(rec.as_of(s, "nfl", S0 - timedelta(seconds=1), clock="source")) == []
        early = rec.as_of(s, "nfl", S0, clock="source")                         # the S0 chart, read first
        assert _names(early) == ["B Starter", "C Backup"]
        assert next(f for f in early if f.interval.first.player_name == "C Backup").backfilled is True
        assert _names(rec.as_of(s, "nfl", S1, clock="source")) == ["A Starter", "X Backup"]
        assert _names(rec.as_of(s, "nfl", S3, clock="source")) == ["B Starter", "X Backup"]


def test_6b_the_missed_poll_changes_nothing_and_every_fact_carries_both_stamps():
    _history_b()
    with _ro() as s:
        before = rec.as_of(s, "nfl", T2 - timedelta(minutes=1))
        after = rec.as_of(s, "nfl", T2 + timedelta(hours=1))
        assert [f.interval.first.id for f in before] == [f.interval.first.id for f in after]
        assert _names(before) == ["A Starter", "X Backup"] and len(before) == 7
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
        _load(t, _chart(t - timedelta(hours=2), _depth(f"{who} QB", f"00-{who}", 1, t - timedelta(hours=2))))
    with _ro() as s:
        ivs = _bal_qb(rec.derive(rec.load_rows(s, "nfl")))
        hist = _bal_qb(rec.history(s, "nfl", days[-1]))
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
    t1 = t + timedelta(days=1)
    _load(t, _chart(t, _depth("A QB", "00-A", 1, t), _depth("X QB", "00-X", 2, t)))
    _load(t1, _chart(t1, _depth("X QB", "00-X", 1, t1), _depth("A QB", "00-A", 2, t1)))
    rec.write_observation(_nhl("T+20", KO + timedelta(minutes=21)),
                          [_goalie(1, "G One", 1, "home", kind="eventual_starter"),
                           _goalie(2, "G Two", 1, "home", kind="eventual_starter")])
    with _ro() as s:
        nfl = [iv for iv in rec.derive(rec.load_rows(s, "nfl")) if iv.first.player_name == "A QB"]
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
        _load(t, _chart(t - timedelta(hours=2), _depth("A QB", "00-A", 1, t - timedelta(hours=2))))
    with _ro() as s:
        ivs = rec.derive(rec.load_rows(s, "nfl"))
    (iv,) = _bal_qb(ivs)
    assert iv.restated == 1 and iv.end is None
    assert len(ivs) == 6 and all(x.restated == 1 and x.end is None for x in ivs)       # the whole chart, restated


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
    assert lines[0] == "AVAILABILITY · nfl · as of 2026-11-08T09:00:00Z · clock recorded · 7 fact(s) in force"
    assert any("B Starter" in ln for ln in lines) and any("C Backup" in ln and "BACKFILLED" in ln for ln in lines)
    assert lines[-1] == "Depth charts: nflverse (CC BY 4.0)"
    h = _cli("--sport", "nfl", "--as-of", "2026-11-08T04:00:00-05:00", "--history", "--team", "BAL")
    assert h.exit_code == 0, h.output
    assert "12 assertion(s) · --history" in h.output.splitlines()[0] and "team BAL" in h.output     # 3 loads x 4
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
    assert "7 fact(s) in force" in r.output and "B Starter" in r.output


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
    stamp = datetime(2026, 11, 5, 7)
    _load(datetime(2026, 11, 5, 9), _chart(stamp, _depth("A", "00-1", 1, stamp, team="HAW", team_id=other_id),
                                           team="HAW", team_id=other_id))
    con = sqlite3.connect(fresh_db, isolation_level=None)
    try:
        p = tm.plan(con)
        assert "availability_assertions.team_id" in p["refs"] and not p["unknown_refs"]
        res = tm.apply(con, "T", [(keep_id, other_id)])
        assert not res["merged"] and "append-only" in res["refused"][0]["why"], res
        assert con.execute("SELECT DISTINCT team_id FROM availability_assertions WHERE source_team = 'HAW'"
                           ).fetchall() == [(other_id,)]
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
    _load(datetime(2026, 11, 5, 9), _chart(datetime(2026, 11, 5, 7), _depth("A", "00-1", 1,
                                                                       datetime(2026, 11, 5, 7))))
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
    names = [x["lane"] for x in doc["lanes"]]       # appended after pl-availability; later lanes append after it (#832)
    assert names.index("availability-record") == names.index("pl-availability") + 1
    assert "competitions" not in ln and ln["moved"] == [] and ln["earliest_live"] is None
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
    s20, s2, s3, s30 = (f1 - timedelta(days=20), f1 - timedelta(hours=2), f2 - timedelta(hours=2),
                        f1 - timedelta(days=30))
    _load(f1, _chart(s20, _depth("A QB", "00-A", 1, s20)) + _chart(s2, _depth("A QB", "00-A", 1, s2)))  # two loads
    _load(f2, _chart(s3, _depth("A QB", "00-A", 1, s3)))
    _load(f2 + timedelta(hours=1), _chart(s30, _depth("A QB", "00-A", 1, s30), _depth("D Old", "00-D", 3, s30)))
    with _ro() as s:
        facts = rec.as_of(s, "nfl", f2 + timedelta(hours=2))
    a = next(f for f in facts if f.interval.first.player_name == "A QB")
    assert len([f for f in facts if f.interval.first.player_name == "A QB"]) == 1
    assert a.interval.restated == 3 and rec.backfilled(a.interval.first) is True    # the last chart restates A too
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
    s1, s2 = d1 - timedelta(hours=2), d2 - timedelta(hours=2)
    _load(d1, _chart(s1, _depth("A QB", "00-A", 1, s1), _depth("B QB", "00-B", 2, s1)), status="partial")
    _load(d2, _chart(s2, _depth("B QB", "00-B", 1, s2, team_id=1),
                     {**_depth("A QB", "00-A", 2, s2, team_id=1), "player_id": 501}, team_id=1))
    with _ro() as s:
        facts = _bal_qb(rec.as_of(s, "nfl", d2 + timedelta(hours=1)))
        ivs = rec.derive(rec.load_rows(s, "nfl"))
    assert sorted((f.interval.first.player_name, f.interval.first.attrs["pos_rank"], f.interval.first.team_id)
                  for f in facts) == [("A QB", 2, 1), ("B QB", 1, 1)]
    assert [iv.why_closed for iv in ivs if iv.end is not None] == ["asserted differently"] * 2
    assert any("player #501" in rec.fact_line(f) and "team #1" in rec.fact_line(f) for f in facts)


def test_a_late_assertion_on_an_older_observation_is_refused_by_the_file():
    """No backdating (item 5): only the observation just inserted receives assertions, whoever writes."""
    _migrate()
    t = datetime(2026, 11, 8, 9)
    first = _load(t, _chart(t - timedelta(hours=2), _depth("A", "00-1", 1, t - timedelta(hours=2))))
    rec.write_observation(_nfl(t + timedelta(days=1)), [])
    with pytest.raises(IntegrityError, match="only the newest observation receives assertions"):
        with _engine().begin() as c:
            c.execute(text("INSERT INTO availability_assertions (observation_id, sport, kind, source_player_id, "
                           "player_name, source_team, recorded_at) VALUES (:o, 'NFL', 'depth_rank', 'g9', 'Z', 'BAL', "
                           "'2026-11-08 09:00:00.000000')"), {"o": first.observation_id})
    assert _counts() == (2, 6)
    r = _load(t + timedelta(days=2), _chart(t + timedelta(days=2), _depth("B", "00-2", 1, t + timedelta(days=2))))
    assert r.written and _counts() == (3, 12)                    # the writer's own path is unchanged


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
    assert out1.count("+ Created trigger") == 8 and "· Kept trigger" not in out1
    assert "+ Creating availability_observations..." in out1 and "+ Creating availability_assertions..." in out1
    assert f"+ Created index {RECORDED_IX}" in out1 and "· Kept index" not in out1
    out2 = _migrate(capsys)
    assert out2.count("· Kept trigger") == 8 and "+ Created trigger" not in out2
    assert f"· Kept index {RECORDED_IX}" in out2 and "+ Created index" not in out2
    eng.dispose()


# ---- the recorded-clock index (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 4) -----------------------------------
RECORDED_IX = "ix_avail_asr_sport_recorded"


def _indexes(eng) -> set:
    with eng.connect() as c:
        return {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name IN "
                                             "('availability_observations', 'availability_assertions')"))}


def _plan(eng, clock: str, t: datetime) -> list[str]:
    """EXPLAIN QUERY PLAN of the bounded read's partition SELECT (rec._select + rec._clock_bound, as _partitions
    issues it), on the engine's file."""
    q = rec._select("nfl").where(rec._clock_bound(clock, t))
    sql = q.compile(eng, compile_kwargs={"literal_binds": True})
    with eng.connect() as c:
        return [r[3] for r in c.execute(text("EXPLAIN QUERY PLAN " + str(sql)))]


def test_262_4_the_mapped_model_declares_the_recorded_clock_index_and_a_fresh_store_has_it(capsys):
    """262 item 4: "AN INDEX IS ALLOWED in this PR if the query needs one". A fresh store (init_db: the mapped models)
    has it, and the migration on it keeps it, naming it; the recorded-clock read uses it, the source clock its own."""
    from src.db.schema import AvailabilityAssertion
    ix = next(i for i in AvailabilityAssertion.__table__.indexes if i.name == RECORDED_IX)
    assert [c.name for c in ix.columns] == ["sport", "recorded_at"] and not ix.unique
    assert RECORDED_IX in _indexes(_engine())
    out = _migrate(capsys)
    assert f"· Kept index {RECORDED_IX}" in out and "+ Created index" not in out
    assert "indexes on the record (11 of 11 declared)" in out   # 10 + #835 item 2's poll key (258 item 2(2))
    t = datetime(2026, 11, 5, 12)
    assert any(f"USING INDEX {RECORDED_IX} (sport=? AND recorded_at" in ln for ln in _plan(_engine(), "recorded", t))
    assert any("USING INDEX ix_avail_asr_sport_stamp (sport=? AND source_stamp" in ln
               for ln in _plan(_engine(), "source", t))


def test_262_4_a_store_migrated_before_the_index_gains_it_on_a_rerun_and_the_rerun_is_idempotent(
        tmp_path, monkeypatch, capsys):
    """262 item 4: the index "joins #831's migration (additive, idempotent, the same marker file or its own)". A store
    migrated by #831's migrate_availability_record.py (the tables, the triggers and the marker, no recorded-clock
    index), holding rows: a rerun creates the index (CREATE INDEX IF NOT EXISTS), keeps the marker as written (its
    migrated_at unchanged), the triggers and every row; the recorded-clock read then uses it; a third run keeps it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import AvailabilityAssertion, Base
    eng = create_engine(f"sqlite:///{tmp_path / 'm831.db'}", future=True)
    Base.metadata.create_all(eng, tables=[t for t in Base.metadata.sorted_tables if t.name not in rec.TABLES])
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    tbl = AvailabilityAssertion.__table__
    with monkeypatch.context() as m:                                  # #831's model: no recorded-clock index
        m.setattr(tbl, "indexes", {i for i in tbl.indexes if i.name != RECORDED_IX})
        out0 = _migrate(capsys)
    assert RECORDED_IX not in out0 and RECORDED_IX not in _indexes(eng)
    t0 = datetime(2026, 11, 5, 9)
    _load(t0, _chart(t0 - timedelta(hours=2), _depth("A Starter", "00-1", 1, t0 - timedelta(hours=2))))
    with eng.connect() as c:
        marker = c.execute(text(f"SELECT script, migrated_at FROM {rec.MIGRATION_MARKER}")).one()
    counts = _counts()
    assert counts == (1, 6)
    assert not any(RECORDED_IX in ln for ln in _plan(eng, "recorded", t0))     # the sport's rows walked
    out1 = _migrate(capsys)
    assert f"+ Created index {RECORDED_IX}" in out1 and out1.count("+ Created index") == 1
    assert "· Kept migration marker availability_record_migration" in out1
    assert out1.count("· Kept trigger") == 8 and "+ Created trigger" not in out1
    assert RECORDED_IX in _indexes(eng) and _counts() == counts
    with eng.connect() as c:
        assert c.execute(text(f"SELECT script, migrated_at FROM {rec.MIGRATION_MARKER}")).one() == marker
        assert c.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    assert any(f"USING INDEX {RECORDED_IX} (sport=? AND recorded_at" in ln for ln in _plan(eng, "recorded", t0))
    with _ro() as s:
        assert len(rec.as_of(s, "nfl", t0)) == 6
    out2 = _migrate(capsys)
    assert f"· Kept index {RECORDED_IX}" in out2 and "+ Created index" not in out2 and _counts() == counts
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
    b_lines = [ln for ln in h.output.splitlines() if "B Starter" in ln]           # a history line labels its own row
    assert len(b_lines) == 2 and [("BACKFILLED" in ln) for ln in b_lines] == [False, True]   # T3's fresh, T4's S0
    n = _cli("--sport", "nhl", "--as-of", "2026-11-10T01:00:00Z", "--history")
    assert n.exit_code == 0 and any("G One" in ln and "POST HOC" in ln for ln in n.output.splitlines()), n.output


# ---- Codex on #831, round 1: kickoff from the match, the latest member's mapping, the source's game id ----------------

def _match_row(mid: int, kickoff: datetime) -> None:
    """A stored match (the synthetic minimum of matches' NOT NULL columns): its utc_date is the kickoff a league-wide
    fact is compared to."""
    with _engine().begin() as c:
        c.execute(text("INSERT INTO matches (id, sport, competition_id, season, utc_date, status, home_team_id, "
                       "away_team_id, external_ids) VALUES (:i, 'NHL', 1, '2026', :k, 'SCHEDULED', 1, 2, '{}')"),
                  {"i": mid, "k": kickoff.strftime("%Y-%m-%d %H:%M:%S.%f")})


def test_a_league_wide_per_game_fact_recorded_after_its_kickoff_is_post_hoc():
    """A league-wide observation stores no kickoff (kickoff_at NULL). A per-game fact on it names our match 77: the
    kickoff our matches table stores for 77 decides POST HOC. A fact whose match is unmapped, with no kickoff stored
    anywhere, reads "kickoff unknown", never pregame (law 4)."""
    _migrate()
    _match_row(77, KO)
    lw = {"sport": "nhl", "source": "sportsdataio_goalies", "endpoint": "https://example.test/goalies/2026-11-09",
          "status": "partial"}
    rec.write_observation({**lw, "fetched_at": KO - timedelta(hours=3)},
                          [_goalie(1, "G Pre", 1, "home", gid=None)])
    rec.write_observation({**lw, "fetched_at": KO + timedelta(minutes=5)},
                          [_goalie(2, "G Late", 2, "away", gid=None),
                           _goalie(3, "G Nowhere", None, "home", match_id=None, source_team="UTA", gid=None)])
    with _ro() as s:
        facts = {f.interval.first.player_name: f for f in rec.as_of(s, "nhl", KO + timedelta(hours=1))}
        hist = {r.player_name: (r, iv) for r, iv in rec.history(s, "nhl", KO + timedelta(hours=1))}
    assert (facts["G Pre"].post_hoc, facts["G Late"].post_hoc, facts["G Nowhere"].post_hoc) == (False, True, None)
    assert "POST HOC" in rec.fact_line(facts["G Late"]) and "POST HOC" in rec.history_line(*hist["G Late"])
    assert "POST HOC" not in rec.fact_line(facts["G Pre"]) and "kickoff unknown" not in rec.fact_line(facts["G Pre"])
    for line in (rec.fact_line(facts["G Nowhere"]), rec.history_line(*hist["G Nowhere"])):
        assert "kickoff unknown" in line and "POST HOC" not in line


def test_a_fact_restated_after_its_team_maps_is_found_and_shown_by_our_id():
    """Day 1 partial: BAL unmapped (team_id NULL). Day 2 complete: the same fact restated with BAL mapped to team 1.
    One interval; --team 1 finds it and prints team #1 (its latest member); --history lists both rows under --team 1,
    the first as recorded with "mapped now"."""
    _migrate()
    d1, d2 = datetime(2026, 11, 5, 9), datetime(2026, 11, 6, 9)
    s1, s2 = d1 - timedelta(hours=2), d2 - timedelta(hours=2)
    _load(d1, _chart(s1, _depth("A QB", "00-A", 1, s1)), status="partial")
    _load(d2, _chart(s2, _depth("A QB", "00-A", 1, s2, team_id=1), team_id=1))
    with _ro() as s:
        by_id = rec.as_of(s, "nfl", d2 + timedelta(hours=1), team="1")
        assert len(by_id) == 3 and {f.interval.first.source_team for f in by_id} == {"BAL"}   # BAL's chart, not KC's
        (f,) = _bal_qb(by_id)
        assert len(rec.as_of(s, "nfl", d2 + timedelta(hours=1), team="BAL")) == 3      # the source text too
        hist = _bal_qb(rec.history(s, "nfl", d2 + timedelta(hours=1), team="1"))
    assert f.interval.restated == 1 and f.interval.first.team_id is None and f.interval.start == d1
    line = rec.fact_line(f)
    assert "team #1" in line and "UNMAPPED ('BAL')" not in line and "recorded_at 2026-11-05T09:00:00Z" in line
    assert [r.recorded_at for r, _ in hist] == [d1, d2]
    first = rec.history_line(*hist[0])
    assert "team UNMAPPED ('BAL')" in first and "mapped now: " in first and "team #1" in first


def test_a_mapped_fact_restated_unmapped_is_still_found_and_shown_by_our_id():
    """The reverse direction. Day 1 complete: BAL mapped to team 1. Day 2 partial (item 6(c): a team unmapped): the
    same fact restated with team_id NULL. And an NHL poll at T-60 on match 77, restated at T-30 by a partial poll whose
    match did not map. Each is one interval; --team 1 and --match-id 77 still find it, and its line prints our ids
    (each from the latest member that carries one), never UNMAPPED."""
    _migrate()
    d1, d2 = datetime(2026, 11, 5, 9), datetime(2026, 11, 6, 9)
    s1, s2 = d1 - timedelta(hours=2), d2 - timedelta(hours=2)
    _load(d1, _chart(s1, _depth("A QB", "00-A", 1, s1, team_id=1), team_id=1))
    _load(d2, _chart(s2, _depth("A QB", "00-A", 1, s2)), status="partial")
    _match_row(77, KO)
    rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60)), [_goalie(1, "G One", 1, "home")])
    rec.write_observation(_nhl("T-30", KO - timedelta(minutes=30), status="partial", match_id=None),
                          [_goalie(1, "G One", 1, "home", match_id=None)])
    with _ro() as s:
        (nf,) = _bal_qb(rec.as_of(s, "nfl", d2 + timedelta(hours=1), team="1"))
        nhist = _bal_qb(rec.history(s, "nfl", d2 + timedelta(hours=1), team="1"))
        (hf,) = rec.as_of(s, "nhl", KO - timedelta(minutes=20), match_id=77)
        hhist = rec.history(s, "nhl", KO - timedelta(minutes=20), match_id=77)
    assert nf.interval.restated == 1 and nf.interval.last.team_id is None
    assert "team #1" in rec.fact_line(nf) and "UNMAPPED ('BAL')" not in rec.fact_line(nf)
    assert [r.recorded_at for r, _ in nhist] == [d1, d2]
    second = rec.history_line(*nhist[1])
    assert "team UNMAPPED ('BAL')" in second and "mapped now: " in second and "team #1" in second
    assert hf.interval.restated == 1 and hf.interval.last.match_id is None
    assert "match #77" in rec.fact_line(hf) and "match UNMAPPED" not in rec.fact_line(hf)
    assert len(hhist) == 2


def test_262_4_as_ofs_summary_carries_the_latest_ids_its_members_carry():
    """Addendum 262 item 4 (the unfiltered as_of's memory): as_of keeps a Summary in place of an interval's members.
    One league-wide goalie fact restated over four fetches while our ids move: team 1, then 11, then none; player 5,
    then none, then 6; match none, then 501 (its kickoff already past), then 502 (re-mapped, a day later), then none.
    as_of names what the latest member carrying each id names (team 11, player 6, match 502 and 502's kickoff, so not
    POST HOC), exactly as the full derivation's members give it, and keeps no member rows."""
    _migrate()
    _match_row(501, KO - timedelta(hours=4))
    _match_row(502, KO + timedelta(days=1))
    ep = "https://example.test/goalies/2026-11-09"
    for at, team_id, pid, mid in ((KO - timedelta(hours=3), 1, 5, None), (KO - timedelta(hours=2), 11, None, 501),
                                  (KO - timedelta(minutes=90), None, 6, 502),
                                  (KO + timedelta(hours=1), None, None, None)):
        g = {**_goalie(9, "G Moves", team_id, "home", match_id=mid, gid="2025020999"), "player_id": pid,
             "source_team": "HOM"}
        rec.write_observation({"sport": "nhl", "source": "sportsdataio_goalies", "endpoint": ep, "status": "complete",
                               "fetched_at": at}, [g])
    t = KO + timedelta(hours=2)
    with _ro() as s:
        (f,) = rec.as_of(s, "nhl", t)
        (ref,) = _reference_as_of(_reference_rows(s, "nhl"), t, "recorded")
    now = rec.mapped_now(f.interval)
    assert f.interval.members is None and f.interval.restated == 3
    assert (now.team_id, now.player_id, now.match_id, now.match_kickoff) == (11, 6, 502, KO + timedelta(days=1))
    assert f.post_hoc is False and "match #502" in rec.fact_line(f) and "POST HOC" not in rec.fact_line(f)
    assert _fact_sig(f) == _fact_sig(ref) and len(ref.interval.members) == 4


def test_post_hoc_reads_the_current_kickoff_where_none_was_stored_at_fetch():
    """Spec section 4: a league-wide fact has no kickoff stored at fetch, so POST HOC reads matches.utc_date as it stands
    at READ time, not as of the instant. Pinned: a re-date after T changes the same as_of(T)'s label (section 7 (n))."""
    _migrate()
    _match_row(77, KO)
    lw = {"sport": "nhl", "source": "sportsdataio_goalies", "endpoint": "https://example.test/goalies/2026-11-09",
          "status": "complete", "fetched_at": KO + timedelta(minutes=5)}
    rec.write_observation(lw, [_goalie(2, "G Late", 2, "away", gid=None)])
    t = KO + timedelta(minutes=10)
    with _ro() as s:
        before = [f.post_hoc for f in rec.as_of(s, "nhl", t)]
    with _engine().begin() as c:     # the tmp DB's match is re-dated a day later (a postponement)
        c.execute(text("UPDATE matches SET utc_date = :k WHERE id = 77"),
                  {"k": (KO + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S.%f")})
    with _ro() as s:
        after = [f.post_hoc for f in rec.as_of(s, "nhl", t)]
    assert (before, after) == ([True], [False])


def test_a_per_game_fact_restated_after_its_match_maps_is_one_fact_and_its_slot_closes():
    """T-60: G One projected for game 2025020123, our match not yet mapped (match_id NULL). T-30: the same fact, the
    match now mapped to 77. T-0: G Two projected for the same side. Keyed on the source's game id, T-30 restates T-60
    and T-0 closes it: one fact in force at each instant, never the stale unmapped one beside the mapped one."""
    _migrate()
    rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60), status="partial", match_id=None),
                          [_goalie(1, "G One", 1, "home", match_id=None)])
    rec.write_observation(_nhl("T-30", KO - timedelta(minutes=30)), [_goalie(1, "G One", 1, "home")])
    with _ro() as s:
        mid = rec.as_of(s, "nhl", KO - timedelta(minutes=20))
        by_match = rec.as_of(s, "nhl", KO - timedelta(minutes=20), match_id=77)
    assert [(f.interval.first.player_name, f.interval.restated, f.interval.start) for f in mid] == [
        ("G One", 1, KO - timedelta(minutes=60))]
    assert [f.interval.first.id for f in by_match] == [mid[0].interval.first.id]
    assert "match #77" in rec.fact_line(mid[0])
    rec.write_observation(_nhl("T-0", KO), [_goalie(2, "G Two", 1, "home")])
    with _ro() as s:
        now = rec.as_of(s, "nhl", KO + timedelta(minutes=1))
        ivs = rec.derive(rec.load_rows(s, "nhl"))
    assert _names(now) == ["G Two"]
    assert [(iv.first.player_name, iv.end, iv.why_closed) for iv in ivs] == [
        ("G One", KO, "slot asserted to someone else"), ("G Two", None, None)]


def test_the_writer_requires_the_source_game_id_on_an_nhl_per_game_fact():
    """nhl_api_landing's per-game facts carry attrs.source_match_id (the NHL gameId), stored as text."""
    _migrate()
    for gid in (None, "", True):
        with pytest.raises(rec.Refused, match="carries attrs.source_match_id"):
            rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60)), [_goalie(1, "G", 1, "home", gid=gid)])
    assert _counts() == (0, 0)
    rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60)), [_goalie(1, "G", 1, "home", gid=2025020123)])
    with _ro() as s:
        (row,) = rec.load_rows(s, "nhl")
    assert row.attrs["source_match_id"] == GID


# ---- dedupe-matches' record line (ARCHITECT 2026-11-04 15:45 ET, addendum 254 item 2(4)) -----------------------------
# Verbatim: "our match_id is read as recorded; dedupe-matches prints one receipt line, "record rows on retired match
# ids: N", and rewrites nothing in the record." N counts both tables' rows on the ids the run retires (a dry run: the
# ids it would retire); a DB without the record's tables prints "n/a (availability tables absent)", never a 0.

DD_CODE = "AVD"
DD_KO = datetime(2091, 10, 2, 0, 0)
DD_SRC = "api_american_football"


def _dd_world():
    """A twin pair under the dedupe's rule (same home and away, same kickoff, different source ids): keeper (the
    older row) and newer (the row a merge retires), and a third game the run never touches."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        c = Competition(sport=Sport.NHL, code=DD_CODE, name=DD_CODE, area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NHL, name=f"{DD_CODE} T{i}", external_ids={DD_SRC: f"t{i}"}) for i in range(4)]
        s.add(c)
        s.add_all(ts)
        s.flush()

        def m(h, a, sid, **kw):
            row = Match(sport=Sport.NHL, competition_id=c.id, season="2091", utc_date=DD_KO, status=kw.pop(
                "status", MatchStatus.SCHEDULED), home_team_id=ts[h].id, away_team_id=ts[a].id,
                external_ids={DD_SRC: sid}, **kw)
            s.add(row)
            s.flush()
            return row.id
        keeper = m(0, 1, "100")
        newer = m(0, 1, "9100", status=MatchStatus.FINISHED, home_score=3, away_score=1)
        other = m(2, 3, "500")
    return keeper, newer, other


def _dd_record(keeper, newer, other):
    """Record rows: a per-game observation and its fact on the newer id (2 rows the line counts), one on the keeper
    and one on the untouched game (not counted), and a league-wide nflverse fetch (match_id NULL, not counted)."""
    _migrate()
    rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60), match_id=newer),
                          [_goalie(1, "G One", None, "home", match_id=newer, source_team="AAA")])
    rec.write_observation(_nhl("T-30", KO - timedelta(minutes=30), match_id=keeper), [])
    rec.write_observation(_nhl("T-0", KO, match_id=other), [])
    _load(datetime(2026, 11, 5, 9), _chart(datetime(2026, 11, 5, 7), _depth("A", "00-1", 1,
                                                                       datetime(2026, 11, 5, 7))))


def _record_bytes(path) -> bytes:
    """Every row of both record tables, in id order, as bytes: the byte-identity a rewrite would break."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        return repr([con.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in rec.TABLES]).encode()
    finally:
        con.close()


def _dedupe_cli(monkeypatch, *args, code=DD_CODE):
    from click.testing import CliRunner

    import cli as climod
    monkeypatch.setattr(climod, "_verify_backup", lambda *a, **k: "verified (test)")   # law 5's check: not under test
    return CliRunner().invoke(climod.cli, ["dedupe-matches", "--competition", code, *args])


def _record_lines(out: str) -> list[str]:
    return [ln.strip() for ln in out.splitlines() if ln.strip().startswith("record rows on retired match ids")]


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_dedupe_matches_prints_the_record_rows_on_the_retired_ids(fresh_db, monkeypatch, apply):
    keeper, newer, other = _dd_world()
    _dd_record(keeper, newer, other)
    before = _record_bytes(fresh_db)
    r = _dedupe_cli(monkeypatch, *(["--apply", "--backup", "x.backup"] if apply else []))
    assert r.exit_code == 0, r.output
    assert _record_lines(r.output) == ["record rows on retired match ids: 2"], r.output
    assert _record_bytes(fresh_db) == before                       # the record: nothing rewritten, dry run or apply
    con = sqlite3.connect(fresh_db)
    try:
        left = sorted(x for (x,) in con.execute("SELECT id FROM matches"))
    finally:
        con.close()
    assert left == (sorted([keeper, other]) if apply else sorted([keeper, newer, other]))


def test_dedupe_matches_record_rows_are_byte_identical_after_an_apply(fresh_db, monkeypatch):
    """The ruling's "rewrites nothing": every row of both tables, every column, the same bytes after --apply; the
    rows on the retired id keep that id as recorded (no foreign key re-points them)."""
    keeper, newer, other = _dd_world()
    _dd_record(keeper, newer, other)
    before = _record_bytes(fresh_db)
    r = _dedupe_cli(monkeypatch, "--apply", "--backup", "x.backup")
    assert r.exit_code == 0 and "merged 1" in r.output, r.output
    assert _record_bytes(fresh_db) == before
    con = sqlite3.connect(fresh_db)
    try:
        assert con.execute("SELECT COUNT(*) FROM availability_observations WHERE match_id = ?", (newer,)).fetchone() \
            == (1,)
        assert con.execute("SELECT COUNT(*) FROM availability_assertions WHERE match_id = ?", (newer,)).fetchone() \
            == (1,)
        assert con.execute("SELECT COUNT(*) FROM matches WHERE id = ?", (newer,)).fetchone() == (0,)
    finally:
        con.close()


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_dedupe_matches_labels_the_record_line_n_a_where_the_record_tables_are_absent(tmp_path, monkeypatch, apply):
    """A DB the migration has not reached (no availability tables): the line says n/a and why, never a 0 it did not
    count (law 4); the dedupe itself runs as before."""
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Base
    path = tmp_path / "pre_migration.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng, tables=[t for t in Base.metadata.sorted_tables if t.name not in rec.TABLES])
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    try:
        assert not set(rec.TABLES) & set(inspect(eng).get_table_names())
        keeper, newer, _ = _dd_world()
        r = _dedupe_cli(monkeypatch, *(["--apply", "--backup", "x.backup"] if apply else []))
        assert r.exit_code == 0, r.output
        assert _record_lines(r.output) == ["record rows on retired match ids: n/a (availability tables absent)"]
        assert ("merged 1" in r.output) is apply
        assert not set(rec.TABLES) & set(inspect(eng).get_table_names())     # read-only: nothing created
    finally:
        eng.dispose()


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_dedupe_matches_orphans_counts_the_record_rows_on_the_merge_it_retires(fresh_db, monkeypatch, apply):
    """--orphans: a merge retires the newer row (whichever is stale); a relink or an orphan mark retires no id. The
    stale row (sid 1, absent at the provider) and its live twin (sid 2) merge; the twin is the newer row."""
    from src.adapters.normalized import NormalizedMatch
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    from src.ingestion import match_dedupe as md
    from src.timeutil import utc_now_naive
    now = utc_now_naive().replace(microsecond=0)
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="AVO", name="AVO", area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"AVO T{i}", external_ids={DD_SRC: f"o{i}"}) for i in range(2)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        rows = [Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=when, status=MatchStatus.SCHEDULED,
                      home_team_id=ts[0].id, away_team_id=ts[1].id, external_ids={DD_SRC: sid})
                for sid, when in (("1", now + timedelta(days=2)), ("2", now + timedelta(days=2, hours=30)))]
        s.add_all(rows)
        s.flush()
        stale, twin = rows[0].id, rows[1].id
    live = NormalizedMatch(sport=Sport.NFL, competition_code="AVO", season="2026", utc_date=now + timedelta(days=3),
                           status=MatchStatus.SCHEDULED, home_team_source_id="o0", away_team_source_id="o1",
                           source=DD_SRC, source_id="2", status_raw="NS")

    class Provider:
        def get_game(self, sid, code):
            return (True, live) if sid == "2" else (False, None)

        def list_matches(self, *a, **k):
            return []
    _dd_record(stale, twin, stale)
    before = _record_bytes(fresh_db)
    r = md.orphans("AVO", Provider(), apply=False, now=now)               # the plan: the merge it would make
    assert r["retired_ids"] == [twin] and r["record_rows_on_retired"] == 2 and r["applied_counts"] == {}, r
    import src.adapters.api_american_football as aaf
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", Provider)
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "600000")
    out = _dedupe_cli(monkeypatch, "--orphans", *(["--apply", "--backup", "x.backup"] if apply else []), code="AVO")
    assert out.exit_code == 0, out.output
    assert _record_lines(out.output) == ["record rows on retired match ids: 2"], out.output
    assert ("applied {'merge': 1}" in out.output) is apply, out.output
    assert _record_bytes(fresh_db) == before


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_dedupe_matches_labels_the_record_line_n_a_where_the_tables_cannot_be_read(fresh_db, monkeypatch, apply):
    """The third form: a DB whose table list cannot be inspected (match_dedupe._live_tables returns None) prints
    "n/a (the live DB's tables could not be read)", never a count it did not make (law 4); the dedupe runs as before."""
    from src.ingestion import match_dedupe as md
    keeper, newer, other = _dd_world()
    _dd_record(keeper, newer, other)
    before = _record_bytes(fresh_db)
    monkeypatch.setattr(md, "_live_tables", lambda s: None)
    r = _dedupe_cli(monkeypatch, *(["--apply", "--backup", "x.backup"] if apply else []))
    assert r.exit_code == 0, r.output
    assert _record_lines(r.output) == ["record rows on retired match ids: n/a (the live DB's tables could not be read)"]
    assert ("merged 1" in r.output) is apply, r.output
    assert _record_bytes(fresh_db) == before


def test_dedupe_matches_record_line_leaves_a_refused_merge_out_of_the_apply_count(fresh_db, monkeypatch):
    """Two pairs: A, whose rows both hold a match_stats entry (a unique table), so merge() refuses it at apply; and B,
    which merges. Record rows: 2 on A's newer id, 1 on B's. The dry run counts the newer row of every planned pair (3:
    a refusal at apply is not known on a dry run); the apply counts only the merge it made (1)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStats, MatchStatus, Sport, Team
    with session_scope() as s:
        c = Competition(sport=Sport.NHL, code=DD_CODE, name=DD_CODE, area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NHL, name=f"{DD_CODE} T{i}", external_ids={DD_SRC: f"t{i}"}) for i in range(4)]
        s.add(c)
        s.add_all(ts)
        s.flush()

        def m(h, a, sid):
            row = Match(sport=Sport.NHL, competition_id=c.id, season="2091", utc_date=DD_KO,
                        status=MatchStatus.SCHEDULED, home_team_id=ts[h].id, away_team_id=ts[a].id,
                        external_ids={DD_SRC: sid})
            s.add(row)
            s.flush()
            return row.id
        a_keep, a_new = m(0, 1, "100"), m(0, 1, "9100")
        b_keep, b_new = m(2, 3, "200"), m(2, 3, "9200")
        s.add_all([MatchStats(match_id=mid, team_id=ts[0].id) for mid in (a_keep, a_new)])
    _migrate()
    rec.write_observation(_nhl("T-60", KO - timedelta(minutes=60), match_id=a_new),
                          [_goalie(1, "G One", None, "home", match_id=a_new, source_team="AAA")])
    rec.write_observation(_nhl("T-30", KO - timedelta(minutes=30), match_id=b_new), [])
    before = _record_bytes(fresh_db)

    dry = _dedupe_cli(monkeypatch)
    assert dry.exit_code == 0, dry.output
    assert _record_lines(dry.output) == ["record rows on retired match ids: 3"], dry.output

    applied = _dedupe_cli(monkeypatch, "--apply", "--backup", "x.backup")
    assert applied.exit_code == 0, applied.output
    assert "merged 1 · refused 1" in applied.output, applied.output
    assert f"REFUSED keeper {a_keep} / newer {a_new}: match_stats: both rows hold an entry" in applied.output
    assert _record_lines(applied.output) == ["record rows on retired match ids: 1"], applied.output
    assert _record_bytes(fresh_db) == before
    con = sqlite3.connect(fresh_db)
    try:
        left = sorted(x for (x,) in con.execute("SELECT id FROM matches"))
    finally:
        con.close()
    assert left == sorted([a_keep, a_new, b_keep])


# ---- the bounded read (Codex on #841, round 1): the answer of the full materialisation, from bounded reads ----------------

def _reference_rows(s, sport, kind=None):
    """HEAD 01a52c99's load_rows, verbatim in effect: every assertion of the sport (and kind) as ORM objects, the kickoff
    by a second query. The reference the bounded read is compared with."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    from src.db.schema import Match
    q = select(A, O).join(O, O.id == A.observation_id).where(A.sport == rec._sport(sport))
    if kind is not None:
        q = q.where(A.kind == kind)
    got = s.execute(q.order_by(A.id)).all()
    ids = sorted({a.match_id for a, _ in got if a.match_id is not None})
    kickoff = {mid: ko for i in range(0, len(ids), 500)
               for mid, ko in s.execute(select(Match.id, Match.utc_date).where(Match.id.in_(ids[i:i + 500]))).all()}
    return [rec.Row(a.id, a.observation_id, o.source, o.endpoint, o.poll_label, o.status, o.kickoff_at,
                    getattr(a.sport, "value", a.sport), a.kind, a.player_id, a.source_player_id, a.player_name,
                    a.team_id, a.source_team, a.match_id, a.attrs, a.source_stamp, a.recorded_at,
                    rec._naive_utc(kickoff.get(a.match_id), "matches.utc_date"), o.payload_sha256) for a, o in got]


def _reference_as_of(rows, t, clock, match_id=None, team=None):
    """HEAD's as_of over the reference rows: the whole derivation, cut in Python, the open intervals kept."""
    cut = [r for r in rows if rec.clock_of(r, clock) is not None and rec.clock_of(r, clock) <= t]
    return [rec.Fact(iv, rec.interval_backfilled(iv), rec.post_hoc(iv.first, iv), rec.live_since(iv))
            for iv in rec.derive(cut, clock) if iv.end is None and rec._keep(iv, match_id, team)]


def _reference_history(rows, t, clock, match_id=None, team=None):
    cut = [r for r in rows if rec.clock_of(r, clock) is not None and rec.clock_of(r, clock) <= t]
    member = {r.id: iv for iv in rec.derive(cut, clock) for r in iv.members}
    order = [r for _, g in rec._groups(cut, clock) for r in g]
    return [(r, member[r.id]) for r in order if rec._keep(member[r.id], match_id, team)]


def _iv_core(iv):
    return (iv.first.id, iv.last.id, iv.start, iv.end, iv.closed_by.id if iv.closed_by else None, iv.why_closed,
            iv.restated)


def _iv_sig(iv):
    """An interval with every member (history's, and the full derivation's)."""
    return _iv_core(iv) + (tuple(m.id for m in iv.members),)


def _fact_sig(f):
    """A fact as as_of answers it (addendum 262 item 4: as_of keeps a Summary, not the members): the interval without
    its members, the mapping it carries now (mapped_now: the latest ids and the match's stored kickoff, which the
    members gave), its labels and its printed line. The reference computes every one of them from the members."""
    now = rec.mapped_now(f.interval)
    return (_iv_core(f.interval), (now.player_id, now.team_id, now.match_id, now.match_kickoff), f.backfilled,
            f.post_hoc, f.live_since, rec.fact_line(f))


def _random_history(seed):
    """A SYNTHETIC randomized history written through the writer (its triggers): nflverse loads, each carrying its
    payload hash (addendum 262 item 1: the writer requires it), and nflverse failed fetches (no payload, no row);
    partial team groups (short ones, and groups that lost a refused row: attrs.rows_refused, 262 item 5), several
    loads per fetch, backfilled and fresh stamps, team ids mapped and unmapped between fetches, a depth group mixed
    with another kind in one load (not a load), NHL starters on two games (one with a stored match), plays_for
    moving players across teams, inactive and injury rows, and rows with no source stamp. Our ids change between the
    members of one fact now and then (a team id re-mapped, a player id given then changed, a game mapped to one match
    then to another with another kickoff): the latest member's ids are what as_of's Summary keeps (262 item 4)."""
    import random
    rnd = random.Random(seed)
    ids = random.Random(seed * 31)                       # the id changes draw apart: the history's shape is rnd's
    _migrate()
    _match_row(501, datetime(2026, 10, 20, 0, 0))
    _match_row(502, datetime(2026, 10, 9, 0, 0))
    teams = ["BAL", "KC", "BUF"]
    tid = {"BAL": 1, "KC": 2, "BUF": 3}
    pool = {t: [(f"00-{t}{i}" if i % 5 else None, f"Syn {t} {i}") for i in range(8)] for t in teams}
    chart = {t: list(range(6)) for t in teams}
    at = datetime(2026, 10, 1, 9)
    for _ in range(34):
        at += timedelta(hours=rnd.randint(4, 40))
        src = rnd.choices(["snap", "failed", "nhl", "sdio"], [6, 1, 2, 2])[0]
        rows = []
        if src == "failed":                                             # a fetch that raised: no payload, no row
            obs = {"sport": "nfl", "source": "nflverse_depth_charts", "endpoint": NFLVERSE, "status": "failed",
                   "fetched_at": at, "error": "ConnectionError: synthetic"}
        elif src == "snap":
            stamp = at - timedelta(hours=rnd.choice([1, 2, 30, 80]))
            for _ in range(rnd.choice([1, 1, 2, 3])):
                stamp += timedelta(minutes=rnd.randint(5, 600))
                if stamp > at:
                    break
                for t in teams:
                    if rnd.random() < 0.15:
                        continue                                        # a team absent from the load
                    if rnd.random() < 0.3:
                        i, j = rnd.sample(range(6), 2)
                        chart[t][i], chart[t][j] = chart[t][j], chart[t][i]
                    if rnd.random() < 0.15:
                        chart[t][rnd.randrange(6)] = rnd.choice([6, 7])
                    size = 2 if rnd.random() < 0.15 else rnd.choice([5, 6])   # a partial group now and then
                    refused = {rec.ROWS_REFUSED_ATTR: 1} if rnd.random() < 0.1 else {}   # a row refused (262 5)
                    for slot in range(size):
                        spid, name = pool[t][chart[t][slot]]
                        # 262 item 5: a snapshot source's row is never keyed by name (the writer refuses one with no
                        # id): the nflverse rows carry an id; the pool's name-only players stay for the other sources
                        spid = spid or f"00-{t}{chart[t][slot]}-NV"
                        rows.append({"kind": "depth_rank", "source_player_id": spid, "player_name": name,
                                     "source_team": t, "team_id": ((tid[t] + 10 if ids.random() < 0.15 else tid[t])
                                                                   if rnd.random() < 0.6 else None),
                                     "player_id": ids.choice([None, None, 900 + chart[t][slot],
                                                              950 + chart[t][slot]]),
                                     "source_stamp": stamp,
                                     "attrs": {"pos_grp": "Offense", "pos_abb": "QB" if slot < 2 else f"P{slot}",
                                               "pos_slot": "1" if slot < 2 else str(slot),
                                               "pos_rank": str(slot + 1) if slot < 2 else "1",
                                               "dt_raw": stamp.isoformat() + "Z", **refused}})
                if rnd.random() < 0.15:                                 # a mixed group: not a load
                    rows.append({"kind": "inactive", "source_player_id": "00-BAL1", "player_name": "Syn BAL 1",
                                 "source_team": "BAL", "source_stamp": stamp, "attrs": {"note": "mixed"}})
            obs = {"sport": "nfl", "source": "nflverse_depth_charts", "endpoint": NFLVERSE, "status": "complete",
                   "fetched_at": at, "payload_sha256": hashlib.sha256(str(at).encode()).hexdigest()}
        elif src == "nhl":
            m1 = rnd.choice([None, 501])                                # mapped to 502 from 10-12 on (re-mapped)
            for gid, mid in (("2025020001", 502 if m1 and at >= datetime(2026, 10, 12) else m1), ("2025020002", None)):
                for t in rnd.sample(teams, 2):
                    for kind in rnd.sample(["projected_starter", "confirmed_starter", "eventual_starter",
                                            "inactive"], 2):
                        spid, name = rnd.choice(pool[t][:3])
                        rows.append({"kind": kind, "source_player_id": spid, "player_name": name,
                                     "source_team": t if rnd.random() < 0.8 else None, "team_id": tid[t],
                                     "match_id": mid, "attrs": {"source_match_id": gid, "side": t},
                                     "source_stamp": None if rnd.random() < 0.5 else at - timedelta(minutes=5)})
            obs = {"sport": "nfl", "source": "nhl_api_landing", "endpoint": LANDING, "status": "complete",
                   "fetched_at": at, "kickoff_at": rnd.choice([None, at + timedelta(hours=3), at - timedelta(hours=1)])}
        else:
            for _ in range(rnd.randint(1, 4)):
                t = rnd.choice(teams)
                spid, name = rnd.choice(pool["BAL"][:4])                 # plays_for: one player, any team
                rows.append({"kind": rnd.choice(["plays_for", "plays_for", "injury_status"]),
                             "source_player_id": spid, "player_name": name, "source_team": t,
                             "team_id": tid[t] if rnd.random() < 0.5 else None,
                             "attrs": {"status": rnd.choice(["active", "out"])},
                             "source_stamp": None if rnd.random() < 0.3 else at - timedelta(hours=rnd.randint(0, 50))})
            obs = {"sport": "nfl", "source": "sportsdataio_goalies", "endpoint": "https://example.invalid/goalies",
                   "status": "complete", "fetched_at": at}
        rec.write_observation(obs, rows)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_bounded_read_equals_the_full_materialisation_on_randomized_histories(seed):
    """Codex on #841, round 1 (P1): as_of and history read bounded (the clock and the key in SQL, the derivation per
    partition). Every fact and every history line equals HEAD's full materialisation (every row loaded, one derive),
    interval by interval and in the same order, under both clocks, at every group's own instant and around it, with no
    key, a team (the source's text, our id) and a match, and per kind. as_of keeps a Summary in place of each
    interval's members (addendum 262 item 4): its facts are compared on the interval, the mapping it carries now and
    every label, each of which the reference reads from the members; history keeps the members and is compared on
    every member."""
    import random
    _random_history(seed)
    rnd = random.Random(seed * 7919)
    with _ro() as s:
        rows = _reference_rows(s, "nfl")
        assert len(rows) > 150 and {r.source for r in rows} == set(rec.SOURCES)
        whys = {iv.why_closed for clock in rec.CLOCKS for iv in rec.derive(rows, clock)}
        assert whys >= {"asserted differently", "slot asserted to someone else",
                        "not restated in its team's snapshot"}, whys     # every closing rule is exercised
        mixed = rec._mixed_groups(s, "nfl", "recorded", datetime(2027, 1, 1), None)
        assert mixed                                                  # a depth group that is not a load
        last, partial, refused_partial = {}, 0, 0
        for _, g in rec._groups(rows, "source"):
            if rec.snapshot_load(g) and (g[0].observation_id, g[0].source_stamp) not in mixed:
                counts: dict = {}
                refused = {rec.team_key(r) for r in g if (r.attrs or {}).get(rec.ROWS_REFUSED_ATTR)}
                for r in g:
                    counts[rec.team_key(r)] = counts.get(rec.team_key(r), 0) + 1
                partial += len(rec.guard_load(counts, last, refused))
                refused_partial += len(refused)
        assert partial and refused_partial                            # partial groups (both kinds), closing nothing
        # the partition holds every pair of rows a rule compares (fact key, slot key)
        for keyf in (rec.fact_key, rec.slot_key):
            parts: dict = {}
            for r in rows:
                if keyf(r) is not None:
                    parts.setdefault(keyf(r), set()).add(rec._partition(r))
            assert all(len(p) == 1 for p in parts.values())
        for clock in rec.CLOCKS:
            stamps = sorted({rec.clock_of(r, clock) for r in rows if rec.clock_of(r, clock) is not None})
            ts = ([stamps[0] - timedelta(days=1), stamps[-1] + timedelta(days=1),
                   datetime(9999, 12, 31, 23, 59, 59), datetime.max]               # the last date: no day after it
                  + [x + d for x in rnd.sample(stamps, 12) for d in (timedelta(0), timedelta(seconds=-1),
                                                                    timedelta(microseconds=1))])
            keys = [{}, {"team": "BAL"}, {"team": "2"}, {"team": "BUF"}, {"match_id": 501}]
            for t in ts:
                for key in keys:
                    new = rec.as_of(s, "nfl", t, clock, **key)
                    old = _reference_as_of(rows, t, clock, **key)
                    assert [_fact_sig(f) for f in new] == [_fact_sig(f) for f in old], (clock, t, key)
                    assert all(f.interval.members is None and f.interval.summary is not None for f in new)
                    assert all(f.interval.members for f in old)            # the reference labels from members
                    hn = rec.history(s, "nfl", t, clock, **key)
                    ho = _reference_history(rows, t, clock, **key)
                    assert [(r.id, _iv_sig(iv)) for r, iv in hn] == [(r.id, _iv_sig(iv)) for r, iv in ho]
            for kind in ("depth_rank", "plays_for", "projected_starter"):
                kr = _reference_rows(s, "nfl", kind)
                for t in rnd.sample(stamps, 4):
                    assert ([_fact_sig(f) for f in rec.as_of(s, "nfl", t, clock, kind=kind)]
                            == [_fact_sig(f) for f in _reference_as_of(kr, t, clock)]), (clock, t, kind)
                    assert ([_fact_sig(f) for f in rec.as_of(s, "nfl", t, clock, team="KC", kind=kind)]
                            == [_fact_sig(f) for f in _reference_as_of(kr, t, clock, team="KC")]), (clock, t, kind)
        assert rec.unread_under_source_clock(s, "nfl") == sum(r.source_stamp is None for r in rows)
        assert rec.unread_under_source_clock(s, "nfl", "plays_for") == sum(
            r.source_stamp is None for r in rows if r.kind == "plays_for")


class _CountingSession:
    """The read's session, counting every row its SELECTs hand back, on the session (HEAD's reads) or on its
    connection (the bounded read's): an instrumented reader."""

    def __init__(self, s, owner=None):
        self.s, self.owner = s, owner or self
        self.fetched = 0

    def execute(self, *a, **kw):
        return _Counted(self.s.execute(*a, **kw), self.owner)

    def connection(self, *a, **kw):
        return _CountingSession(self.s.connection(*a, **kw), self.owner)

    def __getattr__(self, name):
        return getattr(self.s, name)


class _Counted:
    def __init__(self, res, owner):
        self.res, self.owner = res, owner

    def __iter__(self):
        for row in self.res:
            self.owner.fetched += 1
            yield row

    def all(self):
        got = self.res.all()
        self.owner.fetched += len(got)
        return got

    def __getattr__(self, name):
        return getattr(self.res, name)


def test_a_team_read_loads_that_teams_rows_not_the_records_whole_history():
    """Codex on #841, round 1 (P1), fail-first: a --team read at a mid-history instant fetches that team's rows up to
    the instant (and a few rows of the key's own lookup), not every row of the sport: on HEAD 01a52c99 it fetched all
    of them (load_rows, then a cut in Python)."""
    _migrate()
    teams = [f"T{i:02d}" for i in range(8)]
    at = datetime(2026, 9, 1, 9)
    for day in range(10):
        stamp = at - timedelta(hours=2)
        _load(at, [_depth(f"Syn {t} {n}", f"00-{t}{n}", n % 3 + 1, stamp, team=t, slot=n)    # 8 full charts
                   for t in teams for n in range(6)])
        at += timedelta(days=1)
    mid = datetime(2026, 9, 5, 12)
    with _ro() as s:
        cs = _CountingSession(s)
        facts = rec.as_of(cs, "nfl", mid, team="T03")
        assert {f.interval.first.source_team for f in facts} == {"T03"} and len(facts) == 6
        total = _counts()[1]
        own = 5 * 6                                                   # T03's rows recorded at or before mid
        assert total == 480 and cs.fetched <= own + 6, (cs.fetched, own, total)
        cs2 = _CountingSession(s)
        assert len(rec.as_of(cs2, "nfl", datetime(2026, 9, 12), clock="source")) == 48
        assert cs2.fetched <= total, cs2.fetched                       # the unfiltered read: every row once, no more


def test_an_instant_on_the_last_representable_date_reads_everything_never_an_overflow():
    """Codex on #841, round 1 (the bounded read's own boundary), fail-first: the bounded read's clock bound added one day to the instant's date, so an
    instant on 9999-12-31 (a plausible "everything" instant) raised OverflowError from as_of and history, and the cli
    ended in a traceback. On that date the bound is the column's NULL test alone (a superset; the exact cut runs in
    Python): the answer is every fact in force, under both clocks, through the API and the cli."""
    _history_b()
    with _ro() as s:
        for clock in rec.CLOCKS:
            for t in (datetime(9999, 12, 31, 23, 59, tzinfo=timezone.utc), datetime.max):
                rows = _reference_rows(s, "nfl")
                assert ([_fact_sig(f) for f in rec.as_of(s, "nfl", t, clock)]
                        == [_fact_sig(f) for f in _reference_as_of(rows, rec._instant(t), clock)]), (clock, t)
                assert len(rec.history(s, "nfl", t, clock)) == len(_reference_history(rows, rec._instant(t), clock))
                assert len(rec.as_of(s, "nfl", t, clock, team="BAL")) == len(
                    _reference_as_of(rows, rec._instant(t), clock, team="BAL"))
    r = _cli("--sport", "nfl", "--as-of", "9999-12-31T23:59:59Z")
    assert r.exit_code == 0 and r.exception is None, r.output
    assert "7 fact(s) in force" in r.output.splitlines()[0]
    h = _cli("--sport", "nfl", "--as-of", "9999-12-31T23:59:59Z", "--history", "--clock", "source")
    assert h.exit_code == 0 and h.exception is None, h.output
