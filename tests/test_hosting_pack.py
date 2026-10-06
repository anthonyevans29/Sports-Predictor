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
    assert soccer == set(KalshiAdapter.SOCCER_GAME_SERIES) | set(KalshiAdapter.SOCCER_SERIES_DISCOVERY)
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
    assert ch["nfl-predict"]["steps"][0] == ["sync-injuries", "--competition", "NFL", "--season", "2026"]
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
    assert cals == ["Thu *-*-* 16:00:00 UTC", "Fri *-*-* 16:00:00 UTC", "Sat *-*-* 13:00:00 UTC"]


def test_ncaa_market_syncs_results_before_the_export():
    """ARCHITECT 2026-10-02 (#254): Thursday games read SCHEDULED in Friday's export — sync-matches NCAA
    (single-day calls, yesterday + today) runs before the export so finished games leave the window."""
    steps = chains.CHAINS["ncaa-market"]["steps"]
    assert [s[0] for s in steps] == ["sync-matches", "sync-matches", "sync-kalshi-ncaa", "export-fixtures"]
    for st, d in zip(steps[:2], ("{yesterday}", "{today}")):
        assert st == ["sync-matches", "--competition", "NCAA", "--season", "2026", "--date-from", d, "--date-to", d]
    assert "sync-matches" not in chains.UNMETERED


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