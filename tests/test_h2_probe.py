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
    games25 = [{"game": {"id": 10, "status": {"short": "AOT"}, "date": {"timestamp": 5}},
                "teams": {"home": {"id": 7}}}]
    games26 = [{"game": {"id": 20, "status": {"short": "NS"}, "date": {"timestamp": 9}},
                "teams": {"home": {"id": 7}}}]

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
    assert "goalie-hint" in out and "Q4" in out and "Nothing was written" in out


def test_no_key_stops_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(h2, "KEY", "")
    assert h2.main() == 1 and "No API key" in capsys.readouterr().out
