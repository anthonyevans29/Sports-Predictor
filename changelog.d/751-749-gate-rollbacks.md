## 2026-10-31 (#751: 749-gate-rollbacks — the mlb-pitchers-v1 gate's three write-failure paths refuse and leave nothing; #749 items 1–3, addendum 194 item 2)
- src/walters/mlb_pitchers_gate.py `reserve`: a write that fails after the reservation's exclusive create removes the file and refuses (GateRefused, REFUSED exit 2), naming the error: the one run is not spent and nothing is read (#749 item 1, the law-3 hazard).
- `frozen_ids`: a token in the frozen cohort file that is not an id refuses, naming the file, before the reservation (#749 item 2); it was a ValueError traceback.
- `freeze`: one rollback around the whole sequence: the cohort file's create and write, the ledger's reload and save. Any failure removes the file the call created and puts the ledger's bytes back, because `registry.save` truncates before it writes. It then refuses, naming what was undone (#749 item 3). This replaces #748's save-only rollback.
- Tests (tests/test_mlb_pitchers_v1.py):
  - a half-written reservation is removed and the next reservation goes through;
  - a conflict-marker token refuses, naming the file, with nothing reserved;
  - a failed reload, and a save that truncates the ledger and then fails, each leave no file and the ledger byte-identical, and the next freeze goes through.
- Codex round 1 on #751: the freeze restores the ledger only when the failure came in or after its own save, so another command's update is never overwritten. A reservation whose cleanup also fails says the file remains and must be removed by hand, never that the run is not spent. A test for each.
