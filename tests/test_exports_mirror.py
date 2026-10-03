"""F2.5 EXPORTS MIRROR (ARCHITECT 2026-10-03): host/<date>/<file> + host/latest/<kind>.json, 14-day
retention, both writers on one branch, the compare tool + Action shipped, weekly squash; the sp_run
hook is non-fatal and off until configured. Uses a LOCAL bare repo as the remote (no network)."""
import os
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
