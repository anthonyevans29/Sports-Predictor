"""THE POSITION LOOKUP (ARCHITECT 2026-10-12, addendum 44 item 4; #432, #424, #440), on the throwaway DB, the real
NFL adapter with its HTTP replaced (the test double):

"A listed player whose position the roster does not give is asked for by his provider id. The answer is kept, so a
player is asked once and not at every read. A quarterback found that way is a quarterback for the rule like any
other. What the provider does not answer stays unresolved, counted and on the page as today. Under --strict a lookup
that fails is a failed read; an answer that holds no position is not. A name the feed lists under two ids is
ambiguous: not asked, counted and listed." Only the position field is taken. (The last sentence is replaced by
addendum 47 item 3, #454: entries are told apart by provider id; tests at the end of this file.)
Addendum 46 item 2 (RULED): "Only an answer that gives a position is kept. An answer that gives none, an empty answer
included, leaves the player unresolved and counted. It is not a failed read, it is not kept, and he is asked again at
the next read." """
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
            if a == "429":
                from src.adapters.api_american_football import RateLimited
                raise RateLimited("players", 60)
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
    if not getattr(double, "ncaa", False):          # the scratch codes stand for NFL (cli.POSITION_LOOKUP_COMPS)
        monkeypatch.setattr(cli, "POSITION_LOOKUP_COMPS", ("NFL", code))
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
            "from kept answers 0 · resolved by lookup 2 · kept 2 new") in r.output
    r2, _ = _run(monkeypatch, "PLA", d, "--strict")          # "a player is asked once and not at every read"
    assert r2.exit_code == 0 and d.calls["players_by_id"] == 2 and _stored(ts)["Backup Qb"] == "QB"
    assert "asked by provider id 0 " in r2.output and "from kept answers 2 · resolved by lookup 2" in r2.output


def test_46_an_answer_without_a_position_is_unresolved_not_kept_and_asked_again(monkeypatch):
    """Addendum 46 item 2: an answer with no position (an empty answer, or a group only) is counted, is not a failed
    read, is NOT kept, and the player is asked again at the next read."""
    d = Double({"PLB-0": [{"id": 21, "name": "No Pos"}], "PLB-1": [{"id": 22, "name": "Group Only"}]},
               {"21": {"response": []}, "22": _ans(22, group="Defense")})      # nothing, and a group only
    r, ts = _run(monkeypatch, "PLB", d, "--strict")
    assert r.exit_code == 0 and "STRICT" not in r.output, r.output
    assert _stored(ts) == {"No Pos": None, "Group Only": None}               # only the position field is taken
    assert _kept(21, 22) == {}                                               # nothing kept for them
    assert "answered a position 0, answered none 2, failed 0" in r.output and "kept 0 new" in r.output
    r2, _ = _run(monkeypatch, "PLB", d, "--strict")
    assert r2.exit_code == 0 and d.calls["players_by_id"] == 4               # asked again at the second read
    assert sorted(d.asked_ids) == ["21", "21", "22", "22"] and _kept(21, 22) == {}
    d.answers["21"] = _ans(21, position="QB")                                # the provider answers later: kept then
    _run(monkeypatch, "PLB", d, "--strict")
    assert _kept(21) == {"21": "QB"} and _stored(ts)["No Pos"] == "QB"


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
    calls made"): 12 listed entries the roster does not give across two teams: 8 answer a position (2 QBs), 1 answers
    empty, 1 lookup fails, and one name is listed under two ids, which addendum 47 item 3 makes two players, each
    asked by its own id (both answer empty here). First read, then a second read of the same teams. Addendum 46 item
    2: the second read asks the failed one and the empty ones."""
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
    assert first == 12 and second == 4                                       # the failed one and the empty ones
    assert sorted(d.asked_ids[first:]) == ["109", "110", "198", "199"]
    assert "asked by provider id 12 (answered a position 8, answered none 3, failed 1)" in line1
    assert "resolved by lookup 8" in line1 and line1.endswith("kept 8 new") and _kept(198, 199, 109, 110) == {}
    assert line2.endswith("asked by provider id 4 (answered a position 0, answered none 3, failed 1) · from kept "
                          "answers 8 · resolved by lookup 8 · kept 0 new")


def test_a_strict_failure_prints_the_lookup_block_once_and_empty_answer_stays_last(monkeypatch):
    d = Double({"PLI-0": [{"id": 71, "name": "Fails"}], "PLI-1": []}, {"71": "raise"})
    r, _ = _run(monkeypatch, "PLI", d, "--strict")
    lines = r.output.strip().splitlines()
    assert r.exit_code == 1 and sum(x.startswith("POSITION-LOOKUP") for x in lines) == 1
    assert lines[-1].startswith("EMPTY-ANSWER (PLI)")


def test_codex_4248625990_ncaa_makes_no_lookup():
    """Codex 4248625990: NCAA is served by the same adapter; the lookup is NFL's (addendum 44 item 4), so an NCAA
    read asks no /players?id= and keeps nothing."""
    import cli
    assert cli.POSITION_LOOKUP_COMPS == ("NFL",)


def test_codex_4248625990_a_read_outside_the_lookup_comps_asks_nothing(monkeypatch):
    d = Double({"PLJ-0": [{"id": 81, "name": "College Qb"}], "PLJ-1": []}, {"81": _ans(81, position="QB")})
    d.ncaa = True
    r, ts = _run(monkeypatch, "PLJ", d, "--strict")
    assert r.exit_code == 0 and d.calls["players_by_id"] == 0 and _stored(ts) == {"College Qb": None}
    assert "POSITION-LOOKUP" not in r.output and _kept(81) == {}


def test_codex_4248901861_a_rate_limit_stops_the_lookups_for_the_rest_of_the_command(monkeypatch):
    """Codex on #448 (P1): after a RateLimited answer no further /players?id= is made in the command (the closing
    step is time-bound and each further call would be two doomed requests). The ones not asked are failed reads
    under --strict, listed, and nothing is kept for them."""
    d = Double({"PLL-0": [{"id": 1001, "name": "First"}, {"id": 1002, "name": "Second"}],
                "PLL-1": [{"id": 1003, "name": "Third"}]},
               {"1001": "429", "1002": _ans(1002, position="QB"), "1003": _ans(1003, position="WR")})
    r, ts = _run(monkeypatch, "PLL", d, "--strict")
    assert r.exit_code == 1 and d.calls["players_by_id"] == 1, r.output                # one call, then none
    assert "position lookup failed: First (player id 1001): RateLimited" in r.output
    assert "Second (player id 1002): not asked, rate limited earlier in this command (retry after 60s)" in r.output
    assert "Third (player id 1003): not asked, rate limited" in r.output and _kept(1001, 1002, 1003) == {}


# ================================== addendum 47 items 3 and 4: the entries of the injuries read (#454), group (#451) ==
# "In the injuries read an entry is told apart by its provider id. One id listed more than once is one entry, the
# first. Entries that share a name and differ in id are different players: each is kept, and each is resolved by its
# own id, from the roster and then by the lookup, never by a name. An entry with no id is resolved by name as today.
# It is not kept where an entry with an id has its name. Entries with no id that share a name are one entry, the
# first. A name the roster holds more than once resolves nobody by name." (fourth sentence: addendum 48 item 3)
# "A group is not a position. In the roster join, as in the lookup, only the position field resolves a player."

def _rows(team_ids):
    from src.db.schema import Injury
    with session_scope() as s:
        return sorted((i.player_name, i.player_position) for i in s.query(Injury).filter(Injury.team_id.in_(team_ids)))


def _qb_listed(team_id):
    """nfl_predict's qb_listed: the same expression over the stored rows."""
    from src.db.schema import Injury
    from src.walters.qb_audit import is_qb
    with session_scope() as s:
        return [i.player_name for i in s.query(Injury).filter(Injury.team_id == team_id) if is_qb(i.player_position)]


def test_47_two_ids_one_name_the_quarterback_listed_second_is_kept_and_qb_listed_names_him(monkeypatch):
    d = Double({"PLM-0": [{"id": 71, "name": "John Smith"}, {"id": 72, "name": "John Smith"}], "PLM-1": []},
               {"71": _ans(71, position="WR"), "72": _ans(72, position="QB")},
               roster={"PLM-0": [{"id": 77, "name": "John Smith", "position": "RB"}]})   # never by a name
    r, ts = _run(monkeypatch, "PLM", d, "--strict")
    assert r.exit_code == 0, r.output
    assert _rows(ts) == [("John Smith", "QB"), ("John Smith", "WR")] and _qb_listed(ts[0]) == ["John Smith"]
    assert sorted(d.asked_ids) == ["71", "72"]


def test_47_the_roster_gives_one_of_two_ids_the_other_is_asked_by_id(monkeypatch):
    d = Double({"PLN-0": [{"id": 81, "name": "Jim Doe"}, {"id": 82, "name": "Jim Doe"}], "PLN-1": []},
               {"81": _ans(81, position="TE"), "82": _ans(82, position="TE")},
               roster={"PLN-0": [{"id": 81, "name": "Jim Doe", "position": "QB"}]})
    r, ts = _run(monkeypatch, "PLN", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Jim Doe", "QB"), ("Jim Doe", "TE")], r.output
    assert d.asked_ids == ["82"]                                           # 81 from the roster, by its id


def test_47_one_id_listed_twice_is_one_entry_the_first(monkeypatch):
    d = Double({"PLO-0": [{"id": 91, "name": "J. Doe"}, {"id": 91, "name": "John Doe"}], "PLO-1": []},
               {"91": _ans(91, position="LB")})
    r, ts = _run(monkeypatch, "PLO", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("J. Doe", "LB")] and d.calls["players_by_id"] == 1, r.output
    assert "asked by provider id 1 (answered a position 1, answered none 0, failed 0)" in r.output


def test_47_a_name_the_roster_holds_twice_resolves_nobody_by_name_he_is_asked_by_id(monkeypatch):
    d = Double({"PLP-0": [{"id": 93, "name": "Michael Carter"}], "PLP-1": []}, {"93": _ans(93, position="WR")},
               roster={"PLP-0": [{"id": 94, "name": "Michael Carter", "position": "RB"},
                                 {"id": 95, "name": "Michael Carter II", "position": "QB"}]})   # one name, held twice
    r, ts = _run(monkeypatch, "PLP", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Michael Carter", "WR")] and d.asked_ids == ["93"], r.output


def test_47_an_entry_with_no_id_whose_name_another_entry_has_is_not_kept(monkeypatch):
    d = Double({"PLQ-0": [{"id": 96, "name": "Sam Lee"}, {"name": "Sam Lee"}], "PLQ-1": []},
               {"96": _ans(96, position="CB")})
    r, ts = _run(monkeypatch, "PLQ", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Sam Lee", "CB")], r.output


def test_47_an_entry_with_no_id_and_a_name_of_its_own_is_resolved_by_name_as_today(monkeypatch):
    d = Double({"PLR-0": [{"name": "Solo Guy"}], "PLR-1": []}, {},
               roster={"PLR-0": [{"id": 97, "name": "Solo Guy", "position": "QB"}]})
    r, ts = _run(monkeypatch, "PLR", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Solo Guy", "QB")] and d.calls["players_by_id"] == 0, r.output


def test_451_a_group_is_not_a_position_the_roster_row_leaves_him_unresolved_and_he_is_asked(monkeypatch):
    from src.walters.qb_audit import resolve_position, roster_index
    idx = roster_index([{"id": 98, "name": "Grp Only", "group": "Offense"}])
    assert resolve_position({"id": 98, "name": "Grp Only"}, idx) == (None, None)     # NCAA: unresolved, as it is
    d = Double({"PLS-0": [{"id": 98, "name": "Grp Only"}], "PLS-1": []}, {"98": _ans(98, position="QB")},
               roster={"PLS-0": [{"id": 98, "name": "Grp Only", "group": "Offense"}]})
    r, ts = _run(monkeypatch, "PLS", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Grp Only", "QB")] and d.asked_ids == ["98"], r.output


def test_codex_4250343104_an_id_entry_sharing_its_name_with_an_id_less_one_is_never_resolved_by_name(monkeypatch):
    """Codex on #456: the id-less entry is dropped, and the id entry that shares its name is resolved by its own id
    alone; the roster's other player of that name never gives it a position."""
    d = Double({"PLT-0": [{"id": 99, "name": "Kai Moss"}, {"name": "Kai Moss"}], "PLT-1": []},
               {"99": _ans(99, position="S")},
               roster={"PLT-0": [{"id": 500, "name": "Kai Moss", "position": "QB"}]})
    r, ts = _run(monkeypatch, "PLT", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Kai Moss", "S")] and d.asked_ids == ["99"], r.output


def test_codex_4250343097_the_live_qb_audit_takes_the_reads_entries():
    """Codex on #456: nfl-qb-audit --live classifies the same entries the read keeps, resolved the same way."""
    from datetime import datetime
    from src.walters.qb_audit import audit_live
    roster = [{"id": 1, "name": "John Smith", "position": "QB"}]
    inj = [{"player": {"id": 2, "name": "John Smith"}, "status": "Out"},
           {"player": {"id": 3, "name": "John Smith"}, "status": "Out"},
           {"player": {"id": 2, "name": "J. Smith"}, "status": "Out"},          # one id twice: the first
           {"player": {"name": "John Smith"}, "status": "Out"}]                 # no id, shared name: not kept
    a = audit_live(inj, roster, datetime(2026, 10, 12))
    assert [(i["id"], i["position"]) for i in a["items"]] == [(2, None), (3, None)]   # never the roster QB by name


def test_48_two_entries_with_no_id_and_one_name_are_one_entry_the_first_resolved_by_name(monkeypatch):
    """Addendum 48 item 3 (the fourth sentence of addendum 47 item 3 as it now reads): "An entry with no id is
    resolved by name as today. It is not kept where an entry with an id has its name. Entries with no id that share
    a name are one entry, the first." A listed player never becomes nobody."""
    d = Double({"PLU-0": [{"name": "Twin Name"}, {"name": "Twin Name"}], "PLU-1": []}, {},
               roster={"PLU-0": [{"id": 501, "name": "Twin Name", "position": "QB"}]})
    r, ts = _run(monkeypatch, "PLU", d, "--strict")
    assert r.exit_code == 0 and _rows(ts) == [("Twin Name", "QB")] and d.calls["players_by_id"] == 0, r.output
