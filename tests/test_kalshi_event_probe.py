"""ARCHITECT 2026-10-10, addendum 37 item 2 (Law 1 first): the event payload probe. Fake fetch, no network."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kalshi_event_probe as kp  # noqa: E402

EV = "KXNCAAFGAME-26OCT10NDSUUNLV"
MK = [{"ticker": f"{EV}-NDSU", "event_ticker": EV, "status": "finalized", "title": "North Dakota St. wins",
       "yes_sub_title": "North Dakota St.", "occurrence_datetime": "2026-10-10T23:00:00Z",
       "close_time": "2026-10-11T05:00:00Z", "expected_expiration_time": "2026-10-11T02:30:00Z",
       "last_price": 99},
      {"ticker": f"{EV}-UNLV", "event_ticker": EV, "status": "finalized", "title": "UNLV wins",
       "yes_sub_title": "UNLV", "occurrence_datetime": "2026-10-10T23:00:00Z"}]


def fake(calls):
    def f(url):
        calls.append(url)
        if "/events/" in url:
            return {"event": {"event_ticker": EV, "title": "North Dakota St. at UNLV", "strike_date": None,
                              "series_ticker": "KXNCAAFGAME", "mutually_exclusive": True}}
        assert "markets?" in url and "event_ticker=" + EV in url and "status" not in url   # any status
        return {"markets": MK, "cursor": ""}
    return f


def test_every_time_field_is_printed_verbatim_and_names_beside_it():
    calls, lines = [], []
    c = kp.probe([EV], fetch=fake(calls), echo=lines.append)
    text = "\n".join(lines)
    assert c == {"events": 1, "markets": 2, "errors": 0}
    for want in ("occurrence_datetime = '2026-10-10T23:00:00Z'", "close_time = '2026-10-11T05:00:00Z'",
                 "expected_expiration_time = '2026-10-11T02:30:00Z'", "yes_sub_title='North Dakota St.'",
                 "title='UNLV wins'", "strike_date = None"):
        assert want in text
    assert "last_price" not in text                       # not a time field
    assert all(u.startswith(kp.BASE) for u in calls) and len(calls) == 2


def test_ticker_stamp_as_written_with_or_without_a_time():
    assert kp.ticker_stamp(EV) == {"stamp": "26OCT10", "yy": "26", "mon": "OCT", "dd": "10", "hhmm": None}
    assert kp.ticker_stamp("KXMLBGAME-26OCT101905NYYBOS")["hhmm"] == "1905"
    assert kp.ticker_stamp("nothing") == {"stamp": None}


def test_out_appends_one_json_line_per_event_with_the_raw_markets():
    buf = io.StringIO()
    kp.probe([EV, EV], fetch=fake([]), out=buf, echo=lambda *_: None)
    recs = [json.loads(x) for x in buf.getvalue().splitlines()]
    assert len(recs) == 2 and recs[0]["markets"] == MK and recs[0]["event"]["series_ticker"] == "KXNCAAFGAME"


def test_a_failed_get_is_reported_and_counted_never_hidden():
    def boom(url):
        raise OSError("403 Forbidden")
    lines = []
    c = kp.probe([EV], fetch=boom, echo=lines.append)
    assert c["errors"] == 2 and any("event GET failed: OSError: 403 Forbidden" in x for x in lines)


def test_the_default_events_are_the_receipts_nine():
    assert len(kp.RECEIPT_EVENTS) == 9 and all(e.startswith("KXNCAAFGAME-26OCT10") for e in kp.RECEIPT_EVENTS)
