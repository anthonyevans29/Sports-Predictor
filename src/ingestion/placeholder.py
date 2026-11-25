"""The provider's TBD kickoff for the college schedule: ONE definition, shared (ARCHITECT 2026-10-09,
addendum 30 item 3: "What a placeholder is, and what resolves one, is already ruled (2026-10-05) and already
in code: is_placeholder_kickoff and placeholder_resolved in scripts/ncaa_rekey_receipt.py. One definition,
shared; not a second copy.").

Used by scripts/ncaa_rekey_receipt.py (the receipt's accounting) and src/ingestion/service.py (the NCAA
placeholder re-key window). Standard library only: the receipt script imports it without the ORM.

Noted, not ruled (addendum 30): the placeholder is midnight US Eastern, which is 04:00Z until the clocks
change on 2026-11-01. What the provider sends after that is not known; November's first listing decides.
Answered (ARCHITECT 2026-11-24, addendum 500 item 1(b), verbatim): "Eight of the nine sit at 04:00Z; 33608 at 19:00Z."

The provider's TBD TEAM (ARCHITECT 2026-11-24, addendum 500 Q2, verbatim): "ONE ID, 345, held as data in
placeholder.py beside the kickoff's definition, never matched by name." PLACEHOLDER_TEAM_ID and is_placeholder_team
below; the user is src/ingestion/service.py (the upsert's placeholder fill, addendum 500 Q1 to Q5).
"""
from __future__ import annotations

from datetime import timedelta

PLACEHOLDER_RESOLVE_H = 24
# The provider's TBD team (api_american_football), ARCHITECT 2026-11-24, addendum 500 item 1(a) ("ONE stored placeholder
# team (our team id 1636; the provider's team id 345)") and Q2, verbatim: "ONE ID, 345, held as data in placeholder.py
# beside the kickoff's definition, never matched by name."
PLACEHOLDER_TEAM_ID = "345"


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


def is_placeholder_team(team_sid) -> bool:
    """The provider's TBD team (addendum 500 Q2): its provider id is PLACEHOLDER_TEAM_ID, compared as a string; never
    matched by name."""
    return team_sid is not None and str(team_sid) == PLACEHOLDER_TEAM_ID
