**2026-11-24 — The file structure receipt, read-only tooling for the architect's blocks over the reopened sources (DEV 4, Lane D; the brief of addendum 518 item 5; Refs #105, #838; #1124).**
- **Why:** the operator reopened MoneyPuck's files (addendum 517) and the tennis archive (addendum 518 item 2). The architect reads the files' structure by block before ordering the depth probe (517 item 2(f)), and only counts and structure leave the laptop (517 item 2(d); 518 item 2(b)).
- **What landed:** `scripts/file_structure_receipt.py` and its tests.
  - It reads a file or a folder of CSV files (plain, .gz, .zip) and prints per file: the name, the size, the sha256, the rows, the columns in order, each column's null and empty share, kind and distinct count, and the minimum and maximum of a numeric or date column.
  - It prints the values and counts only for a column the caller names with `--vocab`.
  - It assumes no column name, prints no row, refuses a path under data/, writes nothing, and exits non-zero on a file it cannot read whole.
- **Nothing was run on a real file.** No model, no figure, no bar.
