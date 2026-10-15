"""MLB PITCHER COVERAGE PROBE (ARCHITECT 2026-10-14, addendum 67 item 2; #507): read-only, on a throwaway SQLite file
built from the app's own schema (never the configured DB, never data/) and a stubbed statsapi (no network)."""
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
from src.db.schema import (Base, Competition, Match, MatchParticipant, MatchStatus, PitcherAppearance, Sport,
                           Team)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mlb_pitcher_probe", ROOT / "scripts" / "mlb_pitcher_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

SRC = MLBStatsAPIAdapter.source_name


def build(path: Path, future_pk="999001"):
    """2025: 12 finished games (pk 1000..1011): 0-4 starters both sides, 5-6 one side (6 by source_game_id only),
    7-11 none; 2 participants rows on game 0. One finished 2024 game with no statsapi id. A future game."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        h, a = Team(sport=Sport.MLB, name="Home Hawks"), Team(sport=Sport.MLB, name="Away Owls")
        s.add_all([comp, h, a])
        s.flush()
        t0 = datetime(2025, 4, 1, 23, 0)
        games = []
        for i in range(12):
            m = Match(sport=Sport.MLB, competition_id=comp.id, season="2025", utc_date=t0 + timedelta(days=i),
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id,
                      external_ids={SRC: str(1000 + i)})
            s.add(m)
            games.append(m)
        s.add(Match(sport=Sport.MLB, competition_id=comp.id, season="2024", utc_date=datetime(2024, 5, 1, 23),
                    status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, external_ids={}))
        s.add(Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=datetime(2099, 1, 1, 23),
                    status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                    external_ids={SRC: future_pk}))
        s.flush()
        for i, m in enumerate(games):
            if i <= 4:
                for team in ("147", "111"):
                    s.add(PitcherAppearance(match_id=m.id, source_game_id=str(1000 + i), game_date=m.utc_date,
                                            team_source_id=team, pitcher_id=f"{i}{team}", is_starter=True))
                s.add(PitcherAppearance(match_id=m.id, source_game_id=str(1000 + i), game_date=m.utc_date,
                                        team_source_id="147", pitcher_id=f"r{i}", is_starter=False))
            elif i == 5:
                s.add(PitcherAppearance(match_id=m.id, source_game_id="1005", game_date=m.utc_date,
                                        team_source_id="147", pitcher_id="s5", is_starter=True))
            elif i == 6:                           # match_id null: found by the statsapi id in source_game_id
                s.add(PitcherAppearance(match_id=None, source_game_id="1006", game_date=m.utc_date,
                                        team_source_id="111", pitcher_id="s6", is_starter=True))
        for team in (h, a):
            s.add(MatchParticipant(match_id=games[0].id, team_id=team.id, role="starting_pitcher",
                                   kind="confirmed", player_name="X"))
        s.commit()
    eng.dispose()


def schedule(pk, home="Ann Arbor", away="Bo Bell", extra=None, pp_extra=None):
    teams = {}
    for side, name in (("home", home), ("away", away)):
        teams[side] = {"team": {"id": 1}, **({"probablePitcher": {"id": 7, "fullName": name, "link": "/p/7",
                                                                  **(pp_extra or {})}} if name else {})}
    return {"dates": [{"date": "2025-04-01", "games": [{"gamePk": int(pk), "gameDate": "2025-04-01T23:05:00Z",
                                                        "teams": teams, **(extra or {})}]}]}


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "copy.db"
    build(p)
    return p


def run(capsys, *argv):
    assert probe.main(list(argv)) == 0
    return capsys.readouterr().out


def test_the_database_part_enumerates_the_tables_and_counts_both_one_and_neither(db, capsys):
    out = run(capsys, "--db", str(db), "--no-network")
    assert "opened via mode=ro URI" in out
    assert "  table pitcher_appearances: id, match_id, source_game_id, game_date, team_source_id, pitcher_id" in out
    assert "  table match_participants: " in out
    assert "  READ: pitcher_appearances (match_id, source_game_id, team_source_id, is_starter = 1)" in out
    assert "  pitcher_appearances: starters for both sides 5/12 · one side only 2 · neither 5" in out
    assert "match_participants (second read): kind 'confirmed': both sides 1, one side 0" in out
    assert "  2025: starters recorded 5/12 · probables available on the sample not asked/10" in out
    assert "  2024: starters recorded 0/1" in out


def test_the_sample_is_ten_evenly_spaced_and_counts_both_named(db, capsys, monkeypatch):
    asked = []

    def fake(self, path, params=None):
        asked.append(params["gamePk"])
        pk = params["gamePk"]
        if pk == "1004":
            return schedule(pk, away=None)                 # one side not named
        if pk == "999001":
            return schedule(pk)
        return schedule(pk)
    monkeypatch.setattr(MLBStatsAPIAdapter, "_get", fake)
    monkeypatch.setattr(MLBStatsAPIAdapter, "_throttle", lambda self: None)
    out = run(capsys, "--db", str(db), "--seasons", "2025")
    sampled = [pk for pk in asked if pk != "999001"]
    assert sampled == ["1000", "1001", "1002", "1004", "1005", "1006", "1007", "1009", "1010", "1011"]
    assert "P1 season 2025: 10 finished game(s) sampled of 12 carrying a statsapi id (of 12 finished)" in out
    assert "away not named" in out and "probablePitcher keys ['fullName', 'id', 'link']" in out
    assert "  2025: starters recorded 5/12 · probables available on the sample 9/10" in out
    assert "keys read: dates[].games[].gamePk · games[].teams.{home,away}.probablePitcher.{id,fullName}" in out


def test_the_next_unplayed_game_says_when_the_payload_does_not(db, capsys, monkeypatch):
    monkeypatch.setattr(MLBStatsAPIAdapter, "_get", lambda self, path, params=None: schedule(params["gamePk"]))
    monkeypatch.setattr(MLBStatsAPIAdapter, "_throttle", lambda self: None)
    out = run(capsys, "--db", str(db), "--seasons", "2025", "--sample", "2")
    assert "P2 the next unplayed game: match " in out and "gamePk 999001" in out
    assert "  home: named 'Ann Arbor' · probablePitcher keys ['fullName', 'id', 'link']" in out
    assert "  keys speaking of a time or a date: game.gameDate='2025-04-01T23:05:00Z'" in out
    assert "  the hour the probables appeared: THE PAYLOAD DOES NOT SAY" in out


def test_a_time_key_on_a_probable_is_printed(db, capsys, monkeypatch):
    monkeypatch.setattr(MLBStatsAPIAdapter, "_get", lambda self, path, params=None: schedule(
        params["gamePk"], pp_extra={"lastUpdated": "2099-01-01T12:00:00Z"}))
    monkeypatch.setattr(MLBStatsAPIAdapter, "_throttle", lambda self: None)
    out = run(capsys, "--db", str(db), "--seasons", "2025", "--sample", "1")
    assert "  the hour the probables appeared: probablePitcher.home.lastUpdated='2099-01-01T12:00:00Z'; " \
           "probablePitcher.away.lastUpdated='2099-01-01T12:00:00Z'" in out


def test_a_failed_call_is_printed_and_the_probe_goes_on(db, capsys, monkeypatch):
    def fake(self, path, params=None):
        if params["gamePk"] == "1000":
            raise RuntimeError("boom")
        return schedule(params["gamePk"])
    monkeypatch.setattr(MLBStatsAPIAdapter, "_get", fake)
    monkeypatch.setattr(MLBStatsAPIAdapter, "_throttle", lambda self: None)
    out = run(capsys, "--db", str(db), "--seasons", "2025")
    assert "gamePk 1000 2025-04-01 23:00:00.000000: ✗ RuntimeError: boom" in out
    assert "probables available on the sample 9/10" in out and "· failed 1" in out


def test_it_writes_nothing_and_never_creates_a_database(db, tmp_path, capsys):
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    files = sorted(p.name for p in tmp_path.iterdir())
    run(capsys, "--db", str(db), "--no-network")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == files
    missing = tmp_path / "nope.db"
    with pytest.raises(SystemExit, match="no database at"):
        probe.main(["--db", str(missing), "--no-network"])
    assert not missing.exists()


def test_codex_on_522_p2_takes_the_next_scheduled_game_and_skips_malformed_ids(db, capsys, monkeypatch):
    """P2 reads only a SCHEDULED game: an earlier CANCELLED, POSTPONED or STALE_ORPHAN row (a retired provider id,
    never a fixture) is passed over; a row whose external_ids is not a JSON object is one game with no id, never the
    end of the probe."""
    import sqlite3
    con = sqlite3.connect(db)
    comp, home, away = con.execute("SELECT competition_id, home_team_id, away_team_id FROM matches LIMIT 1").fetchone()
    for i, (status, ext) in enumerate([("CANCELLED", json.dumps({SRC: "999101"})),
                                       ("STALE_ORPHAN", json.dumps({SRC: "999102"})),
                                       ("POSTPONED", json.dumps({SRC: "999103"})),
                                       ("SCHEDULED", "not json"), ("SCHEDULED", "[1]")]):
        con.execute("INSERT INTO matches (sport, competition_id, season, utc_date, status, home_team_id, "
                    "away_team_id, external_ids) VALUES ('MLB', ?, '2026', ?, ?, ?, ?, ?)",
                    (comp, f"2098-0{i + 1}-01 23:00:00.000000", status, home, away, ext))
    con.commit()
    con.close()
    asked = []

    def fake(self, path, params=None):
        asked.append(params["gamePk"])
        return schedule(params["gamePk"])
    monkeypatch.setattr(MLBStatsAPIAdapter, "_get", fake)
    monkeypatch.setattr(MLBStatsAPIAdapter, "_throttle", lambda self: None)
    out = run(capsys, "--db", str(db), "--seasons", "2025", "--sample", "1")
    assert asked[-1] == "999001" and not {"999101", "999102", "999103"} & set(asked)
    assert "P2 the next unplayed game: match " in out and "gamePk 999001" in out and "(stored status SCHEDULED)" in out


def test_codex_on_522_a_starter_with_no_team_id_names_no_side(tmp_path, capsys):
    """A starter row with a null or empty team_source_id names no side: a game whose only starters have none is
    counted under neither, and one with a single identified side under one side."""
    import sqlite3
    p = tmp_path / "nulls.db"
    build(p)
    con = sqlite3.connect(p)
    m7, m8 = [r[0] for r in con.execute("SELECT id FROM matches WHERE season='2025' ORDER BY utc_date LIMIT 2 OFFSET 7")]
    con.execute("INSERT INTO pitcher_appearances (match_id, source_game_id, game_date, team_source_id, pitcher_id, "
                "is_starter, captured_at) VALUES (?, '1007', '2025-04-08', NULL, 'n7', 1, '2025-04-09')", (m7,))
    con.execute("INSERT INTO pitcher_appearances (match_id, source_game_id, game_date, team_source_id, pitcher_id, "
                "is_starter, captured_at) VALUES (?, '1008', '2025-04-09', '', 'e8', 1, '2025-04-10')", (m8,))
    con.execute("INSERT INTO pitcher_appearances (match_id, source_game_id, game_date, team_source_id, pitcher_id, "
                "is_starter, captured_at) VALUES (?, '1008', '2025-04-09', '147', 's8', 1, '2025-04-10')", (m8,))
    con.commit()
    con.close()
    out = run(capsys, "--db", str(p), "--no-network")
    # base fixture: 5 both · 2 one · 5 neither; game 7 (null team only) stays neither, game 8 gains one side
    assert "  pitcher_appearances: starters for both sides 5/12 · one side only 3 · neither 4" in out


def test_the_games_with_neither_starter_carry_their_range_months_provenance_and_the_backfill_sentence(db, capsys):
    """Addendum 74 item 2 (#507): per season, the games with neither starter: their date range, count by month, which
    sync wrote them (matches.external_ids keys), and, from the code, whether a re-run of sync-appearances fills them."""
    import sqlite3
    con = sqlite3.connect(db)                        # the test's own throwaway copy: game 11 gets a reliever row only
    mid = con.execute("SELECT id FROM matches WHERE json_extract(external_ids, '$.mlb_stats_api') = '1011'").fetchone()[0]
    con.execute("INSERT INTO pitcher_appearances (match_id, source_game_id, game_date, team_source_id, pitcher_id, "
                "is_starter, captured_at) VALUES (?, '1011', '2025-04-12 23:00:00', '147', 'r11', 0, "
                "'2025-04-13 00:00:00')", (mid,))
    con.commit()
    con.close()
    out = run(capsys, "--db", str(db), "--no-network")
    assert "  pitcher_appearances: starters for both sides 5/12 · one side only 2 · neither 5" in out
    assert "  neither starter, season 2025: 5 game(s) · 2025-04-08..2025-04-12 (stored kickoff, UTC)" in out
    assert "    by month: 2025-04 5" in out
    assert ("    provenance read: matches.external_ids keys (mlb_stats_api = statsapi's sync-matches; api_baseball = "
            "the api-sports fallback, mlb_apisports.sync_matches): mlb_stats_api 5") in out
    assert ("    as sync-appearances reads them: no pitcher_appearances row for its statsapi id 4 · rows for its id but "
            "no starter 1 · no statsapi id 0") in out
    assert "so a re-run fills the 4 game(s) with no row where the boxscore answers; the 1 game(s) holding rows but " \
           "no starter are skipped unless --refresh" in out
    # 2024: its one finished game carries no statsapi id: no command fills it
    assert "  neither starter, season 2024: 1 game(s) · 2024-05-01..2024-05-01 (stored kickoff, UTC)" in out
    assert "the api-sports fallback, mlb_apisports.sync_matches): (no key) 1" in out
    assert "no pitcher_appearances row for its statsapi id 0 · rows for its id but no starter 0 · no statsapi id 1" in out
    assert "and the 1 game(s) with no statsapi id are skipped either way, so for them a command is missing." in out
