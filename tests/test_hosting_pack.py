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
        for st in sp_run.resolve(name, {}, date(2026, 10, 9)) if not ch.get("fullseason") else []:
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
            mm = re.fullmatch(r"(?:([A-Za-z,]+) )?\*-\*-\* (\d\d):(\d\d):00 (\S+)", cal)
            assert mm, f"{fname}: unexpected calendar {cal!r}"
            hh, mi, tz = int(mm.group(2)), int(mm.group(3)), ZoneInfo(mm.group(4))
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
    t11 = rb[rb.index("TIMERS=\""):rb.index("echo $TIMERS")]
    assert "HELD_B4" not in rb  # B4 ruled: the model-bearing timers enable with the rest
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
