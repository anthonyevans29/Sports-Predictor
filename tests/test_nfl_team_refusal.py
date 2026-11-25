"""THE NFL-TEAM REFUSAL (ARCHITECT 2026-11-24, addendum 500 Q9), verbatim: "in the college competition, a listing either
of whose teams holds a membership of the NFL competition is refused at create and at update, counted with its id, never
stored." Item 3(a): "THE NFL-TEAM REFUSAL of Q9, with its count line".

The finding is addendum 493 item 2(d) (match 66178, an NCAA row holding two NFL teams); 500 item 1(c) reads it as the
provider's error. This file pins the rule only: no stored row is deleted or rewritten here.

Throwaway DB only (tests/conftest.py); the provider is a fake adapter, no network. The "NCAA" and "NFL" competitions
are the shared session DB's (get-or-created, never created outright). Season "2093" and kickoffs in 2093, so no test
that reads the shared NFL competition's 2026 window sees these rows or memberships."""
import itertools
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from click.testing import CliRunner
from sqlalchemy import event, select, text

from src.adapters.normalized import NormalizedMatch
from src.db.database import get_engine, init_db, session_scope
from src.db.schema import Competition, CompetitionTeam, Match, MatchStatus, Result, Sport, Team
from src.ingestion import service as svc
from src.ingestion.service import IngestionService, SyncResult
from src.timeutil import utc_now_naive

AF = "api_american_football"
SEASON = "2093"
KICK = datetime(2093, 10, 3, 19, 0)
_seq = itertools.count(1)


class Listing:
    source_name = AF

    def __init__(self, listing=()):
        self.listing = list(listing)

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        return list(self.listing)


def _comp(s, code):
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.NFL, code=code, name=code, area="x", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _teams(n, nfl_member, nfl_season=SEASON):
    """`n` new Sport.NFL teams, [(team id, provider id)]. Every one holds a 2093 membership of the college competition
    (a real college team holds one; so do 66178's two NFL teams, 500 Q9: "the bad row's own teams hold one"); each
    `nfl_member` one also holds a membership of the NFL competition, in `nfl_season`."""
    init_db()
    out = []
    with session_scope() as s:
        nfl = _comp(s, "NFL")
        ncaa = _comp(s, "NCAA")
        for _ in range(n):
            pid = f"ntr-{next(_seq)}-{utc_now_naive():%H%M%S%f}"
            t = Team(sport=Sport.NFL, name=f"Team {pid}", external_ids={AF: pid})
            s.add(t)
            s.flush()
            s.add(CompetitionTeam(competition_id=ncaa.id, team_id=t.id, season=SEASON))
            if nfl_member:
                s.add(CompetitionTeam(competition_id=nfl.id, team_id=t.id, season=nfl_season))
            s.flush()
            out.append((t.id, pid))
    return out


def _gid():
    return str(93_000_000 + next(_seq) * 1000 + int(utc_now_naive().strftime("%f")) % 1000)


def _stored(sid, home, away, when=KICK, status=MatchStatus.FINISHED, season=SEASON, **scores):
    init_db()
    with session_scope() as s:
        c = _comp(s, "NCAA")
        m = Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=when, status=status,
                  status_raw="FT" if status == MatchStatus.FINISHED else "NS", home_team_id=home, away_team_id=away,
                  external_ids={AF: sid}, **scores)
        s.add(m)
        s.flush()
        return m.id


def _nm(code, sid, home_pid, away_pid, when=KICK, status=MatchStatus.FINISHED, **scores):
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season=SEASON, utc_date=when, status=status,
                           home_team_source_id=home_pid, away_team_source_id=away_pid, source=AF, source_id=sid,
                           status_raw="FT" if status == MatchStatus.FINISHED else "NS", **scores)


def _raw(mid):
    """Every column of the stored row as SQLite holds it, external_ids included (the byte-identical check)."""
    with session_scope() as s:
        return dict(s.execute(text("SELECT * FROM matches WHERE id = :i"), {"i": mid}).mappings().one())


def _rows_with(code, sid):
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        return [m.id for m in s.execute(select(Match).where(Match.competition_id == c.id)).scalars()
                if (m.external_ids or {}).get(AF) == sid]


def _sync(code, listing):
    return IngestionService(Listing(listing)).sync_matches(code, season=SEASON)


# ---------------------------------------------------------------------------- at create


def test_a_listing_with_an_nfl_member_at_home_is_refused_at_create():
    (nfl_t, nfl_pid), = _teams(1, nfl_member=True)
    (col, col_pid), = _teams(1, nfl_member=False)
    sid = _gid()
    r = _sync("NCAA", [_nm("NCAA", sid, nfl_pid, col_pid, home_score=31, away_score=7, full_time_result=Result.HOME)])
    assert _rows_with("NCAA", sid) == []                                     # never stored
    assert (r.created, r.updated, r.skipped) == (0, 0, 1)
    assert r.nfl_team_refused == [sid] and r.teams_mismatch_refused == []


def test_either_side_is_enough_the_away_team_alone():
    (col, col_pid), = _teams(1, nfl_member=False)
    (nfl_t, nfl_pid), = _teams(1, nfl_member=True)
    sid = _gid()
    r = _sync("NCAA", [_nm("NCAA", sid, col_pid, nfl_pid, status=MatchStatus.SCHEDULED)])
    assert _rows_with("NCAA", sid) == []
    assert (r.created, r.skipped) == (0, 1) and r.nfl_team_refused == [sid]


def test_an_nfl_membership_of_another_season_is_enough():
    """Q9 names no season ("holds a membership of the NFL competition"); 500 item 4 counts "over every season". A 2092
    NFL membership refuses a 2093 college listing."""
    (nfl_t, nfl_pid), = _teams(1, nfl_member=True, nfl_season="2092")
    (col, col_pid), = _teams(1, nfl_member=False)
    sid = _gid()
    r = _sync("NCAA", [_nm("NCAA", sid, col_pid, nfl_pid, status=MatchStatus.SCHEDULED)])
    assert _rows_with("NCAA", sid) == []
    assert (r.created, r.skipped) == (0, 1) and r.nfl_team_refused == [sid]


def test_a_caller_with_no_cache_reads_the_membership_itself():
    """_upsert_match with cache=None (sync_matches always prefetches; this is the fallback)."""
    (nfl_t, nfl_pid), = _teams(1, nfl_member=True)
    (col, col_pid), = _teams(1, nfl_member=False)
    sid = _gid()
    result = SyncResult()
    with session_scope() as s:
        ncaa = s.execute(select(Competition).where(Competition.code == "NCAA")).scalar_one()
        got = IngestionService(Listing())._upsert_match(
            s, _nm("NCAA", sid, nfl_pid, col_pid, status=MatchStatus.SCHEDULED), ncaa, result, cache=None)
    assert got is None
    assert result.nfl_team_refused == [sid] and result.skipped == 1
    assert _rows_with("NCAA", sid) == []


# ---------------------------------------------------------------------------- at update (the 66178 shape)


def test_a_stored_row_holding_two_nfl_members_is_not_updated_by_the_same_pair():
    (a, ap), (b, bp) = _teams(2, nfl_member=True)
    sid = _gid()
    mid = _stored(sid, a, b, home_score=20, away_score=17, full_time_result=Result.HOME)
    before = _raw(mid)
    r = _sync("NCAA", [_nm("NCAA", sid, ap, bp, home_score=27, away_score=24, full_time_result=Result.HOME)])
    assert _raw(mid) == before                                               # every column, external_ids included
    assert (r.updated, r.skipped) == (0, 1)
    assert r.nfl_team_refused == [sid] and r.teams_mismatch_refused == []
    assert r.nfl_team_refused_rows == [mid]


def test_a_stored_row_listed_with_its_nfl_pair_reversed_writes_nothing():
    """The reverse of the stored pair is not a mismatch: the listing is refused, so no update and no key."""
    (a, ap), (b, bp) = _teams(2, nfl_member=True)
    sid = _gid()
    mid = _stored(sid, a, b, home_score=20, away_score=17, full_time_result=Result.HOME)
    before = _raw(mid)
    r = _sync("NCAA", [_nm("NCAA", sid, bp, ap, home_score=17, away_score=20, full_time_result=Result.AWAY)])
    assert _raw(mid) == before
    assert (r.updated, r.skipped) == (0, 1)
    assert r.nfl_team_refused == [sid] and r.teams_mismatch_refused == [] and r.orientation_reversed == []
    assert r.nfl_team_refused_rows == [mid]


def test_a_stored_row_holding_two_nfl_members_listed_with_two_other_nfl_teams_writes_nothing():
    """493 item 2(d): "listed today under the same id with two other NFL teams". No provider_orientation key either
    (whether 297 C(ii)'s key is written here waits on the architect, #1123 item 1); the row is named for STRICT."""
    (a, ap), (b, bp), (c, cp), (d, dp) = _teams(4, nfl_member=True)
    sid = _gid()
    mid = _stored(sid, a, b, home_score=20, away_score=17, full_time_result=Result.HOME)
    before = _raw(mid)
    r = _sync("NCAA", [_nm("NCAA", sid, cp, dp, home_score=10, away_score=13, full_time_result=Result.AWAY)])
    assert _raw(mid) == before
    assert (r.created, r.updated, r.skipped) == (0, 0, 1)
    assert r.nfl_team_refused == [sid] and r.teams_mismatch_refused == []
    assert r.nfl_team_refused_rows == [mid]
    assert _rows_with("NCAA", sid) == [mid]                                  # the listing stored nowhere


def test_a_row_created_earlier_in_the_same_run_is_named_by_its_id_never_none():
    """One listing names the same id twice: a college pair (row R created, unflushed under autoflush=False), then two
    NFL members. The refusal's flush gives R its id, so the receipts name R, never None (the #884 class)."""
    (h, hp), (a, ap) = _teams(2, nfl_member=False)
    (c, cp), (d, dp) = _teams(2, nfl_member=True)
    sid = _gid()
    r = _sync("NCAA", [_nm("NCAA", sid, hp, ap, status=MatchStatus.SCHEDULED),
                       _nm("NCAA", sid, cp, dp, status=MatchStatus.SCHEDULED)])
    (mid,) = _rows_with("NCAA", sid)
    assert (r.created, r.skipped) == (1, 1) and r.nfl_team_refused == [sid]
    assert r.nfl_team_refused_rows == [mid] and r.teams_mismatch_refused == []
    assert json.loads(_raw(mid)["external_ids"]) == {AF: sid}


def test_a_stored_row_of_another_season_carrying_the_id_is_untouched():
    """Addendum 310 item 3(a) (#906): a row of another season carrying the listed id is another game; the refused
    listing reads nothing against it, writes no key on it and names it nowhere."""
    (a, ap), (b, bp), (c, cp), (d, dp) = _teams(4, nfl_member=True)
    sid = _gid()
    mid = _stored(sid, a, b, season="2092", when=KICK - timedelta(days=365), home_score=20, away_score=17,
                  full_time_result=Result.HOME)
    before = _raw(mid)
    r = _sync("NCAA", [_nm("NCAA", sid, cp, dp, home_score=10, away_score=13, full_time_result=Result.AWAY)])
    assert _raw(mid) == before
    assert _rows_with("NCAA", sid) == [mid]
    assert (r.created, r.updated, r.skipped) == (0, 0, 1)
    assert r.nfl_team_refused == [sid] and r.teams_mismatch_refused == [] and r.nfl_team_refused_rows == []
    assert r.provider_id_collision == []


# ---------------------------------------------------------------------------- the re-keys


def test_the_12h_rekey_is_refused_for_an_nfl_member_pair():
    (a, ap), (b, bp) = _teams(2, nfl_member=True)
    old_sid, new_sid = _gid(), _gid()
    mid = _stored(old_sid, a, b, when=KICK, status=MatchStatus.SCHEDULED)
    before = _raw(mid)
    r = _sync("NCAA", [_nm("NCAA", new_sid, ap, bp, when=KICK + timedelta(hours=2), status=MatchStatus.SCHEDULED)])
    assert _raw(mid) == before                                               # no _prev, the id unchanged
    assert _rows_with("NCAA", new_sid) == []
    assert (r.rekeyed, r.rekey_refused, r.created) == (0, 0, 0)
    assert r.nfl_team_refused == [new_sid]


def test_the_placeholder_rekey_is_refused_for_an_nfl_member_pair():
    (a, ap), (b, bp) = _teams(2, nfl_member=True)
    old_sid, new_sid = _gid(), _gid()
    placeholder = datetime(2093, 12, 5, 4, 0)                                # the 04:00Z placeholder kickoff
    mid = _stored(old_sid, a, b, when=placeholder, status=MatchStatus.SCHEDULED)
    before = _raw(mid)
    r = _sync("NCAA", [_nm("NCAA", new_sid, ap, bp, when=placeholder + timedelta(hours=18),
                           status=MatchStatus.SCHEDULED)])                   # a real kickoff within 24h, past 12h
    assert _raw(mid) == before
    assert _rows_with("NCAA", new_sid) == []
    assert (r.rekeyed, r.rekey_refused, r.created) == (0, 0, 0)
    assert r.nfl_team_refused == [new_sid]


# ---------------------------------------------------------------------------- unchanged


def test_a_college_listing_with_no_nfl_member_creates_and_updates_as_today():
    _teams(1, nfl_member=True)                                               # the NFL competition holds members
    (h, hp), (a, ap) = _teams(2, nfl_member=False)
    sid = _gid()
    r1 = _sync("NCAA", [_nm("NCAA", sid, hp, ap, status=MatchStatus.SCHEDULED)])
    assert (r1.created, r1.updated, r1.skipped) == (1, 0, 0) and r1.nfl_team_refused == []
    (mid,) = _rows_with("NCAA", sid)
    r2 = _sync("NCAA", [_nm("NCAA", sid, hp, ap, home_score=21, away_score=14, full_time_result=Result.HOME)])
    assert (r2.created, r2.updated, r2.skipped) == (0, 1, 0) and r2.nfl_team_refused == []
    assert _raw(mid)["home_score"] == 21 and _rows_with("NCAA", sid) == [mid]


def test_the_nfl_competition_sync_is_unchanged():
    (h, hp), (a, ap) = _teams(2, nfl_member=True)
    sid = _gid()
    r1 = _sync("NFL", [_nm("NFL", sid, hp, ap, status=MatchStatus.SCHEDULED)])
    assert (r1.created, r1.skipped) == (1, 0) and r1.nfl_team_refused == []
    r2 = _sync("NFL", [_nm("NFL", sid, hp, ap, home_score=24, away_score=10, full_time_result=Result.HOME)])
    assert (r2.created, r2.updated, r2.skipped) == (0, 1, 0) and r2.nfl_team_refused == []

    class NoQuery:
        def execute(self, *a, **k):
            raise AssertionError("_nfl_members ran a query outside the college competition")

    assert IngestionService._nfl_members(NoQuery(), SimpleNamespace(code="NFL", sport=Sport.NFL)) == frozenset()


def test_the_membership_is_read_once_per_run():
    (n1, n1p), = _teams(1, nfl_member=True)
    (h, hp), (a, ap), (c, cp) = _teams(3, nfl_member=False)
    listing = [_nm("NCAA", _gid(), hp, ap, status=MatchStatus.SCHEDULED),
               _nm("NCAA", _gid(), n1p, cp, when=KICK + timedelta(days=7), status=MatchStatus.SCHEDULED),
               _nm("NCAA", _gid(), cp, hp, when=KICK + timedelta(days=14), status=MatchStatus.SCHEDULED)]
    seen = []

    def grab(conn, cursor, statement, params, context, executemany):
        if "competition_teams" in statement:
            seen.append(statement)

    eng = get_engine()
    event.listen(eng, "before_cursor_execute", grab)
    try:
        r = _sync("NCAA", listing)
    finally:
        event.remove(eng, "before_cursor_execute", grab)
    assert len(seen) == 1, seen
    assert (r.created, r.skipped) == (2, 1) and r.nfl_team_refused == [listing[1].source_id]


def test_the_default_is_empty():
    assert SyncResult().nfl_team_refused == []


# ---------------------------------------------------------------------------- the count line (3(a))


def test_the_line_text():
    assert svc.nfl_team_refused_line([]) == "nfl_team_refused 0"
    assert svc.nfl_team_refused_line(["1", "2"]) == "nfl_team_refused 2: 1, 2"


def _cli(monkeypatch, listing):
    import cli

    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: Listing(listing))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "NCAA", "--season", SEASON])
    assert res.exit_code == 0, res.output
    return res.output


def test_the_cli_prints_the_count_line_when_n_is_above_zero(monkeypatch):
    (nfl_t, nfl_pid), = _teams(1, nfl_member=True)
    (col, col_pid), = _teams(1, nfl_member=False)
    sid = _gid()
    out = _cli(monkeypatch, [_nm("NCAA", sid, col_pid, nfl_pid, status=MatchStatus.SCHEDULED)])
    lines = out.splitlines()
    assert f"nfl_team_refused 1: {sid}" in lines
    assert lines[-1].startswith("orientation_reversed")                      # the scores-by-team line stays last
    assert _rows_with("NCAA", sid) == []


def test_the_cli_prints_no_count_line_at_zero(monkeypatch):
    (h, hp), (a, ap) = _teams(2, nfl_member=False)
    out = _cli(monkeypatch, [_nm("NCAA", _gid(), hp, ap, status=MatchStatus.SCHEDULED)])
    assert "nfl_team_refused" not in out


def test_the_admin_sync_job_carries_the_count_line(monkeypatch):
    from src.web.routes import admin

    (nfl_t, nfl_pid), = _teams(1, nfl_member=True)
    (col, col_pid), (col2, col2_pid) = _teams(2, nfl_member=False)
    sid = _gid()
    monkeypatch.setattr(admin, "_adapter_for_competition",
                        lambda c: Listing([_nm("NCAA", sid, nfl_pid, col_pid, status=MatchStatus.SCHEDULED)]))
    out = admin._job_sync_matches(competition_code="NCAA", season=SEASON, seasons=0)
    assert f" · nfl_team_refused 1: {sid}" in out, out
    monkeypatch.setattr(admin, "_adapter_for_competition",
                        lambda c: Listing([_nm("NCAA", _gid(), col_pid, col2_pid, status=MatchStatus.SCHEDULED)]))
    out = admin._job_sync_matches(competition_code="NCAA", season=SEASON, seasons=0)
    assert "nfl_team_refused" not in out, out


class _Refusing:
    """A stand-in service: every sync_matches call returns one NFL-team refusal, no DB rows."""

    def __init__(self, *a, **k):
        pass

    def sync_matches(self, code, season=None, **k):
        return SyncResult(skipped=1, nfl_team_refused=[f"r-{season}"])


def test_the_cli_seasons_loop_prints_the_count_line_per_season(monkeypatch):
    import cli

    monkeypatch.setattr(cli, "IngestionService", _Refusing)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: Listing())
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "NCAA", "--seasons", "2"])
    assert res.exit_code == 0, res.output
    assert sum(1 for ln in res.output.splitlines() if ln.startswith("nfl_team_refused 1: r-")) == 2, res.output


def test_the_admin_seasons_job_adds_the_count_over_every_season(monkeypatch):
    from src.web.routes import admin

    monkeypatch.setattr(admin, "IngestionService", _Refusing)
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda c: Listing())
    out = admin._job_sync_matches(competition_code="NCAA", season=None, seasons=2)
    assert " · nfl_team_refused 2: r-" in out, out


def test_strict_reports_a_row_refused_by_q9_as_refused_never_as_absent(monkeypatch):
    """#1123 review (Codex P2): --match-ids naming stored college rows whose listings Q9 refused. The 66178 shape (a
    pair that is neither the stored one nor its reverse) and the same pair are both on Q9's own REFUSED line; a row
    the listing does not carry is the only one "not in the provider's answer". Exit 1."""
    import cli

    (a, ap), (b, bp), (c, cp), (d, dp) = _teams(4, nfl_member=True)
    mis_sid, same_sid, gone_sid = _gid(), _gid(), _gid()
    mis = _stored(mis_sid, a, b)
    same = _stored(same_sid, c, d, when=KICK + timedelta(days=7))
    gone = _stored(gone_sid, a, d, when=KICK + timedelta(days=14))
    monkeypatch.setattr(cli, "_adapter_for_competition",
                        lambda code: Listing([_nm("NCAA", mis_sid, cp, dp),
                                              _nm("NCAA", same_sid, cp, dp, when=KICK + timedelta(days=7))]))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda code: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "NCAA", "--season", SEASON,
                                       "--match-ids", f"{mis},{same},{gone}"])
    assert res.exit_code == 1, res.output
    lines = res.output.splitlines()
    assert any(x.startswith("✗ STRICT: 1 of 3 named game(s) not in the provider's answer") and x.endswith(f"match {gone}")
               for x in lines), res.output
    assert not any("provider_orientation mismatch written" in x for x in lines), res.output
    assert (f"✗ STRICT: 2 of 3 named game(s) REFUSED (a listed team holds a membership of the NFL competition, "
            f"addendum 500 Q9; nothing written): match {mis}, match {same}") in lines, res.output
    assert f"nfl_team_refused 2: {mis_sid}, {same_sid}" in lines, res.output


def test_strict_split_reads_the_q9_rows():
    import cli

    r = SyncResult(teams_mismatch_refused=[1], nfl_team_refused_rows=[1, 2])
    refused, missing = cli._strict_split(r, {1, 2, 3}, [1, 2, 3])
    assert (refused, missing) == ([1], [2, 3])
    assert cli._strict_nfl_split(r, missing) == ([2], [3])
    assert cli._strict_nfl_split(SimpleNamespace(), [3]) == ([], [3])       # a stand-in result: unchanged
