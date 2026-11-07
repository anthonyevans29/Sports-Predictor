"""THE EARLY-ENTRY ARM, ATTRIBUTED (#862; ARCHITECT 2026-11-07 08:55 ET, addendum 283 item 4; ruled further 12:00 ET,
addendum 285) — READ-ONLY.

Addendum 283 item 4, verbatim in part: "the import's attribution gains the early fill — a fill on a match BEFORE that
match's closing run, on the side the closing page PLAYs → attributed to the closing call with early = true, early_price
and early_clv_cents; a fill before the closing run on a match the closing page PASSes or whose side it changed → "arm
flip", paired with its pre-kickoff exit fill and its flip_cost_cents; a fill AFTER kickoff on an arm position → "arm
breach", listed; the #446-class receipt script gains the arm's table (count, mean early CLV, flip count and cost,
breaches) in cents and units only — never a dollar figure, never a contract count on a public surface (238, 250); the
bulletins carry nothing of the arm beyond the word "early" on a call line."
Item 2(f), verbatim in part: "the venue's interest on open positions is a LEDGER LINE of its own (the CSV import's
interest rows, if the export carries them, under their own kind; never attributed to a call or to the arm) [...] The
rate is never written into the repo."

Addendum 285 (ARCHITECT 2026-11-07 12:00 ET) rules the round-2 P2s and the seven open readings; each is built below
and named where it is: 1(a) the straight-PLAY gate, 1(b) NOT CLASSIFIED, 1(c) the boundary (no change), 2(1) the fee
basis, 2(2) games, 2(3) a flip held to settlement, 2(4) the prematch page as the side's source, 2(5) the breach list
(console only: scripts/early_arm_receipt.py), 2(6) both gates, 2(7) the interest wording.

A LAYER, NOT A CHANGE TO THE MATCHER: ledger_fills.classify_fills (the Cockpit's classifyFills, line for line, its
parity checked by scripts/ledger_fills_parity_verify.py) is called unchanged; attribute() reads its output beside the
closing and prematch pages and adds the arm's fields. It never writes the ledger (the ledger is the Cockpit's browser
storage; the Cockpit's view gains the arm's line at its next republish, on the operator's word, item 4) and writes
nothing at all.

THE JOIN (by EVENT ticker: the market ticker less its last "-" part, against a row's desk.order ticker and its
kalshi_legs tickers; match ids are machine-local, an event ticker is the venue's own). Both page kinds are read on
<exports> and each dated folder <YYYY-MM-DD>/; latest/ is refused, given directly or behind a dated-named folder
(LatestRefused, the 232 item 2(c) rule of pl_injury_classification_receipt.population): its files are copies.
- THE CLOSING PAGE (redated.closing_rows, the one reader of closing_*.json): the match's CLOSING RUN is the latest page
  that holds the event (addendum 41: the later page is the close), ordered by the file's exported_at, naive UTC: the
  time the run's page went out. NEVER the closing block's start (nor the file name's stamp): closing_doc writes
  closing.start = the COVERED start, a kickoff, and the run goes at that start less RUN_LEAD_MIN (35 minutes).
  THE BOUNDARY (addendum 285 item 1(c), closed by ruling, no change): early is before the closing page's exported_at,
  because the closing numbers exist at the export; a fill after the export is a fill at the closing call's own
  numbers (the ordinary call, not an early one), whatever the page's send-and-retry time. A page with no exported_at
  has no run time (RUN_UNKNOWN, law 4); one that disagrees with the latest timed page, or two pages of that latest
  export time that disagree on the call, side, contract, units, cost, quotes or kickoff, are refused (never picked).
  Kickoff is the closing row's utc_date.
- THE PREMATCH PAGE (addendum 285 items 2(4) and 2(6)): the family's slate export, PREMATCH_GLOBS (closing.FAMILIES'
  export_glob: soccer_PL_*.json, nfl_predictions_*.json, mlb_MLB_*.json; a closing run writes its own slate under
  logs/, never into exports/, addendum 40 item 2), a Desk page (a dict with a predictions list and a desk_meta block,
  no closing block; any other file of the glob is counted, never read as a page); a row is a page of its events when
  it carries a desk block. A page's time is its file's exported_at. For a fill, THE prematch page is the latest page
  of its event whose exported_at is strictly BEFORE the fill's opened time; pages of that time that disagree on the
  call, pick, units or order contract are refused; untimed pages are never placed before a fill (a reading: a timed
  page before the fill is used even when an untimed page also names the event; every export writes exported_at).
  ITS ASK (2(4): "the source of the arm's side and ask"; 283 2(b): "at or below THAT PAGE's own ask [...] never above
  it"): prematch_ask is that page's ask on the fill's own contract (page_ask, the closing ask's derivation). A lot
  whose entry is ABOVE it is counted on its own line, above_prematch_ask True: never excluded and never a breach (not
  ruled, a reading); None when the ask or the entry is not read.
  WHAT THE FOLDERS HOLD (a reading): a slate file is replaced whole under one window name at every slate stage
  (closing.slate_file / link_slate_file; the replaced copy is kept only under logs/). A page replaced since the fill is
  therefore seen only in the mirror's dated folders, one copy per file name per UTC mtime day, so a same-day
  re-export overwrites the earlier page there too. Read on exports/ alone, such a fill has no page before it and is
  UNESTABLISHED (NO_PREMATCH), never a guess; the logs/ copies are not read.

THE GATE (addendum 285 items 1(a) and 2(6): "both, not either"). An arm fill (early or flip) is a fill that
  (i) the matcher booked system_matched to a STRAIGHT PLAY call on the fill's side: its call_id resolved against
      L["calls"], call_type "straight" (the Cockpit's vocabulary: straight, ladder, quarantine_shadow, value_shadow,
      parlay_leg), not a shadow, units > 0, its pick the fill's backed_role. A LADDER call, a composite NO, a value
      shadow or any other kind is never an arm fill, on a PLAY page or a PASS page (NOT_STRAIGHT_PLAY); a fill the
      matcher booked to no call is PRE_CLOSE_OFF_ARM; and
  (ii) THE prematch page before it shows desk.call PLAY on the fill's side (its own order contract, else desk.pick ==
      the fill's backed_role). That page is the source of the arm's SIDE (2(4): "never the Cockpit's re-logged call").
      No prematch page before the fill: NO_PREMATCH, UNESTABLISHED (listed, never counted); a PASS or another side:
      PREMATCH_NOT_PLAY (not the arm's).
  THE SAME-DAY SIDE CHANGE (2(4)): gate (i) stays strict, the re-log never meets it (a reading; the re-log case
  waits for #865, the Cockpit's callKey gaining the pick). The Cockpit's callKey has no pick, so a closing page that
  changes side the same ET day re-logs the prematch call in place on the new side, and the matcher books the old
  side's fill "logged call exists but the side disagrees" (MATCHER_SIDE_DISAGREES), to no call. Take a fill booked
  that way on a timed close that PLAYs the other side, where a straight PLAY call of that game holds the closing side
  (the call's kickoff is the closing page's, within desk_policy.DESK_CLOCK_DRIFT: the same game, never a neighbouring
  day's). Such a fill is SIDE_RELOGGED, UNESTABLISHED (listed, never counted), whether or not a prematch page before
  it PLAYs its side. It is never an arm fill.
AN AMBIGUOUS BOOKING (addendum 286 item 3(1)): a fill carrying ambiguous_calls (ledger_fills.match_fill's field: more
  than one call fits, e.g. a doubleheader with no start time, and the matcher booked the first) is AMBIGUOUS_CALLS,
  UNESTABLISHED on its own line: never an arm fill, never in the thirty. It is checked before any other test, and the
  row keeps its ambiguous_calls (the flip path no longer pops it).
ORDER (a reading, not a ruling): interest; an ambiguous booking (286 item 3(1)); a fill opened at or after a timed closing run is ordinary (AFTER_RUN); the
  gate's (i); the fill's time; the gate's (ii); then the closing page's unknowns (NO_PAGE, DISAGREE, RUN_UNKNOWN). A
  row a gate rejects is classified by that gate whatever its closing page; only a row both gates admit can be NOT
  CLASSIFIED for want of a closing page or a fill time (a fill that cannot be the arm's never holds the read).
AN ENTRY PRICE is read only inside (0, 1): the Cockpit stores a blank entry cell as 0 (importKalshiCSV's
  `num(...)||0`). Outside that range the lot's early_price is None and its arm_note is ENTRY_UNREAD; its CLV, flip cost
  and settlement result are unread, so its game is unpriced (law 4), never a figure.

THE KINDS, per fill (the field `arm`; `arm_note` says why a fill is none of them, never a guess, law 4):
- ARM_EARLY ("early"): through the gate, before the closing run, on a match whose closing page PLAYs the prematch
  page's pick. early = True, early_price = the fill's entry (read inside (0, 1)), closing_ask = THE CLOSING PAGE'S
  ASK on the fill's contract (2(1): "price against price, fees out of both"): its kalshi_legs quote for that ticker,
  YES the leg's ask, NO 1 − the leg's bid (desk_policy.order_line / side_quotes: the number exec_block's cost = ask + kalshi_fee(ask, M,
  n) was priced from; the fee cancels, paid on either path); null when the page carries no quote for the fill's
  contract. early_clv_cents (the lot's) = (closing_ask − early_price) × 100. The fill keeps the book and call the
  matcher gave it (the closing call's position, 2(c)(i)); closing_call names the closing page; prematch_page the
  prematch page that admitted it.
- ARM_FLIP ("arm flip"): through the gate, before the closing run, on a match whose closing page PASSes or PLAYs
  another side than the prematch page's. Its book becomes ARM_BOOK ("booked to the arm, never hidden", 2(c)(iii)), its
  call_id None (the matcher's kept as ledger_call_id), so ledger_fills.executed_positions over attribute()'s output
  never counts a flip. Paired with its pre-kickoff exit: the CSV row is a position lot, entry and exit on one row. A
  SALE is close_fee > 0 (the fee-class rule); NO SALE is close_fee 0 on an exit of 0 or 1 (a settlement) or a lot
  with no exit and no close yet (open); anything else is a sale NOT READ (law 4), never "no sale". A sale closed
  before kickoff: flip_exit_price = its exit and flip_cost_cents (the lot's, 2(1)) = (early_price − flip_exit_price)
  × 100 + (open_fee + close_fee) / qty × 100: both legs' taker fees in cents per contract, "a cost the closing-call
  path never pays" (qty read to divide, never printed); null when a figure is unread. Otherwise flip_exit says why:
  FLIP_SETTLED (held to settlement: a BREACH of 2(c)(iii), 2(3)), FLIP_OPEN, FLIP_LATE (a breach: sold after kickoff),
  FLIP_SALE_UNREAD, FLIP_TIME_UNREAD.
- NOT_RULED_CALL: a closing page whose call is neither PLAY nor PASS (LADDER, VENUE), on a fill both gates admit:
  listed on the NOT RULED line, and it holds the read (1(b): refused while any row is unclassified).
- ARM BREACH ("arm breach", the flag arm_breach and breach_why): any fill on an ARM POSITION's event opened at or after
  kickoff, or sold at or after kickoff (2(d)), and a flip held to settlement (2(3)). A settlement of an early lot is
  no breach. A lot closed at or after kickoff whose sale is NOT READ is breach_unread, never "no breach"; so is a lot
  whose sale is not ruled out (a sale, or a sale not read) with its closing time unread, and every lot of an arm event
  whose closing page carries no kickoff (286 item 3(2)), a breach already or not (a cause not read is not a count).
- INTEREST_KIND ("interest", 2(f)): a fill entry whose stored `type` holds the word interest: kind and book
  "interest", call_id None, arm None, never attributed to a call or to the arm, its amount never read. 2(7): when no
  fill of the export carries a `type` key the export does not carry interest rows: the table says so, never zero.

THE TABLE (arm_table, 2(2): "THE UNIT OF THE THIRTY: GAMES"): a game is an event with an early or flip lot. Per game:
  early CLV = the contract-weighted (qty) mean of its early lots' early_clv_cents (= the closing ask less the
  contract-weighted early price, one contract), flip cost = the contract-weighted mean of its exited flip lots'
  flip_cost_cents, the settlement result of a flip held to settlement = units × Σ qty·(settle − entry) / Σ qty·entry
  (= units × (settle − ē)/ē, ē the contract-weighted entry; the units of the prematch page that admitted the game's
  first arm lot; price only, fees out: a reading), in units, outside the CLV mean. A figure is null when any lot of it
  is unread (never a partial mean). toward_thirty = the arm's games; lots are a count beside them. THE READ AT THIRTY
  (283 item 3, 285 items 1(b) and 2(3)), on the first READ_AT games by their first arm fill's time. It is refused
  while any row is NOT CLASSIFIED, or is NOT RULED: a fill both gates admit on a LADDER or VENUE close is classified
  neither early, flip nor ordinary, so it holds the read and stays on its NOT RULED line too. The count is printed,
  never the mean. A breach in those games (any cause) gives no verdict: the continuation is the architect's ruling on
  the record. The net over the thirty is reported WITH that read when every game of the thirty is priced (2(3)); a
  held flip or a late exit adds no cents to it (its result is in units, outside the mean). A breach not read, or a
  game whose figure is unread, gives no verdict either (law 4, readings). 286 item 3: the read is HELD (its count
  printed, no mean, no verdict) while any game of the thirty has a breach not read, then while any game of the thirty
  is unpriced (a held flip whose settlement result is unread is unpriced: "the denominator holds only numbers"),
  both ahead of the breach read, so a breach's net is always over priced games. Else CONTINUE only if (Σ per-game early CLV
  − Σ per-game flip cost) / games > 0 (a tie rejects, law 3), else STOP. Below thirty: "n of 30", no verdict.

Never read or printed: id (it carries the account id), staked, fees, pnl_*, desk.exec.contracts, order.contracts. qty
is read to weight and to divide the fees, never printed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ARM_EARLY = "early"
ARM_FLIP = "arm flip"                      # addendum 283 item 4, the label verbatim
ARM_BREACH = "arm breach"                  # addendum 283 item 4, the label verbatim
ARM_BOOK = "arm"                           # 2(c)(iii): "booked to the arm, never hidden"
INTEREST_KIND = "interest"                 # 2(f): a ledger line of its own kind
EARLY_WORD = "early"                       # item 4: "nothing of the arm beyond the word "early" on a call line"
STRAIGHT = "straight"                      # the Cockpit's call_type of a straight call (ledger call vocabulary)
ROLES = ("HOME", "AWAY", "DRAW")
# The families' prematch (slate) exports: deploy/hosting/closing.FAMILIES[fam]["export_glob"] (a test pins the two).
PREMATCH_GLOBS = ("mlb_MLB_*.json", "nfl_predictions_*.json", "soccer_PL_*.json")

PRE_CLOSE_OFF_ARM = "no straight PLAY call on its side (the matcher booked it to no call): not the arm's"
NOT_STRAIGHT_PLAY = ("booked to a call that is not a straight PLAY on its side (a LADDER, a composite NO, a shadow, "
                     "another kind): never an arm fill")
PREMATCH_NOT_PLAY = "the prematch page before the fill does not PLAY its side (a PASS or another side): not the arm's"
NO_PREMATCH = "UNESTABLISHED: no prematch page before the fill"
SIDE_RELOGGED = ("UNESTABLISHED: on the side a same-day re-log replaced (the close PLAYs the other side): never an "
                 "arm fill, whether or not a prematch page before the fill PLAYs its side (gate (i) strict; waits "
                 "for #865)")
AMBIGUOUS_CALLS = ("UNESTABLISHED: the matcher could not tell its calls apart (ambiguous_calls: booked to the first "
                   "of several that fit, e.g. a doubleheader with no start time): never an arm fill, never in the "
                   "thirty (addendum 286 item 3(1))")
PREMATCH_DISAGREE = "the latest prematch pages before the fill disagree on the game (refused, none picked)"
PREMATCH_UNTIMED = "only untimed prematch pages (no exported_at) name its event: before the fill not established"
NOT_RULED_CALL = "the closing page's call is neither PLAY nor PASS: not ruled for the arm"
NO_PAGE = "no closing page names its event"
DISAGREE = "the latest closing run's pages disagree on the game (refused, none picked)"
RUN_UNKNOWN = "closing run time unknown (the page's file has no exported_at)"
TIME_UNREAD = "fill open time not read"
SIDE_UNREAD = "side not comparable to the page's"
AFTER_RUN = "opened at or after the closing page went out (its exported_at): an ordinary fill"
MATCHER_SIDE_DISAGREES = "logged call exists but the side disagrees"     # ledger_fills.match_fill's own category
ASK_UNREAD = "the closing page carries no quote for the fill's contract"
ENTRY_UNREAD = "entry price not read (outside 0 to 1: the Cockpit stores a blank entry as 0)"
FLIP_EXITED = "exited before kickoff"
FLIP_SETTLED = "held to settlement (a breach of 2(c)(iii))"
FLIP_OPEN = "open at the export (not exited, not settled)"
FLIP_LATE = "exited at or after kickoff"
FLIP_SALE_UNREAD = ("sale not read (close_fee unread, or no fee on an exit between 0 and 1): exit before kickoff not "
                    "established")
FLIP_TIME_UNREAD = "kickoff or exit time not read"
BREACH_OPENED = "opened at or after kickoff"
BREACH_SOLD = "sold at or after kickoff"
BREACH_HELD = "flip held to settlement"     # 285 item 2(3): its own line and its own cause
BREACH_CAUSES = (BREACH_OPENED, BREACH_SOLD, BREACH_HELD)
NOT_EXITED_KEYS = {FLIP_OPEN: "open at the export", FLIP_LATE: "exited at or after kickoff (a breach)",
                   FLIP_SALE_UNREAD: "sale not read", FLIP_TIME_UNREAD: "time not read"}
# Every arm_note, by the table line that counts it (1(b): none is dropped; arm_table counts an unknown one NOT
# CLASSIFIED "other", never nowhere).
NOT_THE_ARMS_KEYS = {PRE_CLOSE_OFF_ARM: "no straight PLAY call", NOT_STRAIGHT_PLAY: "not a straight PLAY call",
                     PREMATCH_NOT_PLAY: "prematch page not PLAY on its side"}
UNESTABLISHED_KEYS = {NO_PREMATCH: "no prematch page before the fill", SIDE_RELOGGED: "same-day re-log",
                      AMBIGUOUS_CALLS: "ambiguous attribution"}
NOT_CLASSIFIED_KEYS = {NO_PAGE: "no closing page", RUN_UNKNOWN: "closing run time unknown",
                       TIME_UNREAD: "fill open time not read", DISAGREE: "closing pages disagree",
                       SIDE_UNREAD: "side not comparable", PREMATCH_DISAGREE: "prematch pages disagree",
                       PREMATCH_UNTIMED: "prematch page time unknown"}
OTHER_NOTE = "other"
DATED = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
READ_AT = 30                               # item 3: "THE READ at n = 30"; 285 item 2(2): thirty GAMES
READ_BELOW = "below thirty"
READ_REFUSED = "refused: rows not classified"
READ_BREACH = "breach in the thirty"
READ_BREACH_UNREAD = "breach not read in the thirty"
READ_UNPRICED = "unpriced in the thirty"
READ_CONTINUE, READ_STOP = "CONTINUE", "STOP"


class LatestRefused(ValueError):
    """--exports is, or a dated-named folder of it resolves to, a latest/ folder: never read (232 item 2(c))."""


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


def _legs(row: dict) -> dict:
    """{TICKER: (yes bid, yes ask)}: the row's kalshi_legs quotes (venue.kalshi_legs: ticker, bid, ask per leg)."""
    legs = row.get("kalshi_legs") if isinstance(row.get("kalshi_legs"), dict) else {}
    out = {}
    for v in legs.values():
        if isinstance(v, dict) and v.get("ticker"):
            out[str(v["ticker"]).strip().upper()] = (_num(v.get("bid")), _num(v.get("ask")))
    return out


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
            "cost": _num(ex.get("cost")), "legs": _legs(row)}


def _dirs(exports_dir) -> list[Path]:
    """<exports_dir> and its dated folders; latest/ refused, given directly or behind a dated-named folder."""
    d = Path(exports_dir)
    if "latest" in (d.name, d.resolve().name):
        raise LatestRefused(f"--exports {d}: a latest/ folder (resolves to {d.resolve()}); latest/ is never read (its "
                            "files are copies of a dated folder's newest); pass its parent; nothing read")
    subs = sorted(p for p in d.iterdir() if p.is_dir() and DATED.fullmatch(p.name)) if d.is_dir() else []
    for sub in subs:
        if sub.resolve().name == "latest":
            raise LatestRefused(f"--exports {d}: the dated folder {sub.name}/ resolves to {sub.resolve()}, a latest/ "
                                "folder; latest/ is never read; nothing read")
    return [d] + subs


_CLOSE_SIG = ("call", "pick", "units", "order_ticker", "order_side", "cost", "kickoff")
_PRE_SIG = ("call", "pick", "units", "order_ticker", "order_side")


def _sig(p: dict, keys) -> tuple:
    return tuple(p[k] for k in keys) + (tuple(sorted(p["legs"].items())),)


def closing_pages(exports_dir) -> dict:
    """The closing page of each event: {"by_event": {event: page or {"refused": DISAGREE}}, "files": n,
    "unreadable": [names], "dated": n dated folders}. Read with redated.closing_rows on <exports_dir> and each dated
    folder <exports_dir>/<YYYY-MM-DD>/; latest/ is refused (LatestRefused). A page's run is its file's exported_at
    (redated.closing_rows' "exports"), never the closing block's start (the covered start, kept as the page's
    `start`). An event's page is its LATEST export's; a page with no exported_at has run None and is refused with the
    rest when it disagrees with that page; an event whose every page has none keeps its page with run None
    (RUN_UNKNOWN downstream) when they agree."""
    from src.walters.redated import as_utc, closing_rows
    dirs = _dirs(exports_dir)
    d = dirs[0]
    by: dict = {}
    files, bad = 0, []
    for sub in dirs:
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
        # The page's own fields (units and quotes among them: they feed closing_call, the units line and the ask);
        # never match_id, which is machine-local (the join is the event ticker): the page kept is top[0].
        sig = {_sig(p, _CLOSE_SIG) for p in top}
        out[ev] = top[0] if len(sig) == 1 else {"refused": DISAGREE}
    return {"by_event": out, "files": files, "unreadable": bad, "dated": len(dirs) - 1}


def prematch_pages(exports_dir) -> dict:
    """The prematch (slate) Desk pages of each event (285 items 2(4), 2(6)): {"by_event": {event: [page, ...]} (timed
    pages, page["run"] = the file's exported_at), "untimed": {events named only by a page with no exported_at},
    "files": n Desk pages read, "not_desk": n files of the globs that are no Desk page, "unreadable": [names],
    "dated": n}. PREMATCH_GLOBS on <exports_dir> and its dated folders; latest/ refused (the same _dirs)."""
    from src.walters.redated import CLOSING_GLOB, as_utc
    dirs = _dirs(exports_dir)
    d = dirs[0]
    by: dict = {}
    untimed: set = set()
    files, not_desk, bad = 0, 0, []
    for sub in dirs:
        names = sorted({p for g in PREMATCH_GLOBS for p in sub.glob(g)}) if sub.is_dir() else []
        for p in names:
            if p.match(CLOSING_GLOB):
                continue
            label = ("" if sub == d else f"{sub.name}/") + p.name
            try:
                doc = json.loads(p.read_text())
            except (OSError, ValueError):
                bad.append(label)
                continue
            if not (isinstance(doc, dict) and isinstance(doc.get("predictions"), list)
                    and isinstance(doc.get("desk_meta"), dict) and "closing" not in doc):
                not_desk += 1
                continue
            files += 1
            at = as_utc(doc.get("exported_at"))
            for r in doc["predictions"]:
                if not (isinstance(r, dict) and isinstance(r.get("desk"), dict)):
                    continue
                for ev in _row_events(r):
                    if at is None:
                        untimed.add(ev)
                    else:
                        by.setdefault(ev, []).append(_page(at, None, r))
    return {"by_event": by, "untimed": untimed, "files": files, "not_desk": not_desk, "unreadable": bad,
            "dated": len(dirs) - 1}


def prematch_before(pre: dict, event, t: datetime):
    """THE prematch page of a fill opened at `t`: the latest timed page of `event` strictly before t; {"refused":
    PREMATCH_DISAGREE} when the pages of that time disagree; PREMATCH_UNTIMED when none is timed before t and an
    untimed page names the event; None when no page is before t."""
    pages = [p for p in (pre.get("by_event") or {}).get(event, []) if p["run"] < t]
    if not pages:
        return PREMATCH_UNTIMED if event in (pre.get("untimed") or set()) else None
    last = max(p["run"] for p in pages)
    top = [p for p in pages if p["run"] == last]
    return top[0] if len({_sig(p, _PRE_SIG) for p in top}) == 1 else {"refused": PREMATCH_DISAGREE}


def is_interest(f: dict) -> bool:
    """2(f): the stored entry's `type` holds the word interest (the CSV's own column; read only when stored)."""
    t = f.get("type")
    return isinstance(t, str) and re.search(r"\binterest\b", t, flags=re.I) is not None


def _on_side(f: dict, page: dict) -> bool | None:
    """Whether the fill is on the page's side: its own order contract, else the fill's resolved role == desk.pick;
    None when not comparable (a composite contract, a role or pick not HOME / AWAY / DRAW)."""
    tk, sd = str(f.get("ticker") or "").strip().upper(), str(f.get("side") or "").strip().lower()
    if page["order_ticker"] and tk == page["order_ticker"] and sd == page["order_side"]:
        return True
    role = f.get("backed_role")
    if f.get("composite") or role not in ROLES or page["pick"] not in ROLES:
        return None
    return role == page["pick"]


def page_ask(page: dict, ticker, side) -> float | None:
    """The page's ask on a contract (285 item 2(1)): its kalshi_legs quote for the ticker, YES the leg's ask, NO
    1 − the leg's bid (desk_policy.order_line / side_quotes); None when the page carries none."""
    q = page["legs"].get(str(ticker or "").strip().upper())
    if q is None:
        return None
    bid, ask = q
    if str(side or "").strip().lower().startswith("n"):
        return None if bid is None else round(1 - bid, 4)
    return ask


def _straight_play(c: dict | None, role) -> bool:
    from src.walters import ledger_fills as lf
    return (isinstance(c, dict) and c.get("call_type") == STRAIGHT and not lf.is_shadow(c)
            and (_num(c.get("units")) or 0) > 0 and role in ROLES and c.get("pick") == role)


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


def _price(x) -> float | None:
    """A fill price, read only inside (0, 1): the Cockpit stores a blank entry cell as 0 (law 4: unread, never 0)."""
    v = _num(x)
    return v if v is not None and 0 < v < 1 else None


def _cents(a, b) -> float | None:
    return None if a is None or b is None else round((a - b) * 100, 4)


def _flip_cost(fx: dict) -> float | None:
    """285 item 2(1): (entry − exit) × 100 + (open_fee + close_fee) / qty × 100, cents per contract; None if unread."""
    e, x, q = _price(fx.get("entry")), _num(fx.get("exit")), _num(fx.get("qty"))
    of, cf = _num(fx.get("open_fee")), _num(fx.get("close_fee"))
    if None in (e, x, q, of, cf) or q <= 0:
        return None
    return round(((e - x) + (of + cf) / q) * 100, 4)


def _brief(p: dict) -> dict:
    return {"run": p["run"], "call": p["call"], "pick": p["pick"], "units": p["units"]}


def _relog(fx: dict, page: dict, calls: list) -> bool:
    """THE SAME-DAY RE-LOG (2(4), the module docstring): a fill the matcher left to no call on the side a re-log
    replaced. The close PLAYs the other side, and a straight PLAY call of THIS game (its kickoff the closing page's,
    within desk_policy.DESK_CLOCK_DRIFT) holds the closing side. A label only (SIDE_RELOGGED, UNESTABLISHED), never an
    arm fill: gate (i) stays strict."""
    from src.walters import ledger_fills as lf
    from src.walters.desk_policy import DESK_CLOCK_DRIFT
    from src.walters.redated import as_utc
    role, ko = fx.get("backed_role"), page.get("kickoff")
    if not (page.get("call") == "PLAY" and page.get("pick") in ROLES and role in ROLES and role != page["pick"]
            and fx.get("category") == MATCHER_SIDE_DISAGREES and not fx.get("composite") and ko is not None):
        return False

    def same_game(c) -> bool:
        k = as_utc(c.get("kickoff"))
        return k is not None and abs(k - ko) < DESK_CLOCK_DRIFT
    return any(c.get("id") is not None and _straight_play(c, page["pick"])
               and c.get("sport") in (fx.get("sports") or ()) and lf.game_fits(fx, c) and same_game(c) for c in calls)


def attribute(L: dict, exports_dir=None, pages: dict | None = None, prematch: dict | None = None) -> list[dict]:
    """ledger_fills.classify_fills(L), each fill with the arm's fields (the module docstring): arm, arm_note, early,
    early_price, closing_ask, early_clv_cents, closing_call, prematch_page, prematch_ask, above_prematch_ask,
    flip_exit_price, flip_cost_cents, flip_exit, ledger_call_id, arm_breach, breach_why, breach_unread; interest rows
    relabelled.
    `pages` is closing_pages(exports_dir), `prematch` prematch_pages(exports_dir)."""
    from src.walters import ledger_fills as lf
    from src.walters.redated import as_utc
    if pages is None:
        pages = closing_pages(exports_dir)
    if prematch is None:
        prematch = prematch_pages(exports_dir) if exports_dir is not None else {"by_event": {}, "untimed": set()}
    by_event = pages["by_event"]
    calls = [c for c in (L.get("calls") or []) if isinstance(c, dict)]
    by_id = {}
    for c in calls:
        if c.get("id") is not None:
            by_id.setdefault(c["id"], c)
    out = []
    for fx in lf.classify_fills(L):
        a = {**fx, "arm": None, "arm_note": None, "early": False, "early_price": None, "closing_ask": None,
             "early_clv_cents": None, "closing_call": None, "prematch_page": None, "prematch_ask": None,
             "above_prematch_ask": None, "flip_exit_price": None, "flip_cost_cents": None, "flip_exit": None, "ledger_call_id": None,
             "arm_breach": False, "breach_why": None, "breach_unread": False}
        out.append(a)
        if is_interest(fx):
            a.update(kind=INTEREST_KIND, book=INTEREST_KIND, category="interest (a ledger line of its own, 2(f))",
                     call_id=None, engine=None, tier=None)
            a.pop("ambiguous_calls", None)
            continue
        if fx.get("kind") != "sport":
            continue
        # 286 item 3(1): a fill the matcher could not resolve to one call is UNESTABLISHED, whatever else holds: its
        # own line, never an arm fill, never in the thirty. Checked first; its ambiguous_calls stays on the row.
        if fx.get("ambiguous_calls"):
            a["arm_note"] = AMBIGUOUS_CALLS
            continue
        ev = event_of(fx.get("ticker"))
        page = by_event.get(ev)
        timed = page is not None and "refused" not in page and page["run"] is not None
        role = fx.get("backed_role")
        opened = as_utc(fx.get("opened"))
        if timed and opened is not None and opened >= page["run"]:
            a["arm_note"] = AFTER_RUN                     # 1(c): at the closing call's own numbers, the ordinary call
            continue
        # THE GATE (i), 285 item 1(a): the matcher's booking, to a straight PLAY call on the fill's side.
        # Strict (2(6) "both, not either"; 2(4) "never [...] the Cockpit's re-logged call"): a same-day re-log is a
        # label, SIDE_RELOGGED, never an arm fill (the module docstring).
        booked = fx.get("book") == "system_matched"
        straight = booked and not fx.get("composite") and _straight_play(by_id.get(fx.get("call_id")), role)
        if not straight:
            a["arm_note"] = (NOT_STRAIGHT_PLAY if booked else SIDE_RELOGGED if timed and _relog(fx, page, calls)
                             else PRE_CLOSE_OFF_ARM)
            continue
        if opened is None:
            a["arm_note"] = TIME_UNREAD
            continue
        # THE GATE (ii), 285 items 2(4) and 2(6): the prematch page before the fill PLAYs its side.
        pre = prematch_before(prematch, ev, opened)
        if pre is None:
            a["arm_note"] = NO_PREMATCH
            continue
        if pre == PREMATCH_UNTIMED or "refused" in pre:
            a["arm_note"] = PREMATCH_UNTIMED if pre == PREMATCH_UNTIMED else pre["refused"]
            continue
        on = _on_side(fx, pre) if pre["call"] == "PLAY" else False
        if on is None:
            a["arm_note"] = SIDE_UNREAD
            continue
        if not on:
            a["arm_note"] = PREMATCH_NOT_PLAY
            continue
        a["prematch_page"] = _brief(pre)
        price = _price(fx.get("entry"))
        # 283 2(b), the prematch page's own ask on the fill's contract: a lot above it is counted, never excluded.
        pask = page_ask(pre, fx.get("ticker"), fx.get("side"))
        a["prematch_ask"] = pask
        a["above_prematch_ask"] = None if price is None or pask is None else round(price - pask, 6) > 0
        # The closing page's unknowns, for a fill both gates admit (1(b): NOT CLASSIFIED, never dropped).
        if page is None:
            a["arm_note"] = NO_PAGE
            continue
        if "refused" in page:
            a["arm_note"] = page["refused"]
            continue
        if page["run"] is None:
            a["arm_note"] = RUN_UNKNOWN
            continue
        if page["call"] not in ("PLAY", "PASS"):
            a["arm_note"] = NOT_RULED_CALL
            continue
        if page["call"] == "PLAY" and (page["pick"] not in ROLES or pre["pick"] not in ROLES):
            a["arm_note"] = SIDE_UNREAD
            continue
        cc = {"match_id": page["match_id"], "run": page["run"], "start": page["start"], "pick": page["pick"],
              "units": page["units"]}
        if page["call"] == "PLAY" and page["pick"] == pre["pick"]:
            ask = page_ask(page, fx.get("ticker"), fx.get("side"))
            a.update(arm=ARM_EARLY, early=True, early_price=price, closing_ask=ask, early_clv_cents=_cents(ask, price),
                     closing_call=cc,
                     arm_note=ENTRY_UNREAD if price is None else ASK_UNREAD if ask is None else None)
            continue
        a.update(arm=ARM_FLIP, ledger_call_id=fx.get("call_id"), book=ARM_BOOK, call_id=None,
                 category="arm flip (booked to the arm, 2(c)(iii))", early_price=price,
                 closing_call={**cc, "call": page["call"]}, arm_note=ENTRY_UNREAD if price is None else None)
        closed, ko = as_utc(fx.get("closed")), page["kickoff"]
        sale = _sale(fx)
        if sale is False:
            a["flip_exit"] = FLIP_SETTLED if _num(fx.get("exit")) in (0.0, 1.0) else FLIP_OPEN
        elif ko is None or closed is None:
            a["flip_exit"] = FLIP_TIME_UNREAD
        elif sale is None:
            a["flip_exit"] = FLIP_SALE_UNREAD
        elif closed < ko:
            a["flip_exit"] = FLIP_EXITED
            a["flip_exit_price"] = _num(fx.get("exit"))
            a["flip_cost_cents"] = _flip_cost(fx)
        else:
            a["flip_exit"] = FLIP_LATE
    arm_events = {event_of(a.get("ticker")) for a in out if a["arm"] in (ARM_EARLY, ARM_FLIP)}
    for a in out:
        if a.get("kind") != "sport" or event_of(a.get("ticker")) not in arm_events:
            continue
        why = [BREACH_HELD] if a["arm"] == ARM_FLIP and a["flip_exit"] == FLIP_SETTLED else []
        page = by_event.get(event_of(a.get("ticker")))
        ko = page.get("kickoff") if isinstance(page, dict) else None
        opened, closed = as_utc(a.get("opened")), as_utc(a.get("closed"))
        sale = _sale(a)
        if ko is not None:
            if opened is not None and opened >= ko:
                why.insert(0, BREACH_OPENED)
            if sale and closed is not None and closed >= ko:
                why.append(BREACH_SOLD)
        if why:
            a["arm_breach"], a["breach_why"] = True, " and ".join(why)
        # 286 item 3(2), breach or not (the ruling has no exception: a cause not read is not a count): a closing page
        # without a kickoff, or a sale (or a sale not read) whose clock is unread, marks the lot breach_unread.
        if ko is None or (sale is not False and closed is None):
            a["breach_unread"] = True
        elif not why and sale is None and closed >= ko:   # closed after kickoff, its sale not read
            a["breach_unread"] = True                 # never "no breach": the discipline count is a count, never a guess
    return out


def _mean(xs: list) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _wmean(lots: list, key: str) -> float | None:
    """The contract-weighted (qty) mean of the lots' `key`; None when any lot's qty or value is unread."""
    pairs = [(_num(r.get("qty")), _num(r.get(key))) for r in lots]
    if not pairs or any(q is None or q <= 0 or v is None for q, v in pairs):
        return None
    return round(sum(q * v for q, v in pairs) / sum(q for q, _ in pairs), 4)


def _settle_units(lots: list, units) -> float | None:
    """285 item 2(3), a reading: units × Σ qty·(settle − entry) / Σ qty·entry; None when any figure is unread."""
    u = _num(units)
    trip = [(_num(r.get("qty")), _price(r.get("entry")), _num(r.get("exit"))) for r in lots]
    if u is None or not trip or any(q is None or q <= 0 or e is None or x is None for q, e, x in trip):
        return None
    return round(u * sum(q * (x - e) for q, e, x in trip) / sum(q * e for q, e, _ in trip), 4)


def arm_games(rows: list[dict]) -> list[dict]:
    """The arm's games (285 item 2(2)), by the time of their first arm fill: per event its early CLV, flip cost and
    settlement result (the module docstring), whether a breach or a breach not read falls on it, and its lots."""
    from src.walters.redated import as_utc
    by: dict = {}
    for r in rows:
        if r.get("arm") in (ARM_EARLY, ARM_FLIP):
            by.setdefault(event_of(r.get("ticker")), []).append(r)
    out = []
    for ev, lots in by.items():
        lots = sorted(lots, key=lambda r: as_utc(r.get("opened")) or datetime.max)
        early = [r for r in lots if r["arm"] == ARM_EARLY]
        flips = [r for r in lots if r["arm"] == ARM_FLIP]
        exited = [r for r in flips if r.get("flip_exit") == FLIP_EXITED]
        held = [r for r in flips if r.get("flip_exit") == FLIP_SETTLED]
        pending = [r for r in flips if r.get("flip_exit") in (FLIP_OPEN, FLIP_SALE_UNREAD, FLIP_TIME_UNREAD)]
        on_ev = [r for r in rows if r.get("kind") == "sport" and event_of(r.get("ticker")) == ev]
        units = (lots[0].get("prematch_page") or {}).get("units")
        g = {"event": ev, "first": as_utc(lots[0].get("opened")), "lots": len(lots),
             "early": bool(early), "flip": bool(flips),
             "early_clv_cents": _wmean(early, "early_clv_cents") if early else None,
             "flip_cost_cents": (_wmean(exited, "flip_cost_cents") if exited and not pending else None),
             "flip_exited": bool(exited), "held": bool(held),
             "settle_units": _settle_units(held, units) if held else None,
             "flip_not_exited": sorted({r["flip_exit"] for r in flips if r.get("flip_exit") in NOT_EXITED_KEYS}),
             "closing_units": (early[0].get("closing_call") or {}).get("units") if early else None,
             "breach": any(r.get("arm_breach") for r in on_ev),
             "breach_unread": any(r.get("breach_unread") for r in on_ev)}
        # A game's number for the read: its early CLV where it has early lots, its flip cost where it has exited flip
        # lots (a flip held or exited late is a breach, outside the mean); an exit not established is unpriced (law 4);
        # a held flip whose settlement result is unread is unpriced (286 item 3(3): the denominator holds only numbers).
        g["priced"] = ((not early or g["early_clv_cents"] is not None)
                       and (not exited or g["flip_cost_cents"] is not None) and not pending
                       and (not held or g["settle_units"] is not None))
        out.append(g)
    return sorted(out, key=lambda g: (g["first"] or datetime.max, g["event"] or ""))


def the_read(games: list[dict], unclassified: int) -> dict:
    """THE READ AT THIRTY (283 item 3; 285 items 1(b), 2(2), 2(3)), on the first READ_AT games: {"read", "net",
    "blocking"}. `unclassified` counts the NOT CLASSIFIED and NOT RULED rows. In order: refused while unclassified;
    HELD while any game of the thirty has a breach not read (286 item 3(2)), then while any is unpriced (286 item
    3(3)), the count printed, no net, no verdict; a breach in the thirty with its net (2(3): "reported with the read";
    no verdict); else CONTINUE / STOP with the net."""
    if len(games) < READ_AT:
        return {"read": READ_BELOW, "net": None, "blocking": None}
    if unclassified:
        return {"read": READ_REFUSED, "net": None, "blocking": unclassified}
    thirty = games[:READ_AT]
    # 286 item 3(2): HELD while any game of the thirty has a breach not read (the discipline count is a count, never
    # a guess), ahead of a breach: a breach count beside an unread one is not a count.
    n = sum(1 for g in thirty if g["breach_unread"])
    if n:
        return {"read": READ_BREACH_UNREAD, "net": None, "blocking": n}
    # 286 item 3(3): HELD while any game of the thirty is unpriced (the denominator holds only numbers), ahead of a
    # breach: a held flip is a breach, so a breach first would never hold.
    unpriced = sum(1 for g in thirty if not g["priced"])
    if unpriced:
        return {"read": READ_UNPRICED, "net": None, "blocking": unpriced}
    clv = sum(g["early_clv_cents"] for g in thirty if g["early"])
    cost = sum(g["flip_cost_cents"] for g in thirty if g["flip_cost_cents"] is not None)
    net = round((clv - cost) / len(thirty), 4)
    n = sum(1 for g in thirty if g["breach"])
    if n:
        return {"read": READ_BREACH, "net": net, "blocking": n}
    return {"read": READ_CONTINUE if net > 0 else READ_STOP, "net": net, "blocking": None}


def arm_table(rows: list[dict]) -> dict:
    """The arm's table (item 4: "count, mean early CLV, flip count and cost, breaches"; 285: games, not lots), in
    cents and units only: counts of games (lots a count beside them), means and totals of cents per contract over
    games, the early games by the closing page's units, the settlement result in units, breaches by cause, every
    arm_note counted on a line (NOT CLASSIFIED by cause), interest rows (None when the export carries no `type`), and
    the read at thirty (the_read). Never a dollar figure, never a contract count."""
    games = arm_games(rows)
    early = [g for g in games if g["early"]]
    flips = [g for g in games if g["flip"]]
    clv = [g["early_clv_cents"] for g in early if g["early_clv_cents"] is not None]
    fc = [g["flip_cost_cents"] for g in flips if g["flip_cost_cents"] is not None]
    held = [g for g in flips if g["held"]]
    su = [g["settle_units"] for g in held if g["settle_units"] is not None]
    units: dict = {}
    for g in early:
        u = g["closing_units"]
        k = f"{u:g}u" if isinstance(u, (int, float)) else "units not printed"
        units[k] = units.get(k, 0) + 1
    not_the_arms = {v: 0 for v in NOT_THE_ARMS_KEYS.values()}
    unest = {v: 0 for v in UNESTABLISHED_KEYS.values()}
    nc = {v: 0 for v in NOT_CLASSIFIED_KEYS.values()}
    ordinary = not_ruled = 0
    lots = [r for r in rows if r.get("arm") in (ARM_EARLY, ARM_FLIP)]
    ask_unread = sum(1 for r in lots if r["arm"] == ARM_EARLY and r.get("closing_ask") is None)
    for r in rows:
        n = r.get("arm_note")
        if n is None or r.get("arm") in (ARM_EARLY, ARM_FLIP):
            continue                       # an arm lot's note names a figure unread: counted by its fields below
        if n in NOT_THE_ARMS_KEYS:
            not_the_arms[NOT_THE_ARMS_KEYS[n]] += 1
        elif n in UNESTABLISHED_KEYS:
            unest[UNESTABLISHED_KEYS[n]] += 1
        elif n in NOT_CLASSIFIED_KEYS:
            nc[NOT_CLASSIFIED_KEYS[n]] += 1
        elif n == AFTER_RUN:
            ordinary += 1
        elif n == NOT_RULED_CALL:
            not_ruled += 1
        else:
            nc[OTHER_NOTE] = nc.get(OTHER_NOTE, 0) + 1
    breach_rows = [r for r in rows if r.get("arm_breach")]
    by_cause = {c: sum(1 for r in breach_rows if c in (r.get("breach_why") or "").split(" and "))
                for c in BREACH_CAUSES}
    carried = any(isinstance(r, dict) and "type" in r for r in rows)
    read = the_read(games, sum(nc.values()) + not_ruled)
    return {"arm_games": len(games), "early_games": len(early), "flip_games": len(flips),
            "lots": sum(g["lots"] for g in games),
            "early_games_priced": len(clv), "early_lots_ask_unread": ask_unread,
            "arm_lots_entry_unread": sum(1 for r in lots if r.get("early_price") is None),
            "arm_lots_above_prematch_ask": sum(1 for r in lots if r.get("above_prematch_ask") is True),
            "arm_lots_prematch_ask_unread": sum(1 for r in lots if r.get("above_prematch_ask") is None),
            "mean_early_clv_cents_per_game": _mean(clv),
            "early_games_by_units": dict(sorted(units.items())),
            "flip_games_exited": sum(1 for g in flips if g["flip_exited"]), "flip_games_priced": len(fc),
            "mean_flip_cost_cents_per_game": _mean(fc), "total_flip_cost_cents": round(sum(fc), 4) if fc else None,
            "flip_games_not_exited": {v: sum(1 for g in flips if k in g["flip_not_exited"])
                                      for k, v in NOT_EXITED_KEYS.items()},
            "flip_held_to_settlement_games": len(held), "flip_held_settlement_units": round(sum(su), 4) if su else None,
            "flip_held_unpriced_games": len(held) - len(su),
            "breaches": len(breach_rows), "breaches_by_cause": by_cause,
            "breach_games": sum(1 for g in games if g["breach"]),
            "breaches_not_read": sum(1 for r in rows if r.get("breach_unread")),
            "interest_carried": carried,
            "interest_rows": sum(1 for r in rows if r.get("kind") == INTEREST_KIND) if carried else None,
            "ordinary": ordinary, "not_the_arms": not_the_arms, "unestablished": unest, "not_ruled": not_ruled,
            "not_classified": nc, "toward_thirty": len(games), "read_at": READ_AT,
            "read": read["read"], "read_net_cents_per_game": read["net"], "read_blocking": read["blocking"]}


def _c(x) -> str:
    return "—" if x is None else f"{x:+.2f}¢"


def _u(x) -> str:
    return "—" if x is None else f"{x:+.2f}u"


def _kv(d: dict) -> str:
    return " · ".join(f"{k} {v}" for k, v in d.items()) or "none"


def read_line(t: dict) -> str:
    n, rd = t["toward_thirty"], t["read"]
    head = f"THE READ at {t['read_at']} games (283 item 3; 285 items 1(b), 2(3)): "
    if rd == READ_BELOW:
        return head + f"{n} of {t['read_at']} — no read before thirty, no verdict"
    if rd == READ_REFUSED:
        nc = sum(t["not_classified"].values())
        return head + (f"REFUSED: {t['read_blocking']} rows not classified (NOT CLASSIFIED {nc} · NOT RULED "
                       f"{t['not_ruled']}) — no mean is computed while any row is unclassified (285 item 1(b))")
    if rd == READ_BREACH:
        net = (f"mean early CLV net of flip costs {_c(t['read_net_cents_per_game'])} per game over the first "
               f"{t['read_at']}")             # 286 item 3(3): a breach is read only when every game is priced
        return head + (f"breach in the thirty: {t['read_blocking']} games · {net} (reported with the read, 285 item "
                       "2(3)) — no verdict: the continuation is the architect's ruling on the record")
    if rd == READ_BREACH_UNREAD:
        return head + (f"HELD: breach not read in the thirty: {t['read_blocking']} games (a sale or kickoff clock not "
                       "read) — no mean, no verdict (law 4; 286 item 3(2): the discipline count is a count, never a "
                       "guess)")
    if rd == READ_UNPRICED:
        return head + (f"HELD: unpriced in the thirty: {t['read_blocking']} games — no net, no verdict (law 4; 286 "
                       "item 3(3): the denominator holds only numbers)")
    return head + (f"{rd}: mean early CLV net of flip costs {_c(t['read_net_cents_per_game'])} per game over the "
                   f"first {t['read_at']} (positive continues; a tie rejects, law 3) — the read is the architect's, "
                   "by a block")


def table_lines(t: dict) -> list[str]:
    """The table as printed: counts of games (lots a count), cents per contract, units; nothing else."""
    nc = sum(t["not_classified"].values())
    interest = ("interest rows: not carried by this export" if not t["interest_carried"]
                else f"interest rows: {t['interest_rows']}")
    return [
        f"EARLY (before the closing run, on the prematch page's side, which the closing page PLAYs; a straight PLAY "
        f"call): games {t['early_games']} · priced {t['early_games_priced']} · mean early CLV "
        f"{_c(t['mean_early_clv_cents_per_game'])} per game (the closing page's ask on the side − the "
        f"contract-weighted early price, × 100; fees out of both; positive = early was cheaper) · lots whose "
        f"contract the closing page quotes no ask for {t['early_lots_ask_unread']} · by the closing page's units: "
        f"{_kv(t['early_games_by_units'])}",
        f"ARM FLIP (the close PASSed or changed side; booked to the arm): games {t['flip_games']} · exited before "
        f"kickoff {t['flip_games_exited']} (priced {t['flip_games_priced']}) · flip cost mean "
        f"{_c(t['mean_flip_cost_cents_per_game'])} per game, total {_c(t['total_flip_cost_cents'])} ((early entry − "
        f"pre-kickoff exit) × 100 + both legs' taker fees per contract, contract-weighted; positive = a cost)",
        f"ARM FLIP NOT EXITED before kickoff (games, by cause): {_kv(t['flip_games_not_exited'])} — not in the flip "
        "cost",
        f"FLIP HELD TO SETTLEMENT (a breach of 2(c)(iii), outside the CLV mean, 285 item 2(3)): games "
        f"{t['flip_held_to_settlement_games']} · settlement result {_u(t['flip_held_settlement_units'])} (units of "
        f"the prematch page's call × (settle − entry) / entry, contract-weighted) · unpriced "
        f"{t['flip_held_unpriced_games']}",
        f"ARM BREACH (2(d), 2(3)): fills {t['breaches']} ({_kv(t['breaches_by_cause'])}) · games "
        f"{t['breach_games']} · not read (closed at or after kickoff, its sale not read; a sale whose clock is not "
        f"read; a closing page without a kickoff, 286 item 3(2)): {t['breaches_not_read']}",
        f"ABOVE THE PREMATCH PAGE'S ASK (283 item 2(b) \"never above it\": counted, never excluded, not a breach; not "
        f"ruled): above the prematch page's ask: {t['arm_lots_above_prematch_ask']} lots · not compared (the page's "
        f"ask or the entry not read) {t['arm_lots_prematch_ask_unread']} · entry price not read (outside 0 to 1) "
        f"{t['arm_lots_entry_unread']}",
        f"INTEREST (its own kind, never attributed to a call or to the arm, 2(f)): {interest}",
        f"NOT THE ARM'S: {_kv(t['not_the_arms'])} · UNESTABLISHED (listed, never counted): "
        f"{_kv(t['unestablished'])} · NOT RULED (a LADDER or VENUE close; it holds the read): {t['not_ruled']} · "
        f"ORDINARY (opened at or after the closing page went out): {t['ordinary']}",
        f"NOT CLASSIFIED (counts by cause, 285 item 1(b)): {nc} — {_kv(t['not_classified'])}",
        f"COUNT toward thirty (the arm's games, early or flip, 285 item 2(2)): {t['toward_thirty']} of "
        f"{t['read_at']} (lots {t['lots']})",
        read_line(t),
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
