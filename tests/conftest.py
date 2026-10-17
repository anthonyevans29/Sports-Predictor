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
def _machine_role_laptop(monkeypatch):
    """Addendum 109 item 3 + addendum 110 item 1 (#410): the Desk's host fence reads the machine's
    SP_EXPORTS_MIRROR_ROLE from host.env (SP_HOST_ENV) first, then the environment, then the checkout's .env
    (desk_policy.DOTENV), and fences every soccer model row unless the role is exactly laptop. Every test runs pinned
    to laptop, in the environment, with both files pointed at a path that does not exist: no test inherits the
    machine's role (a real host.env, a role exported into the shell, a .env read by config.py's load_dotenv), and a
    child process inherits the pin. A test that needs another role, or none, sets or deletes it
    (tests/test_desk_host_fence.py's role fixture, tests/test_closing_runs.py's box). Per test, since load_dotenv
    runs after this file is imported."""
    from src.walters import desk_policy
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    monkeypatch.setenv("SP_HOST_ENV", str(_TMP / "no-host.env"))
    monkeypatch.setattr(desk_policy, "DOTENV", _TMP / "no.env")
