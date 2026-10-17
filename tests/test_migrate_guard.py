"""THE MIGRATIONS' SHARED GUARD (ARCHITECT 2026-10-17, addendum 112 item 1; #524): "every migration refuses when the
file is absent ("no database at <path>; a migration never creates one — law 5"), exit 1, nothing written; one shared
guard in the migrations' common helper; a test."

Every top-level migrate_*.py is found by glob (a new one is covered without an edit here) and run as the operator and
sp_deploy run it, `python migrate_<name>.py` in its own process, with DATABASE_URL on a throwaway path under tmp_path:
the app's real engine and its connect hooks, which create a missing directory and a WAL file on a first connection."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted(p.name for p in REPO.glob("migrate_*.py"))


def _run(script, url, cwd=REPO):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, str(REPO / script)], cwd=str(cwd), env=env, capture_output=True,
                          text=True, timeout=120)


def _refusal(path):
    return f"no database at {path.resolve()}; a migration never creates one — law 5\n"


def test_every_migration_is_found():
    assert len(MIGRATIONS) >= 21 and "migrate_kalshi_settled_markets.py" in MIGRATIONS


@pytest.mark.parametrize("script", MIGRATIONS)
def test_a_migration_never_creates_a_database(script, tmp_path):
    """No DB file at the configured path (in a directory that does not exist either): exit 1, the ruled line and
    nothing else on stdout, and neither the file nor its directory exists afterwards."""
    missing = tmp_path / "nowhere" / "sports.db"
    r = _run(script, f"sqlite:///{missing}")
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout == _refusal(missing)
    assert not missing.exists() and not missing.parent.exists()
    assert list(tmp_path.iterdir()) == []                          # no -wal / -shm sidecar, nothing at all


def test_a_relative_url_is_read_against_the_working_directory(tmp_path):
    """The app's default URL is relative (sqlite:///./data/sports.db): SQLite opens it against the working directory,
    and the guard reads it there too."""
    r = _run("migrate_status_raw.py", "sqlite:///./data/sports.db", cwd=tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout == _refusal(tmp_path / "data" / "sports.db")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("script, done", [
    ("migrate_kalshi_ticker.py", "+ Adding odds_snapshots.market_ticker..."),
    ("migrate_kalshi_settled_markets.py", "+ Wrote migration marker kalshi_settled_markets_migration"),
])
def test_an_existing_database_is_migrated_as_before(script, done, tmp_path):
    """The guard lets an existing DB through: the migration runs on it and exits 0, as before the guard."""
    from src.db.schema import Base
    live = tmp_path / "live.db"
    eng = create_engine(f"sqlite:///{live}", future=True)
    Base.metadata.create_all(eng)                                  # init_db()'s tables on a DB of the test's own
    r = _run(script, f"sqlite:///{live}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no database at" not in r.stdout and done in r.stdout
    insp = inspect(eng)
    if script == "migrate_kalshi_ticker.py":
        assert "market_ticker" in {c["name"] for c in insp.get_columns("odds_snapshots")}
    else:
        assert insp.has_table("kalshi_settled_markets_migration")
    eng.dispose()
