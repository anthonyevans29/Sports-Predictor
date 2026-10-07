"""Next-24h window card (architect spec 2026-09-27). Rows: kickoff-sorted,
every competition, fixtures grammar; model fields copied from the canonical
exports (never recomputed); venue gap + STALE-BOOK? via venue.py; edge vs the
book fair for the model's top pick; engine model_edge | market_only."""
import json
from datetime import datetime, timedelta

import pytest

from src.db.database import get_engine, init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, Odds, OddsSnapshot,
                           Sport, Team)
from src.walters import window

NOW = datetime(2031, 5, 5, 12, 0)  # far from other tests' dates


def _comp(s, sport, code):
    c = s.query(Competition).filter_by(sport=sport, code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _team(s, sport, name):
    t = Team(sport=sport, name=name, external_ids={"wtest": name})
    s.add(t)
    s.flush()
    return t


@pytest.fixture(scope="module")
def seeded():
    init_db()
    with session_scope() as s:
        pl, nfl = _comp(s, Sport.SOCCER, "PL"), _comp(s, Sport.NFL, "NFL")
        a, b, c, d = (_team(s, Sport.SOCCER, "W-Ars"), _team(s, Sport.SOCCER, "W-Che"),
                      _team(s, Sport.NFL, "W-KC"), _team(s, Sport.NFL, "W-BUF"))
        g_soc = Match(sport=Sport.SOCCER, competition_id=pl.id, season="2030/31",
                      utc_date=NOW + timedelta(hours=5), status=MatchStatus.SCHEDULED,
                      home_team_id=a.id, away_team_id=b.id, external_ids={"wtest": "s1"})
        g_nfl = Match(sport=Sport.NFL, competition_id=nfl.id, season="2030",
                      utc_date=NOW + timedelta(hours=2), status=MatchStatus.SCHEDULED,
                      home_team_id=c.id, away_team_id=d.id, external_ids={"wtest": "n1"})
        g_out = Match(sport=Sport.NFL, competition_id=nfl.id, season="2030",
                      utc_date=NOW + timedelta(hours=30), status=MatchStatus.SCHEDULED,
                      home_team_id=c.id, away_team_id=d.id, external_ids={"wtest": "n2"})
        s.add_all([g_soc, g_nfl, g_out])
        s.flush()
        cap = NOW - timedelta(hours=1)
        for bk in ("b1", "b2", "b3", "b4"):
            for sel, price in (("HOME", 2.0), ("DRAW", 3.6), ("AWAY", 4.2)):
                s.add(Odds(match_id=g_soc.id, bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=cap))
            for sel, price in (("HOME", 1.6), ("AWAY", 2.5)):
                s.add(Odds(match_id=g_nfl.id, bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=cap))
        # Kalshi disagrees with the NFL books by > 8pp -> STALE-BOOK?
        s.add(OddsSnapshot(match_id=g_nfl.id, source="kalshi", market="ML", selection="HOME",
                           devig_prob=0.45, captured_at=cap))
        s.add(OddsSnapshot(match_id=g_nfl.id, source="kalshi", market="ML", selection="AWAY",
                           devig_prob=0.55, captured_at=cap))
        ids = {"soc": g_soc.id, "nfl": g_nfl.id, "out": g_out.id}
    return ids


def _exports(tmp_path, ids):
    (tmp_path / "nfl_predictions_2031-05-05.json").write_text(json.dumps({
        "exported_at": "2031-05-05T09:00:00Z", "predictions": [{
            "match_id": ids["nfl"], "quarantine": True, "market_divergence_pp": 16.0,
            "prediction": {"model_version": "nfl_elo_v1", "home_win_prob": 0.77,
                           "away_win_prob": 0.23, "top_pick": "home_win", "tier": "strong"}}]}))
    (tmp_path / "predictions_PL_2031-05-05.json").write_text(json.dumps({
        "exported_at": "2031-05-05T08:00:00Z", "predictions": [{
            "match_id": ids["soc"], "prediction": {
                "model_version": "v22", "top_pick": "home_win", "top_pick_prob": 0.55,
                "tier": "lean", "probabilities": {"home_win": 0.55, "draw": 0.25,
                                                  "away_win": 0.20}}}]}))
    (tmp_path / "fixtures_NHL_2031-05-05.json").write_text(json.dumps({"fixtures": []}))


def test_card_rows_sorted_joined_and_repriced(seeded, tmp_path):
    _exports(tmp_path, seeded)
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path))
    mine = [r for r in card["fixtures"] if r["match_id"] in seeded.values()]
    assert [r["match_id"] for r in mine] == [seeded["nfl"], seeded["soc"]]  # kickoff order
    assert seeded["out"] not in [r["match_id"] for r in card["fixtures"]]   # outside 24h
    nfl, soc = mine
    # model fields copied, not recomputed
    assert nfl["model"]["model_version"] == "nfl_elo_v1" and nfl["tier"] == "strong"
    assert nfl["quarantine"] is True and nfl["engine"] == "model_edge"
    assert soc["model"]["top_pick"] == "HOME" and soc["tier"] == "lean"
    # book fair (fixtures grammar) + venue gap via venue.py
    fair_home = nfl["market"]["fair_prob"]["HOME"]
    assert nfl["kalshi_home_norm"] == 0.45
    assert nfl["venue_gap_pp"] == round(abs(fair_home - 0.45) * 100, 1)
    assert nfl["venue_flag"] == "STALE-BOOK?"
    assert nfl["edge_pp"] == round((0.77 - fair_home) * 100, 1)
    assert soc["edge_pp"] == round((0.55 - soc["market"]["fair_prob"]["HOME"]) * 100, 1)
    assert soc["sport"] == "soccer" and nfl["sport"] == "nfl"
    assert card["receipts"]["with_model"] >= 2 and card["contains_predictions"] is True


def test_market_only_row_when_no_canonical_model(seeded, tmp_path):
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path))  # no exports
    mine = [r for r in card["fixtures"] if r["match_id"] in seeded.values()]
    assert all(r["model"] is None and r["engine"] == "market_only" and r["edge_pp"] is None
               for r in mine)


def test_write_card_is_atomic_and_named(tmp_path):
    path = window.write_card({"fixtures": []}, export_dir=str(tmp_path))
    assert path.endswith("window_24h.json") and not list(tmp_path.glob("*.tmp"))


def test_t90_signature_moves_when_injuries_land(seeded):
    from src.db.schema import Injury
    before = window.t90_signatures([seeded["nfl"], seeded["soc"]], now=NOW + timedelta(minutes=45))
    assert set(before) == {str(seeded["nfl"])}  # only the game inside T-90
    with session_scope() as s:
        m = s.get(Match, seeded["nfl"])
        s.add(Injury(team_id=m.home_team_id, player_name="QB1", refreshed_at=NOW))
    after = window.t90_signatures([seeded["nfl"]], now=NOW + timedelta(minutes=45))
    assert after[str(seeded["nfl"])] != before[str(seeded["nfl"])]


def test_mlb_desk_quarantine_shadow_flags_the_card_counts_and_pages(seeded, tmp_path):
    """Codex on #328 (P1): the MLB big-edge quarantine (ARCHITECT 2026-10-07) lives only in the row's desk block —
    the export's own `quarantine` stays false for MLB. The card ORs the Desk's quarantine shadow (the Cockpit's
    fileQuar: PASS, shadow_units > 0, a "quarantine … (shadow)" tag) into the flag, the count and the pager."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import sp_window_page as page

    with session_scope() as s:
        mlb = _comp(s, Sport.MLB, "MLB")
        h, a = _team(s, Sport.MLB, "W-NYY"), _team(s, Sport.MLB, "W-BOS")
        g = Match(sport=Sport.MLB, competition_id=mlb.id, season="2031", utc_date=NOW + timedelta(hours=3),
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                  external_ids={"wtest": "m1"})
        s.add(g)
        s.flush()
        mid = g.id
    desk = {"engine": "model_edge", "call": "PASS", "units": 0, "shadow_units": 1, "edge_pp": 9.0,
            "tags": ["edge ≥ floor", "quarantine > 8pp (shadow)"],
            "reason": "QUARANTINE edge 9.0pp > 8pp vs the book close — MLB big-edge quarantine, ARCHITECT 2026-10-07"}
    row = {"match_id": mid, "quarantine": False, "desk": desk,
           "prediction": {"model_version": "v2", "top_pick": "home_win", "top_pick_prob": 0.65, "tier": "lean",
                          "probabilities": {"home_win": 0.65, "draw": None, "away_win": 0.35}}}
    (tmp_path / "predictions_MLB_2031-05-05.json").write_text(json.dumps(
        {"exported_at": "2031-05-05T10:00:00Z", "predictions": [row]}))
    assert window.canonical_models(str(tmp_path))[mid]["quarantine"] is True
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path))
    r, = [x for x in card["fixtures"] if x["match_id"] == mid]
    assert r["quarantine"] is True and card["receipts"]["quarantined"] >= 1
    # the pager's quarantine flip: the same game before the rule (no shadow) -> after (shadowed)
    cur = page.snapshot(card)
    prev = {k: {**v, "quarantine": False} for k, v in cur.items()}
    assert any(d["cls"] == "quarantine" and d["id"] == str(mid) for d in page.deltas(prev, cur, {}, {}))
    # negatives: a PASS without the shadow tag, a PLAY, an empty shadow, no block — never desk-quarantined
    for dk in ({**desk, "tags": ["edge < 4pp floor"]}, {**desk, "call": "PLAY", "units": 1},
               {**desk, "shadow_units": 0}, None):
        assert window.desk_quarantined(dk) is False
    assert window.desk_quarantined({"call": "PASS", "shadow_units": 0.5,
                                    "tags": ["quarantine ≥ 15pp (shadow)"]}) is True     # the NFL shape too
