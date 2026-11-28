"""#1186 (ARCHITECT 2026-11-28 14:05 ET, addendum 590 item 7): the BOOKS line in the closing book-gap receipt, and
one pin as built.

(b) "YES, your BOOKS line in the gap receipt, read-only, files only: the complete count as 0, 1, 2, 3, 4 or more and
absent, the quoted count beside it, the rows under four split by the Desk's call, the unpriced close apart. SCOPE: PL
and NFL, the receipt's two families; "this season" is the family's first closing page on the record."
(c) "With it, ONE PIN AS BUILT: a model PLAY or LADDER is blind to the count, one book against nine. It records
today's behaviour and rules nothing."

Synthetic only: the receipt's own test world (tests/test_closing_book_gap_receipt.py: a throwaway SQLite copy under
tmp_path, never data/), pages written here with invented counts. No network."""
import copy
import json

import pytest

from src.walters import desk_policy as dp
from tests import test_closing_book_gap_receipt as g
from tests.test_bulletin import NOW
from tests.test_bulletin import row as brow

rc = g.rc
SD, ND = g.SD, g.ND


def smarket(n, quoted=None, unpriced=False, kalshi_only=False):
    """A SOCCER market block in export.py's shapes: priced (n >= 1), unpriced and quoted (close_unpriced), or no
    book quoted with a Kalshi block (export.py:710-727, :752-756)."""
    if n == 0 and unpriced:
        return {"selections": {}, "bookmaker_count": 0, "bookmaker_count_quoted": quoted,
                "close_unpriced": {"books_quoted": quoted, "missing": {"bookA": ["DRAW"]}}}
    if n == 0 and kalshi_only:
        return {"selections": {}, "bookmaker_count": 0, "kalshi": {"status": "mismatched", "events": []}}
    sels = {s: {"fair_prob": round(v, 4), "best_price": 6161.0, "best_bookmaker": "SecretBook"}
            for s, v in zip(g.S3, g.F3)}
    return {"selections": sels, "bookmaker_count": n, "bookmaker_count_quoted": n if quoted is None else quoted}


def srow(mid, market, call="PASS", reference="books", **kw):
    r = g.srow(mid, dk=None if call is None else g.desk(call, "HOME", reference, 0.4523), **kw)
    if market is None:
        r.pop("market")
    else:
        r["market"] = market
    return r


def nrow(mid, n, source="1X2", call="PASS", no_market=False):
    r = g.nrow(mid, source=source, dk=g.desk(call, "HOME", "books", 0.6))
    if no_market:
        r["market"] = None
    else:
        r["market"]["bookmaker_count"] = n
    return r


def soccer_rows():
    return [srow(100, smarket(1), "PLAY"),
            srow(101, smarket(2, quoted=7), "LADDER"),
            srow(102, smarket(3), "PASS"),
            srow(103, smarket(0, quoted=2, unpriced=True), "PASS"),
            srow(104, smarket(0, kalshi_only=True), "PASS"),
            srow(105, None, "PASS"),
            srow(106, {**smarket(3), "bookmaker_count": "3"}, "PASS"),     # not a whole number: absent, by cause
            srow(107, smarket(9, quoted=11), "PLAY"),
            srow(108, smarket(1), "PLAY", reference="kalshi_only"),
            srow(109, smarket(2), None),                                     # no desk block
            srow(100, smarket(1), "PLAY", comp="ELC")]                       # another competition: not read


def nfl_rows():
    return [nrow(200, 1, call="PLAY"), nrow(201, 3), nrow(203, 4, source="spread_derived"),
            nrow(202, 0, no_market=True), nrow(204, 6)]


@pytest.fixture
def books_world(tmp_path):
    db = tmp_path / "copy.db"
    g.build_db(db)
    ex = tmp_path / "exports"
    # the FIRST closing page of SOCCER on the record: an earlier start, its row counted (two books)
    g.closing(ex, "2026-11-14T15:00:00", "2026-11-14T14:27:00.000000Z", [srow(90, smarket(2), "PLAY")])
    g.closing(ex, SD + "15:00:00", g.S_EXP, soccer_rows())
    # an EARLIER page of the same start in a dated folder: labelled and out, never counted (its one book unseen)
    g.closing(ex / "2026-11-21", SD + "15:00:00", SD + "14:00:00.000000Z", [srow(110, smarket(1), "PLAY")],
              run_id="run-earlier")
    g.closing(ex, ND + "18:00:00", g.N_EXP, nfl_rows(), fam="NFL")
    return {"db": db, "ex": ex, "tmp": tmp_path}


def books(out, fam):
    return g.summary(out)["families"][fam]["books"]


def lines(out):
    return [ln for ln in out if ln.startswith(("BOOKS (", "    complete count:", "    UNDER FOUR", "    1:", "    2:",
                                               "    3:", "    4 or more:", "    0 (", "    absent:",
                                               "    fair_source not 1X2"))]


# ---- (b) the BOOKS line -----------------------------------------------------------------------------------------

def test_soccer_counts_every_counted_row_from_the_first_closing_page_by_the_complete_count(books_world):
    code, out = g.run(books_world)
    assert code == 0
    b = books(out, "SOCCER")
    assert b["first_page"]["page"] == "closing_SOCCER_2026-11-14T1500Z.json"
    assert b["rows"] == 11                  # 90 (the first page) and the ten PL 2026/27 rows; ELC and the earlier page out
    got = {k: v["rows"] for k, v in b["buckets"].items()}
    assert got == {"0": 2, "1": 2, "2": 3, "3": 1, "4 or more": 1, "absent": 2}
    assert b["buckets"]["absent"]["why"] == {"no market block (no book odds and no Kalshi price: export.py:714)": 1,
                                             "bookmaker_count not a whole number": 1}


def test_the_quoted_count_sits_beside_the_complete_count(books_world):
    _code, out = g.run(books_world)
    b = books(out, "SOCCER")["buckets"]
    assert b["2"]["quoted"] == {"7": 1, "2": 2}
    assert b["4 or more"]["quoted"] == {"11": 1}
    assert b["0"]["quoted"] == {"2": 1, "not on the page": 1}
    assert "    2: rows 3 · games 3 · quoted: 2 2 · 7 1 · desk.call: (no desk block) 1 · LADDER 1 · PLAY 1" in out


def test_the_rows_under_four_are_split_by_the_desks_call(books_world):
    _code, out = g.run(books_world)
    u = books(out, "SOCCER")["under_four"]
    assert u["rows"] == 6 and u["games"] == 6
    assert u["calls"] == {"PLAY": 3, "LADDER": 1, "PASS": 1, "(no desk block)": 1}
    assert u["staked_on_the_books"] == 3        # 108's PLAY is on the kalshi-only reference: not counted here
    assert any(ln.startswith("    UNDER FOUR (1, 2, 3): rows 6 · games 6 · by desk.call: ") and
               ln.endswith("of which PLAY or LADDER on desk.reference 'books' 3") for ln in out)


def test_zero_is_apart_by_cause_the_unpriced_close_named_and_never_a_thin_close(books_world):
    """0 is the page's own count; its two causes print apart: THE UNPRICED CLOSE (quoted, no book complete) and the
    Kalshi-only block (no book quoted). Neither is in the under-four rows."""
    _code, out = g.run(books_world)
    b = books(out, "SOCCER")
    assert b["buckets"]["0"]["why"] == {rc.BOOKS_UNPRICED_WHY: 1, rc.BOOKS_KALSHI_ONLY_WHY: 1}
    assert b["unpriced_close"] == 1
    assert b["under_four"]["rows"] == 6
    line = next(ln for ln in out if ln.startswith("    " + rc.BOOKS_ZERO))
    assert "rows 2 · games 2" in line and rc.BOOKS_UNPRICED_WHY + " 1" in line and rc.BOOKS_KALSHI_ONLY_WHY + " 1" in line


def test_nfl_counts_its_1x2_rows_and_holds_the_spread_fallback_apart(books_world):
    _code, out = g.run(books_world)
    b = books(out, "NFL")
    assert b["first_page"]["page"] == "closing_NFL_2026-11-22T1800Z.json"
    got = {k: v["rows"] for k, v in b["buckets"].items()}
    assert got == {"0": 0, "1": 1, "2": 0, "3": 1, "4 or more": 1, "absent": 1, rc.BOOKS_NOT_1X2: 1}
    assert b["buckets"][rc.BOOKS_NOT_1X2]["why"] == {"fair_source 'spread_derived'": 1}
    assert b["buckets"]["absent"]["why"] == {"no market block (on NFL: neither a 1X2 consensus nor the spread "
                                             "fallback; an unpriced close among them, not told apart)": 1}
    assert b["unpriced_close"] is None         # cannot be told from an NFL page: no count is given
    line = next(ln for ln in out if ln.startswith("    " + rc.BOOKS_ZERO) and rc.BOOKS_NFL_UNPRICED in ln)
    assert "by cause" not in line
    assert b["buckets"]["1"]["quoted"] == {"not on the page": 1}       # NFL pages carry no quoted count
    assert b["under_four"]["calls"] == {"PLAY": 1, "PASS": 1}


def test_the_line_is_files_only_and_stands_outside_the_stamped_window(books_world):
    """Files only: the count reads the page alone. On a copy with no stamp column no family has a first stamped row
    and every row is out of the gap's window (532 item 4 #7), yet the BOOKS line is the same, row for row."""
    _code, out = g.run(books_world)
    bare = books_world["tmp"] / "bare.db"
    g.build_db(bare, stamp=False)
    code2, out2 = g.run(books_world, db=bare)
    assert code2 == 0
    s2 = g.summary(out2)["families"]["SOCCER"]
    assert s2["in_window"] == 0 and s2["out_no_stamped_row"] == 11
    for fam in ("SOCCER", "NFL"):
        assert books(out2, fam) == books(out, fam)
    assert lines(out2) == lines(out)


def test_under_a_bound_the_first_page_says_it_is_the_bounds_and_an_undecided_start_is_named(books_world):
    """A run bounded by --from prints the first page IN THE BOUND, saying so; a start whose latest page cannot be told
    is out of the count and named."""
    ex = books_world["ex"]
    g.closing(ex, SD + "12:30:00", SD + "11:57:00.000000Z", [srow(110, smarket(1), "PLAY")], run_id="run-a")
    g.closing(ex / "2026-11-20", SD + "12:30:00", SD + "11:57:00.000000Z", [srow(110, smarket(1), "PLAY")],
              run_id="run-b")
    _code, out = g.run(books_world, "--from", "2026-11-20T00:00:00Z")
    b = books(out, "SOCCER")
    assert b["bounded"] is True and b["undecided_starts_out"] == 1
    assert b["first_page"]["page"] == "closing_SOCCER_2026-11-21T1500Z.json"
    assert b["rows"] == 10                     # the 11-14 page is outside the bound; the undecided start is out
    head = next(ln for ln in out if ln.startswith("BOOKS (590 item 7(b); #1186)") and "SOCCER" in ln)
    assert "in this run's bound" in head and "starts whose latest page cannot be told, out: 1" in head
    _code, out = g.run(books_world)
    assert "on the record" in next(ln for ln in out if ln.startswith("BOOKS (590 item 7(b); #1186)") and "SOCCER" in ln)


def test_the_never_read_fields_stay_off_the_console(books_world):
    _code, out = g.run(books_world)
    text = "\n".join(out)
    for s in g.SENTINELS:
        assert s not in text


def test_no_counted_page_prints_its_own_line(tmp_path):
    db = tmp_path / "copy.db"
    g.build_db(db)
    ex = tmp_path / "exports"
    g.closing(ex, ND + "18:00:00", g.N_EXP, nfl_rows(), fam="NFL")
    code, out = g.run({"ex": ex, "db": db})
    assert code == 0
    assert "BOOKS (590 item 7(b)), files only: no counted SOCCER page, so no first closing page and no row" in out
    assert books(out, "SOCCER") == {"rows": 0, "first_page": None, "bounded": False, "undecided_starts_out": 0}


@pytest.mark.parametrize("v, want", [(0, "0"), (1, "1"), (3, "3"), (4, "4 or more"), (40, "4 or more"),
                                     (True, "absent"), (1.0, "absent"), (-1, "absent"), (None, "absent"),
                                     ("2", "absent")])
def test_only_a_whole_non_negative_count_takes_a_bucket(v, want):
    assert rc.books_of("SOCCER", {"market": {"bookmaker_count": v}})["bucket"] == want


def test_the_line_is_in_the_definitions_printed_on_every_run(books_world):
    _code, out = g.run(books_world)
    assert any(ln.startswith("THE BOOKS LINE (590 item 7(b)), files only:") for ln in out)
    assert lines(out)                          # the family lines print


# ---- (c) ONE PIN AS BUILT: the model engine is blind to the count ------------------------------------------------

def _desks(rows, n, sport):
    rows = copy.deepcopy(rows)
    for r in rows:
        r["market"]["bookmaker_count"] = n
        if "bookmaker_count_quoted" in r["market"]:
            r["market"]["bookmaker_count_quoted"] = n
    doc = dp.annotate({"sport": sport, "exported_at": "2026-11-08T15:25:00Z", "predictions": rows}, now=NOW)
    return [r["desk"] for r in doc["predictions"]]


SOCCER_PLAYS = [   # a home PLAY at 7pp and an away LADDER at 30pp, on the live rules (no base_v11)
    brow(9401, "Alpha Owls", "Beta Hawks", 0.55, fair_h=0.48, fair_d=0.27, draw=0.25, bid=0.44, ask=0.45,
         comp="PL", series="KXTESTGAME"),
    brow(9402, "Gamma FC", "Delta United", 0.20, fair_h=0.45, fair_d=0.30, draw=0.25, bid=0.44, ask=0.45,
         comp="PL", series="KXTESTGAME")]


@pytest.mark.parametrize("few", [1, 2, 3])
def test_as_built_a_model_play_or_ladder_is_blind_to_the_count(few):
    """590 item 7(c), AS BUILT, ruling nothing: the same rows on one (two, three) book(s) and on nine give the same
    desk block byte for byte. desk_policy reads the count in the model chain only in PASSCLASS, which relabels a floor
    PASS (desk_policy.py:1739-1742); no floor on books stands before a PLAY or a LADDER."""
    one, nine = _desks(SOCCER_PLAYS, few, "soccer"), _desks(SOCCER_PLAYS, 9, "soccer")
    assert [d["call"] for d in nine] == ["PLAY", "LADDER"]
    assert json.dumps(one, sort_keys=True, default=str) == json.dumps(nine, sort_keys=True, default=str)


def test_as_built_the_floor_pass_is_where_the_count_is_read():
    """Beside the pin, for contrast and ruling nothing: the one place the model chain reads the count. A floor PASS on
    fewer than three books is relabelled noref with the thin-reference reason (PASSCLASS, minBooks 3)."""
    floor = [brow(9403, "Iota FC", "Kappa Town", 0.47, fair_h=0.46, fair_d=0.27, draw=0.26, bid=0.44, ask=0.45,
                  comp="PL", series="KXTESTGAME")]
    two, nine = _desks(floor, 2, "soccer")[0], _desks(floor, 9, "soccer")[0]
    assert (nine["call"], nine["pass_kind"]) == ("PASS", "floor")
    assert (two["call"], two["pass_kind"]) == ("PASS", "noref")
    assert "books 2 < 3 → thin reference" in two["reason"]
    assert dp.PASSCLASS["minBooks"] == 3 and dp.VENUE["minBooks"] == 4
