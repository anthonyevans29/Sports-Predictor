"""Lane 5 (ARCHITECT 2026-10-04): intl venue-country normalization — the rows
intl-neutral-v3 left unknown, resolved into intl_venue_resolved (route A
/venues?id, unique city/name match, pinned aliases). intl_match_venue (what the
frozen intl-elo-v2 reads) is never touched. Synthetic data; no API."""
import itertools
import json
import os
from datetime import datetime

import pytest
from sqlalchemy import select

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_N = itertools.count(1)
V = {k: 97_710_000 + i for i, k in enumerate(("abroad", "unserved", "spelling", "de1", "de2", "fr1", "fr2"))}


def _world(tmp_path):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team
    init_db()
    with session_scope() as s:
        n = next(_N)
        comp = Competition(sport=Sport.SOCCER, code=f"RSV_T{n}", name="RSV", area="I", type="INTL")
        s.add(comp)
        s.flush()
        T = {k: Team(sport=Sport.SOCCER, name=f"RSV{n} {k}", area=a)
             for k, a in (("de", "Germany"), ("fr", "France"), ("nx", None), ("kr", "Korea Republic"))}
        s.add_all(T.values())
        s.flush()
        spec = [  # (key, home, venue id, fixture venue {name, city}, v3)
            ("abroad", "de", V["abroad"], {}, None),                                   # route A -> USA -> neutral
            ("city", "de", None, {"name": "?", "city": "Munich"}, None),        # unique city -> Germany -> home
            ("ambig", "fr", None, {"name": "?", "city": "Springfield"}, None),  # two countries -> refused
            ("nohome", "nx", V["de1"], {}, None),                                   # home country unknown
            ("name", "de", None, {"name": "Arena Z", "city": "Atlantis"}, None),  # unique name -> France -> neutral
            ("flagged", "de", V["de1"], {}, False),                                 # v3 already flagged: untouched
            ("unserved", "de", V["unserved"], {}, None),                                 # route A serves nothing
            ("spelling", "kr", V["spelling"], {}, None),                                 # South Korea vs Korea Republic
        ]
        ids, fixtures = {}, []
        for i, (k, h, vid, fvn, v3) in enumerate(spec):
            sid = str(7_700_000 + 100 * n + i)
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2096", utc_date=datetime(2096, 3, 1 + i, n % 24),
                      status=MatchStatus.FINISHED, home_team_id=T[h].id, away_team_id=T["fr" if h != "fr" else "de"].id,
                      home_score=1, away_score=0, external_ids={"api_football": sid})
            s.add(m)
            s.flush()
            ids[k] = m.id
            s.add(IntlMatchVenue(match_id=m.id, venue_id=vid, venue_country=None, home_country=T[h].area,
                                 neutral_v3=v3, rule="v3"))
            fixtures.append({"fixture": {"id": int(sid), "venue": {"id": vid, **fvn}}})
    save, vd = tmp_path / "save", tmp_path / "venues"
    save.mkdir()
    vd.mkdir()
    json.dump({"response": fixtures}, open(save / "fixtures_1_2096.json", "w"))
    json.dump({"response": [{"id": V["de1"], "country": "Germany", "city": "Munich", "name": "Allianz"},
                            {"id": V["de2"], "country": "Germany", "city": "Springfield", "name": "A"}]},
              open(vd / "venues_germany.json", "w"))
    json.dump({"response": [{"id": V["fr1"], "country": "France", "city": "Paris", "name": "Arena Z"},
                            {"id": V["fr2"], "country": "France", "city": "Springfield", "name": "B"}]},
              open(vd / "venues_france.json", "w"))
    return save, vd, ids


class FakeClient:
    def __init__(self):
        self.calls = []

    def _get(self, path, params):
        assert path == "venues"
        self.calls.append(params["id"])
        served = {V["abroad"]: [{"id": V["abroad"], "country": "USA", "city": "Dallas", "name": "AT&T"}],
                  V["spelling"]: [{"id": V["spelling"], "country": "South Korea", "city": "Seoul",
                                   "name": "World Cup Stadium"}]}
        return {"response": served.get(params["id"], [])}


def _rows(ids):
    from src.db.database import session_scope
    from src.db.schema import IntlVenueResolved
    with session_scope() as s:
        got = {r.match_id: (r.venue_country, r.country_source, r.neutral_resolved, r.reason)
               for r in s.execute(select(IntlVenueResolved).where(IntlVenueResolved.match_id.in_(ids.values()))).scalars()}
    return {k: got.get(v) for k, v in ids.items()}


def test_plan_counts_reasons_and_route_a_calls(tmp_path):
    from src.ingestion import intl_venues as iv
    save, vd, ids = _world(tmp_path)
    p = iv.resolve(str(save), str(vd), plan_only=True)["plan"]
    assert p["route_a_ids"] >= 3 and p["route_a_calls"] >= 3                 # abroad, unserved, spelling
    assert p["reasons"]["no venue id served"] >= 3 and p["reasons"]["home country unknown"] >= 1


def test_resolve_route_a_city_name_ambiguity_and_spelling(tmp_path):
    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    from src.ingestion import intl_venues as iv
    save, vd, ids = _world(tmp_path)
    fc = FakeClient()
    r = iv.resolve(str(save), str(vd), client=fc)
    assert {V["abroad"], V["unserved"], V["spelling"]} <= set(fc.calls) and r["calls"] == len(fc.calls)
    got = _rows(ids)
    assert got["abroad"][:3] == ("USA", "venues_by_id", True)
    assert got["city"][:3] == ("Germany", "city_match", False)
    assert got["name"][:3] == ("France", "name_match", True)
    assert got["ambig"][2] is None and "2 countries" in got["ambig"][3]      # never guessed
    assert got["nohome"][2] is None and got["nohome"][3] == "home country unknown"
    assert got["unserved"][2] is None and "not served by /venues?id" in got["unserved"][3]
    assert got["spelling"][2] is None and "alias needed" in got["spelling"][3]
    assert got["flagged"] is None                                            # v3-flagged rows are not re-derived
    assert "korea republic" in r["home_spellings_not_in_venue_vocab"]
    with session_scope() as s:                                               # v3 is never touched
        v3 = {m.match_id: (m.neutral_v3, m.venue_country, m.rule)
              for m in s.execute(select(IntlMatchVenue).where(IntlMatchVenue.match_id.in_(ids.values()))).scalars()}
    assert v3[ids["abroad"]] == (None, None, "v3") and v3[ids["flagged"]] == (False, None, "v3")
    # a pinned alias resolves the spelling gap; the replay makes no call
    again = iv.resolve(str(save), str(vd), aliases={"South Korea": "Korea Republic"}, client=None)
    assert again["calls"] == 0
    assert _rows(ids)["spelling"][:3] == ("South Korea", "venues_by_id", False)


def test_refusals(tmp_path):
    from src.ingestion import intl_venues as iv
    save, vd, ids = _world(tmp_path)
    with pytest.raises(iv.VenueError, match="under data/"):
        iv.resolve(str(save), os.path.join(ROOT, "data", "v"))
    with pytest.raises(iv.VenueError, match="max-calls"):
        iv.resolve(str(save), str(vd), max_calls=1, client=FakeClient())


def test_cli_plan_prints_reasons(tmp_path):
    from click.testing import CliRunner

    from cli import cli
    save, vd, ids = _world(tmp_path)
    out = CliRunner().invoke(cli, ["intl-venue-resolve", "--from-dir", str(save), "--venues-dir", str(vd), "--plan"])
    assert out.exit_code == 0, out.output
    assert "INTL-VENUE-RESOLVE" in out.output and "PLAN" in out.output and "route A (/venues?id): " in out.output
