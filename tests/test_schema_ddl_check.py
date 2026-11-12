"""THE SCHEMA CHECK (#950; ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 2, verbatim in part): "a changed or added
object of any kind with no new `migrate_*.py` in the PR refuses", scope B: a NEW TABLE ships with its migrate file too;
"a comment-only edit never tripping". Each case is a throwaway git repository under tmp_path holding a minimal
src/db/schema.py; the check compiles it in memory (DATABASE_URL=sqlite://). Nothing is written outside tmp_path."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import schema_ddl_check as ddl  # noqa: E402

BASE_SCHEMA = '''"""A minimal stored schema for the check's tests."""
from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
'''


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src" / "db").mkdir(parents=True)
    (r / "src" / "__init__.py").write_text("")
    (r / "src" / "db" / "__init__.py").write_text("")
    (r / "src" / "db" / "schema.py").write_text(BASE_SCHEMA)
    _git(r, "init", "-q", "-b", "main")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    _git(r, "tag", "base")
    return r


def _commit(repo, schema=None, files=None, msg="change"):
    if schema is not None:
        (repo / "src" / "db" / "schema.py").write_text(schema)
    for path, text in (files or {}).items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _check(repo, head="HEAD"):
    lines = []
    code = ddl.run("base", head, say=lines.append, cwd=repo)
    return code, "\n".join(lines)


MIG = {"migrate_teams_city.py": '"""#950 test: calls the idempotent migration."""\n'}
ADD_COLUMN = BASE_SCHEMA + "    city = Column(String(64))\n"
NEW_TABLE = BASE_SCHEMA + '''

class Venue(Base):
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
'''


def test_a_comment_only_edit_never_trips(repo):
    _commit(repo, BASE_SCHEMA.replace('"""A minimal', '# a new comment\n"""A minimal') + "\n# trailing comment\n")
    code, out = _check(repo)
    assert code == ddl.OK and "SCHEMA: PASS (the compiled DDL is unchanged" in out, out


def test_a_varchar_length_change_compiles_the_same(repo):
    _commit(repo, BASE_SCHEMA.replace("String(64)", "String(200)"))
    code, out = _check(repo)
    assert code == ddl.OK and "unchanged" in out, out


def test_a_column_added_with_no_new_migration_is_refused(repo):
    _commit(repo, ADD_COLUMN)
    code, out = _check(repo)
    assert code == ddl.REFUSED, out
    assert "  CHANGED  table:teams (on teams)" in out
    assert "new migrate_*.py in this PR: none" in out and "SCHEMA: REFUSED (1 changed, 0 added" in out


def test_a_column_added_with_its_new_migration_passes(repo):
    _commit(repo, ADD_COLUMN, MIG)
    code, out = _check(repo)
    assert code == ddl.OK and "the PR ships migrate_teams_city.py" in out, out


def test_scope_b_a_new_table_needs_its_migration_too(repo):
    """358 item 2: "a NEW TABLE ships with its migrate file too"."""
    head = _commit(repo, NEW_TABLE)
    code, out = _check(repo)
    assert code == ddl.REFUSED, out
    assert "  ADDED    table:venues (on venues, a new table)" in out
    assert "  ADDED    index:ix_venues_team_id (on venues, a new table)" in out
    _git(repo, "reset", "-q", "--hard", "base")
    _commit(repo, NEW_TABLE, {"migrate_venues.py": '"""#950 test: venues."""\n'})
    code, out = _check(repo)
    assert code == ddl.OK and "the PR ships migrate_venues.py" in out, out
    assert head  # the refused head was a real commit


def test_an_index_added_on_an_existing_table_is_refused(repo):
    _commit(repo, BASE_SCHEMA + '    __table_args__ = (Index("ix_teams_name", "name"),)\n')
    code, out = _check(repo)
    assert code == ddl.REFUSED and "  ADDED    index:ix_teams_name (on teams)" in out, out


def test_a_trigger_attached_after_create_is_seen(repo):
    _commit(repo, BASE_SCHEMA + '''
from sqlalchemy import DDL, event
event.listen(Team.__table__, "after_create", DDL(
    "CREATE TRIGGER trg_teams_guard BEFORE DELETE ON teams BEGIN SELECT RAISE(ABORT, 'no'); END"))
''')
    code, out = _check(repo)
    assert code == ddl.REFUSED and "  ADDED    trigger:trg_teams_guard (on teams)" in out, out


@pytest.mark.parametrize("path", ["scripts/migrate_teams_city.py", "src/db/migrate_teams_city.py",
                                  "migrate-teams.py", "migrate_teams_city.txt"])
def test_only_a_top_level_migrate_file_counts(repo, path):
    """The file sp_deploy's plan lists: `^migrate_[A-Za-z0-9_]+\\.py$` at the repository root."""
    _commit(repo, ADD_COLUMN, {path: "x = 1\n"})
    code, out = _check(repo)
    assert code == ddl.REFUSED and "new migrate_*.py in this PR: none" in out, out


def test_a_migration_already_on_the_base_does_not_count(repo):
    _commit(repo, files=MIG, msg="an older migration")
    _git(repo, "tag", "-f", "base")
    _commit(repo, ADD_COLUMN)
    code, out = _check(repo)
    assert code == ddl.REFUSED and "new migrate_*.py in this PR: none" in out, out


def test_a_removed_table_is_information_only(repo):
    _commit(repo, NEW_TABLE, {"migrate_venues.py": '"""venues"""\n'})
    _git(repo, "tag", "-f", "base")
    _commit(repo, BASE_SCHEMA)
    code, out = _check(repo)
    assert code == ddl.OK, out
    assert "  REMOVED  table:venues (on venues; information: the live DB keeps it, nothing drops it)" in out


def test_the_working_tree_mode_compiles_this_checkout_and_writes_nothing(repo):
    """No --head: the working tree is compiled (CI: the PR's merge result). Nothing is created in the tree."""
    _commit(repo, ADD_COLUMN)
    before = sorted(p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts)
    lines = []
    code = ddl.run("base", None, say=lines.append, cwd=repo)
    assert code == ddl.REFUSED and "head this working tree" in lines[0], lines
    after = sorted(p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts and "__pycache__" not in p.parts)
    assert after == [p for p in before if "__pycache__" not in p.parts]
    assert not (repo / "data").exists()


@pytest.mark.parametrize("how", ["broken-schema", "no-such-base"])
def test_a_check_that_cannot_run_fails_never_passes(repo, how, monkeypatch, capsys):
    """Law 4: a revision that cannot be read, or a schema that does not compile, is exit 2, never a pass."""
    if how == "broken-schema":
        _commit(repo, BASE_SCHEMA + "    oops = Column(\n")
        monkeypatch.chdir(repo)
        monkeypatch.setattr(ddl, "ROOT", repo)
        code = ddl.main(["--base", "base", "--head", "HEAD"])
    else:
        monkeypatch.setattr(ddl, "ROOT", repo)
        code = ddl.main(["--base", "no-such-rev", "--head", "HEAD"])
    out = capsys.readouterr().out
    assert code == ddl.FAILED and "SCHEMA: FAILED" in out and "never a pass" in out, out


def test_normalise_collapses_whitespace_and_drops_varchar_lengths():
    assert ddl.normalise("CREATE TABLE t (\n\tname VARCHAR(64) NOT NULL,  x VARCHAR ( 8 )\n)") == \
        "CREATE TABLE t ( name VARCHAR NOT NULL, x VARCHAR )"
    assert ddl.normalise(None) == ""


def test_the_migration_name_is_sp_deploys():
    src = (ROOT / "deploy" / "hosting" / "sp_deploy.py").read_text(encoding="utf-8")
    m = re.search(r'^MIGRATION_NAME = re\.compile\((r"[^"]+")\)', src, re.M)
    assert m and ddl.MIGRATION_NAME.pattern == eval(m.group(1))  # noqa: S307 - a raw string literal from our source


def test_ci_runs_the_check_on_every_pull_request():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python scripts/schema_ddl_check.py --base "origin/${{ github.base_ref }}"' in ci


def test_this_repositorys_schema_compiles_the_same_twice_and_passes_itself():
    """The real schema compiles through the same path (no file DB), to the same objects each time (a compile that
    varied would refuse every PR), and the check of this checkout's HEAD against itself runs end to end and passes."""
    objs = ddl.compile_objects(ROOT)
    assert len(objs) > 100 and any(k.startswith("trigger:") for k in objs), len(objs)
    assert ddl.compile_objects(ROOT) == objs
    lines = []
    assert ddl.run("HEAD", "HEAD", say=lines.append, cwd=ROOT) == ddl.OK, lines
    assert lines[-1].startswith("SCHEMA: PASS (the compiled DDL is unchanged"), lines


def test_review_a_pr_behind_its_base_is_not_asked_for_the_bases_own_schema_changes(repo):
    """Pre-push review P1: the base is compiled at the MERGE BASE. The base branch later adds a column and its own
    migration; a PR forked before that, changing no schema, passes (it would be refused if the base tip were compiled:
    the base's migration is outside the PR's range)."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, files={"docs.txt": "a doc\n"}, msg="feature: docs only")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, ADD_COLUMN, MIG, msg="main: a column and its migration")
    _git(repo, "tag", "-f", "base")
    code, out = _check(repo, head="feature")
    assert code == ddl.OK and "the compiled DDL is unchanged" in out and "(merge base " in out, out
    _git(repo, "checkout", "-q", "feature")                         # the working-tree mode reads the same way
    lines = []
    assert ddl.run("base", None, say=lines.append, cwd=repo) == ddl.OK, lines


@pytest.mark.parametrize("how", ["copy", "rename"])
def test_review_a_copied_or_renamed_migration_is_not_new(repo, how):
    """Pre-push review P2: sp_deploy's plan treats a new file whose content equals a migration already on the base,
    and a renamed migration, as a copy that already ran, and never runs it. The check does not count it either."""
    _commit(repo, files={"migrate_old.py": '"""an older migration"""\nprint("old")\n'}, msg="an older migration")
    _git(repo, "tag", "-f", "base")
    if how == "copy":
        _commit(repo, ADD_COLUMN, {"migrate_teams_city.py": '"""an older migration"""\nprint("old")\n'})
        why = "a byte copy of migrate_old.py, already on the base: sp_deploy never runs it"
    else:
        (repo / "src" / "db" / "schema.py").write_text(ADD_COLUMN)
        _git(repo, "mv", "migrate_old.py", "migrate_teams_city.py")
        with (repo / "migrate_teams_city.py").open("a") as fh:          # a rename with an edit, not a byte copy
            fh.write("# the PR's note\n")
        _commit(repo)
        why = "renamed from migrate_old.py: sp_deploy treats it as already run"
    code, out = _check(repo)
    assert code == ddl.REFUSED, out
    assert f"  NOT NEW  migrate_teams_city.py: {why}" in out and "new migrate_*.py in this PR: none" in out


def test_review_editing_an_existing_migration_does_not_count(repo):
    """Pre-push review P2: the #950 case itself, a schema change that rides an existing migration, refuses."""
    _commit(repo, files={"migrate_old.py": '"""an older migration"""\n'}, msg="an older migration")
    _git(repo, "tag", "-f", "base")
    _commit(repo, ADD_COLUMN, {"migrate_old.py": '"""an older migration, now also adding city"""\n'})
    code, out = _check(repo)
    assert code == ddl.REFUSED and "new migrate_*.py in this PR: none" in out, out


def test_review_the_working_tree_mode_compiles_uncommitted_edits_and_writes_no_pyc(repo):
    """The working tree as it stands is what is compiled (an uncommitted column refuses while HEAD has none), and
    `python -I -B` keeps even a .pyc out of the checkout."""
    (repo / "src" / "db" / "schema.py").write_text(ADD_COLUMN)        # not committed
    lines = []
    assert ddl.run("base", None, say=lines.append, cwd=repo) == ddl.REFUSED, lines
    assert any(ln.startswith("  CHANGED  table:teams") for ln in lines), lines
    assert not list(repo.rglob("__pycache__")) and not list(repo.rglob("*.pyc"))


def test_review_a_schema_import_from_outside_src_compiles_at_both_ends(repo):
    """Pre-push review P2: the whole tree is exported, so a schema.py that imports a top-level module compiles at the
    base as at the head (src/ alone would fail every later PR with exit 2)."""
    _commit(repo, BASE_SCHEMA.replace('from sqlalchemy.orm import DeclarativeBase',
                                      'from sqlalchemy.orm import DeclarativeBase\nimport helper  # noqa: F401'),
            {"helper.py": "X = 1\n"}, msg="schema imports a top-level module")
    _git(repo, "tag", "-f", "base")
    _commit(repo, files={"notes.txt": "x\n"})
    code, out = _check(repo)
    assert code == ddl.OK and "unchanged" in out, out


def test_every_table_is_declared_in_schema_py():
    """The check compiles what src.db.schema's import registers on Base. That covers every table only while no other
    module declares one: no tracked .py outside src/db/schema.py (tests aside) assigns __tablename__."""
    out = subprocess.run(["git", "grep", "-l", "-E", r"^\s*__tablename__\s*=", "--", "*.py"], cwd=ROOT,
                         capture_output=True, text=True).stdout.split()
    assert [p for p in out if not p.startswith("tests/")] == ["src/db/schema.py"], out


def test_contributing_states_the_limits():
    text = " ".join((ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").split())
    assert "scripts/schema_ddl_check.py" in text and "addendum 358 item 2" in text
    assert "DDL outside `Base.metadata`" in text and "a backfill with no DDL change" in text
    assert "the merge base" in text and "byte copy" in text
