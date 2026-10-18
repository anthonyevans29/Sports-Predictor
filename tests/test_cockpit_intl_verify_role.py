"""#591 (ARCHITECT 2026-10-18, addendum 128 item 4, verbatim): "#591 (the intl verifier fails 3/8 with no role set) —
approved as proposed: the verifier pins SP_EXPORTS_MIRROR_ROLE=laptop for its own process and says so in its header."

scripts/cockpit_intl_verify.py drives Chromium through Playwright, which CI does not install, so the verifier itself is
run by hand (with no role set: 3/8 before, 8/8 after). This test loads it with Playwright stubbed and checks that its
pin holds over every source desk_policy.role_reading reads, first to last: a host.env that says host, a role exported
as host, no role anywhere (tests/conftest.py's pin taken away first). Before: the role stayed host or unknown, and the
host fence (#410) made every INTL row PASS host_fence. The pin is the verifier's own process: the environment is put
back after each test (monkeypatch recorded both keys)."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from src.walters import desk_policy as dp

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "cockpit_intl_verify.py"


def load_verifier(monkeypatch):
    """Execute the verifier's module body (main() is not run) with playwright.sync_api stubbed."""
    pw, api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
    api.sync_playwright = lambda: None
    monkeypatch.setitem(sys.modules, "playwright", pw)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    monkeypatch.setattr(sys, "path", list(sys.path))                  # the verifier inserts its own paths
    spec = importlib.util.spec_from_file_location("cockpit_intl_verify_under_test", VERIFY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("case", ["host.env says host", "exported host", "no role anywhere"])
def test_the_intl_verifier_pins_the_laptop_role_for_its_own_process(case, tmp_path, monkeypatch):
    monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)       # conftest's pin, taken away
    if case == "host.env says host":
        (tmp_path / "host.env").write_text("SP_EXPORTS_MIRROR_ROLE=host\n")
        monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "host.env"))
    elif case == "exported host":
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    intl = {"sport": "INTL"}
    assert dp.machine_role() != "laptop" and dp.host_fenced(intl)     # as the verifier found it: fenced
    load_verifier(monkeypatch)
    assert dp.role_reading() == ("laptop", "laptop")
    assert dp.host_fenced(intl) is None and dp.host_fenced({"sport": "SOCCER"}) is None


def test_the_intl_verifier_header_says_it_pins_the_role():
    doc = load_doc()
    assert "SP_EXPORTS_MIRROR_ROLE=laptop" in doc and "addendum 128 item 4" in doc and "#591" in doc


def load_doc() -> str:
    import ast
    return ast.get_docstring(ast.parse(VERIFY.read_text(encoding="utf-8"))) or ""
