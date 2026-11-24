"""desk_policy.not_laptop_reason (ARCHITECT 2026-11-23, addendum 461 item 2(d), verbatim): "WHAT IS BUILT:
desk_policy.not_laptop_reason(), beside not_host_reason() and on its pattern (178 R6). None on the laptop; otherwise
why this machine is not the laptop, by role_reading, read only: the role is host, unset, a value that is neither, or
host.env exists and cannot be read. Its docstring says, as not_host_reason's does, that it is not a fence input:
host_fenced never reads it. The routine calls it, prints the reason and exits 2 with nothing run when it is not None."
Item 2(c): the refusal rests on the fence's reading (role_reading: host.env first), never on closing.mirror_role(),
which reads the environment first, so a routine typed by hand on the host could be answered by the checkout's .env,
which on the host says laptop. Item 4: "the refusal's test reads not_laptop_reason on each of its four answers".
The machine is driven as tests/test_desk_host_fence.py drives role_reading: SP_HOST_ENV at a tmp host.env, the
checkout's .env at a tmp file (desk_policy.DOTENV), the environment's role (conftest pins laptop)."""
import ast
from pathlib import Path

import pytest

from src.walters import desk_policy as dp

HOST = "this machine's role is host"
UNREADABLE = "host.env exists but cannot be read: the role is unknown"
UNSET = "the role is unknown (SP_EXPORTS_MIRROR_ROLE unset)"
READ_PATH = ("host_fenced", "role_reading", "machine_role", "_env_file")   # test_host_watch_after_flip's READ_PATH


def neither(value):
    return f"the role {value!r} is not host or laptop"


@pytest.fixture
def role(monkeypatch):
    """The environment's role (conftest pins laptop); None deletes it."""
    def set_role(v):
        if v is None:
            monkeypatch.delenv(dp.ROLE_ENV, raising=False)
        else:
            monkeypatch.setenv(dp.ROLE_ENV, v)
    return set_role


@pytest.fixture
def files(tmp_path, monkeypatch):
    """The machine's host.env (SP_HOST_ENV) and the checkout's .env (desk_policy.DOTENV); None: no such file;
    host_env=dir: a directory there (exists, cannot be read)."""
    def write(host_env=None, dotenv=None):
        for name, text in (("host.env", host_env), (".env", dotenv)):
            p = tmp_path / name
            if p.is_dir():
                p.rmdir()
            p.unlink(missing_ok=True)
            if text is dir:
                p.mkdir()
            elif text is not None:
                p.write_text(text)
        monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "host.env"))
        monkeypatch.setattr(dp, "DOTENV", tmp_path / ".env")
    return write


def test_none_on_the_laptop_from_each_source(role, files):
    """The laptop: its role is laptop in the environment (conftest), in the checkout's .env alone, or in a host.env."""
    files()
    role("laptop")
    assert dp.role_reading() == ("laptop", "laptop") and dp.not_laptop_reason() is None
    role(None)
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    assert dp.not_laptop_reason() is None                           # a script that never imports config
    files(host_env="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    assert dp.not_laptop_reason() is None
    role(" laptop ")                                                # stripped, as role_reading strips it
    files()
    assert dp.not_laptop_reason() is None


def test_the_role_is_host(role, files):
    files(host_env="SP_EXPORTS_MIRROR_ROLE=host\n")
    role(None)
    assert dp.role_reading() == ("host", "host") and dp.not_laptop_reason() == HOST
    files()
    role("host")                                                    # the environment alone
    assert dp.not_laptop_reason() == HOST
    role(None)
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=host\n")                   # the .env alone
    assert dp.not_laptop_reason() == HOST


def test_the_role_is_unset(role, files):
    files()
    role(None)
    assert dp.role_reading() == (None, "") and dp.not_laptop_reason() == UNSET
    files(host_env="SP_WRITER_OF_RECORD=laptop\n", dotenv="SP_EXPORTS_MIRROR_ROLE=\n")   # no role line; an empty one
    role("  ")
    assert dp.not_laptop_reason() == UNSET
    assert UNSET == f"the role is unknown ({dp.ROLE_ENV} unset)"


@pytest.mark.parametrize("value", ["staging", "Laptop", "laptop2"])
def test_a_value_that_is_neither_host_nor_laptop(role, files, value):
    """A value that is neither decides (law 4): never the next source's laptop."""
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    role(value)
    assert dp.role_reading() == (None, value) and dp.not_laptop_reason() == neither(value)
    role("laptop")
    files(host_env=f"SP_EXPORTS_MIRROR_ROLE={value}\n", dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    assert dp.not_laptop_reason() == neither(value)


def test_host_env_exists_and_cannot_be_read(role, files, monkeypatch):
    """Addendum 116 item 2: a host.env that exists but cannot be read makes the role unknown and nothing after it is
    consulted, so an unreadable host.env is never answered by the environment's or the .env's laptop."""
    files(host_env=dir, dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")   # a directory: exists, cannot be read
    for env_role in ("laptop", "host", None):
        role(env_role)
        assert dp.role_reading() == (None, dp.HOST_ENV_UNREADABLE) and dp.not_laptop_reason() == UNREADABLE
    real = open

    def guarded(path, *a, **kw):
        if str(path).endswith("host.env") and Path(path).exists():  # it exists; this user cannot read it (0640)
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *a, **kw)
    monkeypatch.setattr(dp, "open", guarded, raising=False)         # desk_policy's own open, nothing else's
    files(host_env="SP_EXPORTS_MIRROR_ROLE=laptop\n", dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    role("laptop")
    assert dp.not_laptop_reason() == UNREADABLE                     # even a host.env that would say laptop


def test_host_env_comes_first_so_the_hosts_laptop_env_never_answers(role, files):
    """461 item 2(c), the #410 case: a routine typed by hand on the host, whose checkout's .env (copied from the
    laptop) and environment say laptop, is refused by host.env's host."""
    files(host_env="SP_WRITER_OF_RECORD=laptop\nSP_EXPORTS_MIRROR_ROLE=host\n", dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    for env_role in ("laptop", None):
        role(env_role)
        assert dp.not_laptop_reason() == HOST
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")                 # no host.env (the laptop): falls through
    role(None)
    assert dp.not_laptop_reason() is None


def test_it_mirrors_not_host_reason_on_the_same_reading(role, files):
    """178 R6's pattern: each machine answers exactly one of the two with None, and the shared answers match."""
    files()
    role("laptop")
    assert (dp.not_laptop_reason(), dp.not_host_reason()) == (None, "this machine's role is laptop")
    role("host")
    assert (dp.not_laptop_reason(), dp.not_host_reason()) == (HOST, None)
    role(None)
    assert dp.not_laptop_reason() == dp.not_host_reason() == UNSET
    role("staging")
    assert dp.not_laptop_reason() == dp.not_host_reason() == neither("staging")
    files(host_env=dir)
    assert dp.not_laptop_reason() == dp.not_host_reason() == UNREADABLE


def _functions():
    tree = ast.parse(Path(dp.__file__).read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _mentions(fn, name):
    """Every reference to `name` in a function: a Name, an Attribute, or a string constant that holds it."""
    return [n for n in ast.walk(fn) if (isinstance(n, ast.Name) and n.id == name)
            or (isinstance(n, ast.Attribute) and n.attr == name)
            or (isinstance(n, ast.Constant) and isinstance(n.value, str) and name in n.value)]


def test_not_a_fence_input_the_read_path_never_names_it():
    """Its docstring's claim, pinned: host_fenced and the fence's read path (role_reading, machine_role, _env_file)
    never reference not_laptop_reason, and nothing in desk_policy calls it; it reads role_reading and two constants."""
    fns = _functions()
    assert "not_laptop_reason" in fns and set(READ_PATH) <= set(fns)
    names = list(fns)
    assert names.index("not_laptop_reason") == names.index("not_host_reason") + 1   # beside not_host_reason
    assert {f: _mentions(fns[f], "not_laptop_reason") for f in READ_PATH} == {f: [] for f in READ_PATH}
    assert [f for f, fn in fns.items() if f != "not_laptop_reason" and _mentions(fn, "not_laptop_reason")] == []
    fn = fns["not_laptop_reason"]
    loads = {n.id for b in fn.body for n in ast.walk(b) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert loads - {"role", "value"} == {"role_reading", "HOST_ENV_UNREADABLE", "ROLE_ENV"}
    doc = ast.get_docstring(fn)
    assert "Not a fence input: host_fenced never reads it" in doc and "addendum 461 item 2(d)" in doc


def test_rebinding_it_changes_no_desk_call(role, files, monkeypatch):
    """With the fence's switch on (as before the cutover), a rebound not_laptop_reason leaves host_fenced's answer
    as it was on every role."""
    monkeypatch.setitem(dp.HOST_FENCE_RULE, "on", True)
    row = {"sport": "SOCCER"}
    files()
    real = dp.not_laptop_reason
    seen = []
    for env_role in ("host", "laptop", None):
        role(env_role)
        monkeypatch.setattr(dp, "not_laptop_reason", real)
        before = dp.host_fenced(row)
        for stub in (lambda: None, lambda: "rebound"):
            monkeypatch.setattr(dp, "not_laptop_reason", stub)
            assert dp.host_fenced(row) == before
        seen.append(before)
    assert seen == [dp.HOST_FENCE_REASON, None, dp.HOST_FENCE_UNSET_REASON]
