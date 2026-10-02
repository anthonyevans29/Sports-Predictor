## 2026-10-02 (intl-venue-sync: fix the crash on /venues payloads with None fields)
- `src/ingestion/intl_venues.py`: the law-1 key receipt counts keys (`Counter.update(v.keys())`), not dict values, which crashed on a None field and would have summed numeric ones. Regression test on a real-shaped payload. A re-run with the same `--venues-dir` replays the saved responses.
