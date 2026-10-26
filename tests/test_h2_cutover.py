"""H2-PREP: deploy/hosting/sp_cutover.py (host cutover orchestrator) and
scripts/h2_dry_run.py, exercised without a host: a fake systemctl runner,
tmp dirs only (never data/), and the "real" host paths pinned to sandbox
files that must come out byte-identical."""
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))
sys.path.insert(0, str(ROOT / "scripts"))

import sp_backup  # noqa: E402
import sp_common as c  # noqa: E402
import sp_cutover  # noqa: E402
import sp_migrate  # noqa: E402

REAL_ENV_TEXT = "# real host.env (sandbox stand-in)\nSP_WRITER_OF_RECORD=laptop\nSP_SKIP_FAMILIES=MLB\nSP_EXPORTS_MIRROR_ROLE=host\n"


class FakeSystemctl:
    """Records calls; models timer state; never runs a process. Starting
    sp-backup.service runs the real sp_backup code against the current DB."""

    def __init__(self, active=(), fail_on=None):
        self.calls, self.active, self.fail_on = [], set(active), fail_on

    def __call__(self, argv):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        assert argv[0] == "systemctl", f"unexpected command {argv}"
        verb, units = argv[1], argv[2:]
        if self.fail_on == verb:
            return 1, "Failed: injected"
        if verb == "stop":
            self.active -= set(units)
        elif verb == "start":
            for u in units:
                if u == "sp-backup.service":
                    if sp_backup.run_backup("daily")["exit"]:
                        return 1, "backup failed"
                else:
                    self.active.add(u)
        elif verb == "is-active":
            st = ["active" if u in self.active else "inactive" for u in units]
            return (0 if all(s == "active" for s in st) else 3), "\n".join(st)
        elif verb == "list-units" and "--type=timer" in argv:   # as systemd lists them: --plain --no-legend
            return 0, "\n".join(f"{u} loaded active waiting Timer" for u in sorted(self.active)
                                if u.endswith(".timer"))
        return 0, ""

    def verbs(self):
        return [a[1] for a in self.calls]


@pytest.fixture(autouse=True)
def _restore_environ():
    """Real-mode main() calls load_host_env() (setdefault into os.environ)."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A laptop checkout + its pack, and 'real' host paths that must stay untouched."""
    laptop = tmp_path / "laptop"
    (laptop / "data").mkdir(parents=True)
    db = laptop / "data" / "sports.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE matches(id INTEGER); CREATE TABLE predictions(id INTEGER);"
                      "INSERT INTO matches VALUES (1),(2),(3); INSERT INTO predictions VALUES (9);")
    con.commit()
    con.close()
    (laptop / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    (laptop / "exports").mkdir()
    (laptop / "exports" / "nfl_predictions_2026-10-08.json").write_text("[1]")
    real_env = tmp_path / "real-etc" / "host.env"
    real_env.parent.mkdir()
    real_env.write_text(REAL_ENV_TEXT)
    real_receipts = tmp_path / "real-log" / "receipts.jsonl"
    monkeypatch.setattr(c, "REPO", laptop)
    monkeypatch.setattr(c, "HOST_ENV", real_env)
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    for k in ("SP_PARALLEL_MODE", "SP_WRITER_OF_RECORD", "SP_DESIGNATED_DAYS", "SP_TIMERS_ENABLED", "SP_SERVICE_USER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_RECEIPTS", str(real_receipts))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "real-lib" / "db.lock"))
    monkeypatch.setenv("SP_BACKUP_DIR", str(tmp_path / "real-backups"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(sp_cutover, "_euid", lambda: 1000)   # in-process path (CI may run as root)
    pk = tmp_path / "pack_20261008T0700"
    assert sp_migrate.pack(pk) == 0
    return {"tmp": tmp_path, "pack": pk, "laptop": laptop, "db": db, "real_env": real_env,
            "real_receipts": real_receipts}


def _lines(p):
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def _snapshot(w):
    return {"env": w["real_env"].read_bytes(), "receipts": w["real_receipts"].read_bytes(),
            "db": c.sha256_file(w["db"]), "etc": sorted(p.name for p in w["real_env"].parent.iterdir())}


def _dry(w, scratch, runner=None):
    return sp_cutover.main(["run", "--pack", str(w["pack"]), "--dry-run", "--scratch", str(scratch)],
                           runner=runner)


# ------------------------------------------------------------ dry run ----

def test_dry_run_full_sequence_passes_on_scratch_only(world, capsys):
    before = _snapshot(world)
    scratch = world["tmp"] / "scratch"
    fake = FakeSystemctl(active=sp_cutover.runbook_timers())
    assert _dry(world, scratch, fake) == 0
    out = capsys.readouterr().out
    assert "DRY-RUN PASS" in out and out.count("  receipt {") == 6

    rs = [r for r in _lines(scratch / "log" / "receipts.jsonl") if r["kind"] == "cutover"]
    assert [r["step"] for r in rs] == list(sp_cutover.STEPS)
    assert all(r["exit"] == 0 and r["dry_run"] is True for r in rs)
    summary = rs[-1]
    assert summary["s2_eq_s1"] and summary["r2_eq_r1"] and summary["flag"] == "SP_WRITER_OF_RECORD=host"
    man = json.loads((world["pack"] / "MANIFEST.json").read_text())
    assert summary["db_sha256"] == man["files"]["sports.db"]

    # the scratch env flipped, line-preserving; the old file kept beside it
    env = scratch / "etc" / "host.env"
    kept = list(env.parent.glob("host.env.pre-cutover-*"))
    assert len(kept) == 1
    old, new = kept[0].read_text().splitlines(), env.read_text().splitlines()
    changed = [(a, b) for a, b in zip(old, new) if a != b]
    assert len(old) == len(new) and changed == [("SP_WRITER_OF_RECORD=laptop", "SP_WRITER_OF_RECORD=host")]

    # installed into the SCRATCH checkout; rehearsal moved aside
    host_db = scratch / "repo" / "data" / "sports.db"
    assert c.table_counts(host_db) == {"matches": 3, "predictions": 1}
    assert list((scratch / "repo" / "data").glob("rehearsal_*.db"))
    # systemctl: stop before start; the backup unit last
    v = fake.verbs()
    assert v.index("stop") < v.index("start") and fake.calls[-1] == ["systemctl", "start", "sp-backup.service"]

    # real paths untouched, module state restored
    assert _snapshot(world) == before
    assert c.REPO == world["laptop"] and c.HOST_ENV == world["real_env"]
    assert os.environ["DATABASE_URL"] == f"sqlite:///{world['db']}"


def test_verify_fail_refuses_before_pause_and_never_flips(world, capsys):
    con = sqlite3.connect(world["pack"] / "sports.db")
    con.execute("INSERT INTO matches VALUES (4)")
    con.commit()
    con.close()
    scratch = world["tmp"] / "scratch"
    fake = FakeSystemctl(active=sp_cutover.runbook_timers())
    assert _dry(world, scratch, fake) == 1
    out = capsys.readouterr().out
    assert "REFUSED preflight" in out and "verify FAIL" in out and "FAIL at preflight" in out
    assert "stop" not in fake.verbs()                      # chains never paused
    env = scratch / "etc" / "host.env"
    assert "SP_WRITER_OF_RECORD=laptop" in env.read_text()
    assert not list(env.parent.glob("host.env.pre-cutover-*"))
    rs = [r for r in _lines(scratch / "log" / "receipts.jsonl") if r["kind"] == "cutover"]
    assert [(r["step"], r["exit"]) for r in rs] == [("preflight", 1)]


def test_scratch_under_data_refused(world):
    target = c.REPO / "data" / "h2scratch"
    with pytest.raises(SystemExit, match="law 5"):
        _dry(world, target)
    assert not target.exists()


def test_flag_mismatch_and_missing_pack_refused(world, capsys):
    with pytest.raises(SystemExit, match="flag mismatch"):
        sp_cutover.main(["run", "--pack", str(world["pack"]), "--dry-run"])
    with pytest.raises(SystemExit, match="flag mismatch"):
        sp_cutover.main(["run", "--pack", str(world["pack"]), "--scratch", str(world["tmp"] / "s")])
    with pytest.raises(SystemExit, match="flag mismatch"):
        sp_cutover.main(["flip", "--dry-run", "--scratch", str(world["tmp"] / "s")])
    assert sp_cutover.main(["run", "--pack", str(world["tmp"] / "nope"), "--dry-run",
                            "--scratch", str(world["tmp"] / "s2")], runner=FakeSystemctl()) == 1
    assert "missing pack" in capsys.readouterr().out


def test_non_empty_scratch_refused(world):
    s = world["tmp"] / "busy"
    s.mkdir()
    (s / "x").write_text("x")
    with pytest.raises(SystemExit, match="not empty"):
        _dry(world, s)


# ---------------------------------------------- real mode, fake runner ----

@pytest.fixture
def host(world, monkeypatch):
    """Real (non-dry) mode against sandbox host paths: a host checkout with a
    rehearsal DB, a host.env and a timers list — all under tmp."""
    h = world["tmp"] / "host"
    (h / "data").mkdir(parents=True)
    sqlite3.connect(h / "data" / "sports.db").close()
    monkeypatch.setattr(c, "REPO", h)
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/sports.db")
    timers = world["tmp"] / "timers.enabled"
    timers.write_text("sp-backup.timer sp-window.timer\nsp-mlb-history.timer\n")
    return {"h": h, "timers": timers}


# Addendum 79 item 4: NHL shot GATE streams, as `sp_cutover.py shot-gate` prints them. The laptop's numbers (#520:
# 1396/1396, 1394/1394) pass; the host's of 2026-10-14 (0/1396, 0/1394) do not. Addendum 80 item 3: the pack's DB (the
# laptop's) gates; the host's live DB is read for the record and never refuses.
PASS_GATE = {"db": "/home/sp/sp_pack/sports.db", "source": "pack", "bar": 95.0, "seasons": {
    "2024": {"games": 1396, "with_shots": 1396, "first": "2024-10-08", "last": "2025-06-17"},
    "2025": {"games": 1394, "with_shots": 1394, "first": "2025-10-07", "last": "2026-06-19"}}}
HOST_GATE = {**PASS_GATE, "db": "/opt/sports-predictor/data/sports.db", "source": "live",
             "seasons": {k: {**v, "with_shots": 0} for k, v in PASS_GATE["seasons"].items()}}


def _real(world, host, step="run", runner=None, shot=PASS_GATE, host_shot=PASS_GATE, seen=None):
    """`shot` is the pack's read (it gates), `host_shot` the host's live read (for the record)."""
    if runner is None:          # never the real systemctl in a test: the preflight reads the active timers (57.8)
        runner = FakeSystemctl(active=host["timers"].read_text().split())

    def read(ctx, pack):
        if seen is not None:
            seen.append(pack)
        return shot if pack else host_shot
    return sp_cutover.main([step, "--pack", str(world["pack"]), "--timers-file", str(host["timers"])],
                           runner=runner, shot_read=read)


def test_real_mode_sequence_with_fake_systemctl(world, host):
    fake = FakeSystemctl(active=host["timers"].read_text().split())
    assert _real(world, host, runner=fake) == 0
    env = world["real_env"].read_text()
    assert env == REAL_ENV_TEXT.replace("=laptop", "=host")
    kept = list(world["real_env"].parent.glob("host.env.pre-cutover-*"))
    assert len(kept) == 1 and kept[0].read_text() == REAL_ENV_TEXT
    rs = [r for r in _lines(world["real_receipts"]) if r["kind"] == "cutover"]
    assert [r["step"] for r in rs] == list(sp_cutover.STEPS)
    assert {r["cutover_id"] for r in rs} == {"pack_20261008T0700"}
    assert fake.active == set(host["timers"].read_text().split())


def test_flip_is_idempotent_when_already_host(world, host):
    world["real_env"].write_text("SP_WRITER_OF_RECORD=host\n")
    assert _real(world, host, step="flip") == 0
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "flip" and r["changed"] is False and r["before"] == "host"
    assert world["real_env"].read_text() == "SP_WRITER_OF_RECORD=host\n"


def test_flip_appends_when_absent_and_refuses_ambiguity(world, host):
    world["real_env"].write_text("SP_SKIP_FAMILIES=MLB")       # no trailing newline
    assert _real(world, host, step="flip") == 0
    assert world["real_env"].read_text() == "SP_SKIP_FAMILIES=MLB\nSP_WRITER_OF_RECORD=host\n"
    world["real_env"].write_text("SP_WRITER_OF_RECORD=host\nexport SP_WRITER_OF_RECORD=laptop\n")
    assert _real(world, host, step="flip") == 1
    assert _lines(world["real_receipts"])[-1]["refused"].startswith("SP_WRITER_OF_RECORD set on 2 lines")


def test_preflight_refuses_unknown_flag_value_and_bad_timer_names(world, host):
    world["real_env"].write_text("SP_WRITER_OF_RECORD=both\n")
    assert _real(world, host, step="preflight") == 1
    assert "not one of" in _lines(world["real_receipts"])[-1]["refused"]
    world["real_env"].write_text(REAL_ENV_TEXT)
    host["timers"].write_text("sp-window.timer ; rm -rf /\n")
    assert _real(world, host, step="preflight") == 1
    assert "non-timer names" in _lines(world["real_receipts"])[-1]["refused"]


def test_pause_failure_refuses_and_install_never_runs(world, host):
    fake = FakeSystemctl(active=host["timers"].read_text().split(), fail_on="stop")
    rehearsal = c.sha256_file(host["h"] / "data" / "sports.db")
    assert _real(world, host, runner=fake) == 1
    assert c.sha256_file(host["h"] / "data" / "sports.db") == rehearsal
    assert world["real_env"].read_text() == REAL_ENV_TEXT
    steps = [(r["step"], r["exit"]) for r in _lines(world["real_receipts"]) if r["kind"] == "cutover"]
    assert steps == [("preflight", 0), ("pause", 1)]


def test_receipt_step_refuses_without_the_prior_steps(world, host):
    assert _real(world, host, step="receipt") == 1
    assert "no successful 'preflight'" in _lines(world["real_receipts"])[-1]["refused"]


# --------------------------------------------- operator script + docs ----

def test_h2_dry_run_script_passes(tmp_path, monkeypatch, capsys):
    import h2_dry_run
    monkeypatch.setattr(sp_cutover, "_euid", lambda: 1000)
    saved = (c.REPO, c.HOST_ENV, dict(os.environ))
    assert h2_dry_run.main(["--workdir", str(tmp_path / "w")]) == 0
    out = capsys.readouterr().out
    assert "DRY-RUN PASS" in out and "H2 DRY RUN: PASS" in out and "CLEAN (1 compared)" in out
    assert (c.REPO, c.HOST_ENV, dict(os.environ)) == saved


def test_runbook_names_waivers_and_is_linked():
    rb = (ROOT / "docs" / "specs" / "h2-cutover-runbook.md").read_text()
    for needle in ("sp_cutover.py run", "compare_exports.py", "--since 1", "WAIVER W1",
                   "WAIVER W2", "doubleheader", "postponed", "Rollback", "architect ruling"):
        assert needle in rb, needle
    h1 = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    assert "h2-cutover-runbook.md" in h1[h1.index("## H2. Cutover"):]


def test_flip_sets_writer_and_never_touches_parallel_mode(world, host):
    """ARCHITECT-RULE 2026-10-01: the REAL flag is SP_WRITER_OF_RECORD; SP_PARALLEL_MODE
    stays the quota mode and is never edited by the flip."""
    world["real_env"].write_text("SP_PARALLEL_MODE=designated\nSP_WRITER_OF_RECORD=laptop\n")
    assert _real(world, host, step="flip") == 0
    assert world["real_env"].read_text() == "SP_PARALLEL_MODE=designated\nSP_WRITER_OF_RECORD=host\n"


def test_writer_of_record_stamped_on_receipts_and_named_by_compare(tmp_path, monkeypatch, capsys):
    import compare_exports
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "r.jsonl"))
    monkeypatch.setenv("SP_WRITER_OF_RECORD", "host")
    assert c.writer_of_record() == "host" and c.append_receipt({"kind": "chain"})["writer_of_record"] == "host"
    monkeypatch.setenv("SP_WRITER_OF_RECORD", "somewhere")
    assert c.writer_of_record() is None                       # unknown values are never guessed
    monkeypatch.setenv("SP_WRITER_OF_RECORD", "laptop")
    (tmp_path / "l").mkdir(); (tmp_path / "h").mkdir()
    compare_exports.main([str(tmp_path / "l"), str(tmp_path / "h"), "--since", "0"])
    assert "writer of record: laptop — canonical side: laptop" in capsys.readouterr().out


# ------------------------------- addendum 47 item 7(c): the role in host.env, the settings the pack's .env changes --

@pytest.mark.parametrize("env_text, why", [
    ("SP_WRITER_OF_RECORD=laptop\n", "not set there"),
    ("SP_WRITER_OF_RECORD=laptop\nSP_EXPORTS_MIRROR_ROLE=laptop\n", "it says 'laptop'"),
])
def test_47_7c_preflight_refuses_unless_host_env_itself_says_the_host_role(world, host, monkeypatch, env_text, why):
    """"The cutover's preflight refuses unless host.env itself says SP_EXPORTS_MIRROR_ROLE=host." The environment
    saying host does not count: only host.env's own line survives the pack's .env."""
    world["real_env"].write_text(env_text)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    assert _real(world, host, step="preflight") == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "preflight" and "does not say SP_EXPORTS_MIRROR_ROLE=host" in r["refused"] and why in r["refused"]


def test_47_7c_preflight_prints_the_settings_the_pack_changes_by_name_never_by_value(world, host, capsys):
    """"It also prints, by name and never by value, each setting whose value on the host changes when the pack's .env
    replaces the checkout's [...] A setting host.env carries is left out, since host.env wins. The list refuses
    nothing by itself." The pack's .env: DATABASE_URL. The host checkout's .env: DATABASE_URL (another value),
    NTFY_TOPIC (not in the pack), SP_EXPORTS_MIRROR_ROLE and SP_SKIP_FAMILIES (host.env carries them: left out)."""
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/other.db\nNTFY_TOPIC=host-secret-topic\n"
                                    "SP_EXPORTS_MIRROR_ROLE=laptop\nSP_SKIP_FAMILIES=NONE\n")
    capsys.readouterr()
    assert _real(world, host, step="preflight") == 0                      # the list refuses nothing by itself
    out = capsys.readouterr().out
    assert "in the pack, not in the checkout's .env: —" in out
    assert "in the checkout's .env, not in the pack: NTFY_TOPIC" in out
    assert "in both, different values: DATABASE_URL" in out
    assert "host-secret-topic" not in out and "other.db" not in out and "SP_SKIP_FAMILIES" not in out
    r = _lines(world["real_receipts"])[-1]
    assert r["exit"] == 0 and r["mirror_role"] == "host"
    assert r["env_changes"] == {"pack_only": [], "checkout_only": ["NTFY_TOPIC"], "differ": ["DATABASE_URL"]}
    assert "host-secret-topic" not in world["real_receipts"].read_text()


def test_codex_4250381661_a_pack_without_an_env_changes_no_setting(tmp_path, monkeypatch):
    """Codex on #457: install leaves the checkout's .env when the pack has none, so nothing is listed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("NTFY_TOPIC=x\nDATABASE_URL=sqlite:///./data/sports.db\n")
    monkeypatch.setattr(c, "REPO", repo)
    pack = tmp_path / "pack"
    pack.mkdir()
    assert sp_cutover.env_changes_by_pack(pack, {}) == {"pack_only": [], "checkout_only": [], "differ": []}


def test_48_6_460_a_setting_host_env_leaves_empty_is_still_listed(tmp_path, monkeypatch):
    """#460 item 1 RULED (addendum 48 item 6): "Only a setting to which host.env gives a value is left out of the
    list." NTFY_TOPIC= in host.env falls back to the .env, so the pack changes it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("NTFY_TOPIC=old-topic\n")
    monkeypatch.setattr(c, "REPO", repo)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / sp_migrate.ENV).write_text("NTFY_TOPIC=new-topic\n")
    assert sp_cutover.env_changes_by_pack(pack, {"NTFY_TOPIC": ""})["differ"] == ["NTFY_TOPIC"]
    assert sp_cutover.env_changes_by_pack(pack, {"NTFY_TOPIC": "host-topic"})["differ"] == []


# ---------------------------------- addendum 57 item 8 (#481): the active timers ----

def test_57_8_an_active_sp_timer_off_the_list_refuses_the_preflight_and_names_it(world, host):
    """"The cutover's preflight reads the sp timers that are active on the host. An active timer that is not on the
    list refuses the preflight, and the refusal names it. The operator corrects the list by hand; the tool never
    writes it." The host of 2026-10-13: two active timers not on the list."""
    listed = host["timers"].read_text().split()
    before = host["timers"].read_bytes()
    fake = FakeSystemctl(active=listed + ["sp-intl-daily.timer", "sp-exports-squash.timer"])
    assert _real(world, host, runner=fake) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "preflight" and r["exit"] == 1
    assert "sp-exports-squash.timer, sp-intl-daily.timer" in r["refused"] and str(host["timers"]) in r["refused"]
    assert r["timers_off_list"] == ["sp-exports-squash.timer", "sp-intl-daily.timer"]
    assert host["timers"].read_bytes() == before                  # the tool never writes the list
    assert "stop" not in fake.verbs() and world["real_env"].read_text() == REAL_ENV_TEXT   # nothing paused or flipped


def test_57_8_an_active_sp_timer_the_list_cannot_carry_is_named_never_dropped(world, host):
    """systemd's 'sp-*' also lists a templated or underscored timer. It is active and off the list, so it refuses and
    is named like any other, and the refusal says the list cannot carry it as built."""
    listed = host["timers"].read_text().split()
    fake = FakeSystemctl(active=listed + ["sp-chain@mlb.timer", "sp-soccer_refresh.timer"])
    assert _real(world, host, runner=fake) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "preflight" and r["exit"] == 1
    assert r["timers_off_list"] == ["sp-chain@mlb.timer", "sp-soccer_refresh.timer"]
    assert "sp-chain@mlb.timer, sp-soccer_refresh.timer cannot go on the list as built" in r["refused"]
    assert "stop" not in fake.verbs()


def test_57_8_the_list_corrected_by_hand_passes_and_the_receipt_counts_the_active_timers(world, host):
    fake = FakeSystemctl(active=host["timers"].read_text().split() + ["sp-intl-daily.timer"])
    host["timers"].write_text(host["timers"].read_text() + "sp-intl-daily.timer\n")   # the operator's hand
    assert _real(world, host, step="preflight", runner=fake) == 0
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "preflight" and r["timers_active"] == 4 and r["timers"] == 4


def test_79_4_a_listed_timer_that_is_not_active_refuses_the_preflight_and_is_named(world, host, capsys):
    """ARCHITECT 2026-10-15, addendum 79 item 4: "deploy/hosting/sp_cutover.py's preflight refuses when any listed timer
    is not active (naming it)". (#495's addendum 60 item 6 had it named and refusing nothing: addendum 79 is later.)"""
    listed = host["timers"].read_text().split()
    fake = FakeSystemctl(active=listed[1:])
    assert _real(world, host, step="preflight", runner=fake) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "preflight" and r["exit"] == 1 and r["timers_listed_inactive"] == [listed[0]]
    assert f"listed sp timers not active on the host: {listed[0]}" in r["refused"]
    out = capsys.readouterr().out
    assert f"✗ timers list {host['timers']}: 3 · listed but not active: {listed[0]}" in out
    assert "stop" not in fake.verbs() and world["real_env"].read_text() == REAL_ENV_TEXT


def test_57_8_other_units_refuse_nothing_and_the_receipt_names_no_inactive_timer(world, host, capsys):
    """A service, a non-sp timer: neither is an sp timer, so neither refuses (57.8 and 79.4 read sp-*.timer only)."""
    listed = host["timers"].read_text().split()
    fake = FakeSystemctl(active=listed + ["sp-chain@mlb.service", "apt-daily.timer"])
    assert _real(world, host, step="preflight", runner=fake) == 0
    r = _lines(world["real_receipts"])[-1]
    assert r["timers_active"] == len(listed) and r["timers_listed_inactive"] == []
    out = capsys.readouterr().out
    assert f"· timers list {host['timers']}: 3 · listed but not active: none" in out
    assert "· active sp timers on the host: 3 · not on the list: none" in out


def test_57_8_a_listing_that_cannot_be_read_refuses(world, host):
    class NoList(FakeSystemctl):
        def __call__(self, argv):
            if argv[1:2] == ["list-units"]:
                self.calls.append([str(a) for a in argv])
                return 1, "Failed to connect to bus"
            return super().__call__(argv)
    fake = NoList(active=host["timers"].read_text().split())
    assert _real(world, host, step="preflight", runner=fake) == 1
    assert "cannot read the active sp timers" in _lines(world["real_receipts"])[-1]["refused"]


def test_57_8_the_dry_run_scratch_list_is_its_own_and_passes(world, capsys):
    """The dry run's scratch list stays as it is: its stand-in reports the scratch list's timers as the active ones."""
    run = sp_cutover.DryRunner(active=sp_cutover.runbook_timers())
    rc, out = run(["systemctl", "list-units", "--type=timer", "--state=active", "--no-legend", "--plain", "sp-*"])
    assert rc == 0 and sorted(ln.split()[0] for ln in out.splitlines()) == sorted(sp_cutover.runbook_timers())
    assert _dry(world, world["tmp"] / "scratch57") == 0


# ------------------------------- addendum 79 item 4 (#520): the host's NHL shot GATE streams ----

def test_80_3_the_packs_streams_below_95_refuse_naming_each_stream(world, host, capsys):
    """ARCHITECT 2026-10-15, addendum 80 item 3 (Q3): "The shot gate reads the PACK's DB — the laptop's, the one the
    cutover installs — and refuses on it". A pack below 95% refuses, naming each stream and its share; no backfill
    command is printed for it (the host's backfill does not change the pack)."""
    fake = FakeSystemctl(active=host["timers"].read_text().split())
    low = {**HOST_GATE, "db": PASS_GATE["db"], "source": "pack"}
    assert _real(world, host, step="preflight", runner=fake, shot=low) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["refused"] == ("the pack's NHL shot GATE streams below 95%: 2024 0/1396 = 0.0%, 2025 0/1394 = 0.0% "
                            "(the pack carries the laptop's DB, the one install puts in place)")
    assert r["shot_gate_pack"] == low and r["shot_gate_host"] == PASS_GATE
    out = capsys.readouterr().out.splitlines()
    assert "✗ the pack's NHL shot GATE stream 2024: 0/1396 = 0.0% [BELOW >= 95%]" in out
    assert "✗ the pack's NHL shot GATE stream 2025: 0/1394 = 0.0% [BELOW >= 95%]" in out
    assert not any("nhl-shot-sync" in o for o in out)
    assert "stop" not in fake.verbs() and [c_[0] for c_ in fake.calls] == ["systemctl"]   # nothing run but the reads


def test_80_3_the_hosts_live_streams_below_95_never_refuse_and_print_the_optional_backfill(world, host, capsys):
    """#520's host (2026-10-14): 0/1396 and 0/1394, read for the record. With the pack at the laptop's numbers the
    preflight PASSES; the host's lines carry no fault mark, and the backfill's exact host command is printed,
    --dry-run first, never run, labelled "optional before cutover; not a prerequisite" (addendum 80 item 3)."""
    fake = FakeSystemctl(active=host["timers"].read_text().split())
    assert _real(world, host, step="preflight", runner=fake, host_shot=HOST_GATE) == 0
    r = _lines(world["real_receipts"])[-1]
    assert r["exit"] == 0 and r["shot_gate_pack"] == PASS_GATE and r["shot_gate_host"] == HOST_GATE
    out = capsys.readouterr().out.splitlines()
    assert "· the pack's NHL shot GATE stream 2024: 1396/1396 = 100.0% [PASS >= 95%]" in out
    assert ("· for the record, never refuses: the host's live NHL shot GATE stream 2024: 0/1396 = 0.0% "
            "[BELOW >= 95%]") in out
    assert ("· for the record, never refuses: the host's live NHL shot GATE stream 2025: 0/1394 = 0.0% "
            "[BELOW >= 95%]") in out
    i = out.index("· the host's NHL shot backfill: optional before cutover; not a prerequisite (addendum 80 item 3: "
                  "the pack's DB is the one the cutover installs). Printed here, never run. FIRST, the dry run, pasted "
                  "to the architect:")
    assert out[i + 1:i + 9] == [
        f"    cd {host['h']}",
        "    sudo -u sp venv/bin/python cli.py nhl-shot-sync --start 2024-10-07 --end 2026-06-19 --dry-run",
        "  STOP: the write below is the operator's block after the architect has read that dry run.",
        f"    cd {host['h']}",
        "    sudo -u sp venv/bin/python deploy/hosting/sp_backup.py daily",
        "    sudo -u sp venv/bin/python cli.py nhl-shot-sync --start 2024-10-07 --end 2026-06-19",
        "    sudo -u sp venv/bin/python cli.py nhl-shot-coverage",
        "  (--start 2024-10-07: the day before the first GATE-stream game, 2024-10-08 UTC; --end 2026-06-19: the "
        "last one's)"]
    assert not any(o.startswith("✗") for o in out)
    assert "stop" not in fake.verbs() and [c_[0] for c_ in fake.calls] == ["systemctl"]


def test_79_4_the_laptops_numbers_pass_and_the_receipt_carries_both_reads(world, host, capsys):
    seen = []
    assert _real(world, host, step="preflight", seen=seen) == 0
    assert seen == [True, False]                                          # the pack's DB, then the host's live one
    r = _lines(world["real_receipts"])[-1]
    assert r["exit"] == 0 and r["shot_gate_pack"] == PASS_GATE and r["shot_gate_host"] == PASS_GATE
    out = capsys.readouterr().out
    assert "· the pack's NHL shot GATE stream 2024: 1396/1396 = 100.0% [PASS >= 95%]" in out
    assert "nhl-shot-sync" not in out                                     # nothing to backfill: no command


@pytest.mark.parametrize("w,ok", [(1326, False), (1327, True)])
def test_79_4_the_bar_is_nhl_shot_coverages_own(world, host, capsys, w, ok):
    """1326/1396 = 94.99% prints 95.0% and is BELOW (the unrounded share decides, as nhl-shot-coverage's line does);
    1327/1396 = 95.06% passes."""
    gate = {**PASS_GATE, "seasons": {**PASS_GATE["seasons"], "2024": {**PASS_GATE["seasons"]["2024"], "with_shots": w}}}
    assert _real(world, host, step="preflight", shot=gate) == (0 if ok else 1)
    out = capsys.readouterr().out
    pct = f"{w / 1396 * 100:.1f}"
    assert f"the pack's NHL shot GATE stream 2024: {w}/1396 = {pct}% [{'PASS' if ok else 'BELOW'} >= 95%]" in out


@pytest.mark.parametrize("read,why", [
    ({"error": "OperationalError: no such table: nhl_shot_events"}, "not read (OperationalError: no such table"),
    ({"bar": 95.0, "seasons": {}}, "named no season or no bar"),
])
def test_79_4_an_unread_gate_refuses_never_reads_as_a_pass(world, host, capsys, read, why):
    assert _real(world, host, step="preflight", shot=read) == 1
    assert f"the pack's NHL shot GATE {'streams ' if 'not read' in why else 'read '}" \
        in _lines(world["real_receipts"])[-1]["refused"]
    assert why in _lines(world["real_receipts"])[-1]["refused"]
    assert "nhl-shot-sync" not in capsys.readouterr().out             # no stream dates read: no command printed


@pytest.mark.parametrize("read,line", [
    ({"error": "OperationalError: no such table: nhl_shot_events"}, "the host's live NHL shot GATE: not read ("),
    ({"bar": 95.0, "seasons": {}}, "the host's live NHL shot GATE: the read named no season or no bar"),
    ({"bar": 95.0, "seasons": {"2024": {"games": 0, "with_shots": 0, "first": None, "last": None}}},
     "the host's live NHL shot GATE stream 2024: 0/0 = 0.0% [BELOW >= 95%]"),
])
def test_80_3_an_unread_host_record_never_refuses_and_prints_no_fault_mark(world, host, capsys, read, line):
    """The host's live read is the record: unread, empty, or with no stream games, it says so with no ✗ anywhere, and
    the preflight still passes on the pack's gate."""
    assert _real(world, host, step="preflight", host_shot=read) == 0
    out = capsys.readouterr().out
    assert f"· for the record, never refuses: {line}" in out and "nhl-shot-sync" not in out
    assert not any(o.startswith("✗") for o in out.splitlines())
    assert _lines(world["real_receipts"])[-1]["shot_gate_host"] == read


def test_79_4_every_check_prints_its_line_and_one_refusal_names_them_all(world, host, capsys):
    """Off the list, listed but inactive, and the gate below, at once: one refusal names all three, and each check
    printed its line."""
    listed = host["timers"].read_text().split()
    fake = FakeSystemctl(active=listed[1:] + ["sp-intl-daily.timer"])
    low = {**HOST_GATE, "source": "pack"}
    assert _real(world, host, step="preflight", runner=fake, shot=low) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["refused"].count(" | ") == 2 and r["timers_off_list"] == ["sp-intl-daily.timer"]
    assert r["timers_listed_inactive"] == [listed[0]] and r["shot_gate_pack"] == low
    out = capsys.readouterr().out
    for line in ("✗ active sp timers on the host: 3 · not on the list: sp-intl-daily.timer",
                 f"✗ timers list {host['timers']}: 3 · listed but not active: {listed[0]}",
                 f"· host env {world['real_env']}: present", "· SP_WRITER_OF_RECORD lines in host.env: 1",
                 "· SP_WRITER_OF_RECORD now: 'laptop'", "· host.env's own SP_EXPORTS_MIRROR_ROLE: host",
                 "· host env writable by this user: file yes · its directory yes",
                 "· the pack's .env: DATABASE_URL relative",
                 "✗ the pack's NHL shot GATE stream 2025: 0/1394 = 0.0% [BELOW >= 95%]"):
        assert line in out
    assert out.count("✗ REFUSED preflight") == 1


def test_79_4_the_dry_run_says_the_gate_is_not_read_there(world, capsys):
    assert _dry(world, world["tmp"] / "scratch79") == 0
    out = capsys.readouterr().out
    assert ("· NHL shot GATE: not read in a dry run (the scratch world holds no NHL games; the real preflight reads "
            "the pack's DB, which gates, and the host's live DB, for the record)") in out
    r = next(x for x in _lines(world["tmp"] / "scratch79" / "log" / "receipts.jsonl") if x.get("step") == "preflight")
    assert r["shot_gate_pack"] == "not read (dry run)" and r["shot_gate_host"] == "not read (dry run)"


def test_79_4_the_host_read_runs_as_the_service_user_and_returns_its_one_line(world, monkeypatch):
    seen = []

    def runner(argv):
        seen.append([str(a) for a in argv])
        return 0, "noise\n" + sp_cutover.SHOT_GATE_TAG + json.dumps(PASS_GATE) + "\n"
    ctx = sp_cutover.Ctx(pack=world["pack"], timers_file=world["tmp"] / "t", runner=runner)
    monkeypatch.setattr(sp_cutover, "_euid", lambda: 0)
    assert sp_cutover.run_shot_read(ctx, False) == PASS_GATE
    assert seen[0][:4] == ["runuser", "-u", "sp", "--"] and seen[0][-2:] == [str(sp_cutover.HERE / "sp_cutover.py"),
                                                                           "shot-gate"]
    assert sp_cutover.run_shot_read(ctx, True) == PASS_GATE              # addendum 80 item 3: the pack's DB
    assert seen[1][-3:] == ["shot-gate", "--pack", str(world["pack"])]
    for rc, out, why in ((1, "Traceback ...", "printed no SHOT-GATE line (exit 1)"),
                         (0, sp_cutover.SHOT_GATE_TAG + "{bad", "is not JSON"),
                         (2, sp_cutover.SHOT_GATE_TAG + json.dumps(PASS_GATE), "the read exit 2")):
        ctx.runner = lambda argv, rc=rc, out=out: (rc, out)
        assert why in sp_cutover.run_shot_read(ctx, True)["error"]


def _nhl_db(path):
    """A throwaway DB holding two GATE-stream seasons: 2024 (3 games from 2024-10-08, 2 with shot events; a preseason
    game before it, cut) and 2025 (2 games, 1 with shot events)."""
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.schema import Base, Competition, Match, MatchStatus, NHLShotEvent, Sport, Team
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="NA", type="LEAGUE")
        h, a = Team(sport=Sport.NHL, name="H"), Team(sport=Sport.NHL, name="A")
        s.add_all([comp, h, a])
        s.flush()
        games = [("2024", datetime(2024, 10, 1, 23)), ("2024", datetime(2024, 10, 8, 23)),
                 ("2024", datetime(2024, 12, 1, 0)), ("2024", datetime(2025, 6, 17, 0)),
                 ("2025", datetime(2025, 10, 7, 23)), ("2025", datetime(2026, 6, 19, 0))]
        for i, (season, when) in enumerate(games):
            m = Match(sport=Sport.NHL, competition_id=comp.id, season=season, utc_date=when,
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=3, away_score=2)
            s.add(m)
            s.flush()
            if i in (1, 2, 4):
                s.add(NHLShotEvent(nhl_game_id=1000 + i, event_id=1, match_id=m.id, game_start=when,
                                   event_type="shot-on-goal"))
        s.commit()
    eng.dispose()


def test_79_4_shot_gate_reads_a_real_db_in_a_process_of_its_own_and_never_creates_one(tmp_path):
    import subprocess
    db = tmp_path / "host.db"
    _nhl_db(db)
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "SP_HOST_ENV": str(tmp_path / "no-host.env")}
    r = subprocess.run([sys.executable, str(HOSTING / "sp_cutover.py"), "shot-gate"], capture_output=True, text=True,
                       env=env, cwd=tmp_path, timeout=120)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith(sp_cutover.SHOT_GATE_TAG)]
    assert r.returncode == 0 and len(line) == 1, r.stdout + r.stderr
    got = json.loads(line[0][len(sp_cutover.SHOT_GATE_TAG):])
    assert got["bar"] == 95.0 and got["seasons"] == {
        "2024": {"games": 3, "with_shots": 2, "first": "2024-10-08", "last": "2025-06-17"},
        "2025": {"games": 2, "with_shots": 1, "first": "2025-10-07", "last": "2026-06-19"}}
    assert not (tmp_path / "data").exists()                      # nothing created beside the run
    missing = tmp_path / "none" / "sports.db"
    r = subprocess.run([sys.executable, str(HOSTING / "sp_cutover.py"), "shot-gate"], capture_output=True, text=True,
                       env={**env, "DATABASE_URL": f"sqlite:///{missing}"}, cwd=tmp_path, timeout=120)
    assert r.returncode == 1 and "no database at" in r.stdout and not missing.exists() and not missing.parent.exists()


@pytest.mark.parametrize("env_text,lines", [
    ("SP_WRITER_OF_RECORD=bogus\nSP_WRITER_OF_RECORD=laptop\nSP_EXPORTS_MIRROR_ROLE=host\n",
     ["✗ SP_WRITER_OF_RECORD lines in host.env: 2", "  (SP_WRITER_OF_RECORD's value not read: it is set on 2 lines)"]),
    ("SP_WRITER_OF_RECORD=\nSP_EXPORTS_MIRROR_ROLE=host\n", ["✗ SP_WRITER_OF_RECORD now: ''"]),
    ("SP_EXPORTS_MIRROR_ROLE=host\n", ["· SP_WRITER_OF_RECORD now: unset (no line)"]),
])
def test_79_4_the_flag_lines_say_what_was_read(world, host, capsys, env_text, lines):
    world["real_env"].write_text(env_text)
    _real(world, host, step="preflight")
    out = capsys.readouterr().out.splitlines()
    for ln in lines:
        assert ln in out
    assert not any(o.startswith("· SP_WRITER_OF_RECORD now") for o in out) or "unset (no line)" in lines[0]


def test_79_4_the_writable_line_names_the_file_and_its_directory(world, host, capsys, monkeypatch):
    real = os.access
    monkeypatch.setattr(sp_cutover.os, "access", lambda p, m: False if Path(p) == world["real_env"].parent else real(p, m))
    assert _real(world, host, step="preflight") == 1
    out = capsys.readouterr().out
    assert "✗ host env writable by this user: file yes · its directory no" in out


def test_79_4_shot_gate_writes_nothing_to_the_db_it_reads(tmp_path):
    """The read is mode=ro on a connection of its own: a non-WAL DB keeps its bytes and its journal mode, and no -wal
    or -shm is left beside it."""
    import hashlib
    import subprocess
    db = tmp_path / "host.db"
    _nhl_db(db)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "SP_HOST_ENV": str(tmp_path / "no-host.env")}
    r = subprocess.run([sys.executable, str(HOSTING / "sp_cutover.py"), "shot-gate"], capture_output=True, text=True,
                       env=env, cwd=tmp_path, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["host.db"]
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    con.close()


# ------------------------------- addendum 80 item 3: the preflight before step 2; the pack's DB gates ----

def test_80_3_a_preflight_after_step_2_stops_with_its_one_line_never_a_fault(world, host, capsys):
    """ARCHITECT 2026-10-15, addendum 80 item 3 (Q1), verbatim: "A run after step 2 is not the preflight; sp_cutover
    prints "timers already stopped: run the preflight before step 2" when every listed timer is inactive, rather than a
    refusal that reads as a fault." It stops (exit 1: `run` goes no further), checks nothing else and reads no DB."""
    fake = FakeSystemctl(active=[])                                       # runbook step 2 stopped every listed timer
    seen = []
    assert _real(world, host, step="run", runner=fake, seen=seen) == 1
    out = capsys.readouterr().out.splitlines()
    assert "timers already stopped: run the preflight before step 2" in out
    assert not any(o.startswith("✗") or "REFUSED" in o or "FAIL" in o for o in out)
    assert seen == [] and "stop" not in fake.verbs()                      # no shot read, no pause
    rs = [r for r in _lines(world["real_receipts"]) if r["kind"] == "cutover"]
    assert [r["step"] for r in rs] == ["preflight"]
    r = rs[0]
    assert r["exit"] == 1 and r["stopped"] == "timers already stopped: run the preflight before step 2"
    assert "refused" not in r and r["timers_listed_inactive"] == host["timers"].read_text().split()
    assert world["real_env"].read_text() == REAL_ENV_TEXT


def test_80_3_one_listed_timer_stopped_is_still_the_79_4_refusal(world, host, capsys):
    """Only EVERY listed timer inactive reads as a run after step 2; one of three is addendum 79 item 4's refusal."""
    listed = host["timers"].read_text().split()
    assert _real(world, host, step="preflight", runner=FakeSystemctl(active=listed[:2])) == 1
    r = _lines(world["real_receipts"])[-1]
    assert "stopped" not in r and r["refused"].startswith(f"listed sp timers not active on the host: {listed[2]}")


def _pack_dir(tmp_path, wal=False):
    pk = tmp_path / "sp_pack_x"
    pk.mkdir()
    _nhl_db(pk / "sports.db")
    if wal:                                                               # a .backup of a WAL DB keeps the WAL header
        con = sqlite3.connect(pk / "sports.db")
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        con.close()
        assert not (pk / "sports.db-wal").exists()
    return pk


@pytest.mark.parametrize("wal", [False, True])
def test_80_3_shot_gate_reads_the_packs_db_as_a_copy_and_leaves_it_as_it_was(tmp_path, wal):
    """`shot-gate --pack <dir>` reads <dir>/sports.db (addendum 80 item 3: the pack's DB gates), opened as sp_migrate
    opens the pack's copy (copy_connect, addendum 73 item 4): its bytes unchanged, nothing beside it, and the live
    DATABASE_URL never opened."""
    import hashlib
    import subprocess
    pk = _pack_dir(tmp_path, wal)
    before = hashlib.sha256((pk / "sports.db").read_bytes()).hexdigest()
    live = tmp_path / "live" / "sports.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{live}", "SP_HOST_ENV": str(tmp_path / "no-host.env")}
    r = subprocess.run([sys.executable, str(HOSTING / "sp_cutover.py"), "shot-gate", "--pack", str(pk)],
                       capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith(sp_cutover.SHOT_GATE_TAG)]
    assert r.returncode == 0 and len(line) == 1, r.stdout + r.stderr
    got = json.loads(line[0][len(sp_cutover.SHOT_GATE_TAG):])
    assert got["source"] == "pack" and got["db"] == str(pk.resolve() / "sports.db")
    assert got["seasons"]["2024"] == {"games": 3, "with_shots": 2, "first": "2024-10-08", "last": "2025-06-17"}
    assert hashlib.sha256((pk / "sports.db").read_bytes()).hexdigest() == before
    assert sorted(x.name for x in pk.iterdir()) == ["sports.db"]
    assert not live.parent.exists()


def test_80_3_shot_gate_on_a_pack_without_a_db_refuses_and_creates_nothing(tmp_path):
    """--pack names the pack's sports.db and nothing else: a pack without one refuses on THAT path (the live
    DATABASE_URL is never read in its place) and nothing is created on either side."""
    import subprocess
    pk = tmp_path / "sp_pack_empty"
    pk.mkdir()
    live = tmp_path / "live" / "sports.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{live}", "SP_HOST_ENV": str(tmp_path / "no-host.env")}
    r = subprocess.run([sys.executable, str(HOSTING / "sp_cutover.py"), "shot-gate", "--pack", str(pk)],
                       capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)
    assert r.returncode == 1 and f"no database at {pk.resolve() / 'sports.db'}" in r.stdout
    assert list(pk.iterdir()) == [] and not live.parent.exists()


def test_80_3_the_live_read_is_mode_ro_never_immutable(tmp_path):
    """#340: the host's live DB is read mode=ro, never immutable: a row committed to its WAL and not yet checkpointed
    is read (an immutable open would miss it). The pack's copy is the only immutable read."""
    import subprocess
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.schema import Match, NHLShotEvent
    db = tmp_path / "live.db"
    _nhl_db(db)
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    eng = create_engine(f"sqlite:///{db}")
    with Session(eng) as s_:                                   # the 2024 game of 2025-06-17 gains its shot events
        m = s_.query(Match).filter(Match.utc_date == datetime(2025, 6, 17, 0)).one()
        s_.add(NHLShotEvent(nhl_game_id=2000, event_id=1, match_id=m.id, game_start=m.utc_date,
                            event_type="shot-on-goal"))
        s_.commit()
    assert (tmp_path / "live.db-wal").stat().st_size > 0      # the row lives only in the WAL
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "SP_HOST_ENV": str(tmp_path / "no-host.env")}
    r = subprocess.run([sys.executable, str(HOSTING / "sp_cutover.py"), "shot-gate"], capture_output=True, text=True,
                       env=env, cwd=tmp_path, timeout=120)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith(sp_cutover.SHOT_GATE_TAG)]
    assert r.returncode == 0 and len(line) == 1, r.stdout + r.stderr
    got = json.loads(line[0][len(sp_cutover.SHOT_GATE_TAG):])
    assert got["source"] == "live" and got["seasons"]["2024"]["with_shots"] == 3
    con.close()
    eng.dispose()


def test_80_3_an_off_list_timer_active_is_never_hidden_by_the_stop(world, host, capsys):
    """Every listed timer inactive but an sp timer active OFF the list: not "already stopped". Addendum 57 item 8's
    refusal names the off-list timer (and 79.4 the listed ones); the stop line is not printed."""
    listed = host["timers"].read_text().split()
    assert _real(world, host, step="preflight", runner=FakeSystemctl(active=["sp-intl-daily.timer"])) == 1
    r = _lines(world["real_receipts"])[-1]
    assert "stopped" not in r and r["timers_off_list"] == ["sp-intl-daily.timer"]
    assert r["timers_listed_inactive"] == listed
    assert "active sp timers not on the timers list" in r["refused"]
    assert "timers already stopped" not in capsys.readouterr().out


def test_80_3_a_refusal_for_another_check_keeps_both_shot_reads_on_its_receipt(world, host):
    """The host's read is the record: a preflight refused on another check still receipts both reads."""
    listed = host["timers"].read_text().split()
    fake = FakeSystemctl(active=listed + ["sp-intl-daily.timer"])
    assert _real(world, host, step="preflight", runner=fake, host_shot=HOST_GATE) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["refused"].startswith("active sp timers not on the timers list")
    assert r["shot_gate_pack"] == PASS_GATE and r["shot_gate_host"] == HOST_GATE


# ---------------- addendum 168 item 3 (#677): install removes the ruled pack-only settings, names only ----

PACK_ENV_168 = ("# laptop .env\r\n"
                "DATABASE_URL=sqlite:///./data/sports.db\r\n"
                "SP_EXPORTS_MIRROR_KEY=/home/anthony/.ssh/sp_mirror_ed25519\n"
                "export CFBD_API_KEY=\"cfbd-secret-value-123\"\n"
                "NTFY_TOPIC=laptop-topic-value\n"
                "  SP_HOST_ADDR = 100.64.0.7\n"
                "# trailing comment, no newline")
VALUES_168 = ("/home/anthony/.ssh/sp_mirror_ed25519", "cfbd-secret-value-123", "100.64.0.7", "laptop-topic-value")


def _pack_168(world, host, monkeypatch, env_text, name="pack_20261026T1340"):
    """A pack whose .env is `env_text` (made on the laptop), then back to the host checkout."""
    laptop = world["laptop"]
    monkeypatch.setattr(c, "REPO", laptop)
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{world['db']}")
    (laptop / ".env").write_bytes(env_text.encode())
    pk = world["tmp"] / name
    assert sp_migrate.pack(pk) == 0
    monkeypatch.setattr(c, "REPO", host["h"])
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/sports.db")
    return pk


def _install_168(host, pk):
    return sp_cutover.main(["install", "--pack", str(pk), "--timers-file", str(host["timers"])],
                           runner=FakeSystemctl(active=host["timers"].read_text().split()))


def test_168_3_install_removes_the_ruled_pack_only_settings_and_names_them_never_their_values(
        world, host, monkeypatch, capsys):
    """Addendum 168 item 3: "`install` [...] REMOVES pack-only settings that host.env does not define and that name a
    path or a key (a list in sp_cutover, ruled: SP_EXPORTS_MIRROR_KEY, CFBD_API_KEY, SP_HOST_ADDR today), printing
    their names". host.env defines CFBD_API_KEY (kept); SP_HOST_ADDR= there is empty, so the .env's line is the one
    the host reads (removed, addendum 48 item 6); NTFY_TOPIC is pack-only but not ruled (kept). Every other line is
    byte-identical; the .env before it is kept beside host.env (outside the checkout), 0640."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    world["real_env"].write_text(REAL_ENV_TEXT + "CFBD_API_KEY=host-cfbd\nSP_HOST_ADDR=\n")
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    capsys.readouterr()
    assert _install_168(host, pk) == 0
    out = capsys.readouterr().out
    assert ("· pack-only settings removed from the checkout's .env (addendum 168 item 3; names only, never values): "
            "SP_EXPORTS_MIRROR_KEY, SP_HOST_ADDR · the .env before it kept as "
            f"{world['real_env'].parent / 'checkout.env.pre-scrub-'}") in out
    envp = host["h"] / ".env"
    want = "".join(ln for ln in PACK_ENV_168.splitlines(keepends=True)
                   if not ln.lstrip().startswith(("SP_EXPORTS_MIRROR_KEY", "SP_HOST_ADDR")))
    assert envp.read_bytes() == want.encode()                        # other lines byte-identical, CRLF kept
    assert c.parse_env_file(envp)["CFBD_API_KEY"] == "cfbd-secret-value-123"
    assert c.parse_env_file(envp)["NTFY_TOPIC"] == "laptop-topic-value"
    baks = list(world["real_env"].parent.glob("checkout.env.pre-scrub-*"))
    assert len(baks) == 1 and baks[0].read_bytes() == PACK_ENV_168.encode()
    assert baks[0].stat().st_mode & 0o777 == 0o640
    assert not [q for q in host["h"].rglob("*") if "pre-scrub" in q.name]      # nothing in the checkout
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "install" and r["exit"] == 0
    assert r["env_removed"] == ["SP_EXPORTS_MIRROR_KEY", "SP_HOST_ADDR"]
    assert r["env_scrub_ruled"] == list(sp_cutover.PACK_ONLY_SCRUB) and r["env_kept_copy"] == str(baks[0])
    receipts = world["real_receipts"].read_text()
    for v in VALUES_168:
        assert v not in out and v not in receipts


def test_168_3_a_ruled_setting_the_host_checkout_already_had_is_kept(world, host, monkeypatch, capsys):
    """Only a setting that came from the pack alone is removed: one the host checkout's .env already carried is not
    pack-only (the preflight's comparison), so install leaves the pack's line."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\nSP_HOST_ADDR=10.0.0.1\n"
                                    "SP_EXPORTS_MIRROR_KEY=/home/sp/.ssh/k\nCFBD_API_KEY=host\n")
    capsys.readouterr()
    assert _install_168(host, pk) == 0
    assert "never values): " not in capsys.readouterr().out
    assert (host["h"] / ".env").read_bytes() == PACK_ENV_168.encode()
    assert not list(world["real_env"].parent.glob("checkout.env.pre-scrub-*"))
    r = _lines(world["real_receipts"])[-1]
    assert r["env_removed"] == [] and r["env_kept_copy"] is None and "env_scrub_undecided" not in r


def test_168_3_an_env_already_the_packs_decides_nothing_and_names_the_ruled_settings(world, host, monkeypatch, capsys):
    """Law 4: when the checkout's .env is already the pack's before install, the .env the pack replaces is gone, so
    which settings came only from the pack cannot be read: nothing is removed, the ruled names it carries are named."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_bytes(PACK_ENV_168.encode())
    capsys.readouterr()
    assert _install_168(host, pk) == 0
    out = capsys.readouterr().out
    assert "· NOT decided, nothing removed: SP_EXPORTS_MIRROR_KEY, CFBD_API_KEY, SP_HOST_ADDR — the checkout's .env " \
           "was already the pack's before install" in out
    assert (host["h"] / ".env").read_bytes() == PACK_ENV_168.encode()
    r = _lines(world["real_receipts"])[-1]
    assert r["env_removed"] == [] and r["env_scrub_undecided"] == ["SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY",
                                                                   "SP_HOST_ADDR"]
    for v in VALUES_168:
        assert v not in out and v not in world["real_receipts"].read_text()


def test_168_3_a_refused_install_after_the_env_is_placed_still_removes_and_receipts_the_names(
        world, host, monkeypatch, capsys):
    """The pack's .env never stays unscrubbed: install refusing after it placed the .env still removes the ruled
    names, and the refusal's receipt carries them."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")

    def placed_then_failed(pack, replace):
        (c.REPO / ".env").write_bytes((pack / sp_migrate.ENV).read_bytes())
        raise SystemExit("✗ injected failure after the .env was placed")
    monkeypatch.setattr(sp_migrate, "install", placed_then_failed)
    assert _install_168(host, pk) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "install" and "injected failure" in r["refused"]
    assert r["env_removed"] == ["SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY", "SP_HOST_ADDR"]
    left = c.parse_env_file(host["h"] / ".env")
    assert not set(sp_cutover.PACK_ONLY_SCRUB) & set(left) and left["NTFY_TOPIC"] == "laptop-topic-value"


def test_168_3_the_ruled_list_is_the_three_names():
    assert sp_cutover.PACK_ONLY_SCRUB == ("SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY", "SP_HOST_ADDR")


def test_168_3_codex_682_a_taken_backup_name_gets_a_suffix_and_the_scrub_still_runs(world, host, monkeypatch, capsys):
    """Codex on #682 (P2): a retry in the same second finds the backup name taken. The kept copy takes a -N suffix,
    the earlier copy is never overwritten, and the ruled names are still removed."""
    from datetime import datetime, timezone
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 10, 26, 13, 44, 0, tzinfo=timezone.utc))
    earlier = world["real_env"].parent / "checkout.env.pre-scrub-20261026T134400Z"
    earlier.write_bytes(b"EARLIER=kept\n")
    assert _install_168(host, pk) == 0
    assert earlier.read_bytes() == b"EARLIER=kept\n"
    second = world["real_env"].parent / "checkout.env.pre-scrub-20261026T134400Z-1"
    assert second.read_bytes() == PACK_ENV_168.encode()
    r = _lines(world["real_receipts"])[-1]
    assert r["env_kept_copy"] == str(second) and r["env_removed"] == ["SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY",
                                                                      "SP_HOST_ADDR"]


def test_168_3_codex_682_the_secret_copies_are_created_0600_from_the_outset(world, host, monkeypatch):
    """Codex on #682 (P1), ARCHITECT 2026-10-26: the kept copy and the temporary name are created with mode 0600 and
    O_EXCL, never written at a wider mode first, whatever the umask; the copy is 0640 only after its bytes."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    seen, real_open = [], sp_cutover.os.open

    def spy(path, flags, mode=0o777, *a, **kw):
        if ".env" in str(path):
            seen.append((Path(path).name, flags, mode))
        return real_open(path, flags, mode, *a, **kw)
    monkeypatch.setattr(sp_cutover.os, "open", spy)
    old = os.umask(0o022)
    try:
        assert _install_168(host, pk) == 0
    finally:
        os.umask(old)
    names = [n for n, _, _ in seen]
    assert any(n.startswith("checkout.env.pre-scrub-") for n in names) and "..env.scrub-tmp" in names
    for n, flags, mode in seen:
        assert mode == 0o600 and flags & os.O_EXCL and flags & os.O_CREAT, (n, oct(mode))
    assert not (host["h"] / "..env.scrub-tmp").exists()


def test_168_3_codex_682_a_scrub_io_error_is_a_receipted_refusal_not_a_traceback(world, host, monkeypatch, capsys):
    """Codex on #682 (P2): an OSError while scrubbing (a full disk at the replace) refuses install with a receipt
    naming the error and the settings to remove by hand; no traceback, no value printed."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")

    def full(src, dst):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(sp_cutover.os, "replace", full)
    capsys.readouterr()
    assert _install_168(host, pk) == 1
    out = capsys.readouterr().out
    assert "could not be removed from the checkout's .env (OSError: [Errno 28] No space left on device): remove " \
           "SP_EXPORTS_MIRROR_KEY, CFBD_API_KEY, SP_HOST_ADDR from it by hand" in out
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "install" and r["exit"] == 1 and "could not be removed" in r["refused"]
    assert r["env_removed"] == [] and r["env_scrub_planned"] == ["SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY",
                                                                 "SP_HOST_ADDR"]
    for v in VALUES_168:
        assert v not in out and v not in world["real_receipts"].read_text()


def test_168_3_codex_682_the_temporary_name_and_a_hand_made_copy_are_gitignored():
    """Codex on #682 (P1): the scrub's temporary name (it lives beside the .env until the replace) and a hand-made
    .env.bak are ignored by git; .env.example stays tracked. The kept copy is not in the checkout at all (below)."""
    import subprocess
    root = Path(__file__).resolve().parent.parent
    for name in (".env.bak", "..env.scrub-tmp"):
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", name]).returncode == 0, name
    assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".env.example"]).returncode == 1


def test_168_3_architect_682_the_root_install_keeps_the_copy_beside_host_env_and_names_it_to_the_sp_install(
        world, host, monkeypatch):
    """ARCHITECT 2026-10-26, on Codex's two P1s on #682: the copy lives where git can't see it, beside
    host.env.pre-cutover-<ts>, root:sp 0640 (the flip's pattern). Root writes it (sp cannot write that directory),
    created 0600, then host.env's owner and 0640 through the descriptor, BEFORE the sp install runs, and names it."""
    from datetime import datetime, timezone
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 10, 26, 13, 44, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(sp_cutover, "_euid", lambda: 0)
    owners = []
    monkeypatch.setattr(sp_cutover.os, "fchown", lambda fd, uid, gid: owners.append((uid, gid)))
    seen = []

    def runner(argv):
        seen.append([str(a) for a in argv])
        keep = world["real_env"].parent / "checkout.env.pre-scrub-20261026T134400Z"
        assert keep.read_bytes() == PACK_ENV_168.encode() and keep.stat().st_mode & 0o777 == 0o640
        return 1, "the sp install (not run here)"
    ctx = sp_cutover.Ctx(pack=pk, timers_file=host["timers"], runner=runner)
    with pytest.raises(sp_cutover.Refused):
        sp_cutover.step_install(ctx)
    st = world["real_env"].stat()
    assert owners == [(st.st_uid, st.st_gid)]
    assert seen[0][:4] == ["runuser", "-u", "sp", "--"]
    assert seen[0][-2:] == ["--env-kept-copy", str(world["real_env"].parent / "checkout.env.pre-scrub-20261026T134400Z")]
    assert not [q for q in host["h"].rglob("*") if "pre-scrub" in q.name]


def test_168_3_architect_682_the_sp_install_edits_only_against_the_copy_it_was_named(world, host, monkeypatch, capsys):
    """The `sp` install scrubs with the copy root named (--env-kept-copy), and edits nothing unless that copy holds the
    placed .env's bytes: a missing or different copy is a receipted refusal, the .env left as the pack's."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    named = world["real_env"].parent / "checkout.env.pre-scrub-20261026T134400Z"
    named.write_bytes(PACK_ENV_168.encode())
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    argv = ["install", "--pack", str(pk), "--timers-file", str(host["timers"]), "--env-kept-copy", str(named)]
    assert sp_cutover.main(argv, runner=FakeSystemctl(active=host["timers"].read_text().split())) == 0
    r = _lines(world["real_receipts"])[-1]
    assert r["env_kept_copy"] == str(named) and r["env_removed"] == ["SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY",
                                                                     "SP_HOST_ADDR"]
    assert list(world["real_env"].parent.glob("checkout.env.pre-scrub-*")) == [named]   # no second copy written

    pk2 = _pack_168(world, host, monkeypatch, PACK_ENV_168, name="pack_20261026T1341")
    named.write_bytes(b"NOT=the pack's .env\n")
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    capsys.readouterr()
    argv = ["install", "--pack", str(pk2), "--timers-file", str(host["timers"]), "--env-kept-copy", str(named)]
    assert sp_cutover.main(argv, runner=FakeSystemctl(active=host["timers"].read_text().split())) == 1
    r = _lines(world["real_receipts"])[-1]
    assert r["exit"] == 1 and "no kept copy of the placed .env" in r["env_scrub_error"] and r["env_removed"] == []
    assert (host["h"] / ".env").read_bytes() == PACK_ENV_168.encode()
    for v in VALUES_168:
        assert v not in capsys.readouterr().out and v not in world["real_receipts"].read_text()


@pytest.mark.parametrize("swap", ["symlink", "other_bytes"])
def test_168_3_codex_682_root_never_copies_a_swapped_pack_env(world, host, monkeypatch, swap):
    """Codex on #682 (P1): the pack is the service user's, so root opens its .env without following a symlink and
    copies it only when its bytes are the manifest's: a name swapped after the plan read it (a symlink to a
    root-readable file, or other bytes) is never copied into the group-readable copy; install refuses first."""
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")
    secret = world["tmp"] / "root-only.txt"
    secret.write_text("ROOT_ONLY=never-copied\n")
    real_plan = sp_cutover._scrub_plan

    def plan_then_swap(ctx, man):
        out = real_plan(ctx, man)
        pe = ctx.pack / sp_migrate.ENV
        pe.unlink()
        if swap == "symlink":
            pe.symlink_to(secret)
        else:
            pe.write_text("ROOT_ONLY=never-copied\n")
        return out
    monkeypatch.setattr(sp_cutover, "_scrub_plan", plan_then_swap)
    called = []
    monkeypatch.setattr(sp_migrate, "install", lambda pack, replace: called.append(pack) or 0)
    assert _install_168(host, pk) == 1
    assert called == [] and not list(world["real_env"].parent.glob("checkout.env.pre-scrub-*"))
    r = _lines(world["real_receipts"])[-1]
    assert "the .env copy could not be kept" in r["refused"] and "never-copied" not in world["real_receipts"].read_text()


def test_168_3_architect_682_a_copy_that_cannot_be_kept_refuses_before_anything_is_installed(
        world, host, monkeypatch):
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")

    def denied(path, data, owner=None, mode=None):
        raise PermissionError(13, "Permission denied", str(path))
    monkeypatch.setattr(sp_cutover, "_write_private", denied)
    called = []
    monkeypatch.setattr(sp_migrate, "install", lambda pack, replace: called.append(pack) or 0)
    assert _install_168(host, pk) == 1
    assert called == []
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "install" and "the .env copy could not be kept" in r["refused"] and "nothing installed" in \
        r["refused"] and r["env_scrub_planned"] == ["SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY", "SP_HOST_ADDR"]
    assert (host["h"] / ".env").read_bytes() == b"DATABASE_URL=sqlite:///./data/sports.db\n"


def test_168_3_architect_682_an_install_that_never_placed_the_env_names_the_unused_copy(world, host, monkeypatch, capsys):
    pk = _pack_168(world, host, monkeypatch, PACK_ENV_168)
    (host["h"] / ".env").write_text("DATABASE_URL=sqlite:///./data/sports.db\n")

    def failed_first(pack, replace):
        raise SystemExit("✗ injected failure before the .env was placed")
    monkeypatch.setattr(sp_migrate, "install", failed_first)
    capsys.readouterr()
    assert _install_168(host, pk) == 1
    keep = next(world["real_env"].parent.glob("checkout.env.pre-scrub-*"))
    assert f"· the copy kept before install is unused, nothing was removed: {keep}" in capsys.readouterr().out
    r = _lines(world["real_receipts"])[-1]
    assert r["env_removed"] == [] and r["env_kept_copy"] == str(keep)
