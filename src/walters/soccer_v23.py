"""
soccer-v23: THE DESIGN HARNESS (GATE-CLASS by what it guards; lane soccer-v23, #656; designed with #789). ARCHITECT
2026-11-04 10:10 ET, addendum 248 item 2(b); addendum 230 item 1(d); addendum 216 items 1-3; addendum 243 item 4.
docs/specs/soccer-v23.md quotes each ruling verbatim, carries THE BAR (BAR_TEXT below, pinned by sha256 in a test)
and every declaration slot.

NOTHING HERE HAS RUN ON REAL DATA. "NO run before 11-20's declaration" (248 item 2(b)); "NO run and NO declaration
before 11-20 (a date is never a reason to run early)" (230 item 1(d)). The one run is the operator's block on the
architect's word on 11-27 (216 item 3), through `soccer-v23-gate`, which refuses (exit 2, nothing reserved, nothing
recorded) while the registry holds no declared entry: and it holds none (an undeclared candidate holds no entry:
tests/test_leagues_declaration_220.py; registry.py has no "undeclared" status). v22 is not changed: this module
imports poisson.estimate_strengths / predict_match and elo's own functions and calls them unchanged.

ONE PREDICTION FUNCTION (216 item 4's lane, #789): `predict(snapshot, fixture, arm)` is pure (no database, no clock,
no global read at call time). The snapshot is versioned (SNAPSHOT_VERSION) and immutable (frozen dataclasses, rows a
tuple), digested by `snapshot.sha`. It is built by `snapshot_from_rows` (the replay: a prefix of the walk's rows) or
`snapshot_from_session` (live-shaped: one SELECT bounded at the visibility instant, then the same predicate), which
give the same snapshot, digest included, for the same store and instant (tested). The replay walk and a live caller
therefore price through the same function on the same inputs: "same model, same inputs at the same instant, same
probabilities". A parity harness (230 item 1(e), the sibling PR) can call it from either order; this module does not
import that unmerged code.

THE FIVE ROWS, IDENTICAL BY CONSTRUCTION (ARCHITECT 2026-11-04 13:20 ET, addendum 253 item 2(d); docs/specs/soccer-v23.md
§4b). The replay (`walk`) and live (`predict_live` / `predict_live_slate`) both build their snapshot by calling ONE
builder, `snapshot_from_rows` (live through `snapshot_from_session`, which only reads the store's admitted rows and its
availability record; the walk calls it itself at every instant, and `Prefix` is only a memo of predict's fits keyed by
the builder's own output, never a second builder), and both price through the one `predict`, which reads nothing but
the snapshot and the fixture:
  (1) THE CONTEXT: `rows` (v22's g and b by training.py:196-214's formulas over them; soccer-v23's μ and h fitted on
      them); the stored trained context is never read.
  (2) THE ELO STATE: `elo_pre` (each visible row's pre-kickoff ratings) and `elo_state` (each club's rating and last
      season key after every visible row), filled by `walk_ladder` (production's ladder from the first admitted row,
      the per-team season regression included; v23 applies the fixture's own pending regression, the v22 arm reads the
      state as stored). No season starts fresh.
  (3) THE EARLY-SEASON HISTORY: `rows` again: season S's visible rows, S−1's (v23), and the v22 arm's backfill from
      the visible other-season rows only.
  (4) THE MATCH FACTORS: `availability`, the availability record (addendum 252) read under the RECORDED clock at the
      snapshot's DECISION INSTANT (`Snapshot.decision` = visibility_bound(t), the rows' own bound: under "day" the
      fixture's UTC midnight, the morning chain's reading; under "kickoff" t − RESULT_LAG), never at the kickoff, so
      the replay reads exactly what a live call made at or after the decision instant had on disk; a backfilled fact
      (252 item 1: recorded later than its source_stamp by more than its source's declared cadence,
      record.SOURCE_CADENCE_HOURS filtered to soccer sources: source_cadence_hours, addendum 262 item 2) is excluded,
      labelled, in both paths. No other factor input exists (the injuries, lineups and XI tables are read by neither
      path). Where the record has nothing, the term is OFF in both paths and the walk, the run's lines (every verdict,
      INVALID included) and the preflight print it per era (`availability_lines`). The adapter (`availability_record`)
      reads a migrated record through record.as_of, the one read path (StoreRecord; addendum 263 item 23), and answers
      "no record" where it holds no soccer fact; no soccer source is in the record's vocabulary, so the term is off
      everywhere today.
  (5) SIMULTANEOUS KICKOFFS: `as_of` + `visibility`: the snapshot is a function of the instant, never of the fixture,
      and holds no row kicking off at or after visibility_bound(t) (itself at or before t − RESULT_LAG); fixtures
      sharing a kickoff share ONE snapshot (`by_instant`, in the walk and in predict_live_slate alike).

THE TWO ARMS (both priced by predict on the same snapshot):
  * "soccer-v23": src/models/joint_poisson.py's fit over the fixture's competition's window (seasons S−1 and S as
    visible), its rates priced through the REAL poisson.predict_match by an adaptor (price(): context (1, 1),
    TeamStrength(λ, 1), elo_goal_coeff 0, v22's stored ρ, max_goals and line), so the 0.05 floor, the Dixon–Coles
    cells, the 1X2 renormalisation and the over/under are v22's own bytes.
  * "v22": production as it would have priced the fixture AS OF the snapshot (training._generate_predictions_soccer's
    league branch replayed, on the admitted rows: an AET / PEN row read at its 90-minute score, labelled under
    ADMISSION): g and b from the competition's visible rows over every season (training.py:196-214, b
    clamped to [1.0, 1.30]); the ladder's ratings (no home advantage, no pending regression: the stored state); the
    REAL estimate_strengths on the season's visible rows, plus, below V22_MIN_MATCHES (training.py:476), the
    V22_BACKFILL_LIMIT (training.py:500) most recent VISIBLE other-season rows (the as-of bound utc_date < t that
    production's backfill lacks on a historical replay: it selects Match.season != season with no date bound,
    training.py:489-500), tied kickoffs taken in id-ascending order (production's ORDER BY utc_date DESC has no
    tie-break, so SQL leaves the order undefined; SQLite returns ties in id-ascending scan order, and a test pins the
    arm to the real path with more than 500 other-season rows and tied kickoffs: a declared reading, labelled);
    the promoted default; the REAL predict_match with v22's stored config; no match factors
    (labelled: no history of injuries, lineups or XI exists for the pot, and 216 item 4 rules "Historical injuries are
    never manufactured"; live v22's factor inputs are the injuries, lineups and XI tables, overwritten in place and
    never as-of, so the arm reads none of them and keeps v22's own other inputs from the same snapshot; on the pot the
    record has nothing, so soccer-v23's term is off too and the comparison is like for like). v22 does not change.

THE LADDER (both arms): production's one cross-league LEAGUE ladder (training.py:150-185): every admitted finished
row of a LEAGUE-type soccer competition, in kickoff order (ties by id), EloConfig() defaults, keyed f"{code}:{season}"
with the per-team season regression, stepped through elo.regress_team and elo.update_after_match (a test checks the
walk's end state equals elo.train's). Elo is walked, never fitted.

ADMISSION (one predicate, both builders): a finished soccer row of a LEAGUE-type competition (type not CUP / INTL)
with a kickoff and both scores, passed through the confirmation predicate (soccer_expansion.unscoreable: AWD / WO and
cancelled released; a non-FT raw code with a stored 90-minute score walked on that score; soccer_backtest
._confirmation_rows's rule). Both arms read the same admitted rows; v22's live path reads raw home_score on every
FINISHED row, so it differs from the v22 arm in three places, all labelled: an AWD / WO row it would read is left out
of both arms here, and on an AET / PEN row of a LEAGUE-type competition (a play-off final, e.g.) the v22 arm reads the
stored 90-minute score where live v22 reads the full score with extra-time goals (training.py: the contexts at
196-214, the strengths input and train_elo through _to_train all read home_score / away_score). That is the
confirmation_scoring convention, applied to both arms alike; v22's own gate walk (confirmation_scoring False) reads the
full score too. So the v22 arm equals the real production path at 1e-12 only on a store without such rows; with an AET
row it differs by exactly the score substitution (a test pins both: the arm equals production run on the same store
with that row's full score set to its 90-minute score). RULED AS BUILT (ARCHITECT 2026-11-04 15:45 ET, addendum 254
item 3 Q22 (a)): "v22 re-walked" is v22 on THIS harness, not live v22 reproduced; BAR_TEXT and the run record say so
(V22_REWALKED_LABEL) and the record counts the rows read at their 90-minute score (record_labels). Under scope
LEAGUE_REGULAR a play-off row (an AET final included) is in neither arm's history at all (in_scope; soccer_expansion
F3, "only regular-season rounds are scored and walked"; Codex on #832, round 1): the v22 arm's contexts, strengths,
backfill and ladder skip it as soccer-v23's do, a third labelled difference from live v22, which reads every FINISHED
row of the competition.

THE CONTEXT GAP (ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2; docs/specs/soccer-v23.md "The context gap"). The
soccer gate's walk scores v22 under the default context (soccer_backtest.py: CompetitionScoringContext(), g 1.4, b 1.15)
while production reads the stored trained context (training.py:514), fitted on the whole training pot: neither is
as-of. This design defines g and b IDENTICALLY in its harness and its production path by the ruling's first option,
AS-OF: at each fixture's instant both are estimated from the admitted finished rows visible under the declared
visibility rule, and from nothing else (CONTEXT_DEFINITION). It holds by construction, not by a second
implementation: the harness (walk) and the production path (predict_live, the only live entry point; the PASS shadow
calls it) both call the one function predict on a snapshot, and the snapshot holds only the visible rows. For the v22
arm "g and b" are the CompetitionScoringContext that estimate_strengths and predict_match receive (v22_context: the
training.py:196-214 formulas over the competition's visible rows, every season, b clamped); for soccer-v23 they are the
jointly fitted μ and h of the fixture's window (seasons S−1 and S as visible), reported beside the average team's
implied g = (e^(μ+h) + e^μ)/2 and b = e^(μ+h)/g (the pricing adaptor's context is (1, 1): it carries no g or b). The
stored context is never read: it is fitted on the same games the walk scores, so reading it into a replay would leak
the pot's own totals into every prior-only step (251 item 2: Option 2 REJECTED). Tests pin harness = production (g, b,
μ, h and the probabilities, bitwise) and that no row at or after the instant enters them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from src.availability import record as avr
from src.models import joint_poisson as jp

EID = "soccer-v23"
COMMAND = "soccer-v23-gate"
ENGINE = "soccer_joint_poisson"                 # RULED (addendum 263 item 1); no ModelVersion is minted
BASE_VERSION = "v22"
RULING = ("ARCHITECT 2026-11-04 10:10 ET, addendum 248 item 2(b); addendum 230 item 1(d); addendum 216 items 1-3; "
          "addendum 243 item 4; ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2")
#: 251 item 2: how the harness and the production path define g and b, identically (the module docstring's "THE
#: CONTEXT GAP"). Every prediction's info carries it beside the values it read.
CONTEXT_DEFINITION = ("as-of (addendum 251 item 2): g and b (the v22 arm's CompetitionScoringContext) and soccer-v23's "
                      "fitted mu and h are estimated at each fixture's instant from the admitted finished rows visible "
                      "under the declared visibility rule, and from nothing else, in the harness and the production "
                      "path alike; the stored trained context is never read; the default context only where the "
                      "competition has no visible row (production's own fallback), and G0 and B0 as frozen constants, "
                      "never pot figures: the first season's prior centre, G0 also setting that season's prior "
                      "precision (K_PRIOR·G0) and, in every window, beta's weak prior precision (BETA_PRIOR_PRECISION "
                      "= K_PRIOR·G0)")
#: ARCHITECT 2026-11-04 15:45 ET, addendum 254 item 3 Q4: "the parity statement accepted with its residual (a fixture
#: before the chain's run priced by the previous day's chain) LABELLED in the run record, never silent". The residual
#: is counted only against a chain run time declared in code for this model's live path, and none is (law 4: a time is
#: never guessed; soccer_expansion.SYNC_CHAIN_TIMERS are the leagues export's chains, not soccer-v23's).
DAY_RULE_RESIDUAL = ("a fixture kicking off before the morning chain's run is priced by the previous day's chain "
                     "(labelled residual of the day rule, addendum 254 item 3 Q4)")
DAY_RULE_RESIDUAL_COUNT = ("count not computed: no chain run time is declared in code (none for soccer-v23's live "
                           "path; never guessed)")
#: addendum 254 item 3 Q22: "v22 re-walked" is v22 on THIS harness by definition, not live v22 reproduced, and "the
#: ~3.7e-4 difference from live v22 is labelled in the run record". The figure is the design's SYNTHETIC probe
#: (tests/test_soccer_v23_harness.py, the AET test: the largest probability difference, 3.66e-4 on its one-AET-row
#: store), never a figure of the pot.
V22_REWALKED_LABEL = ("\"v22 re-walked\" is v22 on THIS harness, not live v22 reproduced: both arms read the admitted "
                      "rows, an AET or PEN league row at its 90-minute score where live v22 reads the full score; on a "
                      "store holding such a row it differs from live v22, by about 3.7e-4 in a probability on the "
                      "design's synthetic one-row probe (a synthetic receipt, not a pot figure; addendum 254 item 3 "
                      "Q22)")
#: ARCHITECT 2026-11-05 12:50 ET, addendum 263 item 17: "THE v22 ARM'S TIE ORDER — SQLite's id-ascending, pinned,
#: accepted as "v22's" for the bar and stated in the record (production's own order is SQL-undefined; a pinned order is
#: the only reproducible one)." The run record's line (record_labels).
V22_TIE_ORDER_LABEL = ("the v22 arm's backfill below V22_MIN_MATCHES takes tied kickoffs in SQLite's id-ascending "
                       "order, pinned and accepted as v22's for the bar (production's ORDER BY utc_date DESC is "
                       "SQL-undefined on ties; addendum 263 item 17)")
#: v2 (253 item 2(d)): the snapshot carries the Elo state (elo_pre, elo_state) and the availability record read at the
#: instant (availability) beside the rows; v1 carried the rows and caller-supplied entries.
SNAPSHOT_VERSION = "soccer-snapshot v2"
FINGERPRINT_TAG = f"{EID} stream fingerprint v2"         # v2: the availability reads bound (Codex on #832, round 1)
ARMS = ("v22", "soccer-v23")

V22_MIN_MATCHES = 30                            # training.py:476 MIN_MATCHES_FOR_STRENGTHS (a test greps it)
V22_BACKFILL_LIMIT = 500                        # training.py:500 .limit(500) (a test greps it)
V22_BOOST_CLAMP = (1.0, 1.30)                   # training.py:214 (a test greps it)
#: 253 item 2(d) row 4 for the v22 arm: what it reads of the match factors (none), and why.
V22_FACTORS = ("none (labelled: live v22's factor inputs are the injuries, lineups and XI tables, overwritten in place "
               "and never as-of; the arm reads only the snapshot and no history is manufactured, 216 item 4)")
#: WHEN A RESULT IS KNOWN (the visibility rules; review of the 251 follow-up): a row is visible at t only if its result
#: is known before t. The store holds no final-whistle stamp (schema.Match: utc_date is the kickoff; no finished-at or
#: recorded-at column, law 1), so "known" is a DECLARED bound after kickoff: kickoff + RESULT_LAG_HOURS, which covers 90
#: minutes, half-time, stoppage, extra time, its break and a shoot-out with margin for a delayed start (RULED: ARCHITECT
#: 2026-11-04 15:45 ET, addendum 254 item 3 Q4, the day rule with RESULT_LAG_HOURS = 4 as the bound a result is known,
#: frozen by the declaration: code_constants, the fingerprint; stated in BAR_TEXT). Applied identically by both
#: builders, the cache and predict's own check (visibility_bound is the one bound).
RESULT_LAG_HOURS = 4
RESULT_LAG = timedelta(hours=RESULT_LAG_HOURS)
#: The visibility rules the builders implement: "day" (RULED, addendum 254 item 3 Q4; the only DECLARABLE rule,
#: SLOT_VALUES["visibility"]) and "kickoff" (the result-known bound alone), kept as code for the tests' invariance
#: probes (each pins its property under both rules). No declaration can select "kickoff": slots_state refuses it
#: before any load (Codex on #832, round 3, P1).
VISIBILITY_RULES = ("day", "kickoff")
POT_LABEL = ("the frozen pot as CLAUDE.md names it: 16,546 matches / 24 competitions (v22's); printed as a label, "
             "never a pass condition")
#: THE DECLARED PYRAMID (RULED as built, ARCHITECT 2026-11-05 12:50 ET, addendum 263 item 15: "`PYRAMIDS` declared
#: from the pot's own competitions (England's PL > ELC > EL1 > EL2 as the pot holds them ...)"): the store's only
#: multi-tier LEAGUE family, top tier first, read from src/adapters/api_football.py's England LEAGUE codes
#: (_CODE_TO_META, law 1). A club absent from a competition's S−1 rows whose S−1 rows (the same season label) lie in a
#: HIGHER tier of the same pyramid is RELEGATED (no directional prior: joint_poisson.RELEGATED_*); from a lower tier or
#: from outside the store it is PROMOTED (the persistent promoted prior); from a LEAGUE competition off the pyramid, or
#: from two places (two S−1 competitions, whichever their direction: 282 item 4), it is OFF_PYRAMID: "NOT a refusal:
#: it takes the outside-the-store prior, is counted and labelled. The run never stops on a club's provenance." (263
#: item 15).
PYRAMIDS = (("PL", "ELC", "EL1", "EL2"),)

# ------------------------------------------------------------------------------------------------- THE BAR --
# Written before any result (216 item 3; 230 item 1(d); 248 item 2(b); 251 item 2). A test pins its sha256; the
# declaration's registry entry carries it as `gate`, and the run refuses an entry whose gate differs by one character.
BAR_TEXT = (
    "THE BAR (ARCHITECT, addendum 216 item 3; addendum 230 item 1(d); addendum 248 item 2(b); addendum 251 item 2), "
    "written before any result: soccer-v23's mean three-way log-loss on the frozen pot must be at least 0.0050 BELOW "
    "BOTH v22's recorded figure AND v22's figure re-walked on soccer-v23's harness. PASS iff BOTH (v22's recorded mean "
    "three-way log-loss − soccer-v23's mean three-way log-loss) ≥ 0.0050 AND (v22's re-walked mean three-way "
    "log-loss − soccer-v23's mean three-way log-loss) ≥ 0.0050, every figure unrounded. v22's recorded figure STANDS "
    "as measured and is never recomputed: the run reads it from the declaration slot v22_recorded_log_loss, which the "
    "architect fills from where v22's gate recorded it and names in v22_recorded_source. v22's re-walked figure is v22 "
    "walked by the same harness beside soccer-v23, on the identical scored set, under the same context definition "
    "(as-of: g and b, and soccer-v23's mu and h, estimated at each fixture's instant from the finished games visible "
    "before it under the day visibility rule (addendum 254 item 3 Q4: a game kicking off on a UTC date before the "
    "fixture's), a game visible only once its result is known, at its kickoff plus "
    "RESULT_LAG_HOURS = 4 hours, the bound a result is known, frozen by the declaration; the stored trained context "
    "never read; for the v22 arm, the default context (g 1.4, b 1.15) only where "
    "the competition has no visible game, which is production's own fallback (training.py:217), and for soccer-v23, "
    "G0 and B0 as frozen constants, "
    "never pot figures: the first season's prior centre, G0 also setting that season's prior precision (K_PRIOR·G0) "
    "and, in every window, beta's weak prior precision (BETA_PRIOR_PRECISION = K_PRIOR·G0); neither fallback is a pot "
    "figure; in the harness and the production path alike; \"v22 re-walked\" is v22 on THIS harness, not live v22 "
    "reproduced: both arms read the harness's admitted rows, an AET or PEN league row at its 90-minute score where "
    "live v22 reads the full score, so on a store holding such a row it differs from live v22, by about 3.7e-4 in a "
    "probability on the design's synthetic one-row probe (a synthetic receipt, not a pot figure; the run record "
    "counts the AET and PEN rows; addendum 254 item 3 Q22)) and the same within-season skip "
    "(zero). The recorded figure is read from the slot as measured, by whatever scorer its own gate used, and is never "
    "recomputed; the re-walked figures (soccer-v23's and v22's, on this harness) are computed by "
    "soccer_backtest.soccer_calibration. Each comparison is decided by soccer_backtest.candidate_gate_verdict with "
    "min_delta = training.DEFAULT_PROMOTION_DELTA (0.005). Written as "
    "\"below\", so a tie on EITHER is a rejection: a difference of zero, or any difference under 0.0050, on either "
    "comparison REJECTS; a difference of exactly 0.0050 passes that comparison. INVALID, never a pass, when the two "
    "arms' scored sets differ, are empty, or number under MIN_GATE_N = 30 (soccer_backtest.compare_candidate). The "
    "early-season matches are INCLUDED in the scored set: this candidate's declared within-season skip is zero (no "
    "40-match skip). THE §11 RULINGS (ARCHITECT, addendum 263), frozen with this text: the frozen pot is the "
    "LEAGUE-type competitions' regular rounds only (item 2: scope LEAGUE_REGULAR; cups take cup_strengths in "
    "production and have their own exam, and are not in this pot's log-loss); each competition's first pot season is "
    "scored under soccer-v23's weak prior, as built, and the v22 arm reads its own fallback for the same rows, like "
    "for like (item 3); the constants are as built and frozen by the declaration (item 5): K_PRIOR = 5, the promoted "
    "prior ln 0.85 / ln 1.15, which sits on v22's scale (v22's PoissonConfig promoted priors, set on v22's deflated "
    "ratings, read here as log offsets on S−1's zero mean), the S−1 carry 1.0, and beta's weak prior centred at 0 "
    "with precision K_PRIOR·G0 on ΔE/100 in every window; v22's ρ and c were selected on this pot, and S19, dc-fit, "
    "s14 and soccer-expansion-v1 read it: a tilt toward the incumbent, the conservative direction, accepted, and a "
    "PASS is read against it (item 9); a competition-season with no home or no away goal is excluded by cause, out of "
    "the scored set and out of soccer-v23's window (the v22 arm's history and the ladder keep it), counted and "
    "labelled in the run record, the preflight naming every such season before the reservation, so the exclusion set "
    "is frozen with the declaration and an exclusion that first appears after the reservation is a failure (item "
    "14); an arrival off the declared pyramid (PYRAMIDS: PL > ELC > EL1 > EL2) takes the outside-the-store prior, "
    "counted and labelled: the run never stops on a club's provenance (item 15). The availability record's backfill "
    "cadence is record.SOURCE_CADENCE_HOURS filtered to soccer sources (addendum 262 item 2): no soccer source "
    "declared; every fact carrying a source_stamp is excluded, counted. RPS and Brier are printed for the record and "
    "gate nothing; the market is a reference, never a "
    "feature, and gates nothing. One run, on the architect's word, on a .backup copy opened mode=ro&immutable=1. No "
    "date moves this bar.")
WITHIN_SEASON_SKIP = 0                          # 216 item 3: "no 40-match skip for this candidate ... it is zero"

# ------------------------------------------------------------------------------------- THE DECLARATION SLOTS --
# Every slot is the architect's (11-20). The code holds the allowed values only; the run reads the values from the
# declared registry entry's `declaration_slots` and refuses while any is missing or null. RECOMMENDED is printed for
# the architect; it is never a default.
SLOTS_KEY = "declaration_slots"
#: The stage scopes and first-season rules the builders implement. The slots admit only the RULED ones (ARCHITECT
#: 2026-11-05 12:50 ET, addendum 263 items 2 and 3, stated in BAR_TEXT; Q4's precedent, addendum 254 item 3: a
#: declaration cannot select a history or a scored set BAR_TEXT does not describe); "LEAGUE" and "exclude_as_warmup"
#: stay builder rules for the tests' probes only, as "kickoff" does (VISIBILITY_RULES).
SCOPE_RULES = ("LEAGUE", "LEAGUE_REGULAR")
FIRST_SEASON_RULES = ("score_under_prior", "exclude_as_warmup")
SLOT_VALUES = {
    "scope": ("LEAGUE_REGULAR",),       # Q2 RULED (263 item 2): "LEAGUE-type regular rounds only"
    "first_season": ("score_under_prior",),  # Q3 RULED (263 item 3): "scored under the weak prior, as built"
    "visibility": ("day",),                                      # Q4: results known before the fixture's UTC date
                                                                 # and its kickoff (RESULT_LAG)
    # Q4 RULED (addendum 254 item 3): the DAY rule, stated in BAR_TEXT, so the slot admits "day" alone and
    # slots_state refuses any other value before any load (Codex on #832, round 3, P1): a declaration cannot select
    # a history BAR_TEXT does not describe. "kickoff" stays a builder rule for tests only (VISIBILITY_RULES).
    "cut": "an ISO-8601 UTC instant clearing every fence",       # Q7
    "availability_on": (True, False),                            # Q6: the availability term in the shadow
    # 251 item 2: v22's RECORDED gate figure, read from where it is recorded and never recomputed. No figure of v22 on
    # the frozen pot is machine-readable in the repository (law 1, read on main 44c8fceb: docs/registry/experiments.json
    # holds soccer-s19-time-decay, soccer-dc-fit and soccer-s14-stage2 with PL-pooled deltas only, and
    # soccer-expansion-v1 with per-league figures on five leagues' 2024/25 + 2025/26; BACKLOG records the 2026-09-21
    # promotion "on 16,546 matches / 376 teams" without a log-loss), so it is a declaration slot: the architect fills it
    # at the declaration (11-20) and names the record it comes from.
    "v22_recorded_log_loss": ("a finite positive number: v22's recorded gate figure, as recorded (measured on v22's "
                              "own scored set by its own gate's scorer, not on this candidate's pot; never recomputed)"),
    "v22_recorded_source": "a non-empty string naming where v22's figure is recorded",
}
SLOT_KEYS = tuple(SLOT_VALUES)
RECOMMENDED = {"scope": "LEAGUE_REGULAR", "first_season": "score_under_prior", "visibility": "day",
               "cut": "2026-10-30T15:00:00Z", "availability_on": False}
#: The slots no recommendation can fill (v22's record is the architect's to read and name).
UNRECOMMENDED = ("v22_recorded_log_loss", "v22_recorded_source")

# --------------------------------------------------------------------------- THE AVAILABILITY TERM (243 item 4) --
# "the availability term's inputs are the entry's fixture age (this fixture / an earlier fixture, N days) and its
# type, verbatim". The six fixture-age categories and the one-decimal detail string are the receipt's
# (scripts/pl_injury_classification_receipt.py, THIS / EARLIER / LATER / NOT_STORED / NO_FIX_ID / FIX_AMBIG and
# fixture_age's f"{EARLIER} {d / 24:.1f} d before (...)"); a test pins them equal. N is carried as that detail string,
# never as an input: no threshold on N exists. No figure of the 243/244 receipt is a parameter here (a test checks).
THIS, EARLIER, LATER = "this fixture", "an earlier fixture", "a later fixture"
NOT_STORED, NO_FIX_ID, FIX_AMBIG = "fixture not stored", "no fixture id stored", "fixture id held by 2+ stored matches"
AGE_CATEGORIES = (THIS, EARLIER, LATER, NOT_STORED, NO_FIX_ID, FIX_AMBIG)
MISSING_TYPE = "Missing Fixture"
QUESTIONABLE_TYPE = "Questionable"
AVAILABILITY_TABLE = (
    (MISSING_TYPE, THIS, True, "counts: factors.injury_adjustment, unchanged (position weights, 25% cap)"),
    (MISSING_TYPE, EARLIER, False, "nothing, whatever N is (N recorded; no threshold)"),
    (MISSING_TYPE, LATER, False, "nothing"),
    (MISSING_TYPE, NOT_STORED, False, "nothing, labelled"),
    (MISSING_TYPE, NO_FIX_ID, False, "nothing, labelled"),
    (MISSING_TYPE, FIX_AMBIG, False, "nothing, labelled: an ambiguous id is refused, never guessed"),
    (QUESTIONABLE_TYPE, None, False, "nothing, any age"),
)
TYPE_NOT_RULED = "type not ruled: nothing"


class GateRefused(RuntimeError):
    """A precondition is not met: printed with its reason, exit 2; nothing written, nothing reserved, nothing
    recorded (except SpentRefused, its one subclass, raised only after the reservation)."""


class SpentRefused(GateRefused):
    """A refusal AFTER the reservation (ARCHITECT 2026-11-05 13:50 ET, addendum 264 item 2(b): "THE GATE COMMAND NOT
    CATCHING `FitRefused` (a traceback where the REFUSED line belongs) ... the same follow-up PR catches it and prints
    the REFUSED line with its reason"): the walk stopped (the fit refused, or a walk guard), the reservation STANDS and
    the one run is spent (263 item 13: "The only release is a ruling of mine on the failure's receipt"); nothing is
    recorded. Printed as the gate's REFUSED line, exit 2."""


#: the fit's refusal (src/models/joint_poisson.py), named here for the gate command, which catches it (264 item 2(b))
FitRefused = jp.FitRefused


def _iso(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")


def parse_instant(v) -> datetime | None:
    from src.walters import redated
    return redated.as_utc(v) if isinstance(v, (str, datetime)) else None


# ----------------------------------------------------------------------------------------- availability --

@dataclass(frozen=True)
class Entry:
    """One injury entry as the term reads it: its team, name, position, type (the stored string, verbatim) and its
    fixture age (one of AGE_CATEGORIES) with the receipt's detail string."""
    team_id: int
    player_name: str
    player_position: str | None
    type: str | None
    age: str
    age_text: str


def fixture_age(fid, own_match_id, own_fixture_id, own_utc, by_fid: dict, by_prev: dict | None = None
                ) -> tuple[str, str]:
    """The receipt's fixture_age (scripts/pl_injury_classification_receipt.py), on plain inputs: the entry's fixture
    id against this fixture. by_fid / by_prev: provider id -> [(match_id, kickoff, competition code)], by the
    current and the previous provider id. (category, detail)."""
    if not fid:
        return NO_FIX_ID, NO_FIX_ID
    hits, prev = (by_fid or {}).get(str(fid), []), ""
    if not hits and (by_prev or {}).get(str(fid)):
        hits, prev = by_prev[str(fid)], " (a previous provider id of the match)"
    if not hits:
        return NOT_STORED, f"{NOT_STORED} (provider fixture {fid})"
    if len(hits) > 1:
        return FIX_AMBIG, f"{FIX_AMBIG} ({', '.join(str(h[0]) for h in hits)})"
    mid, utc, code = hits[0]
    if mid == own_match_id or str(fid) == str(own_fixture_id):
        return THIS, THIS + prev
    here, there = parse_instant(own_utc), parse_instant(utc)
    if here is None or there is None:
        return NOT_STORED, f"fixture {fid}: match {mid} has no readable kickoff"
    d = (here - there).total_seconds() / 3600
    if d >= 0:
        return EARLIER, f"{EARLIER} {d / 24:.1f} d before ({code or 'competition ?'}, match {mid}){prev}"
    return LATER, f"{LATER} {-d / 24:.1f} d after ({code or 'competition ?'}, match {mid}){prev}"


def classify(entry_type, age: str) -> tuple[bool, str]:
    """243 item 4: what the term does with one entry, from its type and fixture age alone (AVAILABILITY_TABLE)."""
    for t, a, counts, what in AVAILABILITY_TABLE:
        if entry_type == t and (a is None or a == age):
            return counts, what
    return False, TYPE_NOT_RULED


def availability(entries, home_id: int, away_id: int, on: bool) -> tuple[float, float, list[str]]:
    """(home multiplier, away multiplier, notes). Off, or no entry: (1.0, 1.0) exactly. On: the counted entries
    (classify) go to factors.injury_adjustment, unchanged."""
    if not on or not entries:
        return 1.0, 1.0, (["availability: off"] if not on else ["availability: no entry"])
    from src.models.factors import injury_adjustment
    hc = [e for e in entries if e.team_id == home_id and classify(e.type, e.age)[0]]
    ac = [e for e in entries if e.team_id == away_id and classify(e.type, e.age)[0]]
    if not hc and not ac:
        return 1.0, 1.0, ["availability: no counted entry"]
    f = injury_adjustment(home_injuries=hc, away_injuries=ac)
    return f.home_xg_multiplier, f.away_xg_multiplier, list(f.notes)


# ---------------------------------------------------- THE AVAILABILITY RECORD (addendum 252; 253 item 2(d), row 4) --
# "the as-of factor inputs come only from stored as-of data (the availability record of addendum 252 is the source
# going forward; where the record has nothing for an era, the term is off in BOTH paths for that era and the harness
# says so)" (253 item 2(d)). The record is src/availability/record.py (#831, its tables created by init_db and
# migrate_availability_record.py, never here); soccer-v23 reads it through record.as_of, the one read path
# (ARCHITECT 2026-11-05 12:50 ET, addendum 263 item 23; 252 item 2: "there is no second path"). No soccer source is in
# the record's vocabulary (record.SOURCES), so on every store today a read finds no soccer fact and the term is off in
# both paths, labelled.

#: 252 item 1: the record's two tables, the record module's own names (record.TABLES; never a second spelling).
RECORD_TABLES = avr.TABLES
#: 252 item 1, THE TWO CLOCKS: "A live-era record, a forward confirmation and a closing-time input use `recorded_at`
#: only". A source-stamped read is a labelled backtest that its bar must declare; soccer-v23's bar declares none.
RECORDED_CLOCK = "recorded"
RECORD, NO_RECORD = "record", "no record"
#: Of 252 item 1(b)'s kinds, the one carrying an injury entry's type (its attrs' status text, verbatim), the only input
#: kind of 243 item 4's term; lineup and depth kinds are no input of soccer-v23 (it has no lineup or XI term).
TERM_KIND = "injury_status"
#: 252 item 1, THE TWO CLOCKS: "A backfilled row (recorded_at later than source_stamp by more than the feed's cadence
#: ...) is usable ONLY in a backtest labelled "source-stamped" in its run record and its gate text, never in the
#: live-era record". soccer-v23's bar declares no source-stamped backtest, so the one builder EXCLUDES a backfilled fact
#: from every snapshot (both paths; kept in `AvailabilityAsOf.excluded`, counted in the notes and the per-era line,
#: never read by the term). (Open question 27, RULED AS BUILT by addendum 254 item 3 Q27 (b): exclusion with count and
#: label, not refusal; a soccer source's cadence is declared by the architect with its feed.) A fact carrying a
#: source_stamp from a source with no declared cadence cannot be told from a backfill and is excluded too (law 4: never
#: guessed); a fact with no source_stamp (the source gives none, 252 item 1(b)) is read by the recorded clock alone.
#:
#: ONE CADENCE CONSTANT (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 2): "`record.SOURCE_CADENCE_HOURS` is the
#: single source of truth; soccer-v23 (#832) deletes its own empty copy and READS the record's constant FILTERED TO
#: SOCCER SOURCES at its declaration; its fingerprinted gate text names those soccer entries explicitly (today: "no
#: soccer source declared; every fact carrying a source_stamp is excluded, counted" — 254 item 3 Q27(b)) and the
#: fingerprint hashes that filtered view, so an entry for another sport (nflverse at 24, the NHL landing feed later)
#: never moves v23's fingerprint." The filter is SOCCER_SOURCES: the record's source words that carry soccer facts, a
#: declared tuple, empty today (263 item 25: "The soccer source and its attrs key are named by the soccer feed's adapter
#: PR when one is declared (none today)"); every name in it is one of record.SOURCES (a test holds it).
SOCCER_SOURCES: tuple[str, ...] = ()
#: BAR_TEXT's words for the filtered view while it is empty (262 item 2, quoting 254 item 3 Q27(b)); a test holds
#: BAR_TEXT to name every entry of source_cadence_hours() or, while there is none, this sentence.
NO_SOCCER_CADENCE = "no soccer source declared; every fact carrying a source_stamp is excluded, counted"


def source_cadence_hours() -> dict:
    """262 item 2: record.SOURCE_CADENCE_HOURS (the single source of truth) FILTERED TO SOCCER SOURCES, read at call
    time; the view the backfill rule reads, code_constants freezes and the stream fingerprint hashes. Another sport's
    entry is never in it."""
    return {src: avr.SOURCE_CADENCE_HOURS[src] for src in sorted(avr.SOURCE_CADENCE_HOURS) if src in SOCCER_SOURCES}


@dataclass(frozen=True)
class Fact:
    """One assertion of the availability record, as a snapshot carries it: the fields of 252 item 1(b) the term reads
    (observation_id, source, kind, team_id (ours; None when unmapped, law 4), match_id, the stored kickoff of that
    match, the player's name as the source gave it, the attrs' status text and position, verbatim) and BOTH clocks
    (source_stamp, the source's claim; recorded_at, ours). The snapshot admits a fact only by recorded_at."""
    observation_id: int
    source: str
    kind: str
    team_id: int | None
    match_id: int | None
    match_kickoff: datetime | None
    player_name: str
    status: str | None
    position: str | None
    source_stamp: datetime | None
    recorded_at: datetime

    def key(self) -> tuple:
        return (self.recorded_at, self.observation_id, self.source, self.kind, str(self.team_id),
                str(self.match_id), self.player_name, str(self.status), str(self.position))

    def canon(self) -> list:
        return [self.observation_id, self.source, self.kind, self.team_id, self.match_id,
                _ts(self.match_kickoff) if self.match_kickoff else None, self.player_name, self.status, self.position,
                _ts(self.source_stamp) if self.source_stamp else None, _ts(self.recorded_at)]


@dataclass(frozen=True)
class AvailabilityAsOf:
    """What the record held at one instant under the RECORDED clock: RECORD (the facts of the newest observation per
    source recorded at or before the instant: 252 item 1's "as of T" query) or NO_RECORD (nothing; the term is off),
    with the reason. `excluded`: the backfilled facts the builder took out of `facts` (backfill_reason; never read by
    the term, kept so the exclusion is counted and audited); a record never fills it itself."""
    state: str
    reason: str
    clock: str = RECORDED_CLOCK
    facts: tuple = ()
    excluded: tuple = ()


class AvailabilityRecord:
    """THE INTERFACE the one snapshot builder calls (both paths): at(instant) -> AvailabilityAsOf under the recorded
    clock. The store's reader is 252 item 2's query function, record.as_of (StoreRecord; there is no second query path:
    "The same function is the one a model term ... will read"); `availability_record` is the adapter that picks it."""

    def at(self, as_of: datetime) -> AvailabilityAsOf:                  # pragma: no cover - the interface
        raise NotImplementedError


class NoRecord(AvailabilityRecord):
    """The record has nothing at any instant: every read is NO_RECORD with its reason (the term off in both paths)."""

    def __init__(self, reason: str):
        self.reason = reason

    def at(self, as_of: datetime) -> AvailabilityAsOf:
        return AvailabilityAsOf(NO_RECORD, self.reason)


#: A replay given rows and no store (tests, the uncached builders called bare): no record, said so.
ROWS_ONLY = NoRecord("no availability record supplied (a replay of rows alone): the term is off")
ABSENT_REASON = ("the availability record's tables (availability_observations, availability_assertions) are absent on "
                 "this store (a store built before #831's schema): no record; the term is off")
#: What a read of a present record answers where it holds no soccer fact in force at the instant (253 item 2(d): the
#: term off in both paths, and the harness says so).
NO_SOCCER_FACT_REASON = ("the availability record (record.as_of, the one read path, under the recorded clock, kind "
                         "injury_status) holds no soccer injury_status fact in force at the decision instant (the other "
                         "kinds are no input of v23; no soccer source is declared, addendum 263 item 25); the term is "
                         "off")


class StoreRecord(AvailabilityRecord):
    """THE RECORD'S READER (ARCHITECT 2026-11-05 12:50 ET, addendum 263 item 23: "the follow-up that calls 252 item 2's
    query function (record.as_of, the one path)"): at(instant) is record.as_of(session, soccer, instant, the recorded
    clock, kind=TERM_KIND), on the caller's open session: 263 item 25, "`injury_status` is one entry ..., the other
    kinds no input of v23", so a fact of another kind is never read here and neither refuses nor turns the term on. No
    soccer injury_status fact in force: NO_RECORD (NO_SOCCER_FACT_REASON; the term off). Any in force: REFUSED, never
    guessed: the term's entry needs the soccer source's attrs key for its status and position, and 263 item 25 leaves
    that key to the soccer feed's adapter PR ("none today ... I rule the mapping with it"), so a fact this reader cannot
    map is a record that exists and cannot be read: "a stop, not an absence" (263 item 23). A refusal of the record's
    own read is refused here with its reason."""

    def __init__(self, session):
        self.session = session

    def at(self, as_of: datetime) -> AvailabilityAsOf:
        from src.db.schema import Sport
        try:
            facts = avr.as_of(self.session, Sport.SOCCER, as_of, clock=RECORDED_CLOCK, kind=TERM_KIND)
        except avr.Refused as err:
            raise GateRefused(f"the availability record refused the read at {_ts(as_of)}: {err}; nothing read") from err
        if not facts:
            return AvailabilityAsOf(NO_RECORD, NO_SOCCER_FACT_REASON)
        by: dict[tuple[str, str], int] = {}
        for f in facts:
            k = (f.interval.first.source, f.interval.first.kind)
            by[k] = by.get(k, 0) + 1
        raise GateRefused(f"the availability record holds {len(facts)} soccer {TERM_KIND} fact(s) in force at "
                          f"{_ts(as_of)} ("
                          + ", ".join(f"{src} {kind} {n}" for (src, kind), n in sorted(by.items()))
                          + "): they cannot be mapped to soccer-v23's term (its status and position need the soccer "
                          "source's attrs key, which addendum 263 item 25 leaves to the soccer feed's adapter PR; none "
                          "is declared): never guessed; nothing read")


class ReadRecord(AvailabilityRecord):
    """The copy's record READ ONCE, at every decision instant the run can need, while the copy is open (_load; the
    copy's session closes before the fingerprint and the walk): each answer is StoreRecord's, through record.as_of.
    An instant it did not read is refused, never guessed and never read from a closed copy."""

    def __init__(self, reads: dict):
        self.reads = dict(reads)

    def at(self, as_of: datetime) -> AvailabilityAsOf:
        got = self.reads.get(as_of)
        if got is None:
            raise GateRefused(f"the availability record at {_ts(as_of)} was not read while the copy was open (the run "
                              "reads it at every decision instant of its rows, in _load): never guessed")
        return got


def read_at(record: AvailabilityRecord, instants) -> AvailabilityRecord:
    """The record answered at each of `instants` now (inside the copy's session): a NoRecord stays itself (it reads
    nothing); any other reader becomes a ReadRecord of its answers."""
    if isinstance(record, NoRecord):
        return record
    return ReadRecord({d: record.at(d) for d in sorted(set(instants))})


def availability_record(session) -> AvailabilityRecord:
    """THE ADAPTER. Both tables absent: NoRecord (the term off in both paths, labelled). One present without the other:
    refused (a half-migrated store is never guessed at). Both present but not migrated (record.migrated: the tables
    and the marker migrate_availability_record.py alone writes): refused, as the record's own reader (cli availability)
    refuses it. Migrated: StoreRecord, record.as_of on this session (addendum 263 item 23; its columns are the record
    module's, never guessed)."""
    from sqlalchemy import inspect
    insp = inspect(session.get_bind())
    present = [t for t in RECORD_TABLES if insp.has_table(t)]
    if not present:
        return NoRecord(ABSENT_REASON)
    if len(present) != len(RECORD_TABLES):
        raise GateRefused(f"the availability record is half present on this store ({present} of {list(RECORD_TABLES)}):"
                          " never guessed at; nothing read")
    if not avr.migrated(session):
        raise GateRefused("the availability record's tables are present on this store but migrate_availability_record.py"
                          " has not run on it (the tables without their marker): the record's own reader refuses such "
                          "a store, and so does soccer-v23's; nothing read")
    return StoreRecord(session)


def backfill_reason(f: Fact) -> str | None:
    """252 item 1's backfill rule on one fact (None: not a backfill, the term may read it). A fact with no source_stamp
    makes no claim to compare and is read by the recorded clock alone; one whose source has no declared soccer cadence
    (source_cadence_hours: the record's constant filtered to soccer sources) cannot be told from a backfill; one recorded later than its source_stamp by more than the
    declared cadence IS a backfill. Both are excluded from the snapshot's facts by the one builder."""
    if f.source_stamp is None:
        return None
    cadence = source_cadence_hours().get(f.source)
    if cadence is None:
        return (f"source {f.source!r} stamps its facts and declares no soccer cadence (record.SOURCE_CADENCE_HOURS "
                "filtered to SOCCER_SOURCES, addendum 262 item 2): a backfill cannot be ruled out")
    if f.recorded_at - f.source_stamp > timedelta(hours=cadence):
        return (f"recorded {f.recorded_at - f.source_stamp} after its source_stamp, beyond {f.source!r}'s declared "
                f"cadence of {cadence} h")
    return None


def read_availability(record: AvailabilityRecord, decision: datetime) -> AvailabilityAsOf:
    """The builder's one read of the record, at the snapshot's DECISION INSTANT (Snapshot.decision: visibility_bound
    of the fixture's kickoff, the rows' own bound, never the kickoff itself), checked: the recorded clock only (252
    item 1's two clocks: a source-stamped read is refused); NO_RECORD carries no fact; every fact recorded at or before
    the decision instant (252's "as of T": the clock <= T; a later one refuses: never silently dropped); every
    backfilled fact (backfill_reason) moved to `excluded`, never read by the term; facts in canonical order."""
    got = record.at(decision)
    if not isinstance(got, AvailabilityAsOf):
        raise GateRefused(f"the availability record answered {type(got).__name__}, not an AvailabilityAsOf")
    if got.clock != RECORDED_CLOCK:
        raise GateRefused(f"the availability record was read under the {got.clock!r} clock: a live-era input reads "
                          f"{RECORDED_CLOCK!r} only (addendum 252 item 1); soccer-v23's bar declares no source-stamped "
                          "backtest")
    if got.excluded:
        raise GateRefused("the availability record answered with excluded facts: only the builder excludes")
    if got.state == NO_RECORD:
        if got.facts:
            raise GateRefused("the availability record said 'no record' and carried facts")
        return got
    if got.state != RECORD:
        raise GateRefused(f"the availability record's state {got.state!r} is not {RECORD!r} or {NO_RECORD!r}")
    late = [f for f in got.facts if not isinstance(f, Fact) or f.recorded_at > decision]
    if late:
        raise GateRefused(f"the availability record returned {len(late)} fact(s) recorded after the decision instant "
                          f"{_ts(decision)} (or not a Fact): the recorded clock admits only what was on our disk at or "
                          "before it")
    facts = sorted(got.facts, key=Fact.key)
    return replace(got, facts=tuple(f for f in facts if backfill_reason(f) is None),
                   excluded=tuple(f for f in facts if backfill_reason(f) is not None))


def term_state(on: bool, av: AvailabilityAsOf) -> str:
    """The term's state at one instant: on only when the slot is on AND the record holds something there."""
    if not on:
        return "off: the slot availability_on is false"
    return "on" if av.state == RECORD else "off: no record at the instant"


def term_entries(av: AvailabilityAsOf, fixture) -> tuple[tuple, list[str]]:
    """The term's inputs for one fixture, from the snapshot's facts alone (243 item 4: the entry's type and fixture
    age, verbatim): each injury_status fact of the fixture's clubs as an Entry, its fixture age by the receipt's own
    fixture_age (the fact's match against this fixture, by our match id). A fact of an unmapped team is kept in the
    notes and counted for nothing (law 4: never guessed); a fact of another kind is no input (counted in the notes)."""
    out, notes, other = [], [], 0
    for f in av.facts:
        if f.kind != TERM_KIND:
            other += 1
            continue
        if f.team_id is None:
            notes.append(f"availability: unmapped team for {f.player_name!r} (kept, never guessed; not counted)")
            continue
        if f.team_id not in (fixture.home_id, fixture.away_id):
            continue
        fid = str(f.match_id) if f.match_id is not None else None
        age, text = fixture_age(fid, fixture.id, None, fixture.utc_date,
                                {fid: [(f.match_id, f.match_kickoff, None)]} if fid else {})
        out.append(Entry(f.team_id, f.player_name, f.position, f.status, age, text))
    if other:
        notes.append(f"availability: {other} fact(s) of other kinds (no input of this term)")
    return tuple(out), notes


def availability_lines(items) -> list[str]:
    """253 item 2(d): "where the record has nothing for an era, the term is off in BOTH paths for that era and the
    harness says so". One line per era (competition-season): how many fixtures had the term on, and how many had it
    off and why (the record's own reason at the instant)."""
    eras: dict[tuple[str, str], dict] = {}
    dropped: dict[tuple[str, str], int] = {}
    for a in items:
        e = eras.setdefault((a["code"], a["season"]), {})
        k = (a["term"], a["reason"])
        e[k] = e.get(k, 0) + 1
        dropped[(a["code"], a["season"])] = dropped.get((a["code"], a["season"]), 0) + int(a.get("excluded", 0))
    L = ["  AVAILABILITY (253 item 2(d); addendum 252's record read under the recorded clock at each fixture's "
         "decision instant, both paths alike):"]
    for (c, s), e in sorted(eras.items()):
        L.append(f"    {c} {s}: " + " · ".join(f"{n} fixture(s) term {term} ({reason})"
                                              for (term, reason), n in sorted(e.items()))
                 + (f" · {dropped[(c, s)]} backfilled fact(s) excluded (252 item 1: never a live-era input)"
                    if dropped[(c, s)] else ""))
    return L


# ------------------------------------------------------------------------------------- rows and snapshots --

@dataclass(frozen=True)
class Row:
    """One admitted finished row (see ADMISSION): the goals are the 90-minute ones where the predicate substitutes."""
    id: int
    code: str
    season: str
    utc_date: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int
    stage: str | None = None
    status_raw: str | None = None

    def key(self) -> tuple:
        return (self.utc_date, self.id)

    def canon(self) -> list:
        return [self.id, self.code, self.season, _ts(self.utc_date), self.home_id, self.away_id, self.home_goals,
                self.away_goals, self.stage, self.status_raw]


ROW_FIELDS = ("id", "code", "season", "utc_date", "home_id", "away_id", "home_goals", "away_goals", "stage",
              "status_raw")


@dataclass(frozen=True)
class Fixture:
    id: int
    code: str
    season: str
    utc_date: datetime
    home_id: int
    away_id: int

    @classmethod
    def of(cls, r: Row) -> "Fixture":
        return cls(r.id, r.code, r.season, r.utc_date, r.home_id, r.away_id)


def _chain(prev: str, row: Row) -> str:
    blob = json.dumps(row.canon(), separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256((prev + "|" + blob).encode("ascii")).hexdigest()


CHAIN_ROOT = hashlib.sha256(SNAPSHOT_VERSION.encode("ascii")).hexdigest()


def prefix_digest(rows) -> str:
    h = CHAIN_ROOT
    for r in rows:
        h = _chain(h, r)
    return h


@dataclass(frozen=True)
class Snapshot:
    """The versioned, immutable input of one prediction at one INSTANT (never of one fixture: fixtures sharing a
    kickoff share it, row 5). The fields carrying 253 item 2(d)'s five rows:
      rows          (1) the context and (3) the early-season history: the admitted rows visible at `as_of` (a tuple in
                    kickoff order, ties by id), with `prefix`, their chained digest;
      elo_pre       (2) each visible row's pre-kickoff (home, away) ladder ratings;
      elo_state     (2) ((team id, rating, last season key), ...) by team id: the ladder after every visible row;
      availability  (4) the availability record at the DECISION INSTANT (`decision`) under the recorded clock
                    (AvailabilityAsOf; backfilled facts excluded);
      as_of, visibility  (5) the instant and the rule whose visibility_bound excludes every row at or after it.
    `decision` (derived: visibility_bound(as_of, visibility)) is the one cut-off of rows and facts alike. params_json:
    canonical JSON (v22's stored poisson config, the availability switch). All filled by the one builder
    (snapshot_from_rows; the walk and live both call it)."""
    version: str
    as_of: datetime
    visibility: str
    rows: tuple
    prefix: str
    params_json: str
    elo_pre: tuple
    elo_state: tuple
    availability: AvailabilityAsOf

    def params(self) -> dict:
        return json.loads(self.params_json)

    @property
    def decision(self) -> datetime:
        """THE DECISION INSTANT: the one cut-off of the snapshot's rows (kickoff before it) and of its availability
        facts (recorded at or before it), visibility_bound(as_of, visibility). A live call made at or after it holds
        everything the snapshot holds; a replay on a later copy reads nothing recorded after it."""
        return visibility_bound(self.as_of, self.visibility)

    @property
    def sha(self) -> str:
        body = {"version": self.version, "as_of": _ts(self.as_of), "visibility": self.visibility,
                "n": len(self.rows), "prefix": self.prefix, "params": json.loads(self.params_json),
                "elo_pre": [list(p) for p in self.elo_pre], "elo_state": [list(e) for e in self.elo_state],
                "availability": {"state": self.availability.state, "reason": self.availability.reason,
                                 "clock": self.availability.clock,
                                 "facts": [f.canon() for f in self.availability.facts],
                                 "excluded": [f.canon() for f in self.availability.excluded]}}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                                         allow_nan=False).encode("ascii")).hexdigest()


def canon_params(v22_poisson: dict, availability_on: bool, scope: str, thin_excluded=()) -> str:
    """The snapshot's params: v22's stored poisson config, the availability switch, the declared stage SCOPE (the one
    builder reads it: in_scope) and THE THIN SEASONS EXCLUDED BY CAUSE (ARCHITECT 2026-11-05 12:50 ET, addendum 263
    item 14: the run's frozen exclusion set, thin_season_keys of the walked history, named by the preflight before the
    reservation; soccer-v23's window reads it, both paths alike). `scope` is required, never defaulted; the thin set is
    empty unless the caller names it (a replay of rows alone, the tests)."""
    if scope not in SCOPE_RULES:
        raise ValueError(f"scope {scope!r} is not one of {SCOPE_RULES}")
    thin = sorted([str(c), str(se)] for c, se in thin_excluded)
    return json.dumps({"v22_poisson": dict(v22_poisson), "availability_on": bool(availability_on), "scope": scope,
                       "thin_excluded": thin}, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def in_scope(rows, scope: str) -> list:
    """THE STAGE SCOPE OF THE HISTORY (Codex on #832, round 1; soccer_expansion F3, ruled: "only regular-season rounds
    are scored and walked"): under LEAGUE every row; under LEAGUE_REGULAR only the rows soccer_expansion.placement
    reads "regular": a play-off row is left out of the HISTORY as well as the scored set, so it touches neither arm's
    walk (no Elo step, no context, no v22 strength or backfill, no v23 window), and a label the code cannot place
    REFUSES (never guessed). The one builder applies it (both arms, the replay and live alike) and the walk applies it
    to its own rows first, so the memo's rows are the builder's."""
    if scope == "LEAGUE":
        return list(rows)
    if scope != "LEAGUE_REGULAR":
        raise ValueError(f"scope {scope!r} is not one of {SCOPE_RULES}")
    from src.walters.soccer_expansion import placement
    out, bad = [], {}
    for r in rows:
        pl = placement(r.stage)
        if pl == "regular":
            out.append(r)
        elif pl != "playoff":
            bad[(r.code, r.season)] = bad.get((r.code, r.season), 0) + 1
    if bad:
        raise GateRefused("a row's stage label cannot be placed under scope LEAGUE_REGULAR (soccer_expansion F3: never "
                          "guessed): " + "; ".join(f"{c} {se}: {n}" for (c, se), n in sorted(bad.items())))
    return out


def visible(r: Row, as_of: datetime, rule: str) -> bool:
    """S-VIS (open question 4, RULED by addendum 254 item 3 Q4: the DAY rule, the slot's only value): a row is
    visible at `as_of` only if its result is known before it (kickoff + RESULT_LAG < as_of) and, under "day", it
    kicked off on a UTC date strictly before the fixture's (the morning chain's reading; batches every same-day
    fixture kicking off at least RESULT_LAG after midnight); "kickoff" (VISIBILITY_RULES, never declarable) = the
    result-known bound alone, for the tests' invariance probes. The one bound is visibility_bound's."""
    return r.utc_date < visibility_bound(as_of, rule)


def visibility_bound(as_of: datetime, rule: str) -> datetime:
    """The exclusive upper bound on a visible row's kickoff (utc_date < bound), the one bound of both builders, the
    cache and predict's check: as_of − RESULT_LAG (the result known before the instant), and under "day" also the
    fixture's UTC midnight. A row still in play at the instant, or finished less than RESULT_LAG after its kickoff,
    is never visible."""
    known = as_of - RESULT_LAG
    if rule == "day":
        return min(datetime(as_of.year, as_of.month, as_of.day), known)
    if rule == "kickoff":
        return known
    raise ValueError(f"visibility {rule!r} is not one of {VISIBILITY_RULES}")


def admit(m, code: str, ctype: str | None) -> Row | None:
    """THE ONE admission predicate (both builders; see ADMISSION)."""
    from src.walters.soccer_expansion import unscoreable
    if (ctype or "LEAGUE").upper() in ("CUP", "INTL"):
        return None
    status = m.status.value if hasattr(m.status, "value") else str(m.status)
    if status != "finished" or m.utc_date is None or m.home_score is None or m.away_score is None:
        return None
    if unscoreable(m, status):
        return None
    raw = (m.status_raw or "").strip().upper()
    hg, ag = m.home_score, m.away_score
    if raw not in ("", "FT") and m.home_score_90 is not None and m.away_score_90 is not None:
        hg, ag = m.home_score_90, m.away_score_90
    return Row(int(m.id), code, str(m.season), m.utc_date, int(m.home_team_id), int(m.away_team_id), int(hg),
               int(ag), m.stage, m.status_raw)


def _select(session, upper: datetime | None, through: datetime | None):
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, Sport
    q = (select(Match, Competition.code, Competition.type).join(Competition, Match.competition_id == Competition.id)
         .where(Match.sport == Sport.SOCCER, Match.status == MatchStatus.FINISHED, Match.utc_date.is_not(None),
                Match.home_score.is_not(None), Match.away_score.is_not(None)))
    if upper is not None:
        q = q.where(Match.utc_date < upper)
    if through is not None:
        q = q.where(Match.utc_date <= through)
    out = []
    for m, code, ctype in session.execute(q).all():
        r = admit(m, code, ctype)
        if r is not None:
            out.append(r)
    out.sort(key=Row.key)
    return out


def load_rows(session, through: datetime | None = None) -> list[Row]:
    """Every admitted row of the store (select only), kicking off at or before `through` when given (the cut)."""
    return _select(session, None, through)


def _elo_state(ratings: dict, last: dict) -> tuple:
    return tuple((t, ratings[t], last[t]) for t in sorted(ratings))


def snapshot_from_rows(rows, as_of: datetime, params_json: str, visibility_rule: str,
                       record: AvailabilityRecord = ROWS_ONLY) -> Snapshot:
    """THE ONE BUILDER (253 item 2(d); replay and live alike, each calling it at every instant): the admitted rows
    visible at `as_of` (rows 1, 3, 5), the ladder walked over them by walk_ladder (row 2) and the availability record
    read under the recorded clock at the DECISION INSTANT, the rows' own bound b = visibility_bound(as_of) (row 4):
    rows kicking off before b, facts recorded at or before b; the rows in the params' declared stage scope only
    (in_scope: under LEAGUE_REGULAR a play-off row never enters the history). A function of the instant, never of a
    fixture. Cost: one pass of the ladder and the digest over the visible rows per call (about 0.15 s at the pot's
    size on a synthetic 16,546-row probe)."""
    b = visibility_bound(as_of, visibility_rule)
    vis = tuple(sorted(in_scope((r for r in rows if r.utc_date < b), json.loads(params_json)["scope"]), key=Row.key))
    pre, state, last = walk_ladder(vis)
    return Snapshot(SNAPSHOT_VERSION, as_of, visibility_rule, vis, prefix_digest(vis), params_json, tuple(pre),
                    _elo_state(state.ratings, last), read_availability(record, b))


def snapshot_from_session(session, as_of: datetime, params_json: str, visibility_rule: str,
                          record: AvailabilityRecord | None = None) -> Snapshot:
    """Live's way into the one builder: one SELECT bounded at the visibility instant (select only) through the same
    admission predicate, and the store's own availability record (availability_record, unless one is given), then
    snapshot_from_rows."""
    rows = _select(session, visibility_bound(as_of, visibility_rule), None)
    return snapshot_from_rows(rows, as_of, params_json, visibility_rule,
                              availability_record(session) if record is None else record)


# ----------------------------------------------------------------------------------------------- the ladder --

def _key(r) -> str:
    return f"{r.code}:{r.season}"


def walk_ladder(rows):
    """Production's LEAGUE ladder over `rows` (kickoff order), through elo's own functions, exactly as elo.train steps
    it: THE one Elo function of both paths (253 item 2(d) row 2; called only by the one builder). Returns
    (pre: [(home rating, away rating) used by each row's update], the final EloState, last key by team)."""
    from src.models.elo import EloConfig, EloState, regress_team, update_after_match
    state = EloState(config=EloConfig())
    last: dict[int, str] = {}
    pre = []
    for r in rows:
        k = _key(r)
        for tid in (r.home_id, r.away_id):
            p = last.get(tid)
            if p is not None and p != k:
                regress_team(state, tid)
            last[tid] = k
        hr, ar = state.get(r.home_id), state.get(r.away_id)
        pre.append((hr, ar))
        nh, na = update_after_match(hr, ar, r.home_goals, r.away_goals, state.config)
        state.set(r.home_id, nh)
        state.set(r.away_id, na)
    return pre, state, last


class _RowsList:
    """season_rows over a plain row list (off_pyramid_arrivals' census and tests; no ladder walked)."""

    def __init__(self, rows):
        self.rows = rows

    def season_rows(self, season: str):
        return [r for r in self.rows if r.season == season]


class _SnapView:
    """What predict reads of a snapshot: its rows with their elo_pre, and elo_state, nothing else, indexed by ONE pass
    over the snapshot's OWN rows (never another structure's index). `digest`, set only for a memoised view, is the
    snapshot's own prefix digest (the builder's output), the key of the fits memo."""

    def __init__(self, snap: Snapshot, memoised: bool = False):
        self.snap = snap
        self.digest = snap.prefix if memoised else None
        self._teams: dict | None = None
        self._by: tuple[dict, dict] | None = None
        self._comp: dict[str, list] = {}

    def _index(self) -> tuple[dict, dict]:
        if self._by is None:
            code: dict[str, list[int]] = {}
            season: dict[str, list[int]] = {}
            for i, r in enumerate(self.snap.rows):
                code.setdefault(r.code, []).append(i)
                season.setdefault(r.season, []).append(i)
            self._by = (code, season)
        return self._by

    def comp(self, code: str):
        got = self._comp.get(code)
        if got is None:
            got = self._comp[code] = [(self.snap.rows[i], self.snap.elo_pre[i]) for i in self._index()[0].get(code, [])]
        return got

    def season_rows(self, season: str):
        return [self.snap.rows[i] for i in self._index()[1].get(season, [])]

    def team(self, tid: int) -> tuple[float | None, str | None]:
        if self._teams is None:
            self._teams = {t: (rating, k) for t, rating, k in self.snap.elo_state}
        return self._teams.get(tid, (None, None))


class Prefix:
    """THE WALK'S MEMO, never a second builder (253 item 2(d): identical BY CONSTRUCTION; the review of the five rows
    found the earlier cache assembling snapshots itself). `snapshot` IS snapshot_from_rows over the walk's rows, and
    `walk` calls snapshot_from_rows itself at every instant, the same function live reaches through
    snapshot_from_session. What the memo keeps: predict's fits, keyed by the builder's own output (the snapshot's
    prefix digest with the competition and season: a fit reads only the snapshot's rows and elo_pre, both functions of
    those rows in the one builder), and the view of the last snapshot it was handed (one pass over that snapshot's own
    rows). `view` refuses a snapshot whose rows are not a prefix of the walk's (its digest checked)."""

    def __init__(self, rows):
        self.rows = tuple(sorted(rows, key=Row.key))
        self.digests = [CHAIN_ROOT]
        for r in self.rows:
            self.digests.append(_chain(self.digests[-1], r))
        self.memo: dict = {}
        self._last: _SnapView | None = None

    def snapshot(self, as_of: datetime, params_json: str, rule: str,
                 record: AvailabilityRecord = ROWS_ONLY) -> Snapshot:
        """The one builder over the walk's rows (no second assembly)."""
        return snapshot_from_rows(self.rows, as_of, params_json, rule, record)

    def view(self, snap: Snapshot) -> _SnapView:
        if self._last is not None and self._last.snap is snap:
            return self._last
        k = len(snap.rows)
        if k > len(self.rows) or self.digests[k] != snap.prefix:
            raise ValueError("the cache was not built over the rows this snapshot is a prefix of")
        self._last = _SnapView(snap, memoised=True)
        return self._last


# ------------------------------------------------------------------------------------------------ predict --

def _season_order(crows, fixture: Fixture) -> str | None:
    """S−1: the competition's season before S, ordering its visible seasons by their earliest stored kickoff (S's own
    earliest is min(its visible rows, the fixture's kickoff)). None when no earlier season is visible."""
    first: dict[str, datetime] = {}
    for r, _ in crows:
        if r.season not in first or r.utc_date < first[r.season]:
            first[r.season] = r.utc_date
    s0 = min(first.get(fixture.season, fixture.utc_date), fixture.utc_date)
    earlier = [(d, s) for s, d in first.items() if s != fixture.season and d < s0]
    return max(earlier)[1] if earlier else None


def window_rows(crows, fixture: Fixture, thin=frozenset()) -> tuple[list[tuple], str | None, list[str]]:
    """The fixture's window (seasons S−1 and S as visible): its rows as (row, ratings, slot), S−1, and the seasons it
    reads. The one predicate: window_obs fits these rows and soccer-v23's context block reports them (Codex, #856
    round 1). A competition-season in `thin` (263 item 14: excluded by cause, the run's frozen set) gives the window
    no row: an excluded S−1 leaves the window without one (a first season: the weak prior), an excluded S without its
    own rows. S−1 is still the season the ordering names (an excluded season is never skipped over to an older one)."""
    sp = _season_order(crows, fixture)
    if sp is not None and (fixture.code, sp) in thin:
        sp = None
    out = []
    for r, e in crows:
        if (r.code, r.season) in thin:
            continue
        if r.season == fixture.season:
            slot = jp.CUR
        elif sp is not None and r.season == sp:
            slot = jp.PREV
        else:
            continue
        out.append((r, e, slot))
    seasons = sorted(se for se in {fixture.season, sp} if se is not None and (fixture.code, se) not in thin)
    return out, sp, seasons


def _obs(wrows) -> list[jp.Obs]:
    return [jp.Obs(r.home_id, r.away_id, slot, float(r.home_goals), float(r.away_goals), eh - ea)
            for r, (eh, ea), slot in wrows]


def window_obs(crows, fixture: Fixture, thin=frozenset()) -> tuple[list[jp.Obs], str | None]:
    """The fixture's window (window_rows) as the fit's observations, and S−1."""
    wrows, sp, _ = window_rows(crows, fixture, thin)
    return _obs(wrows), sp


def _direction(to_code: str, from_code: str) -> str | None:
    """'relegated' (from a higher tier of the same declared pyramid), 'promoted' (from a lower one), None (not on one
    pyramid together: off the declared pyramid)."""
    for pyr in PYRAMIDS:
        if to_code in pyr and from_code in pyr and to_code != from_code:
            return "relegated" if pyr.index(from_code) < pyr.index(to_code) else "promoted"
    return None


OFF_PYRAMID = "off-pyramid"


def arrival_class(code: str, team: int, prev_season_rows) -> tuple[str, list[str]]:
    """How `team`, absent from `code`'s S−1 rows, arrives: from the rows of S−1's season label in OTHER competitions
    (`prev_season_rows`). ('promoted' | 'relegated' | OFF_PYRAMID, the other codes). No such row: promoted (from
    outside the store)."""
    return _classify(code, sorted({r.code for r in prev_season_rows if r.code != code and team in (r.home_id,
                                                                                         r.away_id)}))


def _classify(code: str, codes: list[str]) -> tuple[str, list[str]]:
    """ARCHITECT 2026-11-05 12:50 ET, addendum 263 item 15: "An arrival OFF the declared pyramid is NOT a refusal: it
    takes the outside-the-store prior, is counted and labelled. The run never stops on a club's provenance." Relegated
    or promoted only from ONE S−1 competition on the declared pyramid; a competition off it, or two places (two S−1
    competitions, "whichever their direction", addendum 282 item 4: a data defect, refused a reduction) is OFF_PYRAMID:
    not relegated, so the fit centres it on the promoted prior, the prior of an arrival from outside the store
    (joint_poisson's penalty rows), counted and labelled (off_pyramid_arrivals, the run record, predict's info)."""
    if not codes:
        return "promoted", codes
    got = _direction(code, codes[0]) if len(codes) == 1 else None      # 282 item 4: two places never reduce to one
    return (got if got is not None else OFF_PYRAMID), codes


def window_arrivals(view, code: str, season: str, sp: str | None, crows) -> tuple[frozenset, dict[int, list[str]]]:
    """(the relegated teams, {team: codes} OFF the declared pyramid: 263 item 15, the outside-the-store prior, counted
    and labelled, never refused) among the clubs of `code`'s season S (its visible rows) absent from its S−1 rows, plus
    every club of S−1's season label elsewhere that a fixture could bring in. The relegated set does not depend on the
    fixture, so the memoised fit serves every fixture of the snapshot."""
    if sp is None:
        return frozenset(), {}
    prev_teams = {t for r, _ in crows if r.season == sp for t in (r.home_id, r.away_id)}
    others = [r for r in view.season_rows(sp) if r.code != code]
    cand = ({t for r in others for t in (r.home_id, r.away_id)}
            | {t for r, _ in crows if r.season == season for t in (r.home_id, r.away_id)}) - prev_teams
    where: dict[int, set] = {}                            # one pass: each club's other competitions in S−1
    for r in others:
        for t in (r.home_id, r.away_id):
            where.setdefault(t, set()).add(r.code)
    rel, bad = set(), {}
    for t in sorted(cand):
        cls, codes = _classify(code, sorted(where.get(t, ())))
        if cls == "relegated":
            rel.add(t)
        elif cls == OFF_PYRAMID:
            bad[t] = codes
    return frozenset(rel), bad


def _fixture_ratings(view, fixture: Fixture, pending_regression: bool) -> tuple[float, float]:
    from src.models.elo import EloConfig, EloState, regress_team
    out = []
    for tid in (fixture.home_id, fixture.away_id):
        r, lk = view.team(tid)
        if r is None:
            out.append(EloConfig().starting_rating)
            continue
        if pending_regression and lk is not None and lk != f"{fixture.code}:{fixture.season}":
            st = EloState(ratings={tid: r}, config=EloConfig())
            regress_team(st, tid)
            r = st.ratings[tid]
        out.append(r)
    return out[0], out[1]


def price(lam_h: float, lam_a: float, v22_poisson: dict):
    """The adaptor (verified, law 1): the REAL poisson.predict_match with context (1, 1), TeamStrength(λ_H, 1) and
    TeamStrength(λ_A, 1), elo_goal_coeff 0 and equal Elo: home_xg = 1·1·λ_H·1·exp(0) = λ_H and away_xg = λ_A exactly,
    then v22's floor, ρ, max_goals and line."""
    from src.models.poisson import CompetitionScoringContext, PoissonConfig, TeamStrength, predict_match
    cfg = replace(PoissonConfig(**v22_poisson), elo_goal_coeff=0.0)
    return predict_match(0.0, 0.0, TeamStrength(attack=lam_h, defense=1.0), TeamStrength(attack=lam_a, defense=1.0),
                         CompetitionScoringContext(avg_goals_per_team_per_match=1.0, home_field_goal_boost=1.0), cfg)


def v22_context(crows):
    """training.py:196-214's formulas on the competition's visible rows (every season)."""
    from src.models.poisson import CompetitionScoringContext
    total = tm = home = hm = 0
    for r, _ in crows:
        total += r.home_goals + r.away_goals
        tm += 2
        home += r.home_goals
        hm += 1
    if tm <= 0:
        return CompetitionScoringContext()
    avg = total / tm
    home_avg = home / hm if hm else avg
    boost = home_avg / avg if avg > 0 else 1.15
    return CompetitionScoringContext(avg_goals_per_team_per_match=avg,
                                     home_field_goal_boost=max(V22_BOOST_CLAMP[0], min(V22_BOOST_CLAMP[1], boost)))


def _v22(view, snap, fixture, memo):
    from src.models.poisson import PoissonConfig, TeamStrength, estimate_strengths, predict_match
    v22p = snap.params()["v22_poisson"]
    cfg = PoissonConfig(**v22p)
    key = ("v22", getattr(view, "digest", None), fixture.code, fixture.season)
    got = memo.get(key) if key[1] is not None else None
    if got is None:
        crows = view.comp(fixture.code)
        ctx = v22_context(crows)
        cur = [r for r, _ in crows if r.season == fixture.season]
        inp, backfilled = cur, False
        if len(cur) < V22_MIN_MATCHES:
            # production's ORDER BY utc_date DESC LIMIT 500: newest first, ties in SQLite's id-ascending scan order
            other = sorted(sorted((r for r, _ in crows if r.season != fixture.season), key=lambda r: r.id),
                           key=lambda r: r.utc_date, reverse=True)
            inp, backfilled = cur + other[:V22_BACKFILL_LIMIT], True
        st = estimate_strengths([{"home_team_id": r.home_id, "away_team_id": r.away_id, "home_score": r.home_goals,
                                  "away_score": r.away_goals} for r in inp], ctx)
        got = (ctx, st, len(cur), backfilled)
        if key[1] is not None:
            memo[key] = got
    ctx, st, n_cur, backfilled = got
    sides, src = [], []
    for tid in (fixture.home_id, fixture.away_id):
        if tid in st:
            sides.append(st[tid])
            src.append("fit")
        else:
            sides.append(TeamStrength(attack=cfg.promoted_attack_prior, defense=cfg.promoted_defense_prior))
            src.append("promoted_default")
    eh, ea = _fixture_ratings(view, fixture, pending_regression=False)
    p = predict_match(eh, ea, sides[0], sides[1], ctx, cfg)
    return p, {"g": ctx.avg_goals_per_team_per_match, "b": ctx.home_field_goal_boost, "n_cur": n_cur,
               "backfilled": backfilled, "strengths_source": src, "factors": V22_FACTORS,
               "context": _context_block(view, fixture, g=ctx.avg_goals_per_team_per_match,
                                         b=ctx.home_field_goal_boost)}


def _context_block(view, fixture: Fixture, fed=None, **values) -> dict:
    """251 item 2: what the arm's g and b (soccer-v23: mu and h, with the average team's implied g and b) were read
    from: CONTEXT_DEFINITION, and the competition's visible rows feeding them (their count and the latest kickoff
    among them, which a test holds strictly before the visibility bound). The values are the ones the arm priced with.
    `fed` is (count, latest kickoff) of the rows that fed them: soccer-v23's window (window_rows, the thin set
    excluded); None, the v22 arm's, every visible row of the competition (263 item 19)."""
    if fed is None:
        crows = view.comp(fixture.code)
        fed = (len(crows), max((r.utc_date for r, _ in crows), default=None))
    n, last = fed
    return {"definition": CONTEXT_DEFINITION, **values, "n_rows": n, "through": _ts(last) if last else None}


def _v23(view, snap, fixture, memo):
    thin = frozenset((c, se) for c, se in snap.params()["thin_excluded"])
    key = ("v23", getattr(view, "digest", None), fixture.code, fixture.season, tuple(sorted(thin)))
    got = memo.get(key) if key[1] is not None else None
    if got is None:
        crows = view.comp(fixture.code)
        wrows, sp, seasons = window_rows(crows, fixture, thin)
        obs = _obs(wrows)
        rel, off = window_arrivals(view, fixture.code, fixture.season, sp, crows)
        in_s = frozenset(t for o in obs if o.slot == jp.CUR for t in (o.home, o.away))
        fed = (len(wrows), max((r.utc_date for r, _, _ in wrows), default=None))
        got = (jp.fit(obs, relegated=rel), sp, sum(1 for o in obs if o.slot == jp.CUR), off, in_s, fed, seasons)
        if key[1] is not None:
            memo[key] = got
    f, sp, n_cur, off, in_s, fed, seasons = got
    # 263 item 15: an arrival off the declared pyramid is priced on the outside-the-store prior, labelled here (the
    # clubs of the window's season S and the fixture's, as the fit saw them), never refused
    off_here = {t: off[t] for t in sorted(off)
                if not f.first_season and t in in_s | {fixture.home_id, fixture.away_id}}
    eh, ea = _fixture_ratings(view, fixture, pending_regression=True)
    lh, la = jp.rates(f, fixture.home_id, fixture.away_id, eh - ea)
    av, term = snap.availability, term_state(snap.params()["availability_on"], snap.availability)
    entries, anotes = term_entries(av, fixture) if term == "on" else ((), [])
    mh, ma, notes = availability(entries, fixture.home_id, fixture.away_id, term == "on")
    notes = ([f"availability record at the decision instant {_ts(snap.decision)}: {av.state} ({av.reason})"]
             + ([f"availability: {len(av.excluded)} backfilled fact(s) excluded (addendum 252 item 1: a source-stamped "
                 "backtest only, never a live-era input; soccer-v23's bar declares none)"] if av.excluded else [])
             + anotes + notes)
    if mh != 1.0 or ma != 1.0:
        lh, la = lh * mh, la * ma
    p = price(lh, la, snap.params()["v22_poisson"])
    g_imp = (math.exp(f.mu + f.h) + math.exp(f.mu)) / 2.0
    return p, {"context": _context_block(view, fixture, fed=fed, mu=f.mu, h=f.h, g=g_imp,
                                         b=math.exp(f.mu + f.h) / g_imp, window=seasons, window_rows=f.n_obs),
               "mu": f.mu, "h": f.h, "beta": f.beta, "prev_season": sp, "first_season": f.first_season,
               "n_cur": n_cur, "labels": list(f.labels), "resid_home": f.resid_home, "resid_away": f.resid_away,
               "iterations": f.iterations, "availability": [mh, ma], "availability_notes": notes,
               "availability_term": term, "availability_record": av.state, "availability_reason": av.reason,
               "home_source": f.strength(fixture.home_id)[2], "away_source": f.strength(fixture.away_id)[2],
               "arrivals_off_pyramid": off_here,
               "thin_excluded_in_window": sorted(se for c, se in thin if c == fixture.code)}


def predict(snap: Snapshot, fixture: Fixture, arm: str, cache: Prefix | None = None) -> dict:
    """THE ONE PREDICTION FUNCTION. Pure: reads only `snap` and `fixture` (and, when given, a Prefix memo built over
    rows the snapshot is a prefix of: it refuses any other, and returns the unmemoised answer bitwise). Refuses a
    snapshot that is not the fixture's: another instant, a row not visible at the kickoff, or an availability fact
    recorded after the snapshot's decision instant or backfilled (the one builder never yields either)."""
    if snap.version != SNAPSHOT_VERSION:
        raise ValueError(f"snapshot version {snap.version!r} is not {SNAPSHOT_VERSION!r}")
    if snap.as_of != fixture.utc_date or (snap.rows and not visible(snap.rows[-1], fixture.utc_date, snap.visibility)):
        raise ValueError("the snapshot is not the fixture's: its rows must be visible at the fixture's own kickoff")
    d = snap.decision
    if any(f.recorded_at > d for f in snap.availability.facts + snap.availability.excluded) or any(
            backfill_reason(f) is not None for f in snap.availability.facts):
        raise ValueError(f"the snapshot is not the fixture's: an availability fact recorded after its decision instant "
                         f"{_ts(d)}, or a backfilled fact among its facts")
    view = cache.view(snap) if cache is not None else _SnapView(snap)
    memo = cache.memo if cache is not None else {}
    if arm == "v22":
        p, info = _v22(view, snap, fixture, memo)
    elif arm == "soccer-v23":
        p, info = _v23(view, snap, fixture, memo)
    else:
        raise ValueError(f"arm {arm!r} is not one of {ARMS}")
    return {"match_id": fixture.id, "arm": arm, "p_home": p.p_home, "p_draw": p.p_draw, "p_away": p.p_away,
            "home_xg": p.home_xg, "away_xg": p.away_xg, "p_over": p.p_over, "info": info}


def by_instant(fixtures) -> list[tuple[datetime, list]]:
    """253 item 2(d) row 5, SIMULTANEOUS KICKOFFS: the fixtures grouped by kickoff instant, in kickoff order (ids
    ascending within an instant). Each group is priced from ONE snapshot of its instant, in the walk and in
    predict_live_slate alike: no fixture of the group sees another's result (visibility_bound(t) <= t − RESULT_LAG)."""
    groups: dict[datetime, list] = {}
    for f in sorted(fixtures, key=lambda x: (x.utc_date, x.id)):
        groups.setdefault(f.utc_date, []).append(f)
    return list(groups.items())


def predict_live_slate(session, fixtures, arm: str, params_json: str, visibility_rule: str,
                       record: AvailabilityRecord | None = None) -> list[dict]:
    """THE PRODUCTION PATH over a slate (251 item 2; 253 item 2(d); #789): the design's only live entry point, which the
    PASS shadow calls (216 item 3) and nothing else replaces. Per kickoff instant (by_instant), ONE snapshot through
    snapshot_from_session (one SELECT bounded at the visibility instant, the store's availability record read under the
    recorded clock), then the one prediction function for each fixture of the instant. It reads no ModelVersion: no
    stored trained context, no stored state, no injuries, lineups or XI table; g and b (soccer-v23: mu and h) are
    CONTEXT_DEFINITION's, the same as the harness's walk at the same instant (tested: bitwise, both arms, the five rows).
    THE DECISION INSTANT (Snapshot.decision = visibility_bound(t)): rows kicking off before it and availability facts
    recorded at or before it, in both paths alike; a call made at or after it (under "day", the morning chain of the
    fixture's own UTC date) holds every fact the replay reads, so row 4 is the same record content in both paths.
    The residual, labelled (results and facts alike): the bound is a declared instant, not the time our store learned a
    result (no match row carries a recorded-at stamp), so a result the live store has not yet synced at the call, and,
    for a call made BEFORE the decision instant (a previous day's chain under "day"; any call earlier than t −
    RESULT_LAG under "kickoff"), a result or fact arriving between the call and the decision instant, is absent here
    and present in a replay on a later copy; never the reverse (no row inside the lag, and no fact recorded after the
    decision instant, is visible to either)."""
    rec = availability_record(session) if record is None else record
    out = []
    for t, group in by_instant(fixtures):
        snap = snapshot_from_session(session, t, params_json, visibility_rule, rec)
        out.extend(predict(snap, fx, arm) for fx in group)
    return out


def predict_live(session, fixture: Fixture, arm: str, params_json: str, visibility_rule: str,
                 record: AvailabilityRecord | None = None) -> dict:
    """predict_live_slate for one fixture (the same path)."""
    return predict_live_slate(session, [fixture], arm, params_json, visibility_rule, record)[0]


# --------------------------------------------------------------------------------------------- the walk --

def _actual(r: Row) -> str:
    return "H" if r.home_goals > r.away_goals else "A" if r.home_goals < r.away_goals else "D"


def _first_season_census(rows, scope: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """({code: every season soccer-v23 prices as a first season, in season order}, {code: its thin seasons before the
    first of them}), over `rows` IN THE STAGE SCOPE less 263 item 14's thin set (thin_season_keys of that history, the
    set the_pot freezes). A season is priced as a first season when its S−1 (_season_order, window_obs's own rule) is
    None or thin: window_obs gives a thin S−1 no row, and never skips over it to an older season. Under LEAGUE_REGULAR
    only the rows soccer_expansion.placement reads "regular" count (in_scope's rule; a label it cannot place is not
    regular, and the stage refusal names it); `scope` is required, never defaulted."""
    if scope not in SCOPE_RULES:
        raise ValueError(f"scope {scope!r} is not one of {SCOPE_RULES}")
    if scope == "LEAGUE_REGULAR":
        from src.walters.soccer_expansion import placement
        rows = [r for r in rows if placement(r.stage) == "regular"]
    thin = set(thin_season_keys(rows))
    windows: dict[str, list[str]] = {}
    before: dict[str, list[str]] = {}
    for code in sorted({r.code for r in rows}):
        crows = [(r, None) for r in rows if r.code == code]
        first: dict[str, datetime] = {}
        for r, _ in crows:
            if r.season not in first or r.utc_date < first[r.season]:
                first[r.season] = r.utc_date
        for season, d in sorted(first.items(), key=lambda kv: (kv[1], kv[0])):
            if (code, season) in thin:
                if code not in windows:
                    before.setdefault(code, []).append(season)
                continue
            sp = _season_order(crows, Fixture(0, code, season, d, 0, 0))
            if sp is None or (code, sp) in thin:
                windows.setdefault(code, []).append(season)
    return windows, before


def first_season_windows(rows, scope: str) -> dict[str, list[str]]:
    """Per competition, every season soccer-v23 prices as a first season (the weak prior, 263 item 3): its first
    in-scope season outside the thin set, and every season whose S−1 is thin (263 item 14: out of soccer-v23's
    window). The preflight prints them, so the season the walk treats as a first season is the one it names."""
    return _first_season_census(rows, scope)[0]


def first_seasons(rows, scope: str) -> dict[str, str]:
    """Each competition's first season among `rows` IN THE STAGE SCOPE and outside 263 item 14's thin set (by earliest
    kickoff): the season with no S−1 in soccer-v23's window. ARCHITECT 2026-11-05 13:50 ET, addendum 264 item 2(a):
    "`first_seasons` COMPUTED BEFORE THE STAGE SCOPE — a real harness defect: a competition whose first stored season
    holds only out-of-scope rows would have its first IN-SCOPE season read as a continuing one"; a thin first season is
    the same defect one layer up (window_obs gives it no row, so the season after it is the walk's first). A
    competition with no in-scope season outside the thin set has no entry."""
    return {c: ses[0] for c, ses in first_season_windows(rows, scope).items()}


def stage_census(rows) -> dict[tuple[str, str], dict]:
    """Per competition-season, soccer_expansion.placement's three values over the rows' stage labels: the regular
    count, the play-off labels (left out BY CAUSE under LEAGUE_REGULAR) and the labels that cannot be placed (NULL,
    empty, any other form), each label with its count."""
    from src.walters.soccer_expansion import placement
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        c = out.setdefault((r.code, r.season), {"regular": 0, "playoff": {}, "unplaced": {}})
        pl = placement(r.stage)
        if pl == "regular":
            c["regular"] += 1
        else:
            d = c["playoff" if pl == "playoff" else "unplaced"]
            d[r.stage] = d.get(r.stage, 0) + 1
    return out


def _labels(d: dict) -> str:
    return ", ".join(f"{k!r} {n}" for k, n in sorted(d.items(), key=lambda kv: (kv[0] is not None, str(kv[0]))))


def stage_refusals(rows, slots: dict) -> list[str]:
    """Under LEAGUE_REGULAR, soccer_expansion F3's rule: "A label the code cannot place refuses the run (never
    guessed)". One line per competition-season holding a walked row whose label cannot be placed; empty under LEAGUE
    (no stage rule) or when every label is placed."""
    if slots.get("scope") != "LEAGUE_REGULAR":
        return []
    return [f"{c} {se}: {_labels(v_['unplaced'])}" for (c, se), v_ in sorted(stage_census(rows).items())
            if v_["unplaced"]]


def off_pyramid_arrivals(rows, thin) -> list[str]:
    """THE CENSUS OF 263 item 15 (ARCHITECT 2026-11-05 12:50 ET: "An arrival OFF the declared pyramid is NOT a refusal:
    it takes the outside-the-store prior, is counted and labelled. The run never stops on a club's provenance."): every
    club, absent from a competition's S−1 rows, whose S−1 rows lie in a competition off the declared pyramid (PYRAMIDS)
    or in two places (two S−1 competitions, whichever their direction: addendum 282 item 4): one line each, printed by
    the preflight before the reservation and counted in the run record. `thin` is 263 item 14's frozen set (the_pot's;
    required, never defaulted), read as the walk reads it (window_obs): a thin S is not priced, and a thin S−1 leaves S
    a first season (the weak prior, no arrival), so neither is listed."""
    thin = set(map(tuple, thin))
    out = []
    for code in sorted({r.code for r in rows}):
        crows = [(r, None) for r in rows if r.code == code]
        for season in sorted({r.season for r, _ in crows}):
            if (code, season) in thin:
                continue
            first = min(r.utc_date for r, _ in crows if r.season == season)
            sp = _season_order(crows, Fixture(0, code, season, first, 0, 0))
            if sp is not None and (code, sp) in thin:
                continue                                  # window_obs: a first season, the weak prior
            view = _RowsList(rows)
            _, bad = window_arrivals(view, code, season, sp, [(r, p_) for r, p_ in crows if r.season in (season, sp)])
            in_s = {t for r, _ in crows if r.season == season for t in (r.home_id, r.away_id)}
            for t in sorted(set(bad) & in_s):
                out.append(f"{code} {season}: club {t} arrives from {bad[t]} (S−1 {sp}), off the declared pyramid: "
                           "the outside-the-store prior")
    return out


def scored_rows(rows, slots: dict) -> list[Row]:
    """The scored set: every admitted row at or before the cut, of a LEAGUE-type competition (admission), with the
    scope's stage rule; each competition's first season out by cause when first_season is exclude_as_warmup. The
    within-season skip is zero (WITHIN_SEASON_SKIP): no prior-count condition exists. Under LEAGUE_REGULAR a play-off
    label is left out BY CAUSE and a label that cannot be placed REFUSES (stage_refusals; never a silent drop)."""
    from src.walters.soccer_expansion import placement
    cut = parse_instant(slots["cut"])
    refused = stage_refusals(rows, slots)
    if refused:
        raise GateRefused("a walked row's stage label cannot be placed under scope LEAGUE_REGULAR (soccer_expansion "
                          "F3: never guessed; the architect rules first): " + "; ".join(refused))
    fs = first_seasons(rows, slots["scope"])              # 264 item 2(a): the first IN-SCOPE season
    out = []
    for r in rows:
        if r.utc_date > cut:
            continue
        if slots["scope"] == "LEAGUE_REGULAR" and placement(r.stage) != "regular":
            continue                                      # a play-off round, by cause (an unplaced label refused above)
        if slots["first_season"] == "exclude_as_warmup" and fs.get(r.code) == r.season:
            continue
        out.append(r)
    return sorted(out, key=Row.key)


def the_pot(rows, slots: dict) -> tuple[list[Row], list[tuple[str, str]], list[Row]]:
    """(the walked history, the thin set, the scored set), the preflight's and the run's one computation, BEFORE the
    reservation: the history in the declared stage scope (in_scope), the competition-seasons 263 item 14 excludes by
    cause (thin_season_keys of that history), and scored_rows less those seasons' rows. Each thin season is named by the
    preflight and frozen in the fingerprint (its rows and the scored ids) and in the walk's params."""
    hist = in_scope(rows, slots["scope"])
    thin = thin_season_keys(hist)
    out = set(thin)
    return hist, thin, [r for r in scored_rows(rows, slots) if (r.code, r.season) not in out]


def walk(rows, fixtures, params_json: str, visibility_rule: str, use_cache: bool = True,
         record: AvailabilityRecord = ROWS_ONLY) -> dict:
    """Both arms over `fixtures` in kickoff order (predict-then-nothing: no row is ever updated by a prediction), ONE
    snapshot per kickoff instant (by_instant: row 5), built by calling the one builder snapshot_from_rows itself at
    every instant, with the same availability record live reads (row 4); `use_cache` adds only the Prefix memo of the
    fits (keyed by the builder's own output), never a second builder. Returns {"v22": [rows], "soccer-v23": [rows],
    "strata": [...], "context": [...], "availability": [...]} with each row's actual 90-minute outcome; "context"
    holds, per fixture, the g and b each arm priced with (soccer-v23: mu and h; 251 item 2), reported only;
    "availability", per fixture, the record's state at the decision instant, the term's and the backfilled facts
    excluded (availability_lines prints them per era)."""
    rows = sorted(in_scope(rows, json.loads(params_json)["scope"]), key=Row.key)   # the history the builder keeps
    cache = Prefix(rows) if use_cache else None
    out = {"v22": [], "soccer-v23": [], "strata": [], "context": [], "availability": []}
    for t, group in by_instant(fixtures):
        snap = snapshot_from_rows(rows, t, params_json, visibility_rule, record)
        for r in group:
            fx = Fixture.of(r)
            p22 = predict(snap, fx, "v22", cache)
            p23 = predict(snap, fx, "soccer-v23", cache)
            if p23["info"]["availability"] != [1.0, 1.0] and p23["info"]["availability_term"] != "on":
                raise GateRefused("the availability multiplier is not 1.0 where the term is off (the slot, or no record "
                                  "at the instant): no injury history exists and none is manufactured (216 item 4); "
                                  "the walk stops")
            a = _actual(r)
            out["context"].append({"match_id": r.id, "v22": p22["info"]["context"],
                                   "soccer-v23": p23["info"]["context"]})
            out["availability"].append({"match_id": r.id, "code": r.code, "season": r.season,
                                        "state": snap.availability.state, "reason": snap.availability.reason,
                                        "term": p23["info"]["availability_term"],
                                        "excluded": len(snap.availability.excluded)})
            for arm, p in (("v22", p22), ("soccer-v23", p23)):
                out[arm].append({"match_id": r.id, "p_home": p["p_home"], "p_draw": p["p_draw"],
                                 "p_away": p["p_away"], "actual": a})
            crows = [x for x, _ in (cache.view(snap) if cache is not None else _SnapView(snap)).comp(r.code)]
            own = {tid: sum(1 for x in crows if x.season == r.season and tid in (x.home_id, x.away_id))
                   for tid in (r.home_id, r.away_id)}
            out["strata"].append({"match_id": r.id, "code": r.code, "league_n": p23["info"]["n_cur"],
                                  "team_min_n": min(own.values()), "beta": p23["info"]["beta"],
                                  "resid": max(abs(p23["info"]["resid_home"]), abs(p23["info"]["resid_away"])),
                                  "first_season": p23["info"]["first_season"]})
    return out


def _ll(r: dict) -> float:
    k = {"H": "p_home", "D": "p_draw", "A": "p_away"}[r["actual"]]
    return -math.log(max(1e-12, r[k] / (r["p_home"] + r["p_draw"] + r["p_away"])))


def strata_lines(w: dict) -> list[str]:
    """Reported only, gating nothing: the league's season count (below 30 / at least 30: the boundary 216 item 2
    found unevaluated), the lower of the two teams' own season counts, per competition; β̂ and the I1/I2 residuals."""
    def team_bin(n: int) -> str:
        return "0" if n == 0 else "1-4" if n < 5 else "5-9" if n < 10 else ">= 10"

    groups: dict[str, list[int]] = {}
    for i, s in enumerate(w["strata"]):
        for g in (f"league count {'< 30' if s['league_n'] < 30 else '>= 30'}",
                  f"team min count {team_bin(s['team_min_n'])}", f"competition {s['code']}"):
            groups.setdefault(g, []).append(i)
    L = ["  STRATA (reported only, gating nothing):"]
    for g in sorted(groups):
        ix = groups[g]
        a = sum(_ll(w["v22"][i]) for i in ix) / len(ix)
        b = sum(_ll(w["soccer-v23"][i]) for i in ix) / len(ix)
        L.append(f"    {g}: n={len(ix)} · v22 {a:.6f} · soccer-v23 {b:.6f}")
    if w["strata"]:
        L.append(f"    beta (per Elo point) range {min(s['beta'] for s in w['strata']):.6g} .. "
                 f"{max(s['beta'] for s in w['strata']):.6g} · max |I1|,|I2| residual "
                 f"{max(s['resid'] for s in w['strata']):.3e}")
    return L


# ---------------------------------------------------------------------------------------------- the gate --

def _reg():
    from src.walters import registry as reg
    return reg


def code_constants() -> dict:
    """The design's constants, as the declaration must freeze them (the run refuses any difference)."""
    return {"K_PRIOR": jp.K_PRIOR, "G0": jp.G0, "B0": jp.B0, "PROMOTED_ATTACK_MULT": jp.PROMOTED_ATTACK_MULT,
            "PROMOTED_DEFENCE_MULT": jp.PROMOTED_DEFENCE_MULT, "CARRY": jp.CARRY, "ELO_SCALE": jp.ELO_SCALE,
            "MAX_ITER": jp.MAX_ITER, "MAX_HALVINGS": jp.MAX_HALVINGS, "TOL": jp.TOL,
            "PRECISION_FLOOR": jp.PRECISION_FLOOR, "V22_MIN_MATCHES": V22_MIN_MATCHES,
            "V22_BACKFILL_LIMIT": V22_BACKFILL_LIMIT, "WITHIN_SEASON_SKIP": WITHIN_SEASON_SKIP,
            "RESULT_LAG_HOURS": RESULT_LAG_HOURS,
            "BETA_PRIOR_MEAN": jp.BETA_PRIOR_MEAN, "BETA_PRIOR_PRECISION": jp.BETA_PRIOR_PRECISION,
            "RELEGATED_ATTACK": jp.RELEGATED_ATTACK, "RELEGATED_DEFENCE": jp.RELEGATED_DEFENCE,
            "PYRAMIDS": [list(p) for p in PYRAMIDS],
            # 262 item 2: the record's constant filtered to soccer sources (another sport's entry never moves it)
            "SOURCE_CADENCE_HOURS": source_cadence_hours()}


def constants_state(e: dict | None) -> str | None:
    blk = (e or {}).get("frozen_constants")
    if not isinstance(blk, dict):
        return "the registry entry has no frozen_constants block"
    code = code_constants()
    if set(blk) != set(code):
        return (f"the entry's frozen_constants do not name exactly the design's ({', '.join(code)}): missing "
                f"{sorted(set(code) - set(blk))}, extra {sorted(set(blk) - set(code))}")
    def differs(k) -> bool:
        if isinstance(code[k], (list, dict)):             # PYRAMIDS, SOURCE_CADENCE_HOURS: compared as JSON
            return blk[k] != code[k]
        return isinstance(blk[k], bool) or not isinstance(blk[k], (int, float)) or float(blk[k]) != float(code[k])
    diff = [f"{k}: entry {blk[k]!r}, code {code[k]!r}" for k in code if differs(k)]
    return ("the entry's frozen constants differ from the code's (" + "; ".join(diff) + ")") if diff else None


def slots_state(e: dict | None) -> tuple[dict | None, str | None]:
    blk = (e or {}).get(SLOTS_KEY)
    if not isinstance(blk, dict):
        return None, f"the registry entry has no {SLOTS_KEY} block (every slot is the architect's, 11-20)"
    for k in SLOT_KEYS:
        v = blk.get(k)
        if v is None:
            return None, f"the declaration slot {k!r} is null: the run refuses until the architect fills it"
        if k == "cut":
            if not isinstance(v, str) or parse_instant(v) is None:
                return None, f"the declaration slot 'cut' is {v!r}, not an ISO-8601 UTC instant"
        elif k == "availability_on":
            if not isinstance(v, bool):
                return None, f"the declaration slot 'availability_on' is {v!r}, not true or false"
        elif k == "v22_recorded_log_loss":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                return None, (f"the declaration slot 'v22_recorded_log_loss' is {v!r}, not a finite positive number "
                              "(v22's recorded figure, as recorded: 251 item 2)")
        elif k == "v22_recorded_source":
            if not isinstance(v, str) or not v.strip():
                return None, (f"the declaration slot 'v22_recorded_source' is {v!r}, not a non-empty string naming "
                              "where v22's figure is recorded")
        elif v not in SLOT_VALUES[k]:
            return None, f"the declaration slot {k!r} is {v!r}, not one of {SLOT_VALUES[k]}"
    extra = sorted(set(blk) - set(SLOT_KEYS))
    if extra:
        return None, f"the {SLOTS_KEY} block names slots the design does not read: {extra}"
    return {k: blk[k] for k in SLOT_KEYS}, None


def bar_state(e: dict | None) -> str | None:
    g = (e or {}).get("gate")
    return None if g == BAR_TEXT else "the entry's gate is not BAR_TEXT, character for character"


RESERVATION = None                  # None = docs/registry/soccer-v23.started.json (tests point it at a tmp path)


def reservation_path() -> str:
    return RESERVATION or os.path.join(os.path.dirname(_reg().LEDGER), f"{EID}.started.json")


def declared_unrun() -> dict:
    reg = _reg()
    e = reg.get(EID, reg.LEDGER)
    if e is None or e.get("status") != "declared" or e.get("run") is not None:
        raise GateRefused(f"{EID} must be declared and unrun in the registry (status "
                          f"{e.get('status') if e else 'absent'}; the declaration is the architect's, 11-20): the pot "
                          "is read once for this candidate")
    if os.path.exists(reservation_path()):
        raise GateRefused(f"{EID}: a run was started ({os.path.relpath(reservation_path())}); nothing reruns without "
                          "an architect ruling")
    return e


def production_params(session) -> tuple[str | None, dict | None]:
    """The copy's soccer production ModelVersion: (version, parameters["poisson"]). Every soccer_elo_poisson row
    marked production is loaded, and the copy is REFUSED unless there is exactly one (Codex on #832, round 1: the live
    resolver reads it with scalar-one semantics, so a store holding two has no unambiguous production model; never
    the newest id picked). None of them: (None, None), which the run refuses as "not v22"."""
    from sqlalchemy import select

    from src.db.schema import ModelVersion, Sport
    mvs = session.execute(select(ModelVersion).where(ModelVersion.sport == Sport.SOCCER,
                                                     ModelVersion.model_family == "soccer_elo_poisson",
                                                     ModelVersion.status == "production")
                          .order_by(ModelVersion.id)).scalars().all()
    if not mvs:
        return None, None
    if len(mvs) > 1:
        raise GateRefused(f"the copy holds {len(mvs)} soccer_elo_poisson rows marked production ("
                          + ", ".join(f"id {m.id} {m.version!r}" for m in mvs) + "): no unambiguous production "
                          "model (the live resolver reads exactly one); never the newest picked; nothing reserved")
    mv = mvs[0]
    return mv.version, dict((mv.parameters or {}).get("poisson") or {})


def fence_refusals(codes, cut: datetime) -> list[str]:
    """Every fence called with through = the cut (pl_availability.fence_refusal; soccer_expansion.guards_backtest,
    which carries the leagues' window fence, leagues_window.fence_refusal). Any refusal refuses the run."""
    from src.walters import pl_availability as pla
    from src.walters import soccer_expansion as sx
    out = []
    for c in sorted(set(codes)):
        for why in (pla.fence_refusal(c, None, cut), sx.guards_backtest(c, None, cut)):
            if why:
                out.append(f"{c}: {why}")
    return out


def availability_reads(record: AvailabilityRecord, scored, rule: str) -> list:
    """Every as-of read of the availability record the walk can make over `scored` (one per decision instant,
    visibility_bound of each scored kickoff under `rule`, ascending), each through the builder's own checked read
    (read_availability), canonical: [instant, state, reason, clock, facts, excluded]. While the tables are absent each
    is the adapter's NoRecord with its reason (the tables' absence, said so)."""
    out = []
    for d in sorted({visibility_bound(r.utc_date, rule) for r in scored}):
        av = read_availability(record, d)
        out.append([_ts(d), av.state, av.reason, av.clock, [f.canon() for f in av.facts],
                    [f.canon() for f in av.excluded]])
    return out


def stream_fingerprint(rows, scored, slots: dict, v22_poisson: dict,
                       record: AvailabilityRecord) -> tuple[str, int]:
    """sha256 over the walked rows (ROW_FIELDS, walk order: the history in the declared stage scope, in_scope), the
    scored ids, the slots, v22's stored poisson params, the design's constants, SNAPSHOT_VERSION and EVERY as-of read
    of the availability record the walk makes (availability_reads; Codex on #832, round 1: a copy whose record differs
    is a different stream, whatever its rows). JSON, sorted keys, no whitespace."""
    body = {"tag": FINGERPRINT_TAG, "fields": list(ROW_FIELDS), "rows": [r.canon() for r in rows],
            "scored": [r.id for r in scored], "slots": slots, "v22_poisson": v22_poisson,
            "constants": code_constants(), "snapshot_version": SNAPSHOT_VERSION,
            "availability_reads": availability_reads(record, scored, slots["visibility"])}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(blob.encode("ascii")).hexdigest(), len(rows)


def _load(db, slots):
    from src.walters import nfl_v2_gate as ng
    try:
        path = ng.check_db(db)
    except ng.GateRefused as err:
        raise GateRefused(str(err))
    with ng.db_session(path) as s:
        version, v22p = production_params(s)
        rows = load_rows(s, through=parse_instant(slots["cut"]))
        # 253 item 2(d) row 4: the copy's own record (or none), read through record.as_of (263 item 23) at every
        # decision instant its rows can need (the scored set's are among them) while the copy is open
        record = read_at(availability_record(s), {visibility_bound(r.utc_date, slots["visibility"]) for r in rows})
    return path, version, v22p, rows, record


def thin_season_keys(rows) -> list[tuple[str, str]]:
    """THE EXCLUSION SET OF 263 item 14 (ARCHITECT 2026-11-05 12:50 ET: "THIN SEASONS — EXCLUSION BY CAUSE, not
    refusal: a competition-season with no home or no away goal in a window is excluded, counted and labelled in the run
    record; the preflight names every such season BEFORE the reservation so the exclusion set is known and frozen with
    the declaration"): each (code, season) of `rows` (the walked history) naming no home goal or no away goal, sorted.
    A goal total only: no figure of either arm."""
    tot: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        t = tot.setdefault((r.code, r.season), [0, 0])
        t[0] += r.home_goals
        t[1] += r.away_goals
    return sorted(k for k, (h, a) in tot.items() if h == 0 or a == 0)


def thin_seasons(rows) -> list[str]:
    """The census preflight prints (counts and goal totals only, no figure of either arm): each competition-season of
    thin_season_keys with its row count and the side that has no goal. The fit cannot converge on a window whose only
    rows are those (μ or h runs to minus infinity), so each is excluded by cause (263 item 14): out of the scored set
    and out of soccer-v23's window (window_obs), the v22 arm's history and the ladder untouched."""
    tot: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        t = tot.setdefault((r.code, r.season), [0, 0, 0])
        t[0] += 1
        t[1] += r.home_goals
        t[2] += r.away_goals
    return [f"{c} {s} ({n} rows: {'no home goal' if h == 0 else ''}{' and ' if h == 0 and a == 0 else ''}"
            f"{'no away goal' if a == 0 else ''})" for (c, s), (n, h, a) in sorted(tot.items()) if h == 0 or a == 0]


def preflight_lines(entry: dict | None, db) -> list[str]:
    """Fits nothing, prices nothing, reads no outcome into a figure: the counts, the first seasons, the scored n, the
    slots, v22's params, the fences and, last, the fingerprint. Refuses without --db (the copy)."""
    L = [f"SOCCER-V23 · PREFLIGHT (fits nothing, prices nothing) · {RULING}", f"  {POT_LABEL}"]
    slots, why = slots_state(entry)
    L.append("  slots: " + (json.dumps(slots, sort_keys=True) if slots else f"NOT DECLARED — the run refuses: {why}")
             + f" · recommended {json.dumps(RECOMMENDED, sort_keys=True)}")
    cwhy = constants_state(entry)
    L.append("  constants: " + json.dumps(code_constants(), sort_keys=True) + " · "
             + ("SAME as the entry's" if not cwhy else f"the run refuses: {cwhy}"))
    bwhy = bar_state(entry)
    L.append("  bar: " + ("the entry's gate is BAR_TEXT" if not bwhy else f"the run refuses: {bwhy}"))
    L.append(f"  context (both arms, harness and production path): {CONTEXT_DEFINITION}")
    L.append("  v22's recorded figure (declaration slots v22_recorded_log_loss / v22_recorded_source; never recomputed): "
             + (f"{slots['v22_recorded_log_loss']!r} from {slots['v22_recorded_source']!r}" if slots else
                "NOT DECLARED"))
    if not slots:
        L.append("PREFLIGHT only: nothing loaded without the declared slots (the cut bounds every read).")
        return L
    if db is None or not str(db).strip():
        raise GateRefused("--db COPY is required: a .backup copy outside data/ (mode=ro&immutable=1)")
    path, version, v22p, rows, record = _load(db, slots)
    from src.walters import nfl_v2_gate as ng
    L.append(f"  {ng.db_label(path)}")
    L.append(f"  production version on the copy: {version!r} (the run refuses unless {BASE_VERSION!r}) · poisson "
             f"{json.dumps(v22p, sort_keys=True) if v22p is not None else None}")
    by = {}
    for r in rows:
        by.setdefault(r.code, {}).setdefault(r.season, 0)
        by[r.code][r.season] += 1
    # 264 item 2(a): the first IN-SCOPE season, outside 263 item 14's thin set, and every later season the walk prices
    # as a first season (its S−1 thin): the seasons the walk treats as first are the ones this line names
    fw, fb = _first_season_census(rows, slots["scope"])
    for c in sorted(by):
        ws = fw.get(c, [])
        L.append(f"  {c}: " + ", ".join(f"{s} {n}" for s, n in sorted(by[c].items()))
                 + f" · first season in scope {ws[0] if ws else 'none (no in-scope season outside the thin set)'}"
                 + (f" ({', '.join(f'{c} {se}' for se in fb[c])} excluded by cause, addendum 263 item 14)"
                    if fb.get(c) else "")
                 + (f" · priced as a first season again after a thin S−1 (addendum 263 item 14): {', '.join(ws[1:])}"
                    if len(ws) > 1 else ""))
    for (c, se), cen in sorted(stage_census(rows).items()):
        if cen["playoff"] or cen["unplaced"]:
            L.append(f"  stages {c} {se}: regular {cen['regular']} · play-off (left out by cause under "
                     f"LEAGUE_REGULAR) {_labels(cen['playoff']) or 'none'} · CANNOT BE PLACED "
                     f"{_labels(cen['unplaced']) or 'none'}")
    sr = stage_refusals(rows, slots)
    L.append("  stage labels: " + ("every walked label placed (or scope LEAGUE: no stage rule)" if not sr else
                                   "REFUSED under LEAGUE_REGULAR — " + "; ".join(sr)))
    if sr:
        L.append("PREFLIGHT only: nothing fitted, nothing priced, nothing reserved, nothing recorded; NO fingerprint: "
                 "the run refuses while a walked row's stage label cannot be placed (never guessed); the architect "
                 "rules first.")
        return L
    hist, thin, sc = the_pot(rows, slots)                 # F3's history; 263 item 14's set; the scored set
    ar = off_pyramid_arrivals(hist, thin)
    L.append(f"  arrivals off the declared pyramid (addendum 263 item 15: the outside-the-store prior, counted and "
             f"labelled, never a refusal): {len(ar)}" + ("" if not ar else " — " + "; ".join(ar)))
    L.append(f"  walked {len(hist)} admitted rows at or before the cut {slots['cut']} (scope {slots['scope']}: "
             f"{len(rows) - len(hist)} play-off row(s) out of the history and the scored set, F3) · scored {len(sc)} "
             f"(counts only; within-season skip {WITHIN_SEASON_SKIP})")
    L += availability_lines([{"code": r.code, "season": r.season, "reason": av.reason,
                              "term": term_state(slots["availability_on"], av), "excluded": len(av.excluded)}
                             for r in sc for av in (read_availability(record, visibility_bound(r.utc_date,
                                                                                               slots["visibility"])),)])
    tl = thin_seasons(hist)
    L.append(f"  thin seasons excluded by cause (addendum 263 item 14): {len(thin)} competition-season(s), "
             f"{sum(1 for r in hist if (r.code, r.season) in set(thin))} row(s)"
             + (" — " + "; ".join(tl) + " (out of the scored set and out of soccer-v23's window; the v22 arm's "
                "history and the ladder keep them; frozen with the declaration)" if tl else ""))
    fr = fence_refusals({r.code for r in rows}, parse_instant(slots["cut"]))
    L.append("  fences at the cut: " + ("clear" if not fr else "REFUSED — " + " | ".join(fr)))
    fp, n = stream_fingerprint(hist, sc, slots, v22p or {}, record)
    L.append("PREFLIGHT only: nothing fitted, nothing priced, nothing reserved, nothing recorded.")
    L.append(f"STREAM FINGERPRINT {fp} ({n} rows; the run takes it as --stream-fingerprint)")
    return L


def reserve(meta: dict, no_fetch: bool = False, echo=None) -> str:
    """The #329 cross-ref guard, then the exclusive create of the reservation (serialised first; written, fsynced,
    closed, its directory fsynced; on a failure removed and refused: nothing priced). nfl_v2_gate.reserve's shape."""
    from src.walters import nfl_v2_gate as ng
    reg = _reg()
    p = reservation_path()
    if os.path.exists(p):
        raise GateRefused(f"{EID}: a run was started ({os.path.relpath(p)})")
    try:
        receipt = reg.cross_ref_guard(EID, no_fetch=no_fetch)
    except reg.RegistryError as err:
        raise GateRefused(str(err))
    if echo:
        echo(receipt)
    try:
        data = (json.dumps({"id": EID, "started_at": _iso(_now()), "guard": receipt, **meta}) + "\n").encode("utf-8")
    except Exception as err:
        raise GateRefused(f"{EID}: the reservation could not be serialised ({err}); nothing written") from err
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as err:
        raise GateRefused(f"{EID}: the reservation could not be created ({type(err).__name__}: {err}); nothing "
                          "written, nothing priced") from err
    try:
        ng._write_all(fd, data)
        os.close(fd)
        fd = None
        ng._fsync_dir(p)
    except BaseException as err:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(p)
            ng._fsync_dir(p)
        except OSError as uerr:
            raise GateRefused(f"{EID}: the reservation could not be written ({err}) nor removed ({uerr}): INSPECT "
                              f"{os.path.relpath(p)}") from err
        if not isinstance(err, Exception):
            raise
        raise GateRefused(f"{EID}: the reservation could not be written ({err}); removed; nothing priced") from err
    return p


def _now() -> datetime:
    from src.timeutil import utc_now_naive
    return utc_now_naive()


def run(word: str | None, fingerprint: str | None, db=None, no_fetch: bool = False, echo=None) -> dict:
    """THE ONE RUN. Refused, nothing reserved and nothing recorded, in this order: no declared unrun entry (or a
    reservation); a null or invalid slot; the entry's constants or gate not the code's; no word; no fingerprint; no
    --db or a copy check_db refuses; the copy holding more than one soccer_elo_poisson row marked production
    (production_params, in _load: never the newest picked); the copy's availability record half present, present and
    not migrated, or holding a soccer fact the reader cannot map (availability_record and read_at, in _load: the record
    read through record.as_of, addendum 263 item 23); the copy's production version not v22; a fence refusing at the
    cut; under LEAGUE_REGULAR a walked stage label that cannot be placed; a fingerprint that does not match. A club's
    provenance never refuses (263 item 15: an arrival off the declared pyramid is counted and takes the
    outside-the-store prior), nor does a thin season (263 item 14: excluded by cause, the_pot, before the reservation,
    named by the preflight). Then the cross-ref guard and the reservation,
    BEFORE any outcome is scored or priced: the outcome-bearing stream (the admitted rows with their goals) is loaded
    and fingerprinted before the reservation, as in both precedent gates (nfl_v2_gate.run: load :655, fingerprint
    :667-668, reserve :678, its guard inside reserve :427; ncaa_v1r_gate.run: load :798, fingerprint :799-800, reserve
    :824, its guard inside reserve :301), and nothing is fitted, scored or priced before it (ARCHITECT 2026-11-04
    15:45 ET, addendum 254 item 3: "preflight → fingerprint → cross_ref_guard → reservation → walk → record", the
    three gates' common order; --preflight is its own earlier invocation in all three). A MISSING fingerprint is
    refused right after the word, before any load, MATCHING both precedents (soccer_v23.py:1954, nfl_v2_gate.py:642,
    ncaa_v1r_gate.py:792); a WRONG one is refused at the compare, after the load, as in both. Then the walk of
    both arms (v22 re-walked beside soccer-v23 on the same harness: the same scored set, the same as-of context
    definition, the same skip zero), the comparison (soccer_backtest.compare_candidate) and decide (THE BAR, 251 item
    2: at least DEFAULT_PROMOTION_DELTA below BOTH v22's recorded figure, read from its declaration slot, AND the
    re-walked one; pinned by tests that drive run itself at each side of each comparison) and the record. A failure
    after the reservation leaves it standing (the pot may have been read; RULED, addendum 263 item 13: the one run
    SPENT, "never a code path that releases it on its own"): the fit refusing or a walk guard refusing is raised as
    SpentRefused, which the gate prints as its REFUSED line with its reason (addendum 264 item 2(b)), nothing
    recorded."""
    e = declared_unrun()
    slots, why = slots_state(e)
    if why:
        raise GateRefused(f"{EID}: {why}; nothing read, nothing reserved")
    for w_ in (constants_state(e), bar_state(e)):
        if w_:
            raise GateRefused(f"{EID}: {w_}; nothing read, nothing reserved")
    if not word or not str(word).strip():
        raise GateRefused("the run starts only on the architect's word (216 item 3): pass --architect-word verbatim")
    if not fingerprint or not str(fingerprint).strip():  # 254 item 3: before any load, as nfl_v2_gate / ncaa_v1r_gate
        raise GateRefused("the word refers to one stream (addendum 17 item 1): pass --stream-fingerprint with the last "
                          f"line of {COMMAND} --preflight; nothing read, nothing reserved")
    if db is None or not str(db).strip():
        raise GateRefused("the ONE run reads a .backup copy outside data/ opened immutable=1 (216 item 3): pass --db")
    path, version, v22p, rows, record = _load(db, slots)
    if version != BASE_VERSION or not v22p:
        raise GateRefused(f"the copy's soccer production version is {version!r}, not {BASE_VERSION!r} (or carries no "
                          "poisson params): the bar is against v22; nothing reserved")
    cut = parse_instant(slots["cut"])
    fr = fence_refusals({r.code for r in rows}, cut)
    if fr:
        raise GateRefused("a fence refuses at the cut: " + " | ".join(fr) + "; nothing reserved")
    sr = stage_refusals(rows, slots)
    if sr:
        raise GateRefused("a walked row's stage label cannot be placed under scope LEAGUE_REGULAR (soccer_expansion "
                          "F3: never guessed): " + "; ".join(sr) + "; nothing reserved")
    # F3: the history the walk keeps (a play-off row never in it); 263 item 14's thin set, out of the scored set;
    # 263 item 15: an arrival off the pyramid is counted and labelled, never a refusal
    hist, thin, sc = the_pot(rows, slots)
    ar = off_pyramid_arrivals(hist, thin)
    fp, n = stream_fingerprint(hist, sc, slots, v22p, record)
    if not fingerprint or str(fingerprint).strip() != fp:
        raise GateRefused(f"the stream fingerprint given ({fingerprint!r}) is not the stream about to be walked ({fp}, "
                          f"{n} rows): re-run {COMMAND} --preflight and take the word on it; nothing reserved")
    meta = {"architect_word": word, "stream_fingerprint": fp, "rows": n, "scored": len(sc), "slots": slots,
            "db": str(path)}
    held = reserve(meta, no_fetch=no_fetch, echo=echo)
    # from here on, the one run is spent
    params_json = canon_params(v22p, slots["availability_on"], slots["scope"], thin_excluded=thin)
    try:
        w = walk(hist, sc, params_json, slots["visibility"], record=record)
    except (jp.FitRefused, GateRefused) as err:          # 264 item 2(b): the REFUSED line, never a traceback
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}), the walk stopped: "
                           f"{'the fit refused' if isinstance(err, jp.FitRefused) else 'a walk guard refused'}: {err}; "
                           "the reservation stands and the one run is spent (addendum 263 item 13: its only release is "
                           "the architect's ruling on this receipt); nothing recorded") from err
    from src.walters.soccer_backtest import compare_candidate
    from src.walters.training import DEFAULT_PROMOTION_DELTA
    cmp_ = decide(compare_candidate(w["v22"], w["soccer-v23"], DEFAULT_PROMOTION_DELTA),
                  slots["v22_recorded_log_loss"], slots["v22_recorded_source"], DEFAULT_PROMOTION_DELTA)
    out_ = set(thin)
    return {"compare": cmp_, "walk": w, "stream_fingerprint": fp, "rows": n, "slots": slots, "db": str(path),
            "scored_ids": [r.id for r in sc], "v22_poisson": v22p,
            # 263 items 14 and 15: the exclusion set and the off-pyramid arrivals, counted for the record
            "thin_excluded": [list(k) for k in thin], "thin_rows": sum(1 for r in hist if (r.code, r.season) in out_),
            "off_pyramid": list(ar),
            # addendum 254 item 3 Q22: the rows the 90-minute reading touches, counted (admit()'s substitution)
            "aet_pen": {"scored": sum(1 for r in sc if ninety_minute_read(r)),
                        "history": sum(1 for r in hist if ninety_minute_read(r))}}


def ninety_minute_read(r: Row) -> bool:
    """admit()'s substitution, read back from the row: an admitted row whose raw code is not FT (AET / PEN ...) is
    walked and scored at its stored 90-minute score (soccer_expansion.unscoreable admits no non-FT row without one, and
    releases AWD / WO), where live v22 reads the full score."""
    return (r.status_raw or "").strip().upper() not in ("", "FT")


def record_labels(r: dict) -> list[str]:
    """The run record's labels, printed on every verdict and recorded: addendum 254 item 3's two (ARCHITECT 2026-11-04
    15:45 ET: Q4's day-rule residual, never silent (counted only against a chain run time declared in code: none is,
    so the count is said not computed), and Q22's "v22 re-walked" (v22 on this harness, not live v22 reproduced) with
    the AET / PEN rows read at their 90-minute score counted, scored and in the walked history) and addendum 263's
    three (ARCHITECT 2026-11-05 12:50 ET: item 17's tie order "stated in the record"; item 14's thin seasons excluded
    by cause, counted; item 15's arrivals off the declared pyramid, counted)."""
    vis = r["slots"]["visibility"]
    if vis not in SLOT_VALUES["visibility"]:          # unreachable through run(): slots_state refuses it before any load
        raise ValueError(f"visibility {vis!r} is not the day rule addendum 254 item 3 Q4 ruled: no record is labelled "
                         "under it")
    a = r["aet_pen"]
    thin = r["thin_excluded"]
    return [f"  residual (visibility {vis!r}): {DAY_RULE_RESIDUAL}; {DAY_RULE_RESIDUAL_COUNT}",
            f"  {V22_REWALKED_LABEL}; rows read at their 90-minute score (a non-FT raw code: AET / PEN): "
            f"{a['scored']} scored, {a['history']} in the walked history",
            f"  {V22_TIE_ORDER_LABEL}",
            f"  thin seasons excluded by cause (addendum 263 item 14): {len(thin)} competition-season(s), "
            f"{r['thin_rows']} row(s), out of the scored set and soccer-v23's window"
            + (": " + ", ".join(f"{c} {se}" for c, se in thin) if thin else ""),
            f"  arrivals off the declared pyramid (addendum 263 item 15): {len(r['off_pyramid'])}, each priced on the "
            "outside-the-store prior" + (": " + "; ".join(r["off_pyramid"]) if r["off_pyramid"] else "")]


def decide(cmp_: dict, recorded: float, source: str, min_delta: float) -> dict:
    """THE BAR's decision (BAR_TEXT; ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2), the only decision path:
    PASS iff soccer-v23's pot log-loss is at least `min_delta` below BOTH v22's re-walked figure (compare_candidate's
    candidate_gate_verdict on the walk's two arms) AND v22's recorded figure (`recorded`, the declaration slot, never
    recomputed), each decided by soccer_backtest.candidate_gate_verdict; a tie, or any difference under min_delta, on
    either REJECTS. An INVALID comparison stays INVALID. Both figures are carried side by side in the result."""
    from src.walters.soccer_backtest import candidate_gate_verdict
    out = dict(cmp_)
    out.update({"v22_recorded_log_loss": recorded, "v22_recorded_source": source})
    if cmp_["verdict"] == "INVALID":
        return out
    v_rec, d_rec = candidate_gate_verdict(recorded, cmp_["cand_log_loss"], min_delta)
    out.update({"v23_log_loss": cmp_["cand_log_loss"], "v22_rewalked_log_loss": cmp_["prod_log_loss"],
                "verdict_rewalked": cmp_["verdict"], "delta_rewalked": cmp_["delta"],
                "verdict_recorded": v_rec, "delta_recorded": d_rec,
                "verdict": "PASS" if cmp_["verdict"] == "PASS" and v_rec == "PASS" else "REJECT"})
    return out


def run_lines(r: dict) -> list[str]:
    c = r["compare"]
    L = [f"  stream fingerprint {r['stream_fingerprint']} ({r['rows']} rows) · slots "
         f"{json.dumps(r['slots'], sort_keys=True)}"]
    if c["verdict"] == "INVALID":                         # the per-era line on every verdict (253 item 2(d))
        L += availability_lines(r["walk"]["availability"])
        L += record_labels(r)                             # 254 item 3 Q4 / Q22: on every verdict too
        L.append(f"  VERDICT (computed; the architect rules): INVALID — {c['reason']}")
        return L
    L.append(f"  n={c['n']} · soccer-v23 log-loss {c['v23_log_loss']:.6f} · min delta {c['min_delta']} · context "
             "as-of (251 item 2)")
    L.append(f"    against v22 RE-WALKED on this harness: {c['v22_rewalked_log_loss']:.6f} · delta "
             f"{c['delta_rewalked']:+.6f} · {c['verdict_rewalked']}")
    L.append(f"    against v22 RECORDED ({c['v22_recorded_source']}): {c['v22_recorded_log_loss']:.6f} · delta "
             f"{c['delta_recorded']:+.6f} · {c['verdict_recorded']}")
    L.append(f"  RPS {c['prod_rps']:.6f} / {c['cand_rps']:.6f} · Brier {c['prod_brier']:.6f} / {c['cand_brier']:.6f} "
             "(v22 re-walked / soccer-v23; printed for the record; gate nothing)")
    L += strata_lines(r["walk"])
    L += availability_lines(r["walk"]["availability"])
    L += record_labels(r)
    L.append(f"  VERDICT (computed; the architect rules): {c['verdict']}")
    return L


def record(r: dict, word: str) -> dict:
    reg = _reg()
    res = {k: v for k, v in r["compare"].items()}
    res.update({"architect_word": word, "stream_fingerprint": r["stream_fingerprint"], "slots": r["slots"],
                "db": r["db"],
                # 253 item 2(d): the per-era availability line, on the record as on the console (every verdict)
                "availability": availability_lines(r["walk"]["availability"]),
                # 254 item 3 Q4 / Q22: the day rule's residual and "v22 re-walked", labelled, the AET / PEN rows counted;
                # 263 items 14, 15, 17: the thin seasons excluded, the off-pyramid arrivals, the tie order
                "labels": record_labels(r), "aet_pen_rows": dict(r["aet_pen"]),
                "thin_excluded": [list(k) for k in r["thin_excluded"]], "off_pyramid_arrivals": list(r["off_pyramid"])})
    return reg.record_run(EID, list(r["scored_ids"]), res, reg.LEDGER, reg.IDS_DIR)
