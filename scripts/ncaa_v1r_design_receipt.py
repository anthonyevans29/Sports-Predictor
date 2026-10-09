"""
ncaa-elo-v1r gate DESIGN RECEIPT (ARCHITECT 2026-10-08, addendum 11, item 3,
PR A step (a)). A seeded simulation: it reads NO stored game and opens NO
database. It asks how the repo's NCAAEloV1 (constants untouched, D1) fares on
synthetic college seasons whose truth is known, against #79's calibration
band rule AS CODED (src/walters/ncaa_backtest.run_gate -> crit_bands) and
against D5 criteria (2) level and (3) spread.

Spec (architect, verbatim): "130 teams in 10 conferences of 13. True strength
in Elo points = a conference effect plus a team effect, both normal, in three
settings of (conference sd, team sd): (110, 140), (150, 170), (190, 210).
Team effects carry to the next season with persistence 0.85, the spread kept.
Each season: 3 rounds of random cross-conference pairings, then 8 rounds of
random in-conference pairings; home side by coin flip; 6% of games neutral.
Margin = normal with mean (home strength - away strength + 55 unless neutral)
/ 21.5 points and sd 14, rounded, never level. One warm-up season from flat
1500, update only, then the test season scored predict-then-update under D1.
200 seeded seasons per setting."

Interpretations (each stated in the receipt):
  I1 true strength = 1500 + conf_effect + team_effect, conf_effect ~ N(0, conf_sd)
     per conference, team_effect ~ N(0, team_sd) per team.
  I2 team_next = 0.85*team + sqrt(1 - 0.85^2) * N(0, team_sd) (spread kept).
  I3 conference effects persist unchanged from warm-up to test season.
  I4 the model's season_regression (0.25) applies at the season boundary
     exactly as NCAAEloV1 does it (a team regresses at its first test game).
  I5 cross-conference round: a uniformly random perfect matching of all 130
     teams with no same-conference pair (65 games), drawn by REJECTION
     SAMPLING (Codex on #365: the earlier greedy draw was not uniform over
     valid matchings): a uniform random permutation paired consecutively is a
     uniform perfect matching; it is accepted iff no pair shares a conference,
     so an accepted draw is uniform over the valid matchings. Acceptance is
     about e^-6 per attempt; capped at MAX_CROSS_ATTEMPTS, exceeding it raises.
     Seeded. Pairs may repeat across rounds.
  I6 in-conference round: each conference's 13 teams are shuffled and paired
     consecutively; the 13th has a bye (6 games per conference, 60 per round).
     Season = 3*65 + 8*60 = 675 games, all FBS-vs-FBS, all scored.
  I7 neutral: each game independently neutral with probability 0.06.
  I8 "never level": round(margin); a rounded 0 takes the sign of the
     unrounded draw (+1 / -1), so P(home win) = P(draw > 0) exactly.
  I9 D1 neutral handling: NCAAEloV1 has no neutral input, so a thin wrapper
     (NeutralAwareElo) swaps the model's cfg for
     dataclasses.replace(cfg, home_advantage=0.0) for the duration of the
     predict/update call of a game whose `neutral` label is True, then
     restores it. Nothing else of the model is touched.
  I10 Logistic fit: maximum-likelihood Newton-Raphson (numpy, an existing
     dependency) of y on logit(clip(p, 1e-6, 1-1e-6)) with intercept; max 100
     iterations, converged when the max |step| < 1e-10; a singular Hessian,
     a non-finite value or no convergence = FAIL (D5 (3)).
  I11 D5 (2) inclusive and float-safe like the band rule: |mean p - mean y|
     <= 0.05 + 1e-12. D5 (3): |b - 1| <= 0.20 + 1e-12.
  I12 Band rule as coded: run_gate(stream, model).crit_bands from
     src/walters/ncaa_backtest.py (10pp bands, gated when n >= BAND_MIN_N,
     |realized - stated| <= BAND_TOL; no gated band = vacuous pass, as coded).
  I13 "mean slope" = mean of b over the seasons whose fit converged.

Run:  python scripts/ncaa_v1r_design_receipt.py [--seasons N] [--out PATH]
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.ncaa_elo import NCAAEloV1  # noqa: E402
from src.walters import ncaa_backtest as nb  # noqa: E402

N_CONF, CONF_SIZE = 10, 13
N_TEAMS = N_CONF * CONF_SIZE
SETTINGS = [(110.0, 140.0), (150.0, 170.0), (190.0, 210.0)]
PERSISTENCE = 0.85
CROSS_ROUNDS, CONF_ROUNDS = 3, 8
NEUTRAL_P = 0.06
TRUE_HFA = 55.0
ELO_PER_POINT = 21.5
MARGIN_SD = 14.0
N_SEASONS = 200
MASTER_SEED = 20261008
MAX_CROSS_ATTEMPTS = 1_000_000      # I5: expected ~420 attempts per round; a miss here raises, never falls back
CLIP = nb.V1R_CLIP
LEVEL_TOL, SLOPE_TOL = nb.V1R_LEVEL_TOL, nb.V1R_SLOPE_TOL
ARCHITECT = {"slope": (0.99, 1.16, 1.33), "band": (0.32, 0.33, 0.29), "d5": (0.92, 0.60, 0.13)}


def season_seed(setting_idx: int, season_idx: int) -> int:
    return MASTER_SEED + 1000 * setting_idx + season_idx


class NeutralAwareElo(nb.NeutralRuleElo):
    """D1's neutral_site_rule (I9): a game labelled neutral is priced and
    updated with home advantage 0. The wrapper is the one shared with the
    shadow (src/walters/ncaa_backtest.NeutralRuleElo, rule
    no_home_advantage_at_neutral); this subclass only records the test-season
    (p, y) pairs."""

    def __init__(self) -> None:
        super().__init__(neutral_home_advantage=False)
        self.pairs: list[tuple[float, int]] = []

    def predict(self, g) -> float:
        p = super().predict(g)
        self.pairs.append((p, g.home_win))
        return p


def cross_round(rng: np.random.Generator, conf_of: np.ndarray) -> list[tuple[int, int]]:
    """I5: uniform over the perfect matchings with no same-conference pair, by rejection sampling."""
    for _ in range(MAX_CROSS_ATTEMPTS):
        perm = rng.permutation(N_TEAMS)
        a, b = perm[0::2], perm[1::2]
        if not np.any(conf_of[a] == conf_of[b]):
            return [(int(x), int(y)) for x, y in zip(a, b)]
    raise RuntimeError(f"cross_round: no valid matching in {MAX_CROSS_ATTEMPTS} attempts (acceptance ~e^-6)")


def conf_round(rng: np.random.Generator) -> list[tuple[int, int]]:
    out = []
    for c in range(N_CONF):
        members = rng.permutation(np.arange(c * CONF_SIZE, (c + 1) * CONF_SIZE))
        out.extend((int(members[i]), int(members[i + 1])) for i in range(0, CONF_SIZE - 1, 2))
    return out


def play_season(rng, strength, conf_of, season: str, t0: datetime, start_id: int):
    games, k = [], 0
    rounds = [cross_round(rng, conf_of) for _ in range(CROSS_ROUNDS)] + \
             [conf_round(rng) for _ in range(CONF_ROUNDS)]
    for rnd in rounds:
        for a, b in rnd:
            home, away = (a, b) if rng.random() < 0.5 else (b, a)
            neutral = bool(rng.random() < NEUTRAL_P)
            mean = (strength[home] - strength[away] + (0.0 if neutral else TRUE_HFA)) / ELO_PER_POINT
            raw = float(rng.normal(mean, MARGIN_SD))
            margin = int(round(raw))
            if margin == 0:
                margin = 1 if raw > 0 else -1
            hs, as_ = (margin, 0) if margin > 0 else (0, -margin)
            games.append(nb.Game(home_id=home, away_id=away, season=season,
                                 utc_date=t0 + timedelta(minutes=k), home_score=hs,
                                 away_score=as_, neutral=neutral, match_id=start_id + k))
            k += 1
    return games


# I10 / I11: the D5 (2) and (3) computation lives in src (ncaa_backtest.logistic_slope / level_gap / level_ok /
# slope_ok), ONE implementation shared with the gate (src/walters/ncaa_v1r_gate.py).
logistic_slope = nb.logistic_slope


def run_one(setting_idx: int, season_idx: int) -> dict:
    conf_sd, team_sd = SETTINGS[setting_idx]
    seed = season_seed(setting_idx, season_idx)
    rng = np.random.default_rng(seed)
    conf_of = np.repeat(np.arange(N_CONF), CONF_SIZE)
    conf_eff = rng.normal(0.0, conf_sd, N_CONF)
    team0 = rng.normal(0.0, team_sd, N_TEAMS)
    team1 = PERSISTENCE * team0 + math.sqrt(1 - PERSISTENCE ** 2) * rng.normal(0.0, team_sd, N_TEAMS)
    s0 = 1500.0 + conf_eff[conf_of] + team0
    s1 = 1500.0 + conf_eff[conf_of] + team1
    warm = play_season(rng, s0, conf_of, nb.TRAIN_SEASON, datetime(2025, 9, 1), 0)
    test = play_season(rng, s1, conf_of, nb.TEST_SEASON, datetime(2026, 9, 1), 10_000)
    stream = nb.build_stream(warm + test)
    model = NeutralAwareElo()
    r = nb.run_gate(stream, model)
    pairs = model.pairs
    gap = nb.level_gap(pairs)
    a, b = nb.logistic_slope(pairs)
    level_ok = nb.level_ok(gap)
    slope_ok = nb.slope_ok(b)
    return {"seed": seed, "n": len(pairs), "n_test_gate": r.n_test, "slope": b,
            "band_ok": bool(r.crit_bands), "level_ok": level_ok, "slope_ok": slope_ok,
            "d5_ok": level_ok and slope_ok, "level_gap": gap}


def run(n_seasons: int = N_SEASONS) -> list[dict]:
    rows = []
    for si, (cs, ts) in enumerate(SETTINGS):
        res = [run_one(si, k) for k in range(n_seasons)]
        slopes = [x["slope"] for x in res if x["slope"] is not None]
        rows.append({
            "setting": (cs, ts), "seasons": n_seasons,
            "seeds": (season_seed(si, 0), season_seed(si, n_seasons - 1)),
            "mean_scored": sum(x["n"] for x in res) / n_seasons,
            "mean_slope": sum(slopes) / len(slopes) if slopes else float("nan"),
            "nonconverged": n_seasons - len(slopes),
            "band_pass": sum(x["band_ok"] for x in res) / n_seasons,
            "level_pass": sum(x["level_ok"] for x in res) / n_seasons,
            "slope_pass": sum(x["slope_ok"] for x in res) / n_seasons,
            "d5_pass": sum(x["d5_ok"] for x in res) / n_seasons,
        })
    return rows


def verdict(rows: list[dict]) -> str:
    first = rows[0]
    if first["d5_pass"] < 0.85 or first["band_pass"] > 0.60:
        return ("STOP — first setting contradicts the architect beyond noise "
                f"(D5 (2)&(3) {first['d5_pass']:.1%} < 85% or band rule {first['band_pass']:.1%} > 60%): "
                "write no entry; report to the architect.")
    return (f"OK — first setting: D5 (2)&(3) {first['d5_pass']:.1%} (>= 85%), "
            f"band rule {first['band_pass']:.1%} (<= 60%); no stop condition met.")


def render(rows: list[dict], runtime_s: float) -> str:
    cfg = NCAAEloV1().cfg
    L = []
    L.append("# ncaa-elo-v1r gate: design receipt (seeded simulation)")
    L.append("")
    L.append("ARCHITECT 2026-10-08, addendum 11, item 3, PR A step (a). Generated by "
             "`scripts/ncaa_v1r_design_receipt.py`. Reads NO stored game; opens no database.")
    L.append("")
    L.append("## Result")
    L.append("")
    L.append("| setting (conf sd, team sd) | seasons | mean scored games | mean slope b | "
             "non-converged fits | #79 band rule as coded | D5 (2) level | D5 (3) spread | D5 (2)&(3) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        cs, ts = r["setting"]
        L.append(f"| ({cs:.0f}, {ts:.0f}) | {r['seasons']} | {r['mean_scored']:.1f} | "
                 f"{r['mean_slope']:.3f} | {r['nonconverged']} | {r['band_pass']:.1%} | "
                 f"{r['level_pass']:.1%} | {r['slope_pass']:.1%} | {r['d5_pass']:.1%} |")
    L.append("")
    L.append("Architect's numbers for comparison: slope "
             + " / ".join(f"{x:.2f}" for x in ARCHITECT["slope"]) + "; band rule "
             + " / ".join(f"{x:.0%}" for x in ARCHITECT["band"]) + "; D5 (2) and (3) "
             + " / ".join(f"{x:.0%}" for x in ARCHITECT["d5"]) + ".")
    L.append("")
    L.append("Stop condition (verbatim): \"If yours contradict mine beyond noise (in the first "
             "setting the model passing D5 (2) and (3) in fewer than 85% of seasons, or passing "
             "the band rule in more than 60%), stop: write no entry and tell me.\"")
    L.append("")
    L.append(f"**{verdict(rows)}**")
    L.append("")
    L.append("## Parameters")
    L.append("")
    L.append(f"- Teams {N_TEAMS} = {N_CONF} conferences x {CONF_SIZE}. Settings (conf sd, team sd): "
             + ", ".join(f"({a:.0f}, {b:.0f})" for a, b in SETTINGS) + ".")
    L.append(f"- Team-effect persistence {PERSISTENCE}; rounds: {CROSS_ROUNDS} cross-conference "
             f"then {CONF_ROUNDS} in-conference; neutral probability {NEUTRAL_P}.")
    L.append(f"- Margin ~ Normal((home - away + {TRUE_HFA:.0f} unless neutral) / {ELO_PER_POINT}, "
             f"{MARGIN_SD:.0f}), rounded, never level.")
    L.append(f"- Candidate (D1): NCAAEloV1 from src/models/ncaa_elo.py, constants untouched: "
             f"k_factor {cfg.k_factor:g}, home_advantage {cfg.home_advantage:g}, mov_base "
             f"{cfg.mov_base:g}, season_regression {cfg.season_regression:g}, default_rating "
             f"{cfg.default_rating:g}.")
    L.append(f"- Band rule as coded: src/walters/ncaa_backtest.py run_gate -> crit_bands "
             f"(10pp bands, BAND_MIN_N {nb.BAND_MIN_N}, BAND_TOL {nb.BAND_TOL}; run_gate's "
             f"MIN_TEST_N {nb.MIN_TEST_N} also applies; warm-up season \"{nb.TRAIN_SEASON}\", "
             f"test \"{nb.TEST_SEASON}\").")
    L.append(f"- D5 (2): |mean p - home win rate| <= {LEVEL_TOL}; D5 (3): |b - 1| <= {SLOPE_TOL}, "
             f"p clipped to [{CLIP:g}, {1 - CLIP:.6f}].")
    L.append("")
    L.append("## Seeds")
    L.append("")
    L.append(f"- MASTER_SEED {MASTER_SEED}; replicate k of setting i uses "
             "`numpy.random.default_rng(MASTER_SEED + 1000*i + k)`, k = 0..seasons-1.")
    for i, r in enumerate(rows):
        L.append(f"- setting {i} {r['setting']}: seeds {r['seeds'][0]}..{r['seeds'][1]}")
    L.append("")
    L.append("## Interpretations")
    L.append("")
    L.append("- I1 \"a conference effect plus a team effect\": true strength = 1500 + conf_effect "
             "+ team_effect; conf_effect ~ N(0, conf sd) per conference, team_effect ~ N(0, team sd) per team.")
    L.append("- I2 \"persistence 0.85, the spread kept\": team_next = 0.85*team + "
             "sqrt(1 - 0.85^2)*N(0, team sd).")
    L.append("- I3 Conference effects persist unchanged from the warm-up to the test season.")
    L.append("- I4 The model's season_regression 0.25 applies at the season boundary exactly as "
             "NCAAEloV1 does it (a team regresses toward 1500 at its first test-season game, "
             "which already prices on the regressed rating).")
    L.append("- I5 Cross-conference round: a uniformly random perfect matching of all 130 teams "
             "with no same-conference pair (65 games), drawn by rejection sampling: a uniform random "
             "permutation paired consecutively (a uniform perfect matching), accepted iff no pair "
             "shares a conference, so accepted draws are uniform over the valid matchings (acceptance "
             f"about e^-6; capped at {MAX_CROSS_ATTEMPTS:,} attempts, exceeding it raises). Replaces the "
             "earlier randomized greedy draw, which was not uniform (Codex on #365). Pairs may repeat "
             "across rounds.")
    L.append("- I6 In-conference round: each conference's 13 teams shuffled and paired "
             "consecutively, the 13th has a bye (6 games per conference, 60 per round). One "
             "season = 3*65 + 8*60 = 675 games, all FBS-vs-FBS; \"scored\" = every test-season game.")
    L.append("- I7 Home side by a fair coin per game; each game independently neutral with "
             "probability 0.06 (true margin mean then carries no +55).")
    L.append("- I8 \"Never level\": the margin is round(draw); a rounded 0 takes the sign of the "
             "unrounded draw (+1 or -1), so P(home win) = P(draw > 0) exactly.")
    L.append("- I9 D1 neutral_site_rule: NCAAEloV1 has no neutral input, so a thin wrapper "
             "(NeutralAwareElo) sets the model's cfg to dataclasses.replace(cfg, "
             "home_advantage=0.0) for the duration of predict/update on a game labelled neutral, "
             "then restores it. Nothing else in the model changes.")
    L.append("- I10 Calibration slope: maximum-likelihood Newton-Raphson (numpy, already a "
             "dependency; no dependency added) of the home result on logit(p) with intercept; "
             "max 100 iterations, converged when max |step| < 1e-10; singular Hessian, non-finite "
             "value or no convergence = FAIL of D5 (3).")
    L.append("- I11 D5 (2) and (3) are inclusive and float-safe (+1e-12), as the band rule is coded.")
    L.append("- I12 Band rule as coded: the gate's own run_gate drives the warm-up (update only) "
             "and the test season (predict-then-update); its crit_bands is the pass. A season with "
             "no band of n >= 100 passes vacuously, as coded.")
    L.append("- I13 Mean slope = mean of b over the seasons whose fit converged.")
    L.append("")
    L.append(f"Runtime: {runtime_s:.1f} s.")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=N_SEASONS)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    t = time.time()
    rows = run(a.seasons)
    text = render(rows, time.time() - t)
    print(text)
    if a.out:
        Path(a.out).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
