"""scripts/nhl_leaders_order_receipt.py (ARCHITECT 2026-11-01, addendum 200 item 1; #105): read-only, on synthetic
payload files in tmp_path in the probe's --save form (<game id>_<endpoint>_<label>.json). A flip, a miss, two in net,
an unread eventual, AGREES / DIFFERS at T-35 and T-120, several directories summed, the refusals, the run from /tmp
with PYTHONPATH."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nhl_leaders_order_receipt.py"
_spec = importlib.util.spec_from_file_location("nhl_leaders_order_receipt", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

PRE = rc.PREGAME


def landing(away_ids, home_ids, *, gc=True):
    def team(ids):
        return {"leaders": [{"playerId": i, "name": {"default": f"G{i}"}} for i in ids]}
    p = {"awayTeam": {"abbrev": "BOS"}, "homeTeam": {"abbrev": "TOR"}, "gameState": "FUT"}
    if gc:
        p["matchup"] = {"goalieComparison": {"awayTeam": team(away_ids), "homeTeam": team(home_ids)}}
    else:
        p["matchup"] = {"skaterComparison": {}}
    return p


def goalie(i, toi, first="F", last=None):
    return {"playerId": i, "firstName": {"default": first}, "lastName": {"default": last or f"L{i}"}, "toi": toi}


def boxscore(away, home):
    return {"awayTeam": {"abbrev": "BOS"}, "homeTeam": {"abbrev": "TOR"},
            "playerByGameStats": {"awayTeam": {"goalies": away, "forwards": []},
                                  "homeTeam": {"goalies": home, "forwards": []}}}


def put(d: Path, gid: int, endpoint: str, label: str, payload) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{gid}_{endpoint}_{label}.json").write_text(payload if isinstance(payload, str) else json.dumps(payload))


def game(d: Path, gid: int, away_by_label=None, home_by_label=None, box=None, skip=()):
    """Landing at every pregame label (away/home leaders by label, default [10, 11] / [20, 21]); box at T+20."""
    for p in PRE:
        if p in skip:
            continue
        a = (away_by_label or {}).get(p, [10, 11])
        h = (home_by_label or {}).get(p, [20, 21])
        put(d, gid, "landing", p, landing(a, h))
    if box is not None:
        put(d, gid, "boxscore", "T+20", box)


def run(*dirs):
    lines = []
    code = rc.main([str(d) for d in dirs], out=lines.append)
    return code, lines


def last_json(lines):
    assert lines[-1].startswith(rc.TAG + " ")
    return json.loads(lines[-1][len(rc.TAG) + 1:])


def side(lines, gid, s):
    i = next(n for n, ln in enumerate(lines) if ln.startswith(f"  GAME {gid}"))
    return next(ln for ln in lines[i + 1:i + 3] if ln.startswith(f"    {s}:"))


def test_flip_agrees_at_t35_differs_at_t120(tmp_path):
    d = tmp_path / "p"
    flip = {p: ([12, 10] if p in ("T-35", "T-30", "T-15", "T-0") else [10, 12]) for p in PRE}
    game(d, 2025020001, away_by_label=flip, box=boxscore([goalie(10, "00:00"), goalie(12, "20:00")],
                                                         [goalie(20, "20:00"), goalie(21, "00:00")]))
    code, lines = run(d)
    assert code == 0
    a = side(lines, 2025020001, "away")
    assert "T-120 10 (G10)" in a and "T-35 12 (G12)" in a
    assert a.index("T-45 10") < a.index("T-35 12")                     # poll order, so the flip shows
    assert "eventual 12 (F L12)" in a
    assert a.endswith("T-35 AGREES · T-120 DIFFERS · flips 1 (T-45->T-35 10 (G10)->12 (G12))")
    h = side(lines, 2025020001, "home")
    assert h.endswith("T-35 AGREES · T-120 AGREES · flips 0")
    j = last_json(lines)
    assert j["agrees_at_T-35"] == 2 and j["n_at_T-35"] == 2
    assert j["agrees_at_T-120"] == 1 and j["differs_at_T-120"] == 1 and j["n_at_T-120"] == 2
    assert j["sides_with_at_least_one_flip"] == 1 and j["games_read"] == 1
    assert "  GAME 2025020001 (BOS @ TOR)" in lines


def test_miss_missing_file_no_goaliecomparison_empty_leaders(tmp_path):
    d = tmp_path / "p"
    gid = 2025020002
    game(d, gid, home_by_label={"T-90": []}, skip=("T-35",),
         box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    put(d, gid, "landing", "T-60", landing([10], [20], gc=False))
    code, lines = run(d)
    assert code == 0
    a, h = side(lines, gid, "away"), side(lines, gid, "home")
    assert "missing at T-35 (no landing file)" in a
    assert "missing at T-60 (no matchup.goalieComparison)" in a
    assert "missing at T-90 (empty leaders list)" in h
    assert a.endswith("T-35 UNREAD · T-120 AGREES · flips 0")      # a miss is skipped, never a flip by itself
    j = last_json(lines)
    assert j["missing_at_T-35"] == 2 and j["missing_at_T-60"] == 2 and j["missing_at_T-90"] == 1
    assert j["n_at_T-35"] == 0 and j["n_at_T-120"] == 2 and j["agrees_at_T-120"] == 2


def test_late_flip_and_return_flip_counted_t0_read(tmp_path):
    """A flip at T-15 and a return at T-0 are two flips on one side; a side counts once however many it has; the T-0
    poll is read and printed; a second side with one flip moves the side count to 2, not 3."""
    d = tmp_path / "p"
    late = {p: [10, 12] for p in PRE} | {"T-15": [12, 10], "T-0": [10, 12]}
    one = {p: ([21, 20] if p == "T-0" else [20, 21]) for p in PRE}
    game(d, 2025020060, away_by_label=late, home_by_label=one,
         box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    put(d, 2025020061, "landing", "T-120", landing([10], [20]))      # T-0 (and the rest) missing on this game
    code, lines = run(d)
    assert code == 0
    a = side(lines, 2025020060, "away")
    assert "T-0 10 (G10)" in a
    assert a.endswith("flips 2 (T-30->T-15 10 (G10)->12 (G12); T-15->T-0 12 (G12)->10 (G10))")
    assert side(lines, 2025020060, "home").endswith("flips 1 (T-15->T-0 20 (G20)->21 (G21))")
    assert "missing at T-0 (no landing file)" in side(lines, 2025020061, "away")
    j = last_json(lines)
    assert j["sides_with_at_least_one_flip"] == 2
    assert j["missing_at_T-0"] == 2


def test_two_in_net_counted_never_chosen(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020003, box=boxscore([goalie(10, "12:10"), goalie(11, "07:50")], [goalie(20, "20:00")]))
    code, lines = run(d)
    assert code == 0
    a = side(lines, 2025020003, "away")
    assert "eventual: two in net (2 goalies with toi above zero: 10 (F L10) 730s, 11 (F L11) 470s)" in a
    assert a.endswith("T-35 UNREAD · T-120 UNREAD · flips 0")
    j = last_json(lines)
    assert j["two_in_net"] == 1 and j["eventual_unread"] == 0
    assert j["n_at_T-35"] == 1 and j["agrees_at_T-35"] == 1             # the home side only


def test_unread_eventual_no_file_none_on_and_toi_unread(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020004)                                                 # no T+20 file
    game(d, 2025020005, box=boxscore([goalie(10, "00:00"), goalie(11, "00:00")],
                                     [goalie(20, "20:00"), goalie(21, None)]))
    code, lines = run(d)
    assert code == 0
    assert "eventual starter unread (no T+20 boxscore file)" in side(lines, 2025020004, "away")
    assert "eventual starter unread (no goalie with toi above zero)" in side(lines, 2025020005, "away")
    h = side(lines, 2025020005, "home")
    assert "eventual starter unread (one goalie with toi above zero, 20 (F L20), beside toi unread on 21 (F L21))" in h
    assert h.endswith("T-35 UNREAD · T-120 UNREAD · flips 0")
    j = last_json(lines)
    assert j["eventual_unread"] == 4 and j["n_at_T-35"] == 0 and j["games_read"] == 2


def test_differs_and_the_ingest_refusal_of_an_unsided_box(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020006, box=boxscore([goalie(11, "20:00")], [goalie(21, "20:00")]))
    unsided = {"goalies": [goalie(1, "20:00")], "playerByGameStats": {}}
    game(d, 2025020007, box=unsided)
    code, lines = run(d)
    assert code == 0
    assert side(lines, 2025020006, "away").endswith("T-35 DIFFERS · T-120 DIFFERS · flips 0")
    assert "the ingest refused the boxscore: goalie lists not sided one home + one away (lists: goalies)" \
        in side(lines, 2025020007, "home")
    j = last_json(lines)
    assert j["differs_at_T-35"] == 2 and j["agrees_at_T-35"] == 0 and j["eventual_unread"] == 2


def test_the_ingest_reads_the_goalie_block(tmp_path, monkeypatch):
    """The eventual starter comes from src.ingestion.nhl_goalies.boxscore_goalies, called (never a copy)."""
    from src.ingestion import nhl_goalies
    seen = []
    real = nhl_goalies.boxscore_goalies
    monkeypatch.setattr(nhl_goalies, "boxscore_goalies", lambda p: seen.append(p) or real(p))
    d = tmp_path / "p"
    game(d, 2025020008, box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    assert run(d)[0] == 0 and len(seen) == 1


def test_several_directories_summed_and_unparseable_counted(tmp_path):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    game(d1, 2025020010, box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    game(d2, 2025020011, box=boxscore([goalie(11, "20:00")], [goalie(20, "20:00")]))
    put(d2, 2025020011, "landing", "T-35", "{not json")
    (d2 / "notes.txt").write_text("x")
    code, lines = run(d1, d2)
    assert code == 0
    sums = [ln for ln in lines if ln.startswith("  SUMMARY")]
    assert len(sums) == 3 and sums[-1].startswith("  SUMMARY ALL (2 directories)")
    assert "at T-35: agrees 2 of 2 (100%)" in sums[0]
    assert "at T-35: agrees 0 of 0" in sums[1] and "files that did not parse 1" in sums[1]
    assert "missing at T-35 (unreadable (JSONDecodeError))" in side(lines, 2025020011, "away")
    j = last_json(lines)
    assert j["directories"] == 2 and j["games_read"] == 2 and j["n_at_T-35"] == 2 and j["agrees_at_T-35"] == 2
    assert j["n_at_T-120"] == 4 and j["agrees_at_T-120"] == 3 and j["differs_at_T-120"] == 1
    assert j["files_that_did_not_parse"] == 1 and j["files_not_of_the_name_form"] == 1


def test_unparseable_t20_boxscore_named_as_such(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020099, box="{bad")
    code, lines = run(d)
    assert code == 0
    for s_ in ("away", "home"):
        assert "eventual starter unread (T+20 boxscore unreadable (JSONDecodeError))" in side(lines, 2025020099, s_)
    j = last_json(lines)
    assert j["eventual_unread"] == 2 and j["files_that_did_not_parse"] == 1


def test_a_directory_given_twice_is_read_once(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020070, box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    code, lines = run(d, d, tmp_path / "p" / ".." / "p")
    assert code == 0
    assert any("2 argument(s) naming a directory already given, read once" in ln for ln in lines)
    assert sum(ln.startswith("  GAME 2025020070") for ln in lines) == 1
    j = last_json(lines)
    assert j["directories"] == 1 and j["directories_given_twice"] == 2
    assert j["games_read"] == 1 and j["sides"] == 2 and j["n_at_T-35"] == 2


def test_refusals_exit_2(tmp_path):
    assert run()[0] == 2
    assert run(tmp_path / "nope")[0] == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    code, lines = run(empty)
    assert code == 2 and "no file of the probe's name form" in lines[0]
    under = tmp_path / "data" / "p"
    game(under, 2025020020)
    code, lines = run(under)
    assert code == 2 and "under data/" in lines[0]


def test_writes_nothing(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020030, box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    before = sorted((f.name, f.read_bytes()) for f in d.iterdir())
    assert run(d)[0] == 0
    assert sorted((f.name, f.read_bytes()) for f in d.iterdir()) == before


@pytest.mark.parametrize("where", ["tmp", "checkout"])
def test_runs_as_a_file(tmp_path, where):
    """As #757's: a copy in /tmp-like dir run with PYTHONPATH naming the checkout; and in place in the checkout."""
    d = tmp_path / "p"
    game(d, 2025020040, box=boxscore([goalie(10, "20:00")], [goalie(20, "20:00")]))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if where == "tmp":
        copy = tmp_path / "bin" / SCRIPT.name
        copy.parent.mkdir()
        shutil.copy(SCRIPT, copy)
        env["PYTHONPATH"] = str(ROOT)
        cmd, cwd = [sys.executable, str(copy), str(d)], str(tmp_path)
    else:
        cmd, cwd = [sys.executable, str(SCRIPT), str(d)], str(tmp_path)
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[-1].startswith(rc.TAG + " ")
    assert '"agrees_at_T-35": 2' in r.stdout


def test_not_importable_refused(tmp_path):
    d = tmp_path / "p"
    game(d, 2025020050)
    copy = tmp_path / "bin" / SCRIPT.name
    copy.parent.mkdir()
    shutil.copy(SCRIPT, copy)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, str(copy), str(d)], cwd=str(tmp_path), env=env, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 2 and "src.ingestion.nhl_goalies not importable" in r.stdout
