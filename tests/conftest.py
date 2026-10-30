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
# sync-teams / sync-matches take the chains' DB lock (#569): a test's sync locks a file under the throwaway dir, never
# the checkout's logs/db.lock nor a lock path the launching shell exported (Codex on #650: set, not setdefault); a
# test that names its own lock sets SP_LOCK (monkeypatch), which wins. A lock marker inherited from a holding run is
# cleared, so no test skips the lock as a step of one.
os.environ["SP_LOCK"] = str(_TMP / "db.lock")
os.environ.pop("SP_DB_LOCK_HELD", None)

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
    (desk_policy.DOTENV), and, while its switch is on (HOST_FENCE_RULE: off from addendum 166 item 6(A); the fence's
    own tests turn it on), fences every soccer model row unless the role is exactly laptop. Every test runs pinned
    to laptop, in the environment, with both files pointed at a path that does not exist: no test inherits the
    machine's role (a real host.env, a role exported into the shell, a .env read by config.py's load_dotenv), and a
    child process inherits the pin. A test that needs another role, or none, sets or deletes it
    (tests/test_desk_host_fence.py's role fixture, tests/test_closing_runs.py's box). Per test, since load_dotenv
    runs after this file is imported."""
    from src.walters import desk_policy
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    monkeypatch.setenv("SP_HOST_ENV", str(_TMP / "no-host.env"))
    monkeypatch.setattr(desk_policy, "DOTENV", _TMP / "no.env")


@pytest.fixture(autouse=True)
def _desk_unit_pinned(monkeypatch, tmp_path):
    """Addendum 179 (#732, Desk policy v1.2): the Desk sizes its order lines from the day's unit file
    (src/walters/desk_unit.py, logs/desk_unit_<ET date>.json, folder SP_DESK_UNIT_DIR). No test reads or writes the
    checkout's logs/: the folder is a per-test path under tmp_path that does not exist, and no test inherits a floor
    (SP_UNIT_FLOOR_USD) or the retired SP_UNIT_USD from the launching shell. As the machine's role is pinned above,
    every test is pinned to the pre-v1.2 contracts basis (desk_policy.UNIT_PIN = LEGACY_CONTRACTS_BASIS: 10 contracts
    per 1u, the label a file exported with SP_UNIT_USD unset carries), so the other rules' tests keep their order
    lines; a test of the unit itself lifts the pin (tests/test_desk_unit_fraction.py's `day` fixture)."""
    from src.walters import desk_policy
    monkeypatch.setenv("SP_DESK_UNIT_DIR", str(tmp_path / "desk-unit-none"))
    monkeypatch.delenv("SP_UNIT_FLOOR_USD", raising=False)
    monkeypatch.delenv("SP_UNIT_USD", raising=False)
    monkeypatch.setattr(desk_policy, "UNIT_PIN", desk_policy.LEGACY_CONTRACTS_BASIS)


@pytest.fixture(autouse=True)
def _no_live_kalshi_pool_read(monkeypatch):
    """Addenda 186-187 (#734): kalshi_pool.POOL_FIELDS holds the real names, so a read with no fake fetch would sign a
    GET to Kalshi PROD on any machine with a key. No test ever does: the key's names are cleared (config's load_dotenv
    may have set them from the checkout's .env) and signed_fetch refuses; a test of the read passes its own fake fetch.
    The figures' role is pinned too: desk_unit.figures_allowed reads config.PROCESS_ENV_ROLE (captured at import,
    before load_dotenv, addendum 183 item 2(1)), set here to the laptop pin above; a test that needs another role sets
    it."""
    import config
    from src.walters import kalshi_pool
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)

    def refused():
        raise AssertionError("a test reached kalshi_pool.signed_fetch: no test signs a Kalshi request")
    monkeypatch.setattr(kalshi_pool, "signed_fetch", refused)
    monkeypatch.setattr(config, "PROCESS_ENV_ROLE", "laptop")
