"""ncaa-elo-v2: THE DECLARATION AND ITS MACHINERY (ARCHITECT 2026-10-16, addendum 81 item 2; GATE-CLASS). Synthetic
data only: no test reads data/, runs the real gate or the real fit, or touches the real registry (every registry
write goes to a tmp ledger). Pins:
- the registry entry (declared, unrun; D5 and D7 verbatim; the plan; v1's constants; the neutral rule; s null until
  the fit is frozen; D9, D10 and D11 verbatim) and the spec and ledger quoting D1-D11 verbatim; the roadmap lane;
- D1: NCAAEloV2 at s = 400 is v1 exactly; s is the price only, the update at /400 (addendum 86 item 3, Q1): any s
  walks v1's ratings;
- the gate's machinery parameterised by registry id (v1r unchanged: tests/test_ncaa_v1r_gate.py): the run refuses
  until s is frozen, without the word or the fingerprint, without 2024, 2025 and 2026 covered, on a fingerprint
  mismatch, under 500 and without D4, each before the reservation; D3 (2024 and 2025 update only, 2026 'regular'
  scored), D4 over 2024 AND 2025; one fingerprint over both streams (the week included for 2023);
- D10: the second read's cold start, weeks 1-4 walked and the baseline's, scored from week 5, INVALID under 500 or
  without its baseline, NOT READ without coverage (never a refusal of the gate), and the combined verdict;
- --preflight prints both streams and no outcome the run would score; the frozen s and the training stream check;
- the fit of s: training seasons only (the command loads no other season's label or score), each with a 'regular'
  game, the declared search (maximum, bracket edge, tie toward 400), the curve, the slope on 2025, the checks against
  v1r's recorded run; the commands by id."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

import cli as cli_mod
from src.models.ncaa_elo import NCAAEloConfig, NCAAEloV1, NCAAEloV2
from src.walters import ncaa_backtest as nb
from src.walters import ncaa_scale_fit as fs
from src.walters import ncaa_v1r_gate as vg
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent

# ARCHITECT 2026-10-16 07:53 ET, addendum 81, item 2 (D1-D11) and item 1, verbatim
D = {
    "D1": (
        "D1. Candidate: NCAAEloV1's structure and constants (k_factor 24, home_advantage 55, mov_base 2.2, "
        'season_regression 0.25, default_rating 1500, neutral rule no_home_advantage_at_neutral) with ONE '
        'fitted parameter: the logistic scale s in P(home) = 1 / (1 + 10^(-(dr + ha) / s)), fitted by maximum'
        ' likelihood on the 2024 and 2025 regular-season games of the stream (D2) and then frozen; v1 is s = '
        "400. Code's PR prints the fitted s, the fit's log-likelihood curve at s = 300..500 by 25, and the "
        'slope b that the fitted s gives on 2025 (a read of the training set, reported, not a gate). Nothing '
        'else is fitted.'
    ),
    "D2": (
        "D2. Stream: as v1r's D2 (stored NCAA games with a current CFBD both-FBS label, seasons 2024, 2025, "
        '2026, kickoff then id; labels give home/away, scores, neutral; level scores skipped, counted, '
        'listed), plus 2023 under D10.'
    ),
    "D3": (
        'D3. Split: 2024 and 2025 are training (the fit of s) and warm-up (update); the test set is the 2026 '
        "games whose season_type is exactly 'regular', scored when the 500th is final and labelled (the "
        "roadmap's step, 2026-11-08; 274 were final at 2026-10-09). The gate scores no 2026 game before that "
        "day and no game after the run's stream fingerprint is taken."
    ),
    "D4": (
        "D4. Baseline: as v1r's D4, over the stream's 2024 AND 2025 non-neutral regular-season games (one "
        'number, frozen at --preflight, printed).'
    ),
    "D5": (
        "D5. Gate: v1r's D5 verbatim — under 500 scored games INVALID; PASS iff margin (model log-loss < "
        'baseline − 0.010, ties reject), level (|mean p_home − home rate| ≤ 5pp), spread (b within 0.20 of 1,'
        ' non-convergence fails), range (ratings within 1000-2000) — on the 2026 scored set. The reported-'
        "never-gated figures as v1r's."
    ),
    "D6": (
        'D6. Preconditions, in code: --preflight prints the census and the fingerprint; the run takes my word'
        " and the fingerprint; one run; the reservation before the first scored game (ncaa-v1r-gate's "
        "machinery, parameterised by registry id, not copied). 2023's coverage (D10) is a precondition of the"
        ' SECOND read, not of the gate.'
    ),
    "D7": (
        "D7. Confirmation: as v1r's D7 (the first 100 stored fixtures after the verdict, frozen once; "
        'CONFIRMED iff log-loss ≤ 0.6931 and < the D4 baseline − 0.010 on the same games).'
    ),
    "D8": (
        "D8. As v1r's D8: PASS and CONFIRMED make no call; the Desk stays market-only for NCAA until a "
        "separate policy ruling needing the neutral flag before kickoff and the shadow's record against the "
        'close (vs_close on the lane).'
    ),
    "D9": (
        "D9. Prior reads: the 2026 season's games through 2026-10-09 (274 both-FBS finals) were walked by "
        "v1r's shadow exports and by nothing scored; no candidate has been scored on 2026; this declaration "
        "is written with v1r's 2025 figures known (item 1), and with no figure of 2026 read beyond the "
        "shadow's own rows, which carry no verdict."
    ),
    "D10": (
        'D10. THE SECOND READ (older season as test — RULED generally here): a season that predates every '
        'training season, whose games the candidate never walked, is a legitimate additional test, and it can'
        ' only BLOCK: the lane goes live only if BOTH the gate (D5 on 2026) and the second read pass; a '
        'second read that fails is a FAIL of the candidate. For v2: the 2023 FBS regular season, labels from '
        "CFBD (792 both-FBS completed games listed as of the 10-13 probe), the games from the provider's 2023"
        " listing (3,720 listed), ingested whole by Code's PR before 2026-11-01, read ONCE by the run: "
        "ratings start at default_rating for every team (no 2022 warm-up: a cold start, so the first 4 weeks'"
        ' games are walked and not scored; the scored set is 2023 regular games from week 5, which must '
        "number ≥ 500 or the second read is INVALID and I rule again), the fitted s applied, D5's four tests "
        "with D4's baseline taken from 2023's own weeks 1-4 non-neutral games. Safeguards: the season is "
        'declared whole here, nothing of it is fitted, and its census (--preflight) is read by me before the '
        'run; the run is the same one run (one word, one fingerprint covering both streams).'
    ),
    "D11": (
        'D11. Kalshi close as a benchmark: kalshi_settled_markets (KXNCAAFGAME, from 2025-08-23) is read '
        'beside the verdict for the 2026 scored games where a row exists — reported, never gated — and 2023 '
        "has none; nothing in D5 moves for it. (That read waits on the table's first NCAA pull, a later "
        'block.)'
    ),
}
ITEM1 = (
    '1. WHAT v1r SHOWED (the FAIL of 2026-10-09, registry ncaa-elo-v1r, verbatim in part): margin passed '
    '(0.5596 vs the bar 0.6649), level passed (1.8pp), range passed, SPREAD FAILED: slope b 1.4205 '
    "outside 0.80-1.20. b above 1 means the model's log-odds are too timid: outcomes were more decided "
    'than the ratings said. That is one knob — the map from rating difference to probability — and the '
    'ruling of 10-09 allows exactly this: "its figures now show how to correct the candidate. A later '
    'college candidate may train on 2024 and 2025, and declares the 2026 regular season, as it accrues, '
    'as its test."'
)


SPEC = ROOT / "docs" / "specs" / "ncaa-elo-v2.md"
# the BACKLOG entry: a fragment until the tag ritual's compile folds it into BACKLOG.md (tests/ledger_text.py)
LEDGER_ENTRY = ("2026-10-16-ncaa-elo-v2-declaration",
                "**2026-10-16 — DECLARED (ARCHITECT 2026-10-16 07:53 ET, addendum 81 item 2): ncaa-elo-v2")
TEST_SET = "NCAA FBS 2026 regular season as it accrues (CFBD both-FBS labels; training and warm-up 2024 and 2025)"
AT = datetime(2026, 10, 16, 12)
V2 = vg.V2


def G(mid, h, a, season, at, hs, as_, neutral=False, st="regular", week=None):
    return nb.Game(h, a, season, at, hs, as_, "FBS (Division I-A)", neutral=neutral, label_source="cfbd",
                   orientation="same", match_id=mid, season_type=st, cfbd_id=mid + 10_000, cfbd_season=season,
                   label_fetched_at=AT, week=week)


class Fake:
    """A predictor whose probabilities the test sets; it logs every call."""

    def __init__(self, p=0.5, ratings=None):
        self.p, self._r, self.calls = p, ratings or {1: 1500.0, 2: 1500.0}, []

    def predict(self, g):
        self.calls.append(("predict", g.match_id))
        return self.p(g) if callable(self.p) else self.p

    def update(self, g):
        self.calls.append(("update", g.match_id))

    def ratings(self):
        return dict(self._r)


def main_stream(n_test=520, base=(6, 10), flip_2026=False):
    """2024 and 2025: base[1] 'regular' non-neutral games each with base[0] home wins (the D4 rate base[0]/base[1]);
    2026: n_test 'regular' games (home wins on even ids; flipped with flip_2026)."""
    games, mid = [], 0
    for season, t in (("2024", datetime(2024, 9, 1)), ("2025", datetime(2025, 9, 1))):
        for i in range(base[1]):
            mid += 1
            games.append(G(mid, 1 + i % 4, 1 + (i + 1) % 4, season, t + timedelta(hours=mid),
                           21 if i < base[0] else 7, 14))
    t = datetime(2026, 9, 1)
    for i in range(n_test):
        mid += 1
        win = (mid % 2 == 0) != flip_2026
        games.append(G(mid, 1 + i % 4, 1 + (i + 2) % 4, "2026", t + timedelta(hours=mid), 28 if win else 3, 10))
    return games


def second_stream(n_scored=520, early=40, early_wins=30, flip_late=False, no_week=0):
    """2023: `early` 'regular' games in weeks 1-4 (early_wins home wins), then n_scored 'regular' games from week 5,
    then `no_week` 'regular' games without a week, then one postseason game."""
    games, mid, t = [], 50_000, datetime(2023, 8, 26)
    for i in range(early):
        mid += 1
        games.append(G(mid, 1 + i % 4, 1 + (i + 1) % 4, "2023", t + timedelta(hours=mid - 50_000),
                       21 if i < early_wins else 7, 14, week=1 + i % 4))
    for i in range(n_scored):
        mid += 1
        win = (mid % 3 != 0) != flip_late
        games.append(G(mid, 1 + i % 4, 1 + (i + 3) % 4, "2023", t + timedelta(days=30, hours=mid - 50_000),
                       24 if win else 6, 13, week=5 + i // 60))
    for i in range(no_week):
        mid += 1
        games.append(G(mid, 1, 2, "2023", t + timedelta(days=100, hours=i), 20, 10, week=None))
    mid += 1
    games.append(G(mid, 2, 1, "2023", datetime(2024, 1, 1), 31, 30, st="postseason", week=1))
    return games


def _v(games, seasons):
    return nb.v1r_stream(games, {}, {s_: AT for s_ in ("2023", "2024", "2025", "2026")}, seasons)


def _cov(ok=("2023", "2024", "2025", "2026"), present=("2023", "2024", "2025", "2026")):
    from src.ingestion import ncaa_cfbd as nc
    return {s_: {"season": s_, "payload": f"p{s_}", "reason": None, "unlabelled": [], "fetched_at": AT,
                 "current": 100 if s_ in ok else 80, **nc.fbs_coverage(100, 100 if s_ in ok else 80)}
            for s_ in present}


# ---------------------------------------------------------------------------------- the declaration (registry) --

def test_registry_entry_is_declared_unrun_with_the_verbatim_gate_window_plan_and_keys():
    e = reg.get("ncaa-elo-v2")
    assert e is not None, "ncaa-elo-v2 must be declared in docs/registry/experiments.json"
    assert (e["status"], e["run"], e["verdict"]) == ("declared", None, None)
    assert e["declared_at"].startswith("2026-10-16")
    assert e["sport"] == "ncaa" and e["declaration"] == "docs/specs/ncaa-elo-v2.md" and e["test_set"] == TEST_SET
    assert e["gate"] == D["D5"].removeprefix("D5. Gate: ")
    assert e["confirmation_window"] == D["D7"].removeprefix("D7. Confirmation: ")
    assert e["confirmation_plan"] == {"n_games": 100, "metric": "log_loss", "bar": 0.6931,
                                      "must_beat_reference": True,
                                      "reference": "the D4 baseline on the same games minus 0.010"}
    assert reg.check_plan(e["confirmation_plan"]) == e["confirmation_plan"]
    assert all(e.get(k) for k in reg.DECLARE_FIELDS)
    assert e["neutral_site_rule"] == "no_home_advantage_at_neutral"
    d = NCAAEloConfig()
    assert e["constants"] == {k: getattr(d, k) for k in ("k_factor", "home_advantage", "mov_base",
                                                         "season_regression", "default_rating")}
    # D1, FROZEN by the declaration PR from the operator's printout (ARCHITECT 2026-10-16, addendum 93 item 2)
    assert e[vg.SCALE_KEY]["s"] == 279.14222651259433 and repr(e[vg.SCALE_KEY]["s"]) == "279.14222651259433"
    assert vg.scale_state(V2, e) == (279.14222651259433, None)
    assert e[vg.SCALE_KEY]["fit"]["training_fingerprint"] == ("a5568a48718d7ea18e7d397c8c3be4ff11c03651574c38cbcf6d0"
                                                             "6f882f3ab47")
    assert e[vg.SCALE_KEY]["fit"]["regular_games"] == {"2024": 752, "2025": 762}
    assert (e[vg.SCALE_KEY]["fit"]["log_likelihood"], e[vg.SCALE_KEY]["fit"]["b_2025"]) == (-870.104578, 0.99133)
    assert e[vg.SCALE_KEY]["fit"]["head"] == "4790737" and "addendum 93" in e[vg.SCALE_KEY]["fit"]["ruling"]
    assert "PRICE ONLY (ARCHITECT 2026-10-16, addendum 86 item 3, Q1)" in e[vg.SCALE_KEY]["rule"]
    assert e["second_read"] == D["D10"] and e["benchmark"] == D["D11"] and e["prior_reads_note"] == D["D9"]
    assert reg._retired_refusal(e["test_set"], e["id"]) is None
    assert reg.prior_reads(e["test_set"], None, before_id="ncaa-elo-v2") == []


def test_spec_and_ledger_quote_d1_to_d11_and_item_1_verbatim():
    from ledger_text import entry_text, flat
    for name, raw in ((SPEC.name, SPEC.read_text()), (LEDGER_ENTRY[0], entry_text(*LEDGER_ENTRY))):
        text_ = flat(raw)                                    # line wrapping never changes a word
        for k, v in D.items():
            assert v in text_, f"{name}: {k} not verbatim"
        assert TEST_SET in text_
    assert ITEM1 in " ".join(SPEC.read_text().split())


def test_the_roadmap_lane_names_the_declaration_and_the_step_done():
    from src import roadmap
    doc = json.loads((ROOT / "docs" / "roadmap.json").read_text())
    assert roadmap.validate(doc) == []
    ln = next(x for x in doc["lanes"] if x["lane"] == "ncaa")
    assert (ln["registry_id"], ln["state"]) == ("ncaa-elo-v2", "declared")
    assert ln["steps"][0]["done"]["date"] == "2026-10-16" and "addendum 81" in ln["steps"][0]["done"]["receipt"]
    assert ln["steps"][1]["done"] is None and ln["moved"] == []


# ------------------------------------------------------------------------------------------------ D1: the model --

def test_v2_at_400_is_v1_and_s_is_the_price_only_the_ratings_v1s():
    g = [G(1, 1, 2, "2024", datetime(2024, 9, 1), 30, 10), G(2, 2, 1, "2024", datetime(2024, 9, 8), 3, 24),
         G(3, 1, 2, "2025", datetime(2025, 9, 1), 17, 20, neutral=True), G(4, 2, 3, "2025", datetime(2025, 9, 8), 7, 9)]
    v1, v2 = NCAAEloV1(), NCAAEloV2(scale=400.0)
    for x in g:
        assert v1.predict(x) == v2.predict(x)
        v1.update(x)
        v2.update(x)
    assert v1.ratings() == v2.ratings()
    # PRICE ONLY (addendum 86 item 3, Q1): at any s the walk is v1's, rating for rating, neutral games included; only
    # the stated probability moves, and it moves away from 0.5 the same way (s < 400 states it more strongly)
    ref, models = nb.NeutralRuleElo(), [nb.NeutralRuleElo(scale=s_) for s_ in (150.0, 300.0, 400.0, 617.25)]
    for x in g:
        p_ref = ref.predict(x)
        ps = [m.predict(x) for m in models]
        ref.update(x)
        for m in models:
            m.update(x)
            assert m.ratings() == ref.ratings()
        if p_ref != 0.5:
            assert ps[2] == p_ref and (ps[0] - 0.5) * (p_ref - 0.5) > 0
            assert abs(ps[0] - 0.5) > abs(ps[1] - 0.5) > abs(p_ref - 0.5) > abs(ps[3] - 0.5)
    w = nb.NeutralRuleElo(scale=300.0)                        # the neutral rule wraps v2 the same way
    assert w.predict(g[2]) == 0.5 and isinstance(w.m, NCAAEloV2) and w.m.scale == 300.0
    assert isinstance(nb.NeutralRuleElo().m, NCAAEloV1) and not isinstance(nb.NeutralRuleElo().m, NCAAEloV2)


def test_spec_of_serves_the_two_ids_and_refuses_any_other():
    assert vg.spec_of("ncaa-elo-v1r") is vg.V1R and vg.spec_of("ncaa-elo-v2") is V2
    with pytest.raises(vg.GateRefused, match="not a declaration this gate serves"):
        vg.spec_of("ncaa-elo-v3")


@pytest.mark.parametrize("s_", [None, 0, -1.0, float("nan"), float("inf"), True, "283"])
def test_an_unfrozen_or_invalid_scale_refuses(s_):
    e = {vg.SCALE_KEY: {"s": s_}}
    assert vg.scale_state(V2, e)[0] is None
    with pytest.raises(vg.GateRefused, match="not frozen"):
        vg.frozen_scale(V2, e)
    assert vg.frozen_scale(V2, {vg.SCALE_KEY: {"s": 283.25}}) == 283.25
    assert vg.frozen_scale(vg.V1R, {}) is None and isinstance(vg.model_for(vg.V1R, {}).m, NCAAEloV1)
    assert vg.model_for(V2, {vg.SCALE_KEY: {"s": 283.25}}).m.scale == 283.25


# ----------------------------------------------------------------------------------------- D3, D4, D5 (pure) --

def test_d3_d4_2024_and_2025_update_only_the_2026_regular_games_scored_d4_over_both_years():
    extra = [G(9001, 1, 2, "2026", datetime(2026, 9, 2), 30, 20, st="postseason"),
             G(9002, 2, 1, "2025", datetime(2025, 9, 5), 30, 20, neutral=True),      # neutral: not in D4
             G(9003, 2, 1, "2024", datetime(2024, 12, 20), 30, 20, st="postseason")]  # not 'regular': not in D4
    games = sorted(main_stream(n_test=30, base=(7, 10)) + extra, key=lambda g: (g.utc_date, g.match_id))
    assert vg.d4_baseline(games, V2.gate) == (14 / 20, 20)
    m = Fake(0.6)
    r = vg.run_gate(games, m, V2.gate)
    predicted = [mid for k, mid in m.calls if k == "predict"]
    assert set(predicted) == {g.match_id for g in games if g.season == "2026" and g.season_type == "regular"}
    assert len(predicted) == 30 and r["n_scored"] == 30
    assert {mid for k, mid in m.calls if k == "update"} == {g.match_id for g in games}
    assert r["walked_not_scored_2026_by_season_type"] == {"postseason": 1}
    assert r["baseline_home_rate"] == 0.7 and r["verdict"].startswith("INVALID — 30 scored games < 500")


def test_the_gate_reads_the_d5_tests_unchanged_on_2026():
    games = main_stream(n_test=600)
    r = vg.run_gate(games, Fake(lambda g: 0.5 if g.season != "2026" else (0.99 if g.home_win else 0.01)), V2.gate)
    assert r["crit_margin"] and r["n_scored"] == 600 and r["min_scored"] == 500
    assert set(r) >= {"crit_level", "crit_spread", "crit_range", "bands_79", "intercept_a", "cold_starts"}


# ------------------------------------------------------------------------------------------ D10: the second read --

def test_second_read_is_a_cold_start_scored_from_week_5_with_its_own_weeks_1_to_4_baseline():
    games = second_stream(n_scored=510, early=40, early_wins=30, no_week=3)
    v = _v(games, ("2023",))
    assert vg.d4_baseline(v.games, V2.second) == (30 / 40, 40)
    m = Fake(0.6)
    r = vg.second_read(v.games, m, None, V2.second)
    predicted = {mid for k, mid in m.calls if k == "predict"}
    assert predicted == {g.match_id for g in v.games if g.season_type == "regular" and (g.week or 0) >= 5}
    assert r["n_scored"] == 510 and r["read"] is True and r["baseline_home_rate"] == 0.75
    assert r["walked_not_scored_2023_by_season_type"] == {"postseason": 1, "regular, week before 5": 40,
                                                          "regular, week unknown": 3}
    real = vg.second_read(v.games, nb.NeutralRuleElo(scale=300.0), None, V2.second)
    ref = nb.NeutralRuleElo(scale=300.0)                       # a cold start: a fresh model over 2023 alone
    first = ref.predict(v.games[0])
    for g in v.games:
        ref.update(g)
    assert first == 1 / (1 + 10 ** (-55 / 300.0))              # every team at the default rating, home edge only
    assert (real["rating_min"], real["rating_max"]) == (min(ref.ratings().values()), max(ref.ratings().values()))
    assert real["teams_rated"] == 4 and real["walked_by_season"] == {"2023": len(v.games)}


def test_second_read_invalid_under_500_or_without_its_baseline_and_not_read_without_coverage():
    v = _v(second_stream(n_scored=499), ("2023",))
    r = vg.second_read(v.games, Fake(0.6), None, V2.second)
    assert r["verdict"].startswith("INVALID — 499 scored games < 500")
    v = _v(second_stream(n_scored=600, early=0, early_wins=0), ("2023",))
    m = Fake(0.6)
    r = vg.second_read(v.games, m, None, V2.second)
    assert r["verdict"].startswith("INVALID — no 2023 non-neutral 'regular' (weeks before 5) game") and not m.calls
    r = vg.second_read(v.games, m, "2023 not covered", V2.second)
    assert r["verdict"] == "NOT READ — 2023 not covered" and r["read"] is False and not m.calls


@pytest.mark.parametrize("gate,second,head", [
    ("PASS — x", "PASS — y", "PASS"),
    ("PASS — x", "FAIL — (3) spread", "FAIL"),
    ("FAIL — (1) margin", "PASS — y", "FAIL"),
    ("FAIL — (1) margin", "FAIL — (4) range", "FAIL"),
    ("PASS — x", "INVALID — 480 scored games < 500", "NO VERDICT"),
    ("PASS — x", "NOT READ — 2023 not covered", "NO VERDICT"),
    ("FAIL — (2) level", "NOT READ — 2023 not covered", "FAIL"),
])
def test_the_lane_goes_live_only_if_both_pass_and_a_failed_second_read_fails_the_candidate(gate, second, head):
    v = vg.combined_verdict(gate, second)
    assert v.startswith(head + " —")
    if head == "PASS":
        assert "Desk stays market-only" in v
    failed_second = second.startswith("FAIL")
    assert ("a second read that fails is a FAIL of the candidate" in v) is failed_second
    if head == "NO VERDICT":                                   # each read's whole status, never a truncated word
        assert f"the second read {second.split(' — ')[0]}:" in v and "the gate PASS," in v
    if head == "FAIL" and not failed_second:
        assert f"the second read: {second.split(' — ')[0]})" in v and "goes live only if BOTH" in v


def test_the_combined_verdict_strings_in_full():
    assert vg.combined_verdict("PASS — x", "NOT READ — 2023 not covered (L2 + L3)") == (
        "NO VERDICT — the gate PASS, the second read NOT READ: D10, the lane goes live only if both pass; the "
        "architect rules again")
    assert vg.combined_verdict("FAIL — (1) margin", "INVALID — 480 scored games < 500") == (
        "FAIL — the gate: FAIL — (1) margin (D10: the lane goes live only if BOTH the gate and the second read "
        "pass; the second read: INVALID)")
    assert vg.combined_verdict("PASS — x", "FAIL — (3) spread") == (
        "FAIL — the second read: FAIL — (3) spread (D10: a second read that fails is a FAIL of the candidate)")


# ------------------------------------------------------------------------------------------ the fingerprint --

def test_one_fingerprint_covers_both_streams_and_the_second_reads_week():
    main, second = main_stream(n_test=20), second_stream(n_scored=20)
    fp, n = vg.stream_fingerprint(main, V2, second)
    assert n == len(main) + len(second)
    moved = [nb.Game(**{**g.__dict__, "week": 6}) if g.match_id == second[-2].match_id else g for g in second]
    assert vg.stream_fingerprint(main, V2, moved)[0] != fp                 # the week is a field D10 reads
    flipped = main[:-1] + [nb.Game(**{**main[-1].__dict__, "home_score": 0})]
    assert vg.stream_fingerprint(flipped, V2, second)[0] != fp
    assert vg.stream_fingerprint(main, V2, second)[0] == fp                 # stable
    assert vg.stream_fingerprint(main, vg.V1R)[0] != fp                     # its own tag
    assert "week" not in vg.FINGERPRINT_FIELDS and "week" in V2.second_fields


# --------------------------------------------------------------------------------------------------- the run --

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A tmp copy of the real registry (every registry read/write goes there); the reservations in tmp."""
    p = tmp_path / "experiments.json"
    p.write_text((ROOT / "docs" / "registry" / "experiments.json").read_text())
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(vg, "RESERVATION_DIR", str(tmp_path))
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: f"guard {eid}: stub")
    return p


def _freeze_s(ledger, s_=300.0, fit=None):
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == "ncaa-elo-v2")
    e[vg.SCALE_KEY] = {**e[vg.SCALE_KEY], "s": s_, "fit": fit}
    Path(ledger).write_text(json.dumps(entries, indent=2))


def _ready(monkeypatch, main=None, second=None, cov=None):
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: {k: v for k, v in (cov or _cov()).items()
                                                                 if k in seasons})
    seen = {}
    main = main if main is not None else main_stream()
    second = second if second is not None else second_stream()

    def load(spec=vg.V1R):
        seen["reserved_at_read"] = os.path.exists(vg.reservation_path(spec))
        seen["reads"] = seen.get("reads", 0) + 1
        return _v(main, V2.seasons), _v(second, V2.second_seasons)
    monkeypatch.setattr(vg, "load_streams", load)
    return seen, vg.stream_fingerprint(_v(main, V2.seasons).games, V2, _v(second, ("2023",)).games)[0]


def test_the_run_refuses_until_s_is_frozen_before_anything_is_read(ledger, monkeypatch):
    _freeze_s(ledger, None)                                       # the entry as declared, before addendum 93's freeze
    seen, fp = _ready(monkeypatch)
    asked = []
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: asked.append(seasons) or _cov())
    with pytest.raises(vg.GateRefused, match="logistic scale s is not frozen"):
        vg.run("go", fp, spec=V2)
    assert not seen and not asked and not os.path.exists(vg.reservation_path(V2))   # not even the coverage read


def test_the_run_refuses_without_word_fingerprint_or_2024_2025_2026_coverage(ledger, monkeypatch):
    _freeze_s(ledger)
    seen, fp = _ready(monkeypatch)                             # coverage full: only the word or the print refuses
    for word, f, why in ((None, fp, "architect's word"), ("  ", fp, "architect's word"),
                         ("go", None, "--stream-fingerprint"), ("go", " ", "--stream-fingerprint")):
        with pytest.raises(vg.GateRefused, match=why):
            vg.run(word, f, spec=V2)
    assert not seen
    seen, fp = _ready(monkeypatch, cov=_cov(ok=("2023", "2024", "2025")))
    with pytest.raises(vg.GateRefused, match=r"2026 80\.0% \(80/100\)"):
        vg.run("go", fp, spec=V2)
    assert not seen and not os.path.exists(vg.reservation_path(V2))


def test_mismatch_under_500_and_undefined_d4_refuse_before_the_reservation(ledger, monkeypatch):
    _freeze_s(ledger)
    seen, fp = _ready(monkeypatch)
    with pytest.raises(vg.GateRefused, match="no longer matches"):
        vg.run("go", "0" * 64, spec=V2)
    seen, fp = _ready(monkeypatch, main=main_stream(n_test=499))
    with pytest.raises(vg.GateRefused, match="499 < 500"):
        vg.run("go", fp, spec=V2)
    seen, fp = _ready(monkeypatch, main=[g for g in main_stream() if g.season == "2026"])
    with pytest.raises(vg.GateRefused, match="no 2024 and 2025 non-neutral 'regular' game"):
        vg.run("go", fp, spec=V2)
    assert not os.path.exists(vg.reservation_path(V2)) and reg.get("ncaa-elo-v2", reg.LEDGER)["run"] is None


def test_the_one_run_reserves_first_reads_both_streams_and_records_every_scored_id(ledger, monkeypatch):
    _freeze_s(ledger, 300.0)
    seen, fp = _ready(monkeypatch)
    order = []
    real = vg.run_gate

    models = []

    def gate(games, model=None, read=None):
        order.append((read.name if read else "v1r", os.path.exists(vg.reservation_path(V2)), model.m.scale))
        models.append((model, dict(model.ratings())))          # the model itself: an id() of a freed one recurs
        return real(games, model, read)
    monkeypatch.setattr(vg, "run_gate", gate)
    r = vg.run("the word", fp, spec=V2)
    assert seen == {"reserved_at_read": False, "reads": 1}
    assert order == [("the gate", True, 300.0), ("the second read", True, 300.0)]
    assert models[0][0] is not models[1][0] and models[1][1] == {}      # D10: a fresh model, every team at default
    cold = vg.second_read(_v(second_stream(), ("2023",)).games, nb.NeutralRuleElo(scale=300.0), None, V2.second)
    assert (r["second_read"]["rating_min"], r["second_read"]["ll_model"]) == (cold["rating_min"], cold["ll_model"])
    saved = json.load(open(vg.reservation_path(V2)))
    assert saved["id"] == "ncaa-elo-v2" and saved["architect_word"] == "the word" and saved["stream_fingerprint"] == fp
    assert saved["logistic_scale"] == 300.0 and saved["second_read"]["covered"] is True
    assert saved["second_read"]["scored_set_n"] == 520 and saved["guard"] == "guard ncaa-elo-v2: stub"
    assert r["n_scored"] == 520 and r["second_read"]["n_scored"] == 520 and r["logistic_scale"] == 300.0
    assert r["verdict"] == vg.combined_verdict(r["verdict_gate"], r["second_read"]["verdict"])
    lines = vg.run_lines(r, V2)
    assert any(x.startswith("  THE GATE (D5 on 2026): ") for x in lines)
    assert f"  stream fingerprint {fp} ({len(main_stream()) + len(second_stream())} games: the 2024-2026 stream " \
           "and the 2023 second-read stream as the run walks them), checked before the reservation and recorded " \
           "beside the word" in lines
    assert any(x.startswith("  THE SECOND READ: ") for x in lines) and lines[-1].startswith("  VERDICT")
    e = vg.record(r, "the word", V2)
    ids = (Path(reg.IDS_DIR) / "ncaa-elo-v2.txt").read_text().split()
    assert len(ids) == e["run"]["n_scored"] == 1040
    by = e["run"]["result"]["scored_ids_by_read"]
    assert by["gate"]["n"] == 520 and by["second read"]["n"] == 520
    assert "scored_ids" not in e["run"]["result"]["second_read"] and e["run"]["result"]["architect_word"] == "the word"
    with pytest.raises(vg.GateRefused, match="declared and unrun"):
        vg.run("again", fp, spec=V2)


@pytest.mark.parametrize("second, why", [
    (dict(n_scored=499), "INVALID — 499 scored games < 500"),
    (dict(early=0, early_wins=0), "INVALID — no 2023 non-neutral 'regular' (weeks before 5) game"),
])
def test_the_second_reads_invalid_states_never_refuse_the_run(ledger, monkeypatch, second, why):
    _freeze_s(ledger)
    seen, fp = _ready(monkeypatch, second=second_stream(**second))
    r = vg.run("go", fp, spec=V2)
    assert r["second_read"]["verdict"].startswith(why) and os.path.exists(vg.reservation_path(V2))
    assert not r["verdict"].startswith("PASS")


def test_2023_not_covered_never_refuses_the_gate_the_second_read_is_not_read(ledger, monkeypatch):
    _freeze_s(ledger)
    seen, fp = _ready(monkeypatch, cov=_cov(ok=("2024", "2025", "2026")))
    r = vg.run("go", fp, spec=V2)
    assert r["second_read"]["verdict"].startswith("NOT READ — 2023 not covered") and r["second_read"]["n_scored"] == 0
    assert json.load(open(vg.reservation_path(V2)))["second_read"]["covered"] is False
    assert not r["verdict"].startswith("PASS")


# ------------------------------------------------------------------------------------------------ --preflight --

def _pf(ledger, main, second, fit_fp=None, s_=None):
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == "ncaa-elo-v2")
    if s_ is not None:
        e[vg.SCALE_KEY] = {"s": s_, "fit": {"training_fingerprint": fit_fp}}
    return vg.preflight_lines(vg.preflight(_v(main, V2.seasons), _cov(), V2, _v(second, ("2023",)), e), V2)


def test_preflight_prints_both_streams_and_no_2026_or_scored_2023_outcome(ledger):
    _freeze_s(ledger, None)                                       # the entry as declared, before addendum 93's freeze
    main, second = main_stream(), second_stream(no_week=2)
    L = _pf(ledger, main, second)
    assert L[0].startswith("NCAA-ELO-V2 · PREFLIGHT (D6: scores nothing)") and L[-1].startswith("STREAM FINGERPRINT ")
    assert L[-1].split()[2] == vg.stream_fingerprint(_v(main, V2.seasons).games, V2, _v(second, ("2023",)).games)[0]
    text_ = "\n".join(L)
    assert "NOT FROZEN — the run refuses" in text_ and "SECOND READ (D10" in text_
    assert "'regular' games by CFBD week: 1 10, 2 10, 3 10, 4 10, 5 60" in text_ and "unknown 2" in text_
    assert "2024 and 2025 non-neutral 'regular' home win rate 0.600000 (n 20)" in text_
    assert "2023 non-neutral 'regular' (weeks before 5) home win rate 0.750000 (n 40)" in text_
    assert "test set if run now: 520 2026 'regular' games" in text_ and "second read if run now: 520" in text_
    # every outcome the run would score can change and only the fingerprint moves
    L2 = _pf(ledger, main_stream(flip_2026=True), second_stream(flip_late=True, no_week=2))
    assert L2[:-1] == L[:-1] and L2[-1] != L[-1]


def test_preflight_shows_the_frozen_s_and_whether_the_training_stream_is_the_fits(ledger):
    main, second = main_stream(), second_stream()
    tfp = vg.training_fingerprint(_v(main, V2.seasons).games, V2)[0]
    assert "300.0 FROZEN" in "\n".join(_pf(ledger, main, second, tfp, 300.0))
    assert ": SAME" in "\n".join(_pf(ledger, main, second, tfp, 300.0))
    assert "CHANGED since the fit" in "\n".join(_pf(ledger, main, second, "f" * 64, 300.0))
    unknown = "\n".join(_pf(ledger, main, second, None, 300.0))
    assert "UNKNOWN — logistic_scale.fit records no training_fingerprint" in unknown and "CHANGED" not in unknown
    # the training fingerprint reads 2024 and 2025 only: a 2026 result never moves it
    assert vg.training_fingerprint(_v(main_stream(flip_2026=True), V2.seasons).games, V2)[0] == tfp


# --------------------------------------------------------------------------------------------- D1: the fit of s --

def test_the_fit_refuses_any_game_outside_2024_and_2025():
    with pytest.raises(fs.FitRefused, match="2026"):
        fs.walk(main_stream(n_test=5), 400.0)
    assert fs.walk(vg.training_games(main_stream(n_test=5), V2), 400.0)["n"] == 20


def test_the_fit_refuses_a_training_season_without_a_regular_game_before_any_walk(monkeypatch):
    walks = []
    monkeypatch.setattr(fs, "walk", lambda train, s_, spec=V2: walks.append(s_) or {"ll": -1.0, "n": 1})
    both = vg.training_games(main_stream(n_test=0), V2)
    no25 = [g for g in both if g.season == "2024"] + [nb.Game(**{**g.__dict__, "season_type": "postseason"})
                                                      for g in both if g.season == "2025"]
    for train, gone in ((no25, "2025"), ([g for g in both if g.season == "2025"], "2024"), ([], "2024, 2025")):
        with pytest.raises(fs.FitRefused, match=f"no 'regular' game of {gone} in the training stream"):
            fs.fit(train)
    with pytest.raises(fs.FitRefused, match="2026"):
        fs.fit(main_stream(n_test=5))
    assert walks == []
    assert fs.check_training(both) == {"2024": 10, "2025": 10} and fs.fit(both)["n"] == 20


def test_the_search_finds_the_maximum_flags_the_edge_and_breaks_ties_toward_400(monkeypatch):
    train = vg.training_games(main_stream(n_test=0), V2)
    for peak in (283.4, 412.77):
        monkeypatch.setattr(fs, "walk", lambda train, s_, spec=V2, p=peak: {"ll": -(s_ - p) ** 2, "n": 1})
        f = fs.fit(train)
        assert abs(f["s"] - peak) < 1e-5 and not f["on_bracket_edge"] and f["grid_best"] == round(peak / 5) * 5
    monkeypatch.setattr(fs, "walk", lambda train, s_, spec=V2: {"ll": -(s_ - 40.0) ** 2, "n": 1})
    f = fs.fit(train)
    assert f["on_bracket_edge"] and f["grid_best"] == 100.0 and f["s"] == 100.0
    monkeypatch.setattr(fs, "walk", lambda train, s_, spec=V2: {"ll": -1.0, "n": 1})
    assert fs.fit(train)["s"] == 400.0


def test_the_fit_on_a_real_walk_beats_every_curve_point_and_never_reads_2026():
    import random
    rnd = random.Random(7)
    true = {t: rnd.gauss(0, 150) for t in range(40)}
    games, mid = [], 0
    for season, t0 in (("2024", datetime(2024, 8, 31)), ("2025", datetime(2025, 8, 30))):
        for wk in range(12):
            order = list(true)
            rnd.shuffle(order)
            for i in range(0, 40, 2):
                h, a = order[i], order[i + 1]
                y = rnd.random() < 1 / (1 + 10 ** (-(true[h] - true[a] + 55) / 250))
                mid += 1
                games.append(G(mid, h, a, season, t0 + timedelta(days=7 * wk, minutes=i), 30 if y else 10,
                               10 if y else 30))
    g26 = [G(10**6 + i, 1, 2, "2026", datetime(2026, 9, 1) + timedelta(hours=i), 9, 30) for i in range(50)]
    v = _v(games + g26, V2.seasons)
    c = fs.compute(v, {vg.SCALE_KEY: {"s": None}}, None)
    flipped = fs.compute(_v(games + [nb.Game(**{**g.__dict__, "home_score": 40}) for g in g26], V2.seasons),
                         {vg.SCALE_KEY: {"s": None}}, None)
    assert c["fit"] == flipped["fit"] and c["curve"] == flipped["curve"] and c["slope"] == flipped["slope"]
    assert [p["s"] for p in c["curve"]] == [300.0 + 25 * i for i in range(9)]
    assert all(c["fit"]["ll"] >= p["ll"] for p in c["curve"])
    assert c["training_games"] == len(games) and c["slope"]["season"] == "2025" and c["slope"]["b"] is not None
    L = fs.lines(c)
    assert any(x.startswith(f"  FITTED s = {c['fit']['s']!r}") for x in L) and "NOT REPRODUCED" in "\n".join(L)
    assert L[-1].startswith("FIT ONLY: nothing scored on 2026")
    assert any(x.startswith("  later-season games kicking off before the last 2025 game: 0 ") for x in L)
    early26 = G(10**7, 1, 2, "2026", datetime(2025, 9, 10), 9, 30)       # a 2026 game before the last 2025 one
    c2 = fs.compute(_v(games + g26 + [early26], V2.seasons), {vg.SCALE_KEY: {"s": None}}, None)
    assert c2["fit"] == c["fit"]                                           # the fit never reads it
    assert any(x.startswith("  later-season games kicking off before the last 2025 game: 1 ") for x in fs.lines(c2))
    # the check against v1r's recorded run: b at s = 400 on 2025, and v1r's stream fingerprint
    rec = {"run": {"result": {"slope_b": c["at_400"]["b"], "stream_fingerprint": c["v1r_fingerprint_today"]}}}
    L = fs.lines(fs.compute(v, {vg.SCALE_KEY: {"s": None}}, rec))
    assert "-> REPRODUCED" in "\n".join(L) and "-> SAME" in "\n".join(L)


def _fresh_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    eng = create_engine(f"sqlite:///{tmp_path / 'fit.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return db


def test_the_fit_command_loads_the_2024_and_2025_labels_only_and_counts_later_games_without_a_score(
        tmp_path, ledger, monkeypatch):
    """Codex on #553 (P1): the fit's read loads no 2026 (or 2023) label or score, and no unlabelled row; the later-
    season count reads kickoffs and stamps only, current labels only."""
    from src.db.schema import (Competition, Match, MatchStatus, NCAACFBDIngestRecord, NCAACFBDLabel, Sport, Team)
    db = _fresh_db(tmp_path, monkeypatch)
    with db.session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        t = [Team(sport=Sport.NFL, name=n) for n in "ABCDEF"]
        s.add_all([comp, *t])
        s.flush()
        ids = {}

        def match(i, season, at, label=True, stamp=AT, status=MatchStatus.FINISHED):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=at, status=status,
                      home_team_id=t[i % 6].id, away_team_id=t[(i + 1) % 6].id, stage="FBS (Division I-A)",
                      home_score=21, away_score=14)
            s.add(m)
            s.flush()
            if label:
                s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=m.id, season=season,
                                    orientation="same", neutral=False, home_score=21 + i % 2, away_score=14,
                                    fetched_at=stamp, season_type="regular"))
            ids.setdefault(season, []).append(m.id)
            return m.id

        for season, start in (("2023", datetime(2023, 9, 2)), ("2024", datetime(2024, 9, 1)),
                              ("2025", datetime(2025, 9, 1)), ("2026", datetime(2026, 9, 1))):
            for i in range(8):
                match(i, season, start + timedelta(days=i))
        early = match(0, "2026", datetime(2025, 9, 3))                                # a 2026 label before the end
        match(1, "2026", datetime(2025, 9, 4), stamp=AT - timedelta(days=3))         # stale: not current, not counted
        unl = match(2, "2025", datetime(2025, 9, 5), label=False)                    # an unlabelled FINISHED row
        for season in ("2023", "2024", "2025", "2026"):
            s.add(NCAACFBDIngestRecord(season=season, division="fbs", fetched_at=AT, payload_file="p.json",
                                       records=8, in_scope=8, joined=8, unlabelled=[]))
    games = nb.load_v1r_games(("2024", "2025"))
    assert {g.cfbd_season for g in games} == {"2024", "2025"} and len(games) == 16
    assert early not in {g.match_id for g in games} and unl not in {g.match_id for g in games}
    assert len(nb.load_v1r_games()) == 8 * 4 + 2 + 1                                   # v1r's read: unchanged
    last25 = datetime(2025, 9, 8)
    assert nb.count_current_labels_before(last25, ("2026",)) == 1                      # the early one, current only
    assert nb.count_current_labels_before(datetime(2025, 9, 2), ("2026",)) == 0
    assert nb.count_current_labels_before(last25, ("2023",)) == 8                      # 2023 is not v1r's: not asked
    seen = []
    real = nb.load_v1r_games
    monkeypatch.setattr(nb, "load_v1r_games", lambda seasons=None: seen.append(seasons) or real(seasons))
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: _cov())
    c = fs.run(V2)
    assert seen == [("2024", "2025")] and c["training_games"] == 16 and c["later_walked_before"] == 1
    assert c["by_season"] == {"2024": 8, "2025": 8}


def test_fit_command_refuses_without_2024_and_2025_coverage(ledger, monkeypatch):
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: _cov(ok=("2024",)))
    res = CliRunner().invoke(cli_mod.cli, ["ncaa-fit-scale", "--id", "ncaa-elo-v2"])
    assert res.exit_code == 2 and "REFUSED" in res.output and "2025 80.0%" in res.output


# ------------------------------------------------------------------------------------- the commands, by id --

def test_the_gate_command_by_id(ledger, monkeypatch):
    r = CliRunner().invoke(cli_mod.cli, ["ncaa-gate", "--id", "ncaa-elo-v1r", "--preflight"])
    assert r.exit_code == 2 and "ncaa-elo-v1r must be declared and unrun" in r.output     # v1r ran: closed
    _freeze_s(ledger)
    seen, fp = _ready(monkeypatch)
    r = CliRunner().invoke(cli_mod.cli, ["ncaa-gate", "--id", "ncaa-elo-v2", "--preflight"])
    assert r.exit_code == 0, r.output
    assert r.output.splitlines()[-1] == f"STREAM FINGERPRINT {fp} ({len(main_stream()) + len(second_stream())} " \
                                        "games: the 2024-2026 stream and the 2023 second-read stream as the run " \
                                        "walks them; the run takes it as --stream-fingerprint)"
    assert not os.path.exists(vg.reservation_path(V2))
    r = CliRunner().invoke(cli_mod.cli, ["ncaa-gate", "--id", "ncaa-elo-v2", "--architect-word", "go"])
    assert r.exit_code == 2 and "--stream-fingerprint" in r.output


def test_the_confirmation_by_id_refuses_before_a_run_and_scores_with_the_frozen_s(ledger, monkeypatch):
    with pytest.raises(vg.GateRefused, match="ncaa-elo-v2 has no run record"):
        vg.confirming(V2)
    r = CliRunner().invoke(cli_mod.cli, ["ncaa-confirm", "--id", "ncaa-elo-v2"])
    assert r.exit_code == 2 and "ncaa-elo-v2 has no run record" in r.output
    # a PASS recorded on the tmp ledger, s frozen at 283.25: D7 scores the cohort by v2's own replay at that s
    _freeze_s(ledger, 283.25)
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == "ncaa-elo-v2")
    e.update({"status": "confirming", "verdict": {"verdict": "PASS", "ruling": "PASS. ARCHITECT", "at": "2026-11-10T00:00:00Z"},
              "run": {"run_at": "2026-11-09T00:00:00Z", "n_scored": 0, "ids_file": None,
                      "result": {"baseline_home_rate": 0.6}}})
    Path(ledger).write_text(json.dumps(entries, indent=2))
    games = main_stream(n_test=40)
    ids = [g.match_id for g in games if g.season == "2026"][-10:]
    monkeypatch.setattr(vg, "coverage", lambda seasons, s=None: _cov())
    monkeypatch.setattr(vg, "load_streams", lambda spec=vg.V1R: (_v(games, V2.seasons), None))
    monkeypatch.setattr(vg, "cohort", lambda e_, s: {"state": "frozen", "ids": ids, "n_games": 100,
                                                     "eligible_stored": 10})
    monkeypatch.setattr(vg, "_statuses", lambda s, ids_: {i: {"status": "finished"} for i in ids_})
    got = vg.confirmation_read(V2)
    walked = _v(games, V2.seasons).games
    at_s = vg.score_cohort(walked, ids, 0.6, nb.NeutralRuleElo(scale=283.25))
    at_400 = vg.score_cohort(walked, ids, 0.6)
    assert got["n"] == 10 and got["log_loss"] == at_s["log_loss"] and got["log_loss"] != at_400["log_loss"]
