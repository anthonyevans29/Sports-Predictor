"""
The migrations' shared guard (ARCHITECT 2026-10-17, addendum 112 item 1; Issue #524): "every migration refuses when
the file is absent ("no database at <path>; a migration never creates one — law 5"), exit 1, nothing written; one
shared guard in the migrations' common helper".

Why: the migrate_*.py scripts reach the DB through the app's engine, whose connect hooks (src/db/database.py) create
what is missing: do_connect makes the directory, connect sets PRAGMA journal_mode=WAL on a new, empty file. That is
the 2026-10-06 incident's shape (an empty DB under data/). The engine object makes no connection until first used,
so a check before that first use writes nothing.

Usage (the first lines of every migration's main):
    engine = get_engine()
    if refuse_missing_db(engine):                               # law 5: a migration never creates a database
        return 1
"""
from __future__ import annotations

from pathlib import Path


def refuse_missing_db(engine) -> bool:
    """True, after printing the refusal, when there is no database file at the engine's configured path.

    The path is the engine's own URL, the file the SQLite driver would open: `settings.database_url` for the app's
    engine (src/db/database.py), a relative path resolved against the working directory as SQLite resolves it. An
    in-memory SQLite URL has no file and is refused too. A non-SQLite URL passes: no file to check, and connecting to
    a server never creates its database."""
    url = engine.url
    if url.get_backend_name() != "sqlite":
        return False
    db = url.database
    path = Path(db).resolve() if db and db != ":memory:" else None
    if path is not None and path.is_file():
        return False
    print(f"no database at {path or ':memory:'}; a migration never creates one — law 5")
    return True
