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


def test_this_repositorys_schema_compiles_and_main_passes_itself():
    """The real schema compiles through the same path (no file DB): the check of a tree against itself passes."""
    objs = ddl.compile_objects(ROOT)
    assert len(objs) > 100 and any(k.startswith("trigger:") for k in objs), len(objs)


def test_contributing_states_the_limits():
    text = " ".join((ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").split())
    assert "scripts/schema_ddl_check.py" in text and "addendum 358 item 2" in text
    assert "DDL outside `Base.metadata`" in text and "a backfill with no DDL change" in text
