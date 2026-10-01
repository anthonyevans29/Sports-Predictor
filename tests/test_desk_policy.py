"""F1 — policy in the export (#151; defaults RULED 2026-10-01). The Python
port of the Cockpit Desk v1.1: JS semantics, hand cases from the ruled policy,
the ruled defaults (counts parameter / ledger summary, as-of-export clock),
the export hook (OFF by default; --desk / SP_DESK_CALLS=1), and the CLI
receipt. Row-for-row parity against the JS lives in
scripts/desk_parity_verify.py (headless Chromium)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.walters import desk_policy as dp

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
NOW_MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))


def ko(minutes):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def row(home, p_home, *, fair_h=None, books=None, bid=None, ask=None, when=30, stage="regular", comp="MLB",
        tier="lean", **kw):
    mk = {"bookmaker_count": books if books is not None else (9 if fair_h is not None else 0)}
    if fair_h is not None:
        mk["fair_prob"] = {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}
    r = {"home_team": home, "away_team": f"{home} away", "utc_date": ko(when), "competition": comp, "stage": stage,
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": tier},
         "market": mk, "kalshi_bid": bid, "kalshi_ask": ask}
    r.update(kw)
    return r


def calls(doc, counts=None):
    ev = dp.evaluate(doc, NOW_MS, counts)
    return {r["home"]: c for r, c in ev["calls"]}


def test_js_semantics():
    assert dp.js_fixed(0.125, 2) == "0.13" and dp.js_fixed(13.35, 1) == "13.3" and dp.js_fixed(1.005, 2) == "1.00"
    assert dp.js_fixed(-0.04, 1) == "-0.0" and dp.js_fixed(-0.0, 1) == "0.0"
    assert (dp.js_str(5.0), dp.js_str(0.25), dp.js_str(dp.INF), dp.js_str(None)) == ("5", "0.25", "Infinity", "null")
    assert dp.js_round(2.5) == 3 and dp.js_round(-2.5) == -2
    assert dp.utc_ms("2026-10-01T18:00:00") == NOW_MS == dp.utc_ms("2026-10-01T18:00:00Z")   # naive = UTC (#178)
    assert dp.utc_ms("2026-10-01T14:00:00-04:00") == NOW_MS and dp.utc_ms("") != dp.utc_ms("")


def test_ruled_policy_hand_cases():
    doc = {"sport": "mlb", "predictions": [
        row("Books1u", 0.65, fair_h=0.56),                                   # 9pp, books → PLAY 1u
        row("NearFloor", 0.60, fair_h=0.556),                                # 4.4pp → half (near floor)
        row("Floor", 0.58, fair_h=0.56),                                     # 2pp → PASS floor
        row("Thin", 0.58, fair_h=0.56, books=2),                             # floor on 2 books → noref
        row("Big", 0.80, fair_h=0.60),                                       # 20pp ≥ 15 → caution half
        row("Post", 0.65, fair_h=0.56, stage="postseason"),                  # postseason half (0/30)
        row("KO", 0.65, bid=0.55, ask=0.57),                                 # kalshi-only mid .56 → 0.5u
        row("KOEarly", 0.65, bid=0.55, ask=0.57, when=180),                  # before T-60 → noref
        row("KOWide", 0.65, bid=0.54, ask=0.57),                             # 3c spread → noref
        row("KOPost", 0.65, bid=0.55, ask=0.57, stage="postseason"),         # 0.5 × 0.5 = 0.25u
    ]}
    c = calls(doc)
    assert (c["Books1u"]["call"], c["Books1u"]["units"]) == ("PLAY", 1)
    assert c["NearFloor"]["units"] == 0.5 and "near-floor half units" in c["NearFloor"]["tags"]
    assert (c["Floor"]["call"], c["Floor"]["passKind"]) == ("PASS", "floor")
    assert c["Thin"]["passKind"] == "noref" and c["Thin"]["reasons"][-1] == "books 2 < 3 → thin reference"
    assert c["Big"]["units"] == 0.5 and c["Big"]["cls"] == "caution"
    assert c["Post"]["units"] == 0.5 and "postseason → half units until 30 graded (0/30)" in c["Post"]["reasons"]
    assert c["KO"]["kalOnly"] and c["KO"]["units"] == 0.5 and c["KO"]["mktRef"] == 0.56
    assert c["KO"]["reasons"][0] == "kalshi-only reference: mid 0.560 (bid 0.55 / ask 0.57, spread 2c)"
    assert c["KOEarly"]["passKind"] == "noref" and "before T-60" in c["KOEarly"]["reasons"][0]
    assert "Kalshi spread 3c > 2c" in c["KOWide"]["reasons"][0]
    assert c["KOPost"]["units"] == 0.25
    # ruled default (1): counts are a parameter — 31 graded lifts the postseason half
    assert calls(doc, {"postseason_graded": 31})["Post"]["units"] == 1


def test_nfl_quarantine_qb_and_soccer_ladder():
    nfl = {"sport": "nfl", "predictions": [
        row("Quar", 0.70, fair_h=0.50, market_divergence_pp=20.0, quarantine=True, comp=None),
        row("QB", 0.65, fair_h=0.56, comp=None, input_quality={"injuries": {"home": {"qb_listed": ["Q. B."]}}}),
    ]}
    c = calls(nfl)
    assert c["Quar"]["call"] == "PASS" and c["Quar"]["shadowUnits"] == 0.5
    assert c["Quar"]["reasons"] == ["QUARANTINE 20pp — contract: never a straight play"]
    assert c["QB"]["units"] == 0.5 and "QB-flagged (Q. B.) → half units" in c["QB"]["reasons"]
    soc = {"sport": "soccer", "predictions": [{
        "home_team": "Home FC", "away_team": "Away FC", "utc_date": ko(300), "competition": "PL",
        "prediction": {"probabilities": {"home_win": 0.20, "draw": 0.25, "away_win": 0.55}},
        "market": {"bookmaker_count": 8, "fair_prob": {"HOME": 0.35, "DRAW": 0.25, "AWAY": 0.40}}}]}
    s = calls(soc)["Home FC"]
    assert calls({"sport": "soccer", "predictions": [dict(soc["predictions"][0], prediction={
        "probabilities": {"home_win": 0.25, "draw": 0.30, "away_win": 0.45}})]})["Home FC"]["reasons"] == [
        "pick prob 0.450 < 0.5"]                                             # soccer pMin 0.50
    assert s["call"] == "LADDER" and s["units"] == 0.5 and "double-chance (X2)" in s["reasons"][1]


def test_value_shadow_and_venue():
    doc = {"sport": "nfl", "predictions": [row("Fav", 0.55, fair_h=0.70, comp=None)]}   # dog +15pp
    v = dp.evaluate(doc, NOW_MS)["values"][0][1]
    assert (v["side"], v["role"]) == ("AWAY", "dog") and v["reason"].startswith("value on dog: +15.0pp")
    fx = {"competition_code": "NHL", "fixtures": [
        {"home_team": "H", "away_team": "A", "utc_date": ko(120), "status": "scheduled",
         "market": {"bookmaker_count": 6, "fair_prob": {"HOME": 0.60, "AWAY": 0.40}},
         "kalshi": {"status": "two_sided", "prob": {"HOME": 0.52, "AWAY": 0.48}}},
        {"home_team": "F", "away_team": "G", "utc_date": ko(-60), "status": "finished"}]}   # skipped
    ven = dp.evaluate(fx, NOW_MS)["venue"]
    assert len(ven) == 1 and ven[0][1]["eligible"] and ven[0][1]["reason"].endswith("underprices by 8.0pp")


def test_js_truthiness_and_shadow_docs():
    # JS: [] is truthy — an empty predictions list never falls through to fixtures
    assert dp.normalize({"predictions": [], "fixtures": [{"home_team": "x", "utc_date": ko(5)}]}) == []
    assert dp.normalize({"engine": "model_shadow", "predictions": [row("S", 0.6, fair_h=0.5)]}) == []


def test_ledger_summary_read_and_annotate(tmp_path):
    assert dp.read_ledger_summary(None) == ({k: 0 for k in dp.COUNT_KEYS}, "default 0 (no ledger summary)")
    p = tmp_path / "ledger_summary.json"
    p.write_text(json.dumps({"kind": "bd_ledger_summary_v1", "generated_at": "2026-10-01T12:00:00Z",
                             "counts": {"postseason_graded": 12, "value_shadow_graded": 3, "kalshi_only_graded": 1}}))
    counts, src = dp.read_ledger_summary(str(p))
    assert counts == {"postseason_graded": 12, "value_shadow_graded": 3, "kalshi_only_graded": 1}
    assert "generated 2026-10-01T12:00:00Z" in src
    p.write_text(json.dumps({"kind": "other", "counts": {}}))
    assert dp.read_ledger_summary(str(p))[1].startswith("default 0 (not a")
    doc = dp.annotate({"sport": "mlb", "predictions": [row("Post", 0.65, fair_h=0.56, stage="postseason")]},
                      now=NOW, counts=counts, counts_source=src)
    d = doc["predictions"][0]["desk"]
    assert doc["desk_meta"]["as_of"] == "2026-10-01T18:00:00Z" and doc["desk_meta"]["counts"]["postseason_graded"] == 12
    assert (d["call"], d["units"], d["reference"]) == ("PLAY", 0.5, "books")
    assert d["reason"] == " · ".join(d["reasons"]) and "(12/30)" in d["reason"]


def test_maybe_annotate_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(dp.DESK_ENV, raising=False)
    doc = {"sport": "mlb", "predictions": [row("X", 0.65, fair_h=0.56)]}
    assert "desk_meta" not in dp.maybe_annotate(json.loads(json.dumps(doc)))
    monkeypatch.setenv(dp.DESK_ENV, "1")
    out = dp.maybe_annotate(json.loads(json.dumps(doc)), summary_path=str(tmp_path / "absent.json"))
    assert out["desk_meta"]["counts_source"] == "default 0 (no ledger summary)" and out["predictions"][0]["desk"]


@pytest.fixture
def fixtures_world():
    init_db()
    kick = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None, microsecond=0)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "DESKX")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NHL, code="DESKX", name="desk test", area="Testland", type="LEAGUE")
            t = [Team(sport=Sport.NHL, name=f"DESKX club {i}") for i in range(2)]
            s.add(comp)
            s.add_all(t)
            s.flush()
            m = Match(sport=Sport.NHL, competition_id=comp.id, season="2026", utc_date=kick,
                      status=MatchStatus.SCHEDULED, home_team_id=t[0].id, away_team_id=t[1].id)
            s.add(m)
            s.flush()
            for sel, p in (("HOME", 0.55), ("AWAY", 0.45)):
                s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=p, n_books=1,
                                   captured_at=kick - timedelta(hours=3), source="kalshi"))
    return "DESKX"


def test_fixtures_export_hook_and_cli_receipt(fixtures_world, tmp_path, monkeypatch):
    from src.walters.export import export_fixtures
    monkeypatch.delenv(dp.DESK_ENV, raising=False)
    off = json.loads(open(export_fixtures(fixtures_world, out_dir=str(tmp_path))).read())
    assert "desk_meta" not in off and all("desk" not in f for f in off["fixtures"])
    on = json.loads(open(export_fixtures(fixtures_world, out_dir=str(tmp_path), desk=True)).read())
    d = on["fixtures"][0]["desk"]
    assert on["desk_meta"]["policy_version"] == "v1.1"
    assert (d["engine"], d["call"], d["pass_kind"], d["reason"]) == ("venue_edge", "PASS", "noref",
                                                                     "single venue — no pair")
    from cli import cli
    monkeypatch.chdir(tmp_path)
    out = CliRunner().invoke(cli, ["export-fixtures", "--competition", fixtures_world, "--desk"]).output
    assert "desk v1.1 as of" in out and "1 rows → PASS 1" in out and "default 0 (no ledger summary)" in out
