"""THE EARLY-ENTRY ARM, ATTRIBUTED (#862; addendum 283 item 4): src/walters/early_arm.py and
scripts/early_arm_receipt.py, read-only.

The world is synthetic (no real CSV row, no account id, no fill figure from any real file, no real game: the clubs
and the ticker are fictional, Testford at Mockley): its closing pages written as production writes them
(deploy/hosting/closing.closing_doc: the closing block's start is the COVERED start, a kickoff; the file's
exported_at is when the run's page went out, the run going at the start less RUN_LEAD_MIN), and a Cockpit ledger
export whose fills are the entries importKalshiCSV stores (ledger_fills.parse_ticker / side_fields spread in), every
figure invented here. Pins: each attribution case (early on the PLAY side; arm flip on a PASS and on a side change,
paired with its pre-kickoff exit; a pre-closing fill with no logged PLAY is not the arm's, early or flip alike; a
same-day side re-log listed as unestablished; an ordinary fill after the page went out; the latest page decides, by
its export time; a LADDER close is not ruled; pages that disagree are refused; latest/ is refused), the CLV formula's
sign, a breach (an entry after kickoff, a sale after kickoff; a settlement is none; a sale not read is labelled), an
interest row (its own kind, never attributed), the matcher untouched and a flip out of executed_positions, the
receipt's table in cents and units only, and the bulletin's one word.
"""
import importlib.util
import json
import os
from datetime import datetime
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
QTY, ENTRY, EXIT_, FEE = 4711, 0.4913, 0.4512, 0.0123    # invented figures: none may reach the receipt's output
FILL_ID = "syn-FIXTURE␟fixture␟0001"            # a synthetic id (a real one carries the account id)


def row(call="PLAY", pick="AWAY", cost=0.51, order=TST, side="YES", mid=9001, units=0.5, ko=KO):
    desk = {"call": call, "pick": pick, "units": units if call != "PASS" else 0,
            "exec": {"cost": cost, "basis": "ask", "contracts": 777},
            "order": {"ticker": order, "side": side, "limit": cost, "contracts": 777} if call in ("PLAY", "LADDER")
            else None}
    return {"match_id": mid, "home_team": "Mockley", "away_team": "Testford", "utc_date": ko, "competition": "PL",
            "desk": desk, "kalshi_legs": {"HOME": {"ticker": MCK}, "AWAY": {"ticker": TST}, "DRAW": {"ticker": TIE}}}


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


def entry(ticker=TST, side="yes", opened=PRE, closed="2026-11-08T16:00:00Z", exit_=1.0, close_fee=0.0, entry_=ENTRY,
          fid=FILL_ID, **extra):
    """The entry the Cockpit's importKalshiCSV stores (synthetic figures)."""
    title = {"TST": "Testford wins — Mockley", "MCK": "Mockley wins — Testford", "TIE": "Tie — Testford v Mockley"}
    fx = {"id": fid, "ticker": ticker, "side": side, "qty": QTY, "entry": entry_, "exit": exit_,
          "staked": round(QTY * entry_, 4), "fees": round(FEE + (close_fee or 0), 4), "open_fee": FEE,
          "close_fee": close_fee, "pnl_pre": 0.0, "pnl_net": 0.0, "opened": opened, "closed": closed,
          "title": title.get(ticker.rsplit("-", 1)[-1], ""), **extra}
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


def world(tmp_path, pages, fills, calls=()):
    """pages: [(exported_at, rows) or (exported_at, rows, start) or (exported_at, rows, start, dated folder)]."""
    ex = tmp_path / "exports"
    for pg in pages:
        at, rows, start, sub = (list(pg) + [KO_DT, None][len(pg) - 2:])[:4]
        write_page(ex / sub if sub else ex, at, rows, start)
    return {"calls": list(calls), "fills": list(fills)}, ex


def one(tmp_path, page_row, f, calls=(call(),), extra_pages=()):
    L, ex = world(tmp_path, [*extra_pages, (RUN, [page_row])], [f], calls)
    return ea.attribute(L, ex)[0], L, ex


# ---- the attribution ----------------------------------------------------------------------------------------------

def test_early_is_attributed_to_the_closing_call_with_its_price_and_clv(tmp_path):
    a, L, _ = one(tmp_path, row(), entry())
    assert a["arm"] == ea.ARM_EARLY and a["early"] is True
    assert a["early_price"] == ENTRY and a["closing_cost"] == 0.51
    assert a["early_clv_cents"] == pytest.approx((0.51 - ENTRY) * 100)
    assert a["closing_call"] == {"match_id": 9001, "run": RUN, "start": KO_DT, "pick": "AWAY", "units": 0.5}
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
    a, _, _ = one(tmp_path, row(order="KXEPLGAME-26NOV08TSTMCK-XXX"), entry())
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
    a, _, _ = one(tmp_path, row(pick="HOME", order=MCK), entry())
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
    a, _, _ = one(tmp_path, row(), entry(opened="2026-11-08T13:40:00Z"))      # after the page, before kickoff
    assert a["arm"] is None and a["arm_note"] == ea.AFTER_RUN and a["book"] == "system_matched"


def test_the_latest_closing_run_decides(tmp_path):
    """A re-dated game: its earlier page (another start, the day before) PLAYed; the later page PASSes."""
    earlier = (datetime(2026, 11, 7, 13, 26), [row(ko="2026-11-07T14:00:00")], datetime(2026, 11, 7, 14, 0))
    a, _, _ = one(tmp_path, row(call="PASS"), entry(opened="2026-11-06T15:30:00Z"), extra_pages=[earlier])
    assert a["arm"] == ea.ARM_FLIP


def test_a_ladder_close_is_not_ruled(tmp_path):
    a, _, _ = one(tmp_path, row(call="LADDER", order=MCK, side="NO"), entry())
    assert a["arm"] is None and a["arm_note"] == ea.NOT_RULED_CALL


def test_pages_of_one_run_that_disagree_are_refused(tmp_path):
    L, ex = world(tmp_path, [(RUN, [row()]), (RUN, [row(call="PASS")], KO_DT, "2026-11-08")], [entry()], [call()])
    a = ea.attribute(L, ex)[0]                                  # the same run (one export time), a dated copy differs
    assert a["arm"] is None and a["arm_note"] == ea.DISAGREE


def test_no_page_and_unread_time(tmp_path):
    a, _, _ = one(tmp_path / "a", row(), entry(ticker="KXEPLGAME-26NOV08QQQRRR-QQQ"))
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
             entry(ticker="KXEPLGAME-26NOV09QUIREX-QUI", fid="syn-f1", title="Quillby wins — Rexham",
                   closed="2026-11-09T13:00:00Z",
                   exit_=EXIT_, close_fee=0.0101, entry_=0.4800, opened="2026-11-08T10:00:00Z"),   # flip, exited
             entry(fid="syn-b1", opened="2026-11-08T14:30:00Z"),                     # breach (an add after kickoff)
             entry(fid="syn-i1", type="interest", ticker="")]
    ars = {**row(call="PASS", mid=9002), "home_team": "Rexham", "away_team": "Quillby",
           "utc_date": "2026-11-09T14:00:00",
           "kalshi_legs": {"HOME": {"ticker": "KXEPLGAME-26NOV09QUIREX-REX"},
                           "AWAY": {"ticker": "KXEPLGAME-26NOV09QUIREX-QUI"}}}
    ars_call = {**call(cid="c2"), "home": "Rexham", "away": "Quillby", "kickoff": "2026-11-09T14:00:00Z"}
    L, ex = world(tmp_path, [(RUN, [row()]), (datetime(2026, 11, 9, 13, 26), [ars], datetime(2026, 11, 9, 14, 0))],
                  fills, [call(), ars_call])
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
    assert "arm breach: match 9001 Testford @ Mockley (kickoff 2026-11-08T14:00:00Z): opened at or after kickoff" in out
    for figure in ("$", "4711", "0.4913", "0.4512", "0.0123", "0.0101", "0.53", "0.48", "777", "syn-", "FIXTURE",
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
    logged call, or only a value shadow on its side) is not the arm's, the same gate as a flip's. Early and flip are
    held to one rule, so a prematch page never loaded into the Cockpit counts neither its winners nor its flips."""
    none_, _, _ = one(tmp_path / "a", row(), entry(), calls=())
    shadow, _, _ = one(tmp_path / "b", row(), entry(),
                       calls=(call(call_type="value_shadow", units=0, shadow_units=0.5, cid="vs1"),))
    flip, _, _ = one(tmp_path / "c", row(call="PASS"), entry(closed="2026-11-08T13:10:00Z", exit_=EXIT_,
                                                             close_fee=0.0101), calls=())
    for a in (none_, shadow, flip):
        assert a["arm"] is None and not a["early"] and a["arm_note"] == ea.PRE_CLOSE_OFF_ARM
        assert a["early_clv_cents"] is None and a["book"] == "off_book_sports" and a.get("call_id") is None
    t = ea.arm_table([none_, shadow, flip])
    assert (t["toward_thirty"], t["early"], t["flips"], t["not_the_arms"]) == (0, 0, 0, 3)
    assert t["mean_early_clv_cents"] is None


def test_a_same_day_side_relog_is_listed_unestablished_never_dropped(tmp_path):
    """The Cockpit's callKey has no pick: a closing page that changes side the same ET day re-logs the prematch call
    in place, so the ledger keeps only the new side's call. The early fill on the old side is then "logged call
    exists but the side disagrees": it may be a (c)(iii) flip or an off-book bet; the ledger cannot tell, so it is
    listed as unestablished (its own line), never counted and never silently "not the arm's"."""
    L, ex = world(tmp_path, [(RUN, [row(pick="HOME", order=MCK)])], [entry(opened="2026-11-08T06:30:00-05:00")],
                  [call(pick="HOME", log_date="2026-11-08")])
    assert lf.classify_fills(L)[0]["category"] == ea.MATCHER_SIDE_DISAGREES
    a = ea.attribute(L, ex)[0]
    assert a["arm"] is None and a["arm_note"] == ea.SIDE_RELOGGED and a["book"] == "off_book_sports"
    t = ea.arm_table([a])
    assert (t["unestablished"], t["toward_thirty"], t["not_the_arms"]) == (1, 0, 0)
    assert any("UNESTABLISHED" in ln and ": 1" in ln for ln in ea.table_lines(t))


def test_a_flip_not_exited_before_kickoff_is_a_labelled_line(tmp_path):
    held = entry(fid="syn-h", close_fee=0.0, exit_=0.0)
    late = entry(fid="syn-l", closed="2026-11-08T14:30:00Z", exit_=0.40, close_fee=0.01)
    done = entry(fid="syn-d", closed="2026-11-08T13:10:00Z", exit_=0.48, close_fee=0.01, entry_=0.49)
    L, ex = world(tmp_path, [(RUN, [row(call="PASS")])], [held, late, done], [call()])
    rows = ea.attribute(L, ex)
    assert [r["arm"] for r in rows] == [ea.ARM_FLIP] * 3
    t = ea.arm_table(rows)
    assert (t["flips"], t["flips_exited_before_kickoff"]) == (3, 1)
    assert t["flips_not_exited_before_kickoff"] == {"held to settlement or open": 1, "exited at or after kickoff": 1,
                                                    "sale not read": 0, "time not read": 0}
    assert t["mean_flip_cost_cents"] == pytest.approx(1.0)
    ln = next(x for x in ea.table_lines(t) if x.startswith("ARM FLIP NOT EXITED"))
    assert "held to settlement or open 1" in ln and "exited at or after kickoff 1" in ln
    assert "not in the flip cost" in ln


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
    assert t["flips_not_exited_before_kickoff"]["sale not read"] == 1


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
    assert "NOT FOR POSTING" in lines[i - 1] and lines[i - 1].startswith("BREACHES LISTED")
    assert "9001" not in lines[-1] and "Testford" not in lines[-1]                       # never in the JSON
    for ln in lines[:i - 1]:
        assert "Testford" not in ln and "Mockley" not in ln                               # the table names no game


def test_the_table_prints_the_arms_distinct_games_beside_the_lot_count(tmp_path):
    """toward_thirty counts the export's rows (lots); the distinct games are printed beside it (the unit of the 30
    is the architect's to rule: an open question, nothing re-cut here)."""
    p, ex = _receipt_world(tmp_path)
    t = ea.arm_table(ea.attribute(json.loads(p.read_text()), ex))
    assert (t["toward_thirty"], t["arm_games"]) == (3, 2)
    assert any("distinct games 2" in ln for ln in ea.table_lines(t))
