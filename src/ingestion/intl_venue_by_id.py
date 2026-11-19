"""THE BY-ID VENUE RECEIPT (ARCHITECT 2026-11-19, addendum 433 item 4), read-only tooling.

433 item 4, verbatim: "For every venue id stored on a copy (--db COPY, 346's fence; 623 on today's): the provider's
answer by id, one call each, the answers kept under logs/, a call cap, resumable from the kept answers. It prints
counts: ids whose by-id country agrees with the stored country, differs, or is not served; and for each id that
differs, its stored games by home country with the flag now and the flag under the by-id country, the cohort fixtures
among them named. It reads no score and no result, writes no row, and prints no log-loss."

Why (433 items 1-2): the stored venue country comes from intl-venue-sync's one dictionary across the /venues?country
answers, the later country's answer writing last, while the provider files a ground under every country it lists it
with. This receipt asks the provider by id instead, for every stored venue id, and says where the two disagree. The
architect rules the mended derivation on it (433 item 3(e)); nothing here is a correction and nothing is applied.

What it reads: intl_match_venue's own columns (venue id, the stored venue country, the stored home country, the stored
flag) on a .backup copy under addendum 346's fence (mode=ro + immutable=1); the frozen confirmation cohort's ids from
the registry's verified file (registry.frozen_cohort; no match row is read); the kept by-id answers; and, with
--fixtures-dir, the saved /fixtures files' own venue object per fixture (intl_venues.fixture_venue_fields: venue id,
name, city), which shows an id the provider names under two grounds (433 item 1(e)). No score, no result, no row
written, no log-loss.

The flag under the by-id country is neutral_v3's own rule (intl-neutral-v3): norm(by-id country) != norm(home
country), either unknown -> unknown. norm is intl_history.norm_city.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

RULING = "ARCHITECT 2026-11-19, addendum 433 item 4"
DEFAULT_OUT = os.path.join("logs", "venue_by_id")
DEFAULT_CAP = 700


class ByIdRefused(RuntimeError):
    """The receipt refuses; nothing is read or written past the refusal."""


def _norm(x):
    from src.ingestion.intl_history import norm_city
    return norm_city(x)


def _flag(home_country, venue_country) -> bool | None:
    """neutral_v3's rule (intl-neutral-v3): venue country != home country, either unknown -> None."""
    a, b = _norm(venue_country), _norm(home_country)
    return None if a is None or b is None else a != b


def _flag_text(v) -> str:
    return "unknown" if v is None else "neutral" if v else "home"


def answer_path(out_dir, vid) -> Path:
    """The kept answer of one id: venue_id_<id>.json, the same name intl-venue-resolve's route A keeps."""
    return Path(out_dir) / f"venue_id_{int(vid)}.json"


def check_out_dir(out_dir, root: str | None = None) -> Path:
    """The answers' folder, never under the repo's data/ (law 5)."""
    root = root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = Path(out_dir)
    data = Path(root, "data").resolve()
    rp = p.resolve()
    if rp == data or data in rp.parents:
        raise ByIdRefused(f"--out-dir {out_dir}: under data/ (law 5); nothing read, nothing written")
    return p


def stored_venues(s) -> dict[int, list[tuple]]:
    """venue id -> [(match id, stored venue country, stored home country, stored neutral_v3)], from intl_match_venue's
    own columns only (no match row, no score)."""
    from sqlalchemy import select

    from src.db.schema import IntlMatchVenue
    out: dict[int, list[tuple]] = defaultdict(list)
    q = (select(IntlMatchVenue.match_id, IntlMatchVenue.venue_id, IntlMatchVenue.venue_country,
                IntlMatchVenue.home_country, IntlMatchVenue.neutral_v3)
         .where(IntlMatchVenue.venue_id.isnot(None)).order_by(IntlMatchVenue.venue_id, IntlMatchVenue.match_id))
    for mid, vid, vc, hc, flag in s.execute(q).all():
        out[int(vid)].append((mid, vc, hc, flag))
    return dict(out)


def cohort_ids() -> tuple[set[int] | None, str]:
    """The frozen confirmation cohort's ids from the registry's verified file (no database); (None, why) else."""
    try:
        from src.walters import intl_elo as ie
        from src.walters import registry as reg
        e = reg.get(ie.EID_V2)
        if e is None:
            return None, f"{ie.EID_V2} not in the registry"
        ids = reg.frozen_cohort(e)
        if ids is None:
            return None, "no frozen cohort"
        return set(ids), f"frozen ({len(ids)} ids)"
    except Exception as err:  # noqa: BLE001 - the receipt says why; the counts still print
        return None, f"not read: {type(err).__name__}: {err}"


def fetch(vids, out_dir, max_calls: int = DEFAULT_CAP, client=None, plan_only: bool = False) -> dict:
    """The by-id answers: a kept answer is replayed (no call); every other id is asked once (/venues?id=<id>), the
    answer written under out_dir BEFORE it is used, until max_calls calls this run. A failed call stops the run
    there (what is kept stays kept; a re-run resumes). Returns {"answers": {vid: payload}, "calls", "kept_before",
    "not_asked": [vids], "stopped": reason or None}."""
    out_dir = Path(out_dir)
    vids = sorted(set(int(v) for v in vids))
    kept = [v for v in vids if answer_path(out_dir, v).exists()]
    need = [v for v in vids if not answer_path(out_dir, v).exists()]
    r = {"answers": {}, "calls": 0, "kept_before": len(kept), "need": len(need), "not_asked": [], "stopped": None}
    for v in kept:
        try:
            r["answers"][v] = json.loads(answer_path(out_dir, v).read_text())
        except (OSError, ValueError) as err:
            raise ByIdRefused(f"the kept answer {answer_path(out_dir, v)} cannot be read ({err}); move it aside and "
                              "re-run; nothing written") from None
    if plan_only:
        r["not_asked"] = need
        return r
    if need and client is None:
        try:
            client = _client()
        except ValueError as err:
            raise ByIdRefused(f"{err}; {len(need)} ids not yet asked; nothing written") from None
    if need:
        out_dir.mkdir(parents=True, exist_ok=True)
    for i, v in enumerate(need):
        if r["calls"] >= max_calls:
            r["not_asked"] = need[i:]
            r["stopped"] = f"the call cap ({max_calls}) reached"
            break
        try:
            payload = client._get("venues", {"id": v})
        except Exception as err:  # noqa: BLE001 - stop where it failed; what is kept stays kept
            r["not_asked"] = need[i:]
            r["stopped"] = f"the call for venue {v} failed ({type(err).__name__}: {err})"
            break
        r["calls"] += 1
        answer_path(out_dir, v).write_text(json.dumps(payload))   # kept BEFORE it is used (a re-run replays it)
        r["answers"][v] = payload
    return r


def _client():
    """The provider (API-Football); constructed only when an id is to be asked."""
    from src.adapters.api_football import APIFootballAdapter
    return APIFootballAdapter()


def _served(payload, vid) -> list[dict]:
    return [x for x in (payload or {}).get("response") or [] if isinstance(x, dict) and x.get("id") == vid]


def grounds_from_fixtures(fixtures_dir) -> dict[int, set[tuple]]:
    """venue id -> the distinct (name, city) the saved /fixtures files name for it (fixture.venue, as served)."""
    from src.ingestion import intl_venues as iv
    out: dict[int, set[tuple]] = defaultdict(set)
    for v in iv.fixture_venue_fields(str(fixtures_dir)).values():
        if v.get("id") is not None:
            out[int(v["id"])].add((v.get("name"), v.get("city")))
    return dict(out)


def classify(stored: dict, fetched: dict, cohort: set[int] | None, grounds: dict | None = None) -> dict:
    """The receipt's content: per stored venue id, the by-id answer against the stored country."""
    answers = fetched["answers"]
    keys = Counter()
    out = {"agrees": [], "differs": [], "not_served": [], "several": [], "not_asked": list(fetched["not_asked"])}
    for vid, rows in sorted(stored.items()):
        if vid not in answers:
            continue
        served = _served(answers[vid], vid)
        for x in (answers[vid] or {}).get("response") or []:
            if isinstance(x, dict):
                keys.update(x.keys())
        countries = sorted({x.get("country") for x in served if x.get("country")}, key=str)
        if not countries:
            out["not_served"].append(vid)
            continue
        if len({_norm(c) for c in countries}) > 1:
            out["several"].append({"venue_id": vid, "countries": countries})
            continue
        byid = countries[0]
        if all(_norm(vc) == _norm(byid) for _, vc, _, _ in rows):
            out["agrees"].append(vid)
            continue
        by_home: dict = defaultdict(lambda: {"n": 0, "now": Counter(), "byid": Counter(), "cohort": [],
                                             "changes": 0})
        for mid, vc, hc, flag in rows:
            g = by_home[hc]
            g["n"] += 1
            after = _flag(hc, byid)
            g["now"][_flag_text(flag)] += 1
            g["byid"][_flag_text(after)] += 1
            g["changes"] += after != flag
            if cohort is not None and mid in cohort:
                g["cohort"].append(mid)
        ground = served[0]
        out["differs"].append({
            "venue_id": vid, "stored": sorted({vc for _, vc, _, _ in rows}, key=lambda c: (c is None, str(c))),
            "byid": byid, "byid_name": ground.get("name"), "byid_city": ground.get("city"),
            "games": len(rows), "by_home": dict(by_home),
            "fixture_grounds": sorted((grounds or {}).get(vid, set()), key=str) if grounds is not None else None})
    out["keys"] = sorted(keys)
    out["stored_ids"] = len(stored)
    out["stored_rows"] = sum(len(v) for v in stored.values())
    out["games_changing"] = sum(g["changes"] for d in out["differs"] for g in d["by_home"].values())
    out["cohort_at_differing"] = sorted(m for d in out["differs"] for g in d["by_home"].values() for m in g["cohort"])
    if grounds is not None:
        out["two_grounds"] = sorted(v for v, gs in grounds.items() if v in stored and len(gs) > 1)
    return out


def _counter_text(c: Counter) -> str:
    return "/".join(f"{k} {c[k]}" for k in ("neutral", "home", "unknown") if c[k]) or "none"


def lines(r: dict, fetched: dict, out_dir, cap: int, cohort_why: str) -> list[str]:
    done = not r["not_asked"]
    L = [f"INTL-VENUE-BY-ID ({RULING}) · read-only: no score, no result, no row written, no log-loss · "
         + ("COMPLETE" if done else f"INCOMPLETE: {len(r['not_asked'])} ids not yet asked")
         + f" · the confirmation cohort: {cohort_why}",
         f"  stored venue ids on the copy {r['stored_ids']} (rows with a venue id {r['stored_rows']}) · answers kept "
         f"under {out_dir}: {fetched['kept_before']} before this run · provider calls this run {fetched['calls']} "
         f"(cap {cap})"]
    if fetched["stopped"]:
        L.append(f"  STOPPED: {fetched['stopped']}; re-run to continue from the kept answers")
    L.append(f"  by-id country: agrees {len(r['agrees'])} · differs {len(r['differs'])} · not served "
             f"{len(r['not_served'])} · served under more than one country {len(r['several'])} · not yet asked "
             f"{len(r['not_asked'])}")
    L.append("  keys served by id (law 1): " + (", ".join(r["keys"]) or "none"))
    L.append(f"  games at a differing id whose flag changes under the by-id country: {r['games_changing']} · cohort "
             f"fixtures at a differing id: {len(r['cohort_at_differing'])}"
             + (" — " + ", ".join(map(str, r["cohort_at_differing"])) if r["cohort_at_differing"] else ""))
    if "two_grounds" in r:
        L.append(f"  stored ids the saved fixtures name under two or more grounds: {len(r['two_grounds'])}"
                 + (" — " + ", ".join(map(str, r["two_grounds"])) if r["two_grounds"] else ""))
    L.append(f"  DIFFERS ({len(r['differs'])}):")
    for d in r["differs"]:
        stored = ", ".join("unknown" if c is None else str(c) for c in d["stored"])
        L.append(f"    venue {d['venue_id']}: stored {stored} -> by id {d['byid']} ({d['byid_name']}, {d['byid_city']}) "
                 f"· {d['games']} stored games")
        for hc, g in sorted(d["by_home"].items(), key=lambda kv: (kv[0] is None, str(kv[0]))):
            L.append(f"      home {hc or 'unknown'}: {g['n']} · flag now {_counter_text(g['now'])} · under the by-id "
                     f"country {_counter_text(g['byid'])}"
                     + (f" · COHORT {', '.join(map(str, g['cohort']))}" if g["cohort"] else ""))
        if d["fixture_grounds"] is not None:
            L.append("      the saved fixtures name it: " + ("; ".join(f"{n}, {c}" for n, c in d["fixture_grounds"])
                                                            or "no saved fixture"))
    if r["several"]:
        L.append(f"  SERVED UNDER MORE THAN ONE COUNTRY ({len(r['several'])}): "
                 + "; ".join(f"{x['venue_id']} ({', '.join(x['countries'])})" for x in r["several"]))
    if r["not_served"]:
        L.append(f"  NOT SERVED BY ID ({len(r['not_served'])}): " + ", ".join(map(str, r["not_served"])))
    return L
