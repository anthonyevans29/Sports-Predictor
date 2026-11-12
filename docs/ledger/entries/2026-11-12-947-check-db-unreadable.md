**2026-11-12 — FIXED (#947, #942's follow-up Issue under the review stop rule): the `--db` fence's two silent "absent" reads.**
- **The defect:** an unreadable data/ root and an unreadable `--db` stat were each treated as absent, so the identity check (a hard link into data/) did not run on either.
- **The fix:** only `FileNotFoundError` and `NotADirectoryError` read as absent. Any other `OSError` refuses (law 4).
- **Classification (#947's, the architect's to overrule):** read-only. `check_db` is the fence that receipts, probes and gates call before they open a `.backup` copy read-only.
