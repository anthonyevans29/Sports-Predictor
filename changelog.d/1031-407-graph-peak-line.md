## 2026-11-16 (#1031: 407-graph-peak-line — the graph rebuild's receipt line carries the run's peak (ARCHITECT 2026-11-16, addendum 407 item 3; #1010))
- **src/availability/graph.py:** every rebuild line (success, failure and refusal) carries `peak`:
  - `process_rss_kib` (RUSAGE_SELF);
  - `children_rss_kib` (RUSAGE_CHILDREN, the staging child once waited for);
  - `cgroup_peak_bytes` and `cgroup_peak_from`, the process's own cgroup read while the unit runs (memory.peak on v2, memory.max_usage_in_bytes on v1).

  A part that cannot be read is null with its reason, never a failed run. `_cgroup_peak` sits beside `_cgroup_limit`.
- **Untouched:** the build, the pool rule, the unit file and the walk. #1010 stays open.
- **Receipt:** the real 1× build in the 1536M rig at 9efff9b7 wrote process 439,816 KiB (429.5 MiB) and cgroup 1,410,441,216 bytes (1,345 MiB). Both agree with the rig's own measures.
- **Docs and tests:** the spec's section 11 says what the line carries. Three new tests, each failing first.
