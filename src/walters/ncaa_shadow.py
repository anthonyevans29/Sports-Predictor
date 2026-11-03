"""
NCAA SHADOW (ARCHITECT 2026-10-07, addendum 6 item 1, verbatim):
"NCAA SHADOW. Once #333's coverage receipt shows 95% on both seasons and
ncaa-elo-v1r is declared in the registry with its constants frozen, ship
export-ncaa-predictions and ncaa-shadow-grade on the NHL shadow's pattern:
engine model_shadow, the gate status on every row ('UNGATED — shadow only'
until the verdict, then the verdict), FBS games in the next 36 hours, the
market block beside each row, graded on results and on model-vs-close from
the last shadow file before kickoff. Never a call, never a venue input, never
in the ledger. The shadow starts before the gate run and changes nothing
about it: the one run, the verdict and the confirmation cohort stand as
declared, and the shadow's live record is not gate evidence. Target: the
Saturday 2026-10-10 slate. If the labels are not in by Friday night, say so
and Saturday stays market-only."

    export-ncaa-predictions  -> exports/ncaa_shadow_<YYYY-MM-DD_HHMM>.json
    ncaa-shadow-grade        -> results + model-vs-close, from the artifacts

THE PRECONDITIONS ARE CODE, NOT A CHECKLIST: the export REFUSES (exit 2,
reason stated) unless
  (a) the registry holds ncaa-elo-v1r (docs/registry/experiments.json), and
      its declaration states the neutral-site rule (NEUTRAL_RULE_KEY, one of
      NEUTRAL_RULES): "Whether v1r applies home advantage at neutral sites is
      a declaration question" (#333 ruling), so the shadow never chooses it;
  (b) SCOPE (ARCHITECT 2026-10-08): "The shadow's precondition is that same
      fact": the side table labels >= 95% of CFBD's completed both-FBS games
      in EACH season used (D6: 2024, 2025, 2026), re-read by
      ncaa_cfbd.stored_coverage (the denominator is the saved CFBD payload
      the side table names, never our stream);
  (c) ARCHITECT 2026-10-09, addendum 24 item 2(d): the registry records no
      verdict for ncaa-elo-v1r other than PASS. v1r FAILED (2026-10-09): the
      college shadow does not start on it (VERDICT_REFUSAL, verbatim).
The architect's read of the receipt is what makes (a) happen; (b) is
re-checked on every run so a regressed side table stops the shadow.
D6 (ncaa-elo-v1r declaration, ARCHITECT 2026-10-08, addendum 11 item 3,
verbatim): "the shadow and the confirmation read refuse unless 2024, 2025 and
2026 are [covered as L2 and L3 rule]": the seasons are ncaa_backtest.V1R_SEASONS,
each missing season named.

THE STREAM IS ncaa-elo-v1r's D2 (ARCHITECT 2026-10-08, addendum 11 item 3):
stored games carrying a CURRENT CFBD both-FBS label (L3), seasons 2024, 2025
and 2026 (the label's season), in order of stored kickoff then match id,
postseason included, level scores skipped / counted / listed
(ncaa_backtest.v1r_stream); team ids whose html-unescaped names are identical
are one team, keyed by the lowest id (J2, ncaa_backtest.team_merge), for the
walk AND the upcoming games.

THE MODEL IS v1 WITH ITS CONSTANTS UNTOUCHED (the #333 ruling: "ONE scored
run of v1 with its constants untouched, declared beforehand in the registry
as ncaa-elo-v1r"): src/models/ncaa_elo.NCAAEloConfig() defaults, the update
math of NCAAEloV1 verbatim. The only declared input is the neutral rule (D1:
"no_home_advantage_at_neutral"): a game whose label says neutral prices and
updates with home advantage 0 (ncaa_backtest.NeutralRuleElo, shared with the
design receipt); a label without a neutral flag is non-neutral and counted.
D8: every UPCOMING game (no label before the game) is priced with the listed
home's advantage and the row says the neutral flag is unknown (law 4).
Walk-forward over D2's stream, every game before now, then the predictions.

ROWS: engine "model_shadow" (window card and desk_policy already skip it;
never a Desk call, never a venue input, never logged to the ledger),
model_version "ncaa_elo_v1r", competition "NCAA", family "NCAAF",
gate_verdict = "UNGATED — shadow only" until the registry records a verdict,
then that verdict. FBS = both teams appear in the CFBD side table (its
ingest's default scope is both-FBS completed games); a game with a team
outside it is skipped and counted, never priced. The market block is the
fixtures export's own (_fixture_row), beside the prediction.

GRADING READS THE ARTIFACTS: a game's call is the LAST shadow row written
before kickoff. Results: the CFBD side-table score in our orientation where
a row exists, else the matches row; hit rate, log-loss and Brier of the
shadow probability. Model-vs-close: pick-vs-close against the stored 1X2
book close (#167/#207 contract, nfl-grade's rule) and value-side-vs-close
from the earliest pre-kickoff book snapshot. The live record is NOT gate
evidence and says so.

THE v2 BINDING (ARCHITECT 2026-10-23, addendum 158 item 1(b), verbatim): "(b) The v2 shadow: src/walters/ncaa_shadow.py
still binds ncaa-elo-v1r and refuses on its FAIL. Prepare the v2 binding now (registry id, the frozen s =
279.14222651259433, the version, input cutoff and prediction stamp on every row), under the same refusal guard (it
exports nothing unless the registry verdict is PASS), so a PASS on 11-09 leads straight into the confirmation window. A
read-only receipt on synthetic cases that the shadow's probabilities equal the gate path's. One PR, after (a), before
11-08."
  * BINDINGS: one per registry id. `export-ncaa-predictions --id ncaa-elo-v2` runs the v2 binding; the default stays
    v1r, which refuses on its FAIL as before.
  * v2: the registry entry must record a PASS verdict (none, or anything else, refuses), the declaration's neutral rule
    and v1's constants (as v1r's), and the logistic scale s frozen at exactly V2_FROZEN_S (the ruling's number; a
    registry that disagrees refuses). The model is the gate's own: ncaa_backtest.NeutralRuleElo at that s, walked over
    the same D2 stream (2024-2026, current labels, J2 merge).
  * Every row of either binding carries registry_id, model_version, input_cutoff (the walk reads every stream game
    kicking off before it) and prediction_stamp (the export's clock); a v2 row also the logistic scale.
  * parity(): the receipt on synthetic cases. The gate path is ncaa_v1r_gate.run_gate itself, with a recorder around
    the declared model that keeps the probability of every game the gate scores; the shadow path is this module's walk
    over the stream games kicking off before that game, then the prediction. scripts/ncaa_v2_shadow_parity.py prints
    it on a seeded synthetic stream; no DB is read.
  * Grading never pools: ncaa-shadow-grade --id reads only the files its binding wrote.

ncaa-elo-v2's CONFIRMATION MACHINERY (ARCHITECT 2026-11-03, addendum 230 item 1(b), verbatim): "the college shadow
export on the ncaa-schedule chain (the NHL shadow's shape: the entry's probabilities per fixture, market-only, never a
call), its grade against the Kalshi close (the close record's KXNCAAFGAME rule), the neutral flag on each row before
kickoff with its rule stated (never a provider fact), the confirmation counter to 100; dormant while the verdict is null
or FAIL."
  * The chain: ncaa-schedule's last step, `export-ncaa-predictions --id ncaa-elo-v2 --dormant-ok`. frozen()'s verdict
    refusal is ShadowDormant: with --dormant-ok it prints DORMANT and its reason, writes nothing, exit 0; every other
    refusal exits 2 (deploy/hosting/chains.py NCAA_SHADOW_STEP; coverage reads the same preconditions, SHADOW_BINDS).
  * The neutral flag before kickoff: every row states its rule (NEUTRAL_PREGAME_RULE, D8's until a source is ruled).
  * The grade against the Kalshi close: vs_kalshi_close per name, paper.guarded_two_way_close (close_record's own),
    its exclusions counted; the book line stays beside it.
  * The counter to 100: confirmation_counter (ncaa_v1r_gate.confirmation_count: counts, never a figure or a verdict).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive

ENGINE = "model_shadow"
EID = "ncaa-elo-v1r"
MODEL_VERSION = "ncaa_elo_v1r"
COMPETITION = "NCAA"
FAMILY = "NCAAF"
WINDOW_HOURS = 36
FILE_PREFIX = "ncaa_shadow_"
UNGATED = "UNGATED — shadow only"
# The declaration states one of these (the #333 ruling leaves the choice to the declaration PR).
NEUTRAL_RULE_KEY = "neutral_site_rule"
NEUTRAL_RULES = {"home_advantage_at_neutral": True, "no_home_advantage_at_neutral": False}
# Codex on #344: the declaration freezes the constants; the shadow runs only if they are v1's, untouched (#333 ruling)
CONSTANTS_KEY = "constants"
CONSTANT_KEYS = ("k_factor", "home_advantage", "mov_base", "season_regression", "default_rating")
# D8 (ARCHITECT 2026-10-08, addendum 11 item 3, verbatim): "Until then the shadow prices an upcoming game with the
# listed home's advantage and says on the row that the neutral flag is unknown."
NEUTRAL_FLAG_UNKNOWN = "unknown before the game"
HOME_ADV_BASIS = "listed home (neutral flag unknown before the game)"
# THE NEUTRAL FLAG BEFORE KICKOFF, ITS RULE STATED ON EVERY ROW (ARCHITECT 2026-11-03, addendum 230 item 1(b): "the
# neutral flag on each row before kickoff with its rule stated (never a provider fact)"). The rule is D8's until the
# architect rules a pregame source: nothing this repo stores carries a neutral flag for an upcoming college game that
# is ours (ncaa_cfbd's side table labels completed games only, after the game; the american-football adapter stores no
# venue), so the flag is unknown (law 4) and the price stays the listed home's. A rule that derives it changes this
# text and the value together, by a ruling.
NEUTRAL_PREGAME_RULE = (
    "D8 (ncaa-elo-v1r's declaration, ARCHITECT 2026-10-08, addendum 11 item 3; ncaa-elo-v2's D8: \"As v1r's D8\"), "
    "verbatim: \"Until then the shadow prices an upcoming game with the listed home's advantage and says on the row "
    "that the neutral flag is unknown.\" Never a provider fact (ARCHITECT 2026-11-03, addendum 230 item 1(b)): no "
    "stored source of ours carries the flag before kickoff (the CFBD side table labels completed games only; the "
    "american-football adapter stores no venue), so the flag is unknown (law 4) and the listed home's advantage is "
    "applied.")
NOTE = ("NCAA SHADOW — ncaa_elo_v1r (v1, constants untouched) as a model shadow beside the market-only NCAA "
        "Desk. Never a call, never a venue input, never in the ledger. The shadow changes nothing about the "
        "gate: the one run, the verdict and the confirmation cohort stand as declared, and this live record "
        "is NOT gate evidence.")


class ShadowRefused(RuntimeError):
    """A precondition the ruling names is not met: printed with its reason, exit 2, nothing written."""


class ShadowDormant(ShadowRefused):
    """The v2 binding's verdict refusal alone (frozen(), a pass_only binding: no verdict recorded, or a verdict other
    than PASS). ARCHITECT 2026-11-03, addendum 230 item 1(b), for ncaa-elo-v2: "dormant while the verdict is null or
    FAIL". The operator's command still exits 2 on it (a ShadowRefused); the ncaa-schedule chain's step (--dormant-ok)
    prints it as DORMANT, writes nothing and exits 0. Every other refusal (not declared, the neutral rule, the
    constants, s, D6 coverage, a file that exists) is not dormant and exits 2 on either path, and so is v1r's verdict
    refusal (addendum 24 item 2(d): "refuses, exit 2, naming this ruling"): v1r never wakes, so it is never dormant."""

    def __init__(self, msg: str, eid: str = "", verdict=None):
        super().__init__(msg)
        self.eid, self.verdict = eid, verdict


DORMANT_RULING = "ARCHITECT 2026-11-03, addendum 230 item 1(b)"
DORMANT_TEXT = "dormant while the verdict is null or FAIL"


def dormant_reason(eid: str, verdict) -> str:
    """The one short reason every dormant line prints (the chain step, coverage, the counter)."""
    what = "no verdict" if not verdict else f"the verdict {verdict}"
    return f"the registry records {what} for {eid}: {DORMANT_TEXT} ({DORMANT_RULING})"


V2_EID = "ncaa-elo-v2"
V2_MODEL_VERSION = "ncaa_elo_v2"
V2_FROZEN_S = 279.14222651259433            # addendum 158 item 1(b): "the frozen s = 279.14222651259433"
V2_RULING = "ARCHITECT 2026-10-23, addendum 158 item 1(b)"
V2_NOTE = ("NCAA SHADOW — ncaa_elo_v2 (v1's structure and constants, the logistic scale s frozen) as a model shadow "
           "beside the market-only NCAA Desk: the confirmation window's instrument after a PASS. Never a call, never a "
           "venue input, never in the ledger. This live record is NOT gate evidence.")


@dataclass(frozen=True)
class Binding:
    """One registry id the shadow can serve: its model version, its note, whether it exports only on a recorded PASS
    and the frozen logistic scale it requires (None: v1, /400)."""
    eid: str
    model_version: str
    note: str
    pass_only: bool
    scale: float | None
    # the neutral-site rule the gate's model runs (ncaa_v1r_gate.model_for: NeutralRuleElo's default, no home advantage
    # at neutral sites); None = either declared rule (v1r). ARCHITECT 2026-10-26 15:15 ET (#698): "the neutral-rule
    # pin BLOCKS — the binding refuses any rule but the gate's".
    rule: str | None = None


GATE_RULE = "no_home_advantage_at_neutral"
BINDINGS = {EID: Binding(EID, MODEL_VERSION, NOTE, False, None),
            V2_EID: Binding(V2_EID, V2_MODEL_VERSION, V2_NOTE, True, V2_FROZEN_S, GATE_RULE)}


def binding(eid: str = EID) -> Binding:
    if eid not in BINDINGS:
        raise ShadowRefused(f"REFUSED: {eid!r} is not a registry id the NCAA shadow serves ({', '.join(BINDINGS)})")
    return BINDINGS[eid]


# ARCHITECT 2026-10-09, addendum 24 item 2(d), verbatim: the college shadow does not start on v1r. frozen() refuses
# once the registry records a verdict for ncaa-elo-v1r other than PASS (FAIL, 2026-10-09). ncaa-shadow-grade is
# untouched: it has no file to read.
VERDICT_RULING = "ARCHITECT 2026-10-09, addendum 24 item 2(d)"
VERDICT_REFUSAL = ("Addendum 6 item 1 put the verdict on every shadow row once there was one. No shadow file has been "
                   "written, and this verdict says the model is too timid: beside a market its rows would show value "
                   "on every underdog, and that value would be its own miscalibration. export-ncaa-predictions "
                   "refuses, exit 2, naming this ruling, once the registry records a verdict for ncaa-elo-v1r other "
                   "than PASS. The shadow's terms for the next candidate are part of its declaration.")


def frozen(registry_path: str | None = None, eid: str = EID) -> tuple[dict, bool, str]:
    """(entry, home advantage at neutral sites?, rule) from the registry; refuses unless `eid` is declared and its
    declaration states the neutral-site rule and freezes v1's constants. v1r: refuses once the registry records a
    verdict other than PASS (addendum 24 item 2(d)). v2: refuses unless the registry records a PASS (addendum 158
    item 1(b): "it exports nothing unless the registry verdict is PASS")."""
    from src.walters import registry as reg

    b = binding(eid)
    e = reg.get(b.eid, registry_path) if registry_path else reg.get(b.eid)
    if e is None:
        raise ShadowRefused(f"REFUSED: {b.eid} is not declared in docs/registry — the NCAA shadow starts only once "
                            "it is (ARCHITECT 2026-10-07, addendum 6 item 1)")
    verdict = (e.get("verdict") or {}).get("verdict")
    if b.pass_only and str(verdict or "").upper() != "PASS":
        raise ShadowDormant(f"export-ncaa-predictions --id {b.eid} REFUSED (exit 2): the registry records "
                            f"{'no verdict' if not verdict else 'the verdict ' + str(verdict)} for {b.eid}; the v2 "
                            f"shadow exports nothing unless the registry verdict is PASS ({V2_RULING})", b.eid, verdict)
    if verdict and str(verdict).upper() != "PASS":
        # v1r's refusal is its own ruling's (addendum 24 item 2(d)), never 230's dormancy: it stays a ShadowRefused
        raise ShadowRefused(f"export-ncaa-predictions REFUSED (exit 2): the registry records {b.eid}'s verdict as "
                            f"{verdict}. {VERDICT_RULING}, verbatim: \"{VERDICT_REFUSAL}\"")
    rule = e.get(NEUTRAL_RULE_KEY)
    if rule not in NEUTRAL_RULES:
        raise ShadowRefused(f"REFUSED: {b.eid}'s declaration has no {NEUTRAL_RULE_KEY} (one of "
                            f"{', '.join(sorted(NEUTRAL_RULES))}; got {rule!r}) — whether v1r applies home "
                            "advantage at neutral sites is the declaration's choice, never the shadow's")
    if b.rule is not None and rule != b.rule:
        raise ShadowRefused(f"export-ncaa-predictions --id {b.eid} REFUSED (exit 2): its declaration's "
                            f"{NEUTRAL_RULE_KEY} is {rule!r}, not the gate's {b.rule!r} (the gate's model is "
                            "NeutralRuleElo's default); the shadow runs only the model the gate scored "
                            "(ARCHITECT 2026-10-26 15:15 ET, on #698)")
    from src.models.ncaa_elo import NCAAEloConfig

    frozen_v1 = {k: getattr(NCAAEloConfig(), k) for k in CONSTANT_KEYS}
    declared = e.get(CONSTANTS_KEY)
    if not isinstance(declared, dict) or set(declared) != set(CONSTANT_KEYS) or any(
            not isinstance(declared[k], (int, float)) or isinstance(declared[k], bool)
            or float(declared[k]) != frozen_v1[k] for k in CONSTANT_KEYS):
        raise ShadowRefused(f"REFUSED: {b.eid}'s declaration must freeze {CONSTANTS_KEY} = v1's untouched constants "
                            f"{frozen_v1} (got {declared!r}) — the shadow runs only the declared model")
    return e, NEUTRAL_RULES[rule], rule


def bound_scale(b: Binding, e: dict) -> float | None:
    """The logistic scale the binding runs at: None for v1r (v1's /400); for v2 the registry's frozen s
    (ncaa_v1r_gate.scale_state, the gate's own read), which must equal the ruled V2_FROZEN_S exactly."""
    if b.scale is None:
        return None
    from src.walters import ncaa_v1r_gate as g

    v, why = g.scale_state(g.spec_of(b.eid), e)
    if why:
        raise ShadowRefused(f"REFUSED: {b.eid}: {why}")
    if v != b.scale:
        raise ShadowRefused(f"REFUSED: {b.eid}'s registry freezes s = {v!r}, not the ruled {b.scale!r} ({V2_RULING}); "
                            "the shadow runs only the declared model")
    return v


def gate_label(e: dict) -> str:
    """'UNGATED — shadow only' until the registry records a verdict, then that verdict."""
    v = (e.get("verdict") or {}).get("verdict")
    return str(v) if v else UNGATED


def coverage_guard(fbs: dict[str, dict]) -> dict[str, dict]:
    """SCOPE (ARCHITECT 2026-10-08): the shadow's precondition is the ingest receipt's fact — the side table
    labels >= 95% of CFBD's completed both-FBS games in EACH season used (ncaa_cfbd.stored_coverage); D6: the
    seasons are 2024, 2025 and 2026."""
    from src.walters import ncaa_backtest as nb

    bad = nb.coverage_misses(fbs, nb.V1R_SEASONS)      # D6: 2024, 2025 and 2026, each missing season named
    if bad:
        raise ShadowRefused(f"REFUSED: the CFBD side table labels less than {nb.COVERAGE_MIN:.0%} of CFBD's completed "
                            f"both-FBS games in {'; '.join(bad)} — the shadow does not run before the coverage "
                            "condition holds (`python cli.py ncaa-cfbd-coverage` lists every unlabelled game)")
    return fbs


# D1's thin wrapper, one shared class (ncaa_backtest.NeutralRuleElo; the design receipt imports the same one).
from src.walters.ncaa_backtest import NeutralRuleElo as V1R  # noqa: E402  (stdlib-only at import time)


def walk(model, games, now: datetime) -> dict:
    """The shadow's walk, pure: update `model` on every stream game (D2 order) kicking off before `now`. Returns the
    count walked by season."""
    by_season: dict = {}
    for g in games:                                     # D2 order: stored kickoff, then match id
        if g.utc_date >= now:
            continue
        model.update(g)
        by_season[g.season] = by_season.get(g.season, 0) + 1
    return by_season


def fit(now: datetime, neutral_home_advantage: bool, games=None, fbs: dict | None = None,
        scale: float | None = None):
    """(model, receipt, team merge): walk-forward over D2's stream (current CFBD labels only, seasons 2024-2026,
    kickoff then match id, postseason included, level scores skipped; J2 merge applied) before `now`; refuses
    unless D6's coverage holds for 2024, 2025 and 2026. `scale`: the v2 binding's frozen s (None: v1)."""
    from src.db.database import session_scope
    from src.ingestion.ncaa_cfbd import stored_coverage
    from src.walters import ncaa_backtest as nb

    if fbs is None:
        with session_scope() as s:
            fbs = stored_coverage(s, nb.V1R_SEASONS)
            s.rollback()
    cov = coverage_guard(fbs)
    v = nb.load_v1r_stream(games)
    model = V1R(neutral_home_advantage, scale=scale)
    by_season = walk(model, v.games, now)
    used = sum(by_season.values())
    return model, {"games_used": used, "logistic_scale": scale, "walked_by_season": dict(sorted(by_season.items())),
                   "season_type_census": {s_: dict(sorted(c.items())) for s_, c in sorted(v.census.items())},
                   "level_scores_skipped": len(v.level), "level_scores_listed": list(v.level),
                   "neutral_updates": model.neutral_updates, "neutral_unflagged": model.unflagged_updates,
                   "coverage": {s: round(c["share"], 4) for s, c in sorted(cov.items()) if c["share"] is not None},
                   "unlabelled_not_walked": dict(sorted(v.unlabelled.items())),
                   "stale_labels_not_walked": list(v.stale),
                   "outside_seasons_not_walked": dict(sorted(v.outside.items())),
                   "team_merge": {"groups": [[[t, n] for t, n in g] for g in v.merge.groups],
                                  "changed_names": [[t, n, u] for t, n, u in v.merge.changed]},
                   "constants": {"k_factor": model.cfg.k_factor, "home_advantage": model.cfg.home_advantage,
                                 "mov_base": model.cfg.mov_base, "season_regression": model.cfg.season_regression,
                                 "default_rating": model.cfg.default_rating}}, v.merge


def fbs_teams(s, merge=None) -> set[int]:
    """L3 (ARCHITECT 2026-10-08, addendum 11): "The v1r stream and the shadow's FBS team set read current
    labels only." Teams of the games whose label is current (its fetched_at equals its season's latest ingest
    record's; ncaa_cfbd.latest_record_stamps); a stale label never qualifies a team. Merged ids (J2) when
    `merge` is given."""
    from sqlalchemy import and_, or_, select

    from src.db.schema import Match, NCAACFBDLabel
    from src.ingestion.ncaa_cfbd import latest_record_stamps

    stamps = latest_record_stamps(s)
    if not stamps:
        return set()
    cond = or_(*[and_(NCAACFBDLabel.season == season, NCAACFBDLabel.fetched_at == at)
                 for season, at in stamps.items()])
    q = (select(Match.home_team_id, Match.away_team_id)
         .join(NCAACFBDLabel, NCAACFBDLabel.match_id == Match.id).where(cond))
    canon = merge or (lambda t: t)
    return {canon(t) for row in s.execute(q).all() for t in row}


def build_rows(now: datetime | None = None, hours: int = WINDOW_HOURS, registry_path: str | None = None,
               eid: str = EID) -> dict:
    from collections import Counter

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport
    from src.walters import ncaa_backtest as nb
    from src.walters.export import _fixture_row

    now = now or utc_now_naive()
    b = binding(eid)
    e, neutral_ha, rule = frozen(registry_path, eid=eid)
    scale = bound_scale(b, e)
    label = gate_label(e)
    model, rc, merge = fit(now, neutral_ha, scale=scale)
    rc["neutral_site_rule"] = rule
    rows, skipped = [], Counter()
    with session_scope() as s:
        fbs = fbs_teams(s, merge)
        q = (select(Match).join(Competition, Match.competition_id == Competition.id)
             .where(Match.sport == Sport.NFL, Competition.code == COMPETITION,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now, Match.utc_date < now + timedelta(hours=hours))
             .order_by(Match.utc_date, Match.id))
        for m in s.execute(q).scalars():
            g = nb.Game(merge(m.home_team_id), merge(m.away_team_id), m.season, m.utc_date, 0, 0, m.stage or "",
                        match_id=m.id)                       # J2: merged ids, as walked
            why = nb.exclusion_reason(g)
            if why:
                skipped[why] += 1
                continue
            if g.home_id not in fbs or g.away_id not in fbs:
                skipped["not_both_fbs"] += 1
                continue
            p = model.predict(g)
            row = _fixture_row(s, m, COMPETITION, Counter(), Counter())
            pick_home = p >= 0.5
            row.update({
                "competition": COMPETITION, "family": FAMILY,
                "engine": ENGINE, "model_version": b.model_version, "gate_verdict": label, "registry_id": b.eid,
                # addendum 158 item 1(b): the input cutoff (the walk read every stream game kicking off before it)
                # and the prediction stamp (this export's clock), on every row
                "input_cutoff": now.isoformat(), "prediction_stamp": now.isoformat(),
                "prediction": {"home_win_prob": round(p, 4), "away_win_prob": round(1 - p, 4),
                               "top_pick": "home_win" if pick_home else "away_win",
                               "top_pick_prob": round(p if pick_home else 1 - p, 4),
                               "elo_home": round(model.rating(g.home_id), 1),
                               "elo_away": round(model.rating(g.away_id), 1),
                               # D8: the listed home's advantage; the neutral flag is unknown before the game
                               "home_adv_applied": model.home_adv(g),
                               "home_adv_basis": HOME_ADV_BASIS,
                               "neutral": None, "neutral_flag": NEUTRAL_FLAG_UNKNOWN,
                               "neutral_rule": NEUTRAL_PREGAME_RULE,      # addendum 230 item 1(b): its rule stated
                               **({"logistic_scale": scale} if scale is not None else {})},
            })
            rows.append(row)
        s.rollback()
    return {"rows": rows, "fit": rc, "skipped": dict(skipped), "label": label, "now": now, "binding": b}


def export(now: datetime | None = None, hours: int = WINDOW_HOURS, out_dir: str = "exports",
           registry_path: str | None = None, eid: str = EID) -> tuple[str, dict]:
    r = build_rows(now, hours, registry_path, eid=eid)
    b = r["binding"]
    now = r["now"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # Codex on #344: second precision and an exclusive create, so a rerun never replaces an earlier artifact
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M%S')}.json")
    doc = {"sport": "ncaa", "competition": COMPETITION, "family": FAMILY, "engine": ENGINE,
           "model_version": b.model_version, "registry_id": b.eid, "gate_verdict": r["label"],
           "contains_predictions": False,   # nothing here is a live prediction (doctrine)
           "gate_evidence": False,          # the shadow's live record is not gate evidence (ruling)
           "exported_at": now.isoformat(), "window_hours": hours, "note": b.note,
           "fit": r["fit"], "skipped": r["skipped"], "count": len(r["rows"]), "predictions": r["rows"]}
    try:
        with open(path, "x") as f:
            json.dump(doc, f, indent=2, default=str)
    except FileExistsError:
        raise ShadowRefused(f"REFUSED: {path} already exists — an artifact is never overwritten; re-run next second")
    return path, doc


def last_calls(export_dir: str = "exports", eid: str | None = None) -> dict[int, dict]:
    """match_id -> the LAST shadow row written before its kickoff. `eid`: only the files that binding wrote (a file
    without a registry_id is v1r's, the only binding before 158 item 1(b)); None reads every binding's."""
    out: dict[int, dict] = {}
    for f in sorted(Path(export_dir).glob(f"{FILE_PREFIX}*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("engine") != ENGINE or doc.get("competition") != COMPETITION:
            continue
        if eid is not None and doc.get("registry_id", EID) != eid:
            continue                                 # grading never pools two bindings
        at = doc.get("exported_at") or ""
        for r in doc.get("predictions") or []:
            mid, ko = r.get("match_id"), r.get("utc_date") or ""
            if mid is None or not at or at >= ko:
                continue
            if mid not in out or at >= out[mid]["exported_at"]:
                out[mid] = {**r, "exported_at": at, "source_file": f.name}
    return out


def _result(s, m) -> tuple[int, int, str] | None:
    """(home score, away score, source) in OUR orientation: the CFBD side table where a row exists (the label
    source of record stores the source's scores in our orientation), else the matches row."""
    from sqlalchemy import inspect

    from src.db.schema import NCAACFBDLabel
    from src.ingestion.ncaa_cfbd import label_load_options

    if inspect(s.connection()).has_table(NCAACFBDLabel.__tablename__):
        lab = s.get(NCAACFBDLabel, m.id, options=label_load_options(s))
        if lab is not None and lab.orientation in ("same", "swapped"):
            return lab.home_score, lab.away_score, "cfbd"
    if m.home_score is None or m.away_score is None:
        return None
    return m.home_score, m.away_score, "matches"


def grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None, progress=None,
          eid: str = EID) -> dict:
    """Results (hit rate, log-loss, Brier) and model-vs-close (pick-vs-close + value-side) for finished NCAA
    games whose call exists in a shadow export of the `eid` binding (never pooled). Not gate evidence."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.close import KALSHI_SOURCES, close_1x2, outcomes_for, priced, stale_book_close
    from src.walters.nfl_predict import _book_anchor, value_side_grade
    from src.walters.vs_close import block

    from src.walters import close as _close
    from src.walters import kalshi_legs
    from src.walters import ncaa_backtest as nb
    from src.walters import paper

    now = now or utc_now_naive()
    b = binding(eid)
    tag = b.model_version.replace("ncaa_elo_", "")             # v1r_H= / v2_H= on each line
    calls = last_calls(export_dir, eid=b.eid)
    hits, lls, briers, clvs, vclvs, lines = [], [], [], [], [], []
    pairs = []                         # addendum 64 item 2: (model p, close p) of the outcome, games with a close
    kalshi_fed = 0                     # of those, the closes a Kalshi mid priced (the stale-book rule)
    graded = unpriced = unanchored = ties = no_result = identity_mismatch = 0
    # ARCHITECT 2026-11-03, addendum 230 item 1(b): "its grade against the Kalshi close (the close record's KXNCAAFGAME
    # rule)", each name on its own as the NHL shadow's record against the close (addendum 63 item 3): this binding's
    # one name. The close is paper.guarded_two_way_close, the record's own (books not read), in the record's order of
    # exclusion; the record's 2026 / 2023 fences (ncaa_backtest.v2_run_recorded) apply as they apply to the record.
    kpairs = []
    # every finished call in the window lands in exactly one: n + sum(kalshi_close_excluded) == the window's calls
    kx = {"identity_mismatch": 0, "fenced_2023": 0, "fenced_2026": 0, "three_way": 0, "no_result": 0, "tie": 0,
          paper.MISMATCHED: 0, paper.NO_CLOSE: 0}
    with session_scope() as s:
        window = [m for m in (s.get(Match, mid) for mid in calls)
                  if m is not None and m.status == MatchStatus.FINISHED and m.utc_date >= now - timedelta(days=days)]
        ids = [m.id for m in window]
        snaps = paper._kalshi_snaps(s, ids)
        mism = kalshi_legs.mismatched(s, ids) if ids else {}
        tickers, current, homes = paper.two_way_legs(s, window, snaps)
        fence_v2 = not nb.v2_run_recorded()
        labs = nb.label_seasons(s, window) if fence_v2 else {}
        for mid, c in sorted(calls.items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            # Codex on #344: match ids are machine-local and reusable (init-db --force); the artifact row's teams and
            # kickoff must be this match's, else it is never graded against it
            if (m.competition is None or m.competition.code != COMPETITION
                    or (c.get("home_team"), c.get("away_team")) != (m.home_team.name, m.away_team.name)
                    or c.get("utc_date") != m.utc_date.isoformat()):
                identity_mismatch += 1
                kx["identity_mismatch"] += 1                # the shadow's own guard: the row is not this match's
                continue
            # the Kalshi close's exclusions in the close record's order (paper.close_record): the fences and a
            # three-way board BEFORE the result, so a fenced game with no result or a tie counts as fenced, as there
            seasons = {str(m.season), labs.get(m.id, (None,))[0]}
            kpre = ("fenced_2023" if fence_v2 and nb.V2_SECOND in seasons
                    else "fenced_2026" if fence_v2 and nb.V2_TEST in seasons
                    else "three_way" if tuple(_close.outcomes_for(m.sport)) != _close.BINARY else None)
            res = _result(s, m)
            if res is None:
                no_result += 1
                kx[kpre or "no_result"] += 1
                continue
            hs, as_, src = res
            if hs == as_:
                ties += 1                                   # college football cannot tie: a data defect
                kx[kpre or "tie"] += 1
                continue
            graded += 1
            p = c["prediction"]["home_win_prob"]
            y = 1 if hs > as_ else 0
            pick_home = p >= 0.5
            hits.append(1 if pick_home == bool(y) else 0)
            pc = min(max(p, 1e-12), 1 - 1e-12)
            lls.append(-(y * math.log(pc) + (1 - y) * math.log(1 - pc)))
            briers.append((p - y) ** 2)
            odds = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            cl = close_1x2(odds, m.utc_date, outcomes_for(m.sport))
            # addendum 137 item 4 ("every family, applied where a stamp exists"): NCAA odds carry the NFL writer's stamp
            cl = stale_book_close(s, m, cl)
            close_h = cl["fair"].get("HOME", 0) if priced(cl) else None
            clv = None
            if close_h is not None:
                clv = (p if pick_home else 1 - p) - (close_h if pick_home else 1 - close_h)
                clvs.append(clv)
                # ARCHITECT 2026-10-13 (addendum 64 item 2): the hit rate carries the line against the close, per the
                # shadow's own close (close_1x2 on the odds table, then the stale-book rule, addendum 137 item 4), over
                # the same graded games that have one
                side = "HOME" if y else "AWAY"
                pairs.append((p if y else 1 - p, cl["fair"][side]))
                kalshi_fed += cl.get("source") in KALSHI_SOURCES
            else:
                unpriced += 1
            anchor_h, _ = _book_anchor(s, m)
            vg = value_side_grade(p, anchor_h, close_h)
            if vg:
                vclvs.append(vg["value_side_clv"])
            elif anchor_h is None:
                unanchored += 1
            # the Kalshi close, the close record's rule (paper.close_record's two-way order after the result)
            kcl, kwhy = None, kpre
            if kwhy is None:
                kcl, kwhy = paper.guarded_two_way_close(m, snaps.get(m.id, []), mism, tickers, current.get(m.id),
                                                        homes)
            if kwhy:
                kx[kwhy] += 1
            else:
                kside = "HOME" if y else "AWAY"
                kpairs.append((p if y else 1 - p, kcl["fair"][kside]))
            line = (f"  {m.away_team.name[:16]:16} @ {m.home_team.name[:16]:16} {tag}_H={p:.3f} "
                    f"result {hs}-{as_} ({src}) {'HIT' if hits[-1] else 'miss'} · "
                    f"close_H={'%.3f' % close_h if close_h is not None else '  — '} "
                    f"div={'%+.1fpp' % (clv * 100) if clv is not None else '—'} "
                    f"value={(vg['side'] + ' %+.1fpp' % (vg['value_side_clv'] * 100)) if vg else '— (no anchor)'}"
                    f" · kalshi_close_H={'%.3f' % kcl['fair']['HOME'] if kcl else '— (' + kwhy + ')'}"
                    " · NOT gate evidence")
            lines.append(line)
            if progress:
                progress(line)
    return {"graded": graded, "calls_on_file": len(calls), "ties_skipped": ties, "no_result": no_result,
            "identity_mismatch": identity_mismatch,
            "hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
            # the line names the closes a Kalshi mid priced, as every results file's block does (addendum 137 item 4)
            "vs_close": {**block(pairs), "kalshi_only_closes": kalshi_fed},
            # addendum 230 item 1(b): the record against the Kalshi close, per name (this binding's), never pooled
            "vs_kalshi_close": {b.model_version: block(kpairs)},
            "kalshi_close_excluded": kx,
            "kalshi_close_rule": KALSHI_CLOSE_RULE,
            "log_loss": round(sum(lls) / len(lls), 4) if lls else None,
            "brier": round(sum(briers) / len(briers), 4) if briers else None,
            "priced": len(clvs), "unpriced": unpriced,
            "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
            "value_side_n": len(vclvs), "unanchored": unanchored,
            "mean_value_side_clv_pp": round(sum(vclvs) / len(vclvs) * 100, 2) if vclvs else None,
            "lines": lines}


KALSHI_CLOSE_RULE = ("the close record's two-way rule (paper.close_record; KXNCAAFGAME for NCAA): the last "
                     "two-sided pre-kickoff Kalshi HOME quote's mid under the 2c cap (close.close_from_kalshi), books "
                     "not read; left out in order: first the shadow's own identity guard (the row's teams and "
                     "kickoff are not this match's), then the record's order: the 2023 / 2026 fences until "
                     "ncaa-elo-v2's run is recorded, a three-way board, no decided result, a tie (a data defect), "
                     "mismatched legs (kalshi_legs.mismatched, then the HOME row the close reads, "
                     "paper.close_row_mismatched), no close")


def confirmation_counter(eid: str = V2_EID, export_dir: str = "exports", registry_path: str | None = None) -> dict:
    """THE CONFIRMATION COUNTER TO 100 (ARCHITECT 2026-11-03, addendum 230 item 1(b): "the confirmation counter to
    100; dormant while the verdict is null or FAIL"). A count, never a verdict and never a figure of the games:
    - {"state": "dormant", "why"} while the registry records no verdict, or a verdict other than PASS, for `eid`;
    - {"state": "refused", "why"} when the read refuses after a PASS (no run record, D6 coverage: GateRefused);
    - else {"state": "counting", ...ncaa_v1r_gate.confirmation_count (n scored of n_games, the cohort's state and
      size, pending by status, releases due, complete), "shadow_rows": cohort fixtures holding a row of this binding
      written before kickoff (last_calls), "shadow_rows_scored": of the scored ones}.
    The confirmation fixture is D7's, as ncaa-confirm reads it (any status, frozen once); a fixture without a shadow
    row still counts (the shadow row is printed beside, never a condition). Read-only."""
    from src.walters import ncaa_v1r_gate as g
    from src.walters import registry as reg

    b = binding(eid)
    e = reg.get(b.eid, registry_path or reg.LEDGER)          # the registry confirming() reads (registry.LEDGER)
    verdict = ((e or {}).get("verdict") or {}).get("verdict")
    if str(verdict or "").upper() != "PASS":
        if b.pass_only:                                      # ncaa-elo-v2: addendum 230 item 1(b)'s dormancy
            return {"state": "dormant", "why": dormant_reason(b.eid, verdict)}
        # v1r: 230 item 1(b) is v2's; v1r's own refusal names its own ruling (addendum 24 item 2(d)), never dormancy
        what = "no verdict" if not verdict else f"the verdict {verdict}"
        return {"state": "refused", "why": f"the registry records {what} for {b.eid}: no confirmation to count"
                + (f" (its shadow refuses on that verdict, {VERDICT_RULING})" if verdict else "")}
    try:
        r = g.confirmation_count(g.spec_of(b.eid))
    except g.GateRefused as err:
        return {"state": "refused", "why": str(err)}
    rows = set(last_calls(export_dir, eid=b.eid))
    return {"state": "counting", **r, "shadow_rows": len(rows & set(r["cohort_ids"])),
            "shadow_rows_scored": len(rows & set(r["scored_ids"]))}


def counter_line(r: dict, eid: str) -> str:
    """The printed line: counts only (no log-loss, no baseline, no verdict)."""
    if r["state"] != "counting":
        return f"confirmation counter {eid}: {r['state'].upper()} — {r['why']}"
    from collections import Counter
    pend = dict(Counter(p["status"] for p in r["pending"]))
    return (f"confirmation counter {eid}: {r['n']}/{r['n_games']} scored · cohort {r['cohort_state'].upper()} "
            f"({r['cohort_size']}/{r['n_games']} fixtures; {r['eligible_stored']} eligible stored) · pending "
            f"{len(r['pending'])}{' ' + str(pend) if pend else ''}"
            + (f" · {r['release_due']} cancelled: release due" if r["release_due"] else "")
            + f" · shadow row before kickoff: {r['shadow_rows']} of the cohort, {r['shadow_rows_scored']} of the scored"
            + (" · COMPLETE (the read and its record are ncaa-confirm's)" if r["complete"] else "")
            + " · a count, not a verdict")


# ----------------------------------------------------------------------------------------------------------------
# THE PARITY RECEIPT (addendum 158 item 1(b)): "A read-only receipt on synthetic cases that the shadow's probabilities
# equal the gate path's." Pure over its inputs: no DB, no file.
# ----------------------------------------------------------------------------------------------------------------

PARITY_TOL = 1e-12


class _Recorder:
    """The gate's declared model, recording the probability of every game the gate predicts (it predicts only the
    games it scores); every other call passes through unchanged."""

    def __init__(self, inner):
        self.inner, self.p = inner, {}

    def predict(self, g):
        p = self.inner.predict(g)
        self.p[g.match_id] = p
        return p

    def __getattr__(self, name):
        return getattr(self.inner, name)


def parity(games, scale: float = V2_FROZEN_S, neutral_home_advantage: bool = False) -> dict:
    """Both paths on one stream (`games`: D2 order, as the gate and the shadow read it):
    - the gate path: ncaa_v1r_gate.run_gate on ncaa-elo-v2's gate read, the declared model at `scale` recorded;
    - the shadow path: for every game the gate scored, a fresh model at `scale` walked (walk()) over the stream games
      kicking off before it, then the prediction of that game with the same game record.
    Returns per-game rows (match id, kickoff, the two probabilities, |diff|) and the counts. The pregame difference
    (D8: a live row prices with the listed home's advantage and an unknown neutral flag) is counted apart: the
    shadow's price of each neutral scored game with its flag unknown, against the gate's."""
    from dataclasses import replace

    from src.walters import ncaa_backtest as nb
    from src.walters import ncaa_v1r_gate as g

    read = g.spec_of(V2_EID).gate
    rec = _Recorder(nb.NeutralRuleElo(neutral_home_advantage, scale=scale))
    res = g.run_gate(games, model=rec, read=read)
    by_id = {x.match_id: x for x in games}
    rows, pregame = [], []
    for mid, gp in rec.p.items():
        x = by_id[mid]
        m = V1R(neutral_home_advantage, scale=scale)
        walk(m, games, x.utc_date)
        sp = m.predict(x)
        rows.append({"match_id": mid, "kickoff": x.utc_date, "gate": gp, "shadow": sp, "diff": abs(sp - gp)})
        if x.neutral is True:
            m2 = V1R(neutral_home_advantage, scale=scale)
            walk(m2, games, x.utc_date)
            pregame.append(abs(m2.predict(replace(x, neutral=None)) - gp))
    diffs = [r["diff"] for r in rows]
    return {"scale": scale, "stream": len(games), "gate_scored": res.get("n_scored", 0), "compared": len(rows),
            "unequal": sum(d > PARITY_TOL for d in diffs), "max_diff": max(diffs, default=0.0), "rows": rows,
            "neutral_scored": len(pregame), "pregame_max_diff": max(pregame, default=0.0)}


def parity_lines(r: dict, rows: bool = False) -> list[str]:
    L = [f"NCAA v2 SHADOW PARITY ({V2_RULING}) · synthetic · s {r['scale']!r} · stream {r['stream']} games · gate scored "
         f"{r['gate_scored']} · compared {r['compared']} · unequal {r['unequal']} (max |diff| {r['max_diff']:.3g}; "
         f"equal within {PARITY_TOL:g}) · {'EQUAL' if r['compared'] and not r['unequal'] else 'NOT EQUAL'}",
         f"  pregame (D8, reported): {r['neutral_scored']} scored neutral games; priced as a live row prices them "
         f"(the listed home's advantage, the neutral flag unknown) they differ from the gate by up to "
         f"{r['pregame_max_diff']:.3g}: the pregame metadata (item 1(c)) is that difference's source"]
    if rows:
        L += [f"  - game {x['match_id']} · {x['kickoff']:%Y-%m-%d %H:%M} · gate {x['gate']:.6f} · shadow "
              f"{x['shadow']:.6f} · |diff| {x['diff']:.2g}" for x in r["rows"]]
    return L


def synthetic_stream(seed: int = 158, teams: int = 30, weeks: int = 13, per_week: int = 14) -> list:
    """A seeded synthetic D2 stream (2024-2026; 'regular' weeks then a 'postseason' week; one game in ten neutral;
    no level score), for the parity receipt only. D2 order: kickoff, then id."""
    import random

    from src.walters import ncaa_backtest as nb

    rnd = random.Random(seed)
    out, mid = [], 0
    for season, year in (("2024", 2024), ("2025", 2025), ("2026", 2026)):
        for w in range(weeks + 1):
            ids = rnd.sample(range(1, teams + 1), 2 * per_week)
            for i in range(per_week):
                mid += 1
                hs, as_ = rnd.randint(0, 49), rnd.randint(0, 49)
                if hs == as_:
                    hs += 3
                at = datetime(year, 9, 1) + timedelta(days=7 * w, hours=12 + 4 * (i % 3))
                out.append(nb.Game(ids[2 * i], ids[2 * i + 1], season, at, hs, as_, "",
                                   neutral=rnd.random() < 0.1, label_source="cfbd", orientation="same",
                                   match_id=mid, season_type="postseason" if w == weeks else "regular",
                                   cfbd_season=season))
    return sorted(out, key=lambda x: (x.utc_date, x.match_id))
