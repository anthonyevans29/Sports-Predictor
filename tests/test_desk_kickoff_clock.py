"""A STORED KICKOFF THE MARKET'S CLOCK DISPUTES GETS NO CALL (ARCHITECT 2026-10-15 08:46 ET, addendum 72 item 1, RULED,
law 4): a row whose stored kickoff and the Kalshi clock in its leg's own ticker disagree by more than
kalshi_match.MAX_TICK_DRIFT (superseded for the Desk by addendum 83 item 2, below: DESK_CLOCK_DRIFT, 1h, inclusive)
gets no Desk call: PASS, units 0, no order, no value shadow, pass kind kickoff_clock, the
reason naming both clocks. A ticker shape without a clock is not compared. The closing file carries the kind and both
clocks. Tests on the day's rows: 50546 TB at CLE (stored 13:00 ET, KXMLBGAME-26OCT151800TBCLE: 18:00 ET) is held;
50547 MIL at LAD (20:00 ET both) is untouched.
THE DESK'S OWN THRESHOLD (ARCHITECT 2026-10-16, addendum 83 item 2, RULED): DESK_CLOCK_DRIFT = 1h in desk_policy,
inclusive ("at or more than 60 minutes apart hold the row"); the matcher's MAX_TICK_DRIFT stays 2h for placement.
"Today's 50548 (8pm vs 6pm) then holds; yesterday's 50546 (1pm vs 6pm) holds; 50547 (8pm vs 8pm) does not." (verbatim)."""
import importlib.util
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from src.ingestion.kalshi_match import MAX_TICK_DRIFT
from src.walters import desk_policy as dp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 15, 16, 25, tzinfo=timezone.utc)          # 12:25pm ET, the closing run of the morning
NOW_MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
REASON_50546 = "stored kickoff 2026-10-15 13:00 ET vs Kalshi's clock 18:00 ET: no call"


def mlb(mid, home, away, utc, event, p_home=0.61, fair_h=0.56):
    """An MLB export row at a 5pp edge on HOME (a PLAY on books), its legs on the event's own tickers."""
    h, a = event.rsplit("-", 1)[0], event
    return {"match_id": mid, "home_team": home, "away_team": away, "utc_date": utc, "competition": "MLB",
            "stage": "postseason",
            "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                           "tier": "lean"},
            "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}},
            "kalshi_legs": {"HOME": {"ticker": f"{event}-{home[:3].upper()}", "bid": 0.55, "ask": 0.56},
                            "AWAY": {"ticker": f"{event}-{away[:3].upper()}", "bid": 0.43, "ask": 0.44}}}


def tb_cle():
    return mlb(50546, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-15T17:00:00", "KXMLBGAME-26OCT151800TBCLE")


def mil_lad():
    return mlb(50547, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", "KXMLBGAME-26OCT152000MILLAD")


def annotate(*rows, now=NOW):
    doc = {"sport": "mlb", "predictions": list(rows)}
    dp.annotate(doc, now=now)
    return {r["match_id"]: r["desk"] for r in doc["predictions"]}, doc


def tb_cle_tonight():
    """50548 (addendum 83 item 1): statsapi and the host at 8:00pm ET (2026-10-17T00:00Z), the ticker at 6:00pm ET."""
    return mlb(50548, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-17T00:00:00", "KXMLBGAME-26OCT161800TBCLE")


def test_the_desk_reads_its_own_one_hour_threshold_and_the_matcher_keeps_two(monkeypatch):
    """Addendum 83 item 2: "the Desk's own threshold is ONE HOUR, its own constant (DESK_CLOCK_DRIFT = 1h in
    desk_policy; the matcher's MAX_TICK_DRIFT stays 2h for placement, which is a different question)"."""
    assert dp.DESK_CLOCK_DRIFT == timedelta(hours=1) and MAX_TICK_DRIFT == timedelta(hours=2)
    assert dp.KICKOFF_CLOCK_KIND in dp.NO_CALL_KINDS and dp.KICKOFF_CLOCK_RULE["on"] is True
    from src.ingestion import kalshi_match
    monkeypatch.setattr(kalshi_match, "MAX_TICK_DRIFT", timedelta(hours=6))     # the matcher's never moves the Desk's
    desk, doc = annotate(tb_cle_tonight())
    assert desk[50548]["pass_kind"] == "kickoff_clock"
    assert doc["desk_meta"]["kickoff_clock_rule"] is True and doc["desk_meta"]["kickoff_clock_hold_h"] == 1.0
    monkeypatch.setattr(dp, "DESK_CLOCK_DRIFT", timedelta(hours=3))             # the Desk's own constant decides
    desk, _ = annotate(tb_cle_tonight())
    assert desk[50548]["pass_kind"] != "kickoff_clock" and desk[50548]["call"] == "PLAY"


def test_50548_tb_at_cle_tonight_is_held_at_exactly_two_hours():
    """Addendum 83 item 1: two hours apart is exactly MAX_TICK_DRIFT, so the matcher printed no clock line and #530's
    "more than" 2h would not fire; the Desk's own inclusive hour holds it."""
    stored, clock = datetime(2026, 10, 17, 0, 0), datetime(2026, 10, 16, 22, 0)
    assert abs(stored - clock) == MAX_TICK_DRIFT and not abs(stored - clock) > MAX_TICK_DRIFT    # #530 would pass it
    desk, _ = annotate(tb_cle_tonight(), now=datetime(2026, 10, 16, 21, 25, tzinfo=timezone.utc))
    d = desk[50548]
    reason = "stored kickoff 2026-10-16 20:00 ET vs Kalshi's clock 18:00 ET: no call"
    assert (d["call"], d["units"], d["pass_kind"], d["reason"]) == ("PASS", 0, "kickoff_clock", reason)
    assert d["order"] is None and d["value_shadow"] is None and d["exec"] is None
    assert d["kickoff_clock"] == {"stored_kickoff": "2026-10-17T00:00:00Z", "stored_kickoff_et": "2026-10-16 20:00 ET",
                                  "kalshi_clock": "2026-10-16T22:00:00Z", "kalshi_clock_et": "2026-10-16 18:00 ET",
                                  "drift_h": 2.0, "max_drift_h": 1.0}


def test_50546_tb_at_cle_is_held_with_both_clocks():
    desk, doc = annotate(tb_cle())
    d = desk[50546]
    assert (d["call"], d["units"], d["pass_kind"], d["shadow_units"]) == ("PASS", 0, "kickoff_clock", 0)
    assert d["reason"] == REASON_50546 and d["reasons"] == [REASON_50546] and d["tags"] == ["kickoff_clock"]
    assert d["order"] is None and d["value_shadow"] is None and d["exec"] is None
    assert d["kickoff_clock"] == {"stored_kickoff": "2026-10-15T17:00:00Z", "stored_kickoff_et": "2026-10-15 13:00 ET",
                                  "kalshi_clock": "2026-10-15T22:00:00Z", "kalshi_clock_et": "2026-10-15 18:00 ET",
                                  "drift_h": 5.0, "max_drift_h": 1.0}
    assert doc["desk_meta"]["kickoff_clock_rule"] is True
    with dp.kickoff_clock_rule_off():                  # the call the rule holds: a PLAY on 5pp
        off, _ = annotate(tb_cle())
    assert off[50546]["call"] == "PLAY" and off[50546]["order"] is not None and "kickoff_clock" not in off[50546]


def test_50547_mil_at_lad_is_untouched():
    desk, _ = annotate(mil_lad())
    with dp.kickoff_clock_rule_off():
        off, _ = annotate(mil_lad())
    assert desk[50547] == off[50547] and desk[50547]["call"] == "PLAY" and "kickoff_clock" not in desk[50547]


def test_the_held_row_is_never_a_parlay_leg():
    ev = dp.evaluate({"sport": "mlb", "predictions": [tb_cle(), mil_lad()]}, NOW_MS)
    held = [r for r, c in ev["calls"] if c["passKind"] == "kickoff_clock"]
    assert [r["home"] for r in held] == ["Cleveland Guardians"]
    doc = dp.parlays_doc([("mlb.json", {"sport": "mlb", "predictions": [tb_cle(), mil_lad()]})], now=NOW)
    assert doc["live_legs"] == 1


def test_the_held_row_is_never_a_value_shadow():
    """A row with a value side (the model 0.55 on CLE against the books' 0.62: TB +7pp) loses its shadow."""
    def value_row():
        return mlb(50546, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-15T17:00:00", "KXMLBGAME-26OCT151800TBCLE",
                   p_home=0.55, fair_h=0.62)
    with dp.kickoff_clock_rule_off():
        off, _ = annotate(value_row())
        assert dp.evaluate({"sport": "mlb", "predictions": [value_row()]}, NOW_MS)["values"]
    assert off[50546]["value_shadow"]["side"] == "AWAY"
    desk, _ = annotate(value_row())
    assert desk[50546]["pass_kind"] == "kickoff_clock" and desk[50546]["value_shadow"] is None
    assert dp.evaluate({"sport": "mlb", "predictions": [value_row()]}, NOW_MS)["values"] == []


@pytest.mark.parametrize("utc, held", [
    ("2026-10-15T21:00:00", True),        # 17:00 ET vs 18:00 ET: exactly 60 minutes holds (addendum 83: inclusive)
    ("2026-10-15T21:01:00", False),       # 59 minutes
    ("2026-10-15T23:00:00", True),        # 19:00 ET vs 18:00 ET: 60 minutes, the other way
    ("2026-10-15T22:59:00", False),
    ("2026-10-15T22:00:00", False),       # the same clock
    ("2026-10-15T20:00:00", True),        # 2h: the matcher's threshold, which #530 let through, now held
])
def test_at_or_more_than_the_hour_holds_and_under_it_does_not(utc, held):
    r = tb_cle()
    r["utc_date"] = utc
    desk, _ = annotate(r)
    assert (desk[50546]["pass_kind"] == "kickoff_clock") is held


def test_a_ticker_shape_without_a_clock_is_not_compared():
    r = tb_cle()
    r["kalshi_legs"] = {"HOME": {"ticker": "KXMLBGAME-26OCT15TBCLE-CLE", "bid": 0.55, "ask": 0.56},
                        "AWAY": {"ticker": "KXMLBGAME-26OCT15TBCLE-TB", "bid": 0.43, "ask": 0.44}}
    desk, _ = annotate(r)
    assert desk[50546]["pass_kind"] != "kickoff_clock" and desk[50546]["call"] == "PLAY"


@pytest.mark.parametrize("legs", [None, {}, {"HOME": {"ticker": None, "bid": 0.55, "ask": 0.56}},
                                  {"HOME": {"ticker": "", "bid": 0.55, "ask": 0.56}}])
def test_a_row_with_no_ticker_is_not_compared(legs):
    r = tb_cle()
    r["kalshi_legs"] = legs
    desk, _ = annotate(r)
    assert desk[50546]["pass_kind"] != "kickoff_clock"


@pytest.mark.parametrize("home, away", [
    ("KXMLBGAME-26OCT151300TBCLE-CLE", "KXMLBGAME-26OCT151800TBCLE-TB"),     # AWAY disputes, HOME agrees
    ("KXMLBGAME-26OCT151800TBCLE-CLE", "KXMLBGAME-26OCT151300TBCLE-TB"),     # HOME disputes, AWAY agrees
    ("KXMLBGAME-26OCT151800TBCLE-CLE", None),                                # HOME disputes, AWAY has no ticker
])
def test_any_one_leg_past_the_threshold_holds_the_row(home, away):
    r = tb_cle()
    r["kalshi_legs"]["HOME"]["ticker"], r["kalshi_legs"]["AWAY"]["ticker"] = home, away
    desk, _ = annotate(r)
    assert desk[50546]["pass_kind"] == "kickoff_clock" and desk[50546]["reason"] == REASON_50546


def test_a_stored_kickoff_after_kalshis_clock_is_held_with_a_positive_drift():
    r = tb_cle()
    r["utc_date"] = "2026-10-16T01:00:00"                                       # 21:00 ET vs 18:00 ET
    desk, _ = annotate(r)
    k = desk[50546]["kickoff_clock"]
    assert (k["drift_h"], k["stored_kickoff_et"], k["kalshi_clock_et"]) == (3.0, "2026-10-15 21:00 ET",
                                                                             "2026-10-15 18:00 ET")
    assert desk[50546]["reason"] == "stored kickoff 2026-10-15 21:00 ET vs Kalshi's clock 18:00 ET: no call"


def test_the_rule_precedes_started_and_follows_the_shadow_league_rule():
    later = datetime(2026, 10, 15, 17, 30, tzinfo=timezone.utc)      # 13:30 ET: past the stored kickoff
    desk, _ = annotate(tb_cle(), now=later)
    assert desk[50546]["pass_kind"] == "kickoff_clock"
    with dp.kickoff_clock_rule_off():
        off, _ = annotate(tb_cle(), now=later)
    assert off[50546]["pass_kind"] == "started"
    shadow = tb_cle()                                   # S1 comes first: a shadow-league row keeps its own reason
    shadow["competition"] = sorted(dp.SHADOW_VENUE_COMPS)[0]
    desk, _ = annotate(shadow)
    assert desk[50546]["pass_kind"] == dp.SHADOW_LEAGUE_KIND


def test_kalshis_clock_on_another_day_keeps_its_date():
    stored, clock = datetime(2026, 10, 15, 17, 0), datetime(2026, 10, 16, 4, 30)
    assert dp.kickoff_clock_reason(stored, clock) == \
        "stored kickoff 2026-10-15 13:00 ET vs Kalshi's clock 2026-10-16 00:30 ET: no call"


def test_the_frozen_battery_runs_with_the_rule_off():
    with dp.base_v11():
        assert dp.KICKOFF_CLOCK_RULE["on"] is False
    assert dp.KICKOFF_CLOCK_RULE["on"] is True


def test_the_closing_file_carries_the_kind_and_both_clocks():
    """The closing file is the export's rows as the run's export gave them (closing.closing_doc, addendum 40 item 2):
    the held row's desk block carries the kind, the reason and both clocks."""
    spec = importlib.util.spec_from_file_location("closing", os.path.join(ROOT, "deploy", "hosting", "closing.py"))
    closing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(closing)
    _, doc = annotate(tb_cle(), mil_lad())
    out = closing.closing_doc(doc, "MLB", datetime(2026, 10, 15, 17, 0), "run-1", [50546, 50547], [])
    rows = {r["match_id"]: r["desk"] for r in out["predictions"]}
    assert rows[50546]["pass_kind"] == "kickoff_clock" and rows[50546]["reason"] == REASON_50546
    assert (rows[50546]["kickoff_clock"]["stored_kickoff_et"], rows[50546]["kickoff_clock"]["kalshi_clock_et"]) == \
        ("2026-10-15 13:00 ET", "2026-10-15 18:00 ET")
    assert "kickoff_clock" not in rows[50547] and rows[50547]["call"] == "PLAY"
    assert out["desk_meta"]["kickoff_clock_rule"] is True
    page = {x["match_id"]: x for x in closing.desk_rows(doc, {50546, 50547}, NOW, fam="MLB")}
    assert page[50546]["call"] == "PASS" and page[50546]["reason"] == REASON_50546     # the page's line names both


def test_the_cockpit_shows_the_kind_as_it_shows_the_other_no_call_kinds():
    html = open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()
    tag = re.search(r"function passKindTag\(k\)\{(.*?)\n\}", html, re.S).group(1)
    assert 'k==="kickoff_clock"' in tag and "kickoff disputed" in tag
    pol = re.search(r"function policy\(\)\{(.*?)\n\}", html, re.S).group(1)
    assert 'passKind==="kickoff_clock"' in pol and 'reasons.join(" · ")' in pol
