## 2026-11-24 (#1124: 518-file-structure-receipt — the file structure receipt, read-only tooling (DEV 4, Lane D; the brief of addendum 518 item 5, ruled by addendum 521 item 6; Refs #105, #838))
- **scripts/file_structure_receipt.py**, new, stdlib only, Python 3.10 floor, no f-strings. It reads CSV files (plain, `.csv.gz`, `.zip` members), as a file or a folder (`--recursive` opt-in), and prints per file:
  - the name, the size and the sha256 of the bytes on disk; for a `.gz` file or a zip member, also the decompressed bytes read and their sha256;
  - the rows, blank records and ragged rows, and the columns in order (blank and duplicate names flagged);
  - per column: the null share (a fixed token list printed in the receipt), the empty share, the absent share, the kind (bool, int, float, ISO date, ISO datetime, text, none; ASCII digits only; no MM/DD guess), the distinct count (exact up to `--distinct-cap`, default 100,000, else "more than N (cap)"), and the minimum and maximum of numeric and date columns only (521 item 6 Q2);
  - for a column named with `--vocab` (the header's exact text), its distinct values and counts, at most `--vocab-max` (default 200).
- **Read strictly:**
  - The first non-blank record is the header. An unclosed quote, a character after a closing quote, or a NUL in the text is an error on every Python, never a silent merge.
  - A file not read whole prints its ERROR line first, and every figure after it is marked PARTIAL.
- **What it never does:**
  - It prints no row, and no value of a column nobody named, save that minimum and maximum.
  - An error names the record and the error's class, never the bytes.
  - A header that may be a data row is withheld and its columns print by position. That is a header with a cell that parses as a number, a date, a bool or a null token, or whose text recurs in its own column.
  - Names print with control characters escaped.
  - It opens no FIFO or device, writes nothing, and ends with no traceback.
- **Refused, exit 2, before any file opens:**
  - any directory named data, case ignored, on the path as given and as resolved (521 item 6 Q1);
  - anything resolving under the checkout's data/;
  - a PATH that cannot be resolved;
  - bad options, including a bytes codec given as `--encoding`.

  A zip member's name is not refused for that word (521 item 6 Q1).
- **Exit 1, with the other files still printed and the SUMMARY line always last:**
  - a missing path, or a folder that cannot be listed;
  - an entry that cannot be resolved;
  - a file not read whole;
  - no CSV found.
- **Named as SKIPPED:** subfolders (without `--recursive`), symlinked folders, macOS metadata (`._*`, `__MACOSX/`), other files and other zip members.
- **tests/test_file_structure_receipt.py (67):** synthetic files under tmp_path only. They pin every finding of two independent review passes made before the PR. They pass on Python 3.10 and 3.13. Nothing was run on a real file.
- **scripts/README.md:** the receipt is indexed as a TOOL (119 indexed, TOOL 67).
