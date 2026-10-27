"""NFL QB COVERAGE RECEIPT (ARCHITECT 2026-10-23, addendum 162 item 3(a); #427): offline runs on a fake provider, the
payload cache in a throwaway directory, no network and no database."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qbc", ROOT / "scripts" / "nfl_qb_coverage.py")
qbc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbc)


def _row(gid, ts, status, home=(1, "Home"), away=(2, "Away"), stage="Regular Season"):
    return {"game": {"id": gid, "stage": stage, "week": "Week 1", "status": {"short": status},
                     "date": {"timestamp": ts, "date": "2025-09-07", "time": "17:00"}},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}}}


GAMES = [_row(10, 100, "FT"), _row(11, 200, "FT"), _row(12, 300, "FT", stage="Pre Season"), _row(13, 400, "NS")]


def _team(tid, players):
    return {"team": {"id": tid, "name": f"T{tid}"}, "groups": [{"name": "Passing", "players": players}]}


def _p(pid, ca, extra=()):
    return {"player": {"id": pid, "name": f"P{pid}"},
            "statistics": [{"name": "comp att", "value": ca}, {"name": "yards", "value": "200"}, *extra]}


STATS = {10: [_team(1, [_p(101, "20/30", [{"name": "sacks", "value": "2-14"}]), _p(102, "1/2")]),
              _team(2, [_p(201, "18/25", [{"name": "sacks", "value": None}])])],
         11: [_team(1, [_p(103, "22/33")])],                      # one team's passing only; 103 is on team 2's roster
         12: []}                                                   # the preseason game: no answer
ROSTERS = {1: [{"id": 101, "position": "QB"}, {"id": 102, "position": "QB"}],
           2: [{"id": 201, "position": "QB"}, {"id": 103, "position": "QB"}]}


def fake(calls):
    def get(path, **p):
        calls.append((path, p))
        if path == "games":
            return 200, {}, GAMES
        if path == "games/statistics/players":
            return 200, {}, STATS.get(p["id"], [])
        if path == "players":
            return 200, {}, ROSTERS.get(p["team"], [])
        return 200, {}, []
    return get


def run(tmp_path, *args, calls=None):
    out = []
    calls = [] if calls is None else calls
    assert qbc.main(["--seasons", "2025", "--save", str(tmp_path / "pay"), *args], echo=out.append,
                    get=fake(calls)) == 0
    return "\n".join(out), calls


def test_coverage_by_game_type_fields_and_the_roster_join(tmp_path):
    out, calls = run(tmp_path)
    assert "G /games: by status FINISHED 3 · SCHEDULED 1" in out
    assert "Regular Season: listed 3 · finished 2 · passing both teams 1 · one team 1 · neither 0" in out
    assert "Pre Season: listed 1 · finished 1 · passing both teams 0 · one team 0 · neither 1" in out
    # four lines; 'sacks' is on two lines (one null) and absent from two
    assert "F passing lines 4 (no attempts read 0)" in out
    assert "'sacks' on 1, missing/empty 3" in out and "'yards' on 4, missing/empty 0" in out
    assert "R roster join, every passing line: another team's roster 1 · same team 3" in out
    assert "the most-attempts quarterback per team-game (OUR READ): another team's roster 1 · same team 2" in out
    assert "SUMMARY 2025: listed 4 · finished 3 · passing stats for both teams 1/3" in out
    assert len(calls) == 1 + 3 + 2                                 # the list, three finished games, two rosters
    assert "failed or empty 1" in out                              # the preseason game's empty answer


def test_a_rerun_reads_the_kept_payloads_and_a_cap_stops_cleanly(tmp_path):
    run(tmp_path)
    out, calls = run(tmp_path)
    assert [c[0] for c in calls] == ["games/statistics/players"]     # only the unkept empty answer is asked again
    assert "answers read from the kept payloads 5" in out
    out, calls = run(tmp_path / "fresh", "--max-calls", "2")
    assert "LEFT at the call cap (2)" in out and len(calls) == 2


def test_the_cache_is_refused_under_data(tmp_path):
    with pytest.raises(SystemExit, match="under data/"):
        qbc.main(["--save", str(ROOT / "data" / "x")], echo=lambda *_: None, get=fake([]))


def test_a_cap_at_a_season_boundary_stops_cleanly_and_unreadable_attempts_make_no_pick(tmp_path, monkeypatch):
    """Codex on #710: the cap reached at the next season's list ends cleanly (no traceback); a team-game whose lines
    read no attempts has no most-attempts quarterback (counted, never the first line), and 0 attempts is a read."""
    out, calls = run(tmp_path, "--max-calls", "6")                 # season 2025 uses all six calls
    out2 = []
    assert qbc.main(["--seasons", "2025,2026", "--save", str(tmp_path / "pay"), "--max-calls", "0"],
                    echo=out2.append, get=fake([])) == 0
    assert "LEFT at the call cap (0)" in "\n".join(out2) and "SUMMARY 2026" in "\n".join(out2)
    monkeypatch.setitem(STATS, 11, [_team(1, [{"player": {"id": 104}, "statistics": [{"name": "yards", "value": "9"}]},
                                              _p(105, "0/0")])])
    monkeypatch.setitem(STATS, 10, [_team(1, [{"player": {"id": 106}, "statistics": [{"name": "yards", "value": "3"}]}])])
    out, _ = run(tmp_path / "b")
    assert "no attempts read (no most-attempts quarterback) 1" in out          # game 10: nothing readable
    assert "the most-attempts quarterback per team-game (OUR READ): no attempts read (no most-attempts " \
           "quarterback) 1 · no roster 1" in out                               # game 11: 105 (0/0) is the pick
