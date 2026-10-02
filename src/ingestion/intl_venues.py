"""
intl-neutral-v3 INGEST (ARCHITECT 2026-10-02, intl-elo-v2 (b)): "neutral rule
v3 (venue country != home team's country) replaces v2 — route B, 218 calls,
run on the laptop as an ingest step before v2's run; derived, labelled."

  1. Venue ids per fixture come from the SAVED /fixtures responses of the
     intl-sync --save directory (0 calls), joined to OUR stored matches by
     external_ids["api_football"].
  2. Home-team country = teams.area (the /teams team.country intl-sync
     stored). The DISTINCT home countries are route B's call list.
  3. /venues?country=<home country>, one call each (route B). The response
     maps venue id -> country, as served. Its field names are DISCOVERED and
     printed (law 1); a response without "id" and "country" refuses the run.
  4. neutral_v3 = norm(venue country) != norm(home country); either unknown
     -> NULL. Stored in intl_match_venue with NEUTRAL_V3_RULE. A venue in a
     country no home team belongs to stays unknown (counted).

--plan prints the call count and stops. --max-calls refuses an over-budget
plan. --venues-dir saves (and on a re-run replays) the /venues responses.
Never touches data/. Upsert; never deletes.
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter

NEUTRAL_V3_RULE = ("intl-neutral-v3 (ARCHITECT 2026-10-02; intl-elo-v2): neutral_v3 = norm(venue country, "
                   "API-Football /venues as served) != norm(home team's country, /teams team.country); norm = "
                   "NFKD, combining marks dropped, casefold, whitespace collapsed; either unknown -> NULL. "
                   "Derived by us — never a provider fact.")


class VenueError(RuntimeError):
    pass


def _slug(country: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", country.casefold()).strip("_")


def fixture_venues(save_dir: str) -> dict[str, int | None]:
    """provider fixture id -> venue id, from the saved /fixtures responses."""
    out = {}
    files = sorted(glob.glob(os.path.join(save_dir, "fixtures_*.json")))
    if not files:
        raise VenueError(f"REFUSED: no fixtures_*.json under {save_dir} (the intl-sync --save directory)")
    for f in files:
        with open(f) as fh:
            for it in json.load(fh).get("response") or []:
                fx = it.get("fixture") or {}
                if fx.get("id") is not None:
                    out[str(fx["id"])] = (fx.get("venue") or {}).get("id")
    return out


def sync(save_dir: str, venues_dir: str | None = None, plan_only: bool = False, max_calls: int = 230,
         root: str | None = None, client=None) -> dict:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, IntlMatchVenue, Match, Team
    from src.ingestion.intl_history import CODE_BY_NAME, norm_city

    root = root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for d in (save_dir, venues_dir):
        if d and os.path.abspath(d).startswith(os.path.join(root, "data")):
            raise VenueError("REFUSED: never write or read venue files under data/ (law 5)")
    fv = fixture_venues(save_dir)
    codes = tuple(code for _, code in CODE_BY_NAME)
    with session_scope() as s:
        comps = [c.id for c in s.execute(select(Competition).where(Competition.code.in_(codes))).scalars()]
        area = {t.id: t.area for t in s.execute(select(Team)).scalars()}
        rows = []
        for m in s.execute(select(Match).where(Match.competition_id.in_(comps))).scalars():
            sid = (m.external_ids or {}).get("api_football")
            if sid in fv:
                rows.append((m.id, fv[sid], area.get(m.home_team_id)))
        s.rollback()
    countries = sorted({c for _, _, c in rows if c})
    plan = {"matches": len(rows), "with_venue_id": sum(1 for _, v, _ in rows if v is not None),
            "home_country_known": sum(1 for _, _, c in rows if c), "calls": len(countries), "countries": countries}
    if plan_only:
        return {"plan": plan}
    if venues_dir:
        os.makedirs(venues_dir, exist_ok=True)
    need = [c for c in countries
            if not (venues_dir and os.path.exists(os.path.join(venues_dir, f"venues_{_slug(c)}.json")))]
    if len(need) > max_calls:
        raise VenueError(f"REFUSED: {len(need)} /venues calls > --max-calls {max_calls}")
    if need and client is None:
        from src.adapters.api_football import APIFootballAdapter
        try:
            client = APIFootballAdapter()
        except ValueError as e:
            raise VenueError(f"REFUSED: {e}") from None
    venue_country, keys, calls = {}, Counter(), 0
    for c in countries:
        path = os.path.join(venues_dir, f"venues_{_slug(c)}.json") if venues_dir else None
        if path and os.path.exists(path):
            with open(path) as fh:
                payload = json.load(fh)
        else:
            payload = client._get("venues", {"country": c})
            calls += 1
            if path:
                with open(path, "w") as fh:
                    json.dump(payload, fh)
        for v in payload.get("response") or []:
            keys.update(v.keys())          # count KEYS (law-1 receipt); update(dict) would add values
            if v.get("id") is not None:
                venue_country[v["id"]] = v.get("country")
    if venue_country and not {"id", "country"} <= set(keys):
        raise VenueError("REFUSED (law 1): /venues response lacks id/country; keys served: " + ", ".join(sorted(keys)))
    out = Counter()
    with session_scope() as s:
        for mid, vid, hc in rows:
            vc = venue_country.get(vid) if vid is not None else None
            a, b = norm_city(vc), norm_city(hc)
            flag = None if a is None or b is None else a != b
            r = s.get(IntlMatchVenue, mid) or IntlMatchVenue(match_id=mid, rule=NEUTRAL_V3_RULE)
            r.venue_id, r.venue_country, r.home_country, r.neutral_v3, r.rule = vid, vc, hc, flag, NEUTRAL_V3_RULE
            s.add(r)
            out["unknown" if flag is None else "neutral" if flag else "home"] += 1
            if vid is not None and vid not in venue_country:
                out["venue_not_in_any_queried_country"] += 1
    return {"plan": plan, "calls": calls, "venue_keys": dict(keys), "venues_resolved": len(venue_country),
            "neutral_v3": dict(out)}
