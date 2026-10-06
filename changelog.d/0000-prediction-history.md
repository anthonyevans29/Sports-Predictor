## 2026-10-06 (#0000: prediction-history — every prediction write kept as a series, #87 K-track — ARCHITECT)
- New APPEND-ONLY `prediction_history` table: `match_id`, `model_version`, `computed_at`, the home/draw/away probabilities, and `recorded_at`.
  - Every `Prediction` insert, from any write path (`predict-nfl`, soccer and MLB predict), is appended at flush in the same transaction. A rolled-back run leaves no history.
  - `predictions` stays current-only (S13). The window chain's hourly re-predicts become a stored series, so model-vs-cost is evaluable per Kalshi capture.
- New `migrate_prediction_history.py`: additive and idempotent, with a receipt. There is no backfill, because overwritten predictions are gone.
  - Before it runs, predictions still write and the skipped history is logged as a warning.
- Chain receipts count `prediction_history`. The count is null until the migration runs.
