## 2026-11-23 (#1099: 1087-leagues-read-mends — #1075's two follow-ups, mended before the first read (ARCHITECT 2026-11-23, addendum 459 item 1(c); #1087))
- **src/walters/leagues_window.py, `pages_digest`:** each page is read by `lstat`. A page that is a symbolic link is refused, never followed (459 item 1(a)): "is a symbolic link, not a page; nothing read". Anything else that is not a regular file is refused as before.
  - The folder's own stat is read in a try. Missing, or not a directory, is "not a folder". Any other stat error (a permission refused, a name too long, a link loop) is "the folder cannot be read", where Python 3.13's `is_dir` let them through as a traceback. This applies on the host's `--pages-digest` and on the read's second digest alike.
  - Each page is opened without following a link (`O_NOFOLLOW`, `O_NONBLOCK`), and the open file is checked to be a regular file. A page swapped for a link or a fifo between the lstat and the open is refused, never followed and never waited on.
- **src/walters/leagues_read.py, `inside_checkout` and `check_pages`** (459 item 1(b)):
  - A path under a regular file (`NotADirectoryError`) reads as a missing folder, so the pages check refuses it as not a folder.
  - Any other stat error (a permission refused, a symlink loop) refuses as "the folder cannot be checked". The REFUSED line replaces a traceback.
  - Both happen before the reservation: nothing is spent and nothing written.
- **tests/test_447_leagues_window_read.py:** four tests.
  - A link to one of the folder's own pages, and a link to a file elsewhere, each refuse the digest and the script's `--pages-digest` (exit 2). With the link removed, the folder digests as before.
  - An `--exports` path under a file refuses as not a folder, and a stat refused by permissions refuses by name. Both are tested through the preflight and through the read itself, which is refused before the reservation, with no reservation file.
  - The digest alone (the host's mode) refuses a folder whose stat is refused, a name too long and a link loop, each exit 2 with REFUSED.
  - A page swapped for a link after its lstat is refused at the open.

  No bar, threshold or verdict moves. No digest of a folder of regular pages changes. Nothing is run on real data.
