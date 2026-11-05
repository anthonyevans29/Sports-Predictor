"""The basketball source probe (ARCHITECT 2026-11-05 11:40 ET, addendum 261 item 1(a); lane basketball-market-only,
#839): read-only, on SYNTHETIC responses only. Every team, league, status word, ticker, fee field and URL answer below
is invented for the test and labelled synthetic; none is a provider's real value, and no field name here is confirmed
against a live answer (the probe exists to read them). HTTP is monkeypatched: no provider is reached.

Pinned: the parsers read by field name (flat and nested shapes, a side's 0 kept), league ids read by exact served name
(zero or several refused, never a substring), the key fallback by NAME with no key value ever printed or written, the
/status account block never printed, the rate-limit headers printed as served, the Kalshi listing's rows and fee
fields as served (a failed listing is FAILED, not an empty match), the exit codes (0 / 1 / 2), --out refused under
data/, and an import graph that opens no DB. The review round added: the NBA JSON's own team list, the terms read and
quoted first (no URL typed; none given is REFUSED for ingest), each game counted once in the vocabulary, a key echoed at
any length never printed in part, data/ refused in any case and by resolved path, --out checked before any call, every
/status attempt counted with its headers, a league with no season refused in the receipt, an answer of the wrong shape
or a raising section FAILED (never a traceback), the honest scored-game labels, and --skip of every section refused."""
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "basketball_source_probe.py"
spec = importlib.util.spec_from_file_location("basketball_source_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

DAY = "2026-11-04"                                   # synthetic run day
KEY_B = "SYNTH-BASKETBALL-KEY-7f3a"                  # synthetic secrets: must never appear in any output
KEY_F = "SYNTH-SHARED-KEY-91c2"
RATE = {"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "93", "X-RateLimit-Remaining": "9",
        "Content-Type": "application/json"}

# ---- synthetic API-Sports-shaped answers --------------------------------------------------------------------------
STATUS = {"errors": [], "response": {"account": {"firstname": "Synth", "email": "synthetic-account@example.invalid"},
                                     "subscription": {"plan": "SynthPlan", "end": "2027-01-01", "active": True},
                                     "requests": {"current": 3, "limit_day": 100}}}
BAD_STATUS = {"errors": {"token": f"synthetic: the key {KEY_B} is not subscribed to this product"}, "response": []}


def lg(lid, name, *seasons, country="Synthland"):
    return {"id": lid, "name": name, "type": "League", "country": {"name": country},
            "seasons": [{"season": s} for s in seasons]}


LEAGUES = [lg(9001, "NBA", "SYN-2025", "SYN-2026"), lg(9002, "NCAA", "SYN-2026"), lg(9003, "NCAA Women", "SYN-2026"),
           lg(9004, "Synthetic Other League", "SYN-2026"), lg(9005, "WNBA", "SYN-2026")]


def game(gid, home, away, hs, as_, short, long_, date=f"{DAY}T00:30:00+00:00"):
    return {"id": gid, "date": date, "timestamp": 1, "status": {"short": short, "long": long_},
            "teams": {"home": {"id": gid * 10, "name": home}, "away": {"id": gid * 10 + 1, "name": away}},
            "scores": {"home": {"quarter_1": None, "total": hs}, "away": {"quarter_1": None, "total": as_}}}


DAY_GAMES = [game(1, "Synthetic Home A", "Synthetic Away A", None, None, "SNS", "Synthetic Not Started"),
             game(2, "Synthetic Home B", "Synthetic Away B", 101, 99, "SFT", "Synthetic Finished")]
SEASON_GAMES = DAY_GAMES + [game(3, "Synthetic Home C", "Synthetic Away C", 88, 90, "SOT", "Synthetic After OT",
                                 date="2026-10-30T00:00:00+00:00")]
TEAMS = [{"id": i, "name": f"Synthetic Team {i}", "code": None} for i in range(1, 6)]

# ---- synthetic NBA-JSON-shaped answers ----------------------------------------------------------------------------
NBA_URL = "https://synthetic.invalid/schedule.json"
BOX_URL = "https://synthetic.invalid/box_{game_id}.json"


SH = (1, "SynthHome", "Synth", "SHH")                # synthetic teams: (teamId, teamName, teamCity, teamTricode)
SA = (2, "SynthAway", "Synth", "SAA")
SX = (3, "SynthThird", "Synthville", "SXX")


def nba_game(gid, status, text, date, hs, as_, home=SH, away=SA):
    side = lambda t, sc: {"teamId": t[0], "teamName": t[1], "teamCity": t[2], "teamTricode": t[3], "score": sc}  # noqa
    return {"gameId": gid, "gameStatus": status, "gameStatusText": text, "gameDateTimeUTC": date,
            "homeTeam": side(home, hs), "awayTeam": side(away, as_)}


SCHEDULE = {"leagueSchedule": {"gameDates": [{"games": [
    nba_game("SYN0001", 3, "Synthetic Final", f"{DAY}T00:30:00Z", 110, 104),
    nba_game("SYN0002", 1, "Synthetic 7:00 pm", "2026-11-09T00:00:00Z", 0, 0),
    nba_game("SYN0003", 1, "Synthetic 8:00 pm", "2026-11-10T00:00:00Z", 0, 0, home=SX, away=SH)]}]}}
TERMS_URL = "https://synthetic.invalid/terms"
TERMS_HTML = ("<html><head><style>p{}</style><script>var x=1;</script></head><body><h1>Synthetic Terms</h1>"
              "<p>Synthetic clause one applies to visitors.</p><p>Synthetic clause: you may not use automated means "
              "to access this synthetic site.</p></body></html>")
BOX = {"meta": {"synthetic": True}, "game": nba_game("SYN0001", 3, "Synthetic Final", f"{DAY}T00:30:00Z", 110, 104)}

# ---- synthetic Kalshi-listing-shaped answer -----------------------------------------------------------------------
SERIES = {"series": [
    {"ticker": "SYNTHBBGAME", "title": "Synthetic basketball game", "category": "Sports", "tags": ["Basketball"],
     "fee_type": "synthetic_fee_type", "fee_multiplier": "synthetic-m"},
    {"ticker": "SYNTHBBCHAMP", "title": "Synthetic basketball champion", "category": "Sports", "tags": ["Basketball"]},
    {"ticker": "SYNTHFBGAME", "title": "Synthetic football game", "category": "Sports", "tags": ["Football"]}]}


class Resp:
    def __init__(self, body, status=200, headers=None, text=None):
        self._body, self.status_code, self.headers = body, status, dict(headers if headers is not None else RATE)
        self.text = text if text is not None else json.dumps(body, default=str)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"synthetic HTTP {self.status_code}")


def router(overrides=None, seen=None):
    """A fake requests.get dispatching on the URL; `overrides` maps a URL fragment to a Resp or an exception."""
    overrides = overrides or {}

    def get(url, headers=None, params=None, timeout=None):
        if seen is not None:
            seen.append((url, dict(headers or {}), dict(params or {})))
        for frag, r in overrides.items():
            if frag in url:
                if isinstance(r, Exception):
                    raise r
                return r(url, headers, params) if callable(r) else r
        key = (headers or {}).get(probe.KEY_HEADER)
        if url.endswith("/status"):
            return Resp(STATUS if key == KEY_F or key == "only" else BAD_STATUS)
        if url.endswith("/leagues"):
            return Resp({"errors": [], "response": LEAGUES})
        if url.endswith("/teams"):
            return Resp({"errors": [], "response": TEAMS})
        if url.endswith("/games"):
            return Resp({"errors": [], "response": DAY_GAMES if "date" in (params or {}) else SEASON_GAMES})
        if url == NBA_URL:
            return Resp(SCHEDULE, headers={"Content-Type": "application/json"})
        if url.startswith("https://synthetic.invalid/box_"):
            return Resp(BOX, headers={})
        if url == TERMS_URL:
            return Resp(ValueError("synthetic: not JSON"), headers={"Content-Type": "text/html"}, text=TERMS_HTML)
        if url.endswith("/series"):
            return Resp(SERIES, headers={})
        raise AssertionError(f"unexpected URL {url}")
    return get


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(probe, "_load_env", lambda: None)
    monkeypatch.setenv("API_BASKETBALL_KEY", KEY_B)
    monkeypatch.setenv("API_FOOTBALL_KEY", KEY_F)
    return monkeypatch


def run(args, capsys):
    rc = probe.main(["--date", DAY, "--nba-schedule-url", NBA_URL, "--nba-boxscore-url", BOX_URL,
                     "--nba-terms-url", TERMS_URL, *args])
    return rc, capsys.readouterr().out


def test_every_section_reads_by_field_name_and_exits_0_with_the_receipt(env, capsys, tmp_path):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    out_file = tmp_path / "receipts" / "bball.json"
    rc, out = run(["--out", str(out_file)], capsys)
    assert rc == 0, out
    assert "NBA: id 9001 read by exact name 'NBA'" in out and "NCAA men's Division I: id 9002" in out
    assert "season 'SYN-2026' (the last /leagues lists, as served)" in out
    assert "TEAMS: 5" in out and "Synthetic Team 3" in out
    assert "ONE GAME WITH BOTH TOTALS (the first on the day; finished is not decided here): #2 Synthetic Away B 99 " \
           "@ Synthetic Home B 101" in out
    assert "status short 'SFT' · long 'Synthetic Finished'" in out
    assert "ONE FINISHED GAME" not in out and "ONE FINAL" not in out
    # the season's /games holds the day's games: each is counted once (the season call answered)
    assert "SOT | Synthetic After OT: 1" in out and "SFT | Synthetic Finished: 1" in out
    assert "SNS | Synthetic Not Started: 1" in out and "3 season games, each once)" in out
    assert "id 9003 · 'NCAA Women'" in out and "id 9005 · 'WNBA'" in out                   # candidates printed
    # (ii)
    assert "SYN0001 gameDateTimeUTC=2026-11-04T00:30:00Z SAA @ SHH · 3 | 'Synthetic Final' · 104-110" in out
    assert "ONE GAME WITH TWO NON-ZERO SCORES (the first on the day; finished is not decided here): box score " \
           "https://synthetic.invalid/box_SYN0001.json · HTTP 200" in out
    assert "gameStatusText 'Synthetic Final' · SAA 104 @ SHH 110" in out
    assert "gameDateEst 0" in out and "gameDateTimeUTC 3" in out                            # presence by name
    # (iii)
    assert "SYNTHBBGAME · 'Synthetic basketball game' · 'Sports' · tags ['Basketball'] · GAME · fee fields " \
           "{'fee_type': 'synthetic_fee_type', 'fee_multiplier': 'synthetic-m'}" in out
    assert "SYNTHBBCHAMP" in out and "fee fields none served" in out and "SYNTHFBGAME" not in out
    assert "EXIT 0 (every read answered)" in out
    rec = json.loads(out_file.read_text())
    assert rec["exit"] == 0 and set(rec["sections"]) == {"apisports", "nba", "kalshi"}
    assert rec["sections"]["apisports"]["leagues"]["NBA"]["both_totals"]["id"] == 2
    assert rec["sections"]["nba"]["scored_game"]["gameId"] == "SYN0001"
    assert rec["sections"]["kalshi"]["series"][0]["fee_fields"] == {"fee_type": "synthetic_fee_type",
                                                                    "fee_multiplier": "synthetic-m"}
    games = [p for u, h, p in seen if u.endswith("/games")]
    assert {"league": 9001, "season": "SYN-2026", "date": DAY} in games                    # the ids read, not typed
    assert {"league": 9002, "season": "SYN-2026"} in games


def test_the_key_is_never_printed_and_the_name_that_answered_is(env, capsys, tmp_path):
    """API_BASKETBALL_KEY is set but refused (the synthetic error even echoes it); API_FOOTBALL_KEY answers. Neither
    value reaches the console or the receipt; the account block of /status never prints."""
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "nba", "--skip", "kalshi", "--out", str(out_file)], capsys)
    assert rc == 0, out
    assert "key API_BASKETBALL_KEY: set, refused:" in out and "key API_FOOTBALL_KEY: set, answered" in out
    assert "key used: API_FOOTBALL_KEY (the value is never printed)" in out
    text = out + out_file.read_text()
    assert KEY_B not in text and KEY_F not in text and "<redacted>" in text
    assert "synthetic-account@example.invalid" not in text and "firstname" not in text
    assert "'plan': 'SynthPlan'" in out


def test_rate_limit_headers_print_as_served_and_nothing_else():
    assert probe.rate_headers(RATE) == {"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "93",
                                        "X-RateLimit-Remaining": "9"}
    assert probe.rate_headers({}) == {} and probe.rate_headers(None) == {}


def test_no_key_answers_refuses_with_exit_2(env, capsys):
    env.delenv("API_BASKETBALL_KEY")
    env.delenv("API_FOOTBALL_KEY")
    env.setattr(requests, "get", router())
    rc, out = run(["--skip", "nba", "--skip", "kalshi"], capsys)
    assert rc == 2
    assert "key API_BASKETBALL_KEY: not set" in out and "key API_FOOTBALL_KEY: not set" in out
    assert "REFUSED: no key name answered /status" in out and "EXIT 2 (a read refused)" in out


def test_a_failed_call_exits_1_and_the_other_sections_still_run(env, capsys):
    env.setattr(requests, "get", router({"/leagues": Resp({"errors": [], "response": []}, status=500)}))
    rc, out = run([], capsys)
    assert rc == 1
    assert "/leagues {} · HTTP 500" in out and "FAILED: HTTP 500" in out
    assert "ONE GAME WITH TWO NON-ZERO SCORES" in out and "SYNTHBBGAME" in out    # (ii) and (iii) ran
    assert "EXIT 1 (a call failed)" in out


def test_a_provider_error_on_a_200_is_a_failure():
    assert probe.provider_errors({"errors": {"plan": "synthetic"}}) == '{"plan": "synthetic"}'
    assert probe.provider_errors({"errors": []}) is None and probe.provider_errors({"errors": {}}) is None
    assert probe.provider_errors(None) is None


def test_league_ids_are_read_by_exact_served_name_never_a_substring():
    cands = probe.league_candidates(LEAGUES)
    assert [c["id"] for c in cands] == [9001, 9002, 9003, 9005]                     # 'NBA'/'NCAA' in the name
    assert probe.pick_league(cands, "NCAA")[0]["id"] == 9002                        # not 'NCAA Women'
    assert probe.pick_league(cands, "nba")[0]["id"] == 9001
    got, why = probe.pick_league(cands, "NCAA Men")
    assert got is None and why.startswith("0 leagues named exactly 'NCAA Men'")
    twice = probe.league_candidates(LEAGUES + [lg(9100, "NBA", "SYN-2026", country="Elsewhere")])
    got, why = probe.pick_league(twice, "NBA")
    assert got is None and why.startswith("2 leagues named exactly 'NBA'")
    assert probe.pick_league(twice, "NBA", "Elsewhere")[0]["id"] == 9100
    nested = probe.league_candidates([{"league": {"id": 7, "name": "NBA"}, "country": {"name": "S"},
                                       "seasons": [{"season": 1}]}])
    assert nested == [{"id": 7, "name": "NBA", "type": None, "country": "S", "seasons": [1]}]


def test_an_ambiguous_league_refuses_that_league_with_exit_2(env, capsys):
    dup = {"errors": [], "response": LEAGUES + [lg(9100, "NBA", "SYN-2026", country="Elsewhere")]}
    env.setattr(requests, "get", router({"/leagues": Resp(dup)}))
    rc, out = run(["--skip", "nba", "--skip", "kalshi"], capsys)
    assert rc == 2
    assert "NBA: 2 leagues named exactly 'NBA'" in out and "id 9100 · 'NBA'" in out
    assert "NCAA men's Division I: id 9002" in out                                  # the other league still reads


def test_game_rows_read_flat_and_nested_shapes_and_keep_a_zero():
    flat = probe.game_row(game(5, "H", "A", 0, 77, "SFT", "Synthetic Finished"))
    assert (flat["home_total"], flat["away_total"], flat["missing"]) == (0, 77, [])
    nested = probe.game_row({"game": {"id": 6, "date": {"date": DAY, "timestamp": 9}, "status": {"short": "S"}},
                             "teams": {"home": {"id": 1, "name": "H"}, "away": {"id": 2, "name": "A"}},
                             "scores": {"home": 0, "away": 3}})
    assert (nested["id"], nested["date"], nested["timestamp"], nested["home_total"], nested["away_total"]) == \
        (6, DAY, 9, 0, 3)
    assert probe.first_scored([flat]) is flat                                        # 0 is a total, not a missing one
    assert probe.game_row({"id": 1})["missing"] == ["date", "status", "teams.home", "teams.away", "scores"]


def test_a_required_field_not_served_refuses_the_read(env, capsys):
    bare = [{"id": 1, "when": DAY, "state": "x"}]
    env.setattr(requests, "get", router({"/games": lambda u, h, p: Resp({"errors": [], "response": bare})}))
    rc, out = run(["--skip", "nba", "--skip", "kalshi"], capsys)
    assert rc == 2
    assert "REFUSED: required field(s) not found in the first game: date, status, teams.home, teams.away, scores" \
        in out


def test_no_finished_game_on_the_day_refuses(env, capsys):
    day = {"errors": [], "response": [DAY_GAMES[0]]}
    env.setattr(requests, "get", router({"/games": lambda u, h, p: Resp(day)}))
    rc, out = run(["--skip", "nba", "--skip", "kalshi"], capsys)
    assert rc == 2 and f"REFUSED: no game on {DAY} carries both totals" in out


def test_the_nba_json_refuses_a_shape_it_cannot_read_and_a_day_with_no_final(env, capsys):
    env.setattr(requests, "get", router({NBA_URL: Resp({"synthetic": [1, 2]}, headers={})}))
    rc, out = run(["--skip", "apisports", "--skip", "kalshi"], capsys)
    assert rc == 2 and "REFUSED: no object holds both homeTeam and awayTeam · top-level keys ['synthetic']" in out
    env.setattr(requests, "get", router())
    rc, out = run(["--skip", "apisports", "--skip", "kalshi", "--date", "2026-11-09"], capsys)
    assert rc == 2 and "REFUSED: no game on 2026-11-09 carries two non-zero scores" in out
    assert "1 | Synthetic 7:00 pm: 1" in out                                         # the vocabulary still prints


def test_a_failed_kalshi_listing_is_failed_not_an_empty_match(env, capsys):
    env.setattr(requests, "get", router({"/series": requests.ConnectionError("synthetic: proxy refused")}))
    rc, out = run(["--skip", "apisports", "--skip", "nba"], capsys)
    assert rc == 1
    assert "FAILED: ConnectionError: synthetic: proxy refused" in out
    assert "FAILED: the series listing did not answer" in out


def test_out_under_data_is_refused_and_nothing_is_written(env, capsys, tmp_path):
    env.setattr(requests, "get", router())
    target = tmp_path / "data" / "r.json"
    rc, out = run(["--out", str(target)], capsys)
    assert rc == 2 and "REFUSED: --out" in out and "law 5" in out
    assert not target.exists() and not target.parent.exists()
    assert not (ROOT / "data" / "r.json").exists()


def test_a_bad_date_is_refused(env, capsys):
    rc, out = run(["--date", "2026-11-4x"], capsys)
    assert rc == 2 and "REFUSED: --date" in out


ALLOWED_IMPORTS = {"__future__", "argparse", "html", "json", "os", "re", "sys", "collections", "datetime", "pathlib", "requests",
                   "dotenv", "src.adapters.kalshi"}


def test_the_probe_imports_nothing_that_opens_the_db():
    """Statically: every import in the script is in the allow-list (stdlib, requests, dotenv, the Kalshi adapter).
    Dynamically: a fresh interpreter that loads the script holds no src.db, sqlalchemy, src.ingestion or
    src.walters module."""
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
            "print(sorted(k for k in sys.modules if k.startswith(('src.db', 'sqlalchemy', 'src.ingestion', "
            "'src.walters'))))")
    got = subprocess.run([sys.executable, "-c", code, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT,
                         timeout=60)
    assert got.returncode == 0, got.stderr
    assert got.stdout.strip() == "[]"


def test_the_lane_is_appended_with_261_item_1s_dates_and_no_existing_date_moves():
    """261 item 3: "The roadmap gains the two lanes with the dates above (no existing date moves)." Item 1's dated
    steps in due order; WNBA (item 1(d)) and the adapter ruling are undated, so they are live_needs text (a step's due
    is never null); 1(e)'s injury-report probe is placed on lane availability-record by 261 and is not a step here."""
    from src import roadmap as rm
    doc = rm.load()
    assert rm.validate(doc) == []
    names = [x["lane"] for x in doc["lanes"]]
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "basketball-market-only"]
    assert names.index("basketball-market-only") > names.index("soccer-v23")        # appended after every lane
    assert (ln["issue"], ln["registry_id"], ln["state"], ln["earliest_live"], ln["moved"]) == \
        (839, None, "to declare", None, [])
    assert ln["competitions"] == ["NBA", "NCAAMB", "WNBA"]
    assert [(s["owner"], s["due"], s["done"]) for s in ln["steps"]] == [
        ("code", "2026-11-10", None), ("code", "2026-11-19", None), ("operator", "2026-11-21", None),
        ("code", "2026-12-05", None)]
    assert "scripts/basketball_source_probe.py" in ln["steps"][0]["what"]
    assert "NCAAMB" in ln["steps"][3]["what"] and "never \"NCAA\", which is football" in ln["steps"][3]["what"]
    assert "the same adapter; wire in April for the May season" in ln["live_needs"]
    assert "A MODEL: NONE DECLARED." in ln["live_needs"]
    assert not any("injury" in s["what"] for s in ln["steps"])   # this lane only: other lanes pin their own steps


# ---- the review round's pins (each failed first on the build it fixes) -------------------------------------------

def test_the_nba_json_reads_the_nba_team_list_by_field_name(env, capsys, tmp_path):
    """261 item 1(a): "the team list for the NBA". Section (ii) is the named fallback, so it reads the teams itself:
    the distinct (teamId, teamTricode, teamCity, teamName) of the schedule's homeTeam/awayTeam objects."""
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "apisports", "--skip", "kalshi", "--out", str(out_file)], capsys)
    assert rc == 0, out
    assert "NBA TEAMS (distinct homeTeam/awayTeam, by teamId · teamTricode · teamCity · teamName): 3" in out
    assert "1 · SHH · Synth · SynthHome" in out and "3 · SXX · Synthville · SynthThird" in out
    teams = json.loads(out_file.read_text())["sections"]["nba"]["teams"]
    assert teams == [{"teamId": 1, "teamTricode": "SHH", "teamCity": "Synth", "teamName": "SynthHome"},
                     {"teamId": 2, "teamTricode": "SAA", "teamCity": "Synth", "teamName": "SynthAway"},
                     {"teamId": 3, "teamTricode": "SXX", "teamCity": "Synthville", "teamName": "SynthThird"}]


def test_the_probe_quotes_the_terms_before_reading_the_nba_json(env, capsys, tmp_path):
    """261 item 4: "no scraping of a source whose terms forbid it (the probe quotes the terms)". The terms URL is the
    operator's (no default: no URL typed from memory); the terms are read FIRST and quoted, script/style stripped."""
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "apisports", "--skip", "kalshi", "--out", str(out_file)], capsys)
    assert rc == 0, out
    urls = [u for u, h, p in seen]
    assert urls.index(TERMS_URL) < urls.index(NBA_URL)                               # terms first
    assert f"TERMS {TERMS_URL} · HTTP 200" in out
    assert '"Synthetic clause: you may not use automated means to access this synthetic site."' in out
    assert "var x=1" not in out and "p{}" not in out
    t = json.loads(out_file.read_text())["sections"]["nba"]["terms"]
    assert t["url"] == TERMS_URL and t["read"] is True
    assert any("automated means" in q for q in t["quoted"])


def test_no_terms_url_means_terms_not_read_and_section_ii_refused_for_ingest(env, capsys):
    env.setattr(requests, "get", router())
    rc = probe.main(["--date", DAY, "--nba-schedule-url", NBA_URL, "--nba-boxscore-url", BOX_URL,
                     "--skip", "apisports", "--skip", "kalshi"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "TERMS NOT READ (no --nba-terms-url given; no URL is typed here)" in out
    assert "section (ii) is REFUSED for ingest until the terms are quoted (261 item 4)" in out
    assert "NBA TEAMS" in out                                                        # the reads still print
    assert probe.NBA_TERMS_URL is None


def test_the_terms_excerpt_strips_markup_and_quotes_the_access_clauses():
    html = ("<script>bad()</script><p>Synthetic intro.</p><p>Synthetic: no scraping, crawling or robots.</p>"
            "<p>Synthetic: commercial use needs a licence.</p>")
    got = probe.terms_excerpt(html)
    assert got == ["Synthetic: no scraping, crawling or robots.", "Synthetic: commercial use needs a licence."]
    assert probe.terms_excerpt("<p>Synthetic: capital rapid.</p><p>Synthetic: the API terms.</p>") == \
        ["Synthetic: the API terms."]                                                # a word's start, not inside one
    plain = probe.terms_excerpt("<p>Synthetic text with no clause words at all.</p>")
    assert plain == ["Synthetic text with no clause words at all."]                 # the head, when no clause hits


def test_a_key_echoed_across_any_length_never_prints_in_part(env, capsys, tmp_path):
    """The redaction runs on the whole text: no error string is cut before it (a cut inside the key left a prefix that
    no longer equalled the secret)."""
    key = "SYNTHKEY0123456789abcdef0123456789"
    env.setenv("API_BASKETBALL_KEY", key)
    long_bad = {"errors": {"token": "synthetic " + "x" * 250 + " key=" + key}, "response": []}
    env.setattr(requests, "get", router({"/status": lambda u, h, p: Resp(
        long_bad if h.get(probe.KEY_HEADER) == key else STATUS)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "nba", "--skip", "kalshi", "--out", str(out_file)], capsys)
    assert rc == 0, out
    text = out + out_file.read_text()
    assert key[:8] not in text and "<redacted>" in text


@pytest.mark.parametrize("rel", ["data/r.json", "Data/r.json", "DATA/r.json", "x/dAtA/y/r.json"])
def test_out_under_data_is_refused_in_any_case(rel):
    """The laptop is macOS (a case-insensitive filesystem): Data/ is data/."""
    assert probe.refuse_out(Path(rel)).startswith("REFUSED: --out")


def test_out_under_the_checkouts_data_is_refused_by_its_resolved_path(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "elsewhere").symlink_to(tmp_path / "data")
    assert probe.refuse_out(tmp_path / "elsewhere" / "r.json").startswith("REFUSED: --out")


def test_an_out_that_cannot_be_written_is_refused_before_any_call(env, capsys, tmp_path):
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run(["--out", str(tmp_path)], capsys)                                  # an existing directory
    assert rc == 2 and "is a directory" in out and seen == []
    afile = tmp_path / "afile"
    afile.write_text("synthetic")
    rc, out = run(["--out", str(afile / "r.json")], capsys)                          # its parent is a file
    assert rc == 2 and "REFUSED: --out" in out and seen == []


def test_a_receipt_write_that_fails_after_the_run_is_failed_not_a_traceback(env, capsys, tmp_path, monkeypatch):
    env.setattr(requests, "get", router())
    out_file = tmp_path / "r.json"

    def boom(self, *a, **k):
        raise OSError("synthetic: disk full")
    monkeypatch.setattr(Path, "write_text", boom)
    rc, out = run(["--skip", "nba", "--skip", "kalshi", "--out", str(out_file)], capsys)
    assert rc == 1 and "FAILED: the receipt was not written: OSError: synthetic: disk full" in out


def test_the_call_count_includes_every_status_attempt_and_each_prints_its_headers(env, capsys):
    """API_BASKETBALL_KEY refused, API_FOOTBALL_KEY answers: 2 /status + /leagues + 3 per league x 2 = 9."""
    seen = []
    env.setattr(requests, "get", router(seen=seen))
    rc, out = run(["--skip", "nba", "--skip", "kalshi"], capsys)
    assert rc == 0, out
    n = sum(1 for u, h, p in seen if u.startswith(probe.APISPORTS_BASE))
    assert n == 9 and "API-Sports calls this run: 9 (every /status attempt included)" in out
    lines = [x for x in out.splitlines() if x.strip().startswith("key API_")]
    assert len(lines) == 2 and all("rate-limit {'x-ratelimit-requests-limit': '100'" in x for x in lines)


def test_a_league_with_no_season_listed_is_refused_in_the_receipt(env, capsys, tmp_path):
    bare = {"errors": [], "response": [lg(9001, "NBA"), lg(9002, "NCAA")]}
    env.setattr(requests, "get", router({"/leagues": Resp(bare)}))
    out_file = tmp_path / "r.json"
    rc, out = run(["--skip", "nba", "--skip", "kalshi", "--out", str(out_file)], capsys)
    assert rc == 2 and "REFUSED: NBA: /leagues lists no season for id 9001" in out
    got = json.loads(out_file.read_text())["sections"]["apisports"]["leagues"]
    assert got == {"NBA": {"id": 9001, "name": "NBA", "refused": "no season listed"},
                   "NCAA men's Division I": {"id": 9002, "name": "NCAA", "refused": "no season listed"}}


def test_a_response_that_is_not_a_list_is_a_failed_call_not_a_traceback(env, capsys):
    env.setattr(requests, "get", router({"/teams": Resp({"errors": [], "response": {"synthetic": 1}})}))
    rc, out = run([], capsys)
    assert rc == 1
    assert "FAILED: 'response' is dict, not a list" in out
    assert "ONE GAME WITH TWO NON-ZERO SCORES" in out and "SYNTHBBGAME" in out      # (ii) and (iii) still ran


def test_a_section_that_raises_is_failed_and_the_next_section_runs(env, capsys, monkeypatch):
    env.setattr(requests, "get", router())

    def boom(*a, **k):
        raise RuntimeError("synthetic: unexpected shape")
    monkeypatch.setattr(probe, "nba_section", boom)
    rc, out = run(["--skip", "apisports"], capsys)
    assert rc == 1
    assert "FAILED: RuntimeError: synthetic: unexpected shape" in out and "SYNTHBBGAME" in out
    assert "EXIT 1 (a call failed)" in out


def test_skipping_every_section_is_refused_not_exit_0(env, capsys):
    env.setattr(requests, "get", router())
    rc, out = run(["--skip", "apisports", "--skip", "nba", "--skip", "kalshi"], capsys)
    assert rc == 2 and "REFUSED: --skip names every section; nothing would be read" in out
    assert "EXIT 0" not in out
