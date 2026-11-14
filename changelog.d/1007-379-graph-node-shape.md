## 2026-11-14 (#1007: 379-graph-node-shape — the availability graph's node shape: each assertion a node; ten times today's record builds inside the unit's 1536M (ARCHITECT 2026-11-14, addendum 379 item 2; #995))
- **The shape (379 item 2, amending 252 item 4's "an edge per assertion"):**
  - `Assertion` is a node carrying every property the FACT edge carried, unchanged: kind, both stamps, the derived interval under each clock, attrs, game, backfilled and post_hoc.
  - Its player, team and observation are property-less, forward-only edges: `NAMES_PLAYER`, `NAMES_TEAM` and `ASSERTED_IN`. A directed pattern reads them from either end; the engine refuses an undirected one over a forward-only table.
  - FACT and ASSERTED go. IN_GAME and ABOUT are unchanged.
- **Both counts on the line (379 item 2):** the line names the record's assertions (a COUNT on the copy) beside the graph's assertion nodes, and a build whose two counts differ fails. The line also carries the staging's bytes on disk, and the CLI prints both counts, the staged bytes and the pool.
- **The load, restated on the shape's measured need (379 item 2; the engine's v0.22.3 source cited in graph.py):**
  - **The walk:** the record's own read stays the only read. It stages in a forked child that exits before the load; SIGTERM is blocked across the fork.
  - **The nodes:** COPYs of 100,000 rows, with the database closed and reopened every 10 and between tables. A checkpoint leaves string de-duplication tables on the heap until a close.
  - **Each relationship table:** ONE COPY into the empty table. A later COPY would build a per-group CSR index for every node group of the assertions.
  - **The pool:** a sixth of the limit, 256 MiB under the unit. 64 MiB fails; 128 and 256 MiB build.
- **Receipts:** synthetic records, the real command inside a 1536M cgroup on 2 CPUs.

  | Size | Seconds | Process peak RSS | Graph |
  |---|---|---|---|
  | Today's (1,341,556 assertions) | 118.7 | 436 MiB | 156 MB |
  | Three times | 380.1 | 589 MiB | 470 MB |
  | Ten times (13,415,544) | 1577.2 | 920 MiB | 1.81 GB |

  - **What still grows:** the walk's own partition, 888 MiB at ten times today's.
  - **Before the fixes:** ten times today's was killed by MemoryMax under the node shape's first load.
- **Docs:** the spec's section 11, the candidates page's "after the pick" note and docs/CLI.md's row are brought to the shape.
- **Tests:** tests/test_availability_graph.py, 37 passed and 11 skipped without the engine; 47 passed and 1 skipped with ladybug 0.22.3. The full suite passed: 7984 passed, 24 skipped, 5 xfailed. Every new test failed first.
