"""
F1 — POLICY IN THE EXPORT (architect 2026-09-30, #151; defaults RULED
2026-10-01). A line-for-line Python port of the Cockpit's Desk policy v1.1
(tools/cockpit.html: normalize, kalNormalize/kalFrom*, venueEdge, valueSide,
kSide/joinBidFor/deskCostFor/execEdgePP, kalshiOnlyRef, policy()) — the
single source of truth once parity is proven. Every prediction/fixtures row
gains a `desk` block: the Desk's call, units, tier and reason.

RULED DEFAULTS (ARCHITECT 2026-10-01):
  (1) graded-call counts (postseason / value-shadow / kalshi-only) are a
      PARAMETER, default 0 (the cautious side: postseason plays half units).
      The laptop's ledger summary JSON (Cockpit "Export ledger summary",
      kind bd_ledger_summary_v1) is read when present, so the host's files
      carry real counts after cutover. The doc records which counts it used.
  (2) the Desk is decided AS OF EXPORT TIME, stamped `desk_meta.as_of`.
      T-60 re-export is the doctrine (F2's hourly feed produces it).
  (3) once F1 lands the Cockpit renders desk calls from the file and never
      recomputes policy — after the row-for-row parity verify, with clock
      and counts pinned (scripts/desk_parity_verify.py), and before any
      host chain emits desk calls. Emission is OFF by default until then.

PARITY RULES: arithmetic in the same order as the JS (IEEE doubles both
sides); JS `toFixed` reproduced exactly (`js_fixed`), JS number-to-string
(`js_str`), Math.round (`js_round`). Kickoffs: naive utc_date is UTC (#178).
Presentation-only pieces (KO line, re-run hint, HTML) are not ported.

DESK POLICY v1.2 (ARCHITECT 2026-10-30, addendum 179, #732): the unit is UNIT_FRACTION of the money pool, read once a
day (src/walters/desk_unit.py). The v1.1 rules are unchanged, but the exec gate's fee rounds at the order's own count,
which is now the day's unit's: a borderline row's exec edge, tier and units can differ between a read day and an
unread one (#732 judgement J1, for the architect). The ORDER LINE section holds the rule.
"""
from __future__ import annotations

import io
import json
import math
import os
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# v1.2 (ARCHITECT 2026-10-30 09:30 ET, addendum 179, #732; the operator's ruling of 09:26 ET): THE UNIT BECOMES A
# FRACTION OF THE POOL. Only the unit's size moved; no v1.1 rule changed. The exec gate's fee still rounds at the
# order's own count (#87 v1.1 (h)), now the day's unit's, so a borderline row's tier can follow the read (J1; the
# ORDER LINE section below holds the unit). No dollar figure of any kind is in this module (addendum 179 item 5).
POLICY_VERSION = "v1.2"
INF = math.inf
POLICY = {
    "SOCCER": {"eMin": 4, "eLad": 10, "eHair": 10, "pMin": 0.50, "qNever": False},
    "NFL": {"eMin": 4, "eLad": INF, "eHair": 15, "pMin": 0, "qNever": True},
    "MLB": {"eMin": 4, "eLad": INF, "eHair": 15, "pMin": 0, "qNever": False},
    "NHL": {"passAll": True},
    # INTL DESK POLICY v0 (ARCHITECT 2026-10-07, pre-declared; effective only on CONFIRMED): "(1) A new POLICY
    # block INTL = the SOCCER block (eMin 4, eLad 10, eHair 10, pMin 0.50) with qNever true". DARK: only a
    # production intl export (src/walters/intl_production.py, refused until registry.production_allowed(
    # "intl-elo-v2")) carries sport "intl"; no other file reaches this block.
    "INTL": {"eMin": 4, "eLad": 10, "eHair": 10, "pMin": 0.50, "qNever": True},
    "DEFAULT": {"eMin": 4, "eLad": INF, "eHair": 15, "pMin": 0, "qNever": False},
}
BASE_UNITS = 1
VENUE = {"minBooks": 4, "minDivPP": 5.0, "units": 0.25, "staleGapPP": 8.0,
         "maxBookAgeH": 3}       # #91 RULED 2026-10-02: an older book capture is NO reference
VALUE = {"units": 0.25, "reviewN": 30}
K2 = {"feeClearsPP": 4, "tick": 0.01, "joinMinSpreadC": 3}
# ARCHITECT 2026-10-06: an exact 4.00pp exec edge CLEARS. Binary-float subtraction can land a hair
# below ((0.35 - 0.31) * 100 = 3.9999999999999982), so the comparison allows this tolerance
# (the same one k-track-receipt uses; the Cockpit's marker carries it too).
FEE_CLEAR_EPS = 1e-9
# #87 EXECUTABLE EDGE — v1.1 ADDENDUM (ARCHITECT-RULE 2026-10-06, effective next slate):
#   (1) cost = ask + taker fee (0.07·M·P(1−P), nearest cent per fill): the spread is not the cost, the fee is.
#   (2) default execution TAKES at the ask; join-bid only when the spread is >= 3c (join-bid of 09-30 superseded).
#   (3) exec edge = model_p − cost; a PLAY gets full tier units only at exec edge >= 4pp, else HALF units.
#   (4) venue: the 5pp fair threshold stands AND the exec edge (book fair − cost) must clear 4pp.
#   (5) parlay legs are priced at executable cost; the independence-estimate label stands.
# The frozen pre-F1c golden (tests/golden/desk_js_v1_1.json.gz) predates the addendum: the battery checks it
# with the addendum OFF (`base_v11()`), proving every other v1.1 behaviour unchanged; the addendum has its
# own tests (tests/test_desk_exec_addendum.py).
EXEC_RULES = {"on": True}
# STARTED (ARCHITECT 2026-10-06, #313): "a started game is never a new call" (#49 (b)) is enforced IN THE FILE. A
# model-sport row whose kickoff is at or before desk as_of is PASS / started: units 0, no order, no value shadow,
# never a parlay leg. The pre-kickoff file and the ledger stay the record of the call. An unknown kickoff is
# unchanged (never guessed). Its own switch: the frozen golden (pre-F1c) predates it and runs with it off.
STARTED_RULE = {"on": True}
# MLB BIG-EDGE QUARANTINE (ARCHITECT 2026-10-07, effective with the 2026-10-07 slate): "an MLB row whose edge against
# its reference is above 8pp is QUARANTINED: never a straight play, logged as a quarantine shadow at the size it
# would have staked (the NFL contract, at 8pp for MLB). The MLB 15pp caution tier is superseded. The 4pp floor and
# the rest of v1.1 stand." The edge is the Desk's own (model pick p − its reference: the book fair, or the
# kalshi-only mid), so both references quarantine alike. Exactly 8.00pp plays (the tolerance keeps binary-float
# subtraction noise from tipping an exact 8.00 over). Its own switch: the frozen golden predates it (base_v11()).
MLB_QUARANTINE = {"on": True, "abovePP": 8.0}
MLB_QUARANTINE_EPS = 1e-9
MLB_QUARANTINE_RULING = "MLB big-edge quarantine, ARCHITECT 2026-10-07"
STARTED_REASON = "started - never a new call"
# INTL DESK POLICY v0 (ARCHITECT 2026-10-07) rules (2)-(6): "(2) Half units until 30 INTL calls are graded.
# (3) A row is never a call when its venue flag is unknown and its listed home side is on the home-abroad list;
# that list is ruled by name from the receipt in (c). (4) UNL only: CNL has no wired Kalshi series, so CNL rows
# are predictions without a call. (5) UNL stays ineligible for venue-edge until the skew test (#286) is read.
# (6) First review at 30 graded calls; no threshold moves before it."
#   (5) needs no code: venue_edge never prices a model row, and a market-only UNL fixture reads "single venue".
#   The graded count is `intl_graded` in the ledger summary; absent = 0 (cautious: half units).
INTL = {"callComps": ("UNL",), "halfUntilGraded": 30, "reviewN": 30}
# (3) The home-abroad list is ruled BY NAME from `intl-home-abroad-receipt`. Names are the export's home_team strings.
# RULED (ARCHITECT 2026-10-23, addendum 160 item 1, from the receipt logs/home-abroad-2026-10-23.md, run
# 2026-10-23T17:09:58Z), verbatim: "INTL_HOME_ABROAD = {"Ukraine", "Belarus", "Israel"}. Evidence: Ukraine 14 of 15
# known venues abroad (Poland 7, Slovakia 3, Czechia 2, Germany 2); Belarus 16 of 18 (Hungary 12, Serbia 4); Israel 6
# of 12, every abroad game in one host country (Hungary 6) — listed on the single-host pattern, not the share. The rule
# for later windows: a UNL member enters at 10 or more known venues and 75% or more abroad, OR a single-host pattern
# (every abroad game in one country, 6 or more); never on fewer than 6 known; re-read at each confirmation window from
# a fresh receipt. Kosovo (0 of 9) and Russia (0 of 8, suspended) are not listed. Non-UNL teams [...] are not listed:
# the INTL policy calls UNL only. [...] semantics unchanged: unknown venue + listed home on the list = never a call."
INTL_HOME_ABROAD: frozenset = frozenset({"Ukraine", "Belarus", "Israel"})
INTL_COUNT_KEY = "intl_graded"
# soccer-expansion-v1 (ARCHITECT 2026-10-07): "A pinned series never makes a league live." Their Kalshi series are
# captured (deploy/hosting/chains.py KALSHI_CAPTURE_ONLY) and the window card spans every competition, so the venue
# engine never makes a call on them (Codex on #326). CI pins this set to soccer_expansion.LEAGUES.
SHADOW_VENUE_COMPS = frozenset({"PD", "SA", "BL1", "FL1", "ELC"})
# CL (ARCHITECT 2026-10-13 13:11 ET, addendum 61 item 3(1), #498), verbatim: "'No call' in addendum 58 covers the venue
# engine. CL is a three-way Kalshi soccer market, as UNL is, and it stays out of venue-edge on UNL's ground (INTL policy
# v0, rule 5): until the skew test (#286) is read and I rule on it. Its stop reads 'three-way soccer — no venue call
# before the skew test is read (CL)'. The charter's 'cups when priced' waits on that same ruling."
SKEW_TEST_VENUE_COMPS = ("CL",)
SKEW_TEST_VENUE_REASON = "three-way soccer — no venue call before the skew test is read ({})"
# Its own switch: the frozen golden (pre-F1c) predates it and runs with it off (base_v11()), as the quote-age rule does.
SKEW_TEST_VENUE_RULE = {"on": True}
# S1 (ARCHITECT 2026-10-08, addendum 9 item 1): the same set keys the MODEL path. "desk_call returns PASS for a model
# row whose competition is in the set: reason 'shadow league: never a call until CONFIRMED', no order, no value
# shadow. A league leaves the set only in a reviewed PR after CONFIRMED, by ruling." (predict / export-predictions
# refuse these competitions too: cli.py _refuse_shadow_league.) No switch: no frozen golden row is in the set.
SHADOW_LEAGUE_REASON = "shadow league: never a call until CONFIRMED"
SHADOW_LEAGUE_KIND = "shadow_league"
# MLB KALSHI-ONLY SUSPENSION (ARCHITECT 2026-10-08, addendum 13 item 2, Q3, RULED): "K1. An MLB row is never a call on
# a kalshi-only reference. Where the 2026-10-01 rule would have taken the Kalshi mid as the reference, the row is PASS
# with no reference: units 0, no order, no shadow units. Reason on the row: 'kalshi-only suspended for MLB: the model
# number is unblended without books (ARCHITECT 2026-10-07)'. [...] K3. For the record such a row carries a
# kalshi_only_hold block: the mid, bid, ask and spread, the raw edge (model number minus mid), the edge on equal
# footing (half the raw edge), and the call and units the 2026-10-01 rule would have given. Nothing reads the block
# as a call. K4. NFL and PL keep the kalshi-only reference exactly as ruled on 2026-10-01 [...]. MLB rows no longer
# add to the 30-call review count. K5. MLB kalshi-only reopens only by ruling, on a receipt."
# The would-be call is the pre-K1 path itself (_desk_call), never a copy. Its own switch: the frozen golden (pre-F1c)
# predates it and runs with it off (base_v11()); addendum_off() holds it, as it holds the quarantine (#328).
KALSHI_ONLY_MLB_SUSPENDED = {"on": True}
KALSHI_ONLY_SUSPENDED_KIND = "kalshi_only_suspended"
KALSHI_ONLY_SUSPENDED_REASON = ("kalshi-only suspended for MLB: the model number is unblended without books "
                                "(ARCHITECT 2026-10-07)")
# DEFAULT RATING (ARCHITECT 2026-10-10, addendum 36 item 2, RULED): "Every soccer prediction says, for each side,
# where its rating came from: the model's table, or the default because the team is not in the table. It is
# recorded per side as model or default, in the prediction's factor_breakdown and in the export's input_quality. A
# row with a default on either side gets no Desk call and no value shadow: it is a PASS, and its reason names the
# team. desk_meta says the rule is on. No probability changes." Read from input_quality.rating_source; a row without
# the label (other sports, or a prediction written before it) is unchanged. Checked after the started rule. Its own
# switch; the frozen golden predates the label (no golden row carries it), so it holds with the rule on.
DEFAULT_RATING_RULE = {"on": True}
DEFAULT_RATING_KIND = "default_rating"
DEFAULT_RATING_RULING = "default rating, ARCHITECT 2026-10-10"
# A ONE-SIDED INJURY LIST GETS NO CALL (ARCHITECT 2026-10-11, addendum 40 item 6, RULED): "A soccer row says, for
# each side, how many names are listed and when that team's list was last written. Where one side's list is empty
# and the other's is not, the row gets no Desk call and no value shadow: it is a PASS, and its reason names the
# team. desk_meta says the rule is on. No probability changes." Read from input_quality.injuries.<side>.count; both
# empty is not one-sided (the model's number then carries no injury term, as the gated model's does). A row without
# the counts (an older file, the frozen golden's rows) is unchanged. Built as addendum 36's default_rating is.
INJURIES_ONE_SIDED_RULE = {"on": True}
INJURIES_ONE_SIDED_KIND = "injuries_one_sided"
INJURIES_ONE_SIDED_RULING = "one-sided injury list, ARCHITECT 2026-10-11"
# AN EMPTY NFL INJURY LIST IS UNREAD (ARCHITECT 2026-10-11, addendum 40 item 4, RULED): "An NFL team with no stored
# injury row is a list we could not read, not a team with nobody hurt. A flag we could not look up is not a flag that
# is off (addendum 23, A2). Where either team's list is empty, the Desk sizes an NFL PLAY as it sizes a QB-flagged
# one: half units, and the reason names the team." Read from input_quality.injuries.<side>.count (0 = empty); a row
# without the count (other sports, an older file, the frozen golden's rows) is unchanged. "Nothing else changes: [...]
# a quarantine or a PASS is untouched, and no shadow is resized." POLICY_VERSION stays v1.1: v1.1's QB rule read under
# law 4. Its own switch and its own desk_meta line, as addendum 36's rule has.
INJURY_EMPTY_RULE = {"on": True}
INJURY_EMPTY_TAG = "QB unread half units"
# A STORED KICKOFF THE MARKET'S CLOCK DISPUTES GETS NO CALL (ARCHITECT 2026-10-15 08:46 ET, addendum 72 item 1, RULED,
# law 4): "a row whose stored kickoff and Kalshi clock disagree by more than MAX_TICK_DRIFT (2h, kalshi_match.py:79 —
# the matcher's own threshold, read it, do not add a second one) gets NO Desk call: PASS, units 0, no order, no value
# shadow, a new no-call kind in NO_CALL_KINDS with the reason naming both clocks ("stored kickoff 2026-10-15 13:00 ET
# vs Kalshi's clock 18:00 ET: no call"). The clock is read from the leg's own ticker (the MLB shape carries it; a
# shape without a clock is not compared and nothing changes). The closing file carries the kind and both clocks".
# The ticker's clock is the matcher's own (kalshi_match.ticker_stamp); every leg with a ticker is read, and any one at
# or past the threshold holds the row. Checked after S1 and before the started rule: a started test reads the stored
# kickoff, the clock this rule disputes. The row's desk block carries both clocks (`kickoff_clock`). Its own switch and
# desk_meta line; the frozen golden runs with it off (base_v11()).
# THE DESK'S OWN THRESHOLD (ARCHITECT 2026-10-16 09:22 ET, addendum 83 item 2, RULED, superseding addendum 72's "read
# it, do not add a second one" for the Desk): "the Desk's own threshold is ONE HOUR, its own constant (DESK_CLOCK_DRIFT
# = 1h in desk_policy; the matcher's MAX_TICK_DRIFT stays 2h for placement, which is a different question), inclusive:
# a stored kickoff and a leg's ticker clock at or more than 60 minutes apart hold the row. Today's 50548 (8pm vs 6pm)
# then holds; yesterday's 50546 (1pm vs 6pm) holds; 50547 (8pm vs 8pm) does not."
KICKOFF_CLOCK_RULE = {"on": True}
KICKOFF_CLOCK_KIND = "kickoff_clock"
DESK_CLOCK_DRIFT = timedelta(hours=1)
# THE HOST FENCE (ARCHITECT 2026-10-17 10:15 ET, addendum 109 item 3, RULED; #410; it codifies addendum 36 item 3):
# "when the writer-of-record role is host, every soccer model_edge row is PASS, pass_kind "host_fence", reason "host:
# ratings keyed to the laptop's team ids (#410); the cutover replaces this database". rating_source is untouched; the
# row's model numbers stay in the file for the compare. The host pager never sees a soccer PLAY from the host. [...] The
# fence lifts with the cutover (the ruling that cuts over names it). No re-keying on the host (addendum 36 stands)."
# THE ROLE (ARCHITECT 2026-10-17, addendum 110 item 1, RULED): "the fence keys off the machine's own role,
# SP_EXPORTS_MIRROR_ROLE=host (addendum 45 P1), not SP_WRITER_OF_RECORD, which reads laptop on both machines until the
# cutover flips it. Lift through a named switch the cutover PR turns off. ONE FLIP (law 4, conservative unknowns): an
# unknown or missing role is FENCED, not open. A machine that cannot say it is the laptop does not get to make a soccer
# call." Addendum 114 item 3: "the cutover PR does the flip and turns the switch off in the same change; the fence
# reads the switch, never SP_WRITER_OF_RECORD." Only an exact "laptop" leaves the row as it is; "host", unset and any
# other value fence, each with its own reason (a value that is neither host nor laptop: addendum 115 item 3b's words). The role is read by machine_role(): the machine's own
# host.env, then the process environment, then the checkout's .env. Checked first, before S1: it overrides every call.
# It lifts by this switch, HOST_FENCE_RULE. The frozen golden predates it and runs with it off (base_v11()).
# LIFTED by this PR (#671), ARCHITECT 2026-10-25, addendum 166 items 4(ii) and 6(A) ("THE CUTOVER POLICY PR [...]
# `HOST_FENCE_RULE = {"on": False}` in src/walters/desk_policy.py and nothing else in that module"): the switch is off,
# so a machine's role no longer changes a soccer (or INTL) call. The machinery (host_fenced, machine_role, the
# reasons, host_fence_rule_off, base_v11) is unchanged and reads the switch.
HOST_FENCE_RULE = {"on": False}
HOST_FENCE_KIND = "host_fence"
# Addendum 115 item 3a: "INTL rows ARE fenced under role host. The ruling's "soccer" means every model-edge row of the
# soccer family whose ratings are keyed to the laptop's team ids — intl-elo is copied the same way."
HOST_FENCE_SPORTS = ("SOCCER", "INTL")
HOST_FENCE_REASON = "host: ratings keyed to the laptop's team ids (#410); the cutover replaces this database"
ROLE_ENV = "SP_EXPORTS_MIRROR_ROLE"                 # deploy/hosting/closing.py ROLE_SETTING; host.env / the laptop's .env
ROLES = ("host", "laptop")
HOST_FENCE_UNSET_REASON = f"host fence: role unknown ({ROLE_ENV} unset)"     # addendum 110 item 1, verbatim
# Addendum 116 item 2 (law 4): "a host.env that EXISTS but cannot be read makes the role UNKNOWN — fenced, reason "host
# fence: role unknown (host.env unreadable)" — and nothing after it is consulted. Only a host.env that does not exist
# (the laptop) falls through to the environment and the checkout's .env."
HOST_FENCE_UNREADABLE_REASON = "host fence: role unknown (host.env unreadable)"   # addendum 116 item 2, verbatim
HOST_ENV_UNREADABLE = object()                       # _env_file(strict=True)'s answer for a file it cannot read
HOST_ENV_DEFAULT = "/etc/sports-predictor/host.env"  # deploy/hosting/sp_common.py HOST_ENV; SP_HOST_ENV overrides it
# The checkout's .env, the one config.py loads (PROJECT_ROOT = the directory holding config.py, two above this file;
# load_dotenv(PROJECT_ROOT / ".env")); sp_common._dotenv reads the same file (REPO / ".env"). tests/conftest.py points
# it at a file that does not exist.
DOTENV = Path(__file__).resolve().parents[2] / ".env"
NO_CALL_KINDS = ("started", SHADOW_LEAGUE_KIND,    # PASS rows with no order, no exec block, no value shadow
                 "no_series", "venue_unknown",      # + INTL v0 rules (4) and (3) (#325)
                 KALSHI_ONLY_SUSPENDED_KIND,        # + Q3 K1 (2026-10-08)
                 DEFAULT_RATING_KIND,               # + addendum 36 item 2 (2026-10-10)
                 INJURIES_ONE_SIDED_KIND,           # + addendum 40 item 6 (2026-10-11)
                 KICKOFF_CLOCK_KIND,                # + addendum 72 item 1 (2026-10-15)
                 HOST_FENCE_KIND)                   # + addendum 109 item 3 (2026-10-17)
# VENUE-EDGE: QUOTE AGE (ARCHITECT 2026-10-07, addendum 4 E, gate-class): "#91 means the age of the QUOTE. A fetch
# time is not a quote age; where the quote's own time is not known the age is UNKNOWN, and the ratified rule for
# unknown age is NO REFERENCE. [...] In code, from the next tag: venue-edge emits no call (PASS, noref, 'book quote
# age unknown: no reference') and the venue block keeps its numbers for the record. [...] The engine resumes only
# when a quote time is stored and #91 is applied to it, by ruling." No quote time is stored, so EVERY row the engine
# computes (side + divergence measured) is held: PASS / noref with this reason, units 0, no order, its numbers kept,
# its would-be verdict recorded under the venue block's `quote_age_hold`. PRECEDENCE: rows that stop BEFORE the
# computation keep their own reason (model charter, UNL, in-play, single venue — no pair, book capture unknown /
# after decision / older than 3h, books < 4): each is already a no-call by its own rule. Its own switch: the frozen
# golden (pre-F1c) predates it and runs with it off (base_v11()).
QUOTE_AGE_RULE = {"on": True}
QUOTE_AGE_REASON = "book quote age unknown: no reference"
PARLAY_LABEL = "independence estimate: Π of single-game prices (legs assumed uncorrelated)"
PASSCLASS = {"minBooks": 3, "rerunMin": 60}
POSTSEASON = {"reviewN": 30}
KALSHI_ONLY = {"maxSpreadC": 2, "sizeMult": 0.5, "reviewN": 30,
               "series": {"MLB": "KXMLBGAME", "NFL": "KXNFLGAME", "PL": "KXEPLGAME"}}
SUMMARY_KIND = "bd_ledger_summary_v1"
COUNT_KEYS = ("postseason_graded", "value_shadow_graded", "kalshi_only_graded")
MISSING = object()          # JS `undefined` where the JS distinguishes it from null


# ----------------------------------------------------------- JS semantics --

def js_fixed(x: float, d: int) -> str:
    """Number.prototype.toFixed: the exact binary value, ties away from zero."""
    if x != x:
        return "NaN"
    neg = x < 0                                   # -0.0 is not < 0: prints "0.0" like JS
    q = Decimal(abs(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return ("-" if neg else "") + format(q, "f")


def js_str(x) -> str:
    """`${number}` for the values the Desk prints (finite, moderate)."""
    if x is None:
        return "null"
    if x is MISSING:
        return "undefined"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if x == INF:
            return "Infinity"
        if x.is_integer():
            return str(int(x))
        return repr(x)
    return str(x)


def js_round(x: float) -> int:
    """Math.round: half toward +infinity."""
    return math.floor(x + 0.5)


def nn(v) -> bool:
    """JS `v != null` (null and undefined are both null-ish)."""
    return v is not None and v is not MISSING


def utc_ms(s) -> float:
    """The Cockpit's utcMs (#178): naive date-times are UTC. NaN when unparseable."""
    if not s or not isinstance(s, str):
        return math.nan
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return math.nan
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return float((dt - datetime(1970, 1, 1, tzinfo=timezone.utc)) // _MS)


_MS = timedelta(milliseconds=1)


def _t(n):
    return n[:16] + "…" if n and len(n) > 18 else n


# --------------------------------------------------------------- normalize --

def kal_normalize(raw, need_draw):
    if not raw:
        return None
    sides = ["HOME", "DRAW", "AWAY"] if need_draw else ["HOME", "AWAY"]
    for k in sides:
        v = raw.get(k)
        if v is None or not (isinstance(v, (int, float)) and v >= 0):
            return None
    tot = 0
    for k in sides:
        tot = tot + raw[k]
    if not tot > 0:
        return None
    return {k: raw[k] / tot for k in sides}


def kal_from_fixture(k, fair):
    if not k or k.get("status") != "two_sided":
        return None
    prob = k.get("prob")
    need = bool(fair and fair.get("DRAW") is not None) or bool(prob and prob.get("DRAW") is not None)
    return kal_normalize(prob, need)


def kal_from_prediction(p, mk, fair):
    if p.get("kalshi_prob") is not None:
        h = float(p["kalshi_prob"])
        return {"HOME": h, "AWAY": 1 - h}
    k = mk.get("kalshi") if mk else None
    if k and k.get("normalized") and k.get("prob"):
        return kal_normalize(k["prob"], bool(fair is not None and fair.get("DRAW") is not None))
    return None


def _qn(v):
    return None if v is None else v


def _kexec_of(p: dict, always: bool = False):
    """The row's own K-track quote fields. Fixtures rows (market-only) carry them too (`_fixture_row`); before
    the #87 addendum the venue engine never read them, so a fixtures row without any stays None."""
    k = {"bid": p.get("kalshi_bid"), "ask": p.get("kalshi_ask"), "cost": p.get("exec_cost_taker"),
         "maker": p.get("exec_cost_maker"), "bidAway": p.get("away_bid"), "askAway": p.get("away_ask"),
         "costAway": p.get("exec_cost_taker_away"), "makerAway": p.get("exec_cost_maker_away")}
    return k if always or any(v is not None for v in k.values()) else None


def normalize(doc: dict) -> list[dict]:
    """The Cockpit's normalize(doc): the rows the Desk sees, in file order.
    Each row keeps `src` = the export row it came from (to attach the desk)."""
    out = []
    if doc.get("engine") == "model_shadow":       # NHL shadow: never a Desk input (the Cockpit skips it)
        return out
    # JS truthiness: [] and {} are TRUTHY; only null/undefined (None/absent) are not
    if doc.get("predictions") is None and doc.get("fixtures") is not None:
        sport = (doc.get("sport") or doc.get("competition") or doc.get("competition_code") or "?").upper()
        for f in doc["fixtures"]:
            if f.get("status") and f.get("status") != "scheduled":
                continue
            mk = f.get("market") or {}
            fair = mk.get("fair_prob") or {}
            out.append({"src": f, "game": f"{_t(f.get('away_team') or '?')} @ {_t(f.get('home_team') or '?')}",
                        "home": f.get("home_team") or "?", "away": f.get("away_team") or "?",
                        "pick": None, "prob": None, "mkt": None, "twoSided": False,
                        "mktHasDraw": fair.get("DRAW") is not None,
                        "kal": (f.get("input_quality") or {}).get("kalshi") or None, "sport": sport,
                        "utc": f.get("utc_date") or "", "probsAll": {}, "fairAll": fair, "div": None,
                        "quar": False, "books": mk.get("bookmaker_count"), "booksAt": mk.get("captured_at"),
                        "qbs": [], "marketOnly": True,
                        "tier": None, "kalProb": kal_from_fixture(f.get("kalshi"), fair),
                        "threeWay": fair.get("DRAW") is not None, "stage": MISSING, "comp": "",
                        "kExec": _kexec_of(f)})
        return out
    sport = (doc.get("sport") or "?").upper()
    for p in doc.get("predictions") or []:
        home, away = p.get("home_team") or "?", p.get("away_team") or "?"
        pr = p.get("prediction") or {}
        probs = None
        if pr.get("probabilities") is not None:
            pp = pr["probabilities"]
            probs = {"HOME": pp.get("home_win"), "DRAW": _qn(pp.get("draw")), "AWAY": pp.get("away_win")}
        elif pr.get("home_win_prob") is not None:
            probs = {"HOME": pr["home_win_prob"], "DRAW": None, "AWAY": 1 - pr["home_win_prob"]}
        if not probs:
            continue
        mk = p.get("market") or {}
        market = {}
        if mk.get("selections") is not None:
            for k, v in mk["selections"].items():
                market[k] = v["fair_prob"] if v and v.get("fair_prob") is not None else None
        elif mk.get("fair_prob") is not None:
            market = dict(mk["fair_prob"])
        pick, best = "HOME", -1
        for k in ("HOME", "DRAW", "AWAY"):
            if probs.get(k) is not None and probs[k] > best:
                best, pick = probs[k], k
        inj = (p.get("input_quality") or {}).get("injuries") or {}
        qbs = list(((inj.get("home") or {}).get("qb_listed")) or []) + \
            list(((inj.get("away") or {}).get("qb_listed")) or [])
        # addendum 40 item 4: the teams whose stored injury list is empty (count 0); a side without a count: unknown
        inj_empty = [home if sd == "home" else away for sd in ("home", "away")
                     if isinstance(inj.get(sd), dict) and inj[sd].get("count") == 0]
        out.append({
            "src": p, "game": f"{_t(away)} @ {_t(home)}", "home": home, "away": away,
            "pick": pick, "prob": best, "mkt": market.get(pick),
            "twoSided": market.get("HOME") is not None and market.get("AWAY") is not None,
            "mktHasDraw": market.get("DRAW") is not None,
            "kal": (p.get("input_quality") or {}).get("kalshi") or None, "sport": sport,
            "utc": p.get("utc_date") or "", "probsAll": probs, "fairAll": market,
            "div": p.get("market_divergence_pp"), "quar": bool(p.get("quarantine")),
            "books": mk.get("bookmaker_count"), "qbs": qbs, "injEmpty": inj_empty,
            "stage": p["stage"] if "stage" in p else MISSING,
            "comp": (p.get("competition") or doc.get("sport") or "").upper(),
            "kalProb": kal_from_prediction(p, mk, market),
            "threeWay": market.get("DRAW") is not None or probs.get("DRAW") is not None,
            "kExec": _kexec_of(p, always=True),     # #130: the pre-split alias is retired
            # addendum 36 item 2: {"home": "model"|"default"|None, "away": ...} or None (no label)
            "ratingSrc": (p.get("input_quality") or {}).get("rating_source"),
            # addendum 40 item 6: {"home": {"count", "synced_at"}, "away": {...}} or None (an older row)
            "injSides": (p.get("input_quality") or {}).get("injuries"),
            "tier": pr.get("tier") or None, "marketOnly": False})
    return out


def side_name(r, k):
    return r["home"] if k == "HOME" else r["away"] if k == "AWAY" else "Draw"


# ------------------------------------------------------------ venue engine --

def venue_edge(r, now_ms: float) -> dict:
    out = _venue_edge(r, now_ms)
    if QUOTE_AGE_RULE["on"] and out["side"] is not None:
        # the engine measured a pair (side + divergence): held — no quote time is stored (ARCHITECT 2026-10-07)
        out["held"] = {"eligible": out["eligible"], "kind": out["kind"], "reason": out["reason"]}
        out.update(eligible=False, kind="noref", reason=QUOTE_AGE_REASON)
    return out


def _venue_edge(r, now_ms: float) -> dict:
    out = {"eligible": False, "reason": "", "side": None, "divPP": None, "bookP": None, "kalP": None,
           "sides": {}, "kind": None}
    if not r["marketOnly"]:
        out["reason"] = "model sport — model_edge only (venue charter: market-only family)"
        return out
    if r["sport"] == "UNL":
        out["reason"] = "single venue — no pair (UNL)"
        return out
    cl = next((c for c in SKEW_TEST_VENUE_COMPS if c in (r["sport"], r.get("comp") or "")), None)
    if cl and SKEW_TEST_VENUE_RULE["on"]:                                         # addendum 61 item 3(1): on UNL's ground, until the skew test is read
        out["reason"] = SKEW_TEST_VENUE_REASON.format(cl)
        return out
    if r["sport"] in SHADOW_VENUE_COMPS or (r.get("comp") or "") in SHADOW_VENUE_COMPS:
        out["reason"] = (f"shadow league ({r.get('comp') or r['sport']}, soccer-expansion-v1): Kalshi captured for the "
                         "record only — never a venue call until CONFIRMED")
        return out
    if r["utc"] and utc_ms(r["utc"]) <= now_ms:
        out["reason"] = "in-play — never"
        return out
    fair = r["fairAll"] or {}
    books = r["books"] or 0
    has_book = books > 0 and fair.get("HOME") is not None and fair.get("AWAY") is not None
    if not has_book or not r["kalProb"]:
        out.update(reason="single venue — no pair", kind="noref")
        return out
    # #91 RULED (ARCHITECT 2026-10-02): "a venue-edge row whose book capture is
    # older than 3h at decision time has NO reference (not stale-flagged,
    # excluded) — same PASS/no-ref class as absent books." Decision time = the
    # Desk's as-of (now_ms). Review on #250: a capture AFTER the decision time
    # was not available then -> no reference. UNKNOWN age (missing or
    # unparseable captured_at) -> no reference too. ARCHITECT 2026-10-02:
    # "UNKNOWN capture age = NO REFERENCE — ratified, no longer provisional."
    cap_ms = utc_ms(r.get("booksAt"))
    if math.isnan(cap_ms):
        out.update(reason="book capture time unknown — no reference", kind="noref")
        return out
    if cap_ms > now_ms:
        out.update(reason="book capture after decision time — unavailable, no reference", kind="noref")
        return out
    age_ms = now_ms - cap_ms
    if age_ms > VENUE["maxBookAgeH"] * 3600000:
        out.update(reason=f"books captured {js_fixed(age_ms / 3600000, 1)}h ago > {VENUE['maxBookAgeH']}h"
                          " — no reference", kind="noref")
        return out
    if books < VENUE["minBooks"]:
        out.update(reason=f"books {js_str(r['books'])} < {VENUE['minBooks']} — pair too thin", kind="noref")
        return out
    best = None
    for k in r["kalProb"]:
        if fair.get(k) is None:
            continue
        d = (fair[k] - r["kalProb"][k]) * 100
        out["sides"][k] = d
        if best is None or d > best[1]:
            best = (k, d)
    if not best:
        out.update(reason="single venue — no pair", kind="noref")
        return out
    out.update(side=best[0], divPP=best[1], bookP=fair[best[0]], kalP=r["kalProb"][best[0]])
    if best[1] >= VENUE["minDivPP"]:
        out["eligible"] = True
        out["reason"] = (f"books {js_fixed(out['bookP'] * 100, 1)}% vs Kalshi {js_fixed(out['kalP'] * 100, 1)}%"
                         f" → Kalshi underprices by {js_fixed(best[1], 1)}pp")
        if EXEC_RULES["on"]:
            # #87 v1.1 (4): the 5pp fair threshold stands AND exec edge = book fair − (ask + taker fee) >= 4pp.
            # (i) RULED 2026-10-06: the engine backs the best side (largest fair divergence) among the sides that
            # clear BOTH gates; when none does, the largest-divergence side is reported with its PASS reason.
            both = []
            for k, d in out["sides"].items():
                if d >= VENUE["minDivPP"]:
                    ck = taker_cost_for(r, k, VENUE["units"])
                    if ck is not None and exec_clears((fair[k] - ck) * 100):
                        both.append((d, k))
            if both:
                d, k = max(both)
                best = (k, d)
                out.update(side=k, divPP=d, bookP=fair[k], kalP=r["kalProb"][k])
                out["reason"] = (f"books {js_fixed(out['bookP'] * 100, 1)}% vs Kalshi "
                                 f"{js_fixed(out['kalP'] * 100, 1)}% → Kalshi underprices by {js_fixed(d, 1)}pp")
            cost = taker_cost_for(r, best[0], VENUE["units"])
            out["execCost"] = cost
            out["execPP"] = None if cost is None else (out["bookP"] - cost) * 100
            if cost is None:
                out.update(eligible=False, kind="noref",
                           reason=out["reason"] + " · no executable quote (ask + taker fee) — PASS")
            elif not exec_clears(out["execPP"]):
                out.update(eligible=False, kind="floor",
                           reason=out["reason"] + f" · exec edge {js_fixed(out['execPP'], 1)}pp < "
                                                  f"{K2['feeClearsPP']}pp at ask + taker fee {js_fixed(cost, 3)}"
                                                  " — PASS")
            else:
                out["reason"] += f" · exec edge {js_fixed(out['execPP'], 1)}pp ≥ {K2['feeClearsPP']}pp"
    else:
        out["reason"] = f"max divergence {js_fixed(best[1], 1)}pp < {js_str(VENUE['minDivPP'])}pp"
        out["kind"] = "floor"
    return out


# ------------------------------------------------------- exec (K2 / #89 / #93) --

def k_side(r, side):
    k = r.get("kExec")
    if not k:
        return None
    if side == "HOME":
        return {"bid": k["bid"], "ask": k["ask"], "cost": k["cost"], "maker": k["maker"], "no": False}
    if side == "AWAY" and not r["threeWay"] and (k["costAway"] is not None or k["makerAway"] is not None):
        return {"bid": k["bidAway"], "ask": k["askAway"], "cost": k["costAway"], "maker": k["makerAway"], "no": True}
    return None


@contextmanager
def base_v11():
    """The Desk WITHOUT the #87 addendum: the frozen pre-F1c golden's policy (the parity battery only)."""
    was, was_started = EXEC_RULES["on"], STARTED_RULE["on"]
    was_mlbq, was_qa = MLB_QUARANTINE["on"], QUOTE_AGE_RULE["on"]
    was_kos = KALSHI_ONLY_MLB_SUSPENDED["on"]
    was_one = INJURIES_ONE_SIDED_RULE["on"]    # frozen verification files stay frozen (as Codex asked on #434)
    was_inj = INJURY_EMPTY_RULE["on"]          # Codex on #434: frozen verification files stay frozen
    was_skew = SKEW_TEST_VENUE_RULE["on"]      # addendum 61 item 3(1) postdates the frozen battery's CL rows
    was_clock = KICKOFF_CLOCK_RULE["on"]       # addendum 72 item 1: frozen verification files stay frozen
    was_fence = HOST_FENCE_RULE["on"]          # addendum 109 item 3: the golden holds whatever the machine's role
    EXEC_RULES["on"] = STARTED_RULE["on"] = MLB_QUARANTINE["on"] = QUOTE_AGE_RULE["on"] = False
    KALSHI_ONLY_MLB_SUSPENDED["on"] = INJURIES_ONE_SIDED_RULE["on"] = INJURY_EMPTY_RULE["on"] = False
    SKEW_TEST_VENUE_RULE["on"] = KICKOFF_CLOCK_RULE["on"] = HOST_FENCE_RULE["on"] = False
    try:
        yield
    finally:
        EXEC_RULES["on"], STARTED_RULE["on"] = was, was_started
        MLB_QUARANTINE["on"], QUOTE_AGE_RULE["on"] = was_mlbq, was_qa
        KALSHI_ONLY_MLB_SUSPENDED["on"], INJURIES_ONE_SIDED_RULE["on"] = was_kos, was_one
        INJURY_EMPTY_RULE["on"], SKEW_TEST_VENUE_RULE["on"] = was_inj, was_skew
        KICKOFF_CLOCK_RULE["on"], HOST_FENCE_RULE["on"] = was_clock, was_fence


@contextmanager
def addendum_off():
    """The Desk without the #87 addendum and the started rule, with every OTHER policy switch held as it is —
    desk-rescore's "before" side (Codex on #328: base_v11() also turns MLB_QUARANTINE off, so a quarantined
    >8pp MLB row read as "halved by #87"). base_v11() itself is unchanged: the golden battery's policy."""
    was, was_started = EXEC_RULES["on"], STARTED_RULE["on"]
    EXEC_RULES["on"] = STARTED_RULE["on"] = False
    try:
        yield
    finally:
        EXEC_RULES["on"], STARTED_RULE["on"] = was, was_started


@contextmanager
def quote_age_rule_off():
    """The Desk without the venue quote-age hold (ARCHITECT 2026-10-07): the engine's pre-ruling verdicts, for the
    venue engine's own tests and the Cockpit verifies. Never used by an export."""
    was = QUOTE_AGE_RULE["on"]
    QUOTE_AGE_RULE["on"] = False
    try:
        yield
    finally:
        QUOTE_AGE_RULE["on"] = was


@contextmanager
def kalshi_only_suspension_off():
    """The Desk without the Q3 MLB kalshi-only suspension (ARCHITECT 2026-10-08): the 2026-10-01 path, for tests and
    comparisons only. Never used by an export."""
    was = KALSHI_ONLY_MLB_SUSPENDED["on"]
    KALSHI_ONLY_MLB_SUSPENDED["on"] = False
    try:
        yield
    finally:
        KALSHI_ONLY_MLB_SUSPENDED["on"] = was


def is_quarantine_shadow(c: dict) -> bool:
    """A Desk call that is a quarantine shadow: PASS, shadow units > 0, a "quarantine … (shadow)" tag."""
    import re
    return bool(c.get("call") == "PASS" and (c.get("shadowUnits") or 0) > 0
                and any(re.match(r"^quarantine .*\(shadow\)$", t) for t in (c.get("tags") or [])))


@contextmanager
def started_rule_off():
    """The Desk without the started-game rule (#313) — for comparing a file with and without it."""
    was = STARTED_RULE["on"]
    STARTED_RULE["on"] = False
    try:
        yield
    finally:
        STARTED_RULE["on"] = was


@contextmanager
def injuries_one_sided_rule_off():
    """The Desk without the one-sided injury list rule (addendum 40 item 6) — for comparing a file with and without
    it."""
    was = INJURIES_ONE_SIDED_RULE["on"]
    INJURIES_ONE_SIDED_RULE["on"] = False
    try:
        yield
    finally:
        INJURIES_ONE_SIDED_RULE["on"] = was


@contextmanager
def injury_empty_rule_off():
    """The Desk without the empty-injury-list rule (addendum 40 item 4) — for comparing a file with and without it."""
    was = INJURY_EMPTY_RULE["on"]
    INJURY_EMPTY_RULE["on"] = False
    try:
        yield
    finally:
        INJURY_EMPTY_RULE["on"] = was


@contextmanager
def default_rating_rule_off():
    """The Desk without the default-rating rule (addendum 36 item 2) — for comparing a file with and without it."""
    was = DEFAULT_RATING_RULE["on"]
    DEFAULT_RATING_RULE["on"] = False
    try:
        yield
    finally:
        DEFAULT_RATING_RULE["on"] = was


@contextmanager
def kickoff_clock_rule_off():
    """The Desk without the kickoff-clock rule (addendum 72 item 1) — for comparing a file with and without it."""
    was = KICKOFF_CLOCK_RULE["on"]
    KICKOFF_CLOCK_RULE["on"] = False
    try:
        yield
    finally:
        KICKOFF_CLOCK_RULE["on"] = was


@contextmanager
def host_fence_rule_off():
    """The Desk without the host fence (addendum 109 item 3) — for comparing a file with and without it."""
    was = HOST_FENCE_RULE["on"]
    HOST_FENCE_RULE["on"] = False
    try:
        yield
    finally:
        HOST_FENCE_RULE["on"] = was


def has_started(r, now_ms: float) -> bool:
    """Kickoff at or before as_of. An unknown kickoff is NOT started (never guessed)."""
    t = utc_ms(r["utc"])
    return t == t and now_ms >= t


def side_quotes(r, side):
    """#87 v1.1: the quotes of the contract the order line BUYS for `side` — the side's own YES leg when its
    ask is captured (kalshi_legs), else k_side (HOME YES / two-way NO side). One source for the doctrine, the
    join price, the cost and the order (Codex on #303)."""
    # The SAME selection as order_line (Codex on #303): a side leg WITH A TICKER is the instrument (an unquoted
    # one is unpriceable, never priced from another contract); else, two-way, NO on the opponent's ticketed
    # leg (NO ask = 1 − its yes bid). With no ticketed leg (pre-migrate_kalshi_ticker exports, no order can be
    # written) the old pricing stands: the side's quoted leg, else the row's K-track quotes.
    legs = (r.get("src") or {}).get("kalshi_legs") or {}
    leg = legs.get(side) or {}
    if leg.get("ticker"):
        return {"bid": leg.get("bid"), "ask": leg.get("ask"), "no": False}
    opp = {"HOME": "AWAY", "AWAY": "HOME"}.get(side)
    ol = legs.get(opp) or {}
    if not r.get("threeWay") and opp and ol.get("ticker"):
        yb, ya = ol.get("bid"), ol.get("ask")
        return {"bid": None if ya is None else round(1 - ya, 4), "ask": None if yb is None else round(1 - yb, 4),
                "no": True}
    if leg.get("ask") is not None:
        return {"bid": leg.get("bid"), "ask": leg["ask"], "no": False}
    return k_side(r, side)


def join_price(bid, ask):
    """#87 v1.1 join: bid + 1c, only when the spread is >= 3c (the order line and the exec block share it)."""
    if bid is None or ask is None:
        return None
    return js_round((bid + K2["tick"]) * 100) / 100 if js_round((ask - bid) * 100) >= K2["joinMinSpreadC"] else None


def join_bid_for(r, side):
    k = side_quotes(r, side) if EXEC_RULES["on"] else k_side(r, side)
    if not k or k["bid"] is None:
        return None
    if EXEC_RULES["on"]:
        # #87 v1.1 (2): TAKE at the ask by default; a resting bid only when the spread is >= 3c ("on 1-2c
        # spreads a resting bid is adverse selection, not savings")
        if k["ask"] is None:
            return {"price": None, "note": "no ask — spread unknown, nothing to take or join"}
        sc = js_round((k["ask"] - k["bid"]) * 100)
        if sc < K2["joinMinSpreadC"]:
            return {"price": None, "note": f"spread {sc}¢ < {K2['joinMinSpreadC']}¢ — TAKE at the ask"}
    j = js_round((k["bid"] + K2["tick"]) * 100) / 100
    if k["ask"] is not None and j >= k["ask"] - 1e-9:
        return {"price": None, "note": "spread 1¢ — joining = taking"}
    return {"price": j}


def exec_cost_for(r, side):
    k = k_side(r, side)
    return k["cost"] if k and k["cost"] is not None else None


def maker_cost_for(r, side):
    k = k_side(r, side)
    return k["maker"] if k and k.get("maker") is not None else None


def order_contracts(units, limit):
    """The contract count `order_line` writes for `units` at `limit` (the day's dollar unit / limit, floored; v1.2,
    addendum 179 item 7); on an unread day the reference fill the exec gate prices at (J1). None when under one
    contract or no valid limit."""
    if not units or units <= 0 or limit is None or not (0 < limit < 1):
        return None
    n = _contracts_at(units, limit, unit_size())
    return n if n >= 1 else None


def taker_cost_for(r, side, units=None):
    """#87 v1.1 (1): the EXECUTABLE cost of backing `side` = the ask of the contract the order line buys + the
    taker fee (0.07·M·P(1−P), nearest cent per FILL). (h) RULED 2026-10-06: the fill is the order's OWN
    contract count at `units` (order_contracts at the ask) — the 10-contract assumption ended. The contract:
    `side_quotes` (the side's own YES leg, else HOME YES / two-way NO side). None = no executable quote, or an
    order under one contract (never guessed)."""
    q = side_quotes(r, side)
    ask = (q or {}).get("ask")
    if ask is None or not (0 < ask < 1):
        return None
    # the count is the EMITTED order's: at the join limit when the doctrine joins (>= 3c), else at the ask
    # (a dollar unit sizes by limit — Codex on #303)
    limit = join_price(q.get("bid"), ask) or ask
    n = order_contracts(BASE_UNITS if units is None else units, limit)
    if n is None:
        return None
    from src.walters.venue import KALSHI_FEE_M, KALSHI_SERIES_BY_COMPETITION, kalshi_fee
    series = KALSHI_SERIES_BY_COMPETITION.get(r.get("comp") or r.get("sport") or "")
    fee = kalshi_fee(ask, KALSHI_FEE_M.get(series, (1.0, None))[0], n=n)
    return round(ask + fee, 4) if fee is not None else None


def maker_cost_at(r, side, units=None):
    """The maker cost of a JOIN order (bid + 1c, spreads >= 3c) at the order's own contract count ((h); Codex on
    #303): join + 0.0175·M_maker·P(1−P) per fill. None when the doctrine takes (no join), or when the series'
    maker M is unknown (conservative unknowns, #93)."""
    q = side_quotes(r, side) or {}
    jp = join_price(q.get("bid"), q.get("ask"))
    if jp is None:
        return None
    n = order_contracts(BASE_UNITS if units is None else units, jp)
    from src.walters.venue import KALSHI_FEE_M, KALSHI_MAKER_RATE, KALSHI_SERIES_BY_COMPETITION, kalshi_fee
    m = KALSHI_FEE_M.get(KALSHI_SERIES_BY_COMPETITION.get(r.get("comp") or r.get("sport") or ""), (1.0, None))[1]
    if n is None or m is None:
        return None
    fee = kalshi_fee(jp, m, KALSHI_MAKER_RATE, n=n)
    return None if fee is None else round(jp + fee, 4)


def desk_cost_for(r, side, units=None):
    if EXEC_RULES["on"]:
        t = taker_cost_for(r, side, units)           # #87 v1.1 (1)+(2)+(h): the TAKE cost of this order
        return None if t is None else {"cost": t, "basis": "taker"}
    m = maker_cost_for(r, side)
    if m is not None:
        return {"cost": m, "basis": "maker"}
    t = exec_cost_for(r, side)
    return None if t is None else {"cost": t, "basis": "taker"}


def exec_edge_pp(r, side, model_p, units=None):
    c = desk_cost_for(r, side, units)
    return None if c is None or model_p is None else (model_p - c["cost"]) * 100


def exec_clears(e) -> bool:
    return e is not None and e >= K2["feeClearsPP"] - FEE_CLEAR_EPS


def exec_block(r, side, model_p, units=None, order_units=None):
    """The K2 numbers for the export. Since the #87 addendum `fee_clears` is a SIZING input (desk_call): edge,
    cost and fee_clears are at `units` (the order the sizing decision priced, (h)); `order_cost` is the cost of
    the order actually emitted at `order_units` when that differs (a halved PLAY)."""
    k = r.get("kExec")
    # the contract side_quotes selects (own leg, or NO on the opponent's ticketed leg) counts too (Codex on #303)
    has_leg = EXEC_RULES["on"] and (side_quotes(r, side) or {}).get("ask") is not None
    if (not k or (k["cost"] is None and k["ask"] is None and k["maker"] is None)) and not (
            EXEC_RULES["on"] and has_leg):
        return None
    dc = desk_cost_for(r, side, units)
    jb = join_bid_for(r, side)
    e = exec_edge_pp(r, side, model_p, units)
    out = {"edge_pp": e, "cost": dc["cost"] if dc else None, "basis": dc["basis"] if dc else None,
           "taker_cost": exec_cost_for(r, side), "join_price": (jb or {}).get("price"),
           "join_note": (jb or {}).get("note"),
           "no_side": bool(((side_quotes(r, side) if EXEC_RULES["on"] else k_side(r, side)) or {}).get("no")),
           "fee_clears": exec_clears(e)}
    if EXEC_RULES["on"]:
        out["taker_cost"] = dc["cost"] if dc else None
        # reference: the join (bid + 1c) at the EMITTED order's count (a halved PLAY's smaller order, Codex on #303)
        out["maker_cost"] = maker_cost_at(r, side, order_units if order_units else units)
        out["doctrine"] = "join" if (jb or {}).get("price") is not None else "take"
        q = side_quotes(r, side) or {}
        lim = join_price(q.get("bid"), q.get("ask")) or q.get("ask")
        out["contracts"] = order_contracts(BASE_UNITS if units is None else units, lim)
        if order_units is not None and order_units != units:
            oc = taker_cost_for(r, side, order_units)
            out.update(order_contracts=order_contracts(order_units, lim), order_cost=oc)
        if unit_size()["mode"] == "unread":      # addendum 179 item 4: the counts are the fee's basis, not an order
            out["contracts_basis"] = UNIT_REFERENCE_FILL_TEXT
    return out


# ------------------------------------------------------------- value side --

def value_side(r, P):
    if r["marketOnly"] or P.get("passAll") or not r["twoSided"]:
        return None
    e_min = P.get("eMin", 4)
    best = None
    for k in ("HOME", "DRAW", "AWAY"):
        if k == r["pick"] or r["probsAll"].get(k) is None or r["fairAll"].get(k) is None:
            continue
        e = (r["probsAll"][k] - r["fairAll"][k]) * 100
        if best is None or e > best["edge"]:
            best = {"side": k, "edge": e, "modelP": r["probsAll"][k], "marketP": r["fairAll"][k]}
    if not best or not best["edge"] >= e_min:
        return None
    pick_mkt = r["fairAll"].get(r["pick"])
    best["role"] = "draw" if best["side"] == "DRAW" else (
        "dog" if pick_mkt is not None and best["marketP"] < pick_mkt else "favorite")
    best["reason"] = (f"value on {best['role']}: {'+' if best['edge'] >= 0 else ''}{js_fixed(best['edge'], 1)}pp"
                      f" ({side_name(r, best['side'])} model {js_fixed(best['modelP'] * 100, 1)}% vs market "
                      f"{js_fixed(best['marketP'] * 100, 1)}%)"
                      f" · not the top pick → v1.2 candidate shadow {js_str(VALUE['units'])}u, NOT staked")
    tags = ["value-side shadow (v1.2 candidate)"]
    if r["quar"]:
        tags.append("quarantine ≥ 15pp")
        best["reason"] += f" · row quarantined {js_str(r['div'])}pp"
    if r["qbs"]:
        tags.append("QB-flagged")
        best["reason"] += f" · QB listed: {', '.join(r['qbs'])}"
    best["tags"] = tags
    return best


# ------------------------------------------------------ kalshi-only reference --

def kalshi_only_ref(r, now_ms: float) -> dict:
    if r["threeWay"]:
        return {"ok": False, "why": "3-way board — no Kalshi-only reference (no derived away/draw price)"}
    if not KALSHI_ONLY["series"].get(r["comp"]):
        return {"ok": False, "why": f"series for {r['comp'] or '?'} not in the ruled fee table"}
    k = r.get("kExec") or {}
    bid, ask = k.get("bid"), k.get("ask")
    if bid is None or ask is None:
        return {"ok": False, "why": "Kalshi not two-sided"}
    spread_c = js_round((ask - bid) * 100)
    if spread_c > KALSHI_ONLY["maxSpreadC"]:
        return {"ok": False, "why": f"Kalshi spread {spread_c}c > {KALSHI_ONLY['maxSpreadC']}c"}
    t = utc_ms(r["utc"])
    if t != t:
        return {"ok": False, "why": "kickoff unknown"}
    if now_ms >= t:
        return {"ok": False, "why": "in-play"}
    if now_ms < t - PASSCLASS["rerunMin"] * 60000:
        return {"ok": False, "why": "before T-60 — books may still post"}
    mid = (bid + ask) / 2
    return {"ok": True, "mid": mid, "refs": {"HOME": mid, "AWAY": 1 - mid}, "spreadC": spread_c,
            "bid": bid, "ask": ask}


# ------------------------------------------------------------------ policy --

def kickoff_clock_drift(r):
    """Addendum 72 item 1: (the stored kickoff, Kalshi's clock), both naive UTC, where a leg's own ticker carries a
    clock (kalshi_match.ticker_stamp) at or more than DESK_CLOCK_DRIFT (1h, addendum 83 item 2, inclusive) from the
    row's stored kickoff; else None: the rule off, an unknown kickoff, no leg with a ticker, or a ticker shape without a
    clock (not compared)."""
    if not KICKOFF_CLOCK_RULE["on"]:
        return None
    from src.ingestion.kalshi_match import ticker_stamp
    t = utc_ms(r["utc"])
    if t != t:
        return None
    stored = datetime(1970, 1, 1) + timedelta(milliseconds=t)
    legs = (r.get("src") or {}).get("kalshi_legs") or {}
    for side in sorted(legs):
        tk = (legs.get(side) or {}).get("ticker")
        if not tk or not isinstance(tk, str):
            continue
        _, clock = ticker_stamp({"ticker": tk})
        if clock is not None and abs(stored - clock) >= DESK_CLOCK_DRIFT:
            return stored, clock
    return None


def kickoff_clock_reason(stored: datetime, clock: datetime) -> str:
    """The ruled reason: "stored kickoff 2026-10-15 13:00 ET vs Kalshi's clock 18:00 ET: no call" (Kalshi's clock
    keeps its date where it falls on another US Eastern day)."""
    from src.ingestion.kalshi_match import et_text
    st, kal = et_text(stored), et_text(clock)
    return f"stored kickoff {st} vs Kalshi's clock {kal[11:] if kal[:10] == st[:10] else kal}: no call"


def _no_call(r, kind: str, reason: str) -> dict:
    return {"call": "PASS", "units": 0, "cls": "pass", "edge": None, "tags": [kind], "reasons": [reason],
            "execUnits": None, "shadowUnits": 0, "passKind": kind, "mktRef": r["mkt"], "kalOnly": False}


def intl_venue_unknown(r) -> bool:
    """INTL rule (3): the row's venue flag (the export's `venue_flag`, from neutral_v3) is unknown. A missing
    flag counts as unknown (conservative)."""
    return (r["src"].get("venue_flag") or "unknown") == "unknown"


def default_rated_teams(r) -> list[str]:
    """addendum 36 item 2: the teams of this row whose rating is the default (not in the model's table), home
    first. Empty when the rule is off or the row carries no label."""
    rs = r.get("ratingSrc")
    if not DEFAULT_RATING_RULE["on"] or not isinstance(rs, dict):
        return []
    return [name for side, name in (("home", r["home"]), ("away", r["away"])) if rs.get(side) == "default"]


def one_sided_injuries(r) -> tuple[str, str, int] | None:
    """addendum 40 item 6: (the team whose list is empty, the other team, its count) when exactly one side of a
    soccer row lists no name and the other lists some; else None (rule off, another sport, no counts, both empty,
    both listed)."""
    inj = r.get("injSides")
    if not INJURIES_ONE_SIDED_RULE["on"] or r["sport"] != "SOCCER" or not isinstance(inj, dict):
        return None
    n = {s: (inj.get(s) or {}).get("count") if isinstance(inj.get(s), dict) else None for s in ("home", "away")}
    if not all(isinstance(v, int) for v in n.values()):
        return None
    name = {"home": r["home"], "away": r["away"]}
    for empty, other in (("home", "away"), ("away", "home")):
        if n[empty] == 0 and n[other] > 0:
            return name[empty], name[other], n[other]
    return None


def kalshi_only_suspended(r) -> bool:
    """Q3 K1: the suspension covers MLB rows only (K4: NFL and PL keep the 2026-10-01 reference)."""
    return bool(KALSHI_ONLY_MLB_SUSPENDED["on"] and r["sport"] == "MLB")


def _env_file(path, strict: bool = False):
    """An env file's KEY=VALUE pairs, read with config.py's reader (python-dotenv). A file that does not exist reads {}
    and the next source decides. One that exists but cannot be read (host.env is root:sp 0640; a directory): with
    `strict` (host.env, addendum 116 item 2) HOST_ENV_UNREADABLE, which makes the role unknown and stops the reading;
    without it {} (the checkout's .env, the last source: nothing after it either way)."""
    from dotenv import dotenv_values
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return {}
    except OSError:
        return HOST_ENV_UNREADABLE if strict else {}
    return dotenv_values(stream=io.StringIO(text))


def role_reading(env=None) -> tuple[str | None, object]:
    """(role, value): this machine's SP_EXPORTS_MIRROR_ROLE (addendum 45 P1: host | laptop, no default). `value` is
    the stripped value that decided, "" when no source holds one, HOST_ENV_UNREADABLE when host.env exists but cannot
    be read; `role` is it when it is host or laptop, else None.
    The first source with a non-empty value decides, in this order:
      1. the machine's own host.env (SP_HOST_ENV, else HOST_ENV_DEFAULT; only the host has one). First, so a run typed
         by hand on the host is fenced (#410 review): closing.mirror_role() reads the environment first
         (sp_common.setting), so a closing-run typed by hand, with no EnvironmentFile, signs its page "machine: host"
         from host.env while its export step's environment has no role, or the laptop's .env role. A host.env that
         exists but cannot be read decides too: the role is unknown and nothing after it is read (addendum 116 item 2),
         so a user who cannot read it is never answered by the checkout's .env, which on the host says laptop.
      2. the process environment (the units' EnvironmentFile, sp_run's load_host_env, config.py's load_dotenv).
      3. the checkout's .env (DOTENV), so an entry point that never imports config (a script) reads the laptop's
         line as cli.py does (addendum 110 item 1: "The laptop's .env carries the role line").
    A value there that is neither host nor laptop decides too: the role is unknown (law 4), never the next source's.
    `env`: read that mapping alone, not the machine (tests)."""
    reads = (lambda: env,) if env is not None else (
        lambda: _env_file(os.environ.get("SP_HOST_ENV", HOST_ENV_DEFAULT), strict=True), lambda: os.environ,
        lambda: _env_file(DOTENV))
    for read in reads:                                  # lazily: the .env is read only when nothing before it says
        got = read()
        if got is HOST_ENV_UNREADABLE:
            return None, HOST_ENV_UNREADABLE
        value = (got.get(ROLE_ENV) or "").strip()
        if value:
            return (value if value in ROLES else None), value
    return None, ""


def machine_role(env=None) -> str | None:
    """This machine's role, host or laptop; None when it is unknown (role_reading)."""
    return role_reading(env)[0]


def host_fenced(r) -> str | None:
    """Addendum 109 item 3 + addendum 110 item 1 + addendum 115 item 3: the fence's reason for a soccer or INTL model
    row while the fence is on, on a machine whose role is host or unknown; None (not fenced) on the laptop, for every
    other row, or with the switch off. Only model rows reach desk_call; a market-only row (the venue engine) is never
    fenced."""
    if not (HOST_FENCE_RULE["on"] and r["sport"] in HOST_FENCE_SPORTS):
        return None
    role, value = role_reading()
    if role == "laptop":
        return None
    if role == "host":
        return HOST_FENCE_REASON
    if value is HOST_ENV_UNREADABLE:
        return HOST_FENCE_UNREADABLE_REASON
    if value:
        return f"host fence: role '{value}' is not host or laptop"                # addendum 115 item 3b, approved
    return HOST_FENCE_UNSET_REASON


def desk_call(r, now_ms: float, postseason_graded: int = 0, intl_graded: int = 0) -> dict:
    """The Desk's call for ONE model-sport row: the v1.1 policy (_desk_call), then Q3 K1 (ARCHITECT 2026-10-08):
    an MLB row whose reference would be the kalshi-only mid is PASS with no reference; its would-be call is kept
    in `koHold` for the record (K3)."""
    c = _desk_call(r, now_ms, postseason_graded, intl_graded)
    if not (c["kalOnly"] and kalshi_only_suspended(r)):
        return c
    ko = kalshi_only_ref(r, now_ms)                     # the same pure reference _desk_call took (mid, bid, ask)
    hold = {"mid": ko["mid"], "bid": ko["bid"], "ask": ko["ask"], "spread_c": ko["spreadC"],
            "raw_edge_pp": c["edge"], "equal_footing_edge_pp": c["edge"] / 2,
            "would_call": c["call"], "would_units": c["units"]}
    out = _no_call(r, KALSHI_ONLY_SUSPENDED_KIND, KALSHI_ONLY_SUSPENDED_REASON)
    out.update(tags=["kalshi-only suspended (MLB)"], mktRef=None, koHold=hold)
    return out


def _desk_call(r, now_ms: float, postseason_graded: int = 0, intl_graded: int = 0) -> dict:
    """The Cockpit's policy() body for ONE model-sport row (Desk v1.1 and its addenda, before Q3 K1)."""
    fence = host_fenced(r)                              # addendum 109 item 3 (#410): first, it overrides every call
    if fence:
        return _no_call(r, HOST_FENCE_KIND, fence)
    if (r.get("comp") or "") in SHADOW_VENUE_COMPS:     # S1 (ARCHITECT 2026-10-08), checked before started
        return {"call": "PASS", "units": 0, "cls": "pass", "edge": None, "tags": ["shadow league"],
                "reasons": [SHADOW_LEAGUE_REASON], "execUnits": None, "shadowUnits": 0,
                "passKind": SHADOW_LEAGUE_KIND, "mktRef": r["mkt"], "kalOnly": False}
    drift = kickoff_clock_drift(r)                      # addendum 72 item 1: checked before the started rule
    if drift:
        out = _no_call(r, KICKOFF_CLOCK_KIND, kickoff_clock_reason(*drift))
        out["clockHold"] = drift
        return out
    if STARTED_RULE["on"] and has_started(r, now_ms):
        return _no_call(r, "started", STARTED_REASON)
    defaulted = default_rated_teams(r)
    if defaulted:
        return _no_call(r, DEFAULT_RATING_KIND, f"default rating: {' and '.join(defaulted)} not in the model's "
                                                f"rating table → no call ({DEFAULT_RATING_RULING})")
    one = one_sided_injuries(r)
    if one:
        return _no_call(r, INJURIES_ONE_SIDED_KIND, f"injury list one-sided: {one[0]} lists no name, {one[1]} lists "
                                                    f"{one[2]} → no call ({INJURIES_ONE_SIDED_RULING})")
    if r["sport"] == "INTL":
        if r["comp"] not in INTL["callComps"]:
            return _no_call(r, "no_series", f"{r['comp'] or '?'}: no wired Kalshi series → prediction without a "
                                            "call (INTL v0 rule 4)")
        if intl_venue_unknown(r) and r["home"] in INTL_HOME_ABROAD:
            return _no_call(r, "venue_unknown", f"venue unknown and {r['home']} is on the home-abroad list → "
                                                "never a call (INTL v0 rule 3)")
    base = BASE_UNITS
    ps_half = postseason_graded < POSTSEASON["reviewN"]
    P = POLICY.get(r["sport"]) or POLICY["DEFAULT"]
    e_min, e_lad = P.get("eMin", 4), P.get("eLad", INF)
    e_hair, p_min = P.get("eHair", 15), P.get("pMin", 0)
    reasons, tags = [], []
    call, cls, units, shadow_units = "PASS", "pass", 0, 0
    exec_units = None                     # (h): the order units the exec gate priced (None = not gated)
    mkt_ref, kal_only, ko_why = r["mkt"], False, None
    if not r["twoSided"] or r["mkt"] is None:
        ko = None if P.get("passAll") else kalshi_only_ref(r, now_ms)
        if ko and ko["ok"]:
            mkt_ref = ko["refs"].get(r["pick"])
            kal_only = mkt_ref is not None
            if kal_only:
                reasons.append(f"kalshi-only reference: mid {js_fixed(ko['mid'], 3)} (bid {js_fixed(ko['bid'], 2)}"
                               f" / ask {js_fixed(ko['ask'], 2)}, spread {ko['spreadC']}c)")
        elif ko:
            ko_why = ko["why"]
    edge = (r["prob"] - mkt_ref) * 100 if mkt_ref is not None else None
    pass_kind = None
    if not kal_only and (not r["twoSided"] or r["mkt"] is None):
        reasons.append("market not two-sided → no reference" + (f" (kalshi-only: {ko_why})" if ko_why else ""))
        pass_kind = "noref"
    elif r["prob"] < p_min:
        reasons.append(f"pick prob {js_fixed(r['prob'], 3)} < {js_str(p_min)}")
        pass_kind = "floor"
    elif edge < e_min:
        reasons.append(f"edge {js_fixed(edge, 1)}pp < {js_str(e_min)}pp floor")
        pass_kind = "floor"
    else:
        units, call, cls = base, "PLAY", "play"
        reasons.append(f"edge {js_fixed(edge, 1)}pp ≥ floor")
        tags.append("edge ≥ floor")
        if P.get("passAll"):
            call, cls, units = "PASS", "pass", 0
            reasons.clear()
            reasons.append("pre-gate sport: no production model — market display only")
        quarantined = bool(P.get("qNever") and r["quar"])
        mlb_big = bool(MLB_QUARANTINE["on"] and r["sport"] == "MLB"
                       and edge > MLB_QUARANTINE["abovePP"] + MLB_QUARANTINE_EPS)
        quarantined = quarantined or mlb_big
        if call == "PLAY" and r["sport"] == "NFL" and r["qbs"]:
            units = min(units, base / 2)
            reasons.append(f"QB-flagged ({', '.join(r['qbs'])}) → half units")
            tags.append("QB-flagged half units")
        if (call == "PLAY" and r["sport"] == "NFL" and INJURY_EMPTY_RULE["on"] and r.get("injEmpty")
                and not quarantined):                     # addendum 40 item 4: a quarantine shadow is not resized
            units = min(units, base / 2)
            reasons.append(f"injury list empty ({' and '.join(r['injEmpty'])}): QB rule unread → half units")
            tags.append(INJURY_EMPTY_TAG)
        three_way = r["mktHasDraw"]
        if edge >= e_lad:
            units = base / 2
            if three_way and r["pick"] in ("AWAY", "DRAW"):
                call, cls = "LADDER", "ladder"
                reasons.append(f"edge ≥ {js_str(e_lad)}pp on away/draw (3-way) → double-chance "
                               f"({'X2' if r['pick'] == 'AWAY' else '1X/X2'}), half units")
                tags.append("ladder: big away/draw edge → DC")
            else:
                cls = "caution"
                reasons.append(f"edge ≥ {js_str(e_lad)}pp → reduced-size straight (2-way board: no DC instrument),"
                               f" half units")
                tags.append("ladder-size on 2-way board")
        # #181 (ARCHITECT 2026-10-17 16:55 ET, addendum 117 item 2(a)): "The stale "caution" text on the eight NHL rows
        # is replaced by the pass text (reason as the Desk gives it); nothing else on those rows changes." A row that is
        # already PASS here is the pre-gate branch (passAll) only: it gets neither the caution's size nor its reason and
        # tag. A row the quarantine turns PASS below is still a PLAY here: its shadow keeps the caution's size and tag.
        if (edge >= e_hair and call != "PASS"
                and not (MLB_QUARANTINE["on"] and r["sport"] == "MLB")):   # MLB: superseded (2026-10-07)
            units, cls = base / 2, "caution"
            reasons.append(f"edge ≥ {js_str(e_hair)}pp → market-is-right caution (cohort: big edges historically"
                           f" anti-predictive)")
            tags.append("big-edge caution half units")
        if edge < e_min + 1:
            units = min(units, base / 2)
            reasons.append("edge within 1pp of floor → half units (near-floor noise, not conviction)")
            tags.append("near-floor half units")
        if call != "PASS" and r["stage"] == "postseason" and ps_half:
            units = min(units, base / 2)
            reasons.append(f"postseason → half units until {POSTSEASON['reviewN']} graded "
                           f"({postseason_graded}/{POSTSEASON['reviewN']})")
            tags.append("postseason half units")
        if EXEC_RULES["on"] and call == "PLAY" and not quarantined:
            # #87 v1.1 (3): full tier units only at exec edge >= 4pp; a PLAY whose fair edge clears but whose
            # exec edge does not, or that has no executable quote (conservative unknowns), gets HALF units
            # (h): priced at the order this PLAY places if it clears — its units here, × the kalshi-only
            # multiplier that applies below
            gate_units = float(js_fixed(units * KALSHI_ONLY["sizeMult"], 4)) if kal_only else units
            exec_units = gate_units
            xe = exec_edge_pp(r, r["pick"], r["prob"], gate_units)
            if xe is None:
                units = min(units, base / 2)
                reasons.append("no executable quote for the pick (ask + taker fee) → half units")
                tags.append("exec unknown half units")
            elif not exec_clears(xe):
                units = min(units, base / 2)
                reasons.append(f"exec edge {js_fixed(xe, 1)}pp < {K2['feeClearsPP']}pp at ask + taker fee "
                               f"{js_fixed(desk_cost_for(r, r['pick'], gate_units)['cost'], 3)} → half units")
                tags.append("exec < 4pp half units")
            else:
                reasons.append(f"exec edge {js_fixed(xe, 1)}pp ≥ {K2['feeClearsPP']}pp at ask + taker fee")
                tags.append("exec clears")
        if call != "PASS" and r["sport"] == "INTL" and intl_graded < INTL["halfUntilGraded"]:
            units = min(units, base / 2)
            reasons.append(f"INTL → half units until {INTL['halfUntilGraded']} graded "
                           f"({intl_graded}/{INTL['halfUntilGraded']})")
            tags.append("intl half units")
        if call != "PASS" and r["stage"] is None and r["sport"] == "MLB":
            reasons.append("stage unknown — postseason caution not applied")
        if kal_only and call != "PASS":
            units = float(js_fixed(units * KALSHI_ONLY["sizeMult"], 4))
            reasons.append(f"kalshi-only → {js_str(KALSHI_ONLY['sizeMult'])} × units (provisional; review at "
                           f"{KALSHI_ONLY['reviewN']} graded)")
            tags.append("kalshi-only half units")
        if r["tier"] == "strong":
            reasons.append("strong tier")
            tags.append("strong tier")
        if r["kal"] and r["kal"] != "absent":
            reasons.append(f"kalshi {r['kal']}")
        if quarantined and call != "PASS":
            shadow_units, call, cls, units = units, "PASS", "pass", 0
            reasons.clear()
            if mlb_big:
                reasons.append(f"QUARANTINE edge {js_fixed(edge, 1)}pp > {js_str(MLB_QUARANTINE['abovePP'])}pp vs "
                               f"{'the kalshi-only mid' if kal_only else 'the book close'} — {MLB_QUARANTINE_RULING}:"
                               f" never a straight play (shadow at {js_str(shadow_units)}u)")
                tags.append(f"quarantine > {js_str(MLB_QUARANTINE['abovePP'])}pp (shadow)")
            else:
                reasons.append(f"QUARANTINE {js_str(r['div'])}pp — contract: never a straight play")
                tags.append("quarantine ≥ 15pp (shadow)")
    if (call == "PASS" and pass_kind == "floor" and not kal_only and r["books"] is not None
            and r["books"] < PASSCLASS["minBooks"]):
        pass_kind = "noref"
        reasons.append(f"books {js_str(r['books'])} < {PASSCLASS['minBooks']} → thin reference")
    if call != "PASS":
        pass_kind = None
    else:
        # #181 (ARCHITECT 2026-10-17 10:40 ET, addendum 112 item 9, RULED): "a PASS row carries units 0 and class
        # pass, every sport". The pre-gate branch (passAll) leaves the sizing chain running; its big-edge caution set
        # 0.5u / caution on a PASS row (ported from the JS for parity) and no longer runs there (addendum 117 item 2(a),
        # above). This line holds the rule for every PASS path whatever the chain does. POLICY_VERSION stays v1.1
        # (addendum 117 item 2(b)): a display defect, not a Desk-rule change.
        units, cls = 0, "pass"
    return {"call": call, "units": units, "cls": cls, "edge": edge, "tags": tags, "reasons": reasons,
            "execUnits": exec_units,
            "shadowUnits": shadow_units, "passKind": pass_kind, "mktRef": mkt_ref, "kalOnly": kal_only}


# ---------------------------------------------------------------- parlays --

PARLAY = {"units": 0.25, "maxLegs": 3, "top": 3}


def build_parlays(calls) -> list[dict]:
    """The Cockpit's buildParlays (fixed #183): live legs = non-PASS calls in
    row order; every 2- and 3-leg combo with no shared team; Π model vs Π
    market (market = mkt, else the model p); edge > 0; ranked by distinct
    sports, then edge (stable); the top 3. `calls` = [(row, call)] across
    every file loaded, in load order."""
    return rank_parlays(calls)[:PARLAY["top"]]


def rank_parlays(calls, stats: dict | None = None) -> list[dict]:
    """Every edge > 0 ticket, ranked (build_parlays is its top 3). #87 v1.1 (5): Π market = Π of each leg's
    EXECUTABLE cost (ask + taker fee, `taker_cost_for`); a ticket with a leg that has no executable quote
    cannot be priced and is not offered (counted in stats["unpriced"]). Π fair rides along as `pf`."""
    live = [r for r, c in calls if c["call"] != "PASS"]
    teams = lambda r: (r["home"], r["away"])
    combos = []
    for a in range(len(live)):
        for b in range(a + 1, len(live)):
            A, B = live[a], live[b]
            if any(t in teams(B) for t in teams(A)):
                continue
            combos.append([A, B])
            for c in range(b + 1, len(live)):
                C = live[c]
                if any(t in teams(A) or t in teams(B) for t in teams(C)):
                    continue
                combos.append([A, B, C])
    ranked = []
    if stats is not None:
        stats.setdefault("unpriced", 0)
    for legs in combos:
        pm = pk = 1
        for l in legs:
            pm = pm * l["prob"]
        for l in legs:
            pk = pk * (l["mkt"] if l["mkt"] is not None else l["prob"])
        pf = pk
        if EXEC_RULES["on"] and any(l["mkt"] is None for l in legs):
            pf = None          # Π BOOK fair is unavailable when a leg has no book reference (never the model p)
        if EXEC_RULES["on"]:
            costs = [taker_cost_for(l, l["pick"], PARLAY["units"]) for l in legs]     # (h): the leg's own order
            if any(c is None for c in costs):
                if stats is not None:
                    stats["unpriced"] += 1
                continue
            pk = 1
            for c in costs:
                pk = pk * c
        t = {"legs": legs, "sports": len({l["sport"] for l in legs}), "pm": pm, "pk": pk, "edge": pm - pk}
        if EXEC_RULES["on"]:
            t["pf"], t["costs"] = pf, costs
        if t["edge"] > 0:
            ranked.append(t)
    ranked.sort(key=lambda t: (-t["sports"], -t["edge"]))
    return ranked


# B-TRACK cross-book rules (ARCHITECT 2026-10-01), PRE-COMMITTED, frozen before
# any result. SHADOW ONLY: tickets are built and logged exactly as v1.1; the
# rules record what they WOULD cut, for 30 slates, then promote in the v1.2 bump.
#   (1) EXPOSURE CAP: total units on one team-outcome (game + side) across the
#       Desk's straights and parlay legs (0.25u per ticket) <= 1.25u; a ticket
#       whose leg would breach it is skipped.
#   (2) TICKET DEDUP: tickets with the same leg set (sport, teams, kickoff, pick;
#       price ignored) are one ticket; the better-priced one (the LOWER Π market:
#       the bigger fair-odds payout) is kept.
B_TRACK = {"exposure_cap_units": 1.25, "review_slates": 30, "applied": False}


def _outcome(l) -> str:
    return f"{l['sport']}|{l['away']}@{l['home']}|{l['utc']}|{l['pick']}"


def _legset(t) -> str:
    return "+".join(sorted(_outcome(l) for l in t["legs"]))


def _straight_exposure(calls) -> dict:
    """Units per team-outcome from the Desk's straights. The same game in two
    loaded files (a morning and a T-60 export) is ONE position, as in the
    ledger: the later file's units stand."""
    exp = {}
    for r, c in calls:
        if c["call"] != "PASS":
            exp[_outcome(r)] = c["units"]
    return exp


def _apply_rules(tickets, exp0, want=None):
    """Walk tickets in rank order through dedup then the exposure cap. Returns
    (kept, cuts) where cuts = [(ticket, rule, detail)]. `want` stops after that
    many kept (the v1.2 builder's top 3)."""
    cap, u = B_TRACK["exposure_cap_units"], PARLAY["units"]
    best = {}
    for t in tickets:                                   # (2) dedup: the lowest Π market per leg set
        k = _legset(t)
        if k not in best or t["pk"] < best[k]["pk"]:
            best[k] = t
    exp, kept, cuts = dict(exp0), [], []
    for t in tickets:
        if best[_legset(t)] is not t:
            cuts.append((t, "deduped", f"same legs as a better-priced ticket (Π market {best[_legset(t)]['pk']:.4f})"))
            continue
        breach = [o for o in (_outcome(l) for l in t["legs"]) if exp.get(o, 0) + u > cap + 1e-9]
        if breach:
            cuts.append((t, "capped", "; ".join(f"{o.split('|')[1]} {o.split('|')[3]} at {exp.get(o, 0):g}u"
                                                 for o in breach)))
            continue
        for l in t["legs"]:
            exp[_outcome(l)] = exp.get(_outcome(l), 0) + u
        kept.append(t)
        if want and len(kept) >= want:
            break
    return kept, cuts


def qb_shared_risk(calls, tickets) -> list[dict]:
    """#192 (ruling 2026-10-01): one injured QB is ONE news item. Half units
    still apply on every game his team plays (policy v1.1, unchanged), but
    for the B-track those games share one risk factor: LOGGED here, no cap
    change. A QB listed on >= 2 live games (non-PASS Desk calls): the games,
    their straight units and the v1.1 tickets touching them."""
    by_qb: dict[str, list] = {}
    for r, c in calls:
        if c["call"] == "PASS":
            continue
        for q in dict.fromkeys(r.get("qbs") or []):
            by_qb.setdefault(q, [])
            key = f"{r['game']}|{r['utc']}"
            if key not in [k for k, _, _ in by_qb[q]]:
                by_qb[q].append((key, r, c))
    out = []
    for q, games in sorted(by_qb.items()):
        if len(games) < 2:
            continue
        keys = {_outcome(r).rsplit("|", 1)[0] for _, r, _ in games}
        touching = [t for t in tickets if any(_outcome(l).rsplit("|", 1)[0] in keys for l in t["legs"])]
        out.append({"player": q, "games": [k for k, _, _ in games],
                    "straight_units": sum(c["units"] for _, _, c in games),
                    "tickets_touching": len(touching)})
    return out


def b_track_shadow(calls, ranked=None) -> dict:
    """What the B-track rules WOULD do on this slate (nothing is applied):
    the cuts among the v1.1 tickets, and the tickets v1.2 would build.
    `ranked` = rank_parlays(calls) when the caller already has it (its top 3
    ARE the v1.1 tickets, so the cut marks map onto them)."""
    ranked = rank_parlays(calls) if ranked is None else ranked
    v11 = ranked[:PARLAY["top"]]
    exp0 = _straight_exposure(calls)
    _, cuts = _apply_rules(v11, exp0)
    v12, _ = _apply_rules(ranked, exp0, want=PARLAY["top"])
    return {"rules": {"exposure_cap_units": B_TRACK["exposure_cap_units"],
                      "dedup": "same legs (sport, teams, kickoff, pick), keep the lower Π market"},
            "applied": B_TRACK["applied"], "review_slates": B_TRACK["review_slates"],
            "exposure_capped": sum(1 for _, r, _ in cuts if r == "capped"),
            "deduped": sum(1 for _, r, _ in cuts if r == "deduped"),
            "cuts": [{"signature": _legset(t), "rule": r, "detail": d} for t, r, d in cuts],
            "v12_tickets": [_legset(t) for t in v12],
            "qb_shared_risk": qb_shared_risk(calls, v11),
            "_cut_by_id": {id(t): r for t, r, _ in cuts}}


def parlay_block(t) -> dict:
    """One ticket for the file (the ledger keys a ticket on sport:away@home:pick). #87 v1.1 (5): market_p is
    Π executable cost; fair_p (Π fair) and each leg's exec_cost ride along; the independence label stands."""
    b = _parlay_block(t)
    if "pf" in t:
        b.update(market_basis="executable (Π ask + taker fee)", fair_p=_num(t["pf"]) if t["pf"] is not None else None,
                 label=PARLAY_LABEL)
        for leg, c in zip(b["legs"], t["costs"]):
            leg["exec_cost"] = _num(c)
    return b


def _parlay_block(t) -> dict:
    return {"units": PARLAY["units"], "sports": t["sports"], "model_p": _num(t["pm"]), "market_p": _num(t["pk"]),
            "edge": t["edge"], "edge_pp": _num(t["edge"] * 100),
            "signature": "+".join(sorted(f"{l['sport']}:{l['away']}@{l['home']}:{l['pick']}" for l in t["legs"])),
            "legs": [{"sport": l["sport"], "game": l["game"], "home": l["home"], "away": l["away"],
                      "kickoff": l["utc"] or None, "pick": l["pick"], "model_p": _num(l["prob"]),
                      "market_p": _num(l["mkt"]),
                      # ORDER LINE: each leg as its single-game order at the ticket's units
                      # (a Kalshi combo is built from these legs)
                      "order": order_line(l, l["pick"], PARLAY["units"])} for l in t["legs"]]}


def evaluate(doc: dict, now_ms: float, counts: dict | None = None) -> dict:
    """Desk output for one export document, row order as the Cockpit's:
    calls (model rows), value shadows, venue (every row)."""
    intl_graded = int((counts or {}).get(INTL_COUNT_KEY) or 0)
    counts = {k: int((counts or {}).get(k) or 0) for k in COUNT_KEYS}
    rows = normalize(doc)
    if any(r["sport"] == "INTL" for r in rows):     # INTL v0 (2): only an intl file carries the count
        counts[INTL_COUNT_KEY] = intl_graded
    calls, values, venue = [], [], []
    for r in rows:
        if not r["marketOnly"]:
            c = desk_call(r, now_ms, counts["postseason_graded"], intl_graded)
            calls.append((r, c))
            v = None if c["passKind"] in NO_CALL_KINDS else value_side(r, POLICY.get(r["sport"]) or POLICY["DEFAULT"])
            if v:
                values.append((r, v))
    for r in rows:
        venue.append((r, venue_edge(r, now_ms)))
    return {"rows": rows, "calls": calls, "values": values, "venue": venue, "counts": counts}


# ------------------------------------------------------------ the export --

def _num(v):
    """Numbers go into the file UNROUNDED (F1b: the Cockpit renders them as-is,
    bit-identical to computing them)."""
    return v


def venue_block(ven) -> dict:
    out = {"eligible": ven["eligible"], "side": ven["side"], "div_pp": _num(ven["divPP"]),
           "book_p": _num(ven["bookP"]), "kalshi_p": _num(ven["kalP"]), "kind": ven["kind"],
           "reason": ven["reason"]}
    if "execPP" in ven:                                   # #87 v1.1 (4)
        out.update(exec_pp=_num(ven["execPP"]), exec_cost=_num(ven["execCost"]))
    if "held" in ven:                                     # ARCHITECT 2026-10-07: the engine's verdict, for the record
        out["quote_age_hold"] = {"rule": "ARCHITECT 2026-10-07 venue-edge quote age",
                                 "engine_eligible": ven["held"]["eligible"], "engine_kind": ven["held"]["kind"],
                                 "engine_reason": ven["held"]["reason"]}
    return out


def window_venue(row: dict, now_ms: float) -> dict:
    """F1c (#191): the venue verdict for one Next-24h card row (the fixtures
    grammar + engine), computed here so the Cockpit only renders it — the same
    inputs the card's in-browser venueEdge() read before F1c."""
    fair = (row.get("market") or {}).get("fair_prob") or {}
    ven = venue_edge({"marketOnly": row.get("engine") != "model_edge",
                      "sport": str(row.get("competition") or row.get("sport") or "?").upper(),
                      "utc": row.get("utc_date") or "", "fairAll": fair,
                      "books": (row.get("market") or {}).get("bookmaker_count") or 0,
                      "booksAt": (row.get("market") or {}).get("captured_at"),
                      "kalProb": kal_from_fixture(row.get("kalshi"), fair),
                      # #87 v1.1 (4): the exec gate's quotes (the row is a _fixture_row: legs + K-track fields)
                      "src": row, "comp": str(row.get("competition") or "").upper(),
                      "threeWay": fair.get("DRAW") is not None, "kExec": _kexec_of(row)}, now_ms)
    return venue_block(ven)


# ------------------------------------------------------------- order line --
# ORDER LINE (ARCHITECT 2026-10-04): every PLAY / LADDER / VENUE row and every
# parlay leg carries the copy-exact Kalshi order: market ticker, side, limit
# price per doctrine, contract count — "placing an order is copy-exact, never a
# lookup". No policy change: the call and the units are the policy's; this only
# writes them as an order. Inputs: the export row's `kalshi_legs` (ticker +
# yes bid / ask per captured leg, from sync-kalshi-*).
#   side   : backing a side = BUY YES on that side's contract; a LADDER (double
#            chance, away pick) = BUY NO on the HOME contract; a two-way game
#            whose side has no captured leg = BUY NO on the opponent's contract
#   limit  : #87 v1.1 (ARCHITECT-RULE 2026-10-06) TAKE at the ASK by default; join the bid
#            only when the spread is >= 3c; no ask -> no limit (stated, never guessed).
#            (The 2026-09-30 join-bid doctrine is superseded; base_v11() keeps it for the golden.)
#            NO prices mirror the YES contract: NO bid = 1 - yes ask, NO ask = 1 - yes bid
#   count  : floor(units x the day's unit in dollars / limit) (addendum 179 item 7, "as today, on the day's unit")
#
# THE UNIT IS A FRACTION OF THE POOL (ARCHITECT 2026-10-30 09:30 ET, addendum 179, #732, Desk policy v1.2; the
# operator's ruling of 09:26 ET), verbatim: "a unit is 8% of the money pool, growing and shrinking with it. [...] The
# half-unit cohort (0 < exec < 4, QB-clean) is therefore 4% of the pool; LADDER notional and the floor-blocked notional
# lines stay notional at 1u." The architect advised 2-3% and the operator kept 8%: the operator's sizing decision, the
# advice beside it, not re-opened. The fraction and the names are code and may be printed; the pool's dollar value
# and the day's dollar unit are never in this repo (item 5). Every PLAY's units are the v1.1 policy's; a 0.5u row is
# HALF_UNIT_FRACTION of the pool by arithmetic (item 1), so it has no code path of its own.
#   THE READ, ONCE A DAY (item 3): the day's first slate stage runs `cli.py desk-unit`, which computes
#     floor(UNIT_FRACTION x pool) in whole dollars, applies the floor (UNIT_FLOOR_ENV, set by hand, never in the repo)
#     and writes logs/desk_unit_<ET date>.json once (src/walters/desk_unit.py). Every later page that day reads that
#     file: annotate / parlays_doc read it once for their own `now`'s ET date (_day_scope).
#   UNREAD (item 4, law 4): a failed read, a file the day does not have (no read yet today; yesterday's file is never
#     read), or a file that cannot be read: no order line; the order's `why` is UNIT_UNREAD_TEXT verbatim. The exec
#     gate's fee is then priced at the reference fill (ORDER_UNIT_CONTRACTS per 1u, the pre-v1.2 default). That is
#     NOT neutral (#732 judgement J1, for the architect): the fee rounds per fill of the order's own count (#87 v1.1
#     (h)), on a read day units x the day's unit / limit, so a borderline row's exec edge, tier and units can differ
#     between a read day and an unread one. Which basis is right is the architect's ruling; until then the unread
#     day's desk.exec / desk.ladder_exec counts carry `contracts_basis` = UNIT_REFERENCE_FILL_TEXT.
#   SP_UNIT_USD is retired from the Desk's sizing (item 4): nothing here reads it. A file exported before the switch
#     carries its own basis in its order lines' `unit` label, which desk-rescore reads (file_unit_basis).
ORDER_UNIT_CONTRACTS = 10
UNIT_FRACTION = 0.08                     # addendum 179 item 1: a unit is 8% of the money pool
HALF_UNIT_FRACTION = 0.04                # addendum 179 item 1: the half-unit cohort, 0.5u = 4% of the pool
UNIT_FLOOR_ENV = "SP_UNIT_FLOOR_USD"     # addendum 179 item 4: the floor's NAME (its value is set by hand, never here)
UNIT_UNREAD_TEXT = "unit unread — no order"          # addendum 179 item 4, verbatim
UNIT_UNREAD_LABEL = "unit unread"
# An unread day's desk.exec / desk.ladder_exec `contracts` are the reference fill the fee is priced at, never an order:
# those blocks then carry `contracts_basis` with this text (absent on a read day, where the count is the order's).
UNIT_REFERENCE_FILL_TEXT = "reference fill, no order (unit unread)"
# The basis a file exported before v1.2 with SP_UNIT_USD unset declares in its order lines (desk-rescore re-scores
# such a file under it; the Cockpit's fillUnitBasis reads it): the label is that file's, kept verbatim.
LEGACY_CONTRACTS_LABEL = f"1u = {ORDER_UNIT_CONTRACTS} contracts (SP_UNIT_USD unset)"
LEGACY_CONTRACTS_BASIS = {"mode": "contracts", "value": ORDER_UNIT_CONTRACTS, "label": LEGACY_CONTRACTS_LABEL,
                          "state": "contracts", "et_date": None, "why": None}
# The unit in force, most specific first: unit_override (desk-rescore's file basis), UNIT_PIN (tests: conftest pins
# every test to the legacy contracts basis, as it pins the machine's role; a test of the unit itself lifts the pin),
# the day the running annotate / parlays_doc read (_day_scope), else a fresh read of the wall clock's ET day.
_UNIT_OVERRIDE: ContextVar = ContextVar("desk_unit_override", default=None)
_UNIT_DAY: ContextVar = ContextVar("desk_unit_day", default=None)
UNIT_PIN = None


def unit_basis_usd(dollars, *, state: str = "read", et_date: str | None = None) -> dict:
    """A dollar basis: 1u = `dollars`. The label keeps the pre-v1.2 shape, "1u = $<n>" (item 6: "every page's order
    line stamps the day's unit ("1u = $X") as now")."""
    v = float(dollars)
    return {"mode": "usd", "value": v, "label": f"1u = ${v:g}", "state": state, "et_date": et_date, "why": None}


def unit_unread(why: str, *, state: str = "unread", et_date: str | None = None) -> dict:
    """No unit (item 4): no order line. `value` is the reference fill the exec gate prices at (J1), never an order."""
    return {"mode": "unread", "value": ORDER_UNIT_CONTRACTS, "label": UNIT_UNREAD_LABEL, "state": state,
            "et_date": et_date, "why": why}


def day_unit_basis(now: datetime | None = None) -> dict:
    """The unit of `now`'s ET day, from its file (desk_unit.read_day): read -> its dollars; unread, absent or
    unreadable -> unit_unread. Never another day's file."""
    from src.walters import desk_unit
    day = desk_unit.et_date(now or datetime.now(timezone.utc))
    try:
        rec = desk_unit.read_day(day)
    except desk_unit.UnitPathRefused as e:
        return unit_unread(str(e), et_date=day.isoformat())
    if rec is None:
        return unit_unread("no unit read for this ET day (the day's first slate reads it)", state="absent",
                           et_date=day.isoformat())
    if rec.get("state") == "read" and rec.get("unit_usd"):
        return unit_basis_usd(rec["unit_usd"], et_date=day.isoformat())
    return unit_unread(rec.get("why") or "unit unread", et_date=day.isoformat())


@contextmanager
def unit_override(basis: dict | None):
    """Size under `basis` (desk-rescore: the file's own unit); None leaves the unit as it is."""
    token = _UNIT_OVERRIDE.set(basis) if basis is not None else None
    try:
        yield
    finally:
        if token is not None:
            _UNIT_OVERRIDE.reset(token)


@contextmanager
def _day_scope(now: datetime):
    """annotate / parlays_doc: the day's file is read ONCE for the document, at its own `now`'s ET day."""
    if _UNIT_OVERRIDE.get() is not None or UNIT_PIN is not None:
        yield
        return
    token = _UNIT_DAY.set(day_unit_basis(now))
    try:
        yield
    finally:
        _UNIT_DAY.reset(token)


def unit_size() -> dict:
    """The unit in force (see _UNIT_OVERRIDE): {mode usd | contracts | unread, value, label, state, et_date, why}."""
    return _UNIT_OVERRIDE.get() or UNIT_PIN or _UNIT_DAY.get() or day_unit_basis()


def unit_meta() -> dict:
    """desk_meta.unit: the unit's state and names, and the fractions (item 5: the fraction and the names are code)."""
    u = unit_size()
    return {"state": u.get("state"), "et_date": u.get("et_date"), "label": u["label"], "why": u.get("why"),
            "fraction": UNIT_FRACTION, "half_fraction": HALF_UNIT_FRACTION, "floor_name": UNIT_FLOOR_ENV}


def _contracts_at(units, limit, unit) -> int:
    """floor(units x dollars / limit) on a dollar unit; floor(units x 10) on the contracts basis and on the reference
    fill of an unread day (J1: the exec gate's price only)."""
    if unit["mode"] == "usd":
        return int(units * unit["value"] / limit + 1e-9)
    return int(units * unit["value"] + 1e-9)


# ADDENDUM 179 ITEM 7 (verbatim): "The Desk's "take at the ask, spread < 3¢" doctrine stays; Code adds to the page the
# order's size against the visible depth at the ask (contracts available at the limit, from the orderbook read the
# Desk already makes) and a line "size over the ask's depth: N contracts" when it is — informational". No orderbook
# read exists today (#732): the /markets listing's level sizes are not stored, so no export leg carries a depth, and
# the depth field's key name has not been read from a real response (law 1). The line is therefore UNWIRED: depth_note
# below is the line's text and arithmetic only, and order_line reads no depth from a leg (no field name is guessed).
# Wiring it, on the enumerated name of a stored size, is the follow-up the architect rules on #732 (needs-ruling: the
# premise "the orderbook read the Desk already makes" does not hold). N is the depth at the ask; a TAKE order only.
DEPTH_NOTE = "size over the ask's depth: {} contracts"


def depth_note(contracts, depth) -> str | None:
    """Item 7's line when the order's contracts exceed the depth at the ask, else None (informational)."""
    if contracts is None or depth is None or isinstance(depth, bool):
        return None
    try:
        d = int(float(depth))
    except (TypeError, ValueError):
        return None
    return DEPTH_NOTE.format(d) if contracts > d else None


def _c(x):
    return None if x is None else round(float(x) + 1e-9, 2)


def order_line(r, target: str | None, units, ladder: bool = False) -> dict | None:
    """The order for backing `target` (HOME / AWAY / DRAW) at `units`; None when
    nothing is staked. A dict with ticker None + why when no order can be written."""
    if not units or units <= 0 or not target:
        return None
    legs = (r.get("src") or {}).get("kalshi_legs") or {}
    unit = unit_size()
    out = {"ticker": None, "side": None, "limit": None, "limit_basis": None, "contracts": None,
           "unit": unit["label"], "text": None, "why": None}
    if unit["mode"] == "unread":              # addendum 179 item 4: "unit unread — no order" (law 4)
        out["why"] = UNIT_UNREAD_TEXT
        return out
    opp = {"HOME": "AWAY", "AWAY": "HOME"}.get(target)
    if ladder:
        if target != "AWAY":
            out["why"] = "double chance for a draw pick is 1X or X2 — no single contract; write it by hand"
            return out
        leg, side = legs.get("HOME"), "NO"                    # X2 = NOT HOME
    elif (legs.get(target) or {}).get("ticker"):
        leg, side = legs[target], "YES"
    elif not r.get("threeWay") and opp and (legs.get(opp) or {}).get("ticker"):
        leg, side = legs[opp], "NO"                           # two-way: NO on the opponent = the side
    else:
        out["why"] = f"no Kalshi ticker on file for the {target} leg (sync-kalshi-* after migrate_kalshi_ticker.py)"
        return out
    if not (leg or {}).get("ticker"):
        out["why"] = "no Kalshi ticker on file for the HOME leg (ladder = NO on HOME)"
        return out
    yb, ya = _c(leg.get("bid")), _c(leg.get("ask"))
    bid, ask = (yb, ya) if side == "YES" else (_c(1 - ya) if ya is not None else None,
                                               _c(1 - yb) if yb is not None else None)
    out.update(ticker=leg["ticker"], side=side)
    if EXEC_RULES["on"]:
        if ask is None:
            out["why"] = "no ask to take (doctrine: TAKE at the ask, #87 v1.1) — no limit written"
            return out
        sc = None if bid is None else js_round((ask - bid) * 100)
        jp = join_price(bid, ask)
        if jp is not None:                    # the same price the exec block reports (Codex on #303)
            limit, basis = jp, f"join bid + 1c (spread {sc}c >= {K2['joinMinSpreadC']}c)"
        else:
            limit, basis = ask, "take at the ask" + (f" (spread {sc}c)" if sc is not None else " (no bid)")
    elif bid is None:
        out["why"] = "no bid to join (doctrine: join-bid) — no limit written"
        return out
    elif ask is not None and round(ask - bid, 2) <= 0.01:
        limit, basis = ask, "ask (1c spread: joining = taking)"
    else:
        limit, basis = bid, "join bid"
    if not (0 < limit < 1):
        out["why"] = f"limit {limit} outside (0, 1) — no order written"
        return out
    n = _contracts_at(units, limit, unit)
    out.update(limit=limit, limit_basis=basis, contracts=n)
    if n < 1:
        out["why"] = f"{units}u at {unit['label']} is under one contract at {limit:.2f}"
        return out
    out["text"] = f"BUY {side} {leg['ticker']} @ {limit:.2f} × {n}"
    # addendum 179 item 7's depth line: UNWIRED (no stored depth, no enumerated key name; see DEPTH_NOTE)
    return out


def call_exec_block(r, c):
    """The `exec` block of a model row's desk block: the cost of the row's own order. None for a LADDER (it buys NO
    on HOME, not the pick's leg) and for every no-call kind (no order: a suspended row is not priced). A quarantine
    shadow is priced at its shadow size. desk_block and the rescore read this one function (ARCHITECT 2026-10-08,
    addendum 15 item 2: "A cost is the cost of an order")."""
    if (EXEC_RULES["on"] and c["call"] == "LADDER") or c["passKind"] in NO_CALL_KINDS:
        return None
    return exec_block(r, r["pick"], r["prob"], c.get("execUnits") or (c["shadowUnits"] or None),
                      c["units"] if c.get("execUnits") and c["units"] else None)


LADDER_EXEC_NOTE = ("informational (#689): the ordered NO leg's price; no call, no units and no floor read it, and "
                    "desk.exec stays null for a LADDER")


def ladder_exec_block(r, c):
    """THE LADDER EXEC BLOCK (ARCHITECT 2026-10-26 12:05 ET, #689), verbatim: "Build the exec block for the ordered NO
    leg, informational: it changes no call, no units, no floor." A LADDER on an away pick orders BUY NO on the HOME
    contract (order_line, X2 = NOT HOME); this prices that order as call_exec_block prices a PLAY's: the NO ask
    (1 - the HOME leg's yes bid) plus the taker fee at the order's own contract count (#87 v1.1 (h); the count at the
    join price when the doctrine joins, as order_line writes it). model_p is the model's draw + away; market_p the
    books' fair draw + away; edge_pp = (model_p - cost) x 100. A draw pick has no single contract (1X or X2), and a
    leg with no ticker or no ask is unpriceable: each says why, never priced from another contract. None for every
    row but a LADDER, and with the #87 addendum off (base_v11, the golden's policy)."""
    if not EXEC_RULES["on"] or c["call"] != "LADDER":
        return None
    out = {"leg": "NO on HOME (X2 = not home)", "ticker": None, "model_p": None, "market_p": None, "bid": None,
           "ask": None, "cost": None, "basis": None, "contracts": None, "edge_pp": None, "fee_clears": None,
           "why": None, "informational": True, "note": LADDER_EXEC_NOTE}
    if r["pick"] != "AWAY":
        out["leg"] = None
        out["why"] = "double chance for a draw pick is 1X or X2: no single contract to price"
        return out
    probs, fair = r.get("probsAll") or {}, r.get("fairAll") or {}
    if probs.get("DRAW") is not None and probs.get("AWAY") is not None:
        out["model_p"] = _num(probs["DRAW"] + probs["AWAY"])
    if fair.get("DRAW") is not None and fair.get("AWAY") is not None:
        out["market_p"] = _num(fair["DRAW"] + fair["AWAY"])
    leg = ((r.get("src") or {}).get("kalshi_legs") or {}).get("HOME") or {}
    if not leg.get("ticker"):
        out["why"] = "no Kalshi ticker on file for the HOME leg (ladder = NO on HOME)"
        return out
    # the quotes normalized exactly as order_line normalizes them (cents first, then the NO mirror; Codex on #714),
    # so a sub-cent yes quote prices the very limit the order writes
    yb, ya = _c(leg.get("bid")), _c(leg.get("ask"))
    bid = None if ya is None else _c(1 - ya)
    ask = None if yb is None else _c(1 - yb)
    out.update(ticker=leg["ticker"], bid=bid, ask=ask)
    if ask is None or not (0 < ask < 1):
        out["why"] = "no NO ask to take (the HOME leg has no yes bid)"
        return out
    n = order_contracts(c["units"], join_price(bid, ask) or ask)
    if n is None:
        out["why"] = f"{c['units']}u is under one contract at {ask:.2f}"
        return out
    from src.walters.venue import KALSHI_FEE_M, KALSHI_SERIES_BY_COMPETITION, kalshi_fee
    fee = kalshi_fee(ask, KALSHI_FEE_M.get(KALSHI_SERIES_BY_COMPETITION.get(r.get("comp") or ""), (1.0, None))[0], n=n)
    if fee is None:
        out["why"] = "no taker fee for the NO ask"
        return out
    cost = round(ask + fee, 4)
    e = None if out["model_p"] is None else (out["model_p"] - cost) * 100
    out.update(cost=cost, basis="taker", contracts=n, edge_pp=_num(e), fee_clears=exec_clears(e))
    if unit_size()["mode"] == "unread":          # addendum 179 item 4: the count is the fee's basis, not an order
        out["contracts_basis"] = UNIT_REFERENCE_FILL_TEXT
    if e is None:                                         # priced, but no model draw + away (Codex on #714)
        out["why"] = "no model probability for draw + away (the row carries no draw probability): no edge"
    return out


def desk_block(r, c, v, ven) -> dict:
    """The per-row `desk` field (model rows: the call + any value shadow;
    market-only rows: the venue engine). Every row also carries `venue`, the
    venue engine's verdict as the Cockpit's venue table shows it."""
    if r["marketOnly"]:
        out = {"engine": "venue_edge", "call": ("VENUE" if ven["eligible"] else "PASS"),
               "units": VENUE["units"] if ven["eligible"] else 0}
        if not ven["eligible"]:
            # #181 (ARCHITECT 2026-10-17 16:55 ET, addendum 117 item 2(c)): "Venue rows: the same rule — a PASS venue
            # row is 0 units / class pass. Every PASS, every engine." A VENUE row carries no class (it never did).
            out["cls"] = "pass"
        out.update({"side": ven["side"],
                    "div_pp": _num(ven["divPP"]), "book_p": _num(ven["bookP"]), "kalshi_p": _num(ven["kalP"]),
                    "pass_kind": None if ven["eligible"] else ven["kind"], "reason": ven["reason"],
                    "stale_book_zone": ven["divPP"] is not None and abs(ven["divPP"]) >= VENUE["staleGapPP"],
                    "order": order_line(r, ven["side"], VENUE["units"]) if ven["eligible"] else None,
                    "venue": venue_block(ven)})
        return out
    out = {"engine": "model_edge", "call": c["call"], "units": c["units"], "cls": c["cls"],
           "tier": r["tier"], "pick": r["pick"], "model_p": _num(r["prob"]), "market_ref": _num(c["mktRef"]),
           "reference": ("kalshi_only" if c["kalOnly"] else "books") if c["mktRef"] is not None else None,
           "edge_pp": _num(c["edge"]), "pass_kind": c["passKind"], "tags": c["tags"],
           "reasons": c["reasons"], "reason": " · ".join(c["reasons"]),
           "shadow_units": c["shadowUnits"], "exec": call_exec_block(r, c),
           "value_shadow": None,
           "order": (order_line(r, r["pick"], c["units"], ladder=(c["call"] == "LADDER"))
                     if c["call"] in ("PLAY", "LADDER") else None),
           "venue": venue_block(ven)}
    lx = ladder_exec_block(r, c)
    if lx is not None:                                    # #689: informational; desk.exec stays null for a LADDER
        out["ladder_exec"] = lx
    if c.get("koHold"):                                   # Q3 K3: for the record only; nothing reads it as a call
        out["kalshi_only_hold"] = {k: _num(x) for k, x in c["koHold"].items()}
    if c.get("clockHold"):                                # addendum 72 item 1: both clocks, for the closing file
        from src.ingestion.kalshi_match import et_text
        stored, clock = c["clockHold"]
        out["kickoff_clock"] = {"stored_kickoff": stored.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "stored_kickoff_et": et_text(stored),
                                "kalshi_clock": clock.strftime("%Y-%m-%dT%H:%M:%SZ"), "kalshi_clock_et": et_text(clock),
                                "drift_h": round(abs((clock - stored).total_seconds()) / 3600, 2),
                                "max_drift_h": DESK_CLOCK_DRIFT.total_seconds() / 3600}
    if v:
        out["value_shadow"] = {"side": v["side"], "edge_pp": _num(v["edge"]), "model_p": _num(v["modelP"]),
                               "market_p": _num(v["marketP"]), "role": v["role"], "units": VALUE["units"],
                               "staked": False, "reason": v["reason"], "tags": v["tags"],
                               "exec": exec_block(r, v["side"], v["modelP"], VALUE["units"])}
    return out


def read_ledger_summary(path: str | None) -> tuple[dict, str]:
    """Counts from the Cockpit's ledger summary (bd_ledger_summary_v1) when
    present; else the ruled default 0 (cautious). Returns (counts, source)."""
    zero = {k: 0 for k in COUNT_KEYS}
    if not path or not os.path.isfile(path):
        return zero, "default 0 (no ledger summary)"
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        return zero, f"default 0 (ledger summary unreadable: {e.__class__.__name__})"
    if d.get("kind") != SUMMARY_KIND or not isinstance(d.get("counts"), dict):
        return zero, f"default 0 (not a {SUMMARY_KIND} file)"
    counts = {}
    for k in COUNT_KEYS:
        v = d["counts"].get(k)
        if not isinstance(v, int) or v < 0:
            return zero, f"default 0 (ledger summary: bad {k})"
        counts[k] = v
    v = d["counts"].get(INTL_COUNT_KEY)     # INTL v0 (2): optional; absent or bad = 0 (half units)
    if isinstance(v, int) and v >= 0:
        counts[INTL_COUNT_KEY] = v
    return counts, f"ledger summary {os.path.basename(path)} generated {d.get('generated_at') or '?'}"


def _kalshi_leg_guard_on() -> bool:
    from src.walters.kalshi_legs import GUARD
    return bool(GUARD["on"])


def annotate(doc: dict, *, now: datetime | None = None, counts: dict | None = None,
             counts_source: str = "parameter") -> dict:
    """Attach `desk` to every row the Desk sees, plus `desk_meta`. In place;
    returns the doc. Rows the Cockpit skips (non-scheduled fixtures, rows with
    no probabilities) get no desk block."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_ms = float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // _MS)
    with _day_scope(now):                 # v1.2 (addendum 179 item 3): the day's unit, read once for the file
        ev = evaluate(doc, now_ms, counts)
        calls = {id(r): c for r, c in ev["calls"]}
        values = {id(r): v for r, v in ev["values"]}
        for r, ven in ev["venue"]:
            r["src"]["desk"] = desk_block(r, calls.get(id(r)), values.get(id(r)), ven)
        unit = unit_meta()
    doc["desk_meta"] = {"policy_version": POLICY_VERSION,
                        "as_of": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "counts": ev["counts"], "counts_source": counts_source,
                        "exec_addendum": EXEC_RULES["on"],    # #87 v1.1 (2026-10-06): TAKE cost sizes PLAYs
                        "started_rule": STARTED_RULE["on"],   # #313: a started game is never a new call
                        "venue_quote_age_rule": QUOTE_AGE_RULE["on"],  # 2026-10-07: venue-edge emits no call
                        # MLB big-edge quarantine (ARCHITECT 2026-10-07): the threshold in force, None = off
                        "mlb_quarantine_above_pp": MLB_QUARANTINE["abovePP"] if MLB_QUARANTINE["on"] else None,
                        # Q3 (ARCHITECT 2026-10-08): MLB is never a call on a kalshi-only reference
                        "mlb_kalshi_only_suspended": KALSHI_ONLY_MLB_SUSPENDED["on"],
                        # addendum 36 item 2 (2026-10-10): a default rating on either side is never a call
                        "default_rating_rule": DEFAULT_RATING_RULE["on"],
                        # addendum 40 item 6 (2026-10-11): a one-sided soccer injury list is never a call
                        "injuries_one_sided_rule": INJURIES_ONE_SIDED_RULE["on"],
                        # addendum 40 item 4 (2026-10-11): an empty NFL injury list sizes a PLAY as QB-flagged
                        "nfl_injury_list_empty_rule": INJURY_EMPTY_RULE["on"],
                        # addendum 72 item 1 (2026-10-15): a stored kickoff the Kalshi clock disputes is never a call
                        "kickoff_clock_rule": KICKOFF_CLOCK_RULE["on"],
                        # addendum 83 item 2 (2026-10-16): the Desk's own threshold, inclusive (the matcher's is 2h)
                        "kickoff_clock_hold_h": DESK_CLOCK_DRIFT.total_seconds() / 3600,
                        # addendum 109 item 3 (2026-10-17): under role host (or unknown, addendum 110 item 1) every
                        # soccer model row is PASS host_fence (the role itself is not written here: it would part every
                        # laptop/host desk file in the compare)
                        "host_fence_rule": HOST_FENCE_RULE["on"],
                        # addendum 37 item 3 (2026-10-10): legs of two events are never a pair (read in the export)
                        "kalshi_leg_guard": _kalshi_leg_guard_on(),
                        # addendum 179 (v1.2): the day's unit, its state and the fractions (the label is the order's)
                        "unit": unit,
                        "source": "src/walters/desk_policy.py (F1 port of the Cockpit Desk v1.1; v1.2: the unit, "
                                  "addendum 179)"}
    return doc


def parlays_doc(named_docs, *, now: datetime | None = None, counts: dict | None = None,
                counts_source: str = "parameter") -> dict:
    """Parlay tickets across EVERY file loaded (they are cross-sport: ranked by
    distinct sports first), as one file — the shape the Cockpit renders in
    F1b. `named_docs` = [(file name, doc)] in load order."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_ms = float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // _MS)
    calls = []
    with _day_scope(now):                 # v1.2 (addendum 179 item 3): the legs' orders on the day's unit
        for _, d in named_docs:
            calls += evaluate(d, now_ms, counts)["calls"]
        pstats: dict = {}
        ranked = rank_parlays(calls, pstats)
        tickets = ranked[:PARLAY["top"]]                      # == build_parlays(calls)
        shadow = b_track_shadow(calls, ranked)
        cut = shadow.pop("_cut_by_id")
        blocks = []
        for t in tickets:
            b = parlay_block(t)
            b["b_shadow"] = cut.get(id(t))        # "capped" | "deduped" | None — NOT applied (shadow)
            blocks.append(b)
        unit = unit_meta()
    return {"kind": "desk_parlays_v1", "files": [n for n, _ in named_docs],
            "live_legs": sum(1 for _, c in calls if c["call"] != "PASS"),
            "desk_meta": {"policy_version": POLICY_VERSION,
                          "as_of": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "counts": {k: int((counts or {}).get(k) or 0) for k in COUNT_KEYS},
                          "counts_source": counts_source,
                          # #418 (addendum 112 item 11): the same field the --desk exports carry (annotate)
                          "kalshi_leg_guard": _kalshi_leg_guard_on(),
                          "unit": unit,                     # addendum 179 (v1.2), as annotate's
                          "source": "src/walters/desk_policy.py build_parlays (F1 port, #183 semantics)"},
            "b_track_shadow": shadow,
            "pricing": ({"basis": "executable (ask + taker fee per leg)", "label": PARLAY_LABEL,
                         "unpriced_tickets": pstats.get("unpriced", 0)} if EXEC_RULES["on"] else None),
            "tickets": blocks}


def file_unit_basis(doc: dict):
    """The unit basis the FILE was produced under, read from its own order lines: "1u = $N" -> a dollar basis of N;
    the pre-v1.2 "1u = 10 contracts" label -> the contracts basis; "unit unread" (v1.2, addendum 179 item 4) -> unread
    (never read as 10 contracts). None when the file carries no order (the unit in force then stands)."""
    import re
    for r in (doc.get("predictions") or []) + (doc.get("fixtures") or []):
        u = ((r.get("desk") or {}).get("order") or {}).get("unit")
        if u:
            m = re.match(r"1u = \$([0-9.]+)", u)
            if m:
                return unit_basis_usd(float(m.group(1)), state="file")
            if u == UNIT_UNREAD_LABEL:
                return unit_unread(UNIT_UNREAD_TEXT, state="file")
            return dict(LEGACY_CONTRACTS_BASIS, state="file")
    return None


def unit_basis_text(basis: dict | None) -> str:
    """desk-rescore's unit-basis words. They go into docs/receipts (the public repo), so a dollar unit is named, never
    its figure (addendum 179 item 5: "never the public repo")."""
    if basis is None:
        return "no order in the file: the reference fill"
    if basis["mode"] == "usd":
        return "the file's dollar unit (from the file; its figure is not printed, addendum 179 item 5)"
    if basis["mode"] == "unread":
        return "unit unread (from the file): no order"
    return f"1u = {ORDER_UNIT_CONTRACTS} contracts (from the file)"


def rescore(doc: dict) -> list[dict]:
    """Re-scores under the FILE's own unit basis (file_unit_basis), so the audit is reproducible from the file,
    not the caller's environment or day (Codex on #303; v1.2: no environment is read)."""
    basis = file_unit_basis(doc)
    # a file with no order is priced at the reference fill, never at the caller's day (reproducible from the file)
    with unit_override(basis or unit_unread("no order in the file", state="file")):
        rows = _rescore(doc)
    for x in rows:
        x["unit_basis"] = unit_basis_text(basis)
    return rows


def _rescore(doc: dict) -> list[dict]:
    """#87 v1.1 receipt (ARCHITECT-RULE 2026-10-06: "Sunday's four PLAYs re-scored under rule 3 (which would have
    been halved)"): every row the FILE's own desk called PLAY, re-scored at the file's as_of and counts, without
    and with the addendum. READ-ONLY: works on a copy; the file's published call is reported, never rewritten."""
    meta = doc.get("desk_meta") or {}
    asof = meta.get("as_of")
    now = datetime.fromisoformat(asof.replace("Z", "+00:00")) if asof else datetime.now(timezone.utc)
    now_ms = float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // _MS)
    counts = meta.get("counts") or {}
    out = []
    published = [((r.get("desk") or {}), i) for i, r in enumerate(doc.get("predictions") or [])]
    clean = json.loads(json.dumps(doc))
    for r in clean.get("predictions") or []:
        r.pop("desk", None)
    with addendum_off():                    # quarantine policy held constant: only #87 (+ started) differs
        base = {id(r["src"]): (r, c) for r, c in evaluate(clean, now_ms, counts)["calls"]}
    new = {id(r["src"]): (r, c) for r, c in evaluate(clean, now_ms, counts)["calls"]}
    for d, i in published:
        if d.get("call") != "PLAY":
            continue
        src = clean["predictions"][i]
        if id(src) not in new:
            continue
        r, c = new[id(src)]
        _, b = base[id(src)]
        # ARCHITECT 2026-10-08, addendum 15 item 2 (RULED, verbatim): "A cost is the cost of an order. The
        # desk-rescore line carries the exec cost and exec edge of the row's own exec block under the current Desk,
        # at the file's as_of and counts: the same size, and none where the Desk writes no exec block."
        ex = call_exec_block(r, c)
        out.append({"game": r["game"], "pick": side_name(r, r["pick"]), "kickoff": r["utc"] or None,
                    "model_p": r["prob"], "fair_edge_pp": c["edge"],
                    "exec_cost": ex["cost"] if ex else None, "exec_edge_pp": ex["edge_pp"] if ex else None,
                    # Codex P1 on #369: a suspended row has no live edge (None); its hold's raw edge rides along,
                    # labelled as the hold's (record only, never a live edge)
                    "hold_raw_edge_pp": (c.get("koHold") or {}).get("raw_edge_pp"),
                    "published_units": d.get("units"), "v11_units": b["units"], "addendum_units": c["units"],
                    "addendum_call": c["call"],
                    # the PASS's own reason (the host fence's names the machine's role: host, unset or the value)
                    "pass_reason": (c.get("reasons") or [None])[0] if c["call"] == "PASS" else None,
                    # a published PLAY the CURRENT quarantine now shadows is its own transition, never "halved"
                    # ... and so is one the Q3 suspension now holds (MLB kalshi-only, ARCHITECT 2026-10-08)
                    # ... and one the host fence now holds (addendum 109 item 3, 110 item 1; #410): it is on in both
                    # sides (addendum_off holds it), so 0u = 0u would read "unchanged" on a machine not the laptop
                    "verdict": ("quarantined" if is_quarantine_shadow(c) else
                                "kalshi-only suspended" if c.get("passKind") == KALSHI_ONLY_SUSPENDED_KIND else
                                "host fence" if c.get("passKind") == HOST_FENCE_KIND else
                                "halved" if c["units"] < b["units"] else "unchanged" if c["units"] == b["units"]
                                else "raised")})
    return out


DESK_ENV = "SP_DESK_CALLS"          # "1" = emit; OFF until the parity receipt is ruled
SUMMARY_ENV = "SP_LEDGER_SUMMARY"   # path to the Cockpit's ledger summary JSON
DEFAULT_SUMMARY = os.path.join("exports", "ledger_summary.json")


def desk_enabled(flag: bool | None = None) -> bool:
    if flag is not None:
        return flag
    return os.environ.get(DESK_ENV, "").strip() == "1"


def maybe_annotate(doc: dict, flag: bool | None = None, summary_path: str | None = None,
                   now: datetime | None = None) -> dict:
    """Export hook: annotate when enabled, reading the ledger summary if present. `now`: the export's own decision
    time (default: the wall clock, as before)."""
    if not desk_enabled(flag):
        return doc
    path = summary_path or os.environ.get(SUMMARY_ENV) or DEFAULT_SUMMARY
    counts, src = read_ledger_summary(path)
    return annotate(doc, now=now, counts=counts, counts_source=src)
