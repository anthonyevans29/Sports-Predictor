"""
MATCH DEDUPE (ARCHITECT 2026-10-03, priority): "sync-matches NCAA (2026-10-03
07:51) created 1006 rows and the fixtures export now holds DUPLICATE games —
a scheduled row (old provider id?) and a finished row for the same fixture
... Receipt: how the two rows differ (ext ids, team ids, utc_date); fix the
matcher so a resync UPDATES; dedupe the 1006 with a receipt (never delete the
row the ledger or odds reference — merge into it)."

A DUPLICATE PAIR: two rows of one competition with the same home AND away team,
kickoffs within WINDOW_H, and DIFFERENT ids under the source. Clusters of three
or more, and pairs that only match home/away SWAPPED, are reported, never
merged.

MERGE (per pair): the KEEPER is the OLDER row (lower id) — the one the ledger,
odds, Kalshi snapshots and predictions were written against before the resync.
The newer row (the resync's) carries the provider's latest state:
  * status / status_raw / utc_date / matchday / stage / scores / result /
    venue copy from it, never blanking a value and never regressing a
    FINISHED keeper to non-finished;
  * the keeper takes its source id; the keeper's old id moves to
    "<source>_prev"; other ids it lacks are added;
  * every row in every table referencing matches.id is re-pointed to the
    keeper (discovered from the schema, not listed by hand); a table where
    match_id is unique and BOTH rows hold an entry refuses the pair (no child
    row is ever deleted);
  * then the newer row — now referenced by nothing — is deleted.
Dry-run by default; --apply needs a verified .backup (CLI).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta, timezone

WINDOW_H = 12
FIELDS = ("status", "status_raw", "utc_date", "matchday", "stage", "home_score", "away_score",
          "home_score_ht", "away_score_ht", "home_score_90", "away_score_90", "full_time_result", "venue")


SKIPPED_ABSENT: set = set()     # reference tables the ORM maps but the live DB lacks (receipt)


def _live_tables(s) -> set | None:
    """Table names in the live DB (None when the session cannot be inspected)."""
    try:
        from sqlalchemy import inspect

        return set(inspect(s.get_bind()).get_table_names())
    except Exception:
        return None


def _fk_tables(s=None):
    """(table, column, unique_with_match_id) for every column referencing matches.id.
    With a session: tables ABSENT from the live DB are skipped (ARCHITECT 2026-10-05:
    `dedupe --apply` crashed "no such table: intl_venue_resolved" — a table the code maps
    but init_db has not created yet holds no references) and named in SKIPPED_ABSENT."""
    from src.db.schema import Base

    live = _live_tables(s) if s is not None else None
    out = []
    for t in Base.metadata.sorted_tables:
        if live is not None and t.name not in live:
            SKIPPED_ABSENT.add(t.name)
            continue
        for c in t.columns:
            if any(fk.target_fullname == "matches.id" for fk in c.foreign_keys):
                uniq = any(c.name in [x.name for x in con.columns] and len(con.columns) <= 2
                           for con in t.constraints
                           if con.__class__.__name__ in ("UniqueConstraint", "PrimaryKeyConstraint")
                           and [x.name for x in con.columns] != ["id"])
                out.append((t, c, uniq))
    return out


# THE RECORD ON A RETIRED ID (ARCHITECT 2026-11-04 15:45 ET, addendum 254 item 2(4)), verbatim: "our match_id is
# read as recorded; dedupe-matches prints one receipt line, "record rows on retired match ids: N", and rewrites
# nothing in the record." Both record tables carry our match_id as a plain integer with no foreign key
# (src/db/schema.py), so _fk_tables never lists them and merge() never re-points them: the rows stay on the retired id
# as recorded, and a per-game fact keeps the source's own game id in attrs (record.SOURCE_MATCH_IDS). N counts the rows
# of both tables whose match_id is the newer row of a merge the run made (apply: a refused merge retires nothing and is
# left out) or, on a dry run, of every planned merge (a refusal at apply is not known on a dry run, so the dry run's N
# can exceed the apply's). Read-only: SELECT COUNT only. A database without the record's tables (pre-migration) prints
# RECORD_ABSENT; one whose tables cannot be inspected prints RECORD_UNREADABLE; never a 0 it did not count (law 4).
RECORD_TABLES = ("availability_observations", "availability_assertions")
RECORD_LINE = "record rows on retired match ids"
RECORD_ABSENT = "n/a (availability tables absent)"
RECORD_UNREADABLE = "n/a (the live DB's tables could not be read)"
_IN_CHUNK = 500                       # SQLite's bound-variable limit is 999 on older builds


def record_rows_on(s, ids) -> int | str:
    """The record's rows (both tables) whose match_id is among `ids`: an int, or the n/a label when the record's tables
    are absent from the live DB or the DB cannot be inspected. Read-only (SELECT COUNT)."""
    from sqlalchemy import func, select

    from src.db.schema import AvailabilityAssertion, AvailabilityObservation

    live = _live_tables(s)
    if live is None:
        return RECORD_UNREADABLE
    if any(t not in live for t in RECORD_TABLES):
        return RECORD_ABSENT
    ids = sorted({int(i) for i in ids})
    n = 0
    for model in (AvailabilityObservation, AvailabilityAssertion):
        for k in range(0, len(ids), _IN_CHUNK):
            n += s.execute(select(func.count()).select_from(model)
                           .where(model.match_id.in_(ids[k:k + _IN_CHUNK]))).scalar()
    return n


def record_line(n) -> str:
    """The one receipt line, exactly as ruled: "record rows on retired match ids: N"."""
    return f"{RECORD_LINE}: {n}"


def find_pairs(s, competition_code: str, source: str):
    """(pairs, report): pairs = [(keeper, newer)]; report counts the rest."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match

    comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
    if comp is None:
        raise ValueError(f"competition {competition_code} not in DB")
    by_pair = defaultdict(list)
    for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars():
        by_pair[(m.home_team_id, m.away_team_id)].append(m)
    win = timedelta(hours=WINDOW_H)
    pairs, rc, seen = [], Counter(), set()
    for (h, a), rows in by_pair.items():
        rows.sort(key=lambda m: (m.utc_date, m.id))
        for i, m in enumerate(rows):
            if m.id in seen:
                continue
            cluster = [x for x in rows if x.utc_date and m.utc_date and abs(x.utc_date - m.utc_date) <= win]
            if len(cluster) < 2:
                continue
            seen.update(x.id for x in cluster)
            ids = {(x.external_ids or {}).get(source) for x in cluster}
            if len(cluster) > 2:
                rc["refused_cluster_gt2"] += 1
                continue
            if None in ids or len(ids) < 2:
                rc["refused_same_or_missing_source_id"] += 1
                continue
            keeper, newer = sorted(cluster, key=lambda x: x.id)
            pairs.append((keeper, newer))
        for m in rows:                                   # swapped near-pairs: report only
            for x in by_pair.get((a, h), []):
                if h < a and x.utc_date and m.utc_date and abs(x.utc_date - m.utc_date) <= win:
                    rc["swapped_near_pairs_not_merged"] += 1
    return pairs, rc


def describe(keeper, newer, source: str) -> dict:
    """How the two rows differ (the receipt the ruling asks for)."""
    def row(m):
        return {"id": m.id, "ext": (m.external_ids or {}).get(source), "home": m.home_team_id,
                "away": m.away_team_id, "utc": m.utc_date.isoformat() if m.utc_date else None,
                "status": getattr(m.status, "value", m.status), "status_raw": m.status_raw,
                "score": f"{m.home_score}-{m.away_score}" if m.home_score is not None else None,
                "season": m.season}
    k, n = row(keeper), row(newer)
    return {"keeper": k, "newer": n, "differs": sorted(f for f in k if f != "id" and k[f] != n[f])}


def stamp_rekey(ext: dict, source: str, old, new, via: str) -> None:
    """Provenance for a re-key (ARCHITECT 2026-10-03: an apply that re-keyed 962
    rows printed "merged 0" — who re-keyed must be readable from the row):
    the old id joins "<source>_prev" and {"from","to","via","at"} joins
    "<source>_rekeys". via: "dedupe-merge" | "orphan-merge" | "orphan-relink" | "sync"."""
    from src.timeutil import utc_now_naive

    prev = list(ext.get(f"{source}_prev") or [])
    if old and old not in prev:
        prev.append(old)
    ext[f"{source}_prev"] = prev
    if old != new:
        log = list(ext.get(f"{source}_rekeys") or [])
        log.append({"from": old, "to": new, "via": via, "at": utc_now_naive().isoformat(timespec="seconds")})
        ext[f"{source}_rekeys"] = log


def merge(s, keeper, newer, source: str, take_state: bool = True, via: str = "dedupe-merge") -> dict:
    """Merge `newer` into `keeper` (see module doc). Returns {table: re-pointed} or
    {"refused": reason}. Caller owns the transaction. take_state=False (the
    orphan path, when the STALE row is the newer one): the keeper keeps its own
    state and id, the stale row's id joins its "<source>_prev"."""
    from sqlalchemy import func, select, update

    from src.db.schema import MatchStatus

    tables = _fk_tables(s)
    for t, c, uniq in tables:
        if uniq:
            both = [s.execute(select(func.count()).select_from(t).where(c == mid)).scalar()
                    for mid in (keeper.id, newer.id)]
            if all(both):
                return {"refused": f"{t.name}: both rows hold an entry ({both}) — nothing deleted"}
    finished = keeper.status == MatchStatus.FINISHED
    for f in (FIELDS if take_state else ()):
        v = getattr(newer, f)
        if v is None:
            continue
        if f == "status" and finished and v != MatchStatus.FINISHED:
            continue
        setattr(keeper, f, v)
    ext, new_ext = dict(keeper.external_ids or {}), dict(newer.external_ids or {})
    if take_state:
        stamp_rekey(ext, source, ext.get(source), new_ext.get(source), via)
        ext[source] = new_ext.get(source)
    else:                                   # keeper keeps its id; the stale id is history, with provenance
        stamp_rekey(ext, source, new_ext.get(source), ext.get(source), via)
    for k, v in new_ext.items():
        ext.setdefault(k, v)
    # THE PROVIDER'S ORIENTATION (ARCHITECT 2026-11-08, addendum 295 item 5(a), #885): the key records what the listing
    # of the row's provider id says about it, and the odds writers price by it. The keeper's id is the newer row's
    # (take_state) or its own, so the key is that id's row's, never the other row's (none when that row had none).
    from src.ingestion.score_orientation import PROVIDER_ORIENTATION_KEY
    own = new_ext if take_state else dict(keeper.external_ids or {})
    if PROVIDER_ORIENTATION_KEY in own:
        ext[PROVIDER_ORIENTATION_KEY] = own[PROVIDER_ORIENTATION_KEY]
    else:
        ext.pop(PROVIDER_ORIENTATION_KEY, None)
    moved = {}
    for t, c, _ in tables:
        n = s.execute(update(t).where(c == newer.id).values({c.name: keeper.id})).rowcount
        if n:
            moved[t.name] = n
    keeper.external_ids = ext
    s.flush()
    s.delete(newer)
    s.flush()
    return moved


def run(competition_code: str, source: str = "api_american_football", apply: bool = False,
        sample: int = 8) -> dict:
    from src.db.database import session_scope

    out = {"competition": competition_code, "source": source, "applied": apply}
    with session_scope() as s:
        out["before"] = state(s, competition_code, source)
        pairs, rc = find_pairs(s, competition_code, source)
        out["pairs"] = len(pairs)
        out["report"] = dict(rc)
        out["differs"] = dict(Counter(f for k, n in pairs for f in describe(k, n, source)["differs"]))
        out["sample"] = [describe(k, n, source) for k, n in pairs[:sample]]
        moved, refused, merged = Counter(), [], 0
        retired = []                     # the newer rows' ids: merged (apply) or every planned pair's (dry run)
        if apply:
            for k, n in pairs:
                nid = n.id
                r = merge(s, k, n, source)
                if "refused" in r:
                    refused.append({"keeper": k.id, "newer": nid, "why": r["refused"]})
                    continue
                merged += 1
                retired.append(nid)
                moved.update(r)
        else:
            retired = [n.id for _k, n in pairs]
            s.rollback()
        out.update(merged=merged, refused=refused, repointed=dict(moved), retired_ids=sorted(retired))
        out["record_rows_on_retired"] = record_rows_on(s, retired)       # addendum 254 item 2(4): a SELECT only
        s.flush()
        out["after"] = state(s, competition_code, source)
    return out


def state(s, competition_code: str, source: str) -> dict:
    """The competition's re-key state — what a summary must report besides this
    run's merges (ARCHITECT 2026-10-03: "merged 0" on a table 962 rows of which
    were already re-keyed in place). rekeys_by_via counts the provenance log."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus

    comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
    if comp is None:
        raise ValueError(f"competition {competition_code} not in DB")
    rows = list(s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())
    via = Counter(r.get("via") for m in rows for r in ((m.external_ids or {}).get(f"{source}_rekeys") or []))
    return {"rows": len(rows),
            "carry_prev": sum(1 for m in rows if (m.external_ids or {}).get(f"{source}_prev")),
            "stale_orphans": sum(1 for m in rows if m.status == MatchStatus.STALE_ORPHAN),
            "rekeys_by_via": dict(via)}


# ---------------------------------------------------------------------------
# ORPHANS (ARCHITECT 2026-10-03): "13 window duplicates where the kickoff moved
# >12h (twin test too tight for provider time corrections: widen to same
# home+away within 48h when one row is stale-scheduled and the other has a live
# id), and 142 stale SCHEDULED rows >6h past kickoff with no result — orphans
# under retired ids ... Add `dedupe-matches --orphans` dry-run/apply: resolve
# each stale row's sid at the provider; NOT FOUND + a live twin → merge; NOT
# FOUND + no twin → mark status=stale_orphan (never delete). Receipt first.
# Georgia@Alabama must resolve to its live id before next Saturday."
#
# Candidates: SCHEDULED rows with no score and a source id that are either
# STALE (kickoff more than STALE_H past) or have a TWIN (same home AND away,
# kickoffs within TWIN_H, a different source id). Each candidate's id is
# resolved at the provider (GET /games?id=):
#   * found               -> live: untouched. A stale one is "live, resync
#                            needed" only for a change of STATE the provider
#                            serves and our row lacks (#945, #1001; ARCHITECT,
#                            addenda 365 item 3(b) and 382 item 4): the status,
#                            a score, the kickoff, or the provider_orientation
#                            key a resync would write or remove (served_diff);
#                            status_raw, matchday and stage are annotations
#                            (named, never counted); one whose served state
#                            equals the stored one is "live", nothing to do.
#                            An id that serves ANOTHER pair (neither the stored
#                            one nor its reverse), stale or not, is "live, the
#                            id serves another pair" (382 item 4(c));
#   * lookup error        -> UNRESOLVED: untouched (never read as absent);
#   * NOT FOUND + exactly one twin whose id IS found -> MERGE (keeper = the older
#     row; when the stale row is the keeper it takes the twin's id and state,
#     else the twin keeps its own and the stale id joins its _prev);
#   * NOT FOUND, no twin  -> the provider's games on the row's date ±2 days are
#     searched for the same home AND away team: exactly one, its id held by no
#     row -> RELINK (re-key in place, provider state applied); held by a row
#     outside the twin window, two games, or only home/away swapped -> REFUSED
#     (reported); none -> STALE_ORPHAN (never deleted).
# Dry-run by default; --apply needs a verified .backup (CLI).
STALE_H = 6
TWIN_H = 48
SEARCH_DAYS = 2


def _team_sids(s, source: str, team_ids) -> dict:
    from sqlalchemy import select

    from src.db.schema import Team

    from src.ingestion.team_merge import source_ids

    # every provider id a row answers to: a merged row holds more than one (addendum 44 item 3)
    return {t.id: source_ids(t.external_ids, source)
            for t in s.execute(select(Team).where(Team.id.in_(set(team_ids)))).scalars()}


def _check_allows_orphan(s) -> str | None:
    """SQLite DDL guard: a table created with a CHECK on the status column that
    predates STALE_ORPHAN would reject the mark — refuse it cleanly instead."""
    from sqlalchemy import text

    if s.get_bind().dialect.name != "sqlite":
        return None
    ddl = s.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='matches'")).scalar() or ""
    if "CHECK" in ddl.upper() and "SCHEDULED" in ddl and "STALE_ORPHAN" not in ddl:
        return "the matches table carries a status CHECK constraint without STALE_ORPHAN"
    return None


def orphans(competition_code: str, adapter, source: str = "api_american_football", apply: bool = False,
            now=None, pace=None) -> dict:
    """Plan (and with apply, perform) the orphan actions. Returns the receipt."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus
    from src.ingestion.service import IngestionService
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    pace = pace or (lambda: None)
    cache: dict = {}

    def resolve(sid):
        if sid not in cache:
            pace()
            try:
                exists, nm = adapter.get_game(str(sid), competition_code)
                cache[sid] = ("found", nm) if exists else ("absent", None)
            except Exception as e:  # noqa: BLE001 — UNRESOLVED, never absent
                cache[sid] = ("error", f"{type(e).__name__}: {str(e)[:120]}")
        return cache[sid]

    day_cache: dict = {}

    def games_on(day: str):
        if day not in day_cache:
            pace()
            try:
                day_cache[day] = adapter.list_matches(competition_code, date_from=day, date_to=day)
            except Exception as e:  # noqa: BLE001
                day_cache[day] = e
        return day_cache[day]

    out = {"competition": competition_code, "source": source, "applied": apply, "now": now.isoformat()}
    with session_scope() as s:
        out["before"] = state(s, competition_code, source)
        comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one()
        rows = list(s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())
        sid_of = lambda m: (m.external_ids or {}).get(source)  # noqa: E731
        holder = {}
        for m in rows:
            if sid_of(m):
                holder.setdefault(str(sid_of(m)), []).append(m)
        by_pair = defaultdict(list)
        for m in rows:
            if m.status not in (MatchStatus.CANCELLED, MatchStatus.STALE_ORPHAN):
                by_pair[(m.home_team_id, m.away_team_id)].append(m)

        def unplayed(m):
            return m.status == MatchStatus.SCHEDULED and m.home_score is None and m.away_score is None

        def twins(m):
            return [x for x in by_pair[(m.home_team_id, m.away_team_id)]
                    if x.id != m.id and x.utc_date and m.utc_date and sid_of(x) and sid_of(x) != sid_of(m)
                    and abs(x.utc_date - m.utc_date) <= timedelta(hours=TWIN_H)]

        stale_cut = now - timedelta(hours=STALE_H)
        cands = sorted((m for m in rows if unplayed(m) and sid_of(m) and m.utc_date
                        and (m.utc_date < stale_cut or twins(m))), key=lambda m: m.id)
        tsid = _team_sids(s, source, [t for m in cands for t in (m.home_team_id, m.away_team_id)])
        plan, claimed = [], set()                        # claimed: live ids a relink already takes

        # PR #270 review 2 (Anthony): uniqueness is decided per CONNECTED COMPONENT of the twin graph
        # (same home+away, kickoffs within TWIN_H, different ids), never candidate by candidate — so no
        # insertion or id order can let one candidate's set hide a competing twin from another.
        comp_of: dict = {}
        for r in sorted((x for grp in by_pair.values() for x in grp if sid_of(x) and x.utc_date), key=lambda x: x.id):
            if r.id in comp_of:
                continue
            comp, stack = [], [r]
            comp_of[r.id] = comp
            while stack:
                x = stack.pop()
                comp.append(x)
                for y in twins(x):
                    if y.id not in comp_of:
                        comp_of[y.id] = comp
                        stack.append(y)
        cand_ids = {m.id for m in cands}

        def entry(x, action, **kw):
            return {"id": x.id, "sid": sid_of(x), "utc": x.utc_date.isoformat(), "home": x.home_team_id,
                    "away": x.away_team_id, "stale": x.utc_date < stale_cut, "action": action, **kw}

        def served(nm):
            """What the provider serves for a live id, from the by-id answer already read (#945; ARCHITECT 2026-11-12,
            addendum 348 item 2: "say what the provider serves for each"): its status as our map reads it, its status
            code verbatim, its score and its kickoff. No further call. An id that answers with no game the adapter
            keeps (non-competitive, or served with no date or no team ids) says so, without claiming which."""
            if nm is None:
                return "the id answers; the adapter kept no game (non-competitive, or no date or team ids)"
            score = None if nm.home_score is None and nm.away_score is None else f"{nm.home_score}-{nm.away_score}"
            return {"status": nm.status.name, "status_raw": nm.status_raw, "score": score,
                    "utc": nm.utc_date.isoformat()}

        def served_diff(x, nm):
            """(state, annotation): what a resync would write on a live row, as the upsert writes it
            (IngestionService._apply_match_updates; the orientation check _scores_by_team), split by ARCHITECT
            2026-11-14 13:38 ET, addendum 382 item 4, verbatim: "THE LABEL "live, resync needed" IS FOR A CHANGE OF
            STATE THE PROVIDER SERVES AND OUR ROW LACKS. (a) What counts, each named when it does: the status, a
            score, the kickoff, and a stored provider_orientation key the upsert would remove on the same pair [...]
            (b) What does NOT count, alone or together: status_raw, matchday and stage. They are annotations of a
            state we already hold; a row that differs only in them reads `live`, and under --sample its line names
            each one that differs ("annotation: status_raw None -> NS"), so nothing is hidden." State: the status and
            the kickoff (always written), a score side (when served), the provider_orientation key (removed on the same
            pair; written on a reversal not yet recorded). Annotation: a served, non-empty status code, matchday or
            stage the row lacks (the writer never blanks a stored one). A REVERSED pair is the same game: its served
            scores are compared in the stored orientation (score_orientation.scores_by_team swaps them so). Returns
            None for a pair that is neither the stored one nor its reverse (382 item 4(c): its own label)."""
            from src.ingestion.score_orientation import PROVIDER_ORIENTATION_KEY, REVERSED
            hs, as_ = tsid.get(x.home_team_id) or set(), tsid.get(x.away_team_id) or set()
            h_, a_ = str(nm.home_team_source_id), str(nm.away_team_source_id)
            same, rev = (h_ in hs and a_ in as_), (h_ in as_ and a_ in hs)
            if not (same or rev):
                return None
            state, note = {}, {}
            held = (x.external_ids or {}).get(PROVIDER_ORIENTATION_KEY)
            if same and held is not None:          # the upsert REMOVES it (SAME); the odds writers read it (#997)
                state[PROVIDER_ORIENTATION_KEY] = f"{held} -> (removed: the served pair is the stored one)"
            if rev and held != REVERSED:           # a reversal not yet recorded: the upsert writes the key
                state[PROVIDER_ORIENTATION_KEY] = f"{held} -> {REVERSED}"
            if nm.status != x.status:
                state["status"] = f"{x.status.name} -> {nm.status.name}"
            served_sides = ({"home_score": nm.home_score, "away_score": nm.away_score} if same
                            else {"home_score": nm.away_score, "away_score": nm.home_score})   # stored orientation
            for side, v in served_sides.items():
                if v is not None and v != getattr(x, side):
                    state[side] = f"{getattr(x, side)} -> {v}"
            served_utc = nm.utc_date.astimezone(timezone.utc).replace(tzinfo=None) if nm.utc_date.tzinfo else nm.utc_date
            if served_utc != x.utc_date:
                state["kickoff"] = f"{x.utc_date.isoformat()} -> {served_utc.isoformat()}"
            for f in ("status_raw", "matchday", "stage"):
                v = getattr(nm, f, None)
                if v not in (None, "") and v != getattr(x, f, None):
                    note[f] = f"{getattr(x, f, None)} -> {v}"
            return state, note

        def other_pair(x, nm):
            """382 item 4(c): the stored pair and the served pair, by team id; whether the row records the mismatch."""
            from src.ingestion.score_orientation import PROVIDER_ORIENTATION_KEY
            ours = lambda sid: sorted(t for t, ss in tsid.items() if sid in ss) or "not stored"   # noqa: E731
            h_, a_ = str(nm.home_team_source_id), str(nm.away_team_source_id)
            held = (x.external_ids or {}).get(PROVIDER_ORIENTATION_KEY)
            return {"pair": f"stored teams {x.home_team_id} v {x.away_team_id} -> served provider teams {h_} v {a_} "
                            f"(our teams {ours(h_)} v {ours(a_)})",
                    "recorded": f"{PROVIDER_ORIENTATION_KEY} = {held}" if held else "the mismatch is not recorded"}

        def live_entry(x, nm):
            if nm is not None and served_diff(x, nm) is None:     # 382 item 4(c): "neither `live` nor `live, resync
                return entry(x, "live_other_pair", served=served(nm), **other_pair(x, nm))   # needed`", stale or not
            if x.utc_date >= stale_cut:                  # not stale: live, as before (365 item 3(b) splits the stale)
                return entry(x, "live", served=served(nm))
            if nm is None:                               # nothing to compare: never read as equal (law 4)
                return entry(x, "live_resync", served=served(nm),
                             differs={"served": "unknown: the id answers and the adapter kept no game"})
            state, note = served_diff(x, nm)
            extra = {"annotation": note} if note else {}
            if state:
                return entry(x, "live_resync", served=served(nm), differs=state, **extra)
            return entry(x, "live", served=served(nm), **extra)

        def date_search(m):
            hs, as_ = tsid.get(m.home_team_id), tsid.get(m.away_team_id)
            found, swapped, err = [], [], None
            for d in range(-SEARCH_DAYS, SEARCH_DAYS + 1):
                g = games_on((m.utc_date + timedelta(days=d)).strftime("%Y-%m-%d"))
                if isinstance(g, Exception):
                    err = f"{type(g).__name__}: {str(g)[:120]}"
                    continue
                for nm in g:
                    h_, a_ = str(nm.home_team_source_id), str(nm.away_team_source_id)
                    if hs and as_ and h_ in hs and a_ in as_:
                        found.append(nm)
                    elif hs and as_ and h_ in as_ and a_ in hs:
                        swapped.append(nm)
            return list({nm.source_id: nm for nm in found}.values()), swapped, err

        seen_comps = set()
        for m0 in cands:
            comp = comp_of.get(m0.id, [m0])
            if id(comp) in seen_comps:
                continue
            seen_comps.add(id(comp))
            comp = sorted(comp, key=lambda x: x.id)
            ids = [x.id for x in comp]
            cc = [x for x in comp if x.id in cand_ids]
            st_of = {x.id: resolve(sid_of(x)) for x in comp}            # every lookup in the set, first
            errs = [x.id for x in comp if st_of[x.id][0] == "error"]
            if errs:                                                     # incomplete coverage: nobody moves
                why = f"lookup failed for {errs} in candidate set {ids}: {st_of[errs[0]][1]}"
                plan.extend(entry(x, "unresolved", why=why) for x in cc)
                continue
            found = [x for x in comp if st_of[x.id][0] == "found"]
            absent = [x for x in cc if st_of[x.id][0] == "absent"]
            plan.extend(live_entry(x, st_of[x.id][1]) for x in cc if st_of[x.id][0] == "found")
            if not absent:
                continue
            if found:
                if len(comp) == 2 and len(found) == 1 and len(absent) == 1:
                    m, t = absent[0], found[0]
                    plan.append(entry(m, "merge", twin=t.id, twin_sid=sid_of(t), keeper=min(m.id, t.id),
                                      _rows=(m, t)))
                else:
                    why = (f"overlapping candidate set {ids}: {len(comp)} rows, {len(found)} live id(s) "
                           f"{[sid_of(x) for x in found]} — uniqueness not established, review")
                    plan.extend(entry(x, "refused", why=why) for x in absent)
                continue
            # no live id anywhere in the set: each absent candidate is searched at the provider; one
            # failed search day leaves the WHOLE set unresolved
            searched = [(m, *date_search(m)) for m in absent]
            bad = [(m.id, err) for m, _f, _s, err in searched if err]
            if bad:
                why = (f"provider search incomplete for {[b[0] for b in bad]} in candidate set {ids}: {bad[0][1]}")
                plan.extend(entry(x, "unresolved", why=why) for x in absent)
                continue
            for m, fnd, swapped, _ in searched:
                if len(fnd) > 1:
                    plan.append(entry(m, "refused", why=f"{len(fnd)} provider games for the pair within "
                                f"±{SEARCH_DAYS}d {[n.source_id for n in fnd]}"))
                elif fnd:
                    nm = fnd[0]
                    held = [x.id for x in holder.get(str(nm.source_id), []) if x.id != m.id]
                    if str(nm.source_id) in claimed:
                        plan.append(entry(m, "refused", live_sid=nm.source_id,
                                          why=f"live id {nm.source_id} already taken by another relink in this run"))
                    elif held:
                        plan.append(entry(m, "refused", live_sid=nm.source_id,
                                          why=f"live id {nm.source_id} held by row(s) {held} outside the "
                                              f"{TWIN_H}h twin window — review"))
                    else:
                        claimed.add(str(nm.source_id))
                        plan.append(entry(m, "relink", live_sid=nm.source_id, live_utc=nm.utc_date.isoformat(),
                                          _nm=nm, _row=m))
                elif swapped:
                    plan.append(entry(m, "refused", why=f"provider holds the pair home/away SWAPPED "
                                f"{[n.source_id for n in swapped]}"))
                else:
                    plan.append(entry(m, "orphan", _row=m))
        out["counts"] = dict(Counter(p["action"] for p in plan))
        out["provider_lookups"] = {"games_by_id": len(cache), "dates_searched": len(day_cache)}
        applied, refused = Counter(), []
        # the merges' newer rows are the ids retired (relink and orphan retire none: the row stays, re-keyed or marked)
        retired = [] if apply else [max(p["id"], p["twin"]) for p in plan if p["action"] == "merge"]
        if apply:
            guard = _check_allows_orphan(s)
            for p in plan:
                if p["action"] == "merge":
                    m, t = p["_rows"]
                    keeper, newer = (m, t) if m.id < t.id else (t, m)
                    nid = newer.id
                    r = merge(s, keeper, newer, source, take_state=(keeper is m), via="orphan-merge")
                    if "refused" in r:
                        refused.append({"id": p["id"], "why": r["refused"]})
                    else:
                        applied["merge"] += 1
                        retired.append(nid)
                elif p["action"] == "relink":
                    m, nm = p["_row"], p["_nm"]
                    ext = dict(m.external_ids or {})
                    stamp_rekey(ext, source, sid_of(m), str(nm.source_id), "orphan-relink")
                    ext[source] = str(nm.source_id)
                    # addendum 295 item 5(a) (#885): the live id lists the pair the SAME (date_search's `found`; a
                    # swapped pair is refused above), so the old id's orientation key goes, as a same listing removes it
                    from src.ingestion.score_orientation import PROVIDER_ORIENTATION_KEY
                    ext.pop(PROVIDER_ORIENTATION_KEY, None)
                    m.external_ids = ext
                    IngestionService._apply_match_updates(m, nm)
                    applied["relink"] += 1
                elif p["action"] == "orphan":
                    if guard:
                        refused.append({"id": p["id"], "why": f"orphan mark refused: {guard}"})
                        continue
                    m = p["_row"]
                    ext = dict(m.external_ids or {})
                    ext[f"{source}_orphaned_at"] = now.isoformat(timespec="seconds")
                    m.external_ids = ext
                    m.status = MatchStatus.STALE_ORPHAN
                    applied["orphan"] += 1
            s.flush()
        else:
            s.rollback()
        out["applied_counts"] = dict(applied)
        out["refused_at_apply"] = refused
        out["retired_ids"] = sorted(retired)
        out["record_rows_on_retired"] = record_rows_on(s, retired)       # addendum 254 item 2(4): a SELECT only
        out["plan"] = [{k: v for k, v in p.items() if not k.startswith("_")} for p in plan]
        out["after"] = state(s, competition_code, source) if apply else out["before"]
    return out
