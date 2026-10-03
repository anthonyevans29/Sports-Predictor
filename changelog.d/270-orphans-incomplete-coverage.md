## 2026-10-03 (#270: dedupe-matches --orphans: incomplete lookup coverage leaves the whole candidate set UNRESOLVED)
- PR #266 review (Anthony) found two cases on `d14c3f83`. A failed date lookup plus one observed provider game still permitted a RELINK. One found twin plus an unresolved competing twin still permitted a MERGE.
- Now a twin whose provider lookup errors, or any day of the ±2d search that fails, leaves the candidate and every twin it was weighed against UNRESOLVED and untouched (no merge, no relink) until complete lookups establish uniqueness. The plan line names the gap.
- tests/test_dedupe_orphans.py (+1): both cases, dry-run and apply, with ids, rows and references unchanged. The test was verified to fail on the old code (it relinked).
