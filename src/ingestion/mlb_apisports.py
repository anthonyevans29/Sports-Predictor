"""
MLB PHASE A (architect, 2026-09-29): the api-sports Baseball FALLBACK for MLB
sync-matches / results, engaged where SP_SKIP_FAMILIES names MLB (the DO host:
statsapi.mlb.com returns 406 to datacenter ASNs). The laptop keeps statsapi.

Gate met before this was built: score parity 100.0% on finished pairs
(2476/2476 and 2426/2426, the operator's laptop run of
scripts/mlb_apisports_probe.py).

Rules (ruled 2026-09-29):
  - The host SYNCS MLB only (the mlb-history chain). It holds no MLB
    predictions, and nothing here predicts or evaluates.
  - STAGE comes from OUR gameType mapping only (statsapi R/F/D/L/W). The
    provider's `week` labels the Wild Card round and the World Series both
    "Final", so it is never read into `stage`. A row this fallback creates
    has stage NULL (the host has no statsapi row to take it from); a row that
    pairs to a statsapi row keeps that row's stage.
  - KNOWN LIMITATION: doubleheader game 2 is absent from api-sports /games
    (13 games across 2025-2026, all confirmed same-date / same-teams). The
    fallback never fabricates them. Where one of OUR rows exists for such a
    game, it is marked external_ids["api_baseball_note"] =
    "apisports-unavailable" and otherwise left alone: the laptop's statsapi
    remains the record. Every run's receipt restates the limitation.
  - Conservative unknowns (law 4): only FT (with both run totals), POST and
    CANC are mapped. Every other provider status stays SCHEDULED, is stored
    verbatim in status_raw, and is counted in the receipt as unmapped. A
    FINISHED row is never downgraded by this path.

The pairing rules (pair / suspects) are the probe's, moved here so the probe
and the fallback share one definition.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timezone

TOL_H = 12
SUSPECT_H = 48
CANDIDATE_TYPE_FIELDS = ("week", "stage", "type", "round", "game_type")
SOURCE = "api_baseball"                  # the key odds/weather already use for provider game ids
NOTE_KEY = "api_baseball_note"
UNAVAILABLE = "apisports-unavailable"
KNOWN_LIMITATION = ("doubleheader game 2 is absent from api-sports /games (13 games across "
                    "2025-2026, architect 2026-09-29); never fabricated; the laptop's statsapi "
                    "remains the record for them")
# Provider status (short) -> ours. Anything else stays SCHEDULED (law 4).
STATUS_MAP = {"FT": "FINISHED", "POST": "POSTPONED", "CANC": "CANCELLED"}
# Not club competition: never ingested. Team names first (the all-star sides,
# the #43 lesson), then an exhibition label on the game.
NON_CLUB_TEAM = re.compile(r"all[- ]?star|^american league$|^national league$", re.I)
EXHIBITION = re.compile(r"spring|pre-?season|exhibition|all[- ]?star", re.I)


def fallback_engaged(competition_code: str, env=None) -> bool:
    """True where the host skips MLB's statsapi path: competition MLB and
    SP_SKIP_FAMILIES (host.env) names MLB. MLB_SPRING never falls back."""
    env = os.environ if env is None else env
    skip = {s.strip().upper() for s in (env.get("SP_SKIP_FAMILIES") or "").split(",") if s.strip()}
    return (competition_code or "").upper() == "MLB" and "MLB" in skip


# ----------------------------------------------------------------- pairing --

def norm(name: str) -> str:
    from src.ingestion.match_lookup import normalize_team_name
    return normalize_team_name(name or "")


def names_match(a: str, b: str) -> bool:
    return a == b or bool(a and b and (a in b or b in a))


def provider_rows(games: list[dict]) -> list[dict]:
    """Flatten /games items into {id, utc, home, away, home_id, away_id,
    status_short, status_long, home_runs, away_runs, extra}. `extra` keeps
    every candidate type field present (the probe's postseason cross-tab)."""
    out = []
    for g in games or []:
        teams = g.get("teams") or {}
        st = g.get("status") or {}
        sc = g.get("scores") or {}
        try:
            dt = datetime.fromisoformat(str(g.get("date")).replace("Z", "+00:00"))
            utc = (dt.astimezone(timezone.utc) if dt.tzinfo else dt).replace(tzinfo=None)
        except ValueError:
            utc = None
        out.append({"id": g.get("id"), "utc": utc,
                    "home": (teams.get("home") or {}).get("name"),
                    "away": (teams.get("away") or {}).get("name"),
                    "home_id": (teams.get("home") or {}).get("id"),
                    "away_id": (teams.get("away") or {}).get("id"),
                    "status_short": st.get("short"), "status_long": st.get("long"),
                    "home_runs": (sc.get("home") or {}).get("total"),
                    "away_runs": (sc.get("away") or {}).get("total"),
                    "extra": {k: g.get(k) for k in CANDIDATE_TYPE_FIELDS if k in g}})
    return out


def pair(ours: list[dict], prov: list[dict]) -> dict:
    """Pair our matches with provider games: same normalized home/away names and
    kickoff within +/-TOL_H hours; among several candidates (doubleheaders) the
    nearest start wins, and a tie is AMBIGUOUS (counted, left unpaired).
    ours rows: {id, utc, home, away, ...}."""
    by_pair: dict[tuple, list[dict]] = {}
    for p in prov:
        if p["utc"] is None:
            continue
        by_pair.setdefault((norm(p["home"]), norm(p["away"])), []).append(p)
    used, pairs, unmatched, ambiguous = set(), [], [], []
    for o in sorted(ours, key=lambda r: r["utc"]):
        h, a = norm(o["home"]), norm(o["away"])
        cands = [p for (ph, pa), ps in by_pair.items() if names_match(h, ph) and names_match(a, pa)
                 for p in ps if p["id"] not in used and abs((p["utc"] - o["utc"]).total_seconds()) <= TOL_H * 3600]
        if not cands:
            unmatched.append(o)
            continue
        cands.sort(key=lambda p: abs((p["utc"] - o["utc"]).total_seconds()))
        if len(cands) > 1 and abs((cands[0]["utc"] - o["utc"]).total_seconds()) == \
                abs((cands[1]["utc"] - o["utc"]).total_seconds()):
            ambiguous.append(o)
            continue
        used.add(cands[0]["id"])
        pairs.append((o, cands[0]))
    return {"pairs": pairs, "ours_unmatched": unmatched, "ambiguous": ambiguous,
            "provider_unmatched": [p for p in prov if p["id"] not in used],
            "paired_to": {p["id"]: o["id"] for o, p in pairs}}


def suspects(unpaired: list[dict], prov: list[dict], paired_to: dict) -> list[dict]:
    """Why an unpaired game of ours found no partner: a same-teams provider
    game within +/-SUSPECT_H hours that was either already paired to another of
    our games (DOUBLEHEADER suspect) or sits outside the +/-12h window
    (UTC-BOUNDARY / date suspect); else none. `doubleheader` is True only for
    the first kind (the known api-sports limitation)."""
    out = []
    for o in unpaired:
        h, a = norm(o["home"]), norm(o["away"])
        near = sorted((p for p in prov if p["utc"] is not None and names_match(h, norm(p["home"]))
                       and names_match(a, norm(p["away"]))
                       and abs((p["utc"] - o["utc"]).total_seconds()) <= SUSPECT_H * 3600),
                      key=lambda p: abs((p["utc"] - o["utc"]).total_seconds()))
        why, dh = "no same-teams provider game within ±48h", False
        for p in near:
            d = (p["utc"] - o["utc"]).total_seconds() / 3600
            if p["id"] in paired_to:
                why, dh = (f"DOUBLEHEADER suspect: provider #{p['id']} at {p['utc'].isoformat()} ({d:+.1f}h) "
                           f"already paired to our match #{paired_to[p['id']]}"), True
                break
            if abs(d) > TOL_H:
                why = f"UTC-BOUNDARY/date suspect: provider #{p['id']} at {p['utc'].isoformat()} ({d:+.1f}h)"
                break
        out.append({"match_id": o["id"], "game": f"{o['away']} @ {o['home']}", "utc": o["utc"].isoformat(),
                    "stage": o.get("stage"), "score": f"{o.get('away_score')}-{o.get('home_score')}",
                    "why": why, "doubleheader": dh})
    return out


# ---------------------------------------------------------------- mapping --

def map_status(p: dict) -> str:
    """Our MatchStatus NAME for a provider row (conservative: see module doc)."""
    ours = STATUS_MAP.get((p.get("status_short") or "").upper(), "SCHEDULED")
    if ours == "FINISHED" and not (isinstance(p.get("home_runs"), int) and isinstance(p.get("away_runs"), int)):
        return "SCHEDULED"           # FT without both totals: never a fabricated final
    return ours


def is_exhibition(p: dict) -> bool:
    if NON_CLUB_TEAM.search(p.get("home") or "") or NON_CLUB_TEAM.search(p.get("away") or ""):
        return True
    return any(isinstance(v, str) and EXHIBITION.search(v) for v in (p.get("extra") or {}).values())


def in_window(p: dict, date_from: str | None, date_to: str | None) -> bool:
    if p["utc"] is None:
        return False
    d = p["utc"].date().isoformat()
    return (not date_from or d >= date_from) and (not date_to or d <= date_to)


# ------------------------------------------------------------------- sync --

def sync_teams(client, season: str) -> dict:
    """Provider clubs -> our MLB teams, linked to competition MLB for `season`.
    An existing team is found by external_ids["api_baseball"], else by a
    UNIQUE normalized-name match (then stamped); it is never renamed. A club
    with no match is created under the provider's name. Non-club sides
    (all-star) are never created."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, CompetitionTeam, Sport, Team

    clubs = client.list_teams(season=int(season))
    rec = {"season": str(season), "provider_teams": len(clubs), "created": 0, "linked": 0,
           "stamped": 0, "existing": 0, "non_club_skipped": [], "ambiguous_name": []}
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.MLB,
                                                   Competition.code == "MLB")).scalars().first()
        if comp is None:
            raise RuntimeError("competition MLB not in DB: run `sync-competitions --sport mlb` first")
        teams = list(s.execute(select(Team).where(Team.sport == Sport.MLB)).scalars())
        by_ext = {str((t.external_ids or {}).get(SOURCE)): t for t in teams if (t.external_ids or {}).get(SOURCE)}
        for c in clubs:
            if NON_CLUB_TEAM.search(c["name"] or ""):
                rec["non_club_skipped"].append(c["name"])
                continue
            t = by_ext.get(str(c["id"]))
            if t is not None:
                rec["existing"] += 1
            else:
                n = norm(c["name"])
                cands = [x for x in teams if not (x.external_ids or {}).get(SOURCE)
                         and names_match(norm(x.name), n)]
                if len(cands) > 1:
                    rec["ambiguous_name"].append(c["name"])      # refused, never guessed
                    continue
                if cands:
                    t = cands[0]
                    t.external_ids = {**(t.external_ids or {}), SOURCE: str(c["id"])}
                    rec["stamped"] += 1
                else:
                    t = Team(sport=Sport.MLB, name=c["name"], tla=c.get("code"),
                             external_ids={SOURCE: str(c["id"])})
                    s.add(t)
                    s.flush()
                    teams.append(t)
                    rec["created"] += 1
                by_ext[str(c["id"])] = t
            if s.get(CompetitionTeam, {"competition_id": comp.id, "team_id": t.id, "season": str(season)}) is None:
                s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season=str(season)))
                rec["linked"] += 1
    return rec


def sync_matches(client, season: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    """One /games call for the season; the window filters locally. Returns the
    run receipt (see module doc). Teams are synced first (the ruled order)."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Result, Sport, Team

    team_rec = sync_teams(client, season)
    games = client._get("games", params={"league": _league_id(), "season": int(season)}).get("response") or []
    prov_all = provider_rows(games)
    rec = {"season": str(season), "window": [date_from, date_to], "provider_games": len(prov_all),
           "teams": team_rec, "created": 0, "updated": 0, "linked_existing": 0, "ambiguous": 0,
           "exhibition_skipped": 0, "team_missing": 0, "held_near_unkeyed": 0, "downgrade_refused": 0,
           "status_vocab": dict(Counter(f"{p['status_short']}|{p['status_long']}" for p in prov_all)),
           "unmapped_status": {}, "finished": 0, "stage_null_created": 0,
           "dh_marked": [], "known_limitation": KNOWN_LIMITATION}
    prov = []
    for p in prov_all:
        if not in_window(p, date_from, date_to):
            continue
        if is_exhibition(p):
            rec["exhibition_skipped"] += 1
            continue
        prov.append(p)
    unm = Counter(p["status_short"] for p in prov if (p["status_short"] or "").upper() not in STATUS_MAP)
    rec["unmapped_status"] = dict(unm)

    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.MLB,
                                                   Competition.code == "MLB")).scalars().first()
        team_by_ext = {str((t.external_ids or {}).get(SOURCE)): t
                       for t in s.execute(select(Team).where(Team.sport == Sport.MLB)).scalars()
                       if (t.external_ids or {}).get(SOURCE)}
        rows = list(s.execute(select(Match).where(Match.competition_id == comp.id,
                                                  Match.season == str(season))).scalars())
        by_ext = {str((m.external_ids or {}).get(SOURCE)): m for m in rows if (m.external_ids or {}).get(SOURCE)}
        # Our rows not yet keyed to the provider (statsapi-origin): pair them by the probe's rule.
        unlinked = [m for m in rows if not (m.external_ids or {}).get(SOURCE)
                    and in_window({"utc": m.utc_date}, date_from, date_to)]
        ours = [{"id": m.id, "utc": m.utc_date, "home": m.home_team.name, "away": m.away_team.name,
                 "stage": m.stage, "home_score": m.home_score, "away_score": m.away_score} for m in unlinked]
        fresh = [p for p in prov if str(p["id"]) not in by_ext]
        pr = pair(ours, fresh)
        mid = {m.id: m for m in unlinked}
        for o, p in pr["pairs"]:
            m = mid[o["id"]]
            m.external_ids = {**(m.external_ids or {}), SOURCE: str(p["id"])}
            by_ext[str(p["id"])] = m
            rec["linked_existing"] += 1
        rec["ambiguous"] = len(pr["ambiguous"])
        # The known limitation, on rows that exist: an unpaired row of ours
        # whose same-teams provider game is already paired (doubleheader game 2).
        for sx in suspects(pr["ours_unmatched"], prov, {**pr["paired_to"],
                                                         **{int(k): v.id for k, v in by_ext.items() if k.isdigit()}}):
            if sx["doubleheader"]:
                m = mid[sx["match_id"]]
                if (m.external_ids or {}).get(NOTE_KEY) != UNAVAILABLE:
                    m.external_ids = {**(m.external_ids or {}), NOTE_KEY: UNAVAILABLE}
                rec["dh_marked"].append({"match_id": m.id, "game": sx["game"], "utc": sx["utc"]})
        # A provider game near one of our still-unkeyed rows (ambiguous, or
        # unpaired for any reason) is never CREATED: that would duplicate it.
        held = [o for o in pr["ambiguous"] + pr["ours_unmatched"]]
        for p in prov:
            m = by_ext.get(str(p["id"]))
            status = map_status(p)
            if m is None and any(_near(o, p) for o in held):
                rec["held_near_unkeyed"] += 1
                continue
            if m is None:
                home, away = team_by_ext.get(str(p["home_id"])), team_by_ext.get(str(p["away_id"]))
                if home is None or away is None:
                    rec["team_missing"] += 1
                    continue
                m = Match(sport=Sport.MLB, competition_id=comp.id, season=str(season), stage=None,
                          utc_date=p["utc"], status=MatchStatus[status], home_team_id=home.id,
                          away_team_id=away.id, external_ids={SOURCE: str(p["id"])})
                s.add(m)
                by_ext[str(p["id"])] = m
                rec["created"] += 1
                rec["stage_null_created"] += 1
            else:
                if m.status == MatchStatus.FINISHED and status != "FINISHED":
                    rec["downgrade_refused"] += 1
                    continue
                m.status = MatchStatus[status]
                m.utc_date = p["utc"]
                rec["updated"] += 1
            if p["status_short"]:
                m.status_raw = str(p["status_short"])[:16]
            if status == "FINISHED":
                m.home_score, m.away_score = p["home_runs"], p["away_runs"]
                m.full_time_result = (Result.HOME if p["home_runs"] > p["away_runs"] else
                                      Result.AWAY if p["away_runs"] > p["home_runs"] else None)
                rec["finished"] += 1
    return rec


def _near(o: dict, p: dict) -> bool:
    return (p["utc"] is not None and names_match(norm(o["home"]), norm(p["home"]))
            and names_match(norm(o["away"]), norm(p["away"]))
            and abs((p["utc"] - o["utc"]).total_seconds()) <= TOL_H * 3600)


def _league_id() -> int:
    from src.adapters.api_baseball import MLB_LEAGUE_ID
    return MLB_LEAGUE_ID
