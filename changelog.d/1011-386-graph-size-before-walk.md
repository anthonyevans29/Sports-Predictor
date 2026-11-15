## 2026-11-15 (#1011: 386-graph-size-before-walk — the graph rebuild's line names the record's size before the walk starts (ARCHITECT 2026-11-15, addendum 386 item 1; #1010(a)))
- **src/availability/graph.py:** the parent counts the copy's assertions (`_record_assertions`, a COUNT in its own mode=ro + immutable=1 session) before the staging child is forked, and writes `record_assertions` on the run's line then.
  - A night that dies in the walk, with the child taken by MemoryMax ("the staging child gave no answer (exit -9)"), now names the size it died at, where before its line named none.
  - 379 item 2's check reads the same count; the child no longer counts.
- **docs/specs/availability-record.md section 11** says so.
- **Tests:** a new test kills the child outright, as MemoryMax would, and reads the line: `record_assertions` present, `staged` absent. It fails first on e3f55ee2. tests/test_availability_graph.py: 38 passed and 11 skipped without the engine; 48 passed and 1 skipped with ladybug 0.22.3.
- **#1010 stays open:** it records a limitation (the walk's heap grows with the record), not this line.
