**2026-11-23 — #1075's two follow-ups mended before the first read (addendum 459 item 1(c); #1087; #1099).**
- **Ruling (459 item 1(c), in part):** "both are mended in one small PR BEFORE THE FIRST READ (2026-12-07), by the fixes you name: lstat in pages_digest; NotADirectoryError as a missing folder and any other OSError a refusal."
- **What landed:** both fixes as named, and the folder's own stat refused the same way (the adversarial review: the host's `--pages-digest` still went to a traceback on a refused stat). Each page is opened without following a link. Four tests. A folder of regular pages digests to the same value as before.
- **Next:** CI, then the stop rule. It merges before 2026-12-07.
