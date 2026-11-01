"""#585 (ARCHITECT 2026-11-01 13:15 ET, addendum 200 item 3): after a team merge, a sync-teams listing that carries
both of the kept row's provider ids in a season where the kept row has no membership yet wrote that membership twice
(SessionLocal runs autoflush=False, so the second s.get in one sync missed the first add) and the unique key on
(competition_id, team_id, season) rolled the competition's whole team sync back. The fix: _link_team_to_competition
flushes right after its add.

The test is the Issue's receipt fixture: rows 59 "Hawai'i" and 901 "Hawai&#x27;i" (tests/test_team_merge.py's
`hawaii`), merged by team_merge.apply (keep/other as those tests do), then a 2027 listing carrying [901, 59] through
the real adapter's list_teams (its HTTP _get replaced; no network) and the real IngestionService.sync_teams. Every
write goes to a scratch SQLite file under tmp_path, its sessions made exactly as SessionLocal's (autoflush=False);
never data/."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.schema import Base
from src.ingestion import team_merge as tm
from tests.test_team_merge import SRC, con_of, hawaii


@pytest.fixture
def merged(tmp_path, monkeypatch):
    """The scratch DB the app's sessions are bound to, holding the hawaii pair merged: 1 row, provider ids 59 + 901."""
    import src.db.database as db
    path = tmp_path / "scratch585.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                                         expire_on_commit=False))
    keep, other = hawaii(eng)
    con = con_of(path)
    res = tm.apply(con, "2026-11-01T13:15:00", [(keep, other)])
    assert [(m["keep"], m["other"]) for m in res["merged"]] == [(keep, other)] and not res["refused"], res
    ext = json.loads(con.execute("SELECT external_ids FROM teams WHERE id = ?", (keep,)).fetchone()[0])
    assert tm.source_ids(ext, SRC) == {"59", "901"}                    # both provider ids now resolve to the kept row
    yield con, keep, other
    con.close()
    eng.dispose()


def _adapter(monkeypatch, listing):
    """The real APIAmericanFootballAdapter; only its HTTP call is replaced (recorded, no network)."""
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter()
    calls = []

    def fake_get(path, params=None):
        calls.append((path, dict(params or {})))
        return {"response": listing}
    monkeypatch.setattr(ad, "_get", fake_get)
    return ad, calls


def _members(con, season):
    return con.execute("SELECT ct.team_id FROM competition_teams ct JOIN competitions c ON c.id = ct.competition_id "
                       "WHERE c.code = 'NCAA' AND ct.season = ? ORDER BY ct.team_id", (season,)).fetchall()


def test_a_listing_carrying_both_merged_ids_writes_one_membership_and_raises_nothing(merged, monkeypatch):
    """The Issue's receipt on main: "RAISED IntegrityError ... UNIQUE constraint failed: competition_teams..." and
    "2027 memberships before/after: 0 0". With the flush: one 2027 membership, on the kept row, no error."""
    from src.ingestion.service import IngestionService
    con, keep, other = merged
    ad, calls = _adapter(monkeypatch, [{"id": 901, "name": "Hawai&#x27;i"}, {"id": 59, "name": "Hawai'i"}])
    assert _members(con, "2027") == []
    res = IngestionService(ad).sync_teams("NCAA", "2027")                  # raised IntegrityError before the fix
    assert calls == [("teams", {"league": 2, "season": 2027})]           # the real adapter path, the NCAA league
    assert _members(con, "2027") == [(keep,)]                             # ONE membership, on the kept row
    assert res.updated == 2 and res.created == 0                          # both listing entries found the kept row
    assert con.execute("SELECT COUNT(*) FROM teams WHERE id = ?", (other,)).fetchone()[0] == 0   # no row remade
    ext = json.loads(con.execute("SELECT external_ids FROM teams WHERE id = ?", (keep,)).fetchone()[0])
    assert ext[SRC] == "59" and ext[f"{SRC}_also"] == ["901"]            # the merge's ids stand (#465's P1)
    # the seasons already stored are untouched
    assert _members(con, "2024") == [(keep,)] and _members(con, "2026") == [(keep,)]


def test_a_second_sync_of_the_same_season_finds_the_stored_membership(merged, monkeypatch):
    """The flush adds nothing for a membership already stored: a re-run of the same listing writes nothing new."""
    from src.ingestion.service import IngestionService
    con, keep, _ = merged
    ad, _ = _adapter(monkeypatch, [{"id": 59, "name": "Hawai'i"}, {"id": 901, "name": "Hawai&#x27;i"}])
    IngestionService(ad).sync_teams("NCAA", "2027")
    IngestionService(ad).sync_teams("NCAA", "2027")
    assert _members(con, "2027") == [(keep,)]


def test_an_unmerged_listing_still_links_each_team_once(merged, monkeypatch):
    """A listing of distinct rows (no merged id twice) links each once, as before the fix."""
    from src.ingestion.service import IngestionService
    con, keep, _ = merged
    wyo = con.execute("SELECT id FROM teams WHERE name = 'Wyoming'").fetchone()[0]
    ad, _ = _adapter(monkeypatch, [{"id": 59, "name": "Hawai'i"}, {"id": 70, "name": "Wyoming"},
                                   {"id": 999585, "name": "New Program 585"}])
    res = IngestionService(ad).sync_teams("NCAA", "2027")
    new = con.execute("SELECT id FROM teams WHERE name = 'New Program 585'").fetchone()[0]
    assert res.created == 1 and res.updated == 2
    assert _members(con, "2027") == sorted([(keep,), (wyo,), (new,)])
