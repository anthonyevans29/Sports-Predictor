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
    # the gate leaves the preseason out: the two regular-season games, one with both teams (addendum 170 item 2(a))
    assert "coverage gate 2025 (regular season and postseason, both teams >= 98%): 1/2 = 50.0% · BELOW" in out
    assert len(calls) == 1 + 3 + 2                                 # the list, three finished games, two rosters
    assert "failed 0 · answered with no rows 1" in out              # the preseason game's empty answer


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


def test_failed_reads_are_kept_out_of_the_counts_and_the_gate_is_incomplete(tmp_path):
    """Codex on #710 (P1): a failed statistics or roster read is neither "passing neither" nor an empty roster; the
    gate says INCOMPLETE and names it, never BELOW."""
    def get(path, **p):
        if path == "games/statistics/players" and p["id"] == 11:
            return 429, {"rateLimit": "Too many requests"}, []
        if path == "players" and p["team"] == 2:
            return None, {"request": "Timeout"}, []
        return fake([])(path, **p)
    out = []
    assert qbc.main(["--seasons", "2025", "--save", str(tmp_path / "pay")], echo=out.append, get=get) == 0
    out = "\n".join(out)
    assert "Regular Season: listed 3 · finished 2 · passing both teams 1 · one team 0 · neither 0 · statistics read " \
           "failed 1" in out
    assert "FAILED reads 2 (kept out of every count; a re-run asks them again): statistics of game 11, roster of " \
           "team 2" in out
    assert "R roster join, every passing line: no roster read for the team 1 · same team 2" in out
    # #715 item 1: the gate is INCOMPLETE for the failed statistics read only; the roster read never decides it
    assert ("1/2 = 50.0% · INCOMPLETE (1 games-list or statistics read(s) failed or capped: a re-run completes them)"
            in out) and "BELOW" not in out
    assert "failed 2 · answered with no rows 1" in out


def test_a_tie_for_the_most_attempts_names_no_quarterback(tmp_path, monkeypatch):
    """Codex on #710: two lines tied at the most attempts give no pick, counted, never the provider's row order."""
    monkeypatch.setitem(STATS, 11, [_team(1, [_p(101, "20/30"), _p(102, "18/30")])])
    out, _ = run(tmp_path)
    assert "tied for the most attempts (no most-attempts quarterback) 1" in out


def test_a_stage_not_identified_stays_out_of_the_gate(tmp_path, monkeypatch):
    """Codex on #710: a finished game with no stage, or a novel one, is never counted as regular season or
    postseason; it is printed and the gate reads INCOMPLETE."""
    monkeypatch.setattr(qbc, "GATE", 0.5)
    kept = GAMES[1]
    try:
        GAMES[1] = _row(11, 200, "FT", stage=None)
        out, _ = run(tmp_path)
        assert "stages not identified (missing or novel; not in the gate): finished 1" in out
        assert "1/1 = 100.0% · INCOMPLETE (1 finished game(s) of a stage not identified)" in out
        GAMES[1] = _row(11, 200, "FT", stage="Post Season")
        out, _ = run(tmp_path / "b")
        assert "1/2 = 50.0% · MEETS" in out
    finally:
        GAMES[1] = kept


# ---- #712 items 1 and 2 (ARCHITECT 2026-10-27 13:45 ET: "fixed in ONE small PR before the receipt runs") ----------

def test_a_field_absent_from_a_whole_season_is_on_its_field_line(tmp_path):
    """Item 1: the field universe is every field any season of the run sends; a season that sends none of a field
    lists it "on 0, ABSENT", never leaves it off (sack yards decide ANY/A against NY/A0, spec 3.1)."""
    g26 = [_row(20, 500, "FT")]
    s26 = {20: [_team(1, [_p(101, "20/30")]), _team(2, [_p(201, "18/25")])]}          # no 'sacks' on any line

    def get(path, **p):
        if path == "games":
            return 200, {}, (g26 if p["season"] == 2026 else GAMES)
        if path == "games/statistics/players":
            return 200, {}, (s26 if p["id"] == 20 else STATS).get(p["id"], [])
        return fake([])(path, **p)
    out = []
    assert qbc.main(["--seasons", "2025,2026", "--save", str(tmp_path / "pay")], echo=out.append, get=get) == 0
    out = "\n".join(out)
    s25, s26_text = out.split("== season 2026", 1)
    assert "'sacks' on 1, missing/empty 3" in s25
    assert "'sacks' on 0, ABSENT from the whole season (2 lines)" in s26_text
    assert "field universe (#712 item 1): 3 passing field(s)" in out


def test_a_finished_game_the_parse_drops_makes_the_gate_incomplete(tmp_path):
    """Item 2: a regular-season row the provider marks FT but the adapter's parse cannot read (no kickoff) is named
    and makes the gate INCOMPLETE; an all-star exhibition is the adapter's exclusion, counted apart, never a gap; a
    dropped row not marked finished is neither."""
    bad = _row(14, 0, "FT")
    bad["game"]["date"] = {}                                               # no kickoff: the parse drops it
    star = _row(15, 600, "FT", home=(31, "AFC"), away=(32, "NFC"), stage="Post Season")
    ns = _row(16, 0, "NS")
    ns["game"]["date"] = {}
    rows = GAMES + [bad, star, ns]

    def get(path, **p):
        return (200, {}, rows) if path == "games" else fake([])(path, **p)
    out = []
    assert qbc.main(["--seasons", "2025", "--save", str(tmp_path / "pay")], echo=out.append, get=get) == 0
    out = "\n".join(out)
    assert "FINISHED BUT DROPPED by the adapter's parse 1 (no statistics read; the gate cannot check them): game 14" in out
    assert "non-competitive, excluded by the adapter (all-star side 'AFC'): 1 (not in the gate)" in out
    assert "1/2 = 50.0% · INCOMPLETE (1 finished game(s) dropped by the parse)" in out



def test_an_absence_is_never_claimed_for_a_season_whose_reads_are_incomplete(tmp_path):
    """Codex on #713: when a season's statistics reads are incomplete (a failed read here), a field the season's read
    lines lack is UNKNOWN for the season, never ABSENT from the whole season."""
    g26 = [_row(20, 500, "FT"), _row(21, 600, "FT")]
    s26 = {20: [_team(1, [_p(101, "20/30")]), _team(2, [_p(201, "18/25")])]}

    def get(path, **p):
        if path == "games":
            return 200, {}, (g26 if p["season"] == 2026 else GAMES)
        if path == "games/statistics/players":
            if p["id"] == 21:
                return 500, {}, []
            return 200, {}, (s26 if p["id"] == 20 else STATS).get(p["id"], [])
        return fake([])(path, **p)
    out = []
    assert qbc.main(["--seasons", "2025,2026", "--save", str(tmp_path / "pay")], echo=out.append, get=get) == 0
    s26_text = "\n".join(out).split("== season 2026", 1)[1]
    assert "'sacks' on 0 of the 2 lines read, UNKNOWN for the season (reads incomplete)" in s26_text
    assert "ABSENT" not in s26_text



# ---- #715 (ARCHITECT 2026-10-27 14:35 ET: "#715 (both items) goes in before the receipts run") -------------------

def test_a_failed_roster_read_decides_neither_the_field_absence_nor_the_gate(tmp_path):
    """Item 1: every statistics read of 2026 completes and its roster read fails; the season's absent field reads
    ABSENT (the passing lines establish it), the gate reads its verdict, and the roster failure is listed."""
    g26 = [_row(20, 500, "FT")]
    s26 = {20: [_team(1, [_p(101, "20/30")]), _team(2, [_p(201, "18/25")])]}

    def get(path, **p):
        if path == "games":
            return 200, {}, (g26 if p["season"] == 2026 else GAMES)
        if path == "games/statistics/players":
            return 200, {}, (s26 if p["id"] == 20 else STATS).get(p["id"], [])
        if path == "players" and p["season"] == 2026:
            return 503, {}, []
        return fake([])(path, **p)
    out = []
    assert qbc.main(["--seasons", "2025,2026", "--save", str(tmp_path / "pay")], echo=out.append, get=get) == 0
    s26_text = "\n".join(out).split("== season 2026", 1)[1]
    assert "'sacks' on 0, ABSENT from the whole season (2 lines)" in s26_text and "UNKNOWN" not in s26_text
    assert "FAILED reads 2" in s26_text and "roster of team 1" in s26_text
    assert "1/1 = 100.0% · MEETS" in s26_text


def test_a_malformed_row_is_counted_and_named_never_a_traceback(tmp_path):
    """Item 2: a row whose game is not an object, a row that is not an object, and a row whose home team is a string
    are counted under their own status and named; they make the gate INCOMPLETE and an absence UNKNOWN."""
    rows = GAMES + [{"game": ["x"], "teams": {}}, "oops", {"game": {"id": 30}, "teams": {"home": "Bills"}}]

    def get(path, **p):
        return (200, {}, rows) if path == "games" else fake([])(path, **p)
    out = []
    assert qbc.main(["--seasons", "2025", "--save", str(tmp_path / "pay")], echo=out.append, get=get) == 0
    out = "\n".join(out)
    assert "(not the provider's row shape) 3" in out
    assert "NOT THE PROVIDER'S ROW SHAPE 3 (counted; may be finished games the gate cannot check)" in out
    assert "1/2 = 50.0% · INCOMPLETE (3 listed row(s) not in the provider's shape)" in out
    assert "SUMMARY 2025: listed 7 · finished 3" in out                     # the malformed rows are listed (Codex)
    assert "(not the provider's row shape): listed 3 · finished 0" in out
