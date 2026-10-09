"""soccer-value-receipt (ARCHITECT 2026-10-09, addendum 21 item 6; Issue #383): the READ-ONLY receipt of the model's
value sides against the close. Pins, on synthetic leagues in the throwaway test DB and a TMP registry (the real
docs/registry/ is never written, data/ never touched): the value outcome (largest model p minus close p) and the top
pick, bucket assignment at market_side's tolerance, the top-pick split, the kind table (5-and-over only), the seeded
bootstrap's determinism, the flat-stake return at the close's fair price, the cohort-reproduction check (pass, fail,
decomposition), the fidelity refusal, and the PL reference page."""
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


def _rec(n, hits):
    return {"market": {"edge_cohort": {"n": n, "hits": hits}}}


def test_cohort_check_passes_only_when_the_5_plus_row_equals_the_record_and_decomposes_a_miss():
    pd = [_row(6, True, 1), _row(12, True, 0), _row(2, True, 1)]
    ok = vr.cohort_check({"PD": pd}, {"PD": _rec(2, 1)})
    assert ok["ok"] and ok["per_league"]["PD"]["five_plus"] == (2, 1) and ok["pooled"]["record"] == (2, 1)
    # a value outcome other than the top pick at 5pp+ enters the 5+ row but not the record's top-pick cohort
    pd2 = pd + [_row(7, False, 1, value="D")]
    bad = vr.cohort_check({"PD": pd2, "SA": [_row(9, True, 1, league="SA")]}, {"PD": _rec(2, 1), "SA": _rec(1, 1)})
    d = bad["per_league"]["PD"]
    assert not bad["ok"] and not d["ok"] and bad["per_league"]["SA"]["ok"]
    assert d["five_plus"] == (3, 2) and d["five_plus_top"] == (2, 1) and d["five_plus_not_top"] == (1, 1)
    assert bad["pooled"] == {"record": (3, 2), "five_plus": (4, 3)}
    # a cohort match (top-pick edge >= 5) whose value outcome is another one is counted
    r = _row(9, False, 0, value="D")
    r["top_edge_pp"] = 6.0
    assert vr.cohort_check({"PD": [r]}, {"PD": _rec(1, 0)})["per_league"]["PD"]["cohort_other_value"] == 1


def test_out_paths_default_under_docs_receipts_pl_page_beside_it_and_never_data(tmp_path):
    p, pl = vr.out_paths(None, "2026-10-09")
    assert p.endswith("docs/receipts/soccer-value-sides-2026-10-09.md")
    assert pl.endswith("docs/receipts/soccer-value-sides-2026-10-09-pl-reference.md")
    q, ql = vr.out_paths(str(tmp_path / "r.md"), "x")
    assert ql == str(tmp_path / "r-pl-reference.md")
    with pytest.raises(vr.ReceiptRefused, match="data/"):
        vr.out_paths(f"{reg.ROOT}/data/receipt.md", "x")


def test_the_declaration_is_quoted_verbatim_and_names_the_five_cohorts():
    text = " ".join(vr.DECLARATION)
    for s in ("79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of 373", "512 hits on 1,281 picks",
              "PL's live read (#92) stands as declared and is not this", "seeded bootstrap 95% interval"):
        assert s in text


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


def test_fidelity_refuses_when_the_rewalk_does_not_reproduce_the_record(ledger):
    per = json.loads(json.dumps(ledger["per"]))
    per["SA"]["market"]["edge_cohort"]["hits"] += 1
    ledger["put"](per=per)
    r = _cli("--out", str(ledger["tmp"] / "x.md"))
    assert r.exit_code == 2 and "FIDELITY" in r.output and "SA:" in r.output
    assert not (ledger["tmp"] / "x.md").exists()


def test_the_receipt_rewalks_the_scored_ids_and_checks_the_cohorts(ledger):
    data = vr.build(n_boot=200)
    assert data["n_scored"] == len(ledger["ids"]) and data["n_unpriced"] == 0
    assert data["fidelity"]["walked"] == len(ledger["ids"])
    assert data["tables"]["order"] == ["PD", "SA", "pooled"]
    chk = data["check"]
    for code in LEAGUES:
        d, coh = chk["per_league"][code], ledger["per"][code]["market"]["edge_cohort"]
        assert d["record"] == (coh["n"], coh["hits"])
        # the 5+ row's top-pick part is inside the record's cohort; the rest is the decomposition
        assert d["five_plus_top"][0] + d["cohort_other_value"] == coh["n"]
        assert d["ok"] == (d["five_plus"] == d["record"])
    pooled5 = sum(data["tables"]["main"]["pooled"][("5 and over", t)]["n"] for t in (True, False))
    assert pooled5 == chk["pooled"]["five_plus"][0]
    # deterministic end to end
    again = vr.build(n_boot=200)
    assert again["tables"]["main"]["pooled"] == data["tables"]["main"]["pooled"]


def test_cli_writes_both_pages_and_flags_a_failed_cohort_check(ledger, monkeypatch):
    out = ledger["tmp"] / "receipts" / "v.md"
    real = vr.cohort_check
    for forced, code in ((True, 0), (False, 3)):
        monkeypatch.setattr(vr, "cohort_check", lambda b, p, f=forced: {**real(b, p), "ok": f})
        r = _cli("--out", str(out))
        assert r.exit_code == code, r.output
        main, pl = out.read_text(), (ledger["tmp"] / "receipts" / "v-pl-reference.md").read_text()
        assert "Not gate evidence and not a policy" in main and "300 resamples" in main and "seed 20261009" in main
        assert "79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of 373" in main
        for h in ("### PD", "### SA", "### pooled", "The 5-and-over row by the value outcome's kind"):
            assert h in main
        assert ("COHORT CHECK FAILED" in main) is (not forced) and ("FLAGGED" in r.output) is (not forced)
        # the PL page: its own file, PL only, no cohort check, #92 named as not this
        assert "PL's live read (#92) stands as declared and is not this" in pl and "### PL" in pl
        assert "### PD" not in pl and "Cohort check" not in pl and "1 without a full fdcuk_close" in pl
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
