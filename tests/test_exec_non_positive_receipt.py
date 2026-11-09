"""Addendum 305 item 2(d) / 306 item 2: the exec <= 0 receipt, a read-only script with --dir (default exports/)."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exec_non_positive_receipt", ROOT / "scripts" / "exec_non_positive_receipt.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def row(mid, call="PLAY", edge=1.5, cost=0.50, p=0.52, pass_kind=None, would=None, pick="HOME"):
    d = {"call": call, "pick": pick, "model_p": p, "exec": {"edge_pp": edge, "basis": "taker", "cost": cost}}
    if pass_kind:
        d["pass_kind"] = pass_kind
    if would:
        d["market_only_hold"] = {"would_call": would}
    return {"match_id": mid, "utc_date": "2026-10-12T17:00:00", "home_team": f"Home {mid}", "away_team": f"Away {mid}",
            "desk": d}


def write(path: Path, fam: str, rows, ids=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"predictions": rows, "closing": {"family": fam, "match_ids": ids or
                                                                 [r["match_id"] for r in rows]}}))


def test_flat_exports_layout_counts_exec_non_positive_plays_by_family(tmp_path, capsys):
    write(tmp_path / "closing_NFL_2026-10-12T1700Z.json", "NFL",
          [row(1, edge=-0.2, cost=0.734, p=0.732), row(2, edge=0.0), row(3, edge=0.1), row(4, edge=4.0)])
    write(tmp_path / "closing_MLB_2026-10-13T2300Z.json", "MLB", [row(5, edge=-1.0), row(6, call="PASS", edge=-3.0)])
    write(tmp_path / "closing_NFL_2026-10-12T1700Z_copy.json", "NFL", [row(9, edge=-5.0)])    # not a closing name
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "exports: 2 closing file(s), dates 2026-10-12 .. 2026-10-13, by family {'MLB': 1, 'NFL': 1}" in out
    assert "exec edge <= 0: 3 row(s) · by family {'MLB': 1, 'NFL': 2} · distinct games 3" in out
    assert ("NFL · match 1 · 2026-10-12 · kickoff 2026-10-12T17:00:00 · pick Home 1 · exec -0.20pp · all-in cost "
            "0.734 · model 0.732 · on page · closing_NFL_2026-10-12T1700Z.json") in out
    assert "match 2 " in out and "match 9 " not in out and "match 6 " not in out           # exactly 0 is the gap
    assert "SUMMARY: emitted PLAYs with exec <= 0: 3 row(s), 3 distinct game(s)" in out


def test_mirror_layout_skips_latest_and_links_and_dedupes_a_start(tmp_path, capsys):
    f = tmp_path / "host" / "2026-10-20" / "closing_SOCCER_2026-10-20T1400Z.json"
    write(f, "SOCCER", [row(11, edge=-0.5), row(11, edge=-0.5)])
    write(tmp_path / "host" / "latest" / "closing_SOCCER_2026-10-20T1400Z.json", "SOCCER", [row(12, edge=-9.0)])
    (tmp_path / "laptop").mkdir()
    (tmp_path / "laptop" / "2026-10-20").symlink_to(f.parent, target_is_directory=True)
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "host: 1 closing file(s)" in out and "laptop" not in out.split("files read")[0]
    assert "exec edge <= 0: 1 row(s) · by family {'SOCCER': 1} · distinct games 1" in out
    assert "match 12" not in out


def test_would_be_plays_are_their_own_block_and_never_emitted(tmp_path, capsys):
    write(tmp_path / "closing_NFL_2026-11-09T0120Z.json", "NFL",
          [row(15175, call="PASS", pass_kind="market_only", would="PLAY", edge=-0.21, cost=0.734, p=0.732)])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "SUMMARY: emitted PLAYs with exec <= 0: 0 row(s), 0 distinct game(s); would-be PLAYs with exec <= 0: " \
           "1 row(s), 1 distinct game(s)" in out


def test_the_date_bounds_and_an_unstored_edge_is_never_zero(tmp_path, capsys):
    write(tmp_path / "closing_MLB_2026-10-05T2300Z.json", "MLB", [row(1, edge=-1.0)])
    write(tmp_path / "closing_MLB_2026-10-06T2300Z.json", "MLB", [row(2, edge=None)])
    write(tmp_path / "closing_MLB_2026-10-27T2300Z.json", "MLB", [row(3, edge=-1.0)])
    assert rc.main(["--dir", str(tmp_path), "--from", "2026-10-06", "--through", "2026-10-26"]) == 0
    out = capsys.readouterr().out
    assert "start dates 2026-10-06 .. 2026-10-26" in out and "exports: 1 closing file(s)" in out
    assert "no exec edge stored: 1" in out and "exec edge <= 0: 0 row(s)" in out.split("WOULD-BE")[0]


def test_it_writes_nothing_and_prints_no_order_or_count(tmp_path, capsys):
    r = row(1, edge=-0.2)
    r["desk"]["order"] = {"text": "BUY YES KXTEST @ 73 × 4", "contracts": 4}
    r["desk"]["exec"]["contracts"] = 4
    write(tmp_path / "closing_NFL_2026-10-12T1700Z.json", "NFL", [r])
    before = sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*")) == before
    assert "BUY" not in out and "×" not in out and "contracts" not in out and "$" not in out


@pytest.mark.parametrize("argv", [["--dir", "/nonexistent/exports"], ["--from", "2026-13-01"]])
def test_refusals_exit_2(tmp_path, argv, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "exports").mkdir()
    assert rc.main(argv) == 2
