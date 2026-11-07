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
match's CLOSING RUN is the latest run whose page holds the event (addendum 41: the later page is the close); its start
is the closing block's start (else the file name's stamp), naive UTC. Two pages of that latest run that disagree on
the call, side, contract or cost are refused (never picked). Kickoff is the closing row's utc_date.

THE KINDS, per fill (the field `arm`; `arm_note` says why a fill is none of them, never a guess, law 4):
- ARM_EARLY ("early"): opened BEFORE the closing run's start on a match whose closing page's desk.call is PLAY, on the
  page's side: the fill's market ticker and side are the page's desk.order ticker and side, else (no order contract
  on the page, or another contract) its resolved role is desk.pick. early = True, early_price = the fill's entry,
  closing_cost = desk.exec.cost (the page's all-in cost) when the fill holds the page's own order contract, else null
  (the page printed no cost for that contract), early_clv_cents = (closing_cost − early_price) × 100, null when either
  is. The fill keeps the book and call the matcher gave it (the closing call's position, 2(c)(i)), and
  closing_call names the page: its match id, run start, pick and units.
- ARM_FLIP ("arm flip"): opened BEFORE the closing run's start on a match whose closing page PASSes, or PLAYs another
  side, AND which the matcher booked system_matched (a logged PLAY call on the fill's own side: a page said PLAY on it
  before the close). closing_cost null. Its book becomes ARM_BOOK ("booked to the arm, never hidden", 2(c)(iii)), its
  call_id None (never attributed to a call; the matcher's call is kept as ledger_call_id for the record), so
  ledger_fills.executed_positions over attribute()'s output never counts a flip. Paired with its pre-kickoff exit: the
  CSV row is a position lot, entry and exit on one row, and a sale is close_fee > 0 (the fee-class rule): a sale
  closed before kickoff gives flip_exit_price = its exit and flip_cost_cents = (early_price − flip_exit_price) × 100
  (positive = the flip cost the arm; fees excluded, as early_clv_cents excludes the fill's fee); no such sale, null
  with flip_exit saying why. A pre-closing fill on such a match with no system_matched booking is NOT the arm's: it
  keeps its booking, arm None, arm_note PRE_CLOSE_OFF_ARM.
- A closing page whose call is neither PLAY nor PASS (LADDER, VENUE) is not ruled for the arm: arm None, arm_note
  NOT_RULED_CALL, listed.
- ARM BREACH ("arm breach", the flag arm_breach and breach_why): any fill on an ARM POSITION's event (one with an early
  or flip fill) opened at or after kickoff, or sold (close_fee > 0) at or after kickoff (2(d): "from kickoff a position
  is held to settlement"). A settlement (close_fee 0) is no breach. A breach flags the fill whatever its kind.
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
RUN_UNKNOWN = "closing run start unknown"
TIME_UNREAD = "fill open time not read"
SIDE_UNREAD = "side not comparable to the page's"
AFTER_RUN = "opened at or after the closing run's start (an ordinary fill)"
DATED = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
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


def _page(run, row: dict) -> dict:
    desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
    order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
    ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else {}
    from src.walters.redated import as_utc
    return {"run": run, "match_id": row.get("match_id"), "home": row.get("home_team"), "away": row.get("away_team"),
            "kickoff": as_utc(row.get("utc_date")), "call": desk.get("call"), "pick": desk.get("pick"),
            "units": _num(desk.get("units")),
            "order_ticker": str(order.get("ticker")).upper() if order.get("ticker") else None,
            "order_side": str(order.get("side")).lower() if order.get("side") else None,
            "cost": _num(ex.get("cost"))}


def closing_pages(exports_dir) -> dict:
    """The closing page of each event: {"by_event": {event: page or {"refused": DISAGREE}}, "files": n,
    "unreadable": [names], "dated": n dated folders}. Read with redated.closing_rows on <exports_dir> and each dated
    folder <exports_dir>/<YYYY-MM-DD>/ (never latest/). An event's page is its LATEST run's; a row with no run start
    sorts oldest, and an event whose every row has none keeps the page with run None."""
    from src.walters.redated import closing_rows
    d = Path(exports_dir)
    dirs = [d] + (sorted(p for p in d.iterdir() if p.is_dir() and DATED.fullmatch(p.name)) if d.is_dir() else [])
    by: dict = {}
    files, bad = 0, []
    for sub in dirs:
        cr = closing_rows(sub)
        files += cr["files"]
        bad += [("" if sub == d else f"{sub.name}/") + n for n in cr["unreadable"]]
        for entries in cr["rows"].values():
            for run, _fam, row in entries:
                for ev in _row_events(row):
                    by.setdefault(ev, []).append(_page(run, row))
    out = {}
    for ev, pages in by.items():
        known = [p for p in pages if p["run"] is not None]
        if known:
            last = max(p["run"] for p in known)
            top = [p for p in known if p["run"] == last]
        else:
            top = pages
        sig = {tuple(p[k] for k in ("match_id", "call", "pick", "order_ticker", "order_side", "cost", "kickoff"))
               for p in top}
        out[ev] = top[0] if len(sig) == 1 else {"refused": DISAGREE}
    return {"by_event": out, "files": files, "unreadable": bad, "dated": len(dirs) - 1}


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
             "flip_exit": None, "ledger_call_id": None, "arm_breach": False, "breach_why": None}
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
        if page["call"] == "PLAY" and side == "same":
            price = _num(fx.get("entry"))
            cost = page["cost"] if own else None
            a.update(arm=ARM_EARLY, early=True, early_price=price, closing_cost=cost,
                     early_clv_cents=_cents(cost, price),
                     closing_call={"match_id": page["match_id"], "run": page["run"], "pick": page["pick"],
                                   "units": page["units"]})
            continue
        if page["call"] not in ("PLAY", "PASS"):
            a["arm_note"] = NOT_RULED_CALL
            continue
        if page["call"] == "PLAY" and side is None:
            a["arm_note"] = SIDE_UNREAD
            continue
        if fx.get("book") != "system_matched":
            a["arm_note"] = PRE_CLOSE_OFF_ARM
            continue
        a.update(arm=ARM_FLIP, ledger_call_id=fx.get("call_id"), book=ARM_BOOK, call_id=None,
                 category="arm flip (booked to the arm, 2(c)(iii))", early_price=_num(fx.get("entry")),
                 closing_call={"match_id": page["match_id"], "run": page["run"], "pick": page["pick"],
                               "units": page["units"], "call": page["call"]})
        a.pop("ambiguous_calls", None)
        closed, ko = as_utc(fx.get("closed")), page["kickoff"]
        sale = (_num(fx.get("close_fee")) or 0) > 0
        if not sale:
            a["flip_exit"] = "no sale (held to settlement or still open): not exited before kickoff"
        elif ko is None or closed is None:
            a["flip_exit"] = "kickoff or exit time not read"
        elif closed < ko:
            a["flip_exit"] = "exited before kickoff"
            a["flip_exit_price"] = _num(fx.get("exit"))
            a["flip_cost_cents"] = _cents(a["early_price"], a["flip_exit_price"])
        else:
            a["flip_exit"] = "exited at or after kickoff"
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
        if (_num(a.get("close_fee")) or 0) > 0 and closed is not None and closed >= ko:
            why.append("sold at or after kickoff")
        if why:
            a["arm_breach"], a["breach_why"] = True, " and ".join(why)
    return out


def _mean(xs: list) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def arm_table(rows: list[dict]) -> dict:
    """The arm's table (item 4: "count, mean early CLV, flip count and cost, breaches"), in cents and units only:
    counts of fills, means and totals of cents per contract, unweighted over the export's entries (each CSV lot one;
    no quantity is read), the early fills by the closing page's units. Never a dollar figure, never a contract
    count. toward_thirty is early + flips (item 3: "flips counted in the 30"); no read is computed here."""
    early = [r for r in rows if r.get("arm") == ARM_EARLY]
    flips = [r for r in rows if r.get("arm") == ARM_FLIP]
    clv = [r["early_clv_cents"] for r in early if r.get("early_clv_cents") is not None]
    fc = [r["flip_cost_cents"] for r in flips if r.get("flip_cost_cents") is not None]
    units: dict = {}
    for r in early:
        u = (r.get("closing_call") or {}).get("units")
        k = f"{u:g}u" if isinstance(u, (int, float)) else "units not printed"
        units[k] = units.get(k, 0) + 1
    return {"early": len(early), "early_priced": len(clv), "mean_early_clv_cents": _mean(clv),
            "early_by_units": dict(sorted(units.items())),
            "flips": len(flips), "flips_exited_before_kickoff": len(fc),
            "mean_flip_cost_cents": _mean(fc), "total_flip_cost_cents": round(sum(fc), 4) if fc else None,
            "breaches": sum(1 for r in rows if r.get("arm_breach")),
            "interest_rows": sum(1 for r in rows if r.get("kind") == INTEREST_KIND),
            "not_the_arms": sum(1 for r in rows if r.get("arm_note") == PRE_CLOSE_OFF_ARM),
            "not_ruled": sum(1 for r in rows if r.get("arm_note") in (NOT_RULED_CALL, SIDE_UNREAD, DISAGREE)),
            "toward_thirty": len(early) + len(flips), "read_at": READ_AT}


def _c(x) -> str:
    return "—" if x is None else f"{x:+.2f}¢"


def table_lines(t: dict) -> list[str]:
    """The table as printed: counts of fills, cents per contract and the page's units; nothing else."""
    by_u = " · ".join(f"{k} {v}" for k, v in t["early_by_units"].items()) or "none"
    return [
        f"EARLY (item 4: before the closing run, on the side the closing page PLAYs): {t['early']} fills · priced "
        f"{t['early_priced']} · mean early CLV {_c(t['mean_early_clv_cents'])} per contract (closing_cost − "
        f"early_price, × 100; positive = early was cheaper) · by the closing page's units: {by_u}",
        f"ARM FLIP (the close PASSed or changed side; booked to the arm): {t['flips']} fills · exited before kickoff "
        f"{t['flips_exited_before_kickoff']} · flip cost mean {_c(t['mean_flip_cost_cents'])} per contract, total "
        f"{_c(t['total_flip_cost_cents'])} (early_price − flip_exit_price, × 100; positive = a cost)",
        f"ARM BREACH (a fill opened or sold at or after kickoff on an arm position, 2(d)): {t['breaches']}",
        f"INTEREST (its own kind, never attributed to a call or to the arm, 2(f)): {t['interest_rows']} rows",
        f"NOT THE ARM'S (pre-closing, no logged PLAY on its side): {t['not_the_arms']} · NOT RULED (a LADDER or "
        f"VENUE close, a side not comparable, pages that disagree): {t['not_ruled']}",
        f"COUNT toward thirty (early + flips, item 3): {t['toward_thirty']} of {t['read_at']} — no read before "
        "thirty; the read is the architect's, on the laptop's ledger, by a block (no verdict is computed here)",
    ]


def early_calls(rows: list[dict]) -> set:
    """The closing calls (match id, run start) holding at least one early fill: the calls a bulletin marks."""
    return {(r["closing_call"]["match_id"], r["closing_call"]["run"]) for r in rows
            if r.get("arm") == ARM_EARLY and r.get("closing_call")}


def arm_call_line(call_line: str, early: bool) -> str:
    """A bulletin's call line (closing.call_text, verbatim) with the arm's one word: item 4, "the bulletins carry
    nothing of the arm beyond the word "early" on a call line". No flip, breach, price or figure ever."""
    return f"{call_line} {EARLY_WORD}" if early else call_line


def _iso(d: datetime | None) -> str | None:
    return f"{d:%Y-%m-%dT%H:%M:%S}Z" if d is not None else None
