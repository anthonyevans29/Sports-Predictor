"""
#176 NCAA SOURCE PROBE — read-only, row-level (ARCHITECT 2026-10-02: "moves
from offseason to THIS WEEK: read-only, row-level home/away and score
comparison against an independent source with neutral-site flags").

Why: our NCAA 2025 home labels match what api-sports serves today (a 0.489
home rate at the source, implausible for college football), so re-syncing
cannot repair them; the gate (#79) stays SUSPENDED-PENDING-DATA. This probe
measures an INDEPENDENT source (CollegeFootballData, CFBD) game by game.

LAW 1: the source's field names are DISCOVERED from the first record and
printed; a required field that cannot be found REFUSES the run (never
guessed). LAW 4: our DB stores no neutral flag — the source's neutral games
are counted separately and never relabel ours.

Per source game (completed, both scores): our match via the SHARED matcher
(find_match, ambiguity refused) in the source's orientation ("same"), else
the reverse ("swapped"), else unmatched. Then, row by row: label agreement,
score agreement (in our orientation), neutral flag. Reports, per year: the
source's home-label rate and home margin (non-neutral / neutral separately),
ours on the same joined games, join rate, swapped and score-mismatch samples,
access receipt (HTTP status, rate-limit headers; the key is never printed).

    CFBD_API_KEY=... python3 scripts/ncaa_source_probe.py --year 2025 --year 2026
    python3 scripts/ncaa_source_probe.py --from-file saved_cfbd_2025.json --year 2025

Writes NOTHING (no DB writes, no ingest path, no files unless --save).
"""
import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# The CFBD access pieces (field discovery, fetch, start-date parsing) live in
# src/ingestion/ncaa_cfbd.py since the label lane (ARCHITECT 2026-10-07); this
# probe keeps its own compare() so its 2026-10-07 read stays reproducible.
from src.ingestion.ncaa_cfbd import BASE, FIELDS, OPTIONAL, discover, fetch, parse_start  # noqa: E402,F401

SAMPLE = 15


def compare(records: list, keys: dict, session, division: str | None = None) -> dict:
    """Row-level comparison against OUR NCAA matches. Read-only."""
    from src.db.schema import Sport
    from src.ingestion.match_lookup import find_match

    out = Counter()
    swapped, score_bad, unmatched = [], [], []
    src = {"neutral": [], "nonneutral": []}
    ours_joined = {"neutral": [], "nonneutral": []}
    for rec in records:
        if keys["completed"] and rec.get(keys["completed"]) is False:
            out["source_not_completed"] += 1
            continue
        hp, ap = rec.get(keys["home_pts"]), rec.get(keys["away_pts"])
        if hp is None or ap is None:
            out["source_no_score"] += 1
            continue
        if division and keys["home_class"] and keys["away_class"] and \
                (str(rec.get(keys["home_class"]) or "").lower() != division
                 or str(rec.get(keys["away_class"]) or "").lower() != division):
            out["source_not_both_" + division] += 1
            continue
        neutral = bool(rec.get(keys["neutral"]))
        bucket = "neutral" if neutral else "nonneutral"
        out[f"source_{bucket}"] += 1
        src[bucket].append((hp, ap))
        home, away, start = rec.get(keys["home"]), rec.get(keys["away"]), parse_start(rec.get(keys["start"]))
        if not home or not away or start is None:
            out["source_unusable_row"] += 1
            continue
        m, orient = find_match(session, Sport.NFL, home, away, start), "same"
        if m is None:
            m, orient = find_match(session, Sport.NFL, away, home, start), "swapped"
        if m is None:
            out["unmatched"] += 1
            if len(unmatched) < SAMPLE:
                unmatched.append(f"{start:%Y-%m-%d} {away} @ {home}")
            continue
        code = m.competition.code if m.competition else None
        if code != "NCAA":
            out[f"matched_non_ncaa_{code}"] += 1
            continue
        out[f"joined_{orient}"] += 1
        oh, oa = (hp, ap) if orient == "same" else (ap, hp)       # the source score in OUR orientation
        if m.home_score is None or m.away_score is None:
            out["ours_no_score"] += 1
        elif (m.home_score, m.away_score) == (oh, oa):
            out["score_agree"] += 1
        else:
            out["score_disagree"] += 1
            if len(score_bad) < SAMPLE:
                score_bad.append(f"{start:%Y-%m-%d} match {m.id} ours {m.home_score}-{m.away_score} "
                                 f"source {oh}-{oa} ({orient})")
        if orient == "swapped" and len(swapped) < SAMPLE:
            swapped.append(f"{start:%Y-%m-%d} match {m.id}: source {away} @ {home}{' (neutral)' if neutral else ''}"
                           f" · ours {m.away_team.name if m.away_team else '?'} @ {m.home_team.name if m.home_team else '?'}")
        if m.home_score is not None and m.away_score is not None:
            ours_joined[bucket].append((m.home_score, m.away_score))
    rate = lambda xs: (sum(1 for h, a in xs if h > a) / len(xs)) if xs else None
    margin = lambda xs: (sum(h - a for h, a in xs) / len(xs)) if xs else None
    return {"counts": dict(out),
            "source": {b: {"n": len(v), "home_rate": rate(v), "home_margin": margin(v)} for b, v in src.items()},
            "ours_on_joined": {b: {"n": len(v), "home_rate": rate(v), "home_margin": margin(v)}
                               for b, v in ours_joined.items()},
            "swapped_sample": swapped, "score_disagree_sample": score_bad, "unmatched_sample": unmatched}


def fmt(x, pct=False):
    return "—" if x is None else (f"{x:.3f}" if pct else f"{x:+.2f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append", required=True)
    ap.add_argument("--from-file", default=None, help="a saved source response (JSON list) instead of the API")
    ap.add_argument("--key-env", default="CFBD_API_KEY")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--division", default="fbs", help="both teams' classification must equal this ('' = all)")
    ap.add_argument("--save", default=None, help="write the raw response here (outside data/) for re-runs")
    a = ap.parse_args(argv)
    if a.save and os.path.abspath(a.save).startswith(os.path.join(ROOT, "data")):
        print("REFUSED: never write under data/ (law 5)")
        return 2
    from src.db.database import session_scope

    print("NCAA SOURCE PROBE (#176) · read-only · source: CollegeFootballData (CFBD)")
    rc = 0
    for year in a.year:
        if a.from_file:
            with open(a.from_file) as f:
                recs, status, hdr = json.load(f), "file", {}
        else:
            key = os.environ.get(a.key_env, "").strip()
            if not key:
                print(f"REFUSED: no {a.key_env} in the environment (.env; never committed, never printed)")
                return 2
            try:
                status, recs, hdr = fetch(year, key, a.base, a.division or "fbs")
            except Exception as e:                      # the key is not in the message
                print(f"{year}: fetch failed: {type(e).__name__}: {str(e)[:200]}")
                rc = 1
                continue
            if a.save:
                with open(a.save.replace("{year}", str(year)), "w") as f:
                    json.dump(recs, f)
        print(f"\n== {year} · HTTP {status} · {len(recs)} records"
              + (" · rate-limit headers " + json.dumps(hdr) if hdr else ""))
        if not recs:
            continue
        keys, missing = discover(recs[0])
        print("  keys used (law-1 receipt): " + " · ".join(f"{n}<-{k}" for n, k in keys.items() if k))
        if missing:
            print(f"  REFUSED: required field(s) not found: {', '.join(missing)} · first record keys: "
                  + ", ".join(sorted(recs[0]))[:600])
            rc = 2
            continue
        with session_scope() as s:
            r = compare(recs, keys, s, (a.division or "").lower() or None)
            s.rollback()
        c = r["counts"]
        joined = c.get("joined_same", 0) + c.get("joined_swapped", 0)
        scored = c.get("source_neutral", 0) + c.get("source_nonneutral", 0)
        print("  counts: " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())))
        print(f"  join rate: {joined}/{scored} = {joined / scored * 100:.1f}%" if scored else "  join rate: —")
        if joined:
            print(f"  LABELS: same orientation {c.get('joined_same', 0)} · swapped {c.get('joined_swapped', 0)} "
                  f"({c.get('joined_swapped', 0) / joined * 100:.1f}% of joined)")
            sc = c.get("score_agree", 0) + c.get("score_disagree", 0)
            if sc:
                print(f"  SCORES (our orientation): agree {c.get('score_agree', 0)}/{sc} = "
                      f"{c.get('score_agree', 0) / sc * 100:.1f}%")
        for b in ("nonneutral", "neutral"):
            S, O = r["source"][b], r["ours_on_joined"][b]
            print(f"  {b}: SOURCE n {S['n']} home rate {fmt(S['home_rate'], True)} margin {fmt(S['home_margin'])}"
                  f" · OURS on joined n {O['n']} home rate {fmt(O['home_rate'], True)} margin {fmt(O['home_margin'])}")
        for title, xs in (("swapped (sample)", r["swapped_sample"]),
                          ("score disagree (sample)", r["score_disagree_sample"]),
                          ("unmatched (sample)", r["unmatched_sample"])):
            if xs:
                print(f"  {title}:")
                for x in xs:
                    print("    " + x)
    print("\nACCESS TERMS: free API key (Bearer) from collegefootballdata.com; check the current tier's "
          "rate limit (headers above) and licence before any ingest lane. This probe ingests nothing.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
