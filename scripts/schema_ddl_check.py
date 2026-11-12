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

HOW: the tree at the MERGE BASE of the base and head (git archive of the whole tree, so an import from outside src/
resolves), and the head (--head REV, archived the same way, or this working tree as it stands) are compiled into an
in-memory SQLite
(`Base.metadata.create_all` on `sqlite://`, DATABASE_URL=sqlite:// for the import: no file is created anywhere), and
`sqlite_master` is read: every table, index and trigger, including the triggers schema.py attaches by `after_create`.
Each object's SQL is normalised (whitespace collapsed, `VARCHAR(n)` read as `VARCHAR`, as SQLite does not enforce the
length), then base and head are compared object by object:
  - CHANGED / ADDED objects (any kind: a table, an index, a trigger, on an existing table or a new one) need a NEW
    top-level migrate_*.py in the PR (added between the merge base and head, the name sp_deploy's plan reads:
    `^migrate_[A-Za-z0-9_]+\\.py$` at the repository root). A new name whose content is a byte copy of a migration
    already on the merge base, or the destination of a renamed one, is not new: sp_deploy's plan treats it as a copy
    that already ran and never runs it, so it does not count here either. Editing an existing migration does not
    count (it is not new). Without one: REFUSED.
  - Base = the MERGE BASE, never the base branch's tip: a PR behind its base is not asked to carry the base's own
    later schema changes (their migrations are the base's, outside the PR's range).
  - REMOVED objects are printed as information: a table dropped from the metadata stays on the live DB (nothing drops
    it), so no migration is asked for.
  - A comment-only edit, or a change SQLite compiles the same (an Enum widened, a VARCHAR length), compiles to the
    same objects: no change, PASS.
STATED LIMITS (CONTRIBUTING.md): DDL outside Base.metadata (raw SQL in a migration or elsewhere) is not seen; a data
change that needs a backfill with no DDL change is not seen; only what `src.db.schema`'s import registers on Base is
compiled (every table is declared in src/db/schema.py; a test pins that no other module assigns `__tablename__`); a
difference only in whitespace or in a `VARCHAR(n)` inside a SQL string literal is normalised away. The deploy's `!`
line (#954) stays the net behind it.

Read-only: it reads git objects and compiles in memory (`python -I -B`, so not even a .pyc is written into the
checkout); it writes only a temporary directory it removes. Never data/.

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


def export_tree(rev: str, dest: Path, cwd: Path = ROOT) -> None:
    """The whole tree at `rev`, written under `dest` from git's own objects (`git archive`): no checkout, no worktree.
    The whole tree, not src/ alone, so a schema import from outside src/ (a top-level module) compiles at both ends.
    Regular files and directories only (a symlink is not needed to compile and is not extracted); data/ is never in
    git, so it is never in the archive."""
    r = subprocess.run(["git", "archive", "--format=tar", rev], cwd=cwd, capture_output=True)
    if r.returncode != 0:
        raise CheckFailed(f"git archive {rev}: {r.stderr.decode(errors='replace').strip() or 'failed'}")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        members = []
        for m in tar.getmembers():                                  # our own repository's objects; still no escape
            if m.name.startswith(("/", "..")) or "/../" in m.name:
                raise CheckFailed(f"git archive {rev}: unexpected member {m.name!r}")
            if m.isfile() or m.isdir():
                members.append(m)
        tar.extractall(dest, members=members, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def compile_objects(tree: Path) -> dict[str, tuple[str, str]]:
    """{'<type>:<name>': (table, normalised sql)} as SQLite compiles `tree`'s src/db/schema.py, in memory."""
    env = {**os.environ, "DATABASE_URL": "sqlite://"}               # the import opens nothing on disk
    env.pop("PYTHONPATH", None)
    # -B: no .pyc written into the tree (-I implies -E, which ignores PYTHONDONTWRITEBYTECODE)
    r = subprocess.run([sys.executable, "-I", "-B", "-c", DUMP], cwd=tree, capture_output=True, text=True, env=env,
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


def _names(text: str) -> set[str]:
    return {p.strip() for p in text.splitlines() if MIGRATION_NAME.match(p.strip())}


def new_migrations(merge_base: str, head: str, cwd: Path = ROOT, worktree: bool = False
                   ) -> tuple[list[str], dict[str, str]]:
    """(the top-level migrate_*.py files the PR adds, {added name: why it does not count}), merge base .. head, as
    sp_deploy.migration_plan reads them:
      - a byte copy of a migration on the merge base, or a renamed one, already ran: the plan never runs it;
      - two new files with the same content: the plan leaves both undetermined (one one-shot would run twice);
      - ANY migration deleted anywhere in the range's history (a move shows as delete + add): the plan's lineage is
        unknown and it runs none of the new ones, so none counts here (Codex on #968: an add-then-rename inside the
        PR leaves only the new name in the endpoint diff);
      - an edited existing migration is not added, so not new.
    worktree=True (no --head): the working tree is what was compiled, so its uncommitted files count too: staged or
    unstaged additions and deletions against HEAD, and untracked files (Codex on #968)."""
    added = _names(git("diff", "--name-only", "--no-renames", "--diff-filter=A", merge_base, head, cwd=cwd))
    deleted = _names(git("log", "-m", "--no-renames", "--diff-filter=D", "--name-only", "--format=",
                         f"{merge_base}..{head}", cwd=cwd))
    if worktree:
        added |= _names(git("diff", "--name-only", "--no-renames", "--diff-filter=A", head, cwd=cwd))
        added |= _names(git("ls-files", "--others", "--exclude-standard", cwd=cwd))
        deleted |= _names(git("diff", "--name-only", "--no-renames", "--diff-filter=D", head, cwd=cwd))
        added = {n for n in added if (cwd / n).is_file()}
    added = sorted(added)
    if not added:
        return [], {}
    old = {}                                                        # blob -> name, the merge base's own migrations
    for ln in git("ls-tree", merge_base, cwd=cwd).splitlines():
        meta, _, name = ln.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob" and MIGRATION_NAME.match(name):
            old[parts[2]] = name
    renamed = {}
    rename_args = ["diff", "--name-status", "-M", "--diff-filter=R", merge_base] + ([] if worktree else [head])
    for ln in git(*rename_args, cwd=cwd).splitlines():
        f = ln.split("\t")
        if len(f) == 3 and MIGRATION_NAME.match(f[1]) and MIGRATION_NAME.match(f[2]):
            renamed[f[2]] = f[1]

    def blob(name: str) -> str:
        if worktree:
            return git("hash-object", "--", name, cwd=cwd).strip()
        return git("rev-parse", f"{head}:{name}", cwd=cwd).strip()
    blobs = {name: blob(name) for name in added}
    excluded = {}
    for name in added:
        if deleted:
            excluded[name] = (f"migration history unknown: {', '.join(sorted(deleted))} deleted in the PR's range, so "
                              "sp_deploy's plan runs none of the new migrations")
        elif blobs[name] in old:
            excluded[name] = f"a byte copy of {old[blobs[name]]}, already on the base: sp_deploy never runs it"
        elif name in renamed:
            excluded[name] = f"renamed from {renamed[name]}: sp_deploy treats it as already run"
        elif sum(1 for b in blobs.values() if b == blobs[name]) > 1:
            excluded[name] = "the same content as another new migration: sp_deploy leaves both undetermined"
    return [n for n in added if n not in excluded], excluded


def run(base: str, head: str | None, say=print, cwd: Path | None = None) -> int:
    cwd = cwd or ROOT
    base_sha = git("rev-parse", "--verify", f"{base}^{{commit}}", cwd=cwd).strip()
    head_rev = head or "HEAD"
    head_sha = git("rev-parse", "--verify", f"{head_rev}^{{commit}}", cwd=cwd).strip()
    mb = git("merge-base", base_sha, head_sha, cwd=cwd).strip()     # the PR's own range, at both ends
    with tempfile.TemporaryDirectory(prefix="schema_ddl_check_") as tmp:
        b = Path(tmp) / "base"
        b.mkdir()
        export_tree(mb, b, cwd)
        if head is None:
            h = cwd                                                 # this working tree (CI: the PR's merge result)
        else:
            h = Path(tmp) / "head"
            h.mkdir()
            export_tree(head_sha, h, cwd)
        a, z = compile_objects(b), compile_objects(h)
    d = compare(a, z)
    migs, not_new = new_migrations(mb, head_sha, cwd, worktree=head is None)
    say(f"SCHEMA DDL CHECK (#950; addendum 358 item 2, scope B) · base {base} {base_sha[:8]} (merge base {mb[:8]}) · "
        f"head {head or 'this working tree'} {head_sha[:8]} · objects: base {len(a)}, head {len(z)}")
    for k in d["changed"]:
        say(f"  CHANGED  {k} (on {z[k][0]})")
    for k in d["added"]:
        say(f"  ADDED    {k} (on {z[k][0]}{', a new table' if z[k][0] not in {v[0] for v in a.values()} else ''})")
    for k in d["removed"]:
        say(f"  REMOVED  {k} (on {a[k][0]}; information: the live DB keeps it, nothing drops it)")
    for name, why in sorted(not_new.items()):
        say(f"  NOT NEW  {name}: {why}")
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
