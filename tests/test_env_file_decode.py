"""desk_policy._env_file on a file that is not valid UTF-8 (ARCHITECT 2026-11-23 13:48 ET, addendum 464 item 4; #1093).
Ruled mend, verbatim in part: "With `strict`, `_env_file` reads a file it cannot decode as `HOST_ENV_UNREADABLE`: the
role is unknown and nothing after it is read. Without `strict` it reads such a file as `{}`, which is the checkout's
`.env`, the last source." Before #1093 a UnicodeDecodeError (a ValueError, not an OSError) passed through every caller
of role_reading (host_fenced, not_host_reason, not_laptop_reason, machine_role) as a traceback. The machine is driven as
tests/test_not_laptop_reason.py drives it: SP_HOST_ENV at a tmp host.env, desk_policy.DOTENV at a tmp .env, the
environment's role (conftest pins laptop)."""
import pytest

from src.walters import desk_policy as dp

BAD = b"SP_EXPORTS_MIRROR_ROLE=laptop\n\xff\xfe\n"          # the role line, then two bytes that are not UTF-8 (#1093)
UNREADABLE = "host.env exists but cannot be read: the role is unknown"


@pytest.fixture
def machine(tmp_path, monkeypatch):
    def set_up(host_env=None, dotenv=None, role=None):
        for name, data in (("host.env", host_env), (".env", dotenv)):
            p = tmp_path / name
            p.unlink(missing_ok=True)
            if data is not None:
                p.write_bytes(data)
        monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "host.env"))
        monkeypatch.setattr(dp, "DOTENV", tmp_path / ".env")
        if role is None:
            monkeypatch.delenv(dp.ROLE_ENV, raising=False)
        else:
            monkeypatch.setenv(dp.ROLE_ENV, role)
        return tmp_path
    return set_up


def test_strict_reads_an_undecodable_file_as_unreadable_and_plain_reads_it_as_empty(tmp_path):
    p = tmp_path / "bad.env"
    p.write_bytes(BAD)
    with pytest.raises(UnicodeDecodeError):                    # the bytes really do not decode
        p.read_text(encoding="utf-8")
    assert dp._env_file(p, strict=True) is dp.HOST_ENV_UNREADABLE
    assert dp._env_file(p) == {}
    good = tmp_path / "good.env"
    good.write_text("SP_EXPORTS_MIRROR_ROLE=laptop\n")
    assert dp._env_file(good, strict=True) == {"SP_EXPORTS_MIRROR_ROLE": "laptop"}   # a readable file is unchanged


@pytest.mark.parametrize("env_role", ["laptop", "host", None])
def test_an_undecodable_host_env_makes_the_role_unknown_and_nothing_after_it_is_read(machine, env_role):
    """#1093's own case (the role line then two bytes that are not UTF-8, the environment saying laptop) and the other
    two environment roles: the reading is (None, HOST_ENV_UNREADABLE) and no caller raises."""
    machine(host_env=BAD, dotenv=b"SP_EXPORTS_MIRROR_ROLE=laptop\n", role=env_role)
    assert dp.role_reading() == (None, dp.HOST_ENV_UNREADABLE)
    assert dp.machine_role() is None
    assert dp.not_laptop_reason() == UNREADABLE
    assert dp.not_host_reason() == UNREADABLE


def test_an_undecodable_host_env_fences_a_soccer_row_while_the_switch_is_on(machine, monkeypatch):
    """The fence's own read (host_fenced) with its switch on, as tests/test_cockpit_intl_verify_role.py turns it on:
    an undecodable host.env fences as an unreadable one does, never as the environment's laptop."""
    machine(host_env=BAD, role="laptop")
    monkeypatch.setitem(dp.HOST_FENCE_RULE, "on", True)
    assert dp.host_fenced({"sport": "SOCCER"}) == dp.HOST_FENCE_UNREADABLE_REASON


def test_an_undecodable_checkout_env_reads_as_empty_the_last_source(machine):
    """Without strict (the checkout's .env, the last source): {} and the role is unset, a refusal and not a
    traceback."""
    machine(dotenv=BAD, role=None)
    assert dp.role_reading() == (None, "")
    assert dp.not_laptop_reason() == f"the role is unknown ({dp.ROLE_ENV} unset)"
    assert dp.not_host_reason() == f"the role is unknown ({dp.ROLE_ENV} unset)"
