"""#1089 on scripts/mlb_pitcher_asof_receipt.py (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4): the app's configured
database keeps its open (open_read: mode=ro, #421's fallback); any other --db is a copy, opened mode=ro&immutable=1 with
no fallback, and refused before any open (exit 2, nothing read) under data/, with a sidecar beside it, or absent. Every
file here is a throwaway in tmp_path, built from the app's own schema by the receipt's own test fixture."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

from src.walters import db_copy

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("mlb_pitcher_asof_receipt_t1089", ROOT / "scripts" / "mlb_pitcher_asof_receipt.py")
fx = _load("mlb_pitcher_asof_receipt_fixture_t1089", ROOT / "tests" / "test_mlb_pitcher_asof_receipt.py")


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy of the receipt's fixture: WAL mode, its sidecars checkpointed away."""
    fx.build(p)
    con = sqlite3.connect(p)
    assert con.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    con.close()
    for s in db_copy.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    assert p.read_bytes()[18:20] == b"\x02\x02"                    # the header says WAL
    return p


def _no_open(monkeypatch):
    monkeypatch.setattr(rc, "open_read", lambda *a: pytest.fail("the live open was taken"))
    monkeypatch.setattr(db_copy, "connect_copy", lambda *a: pytest.fail("a copy was opened"))


def test_a_wal_copy_is_read_through_immutable_and_nothing_is_left_beside_it(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    monkeypatch.setattr(rc, "open_read", lambda *a: pytest.fail("a copy took the live file's open (#421's fallback)"))
    assert rc.main(["--db", str(p), "--seasons", "2025"]) == 0
    out = capsys.readouterr().out
    assert f"database {p.resolve()} (mode=ro URI with immutable=1 (a copy; no fallback))" in out
    assert "regular games read 5" in out
    assert db_copy.sidecars(p) == []                                # no -wal, -shm or -journal beside it


@pytest.mark.parametrize("side", db_copy.SIDECARS)
def test_a_copy_with_a_sidecar_is_refused_before_any_open(tmp_path, capsys, monkeypatch, side):
    p = wal_copy(tmp_path / "copy.db")
    p.with_name(p.name + side).write_bytes(b"")
    _no_open(monkeypatch)
    assert rc.main(["--db", str(p)]) == db_copy.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    assert cap.err.startswith("REFUSED: ") and f"has a {side} sidecar (copy.db{side})" in cap.err
    assert str(p) in cap.err and cap.out == ""                      # the path, never a row


def test_an_absent_copy_is_refused_and_never_created(tmp_path, capsys, monkeypatch):
    p = tmp_path / "absent.db"
    _no_open(monkeypatch)
    assert rc.main(["--db", str(p)]) == 2
    cap = capsys.readouterr()
    assert cap.err.startswith("REFUSED: ") and "no file at" in cap.err and str(p) in cap.err
    assert not p.exists() and list(tmp_path.iterdir()) == []


def test_a_copy_under_data_is_refused_as_is_the_live_file_with_no_configuration(tmp_path, capsys, monkeypatch):
    """582 item 4(b) and 4(d): a file under data/ is refused; with no configuration loaded nothing reads as live, so
    the machine's own live file under data/ is a copy under data/ and is refused too."""
    from src.walters import mlb_pitchers_gate as mp
    data = tmp_path / "data"
    data.mkdir()
    p = wal_copy(data / "sports.db")
    monkeypatch.setattr(mp, "_data_dirs", lambda: [data.resolve()])
    monkeypatch.setattr(db_copy, "app_db", lambda: None)
    _no_open(monkeypatch)
    assert rc.main(["--db", str(p)]) == 2
    cap = capsys.readouterr()
    assert "under the repo's data/" in cap.err and cap.out == ""


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    p = tmp_path / "sports.db"
    fx.build(p)
    monkeypatch.setattr(db_copy, "app_db", lambda: p.resolve())
    monkeypatch.setattr(db_copy, "connect_copy", lambda *a: pytest.fail("the live file took a copy's open"))
    seen, real = [], rc.open_read
    monkeypatch.setattr(rc, "open_read", lambda path: seen.append(path) or real(path))
    assert rc.main(["--db", str(p), "--seasons", "2025"]) == 0
    assert seen == [Path(str(p))]
    out = capsys.readouterr().out
    assert f"database {p} (mode=ro URI)" in out and "regular games read 5" in out


def test_the_help_line_says_the_rule(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "2000")                          # one line: no wrap can split a hyphenated word
    with pytest.raises(SystemExit):
        rc.main(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    for words in ("configured database keeps its open", "mode=ro&immutable=1", "no fallback", "under data/",
                  "-wal/-shm/-journal sidecar", "or absent", "without the app's configuration loaded",
                  "addendum 582 item 4"):
        assert words in out, words
