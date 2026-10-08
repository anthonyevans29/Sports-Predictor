"""
NCAA CFBD LABEL LANE (ARCHITECT 2026-10-07, item 6, "#176 probe read", DATA
LANE): CollegeFootballData (CFBD) is the NCAA label source of record.

    "Build: the ingest command (operator-run; key from .env, never printed),
    the side table and its migration, the alias map, the stream read, a
    coverage receipt per season. No model change in this lane."

This module holds:
  * the CFBD fetch / field discovery shared with scripts/ncaa_source_probe.py
    (moved here, law 1: field names are DISCOVERED from the first record;
    a required field that cannot be found REFUSES the run);
  * the join of each CFBD game to OUR NCAA matches (below), the pinned alias
    map, and the upsert into ncaa_cfbd_labels (src/db/schema.py). The
    matches table is NEVER written by this module.

JOIN (operational definition, docs/specs/ncaa-cfbd-labels.md):
  * universe: OUR matches with competition code NCAA (Sport.NFL family), not
    CANCELLED / STALE_ORPHAN, kickoff within ±12h of CFBD's startDate (the
    shared matcher's window and status rule, src/ingestion/match_lookup.py);
  * names compared after the shared normalize_team_name;
  * tier 1 EXACT: both normalized names equal ours, in either orientation
    ('same' = CFBD home is our home; 'swapped' = CFBD home is our away);
    tier 2 SUBSTRING (the shared matcher's last resort), only when tier 1
    found nothing. Within a tier exactly ONE (match, orientation) must fit;
    two or more = AMBIGUOUS, REFUSED (never the matcher's start-time
    tiebreak: college teams do not play doubleheaders, so >1 is a naming
    collision, law 4);
  * two CFBD games landing on the same match id: all of them REFUSED;
  * aliases (pinned file ncaa_cfbd_aliases.json): a source name whose
    normalized form equals one of our NCAA teams' never uses an alias
    (exact wins); otherwise an alias replaces the source name only if its
    target names EXACTLY ONE of our NCAA teams (else refused, reported).

SCOPE + JOIN (ARCHITECT 2026-10-08, addendum 10 item 3; docs/specs/ncaa-cfbd-labels.md):
  * J1 dateshift: a source game the first pass leaves UNMATCHED is retried
    against our NCAA matches within ±36h (DATESHIFT_HOURS) by the same name
    tiers; it joins only if exactly one (match, orientation) fits, that match
    is not already joined (by the first pass), and the final scores agree in
    that orientation (join_via 'dateshift'; listed with both kickoffs and the
    offset). A name fit whose scores disagree stays unmatched, listed with both
    scores (dateshift_retry);
  * J2: OUR team names are html.unescape'd before normalization in the join
    and in alias vetting (our_norm). The id merge for the v1r stream and the
    shadow is team_merge (read-time mapping; the teams table is never written);
  * J4: CFBD's seasonType as served rides on each row (season_type, nullable,
    migrate_ncaa_cfbd_v2.py);
  * J5 (addendum 11): a SUBSTRING-tier fit joins only when our match is scored
    and the final scores agree in that orientation, in the first pass as in
    the retry; a first pass whose substring tier gives no clean join goes to
    the J1 retry (exact tier first across the 36 hours). Exact-tier joins are
    unchanged (join_one);
  * LABEL SET (addendum 11, L1-L4): every non-dry run writes one ingest record
    per season (ncaa_cfbd_ingest_records, zero joins included; write_record);
    the coverage fact is the season's latest record (stored_coverage, never
    opening the payload); a label is current when its fetched_at equals that
    record's (latest_record_stamps; the v1r stream and the shadow's FBS team
    set read current labels only); a non-dry run needs division fbs.
"""
from __future__ import annotations

import bisect
import html
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.collegefootballdata.com"
SOURCE = "cfbd"
KEY_ENV = "CFBD_API_KEY"
ALIAS_FILE = Path(__file__).with_name("ncaa_cfbd_aliases.json")
DEFAULT_SAVE_DIR = ROOT / "exports" / "cfbd"
TOLERANCE_HOURS = 12            # find_match's default window
DATESHIFT_HOURS = 36            # J1 (ARCHITECT 2026-10-08): the retry window, either side
COVERAGE_MIN = 0.95             # SCOPE (ARCHITECT 2026-10-07/-08): labelled / CFBD completed both-FBS, per season
SAMPLE = 15

FIELDS = {   # name -> regex over the record's keys (first match wins)
    "home": re.compile(r"^home_?team$", re.I),
    "away": re.compile(r"^away_?team$", re.I),
    "home_pts": re.compile(r"^home_?points$", re.I),
    "away_pts": re.compile(r"^away_?points$", re.I),
    "neutral": re.compile(r"^neutral_?site$", re.I),
    "start": re.compile(r"^start_?date$", re.I),
}
OPTIONAL = {
    "completed": re.compile(r"^completed$", re.I),
    "season_type": re.compile(r"^season_?type$", re.I),
    "home_class": re.compile(r"^home_?(classification|division)$", re.I),
    "away_class": re.compile(r"^away_?(classification|division)$", re.I),
    "id": re.compile(r"^id$", re.I),
}


class CFBDError(RuntimeError):
    """A refusal: the message is printed verbatim (never carries the key)."""


# --------------------------------------------------------------------------
# Source access (shared with scripts/ncaa_source_probe.py)
# --------------------------------------------------------------------------


def discover(rec: dict) -> tuple[dict, list[str]]:
    keys, missing = {}, []
    for name, rx in {**FIELDS, **OPTIONAL}.items():
        k = next((k for k in rec if rx.match(k)), None)
        if k is None and name in FIELDS:
            missing.append(name)
        keys[name] = k
    return keys, missing


def fetch(year: int, key: str, base: str = BASE, division: str | None = "fbs") -> tuple[int, list, dict]:
    """GET /games for one season. Returns (HTTP status, records, rate-limit headers).
    The key travels only in the Authorization header; it is never returned.
    A blank / None division (the documented `--division ''` = all
    classifications) OMITS the classification query parameter, so the payload
    is unfiltered at the source too (Codex on #333: it used to send
    classification=fbs while the local filter treated the run as "all")."""
    params = {"year": year, "seasonType": "both"}
    if division:
        params["classification"] = division
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{base}/games?{q}", headers={"Authorization": f"Bearer {key}",
                                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        hdr = {k: v for k, v in r.headers.items() if re.search(r"limit|remaining|quota|calls", k, re.I)}
        return r.status, json.loads(r.read().decode()), hdr


def parse_start(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def api_key() -> str:
    """CFBD_API_KEY from .env via config.settings (the single settings source).
    Callers never print it."""
    import config
    return (config.settings.cfbd_api_key or "").strip()


def _within(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def refuse_save_path(path: Path | str) -> None:
    """Where a raw CFBD payload may be written (Codex on #333). CFBD's terms
    forbid republishing and the repo is public, so inside the repository ONLY
    exports/ (gitignored) is allowed; data/ is refused (law 5); any path outside
    the repository is the operator's own. Real paths (symlinks resolved) on
    both sides, so a link into the tree cannot slip a tracked path through."""
    p = Path(path).expanduser().resolve()
    root = ROOT.resolve()
    if _within(p, (ROOT / "data").resolve()):
        raise CFBDError(f"REFUSED: never write under data/ (law 5): {path}")
    if _within(p, root) and not _within(p, (ROOT / "exports").resolve()):
        raise CFBDError(f"REFUSED: a CFBD payload inside the repository goes under exports/ only "
                        f"(gitignored; CFBD's terms forbid republishing, the repo is public): {path}")


def save_payload(recs: list, year: int, save_dir: Path | str | None = None,
                 now: datetime | None = None) -> Path:
    """The raw response, timestamped, under exports/cfbd/ by default (gitignored:
    CFBD's terms allow private storage and forbid republishing; this repo is public).
    Inside the repo only exports/ is accepted (refuse_save_path)."""
    d = Path(save_dir) if save_dir else DEFAULT_SAVE_DIR
    refuse_save_path(d)
    d.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    p = d / f"cfbd_games_{year}_{stamp}.json"
    with open(p, "w") as f:
        json.dump(recs, f)
    return p


def payload_label(path: Path | str) -> str:
    """Provenance string for the side table: repo-relative when under the repo."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT.resolve()))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# Alias map (ruling (3))
# --------------------------------------------------------------------------


def load_aliases(path: Path | str = ALIAS_FILE) -> dict[str, str]:
    try:
        doc = json.load(open(path))
    except (OSError, ValueError) as e:
        raise CFBDError(f"REFUSED: alias map {path} unreadable ({e})")
    al = doc.get("aliases") if isinstance(doc, dict) else None
    if not isinstance(al, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in al.items()):
        raise CFBDError(f"REFUSED: alias map {path} must hold {{\"aliases\": {{source name: our team name}}}}")
    return dict(al)


def our_norm(name: str | None) -> str:
    """J2 (ARCHITECT 2026-10-08): "In the join and in alias vetting our team
    names are HTML-unescaped before normalization." OUR stored name
    ('Hawai&#x27;i') -> html.unescape -> the shared normalize_team_name.
    Source (CFBD) names are normalized as served."""
    from src.ingestion.match_lookup import normalize_team_name as norm

    return norm(html.unescape(name or ""))


def escaped_names(teams: dict[int, str]) -> list[tuple[int, str, str]]:
    """[(team id, stored name, unescaped name)] for every one of OUR names that
    html.unescape changes (J2's receipt: "every name that changes")."""
    return sorted((tid, n, html.unescape(n)) for tid, n in teams.items() if n and html.unescape(n) != n)


def vet_aliases(aliases: dict[str, str], teams: dict[int, str]) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """(usable {source name: our team name}, refused [(source, target, reason)]).
    `teams` = our NCAA teams {id: name}. An alias is usable only if its target
    normalizes to EXACTLY ONE of our teams, and its source name does not
    already match one of ours exactly (an alias never overrides an exact match).
    Our names (and the target, which is one of ours) are html-unescaped first (J2)."""
    from src.ingestion.match_lookup import normalize_team_name as norm

    by_norm: dict[str, list[int]] = {}
    for tid, name in teams.items():
        by_norm.setdefault(our_norm(name), []).append(tid)
    ok, refused = {}, []
    for src, tgt in sorted(aliases.items()):
        if norm(src) in by_norm:
            refused.append((src, tgt, "shadowed: the source name already matches one of our teams exactly "
                                      "(an alias never overrides an exact match)"))
            continue
        hits = by_norm.get(our_norm(tgt), [])
        if len(hits) == 1:
            ok[src] = tgt
        elif not hits:
            refused.append((src, tgt, "target names 0 of our NCAA teams"))
        else:
            refused.append((src, tgt, f"target names {len(hits)} of our NCAA teams (ambiguous)"))
    return ok, refused


# --------------------------------------------------------------------------
# Join + labels
# --------------------------------------------------------------------------


@dataclass
class Ours:
    id: int
    utc_date: datetime
    season: str
    home_id: int
    away_id: int
    home_norm: str
    away_norm: str
    home_score: int | None
    away_score: int | None


def ncaa_teams(s) -> dict[int, str]:
    """{team id: name} for every team in any NCAA match (read-only)."""
    from sqlalchemy import select, union

    from src.db.schema import Competition, Match, Team

    comp_ids = select(Competition.id).where(Competition.code == "NCAA")
    ids = union(select(Match.home_team_id.label("t")).where(Match.competition_id.in_(comp_ids)),
                select(Match.away_team_id.label("t")).where(Match.competition_id.in_(comp_ids))).subquery()
    return {t.id: t.name for t in s.execute(select(Team).where(Team.id.in_(select(ids.c.t)))).scalars()}


def load_ours(s, start: datetime, end: datetime, teams: dict[int, str]) -> list[Ours]:
    """OUR NCAA matches kicking off in [start-36h, end+36h] (the J1 dateshift
    window; the first pass still uses ±12h), the shared matcher's status rule
    (CANCELLED / STALE_ORPHAN never join). Prefetched once (no per-record
    query). Our names html-unescaped before normalization (J2). Read-only."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, Sport

    norm = our_norm
    tol = timedelta(hours=max(TOLERANCE_HOURS, DATESHIFT_HOURS))
    rows = s.execute(
        select(Match).join(Competition, Match.competition_id == Competition.id).where(
            Match.sport == Sport.NFL, Competition.code == "NCAA",
            Match.utc_date >= start - tol, Match.utc_date <= end + tol,
            Match.status.notin_([MatchStatus.CANCELLED, MatchStatus.STALE_ORPHAN]),
        ).order_by(Match.utc_date, Match.id)).scalars().all()
    return [Ours(m.id, m.utc_date, m.season, m.home_team_id, m.away_team_id,
                 norm(teams.get(m.home_team_id, "")), norm(teams.get(m.away_team_id, "")),
                 m.home_score, m.away_score) for m in rows]


def _fits(tier: str, src: str, ours: str) -> bool:
    if not src or not ours:
        return False
    if tier == "exact":
        return src == ours
    return src in ours or ours in src


def tier_fits(home_n: str, away_n: str, start: datetime, ours: list[Ours], dates: list[datetime],
              hours: int) -> tuple[str | None, list[tuple[Ours, str]]]:
    """The name tiers over our matches within ±`hours` of `start`: (tier, every
    (match, orientation) that fits in it) for the FIRST tier with any fit
    (exact, then substring), else (None, []). Shared by the first pass (12h)
    and the J1 dateshift retry (36h): "by the same name tiers"."""
    if not home_n or not away_n:
        return None, []
    tol = timedelta(hours=hours)
    lo, hi = bisect.bisect_left(dates, start - tol), bisect.bisect_right(dates, start + tol)
    cands = ours[lo:hi]
    for tier in ("exact", "substring"):
        hits = []
        for m in cands:
            if _fits(tier, home_n, m.home_norm) and _fits(tier, away_n, m.away_norm):
                hits.append((m, "same"))
            if _fits(tier, away_n, m.home_norm) and _fits(tier, home_n, m.away_norm):
                hits.append((m, "swapped"))
        if hits:
            return tier, hits
    return None, []


def scores_agree(m: Ours, orient: str, hp, ap) -> bool:
    """Our match is scored and its final scores equal CFBD's stated in that orientation."""
    if m.home_score is None or m.away_score is None:
        return False
    oh, oa = (int(hp), int(ap)) if orient == "same" else (int(ap), int(hp))
    return (m.home_score, m.away_score) == (oh, oa)


def join_one(home_n: str, away_n: str, start: datetime, ours: list[Ours], dates: list[datetime],
             hp=None, ap=None):
    """The first pass (±12h): ('joined', Ours, orientation, tier, note) | ('ambiguous', ..., 'exact', note) |
    ('unmatched', None, None, tier|None, note).
    J5 (ARCHITECT 2026-10-08, addendum 11, verbatim): "A substring-tier fit is a join only when our match is
    scored and the final scores agree in that orientation, in the first pass as in the retry. A game whose
    first-pass substring tier gives no clean join (no fit, more than one fit, or a fit that fails this test) is
    unmatched for the first pass and goes to the J1 retry, where the exact tier is tried first across the 36
    hours. Exact-tier joins are unchanged: the side table carries CFBD's scores and a disagreement is listed as
    corrected (ruling (4) of 2026-10-07)." So: exact, one fit -> joined; exact, more than one -> ambiguous
    (refused, unchanged); substring -> joined only on exactly one fit that passes scores_agree, else unmatched."""
    tier, hits = tier_fits(home_n, away_n, start, ours, dates, TOLERANCE_HOURS)
    if tier == "exact":
        if len(hits) == 1:
            return "joined", hits[0][0], hits[0][1], tier, ""
        return "ambiguous", None, None, tier, ""
    if tier == "substring":
        if len(hits) > 1:
            return "unmatched", None, None, tier, (f"first pass: {len(hits)} substring fits (matches "
                                                   f"{', '.join(str(m.id) for m, _ in hits)}), no clean join")
        m, orient = hits[0]
        if hp is not None and ap is not None and scores_agree(m, orient, hp, ap):
            return "joined", m, orient, tier, ""
        ours_s = "—" if m.home_score is None or m.away_score is None else f"{m.home_score}-{m.away_score}"
        return "unmatched", None, None, tier, (f"first pass: substring fit our match {m.id} ({orient}) fails the "
                                               f"score test (ours {ours_s})")
    return "unmatched", None, None, None, ""


def _offset_h(ours_at: datetime, start: datetime) -> str:
    return f"{(ours_at - start).total_seconds() / 3600:+.1f}h"


def dateshift_retry(home_n: str, away_n: str, start: datetime, hp: int, ap: int, ours: list[Ours],
                    dates: list[datetime], joined_ids: set[int]) -> tuple[str, Ours | None, str | None, str]:
    """J1 (ARCHITECT 2026-10-08, verbatim): "A source game the first pass leaves
    unmatched is retried against our NCAA matches within 36 hours either side.
    It joins only if exactly one (match, orientation) fits by the same name
    tiers, that match is not already joined, and the final scores agree in that
    orientation. join_via is dateshift. Each such row is listed with both
    kickoffs and the offset; a name fit whose scores disagree stays unmatched
    and is listed with both scores."
    `hp`/`ap` = CFBD homePoints/awayPoints; `joined_ids` = our match ids the
    first pass joined. Returns (status, match, orientation, note) with status
    'joined' | 'no_fit' | 'ambiguous' | 'already_joined' | 'score_disagree'."""
    tier, hits = tier_fits(home_n, away_n, start, ours, dates, DATESHIFT_HOURS)
    if not hits:
        return "no_fit", None, None, ""
    if len(hits) > 1:
        return "ambiguous", None, None, (f"dateshift: {len(hits)} (match, orientation) fits in the {tier} tier "
                                         f"within ±{DATESHIFT_HOURS}h (matches "
                                         f"{', '.join(str(m.id) for m, _ in hits)}); stays unmatched")
    m, orient = hits[0]
    where = (f"our match {m.id} ({orient}, {tier} tier) · CFBD kickoff {start:%Y-%m-%d %H:%M} · ours "
             f"{m.utc_date:%Y-%m-%d %H:%M} · offset {_offset_h(m.utc_date, start)}")
    if m.id in joined_ids:
        return "already_joined", m, orient, f"dateshift: {where} — that match is already joined; stays unmatched"
    oh, oa = (int(hp), int(ap)) if orient == "same" else (int(ap), int(hp))
    ours_s = "—" if m.home_score is None or m.away_score is None else f"{m.home_score}-{m.away_score}"
    if (m.home_score, m.away_score) != (oh, oa):
        return "score_disagree", m, orient, (f"dateshift: {where} — scores disagree: ours {ours_s}, CFBD in our "
                                             f"orientation {oh}-{oa}; stays unmatched")
    return "joined", m, orient, f"dateshift: {where} · scores agree {oh}-{oa}"


@dataclass
class YearResult:
    year: int
    scope_label: str = "both-FBS"
    counts: Counter = field(default_factory=Counter)
    rows: list[dict] = field(default_factory=list)            # side-table rows to upsert
    corrections: list[str] = field(default_factory=list)      # every score-corrected row, with its reason
    unmatched: list[str] = field(default_factory=list)        # every unmatched game
    ambiguous: list[str] = field(default_factory=list)        # every refused game
    unmatched_names: Counter = field(default_factory=Counter)  # source names with no exact match of ours
    alias_refused: list[tuple[str, str, str]] = field(default_factory=list)
    aliases_usable: int = 0
    season_disagree: list[str] = field(default_factory=list)
    dateshift: list[str] = field(default_factory=list)        # J1: every dateshift row (both kickoffs, offset)
    escaped: list[tuple[int, str, str]] = field(default_factory=list)   # J2: our names html.unescape changes
    unlabelled: list[str] = field(default_factory=list)       # SCOPE: every in-scope game with no row, and why


def in_scope_reason(rec: dict, keys: dict, division: str | None) -> str | None:
    """None when the source game is IN SCOPE (completed or no `completed`
    field, both scores, both classifications == division), else the counter
    name of why not. The ingest's filter, shared with stored_coverage so the
    coverage denominator is the receipt's own ("CFBD's completed both-FBS")."""
    if keys["completed"] and rec.get(keys["completed"]) is False:
        return "source_not_completed"
    if rec.get(keys["home_pts"]) is None or rec.get(keys["away_pts"]) is None:
        return "source_no_score"
    if division and not (keys["home_class"] and keys["away_class"]):
        return "source_no_classification"            # Codex P1 on #365: never in scope without both fields
    if division and (str(rec.get(keys["home_class"]) or "").lower() != division
                     or str(rec.get(keys["away_class"]) or "").lower() != division):
        return f"source_not_both_{division}"
    return None


def _desc(rec: dict, keys: dict) -> str:
    start = parse_start(rec.get(keys["start"]))
    nv = rec.get(keys["neutral"])
    return (f"{start:%Y-%m-%d} " if start else "(no start) ") + \
        f"{rec.get(keys['away'])} @ {rec.get(keys['home'])}" + (" (neutral)" if nv else "")


def build_labels(records: list, keys: dict, ours: list[Ours], teams: dict[int, str],
                 aliases: dict[str, str], year: int, division: str | None = "fbs") -> YearResult:
    """Pure over its inputs: no DB, no network. Returns the rows to upsert and the receipt.
    First pass (±12h), then the J1 dateshift retry (±36h) for the first pass's
    UNMATCHED games only, then the duplicate-target refusal over both."""
    from src.ingestion.match_lookup import normalize_team_name as norm

    r = YearResult(year, scope_label=f"both-{division.upper()}" if division else "all")
    usable, r.alias_refused = vet_aliases(aliases, teams)
    r.aliases_usable = len(usable)
    r.escaped = escaped_names(teams)
    our_norms = {our_norm(n) for n in teams.values()}
    dates = [m.utc_date for m in ours]
    c = r.counts
    c["records"] = len(records)

    def resolve(name: str) -> tuple[str, bool]:
        n = norm(name)
        if n in our_norms:
            return n, False                                   # exact wins; an alias never overrides it
        if name in usable:
            return our_norm(usable[name]), True
        return n, False

    def make_row(rec, m, orient, via, desc, neutral, oh, oa):
        reason = None
        if m.home_score is None or m.away_score is None:
            kind = "ours_no_score"
        elif (m.home_score, m.away_score) == (oh, oa):
            kind = "score_agree"
        elif (m.home_score, m.away_score) == (oa, oh):
            kind = "score_reversed"
            reason = (f"score-reversed: provider home/away scores swapped vs CFBD (ours {m.home_score}-"
                      f"{m.away_score}, CFBD in our orientation {oh}-{oa})")
        else:
            kind = "score_disagree"
            reason = (f"score-disagree: provider scores differ from CFBD (ours {m.home_score}-{m.away_score}, "
                      f"CFBD in our orientation {oh}-{oa})")
        sid = rec.get(keys["id"]) if keys["id"] else None
        st = rec.get(keys["season_type"]) if keys.get("season_type") else None
        return {"match_id": m.id, "source": SOURCE, "source_game_id": int(sid) if isinstance(sid, int) else None,
                "season": str(year), "orientation": orient, "neutral": neutral, "home_score": oh, "away_score": oa,
                "source_home_team": rec.get(keys["home"]), "source_away_team": rec.get(keys["away"]),
                "join_via": via, "correction_reason": reason,
                "season_type": None if st is None else str(st),          # J4: CFBD seasonType as served
                "_kind": kind, "_desc": desc, "_our_season": m.season, "_rec": id(rec)}

    by_target: dict[int, list[dict]] = {}
    in_scope: list[tuple[dict, str]] = []
    pending: list[tuple] = []                                 # first-pass unmatched, for the J1 retry
    why_not: dict[int, str] = {}                              # id(rec) -> why it carries no row
    for rec in records:
        out_of_scope = in_scope_reason(rec, keys, division)
        if out_of_scope:
            c[out_of_scope] += 1
            continue
        hp, ap = rec.get(keys["home_pts"]), rec.get(keys["away_pts"])
        c["completed_in_scope"] += 1
        home, away, start = rec.get(keys["home"]), rec.get(keys["away"]), parse_start(rec.get(keys["start"]))
        desc = _desc(rec, keys)
        in_scope.append((rec, desc))
        if not home or not away or start is None:
            c["source_unusable_row"] += 1
            why_not[id(rec)] = "unusable source row (no team or start date)"
            continue
        nv = rec.get(keys["neutral"])
        neutral = None if nv is None else bool(nv)
        (hn, h_alias), (an, a_alias) = resolve(home), resolve(away)
        status, m, orient, tier, fp_note = join_one(hn, an, start, ours, dates, hp, ap)
        if status == "ambiguous":
            c["ambiguous_refused"] += 1
            r.ambiguous.append(f"{desc} — more than one of our games fits ({tier} tier); refused, never guessed")
            why_not[id(rec)] = f"ambiguous ({tier} tier), refused"
            continue
        if status == "unmatched":
            if fp_note:
                c["first_pass_substring_to_retry"] += 1      # J5: no clean substring join -> the retry
            pending.append((rec, home, away, hn, an, start, hp, ap, neutral, desc, fp_note))
            continue
        oh, oa = (int(hp), int(ap)) if orient == "same" else (int(ap), int(hp))   # source, OUR orientation
        via = "alias" if (h_alias or a_alias) else tier
        by_target.setdefault(m.id, []).append(make_row(rec, m, orient, via, desc, neutral, oh, oa))

    joined_first = set(by_target)                             # "that match is not already joined"
    for rec, home, away, hn, an, start, hp, ap, neutral, desc, fp_note in pending:
        status, m, orient, note = dateshift_retry(hn, an, start, hp, ap, ours, dates, joined_first)
        note = "; ".join(x for x in (fp_note, note) if x)
        if status == "joined":
            oh, oa = (int(hp), int(ap)) if orient == "same" else (int(ap), int(hp))
            row = make_row(rec, m, orient, "dateshift", desc, neutral, oh, oa)
            row["_dateshift"] = note
            by_target.setdefault(m.id, []).append(row)
            continue
        c["unmatched"] += 1
        if status != "no_fit":
            c[f"dateshift_{status}"] += 1
        r.unmatched.append(desc + (f" — {note}" if note else ""))
        why_not[id(rec)] = "unmatched" + (f" ({note})" if note else "")
        if hn in our_norms and an in our_norms:
            c["unmatched_both_names_known"] += 1             # a date / missing-game gap, not a name gap
        for name, n in ((home, hn), (away, an)):
            if n not in our_norms:
                r.unmatched_names[name] += 1

    for mid, rows in by_target.items():
        if len(rows) > 1:
            c["duplicate_target_refused"] += len(rows)
            for x in rows:
                r.ambiguous.append(f"{x['_desc']} — {len(rows)} CFBD games join our match {mid}; all refused")
                why_not[x["_rec"]] = f"{len(rows)} CFBD games join our match {mid}; all refused"
            continue
        row = rows[0]
        c["joined"] += 1
        c[f"joined_{row['orientation']}"] += 1
        c[f"join_via_{row['join_via']}"] += 1
        c[row["_kind"]] += 1
        if row.get("_dateshift"):
            r.dateshift.append(f"match {mid} · {row['_desc']} · {row['_dateshift']}")
        if row["neutral"]:
            c["neutral"] += 1
        elif row["neutral"] is None:
            c["neutral_unknown"] += 1
        if row["correction_reason"]:
            r.corrections.append(f"match {mid} · {row['_desc']} · {row['correction_reason']}")
        if row["_our_season"] != row["season"]:
            c["season_disagree"] += 1
            r.season_disagree.append(f"match {mid} · {row['_desc']} · our season {row['_our_season']!r} "
                                     f"vs CFBD year {row['season']}")
        r.rows.append({k: v for k, v in row.items() if not k.startswith("_")})
    r.unlabelled = [f"{desc} — {why_not[id(rec)]}" for rec, desc in in_scope if id(rec) in why_not]
    return r


def fbs_coverage(in_scope: int, labelled: int) -> dict:
    """SCOPE (ARCHITECT 2026-10-08, verbatim): "the side table labels at least
    95% of CFBD's completed both-FBS games in each season used, read from the
    ingest receipt (joined over in scope), every unmatched game listed."
    The denominator is CFBD's completed in-scope games, NOT our stream (the
    2026-10-07 build divided by every kept stream game, all divisions)."""
    share = (labelled / in_scope) if in_scope else None
    return {"in_scope": in_scope, "labelled": labelled, "share": share,
            "ok": bool(in_scope) and labelled / in_scope >= COVERAGE_MIN - 1e-12}


# The migration marker (Codex on #333). NCAACFBDLabel is mapped in
# Base.metadata, so ANY init_db() (create_all, run by many scheduled commands)
# creates an empty ncaa_cfbd_labels; the table's existence therefore does not
# prove the backed-up migration ran. migrate_ncaa_cfbd_labels.py, and nothing
# else, creates this one-row table by Core SQL (it is deliberately NOT mapped in
# the ORM: the migrate_kalshi_ticker.py convention, so create_all can never
# make it), and the ingest writes only when both exist.
MIGRATION_MARKER = "ncaa_cfbd_labels_migration"


def has_table(s) -> bool:
    from sqlalchemy import inspect
    try:
        return inspect(s.connection()).has_table("ncaa_cfbd_labels")
    except Exception:
        return False


def migrated(s) -> bool:
    """True only when migrate_ncaa_cfbd_labels.py ran: the side table exists AND
    the marker table it alone writes holds its row. An init_db()-created table
    without the marker is NOT migrated (the ingest refuses a non-dry run)."""
    from sqlalchemy import inspect, text
    try:
        if not (has_table(s) and inspect(s.connection()).has_table(MIGRATION_MARKER)):
            return False
        return bool(s.execute(text(f"SELECT COUNT(*) FROM {MIGRATION_MARKER}")).scalar())
    except Exception:
        return False


SEASON_TYPE_COLUMN = "season_type"      # J4 (ARCHITECT 2026-10-08): migrate_ncaa_cfbd_v2.py adds it


def has_season_type(s) -> bool:
    """True when ncaa_cfbd_labels.season_type exists (J4's migration ran, or the
    table was created from the current ORM, which carries the column)."""
    from sqlalchemy import inspect
    try:
        return SEASON_TYPE_COLUMN in {c["name"] for c in inspect(s.connection()).get_columns("ncaa_cfbd_labels")}
    except Exception:
        return False


def label_load_options(s) -> list:
    """ORM load options for reading NCAACFBDLabel on a DB that may predate J4's
    migration: without the column, every other column is loaded and season_type
    is never selected (readers use getattr(row, 'season_type', None) only when
    it exists). Readers never fail on an un-migrated laptop."""
    if has_season_type(s):
        return []
    from sqlalchemy.orm import load_only

    from src.db.schema import NCAACFBDLabel
    return [load_only(*[getattr(NCAACFBDLabel, c.key) for c in NCAACFBDLabel.__table__.columns
                        if c.key != SEASON_TYPE_COLUMN])]


LABEL_FIELDS = ("source", "source_game_id", "season", "orientation", "neutral", "home_score", "away_score",
                "source_home_team", "source_away_team", "join_via", "correction_reason", "season_type")


def upsert(s, rows: list[dict], fetched_at: datetime, payload_file: str | None) -> Counter:
    """Insert or update ncaa_cfbd_labels by match id. Never deletes; never touches matches."""
    from src.db.schema import NCAACFBDLabel
    from src.timeutil import utc_now_naive

    out = Counter()
    now = utc_now_naive()
    for row in rows:
        cur = s.get(NCAACFBDLabel, row["match_id"])
        if cur is None:
            s.add(NCAACFBDLabel(**row, payload_file=payload_file, fetched_at=fetched_at, updated_at=now))
            out["inserted"] += 1
            continue
        if all(getattr(cur, k) == row[k] for k in LABEL_FIELDS):
            out["unchanged"] += 1
        else:
            out["updated"] += 1
        for k in LABEL_FIELDS:
            setattr(cur, k, row[k])
        cur.payload_file, cur.fetched_at, cur.updated_at = payload_file, fetched_at, now
    s.flush()
    return out


# --------------------------------------------------------------------------
# Orchestration (the CLI calls this)
# --------------------------------------------------------------------------


def _records_for(year: int, from_file: str | None, years: list[int]):
    if "{year}" in from_file:
        path = from_file.replace("{year}", str(year))
    elif len(years) == 1:
        path = from_file
    else:
        raise CFBDError("REFUSED: one --from-file for several --year values must contain '{year}' "
                        "(e.g. exports/cfbd/cfbd_games_{year}_<stamp>.json)")
    try:
        recs = json.load(open(path))
    except (OSError, ValueError) as e:
        raise CFBDError(f"REFUSED: --from-file {path} unreadable ({e})")
    if not isinstance(recs, list):
        raise CFBDError(f"REFUSED: --from-file {path} is not a JSON list of games")
    return recs, Path(path)


def run(years: list[int], from_file: str | None = None, dry_run: bool = False, save_dir: str | None = None,
        division: str = "fbs", alias_path: Path | str | None = None, out=print, limit: int = SAMPLE,
        unmatched_names: bool = False, base: str = BASE) -> int:
    """Fetch (or replay), join, upsert, receipt. Returns an exit code."""
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import NCAACFBDLabel
    from src.timeutil import utc_now_naive

    aliases = load_aliases(alias_path or ALIAS_FILE)
    div = (division or "").lower() or None
    if not dry_run and div != SCOPE_DIVISION:
        raise CFBDError(f"REFUSED: a non-dry ingest runs only with division {SCOPE_DIVISION} (L4, ARCHITECT "
                        f"2026-10-08: \"Any other division is a dry run or a refusal.\"); got {division!r} — add "
                        "--dry-run to read another division")
    if save_dir:
        refuse_save_path(save_dir)
    key = None
    if not from_file:
        key = api_key()
        if not key:
            raise CFBDError(f"REFUSED: no {KEY_ENV} in .env (never committed, never printed)")
    out(f"NCAA-CFBD-LABELS (ARCHITECT 2026-10-07, data lane){' · DRY RUN: nothing written' if dry_run else ''}"
        f" · source CollegeFootballData · {'replay ' + from_file if from_file else 'API'} · "
        f"division {division or 'all'} · pinned aliases {len(aliases)}")
    with session_scope() as s:
        ready = migrated(s)
        v2_ready = ready and v2_migrated(s)
        s.rollback()
    if not ready and not dry_run:
        raise CFBDError("REFUSED: ncaa_cfbd_labels is not migrated (no migration marker "
                        f"{MIGRATION_MARKER}; an init_db()-created table does not count) — take the .backup, "
                        "then run `python migrate_ncaa_cfbd_labels.py` (a --dry-run works without it)")
    if not v2_ready and not dry_run:
        raise CFBDError(f"REFUSED: the v2 migration has not run (ncaa_cfbd_labels.season_type (J4) and/or "
                        f"{RECORD_TABLE} (L1) missing, or no migration marker {V2_MIGRATION_MARKER}; an "
                        "init_db()-created table or column does not count) — take the .backup, then run "
                        "`python migrate_ncaa_cfbd_v2.py` (a --dry-run works without it)")
    rc = 0
    for year in years:
        fetched_at = utc_now_naive()
        if from_file:
            recs, src_path = _records_for(year, from_file, years)
            status, hdr, saved = "file", {}, src_path
        else:
            try:
                status, recs, hdr = fetch(year, key, base, division)   # '' = all: no classification sent
            except Exception as e:                      # the key is never in the message
                out(f"\n== {year}: fetch failed: {type(e).__name__}: {str(e)[:200].replace(key, '[REDACTED]')}")
                rc = 1
                continue
            saved = None if dry_run else save_payload(recs, year, save_dir)
        out(f"\n== {year} · HTTP {status} · {len(recs)} records"
            + (f" · rate-limit headers {json.dumps(hdr)}" if hdr else "")
            + (f" · payload saved {payload_label(saved)}" if saved and not from_file else "")
            + (" · payload NOT saved (dry run)" if dry_run and not from_file else ""))
        pf = payload_label(saved) if saved else None
        if not recs:
            if not dry_run:
                with session_scope() as s:
                    write_record(s, year, None, 0, fetched_at, pf, div)
                out(f"  INGEST RECORD {year} written ({RECORD_TABLE}): 0 records · in scope 0 · joined 0")
            continue
        keys, missing = discover(recs[0])
        if div:                                     # Codex P1 on #365: a division-filtered (fbs) ingest needs
            missing += [n for n in ("home_class", "away_class") if not keys.get(n)]   # both classification fields
        out("  keys used (law-1 receipt): " + " · ".join(f"{n}<-{k}" for n, k in keys.items() if k))
        if missing:
            out(f"  REFUSED: required field(s) not found: {', '.join(missing)} · first record keys: "
                + ", ".join(sorted(recs[0]))[:600])
            if not dry_run:
                with session_scope() as s:
                    write_record(s, year, None, len(recs), fetched_at, pf, div)
            rc = 2
            continue
        starts = [d for d in (parse_start(x.get(keys["start"])) for x in recs) if d is not None]
        with session_scope() as s:
            teams = ncaa_teams(s)
            ours = load_ours(s, min(starts), max(starts), teams) if starts else []
            res = build_labels(recs, keys, ours, teams, aliases, year, div)
            if dry_run:
                wrote = None
                s.rollback()
            else:
                wrote = upsert(s, res.rows, fetched_at, pf)
                write_record(s, year, res, len(recs), fetched_at, pf, div)   # L1: zero joins included
                stored = s.execute(select(func.count()).select_from(NCAACFBDLabel)
                                   .where(NCAACFBDLabel.season == str(year))).scalar_one()
                stale = s.execute(select(func.count()).select_from(NCAACFBDLabel).where(
                    NCAACFBDLabel.season == str(year),
                    NCAACFBDLabel.match_id.notin_([x["match_id"] for x in res.rows]))).scalar_one()
        for line in receipt_lines(res, limit=limit, unmatched_names=unmatched_names):
            out(line)
        if wrote is not None:
            out(f"  WRITTEN ncaa_cfbd_labels: inserted {wrote['inserted']} · updated {wrote['updated']} · "
                f"unchanged {wrote['unchanged']} · rows for {year} now {stored} (matches table untouched)"
                + (f" · {stale} earlier row(s) not re-joined this run, KEPT as STALE (L3: counted and listed, "
                   f"never walked)" if stale else ""))
            out(f"  INGEST RECORD {year} written ({RECORD_TABLE}): records {len(recs)} · in scope "
                f"{res.counts['completed_in_scope']} · joined {res.counts['joined']} · division {div} · "
                f"fetched_at {fetched_at.isoformat(sep=' ')}")
    out("\nNext: `python cli.py ncaa-cfbd-coverage` (the coverage fact per season = its latest ingest record; the "
        "gate stays SUSPENDED until the architect reads it).")
    return rc


def receipt_lines(r: YearResult, limit: int = SAMPLE, unmatched_names: bool = False) -> list[str]:
    c = r.counts
    scope = c["completed_in_scope"]
    j = c["joined"]
    pct = (lambda n, d: f"{100 * n / d:.1f}%" if d else "—")
    filtered = " · ".join(f"{k} {v}" for k, v in sorted(c.items()) if k.startswith("source_")) or "none"
    L = [f"  RECEIPT {r.year}: records {c['records']} · {r.scope_label} completed {scope} · joined {j} "
         f"({pct(j, scope)}) · same {c['joined_same']} · swapped {c['joined_swapped']} "
         f"({pct(c['joined_swapped'], j)} of joined) · neutral {c['neutral']}"
         + (f" (unknown {c['neutral_unknown']})" if c["neutral_unknown"] else "")
         + f" · score-reversed {c['score_reversed']} · score-disagree {c['score_disagree']}"
         f" · unmatched {c['unmatched']} · ambiguous-refused {c['ambiguous_refused']}"
         + (f" · duplicate-target-refused {c['duplicate_target_refused']}" if c["duplicate_target_refused"] else ""),
         f"    filtered out: {filtered}",
         f"    joined via: exact {c['join_via_exact']} · substring {c['join_via_substring']} · alias "
         f"{c['join_via_alias']} · dateshift {c['join_via_dateshift']} · scores agree {c['score_agree']} · "
         f"ours unscored {c['ours_no_score']} · our season differs from the CFBD year {c['season_disagree']}",
         f"    aliases: usable {r.aliases_usable} · refused {len(r.alias_refused)}"]
    for src, tgt, why in r.alias_refused:
        L.append(f"      REFUSED alias {src!r} -> {tgt!r}: {why}")
    cov = fbs_coverage(scope, j)
    L.insert(1, f"    COVERAGE (SCOPE, ARCHITECT 2026-10-08): labelled {j} / CFBD completed {r.scope_label} {scope} "
                f"= {pct(j, scope)} · >= {COVERAGE_MIN:.0%}: {'YES' if cov['ok'] else 'NO'} (joined over in scope; "
                f"every unlabelled game listed below)")
    L.append(f"    J2 our names changed by html.unescape (join + alias vetting): {len(r.escaped)}")
    L += [f"      team {tid}: {n!r} -> {u!r}" for tid, n, u in r.escaped]
    L.append(f"    DATESHIFT rows (J1, ±{DATESHIFT_HOURS}h retry of first-pass unmatched; both kickoffs, offset): "
             f"{len(r.dateshift)} · retry refused: score-disagree {c['dateshift_score_disagree']} · already-joined "
             f"{c['dateshift_already_joined']} · ambiguous {c['dateshift_ambiguous']} (listed under unmatched)")
    L += [f"      {x}" for x in r.dateshift]
    if r.corrections:
        L.append(f"    SCORE-CORRECTED rows ({len(r.corrections)}; the side table carries CFBD's scores):")
        L += [f"      {x}" for x in r.corrections]
    if r.ambiguous:
        L.append(f"    REFUSED ({len(r.ambiguous)}):")
        L += [f"      {x}" for x in r.ambiguous]
    if r.season_disagree:
        L.append("    season label differs (written; information):")
        L += [f"      {x}" for x in r.season_disagree[:limit]]
    if r.unmatched:
        L.append(f"    unmatched games ({len(r.unmatched)}, every one; both names known to us, i.e. a date / "
                 f"missing-game gap: {c['unmatched_both_names_known']}):")
        L += [f"      {x}" for x in r.unmatched]
    if r.unlabelled:
        L.append(f"    UNLABELLED in-scope games ({len(r.unlabelled)}, every one: the coverage gap):")
        L += [f"      {x}" for x in r.unlabelled]
    names = r.unmatched_names.most_common()
    shown = names if unmatched_names else names[:limit]
    L.append(f"    UNMATCHED SOURCE NAMES with no exact match among our NCAA teams: {len(names)} "
             f"(alias candidates for a reviewed PR; never auto-mapped)"
             + ("" if unmatched_names or len(names) <= limit else f" — first {limit}; --unmatched-names lists all"))
    L += [f"      {n:>4}  {name}" for name, n in shown]
    return L


# --------------------------------------------------------------------------
# The ingest record and the label set (ARCHITECT 2026-10-08, addendum 11, L1-L4)
# --------------------------------------------------------------------------

# LABEL SET, RULED (verbatim): "L1. Every non-dry ingest writes one ingest
# record per season to a new table with its own additive migrate script:
# season, division, fetched_at, payload_file, records, in scope, joined, and
# the unlabelled games as the receipt lists them. A run that joins nothing still
# writes its record. L2. The coverage fact is the season's latest ingest
# record: joined over in scope, at least 95%. ncaa-cfbd-coverage and the
# shadow's precondition read that record and never open the payload file. A
# season with no record is not covered. L3. A label is current when its
# fetched_at equals that of its season's latest ingest record. The v1r stream
# and the shadow's FBS team set read current labels only. A stale label is
# kept, counted and listed, never walked. A season whose current labels do not
# number its record's joined count is not covered. L4. A non-dry ingest runs
# only with division fbs. Any other division is a dry run or a refusal."
RECORD_TABLE = "ncaa_cfbd_ingest_records"
SCOPE_DIVISION = "fbs"          # L4 / the SCOPE ruling's "both-FBS"


def records_ready(s) -> bool:
    """True when the records table EXISTS (readers: an init_db()-created table is empty, so it reads as "no
    ingest record"). The ingest's write gate is v2_migrated(), which also requires the v2 marker (#367)."""
    from sqlalchemy import inspect
    try:
        return inspect(s.connection()).has_table(RECORD_TABLE)
    except Exception:
        return False


# The v2 migration marker (#367, Codex P2 on #362; ARCHITECT 2026-10-08 addendum 13 item 1). Same reason and
# same convention as MIGRATION_MARKER: NCAACFBDIngestRecord is mapped, so any init_db() creates
# ncaa_cfbd_ingest_records, and a table created from the current ORM also carries season_type; neither object's
# existence proves migrate_ncaa_cfbd_v2.py (the post-backup migration) ran. That script, and nothing else,
# creates this one-row table by Core SQL (unmapped, so create_all can never make it). Its own table rather than
# a second row in MIGRATION_MARKER: that table's id is CHECK (id = 1), and one marker per script keeps each
# readable on its own.
V2_MIGRATION_MARKER = "ncaa_cfbd_v2_migration"


def v2_migrated(s) -> bool:
    """True only when migrate_ncaa_cfbd_v2.py ran: ncaa_cfbd_labels.season_type and the records table exist
    AND the marker table that script alone writes holds its row. An init_db()-created table and column
    without the marker is NOT migrated (the ingest refuses a non-dry run)."""
    from sqlalchemy import inspect, text
    try:
        if not (has_season_type(s) and records_ready(s)
                and inspect(s.connection()).has_table(V2_MIGRATION_MARKER)):
            return False
        return bool(s.execute(text(f"SELECT COUNT(*) FROM {V2_MIGRATION_MARKER}")).scalar())
    except Exception:
        return False


def write_record(s, year: int, res: YearResult | None, records: int, fetched_at: datetime,
                 payload_file: str | None, division: str | None) -> None:
    """L1: append this run's ingest record for `year` (never updates or deletes one). `fetched_at` is the
    run's own, the same stamp upsert() puts on every label it writes or updates (L3). `res` None = an empty
    payload or a refused one: in scope 0, joined 0."""
    from src.db.schema import NCAACFBDIngestRecord

    c = res.counts if res else Counter()
    s.add(NCAACFBDIngestRecord(season=str(year), division=division or "", fetched_at=fetched_at,
                               payload_file=payload_file, records=records, in_scope=c["completed_in_scope"],
                               joined=c["joined"], unlabelled=list(res.unlabelled) if res else []))
    s.flush()


def latest_records(s, seasons=None) -> dict:
    """{season: its latest NCAACFBDIngestRecord} (by fetched_at, then id); every season with one when
    `seasons` is None. Read-only."""
    from sqlalchemy import select

    from src.db.schema import NCAACFBDIngestRecord

    if not records_ready(s):
        return {}
    q = select(NCAACFBDIngestRecord)
    if seasons is not None:
        q = q.where(NCAACFBDIngestRecord.season.in_([str(x) for x in seasons]))
    out = {}
    for r_ in s.execute(q.order_by(NCAACFBDIngestRecord.fetched_at, NCAACFBDIngestRecord.id)).scalars():
        out[r_.season] = r_
    return out


def latest_record_stamps(s, seasons=None) -> dict[str, datetime]:
    """L3: {CFBD season: the fetched_at of its latest ingest record}. A label is CURRENT exactly when its
    fetched_at equals its season's stamp here; a season with no record has no current label."""
    return {season: r_.fetched_at for season, r_ in latest_records(s, seasons).items()}


def current_label_counts(s, stamps: dict[str, datetime]) -> dict[str, int]:
    """{season: how many side-table labels are current (fetched_at == the season's latest record's)}."""
    from sqlalchemy import func, select

    from src.db.schema import NCAACFBDLabel

    out = {}
    for season, at in stamps.items():
        out[season] = s.execute(select(func.count()).select_from(NCAACFBDLabel).where(
            NCAACFBDLabel.season == season, NCAACFBDLabel.fetched_at == at)).scalar_one()
    return out


def stored_coverage(s, seasons) -> dict[str, dict]:
    """L2 + L3: the coverage fact per season = its LATEST ingest record (joined over in scope, at least 95%),
    every unlabelled game as the record lists it. Never opens the payload file. Not covered when: no record;
    or the season's current labels do not number the record's joined count. Read-only."""
    rec = latest_records(s, seasons)
    stamps = {k: v.fetched_at for k, v in rec.items()}
    current = current_label_counts(s, stamps) if has_table(s) else {}
    out: dict[str, dict] = {}
    for season in (str(x) for x in seasons):
        r_ = rec.get(season)
        if r_ is None:
            out[season] = {"season": season, "payload": None, "fetched_at": None, "current": 0, "unlabelled": [],
                           "reason": "no ingest record for this season (L2: not covered)", **fbs_coverage(0, 0)}
            continue
        cov = fbs_coverage(r_.in_scope, r_.joined)
        n_cur = current.get(season, 0)
        reason = None
        if n_cur != r_.joined:
            reason = (f"current labels {n_cur} do not number the record's joined count {r_.joined} "
                      "(L3: not covered)")
            cov["ok"] = False
        out[season] = {"season": season, "payload": r_.payload_file, "fetched_at": r_.fetched_at,
                       "current": n_cur, "unlabelled": list(r_.unlabelled or []), "reason": reason, **cov}
    return out


def stored_coverage_lines(cov: dict[str, dict]) -> list[str]:
    L = []
    for season, c in cov.items():
        share = "—" if c["share"] is None else f"{100 * c['share']:.1f}%"
        L.append(f"  {season}: labelled {c['labelled']} / CFBD completed both-FBS {c['in_scope']} = {share} · "
                 f">= {COVERAGE_MIN:.0%}: {'YES' if c['ok'] else 'NO'}"
                 + (f" · current labels {c['current']} · record fetched_at {c['fetched_at']}"
                    if c.get("fetched_at") else "")
                 + (f" · payload {c['payload']}" if c["payload"] else "")
                 + (f" · NOT COVERED: {c['reason']}" if c["reason"] else ""))
        if c["unlabelled"]:
            L.append(f"    unlabelled ({len(c['unlabelled'])}, every one):")
            L += [f"      {x}" for x in c["unlabelled"]]
    return L
