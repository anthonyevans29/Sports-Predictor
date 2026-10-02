"""#91 RULED (ARCHITECT 2026-10-02): "a venue-edge row whose book capture is
older than 3h at decision time has NO reference (not stale-flagged, excluded)
— same PASS/no-ref class as absent books." Decision time = the Desk's as-of.
Pins: > 3h -> PASS / noref (never VENUE, never stale-flagged); exactly 3h and
fresher -> the pair is judged as before; no capture time -> the pre-ruling
path; the Next-24h card (window_venue) obeys the same rule."""
from datetime import datetime, timedelta, timezone

from src.walters import desk_policy as dp

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
MS = float((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))


def at(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).replace(tzinfo=None).isoformat()


def fx(captured_at, home="H"):
    mk = {"bookmaker_count": 6, "fair_prob": {"HOME": 0.60, "AWAY": 0.40}}     # books 60% vs Kalshi 50%: +10pp
    if captured_at is not None:
        mk["captured_at"] = captured_at
    return {"home_team": home, "away_team": "A", "utc_date": (NOW + timedelta(hours=2)).replace(tzinfo=None).isoformat(),
            "status": "scheduled", "market": mk,
            "kalshi": {"status": "two_sided", "prob": {"HOME": 0.50, "AWAY": 0.50}}}


def desk(captured_at):
    doc = dp.annotate({"competition_code": "NHL", "fixtures": [fx(captured_at)]}, now=NOW)
    return doc["fixtures"][0]["desk"]


def test_a_book_capture_older_than_3h_is_no_reference():
    d = desk(at(181))
    assert (d["call"], d["units"], d["pass_kind"]) == ("PASS", 0, "noref")
    assert d["reason"] == "books captured 3.0h ago > 3h — no reference"
    assert d["side"] is None and d["div_pp"] is None and d["stale_book_zone"] is False   # excluded, not flagged
    far = desk(at(60 * 26))
    assert far["pass_kind"] == "noref" and far["reason"].startswith("books captured 26.0h ago")


def test_exactly_3h_and_fresher_books_are_judged_as_before():
    for mins in (180, 120, 5):
        d = desk(at(mins))
        assert (d["call"], d["units"], d["side"]) == ("VENUE", 0.25, "HOME"), mins
        assert abs(d["div_pp"] - 10.0) < 1e-9 and d["stale_book_zone"] is True


def test_no_capture_time_keeps_the_pre_ruling_path():
    d = desk(None)
    assert d["call"] == "VENUE" and d["pass_kind"] is None


def test_absent_books_still_say_single_venue():
    row = fx(at(600))
    row["market"] = None
    doc = dp.annotate({"competition_code": "NHL", "fixtures": [row]}, now=NOW)
    assert doc["fixtures"][0]["desk"]["reason"] == "single venue — no pair"


def test_window_card_obeys_the_same_rule():
    row = {**fx(at(240)), "engine": "market_only", "competition": "NHL"}
    v = dp.window_venue(row, MS)
    assert (v["eligible"], v["kind"]) == (False, "noref") and "no reference" in v["reason"]
    row["market"]["captured_at"] = at(30)
    assert dp.window_venue(row, MS)["eligible"] is True
