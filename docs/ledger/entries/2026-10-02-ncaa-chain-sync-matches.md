**2026-10-02 — #254 CLOSED (ARCHITECT: misread); the residue built: the NCAA market chain syncs results before its export.**
- **Ruling (verbatim):** "#254 — CLOSE as architect misread; stored kickoffs are correct and "in-play — never" was right (games played Thu). The real residue: WKU@NMSU and UNT@Tulsa still status=scheduled 20h after finishing — NCAA match/result sync isn't running between the Thu games and the Fri export. Add sync-matches NCAA to the Friday/Saturday NCAA chain (laptop + host sp-ncaa-market) before the fixtures export, so finished games leave the window."
- **Correction to #255's entry:** it called the stored kickoffs "+24h". That was based on the reported utc_date values, which the architect has ruled a misread. The stored kickoffs are correct. `scripts/kickoff_receipt.py` stays as a read-only tool.
- **Built:**
  - `deploy/hosting/chains.py` `ncaa-market` now runs `sync-matches --competition NCAA --season 2026 --date-from D --date-to D` for D = yesterday and today. These are single-day calls, because the american-football adapter sends a `date` only when from == to. They run before `sync-kalshi-ncaa` and `export-fixtures`.
  - The timer is unchanged (Thu 16:00, Fri 16:00, Sat 13:00 UTC), so the Thursday run also covers Wednesday games.
  - `sync-matches` is metered: in designated-days mode it is skipped on non-designated days, like every other sync.
- **Laptop:** the same three steps, documented in `docs/CLI.md` under Market-only competitions. The operator's Thu/Fri/Sat NCAA routine gains the two `sync-matches` lines.
- **Review on #256 (Anthony, 2026-10-03):** the receipt omitted the exported status and the stored scores. `scripts/kickoff_receipt.py` now prints:
  - STORED: `score H-A`;
  - one EXPORT line per file: file name, `exported_at`, the row's status and score, and **Desk input INCLUDED / excluded**. A fixtures row is a Desk input only while scheduled (`desk_policy.normalize`).

  The output is pinned in tests/test_kickoff_receipt.py. The script stays read-only.
