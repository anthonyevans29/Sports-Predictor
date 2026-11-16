## 2026-11-16 (#000: 414-ncaa-listing-probe — the NCAA listing probe, read-only (ARCHITECT 2026-11-16, addendum 414 item 3; #1035, #1038))
- **New:** `scripts/ncaa_listing_probe.py`. For each date given (at most seven), one GET of the provider's college football games through the adapter's own `_get` (league 2, season 2026, that date). Each raw row is printed before any parsing, beside what our side would do with it:
  - no date (#1), no team id (#2), all-star or exhibition (#3);
  - with an optional `--db` copy (mode=ro&immutable=1; data/ and sidecars refused): team not in the copy (#6), the stored match holding the provider id, or NOT STORED.
- **The fence (414 item 3(c)):** no write and no file made; provider calls counted first and last; the key by name only; a provider error prints and exits 1 after what was read; no sync, re-key or repair module is loaded.
- **Tests:** tests/test_ncaa_listing_probe.py (17), on invented rows only; no network.
- **Unchanged:** every sync, the adapter and the database. Nothing runs on a schedule.
