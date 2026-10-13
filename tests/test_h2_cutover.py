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


def _real(world, host, step="run", runner=None):
    if runner is None:          # never the real systemctl in a test: the preflight reads the active timers (57.8)
        runner = FakeSystemctl(active=host["timers"].read_text().split())
    return sp_cutover.main([step, "--pack", str(world["pack"]), "--timers-file", str(host["timers"])],
                           runner=runner)


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


def test_57_8_the_list_corrected_by_hand_passes_and_the_receipt_counts_the_active_timers(world, host):
    fake = FakeSystemctl(active=host["timers"].read_text().split() + ["sp-intl-daily.timer"])
    host["timers"].write_text(host["timers"].read_text() + "sp-intl-daily.timer\n")   # the operator's hand
    assert _real(world, host, step="preflight", runner=fake) == 0
    r = _lines(world["real_receipts"])[-1]
    assert r["step"] == "preflight" and r["timers_active"] == 4 and r["timers"] == 4


def test_57_8_a_listed_timer_that_is_not_active_and_other_units_refuse_nothing(world, host):
    """Only an active sp timer off the list refuses: an inactive listed timer, a service, a non-sp timer do not."""
    listed = host["timers"].read_text().split()
    fake = FakeSystemctl(active=listed[1:] + ["sp-chain@mlb.service", "apt-daily.timer"])
    assert _real(world, host, step="preflight", runner=fake) == 0
    assert _lines(world["real_receipts"])[-1]["timers_active"] == len(listed) - 1


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
