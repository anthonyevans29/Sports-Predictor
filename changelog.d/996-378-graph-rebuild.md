## 2026-11-14 (#996: 378-graph-rebuild — the graph rebuild's two host faults: data/ an empty read-only folder in its unit; the engine's pool half the limit it runs under; the staged size on its line (ARCHITECT 2026-11-14, addendum 378 items 3 and 4))
- **The fence against the unit's own line (item 3):** `deploy/hosting/systemd/sp-availability-graph.service` changes exactly the two lines the probe ran:
  - `InaccessiblePaths=/etc/sports-predictor`;
  - data/ joins `TemporaryFileSystem` as `/opt/sports-predictor/data:ro`.

  The header says the empty-folder walk is accepted HERE AND ONLY HERE. `check_db` is unchanged. A test pins both lines, and asserts that no unit running the app puts a fenced data/ (or a folder above it, or one below it) on InaccessiblePaths.
- **The pool as a rule tied to MemoryMax (item 4(c)):** `src/availability/graph.py` drops the bare 256 MiB `BUFFER_POOL`.
  - The pool is half the smaller of the process's cgroup memory limit, read at run time (v2 or v1), and `UNIT_MEMORY_MAX`, the unit's 1536M, which a test pins against the unit. That gives 768 MiB under the unit.
  - `auto_checkpoint` is set ON. The engine's docstring, docs and v0.22.3 source were read first and are quoted. Every COPY forces a checkpoint, every Player sits in one 2^17-node group, and a checkpoint's buffers never spill, so the pool a FACT checkpoint needs grows with the record.
- **The line (items 4(d) and 4(e)):**
  - It carries the staged counts, the limit, where the limit was read and the pool, before the load starts.
  - The staging directory keeps the staged size until the commit point, so a killed run's size is named by the next run (`stale_staged`).
  - A failed build still exits 1 with the previous graph untouched and its line written.
- **Receipts:** synthetic records only, run inside a 1536M cgroup on 2 CPUs.
  - **1×:** main fails as the host did (113.9 s). The head builds in 153.0 s (RSS 743 MiB, a 202 MB graph).
  - **3× does NOT build inside 1536M** at any pool from 256 to 1024 MiB. The last COPY that built reached about 3.2–3.5M FACT edges at the rule's 768 MiB.
  - **The choice, for the architect:** a larger MemoryMax (2560M builds 3× in 565.6 s, RSS 1813 MiB), or assertions as nodes (3× builds at 256 MiB). See #995 (`needs-ruling`).
- **The pre-PR adversarial pass:** three P2s fixed fail-first. One question goes to the architect: whether the host's /dev/shm is writable inside the unit under PrivateDevices.
- **Codex's review rounds on #996:**
  - **Round 1:** two P2s, fixed fail-first in c986d84f. A finite cgroup v2 limit is now kept even at or above the machine's RAM, and the staged size is now kept through the commit point.
  - **Round 2:** one P2, a finite cgroup v1 limit at or above RAM read as no limit. It is listed for the architect (378 item 5) and not changed here.
- **The third ruled line (addenda 379 item 3 and 380 item 2):** `/dev/shm:ro` joins `TemporaryFileSystem`.
  - The host showed that PrivateDevices binds its own /dev/shm, writable, into the unit: a file written from inside was present in the host's /dev/shm (380 item 1).
  - The header now names what makes each part of "the one writable path" true: ProtectSystem=strict, TemporaryFileSystem, PrivateIPC and ReadWritePaths.
  - The test pins all four TemporaryFileSystem entries.
  - The rebuild builds with /dev/shm read-only in Dev 2's container (135.7 s, RSS 776 MiB).
- **cgroup v1 (379 item 4):** a finite v1 limit at or above the machine's memory is a limit. Only the kernel's own no-limit value, 9223372036854771712 on 4 KiB pages, reads as none.
- **The spec's unit paragraph** says what the unit does with data/ and /dev/shm.
- **Tests:** tests/test_availability_graph.py, 32 passed and 11 skipped without the engine; 42 passed and 1 skipped with ladybug 0.22.3.
