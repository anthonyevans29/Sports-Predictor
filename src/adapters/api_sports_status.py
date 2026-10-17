"""
The api-sports game status both game adapters read (api_american_football: NFL and NCAA; api_hockey: NHL).

#493 (Codex P1 on #489, verified in code): each adapter set an absent status to "NS" before its score-presence check,
so the rule could match only the literal text "None" and never fired for an absent status. The ruling, verbatim
(ARCHITECT 2026-10-16, addendum 81 item 3): "the rule fires where it was meant to — a row whose provider status is
ABSENT (None at the source) and whose two scores are present is FINISHED; a row whose provider status is anything else
keeps it (law 4: a status the provider stated is never overridden by scores)." Addendum 112 item 4 (2026-10-17): "make
the check run on the provider's raw status before the NS default is applied; the rule stays "conservative unknowns":
no score → not FINISHED."

Addendum 116 item 4 (ARCHITECT 2026-10-17 13:15 ET), items (3) and (4), verbatim:
"(3) The current season: add the kickoff-age condition. The rule marks a scoreless-status row FINISHED only when now >=
kickoff + the sport's longest game (SOCCER 3h, NHL 4h, NFL/NCAA 5h, MLB 6h — constants, named in the receipt); before
that it leaves the stored status alone. A game in play with running totals never reads FINISHED. The daily sync then
applies the rule safely; no operator block needed for new rows.
(4) The literal text "None": treated as NO status — the same as absent — never as a stated status. A FINISHED row with
scores and the text "None" stays FINISHED. Those rows are listed separately in the dry run for the record, nothing
flips."

So a game's status, from its provider short (provider_short) and its two totals (game_status):
  - a STATED short keeps its mapping; a code the map lacks is SCHEDULED (law 4), whatever the scores;
  - NO status (the block missing, null or empty, its short null or empty, or the literal text "None": no_status) with a
    total missing is what the "NS" default maps to (SCHEDULED): no score, not FINISHED;
  - NO status with both totals is FINISHED once now >= kickoff + LONGEST_GAME_H of the sport; before that the answer is
    None: NO STATUS FOR THIS GAME. IngestionService then leaves the stored row's status as it is
    (_apply_match_updates skips the column) and creates a new row SCHEDULED (created_status), so a game in play with
    running totals never reads FINISHED.
"now" is utc_now_naive() read at parse time (once per listing), or the caller's (tests, the dry run, the apply).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.db.schema import MatchStatus
from src.timeutil import utc_now_naive

#: ARCHITECT 2026-10-17, addendum 116 item 4 (3): each sport's longest game, in hours. A game with no status and both
#: totals reads FINISHED only when now >= kickoff + these hours. SOCCER and MLB are named as ruled; no soccer or MLB
#: parse carries the score-presence rule, so only NFL, NCAA and NHL are read today.
LONGEST_GAME_H = {"SOCCER": 3, "NHL": 4, "NFL": 5, "NCAA": 5, "MLB": 6}

#: The literal text the provider can send where a status would be (addendum 116 item 4 (4)): NO status.
NONE_TEXT = "None"


def provider_short(status) -> str | None:
    """The provider's short status code as sent, read BEFORE any "NS" default. None = no status sent: the block
    missing, null or empty, or its short null or empty. Anything else is returned as text, verbatim (the literal "None"
    included, so the dry run can list those rows apart; no_status reads it as no status)."""
    block = status or {}
    short = block.get("short") if isinstance(block, dict) else block
    return None if short is None or short == "" else str(short)


def no_status(short: str | None) -> bool:
    """True when a provider short (provider_short) states NO status: none sent, or the literal text "None" (addendum
    116 item 4 (4): "the same as absent — never as a stated status")."""
    return short is None or short == NONE_TEXT


def sport_key(competition_code: str | None, sport=None) -> str:
    """The LONGEST_GAME_H key of an api-sports game: NHL for a hockey game (`sport` NHL: the hockey adapter reads NHL's
    hours whatever the competition's code) or the code NHL; NCAA by its code; NFL otherwise (the american-football
    adapter's default league)."""
    if getattr(sport, "name", sport) == "NHL":
        return "NHL"
    code = (competition_code or "NFL").upper()
    return code if code in ("NCAA", "NHL") else "NFL"


def rule_now(now: datetime | None = None) -> datetime:
    """The clock the rule reads: `now` when given, else naive UTC now (the repo's clock, src/timeutil.py)."""
    return utc_now_naive() if now is None else now


def longest_game_text() -> str:
    """The constants as a receipt names them: "SOCCER 3h · NHL 4h · NFL 5h · NCAA 5h · MLB 6h"."""
    return " · ".join(f"{k} {h}h" for k, h in LONGEST_GAME_H.items())


def game_status(short: str | None, mapping: dict, home_total, away_total, kickoff: datetime | None, sport: str,
                now: datetime | None = None) -> MatchStatus | None:
    """One game's status from its provider short (provider_short), its two final totals and its kickoff.

    - A stated short keeps its mapping; a code the map lacks is SCHEDULED (law 4), whatever the scores.
    - NO status (no_status) with a total missing: what the "NS" default maps to (SCHEDULED). Conservative unknowns: no
      score, not FINISHED.
    - NO status with both totals: FINISHED when now >= kickoff + LONGEST_GAME_H[sport] (score-presence beats
      status-absence, 2026-09-05: 16 of 2024's NFL games arrived with NO status block at all but full final totals).
      Before that, or with no kickoff to age, None: no status for this game, the stored status is left alone (a game in
      play with running totals never reads FINISHED).
    """
    if not no_status(short):
        return mapping.get(short, MatchStatus.SCHEDULED)
    if home_total is None or away_total is None:
        return mapping.get("NS", MatchStatus.SCHEDULED)
    if kickoff is not None and rule_now(now) >= kickoff + timedelta(hours=LONGEST_GAME_H[sport]):
        return MatchStatus.FINISHED
    return None
