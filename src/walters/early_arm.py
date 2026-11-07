"""THE EARLY-ENTRY ARM, ATTRIBUTED (#862; ARCHITECT 2026-11-07 08:55 ET, addendum 283 item 4) — READ-ONLY.

Addendum 283 item 4, verbatim in part: "the import's attribution gains the early fill — a fill on a match BEFORE that
match's closing run, on the side the closing page PLAYs → attributed to the closing call with early = true, early_price
and early_clv_cents; a fill before the closing run on a match the closing page PASSes or whose side it changed → "arm
flip", paired with its pre-kickoff exit fill and its flip_cost_cents; a fill AFTER kickoff on an arm position → "arm
breach", listed; the #446-class receipt script gains the arm's table (count, mean early CLV, flip count and cost,
breaches) in cents and units only — never a dollar figure, never a contract count on a public surface (238, 250); the
bulletins carry nothing of the arm beyond the word "early" on a call line."

Item 3, verbatim in part: "per early fill the ledger records early_price (the fill), closing_cost (the closing page's
all-in cost on the same side; null if the close PASSed), early_clv_cents = (closing_cost − early_price) × 100 (positive
= early was cheaper than the close would have been), flip_exit_price and flip_cost_cents where (c)(iii) applied."
Item 2(f), verbatim in part: "the venue's interest on open positions is a LEDGER LINE of its own (the CSV import's
interest rows, if the export carries them, under their own kind; never attributed to a call or to the arm) [...] The
rate is never written into the repo."

A LAYER, NOT A CHANGE TO THE MATCHER: ledger_fills.classify_fills (the Cockpit's classifyFills, line for line, its
parity checked by scripts/ledger_fills_parity_verify.py) is called unchanged; attribute() reads its output beside the
closing pages and adds the arm's fields. It never writes the ledger (the ledger is the Cockpit's browser storage; the
Cockpit's view gains the arm's line at its next republish, on the operator's word, item 4) and writes nothing at all.

THE JOIN (the closing pages, redated.closing_rows, the one reader, on <exports> and each dated folder <YYYY-MM-DD>/):
a fill is a closing row's game when its EVENT ticker (the market ticker less its last "-" part) is one the row names
(its desk.order ticker or a kalshi_legs ticker): match ids are machine-local, an event ticker is the venue's own. The
match's CLOSING RUN is the latest page that holds the event (addendum 41: the later page is the close), ordered by
the file's exported_at, naive UTC: the time the run's page went out. NEVER the closing block's start (nor the file
name's stamp): deploy/hosting/closing.closing_doc writes closing.start = the COVERED start, a kickoff, and the run goes
at that start less RUN_LEAD_MIN (35 minutes), so "before the start" would take every ordinary closing-call fill
placed after the page went out for an early one (review of 7ddac1a8). A page with no exported_at has no run time
(RUN_UNKNOWN, law 4); one that disagrees with the latest timed page, or two pages of that latest export time that
disagree on the call, side, contract or cost, are refused (never picked). The covered start is kept as the closing
call's `start`. Kickoff is the closing row's utc_date. latest/ is refused, given directly or behind a dated-named
folder (LatestRefused, the 232 item 2(c) rule of pl_injury_classification_receipt.population): its files are copies.

THE KINDS, per fill (the field `arm`; `arm_note` says why a fill is none of them, never a guess, law 4):
- THE ONE GATE (early and flip alike): the matcher booked the fill system_matched, to a logged PLAY call on the fill's
  own side (a page said PLAY on it and the Cockpit logged it). A pre-closing fill with no such booking (no logged
  call, an off-book bet, a value shadow on its side: 2(e)) keeps its booking, arm None, arm_note PRE_CLOSE_OFF_ARM,
  counted neither early nor flip, so the read's sample holds only fills the ledger ties to a PLAY call.
  One exception is listed, never counted: a fill the matcher booked "logged call exists but the side disagrees" on a
  close that PLAYs the other side, a logged call of that game on the close's side (the Cockpit's callKey has no pick,
  so a same-ET-day side change re-logs the prematch call in place and the old side's call is gone): arm None,
  arm_note SIDE_RELOGGED, the table's UNESTABLISHED line. It may be a (c)(iii) flip or an off-book bet; the ledger
  cannot tell (an open question on #862).
- ARM_EARLY ("early"): opened BEFORE the closing run (the page's exported_at) on a match whose closing page's desk.call
  is PLAY, on the page's side, booked system_matched (the gate): the fill's market ticker and side are the page's
  desk.order ticker and side, else (no order contract on the page, or another contract) its resolved role is
  desk.pick. early = True, early_price = the fill's entry,
  closing_cost = desk.exec.cost (the page's all-in cost) when the fill holds the page's own order contract, else null
  (the page printed no cost for that contract), early_clv_cents = (closing_cost − early_price) × 100, null when either
  is. The fill keeps the book and call the matcher gave it (the closing call's position, 2(c)(i)), and
  closing_call names the page: its match id, run (the page's export time), start (the covered start), pick and units.
- ARM_FLIP ("arm flip"): opened BEFORE the closing run on a match whose closing page PASSes, or PLAYs another side,
  booked system_matched (the gate). closing_cost null. Its book becomes ARM_BOOK ("booked to the arm, never hidden",
  2(c)(iii)), its call_id None (never attributed to a call; the matcher's call is kept as ledger_call_id for the record), so
  ledger_fills.executed_positions over attribute()'s output never counts a flip. Paired with its pre-kickoff exit: the
  CSV row is a position lot, entry and exit on one row. A SALE is close_fee > 0 (the fee-class rule); NO SALE is
  close_fee 0 on an exit of 0 or 1 (a settlement) or a lot with no exit and no close yet (open); anything else
  (close_fee unread, None, or 0 on an exit strictly between 0 and 1) is a sale NOT READ (law 4), never "no sale". A
  sale closed before kickoff gives flip_exit_price = its exit and flip_cost_cents = (early_price − flip_exit_price) ×
  100 (positive = the flip cost the arm; fees excluded, as early_clv_cents excludes the fill's fee: the basis is an
  open question on #862); otherwise null, with flip_exit saying why (FLIP_HELD, FLIP_LATE, FLIP_SALE_UNREAD,
  FLIP_TIME_UNREAD), and the table counts each on its own ARM FLIP NOT EXITED line (their cost is not in the flip cost).
- A closing page whose call is neither PLAY nor PASS (LADDER, VENUE) is not ruled for the arm: arm None, arm_note
  NOT_RULED_CALL, listed.
- ARM BREACH ("arm breach", the flag arm_breach and breach_why): any fill on an ARM POSITION's event (one with an early
  or flip fill) opened at or after kickoff, or sold (a SALE, above) at or after kickoff (2(d): "from kickoff a position
  is held to settlement"). A settlement is no breach. A lot closed at or after kickoff whose sale is NOT READ is
  breach_unread (its own count), never "no breach". A breach flags the fill whatever its kind.
- INTEREST_KIND ("interest", 2(f)): a fill entry whose stored `type` holds the word interest. kind and book become
  "interest", call_id None, arm None: a ledger line of its own, never attributed to a call or to the arm, its amount
  never read here. The Cockpit's importKalshiCSV does not store the CSV's `type` today, so no entry of today's export
  can be one (an open question on #862, never guessed from the account-id-bearing id).

Never read or printed: id (it carries the account id), qty, staked, fees, pnl_*, desk.exec.contracts, order.contracts.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ARM_EARLY = "early"
ARM_FLIP = "arm flip"                      # addendum 283 item 4, the label verbatim
ARM_BREACH = "arm breach"                  # addendum 283 item 4, the label verbatim
ARM_BOOK = "arm"                           # 2(c)(iii): "booked to the arm, never hidden"
INTEREST_KIND = "interest"                 # 2(f): a ledger line of its own kind
EARLY_WORD = "early"                       # item 4: "nothing of the arm beyond the word "early" on a call line"
PRE_CLOSE_OFF_ARM = ("opened before the closing run, but no logged PLAY call on its side (not system_matched): "
                     "not the arm's")
NOT_RULED_CALL = "the closing page's call is neither PLAY nor PASS: not ruled for the arm"
NO_PAGE = "no closing page names its event"
DISAGREE = "the latest closing run's pages disagree on the game (refused, none picked)"
RUN_UNKNOWN = "closing run time unknown (the page's file has no exported_at)"
TIME_UNREAD = "fill open time not read"
SIDE_UNREAD = "side not comparable to the page's"
AFTER_RUN = "opened at or after the closing page went out (its exported_at): an ordinary fill"
SIDE_RELOGGED = ("opened before the closing run on the side a logged call of this game no longer holds (the close "
                 "PLAYs the other side; a same-day re-log keeps one pick): a flip or an off-book bet, not established "
                 "— listed, never counted")
MATCHER_SIDE_DISAGREES = "logged call exists but the side disagrees"     # ledger_fills.match_fill's own category
FLIP_EXITED = "exited before kickoff"
FLIP_HELD = "no sale (held to settlement or still open): not exited before kickoff"
FLIP_LATE = "exited at or after kickoff"
FLIP_SALE_UNREAD = ("sale not read (close_fee unread, or no fee on an exit between 0 and 1): exit before kickoff not "
                    "established")
FLIP_TIME_UNREAD = "kickoff or exit time not read"
NOT_EXITED_KEYS = {FLIP_HELD: "held to settlement or open", FLIP_LATE: "exited at or after kickoff",
                   FLIP_SALE_UNREAD: "sale not read", FLIP_TIME_UNREAD: "time not read"}
DATED = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class LatestRefused(ValueError):
    """--exports is, or a dated-named folder of it resolves to, a latest/ folder: never read (232 item 2(c))."""
READ_AT = 30                               # item 3: "THE READ at n = 30 early fills (flips counted in the 30)"


def event_of(ticker) -> str | None:
    t = str(ticker or "").strip().upper()
    return t.rsplit("-", 1)[0] if "-" in t else None


def _row_events(row: dict) -> set:
    desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
    order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
    legs = row.get("kalshi_legs") if isinstance(row.get("kalshi_legs"), dict) else {}
    out = set()
    for t in [order.get("ticker")] + [(v or {}).get("ticker") for v in legs.values() if isinstance(v, dict)]:
        e = event_of(t)
        if e:
            out.add(e)
    return out


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _page(run, start, row: dict) -> dict:
    desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
    order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
    ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else {}
    from src.walters.redated import as_utc
    return {"run": run, "start": start, "match_id": row.get("match_id"), "home": row.get("home_team"),
            "away": row.get("away_team"),
            "kickoff": as_utc(row.get("utc_date")), "call": desk.get("call"), "pick": desk.get("pick"),
            "units": _num(desk.get("units")),
            "order_ticker": str(order.get("ticker")).upper() if order.get("ticker") else None,
            "order_side": str(order.get("side")).lower() if order.get("side") else None,
            "cost": _num(ex.get("cost"))}


def closing_pages(exports_dir) -> dict:
    """The closing page of each event: {"by_event": {event: page or {"refused": DISAGREE}}, "files": n,
    "unreadable": [names], "dated": n dated folders}. Read with redated.closing_rows on <exports_dir> and each dated
    folder <exports_dir>/<YYYY-MM-DD>/; latest/ is refused (LatestRefused), given directly or behind a dated-named
    folder. A page's run is its file's exported_at (redated.closing_rows' "exports"), never the closing block's
    start (the covered start, kept as the page's `start`). An event's page is its LATEST export's; a page with no
    exported_at has run None and is refused with the rest when it disagrees with that page; an event whose every page
    has none keeps its page with run None (RUN_UNKNOWN downstream) when they agree."""
    from src.walters.redated import as_utc, closing_rows
    d = Path(exports_dir)
    if "latest" in (d.name, d.resolve().name):
        raise LatestRefused(f"--exports {d}: a latest/ folder (resolves to {d.resolve()}); latest/ is never read (its "
                            "files are copies of a dated folder's newest); pass its parent; nothing read")
    subs = sorted(p for p in d.iterdir() if p.is_dir() and DATED.fullmatch(p.name)) if d.is_dir() else []
    for sub in subs:
        if sub.resolve().name == "latest":
            raise LatestRefused(f"--exports {d}: the dated folder {sub.name}/ resolves to {sub.resolve()}, a latest/ "
                                "folder; latest/ is never read; nothing read")
    by: dict = {}
    files, bad = 0, []
    for sub in [d] + subs:
        cr = closing_rows(sub)
        files += cr["files"]
        bad += [("" if sub == d else f"{sub.name}/") + n for n in cr["unreadable"]]
        for mid, entries in cr["rows"].items():
            for (start, _fam, row), src in zip(entries, cr["exports"][mid]):
                run = as_utc(src.get("exported_at"))
                for ev in _row_events(row):
                    by.setdefault(ev, []).append(_page(run, start, row))
    out = {}
    for ev, pages in by.items():
        known = [p for p in pages if p["run"] is not None]
        if known:
            last = max(p["run"] for p in known)
            top = [p for p in known if p["run"] == last] + [p for p in pages if p["run"] is None]
        else:
            top = pages
        # The page's own fields, its units among them (they feed closing_call and early_by_units); never match_id,
        # which is machine-local (the join is the event ticker): the page kept is the latest timed one, top[0].
        sig = {tuple(p[k] for k in ("call", "pick", "units", "order_ticker", "order_side", "cost", "kickoff"))
               for p in top}
        out[ev] = top[0] if len(sig) == 1 else {"refused": DISAGREE}
    return {"by_event": out, "files": files, "unreadable": bad, "dated": len(subs)}


def is_interest(f: dict) -> bool:
    """2(f): the stored entry's `type` holds the word interest (the CSV's own column; read only when stored)."""
    t = f.get("type")
    return isinstance(t, str) and re.search(r"\binterest\b", t, flags=re.I) is not None


def _side(f: dict, page: dict) -> tuple[str | None, bool]:
    """("same" / "other" / None not comparable, whether the fill holds the page's own order contract)."""
    tk, sd = str(f.get("ticker") or "").strip().upper(), str(f.get("side") or "").strip().lower()
    own = bool(page["order_ticker"]) and tk == page["order_ticker"] and sd == page["order_side"]
    if own:
        return "same", True
    role = f.get("backed_role")
    if f.get("composite") or role not in ("HOME", "AWAY", "DRAW") or page["pick"] not in ("HOME", "AWAY", "DRAW"):
        return None, False
    return ("same" if role == page["pick"] else "other"), False


def _sale(fx: dict) -> bool | None:
    """A SALE (True: close_fee > 0), NO SALE (False: close_fee 0 on an exit of 0 or 1, a settlement; or no exit and no
    close yet, open), else None: NOT READ (close_fee missing, or 0 on an exit strictly between 0 and 1), law 4."""
    cf, ex = _num(fx.get("close_fee")), _num(fx.get("exit"))
    if cf is not None and cf > 0:
        return True
    if ex is None and not fx.get("closed"):
        return False
    if cf is not None and cf == 0 and ex in (0.0, 1.0):
        return False
    return None


def _cents(a, b) -> float | None:
    return None if a is None or b is None else round((a - b) * 100, 4)


def attribute(L: dict, exports_dir=None, pages: dict | None = None) -> list[dict]:
    """ledger_fills.classify_fills(L), each fill with the arm's fields (the module docstring): arm, arm_note, early,
    early_price, closing_cost, early_clv_cents, closing_call, flip_exit_price, flip_cost_cents, flip_exit,
    ledger_call_id, arm_breach, breach_why; interest rows relabelled. `pages` is closing_pages(exports_dir)."""
    from src.walters import ledger_fills as lf
    from src.walters.redated import as_utc
    if pages is None:
        pages = closing_pages(exports_dir)
    by_event = pages["by_event"]
    out = []
    for fx in lf.classify_fills(L):
        a = {**fx, "arm": None, "arm_note": None, "early": False, "early_price": None, "closing_cost": None,
             "early_clv_cents": None, "closing_call": None, "flip_exit_price": None, "flip_cost_cents": None,
             "flip_exit": None, "ledger_call_id": None, "arm_breach": False, "breach_why": None,
             "breach_unread": False}
        out.append(a)
        if is_interest(fx):
            a.update(kind=INTEREST_KIND, book=INTEREST_KIND, category="interest (a ledger line of its own, 2(f))",
                     call_id=None, engine=None, tier=None)
            a.pop("ambiguous_calls", None)
            continue
        if fx.get("kind") != "sport":
            continue
        page = by_event.get(event_of(fx.get("ticker")))
        if page is None:
            a["arm_note"] = NO_PAGE
            continue
        if "refused" in page:
            a["arm_note"] = page["refused"]
            continue
        opened = as_utc(fx.get("opened"))
        if page["run"] is None:
            a["arm_note"] = RUN_UNKNOWN
            continue
        if opened is None:
            a["arm_note"] = TIME_UNREAD
            continue
        if opened >= page["run"]:
            a["arm_note"] = AFTER_RUN
            continue
        side, own = _side(fx, page)
        if page["call"] not in ("PLAY", "PASS"):
            a["arm_note"] = NOT_RULED_CALL
            continue
        if page["call"] == "PLAY" and side is None:
            a["arm_note"] = SIDE_UNREAD
            continue
        if fx.get("book") != "system_matched":
            relogged = (page["call"] == "PLAY" and side == "other" and fx.get("category") == MATCHER_SIDE_DISAGREES
                        and any(c.get("pick") == page["pick"] and c.get("id") is not None
                                for c in (L.get("calls") or []) if isinstance(c, dict)
                                and c.get("sport") in (fx.get("sports") or ()) and c.get("call_type") != "parlay_leg"
                                and lf.game_fits(fx, c)))
            a["arm_note"] = SIDE_RELOGGED if relogged else PRE_CLOSE_OFF_ARM
            continue
        if page["call"] == "PLAY" and side == "same":
            price = _num(fx.get("entry"))
            cost = page["cost"] if own else None
            a.update(arm=ARM_EARLY, early=True, early_price=price, closing_cost=cost,
                     early_clv_cents=_cents(cost, price),
                     closing_call={"match_id": page["match_id"], "run": page["run"], "start": page["start"],
                                   "pick": page["pick"], "units": page["units"]})
            continue
        a.update(arm=ARM_FLIP, ledger_call_id=fx.get("call_id"), book=ARM_BOOK, call_id=None,
                 category="arm flip (booked to the arm, 2(c)(iii))", early_price=_num(fx.get("entry")),
                 closing_call={"match_id": page["match_id"], "run": page["run"], "start": page["start"],
                               "pick": page["pick"], "units": page["units"], "call": page["call"]})
        a.pop("ambiguous_calls", None)
        closed, ko = as_utc(fx.get("closed")), page["kickoff"]
        sale = _sale(fx)
        if sale is False:
            a["flip_exit"] = FLIP_HELD
        elif ko is None or closed is None:
            a["flip_exit"] = FLIP_TIME_UNREAD
        elif sale is None:
            a["flip_exit"] = FLIP_SALE_UNREAD
        elif closed < ko:
            a["flip_exit"] = FLIP_EXITED
            a["flip_exit_price"] = _num(fx.get("exit"))
            a["flip_cost_cents"] = _cents(a["early_price"], a["flip_exit_price"])
        else:
            a["flip_exit"] = FLIP_LATE
    arm_events = {event_of(a.get("ticker")) for a in out if a["arm"] in (ARM_EARLY, ARM_FLIP)}
    for a in out:
        if a.get("kind") != "sport" or event_of(a.get("ticker")) not in arm_events:
            continue
        page = by_event.get(event_of(a.get("ticker")))
        ko = page.get("kickoff") if isinstance(page, dict) else None
        if ko is None:
            continue
        opened, closed = as_utc(a.get("opened")), as_utc(a.get("closed"))
        why = []
        if opened is not None and opened >= ko:
            why.append("opened at or after kickoff")
        sale = _sale(a)
        if sale and closed is not None and closed >= ko:
            why.append("sold at or after kickoff")
        if why:
            a["arm_breach"], a["breach_why"] = True, " and ".join(why)
        elif sale is None and closed is not None and closed >= ko:
            a["breach_unread"] = True                 # closed after kickoff, its sale not read: never "no breach"
    return out


def _mean(xs: list) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def arm_table(rows: list[dict]) -> dict:
    """The arm's table (item 4: "count, mean early CLV, flip count and cost, breaches"), in cents and units only:
    counts of fills, means and totals of cents per contract, unweighted over the export's entries (each CSV lot one;
    no quantity is read), the early fills by the closing page's units. Never a dollar figure, never a contract
    count. toward_thirty is early + flips (item 3: "flips counted in the 30"), counted in the export's rows (lots);
    arm_games, the distinct games those rows are on, is printed beside it (the unit of the 30 is open on #862); no
    read is computed here. A flip not exited before kickoff is counted by why (flips_not_exited_before_kickoff); its
    cost is not in the flip cost (open on #862)."""
    early = [r for r in rows if r.get("arm") == ARM_EARLY]
    flips = [r for r in rows if r.get("arm") == ARM_FLIP]
    clv = [r["early_clv_cents"] for r in early if r.get("early_clv_cents") is not None]
    fc = [r["flip_cost_cents"] for r in flips if r.get("flip_cost_cents") is not None]
    units: dict = {}
    for r in early:
        u = (r.get("closing_call") or {}).get("units")
        k = f"{u:g}u" if isinstance(u, (int, float)) else "units not printed"
        units[k] = units.get(k, 0) + 1
    not_exited = {v: sum(1 for r in flips if r.get("flip_exit") == k) for k, v in NOT_EXITED_KEYS.items()}
    return {"early": len(early), "early_priced": len(clv), "mean_early_clv_cents": _mean(clv),
            "early_by_units": dict(sorted(units.items())),
            "flips": len(flips),
            "flips_exited_before_kickoff": sum(1 for r in flips if r.get("flip_exit") == FLIP_EXITED),
            "flips_exited_priced": len(fc),
            "flips_not_exited_before_kickoff": not_exited,
            "mean_flip_cost_cents": _mean(fc), "total_flip_cost_cents": round(sum(fc), 4) if fc else None,
            "breaches": sum(1 for r in rows if r.get("arm_breach")),
            "breaches_not_read": sum(1 for r in rows if r.get("breach_unread")),
            "interest_rows": sum(1 for r in rows if r.get("kind") == INTEREST_KIND),
            "not_the_arms": sum(1 for r in rows if r.get("arm_note") == PRE_CLOSE_OFF_ARM),
            "unestablished": sum(1 for r in rows if r.get("arm_note") == SIDE_RELOGGED),
            "not_ruled": sum(1 for r in rows if r.get("arm_note") in (NOT_RULED_CALL, SIDE_UNREAD, DISAGREE)),
            "toward_thirty": len(early) + len(flips),
            "arm_games": len({event_of(r.get("ticker")) for r in early + flips}), "read_at": READ_AT}


def _c(x) -> str:
    return "—" if x is None else f"{x:+.2f}¢"


def table_lines(t: dict) -> list[str]:
    """The table as printed: counts of fills, cents per contract and the page's units; nothing else."""
    by_u = " · ".join(f"{k} {v}" for k, v in t["early_by_units"].items()) or "none"
    ne = " · ".join(f"{k} {v}" for k, v in t["flips_not_exited_before_kickoff"].items())
    return [
        f"EARLY (item 4: before the closing run, on the side the closing page PLAYs, booked to its logged call): "
        f"{t['early']} fills · priced {t['early_priced']} · mean early CLV {_c(t['mean_early_clv_cents'])} per "
        f"contract (closing_cost − early_price, × 100; positive = early was cheaper) · by the closing page's units: "
        f"{by_u}",
        f"ARM FLIP (the close PASSed or changed side; booked to the arm): {t['flips']} fills · exited before kickoff "
        f"{t['flips_exited_before_kickoff']} (priced {t['flips_exited_priced']}) · flip cost mean "
        f"{_c(t['mean_flip_cost_cents'])} per contract, total "
        f"{_c(t['total_flip_cost_cents'])} (early_price − flip_exit_price, × 100; positive = a cost)",
        f"ARM FLIP NOT EXITED before kickoff (2(c)(iii)): {ne} — their cost is not in the flip cost (open on #862)",
        f"ARM BREACH (a fill opened or sold at or after kickoff on an arm position, 2(d)): {t['breaches']} · not read "
        f"(closed at or after kickoff, its sale not read): {t['breaches_not_read']}",
        f"INTEREST (its own kind, never attributed to a call or to the arm, 2(f)): {t['interest_rows']} rows",
        f"NOT THE ARM'S (pre-closing, no logged PLAY on its side): {t['not_the_arms']} · UNESTABLISHED (pre-closing, "
        f"on the side a same-day re-log may have replaced; never counted): {t['unestablished']} · NOT RULED (a LADDER "
        f"or VENUE close, a side not comparable, pages that disagree): {t['not_ruled']}",
        f"COUNT toward thirty (early + flips, item 3): {t['toward_thirty']} of {t['read_at']} (export rows; distinct "
        f"games {t['arm_games']}) — no read before thirty; the read is the architect's, on the laptop's ledger, by a "
        "block (no verdict is computed here)",
    ]


def early_calls(rows: list[dict]) -> set:
    """The closing calls (match id, run: the page's export time) holding at least one early fill: the calls a
    bulletin marks."""
    return {(r["closing_call"]["match_id"], r["closing_call"]["run"]) for r in rows
            if r.get("arm") == ARM_EARLY and r.get("closing_call")}


def arm_call_line(call_line: str, early: bool) -> str:
    """A bulletin's call line (closing.call_text, verbatim) with the arm's one word: item 4, "the bulletins carry
    nothing of the arm beyond the word "early" on a call line". No flip, breach, price or figure ever."""
    return f"{call_line} {EARLY_WORD}" if early else call_line


def _iso(d: datetime | None) -> str | None:
    return f"{d:%Y-%m-%dT%H:%M:%S}Z" if d is not None else None
