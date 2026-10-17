"""
SCORE-PRESENCE DRY RUN (#493) — read-only: every stored row the adapters' fixed score-presence rule would change at the
next sync of its season, counted per competition-season, with the ids. It writes nothing. The ruling, verbatim
(ARCHITECT 2026-10-16, addendum 81 item 3): "Code's PR fixes the ordering, prints a --dry-run listing of every row the
rule would change (count per competition-season, and the ids), and the operator's block runs it after the backup; the
receipt is pasted on the PR before merge."

HOW (law 1: read from the code):
  * The vehicle that writes is sync-matches. For each listed game, _apply_match_updates sets the stored status to the
    adapter's and also writes the kickoff, matchday, stage and every present score. So the dry run makes the same single
    /games call a season read makes (no date). It parses the answer with the adapter's own _parse_games and keeps each
    game's provider status as sent (raw_shorts).
  * The fix changes exactly two classes of listed game, both with their two totals present (fix_class):
      ABSENT     no status stated: FINISHED now (before #493: SCHEDULED)
      NONE_TEXT  the provider's own text "None", a stated status the map lacks: SCHEDULED now (before #493: FINISHED)
    Every other listed game parses as it did before the fix (src/adapters/api_sports_status.py).
  * A stored row is found by its provider id (external_ids[<source>]) in the competition-season. It is CHANGED when its
    stored status differs from the fixed parse's.
  * The receipt also reconciles the stored SCHEDULED rows carrying both scores (the count addendum 81 cites: NCAA 2024
    120, NFL 2024 16), and it says what the same whole-season sync would write besides the rule: other status
    changes, kickoffs and scores. The kickoffs matter: matches.utc_date is one of the NCAA stream fingerprints' fields
    (ncaa_v1r_gate.FINGERPRINT_FIELDS) and orders the walk; matches.status is neither.
Scores are never printed (the NCAA fences print no outcome); ids, kickoffs, stages and statuses are.
"""
from __future__ import annotations

import json
from typing import Callable

COMPETITIONS = ("NFL", "NCAA", "NHL")       # the competitions of the two adapters that carry the rule
ABSENT, NONE_TEXT = "absent", "text 'None'"


def fix_class(short: str | None, home_total, away_total) -> str | None:
    """Pure. The class of the #493 fix a listed game falls in (ABSENT / NONE_TEXT), or None when the fix leaves its
    parse as it was: a total missing, or any other stated status."""
    if home_total is None or away_total is None:
        return None
    if short is None:
        return ABSENT
    return NONE_TEXT if short == "None" else None


def read_listing(adapter, competition_code: str, season: str) -> tuple[list, dict]:
    """(the adapter's NormalizedMatch rows, {provider id: provider short or None}) for one season: the single /games
    call list_matches makes for a season read without a date, parsed by the adapter's own _parse_games."""
    from src.adapters.api_american_football import _league_for
    from src.adapters.api_hockey import NHL_LEAGUE_ID, APIHockeyAdapter

    year = int(str(season).split("/")[0])
    shorts: dict = {}
    if isinstance(adapter, APIHockeyAdapter):
        data = adapter._get("games", params={"league": NHL_LEAGUE_ID, "season": year})
        return adapter._parse_games(data, str(year), raw_shorts=shorts), shorts
    data = adapter._get("games", params={"league": _league_for(competition_code), "season": year})
    return adapter._parse_games(data, competition_code, str(year), raw_shorts=shorts), shorts


def stored_seasons(competition_code: str) -> list[str] | None:
    """Read-only: every season string the DB stores for the competition, sorted; None when the competition is not in
    the DB."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match

    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
        if comp is None:
            s.rollback()
            return None
        out = sorted({x for x in s.execute(select(Match.season).where(Match.competition_id == comp.id)).scalars()
                      if x is not None})
        s.rollback()
    return out


def stored_rows(competition_code: str, season: str, source: str) -> list[dict]:
    """Read-only: the competition-season's stored rows, each {id, pid (its `source` id or None), utc_date, stage,
    status (the enum's name), home_score, away_score}."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match

    with session_scope() as s:
        q = (select(Match).join(Competition, Match.competition_id == Competition.id)
             .where(Competition.code == competition_code, Match.season == season).order_by(Match.utc_date, Match.id))
        out = [{"id": m.id, "pid": (None if (m.external_ids or {}).get(source) is None
                                    else str((m.external_ids or {}).get(source))),
                "utc_date": m.utc_date, "stage": m.stage, "status": getattr(m.status, "name", str(m.status)),
                "home_score": m.home_score, "away_score": m.away_score} for m in s.execute(q).scalars()]
        s.rollback()
    return out


def compare(listing: list, shorts: dict, rows: list[dict]) -> dict:
    """Pure. One competition-season: the fixed parse (`listing`, `shorts`) against the stored `rows`."""
    by_pid = {r["pid"]: r for r in rows if r["pid"] is not None}        # the sync's cache: the last row of an id
    r = {"listing": len(listing), "stored": len(rows), "changes": [], "already": [], "not_stored": [],
         "other_status": [], "kickoff": [], "scores": [], "left": [], "sched_both": 0,
         "classes": {ABSENT: 0, NONE_TEXT: 0}}
    listed = {}
    for nm in listing:
        pid = str(nm.source_id)
        short = shorts.get(pid)
        cls = fix_class(short, nm.home_score, nm.away_score)
        listed[pid] = (nm, short, cls)
        if cls:
            r["classes"][cls] += 1
        m = by_pid.get(pid)
        if m is None:
            if cls:
                r["not_stored"].append({"pid": pid, "class": cls, "utc_date": nm.utc_date, "new": nm.status.name})
            continue
        new = nm.status.name
        if cls:
            (r["changes"] if m["status"] != new else r["already"]).append(
                {**m, "class": cls, "new": new})
        elif m["status"] != new:
            r["other_status"].append({**m, "new": new, "short": short})
        if m["utc_date"] != nm.utc_date:
            r["kickoff"].append({**m, "new_utc": nm.utc_date})
        if ((nm.home_score is not None and nm.home_score != m["home_score"])
                or (nm.away_score is not None and nm.away_score != m["away_score"])):
            r["scores"].append(m)
    for m in rows:                                          # the stored SCHEDULED rows carrying both scores
        if m["status"] != "SCHEDULED" or m["home_score"] is None or m["away_score"] is None:
            continue
        r["sched_both"] += 1
        got = listed.get(m["pid"]) if m["pid"] is not None else None
        if got is None:
            r["left"].append({**m, "why": "not in the listing (the sync does not touch it)"})
            continue
        nm, short, cls = got
        if cls and nm.status.name != m["status"]:
            continue                                        # the rule changes it (listed above)
        if cls == NONE_TEXT:
            why = "the provider states 'None' (a stated status the map lacks: stays SCHEDULED, law 4)"
        elif short is None:
            why = "no status stated and a score missing in the listing: stays SCHEDULED (no score, not FINISHED)"
        else:
            why = f"the provider states {short!r} (the sync writes {nm.status.name})"
        r["left"].append({**m, "why": why})
    for k in ("changes", "already", "other_status", "kickoff", "scores"):
        r[k].sort(key=lambda x: (x["utc_date"] is None, x["utc_date"] or 0, x["id"]))
    return r


def _when(d) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S") if d is not None else "no kickoff"


def _row(m) -> str:
    return f"match {m['id']} · provider {m['pid'] or '—'} · {_when(m['utc_date'])}Z · {m['stage'] or 'no stage'}"


def lines(code: str, season: str, source: str, r: dict) -> list[str]:
    """One competition-season's receipt, every row whole (#491: a receipt cuts nothing)."""
    L = [f"{code} {season} · source {source} · listing {r['listing']} games · stored {r['stored']} rows",
         f"  THE RULE CHANGES {len(r['changes'])} stored row(s) at the next sync of {code} {season} · listed with both "
         f"scores and no status stated {r['classes'][ABSENT]} · listed with both scores and the text 'None' "
         f"{r['classes'][NONE_TEXT]} · already as the fixed parse reads {len(r['already'])} · not stored "
         f"{len(r['not_stored'])}"]
    for m in r["changes"]:
        L.append(f"    {_row(m)} · {m['class']} · {m['status']} → {m['new']}")
    for m in r["already"]:
        L.append(f"    already: {_row(m)} · {m['class']} · {m['status']}")
    for m in r["not_stored"]:
        L.append(f"    not stored: provider {m['pid']} · {_when(m['utc_date'])}Z · {m['class']} · no stored row holds "
                 f"this id; the sync writes it {m['new']} (created, or re-keyed onto a stored row, if both teams are "
                 f"stored)")
    L.append(f"  stored SCHEDULED with both scores: {r['sched_both']} · the rule changes "
             f"{len([1 for x in r['changes'] if x['status'] == 'SCHEDULED'])} · the rule leaves {len(r['left'])}")
    for m in r["left"]:
        L.append(f"    left: {_row(m)} · {m['why']}")
    L.append(f"  THE SAME WHOLE-SEASON SYNC ALSO WRITES (not the rule's): status {len(r['other_status'])} · kickoff "
             f"{len(r['kickoff'])} · scores {len(r['scores'])} (values not printed)")
    for m in r["other_status"]:
        said = "no status stated" if m["short"] is None else f"the provider states {m['short']!r}"
        L.append(f"    status: {_row(m)} · {m['status']} → {m['new']} ({said})")
    for m in r["kickoff"]:
        L.append(f"    kickoff: match {m['id']} · provider {m['pid']} · {_when(m['utc_date'])}Z → "
                 f"{_when(m['new_utc'])}Z")
    for m in r["scores"]:
        L.append(f"    scores: {_row(m)}")
    return L


def summary(r: dict) -> dict:
    return {"listing": r["listing"], "stored": r["stored"], "changes": len(r["changes"]),
            "listed_absent_both_scores": r["classes"][ABSENT], "listed_none_text_both_scores": r["classes"][NONE_TEXT],
            "already": len(r["already"]), "not_stored": len(r["not_stored"]), "sched_both_scores": r["sched_both"],
            "left": len(r["left"]),
            "also_status": len(r["other_status"]), "also_kickoff": len(r["kickoff"]), "also_scores": len(r["scores"])}


def missing_db() -> str | None:
    """The configured SQLite file's path when it does not exist, else None. The app's engine creates what is missing on
    its first connection (src/db/database.py: the directory, then a new WAL file), so a dry run checks first: it never
    creates a database (law 5). A non-SQLite URL has no file to check."""
    from pathlib import Path

    from src.db.database import get_engine

    url = get_engine().url
    if url.get_backend_name() != "sqlite":
        return None
    db = url.database
    path = Path(db).resolve() if db and db != ":memory:" else None
    return None if path is not None and path.is_file() else str(path or ":memory:")


def run(competitions, seasons, adapter_for: Callable, out: Callable[[str], None] = print) -> int:
    """The dry run over `competitions` (each of COMPETITIONS) and `seasons` (stored season strings; none = every season
    the DB stores for the competition). `adapter_for(code)` gives the competition's adapter. One /games call per
    competition-season. Writes nothing. Exit 2 when there is no database file (nothing opened, nothing read); 1 when a
    listing could not be read (that competition-season is named, the others still run); else 0."""
    gone = missing_db()
    if gone:
        out(f"✗ no database at {gone}; the dry run never creates one (law 5) · nothing read")
        return 2
    out("SCORE-PRESENCE DRY RUN (#493; ARCHITECT 2026-10-16 addendum 81 item 3, 2026-10-17 addendum 112 item 4) · "
        "READ-ONLY, writes nothing · the rule: a provider status that is ABSENT with both scores present is FINISHED; "
        "a status the provider stated keeps its mapping (an unknown code SCHEDULED); the text 'None' is a stated "
        "status")
    totals, failed = {}, []
    for code in competitions:
        code = code.upper()
        have = stored_seasons(code)
        if have is None:
            out(f"{code}: not in the DB · nothing stored, nothing to change")
            continue
        todo = list(seasons) or have
        if not todo:
            out(f"{code}: no stored season · nothing to change")
            continue
        adapter = adapter_for(code)
        source = adapter.source_name
        for season in todo:
            try:
                listing, shorts = read_listing(adapter, code, season)
            except Exception as e:                          # one listing that cannot be read never stops the others
                failed.append(f"{code} {season}")
                out(f"✗ {code} {season}: the listing could not be read ({type(e).__name__}: {e}) · nothing compared")
                continue
            r = compare(listing, shorts, stored_rows(code, season, source))
            for ln in lines(code, season, source, r):
                out(ln)
            totals[f"{code} {season}"] = summary(r)
    out("SCORE-PRESENCE-DRY-RUN " + json.dumps({"changes_total": sum(v["changes"] for v in totals.values()),
                                               "by_competition_season": totals, "unread": failed,
                                               "written": 0}, sort_keys=True))
    return 1 if failed else 0
