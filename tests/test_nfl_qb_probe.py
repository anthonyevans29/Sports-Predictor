"""NFL quarterback probe (ARCHITECT 2026-10-13, addendum 59 item 5(h)): offline runs, no network.

"It follows scripts/lineup_history_probe.py: ids from the adapter's own mapping, never from memory; it never stops on
an error; it writes nothing; the whole output is pasted to me."
"""
import importlib.util
import sqlite3
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "qbp", Path(__file__).resolve().parent.parent / "scripts" / "nfl_qb_probe.py")
qbp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbp)


def _row(gid, ts, status, home=(1, "Home"), away=(2, "Away"), stage="Regular Season", week="Week 1"):
    return {"game": {"id": gid, "stage": stage, "week": week, "status": {"short": status},
                     "date": {"timestamp": ts, "date": "2025-09-07", "time": "17:00"}},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}}}


GAMES = [_row(10, 100, "FT"), _row(11, 200, "AOT"), _row(12, 300, "FT"), _row(13, 400, "FT"),
         _row(14, 500, "NS"), _row(15, 450, "NS"), _row(16, 50, "CANC")]

PLAYERS = [
    {"team": {"id": 1, "name": "Home"}, "groups": [
        {"name": "Passing", "players": [
            {"player": {"id": 101, "name": "A. Starter"},
             "statistics": [{"name": "comp att", "value": "22/31"}, {"name": "yards", "value": "250"}]},
            {"player": {"id": 102, "name": "B. Backup"},
             "statistics": [{"name": "comp att", "value": "1/2"}, {"name": "yards", "value": "8"}]}]},
        {"name": "Rushing", "players": []}]},
    {"team": {"id": 2, "name": "Away"}, "groups": [{"name": "Rushing", "players": []}]},
]


def _fake(calls, players=PLAYERS):
    def get(path, **p):
        calls.append((path, p))
        if path == "status":
            return 200, {}, [{"subscription": {"plan": "Pro"}, "requests": {"current": 3}}]
        if path == "leagues":
            return 200, {}, [{"seasons": [{"year": 2025, "coverage": {"games": {"statistics": {"players": True}}}}]}]
        if path == "games" and "season" in p:
            return 200, {}, GAMES
        if path == "games/statistics/players":
            return 200, {}, players if p["id"] != 15 else []
        if path == "games":
            return 200, {}, [GAMES[5]]
        if path == "players":
            return 200, {}, [{"id": 101, "name": "A. Starter", "position": "QB", "number": 9},
                             {"id": 103, "name": "C. Lineman", "position": "OT"}]
        return 200, {}, []
    return get


def test_ids_come_from_the_adapters_own_mapping():
    from src.adapters import api_american_football as af
    assert qbp.LEAGUE == af._CODE_TO_LEAGUE["NFL"] and qbp.DIRECT_BASE is af.DIRECT_BASE


def test_sampling_takes_first_middle_last_finished_and_the_next_unplayed():
    assert [qbp.game_id(r) for r in qbp.sample_finished(GAMES)] == [10, 12, 13]
    assert qbp.game_id(qbp.next_unplayed(GAMES)) == 15
    assert qbp.sample_finished([_row(1, 1, "NS")]) == [] and qbp.next_unplayed([]) is None


def test_attempts_is_our_read_of_the_line():
    assert qbp.attempts([("comp att", "22/31")]) == 31
    assert qbp.attempts([("yards", "250")]) is None
    assert qbp.attempts([("comp att", "x/y")]) is None


def test_start_paths_find_where_the_provider_says_so():
    assert qbp.start_paths(PLAYERS) == []
    flagged = [{"team": {"id": 1}, "groups": [{"name": "Passing", "players": [
        {"player": {"id": 1, "starter": True}, "statistics": [{"name": "games started", "value": "1"}]}]}]}]
    got = qbp.start_paths(flagged)
    assert any(".starter=true" in g for g in got) and any("'games started'" in g for g in got)


def test_an_offline_run_prints_the_passing_lines_fields_and_our_read(monkeypatch, tmp_path):
    calls, out = [], []
    monkeypatch.setattr(qbp, "KEY", "secret-key-xyz")
    monkeypatch.setattr(qbp, "get", _fake(calls))
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2025"], echo=out.append) == 0
    text = "\n".join(out)
    assert "league 1 (the adapter's mapping)" in text
    assert "passing fields (2): ['comp att', 'yards']" in text
    assert "raw shape (law 1: the answer as sent, whatever this probe expects): team block keys ['groups', 'team']" \
        in text and '"name": "A. Starter"' in text
    assert "101 A. Starter: comp att=22/31 · yards=250" in text
    assert "most attempts (OUR READ, not the provider's word): A. Starter (31)" in text
    assert "the provider says who started: NO key or stat name says 'start'" in text
    assert "passing: NO passing group or no players in it" in text            # the away team
    assert "Q3 2025 next unplayed: game 15" in text and "0 team block(s), 0 player(s) named" in text
    assert '"position": "QB"' in text and "C. Lineman" not in text            # the roster's QBs, every field
    assert "secret-key-xyz" not in text                                       # the key is never printed
    assert text.splitlines()[-1].startswith("✓ NFL quarterback probe complete")
    assert {c[0] for c in calls} <= {"status", "leagues", "games", "games/statistics/players", "players"}
    assert list(tmp_path.iterdir()) == []                                     # it writes nothing


def test_it_never_stops_on_an_error(monkeypatch, tmp_path):
    """Every answer an error, an empty list, or a shape the probe does not expect: it carries on to the end."""
    out = []
    n = [0]

    def bad(path, **p):
        n[0] += 1
        if path == "games" and "season" in p:
            return 200, {}, GAMES
        if path == "games/statistics/players" and n[0] % 2:
            return 200, {}, ["not a team block", {"groups": "nonsense"}]
        if path == "games/statistics/players":
            raise RuntimeError("boom")
        return None, {"request": "ConnectionError"}, []
    monkeypatch.setattr(qbp, "KEY", "k")
    monkeypatch.setattr(qbp, "get", bad)
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2023,2024"], echo=out.append) == 0
    text = "\n".join(out)
    assert "=== NFL 2023" in text and "=== NFL 2024" in text
    assert "— continuing" in text
    assert text.splitlines()[-1].startswith("✓ NFL quarterback probe complete")
    assert list(tmp_path.iterdir()) == []


def test_it_opens_no_database(monkeypatch, tmp_path):
    def no(*a, **k):
        raise AssertionError("the probe opened a database")
    monkeypatch.setattr(sqlite3, "connect", no)
    monkeypatch.setattr(qbp, "KEY", "k")
    monkeypatch.setattr(qbp, "get", _fake([]))
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2026"], echo=lambda s: None) == 0


def test_no_key_stops_before_any_request(monkeypatch):
    out, calls = [], []
    monkeypatch.setattr(qbp, "KEY", "")
    monkeypatch.setattr(qbp, "get", _fake(calls))
    assert qbp.main([], echo=out.append) == 1 and calls == [] and "No API key" in out[0]


def test_the_real_get_never_raises(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(qbp.requests, "get", boom)
    monkeypatch.setattr(qbp, "RPM", 1e9)
    assert qbp.get("status") == (None, {"request": "ConnectionError"}, [])


# --- Codex on #489 (3a327ed) ---

def _run_with(monkeypatch, tmp_path, players=PLAYERS, unplayed=None, roster=None):
    out = []
    base = _fake([], players)

    def get(path, **p):
        if path == "games/statistics/players" and p.get("id") == 15 and unplayed is not None:
            return 200, {}, unplayed
        if path == "players" and roster is not None:
            return 200, {}, roster
        return base(path, **p)
    monkeypatch.setattr(qbp, "KEY", "k")
    monkeypatch.setattr(qbp, "get", get)
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2025"], echo=out.append) == 0
    return "\n".join(out)


def test_a_stat_with_no_name_never_stops_the_summary(monkeypatch, tmp_path):
    """P1: a statistics entry with a null name beside named ones: the summary still prints and the run ends."""
    odd = [{"team": {"id": 1, "name": "Home"}, "groups": [{"name": "Passing", "players": [
        {"player": {"id": 101, "name": "A. Starter"},
         "statistics": [{"name": "comp att", "value": "22/31"}, {"name": None, "value": "7"}]}]}]}]
    text = _run_with(monkeypatch, tmp_path, players=odd)
    assert "passing fields ['None', 'comp att']" in text
    assert text.splitlines()[-1].startswith("✓ NFL quarterback probe complete")


def test_every_start_path_is_printed_never_cut(monkeypatch, tmp_path):
    """P2: twelve players carrying 'games started': all twelve are printed."""
    many = [{"team": {"id": 1, "name": "Home"}, "groups": [{"name": "Passing", "players": [
        {"player": {"id": i, "name": f"P{i}"}, "statistics": [{"name": "games started", "value": "1"}]}
        for i in range(12)]}]}]
    text = _run_with(monkeypatch, tmp_path, players=many)
    assert "(12 key(s) or stat name(s) say 'start', each with whose it is):" in text
    assert all(f"team 1 Home · group 'Passing' · {i} P{i}: statistics[0].name='games started' (value '1')" in text
               for i in range(12))


def test_the_unplayed_games_statistics_name_their_players_and_starter_fields(monkeypatch, tmp_path):
    """P1: Q3 prints every player the unplayed game's statistics name, and where the answer says 'start'."""
    named = [{"team": {"id": 2, "name": "Away"}, "groups": [{"name": "Passing", "players": [
        {"player": {"id": 201, "name": "D. Probable", "starter": True}, "statistics": []}]}]}]
    text = _run_with(monkeypatch, tmp_path, unplayed=named)
    assert "1 team block(s), 1 player(s) named, 0 entr(ies) naming nobody" in text
    assert "      Away · Passing · 201 D. Probable" in text
    assert "team 2 Away · group 'Passing' · 201 D. Probable: player.starter=true" in text


def test_the_rosters_start_evidence_is_read_from_its_quarterbacks_only(monkeypatch, tmp_path):
    """P2: a 'start' field on a lineman is not evidence about the quarterback; each QB's own entry is read."""
    roster = [{"id": 101, "name": "A. Starter", "position": "QB", "depth_start": 1},
              {"id": 103, "name": "C. Lineman", "position": "OT", "starter": True}]
    text = _run_with(monkeypatch, tmp_path, roster=roster)
    assert "'start' in this quarterback's entry: ['depth_start=1']" in text
    assert "starter=true" not in text and "C. Lineman" not in text


# --- Codex on #489, second round (cc71fa3) ---

def test_wrapped_roster_rows_are_read_as_the_qb_audit_reads_them(monkeypatch, tmp_path):
    """P1: a roster row shaped {"player": {...}} is unwrapped (qb_audit.roster_index's own reading)."""
    roster = [{"player": {"id": 101, "name": "A. Starter", "position": "QB"}},
              {"player": {"id": 103, "name": "C. Lineman", "position": "OT"}}]
    text = _run_with(monkeypatch, tmp_path, roster=roster)
    assert "2 player(s), 1 at QB" in text and '"name": "A. Starter"' in text and "C. Lineman" not in text


def test_the_unplayed_games_own_answer_is_printed_whole(monkeypatch, tmp_path):
    """P1: /games?id is printed verbatim, so a player named under any key (not only one saying 'start') shows."""
    out = []
    base = _fake([])

    def get(path, **p):
        if path == "games" and p.get("id") == 15:
            return 200, {}, [{**GAMES[5], "quarterback": {"home": {"id": 101, "name": "A. Starter"}}}]
        return base(path, **p)
    monkeypatch.setattr(qbp, "KEY", "k")
    monkeypatch.setattr(qbp, "get", get)
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2025"], echo=out.append) == 0
    assert any('"quarterback": {"home": {"id": 101, "name": "A. Starter"}}' in ln for ln in out)


def test_a_leagues_answer_of_another_shape_never_stops_the_run(monkeypatch, tmp_path):
    """P1: a seasons value that is not a list, or a year that is a list: Q1 says so and every season is probed."""
    for seasons in (5, [{"year": [2025], "coverage": {}}]):
        out = []
        base = _fake([])

        def get(path, _s=seasons, **p):
            if path == "leagues":
                return 200, {}, [{"seasons": _s}]
            return base(path, **p)
        monkeypatch.setattr(qbp, "KEY", "k")
        monkeypatch.setattr(qbp, "get", get)
        monkeypatch.chdir(tmp_path)
        assert qbp.main(["--seasons", "2025"], echo=out.append) == 0
        text = "\n".join(out)
        assert "seasons listed: -..- (0)" in text and "=== NFL 2025" in text
        assert text.splitlines()[-1].startswith("✓ NFL quarterback probe complete")


def test_a_malformed_unplayed_statistics_answer_still_reaches_both_rosters(monkeypatch, tmp_path):
    """P1: a team or player of another shape in the unplayed game's statistics: both rosters are still asked."""
    odd = [{"team": "Away", "groups": [{"name": "Passing", "players": [{"player": "D. Probable"}]}]},
           {"team": {"id": 1}, "groups": [{"name": "Passing", "players": [{"player": {"id": 9, "name": "X"}}]}]}]
    text = _run_with(monkeypatch, tmp_path, unplayed=odd)
    assert "1 player(s) named, 1 entr(ies) naming nobody" in text and '{"player": "D. Probable"}' in text
    assert text.count("at QB (HTTP 200)") == 2


def test_an_unknown_status_is_unplayed_as_the_adapter_reads_it():
    """P1: the adapter reads an unknown status short as SCHEDULED (_STATUS.get(short, SCHEDULED)); so does Q3."""
    rows = [_row(20, 100, "FT"), _row(21, 300, "TBD"), _row(22, 200, "NS")]
    assert qbp.game_id(qbp.next_unplayed(rows)) == 22
    assert qbp.game_id(qbp.next_unplayed([_row(21, 300, "TBD")])) == 21


def test_a_kickoff_the_adapter_cannot_read_drops_only_that_row():
    """A string timestamp beside a missing one never stops the sampling: the adapter's parse drops the row."""
    bad = _row(30, "soon", "FT")
    rows = [bad, _row(31, 100, "FT"), _row(32, 200, "FT")]
    assert [qbp.game_id(r) for r in qbp.sample_finished(rows)] == [31, 32]


# --- Codex on #489, third round (853d0ee) ---

def test_a_game_with_no_status_and_both_totals_is_finished_not_unplayed():
    """P1: the score-presence rule, the adapter's own since #493 (the probe reads the adapter's parse only)."""
    done = {**_row(40, 100, "FT"), "game": {**_row(40, 100, "FT")["game"], "status": {}},
            "scores": {"home": {"total": 20}, "away": {"total": 17}}}
    nostatus = {**_row(41, 150, "NS"), "scores": {"home": {"total": None}, "away": {"total": None}}}
    nostatus["game"] = {k: v for k, v in nostatus["game"].items() if k != "status"}
    rows = [done, nostatus, _row(42, 200, "NS")]
    assert [qbp.game_id(r) for r in qbp.sample_finished(rows)] == [40]
    assert qbp.game_id(qbp.next_unplayed(rows)) == 41             # no status and no totals: still unplayed
    assert qbp.game_id(qbp.next_unplayed([done, _row(42, 200, "NS")])) == 42


# --- addendum 60 item 5: #491 goes into #489; "A probe's receipt cuts nothing" ---

def test_nothing_the_probe_prints_is_cut():
    """No slice of anything printed: a long 'start' value, a long error body, a raw shape, all whole."""
    import inspect
    src = inspect.getsource(qbp)
    assert "[:" not in src.replace("[:]", "")
    long_value = {"depth": [{"id": i, "name": f"Q{i}"} for i in range(30)]}
    got = qbp.start_paths({"starters": long_value})
    assert got == [f"starters={__import__('json').dumps(long_value, sort_keys=True)}"]


def test_a_year_sent_as_digits_is_that_year_in_q1(monkeypatch, tmp_path):
    out = []
    base = _fake([])

    def get(path, **p):
        if path == "leagues":
            return 200, {}, [{"seasons": [{"year": "2025", "coverage": {"games": {"statistics": {"players": True}}}},
                                          {"year": "twenty", "coverage": {}}]}]
        return base(path, **p)
    monkeypatch.setattr(qbp, "KEY", "k")
    monkeypatch.setattr(qbp, "get", get)
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2025"], echo=out.append) == 0
    text = "\n".join(out)
    assert "seasons listed: 2025..2025 (1)" in text and '2025 coverage: {"games"' in text
    assert "seasons whose year is not a year: ['twenty']" in text


def test_a_status_or_stage_of_another_shape_is_tallied_by_its_repr(monkeypatch, tmp_path):
    odd = _row(50, 50, "FT")
    odd["game"] = {**odd["game"], "status": {"short": ["FT"]}, "stage": {"x": 1}}
    rows = GAMES + [odd]
    out = []
    base = _fake([])

    def get(path, **p):
        if path == "games" and "season" in p:
            return 200, {}, rows
        return base(path, **p)
    monkeypatch.setattr(qbp, "KEY", "k")
    monkeypatch.setattr(qbp, "get", get)
    monkeypatch.chdir(tmp_path)
    assert qbp.main(["--seasons", "2025"], echo=out.append) == 0
    text = "\n".join(out)
    assert "by status {'FT': 3, 'AOT': 1, 'NS': 2, 'CANC': 1, \"['FT']\": 1}" in text
    assert "by stage {'Regular Season': 7, \"{'x': 1}\": 1}" in text
    assert "game 10 (" in text                          # the season's samples still run


def test_a_malformed_group_never_drops_the_finished_game(monkeypatch, tmp_path):
    odd = [{"team": {"id": 1, "name": "Home"}, "groups": ["junk", {"name": "Passing", "players": [
        "junk", {"player": {"id": 101, "name": "A. Starter"}, "statistics": [{"name": "comp att", "value": "22/31"}]}]}]},
           {"team": {"id": 2, "name": "Away"}, "groups": "not a list"}]
    text = _run_with(monkeypatch, tmp_path, players=odd)
    assert "101 A. Starter: comp att=22/31" in text
    assert "groups not a list: \"not a list\"" in text
    assert "✗" not in text


def test_start_fields_say_whose_they_are_and_a_lineman_is_told_from_the_quarterback(monkeypatch, tmp_path):
    odd = [{"team": {"id": 1, "name": "Home"}, "groups": [
        {"name": "Passing", "players": [{"player": {"id": 101, "name": "A. Starter"},
                                         "statistics": [{"name": "comp att", "value": "22/31"}]}]},
        {"name": "Defensive", "players": [{"player": {"id": 103, "name": "C. Lineman"},
                                           "statistics": [{"name": "games started", "value": "1"}]}]}]}]
    text = _run_with(monkeypatch, tmp_path, players=odd)
    assert "team 1 Home · group 'Defensive' · 103 C. Lineman: statistics[0].name='games started'" in text
    assert "group 'Passing' · 101 A. Starter:" not in text


def test_a_tie_on_attempts_never_compares_names(monkeypatch, tmp_path):
    odd = [{"team": {"id": 1, "name": "Home"}, "groups": [{"name": "Passing", "players": [
        {"player": {"id": 101, "name": "A. Starter"}, "statistics": [{"name": "comp att", "value": "10/20"}]},
        {"player": {"id": 102, "name": None}, "statistics": [{"name": "comp att", "value": "9/20"}]}]}]}]
    text = _run_with(monkeypatch, tmp_path, players=odd)
    assert "most attempts (OUR READ, not the provider's word):" in text and "✗" not in text


def test_a_placeholder_entry_is_not_counted_as_named(monkeypatch, tmp_path):
    ph = [{"team": {"id": 2, "name": "Away"}, "groups": [{"name": "Passing", "players": [
        {"statistics": []}, {"player": None, "statistics": []}, {"player": {"id": 201, "name": "D. Probable"}}]}]}]
    text = _run_with(monkeypatch, tmp_path, unplayed=ph)
    assert "1 team block(s), 1 player(s) named, 2 entr(ies) naming nobody" in text
    assert 'no identity: {"statistics": []}' in text and 'no identity: {"player": null, "statistics": []}' in text
