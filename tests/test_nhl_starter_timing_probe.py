"""Addendum 157 items 2(b) and 7: the NHL starter timing probe, on fake API answers and a fake clock (no network).
Item 7: the probe reports the distribution (per poll, unique / conflicting / missing identities; usable at the T-35
cutoff; missing, conflicting, withdrawn, changed before puck drop), and the eventual starter only checks reliability."""
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


def _box(home_flag, away_flag):
    gl = lambda flagged, ids: [{"playerId": i, "starter": i == flagged} for i in ids]
    return {"gameState": "FUT", "playerByGameStats": {"homeTeam": {"goalies": gl(home_flag, (1, 2))},
                                                      "awayTeam": {"goalies": gl(away_flag, (3, 4))}}}


class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=max(s, 1))


def _fetch(clock):
    """right-rail names probable starters (home 1, away 3) from T-60; the boxscore flags them from T-15; after puck
    drop the boxscore's flags are the eventual starters (home 1, away 4: the away starter changed); landing lists
    season leaders (named, never asserted)."""
    def f(url):
        if "/schedule/" in url:
            return 200, _schedule()
        t = clock.t
        if url.endswith("/boxscore"):
            if t >= START:
                return 200, _box(1, 4)
            return 200, _box(1, 3) if t >= START - timedelta(minutes=15) else _box(None, None)
        if url.endswith("/right-rail"):
            if t < START - timedelta(minutes=60):
                return 404, None
            return 200, {"gameState": "FUT", "probableStarters": {"homeTeam": {"goalie": {"playerId": 1}},
                                                                 "awayTeam": {"goalie": {"playerId": 3}}}}
        return 200, {"gameState": "FUT", "matchup": {"goalieComparison": {
            "homeTeam": {"leaders": [{"playerId": 1}, {"playerId": 2}]},
            "awayTeam": {"leaders": [{"playerId": 3}, {"playerId": 4}]}}}}
    return f


def test_the_day_is_the_nhl_day_types_2_3_and_the_polls_include_the_cutoff_and_the_eventual_read():
    gs = tp.day_games(_schedule(), DAY)
    assert [g["id"] for g in gs] == [GAME]
    assert [tp.label(o) for _, _, o in tp.plan(gs)] == ["T-120", "T-90", "T-60", "T-45", "T-35", "T-30", "T-15",
                                                        "T-0 (puck drop)", "T+20 (eventual starter)"]


def test_what_each_endpoint_asserted():
    s = tp.asserted(_box(1, 3))
    assert s["home"] == {"kind": "flag", "ids": [1], "listed": 2, "keys": {"flag starter=True"}}
    assert tp.asserted(_box(None, None))["away"]["kind"] == "listed"
    rr = tp.asserted({"probableStarters": {"homeTeam": {"goalie": {"playerId": 1}}}})
    assert rr["home"]["kind"] == "path" and rr["home"]["ids"] == [1] and rr["away"]["kind"] == "none"
    leaders = tp.asserted({"goalieComparison": {"homeTeam": {"leaders": [{"playerId": 1}]}}})
    assert leaders["home"]["kind"] == "listed" and leaders["home"]["ids"] == []   # named, never asserted


def test_the_distribution_the_cutoff_and_reliability(capsys):
    clock = Clock(START - timedelta(minutes=125))
    assert tp.run(DAY, _fetch(clock), clock.now, clock.sleep) == 0
    out = capsys.readouterr().out
    assert f"  {GAME} T-90 · boxscore HTTP 200 21:30:00Z · landing HTTP 200 21:30:00Z · right-rail HTTP 404 21:30:00Z" in out
    assert "· both unique no · away missing (boxscore listed, landing listed)" in out
    assert (f"  {GAME} T-35 · boxscore HTTP 200 22:25:00Z · landing HTTP 200 22:25:00Z · right-rail HTTP 200 "
            "22:25:00Z · gameState FUT · both unique yes · away unique [3] (boxscore listed, landing listed, "
            "right-rail path)") in out
    assert f"  {GAME} T+20 (eventual starter) · reliability only: away [4] · home [1]" in out
    assert ("away first seen T-60 by right-rail [3] · home first seen T-60 by right-rail [1] · at the cutoff (T-35): "
            "USABLE · before puck drop: away missing 2 · home missing 2 · reliability: away differs, home agrees") in out
    assert "  usable at the cutoff (T-35): 1 of 1 games (100%)" in out
    assert "right-rail T-60 2" in out and "  before puck drop, side-polls: missing 4 · conflicting 0 · withdrawn 0 · changed 0" in out
    assert "reliability (the identity at the cutoff against the eventual starter; never fills a gap), sides: agrees 1 · differs 1" in out
    assert "requests: schedule 1 · boxscore HTTP 200 9 · landing HTTP 200 8 · right-rail HTTP 200 6 · right-rail HTTP 404 2" in out


def _ident(home, away):
    return {"home": {"ids": home, "by": {"boxscore": "flag" if home else "listed"}},
            "away": {"ids": away, "by": {"boxscore": "flag" if away else "listed"}}}


def test_conflicting_withdrawn_and_changed_are_counted_before_puck_drop_and_the_eventual_never_fills_a_gap():
    polls = {120: _ident([], []), 90: _ident([1], [3]), 60: _ident([1, 2], [3]), 45: _ident([], [4]),
             35: None, 30: _ident([2], [4]), 15: _ident([2], [3]), 0: _ident([9], [9])}
    s = tp.game_summary({"id": 1}, polls, eventual=_ident([2], [3]))
    assert s["counts"]["home"] == {"missing": 2, "conflicting": 1, "withdrawn": 1, "changed": 1}   # 1 -> 2 at T-30
    assert s["counts"]["away"] == {"missing": 1, "changed": 2}                        # 3 -> 4 at T-45, 4 -> 3 at T-15
    assert s["cutoff_label"] == "T-45" and s["cutoff"] == {"away": [4], "home": []}   # T-35 unanswered: T-45 stands
    assert not s["usable"] and s["reliability"] == {"away": "differs", "home": "no identity at the cutoff"}
    assert s["first"]["home"] == (90, ["boxscore"], [1])                              # the puck-drop poll is not counted


def test_a_late_start_misses_polls_and_never_counts_them(capsys):
    clock = Clock(START - timedelta(minutes=40))     # T-120..T-60 more than 5 minutes late; T-45 at 5 minutes is polled
    tp.run(DAY, _fetch(clock), clock.now, clock.sleep)
    out = capsys.readouterr().out
    assert out.count("· MISSED (") == 3 and f"  {GAME} T-45 · boxscore HTTP 200" in out


def test_plan_polls_nothing(capsys):
    calls = []
    f = _fetch(Clock(START))
    tp.run(DAY, lambda u: (calls.append(u), f(u))[1], lambda: START, lambda s: None, plan_only=True)
    out = capsys.readouterr().out
    assert len(calls) == 1 and "plan 21:00Z" in out and "plan 23:20Z · 2026020150 T+20 (eventual starter) · boxscore" in out


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
