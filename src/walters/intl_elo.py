"""
INTERNATIONAL ELO v1 — the run harness, built FROM the ratified declaration
docs/specs/intl-elo-v1.md (registry `intl-elo-v1`, #220 lane 2). Every
constant below is that document's; nothing here is tuned.

ARCHITECT 2026-10-02 (ruling, then ARCHITECT-RULE on #232, pre-run, frozen):
  H +100, 0 at derived-neutral; unknown venue = listed home +100 (counted);
  K by class: friendlies 20, Nations League 40, qualifiers 50, finals 60;
  mov = ln(max(|margin|, 1) + 1) x 2.2/(2.2 + gap*0.001) (the gap factor is 1
  for a draw: no winner), S = 1 / 0.5 / 0;
  three-way via the soccer Elo->Poisson mapping (c 0.0023, DC rho -0.10,
  mu from train); no season regression; naive baseline = frozen train H/D/A,
  symmetric at derived-neutral; bar = naive - 0.010; the NHL/NFL bands
  with three pairs per match; RPS reported.
  RULE CHECK gate at 10%: if the home-and-away competitions derive > 10%
  neutral under intl-neutral-v1, the run switches to the pre-declared
  intl-neutral-v2 (the venue city is not among the cities where the home
  team hosted >= 1 COMPETITIVE match in the pool; friendlies excluded).

Refused before any data is read unless the registry holds `intl-elo-v1`
declared and unrun. The ONE run records its scored ids and result.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

EID = "intl-elo-v1"
START = 1500.0
HOME = 100.0
MOV_BASE = 2.2
ELO_GOAL_COEFF = 0.0023
DC_RHO = -0.10
LL_MARGIN = 0.010
RULE_CHECK_MAX = 0.10

FRIENDLY = "FRIENDLIES_INT"
# CNL_Q (808): Nations League class, K 40 (#234 ruling 1, 2026-10-02).
NATIONS_LEAGUE = ("UNL", "CNL", "CNL_Q")
QUALIFIERS = ("WCQ_EU", "WCQ_SA", "WCQ_AF", "WCQ_AS", "WCQ_NA", "WCQ_OC", "WCQ_IC", "UEFA_EURO_Q")
FINALS = ("UEFA_EURO",)
K_BY_CODE = {FRIENDLY: 20.0, **{c: 40.0 for c in NATIONS_LEAGUE}, **{c: 50.0 for c in QUALIFIERS},
             **{c: 60.0 for c in FINALS}}
STREAM_CODES = tuple(K_BY_CODE)
HOME_AND_AWAY = ("UNL", "UEFA_EURO_Q") + tuple(c for c in QUALIFIERS if c.startswith("WCQ_"))
# v2's host-city set (#234 ruling 2): home-and-away competitions only — the
# RULE CHECK's codes plus CNL, as proposed on #234. Finals tournaments
# (UEFA_EURO) and friendlies never seed a host city. Every stage of these
# codes counts: the stage vocabulary is not filtered (law 1: not enumerated).
HOST_SET_CODES = HOME_AND_AWAY + ("CNL",)

TRAIN_FROM = datetime(2018, 1, 1)
TRAIN_TO = datetime(2024, 9, 1)            # exclusive: kickoff 2018-01-01 .. 2024-08-31
TEST_UNL_SEASON = "2024/25"
TEST_WCQ_FROM, TEST_WCQ_TO = datetime(2025, 3, 1), datetime(2026, 4, 1)   # 2025-03-01 .. 2026-03-31

RULE_V2 = ("intl-neutral-v2 (ARCHITECT-RULE on #232; #234 ruling 2; preflight ruling 2026-10-02): neutral = "
           "the venue city is not among the cities where the home team hosted >= 1 match of a home-and-away "
           "competition (UNL, WCQ_*, UEFA_EURO_Q, CNL) in the pool — a team hosting a competitive match is at "
           "home even if that city appears once; friendlies and finals tournaments never seed a host city; "
           "either city unknown -> unknown.")


@dataclass(frozen=True)
class Game:
    id: int
    code: str
    season: str
    kickoff: datetime
    home: int
    away: int
    hg: int                        # 90-minute goals
    ag: int
    neutral: bool | None           # under the rule in force; None = unknown
    venue_city: str | None = None

    @property
    def outcome(self) -> str:
        return "H" if self.hg > self.ag else ("A" if self.hg < self.ag else "D")


def is_test(g: Game) -> bool:
    return (g.code == "UNL" and g.season == TEST_UNL_SEASON) or \
        (g.code == "WCQ_EU" and TEST_WCQ_FROM <= g.kickoff < TEST_WCQ_TO)


def home_term(g: Game) -> float:
    return 0.0 if g.neutral is True else HOME          # unknown -> listed home +100 (counted)


@dataclass
class IntlElo:
    mu: float
    ratings: dict[int, float] = field(default_factory=dict)
    # intl-elo-v2 (a): the rating-to-probability scale (a multiplier on the Elo->goals coefficient c,
    # the only place a rating difference becomes a probability) and a global K multiplier.
    # v1 = 1.0 / 1.0 exactly.
    c_mult: float = 1.0
    k_mult: float = 1.0

    def r(self, t: int) -> float:
        return self.ratings.get(t, START)

    def probs(self, g: Game) -> tuple[float, float, float]:
        """(P_H, P_D, P_A): the soccer Elo->Poisson mapping (poisson.predict_match),
        strengths 1, no separate home goal boost (H lives in the Elo difference)."""
        from src.models.poisson import (CompetitionScoringContext, PoissonConfig, TeamStrength,
                                        predict_match)

        p = predict_match(self.r(g.home) + home_term(g), self.r(g.away), TeamStrength(), TeamStrength(),
                          CompetitionScoringContext(avg_goals_per_team_per_match=self.mu, home_field_goal_boost=1.0),
                          PoissonConfig(elo_goal_coeff=ELO_GOAL_COEFF * self.c_mult, dixon_coles_rho=DC_RHO))
        return p.p_home, p.p_draw, p.p_away

    def update(self, g: Game) -> None:
        rh, ra, h = self.r(g.home), self.r(g.away), home_term(g)
        exp_h = 1.0 / (1.0 + 10 ** ((ra - (rh + h)) / 400.0))
        s = {"H": 1.0, "D": 0.5, "A": 0.0}[g.outcome]
        margin = abs(g.hg - g.ag)
        if s == 0.5:
            factor = 1.0                                   # a draw has no winner: no gap term
        else:
            gap = (rh + h - ra) if s == 1.0 else (ra - rh - h)
            factor = MOV_BASE / (MOV_BASE + max(gap, 0.0) * 0.001)
        mov = math.log(max(margin, 1) + 1.0) * factor
        delta = K_BY_CODE[g.code] * self.k_mult * mov * (s - exp_h)
        self.ratings[g.home] = rh + delta
        self.ratings[g.away] = ra - delta


def naive(train: list[Game]) -> dict:
    """Frozen train H/D/A: non-neutral (incl. unknown) for non-neutral games;
    (p_N, d_N, p_N) from the train draw rate in neutral games."""
    nn = [g for g in train if g.neutral is not True]
    ne = [g for g in train if g.neutral is True]
    if not nn or not ne:
        raise ValueError("naive baseline needs both non-neutral and neutral train games")
    c = Counter(g.outcome for g in nn)
    d_n = sum(g.outcome == "D" for g in ne) / len(ne)
    return {"home": (c["H"] / len(nn), c["D"] / len(nn), c["A"] / len(nn)),
            "neutral": ((1 - d_n) / 2, d_n, (1 - d_n) / 2), "n_train_nonneutral": len(nn),
            "n_train_neutral": len(ne)}


def ll3(p: tuple[float, float, float], outcome: str) -> float:
    return -math.log(max(p["HDA".index(outcome)], 1e-12))


def rule_check(games: list[Game]) -> dict:
    ha = [g for g in games if g.code in HOME_AND_AWAY and g.neutral is not None]
    n = sum(g.neutral for g in ha)
    share = n / len(ha) if ha else 0.0
    return {"neutral": n, "known": len(ha), "share": share, "breached": share > RULE_CHECK_MAX}


def apply_v2(games: list[Game], norm) -> tuple[list[Game], Counter]:
    """intl-neutral-v2: host-city sets from home-and-away competitions only
    (#234 ruling 2); friendlies and finals tournaments never seed a host city.

    ARCHITECT 2026-10-02 (intl preflight): "the
    "neutral_city_hosted_only_this_match" category is HOME, not neutral — a
    team hosting a competitive match is at home even if that city appears
    once; leave-one-out was meant to catch finals, which never seed anyway."
    So a home-and-away match's own venue counts toward its team's host set.
    The reclassified matches (their city hosted only this match) are counted
    as `home_city_hosted_only_this_match` (formerly neutral or unknown)."""
    hosts: dict[int, Counter] = defaultdict(Counter)
    for g in games:
        if g.code in HOST_SET_CODES and norm(g.venue_city):
            hosts[g.home][norm(g.venue_city)] += 1
    out, c = [], Counter()
    for g in games:
        v = norm(g.venue_city)
        mine = hosts.get(g.home, {})
        flag = None if v is None or not mine else (v not in mine)
        if flag is False and g.code in HOST_SET_CODES and mine.get(v) == 1:
            c["home_city_hosted_only_this_match"] += 1           # reclassified HOME by the ruling
        c["unknown" if flag is None else "neutral" if flag else "home"] += 1
        out.append(Game(g.id, g.code, g.season, g.kickoff, g.home, g.away, g.hg, g.ag, flag, g.venue_city))
    return out, c


def load(s, rule: str = "v1") -> tuple[list[Game], Counter]:
    """The stream (law 4: a finished AET/PEN row without a 90-minute score is
    excluded and counted; so is a row with no status code to vouch for its
    score). rule "v1": neutral from match_neutral_derived (v2 is applied on
    top by the caller); rule "v3" (intl-elo-v2): neutral_v3 from
    intl_match_venue — no row, or a NULL flag, is unknown."""
    from sqlalchemy import select

    from src.db.schema import Competition, IntlMatchVenue, Match, MatchNeutralDerived, MatchStatus

    comps = {c.id: c.code for c in s.execute(select(Competition).where(Competition.code.in_(STREAM_CODES))).scalars()}
    nd = {r.match_id: r for r in s.execute(select(MatchNeutralDerived)).scalars()}
    v3 = {r.match_id: r.neutral_v3 for r in s.execute(select(IntlMatchVenue)).scalars()} if rule == "v3" else {}
    games, c = [], Counter()
    rows = s.execute(select(Match).where(Match.competition_id.in_(list(comps)), Match.status == MatchStatus.FINISHED)
                     .order_by(Match.utc_date, Match.id)).scalars() if comps else []
    for m in rows:
        if m.utc_date < TRAIN_FROM:
            continue
        if m.home_score_90 is not None and m.away_score_90 is not None:
            hg, ag = m.home_score_90, m.away_score_90
        elif m.status_raw == "FT" and m.home_score is not None and m.away_score is not None:
            hg, ag = m.home_score, m.away_score
        else:
            c["excluded_no_90min_score"] += 1
            continue
        r = nd.get(m.id)
        flag = (v3.get(m.id) if rule == "v3" else (r.neutral_derived if r else None))
        games.append(Game(m.id, comps[m.competition_id], m.season, m.utc_date, m.home_team_id, m.away_team_id,
                          hg, ag, flag, r.venue_city if r else None))
        c["no_neutral_row"] += (m.id not in v3) if rule == "v3" else (r is None)
    return games, c


def run(games: list[Game], c_mult: float = 1.0, k_mult: float = 1.0) -> dict:
    """Walk-forward over the whole stream: predict, then update; only the
    test games are scored. Pure — the CLI handles the registry."""
    from src.walters.evaluation import rps_1x2
    from src.walters.nhl_backtest import calibration_bands

    unruled = Counter(g.code for g in games if g.code not in K_BY_CODE)
    if unruled:
        raise ValueError("K class not ruled for " + ", ".join(f"{c} ({n} games)" for c, n in sorted(unruled.items()))
                         + " — a ruling is needed before the run")
    train = [g for g in games if g.kickoff < TRAIN_TO]
    test = [g for g in games if is_test(g)]
    if not train or not test:
        raise ValueError(f"empty split: train {len(train)}, test {len(test)}")
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    base = naive(train)
    m = IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
    pairs, ll_m, ll_n, rps_m, rps_n = [], 0.0, 0.0, 0.0, 0.0
    per = defaultdict(lambda: [0, 0.0, 0.0])
    counts = Counter()
    for g in games:
        if is_test(g):
            p = m.probs(g)
            q = base["neutral"] if g.neutral is True else base["home"]
            y = g.outcome
            ll_m += ll3(p, y)
            ll_n += ll3(q, y)
            rps_m += rps_1x2(*p, y)
            rps_n += rps_1x2(*q, y)
            for i, o in enumerate("HDA"):
                pairs.append((p[i], int(y == o)))
            k = per[g.code]
            k[0] += 1
            k[1] += ll3(p, y)
            k[2] += ll3(q, y)
            counts["test_neutral" if g.neutral is True else "test_unknown" if g.neutral is None else "test_home"] += 1
        elif g.kickoff >= TRAIN_TO:
            counts["gap"] += 1
        m.update(g)
    n = len(test)
    bands = calibration_bands(pairs)
    ll_model, ll_naive = ll_m / n, ll_n / n
    crit_ll = (ll_naive - ll_model) >= LL_MARGIN - 1e-12
    crit_bands = all(b["ok"] for b in bands if b["gated"])
    verdict = "PASS" if crit_ll and crit_bands else "FAIL — " + ", ".join(
        w for w, ok in (("log-loss margin", crit_ll), ("calibration", crit_bands)) if not ok)
    seasons = sorted({g.season for g in test if g.code == "WCQ_EU"})
    return {"n_train": len(train), "n_test": n, "mu": mu, "naive": base, "ll_model": ll_model,
            "ll_naive": ll_naive, "bar": ll_naive - LL_MARGIN, "rps_model": rps_m / n, "rps_naive": rps_n / n,
            "per_competition": {c: {"n": v[0], "ll_model": v[1] / v[0], "ll_naive": v[2] / v[0]}
                                for c, v in sorted(per.items())},
            "bands": bands, "crit_ll": crit_ll, "crit_bands": crit_bands, "verdict": verdict,
            "counts": dict(counts), "wcq_eu_test_seasons": seasons,
            "unknown_venue_all": sum(g.neutral is None for g in games),
            "scored_ids": [g.id for g in test], "ratings": dict(m.ratings)}


# --------------------------------------------------------------------------
# intl-elo-v2 (ARCHITECT 2026-10-02; docs/specs/intl-elo-v2.md): v1 with (a)
# the rating-to-probability scale and a global K multiplier FITTED BY MAXIMUM
# LIKELIHOOD ON THE TRAINING STREAM ONLY (walk-forward within 2018-2024,
# declared grid, chosen before any test read) and (b) neutral rule v3 (venue
# country) in place of v2. Same bar, same bands, same test set. One run.
# --------------------------------------------------------------------------

EID_V2 = "intl-elo-v2"
V2_C_MULT_GRID = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
V2_K_MULT_GRID = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


def train_loss(train: list[Game], mu: float, c_mult: float, k_mult: float) -> float:
    """Mean three-way log-loss of predict-then-update over the training stream
    from fresh ratings (the walk-forward negative log-likelihood)."""
    m = IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
    total = 0.0
    for g in train:
        total += ll3(m.probs(g), g.outcome)
        m.update(g)
    return total / len(train)


def fit_v2(train: list[Game]) -> tuple[dict, list]:
    """intl-elo-v2 (a): the declared grid, TRAINING STREAM ONLY (kickoff before
    TRAIN_TO; any other game is refused). Minimum mean log-loss wins; an exact
    tie goes to the pair closest to v1's (1.0, 1.0), c first. A grid-edge
    choice is flagged, never widened."""
    if any(g.kickoff >= TRAIN_TO or g.kickoff < TRAIN_FROM for g in train):
        raise ValueError("fit_v2 reads the training stream only (2018-01-01 .. 2024-08-31)")
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    rows = sorted(((train_loss(train, mu, c, k), c, k) for c in V2_C_MULT_GRID for k in V2_K_MULT_GRID),
                  key=lambda r: (round(r[0], 12), abs(r[1] - 1.0), abs(r[2] - 1.0)))
    loss, c, k = rows[0]
    edge = c in (V2_C_MULT_GRID[0], V2_C_MULT_GRID[-1]) or k in (V2_K_MULT_GRID[0], V2_K_MULT_GRID[-1])
    return {"c_mult": c, "k_mult": k, "loss": loss, "mu": mu, "on_grid_edge": edge}, rows
