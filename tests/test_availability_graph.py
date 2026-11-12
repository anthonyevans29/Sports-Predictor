"""The availability record's graph projection (lane availability-record, #830, step 7): `availability-graph-rebuild`
on the pick (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4; 2026-11-11 19:50 ET, addendum 347 item 5).

The engine is HOST-ONLY (347 item 5(a): "the laptop and CI do not install it and its tests skip when it is absent"):
every test that builds a graph skips without `ladybug`; the read (record.walk), the copy's choice, the fences, the
refusals, the unit's form and conditions (c) and (d) run everywhere. Every row is synthetic, written through the
record's writer on a throwaway DB (tests/conftest.py; the record tests' fresh_db); nothing under data/.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.availability import graph as g
from src.availability import record as rec
from tests.test_availability_record import _history_b, _migrate, _random_history, _ro, fresh_db  # noqa: F401

pytestmark = pytest.mark.usefixtures("fresh_db")

REPO = Path(__file__).resolve().parents[1]
HOSTING = REPO / "deploy" / "hosting"
NOW = datetime(2026, 11, 12, 10, 20, tzinfo=timezone.utc)


def _have_engine() -> bool:
    try:
        import ladybug  # noqa: F401
    except ImportError:
        return False
    return True


needs_engine = pytest.mark.skipif(not _have_engine(), reason="the graph engine is host-only (addendum 347 item 5(a))")


def _sig(iv):
    return None if iv is None else (iv.first.id, iv.start, iv.end, iv.closed_by.id if iv.closed_by else None,
                                    iv.why_closed)


def _copy(fresh, d: Path, name="sports_2026-11-12.db", sidecar=True, mtime=None) -> Path:
    """A .backup copy of the throwaway DB (sqlite3's backup API, as sp_backup takes it) and its sha256 sidecar."""
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    src, dst = sqlite3.connect(fresh), sqlite3.connect(p)
    src.backup(dst)
    src.close()
    dst.close()
    if sidecar:
        (d / (name + ".sha256")).write_text(f"{g.sha256_file(p)}  {name}\n")
    if mtime is not None:
        os.utime(p, (mtime.timestamp(), mtime.timestamp()))
    return p


# ---- the read: record.walk is history's own derivation (252 item 2: "there is no second path") -------------------------

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_walk_equals_history_under_both_clocks_row_by_row(seed):
    """The projection reads record.walk: for every assertion, its interval under the recorded clock and (where it
    carries a source stamp) under the source clock equal what history(s, sport, datetime.max, clock) gives that row:
    the same opening row, start, end, closing row and reason. Rows with no source stamp carry None under the source
    clock, as history does not list them there."""
    _random_history(seed)
    with _ro() as s:
        walked = list(rec.walk(s, "nfl"))
        hist = {c: {r.id: iv for r, iv in rec.history(s, "nfl", datetime.max, c)} for c in rec.CLOCKS}
    assert len(walked) > 150 and len({r.id for r, _, _ in walked}) == len(walked)
    assert {r.id for r, _, _ in walked} == set(hist["recorded"])
    assert {r.id for r, _, siv in walked if siv is not None} == set(hist["source"])
    for r, riv, siv in walked:
        assert _sig(riv) == _sig(hist["recorded"][r.id]), r.id
        assert _sig(siv) == _sig(hist["source"].get(r.id)), r.id
    whys = {iv.why_closed for _, riv, siv in walked for iv in (riv, siv) if iv is not None}
    assert whys >= {"asserted differently", "slot asserted to someone else", "not restated in its team's snapshot"}


def test_the_walk_reads_the_flip_and_the_backfill_of_the_small_history():
    _history_b()
    with _ro() as s:
        named = {r.player_name: (riv, siv) for r, riv, siv in rec.walk(s, "nfl") if not r.player_name.startswith("Fill")}
    a_rec, _ = named["A Starter"]
    assert a_rec.end == datetime(2026, 11, 7, 9) and a_rec.why_closed == "slot asserted to someone else"
    c_rec, c_src = named["C Backup"]
    assert c_rec.start == datetime(2026, 11, 8, 9) and c_src.start == datetime(2026, 10, 20, 7)


# ---- the copy (347 item 5(b): a .backup COPY, mode=ro + immutable=1, never the live file) --------------------------------

def test_the_newest_daily_copy_with_a_matching_sidecar_is_taken(fresh_db, tmp_path):
    _migrate()
    d = tmp_path / "backups"
    _copy(fresh_db, d, "sports_2026-11-10.db", mtime=NOW - timedelta(hours=49))
    want = _copy(fresh_db, d, "sports_2026-11-11.db", mtime=NOW - timedelta(hours=25))
    _copy(fresh_db, d, "sports_2026-11-12.db", sidecar=False, mtime=NOW - timedelta(hours=1))        # no sidecar
    bad = _copy(fresh_db, d, "sports_2026-11-12_101500.db", mtime=NOW - timedelta(minutes=5))
    (d / (bad.name + ".sha256")).write_text("0" * 64 + f"  {bad.name}\n")                            # a mismatch
    _copy(fresh_db, d, "sports_2026-11-12_prerefresh_0930.db", mtime=NOW)                           # not a daily
    _copy(fresh_db, d, "sports_2026-11-12_closing_101000.db", mtime=NOW)                             # not a daily
    assert g.pick_copy(d, NOW) == want


def test_a_stale_newest_copy_is_refused_never_rebuilt_from(fresh_db, tmp_path):
    _migrate()
    d = tmp_path / "backups"
    _copy(fresh_db, d, "sports_2026-11-10.db", mtime=NOW - timedelta(hours=27))
    with pytest.raises(g.Refused, match=r"27\.0 h old \(> 26 h\): stale"):
        g.pick_copy(d, NOW)
    assert g.pick_copy(d, NOW, max_age_hours=30).name == "sports_2026-11-10.db"
    (tmp_path / "empty").mkdir()
    with pytest.raises(g.Refused, match="no daily .backup copy"):
        g.pick_copy(tmp_path / "empty", NOW)
    for n in os.listdir(d):
        if n.endswith(".sha256"):
            (d / n).unlink()
    with pytest.raises(g.Refused, match="no daily copy has a matching .sha256 sidecar"):
        g.pick_copy(d, NOW)


def test_the_out_path_is_fenced(tmp_path):
    (tmp_path / "graph").mkdir()
    assert g.check_out(tmp_path / "graph" / "a.lbug") == (tmp_path / "graph" / "a.lbug").resolve()
    for bad, why in ((tmp_path / "graph" / "a.db", "a .lbug file"),
                     (tmp_path / "nowhere" / "a.lbug", "its directory does not exist"),
                     (tmp_path / "data" / "a.lbug", "data/"),
                     (REPO / "data" / "a.lbug", "data/")):
        with pytest.raises(g.Refused, match=re.escape(why)):
            g.check_out(bad)
    q = tmp_path / "it's"
    q.mkdir()
    with pytest.raises(g.Refused, match="a quote"):
        g.check_out(q / "a.lbug")


def _no_engine(monkeypatch):
    monkeypatch.setitem(sys.modules, "ladybug", None)        # `import ladybug` raises ImportError


def test_without_the_engine_the_rebuild_refuses_reads_nothing_and_writes_one_receipt_line(fresh_db, tmp_path,
                                                                                            monkeypatch):
    _history_b()
    _no_engine(monkeypatch)
    copy = _copy(fresh_db, tmp_path / "backups")
    before = copy.read_bytes()
    out = tmp_path / "graph"
    out.mkdir()
    with pytest.raises(g.Refused, match=r"not installed .*host-only: requirements-graph\.txt"):
        g.rebuild(out / g.GRAPH_NAME, copy=copy)
    assert copy.read_bytes() == before and sorted(p.name for p in out.iterdir()) == [g.RECEIPTS]
    line = json.loads((out / g.RECEIPTS).read_text())
    assert line["ok"] is False and "not installed" in line["refused"] and line["copy"] == str(copy.resolve())


def test_the_engine_must_be_the_pinned_version_and_its_overrides_are_dropped(monkeypatch):
    import types
    fake = types.ModuleType("ladybug")
    fake.__version__ = "0.22.4"
    monkeypatch.setitem(sys.modules, "ladybug", fake)
    monkeypatch.setenv("LBUG_PYTHON_BACKEND", "capi")
    monkeypatch.setenv("LBUG_C_API_LIB_PATH", "/tmp/liblbug.so")
    with pytest.raises(g.Refused, match=r"0\.22\.4, not the pinned 0\.22\.3"):
        g.engine()
    assert "LBUG_PYTHON_BACKEND" not in os.environ and "LBUG_C_API_LIB_PATH" not in os.environ
    fake.__version__ = "0.22.3"
    assert g.engine() is fake


def test_the_rebuild_refuses_a_copy_under_data_and_an_unmigrated_copy(fresh_db, tmp_path, monkeypatch):
    out = tmp_path / "graph"
    out.mkdir()
    with pytest.raises(g.Refused, match="one of --db"):
        g.rebuild(out / g.GRAPH_NAME)
    with pytest.raises(g.Refused, match="under the repo's data/"):
        g.rebuild(out / g.GRAPH_NAME, copy=REPO / "data" / "sports.db")
    copy = _copy(fresh_db, tmp_path / "backups")                     # not migrated: the record's tables absent
    import types
    fake = types.ModuleType("ladybug")
    fake.__version__ = g.ENGINE_VERSION
    with pytest.raises(g.Refused, match="migrate_availability_record.py has not run"):
        g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=fake)
    lines = [json.loads(x) for x in (out / g.RECEIPTS).read_text().splitlines()]
    assert [bool(x.get("refused")) for x in lines] == [True, True, True]
    assert sorted(p.name for p in out.iterdir()) == [g.RECEIPTS]                 # no staging left


def test_the_cli_refusal_exits_2(fresh_db, tmp_path, monkeypatch):
    from click.testing import CliRunner

    import cli
    _history_b()
    _no_engine(monkeypatch)
    copy = _copy(fresh_db, tmp_path / "backups")
    (tmp_path / "graph").mkdir()
    r = CliRunner().invoke(cli.cli, ["availability-graph-rebuild", "--db", str(copy), "--out",
                                     str(tmp_path / "graph" / g.GRAPH_NAME)])
    assert r.exit_code == 2 and "AVAILABILITY-GRAPH REFUSED" in r.output and "host-only" in r.output, r.output


# ---- conditions (c) and (d) ----------------------------------------------------------------------------------------------

def _python_files():
    for base in ("src", "scripts", "deploy", "migrations"):
        yield from (REPO / base).rglob("*.py")
    yield from REPO.glob("*.py")


def test_347_c_nothing_but_the_rebuild_imports_the_engine_or_names_the_graph():
    """347 item 5(c): "nothing reads the graph for a call, a price or a page until a later ruling". The engine is
    imported in src/availability/graph.py alone; the graph's file is named there and by the CLI's help (its default)
    alone; no export, chain, Desk or page module names either."""
    importers, namers = [], []
    for p in _python_files():
        t = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(REPO).as_posix()
        if re.search(r"^\s*(import ladybug|from ladybug)|import_module\(\s*['\"]ladybug", t, re.M):
            importers.append(rel)
        if re.search(r"availability\.lbug|\.lbug['\"]|logs/availability/graph", t):
            namers.append(rel)
    assert importers == ["src/availability/graph.py"]
    assert sorted(namers) == ["cli.py", "src/availability/graph.py"]
    import cli
    cmds = [n for n in cli.cli.commands if "graph" in n]
    assert cmds == ["availability-graph-rebuild"]


def test_347_d_the_pin_is_exact_by_hash_and_never_in_requirements_txt():
    """347 item 5(a) and (d): its own requirements file, the exact version, the cp312 manylinux x86_64 wheel's
    sha256 as the candidates page records it; never requirements.txt; CI installs requirements.txt only."""
    lines = [x for x in (REPO / g.REQUIREMENTS).read_text().splitlines() if x.strip() and not x.startswith("#")]
    assert lines == ["ladybug==0.22.3 --hash=sha256:d58f4457ce6fd0bc36656426cd663972429b94c8a9e49e153dd37d04f256b9c4"]
    assert g.ENGINE_VERSION == "0.22.3" and g.ENGINE == "ladybug"
    assert "ladybug" not in (REPO / "requirements.txt").read_text().lower()
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
    assert "requirements-graph" not in ci and "ladybug" not in ci


# ---- the unit (347 item 5(b)) --------------------------------------------------------------------------------------------

def test_347_b_the_unit_is_its_own_sandbox():
    u = (HOSTING / "systemd" / "sp-availability-graph.service").read_text()
    body = "\n".join(x for x in u.splitlines() if not x.startswith("#"))
    assert "EnvironmentFile" not in body                                           # never host.env
    for line in ("PrivateNetwork=yes", "NoNewPrivileges=yes", "ProtectSystem=strict", "User=sp", "Type=oneshot",
                 "InaccessiblePaths=/opt/sports-predictor/data", "ProtectHome=yes", "CapabilityBoundingSet=",
                 "OnFailure=sp-notify@availability-graph.service"):
        assert re.search(rf"^{re.escape(line)}$", body, re.M), line
    assert re.findall(r"^ReadWritePaths=(.+)$", body, re.M) == ["/opt/sports-predictor/logs/availability/graph"]
    masks = re.findall(r"^BindReadOnlyPaths=(.+)$", body, re.M)
    assert masks == ["/dev/null:/etc/sports-predictor/host.env /dev/null:/opt/sports-predictor/.env"]
    assert re.findall(r"^TemporaryFileSystem=(.+)$", body, re.M) == ["/tmp:ro /var/tmp:ro"]
    assert "PrivateTmp" not in body                                               # one writable directory
    for k in ("SQLITE_TMPDIR", "TMPDIR"):
        assert re.search(rf"^Environment={k}=/opt/sports-predictor/logs/availability/graph$", body, re.M), k
    m = re.search(r"^ExecStart=(.+)$", body, re.M).group(1).split()
    assert m == ["/opt/sports-predictor/venv/bin/python", "cli.py", "availability-graph-rebuild", "--backup-dir",
                 "/var/backups/sports-predictor", "--out",
                 "/opt/sports-predictor/logs/availability/graph/availability.lbug"]
    assert "Wants=" not in body and "network-online" not in body


def test_the_timer_follows_the_backup_and_ships_disabled():
    sys.path.insert(0, str(HOSTING))
    import chains
    import sp_common as c
    import sp_notify
    t = (HOSTING / "systemd" / "sp-availability-graph.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == ["*-*-* 10:20:00 UTC"]
    b = (HOSTING / "systemd" / "sp-backup.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", b, re.M) == ["*-*-* 09:30:00 UTC"]     # the copy it reads is older
    assert re.search(r"^Unit=sp-availability-graph\.service$", t, re.M)
    assert sp_notify.unit_for("availability-graph") == "sp-availability-graph.service"
    assert "sp-availability-graph.service" not in sp_notify.THROTTLED_UNITS          # daily: every failure pages
    assert "sp-availability-graph.timer" in c.t11_lists()["TIMERS"]
    assert "availability-graph" not in chains.CHAINS                                # not a chain step (347 item 5(b))
    assert all("availability-graph-rebuild" not in json.dumps(v) for v in chains.CHAINS.values())


# ---- the build (skipped without the engine) ------------------------------------------------------------------------------

def _graph_rows(path: Path, q: str):
    import ladybug as lb
    db = lb.Database(str(path), backend="pybind", read_only=True)
    con = lb.Connection(db)
    try:
        return con.execute(q).get_all()
    finally:
        con.close()
        db.close()


@needs_engine
def test_the_rebuild_projects_every_assertion_with_both_intervals(fresh_db, tmp_path):
    _random_history(2)
    copy = _copy(fresh_db, tmp_path / "backups")
    before = copy.read_bytes()
    out = tmp_path / "graph"
    out.mkdir()
    r = g.rebuild(out / g.GRAPH_NAME, backup_dir=tmp_path / "backups", now=datetime.now(timezone.utc))
    assert r["ok"] and copy.read_bytes() == before                                 # the copy byte-identical
    assert not (copy.parent / (copy.name + "-wal")).exists() and not (copy.parent / (copy.name + "-shm")).exists()
    assert sorted(p.name for p in out.iterdir()) == [g.GRAPH_NAME, g.RECEIPTS]      # one file, no sidecar, no staging
    with _ro() as s:
        walked = list(rec.walk(s, "nfl"))
        n_obs = s.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM availability_observations")).scalar()
    c = r["counts"]
    assert c["FACT"] == c["ASSERTED"] == len(walked) and c["Observation"] == n_obs and c["Build"] == 1
    graph = out / g.GRAPH_NAME
    got = {row[0]: tuple(row[1:]) for row in _graph_rows(graph, "MATCH ()-[f:FACT]->() RETURN f.assertion_id, f.rec_interval, "
                                                         "f.rec_start, f.rec_end, f.rec_why, f.src_interval, f.src_start, "
                                                         "f.src_end, f.kind, f.recorded_at, f.source_stamp")}
    for row, riv, siv in walked:
        want = (riv.first.id, riv.start, riv.end, riv.why_closed, siv.first.id if siv else None,
                siv.start if siv else None, siv.end if siv else None, row.kind, row.recorded_at, row.source_stamp)
        assert got[row.id] == want, row.id
    keys = {k for (k,) in _graph_rows(graph, "MATCH (p:Player) RETURN p.key")}
    assert {f"{r.source}|{rec.player_key(r)[0]}|{rec.player_key(r)[1]}" for r, _, _ in walked} == keys
    b = _graph_rows(graph, "MATCH (b:Build) RETURN b.copy, b.copy_sha256, b.engine, b.assertions")
    assert b == [[copy.name, g.sha256_file(copy), "ladybug 0.22.3", len(walked)]]
    line = json.loads((out / g.RECEIPTS).read_text().splitlines()[-1])
    assert line["ok"] is True and line["sha256"] == g.sha256_file(graph) and line["counts"] == c


@needs_engine
def test_a_failed_rebuild_leaves_the_previous_graph_and_writes_its_line(fresh_db, tmp_path, monkeypatch):
    _history_b()
    copy = _copy(fresh_db, tmp_path / "backups")
    out = tmp_path / "graph"
    out.mkdir()
    g.rebuild(out / g.GRAPH_NAME, copy=copy)
    first = (out / g.GRAPH_NAME).read_bytes()

    def boom(*a, **k):
        raise RuntimeError("synthetic COPY failure")
    monkeypatch.setattr(g, "_load", boom)
    with pytest.raises(RuntimeError, match="synthetic"):
        g.rebuild(out / g.GRAPH_NAME, copy=copy)
    assert (out / g.GRAPH_NAME).read_bytes() == first
    assert sorted(p.name for p in out.iterdir()) == [g.GRAPH_NAME, g.RECEIPTS]
    lines = [json.loads(x) for x in (out / g.RECEIPTS).read_text().splitlines()]
    assert [x["ok"] for x in lines] == [True, False] and "synthetic COPY failure" in lines[1]["error"]


@needs_engine
def test_the_cli_builds_and_prints_its_counts(fresh_db, tmp_path):
    from click.testing import CliRunner

    import cli
    _history_b()
    copy = _copy(fresh_db, tmp_path / "backups")
    (tmp_path / "graph").mkdir()
    r = CliRunner().invoke(cli.cli, ["availability-graph-rebuild", "--db", str(copy), "--out",
                                     str(tmp_path / "graph" / g.GRAPH_NAME)])
    assert r.exit_code == 0, r.output
    assert "AVAILABILITY-GRAPH" in r.output and "mode=ro + immutable=1" in r.output and "FACT 21" in r.output
