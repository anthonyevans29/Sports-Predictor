"""#220 v3 route probe: enumerates the served fixture.venue keys (law 1),
counts distinct venue ids (route A) and home-team countries (route B), picks
the cheapest, makes no call, refuses data/. Synthetic saved responses."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import intl_venue_route_probe as vp  # noqa: E402


def _fx(fid, home, vid, city):
    return {"fixture": {"id": fid, "venue": {"id": vid, "name": f"{city} Arena", "city": city}},
            "teams": {"home": {"id": home}, "away": {"id": 999}}}


def test_routes_and_cheapest(tmp_path, capsys):
    json.dump({"response": [_fx(1, 10, 100, "Munich"), _fx(2, 10, 101, "Berlin"), _fx(3, 20, 200, "Paris"),
                            _fx(4, 20, None, "Lyon"), _fx(5, 30, 300, "Doha")]},
              open(tmp_path / "fixtures_10_2022.json", "w"))
    json.dump({"response": [{"team": {"id": 10, "country": "Germany"}}, {"team": {"id": 20, "country": "France"}},
                            {"team": {"id": 30, "country": None}}]}, open(tmp_path / "teams_10_2022.json", "w"))
    r = vp.analyse(str(tmp_path))
    assert r["served_country_keys"] == [] and r["venue_ids"] == 4 and r["fixtures_without_venue_id"] == 1
    assert (r["home_countries"], r["home_teams_without_country"]) == (2, 1)
    assert r["cheapest"] == ("B /venues?country", 2)
    assert vp.main(["--from-dir", str(tmp_path)]) == 0 and "CHEAPEST: B /venues?country = 2 calls" in capsys.readouterr().out
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert vp.main(["--from-dir", os.path.join(root, "data", "x")]) == 2


def test_a_served_country_key_is_route_zero(tmp_path):
    it = _fx(1, 10, 100, "Munich")
    it["fixture"]["venue"]["country"] = "Germany"
    json.dump({"response": [it]}, open(tmp_path / "fixtures_5_2022.json", "w"))
    r = vp.analyse(str(tmp_path))
    assert r["served_country_keys"] == ["country"] and r["cheapest"] == ("0 fixture.venue.country", 0)
