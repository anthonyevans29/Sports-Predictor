"""THE NHL LANDING FEED (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(b); 258 item 2(2), #835 item 2; 2026-11-11,
addenda 340 and 341 item 2): the adapter, its watch tick, the schedule's support read, the mapping, the poll key, the
command, on a throwaway SQLite file (fresh_db below) with a fake HTTP layer: NO NETWORK.

EVERY PAYLOAD IN THIS FILE IS SYNTHETIC, in the shapes the probe's and the receipt's own tests build
(tests/test_nhl_starter_timing_probe.py, tests/test_nhl_leaders_order_receipt.py): game ids, player ids ("G<n>") and
times are made up. No provider payload is committed (252; the brief). The 32 team names are the host's stored NHL
names as the architect read them on 2026-11-11 (addendum 341 item 2: "The 32 stored names, for your tests' pins").

Item 6, the parts this feed carries, verbatim in part: "(a) append-only — the ingest commands expose no update or
delete path, and a test asserts the tables' row counts only grow across a replay of saved payloads; [...] (c) the five
statuses on saved payloads: complete, partial (a team unmapped), empty, failed (a raised call), missed (a scheduled poll
with no call); [...] (e) the NHL adapter on the probe's saved payloads [...]: leaders[0] per side, two in net, no
goalieComparison; (f) a payload with an unmapped player keeps its name and NULL id; [...] (h) nothing under data/ after
any test."
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import text

import migrate_availability_record as mig
from src.availability import nhl_landing as nl
from src.availability import record as rec

REPO = Path(__file__).resolve().parents[1]
REPO_DATA_EXISTED = (REPO / "data").exists()

# addendum 341 item 2, verbatim: the host's 32 stored NHL names (2026-11-11)
HOST_NHL_TEAMS = (
    "Anaheim Ducks", "Boston Bruins", "Buffalo Sabres", "Calgary Flames", "Carolina Hurricanes", "Chicago Blackhawks",
    "Colorado Avalanche", "Columbus Blue Jackets", "Dallas Stars", "Detroit Red Wings", "Edmonton Oilers",
    "Florida Panthers", "Los Angeles Kings", "Minnesota Wild", "Montreal Canadiens", "Nashville Predators",
    "New Jersey Devils", "New York Islanders", "New York Rangers", "Ottawa Senators", "Philadelphia Flyers",
    "Pittsburgh Penguins", "San Jose Sharks", "Seattle Kraken", "St. Louis Blues", "Tampa Bay Lightning",
    "Toronto Maple Leafs", "Utah Mammoth", "Vancouver Canucks", "Vegas Golden Knights", "Washington Capitals",
    "Winnipeg Jets")

GAME = 2026020150                                          # SYNTHETIC game ids
START = datetime(2026, 11, 13, 0, 0)                       # NHL day 2026-11-12 (before 10:00Z)
DAY = START.date() - timedelta(days=1)

pytestmark = pytest.mark.usefixtures("fresh_db")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB, migrated; payloads under tmp_path; cwd = tmp_path. 6(h): no data/ anywhere after the test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nl, "PAYLOAD_BASE", tmp_path)
    db.init_db()
    assert mig.main() == 0
    yield path
    eng.dispose()
    assert not list(tmp_path.rglob("data")), "item 6(h): nothing under data/"
    assert (REPO / "data").exists() == REPO_DATA_EXISTED, "item 6(h): the repo's data/ untouched"


def _dt(d: datetime) -> str:
    """A naive UTC instant as SQLAlchemy stores it in SQLite."""
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


def _engine():
    import src.db.database as db
    return db._engine


def _counts() -> tuple[int, int]:
    with _engine().connect() as c:
        return tuple(c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in rec.TABLES)


def _obs() -> list[dict]:
    with _engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(f"SELECT * FROM {rec.OBS_TABLE} ORDER BY id"))]


def _asr() -> list[dict]:
    with _engine().connect() as c:
        rows = [dict(r._mapping) for r in c.execute(text(f"SELECT * FROM {rec.ASR_TABLE} ORDER BY id"))]
    for r in rows:
        r["attrs"] = json.loads(r["attrs"]) if r["attrs"] else None
    return rows


# ---- SYNTHETIC payloads (the probe's and the receipt's test shapes) --------------------------------------------------------

def _team(place, common, abbrev):
    return {"placeName": {"default": place}, "commonName": {"default": common}, "abbrev": abbrev}


TOR = ("Toronto", "Maple Leafs", "TOR")
BOS = ("Boston", "Bruins", "BOS")
MTL = ("Montréal", "Canadiens", "MTL")                      # accented, as the API serves it
UTA = ("Utah", "Mammoth", "UTA")
FAKE = ("Springfield", "Isotopes", "SPI")                   # a made-up club: refused


def _game(gid=GAME, start=START, home=TOR, away=BOS, gt=2):
    return {"id": gid, "startTimeUTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "gameType": gt,
            "homeTeam": _team(*home), "awayTeam": _team(*away)}


def _schedule(*games):
    return {"gameWeek": [{"games": list(games) or [_game()]}]}


def _landing(away_ids=(10, 11), home_ids=(20, 21), *, gc=True):
    def side(ids):
        return {"leaders": [{"playerId": i, "name": {"default": f"G{i}"}} for i in ids]}
    p = {"awayTeam": {"abbrev": "BOS"}, "homeTeam": {"abbrev": "TOR"}, "gameState": "FUT"}
    p["matchup"] = ({"goalieComparison": {"awayTeam": side(away_ids), "homeTeam": side(home_ids)}} if gc
                    else {"skaterComparison": {}})
    return p


def _goalie(i, toi):
    return {"playerId": i, "firstName": {"default": "F"}, "lastName": {"default": f"L{i}"}, "toi": toi}


def _box(away, home):
    return {"awayTeam": {"abbrev": "BOS"}, "homeTeam": {"abbrev": "TOR"},
            "playerByGameStats": {"awayTeam": {"goalies": away, "forwards": []},
                                  "homeTeam": {"goalies": home, "forwards": []}}}


class Resp:
    def __init__(self, status, body: bytes):
        self.status_code, self.content = status, body


class FakeHTTP:
    """url -> payload (dict, bytes, an int status, or an Exception to raise); records every call."""

    def __init__(self, routes=None):
        self.routes, self.calls = dict(routes or {}), []

    def __call__(self, url, timeout=None, headers=None):
        self.calls.append(url)
        v = self.routes.get(url, 404)
        if callable(v) and not isinstance(v, type):
            v = v()
        if isinstance(v, BaseException):
            raise v
        if isinstance(v, int):
            return Resp(v, b"")
        return Resp(200, v if isinstance(v, bytes) else json.dumps(v).encode())

    def n(self, part: str) -> int:
        return sum(part in u for u in self.calls)


def _routes(sched=None, landing=None, box=None, gid=GAME, day=DAY):
    return {nl.schedule_url(day): sched if sched is not None else _schedule(),
            nl.game_url(gid, "landing"): landing if landing is not None else _landing(),
            nl.game_url(gid, "boxscore"): box if box is not None else _box([_goalie(10, "60:00")],
                                                                              [_goalie(20, "60:00")])}


def _tick(http, at, *, dry_run=False, lag=timedelta(seconds=2)):
    return nl.tick(at, dry_run=dry_run, http_get=http, now_fn=lambda: at + lag)


def _nhl(names=HOST_NHL_TEAMS, match_pair=("Toronto Maple Leafs", "Boston Bruins"), start=START, status="SCHEDULED"):
    """SYNTHETIC store rows: the NHL competition, one team per name (the host's 32 by default), every team in a stored
    NHL match (the rows find_match compares), and the game's own match (home, away) at `start` when match_pair is set."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    ids, mid = {}, None
    with session_scope() as s:
        comp = Competition(sport=Sport.NHL, code="NHL", name="National Hockey League", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        for n in names:
            t = Team(sport=Sport.NHL, name=n)
            s.add(t)
            s.flush()
            ids[n] = t.id
        old = datetime(2026, 10, 10, 23)
        for i in range(0, len(names) - 1, 2):                  # every team in an old FINISHED NHL match
            s.add(Match(sport=Sport.NHL, competition_id=comp.id, season="2026", utc_date=old + timedelta(days=i),
                        status=MatchStatus.FINISHED, home_team_id=ids[names[i]], away_team_id=ids[names[i + 1]]))
        if len(names) % 2:
            s.add(Match(sport=Sport.NHL, competition_id=comp.id, season="2026", utc_date=old - timedelta(days=1),
                        status=MatchStatus.FINISHED, home_team_id=ids[names[-1]], away_team_id=ids[names[0]]))
        if match_pair:
            m = Match(sport=Sport.NHL, competition_id=comp.id, season="2026", utc_date=start,
                      status=MatchStatus[status], home_team_id=ids[match_pair[0]], away_team_id=ids[match_pair[1]])
            s.add(m)
            s.flush()
            mid = m.id
    return ids, mid


# ---- the constants are the probe's and the receipt's ---------------------------------------------------------------------

def _script(name):
    spec = importlib.util.spec_from_file_location(f"_t_{name}", REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_polls_and_the_day_are_the_probes_and_the_receipts():
    probe, receipt = _script("nhl_starter_timing_probe"), _script("nhl_leaders_order_receipt")
    assert tuple(off for _, off in nl.PREGAME) == probe.OFFSETS and nl.EVENTUAL[1] == probe.EVENTUAL
    assert tuple(lab for lab, _ in nl.PREGAME) == receipt.PREGAME and nl.EVENTUAL[0] == receipt.EVENTUAL
    assert nl.DAY_CUT_UTC == probe.DAY_CUT_UTC and nl.GAME_TYPES == set(probe.GAME_TYPES)
    assert [p.split()[0] for p in map(probe.label, (*probe.OFFSETS, probe.EVENTUAL))] == [x[0] for x in nl.POLLS]
    assert nl.MISSED_AFTER == timedelta(minutes=5)          # 252 item 3(b): "more than five minutes past its time"
    assert nl.SCHEDULE_TTL == timedelta(hours=1)            # 340 item 4: "at most hourly"


def test_the_leaders_reading_is_the_receipts_own_leader0(monkeypatch):
    """252 item 3(b): "EXACTLY as scripts/nhl_leaders_order_receipt.py reads it": the function called is the script's."""
    mod = nl._receipt()
    assert Path(mod.__file__).resolve() == (REPO / "scripts" / "nhl_leaders_order_receipt.py").resolve()
    seen = []
    monkeypatch.setattr(mod, "leader0", lambda ng, landing, side: (seen.append(side), ((7, "X"), ""))[1])
    assert nl.leader({}, "home") == ((7, "X"), "") and seen == ["home"]


def test_the_schedule_day_is_the_probes_day_games():
    probe = _script("nhl_starter_timing_probe")
    pay = _schedule(_game(), _game(GAME + 1, START + timedelta(days=1)), _game(GAME + 2, START, gt=1),
                    _game(GAME + 3, datetime(2026, 11, 12, 10, 0)))
    ours = [g["id"] for g in nl.day_games(pay, DAY)]
    assert ours == [g["id"] for g in probe.day_games(pay, DAY)] == [GAME + 3, GAME]


# ---- 6(e): the landing, per side ------------------------------------------------------------------------------------------

def test_6e_leaders0_per_side_two_projected_starters_mapped_complete():
    ids, mid = _nhl()
    http = FakeHTTP(_routes())
    t = _tick(http, START - timedelta(minutes=120))
    assert [p.label for p in t.due] == ["T-120"] and t.remaining == 8 and t.exit_code == 0
    (o,) = _obs()
    assert o["source"] == "nhl_api_landing" and o["poll_label"] == "T-120" and o["status"] == "complete"
    assert o["endpoint"] == f"https://api-web.nhle.com/v1/gamecenter/{GAME}/landing" and o["match_id"] == mid
    assert o["scheduled_at"] == _dt(START - timedelta(minutes=120)) and o["rows_asserted"] == 2
    assert o["kickoff_at"] == _dt(START) and not o["late"] and o["http_status"] == 200
    a = _asr()
    assert [(x["kind"], x["source_player_id"], x["player_name"], x["attrs"]["side"]) for x in a] == [
        ("projected_starter", "10", "G10", "away"), ("projected_starter", "20", "G20", "home")]
    assert [x["team_id"] for x in a] == [ids["Boston Bruins"], ids["Toronto Maple Leafs"]]
    assert [x["source_team"] for x in a] == ["BOS", "TOR"]                 # the source's text: the record's identity
    assert all(x["player_id"] is None and x["source_stamp"] is None and x["match_id"] == mid for x in a)   # 6(f)
    assert all(x["attrs"]["source_match_id"] == str(GAME) for x in a)
    assert http.n("/landing") == 1 and http.n("/boxscore") == 0


def test_6e_no_goalie_comparison_is_empty_and_one_side_missing_asserts_the_other():
    _nhl()
    http = FakeHTTP(_routes(landing=_landing(gc=False)))
    _tick(http, START - timedelta(minutes=120))
    http.routes[nl.game_url(GAME, "landing")] = _landing(away_ids=())
    t = _tick(http, START - timedelta(minutes=90))
    o = _obs()
    assert [x["status"] for x in o] == ["empty", "complete"] and [x["rows_asserted"] for x in o] == [0, 1]
    assert [x["attrs"]["side"] for x in _asr()] == ["home"]
    assert "away missing: empty leaders list" in t.lines()[-1]


def _seed_written(written):
    """The polls in `written` stored as missed rows (the store's own writer), so the plan treats them as written."""
    for gid, lab in sorted(written):
        off = {x: o for x, o, _ in nl.POLLS}[lab]
        ep = {x: e for x, _, e in nl.POLLS}[lab]
        rec.write_observation({"sport": "nhl", "source": nl.SOURCE, "endpoint": nl.game_url(gid, ep),
                               "kickoff_at": START, "poll_label": lab, "status": "missed",
                               "scheduled_at": START - timedelta(minutes=off)})


PREGAME_LABELS = [lab for lab, _, _ in nl.POLLS if lab != "T+20"]


def test_6e_two_in_net_at_t20_is_two_eventual_rows_flagged_and_none_in_net_is_empty():
    _nhl()
    two = _box([_goalie(10, "30:00"), _goalie(11, "29:10")], [_goalie(20, "60:00"), _goalie(21, "00:00")])
    none = _box([_goalie(12, "00:00")], [_goalie(22, "00:00")])
    _seed_written({(g, lab) for g in (GAME, GAME + 1) for lab in PREGAME_LABELS})
    http = FakeHTTP({nl.schedule_url(DAY): _schedule(_game(), _game(GAME + 1, home=MTL, away=UTA)),
                     nl.game_url(GAME, "boxscore"): two, nl.game_url(GAME + 1, "boxscore"): none})
    t = _tick(http, START + timedelta(minutes=20))
    assert [(p.game["id"], p.label) for p in t.due] == [(GAME, "T+20"), (GAME + 1, "T+20")]
    o = _obs()[-2:]
    assert [(x["poll_label"], x["status"], x["rows_asserted"]) for x in o] == [("T+20", "complete", 3),
                                                                              ("T+20", "empty", 0)]
    assert o[0]["endpoint"].endswith(f"{GAME}/boxscore") and o[1]["endpoint"].endswith(f"{GAME + 1}/boxscore")
    a = _asr()
    assert [(x["kind"], x["source_player_id"], x["attrs"]["two_in_net"]) for x in a] == [
        ("eventual_starter", "10", True), ("eventual_starter", "11", True), ("eventual_starter", "20", False)]
    assert a[0]["attrs"]["toi_seconds"] == 1800 and a[0]["player_name"] == "F L10"
    assert "away TWO IN NET" in "\n".join(t.lines())
    assert rec.POST_HOC_KINDS == ("eventual_starter",)               # post hoc, kind-labelled


def test_a_boxscore_the_ingest_refuses_is_failed_with_its_reason_and_its_payload_kept(tmp_path):
    _nhl()
    _seed_written({(GAME, lab) for lab, _, _ in nl.POLLS if lab != "T+20"})
    http = FakeHTTP(_routes(box={"playerByGameStats": {"goalies": []}}))
    _tick(http, START + timedelta(minutes=20))
    o = _obs()[-1]
    assert o["status"] == "failed" and "goalie lists not sided one home + one away" in o["error"]
    assert o["payload_path"] and (tmp_path / o["payload_path"]).is_file()
    assert hashlib.sha256((tmp_path / o["payload_path"]).read_bytes()).hexdigest() == o["payload_sha256"]


# ---- 6(c): failed, missed; late -------------------------------------------------------------------------------------------

def test_6c_a_raised_call_and_a_500_are_failed_rows_with_the_error_redacted():
    _nhl()
    http = FakeHTTP(_routes(landing=ConnectionError("boom ?api_token=SECRETVALUE")))
    _tick(http, START - timedelta(minutes=120))
    http.routes[nl.game_url(GAME, "landing")] = 500
    _tick(http, START - timedelta(minutes=90))
    o = _obs()
    assert [x["status"] for x in o] == ["failed", "failed"] and [x["http_status"] for x in o] == [None, 500]
    assert "ConnectionError" in o[0]["error"] and "SECRETVALUE" not in o[0]["error"]
    assert o[1]["error"].startswith("HTTP 500") and o[0]["payload_path"] is None and _counts()[1] == 0


def test_6c_a_poll_more_than_five_minutes_past_is_missed_with_no_call_and_a_late_answer_is_flagged():
    _nhl()
    http = FakeHTTP(_routes())
    t = _tick(http, START - timedelta(minutes=114))           # T-120 is 6 min past: missed
    assert [(p.label, p.missed) for p in t.due] == [("T-120", True)] and http.n("/landing") == 0
    (o,) = _obs()
    assert o["status"] == "missed" and o["fetched_at"] is None and o["http_status"] is None
    # an answer stamped more than five minutes after its time (a slow call, after the plan): asked, flagged late
    at = START - timedelta(minutes=86)                        # T-90 is 4 min past at the plan
    clock = iter([at + timedelta(seconds=1), at + timedelta(minutes=1, seconds=30)])   # the plan, the stamp
    nl.tick(at, http_get=http, now_fn=lambda: next(clock))
    o = _obs()[-1]
    assert o["poll_label"] == "T-90" and o["status"] == "complete" and o["late"]


def test_the_plan_under_the_lock_reads_the_clock_again_so_a_poll_past_five_minutes_while_waiting_is_missed():
    """Review finding: the tick's `now` was frozen before the lock wait. 4 min past at the tick's start, 9 min past
    once the lock is held: `missed`, no call (252 item 3(b))."""
    _nhl()
    http = FakeHTTP(_routes())
    _seed_written({(GAME, "T-120")})
    at = START - timedelta(minutes=86)
    t = nl.tick(at, http_get=http, now_fn=lambda: at + timedelta(minutes=5, seconds=30))
    o = _obs()[-1]
    assert o["poll_label"] == "T-90" and o["status"] == "missed" and http.n("/landing") == 0
    assert t.planned_at == at + timedelta(minutes=5, seconds=30)


def test_340_3_polls_inside_the_reboot_buffer_are_missed_rows_written_by_the_first_tick_after_it():
    """340 item 3: "a poll scheduled inside the 04:00–05:59Z buffer (a late West-coast start's T-0 or T+20) is written
    as a `missed` row by the first tick after the buffer, never dropped". A 05:00Z start: T-120 and T-90 asked at
    03:00 and 03:30; nothing ticks 04:00-05:59; the 06:00 tick writes the other seven as missed, calling nothing."""
    late = datetime(2026, 11, 13, 5, 0)
    day = nl.nhl_day(late)
    _nhl(start=late)
    http = FakeHTTP(_routes(sched=_schedule(_game(start=late)), day=day))
    for at in (datetime(2026, 11, 13, 3, 0), datetime(2026, 11, 13, 3, 30)):
        _tick(http, at)
    assert [o["poll_label"] for o in _obs()] == ["T-120", "T-90"]
    calls = len(http.calls)
    t = _tick(http, datetime(2026, 11, 13, 6, 0))
    o = _obs()[2:]
    assert [x["poll_label"] for x in o] == ["T-60", "T-45", "T-35", "T-30", "T-15", "T-0", "T+20"]
    assert {x["status"] for x in o} == {"missed"} and len(t.rows) == 7
    assert [u for u in http.calls[calls:] if "/gamecenter/" in u] == []


# ---- the mapping (addendum 341 item 2) ------------------------------------------------------------------------------------

def test_341_two_sides_map_onto_the_hosts_names_and_a_made_up_club_is_refused():
    ids, _ = _nhl(match_pair=None)
    from src.db.database import readonly_scope
    from src.ingestion.nhl_goalies import schedule_games
    games = {g["id"]: g for g in schedule_games(_schedule(_game(1, home=MTL, away=UTA), _game(2, home=FAKE, away=TOR),
                                                          _game(3, home=("St. Louis", "Blues", "STL"),
                                                                away=("New York", "Islanders", "NYI"))))}
    with readonly_scope() as s:
        u = nl.team_universe(s)
    assert nl.resolve_team(u, games[1]["home_names"]) == ids["Montreal Canadiens"]          # accents stripped
    assert nl.resolve_team(u, games[1]["away_names"]) == ids["Utah Mammoth"]
    assert nl.resolve_team(u, games[2]["home_names"]) is None                               # a made-up club
    assert nl.resolve_team(u, games[2]["away_names"]) == ids["Toronto Maple Leafs"]
    assert nl.resolve_team(u, games[3]["home_names"]) == ids["St. Louis Blues"]
    assert nl.resolve_team(u, games[3]["away_names"]) == ids["New York Islanders"]
    got = [nl.resolve_team(u, [n]) for n in HOST_NHL_TEAMS]
    assert None not in got and len(set(got)) == 32 and set(got) == set(ids.values())     # each of the 32, itself


def test_341_an_unmapped_team_stays_null_with_its_text_and_the_observation_is_partial():
    ids, _ = _nhl(match_pair=None)
    http = FakeHTTP(_routes(sched=_schedule(_game(home=FAKE, away=TOR))))
    t = _tick(http, START - timedelta(minutes=120))
    (o,) = _obs()
    assert o["status"] == "partial" and o["match_id"] is None
    a = {x["attrs"]["side"]: x for x in _asr()}
    assert a["home"]["team_id"] is None and a["home"]["source_team"] == "SPI"
    assert a["away"]["team_id"] == ids["Toronto Maple Leafs"]
    assert "team SPI UNMAPPED" in t.lines()[-1] and "match UNMAPPED" in t.lines()[-1]


def test_a_name_held_by_two_teams_is_passed_over_never_chosen():
    """341 item 2: "a side maps only when its candidates resolve to exactly one of the NHL competition's teams"."""
    from src.db.database import readonly_scope, session_scope
    from src.db.schema import Match, MatchStatus, Sport, Team
    _, mid = _nhl()
    with session_scope() as s:
        twin = Team(sport=Sport.NHL, name="Boston Bruins")          # a second team row of one stored name
        s.add(twin)
        s.flush()
        m = s.get(Match, mid)
        s.add(Match(sport=Sport.NHL, competition_id=m.competition_id, season="2026", utc_date=START - timedelta(days=40),
                    status=MatchStatus.FINISHED, home_team_id=twin.id, away_team_id=m.home_team_id))
    with readonly_scope() as s:
        u = nl.team_universe(s)
    assert len(u["boston bruins"]) == 2
    assert nl.resolve_team(u, ["Boston Bruins"]) is None and nl.resolve_team(u, ["Toronto Maple Leafs"]) is not None


def test_the_match_comes_from_the_goalie_link_first_then_match_game_on_a_scheduled_row():
    from src.db.database import readonly_scope, session_scope
    from src.db.schema import Match, MatchStatus, NHLGoalieAppearance, Sport
    from src.ingestion.nhl_goalies import schedule_games
    ids, mid = _nhl()                                           # a SCHEDULED row at START: match_game finds it
    g = schedule_games(_schedule())[0]
    with readonly_scope() as s:
        assert nl.resolve_match(s, g) == mid
    with session_scope() as s:
        m = Match(sport=Sport.NHL, competition_id=s.get(Match, mid).competition_id, season="2026",
                  utc_date=START + timedelta(days=30), status=MatchStatus.SCHEDULED,
                  home_team_id=ids["Seattle Kraken"], away_team_id=ids["Dallas Stars"])
        s.add(m)
        s.flush()
        other = m.id
        s.add(NHLGoalieAppearance(nhl_game_id=GAME, match_id=other, game_start=START, side="home", goalie_id=99))
    with readonly_scope() as s:
        assert nl.resolve_match(s, g) == other                   # the link nhl_goalies holds wins


def test_match_game_reads_no_cancelled_row_and_the_poll_then_is_partial():
    _nhl(status="CANCELLED")
    _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    (o,) = _obs()
    assert o["match_id"] is None and o["status"] == "partial"


# ---- #835 item 2 (258 item 2(2)): the poll key ----------------------------------------------------------------------------

def _poll(match_id=None, kickoff=None):
    return {"sport": "nhl", "source": nl.SOURCE, "endpoint": nl.game_url(GAME, "landing"), "match_id": match_id,
            "kickoff_at": kickoff, "poll_label": "T-35", "scheduled_at": START - timedelta(minutes=35),
            "fetched_at": START - timedelta(minutes=35), "status": "empty"}


def test_835_2_an_unmapped_poll_written_twice_is_one_row_and_one_already_and_a_later_mapped_write_is_already():
    """258 item 2(2), verbatim: "the test: an unmapped poll written twice gives one observation and one "already", and
    a later mapped write of the same poll is "already" too". FAIL-FIRST on main 1e018f7b (the second write was a second row, no "already")."""
    first = rec.write_observation(_poll())
    again = rec.write_observation(_poll())
    mapped = rec.write_observation(_poll(match_id=7, kickoff=START))
    assert first.written and not first.already and again.already and mapped.already
    assert _counts() == (1, 0) and "already observed" in again.line()
    with pytest.raises(Exception, match="this poll is already observed"):              # a raw INSERT, around the writer
        with _engine().begin() as c:
            c.execute(text(f"INSERT INTO {rec.OBS_TABLE} (sport, source, endpoint, poll_label, scheduled_at, fetched_at,"
                           " status, late, rows_asserted, created_at) VALUES ('NHL', :s, :e, 'T-35', :t, :t, "
                           "'empty', 0, 0, :t)"), {"s": nl.SOURCE, "e": nl.game_url(GAME, "landing"),
                                                   "t": _dt(START - timedelta(minutes=35))})
    assert _counts() == (1, 0)
    other = rec.write_observation({**_poll(), "scheduled_at": START - timedelta(minutes=30), "poll_label": "T-30"})
    assert other.written                                         # another poll of the game is its own row


def test_835_2_the_poll_key_is_an_index_and_a_guard_and_a_store_migrated_before_gains_both(tmp_path, monkeypatch,
                                                                                          capsys):
    """The migration's first run on a store migrated before #835 item 2 creates the index and the guard and says so;
    the second keeps them (the PR body quotes both receipts for the deploy block's --expect)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.schema import CreateIndex, CreateTable

    import src.db.database as db
    from src.db.schema import AVAILABILITY_TRIGGERS, AvailabilityAssertion, AvailabilityObservation, Base
    eng = create_engine(f"sqlite:///{tmp_path / 'm841.db'}", future=True)
    Base.metadata.create_all(eng, tables=[t for t in Base.metadata.sorted_tables if t.name not in rec.TABLES])
    with eng.begin() as c:                                        # #841's store: the tables, 7 triggers, 10 indexes
        for m in (AvailabilityObservation, AvailabilityAssertion):
            c.execute(CreateTable(m.__table__))
            for ix in m.__table__.indexes:
                if ix.name != nl.POLL_KEY_INDEX:
                    c.execute(CreateIndex(ix))
        for name, _t, sql in AVAILABILITY_TRIGGERS:
            if name != nl.POLL_GUARD:
                c.execute(text(sql))
        c.execute(text(f"CREATE TABLE {rec.MIGRATION_MARKER} (id INTEGER PRIMARY KEY CHECK (id = 1), script "
                       "VARCHAR(64) NOT NULL, migrated_at DATETIME NOT NULL)"))
        c.execute(text(f"INSERT INTO {rec.MIGRATION_MARKER} VALUES (1, 'migrate_availability_record.py', "
                       "'2026-11-05 14:00:00')"))
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    from src.db.database import readonly_scope
    with readonly_scope() as s:
        assert rec.migrated(s) and not nl.poll_key_migrated(s)
    http = FakeHTTP(_routes())
    with pytest.raises(nl.Refused, match="since #835 item 2's poll key"):
        nl.tick(START, http_get=http, now_fn=lambda: START)
    assert http.calls == [] and not (tmp_path / "logs").exists()        # refused before any call, kept file or notice
    assert mig.main() == 0
    out1 = capsys.readouterr().out
    assert f"+ Created trigger {nl.POLL_GUARD}" in out1 and out1.count("+ Created trigger") == 1
    assert f"+ Created index {nl.POLL_KEY_INDEX}" in out1 and out1.count("+ Created index") == 1
    assert "· Kept migration marker availability_record_migration (migrated_at 2026-11-05 14:00:00)" in out1
    assert mig.main() == 0
    out2 = capsys.readouterr().out
    assert f"· Kept trigger {nl.POLL_GUARD}" in out2 and f"· Kept index {nl.POLL_KEY_INDEX}" in out2
    assert "+ Created" not in out2 and "indexes on the record (11 of 11 declared)" in out2
    with readonly_scope() as s:
        assert nl.poll_key_migrated(s)
    eng.dispose()


# ---- 6(a): append-only; the replay asserts nothing again -------------------------------------------------------------------

def test_6a_counts_only_grow_across_a_replay_and_the_feed_has_no_update_or_delete_path():
    _nhl()
    http = FakeHTTP(_routes())
    seen = [_counts()]
    for minutes in (120, 120, 90, 90, 60):
        _tick(http, START - timedelta(minutes=minutes))
        seen.append(_counts())
    assert seen == [(0, 0), (1, 2), (1, 2), (2, 4), (2, 4), (3, 6)]
    assert http.n("/landing") == 3
    src = (REPO / "src" / "availability" / "nhl_landing.py").read_text()
    public = [n for n in dir(nl) if not n.startswith("_")]
    assert not [n for n in public if re.search(r"update|delete|upsert|replace|merge|correct|amend", n, re.I)]
    for pat in (r"\bOR\s+REPLACE\b", r"on_conflict", r"\.delete\(", r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\s+FROM\b",
                r"session_scope", r"\bs\.add\("):
        assert not re.search(pat, src), pat                      # record.write_observation is its only writer


def test_a_tick_with_no_poll_due_takes_no_lock_and_calls_no_game_page(monkeypatch):
    _nhl()
    http = FakeHTTP(_routes())
    monkeypatch.setattr(nl, "_db_lock", lambda: (_ for _ in ()).throw(AssertionError("the lock was taken")))
    t = _tick(http, START - timedelta(minutes=121))              # one minute before T-120: outside the window
    assert t.games == 0 and not t.due and _counts() == (0, 0)
    assert http.calls == [nl.schedule_url(DAY)]
    _seed_written({(GAME, "T-120")})
    t = _tick(http, START - timedelta(minutes=100))              # T-120 written, T-90 not yet due
    assert t.games == 1 and not t.due and t.remaining == 8 and _counts() == (1, 0)
    assert http.calls == [nl.schedule_url(DAY)]                  # the kept schedule: no second read within the hour


# ---- the schedule (340 item 4) --------------------------------------------------------------------------------------------

def test_340_4_the_schedule_is_read_at_most_hourly_kept_per_day_and_writes_no_row(tmp_path):
    _nhl()
    http = FakeHTTP(_routes())
    at = START - timedelta(minutes=200)
    _tick(http, at)
    _tick(http, at + timedelta(minutes=10))
    assert http.n("/schedule/") == 1 and _counts() == (0, 0)                  # support data: no row
    kept = sorted((tmp_path / "logs/availability/nhl_api_landing" / DAY.isoformat()).glob("*-schedule.json"))
    assert len(kept) == 1 and json.loads(kept[0].read_bytes()) == _schedule()
    t = _tick(http, at + timedelta(minutes=61))
    assert http.n("/schedule/") == 2 and t.schedules[0].read == "read (unchanged)"
    assert len(sorted(kept[0].parent.glob("*-schedule.json"))) == 1                # identical bytes: not kept again
    http.routes[nl.schedule_url(DAY)] = _schedule(_game(start=START + timedelta(minutes=30)))
    t = _tick(http, at + timedelta(minutes=122))
    assert t.schedules[0].read == "read (new)" and len(sorted(kept[0].parent.glob("*-schedule.json"))) == 2


def test_340_4_a_failed_schedule_read_invents_nothing_and_notices_once_per_day():
    _nhl()
    http = FakeHTTP({nl.schedule_url(DAY): ConnectionError("down")})
    t1 = _tick(http, START + timedelta(minutes=30))              # every pregame poll would be past: none is known
    t2 = _tick(http, START + timedelta(minutes=35))
    assert t1.exit_code == 1 and t2.exit_code == 0 and t1.schedules[0].notice and not t2.schedules[0].notice
    assert _counts() == (0, 0) and t1.games == 0                # no missed rows for games it could not know
    assert "ERROR (redacted): ConnectionError: down" in t1.lines()[1]
    assert "last read FAILED at" in t2.lines()[1] and http.n("/schedule/") == 1     # at most hourly: not re-read
    t3 = _tick(http, START + timedelta(minutes=95))              # over the hour: read again (fails again, no notice)
    assert http.n("/schedule/") == 2 and t3.exit_code == 0 and t3.schedules[0].read == "failed"


def test_340_4_a_failed_read_uses_the_games_it_already_knew():
    _nhl()
    http = FakeHTTP(_routes())
    _tick(http, START - timedelta(minutes=120))
    http.routes[nl.schedule_url(DAY)] = 503
    t = _tick(http, START - timedelta(minutes=50))               # over an hour later: read again, fails
    assert t.schedules[0].read == "failed" and t.games == 1 and t.exit_code == 1
    assert [o["poll_label"] for o in _obs()] == ["T-120", "T-90", "T-60"]
    assert [o["status"] for o in _obs()] == ["complete", "missed", "missed"]


def test_340_4_a_moved_start_recomputes_the_polls_not_yet_written_and_never_touches_a_written_one():
    _nhl()
    http = FakeHTTP(_routes())
    _tick(http, START - timedelta(minutes=120))                  # T-120 written against START
    moved = START + timedelta(minutes=30)
    http.routes[nl.schedule_url(DAY)] = _schedule(_game(start=moved))
    t = _tick(http, START - timedelta(minutes=59))               # over an hour: the moved start is read
    assert [p.label for p in t.due] == ["T-90"]                  # moved T-90 = START-60; T-120 stays written
    o = _obs()
    assert [(x["poll_label"], x["kickoff_at"], x["scheduled_at"]) for x in o] == [
        ("T-120", _dt(START), _dt(START - timedelta(minutes=120))),
        ("T-90", _dt(moved), _dt(moved - timedelta(minutes=90)))]


# ---- the payload; dry run; the command -------------------------------------------------------------------------------------

def test_a_200_is_kept_under_logs_availability_by_its_sha_and_never_under_data(tmp_path):
    _nhl()
    _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    (o,) = _obs()
    p = tmp_path / o["payload_path"]
    assert o["payload_path"].startswith(f"logs/availability/nhl_api_landing/{(START - timedelta(hours=2)).date()}/")
    assert p.name.endswith(f"-{o['payload_sha256'][:16]}-{GAME}_landing_T-120.json")
    assert hashlib.sha256(p.read_bytes()).hexdigest() == o["payload_sha256"]
    assert rec.endpoint_refusal(o["endpoint"]) is None


def test_the_dry_run_calls_no_game_page_writes_and_keeps_nothing(tmp_path):
    _nhl()
    http = FakeHTTP(_routes())
    t = _tick(http, START - timedelta(minutes=86), dry_run=True)
    assert [(p.label, p.missed) for p in t.due] == [("T-120", True), ("T-90", False)]
    assert _counts() == (0, 0) and http.calls == [nl.schedule_url(DAY)]
    assert not (tmp_path / "logs").exists()
    assert "would be MISSED (no call)" in "\n".join(t.lines()) and "DRY RUN" in t.lines()[0]


def test_the_command_one_tick_its_receipt_and_its_refusals(monkeypatch, tmp_path):
    from cli import cli
    _nhl()
    http = FakeHTTP(_routes())
    import requests
    monkeypatch.setattr(requests, "get", http)
    monkeypatch.setattr(nl, "_now", lambda: START - timedelta(minutes=120))
    res = CliRunner().invoke(cli, ["availability-nhl-observe"])
    assert res.exit_code == 0, res.output
    assert res.output.startswith("AVAILABILITY-NHL-OBSERVE · 2026-11-12T22:00:00Z · games in the window 1 · polls due 1")
    assert f"game {GAME} T-120" in res.output and "COMPLETE" in res.output
    import src.db.database as db
    monkeypatch.setattr(db.SessionLocal, "kw", {**db.SessionLocal.kw})
    from sqlalchemy import create_engine
    monkeypatch.setitem(db.SessionLocal.kw, "bind", create_engine(f"sqlite:///{tmp_path / 'nope' / 'x.db'}"))
    res = CliRunner().invoke(cli, ["availability-nhl-observe"])
    assert res.exit_code == 2 and "the record never creates one" in res.output
    assert not (tmp_path / "nope").exists()


# ---- the review's findings (the adversarial pass before the PR) ------------------------------------------------------------

def test_a_start_moved_earlier_never_re_asks_a_written_endpoint_and_time():
    """#835 item 2's key "the scheduled poll time is the poll": START moved 30 min earlier lands the recomputed T-90 on
    the written T-120's (endpoint, scheduled_at); it is written already, never due, never an "already" every tick."""
    _nhl()
    http = FakeHTTP(_routes())
    _tick(http, START - timedelta(minutes=120))                  # T-120 at START-120
    http.routes[nl.schedule_url(DAY)] = _schedule(_game(start=START - timedelta(minutes=30)))
    t = _tick(http, START - timedelta(minutes=59))               # over an hour: the earlier start read
    assert ("T-90" not in [p.label for p in t.due]) and t.already == 0
    assert [o["poll_label"] for o in _obs()][0] == "T-120" and _obs()[0]["scheduled_at"] == _dt(START - timedelta(
        minutes=120))


def test_one_match_two_game_ids_maps_neither():
    """Law 4: two gameIds that resolve to one match (here: the same pair at the same start) keep match_id NULL with
    their own source_match_id; neither poll is swallowed by Step B's key as "already"."""
    _nhl()
    http = FakeHTTP({**_routes(), nl.schedule_url(DAY): _schedule(_game(), _game(GAME + 7)),
                     nl.game_url(GAME + 7, "landing"): _landing((30,), (40,))})
    t = _tick(http, START - timedelta(minutes=120))
    o = _obs()
    assert len(o) == 2 and t.already == 0 and {x["match_id"] for x in o} == {None}
    assert {x["status"] for x in o} == {"partial"}


def test_a_match_already_claimed_by_another_game_in_the_record_is_refused():
    _, mid = _nhl()
    rec.write_observation({"sport": "nhl", "source": nl.SOURCE, "endpoint": nl.game_url(GAME + 9, "landing"),
                           "match_id": mid, "kickoff_at": START, "poll_label": "T-120", "status": "missed",
                           "scheduled_at": START - timedelta(minutes=120)})
    _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    assert _obs()[-1]["match_id"] is None and _obs()[-1]["status"] == "partial"


def test_a_side_whose_candidates_name_two_teams_is_unmapped_union_not_first_hit():
    """341 item 2: "a side maps only when its candidates resolve to exactly one": a Utah side's candidates (Utah
    Mammoth, Utah Hockey Club by NAME_ALIASES) naming two stored rows maps to neither."""
    from src.db.database import readonly_scope, session_scope
    from src.db.schema import Match, MatchStatus, Sport, Team
    from src.ingestion.nhl_goalies import schedule_games
    ids, mid = _nhl()
    with session_scope() as s:
        old = Team(sport=Sport.NHL, name="Utah Hockey Club")
        s.add(old)
        s.flush()
        m = s.get(Match, mid)
        s.add(Match(sport=Sport.NHL, competition_id=m.competition_id, season="2024", utc_date=datetime(2025, 1, 5),
                    status=MatchStatus.FINISHED, home_team_id=old.id, away_team_id=m.home_team_id))
    g = schedule_games(_schedule(_game(home=UTA)))[0]
    with readonly_scope() as s:
        u = nl.team_universe(s)
    assert nl.resolve_team(u, ["Utah Mammoth"]) == ids["Utah Mammoth"]        # one name alone: one team
    assert nl.resolve_team(u, g["home_names"]) is None                           # the side's candidates: two teams


def test_source_team_is_the_schedules_own_text_verbatim_and_a_side_with_none_asserts_nothing():
    _nhl(match_pair=None)
    (g,) = nl.day_games(_schedule(_game(home=MTL)), DAY)
    assert g["home_text"] == "MTL" and g["away_text"] == "BOS"
    raw = _game(home=MTL)
    del raw["homeTeam"]["abbrev"]
    (g,) = nl.day_games(_schedule(raw), DAY)
    assert g["home_text"] == "Montréal Canadiens"                # verbatim: the accent kept
    raw["homeTeam"] = {"id": 5}                                  # a side the schedule names no team for
    (g,) = nl.day_games(_schedule(raw), DAY)
    r = nl.read_landing(_landing(), g, {"home": None, "away": None}, None)
    assert [a["attrs"]["side"] for a in r.assertions] == ["away"] and "names no team" in r.missing["home"]


def test_a_boxscore_whose_toi_is_unread_is_empty_with_the_note_never_a_clean_none_in_net():
    _nhl()
    _seed_written({(GAME, lab) for lab in PREGAME_LABELS})
    box = _box([{"playerId": 10, "toi": "n/a"}], [_goalie(20, "00:00")])
    _tick(FakeHTTP(_routes(box=box)), START + timedelta(minutes=20))
    o = _obs()[-1]
    assert o["status"] == "empty" and "could not read" in o["error"] and o["rows_asserted"] == 0


def test_a_payload_is_dropped_when_the_write_raises_anything(monkeypatch, tmp_path):
    _nhl()
    monkeypatch.setattr(rec, "write_observation", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    assert not list((tmp_path / "logs").rglob("*_landing_*.json"))


def test_a_due_tick_takes_the_db_lock_and_plans_again_under_it(monkeypatch):
    import contextlib
    _nhl()
    taken = []

    @contextlib.contextmanager
    def lock():
        taken.append(len(_obs()))
        yield
    monkeypatch.setattr(nl, "_db_lock", lock)
    _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    assert taken == [0] and len(_obs()) == 1


def test_a_store_refusal_after_the_keep_is_a_failed_row_keeping_the_payload(monkeypatch, tmp_path):
    _nhl()
    real = rec.write_observation
    calls = []

    def refuse_first(obs, assertions=()):
        calls.append(obs["status"])
        if len(calls) == 1:
            raise rec.Refused("REFUSED: the store refused the write (a synthetic refusal); nothing written")
        return real(obs, assertions)
    monkeypatch.setattr(rec, "write_observation", refuse_first)
    _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    (o,) = _obs()
    assert calls == ["complete", "failed"] and o["status"] == "failed" and "synthetic refusal" in o["error"]
    assert o["payload_path"] and (tmp_path / o["payload_path"]).is_file() and _counts() == (1, 0)


def test_already_drops_the_payload_this_run_created(monkeypatch, tmp_path):
    _nhl()
    monkeypatch.setattr(rec, "write_observation",
                        lambda obs, assertions=(): rec.Receipt(source=nl.SOURCE, status=obs["status"], already=True))
    t = _tick(FakeHTTP(_routes()), START - timedelta(minutes=120))
    assert t.already == 1 and not list((tmp_path / "logs").rglob("*_landing_*.json"))
    assert "already observed 1" in t.lines()[0]


def test_the_command_exits_1_on_the_days_first_failed_schedule_read_then_0(monkeypatch):
    from cli import cli
    _nhl()
    import requests
    monkeypatch.setattr(requests, "get", FakeHTTP({nl.schedule_url(DAY): 503}))
    monkeypatch.setattr(nl, "_now", lambda: START - timedelta(minutes=120))
    first = CliRunner().invoke(cli, ["availability-nhl-observe"])
    assert first.exit_code == 1 and "NOTICE: the NHL day's first failed schedule read" in first.output
    monkeypatch.setattr(nl, "_now", lambda: START - timedelta(minutes=115))
    second = CliRunner().invoke(cli, ["availability-nhl-observe"])
    assert second.exit_code == 0 and "last read FAILED at" in second.output


# ---- addendum 343 item 1: the series' scope (six hours) -------------------------------------------------------------------

def test_343_1_a_90_minute_slip_schedules_no_second_series_and_moves_only_the_polls_not_yet_written():
    """343 item 1, verbatim in part: "A slip inside six hours (a delayed puck drop) schedules no second series: the
    polls not yet written move with the start, the written ones stand"."""
    _nhl()
    http = FakeHTTP(_routes())
    _tick(http, START - timedelta(minutes=120))                  # T-120 against START
    slipped = START + timedelta(minutes=90)
    http.routes[nl.schedule_url(DAY)] = _schedule(_game(start=slipped))
    t = _tick(http, START - timedelta(minutes=30))               # over the hour: the slip is read; T-120 recomputed
    assert "T-120" not in [p.label for p in t.due]               # ... at START-30 is written already (within 6 h)
    assert [p.label for p in t.due] == []                        # T-90 of the slipped start is START+0: not yet due
    t = _tick(http, START)                                       # the slipped T-90
    assert [p.label for p in t.due] == ["T-90"]
    o = _obs()
    assert [(x["poll_label"], x["kickoff_at"]) for x in o] == [("T-120", _dt(START)), ("T-90", _dt(slipped))]


def test_343_1_a_next_day_move_gets_a_fresh_series_beside_the_old_rows():
    """343 item 1: "a start that moves by six hours or more (a postponement) gets a fresh set of polls against the new
    start, new rows beside the old, nothing touched (append-only holds)"."""
    _nhl()
    http = FakeHTTP(_routes())
    _tick(http, START - timedelta(minutes=120))                  # T-120 against START, on NHL day DAY
    before = _obs()
    moved = START + timedelta(days=1)
    http.routes[nl.schedule_url(DAY)] = _schedule(_game(GAME + 50, start=START + timedelta(hours=1), home=MTL,
                                                        away=UTA))
    http.routes[nl.schedule_url(DAY + timedelta(days=1))] = _schedule(_game(start=moved))
    t = _tick(http, moved - timedelta(minutes=120))
    assert [(p.game["id"], p.label) for p in t.due] == [(GAME, "T-120")]
    o = _obs()
    assert o[:1] == before                                       # the old row stands, untouched
    assert [(x["poll_label"], x["kickoff_at"], x["scheduled_at"]) for x in o] == [
        ("T-120", _dt(START), _dt(START - timedelta(minutes=120))),
        ("T-120", _dt(moved), _dt(moved - timedelta(minutes=120)))]


def test_343_1_the_scope_is_six_hours_declared():
    assert nl.SERIES_SCOPE == timedelta(hours=6)
    g = {"id": GAME, "start": START}
    w = nl.Written(labels={(GAME, "T-0"): [START - timedelta(hours=5, minutes=59)]})
    assert w.has(g, "T-0", "landing", START)                                      # inside six hours: written
    w = nl.Written(labels={(GAME, "T-0"): [START - timedelta(hours=6)]})
    assert not w.has(g, "T-0", "landing", START)                                  # six hours or more: a fresh series
