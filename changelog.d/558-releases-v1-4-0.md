## 2026-10-16 (#558: releases-v1-4-0 — ARCHITECT addendum 88 items 1 and 3; Closes #557)
- docs/RELEASES.md, ritual step 3: the tag step now reads `git tag -a vX.Y.Z <sha> --cleanup=verbatim -F <notes>`, from v1.5.0 on. git's default cleanup strips every line beginning with `#`.
- docs/RELEASES.md, a new "Release record" section, one line per tag. Its first line is v1.4.0:
  - cut 2026-10-16 14:18:21Z, commit `684462e3d5078ff2c906db73362a220917bf1fcb`, tag object `253bacd00327446936cdb16ea37a76deafc20ff1`, release Issue #556;
  - the record of its tag message's dropped lines: the notes' header and all 105 `## ` section headings, 106 lines (#557).
- No code change. The tag does not move.
