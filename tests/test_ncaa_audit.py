"""#79 NCAA DATA AUDIT (architect 2026-09-30): stage/month tables, the
repeated-pairing detector, the established split, the prior-season heuristic,
suspects, and that the command writes nothing."""
from datetime import datetime, timedelta

import pytest

from src.walters import ncaa_audit as na


def A(mid, h, a, season, when, hs, as_, stage="Regular Season"):
    return na.AuditGame(mid, season, when, h, a, hs, as_, stage)


# --- stage / month tables ------------------------------------------------------------

def test_stage_table_is_verbatim_and_counts_ties_margins():
    d = datetime(2025, 9, 6)
    gs = [A(1, 1, 2, "2025", d, 30, 10),
          A(2, 3, 4, "2025", d, 10, 20),
          A(3, 5, 6, "2025", d, 17, 17),
          A(4, 1, 2, "2025", d, 21, 14, stage="Post Season"),
          A(5, 1, 2, "2025", d, 3, 0, stage="")]
    rows = {r.key: r for r in na.by_stage(gs)}
    assert set(rows) == {"Regular Season", "Post Season", "<empty>"}
    reg = rows["Regular Season"]
    assert (reg.n, reg.home_wins, reg.ties) == (3, 1, 1)
    assert reg.home_rate == pytest.approx(0.5)          # 1 of 2 decided
    assert reg.mean_margin == pytest.approx((20 - 10 + 0) / 3)
    assert rows["Post Season"].home_rate == 1.0


def test_month_table_uses_utc_year_month():
    gs = [A(1, 1, 2, "2025", datetime(2025, 8, 31, 23), 1, 0),
          A(2, 1, 2, "2025", datetime(2025, 9, 1, 1), 0, 1),
          A(3, 1, 2, "2025", datetime(2025, 9, 20), 0, 1)]
    rows = {r.key: r for r in na.by_month(gs)}
    assert list(rows) == ["2025-08", "2025-09"]
    assert (rows["2025-08"].n, rows["2025-08"].home_rate) == (1, 1.0)
    assert (rows["2025-09"].n, rows["2025-09"].home_wins) == (2, 0)


def test_all_ties_row_has_no_rate():
    r = na.total([A(1, 1, 2, "2025", datetime(2025, 9, 1), 7, 7)])
    assert r.home_rate is None and r.mean_margin == 0


# --- repeated pairings ----------------------------------------------------------------

def test_reversed_and_same_host_pairings():
    d = datetime(2025, 9, 1)
    gs = [A(1, 1, 2, "2025", d, 1, 0),
          A(2, 2, 1, "2025", d + timedelta(days=60), 1, 0),       # reversed: 1<->2
          A(3, 3, 4, "2025", d, 1, 0),
          A(4, 3, 4, "2025", d + timedelta(days=90), 1, 0),       # same host twice
          A(5, 5, 6, "2025", d, 1, 0)]                              # single meeting
    rev, same = na.pairings(gs)
    assert [(p.a, p.b) for p in rev] == [(1, 2)]
    assert len(rev[0].a_hosts) == 1 and len(rev[0].b_hosts) == 1
    assert [(p.a, p.b) for p in same] == [(3, 4)]


# --- heuristics -----------------------------------------------------------------------

def test_established_split_threshold_is_per_season_game_count():
    d = datetime(2025, 9, 1)
    gs = []
    # teams 1 and 2: 8 games each (established); team 9: 1 game (not)
    for i in range(8):
        gs.append(A(i, 1, 2, "2025", d + timedelta(days=i), 1, 0))
    gs.append(A(100, 9, 1, "2025", d, 0, 1))   # non-established home, established away
    both, h_only, a_only, neither = na.established_split(gs)
    # team 1 now has 9 games, team 2 has 8, team 9 has 1
    assert (both.n, both.home_wins) == (8, 8)
    assert (a_only.n, a_only.home_wins) == (1, 0)
    assert h_only.n == 0 and neither.n == 0
    assert na.ESTABLISHED_MIN_GAMES == 8
    # variant: counts supplied from another season (the in-progress case)
    from collections import Counter
    b2, h2, a2, n2 = na.established_split(gs, counts=Counter({9: 10, 1: 10}))
    assert (b2.n, a2.n, n2.n, h2.n) == (1, 0, 0, 8)   # team 2 has no count -> not established


def test_prior_season_check_counts_home_fewer():
    d = datetime(2024, 9, 1)
    prior = [A(i, 1, 2, "2024", d, 1, 0) for i in range(5)] + [A(9, 3, 1, "2024", d, 1, 0)]
    cur = [A(20, 3, 1, "2025", d, 1, 0),   # home 3 (1 prior) < away 1 (6)
           A(21, 1, 3, "2025", d, 1, 0),   # home more
           A(22, 7, 8, "2025", d, 1, 0)]   # neither present
    pc = na.prior_season_check(cur, prior, "2024")
    assert (pc.comparable, pc.home_fewer, pc.home_more, pc.neither) == (2, 1, 1, 1)


def test_suspects_and_home_heavy_teams():
    rows = [na.Row("a", n=60, home_wins=30), na.Row("b", n=49, home_wins=0),
            na.Row("c", n=60, home_wins=40)]
    assert [r.key for r in na.suspects(rows)] == ["a"]    # 0.50 < 0.52, n >= 50
    d = datetime(2025, 9, 1)
    gs = [A(1, 5, 6, "2025", d, 1, 0), A(2, 5, 7, "2025", d, 1, 0), A(3, 6, 5, "2025", d, 1, 0)]
    assert na.home_heavy_teams(gs, 2) == [(5, 2, 3), (6, 1, 2)]
    assert na.home_heavy_teams(gs, 5)[-1] == (7, 0, 1)


def test_gate_exclusion_reasons_match_the_gate():
    d = datetime(2025, 9, 1)
    assert A(1, 1, 2, "2025", d, 1, 0, "Pre Season").gate_exclusion() == "preseason"
    assert A(1, 1, 2, "2025", d, 1, 0, "Post Season").gate_exclusion() == "postseason"
    assert A(1, 1, 2, "2025", d, 3, 3).gate_exclusion().startswith("tied")
    assert A(1, 1, 2, "2025", d, 3, 0).gate_exclusion() is None


# --- DB + CLI: read-only ---------------------------------------------------------------

def _seed():
    from sqlalchemy import select

    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team

    init_db()
    with session_scope() as s:
        def comp(code, name):
            c = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                    Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.NFL, code=code, name=name, area="USA", type="LEAGUE")
                s.add(c)
            return c
        ncaa, nfl = comp("NCAA", "NCAA Football"), comp("NFL", "NFL")
        big = [Team(sport=Sport.NFL, name=f"Audit Big {i}") for i in range(4)]
        small = [Team(sport=Sport.NFL, name=f"Audit Small {i}") for i in range(2)]
        s.add_all(big + small)
        s.flush()
        rows = []

        def mk(c, season, when, h, a, hs, as_, stage="Regular Season", st=MatchStatus.FINISHED):
            rows.append(Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=when,
                              status=st, home_team_id=h.id, away_team_id=a.id,
                              home_score=hs, away_score=as_, stage=stage))
        d25, d26 = datetime(2025, 8, 30), datetime(2026, 8, 29)
        # 2025: big teams play 10 each, small teams host big teams and lose
        for w in range(12):
            mk(ncaa, "2025", d25 + timedelta(days=7 * w), big[w % 2], big[2 + w % 2], 28, 14)
        mk(ncaa, "2025", d25, small[0], big[0], 3, 45)
        mk(ncaa, "2025", d25 + timedelta(days=100), big[2], big[0], 10, 13)   # reversed pairing
        mk(ncaa, "2025", d25 + timedelta(days=101), big[1], big[3], 17, 17)   # regular-season tie
        mk(ncaa, "2025", datetime(2025, 12, 20), big[1], big[3], 20, 20, stage="Post Season")
        for w in range(6):
            mk(ncaa, "2026", d26 + timedelta(days=7 * w), big[w % 4], small[w % 2], 35, 7)
        mk(ncaa, "2026", datetime(2026, 11, 1), big[0], big[1], None, None, st=MatchStatus.SCHEDULED)
        mk(nfl, "2026", d26, big[0], big[1], 99, 98)
        s.add_all(rows)


def _row_counts():
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Base
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


def test_cli_audit_reads_everything_and_writes_nothing(monkeypatch):
    from click.testing import CliRunner

    from cli import cli

    _seed()
    before = _row_counts()
    data = na.load()
    assert _row_counts() == before
    mine = [g for g in data.games if data.names.get(g.home_id, "").startswith("Audit ")]
    assert len(mine) == 16 + 6                           # finished+scored NCAA only; NFL row out
    assert any(g.stage == "Post Season" for g in mine)   # gate exclusions NOT applied
    assert "venue" in data.inventory.match_columns
    assert "venue" in data.inventory.site_division_named

    from src.walters import ncaa_backtest as nb
    recorded = nb.v1r_run_recorded
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: False)         # #368: refused until the v1r run
    fenced = CliRunner().invoke(cli, ["ncaa-audit", "--limit", "5"])
    assert fenced.exit_code == 2 and "ncaa-audit REFUSED (exit 2)" in fenced.output
    monkeypatch.setattr(nb, "v1r_run_recorded", recorded)    # the committed registry records the run (addendum 24 (e))
    res = CliRunner().invoke(cli, ["ncaa-audit", "--limit", "5"])
    assert res.exit_code == 0, res.output
    out = res.output
    for needle in ("NCAA DATA AUDIT", "=== SEASON 2025 ===", "=== SEASON 2026 ===",
                   "(1) HOME RATE BY STAGE", "(1) HOME RATE BY MONTH", "(2a) REPEATED PAIRINGS",
                   "(2b) HEURISTIC", "(2c) HEURISTIC", "FIELD INVENTORY (d)",
                   "NO neutral-site flag column exists", "(3) SUSPECTS",
                   "GATE EXCLUSIONS", "postseason", "tied final", "Audit Big 2"):
        assert needle in out, needle
    only = CliRunner().invoke(cli, ["ncaa-audit", "--season", "2026"])
    assert only.exit_code == 0 and "=== SEASON 2025 ===" not in only.output
    assert "=== SEASON 2026 ===" in only.output
    assert _row_counts() == before                       # the CLI writes nothing
