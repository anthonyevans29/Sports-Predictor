"""#329 RULED (ARCHITECT 2026-10-08, addendum 11, item 5): "build the guard as proposed, parts 1 and 2, as one shared
function. Every cohort freeze and every one-run reservation calls it: a cohort, a run record or a reservation for the
experiment on any ref the clone knows refuses, naming the ref and the commit. --no-fetch stays, and the receipt then
prints that other clones were not checked."

Every repo here is synthetic, under tmp_path: the real repo's refs are never read or fetched."""
import json
import os
import subprocess

import pytest

from src.walters import registry as reg
from src.walters import soccer_expansion as sx
from src.walters.registry import cross_ref_guard as REAL_GUARD     # captured before conftest's autouse stub

EID = "exp-x"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
       "-c", "init.defaultBranch=main"]


def git(repo, *args):
    r = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


ENTRY = {"id": EID, "status": "confirming", "run": None, "confirmation_plan": {"n_games": 2}}


def write_registry(repo, entry=None, cohort=None, run_ids=None, reservation=None):
    d = repo / "docs" / "registry"
    (d / "ids").mkdir(parents=True, exist_ok=True)
    (d / "experiments.json").write_text(json.dumps([{"id": "other", "run": {"x": 1}}, entry or ENTRY], indent=2))
    if cohort is not None:
        (d / "ids" / f"{EID}.cohort.txt").write_text(cohort)
    if run_ids is not None:
        (d / "ids" / f"{EID}.txt").write_text(run_ids)
    if reservation is not None:
        (d / f"{EID}.started.json").write_text(reservation)


def commit(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def clone(tmp_path):
    """origin (bare) + the freezing clone on main, holding a declared experiment with nothing recorded."""
    origin, seed, a = tmp_path / "origin.git", tmp_path / "seed", tmp_path / "a"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "init", "-q", str(seed))
    write_registry(seed)
    commit(seed, "declare")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "main")
    git(tmp_path, "clone", "-q", str(origin), str(a))
    return {"origin": origin, "a": a, "tmp": tmp_path}


def on_branch(repo, branch, **write):
    """Record something on `branch` of `repo`, then return to main (the working tree is main's again)."""
    git(repo, "checkout", "-q", "-b", branch)
    write_registry(repo, **write)
    sha = commit(repo, f"record on {branch}")
    git(repo, "checkout", "-q", "main")
    return sha


COHORT = {"n": 2, "ids_sha256": "94416b7c" + "0" * 56, "ids_file": f"docs/registry/ids/{EID}.cohort.txt"}


def test_a_cohort_on_another_ref_refuses_naming_the_ref_and_the_commit(clone):
    a = clone["a"]
    sha = on_branch(a, "laptop/intl-cohort-freeze", entry={**ENTRY, "confirmation_cohort": COHORT},
                    cohort="1\n2\n")
    with pytest.raises(reg.CrossRefRefused) as ei:
        REAL_GUARD(EID, no_fetch=True, repo=str(a))
    msg = str(ei.value)
    assert "a cohort on ref heads/laptop/intl-cohort-freeze" in msg and sha in msg and "sha256 94416b7c" in msg
    # the cohort FILE alone (no ledger field) is a cohort too
    git(a, "branch", "-q", "-D", "laptop/intl-cohort-freeze")
    sha2 = on_branch(a, "laptop/file-only", cohort="1\n2\n")
    with pytest.raises(reg.CrossRefRefused, match=f"a cohort on ref heads/laptop/file-only at commit {sha2}"):
        REAL_GUARD(EID, no_fetch=True, repo=str(a))


def test_a_pushed_then_deleted_branch_still_refuses_through_its_remote_tracking_ref(clone):
    """The 2026-10-07 case: bf556b4 was pushed, so origin/laptop/... stayed in the clone after the local delete."""
    a = clone["a"]
    sha = on_branch(a, "laptop/intl-cohort-freeze", entry={**ENTRY, "confirmation_cohort": COHORT}, cohort="1\n2\n")
    git(a, "push", "-q", "origin", "laptop/intl-cohort-freeze")
    git(a, "branch", "-q", "-D", "laptop/intl-cohort-freeze")
    with pytest.raises(reg.CrossRefRefused, match=f"remotes/origin/laptop/intl-cohort-freeze at commit {sha}"):
        REAL_GUARD(EID, no_fetch=True, repo=str(a))


def test_a_run_record_on_another_ref_refuses(clone):
    a = clone["a"]
    run = {"run_at": "2026-10-08T00:00:00Z", "ids_sha256": "ab" * 32, "ids_file": f"docs/registry/ids/{EID}.txt"}
    sha = on_branch(a, "laptop/one-run", entry={**ENTRY, "status": "run", "run": run}, run_ids="7\n")
    with pytest.raises(reg.CrossRefRefused) as ei:
        REAL_GUARD(EID, no_fetch=True, repo=str(a))
    assert f"a run record on ref heads/laptop/one-run at commit {sha}" in str(ei.value)
    assert "a cohort" not in str(ei.value) and "a reservation" not in str(ei.value)


def test_a_reservation_on_another_ref_refuses(clone):
    a = clone["a"]
    sha = on_branch(a, "laptop/reserved", reservation='{"id": "exp-x", "started_at": "2026-10-08T00:00:00Z"}\n')
    with pytest.raises(reg.CrossRefRefused, match=f"a reservation on ref heads/laptop/reserved at commit {sha}"):
        REAL_GUARD(EID, no_fetch=True, repo=str(a))


def test_identical_state_on_another_ref_passes_and_a_different_one_refuses(clone):
    a = clone["a"]
    on_branch(a, "laptop/same", entry={**ENTRY, "confirmation_cohort": COHORT}, cohort="1\n2\n")
    write_registry(a, entry={**ENTRY, "confirmation_cohort": COHORT}, cohort="1\n2\n")   # this tree holds it too
    out = REAL_GUARD(EID, no_fetch=True, repo=str(a))
    assert out.startswith("cross-ref guard: --no-fetch: other clones not checked") and "ref(s) scanned" in out
    # (main, committed without the cohort, holds nothing: a ref without a record never refuses)
    # the same cohort file under a different ledger field (a second freeze) is not identical: refused
    write_registry(a, entry={**ENTRY, "confirmation_cohort": {**COHORT, "ids_sha256": "419872ed" + "0" * 56}},
                   cohort="1\n2\n")
    with pytest.raises(reg.CrossRefRefused, match="heads/laptop/same"):
        REAL_GUARD(EID, no_fetch=True, repo=str(a))


def test_nothing_anywhere_passes_and_other_experiments_never_count(clone):
    a = clone["a"]
    on_branch(a, "laptop/other-exp", entry={**ENTRY, "id": "exp-y", "confirmation_cohort": COHORT})
    assert "none holds" in REAL_GUARD(EID, no_fetch=True, repo=str(a))


def test_fetch_sees_another_clones_pushed_branch_and_no_fetch_says_it_did_not(clone):
    """Part 2: a freeze in clone A after clone B pushed laptop/* — invisible offline, refused after the fetch."""
    tmp, origin, a = clone["tmp"], clone["origin"], clone["a"]
    b = tmp / "b"
    git(tmp, "clone", "-q", str(origin), str(b))
    sha = on_branch(b, "laptop/b-freeze", entry={**ENTRY, "confirmation_cohort": COHORT}, cohort="1\n2\n")
    git(b, "push", "-q", "origin", "laptop/b-freeze")
    offline = REAL_GUARD(EID, no_fetch=True, repo=str(a))                    # A never fetched: not visible
    assert "--no-fetch: other clones not checked" in offline
    with pytest.raises(reg.CrossRefRefused, match=f"remotes/origin/laptop/b-freeze at commit {sha}"):
        REAL_GUARD(EID, repo=str(a))


def test_a_failed_fetch_refuses_unless_no_fetch(clone):
    a = clone["a"]
    git(a, "remote", "set-url", "origin", str(clone["tmp"] / "gone.git"))
    with pytest.raises(reg.CrossRefRefused, match="could not fetch origin laptop/.*--no-fetch"):
        REAL_GUARD(EID, repo=str(a))
    assert "other clones not checked" in REAL_GUARD(EID, no_fetch=True, repo=str(a))


def test_a_clone_git_cannot_read_refuses(tmp_path):
    with pytest.raises(reg.CrossRefRefused, match="cannot list this clone's refs"):
        REAL_GUARD(EID, no_fetch=True, repo=str(tmp_path))


# ------------------------------------------------------------------ every caller calls the ONE function --

class Called(Exception):
    pass


def _raise(eid, no_fetch=False, repo=None):
    raise Called((eid, no_fetch))


def test_the_cohort_freeze_calls_the_guard_before_any_write(monkeypatch, tmp_path):
    led, ids = str(tmp_path / "experiments.json"), str(tmp_path / "ids")
    reg.save([{"id": EID, "status": "confirming", "confirmation_plan": {"n_games": 2}, "run": None}], led)
    monkeypatch.setattr(reg, "cross_ref_guard", _raise)
    with pytest.raises(Called) as ei:
        reg.freeze_confirmation_cohort(EID, [1, 2], {"rule": "t"}, path=led, ids_dir=ids, no_fetch=True)
    assert ei.value.args[0] == (EID, True)
    assert not os.path.exists(os.path.join(ids, f"{EID}.cohort.txt"))
    assert "confirmation_cohort" not in reg.load(led)[0]
    # a refusal surfaces as a RegistryError (the CLI exits 2); a pass writes and echoes the receipt
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: (_ for _ in ()).throw(
        reg.CrossRefRefused("on ref heads/laptop/x at commit abc")))
    with pytest.raises(reg.RegistryError, match="laptop/x at commit abc"):
        reg.freeze_confirmation_cohort(EID, [1, 2], {"rule": "t"}, path=led, ids_dir=ids)
    lines = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: f"receipt {no_fetch}")
    reg.freeze_confirmation_cohort(EID, [1, 2], {"rule": "t"}, path=led, ids_dir=ids, no_fetch=True,
                                   echo=lines.append)
    assert lines == ["receipt True"] and reg.load(led)[0]["confirmation_cohort"]["n"] == 2


def test_the_cli_freeze_passes_no_fetch_through(monkeypatch):
    from click.testing import CliRunner

    from cli import cli
    from src.walters import intl_shadow as us
    seen = {}

    def fake_freeze(eid, ids, basis, no_fetch=False, echo=None, **k):
        seen["no_fetch"] = no_fetch
        raise reg.CrossRefRefused(f"{eid}: a cohort on ref heads/laptop/x at commit deadbeef")
    from datetime import datetime
    monkeypatch.setattr(us, "frozen", lambda: ({}, None, None))
    monkeypatch.setattr(us, "cohort", lambda e, s: {
        "state": "provisional", "ids": [1, 2], "n_games": 2, "eligible_stored": 2,
        "fixtures": [{"kickoff": datetime(2026, 10, 9), "status": "scheduled", "code": "WCQ"}] * 2})
    monkeypatch.setattr(reg, "freeze_confirmation_cohort", fake_freeze)
    out = CliRunner().invoke(cli, ["intl-elo-confirm", "--freeze-cohort", "--no-fetch"])
    assert out.exit_code == 2 and "heads/laptop/x at commit deadbeef" in out.output and seen["no_fetch"] is True


def test_the_one_run_reservation_calls_the_guard_before_the_create(monkeypatch, tmp_path):
    monkeypatch.setattr(sx, "RESERVATION", str(tmp_path / "sx.started.json"))
    monkeypatch.setattr(reg, "cross_ref_guard", _raise)
    with pytest.raises(Called) as ei:
        sx.reserve({"rho": -0.1}, no_fetch=True)
    assert ei.value.args[0] == (sx.EID, True) and not os.path.exists(sx.reservation_path())
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: (_ for _ in ()).throw(
        reg.CrossRefRefused(f"{eid}: a run record on ref remotes/origin/laptop/x at commit abc")))
    with pytest.raises(sx.ExpansionRefused, match="laptop/x at commit abc"):
        sx.reserve()
    assert not os.path.exists(sx.reservation_path())
    lines = []
    monkeypatch.setattr(reg, "cross_ref_guard",
                        lambda eid, no_fetch=False, repo=None: f"cross-ref guard: --no-fetch: {reg.NOT_CHECKED}")
    sx.reserve(no_fetch=True, echo=lines.append)
    assert lines == ["cross-ref guard: --no-fetch: other clones not checked"] and os.path.exists(sx.reservation_path())


def test_the_gate_cli_passes_no_fetch_to_the_run(monkeypatch):
    from click.testing import CliRunner

    import cli as climod
    seen = {}
    monkeypatch.setattr(sx, "declared_unrun", lambda: {})
    monkeypatch.setattr(climod, "_soccer_prod_poisson", lambda: ("v22", -0.1, 0.0008))

    def fake_run(rho, coeff, progress=None, meta=None, no_fetch=False, echo=None):
        seen["no_fetch"] = no_fetch
        echo(f"cross-ref guard: --no-fetch: {reg.NOT_CHECKED}")
        raise sx.ExpansionRefused("stop after the guard")
    monkeypatch.setattr(sx, "run", fake_run)
    out = CliRunner().invoke(climod.cli, ["soccer-expansion-gate", "--no-fetch"])
    assert out.exit_code == 2 and seen["no_fetch"] is True and "other clones not checked" in out.output
