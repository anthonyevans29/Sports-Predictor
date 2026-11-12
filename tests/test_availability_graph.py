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


LOCK = f".{g.GRAPH_NAME}.lock"                                # the one-run-at-a-time lock beside the graph


def _no_engine(monkeypatch):
    monkeypatch.setattr(g, "_dist_version", lambda: None)    # no distribution installed
    monkeypatch.setitem(sys.modules, "ladybug", None)        # and `import ladybug` raises ImportError


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
    assert copy.read_bytes() == before and sorted(p.name for p in out.iterdir()) == [LOCK, g.RECEIPTS]
    line = json.loads((out / g.RECEIPTS).read_text())
    assert line["ok"] is False and "not installed" in line["refused"] and line["copy"] == str(copy.resolve())


def _fake_engine(monkeypatch, version="0.22.3", native=True):
    """A stand-in package: its version is the distribution's metadata (never ladybug.__version__, which asks the
    native library), its native module present or not."""
    import types
    fake = types.ModuleType("ladybug")
    backend = types.ModuleType("ladybug._backend")
    backend.get_pybind_module = lambda: object() if native else None
    backend._PYBIND_IMPORT_ERROR = None if native else ImportError("libssl.so.3: cannot open shared object file")
    fake._backend = backend

    def no_version(name):
        if name in ("__version__", "version", "storage_version"):
            raise AssertionError("ladybug.__version__ asks the native library: never read")
        raise AttributeError(name)
    fake.__getattr__ = no_version
    monkeypatch.setattr(g, "_dist_version", lambda: version)
    monkeypatch.setitem(sys.modules, "ladybug", fake)
    monkeypatch.setitem(sys.modules, "ladybug._backend", backend)
    return fake


def test_the_engine_must_be_the_pinned_version_and_its_overrides_are_dropped(monkeypatch):
    _fake_engine(monkeypatch, version="0.22.4")
    monkeypatch.setenv("LBUG_PYTHON_BACKEND", "capi")
    monkeypatch.setenv("LBUG_C_API_LIB_PATH", "/tmp/liblbug.so")
    with pytest.raises(g.Refused, match=r"0\.22\.4, not the pinned 0\.22\.3"):
        g.engine()
    assert "LBUG_PYTHON_BACKEND" not in os.environ and "LBUG_C_API_LIB_PATH" not in os.environ
    fake = _fake_engine(monkeypatch)
    assert g.engine() is fake


def test_review_a_missing_native_module_is_a_refusal_and_the_ctypes_fallback_is_never_imported(monkeypatch):
    """The pre-PR review: `ladybug.__version__` asked the native library and, with `ladybug._lbug` absent, the
    package's ctypes fallback (a liblbug.so by path, the working directory included). engine() now reads the version
    from the metadata and imports the native module through the package's loader first: absent, a refusal (exit 2),
    and `ladybug._lbug_capi` never imported."""
    monkeypatch.delitem(sys.modules, "ladybug._lbug_capi", raising=False)
    _fake_engine(monkeypatch, native=False)
    with pytest.raises(g.Refused, match=r"native module does not import \(libssl\.so\.3.*never taken"):
        g.engine()
    assert "ladybug._lbug_capi" not in sys.modules


def test_the_rebuild_refuses_a_copy_under_data_and_an_unmigrated_copy(fresh_db, tmp_path, monkeypatch):
    out = tmp_path / "graph"
    out.mkdir()
    with pytest.raises(g.Refused, match="one of --db"):
        g.rebuild(out / g.GRAPH_NAME)
    with pytest.raises(g.Refused, match="under the repo's data/"):
        g.rebuild(out / g.GRAPH_NAME, copy=REPO / "data" / "sports.db")
    copy = _copy(fresh_db, tmp_path / "backups")                     # not migrated: the record's tables absent
    fake = object()
    with pytest.raises(g.Refused, match="migrate_availability_record.py has not run"):
        g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=fake)
    lines = [json.loads(x) for x in (out / g.RECEIPTS).read_text().splitlines()]
    assert [bool(x.get("refused")) for x in lines] == [True, True, True]
    assert sorted(p.name for p in out.iterdir()) == [LOCK, g.RECEIPTS]           # no staging left


def test_review_a_copy_that_is_not_sqlite_is_refused_as_unreadable_not_as_unmigrated(tmp_path):
    out = tmp_path / "graph"
    out.mkdir()
    bad = tmp_path / "backups" / "sports_2026-11-12.db"
    bad.parent.mkdir()
    bad.write_bytes(b"not a database" * 100)
    with pytest.raises(g.Refused, match="cannot be read through a mode=ro \\+ immutable=1 URI"):
        g.rebuild(out / g.GRAPH_NAME, copy=bad, lb=object())


def test_review_a_receipt_that_cannot_be_written_never_replaces_the_outcome(fresh_db, tmp_path, monkeypatch):
    out = tmp_path / "graph"
    out.mkdir()
    (out / g.RECEIPTS).mkdir()                                     # the line cannot be appended
    copy = _copy(fresh_db, tmp_path / "backups")
    with pytest.raises(g.Refused, match="has not run"):            # still the refusal (exit 2), never an OSError
        g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=object())
    with pytest.raises(g.Refused, match="not writable"):
        os.chmod(out, 0o500)
        try:
            if os.access(out, os.W_OK):                            # root writes anyway: the check is moot here
                raise g.Refused("not writable (root: skipped)")
            g.check_out(out / g.GRAPH_NAME)
        finally:
            os.chmod(out, 0o700)


def test_review_one_run_at_a_time_and_a_killed_runs_staging_is_removed(fresh_db, tmp_path):
    import fcntl
    _history_b()
    out = tmp_path / "graph"
    out.mkdir()
    left = out / f".{g.GRAPH_NAME}.build-99999"                    # a SIGKILLed run's (MemoryMax)
    left.mkdir()
    (left / "Player.0000.csv").write_text("x")
    copy = _copy(fresh_db, tmp_path / "backups")
    with open(out / LOCK, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(g.Refused, match="another rebuild holds"):
            g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=object())
    assert left.exists()                                          # nothing touched while another run holds the lock

    def no_build(*a, **k):
        raise RuntimeError("synthetic")
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(g, "_load", no_build)
    try:
        with pytest.raises(RuntimeError):
            g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=object())
    finally:
        mp.undo()
    assert not left.exists()
    line = json.loads((out / g.RECEIPTS).read_text().splitlines()[-1])
    assert line["removed_stale_staging"] == [left.name] and "synthetic" in line["error"]


def test_review_a_sigterm_removes_the_staging_and_writes_its_line(fresh_db, tmp_path, monkeypatch):
    import signal
    _history_b()
    out = tmp_path / "graph"
    out.mkdir()
    copy = _copy(fresh_db, tmp_path / "backups")
    monkeypatch.setattr(g, "_load", lambda *a, **k: os.kill(os.getpid(), signal.SIGTERM))
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(g.Killed):
        g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=object())
    assert signal.getsignal(signal.SIGTERM) is before                # the handler restored
    assert sorted(p.name for p in out.iterdir()) == [LOCK, g.RECEIPTS]
    line = json.loads((out / g.RECEIPTS).read_text().splitlines()[-1])
    assert line["ok"] is False and line["error"].startswith("Killed: signal 15")


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


def _imports(tree):
    """Every module a file's syntax tree imports or loads by name: import, from-import (with each name it takes),
    __import__ and import_module calls on a constant."""
    import ast
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in ("__import__", "import_module") and n.args and isinstance(n.args[0], ast.Constant):
                out.add(str(n.args[0].value))
    return out


def test_347_c_nothing_but_the_rebuild_imports_the_engine_or_names_the_graph():
    """347 item 5(c): "nothing reads the graph for a call, a price or a page until a later ruling". Read on every
    Python file's syntax tree (the pre-PR review: a regex missed `import os, ladybug`, `__import__` and a module
    reaching the engine through graph.py): the engine is loaded in src/availability/graph.py alone; graph.py is
    imported by cli.py alone (its command); and only those two name the graph's file or directory. The web pages
    (src/web) are Python too, and are read here."""
    import ast
    engine_users, graph_users, namers = [], [], []
    for p in _python_files():
        t = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(REPO).as_posix()
        mods = _imports(ast.parse(t))
        if any(m == "ladybug" or m.startswith("ladybug.") for m in mods):
            engine_users.append(rel)
        if rel != "src/availability/graph.py" and ("src.availability.graph" in mods):
            graph_users.append(rel)
        if re.search(r"\.lbug\b|logs/availability/graph|availability-graph-rebuild|requirements-graph", t):
            namers.append(rel)
    assert engine_users == ["src/availability/graph.py"]
    assert graph_users == ["cli.py"]
    assert sorted(namers) == ["cli.py", "src/availability/graph.py"]
    import cli
    assert [n for n in cli.cli.commands if "graph" in n] == ["availability-graph-rebuild"]
    for p in (REPO / "src" / "web").rglob("*") if (REPO / "src" / "web").is_dir() else ():
        if p.is_file() and p.suffix in (".html", ".js", ".css", ".jinja", ".j2"):
            assert ".lbug" not in p.read_text(encoding="utf-8", errors="replace"), p


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
                 "InaccessiblePaths=/opt/sports-predictor/data /etc/sports-predictor", "ProtectHome=yes",
                 "CapabilityBoundingSet=", "OnFailure=sp-notify@availability-graph.service",
                 # the pre-PR review: another sp process's /proc view, filesystem sockets, the shared /dev/shm
                 "PrivateUsers=yes", "ProtectProc=invisible", "ProcSubset=pid", "RestrictAddressFamilies=none",
                 "PrivateDevices=yes", "PrivateIPC=yes"):
        assert re.search(rf"^{re.escape(line)}$", body, re.M), line
    assert re.findall(r"^ReadWritePaths=(.+)$", body, re.M) == ["/opt/sports-predictor/logs/availability/graph"]
    masks = re.findall(r"^BindReadOnlyPaths=(.+)$", body, re.M)
    assert masks == ["/dev/null:/opt/sports-predictor/.env"]          # host.env: its whole directory inaccessible
    assert re.findall(r"^TemporaryFileSystem=(.+)$", body, re.M) == ["/tmp:ro /var/tmp:ro"]
    assert "PrivateTmp" not in body                                               # one writable directory
    for k in ("SQLITE_TMPDIR", "TMPDIR"):
        assert re.search(rf"^Environment={k}=/opt/sports-predictor/logs/availability/graph$", body, re.M), k
    m = re.search(r"^ExecStart=(.+)$", body, re.M).group(1).split()
    assert m == ["/opt/sports-predictor/venv/bin/python", "cli.py", "availability-graph-rebuild", "--backup-dir",
                 "/var/backups/sports-predictor", "--out",
                 "/opt/sports-predictor/logs/availability/graph/availability.lbug"]
    assert "Wants=" not in body and "network-online" not in body
    assert re.findall(r"^After=(.+)$", body, re.M) == ["sp-backup.service"]  # Codex #943 r1: catch-up after the backup


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
    lists = c.t11_lists()                             # addendum 351 item 2: enabled only by the architect's block
    assert "sp-availability-graph.timer" in lists["TIMERS_BY_BLOCK"] and "sp-availability-graph.timer" not in lists["TIMERS"]
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
    assert sorted(p.name for p in out.iterdir()) == [LOCK, g.GRAPH_NAME, g.RECEIPTS]  # one file, no sidecar, no stage
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
    assert {f"nfl|{r.source}|{rec.player_key(r)[0]}|{rec.player_key(r)[1]}" for r, _, _ in walked} == keys
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
    assert sorted(p.name for p in out.iterdir()) == [LOCK, g.GRAPH_NAME, g.RECEIPTS]
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


@needs_engine
def test_review_any_text_the_record_keeps_survives_the_copy(fresh_db, tmp_path):
    """The pre-PR review: the engine's parallel CSV reader refuses a quoted newline, and the record keeps whatever
    text its source gave (the writer refuses only blank or over-long text): one such name failed every rebuild for
    good (append-only). COPY runs with PARALLEL=FALSE; every awkward text reads back exactly."""
    _migrate()
    names = ["line1\nline2", "x\r\ny", 'a "q", b', "back\\slash", "#lead", " pad ", "tab\tbed", "it's", '""']
    rows = [{"kind": "injury_status", "source_player_id": f"p{i}", "player_name": n, "source_team": f"T\n{i}",
             "attrs": {"status": n}} for i, n in enumerate(names)]
    rec.write_observation({"sport": "nfl", "source": "sportsdataio_goalies", "status": "complete",
                           "endpoint": "https://example.invalid/goalies", "fetched_at": datetime(2026, 11, 12, 9)},
                          rows)
    copy = _copy(fresh_db, tmp_path / "backups")
    out = tmp_path / "graph"
    out.mkdir()
    assert g.rebuild(out / g.GRAPH_NAME, copy=copy)["ok"]
    got = dict(_graph_rows(out / g.GRAPH_NAME, "MATCH (p:Player) RETURN p.source_player_id, p.name"))
    assert got == {f"p{i}": n for i, n in enumerate(names)}
    teams = {k for (k,) in _graph_rows(out / g.GRAPH_NAME, "MATCH (t:Team) RETURN t.source_team")}
    assert teams == {f"T\n{i}" for i in range(len(names))}
    attrs = [json.loads(a)["status"] for (a,) in _graph_rows(out / g.GRAPH_NAME, "MATCH ()-[f:FACT]->() RETURN f.attrs")]
    assert sorted(attrs) == sorted(names)


@needs_engine
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_review_a_nodes_ids_are_the_latest_mapping_whatever_the_walk_order(fresh_db, tmp_path, seed):
    """The pre-PR review: each node took the ids of whichever partition the walk yielded last (partition order, not
    time), so a team mapped by its later assertions came out NULL, and a re-mapped game kept its old match. A node's
    id is now the LATEST assertion's that carries one (recorded_at, then id): mapped_now's rule across the key."""
    _random_history(seed)
    copy = _copy(fresh_db, tmp_path / "backups")
    out = tmp_path / "graph"
    out.mkdir()
    g.rebuild(out / g.GRAPH_NAME, copy=copy)
    want: dict = {}
    with _ro() as s_:
        for r, _, _ in rec.walk(s_, "nfl"):
            mk = rec.match_key(r)
            keys = [("Player", g._key("nfl", r.source, rec.player_key(r)), r.player_id),
                    ("Team", g._key("nfl", r.source, rec.team_key(r)), r.team_id)]
            if mk is not None:
                gk = f"match|{mk[1]}" if mk[0] == "id" else g._key("nfl", r.source, mk)
                keys.append(("Game", gk, r.match_id if mk[0] == "src" else mk[1]))
            for kind, k, v in keys:
                if v is not None and (want.get((kind, k)) is None or (r.recorded_at, r.id) > want[(kind, k)][:2]):
                    want[(kind, k)] = (r.recorded_at, r.id, v)
    col = {"Player": "player_id", "Team": "team_id", "Game": "match_id"}
    seen = 0
    for kind in col:
        for k, v in _graph_rows(out / g.GRAPH_NAME, f"MATCH (n:{kind}) RETURN n.key, n.{col[kind]}"):
            if k.startswith("match|"):
                continue                                          # an observation's own match: its id is its key
            assert v == (want[(kind, k)][2] if (kind, k) in want else None), (kind, k)
            seen += v is not None
    assert seen                                                   # mapped nodes exist and carry the latest id


def test_codex_r1_the_copy_is_never_the_out_path(fresh_db, tmp_path):
    """Codex on #943, round 1: a .backup copy named *.lbug passed as both --db and --out passed both fences, and the
    final replace overwrote the only copy. Refused before anything is read; the copy byte-identical."""
    _history_b()
    out = tmp_path / "graph"
    out.mkdir()
    both = _copy(fresh_db, out, name="availability.lbug", sidecar=False)
    before = both.read_bytes()
    with pytest.raises(g.Refused, match="is --out: the rebuild never writes onto the copy"):
        g.rebuild(both, copy=both, lb=object())
    assert both.read_bytes() == before


def _fake_build(monkeypatch):
    """_load writes a stand-in graph file and _counts returns what was staged: the run reaches its commit point
    without the engine."""
    def load(lb, path, tables):
        path.write_bytes(b"graph")
        for t in tables.values():
            for f in t.files:
                f.unlink()
    monkeypatch.setattr(g, "_load", load)
    monkeypatch.setattr(g, "_counts", lambda lb, path: {n: monkeypatch._staged[n] for n in monkeypatch._staged})
    real = g._stage

    def stage(*a, **k):
        t = real(*a, **k)
        monkeypatch._staged = {n: t[n].n for n in t}
        return t
    monkeypatch.setattr(g, "_stage", stage)


def test_codex_r1_after_the_commit_point_the_run_is_a_success(fresh_db, tmp_path, monkeypatch):
    """Codex on #943, round 1: a SIGTERM (or a failing hash) after os.replace reported a failed run with "the previous
    graph untouched" while the graph had been replaced. The receipt's metadata is computed before the replace, which
    is the commit point: a signal after it leaves an ok line (its note kept), never an error."""
    _history_b()
    out = tmp_path / "graph"
    out.mkdir()
    copy = _copy(fresh_db, tmp_path / "backups")
    _fake_build(monkeypatch)
    real_replace = os.replace

    def replace_then_term(a, b):
        real_replace(a, b)
        raise g.Killed("signal 15 (the unit stopped or timed out)")
    monkeypatch.setattr(g.os, "replace", replace_then_term)
    r = g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=object())
    assert r["ok"] is True and r["sha256"] == g.sha256_file(out / g.GRAPH_NAME) and "Killed" in r["after_commit"]
    line = json.loads((out / g.RECEIPTS).read_text().splitlines()[-1])
    assert line["ok"] is True and "error" not in line


@needs_engine
def test_codex_r1_a_players_name_is_the_latest_assertions(fresh_db, tmp_path):
    """Codex on #943, round 1: the Player node kept the name of whichever partition the walk met first; a corrected
    name asserted later (here in a partition walked after the old one) never reached the graph."""
    _migrate()
    for at, kind, name in ((datetime(2026, 11, 10, 9), "injury_status", "Jon Smiht"),
                           (datetime(2026, 11, 11, 9), "plays_for", "Jon Smith")):
        rec.write_observation({"sport": "nfl", "source": "sportsdataio_goalies", "status": "complete",
                               "endpoint": "https://example.invalid/goalies", "fetched_at": at},
                              [{"kind": kind, "source_player_id": "p1", "player_name": name, "source_team": "KC",
                                "attrs": {"status": "active"}}])
    copy = _copy(fresh_db, tmp_path / "backups")
    out = tmp_path / "graph"
    out.mkdir()
    g.rebuild(out / g.GRAPH_NAME, copy=copy)
    assert _graph_rows(out / g.GRAPH_NAME, "MATCH (p:Player) RETURN p.name") == [["Jon Smith"]]


# ---- #944 (Codex on #943 after its second round; the review stop rule's follow-up) --------------------------------------

@needs_engine
def test_944_one_source_in_two_sports_is_two_nodes(fresh_db, tmp_path):
    """#944 item 2: the record derives per sport, so a source's player id and team text asserted in two sports are two
    nodes, each with its own sport's id; before, they merged and the later sport's ids overwrote the other's."""
    _migrate()
    for sport, tid in (("nfl", 1), ("nhl", 2)):
        rec.write_observation({"sport": sport, "source": "sportsdataio_goalies", "status": "complete",
                               "endpoint": f"https://example.invalid/{sport}", "fetched_at": datetime(2026, 11, 12, 9)},
                              [{"kind": "injury_status", "source_player_id": "p1", "player_name": "Same Id",
                                "source_team": "KC", "team_id": tid, "attrs": {"status": "out"}}])
    copy = _copy(fresh_db, tmp_path / "backups")
    out = tmp_path / "graph"
    out.mkdir()
    g.rebuild(out / g.GRAPH_NAME, copy=copy)
    teams = dict(_graph_rows(out / g.GRAPH_NAME, "MATCH (t:Team) RETURN t.key, t.team_id"))
    assert teams == {"nfl|sportsdataio_goalies|src|KC": 1, "nhl|sportsdataio_goalies|src|KC": 2}
    players = {k for (k,) in _graph_rows(out / g.GRAPH_NAME, "MATCH (p:Player) RETURN p.key")}
    assert players == {"nfl|sportsdataio_goalies|src|p1", "nhl|sportsdataio_goalies|src|p1"}


@needs_engine
def test_944_in_games_side_is_the_latest_assertions(fresh_db, tmp_path):
    """#944 item 3: IN_GAME's side was the first the walk met (partition order: confirmed_starter before
    projected_starter); a later assertion's corrected side never reached the edge. It is now the latest one's."""
    _migrate()
    for at, kind, side in ((datetime(2026, 11, 12, 18), "projected_starter", "home"),
                           (datetime(2026, 11, 12, 16), "confirmed_starter", "away")):
        rec.write_observation({"sport": "nhl", "source": "sportsdataio_goalies", "status": "complete",
                               "endpoint": f"https://example.invalid/{kind}", "fetched_at": at},
                              [{"kind": kind, "source_player_id": "g1", "player_name": "Goalie", "source_team": "BOS",
                                "attrs": {"source_match_id": "2026020309", "side": side}}])
    copy = _copy(fresh_db, tmp_path / "backups")
    out = tmp_path / "graph"
    out.mkdir()
    g.rebuild(out / g.GRAPH_NAME, copy=copy)
    assert _graph_rows(out / g.GRAPH_NAME, "MATCH ()-[e:IN_GAME]->() RETURN e.side") == [["home"]]


def test_944_a_sigterm_during_the_post_commit_cleanup_is_still_a_success(fresh_db, tmp_path, monkeypatch):
    """#944 item 4 (Codex on #943's merge commit): the handler stayed installed through the finally block, so a
    SIGTERM during the cleanup raised Killed past the except, over a graph already moved into place. The handler is
    restored first: the signal no longer reaches the run, and its line is ok. Codex on #952 (P2): restoring it BEFORE
    the cleanup let a SIGTERM under SIG_DFL kill the process before the line was written; the cleanup now defers the
    signal and re-delivers it after the prior disposition is back."""
    import signal
    _history_b()
    out = tmp_path / "graph"
    out.mkdir()
    copy = _copy(fresh_db, tmp_path / "backups")
    _fake_build(monkeypatch)
    seen, got = [], []
    real_rmtree = g.shutil.rmtree

    def rmtree_then_term(path, *a, **k):
        if str(path).endswith(f"build-{os.getpid()}") and (out / g.GRAPH_NAME).exists() and not seen:
            seen.append(path)
            os.kill(os.getpid(), signal.SIGTERM)
        return real_rmtree(path, *a, **k)
    def recorder(signum, frame):                                      # the caller's own handler: it records
        got.append((signum, (out / g.RECEIPTS).read_text() if (out / g.RECEIPTS).exists() else ""))
    original = signal.signal(signal.SIGTERM, recorder)
    try:
        monkeypatch.setattr(g.shutil, "rmtree", rmtree_then_term)
        r = g.rebuild(out / g.GRAPH_NAME, copy=copy, lb=object())
        assert seen and r["ok"] is True and "error" not in r and "after_commit" not in r
        assert [s for s, _ in got] == [signal.SIGTERM]    # the caller's handler had it back: the run never saw it
        # Codex on #952: the signal is DEFERRED through the cleanup and re-delivered once the prior disposition is
        # back, so the caller sees it only after the run's ok line is written (under SIG_DFL, the CLI's own case, the
        # process then ends on the stop it was sent, its receipt already on disk)
        last = [ln for ln in got[0][1].splitlines() if ln.strip()]
        assert last and json.loads(last[-1])["ok"] is True, got
        assert signal.getsignal(signal.SIGTERM) is recorder
    finally:
        signal.signal(signal.SIGTERM, original)
    line = json.loads((out / g.RECEIPTS).read_text().splitlines()[-1])
    assert line["ok"] is True
