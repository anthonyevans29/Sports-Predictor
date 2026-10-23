"""Addendum 157 item 2(b): the NHL starter timing probe, on fake API answers and a fake clock (no network)."""
from __future__ import annotations

import importlib.util
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("nhl_starter_timing_probe", ROOT / "scripts" / "nhl_starter_timing_probe.py")
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)

DAY = date(2026, 10, 24)
START = datetime(2026, 10, 24, 23, 0)
GAME = 2026020150


def _team(place, common, abbrev):
    return {"placeName": {"default": place}, "commonName": {"default": common}, "abbrev": abbrev}


def _schedule():
    g = lambda gid, start, gt=2: {"id": gid, "startTimeUTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "gameType": gt,
                                   "homeTeam": _team("Boston", "Bruins", "BOS"),
                                   "awayTeam": _team("Toronto", "Maple Leafs", "TOR")}
    return {"gameWeek": [{"games": [g(GAME, START), g(GAME + 1, START + timedelta(days=1)),  # next day: not polled
                                    g(2026010001, START, gt=1)]}]}                          # preseason: not polled


def _box(state, starters: bool):
    goalies = lambda side, a, b: [{"playerId": a, "starter": starters}, {"playerId": b, "starter": False}]
    return {"gameState": state, "playerByGameStats": {"homeTeam": {"goalies": goalies("home", 1, 2)},
                                                      "awayTeam": {"goalies": goalies("away", 3, 4)}}}


class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=max(s, 1))


def _fetch(clock):
    def f(url):
        if "/schedule/" in url:
            return 200, _schedule()
        if url.endswith("/boxscore"):
            named = clock.t >= START - timedelta(minutes=15)       # the starter flag appears from T-15
            return 200, _box("PRE" if named else "FUT", named)
        if url.endswith("/landing"):
            return 200, {"gameState": "FUT", "matchup": {"goalieComparison": {
                "homeTeam": {"leaders": [{"playerId": 1}, {"playerId": 2}]},
                "awayTeam": {"leaders": [{"playerId": 3}, {"playerId": 4}]}}}}
        return 404, None
    return f


def test_the_day_is_the_nhl_day_and_types_2_3_only():
    gs = tp.day_games(_schedule(), DAY)
    assert [g["id"] for g in gs] == [GAME]
    assert [tp.label(o) for _, _, o in tp.plan(gs)] == ["T-120", "T-90", "T-60", "T-45", "T-30", "T-15",
                                                        "T-0 (puck drop)"]


def test_a_starter_is_named_by_the_flag_and_listed_only_otherwise():
    s = tp.goalies_named(_box("PRE", True))
    assert s["home"]["starter"] == 1 and s["away"]["starter"] == 3 and s["home"]["how"] == "flag starter=True"
    s = tp.goalies_named(_box("FUT", False))
    assert s["home"]["starter"] is None and s["home"]["how"] == "listed, no starter named"
    assert tp.goalies_named({"x": 1})["away"]["how"] == "none"


def test_the_polls_are_stamped_by_our_clock_and_summarized(capsys):
    clock = Clock(START - timedelta(minutes=125))
    assert tp.run(DAY, _fetch(clock), clock.now, clock.sleep) == 0
    out = capsys.readouterr().out
    assert "1 game(s) of types 2/3" in out
    assert f"  {GAME} T-15 · boxscore · HTTP 200 · polled 22:45:00Z · gameState PRE · away starter 3" in out
    assert f"  {GAME} T-30 · boxscore · HTTP 200 · polled 22:30:00Z · gameState FUT · away listed, no starter named" in out
    assert f"{GAME} Toronto Maple Leafs @ Boston Bruins · boxscore: first at T-15 (answered without at T-30)" in out
    assert "landing: never named" in out and "right-rail: never named" in out
    assert "requests: schedule 1 · boxscore HTTP 200 7 · landing HTTP 200 7 · right-rail HTTP 404 7" in out


def test_a_late_start_misses_polls_and_never_counts_them(capsys):
    clock = Clock(START - timedelta(minutes=40))     # T-120..T-60 more than 5 minutes late; T-45 at 5 minutes is polled
    tp.run(DAY, _fetch(clock), clock.now, clock.sleep)
    out = capsys.readouterr().out
    assert out.count("· MISSED (") == 3 and "3 poll(s) missed" in out and f"{GAME} T-45 · boxscore · HTTP 200" in out


def test_plan_polls_nothing(capsys):
    calls = []
    f = _fetch(Clock(START))
    tp.run(DAY, lambda u: (calls.append(u), f(u))[1], lambda: START, lambda s: None, plan_only=True)
    assert len(calls) == 1 and "plan 21:00Z" in capsys.readouterr().out


def test_stored_counts_rows_captured_before_the_game(tmp_path, capsys):
    p = tmp_path / "s.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE nhl_goalie_appearances (id INTEGER PRIMARY KEY, nhl_game_id INT, game_start TEXT, "
                "captured_at TEXT, is_starter INT)")
    con.executemany("INSERT INTO nhl_goalie_appearances (nhl_game_id, game_start, captured_at, is_starter) "
                    "VALUES (?,?,?,?)", [(2024020001, "2024-10-09 23:00:00", "2024-10-10 12:00:00", 1),
                                         (2024020001, "2024-10-09 23:00:00", "2024-10-10 12:00:00", 0),
                                         (2025020001, "2025-10-08 23:00:00", "2025-10-08 20:00:00", None)])
    con.commit()
    con.close()
    before = p.read_bytes()
    assert tp.main(["--stored", "--db", str(p)]) == 0
    out = capsys.readouterr().out
    assert "2024-25: rows 2 · captured at or after the start 2 · starter False 1 · starter True 1" in out
    assert "pre-game knowledge: 1 row(s) captured before their game's start (of 3)" in out
    assert p.read_bytes() == before


def test_save_is_refused_under_data(tmp_path):
    with pytest.raises(SystemExit, match="never under data/"):
        tp.main(["--save", str(tmp_path / "data" / "x"), "--plan"])
