"""The second wave's read (ARCHITECT addendum 565 item 3; DEV 3): read-only, counts only, on SYNTHETIC answers only.
Every series, title, team, label, plan, key and price below is invented for the test and labelled synthetic; no field
name here is confirmed against a live answer (the read exists to read them). HTTP is monkeypatched: no provider is
reached. The copy is a throwaway SQLite file under tmp_path with the schema's own column names (src/db/schema.py).

Pinned: kalshi prints counts and tickers and never a price, bid, ask, last, volume or open-interest value even when
the fake serves them; it opens and imports no database; a three-leg event with one Tie leg is counted; the cursor is
followed; a 429 is asked again and counted; the call cap and a failed listing are told apart. status makes exactly
one call, prints the plan and the daily limit, never the key value nor the account block. copy opens the copy through
mode=ro&immutable=1, refuses a path under data/ and a missing file, answers the whole-season list YES / NO without a
line of it, counts CZE's unfinished fixtures by label ("Championship Group - 1" playoff by addendum 456,
"Regular Season - 20" regular) and leaves the copy's bytes unchanged."""
import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "second_wave_read.py"
spec = importlib.util.spec_from_file_location("second_wave_read", SCRIPT)
swr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = swr
spec.loader.exec_module(swr)

KEY = "SYNTH-FOOTBALL-KEY-5d1e9b"                     # a synthetic secret: never in any output
# synthetic price-like values: none may appear in any output or receipt
PRICES = ("0.4137", "0.4291", "0.3377", "98765", "54321", "0.0613", "0.0711")
DECIMAL = re.compile(r"\b0?\.\d{2,}\b")             # any price-looking number, served or worked out


def ints_only(x, where="series_read"):
    """Every number under the receipt's series_read is a count (an int), never a price the script worked out."""
    if isinstance(x, dict):
        for k, v in x.items():
            ints_only(v, "{}.{}".format(where, k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            ints_only(v, "{}[{}]".format(where, i))
    elif isinstance(x, float):
        raise AssertionError("a float in the receipt at {}".format(where))


class Resp:
    def __init__(self, body, status=200, headers=None):
        self._body, self.status_code = body, status
        self.headers = dict(headers or {})

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError("synthetic HTTP {}".format(self.status_code))
            err.response = self
            raise err


def leg(event, suffix, label, tie=False, bid="0.4137", ask="0.4291"):
    m = {"ticker": "{}-{}".format(event, suffix), "event_ticker": event, "yes_sub_title": label,
         "status": "active", "yes_bid_dollars": bid, "yes_ask_dollars": ask, "no_bid_dollars": "0.0613",
         "no_ask_dollars": "0.0711", "last_price_dollars": "0.3377", "yes_bid": 41, "no_ask": 43, "last_price": 33,
         "volume": 98765, "open_interest": 54321, "title": "Synthetic row title that must not print"}
    if tie:
        m["custom_strike"] = {"soccer_team": swr.KalshiAdapter.TIE_STRIKE_UUID}
    return m


EL1 = "KXEFLL1GAME"                                    # the adapter's reserved ticker (asserted below, never assumed)
CZE_CAND = "SYNTHCZECHGAME"
SERIES = [
    {"ticker": EL1, "title": "Synthetic League One game", "category": "Sports", "tags": ["Soccer"]},
    {"ticker": CZE_CAND, "title": "Synthetic Czech top flight game", "category": "Sports", "tags": ["Soccer"]},
    {"ticker": "SYNTHCZECHCHAMP", "title": "Synthetic Czech champion", "category": "Sports", "tags": ["Soccer"]},
    {"ticker": "SYNTHHOOPGAME", "title": "Synthetic basketball game", "category": "Sports", "tags": ["Basketball"]},
]
EV1, EV2, EV3 = "SYNTHL1-26NOV28AAABBB", "SYNTHL1-26NOV28CCCDDD", "SYNTHCZ-26NOV29EEEFFF"
EL1_MARKETS_P1 = [leg(EV1, "AAA", "Synthetic Athletic"), leg(EV1, "BBB", "Synthetic Rovers"),
                  leg(EV1, "TIE", "Tie", tie=True)]
EL1_MARKETS_P2 = [leg(EV2, "CCC", "Synthetic Town"), leg(EV2, "DDD", "Synthetic City", bid=None)]
CZE_MARKETS = [leg(EV3, "EEE", "Synthetic Praha"), leg(EV3, "FFF", "Synthetic Brno"),
               leg(EV3, "TIE", "Tie", tie=True, bid=None)]


def kalshi_router(seen=None, overrides=None):
    overrides = overrides or {}

    def get(url, headers=None, params=None, timeout=None):
        params = dict(params or {})
        if seen is not None:
            seen.append((url, params))
        for frag, r in overrides.items():
            if frag in url:
                r = r(url, params) if callable(r) else r
                if isinstance(r, Exception):
                    raise r
                return r
        if url.endswith("/series"):
            return Resp({"series": SERIES, "cursor": ""})
        st = params.get("series_ticker")
        if url.endswith("/events"):
            evs = {EL1: [EV1, EV2, "SYNTHL1-26DEC01GGGHHH"], CZE_CAND: [EV3]}.get(st, [])
            return Resp({"events": [{"event_ticker": e, "title": "synthetic"} for e in evs], "cursor": None})
        if url.endswith("/markets"):
            if st == EL1 and not params.get("cursor"):
                return Resp({"markets": EL1_MARKETS_P1, "cursor": "synthetic-cursor-2"})
            if st == EL1:
                return Resp({"markets": EL1_MARKETS_P2, "cursor": ""})
            return Resp({"markets": CZE_MARKETS if st == CZE_CAND else [], "cursor": None})
        raise AssertionError("unexpected URL {}".format(url))
    return get


def no_db(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a database was opened")
    monkeypatch.setattr(sqlite3, "connect", refuse)


def test_the_reserved_tickers_are_the_adapters():
    assert swr.KalshiAdapter.SOCCER_SERIES_RESERVED["EL1"] == EL1
    assert swr.KalshiAdapter.SOCCER_SERIES_RESERVED["CZE"] == "KXCZEFLGAME"


def test_kalshi_prints_counts_and_tickers_never_a_price(monkeypatch, capsys, tmp_path):
    no_db(monkeypatch)
    seen = []
    monkeypatch.setattr(requests, "get", kalshi_router(seen))
    out_file = tmp_path / "r" / "k.json"
    out_file.parent.mkdir()
    rc = swr.main(["kalshi", "--out", str(out_file)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "addendum 565 item 3" in out.splitlines()[0] and "mode kalshi" in out.splitlines()[0]
    assert "4 series served" in out
    assert "SERVED {} · RESERVED in the adapter".format(EL1) in out
    assert "NOT SERVED: KXCZEFLGAME" in out
    assert "CANDIDATE {} · matched keyword 'czech'".format(CZE_CAND) in out
    assert "CANDIDATE SYNTHCZECHCHAMP" in out           # listed as a candidate, but not a GAME series: not read
    assert not any(p.get("series_ticker") == "SYNTHCZECHCHAMP" for _, p in seen)
    assert "SYNTHHOOPGAME" not in out.split("GAME SERIES READ")[0].split("SOCCER SERIES SERVED")[1]
    # EL1: 3 events listed, 2 with markets (2 pages followed), one 3-leg event with one Tie, all two-sided
    assert ("{}: events listed 3 · events with an open market 2 · open markets 5 · legs per event "
            "{{'2': 1, '3': 1}}".format(EL1)) in out
    assert "three legs with one Tie leg: 1 · of those, every leg quoted both sides: 1" in out
    assert "one event ({}): 3 legs, of which Tie legs 1 (labels not printed)".format(EV1) in out
    # CZE candidate: a 3-leg event with a Tie, its Tie leg one-sided
    assert "three legs with one Tie leg: 1 · of those, every leg quoted both sides: 0" in out
    assert [p.get("cursor") for u, p in seen if u.endswith("/markets") and p["series_ticker"] == EL1] == \
        [None, "synthetic-cursor-2"]
    assert "requests made this run: {}".format(len(seen)) in out
    body = out_file.read_text()
    for p in PRICES + ("yes_bid", "no_ask", "last_price", "volume", "open_interest", "Synthetic row title"):
        assert p not in out, p
        assert p not in body, p
    # no leg label (a team name) and no served series title is printed or written (565 item 3's set)
    for p in ("Synthetic Athletic", "Synthetic Rovers", "Synthetic Praha", "Synthetic League One game",
              "Synthetic Czech top flight game", "Synthetic basketball game"):
        assert p not in out, p
        assert p not in body, p
    assert not DECIMAL.search(out), DECIMAL.search(out)
    assert not DECIMAL.search(body), DECIMAL.search(body)
    rec = json.loads(body)
    assert rec["mode"] == "kalshi" and rec["requests"] == len(seen) and rec["exit"] == 0
    ints_only(rec["record"]["series_read"])


def test_kalshi_a_non_soccer_keyword_match_is_listed_never_read(monkeypatch, capsys):
    rugby = {"ticker": "SYNTHRUGBYGAME", "title": "Synthetic Premiership Rugby Game", "category": "Sports",
             "tags": ["Rugby"]}
    hoops = {"ticker": "SYNTHHOOPTRGAME", "title": "Synthetic Turkish Basketball Super League Game",
             "category": "Sports", "tags": ["Basketball"]}
    seen = []
    monkeypatch.setattr(requests, "get", kalshi_router(seen, {"/series": Resp({"series": SERIES + [rugby, hoops]})}))
    assert swr.main(["kalshi"]) == 0
    out = capsys.readouterr().out
    assert ("CANDIDATE SYNTHRUGBYGAME · matched keyword 'premiership' (a hypothesis) · GAME · NOT SOCCER by the "
            "rule above: listed, never read") in out
    assert "CANDIDATE SYNTHHOOPTRGAME · matched keyword 'turkish'" in out and "NOT SOCCER" in out
    read = {p.get("series_ticker") for _, p in seen}
    assert "SYNTHRUGBYGAME" not in read and "SYNTHHOOPTRGAME" not in read
    assert CZE_CAND in read                                   # a soccer candidate is still read
    assert "SYNTHRUGBYGAME:" not in out.split("GAME SERIES READ")[1]


def test_kalshi_order_is_el1_and_cze_first_then_the_nine_then_the_three(monkeypatch, capsys):
    monkeypatch.setattr(requests, "get", kalshi_router())
    swr.main(["kalshi"])
    out = capsys.readouterr().out
    marks = ["[first] EL1", "[first] CZE"] + ["[pot] " + c for c in
                                              ("NED", "POR", "BEL", "SCO", "TUR", "AUT", "SUI", "GRE", "EL2")] + \
        ["[ticker-only] BUNDESLIGA2", "[ticker-only] BRASILEIRO", "[ticker-only] MYSL"]
    pos = [out.index(m) for m in marks]
    assert pos == sorted(pos)
    assert "NOT SERVED: KXBUNDESLIGA2GAME" in out and "INFERENCE" in out


def test_kalshi_mode_imports_no_database_in_a_fresh_interpreter(tmp_path):
    code = (
        "import importlib.util, sys, requests\n"
        "s = importlib.util.spec_from_file_location('w', sys.argv[1]); m = importlib.util.module_from_spec(s)\n"
        "s.loader.exec_module(m)\n"
        "class R:\n"
        "    status_code = 200\n"
        "    headers = {}\n"
        "    def raise_for_status(self): pass\n"
        "    def json(self): return {'series': [{'ticker': 'KXEFLL1GAME', 'title': 'synthetic', 'tags': ['Soccer']}]}\n"
        "mk = [{'ticker': 'SYNTHE-' + x, 'event_ticker': 'SYNTHE', 'yes_sub_title': x, 'yes_bid_dollars': '0.41',\n"
        "       'yes_ask_dollars': '0.43'} for x in ('A', 'B')]\n"
        "def get(url, **k):\n"
        "    if url.endswith('/series'): return R()\n"
        "    class E(R):\n"
        "        def json(self): return {'events': [{'event_ticker': 'SYNTHE'}], 'markets': mk}\n"
        "    return E()\n"
        "requests.get = get\n"
        "rc = m.main(['kalshi'])\n"
        "bad = sorted(k for k in sys.modules if k.startswith(('src.db', 'sqlalchemy', 'config', 'dotenv')))\n"
        "print('RC', rc, 'LEGS', 'src.walters.k_receipt' in sys.modules, 'BAD', bad)\n")
    got = subprocess.run([sys.executable, "-I", "-c", code, str(SCRIPT)], capture_output=True, text=True,
                         cwd=str(tmp_path), timeout=120)
    assert got.returncode == 0, got.stderr
    assert "RC 0 LEGS True BAD []" in got.stdout, got.stdout      # leg_stats ran (k_receipt loaded), no database
    assert "KXEFLL1GAME: events listed 1" in got.stdout, got.stdout
    assert list(tmp_path.iterdir()) == []              # nothing written in the cwd (no data/, no __pycache__)
    assert not (ROOT / "data").exists()


def test_kalshi_a_429_is_asked_again_and_counted(monkeypatch, capsys):
    waits = []
    monkeypatch.setattr(swr, "_wait", waits.append)
    state = {"n": 0}

    def series_once_429(url, params):
        state["n"] += 1
        return Resp({}, status=429) if state["n"] == 1 else Resp({"series": SERIES})
    seen = []
    monkeypatch.setattr(requests, "get", kalshi_router(seen, {"/series": series_once_429}))
    rc = swr.main(["kalshi"])
    out = capsys.readouterr().out
    assert rc == 0 and waits == [2]
    assert "requests made this run: {} (each 429 retry counted)".format(len(seen)) in out


def test_kalshi_a_failed_listing_is_failed_and_the_cap_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(requests, "get", kalshi_router(overrides={"/series": requests.ConnectionError("synthetic")}))
    assert swr.main(["kalshi"]) == 1
    assert "FAILED: the series listing did not answer" in capsys.readouterr().out
    monkeypatch.setattr(requests, "get", kalshi_router())
    assert swr.main(["kalshi", "--max-calls", "2"]) == 2
    out = capsys.readouterr().out
    assert "REFUSED: the call cap (2) was reached" in out and "requests made this run: 2" in out


def test_kalshi_a_listing_of_the_wrong_shape_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(requests, "get", kalshi_router(overrides={"/series": Resp({"error": "synthetic"})}))
    assert swr.main(["kalshi"]) == 2
    assert "is not {'series': [...]}" in capsys.readouterr().out


# ---- status -----------------------------------------------------------------------------------------------------

STATUS = {"errors": [], "response": {"account": {"firstname": "Synthfirst", "email": "synthetic@example.invalid"},
                                     "subscription": {"plan": "SynthPro", "end": "2027-01-01", "active": True},
                                     "requests": {"current": 12, "limit_day": 7500}}}


def status_router(seen, resp=None, kwargs=None):
    def get(url, headers=None, params=None, timeout=None, **kw):
        seen.append((url, dict(headers or {})))
        if kwargs is not None:
            kwargs.append(kw)
        return resp if resp is not None else Resp(STATUS, headers={"x-ratelimit-requests-limit": "7500",
                                                                   "Content-Type": "application/json"})
    return get


def test_status_makes_one_call_prints_plan_and_limit_never_key_or_account(monkeypatch, capsys, tmp_path):
    no_db(monkeypatch)
    monkeypatch.setenv("API_FOOTBALL_KEY", KEY)
    monkeypatch.delenv("API_FOOTBALL_HOST", raising=False)
    seen, kws = [], []
    monkeypatch.setattr(requests, "get", status_router(seen, kwargs=kws))
    out_file = tmp_path / "s.json"
    rc = swr.main(["status", "--out", str(out_file)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert len(seen) == 1 and kws == [{"allow_redirects": False}]
    url, headers = seen[0]
    assert url == "https://v3.football.api-sports.io/status" and headers == {"x-apisports-key": KEY}
    assert "mode status" in out.splitlines()[0]
    assert "key used: API_FOOTBALL_KEY (the value is never printed)" in out
    assert "PLAN: 'SynthPro'" in out and "limit_day 7500" in out
    assert "x-ratelimit-requests-limit" in out and "requests made this run: 1" in out
    body = out_file.read_text()
    for s in (KEY, "Synthfirst", "synthetic@example.invalid", "account", "email", "2027-01-01"):
        assert s not in out, s
        assert s not in body, s


def test_status_hosts_are_the_adapters_and_rapid_uses_its_headers(monkeypatch):
    from src.adapters import api_football as af
    assert swr.HOST_DIRECT == af._HOST_DIRECT and swr.HOST_RAPID == af._HOST_RAPID
    url, headers, host = swr.status_target({"API_FOOTBALL_KEY": KEY, "API_FOOTBALL_HOST": af._HOST_RAPID})
    assert url == "https://{}/v3/status".format(af._HOST_RAPID)
    assert headers == {"x-rapidapi-key": KEY, "x-rapidapi-host": af._HOST_RAPID}


def test_status_no_key_is_refused_with_no_call(monkeypatch, capsys):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    seen = []
    monkeypatch.setattr(requests, "get", status_router(seen))
    assert swr.main(["status"]) == 2
    out = capsys.readouterr().out
    assert seen == [] and "requests made this run: 0" in out


def test_status_a_429_is_failed_never_retried_and_an_error_never_echoes_the_key(monkeypatch, capsys):
    monkeypatch.setenv("API_FOOTBALL_KEY", KEY)
    seen = []
    monkeypatch.setattr(requests, "get", status_router(seen, Resp({}, status=429)))
    assert swr.main(["status"]) == 1 and len(seen) == 1
    capsys.readouterr()
    seen.clear()
    bad = Resp({"errors": {"token": "synthetic: key {} unknown".format(KEY)}, "response": []})
    monkeypatch.setattr(requests, "get", status_router(seen, bad))
    assert swr.main(["status"]) == 1 and len(seen) == 1
    assert KEY not in capsys.readouterr().out


def test_status_a_redirect_is_failed_not_followed_and_its_target_never_printed(monkeypatch, capsys):
    monkeypatch.setenv("API_FOOTBALL_KEY", KEY)
    seen, kws = [], []
    moved = Resp({}, status=302, headers={"Location": "https://synthetic-elsewhere.invalid/status"})
    monkeypatch.setattr(requests, "get", status_router(seen, moved, kws))
    assert swr.main(["status"]) == 1
    out = capsys.readouterr().out
    assert len(seen) == 1 and kws == [{"allow_redirects": False}]
    assert "HTTP 302 (a redirect, not followed" in out and "requests made this run: 1" in out
    assert "synthetic-elsewhere" not in out and KEY not in out


def test_status_a_limit_not_served_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("API_FOOTBALL_KEY", KEY)
    body = {"errors": [], "response": {"subscription": {"plan": "SynthPro"}, "requests": {}}}
    monkeypatch.setattr(requests, "get", status_router([], Resp(body)))
    assert swr.main(["status"]) == 2
    assert "not served: response.requests.limit_day" in capsys.readouterr().out


# ---- copy -------------------------------------------------------------------------------------------------------

def build_copy(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript(
        "CREATE TABLE competitions (id INTEGER PRIMARY KEY, sport VARCHAR(10), code VARCHAR(16), name VARCHAR(128),"
        " area VARCHAR(64), type VARCHAR(32), external_ids JSON);"
        "CREATE TABLE matches (id INTEGER PRIMARY KEY, sport VARCHAR(10), competition_id INTEGER, season VARCHAR(16),"
        " matchday INTEGER, stage VARCHAR(64), utc_date DATETIME, status VARCHAR(14), status_raw VARCHAR(16),"
        " home_team_id INTEGER, away_team_id INTEGER);")
    con.executemany("INSERT INTO competitions VALUES (?,?,?,?,?,?,?)",
                    [(1, "SOCCER", "EL1", "Synthetic One", "Synthland", "LEAGUE", "{}"),
                     (2, "SOCCER", "CZE", "Synthetic Czech", "Synthland", "LEAGUE", "{}"),
                     (3, "SOCCER", "PL", "Synthetic PL", "Synthland", "LEAGUE", "{}")])
    rows = []

    def add(comp, season, stage, status, n):
        for _ in range(n):
            rows.append((len(rows) + 1, "SOCCER", comp, season, None, stage, "2027-03-01 15:00:00", status, None, 1, 2))
    add(1, "2026/27", "Regular Season - 15", "FINISHED", 4)
    add(1, "2026/27", "Regular Season - 16", "SCHEDULED", 2)
    add(1, "2025/26", "Regular Season - 1", "FINISHED", 3)
    add(2, "2026/27", "Regular Season - 19", "FINISHED", 5)
    add(2, "2026/27", "Regular Season - 20", "SCHEDULED", 3)
    add(2, "2026/27", "Regular Season - 21", "POSTPONED", 1)
    add(2, "2026/27", "Championship Group - 1", "SCHEDULED", 2)
    add(2, "2026/27", "Synthetic Mystery - 1", "SCHEDULED", 1)
    add(2, "2026/27", None, "SCHEDULED", 1)
    add(2, "2026/27", "Regular Season - 22", "LIVE", 1)
    add(2, "2026/27", "Regular Season - 22", "CANCELLED", 1)
    add(2, "2026/27", "Regular Season - 22", "STALE_ORPHAN", 1)
    add(2, "2026/27", "Regular Season - 22", "SETTLED_SCALAR", 1)
    add(3, "2026/27", "Regular Season - 20", "SCHEDULED", 9)
    con.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


LIST_LINES = "# synthetic list\nPL|2026/27\nCZE|2026/27\nSYNTHX|{today}\n"


def test_copy_reads_mode_ro_immutable_counts_and_leaves_the_copy_unchanged(monkeypatch, capsys, tmp_path):
    db = build_copy(tmp_path / "copies" / "sports.backup.db")
    before = db.read_bytes()
    listing = sorted(p.name for p in db.parent.iterdir())
    lst = tmp_path / "fullseason.list"
    lst.write_text(LIST_LINES)
    real = sqlite3.connect
    uris = []

    def spy(*a, **k):
        uris.append((a, k))
        return real(*a, **k)
    monkeypatch.setattr(sqlite3, "connect", spy)
    out_file = tmp_path / "c.json"
    rc = swr.main(["copy", "--db", str(db), "--fullseason-list", str(lst), "--out", str(out_file)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert uris and all(a[0] == db.resolve().as_uri() + "?mode=ro&immutable=1" and k.get("uri") is True
                        for a, k in uris)
    assert "mode copy" in out.splitlines()[0] and "requests made this run: 0" in out
    assert "EL1: competition rows stored 1 (sport ['SOCCER']) · stored seasons {'2025/26': 3, '2026/27': 6}" in out
    assert "2026/27 matches by status: {'FINISHED': 4, 'SCHEDULED': 2} (total 6)" in out
    assert "EL1: named NO" in out and "CZE: named YES · with season 2026/27 as written: YES" in out
    assert "entries: 3" in out
    for line in ("PL|2026/27", "CZE|2026/27", "SYNTHX", "{today}", "synthetic list"):
        assert line not in out, line
        assert line not in out_file.read_text(), line
    assert "'Championship Group - 1' · 2 remaining · PLAYOFF · by addendum 456 (ruled table)" in out
    assert "'Regular Season - 20' · 3 remaining · REGULAR · by soccer_expansion.placement (F3)" in out
    assert "'Regular Season - 21' · 1 remaining · REGULAR" in out
    assert "'Regular Season - 22' · 1 remaining · REGULAR" in out
    assert "'Synthetic Mystery - 1' · 1 remaining · CANNOT PLACE · unplaced" in out
    assert "None · 1 remaining · CANNOT PLACE" in out
    assert "Regular Season - 19" not in out                     # FINISHED: not remaining
    assert ("REGULAR REMAINING (SCHEDULED, POSTPONED, LIVE): 5 · by status {'LIVE': 1, 'POSTPONED': 1, "
            "'SCHEDULED': 3}") in out
    assert ("REGULAR NOT REMAINING (other non-FINISHED statuses, not counted above): 3 · by status "
            "{'CANCELLED': 1, 'SETTLED_SCALAR': 1, 'STALE_ORPHAN': 1}") in out
    assert db.read_bytes() == before
    assert sorted(p.name for p in db.parent.iterdir()) == listing
    assert not (ROOT / "data").exists()


def test_copy_list_from_the_environment_and_no_list_is_refused_not_guessed(monkeypatch, capsys, tmp_path):
    db = build_copy(tmp_path / "copies" / "c.db")
    lst = tmp_path / "env.list"
    lst.write_text("EL1|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    assert swr.main(["copy", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "SP_FULLSEASON_LIST as this process was started" in out and "EL1: named YES" in out \
        and "CZE: named NO" in out
    monkeypatch.delenv("SP_FULLSEASON_LIST")
    assert swr.main(["copy", "--db", str(db)]) == 2
    out = capsys.readouterr().out
    assert "NOT READ" in out and "REGULAR REMAINING (SCHEDULED, POSTPONED, LIVE): 5" in out


def test_copy_a_list_put_in_the_environment_after_start_is_never_read(monkeypatch, capsys, tmp_path):
    """config's load_dotenv runs inside the fence (check_copy); a SP_FULLSEASON_LIST it adds to os.environ then
    (a value only in the checkout's .env) is never the list: the path comes from main()'s snapshot."""
    db = build_copy(tmp_path / "copies" / "c.db")
    lst = tmp_path / "dotenv.list"
    lst.write_text("CZE|2026/27\n")
    monkeypatch.delenv("SP_FULLSEASON_LIST", raising=False)
    real = swr.check_copy

    def dotenv_like(db_):
        monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))     # what load_dotenv would do during the fence
        return real(db_)
    monkeypatch.setattr(swr, "check_copy", dotenv_like)
    assert swr.main(["copy", "--db", str(db)]) == 2
    out = capsys.readouterr().out
    assert "NOT READ" in out and "CZE: named" not in out


@pytest.mark.parametrize("how", ["option", "env"])
def test_copy_a_list_under_data_is_refused_before_any_read(monkeypatch, capsys, tmp_path, how):
    db = build_copy(tmp_path / "copies" / "c.db")
    lst = tmp_path / "data" / "fullseason.list"
    lst.parent.mkdir()
    lst.write_text("CZE|2026/27\n")
    opened = []
    real_read = Path.read_text

    def spy(self, *a, **k):
        if Path(self).resolve() == lst.resolve():
            opened.append(self)
        return real_read(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", spy)
    if how == "env":
        monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
        argv = ["copy", "--db", str(db)]
    else:
        argv = ["copy", "--db", str(db), "--fullseason-list", str(lst)]
    assert swr.main(argv) == 2
    out = capsys.readouterr().out
    assert "REFUSED: the whole-season list" in out and "law 5" in out and "nothing read" in out
    assert opened == [] and "competition rows stored" not in out


def test_copy_a_list_that_is_not_utf8_is_refused_as_such(capsys, tmp_path):
    db = build_copy(tmp_path / "copies" / "c.db")
    lst = tmp_path / "binary.list"
    lst.write_bytes(b"CZE|2026/27\n\xff\xfeSYNTHETIC\x80\n")
    assert swr.main(["copy", "--db", str(db), "--fullseason-list", str(lst)]) == 2
    out = capsys.readouterr().out
    assert "is not UTF-8 text (its bytes are not printed)" in out and "SYNTHETIC" not in out


def test_out_naming_the_copy_or_the_list_is_refused(capsys, tmp_path):
    db = build_copy(tmp_path / "copies" / "c.db")
    before = db.read_bytes()
    lst = tmp_path / "l.list"
    lst.write_text("CZE|2026/27\n")
    assert swr.main(["copy", "--db", str(db), "--fullseason-list", str(lst), "--out", str(db)]) == 2
    assert "is the same file as --db" in capsys.readouterr().out
    assert swr.main(["copy", "--db", str(db), "--fullseason-list", str(lst), "--out", str(lst)]) == 2
    assert "is the same file as --fullseason-list" in capsys.readouterr().out
    assert db.read_bytes() == before and lst.read_text() == "CZE|2026/27\n"


def test_a_receipt_that_cannot_be_written_at_the_end_is_refused(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(requests, "get", kalshi_router())
    out_file = tmp_path / "k.json"
    real_write = Path.write_text

    def fail(self, *a, **k):
        if Path(self) == out_file:
            raise OSError("synthetic")
        return real_write(self, *a, **k)
    monkeypatch.setattr(Path, "write_text", fail)
    assert swr.main(["kalshi", "--out", str(out_file)]) == 2
    assert "REFUSED: --out" in capsys.readouterr().out


def test_copy_a_list_that_does_not_parse_is_refused_without_its_text(monkeypatch, capsys, tmp_path):
    db = build_copy(tmp_path / "copies" / "c.db")
    lst = tmp_path / "bad.list"
    lst.write_text("PL|2026/27\nSYNTHETIC-SECRET-LINE\n")
    assert swr.main(["copy", "--db", str(db), "--fullseason-list", str(lst)]) == 2
    out = capsys.readouterr().out
    assert "does not parse (line 2" in out and "SYNTHETIC-SECRET-LINE" not in out


@pytest.mark.parametrize("folder", ["data", "DATA", "Data"])
def test_copy_under_a_data_directory_is_refused(capsys, tmp_path, folder):
    db = build_copy(tmp_path / folder / "c.db")
    assert swr.main(["copy", "--db", str(db)]) == 2
    out = capsys.readouterr().out
    assert "REFUSED" in out and "data" in out


def test_copy_a_missing_file_is_refused_and_never_created(capsys, tmp_path):
    db = tmp_path / "copies" / "absent.db"
    assert swr.main(["copy", "--db", str(db)]) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert not db.exists()


def test_copy_a_sidecar_is_refused(capsys, tmp_path):
    db = build_copy(tmp_path / "copies" / "c.db")
    (db.parent / (db.name + "-wal")).write_bytes(b"")
    assert swr.main(["copy", "--db", str(db)]) == 2
    assert "sidecar" in capsys.readouterr().out


def test_out_under_data_is_refused_before_any_call(monkeypatch, capsys, tmp_path):
    seen = []
    monkeypatch.setattr(requests, "get", kalshi_router(seen))
    (tmp_path / "data").mkdir()
    assert swr.main(["kalshi", "--out", str(tmp_path / "data" / "r.json")]) == 2
    assert seen == [] and "REFUSED: --out" in capsys.readouterr().out
    assert not (tmp_path / "data" / "r.json").exists()


def test_copy_mode_never_imports_the_engine_module(tmp_path):
    db = build_copy(tmp_path / "copies" / "c.db")
    code = (
        "import importlib.util, sys\n"
        "s = importlib.util.spec_from_file_location('w', sys.argv[1]); m = importlib.util.module_from_spec(s)\n"
        "s.loader.exec_module(m)\n"
        "rc = m.main(['copy', '--db', sys.argv[2], '--fullseason-list', sys.argv[3]])\n"
        "print('RC', rc, 'ENGINE', 'src.db.database' in sys.modules)\n")
    lst = tmp_path / "l.list"
    lst.write_text("CZE|2026/27\n")
    work = tmp_path / "cwd"
    work.mkdir()
    env = dict(__import__("os").environ)
    got = subprocess.run([sys.executable, "-c", code, str(SCRIPT), str(db), str(lst)], capture_output=True,
                         text=True, cwd=str(work), timeout=120, env=env)
    assert got.returncode == 0, got.stderr
    assert "RC 0 ENGINE False" in got.stdout, got.stdout
    assert list(work.iterdir()) == []
    assert not (ROOT / "data").exists()
