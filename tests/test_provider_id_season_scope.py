"""THE PROVIDER ID IS THE SEASON'S (ARCHITECT 2026-11-09, addendum 310 item 3; #902). Item 3(d), verbatim: "a unit
test on the 18216 case: a 2025 FINISHED row with id 18216, a 2026 listing with id 18216 and the pair reversed → the 2025
row byte-identical after the sync, a new 2026 row created with the LISTING's home/away, `provider_id_collision 1`
printed".

ADDENDUM 312 items 1-2 (#906): the key is the season YEAR on both sides ("2026/27", "2026-27" and "2026" read one
season; a season with no leading year is refused and counted, never matched, never created), and the collision line
counts CREATIONS only (a row created because the listed id was held only by a row of another season; once the
listing's own season has its row, nothing printed, nothing counted).

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
    assert r.provider_id_collision == [(((old, "2025"),), sid)]
    assert r.orientation_reversed == [] and r.teams_mismatch_refused == []         # the chain never fired
    assert svc.provider_id_collision_line(r.provider_id_collision) == f"provider_id_collision 1: {old} (2025) ← {sid}"
    return old, sid, new["id"]


# ---------------------------------------------------------------------------- item 3(a)/(b)/(d): the 18216 case


def test_the_18216_case_ncaa_creates_its_own_row_and_leaves_2025_byte_identical():
    _assert_collision_case("PISNCAA")


def test_the_18216_case_nfl_the_same():
    _assert_collision_case("PISNFL")


def test_a_second_sync_updates_the_2026_row_and_counts_nothing():
    """Addendum 312 item 2: "once the listing's own season has a row with that id, the sync finds it by (id,
    season_year) and updates it — nothing printed, nothing counted"."""
    code = "PISAGAIN"
    old, sid, new_id = _assert_collision_case(code)
    before = _raw(old)
    with session_scope() as s:
        m = s.get(Match, new_id)
        home, away = m.home_team.external_ids[AF], m.away_team.external_ids[AF]
    again = _nm(code, sid, home, away, home_score=25, away_score=49, full_time_result=Result.AWAY)
    r = _sync(code, [again])
    assert (r.created, r.updated) == (0, 1)
    assert r.provider_id_collision == []                               # the 2026 row is the listing's own: no creation
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


def test_the_cli_prints_no_collision_line_when_nothing_was_created(monkeypatch):
    """Addendum 312 item 2: "After the restore, steady NCAA runs print nothing" — the line is printed only when N > 0."""
    import cli

    code = "PISCLI0"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    _stored(code, sid, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    mid = _stored(code, sid, a, h, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: Listing([_nm(code, sid, ap, hp)]))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", code, "--season", "2026"])
    assert res.exit_code == 0, res.output
    assert "provider_id_collision" not in res.output and _rows_with(code, sid)[-1]["id"] == mid
    assert svc.provider_id_collision_line([]) == "provider_id_collision 0"


def test_two_other_seasons_holding_the_id_make_one_creation():
    """One new row, one entry: N counts creations, the entry names every other season's row holding the id."""
    code = "PISTWO"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    r24 = _stored(code, sid, h, a, "2024", datetime(2024, 11, 2, 2, 15), home_score=1, away_score=0,
                  full_time_result=Result.HOME)
    r25 = _stored(code, sid, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    r = _sync(code, [_nm(code, sid, ap, hp, home_score=25, away_score=49, full_time_result=Result.AWAY)])
    assert r.created == 1 and len(r.provider_id_collision) == 1
    assert svc.provider_id_collision_line(r.provider_id_collision) == \
        f"provider_id_collision 1: {r24} (2024) + {r25} (2025) ← {sid}"


def test_a_rekey_onto_the_listing_season_is_not_a_collision():
    """A listing re-keys its own season's row (no creation): the 2025 row holding the id is not counted."""
    code = "PISRKC"
    (h, hp), (a, ap) = _pair()
    old_sid, sid = _gid(), _gid()
    _stored(code, sid, h, a, "2025", KICK_2025, home_score=45, away_score=14, full_time_result=Result.HOME)
    mid = _stored(code, old_sid, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = _sync(code, [_nm(code, sid, hp, ap, status=MatchStatus.SCHEDULED)])
    assert (r.created, r.rekeyed) == (0, 1) and r.provider_id_collision == []
    assert [x["id"] for x in _rows_with(code, sid) if x["season"] == "2026"] == [mid]


# ---------------------------------------------------------------------------- addendum 312 item 1: the season year


def test_spellings_of_one_season_year_are_one_season():
    """ "2026/27", "2026-27" and "2026" read one season: the stored row is found and updated, nothing created."""
    for i, (stored, listed) in enumerate((("2026-27", "2026/27"), ("2026/27", "2026"), ("2026", "2026-27"))):
        code = f"PISYR{i}"
        (h, hp), (a, ap) = _pair()
        sid = _gid()
        mid = _stored(code, sid, h, a, stored, KICK_2026, status=MatchStatus.SCHEDULED)
        r = _sync(code, [_nm(code, sid, hp, ap, season=listed, home_score=31, away_score=17,
                             full_time_result=Result.HOME)], season=listed)
        assert (r.created, r.updated, r.skipped) == (0, 1, 0), (stored, listed)
        assert r.provider_id_collision == [] and r.provider_id_season_unknown == []
        assert [x["id"] for x in _rows_with(code, sid)] == [mid]


def test_a_rekey_and_its_history_read_the_season_year():
    """The re-key index (season_year, home, away) and the `_prev` history (old id, season_year) fold spellings too."""
    code = "PISYRK"
    (h, hp), (a, ap) = _pair()
    old_sid, new_sid = _gid(), _gid()
    mid = _stored(code, old_sid, h, a, "2026-27", KICK_2026, status=MatchStatus.SCHEDULED)
    r = _sync(code, [_nm(code, new_sid, hp, ap, season="2026/27", status=MatchStatus.SCHEDULED)], season="2026/27")
    assert (r.created, r.rekeyed) == (0, 1) and _rows_with(code, new_sid)[0]["id"] == mid
    code = "PISYRP"
    (h, hp), (a, ap) = _pair()
    cur, reused = _gid(), _gid()
    mid = _stored(code, cur, h, a, "2026-27", KICK_2026, status=MatchStatus.SCHEDULED,
                  ext={AF: cur, f"{AF}_prev": [reused]})
    r = _sync(code, [_nm(code, reused, hp, ap, season="2026", status=MatchStatus.SCHEDULED)])
    assert (r.created, r.rekeyed) == (0, 1) and _rows_with(code, reused)[0]["id"] == mid


def test_a_season_with_no_leading_year_is_refused_and_counted():
    """A listing or a stored row whose season_year is None: refused and counted, never matched, never created."""
    code = "PISNOYR"
    (h, hp), (a, ap) = _pair()
    sid, sid2 = _gid(), _gid()
    stored = _stored(code, sid, h, a, "26/27", KICK_2026, status=MatchStatus.SCHEDULED)
    before = _raw(stored)
    r = IngestionService(Listing([_nm(code, sid, hp, ap, season="2026"),
                                  _nm(code, sid2, hp, ap, season="abc")])).sync_matches(code)
    assert (r.created, r.updated, r.skipped) == (0, 0, 2)
    assert r.provider_id_season_unknown == [sid, sid2] and r.provider_id_collision == []
    assert _raw(stored) == before and _rows_with(code, sid2) == []


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
    # addendum 312 item 2: no row was created, so no collision is counted (the skip is counted once)
    assert r.provider_id_collision == []


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


def test_an_id_listed_in_another_season_never_blocks_a_same_season_rekey():
    """#906 review (Codex, the re-key guards): a sync without --season lists 2025 and 2026. The 2026 row is re-keyed
    from X to Y while the provider reuses X for a 2025 game: X listed in 2025 is not "still in this listing" for the
    2026 row."""
    code = "PISGUARD"
    (h, hp), (a, ap) = _pair()
    (h2, hp2), (a2, ap2) = _pair()
    x, y = _gid(), _gid()
    mid = _stored(code, x, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = IngestionService(Listing([
        _nm(code, x, hp2, ap2, season="2025", when=KICK_2025, status=MatchStatus.SCHEDULED),
        _nm(code, y, hp, ap, season="2026", status=MatchStatus.SCHEDULED),
    ])).sync_matches(code)
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 1, 0)
    assert _rows_with(code, y)[0]["id"] == mid
    assert [z["season"] for z in _rows_with(code, x)] == ["2025"]


def test_the_same_id_listed_in_the_same_season_still_blocks_the_rekey():
    """The guard itself stands: X still listed in the row's own season refuses the re-key to Y."""
    code = "PISGUARD2"
    (h, hp), (a, ap) = _pair()
    x, y = _gid(), _gid()
    mid = _stored(code, x, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = IngestionService(Listing([
        _nm(code, x, hp, ap, season="2026", status=MatchStatus.SCHEDULED),
        _nm(code, y, hp, ap, season="2026", status=MatchStatus.SCHEDULED),
    ])).sync_matches(code)
    assert (r.created, r.updated, r.rekeyed, r.rekey_refused) == (0, 1, 0, 1)
    assert _rows_with(code, y) == [] and _rows_with(code, x)[0]["id"] == mid


def test_a_claim_in_one_season_never_blocks_another_seasons_rekey():
    """Two seasons' rows both carry X (the collision shape) and each season's listing re-keys its own row: the claim
    of X in 2025 is not a claim of X in 2026."""
    code = "PISCLAIM"
    (h, hp), (a, ap) = _pair()
    x, y25, y26 = _gid(), _gid(), _gid()
    old = _stored(code, x, h, a, "2025", KICK_2025, status=MatchStatus.SCHEDULED)
    new = _stored(code, x, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = IngestionService(Listing([
        _nm(code, y25, hp, ap, season="2025", when=KICK_2025, status=MatchStatus.SCHEDULED),
        _nm(code, y26, hp, ap, season="2026", status=MatchStatus.SCHEDULED),
    ])).sync_matches(code)
    assert (r.created, r.rekeyed, r.rekey_refused) == (0, 2, 0)
    assert _rows_with(code, y25)[0]["id"] == old and _rows_with(code, y26)[0]["id"] == new


def test_a_rekey_target_of_no_season_year_refuses_and_counts_the_listing():
    """Addendum 312 item 1 ("refused and counted ..., never matched, never created"): a stored row of no season year
    that would be the listing's re-key target, by its `_prev` history or by the natural key, is not twinned: the
    listing is refused and counted as provider_id_season_unknown (not as a re-key refusal), the row untouched."""
    code = "PISNOYRK"
    (h, hp), (a, ap) = _pair()
    cur, reused = _gid(), _gid()
    by_prev = _stored(code, cur, h, a, "26/27", KICK_2026, status=MatchStatus.SCHEDULED,
                      ext={AF: cur, f"{AF}_prev": [reused]})
    before = _raw(by_prev)
    r = _sync(code, [_nm(code, reused, hp, ap, status=MatchStatus.SCHEDULED)])
    assert (r.created, r.updated, r.rekeyed, r.rekey_refused, r.skipped) == (0, 0, 0, 0, 1)
    assert r.provider_id_season_unknown == [reused] and _raw(by_prev) == before and _rows_with(code, reused) == []
    code = "PISNOYRN"
    (h, hp), (a, ap) = _pair()
    old, new = _gid(), _gid()
    by_pair = _stored(code, old, a, h, "", KICK_2026, status=MatchStatus.SCHEDULED)       # the pair swapped, no season
    before = _raw(by_pair)
    r = _sync(code, [_nm(code, new, hp, ap, status=MatchStatus.SCHEDULED)])
    assert (r.created, r.rekeyed, r.rekey_refused, r.skipped) == (0, 0, 0, 1)
    assert r.provider_id_season_unknown == [new] and _raw(by_pair) == before and _rows_with(code, new) == []


def test_a_no_year_row_beside_the_own_season_row_is_counted_never_touched():
    """Addendum 313 item 1(4), verbatim: "the listing's own-season row is matched and updated; the no-year row is never
    matched and never touched; it IS counted under `provider_id_season_unknown` so the line is visible when N > 0"."""
    code = "PISBESIDE"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    noyear = _stored(code, sid, h, a, "26/27", KICK_2025, status=MatchStatus.SCHEDULED)
    own = _stored(code, sid, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    before = _raw(noyear)
    r = _sync(code, [_nm(code, sid, hp, ap, home_score=31, away_score=17, full_time_result=Result.HOME)])
    assert (r.created, r.updated, r.skipped) == (0, 1, 0)                # updated, not refused, no skip
    assert r.provider_id_season_unknown == [sid] and r.provider_id_collision == []
    assert _raw(noyear) == before                                          # never touched
    rows = {x["id"]: x for x in _rows_with(code, sid)}
    assert (rows[own]["home_score"], rows[own]["away_score"]) == (31, 17)
    assert svc.season_unknown_line(r.provider_id_season_unknown) == f"provider_id_season_unknown 1: {sid}"


def test_no_no_year_row_counts_nothing():
    """The guard is silent when no row of no season year carries the id (both copies today, 313 item 1(4))."""
    code = "PISBESIDE0"
    (h, hp), (a, ap) = _pair()
    sid = _gid()
    _stored(code, sid, h, a, "2026", KICK_2026, status=MatchStatus.SCHEDULED)
    r = _sync(code, [_nm(code, sid, hp, ap)])
    assert r.updated == 1 and r.provider_id_season_unknown == []


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
    assert r.provider_id_collision == []                    # each listing found its own season's row: no creation
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
