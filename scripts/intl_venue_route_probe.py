"""
#220 intl-neutral-v3 ROUTE PROBE — read-only, ZERO provider calls.
ARCHITECT 2026-10-02: "Pre-declare v3 now so no further ruling blocks the run:
neutral_v3 = venue COUNTRY != home team's country ... Needs venue country per
fixture — report the cheapest route (fixture venue fields vs /venues) and its
call count; derive, label, never a provider fact."

Reads the `intl-sync --save` directory (fixtures_*.json, teams_*.json) and
reports, law 1 (enumerated, never assumed):
  * every key the provider serves under fixture.venue (if one names a
    country, route 0 = 0 calls);
  * fixtures with a venue id, and the DISTINCT venue ids
    (route A = /venues?id=<id>, one call per distinct id);
  * the DISTINCT home-team countries from /teams team.country
    (route B = /venues?country=<name>, one call per country; resolves every
    venue in those countries by id — a venue in a country no home team
    belongs to stays unknown, counted);
  * the cheapest route and its call count.

    python3 scripts/intl_venue_route_probe.py --from-dir <the intl-sync --save dir>
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTRY_KEY = re.compile(r"country", re.I)


def analyse(d: str) -> dict:
    venue_keys, ids, no_id, n = Counter(), set(), 0, 0
    home_ids = set()
    for f in sorted(glob.glob(os.path.join(d, "fixtures_*.json"))):
        for it in json.load(open(f)).get("response") or []:
            n += 1
            v = (it.get("fixture") or {}).get("venue") or {}
            venue_keys.update(k for k in v)
            if v.get("id") is None:
                no_id += 1
            else:
                ids.add(v["id"])
            h = ((it.get("teams") or {}).get("home") or {}).get("id")
            if h is not None:
                home_ids.add(h)
    country_of = {}
    for f in sorted(glob.glob(os.path.join(d, "teams_*.json"))):
        for it in json.load(open(f)).get("response") or []:
            t = it.get("team") or {}
            if t.get("id") is not None and t.get("country"):
                country_of[t["id"]] = t["country"]
    countries = {country_of[h] for h in home_ids if h in country_of}
    served_country = sorted(k for k in venue_keys if COUNTRY_KEY.search(k))
    routes = {"A /venues?id": len(ids), "B /venues?country": len(countries)}
    if served_country:
        routes["0 fixture.venue." + served_country[0]] = 0
    best = min(routes.items(), key=lambda kv: (kv[1], not kv[0].startswith("0 ")))   # a served country wins ties
    return {"fixtures": n, "venue_keys": dict(venue_keys), "served_country_keys": served_country,
            "venue_ids": len(ids), "fixtures_without_venue_id": no_id, "home_teams": len(home_ids),
            "home_teams_without_country": len(home_ids - set(country_of)), "home_countries": len(countries),
            "routes": routes, "cheapest": best}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir", required=True, help="the intl-sync --save directory")
    a = ap.parse_args(argv)
    if os.path.abspath(a.from_dir).startswith(os.path.join(ROOT, "data")):
        print("REFUSED: never read probe files under data/ (law 5)")
        return 2
    r = analyse(a.from_dir)
    if not r["fixtures"]:
        print(f"REFUSED: no fixtures_*.json under {a.from_dir}")
        return 2
    print("INTL v3 ROUTE PROBE (#220) · read-only · 0 provider calls")
    print(f"  fixtures {r['fixtures']} · fixture.venue keys served (law 1): "
          + ", ".join(f"{k} ×{v}" for k, v in sorted(r["venue_keys"].items())))
    print("  country under fixture.venue: " + (", ".join(r["served_country_keys"]) or "NONE served"))
    print(f"  distinct venue ids {r['venue_ids']} · fixtures without a venue id {r['fixtures_without_venue_id']}")
    print(f"  home teams {r['home_teams']} · their distinct /teams countries {r['home_countries']} · "
          f"home teams with no country {r['home_teams_without_country']}")
    for k, v in sorted(r["routes"].items(), key=lambda kv: kv[1]):
        print(f"  route {k}: {v} calls")
    print(f"  CHEAPEST: {r['cheapest'][0]} = {r['cheapest'][1]} calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
