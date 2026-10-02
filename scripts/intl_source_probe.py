"""
#228 NATIONAL-TEAM SOURCE PROBE (lane #220) — read-only (ARCHITECT 2026-10-02: "UNL model
lane SUSPENDED-PENDING-DATA; no pre-commitment yet. Probe lane (read-only):
can the football provider supply national-team history 2018-present (WCQ all
confederations, Euro + qualifiers, Nations League 2018-19 onward, friendlies)
with scores and venue/neutral flags? Coverage receipt per competition-season;
cost estimate in calls. A national-team Elo needs ~6 years of results before
its first gate run.")

Why: intl-inventory found 157 scored national-team results (UNL 60, WC 97);
38/54 UNL teams have 0 prior results; WCQ/EURO/friendlies are registered but
empty. This probe measures what API-Football (the provider we already hold a
key for) can serve, BEFORE any ingest lane is proposed.

LAW 1: league ids are DISCOVERED from /leagues?country=World by name (the
names and ids found are printed) and cross-checked against the ids the adapter
already maps; a ruling target with no discovered league is reported MISSING,
never guessed. LAW 4: the provider's fixture carries a venue (id/name/city) and
no neutral flag (the probe scans every raw key for /neutral/ and counts it);
a neutral site is NEVER inferred here. A venue-vs-home-ground derivation
would be a separate, ruled lane; its call cost is estimated, not spent.

Calls: /status (free, the access receipt) + /leagues?country=World (1) + one
/fixtures?league=&season= per in-scope competition-season. --plan stops after
discovery and prints the cost; --max-calls refuses a run larger than the
budget. Writes NOTHING (no DB writes, no ingest path; raw JSON only with
--save DIR, never under data/). --from-dir replays a saved run offline.

    python3 scripts/intl_source_probe.py --plan
    python3 scripts/intl_source_probe.py --save /tmp/intl_probe
    python3 scripts/intl_source_probe.py --from-dir /tmp/intl_probe
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# The ruling's targets: name regex over /leagues?country=World (first-class
# discovery, law 1). One target may match several leagues (WCQ: one per
# confederation plus the intercontinental play-offs).
TARGETS = {
    "WCQ": re.compile(r"world cup.*qualif", re.I),
    "EURO": re.compile(r"^(uefa )?euro(pean)? championship$", re.I),
    "EURO_Q": re.compile(r"euro(pean)? championship.*qualif", re.I),
    "NATIONS_LEAGUE": re.compile(r"nations league", re.I),
    "FRIENDLIES": re.compile(r"^friendlies$", re.I),
}
# Never national senior men's football: shown nowhere, fetched never.
NOT_SENIOR = re.compile(r"women|\bu-?\d\d\b|youth|olympic|club|beach|futsal|esports|amateur", re.I)
FINISHED = ("FT", "AET", "PEN")
NEUTRAL_KEY = re.compile(r"neutral", re.I)


def _y(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def discover(leagues: list, since: date) -> dict:
    """Ruling targets -> [(league_id, name, [season dicts ending on/after `since`])];
    plus the other senior national-team leagues the provider offers (not fetched)."""
    found: dict = {t: [] for t in TARGETS}
    others, names = [], {}
    for item in leagues:
        lg = item.get("league") or {}
        name, lid = lg.get("name") or "", lg.get("id")
        if lid is None or NOT_SENIOR.search(name):
            continue
        names[lid] = name
        seasons = [s for s in item.get("seasons") or [] if (_y(s.get("end")) or date.min) >= since]
        hit = next((t for t, rx in TARGETS.items() if rx.search(name)), None)
        if hit:
            found[hit].append((lid, name, seasons))
        elif seasons:
            others.append((lid, name, len(seasons)))
    return {"targets": found, "others": sorted(others, key=lambda x: x[1]), "names": names}


def crosscheck(disc: dict) -> list[str]:
    """The adapter's mapped national-team ids vs the discovered names (law 1 receipt)."""
    from src.adapters.api_football import _CODE_TO_LEAGUE_ID
    from src.walters.intl_inventory import INTL_CODES

    names, out = disc["names"], []
    for code in INTL_CODES:
        lid = _CODE_TO_LEAGUE_ID.get(code)
        if lid is None:
            out.append(f"{code}: not mapped in the adapter")
        else:
            out.append(f"{code} -> {lid}: " + (f"discovered as '{names[lid]}'" if lid in names
                                                else "NOT FOUND among the provider's senior World leagues"))
    return out


def _keys(o, prefix="") -> set:
    if isinstance(o, dict):
        return {k2 for k, v in o.items() for k2 in {prefix + k} | _keys(v, prefix + k + ".")}
    return set()


def season_receipt(fixtures: list) -> dict:
    """One competition-season's coverage, from the raw /fixtures response."""
    c = Counter()
    status, teams, dates = Counter(), set(), []
    neutral_keys = set()
    for it in fixtures:
        fx, tm, gl = it.get("fixture") or {}, it.get("teams") or {}, it.get("goals") or {}
        ft = (it.get("score") or {}).get("fulltime") or {}
        st = (fx.get("status") or {}).get("short") or "?"
        status[st] += 1
        c["fixtures"] += 1
        neutral_keys |= {k for k in _keys(it) if NEUTRAL_KEY.search(k)}
        for side in ("home", "away"):
            if (tm.get(side) or {}).get("id") is not None:
                teams.add(tm[side]["id"])
        if st not in FINISHED:
            continue
        c["finished"] += 1
        if gl.get("home") is None or gl.get("away") is None:
            continue
        c["scored"] += 1
        c["score_90"] += ft.get("home") is not None and ft.get("away") is not None
        v = fx.get("venue") or {}
        c["venue_id"] += v.get("id") is not None
        c["venue_name"] += bool(v.get("name"))
        c["venue_city"] += bool(v.get("city"))
        d = _y(fx.get("date"))
        if d:
            dates.append(d)
    n = c["scored"]
    share = lambda k: c[k] / n if n else None
    return {"fixtures": c["fixtures"], "finished": c["finished"], "scored": n,
            "score_90": share("score_90"), "venue_id": share("venue_id"), "venue_name": share("venue_name"),
            "venue_city": share("venue_city"), "neutral_keys": sorted(neutral_keys),
            "from": min(dates).isoformat() if dates else None, "to": max(dates).isoformat() if dates else None,
            "teams": len(teams), "status": dict(status)}


def team_results(fixtures_by_key: dict) -> Counter:
    """Scored results per provider team id, across everything fetched."""
    n = Counter()
    for fixtures in fixtures_by_key.values():
        for it in fixtures:
            st = ((it.get("fixture") or {}).get("status") or {}).get("short")
            gl, tm = it.get("goals") or {}, it.get("teams") or {}
            if st in FINISHED and gl.get("home") is not None and gl.get("away") is not None:
                for side in ("home", "away"):
                    tid = (tm.get(side) or {}).get("id")
                    if tid is not None:
                        n[str(tid)] += 1
    return n


def unl_coverage(s, per_team: Counter) -> dict:
    """Our UNL teams (by their stored api_football id) against the fetched pool:
    how many scored results each would have. Read-only."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match

    comp = s.execute(select(Competition).where(Competition.code == "UNL")).scalars().first()
    if comp is None:
        return {"unl_teams": 0}
    ids = set()
    for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars():
        ids.update((m.home_team, m.away_team))
    src = {t.id: (t.external_ids or {}).get("api_football") for t in ids if t is not None}
    hist = Counter()
    for tid, sid in src.items():
        k = per_team.get(str(sid), 0) if sid else None
        hist["no api_football id" if k is None else "0" if k == 0 else "1-9" if k < 10
             else "10-29" if k < 30 else "30-59" if k < 60 else "60+"] += 1
    return {"unl_teams": len(src), "results_per_team": dict(hist)}


def plan(disc: dict) -> list[tuple[str, int, str, int]]:
    return [(t, lid, name, s.get("year")) for t, rows in disc["targets"].items()
            for lid, name, seasons in rows for s in seasons if s.get("year") is not None]


def pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2018-01-01", help="keep seasons ending on/after this date")
    ap.add_argument("--plan", action="store_true", help="discovery only: print the call cost, fetch no fixtures")
    ap.add_argument("--max-calls", type=int, default=80, help="refuse a fixture plan larger than this")
    ap.add_argument("--save", default=None, help="directory for the raw responses (never under data/)")
    ap.add_argument("--from-dir", default=None, help="replay a --save directory instead of the API")
    ap.add_argument("--no-db", action="store_true", help="skip the read-only UNL-team join")
    a = ap.parse_args(argv)
    for d in (a.save, a.from_dir):
        if d and os.path.abspath(d).startswith(os.path.join(ROOT, "data")):
            print("REFUSED: never write or read probe files under data/ (law 5)")
            return 2
    since = date.fromisoformat(a.since)
    print(f"NATIONAL-TEAM SOURCE PROBE (#228, lane #220) · read-only · provider: API-Football · seasons ending >= {since}")

    cl = None
    if a.from_dir:
        load = lambda name: json.load(open(os.path.join(a.from_dir, name)))
        status = load("status.json") if os.path.exists(os.path.join(a.from_dir, "status.json")) else {}
    else:
        from src.adapters.api_football import APIFootballAdapter
        try:
            cl = APIFootballAdapter()
        except ValueError as e:
            print(f"REFUSED: {e}")
            return 2
        if a.save:
            os.makedirs(a.save, exist_ok=True)

        def load(name, path=None, params=None):
            payload = cl._get(path, params)
            if a.save:
                with open(os.path.join(a.save, name), "w") as f:
                    json.dump(payload, f)
            return payload
        status = load("status.json", "status")
    resp = (status.get("response") or {}) if isinstance(status, dict) else {}
    if resp:
        sub, req = resp.get("subscription") or {}, resp.get("requests") or {}
        print(f"ACCESS: plan {sub.get('plan')!r} active {sub.get('active')} · requests today "
              f"{req.get('current')}/{req.get('limit_day')} (/status is not counted)")

    leagues = load("leagues.json") if a.from_dir else load("leagues.json", "leagues", {"country": "World"})
    disc = discover(leagues.get("response") or [], since)
    print("\nDISCOVERY (/leagues?country=World, 1 call) — law-1 receipt:")
    for t, rows in disc["targets"].items():
        if not rows:
            print(f"  {t}: MISSING — no league name matched {TARGETS[t].pattern!r}")
        for lid, name, seasons in rows:
            print(f"  {t}: id {lid} '{name}' · seasons " + ", ".join(str(s.get("year")) for s in seasons))
    print("ADAPTER CROSS-CHECK:")
    for line in crosscheck(disc):
        print("  " + line)
    work = plan(disc)
    print(f"\nCOST: {len(work)} fixture calls (one per competition-season) + 1 discovery + /status (free)")
    if disc["others"]:
        print(f"  not in the ruling (not fetched; {sum(n for *_, n in disc['others'])} more calls if ruled in):")
        for lid, name, n in disc["others"]:
            print(f"    id {lid} '{name}' · {n} season(s)")
    print("  neutral derivation (NOT run; would be an inference, ruling needed): one /teams?league=&season= per "
          f"competition-season for the home ground = {len(work)} more calls")
    if a.plan:
        return 0
    if not a.from_dir and len(work) > a.max_calls:
        print(f"REFUSED: {len(work)} calls > --max-calls {a.max_calls}")
        return 2

    by_key, rows, rc = {}, [], 0
    for t, lid, name, year in work:
        fn = f"fixtures_{lid}_{year}.json"
        try:
            payload = load(fn) if a.from_dir else load(fn, "fixtures", {"league": lid, "season": year})
        except Exception as e:                       # the key is never in the message
            print(f"  {name} {year}: fetch failed: {type(e).__name__}: {str(e)[:200]}")
            rc = 1
            continue
        by_key[(lid, year)] = payload.get("response") or []
        rows.append((t, lid, name, year, season_receipt(by_key[(lid, year)])))

    print("\nCOVERAGE per competition-season (scored = finished FT/AET/PEN with both goals; shares over scored):")
    print(f"  {'target':<15}{'league':<44}{'season':>6}{'fix':>6}{'fin':>6}{'scored':>7}{'90min':>7}"
          f"{'v.id':>6}{'v.name':>7}{'v.city':>7}{'teams':>6}  span · neutral keys")
    tot = Counter()
    for t, lid, name, year, r in rows:
        tot["scored"] += r["scored"]
        tot["fixtures"] += r["fixtures"]
        print(f"  {t:<15}{(str(lid) + ' ' + name)[:43]:<44}{year:>6}{r['fixtures']:>6}{r['finished']:>6}"
              f"{r['scored']:>7}{pct(r['score_90']):>7}{pct(r['venue_id']):>6}{pct(r['venue_name']):>7}"
              f"{pct(r['venue_city']):>7}{r['teams']:>6}  {r['from']}..{r['to']} · "
              + (", ".join(r["neutral_keys"]) or "none"))
        other = {k: v for k, v in r["status"].items() if k not in FINISHED}
        if other:
            print(f"  {'':<15}  not finished: " + ", ".join(f"{k} {v}" for k, v in sorted(other.items())))
    print(f"  TOTAL: {tot['fixtures']} fixtures · {tot['scored']} scored results · {len(rows)} competition-seasons")
    nk = sorted({k for *_, r in rows for k in r["neutral_keys"]})
    print("NEUTRAL FLAG: " + (f"keys present: {', '.join(nk)}" if nk else
                              "NONE in any fixture (law 4: venue is reported as served; no neutral inferred)"))
    per_team = team_results(by_key)
    span = Counter(per_team.values())
    print(f"TEAMS: {len(per_team)} provider teams with >=1 scored result · "
          f">=30 results: {sum(1 for v in per_team.values() if v >= 30)} · "
          f">=60: {sum(1 for v in per_team.values() if v >= 60)} · max {max(span) if span else 0}")
    if not a.no_db:
        from src.db.database import session_scope
        with session_scope() as s:
            u = unl_coverage(s, per_team)
            s.rollback()
        print(f"OUR UNL TEAMS ({u['unl_teams']}) — scored results each would have from the fetched pool: "
              + " · ".join(f"{k} {v}" for k, v in sorted(u.get("results_per_team", {}).items())))
    if cl is not None:
        print(f"\nprovider calls this run: {2 + len(work)} (/status counted as free)")
    print("This probe ingests nothing. An ingest lane is a separate PR, after a ruling on this receipt.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
