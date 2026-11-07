"""THE EARLY-ENTRY ARM, ATTRIBUTED (#862; addendum 283 item 4, ruled further by addendum 285):
src/walters/early_arm.py and scripts/early_arm_receipt.py, read-only.

The world is synthetic (no real CSV row, no account id, no fill figure from any real file, no real game: the clubs
and the ticker are fictional, Testford at Mockley): its closing pages written as production writes them
(deploy/hosting/closing.closing_doc: the closing block's start is the COVERED start, a kickoff; the file's
exported_at is when the run's page went out, the run going at the start less RUN_LEAD_MIN), its prematch pages as the
family's slate export (a Desk page: exported_at, desk_meta, predictions; named by the family's export_glob, a stamp
per page so that two pages may sit in one folder), and a Cockpit ledger export whose fills are the entries
importKalshiCSV stores (ledger_fills.parse_ticker / side_fields spread in), every figure invented here. Pins: each
attribution case (early on the prematch side the close PLAYs; arm flip on a PASS and on a side change, paired with
its pre-kickoff exit; the two gates of addendum 285 1(a) and 2(6); a same-day side re-log; an ordinary fill after the
page went out; the latest page decides, by its export time; a LADDER close is not ruled; pages that disagree are
refused; latest/ is refused), the CLV formula (the closing ask less the fill), the flip cost (fees in), the games as
the unit, a breach (an entry after kickoff, a sale after kickoff, a flip held to settlement; a settlement of an early
lot is none; a sale not read is labelled), NOT CLASSIFIED, the read at thirty, interest rows (their own kind; not
carried when no fill has a type), the matcher untouched and a flip out of executed_positions, the receipt's table in
cents and units only, and the bulletin's one word. The tests named test_285_* each failed first on bed68361.
"""
import importlib.util
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.walters import early_arm as ea
from src.walters import ledger_fills as lf
from tests.test_void_redated import _closing

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("early_arm_receipt", ROOT / "scripts" / "early_arm_receipt.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)
CL = _closing()

EVENT = "KXEPLGAME-26NOV08TSTMCK"                 # fictional clubs and ticker (no real game, no live position)
TST, MCK, TIE = f"{EVENT}-TST", f"{EVENT}-MCK", f"{EVENT}-TIE"
KO = "2026-11-08T14:00:00"                        # naive UTC, the row's utc_date
KO_DT = datetime(2026, 11, 8, 14, 0)              # the covered start: what closing_doc writes as closing.start
RUN = datetime(2026, 11, 8, 13, 26, 7, 123456)    # the page's exported_at: the run went at KO - 35 min (13:25)
PRE = "2026-11-07T15:30:00-05:00"                 # opened the day before (an offset, as Kalshi writes it)
PRE_AT = datetime(2026, 11, 7, 11, 0, 7)          # the prematch page's exported_at (06:00 ET), before PRE
QTY, ENTRY, EXIT_, FEE = 4711, 0.4913, 0.4512, 0.0123    # invented figures: none may reach the receipt's output
ASK = 0.50                                        # the page's ask on Testford (its exec cost 0.51 = ask + fee)
FILL_ID = "syn-FIXTURE␟fixture␟0001"            # a synthetic id (a real one carries the account id)


def row(call="PLAY", pick="AWAY", cost=0.51, order=TST, side="YES", mid=9001, units=0.5, ko=KO, ask=ASK, legs=None):
    desk = {"call": call, "pick": pick, "units": units if call != "PASS" else 0,
            "exec": {"cost": cost, "basis": "taker", "contracts": 777},
            "order": {"ticker": order, "side": side, "limit": ask, "contracts": 777} if call in ("PLAY", "LADDER")
            else None}
    legs = legs or {"HOME": {"ticker": MCK, "bid": 0.29, "ask": 0.31}, "AWAY": {"ticker": TST, "bid": 0.49, "ask": ask},
                    "DRAW": {"ticker": TIE, "bid": 0.23, "ask": 0.25}}
    return {"match_id": mid, "home_team": "Mockley", "away_team": "Testford", "utc_date": ko, "competition": "PL",
            "desk": desk, "kalshi_legs": legs}


def write_page(ex: Path, at: datetime | None, rows: list[dict], start: datetime = KO_DT, fam: str = "SOCCER") -> Path:
    """One closing file as production writes it: closing_doc over the run's export (its exported_at the run's own,
    utc_now_naive().isoformat() + "Z"), the closing block's start the covered start, the name closing_name's."""
    ex.mkdir(parents=True, exist_ok=True)
    doc = {"sport": "soccer", "predictions": rows}
    if at is not None:
        doc["exported_at"] = at.isoformat() + "Z"
    run_id = f"{(at or start):%Y%m%dT%H%M%SZ}-pl-closing"
    p = ex / CL.closing_name(fam, start)
    p.write_text(json.dumps(CL.closing_doc(doc, fam, start, run_id, [r["match_id"] for r in rows], [])))
    return p


def write_prematch(ex: Path, at: datetime | None, rows: list[dict], name: str | None = None) -> Path:
    """One prematch Desk page as the family's slate export writes it (exported_at, desk_meta, predictions), named by
    the family's export_glob (soccer_PL_*.json) with a stamp of its own time."""
    ex.mkdir(parents=True, exist_ok=True)
    doc = {"sport": "soccer", "desk_meta": {"as_of": "synthetic"}, "count": len(rows), "predictions": rows}
    if at is not None:
        doc["exported_at"] = at.isoformat() + "Z"
    p = ex / (name or f"soccer_PL_{(at or PRE_AT):%Y%m%dT%H%M%S}_to_2026-11-10.json")
    p.write_text(json.dumps(doc))
    return p


def entry(ticker=TST, side="yes", opened=PRE, closed="2026-11-08T16:00:00Z", exit_=1.0, close_fee=0.0, entry_=ENTRY,
          fid=FILL_ID, qty=QTY, **extra):
    """The entry the Cockpit's importKalshiCSV stores (synthetic figures)."""
    title = {"TST": "Testford wins — Mockley", "MCK": "Mockley wins — Testford", "TIE": "Tie — Testford v Mockley"}
    fx = {"id": fid, "ticker": ticker, "side": side, "qty": qty, "entry": entry_, "exit": exit_,
          "staked": round(qty * entry_, 4) if entry_ is not None else None, "fees": round(FEE + (close_fee or 0), 4),
          "open_fee": FEE, "close_fee": close_fee, "pnl_pre": 0.0, "pnl_net": 0.0, "opened": opened,
          "closed": closed, "title": title.get(ticker.rsplit("-", 1)[-1], ""), **extra}
    p = lf.parse_ticker(fx["ticker"])
    fx.update(p)
    if p["kind"] == "sport":
        fx.update(lf.side_fields(p, fx["title"], fx["side"]))
    return fx


def call(pick="AWAY", cid="c1", graded=False, log_date="2026-11-07", **kw):
    c = {"id": cid, "sport": "PL", "home": "Mockley", "away": "Testford", "kickoff": KO + "Z", "log_date": log_date,
         "call_type": "straight", "pick": pick, "units": 0.5, "engine": "model_edge", "tier": "A", **kw}
    if graded:
        c.update(status="graded", close_ref={"fair": {"HOME": 0.3, "AWAY": 0.5, "DRAW": 0.2}})
    return c


def world(tmp_path, pages, fills, calls=(), prematch=None):
    """pages: [(exported_at, rows) or (exported_at, rows, start) or (exported_at, rows, start, dated folder)];
    prematch: [(exported_at, rows) or (exported_at, rows, dated folder)], default one page PLAYing Testford at
    PRE_AT (06:00 ET the day before), before the fills."""
    ex = tmp_path / "exports"
    ex.mkdir(parents=True, exist_ok=True)
    for pg in pages:
        at, rows, start, sub = (list(pg) + [KO_DT, None][len(pg) - 2:])[:4]
        write_page(ex / sub if sub else ex, at, rows, start)
    for pg in ([(PRE_AT, [row()])] if prematch is None else prematch):
        at, rows, sub = (list(pg) + [None])[:3]
        write_prematch(ex / sub if sub else ex, at, rows)
    return {"calls": list(calls), "fills": list(fills)}, ex


def one(tmp_path, page_row, f, calls=(call(),), extra_pages=(), prematch=None):
    L, ex = world(tmp_path, [*extra_pages, (RUN, [page_row])], [f], calls, prematch)
    return ea.attribute(L, ex)[0], L, ex


# ---- the attribution ----------------------------------------------------------------------------------------------

def test_early_is_attributed_to_the_closing_call_with_its_price_and_clv(tmp_path):
    a, L, _ = one(tmp_path, row(), entry())
    assert a["arm"] == ea.ARM_EARLY and a["early"] is True
    assert a["early_price"] == ENTRY and a["closing_ask"] == ASK
    assert a["early_clv_cents"] == pytest.approx((ASK - ENTRY) * 100)
    assert a["closing_call"] == {"match_id": 9001, "run": RUN, "start": KO_DT, "pick": "AWAY", "units": 0.5}
    assert a["prematch_page"] == {"run": PRE_AT, "call": "PLAY", "pick": "AWAY", "units": 0.5}
    base = lf.classify_fills(L)[0]                     # the matcher untouched: the closing call's own booking kept
    assert (a["book"], a["call_id"]) == (base["book"], base["call_id"]) == ("system_matched", "c1")
    assert not a["arm_breach"]


def test_the_clv_sign_positive_when_early_was_cheaper(tmp_path):
    cheap, _, _ = one(tmp_path / "a", row(ask=0.55, cost=0.5675), entry(entry_=0.50))
    dear, _, _ = one(tmp_path / "b", row(ask=0.55, cost=0.5675), entry(entry_=0.58))
    assert cheap["early_clv_cents"] == pytest.approx(5.0) and cheap["early_clv_cents"] > 0
    assert dear["early_clv_cents"] == pytest.approx(-3.0) and dear["early_clv_cents"] < 0


def test_early_on_the_pick_by_another_contract_takes_that_contracts_ask_or_none(tmp_path):
    """285 item 2(1): a fill on the side through a contract other than the page's order contract takes the page's
    kalshi_legs ask for the fill's own contract; a page that quotes no ask for it gives null, labelled, never derived."""
    other = row(order="KXEPLGAME-26NOV08TSTMCK-XXX")
    a, _, _ = one(tmp_path / "a", other, entry())
    assert a["arm"] == ea.ARM_EARLY and a["closing_ask"] == ASK
    bare = row(legs={"HOME": {"ticker": MCK, "bid": 0.29, "ask": 0.31}, "AWAY": {"ticker": TST, "bid": None,
                                                                                "ask": None}})
    b, _, _ = one(tmp_path / "b", bare, entry())
    assert b["arm"] == ea.ARM_EARLY and b["closing_ask"] is None and b["early_clv_cents"] is None
    assert b["arm_note"] == ea.ASK_UNREAD
    t = ea.arm_table([b])
    assert (t["early_games"], t["early_games_priced"], t["early_lots_ask_unread"]) == (1, 0, 1)
    assert sum(t["not_classified"].values()) == 0                  # an early lot, classified: its figure unread


def test_flip_on_a_pass_close_paired_with_its_pre_kickoff_exit(tmp_path):
    f = entry(closed="2026-11-08T13:10:00Z", exit_=EXIT_, close_fee=0.0101)        # sold before kickoff
    a, _, _ = one(tmp_path, row(call="PASS"), f)
    assert a["arm"] == ea.ARM_FLIP and a["early"] is False
    assert a["book"] == ea.ARM_BOOK and a["call_id"] is None and a["ledger_call_id"] == "c1"
    assert a["closing_ask"] is None and a["early_clv_cents"] is None
    assert a["flip_exit_price"] == EXIT_ and a["flip_exit"] == "exited before kickoff"
    assert a["flip_cost_cents"] == pytest.approx((ENTRY - EXIT_) * 100 + (FEE + 0.0101) / QTY * 100, abs=1e-4)
    assert a["flip_cost_cents"] > 0 and not a["arm_breach"]


def test_flip_when_the_close_picks_another_side(tmp_path):
    a, _, _ = one(tmp_path, row(pick="HOME", order=MCK), entry())
    assert a["arm"] == ea.ARM_FLIP and a["closing_call"]["pick"] == "HOME" and a["closing_ask"] is None
    assert a["prematch_page"]["pick"] == "AWAY"


def test_a_pre_closing_fill_with_no_logged_play_is_not_the_arms(tmp_path):
    a, L, _ = one(tmp_path, row(call="PASS"), entry(), calls=())
    assert a["arm"] is None and a["arm_note"] == ea.PRE_CLOSE_OFF_ARM
    assert a["book"] == lf.classify_fills(L)[0]["book"] == "off_book_sports"     # its booking unchanged


def test_a_fill_after_the_closing_run_is_ordinary(tmp_path):
    a, _, _ = one(tmp_path, row(), entry(opened="2026-11-08T13:40:00Z"))      # after the page, before kickoff
    assert a["arm"] is None and a["arm_note"] == ea.AFTER_RUN and a["book"] == "system_matched"
    assert ea.arm_table([a])["ordinary"] == 1


def test_the_latest_closing_run_decides(tmp_path):
    """A re-dated game: its earlier page (another start, the day before) PLAYed; the later page PASSes."""
    earlier = (datetime(2026, 11, 7, 13, 26), [row(ko="2026-11-07T14:00:00")], datetime(2026, 11, 7, 14, 0))
    a, _, _ = one(tmp_path, row(call="PASS"), entry(opened="2026-11-06T15:30:00Z"), extra_pages=[earlier],
                  prematch=[(datetime(2026, 11, 6, 11, 0), [row()])])
    assert a["arm"] == ea.ARM_FLIP


def test_a_ladder_close_is_not_ruled(tmp_path):
    a, _, _ = one(tmp_path, row(call="LADDER", order=MCK, side="NO"), entry())
    assert a["arm"] is None and a["arm_note"] == ea.NOT_RULED_CALL
    assert ea.arm_table([a])["not_ruled"] == 1


def test_pages_of_one_run_that_disagree_are_refused(tmp_path):
    L, ex = world(tmp_path, [(RUN, [row()]), (RUN, [row(call="PASS")], KO_DT, "2026-11-08")], [entry()], [call()])
    a = ea.attribute(L, ex)[0]                                  # the same run (one export time), a dated copy differs
    assert a["arm"] is None and a["arm_note"] == ea.DISAGREE


def test_no_page_and_unread_time(tmp_path):
    L, ex = world(tmp_path / "a", [], [entry()], [call()])                       # no closing page at all
    a = ea.attribute(L, ex)[0]
    b, _, _ = one(tmp_path / "b", row(), entry(opened=None))
    assert a["arm_note"] == ea.NO_PAGE and b["arm_note"] == ea.TIME_UNREAD and a["arm"] is b["arm"] is None


# ---- the breach ---------------------------------------------------------------------------------------------------

def test_a_fill_opened_after_kickoff_on_an_arm_position_is_a_breach(tmp_path):
    early = entry()
    add = entry(opened="2026-11-08T14:20:00Z", fid="syn-2")
    L, ex = world(tmp_path, [(RUN, [row()])], [early, add], [call()])
    a, b = ea.attribute(L, ex)
    assert a["arm"] == ea.ARM_EARLY and not a["arm_breach"]
    assert b["arm_breach"] and b["breach_why"] == "opened at or after kickoff"


def test_a_sale_after_kickoff_is_a_breach_and_a_settlement_is_not(tmp_path):
    sold = entry(closed="2026-11-08T15:00:00Z", exit_=0.7, close_fee=0.0102)
    a, _, _ = one(tmp_path / "a", row(), sold)
    b, _, _ = one(tmp_path / "b", row(), entry(closed="2026-11-08T16:00:00Z", exit_=1.0, close_fee=0.0))
    assert a["arm"] == ea.ARM_EARLY and a["arm_breach"] and a["breach_why"] == "sold at or after kickoff"
    assert not b["arm_breach"]                                     # an EARLY lot settled: the call's position


def test_a_fill_after_kickoff_on_a_game_with_no_arm_position_is_no_breach(tmp_path):
    a, _, _ = one(tmp_path, row(), entry(opened="2026-11-08T14:20:00Z"))
    assert a["arm"] is None and not a["arm_breach"]


# ---- interest (2(f)) ----------------------------------------------------------------------------------------------

def test_an_interest_row_is_its_own_kind_never_attributed(tmp_path):
    i = entry(type="Interest", fid="syn-int")                # even on a sport ticker
    n = {"id": "syn-int-2", "ticker": "", "side": None, "qty": 0, "entry": 0, "opened": None, "closed": None,
         "title": None, "type": "interest"}
    L, ex = world(tmp_path, [(RUN, [row()])], [i, n], [call()])
    for a in ea.attribute(L, ex):
        assert a["kind"] == a["book"] == ea.INTEREST_KIND
        assert a["call_id"] is None and a["arm"] is None and not a["early"]
    t = ea.arm_table(ea.attribute(L, ex))
    assert t["interest_rows"] == 2 and t["interest_carried"] is True


def test_todays_export_carries_no_type_so_no_row_is_interest(tmp_path):
    a, _, _ = one(tmp_path, row(), entry())
    assert "type" not in entry() and a["kind"] == "sport"


# ---- the flip leaves the call's executed position -----------------------------------------------------------------

def test_a_flip_never_enters_executed_positions(tmp_path):
    L, ex = world(tmp_path, [(RUN, [row(call="PASS")])], [entry()], [call(graded=True)])
    assert [p["c"]["id"] for p in lf.executed_positions(L)["pos"]] == ["c1"]          # today's booking: counted
    assert lf.executed_positions(L, fills=ea.attribute(L, ex))["pos"] == []           # the arm's: booked to the arm


# ---- the table and the receipt ------------------------------------------------------------------------------------

QUI_EV = "KXEPLGAME-26NOV09QUIREX"


def _receipt_world(tmp_path, with_type=True):
    fills = [entry(fid="syn-e1"),                                                    # early, lot 1
             entry(fid="syn-e2", entry_=0.5300),                                     # early, lot 2 (one game)
             entry(ticker=f"{QUI_EV}-QUI", fid="syn-f1", title="Quillby wins — Rexham",
                   closed="2026-11-09T13:00:00Z",
                   exit_=EXIT_, close_fee=0.0101, entry_=0.4800, opened="2026-11-08T10:00:00Z"),   # flip, exited
             entry(fid="syn-b1", opened="2026-11-08T14:30:00Z")]                     # breach (an add after kickoff)
    if with_type:
        fills.append(entry(fid="syn-i1", type="interest", ticker=""))
    qlegs = {"HOME": {"ticker": f"{QUI_EV}-REX", "bid": 0.30, "ask": 0.32},
             "AWAY": {"ticker": f"{QUI_EV}-QUI", "bid": 0.47, "ask": 0.49}}
    ars = {**row(call="PASS", mid=9002, legs=qlegs), "home_team": "Rexham", "away_team": "Quillby",
           "utc_date": "2026-11-09T14:00:00"}
    ars_pre = {**row(mid=9002, order=f"{QUI_EV}-QUI", legs=qlegs, ask=0.49), "home_team": "Rexham",
               "away_team": "Quillby", "utc_date": "2026-11-09T14:00:00"}
    ars_call = {**call(cid="c2"), "home": "Rexham", "away": "Quillby", "kickoff": "2026-11-09T14:00:00Z"}
    L, ex = world(tmp_path, [(RUN, [row()]), (datetime(2026, 11, 9, 13, 26), [ars], datetime(2026, 11, 9, 14, 0))],
                  fills, [call(), ars_call], prematch=[(PRE_AT, [row(), ars_pre])])
    p = tmp_path / "bd_ledger_v1_2026-11-09.json"
    p.write_text(json.dumps({**L, "meta": {}}))
    return p, ex


def test_the_arm_table(tmp_path):
    p, ex = _receipt_world(tmp_path)
    t = ea.arm_table(ea.attribute(json.loads(p.read_text()), ex))
    assert (t["early_games"], t["early_games_priced"], t["flip_games"], t["flip_games_exited"], t["breaches"],
            t["interest_rows"], t["toward_thirty"], t["lots"], t["read_at"]) == (1, 1, 1, 1, 1, 1, 2, 3, 30)
    assert t["mean_early_clv_cents_per_game"] == pytest.approx(((ASK - ENTRY) + (ASK - 0.53)) * 50)   # equal qty
    assert t["mean_flip_cost_cents_per_game"] == pytest.approx((0.48 - EXIT_) * 100 + (FEE + 0.0101) / QTY * 100, abs=1e-4)
    assert t["early_games_by_units"] == {"0.5u": 1}
    assert t["read"] == ea.READ_BELOW and t["read_net_cents_per_game"] is None


def test_the_receipt_prints_cents_and_units_only(tmp_path, capsys):
    p, ex = _receipt_world(tmp_path)
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == 0
    out = capsys.readouterr().out.replace(str(ex.resolve()), "<exports>")    # the tmp path is not the receipt's
    assert "EARLY (" in out and "ARM FLIP" in out and "ARM BREACH" in out and "INTEREST" in out
    assert "¢" in out and "0.5u 1" in out and "2 of 30" in out and "lots 3" in out
    assert "arm breach: match 9001 Testford @ Mockley (kickoff 2026-11-08T14:00:00Z): opened at or after kickoff" in out
    for figure in ("$", "4711", "0.4913", "0.4512", "0.0123", "0.0101", "0.53", "0.48", "0.49", "777", "syn-",
                   "FIXTURE", "staked", "pnl", "qty", "contracts"):
        assert figure not in out, figure
    last = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert last["toward_thirty"] == 2 and last["breaches"] == 1


def test_the_receipt_refuses(tmp_path, capsys):
    assert script.main(["--ledger", str(tmp_path / "missing.json")]) == script.REFUSED
    p = tmp_path / "L.json"
    p.write_text(json.dumps({"calls": [], "fills": []}))
    assert script.main(["--ledger", str(p), "--exports", str(tmp_path / "none")]) == script.REFUSED
    p.write_text(json.dumps({"fills": []}))
    assert script.main(["--ledger", str(p), "--exports", str(tmp_path)]) == script.REFUSED
    assert all(ln.startswith("REFUSED: ") for ln in capsys.readouterr().out.strip().splitlines())


# ---- the bulletin's one word --------------------------------------------------------------------------------------

def test_the_bulletin_call_line_gains_only_the_word_early(tmp_path):
    line = "PLAY Testford 0.5u"
    assert ea.arm_call_line(line, True) == "PLAY Testford 0.5u early"
    assert ea.arm_call_line(line, False) == line
    assert ea.arm_call_line(line, True)[len(line):].split() == [ea.EARLY_WORD] == ["early"]
    a, _, _ = one(tmp_path, row(), entry())
    assert ea.early_calls([a]) == {(9001, RUN)}
    f, _, _ = one(tmp_path / "f", row(call="PASS"), entry())
    assert ea.early_calls([f]) == set()                     # a flip marks no call line


# ---- review round 1 (each failing first on 7ddac1a8) --------------------------------------------------------------

def test_the_closing_run_is_the_pages_export_time_not_the_covered_start(tmp_path):
    """closing_doc writes closing.start = the covered start (a kickoff); the run goes at start - RUN_LEAD_MIN and its
    page carries the run's exported_at. A fill after the page went out (13:40Z, at its ask) is the ordinary closing
    call's fill, never early; on a PASS page it is never an arm flip."""
    p = write_page(tmp_path / "x", RUN, [row()])
    assert json.loads(p.read_text())["closing"]["start"] == "2026-11-08T14:00:00Z"        # the kickoff, as written
    assert CL.RUN_LEAD_MIN == 35
    after = entry(opened="2026-11-08T13:40:00Z", entry_=0.51)
    a, _, _ = one(tmp_path / "a", row(), after)
    assert a["arm"] is None and a["arm_note"] == ea.AFTER_RUN and not a["early"]
    b, _, _ = one(tmp_path / "b", row(call="PASS"), after)
    assert b["arm"] is None and b["arm_note"] == ea.AFTER_RUN and b["book"] == "system_matched" and b["call_id"] == "c1"
    c, _, _ = one(tmp_path / "c", row(), entry(opened="2026-11-08T13:00:00Z"))          # before the page: early
    assert c["arm"] == ea.ARM_EARLY and c["closing_call"]["run"] == RUN and c["closing_call"]["start"] == KO_DT
    assert ea.arm_table([a, b])["toward_thirty"] == 0


def test_a_page_with_no_export_time_is_run_unknown_never_its_start(tmp_path):
    L, ex = world(tmp_path, [(None, [row()])], [entry()], [call()])
    a = ea.attribute(L, ex)[0]
    assert a["arm"] is None and a["arm_note"] == ea.RUN_UNKNOWN


def test_a_repaged_start_the_later_page_by_export_time_is_the_close(tmp_path):
    """Addendum 41: the later page is the close. Both pages carry the same closing.start; the earlier copy survives
    in a dated folder (the mirror dates by mtime, so a re-page across UTC midnight). The later export decides."""
    start = datetime(2026, 11, 8, 0, 30)
    ko = "2026-11-08T00:30:00"
    pages = [(datetime(2026, 11, 7, 23, 55), [row(ko=ko)], start, "2026-11-07"),
             (datetime(2026, 11, 8, 0, 12), [row(call="PASS", ko=ko)], start)]
    L, ex = world(tmp_path, pages, [entry(closed="2026-11-08T00:20:00Z", exit_=0.45, close_fee=0.01)],
                  [call(kickoff=ko + "Z")])
    a = ea.attribute(L, ex)[0]
    assert a["arm"] == ea.ARM_FLIP and a["book"] == ea.ARM_BOOK and a["call_id"] is None
    assert a["closing_call"]["call"] == "PASS" and a["flip_exit"] == ea.FLIP_EXITED


def test_early_needs_a_logged_play_call_on_its_side_as_a_flip_does(tmp_path):
    """Items 4 and 2(e): an early fill is "attributed to the closing call"; one the matcher booked to no call (no
    logged call, or only a value shadow on its side) is not the arm's, the same gate as a flip's."""
    none_, _, _ = one(tmp_path / "a", row(), entry(), calls=())
    shadow, _, _ = one(tmp_path / "b", row(), entry(),
                       calls=(call(call_type="value_shadow", units=0, shadow_units=0.5, cid="vs1"),))
    flip, _, _ = one(tmp_path / "c", row(call="PASS"), entry(closed="2026-11-08T13:10:00Z", exit_=EXIT_,
                                                             close_fee=0.0101), calls=())
    for a in (none_, shadow, flip):
        assert a["arm"] is None and not a["early"] and a["arm_note"] == ea.PRE_CLOSE_OFF_ARM
        assert a["early_clv_cents"] is None and a["book"] == "off_book_sports" and a.get("call_id") is None
    t = ea.arm_table([none_, shadow, flip])
    assert (t["toward_thirty"], t["early_games"], t["flip_games"]) == (0, 0, 0)
    assert t["not_the_arms"]["no straight PLAY call"] == 3
    assert t["mean_early_clv_cents_per_game"] is None


def test_a_same_day_side_relog_with_no_prematch_page_is_unestablished(tmp_path):
    """The Cockpit's callKey has no pick: a closing page that changes side the same ET day re-logs the prematch call
    in place, so the ledger keeps only the new side's call ("logged call exists but the side disagrees"). With no
    prematch page before the fill to give its side, it stays UNESTABLISHED (listed, never counted)."""
    L, ex = world(tmp_path, [(RUN, [row(pick="HOME", order=MCK)])], [entry(opened="2026-11-08T06:30:00-05:00")],
                  [call(pick="HOME", log_date="2026-11-08")], prematch=[])
    assert lf.classify_fills(L)[0]["category"] == ea.MATCHER_SIDE_DISAGREES
    a = ea.attribute(L, ex)[0]
    assert a["arm"] is None and a["arm_note"] == ea.SIDE_RELOGGED and a["book"] == "off_book_sports"
    t = ea.arm_table([a])
    assert (t["unestablished"]["same-day re-log"], t["toward_thirty"]) == (1, 0)
    assert any("UNESTABLISHED" in ln and "same-day re-log 1" in ln for ln in ea.table_lines(t))


def test_a_flip_not_exited_before_kickoff_is_a_labelled_line(tmp_path):
    held = entry(fid="syn-h", close_fee=0.0, exit_=0.0)
    late = entry(fid="syn-l", closed="2026-11-08T14:30:00Z", exit_=0.40, close_fee=0.01)
    done = entry(fid="syn-d", closed="2026-11-08T13:10:00Z", exit_=0.48, close_fee=0.01, entry_=0.49)
    L, ex = world(tmp_path, [(RUN, [row(call="PASS")])], [held, late, done], [call()])
    rows = ea.attribute(L, ex)
    assert [r["arm"] for r in rows] == [ea.ARM_FLIP] * 3
    assert [r["flip_exit"] for r in rows] == [ea.FLIP_SETTLED, ea.FLIP_LATE, ea.FLIP_EXITED]
    t = ea.arm_table(rows)
    assert (t["flip_games"], t["flip_games_exited"], t["flip_held_to_settlement_games"]) == (1, 1, 1)
    assert t["flip_games_not_exited"] == {"open at the export": 0, "exited at or after kickoff (a breach)": 1,
                                          "sale not read": 0, "time not read": 0}
    assert t["mean_flip_cost_cents_per_game"] == pytest.approx(1.0 + (FEE + 0.01) / QTY * 100, abs=1e-4)
    ln = next(x for x in ea.table_lines(t) if x.startswith("ARM FLIP NOT EXITED"))
    assert "exited at or after kickoff (a breach) 1" in ln and "not in the flip cost" in ln


def test_a_sale_not_read_is_labelled_never_read_as_a_settlement(tmp_path):
    """Law 4: close_fee None (a pre-#93 import, a CSV without the per-leg fee) or 0 on an exit strictly between 0
    and 1 is a sale NOT READ, never "no sale"; after kickoff its breach is not read either, never "no breach"."""
    none_fee = entry(closed="2026-11-08T15:10:00Z", exit_=0.45, close_fee=None)
    zero_fee = entry(closed="2026-11-08T15:10:00Z", exit_=0.45, close_fee=0.0)
    settled = entry(closed="2026-11-08T16:00:00Z", exit_=1.0, close_fee=0.0)
    p4, _, _ = one(tmp_path / "a", row(call="PASS"), none_fee)
    p5, _, _ = one(tmp_path / "b", row(), zero_fee)
    ok, _, _ = one(tmp_path / "c", row(), settled)
    assert p4["arm"] == ea.ARM_FLIP and p4["flip_exit"] == ea.FLIP_SALE_UNREAD and p4["flip_cost_cents"] is None
    assert not p4["arm_breach"] and p4["breach_unread"] and p5["arm"] == ea.ARM_EARLY
    assert not p5["arm_breach"] and p5["breach_unread"]
    assert not ok["arm_breach"] and not ok["breach_unread"]
    t = ea.arm_table([p4, p5, ok])
    assert t["breaches"] == 0 and t["breaches_not_read"] == 2
    assert t["flip_games_not_exited"]["sale not read"] == 1


def test_latest_is_refused_directly_and_through_a_dated_symlink(tmp_path, capsys):
    host = tmp_path / "host"
    write_page(host / "latest", RUN, [row()])
    with pytest.raises(ea.LatestRefused):
        ea.closing_pages(host / "latest")
    ex = tmp_path / "exports"
    write_page(ex, RUN, [row()])
    os.symlink(host / "latest", ex / "2026-11-08", target_is_directory=True)
    with pytest.raises(ea.LatestRefused):
        ea.closing_pages(ex)
    p = tmp_path / "L.json"
    p.write_text(json.dumps({"calls": [], "fills": []}))
    assert script.main(["--ledger", str(p), "--exports", str(host / "latest")]) == script.REFUSED
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == script.REFUSED
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2 and all(ln.startswith("REFUSED: ") and "latest/" in ln for ln in out)


def test_the_breach_listing_is_console_only_and_held_from_posting(tmp_path, capsys):
    p, ex = _receipt_world(tmp_path)
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == 0
    lines = capsys.readouterr().out.splitlines()
    i = next(k for k, ln in enumerate(lines) if "arm breach: match 9001" in ln)
    assert "CONSOLE ONLY, NOT FOR POSTING" in lines[i - 1] and lines[i - 1].startswith("BREACHES LISTED")
    assert "9001" not in lines[-1] and "Testford" not in lines[-1]                       # never in the JSON
    for ln in lines[:i - 1]:
        assert "Testford" not in ln and "Mockley" not in ln                               # the table names no game


def test_the_table_prints_the_arms_lots_beside_the_games(tmp_path):
    """285 item 2(2): the thirty counts games; the lots are a count printed beside them, nothing more."""
    p, ex = _receipt_world(tmp_path)
    t = ea.arm_table(ea.attribute(json.loads(p.read_text()), ex))
    assert (t["toward_thirty"], t["arm_games"], t["lots"]) == (2, 2, 3)
    assert any("2 of 30 (lots 3)" in ln for ln in ea.table_lines(t))


# ---- Codex on #864, round 1 ---------------------------------------------------------------------------------------

def test_pages_of_one_run_that_differ_only_in_units_are_refused(tmp_path):
    """The units feed closing_call and early_games_by_units: two copies of the latest run disagreeing there are
    refused, never one picked by the files' order."""
    L, ex = world(tmp_path, [(RUN, [row(units=0.5)]), (RUN, [row(units=1.0)], KO_DT, "2026-11-08")], [entry()],
                  [call()])
    a = ea.attribute(L, ex)[0]
    assert a["arm"] is None and a["arm_note"] == ea.DISAGREE


def test_pages_that_differ_only_in_the_machine_local_match_id_agree(tmp_path):
    """The join is the event ticker (match ids are machine-local): an untimed copy under another id that otherwise
    agrees does not refuse the event; the latest timed page is the one kept."""
    L, ex = world(tmp_path, [(RUN, [row(mid=9001)]), (None, [row(mid=4242)], KO_DT, "2026-11-08")], [entry()],
                  [call()])
    a = ea.attribute(L, ex)[0]
    assert a["arm"] == ea.ARM_EARLY and a["closing_call"]["match_id"] == 9001


def test_an_exited_flip_with_an_unread_price_is_counted_exited_not_priced(tmp_path):
    f = {**entry(closed="2026-11-08T13:10:00Z", exit_=EXIT_, close_fee=0.0101), "entry": None}   # entry unread
    a, _, _ = one(tmp_path, row(call="PASS"), f)
    assert a["arm"] == ea.ARM_FLIP and a["flip_exit"] == ea.FLIP_EXITED and a["flip_cost_cents"] is None
    t = ea.arm_table([a])
    assert (t["flip_games"], t["flip_games_exited"], t["flip_games_priced"]) == (1, 1, 0)
    assert t["mean_flip_cost_cents_per_game"] is None
    assert "exited before kickoff 1 (priced 0)" in "\n".join(ea.table_lines(t))


@pytest.mark.parametrize("key,bad", [("fills", {}), ("fills", "x"), ("fills", 0), ("system_picks", {}),
                                     ("system_picks", "x")])
def test_a_non_array_fills_or_system_picks_is_refused_never_read_as_empty(tmp_path, capsys, key, bad):
    p = tmp_path / "L.json"
    p.write_text(json.dumps({"calls": [], "fills": [], key: bad}))
    assert script.main(["--ledger", str(p), "--exports", str(tmp_path)]) == script.REFUSED
    assert f"{key} is not an array of objects" in capsys.readouterr().out


def test_absent_or_null_fills_is_no_fills(tmp_path):
    for doc in ({"calls": []}, {"calls": [], "fills": None, "system_picks": None}):
        p = tmp_path / "L.json"
        p.write_text(json.dumps(doc))
        assert script.read_ledger(p) == {"calls": [], "fills": [], "system_picks": []}


# ---- addendum 285 (ARCHITECT 2026-11-07 12:00 ET): each test failed first on bed68361 ------------------------------

def _ladder_fill():
    """NO on Mockley in a three-way market: composite (Testford or the draw), the ladder's X2 contract."""
    return entry(ticker=MCK, side="no")


@pytest.mark.parametrize("close", ["PASS", "PLAY", "LADDER"])
def test_285_1a_a_composite_no_ladder_fill_is_never_an_arm_fill(tmp_path, close):
    """Codex 4502731775 / 285 item 1(a): the matcher books a composite NO system_matched to a LADDER call; that is
    never an arm fill, on a PASS page (bed68361 counted it an arm flip), a PLAY page or a LADDER page."""
    page = {"PASS": row(call="PASS"), "PLAY": row(), "LADDER": row(call="LADDER", order=MCK, side="NO")}[close]
    lad = call(cid="lad1", call_type="ladder")
    a, L, _ = one(tmp_path, page, _ladder_fill(), calls=(lad,))
    base = lf.classify_fills(L)[0]
    assert base["book"] == "system_matched" and base["call_id"] == "lad1" and base["composite"]
    assert a["arm"] is None and a["arm_note"] == ea.NOT_STRAIGHT_PLAY
    assert (a["book"], a["call_id"]) == ("system_matched", "lad1")            # its ladder booking kept, untouched
    t = ea.arm_table([a])
    assert (t["toward_thirty"], t["flip_games"], t["not_the_arms"]["not a straight PLAY call"]) == (0, 0, 1)


def test_285_2_6_no_prematch_page_before_the_fill_is_unestablished(tmp_path):
    """285 items 2(4)/2(6): no prematch page before the fill (none at all, or only one exported after it) keeps the
    UNESTABLISHED label, never counted; bed68361 counted both early."""
    none_, _, _ = one(tmp_path / "a", row(), entry(), prematch=[])
    later, _, _ = one(tmp_path / "b", row(), entry(), prematch=[(datetime(2026, 11, 7, 21, 0), [row()])])
    for a in (none_, later):
        assert a["arm"] is None and a["arm_note"] == ea.NO_PREMATCH and not a["early"]
    t = ea.arm_table([none_, later])
    assert t["unestablished"]["no prematch page before the fill"] == 2 and t["toward_thirty"] == 0


@pytest.mark.parametrize("pre", ["PASS", "HOME"])
def test_285_2_6_a_prematch_pass_or_other_side_is_not_the_arms(tmp_path, pre):
    page = row(call="PASS") if pre == "PASS" else row(pick="HOME", order=MCK)
    a, _, _ = one(tmp_path, row(), entry(), prematch=[(PRE_AT, [page])])
    assert a["arm"] is None and a["arm_note"] == ea.PREMATCH_NOT_PLAY
    assert ea.arm_table([a])["not_the_arms"]["prematch page not PLAY on its side"] == 1


def test_285_2_6_the_latest_prematch_page_before_the_fill_decides(tmp_path):
    t1, t2, t3 = datetime(2026, 11, 7, 10, 0), datetime(2026, 11, 7, 12, 0), datetime(2026, 11, 7, 22, 0)
    passed, _, _ = one(tmp_path / "a", row(), entry(), prematch=[(t1, [row()]), (t2, [row(call="PASS")])])
    played, _, _ = one(tmp_path / "b", row(), entry(), prematch=[(t1, [row(call="PASS")]), (t2, [row()]),
                                                                 (t3, [row(call="PASS")])])   # t3 after the fill
    assert passed["arm"] is None and passed["arm_note"] == ea.PREMATCH_NOT_PLAY
    assert played["arm"] == ea.ARM_EARLY and played["prematch_page"]["run"] == t2


def test_285_2_6_both_gates_not_either(tmp_path):
    """285 item 2(6): "the prematch page itself is the test of 2(a) [...] AND the matcher's straight PLAY call (item
    1(a)); both, not either"."""
    call_only, _, _ = one(tmp_path / "a", row(), entry(), prematch=[(PRE_AT, [row(call="PASS")])])
    page_only, _, _ = one(tmp_path / "b", row(), entry(), calls=())
    both, _, _ = one(tmp_path / "c", row(), entry())
    assert call_only["arm"] is None and call_only["arm_note"] == ea.PREMATCH_NOT_PLAY
    assert page_only["arm"] is None and page_only["arm_note"] == ea.PRE_CLOSE_OFF_ARM
    assert both["arm"] == ea.ARM_EARLY


def test_285_2_4_a_same_day_side_change_with_a_prematch_page_is_an_arm_flip(tmp_path):
    """285 item 2(4), the reading: the Cockpit re-logged the call in place on the closing side (the matcher's straight
    PLAY call for the game now holds the close's pick); the prematch page before the fill PLAYs the fill's side, so
    the prematch page gives the arm's side and the fill is an arm flip, booked to the arm."""
    f = entry(opened="2026-11-08T06:30:00-05:00", closed="2026-11-08T13:10:00Z", exit_=EXIT_, close_fee=0.0101)
    L, ex = world(tmp_path, [(RUN, [row(pick="HOME", order=MCK)])], [f], [call(pick="HOME", log_date="2026-11-08")])
    assert lf.classify_fills(L)[0]["category"] == ea.MATCHER_SIDE_DISAGREES
    a = ea.attribute(L, ex)[0]
    assert a["arm"] == ea.ARM_FLIP and a["relogged"] is True and a["book"] == ea.ARM_BOOK and a["call_id"] is None
    assert a["prematch_page"]["pick"] == "AWAY" and a["closing_call"]["pick"] == "HOME"
    assert a["flip_exit"] == ea.FLIP_EXITED and a["flip_cost_cents"] is not None
    assert ea.arm_table([a])["flip_games"] == 1


def test_285_2_6_the_prematch_globs_are_the_families_slate_exports():
    assert set(ea.PREMATCH_GLOBS) == {f["export_glob"] for f in CL.FAMILIES.values()}
    assert set(ea.PREMATCH_GLOBS).isdisjoint({"closing_*.json"})


def test_285_2_6_the_prematch_reader(tmp_path):
    """Dated folders read; a file of the glob that is no Desk page counted, never read as one; latest/ refused (the
    same refusal); copies of one export time that disagree refused (NOT CLASSIFIED); an untimed page never placed."""
    ex = tmp_path / "exports"
    write_prematch(ex / "2026-11-07", PRE_AT, [row()])
    (ex / "soccer_PL_odd.json").write_text(json.dumps({"predictions": [row()]}))         # no desk_meta: no page
    (ex / "soccer_PL_bad.json").write_text("{")
    pre = ea.prematch_pages(ex)
    assert (pre["files"], pre["not_desk"], pre["unreadable"], pre["dated"]) == (1, 1, ["soccer_PL_bad.json"], 1)
    assert [p["run"] for p in pre["by_event"][EVENT]] == [PRE_AT]
    host = tmp_path / "host"
    write_prematch(host / "latest", PRE_AT, [row()])
    with pytest.raises(ea.LatestRefused):
        ea.prematch_pages(host / "latest")
    os.symlink(host / "latest", ex / "2026-11-08", target_is_directory=True)
    with pytest.raises(ea.LatestRefused):
        ea.prematch_pages(ex)
    two, _, _ = one(tmp_path / "d", row(), entry(), prematch=[(PRE_AT, [row()]), (PRE_AT, [row(units=1.0)],
                                                                                    "2026-11-07")])
    untimed, _, _ = one(tmp_path / "u", row(), entry(), prematch=[(None, [row()])])
    assert two["arm_note"] == ea.PREMATCH_DISAGREE and untimed["arm_note"] == ea.PREMATCH_UNTIMED
    nc = ea.arm_table([two, untimed])["not_classified"]
    assert (nc["prematch pages disagree"], nc["prematch page time unknown"]) == (1, 1)


def test_285_1b_not_classified_is_counted_by_cause(tmp_path):
    """Codex 4502731779 / 285 item 1(b): NO_PAGE, RUN_UNKNOWN and TIME_UNREAD rows are counted by cause on a NOT
    CLASSIFIED line and in the JSON, never dropped (bed68361's table read all zeros)."""
    L, ex = world(tmp_path / "a", [], [entry()], [call()])
    no_page = ea.attribute(L, ex)[0]
    L, ex = world(tmp_path / "b", [(None, [row()])], [entry()], [call()])
    run_unknown = ea.attribute(L, ex)[0]
    time_unread, _, _ = one(tmp_path / "c", row(), entry(opened=None))
    t = ea.arm_table([no_page, run_unknown, time_unread])
    assert {k: v for k, v in t["not_classified"].items() if v} == {"no closing page": 1, "closing run time unknown": 1,
                                                                   "fill open time not read": 1}
    ln = next(x for x in ea.table_lines(t) if x.startswith("NOT CLASSIFIED"))
    assert ": 3 — no closing page 1 · closing run time unknown 1 · fill open time not read 1" in ln


@pytest.mark.parametrize("name", ["PRE_CLOSE_OFF_ARM", "NOT_STRAIGHT_PLAY", "AFTER_RUN", "TIME_UNREAD",
                                  "SIDE_RELOGGED", "NO_PREMATCH", "PREMATCH_UNTIMED", "PREMATCH_DISAGREE",
                                  "SIDE_UNREAD", "PREMATCH_NOT_PLAY", "NO_PAGE", "DISAGREE", "RUN_UNKNOWN",
                                  "NOT_RULED_CALL", None])
def test_285_1b_every_arm_note_is_counted_on_a_line(name):
    """Every arm_note attribute() sets is counted on one table line; an unknown one is NOT CLASSIFIED "other"."""
    note = "a note no line names" if name is None else getattr(ea, name)
    t = ea.arm_table([{"kind": "sport", "ticker": TST, "arm": None, "arm_note": note}])
    counted = (sum(t["not_the_arms"].values()) + sum(t["unestablished"].values()) + sum(t["not_classified"].values())
               + t["ordinary"] + t["not_ruled"])
    assert counted == 1
    if note == "a note no line names":
        assert t["not_classified"][ea.OTHER_NOTE] == 1


def lot(i, clv=1.0, cost=None, arm=ea.ARM_EARLY, breach=False, unread=False, qty=10, hours=None):
    """A synthetic attributed lot of game i (the fields arm_table reads), first fill at 2026-11-01 + i hours."""
    ev = f"KXEPLGAME-26NOV08G{i:02d}H{i:02d}"
    opened = (datetime(2026, 11, 1) + timedelta(hours=i if hours is None else hours)).isoformat() + "Z"
    return {"kind": "sport", "ticker": f"{ev}-G{i:02d}", "arm": arm, "arm_note": None, "opened": opened, "qty": qty,
            "entry": 0.5, "exit": None, "prematch_page": {"units": 0.5}, "closing_call": {"units": 0.5},
            "early_clv_cents": clv if arm == ea.ARM_EARLY else None,
            "flip_exit": ea.FLIP_EXITED if arm == ea.ARM_FLIP else None, "flip_cost_cents": cost,
            "arm_breach": breach, "breach_why": ea.BREACH_OPENED if breach else None, "breach_unread": unread}


def _read(t):
    return next(x for x in ea.table_lines(t) if x.startswith("THE READ"))


def test_285_2_3_the_read_at_thirty_games():
    """283 item 3 / 285 items 1(b), 2(2), 2(3): below thirty no verdict; at thirty CONTINUE only on a positive mean
    net of flip costs over the first thirty games by their first fill (a tie rejects); a breach in the thirty gives
    no verdict; any row not classified refuses the read (its count printed, never the mean)."""
    t = ea.arm_table([lot(i) for i in range(29)])
    assert t["read"] == ea.READ_BELOW and "29 of 30 — no read before thirty, no verdict" in _read(t)
    t = ea.arm_table([lot(i) for i in range(30)])
    assert (t["read"], t["read_net_cents_per_game"]) == (ea.READ_CONTINUE, 1.0)
    tie = [lot(i) for i in range(29)] + [lot(29, arm=ea.ARM_FLIP, cost=29.0)]          # (29 - 29) / 30 = 0
    t = ea.arm_table(tie)
    assert (t["read"], t["read_net_cents_per_game"]) == (ea.READ_STOP, 0.0)
    t = ea.arm_table([lot(i, clv=-0.5) for i in range(30)])
    assert t["read"] == ea.READ_STOP
    rows = [lot(i, breach=(i == 4)) for i in range(30)]
    t = ea.arm_table(rows)
    assert (t["read"], t["read_blocking"], t["read_net_cents_per_game"]) == (ea.READ_BREACH, 1, None)
    assert "breach in the thirty: 1 — the continuation is the architect's ruling on the record" in _read(t)
    assert "¢" not in _read(t)
    late = [lot(i) for i in range(30)] + [lot(30, breach=True, clv=-99.0)]           # game 31: outside the thirty
    t = ea.arm_table(list(reversed(late)))
    assert (t["read"], t["toward_thirty"], t["read_net_cents_per_game"]) == (ea.READ_CONTINUE, 31, 1.0)
    t = ea.arm_table([lot(i) for i in range(30)] + [{"kind": "sport", "ticker": TST, "arm": None,
                                                     "arm_note": ea.NO_PAGE}])
    assert (t["read"], t["read_blocking"], t["read_net_cents_per_game"]) == (ea.READ_REFUSED, 1, None)
    assert "REFUSED: 1 rows NOT CLASSIFIED" in _read(t) and "¢" not in _read(t)
    t = ea.arm_table([lot(i, clv=None if i == 7 else 1.0) for i in range(30)])
    assert (t["read"], t["read_blocking"]) == (ea.READ_UNPRICED, 1)


def test_285_2_3_a_flip_held_to_settlement_is_a_breach_booked_in_units(tmp_path):
    won, _, _ = one(tmp_path / "w", row(call="PASS"), entry(closed="2026-11-08T16:00:00Z", exit_=1.0, close_fee=0.0))
    lost, _, _ = one(tmp_path / "l", row(call="PASS"), entry(closed="2026-11-08T16:00:00Z", exit_=0.0, close_fee=0.0))
    for a in (won, lost):
        assert a["arm"] == ea.ARM_FLIP and a["flip_exit"] == ea.FLIP_SETTLED
        assert a["arm_breach"] and a["breach_why"] == ea.BREACH_HELD == "flip held to settlement"
        assert a["flip_cost_cents"] is None                          # outside the flip cost and the CLV mean
    t = ea.arm_table([won])
    assert t["flip_held_to_settlement_games"] == 1 and t["breaches_by_cause"][ea.BREACH_HELD] == 1
    assert t["flip_held_settlement_units"] == pytest.approx(0.5 * (1.0 - ENTRY) / ENTRY, abs=1e-4)
    assert t["mean_flip_cost_cents_per_game"] is None and t["breach_games"] == 1
    assert ea.arm_table([lost])["flip_held_settlement_units"] == pytest.approx(-0.5)
    ln = next(x for x in ea.table_lines(t) if x.startswith("FLIP HELD TO SETTLEMENT"))
    assert "games 1" in ln and "+0.52u" in ln


def test_285_2_1_early_clv_is_the_closing_ask_less_the_fill_fees_out_of_both(tmp_path):
    a, _, _ = one(tmp_path, row(ask=0.50, cost=0.5175), entry())
    assert a["closing_ask"] == 0.50 and a["early_clv_cents"] == pytest.approx((0.50 - ENTRY) * 100)
    p = ea._page(RUN, KO_DT, row())
    assert (ea.page_ask(p, TST, "yes"), ea.page_ask(p, MCK, "no"), ea.page_ask(p, "KXEPLGAME-X-Y", "yes")) == \
        (ASK, 0.71, None)                                           # YES the ask; NO 1 − the yes bid; none carried


def test_285_2_1_flip_cost_carries_both_legs_taker_fees_per_contract(tmp_path):
    f = entry(qty=100, entry_=0.50, closed="2026-11-08T13:10:00Z", exit_=0.45, close_fee=0.03, open_fee=0.02)
    a, _, _ = one(tmp_path / "a", row(call="PASS"), f)
    assert a["flip_cost_cents"] == pytest.approx(5.0 + 0.05 / 100 * 100)
    g = {**f, "open_fee": None}
    b, _, _ = one(tmp_path / "b", row(call="PASS"), g)
    assert b["flip_exit"] == ea.FLIP_EXITED and b["flip_cost_cents"] is None          # a fee unread: no cost


def test_285_2_2_the_unit_of_the_thirty_is_games_contract_weighted(tmp_path):
    lots = [entry(fid="syn-a", qty=100, entry_=0.48), entry(fid="syn-b", qty=300, entry_=0.52)]
    L, ex = world(tmp_path, [(RUN, [row(ask=0.50)])], lots, [call()])
    t = ea.arm_table(ea.attribute(L, ex))
    assert (t["toward_thirty"], t["early_games"], t["lots"], t["early_games_priced"]) == (1, 1, 2, 1)
    assert t["mean_early_clv_cents_per_game"] == pytest.approx((100 * 2.0 + 300 * -2.0) / 400)    # -1.0: one CLV


def test_285_2_2_the_receipt_json_keys(tmp_path, capsys):
    p, ex = _receipt_world(tmp_path)
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == 0
    last = json.loads(capsys.readouterr().out.strip().splitlines()[-1].split(" ", 1)[1])
    assert sorted(last) == sorted([
        "arm_games", "early_games", "flip_games", "lots", "early_games_priced", "early_lots_ask_unread",
        "mean_early_clv_cents_per_game", "early_games_by_units", "flip_games_exited", "flip_games_priced",
        "mean_flip_cost_cents_per_game", "total_flip_cost_cents", "flip_games_not_exited",
        "flip_held_to_settlement_games", "flip_held_settlement_units", "flip_held_unpriced_games", "breaches",
        "breaches_by_cause", "breach_games", "breaches_not_read", "interest_carried", "interest_rows", "ordinary",
        "not_the_arms", "unestablished", "not_ruled", "not_classified", "toward_thirty", "read_at", "read",
        "read_net_cents_per_game", "read_blocking", "closing_files", "unreadable", "prematch_files",
        "prematch_unreadable", "prematch_not_desk"])


def test_285_2_5_a_held_flip_is_listed_console_only_its_count_in_the_json(tmp_path, capsys):
    p, ex = _receipt_world(tmp_path)
    L = json.loads(p.read_text())
    q = next(f for f in L["fills"] if f["id"] == "syn-f1")
    q.update(closed="2026-11-09T16:00:00Z", exit=1.0, close_fee=0.0)                   # held to settlement
    p.write_text(json.dumps(L))
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == 0
    lines = capsys.readouterr().out.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith("BREACHES LISTED"))
    assert "CONSOLE ONLY, NOT FOR POSTING" in lines[i]
    assert any("match 9002 Quillby @ Rexham" in ln and ln.endswith("flip held to settlement") for ln in lines[i:])
    last = json.loads(lines[-1].split(" ", 1)[1])
    assert last["breaches_by_cause"]["flip held to settlement"] == 1
    assert "9002" not in lines[-1] and "Quillby" not in lines[-1]


def test_285_2_7_interest_not_carried_is_never_zero(tmp_path, capsys):
    p, ex = _receipt_world(tmp_path, with_type=False)
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == 0
    out = capsys.readouterr().out
    assert "interest rows: not carried by this export" in out
    last = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert last["interest_rows"] is None and last["interest_carried"] is False
    p2, ex2 = _receipt_world(tmp_path / "t")
    t = ea.arm_table(ea.attribute(json.loads(p2.read_text()), ex2))
    assert (t["interest_carried"], t["interest_rows"]) == (True, 1)
    assert any("interest rows: 1" in ln for ln in ea.table_lines(t))


def test_285_1c_the_boundary_is_stated_the_closing_pages_export_time():
    """285 item 1(c), closed by ruling, no change: the docstring states the boundary and why."""
    doc = " ".join(ea.__doc__.split())
    assert "the closing numbers exist at the export" in doc
    assert "a fill after the export is a fill at the closing call's own numbers" in doc
