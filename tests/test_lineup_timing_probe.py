"""LINEUP TIMING PROBE (ARCHITECT 2026-10-15, addendum 71 item 2, Step A; #106): read-only, on a throwaway SQLite file
built from the app's own schema (never the configured DB, never data/), the real APIFootballAdapter with its HTTP session
stubbed (no network), and a fake wall clock (no test waits)."""
import dataclasses
import hashlib
import importlib.util
import sqlite3
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.adapters import api_football
from src.adapters.api_football import APIFootballAdapter
from src.db.schema import Base, Competition, Match, MatchStatus, Sport, Team

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lineup_timing_probe", ROOT / "scripts" / "lineup_timing_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

SRC = APIFootballAdapter.source_name
DAY = "2026-10-20"
EARLY, LATE = datetime(2026, 10, 20, 16, 45), datetime(2026, 10, 20, 19, 0)


def at(h, m, s=0):
    return datetime(2026, 10, 20, h, m, s)


def build(path: Path):
    """CL on the day, in id order: 1 = 1001 at 16:45 (home 50 v away 60); 2 = 1005 at 16:45 (55 v 65); 3 = 1002 at 19:00
    (home 70, merged from 77, v away 80); 4 = a 19:00 row with no fixture id; 7 = 1006 at 19:00, STALE_ORPHAN. Not on
    the day or not CL: 5 = a CL row the next day, 6 = a PL row on the day."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        cl = Competition(sport=Sport.SOCCER, code="CL", name="UEFA Champions League", area="Europe", type="CUP")
        pl = Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England", type="LEAGUE")
        t = {n: Team(sport=Sport.SOCCER, name=f"Club {n}", external_ids=ext) for n, ext in [
            ("50", {SRC: "50"}), ("60", {SRC: "60"}), ("55", {SRC: "55"}), ("65", {SRC: "65"}),
            ("70", {SRC: "70", f"{SRC}_also": ["77"]}), ("80", {SRC: "80"}), ("90", {})]}
        s.add_all([cl, pl, *t.values()])
        s.flush()

        def m(comp, when, home, away, fid, status=MatchStatus.SCHEDULED):
            s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=when, status=status,
                        home_team_id=t[home].id, away_team_id=t[away].id, external_ids={SRC: fid} if fid else {}))
            s.flush()
        m(cl, EARLY, "50", "60", "1001")
        m(cl, EARLY, "55", "65", "1005")
        m(cl, LATE, "70", "80", "1002")
        m(cl, LATE, "90", "50", None)
        m(cl, LATE + timedelta(days=1), "60", "70", "1003")
        m(pl, LATE, "80", "90", "1004")
        m(cl, LATE, "65", "55", "1006", MatchStatus.STALE_ORPHAN)
        s.commit()
    eng.dispose()


def lineup(*teams, starters=11, bench=9, placeholder=None):
    """An answer of /fixtures/lineups: one block per team id; `placeholder` names a team whose last starter has no name."""
    out = []
    for tid in teams:
        xi = [{"player": {"id": int(tid) * 100 + k, "name": f"P{tid}-{k}", "number": k, "pos": "M", "grid": "1:1"}}
              for k in range(starters)]
        if placeholder == tid:
            xi[-1]["player"]["name"] = None
        subs = [{"player": {"id": int(tid) * 1000 + k, "name": f"S{tid}-{k}", "number": 30 + k, "pos": "D",
                            "grid": None}} for k in range(bench)]
        out.append({"team": {"id": int(tid), "name": f"Club {tid}", "logo": "x", "colors": None},
                    "formation": "4-3-3", "startXI": xi, "substitutes": subs, "coach": {"id": 1, "name": "C"}})
    return {"get": "fixtures/lineups", "parameters": {}, "errors": [], "results": len(out), "paging": {},
            "response": out}


EMPTY = {"get": "fixtures/lineups", "parameters": {}, "errors": [], "results": 0, "paging": {}, "response": []}
LIMIT = {**EMPTY, "errors": {"requests": "limit"}}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error for url: fixtures/lineups")


class Clock:
    def __init__(self, when: datetime):
        self.now = when.replace(tzinfo=timezone.utc)
        self.naps = []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.naps.append(s)
        self.now += timedelta(seconds=s)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The DB, and providers built on the real adapter whose session answers from per-fixture scripts: {fid: [answer,
    ...]} (a dict is a 200; (status, body); an exception instance is raised), the last answer repeated once the script
    runs out. No real request can leave a test: requests.Session.get fails it."""
    monkeypatch.setattr(api_football, "_RATE_LIMIT_SECONDS", 0.0)
    monkeypatch.setattr(api_football, "time", types.SimpleNamespace(sleep=lambda s: None, monotonic=lambda: 0.0))

    def no_network(*a, **kw):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr(requests.Session, "get", no_network)
    db = tmp_path / "db" / "sports.db"
    db.parent.mkdir()
    build(db)
    scripts, asked = {}, []

    class Sess:
        headers = {}

        def get(self, url, params=None, timeout=None):
            fid = str(params["fixture"])
            asked.append(fid)
            seq = scripts.setdefault(fid, [EMPTY])
            ans = seq.pop(0) if len(seq) > 1 else seq[0]
            if isinstance(ans, BaseException):
                raise ans
            return Resp(*ans) if isinstance(ans, tuple) else Resp(200, ans)

    def make(when):
        clock = Clock(when)
        adapter = APIFootballAdapter(api_key="test-dummy")
        adapter._session = Sess()
        return clock, probe.Provider(adapter, clock)
    return types.SimpleNamespace(db=db, scripts=scripts, asked=asked, make=make)


def go(world, when, capsys, *extra, sleep=None):
    clock, prov = world.make(when)
    rc = probe.run(["--db", str(world.db), "--date", DAY, *extra], clock=clock, sleep=sleep or clock.sleep,
                   provider=prov)
    return rc, capsys.readouterr().out, clock, prov


def summary(out):
    return out.split("\nSUMMARY\n", 1)[1].splitlines()


def line_of(out, fid):
    return next(ln for ln in summary(out) if f"· fixture {fid}:" in ln)


def test_each_fixture_prints_its_first_poll_with_eleven_per_side_the_keys_and_the_calls(world, capsys):
    world.scripts["1001"] = [EMPTY, EMPTY, EMPTY, lineup("50", "60")]                        # T-120..T-75 empty
    world.scripts["1002"] = [EMPTY, EMPTY, EMPTY, lineup("70", "80", placeholder="80"), lineup("77", "80")]
    rc, out, clock, prov = go(world, at(14, 30), capsys)
    assert rc == 0, out
    assert "opened via mode=ro URI" in out
    assert "  5 CL row(s) stored with a kickoff on 2026-10-20" in out
    assert "fixture 1003" not in out and "fixture 1004" not in out
    assert "· NOT POLLED: no api_football fixture id" in out
    assert "stored status STALE_ORPHAN · fixture 1006 · NOT POLLED: stored status STALE_ORPHAN: not a game" in out
    assert sorted(set(world.asked)) == ["1001", "1002", "1005"] and len(world.asked) == 21
    assert line_of(out, "1001").startswith("  match 1 · Club 50 v Club 60 · kickoff 2026-10-20 16:45Z · stored status "
                                           "SCHEDULED · fixture 1001: first eleven per side at T-60 (asked at T-60.0), "
                                           "the poll before answered without them at T-75 · polls answered 7, "
                                           "failed 0, missed 0")
    assert "first eleven per side at T-45 (asked at T-45.0), the poll before answered without them at T-60" \
        in line_of(out, "1002")
    assert "no poll of the 7 answered came back with eleven per side" in line_of(out, "1005")
    assert "  fixtures by the first poll with eleven per side: T-60 1 · T-45 1 · none 1 · not polled 2 (of 5)" \
        in summary(out)
    assert "  calls: list_lineup_confirmed 21 · HTTP requests 21 (by status {200: 21}) · failed 0" in summary(out)
    # the placeholder poll: 10 starters for the away side, not eleven per side; the merged id 77 is the home side
    assert any("T-60 (asked at T-60.0) · match 3: home (team 70) 11 starters + 9 bench · away (team 80) 10 starters "
               "+ 9 bench" in ln and "ELEVEN" not in ln for ln in out.splitlines())
    assert any("T-45 (asked at T-45.0) · match 3: home (team 77) 11 starters + 9 bench · away (team 80) 11 starters "
               "+ 9 bench · ELEVEN PER SIDE" in ln for ln in out.splitlines())
    s = summary(out)
    assert "      keys sent, response[]: coach, formation, startXI, substitutes, team" in s
    assert "      keys sent, response[].startXI[].player: grid, id, name, number, pos" in s
    assert "      keys sent, answer: errors, get, paging, parameters, response, results" in s
    assert probe.ADAPTER_KEYS in out


def test_polls_run_in_time_order_with_fixtures_sharing_a_kickoff_interleaved(world, capsys):
    rc, out, clock, _ = go(world, at(14, 30), capsys)
    assert world.asked == ["1001", "1005"] * 7 + ["1002"] * 7       # each 16:45 poll time: 1001 then 1005 (id order)
    assert "MISSED" not in out
    assert max(clock.naps) <= probe.NAP
    made = [ln for ln in out.splitlines() if " (asked at " in ln]
    assert [ln.split("Z T-")[1].split(" ")[0] for ln in made[:4]] == ["120", "120", "90", "90"]


def test_a_late_start_misses_the_past_polls_and_counts_the_first_eleven_apart(world, capsys):
    world.scripts["1002"] = [lineup("70", "80")]
    rc, out, _, prov = go(world, at(18, 3), capsys)
    assert "no poll made" in line_of(out, "1001") and "missed 7" in line_of(out, "1001")
    # T-120 17:00 .. T-75 17:45 missed; T-60 (18:00) is 3 minutes past, within the limit: asked at T-57.0
    assert line_of(out, "1002").endswith("first eleven per side at T-60 (asked at T-57.0) · T-120, T-90, T-75 not "
                                         "answered between: it may have been readable earlier · polls answered 4, "
                                         "failed 0, missed 3")
    assert "17:45Z T-75 · match 3: MISSED (its time passed 18.0 min before its turn)" in out
    assert "T-60, earlier polls not answered 1 · no poll made 2 · not polled 2 (of 5)" in out
    assert prov.calls == 4


@pytest.mark.parametrize("late, missed", [(5, False), (6, True)])
def test_the_late_limit_is_five_minutes(world, capsys, late, missed):
    assert probe.LATE_LIMIT == timedelta(minutes=5)
    _, out, _, _ = go(world, at(18, late), capsys)
    assert ("18:00Z T-60 · match 3: MISSED" in out) is missed
    assert (f"T-60 (asked at T-{60 - late}.0) · match 3:" in out) is not missed


def test_a_laptop_that_sleeps_mid_run_misses_its_polls_and_keeps_its_labels(world, capsys):
    world.scripts["1002"] = [lineup("70", "80")]
    clock, prov = world.make(at(16, 50))                       # 1001 and 1005 are past: only 1002 is polled

    def sleep(s):
        if clock.now == datetime(2026, 10, 20, 17, 0, 30, tzinfo=timezone.utc):
            s = 40 * 60                                        # the lid closes after T-120's answer, for 40 minutes
        clock.sleep(s)
    probe.run(["--db", str(world.db), "--date", DAY], clock=clock, sleep=sleep, provider=prov)
    out = capsys.readouterr().out
    assert "17:30Z T-90 · match 3: MISSED (its time passed" in out
    ln = line_of(out, "1002")
    assert "first eleven per side at T-120 (asked at T-120.0), the first poll · polls answered 6, failed 0, missed 1" \
        in ln and "not answered between" not in ln


def test_a_failed_call_is_printed_counted_and_named_before_the_first_eleven(world, capsys):
    world.scripts["1001"] = [(429, EMPTY), EMPTY, (500, EMPTY), LIMIT, lineup("50", "60")]
    rc, out, _, prov = go(world, at(14, 30), capsys)
    assert rc == 0
    assert "✗ HTTPError: 500 Error for url: fixtures/lineups" in out
    assert "✗ RuntimeError: API-Football error: {'requests': 'limit'}" in out
    # T-120: the 429 is asked again and the second answer is empty; T-90 and T-75 fail; T-60 holds the elevens
    assert line_of(out, "1001").endswith("first eleven per side at T-60 (asked at T-60.0), the poll before answered "
                                         "without them at T-120 · T-90, T-75 not answered between: it may have been "
                                         "readable earlier · polls answered 5, failed 2, missed 0")
    assert "T-60, earlier polls not answered 1 · none 2 · not polled 2 (of 5)" in out
    assert "  calls: list_lineup_confirmed 21 · HTTP requests 22 (by status {200: 20, 429: 1, 500: 1}) · failed 2" \
        in summary(out)


def test_a_poll_that_rules_out_an_earlier_missed_one_leaves_no_caveat(world, capsys):
    world.scripts["1001"] = [EMPTY, lineup("50", "60")]            # T-120 (14:45) missed; T-90 empty; T-75 elevens
    _, out, _, _ = go(world, at(14, 55), capsys)
    ln = line_of(out, "1001")
    assert ("first eleven per side at T-75 (asked at T-75.0), the poll before answered without them at T-90 · polls "
            "answered 6, failed 0, missed 1") in ln and "not answered between" not in ln
    assert "T-75 1 ·" in out


def test_a_fixture_whose_every_call_failed_is_no_answer_not_none(world, capsys):
    world.scripts["1005"] = [(500, EMPTY)]
    _, out, _, _ = go(world, at(14, 30), capsys)
    assert "no poll answered · polls answered 0, failed 7, missed 0" in line_of(out, "1005")
    assert "no answer 1" in out


def test_a_request_with_no_answer_is_counted(world, capsys):
    world.scripts["1005"] = [requests.ConnectionError("wifi gone"), EMPTY]
    _, out, _, prov = go(world, at(14, 30), capsys)
    assert "match 2: ✗ ConnectionError: wifi gone" in out
    assert "HTTP requests 21 (by status {200: 20, 'no answer': 1}) · failed 1" in out


def test_a_poll_is_stamped_when_its_counted_answer_was_asked_for(world, capsys, monkeypatch):
    """The adapter's 429 sleep (60 s) passes between the poll's turn and the request whose answer counts."""
    world.scripts["1001"] = [(429, EMPTY), lineup("50", "60")]
    clock, prov = world.make(at(14, 30))
    monkeypatch.setattr(api_football.time, "sleep", clock.sleep)
    probe.run(["--db", str(world.db), "--date", DAY], clock=clock, sleep=clock.sleep, provider=prov)
    out = capsys.readouterr().out
    assert "14:46:00Z T-120 (asked at T-119.0) · match 1:" in out
    assert "first eleven per side at T-120 (asked at T-119.0), the first poll" in line_of(out, "1001")


def test_an_answer_asked_for_past_the_limit_is_missed(world, capsys, monkeypatch):
    """The laptop sleeps inside the adapter's pace before the request: the answer is printed, never under its label."""
    world.scripts["1001"] = [lineup("50", "60")]
    clock, prov = world.make(at(14, 30))
    monkeypatch.setattr(api_football, "_RATE_LIMIT_SECONDS", 6.0)
    first = {"done": False}

    def adapter_sleep(s):
        clock.sleep(400 if not first["done"] else s)
        first["done"] = True
    monkeypatch.setattr(api_football.time, "sleep", adapter_sleep)
    probe.run(["--db", str(world.db), "--date", DAY], clock=clock, sleep=clock.sleep, provider=prov)
    out = capsys.readouterr().out
    assert "14:51:40Z T-120 (asked at T-113.3) · match 1: home (team 50) 11 starters + 9 bench · away (team 60) 11 " \
           "starters + 9 bench · MISSED (asked 6.7 min past its time: not counted under its label)" in out
    assert "first eleven per side at T-90" in line_of(out, "1001") and "missed 1" in line_of(out, "1001")


@pytest.mark.parametrize("answer, why", [
    (lineup("50"), "one side only"),
    (lineup("50", "60", starters=12), "twelve starters"),
    (lineup("50", "60", "99"), "three team ids"),
    (lineup("50", "60", placeholder="50"), "a placeholder"),
])
def test_eleven_per_side_means_two_team_ids_with_exactly_eleven_named_starters(world, capsys, answer, why):
    world.scripts["1001"] = [answer]
    _, out, _, _ = go(world, at(14, 30), capsys)
    assert "no poll of the 7 answered came back with eleven per side" in line_of(out, "1001"), why


def test_plan_makes_no_call_and_names_the_polls_already_past(world, capsys, monkeypatch):
    clock, prov = world.make(at(16, 0))
    monkeypatch.setattr(probe, "Provider", lambda *a, **kw: pytest.fail("--plan built a provider"))
    rc = probe.run(["--db", str(world.db), "--date", DAY, "--plan"], clock=clock, sleep=clock.sleep, provider=prov)
    out = capsys.readouterr().out
    assert rc == 0 and world.asked == [] and prov.calls == 0 and clock.naps == []
    assert "PLAN (21 polls; --plan: no call made)" in out
    assert "  14:45Z T-120 · match 1 · already past" in out and "  14:45Z T-120 · match 2 · already past" in out
    assert "  16:00Z T-45 · match 1\n" in out and "  16:30Z T-15 · match 2\n" in out


def test_nothing_is_written(world, capsys):
    world.scripts["1001"] = [lineup("50", "60")]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in world.db.parent.iterdir()}
    _, out, _, _ = go(world, at(14, 30), capsys)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in world.db.parent.iterdir()}
    assert after == before and "opened via mode=ro URI" in out


def test_the_database_is_opened_mode_ro_and_refuses_a_write(world):
    con, form = probe.open_read(world.db)
    assert form == "mode=ro URI"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("DELETE FROM matches")
    con.close()


def test_a_copy_that_refuses_mode_ro_is_opened_query_only_and_refuses_a_write(world, monkeypatch):
    """#421: the plain path with PRAGMA query_only = ON, the form printed; a write through it fails."""
    real = sqlite3.connect

    def connect(target, *a, **kw):
        if kw.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(target, *a, **kw)
    monkeypatch.setattr(probe.sqlite3, "connect", connect)
    con, form = probe.open_read(world.db)
    assert form == "plain path with PRAGMA query_only = ON (mode=ro refused)"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("DELETE FROM matches")
    con.close()


def test_a_day_with_no_fixture_to_poll_exits_1_with_no_call(world, capsys):
    clock, prov = world.make(datetime(2026, 10, 22, 12, 0))
    rc = probe.run(["--db", str(world.db), "--date", "2026-10-22"], clock=clock, sleep=clock.sleep, provider=prov)
    out = capsys.readouterr().out
    assert rc == 1 and "Nothing to poll" in out and world.asked == []


def test_a_bad_date_exits_2(world, capsys):
    clock = Clock(at(12, 0))
    assert probe.run(["--db", str(world.db), "--date", "2026-10-32"], clock=clock, sleep=clock.sleep) == 2
    assert "is not a real date" in capsys.readouterr().out


def test_no_key_stops_before_any_call(world, capsys, monkeypatch):
    monkeypatch.setattr(api_football, "settings", dataclasses.replace(api_football.settings, api_football_key=""))
    clock = Clock(at(14, 30))
    rc = probe.run(["--db", str(world.db), "--date", DAY], clock=clock, sleep=clock.sleep)
    out = capsys.readouterr().out
    assert rc == 1 and "API-Football key is required" in out and world.asked == [] and clock.naps == []


def test_no_database_file_is_never_created(tmp_path, capsys):
    missing = tmp_path / "nope.db"
    with pytest.raises(SystemExit, match="never creates one"):
        probe.run(["--db", str(missing), "--date", DAY], clock=Clock(at(12, 0)))
    assert not missing.exists()


def test_ctrl_c_between_polls_prints_the_summary_so_far(world, capsys):
    world.scripts["1001"] = [lineup("50", "60")]
    clock, prov = world.make(at(14, 30))

    def sleep(s):
        if clock.now >= datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc):
            raise KeyboardInterrupt
        clock.sleep(s)
    rc = probe.run(["--db", str(world.db), "--date", DAY], clock=clock, sleep=sleep, provider=prov)
    out = capsys.readouterr().out
    assert rc == 0 and "\nINTERRUPTED at 15:30:00Z: the polls after it were not made" in out
    assert "first eleven per side at T-120" in line_of(out, "1001")
    # 14:45, 15:15 and 15:30 are polled (the clock reaches 15:30 on the nap before it); the nap toward 15:45 is cut
    assert "no poll of the 3 answered came back with eleven per side · cut off by the interrupt" in line_of(out, "1005")
    assert "no poll made · cut off by the interrupt" in line_of(out, "1002")
    assert "cut off by the interrupt 2" in out


def test_ctrl_c_during_a_call_is_printed_and_counted(world, capsys):
    world.scripts["1005"] = [EMPTY, KeyboardInterrupt()]
    _, out, _, prov = go(world, at(14, 30), capsys)
    assert "15:15Z T-90 · match 2: INTERRUPTED during the call" in out
    assert "interrupted 1" in line_of(out, "1005") and "cut off by the interrupt" in line_of(out, "1005")
    assert "HTTP requests 4 (by status {200: 3, 'no answer': 1})" in out


def test_an_interrupted_final_poll_cuts_the_fixture_off(world, capsys):
    """Codex on #528: Ctrl-C in a fixture's seventh and last call leaves seven polls; the fixture is still cut off."""
    world.scripts["1002"] = [EMPTY] * 6 + [KeyboardInterrupt()]
    _, out, _, _ = go(world, at(14, 30), capsys)
    ln = line_of(out, "1002")
    assert "18:45Z T-15 · match 3: INTERRUPTED during the call" in out
    assert "no poll of the 6 answered came back with eleven per side · cut off by the interrupt" in ln
    assert ln.endswith("polls answered 6, failed 0, missed 0, interrupted 1")
    assert "cut off by the interrupt 1" in out


def test_a_failed_request_asked_past_the_limit_is_missed_not_failed(world, capsys, monkeypatch):
    """Codex on #528: a request sent past the limit is missed, whatever came back; a failure is not counted under
    its label either."""
    world.scripts["1001"] = [(500, EMPTY), lineup("50", "60")]
    clock, prov = world.make(at(14, 30))
    monkeypatch.setattr(api_football, "_RATE_LIMIT_SECONDS", 6.0)
    first = {"done": False}

    def adapter_sleep(s):
        clock.sleep(400 if not first["done"] else s)
        first["done"] = True
    monkeypatch.setattr(api_football.time, "sleep", adapter_sleep)
    probe.run(["--db", str(world.db), "--date", DAY], clock=clock, sleep=clock.sleep, provider=prov)
    out = capsys.readouterr().out
    assert "14:51:40Z T-120 (asked at T-113.3) · match 1: ✗ HTTPError: 500 Error for url: fixtures/lineups · MISSED " \
           "(asked 6.7 min past its time: not counted under its label)" in out
    ln = line_of(out, "1001")
    assert "first eleven per side at T-90" in ln and ln.endswith("failed 0, missed 1")
    assert "failed 1" in out.split("calls: ")[1]                      # the call itself is still counted as failed


def test_competition_names_the_stored_code_polled_and_cl_stays_the_default(world, capsys, monkeypatch):
    """Addendum 75 item 3(a): "The timing probe takes --competition (CL default; UEL; EFL; the same polls)". A UEL row
    on the day is read only under --competition UEL; the default reads CL's rows as before."""
    eng = create_engine(f"sqlite:///{world.db}")
    with Session(eng) as s:
        uel = Competition(sport=Sport.SOCCER, code="UEL", name="UEFA Europa League", area="Europe", type="CUP")
        s.add(uel)
        s.flush()
        home, away = s.query(Team).filter(Team.name.in_(["Club 50", "Club 60"])).order_by(Team.name).all()
        s.add(Match(sport=Sport.SOCCER, competition_id=uel.id, season="2026/27", utc_date=LATE, home_team_id=home.id,
                    away_team_id=away.id, status=MatchStatus.SCHEDULED, external_ids={SRC: "2001"}))
        s.commit()
    eng.dispose()
    (clock, prov), (clock2, prov2) = world.make(at(16, 0)), world.make(at(16, 0))
    monkeypatch.setattr(probe, "Provider", lambda *a, **kw: pytest.fail("--plan built a provider"))
    assert probe.run(["--db", str(world.db), "--date", DAY, "--plan", "--competition", "UEL"], clock=clock,
                     sleep=clock.sleep, provider=prov) == 0
    out = capsys.readouterr().out
    assert "· competition UEL · read-only, nothing written" in out
    assert "of competitions.code = 'UEL'" in out and "  1 UEL row(s) stored with a kickoff on 2026-10-20" in out
    assert "PLAN (7 polls; --plan: no call made)" in out and "fixture 2001" in out and "fixture 1001" not in out
    probe.run(["--db", str(world.db), "--date", DAY, "--plan"], clock=clock2, sleep=clock2.sleep, provider=prov2)
    out = capsys.readouterr().out
    assert "· competition CL · read-only" in out and "PLAN (21 polls; --plan: no call made)" in out
    assert "fixture 2001" not in out


def test_a_competition_outside_the_three_is_refused_by_the_parser(world, capsys):
    clock = Clock(at(12, 0))
    with pytest.raises(SystemExit) as e:
        probe.run(["--db", str(world.db), "--competition", "BL1"], clock=clock, sleep=clock.sleep)
    assert e.value.code == 2 and "invalid choice: 'BL1'" in capsys.readouterr().err


def _europa_row(world, code, fid):
    """A Europa League competition stored under `code` (UEL or EL: api_football maps both to league 3) with one row on
    the day, on the test's throwaway DB."""
    eng = create_engine(f"sqlite:///{world.db}")
    with Session(eng) as s:
        comp = Competition(sport=Sport.SOCCER, code=code, name="UEFA Europa League", area="Europe", type="CUP")
        s.add(comp)
        s.flush()
        home, away = s.query(Team).filter(Team.name.in_(["Club 55", "Club 65"])).order_by(Team.name).all()
        s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=LATE, home_team_id=home.id,
                    away_team_id=away.id, status=MatchStatus.SCHEDULED, external_ids={SRC: fid}))
        s.commit()
    eng.dispose()


def test_el_is_a_choice_and_reads_its_own_rows(world, capsys, monkeypatch):
    """Addendum 76 item 2: "choices CL|UEL|EL|EFL"."""
    _europa_row(world, "EL", "3001")
    clock, prov = world.make(at(16, 0))
    monkeypatch.setattr(probe, "Provider", lambda *a, **kw: pytest.fail("--plan built a provider"))
    assert probe.run(["--db", str(world.db), "--date", DAY, "--plan", "--competition", "EL"], clock=clock,
                     sleep=clock.sleep, provider=prov) == 0
    out = capsys.readouterr().out
    assert "  1 EL row(s) stored with a kickoff on 2026-10-20\n" in out and "fixture 3001" in out
    assert "PLAN (7 polls; --plan: no call made)" in out


@pytest.mark.parametrize("asked,stored", [("UEL", "EL"), ("EL", "UEL")])
def test_a_day_with_no_row_under_the_code_asked_names_the_other_europa_code(world, capsys, asked, stored):
    """Addendum 76 item 2: the "0 rows" line says how many rows the other Europa League code holds that day, so the
    operator re-runs with the right code; nothing is read as the other code (no poll, exit 1)."""
    _europa_row(world, stored, "3002")
    clock, prov = world.make(at(16, 0))
    rc = probe.run(["--db", str(world.db), "--date", DAY, "--competition", asked], clock=clock, sleep=clock.sleep,
                   provider=prov)
    out = capsys.readouterr().out
    assert rc == 1 and world.asked == [] and "Nothing to poll" in out and "fixture 3002" not in out
    assert (f"  0 {asked} row(s) stored with a kickoff on 2026-10-20 · {stored} holds 1 row(s) that day: the Europa "
            f"League is stored under {stored} here; re-run with --competition {stored} (rows are never read as the "
            "other code)") in out


def test_neither_europa_code_on_the_day_says_so_and_cl_names_no_other_code(world, capsys):
    clock, prov = world.make(at(16, 0))
    assert probe.run(["--db", str(world.db), "--date", "2026-10-22", "--competition", "UEL"], clock=clock,
                     sleep=clock.sleep, provider=prov) == 1
    assert "  0 UEL row(s) stored with a kickoff on 2026-10-22 · EL holds 0 row(s) that day\n" in capsys.readouterr().out
    clock, prov = world.make(at(16, 0))
    probe.run(["--db", str(world.db), "--date", "2026-10-22"], clock=clock, sleep=clock.sleep, provider=prov)
    assert "  0 CL row(s) stored with a kickoff on 2026-10-22\n" in capsys.readouterr().out


def test_pl_is_a_choice_and_reads_its_own_rows(world, capsys, monkeypatch):
    """Addendum 163 item 4: PL in the choice list, read under the stored code 'PL' (the world's PL row, 1004)."""
    clock, prov = world.make(at(16, 0))
    monkeypatch.setattr(probe, "Provider", lambda *a, **kw: pytest.fail("--plan built a provider"))
    assert "PL" in probe.COMPETITIONS
    assert probe.run(["--db", str(world.db), "--date", DAY, "--plan", "--competition", "PL"], clock=clock,
                     sleep=clock.sleep, provider=prov) == 0
    out = capsys.readouterr().out
    assert "  1 PL row(s) stored with a kickoff on 2026-10-20\n" in out and "fixture 1004" in out
    assert "fixture 1001" not in out                        # a CL row is never read as PL
