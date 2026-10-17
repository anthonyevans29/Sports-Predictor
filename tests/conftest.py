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


@pytest.fixture(autouse=True)
def _no_machine_role(monkeypatch):
    """Addendum 109 item 3 (#410): the Desk's host fence reads the machine's SP_EXPORTS_MIRROR_ROLE, from host.env
    (SP_HOST_ENV) first, then the environment. No test inherits the machine's role (a real host.env, host.env exported
    into the shell, a .env read by config.py's load_dotenv): a test that needs one sets it (tests/test_desk_host_fence.py's
    role fixture, tests/test_closing_runs.py's box). Per test, since load_dotenv runs after this file is imported."""
    monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)
    monkeypatch.setenv("SP_HOST_ENV", str(_TMP / "no-host.env"))
