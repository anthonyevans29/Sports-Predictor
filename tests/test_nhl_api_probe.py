"""NHL-API-PROBE (architect 2026-09-30): the discovery + verdict logic on fake
responses. The shapes below exercise the FINDERS (ids + a start-time key,
lists under a goalie-named key, starter flags, stat keys); they are not a claim
about the real API, which the operator's run reports."""
import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "nhl_api_probe", Path(__file__).resolve().parents[1] / "scripts" / "nhl_api_probe.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

NOW = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def goalies(starter=True, stats=True):
    g = {"playerId": 8471679, "name": {"default": "C. Price"}}
    if stats:
        g.update({"saves": 30, "shotsAgainst": 32, "savePctg": 0.938})
    if starter is not None:
        g["starter"] = starter
    return {"playerByGameStats": {"homeTeam": {"goalies": [g]}, "awayTeam": {"goalies": [dict(g, starter=False)]}}}


def world(pre_starter=True, mp_csv=False, blocked=False):
    fin = {"id": 1, "startTimeUTC": "2026-10-03T23:00:00Z", "gameState": "OFF",
           "homeTeam": {"abbrev": "TOR"}, "awayTeam": {"abbrev": "MTL"}}
    up = {"id": 2, "startTimeUTC": (NOW + timedelta(minutes=90)).isoformat().replace("+00:00", "Z"),
          "gameState": "FUT", "homeTeam": {"abbrev": "BOS"}, "awayTeam": {"abbrev": "NYR"}}
    sched = lambda games: json.dumps({"gameWeek": [{"games": games}]}).encode()
    routes = {
        f"/v1/schedule/{(TODAY - timedelta(days=7)).isoformat()}": sched([fin]),
        f"/v1/schedule/{TODAY.isoformat()}": sched([up]),
        f"/v1/schedule/{(TODAY + timedelta(days=1)).isoformat()}": sched([]),
        "/v1/gamecenter/1/boxscore": json.dumps(goalies()).encode(),
        "/v1/roster/BOS/current": json.dumps({"forwards": [{}], "goalies": [{"id": 1}, {"id": 2}]}).encode(),
        "/v1/gamecenter/2/boxscore": json.dumps({"gameState": "FUT"}).encode(),
        "/v1/gamecenter/2/landing": json.dumps({"matchup": goalies(starter=pre_starter, stats=False)}).encode(),
    }
    for yr in (2023, 2024, 2025):
        routes[f"/v1/schedule/{yr}-10-20"] = sched([dict(fin, id=100 + yr)])
        routes[f"/v1/gamecenter/{100 + yr}/boxscore"] = json.dumps(goalies()).encode()

    def fetch(url):
        if blocked:
            return 403, "text/html", b""
        if url.startswith(P.BASE):
            body = routes.get(url[len(P.BASE):])
            return (200, "application/json", body) if body else (404, "application/json", b"")
        if mp_csv and url == P.MONEYPUCK_CANDIDATES[0]:
            return 200, "text/csv", b"date,team,goalie_name,starter_confirmed\n2026-10-10,BOS,J. Swayman,1\n"
        return 404, "text/html", b""
    return fetch


def test_green_when_the_nhl_api_names_a_starter_before_puck_drop():
    r = P.run(world(), TODAY, NOW)
    assert r["verdict"] == {"schedule": "FEEDABLE", "goalie_game_stats": "FEEDABLE",
                            "starter_flag_postgame": "FEEDABLE", "roster_goalies": "FEEDABLE",
                            "starting_goalie_pregame": "FEEDABLE", "history_2023_2025": "FEEDABLE",
                            "moneypuck_starters_csv": "NOT"}
    assert r["h2_green"] is True and r["N4_max_lead_minutes"] == 90
    assert r["N2_boxscore"]["goalie_stat_keys"] == ["savePctg", "saves", "shotsAgainst"]
    assert r["N3_roster"] == {"team": "BOS", "http": 200, "goalie_keys": ["goalies"], "n_goalies": 2}
    assert r["N1_schedule"][TODAY.isoformat()]["key_paths"][:1] == ["gameWeek"]      # dumped, not assumed


def test_no_pregame_starter_but_moneypuck_csv_is_the_fallback():
    r = P.run(world(pre_starter=False, mp_csv=True), TODAY, NOW)
    assert r["verdict"]["starting_goalie_pregame"] == "NOT" and r["N4_max_lead_minutes"] is None
    assert r["verdict"]["moneypuck_starters_csv"] == "FEEDABLE"
    assert r["M1_moneypuck"][0]["goalie_columns"] == ["goalie_name", "starter_confirmed"]
    assert r["h2_green"] is True


def test_a_blocked_host_is_all_not_and_never_green():
    r = P.run(world(blocked=True), TODAY, NOW)
    assert set(r["verdict"].values()) == {"NOT"} and r["h2_green"] is False
    assert all(v["http"] == 403 for v in r["N1_schedule"].values())


def test_out_refuses_data_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "http_get", world())
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    assert P.main(["--date", TODAY.isoformat(), "--out", "data/x.jsonl"]) == 1
    assert P.main(["--date", TODAY.isoformat(), "--out", "probe.jsonl"]) == 0
    assert (tmp_path / "probe.jsonl").read_text().count("\n") == 1
    assert "H2 REOPENING CONDITION" in capsys.readouterr().out
