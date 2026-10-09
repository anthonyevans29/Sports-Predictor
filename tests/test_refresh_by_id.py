"""ARCHITECT 2026-10-09 (addendum 21 item 1): "For NCAA, the kickoff, status and score of every stored
SCHEDULED game kicking off in the next seven days are refreshed from the provider by the game's own id, at
least once a day on the host and in the laptop's morning chain. The listing reads stay: they find games we
do not hold. A game the provider does not return by id is never guessed and never deleted: it is counted
and listed, and nothing else is done to it."

Throwaway DB only (tests/conftest.py); the provider is a fake adapter, no network."""
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters.api_american_football import RateLimited
from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.ingestion import refresh_by_id as rbi
from src.ingestion import service as svc
from src.timeutil import utc_now_naive

HOSTING = Path(__file__).resolve().parent.parent / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))
import chains  # noqa: E402
import sp_run  # noqa: E402

SRC = "api_american_football"
TODAY = utc_now_naive().date()
DAY3 = datetime.combine(TODAY + timedelta(days=3), time())
PLACEHOLDER = DAY3 + timedelta(hours=4)               # the provider's unannounced 04:00Z
ANNOUNCED = DAY3 + timedelta(hours=23, minutes=30)    # Georgia at Alabama, 23:30Z


class FakeAdapter:
    """list_matches = the listing (which omits not-started games); get_game = the answer by id."""
    source_name = SRC

    def __init__(self, listing=(), by_id=None, limited=None):
        self.listing, self.by_id = list(listing), dict(by_id or {})
        self.limited = dict(limited or {})     # id -> how many 429s before it answers
        self.calls = []

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        self.calls.append(("date", date_from))
        return [g for g in self.listing if g.utc_date.strftime("%Y-%m-%d") == date_from]

    def get_game(self, sid, code="NCAA"):
        self.calls.append(("id", sid))
        if self.limited.get(sid, 0) > 0:
            self.limited[sid] -= 1
            raise RateLimited("games", 7)
        if sid not in self.by_id:
            return False, None
        return True, self.by_id[sid]


def _nm(code, sid, h, a, when, status=MatchStatus.SCHEDULED, hs=None, as_=None):
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season="2026", utc_date=when, status=status,
                           home_team_source_id=h, away_team_source_id=a, source=SRC, source_id=sid,
                           home_score=hs, away_score=as_)


def _comp(s, code):
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.NFL, code=code, name=code, area="USA", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _team(s, tag):
    t = s.execute(select(Team).where(Team.name == f"RBI {tag}")).scalar_one_or_none()
    if t is None:
        t = Team(sport=Sport.NFL, name=f"RBI {tag}", external_ids={SRC: f"rbi-{tag}"})
        s.add(t)
        s.flush()
    return t


def _match(code, sid, h, a, when, status=MatchStatus.SCHEDULED):
    init_db()
    with session_scope() as s:
        c = _comp(s, code)
        m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=when, status=status,
                  home_team_id=_team(s, h).id, away_team_id=_team(s, a).id,
                  external_ids={SRC: sid} if sid else {})
        s.add(m)
        s.flush()
        return m.id


def _row(mid):
    with session_scope() as s:
        m = s.get(Match, mid)
        return None if m is None else {"utc": m.utc_date, "status": m.status, "ext": dict(m.external_ids or {}),
                                       "score": (m.home_score, m.away_score)}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setattr(svc, "_odds_sleep", lambda s: None)      # pacing and the retry window: no real sleep
    made = []
    yield made
    with session_scope() as s:
        s.query(Match).filter(Match.id.in_(made)).delete(synchronize_session=False)


def _run_chain(monkeypatch, adapter, steps):
    import cli
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: adapter)
    outs = []
    for st in steps:
        res = CliRunner().invoke(cli.cli, st)
        assert res.exit_code == 0, (st, res.output, res.exception)
        outs.append(res.output)
    return outs


def test_a_scheduled_game_the_listing_omits_gets_the_kickoff_the_provider_answers_by_id(monkeypatch, _isolated):
    """THE TEST THAT FAILS ON TODAY'S CHAIN (addendum 21 item 1): a stored SCHEDULED NCAA game in the next
    seven days that the listing omits, whose answer by id carries another kickoff. After the ncaa-schedule
    chain (its steps, resolved as sp_run resolves them, against a fake adapter and the throwaway DB) the
    stored kickoff is the provider's. Without the refresh-by-id step the listing reads leave it at 04:00Z."""
    mid = _match("NCAA", "23653", "alabama", "georgia", PLACEHOLDER)
    _isolated.append(mid)
    answer = _nm("NCAA", "23653", "rbi-alabama", "rbi-georgia", ANNOUNCED)
    steps = sp_run.resolve("ncaa-schedule", {}, TODAY)
    listing_only = [st for st in steps if st[0] != "refresh-by-id"]

    fake = FakeAdapter(listing=[], by_id={"23653": answer})   # the listing no longer carries the game
    _run_chain(monkeypatch, fake, listing_only)
    assert _row(mid)["utc"] == PLACEHOLDER                    # today's chain: still the placeholder

    outs = _run_chain(monkeypatch, fake, steps)
    assert _row(mid)["utc"] == ANNOUNCED, outs[-1]            # after the chain: the provider's kickoff
    assert _row(mid)["status"] == MatchStatus.SCHEDULED
    assert f"{PLACEHOLDER.isoformat(sep=' ', timespec='minutes')} -> " \
           f"{ANNOUNCED.isoformat(sep=' ', timespec='minutes')}" in outs[-1]
    assert [c for c in fake.calls if c == ("id", "23653")] == [("id", "23653")]   # one GET per game
    assert len(listing_only) == 8 and len(steps) == 9       # the forward-week listing reads stay


def test_the_chain_keeps_its_listing_reads_and_refreshes_by_id_last():
    steps = chains.CHAINS["ncaa-schedule"]["steps"]
    assert [st[0] for st in steps] == ["sync-matches"] * 8 + ["refresh-by-id"]
    assert steps[-1] == ["refresh-by-id", "--competition", "NCAA", "--days", "7"]
    assert "refresh-by-id" not in chains.UNMETERED          # api-sports: metered


def test_a_rate_limited_answer_is_deferred_and_retried_never_dropped(monkeypatch, _isolated):
    slept = []
    monkeypatch.setattr(svc, "_odds_sleep", lambda s: slept.append(s))
    a = _match("RBX", "9001", "h1", "a1", PLACEHOLDER)
    b = _match("RBX", "9002", "h2", "a2", PLACEHOLDER)
    _isolated.extend([a, b])
    fake = FakeAdapter(by_id={"9001": _nm("RBX", "9001", "rbi-h1", "rbi-a1", ANNOUNCED),
                              "9002": _nm("RBX", "9002", "rbi-h2", "rbi-a2", ANNOUNCED)},
                       limited={"9002": 1})
    r = rbi.refresh("RBX", fake, days=7)
    assert r["rate_limited"] == 1 and r["recovered"] == 1 and r["still_rate_limited"] == []
    assert 7 in slept                                          # waited the provider's Retry-After
    assert [c for c in fake.calls if c[0] == "id"] == [("id", "9001"), ("id", "9002"), ("id", "9002")]
    assert _row(a)["utc"] == ANNOUNCED and _row(b)["utc"] == ANNOUNCED
    assert r["updated"] == 2


def test_still_rate_limited_after_the_rounds_is_listed_untouched_and_fails_the_step(monkeypatch, _isolated):
    import cli
    a = _match("NCAA", "9101", "h3", "a3", PLACEHOLDER)
    _isolated.append(a)
    fake = FakeAdapter(by_id={"9101": _nm("NCAA", "9101", "rbi-h3", "rbi-a3", ANNOUNCED)},
                       limited={"9101": svc.ODDS_RETRY_ROUNDS + 1})
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: fake)
    res = CliRunner().invoke(cli.cli, ["refresh-by-id", "--competition", "NCAA", "--days", "7"])
    assert res.exit_code == 1, res.output
    assert "STILL RATE LIMITED (untouched): match %d id 9101" % a in res.output
    assert [c for c in fake.calls if c == ("id", "9101")] == [("id", "9101")] * (svc.ODDS_RETRY_ROUNDS + 1)
    assert _row(a)["utc"] == PLACEHOLDER


def test_a_game_not_returned_by_id_is_counted_listed_and_untouched(_isolated):
    a = _match("RBX", "9201", "h4", "a4", PLACEHOLDER)
    _isolated.append(a)
    before = _row(a)
    r = rbi.refresh("RBX", FakeAdapter(by_id={}), days=7)
    nf = [x for x in r["not_found"] if x["match_id"] == a]
    assert len(nf) == 1 and nf[0]["id"] == "9201"
    assert _row(a) == before                                  # never guessed, never deleted
    assert all(x["match_id"] != a for x in r["kickoff_moved"])


def test_the_receipt_counts_prints_and_is_appended(monkeypatch, _isolated, tmp_path):
    import cli
    code = "NCAA"
    rows = {
        "same": _match(code, "9301", "h5", "a5", ANNOUNCED),
        "moved": _match(code, "9302", "h6", "a6", PLACEHOLDER),
        "final": _match(code, "9303", "h7", "a7", DAY3 + timedelta(hours=1)),
        "gone": _match(code, "9304", "h8", "a8", PLACEHOLDER),
        "noid": _match(code, None, "h9", "a9", PLACEHOLDER),
        "other": _match(code, "9306", "h10", "a10", PLACEHOLDER),
        "outside": _match(code, "9307", "h11", "a11", DAY3 + timedelta(days=6)),   # today+9: not asked
        "odd": _match(code, "9308", "h12", "a12", PLACEHOLDER),
    }
    _isolated.extend(rows.values())
    fake = FakeAdapter(by_id={
        "9301": _nm(code, "9301", "rbi-h5", "rbi-a5", ANNOUNCED),
        "9302": _nm(code, "9302", "rbi-h6", "rbi-a6", ANNOUNCED),
        "9303": _nm(code, "9303", "rbi-h7", "rbi-a7", DAY3 + timedelta(hours=1), MatchStatus.FINISHED, 31, 24),
        "9306": _nm(code, "9306", "rbi-somebody", "rbi-a10", ANNOUNCED),      # another game's teams
        "9307": _nm(code, "9307", "rbi-h11", "rbi-a11", ANNOUNCED),
        "9308": _nm(code, "9308", "rbi-h12", "rbi-a12", PLACEHOLDER, MatchStatus.SCHEDULED),
    })
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: fake)
    res = CliRunner().invoke(cli.cli, ["refresh-by-id", "--competition", "NCAA", "--days", "7"])
    assert res.exit_code == 0, res.output
    log = [json.loads(x) for x in (tmp_path / "receipts.jsonl").read_text().splitlines()]
    rec = log[-1]
    assert rec["kind"] == "refresh_by_id" and rec["competition"] == "NCAA"

    def mine(key):
        return sorted(x["match_id"] for x in rec[key] if x["match_id"] in rows.values())
    assert mine("kickoff_moved") == [rows["moved"]]
    assert mine("status_changed") == [rows["final"]] and mine("score_changed") == [rows["final"]]
    assert mine("not_found") == [rows["gone"]]
    assert mine("no_id") == [rows["noid"]]
    assert mine("refused") == [rows["other"]]
    assert ("id", "9307") not in fake.calls                  # outside the seven days
    km = next(x for x in rec["kickoff_moved"] if x["match_id"] == rows["moved"])
    assert (km["stored_kickoff"], km["provider_kickoff"]) == (PLACEHOLDER.isoformat(sep=" ", timespec="minutes"),
                                                              ANNOUNCED.isoformat(sep=" ", timespec="minutes"))
    # the test DB may hold other NCAA rows in the window (other tests); the counts here are this test's rows
    asked_mine = {"9301", "9302", "9303", "9304", "9306", "9308"}
    assert asked_mine <= {c[1] for c in fake.calls if c[0] == "id"}
    assert rec["asked"] >= 6 and rec["updated"] >= 2 and rec["unchanged"] >= 2
    assert rec["asked"] == (rec["unchanged"] + rec["updated"] + len(rec["not_found"]) + len(rec["refused"])
                            + len(rec["excluded"]) + len(rec["unresolved"]) + len(rec["still_rate_limited"]))
    printed = res.output
    assert "REFRESH-BY-ID NCAA" in printed and "REFRESH-BY-ID-RECEIPT " in printed
    assert f"NOT FOUND by id (untouched): match {rows['gone']} id 9304" in printed
    assert _row(rows["final"])["status"] == MatchStatus.FINISHED and _row(rows["final"])["score"] == (31, 24)
    assert _row(rows["other"])["utc"] == PLACEHOLDER          # refused: untouched
    assert _row(rows["same"])["utc"] == ANNOUNCED


def test_refresh_by_id_refuses_a_competition_outside_the_american_football_provider():
    import cli
    res = CliRunner().invoke(cli.cli, ["refresh-by-id", "--competition", "PL"])
    assert res.exit_code == 2 and "not one of its competitions" in res.output


class _Boom(FakeAdapter):
    def get_game(self, sid, code="NCAA"):
        if sid == "9601":
            self.calls.append(("id", sid))
            raise ConnectionError("provider down")
        return super().get_game(sid, code)


def test_unresolved_a_lookup_error_is_listed_untouched_and_exits_1(monkeypatch, _isolated):
    """Addendum 23 item 1 (b), for #378: the UNRESOLVED path (a lookup error, exit 1) gets a test of its own."""
    import cli
    a = _match("NCAA", "9601", "h20", "a20", PLACEHOLDER)
    _isolated.append(a)
    fake = _Boom()
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: fake)
    res = CliRunner().invoke(cli.cli, ["refresh-by-id", "--competition", "NCAA", "--days", "7"])
    assert res.exit_code == 1, res.output
    assert f"UNRESOLVED (untouched): match {a} id 9601" in res.output and "ConnectionError" in res.output
    assert _row(a)["utc"] == PLACEHOLDER
