"""
Migration (2026-10-06, ARCHITECT #87 K-track, prediction_history lane):
creates prediction_history — an APPEND-ONLY series of every prediction write
(match_id, model_version, computed_at, home/draw/away probabilities,
recorded_at), so model-vs-cost is evaluable per Kalshi capture.

Why (K-track receipt 2026-10-06): `predictions` is current-only per match
(S13), so each re-predict overwrote the last; NFL 47/65 captures were not
evaluable. From this migration on, every Prediction insert is copied into
prediction_history in the same transaction (src/db/database.py).
Backfill is impossible (overwritten rows are gone) and is not attempted.
Additive and idempotent: creates one table and one index if missing; never
deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5); on the host, sp_deploy
prints the exact `--run-migrations` command (backup + this, under one lock).
Until it runs, predict commands still work and log that history was skipped.

Usage:
    python migrate_prediction_history.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine
from src.db.schema import PredictionHistory


def main() -> int:
    engine = get_engine()
    names = inspect(engine).get_table_names()
    if "matches" not in names:
        print("✗ matches table doesn't exist — not a sports_predictor DB; nothing to migrate.")
        return 1
    if "prediction_history" in names:
        print("· prediction_history already exists.")
    else:
        print("+ Creating prediction_history...")
        PredictionHistory.__table__.create(engine, checkfirst=True)
    with engine.connect() as conn:
        n, last = conn.execute(text("SELECT COUNT(*), MAX(recorded_at) FROM prediction_history")).one()
        live = conn.execute(text("SELECT COUNT(*) FROM predictions")).scalar()
    print(f"\nprediction_history: {n} rows (latest recorded {last or '—'}); predictions (current-only): {live}")
    print("0 rows = no predict run since migrating (no backfill: overwritten predictions are gone).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
