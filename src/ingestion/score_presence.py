"""
SCORE-PRESENCE (#493): the read-only DRY RUN, and the status-only APPLY of the rows it lists.

The rulings, verbatim:
  * ARCHITECT 2026-10-16, addendum 81 item 3: "Code's PR fixes the ordering, prints a --dry-run listing of every row
    the rule would change (count per competition-season, and the ids), and the operator's block runs it after the
    backup; the receipt is pasted on the PR before merge."
  * ARCHITECT 2026-10-17, addendum 116 item 4 (1): "Apply vehicle: NO whole-season sync. A status-only apply is built:
    `score-presence-apply --competition --season --match-ids` sets status (and nothing else — never utc_date, never
    scores) on the rows the dry run listed, backup first, in a laptop block on my word. The fingerprint is untouched
    by construction; the PR proves it with the fingerprint printed before and after on the test DB."
  * (2): "NFL 2024: the dry run prints each row's stage. Preseason rows are applied with the rest. Regular-season rows
    are NOT applied by this PR: they change nfl_elo_v1's ratings and need a gate verdict (CLAUDE.md); they get their
    own Issue with the list and wait for the NFL re-declaration lane. The dry run names which of the 16 fall where."
  * (3) and (4), the kickoff-age condition and the text "None": src/adapters/api_sports_status.py.

HOW (law 1: read from the code):
  * The rule is the adapters' own parse (api_sports_status.game_status, read by both _parse_games). read_listing makes
    the single /games call a season read makes (no date), parses it with the adapter's _parse_games at one `now`, and
    keeps each game's provider status as sent (raw_shorts). The dry run and the apply read it the same way.
  * resolve: each listed game resolved to the stored row the sync would write AS THE SYNC RESOLVES IT, with the sync's
    own pieces: the cache over the competition's rows (IngestionService._match_cache), its two teams by provider id (a
    team not stored: the sync skips the game), the row holding its provider id, and for a re-keyed source
    (api_american_football: NFL, NCAA) the sync's own _rekey_candidate (the row's `_prev` history, the same pair
    within 12 hours, the NCAA placeholder window; a refusal creates nothing). It runs on rows detached from the session.
  * compare: THE RULE'S CHANGE SET is every listed game with NO status (none sent, or the text "None": the same as
    absent) and both totals, resolved to a stored row whose status differs from the rule's (FINISHED, once now >=
    the age clock: api_sports_status.age_until, the same helper the parse reads) AND whose stored scores are both
    present and equal the listing's totals. Before the age clock the rule leaves the stored status alone: listed, never
    changed. A row the rule reads FINISHED whose stored scores are missing or differ is NEEDS SCORES, not a change: a
    status-only write cannot complete it (item 4 (1): never scores; addendum 112 item 4: no score, not FINISHED); held
    for the architect, the apply refuses it. The text "None" rows are listed in their own section, for the record.
  * NFL (nfl_elo_v1's competition, nfl_backtest.NFL_COMPETITION_CODE): each change is classed by nfl_elo_v1's own
    preseason test (nfl_predict.is_preseason) on the STORED stage, the one its walk reads (the apply writes no stage):
    PRESEASON_APPLIED, or NOT_PRESEASON_HELD (regular season and postseason: every row the walk reads; they change
    nfl_elo_v1's ratings; the apply refuses them). The hold lives in the apply only: a whole-season sync applies the
    adapters' rule to every row it parses (the ledger entry, "For the architect").
  * HELD off the APPLY line (#493 review): a NOT_PRESEASON_HELD change; a change whose row the sync re-keys (a
    status-only write cannot carry the re-key; after it the NCAA placeholder window, SCHEDULED rows only, no longer
    finds the row and the next sync creates a twin); the apply refuses both. A text "None" change is off the APPLY
    line on its own line (item 4 (4) expects none: the architect's word whether it is applied); the apply accepts it
    when it is named.
  * apply: the same read, resolution and rule at its own `now`. It refuses AS A WHOLE (nothing written) when a named id
    is not in the change set for that competition-season (NEEDS SCORES included), is an NFL row not preseason, or is
    re-keyed; then writes Match.status alone, one UPDATE per row restricted to the status column and guarded by the
    status the read saw. For NCAA it prints ncaa-elo-v2's stream and training fingerprints before and after
    (ncaa_fingerprints): neither reads a status (ncaa_v1r_gate.FINGERPRINT_FIELDS; load_v1r_games: "whatever our local
    status or scores").
  * The dry run also reconciles the stored SCHEDULED rows carrying both scores (addendum 81's NCAA 2024 120 and NFL
    2024 16): the rule changes X of them and leaves Y, X + Y = N. And it says, for information only, what a
    whole-season sync would write besides: it is NOT the vehicle (addendum 116 item 4 (1)).
Scores are never printed (the NCAA fences print no outcome); ids, kickoffs, stages and statuses are.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Callable

COMPETITIONS = ("NFL", "NCAA", "NHL")       # the competitions of the two adapters that carry the rule
NO_STATUS, NONE_TEXT = "no status sent", "text 'None'"
PRESEASON_APPLIED = "preseason (applied with the rest)"
NOT_PRESEASON_HELD = ("not preseason (held: regular season or postseason, nfl_elo_v1's walk reads it; needs a gate "
                      "verdict; own Issue)")
#: Why a change is held off the APPLY line and refused by the apply (holds); the receipt's HELD lines and the refusal.
HELD_NFL_WHY = ("NFL not preseason, regular season and postseason: the rows nfl_elo_v1's walk reads (nfl_predict."
                "is_preseason false); they change its ratings and need a gate verdict (addendum 116 item 4 (2)); their "
                "own Issue, the NFL re-declaration lane")
HELD_REKEY_WHY = ("re-keyed: the sync answers this game under a new provider id; a status-only write cannot carry the "
                  "re-key (the row keeps its old provider id and kickoff), and where the sync matched it through the "
                  "NCAA placeholder window (SCHEDULED rows only) the next sync no longer finds it once FINISHED and "
                  "creates a twin; for the architect")
NEEDS_SCORES_WHY = ("the rule reads FINISHED, but the stored scores are {what}: a status-only write cannot complete "
                    "the row (addendum 116 item 4 (1): never scores; addendum 112 item 4: no score, not FINISHED); held "
                    "for the architect")


def fix_class(short: str | None, home_total, away_total) -> str | None:
    """Pure. The rule's class of a listed game: NO_STATUS (no status sent) or NONE_TEXT (the provider's text "None",
    the same as absent: addendum 116 item 4 (4)), both with their two totals; None when the rule does not read it as
    no status with both scores (a total missing, or a stated status)."""
    from src.adapters.api_sports_status import NONE_TEXT as TEXT

    if home_total is None or away_total is None:
        return None
    if short is None:
        return NO_STATUS
    return NONE_TEXT if short == TEXT else None


def nfl_class(competition_code: str, stage: str | None) -> str | None:
    """Addendum 116 item 4 (2), NFL rows only (nfl_elo_v1's competition): PRESEASON_APPLIED when nfl_elo_v1's own
    preseason test (nfl_predict.is_preseason) reads the stored `stage` as preseason, else NOT_PRESEASON_HELD (regular
    season AND postseason: every stage its walk reads). None for any other competition."""
    from src.walters.nfl_backtest import NFL_COMPETITION_CODE
    from src.walters.nfl_predict import is_preseason

    if competition_code != NFL_COMPETITION_CODE:
        return None
    return PRESEASON_APPLIED if is_preseason(stage) else NOT_PRESEASON_HELD


def read_listing(adapter, competition_code: str, season: str, now=None) -> tuple[list, dict]:
    """(the adapter's NormalizedMatch rows, {provider id: provider short or None}) for one season: the single /games
    call list_matches makes for a season read without a date, parsed by the adapter's own _parse_games at `now` (the
    rule's clock; None = utc now)."""
    from src.adapters.api_american_football import _league_for
    from src.adapters.api_hockey import NHL_LEAGUE_ID, APIHockeyAdapter

    year = int(str(season).split("/")[0])
    shorts: dict = {}
    if isinstance(adapter, APIHockeyAdapter):
        data = adapter._get("games", params={"league": NHL_LEAGUE_ID, "season": year})
        return adapter._parse_games(data, str(year), raw_shorts=shorts, now=now), shorts
    data = adapter._get("games", params={"league": _league_for(competition_code), "season": year})
    return adapter._parse_games(data, competition_code, str(year), raw_shorts=shorts, now=now), shorts


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


def _snap(m, source: str) -> dict:
    """One stored row as the receipt reads it, before anything: {id, pid (its `source` id or None), season, utc_date,
    stage, matchday, status (the enum's name), status_raw, home_score, away_score}."""
    sid = (m.external_ids or {}).get(source)
    return {"id": m.id, "pid": None if sid is None else str(sid), "season": m.season, "utc_date": m.utc_date,
            "stage": m.stage, "matchday": m.matchday, "status": getattr(m.status, "name", str(m.status)),
            "status_raw": m.status_raw, "home_score": m.home_score, "away_score": m.away_score}


def resolve(competition_code: str, season: str, source: str, listing: list) -> tuple[list[dict], dict]:
    """Read-only. (the competition-season's stored rows, {listed provider id: what the sync does with that game}).

    Each listed game is resolved as IngestionService.sync_matches resolves it, in the listing's order, with the sync's
    own pieces: the cache over every stored row of the competition (_match_cache), the two teams (_find_team_by_source),
    the row holding the game's provider id, and on a miss for a re-keyed source _rekey_candidate, with _upsert_match's
    bookkeeping (a re-keyed row answers to its new id; a created game holds its id and its pair). The answer per game:
    {"row": the stored row it writes (_snap, before), "rekey": "old → new" or None}, or {"row": None, "fate":
    "created" | "refused" | "skipped", "why": ...}.

    Writes nothing: the rows are detached from the session before the walk, so what the walk sets on them (the sync's
    own _apply_match_updates and re-key, which the next game's re-key reads, as in the sync) is never flushed; the
    session is rolled back."""
    from types import SimpleNamespace

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match
    from src.ingestion.service import IngestionService as IS
    from src.ingestion.service import created_status

    out: dict = {}
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
        stored = list(s.execute(select(Match).where(Match.competition_id == comp.id)).scalars()) if comp else []
        before = {m.id: _snap(m, source) for m in stored}
        cache = IS._match_cache(stored, listing, competition_code)
        s.expunge_all()                                     # detached: nothing the walk sets on a row is flushed
        pairs = cache.get("__pairs__")
        for nm in listing:
            pid = str(nm.source_id)
            home = IS._find_team_by_source(s, nm.sport, nm.source, nm.home_team_source_id)
            away = IS._find_team_by_source(s, nm.sport, nm.source, nm.away_team_source_id)
            if not home or not away:
                out[pid] = {"row": None, "fate": "skipped", "why": "a team is not stored"}
                continue
            m, rekey = cache.get(nm.source_id), None
            if m is None and pairs is not None:
                m, refused = IS._rekey_candidate(nm, home.id, away.id, cache)
                if refused:
                    out[pid] = {"row": None, "fate": "refused", "why": refused}
                    continue
                if m is not None:                           # the sync's re-key: the row answers to the new id
                    old = (m.external_ids or {}).get(nm.source)
                    m.external_ids = {**(m.external_ids or {}), nm.source: nm.source_id}
                    cache[nm.source_id] = m
                    if old:
                        cache.pop(old, None)
                    rekey = f"{old or '—'} → {pid}"
            if m is None:                                   # a new game: the sync creates it
                made = SimpleNamespace(id=None, utc_date=nm.utc_date, status=created_status(nm),
                                       external_ids={nm.source: nm.source_id})
                if nm.source_id:
                    cache[nm.source_id] = made
                if pairs is not None:
                    pairs.setdefault((home.id, away.id), []).append(made)
            if m is None or m.id is None:                   # (or a game this listing already created)
                out[pid] = {"row": None, "fate": "created"}
                continue
            out[pid] = {"row": before[m.id], "rekey": rekey}
            IS._apply_match_updates(m, nm)                  # on the detached row, as the sync writes it
        s.rollback()
    rows = sorted((x for x in before.values() if x["season"] == season),
                  key=lambda x: (x["utc_date"] is None, x["utc_date"] or 0, x["id"]))
    return rows, out


def clock_start(moved: str | None) -> str:
    """Where the age clock starts, as the receipt names it (api_sports_status.age_start's why: None = the kickoff)."""
    from src.adapters.api_sports_status import CLOCK_DATE_ONLY, CLOCK_PLACEHOLDER
    from src.ingestion.placeholder import PLACEHOLDER_RESOLVE_H

    return {None: "kickoff",
            CLOCK_PLACEHOLDER: f"kickoff + {PLACEHOLDER_RESOLVE_H}h (the end of the TBD placeholder's game day)",
            CLOCK_DATE_ONLY: "the end of the kickoff's UTC date (no kickoff time sent)"}[moved]


def age(nm, key: str, h: int) -> tuple:
    """(the age clock's end for a listed game, why its start moved or None, the receipt's text): the rule's own helper
    (api_sports_status.age_start, the one game_status reads through age_until), so the receipt says what the parse did.
    The text: "kickoff + 5h = <when>Z", its start named when the clock moved."""
    from src.adapters.api_sports_status import age_start

    start, moved = age_start(nm.utc_date, key, getattr(nm, "kickoff_date_only", False))
    until = start + timedelta(hours=h) if start is not None else None
    return until, moved, f"{clock_start(moved)} + {h}h = {_when(until)}Z"


def compare(competition_code: str, listing: list, shorts: dict, rows: list[dict], resolved: dict) -> dict:
    """Pure. One competition-season: the rule's parse (`listing`, `shorts`), each listed game resolved to what the
    sync does with it (`resolved`, from resolve), against the season's stored `rows`. r["changes"] is the rule's
    change set: the rows a status-only write completes (each entry: the stored row, its class, the new status, the
    age clock, its NFL class or None). r["needs_scores"]: the rows the rule reads FINISHED whose stored scores are
    missing or differ from the listing's totals (not changes: held). r["why_row"] says, for every stored row a listed
    game resolves to that is not a change, why not."""
    from src.adapters.api_sports_status import CLOCK_DATE_ONLY, CLOCK_PLACEHOLDER, LONGEST_GAME_H, no_status, sport_key
    from src.ingestion.service import created_status

    key = sport_key(competition_code, listing[0].sport if listing else None)
    h = LONGEST_GAME_H[key]
    r = {"code": competition_code, "hours": h, "listing": len(listing), "stored": len(rows), "changes": [],
         "needs_scores": [], "already": [], "not_yet": [], "not_stored": [], "other_status": [], "kickoff": [],
         "scores": [], "fields": [], "rekeyed": [], "created": [], "refused": [], "skipped": [], "onto_stored": 0,
         "left": [], "sched_both": 0, "sched_both_changed": 0, "classes": {NO_STATUS: 0, NONE_TEXT: 0},
         "clock_moved": {CLOCK_PLACEHOLDER: 0, CLOCK_DATE_ONLY: 0}, "why_row": {}}
    listed, by_row = {}, {}
    for nm in listing:
        pid = str(nm.source_id)
        short = shorts.get(pid)
        cls = fix_class(short, nm.home_score, nm.away_score)
        new = None if nm.status is None else nm.status.name
        until, moved, clock = age(nm, key, h)
        listed[pid] = (nm, short, cls)
        if cls:
            r["classes"][cls] += 1
            if moved:
                r["clock_moved"][moved] += 1
        got = resolved[pid]
        if got["row"] is None:                              # no stored row: the sync creates, refuses or skips it
            g = {"pid": pid, "class": cls, "utc_date": nm.utc_date, "new": created_status(nm).name,
                 "fate": got["fate"], "why": got.get("why"), "moved": moved}
            if cls:
                r["not_stored"].append(g)
            r[got["fate"]].append(g)
            continue
        m = {**got["row"], "rekey": got["rekey"]}
        r["onto_stored"] += 1
        by_row[m["id"]] = pid
        if m["rekey"]:
            r["rekeyed"].append(m)
        if cls:
            e = {**m, "class": cls, "new": new, "until": until, "moved": moved, "clock": clock,
                 "nfl": nfl_class(competition_code, m["stage"])}
            if new is None:
                r["not_yet"].append(e)
                r["why_row"][m["id"]] = f"the rule leaves it alone ({cls}, both scores, but {clock} is after now)"
            elif m["status"] == new:
                r["already"].append(e)
                r["why_row"][m["id"]] = f"already {new} as the rule reads ({cls})"
            elif m["home_score"] is None or m["away_score"] is None:
                e["scores_are"] = "missing"
                r["needs_scores"].append(e)
                r["why_row"][m["id"]] = NEEDS_SCORES_WHY.format(what="missing")
            elif (m["home_score"], m["away_score"]) != (nm.home_score, nm.away_score):
                e["scores_are"] = "different from the listing's totals"
                r["needs_scores"].append(e)
                r["why_row"][m["id"]] = NEEDS_SCORES_WHY.format(what="different from the listing's totals")
            else:                                           # both stored scores present and the listing's: a change
                r["changes"].append(e)
        else:
            r["why_row"][m["id"]] = (
                f"not the rule's: the provider states {short!r}" if not no_status(short) else
                "not the rule's: no status and a score missing in the listing (SCHEDULED: no score, not FINISHED)")
            if new is not None and m["status"] != new:
                r["other_status"].append({**m, "new": new, "short": short})
        if m["utc_date"] != nm.utc_date:
            r["kickoff"].append({**m, "new_utc": nm.utc_date})
        if ((nm.home_score is not None and nm.home_score != m["home_score"])
                or (nm.away_score is not None and nm.away_score != m["away_score"])):
            r["scores"].append(m)
        what = []                                           # _apply_match_updates' other fields, its own `or`s
        if nm.season and nm.season != m["season"]:
            what.append(f"season {m['season'] or '—'} → {nm.season}")
        if (nm.stage or m["stage"]) != m["stage"]:
            what.append(f"stage {m['stage'] or '—'} → {nm.stage}")
        if (nm.matchday or m["matchday"]) != m["matchday"]:
            what.append(f"matchday {m['matchday'] if m['matchday'] is not None else '—'} → {nm.matchday}")
        if nm.status_raw and nm.status_raw != m["status_raw"]:
            what.append(f"status code {m['status_raw'] or '—'} → {nm.status_raw}")
        if what:
            r["fields"].append({**m, "what": " · ".join(what)})
    change_ids = {m["id"] for m in r["changes"]}
    needs_ids = {m["id"] for m in r["needs_scores"]}
    for m in rows:                                          # the stored SCHEDULED rows carrying both scores
        if m["status"] != "SCHEDULED" or m["home_score"] is None or m["away_score"] is None:
            continue
        r["sched_both"] += 1
        pid = by_row.get(m["id"])
        if pid is None:                                     # no listed game resolves to it
            got = resolved.get(m["pid"]) if m["pid"] is not None else None
            if got is None:
                why = "not in the listing (the rule does not touch it)"
            elif got["row"] is not None:
                why = (f"its provider id is listed, but the sync resolves that game to match {got['row']['id']} (the "
                       f"rule does not touch this row)")
            else:
                why = (f"listed, but {_fate({**got, 'new': created_status(listed[m['pid']][0]).name})} (the rule "
                       f"does not touch this row)")
            r["left"].append({**m, "rekey": None, "why": why})
            continue
        nm, short, cls = listed[pid]
        new = None if nm.status is None else nm.status.name
        if m["id"] in change_ids:
            r["sched_both_changed"] += 1
            continue                                        # the rule changes it (listed above)
        if m["id"] in needs_ids:
            why = (f"NEEDS SCORES (held): {r['why_row'][m['id']]}")
        elif cls and new is None:
            why = (f"no status ({cls}) and both scores in the listing, but {age(nm, key, h)[2]} is after now: the "
                   f"stored status is left alone")
        elif no_status(short):
            why = ("no status (none sent, or the text 'None') and a score missing in the listing: stays SCHEDULED (no "
                   "score, not FINISHED)")
        else:
            why = f"the provider states {short!r} (a sync would write {new}; not the rule's)"
        r["left"].append({**m, "rekey": resolved[pid]["rekey"], "why": why})
    for k in ("changes", "needs_scores", "already", "not_yet", "other_status", "kickoff", "scores", "fields",
              "rekeyed"):
        r[k].sort(key=lambda x: (x["utc_date"] is None, x["utc_date"] or 0, x["id"]))
    return r


def holds(m: dict) -> list[str]:
    """Why the apply refuses a change, each with its own HELD line: HELD_NFL_WHY (an NFL row not preseason, item 4
    (2)), HELD_REKEY_WHY (a row the sync re-keys: any re-key, the placeholder window, the 12-hour pair or the row's
    `_prev` history). Empty: the apply accepts it."""
    return ([HELD_NFL_WHY] if m.get("nfl") == NOT_PRESEASON_HELD else []) + ([HELD_REKEY_WHY] if m.get("rekey") else [])


def apply_ids(r: dict) -> list[int]:
    """The APPLY line's ids, ascending: the changes with no hold, but a text "None" change (none_text_ids)."""
    return sorted(m["id"] for m in r["changes"] if not holds(m) and m["class"] != NONE_TEXT)


def none_text_ids(r: dict) -> list[int]:
    """The text "None" changes with no hold, ascending: off the APPLY line, on their own (addendum 116 item 4 (4)
    expects none; the architect's word whether they are applied). The apply accepts them when they are named."""
    return sorted(m["id"] for m in r["changes"] if not holds(m) and m["class"] == NONE_TEXT)


def held_ids(r: dict) -> list[int]:
    """The changes that are NFL rows not preseason (addendum 116 item 4 (2): held, their own Issue), ascending."""
    return sorted(m["id"] for m in r["changes"] if m["nfl"] == NOT_PRESEASON_HELD)


def rekey_held_ids(r: dict) -> list[int]:
    """The changes whose row the sync re-keys (held: a status-only write cannot carry the re-key), ascending."""
    return sorted(m["id"] for m in r["changes"] if m.get("rekey"))


def needs_scores_ids(r: dict) -> list[int]:
    """The rows the rule reads FINISHED whose stored scores are missing or differ (NEEDS SCORES, held), ascending."""
    return sorted(m["id"] for m in r["needs_scores"])


def _when(d) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S") if d is not None else "no kickoff"


def _pid(m) -> str:
    return f"{m['rekey']} (re-keyed)" if m.get("rekey") else (m["pid"] or "—")


def _row(m) -> str:
    return f"match {m['id']} · provider {_pid(m)} · {_when(m['utc_date'])}Z · {m['stage'] or 'no stage'}"


def _nfl(m) -> str:
    return f" · {m['nfl']}" if m.get("nfl") else ""


def _moved(m) -> str:
    return f" · age clock from {clock_start(m['moved'])}" if m.get("moved") else ""


def _fate(g) -> str:
    if g["fate"] == "created":
        return f"the sync creates it {g['new']}"
    if g["fate"] == "refused":
        return f"the sync refuses it, creating nothing: {g['why']}"
    return f"the sync skips it: {g['why']}"


def header(title: str, what: str, now) -> list[str]:
    """The receipt's first lines (the dry run's and the apply's): the rulings, the rule, the constants and `now`."""
    from src.adapters.api_sports_status import longest_game_text
    from src.ingestion.placeholder import PLACEHOLDER_RESOLVE_H

    return [f"{title} (#493; ARCHITECT 2026-10-16 addendum 81 item 3, 2026-10-17 addendum 112 item 4 and addendum 116 "
            f"item 4) · {what}",
            "  the rule: no provider status (none sent, or the text 'None') with both scores is FINISHED once now >= "
            "kickoff + the sport's longest game, and before that the stored status is left alone; no status with a "
            "score missing is SCHEDULED; a status the provider stated keeps its mapping (an unknown code SCHEDULED)",
            f"  longest game (addendum 116 item 4 (3)): {longest_game_text()} · now {_when(now)}Z",
            f"  the age clock (api_sports_status.age_until, the rule's and this receipt's): from the kickoff; an NCAA "
            f"kickoff at the provider's TBD placeholder (04:00:00Z) from the end of its game day (kickoff + "
            f"{PLACEHOLDER_RESOLVE_H}h, src/ingestion/placeholder.py); a kickoff sent as a date with no time from the "
            f"end of that UTC date; a row whose clock moved says so"]


def lines(code: str, season: str, source: str, r: dict) -> list[str]:
    """One competition-season's dry-run receipt, every row whole (#491: a receipt cuts nothing)."""
    from src.adapters.api_sports_status import CLOCK_DATE_ONLY, CLOCK_PLACEHOLDER

    h = r["hours"]

    def of(k, cls):
        return [x for x in r[k] if x["class"] == cls]

    def ids(xs):
        return ",".join(map(str, xs))

    also_created = [g for g in r["created"] if not g["class"]]      # the rule's own are under "not stored"
    L = [f"{code} {season} · source {source} · listing {r['listing']} games · stored {r['stored']} rows",
         f"  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row "
         f"{r['onto_stored']} (re-keyed {len(r['rekeyed'])}) · creates {len(r['created'])} · refuses "
         f"{len(r['refused'])} · skips {len(r['skipped'])} (a team not stored)",
         f"  THE RULE CHANGES {len(r['changes'])} stored row(s) of {code} {season} (status only, score-presence-apply):"
         f" no status sent {len(of('changes', NO_STATUS))} · the text 'None' {len(of('changes', NONE_TEXT))}",
         f"  NO STATUS SENT, both scores: listed {r['classes'][NO_STATUS]} · changes {len(of('changes', NO_STATUS))} "
         f"· needs scores {len(of('needs_scores', NO_STATUS))} · already as the rule reads "
         f"{len(of('already', NO_STATUS))} · left alone until the age clock (kickoff + {h}h) "
         f"{len(of('not_yet', NO_STATUS))} · not stored {len(of('not_stored', NO_STATUS))}"]
    for m in of("changes", NO_STATUS):
        L.append(f"    {_row(m)} · {m['class']} · {m['status']} → {m['new']}{_nfl(m)}{_moved(m)}")
    for m in of("already", NO_STATUS):
        L.append(f"    already: {_row(m)} · {m['class']} · {m['status']}{_moved(m)}")
    for m in of("not_yet", NO_STATUS):
        L.append(f"    left alone: {_row(m)} · {m['class']} · stored {m['status']} kept ({m['clock']} is after now)")
    for g in of("not_stored", NO_STATUS):
        L.append(f"    not stored: provider {g['pid']} · {_when(g['utc_date'])}Z · {g['class']} · {_fate(g)}"
                 f"{_moved(g)}")
    L.append(f"  THE TEXT 'None', both scores (no status, the same as absent: addendum 116 item 4 (4); for the "
             f"record): listed {r['classes'][NONE_TEXT]} · stored as the rule reads, nothing flips "
             f"{len(of('already', NONE_TEXT))} · changes {len(of('changes', NONE_TEXT))} · needs scores "
             f"{len(of('needs_scores', NONE_TEXT))} · left alone until the age clock (kickoff + {h}h) "
             f"{len(of('not_yet', NONE_TEXT))} · not stored {len(of('not_stored', NONE_TEXT))}")
    for m in of("already", NONE_TEXT):
        L.append(f"    {_row(m)} · stored {m['status']} → {m['new']} (unchanged){_moved(m)}")
    for m in of("changes", NONE_TEXT):
        L.append(f"    {_row(m)} · stored {m['status']} → {m['new']} (a change{_nfl(m)}){_moved(m)}")
    for m in of("not_yet", NONE_TEXT):
        L.append(f"    left alone: {_row(m)} · stored {m['status']} kept ({m['clock']} is after now)")
    for g in of("not_stored", NONE_TEXT):
        L.append(f"    not stored: provider {g['pid']} · {_when(g['utc_date'])}Z · {_fate(g)}{_moved(g)}")
    need = needs_scores_ids(r)
    L.append(f"  NEEDS SCORES (held for the architect: the rule reads FINISHED, but the stored scores are missing or "
             f"differ from the listing's totals; a status-only write cannot complete the row, addendum 116 item 4 (1) "
             f"and addendum 112 item 4; not on the APPLY line, score-presence-apply refuses them; scores not printed): "
             f"{len(need)}" + (f" · match ids {ids(need)}" if need else ""))
    for m in r["needs_scores"]:
        L.append(f"    {_row(m)} · {m['class']} · stored {m['status']} → {m['new']} · stored scores "
                 f"{m['scores_are']}{_nfl(m)}{_moved(m)}")
    L.append(f"  AGE CLOCK MOVED (listed games of the rule's class counted from later than the kickoff sent, each row "
             f"says so): the NCAA TBD placeholder {r['clock_moved'][CLOCK_PLACEHOLDER]} · a date with no time "
             f"{r['clock_moved'][CLOCK_DATE_ONLY]}")
    if code == "NFL":                                       # nfl_class: nfl_elo_v1's competition only
        L.append(f"  NFL STAGE (nfl_elo_v1's preseason test, nfl_predict.is_preseason, on the stored stage; the apply "
                 f"writes no stage): of the rule's {len(r['changes'])} change(s), {PRESEASON_APPLIED} "
                 f"{len([1 for m in r['changes'] if m['nfl'] == PRESEASON_APPLIED])} · {NOT_PRESEASON_HELD} "
                 f"{len(held_ids(r))}")
    L.append(f"  stored SCHEDULED with both scores: {r['sched_both']} · the rule changes {r['sched_both_changed']} · "
             f"the rule leaves {len(r['left'])}")
    for m in r["left"]:
        L.append(f"    left: {_row(m)} · {m['why']}")
    ok, held, rekeyed, text = apply_ids(r), held_ids(r), rekey_held_ids(r), none_text_ids(r)
    if ok:
        L.append(f"  APPLY (status only; on the architect's word, after a fresh .backup): python cli.py "
                 f"score-presence-apply --competition {code} --season {season} --match-ids {ids(ok)} --backup <PATH>")
    else:
        L.append(f"  APPLY: nothing to apply for {code} {season}")
    if held:
        L.append(f"  HELD ({HELD_NFL_WHY}): match ids {ids(held)}")
    if rekeyed:
        L.append(f"  HELD ({HELD_REKEY_WHY}): match ids {ids(rekeyed)}")
    if text:
        L.append(f"  THE TEXT 'None' CHANGES (not on the APPLY line: addendum 116 item 4 (4) expects none; the "
                 f"architect's word whether these ids are applied; score-presence-apply accepts them when named): "
                 f"match ids {ids(text)}")
    L.append(f"  A WHOLE-SEASON SYNC WOULD ALSO WRITE (information only: it is not the vehicle, addendum 116 item 4 "
             f"(1); score-presence-apply writes status alone): status {len(r['other_status'])} · kickoff "
             f"{len(r['kickoff'])} · scores {len(r['scores'])} (values not printed) · stage, matchday, season, status "
             f"code {len(r['fields'])} · provider id (re-key) {len(r['rekeyed'])} · listed games it creates "
             f"{len(also_created)}")
    for m in r["other_status"]:
        said = "no status stated" if m["short"] is None else f"the provider states {m['short']!r}"
        L.append(f"    status: {_row(m)} · {m['status']} → {m['new']} ({said})")
    for m in r["kickoff"]:
        L.append(f"    kickoff: match {m['id']} · provider {_pid(m)} · {_when(m['utc_date'])}Z → "
                 f"{_when(m['new_utc'])}Z")
    for m in r["scores"]:
        L.append(f"    scores: {_row(m)}")
    for m in r["fields"]:
        L.append(f"    fields: {_row(m)} · {m['what']}")
    for m in r["rekeyed"]:
        L.append(f"    re-key: {_row(m)}")
    for g in also_created:
        L.append(f"    creates: provider {g['pid']} · {_when(g['utc_date'])}Z · {g['new']}")
    L.append(f"  A WHOLE-SEASON SYNC WOULD WRITE NOTHING FOR: refused {len(r['refused'])} · skipped "
             f"{len(r['skipped'])} (a team not stored)")
    for g in r["refused"]:
        L.append(f"    refused: provider {g['pid']} · {_when(g['utc_date'])}Z · {g['why']}")
    if r["skipped"]:
        L.append(f"    skipped (a team not stored): provider {', '.join(g['pid'] for g in r['skipped'])}")
    return L


def summary(r: dict) -> dict:
    def n(k, cls):
        return len([1 for x in r[k] if x["class"] == cls])

    return {"listing": r["listing"], "stored": r["stored"], "changes": len(r["changes"]),
            "changes_no_status": n("changes", NO_STATUS), "changes_none_text": n("changes", NONE_TEXT),
            "listed_no_status_both_scores": r["classes"][NO_STATUS],
            "listed_none_text_both_scores": r["classes"][NONE_TEXT],
            "already": n("already", NO_STATUS), "none_text_unchanged": n("already", NONE_TEXT),
            "left_alone_until_kickoff_age": len(r["not_yet"]), "not_stored": len(r["not_stored"]),
            "sched_both_scores": r["sched_both"], "sched_both_changed": r["sched_both_changed"], "left": len(r["left"]),
            "needs_scores": len(r["needs_scores"]), "needs_scores_ids": needs_scores_ids(r),
            "apply_ids": apply_ids(r), "held_nfl_not_preseason_ids": held_ids(r), "held_rekeyed_ids": rekey_held_ids(r),
            "none_text_change_ids": none_text_ids(r), "clock_moved": dict(r["clock_moved"]),
            "onto_stored": r["onto_stored"], "rekeyed": len(r["rekeyed"]), "created": len(r["created"]),
            "refused": len(r["refused"]), "skipped": len(r["skipped"]),
            "also_status": len(r["other_status"]), "also_kickoff": len(r["kickoff"]), "also_scores": len(r["scores"]),
            "also_fields": len(r["fields"]),
            "also_created": len([1 for g in r["created"] if not g["class"]])}


def missing_db() -> str | None:
    """The configured SQLite file's path when it does not exist, else None. The app's engine creates what is missing on
    its first connection (src/db/database.py: the directory, then a new WAL file), so the dry run and the apply check
    first: neither ever creates a database (law 5; the shared guard's check, src/db/migrate_guard.py). A non-SQLite URL
    has no file to check."""
    from pathlib import Path

    from src.db.database import get_engine

    url = get_engine().url
    if url.get_backend_name() != "sqlite":
        return None
    db = url.database
    path = Path(db).resolve() if db and db != ":memory:" else None
    return None if path is not None and path.is_file() else str(path or ":memory:")


def run(competitions, seasons, adapter_for: Callable, out: Callable[[str], None] = print, now=None) -> int:
    """The dry run over `competitions` (each of COMPETITIONS) and `seasons` (stored season strings; none = every season
    the DB stores for the competition). `adapter_for(code)` gives the competition's adapter; `now` is the rule's clock
    (None = utc now, read once). One /games call per competition-season. Writes nothing. Exit 2 when there is no
    database file (nothing opened, nothing read); 1 when a listing could not be read (that competition-season is named,
    the others still run); else 0."""
    from src.adapters.api_sports_status import LONGEST_GAME_H, rule_now

    gone = missing_db()
    if gone:
        out(f"✗ no database at {gone}; the dry run never creates one (law 5) · nothing read")
        return 2
    now = rule_now(now)
    for ln in header("SCORE-PRESENCE DRY RUN", "READ-ONLY, writes nothing", now):
        out(ln)
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
                listing, shorts = read_listing(adapter, code, season, now)
            except Exception as e:                          # one listing that cannot be read never stops the others
                failed.append(f"{code} {season}")
                out(f"✗ {code} {season}: the listing could not be read ({type(e).__name__}: {e}) · nothing compared")
                continue
            r = compare(code, listing, shorts, *resolve(code, season, source, listing))
            for ln in lines(code, season, source, r):
                out(ln)
            totals[f"{code} {season}"] = summary(r)
    out("SCORE-PRESENCE-DRY-RUN " + json.dumps({"changes_total": sum(v["changes"] for v in totals.values()),
                                               "by_competition_season": totals, "unread": failed,
                                               "now": _when(now) + "Z", "longest_game_h": LONGEST_GAME_H,
                                               "written": 0}, sort_keys=True))
    return 1 if failed else 0


# ------------------------------------------------------------------------------------------------- the apply --

class StatusMoved(RuntimeError):
    """A row's stored status is no longer the one the change set read: the whole write is rolled back."""


def ncaa_fingerprints() -> dict:
    """ncaa-elo-v2's two fingerprints, by its own functions (src/walters/ncaa_v1r_gate.py) over its own read
    (load_streams(V2): one read of the stored games, both streams): "stream" = stream_fingerprint over the D2 stream and
    the D10 second-read stream (what `ncaa-gate --id ncaa-elo-v2 --preflight` prints as STREAM FINGERPRINT and the run
    takes as --stream-fingerprint); "training" = training_fingerprint (the stream the fit of s read; --preflight's
    "today's training stream"). Each (sha256 hex, games)."""
    from src.walters import ncaa_v1r_gate as vg

    v, second = vg.load_streams(vg.V2)
    return {"stream": vg.stream_fingerprint(v.games, vg.V2, second.games if second is not None else None),
            "training": vg.training_fingerprint(v.games, vg.V2)}


def write_status(changes: list[dict]) -> None:
    """Writes Match.status alone (addendum 116 item 4 (1): "sets status (and nothing else — never utc_date, never
    scores)"): one UPDATE per row, restricted to the status column and guarded by the status the change set read
    (UPDATE matches SET status = new WHERE id = ? AND status = stored). One transaction: a row whose status moved since
    the read raises StatusMoved and nothing is written."""
    from sqlalchemy import update

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus

    with session_scope() as s:
        for m in changes:
            res = s.execute(update(Match)
                            .where(Match.id == m["id"], Match.status == MatchStatus[m["status"]])
                            .values(status=MatchStatus[m["new"]])
                            .execution_options(synchronize_session=False))
            if res.rowcount != 1:
                raise StatusMoved(f"match {m['id']}: its stored status is no longer {m['status']} (it moved since "
                                  f"the read)")


def apply(competition_code: str, season: str, match_ids, adapter_for: Callable,
          out: Callable[[str], None] = print, now=None) -> int:
    """`score-presence-apply` (addendum 116 item 4 (1)). Reads the listing, resolves it and computes the rule's change
    set exactly as the dry run does (at `now`; None = utc now). Refuses AS A WHOLE, nothing written, every reason
    named, when a named id is not in the change set for that competition-season (a NEEDS SCORES row included: the
    rule reads FINISHED but its stored scores are missing or differ), is held (holds: an NFL row not preseason, item 4
    (2); a row the sync re-keys), or when the listing cannot be read. A text "None" change, off the APPLY line, is
    accepted when named (the architect's word carried out). Then writes Match.status alone on the named rows
    (write_status) and prints each id stored → new, the count and, for NCAA, ncaa-elo-v2's fingerprints before and
    after.
    Exit 0 applied; 1 refused (or a fingerprint moved, which status cannot do); 2 no database file. The caller (the
    CLI) verifies the .backup first."""
    from src.adapters.api_sports_status import LONGEST_GAME_H, rule_now

    code = competition_code.upper()
    named = sorted({int(x) for x in match_ids})
    gone = missing_db()
    if gone:
        out(f"✗ no database at {gone}; the apply never creates one (law 5) · nothing written")
        return 2
    now = rule_now(now)
    for ln in header("SCORE-PRESENCE APPLY", "writes Match.status ONLY, on named rows of the rule's change set; "
                     "refuses as a whole", now):
        out(ln)

    def tail(**kw):
        out("SCORE-PRESENCE-APPLY " + json.dumps({"competition": code, "season": season, "named": named,
                                                  "now": _when(now) + "Z", "longest_game_h": LONGEST_GAME_H,
                                                  "written_columns": ["status"] if kw.get("applied") else [], **kw},
                                                 sort_keys=True))

    if code not in COMPETITIONS or stored_seasons(code) is None:
        why = (f"{code} is not a competition of the rule ({', '.join(COMPETITIONS)})" if code not in COMPETITIONS
               else f"{code} is not in the DB")
        out(f"  REFUSED as a whole · nothing written: {why}")
        tail(applied=0, refused=[{"id": None, "why": why}])
        return 1
    adapter = adapter_for(code)
    source = adapter.source_name
    try:
        listing, shorts = read_listing(adapter, code, season, now)
    except Exception as e:
        why = f"the listing could not be read ({type(e).__name__}: {e})"
        out(f"  REFUSED as a whole · nothing written: {code} {season}: {why}")
        tail(applied=0, refused=[{"id": None, "why": why}])
        return 1
    rows, resolved = resolve(code, season, source, listing)
    r = compare(code, listing, shorts, rows, resolved)
    changes = {m["id"]: m for m in r["changes"]}
    needs = set(needs_scores_ids(r))
    in_season = {m["id"] for m in rows}
    refused = []
    for mid in named:
        m = changes.get(mid)
        if m is None:
            why = r["why_row"].get(mid) or ("no listed game resolves to it" if mid in in_season
                                            else f"not a stored row of {code} {season}")
            refused.append({"id": mid, "why": f"NEEDS SCORES (held): {why}" if mid in needs else
                            f"not in the rule's change set for {code} {season}: {why}"})
        elif holds(m):                                      # an NFL row not preseason, or a row the sync re-keys
            why = []
            if m["nfl"] == NOT_PRESEASON_HELD:
                why.append(f"HELD ({HELD_NFL_WHY}) · stored stage {m['stage'] or 'none'!r}")
            if m.get("rekey"):
                why.append(f"HELD ({HELD_REKEY_WHY}) · provider {m['rekey']}")
            refused.append({"id": mid, "why": "; ".join(why)})
    out(f"{code} {season} · source {source} · listing {r['listing']} games · stored {r['stored']} rows · the rule's "
        f"change set {len(changes)} · named {len(named)}: {','.join(map(str, named))}")
    if refused:
        out(f"  REFUSED as a whole · nothing written · {len(refused)} of {len(named)} named id(s) refused:")
        for x in refused:
            out(f"    match {x['id']}: {x['why']}")
        tail(applied=0, refused=refused)
        return 1
    accepted = [changes[mid] for mid in named]
    fps = {"before": ncaa_fingerprints()} if code == "NCAA" else {}
    try:
        write_status(accepted)
    except StatusMoved as e:
        out(f"  REFUSED as a whole · nothing written (rolled back): {e}")
        tail(applied=0, refused=[{"id": None, "why": str(e)}])
        return 1
    out(f"  APPLIED · Match.status only · {len(accepted)} row(s):")
    for m in accepted:
        out(f"    {_row(m)} · {m['class']} · {m['status']} → {m['new']}{_nfl(m)}")
    out(f"  count {len(accepted)} · written: status only (no kickoff, score, stage, season, status code or provider "
        f"id; no row created or deleted)")
    same = True
    if fps:
        fps["after"] = ncaa_fingerprints()
        for k, what in (("stream", "stream fingerprint (both streams)"), ("training", "training fingerprint")):
            (b, bn), (a, an) = fps["before"][k], fps["after"][k]
            same = same and (b, bn) == (a, an)
            out(f"  ncaa-elo-v2 {what}: before {b} ({bn} games) · after {a} ({an} games) · "
                f"{'SAME' if (b, bn) == (a, an) else 'CHANGED'}")
    if not same:
        out("  ✗ a fingerprint CHANGED, which status cannot do (no field of either, no filter of the walk): the write "
            "is committed; restore from the .backup and report it")
    tail(applied=len(accepted), ids=[m["id"] for m in accepted], refused=[],
         fingerprints={w: {k: list(v) for k, v in d.items()} for w, d in fps.items()},
         fingerprints_same=same if fps else None)
    return 0 if same else 1
