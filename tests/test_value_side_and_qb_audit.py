"""Architect rulings 2026-09-29 (Week 4 MNF, PHI@CHI: model CHI 48.9 vs
market 35.5 = +13.4pp on the dog; the Desk said PASS; CHI won 27-7).

(2) value_side_clv — model vs close on the VALUE side, beside pick-vs-close,
    anchored on the earliest pre-kickoff BOOK snapshot (sync-odds-football now
    appends one per sync; the Odds table is wipe-and-replace).
(3) QB feed audit — injured QBs vanished from qb_listed three possible ways
    (H1 not on the report, H2 position did not resolve, H3 the 14-day
    fixture-date filter dropped a still-listed player); the detection fixes
    and the audit command's classification."""
import math
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.adapters.normalized import NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Injury, Match, MatchStatus, Odds, OddsSnapshot,
                           Prediction, Sport, Team)
from src.walters import qb_audit
from src.walters.nfl_predict import value_side_grade
from src.timeutil import utc_now_naive

NOW = utc_now_naive().replace(microsecond=0)


# ------------------------------------------------ (2) value-side grading ----

def test_value_side_grade_mnf_shape():
    # CHI home: model 0.489, market at the anchor 0.355 -> value on the dog
    g = value_side_grade(0.489, 0.355, 0.355)
    assert g["side"] == "HOME" and g["edge_at_anchor_pp"] == 13.4 and g["shadow"] is True
    assert math.isclose(g["value_side_clv"], 0.134, abs_tol=1e-9)
    # the top pick carries the value: same side, not a shadow
    g = value_side_grade(0.66, 0.60, 0.62)
    assert g["side"] == "HOME" and g["shadow"] is False and math.isclose(g["value_side_clv"], 0.04)
    # value on the away side under the floor: not a shadow
    g = value_side_grade(0.55, 0.57, 0.58)
    assert g["side"] == "AWAY" and g["shadow"] is False and math.isclose(g["value_side_clv"], 0.03)
    # no anchor / no close / zero edge: unknown, never guessed from the close
    assert value_side_grade(0.5, None, 0.4) is None
    assert value_side_grade(0.5, 0.4, None) is None
    assert value_side_grade(0.5, 0.5, 0.4) is None


def _nfl_comp(s):
    c = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                            Competition.code == "NFL")).scalars().first()
    if c is None:
        c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _game(s, tag, kickoff, status, gid=None, scores=None):
    comp = _nfl_comp(s)
    h = Team(sport=Sport.NFL, name=f"VS {tag} Home", external_ids={"vs": f"{tag}h"})
    a = Team(sport=Sport.NFL, name=f"VS {tag} Away", external_ids={"vs": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kickoff,
              status=status, home_team_id=h.id, away_team_id=a.id,
              external_ids={"api_american_football": gid} if gid else {"vs": tag})
    if scores:
        m.home_score, m.away_score = scores
    s.add(m)
    s.flush()
    return m


def _consensus(s, m, home, at, source="api_american_football"):
    for sel, p in (("HOME", home), ("AWAY", 1 - home)):
        s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p,
                           n_books=5, captured_at=at, source=source))


def _close(s, m, home):
    for sel, p in (("HOME", home), ("AWAY", 1 - home)):
        s.add(Odds(match_id=m.id, bookmaker="bk", market="1X2", selection=sel,
                   price_decimal=1 / p, source="api_american_football"))


def test_grade_nfl_prints_value_side_beside_pick_vs_close():
    from src.walters.nfl_predict import grade_nfl
    init_db()
    ko = NOW - timedelta(days=1)
    with session_scope() as s:
        mnf = _game(s, "mnf", ko, MatchStatus.FINISHED, scores=(27, 7))
        s.add(Prediction(match_id=mnf.id, model_version="t", home_win_prob=0.489, away_win_prob=0.511))
        _consensus(s, mnf, 0.30, ko - timedelta(days=3))        # the ANCHOR (earliest)
        _consensus(s, mnf, 0.36, ko - timedelta(hours=2))       # later capture: not the anchor
        _consensus(s, mnf, 0.10, ko - timedelta(days=4), source="kalshi")   # never a book anchor
        _consensus(s, mnf, 0.90, ko + timedelta(hours=1))       # in-play: never
        _close(s, mnf, 0.355)
        bare = _game(s, "bare", ko, MatchStatus.FINISHED, scores=(10, 20))
        s.add(Prediction(match_id=bare.id, model_version="t", home_win_prob=0.60, away_win_prob=0.40))
        _close(s, bare, 0.55)                                   # close but no snapshot: unanchored
    lines = []
    r = grade_nfl(days_back=3, progress=lines.append)
    mine = next(x for x in lines if "VS mnf Away" in x)
    assert "clv=-13.4pp" in mine                                # pick-vs-close unchanged (PHI top pick)
    assert "value=HOME +13.4pp [shadow]" in mine                # anchor 0.30 < 0.489: value on CHI
    assert "value=— (no anchor)" in next(x for x in lines if "VS bare Away" in x)
    assert {"games", "hits", "logloss", "mean_clv_pp"} <= set(r)          # existing metrics unchanged
    assert r["value_side_n"] >= 1 and r["value_shadow_n"] >= 1
    assert any("unanchored — no pre-kickoff book snapshot" in x for x in lines)


def test_results_md_prints_both(tmp_path, monkeypatch):
    import src.walters.nfl_predict as nfp
    from src.walters.export import results_tally
    monkeypatch.setattr(nfp, "grade_nfl", lambda days_back=30: {
        "ok": True, "games": 16, "hits": 9, "logloss": 0.66, "mean_clv_pp": -1.25,
        "value_side_n": 12, "mean_value_side_clv_pp": 2.5, "value_shadow_n": 3,
        "mean_value_shadow_clv_pp": 6.1})
    out = tmp_path / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    assert "- Mean pick-vs-close: -1.25pp" in txt
    assert "- Mean value-side-vs-close: +2.50pp (n=12 anchored; value-shadow cohort +6.10pp, n=3)" in txt
    monkeypatch.setattr(nfp, "grade_nfl", lambda days_back=30: {
        "ok": True, "games": 2, "hits": 1, "logloss": 0.7, "mean_clv_pp": 0.5,
        "value_side_n": 0, "mean_value_side_clv_pp": None, "value_shadow_n": 0,
        "mean_value_shadow_clv_pp": None})
    results_tally(days=30, out_path=str(out))
    assert "- Mean value-side-vs-close: — (no games with a pre-kickoff book snapshot yet)" in out.read_text()


def test_sync_odds_football_appends_book_consensus_snapshots(monkeypatch):
    import src.adapters.api_american_football as aaf
    from src.ingestion.service import sync_odds_nfl
    init_db()
    with session_scope() as s:
        m = _game(s, "snap", NOW + timedelta(days=2), MatchStatus.SCHEDULED, gid="G-SNAP-1")
        mid = m.id

    class Fake:
        source_name = "api_american_football"

        def list_odds(self, gid):
            if gid != "G-SNAP-1":
                return []
            mk = lambda bk, sel, px: NormalizedOdds(match_source_id=gid, source="x", bookmaker=bk,
                                                   market="1X2", selection=sel, price_decimal=px,
                                                   captured_at=NOW)
            return [mk("a", "HOME", 1.8), mk("a", "AWAY", 2.1), mk("b", "HOME", 1.85), mk("b", "AWAY", 2.0),
                    NormalizedOdds(match_source_id=gid, source="x", bookmaker="a", market="SPREADS",
                                   selection="HOME", price_decimal=1.9, captured_at=NOW, line=-2.5)]
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", Fake)
    r1 = sync_odds_nfl()
    r2 = sync_odds_nfl()
    assert r1["snapshots"] == 2 and r2["snapshots"] == 2
    with session_scope() as s:
        snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == mid)).scalars())
        n_odds = s.execute(select(func.count(Odds.id)).where(Odds.match_id == mid)).scalar_one()
    assert len(snaps) == 4                                  # appended, never replaced
    assert {x.source for x in snaps} == {"api_american_football"} and {x.market for x in snaps} == {"1X2"}
    by_ts = {}
    for x in snaps:
        by_ts.setdefault(x.captured_at, []).append(x)
    assert all(math.isclose(sum(x.devig_prob for x in g), 1.0) for g in by_ts.values())   # de-vigged
    assert all(x.n_books == 2 for x in snaps)
    assert n_odds == 5                                      # the Odds rows are still wipe-and-replace


# ------------------------------------------------------- (3) QB audit ----

ROSTER = [{"id": 1, "name": "Caleb Williams", "position": "QB"},
          {"id": 2, "name": "Case Keenum", "position": "QB"},
          {"id": 3, "name": "DJ Moore", "position": "WR"},
          {"id": 4, "name": "Tyson Bagent", "position": "Quarterback"}]


def _item(pid, name, status="Out", days_ago=2):
    return {"player": {"id": pid, "name": name}, "status": status,
            "date": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S+00:00")}


def test_is_qb_and_resolver():
    assert qb_audit.is_qb("QB") and qb_audit.is_qb("quarterback") and qb_audit.is_qb(" qb ")
    assert not qb_audit.is_qb(None) and not qb_audit.is_qb("WR") and not qb_audit.is_qb("Offense")
    idx = qb_audit.roster_index(ROSTER)
    assert qb_audit.resolve_position({"id": 1, "name": "x"}, idx) == ("QB", "roster_id")
    assert qb_audit.resolve_position({"id": 999, "name": "Caleb Williams"}, idx) == ("QB", "roster_name")
    assert qb_audit.resolve_position({"id": 999, "name": "C. Williams"}, idx) == ("QB", "roster_initial")
    assert qb_audit.resolve_position({"id": 999, "name": "Nobody Here"}, idx) == (None, None)
    two = qb_audit.roster_index(ROSTER + [{"id": 9, "name": "Chris Williams", "position": "DT"}])
    assert qb_audit.resolve_position({"id": 999, "name": "C. Williams"}, two) == (None, None)  # ambiguous: never guessed


def test_audit_live_classifies_h1_h2_h3():
    # H3: the starter is still listed but his report date is 20 days old
    r = qb_audit.audit_live([_item(1, "Caleb Williams", days_ago=20), _item(3, "DJ Moore")], ROSTER, NOW)
    assert any("Caleb Williams (Out): " in v and "H3:" in v for v in r["verdict"])
    # H2: the provider's injury id does not match the roster id; the name resolves it now
    r = qb_audit.audit_live([_item(777, "Caleb Williams")], ROSTER, NOW)
    assert any("H2: the pre-fix id-only join missed him (resolved by roster_name" in v for v in r["verdict"])
    # a "Quarterback" spelling was invisible to the pre-fix == "QB" read
    r = qb_audit.audit_live([_item(4, "Tyson Bagent")], ROSTER, NOW)
    assert any("Tyson Bagent" in v and "H2" in v for v in r["verdict"])
    # H1: no QB on the report at all
    r = qb_audit.audit_live([_item(3, "DJ Moore")], ROSTER, NOW)
    assert r["verdict"][0].startswith("H1: no QB on the provider's injury report (roster QBs: Caleb Williams, Case Keenum")
    # empty roster: every position None
    r = qb_audit.audit_live([_item(1, "Caleb Williams")], [], NOW)
    assert any("roster came back EMPTY" in v for v in r["verdict"])


def test_adapter_resolves_by_name_and_marks_current_status(monkeypatch):
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter.__new__(APIAmericanFootballAdapter)
    feeds = {"players": {"response": [{"player": p} for p in ROSTER]},
             "injuries": {"response": [_item(777, "Caleb Williams", days_ago=30), _item(3, "DJ Moore")]}}
    monkeypatch.setattr(ad, "_get", lambda path, params=None: feeds[path], raising=False)
    out = ad.list_injuries("16", "2026")
    by = {o["player_name"]: o for o in out}
    assert by["Caleb Williams"]["player_position"] == "QB" and by["DJ Moore"]["player_position"] == "WR"
    assert all(o["current_status"] is True for o in out)


def test_service_keeps_old_current_status_rows_and_still_filters_history_feeds():
    from src.ingestion.service import IngestionService, SyncResult
    init_db()

    class Fake:
        source_name = "vs_fake"

        def __init__(self, rows):
            self.rows = rows

        def list_injuries(self, sid, season):
            return self.rows
    old = (NOW - timedelta(days=30)).isoformat()
    with session_scope() as s:
        t = Team(sport=Sport.NFL, name="VS Injury Team", external_ids={"vs_fake": "T1"})
        s.add(t)
        s.flush()
        IngestionService(Fake([
            {"player_name": "Starter QB", "player_position": "QB", "type": "Out",
             "fixture_date": old, "current_status": True},          # NFL: still listed -> kept
            {"player_name": "Recovered Mid", "player_position": "M", "type": "Missing Fixture",
             "fixture_date": old},                                   # history feed: stale -> dropped
        ]))._sync_injuries_for_team(s, t, "2026", NOW, SyncResult())
        s.flush()
        names = {i.player_name for i in s.execute(select(Injury).where(Injury.team_id == t.id)).scalars()}
    assert names == {"Starter QB"}


def test_nfl_qb_audit_cli_stored_is_read_only(monkeypatch):
    from cli import cli
    init_db()
    with session_scope() as s:
        m = _game(s, "qbaud", NOW - timedelta(hours=10), MatchStatus.FINISHED, scores=(27, 7))
        home = s.get(Team, m.home_team_id)
        s.add_all([Injury(team_id=home.id, player_name="Caleb Williams", player_position=None,
                          type="Out", refreshed_at=NOW - timedelta(hours=30)),
                   Injury(team_id=home.id, player_name="DJ Moore", player_position="WR",
                          type="Questionable", refreshed_at=NOW - timedelta(hours=30))])
    with session_scope() as s:
        before = s.execute(select(func.count(Injury.id))).scalar_one()
    res = CliRunner().invoke(cli, ["nfl-qb-audit", "--team", "VS qbaud Home"])
    assert res.exit_code == 0, res.output
    assert "STORED (DB, read-only): 2 injury rows" in res.output and "+20.0h before kickoff" in res.output
    assert "positions unresolved: 1 ['Caleb Williams']" in res.output
    assert "add --live" in res.output
    with session_scope() as s:
        assert s.execute(select(func.count(Injury.id))).scalar_one() == before
    res = CliRunner().invoke(cli, ["nfl-qb-audit", "--team", "VS"])
    assert res.exit_code != 0 and "be specific" in res.output


def test_each_grade_records_the_anchor_timestamp(tmp_path):
    """Ruling 2026-09-29 on #63 (b): the anchor is ratified as the market at
    claim time (sync precedes predict in every chain); each grade records the
    anchor timestamp beside the prediction's, so the equivalence is visible."""
    import json
    from src.walters.nfl_predict import export_nfl_results, grade_nfl
    init_db()
    ko = NOW - timedelta(days=1)
    with session_scope() as s:
        ok = _game(s, "sok", ko, MatchStatus.FINISHED, scores=(27, 7))
        s.add(Prediction(match_id=ok.id, model_version="t", home_win_prob=0.489, away_win_prob=0.511,
                         computed_at=ko - timedelta(days=2, hours=23)))
        _consensus(s, ok, 0.355, ko - timedelta(days=3))         # synced BEFORE predict
        _close(s, ok, 0.355)
        late = _game(s, "slt", ko, MatchStatus.FINISHED, scores=(7, 27))
        s.add(Prediction(match_id=late.id, model_version="t", home_win_prob=0.60, away_win_prob=0.40,
                         computed_at=ko - timedelta(days=3)))
        _consensus(s, late, 0.50, ko - timedelta(days=1))        # first snapshot AFTER predict
        _close(s, late, 0.50)
    lines = []
    r = grade_nfl(days_back=3, progress=lines.append)
    stamp = lambda dt: dt.strftime("%m-%d %H:%MZ")
    ok_line = next(x for x in lines if "VS sok Away" in x)
    assert (f"anchor={stamp(ko - timedelta(days=3))} pred={stamp(ko - timedelta(days=2, hours=23))}" in ok_line
            and "ANCHOR AFTER PREDICTION" not in ok_line)
    assert "⚠ ANCHOR AFTER PREDICTION" in next(x for x in lines if "VS slt Away" in x)
    assert r["value_anchor_after_prediction_n"] >= 1
    assert any("anchor after prediction:" in x for x in lines)
    # the results file persists it per graded row (additive fields)
    path = export_nfl_results(days_back=3, out_dir=str(tmp_path))
    rows = {x["home_team"]: x["graded"] for x in json.load(open(path))["results"]}
    g = rows["VS sok Home"]
    assert g["value_side"] == "HOME" and g["value_shadow"] is True and g["value_side_clv"] == 0.134
    assert g["value_anchor_at"] == (ko - timedelta(days=3)).isoformat()
    assert g["value_prediction_at"] == (ko - timedelta(days=2, hours=23)).isoformat()
    assert "clv" in g and "close_home_prob" in g                    # existing fields unchanged
    unanchored = rows.get("VS bare Home")
    if unanchored is not None:                                      # created by the earlier test in this module
        assert unanchored["value_side"] is None and unanchored["value_anchor_at"] is None
