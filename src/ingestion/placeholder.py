"""The provider's TBD kickoff for the college schedule: ONE definition, shared (ARCHITECT 2026-10-09,
addendum 30 item 3: "What a placeholder is, and what resolves one, is already ruled (2026-10-05) and already
in code: is_placeholder_kickoff and placeholder_resolved in scripts/ncaa_rekey_receipt.py. One definition,
shared; not a second copy.").

Used by scripts/ncaa_rekey_receipt.py (the receipt's accounting) and src/ingestion/service.py (the NCAA
placeholder re-key window). Standard library only: the receipt script imports it without the ORM.

Noted, not ruled (addendum 30): the placeholder is midnight US Eastern, which is 04:00Z until the clocks
change on 2026-11-01. What the provider sends after that is not known; November's first listing decides.
"""
from __future__ import annotations

from datetime import timedelta

PLACEHOLDER_RESOLVE_H = 24


def is_placeholder_kickoff(dt) -> bool:
    """The provider's TBD kickoff (ARCHITECT 2026-10-05): 04:00:00Z (midnight US Eastern)."""
    return dt is not None and (dt.hour, dt.minute, dt.second) == (4, 0, 0)


def placeholder_resolved(pre, post) -> bool:
    """A placeholder 04:00Z kickoff that became a REAL kickoff within 24h (ruled accounted, 2026-10-05);
    a move onto another placeholder time is a date change, never accounted (#279 review)."""
    if pre is None or post is None or pre == post:
        return False
    return (is_placeholder_kickoff(pre) and not is_placeholder_kickoff(post)
            and abs(post - pre) <= timedelta(hours=PLACEHOLDER_RESOLVE_H))
