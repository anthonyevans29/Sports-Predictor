"""THE THREE-WAY KALSHI CLOSE of the PAPER record (ARCHITECT 2026-10-20 17:52 ET, addendum 150, #639), items 2-4
verbatim: "2. The quotes (Q1): ONE capture in which all three legs (HOME, AWAY, TIE) are two-sided within the 2c cap —
the last such capture before kickoff, the same "last two-sided pre-kickoff session" shape as the two-way kalshi_only
rule. Legs from different captures are never combined. A game with no such capture has no close: counted as unpriced on
its own line, never formed from fewer than three legs (law 4). 3. The number (Q2): the three mids sum-normalized to 1
(as export._summarize_kalshi forms the venue fair); the raw sum is kept on the row as the overround. The record's
log-loss is scored on the normalized three-way probabilities. 4. The favourite (Q3): the largest of the three normalized
probabilities, the draw included; a row whose favourite is the draw is counted and flagged on the line."
Item 5: the result basis is 90 minutes plus stoppage (intl_shadow.result_90).

The stored vocabulary (law 1, read from the writer): src/ingestion/kalshi_sync.py sync_kalshi_soccer stores each leg as
OddsSnapshot(source "kalshi", market "1X2", selection HOME / AWAY / DRAW: the Tie leg is placed as DRAW by
kalshi_match.place), every leg of one run stamped with the run's one `now` (captured_at): a capture is one captured_at.
Each test runs on a throwaway SQLite file (tests/test_record_vs_close.py iso_db)."""
import math
from datetime import timedelta
from types import SimpleNamespace

import pytest

from src.db.schema import Sport
from src.walters import paper
from tests.test_close_record_paper import KO, NOW, _game, _kal
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

KIND3 = "close: kalshi three-way (one capture, normalized)"
OTHER = ("the last full capture fails the close's other checks {c} (a leg stored twice with two quotes, a quote that is "
         "not a number, a crossed or out-of-range quote, or no normalized sum; no older capture substituted)")
T1 = KO - timedelta(minutes=30)                  # one capture (one sync run's captured_at)
T0 = KO - timedelta(hours=3)                     # an earlier capture


def _comps(*extra):
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        for sport, code in ((Sport.NHL, "NHL"), (Sport.NFL, "NCAA"), (Sport.SOCCER, "CL"),
                            *((Sport.SOCCER, c) for c in extra)):
            s.add(Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE"))


def _legs(mid, quotes, at=T1):
    """quotes: {selection: (bid, ask)}, all stored at one captured_at (one capture)."""
    for sel, (bid, ask) in quotes.items():
        _kal(mid, sel, bid, ask, at, market="1X2")


def _three(code="CL"):
    """(the competition's line, its unpriced line, its record)."""
    rec = paper.close_record(30, now=NOW)
    lines = paper.close_record_section(rec, 30).splitlines()
    i = next(k for k, x in enumerate(lines) if x.startswith(f"- {code} · "))
    return lines[i], lines[i + 1], rec[code]


def unpriced_line(code, a, b, c=0):
    """The competition's unpriced line (addendum 150 item 2), its close kind named (item 1), the count split by cause
    (both verifiers' P2-1): a = no full capture before kickoff, b = the last full capture has a leg over the cap (the
    strict reading, R42), c = the third cause, printed only when it counts a game."""
    line = (f"  - {code} · close: kalshi three-way · unpriced {a + b + c}: no capture before kickoff with all three legs "
            f"two-sided {a}; the last full capture has a leg over the 2c cap {b} (no older capture substituted)")
    return line + (f"; {OTHER.format(c=c)}" if c else "")


def _row(sel, bid, ask, at=T1, source="kalshi", market="1X2"):
    return SimpleNamespace(source=source, market=market, selection=sel, captured_at=at, yes_bid=bid, yes_ask=ask)


A = {"HOME": (0.45, 0.46), "DRAW": (0.27, 0.28), "AWAY": (0.27, 0.28)}      # mids .455 .275 .275, raw sum 1.005
B = {"HOME": (0.40, 0.41), "DRAW": (0.30, 0.31), "AWAY": (0.29, 0.30)}      # mids .405 .305 .295, raw sum 1.005


# ---- the close (pure) ---------------------------------------------------------------------------------------------

def test_one_capture_with_all_three_legs_forms_the_close_normalized_with_the_overround_kept():
    """A: mids .455 / .275 / .275 (raw sum 1.005, the overround) -> .455/1.005 = .452736 -> .4527, .275/1.005 =
    .273632 -> .2736 (export._summarize_kalshi's own 4-decimal rounding): sums to 1 within that rounding (.9999)."""
    from src.walters.export import _summarize_kalshi
    rows = [_row(k, *v) for k, v in A.items()]
    cl = paper.three_way_close(rows, KO)
    assert cl["fair"] == {"HOME": 0.4527, "DRAW": 0.2736, "AWAY": 0.2736}
    assert cl["overround"] == 1.005 and cl["captured_at"] == T1 and cl["kind"] == KIND3[len("close: "):]
    assert abs(sum(cl["fair"].values()) - 1) <= 1.5e-4
    assert {k: v["mid"] for k, v in cl["kalshi"].items()} == pytest.approx({"HOME": 0.455, "DRAW": 0.275, "AWAY": 0.275})
    # the venue fair as the export forms it, called, never re-derived: the same numbers from the same mids
    ref = _summarize_kalshi(None, {k: SimpleNamespace(devig_prob=(b + a) / 2, captured_at=T1) for k, (b, a) in A.items()},
                            three_way=True)
    assert cl["fair"] == ref["prob"] and cl["overround"] == ref["raw_sum"]
    cl = paper.three_way_close([_row(k, *v) for k, v in B.items()], KO)
    assert cl["fair"] == {"HOME": 0.403, "DRAW": 0.3035, "AWAY": 0.2935} and sum(cl["fair"].values()) == 1.0


def test_a_leg_exactly_2c_wide_is_within_the_cap():
    """The cap is close_from_kalshi's: js_round of the cents > 2 fails, so a 2c leg (.26/.28, js_round(2.0000000000000018)
    = 2) prices; 3c does not."""
    rows = [_row("HOME", 0.45, 0.46), _row("DRAW", 0.26, 0.28), _row("AWAY", 0.27, 0.28)]
    assert paper.three_way_close(rows, KO)["kalshi"]["DRAW"]["spread_c"] == 2.0
    rows[1] = _row("DRAW", 0.25, 0.28)
    assert paper.three_way_close(rows, KO) is None


def test_legs_spread_over_two_captures_are_never_combined():
    """HOME and DRAW at T1, AWAY at T0: no capture holds all three legs, so no close (never formed from legs of two
    captures)."""
    rows = [_row("HOME", 0.45, 0.46), _row("DRAW", 0.27, 0.28), _row("AWAY", 0.27, 0.28, at=T0)]
    assert paper.three_way_close(rows, KO) is None


def test_the_last_full_capture_over_the_cap_is_no_close_and_an_older_one_is_never_substituted():
    """The strict reading: T1 holds all three legs two-sided, its DRAW 3c wide; T0 is a full capture within the cap.
    The close is the last full capture's or none: none."""
    rows = [_row(k, *v, at=T0) for k, v in A.items()]
    rows += [_row("HOME", 0.45, 0.46), _row("DRAW", 0.26, 0.29), _row("AWAY", 0.27, 0.28)]
    assert paper.three_way_close(rows, KO) is None
    assert paper.three_way_close(rows[:3], KO)["captured_at"] == T0          # T0 alone forms one


@pytest.mark.parametrize("later", [
    [_row("HOME", 0.50, 0.51), _row("AWAY", 0.20, 0.21)],                     # the later capture misses a leg
    [_row("HOME", 0.50, 0.51), _row("DRAW", 0.25, None), _row("AWAY", 0.20, 0.21)],   # one leg one-sided
], ids=["missing-leg", "one-sided-leg"])
def test_a_capture_without_all_three_legs_two_sided_is_skipped(later):
    """A later capture whose legs are not all two-sided is not "such a capture": the last FULL capture (T0) is the
    close."""
    rows = [_row(k, *v, at=T0) for k, v in A.items()] + later
    cl = paper.three_way_close(rows, KO)
    assert cl["captured_at"] == T0 and cl["fair"] == {"HOME": 0.4527, "DRAW": 0.2736, "AWAY": 0.2736}


def test_the_close_reads_only_kalshi_1x2_legs_before_kickoff():
    full = [_row(k, *v) for k, v in A.items()]
    assert paper.three_way_close(full, T1) is None                            # captured at the kickoff: not before it
    assert paper.three_way_close([_row(k, *v, source="consensus") for k, v in A.items()], KO) is None
    assert paper.three_way_close([_row(k, *v, market="ML") for k, v in A.items()], KO) is None
    assert paper.three_way_close([r for r in full if r.selection != "DRAW"], KO) is None   # two legs: never a close


@pytest.mark.parametrize("draw", [[_row("DRAW", 0.27, 0.28), _row("DRAW", 0.26, 0.27)],
                                  [_row("DRAW", "x", 0.28)], [_row("DRAW", 0.29, 0.28)]],
                         ids=["two-quotes-one-leg", "not-a-number", "crossed"])
def test_a_leg_that_cannot_be_read_as_one_quote_is_no_close(draw):
    """Law 4: a leg stored twice at one capture with two different quotes, a quote that is not a number, or a crossed
    quote: no close, never a guess (and no older capture substituted)."""
    rows = [_row(k, *v, at=T0) for k, v in A.items()] + [_row("HOME", 0.45, 0.46), _row("AWAY", 0.27, 0.28), *draw]
    assert paper.three_way_close(rows, KO) is None


def test_the_favourite_is_the_largest_of_three_the_draw_included_and_a_top_tie_is_even():
    assert paper.favourite_3({"HOME": 0.3065, "DRAW": 0.3869, "AWAY": 0.3065}) == "DRAW"
    assert paper.favourite_3({"HOME": 0.3632, "DRAW": 0.2736, "AWAY": 0.3632}) == "EVEN"
    assert paper.favourite_3({"HOME": 0.4527, "DRAW": 0.2736, "AWAY": 0.2736}) == "HOME"


# ---- the record ---------------------------------------------------------------------------------------------------

def test_cl_is_scored_on_the_normalized_three_way_close_and_a_knockout_won_in_extra_time_is_a_draw():
    """Two CL games, worked by hand:
    701, 2-1 after 90 (FT): close A -> HOME .4527 (the favourite, a hit); log-loss -ln(.4527) = 0.792526.
    702, 1-1 after 90, won 2-1 in extra time (AET; home_score_90 / away_score_90 1-1): result_90 reads the draw.
    Close B -> HOME .4030 / DRAW .3035 / AWAY .2935: the favourite HOME misses; log-loss -ln(.3035) = 1.192374.
    Mean (0.792526 + 1.192374) / 2 = 0.992450 -> 0.9924; favourite 1/2; overround mean (1.005 + 1.005) / 2 = 1.0050."""
    _comps()
    _game(701, "CL", 2, 1, hs90=2, aw90=1, raw="FT")
    _legs(701, A)
    _game(702, "CL", 2, 1, hs90=1, aw90=1, raw="AET")
    _legs(702, B)
    ll = (-math.log(0.4527) - math.log(0.3035)) / 2
    assert f"{ll:.4f}" == "0.9924"
    line, unpriced, rec = _three()
    assert line == (f"- CL · {KIND3} · close log-loss 0.9924 · favourite 1/2 (50.0%) · draw favourite 0 · n=2 · "
                    "overround mean 1.0050 · finished 2; left out: none")
    assert unpriced == unpriced_line("CL", 0, 0)
    assert [(r["match_id"], r["result"], r["overround"]) for r in rec["rows"]] == [(701, "HOME", 1.005),
                                                                                  (702, "DRAW", 1.005)]
    # every row of the record names its close kind (addendum 150 item 1; verifier0 P3-1)
    assert [r["kind"] for r in rec["rows"]] == [paper.KIND_THREE] * 2 and rec["kind"] == paper.KIND_THREE


def test_a_ft_row_without_90_minute_scores_reads_its_score_and_an_aet_row_without_them_is_no_result():
    """result_90's own fallback (unchanged): a FT row's score; an AET row with no 90-minute score is never scored."""
    _comps()
    _game(703, "CL", 0, 0, raw="FT")
    _legs(703, A)
    _game(704, "CL", 2, 1, raw="AET")
    _legs(704, A)
    line, _, rec = _three()
    assert (rec["n"], rec["no_result"], rec["rows"][0]["result"]) == (1, 1, "DRAW")
    assert line.endswith("; left out: no decided 90-minute result 1")


def test_the_draw_favourite_is_counted_and_flagged_and_an_exact_top_tie_is_even():
    """705: HOME .30/.31, DRAW .38/.39, AWAY .30/.31 -> DRAW .3869 the favourite; 0-0, a hit (-ln .3869 = 0.949589).
    706: HOME .36/.37, DRAW .27/.28, AWAY .36/.37 -> HOME = AWAY = .3632: EVEN, in n and the log-loss only."""
    _comps()
    _game(705, "CL", 0, 0, hs90=0, aw90=0, raw="FT")
    _legs(705, {"HOME": (0.30, 0.31), "DRAW": (0.38, 0.39), "AWAY": (0.30, 0.31)})
    _game(706, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(706, {"HOME": (0.36, 0.37), "DRAW": (0.27, 0.28), "AWAY": (0.36, 0.37)})
    ll = (-math.log(0.3869) - math.log(0.3632)) / 2
    line, _, rec = _three()
    assert line == (f"- CL · {KIND3} · close log-loss {ll:.4f} · favourite 1/1 (100.0%) · draw favourite 1 · n=2 "
                    "(even 1) · overround mean 1.0000 · finished 2; left out: none")
    assert [r["favourite"] for r in rec["rows"]] == ["DRAW", "EVEN"]


def test_unpriced_games_are_counted_on_their_own_line_and_mismatched_legs_before_them():
    """707: two legs only (unpriced, never formed from two); 708: its last full capture 3c wide (unpriced); 709: no
    leg stored (unpriced); 710: legs of two events (mismatched legs, addendum 37 item 3)."""
    from sqlalchemy import text

    from src.db.database import session_scope
    _comps()
    for mid in (707, 708, 709, 710):
        _game(mid, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(707, {"HOME": (0.45, 0.46), "AWAY": (0.27, 0.28)})
    _legs(708, {"HOME": (0.45, 0.46), "DRAW": (0.26, 0.29), "AWAY": (0.27, 0.28)})
    _legs(710, A)
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXUCLGAME-26OCT18AAABBB-AAA' WHERE match_id = 710 "
                       "AND selection = 'HOME'"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXUCLGAME-26OCT18CCCDDD-TIE' WHERE match_id = 710 "
                       "AND selection <> 'HOME'"))
    line, unpriced, rec = _three()
    assert line == (f"- CL · {KIND3} · close log-loss — · favourite — · n=0 · finished 4; left out: mismatched legs 1")
    assert unpriced == unpriced_line("CL", 2, 1)            # 707 and 709: no full capture; 708: its last one 3c wide


def test_another_market_only_three_way_competition_appears_only_with_kalshi_1x2_legs():
    """ELC (desk_policy.SHADOW_VENUE_COMPS, market-only) with a stored Kalshi 1X2 capture prints its own three-way
    line after CL; UEL (cup_coeff.EXAM_COMPS) with finished games and no Kalshi leg prints nothing; PL (LIVE, in no
    market-only set) never takes this record, whatever it stores."""
    _comps("ELC", "UEL", "PL")
    _game(801, "ELC", 3, 0, hs90=3, aw90=0, raw="FT")
    _legs(801, A)
    _game(802, "UEL", 1, 1, hs90=1, aw90=1, raw="FT")
    _game(803, "PL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(803, A)
    rec = paper.close_record(30, now=NOW)
    assert list(rec) == ["NHL", "NCAA", "CL", "ELC"]
    txt = paper.close_record_section(rec, 30)
    assert (f"- ELC · {KIND3} · close log-loss {-math.log(0.4527):.4f} · favourite 1/1 (100.0%) · draw favourite 0 · "
            "n=1 · overround mean 1.0050 · finished 1; left out: none\n"
            f"{unpriced_line('ELC', 0, 0)}") in txt
    assert "- UEL" not in txt and "- PL" not in txt
    assert paper.close_record_console(rec, 30) == (
        "the close's record (PAPER; 30 days): kalshi_only two-way: NHL n=0 · NCAA n=0; kalshi three-way (one capture, "
        "normalized): CL n=0 (unpriced 0) · ELC n=1 (unpriced 0)")


def test_the_market_only_set_is_the_codes_own():
    from src.walters.cup_coeff import EXAM_COMPS
    from src.walters.desk_policy import SHADOW_VENUE_COMPS
    from src.walters.export import _MARKET_ONLY_REASON
    assert set(paper.three_way_comps()) == (set(SHADOW_VENUE_COMPS) | EXAM_COMPS | set(_MARKET_ONLY_REASON)) - {
        "NHL", "NCAA", "CL"}
    assert "PL" not in paper.three_way_comps()


def test_the_desks_grading_close_is_untouched_on_a_three_way_board():
    """Addendum 150 item 1: "It is never the Desk's graded close". On the same CL game the record prices,
    close.grading_close and close.close_from_kalshi still return None (no book, a three-way board)."""
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    from src.walters import close
    _comps()
    _game(711, "CL", 2, 1, hs90=2, aw90=1, raw="FT")
    _legs(711, A)
    assert _three()[2]["n"] == 1
    with session_scope() as s:
        m = s.get(Match, 711)
        snaps = list(s.query(OddsSnapshot).filter_by(match_id=711))
        assert len(snaps) == 3 and close.outcomes_for(m.sport) == close.THREE_WAY
        assert close.close_from_kalshi(snaps, m.utc_date, close.THREE_WAY) is None
        assert close.grading_close(s, m) is None
        assert paper.three_way_close(snaps, m.utc_date)["fair"] == {"HOME": 0.4527, "DRAW": 0.2736, "AWAY": 0.2736}


# ---- the unpriced line, split by cause (both verifiers' P2-1) -----------------------------------------------------

@pytest.mark.parametrize("rows,why", [
    ([], "unpriced_none"),                                                                      # no leg stored
    ([_row("HOME", 0.45, 0.46), _row("AWAY", 0.27, 0.28)], "unpriced_none"),                   # two legs only
    ([_row("HOME", 0.45, 0.46), _row("DRAW", 0.27, 0.28), _row("AWAY", 0.27, 0.28, at=T0)],   # two captures
     "unpriced_none"),
    ([_row(k, *v, at=T0) for k, v in A.items()]                                    # an older full capture within the
     + [_row("HOME", 0.45, 0.46), _row("DRAW", 0.26, 0.29), _row("AWAY", 0.27, 0.28)],    # cap; the last one 3c wide
     "unpriced_cap"),
    ([_row("HOME", 0.45, 0.46), _row("DRAW", 0.29, 0.28), _row("AWAY", 0.27, 0.28)], "unpriced_other"),   # crossed
    ([_row("HOME", 0.45, 0.46), _row("DRAW", "x", 0.28), _row("AWAY", 0.27, 0.28)], "unpriced_other"),    # text
    ([_row("HOME", 0.45, 0.46), _row("DRAW", 0.27, 0.28), _row("DRAW", 0.26, 0.27), _row("AWAY", 0.27, 0.28)],
     "unpriced_other"),                                                                         # two quotes, one leg
    ([_row(k, 0.0, 0.00008) for k in ("HOME", "DRAW", "AWAY")], "unpriced_other"),           # no normalized sum
], ids=["no-leg", "two-legs", "two-captures", "last-full-over-the-cap", "crossed", "not-a-number", "two-quotes",
        "no-normalized-sum"])
def test_the_cause_of_no_close_is_named_and_which_games_get_a_close_is_unchanged(rows, why):
    """_three_way names the cause; three_way_close is its close, None on each of these (no behaviour change)."""
    assert paper._three_way(rows, KO) == (None, why)
    assert paper.three_way_close(rows, KO) is None


def test_the_unpriced_line_splits_its_count_by_cause_so_every_printed_reason_is_true():
    """Both verifiers' P2-1. 721: a full capture within the cap at T0, and the last full capture (T1) with its DRAW 3c
    wide: unpriced by the strict reading (R42), counted as "the last full capture has a leg over the 2c cap", never as
    "no capture before kickoff with all three legs two-sided" (T0 is one). 722: two legs only; 723: no leg stored;
    724: its legs over two captures: no full capture, counted as such. Then 725, its only full capture's DRAW crossed:
    the third cause, printed only when it counts a game."""
    _comps()
    for mid in (721, 722, 723, 724):
        _game(mid, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(721, A, at=T0)
    _legs(721, {"HOME": (0.45, 0.46), "DRAW": (0.26, 0.29), "AWAY": (0.27, 0.28)})
    _legs(722, {"HOME": (0.45, 0.46), "AWAY": (0.27, 0.28)})
    _legs(724, {"HOME": (0.45, 0.46), "DRAW": (0.27, 0.28)})
    _legs(724, {"AWAY": (0.27, 0.28)}, at=T0)
    line, unpriced, rec = _three()
    assert unpriced == ("  - CL · close: kalshi three-way · unpriced 4: no capture before kickoff with all three legs "
                        "two-sided 3; the last full capture has a leg over the 2c cap 1 (no older capture substituted)")
    assert (rec["unpriced"], rec["unpriced_none"], rec["unpriced_cap"], rec["unpriced_other"]) == (4, 3, 1, 0)
    assert line.endswith(" · n=0 · finished 4; left out: none")
    _game(725, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(725, {"HOME": (0.45, 0.46), "DRAW": (0.29, 0.28), "AWAY": (0.27, 0.28)})
    _, unpriced, rec = _three()
    assert unpriced == unpriced_line("CL", 3, 1, 1) == (
        "  - CL · close: kalshi three-way · unpriced 5: no capture before kickoff with all three legs two-sided 3; the "
        "last full capture has a leg over the 2c cap 1 (no older capture substituted); the last full capture fails the "
        "close's other checks 1 (a leg stored twice with two quotes, a quote that is not a number, a crossed or "
        "out-of-range quote, or no normalized sum; no older capture substituted)")
    assert rec["unpriced"] == 5
    assert paper.close_record_console(paper.close_record(30, now=NOW), 30).endswith("CL n=0 (unpriced 5)")


# ---- verifier1's probes, adopted (each kills a mutation the suite let live: V1-V4, V6, V7, V8, V9, V18, V20) ------

@pytest.mark.parametrize("bid,ask,ok", [(0.26, 0.28, True), (0.255, 0.28, False), (0.265, 0.28, True),
                                        (0.57, 0.59, True), (0.0, 0.02, True), (0.98, 1.0, True),
                                        (0.0, 0.0, False), (1.0, 1.0, False)])
def test_the_per_leg_check_agrees_with_close_from_kalshi_on_the_same_quote(bid, ask, ok):
    """The three-way per-leg check is close_from_kalshi's own (bounds, ask > 0, bid < 1, the 2c cap on js_round): on
    each quote (as the DRAW leg) the two agree. (0, 0) kills V1 (ask > 0 dropped), (1, 1) kills V2 (bid < 1 dropped)."""
    from src.walters import close
    q = dict(A, DRAW=(bid, ask))
    got = paper.three_way_close([_row(k, *v) for k, v in q.items()], KO) is not None
    two = close.close_from_kalshi([_row("HOME", bid, ask, market="ML")], KO, close.BINARY) is not None
    assert got == two == ok, (bid, ask, got, two)


@pytest.mark.parametrize("draw", [(-0.01, 0.01), (0.99, 1.01)], ids=["negative-bid", "ask-over-one"])
def test_a_negative_bid_or_an_ask_over_one_is_no_close(draw):
    """2c wide each, so only the bounds refuse them (V3: 0 <= bid dropped; V4: ask <= 1 dropped)."""
    rows = [_row(k, *v) for k, v in dict(A, DRAW=draw).items()]
    assert paper.three_way_close(rows, KO) is None
    assert paper._three_way(rows, KO) == (None, "unpriced_other")


def test_a_leg_stored_twice_one_quote_two_sided_reads_the_two_sided_quote():
    """A DRAW stored twice in one capture, once two-sided and once with no bid: the one-sided row is not a quote, so
    the leg reads as one quote and the close forms (V6: the one-sided row counted as a second quote)."""
    rows = [_row(k, *v) for k, v in A.items()] + [_row("DRAW", None, 0.40)]
    cl = paper.three_way_close(rows, KO)
    assert cl is not None and cl["fair"]["DRAW"] == 0.2736


def test_captures_a_second_or_a_microsecond_apart_are_never_combined():
    """One capture is one stored captured_at exactly (R43): AWAY a second, or a microsecond, after HOME and DRAW is
    another capture, so no capture holds all three legs (V18: captures grouped by the minute)."""
    for d in (timedelta(seconds=1), timedelta(microseconds=1)):
        rows = [_row("HOME", 0.45, 0.46), _row("DRAW", 0.27, 0.28), _row("AWAY", 0.27, 0.28, at=T1 + d)]
        assert paper._three_way(rows, KO) == (None, "unpriced_none"), d


def test_a_full_capture_after_kickoff_leaves_the_game_unpriced():
    """The record reads only captures before the game's kickoff (V20: the record called with no kickoff bound)."""
    _comps()
    _game(1501, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(1501, A, at=KO + timedelta(minutes=10))
    r = paper.close_record(30, now=NOW)["CL"]
    assert (r["n"], r["unpriced"], r["unpriced_none"]) == (0, 1, 1)


def test_no_decided_90_minute_result_is_counted_before_mismatched_legs():
    """_score_three's order of exclusion: an AET game with no 90-minute score whose legs name two events is "no decided
    90-minute result", never "mismatched legs" (V7: the two checks swapped)."""
    from sqlalchemy import text

    from src.db.database import session_scope
    _comps()
    _game(1601, "CL", 2, 1, raw="AET")
    _legs(1601, A)
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXUCLGAME-26OCT18AAABBB-AAA' WHERE match_id = 1601 "
                       "AND selection = 'HOME'"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXUCLGAME-26OCT18CCCDDD-TIE' WHERE match_id = 1601 "
                       "AND selection <> 'HOME'"))
    r = paper.close_record(30, now=NOW)["CL"]
    assert (r["no_result"], r["mismatched"], r["unpriced"]) == (1, 0, 0)


def test_kalshi_ml_rows_alone_never_print_a_three_way_competition():
    """ELC with only Kalshi two-way (ML) rows has no stored Kalshi 1X2 leg: nothing printed (V8: any Kalshi row
    counted)."""
    _comps("ELC")
    _game(1701, "ELC", 1, 0, hs90=1, aw90=0, raw="FT")
    for sel, (bid, ask) in {"HOME": (0.45, 0.46), "AWAY": (0.27, 0.28)}.items():
        _kal(1701, sel, bid, ask, T1, market="ML")
    assert "ELC" not in paper.close_record(30, now=NOW)


def test_a_market_only_code_stored_as_another_sport_is_not_printed():
    """three_way_comps is kept only where this DB says soccer (V9: the soccer filter dropped)."""
    from src.db.database import session_scope
    from src.db.schema import Competition
    _comps()
    with session_scope() as s:
        s.add(Competition(sport=Sport.NHL, code="UNL", name="UNL", area="X", type="LEAGUE"))
    _game(1201, "UNL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(1201, A)
    assert "UNL" not in paper.close_record(30, now=NOW)


# ---- Codex round 1 P1 on #640 (R47): the tickers of the capture the close reads ------------------------------------

def _tickers(mid, t0, t1):
    """What migrate_kalshi_ticker.py adds, then each leg's market_ticker: t0 for the two-sided capture (yes_bid stored),
    t1 for the bid-less one; {selection: ticker or None}."""
    from sqlalchemy import text

    from src.db.database import session_scope
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        for cond, tick in (("yes_bid IS NOT NULL", t0), ("yes_bid IS NULL", t1)):
            for sel, v in tick.items():
                s.execute(text(f"UPDATE odds_snapshots SET market_ticker = :v WHERE match_id = :m AND selection = :s "
                               f"AND {cond}"), {"v": v, "m": mid, "s": sel})


E1 = {"HOME": "KXUCLGAME-26OCT18AAABBB-AAA", "DRAW": "KXUCLGAME-26OCT18AAABBB-TIE", "AWAY": "KXUCLGAME-26OCT18AAABBB-BBB"}


@pytest.mark.parametrize("t0,want", [
    ({"HOME": E1["HOME"], "DRAW": "KXUCLGAME-26OCT18CCCDDD-TIE", "AWAY": "KXUCLGAME-26OCT18CCCDDD-DDD"},
     {"n": 0, "mismatched": 1, "unpriced": 0}),
    (E1, {"n": 1, "mismatched": 0, "unpriced": 0}),
    ({**E1, "DRAW": None}, {"n": 1, "mismatched": 0, "unpriced": 0}),
], ids=["the-capture-read-names-two-events", "one-event", "one-event-and-an-untickered-leg"])
def test_the_capture_the_close_reads_is_judged_for_mismatched_legs(t0, want):
    """Codex round 1 P1 on #640 (R47, verifier1's probe): CL 1301, T0 = KO-3h a full capture within the cap, T1 = KO-30m
    bid-less legs all of event AAABBB (each side's newest leg: kalshi_legs.mismatched passes them). Before the fix the
    close read T0 whatever its tickers (n=1, mismatched 0, legs of two events priced). Now the close's own capture is
    judged by kalshi_legs.judge on its three rows' market_ticker (read by SQL by row id): two events -> "mismatched
    legs", no close; one event -> priced; an untickered leg names no event (kalshi_legs: "Legs with no stored ticker
    are read as before")."""
    from src.db.database import session_scope
    from src.walters import kalshi_legs
    _comps()
    _game(1301, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(1301, A, at=T0)
    for sel in ("HOME", "DRAW", "AWAY"):
        _kal(1301, sel, None, 0.50, T1, market="1X2")
    _tickers(1301, t0, E1)
    with session_scope() as s:
        assert kalshi_legs.mismatched(s, [1301]) == {}            # the newest legs name one event: the guard passes
    line, unpriced, r = _three()
    assert {k: r[k] for k in want} == want
    if want["mismatched"]:
        assert line == f"- CL · {KIND3} · close log-loss — · favourite — · n=0 · finished 1; left out: mismatched legs 1"
        assert unpriced == unpriced_line("CL", 0, 0) and r["rows"] == []
    else:
        assert r["rows"][0]["captured_at"] == T0


def test_an_older_capture_naming_two_events_is_not_the_capture_read():
    """The check is on the capture the close reads, never an older one: T0 (two events) is not read when T1 is a full
    capture of one event within the cap."""
    from sqlalchemy import text

    from src.db.database import session_scope
    _comps()
    _game(1302, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(1302, A, at=T0)
    _legs(1302, B, at=T1)
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXUCLGAME-26OCT18AAABBB-' || selection "
                       "WHERE match_id = 1302"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXUCLGAME-26OCT18CCCDDD-TIE' WHERE match_id = 1302 "
                       "AND selection = 'DRAW' AND yes_bid = 0.27"))
    r = paper.close_record(30, now=NOW)["CL"]
    assert (r["n"], r["mismatched"], r["unpriced"], r["rows"][0]["captured_at"]) == (1, 0, 0, T1)


def test_a_capture_read_naming_two_events_is_mismatched_before_its_cap_is_judged():
    """The order of exclusion holds on the capture read: mismatched legs before unpriced. T0, the last full capture,
    names two events and its DRAW is 3c wide: "mismatched legs", never "the last full capture has a leg over the 2c
    cap" (nothing is judged from legs of two events, addendum 37 item 3)."""
    _comps()
    _game(1303, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(1303, {**A, "DRAW": (0.26, 0.29)}, at=T0)
    for sel in ("HOME", "DRAW", "AWAY"):
        _kal(1303, sel, None, 0.50, T1, market="1X2")
    _tickers(1303, {"HOME": E1["HOME"], "DRAW": "KXUCLGAME-26OCT18CCCDDD-TIE", "AWAY": "KXUCLGAME-26OCT18CCCDDD-DDD"},
             E1)
    r = paper.close_record(30, now=NOW)["CL"]
    assert (r["n"], r["mismatched"], r["unpriced"], r["unpriced_cap"]) == (0, 1, 0, 0)


def test_a_capture_of_one_event_whose_current_legs_sit_on_another_game_is_mismatched():
    """The ruled guard's second clause on the capture read (addendum 37 item 3: "that event's current legs sit on no
    other game"; verifier on Codex round 1, #640): CL 1402's last full capture T0 is all of event CCCDDD, whose CURRENT
    legs sit on CL 1403; 1402's newest legs (T1, bid-less) are all of AAABBB, so kalshi_legs.mismatched passes both
    games. Before this check 1402 was priced from 1403's contracts; now it is "mismatched legs" and 1403 is priced."""
    from sqlalchemy import text

    from src.db.database import session_scope
    from src.walters import kalshi_legs
    e2 = {"HOME": "KXUCLGAME-26OCT18CCCDDD-CCC", "DRAW": "KXUCLGAME-26OCT18CCCDDD-TIE",
          "AWAY": "KXUCLGAME-26OCT18CCCDDD-DDD"}
    _comps()
    _game(1402, "CL", 1, 0, hs90=1, aw90=0, raw="FT")
    _legs(1402, A, at=T0)
    for sel in ("HOME", "DRAW", "AWAY"):
        _kal(1402, sel, None, 0.50, T1, market="1X2")
    _game(1403, "CL", 0, 1, hs90=0, aw90=1, raw="FT")
    _legs(1403, B, at=T1)
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        for mid, at, tick in ((1402, T0, e2), (1403, T1, e2), (1402, T1, E1)):
            for sel, t in tick.items():
                n = s.execute(text("UPDATE odds_snapshots SET market_ticker = :v WHERE match_id = :m AND selection = :s "
                                   "AND substr(captured_at, 1, 19) = :t"),
                              {"v": t, "m": mid, "s": sel, "t": at.strftime("%Y-%m-%d %H:%M:%S")}).rowcount
                assert n == 1, (mid, sel, at, n)
    with session_scope() as s:
        assert kalshi_legs.mismatched(s, [1402, 1403]) == {}     # each side's newest legs pass the ruled guard
    r = paper.close_record(30, now=NOW)["CL"]
    assert (r["n"], r["mismatched"], r["unpriced"]) == (1, 1, 0)
    assert [x["match_id"] for x in r["rows"]] == [1403]
