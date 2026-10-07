"""READ-ONLY receipt "home-abroad" (ARCHITECT 2026-10-07, item 4 INTERNATIONALS:
GO-LIVE READINESS, part c):

  "c. READ-ONLY receipt "home-abroad": per national team, listed-home games
  since 2022 with a known neutral_v3 and the share played outside the team's
  country; plus venue-id coverage per current competition-season. Writes
  docs/receipts/ via --out."

and ruling (3): "A row is never a call when its venue flag is unknown and its
listed home side is on the home-abroad list; that list is ruled by name from
the receipt in (c)." This module therefore produces NO list and hard-codes no
team: it prints the evidence the architect rules the list from.

Definitions (law 1: read from src/db/schema.py and src/ingestion/intl_venues.py):
- the national-team competitions are the intl ingest's codes
  (intl_history.CODE_BY_NAME: WCQ_*, UEFA_EURO, UEFA_EURO_Q, UNL, CNL, CNL_Q,
  FRIENDLIES_INT);
- "listed home" = matches.home_team_id; kickoff = matches.utc_date >= since;
- never-played statuses (cancelled / postponed / stale_orphan — the
  unl_ladders precedent) are left out and COUNTED; finished and upcoming
  fixtures both count (an upcoming fixture with a known venue is evidence);
- "outside the team's country" = intl_match_venue.neutral_v3 IS TRUE, which
  the ingest derives as norm(venue country) != norm(home team's country)
  (NEUTRAL_V3_RULE). Share = abroad / known (neutral_v3 not NULL);
- unknown venue (law 4) = no intl_match_venue row, or neutral_v3 NULL: never
  in the share's denominator, always counted and labelled per team.

Second table, venue-id coverage per CURRENT competition-season: a
competition-season is current when it still holds at least one SCHEDULED or
LIVE fixture (CONFIRMED, ARCHITECT 2026-10-07 addendum 3, item C: "'current
season' is one with a scheduled or live fixture"). Per comp-season: fixtures
stored (every status), with a venue id, with a known neutral_v3, and neutral_v3 home / neutral / unknown (NULL) /
no row. Writes nothing to the DB.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

DEFAULT_SINCE = datetime(2022, 1, 1)
NEVER_PLAYED = ("cancelled", "postponed", "stale_orphan")
CURRENT_STATUSES = ("scheduled", "live")


def _status(m) -> str:
    return m.status.value if hasattr(m.status, "value") else str(m.status)


def receipt(s, since: datetime = DEFAULT_SINCE) -> dict:
    from sqlalchemy import select

    from src.db.schema import Competition, IntlMatchVenue, Match, Team
    from src.ingestion.intl_history import CODE_BY_NAME

    codes = tuple(dict.fromkeys(code for _, code in CODE_BY_NAME))
    comps = {c.id: c.code for c in s.execute(select(Competition).where(Competition.code.in_(codes))).scalars()}
    if not comps:
        return {"since": since, "teams": [], "coverage": [], "totals": Counter(), "excluded_status": Counter(),
                "competitions": []}
    v3 = {r.match_id: r for r in s.execute(select(IntlMatchVenue)).scalars()}
    teams = {t.id: t for t in s.execute(select(Team)).scalars()}

    per: dict = defaultdict(lambda: {"listed_home": 0, "known": 0, "abroad": 0, "abroad_finished": 0,
                                     "abroad_upcoming": 0, "unknown_null": 0, "unknown_no_row": 0,
                                     "venue_countries": Counter(), "home_countries": Counter(),
                                     "codes": Counter()})
    excluded_status: Counter = Counter()
    cov: dict = defaultdict(Counter)
    current: set = set()
    q = select(Match).where(Match.competition_id.in_(list(comps))).order_by(Match.utc_date, Match.id)
    for m in s.execute(q).scalars():
        code, st = comps[m.competition_id], _status(m)
        v = v3.get(m.id)
        # -- coverage (every stored fixture of the comp-season, any status)
        k = (code, m.season)
        c = cov[k]
        c["fixtures"] += 1
        if st in CURRENT_STATUSES:
            current.add(k)
            c["open"] += 1
        c["with_venue_id"] += bool(v is not None and v.venue_id is not None)
        if v is None:
            c["no_row"] += 1
        elif v.neutral_v3 is None:
            c["unknown"] += 1
        else:
            c["known"] += 1
            c["neutral" if v.neutral_v3 else "home"] += 1
        # -- home-abroad (listed home, since, never-played statuses out and counted)
        if m.utc_date < since:
            continue
        if st in NEVER_PLAYED:
            excluded_status[st] += 1
            continue
        p = per[m.home_team_id]
        p["listed_home"] += 1
        p["codes"][code] += 1
        if v is None:
            p["unknown_no_row"] += 1
            continue
        if v.home_country:
            p["home_countries"][v.home_country] += 1
        if v.neutral_v3 is None:
            p["unknown_null"] += 1
            continue
        p["known"] += 1
        if v.neutral_v3:
            p["abroad"] += 1
            p["abroad_finished" if st == "finished" else "abroad_upcoming"] += 1
            p["venue_countries"][v.venue_country or "(venue country not stored)"] += 1

    rows = []
    for tid, p in per.items():
        t = teams.get(tid)
        country = (p["home_countries"].most_common(1)[0][0] if p["home_countries"]
                   else (t.area if t is not None and t.area else None))
        rows.append({"team_id": tid, "team": t.name if t is not None else f"team {tid}", "country": country,
                     "listed_home": p["listed_home"], "known": p["known"], "abroad": p["abroad"],
                     "abroad_finished": p["abroad_finished"], "abroad_upcoming": p["abroad_upcoming"],
                     "share": (p["abroad"] / p["known"]) if p["known"] else None,
                     "unknown": p["unknown_null"] + p["unknown_no_row"], "unknown_null": p["unknown_null"],
                     "unknown_no_row": p["unknown_no_row"],
                     "venue_countries": dict(p["venue_countries"].most_common()), "codes": dict(p["codes"])})
    # share desc (no known venue last), then known count desc, then name
    rows.sort(key=lambda r: (r["share"] is None, -(r["share"] or 0.0), -r["known"], r["team"]))
    totals = Counter()
    for r in rows:
        for f in ("listed_home", "known", "abroad", "unknown", "unknown_null", "unknown_no_row"):
            totals[f] += r[f]
    coverage = []
    for k in sorted(current):
        c = cov[k]
        coverage.append({"code": k[0], "season": k[1], **{f: c[f] for f in (
            "fixtures", "open", "with_venue_id", "known", "home", "neutral", "unknown", "no_row")}})
    return {"since": since, "teams": rows, "coverage": coverage, "totals": totals,
            "excluded_status": excluded_status, "competitions": sorted(set(comps.values()))}


def format_receipt(r: dict, run_at: datetime | None = None) -> str:
    """Plain text for the console and docs/receipts/ (no DB path, no keys)."""
    pct = lambda a, b: f"{a / b * 100:.1f}%" if b else "—"
    t = r["totals"]
    out = [f"INTL HOME-ABROAD receipt (ARCHITECT 2026-10-07 item 4 (c), READ-ONLY)"
           + (f" · run {run_at:%Y-%m-%dT%H:%M:%SZ}" if run_at else ""),
           f"competitions: {', '.join(r['competitions']) or 'none stored'}",
           f"listed-home games kicking off >= {r['since']:%Y-%m-%d} (finished + upcoming; never-played left out: "
           + (", ".join(f"{k} {v}" for k, v in sorted(r["excluded_status"].items())) or "none") + ")",
           "abroad = intl_match_venue.neutral_v3 TRUE (venue country != home team's country, NEUTRAL_V3_RULE); "
           "share = abroad / known; unknown venue (neutral_v3 NULL or no venue row) is EXCLUDED from the share "
           "and counted (law 4).",
           "No home-abroad list is produced here: the list is ruled by name from this receipt (ruling (3)).",
           "",
           f"TOTAL: {len(r['teams'])} teams · listed-home {t['listed_home']} · known {t['known']} · abroad "
           f"{t['abroad']} ({pct(t['abroad'], t['known'])} of known) · unknown excluded {t['unknown']} "
           f"(v3 NULL {t['unknown_null']}, no venue row {t['unknown_no_row']})",
           "",
           "PER TEAM (sorted by share, then known count):",
           f"  {'team':<28}{'country':<22}{'home':>6}{'known':>7}{'abroad':>8}{'share':>8}{'played':>8}"
           f"{'upcoming':>9}{'unknown':>9}  venue countries (abroad)"]
    for x in r["teams"]:
        vc = ", ".join(f"{k} {v}" for k, v in x["venue_countries"].items()) or "—"
        share = "—" if x["share"] is None else f"{x['share'] * 100:.1f}%"
        out.append(f"  {x['team']:<28}{(x['country'] or '—')[:21]:<22}{x['listed_home']:>6}{x['known']:>7}"
                   f"{x['abroad']:>8}{share:>8}{x['abroad_finished']:>8}{x['abroad_upcoming']:>9}"
                   f"{x['unknown']:>9}  {vc}")
    out += ["",
            "VENUE-ID COVERAGE per CURRENT competition-season (>= 1 SCHEDULED or LIVE fixture; every stored "
            "fixture of the comp-season counted):",
            f"  {'code':<15}{'season':<10}{'fixtures':>9}{'open':>6}{'venue id':>10}{'v3 known':>10}"
            f"{'home':>6}{'neutral':>9}{'unknown':>9}{'no row':>8}"]
    ct = Counter()
    for c in r["coverage"]:
        for f in ("fixtures", "open", "with_venue_id", "known", "home", "neutral", "unknown", "no_row"):
            ct[f] += c[f]
        out.append(f"  {c['code']:<15}{c['season']:<10}{c['fixtures']:>9}{c['open']:>6}{c['with_venue_id']:>10}"
                   f"{c['known']:>10}{c['home']:>6}{c['neutral']:>9}{c['unknown']:>9}{c['no_row']:>8}")
    if not r["coverage"]:
        out.append("  (no current competition-season stored)")
    else:
        out.append(f"  TOTAL: fixtures {ct['fixtures']} · venue id {ct['with_venue_id']} "
                   f"({pct(ct['with_venue_id'], ct['fixtures'])}) · v3 known {ct['known']} "
                   f"({pct(ct['known'], ct['fixtures'])}) · home {ct['home']} / neutral {ct['neutral']} / "
                   f"unknown {ct['unknown']} / no row {ct['no_row']}")
    return "\n".join(out)
