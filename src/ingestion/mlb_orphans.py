"""
RETIRE-ORPHANS FOR MLB (ARCHITECT 2026-10-20, addendum 146 item 3(a); #568), verbatim: "A retire-orphans step for MLB,
explicit, dry run first, in the morning block after the MLB sync (never inside the watch): a SCHEDULED MLB row becomes
STALE_ORPHAN on TWO receipts, both printed per row: (1) the row's provider id is absent from the provider's answer for a
window that covers its date (the strict read's own evidence, one call), and (2) the series arithmetic from the #605
fields shows the series decided before this row's game number: the pair's FINISHED games of the same season and stage,
wins per side, against games_in_series of any row of that series (needed = ceil(gis/2)). Either receipt missing -> the
row stays SCHEDULED (law 4). Never CANCELLED: the provider said nothing. Acceptance cases: 50555 (ALCS Game 7, dropped
10-20) and 50549 (MIL at LAD, dropped 10-16; its own series fields are null, so receipt (2) reads the series' other
rows). The dry run's console on the laptop goes in the PR body before merge."

The readings built here (each stated in the PR for the architect):
  * CANDIDATES: the season's MLB rows that are SCHEDULED, carry a postseason stage (the statsapi gameType F/D/L/W,
    mlb_apisports.POSTSEASON_TYPES) and have both scores NULL. The series arithmetic holds for a postseason series only:
    a regular-season pair plays several series a season and a decided one still plays out. Every other SCHEDULED row
    of the season whose start is past (stage R or NULL included) is printed, never a candidate.
  * RECEIPT (1), "a window that covers its date ... one call": the season's postseason window, ONE GET for the whole
    run ({sportId 1, gameType F,D,L,W, season}, no dates; the precedent: cli.py mlb-time-audit). It covers every
    candidate's date. The strict read's own D..D window is not used: an if-necessary game's own day can list zero
    games. The ids are the answer's raw gamePks (mlb_stats_api.listed_game_pks), not the sync's `held`: an entry the
    sync would skip still lists its game. ABSENT: the call answered, the row's id is not among them, and they hold at
    least one stored gamePk of the row's series (its other rows): an answer that lists no game of the series is no
    evidence about it. LISTED: the row's id is among them. NO RECEIPT: the call raised, the answer lists no game, the
    row has no mlb_stats_api id, or the answer lists no game of the row's series.
  * RECEIPT (2), read from the stored rows only: the SERIES is every row of the competition with this row's season and
    stage and its two teams in either order (LCS home and away alternate), of every status, this row included. Its
    games_in_series is the one value its rows carry; needed = (gis + 1) // 2. NO RECEIPT for: games_in_series null on
    every row, or two values; a gis under 1, or even (a best-of-N is odd: an even N lets both sides reach needed, a
    tie); the series columns not migrated; a LIVE game of the series; a FINISHED game without a decided score; two
    FINISHED rows of one gamePk or one game number; more FINISHED games than gis; a side past needed; two FINISHED games
    sharing the latest start; two FINISHED games on one ET day (one game stored twice); a clinch (the latest FINISHED game) the other side won; a clinch whose stored game number
    is not k, the count of FINISHED games (above k: a FINISHED game of the series is not stored; below: more FINISHED
    rows than its number); with no stored clinch number, a FINISHED row storing a number of k or more (a FINISHED
    game not stored; with no number stored on any FINISHED row such a gap cannot be seen). DECIDED: a side has `needed` wins over the k FINISHED games and the series ended before this
    row's game: its own series_game_number n is after the clinch's (its stored number, equal to k; with none stored the
    receipt says "after k FINISHED games"), or, with its own n null (50549), the clinching game started before this
    row's stored start ("game number: null (own); read by start"; at the same start: NOT DECIDED). The two no-start
    guards (a FINISHED game, or the row, with no start) cannot fire on a current-schema DB (matches.utc_date is NOT
    NULL) and stay as guards. series_description is printed, never a gate.
  * THE WRITE: retire = receipt (1) ABSENT and receipt (2) DECIDED; every other row stays SCHEDULED, both receipts
    printed. --apply needs --backup PATH and --match-ids naming the rows (cli.py; as merge-teams names its pairs): the
    apply plans again in its own session, and a named row whose fresh plan is retire becomes STALE_ORPHAN with
    external_ids["mlb_stats_api_orphaned_at"] (dedupe-matches --orphans' mark, match_dedupe.py); a named row planned
    otherwise is REFUSED and stays. Nothing else on the row changes; nothing is CANCELLED or deleted. A dry run rolls
    back. SELF-HEAL needs no code: a later sync that lists the gamePk again finds the row by its id and sets its status
    from the listing (service._apply_match_updates); the orphaned_at marker stays on the row.
"""
from __future__ import annotations

from collections import Counter
from datetime import timezone
from zoneinfo import ZoneInfo

COMPETITION = "MLB"
SOURCE = "mlb_stats_api"
ORPHANED_AT = f"{SOURCE}_orphaned_at"
NY = ZoneInfo("America/New_York")
RETIRE = "retire"
STAYS = ("listed", "not decided", "no receipt 1", "no receipt 2")


def et(dt) -> str:
    """A stored naive-UTC start in America/New_York (the feed's own date, as closing.ny_date reads it)."""
    return dt.replace(tzinfo=timezone.utc).astimezone(NY).strftime("%a %Y-%m-%d %H:%M ET") if dt else "no start"


def iso_z(dt) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _sid(m) -> str | None:
    v = (m.external_ids or {}).get(SOURCE)
    return str(v) if v is not None and str(v).strip() else None


def is_candidate(m, season: str, postseason) -> bool:
    from src.db.schema import MatchStatus
    return (m.season == season and m.status == MatchStatus.SCHEDULED and m.stage in postseason
            and m.home_score is None and m.away_score is None)


def not_candidate_why(m, comp_id: int, season: str, postseason) -> str:
    """Why a stored row is not a candidate (a named id the apply refuses; a past SCHEDULED row the run prints)."""
    from src.db.schema import MatchStatus
    if m is None:
        return "no such match"
    if m.competition_id != comp_id:
        return "not an MLB row"
    if m.season != season:
        return f"season {m.season}, not {season}"
    if m.status != MatchStatus.SCHEDULED:
        return f"status {m.status.name}, not SCHEDULED"
    if m.stage not in postseason:
        return (f"stage {m.stage or 'null'}: not a postseason row (the series arithmetic is the postseason's; "
                "never a candidate)")
    return f"a score is stored ({m.home_score}-{m.away_score})"


def receipt_one(sid: str | None, answer: dict, series_sids=()) -> dict:
    """Receipt (1) for one row against the run's one answer ({params, pks, error}); `series_sids` are the stored
    gamePks of the row's series' other rows (its siblings)."""
    sibs = sorted({s for s in series_sids if s is not None and s != sid})
    r = {"params": answer["params"], "games": len(answer["pks"] or []), "sid": sid, "series_sids": sibs}
    if answer["error"]:
        return {**r, "verdict": "NO RECEIPT", "why": f"the provider call failed: {answer['error']}"}
    if not answer["pks"]:
        return {**r, "verdict": "NO RECEIPT", "why": "the provider's answer lists no game"}
    if sid is None:
        return {**r, "verdict": "NO RECEIPT", "why": "the row has no mlb_stats_api id"}
    pks = set(answer["pks"])
    if sid in pks:
        return {**r, "verdict": "LISTED", "why": f"gamePk {sid} is in the provider's answer"}
    hit = [s for s in sibs if s in pks]
    r["series_listed"] = hit
    if not hit:                                    # an answer that does not cover this series is no evidence for it
        return {**r, "verdict": "NO RECEIPT", "why": "the answer lists no game of this series (" + (
            f"its other gamePks {', '.join(sibs)}: none listed" if sibs
            else "no other row of the series carries a gamePk") + ")"}
    return {**r, "verdict": "ABSENT", "why": f"gamePk {sid} is not in the provider's answer, which lists {len(hit)} "
                                             f"of the series' other {len(sibs)} gamePks"}


def receipt_two(m, rows: list, fields: dict | None, name) -> dict:
    """Receipt (2) for candidate `m` from its series `rows` (this row included) and the stored series fields."""
    from src.db.schema import MatchStatus

    rows = sorted(rows, key=lambda x: (x.utc_date is None, x.utc_date, x.id))

    def f(x):
        return (fields or {}).get(x.id) or {}

    r = {"ids": [x.id for x in rows], "descriptions": sorted({f(x).get("series_description") for x in rows
                                                               if f(x).get("series_description") is not None}),
         "own_n": f(m).get("series_game_number"), "fields_stored": fields is not None}

    def no(why):
        return {**r, "verdict": "NO RECEIPT", "why": why}

    if fields is None:
        return no("series fields not stored (migrate_match_series_fields.py not run)")
    gis_of: dict = {}
    for x in rows:
        if f(x).get("games_in_series") is not None:
            gis_of.setdefault(f(x)["games_in_series"], []).append(x.id)
    if not gis_of:
        return no(f"games_in_series null on every row of the series ({', '.join(map(str, r['ids']))})")
    if len(gis_of) > 1:
        return no("games_in_series disagree across the series ("
                  + "; ".join(f"{g} on {', '.join(map(str, ids))}" for g, ids in sorted(gis_of.items())) + ")")
    (gis, gis_ids), = gis_of.items()
    needed = (gis + 1) // 2
    r.update(gis=gis, gis_ids=gis_ids, needed=needed)
    if needed < 1:
        return no(f"games_in_series {gis} is not a series length (needed {needed})")
    if gis % 2 == 0:                               # best-of-N is odd: an even N lets both sides reach needed
        return no(f"games_in_series {gis} is even: both sides can reach needed {needed} (a tied series)")
    live = [x.id for x in rows if x.status == MatchStatus.LIVE]
    if live:
        return no(f"a game of the series is LIVE ({', '.join(map(str, live))})")
    fin = [x for x in rows if x.status == MatchStatus.FINISHED]
    bad = [x for x in fin if x.home_score is None or x.away_score is None or x.home_score == x.away_score]
    if bad:
        return no("FINISHED without a decided score: " + ", ".join(f"{x.id} ({x.home_score}-{x.away_score})"
                                                                   for x in bad))
    for what, key in (("gamePk", _sid), ("game number", lambda x: f(x).get("series_game_number"))):
        seen = Counter(key(x) for x in fin if key(x) is not None)
        twin = sorted(k for k, n in seen.items() if n > 1)
        if twin:
            return no(f"two FINISHED rows of one {what} ({', '.join(map(str, twin))})")
    if any(x.utc_date is None for x in fin):     # unreachable on a current-schema DB (matches.utc_date NOT NULL)
        return no("a FINISHED game of the series has no start")
    wins = Counter({m.home_team_id: 0, m.away_team_id: 0})
    for x in fin:
        wins[x.home_team_id if x.home_score > x.away_score else x.away_team_id] += 1
    k = len(fin)
    top = max(wins.values())
    r.update(k=k, wins=sorted(((name(t), n) for t, n in wins.items()), key=lambda p: (-p[1], p[0])))
    if k > gis:
        return no(f"{k} FINISHED games, more than games_in_series {gis}")
    if top > needed:
        return no(f"a game after the clinch ({top} wins against needed {needed})")
    if top < needed:
        return {**r, "verdict": "NOT DECIDED", "why": f"no side has {needed} wins"}
    last = max(x.utc_date for x in fin)
    clinch = [x for x in fin if x.utc_date == last]
    if len(clinch) > 1:
        return no(f"two FINISHED games share the latest start ({', '.join(str(x.id) for x in clinch)})")
    # a postseason series plays one game a day: two FINISHED rows of it on one ET day are one game stored twice (a
    # re-keyed gamePk, a row from another source, neither carrying a game number) whose win the count would take
    # twice, so an undecided series could read decided (#631 review)
    by_day: dict = {}
    for x in fin:
        by_day.setdefault(x.utc_date.replace(tzinfo=timezone.utc).astimezone(NY).date(), []).append(x.id)
    day = sorted((d, sorted(ids)) for d, ids in by_day.items() if len(ids) > 1)
    if day:
        return no(f"two FINISHED games on one day ({day[0][0]} ET: {', '.join(map(str, day[0][1]))})")
    c = clinch[0]
    leader = next(t for t, n in wins.items() if n == top)   # one side: gis odd and k <= gis, so 2 * needed > k
    if (c.home_team_id if c.home_score > c.away_score else c.away_team_id) != leader:
        return no(f"the latest FINISHED game ({c.id}) was won by the side without {needed} wins")
    cn = f(c).get("series_game_number")
    # with no stored clinch number, k stands in for it: a FINISHED row that stores a number of k or more shows a
    # FINISHED game of the series is not stored (k undercounts the games played)
    seen = [f(x).get("series_game_number") for x in fin if x is not c and f(x).get("series_game_number") is not None]
    if cn is None and seen and max(seen) >= k:
        return no(f"a FINISHED game of the series is not stored (game {max(seen)} FINISHED before the clinch, "
                  f"{k} FINISHED)")
    if cn is not None and cn > k:
        return no(f"a FINISHED game of the series is not stored (clinch is game {cn}, {k} FINISHED)")
    if cn is not None and cn < k:
        return no(f"more FINISHED games than the clinch's game number (clinch is game {cn}, {k} FINISHED)")
    r.update(clinch=c.id, clinch_start=c.utc_date, clinch_n=cn)
    if r["own_n"] is not None:
        over = f"game {cn}" if cn is not None else f"{k} FINISHED games"
        r["by"] = f"this row game {r['own_n']} (own), the series over after {over}"
        if k < r["own_n"]:
            return {**r, "verdict": "DECIDED", "why": (f"decided in game {cn}" if cn is not None else
                                                       f"decided after {k} FINISHED games")
                    + f", before game {r['own_n']}"}
        return {**r, "verdict": "NOT DECIDED", "why": f"game {r['own_n']} (own) is not after "
                + (f"game {cn}, the clinch" if cn is not None else f"{k} FINISHED games")}
    if m.utc_date is None:                       # unreachable on a current-schema DB (matches.utc_date NOT NULL)
        return no("game number: null (own) and the row has no start")
    r["by"] = f"game number: null (own); read by start: the clinch {et(c.utc_date)}, this row {et(m.utc_date)}"
    if c.utc_date < m.utc_date:
        return {**r, "verdict": "DECIDED", "why": "the clinch started before this row's start"}
    return {**r, "verdict": "NOT DECIDED", "why": "the clinch did not start before this row's start"}


def action(r1: dict, r2: dict) -> str:
    """retire only on both receipts; else the first that keeps the row SCHEDULED (law 4)."""
    if r1["verdict"] == "ABSENT" and r2["verdict"] == "DECIDED":
        return RETIRE
    if r1["verdict"] == "LISTED":
        return "listed"
    if r1["verdict"] != "ABSENT":
        return "no receipt 1"
    return "not decided" if r2["verdict"] == "NOT DECIDED" else "no receipt 2"


def run(season: str, adapter, apply: bool = False, named=None, now=None) -> dict:
    """Plan (and with apply, retire the named rows planned retire). Returns the receipt; cli.py prints lines()."""
    from sqlalchemy import select

    from src.adapters.mlb_stats_api import listed_game_pks
    from src.db.database import read_match_series, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Team
    from src.ingestion import match_dedupe as md
    from src.ingestion.mlb_apisports import POSTSEASON_TYPES
    from src.timeutil import utc_now_naive

    if apply and not named:
        raise ValueError("--apply names the rows it retires (--match-ids)")
    now = now or utc_now_naive()
    season = str(season)
    out = {"competition": COMPETITION, "season": season, "applied": apply, "now": now, "named": sorted(named or ())}
    with session_scope() as s:
        out["before"] = md.state(s, COMPETITION, SOURCE)              # ValueError: MLB not stored
        comp = s.execute(select(Competition).where(Competition.code == COMPETITION)).scalar_one()
        rows = [m for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars()
                if m.season == season]
        cands = sorted((m for m in rows if is_candidate(m, season, POSTSEASON_TYPES)), key=lambda m: m.id)
        cand_ids = {m.id for m in cands}
        names = {t.id: t.name for t in s.execute(select(Team).where(Team.id.in_(
            {t for m in rows for t in (m.home_team_id, m.away_team_id)}))).scalars()}
        name = lambda t: names.get(t, f"team {t}")  # noqa: E731
        past = [m for m in rows if m.status == MatchStatus.SCHEDULED and m.id not in cand_ids and m.utc_date
                and m.utc_date < now]
        out["others"] = [{"id": m.id, "stage": m.stage, "utc": m.utc_date,
                          "why": not_candidate_why(m, comp.id, season, POSTSEASON_TYPES)}
                         for m in sorted(past, key=lambda m: (m.utc_date, m.id))]
        fields = read_match_series(s, [m.id for m in rows if m.stage in POSTSEASON_TYPES])

        answer = {"params": None, "pks": None, "error": None, "dates": None, "calls": 0}
        if cands:                                                     # one call for the whole run, or none
            answer["params"] = adapter.postseason_params(season, POSTSEASON_TYPES)
            answer["calls"] = 1
            try:
                data = adapter.postseason_answer(season, POSTSEASON_TYPES)
                answer["pks"] = listed_game_pks(data)
                blocks = data.get("dates") if isinstance(data, dict) else None
                days = sorted(str(b["date"]) for b in (blocks if isinstance(blocks, list) else [])
                              if isinstance(b, dict) and b.get("date"))
                answer["dates"] = (days[0], days[-1]) if days else None
            except Exception as e:  # noqa: BLE001 — NO RECEIPT, never absent (the dedupe idiom)
                answer["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        out["answer"] = answer

        def row_view(x):
            sf = (fields or {}).get(x.id) or {}
            return {"id": x.id, "sid": _sid(x), "n": sf.get("series_game_number"), "gis": sf.get("games_in_series"),
                    "utc": x.utc_date, "status": x.status.name, "status_raw": x.status_raw,
                    "home": name(x.home_team_id), "away": name(x.away_team_id),
                    "home_score": x.home_score, "away_score": x.away_score}

        plan = []
        for m in cands:
            series = [x for x in rows if x.stage == m.stage
                      and {x.home_team_id, x.away_team_id} == {m.home_team_id, m.away_team_id}]
            r1 = receipt_one(_sid(m), answer, [_sid(x) for x in series if x.id != m.id])
            r2 = receipt_two(m, series, fields, name)
            plan.append({"id": m.id, "sid": _sid(m), "utc": m.utc_date, "stage": m.stage, "season": m.season,
                         "home": name(m.home_team_id), "away": name(m.away_team_id), "r1": r1, "r2": r2,
                         "action": action(r1, r2), "series": [row_view(x) for x in sorted(
                             series, key=lambda x: (x.utc_date is None, x.utc_date, x.id))], "_row": m})
        out["counts"] = dict(Counter(p["action"] for p in plan))
        applied, refused = [], []
        if apply:
            guard = md._check_allows_orphan(s)
            by_id = {p["id"]: p for p in plan}
            for i in sorted(named):
                p = by_id.get(i)
                if p is None:
                    refused.append({"id": i, "why": "not a candidate: " + not_candidate_why(
                        s.get(Match, i), comp.id, season, POSTSEASON_TYPES)})
                elif p["action"] != RETIRE:
                    refused.append({"id": i, "why": f"its plan is '{p['action']}', not retire (it stays SCHEDULED)"})
                elif guard:
                    refused.append({"id": i, "why": f"orphan mark refused: {guard}"})
                else:
                    m = p["_row"]
                    ext = dict(m.external_ids or {})
                    ext[ORPHANED_AT] = now.isoformat(timespec="seconds")
                    m.external_ids = ext
                    m.status = MatchStatus.STALE_ORPHAN
                    applied.append(i)
            s.flush()
        else:
            s.rollback()
        out["applied_ids"], out["refused_at_apply"] = applied, refused
        out["not_named"] = [p["id"] for p in plan if p["action"] == RETIRE and p["id"] not in set(named or ())]
        out["plan"] = [{k: v for k, v in p.items() if not k.startswith("_")} for p in plan]
        out["after"] = md.state(s, COMPETITION, SOURCE) if apply else out["before"]
    return out


def _params_text(p: dict | None) -> str:
    return "{" + ", ".join(f"{k} {v}" for k, v in p.items()) + "}" if p else "none"


def _score(v: dict) -> str:
    if v["home_score"] is None and v["away_score"] is None:
        return f"{v['away']} @ {v['home']}, no score"
    return f"{v['away']} {v['away_score']} @ {v['home']} {v['home_score']}"


def _r2_text(r2: dict, p: dict) -> str:
    desc = (" | ".join(f'"{d}"' for d in r2["descriptions"]) + (" (they differ; printed, never a gate)"
                                                                 if len(r2["descriptions"]) > 1 else "")
            if r2["descriptions"] else "null")
    t = (f"receipt 2: {r2['verdict']} ({r2['why']}) · series {desc} · stage {p['stage']} · season {p['season']}")
    if "gis" in r2:
        t += (f" · games_in_series {r2['gis']} (from {', '.join(map(str, r2['gis_ids']))}) · needed {r2['needed']}")
    if "wins" in r2:
        t += (" · wins " + ", ".join(f"{n} {w}" for n, w in r2["wins"]) + f" over {r2['k']} FINISHED")
    if "clinch" in r2:
        t += f" · clinch match {r2['clinch']} ({et(r2['clinch_start'])})"
    if "by" in r2:
        t += f" · {r2['by']}"
    elif r2["fields_stored"]:
        t += " · game number: null (own)" if r2["own_n"] is None else f" · this row game {r2['own_n']} (own)"
    return t


def lines(r: dict) -> list[str]:
    """The console: the header, the answer, the plan, every candidate whole with both receipts and its series' rows,
    every past SCHEDULED row that is not a candidate, the state (and with --apply what was written)."""
    from src.ingestion.mlb_apisports import POSTSEASON_TYPES

    c, a = r["counts"], r["answer"]
    out = [f"RETIRE-ORPHANS {r['competition']} {r['season']} ({SOURCE}) · "
           f"{'APPLIED' if r['applied'] else 'DRY-RUN (nothing written)'} · candidates {len(r['plan'])} (SCHEDULED, "
           f"no score, stage {'/'.join(POSTSEASON_TYPES)}) · not candidates, past their start {len(r['others'])} · "
           f"provider calls {a['calls']}"]
    if not a["calls"]:
        out.append("  provider answer: no call (no candidate)")
    elif a["error"]:
        out.append(f"  provider answer: GET schedule {_params_text(a['params'])} (the season's postseason, one call)"
                   f" · ERROR {a['error']} · no receipt 1 for any row")
    else:
        span = f" · dates {a['dates'][0]}..{a['dates'][1]}" if a["dates"] else ""
        out.append(f"  provider answer: GET schedule {_params_text(a['params'])} (the season's postseason, one call)"
                   f" · {len(a['pks'])} game(s){span}")
        out.append(f"  answer gamePks ({len(a['pks'])}): {', '.join(a['pks']) or 'none'}")
    stays = sum(c.get(k, 0) for k in STAYS)
    out.append(f"  plan: retire {c.get(RETIRE, 0)} · stays SCHEDULED {stays} ("
               + " · ".join(f"{k} {c.get(k, 0)}" for k in STAYS) + ")")
    for p in r["plan"]:
        out.append(f"  [{p['action']}] match {p['id']} gamePk {p['sid'] or 'null'} · {p['away']} @ {p['home']} · "
                   f"stage {p['stage']} · {iso_z(p['utc'])} ({et(p['utc'])})")
        r1 = p["r1"]
        out.append(f"    receipt 1: {r1['verdict']} ({r1['why']}) · params {_params_text(r1['params'])} · answer "
                   f"{r1['games']} game(s)")
        out.append("    " + _r2_text(p["r2"], p))
        for v in p["series"]:
            out.append(f"      match {v['id']} · gamePk {v['sid'] or 'null'} · game "
                       f"{'null' if v['n'] is None else v['n']} of {'null' if v['gis'] is None else v['gis']} · "
                       f"{et(v['utc'])} · {v['status']} · status_raw {v['status_raw'] or 'null'} · {_score(v)}")
    for o in r["others"]:
        out.append(f"  [not a candidate] match {o['id']} · stage {o['stage'] or 'null'} · {iso_z(o['utc'])} "
                   f"({et(o['utc'])}) · SCHEDULED, past its start · {o['why']}")
    b = r["before"]
    out.append(f"  state before: MLB rows {b['rows']} · stale orphans {b['stale_orphans']}")
    if r["applied"]:
        out.append(f"  applied: retired {len(r['applied_ids'])} "
                   f"({', '.join(map(str, r['applied_ids'])) or 'none'}) · refused at apply {len(r['refused_at_apply'])}"
                   f" · named {', '.join(map(str, r['named']))}")
        for x in r["refused_at_apply"]:
            out.append(f"  REFUSED match {x['id']}: {x['why']}")
        for i in r["not_named"]:
            out.append(f"  [not named] match {i}: planned retire, not named by --match-ids: stays SCHEDULED")
        a2 = r["after"]
        out.append(f"  state after:  MLB rows {a2['rows']} · stale orphans {a2['stale_orphans']} "
                   f"(+{a2['stale_orphans'] - b['stale_orphans']})")
    return out
