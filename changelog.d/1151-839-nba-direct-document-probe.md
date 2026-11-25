## 2026-11-25 (#1151: 839-nba-direct-document-probe — the NBA injury-report probe reads ONE document by the URL the block names, no index read (553 item 3; DEV 4, Lane D; Refs #839))
- **scripts/nba_injury_report_probe.py `--document-url`**, new, in place of `--index-url` under `--report`: one published document asked for directly, ONE GET with the probe's own User-Agent and no redirect followed; no index read, no link listed, no newest picked.
- **The same read as the newest report:** the document read is one helper (`read_document`) both paths call, so the form, the fields (structure only) and MAPPING print the same; the index path's console and receipt are unchanged.
- **Refused before any fetch:** together with `--index-url`; without `--report`; without `--terms-ruling`; blank; a URL that does not parse. The host gate and `--out` under logs/availability/ come first, as before.
- **The console stays structure only (368/520 unchanged, 553 item 2(e)):** the URL, its file name, any Location and every row are in the mode-0600 receipt only.
- **The no-URL-default rule pinned:** the docstring's sentence, every `-url` option's default None (`build_parser()`), and the no-http(s)-literal test kept.
- **tests/test_nba_injury_report_probe.py:** 23 new (149 in all), synthetic shapes on example.invalid only. docs/CLI.md and scripts/README.md name the option (open point E on #839).
