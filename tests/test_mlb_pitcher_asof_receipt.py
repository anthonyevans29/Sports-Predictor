"""MLB AS-OF PITCHER RECEIPT (lane mlb-pitchers, #507; roadmap step due 2026-10-28): read-only, counts only, on a
throwaway SQLite file built from the app's own schema (never the configured DB, never data/)."""
import hashlib
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
from src.db.schema import (Base, Competition, Match, MatchParticipant, MatchStatus, PitcherAppearance,
                           PitcherSeasonStats, Sport, Team)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mlb_pitcher_asof_receipt",
                                              ROOT / "scripts" / "mlb_pitcher_asof_receipt.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

SRC = MLBStatsAPIAdapter.source_name
T0 = datetime(2025, 4, 1, 23, 0)


def build(path: Path):
    """2025, teams H (statsapi 147) and A (111):
    g0 04-01: H starter p1 18 outs ER 2, H relief r1 9 outs ER 1, A starter p2 15 outs ER NULL.
    g1 04-02: H starter p1 18 outs ER 2 (participants: p1, agrees); A starter p3 (participants: p9, differs).
    g2, g3 04-03 at one kickoff (a doubleheader read together): A starter p2 in g2; g3 has no appearances.
    g4 04-04: A starter p2 again (its prior g0 row has ER NULL); H relief r9 with a team id matching neither team.
    A postseason game, a game with no stage, a scheduled game; pitcher_season_stats rows for p1 and p2."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        h = Team(sport=Sport.MLB, name="Hawks", external_ids={SRC: "147"})
        a = Team(sport=Sport.MLB, name="Owls", external_ids={SRC: "111"})
        s.add_all([comp, h, a])
        s.flush()

        def game(i, at, stage="R", status=MatchStatus.FINISHED):
            m = Match(sport=Sport.MLB, competition_id=comp.id, season="2025", utc_date=at, status=status, stage=stage,
                      home_team_id=h.id, away_team_id=a.id, external_ids={SRC: str(5000 + i)})
            s.add(m)
            s.flush()
            return m
        g = [game(0, T0), game(1, T0 + timedelta(days=1)), game(2, T0 + timedelta(days=2)),
             game(3, T0 + timedelta(days=2)), game(4, T0 + timedelta(days=3))]
        game(5, T0 + timedelta(days=200), stage="F")
        game(6, T0 + timedelta(days=4), stage=None)
        game(7, T0 + timedelta(days=300), status=MatchStatus.SCHEDULED)

        def app(m, team, pid, outs, starter, er, by_pk=False):
            s.add(PitcherAppearance(match_id=None if by_pk else m.id, source_game_id=m.external_ids[SRC],
                                    game_date=m.utc_date, team_source_id=team, pitcher_id=pid, outs=outs,
                                    is_starter=starter, earned_runs=er))
        app(g[0], "147", "p1", 18, True, 2)
        app(g[0], "147", "r1", 9, False, 1)
        app(g[0], "111", "p2", 15, True, None)
        app(g[1], "147", "p1", 18, True, 2, by_pk=True)        # joined by the statsapi id in source_game_id
        app(g[1], "111", "p3", 12, True, 3)
        app(g[2], "111", "p2", 15, True, 1)
        app(g[4], "111", "p2", 18, True, 0)
        app(g[4], "999", "r9", 3, False, 0)                    # a team id matching neither team: left out
        for side, team, pid in (("home", h, "p1"), ("away", a, "p9")):
            s.add(MatchParticipant(match_id=g[1].id, team_id=team.id, role="starting_pitcher", kind="confirmed",
                                   player_name=pid, player_source_id=pid))
        s.add(PitcherSeasonStats(player_source_id="p1", player_name="p1", season="2025", innings_pitched=12.0,
                                 earned_runs=4, era=3.0))
        s.add(PitcherSeasonStats(player_source_id="p2", player_name="p2", season="2025", innings_pitched=17.0,
                                 earned_runs=1, era=0.5))
        s.commit()
    eng.dispose()


def run(tmp_path, capsys, *args):
    p = tmp_path / "copy.db"
    if not p.exists():
        build(p)
    assert rc.main(["--db", str(p), *args]) == 0
    return capsys.readouterr().out


def test_the_as_of_reconstruction_reads_only_games_that_started_before(tmp_path, capsys):
    out = run(tmp_path, capsys, "--seasons", "2025")
    assert "mode=ro URI" in out and "pitcher_appearances(match_id, source_game_id" in out
    assert ("G games: finished postseason 1 · finished regular 5 · finished stage unknown 1 · status FINISHED 7 · "
            "status SCHEDULED 1 · regular without a kickoff 0 · regular games read 5") in out
    assert ("A appearances: both sides 2 · one side 2 · none 1 · rows 7 (earned_runs NULL 1) · left out: no side "
            "(team_source_id matches neither team) 1") in out
    # g0: both sides have no prior (no stats); g1 home the model's p1 (prior g0, GS 1, ER complete), away the model's
    # p9 (no prior; the boxscore says p3: differ); g2 away p2 (prior g0, whose ER is NULL: incomplete); g3 shares g2's
    # kickoff, holds no appearances and sees nothing of g2; g4 away p2 (g0's NULL stays: incomplete)
    assert ("as of the game: boxscore's starter: no prior appearance this season (no stats) 2 · boxscore's starter: "
            "starter component, ERA incomplete (earned_runs NULL on a prior row) 2 · model's starter: no prior "
            "appearance this season (no stats) 1 · model's starter: starter component, ERA complete 1 · no starter to "
            "read 4") in out
    assert "the model's against the boxscore's: agree 1 · boxscore only 4 · differ 1 · neither 4" in out
    assert ("B bullpen, per side (10): recent 10 days: < 10 IP 10 · season: ERA complete 4 · season: no prior relief "
            "IP 6") in out
    # p1: 36 outs = 12.0 IP, ER 4 = 4; p2: 48 outs against 17.0 IP (51), a NULL ER row
    assert "C cross-check, pitcher_season_stats 2025 rows 2: ER NULL on a row 1 · ER agree 1 · IP agree 1 · IP differ 1" \
        in out
    assert ("SUMMARY 2025: regular games 5 · appearances both sides 2/5 · a starter component as of the game (ERA "
            "complete) 1/10 · bullpen season ERA complete 4/10 · bullpen recent >= 10 IP 0/10") in out


def test_it_writes_nothing_and_refuses_a_missing_db(tmp_path, capsys):
    p = tmp_path / "copy.db"
    build(p)
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    assert rc.main(["--db", str(p)]) == 0
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before
    try:
        rc.main(["--db", str(tmp_path / "absent.db")])
    except SystemExit as e:
        assert "never creates one" in str(e)
    assert not (tmp_path / "absent.db").exists()


def test_a_missing_column_refuses_law_1(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    build(p)
    con = sqlite3.connect(p)
    con.execute("ALTER TABLE pitcher_appearances DROP COLUMN earned_runs")
    con.commit()
    con.close()
    try:
        rc.main(["--db", str(p)])
        raise AssertionError("not refused")
    except SystemExit as e:
        assert "pitcher_appearances.earned_runs" in str(e)
