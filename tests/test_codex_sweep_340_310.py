"""Codex sweep (#310, ARCHITECT sweep rule 2026-10-05): two unanswered threads on the merged deploy PR.
Throwaway git repos in tmp only; nothing real is deployed."""
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import sp_common as c  # noqa: E402
import sp_deploy  # noqa: E402
from test_release_model import commit, g, receipts, repos  # noqa: E402,F401


def test_per_requirement_option_after_a_marker_is_refused():
    # pip splits a line's options off at its first "-"-prefixed word, past the `;` (break_args_options)
    for bad in ('pkg>=1; python_version >= "3.0" --config-settings=key=value',
                'pkg>=1; python_version >= "3.0" -C key=value'):
        assert sp_deploy._classify(bad)[0] == "refuse", bad
    assert sp_deploy._classify('pkg==1.0; python_version >= "3.0" --hash=sha256:' + "0" * 64)[0] == "spec"
    assert sp_deploy._classify('pkg>=1; python_version >= "3.0"')[0] == "spec"


def test_failing_post_checkout_hook_after_head_moved_is_receipted_at_the_target_and_fails(repos):  # noqa: F811
    dev, host = repos["dev"], repos["host"]
    g(dev, "tag", "v1.0.0")
    commit(dev, "migrate_y.py", "pass\n", "c2")
    g(dev, "tag", "v1.0.1")
    g(dev, "push", "-q", "--tags", "origin", "main")
    hook = host / ".git" / "hooks" / "post-checkout"
    hook.write_text("#!/bin/sh\necho hook-broke >&2\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    assert sp_deploy.main(["--tag", "v1.0.1"]) == 1        # the hook failed: never reported as success (Codex on #409)
    assert g(host, "rev-parse", "HEAD") == g(dev, "rev-parse", "v1.0.1^{commit}")
    assert c.running_release() == "v1.0.1"
    r = receipts(repos["receipts"])[-1]
    assert r["kind"] == "deploy" and r["exit"] == 1 and r["to_release"] == "v1.0.1"   # where the code IS
    assert r["new_migrations"] == ["migrate_y.py"] and "hook-broke" in r["checkout_warning"]
