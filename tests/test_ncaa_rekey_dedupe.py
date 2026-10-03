"""ARCHITECT 2026-10-03 (priority): an NCAA resync created 1006 rows — known fixtures came back under
NEW provider ids, the source-id lookup missed, duplicates followed. Pins: (1) the matcher re-keys
(UPDATES the stored row, keeps the old id under <source>_prev) when the stored id is absent from the
listing; ambiguous / swapped candidates are refused, never created; (2) dedupe-matches merges the newer
row INTO the older (referenced) one — fresh status/scores, references re-pointed, empty row deleted —
and refuses unique-table conflicts; (3) the fixtures export carries one row per fixture, preferring the
finished one, until the dedupe runs."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchNeutralDerived, MatchStatus, Odds, OddsSnapshot, Sport,
                           Team)
from src.ingestion import match_dedupe as md
from src.ingestion.service import IngestionService
from src.timeutil import utc_now_naive

SRC = "api_american_football"
KO = datetime(2091, 10, 2, 0, 0)


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    """These tests use Sport.NFL; tests/test_nfl_scope.py deletes every NFL match and cleans only
    predictions, so the odds / snapshots / derived rows written here are removed on teardown."""
    yield
    with session_scope() as s:
        cids = [c.id for c in s.execute(select(Competition).where(Competition.code.in_(CODES))).scalars()]
        mids = [m.id for m in s.execute(select(Match).where(Match.competition_id.in_(cids))).scalars()]
        for model in (Odds, OddsSnapshot, MatchNeutralDerived):
            s.query(model).filter(model.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


CODES = ("RK1", "RK2", "DD1", "DD2", "EX1")


class FakeAdapter:
    source_name = SRC

    def __init__(self, listing):
        self.listing = listing

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        return self.listing


def _world(code):
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code=code, name=code, area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"{code} T{i}", external_ids={SRC: f"{code}t{i}"}) for i in range(6)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        return c.id, [t.id for t in ts]


def _match(s, cid, tids, h, a, sid, when=KO, status=MatchStatus.SCHEDULED, **kw):
    m = Match(sport=Sport.NFL, competition_id=cid, season="2091", utc_date=when, status=status,
              home_team_id=tids[h], away_team_id=tids[a], external_ids={SRC: sid}, **kw)
    s.add(m)
    s.flush()
    return m.id


def _nm(code, h, a, sid, when=KO, status=MatchStatus.FINISHED, hs=31, as_=17):
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season="2091", utc_date=when, status=status,
                           home_team_source_id=f"{code}t{h}", away_team_source_id=f"{code}t{a}", source=SRC,
                           source_id=sid, status_raw="FT", home_score=hs, away_score=as_)


def test_resync_with_new_provider_ids_updates_instead_of_creating():
    cid, tids = _world("RK1")
    with session_scope() as s:
        old = _match(s, cid, tids, 0, 1, "100")
        twin_a = _match(s, cid, tids, 2, 3, "200")
        twin_b = _match(s, cid, tids, 2, 3, "201", when=KO + timedelta(hours=3))   # two stored candidates
        swap = _match(s, cid, tids, 5, 4, "300")                                       # stored home/away swapped
        n0 = s.execute(select(func.count(Match.id)).where(Match.competition_id == cid)).scalar()
    listing = [_nm("RK1", 0, 1, "9100"),                    # re-keyed: 100 is not in the listing
               _nm("RK1", 2, 3, "9200"),                    # ambiguous: refused
               _nm("RK1", 4, 5, "9300"),                    # only the swapped pair: refused
               _nm("RK1", 0, 1, "9101", when=KO + timedelta(days=7))]   # genuinely new (a week later)
    r = IngestionService(FakeAdapter(listing)).sync_matches("RK1", "2091")
    assert (r.created, r.rekeyed, r.rekey_refused) == (1, 1, 2)
    with session_scope() as s:
        m = s.get(Match, old)
        assert m.external_ids[SRC] == "9100" and m.external_ids[f"{SRC}_prev"] == ["100"]
        assert (m.status, m.home_score, m.away_score) == (MatchStatus.FINISHED, 31, 17)
        assert s.get(Match, twin_a).external_ids[SRC] == "200" and s.get(Match, swap).external_ids[SRC] == "300"
        assert s.execute(select(func.count(Match.id)).where(Match.competition_id == cid)).scalar() == n0 + 1
    r2 = IngestionService(FakeAdapter(listing[:1])).sync_matches("RK1", "2091")   # idempotent second run
    assert (r2.created, r2.updated, r2.rekeyed) == (0, 1, 0)


def test_a_stored_id_still_listed_is_a_different_game_never_rekeyed():
    cid, tids = _world("RK2")
    with session_scope() as s:
        _match(s, cid, tids, 0, 1, "100")
    listing = [_nm("RK2", 0, 1, "100"), _nm("RK2", 0, 1, "101", when=KO + timedelta(hours=4))]
    r = IngestionService(FakeAdapter(listing)).sync_matches("RK2", "2091")
    assert (r.created, r.updated, r.rekeyed) == (1, 1, 0)


def test_dedupe_merges_the_newer_row_into_the_referenced_one(tmp_path):
    cid, tids = _world("DD1")
    with session_scope() as s:
        keeper = _match(s, cid, tids, 0, 1, "100")
        newer = _match(s, cid, tids, 0, 1, "9100", status=MatchStatus.FINISHED, status_raw="FT",
                       home_score=24, away_score=21)
        s.add(Odds(match_id=keeper, source="b", bookmaker="x", market="1X2", selection="HOME", price_decimal=1.9,
                   captured_at=KO - timedelta(hours=2)))
        s.add(OddsSnapshot(match_id=newer, source="kalshi", market="1X2", selection="HOME", devig_prob=0.5,
                           captured_at=KO - timedelta(hours=1)))
        lone = _match(s, cid, tids, 2, 3, "500")
    dry = md.run("DD1", source=SRC)
    assert dry["pairs"] == 1 and dry["merged"] == 0 and set(dry["differs"]) >= {"ext", "status", "score"}
    with session_scope() as s:
        assert s.get(Match, newer) is not None                      # dry-run wrote nothing
    r = md.run("DD1", source=SRC, apply=True)
    assert r["merged"] == 1 and r["repointed"] == {"odds_snapshots": 1} and not r["refused"]
    with session_scope() as s:
        k = s.get(Match, keeper)
        assert s.get(Match, newer) is None and s.get(Match, lone) is not None
        assert (k.status, k.home_score, k.away_score, k.status_raw) == (MatchStatus.FINISHED, 24, 21, "FT")
        assert k.external_ids[SRC] == "9100" and k.external_ids[f"{SRC}_prev"] == ["100"]
        assert s.execute(select(func.count(Odds.id)).where(Odds.match_id == keeper)).scalar() == 1
        assert s.execute(select(func.count(OddsSnapshot.id)).where(OddsSnapshot.match_id == keeper)).scalar() == 1
    assert md.run("DD1", source=SRC)["pairs"] == 0


def test_dedupe_refuses_a_unique_table_conflict_and_deletes_nothing():
    cid, tids = _world("DD2")
    with session_scope() as s:
        keeper = _match(s, cid, tids, 0, 1, "100")
        newer = _match(s, cid, tids, 0, 1, "9100", status=MatchStatus.FINISHED)
        for mid in (keeper, newer):
            s.add(MatchNeutralDerived(match_id=mid, neutral_derived=False, rule="r"))
    r = md.run("DD2", source=SRC, apply=True)
    assert r["merged"] == 0 and "match_neutral_derived" in r["refused"][0]["why"]
    with session_scope() as s:
        assert s.get(Match, newer) is not None and s.get(Match, keeper) is not None


def test_fixtures_export_carries_one_row_per_fixture_preferring_the_finished(tmp_path):
    from src.walters.export import export_fixtures
    cid, tids = _world("EX1")
    soon = utc_now_naive().replace(microsecond=0) - timedelta(hours=20)
    with session_scope() as s:
        old = _match(s, cid, tids, 0, 1, "100", when=soon)
        fin = _match(s, cid, tids, 0, 1, "9100", when=soon, status=MatchStatus.FINISHED, home_score=3, away_score=1)
        other = _match(s, cid, tids, 2, 3, "200", when=soon + timedelta(hours=30))
    rc = {}
    doc = json.loads(open(export_fixtures("EX1", out_dir=str(tmp_path), receipts=rc)).read())
    ids = [r["match_id"] for r in doc["fixtures"]]
    assert fin in ids and old not in ids and other in ids
