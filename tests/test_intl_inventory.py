"""#220 UNL lane step 1: the read-only national-team results inventory."""
from datetime import datetime, timedelta

from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.walters import intl_inventory as ii


def test_inventory_counts_rates_and_prior_history():
    init_db()
    with session_scope() as s:
        comps = {}
        for code in ("UNL", "FRIENDLIES_INT"):
            comps[code] = s.execute(select(Competition).where(Competition.code == code)).scalars().first() \
                or Competition(sport=Sport.SOCCER, code=code, name=code, area="World", type="CUP")
            s.add(comps[code])
        s.flush()
        t = {n: Team(sport=Sport.SOCCER, name=f"Inv {n}") for n in ("A", "B", "C")}
        s.add_all(t.values())
        s.flush()
        d0 = datetime(2078, 3, 1)

        def m(code, season, h, a, hs, as_, days, status=MatchStatus.FINISHED, venue=None):
            s.add(Match(sport=Sport.SOCCER, competition_id=comps[code].id, season=season, utc_date=d0 + timedelta(days=days),
                        status=status, home_team_id=t[h].id, away_team_id=t[a].id, home_score=hs, away_score=as_,
                        venue=venue))
        m("FRIENDLIES_INT", "2078", "A", "C", 2, 0, 0, venue="Stadium A")     # A's prior history
        m("FRIENDLIES_INT", "2078", "C", "A", 1, 1, 5)
        m("UNL", "2078/79", "A", "B", 1, 0, 30)
        m("UNL", "2078/79", "B", "A", 0, 2, 40)
        m("UNL", "2078/79", "A", "B", None, None, 50, status=MatchStatus.SCHEDULED)
    with session_scope() as s:
        before = s.execute(select(func.count(Match.id))).scalar()
    with session_scope() as s:
        r = ii.inventory(s)
        s.rollback()
        assert s.execute(select(func.count(Match.id))).scalar() == before
    unl = next(x for x in r["table"] if x["code"] == "UNL" and x["season"] == "2078/79")
    assert (unl["matches"], unl["finished_scored"], unl["teams"]) == (3, 2, 2)
    assert (unl["home_rate"], unl["away_rate"]) == (0.5, 0.5)
    fr = next(x for x in r["table"] if x["code"] == "FRIENDLIES_INT" and x["season"] == "2078")
    assert fr["venue_populated"] == 0.5 and fr["draw_rate"] == 0.5
    assert r["unl_teams_prior_history"].get("1-9", 0) >= 1          # A: 2 friendlies before its first UNL match
    out = CliRunner().invoke(__import__("cli").cli, ["intl-inventory"]).output
    assert "INTL INVENTORY (#220)" in out and "no neutral flag is stored" in out
