"""The laptop's morning routine (ARCHITECT 2026-11-23, addendum 451 item 3, amended by addendum 461 items 2 to 4;
#1067): deploy/hosting/laptop_routine.py.

451 item 3(g): every step's command and options exist in cli.py (the law-1 test's method, tests/test_hosting_pack.py,
on this list); the refusal off the laptop; a failing step does not stop the next; --dry-run runs nothing; the weekly
list's exclusions. 461 item 4: "a step that outlives its limit is ended, recorded as timed out, and the next step runs
(a child that sleeps, a limit of one second); a child that ignores SIGTERM is killed; the refusal's test reads
not_laptop_reason on each of its four answers." Also: the daily list exactly as 451 item 3(d) less its step 2 and
renumbered (461 item 2(a)), soccer-refresh in no list, the limits, and the routine-exit marking. No cli.py step runs
for real: the module's one process call (_popen) is replaced by a fake, or, for the two timeout tests, by a python -c
child that sleeps; receipts go to a tmp file; the weekly list is read from a throwaway DB of its own (never data/)."""
import inspect
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import laptop_routine as lr  # noqa: E402

DAY = date(2026, 11, 23)


class FakeProc:
    def __init__(self, lines, rc):
        self.stdout = iter(f"{x}\n" for x in lines)
        self._rc = rc

    def wait(self, timeout=None):
        return self._rc


@pytest.fixture
def box(tmp_path, monkeypatch):
    """Receipts in tmp; no sleep; every process call recorded and answered by `box.answer(argv) -> (lines, rc)`."""
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "log" / "receipts.jsonl"))
    calls, sleeps = [], []

    class Box:
        answer = staticmethod(lambda argv: ([], 0))

    def fake_popen(cmd, **kw):
        assert cmd[0] == sys.executable and cmd[1] == "cli.py" and kw["cwd"] == lr.c.REPO
        calls.append(cmd[2:])
        lines, rc = Box.answer(cmd[2:])
        return FakeProc(lines, rc)

    monkeypatch.setattr(lr, "_popen", fake_popen)
    monkeypatch.setattr(lr, "_sleep", sleeps.append)
    monkeypatch.setattr(lr.c, "utc_now", lambda: datetime(2026, 11, 23, 13, 8, tzinfo=timezone.utc))   # DAY, UTC
    monkeypatch.setattr(lr, "weekly_list", lambda since=lr.WEEKLY_FROM: [("NFL", "2026"), ("PL", "2026/27")])
    Box.calls, Box.sleeps, Box.tmp = calls, sleeps, tmp_path
    return Box


def receipts(tmp):
    p = tmp / "log" / "receipts.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# ---------------------------------------------------------------- the list, item 3(d) ----

EXPECTED = [
    ("1", "sync-matches --competition MLB --season 2026 --date-from 2026-10-15 --date-to 2026-11-24"),
    ("2", "evaluate --sport mlb"),
    ("3", "improve --sport mlb --hold-on-pass"),
    ("4", "export-results --sport mlb --competition MLB"),
    ("5", "sync-kalshi"),
    ("6.1", "sync-matches --competition NBA --season 2026 --date-from 2026-11-21 --date-to 2026-11-21"),
    ("6.2", "sync-matches --competition NBA --season 2026 --date-from 2026-11-22 --date-to 2026-11-22"),
    ("6.3", "sync-matches --competition NBA --season 2026 --date-from 2026-11-23 --date-to 2026-11-23"),
    ("6.4", "sync-matches --competition NBA --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"),
    ("7.1", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-21 --date-to 2026-11-21"),
    ("7.2", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-22 --date-to 2026-11-22"),
    ("7.3", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-23 --date-to 2026-11-23"),
    ("7.4", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"),
    ("8", "sync-teams --competition NCAA --season 2026"),
    ("9", "sync-matches --competition NCAA --season 2026 --date-from 2026-11-15 --date-to 2026-11-22"),
    ("10", "dedupe-matches --competition NCAA --orphans --sample 30"),
    ("11.1", "sync-matches --competition NHL --season 2026 --date-from 2026-11-22 --date-to 2026-11-22"),
    ("11.2", "sync-matches --competition NHL --season 2026 --date-from 2026-11-23 --date-to 2026-11-23"),
    ("11.3", "sync-matches --competition NHL --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"),
    ("12", "export-fixtures --competition NHL"),
    ("13", "nhl-goalie-sync --start 2026-11-22 --end 2026-11-23"),
    ("14.1", "sync-matches --competition ATP --date-from 2026-11-22 --date-to 2026-11-24"),
    ("14.2", "sync-matches --competition WTA --date-from 2026-11-22 --date-to 2026-11-24"),
    ("15.1", "sync-kalshi-atp"),
    ("15.2", "sync-kalshi-wta"),
    ("16", "results-tally"),
]


def test_the_daily_list_is_item_3d_in_its_order():
    """451 item 3(d) less its step 2, renumbered 1..16 in the same order (461 item 2(a)): 16 steps, 26 commands."""
    got = [(st.label, " ".join(st.argv)) for st in lr.resolve(DAY)]
    assert got == EXPECTED
    assert sorted({int(lab.split(".")[0]) for lab, _ in EXPECTED}) == list(range(1, 17)) and len(EXPECTED) == 26
    # the six-second wait after each basketball day, and after no other daily step
    assert {st.label for st in lr.resolve(DAY) if st.wait_s} == {f"{n}.{k}" for n in (6, 7) for k in range(1, 5)}
    assert all(st.wait_s == 6 for st in lr.resolve(DAY) if st.wait_s)
    # nothing is applied: the dry run carries no --apply, improve carries its hold
    assert not any("--apply" in st.argv for st in lr.DAILY)


def test_the_mlb_orphan_dry_run_left_the_routine():
    """461 item 2(a): 451's step 2 leaves the routine; the dry run stays in the architect's block, by hand. Five MLB
    steps stay (451 item 3(f) 7 amended); the module never names the command (test_never_inside_the_watch's pin)."""
    assert [" ".join(st.argv[:1]) for st in lr.DAILY[:5]] == ["sync-matches", "evaluate", "improve", "export-results",
                                                            "sync-kalshi"]
    text = Path(lr.__file__).read_text()
    assert "retire" + "-orphans" not in text and "retire" + "_orphans" not in text
    assert "the dry run stays in the architect's block, by hand, after the routine returns" in " ".join(text.split())


def test_each_entry_carries_its_limit():
    """461 item 3(a): "1,200 for a daily step (each single-day sync counts as its own step), 2,400 for each line of the
    weekly pass"; SIGKILL 10 s after SIGTERM. Constants in the module, set by no environment variable. RULED
    (ARCHITECT 2026-11-23 15:20 ET, addendum 469 item 5(1)): "THE LIMIT IS EACH COMMAND'S, AS BUILT: 2,400 s for each
    command of a weekly line and 1,200 s for each command of a daily step." So W k.1 and W k.2 carry 2,400 s each and
    the two-command daily steps 14 and 15 carry 1,200 s per command."""
    assert (lr.DAILY_STEP_LIMIT, lr.WEEKLY_LINE_LIMIT, lr.KILL_GRACE) == (1200, 2400, 10)
    assert all(st.limit_s == 1200 for st in lr.DAILY) and all(st.limit_s == 1200 for st in lr.resolve(DAY))
    full = lr.resolve(DAY, [("PL", "2026/27"), ("NFL", "2026")])
    assert [(st.label, st.limit_s) for st in full if st.label.startswith("W")] == [
        ("W1.1", 2400), ("W1.2", 2400), ("W2.1", 2400), ("W2.2", 2400)]
    assert "environ" not in inspect.getsource(lr.run) and "getenv" not in Path(lr.__file__).read_text()
    # no read of the environment anywhere in the module but the child's env (run_step's `{**os.environ, ...}`): every
    # os.environ in the module's AST is that one dict unpacking
    import ast
    tree = ast.parse(Path(lr.__file__).read_text())
    environ = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "environ"]
    unpacked = [v for n in ast.walk(tree) if isinstance(n, ast.Dict) for k, v in zip(n.keys, n.values) if k is None]
    assert len(environ) == 1 and environ[0] in unpacked
    assert "getenv" not in {getattr(n, "attr", getattr(n, "id", None)) for n in ast.walk(tree)}


def test_the_dates_are_utc_from_date_vars_plus_today_minus_2_and_8():
    import sp_run
    v = lr.routine_vars(DAY)
    assert {k: v[k] for k in sp_run.date_vars(DAY)} == sp_run.date_vars(DAY)
    assert (v["today_minus2"], v["yesterday"], v["today"], v["tomorrow"], v["today_minus8"]) == (
        "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24", "2026-11-15")
    assert lr.dates_line(v, False).startswith("laptop-routine · UTC dates: today 2026-11-23 · yesterday 2026-11-22")


def test_every_step_command_and_option_exists_in_cli():
    """The law-1 test's method (tests/test_hosting_pack.py, test_every_chain_command_and_option_exists_in_cli) on this
    list: the daily list, and the weekly pass's two commands."""
    import cli
    checked = 0
    for st in lr.resolve(DAY, [("PL", "2026/27")]):
        cmd = cli.cli.commands.get(st.argv[0])
        assert cmd is not None, f"{st.label}: no cli command {st.argv[0]!r}"
        opts = {o for p in cmd.params for o in (*p.opts, *p.secondary_opts)}
        for tok in st.argv[1:]:
            if tok.startswith("--"):
                assert tok in opts, f"{st.label}: {st.argv[0]} has no option {tok}"
        checked += 1
    assert checked == len(EXPECTED) + 2


def test_soccer_refresh_is_in_no_list():
    every = [*lr.DAILY, *lr.resolve(DAY), *lr.resolve(DAY, [("PL", "2026/27"), ("NFL", "2026")]),
             *lr.weekly_steps([("PL", "2026/27")])]
    assert every and not any("soccer-refresh" in st.argv for st in every)
    assert {st.argv[0] for st in lr.weekly_steps([("PL", "2026/27")])} == {"sync-teams", "sync-matches"}


# ---------------------------------------------------------------- the routine-exit marking ----

def test_improve_gives_a_rejection_no_non_zero_exit_so_no_step_is_marked():
    """Read from cli.py (law 1): improve_cmd's one SystemExit is 2, under LegacySoccerImproveRefused, which
    training.improve raises for soccer only; a rejection prints its label and returns (exit 0). The mlb step's routine
    set is therefore empty, and so is every step's."""
    import ast
    import textwrap

    import cli
    from src.walters import training
    body = inspect.getsource(cli.cli.commands["improve"].callback)
    assert re.findall(r"SystemExit\((\d+)\)", body) == ["2"]
    # every way the callback could leave non-zero, read from its AST: its ONE raise is SystemExit(2) inside the
    # LegacySoccerImproveRefused handler, and it calls no exit or abort (sys.exit, ctx.exit, click's Exit, os._exit,
    # ctx.abort/Abort) anywhere
    tree = ast.parse(textwrap.dedent(body))
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    assert [ast.unparse(n) for n in raises] == ["raise SystemExit(2)"]
    handlers = [h for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
                and ast.unparse(h.type) == "LegacySoccerImproveRefused"]
    assert len(handlers) == 1 and raises[0] in list(ast.walk(handlers[0]))
    exits = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call)
             and (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")).lower()
             in ("exit", "_exit", "abort")]
    assert exits == []
    assert re.search(r"except LegacySoccerImproveRefused as e:\n.*\n\s+raise SystemExit\(2\)", body)
    assert 'label = "PROMOTED" if result.promoted else ("HELD" if result.held else "REJECTED")' in body
    src = inspect.getsource(training.improve)
    assert re.search(r"if sport == Sport\.SOCCER:\n\s+raise LegacySoccerImproveRefused", src)
    improve = next(st for st in lr.DAILY if st.argv[0] == "improve")
    assert improve.argv == ("improve", "--sport", "mlb", "--hold-on-pass") and improve.routine == frozenset()
    assert all(st.routine == frozenset() for st in lr.DAILY)


def counts_and_note(out):
    """479 item 1(b): the run's last printed line is EXITS_NOTE, after the counts; returns the counts line."""
    assert out[-1] == lr.EXITS_NOTE == ("exits counted, not outcomes: a step that exits 0 may still have failed "
                                        "(see #1102)")
    return out[-2]


def test_a_routine_exit_is_counted_apart(box, monkeypatch, capsys):
    steps = [lr.Step("1", ("evaluate", "--sport", "mlb")), lr.Step("2", ("improve", "--sport", "mlb"),
                                                                   routine=frozenset({3})),
             lr.Step("3", ("results-tally",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)
    box.answer = staticmethod(lambda argv: (["x"], 3 if argv[0] == "improve" else 0))
    assert lr.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "2 · python cli.py improve --sport mlb · exit 3" in "\n".join(out)
    assert counts_and_note(out) == "✓ laptop-routine: steps run 3/3 · failed 0 · non-zero exits 0 · routine exits 1 · 2 exit 3"
    run = receipts(box.tmp)[-1]
    assert run["routine_exits"] == [{"step": "2", "command": "python cli.py improve --sport mlb", "exit": 3}]
    assert run["nonzero"] == [] and run["exit"] == 0
    assert [r.get("routine_exit") for r in receipts(box.tmp) if r["kind"] == "step"] == [None, True, None]


# ---------------------------------------------------------------- the refusal off the laptop ----

# not_laptop_reason's four answers (tests/test_not_laptop_reason.py), each driven from the machine's own sources as
# that file drives them: host.env (SP_HOST_ENV), the environment's role, the checkout's .env (desk_policy.DOTENV).
FOUR_ANSWERS = {
    "host": ("SP_EXPORTS_MIRROR_ROLE=host\n", "laptop", "this machine's role is host"),
    "unset": (None, None, "the role is unknown (SP_EXPORTS_MIRROR_ROLE unset)"),
    "neither": (None, "something", "the role 'something' is not host or laptop"),
    "unreadable": (dir, "laptop", "host.env exists but cannot be read: the role is unknown"),
}


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Set this machine's role sources for one of FOUR_ANSWERS (or the laptop), and count the routine's reads of
    desk_policy.not_laptop_reason (the real function, wrapped)."""
    from src.walters import desk_policy as dp
    reads = []
    real = dp.not_laptop_reason

    def spy():
        reads.append(real())
        return reads[-1]
    monkeypatch.setattr(dp, "not_laptop_reason", spy)
    monkeypatch.setattr(dp, "DOTENV", tmp_path / "no.env")

    def set_answer(name):
        host_env, env_role, _reason = FOUR_ANSWERS[name] if name != "laptop" else (None, "laptop", None)
        h = tmp_path / "host.env"
        if host_env is dir:
            h.mkdir()
        elif host_env is not None:
            h.write_text(host_env)
        monkeypatch.setenv("SP_HOST_ENV", str(h))
        if env_role is None:
            monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)
        else:
            monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", env_role)
    set_answer.reads = reads
    return set_answer


@pytest.mark.parametrize("answer", sorted(FOUR_ANSWERS))
@pytest.mark.parametrize("dry", [False, True])
def test_refused_off_the_laptop_on_each_of_the_four_answers_exit_2_nothing_run(box, machine, monkeypatch, capsys,
                                                                              answer, dry):
    """461 item 4: 'the refusal's test reads not_laptop_reason on each of its four answers'; 461 item 2(d): 'prints the
    reason and exits 2 with nothing run when it is not None'."""
    machine(answer)
    reason = FOUR_ANSWERS[answer][2]

    def no_read(since=lr.WEEKLY_FROM):
        raise AssertionError("the weekly list is read before the refusal")
    monkeypatch.setattr(lr, "weekly_list", no_read)
    assert lr.main(["--weekly"] + (["--dry-run"] if dry else [])) == 2
    assert machine.reads == [reason]                                  # read once, first, and this is its answer
    assert box.calls == [] and box.sleeps == []
    out = capsys.readouterr().out
    assert out == (f"✗ laptop-routine refused: {reason}; this command runs on the laptop only "
                   "(src.walters.desk_policy.not_laptop_reason). Nothing was run.\n")
    rs = receipts(box.tmp)
    if dry:
        assert rs == []
    else:
        assert [(r["kind"], r["unit"], r["exit"], r["refused"], r["not_laptop_reason"]) for r in rs] == [
            ("laptop_routine", "laptop-routine", 2, "not_laptop_reason", reason)]


def test_the_laptop_reads_none_and_runs(box, machine):
    machine("laptop")
    assert lr.main([]) == 0 and machine.reads == [None] and len(box.calls) == len(EXPECTED)


def test_the_routine_names_no_fence_input_and_not_mirror_role():
    """461 item 2(b) and (c): the routine does not call or name the fence's inputs, in code or in a string, and does
    not rest on closing's environment-first reading (tests/test_host_watch_after_flip.py pins the first)."""
    import ast
    pin = ast.parse((ROOT / "tests" / "test_host_watch_after_flip.py").read_text())
    (FENCE_INPUTS,) = [ast.literal_eval(n.value) for n in pin.body if isinstance(n, ast.Assign)
                       and [getattr(t, "id", None) for t in n.targets] == ["FENCE_INPUTS"]]
    assert "machine_role" in FENCE_INPUTS and "role_reading" in FENCE_INPUTS and "host_fenced" in FENCE_INPUTS
    text = Path(lr.__file__).read_text()
    assert not [w for w in FENCE_INPUTS if re.search(rf"\b{w}\b", text)]
    assert "mirror_role(" not in text.replace("rests on closing.mirror_role(), which reads", "")
    assert "desk_policy.not_laptop_reason()" in inspect.getsource(lr.not_laptop_reason)


def test_a_host_env_saying_host_refuses_whatever_the_checkout_says(box, monkeypatch, tmp_path):
    """desk_policy.role_reading reads host.env first: a host whose checkout's .env (or environment) says laptop is
    still refused."""
    h = tmp_path / "host.env"
    h.write_text("SP_EXPORTS_MIRROR_ROLE=host\n")
    monkeypatch.setenv("SP_HOST_ENV", str(h))
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    assert lr.main([]) == 2 and box.calls == []


# ---------------------------------------------------------------- the run ----

def test_a_failing_step_does_not_stop_the_next(box, capsys):
    def answer(argv):
        if argv[0] == "sync-kalshi":
            return (["Traceback (most recent call last):", "ConnectionError: boom"], 1)
        if argv[:3] == ["sync-matches", "--competition", "WTA"]:
            return (["✓ Players (WTA, as teams): created=0 updated=0 skipped=0",
                     "✗ WTA: a cursor left"], 1)
        if argv[:3] == ["sync-matches", "--competition", "NBA"]:
            return (["→ fetching", "✓ Matches (NBA): created=0 updated=3 skipped=0",
                     "orientation_reversed 1: 59564 · teams_mismatch_refused 0", "plain progress"], 0)
        return (["done"], 0)
    box.answer = staticmethod(answer)
    assert lr.main([]) == 1
    assert [" ".join(a) for a in box.calls] == [x for _, x in EXPECTED]          # every step ran, in order
    assert box.sleeps == [6] * 8                                                 # after each basketball day
    out = capsys.readouterr().out.splitlines()
    assert out[0] == ("laptop-routine · UTC dates: today 2026-11-23 · yesterday 2026-11-22 · tomorrow 2026-11-24 · "
                      "today-2 2026-11-21 · today-8 2026-11-15")
    step_lines = [x for x in out if re.match(r"^\d+(\.\d+)? · python cli\.py ", x)]
    assert [x.split(" · ")[0] for x in step_lines] == [lab for lab, _ in EXPECTED]
    assert all(re.search(r" · exit \d+ · \d+\.\d+s$", x) for x in step_lines)
    assert "5 · python cli.py sync-kalshi · exit 1" in "\n".join(step_lines)
    # a sync step's own lines follow its step line: the counts and the orientation line, never plain progress
    i = out.index(next(x for x in out if x.startswith("6.1 · ")))
    assert out[i + 1:i + 3] == ["    > ✓ Matches (NBA): created=0 updated=3 skipped=0",
                                "    > orientation_reversed 1: 59564 · teams_mismatch_refused 0"]
    j = out.index(next(x for x in out if x.startswith("14.2 · ")))
    assert out[j + 1:j + 4] == ["    > ✓ Players (WTA, as teams): created=0 updated=0 skipped=0",
                                "    > ✗ WTA: a cursor left", "    last line: ✗ WTA: a cursor left"]
    assert "  | plain progress" in out                                          # the step's own output streams
    assert counts_and_note(out) == ("✗ laptop-routine: steps run 26/26 · failed 2 · non-zero exits 2 · 5 exit 1 · 14.2 exit 1 · "
                       "routine exits 0")
    rs = receipts(box.tmp)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [r["step"] for r in steps] == [lab for lab, _ in EXPECTED]
    assert all(r["unit"] == "laptop-routine" for r in rs)
    assert steps[5]["sync"]["matches"] == {"created": 0, "updated": 3, "skipped": 0}
    assert steps[5]["sync"]["scores_by_team"]["orientation_reversed"] == {"n": 1, "ids": ["59564"]}
    run = rs[-1]
    assert run["kind"] == "laptop_routine" and run["exit"] == 1 and run["steps_run"] == 26
    assert [x["step"] for x in run["nonzero"]] == ["5", "14.2"] and run["timed_out"] == [] and len(rs) == 27
    assert run["not_started"] == [] and run["steps_failed"] == 2


def test_a_step_that_cannot_start_is_a_failed_step_with_exit_null_and_the_next_runs(box, monkeypatch, capsys):
    """A step that could not start has exit null, as a timed-out step has: it is counted under "not started", never
    as a non-zero exit, and both count in "failed" (461 item 3(a): "it counts as a failed step")."""
    steps = [lr.Step("1", ("evaluate", "--sport", "mlb")), lr.Step("2", ("results-tally",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)
    seen = []

    def popen(cmd, **kw):
        seen.append(cmd[2])
        if cmd[2] == "evaluate":
            raise FileNotFoundError("no python")
        return FakeProc([], 0)
    monkeypatch.setattr(lr, "_popen", popen)
    assert lr.main([]) == 1 and seen == ["evaluate", "results-tally"]
    out = capsys.readouterr().out
    assert "1 · python cli.py evaluate --sport mlb · exit ?" in out and counts_and_note(out.rstrip().splitlines()) == (
        "✗ laptop-routine: steps run 2/2 · failed 1 · non-zero exits 0 · not started 1 · 1 · routine exits 0")
    run = receipts(box.tmp)[-1]
    assert run["nonzero"] == [] and run["steps_failed"] == 1 and run["not_started"] == [
        {"step": "1", "command": "python cli.py evaluate --sport mlb", "exit": None,
         "not_started": "could not start: FileNotFoundError: no python"}]


def test_a_step_that_cannot_start_is_receipted_as_not_started_with_no_exit_invented(box, monkeypatch):
    steps = [lr.Step("1", ("evaluate", "--sport", "mlb")), lr.Step("2", ("results-tally",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)

    def popen(cmd, **kw):
        if cmd[2] == "evaluate":
            raise FileNotFoundError("no python")
        return FakeProc([], 0)
    monkeypatch.setattr(lr, "_popen", popen)
    assert lr.main([]) == 1
    rs = [r for r in receipts(box.tmp) if r["kind"] == "step"]
    assert rs[0]["exit"] is None and rs[0]["not_started"] == "could not start: FileNotFoundError: no python"
    assert rs[1]["exit"] == 0 and "not_started" not in rs[1]


def test_nhl_goalie_sync_is_a_sync_its_counts_and_refusal_lines_follow_step_13(box, capsys):
    """cli.py nhl_goalie_sync_cmd prints "  counts: ...", "  REFUSED game <id>: goalie lists ..." and "  not in our DB
    (sample): ..."; its name does not start "sync-", and item 3(b) asks a sync's own lines under its step line."""
    def answer(argv):
        if argv[0] == "nhl-goalie-sync":
            return (["NHL-GOALIE-SYNC 2026-11-22 .. 2026-11-23", "  counts: boxscore_calls 5 · rows_written 20",
                     "  keys used (law-1 receipt): none found", "  REFUSED game 2025020311: goalie lists 3/2",
                     "  not in our DB (sample): 2025020312 ×1", "  coverage: plain"], 0)
        return ([], 0)
    box.answer = staticmethod(answer)
    assert lr.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    i = out.index(next(x for x in out if x.startswith("13 · python cli.py nhl-goalie-sync ")))
    assert out[i + 1:i + 4] == ["    > counts: boxscore_calls 5 · rows_written 20",
                                "    > REFUSED game 2025020311: goalie lists 3/2",
                                "    > not in our DB (sample): 2025020312 ×1"]
    assert not out[i + 4].startswith("    > ")


def test_a_receipt_that_cannot_be_written_never_stops_the_next_step(box, monkeypatch, capsys):
    """append_receipt raising (a full disk, a read-only logs/) on one step: every step still runs, the last line still
    prints and counts it, the run receipt names it, and the run exits 1."""
    real, n = lr.c.append_receipt, {"k": 0}

    def flaky(rec):
        n["k"] += 1
        if n["k"] == 3:
            raise OSError(28, "No space left on device")
        return real(rec)
    monkeypatch.setattr(lr.c, "append_receipt", flaky)
    assert lr.main([]) == 1
    assert [" ".join(a) for a in box.calls] == [x for _, x in EXPECTED]
    out = capsys.readouterr().out.splitlines()
    i = out.index(next(x for x in out if x.startswith("3 · python cli.py improve ")))
    assert out[i + 1] == "    receipt NOT written: OSError: [Errno 28] No space left on device"
    assert counts_and_note(out) == ("✗ laptop-routine: steps run 26/26 · failed 0 · non-zero exits 0 · routine "
                                    "exits 0 · receipts not written 1 · 3")
    rs = receipts(box.tmp)
    assert [r["step"] for r in rs if r["kind"] == "step"] == [lab for lab, _ in EXPECTED if lab != "3"]
    assert rs[-1]["kind"] == "laptop_routine" and rs[-1]["exit"] == 1
    assert rs[-1]["receipts_not_written"] == [{"step": "3", "error": "OSError: [Errno 28] No space left on device"}]


def test_a_run_receipt_that_cannot_be_written_still_prints_the_last_line(box, monkeypatch, capsys):
    real = lr.c.append_receipt

    def no_run(rec):
        if rec["kind"] == "laptop_routine":
            raise PermissionError("read-only logs")
        return real(rec)
    monkeypatch.setattr(lr.c, "append_receipt", no_run)
    assert lr.main([]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[-3] == "    receipt NOT written: PermissionError: read-only logs"
    assert counts_and_note(out) == ("✗ laptop-routine: steps run 26/26 · failed 0 · non-zero exits 0 · routine "
                                    "exits 0 · receipts not written 1 · run")


def test_a_reason_read_that_raises_is_refused_exit_2_nothing_run(box, monkeypatch, capsys):
    def boom():
        raise ImportError("no module named src.walters.desk_policy")
    monkeypatch.setattr(lr, "not_laptop_reason", boom)
    monkeypatch.setattr(lr, "weekly_list", lambda since=lr.WEEKLY_FROM: pytest.fail("read before the refusal"))
    assert lr.main(["--weekly"]) == 2 and box.calls == []
    out = capsys.readouterr().out
    assert out.startswith("✗ laptop-routine refused: the role could not be read (ImportError: no module named "
                          "src.walters.desk_policy); ")
    assert "Nothing was run." in out and "UTC dates" not in out
    (r,) = receipts(box.tmp)
    assert (r["exit"], r["refused"]) == (2, "not_laptop_reason")
    assert r["not_laptop_reason"] == "the role could not be read (ImportError: no module named src.walters.desk_policy)"
    assert r["error"] == "ImportError: no module named src.walters.desk_policy"


def test_dry_run_runs_nothing(box, capsys):
    assert lr.main(["--dry-run"]) == 0
    assert box.calls == [] and box.sleeps == [] and receipts(box.tmp) == []
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("laptop-routine · UTC dates: today 2026-11-23 ")
    listed = [x for x in out if re.match(r"^\d+(\.\d+)?\. python cli\.py ", x)]
    assert [x.split(". ", 1)[0] for x in listed] == [lab for lab, _ in EXPECTED]
    assert out[-1] == f"laptop-routine --dry-run: {len(EXPECTED)} steps resolved; nothing run."


def test_weekly_runs_the_whole_season_pass_before_step_8(box, capsys):
    assert lr.main(["--weekly"]) == 0
    cmds = [" ".join(a) for a in box.calls]
    i = cmds.index("sync-teams --competition NCAA --season 2026")
    assert cmds[i - 4:i] == ["sync-teams --competition NFL --season 2026", "sync-matches --competition NFL --season 2026",
                             "sync-teams --competition PL --season 2026/27",
                             "sync-matches --competition PL --season 2026/27"]
    assert cmds[i - 5] == "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"
    assert box.sleeps == [6] * 8 + [6] * 4                     # each basketball day, then each weekly command
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("laptop-routine --weekly · UTC dates: ")
    assert out[1] == ("weekly list (2 competition-season(s) with a game from 2026-07-01, less MLB, ATP, WTA, WC, NCAA): "
                      "NFL 2026 · PL 2026/27")
    assert receipts(box.tmp)[-1]["weekly_list"] == ["NFL 2026", "PL 2026/27"]


def test_weekly_dry_run_prints_the_list_and_the_pass_and_runs_nothing(box, capsys):
    assert lr.main(["--weekly", "--dry-run"]) == 0 and box.calls == [] and receipts(box.tmp) == []
    out = capsys.readouterr().out
    assert "W1.1. python cli.py sync-teams --competition NFL --season 2026 [limit 2400s] [then wait 6s]" in out
    assert "\n8. python cli.py sync-teams --competition NCAA --season 2026 [limit 1200s]\n" in out
    assert out.index("W2.2. python cli.py sync-matches --competition PL --season 2026/27") < out.index(
        "8. python cli.py sync-teams --competition NCAA")


def test_an_unreadable_weekly_list_refuses_the_run(box, monkeypatch, capsys):
    def broken(since=lr.WEEKLY_FROM):
        raise RuntimeError("REFUSED: no DB file")
    monkeypatch.setattr(lr, "weekly_list", broken)
    assert lr.main(["--weekly"]) == 2 and box.calls == []
    assert receipts(box.tmp)[-1]["refused"] == "weekly_list"
    assert "Nothing was run." in capsys.readouterr().out


@pytest.fixture
def bad_dotenv(tmp_path, monkeypatch):
    """A checkout .env holding bytes that are not UTF-8 (\\xff\\xfe): sp_common.redact reads it (_dotenv, by
    sp_common's own parse_env_file) and raises UnicodeDecodeError, and desk_policy.not_laptop_reason reads it too
    (DOTENV, no host.env, no role in the environment) and raises. The receipts' own reads (SP_HOST_NAME,
    SP_WRITER_OF_RECORD) are set in the environment, so append_receipt never reaches the .env and only redact fails."""
    from src.walters import desk_policy as dp
    bad = tmp_path / "bad.env"
    bad.write_bytes(b"\xff\xfe" + b"SP_EXPORTS_MIRROR_ROLE=laptop\n")
    monkeypatch.setattr(lr.c, "_dotenv", lambda: lr.c.parse_env_file(bad))
    monkeypatch.setattr(dp, "DOTENV", bad)
    monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "no-host.env"))
    monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)
    for name in lr.c.SECRET_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SP_HOST_NAME", "test-laptop")
    monkeypatch.setenv("SP_WRITER_OF_RECORD", "laptop")
    with pytest.raises(UnicodeDecodeError):
        lr.c.redact("x")
    return bad


@pytest.mark.parametrize("dry", [False, True])
def test_a_role_read_that_raises_while_redact_raises_is_still_refused_exit_2(box, bad_dotenv, monkeypatch, capsys,
                                                                            dry):
    """461 item 3(d): the refusal is exit 2, nothing run. A checkout .env that is not UTF-8 makes not_laptop_reason
    raise AND the handler's redact raise: the error is named by its class alone (_redacted), the refusal line is
    printed, a real run writes exactly one receipt and a --dry-run none; never a traceback with exit 1."""
    with pytest.raises(UnicodeDecodeError):
        lr.not_laptop_reason()                               # the role read itself raises on this .env
    monkeypatch.setattr(lr, "weekly_list", lambda since=lr.WEEKLY_FROM: pytest.fail("read before the refusal"))
    assert lr.main(["--weekly", "--dry-run"] if dry else ["--weekly"]) == 2 and box.calls == []
    out = capsys.readouterr().out
    assert out.startswith("✗ laptop-routine refused: the role could not be read (UnicodeDecodeError); this command "
                          "runs on the laptop only (src.walters.desk_policy.not_laptop_reason). Nothing was run.")
    assert "UTC dates" not in out and "receipt NOT written" not in out
    rs = receipts(box.tmp)
    if dry:
        assert rs == []
    else:
        (r,) = rs
        assert (r["kind"], r["exit"], r["refused"], r["error"]) == ("laptop_routine", 2, "not_laptop_reason",
                                                                    "UnicodeDecodeError")
        assert r["not_laptop_reason"] == "the role could not be read (UnicodeDecodeError)"


def test_an_unreadable_weekly_list_is_refused_exit_2_while_redact_raises(box, bad_dotenv, monkeypatch, capsys):
    """The weekly list's refusal (exit 2, nothing run) with redact raising on the checkout .env: its receipt names the
    error by its class alone, never a traceback."""
    monkeypatch.setattr(lr, "not_laptop_reason", lambda: None)

    def broken(since=lr.WEEKLY_FROM):
        raise RuntimeError("REFUSED: no DB file")
    monkeypatch.setattr(lr, "weekly_list", broken)
    assert lr.main(["--weekly"]) == 2 and box.calls == []
    assert "Nothing was run." in capsys.readouterr().out
    (r,) = receipts(box.tmp)
    assert (r["exit"], r["refused"], r["error"]) == (2, "weekly_list", "RuntimeError")


def test_a_step_that_cannot_start_while_redact_raises_is_not_started_and_the_next_runs(box, bad_dotenv,
                                                                                         monkeypatch, capsys):
    """run_step's could-not-start message with redact raising: the step is recorded not started (exit null, the
    error's class alone), never raised out of run, and the next step runs; the run exits 1."""
    monkeypatch.setattr(lr, "not_laptop_reason", lambda: None)
    steps = [lr.Step("1", ("evaluate", "--sport", "mlb")), lr.Step("2", ("results-tally",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)
    seen = []

    def popen(cmd, **kw):
        seen.append(cmd[2])
        if cmd[2] == "evaluate":
            raise FileNotFoundError("no python")
        return FakeProc([], 0)
    monkeypatch.setattr(lr, "_popen", popen)
    assert lr.main([]) == 1 and seen == ["evaluate", "results-tally"]
    out = capsys.readouterr().out.rstrip().splitlines()
    assert counts_and_note(out) == ("✗ laptop-routine: steps run 2/2 · failed 1 · non-zero exits 0 · not started 1 · 1 · routine "
                       "exits 0")
    step1, step2, run = receipts(box.tmp)
    assert step1["exit"] is None and step1["not_started"] == "could not start: FileNotFoundError"
    assert step2["exit"] == 0 and "not_started" not in step2
    assert run["not_started"] == [{"step": "1", "command": "python cli.py evaluate --sport mlb", "exit": None,
                                   "not_started": "could not start: FileNotFoundError"}]


# ---------------------------------------------------------------- the per-step timeout, 461 item 3(a) ----

SLEEPER = "import time; print('started', flush=True); time.sleep(60)"
DEAF = ("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('deaf', flush=True); "
        "time.sleep(60)")
COUNT_LINE = "✓ Matches (NBA): created=0 updated=3 skipped=0"
CHILDREN = {
    # a sync (its name starts "sync-") whose LAST line, printed just before it exits, is its count line (after 2,000
    # progress lines)
    # in one write, so most of it is still in the pipe when the child has exited
    "sync-counter": ("import os, sys; sys.stdout.write(''.join(f'row {i} {chr(120) * 40}\\n' for i in range(1500)) + "
                     f"{COUNT_LINE!r} + '\\n'); sys.stdout.flush(); os._exit(0)"),
    # more than a pipe's buffer (5,000 lines of about 70 bytes), then a clean exit
    "flood": "for i in range(5000): print('x' * 68)",
    # a grandchild in a new session that holds the pipe open for 4 s after the child has exited 0
    "holder": ("import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(4)'], "
               "start_new_session=True); print('parent done', flush=True)"),
}


@pytest.fixture
def children(box, monkeypatch):
    """The step named "sleeper"/"deaf" runs a real python -c child (SLEEPER, DEAF) through subprocess.Popen with the
    module's own arguments (its pipe, its cwd, its env); every other step is the box's fake. The children are kept."""
    procs = []

    def popen(cmd, **kw):
        code = {"sleeper": SLEEPER, "deaf": DEAF, **CHILDREN}.get(cmd[2])
        if code is None:
            box.calls.append(cmd[2:])
            return FakeProc(["done"], 0)
        p = subprocess.Popen([sys.executable, "-c", code], **kw)
        procs.append(p)
        return p
    monkeypatch.setattr(lr, "_popen", popen)
    yield procs
    for p in procs:                       # never leave a child behind, whatever the test asserted
        if p.poll() is None:
            p.kill()
            p.wait()


def test_a_step_that_outlives_its_limit_is_ended_recorded_as_timed_out_and_the_next_runs(box, children, capsys):
    """461 item 4: a child that sleeps, a limit of one second. It is ended (SIGTERM), its line and receipt say "timed
    out after 1 s", its exit is null, it counts as a failed step (exit 1), the next step runs, and its output streamed
    before the limit (the reader thread)."""
    steps = [lr.Step("1", ("sleeper",)), lr.Step("2", ("results-tally",))]
    t0 = time.monotonic()
    r = lr.run(steps, "t", limit_s=1, grace_s=5)
    took = time.monotonic() - t0
    (p,) = children
    assert p.poll() == -signal.SIGTERM and took < 1 + 5
    assert r["timed_out"] == [("1", "python cli.py sleeper", 1)] and r["failed"] == [] and r["ran"] == 2
    assert r["not_started"] == [] and r["output_errors"] == []
    assert box.calls == [["results-tally"]]                                       # the next step ran
    out = capsys.readouterr().out.splitlines()
    assert "  | started" in out                                                   # streamed, not lost
    assert re.fullmatch(r"1 · python cli\.py sleeper · timed out after 1 s · exit null · \d+\.\ds", out[1])
    assert out[2] == "    last line: started" and out[3] == "  | done" and out[4].startswith("2 · python cli.py "
                                                                                          "results-tally · exit 0 · ")
    rs = receipts(box.tmp)
    assert (rs[0]["step"], rs[0]["exit"], rs[0]["timed_out"], rs[0]["limit_s"], rs[0]["ended_by"]) == (
        "1", None, "timed out after 1 s", 1, "SIGTERM")
    assert "not_started" not in rs[0] and rs[0]["tail"] == ["started"] and rs[1]["exit"] == 0


def test_a_child_that_ignores_sigterm_is_killed(box, children, capsys):
    """461 item 4: 'a child that ignores SIGTERM is killed' (it traps SIGTERM); SIGKILL after the grace (a small one
    here, KILL_GRACE in the module)."""
    steps = [lr.Step("1", ("deaf",)), lr.Step("2", ("results-tally",))]
    t0 = time.monotonic()
    r = lr.run(steps, "t", limit_s=1, grace_s=1)
    took = time.monotonic() - t0
    (p,) = children
    assert p.poll() == -signal.SIGKILL and 2 <= took < 1 + 1 + 4               # gone within the grace
    assert r["timed_out"] == [("1", "python cli.py deaf", 1)] and box.calls == [["results-tally"]]
    out = capsys.readouterr().out
    assert "  | deaf\n" in out and "1 · python cli.py deaf · timed out after 1 s · exit null · " in out
    (rec, _next) = receipts(box.tmp)
    assert (rec["exit"], rec["timed_out"], rec["ended_by"]) == (None, "timed out after 1 s", "SIGKILL")


def test_a_timed_out_step_makes_the_run_exit_1_and_the_last_line_names_it(box, children, monkeypatch, capsys):
    """461 item 3(d): exit 1 when a step timed out; the run receipt lists it with its exit null."""
    steps = [lr.Step("1", ("sleeper",), limit_s=1), lr.Step("2", ("results-tally",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)
    assert lr.main([]) == 1 and box.calls == [["results-tally"]]
    out = capsys.readouterr().out.splitlines()
    assert counts_and_note(out) == ("✗ laptop-routine: steps run 2/2 · failed 1 · non-zero exits 0 · timed out 1 · 1 timed out "
                       "after 1 s · routine exits 0")
    run = receipts(box.tmp)[-1]
    assert run["steps_failed"] == 1 and run["not_started"] == []
    assert run["exit"] == 1 and run["nonzero"] == [] and run["timed_out"] == [
        {"step": "1", "command": "python cli.py sleeper", "exit": None, "timed_out": "timed out after 1 s"}]


class SlowConsole:
    """A console that takes each line slowly (1 ms): draining the pipe's last 64 KB (about 1,400 lines) after the
    child has exited takes longer than the grace (0.5 s here)."""
    def __init__(self, real):
        self.real = real

    def write(self, s):
        time.sleep(0.001)
        return self.real.write(s)

    def flush(self):
        return self.real.flush()


def test_a_syncs_last_count_line_is_kept_when_the_child_exits_right_after_it(box, children, monkeypatch, capsys):
    """The reader drains the pipe after the child has exited, for as long as it is still reading (a slow console
    included), not only for the grace: the count line printed just before the exit is in the echo, under the step
    line, and in the receipt's sync counts, and the output is whole (3 runs, a real child each)."""
    monkeypatch.setattr(sys, "stdout", SlowConsole(sys.stdout))
    steps = [lr.Step(str(k), ("sync-counter",)) for k in range(1, 4)]
    r = lr.run(steps, "t", limit_s=30, grace_s=0.5)
    assert r["failed"] == [] and r["output_errors"] == [] and r["ran"] == 3
    out = capsys.readouterr().out.splitlines()
    for k in range(1, 4):
        i = out.index(next(x for x in out if x.startswith(f"{k} · python cli.py sync-counter · exit 0 · ")))
        assert out[i - 1] == f"  | {COUNT_LINE}" and out[i + 1] == f"    > {COUNT_LINE}"
    rs = receipts(box.tmp)
    assert [x["sync"]["matches"] for x in rs] == [{"created": 0, "updated": 3, "skipped": 0}] * 3
    assert all("output_error" not in x and x["tail"][-1] == COUNT_LINE for x in rs)


def test_the_routines_own_read_error_is_kept_never_a_timeout(box, children, monkeypatch, capsys):
    """redact raising on every line (a .env it cannot decode): the pipe is still drained, so a child writing more than
    the pipe holds is not blocked; its exit (0) stands, no timeout is recorded, and the step and its receipt say its
    output was not read; the run exits 1 (the receipt is not whole)."""
    def bad(s):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    real = lr.c.redact
    monkeypatch.setattr(lr.c, "redact", bad)
    t0 = time.monotonic()
    rc, echo, tail, _dur, timeout, output = lr.run_step(lr.Step("1", ("flood",)), limit_s=20, grace_s=1)
    assert time.monotonic() - t0 < 10
    assert (rc, timeout, echo, tail) == (0, None, [], [])
    assert output == "output not read: UnicodeDecodeError"
    monkeypatch.setattr(lr.c, "redact", real)
    monkeypatch.setattr(lr, "run_step", lambda st, limit_s=None, grace_s=lr.KILL_GRACE: (
        0, [], [], 0.1, None, "output not read: UnicodeDecodeError"))
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: [lr.Step("1", ("evaluate", "--sport", "mlb"))])
    capsys.readouterr()
    assert lr.main([]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[-3] == "    output not read: UnicodeDecodeError"
    assert counts_and_note(out) == ("✗ laptop-routine: steps run 1/1 · failed 0 · non-zero exits 0 · routine exits 0 · "
                                    "output not whole 1 · 1")
    step, run = receipts(box.tmp)
    assert step["exit"] == 0 and step["output_error"] == "output not read: UnicodeDecodeError"
    assert "timed_out" not in step and run["exit"] == 1
    assert run["output_not_whole"] == [{"step": "1", "output_error": "output not read: UnicodeDecodeError"}]


def test_a_pipe_held_open_after_the_child_exits_is_named_and_never_holds_the_morning(box, children):
    """A grandchild in its own session holding the pipe (4 s) after the child exits 0: the step returns after the
    grace with its exit 0, and says its output was not drained; the next step runs."""
    t0 = time.monotonic()
    r = lr.run([lr.Step("1", ("holder",)), lr.Step("2", ("results-tally",))], "t", limit_s=30, grace_s=1)
    assert time.monotonic() - t0 < 3.5
    assert r["failed"] == [] and r["timed_out"] == [] and box.calls == [["results-tally"]]
    assert r["output_errors"] == [("1", "output not drained: the pipe was still open 1 s after the step ended")]
    rec = receipts(box.tmp)[0]
    assert rec["exit"] == 0 and rec["output_error"].startswith("output not drained") and "timed_out" not in rec


def test_a_descendant_writing_after_the_kill_never_holds_the_morning_a_further_limit(box, children, monkeypatch,
                                                                                    tmp_path):
    """461 item 3(a), "the next step runs": the child times out at a 1 s limit and is ended, but a grandchild it
    spawned (its own session, the inherited stdout) writes a line every 0.05 s for 30 s, so the pipe stays open and
    busy. After the kill the drain is capped at the grace (0.3 s here), never the step's limit again: the step returns
    within limit + grace + slack, is recorded as timed out and its output as not drained, and the next step runs."""
    pid_file = tmp_path / "grandchild.pid"
    monkeypatch.setitem(CHILDREN, "spawner", (
        "import subprocess, sys, time; g = subprocess.Popen([sys.executable, '-c', 'import time\\nfor i in range(600):"
        "\\n    print(f\"gc {i}\", flush=True); time.sleep(0.05)'], start_new_session=True); "
        f"open({str(pid_file)!r}, 'w').write(str(g.pid)); print('spawned', flush=True); time.sleep(60)"))
    try:
        t0 = time.monotonic()
        r = lr.run([lr.Step("1", ("spawner",)), lr.Step("2", ("results-tally",))], "t", limit_s=1, grace_s=0.3)
        took = time.monotonic() - t0
        (p,) = children
        assert p.poll() == -signal.SIGTERM
        assert took < 1 + 0.3 + 0.8, took                     # the old drain ran the limit again: 2.2 s at least
        assert r["timed_out"] == [("1", "python cli.py spawner", 1)] and r["failed"] == [] and r["ran"] == 2
        assert r["output_errors"] == [("1", "output not drained: the pipe was still open 0.3 s after the step ended")]
        assert box.calls == [["results-tally"]]                                   # the next step ran
        rec = receipts(box.tmp)[0]
        assert (rec["exit"], rec["timed_out"], rec["ended_by"]) == (None, "timed out after 1 s", "SIGTERM")
        assert rec["output_error"].startswith("output not drained")
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass


def test_a_refusal_resolves_no_time_before_the_read_and_a_real_one_still_receipts_its_run_id(box, machine,
                                                                                            monkeypatch, capsys):
    """The refusal comes before anything else: a refused --dry-run never reads the clock (utc_now raises here); a
    refused real run reads it only after not_laptop_reason, for its one receipt, which carries its run id."""
    machine("host")
    reason = FOUR_ANSWERS["host"][2]

    def no_clock():
        raise AssertionError("utc_now read before the refusal")
    monkeypatch.setattr(lr.c, "utc_now", no_clock)
    assert lr.main(["--dry-run"]) == 2 and machine.reads == [reason] and receipts(box.tmp) == []
    seen = []

    def clock():
        seen.append(list(machine.reads))
        return datetime(2026, 11, 23, 13, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(lr.c, "utc_now", clock)
    assert lr.main([]) == 2 and box.calls == []
    assert seen[0] == [reason, reason]                       # the clock is read after this run's reason read
    (r,) = receipts(box.tmp)
    assert (r["run_id"], r["exit"], r["refused"], r["not_laptop_reason"]) == (
        "20261123T130800Z-laptop-routine", 2, "not_laptop_reason", reason)


def test_a_receipt_error_redact_cannot_read_is_named_by_its_class_and_the_run_goes_on(box, monkeypatch, capsys):
    """append_receipt raising AND redact raising (a checkout .env it cannot decode): _receipt returns the error's
    class name and never raises (as run_step's note), so every step still runs, each line is printed and counted,
    and the run exits 1."""
    def full(rec):
        raise OSError(28, "No space left on device")

    def bad(s):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    monkeypatch.setattr(lr.c, "append_receipt", full)
    monkeypatch.setattr(lr.c, "redact", bad)
    assert lr._receipt({"kind": "step"}) == "OSError"
    capsys.readouterr()
    assert lr.main([]) == 1
    assert [" ".join(a) for a in box.calls] == [x for _, x in EXPECTED]           # the next step ran, every one
    out = capsys.readouterr().out.splitlines()
    assert out.count("    receipt NOT written: OSError") == len(EXPECTED) + 1      # each step's, then the run's
    assert counts_and_note(out).startswith("✗ laptop-routine: steps run 26/26 · failed 0 · non-zero exits 0 · routine exits 0 · "
                              f"receipts not written {len(EXPECTED) + 1} · 1 · 2 · ")
    assert counts_and_note(out).endswith(" · 16 · run")


def test_the_exits_are_0_1_and_2(box, machine, monkeypatch):
    """461 item 3(d): 0 when every step is clean or its exit is routine and every receipt is written; 1 when a step
    failed, timed out or went unreceipted (the tests above); 2 for the refusal, nothing run."""
    machine("laptop")
    assert lr.main([]) == 0
    box.answer = staticmethod(lambda argv: ([], 1 if argv[0] == "evaluate" else 0))
    assert lr.main([]) == 1
    machine("host")
    n = len(box.calls)
    assert lr.main([]) == 2 and len(box.calls) == n


# ---------------------------------------------------------------- the weekly list, on a throwaway DB ----

@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """A throwaway DB of its own (tests/test_mlb_retire_orphans.py's pattern): competitions, teams and one match per
    (competition, season, kickoff) row below."""
    import src.db.database as dbm
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    path = tmp_path / "weekly.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(dbm, "_engine", eng)
    monkeypatch.setattr(dbm, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                          expire_on_commit=False))
    dbm.init_db()
    rows = [  # (sport, code, season, kickoff)
        (Sport.SOCCER, "PL", "2026/27", datetime(2026, 8, 15, 14)),
        (Sport.SOCCER, "PL", "2026/27", datetime(2026, 11, 29, 16)),
        (Sport.SOCCER, "PL", "2025/26", datetime(2026, 5, 24, 15)),          # before the bound: out
        (Sport.SOCCER, "FAC", "2025/26", datetime(2026, 7, 1, 0, 0)),         # exactly the bound: in
        (Sport.SOCCER, "EFL", "2025/26", datetime(2026, 6, 30, 23, 59)),      # a minute before: out
        (Sport.SOCCER, "UNL", "2026/27", datetime(2026, 11, 14, 19, 45)),
        (Sport.SOCCER, "FRIENDLIES_INT", "2026", datetime(2026, 11, 17, 19)),
        (Sport.SOCCER, "WC", "2026", datetime(2026, 7, 19, 19)),             # excluded
        (Sport.NFL, "NFL", "2026", datetime(2026, 11, 22, 18)),
        (Sport.NFL, "NCAA", "2026", datetime(2026, 11, 22, 17)),             # excluded
        (Sport.MLB, "MLB", "2026", datetime(2026, 10, 30, 0)),               # excluded
        (Sport.NHL, "NHL", "2026", datetime(2026, 11, 22, 0)),
        (Sport.BASKETBALL, "NBA", "2026", datetime(2026, 11, 23, 0, 30)),
        (Sport.BASKETBALL, "NCAAMB", "2026", datetime(2026, 11, 22, 1)),
        (Sport.TENNIS, "ATP", "2026", datetime(2026, 11, 17, 12)),           # excluded
        (Sport.TENNIS, "WTA", "2026", datetime(2026, 11, 17, 12)),           # excluded
    ]
    with dbm.session_scope() as s:
        comps = {}
        for sport, code, _season, _ko in rows:
            if code not in comps:
                comps[code] = Competition(sport=sport, code=code, name=code, area="x", type="LEAGUE")
                s.add(comps[code])
        s.flush()
        for n, (sport, code, season, ko) in enumerate(rows):
            h, a = Team(sport=sport, name=f"h{n}"), Team(sport=sport, name=f"a{n}")
            s.add_all([h, a])
            s.flush()
            s.add(Match(sport=sport, competition_id=comps[code].id, season=season, utc_date=ko,
                        status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id))
    return path


def test_the_weekly_list_is_read_with_its_exclusions_and_its_bound(seeded):
    got = lr.weekly_list()
    assert got == [("FAC", "2025/26"), ("FRIENDLIES_INT", "2026"), ("NBA", "2026"), ("NCAAMB", "2026"),
                   ("NFL", "2026"), ("NHL", "2026"), ("PL", "2026/27"), ("UNL", "2026/27")]
    assert not {code for code, _ in got} & set(lr.WEEKLY_EXCLUDED)
    assert lr.WEEKLY_EXCLUDED == ("MLB", "ATP", "WTA", "WC", "NCAA") and lr.WEEKLY_FROM == datetime(2026, 7, 1)


def test_the_weekly_list_reads_read_only(seeded):
    """readonly_scope: mode=ro on the configured file; the read writes nothing (the file's bytes unchanged)."""
    before = seeded.read_bytes()
    lr.weekly_list()
    assert seeded.read_bytes() == before
    import src.db.database as dbm
    src = inspect.getsource(lr.weekly_list)
    assert "readonly_scope()" in src and "session_scope" not in src and dbm.readonly_scope


def test_the_weekly_list_reads_the_checkouts_file_for_a_relative_url(seeded, tmp_path, monkeypatch):
    """A relative DATABASE_URL (the app default sqlite:///./data/sports.db) names the checkout's file, as it does for the
    steps (cwd the checkout), whatever directory the command was started from; the working directory is restored."""
    import src.db.database as dbm
    rel = create_engine(f"sqlite:///./{seeded.name}", future=True)
    monkeypatch.setattr(dbm, "SessionLocal", sessionmaker(bind=rel, autoflush=False, future=True))
    monkeypatch.setattr(lr.c, "REPO", seeded.parent)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    got = lr.weekly_list()
    assert ("PL", "2026/27") in got and len(got) == 8
    assert Path.cwd() == elsewhere and not (elsewhere / seeded.name).exists()


def test_the_last_line_says_exits_are_counted_not_outcomes_and_a_dry_run_prints_no_counts(box, monkeypatch, capsys):
    # 479 item 1(b): "its last printed line, after the counts, reads 'exits counted, not outcomes: a step that exits 0
    # may still have failed (see #N)'": printed after the counts on a clean run and on a failing one, once
    steps = [lr.Step("1", ("evaluate", "--sport", "mlb")), lr.Step("2", ("sync-kalshi",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)
    for rc, code in ((0, 0), (1, 1)):
        box.answer = staticmethod(lambda argv, rc=rc: (["x"], rc if argv[0] == "sync-kalshi" else 0))
        assert lr.main([]) == code
        out = capsys.readouterr().out.splitlines()
        assert counts_and_note(out).startswith(("✓" if code == 0 else "✗") + " laptop-routine: steps run 2/2")
        assert out.count(lr.EXITS_NOTE) == 1
    # the docs name the ten commands, and the two that exit non-zero on every real failure
    doc = lr.__doc__
    assert "THE ROUTINE COUNTS EXITS, NOT OUTCOMES" in doc and "#1102" in doc
    for cmd in ("sync-kalshi:", "sync-kalshi-atp and sync-kalshi-wta:", "export-results:", "sync-matches:",
                "sync-teams:", "improve:", "dedupe-matches (the dry run):", "nhl-goalie-sync:", "results-tally:",
                "evaluate and export-fixtures exit non-zero"):
        assert cmd in doc, cmd
    assert lr.main(["--dry-run"]) == 0
    assert lr.EXITS_NOTE not in capsys.readouterr().out


def test_the_ncaa_step_echoes_and_counts_the_nfl_team_refused_line(box, capsys):
    """ARCHITECT 2026-11-24, addendum 500 item 3(a): "THE NFL-TEAM REFUSAL of Q9, with its count line". Step 9 is the
    NCAA sync-matches: its line is echoed under the step line and carried on the step's receipt, the stored match id
    beside its listing id (addendum 527 item 1 (3))."""
    def answer(argv):
        if argv[:3] == ["sync-matches", "--competition", "NCAA"]:
            return (["✓ Matches (NCAA): created=0 updated=4 skipped=2",
                     "nfl_team_refused 2: 61234 (match 66178), 61300"], 0)
        return (["done"], 0)
    box.answer = staticmethod(answer)
    lr.main([])
    out = capsys.readouterr().out.splitlines()
    i = out.index(next(x for x in out if x.startswith("9 · ")))
    assert out[i + 1:i + 3] == ["    > ✓ Matches (NCAA): created=0 updated=4 skipped=2",
                                "    > nfl_team_refused 2: 61234 (match 66178), 61300"]
    step = next(r for r in receipts(box.tmp) if r["kind"] == "step" and r["step"] == "9")
    assert step["sync"]["nfl_team_refused"] == {"n": 2, "ids": ["61234", "61300"], "matches": ["66178", None]}
