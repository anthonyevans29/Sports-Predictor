**2026-11-12 — FIXED (#930, #929's follow-up Issue under the review stop rule): the awaiting VERDICT line names an unread paired window.**
- **The defect:** `paired_verdict` returned at its awaiting branch before the window-not-read branch. The verdict was right (NOTHING-TO-COMPARE, pending), but its line named only the awaiting file, and the mirror Action parses that line.
- **The fix:** the awaiting line appends the unread files, as the other NOTHING-TO-COMPARE line does. No verdict, exit code or pending state changes.
