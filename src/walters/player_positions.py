"""
THE POSITION LOOKUP'S STORE (ARCHITECT 2026-10-12, addendum 44 item 4).

"A listed player whose position the roster does not give is asked for by his provider id. The answer is kept, so a
player is asked once and not at every read." The answers live in player_position_answers (src/db/schema.py
PlayerPositionAnswer), created by migrate_player_position_answers.py. Every read and write here is guarded by the
table's existence, checked per call and never cached (as has_prediction_history): "a pull or a deploy before any
migration keeps working". Before the migration nothing is read or kept, so the players are asked at every read.
Nothing here touches the odds tables.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, select

log = logging.getLogger(__name__)

TABLE = "player_position_answers"


def table_ready(conn) -> bool:
    try:
        return inspect(conn).has_table(TABLE)
    except Exception:
        return False


def known_answers(session, source: str) -> dict:
    """{provider player id (str): position or None} for every answer kept from `source`; {} before the migration."""
    from src.db.schema import PlayerPositionAnswer
    if not table_ready(session.connection()):
        return {}
    session.flush()                  # the session does not autoflush: an answer kept earlier in this run is read too
    rows = session.execute(select(PlayerPositionAnswer.player_id, PlayerPositionAnswer.position).where(
        PlayerPositionAnswer.source == source)).all()
    return {str(pid): pos for pid, pos in rows}


def keep_answers(session, source: str, answers: list[dict]) -> int:
    """Store new answers [{player_id, player_name, position}] (position None = answered with no position). An id
    already kept is left as it is. Returns how many were written; 0, with a warning, before the migration."""
    from src.db.schema import PlayerPositionAnswer
    from src.timeutil import utc_now_naive
    if not answers:
        return 0
    if not table_ready(session.connection()):
        log.warning("%s missing: %d position answer(s) not kept (asked again at the next read) — run "
                    "migrate_player_position_answers.py", TABLE, len(answers))
        return 0
    session.flush()                  # as above: a pending answer of this run counts as kept (one row per id)
    have = {pid for (pid,) in session.execute(select(PlayerPositionAnswer.player_id).where(
        PlayerPositionAnswer.source == source,
        PlayerPositionAnswer.player_id.in_([str(a["player_id"]) for a in answers])))}
    now, n = utc_now_naive(), 0
    for a in answers:
        pid = str(a["player_id"])
        if pid in have:
            continue
        have.add(pid)
        session.add(PlayerPositionAnswer(source=source, player_id=pid, player_name=a.get("player_name"),
                                         position=a.get("position"), answered_at=now))
        n += 1
    return n
