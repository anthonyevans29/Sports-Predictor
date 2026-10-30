"""DESK POLICY v1.2 — THE UNIT BECOMES A FRACTION OF THE POOL (ARCHITECT 2026-10-30 09:30 ET, addendum 179, #732; the
operator's ruling of 09:26 ET).

Item 1: "a unit is 8% of the money pool, growing and shrinking with it. [...] The half-unit cohort (0 < exec < 4,
QB-clean) is therefore 4% of the pool". Item 3: "the day's unit is computed at the day's FIRST Desk page on the host [...]
as floor(UNIT_FRACTION × pool) in whole dollars, written to a small state file under logs/ (never data/) keyed by the
ET date, and every later page that day [...] reads that file; the unit never changes inside a day". Item 4: "A balance
read that fails leaves the day's unit UNREAD: the page carries no order line and says "unit unread — no order" (law 4);
[...] the previous day's cached unit is NOT reused silently." Item 7: "a line "size over the ask's depth: N contracts"
when it is — informational".

Every figure here is SYNTHETIC (item 5: "never [...] a test fixture"): the FIXTURE_* values are digit patterns (a run or
a repeated digit), pinned below; no file in the checkout sets SP_UNIT_FLOOR_USD or SP_UNIT_USD to a value. The day files
live under tmp_path (SP_DESK_UNIT_DIR); no network, no real logs/, no real API."""
import json
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.walters import desk_policy as dp
from src.walters import desk_unit as du
from src.walters import kalshi_pool as kpool
from tests.test_closing_runs import box, mc  # noqa: F401  (box is a fixture)
from tests.test_desk_exec_addendum import nfl

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 11, 16, 0, tzinfo=timezone.utc)          # 12:00 ET, 2026-10-11 (EDT)
DAY = date(2026, 10, 11)
FIXTURE_POOL = 12345                  # synthetic: floor(0.08 x 12345) = 987
FIXTURE_UNIT = 987
FIXTURE_POOL_LATER = 54321            # synthetic: a pool that moved within the day
FIXTURE_POOL_SMALL = 1111             # synthetic: floor(0.08 x 1111) = 88
FIXTURE_FLOOR = 111                   # synthetic floor, above 88: it binds
FIXTURE_FLOOR_LOW = 11                # synthetic floor, below 88: it does not
LEGS = {"HOME": {"ticker": "T-FIX-HOME", "bid": 0.54, "ask": 0.55}}


@pytest.fixture
def day(tmp_path, monkeypatch):
    """Lift conftest's pin: the Desk reads the day's file, here under tmp_path."""
    d = tmp_path / "logs"
    monkeypatch.setenv(du.DIR_ENV, str(d))
    monkeypatch.setattr(dp, "UNIT_PIN", None)
    monkeypatch.setattr(du, "wall_now", lambda: WALL[0])    # the documents' own clock is "now" unless a test moves it
    WALL[0] = NOW
    return d


WALL = [None]


def pool_of(amount):
    return lambda: {"ok": True, "pool_usd": Decimal(str(amount)), "why": None}


def failed(why="the balance read answered HTTP 503"):
    return lambda: {"ok": False, "pool_usd": None, "why": why}


def play_doc(ask=0.55, bid=0.54, legs=LEGS):
    return {"sport": "nfl", "predictions": [dict(nfl("FIX", 0.62, 0.55, bid=bid, ask=ask, legs=legs), match_id=7001)]}


# ================================================================================================ the constants ==

def test_v12_constants_and_names():
    assert dp.POLICY_VERSION == "v1.2"
    assert (dp.UNIT_FRACTION, dp.HALF_UNIT_FRACTION) == (0.08, 0.04)
    assert dp.HALF_UNIT_FRACTION == dp.UNIT_FRACTION * 0.5                 # the half-unit is 0.5u, by arithmetic
    assert dp.UNIT_FLOOR_ENV == "SP_UNIT_FLOOR_USD"
    assert dp.UNIT_UNREAD_TEXT == "unit unread — no order"                 # item 4, verbatim
    assert mc.UNIT_UNREAD_TEXT == dp.UNIT_UNREAD_TEXT                      # closing.py never imports the Desk (C8)
    import cli
    assert mc.UNIT_MARK == cli.DESK_UNIT_MARK
    assert dp.annotate(play_doc(), now=NOW)["desk_meta"]["policy_version"] == "v1.2"


# ============================================================================================== the arithmetic ==

def test_the_unit_is_floor_of_the_fraction_of_the_pool_in_whole_dollars():
    assert du.compute(FIXTURE_POOL, None) == {"state": "read", "unit_usd": FIXTURE_UNIT,
                                              "floor_state": "SP_UNIT_FLOOR_USD unset: no floor applied"}
    assert du.compute(Decimal("12345.67"), None)["unit_usd"] == 987          # 987.65 -> 987: whole dollars, floored
    assert du.compute(FIXTURE_POOL_LATER, None)["unit_usd"] == 4345          # it grows with the pool
    assert du.compute(FIXTURE_POOL_SMALL, None)["unit_usd"] == 88            # and shrinks with it
    for bad in (0, -FIXTURE_POOL, "nan", "x"):
        assert du.compute(bad, None)["state"] == "unread"


def test_the_floor_binds_below_it_and_never_above_and_a_bad_floor_is_unread():
    assert du.compute(FIXTURE_POOL_SMALL, str(FIXTURE_FLOOR), "environment") == {
        "state": "read", "unit_usd": FIXTURE_FLOOR,
        "floor_state": "SP_UNIT_FLOOR_USD applied (the floor binds: the unit is above UNIT_FRACTION of the pool)"}
    # a floor above the whole pool is unread, "floor above the pool" (addendum 182 item 3, J3 ruled)
    above = du.compute(FIXTURE_FLOOR_LOW * 5, str(FIXTURE_FLOOR), "environment")
    assert above["state"] == "unread" and "floor above the pool" in above["why"] and "unit_usd" not in above
    assert du.compute(FIXTURE_POOL_SMALL, str(FIXTURE_FLOOR_LOW), "environment") == {
        "state": "read", "unit_usd": 88, "floor_state": "SP_UNIT_FLOOR_USD set (not binding)"}
    for bad in ("abc", "0", "-11", "11.5"):                                 # set, but not a positive whole number
        r = du.compute(FIXTURE_POOL, bad, "environment")
        assert r["state"] == "unread" and "SP_UNIT_FLOOR_USD" in r["why"] and "unit_usd" not in r
    # the requirement (item 4): "a half-unit buys at least one contract at any price" — at a 0.99 limit
    one = du.compute(FIXTURE_POOL, "1", "environment")                      # half of 1 is under 0.99
    assert one["state"] == "unread" and "cannot buy one contract at 0.99" in one["why"]
    assert du.compute(FIXTURE_POOL, "2", "environment")["state"] == "read"  # half of 2 buys one at 0.99
    tiny = du.compute(12, None)                                              # 0.96 -> 0, and no floor lifts it
    assert tiny["state"] == "unread" and "no floor lifts it" in tiny["why"]
    assert du.compute(FIXTURE_POOL, None, "unreadable")["state"] == "unread"  # host.env unreadable (law 4)


def test_the_floor_is_read_by_name_from_the_environment(day, monkeypatch):
    monkeypatch.setenv(dp.UNIT_FLOOR_ENV, str(FIXTURE_FLOOR))
    rec, created = du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL_SMALL))
    assert created and (rec["state"], rec["unit_usd"]) == ("read", FIXTURE_FLOOR)
    assert rec["floor_name"] == "SP_UNIT_FLOOR_USD" and "applied" in rec["floor_state"]


def test_order_lines_on_the_days_unit_and_the_half_unit_is_the_half_fraction(day):
    rec, _ = du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL), role="laptop")
    assert rec["unit_usd"] == FIXTURE_UNIT and rec["pool_usd"] == FIXTURE_POOL
    doc = dp.annotate(play_doc(), now=NOW)
    d = doc["predictions"][0]["desk"]
    assert (d["call"], d["units"]) == ("PLAY", 1)
    assert d["order"]["unit"] == f"1u = ${FIXTURE_UNIT}"                    # the label's shape, "1u = $X", as before
    assert d["order"]["contracts"] == int(FIXTURE_UNIT / 0.55) == 1794       # floor(units x unit / limit)
    assert d["order"]["text"] == "BUY YES T-FIX-HOME @ 0.55 × 1794"
    assert doc["desk_meta"]["unit"] == {"state": "read", "et_date": "2026-10-11", "label": f"1u = ${FIXTURE_UNIT}",
                                        "why": None, "fraction": 0.08, "half_fraction": 0.04,
                                        "floor_name": "SP_UNIT_FLOOR_USD"}
    # the half-unit cohort (0 < exec < 4): the same PLAY at a 0.59 ask is halved by the exec gate, 0.5u of the unit
    half = dp.annotate(play_doc(ask=0.59, bid=0.58, legs={"HOME": {"ticker": "T-FIX-HOME", "bid": 0.58,
                                                                    "ask": 0.59}}), now=NOW)["predictions"][0]["desk"]
    assert half["units"] == 0.5 and "exec < 4pp half units" in half["tags"]
    assert half["order"]["contracts"] == int(0.5 * FIXTURE_UNIT / 0.59) == 836
    assert abs(0.5 * FIXTURE_UNIT - dp.HALF_UNIT_FRACTION * FIXTURE_POOL) < 1     # 4% of the pool, to the dollar (J11)


# ================================================================================================ once a day ==

def test_the_unit_is_read_once_a_day_and_a_pool_change_mid_day_changes_nothing(day):
    first, created = du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL))
    assert created and first["unit_usd"] == FIXTURE_UNIT
    calls = []
    later, created = du.day_unit(NOW + timedelta(hours=6), read_pool=lambda: calls.append(1) or pool_of(
        FIXTURE_POOL_LATER)())
    assert not created and calls == [] and later == first                   # the file, never the pool again
    doc = dp.annotate(play_doc(), now=NOW + timedelta(minutes=20))           # a later page that day reads the file
    assert doc["predictions"][0]["desk"]["order"]["unit"] == f"1u = ${FIXTURE_UNIT}"
    files = sorted(p.name for p in day.iterdir())
    assert files == ["desk_unit_2026-10-11.json"]                            # one file; no temporary name left
    assert json.loads((day / files[0]).read_text())["kind"] == "desk_unit_v1"


def test_the_et_day_keys_the_file_not_the_utc_day(day):
    late = datetime(2026, 10, 12, 3, 30, tzinfo=timezone.utc)                # 23:30 ET on 2026-10-11
    du.day_unit(late, read_pool=pool_of(FIXTURE_POOL))
    assert (day / "desk_unit_2026-10-11.json").exists() and du.et_date(late) == DAY


def test_a_racing_writer_finds_the_first_record(day, monkeypatch):
    rec, _ = du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL))
    with monkeypatch.context() as m:
        m.setattr(du, "read_day", lambda d: None)                            # a second process saw no file yet
        other = du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL_LATER))
    assert du.read_day(DAY)["unit_usd"] == FIXTURE_UNIT and other[1] is False  # os.link refused the second name


# ======================================================================================= unread: no order line ==

def test_a_failed_read_writes_nothing_and_the_next_page_reads_again_180_item_4(day):
    """ARCHITECT 2026-10-30 10:15 ET, addendum 180 item 4: "the unit file for the ET date is written by the FIRST page
    that day whose read succeeds; a page that finds no file for its ET date makes the read itself and writes the file
    on success; a page that finds the file never rewrites it ... A page whose own read fails and finds no file says
    "unit unread — no order"." A failed read costs that page its order line, not the day's."""
    rec, created = du.day_unit(NOW, read_pool=failed())
    assert not created and rec["state"] == "unread" and rec["unit_usd"] is None
    assert rec["why"] == "the balance read answered HTTP 503"
    assert du.read_day(DAY) is None                                   # nothing written: the day is not unread
    doc = dp.annotate(play_doc(), now=NOW)                            # this page: its own read failed, no file
    d = doc["predictions"][0]["desk"]
    assert d["call"] == "PLAY" and d["order"]["text"] is None and d["order"]["contracts"] is None
    assert d["order"]["why"] == "unit unread — no order" and d["order"]["unit"] == "unit unread"
    # 183 item 2(3): the export finds no file for its own ET date and makes the read itself (here the real read,
    # POOL_FIELDS None: unread, nothing written), never a unit
    assert doc["desk_meta"]["unit"]["state"] == "unread" and du.read_day(DAY) is None
    again, created = du.day_unit(NOW + timedelta(hours=1), read_pool=pool_of(FIXTURE_POOL))
    assert created and again["state"] == "read" and again["unit_usd"] == FIXTURE_UNIT   # the next page reads, writes
    later, created = du.day_unit(NOW + timedelta(hours=2), read_pool=failed())
    assert not created and later["unit_usd"] == FIXTURE_UNIT          # the file stands; never re-read, never rewritten
    sized = dp.annotate(play_doc(), now=NOW)["predictions"][0]["desk"]["order"]          # same ET day, the file
    assert sized["text"] and sized["why"] is None


@pytest.mark.parametrize("got,why", [
    ({"ok": True, "pool_usd": 0}, "the pool is not positive"),
    ({"ok": True, "pool_usd": "not a number"}, "the pool is not a number"),
    ({"ok": False, "why": "key 'fixture_cash_key' is missing from the balance response"}, "is missing"),
    ({"ok": False, "why": "key 'fixture_cash_key' of the balance response is not a number"}, "is not a number"),
    ({"ok": False, "why": kpool.NOT_ENUMERATED}, "not enumerated"),
])
def test_empty_is_not_zero_180_item_5(day, monkeypatch, got, why):
    """Addendum 180 item 5: "an empty field-name constant, a missing key, a non-numeric value, or a pool of zero each
    yield UNREAD, never a zero unit and never the floor; the floor applies only to a unit computed from a successful
    read." The floor is set here: it is never applied to any of them, and nothing is written."""
    monkeypatch.setenv(dp.UNIT_FLOOR_ENV, str(FIXTURE_FLOOR))
    rec, created = du.day_unit(NOW, read_pool=lambda: dict(got))
    assert rec["state"] == "unread" and rec["unit_usd"] is None and why in rec["why"]
    assert not created and du.read_day(DAY) is None


def test_the_missing_key_and_non_numeric_value_come_from_the_read_itself():
    miss = kpool.read_pool(fetch=lambda path, params=None: (200, {"other": "1.00"}))
    bad = kpool.read_pool(fetch=lambda path, params=None: (200, {"balance_dollars": "n/a"}))
    assert miss["ok"] is False and miss["why"] == "key 'balance_dollars' is missing from the balance response"
    assert bad["ok"] is False and bad["why"] == "key 'balance_dollars' of the balance response is not a dollar string"


def test_the_et_date_is_new_york_not_the_utc_day():
    late = datetime(2026, 10, 12, 2, 30, tzinfo=timezone.utc)        # 22:30 ET on 2026-10-11
    assert du.et_date(late) == date(2026, 10, 11)


def test_an_unread_day_prices_the_exec_gate_at_the_reference_fill_and_labels_it(day):
    """J1: on an unread day the exec gate prices its fee at the reference fill (10 contracts per 1u), so its calls are
    the contracts basis's, and desk.exec's counts are labelled the fee's basis, never an order."""
    du.day_unit(NOW, read_pool=failed())
    docs = [play_doc(), play_doc(ask=0.59, bid=0.58, legs={"HOME": {"ticker": "T-FIX-HOME", "bid": 0.58,
                                                                     "ask": 0.59}})]
    unread = [dp.annotate(json.loads(json.dumps(x)), now=NOW)["predictions"][0]["desk"] for x in docs]
    with dp.unit_override(dp.LEGACY_CONTRACTS_BASIS):
        pinned = [dp.annotate(json.loads(json.dumps(x)), now=NOW)["predictions"][0]["desk"] for x in docs]
    for u, p in zip(unread, pinned):
        assert (u["call"], u["units"], u["tags"], u["exec"]["edge_pp"]) == (p["call"], p["units"], p["tags"],
                                                                             p["exec"]["edge_pp"])
        assert u["order"]["text"] is None and p["order"]["text"]
        assert u["exec"]["contracts_basis"] == dp.UNIT_REFERENCE_FILL_TEXT == "reference fill, no order (unit unread)"
        assert "contracts_basis" not in p["exec"]                           # a sized day: the count is the order's


def test_j1_the_read_can_move_a_borderline_tier(day):
    """J1, RULED as built (ARCHITECT 2026-10-30 11:20 ET, addendum 182 item 2): "The exec edge is the edge of the order
    the Desk would place; with no order (unread) the reference fill (ORDER_UNIT_CONTRACTS per 1u, the pre-v1.2 basis) is
    the basis, labelled contracts_basis on the row ... Code pins the synthetic receipt (the 0.55 ask at 4pp, both bases'
    tier) as a test so the dependence is visible on the record, never silent." The fee rounds per fill of the order's
    own count (#87 v1.1 (h)): at the 0.55 ask the row's exec edge is at 4pp or above on the reference fill (a 1u PLAY,
    unread: no order placed) and below 4pp on a read day's synthetic unit (a 0.5u PLAY). The thresholds stand."""
    legs = {"HOME": {"ticker": "T-FIX-HOME", "bid": 0.54, "ask": 0.55}}
    doc = {"sport": "nfl", "predictions": [dict(nfl("FIX", 0.6071, 0.55, bid=0.54, ask=0.55, legs=legs),
                                                match_id=7001)]}
    with dp.unit_override(dp.unit_unread(dp.UNIT_UNREAD_TEXT)):
        u = dp.annotate(json.loads(json.dumps(doc)), now=NOW)["predictions"][0]["desk"]
    with dp.unit_override(dp.unit_basis_usd(FIXTURE_UNIT)):
        r = dp.annotate(json.loads(json.dumps(doc)), now=NOW)["predictions"][0]["desk"]
    assert (u["call"], u["units"]) == ("PLAY", 1) and u["exec"]["edge_pp"] >= 4
    assert (r["call"], r["units"]) == ("PLAY", 0.5) and r["exec"]["edge_pp"] < 4
    assert u["exec"]["contracts_basis"] == dp.UNIT_REFERENCE_FILL_TEXT and "contracts_basis" not in r["exec"]
    assert u["order"]["text"] is None and r["order"]["text"]           # the unread day places nothing


def test_j3_a_floor_above_the_pool_is_unread_never_a_whole_pool_unit():
    """Addendum 182 item 3: "A floor above floor(pool) makes the day UNREAD, the reason named ("floor above the pool")
    ... A floor above the fraction's unit but within the pool applies as the operator's hand-set minimum, said by name
    as built." Synthetic figures only."""
    over = du.compute(FIXTURE_POOL_SMALL, str(FIXTURE_POOL_SMALL + 1))
    assert over["state"] == "unread" and "floor above the pool" in over["why"] and "unit_usd" not in over
    within = du.compute(FIXTURE_POOL_SMALL, str(FIXTURE_FLOOR))
    assert within["state"] == "read" and within["unit_usd"] == FIXTURE_FLOOR
    assert within["floor_state"].endswith("(the floor binds: the unit is above UNIT_FRACTION of the pool)")
    whole = du.compute(FIXTURE_POOL_SMALL, str(FIXTURE_POOL_SMALL))      # exactly the pool: within it, applies
    assert whole["state"] == "read"


def test_the_day_file_is_the_owners_alone_0600(day):
    """Codex on #734: the day file holds the day's unit (and the pool on the laptop), so it is created 0600."""
    import os
    import stat
    old = os.umask(0o022)
    try:
        du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL), role="laptop")
    finally:
        os.umask(old)
    assert stat.S_IMODE((day / "desk_unit_2026-10-11.json").stat().st_mode) == 0o600


def test_yesterdays_unit_is_never_read_for_today(day):
    du.day_unit(NOW - timedelta(days=1), read_pool=pool_of(FIXTURE_POOL))
    assert (day / "desk_unit_2026-10-10.json").exists()
    d = dp.annotate(play_doc(), now=NOW)["predictions"][0]["desk"]
    assert d["order"]["why"] == dp.UNIT_UNREAD_TEXT and d["order"]["text"] is None
    assert dp.day_unit_basis(NOW)["state"] == "absent"


def test_a_file_that_is_not_the_days_record_is_unread(day):
    day.mkdir(parents=True)
    p = day / "desk_unit_2026-10-11.json"
    for body in ("not json", json.dumps({"kind": "desk_unit_v1", "et_date": "2026-10-10", "state": "read",
                                         "unit_usd": FIXTURE_UNIT}),
                 json.dumps({"kind": "desk_unit_v1", "et_date": "2026-10-11", "state": "read", "unit_usd": "x"})):
        p.write_text(body)
        assert du.read_day(DAY)["state"] == "unread"
        assert dp.day_unit_basis(NOW)["mode"] == "unread"


def test_a_data_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "UNIT_PIN", None)
    monkeypatch.setenv(du.DIR_ENV, str(tmp_path / "data" / "logs"))
    with pytest.raises(du.UnitPathRefused, match="law 5"):
        du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL))
    assert not (tmp_path / "data").exists()
    u = dp.day_unit_basis(NOW)
    assert u["mode"] == "unread" and "law 5" in u["why"]
    assert dp.order_line({"src": {"kalshi_legs": LEGS}, "threeWay": False}, "HOME", 1)["why"] == dp.UNIT_UNREAD_TEXT


# ================================================================================================ the pool read ==

def test_pool_fields_are_the_names_on_732_and_addenda_186_187():
    """Addendum 186 items 2-3 and 187 items 1-3: the cash is balance_dollars (never the int balance or
    portfolio_value; balance_breakdown not read), the positions term is market_positions[].market_exposure_dollars
    ("Cost of the aggregate market position in dollars"), paged by the documented cursor / limit, count_filter=position,
    settlement_status omitted, the 20-page cap."""
    assert kpool.POOL_FIELDS == {
        "cash": "balance_dollars",
        "positions": {"path": "/portfolio/positions", "list": "market_positions", "cost": "market_exposure_dollars",
                      "cursor": "cursor", "cursor_param": "cursor", "limit_param": "limit",
                      "params": {"count_filter": "position"}}}
    assert kpool.MAX_PAGES == 20 and kpool.PAGE_LIMIT == 100 and kpool.BALANCE_PATH == "/portfolio/balance"
    assert kpool.read_pool(fields=None)["why"] != kpool.NOT_ENUMERATED     # the names are enumerated now


def test_pool_fields_none_still_reads_unread_and_makes_no_request(monkeypatch):
    monkeypatch.setattr(kpool, "POOL_FIELDS", None)
    got = kpool.read_pool(fetch=lambda *a, **k: pytest.fail("no request without the names"))
    assert got == {"ok": False, "pool_usd": None, "why": "the balance response's key names are not enumerated (#732)"}


def test_no_key_through_the_day_unit_and_the_cli_is_unread_and_writes_nothing(day, monkeypatch):
    from click.testing import CliRunner

    import cli
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    out = CliRunner().invoke(cli.cli, ["desk-unit"])
    assert out.exit_code == 0, out.output
    assert du.read_day(du.et_date(datetime.now(timezone.utc))) is None   # 180 item 4: a failed read writes nothing
    assert f"{dp.UNIT_UNREAD_TEXT}: no Kalshi API key configured" in out.output
    assert re.search(r"^DESK-UNIT state=unread et_date=\d{4}-\d\d-\d\d new=no$", out.output, re.M)


# The posted shape (#732's receipt), every value a SYNTHETIC digit pattern (item 5): the balance's int fields and
# portfolio_value carry figures the read must never use; event_positions carries costs it must never add.
FIXTURE_CASH_DOLLARS = "12345.000000"          # synthetic
FIXTURE_COSTS_DOLLARS = ("111.000000", "222.000000")   # synthetic
FIXTURE_NEVER = "99999.000000"                 # synthetic: in a field the pool never reads


def balance_body(cash=FIXTURE_CASH_DOLLARS):
    return {"balance": 7777777, "balance_breakdown": [{"balance": FIXTURE_NEVER, "exchange_index": 0}],
            "balance_dollars": cash, "portfolio_value": 8888888, "updated_ts": 1}


def market(cost):
    return {"exchange_index": 0, "fees_paid_dollars": FIXTURE_NEVER, "last_updated_ts": "2026-10-30T00:00:00Z",
            "market_exposure_dollars": cost, "position_fp": "10.00", "realized_pnl_dollars": FIXTURE_NEVER,
            "ticker": "T-FIX", "total_traded_dollars": FIXTURE_NEVER}


def event():
    return {"event_exposure_dollars": FIXTURE_NEVER, "event_ticker": "E-FIX", "fees_paid_dollars": FIXTURE_NEVER,
            "realized_pnl_dollars": FIXTURE_NEVER, "total_cost_dollars": FIXTURE_NEVER,
            "total_cost_shares_fp": "10.00"}


def fake_fetch(pages, seen=None, balance=None):
    def fetch(path, params=None):
        (seen if seen is not None else []).append((path, dict(params or {})))
        if path == kpool.BALANCE_PATH:
            return 200, balance or balance_body()
        return 200, pages[int((params or {}).get("cursor") or 0)]
    return fetch


def two_pages():
    return [{"cursor": "1", "market_positions": [market(FIXTURE_COSTS_DOLLARS[0])], "event_positions": [event()]},
            {"cursor": "", "market_positions": [market(FIXTURE_COSTS_DOLLARS[1])], "event_positions": [event()]}]


def test_the_pool_is_balance_dollars_plus_market_exposure_over_every_page():
    seen = []
    got = kpool.read_pool(fetch=fake_fetch(two_pages(), seen))
    assert got == {"ok": True, "pool_usd": Decimal("12678"), "why": None}   # 12345 + 111 + 222, Decimal dollars
    assert [p for p, _ in seen] == [kpool.BALANCE_PATH, "/portfolio/positions", "/portfolio/positions"]
    assert seen[0][1] == {}                                       # no exchange_index: the total across the indexes
    assert [q for _, q in seen[1:]] == [{"count_filter": "position", "limit": 100},
                                        {"count_filter": "position", "limit": 100, "cursor": "1"}]


def test_the_breakdown_is_not_read_and_its_absence_never_unreads_the_day():
    """187 item 2: balance_dollars is the total when exchange_index is omitted; the breakdown is not read."""
    body = balance_body()
    del body["balance_breakdown"]
    got = kpool.read_pool(fetch=fake_fetch(two_pages(), balance=body))
    assert got["ok"] is True and got["pool_usd"] == Decimal("12678")


def test_the_int_fields_are_never_the_money_unit():
    """186 item 2: never the int fields (balance, portfolio_value): a balance_dollars given as an int is UNREAD."""
    for v in (1234500, 12345.0, True, None):
        got = kpool.read_pool(fetch=fake_fetch(two_pages(), balance={**balance_body(), "balance_dollars": v}))
        assert got == {"ok": False, "pool_usd": None,
                       "why": "key 'balance_dollars' of the balance response is not a dollar string"}
    pages = two_pages()
    pages[1]["market_positions"][0]["market_exposure_dollars"] = 22200
    got = kpool.read_pool(fetch=fake_fetch(pages))
    assert got["ok"] is False and got["why"] == ("key 'market_exposure_dollars' of the positions response is not a "
                                                 "dollar string")


def test_a_page_loop_past_twenty_pages_is_unread_never_a_partial_pool():
    pages = [{"cursor": str(i + 1), "market_positions": [market("1.000000")], "event_positions": []}
             for i in range(25)]
    seen = []
    got = kpool.read_pool(fetch=fake_fetch(pages, seen))
    assert got == {"ok": False, "pool_usd": None, "why": "the positions read did not end within 20 pages"}
    assert len(seen) == 1 + 20
    twenty = [{"cursor": str(i + 1) if i < 19 else "", "market_positions": [market("1.000000")],
               "event_positions": []} for i in range(20)]
    assert kpool.read_pool(fetch=fake_fetch(twenty))["pool_usd"] == Decimal("12365")    # 20 pages: read whole


@pytest.mark.parametrize("fetch, why", [
    (lambda p, q=None: (200, {"other": "1.00"}), "key 'balance_dollars' is missing from the balance response"),
    (lambda p, q=None: (401, {}), "the balance read answered HTTP 401"),
    (lambda p, q=None: (None, "no key configured"), "the balance read: no key configured"),
    (lambda p, q=None: (200, {"balance_dollars": "NaN"}), "key 'balance_dollars' of the balance response is not a "
                                                          "dollar string"),
    (lambda p, q=None: (_ for _ in ()).throw(TimeoutError()), "the balance read failed (TimeoutError)"),
    (lambda p, q=None: ((200, balance_body()) if p == kpool.BALANCE_PATH else (200, {"cursor": ""})),
     "key 'market_positions' is missing from the positions response"),
    (lambda p, q=None: ((200, balance_body()) if p == kpool.BALANCE_PATH else (503, {})),
     "the positions read answered HTTP 503"),
], ids=["missing-key", "http-401", "no-key", "nan", "timeout", "no-list", "positions-503"])
def test_every_failure_is_unread_never_a_partial_pool(fetch, why):
    got = kpool.read_pool(fetch=fetch)
    assert got == {"ok": False, "pool_usd": None, "why": why}


def test_a_spec_not_in_the_documented_shape_is_unread():
    good = kpool.POOL_FIELDS
    for spec in ({}, {"cash": "c"}, {**good, "per_dollar": 100}, {**good, "positions": {"path": "/p"}},
                 {**good, "positions": {k: v for k, v in good["positions"].items() if k != "params"}},
                 {**good, "positions": {**good["positions"], "params": {"count_filter": 1}}}):
        assert kpool.read_pool(fetch=lambda *a: pytest.fail("no request"), fields=spec)["ok"] is False


def test_the_read_is_get_only_through_the_probes_client():
    kp = kpool._probe()
    with pytest.raises(kp.ReadOnly, match="read-only"):
        kp.Client("https://example.invalid/trade-api/v2").request("POST", kpool.BALANCE_PATH)


@pytest.mark.parametrize("role", ["host", "not laptop", None])
def test_a_day_file_not_written_by_the_laptop_holds_no_pool_figure(day, role):
    """Item 5: the pool's dollar value goes in the laptop's logs only; the host's day file keeps the unit (item 3)."""
    rec, created = du.day_unit(NOW, read_pool=pool_of(FIXTURE_POOL), role=role)
    on_disk = json.loads(du.path_for(DAY).read_text())
    assert created and rec["pool_usd"] is None and on_disk["pool_usd"] is None
    assert on_disk["unit_usd"] == FIXTURE_UNIT and str(FIXTURE_POOL) not in du.path_for(DAY).read_text()


# ================================================================================================ the cli read ==

@pytest.mark.parametrize("role, figures", [("laptop", True), ("host", False)])
def test_desk_unit_prints_figures_on_the_laptop_only(day, monkeypatch, role, figures):
    from click.testing import CliRunner

    import cli
    import config
    monkeypatch.setattr(config, "PROCESS_ENV_ROLE", role)               # 183 item 2(1): the process's own role
    monkeypatch.setattr(kpool, "read_pool", pool_of(FIXTURE_POOL))
    out = CliRunner().invoke(cli.cli, ["desk-unit"]).output
    assert "UNIT_FRACTION 0.08 · HALF_UNIT_FRACTION 0.04 · floor SP_UNIT_FLOOR_USD" in out
    assert (str(FIXTURE_UNIT) in out) is figures and ("12,345.00" in out) is figures
    assert "DESK-UNIT state=read" in out
    again = CliRunner().invoke(cli.cli, ["desk-unit"]).output                  # the day file: new=no
    assert "new=no" in again and "the day file (read once a day)" in again


# ============================================================================ addendum 183 item 2 (Codex round 2) ==

def test_183_the_role_comes_only_from_the_process_environment(day, monkeypatch, tmp_path):
    """183 item 2(1): "The role comes only from the environment the process runs with (host.env through systemd),
    never from a file the code opens; with no role in the environment the role is unknown and every figure is refused
    (law 4)." A host.env absent and a checkout .env (or os.environ after load_dotenv) saying laptop: no figure."""
    import config
    monkeypatch.setattr(config, "PROCESS_ENV_ROLE", None)
    monkeypatch.setenv(dp.ROLE_ENV, "laptop")                           # what load_dotenv would put there from .env
    monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "absent.env"))
    assert du.figures_allowed() is False
    for role, ok in (("laptop", True), (" laptop ", True), ("host", False), ("", False), ("Laptop", False)):
        monkeypatch.setattr(config, "PROCESS_ENV_ROLE", role)
        assert du.figures_allowed() is ok, role


@pytest.mark.parametrize("bad", [True, False, 1.5, "987", 0, -5, None])
def test_183_a_bool_or_any_non_int_unit_is_a_malformed_file_read_unread(day, bad):
    """183 item 2(2): "A unit is an int that is not a bool, positive; anything else is a malformed file and the day
    reads UNREAD, named." """
    day.mkdir(parents=True, exist_ok=True)
    du.path_for(DAY).write_text(json.dumps({"kind": "desk_unit_v1", "et_date": DAY.isoformat(), "state": "read",
                                            "unit_usd": bad}))
    rec = du.read_day(DAY)
    assert rec["state"] == "unread" and "unit file malformed" in rec["why"]
    assert dp.day_unit_basis(NOW)["state"] == "unread"


def test_183_a_run_crossing_midnight_et_exports_on_its_own_dates_unit(day, monkeypatch):
    """183 item 2(3): a run starts 23:50 ET (its pre-step reads and writes that date's file) and exports 00:10 ET: the
    export finds no file for its own ET date, makes the read itself and writes that date's file; the earlier read is
    not passed forward. Synthetic pools."""
    start = datetime(2026, 10, 31, 3, 50, tzinfo=timezone.utc)          # 23:50 ET on 2026-10-30 (EDT)
    export = datetime(2026, 10, 31, 4, 10, tzinfo=timezone.utc)         # 00:10 ET on 2026-10-31
    rec, created = du.day_unit(start, read_pool=pool_of(FIXTURE_POOL))
    assert created and rec["et_date"] == "2026-10-30"
    monkeypatch.setattr(kpool, "read_pool", pool_of(FIXTURE_POOL_SMALL))
    WALL[0] = export                                                    # the export runs at 00:10 ET, wall time
    doc = dp.annotate(play_doc(), now=export)
    assert doc["desk_meta"]["unit"]["et_date"] == "2026-10-31" and doc["desk_meta"]["unit"]["state"] == "read"
    assert du.read_day(date(2026, 10, 31))["unit_usd"] == 88             # floor(0.08 x FIXTURE_POOL_SMALL), its own
    assert du.read_day(date(2026, 10, 30))["unit_usd"] == FIXTURE_UNIT   # the earlier date's file is untouched


# ============================================================================================ the depth line ==

def test_the_depth_line_text_and_that_it_is_unwired():
    """Item 7's line is its text and arithmetic only: no orderbook read exists and no depth field's name has been read
    from a real response (law 1), so order_line reads no depth from a leg under any key (#732, needs-ruling)."""
    assert dp.depth_note(10, 7) == "size over the ask's depth: 7 contracts"
    assert dp.depth_note(10, 10) is None and dp.depth_note(10, 50) is None
    assert dp.depth_note(None, 7) is None and dp.depth_note(10, None) is None and dp.depth_note(10, True) is None
    assert not hasattr(dp, "LEG_DEPTH_KEY")                                  # no guessed key name
    for extra in ({}, {"ask_size": 1, "bid_size": 1}, {"yes_ask_size_fp": 1, "yes_bid_size_fp": 1}):
        for target in ("HOME", "AWAY"):
            o = dp.order_line({"src": {"kalshi_legs": {"HOME": dict(LEGS["HOME"], **extra)}}, "threeWay": False},
                              target, 1)
            assert o["text"] and "depth" not in o and "depth_note" not in o


# ================================================================================================ the pages ==

def _closing_rows(doc):
    return mc.desk_rows(doc, {7001}, NOW - timedelta(minutes=5), fam="NFL")


def test_the_closing_page_says_unit_unread_verbatim(day):
    du.day_unit(NOW, read_pool=failed())
    rows = _closing_rows(dp.annotate(play_doc(), now=NOW))
    _, body, _ = mc.page_text("NFL", NOW + timedelta(minutes=45), NOW, rows, {})
    line = next(x for x in body.splitlines() if "PLAY" in x)
    assert "· unit unread — no order ·" in line and "no order: unit unread" not in body
    assert "   order  unit unread — no order" in mc.summary_block(rows[0])


def test_the_closing_page_carries_the_depth_line():
    """The page passes an order's depth_note through as the export wrote it. No export writes one today (the line is
    unwired, #732): the row's note is set here by hand, the page plumbing only."""
    rows = _closing_rows(dp.annotate(play_doc(), now=NOW))
    assert rows[0]["depth_note"] is None
    rows[0]["depth_note"] = dp.depth_note(10, 4)
    _, body, _ = mc.page_text("NFL", NOW + timedelta(minutes=45), NOW, rows, {})
    assert "size over the ask's depth: 4 contracts" in body
    assert "size over the ask's depth: 4 contracts" in mc.summary_block(rows[0])


def test_the_slate_page_says_unit_unread_on_its_own_line():
    _, body = mc.slate_page_text("NFL", DAY, 2, {"PLAY": 1, "PASS": 1}, "exports/x.json", None, unit_unread=True)
    assert body.splitlines()[1] == "unit unread — no order"
    _, read = mc.slate_page_text("NFL", DAY, 2, {"PLAY": 1, "PASS": 1}, "exports/x.json", None)
    assert "unit unread" not in read


def test_the_slate_reads_the_unit_through_the_cli_and_receipts_no_figure(monkeypatch):
    seen = []
    monkeypatch.setattr(mc, "run_step", lambda argv, run_id: seen.append(argv) or (
        0, ["DESK UNIT ...", "DESK-UNIT state=unread et_date=2026-10-11 new=yes"], 0.1))
    assert mc.read_day_unit("RUN") == {"state": "unread", "et_date": "2026-10-11", "new": True, "exit": 0}
    assert seen == [["desk-unit"]]
    monkeypatch.setattr(mc, "run_step", lambda argv, run_id: (1, ["boom"], 0.1))
    assert mc.read_day_unit("RUN")["state"] == "unknown"
    src = (ROOT / "deploy" / "hosting" / "closing.py").read_text().lower()
    for bad in ("trade-api", "/portfolio", "/orders", "kalshi.com", "create_order"):     # C8 stands
        assert bad not in src


def test_an_unread_slate_day_pages_the_line(box, monkeypatch):
    from tests.test_slate_run import et, slate_pages, the_day, tick
    the_day(box, monkeypatch)
    monkeypatch.setattr(mc, "read_day_unit", lambda run_id: {"state": "unread", "et_date": "2026-10-18", "new": True,
                                                             "exit": 0})
    t = et(6, 55)
    while not slate_pages(box) and t <= et(8, 0):
        assert tick(t) == 0
        t += timedelta(minutes=1)
    (p,) = slate_pages(box)
    assert p["body"].splitlines()[1] == "unit unread — no order"
    (s,) = [r for r in mc.c.receipts_path().read_text().splitlines() if '"kind": "slate"' in r]
    assert json.loads(s)["unit"] == {"state": "unread", "et_date": "2026-10-18", "new": True, "exit": 0}


# ============================================================================== no dollar figure in the repo ==

SYNTHETIC = re.compile(r"^(?:(\d)\1*|0?1?2?3?4?5?6?7?8?9?|9?8?7?6?5?4?3?2?1?0?)0*$")


def test_every_fixture_figure_is_a_synthetic_digit_pattern():
    """Item 5: no test fixture is a plausible real figure. Each FIXTURE_* figure in the unit's tests is a run of
    digits (12345, 54321, 987) or one digit repeated (1111, 111, 11), with trailing zeros for cents; a `_dollars`
    string (addendum 186 item 2) is the same pattern with its point ("12345.000000")."""
    import tests.test_desk_exec_addendum as ea
    import tests.test_desk_order_line as ol
    figures = [v for m in (globals(), vars(ea), vars(ol)) for k, v in m.items() if k.startswith("FIXTURE_")]
    flat = [x for v in figures for x in (v if isinstance(v, tuple) else (v,))]
    assert len(flat) >= 10
    for v in flat:
        digits = str(v).replace(".", "", 1) if isinstance(v, str) else str(v)
        assert isinstance(v, (int, str)) and not isinstance(v, bool) and SYNTHETIC.match(digits), v


def test_no_file_sets_a_unit_figure():
    """The floor's and the retired unit's VALUES are set by hand in host.env and the laptop's .env, never in the
    checkout (item 4: "value never in the repo")."""
    pat = r"SP_UNIT_(FLOOR_)?USD[\"']?\s*[=:,]\s*[\"']?[0-9]"
    got = subprocess.run(["git", "-C", str(ROOT), "grep", "--untracked", "-nIE", pat, "--", ".",
                          ":(exclude)tests/test_desk_unit_fraction.py"], capture_output=True, text=True)
    assert got.returncode == 1 and got.stdout == "", got.stdout


# ============================================================== the pre-push review of round three (#734) ==

def test_a_malformed_unit_is_named_by_type_never_by_value(day):
    path = du.path_for(DAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kind": du.KIND, "et_date": DAY.isoformat(), "state": "read",
                                "unit_usd": float(FIXTURE_UNIT)}))
    got = du.read_day(DAY)
    assert got["state"] == "unread" and "unit_usd (float)" in got["why"] and str(FIXTURE_UNIT) not in got["why"]


def test_a_pinned_clock_on_another_et_day_never_reads_the_live_pool(day, monkeypatch):
    """The export's own read is at export time: a document stamped on another ET day (desk-parlays --now, an as-of
    rescore) finds no file and reads absent, never the live pool, and writes nothing."""
    monkeypatch.setattr(kpool, "read_pool", lambda *a, **k: pytest.fail("no live read for another day"))
    past = NOW - timedelta(days=3)                                       # the wall clock stays at NOW
    got = dp.day_unit_basis(past, read=True)
    assert got["mode"] == "unread" and got["state"] == "absent"
    assert du.read_day(du.et_date(past)) is None


def test_the_slate_pages_unread_line_follows_the_exports_own_unit():
    """183 item 2(3): "the slate's earlier read is not passed forward": the page's unread line is the export's own
    desk_meta.unit; only a file carrying no unit falls back to the slate's read."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy" / "hosting"))
    import closing as cl
    read, unread = {"state": "read"}, {"state": "unread"}
    assert cl.export_unit_unread({"desk_meta": {"unit": {"mode": "usd"}}}, unread) is False
    assert cl.export_unit_unread({"desk_meta": {"unit": {"mode": "unread"}}}, read) is True
    assert cl.export_unit_unread({"desk_meta": {}}, unread) is True and cl.export_unit_unread({}, read) is False


@pytest.mark.parametrize("v", ["1e3", " 12.000000", "12.1234567", "12.", ".5", "+1.00", "", "NaN"])
def test_only_a_fixed_point_dollar_string_is_read(v):
    got = kpool.read_pool(fetch=fake_fetch(two_pages(), balance={**balance_body(), "balance_dollars": v}))
    assert got["ok"] is False and got["why"] == "key 'balance_dollars' of the balance response is not a dollar string"


def test_a_positions_page_without_its_cursor_key_is_unread():
    pages = two_pages()
    del pages[0]["cursor"]
    got = kpool.read_pool(fetch=fake_fetch(pages))
    assert got == {"ok": False, "pool_usd": None, "why": "key 'cursor' is missing from the positions response"}


def test_the_process_role_is_captured_before_any_dotenv_load():
    """Addendum 183 item 2(1): the figures' role is the environment the process started with, so config captures it
    before load_dotenv can fill it from the checkout's .env."""
    src = (Path(__file__).resolve().parent.parent / "config.py").read_text()
    assert src.index("PROCESS_ENV_ROLE = os.environ.get(") < src.index("load_dotenv(")
