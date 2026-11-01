"""#764 (ARCHITECT 2026-11-01 15:45 ET, addendum 206 item 2(i)): "intl_history PASSES ITS SEASON" — a history listing
older than a team's newest membership keeps the name and short_name, counted on the same "names kept" line. Synthetic
API-Football-shaped responses replayed from a directory; the API is never reached."""
import json
import os
from datetime import date

from sqlalchemy import select

from src.adapters.api_football import APIFootballAdapter
from src.db.database import init_db, session_scope
from src.db.schema import Team
from src.ingestion import intl_history as ih
from src.ingestion.service import names_kept_line

SINCE = date(2018, 1, 1)
A, B = 881701, 881702


def _dir(d, year, names):
    os.makedirs(d, exist_ok=True)
    lg = [{"league": {"id": 5, "name": "UEFA Nations League", "type": "Cup"},
           "seasons": [{"year": year, "start": f"{year}-01-01", "end": f"{year}-12-31"}]}]
    fx = {"fixture": {"id": 9917000 + year, "date": f"{year}-06-07T18:45:00+00:00", "status": {"short": "FT"},
                      "venue": {"id": None, "name": "A Arena", "city": "A City"}},
          "league": {"season": year, "round": "Group A - 1"},
          "teams": {"home": {"id": A, "name": names[A], "winner": True},
                    "away": {"id": B, "name": names[B], "winner": False}},
          "goals": {"home": 1, "away": 0},
          "score": {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": 1, "away": 0}}}
    tm = [{"team": {"id": t, "name": names[t], "code": None, "country": "X"},
           "venue": {"name": "A Arena", "city": "A City"}} for t in (A, B)]
    for name, payload in {"leagues.json": {"response": lg}, f"fixtures_5_{year}.json": {"response": [fx]},
                          f"teams_5_{year}.json": {"response": tm}}.items():
        with open(os.path.join(d, name), "w") as f:
            json.dump(payload, f)


def _name(tid):
    src = APIFootballAdapter.source_name if hasattr(APIFootballAdapter, "source_name") else "api_football"
    with session_scope() as s:
        for t in s.execute(select(Team)).scalars():
            if (t.external_ids or {}).get(src) == str(tid):
                return t.name
    return None


def test_a_history_listing_of_an_older_year_keeps_the_current_name(tmp_path):
    init_db()
    _dir(tmp_path / "new", 2083, {A: "Newland", B: "Otherland"})
    ih.ingest(ih.Source(from_dir=str(tmp_path / "new")), SINCE)           # a 2083/84 membership, the current names
    assert _name(A) == "Newland"
    _dir(tmp_path / "old", 2075, {A: "Oldland", B: "Otherland"})          # an older history listing renames nothing
    r = ih.ingest(ih.Source(from_dir=str(tmp_path / "old")), SINCE)
    assert _name(A) == "Newland" and _name(B) == "Otherland"
    assert len(r["names_kept"]) == 1 and r["names_kept"][0][1:] == ("Newland", "Oldland")
    assert r["names_kept_line"] == names_kept_line(1)
    _dir(tmp_path / "newer", 2084, {A: "Newerland", B: "Otherland"})      # a newer listing still renames
    r = ih.ingest(ih.Source(from_dir=str(tmp_path / "newer")), SINCE)
    assert _name(A) == "Newerland" and r["names_kept"] == [] and r["names_kept_line"] is None
