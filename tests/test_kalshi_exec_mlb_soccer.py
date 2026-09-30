"""K-track on MLB / soccer prediction exports (architect 2026-09-30): the rows
gain kalshi_bid / kalshi_ask / kalshi_exec_cost (additive), the HOME contract's
quotes + fee-adjusted cost, only where Kalshi is two-sided (the full outcome
set), as the NFL and fixtures exports carry since K1. The Wild Card file showed
None on every row because the fields did not exist there."""
import json
from datetime import timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Prediction, Sport, Team
from src.walters.export import export_predictions
from src.timeutil import utc_now_naive


def _game(s, sport, code, tag, kick, probs, snaps):
    comp = s.execute(select(Competition).where(Competition.sport == sport,
                                               Competition.code == code)).scalar_one_or_none()
    if comp is None:
        comp = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(comp)
        s.flush()
    h = Team(sport=sport, name=f"KX {tag} Home", external_ids={"kx": f"{tag}h"})
    a = Team(sport=sport, name=f"KX {tag} Away", external_ids={"kx": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=comp.id, season="2026", utc_date=kick,
              status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
    s.add(m)
    s.flush()
    s.add(Prediction(match_id=m.id, model_version="t", home_win_prob=probs[0],
                     draw_prob=probs[1], away_win_prob=probs[2]))
    for sel, mid, bid, ask in snaps:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=mid, n_books=1,
                           captured_at=kick - timedelta(hours=2), source="kalshi",
                           yes_bid=bid, yes_ask=ask))
    return m.id


def test_mlb_and_soccer_rows_carry_home_contract_exec_cost():
    init_db()
    kick = (utc_now_naive() + timedelta(days=3)).replace(microsecond=0)
    with session_scope() as s:
        two = _game(s, Sport.MLB, "KXMLB", "two", kick, (0.58, None, 0.42),
                    [("HOME", 0.55, 0.54, 0.56), ("AWAY", 0.45, 0.44, 0.46)])
        one = _game(s, Sport.MLB, "KXMLB", "one", kick, (0.58, None, 0.42),
                    [("HOME", 0.55, 0.54, 0.56)])                           # one-sided: null
        soc = _game(s, Sport.SOCCER, "KXSOC", "soc", kick, (0.5, 0.25, 0.25),
                    [("HOME", 0.48, 0.47, 0.49), ("DRAW", 0.27, 0.26, 0.28), ("AWAY", 0.25, 0.24, 0.26)])
        soc2 = _game(s, Sport.SOCCER, "KXSOC", "soc2", kick, (0.5, 0.25, 0.25),
                     [("HOME", 0.48, 0.47, 0.49), ("AWAY", 0.25, 0.24, 0.26)])  # no DRAW leg: partial
    lo, hi = kick - timedelta(days=1), kick + timedelta(days=1)
    mlb = {r["match_id"]: r for r in json.loads(export_predictions(
        sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="KXMLB"))["predictions"]}
    assert (mlb[two]["kalshi_bid"], mlb[two]["kalshi_ask"], mlb[two]["kalshi_exec_cost"]) == (0.54, 0.56, 0.58)
    assert mlb[two]["k_track"].startswith("K-track: informational")
    assert (mlb[one]["kalshi_bid"], mlb[one]["kalshi_ask"], mlb[one]["kalshi_exec_cost"]) == (None, None, None)
    sc = {r["match_id"]: r for r in json.loads(export_predictions(
        sport=Sport.SOCCER, start_date=lo, end_date=hi, competition_code="KXSOC"))["predictions"]}
    assert (sc[soc]["kalshi_bid"], sc[soc]["kalshi_ask"], sc[soc]["kalshi_exec_cost"]) == (0.47, 0.49, 0.51)
    # The exec fields follow the export's OWN two-sided flag (market.kalshi.normalized).
    for mid in (soc, soc2):
        assert (sc[mid]["kalshi_exec_cost"] is not None) == bool(sc[mid]["market"]["kalshi"]["normalized"])
    # CORRECTION #113 (architect 2026-09-30): a soccer game with no TIE snapshot is
    # INCOMPLETE — never normalized two-way: prob null, not quoted, cost fields null.
    k2 = sc[soc2]["market"]["kalshi"]
    assert k2["normalized"] is False and k2["prob"] is None and k2["missing_legs"] == ["DRAW"]
    assert k2["model_edge_pp"] is None and "vs_book_pp" not in k2
    assert k2["raw_yes_prob"] == {"HOME": 0.48, "AWAY": 0.25}          # the raw capture stays visible
    assert sc[soc2]["input_quality"]["kalshi"] == "partial"
    assert (sc[soc2]["kalshi_bid"], sc[soc2]["kalshi_ask"], sc[soc2]["kalshi_exec_cost"]) == (None, None, None)
    k1 = sc[soc]["market"]["kalshi"]                                      # the complete 1X2 set is untouched
    assert k1["normalized"] is True and set(k1["prob"]) == {"HOME", "DRAW", "AWAY"} and "missing_legs" not in k1
    assert sc[soc]["input_quality"]["kalshi"] == "three_way"
    assert mlb[one]["market"]["kalshi"]["prob"] == {"HOME": 0.55}          # MLB one-sided: unchanged (raw)
    # additive: the existing market/kalshi block is unchanged
    assert mlb[two]["market"]["kalshi"]["normalized"] is True


def test_113_receipt_script_reports_before_after_on_the_affected_rows(capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "rcpt", Path(__file__).resolve().parents[1] / "scripts" / "kalshi_soccer_incomplete_receipt.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    kick = (utc_now_naive() + timedelta(days=5)).replace(microsecond=0)
    with session_scope() as s:
        mid = _game(s, Sport.SOCCER, "KXRC", "rc", kick, (0.5, 0.25, 0.25),
                    [("HOME", 0.48, 0.47, 0.49), ("AWAY", 0.25, 0.24, 0.26)])
        _game(s, Sport.SOCCER, "KXRC", "rcfull", kick, (0.5, 0.25, 0.25),
              [("HOME", 0.48, 0.47, 0.49), ("DRAW", 0.27, 0.26, 0.28), ("AWAY", 0.25, 0.24, 0.26)])
    lo, hi = (kick - timedelta(days=1)).isoformat(), (kick + timedelta(days=1)).isoformat()
    assert rc.main(["--start", lo, "--end", hi, "--competition", "KXRC"]) == 0
    out = capsys.readouterr().out
    assert "rows 2 · with Kalshi 2 · incomplete now 1 · CHANGED (were normalized two-way) 1" in out
    assert f"#{mid} " in out and "missing ['DRAW']" in out
    assert "BEFORE normalized=True prob={'HOME': 0.6575, 'AWAY': 0.3425} exec_cost=0.51" in out
    assert "AFTER  normalized=False prob=None input_quality=partial exec_cost=None" in out
