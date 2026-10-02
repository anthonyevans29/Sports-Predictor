"""ARCHITECT-RULE 2026-10-02: per-PR ledger fragments. compile folds
changelog.d/ and docs/ledger/entries/ into CHANGELOG.md / BACKLOG.md newest
first and deletes them (refusing malformed fragments before touching
anything); the CI rule fails a PR that edits the shared files (except a pure
compile) or lacks a fragment named for the PR; sp_deploy only reports.
Temporary trees; the repo's own files are never touched."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger_fragments as lf  # noqa: E402

CL = "# Changelog\n\nintro\n\n## 2026-10-01 (old)\n- old\n"
BL = "# Backlog\n\n### MLB / baseball\n\n**2026-10-01 — old entry.**\n- old\n"


def tree(tmp_path, cl=None, en=None):
    (tmp_path / "CHANGELOG.md").write_text(CL)
    (tmp_path / "BACKLOG.md").write_text(BL)
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "docs/ledger/entries").mkdir(parents=True)
    (tmp_path / "changelog.d/README.md").write_text("readme stays")
    for name, text in (cl or {}).items():
        (tmp_path / "changelog.d" / name).write_text(text)
    for name, text in (en or {}).items():
        (tmp_path / "docs/ledger/entries" / name).write_text(text)
    return tmp_path


def test_compile_folds_newest_first_and_deletes(tmp_path):
    t = tree(tmp_path,
             cl={"240-a.md": "## 2026-10-02 (#240: a)\n- a\n", "250-b.md": "## 2026-10-02 (#250: b)\n- b\n",
                 "230-c.md": "## 2026-10-03 (#230: c)\n- c\n"},
             en={"2026-10-02-a.md": "**2026-10-02 — a.**\n- a\n", "2026-10-03-c.md": "**2026-10-03 — c.**\n- c\n"})
    out = lf.compile_fragments(t)
    assert (out["changelog_sections"], out["ledger_entries"]) == (3, 2)
    c = (t / "CHANGELOG.md").read_text()
    assert c.index("#230: c") < c.index("#250: b") < c.index("#240: a") < c.index("(old)")   # date, then PR desc
    assert c.startswith("# Changelog\n\nintro\n")
    b = (t / "BACKLOG.md").read_text()
    assert b.index("2026-10-03 — c.") < b.index("2026-10-02 — a.") < b.index("old entry")
    assert b.index("### MLB / baseball") < b.index("2026-10-03 — c.")
    assert not list((t / "changelog.d").glob("2*.md")) and not list((t / "docs/ledger/entries").glob("*.md"))
    assert (t / "changelog.d/README.md").exists()                                         # README is not a fragment
    assert lf.compile_fragments(t) == {"changelog_sections": 0, "ledger_entries": 0, "files": []}


def test_compile_refuses_a_malformed_fragment_before_touching_anything(tmp_path):
    t = tree(tmp_path, cl={"240-a.md": "## 2026-10-02 (#240)\n- ok\n", "241-b.md": "no heading\n"})
    with pytest.raises(lf.FragmentError, match="dated heading"):
        lf.compile_fragments(t)
    assert (t / "CHANGELOG.md").read_text() == CL and (t / "changelog.d/240-a.md").exists()


def test_dry_run_changes_nothing(tmp_path):
    t = tree(tmp_path, cl={"240-a.md": "## 2026-10-02 (#240)\n- a\n"})
    assert lf.compile_fragments(t, dry_run=True)["changelog_sections"] == 1
    assert (t / "CHANGELOG.md").read_text() == CL and (t / "changelog.d/240-a.md").exists()


def test_ci_rule():
    ok = [("A", "changelog.d/243-x.md"), ("A", "docs/ledger/entries/2026-10-02-x.md"), ("M", "src/a.py")]
    assert lf.check_pr(ok, 243) == []
    assert any("directly" in f for f in lf.check_pr(ok + [("M", "BACKLOG.md")], 243))
    assert any("named for this PR" in f for f in lf.check_pr(ok, 999))
    assert any("no docs/ledger/entries" in f for f in lf.check_pr(ok[:1], 243))
    assert any("no changelog.d" in f for f in lf.check_pr(ok[1:], 243))
    assert lf.check_pr([("A", "changelog.d/README.md"), ("A", "docs/ledger/entries/2026-10-02-x.md")], 5)
    compile_pr = [("M", "CHANGELOG.md"), ("M", "BACKLOG.md"), ("D", "changelog.d/243-x.md"),
                  ("D", "docs/ledger/entries/2026-10-02-x.md")]
    assert lf.check_pr(compile_pr, 300) == []                                             # a pure compile passes
    assert lf.check_pr(compile_pr + [("M", "src/a.py")], 300)                             # compile + code fails


def test_check_against_a_real_git_diff(tmp_path):
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)  # noqa: E731
    tree(tmp_path)
    g("init", "-q", "-b", "main")
    g("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
    g("checkout", "-q", "-b", "feature")
    (tmp_path / "changelog.d/7-x.md").write_text("## 2026-10-02 (#7)\n- x\n")
    (tmp_path / "docs/ledger/entries/2026-10-02-x.md").write_text("**2026-10-02 — x.**\n")
    g("add", "-A")
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "f")
    assert lf.check_pr(lf.diff_changes("main", tmp_path), 7) == []


def test_ledger_cli_dispatches_offline(tmp_path, monkeypatch, capsys):
    import ledger
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(lf, "ROOT", tree(tmp_path, cl={"9-a.md": "## 2026-10-02 (#9)\n- a\n"}))
    monkeypatch.setattr(lf, "changelog_fragments", lambda root=None: lf._frags(tmp_path, lf.CHANGELOG_D, lf.CL_NAME))
    monkeypatch.setattr(lf, "entry_fragments", lambda root=None: lf._frags(tmp_path, lf.ENTRIES_D, lf.EN_NAME))
    assert ledger.main(["pending"]) == 0 and "1 changelog fragment" in capsys.readouterr().out
    assert ledger.main(["compile", "--dry-run"]) == 0 and "(dry run)" in capsys.readouterr().out
