"""K1 (2026-09-27): Kalshi yes_bid/yes_ask stored per snapshot; exports gain
kalshi_bid / kalshi_ask / kalshi_exec_cost (informational, ARCHITECT-VERIFY fee)."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text

from src.adapters.kalshi import KalshiAdapter
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Prediction, Sport, Team
from src.walters import venue
from src.timeutil import utc_now_naive


def test_fee_formula_and_exec_cost():
    # the pre-#88 model, a per-contract CEILING (kept as a documented case)
    assert venue.kalshi_order_fee(0.50, 1, rounding="ceil") == 0.02   # 0.07*.25 = 1.75c -> 2c
    assert venue.kalshi_order_fee(0.90, 1, rounding="ceil") == 0.01   # 0.63c -> 1c
    assert venue.kalshi_order_fee(0.01, 1, rounding="ceil") == 0.01   # 0.0693c -> 1c (rounded UP)
    # #88 (2026-09-30): one NEAREST-cent rounding per FILL of N = 10 contracts (re-fit, #134)
    assert venue.kalshi_fee(0.50) == 0.018         # 17.5c -> 18c / 10
    assert venue.kalshi_fee(0.90) == 0.006         # 6.3c -> 6c / 10
    assert venue.kalshi_fee(0.01) == 0.001         # 0.693c -> 1c / 10
    assert venue.kalshi_fee(0.0) == 0.0 and venue.kalshi_fee(1.0) == 0.0
    assert venue.kalshi_fee(None) is None and venue.kalshi_fee(1.2) is None
    e = venue.kalshi_exec(0.53, 0.55)               # 10 x 1.7325c = 17.3c -> 17c / 10 (was 0.57)
    assert e["exec_cost_taker"] == 0.567 and "kalshi_exec_cost" not in e and e["kalshi_bid"] == 0.53
    assert e["k_track"] == "K-track: informational until the executable-edge ruling"
    assert venue.kalshi_exec(0.5, None)["exec_cost_taker"] is None


def test_yes_quotes_parses_dollar_strings():
    assert KalshiAdapter.yes_quotes({"yes_bid_dollars": "0.53", "yes_ask_dollars": "0.55"}) == (0.53, 0.55)
    assert KalshiAdapter.yes_quotes({"yes_bid_dollars": None}) == (None, None)


@pytest.fixture(scope="module")
def nfl_game():
    init_db()
    kick = utc_now_naive() + timedelta(days=1)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                   Competition.code == "NFL")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
            s.add(comp)
        h = Team(sport=Sport.NFL, name="Kappa Kodiaks", external_ids={"k1": "h"})
        a = Team(sport=Sport.NFL, name="Omega Owls", external_ids={"k1": "a"})
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kick,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=0.6,
                         away_win_prob=0.4, draw_prob=None))
        return {"id": m.id, "kick": kick}


def test_sync_stores_quotes_and_exports_carry_exec_cost(nfl_game, monkeypatch, tmp_path):
    from src.ingestion import kalshi_sync
    occ = nfl_game["kick"].strftime("%Y-%m-%dT%H:%M:%SZ")
    markets = [
        {"ticker": "K-H", "event_ticker": "EV1", "title": "Omega vs Kappa Winner?",
         "yes_sub_title": "Kappa", "occurrence_datetime": occ,
         "yes_bid_dollars": "0.53", "yes_ask_dollars": "0.55"},
        {"ticker": "K-A", "event_ticker": "EV1", "title": "Omega vs Kappa Winner?",
         "yes_sub_title": "Omega", "occurrence_datetime": occ,
         "yes_bid_dollars": "0.45", "yes_ask_dollars": "0.47"},
    ]
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "open_markets_for_series", lambda self, s: markets)
    r = kalshi_sync.sync_kalshi_mlb(sport=Sport.NFL, series_override="KXNFLGAME")
    assert r.get("ok") and r["stored"] == 2, r
    with session_scope() as s:
        snaps = {x.selection: x for x in s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id == nfl_game["id"], OddsSnapshot.source == "kalshi")).scalars()}
        assert (snaps["HOME"].yes_bid, snaps["HOME"].yes_ask) == (0.53, 0.55)
        assert (snaps["AWAY"].yes_bid, snaps["AWAY"].yes_ask) == (0.45, 0.47)
        assert snaps["HOME"].devig_prob == 0.54            # midpoint, unchanged semantics
    from src.walters.nfl_predict import export_nfl_predictions
    row = {r["match_id"]: r for r in json.loads(open(
        export_nfl_predictions(out_dir=str(tmp_path))).read())["predictions"]}[nfl_game["id"]]
    assert (row["kalshi_bid"], row["kalshi_ask"], row["exec_cost_taker"]) == (0.53, 0.55, 0.567)
    assert row["k_track"].startswith("K-track: informational")
    assert row["kalshi_prob"] == pytest.approx(0.54 / (0.54 + 0.46), abs=1e-4)   # untouched
    from src.walters.export import export_fixtures
    fx = {r["match_id"]: r for r in json.loads(open(
        export_fixtures("NFL", out_dir=str(tmp_path))).read())["fixtures"]}[nfl_game["id"]]
    assert (fx["kalshi_bid"], fx["kalshi_ask"], fx["exec_cost_taker"]) == (0.53, 0.55, 0.567)


def test_migration_adds_columns_idempotently(tmp_path, monkeypatch, capsys):
    import migrate_kalshi_quotes as mig
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER, "
                       "market VARCHAR, selection VARCHAR, devig_prob FLOAT, line FLOAT, "
                       "n_books INTEGER, captured_at DATETIME, source VARCHAR)"))
        c.execute(text("INSERT INTO odds_snapshots VALUES (1,1,'ML','HOME',0.5,NULL,1,'2026-09-26','kalshi')"))
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "+ Adding odds_snapshots.yes_bid" in out and "+ Adding odds_snapshots.yes_ask" in out
    assert "ML           1         0         0" in out                 # pre-migration row stays NULL
    assert mig.main() == 0 and "already exists" in capsys.readouterr().out
    with eng.connect() as c:
        assert c.execute(text("SELECT devig_prob FROM odds_snapshots")).scalar() == 0.5
