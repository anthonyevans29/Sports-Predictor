"""Addendum 157 item 2(a): the GSAx feasibility receipt (read-only, counts only) on a throwaway SQLite file."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("nhl_gsax_feasibility", ROOT / "scripts" / "nhl_gsax_feasibility.py")
gx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gx)

SHOTS = """CREATE TABLE nhl_shot_events (id INTEGER PRIMARY KEY, nhl_game_id INT, event_id INT, match_id INT,
    game_start TEXT, game_type INT, period INT, period_type TEXT, time_in_period_s INT, event_type TEXT, shot_type TEXT,
    side TEXT, owner_side TEXT, team_abbrev TEXT, shooter_id INT, goalie_id INT, x REAL, y REAL, zone_code TEXT,
    home_defending_side TEXT, situation_code TEXT, captured_at TEXT)"""
APPS = """CREATE TABLE nhl_goalie_appearances (id INTEGER PRIMARY KEY, nhl_game_id INT, match_id INT, game_start TEXT,
    game_type INT, side TEXT, team_abbrev TEXT, goalie_id INT, goalie_name TEXT, is_starter INT, shots_against INT,
    saves INT, goals_against INT, toi_seconds INT, decision TEXT, captured_at TEXT)"""

STARTER, RELIEF, HOME_G = 8470000, 8470001, 8470002


def _shot(con, gid, eid, start, et, side, goalie, x=70.0, y=5.0, sit="1551", period=1, ptype="REG", gtype=2):
    con.execute("INSERT INTO nhl_shot_events (nhl_game_id, event_id, game_start, game_type, period, period_type, "
                "event_type, side, owner_side, goalie_id, x, y, home_defending_side, situation_code) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (gid, eid, start, gtype, period, ptype, et, side, side, goalie, x, y, "left", sit))


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute(SHOTS)
    con.execute(APPS)
    # 2023-24: the fit's window. Home shoots at x=+89 (home defends left); goals close in, misses far out.
    for i in range(60):
        dist = 10 + i
        _shot(con, 2023020001 + i // 20, i, "2023-11-01 23:00:00", "goal" if i % 6 == 0 else "shot-on-goal",
              "home", STARTER, x=89 - dist, y=(i % 7) * 2.0)
    # 2024-25, one regular-season game: the away goalie (starter, then relief) faces the home shooters
    g, t = 2024020101, "2024-11-01 23:00:00"
    _shot(con, g, 1, t, "shot-on-goal", "home", STARTER)
    _shot(con, g, 2, t, "goal", "home", STARTER, x=80.0)
    _shot(con, g, 3, t, "missed-shot", "home", STARTER)
    _shot(con, g, 4, t, "blocked-shot", "home", None)                    # out by nature
    _shot(con, g, 5, t, "shot-on-goal", "home", RELIEF, period=3)         # the goalie on ice is the one named
    _shot(con, g, 6, t, "goal", "home", None, sit="0651", period=3)       # empty net: away goalie digit 0
    _shot(con, g, 7, t, "shot-on-goal", "home", None)                     # kept by the rules, no goalie named
    _shot(con, g, 8, t, "goal", "home", RELIEF, period=5, ptype="SO")     # shootout
    _shot(con, g, 9, t, "shot-on-goal", "away", HOME_G, x=-70.0)          # the home goalie, no appearance row
    for gid_, side, name, st, sa, ga in ((STARTER, "away", "A. Starter", 1, 2, 1),
                                         (RELIEF, "away", "B. Relief", 0, 2, 0)):
        con.execute("INSERT INTO nhl_goalie_appearances (nhl_game_id, game_start, game_type, side, goalie_id, "
                    "goalie_name, is_starter, shots_against, goals_against) VALUES (?,?,?,?,?,?,?,?,?)",
                    (g, t, 2, side, gid_, name, st, sa, ga))
    con.commit()
    con.close()
    return p


def test_season_is_the_game_ids_first_four_digits():
    assert gx.season_of(2023020001) == 2023 and gx.season_of("2025030411") == 2025
    assert gx.season_of(12345) is None and gx.season_of(None) is None and gx.label(2025) == "2025-26"


def test_the_event_set_counts_every_exclusion_and_joins_the_starters(db):
    con, form = gx.open_read(db)
    events, apps, why_apps = gx.load(con)
    assert why_apps is None
    con.close()
    model, why = gx.xg_model(events)
    assert model is not None and why is None and model.n_fit == 60
    t = gx.receipt(events, apps, model)["seasons"][2024][2]
    assert t["excluded"] == {"blocked": 1, "empty_net": 1, gx.NO_GOALIE: 1, "shootout": 1}
    assert t["n"] == 5 and t["goals"] == 1                         # starter 3 (1 goal), relief 1, home goalie 1
    assert t["join"] == {"the starter": 3, "a relief appearance": 1, "no appearance row": 1}
    assert t["relief_games"] == {2024020101}
    assert t["by_type"]["blocked-shot"] == {"events": 1, "no goalie_id": 1}
    pg = t["per_goalie"]
    assert pg[STARTER]["shots"] == 3 and pg[STARTER]["goals"] == 1 and len(pg[STARTER]["starts"]) == 1
    assert pg[RELIEF]["shots"] == 1 and not pg[RELIEF]["starts"] and pg[HOME_G]["name"] is None
    assert abs(t["xg"] - sum(g["xg"] for g in pg.values())) < 1e-9   # numerator and denominator on one event set
    # the boxscore cross-check: the starter's 2 SOG + goal and 1 goal agree; the relief's shootout goal is out (1 SOG)
    assert t["cross_tally"]["shots against: agree"] == 1 and t["cross_tally"]["shots against: differ"] == 1


def test_the_console_names_each_rule_and_never_writes(db, capsys):
    before = db.read_bytes()
    assert gx.main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "2024-25 regular season (type 2)" in out and "empty net: the defending goalie digit 0 (R5) 1" in out
    assert "THE EVENT SET: shots faced 5 · goals against 1" in out and "(numerator and denominator on these 5 events)" in out
    assert "2023-24's xG is in-sample" in out and "2025-26: no stored event" in out
    assert f"  {STARTER} · A. Starter · 1 · 1 · 3 ·" in out
    assert db.read_bytes() == before


def test_no_database_is_never_created(tmp_path):
    with pytest.raises(SystemExit, match="never creates one"):
        gx.main(["--db", str(tmp_path / "absent.db")])
    assert not (tmp_path / "absent.db").exists()


def _receipt_2024(db):
    con, _ = gx.open_read(db)
    events, apps, why = gx.load(con)
    con.close()
    return gx.receipt(events, apps, gx.xg_model(events)[0])["seasons"][2024][2], why


def test_a_shooting_side_row_establishes_no_role_and_a_zero_sog_goalie_game_is_cross_checked(db):
    con = sqlite3.connect(db)
    g, t = 2024020102, "2024-11-02 23:00:00"
    _shot(con, g, 1, t, "shot-on-goal", "home", STARTER)          # STARTER's row below sits on the shooting side
    _shot(con, g, 2, t, "missed-shot", "home", RELIEF)            # RELIEF: eligible misses only, zero SOG
    for gid_, side, name, st, sa, ga in ((STARTER, "home", "A. Starter", 1, 1, 0), (RELIEF, "away", None, 1, 3, 0)):
        con.execute("INSERT INTO nhl_goalie_appearances (nhl_game_id, game_start, game_type, side, goalie_id, "
                    "goalie_name, is_starter, shots_against, goals_against) VALUES (?,?,?,?,?,?,?,?,?)",
                    (g, t, 2, side, gid_, name, st, sa, ga))
    con.commit()
    con.close()
    t2, _ = _receipt_2024(db)
    assert t2["join"]["appearance side is not the defending side"] == 1
    assert sum(t2["join"].values()) == t2["n"]                     # exclusive: the categories sum to the event set
    assert g not in t2["per_goalie"][STARTER]["starts"]            # a mismatched row adds no start
    # RELIEF's zero-SOG game compares as 0 against the boxscore's 3: a differ the old tally never saw
    assert t2["cross_tally"]["shots against: differ"] == 2


def test_a_joined_row_without_a_name_is_not_a_missing_row(db, capsys):
    con = sqlite3.connect(db)
    con.execute("UPDATE nhl_goalie_appearances SET goalie_name = NULL WHERE goalie_id = ?", (RELIEF,))
    con.commit()
    con.close()
    assert gx.main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert f"  {RELIEF} · (name not stored) ·" in out and f"  {HOME_G} · (no appearance row) ·" in out


def test_an_unreadable_starter_table_is_never_read_as_no_rows(db, capsys):
    con = sqlite3.connect(db)
    con.execute("DROP TABLE nhl_goalie_appearances")
    con.commit()
    con.close()
    t2, why = _receipt_2024(db)
    assert why and "nhl_goalie_appearances could not be read" in why
    assert t2["join"] == {"starter table unreadable": 5} and "no appearance row" not in t2["cross_tally"]
    assert gx.main(["--db", str(db)]) == 0
    assert "STARTERS: UNAVAILABLE (nhl_goalie_appearances could not be read" in capsys.readouterr().out
