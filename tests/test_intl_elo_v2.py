"""intl-elo-v2 (ARCHITECT 2026-10-02): (a) the rating-to-probability scale
(c multiplier) and a global K multiplier fitted on the TRAINING stream only
over the declared grid; (b) neutral rule v3 (venue country != home country)
from the route-B venue ingest. v1's numbers are untouched at (1, 1).
Synthetic data; the API and the real ledger are never touched."""
import json
import os
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.walters import intl_elo as ie

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def G(i, code, home, away, hg, ag, when, neutral=False):
    return ie.Game(i, code, "2019", when, home, away, hg, ag, neutral)


def _train(n=60):
    t, out = datetime(2019, 1, 1), []
    for i in range(n):
        out.append(G(i, "UNL" if i % 2 else "FRIENDLIES_INT", 1 + i % 4, 1 + (i + 1) % 4, (i * 7) % 4, (i * 3) % 3,
                     t + timedelta(days=i), neutral=(i % 5 == 0)))
    return out


def test_multipliers_default_to_v1_and_move_the_right_things():
    g = G(1, "UNL", 1, 2, 2, 0, datetime(2019, 1, 1))
    base, m = ie.IntlElo(mu=1.3), ie.IntlElo(mu=1.3, c_mult=1.0, k_mult=1.0)
    m.ratings = base.ratings = {1: 1600.0, 2: 1500.0}
    assert m.probs(g) == base.probs(g)
    sharp = ie.IntlElo(mu=1.3, c_mult=2.0, ratings={1: 1600.0, 2: 1500.0})
    assert sharp.probs(g)[0] > base.probs(g)[0]                            # c up -> more confident favourite
    a, b = ie.IntlElo(mu=1.3), ie.IntlElo(mu=1.3, k_mult=2.0)
    a.update(g)
    b.update(g)
    assert (b.r(1) - 1500) == pytest.approx(2 * (a.r(1) - 1500))           # K x2 -> twice the move


def test_fit_is_train_only_over_the_declared_grid_and_ties_go_to_v1():
    train = _train()
    sel, rows = ie.fit_v2(train)
    assert len(rows) == len(ie.V2_C_MULT_GRID) * len(ie.V2_K_MULT_GRID) == 48
    assert sel["loss"] == min(r[0] for r in rows)
    with pytest.raises(ValueError, match="training stream only"):
        ie.fit_v2(train + [G(999, "UNL", 1, 2, 1, 0, datetime(2024, 10, 1))])
    flat = [G(1, "UNL", 1, 2, 1, 1, datetime(2019, 1, 1), neutral=True)]   # one neutral draw: all pairs tie
    sel, _ = ie.fit_v2(flat)
    assert (sel["c_mult"], sel["k_mult"]) == (1.0, 1.0)


def _world(tmp_path):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "WCQ_EU")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code="WCQ_EU", name="WCQ", area="I", type="INTL")
            s.add(comp)
            s.flush()
        de = Team(sport=Sport.SOCCER, name="V3 Probe Germany", area="Germany", external_ids={"api_football": "770001"})
        fr = Team(sport=Sport.SOCCER, name="V3 Probe France", area="France", external_ids={"api_football": "770002"})
        nx = Team(sport=Sport.SOCCER, name="V3 Probe Nowhere", area=None, external_ids={"api_football": "770003"})
        s.add_all([de, fr, nx])
        s.flush()
        mk = lambda sid, h, a: Match(sport=Sport.SOCCER, competition_id=comp.id, season="2095",  # noqa: E731
                                     utc_date=datetime(2095, 3, 1), status=MatchStatus.FINISHED, home_team_id=h.id,
                                     away_team_id=a.id, home_score=1, away_score=0, status_raw="FT",
                                     external_ids={"api_football": sid})
        ms = [mk("8800001", de, fr), mk("8800002", de, fr), mk("8800003", fr, de), mk("8800004", nx, de)]
        s.add_all(ms)
        s.flush()
        ids = [m.id for m in ms]
    save = tmp_path / "save"
    save.mkdir()
    fx = lambda fid, vid: {"fixture": {"id": int(fid), "venue": {"id": vid, "name": "x", "city": "y"}}}  # noqa: E731
    json.dump({"response": [fx("8800001", 9001), fx("8800002", 9002), fx("8800003", 9003),
                            fx("8800004", 9004)]}, open(save / "fixtures_32_2095.json", "w"))
    return save, ids


def test_venue_sync_route_b_derives_v3_and_plans(tmp_path):
    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    from src.ingestion import intl_venues as iv
    save, ids = _world(tmp_path)
    p = iv.sync(str(save), plan_only=True)["plan"]
    assert p["calls"] >= 2 and {"France", "Germany"} <= set(p["countries"])

    class FakeClient:
        calls = []

        def _get(self, path, params):
            self.calls.append(params["country"])
            served = {"Germany": [{"id": 9001, "country": "Germany"}, {"id": 9002, "country": "Germany"}],
                      "France": [{"id": 9003, "country": "France"}]}
            return {"response": served.get(params["country"], [])}

    vd = tmp_path / "venues"
    r = iv.sync(str(save), venues_dir=str(vd), client=FakeClient())
    with session_scope() as s:
        rows = {r_.match_id: r_ for r_ in s.execute(select(IntlMatchVenue).where(IntlMatchVenue.match_id.in_(ids))).scalars()}
    assert rows[ids[0]].neutral_v3 is False and rows[ids[2]].neutral_v3 is False
    assert rows[ids[3]].neutral_v3 is None                                 # home country unknown
    assert rows[ids[0]].rule == iv.NEUTRAL_V3_RULE and "never a provider fact" in iv.NEUTRAL_V3_RULE
    # a replay from --venues-dir makes no call
    again = iv.sync(str(save), venues_dir=str(vd), client=None)
    assert again["calls"] == 0
    with pytest.raises(iv.VenueError, match="under data/"):
        iv.sync(os.path.join(ROOT, "data", "x"))


def test_v2_cli_refuses_unless_declared_and_without_venue_rows(monkeypatch):
    from cli import cli
    from src.walters import registry as reg
    monkeypatch.setattr(reg, "get", lambda eid: None)
    r = CliRunner().invoke(cli, ["intl-elo-backtest", "--candidate", "v2"])
    assert r.exit_code == 2 and "intl-elo-v2 must be declared" in r.output
    monkeypatch.setattr(reg, "get", lambda eid: {"status": "declared", "run": None})
    monkeypatch.setattr(ie, "load", lambda s, rule="v1": ([G(1, "UNL", 1, 2, 1, 0, datetime(2019, 1, 1), None)],
                                                          {"no_neutral_row": 1}))
    r = CliRunner().invoke(cli, ["intl-elo-backtest", "--candidate", "v2", "--preflight"])
    assert r.exit_code == 2 and "run intl-venue-sync" in r.output


def test_repo_declaration_v2_on_v1s_test_set():
    from src.walters import registry as reg
    e, v1 = reg.get("intl-elo-v2"), reg.get("intl-elo-v1")
    assert e["status"] == "declared" and e["run"] is None and e["declaration"] == "docs/specs/intl-elo-v2.md"
    for k in ("test_set", "gate", "confirmation_plan"):
        assert e[k] == v1[k]
    assert len(reg.prior_reads(e["test_set"], None, before_id="intl-elo-v2")) == (1 if v1["run"] else 0)
    doc = open(os.path.join(ROOT, e["declaration"])).read()
    assert "interpretation, stated so it can be" in doc and "c_mult" in doc and "k_mult" in doc
