## 2026-11-26 (#1160: 1155-document-url-strip — the NBA probe's --document-url stripped once, then parsed and checked in one guard (558 item 4; DEV 4, Lane D; Closes #1155))
- **scripts/nba_injury_report_probe.py:** the option is stripped once; the parse, the host and the https check run on it inside one guard; the stripped value is fetched; the receipt keeps the value as given. A leading Unicode space before a URL that does not parse is refused before any request, never raised.
- **tests/test_nba_injury_report_probe.py:** 4 new (they fail on the probe before this change); 159 pass.
