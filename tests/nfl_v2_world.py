"""A synthetic NFL stream for the nfl-elo-v2 harness tests (ARCHITECT 2026-11-02, addendum 215 item 3). Not a test
module: tests/test_nfl_v2_gate.py builds its throwaway databases with it. Nothing here reads data/ or a real DB: the
caller binds src.db.database to a SQLite file under pytest's tmp_path first (fresh()).

The stream: 32 NFL teams with fixed hidden strengths (random.Random(215)); per season (2024, 2025) 18 weeks of 16
'Regular Season' games, 13 'Post Season' games and 4 'Pre Season' games, outcomes drawn from the strengths; then the
rows every NFL path must leave out: a 2026 FINISHED game, a 2024 SCHEDULED row with both totals (not FINISHED: the
class #775 corrected), and an NCAA game in each season (Sport.NFL family, Competition.code NCAA)."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

SEASON_START = {"2024": datetime(2024, 9, 5, 17), "2025": datetime(2025, 9, 4, 17), "2026": datetime(2026, 9, 10, 17)}


def fresh(path, monkeypatch):
    """Bind src.db.database to a fresh SQLite file at `path` (tmp_path only) and create the tables."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return db


def _scores(rng, home_wins: bool) -> tuple[int, int]:
    w, lo = 17 + rng.randint(0, 20), rng.randint(0, 16)
    return (w, lo) if home_wins else (lo, w)


def season_games(season: str, seed: int = 215, weeks: int = 18, post: int = 13, pre: int = 4):
    """[(stage, kickoff, home index, away index, home score, away score)] for one season, deterministic."""
    rng = random.Random(f"{seed}-{season}")
    base = random.Random(seed)                       # the same hidden strengths every season
    strength = [base.gauss(0.0, 110.0) for _ in range(32)]
    t0 = SEASON_START[season]
    out = []
    for k in range(pre):
        h, a = (2 * k) % 32, (2 * k + 1) % 32
        out.append(("Pre Season", t0 - timedelta(days=21 - k), h, a, 38, 0))
    for wk in range(weeks):
        order = list(range(32))
        rng.shuffle(order)
        for g in range(16):
            h, a = order[2 * g], order[2 * g + 1]
            p = 1.0 / (1.0 + 10 ** (-(strength[h] + 40.0 - strength[a]) / 400.0))
            hs, as_ = _scores(rng, rng.random() < p)
            out.append(("Regular Season", t0 + timedelta(days=7 * wk, minutes=10 * g), h, a, hs, as_))
    tp = t0 + timedelta(days=7 * weeks + 7)
    for g in range(post):
        h, a = rng.sample(range(32), 2)
        p = 1.0 / (1.0 + 10 ** (-(strength[h] + 40.0 - strength[a]) / 400.0))
        hs, as_ = _scores(rng, rng.random() < p)
        out.append(("Post Season", tp + timedelta(days=g // 4 * 7, minutes=10 * g), h, a, hs, as_))
    return out


def build(db, seasons=("2024", "2025"), extras: bool = True) -> dict:
    """Store the synthetic stream in the bound DB. Returns {"teams": [ids], "ids": {season: [match ids walked]}}."""
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team

    out = {"teams": [], "ids": {}}
    with db.session_scope() as s:
        nfl = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
        ncaa = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        teams = [Team(sport=Sport.NFL, name=f"NFL-{i}") for i in range(32)]
        college = [Team(sport=Sport.NFL, name=f"NCAA-{i}") for i in range(2)]
        s.add_all([nfl, ncaa, *teams, *college])
        s.flush()
        out["teams"] = [t.id for t in teams]

        def add(comp, season, stage, at, h, a, hs, as_, status=MatchStatus.FINISHED):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, stage=stage, utc_date=at,
                      status=status, home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=as_)
            s.add(m)
            s.flush()
            return m.id

        for season in seasons:
            ids = []
            for stage, at, h, a, hs, as_ in season_games(season):
                mid = add(nfl, season, stage, at, teams[h], teams[a], hs, as_)
                if "pre" not in stage.lower():
                    ids.append(mid)
            out["ids"][season] = ids
            if extras:
                add(ncaa, season, "Regular Season", SEASON_START[season] + timedelta(hours=1), college[0],
                    college[1], 56, 0)
        if extras:
            add(nfl, "2026", "Regular Season", SEASON_START["2026"], teams[0], teams[1], 30, 3)
            add(nfl, "2024", "Regular Season", SEASON_START["2024"] + timedelta(days=3), teams[2], teams[3], 27, 24,
                status=MatchStatus.SCHEDULED)
    return out


def add_game(db, season: str, at: datetime, h: int, a: int, hs: int, as_: int, stage: str = "Regular Season",
             status=None) -> int:
    """One more NFL row (team indexes into the stored NFL teams, by id order)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with db.session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NFL")).scalar_one()
        teams = s.execute(select(Team).where(Team.name.like("NFL-%")).order_by(Team.id)).scalars().all()
        m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, stage=stage, utc_date=at,
                  status=status or MatchStatus.FINISHED, home_team_id=teams[h].id, away_team_id=teams[a].id,
                  home_score=hs, away_score=as_)
        s.add(m)
        s.flush()
        return m.id


def ll(p: float, y: int) -> float:
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))
