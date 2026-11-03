"""nfl-elo-v2 HARNESS (ARCHITECT 2026-11-02 10:35 ET, addendum 215 items 2-3). Synthetic data only: every DB is a fresh
SQLite file under tmp_path (tests/nfl_v2_world.py), every registry read and write goes to a tmp copy of the ledger,
the reservation to a tmp path; no test reads data/, runs a gate on real data or touches the real registry.

Pins: nfl-backtest's output is byte-identical to main's on a synthetic stream (the protocol was refactored into a
shared walk); the registry entry (declared, unrun, v1's constants read from code, the term null, 215's bar verbatim)
and the roadmap lane nfl-v2; the gate refuses on each missing condition (no term, both forms, an invalid value, no
word, no fingerprint, a stream that no longer matches it, a season missing, a reservation already there, a run already
recorded) with nothing written; the reservation after the #329 guard and before the first scored game, carrying the
word and the fingerprint; one run recorded as ncaa-gate records it, a second refused; the run is the frozen protocol's
code; the shrink and home-advantage forms change the walk as defined; --preflight scores nothing and prints no 2025
figure; the fit reads 2024 only (its output is identical with and without 2025 rows) and its grid minima.
Addendum 219 (ARCHITECT 2026-11-02 12:20 ET): item 4, the run refuses a null fit and a stale fit (nothing reserved,
nothing recorded) and the stream fingerprint (v2) binds the declared term; item 6, --db reads a .backup copy through
mode=ro&immutable=1 (refused under data/, when missing, and with a -wal/-shm/-journal beside it; never created, no
sidecar), the same fingerprint as the same rows through DATABASE_URL, and the ONE run refuses without --db (--preflight
keeps DATABASE_URL); items 5 and 7 in the entry and the lane. Codex P1s on #784: the run refuses constants that are not
the entry's frozen block (drifted code defaults, a differing or missing value, an extra key) before anything is read,
and a reservation is whole or absent (a failed serialisation, write, fsync or close leaves no file)."""
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

import nfl_v2_world as world
from src.walters import nfl_backtest as nb
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
EID = "nfl-elo-v2"
WORD = "Run it. ARCHITECT 2026-11-06"


def _g():
    from src.walters import nfl_v2_gate as g
    return g


def _f():
    from src.walters import nfl_v2_fit as f
    return f


# ================================================================================ nfl-backtest is unchanged --
# The lines main's run_backtest printed on this synthetic stream (captured at 69ef195d before the refactor), for the
# frozen gate and two of nfl-backtest-caps' variants. The refactor must print them byte for byte.

GOLDEN = {
    (None, None): (
        {"ok": True, "pass": False, "ll_model": 0.6572, "ll_baseline": 0.6925, "scored_games": 301},
        ["scope[nfl-backtest]: teams=32, games=603, competitions={NFL}",
         "stream: 603 games (preseason excluded) — warm-up 301 (2024), scored 301 (2025)",
         "baseline home prob (2024 realized): 0.5648",
         "log-loss: model 0.6572 vs baseline 0.6925 (need <= 0.6825) -> PASS",
         "  band 30-40%: n=36 stated 0.354 realized 0.389 gap 3.5pp -> ok",
         "  band 40-50%: n=52 stated 0.451 realized 0.404 gap 4.7pp -> ok",
         "  band 50-60%: n=44 stated 0.555 realized 0.477 gap 7.8pp -> FAIL",
         "  band 60-70%: n=62 stated 0.652 realized 0.694 gap 4.1pp -> ok",
         "  band 70-80%: n=56 stated 0.747 realized 0.696 gap 5.1pp -> ok",
         "GATE VERDICT: FAIL — REGRESSION: the live model no longer clears its frozen gate; investigate before the "
         "next predict-nfl"]),
    (0.75, None): (
        {"ok": True, "pass": False, "ll_model": 0.65, "ll_baseline": 0.6925, "scored_games": 301},
        ["scope[nfl-backtest]: teams=32, games=603, competitions={NFL}",
         "stream: 603 games (preseason excluded) — warm-up 301 (2024), scored 301 (2025)",
         "baseline home prob (2024 realized): 0.5648",
         "log-loss: model 0.6500 vs baseline 0.6925 (need <= 0.6825) -> PASS",
         "  band 30-40%: n=36 stated 0.354 realized 0.389 gap 3.5pp -> ok",
         "  band 40-50%: n=52 stated 0.451 realized 0.404 gap 4.7pp -> ok",
         "  band 50-60%: n=44 stated 0.555 realized 0.477 gap 7.8pp -> FAIL",
         "  band 60-70%: n=62 stated 0.652 realized 0.694 gap 4.1pp -> ok",
         "  band 70-80%: n=81 stated 0.739 realized 0.679 gap 6.0pp -> ok",
         "GATE VERDICT: FAIL — REGRESSION: the live model no longer clears its frozen gate; investigate before the "
         "next predict-nfl"]),
    (None, 0.9): (
        {"ok": True, "pass": False, "ll_model": 0.6538, "ll_baseline": 0.6925, "scored_games": 301},
        ["scope[nfl-backtest]: teams=32, games=603, competitions={NFL}",
         "stream: 603 games (preseason excluded) — warm-up 301 (2024), scored 301 (2025)",
         "baseline home prob (2024 realized): 0.5648",
         "log-loss: model 0.6538 vs baseline 0.6925 (need <= 0.6825) -> PASS",
         "  band 30-40%: n=38 stated 0.352 realized 0.342 gap 1.0pp -> ok",
         "  band 40-50%: n=57 stated 0.451 realized 0.404 gap 4.8pp -> ok",
         "  band 50-60%: n=51 stated 0.556 realized 0.471 gap 8.6pp -> FAIL",
         "  band 60-70%: n=71 stated 0.654 realized 0.718 gap 6.4pp -> ok",
         "  band 70-80%: n=50 stated 0.751 realized 0.660 gap 9.1pp -> FAIL",
         "GATE VERDICT: FAIL — REGRESSION: the live model no longer clears its frozen gate; investigate before the "
         "next predict-nfl"]),
}


@pytest.fixture
def db(tmp_path, monkeypatch):
    d = world.fresh(tmp_path / "nfl.db", monkeypatch)
    d.ids = world.build(d)
    return d


@pytest.mark.parametrize("variant", list(GOLDEN))
def test_nfl_backtest_output_is_byte_identical_to_main(db, variant):
    cap, shrink = variant
    lines = []
    r = nb.run_backtest(progress=lines.append, cap=cap, shrink=shrink)
    want_r, want_lines = GOLDEN[variant]
    assert lines == want_lines
    assert r == want_r


def test_nfl_backtest_cli_unchanged(db):
    import cli
    res = CliRunner().invoke(cli.cli, ["nfl-backtest"])
    assert res.exit_code == 0, res.output
    assert res.output.splitlines()[:len(GOLDEN[(None, None)][1])] == GOLDEN[(None, None)][1]


# ============================================================================ the registry entry and the lane --

def test_the_entry_is_declared_unrun_with_v1s_constants_the_term_unset_and_215s_bar():
    e = reg.get(EID)
    assert e is not None, "nfl-elo-v2 must be in docs/registry/experiments.json"
    assert (e["status"], e["run"], e["verdict"], e["sport"]) == ("declared", None, None, "nfl")
    assert all(e.get(k) for k in reg.DECLARE_FIELDS)
    c = nb.NFLEloConfig()
    assert e["constants"] == {"k_factor": c.k_factor, "home_advantage": c.home_advantage,
                              "season_regression": c.season_regression, "mov_base": c.mov_base,
                              "default_rating": c.default_rating}
    t = e["calibration_term"]
    assert t["shrink"] is None and t["home_advantage"] is None and t["fit"] is None
    assert set(t["forms"]) == {"shrink", "home_advantage"}
    assert t["rule"].startswith("ruled by the architect's declaration of 2026-11-05 (addendum 215 item 3); written "
                                "before the run")
    bar = ("warm-up 2024 complete (285), scored 2025 regular + post (285), preseason excluded, baseline the warm-up's "
           "realized home rate, PASS iff log-loss ≤ baseline − 0.010 AND every band with n ≥ 30 within 7pp")
    assert bar in e["gate"] and "2026-11-06" in e["gate"] and e["run_date"].startswith("2026-11-06")
    assert "weeks 10 and 11: 11-12 through 11-23" in e["confirmation_window"]
    assert e["confirmation_plan"] is None
    assert e["declared_at"] == "2026-11-02T15:35:00Z" and e["ratified"].startswith("ARCHITECT 2026-11-02 10:35 ET")
    assert reg._retired_refusal(e["test_set"], EID) is None
    # addendum 219 (ARCHITECT 2026-11-02 12:20 ET): the eight questions ruled, each quoted where it applies
    a219 = "ARCHITECT 2026-11-02 12:20 ET, addendum 219"
    for n, field, head in ((1, e["declared_at_note"], "STATUS before the declaration — `declared`"),
                           (2, t["rule"], "THE FIT METHOD — as built"), (3, t["rule"], "h = 0 — ALLOWED"),
                           (4, t["rule"], "BINDING — RULED IN"), (5, e["gate"], "THE TIE — the frozen text"),
                           (6, e["stream"]["database"], "THE DATABASE on 11-06"),
                           (8, e["confirmation_plan_note"], "confirmation_plan null — as built")):
        assert f"{a219} item {n}, verbatim" in field and f"\"{head}" in field, n
    assert "Law 3's \"ties are rejections\" governs bars written as \"better than\" (the improve bar); where a " \
           "pre-committed criterion wrote \"<=\", \"<=\" stands." in e["gate"]
    assert "stream fingerprint v2" in e["stream"]["fingerprint"] and "calibration term" in e["stream"]["fingerprint"]
    raw = (ROOT / "docs" / "registry" / "experiments.json").read_text()
    assert raw == json.dumps(json.loads(raw), indent=2) + "\n"
    ids = [x["id"] for x in reg.load()]
    assert all(x["declared_at"] > e["declared_at"] for x in reg.load()[ids.index(EID) + 1:])
    assert not (ROOT / "docs" / "registry" / f"{EID}.started.json").exists()
    assert not (ROOT / "docs" / "registry" / "ids" / f"{EID}.txt").exists()
    # the gate reads the real entry as NOT DECLARED: it refuses until the declaration writes the term
    g = _g()
    assert g.term_state(e)[0] is None and "not declared" in g.term_state(e)[2]


def test_the_roadmap_lane_nfl_v2():
    from src import roadmap as rm
    doc = rm.load()
    assert rm.validate(doc) == []
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "nfl-v2"]
    assert ln["issue"] == 783                                        # the lane's Issue (no placeholder)
    assert (ln["registry_id"], ln["state"], ln["competitions"], ln["earliest_live"], ln["moved"]) == \
           (EID, "to declare", ["NFL"], "2026-11-26", [])
    assert [(s["owner"], s["due"]) for s in ln["steps"]] == [
        ("code", "2026-11-03"), ("operator", "2026-11-04"), ("architect", "2026-11-05"), ("operator", "2026-11-06"),
        ("calendar", "2026-11-23"), ("operator", "2026-11-24"), ("architect", "2026-11-26")]   # 219 item 7
    # ARCHITECT 2026-11-03 11:10 ET, addendum 232 item 3(i) (227 item 4 restated): the harness step done 2026-11-02,
    # receipt "#784 merged at 8bef04c2 (addendum 219)"; a done-mark, never a moved line (222 item 3(a))
    assert ln["steps"][0]["done"] == {"date": "2026-11-02", "receipt": "#784 merged at 8bef04c2 (addendum 219)"}
    assert all(s["done"] is None for s in ln["steps"][1:])
    assert ln["steps"][0]["what"].startswith("the harness PR")
    assert "the preflight of the v2 harness" in ln["steps"][1]["what"]
    assert ln["steps"][3]["what"] == "the ONE run on my word, my block, the verdict the same day"
    assert "he pastes the rehearsal pages to his GPT; the read comes to me" in ln["steps"][5]["what"]
    # the records PR (#785, addendum 214 item 4(d)) adds nfl-confirm; it sits right after this lane
    names = [x["lane"] for x in doc["lanes"]]
    assert names.count("nfl-confirm") == 1 and names.index("nfl-confirm") == names.index("nfl-v2") + 1


# =================================================================================== the calibration term --

@pytest.mark.parametrize("term,ok", [
    ({"shrink": None, "home_advantage": None}, False),
    ({"shrink": 0.9, "home_advantage": 40.0}, False),
    ({"shrink": 0.0, "home_advantage": None}, False),
    ({"shrink": 1.2, "home_advantage": None}, False),
    ({"shrink": float("nan"), "home_advantage": None}, False),
    ({"shrink": True, "home_advantage": None}, False),
    ({"shrink": "0.9", "home_advantage": None}, False),
    ({"shrink": None, "home_advantage": float("inf")}, False),
    ({"shrink": 0.9, "home_advantage": None}, True),
    ({"shrink": 0.999, "home_advantage": None}, True),
    ({"shrink": 1, "home_advantage": None}, False),           # nfl_elo_v1 unchanged: not "a probability shrink"
    ({"shrink": 1.0, "home_advantage": None}, False),
    ({"shrink": -0.5, "home_advantage": None}, False),
    ({"shrink": None, "home_advantage": 30.5}, True),
    ({"shrink": None, "home_advantage": 47.5}, True),
    ({"shrink": None, "home_advantage": 0}, True),
    ({"shrink": None, "home_advantage": 48.0}, False),        # nfl_elo_v1 unchanged: not "a smaller home advantage"
    ({"shrink": None, "home_advantage": 60.0}, False),        # larger: the other way
    ({"shrink": None, "home_advantage": 480.0}, False),
    ({"shrink": None, "home_advantage": -1.0}, False),        # an away advantage
    ({"shrink": None, "home_advantage": -500.0}, False),
])
def test_exactly_one_form_with_a_valid_value(term, ok):
    g = _g()
    form, v, why = g.term_state({"calibration_term": term})
    assert (why is None) is ok, why
    if ok:
        with pytest.raises(g.GateRefused):
            g.declared_term({})
        assert g.declared_term({"calibration_term": term}) == (form, float(v))
    else:
        with pytest.raises(g.GateRefused, match="nothing reserved, nothing scored"):
            g.declared_term({"calibration_term": term})
    assert g.term_state(None)[2] and g.term_state({"calibration_term": None})[2]
    if (type(term.get("shrink")) in (int, float) and term["shrink"] == 1) or \
            term.get("home_advantage") in (48.0, 60.0, -1.0):                     # refused, quoting 215 item 2
        assert "a probability shrink toward 0.5, or a smaller home advantage" in g.term_state(
            {"calibration_term": term})[2]


def test_a_no_change_term_would_walk_v1_itself():
    """Why s = 1 and h = 48 refuse: either walks nfl_elo_v1 unchanged (the one read of 2025 spent on v1, which 214
    recorded FAILED, under a new id)."""
    g = _g()
    warmup, scored = _rows()
    v1 = nb.walk_protocol(warmup, scored)
    cfg, price = g.candidate("shrink", 1.0)
    assert nb.walk_protocol(warmup, scored, cfg, price)["ll_model"] == v1["ll_model"]
    cfg, price = g.candidate("home_advantage", 48.0)
    assert nb.walk_protocol(warmup, scored, cfg, price)["ll_model"] == v1["ll_model"]


def _rows():
    """The synthetic stream as Game rows (no DB): warm-up 2024, scored 2025."""
    out, mid = [], 0
    for season in ("2024", "2025"):
        for stage, at, h, a, hs, as_ in world.season_games(season):
            mid += 1
            if "pre" not in stage.lower():
                out.append(nb.Game(mid, at, season, stage, h, a, hs, as_))
    return nb.split(out)


def _manual_walk(warmup, scored, cfg):
    """An independent replay of the frozen protocol's walk: [(p, y)] over the scored games."""
    st = nb._State()
    for g in warmup:
        nb._update(cfg, st, g.home_id, g.away_id, g.season, g.home_score, g.away_score)
    out = []
    for g in scored:
        out.append((nb._expected_home(cfg, st, g.home_id, g.away_id), 1 if g.home_score > g.away_score else 0))
        nb._update(cfg, st, g.home_id, g.away_id, g.season, g.home_score, g.away_score)
    return out


def _ll(pairs):
    return sum(world.ll(p, y) for p, y in pairs) / len(pairs)


def test_the_shrink_form_is_p_prime_at_pricing_only():
    g = _g()
    warmup, scored = _rows()
    cfg, price = g.candidate("shrink", 0.8)
    assert cfg == nb.NFLEloConfig()                                  # ratings and updates: v1's
    assert price(0.75) == 0.5 + 0.8 * 0.25 and price(0.5) == 0.5 and price(0.2) == pytest.approx(0.26)
    v1 = _manual_walk(warmup, scored, nb.NFLEloConfig())
    want = [(0.5 + 0.8 * (p - 0.5), y) for p, y in v1]
    w = nb.walk_protocol(warmup, scored, cfg, price)
    assert w["ll_model"] == pytest.approx(_ll(want), abs=1e-12)
    assert w["ll_model"] != pytest.approx(_ll(v1), abs=1e-6)
    stated = {b["band"]: b["stated"] for b in w["bands"]}
    for b, obs in _banded(want).items():
        assert stated[b] == pytest.approx(sum(p for p, _ in obs) / len(obs), abs=1e-12)


def _banded(pairs):
    by = {}
    for p, y in pairs:
        by.setdefault(int(min(max(p, 0.0), 0.9999) * 10), []).append((p, y))
    return by


def test_the_home_advantage_form_replaces_it_for_the_whole_walk():
    g = _g()
    warmup, scored = _rows()
    cfg, price = g.candidate("home_advantage", 30.0)
    assert price is None and cfg.home_advantage == 30.0
    v1 = nb.NFLEloConfig()
    assert (cfg.k_factor, cfg.season_regression, cfg.mov_base, cfg.default_rating) == \
           (v1.k_factor, v1.season_regression, v1.mov_base, v1.default_rating)
    want = _manual_walk(warmup, scored, nb.NFLEloConfig(home_advantage=30.0))   # warm-up and scored, price and update
    w = nb.walk_protocol(warmup, scored, cfg, price)
    assert w["ll_model"] == pytest.approx(_ll(want), abs=1e-12)
    assert w["ll_model"] != pytest.approx(_ll(_manual_walk(warmup, scored, v1)), abs=1e-9)
    # not a price-only change: the warm-up's updates ran on 30 too, so the ratings entering 2025 differ from v1's
    st = nb._State()
    for x in warmup:
        nb._update(nb.NFLEloConfig(home_advantage=30.0), st, x.home_id, x.away_id, x.season, x.home_score,
                   x.away_score)
    st1 = nb._State()
    for x in warmup:
        nb._update(v1, st1, x.home_id, x.away_id, x.season, x.home_score, x.away_score)
    assert st.ratings != st1.ratings


def test_the_baseline_and_criteria_are_the_frozen_protocols():
    warmup, scored = _rows()
    w = nb.walk_protocol(warmup, scored)
    rate = sum(1 for r in warmup if r.home_score > r.away_score) / len(warmup)
    assert w["baseline_home_rate"] == rate
    assert w["bar"] == w["ll_baseline"] - 0.010 and w["crit_logloss"] == (w["ll_model"] <= w["ll_baseline"] - 0.010)
    gated = [b for b in w["bands"] if b["n"] >= 30]
    assert w["crit_bands"] == all(b["gap"] <= 0.07 for b in gated)
    assert all(b["ok"] is None for b in w["bands"] if b["n"] < 30)
    assert w["scored_ids"] == [r.match_id for r in scored] and w["n_scored"] == len(scored)


def _hand(n_scored, home_wins, n_warm=40, warm_home_wins=22):
    """Hand-built Game lists: n_warm 2024 games (warm_home_wins of them home wins), n_scored 2025 games (the first
    home_wins of them home wins). Teams cycle over 8 ids."""
    def game(i, season, home_win):
        return nb.Game(i, datetime(int(season), 9, 1), season, "Regular Season", i % 8, (i + 3) % 8,
                       24 if home_win else 10, 10 if home_win else 24)
    warm = [game(i, "2024", i < warm_home_wins) for i in range(n_warm)]
    sc = [game(1000 + i, "2025", i < home_wins) for i in range(n_scored)]
    return warm, sc


def _band(w, b):
    (x,) = [x for x in w["bands"] if x["band"] == b]
    return x


def test_the_band_minimum_is_n_at_least_30():
    """Criterion (2)'s boundary: a band holding exactly BAND_MIN_N = 30 is gated; 29 is reported, not scored."""
    assert nb.BAND_MIN_N == 30
    at = lambda p: 0.75                                                    # every scored game in the 70-80% band
    w = nb.walk_protocol(*_hand(30, 12), price=at)                         # realized 0.40: gap 0.35, FAIL
    assert (_band(w, 7)["n"], _band(w, 7)["gated"], _band(w, 7)["ok"], w["crit_bands"]) == (30, True, False, False)
    w = nb.walk_protocol(*_hand(29, 12), price=at)
    assert (_band(w, 7)["n"], _band(w, 7)["gated"], _band(w, 7)["ok"], w["crit_bands"]) == (29, False, None, True)


def test_a_band_gap_equal_to_the_bound_is_within_it(monkeypatch):
    """Criterion (2)'s boundary: 'within 7pp' holds at equality (gap <= BAND_MAX_GAP)."""
    assert nb.BAND_MAX_GAP == 0.07
    at = lambda p: 0.75
    warm, sc = _hand(30, 20)                                               # realized 2/3: gap 0.75 - 2/3
    gap = _band(nb.walk_protocol(warm, sc, price=at), 7)["gap"]
    monkeypatch.setattr(nb, "BAND_MAX_GAP", gap)
    w = nb.walk_protocol(warm, sc, price=at)
    assert (_band(w, 7)["ok"], w["crit_bands"]) == (True, True)
    monkeypatch.setattr(nb, "BAND_MAX_GAP", math.nextafter(gap, 0.0))
    w = nb.walk_protocol(warm, sc, price=at)
    assert (_band(w, 7)["ok"], w["crit_bands"]) == (False, False)


def test_the_log_loss_criterion_holds_at_equality(monkeypatch):
    """Criterion (1)'s boundary: 'log-loss <= baseline - 0.010' holds at equality. Stated = the baseline rate on
    every game makes the model's log-loss the baseline's exactly; with the margin at 0 the bar is the baseline."""
    assert nb.LL_MARGIN == 0.010
    warm, sc = _hand(30, 18)
    base = nb.baseline_rate(warm)
    w = nb.walk_protocol(warm, sc, price=lambda p: base)
    assert w["ll_model"] == w["ll_baseline"] and w["crit_logloss"] is False      # the real margin: not 0.010 better
    monkeypatch.setattr(nb, "LL_MARGIN", 0.0)
    w = nb.walk_protocol(warm, sc, price=lambda p: base)
    assert w["bar"] == w["ll_model"] and w["crit_logloss"] is True
    monkeypatch.setattr(nb, "LL_MARGIN", math.ulp(w["ll_baseline"]))
    assert nb.walk_protocol(warm, sc, price=lambda p: base)["crit_logloss"] is False


# ================================================================================ the gate on a synthetic DB --

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A tmp copy of the real registry; every registry read/write goes there; the reservation to tmp."""
    g = _g()
    p = tmp_path / "experiments.json"
    p.write_text((ROOT / "docs" / "registry" / "experiments.json").read_text())
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(g, "RESERVATION", str(tmp_path / f"{EID}.started.json"))
    return p


AUTO = object()


def WFP():
    """The warm-up fingerprint of the bound DB's 2024 rows (the fit's, when the fit read this DB)."""
    return _g().warmup_fingerprint(nb.split(nb.load_stream())[0])[0]


def declare(ledger, shrink=None, home_advantage=None, fit=AUTO):
    """Write a term into the tmp ledger's entry. fit AUTO: a fit recorded on the bound DB's 2024 rows (the bound
    run, addendum 219 item 4); None: the null fit; else the block given."""
    if fit is AUTO:
        fit = {"method": "test", "warmup_fingerprint": WFP()}
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == EID)
    e["calibration_term"].update({"shrink": shrink, "home_advantage": home_advantage, "fit": fit})
    Path(ledger).write_text(json.dumps(entries, indent=2) + "\n")


def FP():
    """The stream fingerprint --preflight prints now: the bound DB's rows and the tmp ledger's declared term (v2)."""
    g = _g()
    warmup, scored = nb.split(nb.load_stream())
    return g.stream_fingerprint(warmup, scored, g.bound_term(reg.get(EID, reg.LEDGER)))[0]


def COPY(tmp_path, name="run-copy.db") -> str:
    """A .backup copy of the bound DB as it stands now: addendum 219 item 6, the ONE run reads the copy (--db), never
    DATABASE_URL."""
    import src.db.database as d
    return str(_backup(Path(d._engine.url.database), tmp_path / "copies" / name))


def _nothing_written(ledger, before, tmp_path):
    g = _g()
    assert Path(ledger).read_bytes() == before
    assert not os.path.exists(g.reservation_path())
    assert not (tmp_path / "ids").exists()


def _no_scoring(monkeypatch):
    def no(*a, **k):
        raise AssertionError("scored before the refusal")
    monkeypatch.setattr(nb, "walk_protocol", no)
    monkeypatch.setattr(nb, "_expected_home", no)


@pytest.mark.parametrize("case", ["no term", "both forms", "bad value", "no shrink", "not smaller", "no word",
                                  "no fingerprint", "stale fingerprint", "reserved", "already run", "not declared",
                                  "closed", "declared with a run", "null fit", "fit not an object",
                                  "fit without its fingerprint", "stale fit", "no db"])
def test_the_run_refuses_on_each_missing_condition_and_writes_nothing(db, ledger, monkeypatch, tmp_path, case):
    import cli
    g = _g()
    if case == "no term":
        pass
    elif case == "null fit":                            # 219 item 4: "the run REFUSES when `fit` is null"
        declare(ledger, shrink=0.9, fit=None)
    elif case == "fit not an object":
        declare(ledger, shrink=0.9, fit="0" * 64)
    elif case == "fit without its fingerprint":
        declare(ledger, shrink=0.9, fit={"method": "grid", "warmup_fingerprint": "  "})
    elif case == "stale fit":                           # 219 item 4: "... or when the fit's warm-up fingerprint differs"
        wfp = WFP()
        declare(ledger, shrink=0.9, fit={"warmup_fingerprint": wfp[:-1] + ("1" if wfp[-1] == "0" else "0")})
    elif case == "both forms":
        declare(ledger, shrink=0.9, home_advantage=40.0)
    elif case == "bad value":
        declare(ledger, shrink=1.5)
    elif case == "no shrink":
        declare(ledger, shrink=1.0)
    elif case == "not smaller":
        declare(ledger, home_advantage=48.0)
    else:
        declare(ledger, shrink=0.9)
    fp = FP()                                           # the fingerprint of the stream and the term as now declared
    word, given = WORD, fp
    if case == "no word":
        word = "   "
    if case == "no fingerprint":
        given = None
    if case == "stale fingerprint":                     # a realistic stale value: one character off
        given = fp[:-1] + ("1" if fp[-1] == "0" else "0")
    if case == "reserved":
        Path(g.reservation_path()).write_text(json.dumps({"id": EID, "started_at": "2026-11-06T15:00:00Z"}) + "\n")
    if case in ("already run", "not declared", "closed", "declared with a run"):
        entries = json.loads(Path(ledger).read_text())
        e = next(x for x in entries if x["id"] == EID)
        if case == "already run":
            e.update({"status": "run", "run": {"run_at": "2026-11-06T16:00:00Z"}})
        elif case == "closed":                          # the status check alone refuses it
            e.update({"status": "closed", "run": None})
        elif case == "declared with a run":             # the run check alone refuses it
            e.update({"status": "declared", "run": {"run_at": "2026-11-06T16:00:00Z"}})
        else:
            entries.remove(e)
        Path(ledger).write_text(json.dumps(entries, indent=2) + "\n")
    copy = COPY(tmp_path)                               # 219 item 6: the run reads the copy
    before = Path(ledger).read_bytes()
    had_reservation = os.path.exists(g.reservation_path())
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")
    _no_scoring(monkeypatch)
    if case not in ("stale fingerprint", "stale fit"):  # every other refusal comes before the stream is loaded
        monkeypatch.setattr(nb, "load_stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("loaded")))
    args = ["nfl-v2-gate", "--no-fetch"]
    if word is not None:
        args += ["--architect-word", word]
    if given is not None:
        args += ["--stream-fingerprint", given]
    if case != "no db":                                 # 219 item 6: without --db the run refuses
        args += ["--db", copy]
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output
    want = {"no term": "not declared", "both forms": "both forms are set", "bad value": "0 < s < 1",
            "no shrink": "s = 1 is nfl_elo_v1 unchanged", "not smaller": "h = 48.0 is nfl_elo_v1 unchanged",
            "no word": "architect's word", "no fingerprint": "--stream-fingerprint",
            "stale fingerprint": "no longer match the fingerprint given", "reserved": "the one run, recorded or not",
            "already run": "declared and unrun", "not declared": "status absent", "closed": "(status closed)",
            "declared with a run": "declared and unrun", "null fit": "calibration_term.fit is null",
            "fit not an object": "calibration_term.fit is not an object",
            "fit without its fingerprint": "recorded without a warmup_fingerprint", "stale fit": "the fit is stale",
            "no db": "pass --db COPY"}[case]
    assert want in res.output, res.output
    if case in ("null fit", "fit not an object", "fit without its fingerprint", "stale fit"):
        assert "addendum 219 item 4" in res.output
    if case == "no db":
        assert "addendum 219 item 6" in res.output
    assert guarded == []
    assert Path(ledger).read_bytes() == before
    assert os.path.exists(g.reservation_path()) == had_reservation
    assert not (tmp_path / "ids").exists()
    if case in ("reserved", "closed", "declared with a run", "already run", "not declared"):
        # --preflight refuses too: the entry is not declared-and-unrun, or a run was started
        pre = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
        assert pre.exit_code == 2 and "REFUSED" in pre.output, pre.output
        with pytest.raises(g.GateRefused):
            g.run(WORD, fp, no_fetch=True)
        assert guarded == [] and Path(ledger).read_bytes() == before


def test_reserve_refuses_an_existing_reservation_before_the_guard(ledger, monkeypatch):
    g = _g()
    Path(g.reservation_path()).write_text('{"id": "nfl-elo-v2", "started_at": "2026-11-06T15:00:00Z"}\n')
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")
    with pytest.raises(g.GateRefused, match="the one run, recorded or not"):
        g.reserve({"architect_word": WORD}, no_fetch=True)
    assert guarded == []


def test_reserve_is_an_exclusive_create(ledger, monkeypatch):
    """A reservation that appears between the exists check and the create (a second run racing this one) is not
    overwritten: the create is O_EXCL and the run refuses."""
    g = _g()
    first = '{"id": "nfl-elo-v2", "started_at": "2026-11-06T15:00:00Z", "architect_word": "first"}\n'

    def racing_guard(*a, **k):
        Path(g.reservation_path()).write_text(first)
        return "stub"
    monkeypatch.setattr(reg, "cross_ref_guard", racing_guard)
    with pytest.raises(g.GateRefused, match="the one run, recorded or not"):
        g.reserve({"architect_word": "second"}, no_fetch=True)
    assert Path(g.reservation_path()).read_text() == first


# ----------------------------------------------- Codex P1 (a) on #784: the run walks the declared constants --

def _set_constants(ledger, constants):
    """Replace the tmp ledger entry's constants block (None: delete it)."""
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == EID)
    if constants is None:
        e.pop("constants", None)
    else:
        e["constants"] = constants
    Path(ledger).write_text(json.dumps(entries, indent=2) + "\n")


def _drifted(**defaults):
    """An NFLEloConfig whose defaults drifted after the declaration (the code changed, the entry did not)."""
    import dataclasses
    return dataclasses.make_dataclass("NFLEloConfig", [(k, float, dataclasses.field(default=v))
                                                       for k, v in defaults.items()], bases=(nb.NFLEloConfig,))


V1 = {"k_factor": 20.0, "home_advantage": 48.0, "season_regression": 0.25, "mov_base": 2.2, "default_rating": 1500.0}


def test_the_real_entrys_constants_are_the_walks():
    g = _g()
    e = reg.get(EID)
    assert g.code_constants() == V1 == e["constants"]
    assert g.constants_state(e) is None and g.declared_constants(e) == V1


@pytest.mark.parametrize("case", ["code k drifts", "code home advantage drifts", "code default rating drifts",
                                  "code adds a field", "entry differs", "entry by one ulp", "no block", "block not an object",
                                  "missing key", "extra key", "a string value", "a bool value"])
def test_constants_that_are_not_the_declarations_refuse_before_anything_is_read(db, ledger, monkeypatch, tmp_path,
                                                                                case):
    """Codex P1 on #784: the run builds the candidate from NFLEloConfig()'s defaults; a default that drifts after the
    declaration (or an entry block that is not the five constants) refuses, exit 2, before the stream is loaded and
    before the guard and the reservation: nothing read, nothing reserved, nothing recorded."""
    import cli
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    copy = COPY(tmp_path)
    c = dict(V1)
    want = "differ from nfl_backtest.NFLEloConfig()'s, the walk the run would build"
    if case == "code k drifts":
        monkeypatch.setattr(nb, "NFLEloConfig", _drifted(k_factor=21.0))
        want += " (k_factor: entry 20.0, code 21.0)"
    elif case == "code home advantage drifts":                 # v1's base default, not the term's replacement
        monkeypatch.setattr(nb, "NFLEloConfig", _drifted(home_advantage=50.0))
        want += " (home_advantage: entry 48.0, code 50.0)"
    elif case == "code default rating drifts":
        monkeypatch.setattr(nb, "NFLEloConfig", _drifted(default_rating=1505.0))
    elif case == "code adds a field":                          # review on #784: the key set is the dataclass's fields
        monkeypatch.setattr(nb, "NFLEloConfig", _drifted(mov_cap=24.0))
        assert g.candidate("shrink", 0.9)[0].mov_cap == 24.0   # the walk would read it; the entry does not freeze it
        want = "does not name exactly NFLEloConfig()'s fields, k_factor, "
        want2 = "(missing mov_cap: walked, not frozen)"
    elif case == "entry differs":
        _set_constants(ledger, {**c, "mov_base": 2.3})
        want += " (mov_base: entry 2.3, code 2.2)"
    elif case == "entry by one ulp":                         # exact float equality
        _set_constants(ledger, {**c, "season_regression": math.nextafter(0.25, 1.0)})
    elif case == "no block":
        _set_constants(ledger, None)
        want = "has no constants block"
    elif case == "block not an object":
        _set_constants(ledger, [20.0, 48.0, 0.25, 2.2, 1500.0])
        want = "has no constants block"
    elif case == "missing key":
        _set_constants(ledger, {k: v for k, v in c.items() if k != "mov_base"})
        want = "(missing mov_base: walked, not frozen)"
    elif case == "extra key":
        _set_constants(ledger, {**c, "shrink": 0.9})
        want = "(not walked: shrink)"
    elif case == "a string value":
        _set_constants(ledger, {**c, "k_factor": "20.0"})
        want += " (k_factor: entry '20.0', code 20.0)"
    elif case == "a bool value":
        _set_constants(ledger, {**c, "k_factor": True})
    before = Path(ledger).read_bytes()
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")
    _no_scoring(monkeypatch)
    monkeypatch.setattr(nb, "load_stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("loaded")))
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", fp,
                                       "--db", copy, "--no-fetch"])
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output and want in res.output, res.output
    if case == "code adds a field":
        assert want2 in res.output, res.output
    assert "The constants are chosen BEFORE the run and written into the declaration" in res.output
    assert "nothing read, nothing reserved, nothing scored" in res.output
    assert guarded == []
    _nothing_written(ledger, before, tmp_path)
    with pytest.raises(g.GateRefused, match="Codex P1 on #784"):
        g.run(WORD, fp, no_fetch=True, db=copy)
    assert guarded == []
    _nothing_written(ledger, before, tmp_path)


def test_the_constants_check_precedes_the_db_check(db, ledger, monkeypatch, tmp_path):
    """Nothing is read: the drifted constants refuse even with no --db and with a --db that check_db would refuse."""
    g = _g()
    declare(ledger, shrink=0.9)
    _set_constants(ledger, {**V1, "k_factor": 25.0})
    monkeypatch.setattr(g, "check_db", lambda *a, **k: (_ for _ in ()).throw(AssertionError("db checked")))
    for db_arg in (None, str(tmp_path / "missing.db")):
        with pytest.raises(g.GateRefused, match="k_factor: entry 25.0, code 20.0"):
            g.run(WORD, "f" * 64, no_fetch=True, db=db_arg)
    assert not os.path.exists(g.reservation_path())


def test_preflight_says_the_constants_same_or_differs(db, ledger, monkeypatch):
    import cli
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert res.exit_code == 0, res.output
    line = next(x for x in res.output.splitlines() if x.startswith("  constants: "))
    assert line == (f"  constants: the entry's frozen {V1!r} · NFLEloConfig()'s {V1!r} · SAME: the run walks the "
                    "declared constants (Codex P1 on #784)")
    _set_constants(ledger, {**V1, "mov_base": 2.3})
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert res.exit_code == 0, res.output                     # the preflight reads; the run refuses
    assert "· DIFFERS — the run refuses: the entry's frozen constants differ from nfl_backtest.NFLEloConfig()'s, " \
           "the walk the run would build (mov_base: entry 2.3, code 2.2) (Codex P1 on #784)" in res.output
    _set_constants(ledger, None)
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert res.exit_code == 0 and "  constants: the entry's frozen (none) · " in res.output
    assert "DIFFERS — the run refuses: the registry entry has no constants block" in res.output


# ------------------------------------------- Codex P1 (b) on #784: the reservation is whole or absent --

def test_a_reservation_that_cannot_be_serialised_creates_nothing(ledger, monkeypatch):
    g = _g()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")
    with pytest.raises(g.GateRefused, match="could not be serialised .*the read is not spent"):
        g.reserve({"architect_word": WORD, "bad": object()}, no_fetch=True)
    assert not os.path.exists(g.reservation_path())


@pytest.mark.parametrize("fault", ["partial write", "write", "fsync", "close", "directory fsync"])
def test_a_reservation_write_failure_leaves_no_file_and_a_later_reserve_succeeds(ledger, monkeypatch, fault):
    import errno
    g = _g()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")
    real_write, real_close = os.write, os.close
    calls = []

    def bad_write(fd, data):
        calls.append(1)
        if fault == "partial write" and len(calls) == 1:
            return real_write(fd, bytes(data[:10]))           # some bytes land, then the disk fills
        raise OSError(errno.ENOSPC, "No space left on device")

    def bad(*a, **k):
        raise OSError(errno.EIO, "Input/output error")
    closed = []

    def bad_close(fd):                                        # Linux: the fd is released even when close fails
        real_close(fd)
        if not closed:
            closed.append(fd)
            raise OSError(errno.EIO, "Input/output error")
    with monkeypatch.context() as m:
        if fault in ("partial write", "write"):
            m.setattr(g.os, "write", bad_write)
        elif fault == "fsync":
            m.setattr(g.os, "fsync", bad)
        elif fault == "directory fsync":                       # the file's fsync passes; the directory's fails
            real_fsync, synced = os.fsync, []

            def dir_bad(fd):
                synced.append(fd)
                if len(synced) == 2:
                    raise OSError(errno.EIO, "Input/output error")
                return real_fsync(fd)
            m.setattr(g.os, "fsync", dir_bad)
        else:
            m.setattr(g.os, "close", bad_close)
        with pytest.raises(g.GateRefused) as ei:
            g.reserve({"architect_word": WORD}, no_fetch=True)
    msg = str(ei.value)
    assert "could not be written (OSError" in msg
    if fault == "fsync":                                      # every fsync fails: the removal's directory fsync too
        assert "removed, but the removal could not be made durable (OSError" in msg, msg     # #798
        assert msg.endswith("is absent before the run: nothing scored"), msg      # never "the read is not spent"
    else:
        assert msg.endswith("removed: nothing scored, the read is not spent"), msg
    assert not os.path.exists(g.reservation_path())
    if fault == "partial write":
        assert len(calls) == 2
    if fault == "directory fsync":
        assert len(synced) == 3                               # the file, its directory (fails), the removal's (#798)
    # the fault removed, the one reservation is written whole
    p = g.reserve({"architect_word": WORD}, no_fetch=True)
    saved = json.loads(Path(p).read_text())
    assert saved["id"] == EID and saved["architect_word"] == WORD and saved["guard"] == "stub"
    assert Path(p).read_text().endswith("}\n")


def test_the_reservation_fsyncs_its_directory_after_the_file(ledger, monkeypatch):
    """Review on #784: the new file's directory entry is made durable (the directory fsynced) before reserve()
    returns, after the file itself is written, fsynced and closed."""
    import stat
    g = _g()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")
    real_fsync, seen = os.fsync, []

    def spy(fd):
        seen.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return real_fsync(fd)
    monkeypatch.setattr(g.os, "fsync", spy)
    p = g.reserve({"architect_word": WORD}, no_fetch=True)
    assert seen == [False, True]                              # the file, then its directory
    assert json.loads(Path(p).read_text())["architect_word"] == WORD


def test_a_write_failure_whose_removal_also_fails_says_inspect_the_file(ledger, monkeypatch):
    import errno
    g = _g()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")

    def bad(*a, **k):
        raise OSError(errno.EIO, "Input/output error")
    with monkeypatch.context() as m:
        m.setattr(g.os, "fsync", bad)
        m.setattr(g.os, "unlink", lambda p: (_ for _ in ()).throw(PermissionError(errno.EACCES, "denied")))
        with pytest.raises(g.GateRefused, match="could not be removed \\(PermissionError.*INSPECT THE FILE"):
            g.reserve({"architect_word": WORD}, no_fetch=True)
    assert os.path.exists(g.reservation_path())               # left for the operator to inspect, as the refusal says
    os.remove(g.reservation_path())


def test_a_run_whose_reservation_cannot_be_written_records_nothing_and_a_later_run_succeeds(db, ledger, monkeypatch,
                                                                                           tmp_path):
    import cli
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    copy = COPY(tmp_path)
    before = Path(ledger).read_bytes()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")
    real = (nb.walk_protocol, nb._expected_home)
    args = ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", fp, "--db", copy, "--no-fetch"]
    with monkeypatch.context() as m:
        m.setattr(g, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError(28, "No space left on device")))
        _no_scoring(m)
        res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output and "could not be written" in res.output and "the read is not spent" in res.output
    _nothing_written(ledger, before, tmp_path)
    assert (nb.walk_protocol, nb._expected_home) == real
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0, res.output
    assert "recorded: 301 scored ids" in res.output
    assert json.load(open(g.reservation_path()))["stream_fingerprint"] == fp


def test_a_run_whose_reservation_cannot_be_created_exits_2_and_a_later_run_succeeds(db, ledger, monkeypatch, tmp_path):
    """#798 (addendum 222 item 2): a create failing with ENOSPC (not an existing file) is a refusal, exit 2, not a
    traceback; nothing created, nothing scored, nothing recorded; the read is not spent and the one run proceeds."""
    import errno

    import cli
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    copy = COPY(tmp_path)
    before = Path(ledger).read_bytes()
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")
    args = ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", fp, "--db", copy, "--no-fetch"]
    real_open = os.open

    def full_disk(path, *a, **k):                             # only the reservation's create fails
        if os.path.abspath(path) == os.path.abspath(g.reservation_path()):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_open(path, *a, **k)
    with monkeypatch.context() as m:
        m.setattr(g.os, "open", full_disk)
        _no_scoring(m)
        res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2, res.output
    assert res.exception is None or isinstance(res.exception, SystemExit), res.exception
    assert "REFUSED" in res.output and "could not be created (OSError" in res.output
    assert "nothing written, nothing scored, the read is not spent" in res.output
    _nothing_written(ledger, before, tmp_path)
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0, res.output
    assert "recorded: 301 scored ids" in res.output


def test_a_missing_season_refuses_before_the_reservation(tmp_path, monkeypatch, ledger):
    d = world.fresh(tmp_path / "only2024.db", monkeypatch)
    world.build(d, seasons=("2024",))
    declare(ledger, shrink=0.9)
    before = Path(ledger).read_bytes()
    _no_scoring(monkeypatch)
    g = _g()
    with pytest.raises(g.GateRefused, match="insufficient seasons for protocol"):
        g.run(WORD, "f" * 64, no_fetch=True, db=COPY(tmp_path))
    _nothing_written(ledger, before, tmp_path)


def test_the_fingerprint_is_the_corrected_stream(db, ledger):
    """#775's class: a 2024 row stored SCHEDULED with both totals is outside the stream; once it is FINISHED (the
    corrected stream) the warm-up grows by one and the fingerprint changes. A 2026 game, a preseason game and an NCAA
    game never enter it."""
    from sqlalchemy import select, update

    from src.db.schema import Match, MatchStatus
    g = _g()
    before = FP()
    assert FP() == before                                               # stable
    w0, s0 = nb.split(nb.load_stream())
    world.add_game(db, "2026", datetime(2026, 9, 20), 4, 5, 30, 10)
    world.add_game(db, "2025", datetime(2025, 8, 20), 4, 5, 30, 10, stage="Pre Season")
    assert FP() == before
    with db.session_scope() as s:
        s.execute(update(Match).where(Match.status == MatchStatus.SCHEDULED, Match.season == "2024")
                  .values(status=MatchStatus.FINISHED))
    w1, s1 = nb.split(nb.load_stream())
    assert (len(w1), len(s1)) == (len(w0) + 1, len(s0))
    corrected = FP()
    assert corrected != before
    assert g.stream_fingerprint(w1, s1, None)[0] == corrected
    with db.session_scope() as s:                                       # a score change is a different stream
        m = s.execute(select(Match).where(Match.id == db.ids["ids"]["2025"][0])).scalar_one()   # a walked game
        m.home_score += 1
    assert FP() not in (before, corrected)


THE_FINGERPRINT_FIELDS = ("match_id", "utc_date", "season", "stage", "home_id", "away_id", "home_score", "away_score")


def _bumped(row, field):
    v = getattr(row, field)
    if isinstance(v, datetime):
        return row._replace(**{field: v + timedelta(seconds=1)})
    if isinstance(v, str):
        return row._replace(**{field: v + "x"})
    return row._replace(**{field: v + 1})


@pytest.mark.parametrize("field", THE_FINGERPRINT_FIELDS)
@pytest.mark.parametrize("where", ["warm-up", "scored"])
def test_the_fingerprint_reads_every_field(field, where):
    """The contract's eight fields, each one: a change to one field of one walked row changes the fingerprint."""
    g = _g()
    assert g.FINGERPRINT_FIELDS == THE_FINGERPRINT_FIELDS
    warmup, scored = _rows()
    for term in (None, ("shrink", 0.9), ("home_advantage", 40.0)):
        fp, n = g.stream_fingerprint(warmup, scored, term)
        if where == "warm-up":
            w2 = list(warmup)
            w2[7] = _bumped(w2[7], field)
            assert g.stream_fingerprint(w2, scored, term) != (fp, n) and g.stream_fingerprint(w2, scored, term)[1] == n
            assert g.warmup_fingerprint(w2)[0] != g.warmup_fingerprint(warmup)[0]
        else:
            s2 = list(scored)
            s2[7] = _bumped(s2[7], field)
            assert g.stream_fingerprint(warmup, s2, term) != (fp, n) and g.stream_fingerprint(warmup, s2, term)[1] == n


def test_the_term_is_inside_the_stream_fingerprint():
    """Addendum 219 item 4: "the term's value is INSIDE the fingerprint the architect's word binds to (the word names
    the term)". The same rows with another value, the other form or no term have another fingerprint; the warm-up
    fingerprint (the fit's) is the rows' alone; the value is taken exactly as the run uses it (term_state's float)."""
    g = _g()
    warmup, scored = _rows()
    terms = [None, ("shrink", 0.9), ("shrink", 0.85), ("shrink", math.nextafter(0.9, 1.0)), ("home_advantage", 0.9),
             ("home_advantage", 40.0), ("home_advantage", 40.5)]
    fps = [g.stream_fingerprint(warmup, scored, t)[0] for t in terms]
    assert len(set(fps)) == len(terms)
    assert g.FINGERPRINT_TAG == "nfl-elo-v2 stream fingerprint v2"
    assert g.stream_fingerprint(warmup, scored, ("home_advantage", 0))[0] == \
        g.stream_fingerprint(warmup, scored, ("home_advantage", 0.0))[0]               # h = 0 as the run uses it
    e = {"calibration_term": {"shrink": None, "home_advantage": 0}}
    assert g.bound_term(e) == ("home_advantage", 0.0)                                # 219 item 3: h = 0 allowed
    assert g.bound_term({"calibration_term": {"shrink": 1.0, "home_advantage": None}}) is None   # invalid: none
    assert g.bound_term(None) is None


def test_a_word_taken_before_a_term_edit_refuses_after_it(db, ledger, monkeypatch, tmp_path):
    """The preflight's fingerprint with s = 0.9 (the word's), then the term edited to 0.85 (the fit untouched): the run
    refuses before the reservation, nothing recorded; the preflight now prints another fingerprint; on that one, it
    runs."""
    import cli
    g = _g()
    declare(ledger, shrink=0.9)
    pre = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert pre.exit_code == 0, pre.output
    worded = pre.output.splitlines()[-1].split()[2]
    assert worded == FP()
    declare(ledger, shrink=0.85)                                    # edited after the word
    before = Path(ledger).read_bytes()
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")
    real = (nb.walk_protocol, nb._expected_home)
    _no_scoring(monkeypatch)
    copy = COPY(tmp_path)
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", worded,
                                       "--db", copy, "--no-fetch"])
    assert res.exit_code == 2 and "REFUSED" in res.output and "no longer match the fingerprint given" in res.output
    assert "shrink s = 0.85" in res.output and "v2 binds the term, addendum 219 item 4" in res.output
    assert guarded == []
    _nothing_written(ledger, before, tmp_path)
    again = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"]).output.splitlines()[-1].split()[2]
    assert again != worded and again == FP()
    monkeypatch.setattr(nb, "walk_protocol", real[0])
    monkeypatch.setattr(nb, "_expected_home", real[1])
    r = g.run(WORD, again, no_fetch=True, db=copy)
    assert r["calibration_term"] == {"form": "shrink", "value": 0.85} and r["stream_fingerprint"] == again


def test_preflight_scores_nothing_writes_nothing_and_prints_no_2025_figure(db, ledger, monkeypatch, tmp_path):
    import cli
    g = _g()
    before = Path(ledger).read_bytes()
    _no_scoring(monkeypatch)
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: (_ for _ in ()).throw(AssertionError("guard")))
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    assert out[0].startswith("NFL-ELO-V2 · PREFLIGHT (scores nothing)")
    assert out[1] == ("  scope[nfl-v2-gate]: teams=32, games=603, competitions={NFL} · db DATABASE_URL (the app's "
                      "configured database)")
    assert "warm-up 2024: 301 games (addendum 215 item 2 names 285: DIFFERS by +16" in res.output
    assert "scored 2025: 301 games (addendum 215 item 2 names 285: DIFFERS by +16" in res.output
    assert "by stage Post Season 13, Regular Season 288" in res.output
    assert "preseason excluded: 2024 4, 2025 4 · other seasons, never walked: 2026 1" in res.output
    assert "calibration term: NOT DECLARED — the run refuses" in res.output
    assert "fit NOT RECORDED (calibration_term.fit null or without warmup_fingerprint): the run refuses" in res.output
    assert out[-1] == (f"STREAM FINGERPRINT {FP()} (602 games: the 2024 and 2025 stream as the gate walks it, and the "
                       "calibration term NOT DECLARED: this fingerprint binds the undeclared term and the run refuses; "
                       "the declaration's term changes it; v2, addendum 219 item 4; the run takes it as "
                       "--stream-fingerprint)")
    assert out[-2] == "PREFLIGHT only: nothing scored, nothing reserved, nothing recorded."
    warmup, scored = nb.split(nb.load_stream())
    r24 = sum(1 for r in warmup if r.home_score > r.away_score) / len(warmup)
    r25 = sum(1 for r in scored if r.home_score > r.away_score) / len(scored)
    assert f"{r24:.6f} (301 games)" in res.output
    for fmt in (".6f", ".4f", ".3f"):
        assert format(r25, fmt) not in res.output
    assert "log-loss" not in res.output
    _nothing_written(ledger, before, tmp_path)
    # a declared term and a recorded fit fingerprint print as such
    wfp = g.warmup_fingerprint(warmup)[0]
    declare(ledger, home_advantage=40.0, fit={"warmup_fingerprint": wfp})
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert "calibration term: home advantage 40.0 Elo points (v1: 48.0)" in res.output
    assert f"warm-up fingerprint {wfp} (301 games" in res.output
    assert "· SAME: the fit is bound to these 2024 rows (addendum 219 item 4)" in res.output
    assert res.output.splitlines()[-1].startswith(f"STREAM FINGERPRINT {FP()} (602 games: the 2024 and 2025 stream as "
                                                  "the gate walks it, and the calibration term as declared (home "
                                                  "advantage 40.0 Elo points")
    declare(ledger, home_advantage=40.0, fit={"warmup_fingerprint": "e" * 64})       # a stale fit, said in advance
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert res.exit_code == 0 and "CHANGED since the fit: the run refuses" in res.output
    _nothing_written(ledger, Path(ledger).read_bytes(), tmp_path)


@pytest.mark.parametrize("declared", [False, True])
def test_preflight_output_does_not_depend_on_any_2025_outcome(db, ledger, declared):
    """The property, not a format: two streams that differ only in their 2025 outcomes print the same preflight,
    byte for byte, but for the stream fingerprint (the last line). 215 item 2: "the PR writes it before any 2025
    figure is printed"."""
    import cli
    from sqlalchemy import update

    from src.db.schema import Match
    g = _g()
    if declared:
        warmup, _ = nb.split(nb.load_stream())
        declare(ledger, shrink=0.9, fit={"warmup_fingerprint": g.warmup_fingerprint(warmup)[0]})

    def out():
        res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
        assert res.exit_code == 0, res.output
        return res.output.splitlines()
    a = out()
    with db.session_scope() as s:                       # every 2025 result reversed: home wins become away wins
        s.execute(update(Match).where(Match.season == "2025")
                  .values(home_score=Match.away_score, away_score=Match.home_score))
    b = out()
    with db.session_scope() as s:                       # and every 2025 margin moved
        s.execute(update(Match).where(Match.season == "2025").values(home_score=Match.home_score + 7))
    c = out()
    assert a[-1].startswith("STREAM FINGERPRINT ") and len({a[-1], b[-1], c[-1]}) == 3   # the outcomes did change
    assert a[:-1] == b[:-1] == c[:-1]


def test_the_counts_print_the_same_when_they_are_285(tmp_path, monkeypatch, ledger):
    """215's 285 / 285: printed 'the same', never asserted (a stream of 272 + 13 per season)."""
    d = world.fresh(tmp_path / "w285.db", monkeypatch)
    from src.walters import nfl_v2_gate as g
    orig = world.season_games
    monkeypatch.setattr(world, "season_games", lambda season: [x for i, x in enumerate(orig(season))
                                                                if not (x[0] == "Regular Season" and i >= 4 + 272)])
    world.build(d)
    lines = g.preflight_read(reg.get(EID, reg.LEDGER))
    assert any("warm-up 2024: 285 games (addendum 215 item 2 names 285: the same)" in x for x in lines)
    assert any("scored 2025: 285 games (addendum 215 item 2 names 285: the same)" in x for x in lines)


def test_the_reservation_follows_the_guard_and_precedes_the_first_scored_game(db, ledger, monkeypatch, tmp_path):
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    seen = {}

    def guard(eid, no_fetch=False, repo=None):
        seen["reserved_at_guard"] = os.path.exists(g.reservation_path())
        return "stub"
    monkeypatch.setattr(reg, "cross_ref_guard", guard)
    real = nb.walk_protocol

    def walk(*a, **k):
        seen["reserved_at_walk"] = os.path.exists(g.reservation_path())
        return real(*a, **k)
    monkeypatch.setattr(nb, "walk_protocol", walk)
    copy = COPY(tmp_path)
    g.run(WORD, fp, no_fetch=True, db=copy)
    assert seen == {"reserved_at_guard": False, "reserved_at_walk": True}
    saved = json.load(open(g.reservation_path()))
    assert saved["architect_word"] == WORD and saved["stream_fingerprint"] == fp and saved["guard"] == "stub"
    assert saved["calibration_term"] == {"form": "shrink", "value": 0.9} and saved["stream_games"] == 602
    assert saved["warmup_fingerprint"] == saved["fit_warmup_fingerprint"] == WFP()
    assert saved["db"] == str(Path(copy).resolve())


def test_a_guard_refusal_reserves_nothing_and_scores_nothing(db, ledger, monkeypatch, tmp_path):
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    before = Path(ledger).read_bytes()

    def refuse(*a, **k):
        raise reg.CrossRefRefused("a run record on ref laptop/x at commit abc")
    monkeypatch.setattr(reg, "cross_ref_guard", refuse)
    _no_scoring(monkeypatch)
    copy = COPY(tmp_path)
    with pytest.raises(g.GateRefused, match="laptop/x"):
        g.run(WORD, fp, db=copy)
    _nothing_written(ledger, before, tmp_path)


def test_one_run_recorded_and_a_second_refused(db, ledger, monkeypatch, tmp_path):
    import cli
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    copy = COPY(tmp_path)
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", fp,
                                       "--db", copy, "--no-fetch"])
    assert res.exit_code == 0, res.output
    warmup, scored = nb.split(nb.load_stream())
    cfg, price = g.candidate("shrink", 0.9)
    want = nb.walk_protocol(warmup, scored, cfg, price)                # the frozen protocol's code, the same stream
    assert f"VERDICT (computed; the architect rules): {g.verdict_text(want['pass'], want)}" in res.output
    assert f"log-loss: model {want['ll_model']:.4f} vs baseline {want['ll_baseline']:.4f}" in res.output
    assert "recorded: 301 scored ids" in res.output
    e = reg.get(EID, str(ledger))
    assert e["status"] == "run" and e["run"]["n_scored"] == 301
    rr = e["run"]["result"]
    assert rr["architect_word"] == WORD and rr["stream_fingerprint"] == fp
    assert rr["calibration_term"] == {"form": "shrink", "value": 0.9}
    assert rr["warmup_fingerprint"] == rr["fit_warmup_fingerprint"] == WFP() and rr["db"] == str(Path(copy).resolve())
    assert rr["stream_fingerprint_tag"] == "nfl-elo-v2 stream fingerprint v2"
    assert f"warm-up fingerprint {WFP()}: the fit's ({WFP()}), checked before the reservation" in res.output
    assert rr["ll_model"] == want["ll_model"] and rr["pass"] == want["pass"] and rr["verdict"]
    assert "scored_ids" not in rr and "protocol_lines" not in rr
    ids = [int(x) for x in open(Path(reg.IDS_DIR) / f"{EID}.txt").read().split()]
    assert ids == sorted(db.ids["ids"]["2025"])
    saved = json.load(open(g.reservation_path()))
    assert saved["architect_word"] == WORD and saved["stream_fingerprint"] == fp
    again = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--architect-word", "again", "--stream-fingerprint", fp,
                                         "--db", copy, "--no-fetch"])
    assert again.exit_code == 2 and "REFUSED" in again.output and "read once" in again.output
    os.remove(g.reservation_path())                        # even without the file, the registry refuses
    with pytest.raises(g.GateRefused, match="declared and unrun"):
        g.run("again", fp, db=copy)


def test_the_home_advantage_run_records_its_constants(db, ledger, monkeypatch, tmp_path):
    g = _g()
    declare(ledger, home_advantage=36.0)
    r = g.run(WORD, FP(), no_fetch=True, db=COPY(tmp_path))
    assert r["constants"]["home_advantage"] == 36.0 and r["calibration_term"] == {"form": "home_advantage",
                                                                                   "value": 36.0}
    warmup, scored = nb.split(nb.load_stream())
    assert r["ll_model"] == nb.walk_protocol(warmup, scored, nb.NFLEloConfig(home_advantage=36.0))["ll_model"]
    e = g.record(r, WORD)
    assert e["run"]["result"]["constants"]["home_advantage"] == 36.0
    import dataclasses                                        # the record reads the dataclass's fields (review, #784)
    assert list(r["constants"]) == [f.name for f in dataclasses.fields(nb.NFLEloConfig)] == list(g.code_constants())


def test_an_interrupted_run_spends_the_reservation(db, ledger, monkeypatch, tmp_path):
    g = _g()
    declare(ledger, shrink=0.9)
    fp = FP()
    copy = COPY(tmp_path)

    def boom(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(nb, "walk_protocol", boom)
    with pytest.raises(KeyboardInterrupt):
        g.run(WORD, fp, no_fetch=True, db=copy)
    with pytest.raises(g.GateRefused, match="one run, recorded or not"):
        g.run(WORD, fp, no_fetch=True, db=copy)


# ===================================================================================== the 2024-only fit --

def _fit_output(tmp_path, monkeypatch, seasons, name):
    import cli
    d = world.fresh(tmp_path / name, monkeypatch)
    world.build(d, seasons=seasons)
    res = CliRunner().invoke(cli.cli, ["nfl-v2-fit-warmup"])
    assert res.exit_code == 0, res.output
    return res.output


def test_the_fit_output_is_identical_with_and_without_2025_rows(tmp_path, monkeypatch, ledger):
    before = Path(ledger).read_bytes()
    with_25 = _fit_output(tmp_path, monkeypatch, ("2024", "2025"), "with.db")
    without = _fit_output(tmp_path, monkeypatch, ("2024",), "without.db")
    assert with_25 == without
    # and a wild 2025 row (a 2025 game at the very start of the 2024 season) changes nothing
    import cli
    d = world.fresh(tmp_path / "wild.db", monkeypatch)
    world.build(d, seasons=("2024",))
    world.add_game(d, "2025", datetime(2024, 9, 1), 0, 1, 99, 0)
    assert CliRunner().invoke(cli.cli, ["nfl-v2-fit-warmup"]).output == without
    assert Path(ledger).read_bytes() == before and not os.path.exists(_g().reservation_path())
    assert "FORM shrink: s = " in without and "FORM home advantage: h = " in without
    assert "FIT only: nothing written, nothing reserved, nothing recorded." in without


def test_the_fit_query_selects_2024_only(db, monkeypatch):
    """The SQL carries season = '2024': the rows it returns are the gate's warm-up exactly, and a row of another
    season handed to the fit refuses."""
    f = _f()
    rows = f.load_warmup()
    warmup, _ = nb.split(nb.load_stream())
    assert rows == warmup and {r.season for r in rows} == {"2024"}
    bad = rows[:3] + [rows[3]._replace(season="2025")]
    with pytest.raises(f.FitRefused):
        f.fit(bad)
    with pytest.raises(f.FitRefused, match="nothing to fit"):
        f.fit([])


def test_the_fit_finds_each_grid_minimum_with_its_tie_rule(db):
    f = _f()
    rows = f.load_warmup()
    v1 = f.walk(rows)
    r = f.fit(rows)
    s, h = r["shrink"], r["home_advantage"]
    brute_s = min((f.mean_ll(f.shrunk(v1, x)), abs(x - 1), x) for x in f.S_GRID)
    assert s["value"] == brute_s[2] and s["ll"] == brute_s[0]
    assert all(s["ll"] <= f.mean_ll(f.shrunk(v1, x)) for x in f.S_GRID)
    from dataclasses import replace
    assert all(h["ll"] <= f.mean_ll(f.walk(rows, replace(nb.NFLEloConfig(), home_advantage=x)))
               for x in f.H_GRID[::8])
    assert r["ll_v1"] == f.mean_ll(v1) and r["n"] == 301
    # the 2024 walk is predict-then-update from default ratings: the first game is priced on home advantage alone
    assert v1[0][0] == pytest.approx(1 / (1 + 10 ** (-48.0 / 400)))
    # ties go to the value nearest v1's
    assert f._argmin([(0.9, 0.5), (1.1, 0.5), (0.95, 0.6)], 1.0) == (0.9, 0.5)
    assert f._argmin([(40.0, 0.5), (50.0, 0.5)], 48.0) == (50.0, 0.5)
    lines = f.fit_lines(r)
    assert any(x.startswith(f"  FORM shrink: s = {s['value']:.3f} · method: the s minimizing") for x in lines)
    assert any(x.startswith(f"  FORM home advantage: h = {h['value']:.1f} Elo points (v1 48.0) · method:")
               for x in lines)


def test_the_gate_and_the_fit_are_registered_commands():
    import cli
    assert "nfl-v2-gate" in cli.cli.commands and "nfl-v2-fit-warmup" in cli.cli.commands
    doc = (ROOT / "docs" / "CLI.md").read_text()
    assert "| `nfl-v2-gate` |" in doc and "| `nfl-v2-fit-warmup` |" in doc


def test_the_fit_flags_a_value_that_is_not_the_named_direction():
    f = _f()
    r = {"n": 1, "by_stage": {"Regular Season": 1}, "warmup_fingerprint": "x", "baseline_home_rate": 0.5,
         "ll_baseline": 0.69, "ll_v1": 0.68, "bands_v1": [],
         "shrink": {"value": 1.2, "ll": 0.6, "grid": (0.001, 1.5, 0.001), "at_edge": False, "pairs": [(0.6, 1)]},
         "home_advantage": {"value": 120.0, "ll": 0.6, "grid": (0.0, 120.0, 0.5), "at_edge": True,
                            "pairs": [(0.6, 1)]}}
    out = "\n".join(f.fit_lines(r))
    assert "s > 1 is an EXPANSION away from 0.5, not a shrink" in out
    assert "h >= v1's 48.0: not a smaller home advantage" in out and "AT THE GRID EDGE" in out
    assert "the gate accepts 0 < s < 1 and refuses this value" in out
    assert "the gate accepts 0 <= h < 48.0 and refuses this value" in out
    r["shrink"]["value"] = 1.0
    out = "\n".join(f.fit_lines(r))
    assert "s = 1 is nfl_elo_v1 unchanged, no shrink" in out and "EXPANSION" not in out
    r["shrink"]["value"], r["home_advantage"]["value"], r["home_advantage"]["at_edge"] = 0.9, 40.0, False
    out = "\n".join(f.fit_lines(r))
    assert "EXPANSION" not in out and "not a smaller" not in out and "GRID EDGE" not in out
    assert "unchanged" not in out


# ============================================================ --db: the .backup copy (addendum 219 item 6) --
# "THE DATABASE on 11-06 — a fresh .backup COPY outside data/, opened with `--db` and immutable=1 (the standing rule of
# addendum 198 item 6(ii), the mlb-pitchers pattern) [...] the preflight's fingerprint on that copy is the run's."

def _backup(src: Path, dst: Path) -> Path:
    """A .backup-API copy (sqlite3's online backup), as the operator's block takes it."""
    import sqlite3
    dst.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    a.backup(b)
    b.close()
    a.close()
    return dst


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_db_copy_gives_the_preflight_and_the_run_the_same_stream_and_creates_no_sidecar(db, ledger, tmp_path):
    import cli
    from sqlalchemy import update

    from src.db.schema import Match
    g = _g()
    declare(ledger, shrink=0.9)
    via_url = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert via_url.exit_code == 0, via_url.output
    copy = _backup(tmp_path / "nfl.db", tmp_path / "copy" / "nfl-copy.db")
    sha = _sha(copy)
    via_db = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight", "--db", str(copy)])
    assert via_db.exit_code == 0, via_db.output
    a, b = via_url.output.splitlines(), via_db.output.splitlines()
    assert b[1] == a[1].replace("db DATABASE_URL (the app's configured database)",
                                f"db --db {copy.resolve()} (a .backup copy, opened mode=ro&immutable=1)")
    assert b[1] != a[1] and a[:1] + a[2:] == b[:1] + b[2:]               # the same counts, fingerprints, term
    worded = b[-1].split()[2]
    assert worded == FP()
    assert sorted(os.listdir(copy.parent)) == ["nfl-copy.db"] and _sha(copy) == sha   # no -wal/-shm, unwritten
    # the copy is what --db reads: the bound DB moves (a 2025 result), the copy's fingerprint does not
    with db.session_scope() as s:
        s.execute(update(Match).where(Match.season == "2025").values(home_score=Match.home_score + 7))
    assert FP() != worded
    again = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight", "--db", str(copy)])
    assert again.output.splitlines()[-1].split()[2] == worded
    # the run on the copy, on the copy's fingerprint (the bound DB's would refuse)
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", worded,
                                       "--db", str(copy), "--no-fetch"])
    assert res.exit_code == 0, res.output
    assert f"--db {copy}" in res.output.splitlines()[0]
    saved = json.load(open(g.reservation_path()))
    assert saved["db"] == str(copy.resolve()) and saved["stream_fingerprint"] == worded
    rr = reg.get(EID, str(ledger))["run"]["result"]
    assert rr["db"] == str(copy.resolve()) and rr["stream_fingerprint"] == worded
    assert f"db --db {copy.resolve()}" in rr["scope"]
    assert sorted(os.listdir(copy.parent)) == ["nfl-copy.db"] and _sha(copy) == sha


@pytest.mark.parametrize("where", ["repo data/", "linked data/", "missing", "-wal", "-shm", "-journal"])
@pytest.mark.parametrize("cmd", ["preflight", "run", "fit"])
def test_db_refuses_a_path_under_data_and_a_missing_file_and_creates_nothing(db, ledger, monkeypatch, tmp_path,
                                                                            where, cmd):
    import cli
    from src.walters import mlb_pitchers_gate as mp
    declare(ledger, shrink=0.9)
    fp = FP()
    if where == "repo data/":                           # the repo's own data/ (never created, never read)
        target = ROOT / "data" / "nfl-v2-gate-test-copy.db"
        assert not target.exists()
        want = "resolves under the repo's data/"
    elif where == "linked data/":                       # through a symlink: resolved before the check
        fake = tmp_path / "data"
        monkeypatch.setattr(mp, "DATA_DIR", str(fake))
        _backup(tmp_path / "nfl.db", fake / "nfl-copy.db")
        (tmp_path / "link").symlink_to(fake, target_is_directory=True)
        target = tmp_path / "link" / "nfl-copy.db"
        want = "resolves under the repo's data/"
    elif where.startswith("-"):                         # a sidecar beside the copy: immutable=1 would ignore it
        target = _backup(tmp_path / "nfl.db", tmp_path / "copy" / "nfl-copy.db")
        Path(str(target) + where).write_bytes(b"")
        want = f"has a {where} sidecar"
    else:
        target = tmp_path / "nowhere" / "nfl-copy.db"
        want = "no file at"
    before = Path(ledger).read_bytes()
    guarded = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: guarded.append(1) or "stub")
    _no_scoring(monkeypatch)
    monkeypatch.setattr(nb, "load_stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("loaded")))
    args = {"preflight": ["nfl-v2-gate", "--preflight"],
            "run": ["nfl-v2-gate", "--architect-word", WORD, "--stream-fingerprint", fp, "--no-fetch"],
            "fit": ["nfl-v2-fit-warmup"]}[cmd] + ["--db", str(target)]
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2 and "REFUSED" in res.output and want in res.output, res.output
    assert guarded == []
    _nothing_written(ledger, before, tmp_path)
    if where == "repo data/":
        assert not target.exists()
    if where == "missing":
        assert not target.exists() and not target.parent.exists()


def test_db_on_the_fit_reads_the_copy(db, tmp_path):
    """nfl-v2-fit-warmup --db: the same 2024 fit and warm-up fingerprint as through DATABASE_URL, from the copy; the
    scope line names the database."""
    import cli
    via_url = CliRunner().invoke(cli.cli, ["nfl-v2-fit-warmup"])
    copy = _backup(tmp_path / "nfl.db", tmp_path / "copy" / "nfl-copy.db")
    via_db = CliRunner().invoke(cli.cli, ["nfl-v2-fit-warmup", "--db", str(copy)])
    assert via_url.exit_code == 0 and via_db.exit_code == 0, via_db.output
    a, b = via_url.output.splitlines(), via_db.output.splitlines()
    assert "db DATABASE_URL" in a[1] and f"db --db {copy.resolve()}" in b[1]
    assert a[:1] + a[2:] == b[:1] + b[2:] and f"warm-up fingerprint {WFP()}" in via_db.output
    assert sorted(os.listdir(copy.parent)) == ["nfl-copy.db"]
