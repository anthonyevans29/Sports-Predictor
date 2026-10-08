"""NCAA SHADOW (ARCHITECT 2026-10-07, addendum 6 item 1). Pins:
- it REFUSES until ncaa-elo-v1r is declared with its neutral-site rule, and until the CFBD side table covers
  >= 95% of the stream in both seasons;
- every row: engine model_shadow, competition NCAA, family NCAAF, the gate status (UNGATED — shadow only until
  the registry records a verdict, then the verdict), the market block beside the prediction;
- FBS games only (both teams in the side table), the next 36 hours, pre/postseason never priced;
- the model is v1 with its constants untouched; the declared neutral rule decides a CFBD-neutral game;
- the file is named and stamped NCAA, never written to the Prediction table, never a Desk / window input;
- grading reads the last row before kickoff: results (side-table score in our orientation) and model-vs-close."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, NCAACFBDLabel, Odds, Prediction, Sport, Team)
from src.models.ncaa_elo import NCAAEloConfig
from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh

NOW = datetime(2034, 6, 1, 12, 0)


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        t = [Team(sport=Sport.NFL, name=f"NSH Team {i}") for i in range(5)]   # t[4]: never in the side table
        s.add_all(t)
        s.flush()
        ids = {"teams": [x.id for x in t], "finished": []}

        def game(h, a, at, season, hs=None, as_=None, status=MatchStatus.FINISHED, stage="Regular Season",
                 label=True, neutral=False):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=at, status=status,
                      home_team_id=t[h].id, away_team_id=t[a].id, home_score=hs, away_score=as_, stage=stage)
            s.add(m)
            s.flush()
            if label and status == MatchStatus.FINISHED:
                s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=m.id, season=season,
                                    orientation="same", neutral=neutral, home_score=hs, away_score=as_,
                                    fetched_at=NOW))
                ids["finished"].append(m.id)
            return m.id
        base = datetime(2034, 1, 1)
        for i in range(8):                                                      # 2025 warm-up, all labelled
            game(i % 4, (i + 1) % 4, base + timedelta(days=i), "2025", 30 if i % 3 else 10, 20)
        ids["neutral"] = game(0, 2, base + timedelta(days=20), "2026", 28, 21, neutral=True)
        for i in range(4):                                                      # 2026, labelled
            game((i + 2) % 4, i % 4 if i % 4 != (i + 2) % 4 else 3, base + timedelta(days=30 + i), "2026", 24, 17)
        ids["up"] = game(0, 1, NOW + timedelta(hours=5), "2026", status=MatchStatus.SCHEDULED)
        ids["non_fbs"] = game(2, 4, NOW + timedelta(hours=6), "2026", status=MatchStatus.SCHEDULED)
        ids["post"] = game(1, 3, NOW + timedelta(hours=7), "2026", status=MatchStatus.SCHEDULED, stage="Post Season")
        ids["far"] = game(2, 3, NOW + timedelta(hours=40), "2026", status=MatchStatus.SCHEDULED)
        for bk in ("b1", "b2"):
            for sel, price in (("HOME", 1.7), ("AWAY", 2.25)):
                s.add(Odds(match_id=ids["up"], source="t", bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=NOW - timedelta(hours=1)))
    yield ids
    # tests/test_nfl_scope.py deletes every NFL-family match; leave no rows that reference ours
    with session_scope() as s:
        mids = [m.id for m in s.execute(select(Match).where(Match.home_team_id.in_(ids["teams"]))).scalars()]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(NCAACFBDLabel).filter(NCAACFBDLabel.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


def _fbs(ok25=True, ok26=True):
    """ncaa_cfbd.stored_coverage's shape (SCOPE 2026-10-08): labelled / CFBD's completed both-FBS games."""
    from src.ingestion import ncaa_cfbd as nc

    return {s_: {"season": s_, "payload": f"p{s_}", "reason": None, "unlabelled": [] if ok else ["CFBD 1 · x"],
                 **nc.fbs_coverage(100, 100 if ok else 90)} for s_, ok in (("2025", ok25), ("2026", ok26))}


@pytest.fixture()
def mine(world, monkeypatch):
    """The stream restricted to this module's teams (the test DB is shared across files); the SCOPE coverage
    fact (read from the side table + saved payload, tested in test_ncaa_cfbd_scope_join.py) holds."""
    from src.ingestion import ncaa_cfbd as nc

    real = nb.load_games
    teams = set(world["teams"])
    monkeypatch.setattr(nb, "load_games", lambda: [g for g in real() if g.home_id in teams and g.away_id in teams])
    monkeypatch.setattr(nc, "stored_coverage", lambda s, seasons, **k: _fbs())

    # L3: every label of this module is stamped NOW, the latest ingest record's fetched_at for both seasons
    monkeypatch.setattr(nc, "latest_record_stamps", lambda s, seasons=None: {"2025": NOW, "2026": NOW})
    return world


V1 = {"k_factor": 24.0, "home_advantage": 55.0, "mov_base": 2.2, "season_regression": 0.25, "default_rating": 1500.0}


def _registry(tmp_path, constants=V1, **extra):
    p = tmp_path / "experiments.json"
    e = {"id": sh.EID, "sport": "ncaa", **extra}
    if constants is not None:
        e["constants"] = constants
    p.write_text(json.dumps([e]))
    return str(p)


def test_refuses_until_declared_with_its_neutral_rule(mine, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    with pytest.raises(sh.ShadowRefused, match="ncaa-elo-v1r is not declared"):
        sh.export(now=NOW, out_dir=str(tmp_path), registry_path=str(empty))
    with pytest.raises(sh.ShadowRefused, match="has no neutral_site_rule"):
        sh.export(now=NOW, out_dir=str(tmp_path), registry_path=_registry(tmp_path))
    assert not list(tmp_path.glob("ncaa_shadow_*.json"))


def test_refuses_below_the_coverage_condition(mine, tmp_path, monkeypatch):
    """SCOPE (ARCHITECT 2026-10-08): "The shadow's precondition is that same fact" — labelled / CFBD's completed
    both-FBS games >= 95% in each season, never a share of our stream."""
    from src.ingestion import ncaa_cfbd as nc

    reg = _registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral")
    monkeypatch.setattr(nc, "stored_coverage", lambda s, seasons, **k: _fbs(ok26=False))
    with pytest.raises(sh.ShadowRefused, match=r"labels less than 95% of CFBD's completed both-FBS games in "
                                               r"2026 90\.0% \(90/100\)"):
        sh.export(now=NOW, out_dir=str(tmp_path), registry_path=reg)
    unread = {**_fbs(), "2025": {"season": "2025", "payload": None, "unlabelled": [], **nc.fbs_coverage(0, 0),
                                 "reason": "no side-table rows for this season"}}
    monkeypatch.setattr(nc, "stored_coverage", lambda s, seasons, **k: unread)
    with pytest.raises(sh.ShadowRefused, match=r"2025 .*no side-table rows"):
        sh.export(now=NOW, out_dir=str(tmp_path), registry_path=reg)
    assert not list(tmp_path.glob("ncaa_shadow_*.json"))


def test_the_shadow_walks_only_labelled_games(mine, tmp_path, monkeypatch):
    """SCOPE: a stored game without a CFBD label is neither walked nor scored in the shadow."""
    real = nb.load_games
    extra = nb.Game(mine["teams"][0], mine["teams"][1], "2026", NOW - timedelta(days=3), 70, 0, "Regular Season",
                    match_id=-1)                                          # label_source "matches": unlabelled
    reg = _registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral")
    base = sh.export(now=NOW, out_dir=str(tmp_path / "a"), registry_path=reg)[1]
    monkeypatch.setattr(nb, "load_games", lambda: real() + [extra])
    more = sh.export(now=NOW, out_dir=str(tmp_path / "b"), registry_path=reg)[1]
    assert more["fit"]["games_used"] == base["fit"]["games_used"]
    assert more["fit"]["unlabelled_not_walked"] == {"2026": 1}
    assert more["predictions"][0]["prediction"] == base["predictions"][0]["prediction"]


def test_export_stamps_every_row_fbs_only_and_v1_constants(mine, tmp_path):
    reg = _registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral")
    path, doc = sh.export(now=NOW, out_dir=str(tmp_path), registry_path=reg)
    assert Path(path).name == "ncaa_shadow_2034-06-01_120000.json"
    with pytest.raises(sh.ShadowRefused, match="never overwritten"):     # Codex on #344: never replaced
        sh.export(now=NOW, out_dir=str(tmp_path), registry_path=reg)
    assert (doc["sport"], doc["competition"], doc["family"], doc["engine"]) == ("ncaa", "NCAA", "NCAAF",
                                                                                 "model_shadow")
    assert doc["gate_verdict"] == "UNGATED — shadow only" and doc["gate_evidence"] is False
    assert doc["contains_predictions"] is False and "NOT gate evidence" in doc["note"]
    rows = {r["match_id"]: r for r in doc["predictions"]}
    assert set(rows) == {mine["up"]}                       # non-FBS, postseason and >36h never priced
    assert doc["skipped"] == {"not_both_fbs": 1, "postseason": 1}
    r = rows[mine["up"]]
    assert (r["engine"], r["competition"], r["family"], r["gate_verdict"], r["model_version"]) == (
        "model_shadow", "NCAA", "NCAAF", "UNGATED — shadow only", "ncaa_elo_v1r")
    assert r["market"]["fair_prob"]["HOME"] > 0.5          # the market block rides beside the prediction
    assert r["prediction"]["neutral"] is None and r["prediction"]["home_adv_applied"] == 55.0
    c = doc["fit"]["constants"]
    d = NCAAEloConfig()
    assert c == {"k_factor": d.k_factor, "home_advantage": d.home_advantage, "mov_base": d.mov_base,
                 "season_regression": d.season_regression, "default_rating": d.default_rating}
    assert doc["fit"]["neutral_updates"] == 1 and doc["fit"]["coverage"] == {"2025": 1.0, "2026": 1.0}
    with session_scope() as s:                             # nothing written to the Prediction table
        assert s.execute(select(func.count()).select_from(Prediction)
                         .where(Prediction.match_id == mine["up"])).scalar() == 0


def test_the_declared_neutral_rule_decides_a_neutral_game(mine, tmp_path):
    a = sh.export(now=NOW, out_dir=str(tmp_path / "a"),
                  registry_path=_registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral"))[1]
    b = sh.export(now=NOW, out_dir=str(tmp_path / "b"),
                  registry_path=_registry(tmp_path, neutral_site_rule="home_advantage_at_neutral"))[1]
    pa, pb = (d["predictions"][0]["prediction"]["home_win_prob"] for d in (a, b))
    assert pa != pb                                        # the one neutral game updated with HA 0 vs 55
    m = sh.V1R(False)
    g = nb.Game(1, 2, "2026", NOW, 0, 0, neutral=True)
    assert m.home_adv(g) == 0.0 and sh.V1R(True).home_adv(g) == 55.0
    assert m.home_adv(nb.Game(1, 2, "2026", NOW, 0, 0)) == 55.0         # unknown -> listed home's advantage


def test_the_gate_status_becomes_the_verdict(mine, tmp_path):
    reg = _registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral",
                    verdict={"verdict": "PASS", "ruling": "x"})
    doc = sh.export(now=NOW, out_dir=str(tmp_path), registry_path=reg)[1]
    assert doc["gate_verdict"] == "PASS" and doc["predictions"][0]["gate_verdict"] == "PASS"


def test_desk_and_window_never_read_the_shadow(mine, tmp_path):
    from src.walters import desk_policy as dp

    doc = sh.export(now=NOW, out_dir=str(tmp_path),
                    registry_path=_registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral"))[1]
    assert doc["engine"] == "model_shadow"
    src = Path(dp.__file__).read_text()
    assert 'doc.get("engine") == "model_shadow"' in src     # desk_policy's skip is by engine


def test_grade_reads_the_last_row_before_kickoff(mine, tmp_path):
    reg = _registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral")
    ex = tmp_path / "ex"
    sh.export(now=NOW - timedelta(hours=2), out_dir=str(ex), registry_path=reg)
    _, last = sh.export(now=NOW, out_dir=str(ex), registry_path=reg)
    p = last["predictions"][0]["prediction"]["home_win_prob"]
    with session_scope() as s:
        m = s.get(Match, mine["up"])
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 13, 31     # matches row: away won
        s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=m.id, season="2026", orientation="same",
                            neutral=False, home_score=31, away_score=13, fetched_at=NOW))   # source of record: home
    try:
        r = sh.grade(days=3650, export_dir=str(ex), now=NOW + timedelta(days=1))
        assert r["graded"] == 1 and r["calls_on_file"] == 1
        assert r["hit_rate"] == (1.0 if p >= 0.5 else 0.0)                 # graded on the CFBD score
        assert r["brier"] == round((p - 1) ** 2, 4) and r["priced"] == 1
        assert "result 31-13 (cfbd)" in r["lines"][0] and r["lines"][0].endswith("NOT gate evidence")
        # Codex on #344: a reused match id (different teams / kickoff in the artifact) is never graded against it
        doc = json.loads(sorted(ex.glob("ncaa_shadow_*.json"))[-1].read_text())
        doc["predictions"][0]["home_team"] = "Someone Else"
        (ex / "ncaa_shadow_2034-06-01_120001.json").write_text(json.dumps({**doc, "exported_at":
                                                                           (NOW + timedelta(seconds=1)).isoformat()}))
        r2 = sh.grade(days=3650, export_dir=str(ex), now=NOW + timedelta(days=1))
        assert (r2["graded"], r2["identity_mismatch"]) == (0, 1)
    finally:
        with session_scope() as s:
            s.delete(s.get(NCAACFBDLabel, mine["up"]))
            m = s.get(Match, mine["up"])
            m.status, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None


def test_cli_refusal_exits_2(mine, monkeypatch):
    from cli import cli

    monkeypatch.setattr(sh, "frozen", lambda *a, **k: (_ for _ in ()).throw(sh.ShadowRefused("REFUSED: test")))
    res = CliRunner().invoke(cli, ["export-ncaa-predictions"])
    assert res.exit_code == 2 and "REFUSED: test" in res.output


def test_refuses_unless_the_declaration_freezes_v1s_constants(mine, tmp_path):
    """Codex on #344: the declaration must freeze v1's untouched constants; missing or different refuses."""
    for i, const in enumerate((None, {**V1, "k_factor": 20.0}, {k: v for k, v in V1.items() if k != "mov_base"},
                               {**V1, "home_advantage": True})):
        reg = _registry(tmp_path, constants=const, neutral_site_rule="no_home_advantage_at_neutral")
        with pytest.raises(sh.ShadowRefused, match="must freeze constants"):
            sh.export(now=NOW, out_dir=str(tmp_path / f"c{i}"), registry_path=reg)
