## 2026-10-16 (#551: ledger-tests-after-compile — main's CI red on c546168, the v1.4.0 commit of ARCHITECT addendum 84)
- c546168 (the ledger compile) folded every fragment into CHANGELOG.md and BACKLOG.md and deleted the files.
  - Three tests read `docs/ledger/entries/2026-10-08-ncaa-v1r-declaration.md` directly, so CI's smoke job on c546168 failed: `test_ncaa_v1r_declaration::test_spec_and_ledger_quote_d1_to_d9_and_the_d5_note_verbatim` and two in `test_ncaa_v1r_fence`.
  - The tag ritual refuses unless CI on the commit is green.
- tests/ledger_text.py (new): `entry_text(name, heading)` reads an entry from its fragment while the file exists. After the compile it reads the entry's block in BACKLOG.md, found by its heading line (exactly once), up to the next entry or section heading.
  - The folded block is the fragment verbatim: checked on c546168 against the file as it stood at 87ea592.
- The three tests read the entry through it. What they assert is unchanged.
- tests/test_ledger_text.py: the fragment is read first; then the folded block, bounded by the next heading; a missing or doubled heading fails loudly.
  - A guard: no test reads `docs/ledger/entries` or `changelog.d` directly any more. The fragments' own checker is exempt.
