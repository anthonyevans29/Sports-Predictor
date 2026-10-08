"""
NCAA v1 gate (#79, architect ruling 2026-09-30) — the NHL Phase 2 harness
shape (src/walters/nhl_backtest.py) for college football.

THE GATE IS WRITTEN FIRST (see BACKLOG "#79 NCAA v1"). This module
implements exactly that protocol and prints a verdict against the frozen
numbers. It writes NOTHING: no predictions, no model rows, no exports. NCAA
stays MARKET-ONLY by doctrine; a PASS earns the architect's promotion
ruling, not production wiring.

Protocol:
  * Stream: Sport.NFL family, Competition.code == "NCAA" (college football
    is stored in the NFL family — the NFL paths pin code "NFL" via
    nfl_backtest.nfl_scoped; this one pins "NCAA"), FINISHED, both scores
    present. FT/AOT both decided games (the provider's totals include OT).
  * Preseason EXCLUDED (stage marker "pre", the NFL/NHL rule).
  * Postseason EXCLUDED (stage marker "post"): bowls and most CFP games are
    neutral-site, and the DB stores NO neutral flag and no venue for this
    family, so a postseason home/away label is arbitrary. ARCHITECT-RULE.
  * Regular-season neutral-site games (kickoff classics, Army-Navy, rivalry
    games at neutral stadiums) cannot be identified from the stored fields;
    they stay IN, labelled as the provider labels them. Known limitation;
    it biases the home rate toward 0.5 identically for baseline and
    candidate. ARCHITECT-RULE.
  * LABELS (ARCHITECT 2026-10-07, CFBD label lane, ruling (2)): "The NCAA
    stream reads orientation, score and neutral from the side table where a
    row exists and prints the uncovered share per season." load_games applies
    ncaa_cfbd_labels; uncovered games read from the matches row. The neutral
    flag is carried on Game as data only — no model input, no constant
    changed, the frozen criteria below untouched.
  * Warm-up (train) = season "2025" (update only); scored (test) = season
    "2026", predict-then-update (walk-forward). 2026 is IN PROGRESS: the test
    set is whatever 2026 games are FINISHED at run time — the report prints
    n and the date range. Other seasons in the DB are ignored (counted).
  * Outcome: binary home win (college football cannot tie; a tied final is
    a data defect, skipped and counted).
  * Baselines on the test season: constant 0.5, and the home rate REALIZED
    IN THE TRAIN SEASON (frozen before any test game is scored).
  * A team with no prior game (FCS / lower-division programs appear rarely;
    743 programs) prices at the default rating; the report counts those
    cold-start test games (information only).

Frozen acceptance (declared before any result exists; ties are rejections):
  0. coverage: test n >= 500 finished games, else INVALID (not scored).
     ARCHITECT-RULE (the in-progress season; the cup-exam coverage-floor
     precedent).
  1. candidate test log-loss <= home-rate baseline - 0.010 (float-safe
     inclusive; an exact tie with the bar passes, a tie with the baseline
     is a rejection) — the NHL margin verbatim.
  2. every 10pp probability band with n >= 100 calibrates within ±5pp
     (inclusive, float-safe) — the NHL rule verbatim.
  3. final ratings all within 1000-2000 (1500 ± 500; outliers FAIL unless
     the architect names a reason). ARCHITECT-RULE: wider than the NHL's
     1200-1800 because college football's true strength spread (FBS to
     lower-division programs) is far wider than a 32-team league's;
     ±500 Elo = a 95% win expectancy against an average program.
Brier and RPS print for INFORMATION ONLY (binary outcome: RPS == Brier).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

NCAA_COMPETITION_CODE = "NCAA"
TRAIN_SEASON = "2025"
TEST_SEASON = "2026"

# ARCHITECT ruling 2026-10-01 (NCAA audit): the 2025 home/away labels are
# UNRELIABLE (FBS home rate 0.404 / margin −6.05; August 0.335; vs 2026 FBS
# 0.773 / +19). The gate is SUSPENDED-PENDING-DATA — not failed — until a
# season with sane stage-level home rates exists on BOTH sides of the split;
# v1's verdict is VOID (trained on corrupted labels). NCAA stays market-only.
GATE_STATUS = "SUSPENDED-PENDING-DATA"
GATE_STATUS_LINE = ("NCAA GATE: SUSPENDED-PENDING-DATA (ruling 2026-10-01) — 2025 home/away labels "
                    "unreliable AT THE PROVIDER (resync-diff: source matches ours); v1's verdict VOID; "
                    "NCAA stays market-only; reopens via an alternative source (#176).")

# FROZEN (architect ruling 2026-09-30 + BACKLOG "#79 NCAA v1").
LL_MARGIN = 0.010
BAND_MIN_N = 100
BAND_TOL = 0.05
RATING_MIN, RATING_MAX = 1000.0, 2000.0
MIN_TEST_N = 500
EPS = 1e-12


@dataclass(frozen=True)
class Game:
    home_id: int
    away_id: int
    season: str
    utc_date: datetime
    home_score: int
    away_score: int
    stage: str = ""
    # CFBD label lane (ARCHITECT 2026-10-07, ruling (2)): where the side table
    # ncaa_cfbd_labels has a row, home/away and the scores above are CFBD's and
    # `neutral` carries CFBD's flag; otherwise they are the matches row's and
    # neutral is None (unknown, law 4). `neutral` is DATA ONLY: no model reads
    # it ("No model change in this lane").
    neutral: bool | None = None
    label_source: str = "matches"          # "cfbd" | "matches"
    orientation: str | None = None         # CFBD row: "same" | "swapped"
    score_corrected: bool = False          # CFBD row whose scores differ from the matches row
    match_id: int | None = None
    # J4 (ARCHITECT 2026-10-08): CFBD's seasonType as served, from the side table; DATA ONLY (no rule reads it:
    # the postseason rule is the architect's to rule after the re-ingest).
    season_type: str | None = None
    # L3 (ARCHITECT 2026-10-08, addendum 11): the label's CFBD game id, CFBD season (the --year) and fetched_at;
    # the v1r stream admits it only when label_fetched_at equals its season's latest ingest record's (current).
    cfbd_id: int | None = None
    cfbd_season: str | None = None
    label_fetched_at: datetime | None = None

    @property
    def home_win(self) -> int:
        return 1 if self.home_score > self.away_score else 0


class Predictor(Protocol):
    def predict(self, g: Game) -> float: ...
    def update(self, g: Game) -> None: ...
    def ratings(self) -> dict[int, float]: ...


# --------------------------------------------------------------------------
# Stream selection
# --------------------------------------------------------------------------


def exclusion_reason(g: Game) -> str | None:
    """'preseason' / 'postseason' from the stage marker, or None if in."""
    stage = (g.stage or "").lower()
    if "pre" in stage:
        return "preseason"
    if "post" in stage:
        return "postseason"
    return None


@dataclass
class Stream:
    train: list[Game] = field(default_factory=list)
    test: list[Game] = field(default_factory=list)
    excluded: Counter = field(default_factory=Counter)   # (season, reason) -> n
    ties: int = 0
    other_seasons: Counter = field(default_factory=Counter)
    stages: dict[str, Counter] = field(default_factory=dict)


def build_stream(games: list[Game]) -> Stream:
    st = Stream()
    for g in sorted(games, key=lambda x: x.utc_date):
        if g.season not in (TRAIN_SEASON, TEST_SEASON):
            st.other_seasons[g.season] += 1
            continue
        st.stages.setdefault(g.season, Counter())[g.stage or "—"] += 1
        why = exclusion_reason(g)
        if why:
            st.excluded[(g.season, why)] += 1
            continue
        if g.home_score == g.away_score:   # college football cannot tie
            st.ties += 1
            continue
        (st.train if g.season == TRAIN_SEASON else st.test).append(g)
    return st


# --------------------------------------------------------------------------
# Scoring (pure)
# --------------------------------------------------------------------------


def beats_margin(ll_model: float, ll_home: float) -> bool:
    """Criterion 1, inclusive and float-safe (the NHL beats_margin rule): an
    exact 0.010 improvement passes; a tie with the baseline is a rejection."""
    return (ll_home - ll_model) >= LL_MARGIN - 1e-12


def _ll(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _brier(p: float, y: int) -> float:
    return (p - y) ** 2


def _rps(p: float, y: int) -> float:
    """Ranked probability score over the ordered outcomes (away, home): one
    threshold, so it equals the Brier score for a binary outcome. Printed
    for information only."""
    return ((1 - p) - (1 - y)) ** 2


@dataclass
class GateResult:
    n_train: int = 0
    n_test: int = 0
    test_first: datetime | None = None
    test_last: datetime | None = None
    home_rate: float = 0.0
    test_home_rate: float = 0.0
    ll_const: float = 0.0
    ll_home: float = 0.0
    brier_const: float = 0.0
    brier_home: float = 0.0
    ll_model: float | None = None
    brier_model: float | None = None
    rps_model: float | None = None
    cold_start_games: int = 0
    teams_rated: int = 0
    bands: list[dict] = field(default_factory=list)
    rating_min: float | None = None
    rating_max: float | None = None
    outliers: list[tuple[int, float]] = field(default_factory=list)
    crit_ll: bool = False
    crit_bands: bool = False
    crit_spread: bool = False
    verdict: str = ""

    @property
    def bar(self) -> float:
        """The frozen log-loss bar the candidate must meet (need <= bar)."""
        return self.ll_home - LL_MARGIN


def baselines(stream: Stream) -> GateResult:
    """The two baselines on the test season. Home rate = the TRAIN season's
    realized home-win rate, frozen before any test game is scored."""
    r = GateResult(n_train=len(stream.train), n_test=len(stream.test))
    if not stream.train or not stream.test:
        r.verdict = "INVALID — protocol needs both seasons"
        return r
    r.test_first, r.test_last = stream.test[0].utc_date, stream.test[-1].utc_date
    r.home_rate = sum(g.home_win for g in stream.train) / len(stream.train)
    r.test_home_rate = sum(g.home_win for g in stream.test) / len(stream.test)
    n = len(stream.test)
    r.ll_const = sum(_ll(0.5, g.home_win) for g in stream.test) / n
    r.ll_home = sum(_ll(r.home_rate, g.home_win) for g in stream.test) / n
    r.brier_const = sum(_brier(0.5, g.home_win) for g in stream.test) / n
    r.brier_home = sum(_brier(r.home_rate, g.home_win) for g in stream.test) / n
    if n < MIN_TEST_N:
        r.verdict = (f"INVALID — insufficient coverage: {n} finished {TEST_SEASON} games "
                     f"< {MIN_TEST_N} (re-run later in the season; the bar does not move)")
    return r


def calibration_bands(pairs: list[tuple[float, int]]) -> list[dict]:
    buckets: dict[int, list[tuple[float, int]]] = {}
    for p, y in pairs:
        buckets.setdefault(int(min(max(p, 0.0), 0.9999) * 10), []).append((p, y))
    out = []
    for b in sorted(buckets):
        obs = buckets[b]
        stated = sum(p for p, _ in obs) / len(obs)
        realized = sum(y for _, y in obs) / len(obs)
        gated = len(obs) >= BAND_MIN_N
        out.append({"band": b, "n": len(obs), "stated": stated, "realized": realized,
                    "gap": realized - stated, "gated": gated,
                    "ok": (abs(realized - stated) <= BAND_TOL + 1e-12) if gated else None})
    return out


def run_gate(stream: Stream, model: Predictor) -> GateResult:
    """Walk-forward: warm-up updates only; test predicts-then-updates."""
    r = baselines(stream)
    if r.verdict:
        return r
    seen: set[int] = set()
    for g in stream.train:
        model.update(g)
        seen.update((g.home_id, g.away_id))
    pairs, ll, br, rp = [], 0.0, 0.0, 0.0
    for g in stream.test:
        if g.home_id not in seen or g.away_id not in seen:
            r.cold_start_games += 1
        p = model.predict(g)
        pairs.append((p, g.home_win))
        ll += _ll(p, g.home_win)
        br += _brier(p, g.home_win)
        rp += _rps(p, g.home_win)
        model.update(g)
        seen.update((g.home_id, g.away_id))
    n = len(stream.test)
    r.ll_model, r.brier_model, r.rps_model = ll / n, br / n, rp / n
    r.bands = calibration_bands(pairs)

    ratings = model.ratings()
    r.teams_rated = len(ratings)
    if ratings:
        r.rating_min, r.rating_max = min(ratings.values()), max(ratings.values())
        r.outliers = sorted((t, v) for t, v in ratings.items()
                            if not RATING_MIN <= v <= RATING_MAX)

    r.crit_ll = beats_margin(r.ll_model, r.ll_home)
    r.crit_bands = all(b["ok"] for b in r.bands if b["gated"])
    r.crit_spread = not r.outliers
    if r.crit_ll and r.crit_bands and r.crit_spread:
        r.verdict = ("PASS — the architect rules on promotion (NCAA stays market-only "
                     "until then; no production wiring in this lane)")
    else:
        why = [n_ for n_, ok in (("log-loss margin", r.crit_ll), ("calibration", r.crit_bands),
                                 ("rating spread", r.crit_spread)) if not ok]
        r.verdict = "FAIL — " + ", ".join(why)
    return r


# --------------------------------------------------------------------------
# DB loading + report
# --------------------------------------------------------------------------


def game_from_rows(m, label=None) -> Game:
    """One stream game. With a ncaa_cfbd_labels row, orientation, scores and
    neutral come from it (CFBD, the label source of record); without one, from
    the matches row (ruling (2)). The side table stores the source's scores in
    OUR orientation, so a 'swapped' row flips the teams AND the scores together.
    A row with an orientation outside {'same', 'swapped'} is not used (law 4)."""
    if label is None or label.orientation not in ("same", "swapped"):
        return Game(m.home_team_id, m.away_team_id, m.season, m.utc_date, m.home_score, m.away_score,
                    m.stage or "", match_id=m.id)
    corrected = (label.home_score, label.away_score) != (m.home_score, m.away_score)
    st = label.__dict__.get("season_type") if hasattr(label, "__dict__") else None   # unloaded pre-J4: None
    if label.orientation == "swapped":
        return Game(m.away_team_id, m.home_team_id, m.season, m.utc_date, label.away_score, label.home_score,
                    m.stage or "", neutral=label.neutral, label_source="cfbd", orientation="swapped",
                    score_corrected=corrected, match_id=m.id, season_type=st,
                    cfbd_id=getattr(label, "source_game_id", None),
                cfbd_season=getattr(label, "season", None), label_fetched_at=getattr(label, "fetched_at", None))
    return Game(m.home_team_id, m.away_team_id, m.season, m.utc_date, label.home_score, label.away_score,
                m.stage or "", neutral=label.neutral, label_source="cfbd", orientation="same",
                score_corrected=corrected, match_id=m.id, season_type=st,
                cfbd_id=getattr(label, "source_game_id", None),
                cfbd_season=getattr(label, "season", None), label_fetched_at=getattr(label, "fetched_at", None))


def load_games() -> list[Game]:
    """Read-only: FINISHED, scored NCAA rows (Sport.NFL + code "NCAA"), with the
    CFBD side table's orientation / scores / neutral applied where a row exists
    (before migrate_ncaa_cfbd_labels.py runs, every game reads from matches)."""
    from sqlalchemy import inspect, select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, Sport
    from src.ingestion.ncaa_cfbd import label_load_options

    with session_scope() as s:
        rows = s.execute(
            select(Match)
            .join(Competition, Match.competition_id == Competition.id)
            .where(
                Match.sport == Sport.NFL,
                Competition.code == NCAA_COMPETITION_CODE,   # never the NFL rows
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars().all()
        labels = {}
        if inspect(s.connection()).has_table(NCAACFBDLabel.__tablename__):
            labels = {r.match_id: r for r in s.execute(select(NCAACFBDLabel)
                                                       .options(*label_load_options(s))).scalars()}
        return [game_from_rows(m, labels.get(m.id)) for m in rows]


# --------------------------------------------------------------------------
# Label coverage (CFBD side table; ARCHITECT 2026-10-07, restated 2026-10-08)
# --------------------------------------------------------------------------

# SCOPE (ARCHITECT 2026-10-08): "My 2026-10-07 coverage condition is restated
# for that stream: the side table labels at least 95% of CFBD's completed
# both-FBS games in each season used, read from the ingest receipt (joined over
# in scope), every unmatched game listed." The 95% condition is therefore
# src/ingestion/ncaa_cfbd.fbs_coverage / stored_coverage (denominator: CFBD's
# completed both-FBS games), NOT label_coverage below, which divides by every
# kept game of #79's all-division stream and stays as #79's information print
# (ruling (2) of 2026-10-07: "prints the uncovered share per season").
# Nothing here changes GATE_STATUS.
from src.ingestion.ncaa_cfbd import COVERAGE_MIN  # noqa: E402  (stdlib-only module: no cycle)


def _home_rate(games: list[Game]) -> float | None:
    return (sum(g.home_win for g in games) / len(games)) if games else None


def label_coverage(stream: Stream) -> dict[str, dict]:
    """#79's all-division stream, per season, over the games the gate KEEPS
    (train / test after its exclusions): covered by the side table, uncovered
    share, swapped, neutral, score-corrected, and home rates. INFORMATION: this
    is not the 95% condition (its denominator is every stream game, all
    divisions; the condition's is CFBD's completed both-FBS games)."""
    out = {}
    for season, kept in ((TRAIN_SEASON, stream.train), (TEST_SEASON, stream.test)):
        cov = [g for g in kept if g.label_source == "cfbd"]
        unc = [g for g in kept if g.label_source != "cfbd"]
        nonneutral = [g for g in cov if g.neutral is False]
        n = len(kept)
        out[season] = {
            "n": n, "covered": len(cov), "uncovered": len(unc),
            "covered_share": (len(cov) / n) if n else None,
            "uncovered_share": (len(unc) / n) if n else None,
            "swapped": sum(1 for g in cov if g.orientation == "swapped"),
            "neutral": sum(1 for g in cov if g.neutral),
            "score_corrected": sum(1 for g in cov if g.score_corrected),
            "home_rate_all": _home_rate(kept),
            "home_rate_nonneutral": _home_rate(nonneutral), "n_nonneutral": len(nonneutral),
            "home_rate_uncovered": _home_rate(unc),
        }
    return out


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _rate(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def coverage_lines(stream: Stream) -> list[str]:
    """The uncovered share per season, printed on every gate run (ruling (2))."""
    cov = label_coverage(stream)
    return [f"  {season} labels: CFBD side table covers {c['covered']}/{c['n']} ({_pct(c['covered_share'])}) · "
            f"UNCOVERED share {_pct(c['uncovered_share'])} (read from the matches row) · swapped "
            f"{c['swapped']} · neutral {c['neutral']} (data only, no model input) · score-corrected "
            f"{c['score_corrected']}"
            for season, c in ((s_, cov[s_]) for s_ in (TRAIN_SEASON, TEST_SEASON))]


# --------------------------------------------------------------------------
# The ncaa-elo-v1r stream (SCOPE + J2, ARCHITECT 2026-10-08)
# --------------------------------------------------------------------------

# SCOPE (verbatim): "ncaa-elo-v1r is an FBS model. Its stream is the games that
# carry a CFBD both-FBS label; a stored game without one is neither walked nor
# scored, in the gate and in the shadow." J2 (verbatim): "In the v1r stream and
# the shadow, team ids whose unescaped names are identical are one team, keyed
# by the lowest id; the receipt lists every such group and every name that
# changes." #79's all-division stream (load_games + build_stream) stays as
# declared; nothing here touches its acceptance numbers.


@dataclass
class TeamMerge:
    canon: dict[int, int] = field(default_factory=dict)            # team id -> lowest id of its group
    groups: list[list[tuple[int, str]]] = field(default_factory=list)   # every group of >= 2 ids
    changed: list[tuple[int, str, str]] = field(default_factory=list)   # (id, stored, unescaped)

    def __call__(self, team_id: int) -> int:
        return self.canon.get(team_id, team_id)

    def lines(self) -> list[str]:
        L = [f"  J2 team merge (read-time mapping; the teams table is never written): {len(self.groups)} "
             f"group(s) · {len(self.changed)} name(s) changed by html.unescape"]
        for grp in self.groups:
            L.append(f"    one team, keyed {grp[0][0]}: " + " · ".join(f"{tid} {name!r}" for tid, name in grp))
        L += [f"    name changes: team {tid} {n!r} -> {u!r}" for tid, n, u in self.changed]
        return L


def team_merge(teams: dict[int, str]) -> TeamMerge:
    """J2: ids whose html-unescaped names are IDENTICAL (exact string equality
    after html.unescape, no other normalization) are one team, keyed by the
    lowest id. Pure; a mapping applied at read time, never a DB write."""
    import html

    by_name: dict[str, list[int]] = {}
    for tid, name in teams.items():
        by_name.setdefault(html.unescape(name or ""), []).append(tid)
    tm = TeamMerge()
    for name, ids in sorted(by_name.items(), key=lambda kv: min(kv[1])):
        ids = sorted(ids)
        if len(ids) > 1:
            tm.groups.append([(t, teams[t]) for t in ids])
            for t in ids:
                tm.canon[t] = ids[0]
    tm.changed = sorted((tid, n, html.unescape(n)) for tid, n in teams.items() if n and html.unescape(n) != n)
    return tm


# ncaa-elo-v1r DECLARATION (ARCHITECT 2026-10-08, addendum 11 item 3; docs/specs/ncaa-elo-v1r.md), D2 verbatim:
# "Stream: stored NCAA games that carry a current CFBD both-FBS label, seasons 2024, 2025 and 2026, in order of
# stored kickoff then match id. Home and away, the scores and the neutral flag come from the label; team ids are
# merged as J2 rules. Every such game is walked, postseason included. A game with level scores is a data defect:
# skipped, counted and listed." D6: the shadow refuses unless all three seasons are covered (L2 + L3).
# The season of a game in this stream is its LABEL's season (the CFBD year the ingest record is keyed by).
V1R_SEASONS = ("2024", "2025", "2026")
V1R_WARMUP, V1R_TEST = "2024", "2025"     # D3 (the gate itself is PR B)
NO_SEASON_TYPE = "(none)"


class NeutralRuleElo:
    """D1 (verbatim): "NCAAEloV1 with its constants untouched [...] neutral_site_rule is
    no_home_advantage_at_neutral: a game whose label says neutral is priced and updated with home advantage 0. A
    label without a neutral flag is treated as non-neutral and counted." NCAAEloV1 has no neutral input, so this
    thin wrapper swaps the model's cfg for dataclasses.replace(cfg, home_advantage=0.0) for the duration of the
    predict / update call of a game whose `neutral` is True, then restores it. The v1 math is untouched. Shared by
    the shadow (ncaa_shadow.V1R) and the design receipt (scripts/ncaa_v1r_design_receipt.py).
    `neutral_home_advantage` True = the other declarable rule (home advantage at neutral sites too)."""

    def __init__(self, neutral_home_advantage: bool = False):
        from src.models.ncaa_elo import NCAAEloConfig, NCAAEloV1

        self.cfg = NCAAEloConfig()
        self.m = NCAAEloV1(self.cfg)
        self.neutral_home_advantage = neutral_home_advantage
        self.neutral_updates = 0
        self.unflagged_updates = 0          # a label without a neutral flag: non-neutral, counted (D1)

    def home_adv(self, g) -> float:
        if not self.neutral_home_advantage and getattr(g, "neutral", None) is True:
            return 0.0
        return self.cfg.home_advantage

    def _call(self, fn, g):
        from dataclasses import replace

        ha = self.home_adv(g)
        if ha == self.cfg.home_advantage:
            return fn(g)
        self.m.cfg = replace(self.cfg, home_advantage=ha)
        try:
            return fn(g)
        finally:
            self.m.cfg = self.cfg

    def predict(self, g) -> float:
        return self._call(self.m.predict, g)

    def update(self, g) -> None:
        nf = getattr(g, "neutral", None)
        if nf is True:
            self.neutral_updates += 1
        elif nf is None and getattr(g, "label_source", None) == "cfbd":
            self.unflagged_updates += 1
        self._call(self.m.update, g)

    def rating(self, team_id: int) -> float:
        return self.m.rating(team_id)

    def ratings(self) -> dict[int, float]:
        return self.m.ratings()


@dataclass
class V1RStream:
    games: list[Game]                                         # D2: walked, kickoff then match id
    merge: TeamMerge
    unlabelled: Counter = field(default_factory=Counter)   # season -> stored games without a current label
    labelled: Counter = field(default_factory=Counter)     # CFBD season -> current labels (every season)
    stale: list[str] = field(default_factory=list)         # L3: stale labels (kept, counted, listed, never walked)
    level: list[str] = field(default_factory=list)         # D2: level scores (a data defect: skipped, listed)
    level_by_season: Counter = field(default_factory=Counter)
    outside: Counter = field(default_factory=Counter)      # current labels outside V1R_SEASONS (not walked)
    census: dict[str, dict[str, int]] = field(default_factory=dict)   # season -> season_type -> walked games
    neutral: Counter = field(default_factory=Counter)      # season -> walked games labelled neutral
    unflagged: Counter = field(default_factory=Counter)    # season -> walked games whose label has no neutral flag

    def by_season(self, season: str) -> list[Game]:
        return [g for g in self.games if g.season == season]

    def lines(self) -> list[str]:
        L = ["NCAA-ELO-V1R STREAM (D2, ARCHITECT 2026-10-08, addendum 11 item 3): stored games carrying a CURRENT "
             f"CFBD both-FBS label, seasons {', '.join(V1R_SEASONS)} (the label's season), kickoff then match id, "
             "postseason included; a game without one is neither walked nor scored"]
        for season in V1R_SEASONS:
            walked = self.by_season(season)
            nn = [g for g in walked if g.neutral is not True]
            L.append(f"  {season}: walked {len(walked)} · by season_type {self.census.get(season, {})} · neutral "
                     f"{self.neutral[season]} (home advantage 0, D1) · no neutral flag {self.unflagged[season]} "
                     f"(non-neutral, counted) · level scores {self.level_by_season[season]} · home win rate "
                     f"non-neutral {_rate(_home_rate(nn))} (n {len(nn)})")
        for season in sorted(set(self.labelled) | set(self.unlabelled)):
            L.append(f"  {season}: current labels {self.labelled[season]} · unlabelled or stale "
                     f"{self.unlabelled[season]} (NOT walked, NOT scored)")
        if self.outside:
            L.append(f"  current labels outside {', '.join(V1R_SEASONS)} (not walked): {dict(sorted(self.outside.items()))}")
        L.append(f"  LEVEL SCORES (D2: a data defect; skipped, counted, listed): {len(self.level)}")
        L += [f"    {x}" for x in self.level]
        L.append(f"  STALE labels (L3: fetched_at is not their season's latest ingest record's; kept, never "
                 f"walked): {len(self.stale)}")
        L += [f"    {x}" for x in self.stale]
        return L + self.merge.lines()


def v1r_stream(games: list[Game], teams: dict[int, str], stamps: dict[str, datetime]) -> V1RStream:
    """D2 + L3 + J2. Keep only games carrying a CURRENT CFBD label. L3 (verbatim): "A label is current when its
    fetched_at equals that of its season's latest ingest record. The v1r stream and the shadow's FBS team set
    read current labels only. A stale label is kept, counted and listed, never walked." `stamps` =
    ncaa_cfbd.latest_record_stamps ({CFBD season: latest record's fetched_at}). The season is the label's (CFBD)
    season; only V1R_SEASONS are walked. Home / away, scores and the neutral flag are the label's (game_from_rows
    already applied them). Both team ids mapped through team_merge. Order: stored kickoff, then match id. Every
    game walked, postseason included (no stage exclusion); a level score is skipped, counted and listed. Pure."""
    from dataclasses import replace

    tm = team_merge(teams)
    v = V1RStream([], tm)
    kept = []
    for g in games:
        if g.label_source != "cfbd":
            v.unlabelled[g.season] += 1
            continue
        at = stamps.get(g.cfbd_season or "")
        if at is None or g.label_fetched_at != at:
            v.unlabelled[g.season] += 1
            v.stale.append(f"match {g.match_id} · CFBD {g.cfbd_id} · CFBD season {g.cfbd_season} · label fetched_at "
                           f"{g.label_fetched_at} vs latest record "
                           + (f"{at}" if at is not None else "— (no ingest record for the season)"))
            continue
        season = str(g.cfbd_season)
        v.labelled[season] += 1
        if season not in V1R_SEASONS:
            v.outside[season] += 1
            continue
        kept.append(replace(g, home_id=tm(g.home_id), away_id=tm(g.away_id), season=season))
    for g in sorted(kept, key=lambda x: (x.utc_date, x.match_id if x.match_id is not None else -1)):
        if g.home_score == g.away_score:
            v.level_by_season[g.season] += 1
            v.level.append(f"match {g.match_id} · CFBD {g.cfbd_id} · CFBD season {g.season} · {g.utc_date} · "
                           f"{g.home_score}-{g.away_score}")
            continue
        v.games.append(g)
        c = v.census.setdefault(g.season, {})
        st = g.season_type if g.season_type else NO_SEASON_TYPE
        c[st] = c.get(st, 0) + 1
        if g.neutral is True:
            v.neutral[g.season] += 1
        elif g.neutral is None:
            v.unflagged[g.season] += 1
    return v


def load_v1r_stream(games: list[Game] | None = None) -> V1RStream:
    """Read-only: load_games() (or `games`) restricted to the v1r stream: current labels only (L3), the team
    merge built over every team in an NCAA match."""
    from src.db.database import session_scope
    from src.ingestion.ncaa_cfbd import latest_record_stamps, ncaa_teams

    with session_scope() as s:
        teams = ncaa_teams(s)
        stamps = latest_record_stamps(s)
        s.rollback()
    return v1r_stream(load_games() if games is None else games, teams, stamps)


def coverage_report(stream: Stream, out: Callable[[str], None] = print, fbs: dict | None = None,
                    v1r: V1RStream | None = None) -> dict[str, dict]:
    """`ncaa-cfbd-coverage`: the per-season receipt the architect reads.
    `fbs` = ncaa_cfbd.stored_coverage (the SCOPE condition: labelled / CFBD's
    completed both-FBS games, >= 95%, every unlabelled game listed); `stream`
    = #79's all-division stream (information); `v1r` = the v1r stream receipt.
    States the condition as a computed fact; never declares the gate un-suspended."""
    from src.ingestion.ncaa_cfbd import stored_coverage_lines

    cov = label_coverage(stream)
    out(f"NCAA CFBD LABEL COVERAGE · SCOPE condition (ARCHITECT 2026-10-08): the side table labels >= "
        f"{COVERAGE_MIN:.0%} of CFBD's completed both-FBS games in EACH of {', '.join(V1R_SEASONS)} (ncaa-elo-v1r "
        f"D6: the shadow needs all three, the gate run {V1R_WARMUP} and {V1R_TEST}) "
        f"(L2: the season's latest ingest record; never the payload, never our stream)")
    if fbs is None:
        out("  (not computed: no session)")
        held = False
    else:
        for line in stored_coverage_lines(fbs):
            out(line)
        held = all(fbs.get(s_, {}).get("ok") for s_ in V1R_SEASONS)
    out(f"  coverage condition in ALL THREE seasons ({', '.join(V1R_SEASONS)}): "
        f"{'HOLDS' if held else 'DOES NOT HOLD'} (computed fact)")
    if v1r is not None:
        for line in v1r.lines():
            out(line)
    out(f"#79 ALL-DIVISION STREAM (information; declared 2026-09-30, unchanged): FINISHED, both scores, "
        f"pre/postseason excluded, ties skipped")
    for season in (TRAIN_SEASON, TEST_SEASON):
        c = cov[season]
        out(f"  {season}: stream games {c['n']} · covered {c['covered']} ({_pct(c['covered_share'])}) · "
            f"uncovered {c['uncovered']} ({_pct(c['uncovered_share'])}) · swapped {c['swapped']} · neutral "
            f"{c['neutral']} · score-corrected {c['score_corrected']}")
        out(f"    home win rate: non-neutral (covered, CFBD neutral=False) {_rate(c['home_rate_nonneutral'])} "
            f"(n {c['n_nonneutral']}) · all stream games {_rate(c['home_rate_all'])} · uncovered games "
            f"(matches-row labels, no neutral flag) {_rate(c['home_rate_uncovered'])} (n {c['uncovered']})")
    out(f"  {TRAIN_SEASON} non-neutral home rate for the sanity read: "
        f"{_rate(cov[TRAIN_SEASON]['home_rate_nonneutral'])} — the architect reads it")
    out(f"  {GATE_STATUS_LINE} This receipt does not change it: un-suspension is the architect's read.")
    return cov


def report(stream: Stream, r: GateResult, out: Callable[[str], None] = print,
           model_name: str | None = None) -> None:
    out(f"NCAA v1 gate (#79) · train {TRAIN_SEASON} · test {TEST_SEASON} (in progress: "
        f"finished games at run time)")
    for season in (TRAIN_SEASON, TEST_SEASON):
        ex = {why: n for (s_, why), n in stream.excluded.items() if s_ == season}
        kept = stream.train if season == TRAIN_SEASON else stream.test
        teams = {t for g in kept for t in (g.home_id, g.away_id)}
        out(f"  {season}: kept {len(kept)} games / {len(teams)} programs · excluded "
            f"preseason {ex.get('preseason', 0)}, postseason {ex.get('postseason', 0)}")
        out(f"    stage values: {dict(stream.stages.get(season, {}))}")
    for line in coverage_lines(stream):
        out(line)
    if stream.other_seasons:
        out(f"  other seasons ignored: {dict(sorted(stream.other_seasons.items()))}")
    if stream.ties:
        out(f"  ⚠ {stream.ties} tied finals skipped (college football cannot tie — data defect)")
    out("  neutral sites: CFBD's flag rides on covered games as DATA only (ruling 2026-10-07: no model "
        "change); neutral-site games stay in the stream as labelled (known limitation)")
    if r.verdict.startswith("INVALID") and not r.n_train:
        out(f"VERDICT: {r.verdict}")
        return
    if r.test_first is not None:
        out(f"TEST SET: n={r.n_test} finished {TEST_SEASON} games, "
            f"{r.test_first.date().isoformat()} .. {r.test_last.date().isoformat()} (UTC) · "
            f"realized home rate {r.test_home_rate:.4f}")
    if r.verdict.startswith("INVALID") and not r.n_test:
        out(f"VERDICT: {r.verdict}")
        return
    out(f"BASELINES (test season, n={r.n_test})")
    out(f"  constant 0.5          log-loss {r.ll_const:.4f}  brier {r.brier_const:.4f}")
    out(f"  train home rate       log-loss {r.ll_home:.4f}  brier {r.brier_home:.4f}  "
        f"(p_home = {r.home_rate:.4f}, realized in {TRAIN_SEASON}, n={r.n_train})")
    out(f"BAR (frozen): candidate log-loss need <= {r.bar:.4f}  "
        f"(home-rate baseline {r.ll_home:.4f} - {LL_MARGIN:.3f}; a tie is a rejection)")
    if r.verdict.startswith("INVALID"):
        out(f"VERDICT: {r.verdict}")
        return
    if r.ll_model is None:
        out("  (baselines only — no candidate model scored)")
        return
    out(f"CANDIDATE {model_name or ''}")
    out(f"  1) log-loss {r.ll_model:.4f} vs need <= {r.bar:.4f} "
        f"-> {'PASS' if r.crit_ll else 'FAIL'}")
    out(f"  2) calibration (10pp bands; gated when n >= {BAND_MIN_N}, tolerance ±{BAND_TOL*100:.0f}pp)")
    for b in r.bands:
        tag = ("ok" if b["ok"] else "FAIL") if b["gated"] else f"(n < {BAND_MIN_N}, not gated)"
        out(f"     {b['band']*10:>2}-{b['band']*10+10}%: n={b['n']:<4} stated {b['stated']:.3f} "
            f"realized {b['realized']:.3f} gap {b['gap']*100:+.1f}pp {tag}")
    out(f"  3) final ratings {r.rating_min:.0f}-{r.rating_max:.0f} over {r.teams_rated} programs "
        f"(bound {RATING_MIN:.0f}-{RATING_MAX:.0f})"
        + (f" OUTLIERS {r.outliers}" if r.outliers else "") + f" -> {'PASS' if r.crit_spread else 'FAIL'}")
    out(f"  info (not gated): brier {r.brier_model:.4f} · rps {r.rps_model:.4f} · "
        f"cold-start test games (a side with no prior game) {r.cold_start_games}/{r.n_test}")
    out(f"GATE VERDICT: {r.verdict}")
