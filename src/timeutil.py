"""UTC clock (cosmetics sweep, architect 2026-09-29).

datetime.utcnow() / utcfromtimestamp() are deprecated (Python 3.12). These are
their EXACT replacements: built on datetime.now(timezone.utc) but returning
NAIVE UTC, because that is the storage convention: SQLite DateTime columns hold
naive UTC, every comparison in the codebase is naive-vs-naive, and exports
append a literal "Z" to .isoformat(). A bare aware now(UTC) would break all
three (TypeError on naive/aware compares; "+00:00Z" in exported timestamps).
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Naive UTC now — the drop-in for datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_naive_fromtimestamp(ts: float) -> datetime:
    """Naive UTC from a POSIX timestamp — the drop-in for datetime.utcfromtimestamp()."""
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
