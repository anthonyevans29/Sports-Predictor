**2026-11-12 — FIXED (#940; ARCHITECT 2026-11-11 19:50 ET, addendum 347 item 3): three fail-safe nits in `intl-elo-confirm --db`, carried by one follow-up Issue instead of a third review round on #938.**
- **As built:**
  - A sidecar that cannot be checked refuses (exit 2), never a traceback, and is never read as absent. A copy name too long for its sidecar names is one such case, and only it gets the shorter-name advice. After the read, the refusal says "nothing recorded".
  - The post-read `OSError` catch covers only the two post-read checks, so a registry read error is not blamed on the copy.
  - The pre-read hash failure has its test.
- **Nothing in the record changes:** the computation, the cohort, the plan and the bar are untouched. The UNL record block (11-17) runs on main with these in.
