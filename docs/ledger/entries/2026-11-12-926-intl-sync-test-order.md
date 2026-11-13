**2026-11-12 — FIXED (#926; ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 5): the intl test's test-order dependency.**
- **Found by pair bisection on main 981734a4:** each earlier module was run with the failing test alone. Only `test_scores_by_team.py` fails it: its intl-history test leaves a reversed UNL 2073 row, and `intl-coverage`'s whole-DB count then reads 2 where the test asserted 1.
- **The fix:** the test asserts its own row as the count before plus one. It passes alone, after `test_scores_by_team.py`, before it, and in the Issue's five-module order, on 3.12 and 3.10.
- **Not a code defect:** the command counts the database it is given, as built.
