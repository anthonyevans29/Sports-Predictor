"""H1 hosting pack (deploy/hosting/): inert artifacts, tested here without a host.

Law-1 receipts in CI: every chain command and option exists in cli.py; the
UNMETERED allowlist holds against the command bodies; no timer fires in the
H0-3 reboot buffer; soccer-refresh has no timer and refuses without
--operator. Plus sp_run / backup / migrate / receipts / prune behaviour in
tmp dirs (never data/)."""
import inspect
import json
import re
import sqlite3
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))

import chains  # noqa: E402
import sp_backup  # noqa: E402
import sp_common as c  # noqa: E402
import sp_migrate  # noqa: E402
import sp_prune  # noqa: E402
import sp_receipts  # noqa: E402
import sp_run  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Receipts/lock/backups in tmp; no host.env; a fake checkout as REPO."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    # the deploy's no-venv fallback keeps its install record inside the RUNNING virtualenv: never let a test write
    # into the developer's real venv (tests run as if from a system interpreter unless they say otherwise)
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)
    for k in ("SP_PARALLEL_MODE", "SP_DESIGNATED_DAYS", "NTFY_TOPIC", "NTFY_SERVER", "SP_FULLSEASON_LIST"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "log" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "lib" / "db.lock"))
    monkeypatch.setenv("SP_BACKUP_DIR", str(tmp_path / "backups"))
    db = tmp_path / "live" / "sports.db"
    db.parent.mkdir()
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE matches(id INTEGER); CREATE TABLE predictions(id INTEGER);"
                      "INSERT INTO matches VALUES (1),(2),(3); INSERT INTO predictions VALUES (9);")
    con.commit()
    con.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    return tmp_path


def receipts(tmp):
    p = tmp / "log" / "receipts.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# ---------------------------------------------------------------- law 1 ----

def _cli():
    import cli
    return cli.cli


def test_every_chain_command_and_option_exists_in_cli():
    cli = _cli()
    checked = 0
    for name, ch in chains.CHAINS.items():
        if ch.get("fullseason") or ch.get("window_plan"):
            continue  # DB-planned chains: covered by their own seeded-DB tests
        for st in sp_run.resolve(name, ch.get("example_vars", {}), date(2026, 10, 9)):  # closing: run-time vars
            cmd = cli.commands.get(st[0])
            assert cmd is not None, f"{name}: no cli command {st[0]!r}"
            opts = {o for p in cmd.params for o in (*p.opts, *p.secondary_opts)}
            for tok in st[1:]:
                if tok.startswith("--"):
                    assert tok in opts, f"{name}: {st[0]} has no option {tok}"
            checked += 1
    assert checked >= 30


def test_unmetered_allowlist_holds_against_command_bodies():
    cli = _cli()
    net = re.compile(r"IngestionService|get_adapter|_adapter_for|requests\.|urlopen")
    for name in chains.UNMETERED:
        body = inspect.getsource(cli.commands[name].callback)
        assert not net.search(body), f"{name} reaches the network; not UNMETERED"


# -------------------------------------------------------- systemd pack ----

def _timers():
    out = {}
    for p in (HOSTING / "systemd").glob("*.timer"):
        t = p.read_text()
        out[p.name] = (re.findall(r"^OnCalendar=(.+)$", t, re.M),
                       re.search(r"^Unit=(.+)$", t, re.M).group(1))
    return out


# H0-3's one exemption, by name (ARCHITECT 2026-10-12, addendum 45 P3): "H0-3's buffer is for chains that write on a
# schedule. A tick with no start due reads the stored schedule and ends, so this one timer is exempt from the buffer
# by name [...] and no start time is ever without a tick." Its own form is test_closing_watch_timer_form below.
H0_3_EXEMPT = {"sp-closing-watch.timer": "the closing watch's tick: a tick with no start due reads the stored "
                                         "schedule and ends; no start time is ever without a tick (addendum 45 P3)"}


def test_no_timer_in_reboot_buffer_and_targets_exist():
    days = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    timers = _timers()
    assert set(H0_3_EXEMPT) <= set(timers) and len(H0_3_EXEMPT) == 1           # one timer, by name
    for fname, (cals, unit) in timers.items():
        assert cals, fname
        if fname in H0_3_EXEMPT:
            continue                  # its own form: test_closing_watch_timer_form; every other timer still H0-3
        m = re.match(r"sp-chain@(.+)\.service$", unit)
        if m:
            assert m.group(1) in chains.CHAINS and m.group(1) != "soccer-refresh"
        else:
            assert (HOSTING / "systemd" / unit).exists(), unit
        for cal in cals:
            mm = re.fullmatch(r"(?:([A-Za-z,]+) )?\*-\*-\* ([\d.,]+):(\d\d):00 (\S+)", cal)
            assert mm, f"{fname}: unexpected calendar {cal!r}"
            hours = []  # "00..03,06..23" -> every hour, each one checked
            for part in mm.group(2).split(","):
                lo, _, hi = part.partition("..")
                hours += list(range(int(lo), int(hi or lo) + 1))
            mi, tz = int(mm.group(3)), ZoneInfo(mm.group(4))
            for hh in hours:
                for probe in (date(2026, 1, 15), date(2026, 7, 15)):  # both DST states
                    local = datetime(probe.year, probe.month, probe.day, hh, mi, tzinfo=tz)
                    u = local.astimezone(timezone.utc)
                    minutes = u.hour * 60 + u.minute
                    assert not (4 * 60 + 15 <= minutes <= 5 * 60 + 15), f"{fname} {cal} -> {u:%H:%M}Z"
            if mm.group(1):
                assert all(d in days for d in mm.group(1).split(","))


def test_closing_watch_timer_form():
    """Addendum 45 P3: "One calendar line: every minute of every hour." Persistent=false, AccuracySec=1s, its own
    service, OnFailure to sp-notify with closing-watch -> sp-closing-watch.service, the 45-minute bound, NFL and
    SOCCER by name (P2), and the watch's own statuses (refusal 2, notified 3) counted as success."""
    t = (HOSTING / "systemd" / "sp-closing-watch.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == ["*-*-* *:*:00 UTC"]   # one line, every minute, UTC
    assert re.search(r"^Unit=sp-closing-watch\.service$", t, re.M)
    assert re.search(r"^Persistent=false$", t, re.M) and re.search(r"^AccuracySec=1s$", t, re.M)
    u = (HOSTING / "systemd" / "sp-closing-watch.service").read_text()
    assert re.search(r"^OnFailure=sp-notify@closing-watch\.service$", u, re.M)
    assert re.search(r"^ExecStart=\S+python deploy/hosting/closing\.py watch --family NFL --family SOCCER$", u, re.M)
    assert re.search(r"^SuccessExitStatus=2 3$", u, re.M) and re.search(r"^TimeoutStartSec=45min$", u, re.M)
    assert re.search(r"^User=sp$", u, re.M) and "EnvironmentFile=-/etc/sports-predictor/host.env" in u
    import closing
    assert closing.NOTIFIED == 3
    rb = (ROOT / "docs" / "specs" / "h2-cutover-runbook.md").read_text()          # Codex on #449: the host's role
    assert "closing.py preflight --family NFL --family SOCCER --expect-role host" in rb
    assert closing.main(["preflight", "--expect-role", "host", "--family", "NFL"]) in (0, 2)   # the option parses
    import sp_notify
    assert sp_notify.unit_for("closing-watch") == "sp-closing-watch.service"
    assert sp_notify.unit_for("window") == "sp-chain@window.service"             # the rest unchanged


def test_soccer_refresh_is_operator_only(sandbox):
    assert not any("soccer-refresh" in u for _, u in _timers().values())
    assert chains.CHAINS["soccer-refresh"]["backup"] == "prerefresh"
    assert sp_run.main(["soccer-refresh"]) == 2
    assert receipts(sandbox)[-1]["refused"] == "operator_only"
    assert "--operator" in (HOSTING / "systemd" / "sp-soccer-refresh.service").read_text()


def test_improve_step_holds_and_units_force_hold():
    steps = chains.CHAINS["mlb-morning"]["steps"]
    assert ["improve", "--sport", "mlb", "--hold-on-pass"] in steps
    assert steps[-1] == ["results-tally"]
    assert "SP_IMPROVE_HOLD_ON_PASS=1" in (HOSTING / "systemd" / "sp-chain@.service").read_text()


# ------------------------------------------------------------- sp_run ----

FAKE_CLI = '''import sys
a = sys.argv[1:]
print("ran", " ".join(a))
if "page" in a:
    print("SP-PAGE: test page line")
if "fail" in a:
    print("boom API_KEY=abc123secret")
    sys.exit(3)
'''


def test_date_vars():
    fri = sp_run.date_vars(date(2026, 10, 2))
    assert (fri["sat"], fri["sat_plus3"], fri["yesterday"]) == ("2026-10-03", "2026-10-06", "2026-10-01")
    assert sp_run.date_vars(date(2026, 10, 3))["sat"] == "2026-10-03"


def test_sp_run_receipts_page_and_stop_at_failure(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    monkeypatch.setitem(chains.CHAINS, "t-chain", {"backup": "daily", "steps": [
        ["one", "--d", "{today}"], ["two", "page"], ["three", "fail"], ["never"]]})
    rc = sp_run.main(["t-chain"])
    assert rc == 3
    rs = receipts(sandbox)
    kinds = [r["kind"] for r in rs]
    assert kinds[0] == "backup" and rs[0]["integrity"] == "ok"  # daily taken first
    assert kinds.count("step") == 3 and "page" in kinds
    fail = [r for r in rs if r["kind"] == "step"][-1]
    assert fail["exit"] == 3 and "abc123secret" not in json.dumps(fail)
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 3 and chain["steps_ok"] == 2
    assert chain["counts"]["matches"] == 3 and chain["counts"]["odds_snapshots"] is None
    assert chain["backup"]["sha256"] == rs[0]["sha256"]
    # second run the same day reuses the verified daily backup, takes no new one
    monkeypatch.setitem(chains.CHAINS, "t-ok", {"backup": "daily", "steps": [["one"]]})
    assert sp_run.main(["t-ok"]) == 0
    assert [r["kind"] for r in receipts(sandbox)].count("backup") == 1


# --- the window chain runs on past a failed SYNC step (ARCHITECT 2026-10-16, addendum 84 item 2(b)) ----------------
# "in the window chain a sync step's failure is recorded and notified as now, but does not stop the chain — the later
# sync steps and the card/export steps run; a failure in a card/export step still ends the chain. [...] the chain's
# exit stays 1 when any step failed, so the failure notice still fires." The case of 2026-10-15 14:05Z: step 1,
# sync-matches UEL 2026/27, raised the provider's free-plan refusal and the chain stopped at 0/15.

def _window_like(monkeypatch, steps):
    import sp_window_page
    posted = []
    monkeypatch.setattr(sp_window_page, "run", lambda p: posted.append(p) or {
        "deltas": {}, "paged": False, "digest": False, "suppressed": 0, "freshen_needed": []})
    monkeypatch.setitem(chains.CHAINS, "t-win", {"steps": steps, "post": "window_page",
                                                 "continue_on_sync_failure": True})
    return posted


def test_a_failed_sync_step_is_recorded_the_rest_and_the_card_run_and_the_exit_stays_non_zero(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    posted = _window_like(monkeypatch, [["sync-matches", "--competition", "UEL", "fail"], ["sync-odds", "x"],
                                        ["sync-kalshi-soccer", "fail"], ["window-card", "--hours", "24"]])
    assert sp_run.main(["t-win"]) == 3                       # non-zero: systemd's OnFailure still pages
    steps = [r for r in receipts(sandbox) if r["kind"] == "step"]
    assert [s_["command"].split()[2] for s_ in steps] == ["sync-matches", "sync-odds", "sync-kalshi-soccer",
                                                          "window-card"]
    assert [s_["exit"] for s_ in steps] == [3, 0, 3, 0]
    assert all("continued" in s_ for s_ in steps if s_["exit"]) and not any("continued" in s_ for s_ in steps
                                                                           if not s_["exit"])
    chain = receipts(sandbox)[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 3 and chain["steps_ok"] == 2 and chain["stopped_at"] is None
    assert [f["step"] for f in chain["failed_steps"]] == [1, 3]
    assert len(posted) == 1                                  # the card ran, so the hour's page is not blanked
    assert "page" in chain


def test_a_failed_card_step_still_ends_the_chain_and_no_page_is_posted(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    posted = _window_like(monkeypatch, [["sync-matches", "fail"], ["window-card", "fail"], ["export-after"]])
    assert sp_run.main(["t-win"]) == 3
    steps = [r for r in receipts(sandbox) if r["kind"] == "step"]
    assert [s_["command"].split()[2] for s_ in steps] == ["sync-matches", "window-card"]   # export-after never runs
    chain = receipts(sandbox)[-1]
    assert chain["stopped_at"] == 2 and [f["step"] for f in chain["failed_steps"]] == [1, 2]
    assert posted == [] and "page" not in chain


def test_the_last_output_lines_name_the_failed_sync_step_so_the_failure_page_carries_it(sandbox, monkeypatch, capsys):
    """sp_notify pages the journal's last 30 lines. A run that went on past a failed sync step pushed that step's
    output out of them, so the chain's closing lines name each failure (step, command, exit, last line, redacted)."""
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    _window_like(monkeypatch, [["sync-matches", "--competition", "UEL", "fail"]] + [["sync-odds", str(k)]
                                                                                   for k in range(20)]
                 + [["window-card", "--hours", "24"]])
    capsys.readouterr()
    assert sp_run.main(["t-win"]) == 3
    out = capsys.readouterr().out.rstrip("\n").split("\n")
    assert "· sync step 1/22 failed (exit 3): python cli.py sync-matches --competition UEL fail" in "\n".join(out)
    assert out[-1].startswith("  ✗ step 1/22 exit=3: python cli.py sync-matches --competition UEL fail — boom ")
    assert "abc123secret" not in out[-1] and "[REDACTED]" in out[-1]     # the receipt's redacted tail, not the stream
    assert out[-2].startswith("✗ t-win: exit=3 steps 21/22")
    assert not any(x.startswith("  ✗ stopped at") for x in out)
    _window_like(monkeypatch, [["sync-matches", "fail"], ["window-card", "fail"], ["export-after"]])
    capsys.readouterr()
    assert sp_run.main(["t-win"]) == 3
    tail = capsys.readouterr().out.rstrip("\n").split("\n")[-3:]
    assert tail[0].startswith("  ✗ step 1/3 exit=3: python cli.py sync-matches fail")
    assert tail[1].startswith("  ✗ step 2/3 exit=3: python cli.py window-card fail") and tail[2] == "  ✗ stopped at step 2/3"


def test_only_the_window_chain_runs_on_and_other_chains_still_stop_at_the_first_failure(sandbox, monkeypatch):
    assert chains.CHAINS["window"].get("continue_on_sync_failure") is True
    assert not any(ch.get("continue_on_sync_failure") for name, ch in chains.CHAINS.items() if name != "window")
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    monkeypatch.setitem(chains.CHAINS, "t-plain", {"steps": [["sync-matches", "fail"], ["sync-odds"]]})
    assert sp_run.main(["t-plain"]) == 3
    steps = [r for r in receipts(sandbox) if r["kind"] == "step"]
    assert len(steps) == 1 and "continued" not in steps[0]
    assert receipts(sandbox)[-1]["stopped_at"] == 1


def test_designated_days_skip_metered_only(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    monkeypatch.setenv("SP_PARALLEL_MODE", "designated")
    monkeypatch.setenv("SP_DESIGNATED_DAYS", "")
    monkeypatch.setitem(chains.CHAINS, "t-mix", {"steps": [["sync-odds"], ["sync-kalshi"]]})
    assert sp_run.main(["t-mix"]) == 0
    steps = [r for r in receipts(sandbox) if r["kind"] == "step"]
    assert steps[0]["skipped"] == "H0-16b" and steps[1]["exit"] == 0


def test_inactive_and_fullseason_guard(sandbox, monkeypatch):
    monkeypatch.setitem(chains.CHAINS, "t-late", {"active_from": "2999-01-01", "steps": [["x"]]})
    assert sp_run.main(["t-late"]) == 0
    assert receipts(sandbox)[-1]["skipped"].startswith("inactive_until")
    with pytest.raises(SystemExit, match="SP_FULLSEASON_LIST"):
        sp_run.resolve("weekly-fullseason", {}, date(2026, 10, 4))
    lst = sandbox / "fs.list"
    lst.write_text("# c\nPL|2026/27\nNFL|2026\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    assert sp_run.resolve("weekly-fullseason", {}, date(2026, 10, 4)) == [
        ["sync-matches", "--competition", "PL", "--season", "2026/27"],
        ["sync-matches", "--competition", "NFL", "--season", "2026"]]


# ------------------------------------------------------- backup / prune ----

def test_backup_refuses_data_dir(sandbox, monkeypatch):
    monkeypatch.setenv("SP_BACKUP_DIR", str(c.REPO / "data" / "bk"))
    with pytest.raises(SystemExit, match="law 5"):
        sp_backup.run_backup("daily")
    assert not (c.REPO / "data").exists()


def test_prerefresh_never_overwrites(sandbox):
    a = sp_backup.run_backup("prerefresh")
    b = sp_backup.run_backup("prerefresh")
    assert a["exit"] == b["exit"] == 0 and a["file"] != b["file"]
    assert sp_backup.todays_daily() is None  # prerefresh never counts as the daily


def test_prune_plan():
    now = datetime(2026, 11, 30, tzinfo=timezone.utc)
    d = Path("/nonexistent")

    class FakeDir:
        def glob(self, pat):
            names = [f"sports_2026-11-{i:02d}.db" for i in range(1, 31)]
            names += ["sports_2026-10-01_prerefresh_0900.db", "sports_2026-11-20_prerefresh_0900.db",
                      "notes.db"]
            return [d / n for n in names]
    doomed = {p.name for p in sp_prune.plan(FakeDir(), now, keep_daily=7, retain_days=14)}
    assert "sports_2026-11-15.db" in doomed and "sports_2026-11-16.db" not in doomed
    assert "sports_2026-10-01_prerefresh_0900.db" in doomed
    assert "sports_2026-11-20_prerefresh_0900.db" not in doomed and "notes.db" not in doomed


# ------------------------------------------------------------ migrate ----

def test_migrate_pack_verify_install_roundtrip(sandbox, monkeypatch, capsys):
    (c.REPO / ".env").write_text("API_FOOTBALL_KEY=zz\n")
    (c.REPO / "exports").mkdir()
    (c.REPO / "exports" / "mlb_predictions_2026-10-08.json").write_text("[1,2]")
    pk = sandbox / "pack"
    assert sp_migrate.main(["pack", "--out", str(pk)]) == 0
    man = json.loads((pk / "MANIFEST.json").read_text())
    assert man["counts"] == {"matches": 3, "predictions": 1}
    assert set(man["files"]) == {"sports.db", "env", "exports/mlb_predictions_2026-10-08.json"}
    assert man["absent"] == ["receipts.jsonl"] or "receipts.jsonl" in man["files"]
    assert sp_migrate.main(["verify", "--pack", str(pk)]) == 0

    # the "host": a fresh checkout with no data/
    host = sandbox / "host"
    host.mkdir()
    monkeypatch.setattr(c, "REPO", host)
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/sports.db")
    assert sp_migrate.main(["install", "--pack", str(pk)]) == 0
    assert c.table_counts(host / "data" / "sports.db") == {"matches": 3, "predictions": 1}
    assert (host / ".env").stat().st_mode & 0o777 == 0o600
    assert (host / "exports" / "mlb_predictions_2026-10-08.json").read_text() == "[1,2]"
    with pytest.raises(SystemExit, match="exists"):
        sp_migrate.main(["install", "--pack", str(pk)])
    assert sp_migrate.main(["install", "--pack", str(pk), "--replace"]) == 0
    assert list((host / "data").glob("rehearsal_*.db"))

    # tamper -> FAIL
    con = sqlite3.connect(pk / "sports.db")
    con.execute("INSERT INTO matches VALUES (4)")
    con.commit()
    con.close()
    assert sp_migrate.main(["verify", "--pack", str(pk)]) == 1
    out = capsys.readouterr().out
    assert "sha256 mismatch sports.db" in out and "count matches: R1=3 R2=4" in out


def test_install_refuses_absolute_laptop_db_url(sandbox, monkeypatch):
    (c.REPO / ".env").write_text("DATABASE_URL=sqlite:////Users/x/sp/data/sports.db\n")
    pk = sandbox / "pack2"
    assert sp_migrate.main(["pack", "--out", str(pk)]) == 0
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        sp_migrate.main(["install", "--pack", str(pk)])


def test_pack_refuses_data_dir(sandbox):
    with pytest.raises(SystemExit, match="law 5"):
        sp_migrate.main(["pack", "--out", str(c.REPO / "data" / "p")])


# ----------------------------------------------------------- receipts ----

def test_receipts_table_failures_first(sandbox):
    c.append_receipt({"kind": "chain", "unit": "sp-chain@a.service", "exit": 0,
                      "steps_ok": 2, "steps_total": 2, "duration_s": 3.0, "exports": []})
    c.append_receipt({"kind": "chain", "unit": "sp-chain@b.service", "exit": 1,
                      "steps_ok": 0, "steps_total": 2, "duration_s": 1.0, "exports": []})
    rs = sp_receipts.rows(c.utc_now() - timedelta(hours=1), steps=False)
    t = sp_receipts.table(rs).splitlines()
    assert "sp-chain@b.service" in t[2] and "**1**" in t[2]
    assert "sp-chain@a.service" in t[3]


def test_redact(monkeypatch):
    monkeypatch.setenv("API_HOCKEY_KEY", "hk-verysecretvalue")
    assert "verysecret" not in c.redact("url?key=x hk-verysecretvalue token: abc")
    assert c.redact("token: abc") == "token: [REDACTED]"


# ---------------------------------------- final-four rulings (2026-09-27) ----

import pull_backup  # noqa: E402
import sp_notify  # noqa: E402


def test_ntfy_page_posts_to_private_topic_and_logs(sandbox, monkeypatch):
    (c.REPO / ".env").write_text("NTFY_TOPIC=sp-secret-topic-xyz\n")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    sent = {}

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        sent.update(url=req.full_url, body=req.data.decode(), title=req.headers["Title"])
        return R()
    monkeypatch.setattr(sp_notify.urllib.request, "urlopen", fake_urlopen)
    assert sp_notify.deliver("page", "sports-predictor: operator action",
                             "SP-PAGE: improve --sport mlb PASS HELD — candidate v9") is True
    assert sent["url"] == "https://ntfy.sh/sp-secret-topic-xyz"
    assert "PASS HELD" in sent["body"]
    r = receipts(sandbox)[-1]  # pages AND logs
    assert r["kind"] == "page" and r["delivered"] is True and r["channel"] == "ntfy"
    assert "sp-secret-topic-xyz" not in json.dumps(receipts(sandbox))


def test_no_topic_logs_undelivered(sandbox):
    assert sp_notify.ntfy_url() is None
    assert sp_notify.deliver("failure", "t", "b") is False
    assert receipts(sandbox)[-1]["delivered"] is False


def test_retention_default_is_14_dailies_report_only(sandbox, monkeypatch):
    bk = sandbox / "backups"
    bk.mkdir()
    for i in range(1, 31):
        (bk / f"sports_2026-11-{i:02d}.db").write_text("x")
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 11, 30, 12, tzinfo=timezone.utc))
    assert sp_prune.main() == 0
    r = receipts(sandbox)[-1]
    assert r["applied"] is False and len(r["files"]) == 16  # 30 - newest 14
    assert "sports_2026-11-16.db" in r["files"] and "sports_2026-11-17.db" not in r["files"]
    assert len(list(bk.glob("*.db"))) == 30  # report-only: nothing deleted


def test_pull_selects_newest_daily_and_verifies(sandbox):
    names = ["sports_2026-10-07.db", "sports_2026-10-08.db", "sports_2026-10-08.db.sha256",
             "sports_2026-10-09_prerefresh_0900.db", "sports_2026-10-08_101500.db", "junk"]
    assert pull_backup.newest_daily(names) == "sports_2026-10-08_101500.db"
    assert pull_backup.newest_daily(["junk"]) is None
    src = sandbox / "live" / "sports.db"
    part, side = sandbox / "x.db.partial", sandbox / "x.db.sha256.partial"
    part.write_bytes(src.read_bytes())
    side.write_text(f"{c.sha256_file(src)}  x.db\n")
    out = pull_backup.verify_and_place(part, side, sandbox / "x.db")
    assert out["integrity"] == "ok" and (sandbox / "x.db.sha256").exists()
    part.write_bytes(b"corrupt")
    side.write_text("0" * 64 + "  y.db\n")
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        pull_backup.verify_and_place(part, side, sandbox / "y.db")
    with pytest.raises(SystemExit, match="law 5"):
        pull_backup.main(["--dest", str(c.REPO / "data" / "bk")])


def test_pull_verifies_a_wal_copy_immutable_and_leaves_its_folder_as_found(sandbox, monkeypatch):
    """#517 (ARCHITECT 2026-10-14, addendum 68 item 2): "an immutable read-only open of a WAL copy with no sidecars
    returns integrity ok and leaves the folder as it found it, and verify_and_place takes that path." The laptop's
    (macOS) mode=ro open of such a copy fails ("unable to open database file"); Linux's creates the -shm and -wal
    beside it, so a mode=ro verify here would leave them in the folder."""
    live = sandbox / "wal_live.db"
    src = sqlite3.connect(live)
    assert src.execute("PRAGMA journal_mode=wal").fetchone()[0] == "wal"
    src.execute("CREATE TABLE t(x)")
    src.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(50)])
    src.commit()
    pulled = sandbox / "pulled"
    pulled.mkdir()
    part = pulled / "sports_2026-10-14_093021.db.partial"
    dst = sqlite3.connect(part)
    src.backup(dst)
    dst.close()
    src.close()
    assert part.read_bytes()[18:20] == b"\x02\x02"                 # the copy is WAL-mode, no sidecar beside it
    assert sorted(x.name for x in pulled.iterdir()) == [part.name]
    assert c.copy_integrity(part) == "ok"
    assert sorted(x.name for x in pulled.iterdir()) == [part.name]  # nothing created beside it
    side = pulled / "sports_2026-10-14_093021.db.sha256.partial"
    side.write_text(f"{c.sha256_file(part)}  sports_2026-10-14_093021.db\n")
    uris = []
    real = sqlite3.connect
    monkeypatch.setattr(c.sqlite3, "connect", lambda d, *a, **k: uris.append(str(d)) or real(d, *a, **k))
    final = pulled / "sports_2026-10-14_093021.db"
    out = pull_backup.verify_and_place(part, side, final)
    assert out["integrity"] == "ok"
    assert uris and all(u.endswith("?mode=ro&immutable=1") for u in uris)   # verify_and_place takes that path
    assert sorted(x.name for x in pulled.iterdir()) == [final.name, final.name + ".sha256"]
    # the live DB is never opened immutable (#340 stands)
    assert "immutable" not in inspect.getsource(c.ro_connect)


def _wal(db: Path) -> None:
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA journal_mode=wal").fetchone()[0] == "wal"
    con.close()


def test_the_host_backup_of_a_wal_db_verifies_immutable_and_leaves_no_partial_sidecar(sandbox, monkeypatch):
    """#517 (ARCHITECT 2026-10-15, addendum 72 item 4): "every daily of 10-11..10-15 (07:20 and 09:30) sits beside a
    32768-byte .partial-shm and an empty .partial-wal [...] written by the host's own verify (Linux opens the .partial
    copy mode=ro and makes them [...]). [...] the host's verify opens the copy the way #526's does (immutable=1, so no
    sidecar is made in the first place)." On a mode=ro verify this folder holds the two sidecars."""
    _wal(sandbox / "live" / "sports.db")
    uris = []
    real = sqlite3.connect
    monkeypatch.setattr(c.sqlite3, "connect", lambda d, *a, **k: uris.append(str(d)) or real(d, *a, **k))
    rec = sp_backup.run_backup("daily")
    assert rec["exit"] == 0 and rec["integrity"] == "ok"
    bk = sandbox / "backups"
    assert sorted(x.name for x in bk.iterdir()) == [rec["file"], rec["file"] + ".sha256"]
    assert (bk / rec["file"]).read_bytes()[18:20] == b"\x02\x02"           # the copy is WAL-mode
    assert any(u.endswith(".db.partial?mode=ro&immutable=1") for u in uris)  # the verify took the immutable open
    assert "immutable" not in inspect.getsource(c.ro_connect)               # the live DB never (#340 stands)


def test_a_failed_host_backup_removes_every_partial_and_nothing_else(sandbox, monkeypatch):
    """Addendum 72 item 4: "the cleanup globs of pull_backup and sp_backup take "*.partial*"". A failed run leaves no
    .partial, .partial-shm or .partial-wal in the folder; the backups and their .sha256 files stay."""
    bk = sandbox / "backups"
    bk.mkdir()
    keep = ["sports_2026-10-11.db", "sports_2026-10-11.db.sha256"]
    gone = ["sports_2026-10-11.db.partial-shm", "sports_2026-10-11.db.partial-wal",
            "sports_2026-10-11_092959.db.partial-shm"]
    for n in keep + gone:
        (bk / n).write_bytes(b"x")
    monkeypatch.setattr(c, "copy_integrity", lambda p: "*** in database main *** Page 2 is never used")
    rec = sp_backup.run_backup("daily")
    assert rec["exit"] == 1 and "integrity_check" in rec["error"]
    assert sorted(x.name for x in bk.iterdir()) == keep


def test_a_failed_pull_removes_every_partial(sandbox, monkeypatch):
    """Addendum 72 item 4: pull_backup's cleanup glob takes "*.partial*": the .partial, the .sha256.partial and
    anything beside them."""
    dest = sandbox / "pulled"
    dest.mkdir()
    for n in ("sports_2026-10-15.db.partial", "sports_2026-10-15.db.sha256.partial",
              "sports_2026-10-15.db.partial-shm", "sports_2026-10-15.db.partial-wal"):
        (dest / n).write_bytes(b"x")
    (dest / "sports_2026-10-14.db").write_bytes(b"kept")

    def run(cmd, **kw):
        if cmd[0] == "ssh" and cmd[-1].startswith("ls"):
            return types.SimpleNamespace(stdout="sports_2026-10-15.db\nsports_2026-10-15.db.sha256\n")
        if cmd[0] == "ssh":
            return types.SimpleNamespace(stdout="0" * 64 + "  sports_2026-10-15.db\n")
        raise pull_backup.subprocess.CalledProcessError(1, cmd)               # scp fails
    monkeypatch.setattr(pull_backup.subprocess, "run", run)
    assert pull_backup.main(["--dest", str(dest)]) == 1
    assert sorted(x.name for x in dest.iterdir()) == ["sports_2026-10-14.db"]


def test_prune_leaves_partial_files_to_the_cleanup(tmp_path):
    """Addendum 72 item 4: "sp_prune leaves them to that cleanup": an old backup is planned, never a .partial* file."""
    for n in ("sports_2026-09-01.db", "sports_2026-09-01.db.sha256", "sports_2026-09-01.db.partial",
              "sports_2026-09-01.db.partial-shm", "sports_2026-09-01.db.partial-wal"):
        (tmp_path / n).write_bytes(b"x")
    doomed = sp_prune.plan(tmp_path, datetime(2026, 11, 30, tzinfo=timezone.utc), keep_daily=0, retain_days=14)
    assert [p.name for p in doomed] == ["sports_2026-09-01.db"]


def _uris(monkeypatch):
    uris = []
    real = sqlite3.connect
    monkeypatch.setattr(c.sqlite3, "connect", lambda d, *a, **k: uris.append(str(d)) or real(d, *a, **k))
    return uris


def test_the_closing_backup_of_a_wal_db_opens_its_copies_immutable(sandbox, monkeypatch):
    """#532 (ARCHITECT 2026-10-15, addendum 73 item 4): "copy_integrity for the copies; the final copy's open in
    take_backup likewise". A WAL source's closing backup leaves the .db and its .sha256 and nothing beside them; on
    the mode=ro opens Linux left a .partial-shm / .partial-wal and a .db-shm / .db-wal here (the Mac cannot open such
    a copy mode=ro at all, #517)."""
    import closing
    _wal(sandbox / "live" / "sports.db")
    uris = _uris(monkeypatch)
    folder = sandbox / "closing-backups"
    rec = closing.take_backup(folder, date(2026, 10, 15))
    assert rec["ok"] and rec["integrity"] == "ok" and rec["opens"]
    assert sorted(x.name for x in folder.iterdir()) == ["sports_2026-10-15.db", "sports_2026-10-15.db.sha256"]
    copies = [u for u in uris if "closing-backups" in u and u.startswith("file:")]   # the reads (the write is a path)
    assert copies and all(u.endswith("?mode=ro&immutable=1") for u in copies)               # .partial and final
    assert any(u.endswith(".db.partial?mode=ro&immutable=1") for u in copies)
    assert any(u.endswith("sports_2026-10-15.db?mode=ro&immutable=1") for u in copies)
    live = [u for u in uris if u.endswith("live/sports.db?mode=ro")]
    assert live and not any("live/sports.db" in u and "immutable" in u for u in uris)       # the live DB never (#340)


def test_the_migrate_pack_reads_its_copy_immutable_and_install_reads_the_live_db_mode_ro(sandbox, monkeypatch):
    """#532 (addendum 73 item 4): sp_migrate's pack and verify read the pack's copy immutable; install's verify reads
    the installed DB, the live one from then on, mode=ro (#340)."""
    _wal(sandbox / "live" / "sports.db")
    uris = _uris(monkeypatch)
    pk = sandbox / "pack"
    assert sp_migrate.main(["pack", "--out", str(pk)]) == 0
    assert not [x.name for x in pk.iterdir() if x.name.endswith(("-shm", "-wal"))]
    assert sp_migrate.main(["verify", "--pack", str(pk)]) == 0
    pack_db = [u for u in uris if "/pack/sports.db" in u and u.startswith("file:")]
    assert pack_db and all(u.endswith("?mode=ro&immutable=1") for u in pack_db)
    host = sandbox / "host"
    host.mkdir()
    monkeypatch.setattr(c, "REPO", host)
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/sports.db")
    uris.clear()
    assert sp_migrate.main(["install", "--pack", str(pk)]) == 0
    installed = [u for u in uris if "/host/data/sports.db" in u and u.startswith("file:")]
    assert installed and all(u.endswith("?mode=ro") for u in installed)


def test_ncaa_timer_ships_enabled_in_runbook():
    rb = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    t11 = rb[rb.index("TIMERS=\""):rb.index("echo $TIMERS")]  # TIMERS + MLB_LAPTOP_ONLY
    assert "HELD_B4" not in rb  # B4 ruled: the model-bearing timers enable with the rest
    enabled = t11[:t11.index("MLB_LAPTOP_ONLY=")]
    for mlb in ("sp-mlb-morning.timer", "sp-mlb-preslate.timer", "sp-clv-capture.timer"):
        assert mlb not in enabled, f"{mlb} must stay OFF the host enable list (statsapi ASN block)"
    # Addendum 45 P3 held sp-closing-watch.timer on a third T11 list until the cutover ruling; ARCHITECT 2026-10-26,
    # addendum 168 item 5: "sp-closing-watch.timer moves to TIMERS (CI's check follows)". The third list is retired.
    assert "sp-closing-watch.timer" in enabled and "HELD_FOR_CUTOVER=" not in t11
    for f in (HOSTING / "systemd").glob("*.timer"):
        assert f.name in t11, f"{f.name} missing from the T11 lists"


def test_the_t11_lists_the_shipped_timers_and_the_schedule_table_agree():
    """ARCHITECT 2026-10-23, addendum 155 item 8(b): "a CI check (read-only) that the T11 TIMERS list, the shipped
    systemd/*.timer files and docs/specs/hosting-h1.md's table agree". Every shipped timer is on exactly one T11 list;
    every name on a T11 list is shipped; the Schedule table has one row per shipped timer and none other."""
    lists = c.t11_lists()
    shipped = c.shipped_timers()
    named = [t for n in c.T11_LISTS for t in lists[n]]
    assert len(shipped) >= 20 and all(lists[n] for n in c.T11_LISTS)
    assert sorted(set(named)) == sorted(named), f"a timer on two T11 lists: {sorted({t for t in named if named.count(t) > 1})}"
    assert sorted(named) == shipped, (f"shipped, on no T11 list: {sorted(set(shipped) - set(named))}; "
                                      f"on a T11 list, not shipped: {sorted(set(named) - set(shipped))}")
    rb = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    table = rb[rb.index("### Schedule"):]
    table = table[:table.index("\n\n", table.index("| Timer |"))]
    rows = [f"{m}.timer" for m in re.findall(r"^\| (sp-[\w-]+) \|", table, re.M)]
    assert sorted(set(rows)) == sorted(rows), f"a timer with two rows: {sorted({t for t in rows if rows.count(t) > 1})}"
    assert sorted(rows) == shipped, (f"shipped, no Schedule row: {sorted(set(shipped) - set(rows))}; "
                                     f"a Schedule row, not shipped: {sorted(set(rows) - set(shipped))}")



# ------------------------------- the prediction timers, retired (ARCHITECT 2026-10-25, addendum 166 item 6(B)) ----
# "(B) THE TIMERS RETIREMENT PR [...] addendum 126 item 2(d) rules the host's fixed-time PREDICTION timers retired by
# the cutover. Law 1 first: enumerate from deploy/hosting/chains.py what each of sp-nfl-predict, sp-soccer-friday and
# sp-soccer-saturday actually runs, step by step. Retire ONLY the predict + slate-export steps the watch's slate stage
# duplicates; a weekly ratings refresh, a grade, a results export or a whole-season sync that one of those chains also
# carries is KEPT (moved to its own unit or left in a renamed chain — propose, do not decide)."
PL_ARGS = ["--competition", "PL", "--season", "2026/27"]
# What each chain ran on main f0e4cbf, before the retirement (chains.py, read 2026-10-25), and which steps retire.
BEFORE_166B = {
    "nfl-predict": [["sync-injuries", "--competition", "NFL", "--season", "2026"], ["capture-weather-nfl"],
                    ["predict-nfl"], ["export-nfl-predictions"]],
    "soccer-prematch": [["sync-matches", *PL_ARGS], ["sync-odds", *PL_ARGS], ["sync-injuries", *PL_ARGS],
                        *[[v, "--competition", x, "--season", "2026/27"] for x in ("PD", "SA", "BL1", "FL1", "ELC")
                          for v in ("sync-matches", "sync-odds")],
                        *[["sync-kalshi-soccer", "--competition", x] for x in ("PD", "SA", "BL1", "FL1", "ELC")],
                        ["sync-kalshi-soccer"],
                        ["predict", "--sport", "soccer", *PL_ARGS],
                        ["export-predictions", "--sport", "soccer", "--competition", "PL",
                         "--start", "{sat}", "--end", "{sat_plus3}", "--status", "scheduled"]],
}
RETIRED_166B = {"nfl-predict": BEFORE_166B["nfl-predict"][2:], "soccer-prematch": BEFORE_166B["soccer-prematch"][-2:]}
# timer -> (its calendar lines, unchanged; the chain it runs now; the chain it ran before)
TIMERS_166B = {
    "sp-nfl-prematch.timer": (["Thu *-*-* 18:00:00 UTC", "Sun *-*-* 14:00:00 UTC"], "nfl-prematch", "nfl-predict"),
    "sp-soccer-friday.timer": (["Fri *-*-* 14:00:00 UTC"], "soccer-prematch", "soccer-prematch"),
    "sp-soccer-saturday.timer": (["Sat *-*-* 10:30:00 Europe/London"], "soccer-prematch", "soccer-prematch"),
}


def _slate_steps_of(fam):
    """The slate stage's own steps for a synthetic day (closing.slate_steps: resolve_steps, the closing's resolution,
    SOCCER's export gaining its window), so the retired steps are compared with what the slate stage really runs."""
    import closing
    day = date(2026, 10, 31)
    covers = [{"match_id": 7, "start": datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)}]
    return closing.slate_steps(fam, day, covers, datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc), "RID")


def test_the_three_timers_keep_their_schedules_and_run_only_the_kept_steps():
    timers = _timers()
    assert "sp-nfl-predict.timer" not in timers and "nfl-predict" not in chains.CHAINS     # renamed, not duplicated
    for t, (cals, chain, before) in TIMERS_166B.items():
        assert timers[t] == (cals, f"sp-chain@{chain}.service"), t
        kept = [s for s in BEFORE_166B[before] if s not in RETIRED_166B[before]]
        assert chains.CHAINS[chain]["steps"] == kept, chain                          # the kept steps, in order
        assert "backup" not in chains.CHAINS[chain] and not chains.CHAINS[chain].get("operator_only")
    assert [s[0] for s in chains.CHAINS["nfl-prematch"]["steps"]] == ["sync-injuries", "capture-weather-nfl"]
    assert all(s[0].startswith("sync-") for s in chains.CHAINS["soccer-prematch"]["steps"])  # every sync stays


def test_each_retired_step_is_one_the_slate_stage_runs_for_the_same_family():
    """A step retires only where the slate stage runs the same command for the same family: the predict word for word,
    the export the same command and competition (the slate's adds --desk and its --out, SOCCER's its window)."""
    nfl, soccer = _slate_steps_of("NFL"), _slate_steps_of("SOCCER")
    assert ["predict-nfl"] in nfl and nfl[-1][0] == "export-nfl-predictions"
    assert RETIRED_166B["nfl-predict"] == [["predict-nfl"], ["export-nfl-predictions"]]
    assert ["predict", "--sport", "soccer", *PL_ARGS] in soccer
    assert soccer[-1][:5] == ["export-predictions", "--sport", "soccer", "--competition", "PL"]
    assert RETIRED_166B["soccer-prematch"][0] in soccer
    assert RETIRED_166B["soccer-prematch"][1][:5] == soccer[-1][:5]
    # the kept steps the slate stage does NOT run as written (whole-league / whole-season / other leagues / weather)
    for chain, slate in (("nfl-prematch", nfl), ("soccer-prematch", soccer)):
        for st in chains.CHAINS[chain]["steps"]:
            assert st[0] not in ("predict", "predict-nfl", "export-predictions", "export-nfl-predictions")
    assert ["capture-weather-nfl"] not in nfl
    assert ["sync-injuries", "--competition", "NFL", "--season", "2026"] not in nfl          # the slate's is scoped
    assert ["sync-matches", *PL_ARGS] not in soccer and ["sync-odds", *PL_ARGS] not in soccer


def test_the_retired_exports_wrote_the_slate_files_names():
    """The in-place rewrite (BACKLOG 2026-10-18, addendum 126 entry, open item 2): the retired exports wrote the slate
    stage's own exports/ names on the days the timers fire. NFL: export-nfl-predictions' default
    exports/nfl_predictions_<UTC date>.json on Thursday 18:00Z and Sunday 14:00Z (the ET date too); SOCCER: Saturday's
    --start {sat} --end {sat_plus3} is the Saturday slate's soccer_PL_<sat>_to_<sat_plus3>.json."""
    import closing
    thu, sun, sat = date(2026, 10, 29), date(2026, 11, 1), date(2026, 10, 31)
    for d in (thu, sun):
        assert closing.slate_file("NFL", d) == f"nfl_predictions_{d.isoformat()}.json"
    v = sp_run.date_vars(sat)
    assert closing.slate_file("SOCCER", sat) == f"soccer_PL_{v['sat']}_to_{v['sat_plus3']}.json"


def test_no_timer_runs_a_live_nfl_or_pl_predict_or_slate_export():
    """After 6(B) no shipped timer's chain predicts or exports NFL or PL: the closing watch's slate stage writes their
    slate files. MLB is not touched (mlb-preslate, a laptop duty: T11's MLB_LAPTOP_ONLY)."""
    retired = {"predict-nfl", "export-nfl-predictions"}
    for t, (_, unit) in _timers().items():
        m = re.match(r"sp-chain@(.+)\.service$", unit)
        if not m:
            continue
        for st in chains.CHAINS[m.group(1)]["steps"]:
            assert st[0] not in retired, (t, st)
            if st[0] in ("predict", "export-predictions"):
                assert "PL" not in st and "soccer" not in st, (t, st)


def test_the_t11_lists_carry_the_renamed_timer():
    lists = c.t11_lists()
    assert "sp-nfl-prematch.timer" in lists["TIMERS"]
    assert not any("sp-nfl-predict.timer" in lists[n] for n in c.T11_LISTS)
    assert {"sp-soccer-friday.timer", "sp-soccer-saturday.timer"} <= set(lists["TIMERS"])
    assert "sp-closing-watch.timer" in lists["TIMERS"] and "HELD_FOR_CUTOVER" not in lists  # on TIMERS from the cutover (addendum 168 item 5)
    rb = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    assert "| sp-nfl-prematch | nfl-prematch (was sp-nfl-predict / nfl-predict;" in rb


import sp_deploy  # noqa: E402


def _enabled(tmp_path, names):
    p = tmp_path / "timers.enabled"
    p.write_text(" ".join(names) + "\n")
    return p


def test_the_deploy_receipt_names_the_shipped_timers_the_host_has_not_enabled(tmp_path):
    """Addendum 155 item 8(b): "a line in the deploy receipt naming any shipped timer not in
    /etc/sports-predictor/timers.enabled on the host (names only)". The 2026-10-23 host: 15 of T11's 16 TIMERS
    enabled, sp-ncaa-schedule.timer never installed."""
    lists = c.t11_lists()
    st = sp_deploy.timers_state(enabled_path=_enabled(tmp_path, [t for t in lists["TIMERS"]
                                                                 if t != "sp-ncaa-schedule.timer"]))
    assert st["not_enabled"] == sorted(["sp-ncaa-schedule.timer", *lists["MLB_LAPTOP_ONLY"]])
    assert st["by_list"] == {"TIMERS": ["sp-ncaa-schedule.timer"], "MLB_LAPTOP_ONLY": sorted(lists["MLB_LAPTOP_ONLY"])}
    line = sp_deploy.timers_line(st)
    assert line.startswith("\n  ! shipped timers not in ") and "sp-ncaa-schedule.timer (TIMERS)" in line
    assert "install and enable it" in line
    # the host as T11 leaves it: only the list T11 holds off is not enabled -> a plain line, no "!"
    ok = sp_deploy.timers_state(enabled_path=_enabled(tmp_path, lists["TIMERS"]))
    assert ok["by_list"].keys() == {"MLB_LAPTOP_ONLY"}
    assert sp_deploy.timers_line(ok).startswith("\n  · shipped timers not in ") and "!" not in sp_deploy.timers_line(ok)
    every = sp_deploy.timers_state(enabled_path=_enabled(tmp_path, c.shipped_timers()))
    assert every["not_enabled"] == [] and "every shipped timer is in" in sp_deploy.timers_line(every)


def test_the_deploy_receipt_never_guesses_when_timers_enabled_is_unreadable(tmp_path):
    """Law 4: a missing file is an error with no list, and the line says so with "!"."""
    st = sp_deploy.timers_state(enabled_path=tmp_path / "absent")
    assert st["not_enabled"] is None and "unreadable (FileNotFoundError)" in st["error"]
    assert sp_deploy.timers_line(st).startswith("\n  ! timers: ")


def test_a_shipped_timer_on_no_t11_list_is_named_unlisted(tmp_path):
    repo = tmp_path / "repo"
    (repo / "deploy" / "hosting" / "systemd").mkdir(parents=True)
    (repo / "docs" / "specs").mkdir(parents=True)
    (repo / "docs" / "specs" / "hosting-h1.md").write_text(
        'TIMERS="sp-a.timer sp-c.timer"\nMLB_LAPTOP_ONLY="sp-b.timer"\n')
    for n in ("sp-a", "sp-b", "sp-c", "sp-new"):
        (repo / "deploy" / "hosting" / "systemd" / f"{n}.timer").write_text("")
    st = sp_deploy.timers_state(repo=repo, enabled_path=_enabled(tmp_path, ["sp-a.timer", "sp-c.timer"]))
    assert st["by_list"] == {"MLB_LAPTOP_ONLY": ["sp-b.timer"], "unlisted": ["sp-new.timer"]}
    assert sp_deploy.timers_line(st).startswith("\n  ! ") and "sp-new.timer (unlisted)" in sp_deploy.timers_line(st)


def _listing(*units, rc=0):
    """A stand-in for `systemctl list-units --type=timer --state=active --no-legend --plain sp-*`: it checks it was
    asked exactly that (sp_common's reader, the cutover preflight's) and answers with these units."""
    calls = []

    def run(argv):
        calls.append(argv)
        assert argv == list(c.ACTIVE_SP_TIMERS_ARGV)
        return rc, "\n".join(f"{u} loaded active waiting desc" for u in units) if rc == 0 else "Failed to connect to bus"
    run.calls = calls
    return run


def test_the_deploy_receipt_names_an_active_sp_timer_the_list_does_not(tmp_path):
    """ARCHITECT 2026-10-26, addendum 168 item 2 (#676): the receipt line "is extended to name ACTIVE timers not on
    the list, not only shipped-but-unlisted ones — a read-only line". The 2026-10-26 host: 14 lines in
    timers.enabled, 16 sp timers active (sp-intl-daily and sp-exports-squash enabled by hand, never listed)."""
    lists = c.t11_lists()
    listed = [t for t in lists["TIMERS"] if t not in ("sp-intl-daily.timer", "sp-exports-squash.timer")]
    path = _enabled(tmp_path, listed)
    run = _listing(*lists["TIMERS"])
    st = sp_deploy.active_timers_state(enabled_path=path, runner=run)
    assert st == {"active_not_listed": ["sp-exports-squash.timer", "sp-intl-daily.timer"]} and len(run.calls) == 1
    line = sp_deploy.active_timers_line(st)
    assert line.startswith(f"\n  ! active sp timers not in {c.TIMERS_ENABLED}: sp-exports-squash.timer, "
                           "sp-intl-daily.timer — add them to the list by hand")
    assert path.read_text() == " ".join(listed) + "\n"           # read-only: the list is never written
    # an active sp timer whose name no T11 list could carry is still named, never dropped (addendum 57 item 8)
    odd = sp_deploy.active_timers_state(enabled_path=path, runner=_listing(*listed, "sp-notify@x.timer"))
    assert odd["active_not_listed"] == ["sp-notify@x.timer"]


def test_every_active_timer_listed_leaves_the_deploy_receipt_as_it_was(tmp_path):
    lists = c.t11_lists()
    path = _enabled(tmp_path, lists["TIMERS"])
    st = sp_deploy.active_timers_state(enabled_path=path, runner=_listing(*lists["TIMERS"][:3], "other.timer"))
    assert st == {"active_not_listed": []} and sp_deploy.active_timers_line(st) == ""
    shipped = sp_deploy.timers_line(sp_deploy.timers_state(enabled_path=path))
    assert shipped + sp_deploy.active_timers_line(st) == shipped   # the addendum 155 line, unchanged and alone


def test_an_unreadable_active_listing_is_labelled_never_read_as_empty(tmp_path):
    """Law 4: a listing that fails (no bus, no systemctl) is an error with no list, and the line says so with "!";
    an unreadable timers.enabled is labelled the same way, and systemctl is not asked."""
    path = _enabled(tmp_path, c.t11_lists()["TIMERS"])
    st = sp_deploy.active_timers_state(enabled_path=path, runner=_listing(rc=1))
    assert st["active_not_listed"] is None and st["error"].startswith("systemctl list-units exit 1: Failed to connect")
    line = sp_deploy.active_timers_line(st)
    assert line.startswith("\n  ! active timers: systemctl list-units exit 1") and "could not be compared" in line
    missing_run = _listing("sp-a.timer")
    gone = sp_deploy.active_timers_state(enabled_path=tmp_path / "absent", runner=missing_run)
    assert gone["active_not_listed"] is None and "unreadable (FileNotFoundError)" in gone["error"]
    assert sp_deploy.active_timers_line(gone).startswith("\n  ! active timers: ") and missing_run.calls == []
    # a systemctl that cannot run at all is exit 127, labelled
    rc, out = sp_deploy._systemctl_read(["/nonexistent/systemctl-for-this-test"])
    assert rc == 127 and "FileNotFoundError" in out


def test_every_by_hand_timer_enable_recipe_adds_the_timer_to_timers_enabled():
    """ARCHITECT 2026-10-26, addendum 168 item 2: "T11's recipe for enabling a timer ends with the timers.enabled
    line". Every `enable --now sp-….timer` a runbook gives by hand is followed, in its recipe, by
    `echo <it> | sudo tee -a /etc/sports-predictor/timers.enabled` (T11's own `enable --now $TIMERS` writes the
    whole list first)."""
    missing = []
    for doc in ("hosting-h1.md", "h2-cutover-runbook.md", "exports-mirror.md"):
        lines = (ROOT / "docs" / "specs" / doc).read_text(encoding="utf-8").splitlines()
        for i, ln in enumerate(lines):
            for t in re.findall(r"enable --now (sp-[\w@.-]+\.timer)", ln):
                recipe = "\n".join(lines[i:i + 3])
                if f"echo {t} | sudo tee -a /etc/sports-predictor/timers.enabled" not in recipe:
                    missing.append(f"{doc}:{i + 1} {t}")
    assert not missing, f"a by-hand timer enable with no timers.enabled line: {missing}"


# ------------------------------------------- H1a fresh bootstrap (09-27) ----

import bootstrap  # noqa: E402


def _fp_db(path, rows, teams=()):
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE competitions(id INTEGER PRIMARY KEY, sport TEXT, code TEXT);
        CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, season TEXT, status TEXT);
        CREATE TABLE competition_teams(competition_id INT, team_id INT, season TEXT);
        CREATE TABLE odds_snapshots(id INTEGER PRIMARY KEY, source TEXT);""")
    ids = {}
    for sport, comp, season, status, n in rows:
        cid = ids.setdefault(comp, len(ids) + 1)
        con.execute("INSERT OR IGNORE INTO competitions VALUES (?,?,?)", (cid, sport, comp))
        con.executemany("INSERT INTO matches(competition_id, season, status) VALUES (?,?,?)",
                        [(cid, season, status)] * n)
    for comp, season, n in teams:
        con.executemany("INSERT INTO competition_teams VALUES (?,?,?)",
                        [(ids[comp], t, season) for t in range(n)])
    con.commit()
    con.close()
    return path


NHL_CERT = [("NHL", "NHL", "2024", "FINISHED", 1502), ("NHL", "NHL", "2024", "CANCELLED", 1),
            ("NHL", "NHL", "2025", "FINISHED", 1498), ("NHL", "NHL", "2026", "SCHEDULED", 1409),
            ("SOCCER", "PL", "2025/26", "FINISHED", 380), ("SOCCER", "PL", "2026/27", "SCHEDULED", 300),
            ("SOCCER", "PL", "2026/27", "FINISHED", 80), ("NFL", "NFL", "2025", "FINISHED", 285),
            ("NFL", "NFL", "2026", "SCHEDULED", 704), ("MLB", "MLB", "2025", "FINISHED", 2430),
            ("MLB", "MLB", "2026", "SCHEDULED", 10)]


def test_bootstrap_plan_is_cli_valid_and_ordered(tmp_path):
    ref = bootstrap.fingerprint(_fp_db(tmp_path / "l.db", NHL_CERT, [("NHL", "2025", 32)]))
    steps = bootstrap.plan(ref)
    cli = _cli()
    assert steps[1] == [bootstrap.SEED]  # model registry seeded right after init-db
    for st in steps:
        if st == [bootstrap.SEED]:
            continue
        cmd = cli.commands[st[0]]
        opts = {o for p in cmd.params for o in (*p.opts, *p.secondary_opts)}
        assert all(t in opts for t in st[1:] if t.startswith("--")), st
    flat = [" ".join(s) for s in steps]
    assert flat[0] == "init-db"
    assert flat[2:6] == ["sync-competitions --sport mlb", "sync-competitions --sport nfl",
                         "sync-competitions --sport nhl", "sync-competitions --sport soccer"]
    i_teams = flat.index("sync-teams --competition NHL --season 2024")
    assert flat[i_teams + 1] == "sync-matches --competition NHL --season 2024"
    assert "sync-odds --competition PL --season 2026/27" in flat  # stored season string
    assert "sync-odds-football" in flat and "sync-kalshi-ncaa" in flat
    assert not any(s.startswith("sync-odds --competition NFL") for s in flat)


def test_bootstrap_compare_completed_exact_and_anchors(tmp_path):
    lap = bootstrap.fingerprint(_fp_db(tmp_path / "l.db", NHL_CERT, [("NHL", "2025", 32)]))
    same = bootstrap.fingerprint(_fp_db(tmp_path / "h.db", NHL_CERT, [("NHL", "2025", 32)]))
    ok, lines = bootstrap.compare(lap, same)
    fails = [x for x in lines if x.startswith("✗")]
    # only the families this synthetic pot lacks fail (NCAA/NFL-total/soccer pot
    # floors), plus the model check: this synthetic DB has no model registry
    assert not ok and all(("ANCHOR" in x and ("NCAA" in x or "NFL" in x or "Soccer" in x))
                          or "MODEL laptop reference carries no production" in x for x in fails)
    assert any(x.startswith("✓ ANCHOR NHL 2024 FINISHED") for x in lines)
    drift = [r if r[:4] != ("NHL", "NHL", "2025", "FINISHED") else ("NHL", "NHL", "2025", "FINISHED", 1497)
             for r in NHL_CERT]
    host = bootstrap.fingerprint(_fp_db(tmp_path / "d.db", drift, [("NHL", "2025", 32)]))
    _, lines = bootstrap.compare(lap, host)
    assert any(x.startswith("✗ NHL   2025") for x in lines)
    assert any(x.startswith("✗ ANCHOR NHL 2025 FINISHED") for x in lines)
    # the current season is informational only
    assert any("NHL   2026" in x and x.startswith("·") for x in lines)


def test_bootstrap_run_refuses_existing_db(sandbox):
    ref = sandbox / "ref.json"
    ref.write_text(json.dumps({"games": [{"sport": "NHL", "comp": "NHL", "season": "2025",
                                          "status": "FINISHED", "n": 1}]}))
    with pytest.raises(SystemExit, match="FRESH host"):
        bootstrap.main(["run", "--reference", str(ref)])


def _real_schema_db(path, models):
    from sqlalchemy import create_engine
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    eng.dispose()
    con = sqlite3.connect(path)
    for sport, fam, ver, status, params in models:
        con.execute("INSERT INTO model_versions(sport, model_family, version, status, parameters, "
                    "train_size, created_at) VALUES (?,?,?,?,?,?,?)",
                    (sport, fam, ver, status, json.dumps(params), 100, "2026-09-21 09:00:00.000000"))
    con.commit()
    con.close()
    return path


MODELS = [("MLB", "mlb_pythag_negbin", "v2", "production", {"k": 1, "manual_config_edits": [{"f": "x"}]}),
          ("MLB", "mlb_pythag_negbin", "v7", "rejected", {"k": 2}),
          ("SOCCER", "soccer_elo_poisson", "v22", "production", {"rho": -0.10, "k": 20})]


def test_model_registry_seed_roundtrip_and_identity(tmp_path):
    lap = bootstrap.fingerprint(_real_schema_db(tmp_path / "lap.db", MODELS))
    reg = lap["model_registry"]
    assert [(r["sport"], r["version"]) for r in reg] == [("MLB", "v2"), ("SOCCER", "v22")]  # production only
    host = _real_schema_db(tmp_path / "host.db", [])
    out = bootstrap.seed_models(host, reg)
    assert out["seeded"] == ["MLB/mlb_pythag_negbin/v2", "SOCCER/soccer_elo_poisson/v22"]
    con = sqlite3.connect(host)
    assert con.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0] == 0  # books stay empty
    assert con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM prediction_outcomes").fetchone()[0] == 0
    con.close()
    with pytest.raises(SystemExit, match="already has"):
        bootstrap.seed_models(host, reg)  # a seed, never a merge
    _, lines = bootstrap.compare(lap, bootstrap.fingerprint(host))
    assert any(x.startswith("✓ MODEL MLB/mlb_pythag_negbin") for x in lines)
    assert any(x.startswith("✓ MODEL SOCCER/soccer_elo_poisson") for x in lines)
    # a parameters drift is a model-identity FAIL
    drift = _real_schema_db(tmp_path / "drift.db", [MODELS[0], MODELS[2][:4] + ({"rho": -0.12, "k": 20},)])
    ok, lines = bootstrap.compare(lap, bootstrap.fingerprint(drift))
    assert not ok and any(x.startswith("✗ MODEL SOCCER/soccer_elo_poisson") for x in lines)


def test_seed_refuses_empty_registry(tmp_path):
    with pytest.raises(SystemExit, match="no production model rows"):
        bootstrap.seed_models(_real_schema_db(tmp_path / "h.db", []), [])


# --------------------------- --skip-family (statsapi 406 on DO ASN, 09-27) ----

def test_skip_family_run_keeps_numbering_and_receipts(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    ref = {"games": [
        {"sport": "MLB", "comp": "MLB", "season": "2025", "status": "FINISHED", "n": 2430},
        {"sport": "MLB", "comp": "MLB", "season": "2026", "status": "SCHEDULED", "n": 10},
        {"sport": "NHL", "comp": "NHL", "season": "2025", "status": "FINISHED", "n": 1498}],
        "model_registry": []}
    rp = sandbox / "ref.json"
    rp.write_text(json.dumps(ref))
    steps = bootstrap.plan(ref)
    flat = [" ".join(s) for s in steps]
    i8 = flat.index("sync-matches --competition MLB --season 2025") + 1
    # resume past init/seed exactly like the host: --from N with the flag
    assert bootstrap.main(["run", "--reference", str(rp), "--from", "3",
                           "--skip-family", "mlb"]) == 0
    rs = [r for r in receipts(sandbox) if r["kind"] == "step"]
    by_step = {r["step"]: r for r in rs}
    assert by_step[i8]["skipped"] == "SKIPPED-ASN" and by_step[i8]["exit"] is None
    mlb_sync = [r for r in rs if r["command"].split()[2] in ("sync-teams", "sync-matches")
                and "MLB" in r["command"]]
    assert len(mlb_sync) == 4 and all(r["skipped"] == "SKIPPED-ASN" for r in mlb_sync)
    nhl = [r for r in rs if "--competition NHL" in r["command"] and "sync-matches" in r["command"]]
    assert nhl and nhl[0]["exit"] == 0
    # market + Kalshi steps still run (commercial / public providers)
    assert any("sync-odds --competition MLB" in r["command"] and r["exit"] == 0 for r in rs)
    assert any(r["command"].endswith("sync-kalshi") and r["exit"] == 0 for r in rs)
    assert sorted(by_step) == list(range(3, len(steps) + 1))  # numbering unchanged
    chain = receipts(sandbox)[-1]
    assert chain["steps_skipped"] == 4 and chain["skipped_families"] == ["MLB"]


def test_compare_skipped_family_is_na_host_not_failure(tmp_path):
    lap = bootstrap.fingerprint(_fp_db(tmp_path / "l.db", NHL_CERT, [("NHL", "2025", 32)]))
    no_mlb = [r for r in NHL_CERT if r[0] != "MLB"]
    host = bootstrap.fingerprint(_fp_db(tmp_path / "h.db", no_mlb, [("NHL", "2025", 32)]))
    _, plain = bootstrap.compare(lap, host)
    assert any(x.startswith("✗ MLB   2025") for x in plain)  # without the flag: a failure
    _, lines = bootstrap.compare(lap, host, {"MLB"})
    assert not any(x.startswith("✗ MLB") for x in lines)
    assert any(x.startswith("· MLB   2025") and "N/A-host (SKIPPED-ASN" in x for x in lines)
    assert any(x.startswith("✓ NHL   2025") for x in lines)  # other families still exact


# ------------------------------- compare --waive (architect ruling 09-27) ----

def test_waive_prints_row_records_receipt_and_never_hides(sandbox, tmp_path):
    rows = [("SOCCER", "UEL", "2024/25", "FINISHED", 269), ("SOCCER", "UEL", "2026/27", "SCHEDULED", 9),
            ("SOCCER", "PL", "2025/26", "FINISHED", 380), ("SOCCER", "PL", "2026/27", "SCHEDULED", 9)]
    host_rows = [("SOCCER", "UEL", "2024/25", "FINISHED", 202)] + rows[1:]
    lp, hp = tmp_path / "l.json", tmp_path / "h.json"
    lp.write_text(json.dumps(bootstrap.fingerprint(_fp_db(tmp_path / "l.db", rows))))
    hp.write_text(json.dumps(bootstrap.fingerprint(_fp_db(tmp_path / "h.db", host_rows))))
    lap, host = json.loads(lp.read_text()), json.loads(hp.read_text())
    _, plain = bootstrap.compare(lap, host)
    assert any(x.startswith("✗ UEL   2024/25") for x in plain)
    w = dict([bootstrap.parse_waiver("UEL:2024/25:provider serves 202 after one host re-sync"),
              bootstrap.parse_waiver("PL:2025/26:not needed")])
    _, lines = bootstrap.compare(lap, host, waivers=w)
    row = [x for x in lines if "UEL   2024/25" in x][0]
    assert row.startswith("~ ") and "laptop    269 | host    202" in row and "WAIVED: provider serves 202" in row
    assert any(x.startswith("· waiver unused PL:2025/26") for x in lines)
    assert not any(x.startswith("✗ UEL") for x in lines)
    with pytest.raises(SystemExit, match="COMP:SEASON:reason"):
        bootstrap.parse_waiver("UEL:2024/25")
    bootstrap.main(["compare", str(lp), str(hp), "--waive", "UEL:2024/25:provider difference"])
    rec = receipts(sandbox)[-1]
    assert rec["waivers"] == [{"comp": "UEL", "season": "2024/25",
                               "reason": "provider difference", "applied": True}]


def test_monday_refresh_syncs_el1_el2_first():
    steps = chains.CHAINS["soccer-refresh"]["steps"]
    assert steps[0] == ["sync-matches", "--competition", "EL1", "--season", "2026/27"]
    assert steps[1] == ["sync-matches", "--competition", "EL2", "--season", "2026/27"]
    assert steps[-1] == ["soccer-refresh"]


# ------------------- fingerprint version guard (architect finding 09-27) ----

def test_fingerprint_stamps_bootstrap_blob_sha_equal_to_git(tmp_path):
    import subprocess
    fp = bootstrap.fingerprint(_fp_db(tmp_path / "x.db", NHL_CERT))
    want = subprocess.run(["git", "hash-object", str(HOSTING / "bootstrap.py")],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert fp["producer"]["bootstrap_blob_sha"] == want


def test_compare_refuses_version_skew_and_unstamped(sandbox, tmp_path):
    base = bootstrap.fingerprint(_fp_db(tmp_path / "l.db", NHL_CERT))
    skew = json.loads(json.dumps(base))
    skew["producer"]["bootstrap_blob_sha"] = "0" * 40
    old = {k: v for k, v in base.items() if k != "producer"}  # a pre-guard fingerprint
    for lap, host, msg in ((base, skew, "different bootstrap.py versions"),
                           (old, base, "laptop fingerprint carries no bootstrap version stamp")):
        lp, hp = tmp_path / "a.json", tmp_path / "b.json"
        lp.write_text(json.dumps(lap))
        hp.write_text(json.dumps(host))
        assert bootstrap.main(["compare", str(lp), str(hp)]) == 2
        rec = receipts(sandbox)[-1]
        assert rec["refused"] == "version_mismatch" and "games" not in json.dumps(rec)
    assert bootstrap.version_mismatch(base, json.loads(json.dumps(base))) is None
    assert "no bootstrap version stamp" in bootstrap.version_mismatch(old, base)
    assert "different bootstrap.py versions" in bootstrap.version_mismatch(base, skew)


# -------------------- fingerprint receipts: explain / self-check (09-27) ----

def _uel_db(path):
    db = _real_schema_db(path, [])
    con = sqlite3.connect(db)
    con.execute("INSERT INTO competitions(id, sport, code, name, area, type, external_ids) "
                "VALUES (5, 'SOCCER', 'UEL', 'UEFA Europa League', 'Europe', 'INTL', '{}')")
    con.execute("INSERT INTO teams(id, sport, name, external_ids) VALUES (1,'SOCCER','A','{}'),"
                "(2,'SOCCER','B','{}')")
    rows = ([("2024/25", "FINISHED", "FT", "League Stage")] * 3
            + [("2024/25", "FINISHED", "AET", "Knockout Round Play-offs")]
            + [("2024", "FINISHED", "FT", "League Stage")] * 2)  # off-format season string
    for i, (season, st, raw, stage) in enumerate(rows, 1):
        con.execute("INSERT INTO matches(sport, competition_id, season, utc_date, status, status_raw, "
                    "stage, home_team_id, away_team_id, external_ids) VALUES "
                    "('SOCCER', 5, ?, '2025-01-01', ?, ?, ?, 1, 2, ?)",
                    (season, st, raw, stage, json.dumps({"api_football": str(1000 + i)})))
    # an orphan competition_id: counted as '?#99', never dropped
    con.execute("INSERT INTO matches(sport, competition_id, season, utc_date, status, home_team_id, "
                "away_team_id, external_ids) VALUES ('SOCCER', 99, '2024/25', '2025-01-01', "
                "'FINISHED', 1, 2, '{}')")
    con.commit()
    con.close()
    return db


def test_fingerprint_counts_every_row_and_self_checks(tmp_path):
    fp = bootstrap.fingerprint(_uel_db(tmp_path / "u.db"))
    assert fp["raw_match_total"] == 7 == sum(g["n"] for g in fp["games"])
    got = {(g["comp"], g["season"]): g["n"] for g in fp["games"]}
    assert got[("UEL", "2024/25")] == 4 and got[("UEL", "2024")] == 2 and got[("?#99", "2024/25")] == 1


def test_compare_index_sums_duplicate_status_entries():
    fp = {"games": [{"sport": "SOCCER", "comp": "UEL", "season": "2024/25", "status": "FINISHED", "n": 202},
                    {"sport": "OTHER", "comp": "UEL", "season": "2024/25", "status": "FINISHED", "n": 67},
                    {"sport": "SOCCER", "comp": "UEL", "season": "2026/27", "status": "SCHEDULED", "n": 1}],
          "family_teams": {}, "model_registry": [{"sport": "S", "model_family": "f", "version": "v",
                                                  "_params_sha256": "h"}]}
    lap = json.loads(json.dumps(fp))
    lap["games"] = [{"sport": "SOCCER", "comp": "UEL", "season": "2024/25", "status": "FINISHED", "n": 269},
                    lap["games"][2]]
    _, lines = bootstrap.compare(lap, fp)
    row = [x for x in lines if "UEL   2024/25" in x][0]
    assert row.startswith("✓") and "laptop    269 | host    269" in row  # 202 + 67 summed, not overwritten


def test_explain_prints_predicate_and_flags_uncounted_rows(sandbox, tmp_path, capsys):
    import sp_common
    lap = _uel_db(tmp_path / "lap.db")
    out_l = tmp_path / "ex_l.json"
    sandbox_db = sp_common.db_path
    sp_common.db_path = lambda: lap
    try:
        assert bootstrap.main(["explain", "--comp", "UEL", "--season", "2024/25",
                               "--out", str(out_l)]) == 0
    finally:
        sp_common.db_path = sandbox_db
    text = capsys.readouterr().out
    assert bootstrap.FINGERPRINT_SQL in text
    assert "fingerprint 4  raw(season exact) 4  raw by season string {'2024': 2, '2024/25': 4}" in text
    assert "(b) rows NOT counted by the fingerprint for UEL 2024/25: 2" in text
    e = json.loads(out_l.read_text())
    assert e["by_status_raw"] == {"AET": 1, "FT": 3} and "status_raw" in e["fields_present"]
    # (c): a host whose rows carry a different stored attribute
    host = json.loads(out_l.read_text())
    host["rows"][0]["status_raw"] = "FT_SYNCED_TODAY"
    host["rows"] = host["rows"][:-1]
    lines = bootstrap.explain_diff(e, host)
    assert any("differs" in x and "status_raw: 'FT' -> 'FT_SYNCED_TODAY'" in x for x in lines)
    assert any(x.strip().startswith("laptop-only:") for x in lines)


# ------------------------- Next-24h WINDOW SERVICE (spec 2026-09-27) ----

import sp_window_page  # noqa: E402


def _window_db(path, now):
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE competitions(id INTEGER PRIMARY KEY, sport TEXT, code TEXT);
        CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, season TEXT, status TEXT,
                             utc_date TEXT);""")
    con.executemany("INSERT INTO competitions VALUES (?,?,?)",
                    [(1, "SOCCER", "PL"), (2, "NFL", "NFL"), (3, "NFL", "NCAA"),
                     (4, "MLB", "MLB"), (5, "SOCCER", "CL")])
    fmt = "%Y-%m-%d %H:%M:%S"
    rows = [(1, "2026/27", "SCHEDULED", 3), (1, "2026/27", "SCHEDULED", 5),
            (2, "2026", "SCHEDULED", 20), (3, "2026", "SCHEDULED", 22),
            (4, "2026", "SCHEDULED", 2), (5, "2026/27", "SCHEDULED", 30),   # CL outside 24h
            (1, "2026/27", "FINISHED", 1)]                                 # finished: ignored
    con.executemany("INSERT INTO matches(competition_id, season, status, utc_date) VALUES (?,?,?,?)",
                    [(cid, s, st, (now + timedelta(hours=h)).strftime(fmt)) for cid, s, st, h in rows])
    con.commit()
    con.close()


def test_window_plan_is_scoped_single_day_and_model_free(sandbox, monkeypatch):
    now = datetime(2026, 10, 3, 20, 0)
    _window_db(sandbox / "w.db", now)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{sandbox / 'w.db'}")
    steps = [" ".join(s) for s in sp_run.window_steps(now)]
    # one single-day sync per UTC date the window touches (adapter law)
    assert "sync-matches --competition PL --season 2026/27 --date-from 2026-10-03 --date-to 2026-10-03" in steps
    assert "sync-matches --competition PL --season 2026/27 --date-from 2026-10-04 --date-to 2026-10-04" in steps
    assert not any(s.startswith("sync-matches --competition CL") for s in steps)  # outside window
    assert "sync-odds --competition PL --season 2026/27 --limit 2" in steps       # games <= 6h
    assert "sync-odds --competition MLB --season 2026 --limit 1" in steps
    # PROXIMITY: NFL (+20h) and NCAA (+22h) are FAR -> schedule check only
    assert "sync-matches --competition NFL --season 2026 --date-from 2026-10-04 --date-to 2026-10-04" in steps
    assert "sync-odds-football" not in steps
    assert not any(s.startswith(("sync-kalshi-nfl", "sync-kalshi-ncaa")) for s in steps)
    assert {"sync-kalshi-soccer --competition PL",
            "sync-kalshi --date-from {today} --date-to {tomorrow}"} <= set(steps)
    plan = sp_run.window_plan(now)
    assert plan["tiers"] == {"far": ["NFL", "NCAA"], "near": ["MLB", "PL"], "imminent": []}
    # flat plan would add sync-odds-football + two Kalshi syncs + the two
    # model-family injury syncs (NFL, PL) the imminent tier carries (2026-09-29)
    assert plan["skipped_by_proximity"] == 5
    assert not any(s.startswith("sync-injuries") for s in steps)       # nothing imminent here
    assert steps[-1] == "window-card --hours 24"
    assert not any(s.split()[0] in ("predict", "predict-nfl", "improve", "soccer-refresh")
                   for s in steps)
    # every planned command/option exists in cli.py (law 1)
    cli = _cli()
    for s in steps:
        st = s.split()
        opts = {o for p in cli.commands[st[0]].params for o in (*p.opts, *p.secondary_opts)}
        assert all(tok in opts for tok in st[1:] if tok.startswith("--")), s
    # the DO host: MLB sync-matches dropped (ASN), MLB odds/Kalshi untouched
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    steps = [" ".join(s) for s in sp_run.window_steps(now)]
    assert not any(s.startswith("sync-matches --competition MLB") for s in steps)
    assert "sync-odds --competition MLB --season 2026 --limit 1" in steps


def test_window_kalshi_table_pinned_to_adapter_series():
    from src.adapters.kalshi import KalshiAdapter
    soccer = {code for code, steps in chains.WINDOW_KALSHI.items()
              if steps and steps[0][0] == "sync-kalshi-soccer"}
    capture = set(chains.KALSHI_CAPTURE_ONLY)       # ARCHITECT 2026-10-07: pinned, capture only, never live
    assert not soccer & capture
    assert soccer | capture == set(KalshiAdapter.SOCCER_GAME_SERIES) | set(KalshiAdapter.SOCCER_SERIES_DISCOVERY)
    cli = _cli()
    for steps in chains.WINDOW_KALSHI.values():
        for st in steps:
            assert st[0] in cli.commands


def test_window_capture_only_table_is_the_expansion_leagues_one_series_per_step():
    """CAPTURE QUALITY (ARCHITECT 2026-10-24, addendum 164 item 2(a)): "the four series plus KXLALIGAGAME join the
    host's hourly window chain's Kalshi capture [...] a capture-only step, no export, no call; [...] one series per
    call". The table is KALSHI_CAPTURE_ONLY, one sync-kalshi-soccer step per code, each code mapped in the adapter (no
    --series flag); WINDOW_KALSHI still excludes them (the card's venue lines are unchanged)."""
    from src.adapters.kalshi import KalshiAdapter
    assert chains.WINDOW_KALSHI_CAPTURE_ONLY == {c: [["sync-kalshi-soccer", "--competition", c]]
                                                 for c in chains.KALSHI_CAPTURE_ONLY}
    assert set(chains.KALSHI_CAPTURE_ONLY) == {"PD", "SA", "BL1", "FL1", "ELC"}
    assert {KalshiAdapter.SOCCER_GAME_SERIES[c] for c in chains.WINDOW_KALSHI_CAPTURE_ONLY} == {
        "KXLALIGAGAME", "KXSERIEAGAME", "KXBUNDESLIGAGAME", "KXLIGUE1GAME", "KXEFLCHAMPIONSHIPGAME"}
    assert not set(chains.WINDOW_KALSHI_CAPTURE_ONLY) & set(chains.WINDOW_KALSHI)
    assert not any("--series" in st for sts in chains.WINDOW_KALSHI_CAPTURE_ONLY.values() for st in sts)
    cli = _cli()
    opts = {o for p in cli.commands["sync-kalshi-soccer"].params for o in (*p.opts, *p.secondary_opts)}
    for sts in chains.WINDOW_KALSHI_CAPTURE_ONLY.values():
        assert len(sts) == 1                                            # one series per call
        assert all(tok in opts for tok in sts[0][1:] if tok.startswith("--")), sts
    assert "sync-kalshi-soccer" in chains.UNMETERED
    # nothing on the card's path reads the table: window-card reads the DB, never chains.py
    import src.walters.window as window
    for src in (inspect.getsource(window), inspect.getsource(cli.commands["window-card"].callback)):
        assert "WINDOW_KALSHI_CAPTURE_ONLY" not in src and "KALSHI_CAPTURE_ONLY" not in src
    # the pager reads it for one thing only (addendum 165 item 1): the leagues whose line moves it never pages
    import sp_window_page
    pager = (HOSTING / "sp_window_page.py").read_text()
    assert "CAPTURE_ONLY = frozenset(WINDOW_KALSHI_CAPTURE_ONLY) - frozenset(WINDOW_KALSHI)" in pager
    for fn in (sp_window_page.run, sp_window_page.deltas, sp_window_page.snapshot, sp_window_page.line):
        assert "WINDOW_KALSHI_CAPTURE_ONLY" not in inspect.getsource(fn)   # read once, as CAPTURE_ONLY


def test_window_plan_captures_the_expansion_leagues_near_and_imminent_only(sandbox, monkeypatch):
    """Addendum 164 item 2(a): the capture-only steps are tiered as the window's Kalshi syncs are: a league with its
    next kickoff near (SA, +3h) or imminent (FL1, +1h) gets its step, a far league (BL1, +10h) only its schedule check,
    a league with no game in the window (PD, +30h; ELC finished) nothing. Every other step of the plan, the card's
    included, is the plan without the table; a window with no expansion game adds none."""
    now = datetime(2026, 10, 3, 20, 0)
    _window_db(sandbox / "w.db", now)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{sandbox / 'w.db'}")
    base = sp_run.window_plan(now)
    assert not any(s[0] == "sync-kalshi-soccer" and s[2] in chains.KALSHI_CAPTURE_ONLY for s in base["steps"])
    con = sqlite3.connect(sandbox / "w.db")
    con.executemany("INSERT INTO competitions VALUES (?,?,?)",
                    [(6, "SOCCER", "SA"), (7, "SOCCER", "FL1"), (8, "SOCCER", "BL1"), (9, "SOCCER", "PD"),
                     (10, "SOCCER", "ELC")])
    fmt = "%Y-%m-%d %H:%M:%S"
    con.executemany("INSERT INTO matches(competition_id, season, status, utc_date) VALUES (?,?,?,?)",
                    [(cid, "2026/27", st, (now + timedelta(hours=h)).strftime(fmt))
                     for cid, st, h in ((6, "SCHEDULED", 3), (7, "SCHEDULED", 1), (8, "SCHEDULED", 10),
                                        (9, "SCHEDULED", 30), (10, "FINISHED", 1))])
    con.commit()
    con.close()
    plan = sp_run.window_plan(now)
    steps = [" ".join(s) for s in plan["steps"]]
    assert "sync-kalshi-soccer --competition SA" in steps                   # near
    assert "sync-kalshi-soccer --competition FL1" in steps                  # imminent
    assert not any(s.startswith(("sync-kalshi-soccer --competition BL1",    # far: schedule only
                                 "sync-kalshi-soccer --competition PD",     # outside the window
                                 "sync-kalshi-soccer --competition ELC")) for s in steps)   # finished only
    assert steps.count("sync-kalshi-soccer --competition SA") == 1
    assert plan["tiers"]["near"] == ["MLB", "PL", "SA"] and plan["tiers"]["imminent"] == ["FL1"]
    assert "BL1" in plan["tiers"]["far"]
    # the capture steps sit with the Kalshi syncs, before the card; the card step is unchanged
    assert steps[-1] == "window-card --hours 24" == " ".join(base["steps"][-1])
    assert max(steps.index("sync-kalshi-soccer --competition SA"),
               steps.index("sync-kalshi-soccer --competition FL1")) < steps.index("window-card --hours 24")
    # only the table differs: without it the plan is the same plan less the capture steps
    monkeypatch.setattr(sp_run, "WINDOW_KALSHI_CAPTURE_ONLY", {})
    without = sp_run.window_plan(now)
    cap = {("sync-kalshi-soccer", "--competition", "SA"), ("sync-kalshi-soccer", "--competition", "FL1")}
    assert [s for s in plan["steps"] if tuple(s) not in cap] == without["steps"]
    # the flat plan carries BL1's capture too: proximity skips it, and the receipt counts it
    assert plan["skipped_by_proximity"] == without["skipped_by_proximity"] + 1
    # every planned command and option exists in cli.py (law 1)
    cli = _cli()
    for st in plan["steps"]:
        opts = {o for p in cli.commands[st[0]].params for o in (*p.opts, *p.secondary_opts)}
        assert all(tok in opts for tok in st[1:] if tok.startswith("--")), st
    # no export / predict / call step names an expansion league in the window plan
    for st in plan["steps"]:
        if any(c in st for c in chains.KALSHI_CAPTURE_ONLY):
            assert st[0] in ("sync-matches", "sync-odds", "sync-kalshi-soccer"), st


def test_window_mlb_kalshi_step_ends_at_tomorrow_plus_one_day(sandbox, monkeypatch):
    """#175 (ARCHITECT 2026-10-17 10:40 ET, addendum 112 item 8), RULED: "the step's window ends at {tomorrow}+1 day".
    The window chain as sp_run resolves it for a run on UTC day D: the MLB Kalshi step is the only step the date
    placeholders touch, and its `--date-to {tomorrow}` is the whole UTC day (cli.py, since #205). So the step's
    window is our kickoffs from D 00:00Z up to D+2 00:00Z: it ends at {tomorrow}+1 day, and it holds the 24 hours
    of every window run on D."""
    from click.testing import CliRunner
    from src.ingestion import kalshi_sync
    now = datetime(2026, 10, 3, 20, 0)
    _window_db(sandbox / "w.db", now)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{sandbox / 'w.db'}")
    planned = sp_run.window_steps(now)
    resolved = sp_run.resolve("window", {}, now.date(), now=now)
    kalshi = [st for st in resolved if st[0] == "sync-kalshi"]
    assert kalshi == [["sync-kalshi", "--date-from", "2026-10-03", "--date-to", "2026-10-04"]]
    # every other step resolves to itself: the placeholders touch the MLB Kalshi step only
    assert [st for st in resolved if st[0] != "sync-kalshi"] == [st for st in planned if st[0] != "sync-kalshi"]
    v = sp_run.date_vars(now.date())
    assert all(a.format(**v) == a for k, sts in chains.WINDOW_KALSHI.items() if k != "MLB"
               for st in sts for a in st)                    # no other Kalshi step carries a date placeholder
    seen = {}

    def fake(date_from=None, date_to=None, progress=None, **kw):
        seen.update(lo=date_from, hi=date_to)
        return {"ok": False, "reason": "test"}
    monkeypatch.setattr(kalshi_sync, "sync_kalshi_mlb", fake)
    r = CliRunner().invoke(_cli(), kalshi[0])
    assert r.exit_code == 0, r.output
    assert seen["lo"] == datetime(2026, 10, 3)
    assert seen["hi"] == datetime(2026, 10, 5) - timedelta(microseconds=1)       # {tomorrow} + 1 day
    last_run = datetime.combine(now.date(), datetime.max.time())                  # the day's last window run
    assert last_run + timedelta(hours=chains.WINDOW_HOURS) <= seen["hi"]


def _card(games, t90=None):
    return {"fixtures": [dict({"match_id": i, "home_team": f"H{i}", "away_team": f"A{i}",
                               "sport": "nfl", "competition": "NFL",
                               "utc_date": "2026-10-04T17:00:00", "status": "scheduled",
                               "market": {"fair_prob": {"HOME": 0.6}}, "kalshi": None,
                               "tier": "lean", "quarantine": False, "venue_flag": None,
                               "edge_pp": 3.0, "engine": "model_edge"}, **g)
                         for i, g in games.items()],
            "t90_signatures": t90 or {}}


def _page(sandbox, monkeypatch, card, when):
    sent = []
    import sp_notify
    monkeypatch.setattr(sp_notify, "deliver",
                        lambda kind, title, body, extra=None, topic_var="NTFY_TOPIC",
                        priority="high": sent.append((topic_var, title, body, priority)) or True)
    p = sandbox / "card.json"
    p.write_text(json.dumps(card))
    return sp_window_page.run(p, now_utc=when), sent


def test_pager_baseline_then_deltas_quiet_hours_and_digest(sandbox, monkeypatch):
    monkeypatch.setenv("SP_WINDOW_STATE", str(sandbox / "ws.json"))
    day = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)          # 11:00 ET
    rec, sent = _page(sandbox, monkeypatch, _card({1: {}, 2: {"market": None}}), day)
    assert rec["first_run"] and sum(rec["deltas"].values()) == 0
    assert [s[1] for s in sent] == ["Next 24h digest 2026-10-04"]    # first run after 08:00 ET
    assert all(s[0] == "NTFY_CARD_TOPIC" for s in sent)
    # unchanged card: silent (no digest twice a day)
    rec, sent = _page(sandbox, monkeypatch, _card({1: {}, 2: {"market": None}}), day)
    assert sent == [] and sum(rec["deltas"].values()) == 0
    # every delta class
    card = _card({1: {"tier": "strong", "venue_flag": "STALE-BOOK?", "quarantine": True,
                      "utc_date": "2026-10-04T18:00:00"},
                  2: {}, 3: {}}, t90={"1": "sig-b"})
    rec, sent = _page(sandbox, monkeypatch, card, day)
    assert rec["deltas"] == {"new_priced": 2, "tier": 1, "quarantine": 1, "stale": 1,
                             "kickoff": 1, "t90_news": 0, "line_move": 0, "model": 0, "call": 0,
                             "qb_news": 0}
    assert len(sent) == 1 and sent[0][3] == "high" and "QUARANTINE ON" in sent[0][2]
    # quiet hours (02:00 ET): only the quarantine flip pages; the rest suppressed
    night = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)
    card = _card({1: {"tier": "lean", "quarantine": False, "utc_date": "2026-10-04T18:00:00",
                      "venue_flag": "STALE-BOOK?"}, 2: {}, 3: {}}, t90={"1": "sig-c"})
    rec, sent = _page(sandbox, monkeypatch, card, night)
    # tier change + T-90 news (sig-b -> sig-c) are suppressed; the flip is not
    assert rec["quiet_hours"] and rec["suppressed"] == 2 and rec["deltas"]["t90_news"] == 1
    assert len(sent) == 1 and "QUARANTINE off" in sent[0][2] and "tier" not in sent[0][2]
    # T-90 news: signature seen last run, changed now -> freshen needed (report + page)
    card["t90_signatures"] = {"1": "sig-d"}
    rec, sent = _page(sandbox, monkeypatch, card, day.replace(day=5))
    assert rec["freshen_needed"] == [{"id": "1", "sport": "nfl", "competition": "NFL",
                                    "reason": "t90_news"}]
    assert any("freshen triggered" in s[2] for s in sent)


def test_window_timer_avoids_reboot_hours_and_is_on_t11():
    t = (HOSTING / "systemd" / "sp-window.timer").read_text()
    assert "Unit=sp-chain@window.service" in t and "00..03,06..23:05:00 UTC" in t
    rb = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    enabled = rb[rb.index("TIMERS=\""):rb.index("MLB_LAPTOP_ONLY=")]
    assert "sp-window.timer" in enabled


# ------------------ freshen chains + proximity tiers (ruling 2026-09-27) ----

def test_freshen_chains_are_the_ruled_sequences():
    ch = chains.CHAINS
    assert [s[0] for s in ch["freshen:NFL"]["steps"]] == [
        "sync-injuries", "sync-odds-football", "sync-kalshi-nfl", "predict-nfl", "export-nfl-predictions"]
    assert ch["freshen:NFL"]["steps"][0] == ["sync-injuries", "--competition", "NFL", "--season", "2026"]
    assert ch["freshen:MLB"]["steps"] == ch["mlb-preslate"]["steps"] and len(ch["freshen:MLB"]["steps"]) == 10
    assert [s[0] for s in ch["freshen:SOCCER"]["steps"]] == [
        "sync-odds", "sync-injuries", "sync-kalshi-soccer", "predict", "export-predictions"]
    assert all("PL" in s for s in ch["freshen:SOCCER"]["steps"])
    # market-only families have no freshen: the window repricing IS their freshen
    assert set(chains.FRESHEN_FAMILY.values()) == {"NFL", "MLB", "SOCCER"}
    assert not any(comp in ("NCAA", "NHL", "CL", "UEL", "EFL", "UNL")
                   for _, comp in chains.FRESHEN_FAMILY)
    assert not any("freshen" in unit for _, unit in _timers().values())  # triggered, never timed


def test_imminent_tier(sandbox, monkeypatch):
    now = datetime(2026, 10, 3, 20, 0)
    _window_db(sandbox / "w.db", now)
    con = sqlite3.connect(sandbox / "w.db")
    con.execute("INSERT INTO matches(competition_id, season, status, utc_date) VALUES "
                "(2, '2026', 'SCHEDULED', ?)", ((now + timedelta(minutes=70)).strftime("%Y-%m-%d %H:%M:%S"),))
    con.commit()
    con.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{sandbox / 'w.db'}")
    plan = sp_run.window_plan(now)
    assert plan["tiers"]["imminent"] == ["NFL"]                 # next NFL kickoff in 70 min
    steps = [" ".join(s) for s in plan["steps"]]
    assert "sync-odds-football" in steps and "sync-kalshi-nfl" in steps


def test_run_freshens_family_map_skip_and_rate_guard(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    now = datetime(2026, 10, 4, 17, 0)
    needed = [{"id": "1", "sport": "nfl", "competition": "NFL"},
              {"id": "2", "sport": "nfl", "competition": "NCAA"},   # market-only: no family
              {"id": "3", "sport": "mlb", "competition": "MLB"}]    # host: logged, never run
    out = sp_run.run_freshens(needed, "win-1", now, now.date())
    by = {r["chain"]: r for r in out}
    assert set(by) == {"freshen:NFL", "freshen:MLB"}
    assert by["freshen:NFL"]["ran"] and by["freshen:NFL"]["exit"] == 0
    assert by["freshen:NFL"]["steps_ok"] == 5 and by["freshen:NFL"]["games"] == ["1"]
    assert not by["freshen:MLB"]["ran"] and "SP_SKIP_FAMILIES" in by["freshen:MLB"]["skipped"]
    steps = [r for r in receipts(sandbox) if r["kind"] == "step"]
    assert [s["command"].split()[2] for s in steps] == [
        "sync-injuries", "sync-odds-football", "sync-kalshi-nfl", "predict-nfl", "export-nfl-predictions"]
    # a second trigger inside the hour is rate-guarded
    again = sp_run.run_freshens(needed[:1], "win-2", now + timedelta(minutes=30), now.date())
    assert not again[0]["ran"] and again[0]["skipped"].startswith("rate-guard")
    later = sp_run.run_freshens(needed[:1], "win-3", now + timedelta(minutes=61), now.date())
    assert later[0]["ran"]


def test_window_run_triggers_freshen_and_recards(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    import sp_window_page
    plan = {"steps": [["window-card", "--hours", "24"]],
            "tiers": {"far": ["NCAA"], "near": [], "imminent": ["NFL"]}, "skipped_by_proximity": 2}
    monkeypatch.setattr(sp_run, "window_plan", lambda now: plan)
    monkeypatch.setattr(sp_window_page, "run", lambda p: {
        "deltas": {"t90_news": 1}, "paged": True, "digest": False, "suppressed": 0,
        "freshen_needed": [{"id": "9", "sport": "nfl", "competition": "NFL"}]})
    assert sp_run.main(["window"]) == 0
    rs = receipts(sandbox)
    fr = [r for r in rs if r["kind"] == "freshen"]
    assert len(fr) == 1 and fr[0]["chain"] == "freshen:NFL" and fr[0]["ran"]
    assert any(r["kind"] == "step" and r["run_id"].endswith("-recard") for r in rs)
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["freshens"][0]["chain"] == "freshen:NFL"
    assert chain["proximity"] == {"tiers": plan["tiers"], "steps_skipped_by_proximity": 2}


# ------------------------------- pull-exports lane (architect 2026-09-28) ----
# Laptop pulls host artifacts over the tailnet into exports/host/ (push is H2).
# A fake `ssh` on PATH runs the "remote" command locally, so REAL rsync makes
# a genuine round trip without a network; a fake `scp` covers the fallback.

import os  # noqa: E402
import shutil  # noqa: E402

import pull_exports  # noqa: E402

FAKE_SSH = """#!{py}
import subprocess, sys
a = sys.argv[1:]
while a and a[0].startswith("-"):
    a = a[2:] if a[0] in ("-o", "-p", "-l", "-i") else a[1:]
host, cmd = a[0], " ".join(a[1:])
{mode}
sys.exit(subprocess.run(["sh", "-c", cmd]).returncode)
"""
FAKE_SCP = """#!{py}
import os, shutil, sys
a = [x for x in sys.argv[1:] if not x.startswith("-")]
a = [x for x in a if x not in ("BatchMode=yes", "ConnectTimeout=15")]
*srcs, dst = a
for s in srcs:
    shutil.copy2(s.split(":", 1)[1], os.path.join(dst, os.path.basename(s)))
"""


def _fake_bin(tmp, monkeypatch, ssh_mode="", scp=False):
    b = tmp / "fakebin"
    b.mkdir(exist_ok=True)
    tools = {"ssh": FAKE_SSH.format(py=sys.executable, mode=ssh_mode)}
    if scp:
        tools["scp"] = FAKE_SCP.format(py=sys.executable)
    for name, body in tools.items():
        (b / name).write_text(body)
        (b / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}{os.pathsep}{os.environ['PATH']}")


def _host_exports(tmp):
    h = tmp / "host" / "exports"
    h.mkdir(parents=True)
    (h / "window_24h.json").write_text(json.dumps({"exported_at": "2026-10-08T14:05:00Z", "fixtures": []}))
    (h / "predictions_PL_2026-10-08.json").write_text('{"predictions": []}')
    (h / "bad name;rm -rf x.json").write_text("{}")          # unsafe name: skipped, never quoted into a shell
    for i, p in enumerate(sorted(h.iterdir())):
        os.utime(p, (1_790_000_000 + i, 1_790_000_000 + i))
    return h


def _laptop_exports():
    own = c.REPO / "exports"
    own.mkdir(parents=True, exist_ok=True)
    (own / "window_24h.json").write_text('{"exported_at": "LAPTOP-OWN"}')
    (own / "predictions_PL_2026-10-08.json").write_text('{"laptop": true}')
    return {p.name: (p.read_bytes(), p.stat().st_mtime) for p in own.iterdir() if p.is_file()}


def _args(h, *extra):
    return ["--host", "sp-vps-1", "--remote-dir", str(h), *extra]


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
def test_pull_exports_rsync_round_trip_idempotent_newest_wins(sandbox, monkeypatch):
    _fake_bin(sandbox, monkeypatch)
    h = _host_exports(sandbox)
    before = _laptop_exports()
    assert pull_exports.main(_args(h, "--transport", "rsync")) == 0
    got = c.REPO / "exports" / "host"
    assert sorted(p.name for p in got.iterdir()) == ["predictions_PL_2026-10-08.json", "window_24h.json"]
    assert (got / "window_24h.json").read_bytes() == (h / "window_24h.json").read_bytes()
    assert int((got / "window_24h.json").stat().st_mtime) == int((h / "window_24h.json").stat().st_mtime)
    r = receipts(sandbox)[-1]
    assert r["kind"] == "pull_exports" and r["exit"] == 0 and r["transport"] == "rsync"
    assert (r["pulled"], r["unchanged"]) == (2, 0) and r["window_24h"] == "2026-10-08T14:05:00Z"
    assert r["skipped_names"] == ["bad name;rm -rf x.json"]
    # idempotent: nothing new -> pulls 0
    assert pull_exports.main(_args(h)) == 0
    assert (receipts(sandbox)[-1]["pulled"], receipts(sandbox)[-1]["unchanged"]) == (0, 2)
    # newest wins: a newer host card is pulled; an OLDER host file never overwrites a newer local one
    (h / "window_24h.json").write_text(json.dumps({"exported_at": "2026-10-08T15:05:00Z"}))
    os.utime(h / "window_24h.json", (1_790_003_600, 1_790_003_600))
    os.utime(got / "predictions_PL_2026-10-08.json", (1_790_009_999, 1_790_009_999))
    assert pull_exports.main(_args(h)) == 0
    r = receipts(sandbox)[-1]
    assert (r["pulled"], r["unchanged"], r["kept_local_newer"]) == (1, 0, 1)
    assert r["window_24h"] == "2026-10-08T15:05:00Z"
    # isolation: the laptop's own exports/ are byte- and mtime-identical
    after = {p.name: (p.read_bytes(), p.stat().st_mtime) for p in (c.REPO / "exports").iterdir() if p.is_file()}
    assert after == before
    assert not (got / pull_exports.STAGING).exists()


def test_pull_exports_scp_fallback(sandbox, monkeypatch):
    _fake_bin(sandbox, monkeypatch, scp=True)
    h = _host_exports(sandbox)
    assert pull_exports.main(_args(h, "--transport", "scp")) == 0
    r = receipts(sandbox)[-1]
    assert r["transport"] == "scp" and r["pulled"] == 2
    assert (c.REPO / "exports" / "host" / "window_24h.json").read_bytes() == (h / "window_24h.json").read_bytes()


def test_pull_exports_unreachable_host_places_nothing(sandbox, monkeypatch, capsys):
    _fake_bin(sandbox, monkeypatch, ssh_mode=(
        'sys.stderr.write("ssh: connect to host sp-vps-1 port 22: Operation timed out\\n"); sys.exit(255)'))
    h = _host_exports(sandbox)
    before = _laptop_exports()
    got = c.REPO / "exports" / "host"
    got.mkdir()
    (got / "window_24h.json").write_text('{"exported_at": "PREVIOUS"}')
    assert pull_exports.main(_args(h)) == 1
    err = capsys.readouterr().err
    assert "host unreachable" in err and "Operation timed out" in err and "nothing placed" in err
    r = receipts(sandbox)[-1]
    assert r["exit"] == 1 and r["pulled"] == 0 and r["window_24h"] == "PREVIOUS"
    assert sorted(p.name for p in got.iterdir()) == ["window_24h.json"]   # no partial files
    assert {p.name: (p.read_bytes(), p.stat().st_mtime)
            for p in (c.REPO / "exports").iterdir() if p.is_file()} == before


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
def test_pull_exports_failed_transfer_is_all_or_nothing(sandbox, monkeypatch):
    # listing works, the transfer dies: nothing is placed, staging is gone
    _fake_bin(sandbox, monkeypatch, ssh_mode='if cmd.startswith("rsync"): sys.exit(12)')
    h = _host_exports(sandbox)
    assert pull_exports.main(_args(h, "--transport", "rsync")) == 1
    got = c.REPO / "exports" / "host"
    assert list(got.iterdir()) == []
    assert "rsync failed" in receipts(sandbox)[-1]["error"]


def test_pull_exports_isolation_and_config(sandbox, monkeypatch, capsys):
    monkeypatch.delenv("SP_HOST_ADDR", raising=False)
    assert pull_exports.main([]) == 2                                    # no address: clear refusal
    assert "SP_HOST_ADDR" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="own exports"):
        pull_exports.main(["--host", "x", "--dest", str(c.REPO / "exports")])
    with pytest.raises(SystemExit, match="own exports"):
        pull_exports.main(["--host", "x", "--dest", str(c.REPO)])        # a parent of exports/
    with pytest.raises(SystemExit, match="law 5"):
        pull_exports.main(["--host", "x", "--dest", str(c.REPO / "data" / "host")])
    (c.REPO / ".env").write_text("SP_HOST_ADDR=sp-vps-1.tail1234.ts.net\n")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    assert pull_exports.host_addr(None) == "sp-vps-1.tail1234.ts.net"
    assert pull_exports.host_addr("override") == "override"
    src = (HOSTING / "pull_exports.py").read_text()
    assert "sp-vps-1" not in src.split('"""', 2)[2]                    # never hardcoded (docstring aside)


# ------------------ season gates are config (architect 2026-09-28) ----------

def test_nhl_gate_is_the_ruled_opening_day_and_every_gate_is_overridable():
    assert chains.CHAINS["nhl-daily"]["active_from"] == "2026-09-29"       # 2026-27 opening day
    assert chains.CHAINS["nhl-daily"]["active_from_env"] == "SP_NHL_ACTIVE_FROM"
    gated = [n for n, ch in chains.CHAINS.items() if ch.get("active_from")]
    assert gated == ["nhl-daily"]                                          # the only season gate today
    for n in gated:                                                        # same treatment for any future one
        var = chains.CHAINS[n].get("active_from_env")
        assert var and var.startswith("SP_") and var.endswith("_ACTIVE_FROM"), n
        assert var in (HOSTING / "etc" / "host.env.example").read_text(), f"{var} undocumented"


def test_season_gate_default_override_receipt_and_malformed(sandbox, monkeypatch, capsys):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    monkeypatch.setitem(chains.CHAINS, "t-season", {"active_from": "2026-09-29",
                                                     "active_from_env": "SP_T_ACTIVE_FROM",
                                                     "steps": [["x"]]})
    monkeypatch.delenv("SP_T_ACTIVE_FROM", raising=False)
    # the day before opening day: skipped, gate receipted with its source
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 9, 28, 16, tzinfo=timezone.utc))
    assert sp_run.main(["t-season"]) == 0
    r = receipts(sandbox)[-1]
    assert r["skipped"] == "inactive_until_2026-09-29"
    assert r["active_from"] == {"date": "2026-09-29",
                                "source": "chains.py default (override: SP_T_ACTIVE_FROM)"}
    assert "· t-season active from 2026-09-29 [chains.py default" in capsys.readouterr().out
    # opening day: it runs, and the chain receipt carries the gate
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 9, 29, 16, tzinfo=timezone.utc))
    assert sp_run.main(["t-season"]) == 0
    r = receipts(sandbox)[-1]
    assert r["kind"] == "chain" and r["steps_ok"] == 1 and r["active_from"]["date"] == "2026-09-29"
    # a config edit moves the start — no code change
    monkeypatch.setenv("SP_T_ACTIVE_FROM", "2026-10-01")
    assert sp_run.main(["t-season"]) == 0
    r = receipts(sandbox)[-1]
    assert r["skipped"] == "inactive_until_2026-10-01" and r["active_from"]["source"] == "SP_T_ACTIVE_FROM"
    # malformed fails loudly (OnFailure pages), never a silent skip
    monkeypatch.setenv("SP_T_ACTIVE_FROM", "Oct 1")
    with pytest.raises(SystemExit, match="SP_T_ACTIVE_FROM='Oct 1' is not a YYYY-MM-DD date"):
        sp_run.main(["t-season"])
    # dry-run prints the gate too
    monkeypatch.delenv("SP_T_ACTIVE_FROM")
    capsys.readouterr()
    assert sp_run.main(["nhl-daily", "--dry-run"]) == 0
    assert "· nhl-daily active from 2026-09-29 [chains.py default (override: SP_NHL_ACTIVE_FROM)]" \
        in capsys.readouterr().out


def test_nhl_daily_syncs_single_days_the_adapter_honours():
    # api_hockey sends `date` only when from == to; a range = a whole-season pull
    steps = sp_run.resolve("nhl-daily", {}, date(2026, 9, 29))
    sm = [s for s in steps if s[0] == "sync-matches"]
    assert [(s[s.index("--date-from") + 1], s[s.index("--date-to") + 1]) for s in sm] == [
        ("2026-09-28", "2026-09-28"), ("2026-09-29", "2026-09-29"), ("2026-09-30", "2026-09-30")]
    from src.adapters.api_hockey import APIHockeyAdapter    # the adapter trait this relies on
    assert "date_from == date_to" in inspect.getsource(APIHockeyAdapter.list_matches)


# --------------- parallel-week exhibit 1 ruling (architect 2026-09-28) ------

import compare_exports  # noqa: E402


def test_prediction_chains_sync_injuries_first_mlb_exempt():
    ch = chains.CHAINS
    # nfl-predict is nfl-prematch since addendum 166 item 6(B): its predict left it, its injury sync stays first
    assert ch["nfl-prematch"]["steps"][0] == ["sync-injuries", "--competition", "NFL", "--season", "2026"]
    for name, c_ in ch.items():                 # the audit, kept as a guard
        cmds = [s[0] for s in c_.get("steps") or []]
        if not {"predict", "predict-nfl"} & set(cmds):
            continue
        if any(s[:2] == ["predict", "--sport"] and "mlb" in s for s in c_["steps"]):
            continue                            # MLB: no injury source (sync-injuries MLB is a no-op)
        first_pred = min(i for i, x in enumerate(cmds) if x in ("predict", "predict-nfl"))
        assert "sync-injuries" in cmds[:first_pred], f"{name}: predicts without syncing injuries"


def _pred(home, away, ko, mid, fair=0.58, inj=280):
    return {"match_id": mid, "utc_date": ko, "home_team": home, "away_team": away,
            "prediction": {"home_win_prob": 0.64},
            "market": {"fair_prob": {"HOME": fair}}, "input_quality": {"injuries": inj}}


def test_comparator_keys_rows_names_unmatched_and_guards_skew(tmp_path, capsys):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    la.mkdir(); ho.mkdir()
    mnf = ("Philadelphia Eagles", "Dallas Cowboys", "2026-09-29T00:15:00")
    lap = {"exported_at": "x", "git_sha": "aaa1111", "predictions": [
        _pred("Kansas City Chiefs", "Buffalo Bills", "2026-10-04T17:00:00", 11),
        _pred(*mnf, 12),
        _pred("Baltimore Ravens", "Pittsburgh Steelers", "2026-10-04T20:25:00", 13)]}
    host = {"exported_at": "y", "git_sha": "bbb2222", "predictions": [
        _pred(*mnf, 907, fair=0.56, inj=0)]}          # different machine-local id
    (la / "nfl_predictions_2026-09-28.json").write_text(json.dumps(lap))
    (ho / "nfl_predictions_2026-09-28.json").write_text(json.dumps(host))
    assert compare_exports.main([str(la), str(ho), "--since", "0"]) == 1
    out = capsys.readouterr().out
    assert "code-version skew: laptop aaa1111 ≠ host bbb2222" in out
    assert "only on laptop (2): Buffalo Bills @ Kansas City Chiefs 2026-10-04T17:00; " \
           "Pittsburgh Steelers @ Baltimore Ravens 2026-10-04T20:25" in out
    key = "[Dallas Cowboys @ Philadelphia Eagles 2026-09-29T00:15]"
    assert f"$.predictions{key}.market.fair_prob.HOME: '0.58' vs '0.56'" in out
    assert f"$.predictions{key}.input_quality.injuries: '280' vs '0'" in out
    assert "match_id" not in out                                    # never compared
    assert "prediction.home_win_prob" not in out                   # identical model probability
    assert "Code-version skew named for: nfl_predictions_2026-09-28.json" in out
    # guard: a file without its SHA cannot claim the class
    host.pop("git_sha")
    (ho / "nfl_predictions_2026-09-28.json").write_text(json.dumps(host))
    compare_exports.main([str(la), str(ho), "--since", "0"])
    out = capsys.readouterr().out
    assert "git_sha missing on host — code-version skew NOT claimable" in out
    assert "Code-version skew named for" not in out


def test_comparator_row_order_and_ids_do_not_matter(tmp_path, capsys):
    la, ho = tmp_path / "l", tmp_path / "h"
    la.mkdir(); ho.mkdir()
    rows = [_pred("A", "B", "2026-10-01T00:00:00", 1), _pred("C", "D", "2026-10-02T00:00:00", 2)]
    (la / "f.json").write_text(json.dumps({"git_sha": "s1", "predictions": rows}))
    (ho / "f.json").write_text(json.dumps({"git_sha": "s1", "predictions": [
        dict(rows[1], match_id=77), dict(rows[0], match_id=88)]}))
    assert compare_exports.main([str(la), str(ho)]) == 0
    assert "✓ f.json" in capsys.readouterr().out


def test_comparator_since_window_skips_settled_dated_files(tmp_path, capsys):
    """--since N (architect 2026-10-01): only files dated within the last N
    UTC days are compared; undated files always; the skip is counted."""
    la, ho = tmp_path / "l", tmp_path / "h"
    la.mkdir(); ho.mkdir()
    same = json.dumps({"git_sha": "s1", "predictions": [_pred("A", "B", "2026-10-01T00:00:00", 1)]})
    for name in ("nfl_predictions_2026-09-29.json", "nfl_predictions_2026-10-01.json", "window_24h.json"):
        (la / name).write_text(same)
        (ho / name).write_text(same)
    # settled and DIVERGENT: outside the default window it must not re-print or fail the run
    (la / "nfl_predictions_2026-09-28.json").write_text(same)
    (ho / "nfl_predictions_2026-09-28.json").write_text(json.dumps({"git_sha": "s1", "predictions": []}))
    assert compare_exports.main([str(la), str(ho), "--today", "2026-10-01"]) == 0
    out = capsys.readouterr().out
    assert "files dated 2026-09-29 .. 2026-10-01 (UTC) + undated; 1 settled file(s)" in out
    assert "✓ window_24h.json" in out and "✓ nfl_predictions_2026-09-29.json" in out
    assert "2026-09-28" not in out.split("\n", 1)[1]
    # --since 0 = everything: the old divergence is back
    assert compare_exports.main([str(la), str(ho), "--today", "2026-10-01", "--since", "0"]) == 1
    assert "✗ nfl_predictions_2026-09-28.json" in capsys.readouterr().out
    assert compare_exports.name_date("fixtures_NHL_next.json") is None
    assert compare_exports.name_date("sp_2026-13-40_x_2026-10-01.json").isoformat() == "2026-10-01"


def test_ncaa_market_covers_thursday_night_slates():
    cals, unit = _timers()["sp-ncaa-market.timer"]
    assert unit == "sp-chain@ncaa-market.service"
    # Tue + Wed 16:00 (ARCHITECT 2026-10-07, addendum 2 item 8a): midweek FBS games get a host fixtures file
    assert cals == ["Tue *-*-* 16:00:00 UTC", "Wed *-*-* 16:00:00 UTC", "Thu *-*-* 16:00:00 UTC",
                    "Fri *-*-* 16:00:00 UTC", "Sat *-*-* 13:00:00 UTC"]


def test_ncaa_market_syncs_results_before_the_export():
    """ARCHITECT 2026-10-02 (#254): Thursday games read SCHEDULED in Friday's export — sync-matches NCAA
    (single-day calls, yesterday + today) runs before the export so finished games leave the window."""
    steps = chains.CHAINS["ncaa-market"]["steps"]
    assert [s[0] for s in steps] == ["sync-matches"] * 3 + ["sync-kalshi-ncaa", "export-fixtures"]
    # {tomorrow} (ARCHITECT 2026-10-07): 8pm-ET-or-later kickoffs fall on the next UTC date.
    for st, d in zip(steps[:3], ("{yesterday}", "{today}", "{tomorrow}")):
        assert st == ["sync-matches", "--competition", "NCAA", "--season", "2026", "--date-from", d, "--date-to", d]
    assert "sync-matches" not in chains.UNMETERED


def test_every_ncaa_kickoff_in_the_next_seven_days_is_refreshed_every_day():
    """ARCHITECT 2026-10-09 (addendum 19 item 3): "On the host, the stored kickoff of every NCAA game in the
    next seven days is at most one day old." On 10-09 the host held 30 of Saturday's games at the provider's
    04:00Z placeholder: ncaa-market synced only yesterday/today (tomorrow on main) and ran Tue-Sat; the window
    service sees 24 hours. For EVERY weekday, the timers that fire that day must, between them, run a
    single-day NCAA sync-matches (the adapter sends `date` only when from == to) for each UTC date
    today..today+7."""
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    monday = date(2026, 10, 5)
    for k, dname in enumerate(days):
        today = monday + timedelta(days=k)
        covered = set()
        for fname, (cals, unit) in _timers().items():
            m = re.match(r"sp-chain@(.+)\.service$", unit)
            if not m or m.group(1) not in chains.CHAINS:
                continue
            ch = chains.CHAINS[m.group(1)]
            if ch.get("window_plan") or ch.get("fullseason"):
                continue  # DB-planned: the window sees 24h; the full-season sync is weekly
            on = [re.match(r"(?:([A-Za-z,]+) )?\*-\*-\* ", cal).group(1) for cal in cals]
            if not any(d is None or dname in d.split(",") for d in on):
                continue
            for st in sp_run.resolve(m.group(1), {}, today):
                if st[0] == "sync-matches" and st[st.index("--competition") + 1] == "NCAA":
                    a, b = st[st.index("--date-from") + 1], st[st.index("--date-to") + 1]
                    assert a == b, f"{fname}: an NCAA range {a}..{b} pulls the whole season listing"
                    covered.add(a)
        want = {(today + timedelta(days=n)).isoformat() for n in range(8)}
        assert want <= covered, f"{dname} {today}: NCAA kickoffs never refreshed for {sorted(want - covered)}"


def test_every_day_the_host_refreshes_ncaa_games_by_id():
    """ARCHITECT 2026-10-09 (addendum 21 item 1): "... refreshed from the provider by the game's own id, at
    least once a day on the host ..." For EVERY weekday some timer that fires that day runs
    `refresh-by-id --competition NCAA --days N` with N >= 7."""
    for k, dname in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        today = date(2026, 10, 5) + timedelta(days=k)
        hit = []
        for fname, (cals, unit) in _timers().items():
            m = re.match(r"sp-chain@(.+)\.service$", unit)
            if not m or m.group(1) not in chains.CHAINS:
                continue
            ch = chains.CHAINS[m.group(1)]
            if ch.get("window_plan") or ch.get("fullseason"):
                continue  # DB-planned
            on = [re.match(r"(?:([A-Za-z,]+) )?\*-\*-\* ", cal).group(1) for cal in cals]
            if not any(d is None or dname in d.split(",") for d in on):
                continue
            for st in sp_run.resolve(m.group(1), {}, today):
                if st[0] == "refresh-by-id" and st[st.index("--competition") + 1] == "NCAA" \
                        and int(st[st.index("--days") + 1]) >= 7:
                    hit.append(fname)
        assert hit, f"{dname}: no host timer refreshes NCAA games by id"


# ------------------------------------------------ transient-step retry ----
# Architect ruling 2026-09-28 (first live page: a UNL sync-matches died on an
# api-football ConnectionResetError): transient classes only, 2 retries,
# 15s/45s, receipted "retried N"; still failing -> pages as today.

RETRY_CLI = '''import sys
from pathlib import Path
a = sys.argv[1:]
n_file = Path("attempts_" + a[0])
n = int(n_file.read_text()) + 1 if n_file.exists() else 1
n_file.write_text(str(n))
print("attempt", n)
if a[0] == "flaky" and n == 1:
    raise ConnectionResetError(104, "Connection reset by peer")
if a[0] == "down":
    print("requests.exceptions.ConnectionError: ('Connection aborted.', "
          "ConnectionResetError(104, 'Connection reset by peer'))")
    sys.exit(1)
if a[0] == "http503" and n == 1:
    print("requests.exceptions.HTTPError: 503 Server Error: Service Unavailable for url: x")
    sys.exit(1)
if a[0] == "http404":
    print("requests.exceptions.HTTPError: 404 Client Error: Not Found for url: x")
    sys.exit(1)
if a[0] == "bug":
    print("fetching fixtures (a Connection reset earlier is only a log mention)")
    raise KeyError("fixture")
print("ok")
'''


@pytest.fixture
def retry_sandbox(sandbox, monkeypatch):
    (c.REPO / "cli.py").write_text(RETRY_CLI)
    waits = []
    monkeypatch.setattr(sp_run, "_sleep", waits.append)
    return sandbox, waits


def _attempts(name):
    p = c.REPO / f"attempts_{name}"
    return int(p.read_text()) if p.exists() else 0


def test_transient_then_success_runs_clean_and_receipts_the_retry(retry_sandbox, monkeypatch, capsys):
    sandbox, waits = retry_sandbox
    monkeypatch.setitem(chains.CHAINS, "t-flaky", {"steps": [["flaky"], ["after"]]})
    assert sp_run.main(["t-flaky"]) == 0
    assert waits == [15] and _attempts("flaky") == 2
    rs = receipts(sandbox)
    step = [r for r in rs if r["kind"] == "step"][0]
    assert step["exit"] == 0 and step["retried"] == 1
    assert [a["transient"] for a in step["attempts"]] == ["ConnectionResetError", None]
    assert [r["kind"] for r in rs].count("page") == 0 and rs[-1]["exit"] == 0
    assert rs[-1]["steps_ok"] == 2
    out = capsys.readouterr().out
    assert "retry 1/2 in 15s" in out and "retried 1: ok" in out
    monkeypatch.setitem(chains.CHAINS, "t-503", {"steps": [["http503"]]})
    assert sp_run.main(["t-503"]) == 0 and waits == [15, 15]


def test_persistent_transient_failure_still_pages_after_two_retries(retry_sandbox, monkeypatch):
    sandbox, waits = retry_sandbox
    monkeypatch.setitem(chains.CHAINS, "t-down", {"steps": [["down"], ["never"]]})
    assert sp_run.main(["t-down"]) == 1                 # non-zero -> OnFailure pages
    assert waits == [15, 45] and _attempts("down") == 3 and _attempts("never") == 0
    rs = receipts(sandbox)
    step = [r for r in rs if r["kind"] == "step"][0]
    assert step["exit"] == 1 and step["retried"] == 2 and len(step["attempts"]) == 3
    assert rs[-1]["kind"] == "chain" and rs[-1]["exit"] == 1 and rs[-1]["steps_ok"] == 0


@pytest.mark.parametrize("name", ["http404", "bug"])
def test_non_transient_failures_never_retry(retry_sandbox, monkeypatch, name):
    sandbox, waits = retry_sandbox
    monkeypatch.setitem(chains.CHAINS, "t-hard", {"steps": [[name]]})
    assert sp_run.main(["t-hard"]) == 1
    assert waits == [] and _attempts(name) == 1
    step = [r for r in receipts(sandbox) if r["kind"] == "step"][0]
    assert "retried" not in step and "attempts" not in step


def test_transient_class_vocabulary():
    t = sp_run.transient_class
    assert t(1, ["requests.exceptions.ConnectionError: ('Connection aborted.', "
                 "ConnectionResetError(104, 'Connection reset by peer'))"]) == "ConnectionError"
    assert t(1, ["requests.exceptions.ReadTimeout: HTTPSConnectionPool(...): Read timed out."]) == "ReadTimeout"
    assert t(1, ["requests.exceptions.HTTPError: 502 Server Error: Bad Gateway"]) == "502 Server Error"
    assert t(1, ["requests.exceptions.HTTPError: 429 Client Error: Too Many Requests"]) == "429 Client Error"
    assert t(1, ["requests.exceptions.HTTPError: 401 Client Error: Unauthorized"]) is None
    assert t(1, ["requests.exceptions.HTTPError: 404 Client Error: Not Found"]) is None
    assert t(1, ["Connection reset while paging", "KeyError: 'fixture'"]) is None  # terminal line decides
    assert t(1, ["✗ sync failed: ('Connection aborted.', RemoteDisconnected(...))"]) == "Connection aborted"
    assert t(0, ["ConnectionError"]) is None and t(-9, ["ConnectionError"]) is None


# ---------------------------- ntfy topic validation (lane C, 2026-09-29) ----

def test_topic_with_whitespace_refused_at_startup_and_never_paged(sandbox, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sp-private topic")          # a space inside
    monkeypatch.setenv("NTFY_CARD_TOPIC", "sp-card-ok")
    probs = sp_notify.topic_problems()
    assert len(probs) == 1 and probs[0].startswith("NTFY_TOPIC contains whitespace")
    assert "sp-private" not in probs[0]                            # the secret topic is never printed
    assert sp_notify.ntfy_url("NTFY_TOPIC") is None
    posted = []
    monkeypatch.setattr(sp_notify.urllib.request, "urlopen", lambda *a, **k: posted.append(a))
    assert sp_notify.deliver("page", "t", "body") is False and posted == []
    rec = receipts(sandbox)[-1]
    assert rec["delivered"] is False and rec["error"] == "invalid_topic_whitespace"
    # sp_run refuses to start a chain (fails loudly, receipted)
    monkeypatch.setitem(chains.CHAINS, "t-ok", {"steps": [["one"]]})
    assert sp_run.main(["t-ok"]) == 2
    rec = receipts(sandbox)[-1]
    assert rec["kind"] == "config_error" and rec["chain"] == "t-ok" and rec["exit"] == 2
    # a trailing newline (the classic paste) is whitespace too; a clean topic passes
    monkeypatch.setenv("NTFY_TOPIC", "sp-private-topic\n")
    assert sp_notify.topic_problems()
    monkeypatch.setenv("NTFY_TOPIC", "sp-private-topic")
    assert sp_notify.topic_problems() == [] and sp_notify.ntfy_url().endswith("/sp-private-topic")


# -------- T-90 hole + quarantine-class line moves (rulings 2026-09-29 on #65) ----

def test_imminent_tier_syncs_model_family_injuries_before_the_card(sandbox, monkeypatch):
    base = datetime(2026, 10, 3, 20, 0)
    _window_db(sandbox / "w.db", base)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{sandbox / 'w.db'}")
    now = base + timedelta(hours=1, minutes=30)          # PL next at +1.5h, MLB +0.5h: imminent; NFL far
    plan = sp_run.window_plan(now)
    assert set(plan["tiers"]["imminent"]) == {"MLB", "PL"}
    steps = [" ".join(s) for s in plan["steps"]]
    inj = [s for s in steps if s.startswith("sync-injuries")]
    assert inj == ["sync-injuries --competition PL --season 2026/27 --kickoff-within-hours 2"]   # MLB never
    assert steps.index(inj[0]) < steps.index("window-card --hours 24")                          # before the card
    cli = _cli()
    opts = {o for p in cli.commands["sync-injuries"].params for o in (*p.opts, *p.secondary_opts)}
    assert "--kickoff-within-hours" in opts
    assert "sync-injuries" not in chains.UNMETERED                  # metered: H0-16(b) days skip it
    monkeypatch.setenv("SP_SKIP_FAMILIES", "SOCCER")
    assert not any(s[0] == "sync-injuries" for s in sp_run.window_plan(now)["steps"])


def test_line_move_pages_through_quiet_hours_high_priority(sandbox, monkeypatch):
    monkeypatch.setenv("SP_WINDOW_STATE", str(sandbox / "ws.json"))
    day = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
    _page(sandbox, monkeypatch, _card({1: {}, 2: {}}), day)                    # baseline
    night = datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc)                  # 03:30 ET: quiet hours
    lm = {"flag": "late-news?", "venues": {"kalshi": {"from": 0.40, "to": 0.33, "move_pp": -7.5, "alarm": True}}}
    card = _card({1: {"late_news_flag": "late-news?", "line_move": lm, "tier": "strong"}, 2: {}})
    rec, sent = _page(sandbox, monkeypatch, card, night)
    assert rec["quiet_hours"] and rec["deltas"]["line_move"] == 1 and rec["suppressed"] == 1   # tier change held
    assert len(sent) == 1 and sent[0][3] == "high" and "LINE MOVE inside T-3h" in sent[0][2]
    assert "tier" not in sent[0][2]
    assert rec["freshen_needed"][0]["reason"] == "line_move"


_ELC_TICKER = "KXEFLCHAMPIONSHIPGAME-26OCT24LEEWBA-LEE"


def _capture_only_move_card(comp):
    """A 6pp+ Kalshi move inside T-3h on one row of competition `comp` (game 1), plus a quiet row (game 2)."""
    lm = {"flag": "late-news?", "threshold_pp": 6.0, "window_h": 3,
          "venues": {"kalshi": {"from": 0.40, "to": 0.33, "move_pp": -7.0, "alarm": True,
                                "from_at": "2026-10-04T14:30:00", "to_at": "2026-10-04T16:05:00",
                                "to_ticker": _ELC_TICKER if comp == "ELC" else "KXEPLGAME-26OCT04ARSCHE-ARS"}}}
    return _card({1: {"competition": comp, "sport": "soccer", "engine": "market_only", "tier": None,
                      "late_news_flag": "late-news?", "line_move": lm},
                  2: {"competition": comp, "sport": "soccer", "engine": "market_only", "tier": None}})


def test_capture_only_line_move_is_logged_and_receipted_never_paged(sandbox, monkeypatch, capsys):
    """ARCHITECT 2026-10-24, addendum 165 item 1: "the pager reads the live list (WINDOW_KALSHI) only, never the new
    table. Keep the move itself: write it to the window's log as one line (series, ticker, from, to, minutes to
    kickoff) [...] Test: a 6pp move on a captured ELC quote produces the log line and no page; the same move on a PL
    quote still pages." """
    assert sp_window_page.CAPTURE_ONLY == frozenset(chains.WINDOW_KALSHI_CAPTURE_ONLY) - frozenset(chains.WINDOW_KALSHI)
    assert sp_window_page.CAPTURE_ONLY == {"PD", "SA", "BL1", "FL1", "ELC"} and "PL" not in sp_window_page.CAPTURE_ONLY
    monkeypatch.setenv("SP_WINDOW_STATE", str(sandbox / "ws.json"))
    day = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
    quiet = _card({1: {"competition": "ELC", "sport": "soccer", "engine": "market_only", "tier": None},
                   2: {"competition": "ELC", "sport": "soccer", "engine": "market_only", "tier": None}})
    _page(sandbox, monkeypatch, quiet, day)                                    # baseline (and the day's digest)
    capsys.readouterr()
    rec, sent = _page(sandbox, monkeypatch, _capture_only_move_card("ELC"), day + timedelta(hours=1, minutes=5))
    out = capsys.readouterr().out
    want = ("· capture-only line move (addendum 165 item 1): ELC KXEFLCHAMPIONSHIPGAME "
            f"{_ELC_TICKER} 0.400->0.330 (-7.0pp) · 55 min to kickoff · venue kalshi")
    assert out.splitlines() == [want]                                          # one line, in the window's log
    assert rec["capture_only_moves"] == {"count": 1, "lines": [want]}
    assert sent == [] and not rec["paged"]                                     # no page, no priority raised
    assert rec["deltas"]["line_move"] == 0 and rec["freshen_needed"] == []     # no freshen
    # the same row again: the move is a transition, logged once
    rec, sent = _page(sandbox, monkeypatch, _capture_only_move_card("ELC"), day + timedelta(hours=1, minutes=10))
    assert rec["capture_only_moves"]["count"] == 0 and sent == []
    # only the book venue alarmed: the same line, venue book, series and ticker '-'; still no page
    card = _card({1: {"competition": "SA", "sport": "soccer", "engine": "market_only", "tier": None,
                      "late_news_flag": "late-news?",
                      "line_move": {"flag": "late-news?", "venues": {
                          "book": {"from": 0.50, "to": 0.57, "move_pp": 7.0, "alarm": True,
                                   "to_at": "2026-10-04T16:30:00"},
                          "kalshi": {"from": 0.50, "to": 0.51, "move_pp": 1.0, "alarm": False,
                                     "to_ticker": "KXSERIEAGAME-26OCT04INTMIL-INT"}}}}})
    monkeypatch.setenv("SP_WINDOW_STATE", str(sandbox / "ws-sa.json"))
    _page(sandbox, monkeypatch, _card({1: {"competition": "SA", "sport": "soccer", "engine": "market_only",
                                           "tier": None}}), day)
    capsys.readouterr()
    rec, sent = _page(sandbox, monkeypatch, card, day + timedelta(hours=1))
    assert capsys.readouterr().out.splitlines() == [
        "· capture-only line move (addendum 165 item 1): SA - - 0.500->0.570 (+7.0pp) · 30 min to kickoff · venue book"]
    assert sent == [] and rec["freshen_needed"] == []
    # every other class still pages on a capture-only league (only the line move is held back)
    monkeypatch.setenv("SP_WINDOW_STATE", str(sandbox / "ws-q.json"))
    _page(sandbox, monkeypatch, quiet, day)
    rec, sent = _page(sandbox, monkeypatch, _card({1: {"competition": "ELC", "sport": "soccer", "quarantine": True,
                                                       "engine": "market_only", "tier": None},
                                                   2: {"competition": "ELC", "sport": "soccer",
                                                       "engine": "market_only", "tier": None}}), day)
    assert rec["deltas"]["quarantine"] == 1 and len(sent) == 1 and "QUARANTINE ON" in sent[0][2]


def test_live_line_move_still_pages_high_with_freshen(sandbox, monkeypatch, capsys):
    """Addendum 165 item 1: "the same move on a PL quote still pages"; as does a competition in neither table."""
    for comp in ("PL", "UEL"):
        monkeypatch.setenv("SP_WINDOW_STATE", str(sandbox / f"ws-{comp}.json"))
        day = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
        _page(sandbox, monkeypatch, _card({1: {"competition": comp, "sport": "soccer"},
                                           2: {"competition": comp, "sport": "soccer"}}), day)
        capsys.readouterr()
        rec, sent = _page(sandbox, monkeypatch, _capture_only_move_card(comp), day + timedelta(hours=1, minutes=5))
        assert "capture-only line move" not in capsys.readouterr().out
        assert rec["capture_only_moves"] == {"count": 0, "lines": []}
        assert rec["deltas"]["line_move"] == 1 and len(sent) == 1 and sent[0][3] == "high"
        assert "LINE MOVE inside T-3h" in sent[0][2]
        assert rec["freshen_needed"] == [{"id": "1", "sport": "soccer", "competition": comp, "reason": "line_move"}]


def test_window_capture_only_kalshi_steps_come_after_every_live_kalshi_step(sandbox, monkeypatch):
    """ARCHITECT 2026-10-24, addendum 165 item 4: "confirm [...] that the five sync-kalshi-soccer steps are AFTER the
    live Kalshi steps in the chain, so a 429 on a shadow league never delays a live capture. [...] a unit test that
    asserts the order is enough." SA's game kicks off BEFORE PL's (and MLB's), so the order is the plan's, not the
    kickoffs'."""
    now = datetime(2026, 10, 3, 20, 0)
    _window_db(sandbox / "w.db", now)
    con = sqlite3.connect(sandbox / "w.db")
    con.executemany("INSERT INTO competitions VALUES (?,?,?)", [(6, "SOCCER", "SA"), (7, "SOCCER", "BL1")])
    fmt = "%Y-%m-%d %H:%M:%S"
    con.executemany("INSERT INTO matches(competition_id, season, status, utc_date) VALUES (?,?,?,?)",
                    [(6, "2026/27", "SCHEDULED", (now + timedelta(hours=2, minutes=10)).strftime(fmt)),
                     (7, "2026/27", "SCHEDULED", (now + timedelta(hours=1)).strftime(fmt))])
    con.commit()
    con.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{sandbox / 'w.db'}")
    steps = sp_run.window_plan(now)["steps"]
    live = {tuple(st) for sts in chains.WINDOW_KALSHI.values() for st in sts}
    capture = {tuple(st) for sts in chains.WINDOW_KALSHI_CAPTURE_ONLY.values() for st in sts}
    live_i = [i for i, st in enumerate(steps) if tuple(st) in live]
    cap_i = [i for i, st in enumerate(steps) if tuple(st) in capture]
    assert [" ".join(steps[i]) for i in cap_i] == ["sync-kalshi-soccer --competition BL1",
                                                  "sync-kalshi-soccer --competition SA"]
    assert {" ".join(steps[i]) for i in live_i} >= {"sync-kalshi-soccer --competition PL",
                                                   "sync-kalshi --date-from {today} --date-to {tomorrow}"}
    assert max(live_i) < min(cap_i)


# --------------------------------- catch-up (architect 2026-09-29) ----
# Laptop completeness sweep vs the host fingerprint: sync-teams then
# sync-matches for every competition-season the laptop is short on.

CATCHUP_CLI = '''import os, sqlite3, sys
a = sys.argv[1:]
open("calls.log", "a").write(" ".join(a) + "\\n")
if os.environ.get("CU_FAIL") and a[0] == "sync-matches":
    print("requests.exceptions.HTTPError: 404 Client Error: Not Found"); sys.exit(1)
if a[0] == "sync-matches":
    comp, season = a[a.index("--competition") + 1], a[a.index("--season") + 1]
    con = sqlite3.connect(os.environ["DATABASE_URL"].replace("sqlite:///", ""))
    row = con.execute("SELECT id FROM competitions WHERE code = ?", (comp,)).fetchone()
    cid = row[0] if row else con.execute("INSERT INTO competitions(sport, code) VALUES ('SOCCER', ?)",
                                         (comp,)).lastrowid
    have = con.execute("SELECT COUNT(*) FROM matches WHERE competition_id = ? AND season = ?",
                       (cid, season)).fetchone()[0]
    want = int(os.environ.get("CU_" + comp.replace("/", "_"), have))
    con.executemany("INSERT INTO matches(competition_id, season, status) VALUES (?,?,'FINISHED')",
                    [(cid, season)] * max(want - have, 0))
    con.commit()
print("ok", " ".join(a))
'''

LAPTOP_ROWS = [("SOCCER", "UEL", "2024/25", "FINISHED", 202), ("SOCCER", "PL", "2025/26", "FINISHED", 380),
               ("NHL", "NHL", "2025", "FINISHED", 1498), ("MLB", "MLB", "2025", "FINISHED", 2430),
               ("NFL", "NFL", "2025", "FINISHED", 280)]
HOST_ROWS = [("SOCCER", "UEL", "2024/25", "FINISHED", 269), ("SOCCER", "PL", "2025/26", "FINISHED", 380),
             ("NHL", "NHL", "2025", "FINISHED", 1498), ("SOCCER", "EL1", "2025/26", "FINISHED", 552),
             ("NFL", "NFL", "2025", "FINISHED", 285)]      # MLB absent: the host skips MLB (ASN)


def test_catch_up_plan_behind_ahead_new_comp_and_skip(tmp_path):
    lap = bootstrap.fingerprint(_fp_db(tmp_path / "l.db", LAPTOP_ROWS))
    ref = bootstrap.fingerprint(_fp_db(tmp_path / "h.db", HOST_ROWS))
    p = bootstrap.catch_up_plan(lap, ref, skip={"NFL"})
    behind = {(r["comp"], r["season"]): r for r in p["behind"]}
    assert set(behind) == {("UEL", "2024/25"), ("EL1", "2025/26"), ("NFL", "2025")}
    assert behind[("UEL", "2024/25")]["short"] == 67 and not behind[("UEL", "2024/25")]["new_comp"]
    assert behind[("NFL", "2025")]["skipped"] and behind[("NFL", "2025")]["steps"] == []
    flat = [" ".join(s) for s in p["steps"]]
    assert flat == ["sync-competitions --sport soccer",                 # EL1: laptop has no games at all
                    "sync-teams --competition EL1 --season 2025/26",
                    "sync-matches --competition EL1 --season 2025/26",
                    "sync-teams --competition UEL --season 2024/25",    # the ruled order: teams first
                    "sync-matches --competition UEL --season 2024/25"]
    assert [(r["comp"], r["laptop"], r["reference"]) for r in p["ahead"]] == [("MLB", 2430, 0)]
    cli = _cli()
    for st in p["steps"]:
        opts = {o for q in cli.commands[st[0]].params for o in (*q.opts, *q.secondary_opts)}
        assert all(t in opts for t in st[1:] if t.startswith("--")), st


def _catchup_env(sandbox, monkeypatch):
    lap_db = _fp_db(sandbox / "live" / "laptop.db", LAPTOP_ROWS)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{lap_db}")
    ref = sandbox / "fp_host.json"
    ref.write_text(json.dumps(bootstrap.fingerprint(_fp_db(sandbox / "h.db", HOST_ROWS))))
    (c.REPO / "cli.py").write_text(CATCHUP_CLI)
    return lap_db, ref


def test_catch_up_dry_run_changes_nothing(sandbox, monkeypatch, capsys):
    lap_db, ref = _catchup_env(sandbox, monkeypatch)
    assert bootstrap.main(["catch-up", "--reference", str(ref)]) == 0
    out = capsys.readouterr().out
    assert "CATCH-UP (DRY-RUN)" in out and "UEL    2024/25  laptop   202 < reference   269 (short 67)" in out
    assert "python cli.py sync-teams --competition UEL --season 2024/25" in out
    assert "laptop ahead: informational, untouched" in out
    assert not (c.REPO / "calls.log").exists()                        # nothing ran
    rec = receipts(sandbox)[-1]
    assert rec["kind"] == "catch_up" and rec["applied"] is False and rec["steps"] == 7   # NFL 2 + soccer 1+2+2
    assert not list((sandbox / "backups").glob("*.db")) if (sandbox / "backups").exists() else True


def test_catch_up_apply_backs_up_runs_in_order_and_receipts(sandbox, monkeypatch, capsys):
    lap_db, ref = _catchup_env(sandbox, monkeypatch)
    monkeypatch.setenv("CU_UEL", "269")
    monkeypatch.setenv("CU_EL1", "552")
    monkeypatch.setenv("CU_NFL", "285")
    assert bootstrap.main(["catch-up", "--reference", str(ref), "--apply"]) == 0
    calls = (c.REPO / "calls.log").read_text().splitlines()
    assert calls[:2] == ["sync-teams --competition NFL --season 2025",           # family order: NFL first
                         "sync-matches --competition NFL --season 2025"]
    assert calls.index("sync-competitions --sport soccer") < calls.index("sync-teams --competition EL1 --season 2025/26")
    assert calls.index("sync-teams --competition UEL --season 2024/25") + 1 == \
        calls.index("sync-matches --competition UEL --season 2024/25")
    rs = receipts(sandbox)
    assert rs[0]["kind"] == "backup" and rs[0]["integrity"] == "ok"   # daily backup before any write
    cu = {(r["comp"], r["season"]): r for r in rs if r["kind"] == "catch_up"}
    assert cu[("UEL", "2024/25")]["laptop_before"] == 202 and cu[("UEL", "2024/25")]["laptop_after"] == 269
    assert all(r["closed"] for r in cu.values())
    assert "3/3 season(s) closed" in capsys.readouterr().out
    # re-run: nothing left to do
    assert bootstrap.main(["catch-up", "--reference", str(ref), "--apply"]) == 0
    assert "nothing to catch up" in capsys.readouterr().out


def test_catch_up_stops_at_failure_and_refuses_version_skew(sandbox, monkeypatch):
    lap_db, ref = _catchup_env(sandbox, monkeypatch)
    monkeypatch.setenv("CU_FAIL", "1")
    assert bootstrap.main(["catch-up", "--reference", str(ref), "--apply"]) == 1
    cu = [r for r in receipts(sandbox) if r["kind"] == "catch_up"]
    assert len(cu) == 1 and cu[0]["exit"] == 1 and cu[0]["closed"] is False     # stopped at the first season
    fp = json.loads(ref.read_text())
    fp["producer"]["bootstrap_blob_sha"] = "0" * 40
    ref.write_text(json.dumps(fp))
    assert bootstrap.main(["catch-up", "--reference", str(ref)]) == 2
    assert receipts(sandbox)[-1]["refused"] == "version_mismatch"


# ------------------------------------- release on every receipt (2026-10-06) ----

def test_running_release_reads_a_checkout_owned_by_another_user(tmp_path, monkeypatch):
    """ARCHITECT 2026-10-06, cutover-readiness (b): receipts.jsonl carried no release. The host checkout is
    root-installed and the units run as `sp`; git refuses a repo owned by another user ("dubious ownership"),
    so running_release() was None on every receipt. _git passes safe.directory for REPO only."""
    import os
    import subprocess
    if os.geteuid() != 0:
        pytest.skip("needs root to own the repo as another user")
    repo = tmp_path / "owned"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    subprocess.run(["git", "-C", str(repo), "tag", "v9.9.9"], check=True)
    subprocess.run(["chown", "-R", "nobody", str(repo)], check=True)
    plain = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    assert plain.returncode != 0 and "dubious ownership" in plain.stderr        # the host's failure, reproduced
    monkeypatch.setattr(c, "REPO", repo)
    assert c.running_release() == "v9.9.9"


def test_a_null_release_carries_its_reason(sandbox, monkeypatch, tmp_path):
    """Law 4: never a guessed tag — but a null release always states why."""
    monkeypatch.setattr(c, "REPO", tmp_path / "not-a-repo")
    line = c.append_receipt({"kind": "chain", "unit": "sp-chain@x.service", "exit": 0})
    assert line["release"] is None and line["release_error"]
    stored = json.loads(c.receipts_path().read_text().splitlines()[-1])
    assert stored["release_error"] == line["release_error"]


def test_deploy_prints_the_exact_migration_command(monkeypatch):
    """ARCHITECT 2026-10-06: the deploy flagged migrate_kalshi_ticker.py; it prints the exact by-hand command
    — as the service user, host.env loaded, the daily .backup first, the migration only if it succeeded."""
    import sp_deploy
    cmd = sp_deploy.migration_command(["migrate_kalshi_ticker.py"], "abc1234")
    assert cmd.startswith("sudo -u sp sh -c ")
    assert f"cd {c.REPO}" in cmd and f". {c.HOST_ENV}" in cmd
    assert "deploy/hosting/sp_deploy.py --expect abc1234 --run-migrations migrate_kalshi_ticker.py" in cmd


def test_deploy_migration_plan_orders_by_commit_and_skips_rollbacks(tmp_path, monkeypatch):
    """Codex on #296 (two P2s, verified): the migrations printed in git's alphabetical path order
    (migrate_score_90.py needs migrate_status_raw.py first), and a rollback's diff printed migrations
    the target predates as runnable. Order is now commit order; a non-forward deploy runs none."""
    import subprocess

    import sp_deploy
    repo = tmp_path / "r"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q")
    (repo / "a.txt").write_text("x")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "--short", "HEAD")
    (repo / "migrate_status_raw.py").write_text("1")
    g("add", "-A")
    g("commit", "-q", "-m", "first")
    (repo / "migrate_score_90.py").write_text("2")
    g("add", "-A")
    g("commit", "-q", "-m", "second")
    head = g("rev-parse", "--short", "HEAD")
    monkeypatch.setattr(c, "REPO", repo)
    changed = sorted(["migrate_score_90.py", "migrate_status_raw.py"])          # git diff's alphabetical order
    fwd = sp_deploy.migration_plan(base, head, changed)
    assert fwd["forward"] and fwd["run"] == ["migrate_status_raw.py", "migrate_score_90.py"]
    cmd = sp_deploy.migration_command(fwd["run"], head)
    assert cmd.index("migrate_status_raw.py") < cmd.index("migrate_score_90.py")
    back = sp_deploy.migration_plan(head, base, changed)                        # a rollback
    assert not back["forward"] and back["run"] == [] and set(back["skipped"]) == set(changed)


def test_run_migrations_holds_one_lock_across_backup_and_every_migration(sandbox, monkeypatch):
    """Codex on #296 (P2, verified): `sp_backup.py daily && migrate…` released the DB lock between the backup and
    the migrations (sp_backup locks only its own copy; migrations take none), so a timer could interleave. The
    printed command now runs `sp_deploy.py --run-migrations`, which holds one lock for the whole sequence."""
    import sp_deploy
    probe = ("import fcntl, os, sys\n"
             "f = open(os.environ['SP_LOCK'], 'a+')\n"
             "try:\n    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n    sys.exit(3)\n"
             "except BlockingIOError:\n    open(sys.argv[0] + '.ran', 'w').write('locked')\n")
    import subprocess

    def g(*a):
        return subprocess.run(["git", "-C", str(c.REPO), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    for m in ("migrate_a.py", "migrate_b.py"):
        (c.REPO / m).write_text(probe)
    (c.REPO / "migrate_c.py").write_text("import sys; sys.exit(5)")
    (c.REPO / "migrate_d.py").write_text("open('d.ran','w')")
    g("init", "-q")
    g("add", "-A")
    g("commit", "-q", "-m", "migrations")
    head = g("rev-parse", "HEAD")
    assert sp_deploy.run_migrations(["migrate_a.py", "migrate_b.py"], head) == 0
    assert (c.REPO / "migrate_a.py.ran").exists() and (c.REPO / "migrate_b.py.ran").exists()
    recs = [json.loads(x) for x in c.receipts_path().read_text().splitlines()]
    assert [r.get("step") for r in recs if r["kind"] == "migrations"] == ["migrate_a.py", "migrate_b.py"]
    assert any(r["kind"] == "backup" and r["exit"] == 0 for r in recs)              # the backup ran first
    assert sp_deploy.run_migrations(["migrate_c.py", "migrate_d.py"], head) == 5    # stops at the failure
    assert not (c.REPO / "d.ran").exists()
    with pytest.raises(SystemExit, match="not a migrate_"):
        sp_deploy.run_migrations(["../evil.py"], head)


def test_migration_plan_merge_added_and_ancestry_errors(tmp_path, monkeypatch):
    """Codex on #296, round 2 (verified): a migration added in a MERGE result is new and runnable; an ancestry
    check that errors (not 'no') refuses the plan instead of reading as a rollback."""
    import subprocess

    import sp_deploy
    repo = tmp_path / "m"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (repo / "a.txt").write_text("x")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    g("checkout", "-q", "-b", "side")
    (repo / "b.txt").write_text("y")
    g("add", "-A")
    g("commit", "-q", "-m", "side")
    g("checkout", "-q", "main")
    (repo / "c.txt").write_text("z")
    g("add", "-A")
    g("commit", "-q", "-m", "main")
    g("merge", "-q", "--no-ff", "--no-commit", "side")
    (repo / "migrate_in_merge.py").write_text("1")                               # added in the merge result
    g("add", "-A")
    g("commit", "-q", "-m", "merge")
    head = g("rev-parse", "HEAD")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, head, ["migrate_in_merge.py"])
    assert plan["forward"] and plan["run"] == ["migrate_in_merge.py"] and plan["modified"] == []
    with pytest.raises(SystemExit, match="ancestry check"):
        sp_deploy.migration_plan("0" * 40, head, ["migrate_in_merge.py"])


def test_explicit_release_is_not_reported_as_an_error(sandbox, monkeypatch):
    """Codex on #296 (P3, verified): sp_cutover's dry run passes its own release (the scratch checkout is not a git
    tree); the receipt must not also carry release_error."""
    monkeypatch.setattr(c, "REPO", sandbox / "not-a-repo")
    line = c.append_receipt({"kind": "cutover", "exit": 0, "release": "v9.9.9"})
    assert line["release"] == "v9.9.9" and "release_error" not in line


def test_deploy_plans_migrations_before_moving_the_checkout(sandbox, monkeypatch):
    """Codex on #296, round 3 (verified): the plan ran after `git checkout` had detached HEAD at the target, so a
    planning failure left production on new code with the old schema and no receipt. The plan now runs first;
    a refusal leaves the checkout where it was."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    (origin / "a.txt").write_text("x")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "base")
    g(origin, "tag", "v1.0.0")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    (origin / "migrate_new.py").write_text("1")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "migration")
    g(origin, "tag", "v1.0.1")
    monkeypatch.setattr(c, "REPO", repo)
    before = g(repo, "rev-parse", "HEAD")

    def boom(*a, **k):
        raise SystemExit("✗ ancestry check failed (simulated) — refusing to plan migrations.")
    monkeypatch.setattr(sp_deploy, "migration_plan", boom)
    with pytest.raises(SystemExit, match="refusing to plan"):
        sp_deploy.main(["--tag", "v1.0.1"])
    assert g(repo, "rev-parse", "HEAD") == before                    # the checkout never moved
    monkeypatch.undo()
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setenv("SP_RECEIPTS", str(sandbox / "log" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    assert sp_deploy.main(["--tag", "v1.0.1", "--dry-run"]) == 0       # the plan is also shown on a dry run
    assert g(repo, "rev-parse", "HEAD") == before


def test_review_round_four_release_binding_dry_run_and_lookup_failures(sandbox, monkeypatch):
    """Codex on #296, round 4 (verified): (1) --run-migrations is bound to the planned release (--expect SHA) and
    refuses before any backup when HEAD moved; (2) --dry-run with --run-migrations refuses (a dry run changes
    nothing); (3) a FAILED tag or branch lookup makes the release unreadable, never 'no tag' / 'detached'."""
    import subprocess

    import sp_deploy

    def g(*a):
        return subprocess.run(["git", "-C", str(c.REPO), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    (c.REPO / "migrate_x.py").write_text("open('x.ran','w')")
    g("init", "-q")
    g("add", "-A")
    g("commit", "-q", "-m", "one")
    planned = g("rev-parse", "HEAD")
    (c.REPO / "migrate_x.py").write_text("open('changed.ran','w')")              # another release moved HEAD
    g("add", "-A")
    g("commit", "-q", "-m", "two")
    with pytest.raises(SystemExit, match="not the planned release"):
        sp_deploy.run_migrations(["migrate_x.py"], planned)
    assert not (c.REPO / "changed.ran").exists() and not (sandbox / "backups").exists()   # nothing ran, no backup
    with pytest.raises(SystemExit, match="needs --expect"):
        sp_deploy.run_migrations(["migrate_x.py"], None)
    with pytest.raises(SystemExit, match="dry run never"):
        sp_deploy.main(["--dry-run", "--run-migrations", "migrate_x.py", "--expect", planned])
    real = c._git
    monkeypatch.setattr(c, "_git", lambda *a: None if a[:2] == ("tag", "--points-at") else real(*a))
    assert c.running_release() is None                                          # not "UNTAGGED@…"
    monkeypatch.setattr(c, "_git", lambda *a: None if a[:2] == ("rev-parse", "--abbrev-ref") else real(*a))
    assert c.running_release() is None                                          # not "UNTAGGED@…"


def test_review_round_five_same_commit_order_renames_and_locked_validation(sandbox, monkeypatch):
    """Codex on #296, round 5 (verified): (1) two migrations added by ONE commit have no determinable order (git
    lists them alphabetically): no runnable command, the operator orders them; (2) a RENAMED migration already
    ran under its old name: reported, never runnable; (3) the files are validated under the DB lock."""
    import subprocess

    import sp_deploy
    repo = sandbox / "g"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q")
    (repo / "migrate_old_name.py").write_text("print('a long enough body for rename detection to work')\n" * 5)
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_z_prerequisite.py").write_text("1")
    (repo / "migrate_a_consumer.py").write_text("2")
    g("add", "-A")
    g("commit", "-q", "-m", "two at once")
    g("mv", "migrate_old_name.py", "migrate_new_name.py")
    g("commit", "-q", "-m", "rename")
    head = g("rev-parse", "HEAD")
    monkeypatch.setattr(c, "REPO", repo)
    changed = sorted(["migrate_z_prerequisite.py", "migrate_a_consumer.py", "migrate_old_name.py",
                      "migrate_new_name.py"])
    plan = sp_deploy.migration_plan(base, head, changed)
    assert plan["run"] == [] and plan["undetermined"] == ["migrate_a_consumer.py", "migrate_z_prerequisite.py"]
    assert plan["renamed"] == {"migrate_new_name.py": "migrate_old_name.py"}
    assert "migrate_new_name.py" not in plan["new"] and "migrate_new_name.py" in plan["modified"]
    seen = []
    real_lock = c.db_lock

    from contextlib import contextmanager

    @contextmanager
    def spy_lock(*a, **k):
        seen.append("lock")
        with real_lock(*a, **k):
            yield
    monkeypatch.setattr(c, "db_lock", spy_lock)
    with pytest.raises(SystemExit, match="not a migrate_"):
        sp_deploy.run_migrations(["migrate_missing.py"], head)
    assert seen == ["lock"]                                               # refused INSIDE the lock


def test_post_merge_review_copies_and_merge_commit_grouping(sandbox, monkeypatch):
    """Codex post-merge on #296 (verified): (1) an UNCHANGED copy of an existing migration was reported by
    `diff -M` as an addition and planned as runnable (a one-shot applied twice); (2) a branch adding two
    migrations in ordered commits, then merged, had both re-listed by `log -m` in the merge commit's first-parent
    diff and was marked "added together" (no runnable command). A template-derived new migration stays new."""
    import subprocess

    import sp_deploy
    repo = sandbox / "g2"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    body = "print('a long enough one-shot migration body for copy detection')\n" * 5
    g("init", "-q", "-b", "main")
    (repo / "migrate_once.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_copy_of_once.py").write_text(body)                  # unchanged copy
    (repo / "migrate_from_template.py").write_text(body + "extra = 'a real new step'\n" * 4)
    g("add", "-A")
    g("commit", "-q", "-m", "copy + template")                          # before the branch: one ancestry chain
    g("checkout", "-q", "-b", "feat")
    (repo / "migrate_b_first.py").write_text("first = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "first")
    (repo / "migrate_a_second.py").write_text("second = 2\n")
    g("add", "-A")
    g("commit", "-q", "-m", "second")
    g("checkout", "-q", "main")
    g("merge", "-q", "--no-ff", "-m", "merge feat", "feat")
    head = g("rev-parse", "HEAD")
    monkeypatch.setattr(c, "REPO", repo)
    changed = ["migrate_b_first.py", "migrate_a_second.py", "migrate_copy_of_once.py", "migrate_from_template.py"]
    plan = sp_deploy.migration_plan(base, head, changed)
    assert plan["renamed"] == {"migrate_copy_of_once.py": "migrate_once.py"}
    assert "migrate_copy_of_once.py" not in plan["run"]
    assert plan["undetermined"] == []
    run = plan["run"]
    assert run == ["migrate_from_template.py", "migrate_b_first.py", "migrate_a_second.py"]   # the commit chain


def test_codex_on_304_template_copies_stay_new_and_re_adds_keep_their_grouping(sandbox, monkeypatch):
    """Codex on #304 (verified): (1) --find-copies-harder offers unchanged NON-migration files as copy sources, so
    a new migration identical to a shared template was suppressed as a copy; only a source that was a migration
    at `before` counts. (2) add migrate_x, delete it, then add migrate_x + migrate_y in ONE commit: first-appearance
    grouping dropped the re-add and planned a runnable order; the re-add counts, so the pair is undetermined."""
    import subprocess

    import sp_deploy
    repo = sandbox / "g3"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    tmpl = "print('a shared schema template body long enough for copy detection')\n" * 5
    g("init", "-q", "-b", "main")
    (repo / "schema_template.py").write_text(tmpl)
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_add_widget.py").write_text(tmpl)                    # identical to a NON-migration file
    g("add", "-A")
    g("commit", "-q", "-m", "widget")
    (repo / "migrate_x.py").write_text("x = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "x")
    g("rm", "-q", "migrate_x.py")
    g("commit", "-q", "-m", "drop x")
    (repo / "migrate_x.py").write_text("x = 2\n")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "x and y together")
    head = g("rev-parse", "HEAD")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, head, ["migrate_add_widget.py", "migrate_x.py", "migrate_y.py"])
    assert plan["renamed"] == {} and "migrate_add_widget.py" in plan["new"]
    assert "migrate_x.py" in plan["undetermined"] and plan["run"] == []      # a re-add: ambiguous history


def test_codex_on_304_round_2_content_copies_and_competing_branch_additions(sandbox, monkeypatch):
    """Codex on #304, round 2 (verified): (1) with a byte-identical template AND migration at `before`, git may
    name the template as the copy source, leaving an exact copy of the already-run migration runnable; copies are
    now decided by content against every prior migration. (2) branch A adds x + y together, branch B later adds a
    DIFFERENT x, the merge keeps A's x: B's addition is not the one the release carries, so x + y stay undetermined."""
    import subprocess

    import sp_deploy

    def mk(name):
        repo = sandbox / name
        repo.mkdir()

        def g(*a, check=True, when=None):
            env = None
            if when:                                # pin commit dates: log order between branches is by date
                import os
                env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=check, capture_output=True, text=True, env=env).stdout.strip()
        g("init", "-q", "-b", "main")
        return repo, g
    body = "print('one-shot body, long enough for any similarity heuristics')\n" * 5
    repo, g = mk("g4")
    (repo / "a_template.py").write_text(body)
    (repo / "migrate_once.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_copy.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "copy")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_copy.py"])
    assert plan["renamed"] == {"migrate_copy.py": "migrate_once.py"} and plan["run"] == []

    repo, g = mk("g5")
    (repo / "r.txt").write_text("r")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    g("checkout", "-q", "-b", "a")
    (repo / "migrate_x.py").write_text("x = 'A'\n")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "A: x and y together", when="2026-01-01T00:00:00Z")
    g("checkout", "-q", "main")
    g("checkout", "-q", "-b", "b")
    (repo / "migrate_x.py").write_text("x = 'B'\n")
    g("add", "-A")
    g("commit", "-q", "-m", "B: a different x", when="2026-01-02T00:00:00Z")     # B's addition logs LATER
    g("checkout", "-q", "a")
    g("merge", "-q", "--no-ff", "-m", "merge b", "b", check=False)       # conflict on migrate_x.py
    (repo / "migrate_x.py").write_text("x = 'A'\n")                      # keep A's version
    g("add", "-A")
    g("commit", "-q", "-m", "merge b (keep A's x)", when="2026-01-03T00:00:00Z")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert "migrate_x.py" in plan["undetermined"] and plan["run"] == []      # competing additions: ambiguous


def test_codex_on_304_round_3_identical_additions_on_two_branches_are_undetermined(sandbox, monkeypatch):
    """Codex on #304, round 3 (verified): branch A adds migrate_x + migrate_y together, branch B adds a
    BYTE-IDENTICAL migrate_x later; both additions carry the released blob, and picking the later one planned
    a runnable order. Several carrying additions = undetermined."""
    import os
    import subprocess

    import sp_deploy
    repo = sandbox / "g6"
    repo.mkdir()

    def g(*a, when=None, check=True):
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else None
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=check, capture_output=True, text=True, env=env).stdout.strip()
    g("init", "-q", "-b", "main")
    (repo / "r.txt").write_text("r")
    g("add", "-A")
    g("commit", "-q", "-m", "base", when="2025-12-31T00:00:00Z")
    base = g("rev-parse", "HEAD")
    g("checkout", "-q", "-b", "a")
    (repo / "migrate_x.py").write_text("x = 1\n")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "A", when="2026-01-01T00:00:00Z")
    g("checkout", "-q", "main")
    g("checkout", "-q", "-b", "b")
    (repo / "migrate_x.py").write_text("x = 1\n")                       # byte-identical
    g("add", "-A")
    g("commit", "-q", "-m", "B", when="2026-01-02T00:00:00Z")
    g("checkout", "-q", "a")
    g("merge", "-q", "--no-ff", "-m", "merge b", "b", when="2026-01-03T00:00:00Z")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert plan["run"] == [] and "migrate_x.py" in plan["undetermined"]


def test_codex_on_304_round_4_parallel_branches_unmatched_and_merge_only_re_adds(sandbox, monkeypatch):
    """Codex on #304, round 4 (verified): (1) migrate_x on one branch and migrate_y on a sibling branch have no
    ancestry: traversal order is not dependency order -> undetermined; (2) competing additions of x whose released
    version was later modified (no blob match) -> undetermined; (3) a merge-only addition deleted and re-added by
    another merge -> undetermined. Only a strict ancestry chain of single additions is runnable."""
    import os
    import subprocess

    import sp_deploy

    def mk(name):
        repo = sandbox / name
        repo.mkdir()

        def g(*a, when=None, check=True):
            env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else None
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=check, capture_output=True, text=True, env=env).stdout.strip()
        g("init", "-q", "-b", "main")
        (repo / "r.txt").write_text("r")
        g("add", "-A")
        g("commit", "-q", "-m", "base", when="2025-12-31T00:00:00Z")
        return repo, g, g("rev-parse", "HEAD")

    def plan(repo, g, base, files):
        monkeypatch.setattr(c, "REPO", repo)
        return sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), files)

    repo, g, base = mk("p1")                                            # (1) parallel branches
    g("checkout", "-q", "-b", "a")
    (repo / "migrate_x.py").write_text("x\n")
    g("add", "-A")
    g("commit", "-q", "-m", "x", when="2026-01-01T00:00:00Z")
    g("checkout", "-q", "main")
    (repo / "migrate_y.py").write_text("y\n")
    g("add", "-A")
    g("commit", "-q", "-m", "y", when="2026-01-02T00:00:00Z")
    g("merge", "-q", "--no-ff", "-m", "m", "a", when="2026-01-03T00:00:00Z")
    p = plan(repo, g, base, ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and p["undetermined"] == ["migrate_x.py", "migrate_y.py"]

    repo, g, base = mk("p2")                                            # (2) competing, later modified
    g("checkout", "-q", "-b", "a")
    (repo / "migrate_x.py").write_text("x = 'A'\n")
    (repo / "migrate_y.py").write_text("y\n")
    g("add", "-A")
    g("commit", "-q", "-m", "A", when="2026-01-01T00:00:00Z")
    (repo / "migrate_x.py").write_text("x = 'A2'\n")
    g("commit", "-q", "-am", "A modifies x", when="2026-01-02T00:00:00Z")
    g("checkout", "-q", "main")
    (repo / "migrate_x.py").write_text("x = 'B'\n")
    g("add", "-A")
    g("commit", "-q", "-m", "B", when="2026-01-03T00:00:00Z")
    g("merge", "-q", "--no-ff", "-m", "m", "a", when="2026-01-04T00:00:00Z", check=False)
    (repo / "migrate_x.py").write_text("x = 'A2'\n")
    g("add", "-A")
    g("commit", "-q", "-m", "m (keep A2)", when="2026-01-04T00:00:00Z")
    p = plan(repo, g, base, ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"]

    repo, g, base = mk("p3")                                            # (3) merge-only add, delete, merge re-add
    for i, files in enumerate((["migrate_x.py"], ["migrate_x.py", "migrate_y.py"])):
        g("checkout", "-q", "-b", f"s{i}")
        (repo / f"side{i}.txt").write_text(str(i))
        g("add", "-A")
        g("commit", "-q", "-m", f"side {i}", when=f"2026-01-0{2 * i + 1}T00:00:00Z")
        g("checkout", "-q", "main")
        g("merge", "-q", "--no-ff", "--no-commit", f"s{i}", when=f"2026-01-0{2 * i + 2}T00:00:00Z")
        for f in files:
            (repo / f).write_text(f"{f} {i}\n")
        g("add", "-A")
        g("commit", "-q", "-m", f"merge {i} (adds {files})", when=f"2026-01-0{2 * i + 2}T00:00:00Z")
        if i == 0:
            g("rm", "-q", "migrate_x.py")
            g("commit", "-q", "-m", "drop x", when="2026-01-02T12:00:00Z")
    p = plan(repo, g, base, ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"]


def test_codex_on_304_round_5_merge_re_add_after_an_ordinary_add_is_ambiguous(sandbox, monkeypatch):
    """Codex on #304, round 5 (verified on the old code: run [x, y]): migrate_x added by an ordinary commit, deleted,
    then re-added by a MERGE together with migrate_y. A merge adds a path when none of its parents had it, so that
    re-add is a second addition of x: ambiguous, nothing runs."""
    import os
    import subprocess

    import sp_deploy
    repo = sandbox / "g7"
    repo.mkdir()

    def g(*a, when=None):
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else None
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True, env=env).stdout.strip()
    g("init", "-q", "-b", "main")
    (repo / "r.txt").write_text("r")
    g("add", "-A")
    g("commit", "-q", "-m", "base", when="2026-01-01T00:00:00Z")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_x.py").write_text("x = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "x", when="2026-01-02T00:00:00Z")
    g("rm", "-q", "migrate_x.py")
    g("commit", "-q", "-m", "drop x", when="2026-01-03T00:00:00Z")
    g("checkout", "-q", "-b", "side")
    (repo / "s.txt").write_text("s")
    g("add", "-A")
    g("commit", "-q", "-m", "side", when="2026-01-04T00:00:00Z")
    g("checkout", "-q", "main")
    g("merge", "-q", "--no-ff", "--no-commit", "side")
    (repo / "migrate_x.py").write_text("x = 2\n")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "merge side, re-adding x with y", when="2026-01-05T00:00:00Z")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert plan["run"] == [] and "migrate_x.py" in plan["undetermined"]


def test_codex_on_304_round_6_a_rename_into_a_migration_name_is_an_addition(sandbox, monkeypatch):
    """Codex on #304, round 6 (verified on the old code: run [x, y]): migrate_x added, deleted, then a non-migration
    file RENAMED to migrate_x.py in the commit that adds migrate_y.py. With rename detection the log dropped that
    re-addition; with --no-renames it is a second addition of x: ambiguous, nothing runs."""
    import subprocess

    import sp_deploy
    repo = sandbox / "g8"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (repo / "notes_x.py").write_text("print('a staged body long enough for rename detection to pair it')\n" * 5)
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_x.py").write_text("x = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "x")
    g("rm", "-q", "migrate_x.py")
    g("commit", "-q", "-m", "drop x")
    g("mv", "notes_x.py", "migrate_x.py")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "rename notes into x, add y")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert plan["run"] == [] and "migrate_x.py" in plan["undetermined"]


def test_sweep_a_migration_renamed_from_an_in_range_migration_is_undetermined(sandbox, monkeypatch):
    """Sweep (Codex post-merge on #304, reproduced on main: run [y, x]): migrate_temp added, then migrate_y, then
    migrate_temp RENAMED to migrate_x. --no-renames placed x at the rename commit, after y, reversing their real
    order. A migration renamed from an in-range migration keeps the source's age: undetermined, nothing runs."""
    import subprocess

    import sp_deploy
    repo = sandbox / "g9"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (repo / "r.txt").write_text("r")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    (repo / "migrate_temp.py").write_text("print('the first migration body, long enough for rename detection')\n" * 5)
    g("add", "-A")
    g("commit", "-q", "-m", "temp")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "y")
    g("mv", "migrate_temp.py", "migrate_x.py")
    g("commit", "-q", "-m", "rename temp -> x")
    monkeypatch.setattr(c, "REPO", repo)
    plan = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert plan["run"] == [] and "migrate_x.py" in plan["undetermined"]
    assert len(plan["new"]) == len(set(plan["new"]))                     # listed once (Codex on #305)


def test_sweep_rename_chains_and_merge_result_renames_are_undetermined(sandbox, monkeypatch):
    """Codex on #305 (verified): (1) migrate_temp -> holding.py -> migrate_x (a chain through a non-migration
    name) and (2) a MERGE commit renaming a side branch's migrate_temp to migrate_x after main added migrate_y both
    planned run [y, x]. Rename chains are followed (merge diffs included via -m): x is undetermined."""
    import os
    import subprocess

    import sp_deploy
    body = "print('a migration body long enough for git rename detection to pair')\n" * 5

    def mk(name):
        repo = sandbox / name
        repo.mkdir()

        def g(*a, when=None, check=True):
            env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else None
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=check, capture_output=True, text=True, env=env).stdout.strip()
        g("init", "-q", "-b", "main")
        (repo / "r.txt").write_text("r")
        g("add", "-A")
        g("commit", "-q", "-m", "base", when="2026-01-01T00:00:00Z")
        return repo, g, g("rev-parse", "HEAD")

    repo, g, base = mk("c1")                                             # (1) chain through holding.py
    (repo / "migrate_temp.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "temp")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "y")
    g("mv", "migrate_temp.py", "holding.py")
    g("commit", "-q", "-m", "park")
    g("mv", "holding.py", "migrate_x.py")
    g("commit", "-q", "-m", "x")
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"] and len(p["new"]) == len(set(p["new"]))

    repo, g, base = mk("c2")                                             # (2) the rename happens in a merge
    g("checkout", "-q", "-b", "side")
    (repo / "migrate_temp.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "temp", when="2026-01-02T00:00:00Z")
    g("checkout", "-q", "main")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "y", when="2026-01-03T00:00:00Z")
    g("merge", "-q", "--no-ff", "--no-commit", "side", when="2026-01-04T00:00:00Z")
    g("mv", "migrate_temp.py", "migrate_x.py")
    g("commit", "-q", "-m", "merge side, renaming temp -> x", when="2026-01-04T00:00:00Z")
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"]


def test_sweep_low_similarity_moves_and_reused_intermediate_names(sandbox, monkeypatch):
    """Codex on #305 round 2 (verified): (1) migrate_temp MOVED AND REWRITTEN to migrate_x (below git's 50% rename
    similarity) after migrate_y planned run [y, x]: a migration added in the same commit (or merge-parent diff)
    that deletes a migration, or a path carrying one's age, is undetermined whatever the similarity. (2) A reused
    intermediate name never produces the wrong order [y, x]; since round 5 a range that deletes any migration is
    wholly undetermined, so the plan is left to the operator (conservative)."""
    import subprocess

    import sp_deploy
    body = "print('a migration body long enough for git rename detection to pair')\n" * 5

    def mk(name):
        repo = sandbox / name
        repo.mkdir()

        def g(*a):
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
        g("init", "-q", "-b", "main")
        (repo / "r.txt").write_text("r")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        return repo, g, g("rev-parse", "HEAD")

    def commit(g, repo, msg, add=(), rm=(), mv=()):
        for a, b in mv:
            g("mv", a, b)
        for name, text in add:
            (repo / name).write_text(text)
        for name in rm:
            g("rm", "-q", name)
        g("add", "-A")
        g("commit", "-q", "-m", msg)

    repo, g, base = mk("lo1")                                            # (1) move + rewrite
    commit(g, repo, "temp", add=[("migrate_temp.py", body)])
    commit(g, repo, "y", add=[("migrate_y.py", "y = 1\n")])
    commit(g, repo, "move and rewrite", mv=[("migrate_temp.py", "migrate_x.py")],
           add=[("migrate_x.py", "completely = 'different'\n")])
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"] and len(p["new"]) == len(set(p["new"]))

    repo, g, base = mk("lo2")                                            # (1b) through a non-migration name
    commit(g, repo, "temp", add=[("migrate_temp.py", body)])
    commit(g, repo, "y", add=[("migrate_y.py", "y = 1\n")])
    commit(g, repo, "park", mv=[("migrate_temp.py", "holding.py")])
    commit(g, repo, "move and rewrite", mv=[("holding.py", "migrate_x.py")],
           add=[("migrate_x.py", "completely = 'different'\n")])
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"]

    repo, g, base = mk("lo3")                                            # (2) a reused name never reaches back
    commit(g, repo, "holding", add=[("holding.py", body)])
    base = g("rev-parse", "HEAD")
    commit(g, repo, "x", mv=[("holding.py", "migrate_x.py")])
    commit(g, repo, "y", add=[("migrate_y.py", "y = 1\n")])
    commit(g, repo, "temp", add=[("migrate_temp.py", body.replace("long", "lengthy"))])
    commit(g, repo, "park temp", mv=[("migrate_temp.py", "holding.py")])
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    # round 5 replaced per-path lineage with the whole-plan rule: this range deletes migrate_temp, so the plan is
    # undetermined (conservative: the operator orders [x, y] by hand) — never [y, x]
    assert p["run"] == [] and p["lineage_unknown"] and "migrate_x.py" in p["undetermined"]


def test_sweep_a_merge_replay_addition_keeps_the_carried_age(sandbox, monkeypatch):
    """Codex on #305 round 3 (verified): a side branch renames migrate_temp -> holding.py and is merged unchanged
    after main added migrate_y; the merge's first-parent diff replays holding.py as a plain addition, which wiped
    the side branch's taint, so a later holding.py -> migrate_x planned run [y, x]. A replayed addition never
    clears a carried age: taint only accumulates."""
    import subprocess

    import sp_deploy
    body = "print('a migration body long enough for git rename detection to pair')\n" * 5
    repo = sandbox / "rp"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (repo / "r.txt").write_text("r")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD")
    g("checkout", "-q", "-b", "side")
    (repo / "migrate_temp.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "temp")
    g("mv", "migrate_temp.py", "holding.py")
    g("commit", "-q", "-m", "park")
    g("checkout", "-q", "main")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "y")
    g("merge", "-q", "--no-ff", "-m", "merge side", "side")
    g("mv", "holding.py", "migrate_x.py")
    g("commit", "-q", "-m", "x")
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"] and len(p["new"]) == len(set(p["new"]))


def test_sweep_replacement_destinations_and_in_range_copies(sandbox, monkeypatch):
    """Codex on #305 round 4 (verified): (1) a placeholder migrate_x is replaced by moving migrate_temp onto it
    (`--no-renames` reports D temp + M x), which planned run [y, x]; a MODIFIED path in a diff that deletes a
    migration carries its age too. (2) migrate_temp copied UNCHANGED to migrate_x inside the range planned
    [temp, y, x], running one one-shot twice; new migrations with identical content are undetermined."""
    import subprocess

    import sp_deploy
    body = "print('a migration body long enough for git rename detection to pair')\n" * 5

    def mk(name):
        repo = sandbox / name
        repo.mkdir()

        def g(*a):
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
        g("init", "-q", "-b", "main")
        (repo / "r.txt").write_text("r")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        return repo, g, g("rev-parse", "HEAD")

    def commit(g, repo, msg, files):
        for name, text in files:
            (repo / name).write_text(text)
        g("add", "-A")
        g("commit", "-q", "-m", msg)

    repo, g, base = mk("rd")                                             # (1) move onto a placeholder
    commit(g, repo, "temp", [("migrate_temp.py", body)])
    commit(g, repo, "y", [("migrate_y.py", "y = 1\n")])
    commit(g, repo, "placeholder x", [("migrate_x.py", "pass\n")])
    g("rm", "-q", "migrate_x.py")
    g("mv", "migrate_temp.py", "migrate_x.py")
    g("commit", "-q", "-m", "replace x with temp")
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"]

    repo, g, base = mk("cp")                                             # (2) unchanged copy, source kept
    commit(g, repo, "temp", [("migrate_temp.py", body)])
    commit(g, repo, "y", [("migrate_y.py", "y = 1\n")])
    commit(g, repo, "copy temp -> x", [("migrate_x.py", body)])
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_temp.py", "migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and "migrate_x.py" in p["undetermined"]


def test_sweep_any_migration_deletion_makes_the_whole_plan_undetermined(sandbox, monkeypatch):
    """Codex on #305 round 5 (verified): (1) a pre-range migrate_old moved AND rewritten to migrate_x was listed
    as new; (2) a split copy-and-delete (copy temp -> holding.py, delete temp, rename holding.py -> migrate_x)
    planned run [y, x]. Lineage through deletions is not reconstructed path by path any more: a range in which ANY
    diff deletes a migration makes every new migration undetermined, and the deploy prompt says some may already
    have run under another name."""
    import subprocess

    import sp_deploy
    body = "print('a migration body long enough for git rename detection to pair')\n" * 5

    def mk(name):
        repo = sandbox / name
        repo.mkdir()

        def g(*a):
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
        g("init", "-q", "-b", "main")
        (repo / "r.txt").write_text("r")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        return repo, g

    repo, g = mk("pre")                                                  # (1) pre-range rename + rewrite
    (repo / "migrate_old.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "old")
    base = g("rev-parse", "HEAD")
    g("mv", "migrate_old.py", "migrate_x.py")
    (repo / "migrate_x.py").write_text("completely = 'different'\n")
    g("add", "-A")
    g("commit", "-q", "-m", "move and rewrite")
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_old.py", "migrate_x.py"])
    assert p["run"] == [] and p["undetermined"] == ["migrate_x.py"] and p["lineage_unknown"]
    assert p["deleted_migrations"] == ["migrate_old.py"]                 # surfaced (Codex on #305, round 7)

    repo, g = mk("split")                                                # (2) split copy-and-delete
    base = g("rev-parse", "HEAD")
    (repo / "migrate_temp.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "temp")
    (repo / "migrate_y.py").write_text("y = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "y")
    (repo / "holding.py").write_text(body)
    g("add", "-A")
    g("commit", "-q", "-m", "copy temp -> holding")
    g("rm", "-q", "migrate_temp.py")
    g("commit", "-q", "-m", "delete temp")
    g("mv", "holding.py", "migrate_x.py")
    g("commit", "-q", "-m", "x")
    monkeypatch.setattr(c, "REPO", repo)
    p = sp_deploy.migration_plan(base, g("rev-parse", "HEAD"), ["migrate_x.py", "migrate_y.py"])
    assert p["run"] == [] and set(p["undetermined"]) == {"migrate_x.py", "migrate_y.py"} and p["lineage_unknown"]


def test_sweep_a_deletion_only_range_warns_on_dry_run_and_deploy(sandbox, monkeypatch, capsys):
    """Codex on #305 round 6 (verified): a range that ONLY deletes a migration set lineage_unknown with nothing
    undetermined, and the warning was nested in the undetermined message, so neither the deploy nor the dry run
    said anything about it. The deletion warning now prints on its own, and the dry run previews it."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    (origin / "migrate_old.py").write_text("1")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "base")
    g(origin, "tag", "v1.0.0")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    g(origin, "rm", "-q", "migrate_old.py")
    g(origin, "commit", "-q", "-m", "retire old")
    g(origin, "tag", "v1.0.1")
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setenv("SP_RECEIPTS", str(sandbox / "log" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    assert sp_deploy.main(["--tag", "v1.0.1", "--dry-run"]) == 0
    assert "DELETES migration(s) ['migrate_old.py']" in capsys.readouterr().out
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 0
    out = capsys.readouterr().out
    assert "! this range DELETES migration(s) ['migrate_old.py']" in out and "not determinable" not in out
    # round 7: the advice names the deleted paths and a --no-renames listing, never --follow alone (a rewritten
    # move is invisible to --follow)
    assert "--no-renames --name-status" in out and "git log --follow" not in out


def test_deploy_installs_requirements_when_they_changed(sandbox, monkeypatch, capsys):
    """ARCHITECT 2026-10-06 (the host lacked `cryptography` after v1.2.3): `pip install -r requirements.txt` runs,
    printed and receipted, from a WORKTREE of the target and BEFORE the checkout, when requirements.txt changed in
    the range OR this host has no successful install receipt for the target's file (the bootstrap: the deploy that
    ships this code still ran the old deployer — Codex on #310). A failed install refuses the deploy and says the
    venv may be partially updated; a target without the file installs nothing and says so; relative -r includes
    resolve as in the checkout."""
    import pathlib
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(msg, tag, files=(), rm=()):
        for name, text in files:
            (origin / name).parent.mkdir(parents=True, exist_ok=True)
            (origin / name).write_text(text)
        for name in rm:
            g(origin, "rm", "-q", name)
        g(origin, "add", "-A")
        g(origin, "commit", "-q", "-m", msg)
        g(origin, "tag", tag)
    g(origin, "init", "-q", "-b", "main")
    commit("base", "v1.0.0", [("requirements.txt", "requests>=2.31.0\n")])
    commit("plain", "v1.0.1", [("a.txt", "no requirements change")])
    commit("plain again", "v1.0.2", [("b.txt", "still none")])
    commit("add cryptography via an include", "v1.0.3",
           [("requirements.txt", "-r reqs/base.txt\ncryptography>=41.0.0\n"), ("reqs/base.txt", "requests\n")])
    commit("bump only the included file", "v1.0.4", [("reqs/base.txt", "requests>=2.32\n")])
    commit("drop requirements.txt", "v1.0.5", rm=["requirements.txt", "reqs/base.txt"])
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", repo)
    log = sandbox / "log" / "receipts.jsonl"
    monkeypatch.setenv("SP_RECEIPTS", str(log))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    calls, rc = [], {"v": 0}

    def fake_pip(cmd, cwd):
        req = pathlib.Path(cwd) / cmd[-1]
        inc = pathlib.Path(cwd) / "reqs" / "base.txt"
        calls.append((cmd, req.read_text(), inc.exists(), pathlib.Path(cwd) != repo, g(repo, "rev-parse", "HEAD")))
        return rc["v"]
    monkeypatch.setattr(sp_deploy, "_pip_run", fake_pip)

    def recs(kind):
        return [json.loads(x) for x in log.read_text().splitlines() if json.loads(x)["kind"] == kind]
    # bootstrap: no install receipt on this host yet -> installs although the range did not change the file
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 0 and len(calls) == 1
    assert "no matching install record" in capsys.readouterr().out
    # stamped: unchanged range and a receipt for this exact file -> nothing
    assert sp_deploy.main(["--tag", "v1.0.2"]) == 0 and len(calls) == 1
    capsys.readouterr()
    assert sp_deploy.main(["--tag", "v1.0.3", "--dry-run"]) == 0 and len(calls) == 1
    assert "changed in this range (reqs/base.txt, requirements.txt): would run" in capsys.readouterr().out
    v102 = g(repo, "rev-parse", "HEAD")
    rc["v"] = 1                                                          # failed install: refused, code unmoved
    assert sp_deploy.main(["--tag", "v1.0.3"]) == 1 and g(repo, "rev-parse", "HEAD") == v102
    assert "PARTIALLY updated" in capsys.readouterr().out
    assert "error" not in recs("deploy_requirements")[-1]                # git's worktree chatter is not pip's error
    rc["v"] = 0
    assert sp_deploy.main(["--tag", "v1.0.3"]) == 0
    cmd, body, include_there, in_worktree, head = calls[-1]
    assert cmd[-3:] == ["install", "-r", "requirements.txt"] and "cryptography" in body
    assert include_there and in_worktree and head == v102                 # target tree, before the checkout
    assert "requirements installed (requirements.txt changed in this range" in capsys.readouterr().out
    assert [r["exit"] for r in recs("deploy_requirements")] == [0, 1, 0] and recs("deploy")[-1]["requirements_installed"]
    assert len(g(repo, "worktree", "list").splitlines()) == 1             # the temporary worktree is gone
    # Codex on #310: an INCLUDED file changing alone still installs; the install record survives log rotation
    log.rename(log.with_suffix(".jsonl.1"))                              # logrotate: a fresh, empty receipts log
    assert sp_deploy.main(["--tag", "v1.0.4"]) == 0 and len(calls) == 4
    assert "changed in this range (reqs/base.txt)" in capsys.readouterr().out
    log.rename(log.with_suffix(".jsonl.2"))
    g(repo, "checkout", "-q", "--detach", "v1.0.3")                      # back to an older, already-installed tree
    (sandbox / "log" / "requirements.installed").write_text(
        sp_deploy._fingerprint(sp_deploy.requirements_inputs("v1.0.4")) + "\n")
    assert sp_deploy.requirements_plan(g(repo, "rev-parse", "v1.0.4"), []) == (None, None)   # stamped: no reinstall
    g(repo, "checkout", "-q", "--detach", "v1.0.4")
    # a target without requirements.txt: nothing installed, said and receipted, no traceback
    assert sp_deploy.main(["--tag", "v1.0.5"]) == 0 and len(calls) == 4
    assert "removed in the target: nothing installed" in capsys.readouterr().out
    assert recs("deploy_requirements")[-1]["skipped"] == "requirements.txt removed in the target"


def _req_repo(sandbox, monkeypatch, name):
    import os
    import subprocess
    repo = sandbox / name
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(files=(), links=()):
        for fname, text in files:
            (repo / fname).parent.mkdir(parents=True, exist_ok=True)
            (repo / fname).write_text(text)
        for fname, target in links:
            (repo / fname).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, repo / fname)
        g("add", "-A")
        g("commit", "-q", "-m", "x")
        return g("rev-parse", "HEAD")
    g("init", "-q", "-b", "main")
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setenv("SP_RECEIPTS", str(sandbox / f"log-{name}" / "receipts.jsonl"))
    return repo, g, commit


def test_requirements_allowlist_refuses_everything_but_plain_files(sandbox, monkeypatch):
    """Codex on #310, rounds 3-6: every pip feature whose input the fingerprint could miss (continuations, env vars,
    editables, local paths and archives, --find-links, `name @ url`, other options, an include not reachable as a
    tracked file — e.g. through a symlinked DIRECTORY) refuses the deploy; plain specifiers, comments (a comment
    ending in a backslash does not continue), -r/-c includes and FILE symlinks are fingerprinted. The repo's own
    requirements.txt is plain."""
    import sp_deploy
    repo, g, commit = _req_repo(sandbox, monkeypatch, "allow")
    ok = commit([("requirements.txt", "# deps \\\n-r reqs/current.txt\nrequests>=2.31  # pinned\n"
                                      "uvicorn[standard]>=0.27.0\nnumpy>=1.26; python_version > '3'\n"),
                 ("shared/base.txt", "click\n")], links=[("reqs/current.txt", "../shared/base.txt")])
    inputs, problems = sp_deploy.requirements_scan(ok)
    assert problems == [] and {"reqs/current.txt", "shared/base.txt"} <= set(inputs)
    two = commit([("shared/base.txt", "click>=8\n")])
    assert sp_deploy.requirements_plan(two, ["shared/base.txt"])[1] == "changed in this range (shared/base.txt)"
    for bad in ("requests \\", "-r ${REQ_DIR}/base.txt", "-e .", "./pkg", "vendor/pkg", "pkg.whl",
                "--find-links wheels", "pkg @ file:///opt/pkg", "pkg @ https://x/y.whl", "--index-url https://x",
                "-r missing.txt"):
        rev = commit([("requirements.txt", f"{bad}\nrequests\n")])
        blob, reason = sp_deploy.requirements_plan(rev, ["requirements.txt"])
        assert blob is None and reason.startswith(sp_deploy.REFUSE), (bad, reason)
    rev = commit([("requirements.txt", "-r reqs/cur/base.txt\n"), ("reqs/v1/base.txt", "a\n")],
                 links=[("reqs/cur", "v1")])                                 # a symlinked DIRECTORY component
    assert sp_deploy.requirements_plan(rev, ["requirements.txt"])[1].startswith(sp_deploy.REFUSE)
    real = Path(__file__).resolve().parents[1] / "requirements.txt"
    assert all(sp_deploy._classify(ln)[0] in ("blank", "spec") for ln in real.read_text().splitlines())


def test_requirements_record_lives_in_the_venv_and_names_its_destination(sandbox, monkeypatch):
    """Codex on #310: the install record lives INSIDE the venv (a recreated venv has none, inode reuse or not), and
    the fingerprint names the destination (a venv replacing the no-venv fallback reinstalls)."""
    import shutil

    import sp_deploy
    repo, g, commit = _req_repo(sandbox, monkeypatch, "venvrec")
    one = commit([("requirements.txt", "requests\n")])
    no_venv = sp_deploy._fingerprint(sp_deploy.requirements_inputs(one))
    (repo / "venv").mkdir()
    (repo / "venv" / "pyvenv.cfg").write_text("home = /usr\n")
    fp = sp_deploy._fingerprint(sp_deploy.requirements_inputs(one))
    assert fp != no_venv and sp_deploy.requirements_state_path() == repo / "venv" / ".sp-requirements.installed"
    sp_deploy.requirements_state_path().write_text(fp + "\n")
    assert sp_deploy.requirements_plan(one, []) == (None, None)
    shutil.rmtree(repo / "venv")
    (repo / "venv").mkdir()
    (repo / "venv" / "pyvenv.cfg").write_text("home = /usr\n")
    assert sp_deploy.requirements_plan(one, [])[0] is not None


def test_deploy_preflights_checkout_blockers_and_receipts_pip_launch_failures(sandbox, monkeypatch, capsys):
    """Codex on #310 round 6: (1) an untracked host file where the target adds a tracked one would fail the checkout
    AFTER pip installed: refused before installing, receipted; (2) a pip launcher that cannot execute (OSError) is a
    receipted failed install, not a traceback."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    (origin / "requirements.txt").write_text("requests\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "base")
    g(origin, "tag", "v1.0.0")
    (origin / "requirements.txt").write_text("requests\ncryptography\n")
    (origin / "newfile.py").write_text("x = 1\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "adds")
    g(origin, "tag", "v1.0.1")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", repo)
    log = sandbox / "log" / "receipts.jsonl"
    monkeypatch.setenv("SP_RECEIPTS", str(log))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    calls = []
    monkeypatch.setattr(sp_deploy, "_pip_run", lambda cmd, cwd: calls.append(cmd) or 0)
    (repo / "newfile.py").write_text("untracked host copy\n")                   # (1)
    before = g(repo, "rev-parse", "HEAD")
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1 and calls == [] and g(repo, "rev-parse", "HEAD") == before
    assert "deploy refused before anything was installed" in capsys.readouterr().out
    assert "untracked files block the checkout" in json.loads(log.read_text().splitlines()[-1])["error"]
    (repo / "newfile.py").unlink()
    monkeypatch.undo()                                                         # (2): the real _pip_run
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setenv("SP_RECEIPTS", str(log))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    monkeypatch.setattr(sp_deploy, "pip_command", lambda: [str(sandbox / "no-such-pip")])
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1 and g(repo, "rev-parse", "HEAD") == before
    recs = [json.loads(x) for x in log.read_text().splitlines()]
    assert [r for r in recs if r["kind"] == "deploy_requirements"][-1]["exit"] == 127
    assert "could not run" in capsys.readouterr().out


def test_requirements_round_seven_ack_preflight_state_errors_and_venv_upgrade(sandbox, monkeypatch, capsys):
    """Codex on #310 round 7 (verified): (1) a release the allowlist refuses could never deploy: the by-hand install
    is acknowledged with --requirements-installed-by-hand (receipted, recorded), and later deploys of the same
    requirements are not refused again; (2) the preflight sees a RENAMED destination and an untracked file at an
    ANCESTOR path; (3) an install record that cannot be written after pip succeeded is a receipted refusal, not a
    traceback; (4) the venv's Python version is part of the identity (`venv --upgrade`)."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(tag, files=(), mv=()):
        for a, b in mv:
            g(origin, "mv", a, b)
        for name, text in files:
            (origin / name).parent.mkdir(parents=True, exist_ok=True)
            (origin / name).write_text(text)
        g(origin, "add", "-A")
        g(origin, "commit", "-q", "-m", tag)
        g(origin, "tag", tag)
    g(origin, "init", "-q", "-b", "main")
    commit("v1.0.0", [("requirements.txt", "requests\n"), ("old.py", "x = 1\n" * 20)])
    commit("v1.0.1", [("requirements.txt", "requests\n--index-url https://example.invalid/simple\n")],
           mv=[("old.py", "moved.py")])
    commit("v1.0.2", [("pkg/new.py", "y = 2\n"), ("c.txt", "change\n")])
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", repo)
    log = sandbox / "log" / "receipts.jsonl"
    monkeypatch.setenv("SP_RECEIPTS", str(log))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    calls = []
    monkeypatch.setattr(sp_deploy, "_pip_run", lambda cmd, cwd: calls.append(cmd) or 0)

    def recs():
        return [json.loads(x) for x in log.read_text().splitlines()]
    (repo / "moved.py").write_text("untracked\n")                                 # (2) renamed destination
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1 and "moved.py" in recs()[-1]["error"] and calls == []
    (repo / "moved.py").unlink()
    capsys.readouterr()
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1                                # (1) refused by the allowlist
    assert "--requirements-installed-by-hand" in capsys.readouterr().out and calls == []
    assert sp_deploy.main(["--tag", "v1.0.1", "--requirements-installed-by-hand"]) == 0 and calls == []
    ack = [r for r in recs() if r["kind"] == "deploy_requirements"][-1]
    assert ack["manual"] is True and ack["exit"] == 0 and recs()[-1]["kind"] == "deploy"
    assert sp_deploy.requirements_plan(g(repo, "rev-parse", "v1.0.1"), []) == (None, None)   # this release: ack'd
    # round 8: the acknowledgement is bound to the release, so the NEXT release asks again (local inputs could change)
    assert sp_deploy.requirements_plan(g(repo, "rev-parse", "v1.0.2"), ["c.txt"])[1].startswith(sp_deploy.REFUSE)
    (repo / "pkg").write_text("an untracked FILE where v1.0.2 adds a directory\n")      # (2) ancestor
    assert sp_deploy.main(["--tag", "v1.0.2"]) == 1 and "pkg/new.py" in recs()[-1]["error"]
    (repo / "pkg").unlink()
    (sandbox / "log" / "requirements.installed").unlink()                          # (3) force an install whose
    monkeypatch.setattr(sp_deploy, "record_installed", lambda fp: "OSError: read-only")   # record cannot be written
    head = g(repo, "rev-parse", "HEAD")
    assert sp_deploy.main(["--tag", "v1.0.2", "--requirements-installed-by-hand"]) == 1
    assert g(repo, "rev-parse", "HEAD") == head and "could not record" in capsys.readouterr().out
    (repo / "venv").mkdir()                                                        # (4) venv --upgrade
    (repo / "venv" / "pyvenv.cfg").write_text("home = /usr\nversion = 3.11.9\n")
    first = sp_deploy._environment_id()
    (repo / "venv" / "pyvenv.cfg").write_text("home = /usr\nversion = 3.12.4\n")
    assert first != sp_deploy._environment_id()
    # (3) also on the pip path: pip succeeded, the record failed -> state_error in the receipt (main refuses on it)
    rec = sp_deploy.install_requirements("v1.0.0", g(repo, "rev-parse", "v1.0.0"), "fp", "test")
    assert rec["exit"] == 0 and rec["state_error"] == "OSError: read-only"


def test_requirements_round_eight_dry_run_dir_to_file_and_encodings(sandbox, monkeypatch, capsys):
    """Codex on #310 round 8 (verified): (1) --dry-run honours --requirements-installed-by-hand; (2) a tracked
    directory the target replaces with a file is not a checkout blocker; (3) a requirements file that is not UTF-8
    text is a receipted refusal, not a traceback."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    (origin / "requirements.txt").write_text("requests\n")
    (origin / "tool").mkdir()
    (origin / "tool" / "a.py").write_text("a = 1\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "base")
    g(origin, "tag", "v1.0.0")
    g(origin, "rm", "-q", "-r", "tool")
    (origin / "tool").write_text("now a file\n")                                 # (2) dir -> file
    (origin / "requirements.txt").write_bytes("requests\n# caf\xe9\n".encode("latin-1"))   # (3) not UTF-8
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "replace")
    g(origin, "tag", "v1.0.1")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", repo)
    log = sandbox / "log" / "receipts.jsonl"
    monkeypatch.setenv("SP_RECEIPTS", str(log))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    monkeypatch.setattr(sp_deploy, "_pip_run", lambda cmd, cwd: 0)
    blob, reason = sp_deploy.requirements_plan(g(repo, "rev-parse", "v1.0.1"), ["requirements.txt"])
    assert blob is None and reason.startswith(sp_deploy.REFUSE) and "UTF-8" in reason                   # (3)
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1
    out = capsys.readouterr().out
    assert "untracked" not in out and "deploy refused" in out                     # (2): refused for (3), not (2)
    assert sp_deploy.main(["--tag", "v1.0.1", "--dry-run", "--requirements-installed-by-hand"]) == 0   # (1)
    assert "RECORDED as installed by hand" in capsys.readouterr().out
    assert sp_deploy.main(["--tag", "v1.0.1", "--requirements-installed-by-hand"]) == 0
    assert (repo / "tool").is_file()


def test_requirements_round_nine_untracked_child_and_external_venv_record(sandbox, monkeypatch, tmp_path):
    """Codex on #310 round 9 (verified): (1) a tracked directory the target replaces with a file is a blocker when
    it holds an UNTRACKED file (git refuses to lose it); (2) without a repo venv, a deployer running from another
    virtualenv keeps its install record inside that environment, so recreating it drops the record."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "origin", sandbox / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    (origin / "tool").mkdir()
    (origin / "tool" / "a.py").write_text("a = 1\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "base")
    g(origin, "tag", "v1.0.0")
    g(origin, "rm", "-q", "-r", "tool")
    (origin / "tool").write_text("now a file\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "replace")
    g(origin, "tag", "v1.0.1")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", repo)
    (repo / "tool" / "local.cfg").write_text("host-only\n")                    # (1) untracked child
    before = g(repo, "rev-parse", "HEAD")
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1 and g(repo, "rev-parse", "HEAD") == before
    (repo / "tool" / "local.cfg").unlink()
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 0 and (repo / "tool").is_file()
    ext = tmp_path / "admin-venv"                                                # (2)
    monkeypatch.setattr(sys, "prefix", str(ext))
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    assert sp_deploy.requirements_state_path() == ext / ".sp-requirements.installed"


def test_requirements_round_ten(sandbox, monkeypatch, tmp_path):
    """Codex on #310 round 10 (verified): (1) a symlinked directory inside a replaced tracked directory is an
    untracked child; (2) a repo venv without a pip script installs via its own python, never the system pip;
    (3) a failed pip run drops the old install record; (4) the venv's system-site-packages mode is part of its
    identity; (5) a missing TMPDIR is a receipted failure; (6) per-requirement options (--config-settings) are
    refused; (7) a matching install record satisfies a range that touched the inputs (retry after a failed
    checkout)."""
    import os
    import subprocess
    import tempfile

    import sp_deploy
    repo, g, commit = _req_repo(sandbox, monkeypatch, "r10")
    one = commit([("requirements.txt", "requests\n")])
    (repo / "venv" / "bin").mkdir(parents=True)                                  # (2)
    (repo / "venv" / "pyvenv.cfg").write_text("home = /usr\nversion = 3.11.9\ninclude-system-site-packages = false\n")
    assert sp_deploy.pip_command() == [str(repo / "venv" / "bin" / "python"), "-m", "pip"]
    plain = sp_deploy._environment_id()                                          # (4)
    (repo / "venv" / "pyvenv.cfg").write_text("home = /usr\nversion = 3.11.9\ninclude-system-site-packages = true\n")
    assert sp_deploy._environment_id() != plain
    for bad in ("pkg>=1 --config-settings=key=value", "pkg>=1 -C key=value"):     # (6)
        assert sp_deploy._classify(bad)[0] == "refuse", bad
    assert sp_deploy._classify("pkg==1.0 --hash=sha256:" + "0" * 64)[0] == "spec"
    fp = sp_deploy._fingerprint(sp_deploy.requirements_inputs(one))              # (7)
    sp_deploy.requirements_state_path().write_text(fp + "\n")
    assert sp_deploy.requirements_plan(one, ["requirements.txt"]) == (None, None)
    monkeypatch.setattr(sp_deploy, "_pip_run", lambda cmd, cwd: 1)               # (3)
    rec = sp_deploy.install_requirements("vX", one, "other", "test")
    assert rec["exit"] == 1 and not sp_deploy.requirements_state_path().exists()
    def no_tmp(*a, **k):                                                         # (5)
        raise FileNotFoundError("no TMPDIR")
    monkeypatch.setattr(tempfile, "mkdtemp", no_tmp)
    rec = sp_deploy.install_requirements("vX", one, "fp", "test")
    assert rec["exit"] == 1 and "temporary directory" in rec["error"]
    monkeypatch.undo()
    # (1) a symlinked directory inside a tracked directory the target replaces with a file blocks the deploy
    origin, clone = sandbox / "o10", sandbox / "c10"
    origin.mkdir()

    def gg(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    gg(origin, "init", "-q", "-b", "main")
    (origin / "tool").mkdir()
    (origin / "tool" / "a.py").write_text("a\n")
    gg(origin, "add", "-A")
    gg(origin, "commit", "-q", "-m", "b")
    gg(origin, "tag", "v1.0.0")
    gg(origin, "rm", "-q", "-r", "tool")
    (origin / "tool").write_text("file\n")
    gg(origin, "add", "-A")
    gg(origin, "commit", "-q", "-m", "r")
    gg(origin, "tag", "v1.0.1")
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    gg(clone, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", clone)
    monkeypatch.setenv("SP_RECEIPTS", str(sandbox / "log10" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib10" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    os.symlink(str(tmp_path), clone / "tool" / "linked")
    head = gg(clone, "rev-parse", "HEAD")
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1 and gg(clone, "rev-parse", "HEAD") == head


def test_requirements_round_eleven(sandbox, monkeypatch, capsys):
    """Codex on #310 round 11 (verified): (1) an untracked tree of only EMPTY directories where the target adds a
    file is not a blocker; (2) the by-hand dry run keeps the migration warnings; (3) pip inputs set in the
    environment (PIP_CONSTRAINT, PIP_REQUIREMENT, ...) refuse auto-install; (4) a failed record write drops the old
    record."""
    import subprocess

    import sp_deploy
    origin, repo = sandbox / "o11", sandbox / "c11"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    (origin / "requirements.txt").write_text("requests\n")
    (origin / "migrate_old.py").write_text("x\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "b")
    g(origin, "tag", "v1.0.0")
    (origin / "requirements.txt").write_text("requests\n--index-url https://example.invalid/simple\n")
    (origin / "slot").write_text("a file\n")
    g(origin, "rm", "-q", "migrate_old.py")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "n")
    g(origin, "tag", "v1.0.1")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.0.0")
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setenv("SP_RECEIPTS", str(sandbox / "log11" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(sandbox / "lib11" / "db.lock"))
    monkeypatch.setattr(c, "HOST_ENV", sandbox / "no-host.env")
    (repo / "slot" / "empty" / "deeper").mkdir(parents=True)                    # (1) only empty directories
    assert sp_deploy.main(["--tag", "v1.0.1", "--dry-run", "--requirements-installed-by-hand"]) == 0   # (2)
    out = capsys.readouterr().out
    assert "RECORDED as installed by hand" in out and "DELETES migration(s) ['migrate_old.py']" in out
    assert sp_deploy.main(["--tag", "v1.0.1", "--requirements-installed-by-hand"]) == 0 and (repo / "slot").is_file()
    one = g(repo, "rev-parse", "HEAD")                                           # (3)
    sp_deploy.requirements_state_path().unlink()                                 # (not the by-hand ack above)
    monkeypatch.setenv("PIP_CONSTRAINT", "constraints.txt")
    assert "environment sets PIP_CONSTRAINT" in sp_deploy.requirements_plan(one, ["requirements.txt"])[1]
    monkeypatch.delenv("PIP_CONSTRAINT")
    state = sp_deploy.requirements_state_path()                                  # (4)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("old-release\n")
    real_write = Path.write_text

    def failing(self, *a, **k):
        if self == state:
            raise PermissionError("read-only")
        return real_write(self, *a, **k)
    monkeypatch.setattr(Path, "write_text", failing)
    assert sp_deploy.record_installed("new") and not state.exists()


# ------------------------------------- addendum 47 item 7(b): the closing watch's failure page, once in 30 minutes --

def test_47_7b_the_closing_watch_failure_page_goes_out_at_most_once_in_thirty_minutes(sandbox, monkeypatch):
    """"For sp-closing-watch.service, by name, the unit's failure page goes out at most once in thirty minutes.
    Every failure still writes its receipt, and a receipt whose page was held back says so and names the page it
    stands behind." """
    import sp_notify
    from datetime import timedelta
    sent = []
    monkeypatch.setattr(sp_notify, "journal_tail", lambda unit, n=30: ["Traceback: boom"])
    monkeypatch.setattr(sp_notify, "deliver", lambda kind, title, body, extra=None, **k: sent.append(title) or
                        c.append_receipt({"kind": kind, "title": title, "delivered": True, "channel": "ntfy",
                                          **(extra or {})}))
    for _ in range(3):
        assert sp_notify.main(["failure", "closing-watch"]) == 0
    rs = [r for r in receipts(sandbox) if r["kind"] == "failure"]
    assert len(rs) == 3 and len(sent) == 1                                     # every failure receipted, one page
    assert rs[1]["page_held_back"] is True and rs[1]["stands_behind"]["ts"] == rs[0]["ts"]
    assert rs[2]["stands_behind"]["ts"] == rs[0]["ts"] and rs[1]["unit"] == "sp-closing-watch.service"
    later = c.utc_now() + timedelta(minutes=31)
    assert sp_notify.held_behind("sp-closing-watch.service", now=later) is None   # 30 minutes on: the page goes out
    assert sp_notify.held_behind("sp-chain@window.service") is None                # by name: no other unit
    for _ in range(2):
        sp_notify.main(["failure", "window"])
    assert len(sent) == 3


def test_codex_4250381656_an_undelivered_failure_page_holds_nothing_back(sandbox, monkeypatch):
    """Codex on #457 (P1): a failure page ntfy did not accept (or no topic) did not go out; the next failure pages."""
    import sp_notify
    monkeypatch.setattr(sp_notify, "journal_tail", lambda unit, n=30: [])
    sent = []
    ok = {"v": False}
    monkeypatch.setattr(sp_notify, "deliver", lambda kind, title, body, extra=None, **k: sent.append(ok["v"]) or
                        c.append_receipt({"kind": kind, "title": title, "delivered": ok["v"], **(extra or {})}))
    sp_notify.main(["failure", "closing-watch"])
    sp_notify.main(["failure", "closing-watch"])                     # the first was not delivered: tries again
    assert sent == [False, False]
    ok["v"] = True
    sp_notify.main(["failure", "closing-watch"])
    sp_notify.main(["failure", "closing-watch"])                     # now one went out: held back
    assert sent == [False, False, True] and receipts(sandbox)[-1]["page_held_back"] is True
