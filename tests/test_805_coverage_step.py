"""#805, RULED (ARCHITECT 2026-11-03, addendum 225 item 5), verbatim: "`coverage --json` becomes the LAST step of one
daily host chain (intl-daily's tail is the candidate: daily, early, after its syncs; read-only, reads the DB and the
registry; its failure never blocks a sync step — Code names the chain and the step's exit handling in the PR body)."

The step is pinned where it is (intl-daily's last, on no other chain), and its exit handling is pinned as sp_run gives
it, unchanged: a failed coverage step blocks nothing (no step follows it; the chain's exit is the first failure's), a
failed sync-teams before it does not stop it (addendum 207 item 4), and a failed cup sync-matches before it stops the
chain, so it does not run that day. Synthetic throughout: a fake cli.py in a tmp checkout for sp_run; no network, no
real DB, never data/."""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import chains  # noqa: E402
import coverage_map as cm  # noqa: E402
import exports_mirror as em  # noqa: E402
import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox: tmp receipts/lock)

STEP = ["coverage", "--json"]


def test_coverage_is_intl_dailys_last_step_and_on_no_other_chain():
    steps = chains.CHAINS["intl-daily"]["steps"]
    assert steps[-1] == STEP == chains.COVERAGE_STEP and steps.count(STEP) == 1
    # after the cups' sync-teams / sync-matches pairs: every step before it is the chain's own earlier steps
    assert [s[0] for s in steps[3:-1]] == ["sync-teams", "sync-matches"] * len(chains.CUP_SCHEDULE)
    holders = sorted(n for n, ch in chains.CHAINS.items()
                     if any(s and s[0] == "coverage" for s in ch.get("steps") or []))
    assert holders == ["intl-daily"]
    # a daily chain (the timer fires every day) whose backup line is the daily one
    t = (ROOT / "deploy" / "hosting" / "systemd" / "sp-intl-daily.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == ["*-*-* 07:20:00 UTC"]
    assert chains.CHAINS["intl-daily"]["backup"] == "daily"
    assert not chains.CHAINS["intl-daily"].get("continue_on_sync_failure")
    # resolved as written: no placeholder, no --out (its default is the file the mirror expects)
    assert sp_run.resolve("intl-daily", {}, date(2026, 11, 3))[-1] == STEP


def test_the_step_writes_the_file_the_mirror_carries_as_kind_coverage():
    """Its default --out is exports/coverage_<date>.json (relative to the working directory, which sp_run sets to the
    checkout for every step), and the exports mirror's kind rule maps it to <role>/latest/coverage.json."""
    out = cm.default_out(date(2026, 11, 3))
    assert out == "exports/coverage_2026-11-03.json"
    assert em.kind_of(Path(out).name) == "coverage"
    assert cm._out_refusal(Path(out)) is None


def test_coverage_is_unmetered_so_designated_days_never_skip_it(monkeypatch):
    """It reads the DB (mode=ro), the registry, the roadmap and exports/ only: no provider call (the cli body is
    re-checked by test_unmetered_allowlist_holds_against_command_bodies)."""
    assert "coverage" in chains.UNMETERED
    monkeypatch.setattr(c, "setting", lambda k: {"SP_PARALLEL_MODE": "designated",
                                                 "SP_DESIGNATED_DAYS": "Sat"}.get(k))
    tue = date(2026, 11, 3)
    assert sp_run.metered_skip("sync-matches", tue) and not sp_run.metered_skip("coverage", tue)


FAKE_CLI = '''import sys
a = sys.argv[1:]
fail = {FAIL!r}
key = " ".join(a)
print("ran", key)
sys.exit(fail.get(key, 0))
'''


def _run(sandbox, capsys, monkeypatch, fail: dict):
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{FAIL!r}", repr(fail)))
    pushed = []
    monkeypatch.setattr(sp_run, "mirror_after_step", lambda unit, i, cmd, run_id: pushed.append((i, cmd)))
    capsys.readouterr()
    rc = sp_run.main(["intl-daily"])
    out = capsys.readouterr().out
    rs = receipts(sandbox)
    return rc, out, [r for r in rs if r["kind"] == "step"], rs[-1], pushed


def test_a_failed_coverage_step_blocks_nothing_and_the_chain_exit_carries_it(sandbox, capsys, monkeypatch):
    """Its failure (coverage exits 2 on a DB it cannot read) comes after every sync step: all of them ran; the chain's
    exit is its exit (systemd's OnFailure pages), and the exports mirror is pushed after it as after every step."""
    rc, out, steps, chain, pushed = _run(sandbox, capsys, monkeypatch, {"coverage --json": 2})
    assert rc == 2
    assert [s["step"] for s in steps] == list(range(1, 13)) and [s["exit"] for s in steps] == [0] * 11 + [2]
    assert chain["kind"] == "chain" and chain["exit"] == 2 and chain["steps_ok"] == 11
    assert chain["failed_steps"] == [{"step": 12, "command": "python cli.py coverage --json", "exit": 2}]
    assert chain["stopped_at"] == 12
    assert pushed[-1] == (12, "coverage")
    assert "✗ intl-daily: exit=2 steps 11/12" in out
    assert "  ✗ step 12/12 exit=2: python cli.py coverage --json" in out


def test_a_failed_cup_sync_matches_stops_the_chain_before_coverage(sandbox, capsys, monkeypatch):
    """sp_run's rule, unchanged: a failed sync-matches stops a chain that is not continue_on_sync_failure, so that
    day has no host coverage file (the step does not run); the chain's exit is the sync's."""
    rc, out, steps, chain, _ = _run(sandbox, capsys, monkeypatch,
                                    {"sync-matches --competition UEL --season 2026/27": 3})
    assert rc == 3
    assert [s["step"] for s in steps] == list(range(1, 10))
    assert not any("coverage" in s["command"] for s in steps)
    assert chain["stopped_at"] == 9 and chain["steps_ok"] == 8
    assert "  ✗ stopped at step 9/12" in out


def test_a_failed_sync_teams_before_it_does_not_stop_coverage(sandbox, capsys, monkeypatch):
    """addendum 207 item 4: a failed sync-teams runs on to every later step, coverage included; the chain's exit stays
    the first failure's."""
    rc, out, steps, chain, _ = _run(sandbox, capsys, monkeypatch,
                                    {"sync-teams --competition FAC --season 2026/27": 4})
    assert rc == 4
    assert steps[-1]["command"] == "python cli.py coverage --json" and steps[-1]["exit"] == 0
    assert chain["stopped_at"] is None and chain["steps_ok"] == 11
