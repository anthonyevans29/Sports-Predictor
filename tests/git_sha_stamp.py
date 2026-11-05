"""The git_sha header stamp, checked on one export (a helper for the tests of the four exports addendum 249 item 2
stamps; not a test module).

ARCHITECT 2026-11-04 11:05 ET (addendum 249 item 2): "the git_sha stamp goes on ALL FIVE exports (the NHL shadow, the
UNL shadow, the NCAA shadow, the intl predictions, the intl results) in the one held PR — the same one-line header
stamp, null when git has no SHA, nothing else in any file; the compare masks git_sha so no field difference appears
across the deploy." tests/test_nhl_shadow.py pins the NHL shadow's own stamp the same way.

`export(out_dir, call)` runs the export into `out_dir` (`call` is 0 for the stamped run, 1 for the run where git
cannot say, so a caller can give each its own clock) and returns its (path, doc)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_stamp(export, tmp_path, monkeypatch, sha="abc1234"):
    from src.walters import provenance
    sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
    import compare_exports as ce
    provenance.git_sha.cache_clear()
    try:
        # the producing checkout's SHA (SP_GIT_SHA overrides), in the doc and in the file, directly after exported_at
        monkeypatch.setenv("SP_GIT_SHA", sha)
        path, doc = export(str(tmp_path / "laptop"), 0)
        assert doc["git_sha"] == provenance.git_sha() == sha
        on_disk = json.loads(Path(path).read_text())
        assert on_disk["git_sha"] == sha
        keys = list(on_disk)
        assert keys.index("git_sha") == keys.index("exported_at") + 1
        # the compare: code is named on its own line and is never a field diff (MASKED), across the deploy too
        other = {**on_disk, "git_sha": "def5678"}
        assert ce.sha_line(on_disk, other) == f"code-version skew: laptop {sha} ≠ host def5678"
        assert ce.sha_line(on_disk, dict(on_disk)) == f"same code {sha}"
        assert ce.diff(on_disk, other) == []
        before = {k: v for k, v in on_disk.items() if k != "git_sha"}   # a file written before the stamp
        assert ce.diff(before, on_disk) == []
        # git cannot say: no override, a directory that is no checkout -> None, written as null, never guessed (law 4)
        provenance.git_sha.cache_clear()
        monkeypatch.delenv("SP_GIT_SHA", raising=False)
        for k in ("GIT_DIR", "GIT_WORK_TREE"):
            monkeypatch.delenv(k, raising=False)
        (tmp_path / "nogit").mkdir()
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        monkeypatch.setattr(provenance, "_REPO", tmp_path / "nogit")
        path, doc = export(str(tmp_path / "host"), 1)
        assert provenance.git_sha() is None and "git_sha" in doc and doc["git_sha"] is None
        written = json.loads(Path(path).read_text())
        assert "git_sha" in written and written["git_sha"] is None
        keys = list(written)
        assert keys.index("git_sha") == keys.index("exported_at") + 1
        assert ce.sha_line(on_disk, written) == "git_sha missing on host — code-version skew NOT claimable"
    finally:
        provenance.git_sha.cache_clear()
