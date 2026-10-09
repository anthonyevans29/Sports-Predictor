"""ncaa-elo-v1r GATE + CONFIRMATION (ARCHITECT 2026-10-08, addendum 11 item 3, PR B). Synthetic data only: no test
reads data/, runs the real gate or touches the real registry (every registry write goes to a tmp ledger).
Pins: --preflight scores nothing and prints the per-season census / neutral count / coverage / D4 baseline, and ends
with the stream fingerprint (addendum 17 item 1); the run refuses without 2024 + 2025 coverage (each season named),
without the word, without the fingerprint, on a fingerprint that no longer matches the stream, on a scored set under
500 (addendum 17 item 2) and on an undefined D4 baseline (addendum 21 item 4 (2)), each before the reservation with nothing written; no OPEN_ITEMS gate; the reservation is
written after the #329 guard and before the first game is scored, carrying the word and the fingerprint; one run; each
D5 criterion fails on its
own (margin tie rejects; level; slope incl. non-convergence; rating range); no 2026 game scored; non-regular 2025
walked, never scored; the D4 baseline is 2024 'regular' non-neutral; D7 freeze / substitute / pending / record and
the CONFIRMED logic with the 0.6931 bar."""
import json
import math
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.walters import ncaa_backtest as nb
from src.walters import ncaa_v1r_gate as vg
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
AT = datetime(2026, 10, 9, 12)


def G(mid, h, a, season, at, hs, as_, neutral=False, st="regular"):
    return nb.Game(h, a, season, at, hs, as_, "FBS (Division I-A)", neutral=neutral, label_source="cfbd",
                   orientation="same", match_id=mid, season_type=st, cfbd_id=mid + 10_000, cfbd_season=season,
                   label_fetched_at=AT)


def _cov(ok=("2024", "2025", "2026"), present=("2024", "2025", "2026")):
    from src.ingestion import ncaa_cfbd as nc
    return {s_: {"season": s_, "payload": f"p{s_}", "reason": None, "unlabelled": [], "fetched_at": AT,
                 "current": 100 if s_ in ok else 80, **nc.fbs_coverage(100, 100 if s_ in ok else 80)}
            for s_ in present}


class Fake:
    """A predictor whose probabilities and ratings the test sets; it logs every call."""

    def __init__(self, p_of, ratings=None):
        self.p_of, self._r, self.calls = p_of, ratings or {1: 1500.0, 2: 1500.0}, []

    def predict(self, g):
        self.calls.append(("predict", g.match_id))
        return self.p_of(g)

    def update(self, g):
        self.calls.append(("update", g.match_id))

    def ratings(self):
        return dict(self._r)


def stream(n_test=600, groups=((0.8, 8), (0.2, 2)), base_wins=(5, 10), extra=(), block=10):
    """2024 warm-up (base_wins[0] home wins of base_wins[1] 'regular' non-neutral games) + n_test 2025 'regular'
    games in blocks of 10 per group: a block whose model p is p_true has `wins` home wins. Returns (games, p_of)."""
    t, mid, games, p = datetime(2024, 9, 1), 0, [], {}
    for i in range(base_wins[1]):
        mid += 1
        games.append(G(mid, 1, 2, "2024", t + timedelta(hours=mid), 21 if i < base_wins[0] else 7, 14))
    t = datetime(2025, 9, 1)
    k = 0
    while k < n_test:
        for prob, wins in groups:
            for i in range(block):
                if k >= n_test:
                    break
                mid += 1
                games.append(G(mid, 1, 2, "2025", t + timedelta(hours=mid), 21 if i < wins else 7, 14))
                p[mid] = prob
                k += 1
    games += list(extra)
    games.sort(key=lambda g: (g.utc_date, g.match_id))
    return games, (lambda g: p.get(g.match_id, 0.5))


def calibrated():
    games, p_of = stream()
    return games, Fake(p_of)


# --------------------------------------------------------------------------------------------- D5 (pure) --

def test_a_calibrated_model_passes_all_four():
    games, m = calibrated()
    r = vg.run_gate(games, m)
    assert r["n_scored"] == 600 and r["baseline_home_rate"] == 0.5
    assert r["crit_margin"] and r["crit_level"] and r["crit_spread"] and r["crit_range"], r
    assert abs(r["slope_b"] - 1) < 1e-6 and abs(r["intercept_a"]) < 1e-6
    assert r["verdict"].startswith("PASS")


def test_under_500_scored_is_invalid():
    games, p_of = stream(n_test=499)
    r = vg.run_gate(games, Fake(p_of))
    assert r["n_scored"] == 499 and r["verdict"].startswith("INVALID — 499 scored games < 500")
    games, p_of = stream(n_test=500)
    assert vg.run_gate(games, Fake(p_of))["verdict"].startswith("PASS")


def test_margin_is_strict_and_a_tie_with_the_bar_rejects():
    base = 0.693147
    bar = base - vg.LL_MARGIN
    assert not (bar < base - vg.LL_MARGIN)                    # equality: rejected
    assert math.nextafter(bar, 0) < base - vg.LL_MARGIN       # one ulp under: passes
    # in the gate: a calibrated but weak model (0.55 / 0.45) beats the baseline by less than 0.010: (1) only
    games, p_of = stream(groups=((0.55, 11), (0.45, 9)), block=20)
    r = vg.run_gate(games, Fake(p_of))
    assert r["ll_baseline"] - 0.010 < r["ll_model"] < r["ll_baseline"]
    assert (r["crit_margin"], r["crit_level"], r["crit_spread"], r["crit_range"]) == (False, True, True, True)
    assert r["verdict"] == "FAIL — (1) margin"


def test_margin_tie_inside_run_gate_rejects(monkeypatch):
    """The exact equality case through run_gate's own arithmetic: with LL_MARGIN set to (baseline − model), which is
    exact (Sterbenz), the bar equals the model log-loss and (1) rejects; one ulp less margin passes."""
    games, m = calibrated()
    r0 = vg.run_gate(games, m)
    d = r0["ll_baseline"] - r0["ll_model"]
    monkeypatch.setattr(vg, "LL_MARGIN", d)
    r = vg.run_gate(games, Fake(m.p_of))
    assert r["bar"] == r["ll_model"] and r["crit_margin"] is False and r["verdict"] == "FAIL — (1) margin"
    monkeypatch.setattr(vg, "LL_MARGIN", r0["ll_baseline"] - math.nextafter(r0["ll_model"], 1))   # bar one ulp above
    r = vg.run_gate(games, Fake(m.p_of))
    assert r["bar"] == math.nextafter(r["ll_model"], 1) and r["crit_margin"] is True


def test_level_fails_on_its_own():
    games, p_of = stream(groups=((0.86, 8), (0.26, 2)))       # 6pp too high, slope ~0.97
    r = vg.run_gate(games, Fake(p_of))
    assert abs(r["level_gap"] - 0.06) < 1e-9
    assert (r["crit_margin"], r["crit_level"], r["crit_spread"], r["crit_range"]) == (True, False, True, True)
    assert r["verdict"] == "FAIL — (2) level"


def test_slope_fails_on_its_own_and_non_convergence_fails():
    games, p_of = stream(groups=((0.95, 8), (0.05, 2)))       # overconfident: b ~0.47
    r = vg.run_gate(games, Fake(p_of))
    assert r["slope_b"] < 0.8 and abs(r["level_gap"]) < 1e-9
    assert (r["crit_margin"], r["crit_level"], r["crit_spread"], r["crit_range"]) == (True, True, False, True)
    games, p_of = stream(groups=((0.8, 10), (0.2, 0)))        # separable: the ML fit never converges
    r = vg.run_gate(games, Fake(p_of))
    assert r["slope_b"] is None and r["fit_converged"] is False and r["intercept_a"] is None
    assert (r["crit_margin"], r["crit_level"], r["crit_spread"], r["crit_range"]) == (True, True, False, True)
    assert r["verdict"] == "FAIL — (3) spread"


def test_range_fails_on_its_own():
    games, p_of = stream()
    for bad in (2000.0001, 999.9999):
        r = vg.run_gate(games, Fake(p_of, {1: 1500.0, 2: bad}))
        assert (r["crit_margin"], r["crit_level"], r["crit_spread"], r["crit_range"]) == (True, True, True, False)
        assert r["outliers"] == [[2, bad]] and r["verdict"] == "FAIL — (4) range"
    r = vg.run_gate(games, Fake(p_of, {1: 1000.0, 2: 2000.0}))  # the bounds are inside
    assert r["crit_range"] is True


def test_d5_level_and_slope_are_the_design_receipts_functions():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rcpt", ROOT / "scripts" / "ncaa_v1r_design_receipt.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.logistic_slope is nb.logistic_slope
    assert (m.CLIP, m.LEVEL_TOL, m.SLOPE_TOL) == (1e-6, 0.05, 0.20)
    src = (ROOT / "scripts" / "ncaa_v1r_design_receipt.py").read_text()
    assert "nb.level_ok(" in src and "nb.slope_ok(" in src and "np.linalg.solve" not in src
    assert nb.level_ok(0.05) and not nb.level_ok(0.0501) and nb.slope_ok(0.8) and not nb.slope_ok(None)


# --------------------------------------------------------------------------------------------- D3, D4 --

def test_2026_never_scored_and_non_regular_2025_walked_not_scored():
    post = G(9001, 1, 2, "2025", datetime(2026, 1, 5), 30, 20, st="postseason")
    none_ = G(9002, 2, 1, "2025", datetime(2025, 12, 1), 30, 20, st=None)
    early26 = G(9003, 1, 2, "2026", datetime(2025, 12, 20), 30, 20)     # a 2026 game before the last 2025 one
    late26 = G(9004, 2, 1, "2026", datetime(2026, 9, 5), 30, 20)
    games, p_of = stream(extra=(post, none_, early26, late26))
    m = Fake(p_of)
    r = vg.run_gate(games, m)
    predicted = {mid for k, mid in m.calls if k == "predict"}
    updated = {mid for k, mid in m.calls if k == "update"}
    assert not predicted & {9001, 9002, 9003, 9004} and len(predicted) == 600
    assert {9001, 9002, 9003} <= updated and 9004 not in updated        # the walk ends after the last 2025 game
    assert r["walked_not_scored_2025_by_season_type"] == {"(none)": 1, "postseason": 1}
    assert r["walked_2026"] == 1 and r["not_walked_after_last_2025"] == 1
    assert set(r["scored_ids"]) == {g.match_id for g in games if g.season == "2025" and g.season_type == "regular"}
    assert m.calls[-1] == ("update", 9001)                              # ratings read after the last 2025 game


def test_baseline_is_2024_regular_non_neutral_frozen_before_scoring():
    t = datetime(2024, 9, 1)
    g24 = [G(1, 1, 2, "2024", t, 21, 14), G(2, 1, 2, "2024", t + timedelta(1), 7, 14),
           G(3, 1, 2, "2024", t + timedelta(2), 21, 14, neutral=None),          # no flag: non-neutral (D1), in
           G(4, 1, 2, "2024", t + timedelta(3), 21, 14, neutral=True),          # neutral: out
           G(5, 1, 2, "2024", t + timedelta(4), 21, 14, st="postseason"),       # not 'regular': out
           G(6, 1, 2, "2024", t + timedelta(5), 21, 14, st="Regular"),          # not EXACTLY 'regular': out
           G(7, 1, 2, "2025", datetime(2025, 9, 1), 7, 14)]                     # 2025: never in the baseline
    assert vg.d4_baseline(g24) == (2 / 3, 3)
    neutral = G(8, 1, 2, "2025", datetime(2025, 9, 2), 21, 14, neutral=True)
    assert vg.baseline_p(neutral, 2 / 3) == 0.5 and vg.baseline_p(g24[-1], 2 / 3) == 2 / 3
    # frozen first: the 2025 results never move it
    games, p_of = stream(base_wins=(7, 10))
    r = vg.run_gate(games, Fake(p_of))
    assert r["baseline_home_rate"] == 0.7 and r["baseline_n"] == 10
    assert abs(r["ll_baseline"] - (-(0.5 * math.log(0.7) + 0.5 * math.log(0.3)))) < 1e-12


def test_reported_quantities_are_present_and_never_gated():
    games, m = calibrated()
    r = vg.run_gate(games, m)
    for k in ("bands_79", "ll_const", "brier_model", "brier_baseline", "intercept_a", "cold_starts", "ll_neutral",
              "ll_nonneutral", "n_neutral", "n_nonneutral"):
        assert k in r
    assert abs(r["ll_const"] - math.log(2)) < 1e-12
    assert r["cold_starts"] == 0                               # both teams played in 2024
    json.dumps(vg.result_record(r, "go"))


def test_real_wrapper_walk_matches_a_hand_replay():
    """The gate's default model is the shared D1 wrapper: a neutral game priced with home advantage 0."""
    games, _ = stream(n_test=20)
    games.append(G(9999, 2, 1, "2025", datetime(2025, 12, 31), 10, 3, neutral=True))
    r = vg.run_gate(games)
    ref = nb.NeutralRuleElo()
    for g in games:
        ref.update(g)
    assert r["rating_min"] == min(ref.ratings().values()) and r["n_neutral"] == 1 and r["neutral_updates"] == 1


# --------------------------------------------------------------------------------------------- D6: the run --

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A tmp copy of the real registry; every registry read/write in these tests goes there."""
    p = tmp_path / "experiments.json"
    shutil.copy(ROOT / "docs" / "registry" / "experiments.json", p)
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(vg, "RESERVATION", str(tmp_path / "ncaa-elo-v1r.started.json"))
    return p


def _v(games=None):
    return nb.v1r_stream(games if games is not None else calibrated()[0], {}, {s_: AT for s_ in nb.V1R_SEASONS})


def FP(games=None):
    """The fingerprint --preflight would print for this synthetic stream."""
    return vg.stream_fingerprint(_v(games).games)[0]


def _ready(monkeypatch, games=None, cov=None):
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: cov or _cov())
    seen = {}

    def load(*a, **k):
        seen["reserved_at_read"] = os.path.exists(vg.reservation_path())
        seen["reads"] = seen.get("reads", 0) + 1
        return _v(games)
    monkeypatch.setattr(nb, "load_v1r_stream", load)
    return seen


def test_run_refuses_without_coverage_naming_each_season_before_any_read(ledger, monkeypatch):
    seen = _ready(monkeypatch, cov=_cov(ok=(), present=("2025",)))
    with pytest.raises(vg.GateRefused) as ex:
        vg.run("go", FP())
    msg = str(ex.value)
    assert "2024 (not computed)" in msg and "2025 80.0% (80/100)" in msg and "2026" not in msg.split("covered: ")[1]
    assert not seen and not os.path.exists(vg.reservation_path())
    seen = _ready(monkeypatch, cov=_cov(ok=("2024", "2025"), present=("2024", "2025")))   # 2026 not needed
    vg.run("go", FP())
    assert seen["reads"] == 1


def test_run_refuses_without_the_word_or_the_fingerprint_before_any_read(ledger, monkeypatch):
    seen = _ready(monkeypatch)
    for word in (None, "", "   "):
        with pytest.raises(vg.GateRefused, match="architect's word"):
            vg.run(word, FP())
    for fp in (None, "", "   "):
        with pytest.raises(vg.GateRefused, match="--stream-fingerprint"):
            vg.run("go", fp)
    assert not seen and not os.path.exists(vg.reservation_path())


def test_there_is_no_open_items_gate(ledger, monkeypatch):
    """Addendum 17 item 1 (verbatim): "There is no OPEN_ITEMS gate: one lock is enough, and this is the one that
    leaves my word in the record." The shipped code runs on the word and the fingerprint alone."""
    assert not hasattr(vg, "OPEN_ITEMS")
    assert "OPEN_ITEMS" not in vg.run.__code__.co_names + vg.preflight_lines.__code__.co_names
    _ready(monkeypatch)
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: "stub")
    assert vg.run("go", FP())["n_scored"] == 600


def test_reservation_after_the_guard_and_the_fingerprint_check_and_before_the_first_score(ledger, monkeypatch):
    seen = _ready(monkeypatch)
    order = []

    def guard(eid, no_fetch=False, repo=None):
        order.append(("guard", eid, no_fetch, os.path.exists(vg.reservation_path())))
        return "cross-ref guard: stub"
    monkeypatch.setattr(reg, "cross_ref_guard", guard)
    real = vg.run_gate

    def gate(games, model=None):
        order.append(("score", os.path.exists(vg.reservation_path())))
        return real(games, model)
    monkeypatch.setattr(vg, "run_gate", gate)
    fp = FP()
    r = vg.run("the word", fp, no_fetch=True)
    assert order == [("guard", "ncaa-elo-v1r", True, False), ("score", True)]
    assert seen == {"reserved_at_read": False, "reads": 1}           # loaded once, before the reservation
    saved = json.load(open(vg.reservation_path()))
    assert saved["id"] == "ncaa-elo-v1r" and saved["architect_word"] == "the word" and saved["guard"]
    assert saved["stream_fingerprint"] == fp and saved["scored_set_n"] == 600
    assert r["stream_fingerprint"] == fp


def test_guard_refusal_means_no_reservation_and_nothing_scored(ledger, monkeypatch):
    _ready(monkeypatch)

    def refuse(eid, no_fetch=False, repo=None):
        raise reg.CrossRefRefused(f"{eid}: a reservation on ref remotes/origin/laptop/x at commit abc")
    monkeypatch.setattr(reg, "cross_ref_guard", refuse)

    def no(*a, **k):
        raise AssertionError("scored after a guard refusal")
    monkeypatch.setattr(vg, "run_gate", no)
    with pytest.raises(vg.GateRefused, match="laptop/x at commit abc"):
        vg.run("go", FP())
    assert not os.path.exists(vg.reservation_path())


def test_a_mismatched_fingerprint_refuses_before_the_reservation(ledger, monkeypatch):
    """Addendum 17 item 1: "refuses, before the reservation, when the stream it is about to walk no longer matches"."""
    import cli
    before = Path(ledger).read_bytes()
    games = calibrated()[0]
    old = FP(games)
    changed = [g if g.match_id != 15 else nb.Game(**{**g.__dict__, "home_score": 3}) for g in games]
    _ready(monkeypatch, games=changed)
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")

    def no(*a, **k):
        raise AssertionError("scored on a stream that does not match the word")
    monkeypatch.setattr(vg, "run_gate", no)
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--architect-word", "Run it.", "--stream-fingerprint", old])
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output and "no longer matches" in res.output and old in res.output
    assert FP(changed) in res.output
    assert not os.path.exists(vg.reservation_path()) and not guarded
    assert Path(ledger).read_bytes() == before and not os.path.exists(reg.IDS_DIR)
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--architect-word", "Run it."])     # required
    assert res.exit_code == 2 and "--stream-fingerprint" in res.output
    assert not os.path.exists(vg.reservation_path())


def test_a_scored_set_under_500_refuses_before_the_reservation_and_records_nothing(ledger, monkeypatch):
    """Addendum 17 item 2 (verbatim): "If it numbers under 500 the run refuses before the reservation and records
    nothing; no game has been scored." Level scores are not in the scored set."""
    import cli
    before = Path(ledger).read_bytes()
    games, _ = stream(n_test=500)
    level = nb.Game(**{**games[-1].__dict__, "home_score": 14, "away_score": 14})   # a level score: skipped (D2)
    games = games[:-1] + [level]
    assert len(vg.scored_set(_v(games).games)) == 499
    _ready(monkeypatch, games=games)
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")

    def no(*a, **k):
        raise AssertionError("a game was scored")
    monkeypatch.setattr(vg, "run_gate", no)
    monkeypatch.setattr(nb.NeutralRuleElo, "predict", no)
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--architect-word", "Run it.", "--stream-fingerprint",
                                       FP(games)])
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output and "499 < 500" in res.output and "the bar does not move" in res.output
    assert not os.path.exists(vg.reservation_path()) and not guarded
    assert Path(ledger).read_bytes() == before and not os.path.exists(reg.IDS_DIR)
    assert reg.get("ncaa-elo-v1r", str(ledger))["run"] is None
    games, _ = stream(n_test=500)                                   # exactly 500: the run proceeds
    _ready(monkeypatch, games=games)
    monkeypatch.setattr(vg, "run_gate", lambda g, model=None: {"n_scored": 500})
    assert vg.run("go", FP(games))["n_scored"] == 500 and os.path.exists(vg.reservation_path())


def test_an_undefined_d4_baseline_refuses_before_the_reservation_and_records_nothing(ledger, monkeypatch):
    """Addendum 21 item 4 (2) (verbatim): "When 2024 has no non-neutral regular game, D4 is undefined and nothing can
    be scored: the run refuses before the reservation and records nothing, as it does under 500 games. It is not an
    INVALID run and the read is not spent." 600 scored 2025 games, so only D4 can refuse."""
    import cli
    before = Path(ledger).read_bytes()
    t = datetime(2024, 9, 1)
    only = [G(9001, 1, 2, "2024", t, 21, 14, neutral=True),                    # 2024: neutral and non-'regular' only
            G(9002, 1, 2, "2024", t + timedelta(1), 21, 14, st="postseason")]
    games, _ = stream(base_wins=(0, 0), extra=only)
    assert vg.d4_baseline(_v(games).games) == (None, 0) and len(vg.scored_set(_v(games).games)) == 600
    _ready(monkeypatch, games=games)
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")

    def no(*a, **k):
        raise AssertionError("a game was scored")
    monkeypatch.setattr(nb.NeutralRuleElo, "predict", no)
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--architect-word", "Run it.", "--stream-fingerprint",
                                       FP(games)])
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output and "D4" in res.output and "undefined" in res.output
    assert "not an INVALID run" in res.output and "INVALID —" not in res.output
    assert not os.path.exists(vg.reservation_path()) and not guarded
    assert Path(ledger).read_bytes() == before and not os.path.exists(reg.IDS_DIR)
    assert reg.get("ncaa-elo-v1r", str(ledger))["run"] is None
    with pytest.raises(vg.GateRefused, match="D4"):                    # the pure walk scores nothing either
        vg.run_gate(games)
    _ready(monkeypatch, games=calibrated()[0])                          # the read is not spent: a later run proceeds
    monkeypatch.setattr(vg, "run_gate", lambda g, model=None: {"n_scored": 600})
    assert vg.run("go", FP())["n_scored"] == 600 and os.path.exists(vg.reservation_path())


def test_the_fingerprint_is_stable_and_names_the_walked_stream_with_every_field_the_gate_reads():
    games = calibrated()[0]
    a, n = vg.stream_fingerprint(_v(games).games)
    assert len(a) == 64 and int(a, 16) >= 0 and n == 610
    assert vg.stream_fingerprint(_v(list(reversed(games))).games) == (a, n)     # same stream, any load order
    assert vg.stream_fingerprint(_v(games).games)[0] == a                       # deterministic
    assert vg.FINGERPRINT_FIELDS == ("match_id", "utc_date", "season", "season_type", "home_id", "away_id",
                                     "home_score", "away_score", "neutral", "label_source")
    g0 = next(g for g in games if g.season == "2025")
    for field, value in (("match_id", 99_999), ("utc_date", g0.utc_date + timedelta(seconds=1)),
                         ("season_type", "postseason"), ("home_id", 7), ("away_id", 7), ("home_score", 99),
                         ("away_score", 0), ("neutral", True), ("label_source", "matches")):
        g1 = nb.Game(**{**g0.__dict__, field: value})
        changed = [g1 if g is g0 else g for g in games]
        assert vg.stream_fingerprint(changed)[0] != a, field
    moved = [nb.Game(**{**g.__dict__, "season": "2024", "cfbd_season": "2024"}) if g is g0 else g for g in games]
    assert FP(moved) != a                                                        # the label season
    # a field the gate never reads does not move it; neither does a 2026 game after the last 2025 game (not walked)
    assert FP([nb.Game(**{**g.__dict__, "cfbd_id": 1, "stage": "x"}) for g in games]) == a
    late = G(9999, 1, 2, "2026", datetime(2026, 9, 5), 30, 20)
    assert FP(games + [late]) == a
    early = G(9998, 1, 2, "2026", datetime(2025, 9, 1, 0, 30), 30, 20)          # walked: before the last 2025 game
    assert FP(games + [early]) != a


def test_one_run_recorded_and_a_second_refused(ledger, monkeypatch):
    import cli
    _ready(monkeypatch)
    fp = FP()
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--architect-word", "Run it. ARCHITECT 2026-10-09",
                                       "--stream-fingerprint", fp])
    assert res.exit_code == 0, res.output
    want = vg.run_gate(calibrated()[0])["verdict"]                # the real D1 wrapper on the same stream
    assert f"VERDICT (computed; the architect rules): {want}" in res.output
    assert "recorded: 600 scored ids" in res.output
    e = reg.get("ncaa-elo-v1r", str(ledger))
    assert e["status"] == "run" and e["run"]["n_scored"] == 600
    assert e["run"]["result"]["architect_word"] == "Run it. ARCHITECT 2026-10-09"
    assert e["run"]["result"]["stream_fingerprint"] == fp                 # recorded beside the word
    saved = json.load(open(vg.reservation_path()))
    assert saved["architect_word"] == "Run it. ARCHITECT 2026-10-09" and saved["stream_fingerprint"] == fp
    ids = [int(x) for x in open(Path(reg.IDS_DIR) / "ncaa-elo-v1r.txt").read().split()]
    games = calibrated()[0]
    assert ids == sorted(g.match_id for g in games if g.season == "2025" and g.season_type == "regular")
    again = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--architect-word", "again", "--stream-fingerprint", fp])
    assert again.exit_code == 2 and "REFUSED" in again.output and "read once" in again.output
    os.remove(vg.reservation_path())                         # even without the file, the registry refuses
    with pytest.raises(vg.GateRefused, match="declared and unrun"):
        vg.run("again", fp)


def test_an_interrupted_run_spends_the_reservation(ledger, monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: "stub")

    def boom(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(vg, "run_gate", boom)
    with pytest.raises(KeyboardInterrupt):
        vg.run("go", FP())
    with pytest.raises(vg.GateRefused, match="one run, recorded or not"):
        vg.run("go", FP())


def test_preflight_scores_nothing_and_prints_census_neutral_coverage_baseline(ledger, monkeypatch):
    import cli
    before = Path(ledger).read_bytes()
    games, _ = stream(extra=(G(9001, 1, 2, "2025", datetime(2026, 1, 5), 30, 20, st="postseason", neutral=True),
                             G(9004, 2, 1, "2026", datetime(2026, 9, 5), 30, 20, st=None)))
    _ready(monkeypatch, games=games, cov=_cov(ok=("2024", "2025"), present=("2024", "2025")))

    def no(*a, **k):
        raise AssertionError("preflight scored a game")
    monkeypatch.setattr(nb.NeutralRuleElo, "predict", no)
    monkeypatch.setattr(nb.NeutralRuleElo, "update", no)
    monkeypatch.setattr(vg, "run_gate", no)
    monkeypatch.setattr(reg, "cross_ref_guard", no)
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--preflight"])
    assert res.exit_code == 0, res.output
    out = res.output
    assert "2024 (warm-up): stream 10 · by season_type regular 10 · neutral 0" in out
    assert "2025 (test (regular) + walked): stream 601 · by season_type postseason 1, regular 600 · neutral 1" in out
    assert "2026 (never scored by the gate): stream 1 · by season_type (none) 1" in out
    assert "coverage: 2024: labelled 100 / CFBD completed both-FBS 100 = 100.0%" in out
    assert "coverage: not computed" in out                                   # 2026 not in the coverage fact
    assert "D4 baseline (frozen before any test game is scored): 2024 non-neutral 'regular' home win rate " \
           "0.500000 (n 10)" in out
    assert "test set if run now: 600 2025 'regular' games" in out
    assert "gate (2024, 2025) COVERED · confirmation (2024, 2025, 2026) NOT COVERED" in out
    assert "PREFLIGHT only: nothing scored" in out
    assert "under 500 the run refuses before the reservation" in out
    assert "open items" not in out
    last = out.strip().splitlines()[-1]                                       # addendum 17 item 1: the last line
    fp, n = vg.stream_fingerprint(_v(games).games)
    assert last.startswith(f"STREAM FINGERPRINT {fp} ({n} games") and n == 611   # 2026 (Sep) not walked
    again = CliRunner().invoke(cli.cli, ["ncaa-v1r-gate", "--preflight"])
    assert again.output.strip().splitlines()[-1] == last                     # stable
    assert not os.path.exists(vg.reservation_path()) and Path(ledger).read_bytes() == before
    assert "realized" not in out and "log-loss" not in out                  # no 2025 outcome printed


def test_ncaa_backtest_is_untouched():
    """#79's ncaa-backtest stays as it is: its frozen numbers and its band rule."""
    assert (nb.TRAIN_SEASON, nb.TEST_SEASON, nb.LL_MARGIN, nb.BAND_MIN_N, nb.BAND_TOL, nb.MIN_TEST_N) == \
        ("2025", "2026", 0.010, 100, 0.05, 500)
    assert "crit_bands" in nb.run_gate.__code__.co_names


# --------------------------------------------------------------------------------------------- D7 --

VERDICT_AT = "2026-10-20T00:00:00Z"


def _confirming(ledger, rate=0.6, frozen_ids=None):
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == "ncaa-elo-v1r")
    e.update({"status": "confirming", "verdict": {"verdict": "PASS", "ruling": "PASS. ARCHITECT", "at": VERDICT_AT},
              "run": {"run_at": "2026-10-19T00:00:00Z", "n_scored": 0, "ids_file": None, "result":
                      {"baseline_home_rate": rate}}})
    Path(ledger).write_text(json.dumps(entries, indent=2))
    if frozen_ids:
        reg.freeze_confirmation_cohort("ncaa-elo-v1r", frozen_ids, {"rule": "test"}, reg.LEDGER, reg.IDS_DIR)


@pytest.mark.parametrize("ll,ref,outcome", [
    (0.6931, 0.70, "CONFIRMED"),             # the bar is inclusive
    (0.69311, 0.70, "NOT_CONFIRMED"),        # over the bar
    (0.60, 0.60, "NOT_CONFIRMED"),           # a tie with (baseline − 0.010) fails
    (0.60, math.nextafter(0.60, 1), "CONFIRMED"),
    (0.65, 0.64, "NOT_CONFIRMED"),           # under the bar but not under the reference
])
def test_confirmed_iff_under_the_bar_and_the_reference(ledger, ll, ref, outcome):
    ids = list(range(1, 101))
    _confirming(ledger, frozen_ids=ids)
    r = {"complete": True, "cohort_state": "frozen", "pending": [], "scored_ids": ids, "log_loss": ll,
         "reference_log_loss": ref, "baseline_log_loss": ref + 0.010, "first_game_at": "2026-10-21T00:00:00Z"}
    e = vg.record_confirmation(r, "ruling verbatim")
    assert e["confirmation"]["outcome"] == outcome and e["confirmation"]["plan"]["bar"] == vg.CONFIRM_BAR == 0.6931


def test_record_refuses_an_incomplete_read(ledger):
    _confirming(ledger, frozen_ids=list(range(1, 101)))
    with pytest.raises(vg.GateRefused, match="pending, never replaced"):
        vg.record_confirmation({"complete": False, "cohort_state": "frozen", "pending": [{"id": 5}]}, "x")


def _fresh(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return db


@pytest.fixture
def world(tmp_path, monkeypatch, ledger):
    """A synthetic NCAA DB: labelled history 2024-2026 for FBS teams 0-5 (team 6 carries the same unescaped name as
    team 5: J2 merges it), team 7 never labelled; 106 fixtures after the verdict among FBS teams (some via team 6),
    one with team 7, one before the verdict."""
    from src.db.schema import (Competition, Match, MatchStatus, NCAACFBDIngestRecord, NCAACFBDLabel, Sport, Team)
    db = _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: _cov())
    w = {"fixtures": []}
    with db.session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        names = ["A", "B", "C", "D", "E", "Texas A&M", "Texas A&amp;M", "FCS"]
        t = [Team(sport=Sport.NFL, name=n) for n in names]
        s.add_all([comp, *t])
        s.flush()
        w["teams"] = [x.id for x in t]

        def match(h, a, at, status=MatchStatus.FINISHED, season="2026", raw=None):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=at, status=status,
                      home_team_id=t[h].id, away_team_id=t[a].id, stage="FBS (Division I-A)", status_raw=raw)
            s.add(m)
            s.flush()
            return m.id

        def label(s, mid, season, hs, as_, neutral=False, st="regular"):
            s.add(NCAACFBDLabel(match_id=mid, source="cfbd", source_game_id=mid, season=season, orientation="same",
                                neutral=neutral, home_score=hs, away_score=as_, fetched_at=AT, season_type=st))
        k = 0
        for season, start in (("2024", datetime(2024, 9, 1)), ("2025", datetime(2025, 9, 1)),
                              ("2026", datetime(2026, 9, 1))):
            for i in range(12):
                h, a = i % 6, (i + 1) % 6
                mid = match(h, a, start + timedelta(days=i), season=season)
                label(s, mid, season, 24 if i % 3 else 10, 17, neutral=(i == 4))
                k += 1
        w["before"] = match(0, 1, datetime(2026, 10, 19), MatchStatus.SCHEDULED)
        base = datetime(2026, 10, 21)
        for i in range(106):
            h, a = i % 6, (i + 2) % 6
            if i == 3:
                h = 6                                          # team 6 merges into team 5 (J2): eligible
            w["fixtures"].append(match(h, a, base + timedelta(hours=i), MatchStatus.SCHEDULED))
            if i == 10:
                w["fcs"] = match(7, 0, base + timedelta(hours=i, minutes=30), MatchStatus.SCHEDULED)
        for season in ("2024", "2025", "2026"):
            s.add(NCAACFBDIngestRecord(season=season, division="fbs", fetched_at=AT, payload_file="p.json",
                                       records=12, in_scope=12, joined=12, unlabelled=[]))
    w["db"], w["label"] = db, label
    _confirming(ledger, rate=0.6)
    return w


def test_freeze_takes_the_first_100_eligible_any_status_and_calls_the_guard(world, monkeypatch):
    from src.db.schema import Match, MatchStatus
    with world["db"].session_scope() as s:                      # any status enters
        s.get(Match, world["fixtures"][0]).status = MatchStatus.POSTPONED
        s.get(Match, world["fixtures"][1]).status = MatchStatus.CANCELLED
    calls = []

    def refuse(eid, no_fetch=False, repo=None):
        calls.append(eid)
        raise reg.CrossRefRefused(f"{eid}: a cohort on ref remotes/origin/laptop/y at commit def")
    monkeypatch.setattr(reg, "cross_ref_guard", refuse)
    with pytest.raises(reg.CrossRefRefused):
        vg.freeze()
    assert calls == ["ncaa-elo-v1r"] and not (Path(reg.IDS_DIR) / "ncaa-elo-v1r.cohort.txt").exists()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: "stub")
    e = vg.freeze()
    frozen = reg.frozen_cohort(e, reg.IDS_DIR)
    assert frozen == sorted(world["fixtures"][:100])            # kickoff then id; team 6 merged in; FCS and pre out
    assert world["fcs"] not in frozen and world["before"] not in frozen
    assert e["confirmation_cohort"]["basis"]["status_at_freeze"] == {"postponed": 1, "cancelled": 1, "scheduled": 98}
    with pytest.raises(vg.GateRefused, match="already frozen"):
        vg.freeze()


def test_freeze_and_read_refuse_without_2026_coverage(world, monkeypatch):
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: _cov(ok=("2024", "2025")))
    for f in (vg.freeze, vg.confirmation_read, vg.substitute):
        with pytest.raises(vg.GateRefused, match=r"2026 80\.0% \(80/100\)"):
            f()


def test_cancelled_is_substituted_finished_without_label_stays_pending(world):
    from src.db.schema import Match, MatchStatus
    vg.freeze()
    fx = world["fixtures"]
    with world["db"].session_scope() as s:
        s.get(Match, fx[5]).status = MatchStatus.CANCELLED
        s.get(Match, fx[5]).status_raw = "canceled"
        s.get(Match, fx[6]).status = MatchStatus.FINISHED          # finished, no label: pending, never replaced
        s.get(Match, fx[100]).status = MatchStatus.CANCELLED       # the next one is cancelled itself: skipped
    lines = []
    assert vg.substitute(echo=lines.append) == 1
    e = reg.get("ncaa-elo-v1r", reg.LEDGER)
    sub = e["confirmation_cohort"]["substitutions"]
    assert [(x["released"], x["replacement"], x["reason"]) for x in sub] == [(fx[5], fx[101], "CANCELED")]
    cohort = reg.frozen_cohort(e, reg.IDS_DIR)
    assert fx[6] in cohort and fx[5] not in cohort and fx[101] in cohort
    r = vg.confirmation_read()
    assert r["n"] == 0 and not r["complete"] and {"id": fx[6], "status": "finished"} in r["pending"]
    assert vg.substitute(echo=lines.append) == 0                  # nothing more to release


def test_read_scores_the_cohort_by_the_gates_replay_and_records(world):
    from src.db.schema import Match, MatchStatus
    vg.freeze()
    e = reg.get("ncaa-elo-v1r", reg.LEDGER)
    cohort = reg.frozen_cohort(e, reg.IDS_DIR)
    with world["db"].session_scope() as s:
        for i, mid in enumerate(cohort[:-1]):
            m = s.get(Match, mid)
            m.status = MatchStatus.FINISHED
            neutral = i % 10 == 0
            st = "postseason" if i % 7 == 0 else "regular"        # any season_type is scored
            world["label"](s, mid, "2026", 30 if i % 4 else 3, 20, neutral=neutral, st=st)
    r = vg.confirmation_read()
    assert r["n"] == 99 and not r["complete"] and [p["id"] for p in r["pending"]] == [cohort[-1]]
    import cli
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-confirm", "--record", "--ruling", "x"])
    assert res.exit_code == 2 and "lack a current label" in res.output
    with world["db"].session_scope() as s:
        s.get(Match, cohort[-1]).status = MatchStatus.FINISHED
        world["label"](s, cohort[-1], "2026", 31, 7)
    r = vg.confirmation_read()
    assert r["complete"] and r["n"] == 100 and sorted(r["scored_ids"]) == cohort
    # the same replay by hand: D1 wrapper over the D2 stream; baseline 0.6 / 0.5 at neutral
    v = nb.load_v1r_stream()
    m = nb.NeutralRuleElo()
    ll = base = 0.0
    for g in v.games:
        if g.match_id in set(cohort):
            ll += nb._ll(m.predict(g), g.home_win)
            base += nb._ll(0.5 if g.neutral is True else 0.6, g.home_win)
        m.update(g)
    assert abs(r["log_loss"] - ll / 100) < 1e-12 and abs(r["baseline_log_loss"] - base / 100) < 1e-12
    assert abs(r["reference_log_loss"] - (base / 100 - 0.010)) < 1e-12
    res = CliRunner().invoke(cli.cli, ["ncaa-v1r-confirm", "--record", "--ruling", "CONFIRM read. ARCHITECT"])
    assert res.exit_code == 0, res.output
    e = reg.get("ncaa-elo-v1r", reg.LEDGER)
    want = "CONFIRMED" if (ll / 100 <= 0.6931 and ll / 100 < base / 100 - 0.010) else "NOT_CONFIRMED"
    assert e["confirmation"]["outcome"] == want and e["confirmation"]["n_scored"] == 100


def test_a_labelled_cancelled_cohort_fixture_is_never_scored_and_keeps_the_read_incomplete(world):
    """Codex on #375: a cancelled cohort fixture that still carries a current label was scored and could complete the
    cohort. D7: "A cancelled fixture is released and replaced by the next eligible one": it stays pending, release
    due, until --substitute replaces it."""
    from src.db.schema import Match, MatchStatus
    vg.freeze()
    cohort = reg.frozen_cohort(reg.get("ncaa-elo-v1r", reg.LEDGER), reg.IDS_DIR)
    with world["db"].session_scope() as s:
        for mid in cohort:
            s.get(Match, mid).status = MatchStatus.FINISHED
            world["label"](s, mid, "2026", 24, 17)
        s.get(Match, cohort[7]).status = MatchStatus.CANCELLED     # cancelled, label kept
    r = vg.confirmation_read()
    assert r["n"] == 99 and cohort[7] not in r["scored_ids"] and not r["complete"]
    assert {"id": cohort[7], "status": "cancelled"} in r["pending"] and r["release_due"] == 1
    with pytest.raises(vg.GateRefused):
        vg.record_confirmation(r, "x")


def test_a_stale_orphan_is_never_eligible_at_the_freeze_or_as_a_replacement(world):
    """Codex on #375: STALE_ORPHAN rows ("never a fixture", schema) entered the cohort and the replacement pool, where
    one could stay pending for ever (only cancelled rows are released)."""
    from src.db.schema import Match, MatchStatus
    fx = world["fixtures"]
    with world["db"].session_scope() as s:
        s.get(Match, fx[2]).status = MatchStatus.STALE_ORPHAN      # inside the first 100
        s.get(Match, fx[101]).status = MatchStatus.STALE_ORPHAN    # the would-be first replacement
    e = vg.freeze()
    frozen = reg.frozen_cohort(e, reg.IDS_DIR)
    assert fx[2] not in frozen and len(frozen) == 100 and fx[100] in frozen
    with world["db"].session_scope() as s:
        s.get(Match, fx[5]).status = MatchStatus.CANCELLED
    assert vg.substitute(echo=lambda *_: None) == 1
    sub = reg.get("ncaa-elo-v1r", reg.LEDGER)["confirmation_cohort"]["substitutions"]
    assert [(x["released"], x["replacement"]) for x in sub] == [(fx[5], fx[102])]


def test_confirm_refuses_before_a_pass(ledger):
    with pytest.raises(vg.GateRefused, match="no run record"):
        vg.confirming()
