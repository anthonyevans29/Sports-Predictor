"""H2 probe helpers + an offline end-to-end run (no network)."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "h2", Path(__file__).resolve().parent.parent / "scripts" / "h2_goalie_probe.py")
h2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h2)


def test_field_paths_and_goalie_hits():
    item = {"game": {"id": 1}, "players": [{"name": "X", "position": "Goalie", "saves": 30}]}
    assert h2.field_paths(item) == ["game", "game.id", "players", "players[].name",
                                    "players[].position", "players[].saves"]
    hits = h2.goalie_hits([item])
    assert ("[0].players[0].position", "Goalie") in hits
    assert ("[0].players[0].saves", 30) in hits


def test_offline_run_continues_past_missing_endpoints(monkeypatch, capsys):
    # the REAL hockey shape: flat item, "date" an ISO string, top-level timestamp
    games25 = [{"id": 10, "date": "2025-10-08T23:00:00+00:00", "timestamp": 5,
                "status": {"long": "After Over Time", "short": "AOT"},
                "teams": {"home": {"id": 7}, "away": {"id": 8}}}]
    games26 = [{"id": 20, "date": "2026-10-07T23:00:00+00:00", "timestamp": 9,
                "status": {"long": "Not Started", "short": "NS"},
                "teams": {"home": {"id": 7}, "away": {"id": 8}}}]

    def fake_get(path, **p):
        if path == "status":
            return 200, {}, [{"subscription": {"plan": "Pro"}, "requests": {"current": 3}}]
        if path == "games":
            return 200, {}, {2025: games25, 2026: games26}.get(p.get("season"), games25)
        if path == "games/events":
            return 200, {}, [{"type": "goal", "player": "Y", "comment": "Goalie pulled"}]
        return 200, {"endpoint": "This endpoint do not exist."}, []

    monkeypatch.setattr(h2, "KEY", "k")
    monkeypatch.setattr(h2, "get", fake_get)
    assert h2.main() == 0
    out = capsys.readouterr().out
    assert "/games/lineups: HTTP 200 · rows 0 · API errors" in out      # missing = finding
    assert '"date": "2025-10-08T23:00:00+00:00"' in out              # raw object printed
    assert "finished: game 10 (status AOT" in out and "upcoming: game 20" in out
    assert "goalie-hint" in out and "Q4" in out and "Nothing was written" in out


def test_no_key_stops_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(h2, "KEY", "")
    assert h2.main() == 1 and "No API key" in capsys.readouterr().out


def test_game_ts_tolerates_both_shapes():
    assert h2._game_ts({"date": "2025-10-08T23:00:00+00:00", "timestamp": 1759964400}) == 1759964400
    assert h2._game_ts({"date": "2025-10-08T23:00:00+00:00"}) == 1759964400   # string only
    assert h2._game_ts({"date": {"timestamp": 42}}) == 42                     # dict shape
    assert h2._game_ts({"date": None}) == 0 and h2._game_ts({"date": "garbage"}) == 0
    rows = [{"id": 2, "date": "2025-10-09T00:00:00Z", "status": "FT", "teams": {"home": {"id": 1}}},
            {"id": 1, "date": "2025-10-08T00:00:00Z", "status": {"short": "AP"}, "teams": {"home": {"id": 1}}}]
    assert [g[1] for g in h2._game_ids(rows, finished=True)] == [1, 2]
