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
An UPCOMING game (no label before the game) carries CFBD's PREGAME neutral flag
where the labels ingest read one (ARCHITECT 2026-11-03, addendum 236 item 3(1):
ncaa_cfbd_pregame, current rows only) and is priced exactly as the walk prices
that field (True: home advantage 0; False or absent: the Game's home's, which is
CFBD's home, our listed away, where the current pregame row is 'swapped',
addendum 239 item 2, and the listed home otherwise); where CFBD has no flag it
is unknown (D8, law 4), and only with no current row (none, or stale) does the
listed home keep the advantage. Walk-forward over D2's stream, every game before now, then the predictions.

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
  * The neutral flag before kickoff: every row states its rule (NEUTRAL_PREGAME_RULE, addendum 236 item 3(1)).
  * The grade against the Kalshi close: vs_kalshi_close per name, paper.guarded_two_way_close (close_record's own),
    its exclusions counted; the book line stays beside it.
  * The counter to 100: confirmation_counter (ncaa_v1r_gate.confirmation_count: counts, never a figure or a verdict).

THE SEVEN, RULED (ARCHITECT 2026-11-03, addendum 236 item 3):
  (1) the neutral flag: CFBD's pregame field (ncaa_cfbd_pregame, read at the labels ingest), "neutral per CFBD's
      pregame field, read <stamp>; absent: unknown, D8" on every row; it prices exactly what the walk does with it;
  (2) the close: the Kalshi close is THE close (KXNCAAFGAME), per name; the book close a reference line; the D4
      baseline a second REFERENCE name (D4_REF_NAME), never a verdict's input; the 2023 / 2026 fences apply to the
      Kalshi block until ncaa-elo-v2's run AND its verdict are recorded (kalshi_fenced);
  (3) the confirmation fixture: D7's cohort is the COUNT (the 100); the RECORD against the close is on the counted
      members holding a prospective shadow row; every member without one is named "no prospective row", unscored,
      its count beside the 100 (confirmation_record);
  (4) a D6 coverage drop after a PASS refuses (exit 2, never dormant); the export runs after refresh-by-id whatever
      its exit (chains: ncaa-schedule's `go_on`), its rows stamped with the refresh it saw (refresh_seen);
  (5) the host fence: the command refuses on any machine but the host (desk_policy.not_host_reason); `--dry-run`
      prints the rows and writes nothing (export(dry_run=True));
  (6) the Kalshi grade reads legs captured on or after KALSHI_LEGS_FROM (#475's switch to the shared pair; the
      boundary per addendum 239 item 4: the repo record names no deploy instant for the tag carrying #475, and
      v1.4.0's release Issue #556 names none either, so the conservative bound 2026-10-14T04:00:00Z); earlier rows never enter it, the close nor its legs guard
      (legs_before_2026_10_14);
  (7) one registry source: registry.LEDGER read at call time by frozen(), the counter and coverage alike.

ADDENDUM 239 (ARCHITECT 2026-11-03 16:15 ET), as built here:
  item 2, orientation counts: a fixture whose CURRENT pregame row is 'swapped' is priced in CFBD's order (live_game,
      the 55 to CFBD's home = our listed away, 0 when CFBD says neutral), its probabilities stated for our listed home
      and away (listed_home_prob); 'same' prices our order; no current row: the listed home keeps it, "unknown"
      (ORIENTATION_TEXT on every row; parity() pins a swapped fixture equal to the gate);
  item 3, the fences: the 2023 and 2026 fences on the Kalshi block lift TOGETHER once the run and its verdict are
      recorded (kalshi_fenced);
  item 4, the legs boundary: KALSHI_LEGS_FROM = 2026-10-14T04:00:00Z, the conservative bound, because the repo
      record names no deploy instant for the tag carrying #475 and release Issue #556 names none (LEGS_WHY, on
      the console);
  item 5, current rows only: a pregame row from an older ingest reads as unknown (pregame_flags' `current`).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive
from src.walters.provenance import git_sha as _git_sha

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
# listed home's advantage and says on the row that the neutral flag is unknown." Met by addendum 236 item 3(1) below
# where CFBD serves its pregame field; where it does not, D8's "unknown" stands.
# THE NEUTRAL FLAG BEFORE KICKOFF (ARCHITECT 2026-11-03, addendum 236 item 3(1), verbatim): "THE NEUTRAL FLAG: option
# (iii) — CFBD's pregame neutral-site field for the fixture, read at the labels ingest and ruled as ours with its rule
# stated on every row ("neutral per CFBD's pregame field, read <stamp>; absent: unknown, D8"); (iv)'s "unknown" where
# CFBD has none; never a hand table for the current season (that is #608's NFL case). It LABELS the row; it PRICES
# only what the candidate's own backtest stream does with the same field — exactly that, no more, no less (parity
# with the gate's walk; Code states which in the PR body, and a test pins the shadow row's probability equal to the
# walk's for a neutral fixture)." The stream's treatment (ncaa_backtest.NeutralRuleElo.home_adv, the gate's model):
# a flag True prices (and updates) with home advantage 0; False or absent, the Game's home's 55 (CFBD's home where
# the current row is swapped: addendum 239 item 2, ORIENTATION_TEXT below). The row's Game carries the fixture's
# CURRENT pregame flag (ncaa_cfbd.pregame_flags: fetched_at = its season's latest ingest record's, L3's rule), so
# model.home_adv prices it exactly so. A stale row, a row whose record served no flag, or no row: the flag is
# unknown (law 4). The listed home keeps the advantage only with no current row (none, or stale); a current 'swapped'
# row, one whose record served no flag included, gives it to CFBD's home (our listed away), as the gate's walk.
NEUTRAL_RULING = "ARCHITECT 2026-11-03, addendum 236 item 3(1)"
NEUTRAL_PREGAME_RULE = "neutral per CFBD's pregame field, read {stamp}; absent: unknown, D8"   # the ruled form
NO_READ = "no CFBD read"
NEUTRAL_FLAG_NEUTRAL = "neutral (CFBD's pregame field)"
NEUTRAL_FLAG_NOT = "not neutral (CFBD's pregame field)"
NEUTRAL_FLAG_UNKNOWN = "absent: unknown, D8"
HOME_ADV_BASIS = {True: "home advantage 0: CFBD's pregame field says neutral (D1, as the gate's walk prices it)",
                  False: "listed home: CFBD's pregame field says not neutral",
                  None: "listed home: the neutral flag is unknown before the game (D8)"}
# ORIENTATION COUNTS (ARCHITECT 2026-11-03 16:15 ET, addendum 239 item 2, verbatim): "the shadow prices EXACTLY as the
# gate's walk prices — the gate's stream is CFBD's, so where CFBD lists the teams the other way round from our stored
# fixture, the home advantage goes to CFBD's home, the row stating "orientation: CFBD's home is our listed away
# (swapped); priced as the gate's walk"; with no CFBD row the listed home keeps it and the row says "unknown". Parity
# with the gate is the rule, not our adapter's orientation (the 2023 census found 4 swapped of 792; the gate's PASS, if
# it comes, is on CFBD's orientation). A test pins a swapped fixture's shadow probability equal to the walk's."
# Built: a CURRENT pregame row (item 5: a row from an older ingest reads as unknown) whose orientation is 'swapped'
# prices the Game in CFBD's order, as ncaa_backtest.game_from_rows walks a swapped label (the teams flip; the 55 goes
# to CFBD's home = our listed away, 0 when CFBD says neutral); the row's probabilities stay stated for OUR listed home
# and away (home_win_prob = 1 - P(CFBD's home wins)). 'same': our order, which is CFBD's. No current row, or an
# orientation outside the two values (law 4, as game_from_rows): our listed order, the listed home keeps the 55.
ORIENTATION_RULING = "ARCHITECT 2026-11-03, addendum 239 item 2"
ORIENTATION_TEXT = {"swapped": "orientation: CFBD's home is our listed away (swapped); priced as the gate's walk",
                    "same": "orientation: CFBD's home is our listed home (same); priced as the gate's walk",
                    None: "orientation: unknown (no current CFBD pregame row); the listed home keeps the home "
                          "advantage"}
SWAPPED_BASIS = {False: "CFBD's home (our listed away): CFBD's pregame field says not neutral",
                 None: "CFBD's home (our listed away): the neutral flag is unknown before the game (D8)"}


def cfbd_orientation(cur) -> str | None:
    """'same' / 'swapped' from the fixture's CURRENT pregame row (addendum 239 items 2 and 5), else None (unknown:
    no row, a stale row, or a value outside the two, law 4)."""
    o = cur.get("orientation") if cur else None
    return o if o in ("same", "swapped") else None


def live_game(home: int, away: int, season, utc_date, stage, neutral, orient, match_id=None):
    """A live row's Game (addendum 239 item 2): our listed `home` / `away` (merged ids) in CFBD's order where `orient`
    is 'swapped' (as ncaa_backtest.game_from_rows walks a swapped label), else in ours; no score; the pregame flag as
    the walk reads it. Shared by build_rows and parity()."""
    from src.walters import ncaa_backtest as nb

    return nb.Game(*((away, home) if orient == "swapped" else (home, away)), season, utc_date, 0, 0, stage or "",
                   neutral=neutral, match_id=match_id, orientation=orient)


def listed_home_prob(model, g) -> float:
    """P(OUR listed home wins) for a live_game: the model prices the Game's home (CFBD's, where swapped), and a
    swapped Game's home is our listed away, so 1 - p there. The row is always stated in our orientation."""
    q = model.predict(g)
    return 1 - q if g.orientation == "swapped" else q


def neutral_rule(stamp) -> str:
    """The rule every row states, in the ruled form, with the read it consulted: the fixture's current pregame row's
    fetched_at, else its season's latest ingest record's (the read that served no flag), else NO_READ."""
    return NEUTRAL_PREGAME_RULE.format(stamp=stamp.isoformat() if stamp else NO_READ)


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


def not_declared(eid: str) -> str:
    """The refusal of a registry holding no entry for `eid`: the export's (frozen) and the counter's one text, never
    dormancy (Codex on #816: an absent declaration is not a null verdict)."""
    return (f"{eid} is not declared in docs/registry — the NCAA shadow starts only once it is (ARCHITECT 2026-10-07, "
            "addendum 6 item 1)")


def frozen(registry_path: str | None = None, eid: str = EID) -> tuple[dict, bool, str]:
    """(entry, home advantage at neutral sites?, rule) from the registry; refuses unless `eid` is declared and its
    declaration states the neutral-site rule and freezes v1's constants. v1r: refuses once the registry records a
    verdict other than PASS (addendum 24 item 2(d)). v2: refuses unless the registry records a PASS (addendum 158
    item 1(b): "it exports nothing unless the registry verdict is PASS")."""
    from src.walters import registry as reg

    b = binding(eid)
    # addendum 236 item 3(7): ONE source, registry.LEDGER read at call time (never get()'s import-time default)
    e = reg.get(b.eid, registry_path or reg.LEDGER)
    if e is None:
        raise ShadowRefused(f"REFUSED: {not_declared(b.eid)}")
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
    from src.ingestion import ncaa_cfbd as nc
    from src.walters import ncaa_backtest as nb
    from src.walters.export import _fixture_row

    now = now or utc_now_naive()
    b = binding(eid)
    e, neutral_ha, rule = frozen(registry_path, eid=eid)
    scale = bound_scale(b, e)
    label = gate_label(e)
    model, rc, merge = fit(now, neutral_ha, scale=scale)
    rc["neutral_site_rule"] = rule
    seen = refresh_seen(now)                        # addendum 236 item 3(4): the refresh this export saw
    rows, skipped, pregame, orients = [], Counter(), Counter(), Counter()
    with session_scope() as s:
        fbs = fbs_teams(s, merge)
        q = (select(Match).join(Competition, Match.competition_id == Competition.id)
             .where(Match.sport == Sport.NFL, Competition.code == COMPETITION,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now, Match.utc_date < now + timedelta(hours=hours))
             .order_by(Match.utc_date, Match.id))
        window = list(s.execute(q).scalars())
        flags = nc.pregame_flags(s, [m.id for m in window])   # addendum 236 item 3(1): CFBD's pregame field
        stamps = nc.latest_record_stamps(s)
        for m in window:
            pf = flags.get(m.id)
            cur = pf if pf and pf["current"] else None          # L3's rule: a stale row is never read
            nf = cur["neutral"] if cur else None
            orient = cfbd_orientation(cur)                    # addendum 239 item 2: orientation counts
            home, away = merge(m.home_team_id), merge(m.away_team_id)     # J2: merged ids, as walked
            # the Game in CFBD's order, as game_from_rows walks a swapped label; the flag as the walk reads it
            g = live_game(home, away, m.season, m.utc_date, m.stage, nf, orient, match_id=m.id)
            why = nb.exclusion_reason(g)
            if why:
                skipped[why] += 1
                continue
            if g.home_id not in fbs or g.away_id not in fbs:
                skipped["not_both_fbs"] += 1
                continue
            pregame["neutral" if nf else "not_neutral" if nf is False
                    else "unknown_stale_row" if pf and not cur else "unknown_no_flag_served" if cur
                    else "unknown_no_row"] += 1
            orients[orient or "unknown"] += 1                   # swapped: priced in CFBD's order (239 item 2)
            stamp = cur["fetched_at"] if cur else stamps.get(str(m.season))
            p = listed_home_prob(model, g)                      # stated for OUR listed home (CFBD's order priced)
            ha = model.home_adv(g)
            row = _fixture_row(s, m, COMPETITION, Counter(), Counter())
            pick_home = p >= 0.5
            row.update({
                "competition": COMPETITION, "family": FAMILY,
                "engine": ENGINE, "model_version": b.model_version, "gate_verdict": label, "registry_id": b.eid,
                # addendum 158 item 1(b): the input cutoff (the walk read every stream game kicking off before it)
                # and the prediction stamp (this export's clock), on every row
                "input_cutoff": now.isoformat(), "prediction_stamp": now.isoformat(),
                # addendum 236 item 3(4): the refresh-by-id run this export saw (its receipt), whatever its exit
                "refresh_seen": seen,
                "prediction": {"home_win_prob": round(p, 4), "away_win_prob": round(1 - p, 4),
                               "top_pick": "home_win" if pick_home else "away_win",
                               "top_pick_prob": round(p if pick_home else 1 - p, 4),
                               "elo_home": round(model.rating(home), 1),      # our listed home's
                               "elo_away": round(model.rating(away), 1),      # our listed away's
                               # addendum 236 item 3(1): the walk's own treatment of CFBD's flag (NeutralRuleElo);
                               # addendum 239 item 2: given to CFBD's home (home_adv_to names which of ours)
                               "home_adv_applied": ha,
                               "home_adv_to": (None if not ha else "listed_away" if orient == "swapped"
                                               else "listed_home"),
                               "home_adv_basis": (SWAPPED_BASIS[nf] if orient == "swapped" and nf is not True
                                                  else HOME_ADV_BASIS[nf]),
                               "orientation": orient or "unknown",
                               "orientation_rule": ORIENTATION_TEXT[orient],
                               "neutral": nf,
                               "neutral_flag": (NEUTRAL_FLAG_NEUTRAL if nf else NEUTRAL_FLAG_NOT if nf is False
                                                else NEUTRAL_FLAG_UNKNOWN),
                               "neutral_source": "cfbd_pregame" if nf is not None else None,
                               "neutral_read": stamp.isoformat() if stamp else None,
                               "neutral_rule": neutral_rule(stamp),
                               "pregame_orientation": cur["orientation"] if cur else None,
                               **({"logistic_scale": scale} if scale is not None else {})},
            })
            rows.append(row)
        s.rollback()
    rc["neutral_pregame"] = dict(sorted(pregame.items()))
    rc["orientation_pregame"] = dict(sorted(orients.items()))   # addendum 239 item 2: same / swapped / unknown
    return {"rows": rows, "fit": rc, "skipped": dict(skipped), "label": label, "now": now, "binding": b,
            "refresh_seen": seen}


def export(now: datetime | None = None, hours: int = WINDOW_HOURS, out_dir: str = "exports",
           registry_path: str | None = None, eid: str = EID, dry_run: bool = False) -> tuple[str | None, dict]:
    """The shadow file. `dry_run` (addendum 236 item 3(5): "a `--dry-run` prints the rows it would write and writes
    nothing, for the laptop"): every precondition and refusal as a real run, the document built, no file (path None)."""
    r = build_rows(now, hours, registry_path, eid=eid)
    b = r["binding"]
    now = r["now"]
    # Codex on #344: second precision and an exclusive create, so a rerun never replaces an earlier artifact
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M%S')}.json")
    doc = {"sport": "ncaa", "competition": COMPETITION, "family": FAMILY, "engine": ENGINE,
           "model_version": b.model_version, "registry_id": b.eid, "gate_verdict": r["label"],
           "contains_predictions": False,   # nothing here is a live prediction (doctrine)
           "gate_evidence": False,          # the shadow's live record is not gate evidence (ruling)
           "exported_at": now.isoformat(),
           "git_sha": _git_sha(),  # addendum 249 item 2: the producing checkout (export.py's stamp)
           "window_hours": hours, "note": b.note,
           "refresh_seen": r["refresh_seen"],
           "fit": r["fit"], "skipped": r["skipped"], "count": len(r["rows"]), "predictions": r["rows"]}
    if dry_run:
        return None, doc
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x") as f:
            json.dump(doc, f, indent=2, default=str)
    except FileExistsError:
        raise ShadowRefused(f"REFUSED: {path} already exists — an artifact is never overwritten; re-run next second")
    return path, doc


# THE ORDER (ARCHITECT 2026-11-03, addendum 236 item 3(4), verbatim in part): "the export runs whether or not
# refresh-by-id succeeded, on the stored state it finds, its rows stamped with the refresh it saw (the window chain's
# rule, 84 item 2(b): a sync step's failure does not stop the chain); the refresh failure pages as now." The refresh
# it saw is read from sp_common.receipts_path() at or before the export's clock, in log order: the latest NCAA
# refresh_by_id receipt (refresh-by-id appends it once rbi.refresh returns, so a refresh that raises before then writes
# none) and the latest chain step receipt of `refresh-by-id --competition NCAA` (sp_run.run_steps appends it after the
# step, whatever its exit, before the next step runs). A refresh step receipt with no refresh_by_id receipt between it
# and the step receipt before it (the same run's previous step, or an earlier refresh step) is a run that wrote none:
# a nonzero exit reads "failed" with that step's exit and stamp, never an earlier receipt. None read: state "none"
# with the reason.
REFRESH_RULING = "ARCHITECT 2026-11-03, addendum 236 item 3(4)"


def _receipts_path() -> Path:
    import sys

    hosting = str(Path(__file__).resolve().parents[2] / "deploy" / "hosting")
    if hosting not in sys.path:
        sys.path.insert(0, hosting)
    try:
        import sp_common                            # the path refresh-by-id appends to (SP_RECEIPTS, else logs/)
    except ImportError:                             # a machine without fcntl: the same default, from the environment
        import os
        return Path(os.environ.get("SP_RECEIPTS") or Path(__file__).resolve().parents[2] / "logs" / "receipts.jsonl")
    return Path(sp_common.receipts_path())


def refresh_seen(now: datetime, competition: str = COMPETITION, path: str | Path | None = None) -> dict:
    """The refresh-by-id run this export saw: {state ok | failed | none, ts, now, age_hours, selected, updated,
    not_found, unresolved, still_rate_limited, error, rule[, step_exit]}. ok: no error, nothing unresolved, nothing
    still rate limited (refresh-by-id's exit 0) and its chain step, when one is receipted after it, exited 0. A chain
    refresh step that wrote no refresh_by_id receipt reads failed (its exit, its stamp), never the earlier run's.
    Read-only; an unreadable receipts log reads none, with the reason."""
    p = Path(path) if path else _receipts_path()
    base = {"rule": f"the latest {competition} refresh_by_id receipt at or before the export, or the chain's "
                    f"refresh-by-id step when that run wrote none ({REFRESH_RULING})"}
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        return {**base, "state": "none", "why": f"no receipts log read at {p} ({type(err).__name__})"}
    cmd = f"python cli.py refresh-by-id --competition {competition}"
    step = None                                        # the latest refresh step receipt seen, walking back
    for ln in reversed(lines):
        rid = step[0].get("run_id") if step is not None else None
        if '"refresh_by_id"' not in ln and "refresh-by-id" not in ln and not (rid and str(rid) in ln):
            continue
        try:
            x = json.loads(ln)
        except ValueError:
            continue
        is_step = (x.get("kind") == "step" and x.get("exit") is not None
                   and (str(x.get("command") or "") + " ").startswith(cmd + " "))
        if rid and not is_step and x.get("kind") == "step" and x.get("run_id") == rid:
            break                                      # the run's step before the refresh: the refresh wrote none
        if not is_step and (x.get("kind") != "refresh_by_id" or x.get("competition") != competition):
            continue
        try:
            ts = datetime.strptime(str(x.get("ts")), "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
        if ts > now:
            continue
        if is_step:
            if step is not None:                       # two refresh steps with no receipt between: the later wrote none
                break
            step = (x, ts)
            continue
        n = (lambda k: len(x.get(k) or []))
        bad = (bool(x.get("error")) or n("unresolved") > 0 or n("still_rate_limited") > 0
               or (step is not None and step[0].get("exit") != 0))     # its own step failed after the receipt
        return {**base, "state": "failed" if bad else "ok", "ts": x.get("ts"), "now": x.get("now"),
                "age_hours": round((now - ts).total_seconds() / 3600, 2), "selected": x.get("selected"),
                "updated": x.get("updated"), "not_found": n("not_found"), "unresolved": n("unresolved"),
                "still_rate_limited": n("still_rate_limited"), "error": x.get("error"),
                **({"step_exit": step[0].get("exit")} if step is not None else {})}
    if step is not None:                               # the latest refresh step wrote no refresh_by_id receipt
        x, ts = step
        held = step_held_codes(x)
        if competition in held:                        # SP_SYNC_HOLD (#928; ARCHITECT 2026-11-11, addendum 336 item 2)
            why = (f"the refresh-by-id step was HELD (SP_SYNC_HOLD {competition}): it wrote nothing and no "
                   "refresh_by_id receipt")
            return {**base, "state": "none", "ts": x.get("ts"), "now": None,
                    "age_hours": round((now - ts).total_seconds() / 3600, 2), "selected": None, "updated": None,
                    "not_found": 0, "unresolved": 0, "still_rate_limited": 0, "error": why, "why": why,
                    "step_exit": x.get("exit"), "held": held}
        why = f"the refresh-by-id step exited {x.get('exit')} and wrote no refresh_by_id receipt"
        return {**base, "state": "failed" if x.get("exit") != 0 else "none", "ts": x.get("ts"), "now": None,
                "age_hours": round((now - ts).total_seconds() / 3600, 2), "selected": None, "updated": None,
                "not_found": 0, "unresolved": 0, "still_rate_limited": 0, "error": why, "why": why,
                "step_exit": x.get("exit")}
    return {**base, "state": "none", "why": f"no {competition} refresh_by_id receipt at or before "
                                            f"{now.isoformat()} in {p}"}


_HELD_LINE = re.compile(r"^HELD (?P<code>[A-Za-z0-9_]+) \(SP_SYNC_HOLD\)$")    # src/ingestion/sync_hold.held_line


def step_held_codes(x: dict) -> list:
    """The codes a chain step receipt says it held (#928): sp_run's `sync.held`, else the HELD lines in its tail
    (sync_hold.held_line: "HELD <CODE> (SP_SYNC_HOLD)"). Read-only; [] when none."""
    codes = list(((x.get("sync") or {}).get("held")) or [])
    for ln in x.get("tail") or []:
        m = _HELD_LINE.match(str(ln).strip())
        if m and m.group("code").upper() not in codes:
            codes.append(m.group("code").upper())
    return codes


def refresh_seen_text(x: dict) -> str:
    if x.get("state") == "none":
        return f"refresh seen: none — {x.get('why')}"
    if x.get("selected") is None and x.get("step_exit") is not None:     # a refresh step that wrote no receipt
        return f"refresh seen: {x['state'].upper()} at {x['ts']} ({x['age_hours']}h before the export) · {x['why']}"
    return (f"refresh seen: {x['state'].upper()} at {x['ts']} ({x['age_hours']}h before the export) · selected "
            f"{x['selected']} · updated {x['updated']} · not found {x['not_found']} · unresolved {x['unresolved']} · "
            f"still rate limited {x['still_rate_limited']}" + (f" · error {x['error']}" if x.get("error") else ""))


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


def same_fixture(c: dict, m) -> bool:
    """Codex on #344: match ids are machine-local and reusable (init-db --force); a shadow row is this match's only
    when its teams and kickoff are (and the match is stored, an NCAA fixture). grade() never grades a row against a
    match that fails it; the confirmation counter never counts it as the cohort fixture's shadow row (Codex on #816)."""
    return not (m is None or m.competition is None or m.competition.code != COMPETITION
                or (c.get("home_team"), c.get("away_team")) != (m.home_team.name, m.away_team.name)
                or c.get("utc_date") != m.utc_date.isoformat())


# (6) #413, NO WAIT (ARCHITECT 2026-11-03, addendum 236 item 3(6), verbatim): "The confirmation's Kalshi grade reads
# legs placed on or after 2026-10-13 (#475's switch to the shared pair); earlier placements never enter it, stated on
# the console." THE BOUNDARY, RULED (ARCHITECT 2026-11-03 16:15 ET, addendum 239 item 4, verbatim): "not midnight —
# the INSTANT the tag carrying #475 was deployed to the host (RELEASES.md and the deploy receipt of that day name it;
# Code reads it and writes it in the PR body and on the console); legs placed before that instant were the old path's.
# If the record does not name it, the conservative bound is 2026-10-14T04:00:00Z (the next ET midnight) and the console
# says why." Read (law 1): #475 merged as 1294960a (2026-10-13 13:03:38Z); the first tag carrying it is v1.4.0
# (`git tag --contains 1294960a`; not an ancestor of v1.3.0), cut 2026-10-16 14:18:21Z (docs/RELEASES.md:111). The
# v1.4.0 section of docs/RELEASES.md carries no "Deploy:" line (v1.5.0's does: "on the host at 13:40:09Z (v1.4.0 ->
# v1.5.0 ...)"), and BACKLOG.md, CHANGELOG.md, docs/ and deploy/ name no v1.3.0 -> v1.4.0 deploy instant. v1.4.0's
# release Issue (#556, docs/RELEASES.md:111), where a release's deploy receipt is filed (v1.6.2's #776), was read on
# 2026-11-03: its Host section says "Not deployed yet. ... Its record follows here once the architect has read the
# console." and none of its comments records the deploy. So the record names no instant, and the ruled
# fallback: 2026-10-14T04:00:00Z, naive UTC as captured_at stores it. A Kalshi row captured before this instant is never
# read by the shadow's Kalshi close, nor by its legs guard (the newest legs, the mismatched set and the events' homes:
# kalshi_legs' captured_from floor); a game whose every Kalshi row is earlier is left out as LEGS_BEFORE.
KALSHI_LEGS_FROM = datetime(2026, 10, 14, 4, 0, 0)              # 2026-10-14T04:00:00Z, naive UTC (the fallback)
LEGS_FROM_TEXT = "2026-10-14T04:00:00Z (2026-10-14 00:00 ET)"
LEGS_BEFORE = "legs_before_2026_10_14"
LEGS_RULING = "ARCHITECT 2026-11-03, addendum 236 item 3(6); the boundary, addendum 239 item 4"
LEGS_WHY = ("the repo record (docs/RELEASES.md, BACKLOG.md, CHANGELOG.md, docs/, deploy/) names no deploy instant "
            "for the tag carrying #475, nor does v1.4.0's release Issue #556 (read: its Host section says \"Not deployed yet\" and no later comment records the deploy); the conservative bound is "
            "the next ET midnight, addendum 239 item 4 (#475 is first carried by v1.4.0, cut 2026-10-16 14:18:21Z, "
            "docs/RELEASES.md:111; its section has no Deploy line)")
# ARCHITECT 2026-11-03 17:40 ET, addendum 240 item 3, verbatim: "the rows before 10-26 were the laptop's captures on
# main, which carried #475 from its merge at 2026-10-13T13:03Z, so the instant that governs them is that merge, and the
# ruled fallback 2026-10-14T04:00:00Z is LATER, i.e. conservative: it keeps ~15 h of correctly placed legs out of the
# grade and lets none of the old path's in. It STANDS; the console prints both instants and why."
LEGS_MERGE_FROM = "2026-10-13T13:03:38Z"     # #475's merge (1294960a): the instant that governs the laptop's captures
LEGS_BOTH = (f"both instants (addendum 240 item 3): #475 merged to main at {LEGS_MERGE_FROM} (1294960a), the instant "
             "that governs the rows before the 10-26 cutover (the laptop's captures on main); the ruled bound "
             f"{LEGS_FROM_TEXT} is LATER, so conservative: it keeps about 15 h of correctly placed legs out of the "
             "grade and lets none of the old path's in")
LEGS_TEXT = (f"legs placed before {LEGS_FROM_TEXT} were the old path's (#475's switch to the shared pair) and never "
             f"enter it, the close nor its legs guard: {LEGS_WHY}; {LEGS_BOTH}; a game whose every Kalshi leg is earlier is left "
             f"out ({LEGS_BEFORE}) ({LEGS_RULING})")
# (2) THE CLOSE (ARCHITECT 2026-11-03, addendum 236 item 3(2), verbatim): "the Kalshi close is THE close for college
# (KXNCAAFGAME is the primary college market source — CLAUDE.md), scored per name, never pooled, as built; the book
# close stays beside it as a reference line; the D4 baseline is a second REFERENCE name, never a verdict's input; the
# 2023 and 2026 fences apply to the Kalshi block exactly as to the record until the 11-09 run's verdict is recorded,
# then lift for 2026 as ruled." THE FENCES, CONFIRMED (ARCHITECT 2026-11-03 16:15 ET, addendum 239 item 3, verbatim):
# "the 2023 and 2026 fences lift TOGETHER when the 11-09 run and its verdict are recorded (both say "withheld until
# the ncaa-elo-v2 run is recorded"); my "then lift for 2026" named the one that matters for the confirmation, not an
# exception for 2023."
CLOSE_RULING = "ARCHITECT 2026-11-03, addendum 236 item 3(2)"
D4_REF_NAME = "d4_baseline (reference)"
D4_REF_TEXT = ("the D4 baseline (the run's frozen baseline_home_rate in a non-neutral game, 0.5 where the game's CFBD "
               "label says neutral), a REFERENCE name against the same Kalshi close on the same games, never a "
               f"verdict's input ({CLOSE_RULING})")
BOOK_REF_TEXT = f"reference: the book close (close_1x2 + the stale-book rule), never THE close ({CLOSE_RULING})"


def v2_verdict_recorded() -> bool:
    """True once the registry (registry.LEDGER, read at call time) records a verdict for ncaa-elo-v2."""
    from src.walters import registry as reg

    e = reg.get(V2_EID, reg.LEDGER)
    return bool(e and (e.get("verdict") or {}).get("verdict"))


def kalshi_fenced() -> bool:
    """Addendum 236 item 3(2): the 2023 / 2026 fences apply to the Kalshi block "exactly as to the record until the
    11-09 run's verdict is recorded": fenced while ncaa-elo-v2's run (the record's own lift,
    ncaa_backtest.v2_run_recorded) or its verdict is unrecorded; both lift TOGETHER after (addendum 239 item 3:
    "the 2023 and 2026 fences lift TOGETHER when the 11-09 run and its verdict are recorded")."""
    from src.walters import ncaa_backtest as nb

    return not (nb.v2_run_recorded() and v2_verdict_recorded())


def d4_rate(eid: str) -> tuple[float | None, str | None]:
    """(the D4 baseline's frozen rate, None) from `eid`'s run record (registry.LEDGER at call time), or (None, why)."""
    from src.walters import registry as reg

    e = reg.get(eid, reg.LEDGER) or {}
    rate = ((e.get("run") or {}).get("result") or {}).get("baseline_home_rate")
    if not isinstance(rate, (int, float)) or isinstance(rate, bool):
        return None, f"{eid} has no run record with baseline_home_rate (the D4 baseline is the run's frozen rate)"
    return float(rate), None


def _d4_home(s, m, rate: float) -> float:
    """D4's home probability for OUR listed home (ncaa_v1r_gate.baseline_p on the game as the stream reads it: the
    CFBD label's flag, 0.5 at a neutral site; the rate is CFBD's home's, so a 'swapped' label prices our home 1 - rate)."""
    from src.db.schema import NCAACFBDLabel
    from src.ingestion.ncaa_cfbd import has_table, label_load_options
    from src.walters import ncaa_v1r_gate as g

    lab = s.get(NCAACFBDLabel, m.id, options=label_load_options(s)) if has_table(s) else None
    neutral = lab.neutral if lab is not None else None
    from types import SimpleNamespace

    p = g.baseline_p(SimpleNamespace(neutral=neutral), rate)
    return 1 - p if lab is not None and lab.orientation == "swapped" and neutral is not True else p


class KalshiClose:
    """THE close for college (addendum 236 item 3(2)), the close record's two-way rule, over a session's finished
    matches: the legs on or after KALSHI_LEGS_FROM only (item 3(6)); the 2023 / 2026 fences (kalshi_fenced) and a
    three-way board BEFORE the result (pre), then no result / a tie (the caller's), then LEGS_BEFORE, mismatched legs
    and no close (close: paper.guarded_two_way_close, the record's own function). One instance per read, shared by
    grade() and confirmation_record()."""

    def __init__(self, s, matches):
        from src.walters import kalshi_legs
        from src.walters import ncaa_backtest as nb
        from src.walters import paper

        ids = [m.id for m in matches]
        every = paper._kalshi_snaps(s, ids)
        self.snaps = {mid: [x for x in rows if x.captured_at is not None and x.captured_at >= KALSHI_LEGS_FROM]
                      for mid, rows in every.items()}
        self.before = {mid for mid, rows in every.items() if rows and not self.snaps.get(mid)}
        # the legs guard reads the same floor (item 3(6)): an earlier leg is never judged, here or on another game
        self.mism = kalshi_legs.mismatched(s, ids, KALSHI_LEGS_FROM) if ids else {}
        self.tickers, self.current, self.homes = paper.two_way_legs(s, matches, self.snaps, KALSHI_LEGS_FROM)
        self.fence = kalshi_fenced()
        self.labs = nb.label_seasons(s, matches) if self.fence else {}

    def pre(self, m) -> str | None:
        from src.walters import close as _close
        from src.walters import ncaa_backtest as nb

        seasons = {str(m.season), self.labs.get(m.id, (None,))[0]}
        return ("fenced_2023" if self.fence and nb.V2_SECOND in seasons
                else "fenced_2026" if self.fence and nb.V2_TEST in seasons
                else "three_way" if tuple(_close.outcomes_for(m.sport)) != _close.BINARY else None)

    def close(self, m) -> tuple[dict | None, str | None]:
        from src.walters import paper

        if m.id in self.before:
            return None, LEGS_BEFORE
        return paper.guarded_two_way_close(m, self.snaps.get(m.id, []), self.mism, self.tickers,
                                           self.current.get(m.id), self.homes)


def _kx() -> dict:
    from src.walters import paper

    return {"identity_mismatch": 0, "fenced_2023": 0, "fenced_2026": 0, "three_way": 0, "no_result": 0, "tie": 0,
            LEGS_BEFORE: 0, paper.MISMATCHED: 0, paper.NO_CLOSE: 0}


def grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None, progress=None,
          eid: str = EID) -> dict:
    """Results (hit rate, log-loss, Brier) and model-vs-close for finished NCAA games whose call exists in a shadow
    export of the `eid` binding (never pooled). THE close is Kalshi's (KalshiClose; addendum 236 item 3(2)), per name:
    the binding's model and the D4 baseline as a REFERENCE name; the book close is a reference line beside it. Not
    gate evidence."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.close import KALSHI_SOURCES, close_1x2, outcomes_for, priced, stale_book_close
    from src.walters.nfl_predict import _book_anchor, value_side_grade
    from src.walters.vs_close import block

    now = now or utc_now_naive()
    b = binding(eid)
    tag = b.model_version.replace("ncaa_elo_", "")             # v1r_H= / v2_H= on each line
    calls = last_calls(export_dir, eid=b.eid)
    rate, rate_why = d4_rate(b.eid)
    hits, lls, briers, clvs, vclvs, lines = [], [], [], [], [], []
    pairs = []                         # addendum 64 item 2: (model p, close p) of the outcome, games with a close
    kalshi_fed = 0                     # of those, the closes a Kalshi mid priced (the stale-book rule)
    graded = unpriced = unanchored = ties = no_result = identity_mismatch = 0
    # addendum 230 item 1(b) / 236 item 3(2): the record against THE (Kalshi) close, each name on its own: this
    # binding's model, and the D4 baseline as a reference name on the same games (never pooled, never a verdict input)
    kpairs, dpairs = [], []
    # every finished call in the window lands in exactly one: n + sum(kalshi_close_excluded) == the window's calls
    kx = _kx()
    with session_scope() as s:
        window = [m for m in (s.get(Match, mid) for mid in calls)
                  if m is not None and m.status == MatchStatus.FINISHED and m.utc_date >= now - timedelta(days=days)]
        kc = KalshiClose(s, window)
        for mid, c in sorted(calls.items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            if not same_fixture(c, m):
                identity_mismatch += 1
                kx["identity_mismatch"] += 1                # the shadow's own guard: the row is not this match's
                continue
            # the Kalshi close's exclusions in the close record's order (paper.close_record): the fences and a
            # three-way board BEFORE the result, so a fenced game with no result or a tie counts as fenced, as there
            kpre = kc.pre(m)
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
                # the same graded games that have one. Addendum 236 item 3(2): a REFERENCE line beside THE close.
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
            # THE close (Kalshi), the close record's rule (paper.close_record's two-way order after the result)
            kcl, kwhy = None, kpre
            if kwhy is None:
                kcl, kwhy = kc.close(m)
            if kwhy:
                kx[kwhy] += 1
            else:
                kside = "HOME" if y else "AWAY"
                kpairs.append((p if y else 1 - p, kcl["fair"][kside]))
                if rate is not None:
                    dh = _d4_home(s, m, rate)
                    dpairs.append((dh if y else 1 - dh, kcl["fair"][kside]))
            line = (f"  {m.away_team.name[:16]:16} @ {m.home_team.name[:16]:16} {tag}_H={p:.3f} "
                    f"result {hs}-{as_} ({src}) {'HIT' if hits[-1] else 'miss'} · "
                    f"kalshi_close_H={'%.3f' % kcl['fair']['HOME'] if kcl else '— (' + kwhy + ')'} (THE close)"
                    f" · reference book close_H={'%.3f' % close_h if close_h is not None else '  — '} "
                    f"div={'%+.1fpp' % (clv * 100) if clv is not None else '—'} "
                    f"value={(vg['side'] + ' %+.1fpp' % (vg['value_side_clv'] * 100)) if vg else '— (no anchor)'}"
                    " · NOT gate evidence")
            lines.append(line)
            if progress:
                progress(line)
    vk = {b.model_version: block(kpairs)}
    if rate is not None:
        vk[D4_REF_NAME] = block(dpairs)                         # a reference name, same games, never pooled
    return {"graded": graded, "calls_on_file": len(calls), "ties_skipped": ties, "no_result": no_result,
            "identity_mismatch": identity_mismatch,
            "hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
            # the line names the closes a Kalshi mid priced, as every results file's block does (addendum 137 item 4)
            "vs_close": {**block(pairs), "kalshi_only_closes": kalshi_fed},    # a reference line ("references")
            # addendum 230 item 1(b) / 236 item 3(2): the record against THE close (Kalshi), per name, never pooled
            "vs_kalshi_close": vk,
            "references": {"book_close": BOOK_REF_TEXT, D4_REF_NAME: D4_REF_TEXT if rate is not None
                           else f"absent: {rate_why}"},
            "kalshi_close_excluded": kx,
            "kalshi_close_rule": KALSHI_CLOSE_RULE,
            "log_loss": round(sum(lls) / len(lls), 4) if lls else None,
            "brier": round(sum(briers) / len(briers), 4) if briers else None,
            "priced": len(clvs), "unpriced": unpriced,
            "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
            "value_side_n": len(vclvs), "unanchored": unanchored,
            "mean_value_side_clv_pp": round(sum(vclvs) / len(vclvs) * 100, 2) if vclvs else None,
            "lines": lines}


KALSHI_CLOSE_RULE = ("THE close for college (KXNCAAFGAME, addendum 236 item 3(2)): the close record's two-way rule "
                     "(paper.close_record): the last two-sided pre-kickoff Kalshi HOME quote's mid under the 2c cap "
                     "(close.close_from_kalshi), books not read; " + LEGS_TEXT + "; left out in order: first the "
                     "shadow's own identity guard (the row's teams and kickoff are not this match's), then the "
                     "record's order: the 2023 / 2026 fences until ncaa-elo-v2's run and its verdict are recorded, a "
                     "three-way board, no decided result, a tie (a data defect), legs before " + LEGS_FROM_TEXT + ", "
                     "mismatched legs (kalshi_legs.mismatched, then the HOME row the close reads, "
                     "paper.close_row_mismatched), no close")


def confirmation_counter(eid: str = V2_EID, export_dir: str = "exports") -> dict:
    """THE CONFIRMATION COUNTER TO 100 (ARCHITECT 2026-11-03, addendum 230 item 1(b): "the confirmation counter to
    100; dormant while the verdict is null or FAIL"). A count, never a verdict and never a figure of the games:
    - {"state": "refused", "why"} when the registry holds no entry for `eid` (the export's refusal, not_declared:
      never dormant, Codex on #816);
    - {"state": "dormant", "why"} while the registry records no verdict, or a verdict other than PASS, for `eid`;
    - {"state": "refused", "why"} when the read refuses after a PASS (no run record, D6 coverage: GateRefused);
    - else {"state": "counting", ...ncaa_v1r_gate.confirmation_count (n scored of n_games, the cohort's state and
      size, pending by status, releases due, complete), "shadow_rows": cohort fixtures holding a row of this binding
      written before kickoff (last_calls) whose teams and kickoff are that fixture's (same_fixture, grade()'s guard),
      "shadow_rows_scored": of the scored ones, "shadow_identity_mismatch": cohort ids whose row fails that guard}.
    registry.LEDGER, read once at call time, is the one registry read: the verdict here and the count's confirming()
    (Codex on #816; addendum 236 item 3(7): no path parameter, so no second source). The confirmation fixture is D7's,
    as ncaa-confirm reads it (any status, frozen once); a fixture without a shadow row still counts (the shadow row is
    printed beside, never a condition). Read-only."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import ncaa_v1r_gate as g
    from src.walters import registry as reg

    b = binding(eid)
    path = reg.LEDGER                                        # one registry for the verdict and the count (236 3(7))
    e = reg.get(b.eid, path)
    if e is None:
        return {"state": "refused", "why": not_declared(b.eid)}
    verdict = (e.get("verdict") or {}).get("verdict")
    if str(verdict or "").upper() != "PASS":
        if b.pass_only:                                      # ncaa-elo-v2: addendum 230 item 1(b)'s dormancy
            return {"state": "dormant", "why": dormant_reason(b.eid, verdict)}
        # v1r: 230 item 1(b) is v2's; v1r's own refusal names its own ruling (addendum 24 item 2(d)), never dormancy
        what = "no verdict" if not verdict else f"the verdict {verdict}"
        return {"state": "refused", "why": f"the registry records {what} for {b.eid}: no confirmation to count"
                + (f" (its shadow refuses on that verdict, {VERDICT_RULING})" if verdict else "")}
    try:
        r = g.confirmation_count(g.spec_of(b.eid), path)
    except g.GateRefused as err:
        return {"state": "refused", "why": str(err)}
    calls = last_calls(export_dir, eid=b.eid)
    held = set(calls) & set(r["cohort_ids"])
    with session_scope() as s:                               # read-only: the guard reads the stored fixture
        rows = {mid for mid in held if same_fixture(calls[mid], s.get(Match, mid))}
        s.rollback()
    return {"state": "counting", **r, "shadow_rows": len(rows), "shadow_rows_scored": len(rows & set(r["scored_ids"])),
            "shadow_identity_mismatch": len(held - rows)}


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
            + f" ({r['shadow_identity_mismatch']} not the fixture's teams and kickoff, never counted)"
            + (" · COMPLETE (the read and its record are ncaa-confirm's)" if r["complete"] else "")
            + " · a count, not a verdict")


# (3) A CONFIRMATION FIXTURE (ARCHITECT 2026-11-03, addendum 236 item 3(3), verbatim): "D7's cohort as declared is the
# COUNT (frozen: the 100 are D7's); the RECORD against the close is on the members holding a prospective shadow row
# before kickoff, and a member without one is named "no prospective row" and unscored, its count printed beside the
# 100. The 11-23 read reads both numbers; what a gap means is that read's ruling, not this PR's. (The first fixtures
# after a 11-09 PASS have no row until the tag that carries the export — named, as the leagues' early games are.)"
FIXTURE_RULING = "ARCHITECT 2026-11-03, addendum 236 item 3(3)"
NO_ROW = "no prospective row"
NO_ROW_OTHER = "no prospective row (a row of another fixture)"


def confirmation_record(eid: str = V2_EID, export_dir: str = "exports") -> dict:
    """The counter (confirmation_counter: D7's COUNT) and, after a PASS, the RECORD against THE close on the COUNTED
    members holding a prospective shadow row (the last row of this binding written before kickoff, last_calls, whose
    teams and kickoff are the fixture's, same_fixture): per name, the binding's model and the D4 baseline as a
    reference (never pooled), the Kalshi exclusions counted (KalshiClose, grade()'s own). Every cohort member without
    such a row is NAMED (id, teams, kickoff, counted or pending) as NO_ROW (NO_ROW_OTHER when the only row is another
    fixture's) and is never scored. No days window: the cohort is the window. One registry (addendum 236 item 3(7)):
    the counter, d4_rate and the Kalshi fences all read registry.LEDGER at call time; no path parameter. Read-only;
    never a verdict."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters.vs_close import block

    r = confirmation_counter(eid, export_dir)
    if r["state"] != "counting":
        return {"counter": r}
    b = binding(eid)
    calls = last_calls(export_dir, eid=b.eid)
    rate, rate_why = d4_rate(b.eid)
    counted = set(r["scored_ids"])
    named, kpairs, dpairs, kx, with_row = [], [], [], _kx(), 0
    with session_scope() as s:
        members = {mid: s.get(Match, mid) for mid in r["cohort_ids"]}
        held = {mid for mid, m in members.items() if mid in calls and same_fixture(calls[mid], m)}
        scored = [members[mid] for mid in r["scored_ids"] if mid in held]
        kc = KalshiClose(s, scored)
        for mid in r["cohort_ids"]:
            if mid in held:
                continue
            m = members[mid]
            named.append({"id": mid, "home": m.home_team.name if m else None, "away": m.away_team.name if m else None,
                          "kickoff": m.utc_date.isoformat() if m else None, "counted": mid in counted,
                          "why": NO_ROW_OTHER if mid in calls else NO_ROW})
        for m in scored:
            with_row += 1
            kpre = kc.pre(m)
            res = _result(s, m)
            if res is None or res[0] == res[1]:
                kx[kpre or ("no_result" if res is None else "tie")] += 1
                continue
            y = 1 if res[0] > res[1] else 0
            kcl, kwhy = (None, kpre) if kpre else kc.close(m)
            if kwhy:
                kx[kwhy] += 1
                continue
            p = calls[m.id]["prediction"]["home_win_prob"]
            side = "HOME" if y else "AWAY"
            kpairs.append((p if y else 1 - p, kcl["fair"][side]))
            if rate is not None:
                dh = _d4_home(s, m, rate)
                dpairs.append((dh if y else 1 - dh, kcl["fair"][side]))
        s.rollback()
    rec = {b.model_version: block(kpairs)}
    if rate is not None:
        rec[D4_REF_NAME] = block(dpairs)
    return {"counter": r, "count": r["n"], "n_games": r["n_games"], "counted_with_row": with_row,
            "record": rec, "record_excluded": kx,
            "references": {D4_REF_NAME: D4_REF_TEXT if rate is not None else f"absent: {rate_why}"},
            "no_prospective_row": named,
            "no_prospective_row_counted": sum(1 for x in named if x["counted"]),
            "no_prospective_row_pending": sum(1 for x in named if not x["counted"])}


def record_lines(x: dict, eid: str) -> list[str]:
    """The printed lines: the COUNT beside the 100, the record against THE close on the members with a row, and every
    member without one named. Never a verdict (the read and its record are ncaa-confirm's)."""
    from src.walters.vs_close import line as _vs_line

    r = x["counter"]
    if r["state"] != "counting":
        return [f"confirmation record {eid}: {r['state'].upper()} — {r['why']}"]
    L = [f"confirmation record {eid} ({FIXTURE_RULING}): count {x['count']}/{x['n_games']} (D7's) · record against "
         f"THE close (Kalshi) on {x['counted_with_row']} counted members holding a prospective row · {NO_ROW}: "
         f"{x['no_prospective_row_counted']} of the counted (unscored) and {x['no_prospective_row_pending']} pending"
         f" · left out of the record: " + ", ".join(f"{k} {v}" for k, v in x["record_excluded"].items() if v)
         + (" none" if not any(x["record_excluded"].values()) else "") + " · a record, not a verdict"]
    L += [f"     {k}: {_vs_line(v)}" for k, v in x["record"].items()]
    L += [f"     {k}: {v}" for k, v in x["references"].items()]
    L += [f"     {n['why']}: match {n['id']} · {n['away']} @ {n['home']} · {n['kickoff']} · "
          f"{'counted' if n['counted'] else 'pending'}" for n in x["no_prospective_row"]]
    return L


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
    Returns per-game rows (match id, kickoff, the two probabilities, |diff|) and the counts. THE PREGAME FLAG
    (addendum 236 item 3(1)): each neutral scored game is priced again as a live row prices it, with CFBD's pregame
    flag True (equal to the gate: `pregame_flag_max_diff` within PARITY_TOL), and with the flag absent (D8's unknown,
    the listed home's advantage: `pregame_absent_max_diff`, reported, the gap a row without CFBD's flag carries).
    THE ORIENTATION (addendum 239 item 2): every scored game is priced again as a live row prices a fixture we list
    the other way round with a current 'swapped' pregame row (live_game in CFBD's order, then listed_home_prob):
    `swapped_compared` games, `swapped_unequal` beyond PARITY_TOL (0 is equal to the gate), `swapped_max_diff`; and in
    our listed order without the orientation (the listed home's 55): `unoriented_max_diff`, reported, the gap a
    swapped fixture would carry if orientation did not count."""
    from dataclasses import replace

    from src.walters import ncaa_backtest as nb
    from src.walters import ncaa_v1r_gate as g

    read = g.spec_of(V2_EID).gate
    rec = _Recorder(nb.NeutralRuleElo(neutral_home_advantage, scale=scale))
    res = g.run_gate(games, model=rec, read=read)
    by_id = {x.match_id: x for x in games}
    rows, pregame, absent, swapped, unoriented = [], [], [], [], []
    for mid, gp in rec.p.items():
        x = by_id[mid]
        m = V1R(neutral_home_advantage, scale=scale)
        walk(m, games, x.utc_date)
        sp = m.predict(x)
        rows.append({"match_id": mid, "kickoff": x.utc_date, "gate": gp, "shadow": sp, "diff": abs(sp - gp)})
        # ORIENTATION (addendum 239 item 2): the same game stored by us the other way round (our listed home = the
        # gate's away), its current pregame row 'swapped', priced as build_rows prices it (live_game, then
        # listed_home_prob): the shadow's P(CFBD's home wins) = 1 - its row's home_win_prob, equal to the gate's p.
        # Without the orientation (our listed order, the listed home's 55) the gap is reported.
        lg = live_game(x.away_id, x.home_id, x.season, x.utc_date, x.stage, x.neutral, "swapped", match_id=mid)
        swapped.append(abs((1 - listed_home_prob(m, lg)) - gp))
        ug = live_game(x.away_id, x.home_id, x.season, x.utc_date, x.stage, x.neutral, None, match_id=mid)
        unoriented.append(abs((1 - listed_home_prob(m, ug)) - gp))
        if x.neutral is True:
            m2 = V1R(neutral_home_advantage, scale=scale)
            walk(m2, games, x.utc_date)
            # the live row's Game: no score, CFBD's pregame flag True (build_rows), then absent (D8)
            live = replace(x, home_score=0, away_score=0, label_source="matches", orientation=None, neutral=True)
            pregame.append(abs(m2.predict(live) - gp))
            absent.append(abs(m2.predict(replace(live, neutral=None)) - gp))
    diffs = [r["diff"] for r in rows]
    return {"scale": scale, "stream": len(games), "gate_scored": res.get("n_scored", 0), "compared": len(rows),
            "unequal": sum(d > PARITY_TOL for d in diffs), "max_diff": max(diffs, default=0.0), "rows": rows,
            "neutral_scored": len(pregame), "pregame_flag_max_diff": max(pregame, default=0.0),
            "pregame_flag_unequal": sum(d > PARITY_TOL for d in pregame),
            "pregame_absent_max_diff": max(absent, default=0.0),
            "swapped_compared": len(swapped), "swapped_max_diff": max(swapped, default=0.0),
            "swapped_unequal": sum(d > PARITY_TOL for d in swapped),
            "unoriented_max_diff": max(unoriented, default=0.0)}


def parity_lines(r: dict, rows: bool = False) -> list[str]:
    L = [f"NCAA v2 SHADOW PARITY ({V2_RULING}) · synthetic · s {r['scale']!r} · stream {r['stream']} games · gate scored "
         f"{r['gate_scored']} · compared {r['compared']} · unequal {r['unequal']} (max |diff| {r['max_diff']:.3g}; "
         f"equal within {PARITY_TOL:g}) · {'EQUAL' if r['compared'] and not r['unequal'] else 'NOT EQUAL'}",
         f"  pregame flag ({NEUTRAL_RULING}): {r['neutral_scored']} scored neutral games priced as a live row "
         f"prices them with CFBD's pregame flag True: unequal {r['pregame_flag_unequal']} (max |diff| "
         f"{r['pregame_flag_max_diff']:.3g}) · "
         f"{'EQUAL' if r['neutral_scored'] and not r['pregame_flag_unequal'] else 'NOT EQUAL'}; with the flag "
         f"absent (D8's unknown, the listed home's advantage) they differ by up to "
         f"{r['pregame_absent_max_diff']:.3g} (reported)",
         f"  orientation ({ORIENTATION_RULING}): {r['swapped_compared']} scored games priced as a live row prices a "
         f"fixture we list the other way round with a current 'swapped' pregame row (the 55 to CFBD's home): "
         f"unequal {r['swapped_unequal']} (max |diff| {r['swapped_max_diff']:.3g}) · "
         f"{'EQUAL' if r['swapped_compared'] and not r['swapped_unequal'] else 'NOT EQUAL'}; in our listed order "
         f"(no orientation, the listed home's 55) they differ by up to {r['unoriented_max_diff']:.3g} (reported)"]
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
