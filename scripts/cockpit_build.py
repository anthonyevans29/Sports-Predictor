"""THE COCKPIT'S BUILD STAMP CHECK (ARCHITECT 2026-11-10 10:45 ET, addendum 319 item 3, verbatim): "the page carries
`COCKPIT_BUILD = "<PR number> · <YYYY-MM-DD>"` and shows it in the header chip ("build #911 · 2026-11-10"); every
Cockpit PR sets it to its own number and date — a test reads the constant and fails when tools/cockpit.html changed in
the PR and the constant did not".

`python scripts/ledger.py check-cockpit-build --base origin/main --pr N` (CI's fragments job, which has the history):
the head's tools/cockpit.html against the file at the merge-base with the base (as check-roadmap reads it, so a change
the base made after the branch point is never charged to the PR). 0 when the file is unchanged, or changed with a stamp
of its own (a new line, the PR's own number when --pr is given, a real date); 1 naming the fault; 2 when the base cannot
be read. Read-only.
"""
from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COCKPIT_REL = "tools/cockpit.html"
BUILD_RE = re.compile(r'^const COCKPIT_BUILD="(\d+) · (\d{4}-\d{2}-\d{2})";$', re.M)
ANY_BUILD_RE = re.compile(r"^const COCKPIT_BUILD=.*$", re.M)


def stamp(text: str | None) -> tuple[int, str] | None:
    """(PR number, date) of the page's COCKPIT_BUILD line, or None when there is no well-formed line (exactly one)."""
    if text is None or len(ANY_BUILD_RE.findall(text)) != 1:
        return None
    m = BUILD_RE.search(text)
    return (int(m.group(1)), m.group(2)) if m else None


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def check_base(base_ref: str, root: Path | None = None, pr: int | None = None, echo=print) -> int:
    root = Path(root or ROOT)
    if _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}").returncode != 0:
        echo(f"✗ COCKPIT BUILD: the base {base_ref!r} is not a commit here: nothing can be compared")
        return 2
    mb = _git(root, "merge-base", base_ref, "HEAD")
    if mb.returncode != 0 or not mb.stdout.strip():
        echo(f"✗ COCKPIT BUILD: the head has no merge-base with {base_ref}: nothing can be compared")
        return 2
    point = mb.stdout.strip()
    at = f"{base_ref} (merge-base {point[:7]})"
    head_path = root / COCKPIT_REL
    head = head_path.read_bytes() if head_path.exists() else None
    shown = subprocess.run(["git", "-C", str(root), "show", f"{point}:{COCKPIT_REL}"], capture_output=True)
    if shown.returncode != 0 and _git(root, "cat-file", "-e", f"{point}:{COCKPIT_REL}").returncode == 0:
        echo(f"✗ COCKPIT BUILD: {COCKPIT_REL} on {at} cannot be read")
        return 2
    base = shown.stdout if shown.returncode == 0 else None
    if head == base:
        echo(f"✓ COCKPIT BUILD: {COCKPIT_REL} is unchanged against {at}")
        return 0
    if head is None:
        echo(f"✗ COCKPIT BUILD: {COCKPIT_REL} is removed on the head: a PR that changes the page "
             f"carries its stamp, and a removed page cannot")
        return 1
    h = stamp(head.decode("utf-8", "replace"))
    if h is None:
        echo(f'✗ COCKPIT BUILD: {COCKPIT_REL} changed and carries no single line '
             f'const COCKPIT_BUILD="<PR number> · <YYYY-MM-DD>"; (addendum 319 item 3)')
        return 1
    b = stamp(base.decode("utf-8", "replace")) if base is not None else None
    faults = []
    if b is not None and h == b:
        faults.append(f"the stamp is the base's ({b[0]} · {b[1]}): a PR that changes the page sets its own")
    if pr is not None and h[0] != pr:
        faults.append(f"the stamp names #{h[0]}, the PR is #{pr}")
    try:
        date.fromisoformat(h[1])
    except ValueError:
        faults.append(f"the stamp's date {h[1]} is not a date")
    if faults:
        for f in faults:
            echo(f"✗ COCKPIT BUILD: {COCKPIT_REL} changed; {f}")
        return 1
    echo(f"✓ COCKPIT BUILD: {COCKPIT_REL} changed and carries its own stamp: build #{h[0]} · {h[1]}")
    return 0
