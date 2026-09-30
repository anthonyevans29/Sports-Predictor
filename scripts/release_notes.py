#!/usr/bin/env python3
"""Release notes = the CHANGELOG slice since the previous tag (release model,
architect 2026-09-30). Read-only: prints markdown; cuts, pushes and writes
nothing — the tag is cut by the architect's ruling (docs/RELEASES.md).

    python3 scripts/release_notes.py [--to HEAD] [--from v1.0.0]

The slice is every `## ` section of CHANGELOG.md at --to whose heading is
not in CHANGELOG.md at --from (default: the latest vX.Y.Z tag that is an
ancestor of --to). A section present at both whose body changed is listed as
AMENDED, never folded in silently. With no previous tag (the first release)
it prints the baseline line and the section count — the whole file is the
history, not a slice.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "deploy" / "hosting"))
import sp_common as c  # noqa: E402


def _git(*args: str, repo: Path = REPO) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def sections(text: str) -> list[tuple[str, str]]:
    """(heading line, body) for each `## ` section, file order."""
    out: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append((line.strip(), []))
        elif out:
            out[-1][1].append(line)
    return [(h, "\n".join(b).strip()) for h, b in out]


def slice_since(old: str, new: str) -> tuple[list[tuple[str, str]], list[str]]:
    """(new sections, amended headings) of `new` relative to `old`."""
    before = dict(sections(old))
    added = [(h, b) for h, b in sections(new) if h not in before]
    amended = [h for h, b in sections(new) if h in before and before[h] != b]
    return added, amended


def previous_tag(to: str, repo: Path = REPO) -> str | None:
    tags = (_git("tag", "-l", "v*", "--merged", to, repo=repo) or "").split()
    head_tags = set((_git("tag", "--points-at", to, repo=repo) or "").split())
    return c.latest_release([t for t in tags if t not in head_tags])


def notes(to: str = "HEAD", frm: str | None = None, repo: Path = REPO) -> str:
    new = _git("show", f"{to}:CHANGELOG.md", repo=repo)
    if new is None:
        return f"✗ CHANGELOG.md not readable at {to}"
    sha = (_git("rev-parse", "--short", to, repo=repo) or "?").strip()
    frm = frm or previous_tag(to, repo)
    if frm is None:
        return (f"# Release notes · {to} ({sha})\n\nFIRST RELEASE — no previous tag: the baseline is "
                f"main at {sha}. CHANGELOG.md holds {len(sections(new))} sections of history; the next "
                f"release's notes are the slice since this tag.")
    old = _git("show", f"{frm}:CHANGELOG.md", repo=repo)
    if old is None:
        return f"✗ CHANGELOG.md not readable at {frm}"
    added, amended = slice_since(old, new)
    out = [f"# Release notes · {to} ({sha}) · since {frm}", "",
           f"{len(added)} CHANGELOG section(s) since {frm}."]
    for h, b in added:
        out += ["", h, b] if b else ["", h]
    if amended:
        out += ["", "AMENDED since the previous tag (bodies changed): " + " · ".join(amended)]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Print the CHANGELOG slice since the previous release tag.")
    ap.add_argument("--to", default="HEAD")
    ap.add_argument("--from", dest="frm", default=None)
    a = ap.parse_args(argv)
    text = notes(a.to, a.frm)
    print(text)
    return 1 if text.startswith("✗") else 0


if __name__ == "__main__":
    sys.exit(main())
