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
DAILY = re.compile(r"^sports_\d{4}-\d{2}-\d{2}(_\d{6})?\.db$")   # pull_backup.DAILY: a daily .backup copy's name
MAX_AGE_HOURS = 26                             # the 09:30 UTC daily backup, read at 10:20, with a day's slack
BUFFER_POOL = 256 * 1024 * 1024                # the engine's default is ~80% of the machine's memory
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
    return out


# ---- the engine (347 item 5(a)) -------------------------------------------------------------------------------------

def engine():
    """The picked engine, imported here and nowhere else. Refused (exit 2, nothing read) when it is absent (the
    laptop and CI never install it) or is not exactly the pinned version. The package's environment overrides are
    dropped first, and every open passes backend="pybind", so its ctypes fallback (a liblbug.so found by path, the
    working directory included) is never taken: a missing native module is an error, not a different library."""
    for k in _LBUG_ENV:
        os.environ.pop(k, None)
    try:
        import ladybug as lb
    except ImportError as e:
        raise Refused(f"the graph engine is not installed ({e}); it is host-only: {REQUIREMENTS}, installed with "
                      "--require-hashes (addendum 347 item 5(a)); nothing read")
    if getattr(lb, "__version__", None) != ENGINE_VERSION:
        raise Refused(f"the graph engine is {ENGINE} {getattr(lb, '__version__', '?')}, not the pinned "
                      f"{ENGINE_VERSION} (347 item 5(d): a bump is a PR); nothing read")
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


def _key(source: str, k: tuple | None) -> str:
    """A node's key: the record's own identity (record.player_key / team_key / match_key: the source's id or text,
    ours only where the source gave none), per source."""
    if k is None or k[1] is None:
        return f"{source}|none"
    return f"{source}|{k[0]}|{k[1]}"


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
    players: dict[str, tuple] = {}
    teams: dict[str, list] = {}
    games: dict[str, list] = {}
    in_game: dict[tuple, str] = {}
    about: set[tuple] = set()
    obs_named_game: set[int] = set()
    sports = sorted({getattr(v, "value", v) for (v,) in s.execute(select(A.sport).distinct())})
    assertions = 0
    for sport in sports:
        for r, riv, siv in rec.walk(s, sport):
            assertions += 1
            now_ = rec.mapped_now(riv)
            pk = _key(r.source, rec.player_key(r))
            tk = _key(r.source, rec.team_key(r))
            mk = rec.match_key(r)
            gk = (f"match|{mk[1]}" if mk[0] == "id" else _key(r.source, mk)) if mk is not None else None
            players[pk] = (pk, r.source, r.source_player_id, r.player_name, now_.player_id)
            teams[tk] = [tk, r.source, r.source_team, now_.team_id, None]
            if gk is not None:
                prev = games.get(gk)
                games[gk] = [gk, r.source if mk[0] == "src" else None, mk[1] if mk[0] == "src" else None,
                             now_.match_id if now_.match_id is not None else (prev[3] if prev else None)]
                side = (r.attrs or {}).get("side")
                in_game.setdefault((tk, gk), "" if side is None else str(side))
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
            games.setdefault(gk, [gk, None, None, mid])
            about.add((oid, gk))
    ids = sorted({g[3] for g in games.values() if g[3] is not None})
    info: dict[int, tuple] = {}
    for k in range(0, len(ids), 500):
        q = (select(Match.id, Competition.code, Match.season, Match.utc_date, Match.status, Match.home_team_id,
                    Match.away_team_id).outerjoin(Competition, Competition.id == Match.competition_id)
             .where(Match.id.in_(ids[k:k + 500])))
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
    for (tk, gk), side in in_game.items():
        t["IN_GAME"].add([tk, gk, side])
    for (oid, gk) in sorted(about):
        t["ABOUT"].add([oid, gk])
    t["Build"].add(["build", _ts(built_at), copy.name, copy_sha, _s(provenance.git_sha()), f"{ENGINE} {ENGINE_VERSION}",
                    assertions, observations])
    for x in t.values():
        x.close()
    return t


def _load(lb, path: Path, tables: dict[str, _Table]) -> None:
    db = lb.Database(str(path), backend="pybind", buffer_pool_size=BUFFER_POOL)
    con = lb.Connection(db)
    try:
        for ddl in SCHEMA:
            con.execute(ddl)
        for name in (*NODE_TABLES, *REL_TABLES):
            for f in tables[name].files:
                con.execute(f"COPY {name} FROM '{f}' (HEADER=true, QUOTE='\"', ESCAPE='\"')")
                f.unlink()
    finally:
        con.close()
        db.close()


def _counts(lb, path: Path) -> dict[str, int]:
    """The finished file's own counts, read back read-only (a read-write open would rewrite the file's bytes)."""
    db = lb.Database(str(path), backend="pybind", read_only=True, buffer_pool_size=BUFFER_POOL // 4)
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


def append_receipt(out: Path, rec: dict) -> None:
    with open(out.parent / RECEIPTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")


def rebuild(out: Path, copy: Path | None = None, backup_dir: Path | None = None, lb=None,
            now: datetime | None = None, max_age_hours: float = MAX_AGE_HOURS) -> dict:
    """Rebuild the graph whole from a .backup copy: `copy` as given, or the newest verified daily copy in
    `backup_dir` (pick_copy). The copy passes mlb_pitchers_gate's --db fence and is read through its mode=ro +
    immutable=1 session; the graph is written into a staging directory beside `out`, then moved onto `out` after the
    finished file's own counts equal what was staged. Every outcome once `out` is accepted is one line of
    rebuild.jsonl beside the graph (252 item 4: "a failed rebuild is a receipt line"): ok, refused or error. A refusal
    raises Refused (exit 2) and a failure re-raises (exit 1); the previous graph is untouched in either case."""
    from src.availability import record as rec
    from src.walters import mlb_pitchers_gate as mp
    t0 = time.monotonic()
    now = now or datetime.now(timezone.utc)
    out = check_out(out)
    receipt = {"kind": "availability-graph-rebuild", "at": _ts(now) + "Z", "ok": False, "copy": None,
               "out": str(out), "engine": f"{ENGINE} {ENGINE_VERSION}"}
    stage = out.parent / f".{out.name}.build-{os.getpid()}"
    try:
        if (copy is None) == (backup_dir is None):
            raise Refused("one of --db (a .backup copy) or --backup-dir (the newest verified daily copy in it)")
        if copy is None:
            copy = pick_copy(backup_dir, now, max_age_hours)
        try:
            copy = mp.check_db(copy)
        except mp.GateRefused as e:
            raise Refused(str(e)) from None
        receipt["copy"] = str(copy)
        lb = lb or engine()
        receipt["copy_sha256"] = copy_sha = sha256_file(copy)
        receipt["copy_mtime"] = _ts(datetime.fromtimestamp(copy.stat().st_mtime, timezone.utc)) + "Z"
        try:
            ctx = mp.readonly_session(copy)
            s = ctx.__enter__()
        except mp.GateRefused as e:
            raise Refused(str(e)) from None
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
        graph = stage / GRAPH_NAME
        _load(lb, graph, tables)
        got = _counts(lb, graph)
        if got != staged:
            raise RuntimeError(f"the finished graph's counts {got} differ from what was staged {staged}")
        left = sorted(p.name for p in stage.iterdir() if p.name != GRAPH_NAME)
        if left:
            raise RuntimeError(f"the staging directory holds {left} beside the graph after its close")
        os.replace(graph, out)
        receipt.update(ok=True, counts=got, sha256=sha256_file(out), bytes=out.stat().st_size)
    except Refused as e:
        receipt["refused"] = str(e)[:500]
        raise
    except Exception as e:  # noqa: BLE001 - the receipt first, then the failure (252 item 4: a receipt line)
        receipt["error"] = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        receipt["seconds"] = round(time.monotonic() - t0, 1)
        append_receipt(out, receipt)
    return receipt
