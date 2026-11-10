"""THE COCKPIT'S BUILD STAMP (ARCHITECT 2026-11-10 10:45 ET, addendum 319 item 3, verbatim): "the page carries
`COCKPIT_BUILD = "<PR number> · <YYYY-MM-DD>"` and shows it in the header chip ("build #911 · 2026-11-10"); every
Cockpit PR sets it to its own number and date — a test reads the constant and fails when tools/cockpit.html changed in
the PR and the constant did not". The page's stamp and chip are read here; the changed-without-a-stamp rule is
scripts/cockpit_build.check_base (CI: `ledger.py check-cockpit-build`, in the job that has the base), exercised on
throwaway git repositories. No logic of the page changes."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cockpit_build as cb  # noqa: E402

COCKPIT = ROOT / "tools" / "cockpit.html"


def test_the_page_carries_one_stamp_and_its_header_chip_shows_it():
    html = COCKPIT.read_text(encoding="utf-8")
    got = cb.stamp(html)
    assert got is not None, "one line: const COCKPIT_BUILD=\"<PR number> · <YYYY-MM-DD>\";"
    assert '<span class="chip" id="buildChip"></span></h1>' in html
    assert 'el.textContent="build #"+COCKPIT_BUILD;' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_chip_reads_build_number_and_date_in_the_browser_shape():
    html = COCKPIT.read_text(encoding="utf-8")
    line = re.search(r"^const COCKPIT_BUILD=.*$", html, re.M).group(0)
    block = re.search(r'^\{ const el=document\.getElementById\("buildChip"\);.*\}$', html, re.M).group(0)
    js = ("const chip={textContent:''};const document={getElementById:id=>id==='buildChip'?chip:null};"
          + line + block + "process.stdout.write(chip.textContent);")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert out == "build #" + re.search(r'COCKPIT_BUILD="([^"]+)"', line).group(1)


def test_stamp_reads_one_well_formed_line_only():
    assert cb.stamp('x\nconst COCKPIT_BUILD="911 · 2026-11-10";\ny') == (911, "2026-11-10")
    assert cb.stamp("no stamp here") is None
    assert cb.stamp('const COCKPIT_BUILD="911";') is None
    assert cb.stamp('const COCKPIT_BUILD="911 · 2026-11-10";\nconst COCKPIT_BUILD="912 · 2026-11-11";') is None


# --- the CI rule: tools/cockpit.html against the merge-base, by git ---

@pytest.fixture(autouse=True)
def _plain_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _g(root):
    return ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
            "-c", "core.hooksPath=/dev/null"]


PAGE = '<h1>Cockpit</h1>\n<script>\nconst COCKPIT_BUILD="{n} · {d}";\nlet x={x};\n</script>\n'


def _repo(tmp_path, base_page):
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    if base_page is not None:
        (root / "tools" / "cockpit.html").write_text(base_page, encoding="utf-8")
    (root / "README").write_text("x")
    subprocess.run(_g(root) + ["add", "-A"], check=True)
    subprocess.run(_g(root) + ["commit", "-q", "-m", "base"], check=True)
    subprocess.run(_g(root) + ["branch", "base"], check=True)
    return root


def _head(root, page):
    (root / "tools" / "cockpit.html").write_text(page, encoding="utf-8")
    subprocess.run(_g(root) + ["commit", "-q", "-am", "head"], check=True)


def _check(root, pr=None):
    out = []
    return cb.check_base("base", root, pr, echo=out.append), out


def test_an_unchanged_page_needs_no_stamp(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    (root / "README").write_text("y")
    subprocess.run(_g(root) + ["commit", "-q", "-am", "other"], check=True)
    rc, out = _check(root, pr=950)
    assert rc == 0 and "unchanged" in out[0]


def test_a_changed_page_with_the_base_stamp_fails(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    _head(root, PAGE.format(n=911, d="2026-11-10", x=2))
    rc, out = _check(root, pr=950)
    assert rc == 1 and any("the stamp is the base's" in x for x in out)


def test_a_changed_page_with_its_own_stamp_passes(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    _head(root, PAGE.format(n=950, d="2026-11-11", x=2))
    rc, out = _check(root, pr=950)
    assert rc == 0 and out == ["✓ COCKPIT BUILD: tools/cockpit.html changed and carries its own stamp: "
                               "build #950 · 2026-11-11"]


def test_a_stamp_naming_another_pr_or_no_real_date_fails(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    _head(root, PAGE.format(n=949, d="2026-13-40", x=2))
    rc, out = _check(root, pr=950)
    assert rc == 1 and any("names #949, the PR is #950" in x for x in out)
    assert any("is not a date" in x for x in out)


def test_a_changed_page_without_a_stamp_line_fails(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    _head(root, "<h1>Cockpit</h1>\n")
    rc, out = _check(root, pr=950)
    assert rc == 1 and "carries no single line" in out[0]


def test_the_first_stamp_on_a_base_without_one_passes(tmp_path):
    root = _repo(tmp_path, "<h1>Cockpit</h1>\n")
    _head(root, PAGE.format(n=950, d="2026-11-10", x=1))
    assert _check(root, pr=950)[0] == 0


def test_a_removed_page_fails(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    subprocess.run(_g(root) + ["rm", "-q", "tools/cockpit.html"], check=True)
    subprocess.run(_g(root) + ["commit", "-q", "-m", "head"], check=True)
    rc, out = _check(root, pr=950)
    assert rc == 1 and out == ["✗ COCKPIT BUILD: tools/cockpit.html is removed on the head: a PR that changes "
                               "the page carries its stamp, and a removed page cannot"]


def test_a_base_that_is_not_a_commit_is_exit_2(tmp_path):
    root = _repo(tmp_path, PAGE.format(n=911, d="2026-11-10", x=1))
    out = []
    assert cb.check_base("no-such-ref", root, 950, echo=out.append) == 2


def test_the_ledger_mode_refuses_a_bad_pr_argument():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "ledger.py"), "check-cockpit-build", "--pr", "x"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "is not a number" in r.stdout
