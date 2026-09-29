"""MLB PHASE B probe (architect 2026-09-29): endpoint classification and the
pitcher/bullpen/umpire verdict, on a fake provider. The live run needs the
laptop's API-Baseball key."""
import importlib.util
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "mlb_phase_b_probe", Path(__file__).resolve().parents[1] / "scripts" / "mlb_phase_b_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

GAME = {"id": 555, "date": "2026-09-28T23:05:00+00:00", "status": {"short": "FT", "long": "Finished"},
        "teams": {"home": {"id": 1, "name": "New York Yankees"}, "away": {"id": 2, "name": "Boston Red Sox"}},
        "scores": {"home": {"hits": 9, "errors": 0, "innings": {"1": 0}, "total": 5}, "away": {"total": 3}}}


def fake(existing: dict):
    calls = []

    def fetch(path, params):
        calls.append((path, dict(params)))
        if path == "games":
            return {"results": 1, "response": [GAME] if params.get("date") == "2026-09-28" else []}
        if path in existing:
            v = existing[path]
            if isinstance(v, Exception):
                raise v
            return v
        raise RuntimeError(f"GET {path}: API error {{'endpoint': 'This endpoint do not exist.'}}")
    return fetch, calls


def test_documented_shape_no_player_endpoints_means_not_feedable():
    fetch, calls = fake({"timezone": {"results": 1, "response": ["UTC"]}})
    r = probe.run(fetch, 2026, datetime(2026, 9, 29, 12))
    assert r["game_id"] == 555 and r["control_ok"]
    st = {e["path"]: e["status"] for e in r["endpoints"]}
    assert st["timezone"] == "EXISTS" and st["players"] == "NO-SUCH-ENDPOINT" and st["umpires"] == "NO-SUCH-ENDPOINT"
    assert r["game_flags"] == {"pitchers": [], "bullpen": [], "umpires": [], "lineup/player": []}
    assert all(not v["feedable"] for v in r["verdict"].values())
    assert sum(1 for p, _ in calls if p != "games") == len(probe.candidates(555, 2026))   # one call each


def test_param_rejection_means_the_endpoint_exists_and_fields_are_flagged():
    players = {"results": 2, "response": [{"player": {"id": 9, "name": "Gerrit Cole", "position": "Starting Pitcher"},
                                           "statistics": {"innings_pitched": 180.1, "saves": 0}}]}
    fetch, _ = fake({"timezone": {"results": 1, "response": ["UTC"]},
                     "players/statistics": players,
                     "players": RuntimeError("GET players: API error {'season': 'The Season field is required.'}"),
                     "games/lineups": RuntimeError("GET games/lineups: HTTP 500 — boom")})
    r = probe.run(fetch, 2026, datetime(2026, 9, 29, 12))
    st = {e["path"]: e for e in r["endpoints"]}
    assert st["players"]["status"] == "EXISTS-PARAMS" and st["games/lineups"]["status"] == "ERROR"
    ps = st["players/statistics"]
    assert ps["status"] == "EXISTS" and ps["item_keys"] == ["player", "statistics"]
    assert "player.position" not in ps["flags"]["pitchers"]                    # key names, not values
    assert ps["flags"]["bullpen"] == ["statistics.innings_pitched", "statistics.saves"]
    assert r["verdict"]["bullpen"]["feedable"] and r["verdict"]["bullpen"]["where"][0].startswith("/players/statistics")
    assert not r["verdict"]["umpires"]["feedable"]


def test_no_finished_game_skips_game_scoped_candidates():
    def fetch(path, params):
        if path == "games":
            return {"response": []}
        if path == "timezone":
            return {"response": ["UTC"]}
        raise RuntimeError("API error {'endpoint': 'This endpoint do not exist.'}")
    r = probe.run(fetch, 2026, datetime(2026, 9, 29, 12))
    assert r["game_id"] is None and not any(e["path"].startswith("games/") for e in r["endpoints"])
