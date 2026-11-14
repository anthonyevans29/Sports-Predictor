"""THE AVAILABILITY RECORD'S GRAPH PROJECTION (lane availability-record, #830, step 7).

ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4, verbatim in part: "a nightly rebuild of the record into an
EMBEDDED graph engine on the host — file-based, no server, Cypher — nodes Player, Team, Game, Observation; edges from
the assertions carrying kind, recorded_at, source_stamp and the derived interval; rebuilt whole from SQLite (mode=ro)
by one command, `availability-graph-rebuild` [...]; its file under logs/, never under data/, never backed up, never
mirrored, deletable without loss. NEVER written by a chain other than its rebuild, NEVER read by the Desk, a
prediction, an export or a gate; a failed rebuild is a receipt line and stops nothing."

ARCHITECT 2026-11-11 19:50 ET, addendum 347 item 5, THE PICK: "LADYBUGDB (`ladybug` [...]), version 0.22.3 exactly,
the cp312 manylinux x86_64 wheel by the sha256 the page records", on four conditions: (a) "HOST-ONLY and optional —
its own requirements file installed with `--require-hashes`, never requirements.txt; the laptop and CI do not install
it and its tests skip when it is absent"; (b) "the rebuild NEVER runs inside the Desk's trust boundary: its own
systemd unit with NO EnvironmentFile [...], `PrivateNetwork=yes`, `NoNewPrivileges=yes`, `ProtectSystem=strict` with
one writable directory for the graph file, reading a `.backup` COPY of the database opened mode=ro + immutable=1,
never the live file"; (c) "nothing reads the graph for a call, a price or a page until a later ruling"; (d) "a
version bump is a PR that re-reads identity and hash, never a range".

The package imports as `ladybug` (its wheel's top_level.txt; there is no `lbug` module), and only here: this module
imports it inside `engine()`, so nothing else in the app loads it (tests/test_availability_graph.py pins that no other
module names it). The graph is written whole into a staging directory beside its final path and moved onto it only
after its own counts are re-read from the finished file; a failed rebuild leaves the previous graph as it was.

The read is the record's own: `record.walk`, the same partitions and the same derivation as `availability --history`
(252 item 2: "there is no second path"), under both clocks.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

ENGINE = "ladybug"
ENGINE_VERSION = "0.22.3"                      # 347 item 5: exactly; requirements-graph.txt pins it by hash
REQUIREMENTS = "requirements-graph.txt"
GRAPH_NAME = "availability.lbug"
DEFAULT_OUT = Path("logs") / "availability" / "graph" / GRAPH_NAME
RECEIPTS = "rebuild.jsonl"                     # beside the graph: the unit's one writable directory (347 item 5(b))
STAGED = "staged.json"                         # in the staging directory: the size a load starts at (378 item 4(d))
DAILY = re.compile(r"^sports_\d{4}-\d{2}-\d{2}(_\d{6})?\.db$")   # pull_backup.DAILY: a daily .backup copy's name
MAX_AGE_HOURS = 26                             # the 09:30 UTC daily backup, read at 10:20, with a day's slack
# THE POOL AND THE CHECKPOINT, AS A RULE TIED TO THE UNIT'S MemoryMax (ARCHITECT 2026-11-14 08:23 ET, addendum 378
# item 4(c): "the pool and the checkpoint behaviour stated as a rule tied to the unit's MemoryMax, not a bare
# constant"). What the engine documents (law 1), its installed wheel's ladybug/database.py docstring: "buffer_pool_size:
# The maximum size of buffer pool in bytes. Defaults to ~80% of system memory."; "auto_checkpoint: If true, the
# database will automatically checkpoint when the size of the WAL file exceeds the checkpoint threshold."; its docs
# (LadybugDB/ladybug-docs, transaction.md): "By default, checkpoint happens automatically at the end of a write
# transaction when the WAL file size goes beyond the `CHECKPOINT_THRESHOLD`"; and import/index.mdx: only "the memory
# used to prepare the imported relationship table data" spills to a .tmp file. What its source adds (v0.22.3, tag
# 6a3e04a8; quoted in the PR): every COPY FROM forces a checkpoint at its commit while auto_checkpoint is on, whatever
# the WAL size (src/main/client_context.cpp: "We force checkpoint for COPY_FROM statement unless the user has disabled
# automatic checkpointing"); a rel table's node group is 2^17 bound nodes; a checkpoint's buffers are never spilled.
# The rule:
#   (1) the pool is HALF the memory limit this process runs under: the smaller of its cgroup's limit, read at run time
#       (memory_limit()), and the unit's MemoryMax (under the unit both are 1536M, so 768 MiB); with no limit of its own,
#       or a looser one (a laptop, a sandbox, a test), the unit's MemoryMax binds, so the pool is never larger than the
#       unit's and a tighter limit still binds. The other half is the staging walk's Python heap, the
#       engine's memory outside its pool and the page cache the limit also counts (the engine's own default, 80% of the
#       limit, would leave the walk too little);
#   (2) auto_checkpoint stays ON, set here rather than inherited: then every COPY of CHUNK rows ends in a checkpoint
#       that merges its rows into the stored graph and frees them. Off, COPY's rows pile up in memory unmerged
#       (measured: the 256 MiB pool failed at the 5th FACT COPY instead of the 10th). checkpoint_threshold has no
#       effect on a COPY and is not set;
#   (3) the pool is a ceiling the record grows into, not a fix for growth: every Player (and every Team) is in one
#       node group, so each FACT checkpoint rewrites every FACT edge in memory, and the pool it needs grows with the
#       record's assertions (the PR's receipts give the measured ceiling). The line names the limit, the pool and the
#       staged size, so the night it is reached says so.
UNIT_MEMORY_MAX = 1536 * 1024 * 1024           # deploy/hosting/systemd/sp-availability-graph.service MemoryMax=1536M
POOL_SHARE = 2                                 # the pool is limit // POOL_SHARE
CHUNK = 100_000                                # rows per COPY: one COPY of 1M edges overflows a 256 MB pool
_LBUG_ENV = ("LBUG_PYTHON_BACKEND", "LBUG_C_API_LIB_PATH")      # the package's own overrides: never honoured here

SCHEMA = (
    "CREATE NODE TABLE Player(key STRING, source STRING, source_player_id STRING, name STRING, player_id INT64, "
    "PRIMARY KEY(key))",
    "CREATE NODE TABLE Team(key STRING, source STRING, source_team STRING, team_id INT64, name STRING, "
    "PRIMARY KEY(key))",
    "CREATE NODE TABLE Game(key STRING, source STRING, source_match_id STRING, match_id INT64, competition STRING, "
    "season STRING, kickoff TIMESTAMP, status STRING, home_team_id INT64, away_team_id INT64, PRIMARY KEY(key))",
    "CREATE NODE TABLE Observation(id INT64, sport STRING, source STRING, endpoint STRING, match_id INT64, "
    "kickoff_at TIMESTAMP, poll_label STRING, scheduled_at TIMESTAMP, fetched_at TIMESTAMP, http_status INT64, "
    "status STRING, late BOOLEAN, rows_asserted INT64, payload_sha256 STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Build(key STRING, built_at TIMESTAMP, copy STRING, copy_sha256 STRING, git_sha STRING, "
    "engine STRING, assertions INT64, observations INT64, PRIMARY KEY(key))",
    "CREATE REL TABLE FACT(FROM Player TO Team, assertion_id INT64, observation_id INT64, sport STRING, kind STRING, "
    "recorded_at TIMESTAMP, source_stamp TIMESTAMP, game STRING, attrs STRING, "
    "rec_interval INT64, rec_start TIMESTAMP, rec_end TIMESTAMP, rec_closed_by INT64, rec_why STRING, "
    "src_interval INT64, src_start TIMESTAMP, src_end TIMESTAMP, src_closed_by INT64, src_why STRING, "
    "backfilled BOOLEAN, post_hoc BOOLEAN)",
    "CREATE REL TABLE ASSERTED(FROM Observation TO Player, assertion_id INT64, kind STRING)",
    "CREATE REL TABLE IN_GAME(FROM Team TO Game, side STRING)",
    "CREATE REL TABLE ABOUT(FROM Observation TO Game)",
)
NODE_TABLES = ("Player", "Team", "Game", "Observation", "Build")
REL_TABLES = ("FACT", "ASSERTED", "IN_GAME", "ABOUT")
COLUMNS = {
    "Player": ("key", "source", "source_player_id", "name", "player_id"),
    "Team": ("key", "source", "source_team", "team_id", "name"),
    "Game": ("key", "source", "source_match_id", "match_id", "competition", "season", "kickoff", "status",
             "home_team_id", "away_team_id"),
    "Observation": ("id", "sport", "source", "endpoint", "match_id", "kickoff_at", "poll_label", "scheduled_at",
                    "fetched_at", "http_status", "status", "late", "rows_asserted", "payload_sha256"),
    "Build": ("key", "built_at", "copy", "copy_sha256", "git_sha", "engine", "assertions", "observations"),
    "FACT": ("from", "to", "assertion_id", "observation_id", "sport", "kind", "recorded_at", "source_stamp", "game",
             "attrs", "rec_interval", "rec_start", "rec_end", "rec_closed_by", "rec_why", "src_interval",
             "src_start", "src_end", "src_closed_by", "src_why", "backfilled", "post_hoc"),
    "ASSERTED": ("from", "to", "assertion_id", "kind"),
    "IN_GAME": ("from", "to", "side"),
    "ABOUT": ("from", "to"),
}


class Refused(Exception):
    """A refusal: nothing read or nothing written; exit 2."""


def _cgroup_limit(cgroup_root: Path = Path("/sys/fs/cgroup"), self_cgroup: Path = Path("/proc/self/cgroup")):
    """The smallest memory limit on this process's cgroup or any cgroup above it, (bytes, the file it came from), or
    None when none is set or none can be read. cgroup v2: <root>/<path>/memory.max (only "max" is no limit; any number
    is a limit, Codex on #996); v1: <root>/memory/<path>/memory.limit_in_bytes (only the kernel's own no-limit value is
    no limit: PAGE_COUNTER_MAX pages, LONG_MAX // PAGE_SIZE, times PAGE_SIZE, 9223372036854771712 on 4 KiB pages; any
    smaller number is a limit, even one at or above the machine's memory; addendum 379 item 4)."""
    try:
        lines = self_cgroup.read_text().splitlines()
    except OSError:
        return None
    try:
        page = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        page = 4096
    v1_no_limit = (2 ** 63 - 1) // page * page
    found = []
    for line in lines:
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        _, controllers, path = parts
        if controllers == "":
            base, name, v1 = cgroup_root, "memory.max", False
        elif "memory" in controllers.split(","):
            base, name, v1 = cgroup_root / "memory", "memory.limit_in_bytes", True
        else:
            continue
        rel = Path(path.lstrip("/"))
        for d in [rel, *rel.parents]:
            f = base / d / name
            try:
                v = f.read_text().strip()
            except OSError:
                continue
            if v == "max" or not v.isdigit():
                continue
            n = int(v)
            if v1 and n >= v1_no_limit:
                continue
            found.append((n, str(f)))
    return min(found) if found else None


def memory_limit() -> tuple[int, str]:
    """(bytes, where): the memory limit the rebuild runs under (rule (1) above): the smaller of its cgroup's and the
    unit's MemoryMax (a looser cgroup limit never inflates the pool past the unit's)."""
    got = _cgroup_limit()
    if got is None:
        return UNIT_MEMORY_MAX, "the unit's MemoryMax (no cgroup limit on this process)"
    if got[0] > UNIT_MEMORY_MAX:
        return UNIT_MEMORY_MAX, f"the unit's MemoryMax (the looser cgroup limit {got[0]} at {got[1]})"
    return got


def buffer_pool(limit: int) -> int:
    """The engine's buffer pool for a memory limit (rule (1) above): half of it."""
    return limit // POOL_SHARE


# ---- the copy (347 item 5(b): "reading a .backup COPY of the database opened mode=ro + immutable=1") -------------

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def pick_copy(backup_dir: Path, now: datetime | None = None, max_age_hours: float = MAX_AGE_HOURS) -> Path:
    """The newest daily .backup copy in backup_dir whose `.sha256` sidecar matches its bytes (sp_backup writes the
    sidecar after the copy's integrity check and rename; a copy without one, or with one that does not match, is not
    taken), refused if it is older than max_age_hours by its file time: a stale copy is not rebuilt from as if it were
    today's. The host has no "latest" path; the choice is by evidence, and the receipt names the file."""
    d = Path(backup_dir).expanduser()
    if not d.is_dir():
        raise Refused(f"--backup-dir {backup_dir}: not a directory; nothing read")
    now = now or datetime.now(timezone.utc)
    names = sorted((n for n in os.listdir(d) if DAILY.match(n)), reverse=True)
    if not names:
        raise Refused(f"--backup-dir {d}: no daily .backup copy (sports_YYYY-MM-DD[_HHMMSS].db); nothing read")
    unverified = []
    for n in names:
        p, side = d / n, d / (n + ".sha256")
        try:
            want = side.read_text().split()[0] if side.is_file() else None
        except (OSError, IndexError):
            want = None
        if want is None or want != sha256_file(p):
            unverified.append(n)
            continue
        age = (now - datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)).total_seconds() / 3600
        if age > max_age_hours:
            raise Refused(f"the newest verified copy {p} is {age:.1f} h old (> {max_age_hours:g} h): stale, not "
                          "rebuilt from" + (f"; newer copies without a matching sidecar: {', '.join(unverified)}"
                                            if unverified else ""))
        return p
    raise Refused(f"--backup-dir {d}: no daily copy has a matching .sha256 sidecar ({', '.join(unverified)}); "
                  "nothing read")


def check_out(out: Path) -> Path:
    """The graph's path: a `.lbug` file under no data/ (law 5; 252 item 4: "its file under logs/, never under data/"),
    in an existing directory (the unit's one writable directory; the command never creates it), with no quote in it
    (the COPY statements name their staging files in quotes)."""
    from src.walters import mlb_pitchers_gate as mp
    out = Path(out).expanduser().resolve()
    if out.suffix != ".lbug":
        raise Refused(f"--out {out}: the graph's file is a .lbug file")
    for data in mp._data_dirs():
        if out == data or data in out.parents:
            raise Refused(f"--out {out} is under the repo's data/ ({data}): law 5; the graph lives under logs/")
    if any(part == "data" for part in out.parts):
        raise Refused(f"--out {out}: a path with a data/ directory in it is refused (law 5)")
    if not out.parent.is_dir():
        raise Refused(f"--out {out}: its directory does not exist (the unit's writable directory is made at install, "
                      "never by the rebuild)")
    if "'" in str(out):
        raise Refused(f"--out {out}: a quote in the path is refused")
    if not os.access(out.parent, os.W_OK):
        raise Refused(f"--out {out}: its directory is not writable by this user (nothing written, no receipt line)")
    return out


# ---- the engine (347 item 5(a)) -------------------------------------------------------------------------------------

def _dist_version() -> str | None:
    """The installed distribution's version, from its metadata (never `ladybug.__version__`: that attribute asks the
    native library, and the package falls back to a ctypes load of a liblbug.so found by path when its own native
    module does not import)."""
    from importlib import metadata
    try:
        return metadata.version(ENGINE)
    except metadata.PackageNotFoundError:
        return None


def engine():
    """The picked engine, imported here and nowhere else. Refused (exit 2, nothing read) when it is absent (the
    laptop and CI never install it), is not exactly the pinned version, or its own native module (`ladybug._lbug`,
    the pybind backend) does not import. The package's environment overrides are dropped first; the native module is
    imported through the package's own loader before anything else is asked of it, and every open passes
    backend="pybind", so the package's ctypes fallback (`ladybug._lbug_capi`: a liblbug.so found by path, the working
    directory included) is never imported: a missing native module is a refusal, not a different library."""
    for k in _LBUG_ENV:
        os.environ.pop(k, None)
    have = _dist_version()
    if have is None:
        raise Refused(f"the graph engine is not installed (no {ENGINE} distribution); it is host-only: "
                      f"{REQUIREMENTS}, installed with --require-hashes (addendum 347 item 5(a)); nothing read")
    if have != ENGINE_VERSION:
        raise Refused(f"the graph engine is {ENGINE} {have}, not the pinned {ENGINE_VERSION} (347 item 5(d): a bump "
                      "is a PR); nothing read")
    try:
        import ladybug as lb
        from ladybug import _backend
    except ImportError as e:
        raise Refused(f"the graph engine does not import ({e}); nothing read")
    if _backend.get_pybind_module() is None:
        raise Refused(f"the graph engine's native module does not import ({_backend._PYBIND_IMPORT_ERROR}; it links "
                      "the system OpenSSL 3); its ctypes fallback is never taken; nothing read")
    return lb


# ---- the projection ----------------------------------------------------------------------------------------------------

def _ts(v) -> str:
    if v is None:
        return ""
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)   # the engine drops an offset without converting
    return v.isoformat(sep=" ")


def _b(v) -> str:
    return "" if v is None else ("true" if v else "false")


def _i(v) -> str:
    return "" if v is None else str(int(v))


def _s(v) -> str:
    return "" if v is None else str(v)


def _key(sport: str, source: str, k: tuple | None) -> str:
    """A node's key: the record's own identity (record.player_key / team_key / match_key: the source's id or text,
    ours only where the source gave none), per sport and source: the record derives per sport, so one source's id
    or text in two sports is two nodes, never one (#944 item 2)."""
    if k is None or k[1] is None:
        return f"{sport}|{source}|none"
    return f"{sport}|{source}|{k[0]}|{k[1]}"


class _Table:
    """A table's staging CSV, written in chunks of CHUNK rows, each chunk its own file (one COPY per chunk)."""

    def __init__(self, stage: Path, name: str):
        self.stage, self.name, self.files, self.n, self._f, self._w, self._in = stage, name, [], 0, None, None, 0

    def add(self, row) -> None:
        if self._w is None or self._in >= CHUNK:
            self._close()
            p = self.stage / f"{self.name}.{len(self.files):04d}.csv"
            self._f = open(p, "w", newline="", encoding="utf-8")
            self._w = csv.writer(self._f)
            self._w.writerow(COLUMNS[self.name])
            self.files.append(p)
            self._in = 0
        self._w.writerow(row)
        self._in += 1
        self.n += 1

    def _close(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = self._w = None

    def close(self) -> list[Path]:
        self._close()
        return self.files


def _stage(s, stage: Path, copy: Path, copy_sha: str, built_at: datetime) -> dict[str, _Table]:
    """Every node and edge as staging CSV, read through the record's own walk (no second path) and, for the nodes'
    display columns, the copy's own tables (teams, matches, competitions, the observations)."""
    from sqlalchemy import select

    from src.availability import record as rec
    from src.db.schema import AvailabilityAssertion as A
    from src.db.schema import AvailabilityObservation as O
    from src.db.schema import Competition, Match, Team
    from src.walters import provenance
    t = {n: _Table(stage, n) for n in (*NODE_TABLES, *REL_TABLES)}
    players: dict[str, list] = {}
    teams: dict[str, list] = {}
    games: dict[str, list] = {}
    ids: dict[tuple, tuple] = {}            # (node kind, key) -> (recorded_at, assertion id, our id): the latest mapping

    def latest(kind: str, key: str, at, aid: int, v):
        """Our id for a node: the one the LATEST assertion carrying an id gives (by recorded_at, then assertion id),
        whatever order the walk yields its partitions in (mapped_now's rule, across every interval of the key)."""
        if v is None:
            return
        cur = ids.get((kind, key))
        if cur is None or (at, aid) > cur[:2]:
            ids[(kind, key)] = (at, aid, v)
    in_game: dict[tuple, str] = {}
    about: set[tuple] = set()
    obs_named_game: set[int] = set()
    sports = sorted({getattr(v, "value", v) for (v,) in s.execute(select(A.sport).distinct())})
    assertions = 0
    for sport in sports:
        for r, riv, siv in rec.walk(s, sport):
            assertions += 1
            pk = _key(sport, r.source, rec.player_key(r))
            tk = _key(sport, r.source, rec.team_key(r))
            mk = rec.match_key(r)
            gk = (f"match|{mk[1]}" if mk[0] == "id" else _key(sport, r.source, mk)) if mk is not None else None
            players.setdefault(pk, [pk, r.source, r.source_player_id])
            latest("name", pk, r.recorded_at, r.id, r.player_name)      # a corrected name: the latest one
            teams.setdefault(tk, [tk, r.source, r.source_team])
            latest("player", pk, r.recorded_at, r.id, r.player_id)
            latest("team", tk, r.recorded_at, r.id, r.team_id)
            if gk is not None:
                games.setdefault(gk, [gk, r.source if mk[0] == "src" else None, mk[1] if mk[0] == "src" else None])
                latest("game", gk, r.recorded_at, r.id, r.match_id if mk[0] == "src" else mk[1])
                in_game.setdefault((tk, gk), "")
                side = (r.attrs or {}).get("side")                 # the latest assertion's side (#944 item 3)
                latest("side", (tk, gk), r.recorded_at, r.id, None if side is None else str(side))
                about.add((r.observation_id, gk))
                obs_named_game.add(r.observation_id)
            t["FACT"].add([pk, tk, r.id, r.observation_id, sport, r.kind, _ts(r.recorded_at), _ts(r.source_stamp),
                           _s(gk), json.dumps(r.attrs, sort_keys=True, default=str) if r.attrs is not None else "",
                           riv.first.id, _ts(riv.start), _ts(riv.end),
                           _i(riv.closed_by.id if riv.closed_by else None), _s(riv.why_closed),
                           _i(siv.first.id if siv else None), _ts(siv.start if siv else None),
                           _ts(siv.end if siv else None), _i(siv.closed_by.id if siv and siv.closed_by else None),
                           _s(siv.why_closed if siv else None), _b(rec.backfilled(r)), _b(rec.post_hoc(r, riv))])
            t["ASSERTED"].add([r.observation_id, pk, r.id, r.kind])
    observations = 0
    obs_cols = (O.id, O.sport, O.source, O.endpoint, O.match_id, O.kickoff_at, O.poll_label, O.scheduled_at,
                O.fetched_at, O.http_status, O.status, O.late, O.rows_asserted, O.payload_sha256)
    for row in s.execute(select(*obs_cols).order_by(O.id)).yield_per(5000):
        (oid, sp, src, ep, mid, ko, poll, sch, fat, http, st, late, n, sha) = row
        observations += 1
        t["Observation"].add([oid, getattr(sp, "value", sp), src, ep, _i(mid), _ts(ko), _s(poll), _ts(sch), _ts(fat),
                              _i(http), st, _b(late), _i(n), _s(sha)])
        if mid is not None and oid not in obs_named_game:
            gk = f"match|{mid}"
            games.setdefault(gk, [gk, None, None])
            latest("game", gk, datetime.min, 0, mid)
            about.add((oid, gk))
    for k, row in players.items():                       # the player's name: the latest assertion's that gives one
        v = ids.get(("name", k))
        row.append(v[2] if v else None)
    for kind, table in (("player", players), ("team", teams), ("game", games)):
        for k, row in table.items():
            v = ids.get((kind, k))
            row.append(v[2] if v else None)
    ids_ = sorted({g[3] for g in games.values() if g[3] is not None})
    info: dict[int, tuple] = {}
    for k in range(0, len(ids_), 500):
        q = (select(Match.id, Competition.code, Match.season, Match.utc_date, Match.status, Match.home_team_id,
                    Match.away_team_id).outerjoin(Competition, Competition.id == Match.competition_id)
             .where(Match.id.in_(ids_[k:k + 500])))
        for (mid, code, season, ko, st, h, a) in s.execute(q):
            info[mid] = (code, season, ko, getattr(st, "value", st), h, a)
    for g in games.values():
        code, season, ko, st, h, a = info.get(g[3], (None,) * 6)
        t["Game"].add([g[0], _s(g[1]), _s(g[2]), _i(g[3]), _s(code), _s(season), _ts(ko), _s(st), _i(h), _i(a)])
    tids = sorted({x[3] for x in teams.values() if x[3] is not None})
    names: dict[int, str] = {}
    for k in range(0, len(tids), 500):
        names.update(dict(s.execute(select(Team.id, Team.name).where(Team.id.in_(tids[k:k + 500]))).all()))
    for x in teams.values():
        t["Team"].add([x[0], x[1], _s(x[2]), _i(x[3]), _s(names.get(x[3]))])
    for p in players.values():
        t["Player"].add([p[0], p[1], _s(p[2]), _s(p[3]), _i(p[4])])
    for (tk, gk) in in_game:
        v = ids.get(("side", (tk, gk)))
        t["IN_GAME"].add([tk, gk, v[2] if v else ""])
    for (oid, gk) in sorted(about):
        t["ABOUT"].add([oid, gk])
    t["Build"].add(["build", _ts(built_at), copy.name, copy_sha, _s(provenance.git_sha()), f"{ENGINE} {ENGINE_VERSION}",
                    assertions, observations])
    for x in t.values():
        x.close()
    return t


def _load(lb, path: Path, tables: dict[str, _Table], pool: int) -> None:
    db = lb.Database(str(path), backend="pybind", buffer_pool_size=pool, auto_checkpoint=True)   # rule (2)
    con = lb.Connection(db)
    try:
        for ddl in SCHEMA:
            con.execute(ddl)
        for name in (*NODE_TABLES, *REL_TABLES):
            for f in tables[name].files:
                # PARALLEL=FALSE: the parallel CSV reader refuses a quoted newline, and the record keeps any text
                # its source gave (a name with a newline would fail every rebuild for good: append-only)
                con.execute(f"COPY {name} FROM '{f}' (HEADER=true, QUOTE='\"', ESCAPE='\"', PARALLEL=FALSE)")
                f.unlink()
    finally:
        con.close()
        db.close()


def _counts(lb, path: Path, pool: int) -> dict[str, int]:
    """The finished file's own counts, read back read-only (a read-write open would rewrite the file's bytes)."""
    db = lb.Database(str(path), backend="pybind", read_only=True, buffer_pool_size=pool // 4)
    con = lb.Connection(db)
    try:
        out = {}
        for n in NODE_TABLES:
            out[n] = con.execute(f"MATCH (x:{n}) RETURN count(*)").get_all()[0][0]
        for n in REL_TABLES:
            out[n] = con.execute(f"MATCH ()-[x:{n}]->() RETURN count(*)").get_all()[0][0]
        return out
    finally:
        con.close()
        db.close()


def append_receipt(out: Path, rec: dict) -> str | None:
    """One line of rebuild.jsonl beside the graph. Never raises: a receipt that cannot be written is returned as its
    error (printed by the command), so it never replaces the run's own outcome."""
    try:
        with open(out.parent / RECEIPTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
    except OSError as e:
        return f"{type(e).__name__}: {e}"
    return None


class Killed(Exception):
    """SIGTERM (systemd's stop, TimeoutStartSec): raised in the run so its staging is removed and its line written."""


def _stale_stages(out: Path) -> tuple[list[str], dict[str, dict]]:
    """Staging directories a killed run left beside the graph (SIGKILL, MemoryMax: no finally runs). Removed by the
    next run, under the lock, and named on its receipt line, with the staged counts the killed run's load started at
    where it had written them (378 item 4(d): a run that dies without its own line still names its size). The size
    stays in the staging directory through the commit point (Codex on #996); only the finally's cleanup removes it,
    so one killed in the instant after its commit names its size too (its graph is then the one in place)."""
    gone, sizes = [], {}
    for p in sorted(out.parent.glob(f".{out.name}.build-*")):
        if p.is_dir():
            try:
                sizes[p.name] = json.loads((p / STAGED).read_text())
            except (OSError, ValueError):
                pass                                  # killed before it staged (or its file unreadable): no size
            shutil.rmtree(p, ignore_errors=True)
            gone.append(p.name)
    return gone, sizes


def rebuild(out: Path, copy: Path | None = None, backup_dir: Path | None = None, lb=None,
            now: datetime | None = None, max_age_hours: float = MAX_AGE_HOURS) -> dict:
    """Rebuild the graph whole from a .backup copy: `copy` as given, or the newest verified daily copy in
    `backup_dir` (pick_copy). The copy passes mlb_pitchers_gate's --db fence and is read through its mode=ro +
    immutable=1 session; the graph is written into a staging directory beside `out`, then moved onto `out` after the
    finished file's own counts equal what was staged. Every run whose `out` is accepted (check_out: a refused --out
    writes nothing at all) is one line of rebuild.jsonl beside the graph (252 item 4: "a failed rebuild is a receipt
    line"): ok, refused or error, a SIGTERM (the unit's stop or timeout) included. A SIGKILL (MemoryMax) writes no
    line and leaves its staging directory; the next run removes it, under the lock, and names it on its own line. A
    refusal raises Refused (exit 2) and a failure re-raises (exit 1); the previous graph is untouched in either
    case. One run at a time: a second run while one holds the lock is refused."""
    from src.availability import record as rec
    from src.walters import mlb_pitchers_gate as mp
    t0 = time.monotonic()
    now = now or datetime.now(timezone.utc)
    import fcntl
    import signal
    out = check_out(out)
    receipt = {"kind": "availability-graph-rebuild", "at": _ts(now) + "Z", "ok": False, "copy": None,
               "out": str(out), "engine": f"{ENGINE} {ENGINE_VERSION}"}
    stage = out.parent / f".{out.name}.build-{os.getpid()}"
    lock = None
    done = None                                       # the finished graph's receipt, computed before the commit point

    def _term(signum, frame):
        raise Killed(f"signal {signum} (the unit stopped or timed out)")
    installed = False
    try:
        prev = signal.signal(signal.SIGTERM, _term)
        installed = True
    except ValueError:                          # not the main thread: no handler (a test runner's worker)
        prev = None
    try:
        lock = open(out.parent / f".{out.name}.lock", "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Refused(f"another rebuild holds {out.parent / ('.' + out.name + '.lock')}; nothing read") from None
        left_by_killed, killed_sizes = _stale_stages(out)
        if left_by_killed:
            receipt["removed_stale_staging"] = left_by_killed
        if killed_sizes:
            receipt["stale_staged"] = killed_sizes
        if (copy is None) == (backup_dir is None):
            raise Refused("one of --db (a .backup copy) or --backup-dir (the newest verified daily copy in it)")
        if copy is None:
            copy = pick_copy(backup_dir, now, max_age_hours)
        try:
            copy = mp.check_db(copy)
        except mp.GateRefused as e:
            raise Refused(str(e)) from None
        receipt["copy"] = str(copy)
        if copy == out or (out.exists() and os.path.samefile(copy, out)):
            raise Refused(f"--db {copy} is --out: the rebuild never writes onto the copy it reads; nothing read")
        lb = lb or engine()
        receipt["copy_sha256"] = copy_sha = sha256_file(copy)
        receipt["copy_mtime"] = _ts(datetime.fromtimestamp(copy.stat().st_mtime, timezone.utc)) + "Z"
        try:
            mp.open_ro(copy).close()                 # the copy reads as SQLite, mode=ro + immutable=1, or a refusal
        except mp.GateRefused as e:
            raise Refused(str(e)) from None
        ctx = mp.readonly_session(copy)
        s = ctx.__enter__()
        try:
            if not rec.migrated(s):
                raise Refused(f"{copy}: migrate_availability_record.py has not run on this copy (the record's tables "
                              "and their marker); nothing built")
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir()
            tables = _stage(s, stage, copy, copy_sha, now)
        finally:
            ctx.__exit__(None, None, None)
        staged = {n: tables[n].n for n in (*NODE_TABLES, *REL_TABLES)}
        # 378 item 4(d): the line names the size BEFORE the load starts, so a failed line says what it failed at; and
        # the staging directory keeps it too, for the next run to name if this one is killed (SIGKILL: no line)
        receipt["staged"] = staged
        limit, where = memory_limit()
        pool = buffer_pool(limit)
        receipt.update(memory_limit=limit, memory_limit_from=where, buffer_pool=pool)
        (stage / STAGED).write_text(json.dumps(dict(staged=staged, memory_limit=limit, buffer_pool=pool),
                                               sort_keys=True))
        graph = stage / GRAPH_NAME
        _load(lb, graph, tables, pool)
        got = _counts(lb, graph, pool)
        if got != staged:
            raise RuntimeError(f"the finished graph's counts {got} differ from what was staged {staged}")
        left = sorted(p.name for p in stage.iterdir() if p.name not in (GRAPH_NAME, STAGED))
        if left:
            raise RuntimeError(f"the staging directory holds {left} beside the graph after its close")
        done = dict(ok=True, counts=got, sha256=sha256_file(graph), bytes=graph.stat().st_size)
        os.replace(graph, out)                       # the commit point: nothing after it can fail the run
        receipt.update(done)
    except Refused as e:
        receipt["refused"] = str(e)[:500]
        raise
    except BaseException as e:  # noqa: BLE001 - the receipt first, then the failure (252 item 4: a receipt line)
        if done is not None and not (stage / GRAPH_NAME).exists() and out.exists():
            receipt.update(done)                     # past the commit point (a SIGTERM there): the run succeeded
            receipt["after_commit"] = f"{type(e).__name__}: {e}"[:500]
            return receipt
        receipt["error"] = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        # The handler goes first (#944 item 4): a SIGTERM during this cleanup must not raise Killed past the except
        # above, after the commit point, over a run that succeeded. Nor may it end the process before the run's line
        # is written (Codex on #952: under SIG_DFL, restored here, it did): through the cleanup the signal is
        # DEFERRED, and it is re-delivered once the previous disposition (or the default one) is back.
        deferred = []
        if installed:
            signal.signal(signal.SIGTERM, lambda signum, frame: deferred.append(signum))
        shutil.rmtree(stage, ignore_errors=True)
        receipt["seconds"] = round(time.monotonic() - t0, 1)
        receipt_error = append_receipt(out, receipt)
        if receipt_error:
            receipt["receipt_error"] = receipt_error
            import sys
            print(f"AVAILABILITY-GRAPH: the receipt line was not written ({receipt_error})", file=sys.stderr)
        if lock is not None:
            lock.close()
        if installed:
            signal.signal(signal.SIGTERM, prev if prev is not None else signal.SIG_DFL)
            if deferred:
                os.kill(os.getpid(), signal.SIGTERM)      # the stop it was sent, after its line: the caller's to act on
    return receipt
