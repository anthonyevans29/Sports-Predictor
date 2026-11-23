## 2026-11-23 (#0000: 1087-leagues-read-mends — #1075's two follow-ups, mended before the first read (ARCHITECT 2026-11-23, addendum 459 item 1(c); #1087))
- **src/walters/leagues_window.py, `pages_digest`:** each page is read by `lstat`. A page that is a symbolic link is refused, never followed (459 item 1(a)): "is a symbolic link, not a page; nothing read". Anything else that is not a regular file is refused as before.
- **src/walters/leagues_read.py, `inside_checkout` and `check_pages`** (459 item 1(b)):
  - A path under a regular file (`NotADirectoryError`) reads as a missing folder, so the pages check refuses it as not a folder.
  - Any other stat error (a permission refused, a symlink loop) refuses as "the folder cannot be checked". The REFUSED line replaces a traceback.
  - Both happen before the reservation: nothing is spent and nothing written.
- **tests/test_447_leagues_window_read.py:** two tests.
  - A link to one of the folder's own pages, and a link to a file elsewhere, each refuse the digest and the script's `--pages-digest` (exit 2). With the link removed, the folder digests as before.
  - An `--exports` path under a file refuses as not a folder; a stat refused by permissions refuses by name; nothing is reserved.

  No bar, threshold or verdict moves. No digest of a folder of regular pages changes. Nothing is run on real data.
