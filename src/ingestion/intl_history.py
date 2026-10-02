"""
#220 NATIONAL-TEAM HISTORY INGEST (ARCHITECT 2026-10-02, after the #228 probe
came back GREEN: 6,957 scored results 2018+, 37 competition-seasons, 54/54 UNL
teams at 60+ results): "INGEST: the ruled competition set 2018-present,
restricted to senior national teams present in UNL/WCQ/EURO/EURO_Q (filters
the wide Friendlies bucket; print what was excluded). Neutral derivation RULED
YES: fetch /teams per competition-season (37 calls), derive neutral = venue
city != home team's ground city, store as `neutral_derived` with the rule
stated — never as a provider fact. Coverage receipt per competition-season
after ingest."

Flow (one provider, API-Football; the probe's discovery, unchanged):
  1. /leagues?country=World (1 call). The ruled targets are matched BY NAME
     (law 1) and each league gets a competition code by name. A code the
     adapter already maps must carry the SAME id, or the run is REFUSED; a
     target league whose name maps to no code is REFUSED (never guessed).
  2. Per competition-season (season ending on/after --since): /fixtures and
     /teams (2 calls each). --max-calls refuses an over-budget plan.
  3. TEAM FILTER: the senior national teams = every team in a UNL, WCQ_*,
     UEFA_EURO or UEFA_EURO_Q fixture fetched. A fixture is kept only when
     BOTH teams are in that set; every exclusion is counted and the excluded
     teams are printed (the Friendlies bucket carries regional, B and
     youth sides).
  4. Teams upsert from /teams (fixture-only teams from the fixture block,
     counted); matches upsert through the normal IngestionService path
     (idempotent on external_ids; a refetch never blanks a score).
  5. neutral_derived under NEUTRAL_RULE, stored in match_neutral_derived with
     the rule text and both cities as served.

Writes only on a real run (--dry-run fetches and reports, writes nothing).
Never deletes. Never touches data/ files (--save / --from-dir refuse it).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date

# The ruling's targets — the #228 probe's own regexes (the run that measured
# 37 competition-seasons); the probe imports them from here.
TARGETS = {
    "WCQ": re.compile(r"world cup.*qualif", re.I),
    "EURO": re.compile(r"^(uefa )?euro(pean)? championship$", re.I),
    "EURO_Q": re.compile(r"euro(pean)? championship.*qualif", re.I),
    "NATIONS_LEAGUE": re.compile(r"nations league", re.I),
    "FRIENDLIES": re.compile(r"^friendlies$", re.I),
}
NOT_SENIOR = re.compile(r"women|\bu-?\d\d\b|youth|olympic|club|beach|futsal|esports|amateur", re.I)

# Discovered league NAME -> our competition code (first match wins). An
# unmatched target name is refused, never assigned.
CODE_BY_NAME = (
    (re.compile(r"world cup.*qualif.*europe", re.I), "WCQ_EU"),
    (re.compile(r"world cup.*qualif.*south america", re.I), "WCQ_SA"),
    (re.compile(r"world cup.*qualif.*africa", re.I), "WCQ_AF"),
    (re.compile(r"world cup.*qualif.*asia", re.I), "WCQ_AS"),
    (re.compile(r"world cup.*qualif.*(concacaf|north|central)", re.I), "WCQ_NA"),
    (re.compile(r"world cup.*qualif.*oceania", re.I), "WCQ_OC"),
    (re.compile(r"world cup.*qualif.*(intercontinental|play-?off)", re.I), "WCQ_IC"),
    (re.compile(r"^(uefa )?euro(pean)? championship$", re.I), "UEFA_EURO"),
    (re.compile(r"euro(pean)? championship.*qualif", re.I), "UEFA_EURO_Q"),
    (re.compile(r"^uefa nations league$", re.I), "UNL"),
    (re.compile(r"^concacaf nations league.*qualif", re.I), "CNL_Q"),   # ruled 2026-10-02 (id 808)
    (re.compile(r"^concacaf nations league$", re.I), "CNL"),            # ruled 2026-10-02 (id 536)
    (re.compile(r"^friendlies$", re.I), "FRIENDLIES_INT"),
)
# The ruling's team-filter source: "senior national teams present in
# UNL/WCQ/EURO/EURO_Q".
FILTER_SOURCE = ("UNL", "UEFA_EURO", "UEFA_EURO_Q")
FILTER_PREFIX = "WCQ_"

NEUTRAL_RULE = ("intl-neutral-v1 (ARCHITECT 2026-10-02): neutral_derived = norm(fixture venue city) != "
                "norm(home team's ground city from /teams of the SAME competition-season); norm = NFKD, "
                "combining marks dropped, casefold, whitespace collapsed; either city missing -> NULL "
                "(unknown). Derived by us from API-Football venue fields — never a provider fact.")
FINISHED = ("FT", "AET", "PEN")


class IntlError(RuntimeError):
    pass


def _end(s) -> date | None:
    try:
        return date.fromisoformat(str(s.get("end"))[:10])
    except (TypeError, ValueError):
        return None


def code_for(name: str) -> str | None:
    return next((code for rx, code in CODE_BY_NAME if rx.search(name or "")), None)


def plan(leagues: list, since: date) -> list[dict]:
    """[{code, league_id, name, year}] for every ruled target league-season
    ending on/after `since`. Refuses unmapped names, an id that disagrees
    with the adapter's mapping, and two leagues claiming one code."""
    from src.adapters.api_football import _CODE_TO_LEAGUE_ID

    out, by_code, unmapped, clash = [], {}, [], []
    for item in leagues:
        lg = item.get("league") or {}
        name, lid = lg.get("name") or "", lg.get("id")
        if lid is None or NOT_SENIOR.search(name) or not any(rx.search(name) for rx in TARGETS.values()):
            continue
        code = code_for(name)
        if code is None:
            unmapped.append(f"id {lid} '{name}'")
            continue
        if code in _CODE_TO_LEAGUE_ID and _CODE_TO_LEAGUE_ID[code] != lid:
            clash.append(f"{code}: adapter maps {_CODE_TO_LEAGUE_ID[code]}, discovered id {lid} '{name}'")
            continue
        if by_code.setdefault(code, lid) != lid:
            clash.append(f"{code}: two leagues ({by_code[code]}, {lid} '{name}')")
            continue
        for s in item.get("seasons") or []:
            if s.get("year") is not None and (_end(s) or date.min) >= since:
                out.append({"code": code, "league_id": lid, "name": name, "year": int(s["year"])})
    if unmapped or clash:
        raise IntlError("REFUSED (law 1): " + "; ".join(
            ([f"target league(s) with no code: {', '.join(unmapped)}"] if unmapped else []) + clash))
    return sorted(out, key=lambda p: (p["code"], p["year"]))


def in_filter_source(code: str) -> bool:
    return code in FILTER_SOURCE or code.startswith(FILTER_PREFIX)


def senior_set(fixtures: dict) -> set[str]:
    """Provider team ids seen in any UNL / WCQ_* / UEFA_EURO / UEFA_EURO_Q fixture."""
    out = set()
    for (code, _year), rows in fixtures.items():
        if in_filter_source(code):
            for it in rows:
                for side in ("home", "away"):
                    tid = ((it.get("teams") or {}).get(side) or {}).get("id")
                    if tid is not None:
                        out.add(str(tid))
    return out


def stored_senior(source: str = "api_football") -> set[str]:
    """Provider ids of teams in STORED UNL / WCQ_* / UEFA_EURO / UEFA_EURO_Q
    matches. The incremental daily sync (--since {today}, ARCHITECT 2026-10-02)
    fetches current seasons only; without this, a friendly against a senior
    side with no competitive fixture THIS season would be dropped."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team

    out = set()
    with session_scope() as s:
        comps = [c.id for c in s.execute(select(Competition)).scalars() if in_filter_source(c.code)]
        if not comps:
            return out
        ids = set()
        for h, a in s.execute(select(Match.home_team_id, Match.away_team_id).where(Match.competition_id.in_(comps))):
            ids.update((h, a))
        for t in s.execute(select(Team).where(Team.id.in_(ids))).scalars():
            sid = (t.external_ids or {}).get(source)
            if sid:
                out.add(str(sid))
        s.rollback()
    return out


def norm_city(s) -> str | None:
    if not s or not str(s).strip():
        return None
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(t.casefold().split())


def grounds(teams_payload: list) -> dict[str, str | None]:
    """provider team id -> ground city as served by /teams (same comp-season)."""
    return {str((it.get("team") or {}).get("id")): (it.get("venue") or {}).get("city")
            for it in teams_payload if (it.get("team") or {}).get("id") is not None}


def derive_neutral(fixture_item: dict, ground_city: dict) -> tuple[bool | None, str | None, str | None]:
    """(neutral_derived, venue_city, home_ground_city) under NEUTRAL_RULE."""
    venue = ((fixture_item.get("fixture") or {}).get("venue") or {}).get("city")
    home = str(((fixture_item.get("teams") or {}).get("home") or {}).get("id"))
    g = ground_city.get(home)
    a, b = norm_city(venue), norm_city(g)
    return (None if a is None or b is None else a != b), venue, g


class Source:
    """API-Football through the adapter's client (throttle, 429 backoff), or a
    saved directory. Every live call is counted; nothing is written under data/."""

    def __init__(self, from_dir: str | None = None, save: str | None = None, root: str | None = None):
        root = root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for d in (from_dir, save):
            if d and os.path.abspath(d).startswith(os.path.join(root, "data")):
                raise IntlError("REFUSED: never write or read ingest files under data/ (law 5)")
        self.from_dir, self.save, self.calls = from_dir, save, 0
        from src.adapters.api_football import APIFootballAdapter
        # the replay never reaches the network: the key is only a placeholder
        try:
            self.cl = APIFootballAdapter(api_key="replay-no-network") if from_dir else APIFootballAdapter()
        except ValueError as e:                     # no key in .env: the message names the variable only
            raise IntlError(f"REFUSED: {e}") from None
        if save:
            os.makedirs(save, exist_ok=True)

    def get(self, name: str, path: str, params: dict | None = None) -> dict:
        if self.from_dir:
            with open(os.path.join(self.from_dir, name)) as f:
                return json.load(f)
        payload = self.cl._get(path, params)
        if path != "status":
            self.calls += 1
        if self.save:
            with open(os.path.join(self.save, name), "w") as f:
                json.dump(payload, f)
        return payload


def _cached_service(adapter):
    """IngestionService whose team lookup is a per-run map (the service's own
    lookup re-scans every team per call: ~14k fixture sides x every team —
    the O(n^2) shape the 2026-09-23 prefetch fix removed for matches)."""
    from sqlalchemy import select

    from src.db.schema import Team
    from src.ingestion.service import IngestionService

    class _Svc(IngestionService):
        _teams: dict | None = None

        def _find_team_by_source(self, s, sport, source, source_id):
            if self._teams is None:
                self._teams = {}
                for t in s.execute(select(Team).where(Team.sport == sport)).scalars():
                    sid = (t.external_ids or {}).get(source)
                    if sid:
                        self._teams.setdefault(sid, t)
            return self._teams.get(source_id)

        def _upsert_team(self, s, nt, result):
            team = super()._upsert_team(s, nt, result)
            self._teams[nt.source_id] = team
            return team

    return _Svc(adapter)


def ingest(src: Source, since: date, max_calls: int = 80, dry_run: bool = False) -> dict:
    """Run the lane. Returns the receipt (fetch side + exclusions + writes)."""
    from sqlalchemy import select

    from src.adapters.normalized import NormalizedTeam
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchNeutralDerived, Sport
    from src.ingestion.service import SyncResult

    leagues = src.get("leagues.json", "leagues", {"country": "World"}).get("response") or []
    work = plan(leagues, since)
    if not work:
        raise IntlError("REFUSED: discovery found no ruled competition-season")
    need = 2 * len(work)
    if not src.from_dir and need > max_calls:
        raise IntlError(f"REFUSED: {need} calls (fixtures + teams per competition-season) > --max-calls {max_calls}")
    fixtures, teams = {}, {}
    for p in work:
        key = (p["code"], p["year"])
        q = {"league": p["league_id"], "season": p["year"]}
        fixtures[key] = src.get(f"fixtures_{p['league_id']}_{p['year']}.json", "fixtures", q).get("response") or []
        teams[key] = src.get(f"teams_{p['league_id']}_{p['year']}.json", "teams", q).get("response") or []

    senior = senior_set(fixtures) | stored_senior(src.cl.source_name)
    if not senior:
        raise IntlError("REFUSED: no team in any UNL/WCQ/EURO/EURO_Q fixture — the filter would drop everything")
    excluded_by_cs, excluded_teams = Counter(), Counter()
    kept: dict = defaultdict(list)
    for key, rows in fixtures.items():
        for it in rows:
            ids = [str(((it.get("teams") or {}).get(side) or {}).get("id")) for side in ("home", "away")]
            if all(i in senior for i in ids):
                kept[key].append(it)
                continue
            excluded_by_cs[key] += 1
            for side, i in zip(("home", "away"), ids):
                if i not in senior:
                    excluded_teams[f"{((it.get('teams') or {}).get(side) or {}).get('name')} (id {i})"] += 1

    adapter = src.cl
    svc = _cached_service(adapter)
    tres, mres = SyncResult(), SyncResult()
    neutral = Counter()
    per_cs: dict = {}
    fixture_only_teams = 0
    with session_scope() as s:
        comps = {}
        for p in work:
            if p["code"] in comps:
                continue
            c = s.execute(select(Competition).where(Competition.code == p["code"])).scalar_one_or_none()
            if c is None:     # a code new to the DB; existing rows are never modified
                c = Competition(sport=Sport.SOCCER, code=p["code"], name=p["name"], area="International",
                                type="INTL", external_ids={adapter.source_name: str(p["league_id"])})
                s.add(c)
                s.flush()
            comps[p["code"]] = c
        for p in work:
            key = (p["code"], p["year"])
            comp, season_str = comps[p["code"]], None
            served = set()
            for it in teams[key]:
                t, v = it.get("team") or {}, it.get("venue") or {}
                if t.get("id") is None or str(t["id"]) not in senior:
                    continue
                served.add(str(t["id"]))
                nt = NormalizedTeam(sport=Sport.SOCCER, name=t["name"], short_name=t.get("code"), tla=t.get("code"),
                                    area=t.get("country"), founded=t.get("founded"), venue=v.get("name"),
                                    source=adapter.source_name, source_id=str(t["id"]))
                team = svc._upsert_team(s, nt, tres)
                season_str = season_str or _season(adapter, kept[key] or fixtures[key], p["code"])
                if season_str:
                    svc._link_team_to_competition(s, team, comp, season_str)
            for it in kept[key]:                     # teams the /teams listing did not serve
                for side in ("home", "away"):
                    t = (it.get("teams") or {}).get(side) or {}
                    if str(t.get("id")) not in served and svc._find_team_by_source(
                            s, Sport.SOCCER, adapter.source_name, str(t.get("id"))) is None:
                        svc._upsert_team(s, NormalizedTeam(sport=Sport.SOCCER, name=t.get("name") or f"team {t['id']}",
                                                           source=adapter.source_name, source_id=str(t["id"])), tres)
                        fixture_only_teams += 1
            cache = {}
            for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars():
                sid = (m.external_ids or {}).get(adapter.source_name)
                if sid:
                    cache[sid] = m
            g = grounds(teams[key])
            n = Counter()
            for it in kept[key]:
                nm = adapter._parse_fixture(it, p["code"])
                m = svc._upsert_match(s, nm, comp, mres, cache=cache)
                if m is None:
                    n["skipped"] += 1
                    continue
                s.flush()
                flag, vcity, gcity = derive_neutral(it, g)
                row = s.get(MatchNeutralDerived, m.id)
                if row is None:
                    row = MatchNeutralDerived(match_id=m.id, rule=NEUTRAL_RULE)
                    s.add(row)
                row.neutral_derived, row.rule = flag, NEUTRAL_RULE
                row.venue_city, row.home_ground_city = vcity, gcity
                n["stored"] += 1
                label = "unknown" if flag is None else ("neutral" if flag else "home")
                n[label] += 1
                neutral[label] += 1
            per_cs[key] = {"league_id": p["league_id"], "name": p["name"], "listed": len(fixtures[key]),
                           "excluded": excluded_by_cs[key], "kept": len(kept[key]), **n}
        if dry_run:
            s.rollback()
    return {"plan": work, "calls": src.calls, "senior_teams": len(senior), "per_cs": per_cs,
            "excluded_teams": excluded_teams, "excluded_total": sum(excluded_by_cs.values()),
            "teams": str(tres), "matches": str(mres), "fixture_only_teams": fixture_only_teams,
            "neutral": dict(neutral), "dry_run": dry_run}


def _season(adapter, rows: list, code: str) -> str | None:
    for it in rows:
        try:
            return adapter._parse_fixture(it, code).season or None
        except Exception:
            continue
    return None


def coverage(s, codes: tuple[str, ...] | None = None) -> list[dict]:
    """Per competition-season, from the DB (read-only): stored matches,
    finished+scored, 90-minute share, venue share, and neutral_derived
    home / neutral / unknown / no row."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchNeutralDerived, MatchStatus

    want = codes or tuple(rx_code for _, rx_code in CODE_BY_NAME)
    comps = {c.id: c.code for c in s.execute(select(Competition).where(Competition.code.in_(want))).scalars()}
    if not comps:
        return []
    nd = {r.match_id: r.neutral_derived for r in s.execute(select(MatchNeutralDerived)).scalars()}
    agg: dict = defaultdict(Counter)
    span: dict = {}
    teams: dict = defaultdict(set)
    for m in s.execute(select(Match).where(Match.competition_id.in_(list(comps))).order_by(Match.utc_date)).scalars():
        k = (comps[m.competition_id], m.season)
        c = agg[k]
        c["matches"] += 1
        teams[k].update((m.home_team_id, m.away_team_id))
        if m.status != MatchStatus.FINISHED or m.home_score is None or m.away_score is None:
            continue
        c["scored"] += 1
        c["score_90"] += m.home_score_90 is not None and m.away_score_90 is not None
        c["venue"] += bool(m.venue)
        c["nd_" + ("none" if m.id not in nd else "unknown" if nd[m.id] is None
                   else "neutral" if nd[m.id] else "home")] += 1
        lo, hi = span.get(k, (m.utc_date, m.utc_date))
        span[k] = (min(lo, m.utc_date), max(hi, m.utc_date))
    out = []
    for k in sorted(agg):
        c = agg[k]
        lo, hi = span.get(k, (None, None))
        out.append({"code": k[0], "season": k[1], "matches": c["matches"], "scored": c["scored"],
                    "teams": len(teams[k]), "score_90": c["score_90"], "venue": c["venue"],
                    "home": c["nd_home"], "neutral": c["nd_neutral"], "unknown": c["nd_unknown"],
                    "no_row": c["nd_none"],
                    "from": lo.date().isoformat() if lo else None, "to": hi.date().isoformat() if hi else None})
    return out


def coverage_lines(rows: list[dict]) -> list[str]:
    pct = lambda a, b: f"{a / b * 100:.0f}%" if b else "—"
    out = [f"  {'code':<15}{'season':<9}{'stored':>7}{'scored':>7}{'teams':>6}{'90min':>7}{'venue':>7}"
           f"{'home':>6}{'neutral':>8}{'unknown':>8}{'no row':>7}  span"]
    tot = Counter()
    for r in rows:
        for k in ("matches", "scored", "home", "neutral", "unknown", "no_row"):
            tot[k] += r[k]
        out.append(f"  {r['code']:<15}{r['season']:<9}{r['matches']:>7}{r['scored']:>7}{r['teams']:>6}"
                   f"{pct(r['score_90'], r['scored']):>7}{pct(r['venue'], r['scored']):>7}{r['home']:>6}"
                   f"{r['neutral']:>8}{r['unknown']:>8}{r['no_row']:>7}  {r['from']}..{r['to']}")
    out.append(f"  TOTAL: {tot['matches']} stored · {tot['scored']} scored · neutral_derived home {tot['home']} "
               f"/ neutral {tot['neutral']} / unknown {tot['unknown']} / no row {tot['no_row']}")
    # the rule's sanity check: home-and-away competitions should derive ~0% neutral
    ha = [r for r in rows if r["code"] == "UNL" or r["code"].startswith("WCQ_") or r["code"] == "UEFA_EURO_Q"]
    h, nn = sum(r["home"] for r in ha), sum(r["neutral"] for r in ha)
    out.append(f"  RULE CHECK (home-and-away competitions UNL / WCQ_* / UEFA_EURO_Q): derived neutral "
               f"{nn}/{h + nn} = {pct(nn, h + nn)} — expected near 0 (relocations, finals tournaments, "
               f"play-off venues). A high share means the city rule reads multi-city home grounds as neutral.")
    return out
