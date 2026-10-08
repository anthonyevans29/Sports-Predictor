"""sp_receipts.py reads every writer's `backup` shape (2026-10-08 host crash:
`AttributeError: 'str' object has no attribute 'get'` at table()).

Writers, read 2026-10-08: sp_run.py chain -> dict {file, sha256, integrity};
sp_deploy.py migrations -> file name string; remove_allstar_rows.py cleanup ->
file name string + backup_sha256. The receipts file is a tmp_path copy.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOSTING = Path(__file__).resolve().parent.parent / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))
import sp_common as c  # noqa: E402
import sp_receipts  # noqa: E402

CHAIN_SHA = "a" * 64
CLEANUP_SHA = "c" * 64


def _ts(minutes_ago: int) -> str:
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(tmp_path, monkeypatch, recs):
    p = tmp_path / "receipts.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "absent.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("SP_RECEIPTS", str(p))
    monkeypatch.setenv("SP_HOST_NAME", "testhost")
    return p


MIXED = [
    {"ts": _ts(30), "host": "h", "release": "v1.3.0", "kind": "chain", "unit": "sp-morning", "exit": 0,
     "steps_ok": 3, "steps_total": 3, "exports": [],
     "backup": {"file": "daily-2026-10-08.db", "sha256": CHAIN_SHA, "integrity": "ok"}},
    {"ts": _ts(20), "host": "h", "release": "v1.3.0", "kind": "migrations", "exit": 0,
     "step": "migrate_x.py", "index": 0, "backup": "daily-2026-10-08.db"},
    {"ts": _ts(10), "host": "h", "release": "v1.3.0", "kind": "cleanup", "exit": 0, "applied": True,
     "backup": "precleanup-2026-10-08.db", "backup_sha256": CLEANUP_SHA},
    {"ts": _ts(5), "host": "h", "release": "v1.3.0", "kind": "odd", "exit": 0, "backup": ["x", 1]},
]


def test_mixed_backup_shapes_render(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch, MIXED)
    assert sp_receipts.main(["--since", "24h"]) == 0
    out = capsys.readouterr().out
    assert "4 lines, 0 failing" in out
    rows = {ln.split("|")[3].strip(): ln for ln in out.splitlines() if ln.startswith("| ") and "time (UTC)" not in ln}
    assert set(rows) == {"sp-morning", "migrations", "cleanup", "odd"}
    shas = {k: v.split("|")[-2].strip() for k, v in rows.items()}
    assert shas == {"sp-morning": CHAIN_SHA[:12], "migrations": "", "cleanup": CLEANUP_SHA[:12], "odd": ""}


def test_backup_sha_shapes():
    assert sp_receipts.backup_sha({"backup": {"sha256": CHAIN_SHA}}) == CHAIN_SHA
    assert sp_receipts.backup_sha({"backup": {"file": "f.db", "sha256": None}}) == ""
    assert sp_receipts.backup_sha({"backup": "f.db"}) == ""
    assert sp_receipts.backup_sha({"backup": "f.db", "backup_sha256": CLEANUP_SHA}) == CLEANUP_SHA
    assert sp_receipts.backup_sha({"kind": "backup", "sha256": CHAIN_SHA}) == CHAIN_SHA
    assert sp_receipts.backup_sha({"backup": 7}) == ""
    assert sp_receipts.backup_sha({"backup": None}) == ""
    assert sp_receipts.backup_sha({}) == ""
