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
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal

POLICY_VERSION = "v1.1"
INF = math.inf
POLICY = {
    "SOCCER": {"eMin": 4, "eLad": 10, "eHair": 10, "pMin": 0.50, "qNever": False},
    "NFL": {"eMin": 4, "eLad": INF, "eHair": 15, "pMin": 0, "qNever": True},
    "MLB": {"eMin": 4, "eLad": INF, "eHair": 15, "pMin": 0, "qNever": False},
    "NHL": {"passAll": True},
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
        out.append({
            "src": p, "game": f"{_t(away)} @ {_t(home)}", "home": home, "away": away,
            "pick": pick, "prob": best, "mkt": market.get(pick),
            "twoSided": market.get("HOME") is not None and market.get("AWAY") is not None,
            "mktHasDraw": market.get("DRAW") is not None,
            "kal": (p.get("input_quality") or {}).get("kalshi") or None, "sport": sport,
            "utc": p.get("utc_date") or "", "probsAll": probs, "fairAll": market,
            "div": p.get("market_divergence_pp"), "quar": bool(p.get("quarantine")),
            "books": mk.get("bookmaker_count"), "qbs": qbs,
            "stage": p["stage"] if "stage" in p else MISSING,
            "comp": (p.get("competition") or doc.get("sport") or "").upper(),
            "kalProb": kal_from_prediction(p, mk, market),
            "threeWay": market.get("DRAW") is not None or probs.get("DRAW") is not None,
            "kExec": _kexec_of(p, always=True),     # #130: the pre-split alias is retired
            "tier": pr.get("tier") or None, "marketOnly": False})
    return out


def side_name(r, k):
    return r["home"] if k == "HOME" else r["away"] if k == "AWAY" else "Draw"


# ------------------------------------------------------------ venue engine --

def venue_edge(r, now_ms: float) -> dict:
    out = {"eligible": False, "reason": "", "side": None, "divPP": None, "bookP": None, "kalP": None,
           "sides": {}, "kind": None}
    if not r["marketOnly"]:
        out["reason"] = "model sport — model_edge only (venue charter: market-only family)"
        return out
    if r["sport"] == "UNL":
        out["reason"] = "single venue — no pair (UNL)"
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
    was = EXEC_RULES["on"]
    EXEC_RULES["on"] = False
    try:
        yield
    finally:
        EXEC_RULES["on"] = was


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
    """The contract count `order_line` writes for `units` at `limit` (SP_UNIT_USD -> dollars / limit, else
    ORDER_UNIT_CONTRACTS per 1u, floored); None when under one contract or no valid limit."""
    if not units or units <= 0 or limit is None or not (0 < limit < 1):
        return None
    unit = unit_size()
    n = int(units * unit["value"] / limit + 1e-9) if unit["mode"] == "usd" else int(units * unit["value"] + 1e-9)
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
    # (SP_UNIT_USD sizes by limit — Codex on #303)
    limit = join_price(q.get("bid"), ask) or ask
    n = order_contracts(BASE_UNITS if units is None else units, limit)
    if n is None:
        return None
    from src.walters.venue import KALSHI_FEE_M, KALSHI_SERIES_BY_COMPETITION, kalshi_fee
    series = KALSHI_SERIES_BY_COMPETITION.get(r.get("comp") or r.get("sport") or "")
    fee = kalshi_fee(ask, KALSHI_FEE_M.get(series, (1.0, None))[0], n=n)
    return round(ask + fee, 4) if fee is not None else None


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
        out["maker_cost"] = maker_cost_for(r, side)          # reference only: the doctrine takes
        out["doctrine"] = "join" if (jb or {}).get("price") is not None else "take"
        q = side_quotes(r, side) or {}
        lim = join_price(q.get("bid"), q.get("ask")) or q.get("ask")
        out["contracts"] = order_contracts(BASE_UNITS if units is None else units, lim)
        if order_units is not None and order_units != units:
            oc = taker_cost_for(r, side, order_units)
            out.update(order_contracts=order_contracts(order_units, lim), order_cost=oc)
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

def desk_call(r, now_ms: float, postseason_graded: int = 0) -> dict:
    """The Cockpit's policy() body for ONE model-sport row."""
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
        if call == "PLAY" and r["sport"] == "NFL" and r["qbs"]:
            units = min(units, base / 2)
            reasons.append(f"QB-flagged ({', '.join(r['qbs'])}) → half units")
            tags.append("QB-flagged half units")
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
        if edge >= e_hair:
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
            reasons.append(f"QUARANTINE {js_str(r['div'])}pp — contract: never a straight play")
            tags.append("quarantine ≥ 15pp (shadow)")
    if (call == "PASS" and pass_kind == "floor" and not kal_only and r["books"] is not None
            and r["books"] < PASSCLASS["minBooks"]):
        pass_kind = "noref"
        reasons.append(f"books {js_str(r['books'])} < {PASSCLASS['minBooks']} → thin reference")
    if call != "PASS":
        pass_kind = None
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
        b.update(market_basis="executable (Π ask + taker fee)", fair_p=_num(t["pf"]), label=PARLAY_LABEL)
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
    counts = {k: int((counts or {}).get(k) or 0) for k in COUNT_KEYS}
    rows = normalize(doc)
    calls, values, venue = [], [], []
    for r in rows:
        if not r["marketOnly"]:
            calls.append((r, desk_call(r, now_ms, counts["postseason_graded"])))
            v = value_side(r, POLICY.get(r["sport"]) or POLICY["DEFAULT"])
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
#   count  : SP_UNIT_USD (dollars per 1u) set -> floor(units x SP_UNIT_USD / limit);
#            unset -> ORDER_UNIT_CONTRACTS contracts per 1u (floor(units x 10))
ORDER_UNIT_CONTRACTS = 10


def unit_size() -> dict:
    import os
    raw = (os.environ.get("SP_UNIT_USD") or "").strip()
    try:
        v = float(raw)
    except ValueError:
        v = 0.0
    if v > 0:
        return {"mode": "usd", "value": v, "label": f"1u = ${v:g}"}
    return {"mode": "contracts", "value": ORDER_UNIT_CONTRACTS,
            "label": f"1u = {ORDER_UNIT_CONTRACTS} contracts (SP_UNIT_USD unset)"}


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
    n = int(units * unit["value"] / limit + 1e-9) if unit["mode"] == "usd" else int(units * unit["value"] + 1e-9)
    out.update(limit=limit, limit_basis=basis, contracts=n)
    if n < 1:
        out["why"] = f"{units}u at {unit['label']} is under one contract at {limit:.2f}"
        return out
    out["text"] = f"BUY {side} {leg['ticker']} @ {limit:.2f} × {n}"
    return out


def desk_block(r, c, v, ven) -> dict:
    """The per-row `desk` field (model rows: the call + any value shadow;
    market-only rows: the venue engine). Every row also carries `venue`, the
    venue engine's verdict as the Cockpit's venue table shows it."""
    if r["marketOnly"]:
        return {"engine": "venue_edge", "call": ("VENUE" if ven["eligible"] else "PASS"),
                "units": VENUE["units"] if ven["eligible"] else 0, "side": ven["side"],
                "div_pp": _num(ven["divPP"]), "book_p": _num(ven["bookP"]), "kalshi_p": _num(ven["kalP"]),
                "pass_kind": None if ven["eligible"] else ven["kind"], "reason": ven["reason"],
                "stale_book_zone": ven["divPP"] is not None and abs(ven["divPP"]) >= VENUE["staleGapPP"],
                "order": order_line(r, ven["side"], VENUE["units"]) if ven["eligible"] else None,
                "venue": venue_block(ven)}
    out = {"engine": "model_edge", "call": c["call"], "units": c["units"], "cls": c["cls"],
           "tier": r["tier"], "pick": r["pick"], "model_p": _num(r["prob"]), "market_ref": _num(c["mktRef"]),
           "reference": ("kalshi_only" if c["kalOnly"] else "books") if c["mktRef"] is not None else None,
           "edge_pp": _num(c["edge"]), "pass_kind": c["passKind"], "tags": c["tags"],
           "reasons": c["reasons"], "reason": " · ".join(c["reasons"]),
           "shadow_units": c["shadowUnits"], "exec": exec_block(r, r["pick"], r["prob"], c.get("execUnits"),
                                                           c["units"] if c.get("execUnits") and c["units"] else None),
           "value_shadow": None,
           "order": (order_line(r, r["pick"], c["units"], ladder=(c["call"] == "LADDER"))
                     if c["call"] in ("PLAY", "LADDER") else None),
           "venue": venue_block(ven)}
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
    return counts, f"ledger summary {os.path.basename(path)} generated {d.get('generated_at') or '?'}"


def annotate(doc: dict, *, now: datetime | None = None, counts: dict | None = None,
             counts_source: str = "parameter") -> dict:
    """Attach `desk` to every row the Desk sees, plus `desk_meta`. In place;
    returns the doc. Rows the Cockpit skips (non-scheduled fixtures, rows with
    no probabilities) get no desk block."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_ms = float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // _MS)
    ev = evaluate(doc, now_ms, counts)
    calls = {id(r): c for r, c in ev["calls"]}
    values = {id(r): v for r, v in ev["values"]}
    for r, ven in ev["venue"]:
        r["src"]["desk"] = desk_block(r, calls.get(id(r)), values.get(id(r)), ven)
    doc["desk_meta"] = {"policy_version": POLICY_VERSION,
                        "as_of": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "counts": ev["counts"], "counts_source": counts_source,
                        "exec_addendum": EXEC_RULES["on"],    # #87 v1.1 (2026-10-06): TAKE cost sizes PLAYs
                        "source": "src/walters/desk_policy.py (F1 port of the Cockpit Desk v1.1)"}
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
    return {"kind": "desk_parlays_v1", "files": [n for n, _ in named_docs],
            "live_legs": sum(1 for _, c in calls if c["call"] != "PASS"),
            "desk_meta": {"policy_version": POLICY_VERSION,
                          "as_of": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "counts": {k: int((counts or {}).get(k) or 0) for k in COUNT_KEYS},
                          "counts_source": counts_source,
                          "source": "src/walters/desk_policy.py build_parlays (F1 port, #183 semantics)"},
            "b_track_shadow": shadow,
            "pricing": ({"basis": "executable (ask + taker fee per leg)", "label": PARLAY_LABEL,
                         "unpriced_tickets": pstats.get("unpriced", 0)} if EXEC_RULES["on"] else None),
            "tickets": blocks}


def file_unit_basis(doc: dict):
    """The unit sizing the FILE was produced under, read from its own order lines ("1u = $20" -> "20"; "1u = 10
    contracts" -> "" = SP_UNIT_USD unset). None when the file carries no order (the caller's env then stands)."""
    import re
    for r in (doc.get("predictions") or []) + (doc.get("fixtures") or []):
        u = ((r.get("desk") or {}).get("order") or {}).get("unit")
        if u:
            m = re.match(r"1u = \$([0-9.]+)", u)
            return m.group(1) if m else ""
    return None


@contextmanager
def _unit_env(basis):
    was = os.environ.get("SP_UNIT_USD")
    try:
        if basis is not None:
            os.environ["SP_UNIT_USD"] = basis
        yield
    finally:
        if was is None:
            os.environ.pop("SP_UNIT_USD", None)
        else:
            os.environ["SP_UNIT_USD"] = was


def rescore(doc: dict) -> list[dict]:
    """Re-scores under the FILE's own unit basis (file_unit_basis), so the audit is reproducible from the file,
    not the caller's SP_UNIT_USD (Codex on #303)."""
    with _unit_env(file_unit_basis(doc)):
        rows = _rescore(doc)
    for x in rows:
        x["unit_basis"] = unit_size()["label"] if file_unit_basis(doc) is None else (
            f"1u = ${file_unit_basis(doc)} (from the file)" if file_unit_basis(doc) else
            f"1u = {ORDER_UNIT_CONTRACTS} contracts (from the file)")
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
    with base_v11():
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
        dc = desk_cost_for(r, r["pick"], c.get("execUnits"))
        out.append({"game": r["game"], "pick": side_name(r, r["pick"]), "kickoff": r["utc"] or None,
                    "model_p": r["prob"], "fair_edge_pp": c["edge"], "exec_cost": dc["cost"] if dc else None,
                    "exec_edge_pp": exec_edge_pp(r, r["pick"], r["prob"], c.get("execUnits")),
                    "published_units": d.get("units"), "v11_units": b["units"], "addendum_units": c["units"],
                    "addendum_call": c["call"],
                    "verdict": ("halved" if c["units"] < b["units"] else "unchanged" if c["units"] == b["units"]
                                else "raised")})
    return out


DESK_ENV = "SP_DESK_CALLS"          # "1" = emit; OFF until the parity receipt is ruled
SUMMARY_ENV = "SP_LEDGER_SUMMARY"   # path to the Cockpit's ledger summary JSON
DEFAULT_SUMMARY = os.path.join("exports", "ledger_summary.json")


def desk_enabled(flag: bool | None = None) -> bool:
    if flag is not None:
        return flag
    return os.environ.get(DESK_ENV, "").strip() == "1"


def maybe_annotate(doc: dict, flag: bool | None = None, summary_path: str | None = None) -> dict:
    """Export hook: annotate when enabled, reading the ledger summary if present."""
    if not desk_enabled(flag):
        return doc
    path = summary_path or os.environ.get(SUMMARY_ENV) or DEFAULT_SUMMARY
    counts, src = read_ledger_summary(path)
    return annotate(doc, counts=counts, counts_source=src)
