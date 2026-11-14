**2026-11-14 — The graph rebuild's two host faults fixed (ARCHITECT addendum 378 items 3 and 4); three times today's record does not build inside 1536M, and the choice is the architect's (#995).**
- **Ruling, item 3 (verbatim):** "RULED: the unit changes, the fence does not. "InaccessiblePaths=/etc/sports-predictor" and data/ joins TemporaryFileSystem as ":ro", exactly the two lines the probe ran. Inside this unit the fence then walks an empty folder; that is accepted HERE AND ONLY HERE, because the live file is not in the unit's view at all, the copy is taken only with a matching sha256 sidecar that sp_backup wrote, the open is mode=ro with immutable=1, and ProtectSystem=strict leaves no write path outside the graph's folder. Not one line of check_db loosens for it."
- **Fault one (#996):** the unit's two lines, its header in those terms, and a test that no unit running the app puts a fenced data/ on InaccessiblePaths.
- **Fault two (#996):** the engine's pool is half the limit the rebuild runs under, capped at the unit's MemoryMax, so 768 MiB under the unit. `auto_checkpoint` is ON. The line carries the staged size, the limit and the pool before the load starts.
- **Finding (#995, `class:limitation`, `needs-ruling`):** from the engine's own v0.22.3 source:
  - every COPY forces a checkpoint;
  - every Player sits in one 2^17-node group, which the checkpoint rewrites in memory, unspilled.

  So the pool a FACT checkpoint needs grows with the record. Measured on synthetic records inside 1536M: 1× builds at the rule's 768 MiB; the last COPY that still built reached about 3.2–3.5M FACT edges (2.4–2.6×); 3× fails at every pool from 256 to 1024 MiB.
- **The choice, for the architect:**
  - **(A) A larger MemoryMax:** 2560M builds 3× in 565.6 s, RSS 1813 MiB, on a host with 3,381 MB available and no swap.
  - **(B) Assertions as nodes:** 3× builds at a 256 MiB pool in about 117 s, but it changes 252 item 4's ruled shape.

  The limit is not raised (item 4(b)).
- **Question for the architect:** the pre-PR pass reports that systemd's PrivateDevices binds the host's /dev/shm writable into the unit. If so, the ruled condition "ProtectSystem=strict leaves no write path outside the graph's folder" is not quite true. A one-line fix is offered; not changed here.
- **State:** the timer stays on THE HELD LIST. The fix rides the next tag. Then the architect's block installs the unit file, runs it once and enables it only on a build (item 5).
