"""
THE SCHEMA CHECK (#950; ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 2): a PR that changes the stored schema's DDL
ships a NEW migrate_*.py, or CI refuses it.

358 item 2, verbatim: "(c) THE CHECK — RULED: SCOPE B. 354 item 2(a) said "a change to the stored schema" and it is
read literally: a NEW TABLE ships with its migrate file too. A table that appears on the live DB because whichever chain
ran first called init_db is a schema change nobody ordered, taken with no .backup before it and written on no deploy
receipt; the migrate file puts it in the plan, under the deploy's one lock, after the backup, on the record (laws 5 and
6). Seven of the twelve new-table PRs already did it. Build `scripts/schema_ddl_check.py` and its CI job as your
prototype has it (the compiled objects at base and head, whitespace collapsed, VARCHAR lengths dropped, a comment-only
edit never tripping; a changed or added object of any kind with no new `migrate_*.py` in the PR refuses), with the
replay table in the PR and its stated limits in CONTRIBUTING (DDL outside the metadata; a backfill with no DDL)."

HOW: src/ at the base revision (and at --head, or this working tree) is compiled into an in-memory SQLite
(`Base.metadata.create_all` on `sqlite://`, DATABASE_URL=sqlite:// for the import: no file is created anywhere), and
`sqlite_master` is read: every table, index and trigger, including the triggers schema.py attaches by `after_create`.
Each object's SQL is normalised (whitespace collapsed, `VARCHAR(n)` read as `VARCHAR`, as SQLite does not enforce the
length), then base and head are compared object by object:
  - CHANGED / ADDED objects (any kind: a table, an index, a trigger, on an existing table or a new one) need a NEW
    top-level migrate_*.py in the PR (added between the merge base and head, the name sp_deploy's plan reads:
    `^migrate_[A-Za-z0-9_]+\\.py$` at the repository root). Without one: REFUSED.
  - REMOVED objects are printed as information: a table dropped from the metadata stays on the live DB (nothing drops
    it), so no migration is asked for.
  - A comment-only edit, or a change SQLite compiles the same (an Enum widened, a VARCHAR length), compiles to the
    same objects: no change, PASS.
STATED LIMITS (CONTRIBUTING.md): DDL outside Base.metadata (raw SQL in a migration or elsewhere) is not seen; a data
change that needs a backfill with no DDL change is not seen. The deploy's `!` line (#954) stays the net behind it.

Read-only: it reads git objects and compiles in memory; it writes only a temporary directory it removes. Never data/.

    python scripts/schema_ddl_check.py --base origin/main [--head REV]

Exit: 0 PASS · 1 REFUSED (a DDL change with no new migration) · 2 the check could not run (a revision or a compile
failed): never a pass on something unread (law 4).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, REFUSED, FAILED = 0, 1, 2
MIGRATION_NAME = re.compile(r"^migrate_[A-Za-z0-9_]+\.py$")        # sp_deploy.MIGRATION_NAME (a test pins the two)

# Run in a child interpreter with cwd = the tree to compile: imports that tree's src.db.schema, never this one's.
DUMP = r"""
import json, os, re, sys
sys.path.insert(0, os.getcwd())
from sqlalchemy import create_engine, text
from src.db.schema import Base
eng = create_engine("sqlite://")
Base.metadata.create_all(eng)
with eng.connect() as c:
    rows = c.execute(text("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")).fetchall()
print(json.dumps([[t, n, tb, s] for t, n, tb, s in rows]))
"""


class CheckFailed(Exception):
    """The check could not run: exit 2, never a pass."""


def normalise(sql: str | None) -> str:
    """Whitespace collapsed, VARCHAR(n) read as VARCHAR (SQLite stores the length and never enforces it)."""
    return re.sub(r"\s+", " ", re.sub(r"VARCHAR\s*\(\s*\d+\s*\)", "VARCHAR", sql or "", flags=re.I)).strip()


def git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise CheckFailed(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip().splitlines()[-1:] or ['failed']}")
    return r.stdout


def export_src(rev: str, dest: Path, cwd: Path = ROOT) -> None:
    """src/ at `rev`, written under `dest` from git's own objects (`git archive`): no checkout, no worktree."""
    r = subprocess.run(["git", "archive", "--format=tar", rev, "src"], cwd=cwd, capture_output=True)
    if r.returncode != 0:
        raise CheckFailed(f"git archive {rev} src: {r.stderr.decode(errors='replace').strip() or 'failed'}")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        for m in tar.getmembers():                                  # our own repository's objects; still no escape
            if m.name.startswith(("/", "..")) or "/../" in m.name or not (m.isfile() or m.isdir()):
                raise CheckFailed(f"git archive {rev}: unexpected member {m.name!r}")
        tar.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def compile_objects(tree: Path) -> dict[str, tuple[str, str]]:
    """{'<type>:<name>': (table, normalised sql)} as SQLite compiles `tree`'s src/db/schema.py, in memory."""
    env = {**os.environ, "DATABASE_URL": "sqlite://"}               # the import opens nothing on disk
    env.pop("PYTHONPATH", None)
    r = subprocess.run([sys.executable, "-I", "-c", DUMP], cwd=tree, capture_output=True, text=True, env=env,
                       timeout=300)
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["no output"])[-1]
        raise CheckFailed(f"compiling {tree}/src/db/schema.py failed: {tail}")
    try:
        rows = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as e:
        raise CheckFailed(f"compiling {tree}/src/db/schema.py: unreadable output ({e})") from e
    return {f"{t}:{n}": (tb, normalise(s)) for t, n, tb, s in rows}


def compare(base: dict, head: dict) -> dict[str, list[str]]:
    return {"changed": sorted(k for k in base.keys() & head.keys() if base[k] != head[k]),
            "added": sorted(head.keys() - base.keys()),
            "removed": sorted(base.keys() - head.keys())}


def new_migrations(base: str, head: str, cwd: Path = ROOT) -> list[str]:
    """Top-level migrate_*.py files the PR adds (merge base .. head), as sp_deploy's plan lists them."""
    out = git("diff", "--name-only", "--no-renames", "--diff-filter=A", f"{base}...{head}", cwd=cwd)
    return sorted(p for p in out.splitlines() if MIGRATION_NAME.match(p))


def run(base: str, head: str | None, say=print, cwd: Path | None = None) -> int:
    cwd = cwd or ROOT
    base_sha = git("rev-parse", "--verify", f"{base}^{{commit}}", cwd=cwd).strip()
    head_rev = head or "HEAD"
    head_sha = git("rev-parse", "--verify", f"{head_rev}^{{commit}}", cwd=cwd).strip()
    with tempfile.TemporaryDirectory(prefix="schema_ddl_check_") as tmp:
        b = Path(tmp) / "base"
        b.mkdir()
        export_src(base_sha, b, cwd)
        if head is None:
            h = cwd                                                 # this working tree (CI: the PR's merge result)
        else:
            h = Path(tmp) / "head"
            h.mkdir()
            export_src(head_sha, h, cwd)
        a, z = compile_objects(b), compile_objects(h)
    d = compare(a, z)
    migs = new_migrations(base_sha, head_sha, cwd)
    say(f"SCHEMA DDL CHECK (#950; addendum 358 item 2, scope B) · base {base} {base_sha[:8]} · head "
        f"{head or 'this working tree'} {head_sha[:8]} · objects: base {len(a)}, head {len(z)}")
    for k in d["changed"]:
        say(f"  CHANGED  {k} (on {z[k][0]})")
    for k in d["added"]:
        say(f"  ADDED    {k} (on {z[k][0]}{', a new table' if z[k][0] not in {v[0] for v in a.values()} else ''})")
    for k in d["removed"]:
        say(f"  REMOVED  {k} (on {a[k][0]}; information: the live DB keeps it, nothing drops it)")
    say(f"  new migrate_*.py in this PR: {', '.join(migs) if migs else 'none'}")
    if not d["changed"] and not d["added"]:
        say("SCHEMA: PASS (the compiled DDL is unchanged: no object changed or added)")
        return OK
    if migs:
        say(f"SCHEMA: PASS ({len(d['changed'])} changed, {len(d['added'])} added; the PR ships {', '.join(migs)})")
        return OK
    say(f"SCHEMA: REFUSED ({len(d['changed'])} changed, {len(d['added'])} added, and no new migrate_*.py in the PR). "
        "A change to the stored schema, a new table included, ships with a NEW one-shot migrate_<what>.py in the same "
        "PR that calls the idempotent migration applying it (CONTRIBUTING.md; addendum 354 item 2(a), 358 item 2)")
    return REFUSED


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#950: refuse a schema DDL change that ships no new migrate_*.py")
    ap.add_argument("--base", required=True, help="the PR's base (e.g. origin/main)")
    ap.add_argument("--head", default=None, help="a revision to compare instead of this working tree (replays)")
    a = ap.parse_args(argv)
    try:
        return run(a.base, a.head)
    except (CheckFailed, subprocess.TimeoutExpired, OSError) as e:
        print(f"SCHEMA: FAILED — the check could not run ({type(e).__name__}: {e}); never a pass on something unread")
        return FAILED


if __name__ == "__main__":
    sys.exit(main())
