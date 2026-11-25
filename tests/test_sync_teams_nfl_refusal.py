"""THE NFL MEMBER AT THE TEAM LISTING (ARCHITECT 2026-11-25, addendum 542 item 1(a)), verbatim: "in the college
competition, sync-teams does not link a team that holds a membership of the NFL competition. The listing is refused,
counted on its own receipt line with the provider's team id, and no membership is stored. The team's own row is not
touched: it is the NFL's club and stays so." Item 1(b): "THE SYNC NEVER REMOVES. A membership already stored is not
taken away by sync-teams, on any run." Addendum 545 item 1 Q6, verbatim: "YES: the placeholder is exempt, by its primary
id, in PR-A and in the command's set, each pinned with a test in which the placeholder holds an NFL membership (527 item
1(7))."

The precedent is #1123 (500 Q9 at the match listing, tests/test_nfl_team_refusal.py). This file pins the rule only: no
stored row is deleted or rewritten here (the retirement is PR-B's command). Every test runs a fake provider through the
real IngestionService.sync_teams on a throwaway DB of its own (fresh_db); synthetic names and ids only, no network,
never data/."""
import sys
from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import event, select, text

from src.adapters.normalized import NormalizedTeam
from src.db.schema import Competition, CompetitionTeam, Sport, Team
from src.ingestion import service as svc
from src.ingestion.placeholder import PLACEHOLDER_TEAM_ID
from src.ingestion.service import IngestionService, SyncResult
from tests.test_match_series_fields import fresh_db  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import laptop_routine as lr  # noqa: E402
import sp_run  # noqa: E402

from tests.test_laptop_routine import box, receipts  # noqa: E402,F401

AF = "api_american_football"
SEASON = "2026"


class _Fake:
    source_name = AF

    def __init__(self, rows, sport=Sport.NFL):
        self.rows = list(rows)          # [(provider team id, name), ...]
        self.sport = sport

    def list_teams(self, code, season):
        return [NormalizedTeam(sport=self.sport, name=n, source=AF, source_id=sid, short_name=f"{n} short",
                               tla="TLA", area="USA", venue=f"{n} venue") for sid, n in self.rows]


def _session():
    from src.db.database import session_scope
    return session_scope()


def _comps():
    """The college and the NFL competitions of this throwaway DB: {code: id}."""
    with _session() as s:
        out = {}
        for code in ("NCAA", "NFL"):
            c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.NFL, code=code, name=code, area="USA", type="LEAGUE", external_ids={})
                s.add(c)
                s.flush()
            out[code] = c.id
        return out


def _team(pid, name, memberships=(), ext=None):
    """A stored Sport.NFL team with provider id `pid` (or the external ids `ext`) and its memberships
    [(code, season), ...]: its id."""
    comps = _comps()
    with _session() as s:
        t = Team(sport=Sport.NFL, name=name, short_name=f"{name} kept", tla="OLD", area="Old area", founded=1900,
                 venue=f"{name} old venue", external_ids=dict(ext or {AF: pid}))
        s.add(t)
        s.flush()
        for code, season in memberships:
            s.add(CompetitionTeam(competition_id=comps[code], team_id=t.id, season=season))
        s.flush()
        return t.id


def _raw(tid):
    """Every column of the stored team row as SQLite holds it, external_ids included (the byte-identical check)."""
    with _session() as s:
        return dict(s.execute(text("SELECT * FROM teams WHERE id = :i"), {"i": tid}).mappings().one())


def _memberships(tid):
    """[(code, season)] of the team's stored memberships, sorted; every column of each row too."""
    with _session() as s:
        rows = s.execute(text("SELECT c.code, ct.* FROM competition_teams ct JOIN competitions c "
                              "ON c.id = ct.competition_id WHERE ct.team_id = :i ORDER BY c.code, ct.season"),
                         {"i": tid}).mappings().all()
        return [dict(r) for r in rows]


def _codes(tid):
    return [(m["code"], m["season"]) for m in _memberships(tid)]


def _team_ids_with(pid):
    with _session() as s:
        return [t.id for t in s.execute(select(Team).where(Team.sport == Sport.NFL)).scalars()
                if (t.external_ids or {}).get(AF) == pid]


def _sync(code, rows, season=SEASON) -> SyncResult:
    _comps()
    return IngestionService(_Fake(rows)).sync_teams(code, season)


# ------------------------------------------------------------------------------------------ the refusal -------

def test_an_nfl_member_listed_in_the_college_competition_is_refused_and_its_row_untouched(fresh_db):
    """542 item 1(a): refused, its provider team id on the result, no college membership stored, the team's row byte for
    byte as it was (name, short name, tla, area, venue, external ids: every column), `skipped` counted once."""
    tid = _team("1001", "Pro Club", memberships=[("NFL", SEASON)])
    before, ms_before = _raw(tid), _memberships(tid)
    r = _sync("NCAA", [("1001", "Pro Club As Listed By College")])
    assert r.nfl_member_team_refused == ["1001"]
    assert (r.created, r.updated, r.skipped) == (0, 0, 1)
    assert _raw(tid) == before                                                   # every column, external_ids included
    assert _memberships(tid) == ms_before and _codes(tid) == [("NFL", SEASON)]   # no college membership
    assert _team_ids_with("1001") == [tid]                                       # no team created
    assert r.names_kept == []


def test_the_sync_never_removes_a_stored_college_membership(fresh_db):
    """542 item 1(b), verbatim: "A membership already stored is not taken away by sync-teams, on any run." An NFL member
    that already holds the college membership (the six of 528 item 4(c)) is refused, and that membership is still
    there, every column unchanged; listed again in another season, the same."""
    tid = _team("1002", "Pro Club Two", memberships=[("NCAA", SEASON), ("NFL", SEASON)])
    before, ms_before = _raw(tid), _memberships(tid)
    for season in (SEASON, "2025", SEASON):
        r = _sync("NCAA", [("1002", "Pro Club Two")], season=season)
        assert r.nfl_member_team_refused == ["1002"] and r.skipped == 1, season
        assert _memberships(tid) == ms_before, season
    assert _raw(tid) == before
    assert _codes(tid) == [("NCAA", SEASON), ("NFL", SEASON)]


def test_a_college_team_with_no_nfl_membership_is_linked_as_today(fresh_db):
    _team("1003", "Pro Club Three", memberships=[("NFL", SEASON)])          # the NFL competition holds a member
    tid = _team("2001", "State U", memberships=[("NCAA", "2025")])
    r = _sync("NCAA", [("2001", "State University")])
    assert r.nfl_member_team_refused == [] and (r.created, r.updated, r.skipped) == (0, 1, 0)
    assert _codes(tid) == [("NCAA", "2025"), ("NCAA", SEASON)]
    row = _raw(tid)
    assert (row["name"], row["short_name"], row["tla"]) == ("State University", "State University short", "TLA")


def test_a_team_not_stored_yet_is_created_and_linked_as_today(fresh_db):
    _team("1004", "Pro Club Four", memberships=[("NFL", SEASON)])
    r = _sync("NCAA", [("2002", "New College")])
    assert r.nfl_member_team_refused == [] and (r.created, r.updated, r.skipped) == (1, 0, 0)
    (tid,) = _team_ids_with("2002")
    assert _codes(tid) == [("NCAA", SEASON)]


def test_the_listing_order_is_kept_and_the_others_go_on(fresh_db):
    """Two refused among linked ones: each id once, in listing order; the rest linked or created as today."""
    a = _team("1005", "Pro A", memberships=[("NFL", SEASON)])
    b = _team("1006", "Pro B", memberships=[("NFL", "2024")])
    col = _team("2003", "Old College", memberships=[("NCAA", "2025")])
    r = _sync("NCAA", [("1006", "Pro B"), ("2003", "Old College"), ("2004", "Brand New"), ("1005", "Pro A")])
    assert r.nfl_member_team_refused == ["1006", "1005"]
    assert (r.created, r.updated, r.skipped) == (1, 1, 2)
    assert _codes(a) == [("NFL", SEASON)] and _codes(b) == [("NFL", "2024")]
    assert _codes(col) == [("NCAA", "2025"), ("NCAA", SEASON)]
    (new,) = _team_ids_with("2004")
    assert _codes(new) == [("NCAA", SEASON)]


def test_an_nfl_membership_of_another_season_still_refuses(fresh_db):
    """500 Q9 names no season, and _nfl_members reads every season: a 2019 NFL membership refuses a 2026 listing."""
    tid = _team("1007", "Old Pro", memberships=[("NFL", "2019")])
    before = _raw(tid)
    r = _sync("NCAA", [("1007", "Old Pro")])
    assert r.nfl_member_team_refused == ["1007"] and r.skipped == 1
    assert _raw(tid) == before and _codes(tid) == [("NFL", "2019")]


def test_a_listing_with_no_season_is_refused_too_and_writes_nothing(fresh_db):
    """sync-teams with no --season links nothing but still writes the row; the refusal keeps the row untouched."""
    tid = _team("1008", "Pro Eight", memberships=[("NFL", SEASON)])
    before = _raw(tid)
    r = _sync("NCAA", [("1008", "Pro Eight Renamed")], season=None)
    assert r.nfl_member_team_refused == ["1008"] and (r.updated, r.skipped) == (0, 1)
    assert _raw(tid) == before


def test_a_merged_row_found_by_its_recorded_id_is_refused_by_its_membership(fresh_db):
    """The stored team the listing names is _find_team_by_source's, an id a merge recorded included: the membership is
    the team's, whatever id the listing carried."""
    tid = _team(None, "Merged Pro", memberships=[("NFL", SEASON)], ext={AF: "1009", f"{AF}_also": ["1909"]})
    before = _raw(tid)
    r = _sync("NCAA", [("1909", "Merged Pro")])
    assert r.nfl_member_team_refused == ["1909"] and _raw(tid) == before and _codes(tid) == [("NFL", SEASON)]


def test_the_nfl_competitions_own_sync_teams_is_unchanged(fresh_db):
    tid = _team("1010", "Pro Ten", memberships=[("NFL", "2025")])
    r = _sync("NFL", [("1010", "Pro Ten Renamed"), ("1011", "Expansion Club")])
    assert r.nfl_member_team_refused == [] and (r.created, r.updated, r.skipped) == (1, 1, 0)
    assert _codes(tid) == [("NFL", "2025"), ("NFL", SEASON)] and _raw(tid)["name"] == "Pro Ten Renamed"


# ------------------------------------------------------------------------------------------ the placeholder ---

def test_the_placeholder_holding_an_nfl_membership_is_not_refused_and_is_linked_as_today(fresh_db):
    """545 item 1 Q6, verbatim: "YES: the placeholder is exempt, by its primary id, in PR-A [...] pinned with a test in
    which the placeholder holds an NFL membership (527 item 1(7))." The provider's TBD team (placeholder.
    PLACEHOLDER_TEAM_ID, "345") holds an NFL membership; listed in the college competition it is linked as today."""
    assert PLACEHOLDER_TEAM_ID == "345"
    ph = _team(PLACEHOLDER_TEAM_ID, "TBD", memberships=[("NFL", SEASON), ("NCAA", "2025")])
    with _session() as s:
        ncaa = s.execute(select(Competition).where(Competition.code == "NCAA")).scalar_one()
        assert ph in IngestionService._nfl_members(s, ncaa)                       # it does hold one
    r = _sync("NCAA", [(PLACEHOLDER_TEAM_ID, "TBD")])
    assert r.nfl_member_team_refused == [] and (r.created, r.updated, r.skipped) == (0, 1, 0)
    assert _codes(ph) == [("NCAA", "2025"), ("NCAA", SEASON), ("NFL", SEASON)]


def test_the_exemption_reads_the_primary_id_never_a_recorded_one(fresh_db):
    """By its primary id (545 Q6): a real NFL member that carries 345 only as an id a merge recorded is no placeholder,
    and is refused when a listing names it by its own id or by 345."""
    tid = _team(None, "Pro With Old Id", memberships=[("NFL", SEASON)], ext={AF: "1012", f"{AF}_also": ["345"]})
    before = _raw(tid)
    r = _sync("NCAA", [("1012", "Pro With Old Id"), (PLACEHOLDER_TEAM_ID, "TBD")])
    assert r.nfl_member_team_refused == ["1012", PLACEHOLDER_TEAM_ID]
    assert _raw(tid) == before and _codes(tid) == [("NFL", SEASON)]


# ------------------------------------------------------------------------------------------ no query outside --

def _competition_team_reads(fn):
    from src.db.database import get_engine
    seen = []

    def grab(conn, cursor, statement, params, context, executemany):
        if "competition_teams" in statement and statement.lstrip().upper().startswith("SELECT") \
                and "competitions.code" in statement:
            seen.append(statement)

    eng = get_engine()
    event.listen(eng, "before_cursor_execute", grab)
    try:
        out = fn()
    finally:
        event.remove(eng, "before_cursor_execute", grab)
    return out, seen


def test_no_nfl_membership_query_runs_outside_the_college_competition(fresh_db):
    _team("1013", "Pro Thirteen", memberships=[("NFL", SEASON)])
    _, seen = _competition_team_reads(lambda: _sync("NFL", [("1013", "Pro Thirteen"), ("1014", "Another")]))
    assert seen == []
    _, seen = _competition_team_reads(lambda: _sync("NCAA", [("2005", "A"), ("2006", "B"), ("1013", "P")]))
    assert len(seen) == 1, seen                                                  # read once per run

    class NoQuery:
        def execute(self, *a, **k):
            raise AssertionError("_nfl_members ran a query outside the college competition")

    from types import SimpleNamespace
    assert IngestionService._nfl_members(NoQuery(), SimpleNamespace(code="NFL", sport=Sport.NFL)) == frozenset()


def test_outside_the_college_competition_no_listing_is_looked_up_twice(fresh_db, monkeypatch):
    """The college competition's own lookup is passed on to the upsert; every other competition (and a college run with
    no NFL member stored) looks each listing up once, as before."""
    _team("1015", "Pro Fifteen", memberships=[("NFL", SEASON)])
    calls = []
    real = IngestionService._find_team_by_source

    def counting(s, sport, source, source_id):
        calls.append(source_id)
        return real(s, sport, source, source_id)

    monkeypatch.setattr(IngestionService, "_find_team_by_source", staticmethod(counting))
    _sync("NFL", [("1015", "Pro Fifteen"), ("1016", "X")])
    _sync("NCAA", [("2007", "Y"), ("1015", "Pro Fifteen"), ("2008", "Z")])
    assert calls == ["1015", "1016", "2007", "1015", "2008"]


def test_the_default_is_empty():
    assert SyncResult().nfl_member_team_refused == []


# ------------------------------------------------------------------------------------------ the line ----------

def test_the_line_text():
    assert svc.nfl_member_team_refused_line([]) == "nfl_member_team_refused 0"
    assert svc.nfl_member_team_refused_line(["1001"]) == "nfl_member_team_refused 1: 1001"
    assert svc.nfl_member_team_refused_line(["1006", 1005]) == "nfl_member_team_refused 2: 1006, 1005"


def test_the_log_line_carries_it(fresh_db, caplog):
    import logging
    _team("1017", "Pro Seventeen", memberships=[("NFL", SEASON)])
    with caplog.at_level(logging.INFO, logger=svc.log.name):
        _sync("NCAA", [("1017", "Pro Seventeen")])
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("sync_teams(NCAA): created")]
    assert lines == ["sync_teams(NCAA): created=0 updated=0 skipped=1 nfl_member_team_refused 1: 1017"]
    assert any("REFUSED" in r.getMessage() and "542" in r.getMessage() for r in caplog.records)


def _cli(monkeypatch, rows):
    import cli
    _comps()
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: _Fake(rows))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-teams", "--competition", "NCAA", "--season", SEASON])
    assert res.exit_code == 0, res.output
    return res.output.splitlines()


def test_the_cli_prints_the_line_plainly_after_the_summary_when_n_is_above_zero(fresh_db, monkeypatch):
    _team("1018", "Pro Eighteen", memberships=[("NFL", SEASON)])
    _team("1019", "Pro Nineteen", memberships=[("NFL", SEASON)])
    lines = _cli(monkeypatch, [("1018", "Pro Eighteen"), ("2009", "College"), ("1019", "Pro Nineteen")])
    i = next(k for k, ln in enumerate(lines) if ln.startswith("✓ Teams (NCAA): "))
    assert sp_run.TEAMS_LINE.match(lines[i]).groupdict() == {"code": "NCAA", "created": "1", "updated": "0",
                                                             "skipped": "2"}
    assert lines[i + 1] == "nfl_member_team_refused 2: 1018, 1019"
    assert sum(1 for ln in lines if ln.startswith("nfl_member_team_refused")) == 1


def test_the_cli_prints_no_line_at_zero(fresh_db, monkeypatch):
    _team("1020", "Pro Twenty", memberships=[("NFL", SEASON)])
    lines = _cli(monkeypatch, [("2010", "College")])
    assert not any("nfl_member_team_refused" in ln for ln in lines), lines


def test_the_admin_sync_teams_job_carries_the_line(fresh_db, monkeypatch):
    """The summary's text only, with the admin's router stubbed. The admin's own router sends every non-MLB code
    to the soccer adapter, which raises on NCAA before sync_teams runs, so this line reaches the admin only once
    the admin routes the college competition (#1152, for the architect's ruling)."""
    from src.web.routes import admin
    _team("1021", "Pro Twenty-One", memberships=[("NFL", SEASON)])
    _comps()
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda c: _Fake([("1021", "P"), ("2011", "C")]))
    out = admin._job_sync_teams(competition_code="NCAA", season=SEASON)
    assert out == "created=1 updated=0 skipped=1 · nfl_member_team_refused 1: 1021", out
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda c: _Fake([("2012", "C2")]))
    out = admin._job_sync_teams(competition_code="NCAA", season=SEASON)
    assert out == "created=1 updated=0 skipped=0", out


# ------------------------------------------------------------------------------------------ the readers -------

def test_sp_run_sync_counts_reads_the_line_and_every_such_line_adds():
    got = sp_run.sync_counts(["✓ Teams (NCAA): created=1 updated=700 skipped=2",
                              "nfl_member_team_refused 2: 1018, 1019"])
    assert got["nfl_member_team_refused"] == {"n": 2, "ids": ["1018", "1019"]}
    assert got["teams"] == {"created": 1, "updated": 700, "skipped": 2}
    two = sp_run.sync_counts(["nfl_member_team_refused 1: 7", "nfl_member_team_refused 2: 8, 9"])
    assert two["nfl_member_team_refused"] == {"n": 3, "ids": ["7", "8", "9"]}
    assert "nfl_member_team_refused" not in sp_run.sync_counts(["✓ Teams (NCAA): created=0 updated=1 skipped=0"])
    assert "nfl_team_refused" not in two                                         # the match listing's line is its own
    assert "nfl_member_team_refused" not in sp_run.sync_counts(["nfl_team_refused 1: 61234"])
    line = svc.nfl_member_team_refused_line(["1018"])
    assert any(r.match(line) for r in sp_run._SYNC_LINES)
    assert any(r.match(line) for r in lr._COUNT_LINES)


def test_the_laptop_routine_echoes_and_counts_the_line_under_the_ncaa_sync_teams_step(box, capsys):
    """Step 8 is the NCAA sync-teams: its line is echoed under the step line and carried on the step's receipt."""
    def answer(argv):
        if argv[:3] == ["sync-teams", "--competition", "NCAA"]:
            return (["✓ Teams (NCAA): created=0 updated=700 skipped=2", "nfl_member_team_refused 2: 1018, 1019"], 0)
        return (["done"], 0)
    box.answer = staticmethod(answer)
    lr.main([])
    out = capsys.readouterr().out.splitlines()
    i = out.index(next(x for x in out if x.startswith("8 · ")))
    assert out[i + 1:i + 3] == ["    > ✓ Teams (NCAA): created=0 updated=700 skipped=2",
                                "    > nfl_member_team_refused 2: 1018, 1019"]
    step = next(r for r in receipts(box.tmp) if r["kind"] == "step" and r["step"] == "8")
    assert step["sync"]["nfl_member_team_refused"] == {"n": 2, "ids": ["1018", "1019"]}
    assert step["sync"]["teams"] == {"created": 0, "updated": 700, "skipped": 2}
