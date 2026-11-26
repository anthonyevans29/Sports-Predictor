"""#1102 PR2, THE DESK'S RULE: kind "stale_price", the slate's alone (DEV 3's one text, comment 7167846609, the PR2
bullets and the Pins; ARCHITECT 2026-11-25 18:46 ET, addendum 555 item 1, which rules the six questions):

- A PLAY or a LADDER whose shown price was captured before the run's start (F1, the file's run_started_at), in its
  second, never, or at a time that will not parse, is PASS stale_price by _no_call, last on desk_call's return (NFL
  only with 214 off): no order, exec, value shadow or parlay leg. Books where shown (F2); Kalshi where shown (F3): one
  leg or none, that leg ("Kalshi price" when there is none to name, Q1); more, the legs the UNTURNED call reads, an
  unread stale leg inert. Every reason, books first then the legs sorted (Q4); "<P> capture time unreadable: no call"
  is its own wording (Q3). A start present but not the CLI's one form (Q2) turns every staked row.
- desk_meta.stale_price_rule: "on" | "on: run start unreadable" | "off: no run start" | "off" (switch off, any start).
- THE RULE SHIPS OFF (addendum 555 item 1(a)): "Until that addendum nothing turns, on a new file or an old one." The
  rule's own pins run with the switch on through the `on` fixture; the shipped default is pinned to turn nothing.
"""
import ast
import inspect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from src.walters import desk_policy as dp
from tests.test_1102_capture_fields import _export, _ko, _soccer_world, iso  # noqa: F401  (the PR1 world fixture)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import closing as mc  # noqa: E402

NOW = datetime(2026, 12, 1, 17, 5, tzinfo=timezone.utc)
NOW_MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
F1 = "2026-12-01T17:00:00.250000Z"          # the run's held start
BEFORE = "2026-12-01T16:59:59Z"
IN_SECOND = "2026-12-01T17:00:00Z"          # in F1's second: stale (law 4)
FRESH = "2026-12-01T17:00:01Z"
ABSENT = object()

R_BOOKS_BEFORE = "books price captured before this run's start: no call"
R_BOOKS_NEVER = "books price never captured: no call"
R_BOOKS_UNREAD = "books price capture time unreadable: no call"
R_UNREADABLE = "this run's start is unreadable: no call"


@pytest.fixture
def on(monkeypatch):
    """The rule with its switch on, as a later addendum would turn it (the shipped switch is off)."""
    monkeypatch.setitem(dp.STALE_PRICE_RULE, "on", True)


def row(mid, home, p_home, *, fair_h=None, bid=0.49, ask=0.50, minutes=60, comp="MLB", series="KXMLBGAME",
        draw=None, fair_d=None, books=FRESH, legs=FRESH):
    """An export prediction row in the shape of tests/test_closing_runs.py's row(), with PR1's stamps: F2 on the priced
    block (bookmaker_count > 0), F3 one stamp per kalshi_legs leg (`legs`: one value for every leg, or a dict)."""
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = ({"HOME": fair_h, "AWAY": round(1 - fair_h, 4)} if draw is None else
                           {"HOME": fair_h, "DRAW": fair_d, "AWAY": round(1 - fair_h - fair_d, 4)})
        if books is not ABSENT:
            mk["books_captured_at"] = books
    tick = home[:3].upper()
    r = {"match_id": mid, "home_team": home, "away_team": f"{home} Visitors", "competition": comp, "stage": "regular",
         "utc_date": (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
         "prediction": {"probabilities": {"home_win": p_home, "draw": draw,
                                          "away_win": round(1 - p_home - (draw or 0), 4)}, "tier": "lean"},
         "market": mk, "kalshi_bid": bid, "kalshi_ask": ask,
         "kalshi_legs": {"HOME": {"ticker": f"{series}-26DEC01-{tick}H", "bid": bid, "ask": ask},
                         "AWAY": {"ticker": f"{series}-26DEC01-{tick}A", "bid": round(1 - ask, 2),
                                  "ask": round(1 - bid, 2)}}}
    if comp == "MLB":
        r["pitchers"] = {s: {"name": f"{s} starter", "kind": "confirmed"} for s in ("home", "away")}
    if draw is not None:
        r["kalshi_legs"]["DRAW"] = {"ticker": f"{series}-26DEC01-TIE", "bid": 0.26, "ask": 0.27}
    r["kalshi_legs_captured_at"] = dict(legs) if isinstance(legs, dict) else {k: legs for k in r["kalshi_legs"]}
    return r


def mlb_play(mid=1, **kw):            # a two-way MLB PLAY on HOME, books reference; reads HOME (exec, order)
    return row(mid, "Clearwater", 0.60, fair_h=0.53, bid=0.51, ask=0.52, **kw)


def soccer_play(mid=6, **kw):         # a three-way PLAY on HOME with a DRAW value shadow; reads HOME and DRAW
    return row(mid, "Homeplay", 0.55, fair_h=0.48, fair_d=0.24, draw=0.30, comp="PL", series="KXEPLGAME",
               bid=0.47, ask=0.48, **kw)


def soccer_ladder(mid=3, **kw):       # an away LADDER (X2 = NO on HOME); reads HOME (the order) only
    return row(mid, "Ladder", 0.17, fair_h=0.30, fair_d=0.252, draw=0.214, comp="PL", series="KXEPLGAME",
               bid=0.29, ask=0.30, **kw)


def floor_pass(mid=4, **kw):          # an MLB floor PASS with a HOME value shadow
    return row(mid, "Valuetown", 0.45, fair_h=0.40, bid=0.39, ask=0.40, **kw)


def nfl_kalshi_only(mid=7, **kw):     # NFL, no books: a kalshi_only-reference PLAY once 214 is off
    return row(mid, "Kalnfl", 0.62, comp="NFL", series="KXNFLGAME", bid=0.51, ask=0.52, **kw)


def nfl_books(mid=8, **kw):
    return row(mid, "Booknfl", 0.62, fair_h=0.55, comp="NFL", series="KXNFLGAME", bid=0.54, ask=0.55, **kw)


def annotate(rows, sport="mlb", f1=F1):
    doc = {"sport": sport, "predictions": [json.loads(json.dumps(r)) for r in rows]}
    if f1 is not ABSENT:
        doc["run_started_at"] = f1
    return dp.annotate(doc, now=NOW)


def desks(doc):
    return {p["match_id"]: p["desk"] for p in doc["predictions"]}


def one(r, sport="mlb", f1=F1):
    doc = annotate([r], sport, f1)
    return doc["predictions"][0]["desk"], doc


def turned(d, *reasons):
    return (d["call"], d["units"], d["pass_kind"], d["reasons"], d["reason"]) == (
        "PASS", 0, dp.STALE_PRICE_KIND, list(reasons), " · ".join(reasons))


# =============================================================================== THE SHIPPED DEFAULT: OFF ==

def test_the_rule_ships_off_and_nothing_turns_on_a_new_file_or_an_old_one():
    """Addendum 555 item 1(a): "The rule ships OFF. [...] Until that addendum nothing turns, on a new file or an old
    one." The switch's line is {"on": False}; every stale case below calls exactly as the file without F1, and every
    file says "off" whatever its start."""
    tree = ast.parse(Path(dp.__file__).read_text())
    line = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) ==
                "STALE_PRICE_RULE")
    assert ast.literal_eval(line.value) == {"on": False} and dp.STALE_PRICE_RULE == {"on": False}
    rows = [mlb_play(books=BEFORE, legs=None), soccer_play(1, books=None, legs=BEFORE), soccer_ladder(2, legs=BEFORE),
            mlb_play(5, minutes=2 * 24 * 60, books=IN_SECOND)]
    bare = {sp: desks(annotate(rows, sp, ABSENT)) for sp in ("mlb", "soccer")}
    for f1 in (F1, None, "junk", 12345, "2026-12-01T17:00:00Z"):
        for sp in ("mlb", "soccer"):
            doc = annotate(rows, sp, f1)
            assert desks(doc) == bare[sp], (f1, sp)
            assert doc["desk_meta"]["stale_price_rule"] == "off"
    assert annotate(rows, "mlb", ABSENT)["desk_meta"]["stale_price_rule"] == "off"
    assert {d["call"] for d in bare["mlb"].values()} >= {"PLAY"}                      # the staked rows stay staked


def test_the_shipped_default_turns_nothing_in_a_rescore_or_the_parlays():
    with dp.stale_price_rule_off():
        doc = annotate([mlb_play(books=BEFORE)])
    assert [x["verdict"] for x in dp.rescore(doc)] == ["unchanged"]
    a = annotate([mlb_play(1, books=BEFORE), soccer_play(2, legs=BEFORE)], "mlb")
    b = annotate([mlb_play(1, books=BEFORE), soccer_play(2, legs=BEFORE)], "mlb", ABSENT)
    pa, pb = dp.parlays_doc([("a", a)], now=NOW), dp.parlays_doc([("b", b)], now=NOW)
    assert pa["live_legs"] == pb["live_legs"] > 0 and pa["tickets"] == pb["tickets"]


# ======================================================================================= each reason: books ==

@pytest.mark.parametrize("books,reason", [(BEFORE, R_BOOKS_BEFORE), (IN_SECOND, R_BOOKS_BEFORE),
                                          (None, R_BOOKS_NEVER), (ABSENT, R_BOOKS_NEVER),
                                          ("2026-12-01T17:00:01.5Z", R_BOOKS_UNREAD),
                                          ("2026-12-01 17:00:01", R_BOOKS_UNREAD), (12345, R_BOOKS_UNREAD),
                                          ("2026-02-30T17:00:01Z", R_BOOKS_UNREAD), (FRESH, None)])
def test_each_books_reason(on, books, reason):
    d, doc = one(mlb_play(books=books))
    assert doc["desk_meta"]["stale_price_rule"] == "on"
    if reason is None:
        assert d["call"] == "PLAY" and d["pass_kind"] is None
    else:
        assert turned(d, reason)


@pytest.mark.parametrize("count", [0, None])
def test_books_not_shown_are_not_read(on, count):
    """Books where shown (C:1186 shows_books): a block with no complete book priced shows none, its F2 unread."""
    r = mlb_play(books=BEFORE)
    r["market"]["bookmaker_count"] = count
    d, _ = one(r)
    want, _ = one(r, f1=ABSENT)
    assert d == want and d["call"] == "PLAY"


# ======================================================================================= each reason: Kalshi ==

def one_leg(**kw):
    r = mlb_play(**kw)
    r["kalshi_legs"].pop("AWAY")
    r["kalshi_legs_captured_at"].pop("AWAY", None)
    return r


@pytest.mark.parametrize("cap,reason", [
    ({"HOME": BEFORE}, "Kalshi HOME leg captured before this run's start: no call"),
    ({"HOME": IN_SECOND}, "Kalshi HOME leg captured before this run's start: no call"),
    ({"HOME": None}, "Kalshi HOME leg never captured: no call"),
    ({}, "Kalshi HOME leg never captured: no call"),
    ({"HOME": "yesterday"}, "Kalshi HOME leg capture time unreadable: no call"),
    ("junk", "Kalshi HOME leg capture time unreadable: no call"),
    ({"HOME": FRESH}, None)])
def test_each_kalshi_reason_one_leg(on, cap, reason):
    r = one_leg()
    r["kalshi_legs_captured_at"] = cap
    d, _ = one(r)
    if reason is None:
        assert d["call"] == "PLAY"
    else:
        assert turned(d, reason)


@pytest.mark.parametrize("cap,reason", [(None, "Kalshi price never captured: no call"),
                                        ({}, "Kalshi price never captured: no call"),
                                        ("junk", "Kalshi price capture time unreadable: no call")])
def test_kalshi_shown_with_no_leg_to_name_q1(on, cap, reason):
    """Addendum 555 item 1 Q1: "KALSHI SHOWN WITH NO LEG TO NAME: stale [...] "Kalshi price never captured: no call".
    [...] The text's P gains "Kalshi price" for this one case." The HOME contract's quotes alone, no kalshi_legs."""
    r = mlb_play()
    r["kalshi_legs"] = None
    r["kalshi_legs_captured_at"] = cap
    want, _ = one(r, f1=ABSENT)
    assert want["call"] == "PLAY"
    d, _ = one(r)
    assert turned(d, reason)


def test_a_kalshi_block_alone_shows_kalshi_and_a_mismatched_one_does_not(on):
    r = mlb_play()
    r.update(kalshi_bid=None, kalshi_ask=None, kalshi_legs=None, kalshi_legs_captured_at=None)
    r["market"]["kalshi"] = {"status": "mismatched", "events": ["A", "B"]}
    d, _ = one(r)
    want, _ = one(r, f1=ABSENT)
    assert d == want and d["call"] == "PLAY"                                         # not shown: unchanged
    r["market"]["kalshi"] = {"status": "matched", "yes_bid": 0.5}
    d, _ = one(r)
    assert turned(d, "Kalshi price never captured: no call")


# ============================================================================================= multi-leg ==

def test_multi_leg_a_read_leg_stale_turns_and_names_it(on):
    d, _ = one(soccer_play(legs={"HOME": BEFORE, "DRAW": FRESH, "AWAY": FRESH}), "soccer")
    assert turned(d, "Kalshi HOME leg captured before this run's start: no call")


def test_multi_leg_an_unread_stale_leg_is_inert(on):
    d, _ = one(soccer_play(legs={"HOME": FRESH, "DRAW": FRESH, "AWAY": BEFORE}), "soccer")
    want, _ = one(soccer_play(), "soccer", ABSENT)
    assert d == want and d["call"] == "PLAY"


def test_multi_leg_a_read_leg_missing_from_f3_is_never_captured(on):
    d, _ = one(soccer_play(legs={"DRAW": FRESH, "AWAY": FRESH}), "soccer")
    assert turned(d, "Kalshi HOME leg never captured: no call")


def test_multi_leg_the_value_shadow_exec_leg_is_read(on):
    want, _ = one(soccer_play(), "soccer", ABSENT)
    assert want["value_shadow"]["side"] == "DRAW" and want["value_shadow"]["exec"] is not None
    d, _ = one(soccer_play(legs={"HOME": FRESH, "DRAW": BEFORE, "AWAY": FRESH}), "soccer")
    assert turned(d, "Kalshi DRAW leg captured before this run's start: no call")


def test_multi_leg_a_kalshi_only_reference_reads_every_leg(on):
    with dp.nfl_market_only_rule_off():
        want, _ = one(nfl_kalshi_only(), "nfl", ABSENT)
        assert want["call"] == "PLAY" and want["reference"] == "kalshi_only"
        d, _ = one(nfl_kalshi_only(legs={"HOME": FRESH, "AWAY": BEFORE}), "nfl")
    assert turned(d, "Kalshi AWAY leg captured before this run's start: no call")
    assert d["reference"] is None and d["market_ref"] is None                         # no book price: null


def test_multi_leg_a_ladder_reads_its_order_leg_no_on_home(on):
    want, _ = one(soccer_ladder(), "soccer", ABSENT)
    assert want["call"] == "LADDER" and want["order"]["ticker"].endswith("LADH") and want["exec"] is None
    d, _ = one(soccer_ladder(legs={"HOME": BEFORE, "DRAW": FRESH, "AWAY": FRESH}), "soccer")
    assert turned(d, "Kalshi HOME leg captured before this run's start: no call")
    d, _ = one(soccer_ladder(legs={"HOME": FRESH, "DRAW": BEFORE, "AWAY": BEFORE}), "soccer")
    assert d == want                                                                  # unread: inert


def test_several_stale_prices_every_reason_in_r2s_order_q4(on):
    """Addendum 555 item 1 Q4: "ALL THE REASONS, in R2's order: the books first, then the legs sorted"; an unread stale
    leg (AWAY) adds none."""
    d, _ = one(soccer_play(books=IN_SECOND, legs={"HOME": None, "DRAW": "junk", "AWAY": BEFORE}), "soccer")
    assert turned(d, R_BOOKS_BEFORE, "Kalshi DRAW leg capture time unreadable: no call",
                  "Kalshi HOME leg never captured: no call")
    assert d["reason"] == (f"{R_BOOKS_BEFORE} · Kalshi DRAW leg capture time unreadable: no call · "
                           "Kalshi HOME leg never captured: no call")


# ========================================================================================= unreadable F1 ==

@pytest.mark.parametrize("f1", [None, "", "2026-12-01T17:00:00Z", "2026-12-01T17:00:00.250000+00:00",
                                "2026-12-01T17:00:00.25Z", "2026-12-01T17:00:00.2500000Z", 12345,
                                "2026-13-01T17:00:00.250000Z", "２026-12-01T17:00:00.250000Z"])
def test_an_unreadable_start_turns_every_staked_row_and_no_pass(on, f1):
    """526 Q3: a start present but not ISO Z (null too) turns every staked row, "this run's start is unreadable: no
    call", the prices fresh or not; addendum 555 item 1 Q2: ISO Z is the CLI's six-digit form and nothing else."""
    rows = [mlb_play(1), soccer_play(2), soccer_ladder(3), floor_pass(4)]
    bare = desks(annotate(rows, "soccer", ABSENT))
    assert [bare[i]["call"] for i in (1, 2, 3, 4)] == ["PLAY", "PLAY", "LADDER", "PASS"]
    doc = annotate(rows, "soccer", f1)
    got = desks(doc)
    assert all(turned(got[i], R_UNREADABLE) for i in (1, 2, 3))
    assert got[4] == bare[4]
    assert doc["desk_meta"]["stale_price_rule"] == "on: run start unreadable"


# ================================================================================================ PASS kept ==

def test_a_pass_is_never_touched(on):
    """A floor, a kalshi-only-suspended (no reference), a quarantine-shadow and a started PASS with every price stale
    keep their call, reasons, shadow units and value shadow byte for byte against the same file without F1."""
    rows = [floor_pass(4, books=BEFORE, legs=None), row(2, "Kalshiburg", 0.60, bid=0.51, ask=0.52, legs=BEFORE),
            row(9, "Quarton", 0.80, fair_h=0.55, bid=0.54, ask=0.55, books=None, legs=BEFORE),
            mlb_play(10, minutes=-20, books=BEFORE, legs=BEFORE)]
    bare = desks(annotate(rows, "mlb", ABSENT))
    kinds = {i: bare[i]["pass_kind"] for i in bare}
    assert {bare[i]["call"] for i in bare} == {"PASS"} and kinds[4] == "floor" and kinds[10] == "started"
    assert kinds[2] == dp.KALSHI_ONLY_SUSPENDED_KIND and dp.is_quarantine_shadow(
        {"call": "PASS", "shadowUnits": bare[9]["shadow_units"], "tags": bare[9]["tags"]})
    assert bare[4]["value_shadow"] is not None
    for f1 in (F1, "junk"):
        assert desks(annotate(rows, "mlb", f1)) == bare


# ==================================================================================== what a turned row loses ==

def test_a_turned_row_keeps_nothing_of_the_would_be_call_q5(on):
    want, _ = one(soccer_play(), "soccer", ABSENT)
    assert want["exec"] and want["order"]["ticker"] and want["value_shadow"] and want["shadow_units"] == 0
    d, _ = one(soccer_play(books=BEFORE), "soccer")
    assert (d["call"], d["units"], d["cls"], d["pass_kind"], d["tags"]) == ("PASS", 0, "pass", "stale_price",
                                                                            ["stale_price"])
    assert d["exec"] is None and d["order"] is None and d["value_shadow"] is None and d["shadow_units"] == 0
    assert "ladder_exec" not in d and d["edge_pp"] is None and d["reference"] == "books"
    assert not {"kalshi_only_hold", "market_only_hold", "kickoff_clock"} & set(d)
    lad, _ = one(soccer_ladder(legs=BEFORE), "soccer")
    assert lad["pass_kind"] == "stale_price" and "ladder_exec" not in lad and lad["order"] is None
    assert dp.STALE_PRICE_KIND == "stale_price" and dp.STALE_PRICE_KIND in dp.NO_CALL_KINDS


# ===================================================================================================== NFL ==

def test_nfl_with_214_on_is_never_turned(on):
    """With 214 on every NFL row is PASS market_only before the rule: its hold, exec block and value shadow stay the
    chain's (chain_kind)."""
    rows = [nfl_books(8, books=BEFORE, legs=BEFORE), nfl_kalshi_only(7, legs=BEFORE)]
    bare = desks(annotate(rows, "nfl", ABSENT))
    got = desks(annotate(rows, "nfl"))
    assert got == bare and {d["pass_kind"] for d in got.values()} == {dp.NFL_MARKET_ONLY_KIND}
    assert got[8]["market_only_hold"]["would_call"] == "PLAY" and got[8]["exec"] is not None


def test_nfl_with_214_off_is_turned_like_any_other(on):
    with dp.nfl_market_only_rule_off():
        d, _ = one(nfl_books(books=BEFORE), "nfl")
    assert turned(d, R_BOOKS_BEFORE) and d["value_shadow"] is None and "market_only_hold" not in d


# =========================================================================================== beyond the day ==

def test_a_staked_row_beyond_the_day_is_turned(on):
    d, _ = one(mlb_play(minutes=2 * 24 * 60, books=BEFORE))
    assert turned(d, R_BOOKS_BEFORE)


# ============================================================================================= same second ==

@pytest.mark.parametrize("f1", ["2026-12-01T17:00:00.000000Z", "2026-12-01T17:00:00.999999Z"])
def test_a_stamp_in_f1s_second_is_stale(on, f1):
    """513 Q2 (law 4): a stamp before F1 or in its second is stale; the next second is fresh. (No pin that R2 agrees
    in the same second: 526 item 3.)"""
    d, _ = one(mlb_play(books=IN_SECOND), f1=f1)
    assert turned(d, R_BOOKS_BEFORE)
    d, _ = one(mlb_play(books=FRESH), f1=f1)
    assert d["call"] == "PLAY"


# ==================================================================================================== meta ==

def test_the_four_meta_values_and_their_precedence(monkeypatch):
    for f1 in (F1, ABSENT, "junk", None):
        assert annotate([mlb_play()], f1=f1)["desk_meta"]["stale_price_rule"] == "off"      # switch off: any start
    monkeypatch.setitem(dp.STALE_PRICE_RULE, "on", True)
    assert annotate([mlb_play()])["desk_meta"]["stale_price_rule"] == "on"
    assert annotate([mlb_play()], f1=ABSENT)["desk_meta"]["stale_price_rule"] == "off: no run start"
    assert annotate([mlb_play()], f1=None)["desk_meta"]["stale_price_rule"] == "on: run start unreadable"
    keys = list(annotate([mlb_play()])["desk_meta"])
    assert keys.index("stale_price_rule") == keys.index("exec_non_positive_rule") + 1
    assert "stale_price_rule" not in dp.parlays_doc([("a", annotate([mlb_play()]))], now=NOW)["desk_meta"]


def test_the_export_files_meta(iso, on, tmp_path):
    """export-predictions with and without --run-start, export-fixtures (no --run-start: "off: no run start"), the NFL
    file with and without F1 (E:99-101, E:1434-1436, N:426-427)."""
    from src.db.database import session_scope
    from src.db.schema import Sport
    from src.walters.export import export_fixtures
    from src.walters.nfl_predict import export_nfl_predictions
    ko = _ko()
    with session_scope() as s:
        _soccer_world(s, ko, key="meta")
    with_f1, _ = _export(Sport.SOCCER, "CFSOC", ko, run_started_at=F1, desk=True)
    without, _ = _export(Sport.SOCCER, "CFSOC", ko, desk=True)
    assert with_f1["desk_meta"]["stale_price_rule"] == "on"
    assert without["desk_meta"]["stale_price_rule"] == "off: no run start"
    fx = export_fixtures("CFSOC", out_dir=str(tmp_path / "fx"), desk=True)
    fdoc = json.loads(open(fx).read())
    assert fdoc["desk_meta"]["stale_price_rule"] == "off: no run start"
    for f1, want in ((F1, "on"), (None, "off: no run start")):
        p = export_nfl_predictions(days_ahead=8, out_dir=str(tmp_path / f"n{want[:2]}"), desk=True,
                                   run_started_at=f1)
        assert json.loads(open(p).read())["desk_meta"]["stale_price_rule"] == want


def test_the_intl_file_reads_off_no_run_start(on, monkeypatch, tmp_path):
    """532 Q2: export-intl-predictions' file gains only desk_meta.stale_price_rule "off: no run start", through
    maybe_annotate (src/walters/intl_production.py:133), and no F1-F4."""
    from src.walters import intl_production as ip
    from tests.test_desk_host_fence import intl_unl
    monkeypatch.setattr(ip, "build", lambda now=None, hours=None: {"rows": [intl_unl()], "fit": {}, "now": NOW,
                                                                    "why": "test"})
    monkeypatch.setattr(ip, "_export_with_history", lambda doc, now, out_dir, *a: ("x", doc))
    _, doc = ip.export(now=NOW, out_dir=str(tmp_path), desk=True)
    assert doc["desk_meta"]["stale_price_rule"] == "off: no run start" and "run_started_at" not in doc


# ================================================================================================= parlays ==

def test_parlays_each_file_by_its_own_f1(on):
    """parlays_doc evaluates each named file by its own F1: only the file with F1 loses its stale legs."""
    rows = [mlb_play(1, books=BEFORE), soccer_play(2, legs=BEFORE)]
    a = annotate([dict(r, match_id=r["match_id"] + 100, home_team=r["home_team"] + " A") for r in rows], "soccer")
    b = annotate([dict(r, home_team=r["home_team"] + " B") for r in rows], "soccer", ABSENT)
    p = dp.parlays_doc([("a.json", a), ("b.json", b)], now=NOW)
    both = dp.parlays_doc([("b.json", b)], now=NOW)
    assert p["live_legs"] == both["live_legs"] == 2
    games = {leg["game"] for t in p["tickets"] for leg in t["legs"]}
    assert games and not [g for g in games if " A" in g]
    with dp.stale_price_rule_off():
        assert dp.parlays_doc([("a.json", a), ("b.json", b)], now=NOW)["live_legs"] == 4


# ================================================================================================== golden ==

def test_the_desk_golden_holds_with_the_switch_on_and_off(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import desk_battery as b
    assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())
    monkeypatch.setitem(dp.STALE_PRICE_RULE, "on", True)
    assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())


def test_base_v11_holds_the_switch_off_and_restores_it(on):
    with dp.base_v11():
        assert dp.STALE_PRICE_RULE["on"] is False
        d, doc = one(mlb_play(books=BEFORE))
    assert d["call"] == "PLAY" and doc["desk_meta"]["stale_price_rule"] == "off"
    assert dp.STALE_PRICE_RULE["on"] is True
    with dp.addendum_off():                         # desk-rescore's before side holds the rule as it is
        assert dp.STALE_PRICE_RULE["on"] is True


# ============================================================================== the read-legs pin (C8 port) ==

def _pin_rows():
    ticketless = mlb_play(11)
    ticketless["kalshi_legs"]["HOME"]["ticker"] = None
    ticketless["home_team"] = "Ticketless"
    no_legs = mlb_play(12)
    no_legs["kalshi_legs"] = None
    mism = mlb_play(13)
    mism.update(kalshi_bid=None, kalshi_ask=None, kalshi_legs=None)
    mism["market"]["kalshi"] = {"status": "mismatched"}
    away = row(14, "Awayplay", 0.38, fair_h=0.46, bid=0.45, ask=0.46)
    return [mlb_play(1), soccer_play(2), soccer_ladder(3), floor_pass(4), ticketless, no_legs, mism, away,
            nfl_kalshi_only(7), nfl_books(8)]


def test_the_desks_read_legs_are_the_closings_desk_read_legs():
    """read_legs is closing.desk_read_legs ported (the Desk never imports deploy/, C8); shows_books_row /
    shows_kalshi_row and _read_leg are shows_books / shows_kalshi and _side_leg. Annotated with the rule as shipped
    (off), so each export row's desk is the unturned call the port reads."""
    seen, legs = set(), set()
    with dp.nfl_market_only_rule_off():
        for sport in ("mlb", "soccer", "nfl"):
            doc = annotate(_pin_rows(), sport, ABSENT)
            ev = dp.evaluate(doc, NOW_MS)
            assert ev["calls"]
            for r, c in ev["calls"]:
                src = r["src"]
                assert dp.read_legs(r, c) == mc.desk_read_legs(src), (sport, src["match_id"])
                assert dp.shows_books_row(src) == mc.shows_books(src)
                assert dp.shows_kalshi_row(src) == mc.shows_kalshi(src)
                for side in ("HOME", "DRAW", "AWAY", None):
                    assert dp._read_leg(r, side) == mc._side_leg(src, side), (sport, src["match_id"], side)
                seen.add((src["desk"]["call"], src["desk"]["reference"], bool(src["desk"]["value_shadow"])))
                x = dp.read_legs(r, c)
                legs.add(json.dumps(["*"] if x is None else sorted(x)))
    assert {("PLAY", "books", True), ("PLAY", "kalshi_only", False), ("LADDER", "books", False),
            ("PASS", "books", True), ("PLAY", "books", False)} <= seen              # value shadow, kalshi_only, LADDER
    assert {'["*"]', '["HOME"]', '["DRAW", "HOME"]', "[]"} <= legs                    # every leg; none (ticketless)


# ================================================================================ F1's one form (Q2) ==

GOOD = ["2026-12-01T17:00:00.250000Z", "2026-12-01T17:00:00.000000Z", "2024-02-29T23:59:59.999999Z"]
BAD = ["2026-12-01T17:00:00Z", "2026-12-01T17:00:00.250000+00:00", "2026-12-01T17:00:00.2500000Z",
       "2026-12-01T17:00:00.25Z", "２０２６-12-01T17:00:00.250000Z", "2026-12-01 17:00:00.250000Z",
       "2026-13-01T17:00:00.250000Z", "2025-02-29T17:00:00.250000Z", "", "junk", " 2026-12-01T17:00:00.250000Z",
       "2026-12-01T17:00:00.250000Z\n", "2026-12-01t17:00:00.250000z"]


@pytest.mark.parametrize("s", GOOD + BAD)
def test_the_desk_reads_f1_exactly_as_the_cli_accepts_it(s):
    """Addendum 555 item 1 Q2: "F1's FORM IS THE CLI's SIX-DIGIT FORM AND NOTHING ELSE, by ONE definition in timeutil
    that the option and the Desk both call"."""
    import cli
    try:
        cli._run_start_option(None, None, s)
        accepted = True
    except click.BadParameter:
        accepted = False
    reading = dp.run_start_reading({"run_started_at": s})
    assert (reading is not dp.RUN_START_UNREADABLE) is accepted is (s in GOOD)
    if accepted:
        assert reading == datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")           # cut to its second
    assert dp.run_start_reading({}) is None


def test_one_definition_in_timeutil():
    import cli
    from src import timeutil
    assert "parse_run_start" in inspect.getsource(cli._run_start_option)
    assert "parse_run_start" in inspect.getsource(dp.run_start_reading)
    src = Path(dp.__file__).read_text() + inspect.getsource(cli._run_start_option)
    assert timeutil.RUN_START_PATTERN not in src and r"\.\d{6}Z" not in src
    assert timeutil.parse_run_start(12345) is None and timeutil.parse_run_start(None) is None
    assert timeutil.parse_run_start(GOOD[0]) == datetime(2026, 12, 1, 17, 0, 0, 250000)


# ================================================================================================= rescore ==

def _published_play(r, sport="mlb", f1=F1):
    with dp.stale_price_rule_off():
        doc = annotate([r], sport, f1)
    assert doc["predictions"][0]["desk"]["call"] == "PLAY"
    return doc


def test_rescore_names_a_published_play_the_rule_now_passes(on):
    rows = dp.rescore(_published_play(mlb_play(books=BEFORE)))
    assert [x["verdict"] for x in rows] == ["stale price"]
    assert rows[0]["addendum_call"] == "PASS" and rows[0]["pass_reason"] == R_BOOKS_BEFORE
    assert rows[0]["exec_cost"] is None and rows[0]["addendum_units"] == 0


def test_rescore_never_turns_a_file_with_no_f1_532_q3(on):
    rows = dp.rescore(_published_play(mlb_play(books=BEFORE), f1=ABSENT))
    assert [x["verdict"] for x in rows] == ["unchanged"]


def test_desk_rescore_counts_stale_price_apart_q6(on, tmp_path):
    import cli
    f = tmp_path / "slate.json"
    doc = _published_play(mlb_play(books=BEFORE))
    doc["predictions"].append(_published_play(mlb_play(2, books=FRESH))["predictions"][0])
    f.write_text(json.dumps(doc))
    out = tmp_path / "r.md"
    r = CliRunner().invoke(cli.cli, ["desk-rescore", str(f), "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert "2 PLAY(s) re-scored · 0 would have been halved under #87 v1.1 rule 3" in r.output
    assert ("1 PLAY(s) now PASS on a stale price (captured before the run's start, never captured or its capture "
            "time unreadable, or the run's start unreadable; #1102, 513 Q2) — not counted as halved") in r.output
    stale = [ln for ln in r.output.splitlines() if ln.endswith("· STALE PRICE")]
    assert len(stale) == 1 and "exec — (no executable quote)" in stale[0]
    assert out.read_text().count("STALE PRICE") == 1


# =============================================================================== the closing's file (526 item 3) ==

def test_a_closings_file_has_no_f1_reads_off_no_run_start_and_carries_f2_to_f4(iso, on):
    """526 item 3 ("new"): the closing's export passes no run start (526 Q1), so its file has no F1, reads "off: no run
    start" and carries F2-F4; closing_doc keeps them. R2 still checks a closing's prices (C:2243): the two never act
    on the same file."""
    import cli
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    ko = utc_now_naive().replace(hour=12, minute=0, second=0, microsecond=0)    # in the argv's window: today (UTC)
    with session_scope() as s:
        mid = _soccer_world(s, ko, key="clo").id
    games = [{"match_id": mid, "start": ko.replace(tzinfo=timezone.utc)}]
    argv = mc.resolve_steps("SOCCER", games[0]["start"], games, datetime.now(timezone.utc), "RID")[-1]
    assert argv[0] == "export-predictions" and "--run-start" not in argv and "--desk" in argv
    i = argv.index("--competition")
    argv = argv[:i + 1] + ["CFSOC"] + argv[i + 2:]          # the seeded world's competition, the closing's argv else
    (iso.tmp / "logs").mkdir()                              # the run's own folder (iso chdirs to its tmp)
    r = CliRunner().invoke(cli.cli, argv)
    assert r.exit_code == 0, r.output
    doc = json.loads(Path(argv[argv.index("--out") + 1]).read_text())
    assert "run_started_at" not in doc and doc["desk_meta"]["stale_price_rule"] == "off: no run start"
    row = {p["match_id"]: p for p in doc["predictions"]}[mid]
    assert row["market"]["books_captured_at"] and row["market"]["books_source_updated_at"]
    assert row["kalshi_legs_captured_at"]
    out = mc.closing_doc(doc, "SOCCER", games[0]["start"], "RID", [mid], [])
    assert out["desk_meta"] == doc["desk_meta"] and "run_started_at" not in out
    assert out["predictions"][0]["market"]["books_captured_at"] == row["market"]["books_captured_at"]
    assert out["predictions"][0]["kalshi_legs_captured_at"] == row["kalshi_legs_captured_at"]
