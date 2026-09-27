#!/usr/bin/env python3
"""Code deploy on the host: fast-forward to merged origin/main only, receipted.

The host never builds from a branch and never pushes. RESULTS.md is the one
tracked file the host rewrites (results-tally, H0-9); it is restored before
the pull so the fast-forward cannot conflict (it is regenerated next morning).
Any OTHER local modification refuses the deploy. Run as the sp user, under
the DB lock so no chain is mid-run. Migrations named in merge notes are run
by hand afterwards, after a backup (hosting-h1.md, "Deploying a merge").
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(c.REPO), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    c.load_host_env()
    with c.db_lock():
        before = git("rev-parse", "--short", "HEAD")
        if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
            raise SystemExit("✗ checkout is not on main — refusing.")
        dirty = [ln[3:] for ln in git("status", "--porcelain", "--untracked-files=no").splitlines()]
        if [p for p in dirty if p != "RESULTS.md"]:
            raise SystemExit(f"✗ local modifications {dirty} — refusing.")
        if dirty:
            git("checkout", "--", "RESULTS.md")
        git("fetch", "origin", "main")
        git("merge", "--ff-only", "origin/main")
        after = git("rev-parse", "--short", "HEAD")
        changed = git("diff", "--name-only", before, after).splitlines() if before != after else []
    migs = [p for p in changed if p.startswith("migrate_") and p.endswith(".py")]
    c.append_receipt({"kind": "deploy", "exit": 0, "from_sha": before, "to_sha": after,
                      "files_changed": len(changed), "new_migrations": migs})
    print(f"✓ deploy {before} -> {after} ({len(changed)} files)"
          + (f"\n  ! migrations in this range (backup first, then run by hand): {migs}" if migs else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
