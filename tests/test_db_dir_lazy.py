"""data/ is created at connect time, not import time (2026-09-26)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run(tmp_path, code):
    db_dir = tmp_path / "nested" / "dbdir"
    env = {"DATABASE_URL": f"sqlite:///{db_dir / 'x.db'}", "PATH": "/usr/bin:/bin"}
    subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, check=True)
    return db_dir


def test_import_does_not_create_the_db_directory(tmp_path):
    assert not _run(tmp_path, "import cli").exists()


def test_first_connection_creates_it(tmp_path):
    d = _run(tmp_path, "from src.db.database import init_db; init_db()")
    assert d.is_dir() and (d / "x.db").exists()
