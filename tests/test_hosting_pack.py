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
        for st in sp_run.resolve(name, {}, date(2026, 10, 9)):
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


def test_no_timer_in_reboot_buffer_and_targets_exist():
    days = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    for fname, (cals, unit) in _timers().items():
        assert cals, fname
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


def test_ncaa_timer_ships_enabled_in_runbook():
    rb = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    t11 = rb[rb.index("TIMERS=\""):rb.index("echo $TIMERS")]  # TIMERS + MLB_LAPTOP_ONLY
    assert "HELD_B4" not in rb  # B4 ruled: the model-bearing timers enable with the rest
    enabled = t11[:t11.index("MLB_LAPTOP_ONLY=")]
    for mlb in ("sp-mlb-morning.timer", "sp-mlb-preslate.timer", "sp-clv-capture.timer"):
        assert mlb not in enabled, f"{mlb} must stay OFF the host enable list (statsapi ASN block)"
    for f in (HOSTING / "systemd").glob("*.timer"):
        assert f.name in t11, f"{f.name} missing from the T11 enable list"


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
    # flat plan would add sync-odds-football + two Kalshi syncs
    assert plan["skipped_by_proximity"] == 3
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
    assert soccer == set(KalshiAdapter.SOCCER_GAME_SERIES)
    cli = _cli()
    for steps in chains.WINDOW_KALSHI.values():
        for st in steps:
            assert st[0] in cli.commands


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
                             "kickoff": 1, "t90_news": 0}
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
    assert rec["freshen_needed"] == [{"id": "1", "sport": "nfl", "competition": "NFL"}]
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
