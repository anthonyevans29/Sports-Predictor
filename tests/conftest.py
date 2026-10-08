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

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_cross_ref_guard(monkeypatch):
    """#329: the registry's cross-ref guard runs git (fetch + for-each-ref) against the repo. No test may read or
    fetch the real repo's refs: every test gets a stub; tests/test_registry_cross_ref_guard.py calls the real
    function (captured at import) against synthetic repos under tmp_path."""
    from src.walters import registry
    monkeypatch.setattr(registry, "cross_ref_guard",
                        lambda eid, no_fetch=False, repo=None: f"cross-ref guard: test stub ({eid})")
