"""F2.5 EXPORTS MIRROR (ARCHITECT 2026-10-03): host/<date>/<file> + host/latest/<kind>.json, 14-day
retention, both writers on one branch, the compare tool + Action shipped, weekly squash; the sp_run
hook is non-fatal and off until configured. Uses a LOCAL bare repo as the remote (no network)."""
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import exports_mirror as em  # noqa: E402

TODAY = date(2026, 10, 3)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_operator_env_files(monkeypatch, tmp_path):
    """sp_common.setting reads host.env and the checkout's .env after the environment (item 8b): tests see
    neither, so an operator's files never leak into them."""
    monkeypatch.setattr(em.c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(em.c, "_DOTENV_CACHE", {})


def _mt(d: date, h=12):
    return datetime(d.year, d.month, d.day, h, tzinfo=timezone.utc).timestamp()


def _exports(tmp, files):
    ex = tmp / "exports"
    (ex / "intl_daily").mkdir(parents=True)                 # subdirectories are never mirrored
    (ex / "intl_daily" / "raw.json").write_text("{}")
    for name, d, body in files:
        p = ex / name
        p.write_text(body)
        os.utime(p, (_mt(d), _mt(d)))
    return ex


def _remote(tmp):
    r = tmp / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(r)], check=True)
    return str(r)


def _tree(remote, tmp):
    co = tmp / f"co{time.time_ns()}"
    subprocess.run(["git", "clone", "-q", remote, str(co)], check=True)
    return co, sorted(str(p.relative_to(co)) for p in co.rglob("*") if p.is_file() and ".git" not in p.parts)


def test_kinds_and_plan():
    assert em.kind_of("fixtures_NCAA_2026-10-03.json") == "fixtures_NCAA"
    assert em.kind_of("unl_shadow_2026-10-03_1200.json") == "unl_shadow"
    assert em.kind_of("fixtures_EFL_2026-10-01_to_2026-10-07.json") == "fixtures_EFL"
    assert em.kind_of("window_24h.json") == "window_24h"
    pl = em.plan([("nhl_shadow_2026-10-02_1600.json", _mt(date(2026, 10, 2))),
                  ("nhl_shadow_2026-10-03_1600.json", _mt(date(2026, 10, 3))),
                  ("old_2026-09-01.json", _mt(date(2026, 9, 1))), ("notes.txt", _mt(TODAY))], "host", TODAY)
    assert set(pl["dated"]) == {"host/2026-10-02/nhl_shadow_2026-10-02_1600.json",
                                "host/2026-10-03/nhl_shadow_2026-10-03_1600.json"}      # 14-day window; .json/.md only
    assert pl["latest"] == {"host/latest/nhl_shadow.json": "nhl_shadow_2026-10-03_1600.json"}


def test_the_coverage_file_is_mirrored_dated_and_as_latest_coverage(tmp_path):
    """ARCHITECT 2026-10-18, addendum 125 item 2(a) (#589): "the mirror carries it (laptop/latest/coverage.json,
    host/latest after the cutover)". coverage_<date>.json (`coverage --json`'s default name) is a kind like any other:
    its dated folder (the file's UTC mtime, as for every file) and latest/coverage.json, the newest day's file. The
    writer's hidden temporary (.coverage_<date>.json.<pid>.tmp) is never taken. No mirror code changed for it."""
    import coverage_map as cm
    assert em.kind_of(Path(cm.default_out(date(2026, 10, 3))).name) == "coverage"
    pl = em.plan([("coverage_2026-10-02.json", _mt(date(2026, 10, 2))),
                  ("coverage_2026-10-03.json", _mt(date(2026, 10, 3))),
                  (".coverage_2026-10-03.json.4242.tmp", _mt(date(2026, 10, 3)))], "laptop", TODAY)
    assert set(pl["dated"]) == {"laptop/2026-10-02/coverage_2026-10-02.json",
                                "laptop/2026-10-03/coverage_2026-10-03.json"}
    assert pl["latest"] == {"laptop/latest/coverage.json": "coverage_2026-10-03.json"}
    ex = _exports(tmp_path, [("coverage_2026-10-03.json", date(2026, 10, 3), '{"kind": "coverage_v1"}')])
    remote = _remote(tmp_path)
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 2
    _, tree = _tree(remote, tmp_path)
    assert {"host/2026-10-03/coverage_2026-10-03.json", "host/latest/coverage.json"} <= set(tree)


def test_host_and_laptop_push_retention_latest_and_tools(tmp_path):
    remote = _remote(tmp_path)
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}'),
                             ("fixtures_NHL_2026-10-02.json", TODAY - timedelta(days=1), '{"a":0}')])
    r = em.push("host", ex, "nhl-daily step 4", remote, tmp_path / "host_clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 3
    again = em.push("host", ex, "nhl-daily step 5", remote, tmp_path / "host_clone", today=TODAY)
    assert again == {"role": "host", "pushed": False, "copied": 0, "pruned": [], "why": "nothing changed"}
    lex = _exports(tmp_path / "lap", [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    assert em.push("laptop", lex, "morning", remote, tmp_path / "lap_clone", today=TODAY)["pushed"]
    co, files = _tree(remote, tmp_path)
    assert "host/2026-10-03/fixtures_NHL_2026-10-03.json" in files and "host/latest/fixtures_NHL.json" in files
    assert "laptop/latest/fixtures_NHL.json" in files                   # both writers kept on one branch
    assert (co / "host/latest/fixtures_NHL.json").read_text() == '{"a":1}'
    assert "tools/compare_exports.py" in files and ".github/workflows/compare.yml" in files
    assert not any("intl_daily" in f for f in files)
    assert (ex / "fixtures_NHL_2026-10-03.json").exists()               # copies only: exports/ untouched
    later = TODAY + timedelta(days=14)                                  # 10-02 and 10-03 now past retention
    ex2 = _exports(tmp_path / "x2", [("fixtures_NHL_2026-10-17.json", later, '{"a":2}')])
    r = em.push("host", ex2, "later", remote, tmp_path / "host_clone", today=later)
    assert sorted(r["pruned"]) == ["2026-10-02", "2026-10-03"]
    co, files = _tree(remote, tmp_path)
    assert not any(f.startswith("host/2026-10-0") for f in files) and "laptop/2026-10-03/fixtures_NHL_2026-10-03.json" in files
    assert (co / "host/latest/fixtures_NHL.json").read_text() == '{"a":2}'


def test_squash_leaves_one_commit_and_the_files(tmp_path):
    remote = _remote(tmp_path)
    ex = _exports(tmp_path, [("a_2026-10-03.json", TODAY, "1")])
    em.push("host", ex, "one", remote, tmp_path / "c", today=TODAY)
    (ex / "a_2026-10-03.json").write_text("2")
    em.push("host", ex, "two", remote, tmp_path / "c", today=TODAY)
    assert em.squash(remote, tmp_path / "c")["squashed"]
    co, files = _tree(remote, tmp_path)
    n = subprocess.run(["git", "-C", str(co), "rev-list", "--count", "HEAD"], capture_output=True, text=True).stdout
    assert n.strip() == "1" and "host/2026-10-03/a_2026-10-03.json" in files


def test_disabled_without_a_remote(monkeypatch, capsys):
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE", raising=False)
    assert em.main(["push"]) == 0 and "disabled" in capsys.readouterr().out


def test_sp_run_hook_is_non_fatal_and_off_by_default(monkeypatch, tmp_path):
    import sp_run
    seen = []
    monkeypatch.setattr(sp_run.c, "append_receipt", lambda r: seen.append(r))
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE", raising=False)
    sp_run.mirror_after_step("nhl-daily", 1, "sync-matches", "r1")
    assert seen == []                                                   # off until configured
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", str(tmp_path / "nowhere.git"))

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 90)
    monkeypatch.setattr(sp_run.subprocess, "run", boom)
    sp_run.mirror_after_step("nhl-daily", 2, "export-fixtures", "r1")   # never raises
    assert seen and seen[-1]["kind"] == "mirror" and seen[-1]["exit"] is None and "timed out" in seen[-1]["tail"][0]


def _action_step(clone: Path) -> str:
    """The `run:` script of the compare step, read from the SHIPPED workflow (no YAML dependency)."""
    lines = (clone / ".github/workflows/compare.yml").read_text().splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.strip() == "id: cmp")
    j = next(n for n in range(i, len(lines)) if lines[n].strip() == "run: |")
    ind = len(lines[j + 1]) - len(lines[j + 1].lstrip())
    body = []
    for ln in lines[j + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) < ind:
            break
        body.append(ln[ind:])
    return "\n".join(body)


def _run_action(clone: Path, tmp: Path) -> dict:
    out, summ = tmp / f"out{time.time_ns()}", tmp / f"sum{time.time_ns()}"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SP_WRITER_OF_RECORD")}
    env.update(GITHUB_OUTPUT=str(out), GITHUB_STEP_SUMMARY=str(summ))
    subprocess.run(["bash", "-c", _action_step(clone)], cwd=clone, env=env, check=True,
                   capture_output=True, text=True)
    return dict(ln.split("=", 1) for ln in out.read_text().splitlines())


def test_shipped_tree_runs_in_a_clean_checkout_clean_divergent_and_error(tmp_path):
    """PR #261 review: the mirror shipped compare_exports.py without sp_common.py (ModuleNotFoundError),
    and the Action read every non-zero exit as DIVERGENT. A fresh clone of the mirror, outside this repo,
    with no PYTHONPATH, must give CLEAN, DIVERGENT and ERROR as three different results."""
    remote = _remote(tmp_path)
    body = '[{"utc_date":"2026-10-03T23:00Z","home_team":"A","away_team":"B","p":0.5}]'
    for role in ("host", "laptop"):
        ex = _exports(tmp_path / role, [("fixtures_NHL_2026-10-03.json", TODAY, body)])
        assert em.push(role, ex, "receipt", remote, tmp_path / f"{role}_clone", today=TODAY)["pushed"]
    co, files = _tree(remote, tmp_path)
    assert "tools/compare_exports.py" in files and not (co / "tools" / "sp_common.py").exists()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SP_WRITER_OF_RECORD")}

    def cli(*args):
        return subprocess.run([sys.executable, "tools/compare_exports.py", *args], cwd=co, env=env,
                              capture_output=True, text=True)

    r = cli("laptop/2026-10-03", "host/2026-10-03", "--since", "0")
    assert r.returncode == 0, r.stderr
    assert "ModuleNotFoundError" not in r.stderr and r.stdout.strip().endswith("VERDICT: CLEAN")
    assert _run_action(co, tmp_path) == {"date": "2026-10-03", "state": "success", "desc": "CLEAN · 2026-10-03"}

    (co / "host/2026-10-03/fixtures_NHL_2026-10-03.json").write_text(body.replace("0.5", "0.6"))
    r = cli("laptop/2026-10-03", "host/2026-10-03", "--since", "0")
    assert r.returncode == 1 and r.stdout.strip().endswith("VERDICT: DIVERGENT")
    assert _run_action(co, tmp_path)["state"] == "failure"

    r = cli("laptop/2026-10-03", "host/2026-10-99", "--since", "0")       # a side that is not there
    assert r.returncode == 2 and "VERDICT: ERROR" in r.stdout
    r = cli("laptop/2026-10-03")                                          # a usage error
    assert r.returncode == 2 and "VERDICT: ERROR" in r.stdout
    (co / "tools/compare_exports.py").write_text("raise RuntimeError('broken comparator')\n")
    got = _run_action(co, tmp_path)                       # crashes before main: Python exits 1, no VERDICT
    assert got["state"] == "error" and "not a data verdict" in got["desc"]


def test_zero_compared_is_no_coverage_never_clean(tmp_path):
    """PR #261 review: a real mirror whose dated folders hold only Markdown gave "CLEAN (0 compared)" and
    state=success. Zero compared is NO-COVERAGE (exit 3) and the Action posts error, in a clean checkout of
    the shipped tree; an empty side folder likewise."""
    remote = _remote(tmp_path)
    for role in ("host", "laptop"):                                      # Markdown-only dated folders
        ex = _exports(tmp_path / role, [("morning_receipt_2026-10-03.md", TODAY, "# receipt\n")])
        assert em.push(role, ex, "md only", remote, tmp_path / f"{role}_clone", today=TODAY)["pushed"]
    co, files = _tree(remote, tmp_path)
    assert "host/2026-10-03/morning_receipt_2026-10-03.md" in files
    assert not any(f.endswith(".json") and f.startswith(("host/2", "laptop/2")) for f in files)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SP_WRITER_OF_RECORD")}

    def cli(*args):
        return subprocess.run([sys.executable, "tools/compare_exports.py", *args], cwd=co, env=env,
                              capture_output=True, text=True)

    r = cli("laptop/2026-10-03", "host/2026-10-03", "--since", "0")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "coverage: 0 JSON file(s) compared" in r.stdout and "laptop 1, host 1" in r.stdout
    assert "CLEAN" not in r.stdout.replace("not a clean verdict", "")
    assert r.stdout.strip().endswith("VERDICT: NO-COVERAGE (0 compared) — not a data verdict")
    got = _run_action(co, tmp_path)
    assert got["state"] == "error" and got["desc"].startswith("NO COVERAGE · 2026-10-03"), got

    (co / "empty_l").mkdir(), (co / "empty_h").mkdir()                   # empty side folders
    r = cli("empty_l", "empty_h", "--since", "0")
    assert r.returncode == 3 and "VERDICT: NO-COVERAGE" in r.stdout
    assert "coverage: 0 JSON file(s) compared" in r.stdout and "laptop 0, host 0" in r.stdout
    for p in (co / "host" / "2026-10-03").iterdir():                     # the shipped workflow on empty folders
        p.unlink()
    for p in (co / "laptop" / "2026-10-03").iterdir():
        p.unlink()
    got = _run_action(co, tmp_path)
    assert got["state"] == "error" and "NO COVERAGE" in got["desc"], got


def test_the_shipped_action_lists_coverage_as_machine_state_never_divergent(tmp_path):
    """#592 RULED (ARCHITECT 2026-10-18, addendum 128 item 3): "the compare treats kind `coverage` as "machine
    state": listed by presence on each side (one side, both sides, neither), never compared for content, never
    DIVERGENT [...] Dated and latest copies both travel". Both writers push one identical fixtures file; the laptop
    alone, then both with different content, push coverage_<date>.json. Both copies travel (dated and latest), and
    the SHIPPED tool in a clean checkout of the mirror (no sp_common, no exports_mirror) posts CLEAN each time."""
    remote = _remote(tmp_path)
    body = '[{"utc_date":"2026-10-03T23:00Z","home_team":"A","away_team":"B","p":0.5}]'
    lap_cov = '{"kind": "coverage_v1", "now": "2026-10-03T12:00:00Z", "competitions": [{"groups": [{"state": "ahead"}]}]}'
    host_cov = '{"kind": "coverage_v1", "now": "2026-10-03T18:40:00Z", "competitions": [{"groups": [{"state": "due"}]}]}'
    host_ex = _exports(tmp_path / "host", [("fixtures_NHL_2026-10-03.json", TODAY, body)])
    assert em.push("host", host_ex, "t", remote, tmp_path / "host_clone", today=TODAY)["pushed"]
    lap_ex = _exports(tmp_path / "laptop", [("fixtures_NHL_2026-10-03.json", TODAY, body),
                                            ("coverage_2026-10-03.json", TODAY, lap_cov)])
    assert em.push("laptop", lap_ex, "t", remote, tmp_path / "laptop_clone", today=TODAY)["pushed"]
    co, files = _tree(remote, tmp_path)
    assert {"laptop/2026-10-03/coverage_2026-10-03.json", "laptop/latest/coverage.json"} <= set(files)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SP_WRITER_OF_RECORD")}

    def cli(*args):
        return subprocess.run([sys.executable, "tools/compare_exports.py", *args], cwd=co, env=env,
                              capture_output=True, text=True)

    r = cli("laptop/2026-10-03", "host/2026-10-03", "--since", "0")                       # one side
    assert r.returncode == 0, r.stdout + r.stderr
    assert "machine-state files: coverage laptop yes / host no" in r.stdout.splitlines()
    assert "only on laptop" not in r.stdout and r.stdout.strip().endswith("VERDICT: CLEAN")
    assert _run_action(co, tmp_path) == {"date": "2026-10-03", "state": "success", "desc": "CLEAN · 2026-10-03"}
    host_ex2 = _exports(tmp_path / "host2", [("fixtures_NHL_2026-10-03.json", TODAY, body),
                                             ("coverage_2026-10-03.json", TODAY, host_cov)])
    assert em.push("host", host_ex2, "t", remote, tmp_path / "host_clone", today=TODAY)["pushed"]
    co, files = _tree(remote, tmp_path)
    assert {"host/2026-10-03/coverage_2026-10-03.json", "host/latest/coverage.json"} <= set(files)
    for folder in ("2026-10-03", "latest"):                                              # both, content differs
        r = cli(f"laptop/{folder}", f"host/{folder}", "--since", "0")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "machine-state files: coverage laptop yes / host yes" in r.stdout.splitlines()
        assert "✗" not in r.stdout and r.stdout.strip().endswith("VERDICT: CLEAN")
    assert _run_action(co, tmp_path)["state"] == "success"


def test_first_push_after_failed_attempts_is_not_nothing_changed(tmp_path):
    """ARCHITECT 2026-10-03 (host): the remote was set in host.env before the deploy key worked, so the chain
    hook's pushes COMMITTED in the working clone and failed to push. The hand-run "first" push then compared
    against that local commit and printed "not pushed — nothing changed" over an EMPTY remote. The change test
    is against the remote's tip: unpushed local commits are pushed."""
    remote = tmp_path / "later.git"                                   # not there yet: every push fails
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    clone = tmp_path / "host_clone"
    for step in (1, 2):                                               # the chain hook, before the key works
        r = em.push("host", ex, f"nhl-daily step {step}", str(remote), clone, today=TODAY)
        assert not r["pushed"] and r["why"].startswith("push rejected"), r
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)   # key now works
    r = em.push("host", ex, "hand run", str(remote), clone, today=TODAY)
    assert r["pushed"], r
    assert r["unpushed_before"] >= 1 and r["copied"] == 0             # the earlier commit carried the files
    _, files = _tree(str(remote), tmp_path)
    assert "host/2026-10-03/fixtures_NHL_2026-10-03.json" in files and "tools/compare_exports.py" in files
    again = em.push("host", ex, "next", str(remote), clone, today=TODAY)
    assert again["pushed"] is False and again["why"] == "nothing changed"   # now genuinely nothing


def test_first_push_to_an_empty_remote_from_a_fresh_clone(tmp_path):
    remote = _remote(tmp_path)
    ex = _exports(tmp_path, [(f"f{i}_2026-10-03.json", TODAY, str(i)) for i in range(18)])
    r = em.push("host", ex, "first", remote, tmp_path / "c", today=TODAY)
    assert r["pushed"] and r["copied"] == 36, r                       # 18 dated + 18 latest
    _, files = _tree(remote, tmp_path)
    assert sum(f.startswith("host/2026-10-03/") for f in files) == 18


def test_key_path_resolution_and_keygen_into_a_writable_path(tmp_path, monkeypatch, capsys):
    """keygen's /etc/sports-predictor default is not writable by sp: --key PATH is accepted, and with no
    env the key resolves to an existing /etc key, else ~/.ssh/sp_exports_deploy_key (push and keygen agree)."""
    monkeypatch.delenv("SP_EXPORTS_MIRROR_KEY", raising=False)
    monkeypatch.setattr(em, "ETC_KEY", tmp_path / "etc-ro" / "exports_deploy_key")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert em.key_path() == tmp_path / "home" / ".ssh" / "sp_exports_deploy_key"
    (tmp_path / "etc-ro").mkdir()
    em.ETC_KEY.write_text("k")
    assert em.key_path() == em.ETC_KEY                                # an installed /etc key wins
    monkeypatch.setenv("SP_EXPORTS_MIRROR_KEY", str(tmp_path / "custom"))
    assert em.key_path() == tmp_path / "custom"                       # the env wins over both
    if shutil.which("ssh-keygen"):
        assert em.main(["keygen", "--key", str(tmp_path / "k" / "deploy")]) == 0
        assert (tmp_path / "k" / "deploy").exists() and "ssh-ed25519" in capsys.readouterr().out


def test_keygen_into_an_unwritable_dir_names_the_root_step(tmp_path, capsys):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(ro, os.W_OK):                                    # running as root: nothing to refuse
            return
        assert em.keygen(str(ro / "exports_deploy_key")) == 2
        out = capsys.readouterr().out
        assert "--key" in out and "sudo" in out and "SP_EXPORTS_MIRROR_KEY" in out
    finally:
        ro.chmod(0o700)


def test_settings_come_from_the_checkouts_env_and_the_environment_wins(monkeypatch, tmp_path, capsys):
    """ARCHITECT 2026-10-07 (addendum 2 item 8b): the laptop's .env carries the mirror's settings through
    sp_common.setting, so the documented morning line cannot be half-typed."""
    for k in ("SP_EXPORTS_MIRROR_REMOTE", "SP_EXPORTS_MIRROR_KEY", "SP_EXPORTS_MIRROR_ROLE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(em.c, "_DOTENV_CACHE", {"SP_EXPORTS_MIRROR_REMOTE": "https://example.invalid/x.git",
                                                "SP_EXPORTS_MIRROR_KEY": str(tmp_path / "dotenv-key")})
    assert em.c.setting("SP_EXPORTS_MIRROR_REMOTE") == "https://example.invalid/x.git"
    assert em.key_path() == tmp_path / "dotenv-key"
    monkeypatch.setenv("SP_EXPORTS_MIRROR_KEY", str(tmp_path / "env-key"))
    assert em.key_path() == tmp_path / "env-key"                      # the environment wins
    (tmp_path / "host.env").write_text("SP_EXPORTS_MIRROR_ROLE=laptop\n")
    monkeypatch.setattr(em.c, "HOST_ENV", tmp_path / "host.env")
    assert em.c.setting("SP_EXPORTS_MIRROR_ROLE") == "laptop" and em.c.setting("SP_NOPE", "d") == "d"


def test_a_missing_key_on_an_ssh_remote_is_a_stated_refusal(monkeypatch, tmp_path, capsys):
    """ARCHITECT 2026-10-07 (addendum 4 F): a KEY naming a file that does not exist ran git keyless and was
    refused; the mirror now refuses first, naming the path. An HTTPS remote never needs the key."""
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", "git@github.com:anthonyevans29/Sports-Predictor-exports.git")
    monkeypatch.setenv("SP_EXPORTS_MIRROR_KEY", str(tmp_path / "sp_exports_laptop"))
    monkeypatch.setenv("SP_EXPORTS_MIRROR_DIR", str(tmp_path / "clone"))
    assert em.main(["push", "--exports", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "REFUSED" in out and "sp_exports_laptop" in out and "SP_EXPORTS_MIRROR_KEY names it" in out
    assert not (tmp_path / "clone").exists()                        # refused before any git step
    monkeypatch.delenv("SP_EXPORTS_MIRROR_KEY")
    monkeypatch.setattr(em, "ETC_KEY", tmp_path / "no-etc-key")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert em.key_refusal("git@github.com:a/b.git").endswith("never falls back silently.")
    assert "the default path" in em.key_refusal("ssh://git@github.com/a/b.git")
    assert em.key_refusal("https://github.com/a/b.git") is None
    assert em.ssh_remote("example.com:owner/repo.git") and em.ssh_remote("git@github.com:a/b.git")   # userless scp form
    assert not em.ssh_remote("https://github.com/a/b.git") and not em.ssh_remote("file:///tmp/x.git")
    for r in ("u@h:path", "[::1]:path", "git+ssh://example.com/path", "ssh+git://h/p", "ssh://git@h:22/p"):
        assert em.ssh_remote(r), r                                     # every form git runs ssh for (Codex on #335)
    for r in ("http://h/p.git", "git://h/p.git", "/srv/x.git", "./x.git", "../x.git", "~/x.git"):
        assert not em.ssh_remote(r), r
    (tmp_path / "home" / ".ssh").mkdir(parents=True)
    (tmp_path / "home" / ".ssh" / "sp_exports_deploy_key").write_text("k")
    assert em.key_refusal("git@github.com:a/b.git") is None
    assert not em.ssh_remote(str(tmp_path / "bare.git"))             # a local path remote (the tests' own)


def test_a_rewritten_https_remote_never_runs_ssh_keyless(monkeypatch, tmp_path):
    """Codex on #335: a pushInsteadOf rewrite can turn an HTTPS remote into SSH at push time. With no key file the
    mirror hands git a refusing SSH command, so no SSH transport runs on an agent or default identity."""
    seen, real_run = {}, subprocess.run
    monkeypatch.setenv("SP_EXPORTS_MIRROR_KEY", str(tmp_path / "missing"))
    monkeypatch.setattr(em.subprocess, "run", lambda *a, **k: seen.update(k["env"]) or None)
    em._git(tmp_path, "push")
    assert seen["GIT_SSH_COMMAND"] == em.REFUSE_SSH
    r = real_run(["sh", "-c", em.REFUSE_SSH + " git@github.com git-receive-pack x"], capture_output=True, text=True)
    assert r.returncode != 0 and "REFUSED" in r.stderr
    (tmp_path / "key").write_text("k")
    monkeypatch.setenv("SP_EXPORTS_MIRROR_KEY", str(tmp_path / "key"))
    em._git(tmp_path, "push")
    assert seen["GIT_SSH_COMMAND"].startswith("ssh -i ") and "IdentitiesOnly=yes" in seen["GIT_SSH_COMMAND"]


# ---- THE KEPT SUBTREE (ARCHITECT 2026-11-04, addendum 250 item 4, #826) --------------------------------------------
# "exports_mirror.py gains ONE kept subtree: `exports/bulletins/**` is copied verbatim to `<role>/bulletins/**` (suffixes
# .md and .png there; the top-level rule is unchanged), NEVER pruned by RETENTION_DAYS (the dated-folder rule applies to
# `<role>/<date>/` only; the weekly squash keeps files, as it does today), and NO JSON is ever written under it, so the
# compare's `*.json` Action glob never sees a bulletin and the compare is untouched (no new kind, no new mask, kind_of
# unchanged); tests pin all three (copied; not pruned; a .json planted under it is refused by the renderer's writer and
# ignored by the plan)." The writer's refusal comes with the renderer (step 1's second PR); these pin the plan's half.
# Invented teams and match ids only: no real bulletin, closing row or ticker.

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))                   # binary bytes: copied verbatim, never re-encoded
B_CLOSE = "bulletins/NFL/2026-10-03/900001_alpha-owls_at_beta-hawks_closing"
B_SLATE = "bulletins/SOCCER/2026-10-03/900002_gamma-fc_at_delta-united_slate"
B_WEEK = "bulletins/SOCCER/weeks/2026-27_7"


def _bulletins(ex: Path, files: dict, mtime: float | None = None) -> Path:
    """Writes exports/bulletins/** (rel path under exports/ -> bytes); an old mtime proves no window applies."""
    for rel, body in files.items():
        p = ex / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
    return ex


def _three(ex: Path, mtime: float | None = None) -> dict:
    files = {f"{B_CLOSE}.md": b"# Alpha Owls at Beta Hawks\nPASS\n", f"{B_CLOSE}.png": PNG,
             f"{B_SLATE}.md": b"# Gamma FC at Delta United\n", f"{B_SLATE}.png": PNG[::-1],
             f"{B_WEEK}.md": b"# week 7\n", f"{B_WEEK}.png": PNG + b"wk"}
    _bulletins(ex, files, mtime)
    return files


def test_bulletins_are_copied_verbatim_to_role_bulletins_and_the_top_level_rule_is_unchanged(tmp_path):
    """Pin 1, copied: every .md and .png under exports/bulletins/ lands at <role>/bulletins/<the same relative path>,
    byte for byte, nested <FAMILY>/<date>/ and <FAMILY>/weeks/ kept as they are, whatever the file's mtime (60 days
    old here: no retention window applies to the subtree). The top-level rule is unchanged: the dated and latest
    copies are the same as without the subtree, latest/ holds no bulletin, and the other subfolders still are not
    mirrored."""
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    files = _three(ex, mtime=_mt(TODAY - timedelta(days=60)))
    pl = em.bulletin_plan(ex, "host")
    assert pl == {"kept": {f"host/{rel}": ex / rel for rel in files}, "skipped": []}
    top = em.plan([(p.name, p.stat().st_mtime) for p in ex.iterdir() if p.is_file()], "host", TODAY)
    assert top == {"dated": {"host/2026-10-03/fixtures_NHL_2026-10-03.json": "fixtures_NHL_2026-10-03.json"},
                   "latest": {"host/latest/fixtures_NHL.json": "fixtures_NHL_2026-10-03.json"}}
    remote = _remote(tmp_path)
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 2 + 6 and "skipped" not in r, r
    co, tree = _tree(remote, tmp_path)
    assert sorted(f for f in tree if "/bulletins/" in f or f.startswith("host/bulletins")) == sorted(
        f"host/{rel}" for rel in files)
    for rel, body in files.items():
        assert (co / "host" / rel).read_bytes() == body                    # verbatim
    assert not any(f.startswith("host/latest/") and "bulletin" in f for f in tree)
    assert not any("intl_daily" in f for f in tree)                        # other subfolders: still not mirrored
    assert {"host/2026-10-03/fixtures_NHL_2026-10-03.json", "host/latest/fixtures_NHL.json"} <= set(tree)
    lap = _exports(tmp_path / "lap", [])
    _three(lap)
    assert em.push("laptop", lap, "t", remote, tmp_path / "lap_clone", today=TODAY)["pushed"]
    _, tree = _tree(remote, tmp_path)
    assert {f"laptop/{rel}" for rel in files} <= set(tree) and {f"host/{rel}" for rel in files} <= set(tree)
    again = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert again == {"role": "host", "pushed": False, "copied": 0, "pruned": [], "why": "nothing changed"}
    (ex / f"{B_CLOSE}.md").write_bytes(b"# re-rendered\n")                 # a changed bulletin is copied again
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 1
    co, _ = _tree(remote, tmp_path)
    assert (co / "host" / f"{B_CLOSE}.md").read_bytes() == b"# re-rendered\n"


def test_bulletins_are_never_pruned_a_removed_source_stays_and_the_squash_keeps_them(tmp_path):
    """Pin 2, not pruned: 30 days on, the dated folder of the first push is pruned (the dated-folder rule, unchanged)
    and <role>/bulletins/** is not, its own nested <date>/ folders included. A bulletin removed from exports/ stays in
    the mirror, as the top-level rule leaves a dated copy whose source is gone until its folder expires (the push copies
    and never deletes for a missing source; the subtree never expires). The weekly squash keeps every file."""
    remote, clone = _remote(tmp_path), tmp_path / "clone"
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    files = _three(ex)
    assert em.push("host", ex, "t", remote, clone, today=TODAY)["pushed"]
    later = TODAY + timedelta(days=30)
    ex2 = _exports(tmp_path / "x2", [("fixtures_NHL_2026-11-02.json", later, '{"a":2}')])   # no bulletins/ at all
    assert not (ex2 / "bulletins").exists()
    r = em.push("host", ex2, "later", remote, clone, today=later)
    assert r["pushed"] and r["pruned"] == ["2026-10-03"] and "skipped" not in r, r
    assert em.expired(clone / "host", later + timedelta(days=365)) == [clone / "host" / "2026-11-02"]
    co, tree = _tree(remote, tmp_path)
    assert not any(f.startswith("host/2026-10-03/") for f in tree)
    assert {f"host/{rel}" for rel in files} <= set(tree)
    assert (co / "host" / f"{B_CLOSE}.png").read_bytes() == PNG
    assert em.squash(remote, clone)["squashed"]
    co, tree = _tree(remote, tmp_path)
    n = subprocess.run(["git", "-C", str(co), "rev-list", "--count", "HEAD"], capture_output=True, text=True).stdout
    assert n.strip() == "1" and {f"host/{rel}" for rel in files} <= set(tree)
    assert "host/2026-11-02/fixtures_NHL_2026-11-02.json" in tree


def test_a_json_or_any_other_suffix_under_bulletins_is_ignored_by_the_plan_and_receipted(tmp_path, monkeypatch, capsys):
    """Pin 3, the plan's half: a .json planted under exports/bulletins/ (and any suffix but .md / .png, an upper-case
    .PNG included) is never copied, so no JSON is ever written under <role>/bulletins/. It is not silent (law 2): the
    push's result carries `skipped` (path, reason) and its console line the count by reason, the line the chain hooks'
    receipts keep. The renderer's writer refusing a .json is the second PR's (it does not exist yet)."""
    ex = _exports(tmp_path, [])
    files = _three(ex)
    _bulletins(ex, {"bulletins/NFL/2026-10-03/planted.json": b'{"rows": []}', "bulletins/planted.json": b"{}",
                    "bulletins/NFL/notes.txt": b"x", "bulletins/NFL/2026-10-03/card.PNG": PNG,
                    "bulletins/NFL/2026-10-03/.x.md.4242.tmp": b"half"})
    pl = em.bulletin_plan(ex, "host")
    assert set(pl["kept"]) == {f"host/{rel}" for rel in files}
    assert not any(d.endswith(".json") for d in pl["kept"])
    assert sorted(pl["skipped"]) == sorted([
        ("bulletins/NFL/2026-10-03/planted.json", "suffix: not .md or .png"),
        ("bulletins/planted.json", "suffix: not .md or .png"),
        ("bulletins/NFL/notes.txt", "suffix: not .md or .png"),
        ("bulletins/NFL/2026-10-03/card.PNG", "suffix: not .md or .png"),
        ("bulletins/NFL/2026-10-03/.x.md.4242.tmp", "suffix: not .md or .png")])
    remote = _remote(tmp_path)
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 6 and sorted(r["skipped"]) == sorted(pl["skipped"]), r
    _, tree = _tree(remote, tmp_path)
    under = [f for f in tree if f.startswith("host/bulletins/")]
    assert sorted(under) == sorted(f"host/{rel}" for rel in files)
    assert not any(f.endswith(".json") for f in under)                      # no JSON is ever written under it
    again = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert again["why"] == "nothing changed" and len(again["skipped"]) == 5  # receipted on every push
    for k in ("SP_EXPORTS_MIRROR_KEY", "SP_EXPORTS_MIRROR_ROLE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", remote)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_DIR", str(tmp_path / "clone"))
    (ex / f"{B_WEEK}.md").write_bytes(b"# week 7, rewritten\n")
    assert em.main(["push", "--exports", str(ex), "--label", "t"]) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("EXPORTS-MIRROR host: pushed 1 file(s)")
    assert line.endswith(" · bulletins: 5 skipped (suffix: not .md or .png 5)"), line


def test_the_subtree_absent_is_nothing_no_error(tmp_path):
    """No exports/bulletins/ (every machine today): an empty plan, no `skipped` key, the push exactly as before. No
    exports/ at all, or a FILE named bulletins at the top (not a .json or .md: the top-level rule ignores it), the
    same."""
    assert em.bulletin_plan(tmp_path / "missing", "host") == {"kept": {}, "skipped": []}
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    assert em.bulletin_plan(ex, "host") == {"kept": {}, "skipped": []}
    remote = _remote(tmp_path)
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 2 and "skipped" not in r
    (ex / "bulletins").write_text("not a folder")
    assert em.bulletin_plan(ex, "host") == {"kept": {}, "skipped": []}
    assert em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)["why"] == "nothing changed"
    _, tree = _tree(remote, tmp_path)
    assert not any("bulletins" in f for f in tree)


def test_symlinks_under_the_subtree_are_never_followed(tmp_path):
    """No symlink is followed, in or out of the subtree: a file link to a secret outside exports/bulletins/, a file
    link to a bulletin inside it, a broken link, a folder link to an outside folder holding a .md, and the subtree's
    own root as a link. Each is skipped with its reason; the outside bytes never reach the mirror; the real files
    still go."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("never mirrored\n")
    (outside / "dir").mkdir()
    (outside / "dir" / "inner.md").write_text("never mirrored either\n")
    ex = _exports(tmp_path, [])
    files = _three(ex)
    b = ex / "bulletins" / "NFL" / "2026-10-03"
    (b / "out_link.md").symlink_to(outside / "secret.md")
    (b / "in_link.md").symlink_to(ex / f"{B_CLOSE}.md")
    (b / "dangling.png").symlink_to(tmp_path / "nowhere.png")
    (ex / "bulletins" / "LINKED").symlink_to(outside / "dir", target_is_directory=True)
    pl = em.bulletin_plan(ex, "host")
    assert set(pl["kept"]) == {f"host/{rel}" for rel in files}
    assert sorted(pl["skipped"]) == sorted([
        ("bulletins/LINKED", "symlink: not followed"),
        ("bulletins/NFL/2026-10-03/dangling.png", "symlink: not followed"),
        ("bulletins/NFL/2026-10-03/in_link.md", "symlink: not followed"),
        ("bulletins/NFL/2026-10-03/out_link.md", "symlink: not followed")])
    remote = _remote(tmp_path)
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 6 and len(r["skipped"]) == 4
    co, tree = _tree(remote, tmp_path)
    assert sorted(f for f in tree if f.startswith("host/bulletins/")) == sorted(f"host/{rel}" for rel in files)
    assert not any("never mirrored" in (co / f).read_text(errors="replace") for f in tree if f.endswith(".md"))
    ex2 = _exports(tmp_path / "x2", [])                                     # the subtree's root itself a link
    (ex2 / "bulletins").symlink_to(outside, target_is_directory=True)
    assert em.bulletin_plan(ex2, "host") == {"kept": {}, "skipped": [("bulletins", "symlink: not followed")]}


def test_unusual_names_never_crash_the_plan_or_the_push(tmp_path, monkeypatch, capsys):
    """Item 1's slugs are ASCII, but the plan must not crash on any name: spaces, quotes, '#', '%', non-ASCII, a
    newline, a name that is not UTF-8 (copied as it is, printed escaped), a `.git` folder (git cannot carry it:
    skipped) and a folder that cannot be read (skipped with its reason, the rest still copied; the read is refused
    by a stand-in for os.scandir, since root, as in this container, reads a mode-000 folder anyway)."""
    ex = _exports(tmp_path, [])
    odd = {"bulletins/NFL/2026-10-03/a b 'c' #1 50%.md": b"spaces",
           "bulletins/SOCCER/2026-10-03/café_münchen_at_øst.md": b"utf8",
           "bulletins/SOCCER/2026-10-03/line\nbreak.png": PNG,
           "bulletins/SOCCER/.git/HEAD.md": b"never", "bulletins/SOCCER/.GIT/x.md": b"never"}
    _bulletins(ex, odd)
    want = {f"host/{rel}" for rel in odd if ".git" not in rel.lower()}
    skipped_want = [("bulletins/SOCCER/.GIT", "a .git path: git cannot carry it"),
                    ("bulletins/SOCCER/.git", "a .git path: git cannot carry it")]
    try:                                                                    # a byte name only some file systems take
        bad = Path(os.fsdecode(str(ex / "bulletins" / "NFL").encode() + b"/bad\xff.md"))
        bad.write_bytes(b"bytes")
        badj = Path(os.fsdecode(str(ex / "bulletins" / "NFL").encode() + b"/bad\xfe.json"))
        badj.write_bytes(b"{}")
        want.add("host/" + bad.relative_to(ex).as_posix())
        skipped_want.append((badj.relative_to(ex).as_posix(), "suffix: not .md or .png"))
    except (OSError, UnicodeError):
        bad = None
    locked = ex / "bulletins" / "LOCKED"
    locked.mkdir()
    (locked / "hidden.md").write_text("x")
    real_scandir = os.scandir

    def scandir(path="."):
        if Path(os.fsdecode(path)) == locked:
            raise PermissionError(13, "Permission denied", os.fsdecode(path))
        return real_scandir(path)
    monkeypatch.setattr(os, "scandir", scandir)                             # os.walk reads folders through it
    skipped_want.append(("bulletins/LOCKED", "unreadable folder: PermissionError"))
    pl = em.bulletin_plan(ex, "host")
    assert set(pl["kept"]) == want
    assert sorted(pl["skipped"]) == sorted(skipped_want)
    remote = _remote(tmp_path)
    for k in ("SP_EXPORTS_MIRROR_KEY", "SP_EXPORTS_MIRROR_ROLE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", remote)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_DIR", str(tmp_path / "clone"))
    assert em.main(["push", "--exports", str(ex), "--label", "odd"]) == 0
    out = capsys.readouterr().out
    assert f"pushed {len(want)} file(s)" in out and f"bulletins: {len(skipped_want)} skipped" in out
    if bad is not None:
        r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
        assert r["why"] == "nothing changed"
        assert ("bulletins/NFL/bad\\xfe.json", "suffix: not .md or .png") in r["skipped"]   # printable
    co = tmp_path / "co_odd"
    subprocess.run(["git", "clone", "-q", remote, str(co)], check=True)
    got = {p.relative_to(co).as_posix() for p in co.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert {f for f in got if f.startswith("host/bulletins/")} == want
    assert (co / "host" / "bulletins/SOCCER/2026-10-03/line\nbreak.png").read_bytes() == PNG
    assert "host/bulletins/LOCKED/hidden.md" not in got


def test_an_unreadable_or_vanished_bulletin_is_skipped_and_the_top_level_still_pushes(tmp_path, monkeypatch):
    """One bad bulletin never stops the push (review of this PR): a kept .md that lstat accepts but that cannot be
    opened (a 0600 file another user owns; refused here by a stand-in for open, since root, as in this container,
    reads a mode-000 file anyway) and a kept .png deleted between the plan and the copy are each skipped with the
    reason, on the result and the console line; the top-level dated and latest files and the other bulletins still go."""
    import builtins
    import io
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    files = _three(ex)
    locked, gone = ex / f"{B_CLOSE}.md", ex / f"{B_SLATE}.png"
    real_open, real_io_open, real_plan = builtins.open, io.open, em.bulletin_plan

    def refusing(f):
        def opener(file, *a, **k):
            if isinstance(file, (str, bytes, os.PathLike)) and Path(os.fsdecode(file)) == locked:
                raise PermissionError(13, "Permission denied", os.fsdecode(file))
            return f(file, *a, **k)
        return opener
    monkeypatch.setattr(builtins, "open", refusing(real_open))                # shutil.copyfile reads through it
    monkeypatch.setattr(io, "open", refusing(real_io_open))                   # Path.read_bytes reads through it

    def plan_then_delete(exports, role):
        pl = real_plan(exports, role)
        if gone.exists():
            gone.unlink()                                                     # gone after the plan, before the copy
        return pl
    monkeypatch.setattr(em, "bulletin_plan", plan_then_delete)
    remote = _remote(tmp_path)
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["pushed"] and r["copied"] == 2 + 4, r                                  # 2 top-level + 4 bulletins
    assert r["skipped"] == [(f"{B_CLOSE}.md", "unreadable: PermissionError"),
                            (f"{B_SLATE}.png", "unreadable: FileNotFoundError")], r
    assert em.skipped_line(r["skipped"]) == (                                       # main's console line ends so
        "bulletins: 2 skipped (unreadable: PermissionError 1 · unreadable: FileNotFoundError 1)")
    co, tree = _tree(remote, tmp_path)
    assert {"host/2026-10-03/fixtures_NHL_2026-10-03.json", "host/latest/fixtures_NHL.json"} <= set(tree)
    assert sorted(f for f in tree if f.startswith("host/bulletins/")) == sorted(
        f"host/{rel}" for rel in files if rel not in (f"{B_CLOSE}.md", f"{B_SLATE}.png"))
    r = em.push("host", ex, "t", remote, tmp_path / "clone", today=TODAY)
    assert r["why"] == "nothing changed" and r["skipped"] == [(f"{B_CLOSE}.md", "unreadable: PermissionError")], r


def test_a_path_git_refuses_is_skipped_and_never_jams_the_mirror(tmp_path):
    """Git decides which paths it carries (review of this PR): with core.protectNTFS (git's default) it refuses
    `.git`'s NTFS spellings, GIT~1, `.git.` and `.git ` (trailing space), which a `.git` test alone does not catch.
    Each is skipped with the reason "git refused the path" and removed from the working clone; the top-level files and
    the other bulletins still push. A refused file already sitting in the clone (a push killed before its add) is
    removed and receipted the same way, so it never jams a later push after its source is gone."""
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    files = _three(ex)
    odd = ["bulletins/GIT~1/x.md", "bulletins/.git./x.md", "bulletins/.git /x.md", "bulletins/SOCCER/git~1/y.png"]
    _bulletins(ex, {rel: b"never" for rel in odd})
    assert set(em.bulletin_plan(ex, "host")["kept"]) == {f"host/{rel}" for rel in [*files, *odd]}   # the plan takes them
    remote, clone = _remote(tmp_path), tmp_path / "clone"
    r = em.push("host", ex, "t", remote, clone, today=TODAY)
    assert r["pushed"] and r["copied"] == 2 + 6, r
    assert sorted(r["skipped"]) == sorted((rel, "git refused the path") for rel in odd)
    _, tree = _tree(remote, tmp_path)
    assert {"host/2026-10-03/fixtures_NHL_2026-10-03.json", "host/latest/fixtures_NHL.json"} <= set(tree)
    assert sorted(f for f in tree if f.startswith("host/bulletins/")) == sorted(f"host/{rel}" for rel in files)
    assert not any((clone / "host" / rel).exists() for rel in odd)          # removed from the clone
    again = em.push("host", ex, "t", remote, clone, today=TODAY)
    assert again["why"] == "nothing changed" and len(again["skipped"]) == 4, again
    for rel in odd:                                                         # the sources go; a stray copy stays behind
        shutil.rmtree(ex / Path(rel).parent)
    stray = clone / "host" / "bulletins" / "GIT~1" / "z.md"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"left by a killed push")
    later = TODAY + timedelta(days=1)
    (ex / "fixtures_NHL_2026-10-04.json").write_text('{"a":2}')
    os.utime(ex / "fixtures_NHL_2026-10-04.json", (_mt(later), _mt(later)))
    r = em.push("host", ex, "t2", remote, clone, today=later)
    assert r["pushed"] and r["skipped"] == [("bulletins/GIT~1/z.md", "git refused the path")], r
    assert not stray.exists()
    _, tree = _tree(remote, tmp_path)
    assert "host/2026-10-04/fixtures_NHL_2026-10-04.json" in tree


def _seeded_remote(tmp: Path, tracked: dict) -> str:
    """A bare remote whose main already TRACKS the given entries: rel -> ("link", target), ("file", bytes) or
    ("gitlink", commit sha)."""
    remote = _remote(tmp)
    seed = tmp / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    for rel, (what, val) in tracked.items():
        q = seed / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        if what == "gitlink":                          # a submodule entry (mode 160000): staged below, no folder
            continue
        q.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(val, q) if what == "link" else q.write_bytes(val)
    (seed / "README").write_text("seed\n")
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True, capture_output=True)
    for rel, (what, val) in tracked.items():
        if what == "gitlink":
            subprocess.run(["git", "-C", str(seed), "update-index", "--add", "--cacheinfo", f"160000,{val},{rel}"],
                           check=True, capture_output=True)
    for args in (["-c", "user.name=s", "-c", "user.email=s@x", "commit", "-q", "-m", "seed"],
                 ["push", "-q", remote, "HEAD:main"]):
        subprocess.run(["git", "-C", str(seed), *args], check=True, capture_output=True)
    return remote


def _gitlinks(remote: str) -> list[str]:
    """The remote main's submodule entries (mode 160000), read from the bare repo itself."""
    out = subprocess.run(["git", "-C", remote, "ls-tree", "-r", "main"], check=True, capture_output=True, text=True)
    return sorted(line.split("\t", 1)[1] for line in out.stdout.splitlines() if line.startswith("160000 "))


def _outside(tmp: Path) -> tuple[Path, dict]:
    """A folder beside the clone, never the mirror's: what a tracked link would carry a write (or a walk's unlink) to."""
    out = tmp / "outside"
    files = {"target.md": b"outside, never the mirror's\n", "2026-10-03/900001_x.md": b"outside, a dated name\n",
             "keep.txt": b"outside, kept\n"}
    for rel, body in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(body)
    return out, files


@pytest.mark.parametrize("where, target", [
    ("bulletins/NFL/2026-10-03/900001_x.md", "../../../../../outside/target.md"),   # the file itself, relative escape
    ("bulletins/NFL/2026-10-03/900001_x.md", "ABS/target.md"),                      # the file itself, absolute
    ("bulletins/NFL", "../../../outside"),                                          # a parent folder, relative escape
    ("bulletins/NFL", "ABS"),                                                       # a parent folder, absolute
    ("bulletins", "../../outside"),                                                 # bulletins/ itself
])
def test_a_tracked_symlink_on_a_bulletin_destination_is_never_followed(tmp_path, where, target):
    """Codex on #847: the mirror's own tree may already TRACK a symlink where a bulletin goes, the file itself or a
    folder above it (relative escape or absolute). The push never reads or writes through it: that bulletin is skipped
    with "destination path has a symlink", receipted on the result and the console line; the outside target is byte
    for byte as it was (no write through the link, and git's own check never walks it, so nothing outside is unlinked);
    the tracked link stays as the mirror holds it; the top-level files and the other bulletins still push."""
    out, before = _outside(tmp_path)
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    mine, other = "bulletins/NFL/2026-10-03/900001_x.md", "bulletins/SOCCER/2026-10-03/900002_y.md"
    _bulletins(ex, {mine: b"# new bulletin bytes\n", other: b"# another bulletin\n"})
    link = target.replace("ABS", str(out))
    remote, clone = _seeded_remote(tmp_path, {f"host/{where}": ("link", link)}), tmp_path / "clone"
    r = em.push("host", ex, "t", remote, clone, today=TODAY)
    linked = [mine, other] if where == "bulletins" else [mine]
    assert r["pushed"] and r["copied"] == 2 + 2 - len(linked), r
    assert r["skipped"] == [(rel, "destination path has a symlink") for rel in linked], r
    assert em.skipped_line(r["skipped"]) == f"bulletins: {len(linked)} skipped (destination path has a symlink {len(linked)})"
    assert {str(q.relative_to(out)): q.read_bytes() for q in out.rglob("*") if q.is_file()} == before   # untouched
    assert os.readlink(clone / "host" / where) == link                       # the tracked link stays as it was
    co, tree = _tree(remote, tmp_path)
    assert {"host/2026-10-03/fixtures_NHL_2026-10-03.json", "host/latest/fixtures_NHL.json"} <= set(tree)
    assert os.readlink(co / "host" / where) == link                          # the remote's link unchanged
    if where != "bulletins":
        assert (co / "host" / other).read_bytes() == b"# another bulletin\n"    # the other bulletin still goes
    again = em.push("host", ex, "t", remote, clone, today=TODAY)
    assert again["why"] == "nothing changed" and again["skipped"] == r["skipped"], again


def test_a_tracked_symlink_role_folder_never_carries_a_bulletin_or_the_walk_out(tmp_path):
    """The walk starts at <role>/ (Codex on #847): a tracked `host -> ../outside` skips every bulletin with "destination
    path has a symlink" and git's own check never walks or unlinks through it (on 3441675a its `add -- host/bulletins`
    beyond the link aborted the whole push). No bulletin bytes land outside and the outside's own files stay; the
    top-level rule's writes under a linked role folder are the top-level rule's, unchanged by this PR (a follow-up)."""
    out, before = _outside(tmp_path)
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    mine = "bulletins/NFL/2026-10-03/900001_x.md"
    _bulletins(ex, {mine: b"# new bulletin bytes\n"})
    remote, clone = _seeded_remote(tmp_path, {"host": ("link", "../outside")}), tmp_path / "clone"
    r = em.push("host", ex, "t", remote, clone, today=TODAY)
    assert r["skipped"] == [(mine, "destination path has a symlink")], r
    assert not (out / "bulletins").exists()                                  # no bulletin written through the link
    assert all((out / rel).read_bytes() == body for rel, body in before.items())
    assert os.readlink(clone / "host") == "../outside"


def test_a_bulletin_destination_that_is_a_folder_or_under_a_file_is_skipped_never_overwritten(tmp_path):
    """The destination is lstat'ed, not trusted (Codex on #847): a FOLDER sitting where a bulletin goes (left in the
    working clone) is "destination not a regular file", and a tracked FILE where a bulletin's folder goes is
    "destination path has a non-folder". Each is skipped and receipted, never removed or overwritten (on 3441675a the
    write raised and the whole push aborted); the top-level files and the other bulletins still push."""
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    as_dir, under_file, ok = ("bulletins/NFL/2026-10-03/900001_x.md", "bulletins/MLB/2026-10-03/900003_z.md",
                              "bulletins/SOCCER/2026-10-03/900002_y.md")
    _bulletins(ex, {as_dir: b"# a\n", under_file: b"# z\n", ok: b"# y\n"})
    remote = _seeded_remote(tmp_path, {"host/bulletins/MLB": ("file", b"a tracked file where a folder goes\n")})
    clone = tmp_path / "clone"
    em._ensure_clone(clone, remote)
    em._sync_to_remote(clone)
    (clone / "host" / as_dir / "inner").mkdir(parents=True)
    (clone / "host" / as_dir / "inner" / "keep.md").write_bytes(b"left in the clone\n")
    r = em.push("host", ex, "t", remote, clone, today=TODAY)
    assert r["pushed"] and sorted(r["skipped"]) == sorted([(as_dir, "destination not a regular file"),
                                                           (under_file, "destination path has a non-folder")]), r
    assert (clone / "host" / as_dir / "inner" / "keep.md").read_bytes() == b"left in the clone\n"
    co, tree = _tree(remote, tmp_path)
    assert {"host/2026-10-03/fixtures_NHL_2026-10-03.json", "host/latest/fixtures_NHL.json"} <= set(tree)
    assert (co / "host" / ok).read_bytes() == b"# y\n"
    assert (co / "host/bulletins/MLB").read_bytes() == b"a tracked file where a folder goes\n"


GITLINK_SHA = "1234567890123456789012345678901234567890"


@pytest.mark.parametrize("where", ["", "bulletins", "bulletins/NFL", "bulletins/NFL/2026-10-03/900001_x.md"])
def test_a_tracked_submodule_on_a_bulletin_destination_is_skipped_kept_and_never_aborts_the_push(tmp_path, where):
    """Codex round 1's fix, reviewed: the mirror's own tree may track a SUBMODULE entry (a gitlink, mode 160000) at the
    role folder, at bulletins/, at a folder above a bulletin or at the bulletin's own place. Git checks one out as an
    empty real folder, so an lstat alone lets it through. Each bulletin under it is skipped and receipted
    ("destination path has a submodule"), never written into it; git's own check never runs a pathspec inside it (a
    gitlink at `host` made `add -- host/bulletins` exit 128, "is in submodule", and every push raised); its empty
    checkout folder is never removed, so the push never stages the gitlink's deletion; the remote still tracks it, the
    skip holds on the next push (a stray an earlier push left inside it neither aborts that push nor is touched), and
    the tools and the other bulletins still go."""
    ex = _exports(tmp_path, [("fixtures_NHL_2026-10-03.json", TODAY, '{"a":1}')])
    mine, other = "bulletins/NFL/2026-10-03/900001_x.md", "bulletins/SOCCER/2026-10-03/900002_y.md"
    _bulletins(ex, {mine: b"# new bulletin bytes\n", other: b"# another bulletin\n"})
    gl = "/".join(x for x in ("host", where) if x)
    remote, clone = _seeded_remote(tmp_path, {gl: ("gitlink", GITLINK_SHA)}), tmp_path / "clone"
    r = em.push("host", ex, "t", remote, clone, today=TODAY)
    under = [mine, other] if where in ("", "bulletins") else [mine]
    assert r["pushed"] and r["skipped"] == [(rel, "destination path has a submodule") for rel in under], r
    assert em.skipped_line(r["skipped"]) == f"bulletins: {len(under)} skipped (destination path has a submodule {len(under)})"
    assert _gitlinks(remote) == [gl]                                         # still tracked, never deleted
    if where:                                                                # no bulletin written into it
        assert (clone / gl).is_dir() and not any((clone / gl).iterdir())
    else:          # the top-level rule still writes host/<date>/ and host/latest/ there, which git never carries: main's
        assert not (clone / gl / "bulletins").exists()                      # behaviour, outside this diff (architect)
    co, tree = _tree(remote, tmp_path)
    assert {"tools/compare_exports.py", ".github/workflows/compare.yml"} <= set(tree)
    if where:                                                                # the role folder is real: the top level goes
        assert {"host/2026-10-03/fixtures_NHL_2026-10-03.json", "host/latest/fixtures_NHL.json"} <= set(tree)
    if other not in under:
        assert (co / "host" / other).read_bytes() == b"# another bulletin\n"
    stray = clone / gl / (mine if not where else "stray.md")                # left in it by a 3441675a push
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"left by an earlier push\n")
    again = em.push("host", ex, "t", remote, clone, today=TODAY)
    assert again["why"] == "nothing changed" and again["skipped"] == r["skipped"], again
    assert _gitlinks(remote) == [gl] and stray.read_bytes() == b"left by an earlier push\n"


def test_the_compare_never_sees_the_subtree(tmp_path):
    """The compare is untouched and never sees a bulletin: in a mirror both writers pushed, with bulletins and a .json
    planted under exports/bulletins/, the compare's own `*.json` glob (its --glob default, read from its source) over
    every folder of the tree yields no path under bulletins/; the shipped Action's date pick never takes bulletins/ for
    a date (a tree holding only bulletins is pending, never a verdict) and posts CLEAN on the common dated folder; the
    shipped tool run on the two bulletins/ folders compares 0 JSON (NO-COVERAGE, never CLEAN). kind_of is the mirror's
    own, unchanged (compare_exports.py is not in this diff)."""
    import compare_exports as ce
    src = (ROOT / "deploy" / "hosting" / "compare_exports.py").read_text()
    assert 'ap.add_argument("--glob", default="*.json")' in src
    glob = "*.json"
    remote = _remote(tmp_path)
    for role in ("host", "laptop"):                                         # bulletins only: no dated folder yet
        ex = _exports(tmp_path / f"b_{role}", [])
        _three(ex)
        _bulletins(ex, {"bulletins/NFL/2026-10-03/planted.json": b'{"rows": []}'})
        assert em.push(role, ex, "b", remote, tmp_path / f"{role}_clone", today=TODAY)["pushed"]
    co, tree = _tree(remote, tmp_path)
    assert sorted(os.listdir(co / "host")) == ["bulletins"] and sorted(os.listdir(co / "laptop")) == ["bulletins"]
    got = _run_action(co, tmp_path)
    assert got["state"] == "pending" and "date" not in got, got            # bulletins/ is never a date
    body = '[{"utc_date":"2026-10-03T23:00Z","home_team":"A","away_team":"B","p":0.5}]'
    for role in ("host", "laptop"):
        ex = _exports(tmp_path / f"d_{role}", [("fixtures_NHL_2026-10-03.json", TODAY, body)])
        _three(ex)
        _bulletins(ex, {"bulletins/NFL/2026-10-03/planted.json": b'{"rows": []}'})
        assert em.push(role, ex, "d", remote, tmp_path / f"{role}_clone", today=TODAY)["pushed"]
    co, tree = _tree(remote, tmp_path)
    assert any(f.startswith("host/bulletins/") for f in tree) and any(f.startswith("laptop/bulletins/") for f in tree)
    seen = [p for d in [co, *(p for p in co.rglob("*") if p.is_dir() and ".git" not in p.parts)] for p in d.glob(glob)]
    assert seen and not any("bulletins" in p.relative_to(co).parts for p in seen), seen
    assert not any(f.endswith(".json") and "/bulletins/" in f for f in tree)
    assert _run_action(co, tmp_path) == {"date": "2026-10-03", "state": "success", "desc": "CLEAN · 2026-10-03"}
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SP_WRITER_OF_RECORD")}
    r = subprocess.run([sys.executable, "tools/compare_exports.py", "laptop/bulletins", "host/bulletins", "--since", "0"],
                       cwd=co, env=env, capture_output=True, text=True)
    assert r.returncode == 3 and "coverage: 0 JSON file(s) compared" in r.stdout, r.stdout + r.stderr
    for rel in (f"{B_CLOSE}.md", f"{B_CLOSE}.png", f"{B_WEEK}.md"):
        name = Path(rel).name
        assert ce.kind_of(name) == em.kind_of(name) and ce.machine_state_kind(name) is None
