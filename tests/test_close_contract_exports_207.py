"""P0-2 (#207) EXPORTS (ARCHITECT-RULE 2026-10-01): the MLB/soccer prediction
export's market block and the fixtures export use the SAME close contract as
grading — one definition; the export block is the Desk's reference."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.walters.export import _summarize_market, export_fixtures

NOW = datetime(2043, 6, 6, 12, 0)
KO = NOW + timedelta(hours=5)
AT = NOW - timedelta(hours=1)


def o(book, sel, price, at=AT):
    return NS(bookmaker=book, selection=sel, price_decimal=price, captured_at=at, market="1X2", line=None)


PRED = NS(home_win_prob=0.50, draw_prob=0.26, away_win_prob=0.24)


def test_prediction_block_soccer_drops_the_drawless_book():
    odds = [o("a", "HOME", 2.0), o("a", "DRAW", 3.4), o("a", "AWAY", 4.0),
            o("b", "HOME", 2.3), o("b", "AWAY", 3.0)]                      # b: no draw
    mk = _summarize_market(PRED, odds, three_way=True, before=KO)
    imp = {"HOME": 1 / 2.0, "DRAW": 1 / 3.4, "AWAY": 1 / 4.0}
    assert mk["selections"]["HOME"]["fair_prob"] == round(imp["HOME"] / sum(imp.values()), 4)
    assert mk["selections"]["HOME"]["best_price"] == 2.0                   # b's 2.3 is not a complete book
    assert (mk["bookmaker_count"], mk["bookmaker_count_quoted"]) == (1, 2)
    assert mk["overround_pct"] == round((sum(imp.values()) - 1) * 100, 2)
    assert set(mk["selections"]) == {"HOME", "DRAW", "AWAY"}


def test_prediction_block_unpriced_ships_the_no_1x2_shape_plus_receipt():
    mk = _summarize_market(PRED, [o("a", "HOME", 2.0), o("a", "AWAY", 4.0)], three_way=True, before=KO)
    assert mk["selections"] == {} and mk["bookmaker_count"] == 0
    assert mk["close_unpriced"] == {"books_quoted": 1, "missing": {"a": ["DRAW"]}}


def test_prediction_block_mlb_binary_per_book_mean():
    odds = [o("a", "HOME", 1.5), o("a", "AWAY", 2.4), o("b", "HOME", 1.8), o("b", "AWAY", 2.1),
            o("c", "HOME", 1.6)]                                            # c: one-sided
    mk = _summarize_market(NS(home_win_prob=0.6, draw_prob=None, away_win_prob=0.4), odds, before=KO)
    fa, fb = (1 / 1.5) / (1 / 1.5 + 1 / 2.4), (1 / 1.8) / (1 / 1.8 + 1 / 2.1)
    assert mk["selections"]["HOME"]["fair_prob"] == round((fa + fb) / 2, 4)
    assert (mk["bookmaker_count"], mk["bookmaker_count_quoted"]) == (2, 3)


def _game(s, sport, code, tag, rows):
    comp = s.execute(select(Competition).where(Competition.code == code)).scalars().first()
    if comp is None:
        comp = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(comp)
        s.flush()
    h = Team(sport=sport, name=f"C207 {tag} H", external_ids={"c207": f"{tag}h"})
    a = Team(sport=sport, name=f"C207 {tag} A", external_ids={"c207": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=comp.id, season="2043", utc_date=KO,
              status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
    s.add(m)
    s.flush()
    for bk, sel, px in rows:
        s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                   captured_at=AT, source="c207"))
    return m.id


def test_fixtures_export_uses_the_contract(tmp_path):
    init_db()
    with session_scope() as s:
        cup_ok = _game(s, Sport.SOCCER, "C207CUP", "ok", [("a", "HOME", 2.0), ("a", "DRAW", 3.4), ("a", "AWAY", 4.0),
                                                          ("b", "HOME", 2.2), ("b", "AWAY", 3.5)])
        cup_no = _game(s, Sport.SOCCER, "C207CUP", "no", [("a", "HOME", 2.0), ("a", "AWAY", 4.0)])
    rc = {}
    fx = {r["match_id"]: r for r in json.loads(open(export_fixtures(
        "C207CUP", start="2043-06-05", end="2043-06-08", out_dir=str(tmp_path), receipts=rc)).read())["fixtures"]}
    ok = fx[cup_ok]["market"]
    imp = {"HOME": 1 / 2.0, "DRAW": 1 / 3.4, "AWAY": 1 / 4.0}
    assert ok["fair_prob"]["HOME"] == round(imp["HOME"] / sum(imp.values()), 4)
    assert (ok["bookmaker_count"], ok["bookmaker_count_quoted"]) == (1, 2)
    assert "close_unpriced" not in fx[cup_ok]
    no = fx[cup_no]
    assert no["market"] is None and no["input_quality"]["book_odds"] == 0
    assert no["close_unpriced"] == {"books_quoted": 1, "missing": {"a": ["DRAW"]}}
    assert rc["close_unpriced"] == 1 and rc["with_books"] == 1


def test_fixtures_export_nhl_one_sided_book_unpriced(tmp_path):
    init_db()
    with session_scope() as s:
        g = _game(s, Sport.NHL, "C207NHL", "nhl", [("a", "HOME", 1.9), ("b", "HOME", 1.95), ("b", "AWAY", 1.95)])
    fx = {r["match_id"]: r for r in json.loads(open(export_fixtures(
        "C207NHL", start="2043-06-05", end="2043-06-08", out_dir=str(tmp_path))).read())["fixtures"]}
    mk = fx[g]["market"]
    assert mk["fair_prob"] == {"HOME": 0.5, "AWAY": 0.5} and (mk["bookmaker_count"], mk["bookmaker_count_quoted"]) == (1, 2)


def test_compare_script_reports_newly_unpriced_and_moves(tmp_path, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ecc", "scripts/export_close_compare.py")
    ecc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ecc)
    before = {"fixtures": [
        {"match_id": 1, "home_team": "H", "away_team": "A", "utc_date": "2043-06-06T17:00:00",
         "market": {"bookmaker_count": 2, "fair_prob": {"HOME": 0.50, "AWAY": 0.50}}},
        {"match_id": 2, "market": {"bookmaker_count": 1, "fair_prob": {"HOME": 0.40, "DRAW": 0.3, "AWAY": 0.3}}}]}
    after = {"fixtures": [
        {"match_id": 1, "home_team": "H", "away_team": "A", "utc_date": "2043-06-06T17:00:00",
         "market": {"bookmaker_count": 1, "bookmaker_count_quoted": 2, "fair_prob": {"HOME": 0.52, "AWAY": 0.48}}},
        {"match_id": 2, "market": None, "close_unpriced": {"books_quoted": 1, "missing": {"a": ["DRAW"]}}}]}
    (tmp_path / "a.json").write_text(json.dumps(before))
    (tmp_path / "b.json").write_text(json.dumps(after))
    assert ecc.main(str(tmp_path / "a.json"), str(tmp_path / "b.json")) == 0
    out = capsys.readouterr().out
    assert "NEWLY UNPRICED (contract: no complete book): 1" in out and '"missing": {"a": ["DRAW"]}' in out
    assert "fair prob moved (>0.005pp) on 1/1" in out and "max 2.00pp" in out
    assert "bookmaker_count changed (now = complete books): 2" in out
