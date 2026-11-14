**2026-11-14 — The availability graph's node shape: each assertion a node (addendum 379 item 2); ten times today's record builds inside the unit's 1536M (#1007, carrying #995).**
- **Ruling (379 item 2, verbatim in part):** "THE THREE-TIMES CHOICE (#995) — RULED: (B), AND NOT AS AN EXPERIMENT. THE GRAPH'S SHAPE CHANGES: EACH ASSERTION IS A NODE. This amends addendum 252 item 4's 'an edge per assertion'. MemoryMax stays 1536M; (A) is declined: a larger limit on a host with no swap only moves the night it fails."
- **The shape:** `Assertion` nodes carry FACT's properties unchanged. `NAMES_PLAYER`, `NAMES_TEAM` and `ASSERTED_IN` are property-less, forward-only edges from each assertion. The line names the record's assertions beside the graph's assertion nodes, and a build fails if they differ.
- **What the ten-times measurement found:** ten times today's was killed by MemoryMax under the node shape's first load. Three causes, each measured and each found in the engine's v0.22.3 source:
  1. **The record's walk** holds 888 MiB of heap at ten times today's.
  2. **A node checkpoint** that rewrites a string segment leaves its de-duplication table on the heap until a close.
  3. **A relationship COPY into a non-empty table** builds a CSR index for every node group of the assertions, about 8 MiB a group.
- **The load as built:**
  - the walk in a forked child, with SIGTERM blocked across the fork;
  - the nodes in COPYs of 100,000 rows, with the database reopened every 10 and between tables;
  - each relationship table in one COPY into the empty table;
  - the pool a sixth of the limit, 256 MiB.
- **Receipts inside 1536M:**

  | Size | Seconds | Process peak RSS |
  |---|---|---|
  | Today's | 118.7 | 436 MiB |
  | Three times | 380.1 | 589 MiB |
  | Ten times | 1577.2 | 920 MiB |

  What still grows with the record is the walk's longest partition.
- **#995:** carried by #1007. The 11-25 step stands: the architect's block enables on a build, on whichever shape the tag before it carries.
