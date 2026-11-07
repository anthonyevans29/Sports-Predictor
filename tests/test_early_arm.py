"""THE EARLY-ENTRY ARM, ATTRIBUTED (#862; addendum 283 item 4): src/walters/early_arm.py and
scripts/early_arm_receipt.py, read-only.

The world is synthetic (no real CSV row, no account id, no fill figure from any real file): one PL game, Chelsea at
Sunderland, its closing pages written as a closing run writes them (tests/test_void_redated.write_closing), and a
Cockpit ledger export whose fills are the entries importKalshiCSV stores (ledger_fills.parse_ticker / side_fields
spread in), every figure invented here. Pins: each attribution case (early on the PLAY side; arm flip on a PASS and on
a side change, paired with its pre-kickoff exit; a pre-closing fill with no logged PLAY is not the arm's; an ordinary
fill after the closing run; the latest run decides; a LADDER close is not ruled; pages that disagree are refused), the
CLV formula's sign, a breach (an entry after kickoff, a sale after kickoff; a settlement is none), an interest row
(its own kind, never attributed), the matcher untouched and a flip out of executed_positions, the receipt's table in
cents and units only, and the bulletin's one word.
"""
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

from src.walters import early_arm as ea
from src.walters import ledger_fills as lf
from tests.test_void_redated import write_closing

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("early_arm_receipt", ROOT / "scripts" / "early_arm_receipt.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

EVENT = "KXEPLGAME-26NOV08CHESUN"
CHE, SUN, TIE = f"{EVENT}-CHE", f"{EVENT}-SUN", f"{EVENT}-TIE"
KO = "2026-11-08T14:00:00"                        # naive UTC, the row's utc_date
RUN = datetime(2026, 11, 8, 12, 2)                # the closing run's start, before kickoff
PRE = "2026-11-07T15:30:00-05:00"                 # opened the day before (an offset, as Kalshi writes it)
QTY, ENTRY, EXIT_, FEE = 4711, 0.4913, 0.4512, 0.0123    # invented figures: none may reach the receipt's output
FILL_ID = "syn-ACCT-0000␟trade␟4711"            # a synthetic id (the real one carries the account id)


def row(call="PLAY", pick="AWAY", cost=0.51, order=CHE, side="YES", mid=9001, units=0.5):
    desk = {"call": call, "pick": pick, "units": units if call != "PASS" else 0,
            "exec": {"cost": cost, "basis": "ask", "contracts": 777},
            "order": {"ticker": order, "side": side, "limit": cost, "contracts": 777} if call in ("PLAY", "LADDER")
            else None}
    return {"match_id": mid, "home_team": "Sunderland", "away_team": "Chelsea", "utc_date": KO, "competition": "PL",
            "desk": desk, "kalshi_legs": {"HOME": {"ticker": SUN}, "AWAY": {"ticker": CHE}, "DRAW": {"ticker": TIE}}}


def entry(ticker=CHE, side="yes", opened=PRE, closed="2026-11-08T16:00:00Z", exit_=1.0, close_fee=0.0, entry_=ENTRY,
          fid=FILL_ID, **extra):
    """The entry the Cockpit's importKalshiCSV stores (synthetic figures)."""
    title = {"CHE": "Chelsea wins — Sunderland", "SUN": "Sunderland wins — Chelsea", "TIE": "Tie — Chelsea v Sunderland"}
    fx = {"id": fid, "ticker": ticker, "side": side, "qty": QTY, "entry": entry_, "exit": exit_,
          "staked": round(QTY * entry_, 4), "fees": round(FEE + close_fee, 4), "open_fee": FEE, "close_fee": close_fee,
          "pnl_pre": 0.0, "pnl_net": 0.0, "opened": opened, "closed": closed,
          "title": title.get(ticker.rsplit("-", 1)[-1], ""), **extra}
    p = lf.parse_ticker(fx["ticker"])
    fx.update(p)
    if p["kind"] == "sport":
        fx.update(lf.side_fields(p, fx["title"], fx["side"]))
    return fx


def call(pick="AWAY", cid="c1", graded=False):
    c = {"id": cid, "sport": "PL", "home": "Sunderland", "away": "Chelsea", "kickoff": KO + "Z", "log_date": "2026-11-07",
         "call_type": "straight", "pick": pick, "units": 0.5, "engine": "model_edge", "tier": "A"}
    if graded:
        c.update(status="graded", close_ref={"fair": {"HOME": 0.3, "AWAY": 0.5, "DRAW": 0.2}})
    return c


def world(tmp_path, rows_by_run, fills, calls=()):
    ex = tmp_path / "exports"
    for start, rows in rows_by_run:
        write_closing(ex, start, rows, fam="SOCCER")
    return {"calls": list(calls), "fills": list(fills)}, ex


def one(tmp_path, page_row, f, calls=(call(),), extra_runs=()):
    L, ex = world(tmp_path, [*extra_runs, (RUN, [page_row])], [f], calls)
    return ea.attribute(L, ex)[0], L, ex


# ---- the attribution ----------------------------------------------------------------------------------------------

def test_early_is_attributed_to_the_closing_call_with_its_price_and_clv(tmp_path):
    a, L, _ = one(tmp_path, row(), entry())
    assert a["arm"] == ea.ARM_EARLY and a["early"] is True
    assert a["early_price"] == ENTRY and a["closing_cost"] == 0.51
    assert a["early_clv_cents"] == pytest.approx((0.51 - ENTRY) * 100)
    assert a["closing_call"] == {"match_id": 9001, "run": RUN, "pick": "AWAY", "units": 0.5}
    base = lf.classify_fills(L)[0]                     # the matcher untouched: the closing call's own booking kept
    assert (a["book"], a["call_id"]) == (base["book"], base["call_id"]) == ("system_matched", "c1")
    assert not a["arm_breach"]


def test_the_clv_sign_positive_when_early_was_cheaper(tmp_path):
    cheap, _, _ = one(tmp_path / "a", row(cost=0.55), entry(entry_=0.50))
    dear, _, _ = one(tmp_path / "b", row(cost=0.55), entry(entry_=0.58))
    assert cheap["early_clv_cents"] == pytest.approx(5.0) and cheap["early_clv_cents"] > 0
    assert dear["early_clv_cents"] == pytest.approx(-3.0) and dear["early_clv_cents"] < 0


def test_early_on_the_pick_by_another_contract_has_no_closing_cost(tmp_path):
    """The page's order names the YES contract; a fill on the same role through another contract (here the page's
    order is written on another ticker) is early, but the page printed no cost for it: null, never derived."""
    a, _, _ = one(tmp_path, row(order="KXEPLGAME-26NOV08CHESUN-XXX"), entry())
    assert a["arm"] == ea.ARM_EARLY and a["closing_cost"] is None and a["early_clv_cents"] is None


def test_flip_on_a_pass_close_paired_with_its_pre_kickoff_exit(tmp_path):
    f = entry(closed="2026-11-08T13:10:00Z", exit_=EXIT_, close_fee=0.0101)        # sold before kickoff
    a, _, _ = one(tmp_path, row(call="PASS"), f)
    assert a["arm"] == ea.ARM_FLIP and a["early"] is False
    assert a["book"] == ea.ARM_BOOK and a["call_id"] is None and a["ledger_call_id"] == "c1"
    assert a["closing_cost"] is None and a["early_clv_cents"] is None
    assert a["flip_exit_price"] == EXIT_ and a["flip_exit"] == "exited before kickoff"
    assert a["flip_cost_cents"] == pytest.approx((ENTRY - EXIT_) * 100) and a["flip_cost_cents"] > 0
    assert not a["arm_breach"]


def test_flip_when_the_close_picks_another_side(tmp_path):
    a, _, _ = one(tmp_path, row(pick="HOME", order=SUN), entry())
    assert a["arm"] == ea.ARM_FLIP and a["closing_call"]["pick"] == "HOME" and a["closing_cost"] is None


def test_flip_held_to_settlement_has_no_exit_and_no_cost(tmp_path):
    a, _, _ = one(tmp_path, row(call="PASS"), entry(close_fee=0.0, exit_=1.0))
    assert a["arm"] == ea.ARM_FLIP and a["flip_exit_price"] is None and a["flip_cost_cents"] is None
    assert a["flip_exit"].startswith("no sale")
    assert not a["arm_breach"]                    # a settlement is no fill after kickoff


def test_a_pre_closing_fill_with_no_logged_play_is_not_the_arms(tmp_path):
    a, L, _ = one(tmp_path, row(call="PASS"), entry(), calls=())
    assert a["arm"] is None and a["arm_note"] == ea.PRE_CLOSE_OFF_ARM
    assert a["book"] == lf.classify_fills(L)[0]["book"] == "off_book_sports"     # its booking unchanged


def test_a_fill_after_the_closing_run_is_ordinary(tmp_path):
    a, _, _ = one(tmp_path, row(), entry(opened="2026-11-08T12:30:00Z"))
    assert a["arm"] is None and a["arm_note"] == ea.AFTER_RUN and a["book"] == "system_matched"


def test_the_latest_closing_run_decides(tmp_path):
    a, _, _ = one(tmp_path, row(call="PASS"), entry(), extra_runs=[(datetime(2026, 11, 7, 12, 2), [row()])])
    assert a["arm"] == ea.ARM_FLIP


def test_a_ladder_close_is_not_ruled(tmp_path):
    a, _, _ = one(tmp_path, row(call="LADDER", order=SUN, side="NO"), entry())
    assert a["arm"] is None and a["arm_note"] == ea.NOT_RULED_CALL


def test_pages_of_one_run_that_disagree_are_refused(tmp_path):
    L, ex = world(tmp_path, [(RUN, [row()])], [entry()], [call()])
    write_closing(ex / "2026-11-08", RUN, [row(call="PASS")], fam="SOCCER")       # the same run, a dated copy
    a = ea.attribute(L, ex)[0]
    assert a["arm"] is None and a["arm_note"] == ea.DISAGREE


def test_no_page_and_unread_time(tmp_path):
    a, _, _ = one(tmp_path / "a", row(), entry(ticker="KXEPLGAME-26NOV08ARSTOT-ARS"))
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
    assert not b["arm_breach"]


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
    assert ea.arm_table(ea.attribute(L, ex))["interest_rows"] == 2


def test_todays_export_carries_no_type_so_no_row_is_interest(tmp_path):
    a, _, _ = one(tmp_path, row(), entry())
    assert "type" not in entry() and a["kind"] == "sport"


# ---- the flip leaves the call's executed position -----------------------------------------------------------------

def test_a_flip_never_enters_executed_positions(tmp_path):
    L, ex = world(tmp_path, [(RUN, [row(call="PASS")])], [entry()], [call(graded=True)])
    assert [p["c"]["id"] for p in lf.executed_positions(L)["pos"]] == ["c1"]          # today's booking: counted
    assert lf.executed_positions(L, fills=ea.attribute(L, ex))["pos"] == []           # the arm's: booked to the arm


# ---- the table and the receipt ------------------------------------------------------------------------------------

def _receipt_world(tmp_path):
    fills = [entry(fid="syn-e1"),                                                    # early, +1.87c
             entry(fid="syn-e2", entry_=0.5300),                                     # early, -2.00c
             entry(ticker="KXEPLGAME-26NOV09ARSTOT-ARS", fid="syn-f1", closed="2026-11-09T13:00:00Z",
                   exit_=EXIT_, close_fee=0.0101, entry_=0.4800, opened="2026-11-08T10:00:00Z"),   # flip, exited
             entry(fid="syn-b1", opened="2026-11-08T14:30:00Z"),                     # breach (an add after kickoff)
             entry(fid="syn-i1", type="interest", ticker="")]
    ars = {**row(call="PASS", mid=9002), "home_team": "Tottenham", "away_team": "Arsenal",
           "utc_date": "2026-11-09T14:00:00",
           "kalshi_legs": {"HOME": {"ticker": "KXEPLGAME-26NOV09ARSTOT-TOT"},
                           "AWAY": {"ticker": "KXEPLGAME-26NOV09ARSTOT-ARS"}}}
    ars_call = {**call(cid="c2"), "home": "Tottenham", "away": "Arsenal", "kickoff": "2026-11-09T14:00:00Z"}
    L, ex = world(tmp_path, [(RUN, [row()]), (datetime(2026, 11, 9, 12, 2), [ars])], fills, [call(), ars_call])
    p = tmp_path / "bd_ledger_v1_2026-11-09.json"
    p.write_text(json.dumps({**L, "meta": {}}))
    return p, ex


def test_the_arm_table(tmp_path):
    p, ex = _receipt_world(tmp_path)
    t = ea.arm_table(ea.attribute(json.loads(p.read_text()), ex))
    assert (t["early"], t["early_priced"], t["flips"], t["flips_exited_before_kickoff"], t["breaches"],
            t["interest_rows"], t["toward_thirty"], t["read_at"]) == (2, 2, 1, 1, 1, 1, 3, 30)
    assert t["mean_early_clv_cents"] == pytest.approx(((0.51 - ENTRY) + (0.51 - 0.53)) * 50)
    assert t["mean_flip_cost_cents"] == pytest.approx((0.48 - EXIT_) * 100)
    assert t["early_by_units"] == {"0.5u": 2}


def test_the_receipt_prints_cents_and_units_only(tmp_path, capsys):
    p, ex = _receipt_world(tmp_path)
    assert script.main(["--ledger", str(p), "--exports", str(ex)]) == 0
    out = capsys.readouterr().out.replace(str(ex.resolve()), "<exports>")    # the tmp path is not the receipt's
    assert "EARLY (item 4" in out and "ARM FLIP" in out and "ARM BREACH" in out and "INTEREST" in out
    assert "¢" in out and "0.5u 2" in out and "3 of 30" in out
    assert "arm breach: match 9001 Chelsea @ Sunderland (kickoff 2026-11-08T14:00:00Z): opened at or after kickoff" in out
    for figure in ("$", "4711", "0.4913", "0.4512", "0.0123", "0.0101", "0.53", "0.48", "777", "syn-", "ACCT",
                   "staked", "pnl", "qty", "contracts"):
        assert figure not in out, figure
    last = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert last["toward_thirty"] == 3 and last["breaches"] == 1


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
    line = "PLAY Chelsea 0.5u"
    assert ea.arm_call_line(line, True) == "PLAY Chelsea 0.5u early"
    assert ea.arm_call_line(line, False) == line
    assert ea.arm_call_line(line, True)[len(line):].split() == [ea.EARLY_WORD] == ["early"]
    a, _, _ = one(tmp_path, row(), entry())
    assert ea.early_calls([a]) == {(9001, RUN)}
    f, _, _ = one(tmp_path / "f", row(call="PASS"), entry())
    assert ea.early_calls([f]) == set()                     # a flip marks no call line
