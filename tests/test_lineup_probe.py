"""Lineup-history probe helpers + an offline end-to-end run (no network)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "lp", Path(__file__).resolve().parent.parent / "scripts" / "lineup_history_probe.py")
lp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lp)

LEAGUE = {"seasons": [
    {"year": 2014, "coverage": {"fixtures": {"lineups": False, "statistics_players": False}, "players": True}},
    {"year": 2016, "coverage": {"fixtures": {"lineups": True, "statistics_players": False}, "players": True}},
    {"year": 2018, "coverage": {"fixtures": {"lineups": False, "statistics_players": False}, "players": True}},
    {"year": 2020, "coverage": {"fixtures": {"lineups": True, "statistics_players": True}, "players": True}},
    {"year": 2025, "coverage": {"fixtures": {"lineups": True, "statistics_players": True}, "players": True}},
    {"year": 2026, "coverage": {"fixtures": {"lineups": True, "statistics_players": True}, "players": True}},
]}


def test_coverage_and_sampling():
    cov = lp.declared_coverage(LEAGUE)
    assert cov[2016] == (True, False, True) and cov[2014][0] is False
    # in-progress 2026 excluded; undeclared seasons never sampled
    assert lp.sample_seasons(cov) == [2025, 2020, 2016]
    assert lp.sample_seasons({2019: (False, False, False)}) == []


def test_summaries_count_fields_not_guess():
    lineups = [{"team": {"name": "A"}, "formation": "4-4-2", "coach": {"name": "C"},
                "startXI": [{"player": {"id": 1, "name": "p1", "pos": "G", "grid": "1:1"}}],
                "substitutes": [{"player": {"id": None, "name": "p2", "pos": None, "grid": None}},
                                {"player": {"name": None}}]}]
    t = lp.summarize_lineups(lineups)[0]
    assert (t["xi"], t["subs"], t["named"], t["player_id"], t["pos"], t["grid"], t["coach"]) == \
        (1, 2, 2, 1, 1, 1, True)
    players = [{"players": [{"statistics": [{"games": {"minutes": 90, "position": "G", "substitute": False}}]},
                            {"statistics": [{"games": {"minutes": None, "position": None}}]}]}]
    assert lp.summarize_players(players) == {"players": 2, "minutes": 1, "position": 1, "substitute": 1}


def test_offline_run_continues_past_empty_payloads(monkeypatch, capsys):
    fixtures = [{"fixture": {"id": 99, "timestamp": 2, "date": "2025-08-12T18:00", "status": {"short": "PEN"}},
                 "league": {"round": "1st Round"}},
                {"fixture": {"id": 98, "timestamp": 9, "status": {"short": "NS"}}}]

    def fake_get(path, **p):
        if path == "status":
            return 200, {}, [{"subscription": {"plan": "Pro"}, "requests": {"current": 1}}]
        if path == "leagues":
            return 200, {}, [LEAGUE]
        if path == "fixtures":
            return 200, {}, fixtures
        return 200, {}, []          # lineups/players missing = a finding, not a crash

    monkeypatch.setattr(lp, "KEY", "k")
    monkeypatch.setattr(lp, "get", fake_get)
    assert lp.main(["--comps", "EFL"]) == 0
    out = capsys.readouterr().out
    assert "=== EFL (league 48) ===" in out
    assert "declared lineups: 2016..2026 (4 seasons)" in out
    assert "GAPS after first coverage: [2018]" in out
    assert "Q2 2016 fixture 99" in out and "/fixtures/lineups: NO ROWS" in out
    assert "Nothing was written" in out


def test_stops_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(lp, "KEY", "")
    assert lp.main([]) == 1 and "No API key" in capsys.readouterr().out
    monkeypatch.setattr(lp, "KEY", "k")
    assert lp.main(["--comps", "XX"]) == 1 and "Unknown codes" in capsys.readouterr().out
