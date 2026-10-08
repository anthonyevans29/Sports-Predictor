"""VENUE-EDGE: QUOTE AGE (ARCHITECT 2026-10-07, addendum 4 E, gate-class): "#91 means the age of the QUOTE. A fetch
time is not a quote age; where the quote's own time is not known the age is UNKNOWN, and the ratified rule for
unknown age is NO REFERENCE. [...] In code, from the next tag: venue-edge emits no call (PASS, noref, 'book quote age
unknown: no reference') and the venue block keeps its numbers for the record."

Pins: a row that was VENUE is PASS / noref with that reason, units 0, no order, its numbers kept and its would-be
verdict recorded; every computed row is held (a below-floor row too); rows that stop before the computation keep
their own reason; base_v11() reproduces the old VENUE (the golden's policy); the window card obeys it; desk_meta
records the switch; parlay tickets never carry a venue leg."""
from datetime import datetime, timedelta, timezone

from src.walters import desk_policy as dp
from src.walters.venue import kalshi_exec

NOW = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)
MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
REASON = "book quote age unknown: no reference"


def fx(home="St. Louis Blues", away="San Jose Sharks", fair=(0.4735, 0.5265), kal=(0.545, 0.455), books=5,
       captured=30, legs=True, kickoff_h=4):
    """The ruling's receipt row (San Jose @ St. Louis): books HOME 0.4735 / AWAY 0.5265 vs Kalshi 0.545 / 0.455."""
    mk = {"bookmaker_count": books, "fair_prob": {"HOME": fair[0], "AWAY": fair[1]}} if fair else None
    if mk is not None and captured is not None:
        mk["captured_at"] = (NOW - timedelta(minutes=captured)).replace(tzinfo=None).isoformat()
    f = {"home_team": home, "away_team": away, "status": "scheduled",
         "utc_date": (NOW + timedelta(hours=kickoff_h)).replace(tzinfo=None).isoformat(), "market": mk,
         "kalshi": {"status": "two_sided", "prob": {"HOME": kal[0], "AWAY": kal[1]}} if kal else None}
    if legs:
        f["kalshi_legs"] = {"HOME": {"ticker": "KXNHLGAME-26OCT08SJSTL-STL", "bid": 0.53, "ask": 0.55},
                            "AWAY": {"ticker": "KXNHLGAME-26OCT08SJSTL-SJ", "bid": 0.44, "ask": 0.46}}
    return f


def desk(f, code="NHL"):
    doc = dp.annotate({"competition_code": code, "fixtures": [f]}, now=NOW)
    return doc["fixtures"][0]["desk"], doc["desk_meta"]


def test_a_row_that_was_venue_is_pass_noref_with_its_numbers_kept():
    d, meta = desk(fx())
    assert (d["engine"], d["call"], d["units"], d["pass_kind"], d["reason"]) == ("venue_edge", "PASS", 0, "noref", REASON)
    assert d["order"] is None
    assert d["side"] == "AWAY" and abs(d["div_pp"] - 7.15) < 1e-9
    assert (d["book_p"], d["kalshi_p"]) == (0.5265, 0.455)
    v = d["venue"]
    assert (v["eligible"], v["kind"], v["reason"], v["side"]) == (False, "noref", REASON, "AWAY")
    assert abs(v["div_pp"] - 7.15) < 1e-9 and v["exec_pp"] is not None and v["exec_cost"] is not None
    hold = v["quote_age_hold"]
    assert hold["engine_eligible"] is True and hold["engine_kind"] is None
    assert "Kalshi underprices by 7.1pp" in hold["engine_reason"] and "exec edge" in hold["engine_reason"]
    assert meta["venue_quote_age_rule"] is True


def test_without_the_hold_the_same_row_is_venue():
    with dp.quote_age_rule_off():
        d, meta = desk(fx())
    assert (d["call"], d["units"], d["side"], d["pass_kind"]) == ("VENUE", 0.25, "AWAY", None)
    assert d["order"]["text"].startswith("BUY YES KXNHLGAME-26OCT08SJSTL-SJ")
    assert "quote_age_hold" not in d["venue"] and meta["venue_quote_age_rule"] is False


def test_base_v11_reproduces_the_old_venue():
    with dp.base_v11():
        d, meta = desk(fx())
        v = dp.evaluate({"competition_code": "NHL", "fixtures": [fx()]}, MS)["venue"][0][1]
    assert (d["call"], d["units"], d["side"]) == ("VENUE", 0.25, "AWAY") and meta["venue_quote_age_rule"] is False
    assert v["eligible"] and "held" not in v


def test_a_below_floor_row_is_held_too_and_keeps_its_engine_verdict():
    d, _ = desk(fx(fair=(0.55, 0.45), kal=(0.54, 0.46)))                        # +1.0pp on HOME: below floor
    assert (d["call"], d["pass_kind"], d["reason"]) == ("PASS", "noref", REASON)
    assert d["side"] == "HOME" and abs(d["div_pp"] - 1.0) < 1e-9
    assert d["venue"]["quote_age_hold"]["engine_kind"] == "floor"
    assert d["venue"]["quote_age_hold"]["engine_eligible"] is False


def test_rows_that_stop_before_the_computation_keep_their_own_reason():
    cases = {
        "single venue — no pair": fx(kal=None),
        "book capture time unknown — no reference": fx(captured=None),
        "books captured 4.0h ago > 3h — no reference": fx(captured=240),
        "books 3 < 4 — pair too thin": fx(books=3),
        "in-play — never": fx(kickoff_h=-1),
    }
    for reason, f in cases.items():
        d, _ = desk(f)
        assert d["call"] == "PASS" and d["reason"] == reason, (reason, d["reason"])
        assert "quote_age_hold" not in d["venue"] and d["side"] is None
    d, _ = desk(fx(), code="UNL")
    assert d["reason"] == "single venue — no pair (UNL)" and "quote_age_hold" not in d["venue"]


def test_the_window_card_is_held_too():
    row = {**fx(), "competition": "NHL", "engine": "market_only"}
    v = dp.window_venue(row, MS)
    assert (v["eligible"], v["kind"], v["reason"], v["side"]) == (False, "noref", REASON, "AWAY")
    assert v["quote_age_hold"]["engine_eligible"] is True
    with dp.quote_age_rule_off():
        assert dp.window_venue(row, MS)["eligible"] is True


def _nfl(home, p_home, fair_h):
    q = kalshi_exec(round(fair_h - 0.01, 2), fair_h, "NFL", two_way=True)       # an executable quote (#87 v1.1 (5))
    return {**q, "home_team": home, "away_team": f"{home} away", "competition": "NFL", "stage": "regular",
            "utc_date": (NOW + timedelta(hours=3)).replace(tzinfo=None).isoformat(),
            "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                           "tier": "lean"},
            "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}}}


def test_parlay_tickets_carry_no_venue_leg():
    """Parlay legs come from model-edge calls only (evaluate()['calls'] never holds a market-only row) — with or
    without the hold, a venue row is never a leg."""
    nhl = {"competition_code": "NHL", "fixtures": [fx(), fx(home="Boston Bruins", away="Buffalo Sabres")]}
    nfl = {"sport": "nfl", "predictions": [_nfl("A", 0.70, 0.60), _nfl("B", 0.72, 0.62), _nfl("C", 0.71, 0.61)]}
    for ctx in (dp.base_v11, dp.quote_age_rule_off):
        with ctx():
            doc = dp.parlays_doc([("fixtures_NHL.json", nhl), ("nfl.json", nfl)], now=NOW)
            venue_was_called = any(v["eligible"] for _, v in dp.evaluate(nhl, MS)["venue"])
        assert venue_was_called                                    # the venue row WAS a call without the hold
        legs = [l for t in doc["tickets"] for l in t["legs"]]
        assert legs and all(l["sport"] == "NFL" for l in legs)
    doc = dp.parlays_doc([("fixtures_NHL.json", nhl), ("nfl.json", nfl)], now=NOW)
    assert all(l["sport"] == "NFL" for t in doc["tickets"] for l in t["legs"])
    assert doc["live_legs"] == 3
