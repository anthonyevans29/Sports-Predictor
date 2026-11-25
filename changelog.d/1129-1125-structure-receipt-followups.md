## 2026-11-25 (#1129: 1125-structure-receipt-followups — #1124's review-round-2 findings fixed, and #1126's index line (DEV 4, Lane D; ARCHITECT 2026-11-25 08:09 ET, addendum 525 item 3(c); #1125))
- **scripts/file_structure_receipt.py:**
  - **An exponent past decimal's limit is data.** Float extrema are ordered by an exact key of the token's sign, power of ten and digits, with no bound on the exponent. decimal.Decimal refused `1e99999999999999999999`, so a valid file read as "not read whole". The new key agrees with Decimal wherever Decimal reads the token.
  - **ISO timestamps with any number of fractional digits are datetimes,** nanosecond exports among them. They order exactly: to the microsecond by the instant, then by the digits past the sixth.
- **changelog.d/1124-518-file-structure-receipt.md:** the test count reads 69, the count that PR collected (the round-2 P3).
- **scripts/README.md:** `scripts/nhl_cohort_count.py` (#1126) is indexed as a TOOL (120 indexed, TOOL 68), as 525 item 3(c) asks.
- **tests/test_file_structure_receipt.py:** 72. They pass on Python 3.10 and 3.13. Synthetic files only.
