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
