"""
The api-sports game status both game adapters read (api_american_football: NFL and NCAA; api_hockey: NHL).

#493 (Codex P1 on #489, verified in code): each adapter set an absent status to "NS" before its score-presence check,
so the rule could match only the literal text "None" and never fired for an absent status. The ruling, verbatim
(ARCHITECT 2026-10-16, addendum 81 item 3): "the rule fires where it was meant to — a row whose provider status is
ABSENT (None at the source) and whose two scores are present is FINISHED; a row whose provider status is anything else
keeps it (law 4: a status the provider stated is never overridden by scores)." Addendum 112 item 4 (2026-10-17): "make
the check run on the provider's raw status before the NS default is applied; the rule stays "conservative unknowns":
no score → not FINISHED."

THE LITERAL TEXT "None" (read, law 1): neither adapter ever wrote it for an absent status. A null status becomes {}
before it is read (`game.get("status") or {}`), and a non-dict block is read as text only when it is not empty. So
"None" reaches the parse only as text the provider sent itself. The absent class the rule was written for had "NO
status block upstream (short=None, full totals present)" (the 16 NFL 2024 games, 2026-09-05). "None" is therefore a
STATED status. It is not in the map, so it stays SCHEDULED (law 4: unmapped statuses stay SCHEDULED), and scores never
override it. Before #493 that text with both scores read FINISHED. The dry run (src/ingestion/score_presence.py) lists
such rows apart, so a provider that does send the text is seen before anything is written.
"""
from __future__ import annotations

from src.db.schema import MatchStatus


def provider_short(status) -> str | None:
    """The provider's short status code as sent, read BEFORE any "NS" default. None = no status stated (ABSENT): the
    block missing, null or empty, or its short null or empty. Anything else is returned as text, verbatim (the literal
    "None" included: see the module's note)."""
    block = status or {}
    short = block.get("short") if isinstance(block, dict) else block
    return None if short is None or short == "" else str(short)


def game_status(short: str | None, mapping: dict, home_total, away_total) -> MatchStatus:
    """One game's status from its provider short (provider_short) and its two final totals.

    - A stated short keeps its mapping; a code the map lacks is SCHEDULED (law 4), whatever the scores.
    - ABSENT with both totals present: FINISHED. Score-presence beats status-absence (2026-09-05: 16 of 2024's NFL
      games arrived with NO status block at all but full final totals).
    - ABSENT with a total missing: what the "NS" default maps to (SCHEDULED). Conservative unknowns: no score, not
      FINISHED.
    """
    if short is None:
        if home_total is not None and away_total is not None:
            return MatchStatus.FINISHED
        return mapping.get("NS", MatchStatus.SCHEDULED)
    return mapping.get(short, MatchStatus.SCHEDULED)
