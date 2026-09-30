"""RELEASE MODEL (architect 2026-09-30): main = BETA, production = tagged
releases only. The host deploy checks out the latest vX.Y.Z (never main),
every receipt names the running tag, release notes = the CHANGELOG slice
since the previous tag. Throwaway git repos in tmp only."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
sys.path.insert(0, str(ROOT / "scripts"))

import release_notes as rn  # noqa: E402
import sp_common as c  # noqa: E402
import sp_deploy  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def g(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=ENV).stdout.strip()


def commit(repo, name, text, msg):
    (repo / name).write_text(text)
    g(repo, "add", name)
    g(repo, "commit", "-qm", msg)


CL1 = "# Changelog\n\n## 2026-09-29 (a)\n- one\n"
CL2 = "# Changelog\n\n## 2026-09-30 (b)\n- two\n\n## 2026-09-29 (a)\n- one\n"


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """origin (bare) + a dev clone that pushes + a host clone that deploys."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    origin, dev, host = tmp_path / "origin.git", tmp_path / "dev", tmp_path / "host"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, env=ENV)
    subprocess.run(["git", "clone", "-q", str(origin), str(dev)], check=True, env=ENV)
    g(dev, "checkout", "-q", "-b", "main")
    commit(dev, "CHANGELOG.md", CL1, "c1")
    g(dev, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(host)], check=True, env=ENV)
    monkeypatch.setattr(c, "REPO", host)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    return {"origin": origin, "dev": dev, "host": host, "receipts": tmp_path / "receipts.jsonl"}


def receipts(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def test_release_tag_order_is_numeric_and_strict():
    assert c.latest_release(["v1.9.0", "v1.10.0", "v1.2.3"]) == "v1.10.0"
    assert c.latest_release(["v2.0.0-rc1", "vnext", "1.0.0", "v1.0"]) is None
    assert c.release_key("v1.0.1") == (1, 0, 1) and c.release_key("v1.0.1x") is None


def test_no_tag_refuses_and_never_pulls_main(repos):
    commit(repos["dev"], "x.py", "1\n", "beta work")
    g(repos["dev"], "push", "-q", "origin", "main")
    before = g(repos["host"], "rev-parse", "HEAD")
    assert c.running_release().startswith("BETA main@")
    with pytest.raises(SystemExit, match="no release tag"):
        sp_deploy.main([])
    assert g(repos["host"], "rev-parse", "HEAD") == before          # main NOT pulled


def test_deploys_latest_tag_detached_and_receipts_the_tag(repos):
    dev = repos["dev"]
    g(dev, "tag", "v1.0.0")
    commit(dev, "migrate_x.py", "pass\n", "c2")
    g(dev, "tag", "v1.0.1")
    commit(dev, "beta.py", "1\n", "beta, untagged")                # main moves past the tag
    g(dev, "push", "-q", "--tags", "origin", "main")
    assert sp_deploy.main([]) == 0
    host = repos["host"]
    assert g(host, "rev-parse", "HEAD") == g(dev, "rev-parse", "v1.0.1^{commit}")
    assert not (host / "beta.py").exists()                         # beta never reaches production
    assert c.running_release() == "v1.0.1"
    r = receipts(repos["receipts"])[-1]
    assert r["kind"] == "deploy" and r["release"] == "v1.0.1" and r["to_release"] == "v1.0.1"
    assert r["from_release"].startswith("BETA main@") and r["new_migrations"] == ["migrate_x.py"]
    # explicit rollback to a named tag; a bogus tag refuses
    assert sp_deploy.main(["--tag", "v1.0.0"]) == 0 and c.running_release() == "v1.0.0"
    with pytest.raises(SystemExit, match="not found"):
        sp_deploy.main(["--tag", "v9.9.9"])
    with pytest.raises(SystemExit, match="not a release tag"):
        sp_deploy.main(["--tag", "main"])


def test_dirty_and_other_branch_refuse_but_results_md_is_restored(repos):
    dev, host = repos["dev"], repos["host"]
    commit(dev, "RESULTS.md", "tally\n", "results")
    g(dev, "tag", "v1.0.0")
    g(dev, "push", "-q", "--tags", "origin", "main")
    g(host, "pull", "-q", "origin", "main")
    (host / "RESULTS.md").write_text("rewritten by the host\n")
    assert sp_deploy.main([]) == 0 and (host / "RESULTS.md").read_text() == "tally\n"
    (host / "CHANGELOG.md").write_text("edited\n")
    with pytest.raises(SystemExit, match="local modifications"):
        sp_deploy.main([])
    g(host, "checkout", "-q", "--", "CHANGELOG.md")
    g(host, "checkout", "-q", "-b", "feature")
    with pytest.raises(SystemExit, match="branch 'feature'"):
        sp_deploy.main([])


def test_every_receipt_carries_the_running_release(repos):
    g(repos["dev"], "tag", "v1.0.0")
    g(repos["dev"], "push", "-q", "--tags", "origin")
    sp_deploy.main([])
    line = c.append_receipt({"kind": "chain", "exit": 0})
    assert line["release"] == "v1.0.0"


def test_release_notes_slice_since_previous_tag(repos):
    dev = repos["dev"]
    g(dev, "tag", "v1.0.0")
    assert "FIRST RELEASE" in rn.notes("v1.0.0", repo=dev)
    commit(dev, "CHANGELOG.md", CL2.replace("- one", "- one (amended)"), "c2")
    g(dev, "tag", "v1.1.0")
    out = rn.notes("v1.1.0", repo=dev)
    assert "since v1.0.0" in out and "## 2026-09-30 (b)" in out and "- two" in out
    assert out.count("## 2026-09-29 (a)") == 1 and "AMENDED" in out   # listed as amended, not re-sliced
    added, amended = rn.slice_since(CL1, CL2)
    assert [h for h, _ in added] == ["## 2026-09-30 (b)"] and amended == []
