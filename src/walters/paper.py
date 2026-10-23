"""THE PAPER LANE for market-only competitions (ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 5), verbatim:

"5. PAPER LANE for market-only competitions (ruled 08:20 ET today, on the operator's "track them as if live"). No
model number means no pick; nothing from this lane enters the ledger, the P&L or the Cockpit positions; the Desk's call
stays PASS noref. Two read-only pieces, small, one PR after item 3 or riding (v):
   (a) coverage's SLATE line for a market-only competition carries, per game, the Kalshi mid (two-way, or the three-way
mids) and, where a shadow export exists for the day, the shadow's pick and value side with their divergence against the
mid, labelled PAPER and never a call. NHL today has a shadow (v7, FAILED gate); CL and NCAA have none and show the
market line only.
   (b) results-tally gains "the close's record" per market-only competition (NHL, NCAA, CL): games with a decided
result and a last two-sided Kalshi quote before kickoff (the kalshi_only close rule), the close's log-loss and the
favourite's record, n. This is the bar a college or cup candidate is scored against (roadmap: "no college candidate has
been scored against a close")."

Addendum 148 item 5 (ARCHITECT 2026-10-20 12:56 ET), verbatim: "5. Carried from 146 and 147: #627 and #628 opened as
ruled; the PAPER lane and the K-track wording ride the next small PR after the slots clear; the Wednesday compile
stands."

THE THREE-WAY CLOSE (ARCHITECT 2026-10-20 17:52 ET, addendum 150, #639), items 1-5 verbatim (item 5 to its rule):
"1. Scope. This close exists for the market-only three-way competitions' PAPER record (146 item 5(b); 149 item 1(d)):
CL now, and every three-way competition the replay prices (ELC and the leagues' lanes, UEL and EFL when their series
exist). It is never the Desk's graded close: a three-way board the Desk grades keeps its book close, labelled when
stale (addendum 145; #629's label). The two never pool; every row of the record names its close kind.
2. The quotes (Q1): ONE capture in which all three legs (HOME, AWAY, TIE) are two-sided within the 2c cap — the last
such capture before kickoff, the same "last two-sided pre-kickoff session" shape as the two-way kalshi_only rule. Legs
from different captures are never combined. A game with no such capture has no close: counted as unpriced on its own
line, never formed from fewer than three legs (law 4).
3. The number (Q2): the three mids sum-normalized to 1 (as export._summarize_kalshi forms the venue fair); the raw sum
is kept on the row as the overround. The record's log-loss is scored on the normalized three-way probabilities.
4. The favourite (Q3): the largest of the three normalized probabilities, the draw included; a row whose favourite is
the draw is counted and flagged on the line. cup_exam.favorite's "the draw is never the favourite" stays the exam's
sign check and is not changed.
5. The result basis (Q4), read from KXUCLGAME's own rules (the kept replay payload of 2026-10-20 11:46Z,
logs/kalshi_replay_20261020T114645Z.json on the laptop, market KXUCLGAME-26OCT20PSGBAR-TIE), verbatim: "If Tie is the
result of the PSG vs Barcelona professional Champions League soccer game originally scheduled for Oct 20, 2026 after 90
minutes plus stoppage time (does not include extra time or penalties), then the market resolves to Yes." The basis is
90 minutes plus stoppage, the same as KXUEFANLGAME's (#325) and intl_shadow.result_90. A knockout game decided in extra
time or on penalties scores as its 90-minute result. [...]"

This module is 5(b) (close_record and its two texts, with the three-way close of addendum 150, three_way_close: the
record's only, never close.py's, never grading_close, the Desk, an export or the matcher) and the pure helpers 5(a)
shares (deploy/hosting/coverage_map.py reads them): the board a game's stored Kalshi rows form, the two-way mid as the
grading close forms it (close.close_from_kalshi, unchanged), the three-way legs' raw mids (display only, never a close
or a reference), and the shadow row's pick and value side against those mids. Nothing here is a call: no ledger, no
P&L, no position, no order, no export.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime, timedelta

from src.walters import close as _close

RULING_5 = ("5. PAPER LANE for market-only competitions (ruled 08:20 ET today, on the operator's \"track them as if "
            "live\"). No model number means no pick; nothing from this lane enters the ledger, the P&L or the Cockpit "
            "positions; the Desk's call stays PASS noref. Two read-only pieces, small, one PR after item 3 or riding "
            "(v):")
RULING_5A = ("(a) coverage's SLATE line for a market-only competition carries, per game, the Kalshi mid (two-way, or "
             "the three-way mids) and, where a shadow export exists for the day, the shadow's pick and value side with "
             "their divergence against the mid, labelled PAPER and never a call. NHL today has a shadow (v7, FAILED "
             "gate); CL and NCAA have none and show the market line only.")
RULING_5B = ("(b) results-tally gains \"the close's record\" per market-only competition (NHL, NCAA, CL): games with "
             "a decided result and a last two-sided Kalshi quote before kickoff (the kalshi_only close rule), the "
             "close's log-loss and the favourite's record, n. This is the bar a college or cup candidate is scored "
             "against (roadmap: \"no college candidate has been scored against a close\").")
PAPER_LABEL = "PAPER, never a call"
PAPER_RULING = "ARCHITECT 2026-10-20, addendum 146 item 5(a)"
CLOSE_RECORD_COMPS = ("NHL", "NCAA", "CL")            # the ruling's own list (5(b)): always printed
TWO_WAY_RECORD = ("NHL", "NCAA")                       # scored by the kalshi_only two-way close, as built
KIND_TWO = "kalshi_only two-way"                       # every line names its close kind (addendum 150 item 1)
KIND_THREE_NAME = "kalshi three-way"                   # the kind's name, on the unpriced line
KIND_THREE = f"{KIND_THREE_NAME} (one capture, normalized)"
LEGS = _close.THREE_WAY                                # HOME, DRAW, AWAY
PICK = {"home_win": "HOME", "draw": "DRAW", "away_win": "AWAY"}     # intl_shadow.PICK / soccer_expansion.PICK
_IN_CHUNK = 500


# --------------------------------------------------------------------------------------------- the board --

def board_of(rows) -> str | None:
    """The board a game's stored Kalshi rows form, from the stored market (never a competition's name): "two-way" when
    every Kalshi row is market ML (the two-way series, kalshi_sync's market="ML"), "three-way" when every one is 1X2
    (the soccer legs HOME/DRAW/AWAY, market="1X2"), "mixed" when both are stored, None with no Kalshi row of either."""
    markets = {getattr(r, "market", None) for r in rows
               if getattr(r, "source", None) == "kalshi" and getattr(r, "market", None) in ("ML", "1X2")}
    if not markets:
        return None
    if markets == {"ML"}:
        return "two-way"
    if markets == {"1X2"}:
        return "three-way"
    return "mixed"


def two_way_mid(rows, before: datetime | None) -> dict | None:
    """The code's Kalshi mid on a two-way board: close.close_from_kalshi(rows, before, BINARY), unchanged (the HOME
    leg's last two-sided pre-kickoff quote, its mid, AWAY = 1 - mid, the 2c cap, no older quote substituted)."""
    return _close.close_from_kalshi(rows, before, _close.BINARY)


def leg_mids(rows, before: datetime | None) -> dict:
    """{HOME|DRAW|AWAY: {"mid", "bid", "ask", "spread_c", "captured_at"} or None} on a three-way board: per selection,
    close_from_kalshi's own filters (source kalshi, market 1X2, captured before `before`, both quotes stored; the newest
    such row; 0 <= bid <= ask <= 1, ask > 0, bid < 1; the 2c cap, desk_policy.KALSHI_ONLY["maxSpreadC"] with js_round),
    and its raw mid (bid + ask) / 2, never normalized. A leg whose newest two-sided quote fails is None (an older quote
    is never substituted).
    Display only (addendum 146 item 5(a)); never a close or a reference (close.py: a three-way board takes no Kalshi
    close)."""
    from src.walters.desk_policy import KALSHI_ONLY, js_round
    out: dict = {}
    for sel in LEGS:
        pre = _leg_pre(rows, sel, before)
        if not pre:
            out[sel] = None
            continue
        k = max(pre, key=lambda x: x.captured_at)
        bid, ask = float(k.yes_bid), float(k.yes_ask)
        if not (0.0 <= bid <= ask <= 1.0) or ask <= 0.0 or bid >= 1.0 \
                or js_round((ask - bid) * 100) > KALSHI_ONLY["maxSpreadC"]:
            out[sel] = None
            continue
        out[sel] = {"mid": (bid + ask) / 2, "bid": bid, "ask": ask, "spread_c": round((ask - bid) * 100, 1),
                    "captured_at": k.captured_at}
    return out


def _leg_pre(rows, sel, before: datetime | None) -> list:
    """leg_mids' candidate rows of one selection: source kalshi, market 1X2, a stored capture time before `before`,
    yes bid and yes ask both stored."""
    return [x for x in rows
            if getattr(x, "source", None) == "kalshi" and getattr(x, "market", None) == "1X2"
            and x.selection == sel and x.captured_at is not None and (before is None or x.captured_at < before)
            and getattr(x, "yes_bid", None) is not None and getattr(x, "yes_ask", None) is not None]


def leg_mids_read(rows, before: datetime | None) -> list:
    """The rows leg_mids reads (#641 item 1, ARCHITECT 2026-10-21, addendum 152 item 4(a)): per leg its newest
    candidate row (_leg_pre; leg_mids' `max`), and every other candidate of that leg tied with it at that capture time
    (all judged, as kalshi_legs judges legs tied at one capture, Codex on #414). [] when no leg has one."""
    out: list = []
    for sel in LEGS:
        pre = _leg_pre(rows, sel, before)
        if pre:
            t = max(x.captured_at for x in pre)
            out += [x for x in pre if x.captured_at == t]
    return out


# ------------------------------------------------------------------------------------------- the shadow --

def shadow_comps() -> dict[str, frozenset]:
    """{shadow module: the competitions its shadow export writes rows for}, read from each module's own code (law 1),
    so coverage's PAPER line hides only a failed module's competitions (Codex round 1 P2 on #640): nhl_shadow.build_rows'
    `Competition.code == "NHL"` (the module keeps it as a literal, no constant), intl_shadow.build_rows' stream
    (intl_elo.STREAM_CODES less FRIENDLY), ncaa_shadow.COMPETITION, soccer_expansion.LEAGUES. The keys are
    coverage_map.SHADOW_EXPORTS' modules (a test pins both)."""
    from src.walters import intl_elo as ie
    from src.walters.ncaa_shadow import COMPETITION
    from src.walters.soccer_expansion import LEAGUES
    return {"src.walters.nhl_shadow": frozenset({"NHL"}),
            "src.walters.intl_shadow": frozenset(c for c in ie.STREAM_CODES if c != ie.FRIENDLY),
            "src.walters.ncaa_shadow": frozenset({COMPETITION}),
            "src.walters.soccer_expansion": frozenset(LEAGUES)}


PROB_KEYS = ("home_win_prob", "draw_prob", "away_win_prob")


def _prob(x) -> float | None:
    """A stored probability when it is a real finite number (never a bool, a text or NaN), else None (law 4)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def unreadable(pred) -> bool:
    """True when a shadow row's prediction cannot be read: not a dict, a probability stored (not null) that is not a
    real finite number, or a top pick stored that is not text. Such a row is never shown and never guessed (law 4)."""
    if not isinstance(pred, dict):
        return True
    if any(pred.get(k) is not None and _prob(pred.get(k)) is None for k in PROB_KEYS):
        return True
    return pred.get("top_pick") is not None and not isinstance(pred.get("top_pick"), str)


def _r9(x: float) -> float:
    """Rounded to 9 decimals before a comparison, so float noise never makes a side exceed its mid (intl_shadow's
    div_bucket rule)."""
    return round(x, 9)


# The value side is judged at the printed precision (one decimal in pp): a side less than 0.05pp above its mid prints
# +0.0pp and is not a value side (a reading for the architect, R18)
BELOW_PRINT = "no side above its mid by 0.05pp or more, the printed precision"
_WAYS = {2: "two-way", 3: "three-way"}


def _differ(n_pred: int, n_board: int) -> str:
    """The reason a prediction is not judged on a board of another shape (never on two of three legs): "a two-way
    prediction on a three-way board" or the reverse."""
    return (f"a {_WAYS.get(n_pred, f'{n_pred}-way')} prediction on a {_WAYS.get(n_board, f'{n_board}-way')} "
            "board")


def board_differs(why) -> bool:
    """True when shadow_view's value_why is _differ's (the prediction is not the board's shape: not judged)."""
    return isinstance(why, str) and why.endswith("-way board")


def shadow_view(pred: dict, fair: dict | None) -> dict:
    """Pure. The shadow row's pick and value side against the Kalshi mids `fair` ({side: mid}, one key per leg of the
    board, None for a leg with no mid; None or {} = no mid). pick: the shadow's top pick (intl_shadow.PICK);
    pick_div_pp: (model p - mid) x 100 on the pick, when that mid exists and the prediction has the board's legs.
    value side: the side with the largest model p - mid above zero (the pick's own side eligible), no floor beyond the
    printed precision (never the Desk's 4pp: never a call): a side less than 0.05pp above its mid prints +0.0pp and is
    none (BELOW_PRINT); none when no side is above its mid (two-way exact equality) or two sides tie at the top; on a
    three-way prediction judged only when all three legs have a mid ("a leg has no mid"); a prediction whose legs are
    not the board's (a two-way prediction on a three-way board, or the reverse) is never judged and carries no
    divergence. value_why says why there is none: "no mid", "a leg has no mid", "a two-way prediction on a three-way
    board" (or the reverse), "no side above its mid", BELOW_PRINT or "two sides tie above their mids". pick_div_pp and
    value_div_pp are rounded to 9 decimals, so the printed figure is the judged one. Only real finite probabilities
    and a text top pick are read (a value of any other kind reads as absent; the coverage line refuses such a row
    first, `unreadable`)."""
    probs = {"HOME": _prob(pred.get("home_win_prob")), "AWAY": _prob(pred.get("away_win_prob"))}
    three = pred.get("draw_prob") is not None
    if three:
        probs["DRAW"] = _prob(pred.get("draw_prob"))
    top_pick = pred.get("top_pick")
    pick = PICK.get(top_pick) if isinstance(top_pick, str) else None
    board = set(fair or {})                                 # the board's legs, priced or not
    fair = {k: v for k, v in (fair or {}).items() if v is not None}
    p_pick = probs.get(pick)
    sides = [k for k in LEGS if k in probs]
    differ = bool(board) and board != set(sides)
    out = {"pick": pick, "pick_p": p_pick,
           "pick_div_pp": (_r9((p_pick - fair[pick]) * 100) if p_pick is not None and pick in fair and not differ
                           else None),
           "value_side": None, "value_div_pp": None, "value_why": None}
    if not fair:
        out["value_why"] = "no mid"
        return out
    if differ:
        out["value_why"] = _differ(len(sides), len(board))
        return out
    if any(k not in fair or probs.get(k) is None for k in sides):
        out["value_why"] = "a leg has no mid"
        return out
    diffs = {k: _r9(probs[k] - fair[k]) for k in sides}
    best = max(diffs.values())
    top = [k for k in sides if diffs[k] == best]
    if not top or best <= 0:
        out["value_why"] = "no side above its mid"
    elif round(_r9((probs[top[0]] - fair[top[0]]) * 100), 1) <= 0:
        out["value_why"] = BELOW_PRINT
    elif len(top) > 1:
        out["value_why"] = "two sides tie above their mids"
    else:
        out["value_side"], out["value_div_pp"] = top[0], _r9((probs[top[0]] - fair[top[0]]) * 100)
    return out


# ------------------------------------------------------------------------------------- the three-way close --

# Why a game has no three-way close, one count per cause, so every printed reason is true of the games it counts
# (R42 RULED (b), ARCHITECT 2026-10-20 19:54 ET, addendum 151 item 1: the close is the LAST capture before kickoff that
# holds any leg of the game; a later capture holding any of its legs ends the search, and no older capture is
# substituted). The ruled three always print; the fourth prints only when it counts a game (R43: a leg stored twice, a
# non-number and a crossed quote cannot arise from one sync-kalshi-soccer run today).
RULING_R42 = ("1. R42, the three-way close's strict reading: (b). The close is the LAST capture before kickoff that holds "
              "any leg of the game; it forms a close only when that capture holds all three legs two-sided within the 2c "
              "cap; a later capture holding any of the game's legs ENDs the search, and no older capture is substituted. "
              "A run that stored no row is invisible, as you say; the unpriced line counts by cause (\"last capture "
              "incomplete\", \"last capture over the cap\", \"no capture\"). The wider market never gets an older close.")
UNPRICED = (("unpriced_incomplete", "last capture incomplete {k} (a leg missing or one-sided; no older capture "
                                    "substituted)"),
            ("unpriced_cap", "last capture over the cap {k} (no older capture substituted)"),
            ("unpriced_none", "no capture {k}"),
            ("unpriced_other", "last capture fails the close's other checks {k} (a leg stored twice with two quotes, "
                               "a quote that is not a number, a crossed or out-of-range quote, or no normalized sum; no "
                               "older capture substituted)"))


def _quote(x) -> tuple[float, float] | None:
    """(bid, ask) of a stored leg read as finite numbers, or None when either cannot be (law 4: never guessed)."""
    try:
        bid, ask = float(x.yes_bid), float(x.yes_ask)
    except (TypeError, ValueError):
        return None
    return (bid, ask) if math.isfinite(bid) and math.isfinite(ask) else None


def _two_sided(x) -> bool:
    return getattr(x, "yes_bid", None) is not None and getattr(x, "yes_ask", None) is not None


def three_way_close(rows, before: datetime | None) -> dict | None:
    """THE THREE-WAY KALSHI CLOSE of the PAPER record (addendum 150 items 2-3). Pure. The record's close only: never
    close.py's, never grading_close's, the Desk's, an export's or the matcher's (item 1: "The two never pool").
    One capture is one stored captured_at: sync_kalshi_soccer stamps every leg one run stores with its one `now`
    (src/ingestion/kalshi_sync.py: `now = utc_now_naive()` after the fetch, `_store(... now=now, market="1X2" ...)`,
    `captured_at=now`), so the legs are grouped by that value exactly and legs of different captures are never
    combined. The stored vocabulary is HOME / DRAW / AWAY (the Tie leg is placed as DRAW, kalshi_match.place). Rows
    read: source kalshi, market 1X2, a stored capture time before `before` (the kickoff).
    The close (R42 RULED (b), addendum 151 item 1): the LAST capture before kickoff that holds any leg of the game;
    it forms a close only when that capture holds all three legs two-sided (yes bid and yes ask both stored): a later
    capture holding any of the game's legs ends the search, missing a leg or holding a one-sided one (no close; no
    older capture is substituted). If any leg of that capture fails close_from_kalshi's checks (0 <= bid <= ask <= 1, ask > 0, bid < 1; both read as numbers; one quote per
    leg, never a guess between two) or is wider than the 2c cap (desk_policy.KALSHI_ONLY["maxSpreadC"] on js_round of
    the cents, close_from_kalshi's arithmetic), there is no close and no older capture is substituted (the two-way
    rule's shape; the strict reading of "the last such capture").
    The number: the three mids (bid + ask) / 2, sum-normalized by export._summarize_kalshi itself (called, never
    re-derived, its 4-decimal rounding included); its raw sum is kept as `overround`.
    {"fair": {HOME, DRAW, AWAY}, "overround", "captured_at", "kalshi": {leg: {bid, ask, mid, spread_c}}, "kind",
    "source"}, or None: no close (unpriced; _three_way says which of UNPRICED's causes)."""
    return _three_way(rows, before)[0]


def _last_capture(rows, before: datetime | None) -> tuple[dict, datetime | None]:
    """({captured_at: {leg: [rows]}}, the LAST capture before `before` that holds any leg of the game, or None): the
    capture three_way_close reads (R42 RULED (b); rows: source kalshi, market 1X2, a leg of LEGS, a stored capture time
    before the kickoff; one capture is one stored captured_at, matched exactly). A run that stored no row is invisible."""
    caps: dict = {}
    for x in rows:
        if (getattr(x, "source", None) == "kalshi" and getattr(x, "market", None) == "1X2"
                and getattr(x, "selection", None) in LEGS and x.captured_at is not None
                and (before is None or x.captured_at < before)):
            caps.setdefault(x.captured_at, {}).setdefault(x.selection, []).append(x)
    return caps, (max(caps) if caps else None)


def _three_way(rows, before: datetime | None) -> tuple[dict | None, str | None]:
    """(three_way_close's close, None), or (None, the UNPRICED key of the cause): "unpriced_none" (no capture before
    kickoff holds a leg of the game), "unpriced_incomplete" (the last capture misses a leg or holds a one-sided one),
    "unpriced_cap" (the last capture has a leg over the 2c cap), "unpriced_other" (the last capture fails close_from_kalshi's other checks: a leg stored twice with two quotes,
    a quote that is not a number, a crossed or out-of-range quote; or _summarize_kalshi forms no normalized sum). The
    legs are judged in LEGS order and the first that fails names the cause; which games get a close is
    three_way_close's rule, unchanged."""
    from types import SimpleNamespace

    from src.walters.desk_policy import KALSHI_ONLY, js_round
    from src.walters.export import _summarize_kalshi
    caps, t = _last_capture(rows, before)
    if t is None:
        return None, "unpriced_none"
    if not all(any(_two_sided(r) for r in caps[t].get(k, ())) for k in LEGS):
        return None, "unpriced_incomplete"  # the last capture ends the search: no older capture substituted (R42 (b))
    q: dict = {}
    for k in LEGS:
        got = {_quote(r) for r in caps[t][k] if _two_sided(r)}
        if len(got) != 1 or None in got:
            return None, "unpriced_other"  # two different quotes of one leg in one capture, or not a number
        bid, ask = got.pop()
        if not (0.0 <= bid <= ask <= 1.0) or ask <= 0.0 or bid >= 1.0:
            return None, "unpriced_other"  # close_from_kalshi's bounds; no older capture substituted
        if js_round((ask - bid) * 100) > KALSHI_ONLY["maxSpreadC"]:
            return None, "unpriced_cap"    # the last capture fails the cap: no close; no older one substituted
        q[k] = {"bid": bid, "ask": ask, "mid": (bid + ask) / 2, "spread_c": round((ask - bid) * 100, 1)}
    v = _summarize_kalshi(None, {k: SimpleNamespace(devig_prob=q[k]["mid"], captured_at=t) for k in LEGS},
                          three_way=True)
    if not v or not v.get("normalized") or not v.get("prob"):
        return None, "unpriced_other"
    return {"fair": {k: v["prob"][k] for k in LEGS}, "overround": v["raw_sum"], "captured_at": t, "kalshi": q,
            "kind": KIND_THREE, "source": "kalshi_three_way"}, None


def capture_tickers(conn, ids) -> dict:
    """{odds_snapshots.id: market_ticker} for the stored rows `ids`, read by SQL by row id (the ticker column is
    unmapped: kalshi_legs reads it so, on a Session or a sqlite3 connection, kalshi_legs._rows); {} when the legs guard
    is off or before migrate_kalshi_ticker.py (no ticker column: every leg reads as untickered, as kalshi_legs reads
    it). Read-only."""
    from src.walters import kalshi_legs
    ids = sorted({int(i) for i in ids if i is not None})
    if not kalshi_legs.GUARD["on"] or not ids or not kalshi_legs.has_tickers(conn):
        return {}
    out: dict = {}
    for k in range(0, len(ids), _IN_CHUNK):
        chunk = ids[k:k + _IN_CHUNK]
        for i, tic in kalshi_legs._rows(conn, f"SELECT id, market_ticker FROM odds_snapshots WHERE id IN "
                                              f"({','.join('?' * len(chunk))})", chunk):
            out[i] = tic
    return out


def capture_mismatched(rows, tickers: dict, match_id, homes: dict | None = None,
                       current: dict | None = None) -> list[str] | None:
    """The events of the ONE capture a three-way close reads (Codex round 1 P1 on #640, R47), when its legs name more
    than one: kalshi_legs.judge, unchanged (its event-of-ticker rule, kalshi_legs.event_of), on `rows`, every stored
    HOME / DRAW / AWAY row of that capture (_last_capture's; all of a leg's rows in it judged, as kalshi_legs judges legs
    tied at one capture), each row's ticker from `tickers` (capture_tickers, by row id). A row with no stored ticker
    names no event (addendum 37 item 3: "Legs with no stored ticker are read as before"). `homes`
    (kalshi_legs.homes_of over the capture's events) carries the ruled second clause, "that event's current legs sit
    on no other game": a capture of one event whose current legs belong to another game is mismatched too.
    `current` (the game's {selection: set of tickers}, kalshi_legs.current_tickers: each side's newest legs) is judged
    together with the capture, as the two-way check judges its row (close_row_mismatched), RULED (ARCHITECT
    2026-10-21, addendum 152 item 4(a), #641 item 2): "the three-way PAPER check judges as the two-way one does — the
    newest legs are passed into capture_mismatched, so a capture whose event no game's current legs carry is
    mismatched, not priced." Else None."""
    from src.walters.kalshi_legs import judge
    by_side: dict = {sel: set(ts) for sel, ts in (current or {}).items()}
    for x in rows:
        by_side.setdefault(x.selection, set()).add(tickers.get(getattr(x, "id", None)))
    return judge(by_side, homes or {}, match_id)


# ----------------------------------------------------------------------------- the two-way close's row --

def _kalshi_close_pre(rows, before: datetime | None) -> list:
    """close.close_from_kalshi's candidate rows, its filters mirrored (src/walters/close.py close_from_kalshi's `pre`):
    source kalshi, selection HOME, a stored capture time before `before`, market in close.KALSHI_CLOSE_MARKETS, yes
    bid and yes ask both stored."""
    return [x for x in rows
            if getattr(x, "source", None) == "kalshi" and x.selection == "HOME" and x.captured_at is not None
            and getattr(x, "market", None) in _close.KALSHI_CLOSE_MARKETS
            and (before is None or x.captured_at < before)
            and getattr(x, "yes_bid", None) is not None and getattr(x, "yes_ask", None) is not None]


def kalshi_close_row(rows, before: datetime | None):
    """The exact HOME row close.close_from_kalshi(rows, before, BINARY) reads (Codex round 2 P1 on #640, R47): its
    filters (_kalshi_close_pre) and its `max(pre, key=captured_at)`, so the first of a tie in `rows` order, as max
    keeps it; None when it reads none. The row read, whether or not its quote then passes the bounds and the 2c cap
    (failing them, close_from_kalshi gives no close; no older quote is substituted). close.py is not changed; a test
    pins that this row and close_from_kalshi's close agree on the same rows."""
    pre = _kalshi_close_pre(rows, before)
    return max(pre, key=lambda x: x.captured_at) if pre else None


def kalshi_close_read(rows, before: datetime | None) -> list:
    """[] when close_from_kalshi reads no row; else the row it reads (kalshi_close_row) first, then every other
    candidate HOME row tied with it at that capture time (all judged, as kalshi_legs judges legs tied at one capture,
    Codex on #414: "whichever a reader keeps, all are judged")."""
    k = kalshi_close_row(rows, before)
    if k is None:
        return []
    return [k, *(x for x in _kalshi_close_pre(rows, before) if x is not k and x.captured_at == k.captured_at)]


def close_row_mismatched(read, tickers: dict, current: dict | None, match_id,
                         homes: dict | None = None) -> list[str] | None:
    """The events, when they are mismatched, of the row(s) a PAPER close or mid reads (`read`: kalshi_close_read's HOME
    row(s) for the two-way close and mid, leg_mids_read's rows for the three-way mids, #641 item 1; each row judged on
    its own selection) together with each side's newest leg (`current`: the game's {selection: set of tickers} from
    kalshi_legs.current_tickers, the ruled guard's current legs, unchanged): kalshi_legs.judge, unchanged, on the
    union (Codex round 2 P1 on #640, R47: the guard passed the newest legs while close_from_kalshi read an older
    two-sided HOME quote of another event). Each read row's ticker from `tickers` (capture_tickers, by row id); a row
    with no stored ticker names no event (addendum 37 item 3: "Legs with no stored ticker are read as before"). `homes`
    (kalshi_legs.homes_of over their events) carries the ruled second clause, "that event's current legs sit on no
    other game". None when the close reads no row, or when they read as a set."""
    if not read:
        return None
    from src.walters.kalshi_legs import judge
    by_side = {sel: set(ts) for sel, ts in (current or {}).items()}
    for x in read:
        by_side.setdefault(x.selection, set()).add(tickers.get(getattr(x, "id", None)))
    return judge(by_side, homes or {}, match_id)


def two_way_legs(s, games, snaps: dict) -> tuple[dict, dict, dict]:
    """(tickers, current, homes) for close_row_mismatched over `games` (a session's Match rows; `snaps` their stored
    rows by match id): the market_ticker of every row the two-way close reads (kalshi_close_read; capture_tickers, by
    row id), each game's newest legs (kalshi_legs.current_tickers, unchanged) and kalshi_legs.homes_of over all their
    events. ({}, {}, {}) with the legs guard off or before migrate_kalshi_ticker.py (every leg reads as untickered, as
    kalshi_legs reads it). Read-only."""
    from src.walters import kalshi_legs
    ids = [m.id for m in games]
    if not ids or not kalshi_legs.GUARD["on"] or not kalshi_legs.has_tickers(s):
        return {}, {}, {}
    tickers = capture_tickers(s, [x.id for m in games for x in kalshi_close_read(snaps.get(m.id, []), m.utc_date)])
    current = kalshi_legs.current_tickers(s, ids)
    events = {kalshi_legs.event_of(t) for t in tickers.values()}
    events |= {kalshi_legs.event_of(t) for legs in current.values() for ts in legs.values() for t in ts}
    return tickers, current, kalshi_legs.homes_of(s, events)


def favourite_3(fair: dict) -> str:
    """The favourite on a three-way close (addendum 150 item 4): the side with the largest normalized probability, the
    draw included; EVEN on an exact tie at the top (in n and the log-loss, outside the favourite's record, as R27).
    cup_exam.favorite (the exam's two-way sign check) is not used and not changed."""
    top = max(fair[k] for k in LEGS)
    sides = [k for k in LEGS if fair[k] == top]
    return sides[0] if len(sides) == 1 else "EVEN"


# ------------------------------------------------------------------------------------ the close's record --

def _result(s, m, code: str) -> tuple[str | None, str | None]:
    """(the side that won, None) or (None, the reason it is left out): NCAA reads ncaa_shadow._result (the CFBD label
    first, else the matches row); a level NCAA score is a tie (college football cannot tie: a data defect). Any other
    competition: both scores stored and not level (NHL's FT/AOT/AP include overtime and the shootout)."""
    if code == "NCAA":
        from src.walters.ncaa_shadow import _result as _ncaa_result
        res = _ncaa_result(s, m)
        if res is None:
            return None, "no_result"
        hs, as_ = res[0], res[1]
        if hs is None or as_ is None:
            return None, "no_result"
        if hs == as_:
            return None, "tie"
        return ("HOME" if hs > as_ else "AWAY"), None
    if m.home_score is None or m.away_score is None or m.home_score == m.away_score:
        return None, "no_result"
    return ("HOME" if m.home_score > m.away_score else "AWAY"), None


def _empty(finished: int, kind: str = KIND_TWO) -> dict:
    if kind == KIND_THREE:
        return {"kind": kind, "finished": finished, "n": 0, "ll_sum": 0.0, "fav_w": 0, "fav_d": 0, "even": 0,
                "draw_fav": 0, "over_sum": 0.0, "no_result": 0, "mismatched": 0, "unpriced": 0,
                **{key: 0 for key, _ in UNPRICED}, "rows": []}
    return {"kind": kind, "finished": finished, "n": 0, "ll_sum": 0.0, "fav_w": 0, "fav_d": 0, "even": 0,
            "no_result": 0, "tie": 0, "mismatched": 0, "no_close": 0, "three_way": 0}


def three_way_comps() -> tuple[str, ...]:
    """The market-only competitions the three-way close may score beside CL (addendum 150 item 1: "every three-way
    competition the replay prices"): the code's own market-only sets, imported, never copied (the src side of
    coverage_map.market_only_sets: desk_policy.SHADOW_VENUE_COMPS, which chains.EXPANSION_CODES and
    KALSHI_CAPTURE_ONLY equal; cup_coeff.EXAM_COMPS; export._MARKET_ONLY_REASON), less the ruling's own three.
    close_record keeps the soccer ones (a three-way board) and prints one only when a FINISHED game of its window
    holds a stored Kalshi 1X2 leg (the reading of "the replay prices")."""
    from src.walters.cup_coeff import EXAM_COMPS
    from src.walters.desk_policy import SHADOW_VENUE_COMPS
    from src.walters.export import _MARKET_ONLY_REASON
    return tuple(sorted((set(SHADOW_VENUE_COMPS) | set(EXAM_COMPS) | set(_MARKET_ONLY_REASON))
                        - set(CLOSE_RECORD_COMPS)))


def _score_three(rec: dict, m, snaps, mism: dict, tickers: dict | None = None, homes: dict | None = None,
                 current: dict | None = None) -> None:
    """One game of a three-way competition, in this order of exclusion: no decided 90-minute result
    (intl_shadow.result_90, unchanged: the _90 score columns, else a FT row's score; a knockout decided in extra time
    or on penalties is its 90-minute result), mismatched legs (each side's newest leg, kalshi_legs.mismatched as ruled,
    then the legs of the capture the close reads judged with those newest legs (`current`), capture_mismatched: Codex
    round 1 P1 on #640, R47, #641 item 2 RULED; no close is formed from legs of two events), unpriced (no three-way
    close)."""
    from src.walters.intl_shadow import OUTCOME_SIDE, result_90
    from src.walters.vs_close import log_loss
    res = result_90(m)
    if res is None:
        rec["no_result"] += 1
        return
    if m.id in mism:
        rec["mismatched"] += 1
        return
    caps, t = _last_capture(snaps, m.utc_date)        # the capture the close reads (none: unpriced, below)
    if t is not None and capture_mismatched([r for legs in caps[t].values() for r in legs], tickers or {}, m.id,
                                            homes, current):
        rec["mismatched"] += 1             # its legs name two events: no close, never priced (Codex on #640, R47)
        return
    cl, why = _three_way(snaps, m.utc_date)
    if cl is None:
        rec["unpriced"] += 1
        rec[why] += 1                      # its cause (UNPRICED), so the unpriced line's every reason is true
        return
    side, fair = OUTCOME_SIDE[res], cl["fair"]
    ll = log_loss(fair[side])
    fav = favourite_3(fair)
    rec["n"] += 1
    rec["ll_sum"] += ll
    rec["over_sum"] += cl["overround"]
    if fav == "EVEN":
        rec["even"] += 1
    else:
        rec["fav_d"] += 1
        rec["fav_w"] += 1 if fav == side else 0
        rec["draw_fav"] += 1 if fav == "DRAW" else 0
    rec["rows"].append({"match_id": m.id, "kind": cl["kind"], "result": side, "fair": dict(fair),
                        "overround": cl["overround"], "captured_at": cl["captured_at"], "log_loss": ll,
                        "favourite": fav})                 # every row names its close kind (addendum 150 item 1)


def _kalshi_snaps(s, ids) -> dict:
    """{match_id: [the stored rows the Kalshi close reads]} for the games `ids` (close.kalshi_close_market_filter)."""
    from sqlalchemy import select

    from src.db.schema import OddsSnapshot
    snaps: dict = {}
    for k in range(0, len(ids), _IN_CHUNK):
        for x in s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id.in_(ids[k:k + _IN_CHUNK]),
                                                      _close.kalshi_close_market_filter(OddsSnapshot))).scalars():
            snaps.setdefault(x.match_id, []).append(x)
    return snaps


def _three_way_guards(s, ids, snaps) -> tuple[dict, dict, dict]:
    """(tickers, current, homes) the three-way score's mismatched-capture guard reads: the captured legs' tickers,
    each side's newest legs judged with the capture (#641), and the events' home teams (Codex on #640)."""
    from src.walters import kalshi_legs
    current: dict = {}
    tickers = capture_tickers(s, [x.id for v in snaps.values() for x in v if x.source == "kalshi" and x.market == "1X2"])
    if tickers:
        current = kalshi_legs.current_tickers(s, ids)
    events = {kalshi_legs.event_of(t) for t in tickers.values()}
    events |= {kalshi_legs.event_of(t) for legs in current.values() for ts in legs.values() for t in ts}
    homes = kalshi_legs.homes_of(s, events) if tickers else {}
    return tickers, current, homes


def close_record(days: int, now: datetime | None = None) -> dict:
    """{code: record}, each record naming its close kind (`kind`); the two kinds never pool. The FINISHED games of
    the last `days` days on the kickoff in this machine's DB.
    NHL and NCAA (TWO_WAY_RECORD), as built: each game scored against close.close_from_kalshi (the kalshi_only close,
    called directly: books are not read) after the mismatched-legs guard (kalshi_legs.mismatched, each side's newest
    leg), then the HOME row the close reads judged with those newest legs (close_row_mismatched: Codex round 2 P1 on
    #640, R47; close.py unchanged), in this order of exclusion: a three-way board (the rule is two-way only), no
    decided result (or an NCAA tie, a data defect), mismatched legs, no Kalshi close. Scored: the log-loss of the
    outcome that happened (vs_close.log_loss) and the favourite (cup_exam.favorite on the close; EVEN counts in n and
    the log-loss, outside the favourite's record).
    CL always, and each other market-only three-way competition (three_way_comps, soccer in this DB) whose window
    holds a stored Kalshi 1X2 leg: three_way_close (addendum 150), _score_three's order of exclusion, the log-loss on
    the normalized three-way probabilities, favourite_3 (the draw included, flagged), the overround and the close
    kind kept per row, each unpriced game counted by its cause (UNPRICED).
    Read-only: one session, rolled back."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport
    from src.timeutil import utc_now_naive
    from src.walters import kalshi_legs
    from src.walters.cup_exam import favorite
    from src.walters.vs_close import log_loss

    now = now or utc_now_naive()
    out: dict = {}
    with session_scope() as s:
        soccer = set(s.execute(select(Competition.code).where(Competition.sport == Sport.SOCCER)).scalars())
        for code in (*CLOSE_RECORD_COMPS, *(c for c in three_way_comps() if c in soccer)):
            three = code not in TWO_WAY_RECORD
            games = list(s.execute(
                select(Match).join(Competition, Competition.id == Match.competition_id)
                .where(Competition.code == code, Match.status == MatchStatus.FINISHED,
                       Match.utc_date >= now - timedelta(days=days))
                .order_by(Match.utc_date, Match.id)).scalars())
            ids = [m.id for m in games]
            snaps = _kalshi_snaps(s, ids)
            if code not in CLOSE_RECORD_COMPS and not any(
                    x.source == "kalshi" and x.market == "1X2" for v in snaps.values() for x in v):
                continue                       # no stored Kalshi three-way leg in the window: nothing printed
            mism = kalshi_legs.mismatched(s, ids) if ids else {}
            if three:
                tickers, current, homes = _three_way_guards(s, ids, snaps)
            else:                                              # the rows the two-way close reads (Codex round 2)
                tickers, current, homes = two_way_legs(s, games, snaps)
            rec = _empty(len(games), KIND_THREE if three else KIND_TWO)
            for m in games:
                if three:
                    _score_three(rec, m, snaps.get(m.id, []), mism, tickers, homes, current.get(m.id))
                    continue
                if tuple(_close.outcomes_for(m.sport)) != _close.BINARY:
                    rec["three_way"] += 1
                    continue
                side, why = _result(s, m, code)
                if why:
                    rec[why] += 1
                    continue
                if m.id in mism:
                    rec["mismatched"] += 1
                    continue
                cs = snaps.get(m.id, [])
                if close_row_mismatched(kalshi_close_read(cs, m.utc_date), tickers, current.get(m.id), m.id, homes):
                    rec["mismatched"] += 1     # the row the close reads names another event: no close (R47)
                    continue
                cl = _close.close_from_kalshi(cs, m.utc_date, _close.BINARY)
                if cl is None:
                    rec["no_close"] += 1
                    continue
                fair = cl["fair"]
                rec["n"] += 1
                rec["ll_sum"] += log_loss(fair[side])
                fav = favorite(fair["HOME"], fair["AWAY"])
                if fav == "EVEN":
                    rec["even"] += 1
                else:
                    rec["fav_d"] += 1
                    rec["fav_w"] += 1 if fav == side else 0
            out[code] = rec
        s.rollback()
    return out


LEAGUES = ("SA", "BL1", "FL1", "ELC")                  # the leagues lane's competitions (docs/roadmap.json, #322)
WINDOW_GAMES = 60                                      # addendum 155 item 4(b): the first 60 FINISHED games per league


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _quality(q: dict, m, rows, tickers: dict, bucket: str) -> None:
    """ARCHITECT 2026-10-23, addendum 158 item 2(b): one FINISHED game's capture quality, by the kickoff's UTC weekday.
    bucket: the close record's own outcome for the game ('n' = a qualifying three-way close, R42(b)). The controlling
    capture is the one three_way_close reads (the last before kickoff holding a leg): its age (kickoff - captured_at),
    its provenance (the legs' source, and the events their stored tickers name). SUPERSEDED: the controlling capture
    forms no close (incomplete, over the cap, other checks) while an OLDER capture before kickoff would have (the R42(b)
    rule substitutes none: it is counted, never used)."""
    from src.walters import kalshi_legs
    day = WEEKDAYS[m.utc_date.weekday()] if m.utc_date else "?"
    d = q["by_weekday"].setdefault(day, Counter())
    d["finished"] += 1
    d[bucket] += 1
    caps, t = _last_capture(rows, m.utc_date)
    if t is None:
        return
    q.setdefault("ages", {}).setdefault(day, []).append((m.utc_date - t).total_seconds() / 3600.0)
    legs = [r for legs in caps[t].values() for r in legs]
    q["sources"].update(str(getattr(r, "source", None)) for r in legs)
    q["events"].update(kalshi_legs.event_of(tickers[r.id]) if tickers.get(r.id) else "(no ticker)" for r in legs)
    if bucket.startswith("unpriced_") and bucket != "unpriced_none":
        for older in sorted((x for x in caps if x < t), reverse=True):
            cl, _ = _three_way(rows, older + timedelta(microseconds=1))
            if cl is not None:
                q["superseded"].append({"match_id": m.id, "kickoff": m.utc_date, "controlling": t, "why": bucket,
                                        "older_complete": older})
                break


def quality_lines(code: str, q: dict) -> list[str]:
    """The capture-quality lines of the leagues receipt (158 item 2(b))."""
    import statistics
    L = [f"  - {code} · capture quality (158 item 2(b)), by the kickoff's UTC weekday:"]
    for day in WEEKDAYS:
        d = q["by_weekday"].get(day)
        if not d:
            continue
        ages = q.get("ages", {}).get(day, [])
        age = (f" · controlling capture age median {statistics.median(ages):.1f} h (min {min(ages):.1f}, max "
               f"{max(ages):.1f})" if ages else " · no capture")
        L.append(f"    {day}: finished {d['finished']} · qualifying close {d['n']} ({d['n'] / d['finished']:.0%}) · "
                 f"missing {d['unpriced_none']} · incomplete {d['unpriced_incomplete']} · over-cap {d['unpriced_cap']} · "
                 f"other checks {d['unpriced_other']} · mismatched {d['mismatched']} · no 90-minute result "
                 f"{d['no_result']}{age}")
    L.append("    provenance of the controlling captures' legs: source " + (", ".join(
        f"{k} {v}" for k, v in sorted(q["sources"].items())) or "none") + " · events " + (", ".join(
        f"{k} {v}" for k, v in sorted(q["events"].items())[:8]) or "none")
             + (f" (+{len(q['events']) - 8} more)" if len(q["events"]) > 8 else ""))
    L.append(f"    superseded (a later capture forms no close where an older one would; never substituted): "
             f"{len(q['superseded'])}")
    for c in q["superseded"]:
        L.append(f"      match {c['match_id']} · kickoff {c['kickoff']:%a %Y-%m-%d %H:%M}Z · controlling capture "
                 f"{c['controlling']:%Y-%m-%d %H:%M:%S}Z ({c['why'][len('unpriced_'):]}) · an older complete capture "
                 f"{c['older_complete']:%Y-%m-%d %H:%M:%S}Z")
    return L


def leagues_season(codes, season: str, declared: date, now: datetime | None = None) -> dict:
    """ARCHITECT 2026-10-23, addendum 155 item 4(a) and addendum 156 item 1: per league, the season's games as the
    close's record reads them. Read-only: one session, rolled back.
    - finished: the season's FINISHED games scored against the three-way Kalshi close of addendum 150 exactly as
      close_record scores a three-way competition (_score_three: no 90-minute result, mismatched legs, unpriced by
      cause, else scored), so n and the close's log-loss are the bar's denominator.
    - to_come: the season's games not FINISHED and not a NOT_GAMES status (kalshi_match.NOT_GAMES), read for the
      capture they hold now: the last stored capture (no kickoff bound yet) forming a close by three_way_close's
      rule, or the UNPRICED cause; "no capture" where none holds a leg.
    - projected: the stored fixture list's games of the season (NOT_GAMES left out) whose kickoff's UTC date is on or
      after `declared`, in kickoff order, every game assumed to get a three-way close (156 item 1): the 60th's kickoff
      UTC date, or None with the count when fewer than 60 are stored."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus
    from src.ingestion.kalshi_match import NOT_GAMES
    from src.timeutil import utc_now_naive
    from src.walters import kalshi_legs

    now = now or utc_now_naive()
    out: dict = {}
    with session_scope() as s:
        for code in codes:
            games = list(s.execute(
                select(Match).join(Competition, Competition.id == Match.competition_id)
                .where(Competition.code == code, Match.season == season)
                .order_by(Match.utc_date, Match.id)).scalars())
            seasons = [] if games else sorted({x for x in s.execute(
                select(Match.season).join(Competition, Competition.id == Match.competition_id)
                .where(Competition.code == code)).scalars() if x})
            status = {m.id: str(getattr(m.status, "value", m.status) or "").lower() for m in games}
            fin = [m for m in games if m.status == MatchStatus.FINISHED]
            ahead = [m for m in games if m.status != MatchStatus.FINISHED and status[m.id] not in NOT_GAMES]
            ids = [m.id for m in fin + ahead]
            snaps = _kalshi_snaps(s, ids)
            mism = kalshi_legs.mismatched(s, [m.id for m in fin]) if fin else {}
            tickers, current, homes = _three_way_guards(s, [m.id for m in fin], snaps)
            rec = _empty(len(fin), KIND_THREE)
            quality = {"by_weekday": {}, "superseded": [], "sources": Counter(), "events": Counter()}
            buckets = ("n", "no_result", "mismatched", *(key for key, _ in UNPRICED))
            for m in fin:
                before = {k: rec[k] for k in buckets}
                _score_three(rec, m, snaps.get(m.id, []), mism, tickers, homes, current.get(m.id))
                _quality(quality, m, snaps.get(m.id, []), tickers,
                         next(k for k in buckets if rec[k] != before[k]))
            come = {"n": len(ahead), "close": 0, **{key: 0 for key, _ in UNPRICED}}
            for m in ahead:
                cl, why = _three_way(snaps.get(m.id, []), None)
                come["close" if cl is not None else why] += 1
            fixtures = [m for m in games if status[m.id] not in NOT_GAMES and m.utc_date is not None
                        and m.utc_date.date() >= declared]
            nth = fixtures[WINDOW_GAMES - 1] if len(fixtures) >= WINDOW_GAMES else None
            out[code] = {"games": len(games), "seasons_stored": seasons, "not_games": sum(
                status[m.id] in NOT_GAMES for m in games), "record": rec, "to_come": come, "quality": quality,
                "from_declared": len(fixtures),
                "projected": None if nth is None else {"date": nth.utc_date.date(), "match_id": nth.id}}
        s.rollback()
    return out


CLOSE_HEADER = ("## THE CLOSE'S RECORD — market-only, PAPER (ARCHITECT 2026-10-20, addendum 146 item 5(b); the "
                "three-way close, addendum 150)")
REASONS = (("no_result", "no decided result {k}"),
           ("tie", "tie {k} (college football cannot tie: a data defect)"),
           ("mismatched", "mismatched legs {k}"),
           ("no_close", "no Kalshi close {k} (no two-sided quote before kickoff, or the last one over the 2c cap)"),
           ("three_way", "three-way board {k} (close_from_kalshi is two-way only; a three-way competition's games "
                         "take the three-way close on its own line, never pooled)"))
REASONS_3 = (("no_result", "no decided 90-minute result {k}"),
             ("mismatched", "mismatched legs {k}"))


def _reasons(r: dict, reasons=REASONS) -> str:
    got = [t.format(k=r[key]) for key, t in reasons if r.get(key)]
    return ", ".join(got) if got else "none"


def unpriced_line(code: str, r: dict) -> str:
    """A three-way competition's unpriced games on a line of their own (addendum 150 item 2), its close kind named
    (item 1), split by cause (UNPRICED): the ruled three always (addendum 151 item 1), the fourth only when it counts a
    game."""
    why = [t.format(k=r.get(key, 0)) for key, t in UNPRICED if key != "unpriced_other" or r.get(key)]
    return f"  - {code} · close: {KIND_THREE_NAME} · unpriced {r['unpriced']}: " + "; ".join(why)


def close_record_line(code: str, r: dict) -> str:
    """The competition's line, its close kind named (addendum 150 item 1); a three-way competition's unpriced games
    on a line of their own (item 2, unpriced_line)."""
    three = r.get("kind") == KIND_THREE
    head = f"- {code} · close: {r.get('kind', KIND_TWO)} · "
    why = _reasons(r, REASONS_3 if three else REASONS)
    if not r["n"]:
        body = f"close log-loss — · favourite — · n=0 · finished {r['finished']}; left out: {why}"
    else:
        fav = (f"favourite {r['fav_w']}/{r['fav_d']} ({r['fav_w'] / r['fav_d']:.1%})" if r["fav_d"]
               else "favourite —")
        draw = f" · draw favourite {r['draw_fav']}" if three else ""
        even = f" (even {r['even']})" if r["even"] else ""
        over = f" · overround mean {r['over_sum'] / r['n']:.4f}" if three else ""
        body = (f"close log-loss {r['ll_sum'] / r['n']:.4f} · {fav}{draw} · n={r['n']}{even}{over} · finished "
                f"{r['finished']}; left out: {why}")
    if not three:
        return head + body
    return head + body + "\n" + unpriced_line(code, r)


def close_record_section(rec: dict, days: int) -> str:
    """The RESULTS.md section: the template of the PR's spec, with addendum 150's three-way close."""
    intro = (f"_The bar a college or cup candidate is scored against (roadmap: \"no college candidate has been scored "
             f"against a close\"). Per competition, the FINISHED games of the last {days} days on the kickoff in this "
             "machine's DB that have a decided result and a close; every line names its close kind, and the two "
             f"kinds never pool. close: {KIND_TWO} (NHL, NCAA): the mid of the last two-sided Kalshi HOME quote "
             "before kickoff within the 2c spread cap (src/walters/close.py close_from_kalshi); the favourite is the "
             "side the close prices above the other. close: "
             f"{KIND_THREE} (CL, and each other market-only three-way competition with a stored Kalshi 1X2 leg in the "
             "window; ARCHITECT 2026-10-20, addendum 150; R42 ruled (b), addendum 151 item 1): the last capture before "
             "kickoff that holds any leg of the game, a close only when it holds all three legs (HOME, DRAW, AWAY) "
             "two-sided within the 2c cap (a later capture holding any leg ends the search; no older capture is "
             "substituted, legs of different captures are never combined); the three mids "
             "sum-normalized to 1 as the export forms the venue fair (export._summarize_kalshi), their raw sum the "
             "overround; scored on the 90-minute result (intl_shadow.result_90: 90 minutes plus stoppage, a knockout "
             "decided in extra time or on penalties is its 90-minute result); the favourite is the largest of the "
             "three, the draw included and flagged; a game left with no close is counted unpriced on its own line, by "
             "cause. "
             "Both: on a game whose Kalshi legs read as a set (addendum 37 item 3); books are not read; the close's "
             "log-loss is the mean of -ln(max(p, 1e-12)) of the outcome that happened; an exact tie at the top (a "
             "two-way close of exactly 0.50) has no favourite (it counts in n and the log-loss, not in the record). "
             "Never a call: nothing here enters the ledger, the P&L or a position._")
    body = [close_record_line(code, r) for code, r in rec.items()]
    return "\n".join([CLOSE_HEADER, "", intro, "", *body]) + "\n"


def close_record_console(rec: dict, days: int) -> str:
    """The one console line results-tally reports: each close kind's competitions apart, never pooled."""
    parts = []
    for kind in (KIND_TWO, KIND_THREE):
        mine = [f"{code} n={r['n']}" + (f" (unpriced {r['unpriced']})" if kind == KIND_THREE else "")
                for code, r in rec.items() if r.get("kind", KIND_TWO) == kind]
        if mine:
            parts.append(f"{kind}: " + " · ".join(mine))
    return f"the close's record (PAPER; {days} days): " + "; ".join(parts)
