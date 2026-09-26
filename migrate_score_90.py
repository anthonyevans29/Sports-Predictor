"""
Migration (2026-09-26): matches.home_score_90 / away_score_90 — soccer's
90-minute score (API-Football score.fulltime, stored verbatim).

Adds to matches:
  - home_score_90  INTEGER   (NULL until the next sync touches the row)
  - away_score_90  INTEGER

Why: home/away_score are API-Football `goals`, which INCLUDE extra time
(pens excluded), so knockout ties level at 90' and decided in ET read as
wins against a 90-minute 1X2 price (the fix-v2 ET label-contamination
finding; architect data item 2026-09-25). The ET flag itself is
matches.status_raw in (AET, PEN) — stored by the same sync (no new column).
Storage only: no label, model or export reads these columns. Additive
and idempotent: safe to run repeatedly; never deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5), then run this BEFORE any
chain after merging — the ORM now maps the columns, so queries on `matches`
fail with "no such column" until they exist. Requires migrate_status_raw.py
(already run for the NHL item).

Receipt: soccer FINISHED rows by status_raw, plus the 90-minute INVARIANTS
that verify the provider's semantics against our reading (law 1):
  * AET / PEN rows must be LEVEL at 90' (else score.fulltime is not 90').
  * FT rows' 90-minute score must EQUAL the stored score.
Right after migrating everything is NULL; populated going forward by the
normal syncs (a re-sync of a competition backfills it, e.g.
`python cli.py sync-matches --competition CL --seasons 2`).

Usage:
    python migrate_score_90.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine

NEW_COLS = ("home_score_90", "away_score_90")


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    if "matches" not in inspector.get_table_names():
        print("✗ matches table doesn't exist — nothing to migrate.")
        return 1

    cols = {c["name"] for c in inspector.get_columns("matches")}
    if "status_raw" not in cols:
        print("✗ matches.status_raw missing — run migrate_status_raw.py first.")
        return 1
    with engine.begin() as conn:
        for col in NEW_COLS:
            if col in cols:
                print(f"· matches.{col} already exists.")
            else:
                print(f"+ Adding matches.{col}...")
                conn.execute(text(f"ALTER TABLE matches ADD COLUMN {col} INTEGER"))

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COALESCE(status_raw, '(null)') AS raw, COUNT(*), "
            "  SUM(home_score_90 IS NOT NULL AND away_score_90 IS NOT NULL), "
            "  SUM(home_score_90 = away_score_90), "
            "  SUM(home_score_90 = home_score AND away_score_90 = away_score) "
            "FROM matches WHERE sport = 'SOCCER' AND status = 'FINISHED' "
            "GROUP BY raw ORDER BY raw"
        )).all()
    # print(), not rich: pasteable receipt lines
    print("\nSoccer FINISHED rows by status_raw (receipt):")
    print(f"  {'raw':<8} {'rows':>7} {'with_90':>8} {'level_90':>9} {'90==score':>10}")
    if not rows:
        print("  (no soccer finished rows)")
    breaches = []
    for raw, n, w90, lvl, same in rows:
        w90, lvl, same = int(w90 or 0), int(lvl or 0), int(same or 0)
        print(f"  {raw:<8} {n:>7} {w90:>8} {lvl:>9} {same:>10}")
        if raw in ("AET", "PEN") and lvl != w90:
            breaches.append(f"{raw}: {w90 - lvl} row(s) NOT level at 90'")
        if raw == "FT" and same != w90:
            breaches.append(f"FT: {w90 - same} row(s) with 90' score != stored score")
    print("\nInvariants (AET/PEN level at 90'; FT 90' == score): "
          + ("HOLD" if not breaches else "BREACHED — " + "; ".join(breaches)))
    print("with_90 = 0 everywhere = not re-synced yet (populates going forward).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
