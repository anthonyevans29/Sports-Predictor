"""NCAA PLACEHOLDER RE-KEY (ARCHITECT 2026-10-09, addendum 30 item 3, amending the second re-key ruling of
2026-10-05): "For NCAA, a stored SCHEDULED row at the provider's TBD kickoff holds its natural key for its whole
game day. An unknown incoming id for the same home and away team, at a real kickoff within 24 hours of that
placeholder, re-keys that row. Every refusal of the 12-hour rule applies as it stands: the stored id still in the
listing, a row already claimed in the run, more than one candidate, the pair swapped. A row at a real kickoff
keeps the 12-hour window." NFL is untouched.

The receipt (addendum 30 item 2): on the host, Georgia @ Alabama held 8376 at 04:00Z and the listing carried the
game as 47665 at 23:30Z; the 12-hour rule created the second row."""
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.ingestion import placeholder
from src.ingestion.service import IngestionService

SRC = "api_american_football"
PH = datetime(2093, 10, 10, 4, 0)            # the provider's TBD kickoff (midnight US Eastern)
REAL = datetime(2093, 10, 10, 23, 30)        # the announced kickoff, 19.5h later: beyond the 12-hour window
_made: list = []


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    yield
    with session_scope() as s:
        s.query(Match).filter(Match.id.in_(_made)).delete(synchronize_session=False)
        s.query(Team).filter(Team.name.like("NPR %")).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.code == "NPRNFL").delete(synchronize_session=False)


class FakeAdapter:
    source_name = SRC

    def __init__(self, listing):
        self.listing = listing

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        return self.listing


def _world(code, tag):
    """The competition (NCAA is shared with other test modules: get-or-create) and six fresh teams."""
    init_db()
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == code)).scalars().first()
        if c is None:
            c = Competition(sport=Sport.NFL, code=code, name=code, area="USA", type="LEAGUE")
            s.add(c)
        ts = [Team(sport=Sport.NFL, name=f"NPR {tag} T{i}", external_ids={SRC: f"npr{tag}t{i}"}) for i in range(6)]
        s.add_all(ts)
        s.flush()
        return c.id, [t.id for t in ts]


def _match(cid, tids, h, a, sid, when, status=MatchStatus.SCHEDULED):
    with session_scope() as s:
        m = Match(sport=Sport.NFL, competition_id=cid, season="2093", utc_date=when, status=status,
                  status_raw="NS", home_team_id=tids[h], away_team_id=tids[a], external_ids={SRC: sid})
        s.add(m)
        s.flush()
        _made.append(m.id)
        return m.id


def _nm(code, tag, h, a, sid, when):
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season="2093", utc_date=when,
                           status=MatchStatus.SCHEDULED, home_team_source_id=f"npr{tag}t{h}",
                           away_team_source_id=f"npr{tag}t{a}", source=SRC, source_id=sid, status_raw="NS")


def _sync(code, listing):
    r = IngestionService(FakeAdapter(listing)).sync_matches(code, "2093")
    with session_scope() as s:
        _made.extend(m.id for m in s.execute(select(Match).where(Match.external_ids.isnot(None))).scalars()
                     if (m.external_ids or {}).get(SRC) in {nm.source_id for nm in listing} and m.id not in _made)
    return r


def _rows(cid, tids, h, a):
    with session_scope() as s:
        return s.execute(select(func.count(Match.id)).where(
            Match.competition_id == cid, Match.home_team_id == tids[h], Match.away_team_id == tids[a])).scalar()


def test_the_receipt_script_and_the_sync_share_one_placeholder_definition():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import ncaa_rekey_receipt as rr
    assert rr.is_placeholder_kickoff is placeholder.is_placeholder_kickoff
    assert rr.placeholder_resolved is placeholder.placeholder_resolved


def test_a_placeholder_row_is_rekeyed_by_its_announced_kickoff_under_a_new_id():
    """Fails on main: the stored row at 04:00Z under an id the listing does not carry, the listing's same pair at
    23:30Z that day under a new id -> main created a second row. Ruled: the first row is re-keyed, the old id kept
    in its history."""
    cid, tids = _world("NCAA", "a")
    row = _match(cid, tids, 0, 1, "8376", PH)
    r = _sync("NCAA", [_nm("NCAA", "a", 0, 1, "47665", REAL)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (0, 1, 0)
    assert _rows(cid, tids, 0, 1) == 1
    with session_scope() as s:
        m = s.get(Match, row)
        assert m.external_ids[SRC] == "47665" and m.external_ids[f"{SRC}_prev"] == ["8376"]
        assert [(e["from"], e["to"], e["via"]) for e in m.external_ids[f"{SRC}_rekeys"]] == [("8376", "47665", "sync")]
        assert m.utc_date == REAL and m.status == MatchStatus.SCHEDULED


def test_a_row_at_a_real_kickoff_keeps_the_12_hour_window():
    """The limit: the stored row at a REAL kickoff 13 hours from the incoming one -> a second row, as today."""
    cid, tids = _world("NCAA", "b")
    row = _match(cid, tids, 0, 1, "9001", datetime(2093, 10, 10, 10, 30))
    r = _sync("NCAA", [_nm("NCAA", "b", 0, 1, "9002", REAL)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 0, 0)
    assert _rows(cid, tids, 0, 1) == 2
    with session_scope() as s:
        assert s.get(Match, row).external_ids[SRC] == "9001"


def test_beyond_24_hours_of_the_placeholder_a_second_row_is_created():
    cid, tids = _world("NCAA", "c")
    _match(cid, tids, 0, 1, "9101", PH)
    r = _sync("NCAA", [_nm("NCAA", "c", 0, 1, "9102", datetime(2093, 10, 11, 4, 30))])   # 24.5h
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 0, 0)


def test_every_12_hour_refusal_applies_under_the_placeholder_window():
    cid, tids = _world("NCAA", "d")
    # the stored id still in the listing -> refused, not created
    _match(cid, tids, 0, 1, "9201", PH)
    # a row already claimed in the run: two new ids for one placeholder row -> the second refused
    _match(cid, tids, 2, 3, "9301", PH)
    # a doubled game (addendum 33 item 1): the placeholder row and its second row at a real kickoff 10.5h from
    # the incoming -> the 12-hour rule decides, as on main: the real-kickoff row is re-keyed, the placeholder
    # row is untouched (eb53a44 refused it as two candidates)
    ph_row = _match(cid, tids, 4, 5, "9401", PH)
    real_row = _match(cid, tids, 4, 5, "9402", datetime(2093, 10, 10, 13, 0))
    listing = [_nm("NCAA", "d", 0, 1, "9201", PH), _nm("NCAA", "d", 0, 1, "9202", REAL),
               _nm("NCAA", "d", 2, 3, "9302", REAL), _nm("NCAA", "d", 2, 3, "9303", REAL),
               _nm("NCAA", "d", 4, 5, "9403", REAL)]
    r = _sync("NCAA", listing)
    assert (r.created, r.rekeyed, r.rekey_refused) == (0, 2, 2)
    assert (_rows(cid, tids, 0, 1), _rows(cid, tids, 2, 3), _rows(cid, tids, 4, 5)) == (1, 1, 2)
    with session_scope() as s:
        assert s.get(Match, real_row).external_ids[SRC] == "9403"
        assert s.get(Match, real_row).external_ids[f"{SRC}_prev"] == ["9402"]
        ph = s.get(Match, ph_row)
        assert ph.external_ids == {SRC: "9401"} and ph.utc_date == PH


def test_two_placeholder_rows_for_one_pair_are_refused():
    """More than one placeholder candidate (addendum 33 item 1) -> refused, nothing created or re-keyed."""
    cid, tids = _world("NCAA", "g")
    _match(cid, tids, 0, 1, "9701", PH)
    _match(cid, tids, 0, 1, "9702", PH)
    r = _sync("NCAA", [_nm("NCAA", "g", 0, 1, "9703", REAL)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (0, 0, 1)
    assert _rows(cid, tids, 0, 1) == 2
    with session_scope() as s:
        assert sorted((m.external_ids or {}).get(SRC) for m in s.execute(select(Match).where(
            Match.competition_id == cid, Match.home_team_id == tids[0])).scalars()) == ["9701", "9702"]


def test_the_pair_swapped_is_refused_under_the_placeholder_window():
    cid, tids = _world("NCAA", "e")
    _match(cid, tids, 1, 0, "9501", PH)                       # stored home/away swapped, at the placeholder
    r = _sync("NCAA", [_nm("NCAA", "e", 0, 1, "9502", REAL)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (0, 0, 1)
    assert _rows(cid, tids, 0, 1) == 0


def test_nfl_is_untouched_a_0400z_row_keeps_the_12_hour_window():
    cid, tids = _world("NPRNFL", "f")
    row = _match(cid, tids, 0, 1, "9601", PH)
    r = _sync("NPRNFL", [_nm("NPRNFL", "f", 0, 1, "9602", REAL)])
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 0, 0)
    with session_scope() as s:
        assert s.get(Match, row).external_ids[SRC] == "9601"
