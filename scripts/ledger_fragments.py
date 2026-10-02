"""
PER-PR LEDGER FRAGMENTS (ARCHITECT-RULE 2026-10-02): "CHANGELOG/BACKLOG move
to per-PR FRAGMENTS. Each PR adds changelog.d/<PR>-<slug>.md and
docs/ledger/entries/<date>-<slug>.md (same content as today's entries); the
shared files are never edited by a feature PR. A `ledger compile` mode (and a
step in sp_deploy's tag path) folds fragments into CHANGELOG.md / BACKLOG.md
in date order and deletes them, in its own commit. CI fails a PR that edits
CHANGELOG.md or BACKLOG.md directly or lacks a fragment. Migrate open PRs on
the way in. This retires the merge-up ritual."

    python scripts/ledger.py compile [--commit] [--dry-run]
    python scripts/ledger.py check-fragments --base origin/main --pr N
    python scripts/ledger.py pending            # read-only count (sp_deploy)

Fragments:
  changelog.d/<PR>-<slug>.md        one CHANGELOG section ("## YYYY-MM-DD (...)")
  docs/ledger/entries/<date>-<slug>.md   one BACKLOG entry ("**YYYY-MM-DD — ...**")
compile folds them NEWEST FIRST (date, then PR number / name, descending):
CHANGELOG sections before the first existing "## " section; BACKLOG entries
right after the "### MLB / baseball" anchor (where entries have always gone).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_D = "changelog.d"
ENTRIES_D = "docs/ledger/entries"
BACKLOG_ANCHOR = "### MLB / baseball\n\n"
CL_NAME = re.compile(r"^(\d+)-[a-z0-9][a-z0-9-]*\.md$")
EN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9][a-z0-9-]*\.md$")
CL_HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b")
EN_HEAD = re.compile(r"^\*\*(\d{4}-\d{2}-\d{2})\b")
SHARED = ("CHANGELOG.md", "BACKLOG.md")


class FragmentError(RuntimeError):
    pass


def _frags(root: Path, d: str, name_rx) -> list[Path]:
    p = root / d
    return sorted(f for f in p.glob("*.md") if name_rx.match(f.name)) if p.is_dir() else []


def changelog_fragments(root: Path = ROOT) -> list[Path]:
    return _frags(root, CHANGELOG_D, CL_NAME)


def entry_fragments(root: Path = ROOT) -> list[Path]:
    return _frags(root, ENTRIES_D, EN_NAME)


def _body(f: Path, head_rx, what: str) -> tuple[str, str]:
    text = f.read_text().strip("\n")
    m = head_rx.match(text)
    if not m:
        raise FragmentError(f"{f}: a {what} fragment must start with its dated heading (got {text[:40]!r})")
    return m.group(1), text


def compile_fragments(root: Path = ROOT, dry_run: bool = False) -> dict:
    """Fold every fragment into CHANGELOG.md / BACKLOG.md (newest first) and
    delete it. Refuses on a malformed fragment or a missing anchor, before
    touching anything."""
    cl = []
    for f in changelog_fragments(root):
        date, text = _body(f, CL_HEAD, "changelog")
        cl.append(((date, int(CL_NAME.match(f.name).group(1))), text, f))
    en = []
    for f in entry_fragments(root):
        date, text = _body(f, EN_HEAD, "ledger entry")
        en.append(((date, f.name), text, f))
    cl.sort(key=lambda x: x[0], reverse=True)
    en.sort(key=lambda x: x[0], reverse=True)
    changelog, backlog = root / "CHANGELOG.md", root / "BACKLOG.md"
    c_text, b_text = changelog.read_text(), backlog.read_text()
    if cl:
        i = c_text.find("\n## ")
        if i < 0:
            raise FragmentError("CHANGELOG.md has no '## ' section to insert before")
        c_text = c_text[:i] + "\n" + "\n\n".join(t for _, t, _ in cl) + "\n" + c_text[i:]
    if en:
        if BACKLOG_ANCHOR not in b_text:
            raise FragmentError(f"BACKLOG.md lacks the anchor {BACKLOG_ANCHOR!r}")
        b_text = b_text.replace(BACKLOG_ANCHOR, BACKLOG_ANCHOR + "".join(t + "\n\n" for _, t, _ in en), 1)
    out = {"changelog_sections": len(cl), "ledger_entries": len(en),
           "files": [str(f.relative_to(root)) for _, _, f in cl + en]}
    if dry_run or not (cl or en):
        return out
    changelog.write_text(c_text)
    backlog.write_text(b_text)
    for _, _, f in cl + en:
        f.unlink()
    return out


def commit(root: Path, out: dict) -> str | None:
    """The fold's OWN commit (nothing else staged with it)."""
    if not out["files"]:
        return None
    paths = list(SHARED) + out["files"]
    subprocess.run(["git", "-C", str(root), "add", "-A", "--", *paths], check=True)
    msg = (f"ledger compile: fold {out['changelog_sections']} changelog fragment(s) and "
           f"{out['ledger_entries']} ledger entr(y/ies) into CHANGELOG.md / BACKLOG.md")
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", msg, "--", *paths], check=True)
    return msg


def check_pr(changes: list[tuple[str, str]], pr: int | None) -> list[str]:
    """CI rule. `changes` = (status, path) from `git diff --name-status base...HEAD`
    (first letter of status). Returns the failures (empty = pass).
      * A PR that edits CHANGELOG.md / BACKLOG.md fails — unless it is a pure
        COMPILE: only the shared files plus DELETED fragments.
      * Otherwise the PR must ADD >= 1 changelog.d fragment (named
        <this PR's number>-<slug>.md when the number is known) and >= 1
        docs/ledger/entries fragment."""
    shared = [p for s, p in changes if p in SHARED]
    is_frag = lambda p: (p.startswith(CHANGELOG_D + "/") and CL_NAME.match(Path(p).name)) or \
        (p.startswith(ENTRIES_D + "/") and EN_NAME.match(Path(p).name))  # noqa: E731
    if shared:
        rest = [(s, p) for s, p in changes if p not in SHARED]
        if rest and all(s == "D" and is_frag(p) for s, p in rest):
            return []                                              # a pure compile PR
        return [f"edits {', '.join(shared)} directly — feature PRs add fragments instead "
                f"({CHANGELOG_D}/<PR>-<slug>.md + {ENTRIES_D}/<date>-<slug>.md); only `ledger compile` folds them"]
    added = [p for s, p in changes if s in ("A", "R", "C")]
    cl = [p for p in added if p.startswith(CHANGELOG_D + "/") and CL_NAME.match(Path(p).name)]
    en = [p for p in added if p.startswith(ENTRIES_D + "/") and EN_NAME.match(Path(p).name)]
    fails = []
    if not cl:
        fails.append(f"adds no {CHANGELOG_D}/<PR>-<slug>.md fragment")
    elif pr is not None and not any(CL_NAME.match(Path(p).name).group(1) == str(pr) for p in cl):
        fails.append(f"no {CHANGELOG_D} fragment is named for this PR ({pr}-<slug>.md)")
    if not en:
        fails.append(f"adds no {ENTRIES_D}/<YYYY-MM-DD>-<slug>.md fragment")
    return fails


def diff_changes(base: str, root: Path = ROOT) -> list[tuple[str, str]]:
    out = subprocess.run(["git", "-C", str(root), "diff", "--name-status", "--find-renames", f"{base}...HEAD"],
                         check=True, capture_output=True, text=True).stdout
    rows = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        rows.append((parts[0][0], parts[-1]))
    return rows


def main(argv: list[str]) -> int:
    mode, args = argv[0], argv[1:]
    if mode == "compile":
        try:
            out = compile_fragments(ROOT, dry_run="--dry-run" in args)
        except FragmentError as e:
            print(f"✗ REFUSED: {e}")
            return 2
        print(f"LEDGER-COMPILE{' (dry run)' if '--dry-run' in args else ''}: {out['changelog_sections']} "
              f"changelog section(s), {out['ledger_entries']} ledger entr(y/ies)")
        for f in out["files"]:
            print(f"  {f}")
        if "--commit" in args and "--dry-run" not in args:
            msg = commit(ROOT, out)
            print(f"  committed: {msg}" if msg else "  nothing to commit")
        return 0
    if mode == "pending":
        n_cl, n_en = len(changelog_fragments()), len(entry_fragments())
        print(f"LEDGER-PENDING: {n_cl} changelog fragment(s), {n_en} ledger entr(y/ies) not yet compiled")
        return 0
    if mode == "check-fragments":
        base = args[args.index("--base") + 1] if "--base" in args else "origin/main"
        pr = int(args[args.index("--pr") + 1]) if "--pr" in args and args[args.index("--pr") + 1] else None
        fails = check_pr(diff_changes(base), pr)
        if fails:
            for f in fails:
                print(f"✗ FRAGMENTS: this PR {f}")
            print("  See changelog.d/README.md (ARCHITECT-RULE 2026-10-02).")
            return 1
        print("✓ FRAGMENTS: the PR adds its fragments and leaves CHANGELOG.md / BACKLOG.md alone")
        return 0
    raise SystemExit(f"unknown fragments mode {mode!r}")
