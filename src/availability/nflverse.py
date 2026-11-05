"""
THE NFLVERSE DEPTH-CHART FEED (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(a); 259 item 2; lane
availability-record): the adapter and ingest of source `nflverse_depth_charts` into the availability record.

Item 3(a), verbatim in part: "nflverse DEPTH CHARTS (source `nflverse_depth_charts`): the release file for the season
(github.com/nflverse/nflverse-data, release tag depth_charts, the 2025+ format: dt, team, player_name, espn_id, gsis_id,
pos_grp_id, pos_grp, pos_id, pos_name, pos_abb, pos_slot, pos_rank — the dictionary as published; the 2023–2024 weekly
files are a DIFFERENT shape and are NOT ingested by this feed [...]). Each fetch is one observation; its NEW rows (dt
later than the newest source_stamp we hold for the source) become assertions of kind depth_rank (attrs: pos_grp,
pos_abb, pos_slot, pos_rank), one per player-slot; the fetch's payload sha256 is kept, and a fetch whose file is
byte-identical to the last is a `complete` observation with rows_asserted 0. [...] A QB1 from this feed is a DAILY RANK,
not a game-day confirmation (the report's own limit): kind depth_rank says so; nothing here writes projected_starter."

    python cli.py availability-nflverse [--season 2026] [--file PATH]

How it reads and writes (law 1: every column by its name, as 259 item 1 read the real files):
- THE FILE: csv.DictReader by column NAME. The header must be exactly COLUMNS (the twelve, each once; their order is
  not read), else the file is REFUSED with the reason, and the 2023–2024 weekly shape (season / week / club_code ...)
  is named as such. Every row's `dt` must be an ISO-8601 instant with Z or an offset, its `team` and one of
  player_name / gsis_id / espn_id non-empty, else the file is refused naming the line (never a guessed row).
- A ROW -> ONE ASSERTION of kind depth_rank: attrs pos_grp, pos_abb, pos_slot, pos_rank VERBATIM (strings, as the file
  holds them), dt_raw (the file's dt text), espn_id and gsis_id verbatim (both ids kept; the record's VOLATILE_ATTRS,
  identity not the fact); source_stamp = dt (UTC); source_player_id = espn_id, else gsis_id where espn_id is empty
  (attrs says which: espn_id "" there). THE KEY IS ONE ID THAT DOES NOT MOVE: record.player_key keys facts and slots on
  source_player_id, so a key that switched ids when nflverse filled one in later would close the player's interval
  "slot asserted to someone else" (the same player) and open a new one: a false flip. espn_id first because the chart
  is ESPN's (its own id); a gsis_id filled in later then changes attrs only (VOLATILE_ATTRS), never the key. The
  RESIDUAL: a row with NO espn_id keyed on gsis_id (or its name) that gains an espn_id later still reads as a flip; the
  blank rate of each id on the real files is unread here (the excerpt is not in this container: the PR body's TODO).
  player_id NULL (addendum 254 item 2(3): no player table maps an NFL id today;
  every player counted unmapped); player_name verbatim; source_team = team verbatim and team_id = OUR teams.id by the
  existing NFL team mapping: the NFL competition's teams (competition_teams, competition code NFL) whose `tla` (the
  api-american-football team `code`, stored by sync-teams) equals the file's team EXACTLY; none, or more than one, is
  UNMAPPED (team_id NULL, the text beside it), counted, and makes the observation `partial` (254 item 2(7)).
- ONLY NEW ROWS: a row is asserted only when its dt is later than the newest source_stamp the record holds for the
  source (any season's file: the watermark is the source's, 252 item 3(a)); the others are read and counted, never
  asserted twice. Both seasons' files are ingested alike (259 item 2(c)); every row recorded more than the cadence
  after its dt (record.SOURCE_CADENCE_HOURS, 24) reads BACKFILLED by the record's existing rule, and is counted here.
  BECAUSE THE WATERMARK IS THE SOURCE'S, the 2025 file is read BEFORE the first 2026 read (259 item 2(c): "2025 IS IN
  SCOPE"). A file that cannot add anything is never silent: a changed file whose newest dt is EARLIER than the
  watermark (the 2025 file after a 2026 read; an older or smaller file) is REFUSED, naming both instants (a --file: exit
  2, nothing written; a fetch: a `failed` observation, exit 1, paged); a changed file whose newest dt IS the watermark
  (nothing new) is `complete` with 0 rows and a "no new load" receipt line.
- NO LOAD FROM THE FUTURE: a row whose dt is later than our fetch's time plus FUTURE_SKEW (1 h of clock skew) refuses
  the file naming its line (a --file: exit 2, nothing written; a fetch: a `failed` observation, the file kept). One such
  stamp held would become the watermark for good (the record is append-only) and drop every real load after it as
  "older".
- THE PARTIAL-GROUP GUARD'S COUNT (259 item 2(b)): the receipt counts the new (dt, team) groups that hold fewer than
  half the rows of the team's previous complete group (record.guard_load, the rule derive() closes by), the previous
  complete groups read from the store's own loads first.
- THE FETCH (259 item 2(e)): GET RELEASE_URL for the season, redirects followed, explicit timeouts (TIMEOUT), If-None-
  Match with the ETag stored for the last kept payload of the same endpoint. The ETag is stored BESIDE THE PAYLOAD FILE
  (`<payload>.etag`): no column of availability_observations holds a validator (the endpoint, http_status,
  payload_sha256, payload_path and error columns each mean something else), and no column or table is added.
  - 304: a `complete` observation, rows_asserted 0, carrying the previous payload's sha256 and path;
  - 200: the body streamed to disk and hashed; byte-identical to the last kept payload: the copy removed, a `complete`
    observation with rows_asserted 0 carrying that payload's sha256 and path, and the answer's ETag, where it differs
    from the stored one, written beside that payload (the sidecar is not the record: no row changes), so the next
    unchanged day sends a validator the server matches; changed: kept under
    logs/availability/nflverse_depth_charts/<UTC date>/<HHMMSS>Z-<sha256, first 16 hex>-depth_charts_<season>.csv
    (never data/, never mirrored), created EXCLUSIVELY (O_EXCL: the same bytes there are reused, other bytes refused,
    never overwritten; Codex on #841, round 1), its ETag beside it, then read;
  - a raised call, a broken stream, any other status, or a refused file: a `failed` observation, the error redacted
    (record.redact, after every URL's query string is cut: a release asset redirects to a signed URL). A 5xx or a 429
    is worded as requests words it ("503 Server Error", "429 Client Error: Too Many Requests"), so the chain's retry
    (sp_run's transient classes: connection errors, timeouts, HTTP 5xx and 429; two retries) treats it as it treats a
    connection error. Each attempt the chain makes is its own run and its own `failed` observation (a fetch that
    raised is a row, 252 item 1(a)): one chain run can write up to three.
  The endpoint string is the requested release URL (no secret is needed or sent), never the redirect's signed one.
- --file PATH: a local file (the operator's hand-carried release file; the tests) read the same way, endpoint
  "file:<its name>"; refused (exit 2, nothing written) when the header or a row is refused; kept under the payload
  directory (<HHMMSS>Z-<sha256, first 16 hex>-<its name>, exclusive) when its bytes differ from the last kept payload
  of that endpoint.
- CHECKED BEFORE ANY FILE (Codex on #841, round 1): the endpoint by the writer's own rule (record.endpoint_refusal)
  before any call, copy or file, and the kept path (record.payload_path_refusal, the name's 255 bytes) before any
  directory or file is made: a refused name (a credential-like one, "api_token=secret.csv"; one too long to keep)
  leaves nothing on disk and no row. Every row to be asserted goes through the writer's own row checks
  (record.assertion_refusal: its widths among them, player_name 128 characters, source_team and source_player_id 64)
  BEFORE a --file is copied (refused: exit 2, nothing copied, nothing written) and, on a fetched file, before the
  write (refused: a `failed` observation keeping the payload's path, the refusal its error). A store refusal after a
  payload was kept leaves no orphan either: a --file's copy made by the run is removed (exit 2); a fetch is written
  as a `failed` observation keeping the path (Codex on #841, round 1).
- THE WRITE: one record.write_observation per run (one fetch, one observation, 252 item 3(a); a retried chain step
  is another run), under the chains' DB
  lock (sp_common.sync_lock, a no-op inside a chain), the store's state read mode=ro under the same lock. A missing DB
  file or an unmigrated store is refused before any call. No update or delete path (the record's triggers stand).
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.availability import record as rec

SOURCE = "nflverse_depth_charts"
KIND = "depth_rank"
# 259 item 1: "COLUMNS, both files, exactly the dictionary's twelve" (252 item 3(a): "the 2025+ format")
COLUMNS = ("dt", "team", "player_name", "espn_id", "gsis_id", "pos_grp_id", "pos_grp", "pos_id", "pos_name", "pos_abb",
           "pos_slot", "pos_rank")
ATTR_COLUMNS = ("pos_grp", "pos_abb", "pos_slot", "pos_rank")        # 252 item 3(a): "attrs: pos_grp, pos_abb, ..."
# columns that name the 2023-2024 weekly shape (nflverse's pre-2025 depth_charts dictionary), for the refusal's reason
WEEKLY_SHAPE_HINTS = ("season", "week", "club_code", "depth_team", "game_type", "formation", "depth_position")
FIRST_SEASON = 2025                                                    # 259 item 2(c): 2025 in scope; 2023-24 not
RELEASE_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.csv"
TIMEOUT = (10, 120)                       # (connect, read) seconds: explicit (259 item 2(e)); read is per chunk
CHUNK = 1 << 20
# the clock skew a load's dt may hold past our fetch's time before the file is refused (a future stamp would hold the
# source's watermark for good: the record is append-only)
FUTURE_SKEW = timedelta(hours=1)
USER_AGENT = "sports-predictor availability-record (nflverse depth charts; CC BY 4.0)"
NFL_COMPETITION = "NFL"
ATTRIBUTION = rec.SOURCES[SOURCE]
assert ATTRIBUTION == "Depth charts: nflverse (CC BY 4.0)"
_QUERY = re.compile(r"(https?://[^\s?#'\"<>]+)\?[^\s'\"<>]*")

# where logs/availability/... lives: the checkout (the host's /opt/sports-predictor, the laptop's clone); the tests
# point it at their tmp directory
PAYLOAD_BASE = Path(__file__).resolve().parents[2]


class Refused(Exception):
    """Nothing written: the run refuses (exit 2)."""


def current_season(today: datetime | None = None) -> int:
    """The default --season: the calendar year from March on, else the year before. nflverse's season file turns over
    in March (259 item 1: the 2025 file's last load 2026-03-14T07:32:09Z, the 2026 file's first 2026-03-22)."""
    t = today or datetime.now(timezone.utc)
    return t.year if t.month >= 3 else t.year - 1


def release_url(season: int) -> str:
    return RELEASE_URL.format(season=int(season))


def season_refusal(season: int) -> str | None:
    if int(season) < FIRST_SEASON:
        return (f"REFUSED: season {season}: the 2023-2024 weekly depth-chart files are a DIFFERENT shape and are NOT "
                f"ingested by this feed (addendum 252 item 3(a); 259 item 2(c): 2025 and later only)")
    return None


# ---- the file ------------------------------------------------------------------------------------------------------

def header_refusal(fieldnames) -> str | None:
    """Why the header is not the 2025+ dictionary's twelve columns, or None (law 1: read by name, the set exact)."""
    got = list(fieldnames or [])
    if len(got) == len(COLUMNS) and set(got) == set(COLUMNS):
        return None
    missing = [c for c in COLUMNS if c not in got]
    extra = [c for c in got if c not in COLUMNS]
    dup = sorted({c for c in got if got.count(c) > 1})
    why = (f"the header is not the 2025+ depth_charts dictionary's twelve columns ({', '.join(COLUMNS)}): "
           f"missing {missing or 'none'}, unexpected {extra or 'none'}" + (f", repeated {dup}" if dup else ""))
    if any(c in got for c in WEEKLY_SHAPE_HINTS):     # said first: an observation's error keeps 256 characters
        why = ("this is the 2023-2024 weekly shape, which this feed does NOT ingest (addendum 252 item 3(a): \"a "
               "DIFFERENT shape [...] a second adapter later if a backtest wants them\"); " + why)
    return f"REFUSED: {why}"


def _instant(text: str) -> datetime | None:
    s = (text or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        return None                                   # law 4: a time with no zone is not assumed UTC
    return d.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class Parsed:
    rows: list = field(default_factory=list)          # (dt naive UTC, the row as read: name -> text)
    loads: list = field(default_factory=list)         # the distinct dt, ascending
    newest_line: int | None = None                    # the first line holding the newest dt (a refusal names it)


def read_file(path: Path) -> Parsed:
    """The file read by column name, every row checked; Refused (with the reason and line) on anything else."""
    out = Parsed()
    seen = set()
    newest = None
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        why = header_refusal(reader.fieldnames)
        if why:
            raise Refused(why)
        for row in reader:
            line = reader.line_num
            if None in row or any(v is None for v in row.values()):
                raise Refused(f"REFUSED: line {line} does not hold the twelve columns (a short or long row)")
            dt = _instant(row["dt"])
            if dt is None:
                raise Refused(f"REFUSED: line {line}: dt {row['dt']!r} is not an ISO-8601 instant with Z or an offset")
            if not row["team"].strip():
                raise Refused(f"REFUSED: line {line} names no team")
            if not (row["player_name"].strip() or row["gsis_id"].strip() or row["espn_id"].strip()):
                raise Refused(f"REFUSED: line {line} names no player (player_name, gsis_id and espn_id all empty)")
            out.rows.append((dt, row))
            seen.add(dt)
            if newest is None or dt > newest:
                newest, out.newest_line = dt, line
    out.loads = sorted(seen)
    return out


def future_refusal(parsed: Parsed, fetched_at: datetime) -> str | None:
    """Why the file holds a load from the future, or None: a dt later than our fetch's time plus FUTURE_SKEW. Such a
    stamp, once asserted, would be the source's watermark for good (append-only) and every real load after it would
    read "older"."""
    if not parsed.loads or parsed.loads[-1] <= fetched_at + FUTURE_SKEW:
        return None
    return (f"REFUSED: line {parsed.newest_line}: dt {parsed.loads[-1].isoformat(timespec='seconds')}Z is later than "
            f"our fetch ({fetched_at.isoformat(timespec='seconds')}Z) by more than "
            f"{int(FUTURE_SKEW.total_seconds() // 60)} min: a load from the future would hold the source's watermark "
            f"for good; nothing asserted")


def older_refusal(parsed: Parsed, wm: datetime | None) -> str | None:
    """Why the file cannot add anything, or None: every load EARLIER than the newest source_stamp the record holds for
    the source (the watermark is the source's, 252 item 3(a); so the 2025 file is read BEFORE the first 2026 read, 259
    item 2(c)). A file whose newest load IS the watermark is not refused (nothing new: complete, 0 rows)."""
    if wm is None or not parsed.loads or parsed.loads[-1] >= wm:
        return None
    return (f"REFUSED: every load is older than the source's watermark (newest dt "
            f"{parsed.loads[-1].isoformat(timespec='seconds')}Z < {wm.isoformat(timespec='seconds')}Z held): none "
            f"of its {len(parsed.rows)} rows can be asserted (252 item 3(a); 259 item 2(c): read the 2025 file "
            f"BEFORE the first 2026 read)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


# ---- the store (read mode=ro) ----------------------------------------------------------------------------------------

def team_map(s) -> tuple[dict, set]:
    """{tla: team id} for the NFL competition's teams whose tla is held by exactly one of them, and the tlas held by
    more than one (ambiguous: unmapped, never a guess). The existing mapping: teams.tla, the api-american-football
    team code sync-teams stores (src/adapters/api_american_football.py list_teams)."""
    from sqlalchemy import select

    from src.db.schema import Competition, CompetitionTeam, Sport, Team
    got = s.execute(select(Team.id, Team.tla).join(CompetitionTeam, CompetitionTeam.team_id == Team.id)
                    .join(Competition, Competition.id == CompetitionTeam.competition_id)
                    .where(Competition.sport == Sport.NFL, Competition.code == NFL_COMPETITION,
                           Team.tla.is_not(None)).distinct()).all()
    ids: dict = {}
    for tid, tla in got:
        ids.setdefault(tla, set()).add(tid)
    return {k: next(iter(v)) for k, v in ids.items() if len(v) == 1}, {k for k, v in ids.items() if len(v) > 1}


def watermark(s) -> datetime | None:
    """The newest source_stamp the record holds for the source (252 item 3(a): "NEW rows (dt later than the newest
    source_stamp we hold for the source)")."""
    from sqlalchemy import func, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    return s.execute(select(func.max(A.source_stamp)).join(O, O.id == A.observation_id)
                     .where(O.source == SOURCE)).scalar()


def stored_complete_groups(s) -> dict:
    """Each team's previous complete group size, from the store's own loads (the groups derive() reads as loads:
    observations that keep a payload hash), folded in dt order by record.guard_load."""
    from sqlalchemy import func, select

    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    got = s.execute(select(A.observation_id, A.source_stamp, A.source_team, func.count())
                    .join(O, O.id == A.observation_id)
                    .where(O.source == SOURCE, A.kind == KIND, O.payload_sha256.is_not(None))
                    .group_by(A.observation_id, A.source_stamp, A.source_team)
                    .order_by(A.source_stamp, A.observation_id)).all()
    last: dict = {}
    load_key, counts = None, {}
    for oid, stamp, team, n in got:
        if (oid, stamp) != load_key:
            if counts:
                rec.guard_load(counts, last)
            load_key, counts = (oid, stamp), {}
        counts[(SOURCE, ("src", team))] = n
    if counts:
        rec.guard_load(counts, last)
    return last


def previous_payload(s, endpoint: str) -> tuple[str, str] | None:
    """(sha256, payload_path) of the newest complete or partial observation of this endpoint that kept a payload."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityObservation as O
    got = s.execute(select(O.payload_sha256, O.payload_path)
                    .where(O.source == SOURCE, O.endpoint == endpoint, O.status.in_(rec.ASSERTING),
                           O.payload_sha256.is_not(None), O.payload_path.is_not(None))
                    .order_by(O.id.desc()).limit(1)).first()
    return (got[0], got[1]) if got else None


def stored_etag(payload_path: str | None) -> str | None:
    if not payload_path:
        return None
    p = PAYLOAD_BASE / (payload_path + ".etag")
    try:
        v = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return v or None


# ---- the fetch ---------------------------------------------------------------------------------------------------------

def _payload_dir(now: datetime) -> tuple[str, Path]:
    rel = "/".join((*rec.PAYLOAD_ROOT, SOURCE, now.date().isoformat()))
    return rel, PAYLOAD_BASE / rel


def _scrub(text: str) -> str:
    """Every URL's query string cut (a release asset redirects to a signed URL), then the record's redact."""
    return rec.redact(_QUERY.sub(lambda m: m.group(1) + "?[query removed]", str(text)))


@dataclass
class Got:
    """What one fetch (or one --file read) produced."""
    endpoint: str
    fetched_at: datetime
    http_status: int | None = None
    sha256: str | None = None
    payload_path: str | None = None       # relative (logs/availability/...)
    changed: bool = False                 # a new payload, kept and to be read
    error: str | None = None              # the call raised / the status was refused (failed)
    etag: str = "none"                    # the ETag line: sent/not sent, the answer
    created: bool = False                 # this run created the kept file (not an earlier run's same bytes, reused)


NAME_MAX = 255                            # bytes in one file name (Linux's NAME_MAX): a longer kept name is refused


def _kept(now: datetime, name: str, sha: str) -> tuple[str, Path]:
    """The kept payload's (relative path, absolute path): logs/availability/<source>/<UTC date>/<HHMMSS>Z-<the payload's
    sha256, first 16 hex>-<name>, so two different payloads kept in one second never share a path (Codex on #841, round
    1). Checked BEFORE any directory or file is made: the writer's payload_path rule and the file-name length; a refusal
    leaves nothing on disk. Creates nothing."""
    rel_dir, abs_dir = _payload_dir(now)
    final = f"{now:%H%M%S}Z-{sha[:16]}-{name}"
    rel = f"{rel_dir}/{final}"
    why = rec.payload_path_refusal(rel, SOURCE)
    if why:
        raise Refused(f"REFUSED: {why}; nothing kept, nothing written")
    if len(final.encode("utf-8")) > NAME_MAX:
        raise Refused(f"REFUSED: the kept payload's file name would be {len(final.encode('utf-8'))} bytes, longer than "
                      f"{NAME_MAX}; nothing kept, nothing written")
    return rel, abs_dir / final


def _retain(src: Path, final: Path, sha: str) -> bool:
    """The payload's bytes at `final`, created EXCLUSIVELY (O_EXCL: never over another file). True when written; False
    when `final` already holds exactly these bytes (its sha256 is the payload's: reused, not written again); Refused
    when it holds other bytes (the evidence there is never overwritten). A failed copy removes its partial file."""
    final.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(final, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if sha256_file(final) == sha:
            return False
        raise Refused(f"REFUSED: {final.name} already holds other bytes (sha256 {sha256_file(final)[:16]}, not "
                      f"{sha[:16]}): the kept evidence is never overwritten; nothing written") from None
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out, CHUNK)
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    return True


def status_error(code: int) -> str:
    """A non-200, non-304 answer's error, worded as requests words an HTTPError for 5xx and 429 ("503 Server Error",
    "429 Client Error: Too Many Requests"), so sp_run's retry reads them in its transient class (connection errors,
    timeouts, HTTP 5xx and 429) like a connection error; any other status is never retried."""
    if 500 <= code <= 599:
        why = f"{code} Server Error"
    elif code == 429:
        why = "429 Client Error: Too Many Requests"
    elif 400 <= code <= 499:
        why = f"{code} Client Error"
    else:
        why = "unexpected status"
    return f"HTTP {code} from the release asset (refused): {why}"


def _refresh_etag(payload_path: str, stored: str | None, new: str | None) -> str:
    """A byte-identical 200 whose ETag differs from the stored one: the new ETag written beside the kept payload (the
    sidecar is not the record; no row changes), so the next unchanged day sends a validator the server matches (259
    item 2(e): "the daily cost is one small request on an unchanged day"). Returns the receipt's ETag-line suffix."""
    if not new or new == stored:
        return ""
    try:
        (PAYLOAD_BASE / (payload_path + ".etag")).write_text(str(new) + "\n", encoding="utf-8")
    except OSError as e:
        return f"; its new ETag NOT stored ({type(e).__name__}): the next call sends the old one"
    return "; its new ETag stored beside the kept payload"


def fetch(season: int, prev: tuple[str, str] | None, *, http_get, now_fn) -> Got:
    """One conditional GET of the season's release asset (the module docstring). Never raises for the call: a raised
    call is a Got with error (a failed observation)."""
    url = release_url(season)
    etag = stored_etag(prev[1]) if prev else None
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    sent = "ETag sent" if etag else "no ETag stored (unconditional GET)"
    part = None
    try:
        resp = http_get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=True)
    except Exception as e:  # noqa: BLE001 - a raised call is a failed observation, its error kept (redacted)
        return Got(url, now_fn(), error=_scrub(f"{type(e).__name__}: {e}")[:256], etag=f"{sent}; the call raised")
    fetched = now_fn()
    try:
        code = int(resp.status_code)
        if code == 304:
            if not prev:
                return Got(url, fetched, 304, error="HTTP 304 with no stored payload to carry (refused)",
                           etag=f"{sent}; 304")
            return Got(url, fetched, 304, prev[0], prev[1], etag=f"{sent}; 304 not modified")
        if code != 200:
            return Got(url, fetched, code, error=status_error(code), etag=f"{sent}; HTTP {code}")
        abs_dir = _payload_dir(fetched)[1]
        abs_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{fetched:%H%M%S}Z-depth_charts_{int(season)}.", suffix=".csv.part",
                                    dir=abs_dir)          # a name of its own: two runs never share a partial file
        part = Path(name)
        h = hashlib.sha256()
        with os.fdopen(fd, "wb") as f:
            for b in resp.iter_content(chunk_size=CHUNK):
                if b:
                    h.update(b)
                    f.write(b)
        sha = h.hexdigest()
        new_etag = (resp.headers or {}).get("ETag")
        if prev and sha == prev[0]:
            part.unlink()
            part = None
            return Got(url, fetched, 200, prev[0], prev[1],
                       etag=f"{sent}; 200 byte-identical (not kept again)" + _refresh_etag(prev[1], etag, new_etag))
        rel, final = _kept(fetched, f"depth_charts_{int(season)}.csv", sha)
        _retain(part, final, sha)                         # exclusive: another payload's file is never overwritten
        if new_etag:
            (final.parent / (final.name + ".etag")).write_text(str(new_etag) + "\n", encoding="utf-8")
        return Got(url, fetched, 200, sha, rel, changed=True,
                   etag=f"{sent}; 200 changed" + ("" if new_etag else " (the answer carried no ETag)"))
    except Exception as e:  # noqa: BLE001 - a broken stream is a failed observation
        return Got(url, fetched, getattr(resp, "status_code", None),
                   error=_scrub(f"{type(e).__name__}: {e}")[:256], etag=f"{sent}; the read broke")
    finally:
        if part is not None:
            try:
                part.unlink()
            except OSError:
                pass
        close = getattr(resp, "close", None)
        if close:
            close()


def file_endpoint(path: Path) -> str:
    return f"file:{path.name}"


def from_file(path: Path, prev: tuple[str, str] | None, now: datetime) -> Got:
    """A hand-carried file: hashed; kept under the payload directory when its bytes differ from the last kept one.
    The endpoint and the kept path are checked (the writer's endpoint rule, the payload path rule, the name's length)
    BEFORE anything is copied: a refusal leaves no file (Codex on #841, round 1)."""
    ep = file_endpoint(path)
    why = rec.endpoint_refusal(ep)
    if why:
        raise Refused(why)
    sha = sha256_file(path)
    if prev and sha == prev[0]:
        return Got(ep, now, None, prev[0], prev[1], etag="n/a (--file); byte-identical to the last kept payload")
    rel, final = _kept(now, path.name, sha)
    created = _retain(path, final, sha)
    return Got(ep, now, None, sha, rel, changed=True, etag="n/a (--file)", created=created)


# ---- the ingest -------------------------------------------------------------------------------------------------------

@dataclass
class Ingest:
    """The run's receipt (law 2)."""
    got: Got
    status: str = "complete"
    observation_id: int | None = None
    rows_read: int = 0
    loads: int = 0
    new_loads: int = 0
    new_rows: int = 0
    rows_asserted: int = 0
    old_rows: int = 0                     # at or before the watermark: read, not asserted again
    watermark: datetime | None = None
    partial_groups: list = field(default_factory=list)     # (dt, team, rows, previous complete rows)
    unmapped_teams: dict = field(default_factory=dict)     # team text -> rows
    ambiguous_teams: set = field(default_factory=set)
    unmapped_players: int = 0
    backfilled: int = 0
    refused: str | None = None            # a fetched file the adapter refused (a failed observation)

    def lines(self) -> list[str]:
        g = self.got
        z = (lambda d: d.isoformat(timespec="seconds") + "Z" if d else "none held")
        out = [f"AVAILABILITY-NFLVERSE · observation #{self.observation_id} · {self.status} · <{g.endpoint}> · "
               f"fetched_at {z(g.fetched_at)}" + (f" · HTTP {g.http_status}" if g.http_status is not None else "")]
        if g.error:
            out.append(f"  error (redacted): {g.error}")
        out.append(f"  rows read {self.rows_read} · loads {self.loads} (new {self.new_loads}) · new rows "
                   f"{self.new_rows} · rows asserted {self.rows_asserted} · older rows not asserted again "
                   f"{self.old_rows} (watermark: newest source_stamp held {z(self.watermark)})")
        out.append(f"  partial team groups: {len(self.partial_groups)}, closing nothing"
                   + "".join(f"\n    {z(dt)} {team}: {n} row(s) < half of {prev}" for dt, team, n, prev
                             in self.partial_groups))
        um = ", ".join(f"{t} ({n} row(s))" for t, n in sorted(self.unmapped_teams.items())) or "none"
        out.append(f"  unmapped teams: {len(self.unmapped_teams)} ({um})"
                   + (f"; ambiguous tla (more than one NFL team): {', '.join(sorted(self.ambiguous_teams))}"
                      if self.ambiguous_teams else "")
                   + f" · unmapped players: {self.unmapped_players} row(s) (no NFL player table: addendum 254 item "
                     f"2(3))")
        out.append(f"  backfilled rows (recorded more than {rec.SOURCE_CADENCE_HOURS[SOURCE]} h after their dt): "
                   f"{self.backfilled}")
        if g.changed and self.rows_read and not self.new_rows and not self.refused:
            out.append(f"  no new load: the file's newest dt is the watermark ({z(self.watermark)}); nothing to "
                       f"assert")
        out.append(f"  payload sha256 {g.sha256[:16] if g.sha256 else 'none'}"
                   + (f" · {g.payload_path}" if g.payload_path else "") + f" · ETag: {g.etag}")
        out.append(ATTRIBUTION)
        return out


def writer_refusal(rows: list[dict]) -> str | None:
    """Why the writer would refuse these assertions, or None: record.assertion_refusal (the writer's own checks, its
    widths among them: player_name 128 characters, source_team and source_player_id 64) on every row, numbered as the
    writer numbers them. Run BEFORE a --file is copied (a refusal: exit 2, nothing copied, nothing written) and, on a
    fetched file, before the write (a refusal: a failed observation that keeps the payload's path) (Codex on #841,
    round 1)."""
    for i, a in enumerate(rows, 1):
        why = rec.assertion_refusal(a, i, SOURCE)
        if why:
            return why
    return None


def _assertions(parsed: Parsed, wm: datetime | None, tmap: dict, ambiguous: set, fetched: datetime,
                last_complete: dict, ing: Ingest) -> list[dict]:
    out = []
    by_load: dict = {}
    cad = timedelta(hours=rec.SOURCE_CADENCE_HOURS[SOURCE])
    for dt, row in parsed.rows:
        if wm is not None and dt <= wm:
            ing.old_rows += 1
            continue
        team = row["team"]
        tid = tmap.get(team) if team not in ambiguous else None
        if tid is None:
            ing.unmapped_teams[team] = ing.unmapped_teams.get(team, 0) + 1
            if team in ambiguous:
                ing.ambiguous_teams.add(team)
        gsis = row["gsis_id"] if row["gsis_id"].strip() else None
        espn = row["espn_id"] if row["espn_id"].strip() else None
        attrs = {**{c: row[c] for c in ATTR_COLUMNS},
                 "dt_raw": row["dt"], "espn_id": row["espn_id"], "gsis_id": row["gsis_id"]}
        # ONE id that does not move: the chart's own (espn_id), else gsis_id; a gsis_id filled in later changes attrs
        # only (VOLATILE_ATTRS), never the key (record.player_key), so it never reads as a flip (the module docstring)
        out.append({"kind": KIND, "player_id": None, "source_player_id": espn or gsis,
                    "player_name": row["player_name"] or None, "team_id": tid, "source_team": team,
                    "match_id": None, "attrs": attrs, "source_stamp": dt})
        by_load.setdefault(dt, {}).setdefault(team, 0)
        by_load[dt][team] += 1
        if fetched - dt > cad:
            ing.backfilled += 1
    ing.new_loads = len(by_load)
    for dt in sorted(by_load):
        counts = {(SOURCE, ("src", t)): n for t, n in by_load[dt].items()}
        prev = dict(last_complete)
        for key in rec.guard_load(counts, last_complete):
            ing.partial_groups.append((dt, key[1][1], counts[key], prev[key]))
    ing.partial_groups.sort(key=lambda x: (x[0], x[1]))
    ing.new_rows = len(out)
    ing.unmapped_players = len(out)
    return out


def _db_lock():
    """The chains' DB lock (#569), as cup_lineups_live._db_lock takes it: a no-op inside a chain step."""
    import sys
    hosting = str(Path(__file__).resolve().parents[2] / "deploy" / "hosting")
    if hosting not in sys.path:
        sys.path.insert(0, hosting)
    import sp_common
    return sp_common.sync_lock(on_wait=lambda p: print(f"… waiting for the DB lock {p} (a chain or closing run holds "
                                                       "it)", flush=True))


def _after_a_refused_write(got: Got, e: Exception, *, hand_carried: bool) -> None:
    """The writer refused a write AFTER a payload was kept (every check the writer runs on the rows is run before the
    keep: what is left is the store's own refusal). Never an orphan payload (Codex on #841, round 1): a --file's copy
    made by this run is removed and the refusal stands (exit 2, nothing copied, nothing written); a fetched file's
    payload stays as evidence and returns here, so the caller writes the fetch as a `failed` observation that keeps
    its path, the refusal its error. A write that kept nothing is re-raised as it was."""
    if not (got.changed and got.payload_path):
        raise e
    if hand_carried:
        if got.created:
            final = PAYLOAD_BASE / got.payload_path
            final.unlink(missing_ok=True)
            for d in (final.parent, final.parent.parent):    # the date and source directories, only when left empty
                try:
                    d.rmdir()
                except OSError:
                    break
        raise e


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run(season: int | None = None, file: str | None = None, *, http_get=None, now_fn=_now) -> Ingest:
    """THE INGEST (the module docstring): one observation, its new rows, its receipt. Refused (nothing written, no
    call) on a missing DB file, an unmigrated store, a season before 2025, or a --file that is not the 2025+ shape,
    holds a load from the future, or holds only loads older than the source's watermark."""
    from src.db.database import readonly_scope
    season = current_season() if season is None else int(season)
    why = season_refusal(season)
    if why and file is None:
        raise Refused(why)
    path = rec._db_file()
    if path is None or not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path or 'a non-file database URL'}: the record never creates one "
                      "(law 5)")
    src_file = None
    if file is not None:
        src_file = Path(file)
        if not src_file.is_file():
            raise Refused(f"REFUSED: --file {file!r} is not a file")
    endpoint = file_endpoint(src_file) if src_file is not None else release_url(season)
    why = rec.endpoint_refusal(endpoint)            # the writer's rule, before any call, copy or file (Codex #841 r1)
    if why:
        raise Refused(why)
    if src_file is not None:
        parsed_local = read_file(src_file)          # refused before anything is copied or written
    with _db_lock():
        with readonly_scope() as s:
            if not rec.migrated(s):
                raise Refused("REFUSED: migrate_availability_record.py has not run (the tables and their marker); "
                              "nothing fetched, nothing written")
            prev = previous_payload(s, endpoint)
            wm = watermark(s)
            tmap, ambiguous = team_map(s)
            last_complete = stored_complete_groups(s)
        pre = None
        if src_file is not None:
            now = now_fn()
            why = future_refusal(parsed_local, now) or older_refusal(parsed_local, wm)
            if why:
                raise Refused(why)                  # an operator's file: nothing copied, nothing written (exit 2)
            # every row it would assert, through the writer's own checks, BEFORE anything is copied (Codex #841 r1)
            pre = Ingest(got=Got(endpoint, now), watermark=wm)
            pre_rows = _assertions(parsed_local, wm, tmap, ambiguous, now, last_complete, pre)
            why = writer_refusal(pre_rows)
            if why:
                raise Refused(f"{why}; nothing copied, nothing written")
            got = from_file(src_file, prev, now)
        else:
            if http_get is None:
                import requests
                http_get = requests.get
            got = fetch(season, prev, http_get=http_get, now_fn=now_fn)
        ing = Ingest(got=got, watermark=wm)
        rows: list = []
        if got.error:
            ing.status = "failed"
        elif got.changed:
            try:
                if pre is not None:                 # the --file: read and checked above, before its copy
                    parsed, ing, rows = parsed_local, pre, pre_rows
                    ing.got = got
                else:
                    parsed = read_file(PAYLOAD_BASE / got.payload_path)
                    why = future_refusal(parsed, got.fetched_at) or older_refusal(parsed, wm)
                    if why:
                        raise Refused(why)          # a fetched file: a failed observation, the file kept (evidence)
                    rows = _assertions(parsed, wm, tmap, ambiguous, got.fetched_at, last_complete, ing)
                    why = writer_refusal(rows)
                    if why:
                        raise Refused(why)          # the writer's own rule: the same failed observation, file kept
            except Refused as e:
                ing = Ingest(got=got, watermark=wm, status="failed", refused=str(e))
                got.error = str(e)[:256]
                parsed, rows = None, []
            if parsed is not None:
                ing.rows_read, ing.loads = len(parsed.rows), len(parsed.loads)
                ing.status = ("empty" if not parsed.rows else "partial" if ing.unmapped_teams else "complete")
        obs = {"sport": "nfl", "source": SOURCE, "endpoint": got.endpoint, "fetched_at": got.fetched_at,
               "http_status": got.http_status, "payload_sha256": got.sha256, "payload_path": got.payload_path,
               "status": ing.status, "error": got.error}
        try:
            r = rec.write_observation(obs, rows if ing.status in rec.ASSERTING else [])
        except rec.Refused as e:
            _after_a_refused_write(got, e, hand_carried=src_file is not None)      # raises unless a fetch kept a file
            ing = Ingest(got=got, watermark=wm, status="failed", refused=str(e))
            got.error = str(e)[:256]
            r = rec.write_observation({**obs, "status": "failed", "error": got.error}, [])
    ing.observation_id = r.observation_id
    ing.rows_asserted = r.assertions
    return ing


__all__ = ["SOURCE", "KIND", "COLUMNS", "ATTR_COLUMNS", "FIRST_SEASON", "RELEASE_URL", "TIMEOUT", "ATTRIBUTION",
           "Refused", "Parsed", "Got", "Ingest", "current_season", "release_url", "season_refusal", "header_refusal",
           "read_file", "future_refusal", "older_refusal", "status_error", "FUTURE_SKEW", "team_map", "watermark",
           "stored_complete_groups", "previous_payload", "stored_etag", "fetch", "from_file", "writer_refusal", "run"]
