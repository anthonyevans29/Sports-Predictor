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


def check_out_dir(out_dir, data_dirs=None) -> Path:
    """The answers' folder, never under the repo's data/ (law 5), by the same keys --db's fence uses
    (mlb_pitchers_gate._data_dirs: this checkout's data/ and, from a worktree, the main checkout's; and every folder a
    data/ links to). `data_dirs`: given in tests."""
    from src.walters import mlb_pitchers_gate as mp
    tgt = Path(out_dir).expanduser().resolve()
    try:
        for data in (data_dirs if data_dirs is not None else mp._data_dirs()):
            data = Path(data).resolve()
            if tgt == data or data in tgt.parents:
                raise ByIdRefused(f"--out-dir {out_dir}: under data/ ({data}; law 5); nothing read, nothing written")
            for d in mp._data_tree(data)[1]:
                if tgt == d or d in tgt.parents:
                    raise ByIdRefused(f"--out-dir {out_dir}: under {d}, a folder data/ links to (law 5); nothing "
                                      "read, nothing written")
    except mp.GateRefused as e:
        raise ByIdRefused(f"{e}; nothing written") from None
    return Path(out_dir)


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
    if need and client is None and max_calls > 0:            # a zero cap asks nothing: no provider needed
        try:
            client = _client()
        except ValueError as err:
            raise ByIdRefused(f"{err}; {len(need)} ids not yet asked; nothing written") from None
    if need:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise ByIdRefused(f"--out-dir {out_dir}: cannot be made ({err}); nothing asked") from None
    for i, v in enumerate(need):
        if r["calls"] >= max_calls:
            r["not_asked"] = need[i:]
            r["stopped"] = f"the call cap ({max_calls}) reached"
            break
        r["calls"] += 1                                  # every attempt counts, a failed one too (the cap and the receipt)
        try:
            payload = client._get("venues", {"id": v})
        except Exception as err:  # noqa: BLE001 - stop where it failed; what is kept stays kept
            r["not_asked"] = need[i:]
            r["stopped"] = f"the call for venue {v} failed ({type(err).__name__}: {err})"
            break
        try:
            _keep(answer_path(out_dir, v), payload)       # kept BEFORE it is used (a re-run replays it)
        except OSError as err:
            r["not_asked"] = need[i:]
            r["stopped"] = f"the answer for venue {v} could not be kept ({err}); it is asked again on a re-run"
            break
        r["answers"][v] = payload
    return r


def _keep(path: Path, payload) -> None:
    """Write one answer atomically: a temporary file beside it, then a rename. A write that fails leaves no file at the
    answer's path (the temporary one is removed), so a re-run asks the id again and never reads a partial answer."""
    tmp = path.with_name(path.name + ".part")
    try:
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _client():
    """The provider (API-Football); constructed only when an id is to be asked."""
    from src.adapters.api_football import APIFootballAdapter
    return APIFootballAdapter()


def _served(payload, vid) -> list[dict]:
    return [x for x in (payload or {}).get("response") or [] if isinstance(x, dict) and x.get("id") == vid]


def grounds_from_fixtures(fixtures_dir) -> tuple[dict[int, set[tuple]], int, int]:
    """(venue id -> the distinct (name, city) the saved /fixtures files name for it (fixture.venue, as served), files
    read, fixtures with a venue id). A folder that is not one, holds no fixtures_*.json, or holds one that cannot be
    read is refused (ByIdRefused), never read as "no saved fixture"."""
    import glob

    from src.ingestion import intl_venues as iv
    d = Path(fixtures_dir)
    if not d.is_dir():
        raise ByIdRefused(f"--fixtures-dir {fixtures_dir}: not a directory; nothing asked")
    files = sorted(glob.glob(os.path.join(str(d), "fixtures_*.json")))
    if not files:
        raise ByIdRefused(f"--fixtures-dir {fixtures_dir}: no fixtures_*.json (the intl-sync --save folder); nothing "
                          "asked")
    try:
        venues = iv.fixture_venue_fields(str(d))
    except (OSError, ValueError) as err:
        raise ByIdRefused(f"--fixtures-dir {fixtures_dir}: a saved file cannot be read ({err}); nothing asked") from None
    out: dict[int, set[tuple]] = defaultdict(set)
    n = 0
    for v in venues.values():
        if v.get("id") is not None:
            out[int(v["id"])].add((v.get("name"), v.get("city")))
            n += 1
    return dict(out), len(files), n


def _detail(rows, byid, cohort) -> tuple[dict, int, int]:
    """A differing (or stored-unknown) id's stored games by home country: the flag now and under the by-id country,
    the cohort fixtures named. (by_home, known flags that flip, unknown flags that become known)."""
    by_home: dict = defaultdict(lambda: {"n": 0, "now": Counter(), "byid": Counter(), "cohort": []})
    flips = known = 0
    for mid, vc, hc, flag in rows:
        g = by_home[hc]
        g["n"] += 1
        after = _flag(hc, byid)
        g["now"][_flag_text(flag)] += 1
        g["byid"][_flag_text(after)] += 1
        if flag is not None and after is not None and flag != after:
            flips += 1
        elif flag is None and after is not None:
            known += 1
        if cohort is not None and mid in cohort:
            g["cohort"].append(mid)
    return dict(by_home), flips, known


def classify(stored: dict, fetched: dict, cohort: set[int] | None, grounds: dict | None = None) -> dict:
    """The receipt's content: per stored venue id, the by-id answer against the stored country. An id whose stored
    rows carry no venue country at all is "stored country unknown", never a disagreement (law 4); an id served by id
    with no country is "served without a country", never "not served"."""
    answers = fetched["answers"]
    keys = Counter()
    out = {"agrees": [], "differs": [], "stored_unknown": [], "served_no_country": [], "not_served": [],
           "several": [], "not_asked": list(fetched["not_asked"]), "games_flipping": 0, "games_unknown_to_known": 0,
           "cohort_read": cohort is not None}
    for vid, rows in sorted(stored.items()):
        if vid not in answers:
            continue
        served = _served(answers[vid], vid)
        for x in (answers[vid] or {}).get("response") or []:
            if isinstance(x, dict):
                keys.update(x.keys())
        if not served:
            out["not_served"].append(vid)
            continue
        countries = sorted({x.get("country") for x in served if x.get("country")}, key=str)
        if not countries:
            out["served_no_country"].append(vid)
            continue
        if len({_norm(c) for c in countries}) > 1:
            out["several"].append({"venue_id": vid, "countries": countries})
            continue
        byid = countries[0]
        known = [vc for _, vc, _, _ in rows if _norm(vc) is not None]
        if known and all(_norm(vc) == _norm(byid) for vc in known):
            out["agrees"].append(vid)
            continue
        by_home, flips, to_known = _detail(rows, byid, cohort)
        out["games_flipping"] += flips
        out["games_unknown_to_known"] += to_known
        ground = served[0]
        entry = {"venue_id": vid, "stored": sorted({vc for _, vc, _, _ in rows}, key=lambda c: (c is None, str(c))),
                 "byid": byid, "byid_name": ground.get("name"), "byid_city": ground.get("city"),
                 "games": len(rows), "by_home": by_home,
                 "fixture_grounds": sorted((grounds or {}).get(vid, set()), key=str) if grounds is not None else None}
        out["differs" if known else "stored_unknown"].append(entry)
    out["keys"] = sorted(keys)
    out["stored_ids"] = len(stored)
    out["stored_rows"] = sum(len(v) for v in stored.values())
    out["cohort_named"] = sorted(m for k in ("differs", "stored_unknown") for d in out[k]
                                 for g in d["by_home"].values() for m in g["cohort"])
    if grounds is not None:
        out["two_grounds"] = sorted(v for v, gs in grounds.items() if v in stored and len(gs) > 1)
    return out


def _counter_text(c: Counter) -> str:
    return "/".join(f"{k} {c[k]}" for k in ("neutral", "home", "unknown") if c[k]) or "none"


def _entry_lines(d: dict) -> list[str]:
    stored = ", ".join("unknown" if c is None else str(c) for c in d["stored"])
    L = [f"    venue {d['venue_id']}: stored {stored} -> by id {d['byid']} ({d['byid_name']}, {d['byid_city']}) "
         f"· {d['games']} stored games"]
    for hc, g in sorted(d["by_home"].items(), key=lambda kv: (kv[0] is None, str(kv[0]))):
        L.append(f"      home {hc or 'unknown'}: {g['n']} · flag now {_counter_text(g['now'])} · under the by-id "
                 f"country {_counter_text(g['byid'])}"
                 + (f" · COHORT {', '.join(map(str, g['cohort']))}" if g["cohort"] else ""))
    if d["fixture_grounds"] is not None:
        L.append("      the saved fixtures name it: " + ("; ".join(f"{n}, {c}" for n, c in d["fixture_grounds"])
                                                        or "no saved fixture"))
    return L


def lines(r: dict, fetched: dict, out_dir, cap: int, cohort_why: str, fixtures_read: tuple | None = None) -> list[str]:
    done = not r["not_asked"]
    L = [f"INTL-VENUE-BY-ID ({RULING}) · read-only: no score, no result, no row written, no log-loss · "
         + ("COMPLETE" if done else f"INCOMPLETE: {len(r['not_asked'])} ids not yet asked")
         + f" · the confirmation cohort: {cohort_why}",
         f"  stored venue ids on the copy {r['stored_ids']} (rows with a venue id {r['stored_rows']}) · answers kept "
         f"under {out_dir}: {fetched['kept_before']} before this run · provider calls this run {fetched['calls']} "
         f"(cap {cap})"]
    if fetched["stopped"]:
        L.append(f"  STOPPED: {fetched['stopped']}; re-run to continue from the kept answers")
    if fixtures_read is not None:
        L.append(f"  saved fixtures read: {fixtures_read[0]} files, {fixtures_read[1]} fixtures with a venue id")
    L.append(f"  by-id country: agrees {len(r['agrees'])} · differs {len(r['differs'])} · stored country unknown "
             f"{len(r['stored_unknown'])} · served without a country {len(r['served_no_country'])} · not served "
             f"{len(r['not_served'])} · served under more than one country {len(r['several'])} · not yet asked "
             f"{len(r['not_asked'])}")
    L.append("  keys served by id (law 1): " + (", ".join(r["keys"]) or "none"))
    cohort = (f"{len(r['cohort_named'])}" + (" — " + ", ".join(map(str, r["cohort_named"])) if r["cohort_named"] else "")
              if r["cohort_read"] else f"NOT READ ({cohort_why})")
    L.append(f"  games whose known flag flips under the by-id country: {r['games_flipping']} · games whose unknown "
             f"flag becomes known: {r['games_unknown_to_known']} · cohort fixtures at those ids: {cohort}")
    if "two_grounds" in r:
        L.append(f"  stored ids the saved fixtures name under two or more grounds: {len(r['two_grounds'])}"
                 + (" — " + ", ".join(map(str, r["two_grounds"])) if r["two_grounds"] else ""))
    L.append(f"  DIFFERS ({len(r['differs'])}):")
    for d in r["differs"]:
        L.extend(_entry_lines(d))
    if r["stored_unknown"]:
        L.append(f"  STORED COUNTRY UNKNOWN ({len(r['stored_unknown'])}; no /venues?country answer listed the id):")
        for d in r["stored_unknown"]:
            L.extend(_entry_lines(d))
    if r["several"]:
        L.append(f"  SERVED UNDER MORE THAN ONE COUNTRY ({len(r['several'])}): "
                 + "; ".join(f"{x['venue_id']} ({', '.join(x['countries'])})" for x in r["several"]))
    if r["served_no_country"]:
        L.append(f"  SERVED BY ID WITHOUT A COUNTRY ({len(r['served_no_country'])}): "
                 + ", ".join(map(str, r["served_no_country"])))
    if r["not_served"]:
        L.append(f"  NOT SERVED BY ID ({len(r['not_served'])}): " + ", ".join(map(str, r["not_served"])))
    return L
