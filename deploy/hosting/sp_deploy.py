#!/usr/bin/env python3
"""Code deploy on the host: check out a RELEASE TAG only, receipted.

RELEASE MODEL (architect 2026-09-30): `main` is BETA (the laptop tracks it);
PRODUCTION is tagged releases only. The host never pulls `main` again: this
fetches tags and checks out the latest `vX.Y.Z` (detached), or the exact
`--tag` given (a rollback or a pinned patch is explicit). A tag is cut only
by the architect's ruling after the day's laptop-vs-host compare passes
(docs/RELEASES.md); a hotfix is a patch tag through the same ritual.

    sp_deploy.py [--tag v1.0.1] [--dry-run]

Refuses: no release tag on origin (the host stays where it is — never falls
back to main); an unknown --tag; a checkout on a branch other than main
(main is accepted once, for the first pin); a moved tag (git refuses to
clobber a local tag); any local modification except RESULTS.md, which the
host rewrites (results-tally, H0-9) and is restored first. The host never
builds from a branch and never pushes. Run as the sp user, under the DB lock
so no chain is mid-run. Migrations in the range are run by hand afterwards,
after a backup (hosting-h1.md, "Deploying a release").
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def git(*args: str, strip: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(c.REPO), *args], check=True,
                         capture_output=True, text=True).stdout
    return out.strip() if strip else out


def dirty_paths() -> list[str]:
    """Modified tracked paths. Porcelain lines are 'XY path': the output must
    NOT be stripped first — a leading ' M' would lose its space and the path
    its first letter (the pre-release deploy read ' M RESULTS.md' as
    'ESULTS.md' and refused the very case it meant to allow)."""
    return [ln[3:] for ln in git("status", "--porcelain", "--untracked-files=no", strip=False).splitlines()
            if ln.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deploy a release tag (production = tags only).")
    ap.add_argument("--tag", default=None, help="Exact release tag (vX.Y.Z); default: the latest.")
    ap.add_argument("--dry-run", action="store_true", help="Fetch and name the target; change nothing.")
    a = ap.parse_args(argv)
    c.load_host_env()
    if a.tag is not None and not c.release_key(a.tag):
        raise SystemExit(f"✗ --tag {a.tag!r} is not a release tag (vMAJOR.MINOR.PATCH) — refusing.")
    with c.db_lock():
        before, before_rel = git("rev-parse", "--short", "HEAD"), c.running_release()
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        if branch not in ("HEAD", "main"):
            raise SystemExit(f"✗ checkout is on branch {branch!r} — refusing (production runs tags only).")
        dirty = dirty_paths()
        if [p for p in dirty if p != "RESULTS.md"]:
            raise SystemExit(f"✗ local modifications {dirty} — refusing.")
        git("fetch", "--tags", "origin")               # a moved tag fails here (no clobber): refused
        tags = git("tag", "-l", "v*").split()
        target = a.tag or c.latest_release(tags)
        if target is None:
            raise SystemExit("✗ no release tag (vX.Y.Z) on origin — refusing; the host stays at "
                             f"{before_rel or before}. Production runs tags only; main is never pulled.")
        if target not in tags:
            raise SystemExit(f"✗ tag {target} not found on origin — refusing.")
        target_sha = git("rev-parse", "--short", f"{target}^{{commit}}")
        if a.dry_run:
            print(f"DRY RUN: would deploy {before_rel or before} -> {target} ({target_sha})")
            return 0
        if dirty:
            git("checkout", "--", "RESULTS.md")
        git("checkout", "--quiet", "--detach", f"{target}^{{commit}}")
        after, after_rel = git("rev-parse", "--short", "HEAD"), c.running_release()
        # ARCHITECT-RULE 2026-10-02 (per-PR fragments): the fold runs in the tag ritual on main
        # (`ledger.py compile --commit`); the host never commits, so this step only REPORTS what the
        # deployed tag still carries uncompiled (expected 0).
        pending = sorted(str(p.relative_to(c.REPO)) for d in ("changelog.d", "docs/ledger/entries")
                         for p in (Path(c.REPO) / d).glob("*.md") if p.name != "README.md")
        changed = git("diff", "--name-only", before, after).splitlines() if before != after else []
    migs = [p for p in changed if p.startswith("migrate_") and p.endswith(".py")]
    c.append_receipt({"kind": "deploy", "exit": 0, "from_sha": before, "to_sha": after,
                      "from_release": before_rel, "to_release": after_rel, "tag": target,
                      "files_changed": len(changed), "new_migrations": migs,
                      "ledger_fragments_pending": len(pending)})
    print(f"✓ deploy {before_rel or before} -> {after_rel} ({after}, {len(changed)} files)"
          + (f"\n  ! migrations in this range (backup first, then run by hand): {migs}" if migs else "")
          + (f"\n  ! {len(pending)} ledger fragment(s) uncompiled in {target} — the tag was cut without "
             "`ledger.py compile` (docs/RELEASES.md step 2)" if pending else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
