"""THE POSITION LOOKUP (ARCHITECT 2026-10-12, addendum 44 item 4; #432, #424, #440), on the throwaway DB, the real
NFL adapter with its HTTP replaced (the test double):

"A listed player whose position the roster does not give is asked for by his provider id. The answer is kept, so a
player is asked once and not at every read. A quarterback found that way is a quarterback for the rule like any
other. What the provider does not answer stays unresolved, counted and on the page as today. Under --strict a lookup
that fails is a failed read; an answer that holds no position is not. A name the feed lists under two ids is
ambiguous: not asked, counted and listed." Only the position field is taken."""
from datetime import timedelta

import pytest
from click.testing import CliRunner

from src.db.database import init_db, session_scope


def _fixture(code):
    from src.db.schema import Competition, CompetitionTeam, Match, MatchStatus, Sport, Team
    from src.timeutil import utc_now_naive
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code=code, name=code, area="X", type="LEAGUE")
        s.add(comp)
        s.flush()
        ts = []
        for i in range(2):
            t = Team(sport=Sport.NFL, name=f"{code} {i}", external_ids={"api_american_football": f"{code}-{i}"})
            s.add(t)
            s.flush()
            s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2026"))
            ts.append(t.id)
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", status=MatchStatus.SCHEDULED,
                  utc_date=utc_now_naive() + timedelta(hours=2), home_team_id=ts[0], away_team_id=ts[1])
        s.add(m)
        s.flush()
        return m.id, ts


class Double:
    """The provider: a roster that gives no position to the injured players, an injury feed per team, and
    /players?id= answers by id (a dict, "raise", or "errors"). Every call is counted."""

    def __init__(self, injuries, answers, roster=None):
        self.injuries, self.answers, self.roster = injuries, answers, roster or {}
        self.calls = {"players_by_id": 0, "roster": 0, "injuries": 0}
        self.asked_ids: list = []

    def get(self, path, params=None):
        params = params or {}
        if path == "players" and "id" in params:
            self.calls["players_by_id"] += 1
            self.asked_ids.append(str(params["id"]))
            a = self.answers.get(str(params["id"]))
            if a == "raise":
                raise ConnectionError("players down")
            if a == "errors":
                return {"errors": {"requests": "limit"}, "response": []}
            return a if a is not None else {"response": []}
        if path == "players":
            self.calls["roster"] += 1
            return {"response": self.roster.get(params["team"], [{"id": 900, "name": "Some Starter",
                                                                    "position": "OL"}])}
        self.calls["injuries"] += 1
        return {"response": [{"player": p, "status": "Out", "description": "knee"}
                             for p in self.injuries.get(params["team"], [])]}


def _ans(pid, **fields):
    return {"response": [{"id": pid, "name": "x", **fields}]}


def _run(monkeypatch, code, double, *extra):
    import cli
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    mid, ts = _fixture(code) if not getattr(double, "fixture", None) else double.fixture
    double.fixture = (mid, ts)
    ad = APIAmericanFootballAdapter()
    monkeypatch.setattr(ad, "_get", double.get)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: ad)
    r = CliRunner().invoke(cli.cli, ["sync-injuries", "--competition", code, "--season", "2026",
                                     "--match-ids", str(mid), *extra])
    return r, ts


def _stored(team_ids):
    from src.db.schema import Injury
    with session_scope() as s:
        return {i.player_name: i.player_position for i in s.query(Injury).filter(Injury.team_id.in_(team_ids))}


def _kept(*ids):
    from src.db.schema import PlayerPositionAnswer
    with session_scope() as s:
        return {r.player_id: r.position for r in s.query(PlayerPositionAnswer)
                if not ids or r.player_id in {str(i) for i in ids}}


def test_asked_by_id_kept_and_a_quarterback_so_found_is_a_quarterback(monkeypatch):
    from src.walters.qb_audit import is_qb
    d = Double({"PLA-0": [{"id": 11, "name": "Backup Qb"}], "PLA-1": [{"id": 12, "name": "A Receiver"}]},
               {"11": _ans(11, position="QB", group="Offense"), "12": _ans(12, position="WR")})
    r, ts = _run(monkeypatch, "PLA", d, "--strict")
    assert r.exit_code == 0, r.output
    st = _stored(ts)
    assert st == {"Backup Qb": "QB", "A Receiver": "WR"} and is_qb(st["Backup Qb"])
    assert d.calls["players_by_id"] == 2 and _kept(11, 12) == {"11": "QB", "12": "WR"}
    assert ("POSITION-LOOKUP (PLA): asked by provider id 2 (answered a position 2, answered none 0, failed 0) · "
            "from kept answers 0 · resolved by lookup 2 · kept 2 new · ambiguous, not asked 0") in r.output
    r2, _ = _run(monkeypatch, "PLA", d, "--strict")          # "a player is asked once and not at every read"
    assert r2.exit_code == 0 and d.calls["players_by_id"] == 2 and _stored(ts)["Backup Qb"] == "QB"
    assert "asked by provider id 0 " in r2.output and "from kept answers 2 · resolved by lookup 2" in r2.output


def test_an_answer_without_a_position_is_unresolved_kept_and_not_a_failed_read(monkeypatch):
    d = Double({"PLB-0": [{"id": 21, "name": "No Pos"}], "PLB-1": [{"id": 22, "name": "Group Only"}]},
               {"21": {"response": []}, "22": _ans(22, group="Defense")})      # nothing, and a group only
    r, ts = _run(monkeypatch, "PLB", d, "--strict")
    assert r.exit_code == 0 and "STRICT" not in r.output, r.output
    assert _stored(ts) == {"No Pos": None, "Group Only": None}               # only the position field is taken
    assert _kept(21, 22) == {"21": None, "22": None}
    assert "answered a position 0, answered none 2, failed 0" in r.output
    _run(monkeypatch, "PLB", d, "--strict")
    assert d.calls["players_by_id"] == 2                                     # not asked again


@pytest.mark.parametrize("bad", ["raise", "errors"])
def test_a_failed_lookup_is_a_failed_read_under_strict_and_is_not_kept(monkeypatch, bad):
    code = "PLC" if bad == "raise" else "PLD"
    d = Double({f"{code}-0": [{"id": 31, "name": "Lost Qb"}], f"{code}-1": []}, {"31": bad})
    r, ts = _run(monkeypatch, code, d)
    assert r.exit_code == 0 and "lookup failed: " in r.output                # default: listed, not a failure
    r, ts = _run(monkeypatch, code, d, "--strict")
    assert r.exit_code == 1 and "position lookup failed: Lost Qb (player id 31)" in r.output, r.output
    assert _stored(ts)["Lost Qb"] is None and "31" not in _kept(31)
    assert d.calls["players_by_id"] == 2                                     # nothing kept: asked at each read


def test_440_a_name_under_two_ids_is_ambiguous_not_asked_counted_and_listed(monkeypatch):
    d = Double({"PLE-0": [{"id": 41, "name": "Same Name"}, {"id": 42, "name": "Same Name"}], "PLE-1": []},
               {"41": _ans(41, position="QB"), "42": _ans(42, position="TE")})
    r, ts = _run(monkeypatch, "PLE", d, "--strict")
    assert r.exit_code == 0, r.output
    assert d.calls["players_by_id"] == 0 and _stored(ts) == {"Same Name": None}
    assert "ambiguous, not asked 1" in r.output and "ambiguous name (not asked): PLE 0: Same Name (ids 41, 42)" in r.output


def test_before_the_migration_the_lookup_runs_and_nothing_is_kept(monkeypatch):
    from sqlalchemy import text

    from src.db.database import get_engine
    d = Double({"PLF-0": [{"id": 51, "name": "Pre Mig"}], "PLF-1": []}, {"51": _ans(51, position="QB")})
    d.fixture = _fixture("PLF")                                               # init_db() first, then the drop
    with get_engine().begin() as c:
        c.execute(text("DROP TABLE IF EXISTS player_position_answers"))
    try:
        r, ts = _run(monkeypatch, "PLF", d, "--strict")
        assert r.exit_code == 0 and _stored(ts) == {"Pre Mig": "QB"}, r.output
        line = next(x for x in r.output.splitlines() if x.startswith("POSITION-LOOKUP"))
        assert "kept 0 new" in line, line
        _run(monkeypatch, "PLF", d, "--strict")
        assert d.calls["players_by_id"] == 2                                 # asked again: nothing could be kept
    finally:
        init_db()                                                            # the table back for the other tests
    assert _kept(51) == {}                                                   # nothing was kept before it existed
    import migrate_player_position_answers as mig
    assert mig.main() == 0                                                   # idempotent on an existing table


def test_the_roster_position_still_comes_first_no_lookup_when_it_answers(monkeypatch):
    d = Double({"PLG-0": [{"id": 61, "name": "On Roster"}], "PLG-1": []}, {"61": _ans(61, position="TE")},
               roster={"PLG-0": [{"id": 61, "name": "On Roster", "position": "QB"}]})
    r, ts = _run(monkeypatch, "PLG", d, "--strict")
    assert r.exit_code == 0 and _stored(ts) == {"On Roster": "QB"} and d.calls["players_by_id"] == 0
    assert "POSITION-LOOKUP" not in r.output                                 # nothing to look up: no line


def test_the_test_double_count_for_the_pr(monkeypatch, capsys):
    """The PR's receipt (addendum 44 item 4: "from a run on the test double, how many names resolve by lookup and the
    calls made"): 12 listed names the roster does not give across two teams: 8 answer a position (2 QBs), 2 answer
    none, 1 lookup fails, 1 name is listed under two ids. First read, then a second read of the same teams."""
    inj = {"PLH-0": [{"id": i, "name": f"P{i}"} for i in range(101, 107)]
           + [{"id": 199, "name": "Twice"}, {"id": 198, "name": "Twice"}],
           "PLH-1": [{"id": i, "name": f"P{i}"} for i in range(107, 111)]}
    answers = {str(i): _ans(i, position=("QB" if i in (101, 107) else "WR")) for i in range(101, 109)}
    answers.update({"109": {"response": []}, "110": "raise"})
    d = Double(inj, answers)
    r1, ts = _run(monkeypatch, "PLH", d)
    first = d.calls["players_by_id"]
    r2, _ = _run(monkeypatch, "PLH", d)
    second = d.calls["players_by_id"] - first
    line1 = next(x for x in r1.output.splitlines() if x.startswith("POSITION-LOOKUP"))
    line2 = next(x for x in r2.output.splitlines() if x.startswith("POSITION-LOOKUP"))
    print(f"\nTEST-DOUBLE RECEIPT: first read {first} /players?id= call(s): {line1}")
    print(f"TEST-DOUBLE RECEIPT: second read {second} call(s): {line2}")
    assert first == 10 and second == 1                                       # the failed one only is asked again
    assert "asked by provider id 10 (answered a position 8, answered none 1, failed 1)" in line1
    assert "resolved by lookup 8" in line1 and "kept 9 new" in line1
    assert "ambiguous, not asked 1" in line1 and _kept(198, 199) == {}
