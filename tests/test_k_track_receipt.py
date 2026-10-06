"""ARCHITECT 2026-10-06: the K-track receipt for the executable-edge ruling (#87) — every Kalshi ladder in the
window (spreads, two-sidedness, fee-clear at maker and taker cost, by sport) plus the executed fills' CLV, with
#75's call-to-fill reconciliation folded in (one disposition per eligible call). Read-only."""
from datetime import datetime, timedelta

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Prediction, Sport, Team
from src.walters import k_receipt as K
from src.walters import ledger_fills as P

LO, HI = datetime(2095, 9, 23), datetime(2095, 10, 8)


CREATED: list = []                              # competitions this file created (removed again)


def _comp(s, code, sport):
    c = s.query(Competition).filter_by(code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
        CREATED.append(c.id)
    return c


def _seed():
    init_db()
    with session_scope() as s:
        nfl, nhl = _comp(s, "NFL", Sport.NFL), _comp(s, "NHL", Sport.NHL)
        ts = [Team(sport=Sport.NFL, name=f"KRcpt {i}") for i in range(8)]
        s.add_all(ts)
        s.flush()
        ids = []

        def game(c, i, ko, quotes, book=None, pred=None, n_books=5, book_age=timedelta(hours=1)):
            m = Match(sport=c.sport, competition_id=c.id, season="2095", utc_date=ko, status=MatchStatus.SCHEDULED,
                      home_team_id=ts[2 * i].id, away_team_id=ts[2 * i + 1].id)
            s.add(m)
            s.flush()
            at = ko - timedelta(hours=2)
            for sel, (bid, ask) in quotes.items():
                s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=ask or 0.5, n_books=1,
                                   captured_at=at, source="kalshi", yes_bid=bid, yes_ask=ask))
            for sel, p in (book or {}).items():
                s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p, n_books=n_books,
                                   captured_at=at - book_age, source="odds_api"))
            if pred:
                s.add(Prediction(match_id=m.id, model_version="t", home_win_prob=pred, away_win_prob=1 - pred,
                                 computed_at=at - timedelta(hours=5)))
            # an in-play capture never counts
            s.add(OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=0.5, n_books=1,
                               captured_at=ko + timedelta(minutes=5), source="kalshi", yes_bid=0.5, yes_ask=0.51))
            ids.append(m.id)
        ko = LO + timedelta(days=2)
        # NFL: model 0.70 on HOME; HOME ask 0.60 -> taker cost ~0.6168 -> +8.3pp clears; maker join 0.58
        game(nfl, 0, ko, {"HOME": (0.57, 0.60), "AWAY": (0.40, 0.43)}, book={"HOME": 0.58, "AWAY": 0.42}, pred=0.70)
        # NFL: one-sided AWAY leg (bid 0) -> not two-sided, never fee-evaluated
        game(nfl, 1, ko, {"HOME": (0.50, 0.52), "AWAY": (0.0, 0.49)}, pred=0.55)
        # NHL (market-only): book 0.66 HOME vs ask 0.60 -> clears on the book basis; thin book on a second game
        game(nhl, 2, ko, {"HOME": (0.59, 0.60), "AWAY": (0.40, 0.41)}, book={"HOME": 0.66, "AWAY": 0.34})
        game(nhl, 3, ko, {"HOME": (0.59, 0.60), "AWAY": (0.40, 0.41)}, book={"HOME": 0.66, "AWAY": 0.34}, n_books=2)
    return ids


def _drop(ids):
    with session_scope() as s:
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Prediction).filter(Prediction.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.name.like("KRcpt %")).delete(synchronize_session=False)
        if CREATED:
            s.query(Competition).filter(Competition.id.in_(CREATED)).delete(synchronize_session=False)
            CREATED.clear()


def test_ladders_spreads_two_sidedness_and_fee_clear_by_sport():
    ids = _seed()
    try:
        with session_scope() as s:
            rows = K.ladders(s, LO, HI)
        mine = [r for r in rows if r["match_id"] in ids]
        assert len(mine) == 4                                              # in-play captures excluded
        agg = K.by_sport(mine)
        assert agg["NFL"]["ladders"] == 2 and agg["NFL"]["two_sided"] == 1   # bid 0.00 is not two-sided
        r0 = next(r for r in mine if r["match_id"] == ids[0])
        m = r0["fee_clear"]["model"]
        assert m["leg"] == "HOME" and m["taker"]["clears"] and m["maker"]["clears"]
        assert abs(m["taker"]["edge_pp"] - (0.70 - r0["legs"]["HOME"]["taker"]) * 100) < 1e-9
        assert r0["legs"]["HOME"]["spread_c"] == 3.0 and r0["legs"]["HOME"]["maker"] is not None
        b = r0["fee_clear"]["book"]                                       # book 0.58 vs costs: no clear
        assert b["taker"]["clears"] is False
        nhl = agg["NHL"]
        assert nhl["fc"][("book", "taker")] == [1, 1] and nhl["unevaluable"]["book"] == 1   # 2 books < 4
        assert nhl["fc"][("book", "maker")] == [0, 0]                     # 1c spread: joining = taking
        txt = "\n".join(K.format_ladders(mine, LO, HI))
        assert "- NFL: ladders 2 · complete 2 · two-sided 1 (50%)" in txt
        assert "fee-clear vs model: — (market-only sport, no live model)" in txt   # NHL
        assert "fee-clear vs book: taker 1/1 (100%) · maker —/0 · not evaluable 1" in txt
    finally:
        _drop(ids)


def _ledger():
    def call(cid, home, away, pick, units=1, **kw):
        return {"id": cid, "log_date": "2095-09-27", "sport": "NFL", "game": f"{away} @ {home}", "home": home,
                "away": away, "kickoff": "2095-09-28T17:00:00", "status": "open", "pick": pick, "tier": "lean",
                "engine": "model_edge", "call_type": "straight", "units": units, **kw}
    fill = {"id": "f1", "ticker": "KXNFLGAME-95SEP28BUFKC-KC", "side": "yes", "qty": 10, "entry": 0.58,
            "exit": 1.0, "staked": 5.8, "fees": 0.17, "open_fee": 0.17, "close_fee": 0, "pnl_pre": 4.2,
            "pnl_net": 4.03, "title": "Kansas City wins — Buffalo"}
    return {"meta": {"policy_version": "v1.1"}, "fills": [fill], "calls": [
        call("c1", "Kansas City Chiefs", "Buffalo Bills", "HOME", claim_exec_cost=0.6, status="graded",
             graded_date="2095-09-28", close_ref={"version": "p0-3 v2", "fair": {"HOME": 0.62, "AWAY": 0.38}}),
        call("c2", "Chicago Bears", "Green Bay Packers", "HOME", exec_cost=0.55),          # quote, no fill
        call("c3", "Detroit Lions", "Minnesota Vikings", "AWAY"),                           # no quote recorded
        call("c4", "Dallas Cowboys", "New York Giants", "HOME", call_type="value_shadow", units=0),   # ineligible
        dict(call("c5", "Miami Dolphins", "Jets", "HOME", exec_cost=0.5), kickoff="2095-10-12T17:00:00"),
    ]}


def test_executed_clv_matches_the_cockpit_worked_example():
    """scripts/cockpit_clv_verify.py's worked example: close 0.62, entry 0.58, opening fee 0.17 over 10
    contracts -> entry CLV +4.00pp, fee-adj +2.30pp."""
    ex = P.executed_positions(_ledger())
    (p,) = ex["pos"]
    assert abs(p["clv"] * 100 - 4.0) < 1e-9 and abs(p["fee_adj"] * 100 - 2.3) < 1e-9 and p["fee_status"] == "open_fee"


def test_reconciliation_one_disposition_per_eligible_call():
    rec = K.reconcile(_ledger(), LO, HI)
    d = {r["call_id"]: r["disposition"] for r in rec["rows"]}
    assert d == {"c1": "MATCHED", "c2": "UNKNOWN", "c3": "UNAVAILABLE"}   # c4 shadow, c5 outside the window
    assert rec["tally"]["UNATTEMPTED"] == 0 and rec["tally"]["ATTEMPTED_UNFILLED"] == 0
    assert rec["funnel"] == {"eligible": 3, "cost_recorded": 2, "matched": 1}
    lg = rec["ledger"]
    assert (lg["matched_in_window"], lg["qty"], round(lg["open_fees"], 2), round(lg["pnl_net"], 2)) == (1, 10, 0.17, 4.03)
    assert lg["fee_classes"]["taker"] == 1                                # 0.07·10·0.58·0.42 = 0.1705
    txt = "\n".join(K.format_fills(_ledger(), LO, HI))
    assert "entry CLV +4.00pp · fee-adj +2.30pp (open_fee)" in txt
    assert "UNAVAILABLE 1 · UNATTEMPTED 0 · ATTEMPTED_UNFILLED 0 · MATCHED 1 · UNKNOWN 1" in txt


def test_cli_reads_the_ledger_refuses_bad_input_and_data(tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    import cli
    from src.walters import unl_ladders as U
    init_db()
    lp = tmp_path / "bd_ledger_v1.json"
    lp.write_text(json.dumps(_ledger()))
    out = tmp_path / "receipts" / "k.txt"
    r = CliRunner().invoke(cli.cli, ["k-track-receipt", "--since", "2095-09-23T00:00Z", "--until", "2095-10-08T00:00Z",
                                     "--ledger", str(lp), "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert "NOT the ruled window — exploratory" in r.output and "CALL-TO-FILL RECONCILIATION" in out.read_text()
    bad = tmp_path / "x.json"
    bad.write_text("[]")
    assert CliRunner().invoke(cli.cli, ["k-track-receipt", "--ledger", str(bad)]).exit_code == 2
    assert CliRunner().invoke(cli.cli, ["k-track-receipt", "--since", "nope"]).exit_code == 2
    data = tmp_path / "data"                     # a stand-in: the real data/ is never touched (law 5)
    data.mkdir()
    monkeypatch.setattr(U, "data_dir", lambda: data.resolve())
    r = CliRunner().invoke(cli.cli, ["k-track-receipt", "--out", str(data / "k.txt")])
    assert r.exit_code == 2 and "REFUSED" in r.output and not (data / "k.txt").exists()
    r = CliRunner().invoke(cli.cli, ["k-track-receipt"])
    assert r.exit_code == 0 and "(the ruled window)" in r.output and "FILLS · not read" in r.output


def test_review_fixes_rewritten_predictions_one_sided_ladders_timestamps_and_fill_ids():
    """Codex on #297 (verified): (1) the predictions table keeps the current row only, so a capture taken before
    a re-prediction has no model reference: reported as such, never silently dropped and never a look-ahead;
    (2) the call window compares full timestamps; (3) one-sided ladders count as not evaluable and their
    two-sided legs' spreads are kept; (4) each reconciled fill prints its ledger id."""
    from types import SimpleNamespace as NS
    t = datetime(2095, 9, 25, 12)
    later = [NS(computed_at=t + timedelta(hours=1), home_win_prob=0.7, away_win_prob=0.3, draw_prob=None)]
    assert K._model_ref(later, t) == (None, K.REWRITTEN)
    assert K._model_ref([], t) == (None, "no model prediction for this game")

    def leg(bid, ask):
        return NS(yes_bid=bid, yes_ask=ask)
    r = K.ladder_row("NFL", t, {"HOME": leg(0.57, 0.60), "AWAY": leg(0.0, 0.43)}, [], later)
    assert not r["two_sided"] and r["fee_clear"]["model"]["reason"].startswith("one-sided")
    r2 = K.ladder_row("NFL", t, {"HOME": leg(0.57, 0.60), "AWAY": leg(0.40, 0.43)}, [], later)
    agg = K.by_sport([r, r2])["NFL"]
    assert agg["unevaluable"] == {"model": 2, "book": 2} and agg["rewritten"] == 1
    assert agg["spread_c"]["legs"] == 3                                    # the one-sided ladder's HOME leg kept
    assert "of which 1 captured before the current prediction was written" in "\n".join(K.format_ladders([r, r2], LO, HI))
    L = _ledger()
    L["calls"].append(dict(L["calls"][1], id="c6", kickoff="2095-09-23T06:00:00Z"))      # before a noon start
    ids = {c["id"] for c in K.eligible_calls(L, datetime(2095, 9, 23, 12), datetime(2095, 10, 7, 12))}
    assert "c6" not in ids and "c1" in ids
    late = dict(L["calls"][1], id="c7", kickoff="2095-10-07T09:00:00")                  # inside a noon end
    L["calls"].append(late)
    assert "c7" in {c["id"] for c in K.eligible_calls(L, datetime(2095, 9, 23, 12), datetime(2095, 10, 7, 12))}
    assert "fill [f1] KXNFLGAME-95SEP28BUFKC-KC" in "\n".join(K.format_fills(_ledger(), LO, HI))


def test_review_round_two_cost_coverage_and_ambiguous_attribution():
    """Codex on #297, round 2 (verified): (1) the funnel's 'cost recorded' counted every MATCHED call, quote or
    not; it now reads the recorded-cost fields. (2) Two real calls fitting one fill (an MLB doubleheader) were
    attributed to the first silently; parity with the Cockpit keeps the attribution, but the fill is flagged
    and listed as ambiguous."""
    L = _ledger()
    del L["calls"][0]["claim_exec_cost"]                                   # matched, but no cost recorded
    rec = K.reconcile(L, LO, HI)
    assert rec["funnel"] == {"eligible": 3, "cost_recorded": 1, "matched": 1}
    L2 = _ledger()
    L2["calls"].append(dict(L2["calls"][0], id="c1b", kickoff="2095-09-28T23:00:00"))   # game 2, same day
    rec2 = K.reconcile(L2, LO, HI)
    assert rec2["ambiguous"] == [{"fill_id": "f1", "ticker": "KXNFLGAME-95SEP28BUFKC-KC", "attributed_to": "c1",
                                  "candidates": ["c1", "c1b"]}]
    txt = "\n".join(K.format_fills(L2, LO, HI))
    assert "! AMBIGUOUS fill [f1]" in txt and "AMBIGUOUS attribution" in txt


def test_review_round_three_window_float_boundary_and_composite_no():
    """Codex on #297, round 3 (verified): (1) executed-position CLV is restricted to the window's calls, the same
    cohort as the reconciliation; (2) an exact 4.00pp edge clears despite binary-float drift; (3) a NO on a
    three-way family's HOME/AWAY leg is two outcomes: kept for Cockpit parity but flagged COMPOSITE NO."""
    from types import SimpleNamespace as NS
    L = _ledger()
    out_call = dict(L["calls"][0], id="c9", kickoff="2095-11-02T17:00:00", log_date="2095-11-01")
    L["calls"].append(out_call)
    L["fills"].append(dict(L["fills"][0], id="f9", ticker="KXNFLGAME-95NOV02BUFKC-KC"))
    txt = "\n".join(K.format_fills(L, LO, HI))
    assert "1 executed position(s) outside the window, excluded" in txt and "mean entry CLV +4.00pp (n 1)" in txt
    t = datetime(2095, 9, 25, 12)
    pred = [NS(computed_at=t - timedelta(hours=1), home_win_prob=0.35, away_win_prob=0.34, draw_prob=None)]
    legs = {"HOME": NS(yes_bid=0.58, yes_ask=0.60), "AWAY": NS(yes_bid=0.38, yes_ask=0.40)}
    import src.walters.k_receipt as KR
    orig = KR.leg_costs
    try:
        KR.leg_costs = lambda bid, ask, comp: {"taker": 0.31, "maker": None}
        r = K.ladder_row("NFL", t, legs, [], pred)
        e = r["fee_clear"]["model"]["taker"]["edge_pp"]                    # (0.35 - 0.31) * 100 = 3.9999999999999982
        assert e < 4.0 and abs(e - 4.0) < 1e-9 and r["fee_clear"]["model"]["taker"]["clears"] is True
    finally:
        KR.leg_costs = orig
    L3 = _ledger()
    L3["calls"].append({"id": "s1", "log_date": "2095-09-27", "sport": "PL", "game": "Chelsea @ Arsenal",
                        "home": "Arsenal", "away": "Chelsea", "kickoff": "2095-09-27T14:00:00", "status": "open",
                        "pick": "AWAY", "tier": "lean", "engine": "model_edge", "call_type": "straight", "units": 1})
    L3["fills"].append({"id": "s-no", "ticker": "KXEPLGAME-95SEP27CHEARS-ARS", "side": "no", "qty": 5, "entry": 0.4,
                        "exit": 1.0, "staked": 2.0, "fees": 0.07, "open_fee": 0.07, "close_fee": 0, "pnl_pre": 3.0,
                        "pnl_net": 2.93, "title": "Arsenal wins — Chelsea"})
    fx = next(f for f in P.classify_fills(L3) if f["id"] == "s-no")
    # fill matcher lane (ARCHITECT 2026-10-06): a composite is never a single-side straight
    assert fx["book"] == "off_book_sports" and fx["composite_no"] is True and "composite" in fx["category"]
    txt3 = "\n".join(K.format_fills(L3, LO, HI))
    assert "composite NO fill [s-no]" in txt3 and "booked off_book_sports" in txt3
