"""CORRECTION #117 (architect 2026-09-30, HIGH: cups are on the venue-edge
charter). The fixtures export (cups, UNL) and the window card's Kalshi
home-price dropped the "HOME + AWAY = two-sided" shortcut on soccer: a 1X2
set is complete only with HOME, DRAW and AWAY, P(home) is normalized over all
three, and a set missing a leg is "partial" — no normalized price, no exec
fields, no venue gap, no Kalshi line-move series. NFL / MLB unchanged."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, OddsSnapshot, Sport, Team
from src.walters import venue, window
from src.walters.export import export_fixtures

NOW = datetime(2032, 3, 3, 12, 0)


def ks(sel, p, at, bid=None, ask=None):
    return NS(source="kalshi", selection=sel, devig_prob=p, captured_at=at, yes_bid=bid, yes_ask=ask)


def test_home_prob_three_way_needs_all_legs_two_way_unchanged():
    at, ko = NOW - timedelta(hours=1), NOW
    full = [ks("HOME", 0.50, at, 0.49, 0.51), ks("DRAW", 0.27, at), ks("AWAY", 0.25, at)]
    r = venue.kalshi_home_prob(full, ko, three_way=True)
    assert abs(r["home"] - 0.50 / 1.02) < 1e-9 and (r["home_bid"], r["home_ask"]) == (0.49, 0.51)
    assert venue.kalshi_home_prob(full[:1] + full[2:], ko, three_way=True) is None     # TIE missing
    # the pre-#117 read of the same full set was H/(H+A): 0.50/0.75 = 0.667 — not a 1X2 home price
    nfl = [ks("HOME", 0.54, at), ks("AWAY", 0.46, at)]
    assert abs(venue.kalshi_home_prob(nfl, ko)["home"] - 0.54) < 1e-9                  # two-way: unchanged


def _cup_game(s, code, tag, legs):
    comp = s.execute(select(Competition).where(Competition.code == code)).scalars().first()
    if comp is None:
        comp = Competition(sport=Sport.SOCCER, code=code, name=code, area="X", type="CUP")
        s.add(comp)
        s.flush()
    h = Team(sport=Sport.SOCCER, name=f"K117 {tag} H", external_ids={"k117": f"{tag}h"})
    a = Team(sport=Sport.SOCCER, name=f"K117 {tag} A", external_ids={"k117": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2031/32", utc_date=NOW + timedelta(hours=5),
              status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
    s.add(m)
    s.flush()
    for sel, p, bid, ask in legs:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=p, n_books=1,
                           captured_at=NOW - timedelta(hours=1), source="kalshi", yes_bid=bid, yes_ask=ask))
    return m.id


FULL = [("HOME", 0.50, 0.49, 0.51), ("DRAW", 0.27, 0.26, 0.28), ("AWAY", 0.25, 0.24, 0.26)]
NOTIE = [("HOME", 0.50, 0.49, 0.51), ("AWAY", 0.25, 0.24, 0.26)]


def test_fixtures_export_marks_a_soccer_set_missing_a_leg_partial(tmp_path):
    init_db()
    with session_scope() as s:
        full = _cup_game(s, "K117CUP", "full", FULL)
        notie = _cup_game(s, "K117CUP", "notie", NOTIE)
    rc = {}
    fx = {r["match_id"]: r for r in json.loads(open(export_fixtures(
        "K117CUP", start="2032-03-01", end="2032-03-05", out_dir=str(tmp_path), receipts=rc)).read())["fixtures"]}
    assert fx[full]["kalshi"]["status"] == "two_sided" and fx[full]["exec_cost_taker"] == 0.527   # #88: per fill, nearest (was 0.53)
    n = fx[notie]
    assert n["kalshi"]["status"] == "partial" and n["input_quality"]["kalshi"] == "partial"
    assert (n["kalshi_bid"], n["kalshi_ask"], n["exec_cost_taker"]) == (None, None, None)
    assert n["kalshi"]["prob"] == {"HOME": 0.5, "AWAY": 0.25}                             # raw capture kept
    assert rc["kalshi_two_sided"] == 1 and rc["kalshi_partial"] == 1 and rc["kalshi_one_sided"] == 0


def test_window_card_soccer_venue_read_is_three_way_or_nothing():
    init_db()
    with session_scope() as s:
        full = _cup_game(s, "K117WIN", "wfull", FULL)
        notie = _cup_game(s, "K117WIN", "wnotie", NOTIE)
        for mid in (full, notie):                     # a book fair for the venue gap (1X2, 4 books)
            for bk in ("b1", "b2", "b3", "b4"):
                for sel, price in (("HOME", 2.0), ("DRAW", 3.6), ("AWAY", 4.5)):
                    s.add(Odds(match_id=mid, source="t", bookmaker=bk, market="1X2", selection=sel,
                               price_decimal=price, captured_at=NOW - timedelta(hours=2)))
    card = window.build_card(now=NOW, hours=24, export_dir="/nonexistent")
    rows = {r["match_id"]: r for r in card["fixtures"]}
    f, n = rows[full], rows[notie]
    assert f["kalshi_home_norm"] == round(0.50 / 1.02, 4) and f["venue_gap_pp"] is not None
    assert n["kalshi_home_norm"] is None and n["venue_gap_pp"] is None and n["venue_flag"] is None
    assert card["receipts"]["kalshi_partial"] >= 1


def test_117_receipt_script_prints_before_after(capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "r117", Path(__file__).resolve().parents[1] / "scripts" / "kalshi_soccer_twoway_receipt.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    init_db()
    with session_scope() as s:
        full = _cup_game(s, "K117RC", "rfull", FULL)
        notie = _cup_game(s, "K117RC", "rnotie", NOTIE)
        for mid in (full, notie):
            for bk in ("b1", "b2", "b3", "b4"):
                for sel, price in (("HOME", 2.0), ("DRAW", 3.6), ("AWAY", 4.5)):
                    s.add(Odds(match_id=mid, source="t", bookmaker=bk, market="1X2", selection=sel,
                               price_decimal=price, captured_at=NOW - timedelta(hours=2)))
    assert rc.main(["--start", "2032-03-01", "--end", "2032-03-05", "--competition", "K117RC"]) == 0
    out = capsys.readouterr().out
    assert "matches 2 · with Kalshi 2 · CHANGED 2 · now partial 1" in out
    # full set: H/(H+A) 0.6667 -> H/(H+D+A) 0.4902; book fair H ~0.4972 -> the old read flagged STALE-BOOK?
    assert "BEFORE status=two_sided kalshi_home=0.6667 exec=0.527" in out and "flag=STALE-BOOK?" in out
    assert "AFTER  status=two_sided kalshi_home=0.4902 exec=0.527" in out   # #88: per fill, nearest (was 0.53)
    # TIE missing: two_sided -> partial, the price, exec and gap all go
    assert "AFTER  status=partial kalshi_home=None exec=None gap=None flag=None" in out
