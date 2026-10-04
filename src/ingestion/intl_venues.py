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


# ---------------------------------------------------------------------------
# VENUE-COUNTRY NORMALIZATION (ARCHITECT build lane 5, 2026-10-04; data lane
# only — intl-elo-v2 stays frozen through its window and never reads this).
# For every match v3 left unknown (intl_match_venue.neutral_v3 NULL):
#   1. venue id served but not in the route-B catalog (a venue in a country no
#      home team belongs to — "unmatched venues"): route A, /venues?id=<id>,
#      one call per distinct id, budget-capped, saved as venue_id_<id>.json and
#      replayed on a re-run;
#   2. no venue id served: the fixture's venue city, then its name, against
#      the saved /venues catalog — a UNIQUE country only (several countries =
#      ambiguous, refused and counted; never guessed);
#   3. country spelling: norm (NFKD, marks dropped, casefold) on both sides,
#      plus an OPTIONAL pinned alias file (--aliases). No alias is built in:
#      the receipt lists every home-country spelling with no exact match in
#      the venue vocabulary, so a ruling can pin it (law 1).
#   A NEUTRAL reading whose home-country spelling never appears as a venue
#   country in the catalog stays unknown ("alias needed"): a spelling gap
#   ("Korea Republic" vs "South Korea") must not read as a neutral venue.
# Stored in intl_venue_resolved; intl_match_venue is never touched.
# ---------------------------------------------------------------------------

RESOLVE_RULE = ("intl-venue-resolve (ARCHITECT lane 5, 2026-10-04; data lane, not read by intl-elo-v2): for rows "
                "with neutral_v3 NULL, venue country = /venues?id (route A) for venue ids outside the route-B "
                "catalog, else a UNIQUE city or name match in the saved /venues catalog; neutral_resolved = "
                "norm(venue country) != norm(home country) after the pinned aliases (if any); either unknown -> "
                "NULL with a reason. Derived by us — never a provider fact.")


def venue_catalog(venues_dir: str) -> dict[int, dict]:
    """venue id -> {country, city, name} from every saved /venues response
    (route B venues_<country>.json and route A venue_id_<id>.json)."""
    cat: dict[int, dict] = {}
    for f in sorted(glob.glob(os.path.join(venues_dir, "venue*.json"))):
        with open(f) as fh:
            payload = json.load(fh)
        for v in payload.get("response") or []:
            if v.get("id") is not None:
                cat[v["id"]] = {"country": v.get("country"), "city": v.get("city"), "name": v.get("name")}
    return cat


def fixture_venue_fields(save_dir: str) -> dict[str, dict]:
    """provider fixture id -> the served fixture.venue object ({id, name, city})."""
    out = {}
    for f in sorted(glob.glob(os.path.join(save_dir, "fixtures_*.json"))):
        with open(f) as fh:
            for it in json.load(fh).get("response") or []:
                fx = it.get("fixture") or {}
                if fx.get("id") is not None:
                    out[str(fx["id"])] = fx.get("venue") or {}
    return out


def _unique_index(cat: dict, field: str, norm) -> dict[str, set]:
    idx: dict[str, set] = {}
    for v in cat.values():
        k, c = norm(v.get(field)), v.get("country")
        if k and c:
            idx.setdefault(k, set()).add(c)
    return idx


def resolve(save_dir: str, venues_dir: str, aliases: dict | None = None, plan_only: bool = False,
            max_calls: int = 400, root: str | None = None, client=None) -> dict:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue, IntlVenueResolved, Match
    from src.ingestion.intl_history import norm_city

    root = root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for d in (save_dir, venues_dir):
        if os.path.abspath(d).startswith(os.path.join(root, "data")):
            raise VenueError("REFUSED: never write or read venue files under data/ (law 5)")
    if not os.path.isdir(venues_dir):
        raise VenueError(f"REFUSED: --venues-dir {venues_dir} not found (the intl-venue-sync --venues-dir)")
    amap = {norm_city(k): norm_city(v) for k, v in (aliases or {}).items() if norm_city(k) and norm_city(v)}

    def ncountry(c):
        n = norm_city(c)
        return amap.get(n, n) if n else None

    fv = fixture_venue_fields(save_dir)
    cat = venue_catalog(venues_dir)
    with session_scope() as s:
        total = s.query(IntlMatchVenue).count()
        known_v3 = s.query(IntlMatchVenue).filter(IntlMatchVenue.neutral_v3.isnot(None)).count()
        rows = []
        for r, ext in s.execute(select(IntlMatchVenue, Match.external_ids)
                                .join(Match, Match.id == IntlMatchVenue.match_id)
                                .where(IntlMatchVenue.neutral_v3.is_(None))).all():
            rows.append({"match_id": r.match_id, "venue_id": r.venue_id, "venue_country": r.venue_country,
                         "home_country": r.home_country,
                         "fixture_venue": fv.get(str((ext or {}).get("api_football")), {})})
        s.rollback()
    reasons = Counter()
    for r in rows:
        if not r["home_country"]:
            reasons["home country unknown"] += 1
        elif r["venue_id"] is None:
            reasons["no venue id served"] += 1
        elif r["venue_id"] not in cat:
            reasons["venue id outside the route-B catalog"] += 1
        else:
            reasons["venue country not served"] += 1
    need = sorted({r["venue_id"] for r in rows if r["venue_id"] is not None and r["venue_id"] not in cat})
    to_fetch = [v for v in need if not os.path.exists(os.path.join(venues_dir, f"venue_id_{v}.json"))]
    plan = {"v3_rows": total, "v3_known": known_v3, "v3_unknown": len(rows), "reasons": dict(reasons),
            "route_a_ids": len(need), "route_a_calls": len(to_fetch)}
    if plan_only:
        return {"plan": plan}
    if len(to_fetch) > max_calls:
        raise VenueError(f"REFUSED: {len(to_fetch)} /venues?id calls > --max-calls {max_calls}")
    calls = 0
    if to_fetch and client is None:
        from src.adapters.api_football import APIFootballAdapter
        try:
            client = APIFootballAdapter()
        except ValueError as e:
            raise VenueError(f"REFUSED: {e}") from None
    for vid in to_fetch:
        payload = client._get("venues", {"id": vid})
        calls += 1
        with open(os.path.join(venues_dir, f"venue_id_{vid}.json"), "w") as fh:   # saved BEFORE use (replay)
            json.dump(payload, fh)
    if to_fetch:
        cat = venue_catalog(venues_dir)
    by_city = _unique_index(cat, "city", norm_city)
    by_name = _unique_index(cat, "name", norm_city)
    out, vocab_home, vocab_venue = Counter(), Counter(), set()
    vocab_venue.update(ncountry(v["country"]) for v in cat.values() if v.get("country"))
    with session_scope() as s:
        for r in rows:
            vc, src, why = None, None, None
            if r["venue_id"] is not None and r["venue_id"] in cat and cat[r["venue_id"]].get("country"):
                vc = cat[r["venue_id"]]["country"]
                src = "venues_by_id" if os.path.exists(os.path.join(venues_dir, f"venue_id_{r['venue_id']}.json")) \
                    else "venues_by_country"
            elif r["venue_id"] is not None:
                why = "venue id not served by /venues?id" if r["venue_id"] in need else "venue country not served"
            else:
                fvn = r["fixture_venue"] or {}
                for field, idx, tag in (("city", by_city, "city_match"), ("name", by_name, "name_match")):
                    hits = idx.get(norm_city(fvn.get(field)) or "", set())
                    if len(hits) == 1:
                        vc, src = next(iter(hits)), tag
                        break
                    if len(hits) > 1:
                        why = f"{field} {fvn.get(field)!r} in {len(hits)} countries (ambiguous, never guessed)"
                        break
                else:
                    why = "no venue id; city/name not in the /venues catalog" if (fvn.get("city") or fvn.get("name")) \
                        else "no venue id, city or name served"
            hc = r["home_country"]
            if hc:
                vocab_home[ncountry(hc)] += 1
            a, b = ncountry(vc), ncountry(hc)
            flag = None if a is None or b is None else a != b
            if flag and b not in vocab_venue:          # law 4: a spelling never served as a venue country
                flag, why = None, "home-country spelling not in the /venues vocabulary (alias needed)"
            if flag is None and why is None:
                why = "home country unknown" if b is None else "venue country unknown"
            row = s.get(IntlVenueResolved, r["match_id"]) or IntlVenueResolved(match_id=r["match_id"], rule=RESOLVE_RULE)
            row.venue_id, row.venue_country, row.home_country = r["venue_id"], vc, hc
            row.country_source, row.neutral_resolved, row.reason, row.rule = src, flag, (None if flag is not None else why), RESOLVE_RULE
            s.add(row)
            out[("resolved: " + ("neutral" if flag else "home") + f" via {src}") if flag is not None
                else ("unknown: city/name ambiguous across countries" if "ambiguous" in why else f"unknown: {why}")] += 1
    unmatched_spellings = sorted(k for k in vocab_home if k not in vocab_venue)
    resolved = sum(v for k, v in out.items() if k.startswith("resolved"))
    return {"plan": plan, "calls": calls, "catalog_venues": len(cat), "outcomes": dict(out), "resolved": resolved,
            "unflagged_before": len(rows), "unflagged_after": len(rows) - resolved,
            "home_spellings_not_in_venue_vocab": unmatched_spellings, "aliases": len(amap)}
