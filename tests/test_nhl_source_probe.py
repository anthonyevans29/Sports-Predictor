"""The NHL source probe (ARCHITECT 2026-11-06 19:40 ET, addendum 279 items 3(a) and 5; lane nhl, #105): read-only, on
SYNTHETIC responses only. Every game, team, goalie, stamp, field value and URL answer below is invented for the test and
labelled synthetic; none is the vendor's real value, and no field name here is confirmed against a live answer (the
probe exists to read them). HTTP is monkeypatched: no provider is reached.

Pinned: the key read by NAME (SPORTSDATAIO_NHL_KEY) and never printed or written, sent in the header only and never in a
URL; a key not set or not accepted makes no metered call; the rate-limit headers printed as served on every call line;
field names printed as served, a price-class field by NAME only (279 item 3(c)) and any figure replaced (a price with
no currency sign included, the receipt's text too); the
stamp-before-start comparison read from the served values only (Z, offsets, and a value with no zone read only in the
operator's --served-zone); a missing, null, numeric, date-only or unparseable stamp refusing that game; no --stamp-field
refused before any call, no --stamp-quote refusing section 3; the terms section refused without --terms-url and its
retention clauses quoted with markup stripped (an inline tag kept inside its sentence), a page with no retention passage
refused; the key's value in any URL refused before any call; --out home-expanded, and under data/ refused before any
call; the exit codes (0 / 1 / 2,
a failed call first); no Kalshi call and no import that opens the DB."""
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nhl_source_probe.py"
spec = importlib.util.spec_from_file_location("nhl_source_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

DAY = "2026-11-07"                                    # synthetic game day
KEY = "SYNTH-NHL-TRIAL-KEY-5e1b9c"                    # synthetic secret: must never appear in any output
BASE = "https://synthetic.invalid/v3/nhl"
TERMS_URL = "https://synthetic.invalid/terms"
QUOTE = "Synthetic documentation: Updated is the time the projection was last published."
RATE = {"X-RateLimit-Remaining": "9", "x-ratelimit-limit": "10", "Retry-After": "1", "Content-Type": "application/json"}
SECRET_COST, SECRET_SALARY, SECRET_LINE = 1234.5, 7777, -987      # synthetic price-class values: never printed

STATUS = {"Season": 2027, "SeasonType": 1, "ApiSeason": "SYN2027", "MonthlyCost": SECRET_COST,
          "Subscription": {"Tier": "SynthTier", "Renews": "2027-01-01"}}


def game(gid, start, home, away, **extra):
    return {"GameID": gid, "DateTime": start, "HomeTeam": home, "AwayTeam": away, "Status": "Scheduled",
            "Day": f"{DAY}T00:00:00", "HomeTeamMoneyLine": SECRET_LINE, **extra}


GAMES = [game(9101, f"{DAY}T19:00:00", "SHA", "SAA"),                     # no zone stated: --served-zone reads it
         game(9102, f"{DAY}T22:00:00-05:00", "SHB", "SAB")]               # an offset as served


def goalie(pid, name, **extra):
    return {"PlayerID": pid, "Name": name, "DraftKingsSalary": SECRET_SALARY, **extra}


def starter(gid, updated, **over):
    it = {"GameID": gid, "HomeGoaltender": goalie(gid * 10, f"Synthetic Goalie H{gid}"),
          "AwayGoaltender": goalie(gid * 10 + 1, f"Synthetic Goalie A{gid}"), "Updated": updated}
    it.update(over)
    return it


STARTERS = [starter(9101, f"{DAY}T15:30:00"),                  # 15:30 vs 19:00, both in the served zone: BEFORE
            starter(9102, "2026-11-08T03:30:00Z")]             # 03:30Z vs 22:00-05:00 (03:00Z): NOT BEFORE
TERMS_HTML = ("<html><head><style>p{}</style><script>var leak=1;</script></head><body><h1>Synthetic Terms</h1>"
              "<p>Synthetic clause one applies to visitors.</p>"
              "<p>Synthetic clause: on termination you must delete all stored data within thirty days.</p>"
              f"<p>Synthetic clause: the plan costs {chr(36)}9999 per synthetic month and you may cache nothing.</p>"
              "</body></html>")


class Resp:
    def __init__(self, body, status=200, headers=None, text=None):
        self._body, self.status_code, self.headers = body, status, dict(headers if headers is not None else RATE)
        self.text = text if text is not None else json.dumps(body, default=str)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def router(overrides=None, seen=None):
    """A fake requests.get dispatching on the URL; `overrides` maps a URL fragment to a Resp, a callable or an
    exception."""
    overrides = overrides or {}

    def get(url, headers=None, params=None, timeout=None):
        if seen is not None:
            seen.append((url, dict(headers or {}), dict(params or {})))
        for frag, r in overrides.items():
            if frag in url:
                if isinstance(r, Exception):
                    raise r
                return r(url, headers, params) if callable(r) else r
        if url == TERMS_URL:
            return Resp(ValueError("synthetic: not JSON"), headers={"Content-Type": "text/html"}, text=TERMS_HTML)
        if (headers or {}).get(probe.KEY_HEADER) != KEY:
            return Resp({"message": "synthetic: no key"}, status=401)
        if url.endswith("/scores/json/CurrentSeason"):
            return Resp(STATUS)
        if url.endswith("/scores/json/GamesByDate/2026-NOV-07"):
            return Resp(GAMES)
        if url.endswith("/projections/json/StartingGoaltendersByDate/2026-NOV-07"):
            return Resp(STARTERS)
        raise AssertionError(f"unexpected URL {url}")
    return get


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(probe, "_load_env", lambda: None)
    monkeypatch.setenv("SPORTSDATAIO_NHL_KEY", KEY)
    return monkeypatch


FULL = ["--date", DAY, "--base-url", BASE, "--stamp-field", "Updated", "--stamp-quote", QUOTE,
        "--served-zone", "America/New_York", "--terms-url", TERMS_URL]


def run(args, capsys, base=FULL):
    rc = probe.main([*base, *args])
    return rc, capsys.readouterr().out


def test_every_section_reads_and_the_stamp_is_compared_from_served_values(env, capsys, tmp_path):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    out_file = tmp_path / "receipts" / "nhl.json"
    rc, out = run(["--out", str(out_file)], capsys)
    assert rc == 0, out
    assert "key SPORTSDATAIO_NHL_KEY: set (the value is never printed)" in out
    assert "KALSHI: none (KXNHLGAME untouched, 279 item 5)" in out
    assert "the key named SPORTSDATAIO_NHL_KEY answered (the value is never printed)" in out
    assert "Season = 2027" in out
    # (2): the date a UTC day, the start as served with its zone as written
    assert f"--date {DAY} (a UTC calendar day, as given" in out
    assert f"game 9101 · 'SAA' @ 'SHA' · Status 'Scheduled' · DateTime = '{DAY}T19:00:00' (no zone stated)" in out
    assert f"game 9102 · 'SAB' @ 'SHB' · Status 'Scheduled' · DateTime = '{DAY}T22:00:00-05:00' (offset -05:00)" in out
    # (3): every field name as served, the goalies, the stamp vs the start
    assert "AwayGoaltender.Name" in out and "HomeGoaltender.PlayerID" in out and "Updated" in out
    assert f'THE DOCUMENTATION ON THE STAMP, as quoted by the operator: "{QUOTE}"' in out
    assert "projected home goaltender (HomeGoaltender): {PlayerID=91010, Name='Synthetic Goalie H9101'" in out
    assert (f"STAMP Updated = '{DAY}T15:30:00' (no zone stated; read in --served-zone America/New_York) vs start "
            f"'{DAY}T19:00:00' (no zone stated; read in --served-zone America/New_York): BEFORE the start "
            "(210.0 minutes, from the served values)") in out
    assert ("STAMP Updated = '2026-11-08T03:30:00Z' (Z, as served) vs start '2026-11-07T22:00:00-05:00' "
            "(offset -05:00, as served): NOT BEFORE the start (-30.0 minutes, from the served values)") in out
    assert "VERDICT PREGAME (every stamp before the start, read from the response)" in out
    assert "VERDICT NOT PREGAME (a stamp at or after the start, read from the response)" in out
    assert "GAMES: 2 · PREGAME 1 · NOT PREGAME 1 · REFUSED 0" in out
    # (4)
    assert '"Synthetic clause: on termination you must delete all stored data within thirty days."' in out
    assert "EXIT 0 (every read answered)" in out
    rec = json.loads(out_file.read_text())
    assert rec["exit"] == 0 and set(rec["sections"]) == {"status", "games", "starters", "terms"}
    assert rec["key_name"] == "SPORTSDATAIO_NHL_KEY" and rec["key_set"] is True
    v = {str(g["game"]): g["verdict"] for g in rec["sections"]["starters"]["games"]}
    assert v == {"9101": "PREGAME", "9102": "NOT PREGAME"}
    urls = [u for u, h, p in seen]
    assert urls == [f"{BASE}/scores/json/CurrentSeason", f"{BASE}/scores/json/GamesByDate/2026-NOV-07",
                    f"{BASE}/projections/json/StartingGoaltendersByDate/2026-NOV-07", TERMS_URL]
    assert not any("kalshi" in u.lower() for u in urls)


def test_the_key_is_never_printed_never_in_a_url_and_never_sent_to_the_terms_page(env, capsys, tmp_path):
    seen = []
    env.setattr(requests, "get", router({"GamesByDate": requests.ConnectionError(f"synthetic: refused key={KEY}")},
                                        seen=seen))
    out_file = tmp_path / "r.json"
    rc, out = run(["--out", str(out_file)], capsys)
    assert rc == 1, out
    text = out + out_file.read_text()
    assert KEY not in text and KEY[:10] not in text and "<redacted>" in text
    assert all(KEY not in u and KEY not in json.dumps(p) for u, h, p in seen)
    keyed = [h for u, h, p in seen if u != TERMS_URL]
    assert keyed and all(h == {probe.KEY_HEADER: KEY} for h in keyed)
    assert [h for u, h, p in seen if u == TERMS_URL] == [{}]


def test_a_key_not_set_makes_no_metered_call(env, capsys):
    env.delenv("SPORTSDATAIO_NHL_KEY")
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run([], capsys)
    assert rc == 2, out
    assert "key SPORTSDATAIO_NHL_KEY: not set" in out
    assert out.count("SPORTSDATAIO_NHL_KEY is not set: no call made") == 3
    assert [u for u, h, p in seen] == [TERMS_URL]                                    # the terms need no key


@pytest.mark.parametrize("status, rc, word", [(401, 2, "REFUSED: the key named SPORTSDATAIO_NHL_KEY was not "
                                                       "accepted (HTTP 401)"),
                                              (403, 2, "REFUSED: the key named SPORTSDATAIO_NHL_KEY was not "
                                                       "accepted (HTTP 403)"),
                                              (500, 1, "FAILED: HTTP 500")])
def test_a_status_read_that_does_not_answer_stops_the_metered_calls(env, capsys, status, rc, word):
    seen = []
    env.setattr(requests, "get", router({"CurrentSeason": Resp({"message": "synthetic"}, status=status)}, seen=seen))
    got, out = run([], capsys)
    assert got == rc, out
    assert word in out
    assert out.count("the status read did not answer: no call made") == 2
    assert [u for u, h, p in seen] == [f"{BASE}/scores/json/CurrentSeason", TERMS_URL]


def test_skip_status_runs_the_metered_sections_without_it(env, capsys):
    seen = []
    env.setattr(requests, "get", router({"CurrentSeason": Resp({}, status=404)}, seen=seen))
    rc, out = run(["--skip", "status"], capsys)
    assert rc == 0, out
    assert "(status) skipped (--skip)" in out and not any("CurrentSeason" in u for u, h, p in seen)


def test_every_call_line_prints_the_rate_limit_headers_as_served(env, capsys):
    env.setattr(requests, "get", router())
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 0, out
    lines = [x for x in out.splitlines() if x.strip().startswith("HTTP 200")]
    assert len(lines) == 3
    assert all("rate-limit {'X-RateLimit-Remaining': '9', 'x-ratelimit-limit': '10', 'Retry-After': '1'}" in x
               for x in lines)
    assert probe.rate_headers({"Content-Type": "x"}) == {} and probe.rate_headers(None) == {}


def test_a_price_class_field_prints_by_name_only_and_no_figure_prints(env, capsys, tmp_path):
    """279 item 3(c): "the figure never written into the repo, an Issue or a PR". The status cost, a goalie's salary
    and a game's betting line print by NAME; their values never print and never reach the receipt; a currency figure in
    the terms page is replaced."""
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"
    rc, out = run(["--out", str(out_file)], capsys)
    assert rc == 0, out
    text = out + out_file.read_text()
    assert "MonthlyCost (price-class: name only)" in out and "Subscription.Tier (price-class: name only)" in out
    assert "HomeGoaltender.DraftKingsSalary (price-class: name only)" in out
    assert "HomeTeamMoneyLine (price-class: name only)" in out
    for secret in (str(SECRET_COST), str(SECRET_SALARY), str(SECRET_LINE), "SynthTier", "9999", chr(36)):
        assert secret not in text, secret
    assert "<figure not printed>" in out and "<value not printed: price-class field>" in out


def test_the_figure_rule_replaces_currency_figures_and_nothing_else():
    say = probe.Out()
    d = chr(36)
    assert say.redact(f"costs {d}12.50 or {d} 3 or 40 USD or EUR 7 or 9 dollars") == \
        "costs <figure not printed> or <figure not printed> or <figure not printed> or <figure not printed> or " \
        "<figure not printed>"
    assert say.redact("game 9101 at 2026-11-07T19:00:00-05:00, 30 minutes, 0.5u") == \
        "game 9101 at 2026-11-07T19:00:00-05:00, 30 minutes, 0.5u"


# ---- the stamp-before-start comparison, from served values only -----------------------------------------------

NY = ZoneInfo("America/New_York")


@pytest.mark.parametrize("stamp, start, zone, verdict, minutes", [
    ("2026-11-07T23:50:00Z", "2026-11-07T19:00:00-05:00", None, "BEFORE", 10.0),       # text order would say after
    ("2026-11-07T19:10:00-05:00", "2026-11-08T00:05:00Z", None, "NOT BEFORE", -5.0),   # text order would say before
    ("2026-11-08T00:00:00+00:00", "2026-11-07T19:00:00-05:00", None, "NOT BEFORE", 0.0),   # the same instant
    ("2026-11-07T18:00:00", "2026-11-07T19:00:00", NY, "BEFORE", 60.0),
    ("2026-11-07T18:00:00", "2026-11-07T23:30:00Z", NY, "BEFORE", 30.0),               # 18:00 EST is 23:00Z
    ("2026-11-07 18:00:00.123+01:00", "2026-11-07T19:00:00+01:00", None, "BEFORE", 60.0)])
def test_the_stamp_is_compared_with_the_start_as_instants(stamp, start, zone, verdict, minutes):
    c = probe.compare(stamp, start, zone)
    assert (c["verdict"], c["minutes_before_start"]) == (verdict, pytest.approx(minutes, abs=0.01))


@pytest.mark.parametrize("stamp, why", [
    (None, "null"), ("", "empty"), (1762542600, "a number (1762542600), not a time as written"),
    ("2026-11-07", "not an ISO 8601 date and time as written"), ("Nov 7 2026 3:30 PM", "not an ISO 8601"),
    ("2026-13-45T99:00:00Z", "not an ISO 8601"), ("2026-11-07T15:30:00", "states no zone; pass --served-zone")])
def test_a_stamp_that_cannot_be_read_refuses_the_comparison(stamp, why):
    c = probe.compare(stamp, "2026-11-07T19:00:00-05:00", None)
    assert c["verdict"] == "REFUSED" and why in c["why"], c


def test_a_start_with_no_zone_and_no_served_zone_refuses_the_comparison():
    c = probe.compare("2026-11-07T15:00:00Z", "2026-11-07T19:00:00", None)
    assert c["verdict"] == "REFUSED" and c["why"].startswith("the start is not read:") and "--served-zone" in c["why"]


def test_values_with_no_zone_and_no_served_zone_refuse_their_games(env, capsys):
    env.setattr(requests, "get", router())
    base = [x for x in FULL if x not in ("--served-zone", "America/New_York")]
    rc, out = run(["--skip", "terms"], capsys, base=base)
    assert rc == 2, out
    assert "VERDICT REFUSED: stamp Updated: the stamp is not read:" in out and "states no zone" in out
    assert "GAMES: 2 · PREGAME 0 · NOT PREGAME 1 · REFUSED 1" in out       # 9102: Z vs an offset, read as served


@pytest.mark.parametrize("how, reason", [("absent", "stamp Updated not served"),
                                         ("null", "stamp Updated null or empty"),
                                         ("garbage", "stamp Updated: the stamp is not read: not an ISO 8601")])
def test_a_missing_or_unparseable_stamp_refuses_that_game_only(env, capsys, tmp_path, how, reason):
    first = starter(9101, "synthetic-garbage" if how == "garbage" else None)
    if how == "absent":
        del first["Updated"]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp([first, STARTERS[1]])}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--out", str(out_file)], capsys)
    assert rc == 2, out
    assert f"VERDICT REFUSED: {reason}" in out
    rows = {str(g["game"]): g for g in json.loads(out_file.read_text())["sections"]["starters"]["games"]}
    assert rows["9101"]["verdict"] == "REFUSED" and rows["9102"]["verdict"] == "NOT PREGAME"


def test_a_per_goalie_stamp_is_read_by_dotted_path_for_each_field_given(env, capsys):
    items = [starter(9101, None, HomeGoaltender=goalie(1, "Synthetic H", Updated=f"{DAY}T14:00:00"),
                     AwayGoaltender=goalie(2, "Synthetic A", Updated=f"{DAY}T20:00:00"))]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items),
                                         "GamesByDate": Resp(GAMES[:1])}))
    base = [x for x in FULL if x != "Updated" and x != "--stamp-field"]
    rc, out = run(["--skip", "terms", "--stamp-field", "HomeGoaltender.Updated", "--stamp-field",
                   "AwayGoaltender.Updated"], capsys, base=base)
    assert rc == 0, out
    assert "STAMP HomeGoaltender.Updated" in out and ": BEFORE the start (300.0 minutes" in out
    assert "STAMP AwayGoaltender.Updated" in out and ": NOT BEFORE the start (-60.0 minutes" in out
    assert "VERDICT NOT PREGAME" in out


def test_no_goaltender_served_refuses_that_game(env, capsys):
    items = [starter(9101, f"{DAY}T15:30:00", HomeGoaltender=None), STARTERS[1]]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2 and "VERDICT REFUSED: no projected goaltender served for the home side under HomeGoaltender" in out


def test_a_game_with_no_starters_item_and_a_starter_with_no_game_are_refused(env, capsys):
    items = [STARTERS[0], starter(9199, f"{DAY}T15:30:00")]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2, out
    assert "game 9199 · start DateTime = None" in out and "VERDICT REFUSED: no start time read for this game" in out
    assert "game '9102' (section 2): REFUSED: no starters item served for it" in out


def test_a_game_missing_a_required_field_is_refused_and_its_comparison_too(env, capsys):
    bad = game(9101, None, "SHA", "SAA")
    env.setattr(requests, "get", router({"GamesByDate": Resp([bad, GAMES[1]])}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2, out
    assert "REFUSED: game 9101: required field(s) not served: DateTime (required: GameID, DateTime, HomeTeam, " \
           "AwayTeam)" in out
    assert "VERDICT REFUSED: no start time read for this game" in out


def test_skipping_the_games_refuses_every_comparison(env, capsys):
    env.setattr(requests, "get", router())
    rc, out = run(["--skip", "games", "--skip", "terms"], capsys)
    assert rc == 2, out
    assert "no start times read (section 2 skipped, refused or failed)" in out
    assert "GAMES: 2 · PREGAME 0 · NOT PREGAME 0 · REFUSED 2" in out


def test_no_stamp_field_is_refused_before_any_call(env, capsys):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    base = [x for x in FULL if x not in ("--stamp-field", "Updated")]
    rc, out = run([], capsys, base=base)
    assert rc == 2 and "REFUSED: no --stamp-field" in out and seen == []
    assert probe.STAMP_FIELD is None
    rc, out = run(["--skip", "starters"], capsys, base=base)                         # not needed without section 3
    assert rc == 0, out


def test_no_stamp_quote_refuses_section_3_and_its_reads_still_print(env, capsys):
    env.setattr(requests, "get", router())
    base = [x for x in FULL if x not in ("--stamp-quote", QUOTE)]
    rc, out = run(["--skip", "terms"], capsys, base=base)
    assert rc == 2, out
    assert "REFUSED: no --stamp-quote" in out and "GAMES: 2 · PREGAME 1 · NOT PREGAME 1" in out


def test_a_stamp_field_not_among_the_served_names_is_said_and_refuses(env, capsys):
    env.setattr(requests, "get", router())
    base = [x if x != "Updated" else "PublishedAt" for x in FULL]
    rc, out = run(["--skip", "terms"], capsys, base=base)
    assert rc == 2, out
    assert "the stamp field 'PublishedAt' is not among the served field names above" in out
    assert "VERDICT REFUSED: stamp PublishedAt not served" in out


@pytest.mark.parametrize("frag, body", [("GamesByDate", {"synthetic": 1}), ("StartingGoaltendersByDate", {"x": 1})])
def test_an_answer_that_is_not_a_list_is_a_failed_call(env, capsys, frag, body):
    env.setattr(requests, "get", router({frag: Resp(body)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 1, out
    assert "FAILED: the answer is dict, not a list" in out


# ---- the terms ------------------------------------------------------------------------------------------------

def test_no_terms_url_means_the_terms_are_not_read_and_the_section_refused(env, capsys):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    base = [x for x in FULL if x not in ("--terms-url", TERMS_URL)]
    rc, out = run([], capsys, base=base)
    assert rc == 2, out
    assert "TERMS NOT READ (no --terms-url given; no URL is typed here): REFUSED" in out
    assert TERMS_URL not in [u for u, h, p in seen] and probe.TERMS_URL is None


def test_the_terms_quote_the_retention_clauses_with_markup_stripped(env, capsys, tmp_path):
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "status", "--skip", "games", "--skip", "starters", "--out", str(out_file)], capsys)
    assert rc == 0, out
    assert "var leak" not in out and "p{}" not in out and "<p>" not in out
    assert "Synthetic clause one applies to visitors." not in out                    # no retention word in it
    t = json.loads(out_file.read_text())["sections"]["terms"]
    assert t["read"] is True and any("delete all stored data" in q for q in t["quoted"])
    assert probe.terms_excerpt("<p>Synthetic: a downstream known word.</p><p>Synthetic: you may store it.</p>") == \
        ["Synthetic: you may store it."]                                              # a word's start, not inside one


@pytest.mark.parametrize("resp, rc, line", [
    (Resp(None, status=500, text=""), 1, "TERMS NOT READ: the retention clause is not quoted"),
    (Resp(None, text="<html><script>x()</script></html>"), 2, "TERMS NOT QUOTED (the page yields no text to quote)")])
def test_a_terms_read_that_fails_or_has_nothing_to_quote(env, capsys, resp, rc, line):
    env.setattr(requests, "get", router({TERMS_URL: resp}))
    got, out = run(["--skip", "status", "--skip", "games", "--skip", "starters"], capsys)
    assert got == rc and line in out


# ---- arguments, --out, exit codes, imports -----------------------------------------------------------------

@pytest.mark.parametrize("rel", ["data/r.json", "Data/r.json", "DATA/r.json", "x/dAtA/y/r.json"])
def test_out_under_data_is_refused_in_any_case(rel):
    assert probe.refuse_out(Path(rel)).startswith("REFUSED: --out")


def test_out_under_data_is_refused_before_any_call_and_nothing_is_written(env, capsys, tmp_path):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    target = tmp_path / "data" / "r.json"
    rc, out = run(["--out", str(target)], capsys)
    assert rc == 2 and "REFUSED: --out" in out and "law 5" in out and seen == []
    assert not target.exists() and not target.parent.exists()
    assert not (ROOT / "data" / "r.json").exists()


def test_out_under_the_checkouts_data_is_refused_by_its_resolved_path(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "elsewhere").symlink_to(tmp_path / "data")
    assert probe.refuse_out(tmp_path / "elsewhere" / "r.json").startswith("REFUSED: --out")


def test_an_out_that_cannot_be_written_is_refused_before_any_call(env, capsys, tmp_path):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run(["--out", str(tmp_path)], capsys)
    assert rc == 2 and "is a directory" in out and seen == []


@pytest.mark.parametrize("args, line", [
    (["--date", "2026-11-7"], "REFUSED: --date '2026-11-7' is not YYYY-MM-DD"),
    (["--served-zone", "Synthetic/Nowhere"], "REFUSED: --served-zone 'Synthetic/Nowhere' is not an IANA zone name"),
    (["--skip", "status", "--skip", "games", "--skip", "starters", "--skip", "terms"],
     "REFUSED: --skip names every section"),
    (["--games-path", "/scores/json/GamesByDate/{date}?key=x"], "REFUSED: --games-path names a key in the URL"),
    (["--base-url", "https://synthetic.invalid/{key}"], "REFUSED: --base-url names a key in the URL")])
def test_bad_arguments_are_refused_before_any_call(env, capsys, args, line):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run(args, capsys)
    assert rc == 2 and line in out and seen == []


def test_an_unknown_skip_is_an_argument_refusal(env, capsys):
    assert probe.main([*FULL, "--skip", "kalshi"]) == 2                                # no Kalshi section exists


def test_the_date_renders_in_both_path_forms():
    assert probe.render("/a/{date_mon}", "2026-11-07") == "/a/2026-NOV-07"
    assert probe.render("/a/{date}", "2026-01-31") == "/a/2026-01-31"


def test_a_failed_call_beats_a_refusal_in_the_exit_code(env, capsys):
    env.setattr(requests, "get", router({"GamesByDate": Resp([], status=502)}))
    base = [x for x in FULL if x not in ("--terms-url", TERMS_URL)]                  # terms REFUSED as well
    rc, out = run([], capsys, base=base)
    assert rc == 1 and "EXIT 1 (a call failed)" in out


def test_a_section_that_raises_is_failed_and_the_next_section_runs(env, capsys, monkeypatch):
    env.setattr(requests, "get", router())

    def boom(*a, **k):
        raise RuntimeError("synthetic: unexpected shape")
    monkeypatch.setattr(probe, "games_section", boom)
    rc, out = run([], capsys)
    assert rc == 1
    assert "FAILED: RuntimeError: synthetic: unexpected shape (section games stopped" in out
    assert "TERMS QUOTED" in out


def test_a_receipt_write_that_fails_is_failed_not_a_traceback(env, capsys, tmp_path, monkeypatch):
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"

    def boom(self, *a, **k):
        raise OSError("synthetic: disk full")
    monkeypatch.setattr(Path, "write_text", boom)
    rc, out = run(["--out", str(out_file)], capsys)
    assert rc == 1 and "FAILED: the receipt was not written: OSError: synthetic: disk full" in out


def test_every_unverified_default_is_flagged_and_no_stamp_default_exists():
    src = SCRIPT.read_text()
    assert "UNVERIFIED defaults" in src and probe.STAMP_FIELD is None and probe.SERVED_ZONE is None
    assert probe.KEY_NAME == "SPORTSDATAIO_NHL_KEY"
    for opt in ("--base-url", "--key-header", "--status-path", "--games-path", "--starters-path",
                "--game-id-field", "--start-field", "--home-goalie-field", "--away-goalie-field"):
        assert opt in src


ALLOWED_IMPORTS = {"__future__", "argparse", "html", "json", "os", "re", "sys", "datetime", "pathlib", "urllib.parse",
                   "zoneinfo", "requests", "dotenv"}


def test_the_probe_imports_nothing_that_opens_the_db_and_no_kalshi_code():
    """Statically: every import is in the allow-list (stdlib, requests, dotenv): no src module at all, Kalshi's
    included (279 item 5: KXNHLGAME untouched). Dynamically: a fresh interpreter that loads the script holds no src.db,
    sqlalchemy, src.ingestion, src.adapters or src.walters module."""
    tree = ast.parse(SCRIPT.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module)
    assert names <= ALLOWED_IMPORTS, names - ALLOWED_IMPORTS
    code = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('p', sys.argv[1]); "
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); import dotenv; "
            "print(sorted(k for k in sys.modules if k.startswith(('src', 'sqlalchemy'))))")
    got = subprocess.run([sys.executable, "-c", code, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT,
                         timeout=60)
    assert got.returncode == 0, got.stderr
    assert got.stdout.strip() == "[]"


# ---- review round 1: the defects verified, each pinned (synthetic values only) ---------------------------------

def test_a_goalie_served_as_a_list_never_prints_a_price_class_value(env, capsys, tmp_path):
    """A side served as a list: every entry goes through the price rule (never a raw repr); two goalies for one side, or
    an empty list, refuse that game (none is picked); a one-entry list is that goalie."""
    items = [starter(9101, f"{DAY}T15:30:00", HomeGoaltender=[goalie(1, "Synthetic G1"), goalie(2, "Synthetic G2")],
                     AwayGoaltender=[]),
             starter(9102, "2026-11-08T02:30:00Z", HomeGoaltender=[goalie(3, "Synthetic G3")])]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--out", str(out_file)], capsys)
    assert rc == 2, out
    text = out + out_file.read_text()
    assert str(SECRET_SALARY) not in text
    assert "2 goaltenders served for the home side under HomeGoaltender (exactly one required; none is picked)" in out
    assert "an empty list served for the away side under AwayGoaltender" in out
    assert "Synthetic G1" in out and "Synthetic G2" in out                          # every entry printed
    rows = {str(g["game"]): g for g in json.loads(out_file.read_text())["sections"]["starters"]["games"]}
    assert rows["9101"]["verdict"] == "REFUSED" and rows["9102"]["verdict"] == "PREGAME"
    assert str(SECRET_SALARY) not in probe.goalie_text([{"Name": "G", "DraftKingsSalary": SECRET_SALARY}])
    assert str(SECRET_SALARY) not in probe.goalie_text([[{"Nested": {"FanDuelSalary": SECRET_SALARY}}]])


@pytest.mark.parametrize("value", [{}, {"PlayerID": None, "Name": None}, {"Name": ""}, [], "  "])
def test_a_goalie_with_nothing_served_refuses_that_game(env, capsys, value):
    items = [starter(9101, f"{DAY}T15:30:00", HomeGoaltender=value), STARTERS[1]]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2, out
    assert "VERDICT REFUSED: " in out and "home side under HomeGoaltender" in out
    assert "PREGAME 0" in out


def test_the_terms_quote_every_retention_passage_ahead_of_the_generic_ones(env, capsys, tmp_path):
    """More generic hits than the probe quotes, the retention clause last on the page: it is still quoted, and the
    passages not quoted are counted."""
    page = "<p>" + " ".join(f"Synthetic: you own clause {i} of this licence." for i in range(25)) + \
           " Synthetic: upon termination you may retain no stored data.</p>"
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "status", "--skip", "games", "--skip", "starters", "--out", str(out_file)], capsys)
    assert rc == 0, out
    assert '"Synthetic: upon termination you may retain no stored data."' in out
    t = json.loads(out_file.read_text())["sections"]["terms"]
    assert t["quoted"][0] == "Synthetic: upon termination you may retain no stored data."
    assert t["not_quoted"] == 25 - (probe.TERMS_QUOTES - 1)
    assert f"(+{t['not_quoted']} more passage" in out


def test_a_cut_terms_passage_is_marked_with_its_full_length():
    long = "Synthetic: you own " + "x" * 2000 + "."
    got = probe.terms_excerpt(f"<p>{long}</p>")
    assert len(got) == 1 and got[0].endswith(f"[cut at {probe.TERMS_QUOTE_CHARS} of {len(long)} characters]")


def test_a_terms_page_with_no_listed_word_quotes_its_head_for_the_record_and_is_refused(env, capsys):
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text="<p>Synthetic welcome text only.</p>")}))
    rc, out = run(["--skip", "status", "--skip", "games", "--skip", "starters"], capsys)
    assert rc == 2 and '"Synthetic welcome text only."' in out                    # quoted for the record only
    assert "FOR THE RECORD ONLY (1 passage: the page's head;" in out
    assert probe.terms_excerpt("<p>Synthetic welcome text only.</p>") == ["Synthetic welcome text only."]


def test_the_status_read_prints_names_and_only_the_named_non_billing_values(env, capsys, tmp_path):
    """The status answer: every field NAME as served, values only for the --status-value-field names (an allow-list),
    never a billing figure under a name the price rule misses and never an account field."""
    body = {"Season": 2027, "MonthlyRate": 4321, "Tier": "SynthTier", "AccountName": "Synthetic Person",
            "Rate": 55, "Plain": 6543}
    env.setattr(requests, "get", router({"CurrentSeason": Resp(body)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--out", str(out_file)], capsys)
    assert rc == 0, out
    text = out + out_file.read_text()
    for secret in ("4321", "SynthTier", "Synthetic Person", "6543", "= 55"):
        assert secret not in text, secret
    assert "MonthlyRate (price-class: name only)" in out and "Tier (price-class: name only)" in out
    assert "AccountName" in out and "Season = 2027" in out
    assert "SeasonType: not served" in out
    assert probe.priced("MonthlyRate") and probe.priced("Rate") and probe.priced("PricePerMonth")
    assert not probe.priced("GeneratedAt") and not probe.priced("DateTime") and not probe.priced("Updated")


def test_a_bare_status_answer_prints_its_type_not_its_value(env, capsys):
    env.setattr(requests, "get", router({"CurrentSeason": Resp(8765)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 0, out
    assert "8765" not in out and "a int as served (its value not printed" in out


@pytest.mark.parametrize("body", [{"Code": 401, "Message": "Synthetic: invalid subscription key"},
                                  {"statusCode": 403, "message": "synthetic"}, {"error": "synthetic"}])
def test_a_200_carrying_an_error_body_is_refused_and_stops_the_metered_calls(env, capsys, body):
    seen = []
    env.setattr(requests, "get", router({"CurrentSeason": Resp(body)}, seen=seen))
    rc, out = run([], capsys)
    assert rc == 2, out
    assert "REFUSED: HTTP 200 carrying an error body" in out
    assert "the key named SPORTSDATAIO_NHL_KEY answered" not in out
    assert out.count("the status read did not answer: no call made") == 2
    assert [u for u, h, p in seen] == [f"{BASE}/scores/json/CurrentSeason", TERMS_URL]


def test_every_field_name_is_read_from_every_element_of_a_nested_list():
    got = probe.field_union([{"GameID": 1, "Goaltenders": [{"Name": "a"}, {"Name": "b", "Updated": "x"}]}])
    assert got == ["GameID", "Goaltenders", "Goaltenders[].Name", "Goaltenders[].Updated"]


def test_a_game_id_served_twice_in_the_games_is_refused_never_picked(env, capsys):
    games = [GAMES[0], game(9101, f"{DAY}T14:00:00", "SHX", "SAX"), GAMES[1]]
    env.setattr(requests, "get", router({"GamesByDate": Resp(games)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2, out
    assert "REFUSED: game id '9101' served 2 times (exactly once required; none is picked)" in out
    assert "VERDICT REFUSED: no start time read for this game" in out
    assert "NOT BEFORE (-90.0" not in out and "'SAX' @ 'SHX' · start" not in out


def test_a_game_id_served_by_two_starters_items_is_refused_and_counted_once(env, capsys, tmp_path):
    items = [STARTERS[0], starter(9101, f"{DAY}T20:30:00", HomeGoaltender=goalie(5, "Synthetic Other")), STARTERS[1]]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--out", str(out_file)], capsys)
    assert rc == 2, out
    assert "GameID '9101' served by 2 starters items (exactly one required; none is picked)" in out
    assert "Synthetic Other" in out                                                   # every item printed
    assert "GAMES: 2 · PREGAME 0 · NOT PREGAME 1 · REFUSED 1" in out
    assert json.loads(out_file.read_text())["sections"]["starters"]["counts"] == \
        {"PREGAME": 0, "NOT PREGAME": 1, "REFUSED": 1}


@pytest.mark.parametrize("stamp, start, minutes", [
    ("2026-03-08T01:30:00", "2026-03-08T03:30:00", 60.0),          # across the spring-forward change, in New York
    ("2026-03-07T20:00:00", "2026-03-08T20:00:00", 1380.0),
    ("2026-03-08T01:30:00-05:00", "2026-03-08T03:30:00", 60.0)])
def test_values_read_in_the_served_zone_are_compared_as_real_instants_across_a_clock_change(stamp, start, minutes):
    c = probe.compare(stamp, start, NY)
    assert c["verdict"] == "BEFORE" and c["minutes_before_start"] == pytest.approx(minutes, abs=0.01), c


@pytest.mark.parametrize("value, why", [("2026-03-08T02:30:00", "does not exist"),
                                        ("2026-11-01T01:30:00", "is ambiguous")])
def test_a_wall_time_the_served_zone_skips_or_repeats_is_not_read(value, why):
    dt, how = probe.read_instant(value, NY)
    assert dt is None and why in how and "America/New_York" in how
    assert probe.compare(value, "2026-11-01T19:00:00-05:00", NY)["verdict"] == "REFUSED"


@pytest.mark.parametrize("value, label", [("2026-11-07T19:00:00+05", "offset +05"),
                                          ("2026-11-07T19:00:00-05:00:30", "offset -05:00:30"),
                                          ("2026-11-07T19:00:00+0530", "offset +0530"),
                                          ("2026-11-07T19:00:00-05:00", "offset -05:00"),
                                          ("2026-11-07T19:00:00", "no zone stated")])
def test_the_zone_label_follows_the_offset_as_written(value, label):
    assert probe.zone_of(value) == label
    if label != "no zone stated":
        dt, how = probe.read_instant(value, None)
        assert dt is not None and how == f"{label}, as served"


@pytest.mark.parametrize("frag, status", [("GamesByDate", 401), ("GamesByDate", 403),
                                          ("StartingGoaltendersByDate", 401), ("StartingGoaltendersByDate", 403)])
def test_a_metered_read_not_accepted_is_refused_not_failed(env, capsys, frag, status):
    env.setattr(requests, "get", router({frag: Resp({"message": "synthetic"}, status=status)}))
    rc, out = run(["--skip", "status", "--skip", "terms"], capsys)
    assert rc == 2, out
    assert f"HTTP {status}" in out and "EXIT 2 (a read refused)" in out


def test_a_games_item_that_is_not_an_object_is_refused(env, capsys):
    env.setattr(requests, "get", router({"GamesByDate": Resp([*GAMES, "synthetic-not-an-object"])}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2 and "REFUSED: 1 item(s) are not objects" in out


@pytest.mark.parametrize("frag", ["CurrentSeason", "GamesByDate", "StartingGoaltendersByDate"])
def test_a_200_answer_that_is_not_json_is_a_failed_call(env, capsys, frag):
    env.setattr(requests, "get", router({frag: Resp(ValueError("synthetic: not JSON"), text="<html>x</html>")}))
    rc, out = run(["--skip", "terms"] + (["--skip", "status"] if frag != "CurrentSeason" else []), capsys)
    assert rc == 1, out
    assert "FAILED: the answer is not JSON" in out


def test_a_status_value_field_holding_an_object_prints_its_names_not_its_values(env, capsys):
    body = {"Season": 2027, "Details": {"Inner": 4242}}
    env.setattr(requests, "get", router({"CurrentSeason": Resp(body)}))
    rc, out = run(["--skip", "terms", "--status-value-field", "Details", "--status-value-field", "Season"], capsys)
    assert rc == 0, out
    assert "4242" not in out and "Details = '<dict: its names above>'" in out and "Details.Inner" in out
    assert "Season = 2027" in out and "SeasonType" not in out.split("VALUES of")[1].split("\n(2)")[0]


# ---- Codex review round 1 (#857): each finding reproduced first, then pinned (synthetic values only) -----------

TERMS_ONLY = ["--skip", "status", "--skip", "games", "--skip", "starters"]


@pytest.mark.parametrize("page", ["<p>Synthetic: please sign in to continue.</p>",
                                  "<p>Synthetic: you own this licence.</p>"])
def test_f1_a_terms_page_with_no_retention_passage_is_refused(env, capsys, tmp_path, page):
    """A login, welcome or wrong page (no retention word): what it holds may print for the record, labelled so, but the
    section never reads OK without a retention passage quoted."""
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run([*TERMS_ONLY, "--out", str(out_file)], capsys)
    assert rc == 2, out
    assert "REFUSED: no passage holding a retention or storage word" in out
    assert "FOR THE RECORD ONLY" in out and "TERMS QUOTED" not in out
    t = json.loads(out_file.read_text())["sections"]["terms"]
    assert t["exit"] == 2 and t["retention_passages"] == 0 and t["retention_quoted"] is False


@pytest.mark.parametrize("text", ["the license costs 100 per month", "a fee of 100 applies", "100/month",
                                  "100 per seat per year", "billed 100 annually", "100 monthly", "100 a year",
                                  "Price: 1,000.00", "you pay 100", "100 each season", "the quoted rate is 100",
                                  "subscription 100 / yr", "charged at 100 for each call"])
def test_f2_a_price_written_as_a_per_period_amount_is_replaced(text):
    got = probe.Out().redact(text)
    assert "100" not in got and "1,000" not in got and "<figure not printed>" in got, got


def test_f2_the_widened_figure_rule_leaves_the_probes_own_lines_whole(env, capsys, tmp_path):
    """The widened rule runs on every line and the receipt: the probe's own reads (dates, times, ids, HTTP status,
    minutes, counts, rate-limit headers, URLs, season strings) are not touched, and the receipt still parses."""
    say = probe.Out()
    for line in ("HTTP 200 · 3 items · rate-limit {'X-RateLimit-Remaining': '9', 'Retry-After': '1'}",
                 "game 9101 · 'SAA' @ 'SHA' · Status 'Scheduled' · DateTime = '2026-11-07T19:00:00' (no zone)",
                 "(210.0 minutes, from the served values) · GAMES: 2 · PREGAME 1 · NOT PREGAME 1 · REFUSED 0",
                 '"minutes_before_start": 210.0, "not_quoted": 0, "retention_passages": 1, "chars": 512',
                 "GET https://synthetic.invalid/v3/nhl/scores/json/GamesByDate/2026-NOV-07 · Season = '2026/27'",
                 "TERMS QUOTED (2 passages: first every one holding a retention or storage word (1)"):
        assert say.redact(line) == line, line
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"
    rc, out = run(["--out", str(out_file)], capsys)
    assert rc == 0, out
    rec = json.loads(out_file.read_text())                                       # still valid JSON
    assert rec["sections"]["starters"]["games"][0]["stamps"][0]["minutes_before_start"] == 210.0
    assert out.count("<figure not printed>") == 1                               # the terms page's figure only


def test_f2_a_figure_in_the_terms_quote_is_replaced_in_the_receipt_too(env, capsys, tmp_path):
    """The receipt's quote is redacted at the source, and the receipt is written as UTF-8 text (a JSON escape of a
    currency sign would otherwise hide the figure from the redactor)."""
    page = f"<p>Synthetic: on termination delete stored data; the plan costs {chr(0x20ac)}100 or 100 per month.</p>"
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run([*TERMS_ONLY, "--out", str(out_file)], capsys)
    assert rc == 2, out                     # a bare number replaced in a retention passage: not shown whole (review 2)
    text = out_file.read_text(encoding="utf-8")
    assert "100" not in text and "100" not in out and "<figure not printed>" in text
    assert all("100" not in q for q in json.loads(text)["sections"]["terms"]["quoted"])


@pytest.mark.parametrize("value", [{"Candidates": []}, {"Candidates": [None, ""]}, {"A": {"B": [{}, {"C": None}]}},
                                   [{"Candidates": []}]])
def test_f3_a_goalie_whose_every_nested_value_is_empty_refuses_that_game(env, capsys, value):
    items = [starter(9101, f"{DAY}T15:30:00", HomeGoaltender=value), STARTERS[1]]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items)}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 2, out
    assert "every value null or empty (at any depth) served for the home side under HomeGoaltender" in out
    assert "PREGAME 0" in out


def test_f3_a_goalie_with_a_nested_value_served_is_read():
    assert probe.goalie_refusal(True, {"Candidates": [{"Name": "Synthetic G"}]}, "home", "H") is None
    assert probe.goalie_refusal(True, {"PlayerID": 0}, "home", "H") is None                 # zero is a value


@pytest.mark.parametrize("opt, value", [
    ("--games-path", "/scores/json/GamesByDate/{date_mon}?token=" + KEY),
    ("--base-url", BASE + "/" + KEY),
    ("--starters-path", "/projections/json/StartingGoaltendersByDate/{date}?t=%20" + KEY),
    ("--terms-url", TERMS_URL + "?k=" + KEY)])
def test_f4_a_url_carrying_the_loaded_key_under_any_name_is_refused_before_any_call(env, capsys, opt, value):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run([opt, value], capsys)
    assert rc == 2, out
    assert f"REFUSED: {opt} carries the value of SPORTSDATAIO_NHL_KEY" in out and seen == []
    assert KEY not in out


@pytest.mark.parametrize("form", [lambda k: k, lambda k: __import__("urllib.parse").parse.quote(k, safe=""),
                                  lambda k: __import__("urllib.parse").parse.quote_plus(k)])
def test_f4_the_key_is_found_in_its_trimmed_and_url_quoted_forms(env, capsys, form):
    secret = "SYNTH key/+&=9c"                                                  # synthetic, URL-special characters
    env.setenv("SPORTSDATAIO_NHL_KEY", f"  {secret}  ")
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run(["--games-path", "/g/{date}?x=" + form(secret)], capsys)
    assert rc == 2 and "REFUSED: --games-path carries the value of SPORTSDATAIO_NHL_KEY" in out and seen == []
    assert "SYNTH key" not in out


def test_f5_out_is_home_expanded_once_and_used_throughout(env, capsys, tmp_path):
    env.setattr(requests, "get", router())
    env.setenv("HOME", str(tmp_path / "home"))
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env.chdir(cwd)
    rc, out = run(["--out", "~/x/run.json"], capsys)
    assert rc == 0, out
    written = tmp_path / "home" / "x" / "run.json"
    assert json.loads(written.read_text())["exit"] == 0
    assert not (cwd / "~").exists()
    assert f"receipt written to {written}" in out


def test_f6_inline_markup_stays_inside_its_sentence():
    got = probe.terms_excerpt("<p>You must <strong>not</strong> retain data after <a href='#'>termination</a>.</p>"
                              "<div>Synthetic: <em>never</em> store<br>it.</div>")
    assert got == ["You must not retain data after termination.", "Synthetic: never store it."]  # <br> is a space
    assert probe.terms_excerpt("<p>Synthetic: <span>do</span><span>not</span> <i>store</i> it.</p>") == \
        ["Synthetic: do not store it."]                                                 # never a glued word
    assert probe.terms_excerpt("<p>Synthetic: delete&nbsp;<b>all</b>   stored &amp; cached data.</p>") == \
        ["Synthetic: delete all stored & cached data."]


def test_f7_time_fields_inside_list_elements_print_with_indexed_paths(env, capsys):
    g = game(9101, f"{DAY}T19:00:00", "SHA", "SAA",
             Periods=[{"Number": 1, "StartTime": f"{DAY}T19:05:00Z", "FeeTime": SECRET_COST},
                      {"Number": 2, "StartTime": f"{DAY}T19:45:00Z"}])
    env.setattr(requests, "get", router({"GamesByDate": Resp([g, GAMES[1]])}))
    rc, out = run(["--skip", "terms"], capsys)
    assert rc == 0, out
    assert f"Periods[0].StartTime = '{DAY}T19:05:00Z' (Z)" in out
    assert f"Periods[1].StartTime = '{DAY}T19:45:00Z' (Z)" in out
    assert "Periods[].StartTime" in out and str(SECRET_COST) not in out


def test_f2_a_currency_sign_in_an_error_body_is_replaced_in_the_receipt_too(env, capsys, tmp_path):
    """json.dumps escapes a non-ASCII sign by default; the receipt is written unescaped so the redactor sees it."""
    body = {"message": f"Synthetic: upgrade for {chr(0x20ac)}100"}
    env.setattr(requests, "get", router({"CurrentSeason": Resp(body)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--out", str(out_file)], capsys)
    assert rc == 2, out
    text = out_file.read_text(encoding="utf-8")
    assert "100" not in text and "100" not in out and "<figure not printed>" in text
    assert json.loads(text)["sections"]["status"]["error_body"]


# ---- review of the round-1 fixes: each problem reproduced first, then pinned (synthetic values only) ---------------

@pytest.mark.parametrize("page, first", [
    ("<p>Billing records are retained 7 years.</p><p>Subscription data is stored 30 days after cancellation.</p>"
     "<p>This licence is personal.</p>", "Billing records are retained 7 years."),
    ("<p>Billing data is retained for 7 years.</p><p>Read the licence.</p>", "Billing data is retained for 7 years."),
    ("<p>Paid subscriber data is deleted 30 days after the term.</p>",
     "Paid subscriber data is deleted 30 days after the term."),
    ("<p>After the subscription we retain data for 30 days.</p><p>You may not copy the database.</p>",
     "After the subscription we retain data for 30 days."),
    ("<p>Data is stored until the end of the billing period plus 30 days.</p>",
     "Data is stored until the end of the billing period plus 30 days.")])
def test_r2_a_price_word_never_eats_a_retention_clause(page, first):
    """Retention is read on the unredacted sentence and the price rule replaces only the number: a retention clause
    that names a price word (billing, subscription, paid) is quoted whole, its retention period kept (a duration is
    not a price)."""
    t = probe.terms_read(page)
    assert t["retention"] >= 1 and t["quoted"][0] == first, t
    assert page.count("retain") + page.count("stored") + page.count("deleted") == t["retention"]


def test_r2_a_page_whose_retention_clause_names_the_subscription_reads_ok(env, capsys, tmp_path):
    page = "<p>After the subscription we retain data for 30 days.</p><p>You may not copy the database.</p>"
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run([*TERMS_ONLY, "--out", str(out_file)], capsys)
    assert rc == 0, out
    t = json.loads(out_file.read_text())["sections"]["terms"]
    assert t["retention_passages"] == 1 and t["quoted"][0] == "After the subscription we retain data for 30 days."


def test_r2_the_price_word_rule_replaces_only_the_number():
    assert probe.Out().redact("the license costs 100 per month") == "the license costs <figure not printed> per month"
    assert probe.Out().redact("a fee of 100 applies") == "a fee of <figure not printed> applies"


@pytest.mark.parametrize("text", ["Price (USD): 100", "Cost — 100", "Fee - 100", "100k per year",
                                  "the plan is 2.5k/month", "100 per calendar month", "the amount is 100", "rate 100",
                                  "Premium tier: 100"])
def test_r2_more_price_phrasings_are_replaced_on_every_line(text):
    got = probe.Out().redact(text)
    assert "100" not in got and "2.5" not in got and "<figure not printed>" in got, got


@pytest.mark.parametrize("text", ["100 per 1,000 calls", "100 each season", "100/day", "100 per request"])
def test_r2_count_unit_prices_are_replaced_in_the_terms_quote(text):
    got = probe.terms_excerpt(f"<p>Synthetic: data is stored; the plan is {text}.</p>")[0]
    assert "100" not in got and "<figure not printed>" in got, got


@pytest.mark.parametrize("line", [
    "Projections are updated daily at 10 AM ET",
    "Projections are updated daily at 10:00 AM ET.",
    "updated daily 2026-11-07T19:00:00Z",
    "Updated: refreshed daily at 10:00 AM ET, 4 times a day",
    "refreshed 4 times a week",
    "rate-limit {'X-RateLimit-Limit': '1000/day'}",
    "rate-limit {'X-RateLimit-Policy': '100 per hour'}",
    "rate-limit {'X-RateLimit-Limit': '1000', 'Retry-After': '30'}",
    "billed on 2026-11-07 and 11/07/2026 at 19:00"])
def test_r2_schedule_times_dates_and_rate_limit_quotas_are_not_figures(line):
    assert probe.Out().redact(line) == line


def test_r2_the_stamp_quote_prints_whole(env, capsys):
    env.setattr(requests, "get", router())
    quote = "Updated: refreshed daily at 10:00 AM ET, 4 times a day"
    rc, out = run(["--skip", "terms", "--stamp-quote", quote], capsys)
    assert rc == 0, out
    assert f'as quoted by the operator: "{quote}"' in out


def test_r6_a_br_inside_a_sentence_keeps_the_negation():
    assert probe.terms_excerpt("<p>You must not<br>retain data after expiry.</p>") == \
        ["You must not retain data after expiry."]


def test_r6_a_list_item_is_quoted_with_its_lead_in():
    assert probe.terms_excerpt("<p>You must not:</p><ul><li>retain data after expiry</li>"
                               "<li>copy the database</li></ul><p>Synthetic: data is stored.</p>") == \
        ["You must not: retain data after expiry", "Synthetic: data is stored.", "You must not: copy the database"]
    assert probe.terms_excerpt("<ul><li>Synthetic: never:<ol><li>store it</li></ol></li><li>cache it</li></ul>") == \
        ["Synthetic: never: store it", "cache it"]


# ---- second review of the round-1 fixes: each problem reproduced first, then pinned (synthetic values only) --------

def leaks(text: str, *figs: str) -> bool:
    return any(f in text for f in figs)


@pytest.mark.parametrize("text", ["100 \u20ac", "100\u20ac per month", "100 \u20ac per month", "1.100,00 \u20ac",
                                  "100\u00a3", "100,- \u20ac", "100\u00a0\u20ac per month"])
def test_r3_a_currency_sign_after_the_number_is_replaced(text):
    got = probe.Out().redact(text)
    assert not leaks(got, "100", "1.100") and "<figure not printed>" in got, got


def test_r3_a_sign_after_the_number_in_a_retention_clause_is_replaced_and_the_clause_reads_ok(env, capsys, tmp_path):
    page = "<p>EU customers: 100&nbsp;&euro; per month, data retained 30 days after cancellation.</p>"
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run([*TERMS_ONLY, "--out", str(out_file)], capsys)
    text = out_file.read_text(encoding="utf-8")
    assert rc == 0, out
    assert "100" not in out and "100" not in text and "data retained 30 days after cancellation." in out


@pytest.mark.parametrize("text", ["100-200 per month", "100\u2013200 per month", "100 to 200 a month",
                                  "between 100 and 200 a month", "fees of 100-200", "plans of 100-200 per month",
                                  "100 or 200 per month", f"{chr(36)}100-200", f"{chr(36)}100 to 200"])
def test_r3_both_ends_of_a_price_range_are_replaced(text):
    for terms in (False, True):
        got = probe.figures(text, terms)
        assert not leaks(got, "100", "200") and "<figure not printed>" in got, got


@pytest.mark.parametrize("text", ["100 billed annually", "100 billed monthly", "100 Billed yearly",
                                  "Annual plans (100 billed annually) may be cancelled", "100 charged monthly"])
def test_r3_a_number_billed_by_period_is_replaced(text):
    got = probe.Out().redact(text)
    assert "100" not in got and "<figure not printed>" in got, got


@pytest.mark.parametrize("text", ["The Pro plan is 100", "starts at 100", "Plans start at 100", "Plans from 100",
                                  "invoiced 100", "an invoice of 100", "Total: 100", "a total of 100", "subtotal 100",
                                  "a sum of 100"])
def test_r3_more_price_words_reach_their_number(text):
    got = probe.Out().redact(text)
    assert "100" not in got and "<figure not printed>" in got, got


@pytest.mark.parametrize("text", ["Price: 100 month-to-month", "Subscription: 100 month to month",
                                  "the subscription fee is 1,100 year-round"])
def test_r3_a_billing_term_after_a_price_does_not_shield_it(text):
    got = probe.Out().redact(text)
    assert not leaks(got, "100") and "<figure not printed>" in got, got


@pytest.mark.parametrize("sep", [" ", "\u00a0", "\u202f"])
def test_r3_a_number_grouped_with_a_space_is_replaced_whole(sep):
    assert probe.Out().redact(f"1{sep}100 per year") == "<figure not printed> per year"


@pytest.mark.parametrize("text", ["100 * per month",
                                  "100/mth", "100 per mth", "100/m", "100 p.a.", "100 pa", "Fee, 100",
                                  "Price \u00b7 100", "\u00a5100", "\u20b9100", "CAD 100", "100 CAD", "AUD 100",
                                  "100 US dollars", "100 bucks", "\uff11\uff10\uff10 per month", "$\uff11\uff10\uff10",
                                  "100\u202fper month"])
def test_r3_other_price_spellings_are_replaced(text):
    got = probe.Out().redact(text)
    assert not leaks(got, "100", "\uff11\uff10\uff10") and "<figure not printed>" in got, got


def test_r3_a_footnote_mark_between_price_and_period_is_replaced_in_the_terms_quote():
    got = probe.terms_excerpt("<p>Storage add-on: 100<sup>*</sup> per month; deleted on cancellation.</p>")
    assert got == ["Storage add-on: <figure not printed> * per month; deleted on cancellation."], got


def test_r3_a_no_break_space_in_an_error_body_does_not_hide_its_price(env, capsys, tmp_path):
    body = {"Message": "Synthetic: trial ended: renew at 100\u00a0per month"}
    env.setattr(requests, "get", router({"CurrentSeason": Resp(body)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--out", str(out_file)], capsys)
    text = out_file.read_text(encoding="utf-8")
    assert rc == 2, out
    assert "100" not in out and "100" not in text and "<figure not printed>" in text
    assert "<figure not printed>" in probe.safe_repr("renew at 100\u00a0per month")


def test_r3_a_stamp_or_id_served_as_an_object_never_prints_its_price_class_values(env, capsys, tmp_path):
    items = [starter(9101, f"{DAY}T15:30:00", Projection={"Updated": f"{DAY}T15:00:00Z",
                                                         "FanDuelSalary": SECRET_SALARY}), STARTERS[1]]
    games = [game(9101, f"{DAY}T19:00:00", {"Code": "SHA", "TicketPrice": SECRET_COST}, "SAA",
                  Status={"Name": "Scheduled", "FeeCode": SECRET_LINE}), GAMES[1]]
    env.setattr(requests, "get", router({"StartingGoaltendersByDate": Resp(items), "GamesByDate": Resp(games)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--stamp-field", "Projection", "--out", str(out_file)], capsys)
    text = out_file.read_text(encoding="utf-8")
    assert rc == 2, out
    for secret in (str(SECRET_SALARY), str(SECRET_COST), str(SECRET_LINE)):
        assert secret not in out and secret not in text
    assert "FanDuelSalary='<value not printed: price-class field>'" in out
    assert "HomeTeam (an object or list, not a value)" in out


def test_r3_the_key_in_a_url_in_another_case_is_refused_and_never_printed(env, capsys):
    secret = "synthkey0123abcdef"
    env.setenv("SPORTSDATAIO_NHL_KEY", secret)
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run(["--terms-url", TERMS_URL + "?token=" + secret.upper()], capsys)
    assert rc == 2 and "REFUSED: --terms-url carries the value of SPORTSDATAIO_NHL_KEY" in out and seen == []
    assert secret.upper() not in out and secret not in out
    say = probe.Out()
    say.secrets.add(secret)
    assert say.redact("echo " + secret.upper()) == "echo <redacted>"


@pytest.mark.parametrize("line", [
    "Updated is the time the projection was last changed; projections are available to paid subscribers by 9 AM ET "
    "and refreshed every 15 minutes",
    "Updated refreshes on all subscription tiers at 7 PM ET",
    "Premium tier projections post at 10 AM ET",
    "Premium tier projections post at 10am",
    "paid tiers refresh at 6 p.m. ET",
    "Updated: refreshed at a rate of 1 every 15 minutes",
    "updated 1 time per week",
    "subscription data from the 2025-26 season is deleted"])
def test_r3_a_clock_time_or_a_frequency_near_a_price_word_is_not_a_figure(line):
    assert probe.Out().redact(line) == line
    assert probe.figures(line, True) == line


def test_r3_the_stamp_quote_with_a_clock_time_prints_whole(env, capsys, tmp_path):
    env.setattr(requests, "get", router())
    quote = "Synthetic: Updated is when the projection changed; available to paid subscribers by 9 AM ET"
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "terms", "--stamp-quote", quote, "--out", str(out_file)], capsys)
    assert rc == 0, out
    assert f'as quoted by the operator: "{quote}"' in out
    assert json.loads(out_file.read_text())["sections"]["starters"]["stamp_quote"] == quote


@pytest.mark.parametrize("url", ["https://synthetic.invalid/subscription-agreement-2024",
                                 "https://synthetic.invalid/legal/terms#fees-3",
                                 "https://synthetic.invalid/terms?rate=1"])
def test_r3_the_terms_url_prints_as_given(env, capsys, tmp_path, url):
    page = "<p>Synthetic: on termination you must delete all stored data.</p>"
    env.setattr(requests, "get", router({url: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run([*TERMS_ONLY, "--terms-url", url, "--out", str(out_file)], capsys)
    assert rc == 0, out
    assert f"TERMS {url} \u00b7 HTTP 200" in out
    assert json.loads(out_file.read_text())["sections"]["terms"]["url"] == url


@pytest.mark.parametrize("text", ["Licensee may cache Data for no longer than 72 hours per game",
                                  "data is kept 30 days per season; 2 hours per user",
                                  "data is cached 24 hours a day"])
def test_r3_a_duration_before_per_is_never_a_figure(text):
    assert probe.figures(text) == text and probe.figures(text, True) == text


def test_r3_a_retention_period_before_per_keeps_the_page_ok(env, capsys):
    page = ("<p>Licensee may cache Data for no longer than 72 hours per game and must delete it when the subscription "
            "terminates or 30 days per season.</p>")
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    rc, out = run(TERMS_ONLY, capsys)
    assert rc == 0, out
    assert "72 hours per game" in out and "30 days per season" in out


def test_r3_a_retention_passage_with_a_number_replaced_is_refused(env, capsys, tmp_path):
    """The probe cannot tell a price from the clause's own number: a retention passage whose bare number the price rule
    replaced is not shown whole, so the page is not read OK (a currency figure is a price, and leaves it OK)."""
    page = "<p>Subscribers on the 100 per month plan must delete stored data on termination.</p>"
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    out_file = tmp_path / "r.json"
    rc, out = run([*TERMS_ONLY, "--out", str(out_file)], capsys)
    assert rc == 2, out
    assert "100" not in out and "a number replaced by the price rule" in out
    assert json.loads(out_file.read_text())["sections"]["terms"]["retention_figure"] == 1


@pytest.mark.parametrize("line", ["    message = 'Rate limit exceeded: 1000 calls per day'",
                                  "rate limit: 100 requests per minute"])
def test_r3_a_rate_limit_message_keeps_its_quota(line):
    assert probe.Out().redact(line) == line


def test_r3_a_source_line_break_never_splits_a_clause():
    assert probe._passages("<p>You must not\nretain the Data after the subscription ends.</p>") == \
        ["You must not retain the Data after the subscription ends."]
    assert probe.terms_excerpt("<p>You may not:</p>\n<ul>\n  <li>\n    store or cache the Data after termination\n"
                               "  </li>\n</ul>") == ["You may not: store or cache the Data after termination"]


def test_r3_a_list_item_wrapped_in_a_block_tag_keeps_its_lead_in():
    assert probe.terms_excerpt("<p>You may not:</p><ul><li><p>retain the Data after termination.</p></li></ul>") == \
        ["You may not: retain the Data after termination."]
    assert probe.terms_excerpt("<p>You may not:</p><ul><li><p>retain the Data.</p><p>Cache it after expiry.</p></li>"
                               "</ul>") == ["You may not: retain the Data.", "You may not: Cache it after expiry."]


@pytest.mark.parametrize("page", [
    "<form><p>Email</p><p>Password</p><button>Sign in</button><button>Cancel</button></form>",
    "<div>Your session has expired. Please sign in again.</div><form><p>Email</p></form>",
    "<p>Sign in</p><footer><a>Download on the App Store</a></footer>",
    "<h1>Cookie policy</h1><p>We store cookies on your device to remember your settings.</p>"])
def test_r3_a_login_or_cookie_page_is_not_read_as_the_terms(env, capsys, page):
    env.setattr(requests, "get", router({TERMS_URL: Resp(None, text=page)}))
    rc, out = run(TERMS_ONLY, capsys)
    assert rc == 2, out
    assert "FOR THE RECORD ONLY" in out and "TERMS QUOTED" not in out


def test_r3_a_table_row_and_a_heading_keep_the_subject_they_govern():
    assert probe.terms_excerpt("<table><tr><th>Data</th><th>Rule</th></tr><tr><td>Odds</td><td>Must be deleted upon "
                               "termination.</td></tr><tr><td>Scores</td><td>May be retained indefinitely.</td></tr>"
                               "</table>") == \
        ["Odds | Must be deleted upon termination.", "Scores | May be retained indefinitely."]
    assert probe.terms_excerpt("<h2>Odds data</h2><p>May be cached for 24 hours.</p>") == \
        ["Odds data May be cached for 24 hours."]
    assert probe.terms_excerpt("<dl><dt>Odds</dt><dd>Must be deleted upon termination.</dd></dl>") == \
        ["Odds Must be deleted upon termination."]


def test_r3_a_lead_in_governs_its_list_across_an_intro_and_without_a_colon():
    assert probe.terms_excerpt("<h3>You may not:</h3><p>The following apply to all plans.</p><ul><li>store the Data "
                               "after termination</li></ul>") == \
        ["You may not: The following apply to all plans. store the Data after termination"]
    assert probe.terms_excerpt("<p>You agree that you will not</p><ul><li>retain any Data after termination; or</li>"
                               "<li>sublicense the Data.</li></ul>") == \
        ["You agree that you will not retain any Data after termination; or"]          # the other holds no listed word
    assert probe.terms_excerpt("<p>Data must be deleted on termination.</p><ul></ul>") == \
        ["Data must be deleted on termination."]                                    # an empty list takes nothing


def test_r3_a_sibling_lead_in_is_not_repeated():
    assert probe.terms_excerpt("<p>Customer agrees:</p><ul><li>Restrictions:</li><li>to retain no Data after expiry"
                               "</li></ul>") == ["Customer agrees: Restrictions: to retain no Data after expiry"]


def test_r3_an_abbreviation_does_not_split_a_sentence():
    assert probe.terms_excerpt("<p>You must not store Licensed Data, e.g. odds, after expiry of the Term.</p>") == \
        ["You must not store Licensed Data, e.g. odds, after expiry of the Term."]
