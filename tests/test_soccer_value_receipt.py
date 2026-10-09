"""soccer-value-receipt (ARCHITECT 2026-10-09, addendum 21 item 6; Issue #383): the READ-ONLY receipt of the model's
value sides against the close. Pins, on synthetic leagues in the throwaway test DB and a TMP registry (the real
docs/registry/ is never written, data/ never touched): the value outcome (largest model p minus close p) and the top
pick, bucket assignment at market_side's tolerance (5.0 in 5 to 10), ties to the first of H, D, A, the top-pick split,
the kind table (5-and-over only), the seeded bootstrap (determinism, no interval under two matches), the flat-stake
return at the close's fair price, the declaration as issued with its withdrawn sentence struck and marked, the
amendment (addendum 23 item 2) verbatim beside it, the Reconciliation of amendment (b) (pass; every compared figure;
a failure writes the difference and stops: no table, exit 2), and the PL reference page."""
import json
import random
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import delete, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.walters import registry as reg
from src.walters import soccer_expansion as sx
from src.walters import soccer_value_receipt as vr

SEASONS = ("2160/61", "2161/62")
PL_SEASONS = ("2162/63", "2163/64")
LEAGUES = ("PD", "SA")
START = datetime(2160, 8, 1)


# ------------------------------------------------------------------ pure --

def _r(ph, pd, pa, actual="H", mid=1):
    return {"match_id": mid, "p_home": ph, "p_draw": pd, "p_away": pa, "actual": actual}


def _fair(h, d, a):
    return {"HOME": h, "DRAW": d, "AWAY": a}


def test_fair_devigs_exactly_as_market_side():
    prices = {"HOME": 2.1, "DRAW": 3.4, "AWAY": 3.9}
    f = vr.fair(prices)
    inv = {k: 1 / v for k, v in prices.items()}
    t = sum(inv.values())
    assert f == {k: inv[k] / t for k in ("HOME", "DRAW", "AWAY")}
    assert vr.fair({"HOME": 2.0, "DRAW": 3.0}) is None and vr.fair(None) is None


def test_value_outcome_is_the_largest_model_minus_close_and_may_differ_from_the_top_pick():
    v = vr.value_row(_r(0.50, 0.30, 0.20, actual="D"), _fair(0.45, 0.22, 0.33), "PD")
    assert v["value"] == "D" and v["top"] == "H" and not v["is_top"]
    assert v["edge_pp"] == pytest.approx(8.0) and v["top_edge_pp"] == pytest.approx(5.0)
    assert v["p_model"] == 0.30 and v["p_close"] == 0.22 and v["hit"] == 1 and v["top_hit"] == 0
    w = vr.value_row(_r(0.60, 0.22, 0.18, actual="A"), _fair(0.50, 0.26, 0.24), "PD")
    assert w["value"] == "H" and w["is_top"] and w["edge_pp"] == pytest.approx(10.0) and w["hit"] == 0
    # ties break to the first of H, D, A (market_side's max)
    t = vr.value_row(_r(0.40, 0.30, 0.30), _fair(0.35, 0.25, 0.40), "PD")
    assert t["value"] == "H" and t["top"] == "H"


def test_a_tie_for_the_largest_edge_takes_the_first_of_home_draw_away():
    # exact binary fractions, so the tie is exact: draw and away tie at +12.5pp (home -25pp): the draw is taken
    t = vr.value_row(_r(0.25, 0.375, 0.375), _fair(0.5, 0.25, 0.25), "PD")
    assert t["value"] == "D" and t["edge_pp"] == 12.5
    u = vr.value_row(_r(0.375, 0.25, 0.375), _fair(0.25, 0.5, 0.25), "PD")       # home and away tie: home
    assert u["value"] == "H" and u["edge_pp"] == 12.5


def test_the_value_edge_is_never_negative_so_under_5_is_0_to_5():
    rng = random.Random(11)
    for _ in range(500):
        m = [rng.random() for _ in range(3)]
        c = [rng.random() for _ in range(3)]
        m, c = [x / sum(m) for x in m], [x / sum(c) for x in c]
        v = vr.value_row(_r(*m), _fair(*c), "PD")
        assert v["edge_pp"] >= -1e-9


@pytest.mark.parametrize("edge,bucket,five_plus", [
    (0.0, "under 5pp", False), (4.99, "under 5pp", False), (5.0 - 1e-10, "5 to 10", True), (5.0, "5 to 10", True),
    (9.999, "5 to 10", True), (10.0, "10 to 15", True), (14.99, "10 to 15", True), (15.0, "15 and over", True),
    (40.0, "15 and over", True)])
def test_bucket_assignment_lower_inclusive_at_market_sides_tolerance(edge, bucket, five_plus):
    assert vr.bucket_of(edge) == bucket
    assert vr.in_bucket(edge, 5.0, None) is five_plus
    hits = [label for label, lo, hi in vr.BUCKETS[:4] if vr.in_bucket(edge, lo, hi)]
    assert hits == [bucket]                                    # the four are exclusive and cover the line


def _row(edge, is_top, hit, value="H", p_close=0.4, league="PD"):
    return {"match_id": random.random(), "league": league, "value": value, "edge_pp": edge, "p_model": p_close + edge / 100,
            "p_close": p_close, "hit": hit, "top": "H" if is_top else "A", "is_top": is_top,
            "top_edge_pp": edge if is_top else 0.0, "top_hit": hit if is_top else 0}


def test_tables_split_every_bucket_by_top_pick_and_the_kind_table_holds_the_5_plus_row_only():
    pd = [_row(2, True, 1), _row(6, True, 1), _row(7, False, 0, value="D"), _row(12, True, 0),
          _row(16, False, 1, value="A"), _row(20, True, 1)]
    sa = [_row(3, False, 0, value="D", league="SA"), _row(8, True, 1, league="SA")]
    t = vr.tables({"PD": pd, "SA": sa}, ["PD", "SA"], n_boot=200)
    assert t["order"] == ["PD", "SA", "pooled"]
    m = t["main"]["PD"]
    n = {k: c["n"] for k, c in m.items()}
    assert n[("under 5pp", True)] == 1 and n[("under 5pp", False)] == 0
    assert n[("5 to 10", True)] == 1 and n[("5 to 10", False)] == 1
    assert n[("10 to 15", True)] == 1 and n[("15 and over", True)] == 1 and n[("15 and over", False)] == 1
    assert n[("5 and over", True)] == 3 and n[("5 and over", False)] == 2
    assert t["main"]["pooled"][("5 and over", True)]["n"] == 4 and t["main"]["pooled"][("under 5pp", False)]["n"] == 1
    k = {kk: c["n"] for kk, c in t["kind"]["PD"].items()}
    assert k == {"H": 3, "D": 1, "A": 1}                       # the 2pp row is not in the kind table
    assert t["kind"]["pooled"]["H"]["n"] == 4 and t["kind"]["SA"]["D"]["n"] == 0


def test_flat_stake_return_at_the_closes_fair_price_and_hit_minus_close():
    c = vr.cell([_row(10, True, 1, p_close=0.25), _row(10, True, 0, p_close=0.5)], n_boot=200)
    assert c["n"] == 2 and c["hits"] == 1 and c["hit_rate"] == 0.5
    assert c["return"] == pytest.approx(((1 / 0.25 - 1) + (-1)) / 2)          # +3 and -1 per stake
    assert c["hit_minus_close_pp"] == pytest.approx(((1 - 0.25) + (0 - 0.5)) * 100 / 2)
    assert c["mean_close_p"] == pytest.approx(0.375)
    assert vr.cell([]) == {"n": 0}


def test_bootstrap_is_seeded_deterministic_and_fresh_per_cell():
    rng = random.Random(3)
    rows = [_row(8, True, int(rng.random() < 0.45), p_close=0.3 + 0.3 * rng.random()) for _ in range(150)]
    a, b = vr.cell(rows, n_boot=1000), vr.cell(rows, n_boot=1000)
    assert a["hmc_ci"] == b["hmc_ci"] and a["return_ci"] == b["return_ci"]
    assert a["hmc_ci"][0] < a["hit_minus_close_pp"] < a["hmc_ci"][1]
    assert a["return_ci"][0] < a["return"] < a["return_ci"][1]
    other = vr.cell(rows, seed=vr.SEED + 1, n_boot=1000)
    assert other["return_ci"] != a["return_ci"]
    # a cell's interval does not depend on the cells computed before it
    vr.cell(rows[:20], n_boot=1000)
    assert vr.cell(rows, n_boot=1000)["return_ci"] == a["return_ci"]
    assert vr.SEED == 20261009 and vr.N_BOOT == 10000


def test_a_cell_of_fewer_than_two_matches_prints_no_interval():
    one = vr.cell([_row(8, True, 1, p_close=0.3)], n_boot=200)
    assert one["n"] == 1 and one["hmc_ci"] is None and one["return_ci"] is None
    assert one["return"] == pytest.approx(1 / 0.3 - 1)
    assert vr._cell_md(one).count("—") == 2                    # the two intervals, nothing else blank
    two = vr.cell([_row(8, True, 1, p_close=0.3), _row(8, True, 0, p_close=0.3)], n_boot=200)
    assert two["hmc_ci"] is not None and two["return_ci"] is not None
    assert vr.bootstrap([], []) == (None, None) and vr.bootstrap([1.0], [1.0]) == (None, None)


def test_bootstrap_is_the_percentile_interval_of_matches_resampled_within_the_cell_same_draws():
    import numpy as np
    a, b = [0.0, 1.0, 2.0, 5.0], [10.0, -1.0, 3.0, 0.5]
    ci_a, ci_b = vr.bootstrap(a, b, seed=5, n_boot=1000)
    rng = np.random.default_rng(5)
    idx = np.concatenate([rng.integers(0, 4, size=(500, 4)) for _ in range(2)])
    assert ci_a == tuple(float(x) for x in np.percentile(np.asarray(a)[idx].mean(axis=1), [2.5, 97.5]))
    assert ci_b == tuple(float(x) for x in np.percentile(np.asarray(b)[idx].mean(axis=1), [2.5, 97.5]))


def _mk(n_priced=100, ll_model=1.01, ll_market=0.97, n=30, hits=12, mean_edge_pp=11.5):
    return {"n_priced": n_priced, "n_unpriced": 0, "ll_model": ll_model, "ll_market": ll_market,
            "edge_cohort": {"min_edge_pp": 5.0, "n": n, "hits": hits, "mean_edge_pp": mean_edge_pp}}


def test_reconciliation_compares_n_priced_both_log_losses_and_the_cohorts_count_hits_and_mean_edge():
    g = {"n": 100, "market": _mk()}
    ok = vr.reconcile_league("PD", 100, _mk(ll_model=1.01 + 1e-12), g)
    assert ok["ok"] and [f[0] for f in ok["fields"]] == [
        "scored n", "n_priced", "model log-loss", "close log-loss", "cohort n", "cohort hits", "cohort mean edge pp"]
    for kw, name in ((dict(n_priced=99), "n_priced"), (dict(ll_model=1.02), "model log-loss"),
                     (dict(ll_market=0.9701), "close log-loss"), (dict(n=31), "cohort n"),
                     (dict(hits=13), "cohort hits"), (dict(mean_edge_pp=11.5 + 1e-6), "cohort mean edge pp")):
        d = vr.reconcile_league("PD", 100, _mk(**kw), g)
        assert not d["ok"] and [f[0] for f in d["fields"] if not f[3]] == [name], kw
    assert not vr.reconcile_league("PD", 99, _mk(), g)["ok"]                         # scored n
    # a figure the record lacks is not reproduced by one the walk has (never assumed equal)
    g2 = {"n": 100, "market": {**_mk(), "ll_market": None}}
    assert [f[0] for f in vr.reconcile_league("PD", 100, _mk(), g2)["fields"] if not f[3]] == ["close log-loss"]
    assert not vr.reconcile_league("PD", 100, None, g)["ok"]
    rc = vr.reconciliation([ok], {1, 2}, [1, 2])
    assert rc["ok"] and rc["ids"]["ok"]
    rc = vr.reconciliation([ok], {1, 2, 3}, [1, 2, 4])
    assert not rc["ok"] and rc["ids"]["not_in_file"] == 1 and rc["ids"]["not_scored"] == 1


def test_out_paths_default_under_docs_receipts_pl_page_beside_it_and_never_data(tmp_path):
    p, pl = vr.out_paths(None, "2026-10-09")
    assert p.endswith("docs/receipts/soccer-value-sides-2026-10-09.md")
    assert pl.endswith("docs/receipts/soccer-value-sides-2026-10-09-pl-reference.md")
    q, ql = vr.out_paths(str(tmp_path / "r.md"), "x")
    assert ql == str(tmp_path / "r-pl-reference.md")
    with pytest.raises(vr.ReceiptRefused, match="data/"):
        vr.out_paths(f"{reg.ROOT}/data/receipt.md", "x")


def test_the_declaration_stays_as_issued_and_its_withdrawn_sentence_is_marked_not_deleted():
    text = " ".join(vr.DECLARATION)
    for x in ("79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of 373", "512 hits on 1,281 picks",
              "PL's live read (#92) stands as declared and is not this", "seeded bootstrap 95% interval"):
        assert x in text
    assert vr.WITHDRAWN in text
    md = "\n".join(vr._declaration_md())
    assert f"~~{vr.WITHDRAWN}~~ [WITHDRAWN, ARCHITECT 2026-10-09 addendum 23 (b)]" in md
    assert md.count(vr.WITHDRAWN) == 1                        # struck once, not repeated unstruck
    assert "and 5 and over as one row, ~~which must" in md and "~~ [WITHDRAWN" in md and ") by whether" in md


def test_the_amendment_is_quoted_verbatim_a_to_e():
    assert [x[:4] for x in vr.AMENDMENT] == ["(a) ", "(b) ", "(c) ", "(d) ", "(e) "]
    text = " ".join(vr.AMENDMENT)
    for x in ("PD 79 of 212 at 11.7pp, SA 88 of 225 at 11.3pp, BL1 115 of 266 at 12.4pp, FL1 93 of 205 at 11.2pp, "
              "ELC 137 of 373 at 11.7pp", "The cohort sentence is WITHDRAWN",
              "If it does not, the receipt prints the difference and stops: no table.", "seed 20261009",
              "A cell of fewer than two matches prints no interval.", "5.0 is in 5 to 10",
              "About seventy cells are printed, each with its own uncorrected interval. Some will exclude zero by "
              "chance. The receipt describes; it tests nothing."):
        assert x in text, x


# ------------------------------------------------------------ the DB walk --

def _comp(s, code):
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.SOCCER, code=code, name=code, area="x", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


@pytest.fixture(scope="module")
def world():
    """PD and SA (the patched experiment leagues) over two synthetic test seasons, PL over two synthetic reference
    seasons: 10 clubs, a double round-robin each season (90 regular rows; the walk scores from row 41), random scores
    and an fdcuk_close 1X2 on every row but one PL row (unpriced)."""
    init_db()
    rng = random.Random(7)
    out = {"unpriced_pl": None}
    with session_scope() as s:
        pre = set(s.execute(select(Competition.code).where(Competition.code.in_(("PD", "SA", "PL")))).scalars())
        for code, seasons in (("PD", SEASONS), ("SA", SEASONS), ("PL", PL_SEASONS)):
            c = _comp(s, code)
            teams = [Team(sport=Sport.SOCCER, name=f"SVR {code} {i}") for i in range(10)]
            s.add_all(teams)
            s.flush()
            for si, season in enumerate(seasons):
                pairs = [(h, a) for h in range(10) for a in range(10) if h != a]
                rng.shuffle(pairs)
                for k, (h, a) in enumerate(pairs):
                    m = Match(sport=Sport.SOCCER, competition_id=c.id, season=season, status=MatchStatus.FINISHED,
                              status_raw="FT", utc_date=START + timedelta(days=400 * si + k // 3, hours=15),
                              home_team_id=teams[h].id, away_team_id=teams[a].id, home_score=rng.randint(0, 3),
                              away_score=rng.randint(0, 3), stage=f"Regular Season - {k // 5 + 1}")
                    s.add(m)
                    s.flush()
                    if code == "PL" and si == 1 and k == 89:
                        out["unpriced_pl"] = m.id
                        continue
                    ph, pd_ = 0.3 + 0.3 * rng.random(), 0.2 + 0.1 * rng.random()
                    for sel, p in (("HOME", ph), ("DRAW", pd_), ("AWAY", 1 - ph - pd_)):
                        s.add(Odds(match_id=m.id, bookmaker=sx.CLOSE_BOOKMAKER, market="1X2", selection=sel,
                                   price_decimal=round(1 / (p * 1.05), 3)))
    yield out
    with session_scope() as s:
        ids = select(Match.id).where(Match.season.in_(SEASONS + PL_SEASONS))
        s.execute(delete(Odds).where(Odds.match_id.in_(ids)))
        s.execute(delete(Match).where(Match.season.in_(SEASONS + PL_SEASONS)))
        s.execute(delete(Team).where(Team.name.like("SVR %")))
        s.execute(delete(Competition).where(Competition.code.in_(("PD", "SA", "PL")), Competition.code.notin_(pre)))


PARAMS = {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}


def _gate_record():
    """What the gate's run would have recorded on the synthetic world: per league n, market_side's output, ids."""
    per, ids = {}, []
    for code in LEAGUES:
        res = vr._walk(code, SEASONS, PARAMS)
        per[code] = {"n": len(res), "market": sx.market_side(res, vr._closes([r["match_id"] for r in res]))}
        ids += [r["match_id"] for r in res]
    return per, ids


@pytest.fixture
def ledger(world, monkeypatch, tmp_path):
    monkeypatch.setattr(sx, "LEAGUES", LEAGUES)
    monkeypatch.setattr(sx, "TEST_SEASONS", SEASONS)
    monkeypatch.setattr(vr, "PL_SEASONS", PL_SEASONS)
    monkeypatch.setattr(vr, "N_BOOT", 300)
    led, ids_dir = tmp_path / "experiments.json", tmp_path / "ids"
    ids_dir.mkdir()
    real_get = reg.get
    monkeypatch.setattr(reg, "LEDGER", str(led))
    monkeypatch.setattr(reg, "IDS_DIR", str(ids_dir))
    monkeypatch.setattr(reg, "get", lambda eid, path=None: real_get(eid, str(led)))
    per, ids = _gate_record()

    def put(per=per, ids=ids, run=True):
        (ids_dir / f"{sx.EID}.txt").write_text("\n".join(str(i) for i in sorted(ids)) + "\n")
        e = {"id": sx.EID, "status": "confirming", "run": None}
        if run:
            e["run"] = {"run_at": "2160-01-01T00:00:00Z", "n_scored": len(ids), "ids_sha256": reg._ids_sha(ids),
                        "ids_file": f"docs/registry/ids/{sx.EID}.txt",
                        "result": {"verdict": "PASS — surviving set PD", "per_league": per, "dropped_before_run": {},
                                   **PARAMS, "min_prior": 40}}
        led.write_text(json.dumps([e]))
    put()
    return {"put": put, "per": per, "ids": ids, "tmp": tmp_path}


def _cli(*args):
    import cli
    return CliRunner().invoke(cli.cli, ["soccer-value-receipt", *args])


def test_refused_without_the_run_record(ledger):
    ledger["put"](run=False)
    r = _cli("--out", str(ledger["tmp"] / "x.md"))
    assert r.exit_code == 2 and "no run record" in r.output and not (ledger["tmp"] / "x.md").exists()


def test_refused_when_the_ids_file_differs_from_the_record(ledger):
    ledger["put"]()
    (ledger["tmp"] / "ids" / f"{sx.EID}.txt").write_text("1\n2\n")
    r = _cli("--out", str(ledger["tmp"] / "x.md"))
    assert r.exit_code == 2 and "sha256" in r.output and not (ledger["tmp"] / "x.md").exists()


@pytest.mark.parametrize("league,path,bump", [
    ("SA", ("edge_cohort", "hits"), 1), ("PD", ("ll_market",), 1e-6), ("SA", ("edge_cohort", "mean_edge_pp"), 1e-6),
    ("PD", ("ll_model",), 1e-6), ("PD", ("n_priced",), 1)])
def test_a_failed_reconciliation_prints_the_difference_and_stops_no_table(ledger, league, path, bump):
    per = json.loads(json.dumps(ledger["per"]))
    node = per[league]["market"]
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] += bump
    ledger["put"](per=per)
    out = ledger["tmp"] / "x.md"
    r = _cli("--out", str(out))
    assert r.exit_code == 2 and "RECONCILIATION FAILED" in r.output and f"reconciliation {league}" in r.output
    assert "DIFFERS" in r.output
    text = out.read_text()
    assert "## Reconciliation" in text and "**Reconciliation: FAIL.**" in text and "DIFFERS" in text
    assert "## The declaration" in text and "## The amendment" in text and vr.WITHDRAWN_MARK in text
    for absent in ("## Tables", "### PD", "### pooled", "## Method", "### The 5-and-over row"):
        assert absent not in text
    assert not (ledger["tmp"] / "x-pl-reference.md").exists()                 # no PL page either
    data = vr.build(n_boot=50)
    assert not data["reconciliation"]["ok"] and "tables" not in data and "pl" not in data


def test_the_receipt_rewalks_the_scored_ids_and_reconciles_every_league(ledger):
    data = vr.build(n_boot=200)
    assert data["n_scored"] == len(ledger["ids"]) and data["n_unpriced"] == 0
    rc = data["reconciliation"]
    assert rc["ok"] and rc["ids"]["walked"] == len(ledger["ids"]) and rc["ids"]["ok"]
    assert [d["league"] for d in rc["per_league"]] == list(LEAGUES)
    for d in rc["per_league"]:
        f = {name: (w, r) for name, w, r, _ in d["fields"]}
        rec = ledger["per"][d["league"]]["market"]
        assert f["close log-loss"] == (rec["ll_market"], rec["ll_market"])
        assert f["cohort mean edge pp"][1] == rec["edge_cohort"]["mean_edge_pp"]
        assert f["cohort hits"][1] == rec["edge_cohort"]["hits"]
    assert data["tables"]["order"] == ["PD", "SA", "pooled"]
    # deterministic end to end
    again = vr.build(n_boot=200)
    assert again["tables"]["main"]["pooled"] == data["tables"]["main"]["pooled"]


def test_cli_writes_both_pages_with_the_declaration_amendment_and_reconciliation_before_any_table(ledger):
    out = ledger["tmp"] / "receipts" / "v.md"
    r = _cli("--out", str(out))
    assert r.exit_code == 0, r.output
    main, pl = out.read_text(), (ledger["tmp"] / "receipts" / "v-pl-reference.md").read_text()
    assert "Not gate evidence and not a policy" in main and "300 resamples" in main and "seed 20261009" in main
    order = [main.index(h) for h in ("## The declaration", "## The amendment", "## Reconciliation", "## Method",
                                     "## Tables")]
    assert order == sorted(order)
    assert f"~~{vr.WITHDRAWN}~~ {vr.WITHDRAWN_MARK}" in main
    for x in ("(a) What was known.", "(e) How to read it.", "The receipt describes; it tests nothing.",
              "**Reconciliation: PASS.**", "close log-loss", "cohort mean edge pp"):
        assert x in main, x
    assert "COHORT CHECK" not in main and "needs-ruling" not in main and "Cohort check" not in main
    for h in ("### PD", "### SA", "### pooled", "The 5-and-over row by the value outcome's kind"):
        assert h in main
    assert "reconciliation PD   reproduces" in r.output and "FLAGGED" not in r.output
    # the PL page: its own file, PL only, no reconciliation, #92 named as not this
    assert "PL's live read (#92) stands as declared and is not this" in pl and "### PL" in pl
    assert "### PD" not in pl and "1 without a full fdcuk_close" in pl and "## Reconciliation" not in pl
    with session_scope() as s:                               # nothing written to the DB
        assert s.execute(select(Match).where(Match.season.in_(SEASONS))).scalars().first() is not None


def test_pl_page_walks_pl_with_the_gates_walk(ledger, world):
    data = vr.build(n_boot=100)
    pl = data["pl"]
    res = vr._walk("PL", PL_SEASONS, PARAMS)
    assert pl["n_scored"] == len(res) and pl["n_unpriced"] == (1 if world["unpriced_pl"] in
                                                               {r["match_id"] for r in res} else 0)
    assert pl["tables"]["order"] == ["PL"]
    tot = sum(pl["tables"]["main"]["PL"][(b, t)]["n"] for b, _, _ in vr.BUCKETS[:4] for t in (True, False))
    assert tot == pl["n_priced"]
