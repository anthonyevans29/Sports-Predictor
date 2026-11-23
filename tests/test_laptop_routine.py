"""The laptop's morning routine (ARCHITECT 2026-11-23, addendum 451 item 3; #1067): deploy/hosting/laptop_routine.py.

Item 3(g): every step's command and options exist in cli.py (the law-1 test's method, tests/test_hosting_pack.py, on
this list); the refusal off the laptop; a failing step does not stop the next; --dry-run runs nothing; the weekly
list's exclusions. Also: the daily list exactly as item 3(d), soccer-refresh in no list, and the routine-exit marking.
No step runs for real: the module's one process call (_popen) is replaced by a fake; receipts go to a tmp file; the
weekly list is read from a throwaway DB of its own (never data/)."""
import inspect
import json
import re
import sys
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

    def wait(self):
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
    ("2", "retire-orphans --competition MLB --season 2026"),
    ("3", "evaluate --sport mlb"),
    ("4", "improve --sport mlb --hold-on-pass"),
    ("5", "export-results --sport mlb --competition MLB"),
    ("6", "sync-kalshi"),
    ("7.1", "sync-matches --competition NBA --season 2026 --date-from 2026-11-21 --date-to 2026-11-21"),
    ("7.2", "sync-matches --competition NBA --season 2026 --date-from 2026-11-22 --date-to 2026-11-22"),
    ("7.3", "sync-matches --competition NBA --season 2026 --date-from 2026-11-23 --date-to 2026-11-23"),
    ("7.4", "sync-matches --competition NBA --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"),
    ("8.1", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-21 --date-to 2026-11-21"),
    ("8.2", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-22 --date-to 2026-11-22"),
    ("8.3", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-23 --date-to 2026-11-23"),
    ("8.4", "sync-matches --competition NCAAMB --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"),
    ("9", "sync-teams --competition NCAA --season 2026"),
    ("10", "sync-matches --competition NCAA --season 2026 --date-from 2026-11-15 --date-to 2026-11-22"),
    ("11", "dedupe-matches --competition NCAA --orphans --sample 30"),
    ("12.1", "sync-matches --competition NHL --season 2026 --date-from 2026-11-22 --date-to 2026-11-22"),
    ("12.2", "sync-matches --competition NHL --season 2026 --date-from 2026-11-23 --date-to 2026-11-23"),
    ("12.3", "sync-matches --competition NHL --season 2026 --date-from 2026-11-24 --date-to 2026-11-24"),
    ("13", "export-fixtures --competition NHL"),
    ("14", "nhl-goalie-sync --start 2026-11-22 --end 2026-11-23"),
    ("15.1", "sync-matches --competition ATP --date-from 2026-11-22 --date-to 2026-11-24"),
    ("15.2", "sync-matches --competition WTA --date-from 2026-11-22 --date-to 2026-11-24"),
    ("16.1", "sync-kalshi-atp"),
    ("16.2", "sync-kalshi-wta"),
    ("17", "results-tally"),
]


def test_the_daily_list_is_item_3d_in_its_order():
    got = [(st.label, " ".join(st.argv)) for st in lr.resolve(DAY)]
    assert got == EXPECTED
    # the six-second wait after each basketball day, and after no other daily step
    assert {st.label for st in lr.resolve(DAY) if st.wait_s} == {f"{n}.{k}" for n in (7, 8) for k in range(1, 5)}
    assert all(st.wait_s == 6 for st in lr.resolve(DAY) if st.wait_s)
    # nothing is applied: the two dry runs carry no --apply, improve carries its hold
    assert not any("--apply" in st.argv for st in lr.DAILY)


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


def test_a_routine_exit_is_counted_apart(box, monkeypatch, capsys):
    steps = [lr.Step("1", ("evaluate", "--sport", "mlb")), lr.Step("2", ("improve", "--sport", "mlb"),
                                                                   routine=frozenset({3})),
             lr.Step("3", ("results-tally",))]
    monkeypatch.setattr(lr, "resolve", lambda today, weekly=None: steps)
    box.answer = staticmethod(lambda argv: (["x"], 3 if argv[0] == "improve" else 0))
    assert lr.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "2 · python cli.py improve --sport mlb · exit 3" in "\n".join(out)
    assert out[-1] == "✓ laptop-routine: steps run 3/3 · non-zero exits 0 · routine exits 1 · 2 exit 3"
    run = receipts(box.tmp)[-1]
    assert run["routine_exits"] == [{"step": "2", "command": "python cli.py improve --sport mlb", "exit": 3}]
    assert run["nonzero"] == [] and run["exit"] == 0
    assert [r.get("routine_exit") for r in receipts(box.tmp) if r["kind"] == "step"] == [None, True, None]


# ---------------------------------------------------------------- the refusal off the laptop ----

@pytest.mark.parametrize("role", ["host", None, "something"])
@pytest.mark.parametrize("dry", [False, True])
def test_refused_off_the_laptop_exit_2_nothing_run(box, monkeypatch, capsys, role, dry):
    if role is None:
        monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)
    else:
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", role)

    def no_read(since=lr.WEEKLY_FROM):
        raise AssertionError("the weekly list is read before the refusal")
    monkeypatch.setattr(lr, "weekly_list", no_read)
    assert lr.main(["--weekly"] + (["--dry-run"] if dry else [])) == 2
    assert box.calls == [] and box.sleeps == []
    out = capsys.readouterr().out
    assert out.startswith("✗ laptop-routine refused: this machine's role is ") and "Nothing was run." in out
    assert "UTC dates" not in out
    rs = receipts(box.tmp)
    if dry:
        assert rs == []
    else:
        assert [(r["kind"], r["unit"], r["exit"], r["refused"]) for r in rs] == [
            ("laptop_routine", "laptop-routine", 2, "machine_role")]


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
    assert "6 · python cli.py sync-kalshi · exit 1" in "\n".join(step_lines)
    # a sync step's own lines follow its step line: the counts and the orientation line, never plain progress
    i = out.index(next(x for x in out if x.startswith("7.1 · ")))
    assert out[i + 1:i + 3] == ["    > ✓ Matches (NBA): created=0 updated=3 skipped=0",
                                "    > orientation_reversed 1: 59564 · teams_mismatch_refused 0"]
    j = out.index(next(x for x in out if x.startswith("15.2 · ")))
    assert out[j + 1:j + 4] == ["    > ✓ Players (WTA, as teams): created=0 updated=0 skipped=0",
                                "    > ✗ WTA: a cursor left", "    last line: ✗ WTA: a cursor left"]
    assert "  | plain progress" in out                                          # the step's own output streams
    assert out[-1] == ("✗ laptop-routine: steps run 27/27 · non-zero exits 2 · 6 exit 1 · 15.2 exit 1 · "
                       "routine exits 0")
    rs = receipts(box.tmp)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [r["step"] for r in steps] == [lab for lab, _ in EXPECTED]
    assert all(r["unit"] == "laptop-routine" for r in rs)
    assert steps[6]["sync"]["matches"] == {"created": 0, "updated": 3, "skipped": 0}
    assert steps[6]["sync"]["scores_by_team"]["orientation_reversed"] == {"n": 1, "ids": ["59564"]}
    run = rs[-1]
    assert run["kind"] == "laptop_routine" and run["exit"] == 1 and run["steps_run"] == 27
    assert [x["step"] for x in run["nonzero"]] == ["6", "15.2"] and len(rs) == 28


def test_a_step_that_cannot_start_is_a_non_zero_exit_and_the_next_runs(box, monkeypatch, capsys):
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
    assert "1 · python cli.py evaluate --sport mlb · exit ?" in out and out.rstrip().endswith(
        "non-zero exits 1 · 1 exit ? · routine exits 0")


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


def test_nhl_goalie_sync_is_a_sync_its_counts_and_refusal_lines_follow_step_14(box, capsys):
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
    i = out.index(next(x for x in out if x.startswith("14 · python cli.py nhl-goalie-sync ")))
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
    i = out.index(next(x for x in out if x.startswith("3 · python cli.py evaluate ")))
    assert out[i + 1] == "    receipt NOT written: OSError: [Errno 28] No space left on device"
    assert out[-1] == ("✗ laptop-routine: steps run 27/27 · non-zero exits 0 · routine exits 0 · receipts not written 1"
                       " · 3")
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
    assert out[-2] == "    receipt NOT written: PermissionError: read-only logs"
    assert out[-1] == ("✗ laptop-routine: steps run 27/27 · non-zero exits 0 · routine exits 0 · receipts not written 1"
                       " · run")


def test_a_role_read_that_raises_is_refused_exit_2_nothing_run(box, monkeypatch, capsys):
    def boom():
        raise ImportError("no module named src.walters.desk_policy")
    monkeypatch.setattr(lr, "machine_role", boom)
    monkeypatch.setattr(lr, "weekly_list", lambda since=lr.WEEKLY_FROM: pytest.fail("read before the refusal"))
    assert lr.main(["--weekly"]) == 2 and box.calls == []
    out = capsys.readouterr().out
    assert out.startswith("✗ laptop-routine refused: this machine's role is unknown, not laptop ")
    assert "ImportError: no module named src.walters.desk_policy" in out and "UTC dates" not in out
    (r,) = receipts(box.tmp)
    assert (r["exit"], r["refused"], r["machine_role"]) == (2, "machine_role", None)
    assert r["error"] == "ImportError: no module named src.walters.desk_policy"


def test_dry_run_runs_nothing(box, capsys):
    assert lr.main(["--dry-run"]) == 0
    assert box.calls == [] and box.sleeps == [] and receipts(box.tmp) == []
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("laptop-routine · UTC dates: today 2026-11-23 ")
    listed = [x for x in out if re.match(r"^\d+(\.\d+)?\. python cli\.py ", x)]
    assert [x.split(". ", 1)[0] for x in listed] == [lab for lab, _ in EXPECTED]
    assert out[-1] == f"laptop-routine --dry-run: {len(EXPECTED)} steps resolved; nothing run."


def test_weekly_runs_the_whole_season_pass_before_step_9(box, capsys):
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
    assert "W1.1. python cli.py sync-teams --competition NFL --season 2026 [then wait 6s]" in out
    assert out.index("W2.2. python cli.py sync-matches --competition PL --season 2026/27") < out.index(
        "9. python cli.py sync-teams --competition NCAA")


def test_an_unreadable_weekly_list_refuses_the_run(box, monkeypatch, capsys):
    def broken(since=lr.WEEKLY_FROM):
        raise RuntimeError("REFUSED: no DB file")
    monkeypatch.setattr(lr, "weekly_list", broken)
    assert lr.main(["--weekly"]) == 2 and box.calls == []
    assert receipts(box.tmp)[-1]["refused"] == "weekly_list"
    assert "Nothing was run." in capsys.readouterr().out


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
