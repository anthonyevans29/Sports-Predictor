"""THE BY-ID RECEIPT'S TWO CLASSES (ARCHITECT 2026-11-21 08:13 ET, addendum 437 item 2), after its first run stopped
at its first call on venue 0 ("STOPPED: the call for venue 0 failed (RuntimeError: API-Football error: {'id': 'The Id
field cannot be 0.'})"), which a re-run would ask first again:
  (a) a stored venue id that is not a positive integer is NEVER ASKED: counted and printed as its own class ("stored id
      is not a provider id"), with its rows and its games by home country, never "not served";
  (b) an answer in which the provider refuses the id (its errors block) is that id's answer: kept as served, counted as
      its own class with the provider's words, and the run goes on; any other errors block (a limit) or a transport
      failure still stops the run, resumable;
  (c) a run holding both completes with exit 0.
Throwaway DB and a .backup copy of it; the provider faked; every id synthetic."""
import json
import sqlite3
from datetime import datetime

import pytest

from src.ingestion import intl_venue_by_id as vb
from tests.test_433_venue_by_id_receipt import BY_ID, Provider, _run

REFUSAL = {"id": "The Id field must be a valid venue."}             # a synthetic refusal of the id, its own words


@pytest.fixture
def world(tmp_path, monkeypatch):
    """(copy, ids): 433's shapes plus two rows stored at venue 0 (homes Peru and Chile, the Chile one a cohort fixture)
    and one at a negative id."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team

    f = tmp_path / "w.db"
    eng = create_engine(f"sqlite:///{f}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True))
    db.init_db()
    ids = {}
    rows = [("esp", "Spain", 9501, "Spain", False), ("ns", "Peru", 9777, "Peru", False),
            ("z1", "Peru", 0, None, None), ("z2", "Chile", 0, None, None), ("neg", "Peru", -3, None, None)]
    with db.session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="FRIENDLIES_INT", name="F", area="I", type="INTL")
        s.add(c)
        s.flush()
        teams = {}
        for i, (key, home, vid, vc, flag) in enumerate(rows):
            for a in (home, "Away"):
                if a not in teams:
                    teams[a] = Team(sport=Sport.SOCCER, name=a, area=a)
                    s.add(teams[a])
            s.flush()
            m = Match(sport=Sport.SOCCER, competition_id=c.id, season="2026", utc_date=datetime(2026, 10, 1 + i),
                      status=MatchStatus.FINISHED, home_team_id=teams[home].id, away_team_id=teams["Away"].id,
                      home_score=1, away_score=0)
            s.add(m)
            s.flush()
            ids[key] = m.id
            s.add(IntlMatchVenue(match_id=m.id, venue_id=vid, venue_country=vc, home_country=home, neutral_v3=flag,
                                 rule="r"))
    copy = tmp_path / "copy" / "sports.db"
    copy.parent.mkdir()
    a, b = sqlite3.connect(str(f)), sqlite3.connect(str(copy))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    monkeypatch.setattr(vb, "cohort_ids", lambda: ({ids["z2"]}, "frozen (1 ids)"))
    return copy, ids


class Answers(Provider):
    """433's stand-in provider, answering an id from `served` when it names one (an errors block included), else from
    433's table."""
    served: dict = {}

    def _get(self, path, params):
        Answers.calls.append((path, params))
        if params["id"] <= 0:
            raise AssertionError(f"venue {params['id']} was asked")    # 437 item 2(a): never
        if params["id"] in Answers.served:
            return Answers.served[params["id"]]
        return {"response": BY_ID[params["id"]]}


@pytest.fixture
def provider(monkeypatch):
    Answers.calls, Answers.fail_on, Answers.served = [], None, {}
    monkeypatch.setattr(vb, "_client", Answers)
    return Answers


def _counts(out) -> str:
    return next(x for x in out.output.splitlines() if x.startswith("  by-id country:"))


def test_a_stored_id_that_is_not_a_positive_integer_is_never_asked_and_is_its_own_class(world, provider, tmp_path):
    """(a): venue 0 and venue -3 are never asked, never "not served"; their rows and games by home country printed,
    the cohort fixture among them named; the run completes."""
    copy, ids = world
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o")])
    assert out.exit_code == 0, out.output
    assert sorted(p["id"] for _, p in provider.calls) == [9501, 9777]
    assert not (tmp_path / "o" / "venue_id_0.json").exists()
    c = _counts(out)
    assert "not served 1 ·" in c and "stored id is not a provider id 2 (rows 3; never asked)" in c
    assert "refused by the provider 0" in c and c.endswith("not yet asked 0")
    L = out.output.splitlines()
    i = L.index(f"  STORED ID IS NOT A PROVIDER ID (2; never asked, not \"not served\": the provider was not asked) · "
                f"cohort fixtures 1 — {ids['z2']}:")
    assert L[i + 1:] == ["    venue -3: 1 stored games", "      home Peru: 1 · flag now unknown 1",
                         "    venue 0: 2 stored games", f"      home Chile: 1 · flag now unknown 1 · COHORT {ids['z2']}",
                         "      home Peru: 1 · flag now unknown 1"]
    assert "NOT SERVED BY ID (1): 9777" in out.output
    plan = _run(["--db", str(copy), "--out-dir", str(tmp_path / "p"), "--plan"])
    assert plan.output.splitlines()[-1].endswith("calls needed 2 (cap 700) · stored id is not a provider id, never "
                                                 "asked: 2")


def test_an_answer_refusing_the_id_is_kept_as_served_and_the_run_goes_on(world, provider, tmp_path):
    """(b): the refusal is the id's answer, kept as served (written before use, replayed with no call), counted with the
    provider's own words, never "not served"; the run goes on to the next id."""
    copy, _ = world
    payload = {"get": "venues", "parameters": {"id": "9501"}, "errors": REFUSAL, "results": 0, "response": []}
    provider.served = {9501: payload}
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o")])
    assert out.exit_code == 0, out.output
    assert [p["id"] for _, p in provider.calls] == [9501, 9777]          # the run went on past the refusal
    assert json.loads((tmp_path / "o" / "venue_id_9501.json").read_text()) == payload   # kept as served
    c = _counts(out)
    assert "refused by the provider 1" in c and "not served 1 ·" in c and "agrees 0" in c
    assert f"    venue 9501: {json.dumps(REFUSAL)} · 1 stored games" in out.output.splitlines()
    again = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o")])
    assert again.exit_code == 0 and len(provider.calls) == 2 and "refused by the provider 1" in _counts(again)


@pytest.mark.parametrize("errors", [{"requests": "You have reached the request limit for the day"},
                                    {"id": "x", "rateLimit": "Too many requests"}, ["an error"]])
def test_any_other_errors_block_still_stops_the_run_resumable(world, provider, tmp_path, errors):
    """A limit or an access error is not the id's answer: the run stops there (exit 3), nothing kept for that id, and a
    re-run asks it again."""
    copy, _ = world
    provider.served = {9501: {"errors": errors, "response": []}}
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o")])
    assert out.exit_code == 3 and "STOPPED: the provider answered venue 9501 with errors" in out.output
    assert not (tmp_path / "o" / "venue_id_9501.json").exists() and "not yet asked 2" in _counts(out)
    provider.served = {}
    again = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o")])
    assert again.exit_code == 0 and [p["id"] for _, p in provider.calls][-2:] == [9501, 9777]


def test_a_run_holding_both_classes_completes_with_exit_0(world, provider, tmp_path):
    """(c): venue 0 (never asked) and a refused id in the same run: COMPLETE, exit 0."""
    copy, _ = world
    provider.served = {9777: {"errors": REFUSAL, "response": []}}
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o")])
    assert out.exit_code == 0, out.output
    assert "· COMPLETE ·" in out.output.splitlines()[1]
    c = _counts(out)
    assert "refused by the provider 1" in c and "stored id is not a provider id 2" in c and "not served 0" in c


def test_the_adapters_answer_is_read_as_served_without_its_raise():
    """On the adapter, _ask goes through the adapter's own throttle and session and returns the errors block as served
    (APIFootballAdapter._get would raise on it); an HTTP error still raises."""
    class Resp:
        def __init__(self, code, body):
            self.status_code, self.body = code, body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self.body

    class Session:
        def __init__(self, resps):
            self.resps, self.calls = list(resps), []

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params))
            return self.resps.pop(0)

    class Adapter:
        base_url = "https://example.invalid"

        def __init__(self, resps):
            self._session, self.throttled = Session(resps), 0

        def _throttle(self):
            self.throttled += 1

    a = Adapter([Resp(200, {"errors": REFUSAL, "response": []})])
    assert vb._ask(a, 7) == {"errors": REFUSAL, "response": []}
    assert a.throttled == 1 and a._session.calls == [("https://example.invalid/venues", {"id": 7})]
    with pytest.raises(RuntimeError, match="HTTP 500"):
        vb._ask(Adapter([Resp(500, {})]), 7)
    assert vb.refused_id({"errors": REFUSAL}) == REFUSAL and vb.refused_id({"errors": {}}) is None
    assert vb.refused_id({"errors": {"requests": "x"}}) is None and vb.refused_id({"errors": ["x"]}) is None
    assert [vb.provider_id(v) for v in (1, 0, -1, True, "5", None)] == [True, False, False, False, False, False]
