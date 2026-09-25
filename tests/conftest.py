"""
Test bootstrap. Points DATABASE_URL at a throwaway SQLite file under pytest's
tmp dir BEFORE any project module is imported — importing src.db.database
creates the DB's parent directory, and data/ must never be touched by tests.
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="sp-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ.setdefault("API_FOOTBALL_KEY", "test-dummy")
os.environ["OPEN_BROWSER"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
