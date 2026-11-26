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


def oldest_source_time(rows):
    """The source time of a set of rows (ARCHITECT 2026-10-09, addendum 32
    item 4: "where a session's rows differ, the oldest"). A row without one
    has an UNKNOWN source time, and unknown is never read as fresh (item 3):
    so any unknown row, or no rows, makes the whole set unknown (None)."""
    times = [getattr(r, "source_updated_at", None) for r in rows]
    if not times or any(x is None for x in times):
        return None
    return min(times)


def iso_z_seconds(t: datetime | None) -> str | None:
    """An instant as ISO Z in whole seconds, the closing watch's own format (deploy/hosting/closing.py iso_z: a naive
    time read as UTC, an aware one converted; the fraction cut, never rounded). None stays None (law 4). #1102 PR1:
    the export's capture stamps (F2-F4) are written in it."""
    if t is None:
        return None
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# #1102 F1's one form (ARCHITECT 2026-11-25, addendum 555 item 1 Q2, verbatim): "F1's FORM IS THE CLI's SIX-DIGIT FORM
# AND NOTHING ELSE, by ONE definition in timeutil that the option and the Desk both call. PR1's refusals of a bad value
# stay as they are, test for test." cli.py's --run-start (export-predictions, export-nfl-predictions) refuses what this
# does not read; the Desk's stale-price rule (src/walters/desk_policy.py run_start_reading) reads a file's
# run_started_at through it.
RUN_START_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"


def parse_run_start(value) -> datetime | None:
    """A slate run's held start in the CLI's one form, YYYY-MM-DDTHH:MM:SS.ffffffZ (ASCII digits, exactly six of the
    fraction), as a naive UTC datetime WITH its microseconds; None for anything else (another form, a non-str, a date
    that does not exist). A regex, then strptime, never datetime.fromisoformat, which refuses the "Z" on the laptop's
    Python 3.10."""
    import re
    if not isinstance(value, str) or not re.fullmatch(RUN_START_PATTERN, value, re.ASCII):   # ASCII digits only
        return None
    try:
        return datetime.strptime(value[:-1], "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return None
