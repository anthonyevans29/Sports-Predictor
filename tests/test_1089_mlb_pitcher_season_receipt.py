"""#1089 (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4) for scripts/mlb_pitcher_season_receipt.py: the app's
configured database keeps its open (mode=ro, #421's fallback); any other --db is a copy, opened mode=ro&immutable=1
with no fallback, refused before any open (exit 2) with a sidecar beside it or absent. Copies are throwaway WAL files
in tmp; nothing here opens or creates anything under data/."""
import importlib.util
import sqlite3
from pathlib import Path

from src.walters import db_copy as dc

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mlb_pitcher_season_receipt.py"


def _receipt():
    spec = importlib.util.spec_from_file_location("ps_receipt_1089", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wal_copy(p: Path) -> Path:
    """A fresh .backup-like copy: a WAL-mode file with the tables the receipt reads, its sidecars checkpointed away."""
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE competitions (id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, season TEXT, stage TEXT,
                              utc_date TEXT, home_team_id INTEGER, away_team_id INTEGER);
        CREATE TABLE match_participants (id INTEGER PRIMARY KEY, match_id INTEGER, team_id INTEGER, role TEXT,
                                         player_name TEXT, player_source_id TEXT);
        CREATE TABLE pitcher_season_stats (id INTEGER PRIMARY KEY, player_source_id TEXT, season TEXT, era REAL,
                                           innings_pitched REAL, games_started INTEGER);
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, match_id INTEGER, model_version TEXT, computed_at TEXT,
                                  factor_breakdown TEXT);
        INSERT INTO pitcher_season_stats VALUES (1, 'ps-9', '2093', 3.5, 50.0, 9);
        INSERT INTO pitcher_season_stats VALUES (2, 'ps-9', '2094', 2.5, 40.0, 7);
    """)
    con.commit()
    con.close()
    for s in dc.SIDECARS:
        p.with_name(p.name + s).unlink(missing_ok=True)
    return p


def test_a_copy_is_read_mode_ro_immutable_and_leaves_no_sidecar(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    mod = _receipt()
    monkeypatch.setattr(mod, "open_read", lambda *_: (_ for _ in ()).throw(AssertionError("live open on a copy")))
    assert mod.main(["--db", str(p), "--date", "2094-07-01", "--season", "2094"]) == 0
    out = capsys.readouterr().out
    assert f"D0 database {p.resolve()} · opened via mode=ro URI with immutable=1 (a copy; no fallback)" in out
    assert "S2 pitchers with more than one season stored: 1" in out and "seasons 2093,2094: 1" in out
    assert dc.sidecars(p) == []                                  # nothing created beside it


def test_a_copy_with_a_wal_sidecar_is_refused_before_any_open(tmp_path, capsys, monkeypatch):
    p = wal_copy(tmp_path / "copy.db")
    (tmp_path / "copy.db-wal").write_bytes(b"")
    mod = _receipt()
    opened = []
    monkeypatch.setattr(mod.db_copy, "connect_copy", lambda *a: opened.append(a))
    monkeypatch.setattr(mod, "open_read", lambda *a: opened.append(a))
    monkeypatch.setattr(mod.sqlite3, "connect", lambda *a, **k: opened.append(a))
    assert mod.main(["--db", str(p)]) == dc.EXIT_REFUSED == 2
    cap = capsys.readouterr()
    assert "REFUSED: " in cap.err and "-wal sidecar (copy.db-wal)" in cap.err
    assert "D0 database" not in cap.out and opened == []


def test_an_absent_db_is_refused_and_never_created(tmp_path, capsys):
    p = tmp_path / "absent.db"
    assert _receipt().main(["--db", str(p)]) == 2
    cap = capsys.readouterr()
    assert "REFUSED: " in cap.err and "no file at" in cap.err and str(p) in cap.err
    assert "D0 database" not in cap.out
    assert not p.exists() and dc.sidecars(p) == []


def test_the_apps_configured_database_takes_the_live_open(tmp_path, capsys, monkeypatch):
    live = wal_copy(tmp_path / "sports.db")
    monkeypatch.setattr(dc, "app_db", lambda: live.resolve())
    mod = _receipt()
    calls = []
    real = mod.open_read

    def record(p):
        calls.append(p)
        return real(p)

    monkeypatch.setattr(mod, "open_read", record)
    monkeypatch.setattr(mod, "open_copy", lambda *_: (_ for _ in ()).throw(AssertionError("copy open on live")))
    assert mod.main(["--db", str(live), "--date", "2094-07-01", "--season", "2094"]) == 0
    assert calls == [Path(str(live))]
    assert "opened via mode=ro URI" in capsys.readouterr().out
