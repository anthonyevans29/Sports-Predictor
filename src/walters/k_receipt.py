"""K-track receipt for the executable-edge ruling (#87) — READ-ONLY.

ARCHITECT 2026-10-06: "K-TRACK RECEIPT for the executable-edge ruling (#87,
two-week window closes 10-07): every ladder captured since 9-23 — spreads,
two-sidedness, fee-clear rate at maker and taker cost, by sport; plus the 4
executed fills' CLV. One command, read-only; the ruling follows the receipt."
#75's call-to-fill reconciliation is folded in (ARCHITECT 2026-10-06, adopted).

LADDER = one Kalshi capture of one game: every stored leg (two-way HOME/AWAY,
soccer HOME/DRAW/AWAY) at one `captured_at`. Per leg:
  two-sided   0 < bid <= ask < 1 (the #286 ruling-9 definition)
  spread      (ask - bid) in cents
  taker cost  ask + fee(0.07 x M_taker, P = ask)            (venue.kalshi_exec)
  maker cost  (bid + 1c) + fee(0.0175 x M_maker, P = bid+1c); none on a 1c
              spread (joining = taking) or when the series' maker M is unknown
FEE-CLEAR is the Desk's own K2 rule, (reference p - cost) >= 4pp
(desk_policy.K2 feeClearsPP), on two references, never pooled:
  model  the live model's latest prediction made at or before the capture, on
         the model's PICK leg (the Desk's exec edge). Live model sports only.
  book   the venue engine's reference: the last complete book session at or
         before the capture, >= 4 books, <= 3h old (desk_policy.VENUE); the
         best leg (fair - cost).
A ladder that cannot be evaluated on a basis is counted as such, never as a
miss. Writes nothing.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

K_WINDOW_FROM = datetime(2026, 9, 23)          # naive UTC: "every ladder captured since 9-23"
K_WINDOW_TO = datetime(2026, 10, 8)            # exclusive: the window closes at the end of 10-07
# Live model sports (CLAUDE.md production state): the model basis exists only here.
MODEL_LIVE = ("MLB", "NFL", "PL")
LEG_ORDER = ("HOME", "DRAW", "AWAY")


CLEAR_EPS = 1e-9     # an exact 4.00pp edge must clear; binary-float subtraction can land a hair below


def _clears(edge_pp: float, floor: float) -> bool:
    return edge_pp >= floor - CLEAR_EPS


def leg_two_sided(bid, ask) -> bool:
    return bid is not None and ask is not None and 0 < bid <= ask < 1


def _pct(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def leg_costs(bid, ask, competition: str) -> dict:
    """The leg's own YES contract priced by the venue fee model (never re-derived here)."""
    from src.walters.venue import kalshi_exec
    k = kalshi_exec(bid, ask, competition)
    return {"taker": k["exec_cost_taker"], "maker": k["exec_cost_maker"]}


def _book_ref(book, t, outcomes):
    """The ladder's own outcome set (a three-way ladder never reads a two-way session)."""
    from src.walters.close import close_from_snapshots
    from src.walters.desk_policy import VENUE
    cl = close_from_snapshots([x for x in book if x.captured_at is not None and x.captured_at <= t],
                              t + timedelta(microseconds=1), tuple(outcomes))
    if cl is None:
        return None, "no book session at or before the capture"
    if (cl["books"] or 0) < VENUE["minBooks"]:
        return None, f"book session {cl['books'] or 0} books < {VENUE['minBooks']}"
    if t - cl["captured_at"] > timedelta(hours=VENUE["maxBookAgeH"]):
        return None, f"book session older than {VENUE['maxBookAgeH']}h"
    return cl["fair"], None


REWRITTEN = ("prediction rewritten after the capture: the predictions table keeps the current row only "
             "(training.py / nfl_predict.py upsert), so no historical model reference exists")


def _model_ref(preds, t):
    """(probs, None) from the latest prediction at or before `t`, else (None, reason). A prediction
    computed AFTER the capture is never used (look-ahead); because re-predicting replaces the row,
    such a capture is reported as REWRITTEN, never silently dropped (Codex on #297)."""
    pre = [p for p in preds if p.computed_at is not None and p.computed_at <= t]
    if not pre:
        return None, (REWRITTEN if any(p.computed_at is not None and p.computed_at > t for p in preds)
                      else "no model prediction for this game")
    p = max(pre, key=lambda x: x.computed_at)
    out = {"HOME": p.home_win_prob, "AWAY": p.away_win_prob}
    if p.draw_prob is not None:
        out["DRAW"] = p.draw_prob
    return out, None


def ladder_row(comp: str, t: datetime, legs: dict, book, preds) -> dict:
    """One ladder: legs {sel: snapshot} at capture `t`."""
    from src.walters.desk_policy import K2
    clear = K2["feeClearsPP"]
    sels = [k for k in LEG_ORDER if k in legs]
    lg = {}
    for k in sels:
        x = legs[k]
        two = leg_two_sided(x.yes_bid, x.yes_ask)
        lg[k] = {"bid": x.yes_bid, "ask": x.yes_ask, "two_sided": two,
                 "spread_c": round((x.yes_ask - x.yes_bid) * 100, 2) if two else None,
                 **(leg_costs(x.yes_bid, x.yes_ask, comp) if two else {"taker": None, "maker": None})}
    complete = len(sels) == (3 if "DRAW" in sels or comp not in ("MLB", "NFL", "NHL", "NCAA") else 2)
    row = {"comp": comp, "captured_at": t, "legs": lg, "complete": complete,
           "two_sided": complete and all(v["two_sided"] for v in lg.values()),
           "fee_clear": {}}
    if not row["two_sided"]:
        why = "incomplete ladder (a leg missing)" if not complete else "one-sided ladder (a leg not 0 < bid <= ask < 1)"
        if comp in MODEL_LIVE:
            row["fee_clear"]["model"] = {"reason": why}
        row["fee_clear"]["book"] = {"reason": why}
        return row
    # model basis: the PICK leg (argmax of the model over the ladder's legs), live model sports only
    if comp in MODEL_LIVE:
        mp, why_m = _model_ref(preds, t)
        if mp is None or any(k not in mp for k in sels):
            row["fee_clear"]["model"] = {"reason": why_m or "prediction lacks a leg of the ladder",
                                         "rewritten": why_m == REWRITTEN}
        else:
            pick = max(sels, key=lambda k: mp[k])
            row["fee_clear"]["model"] = {
                "leg": pick, "p": mp[pick],
                **{b: (None if lg[pick][b] is None else {"edge_pp": (mp[pick] - lg[pick][b]) * 100,
                                                         "clears": _clears((mp[pick] - lg[pick][b]) * 100, clear)})
                   for b in ("taker", "maker")}}
    # book basis: the venue engine's reference, best leg per cost basis
    fair, why = _book_ref(book, t, sels)
    if fair is None or any(k not in fair for k in sels):
        row["fee_clear"]["book"] = {"reason": why or "book session lacks a leg"}
    else:
        bb = {}
        for b in ("taker", "maker"):
            cands = [(k, (fair[k] - lg[k][b]) * 100) for k in sels if lg[k][b] is not None]
            if not cands:
                bb[b] = None
                continue
            k, e = max(cands, key=lambda kv: kv[1])
            bb[b] = {"leg": k, "edge_pp": e, "clears": _clears(e, clear)}
        row["fee_clear"]["book"] = bb
    return row


def ladders(s, since: datetime = K_WINDOW_FROM, until: datetime = K_WINDOW_TO) -> list[dict]:
    """Every pre-kickoff Kalshi ladder captured in [since, until)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, OddsSnapshot, Prediction
    kal = list(s.execute(select(OddsSnapshot, Match, Competition)
                         .join(Match, Match.id == OddsSnapshot.match_id)
                         .join(Competition, Competition.id == Match.competition_id)
                         .where(OddsSnapshot.source == "kalshi", OddsSnapshot.market.in_(("1X2", "ML")),
                                OddsSnapshot.captured_at >= since, OddsSnapshot.captured_at < until))
               .all())
    by: dict = {}
    for x, m, c in kal:
        if m.utc_date is None or x.captured_at >= m.utc_date:      # pre-kickoff only (in-play never)
            continue
        by.setdefault((m.id, x.captured_at), {"comp": c.code, "legs": {}, "match": m})["legs"][x.selection] = x
    mids = sorted({k[0] for k in by})
    book_by: dict = {}
    pred_by: dict = {}
    if mids:
        for x in s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id.in_(mids),
                                                      OddsSnapshot.source != "kalshi",
                                                      OddsSnapshot.market == "1X2")).scalars():
            book_by.setdefault(x.match_id, []).append(x)
        for p in s.execute(select(Prediction).where(Prediction.match_id.in_(mids))).scalars():
            pred_by.setdefault(p.match_id, []).append(p)
    rows = []
    for (mid, t), g in sorted(by.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        r = ladder_row(g["comp"], t, g["legs"], book_by.get(mid, []), pred_by.get(mid, []))
        r["match_id"] = mid
        rows.append(r)
    return rows


def by_sport(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        a = out.setdefault(r["comp"], {"ladders": 0, "complete": 0, "two_sided": 0, "spreads": [],
                                       "fc": {(bs, b): [0, 0] for bs in ("model", "book")
                                              for b in ("taker", "maker")},
                                       "unevaluable": {"model": 0, "book": 0}, "rewritten": 0})
        a["ladders"] += 1
        a["complete"] += r["complete"]
        a["two_sided"] += r["two_sided"]
        # every two-sided LEG's spread, one-sided ladders included (Codex on #297: no liquidity bias)
        a["spreads"] += [v["spread_c"] for v in r["legs"].values() if v["spread_c"] is not None]
        for bs, blk in r["fee_clear"].items():
            if "reason" in blk:
                a["unevaluable"][bs] += 1
                a["rewritten"] += bool(blk.get("rewritten"))
                continue
            for b in ("taker", "maker"):
                v = blk.get(b)
                if v is None:
                    continue
                a["fc"][(bs, b)][1] += 1
                a["fc"][(bs, b)][0] += v["clears"]
    for a in out.values():
        sp = a.pop("spreads")
        a["spread_c"] = {"legs": len(sp), "median": median(sp) if sp else None, "p90": _pct(sp, 0.9),
                         "max": max(sp) if sp else None,
                         "one_cent_share": (sum(1 for x in sp if x <= 1.0 + 1e-9) / len(sp)) if sp else None}
    return out


def format_ladders(rows, since, until) -> list[str]:
    from src.walters.desk_policy import K2
    agg = by_sport(rows)
    out = [f"LADDERS · Kalshi captures {since:%Y-%m-%dT%H:%MZ} → {until:%Y-%m-%dT%H:%MZ} (pre-kickoff only) · "
           f"{len(rows)} ladders · fee-clear = (reference p − cost) ≥ {K2['feeClearsPP']}pp",
           "  two-sided = 0 < bid ≤ ask < 1 on every leg · taker = ask + fee(0.07·M) · maker = join (bid+1c) "
           "+ fee(0.0175·M), none on a 1c spread or unknown maker M"]

    def rate(v):
        c, n = v
        return f"{c}/{n} ({c / n:.0%})" if n else "—/0"
    for comp in sorted(agg):
        a = agg[comp]
        sp = a["spread_c"]
        out.append(f"- {comp}: ladders {a['ladders']} · complete {a['complete']} · two-sided {a['two_sided']}"
                   f" ({a['two_sided'] / a['ladders']:.0%}) · spread legs {sp['legs']} median {_f(sp['median'])}c"
                   f" p90 {_f(sp['p90'])}c max {_f(sp['max'])}c · 1c share {_p(sp['one_cent_share'])}")
        for bs in ("model", "book"):
            if bs == "model" and comp not in MODEL_LIVE:
                out.append("    fee-clear vs model: — (market-only sport, no live model)")
                continue
            out.append(f"    fee-clear vs {bs}: taker {rate(a['fc'][(bs, 'taker')])} · maker "
                       f"{rate(a['fc'][(bs, 'maker')])} · not evaluable {a['unevaluable'][bs]}"
                       + (f" (of which {a['rewritten']} captured before the current prediction was written: "
                          "no history kept)" if bs == "model" and a["rewritten"] else ""))
    return out


def _f(v):
    return "—" if v is None else f"{v:.1f}"


def _p(v):
    return "—" if v is None else f"{v:.0%}"


# ------------------------------------------------- fills + call-to-fill (#75) --

DISPOSITIONS = ("UNAVAILABLE", "UNATTEMPTED", "ATTEMPTED_UNFILLED", "MATCHED", "UNKNOWN")


def _call_day(c: dict) -> str:
    return (c.get("kickoff") or c.get("log_date") or "")[:10]


def _call_time(c: dict):
    """The call's kickoff as naive UTC (offset converted); a call with no kickoff falls back to its log
    date at 00:00. None when neither parses. Compared as a full timestamp (Codex on #297)."""
    from src.walters.unl_ladders import to_naive_utc
    v = c.get("kickoff")
    if v:
        try:
            return to_naive_utc(datetime.fromisoformat(v[:-1] + "+00:00" if v.endswith("Z") else v))
        except ValueError:
            pass
    try:
        return datetime.fromisoformat((c.get("log_date") or "")[:10])
    except ValueError:
        return None


def eligible_calls(L: dict, since: datetime = K_WINDOW_FROM, until: datetime = K_WINDOW_TO) -> list[dict]:
    """Eligible = a real system call: a straight or ladder, units > 0, not a shadow, not a
    parlay leg, its kickoff (else log date) inside the window."""
    from src.walters.ledger_fills import is_shadow
    out = []
    for c in L.get("calls") or []:
        if c.get("call_type") not in ("straight", "ladder") or not (c.get("units") or 0) > 0 or is_shadow(c):
            continue
        t = _call_time(c)
        if t is not None and since <= t < until:
            out.append(c)
    return out


def _recorded_quote(c: dict):
    """The executable cost the ledger recorded for the pick side, earliest first (claim, re-log, call)."""
    for k in ("claim_exec_cost_maker", "claim_exec_cost", "exec_cost_maker", "exec_cost",
              "kalshi_exec_cost_maker", "kalshi_exec_cost"):
        if isinstance(c.get(k), (int, float)) and not isinstance(c.get(k), bool):
            return k, c[k]
    return None, None


def reconcile(L: dict, since: datetime = K_WINDOW_FROM, until: datetime = K_WINDOW_TO) -> dict:
    """Exactly one disposition per eligible call (#75 criteria, ARCHITECT-adopted 2026-10-06).
    MATCHED      a system_matched fill names the call (ids, quantity, paid entry, opening fee kept)
    UNAVAILABLE  the ledger recorded no executable Kalshi cost for the pick side at claim or re-log
    UNKNOWN      a cost was recorded but no fill matched: the ledger holds no order records, so
                 UNATTEMPTED and ATTEMPTED_UNFILLED cannot be told apart and neither is inferred
    UNATTEMPTED / ATTEMPTED_UNFILLED need order provenance the ledger does not carry (count 0, stated)."""
    from src.walters.ledger_fills import classify_fills
    fills = classify_fills(L)
    by_call: dict = {}
    for f in fills:
        if f.get("book") == "system_matched" and f.get("call_id"):
            by_call.setdefault(f["call_id"], []).append(f)
    elig = eligible_calls(L, since, until)
    ids = {c.get("id") for c in elig}
    rows = []
    for c in elig:
        fs = by_call.get(c.get("id"), [])
        qk, qv = _recorded_quote(c)
        if fs:
            d = {"disposition": "MATCHED",
                 "fills": [{"fill_id": f.get("id"), "ticker": f.get("ticker"), "side": f.get("side"),
                            "qty": f.get("qty"), "entry": f.get("entry"), "open_fee": f.get("open_fee"),
                            "fee_class_open": f.get("fee_class_open"),
                            "ambiguous_calls": f.get("ambiguous_calls"),
                            "composite_no": f.get("composite_no")} for f in fs],
                 "why": "system_matched fill(s); no order id exists in the Kalshi CSV"}
        elif qk is None:
            d = {"disposition": "UNAVAILABLE",
                 "why": "no executable Kalshi cost recorded for the pick side (claim, re-log or call)"}
        else:
            d = {"disposition": "UNKNOWN",
                 "why": f"executable cost recorded ({qk} {qv:.3f}) but no matched fill; the ledger has no "
                        "order records, so attempted-unfilled vs unattempted is not knowable"
                        + (" (a manual fill_price is recorded on the call)" if c.get("fill_price") is not None
                           else "")}
        d["cost_recorded"] = qk is not None          # independent of the disposition (Codex on #297)
        rows.append({"call_id": c.get("id"), "sport": c.get("sport"), "game": c.get("game"),
                     "day": _call_day(c), "pick": c.get("pick"), "call_type": c.get("call_type"),
                     "engine": c.get("engine"), "units": c.get("units"), **d})
    matched_fills = [f for f in fills if f.get("book") == "system_matched"]
    outside = [f for f in matched_fills if f.get("call_id") not in ids]
    inside = [f for f in matched_fills if f.get("call_id") in ids]
    tally = {k: sum(1 for r in rows if r["disposition"] == k) for k in DISPOSITIONS}
    return {"since": since, "until": until, "rows": rows, "tally": tally,
            "funnel": {"eligible": len(rows),
                       "cost_recorded": sum(1 for r in rows if r["cost_recorded"]),
                       "matched": tally["MATCHED"]},
            "ledger": {"fills": len(fills), "system_matched": len(matched_fills),
                       "matched_in_window": len(inside), "matched_outside_window": len(outside),
                       "qty": sum(f.get("qty") or 0 for f in inside),
                       "open_fees": sum(f.get("open_fee") or 0 for f in inside
                                        if isinstance(f.get("open_fee"), (int, float))),
                       "fees": sum(f.get("fees") or 0 for f in inside),
                       "pnl_net": sum(f.get("pnl_net") or 0 for f in inside),
                       "pnl_pre": sum(f.get("pnl_pre") or 0 for f in inside),
                       "fee_classes": {k: sum(1 for f in inside if (f.get("fee_class_open") or "n/a") == k)
                                       for k in ("maker", "taker", "taker_live", "ambiguous", "unknown", "n/a")}},
            "ambiguous": [{"fill_id": f.get("id"), "ticker": f.get("ticker"), "attributed_to": f.get("call_id"),
                           "candidates": f["ambiguous_calls"]} for f in matched_fills if f.get("ambiguous_calls")],
            "composite_no": [{"fill_id": f.get("id"), "ticker": f.get("ticker"), "attributed_to": f.get("call_id")}
                             for f in matched_fills if f.get("composite_no")],
            "books": {b: sum(1 for f in fills if f.get("book") == b)
                      for b in ("system_matched", "system_pick_unlogged", "off_book_sports", "fun")}}


def format_fills(L: dict, since: datetime = K_WINDOW_FROM, until: datetime = K_WINDOW_TO) -> list[str]:
    from src.walters.ledger_fills import executed_positions
    rec = reconcile(L, since, until)
    ex = executed_positions(L)
    in_window = {r["call_id"] for r in rec["rows"]}          # the same cohort as the reconciliation (Codex on #297)
    outside = [p for p in ex["pos"] if p["c"].get("id") not in in_window]
    ex["pos"] = [p for p in ex["pos"] if p["c"].get("id") in in_window]
    lg = rec["ledger"]
    out = [f"FILLS · ledger export: {lg['fills']} fills · books " +
           " · ".join(f"{k} {v}" for k, v in rec["books"].items()),
           f"  system_matched in window: {lg['matched_in_window']} (outside window {lg['matched_outside_window']})"
           f" · qty {lg['qty']} · opening fees ${lg['open_fees']:.2f} · fees ${lg['fees']:.2f}"
           f" · realised P&L pre-fee ${lg['pnl_pre']:+.2f} net ${lg['pnl_net']:+.2f}",
           "  opening-fee class: " + " · ".join(f"{k} {v}" for k, v in lg["fee_classes"].items() if v),
           *[f"  ! AMBIGUOUS fill [{a['fill_id']}] {a['ticker']}: {len(a['candidates'])} calls fit "
             f"({', '.join(map(str, a['candidates']))}); attributed to {a['attributed_to']} as the Cockpit does — "
             "check by hand (e.g. a doubleheader)" for a in rec["ambiguous"]],
           *[f"  ! COMPOSITE NO fill [{a['fill_id']}] {a['ticker']}: NO on a three-way leg is two outcomes; "
             f"attributed to {a['attributed_to']} as the Cockpit does — not a straight on one side, check by hand"
             for a in rec["composite_no"]],
           "EXECUTED-POSITION CLV (the Cockpit's executedPositions: held contract's closing fair − fill entry)"]
    pos = sorted(ex["pos"], key=lambda p: (p["day"] or "", str(p["c"].get("id"))))
    for p in pos:
        c = p["c"]
        out.append(f"- {c.get('sport')} {c.get('game')} · {p['day']} · pick {c.get('pick')} · qty {p['qty']} · "
                   f"entry CLV {p['clv'] * 100:+.2f}pp · fee-adj "
                   + ("—" if p["fee_adj"] is None else f"{p['fee_adj'] * 100:+.2f}pp") + f" ({p['fee_status']})")
    if pos:
        cl = [p["clv"] for p in pos]
        fa = [p["fee_adj"] for p in pos if p["fee_adj"] is not None]
        out.append(f"  mean entry CLV {sum(cl) / len(cl) * 100:+.2f}pp (n {len(cl)}) · mean fee-adj "
                   + (f"{sum(fa) / len(fa) * 100:+.2f}pp (n {len(fa)})" if fa else "— (n 0)")
                   + " · execution evidence, not evidence of edge (#75)")
    else:
        out.append("  no executed positions (no graded system_matched fill with a close)")
    if outside:
        out.append(f"  {len(outside)} executed position(s) outside the window, excluded from the CLV above")
    if ex["unpriced"]:
        out.append(f"  {ex['unpriced']} matched call(s) whose held contract is not priceable at the close")
    t = rec["tally"]
    out.append(f"CALL-TO-FILL RECONCILIATION (#75, adopted) · eligible calls {since:%Y-%m-%d} → "
               f"{until:%Y-%m-%d} (exclusive): {rec['funnel']['eligible']} · cost recorded "
               f"{rec['funnel']['cost_recorded']} · matched {rec['funnel']['matched']}")
    out.append("  " + " · ".join(f"{k} {t[k]}" for k in DISPOSITIONS)
               + " (UNATTEMPTED / ATTEMPTED_UNFILLED need order records the ledger does not carry)")
    for r in rec["rows"]:
        line = (f"- {r['disposition']:<11} {r['sport']} {r['game']} · {r['day']} · {r['call_type']} "
                f"{r['pick']} · {r['units']}u · {r['why']}")
        out.append(line)
        for f in r.get("fills") or []:
            out.append(f"      fill [{f['fill_id']}] {f['ticker']} {f['side']} qty {f['qty']} @ {f['entry']} · open fee "
                       f"{f['open_fee']} ({f['fee_class_open'] or 'n/a'})"
                       + (" · AMBIGUOUS attribution" if f.get("ambiguous_calls") else "")
                       + (" · COMPOSITE NO (two outcomes)" if f.get("composite_no") else ""))
    return out
