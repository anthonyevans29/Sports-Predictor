"""--db: the live file or a copy, and how each is opened (ARCHITECT 2026-11-23, addendum 462 item 6; ruled by
ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 4; #1089; the standing line, addendum 198 item 6(ii): "every `--db` on
a copy opens it with `immutable=1` beside `mode=ro` ... the live file keeps readonly_scope as is").

THE RULE (582 item 4, verbatim in part): "(a) The live file is the app's configured database, by resolved path and by
identity, and keeps its open. Any other --db is a copy: mode=ro with immutable=1 and no fallback. (b) A copy is refused
before any open, nothing read, exit 2, the message naming which case: under data/; a sidecar beside it; the file absent.
The path is printed, never a row. (c) The two live-file receipts refuse a --db that is not the configured database ...
(d) A machine whose configuration is not loaded reads its own live file as a copy under data/ and refuses."

`classify(db)` answers ("live", path) or ("copy", path), or raises CopyRefused before anything is opened. The copy's
fence is mlb_pitchers_gate.check_db, the standing --db fence (never created; never under any data/ by resolved path or
by identity, hard links and linked folders included; never the app's configured database), then the sidecar check
(intl_shadow.check_copy's rule: immutable=1 ignores a -wal, -shm or -journal file, so committed pages still in a WAL
would read as missing). `connect_copy(path)` opens it through "?mode=ro&immutable=1" (sp_common.copy_connect's URI),
which creates nothing beside the file; there is no fallback to a plain path, which is a read-write open at the file
level and can write sidecars beside a copy (#421's fallback, kept for the live file alone)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

COPY_URI_QUERY = "?mode=ro&immutable=1"
SIDECARS = ("-wal", "-shm", "-journal")
EXIT_REFUSED = 2


class CopyRefused(Exception):
    """A --db the rule refuses before any open; str(e) names the case and the path, never a row."""


def app_db() -> Path | None:
    """The app's configured SQLite file, resolved (mlb_pitchers_gate._app_db); None when no configuration is loaded or
    it is another backend (582 item 4(d): then nothing reads as live)."""
    from src.walters import mlb_pitchers_gate as mp
    return mp._app_db()


def _resolve(db) -> Path:
    """The --db, resolved; CopyRefused, nothing opened, when it cannot be (a symlink loop, an unreadable folder)."""
    try:
        return Path(str(db)).expanduser().resolve()
    except (OSError, RuntimeError) as err:
        raise CopyRefused(f"REFUSED: --db {db}: the path cannot be resolved ({err.__class__.__name__}); nothing "
                          "read") from None


def is_live(db) -> bool:
    """True when `db` is the app's configured database by resolved path or by identity (582 item 4(a))."""
    from src.walters import mlb_pitchers_gate as mp
    app = app_db()
    if app is None or db is None or not str(db).strip():
        return False
    tgt = _resolve(db)
    return tgt == app or mp._same_file(tgt, app)


def sidecars(path: Path) -> list[str]:
    """The names of any -wal, -shm or -journal file beside `path` (an OSError is raised, never read as absent)."""
    found = []
    for s in SIDECARS:
        side = path.with_name(path.name + s)
        if side.exists() or side.is_symlink():
            found.append(side.name)
    return found


def check_copy(db) -> Path:
    """The copy's fence (582 item 4(b)): CopyRefused, nothing opened, when the path resolves under data/ (law 5; a hard
    link into it or a folder it links to included), is the app's configured database, does not exist, or has a sidecar
    beside it; else the resolved path."""
    from src.walters import mlb_pitchers_gate as mp
    if db is None or not str(db).strip():
        raise CopyRefused("REFUSED: --db is empty: name the app's configured database or a .backup copy outside "
                          "data/; nothing read")
    _resolve(db)                                              # a path that cannot resolve is refused in one line
    try:
        path = mp.check_db(db)
    except mp.GateRefused as e:                               # the fence's own words, spoken for any reader, not the gate
        raise CopyRefused("REFUSED: " + str(e).replace("; the gate never creates one", "; nothing created, nothing read")
                          ) from None
    try:
        sides = sidecars(path)
    except OSError as err:                                   # law 4: an unreadable neighbour is never "no sidecar"
        raise CopyRefused(f"REFUSED: --db {db}: a sidecar beside it cannot be checked ({err.__class__.__name__}); "
                          "nothing read") from None
    if sides:
        raise CopyRefused(f"REFUSED: --db {db} has a {sides[0][len(path.name):]} sidecar ({sides[0]}): not a fresh "
                          ".backup copy; immutable=1 would ignore it and read a stale store; take a fresh .backup copy; "
                          "nothing read")
    return path


def classify(db) -> tuple[str, Path]:
    """("live", path) for the app's configured database (it keeps its open), else ("copy", path) after check_copy;
    CopyRefused before any open otherwise. A missing --db is the caller's: this is only asked of a --db given."""
    if is_live(db):
        return "live", _resolve(db)
    return "copy", check_copy(db)


def copy_uri(path: Path) -> str:
    """The copy's URI: the percent-encoded file URI (a '#' or '?' in the path cannot cut it) and "?mode=ro&immutable=1"."""
    return Path(path).resolve().as_uri() + COPY_URI_QUERY


def connect_copy(path: Path) -> sqlite3.Connection:
    """sqlite3 on a checked copy through mode=ro&immutable=1: never created, never written, nothing beside it; no
    fallback; CopyRefused when SQLite cannot open it (an unreadable file), so the caller prints one line, exit 2."""
    try:
        return sqlite3.connect(copy_uri(path), uri=True)
    except sqlite3.Error as err:                              # a file the fence passed but SQLite cannot open: one
        raise CopyRefused(f"REFUSED: --db {path}: cannot be opened through a mode=ro&immutable=1 URI "   # line, exit 2
                          f"({err.__class__.__name__}); no fallback; nothing read") from None


def copy_engine(path: Path):
    """A SQLAlchemy engine on a checked copy through the same URI (mlb_pitchers_gate.readonly_session's pattern): the
    sqlite3 connection is made by connect_copy, so no dialect can rewrite the URI or drop immutable=1; NullPool."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    return create_engine("sqlite://", creator=lambda: connect_copy(path), poolclass=NullPool)


def require_live(db) -> Path:
    """582 item 4(c), for the two live-file receipts: the resolved path when `db` is the app's configured database,
    else CopyRefused naming the copy open this receipt does not take."""
    if is_live(db):
        return _resolve(db)
    raise CopyRefused(f"REFUSED: --db {db} is not the app's configured database: this receipt reads the live file "
                      "only (its data_version check means something only on a file being written) and takes no copy "
                      "open (mode=ro&immutable=1); nothing read")
