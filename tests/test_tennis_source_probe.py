"""The tennis source probe (ARCHITECT 2026-11-05 11:40 ET, addendum 261 item 2(b); lane tennis-market-only, #838):
the exact rule and its ambiguity refusals, the results-file reader (csv, a stdlib xlsx, a legacy .xls refused), the
date-format read, the Kalshi pair and day, the exit codes, the key that is never read or printed, and a run that opens
no database and writes nothing but its --out.

EVERY RESPONSE HERE IS SYNTHETIC: shaped by the providers' documented field names, never a real answer. The tickers
(SYNTH...), players, dates, prices and pages are invented for the test and are not facts about any source; no real
ticker, player, fee or column value is asserted. The HTTP layer is replaced; no network is reached."""
import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import tennis_source_probe as tsp  # noqa: E402

KB = tsp.KALSHI_BASE
INDEX = "https://synthetic.example/index"
ATP = "https://synthetic.example/files/synthetic-atp.csv"
WTA = "https://synthetic.example/files/synthetic-wta.csv"
SENTINEL = "SENTINEL-KEY-0123456789"
WEEK = "2026-11-02"


def ev(event, names, day=None, why=None):
    return {"event": event, "names": names, "why": why, "day": day or date(2026, 11, 3)}


def row(a, b, day=date(2026, 11, 3), tour="ATP"):
    return {"tour": tour, "a": a, "b": b, "day": day}


# ---------------------------------------------------------------------------------------------------- the exact rule --

def test_one_key_rule_reads_both_forms_on_either_side():
    """Rule (1)-(2): one rule for both sides, by the served name's shape, so the key does not assume which side
    serves which form (261: "surname + initial on the venue, full names elsewhere"; no answer has been read)."""
    assert tsp.name_key("Ann Bee Cee") == ("bee cee a.", tsp.FULL)
    assert tsp.name_key("Bee Cee A.") == ("bee cee a.", tsp.INITIAL)
    assert tsp.name_key("  Zoë   Ñáñez ") == ("nanez z.", tsp.FULL)                 # accents removed, spaces collapsed
    assert tsp.name_key("Mononym") == (None, tsp.ONE_WORD) and tsp.name_key("") == (None, tsp.ONE_WORD)
    assert tsp.name_key("De  Synth A.") == ("de synth a.", tsp.INITIAL)
    assert tsp.name_key("Synth-Name A.B.") == ("synth-name a.", tsp.INITIAL)
    assert tsp.name_key("Synth Ch.") == ("synth c.", tsp.INITIAL) == (tsp.name_key("Charlie Synth")[0], tsp.INITIAL)
    assert tsp.name_key("Ann De Synth")[0] == tsp.name_key("De Synth A.")[0]
    assert tsp.name_key("Bee A") == ("a b.", tsp.FULL)                  # no full stop: not an initial, read as full


def test_the_count_resolves_in_either_orientation():
    """261's own wording (surname + initial on the venue, full names in the file) and the reverse both resolve."""
    e = [ev("SYNTHMATCHX-26NOV03AAA", ["Bee A.", "Dee C."])]
    r = tsp.match_week(e, [row("Ann Bee", "Cid Dee")], date(2026, 11, 2))
    assert r["matched"] == 1
    assert r["name_shapes"] == {"kalshi": {tsp.INITIAL: 2}, "results": {tsp.FULL: 2}}
    e = [ev("SYNTHMATCHX-26NOV03AAA", ["Ann Bee", "Cid Dee"])]
    r = tsp.match_week(e, [row("Dee C.", "Bee A.")], date(2026, 11, 2))
    assert r["matched"] == 1 and r["name_shapes"] == {"kalshi": {tsp.FULL: 2}, "results": {tsp.INITIAL: 2}}


def test_one_row_fitting_two_events_is_refused_and_a_repeated_event_counts_once():
    events = [ev("SYNTHMATCHX-26NOV03AAA", ["Ann Bee", "Cid Dee"]),
              ev("SYNTHMATCHX-26NOV04AAB", ["Ann Bee", "Cid Dee"], date(2026, 11, 4))]
    r = tsp.match_week(events, [row("Dee C.", "Bee A.")], date(2026, 11, 2))
    assert (r["events"], r["matched"], r["refused_ambiguous"]) == (2, 0, 2)
    assert r["reasons"] == {"one results row fits two Kalshi events": 2}
    r = tsp.match_week(events[:1] * 2, [row("Dee C.", "Bee A.")], date(2026, 11, 2))
    assert (r["events"], r["matched"], r["refused_ambiguous"]) == (1, 1, 0)


def test_matched_unmatched_and_unreadable_are_counted_by_the_rule():
    events = [ev("SYNTHMATCHX-26NOV03AAA", ["Ann Bee", "Cid Dee"]),          # matched (order irrelevant)
              ev("SYNTHMATCHX-26NOV04BBB", ["Eve Fay", "Gus Hal"], date(2026, 11, 4)),   # no row: unmatched
              ev("SYNTHMATCHX-26NOV05CCC", ["Ivy Jo"], why=tsp.km.NO_PAIR),            # the pair's refusal
              ev("SYNTHMATCHX-26NOV05DDD", ["Kip", "Lou Moe"]),                        # one word: no key
              ev("SYNTHMATCHX-26NOV20EEE", ["Ann Bee", "Cid Dee"], date(2026, 11, 20))]  # outside the week
    rows = [row("Dee C.", "Bee A."), row("Fay E.", "Hal Q.", tour="WTA")]
    r = tsp.match_week(events, rows, date(2026, 11, 2))
    assert (r["events"], r["matched"], r["unmatched"], r["refused_unreadable"], r["refused_ambiguous"]) == (4, 1, 1, 2, 0)
    assert r["matched_by_tour"] == {"ATP": 1}
    assert r["reasons"][tsp.km.NO_PAIR] == 1 and r["reasons"]["a name of one word"] == 1
    assert r["unmatched_sample"] == ["SYNTHMATCHX-26NOV04BBB 2026-11-04: Eve Fay -> 'fay e.' · Gus Hal -> 'hal g.'"]


def test_ambiguity_is_refused_never_chosen():
    """Two players mapping to one key, on either side, and two rows fitting one pair: refused-ambiguous."""
    events = [ev("SYNTHMATCHX-26NOV03AAA", ["Jan Novsynth", "Ott Pim"]),
              ev("SYNTHMATCHX-26NOV04BBB", ["Jiri Novsynth", "Rex Sam"], date(2026, 11, 4)),   # same key 'novsynth j.'
              ev("SYNTHMATCHX-26NOV04CCC", ["Abe Twin", "Ari Twin"], date(2026, 11, 4)),       # one event, one key
              ev("SYNTHMATCHX-26NOV05DDD", ["Una Vex", "Wes Yul"], date(2026, 11, 5)),         # file: two spellings
              ev("SYNTHMATCHX-26NOV06EEE", ["Zed Ack", "Bo Cue"], date(2026, 11, 6))]          # two rows fit
    rows = [row("Novsynth J.", "Pim O."), row("Novsynth J.", "Sam R."),
            row("Vex U.", "Yul W."), row("Véx U.", "Other Z.", tour="WTA"),
            row("Ack Z.", "Cue B.", date(2026, 11, 5)), row("Cue B.", "Ack Z.", date(2026, 11, 6), tour="WTA")]
    r = tsp.match_week(events, rows, date(2026, 11, 2))
    assert (r["matched"], r["unmatched"], r["refused_ambiguous"]) == (0, 0, 5)
    assert r["reasons"] == {"a key two Kalshi names give in the week": 2, "both players map to one key": 1,
                            "a key two results-file names give": 1, "2 results rows fit the pair": 1}
    assert any("'novsynth j.' <- Jan Novsynth, Jiri Novsynth" in x for x in r["refused_sample"])
    assert any("'vex u.' <- Vex U., Véx U." in x for x in r["refused_sample"])


def test_the_row_window_is_seven_days_before_through_one_after():
    e = [ev("SYNTHMATCHX-26NOV05AAA", ["Ann Bee", "Cid Dee"], date(2026, 11, 5))]
    for d, hit in ((date(2026, 10, 29), True), (date(2026, 10, 28), False), (date(2026, 11, 6), True),
                   (date(2026, 11, 7), False)):
        assert tsp.match_week(e, [row("Bee A.", "Dee C.", d)], date(2026, 11, 2))["matched"] == int(hit), d


# ------------------------------------------------------------------------------------------------------ results side --

CSV_HEADER = "Tour,Location,Date,Winner,Loser,W1,L1,W2,L2,Wsets,Lsets,Comment,SyBkW,SyBkL,WRank,LRank"


def csv_file(rows):
    return (CSV_HEADER + "\n" + "\n".join(rows) + "\n").encode()


ATP_CSV = csv_file(["1,Synthville,03/11/2026,Dee C.,Bee A.,6,4,6,3,2,0,Completed,1.55,2.45,10,20",
                    "1,Synthville,13/10/2026,Qux A.,Zap B.,6,1,2,0,1,0,Retired,1.20,4.10,5,90",
                    "1,Synthville,14/10/2026,Mop C.,Nib D.,,,,,0,0,Walkover,,,7,8"])
WTA_CSV = csv_file(["2,Synthtown,24/10/2026,Fay E.,Hal Q.,7,5,6,2,2,0,Completed,1.90,1.90,3,4"])


def xlsx_bytes(rows, date1904=False):
    """A minimal synthetic workbook: shared strings, numbers stored as numbers, one sheet."""
    strings, idx = [], {}

    def si(v):
        if v not in idx:
            idx[v] = len(strings)
            strings.append(v)
        return idx[v]
    xml_rows = []
    for r, vals in enumerate(rows, 1):
        cells = []
        for c, v in enumerate(vals):
            ref = chr(65 + c) + str(r)
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            elif v is not None:
                cells.append(f'<c r="{ref}" t="s"><v>{si(v)}</v></c>')
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel}><workbookPr date1904="{int(date1904)}"/><sheets>'
                                      '<sheet name="SynthSheet" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    return buf.getvalue()


def test_read_table_csv_xlsx_zip_and_refusals():
    h, rows, info = tsp.read_table(ATP_CSV)
    assert h == CSV_HEADER.split(",") and len(rows) == 3 and info["form"].startswith("csv (utf-8")
    xb = xlsx_bytes([["Date", "Winner", "Loser", "Comment"], [46329, "Dee C.", "Bee A.", "Completed"]])
    h, rows, info = tsp.read_table(xb)
    assert h == ["Date", "Winner", "Loser", "Comment"] and rows == [["46329", "Dee C.", "Bee A.", "Completed"]]
    assert info["form"] == "xlsx" and info["sheet"] == "SynthSheet" and info["date1904"] is False
    fmt, parse = tsp.date_reader(["46329"], info)
    assert fmt.startswith("Excel serial day numbers (the workbook's 1900 date system)")
    assert parse("46329") == date(2026, 11, 3)
    assert tsp.excel_day("0", True) == date(1904, 1, 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("synthetic.csv", ATP_CSV)
    h, rows, info = tsp.read_table(buf.getvalue())
    assert info["form"].startswith("zip member synthetic.csv: csv") and len(rows) == 3
    with pytest.raises(tsp.Refused, match="legacy Excel .xls"):
        tsp.read_table(tsp.XLS_MAGIC + b"\x00" * 64)
    with pytest.raises(tsp.Refused, match="an HTML page"):
        tsp.read_table(b"  <html><body>not a file</body></html>")


def test_the_date_format_is_read_never_guessed():
    fmt, parse = tsp.date_reader(["13/10/2026", "03/11/2026"], {"form": "csv"})
    assert fmt.startswith("%d/%m/%Y") and parse("03/11/2026") == date(2026, 11, 3)
    with pytest.raises(tsp.Refused, match="ambiguous"):
        tsp.date_reader(["03/04/2026", "05/06/2026"], {"form": "csv"})      # d/m and m/d give different dates
    fmt, _ = tsp.date_reader(["2026-11-03"], {"form": "csv"})
    assert fmt.startswith("%Y-%m-%d ")
    with pytest.raises(tsp.Refused, match="parse under none"):
        tsp.date_reader(["Tuesday"], {"form": "csv"})


def test_roles_from_the_header_or_the_flags_and_a_miss_refuses():
    found, missing = tsp.roles(CSV_HEADER.split(","))
    assert found == {"date": "Date", "player_a": "Winner", "player_b": "Loser"} and missing == []
    found, missing = tsp.roles(["When", "P_A", "P_B"])
    assert missing == ["date", "player_a", "player_b"]
    found, missing = tsp.roles(["When", "P_A", "P_B"], "When", ["P_A", "P_B"])
    assert missing == [] and found["player_b"] == "P_B"
    assert tsp.wl_pairs(CSV_HEADER.split(",")) == (["SyBk"], ["1", "2", "Rank", "sets"])


# ------------------------------------------------------------------------------------------------------- Kalshi side --

def mk(ticker, event, name, status="open", **extra):
    return {"ticker": ticker, "event_ticker": event, "status": status, "title": "Synthetic match title",
            "yes_sub_title": name, "occurrence_datetime": "2026-11-03T12:00:00Z",
            "close_time": "2026-11-04T12:00:00Z", **extra}


EV1, EV2 = "SYNTHMATCHX-26NOV03AAABBB", "SYNTHMATCHX-26NOV04EEEGGG"
OPEN = [mk(EV1 + "-AAA", EV1, "Ann Bee"), mk(EV1 + "-BBB", EV1, "Cid Dee"),
        mk(EV2 + "-EEE", EV2, "Eve Fay"), mk(EV2 + "-GGG", EV2, "Gus Hal")]
SETTLED = [mk("SYNTHMATCHX-26NOV05QQQZZZ-QQQ", "SYNTHMATCHX-26NOV05QQQZZZ", "Qi Quo", status="settled")]


def test_event_pairs_use_the_shared_matchers_pair_and_day_rule():
    got = {p["event"]: p for p in tsp.event_pairs(OPEN + OPEN[:1] + SETTLED)}      # a repeated market counted once
    assert got[EV1]["names"] == ["Ann Bee", "Cid Dee"] and got[EV1]["why"] is None
    assert got[EV1]["day"] == date(2026, 11, 3)
    assert got["SYNTHMATCHX-26NOV05QQQZZZ"]["why"] == tsp.km.NO_PAIR       # one name: never a pair
    assert tsp.zone_of("2026-11-03T12:00:00Z") == "Z" and tsp.zone_of("2026-11-03T07:00:00-05:00") == "offset -05:00"
    assert tsp.zone_of("2026-11-03 12:00") == "no zone stated" and tsp.zone_of(1762171200) == "epoch seconds"


# --------------------------------------------------------------------------------------------------------- the runs --

TERMS = "https://synthetic.example/synthterms.html"
INDEX_HTML = (b"<html><head><style>x{}</style><script>var k=1;</script></head><body><h1>Synthetic results index</h1>"
              b"<p>Synthetic index text.</p>"
              b"<a href='files/synthetic-atp.csv'>ATP synthetic</a> <a href='files/synthetic-wta.csv'>WTA synth</a>"
              b"<a href='about.html'>about</a> <a href='synthterms.html'>SYNTH Terms of use</a>"
              b"<a href='synthfixtures.php'>SYNTH fixtures</a></body></html>")
TERMS_HTML = (b"<html><head><script>var k=1;</script></head><body>"
              b"<p>Synthetic terms line: these files are synthetic test data.</p></body></html>")
SERIES = {"series": [{"ticker": "SYNTHMATCHX", "title": "Synthetic tennis match", "category": "Sports",
                      "tags": ["Tennis"]},
                     {"ticker": "SYNTHTOURNEY", "title": "Synthetic tennis tournament winner", "category": "Sports",
                      "tags": ["Tennis"]},
                     {"ticker": "SYNTHGOLF", "title": "Synthetic golf", "category": "Sports", "tags": ["Golf"]}]}


def fake_http(seen=None, series=SERIES, status_for=None, settled=SETTLED, open_=OPEN):
    def get(url, params=None):
        if seen is not None:
            seen.append((url, dict(params or {})))
        if status_for and status_for(url):
            return status_for(url), {}, b"denied"
        rl = {"X-Synthetic-RateLimit-Remaining": "99", "Content-Type": "application/json"}
        if url == f"{KB}/series":
            return 200, rl, json.dumps(series).encode()
        if url == f"{KB}/events":
            return 200, rl, json.dumps({"events": [{"event_ticker": EV1, "title": "Synthetic event",
                                                    "sub_title": "Ann Bee vs Cid Dee",
                                                    "strike_date": "2026-11-03T12:00:00Z"}]}).encode()
        if url == f"{KB}/markets":
            st = (params or {}).get("status")
            return 200, rl, json.dumps({"markets": open_ if st == "open" else settled if st == "settled" else [],
                                        "cursor": ""}).encode()
        if url == INDEX:
            return 200, {}, INDEX_HTML
        if url == TERMS:
            return 200, {}, TERMS_HTML
        if url == ATP:
            return 200, {}, ATP_CSV
        if url == WTA:
            return 200, {}, WTA_CSV
        return 404, {}, b""
    return get


TODAY = date(2026, 11, 20)        # a fixed "today" after the synthetic week: the week is completed


def run(args, get, capsys, today=TODAY):
    rc = tsp.main(args, get=get, today=today)
    return rc, capsys.readouterr().out


FULL = ["--week", WEEK, "--index-url", INDEX, "--atp-url", ATP, "--wta-url", WTA, "--terms-url", TERMS]


def test_the_whole_run_on_synthetic_answers(tmp_path, capsys):
    seen = []
    out_file = tmp_path / "receipt.json"
    rc, out = run(FULL + ["--out", str(out_file)], fake_http(seen), capsys)
    assert rc == 0, out
    assert "KEYS: none read, none sent, none printed" in out
    assert "    SYNTHMATCHX                  'Synthetic tennis match'" in out
    assert "selected by the rule (ticker or title says 'match'): SYNTHMATCHX" in out      # the tourney one is not
    assert "SYNTHGOLF" not in out.split("K2 FIXTURES")[0]                                  # the adapter's filter
    assert "status words as served: open 4" in out and "time field occurrence_datetime: Z 4" in out
    assert f"event {EV1} · ticker date 2026-11-03 · players (the shared matcher's pair): Ann Bee / Cid Dee" in out
    assert "strike_date = '2026-11-03T12:00:00Z' (Z)" in out
    assert "SYNTHMATCHX /markets status=settled: 1 markets, 1 page(s)" in out
    assert "SYNTHMATCHX status words as served, every market read (open, closed, settled): open 4, settled 1" in out
    assert "R1 schedule links on the index page (by the rule, as served; not fetched): " \
           "https://synthetic.example/synthfixtures.php  [SYNTH fixtures]" in out
    assert f"    {ATP}  [ATP synthetic]" in out and "about.html" not in out.split("R2 TERMS")[0].split("R1")[1]
    assert "HEADER (16 columns, as served): Tour | Location | Date | Winner" in out
    assert "result-shape column 'Comment', distinct values as served: 'Completed' 1, 'Retired' 1, 'Walkover' 1" in out
    assert "W/L column pairs by suffix (candidate closing-price pairs; filled, decimal-price-like): SyBkW/SyBkL (2/2, 2/2)" in out
    assert "roles for the match count (law-1 receipt): date<-'Date' · player_a<-'Winner' · player_b<-'Loser'" in out
    assert "date format: %d/%m/%Y (as text, e.g. '03/11/2026')" in out
    assert "name format (6 distinct names in 'Winner' and 'Loser'): surname + initial(s) 6" in out
    assert f"R2 TERMS · {TERMS}" in out
    assert "Synthetic terms line: these files are synthetic test data." in out and "var k=1" not in out
    assert "name shapes · Kalshi (the week's events): full name 5 · results files (rows near the week): " \
           "surname + initial(s) 2" in out
    assert ("Kalshi events in the week 3 · matched 1 · refused-ambiguous 0 · refused-unreadable 1 · unmatched 1"
            in out)
    assert "matched by tour: ATP 1" in out
    assert "X-Synthetic-RateLimit-Remaining: 99" in out
    assert "the tours' own sites" in out and "not fetched by this probe (Code's choice" in out
    assert "TENNIS-SOURCE-PROBE exit 0" in out
    doc = json.loads(out_file.read_text())
    assert doc["match_count"]["matched"] == 1 and doc["kalshi"]["selected"] == ["SYNTHMATCHX"]
    assert doc["results"][0]["url"] == ATP and "text" in doc["terms"] and doc["terms"]["url"] == TERMS
    assert doc["kalshi"]["week_markets"]["SYNTHMATCHX"]["status_words"] == {"open": 4, "settled": 1}
    assert doc["match_count"]["name_shapes"]["kalshi"] == {"full name": 5}
    assert all(u.startswith(("https://synthetic.example/", KB)) for u, _ in seen)        # nothing else reached
    assert sorted(p.name for p in tmp_path.iterdir()) == ["receipt.json"]                  # the file is not stored


def test_the_key_is_never_read_sent_or_printed(tmp_path, capsys, monkeypatch):
    for name in ("API_FOOTBALL_KEY", "API_TENNIS_KEY", "KALSHI_API_KEY_ID", "API_BASKETBALL_KEY"):
        monkeypatch.setenv(name, SENTINEL)
    out_file = tmp_path / "r.json"
    rc, out = run(FULL + ["--out", str(out_file)], fake_http(), capsys)
    assert rc == 0 and SENTINEL not in out and SENTINEL not in out_file.read_text()
    sent = []

    class Resp:
        status_code, headers, content = 200, {"x-ratelimit-remaining": "1"}, b"{}"

    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kw: sent.append((url, kw)) or Resp())
    assert tsp.http_get(f"{KB}/series", {"category": "Sports"}) == (200, {"x-ratelimit-remaining": "1"}, b"{}")
    (url, kw), = sent
    assert SENTINEL not in json.dumps(kw) and not any(h.lower() in ("authorization", "x-apisports-key")
                                                      or "key" in h.lower() for h in kw["headers"])


@pytest.mark.parametrize("args,why", [
    (["--week", "2026-13-01"], "is not an ISO date"),
    (FULL + ["--player-cols", "OnlyOne"], "--player-cols takes two column names"),
    (["--week", "2026-11-14"] + FULL[2:], "is not a completed week"),        # 11-14 .. 11-20, today 11-20
])
def test_argument_refusals_exit_2_before_any_call(args, why, capsys):
    seen = []
    rc, out = run(args, fake_http(seen), capsys)
    assert rc == 2 and why in out and seen == []


def test_out_under_data_is_refused_before_any_call(tmp_path, capsys):
    seen = []
    rc, out = run(FULL + ["--out", str(tmp_path / "data" / "r.json")], fake_http(seen), capsys)
    assert rc == 2 and "under a data/ directory (law 5)" in out and seen == []
    assert not (tmp_path / "data").exists()


def test_a_tour_without_its_url_is_not_chosen_and_exits_2(capsys):
    rc, out = run(["--week", WEEK, "--index-url", INDEX, "--atp-url", ATP], fake_http(), capsys)
    assert rc == 2
    assert "WTA results file: NOT READ (no --wta-url given)" in out
    assert "REFUSED: R1 WTA: no --wta-url (the probe does not choose a file from the index)" in out
    assert "M THE MATCH COUNT" in out and "NOT RUN: results file(s) not read: WTA" in out


def test_no_match_level_series_refuses_and_names_the_listing(capsys):
    series = {"series": [{"ticker": "SYNTHTOURNEY", "title": "Synthetic tennis tournament winner",
                          "category": "Sports", "tags": ["Tennis"]}]}
    rc, out = run(FULL, fake_http(series=series), capsys)
    assert rc == 2 and "pass --series from the listing above (never guessed)" in out
    rc, out = run(FULL + ["--series", "SYNTHTOURNEY"], fake_http(series=series), capsys)     # from the listing: read
    assert rc == 0 and "selected by --series: SYNTHTOURNEY\n" in out
    rc, out = run(FULL + ["--series", "SYNTHMATCHX"], fake_http(series=series), capsys)      # not in it: refused
    assert rc == 2 and "selected by --series: SYNTHMATCHX (NOT in the listing)" in out
    assert "REFUSED: K1: --series SYNTHMATCHX is not in the tennis listing above" in out


def test_a_denied_network_exits_1_with_every_call_listed(capsys):
    rc, out = run(FULL, fake_http(status_for=lambda url: 403), capsys)
    assert rc == 1
    assert "FAILED: K1: the series listing was not read" in out
    assert f"GET {INDEX} · HTTP 403" in out and f"GET {ATP} · HTTP 403" in out
    assert "TENNIS-SOURCE-PROBE exit 1" in out


def test_a_legacy_xls_file_is_refused_with_the_dependency_named(capsys):
    def get(url, params=None):
        return (200, {}, tsp.XLS_MAGIC + b"\x00" * 64) if url == WTA else fake_http()(url, params)
    rc, out = run(FULL, get, capsys)
    assert rc == 2 and "REFUSED: R1 WTA: a legacy Excel .xls file (OLE2): reading it needs a reader dependency (xlrd)" in out


def test_the_script_opens_no_database_and_writes_nothing(tmp_path):
    """Run in a clean interpreter from an empty directory: no src.db / sqlalchemy module is imported, no file
    appears (the network is replaced by a 403 for every call)."""
    work = tmp_path / "cwd"
    work.mkdir()
    code = ("import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('p', {str(ROOT / 'scripts' / 'tennis_source_probe.py')!r})\n"
            "p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)\n"
            "rc = p.main(['--week', '2026-10-19', '--atp-url', 'https://x.invalid/a', '--wta-url', "
            "'https://x.invalid/w'], get=lambda url, params=None: (403, {}, b''))\n"
            "assert rc == 1, rc\n"
            "bad = sorted(m for m in sys.modules if m.startswith(('src.db', 'sqlalchemy')))\n"
            "assert not bad, bad\n"
            "print('CLEAN')\n")
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    p = subprocess.run([sys.executable, "-c", code], cwd=work, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip().endswith("CLEAN")
    assert list(work.iterdir()) == []


# ------------------------------------------------------------------------------------------------------------ the lane --

def test_the_lane_is_appended_with_261s_dates_and_no_date_moved():
    """Addendum 261 item 3: "The roadmap gains the two lanes with the dates above (no existing date moves)"; item 2's
    dates: the probe 11-14, the wiring 12-12, the first PAPER record at the United Cup 12-28, the history pot 01-10."""
    from src import roadmap as rm
    doc = rm.load()
    names = [x["lane"] for x in doc["lanes"]]
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "tennis-market-only"]
    assert names.index("tennis-market-only") > names.index("soccer-v23")          # appended after every older lane
    assert ln["issue"] == 838 and ln["registry_id"] is None and ln["competitions"] == ["ATP", "WTA"]
    assert ln["state"] in rm.STATES and ln["state"] == "to declare"
    # addendum 269 item 5 / 270 item 6 (the records PR): "the 11-14 probe step DONE on the stage-1 receipt"
    assert [(s["owner"], s["due"], s["done"] and s["done"]["date"]) for s in ln["steps"]] == [
        ("code", "2026-11-14", "2026-11-06"), ("code", "2026-12-12", "2026-11-07"), ("operator", "2026-12-28", None)]
    # addendum 286 item 4(f): the wiring step DONE EARLY (11-07, #868); its due stays as the record (222 item 3(a));
    # addendum 287 item 2: the undated step is a live_needs note (the validator has no undated step)
    assert "#868 merged 2026-11-07" in ln["steps"][1]["done"]["receipt"]
    assert "the retraction fix; the timer enabled by the architect's block after both" in ln["live_needs"]
    # addendum 289 item 1(a)-(b): the undated step's text beside 288 item 1's RULED sentences; 288 item 3's clause
    assert ("the kickoff = the served occurrence_datetime; the retraction fix; the expiration_value shape read; the "
            "timer enabled by the architect's block after the stored receipt") in ln["live_needs"]
    assert "RULED: a tennis row's kickoff = the event's occurrence_datetime, as served, UTC;" in ln["live_needs"]
    assert "This market will close and expire after a winner is declared." in ln["live_needs"]
    # addenda 278 item 1 and 282 item 5: the history-pot step (2027-01-10) removed on 270 item 5, quoted in live_needs
    # (a step is "removed by a quoted ruling", addendum 61 item 4; no moved line, whose now may be null only for
    # earliest_live)
    assert not any(s["what"].startswith("the history pot") for s in ln["steps"])
    assert "THE HISTORY-POT STEP (due 2027-01-10) REMOVED by a quoted ruling" in ln["live_needs"]
    assert "no model lane exists, so no backfill is scheduled" in ln["live_needs"]
    assert "#838 issuecomment-6690719842" in ln["steps"][0]["done"]["receipt"]
    assert ln["steps"][0]["what"].startswith("the provider probe (addendum 261 item 2(b))")
    assert "scripts/tennis_source_probe.py" in ln["steps"][0]["what"]
    assert ln["earliest_live"] is None and ln["moved"] == []
    assert "A MODEL: NONE DECLARED." in ln["live_needs"] and ln["vs_close"].startswith("n/a: no model")
    assert rm.validate(doc) == []


# ------------------------------------------------------------------------------------- the review's round-1 defects --

def test_settled_markets_status_words_and_result_fields_are_printed(tmp_path, capsys):
    settled = [mk("SYNTHMATCHX-26NOV05QQQZZZ-QQQ", "SYNTHMATCHX-26NOV05QQQZZZ", "Qi Quo", status="finalizedSYNTHWORD",
                  result="yesSYNTHRESULT", settlement_value=100, expiration_value="SYNTHEXPV",
                  settlement_ts="2026-11-06T00:00:00Z"),
               mk("SYNTHMATCHX-26NOV05QQQZZZ-ZZZ", "SYNTHMATCHX-26NOV05QQQZZZ", "Zo Zed", status="finalizedSYNTHWORD",
                  result="noSYNTHRESULT", settlement_value=0)]
    out_file = tmp_path / "r.json"
    rc, out = run(FULL + ["--out", str(out_file)], fake_http(settled=settled), capsys)
    assert rc == 0, out
    assert "status words as served, every market read (open, closed, settled): finalizedSYNTHWORD 2, open 4" in out
    assert "a market read under status=settled, keys served: close_time, event_ticker, expiration_value, occurrence_datetime, result" in out
    assert "result / settlement field 'result', distinct values as served: 'noSYNTHRESULT' 1, 'yesSYNTHRESULT' 1" in out
    assert "result / settlement field 'settlement_value', distinct values as served: 0 1, 100 1" in out
    assert "result / settlement field 'expiration_value', distinct values as served: 'SYNTHEXPV' 1" in out
    assert "field 'settlement_ts'" not in out                                   # a settlement time is not a result
    wm = json.loads(out_file.read_text())["kalshi"]["week_markets"]["SYNTHMATCHX"]
    assert wm["settled_fields"]["result"] == {"noSYNTHRESULT": 1, "yesSYNTHRESULT": 1}


def test_terms_without_terms_url_are_not_read_and_the_candidates_are_named(capsys):
    rc, out = run(FULL[:-2], fake_http(), capsys)
    assert rc == 2
    assert ("R2 TERMS: not read (no --terms-url; candidate links: https://synthetic.example/synthterms.html "
            "[SYNTH Terms of use])") in out
    assert "BEGIN PAGE TEXT" not in out and "Synthetic index text." not in out
    rc, out = run(FULL[:-2] + ["--terms-url", INDEX], fake_http(), capsys)
    assert rc == 0 and "--terms-url names the index page itself" in out and "Synthetic index text." in out


def test_no_kalshi_event_in_the_week_refuses_the_count(capsys):
    dateless = [mk("SYNTHMATCHX-NODATE-AAA", "SYNTHMATCHX-NODATE", "Ann Bee"),
                mk("SYNTHMATCHX-NODATE-BBB", "SYNTHMATCHX-NODATE", "Cid Dee")]
    rc, out = run(FULL, fake_http(open_=dateless, settled=[]), capsys)
    assert rc == 2 and "M: not run: 0 Kalshi events dated in the week; 1 read, 1 with no date in the ticker" in out
    rc, out = run(["--week", "2026-10-05"] + FULL[2:], fake_http(), capsys)
    assert rc == 2 and "M: not run: 0 Kalshi events dated in the week; 3 read, 0 with no date in the ticker" in out


@pytest.mark.parametrize("where", ["missing", "dir"])
def test_an_out_path_that_cannot_be_written_refuses_before_any_call(tmp_path, capsys, where):
    seen = []
    target = tmp_path / "nodir" / "r.json" if where == "missing" else tmp_path
    rc, out = run(FULL + ["--out", str(target)], fake_http(seen), capsys)
    assert rc == 2 and seen == [] and "REFUSED: --out" in out


@pytest.mark.parametrize("bad", [{"series": None}, {"markets": None, "cursor": ""}, {"series": ["not-an-object"]}])
def test_an_answer_of_the_wrong_shape_fails_with_a_reason_never_a_traceback(capsys, bad):
    def get(url, params=None):
        key = next(iter(bad))
        if (key == "series" and url == f"{KB}/series") or (key == "markets" and url == f"{KB}/markets"):
            return 200, {}, json.dumps(bad).encode()
        return fake_http()(url, params)
    rc, out = run(FULL, get, capsys)
    assert rc == 1 and "TENNIS-SOURCE-PROBE exit 1" in out
    assert "is not a list of objects" in out


def test_an_xlsx_shared_string_cell_with_no_value_is_refused(capsys):
    xb = xlsx_bytes([["Date", "Winner", "Loser"], [46329, "Dee C.", "Bee A."]])
    zin = zipfile.ZipFile(io.BytesIO(xb))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "xl/worksheets/sheet1.xml":
                data = data.replace(b'<c r="B2" t="s"><v>3</v></c>', b'<c r="B2" t="s"><v></v></c>')
                assert b"<v></v>" in data
            z.writestr(n, data)

    def get(url, params=None):
        return (200, {}, buf.getvalue()) if url == WTA else fake_http()(url, params)
    rc, out = run(FULL, get, capsys)
    assert rc == 2 and "REFUSED: R1 WTA: the file did not read as its form says (TypeError" in out


def test_a_series_given_twice_is_read_once(capsys):
    _, once = run(FULL + ["--series", "SYNTHMATCHX"], fake_http(), capsys)
    seen = []
    rc, twice = run(FULL + ["--series", "SYNTHMATCHX", "--series", "SYNTHMATCHX"], fake_http(seen), capsys)
    line = "Kalshi events in the week 3 · matched 1 · refused-ambiguous 0 · refused-unreadable 1 · unmatched 1"
    assert line in once and line in twice and rc == 0
    assert "selected by --series: SYNTHMATCHX (NOT in the listing)" not in twice
    assert sum(1 for u, p in seen if u == f"{KB}/markets" and p.get("status") == "settled") == 1


# ------------------------------------------------------------------------------------------- review round 1 (P2s) --

def test_a_status_whose_pages_pass_max_pages_refuses_the_run(capsys, monkeypatch):
    """A cursor still left at MAX_PAGES is an incomplete market set: a refusal (exit 2), never an exit-0 count."""
    monkeypatch.setattr(tsp, "MAX_PAGES", 2)
    seen = []

    def get(url, params=None):
        if url == f"{KB}/markets" and (params or {}).get("status") == "closed":
            seen.append(params.get("cursor"))
            return 200, {}, json.dumps({"markets": [], "cursor": f"SYNTHCURSOR{len(seen)}"}).encode()
        return fake_http()(url, params)
    rc, out = run(FULL, get, capsys)
    assert seen == [None, "SYNTHCURSOR1"]                                 # MAX_PAGES pages read, then stopped
    assert rc == 2, out
    assert ("REFUSED: K3 SYNTHMATCHX status=closed: MAX_PAGES 2 reached with a cursor left: the market set is "
            "incomplete") in out


def test_a_series_override_absent_from_the_listing_is_refused_before_its_markets(capsys):
    """--series must name a ticker the tennis listing serves; one it does not is refused, never read as tennis."""
    seen = []
    rc, out = run(FULL + ["--series", "SYNTHMATCHX", "--series", "SYNTHGOLF"], fake_http(seen), capsys)
    assert rc == 2, out
    assert "REFUSED: K1: --series SYNTHGOLF is not in the tennis listing above" in out
    assert not [u for u, _ in seen if u in (f"{KB}/events", f"{KB}/markets")]


def _unwritable_targets(tmp_path):
    out = []
    if Path("/sys/kernel").is_dir():
        out.append(Path("/sys/kernel") / "synthetic_tennis_receipt.json")     # unwritable even for root
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        ro_dir = tmp_path / "ro"
        ro_dir.mkdir()
        ro_dir.chmod(0o500)
        ro_file = tmp_path / "ro_file.json"
        ro_file.write_text("{}")
        ro_file.chmod(0o400)
        out += [ro_dir / "r.json", ro_file]
    return out


def test_an_out_that_exists_but_cannot_be_written_refuses_before_any_call(tmp_path, capsys):
    targets = _unwritable_targets(tmp_path)
    if not targets:
        pytest.skip("no unwritable target on this platform")
    for target in targets:
        seen = []
        rc, out = run(FULL + ["--out", str(target)], fake_http(seen), capsys)
        assert rc == 2 and seen == [], (target, out)
        assert f"REFUSED: --out {target} cannot be written" in out


def test_a_writable_out_is_checked_without_leaving_a_file_or_changing_one(tmp_path, capsys):
    new = tmp_path / "new.json"
    assert tsp.refuse_out(str(new)) is None and not new.exists()
    old = tmp_path / "old.json"
    old.write_text("synthetic")
    assert tsp.refuse_out(str(old)) is None and old.read_text() == "synthetic"


def test_a_dangling_symlink_out_is_checked_without_leaving_its_target_or_removing_the_link(tmp_path):
    link = tmp_path / "link"
    link.symlink_to("target.json")                           # dangling: target.json does not exist
    assert tsp.refuse_out(str(link)) is None
    assert sorted(x.name for x in tmp_path.iterdir()) == ["link"], sorted(x.name for x in tmp_path.iterdir())
    assert link.is_symlink() and not (tmp_path / "target.json").exists()
