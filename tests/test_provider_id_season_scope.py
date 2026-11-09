"""THE PROVIDER ID IS THE SEASON'S (ARCHITECT 2026-11-09, addendum 310 item 3; #902). Item 3(d), verbatim: "a unit
test on the 18216 case: a 2025 FINISHED row with id 18216, a 2026 listing with id 18216 and the pair reversed → the 2025
row byte-identical after the sync, a new 2026 row created with the LISTING's home/away, `provider_id_collision 1`
printed".

Also: the same-season update path unchanged; an annual rematch (the same pair next season) is never a re-key target
(item 3(c)); the orientation chain never fires across seasons (item 3(e)); NFL the same (the same provider). Throwaway
DB only (tests/conftest.py); the provider is a fake adapter, no network."""
import itertools
from datetime import datetime

from click.testing import CliRunner
from sqlalchemy import select, text

from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Result, Sport, Team
from src.ingestion import service as svc
from src.ingestion.service import IngestionService, SyncResult
from src.timeutil import utc_now_naive

AF = "api_american_football"
_seq = itertools.count(1)
KICK_2025 = datetime(2025, 11, 2, 2, 15)          # 36454 on 10-09 (item 1)
KICK_2026 = datetime(2026, 10, 31, 19, 45)        # the 2026 Cincinnati-Utah listing (item 1)


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


def _pair():
    """Two new NFL-family teams (Utah, Cincinnati in the 18216 case): [(team id, provider id)]."""
    init_db()
    out = []
    with session_scope() as s:
        for name in ("Utah", "Cincinnati"):
            pid = f"pis-{next(_seq)}-{utc_now_naive():%H%M%S%f}"
            t = Team(sport=Sport.NFL, name=f"{name} {pid}", external_ids={AF: pid})
            s.add(t)
            s.flush()
            out.append((t.id, pid))
    return out


def _gid():
    return str(18216_000 + next(_seq) * 1000 + int(utc_now_naive().strftime("%f")) % 1000)


def _stored(code, sid, home, away, season, when, status=MatchStatus.FINISHED, ext=None, **scores):
    init_db()
    with session_scope() as s:
        c = _comp(s, code)
        m = Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=when, status=status,
                  status_raw="FT" if status == MatchStatus.FINISHED else "NS", home_team_id=home, away_team_id=away,
                  external_ids=ext if ext is not None else {AF: sid}, **scores)
        s.add(m)
        s.flush()
        return m.id


def _nm(code, sid, home_pid, away_pid, season="2026", when=KICK_2026, status=MatchStatus.FINISHED, **scores):
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season=season, utc_date=when, status=status,
                           home_team_source_id=home_pid, away_team_source_id=away_pid, source=AF, source_id=sid,
                           status_raw="FT" if status == MatchStatus.FINISHED else "NS", **scores)


def _raw(mid):
    """Every column of the stored row as SQLite holds it, external_ids included (the byte-identical check)."""
    with session_scope() as s:
        return dict(s.execute(text("SELECT * FROM matches WHERE id = :i"), {"i": mid}).mappings().one())


def _rows_with(code, sid):
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        return [dict(id=m.id, season=m.season, home=m.home_team_id, away=m.away_team_id, home_score=m.home_score,
                     away_score=m.away_score, ftr=m.full_time_result, utc=m.utc_date, ext=dict(m.external_ids or {}))
                for m in s.execute(select(Match).where(Match.competition_id == c.id).order_by(Match.id)).scalars()
                if (m.external_ids or {}).get(AF) == sid]


def _sync(code, listing, season="2026"):
    return IngestionService(Listing(listing)).sync_matches(code, season=season)


def _case_18216(code):
    """A 2025 FINISHED row (Utah home v Cincinnati away, 45-14, the id) and the 2026 listing of the same id with the
    pair reversed (Cincinnati home, Utah away, 25-49, 2026-10-31)."""
    (utah, utah_pid), (cin, cin_pid) = _pair()
    sid = _gid()
    old = _stored(code, sid, utah, cin, "2025", KICK_2025, home_score=45, away_score=14,
                  full_time_result=Result.HOME)
    listing = _nm(code, sid, cin_pid, utah_pid, home_score=25, away_score=49, full_time_result=Result.AWAY)
    return old, sid, (utah, utah_pid), (cin, cin_pid), listing


def _assert_collision_case(code):
    old, sid, (utah, _), (cin, _), listing = _case_18216(code)
    before = _raw(old)
    r = _sync(code, [listing])
    assert _raw(old) == before                                   # every column, external_ids included
    rows = _rows_with(code, sid)
    assert [x["id"] for x in rows][0] == old and len(rows) == 2
    new = rows[1]
    assert (new["season"], new["home"], new["away"]) == ("2026", cin, utah)        # the LISTING's home/away
    assert (new["home_score"], new["away_score"], new["ftr"]) == (25, 49, Result.AWAY)
    assert new["utc"] == KICK_2026 and new["ext"] == {AF: sid}                       # no provider_orientation key
    assert (r.created, r.updated, r.skipped) == (1, 0, 0)
    assert r.provider_id_collision == [(old, "2025", sid)]
    assert r.orientation_reversed == [] and r.teams_mismatch_refused == []         # the chain never fired
    assert svc.provider_id_collision_line(r.provider_id_collision) == f"provider_id_collision 1: {old} (2025) ← {sid}"
    return old, sid, new["id"]


# ---------------------------------------------------------------------------- item 3(a)/(b)/(d): the 18216 case


def test_the_18216_case_ncaa_creates_its_own_row_and_leaves_2025_byte_identical():
    _assert_collision_case("PISNCAA")


def test_the_18216_case_nfl_the_same():
    _assert_collision_case("PISNFL")


def test_a_second_sync_updates_the_2026_row_and_still_names_the_2025_row():
    code = "PISAGAIN"
    old, sid, new_id = _assert_collision_case(code)
    before = _raw(old)
    with session_scope() as s:
        m = s.get(Match, new_id)
        home, away = m.home_team.external_ids[AF], m.away_team.external_ids[AF]
    again = _nm(code, sid, home, away, home_score=25, away_score=49, full_time_result=Result.AWAY)
    r = _sync(code, [again])
    assert (r.created, r.updated) == (0, 1)
    assert r.provider_id_collision == [(old, "2025", sid)]             # a stored row of another season carries the id
    assert _raw(old) == before and len(_rows_with(code, sid)) == 2


def test_the_cli_prints_the_collision_line(monkeypatch):
    import cli

    code = "PISCLI"
    old, sid, _u, _c, listing = _case_18216(code)
    before = _raw(old)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: Listing([listing]))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", code, "--season", "2026"])
    assert res.exit_code == 0, res.output
    lines = res.output.splitlines()
    assert f"provider_id_collision 1: {old} (2025) ← {sid}" in lines
    assert lines[-1].startswith("orientation_reversed 0")             # the scores-by-team line stays the tail's last
    assert _raw(old) == before


def test_the_cli_prints_zero_collisions():
    assert svc.provider_id_collision_line([]) == "provider_id_collision 0"


# ---------------------------------------------------------------------------- the same-season update path


def test_the_same_season_row_is_updated_as_before():
    code = "PISSAME"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    mid = _stored(code, sid, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = _sync(code, [_nm(code, sid, hp, ap, home_score=31, away_score=17, full_time_result=Result.HOME)])
    assert (r.created, r.updated, r.skipped) == (0, 1, 0) and r.provider_id_collision == []
    row = _rows_with(code, sid)
    assert len(row) == 1 and row[0]["id"] == mid
    assert (row[0]["home_score"], row[0]["away_score"], row[0]["ftr"]) == (31, 17, Result.HOME)


def test_a_same_season_reversed_listing_still_reaches_the_orientation_chain():
    """Item 3(e): a reversed pair on a row of the SAME season is a reversal (the chain, #884, unchanged)."""
    code = "PISREV"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    mid = _stored(code, sid, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = _sync(code, [_nm(code, sid, ap, hp, home_score=25, away_score=49, full_time_result=Result.AWAY)])
    assert r.orientation_reversed == [mid] and r.provider_id_collision == [] and r.created == 0
    row = _rows_with(code, sid)[0]
    assert (row["home"], row["away"], row["home_score"], row["away_score"]) == (h, a, 49, 25)
    assert row["ext"].get("provider_orientation") == "reversed"


def test_the_orientation_chain_does_not_fire_across_seasons_even_with_a_same_season_row_absent():
    """Item 3(e): across seasons the reversed pair is a collision and never reaches the chain: no reversal recorded,
    no provider_orientation key written on the older row (it stays byte-identical)."""
    code = "PISCHAIN"
    old, sid, _u, _c, listing = _case_18216(code)
    before = _raw(old)
    r = _sync(code, [listing])
    assert r.orientation_reversed == [] and r.teams_mismatch_refused == []
    assert "provider_orientation" not in _raw(old)["external_ids"] and _raw(old) == before


def test_an_unknown_team_listing_never_marks_another_seasons_row():
    """_mismatch_on_unknown_team (addendum 297 C(i)) reads only the listing's own season's row."""
    code = "PISUNK"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    old = _stored(code, sid, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    before = _raw(old)
    r = _sync(code, [_nm(code, sid, "pis-not-in-db", hp)])
    assert r.teams_mismatch_refused == [] and r.skipped == 1 and _raw(old) == before
    # Codex on #906: the unknown-team branch does the upsert's own accounting, so the cross-season collision is
    # counted there too (the row stays untouched; the skip is counted once)
    assert r.provider_id_collision == [(old, "2025", sid)]


def test_an_unknown_team_listing_with_no_season_is_refused_once():
    """The unknown-team branch counts an unknown-season refusal on the receipt, and the skip once (Codex on #906)."""
    code = "PISUNKS"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    old = _stored(code, sid, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    before = _raw(old)
    nm = _nm(code, sid, "pis-not-in-db-2", hp)
    nm.season = None
    r = IngestionService(Listing([nm])).sync_matches(code, season=None)
    assert r.provider_id_season_unknown == [sid] and r.skipped == 1 and _raw(old) == before


# ---------------------------------------------------------------------------- item 3(c): the re-key index


def test_an_annual_rematch_next_season_is_never_a_rekey_target():
    """The same pair, a new id, next season at the same calendar slot: a NEW row, the older one untouched."""
    code = "PISREKEY"
    (h, hp), (a, ap) = _pair()
    old_sid, new_sid = _gid(), _gid()
    # last season's SCHEDULED row (never finished: a placeholder-shaped row is the widest re-key target there is)
    old = _stored(code, old_sid, h, a, "2025", datetime(2026, 10, 31, 19, 0), status=MatchStatus.SCHEDULED)
    before = _raw(old)
    r = _sync(code, [_nm(code, new_sid, hp, ap, when=KICK_2026, status=MatchStatus.SCHEDULED)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 0, 0)
    assert _raw(old) == before
    assert len(_rows_with(code, new_sid)) == 1 and _rows_with(code, new_sid)[0]["season"] == "2026"


def test_a_prev_id_of_another_season_never_pulls_the_listing_back():
    """The "<source>_prev" history is the season's: last season's row whose history carries the listed id is not
    re-keyed by this season's listing."""
    code = "PISPREV"
    (h, hp), (a, ap) = _pair()
    cur, reused = _gid(), _gid()
    old = _stored(code, cur, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME,
                  ext={AF: cur, f"{AF}_prev": [reused]})
    before = _raw(old)
    r = _sync(code, [_nm(code, reused, hp, ap, home_score=3, away_score=0, full_time_result=Result.HOME)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 0, 0) and _raw(old) == before


def test_the_same_season_rekey_still_works():
    code = "PISRK2"
    (h, hp), (a, ap) = _pair()
    old_sid, new_sid = _gid(), _gid()
    mid = _stored(code, old_sid, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = _sync(code, [_nm(code, new_sid, hp, ap, status=MatchStatus.SCHEDULED)])
    assert (r.created, r.rekeyed) == (0, 1)
    assert _rows_with(code, new_sid)[0]["id"] == mid


# ---------------------------------------------------------------------------- an unknown season (law 4)


def test_a_listing_with_no_season_writes_nothing():
    code = "PISBLANK"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    old = _stored(code, sid, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    before = _raw(old)
    unseen = _gid()
    r = IngestionService(Listing([_nm(code, sid, hp, ap, season=""), _nm(code, unseen, hp, ap, season="")])
                         ).sync_matches(code)
    assert (r.created, r.updated, r.skipped) == (0, 0, 2)
    assert r.provider_id_season_unknown == [sid, unseen] and r.provider_id_collision == []
    assert _raw(old) == before and _rows_with(code, unseen) == []


def test_a_stored_row_of_unknown_season_carrying_the_id_refuses_the_listing():
    code = "PISNOSEA"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    old = _stored(code, sid, h, a, "", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    before = _raw(old)
    r = _sync(code, [_nm(code, sid, hp, ap)])
    assert (r.created, r.updated, r.skipped) == (0, 0, 1) and r.provider_id_season_unknown == [sid]
    assert _raw(old) == before


def test_a_multi_season_listing_scopes_each_row_by_its_own_season():
    """A sync without --season can list several seasons: each listed row finds its own season's row."""
    code = "PISMULTI"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    old = _stored(code, sid, h, a, "2025", KICK_2025, status=MatchStatus.SCHEDULED)
    new = _stored(code, sid, a, h, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = IngestionService(Listing([
        _nm(code, sid, hp, ap, season="2025", when=KICK_2025, home_score=45, away_score=14,
            full_time_result=Result.HOME),
        _nm(code, sid, ap, hp, season="2026", home_score=25, away_score=49, full_time_result=Result.AWAY),
    ])).sync_matches(code)
    assert (r.created, r.updated) == (0, 2) and r.orientation_reversed == []
    assert sorted(r.provider_id_collision) == sorted([(new, "2026", sid), (old, "2025", sid)])
    rows = {x["id"]: x for x in _rows_with(code, sid)}
    assert (rows[old]["home_score"], rows[old]["away_score"]) == (45, 14)
    assert (rows[new]["home_score"], rows[new]["away_score"]) == (25, 49)


def test_a_sport_wide_source_is_unchanged():
    """SPORT_WIDE_SOURCES (mlb_stats_api, #569): the plain gamePk lookup across the sport, whatever the season."""
    assert svc.SPORT_WIDE_SOURCES == frozenset({"mlb_stats_api"})
    m = Match(season="2025", external_ids={"mlb_stats_api": "777"})
    c = svc.match_cache([m], "mlb_stats_api")
    assert c == {"777": m}
    assert IngestionService._same_season_row(
        NormalizedMatch(sport=Sport.MLB, competition_code="MLB", season="2026", utc_date=KICK_2026,
                        status=MatchStatus.SCHEDULED, home_team_source_id="h", away_team_source_id="a",
                        source="mlb_stats_api", source_id="777"), c) is m


def test_the_result_lists_default_empty():
    r = SyncResult()
    assert r.provider_id_collision == [] and r.provider_id_season_unknown == [] and str(r).startswith("created=0")
