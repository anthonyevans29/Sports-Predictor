## 2026-11-12 (#980: 972-probe-lines-ab — the NBA injury-report probe keeps a line's characters: #972 items A and B (ARCHITECT 2026-11-12, addendum 363 item 6))
- **scripts/nba_injury_report_probe.py:** robots.txt and the report's text now break into lines only at CR, LF and CRLF (`text_lines`). `str.splitlines` also broke at VT, FF, FS/GS/RS, NEL and U+2028, and those characters were lost from the receipt's lines.
- **Whitespace:** the page's whitespace folding, the report's line trimming and the index's link text now leave in place the control characters that Python's `\s` also took: VT, \x1c-\x1f and NEL (`fold_ws`, `trim_ws`). Every space, NBSP and the other Unicode spaces included, still folds and trims exactly as before: no mismatch with main in 200,000 random strings without those characters.
- **Page footers:** `PAGE_LINE` allows edge whitespace, so a kept control at a "Page N of M" line's edge does not make it a body line. The console still shows every control character as `\xNN` (362 item 7).
- **Tests:** seven in tests/test_nba_injury_report_probe.py, failing first.
  - Three cover A and B themselves, on main 62be4060.
  - Four cover the first adversarial pass's confirmed regressions in the first version (dadf6c1f): NBSP spacer lines shifting windows and date lines, an NBSP-only page reading NOTHING TO QUOTE instead of NOT READ, NBSP-only report lines counted, and link text.
- **ARCHITECT 2026-11-13, addendum 364 item 5 (the second pass's design question, ruled as recommended; one push):** a line counts only if it holds a character that is neither whitespace nor a control (`has_word`). A line that counts keeps its controls. A block or line of whitespace and controls alone is dropped, as on main, so a control-only spacer shifts no window or date line, a control-only page reads NOT READ, and a control-only report reads NO TEXT.
- **The linear strip (364 item 5):** `trim_ws` is `str.strip` with an explicit character set: every character `str.isspace` takes except the kept controls, with no regex. The quadratic regex it replaces took 7.7 s on a 20,000-space PDF line.
- **The console (364 item 5):** U+2028 and U+2029 are escaped as `\u2028`/`\u2029`. The receipt keeps them exact.
- **Tests:** five more, failing first on cabdff17. The strip is checked against `str.strip` for every whitespace character from U+0000 to U+10FFFF.

