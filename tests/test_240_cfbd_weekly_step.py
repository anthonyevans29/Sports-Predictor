"""THE HOST'S CFBD READ, item (b) (ARCHITECT 2026-11-03 17:40 ET, addendum 240 item 4), verbatim: "THE HOST'S CFBD
READ (239 item 1(b)): no host chain calls CFBD and the key left the host's checkout at the cutover — so the pregame flag
reaches the host only by a hand run after the migration. RULED: (a) for the 11-09 run's window the hand run is mine, by
block, on the host via systemd-run with host.env, once CFBD_API_KEY is in host.env (the operator's hand step, NAME
checked by my Thursday block, the value never printed); (b) a small ruled PR after #816 puts `ncaa-cfbd-labels --year
2026` on the host's weekly-fullseason chain (Sunday 06:00Z; metered, one read a week — the neutral flags of a week's
games are known days ahead and seldom change), its failure a sync-step failure that stops nothing after it; the daily
ncaa-schedule chain stays as it is."

Pins: the step is on weekly-fullseason exactly once, with those arguments, last, and a real cli command and option;
it is METERED; the chain's go_on names it, so a failing run of it is receipted, pages (the chain's exit) and stops
nothing after it, while a failed listing read still stops the chain before it; ncaa-schedule is unchanged; the timer
is Sunday 06:00 UTC; without CFBD_API_KEY the command refuses with exit 2 before any read. Synthetic throughout: a fake
cli.py in a tmp checkout for sp_run, no network, never data/."""
import dataclasses
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import chains  # noqa: E402
import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox: tmp receipts/lock)

STEP = ["ncaa-cfbd-labels", "--year", "2026"]
SUNDAY = date(2026, 11, 8)


@pytest.fixture
def fs_list(sandbox, monkeypatch):
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\nNCAA|2026\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    return lst


# ------------------------------------------------------------------ the step

def test_the_step_is_on_weekly_fullseason_exactly_once_with_those_args_and_last(fs_list):
    assert chains.NCAA_CFBD_STEP == STEP
    ch = chains.CHAINS["weekly-fullseason"]
    assert ch["steps"] == [STEP] and ch["fullseason"] and ch["backup"] == "daily"
    steps = sp_run.resolve("weekly-fullseason", {}, SUNDAY)
    assert [s for s in steps if s[0] == "ncaa-cfbd-labels"] == [STEP]           # exactly once, those args
    assert steps[-1] == STEP                                                     # last: after the list's syncs
    assert steps[:-1] == sp_run.fullseason_resolve(str(fs_list), sp_run.date_vars(SUNDAY))
    # the cutover readout counts the list alone: the CFBD read is no competition
    import cutover_readiness as cr
    assert cr.fullseason_state(str(fs_list), SUNDAY)["entries"] == ["PL|2026/27", "NCAA|2026"]
    # no other chain carries it (the host's one CFBD read a week)
    assert [n for n, x in chains.CHAINS.items() if any(s and s[0] == "ncaa-cfbd-labels" for s in x.get("steps") or [])] \
        == ["weekly-fullseason"]


def test_the_step_is_a_real_cli_command_and_option():
    """Law 1: test_hosting_pack's option check skips the list-planned chain, so the step is checked here."""
    import cli
    cmd = cli.cli.commands[STEP[0]]
    opts = {o for p in cmd.params for o in (*p.opts, *p.secondary_opts)}
    assert all(t in opts for t in STEP[1:] if t.startswith("--"))
    year = next(p for p in cmd.params if "--year" in p.opts)
    assert year.type.name == "integer" and year.multiple and year.required


def test_the_step_is_metered(sandbox, monkeypatch):
    assert "ncaa-cfbd-labels" not in chains.UNMETERED
    monkeypatch.setenv("SP_PARALLEL_MODE", "designated")
    monkeypatch.setenv("SP_DESIGNATED_DAYS", "Fri,Sat,Mon")
    assert sp_run.metered_skip("ncaa-cfbd-labels", SUNDAY)                      # a Sunday not designated: skipped
    monkeypatch.setenv("SP_DESIGNATED_DAYS", "Sat,Sun")
    assert not sp_run.metered_skip("ncaa-cfbd-labels", SUNDAY)
    monkeypatch.setenv("SP_PARALLEL_MODE", "full")
    assert not sp_run.metered_skip("ncaa-cfbd-labels", SUNDAY)
    (c.REPO / "cli.py").write_text("import sys\nprint('ran', ' '.join(sys.argv[1:]))\n")
    q = sp_run.new_quota()
    assert sp_run.run_steps([STEP], "t", "u", "r", SUNDAY, q) == (0, 1)
    assert (q["metered_run"], q["unmetered_run"]) == (1, 0)                     # counted as a metered step


def test_the_dry_run_prints_it_last_with_the_metered_tag(fs_list, monkeypatch, capsys):
    monkeypatch.setenv("SP_PARALLEL_MODE", "designated")
    monkeypatch.setenv("SP_DESIGNATED_DAYS", "Fri")
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc))   # the Sunday tick
    assert sp_run.main(["weekly-fullseason", "--dry-run"]) == 0
    lines = [x for x in capsys.readouterr().out.splitlines() if re.match(r"^\d+\. ", x)]
    assert lines[-1] == "5. python cli.py ncaa-cfbd-labels --year 2026 [skip: H0-16b]"


# ------------------------------------------------------------------ go_on: receipted, paged, stops nothing after it

FAKE_CLI = """import sys
a = sys.argv[1:]
print("ran", " ".join(a))
if a[0] == "ncaa-cfbd-labels":
    print("REFUSED: no CFBD_API_KEY in .env (never committed, never printed)")
    sys.exit(2)
if a[0] == "sync-matches" and "{fail}" == "listing":
    print("RuntimeError: provider read failed")
    sys.exit(1)
"""


def test_go_on_names_it_and_ncaa_schedule_keeps_its_own():
    ch = chains.CHAINS["weekly-fullseason"]
    assert ch["go_on"] == ("ncaa-cfbd-labels",) and ch["go_on_why"] == chains.CFBD_GO_ON
    assert chains.CFBD_GO_ON.startswith("addendum 240 item 4(b): ")
    assert not ch.get("continue_on_sync_failure")                                # not the wider flag


def test_a_failed_cfbd_read_is_receipted_pages_and_the_chain_ran_every_step(fs_list, capsys):
    """The real weekly-fullseason chain on a fake cli.py: the CFBD read refuses (exit 2); every step ran, the chain's
    exit is the read's (OnFailure pages), the receipt says why it went on, and the closing lines name the step."""
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{fail}", "none"))
    capsys.readouterr()
    assert sp_run.main(["weekly-fullseason"]) == 2
    out = capsys.readouterr().out
    rs = receipts(fs_list.parent)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [s["command"].split()[2] for s in steps] == ["sync-teams", "sync-matches"] * 2 + ["ncaa-cfbd-labels"]
    assert steps[-1]["exit"] == 2 and steps[-1]["continued"] == chains.CFBD_GO_ON
    assert all("continued" not in s for s in steps[:-1])
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 2 and chain["steps_ok"] == 4
    assert chain["failed_steps"] == [{"step": 5, "command": "python cli.py ncaa-cfbd-labels --year 2026", "exit": 2}]
    assert chain["stopped_at"] is None
    assert ("· step 5/5 failed (exit 2): python cli.py ncaa-cfbd-labels --year 2026 — recorded; the chain runs on to "
            "every later step on the stored state, the exit stays the first failure's (addendum 240 item 4(b))") in out
    assert ("  ✗ step 5/5 exit=2: python cli.py ncaa-cfbd-labels --year 2026 — REFUSED: no CFBD_API_KEY in .env "
            "(never committed, never printed)") in out
    assert "stopped at step" not in out


def test_a_failed_cfbd_read_stops_nothing_after_it(fs_list, monkeypatch, capsys):
    """"stops nothing after it": with a step after the read (the chain's own steps, extended here only), the later
    step still runs; the exit stays the read's."""
    monkeypatch.setitem(chains.CHAINS["weekly-fullseason"], "steps", [STEP, ["after-step"]])
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{fail}", "none"))
    assert sp_run.main(["weekly-fullseason"]) == 2
    steps = [r for r in receipts(fs_list.parent) if r["kind"] == "step"]
    assert [s["command"].split()[2] for s in steps][-2:] == ["ncaa-cfbd-labels", "after-step"]
    assert steps[-1]["exit"] == 0
    chain = receipts(fs_list.parent)[-1]
    assert chain["stopped_at"] is None and chain["steps_ok"] == 5
    # the same failure without the chain's go_on stops the run (control)
    rep = {}
    rc, ok = sp_run.run_steps([STEP, ["after-step"]], "t", "u", "r", SUNDAY, sp_run.new_quota(), report=rep)
    assert (rc, ok, rep["stopped_at"]) == (2, 0, 1)
    # and with it, run_steps' default reason is ncaa-schedule's (CHAIN_GO_ON) unless the chain names its own
    rep = {}
    rc, ok = sp_run.run_steps([STEP, ["after-step"]], "t", "u", "r2", SUNDAY, sp_run.new_quota(), report=rep,
                              go_on=("ncaa-cfbd-labels",))
    assert (rc, ok, rep["stopped_at"]) == (2, 1, None)
    assert [r for r in receipts(fs_list.parent) if r.get("run_id") == "r2"][0]["continued"] == sp_run.CHAIN_GO_ON


def test_a_failed_listing_read_still_stops_the_chain_before_the_cfbd_read(fs_list, capsys):
    """Only the CFBD read goes on (and sync-teams, addendum 207 item 4): a failed sync-matches stops the chain as before,
    so that week's read does not run (not continue_on_sync_failure: wider than ruled)."""
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{fail}", "listing"))
    assert sp_run.main(["weekly-fullseason"]) == 1
    chain = receipts(fs_list.parent)[-1]
    assert chain["stopped_at"] == 2 and "ran ncaa-cfbd-labels" not in capsys.readouterr().out


# ------------------------------------------------------------------ the daily chain and the schedule

def test_ncaa_schedule_stays_as_it_is():
    """"the daily ncaa-schedule chain stays as it is": its definition, word for word, as #816 left it."""
    days = ["{today}", *[f"{{today_plus{n}}}" for n in range(1, 8)]]
    assert chains.CHAINS["ncaa-schedule"] == {
        "go_on": ("refresh-by-id",),
        "steps": [*[["sync-matches", "--competition", "NCAA", "--season", "2026", "--date-from", d, "--date-to", d]
                    for d in days],
                  ["refresh-by-id", "--competition", "NCAA", "--days", "7"],
                  ["export-ncaa-predictions", "--id", "ncaa-elo-v2", "--dormant-ok"]]}
    assert not any(s[0] == "ncaa-cfbd-labels" for s in chains.CHAINS["ncaa-schedule"]["steps"])
    t = (ROOT / "deploy" / "hosting" / "systemd" / "sp-ncaa-schedule.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == ["*-*-* 10,22:35:00 UTC"]   # daily 10:35 + 22:35 UTC


def test_the_weekly_chain_runs_sunday_0600_utc():
    t = (ROOT / "deploy" / "hosting" / "systemd" / "sp-weekly-fullseason.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == ["Sun *-*-* 06:00:00 UTC"]
    assert re.search(r"^Unit=(.+)$", t, re.M).group(1) == "sp-chain@weekly-fullseason.service"
    unit = (ROOT / "deploy" / "hosting" / "systemd" / "sp-chain@.service").read_text()
    assert "OnFailure=sp-notify@%i.service" in unit                           # a failed chain exit pages
    assert "EnvironmentFile=-/etc/sports-predictor/host.env" in unit           # the key's source on the host (item (a))


# ------------------------------------------------------------------ without the key: refused, exit 2, nothing read

def test_without_cfbd_api_key_the_command_refuses_exit_2_before_any_read(monkeypatch):
    import cli
    import config
    from src.ingestion import ncaa_cfbd as nc
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, cfbd_api_key=""))
    monkeypatch.setattr(nc, "fetch", lambda *a, **k: pytest.fail("no fetch without the key"))
    monkeypatch.setattr("src.db.database.session_scope", lambda *a, **k: pytest.fail("no DB read without the key"))
    r = CliRunner().invoke(cli.cli, STEP)
    assert r.exit_code == 2
    assert r.output.strip() == "REFUSED: no CFBD_API_KEY in .env (never committed, never printed)"


def test_the_docs_name_the_step():
    h1 = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    row = next(x for x in h1.splitlines() if x.startswith("| sp-weekly-fullseason |"))
    assert "`ncaa-cfbd-labels --year 2026`" in row and "addendum 240 item 4(b)" in row and "| Sun 06:00 UTC |" in row
    spec = (ROOT / "docs" / "specs" / "ncaa-cfbd-labels.md").read_text()
    assert "addendum 240 item 4(b)" in spec
