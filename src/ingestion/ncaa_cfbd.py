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
"""
from __future__ import annotations

import bisect
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


def vet_aliases(aliases: dict[str, str], teams: dict[int, str]) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """(usable {source name: our team name}, refused [(source, target, reason)]).
    `teams` = our NCAA teams {id: name}. An alias is usable only if its target
    normalizes to EXACTLY ONE of our teams, and its source name does not
    already match one of ours exactly (an alias never overrides an exact match)."""
    from src.ingestion.match_lookup import normalize_team_name as norm

    by_norm: dict[str, list[int]] = {}
    for tid, name in teams.items():
        by_norm.setdefault(norm(name), []).append(tid)
    ok, refused = {}, []
    for src, tgt in sorted(aliases.items()):
        if norm(src) in by_norm:
            refused.append((src, tgt, "shadowed: the source name already matches one of our teams exactly "
                                      "(an alias never overrides an exact match)"))
            continue
        hits = by_norm.get(norm(tgt), [])
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
    """OUR NCAA matches kicking off in [start-12h, end+12h], the shared matcher's
    status rule (CANCELLED / STALE_ORPHAN never join). Prefetched once (no
    per-record query). Read-only."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, Sport
    from src.ingestion.match_lookup import normalize_team_name as norm

    tol = timedelta(hours=TOLERANCE_HOURS)
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


def join_one(home_n: str, away_n: str, start: datetime, ours: list[Ours], dates: list[datetime]):
    """('joined', Ours, orientation, tier) | ('ambiguous', None, None, tier) | ('unmatched', ...)."""
    if not home_n or not away_n:
        return "unmatched", None, None, None
    tol = timedelta(hours=TOLERANCE_HOURS)
    lo, hi = bisect.bisect_left(dates, start - tol), bisect.bisect_right(dates, start + tol)
    cands = ours[lo:hi]
    for tier in ("exact", "substring"):
        hits = []
        for m in cands:
            if _fits(tier, home_n, m.home_norm) and _fits(tier, away_n, m.away_norm):
                hits.append((m, "same"))
            if _fits(tier, away_n, m.home_norm) and _fits(tier, home_n, m.away_norm):
                hits.append((m, "swapped"))
        if len(hits) == 1:
            return "joined", hits[0][0], hits[0][1], tier
        if len(hits) > 1:
            return "ambiguous", None, None, tier
    return "unmatched", None, None, None


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


def build_labels(records: list, keys: dict, ours: list[Ours], teams: dict[int, str],
                 aliases: dict[str, str], year: int, division: str | None = "fbs") -> YearResult:
    """Pure over its inputs: no DB, no network. Returns the rows to upsert and the receipt."""
    from src.ingestion.match_lookup import normalize_team_name as norm

    r = YearResult(year, scope_label=f"both-{division.upper()}" if division else "all")
    usable, r.alias_refused = vet_aliases(aliases, teams)
    r.aliases_usable = len(usable)
    our_norms = {norm(n) for n in teams.values()}
    dates = [m.utc_date for m in ours]
    c = r.counts
    c["records"] = len(records)

    def resolve(name: str) -> tuple[str, bool]:
        n = norm(name)
        if n in our_norms:
            return n, False                                   # exact wins; an alias never overrides it
        if name in usable:
            return norm(usable[name]), True
        return n, False

    by_target: dict[int, list[dict]] = {}
    for rec in records:
        if keys["completed"] and rec.get(keys["completed"]) is False:
            c["source_not_completed"] += 1
            continue
        hp, ap = rec.get(keys["home_pts"]), rec.get(keys["away_pts"])
        if hp is None or ap is None:
            c["source_no_score"] += 1
            continue
        if division and keys["home_class"] and keys["away_class"] and \
                (str(rec.get(keys["home_class"]) or "").lower() != division
                 or str(rec.get(keys["away_class"]) or "").lower() != division):
            c[f"source_not_both_{division}"] += 1
            continue
        c["completed_in_scope"] += 1
        home, away, start = rec.get(keys["home"]), rec.get(keys["away"]), parse_start(rec.get(keys["start"]))
        if not home or not away or start is None:
            c["source_unusable_row"] += 1
            continue
        nv = rec.get(keys["neutral"])
        neutral = None if nv is None else bool(nv)
        (hn, h_alias), (an, a_alias) = resolve(home), resolve(away)
        status, m, orient, tier = join_one(hn, an, start, ours, dates)
        desc = f"{start:%Y-%m-%d} {away} @ {home}" + (" (neutral)" if neutral else "")
        if status == "ambiguous":
            c["ambiguous_refused"] += 1
            r.ambiguous.append(f"{desc} — more than one of our games fits ({tier} tier); refused, never guessed")
            continue
        if status == "unmatched":
            c["unmatched"] += 1
            r.unmatched.append(desc)
            if hn in our_norms and an in our_norms:
                c["unmatched_both_names_known"] += 1             # a date / missing-game gap, not a name gap
            for name, n in ((home, hn), (away, an)):
                if n not in our_norms:
                    r.unmatched_names[name] += 1
            continue
        oh, oa = (int(hp), int(ap)) if orient == "same" else (int(ap), int(hp))   # source, OUR orientation
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
        via = "alias" if (h_alias or a_alias) else tier
        sid = rec.get(keys["id"]) if keys["id"] else None
        row = {"match_id": m.id, "source": SOURCE, "source_game_id": int(sid) if isinstance(sid, int) else None,
               "season": str(year), "orientation": orient, "neutral": neutral, "home_score": oh, "away_score": oa,
               "source_home_team": home, "source_away_team": away, "join_via": via, "correction_reason": reason,
               "_kind": kind, "_desc": desc, "_our_season": m.season}
        by_target.setdefault(m.id, []).append(row)

    for mid, rows in by_target.items():
        if len(rows) > 1:
            c["duplicate_target_refused"] += len(rows)
            for x in rows:
                r.ambiguous.append(f"{x['_desc']} — {len(rows)} CFBD games join our match {mid}; all refused")
            continue
        row = rows[0]
        c["joined"] += 1
        c[f"joined_{row['orientation']}"] += 1
        c[f"join_via_{row['join_via']}"] += 1
        c[row["_kind"]] += 1
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
    return r


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


LABEL_FIELDS = ("source", "source_game_id", "season", "orientation", "neutral", "home_score", "away_score",
                "source_home_team", "source_away_team", "join_via", "correction_reason")


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
        s.rollback()
    if not ready and not dry_run:
        raise CFBDError("REFUSED: ncaa_cfbd_labels is not migrated (no migration marker "
                        f"{MIGRATION_MARKER}; an init_db()-created table does not count) — take the .backup, "
                        "then run `python migrate_ncaa_cfbd_labels.py` (a --dry-run works without it)")
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
        if not recs:
            continue
        keys, missing = discover(recs[0])
        out("  keys used (law-1 receipt): " + " · ".join(f"{n}<-{k}" for n, k in keys.items() if k))
        if missing:
            out(f"  REFUSED: required field(s) not found: {', '.join(missing)} · first record keys: "
                + ", ".join(sorted(recs[0]))[:600])
            rc = 2
            continue
        starts = [d for d in (parse_start(x.get(keys["start"])) for x in recs) if d is not None]
        with session_scope() as s:
            teams = ncaa_teams(s)
            ours = load_ours(s, min(starts), max(starts), teams) if starts else []
            res = build_labels(recs, keys, ours, teams, aliases, year, (division or "").lower() or None)
            if dry_run:
                wrote = None
                s.rollback()
            else:
                wrote = upsert(s, res.rows, fetched_at, payload_label(saved) if saved else None)
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
                + (f" · {stale} earlier row(s) not re-joined this run, KEPT (the ingest never deletes)"
                   if stale else ""))
    out("\nNext: `python cli.py ncaa-cfbd-coverage` (coverage per season; the gate stays SUSPENDED until "
        "the architect reads it).")
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
         f"{c['join_via_alias']} · scores agree {c['score_agree']} · ours unscored {c['ours_no_score']}"
         f" · our season differs from the CFBD year {c['season_disagree']}",
         f"    aliases: usable {r.aliases_usable} · refused {len(r.alias_refused)}"]
    for src, tgt, why in r.alias_refused:
        L.append(f"      REFUSED alias {src!r} -> {tgt!r}: {why}")
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
        L.append(f"    unmatched games ({len(r.unmatched)}{'; first ' + str(limit) if len(r.unmatched) > limit else ''}"
                 f"; both names known to us, i.e. a date / missing-game gap: {c['unmatched_both_names_known']}):")
        L += [f"      {x}" for x in r.unmatched[:limit]]
    names = r.unmatched_names.most_common()
    shown = names if unmatched_names else names[:limit]
    L.append(f"    UNMATCHED SOURCE NAMES with no exact match among our NCAA teams: {len(names)} "
             f"(alias candidates for a reviewed PR; never auto-mapped)"
             + ("" if unmatched_names or len(names) <= limit else f" — first {limit}; --unmatched-names lists all"))
    L += [f"      {n:>4}  {name}" for name, n in shown]
    return L
