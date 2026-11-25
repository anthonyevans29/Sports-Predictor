**2026-11-25 — A settings refusal lifts every closing it reaches from a resend's bound (addendum 511 item 2; addendum 530 item 3; #1120; #1131).**
- **#1117's one follow-up.** `no_chain` held only the refused start, so a later start that the same settings refusal will refuse could hold a resend for a tick.
- **The fix.** A family's own refusal lifts that family from `send_resend`'s bound. The machine's settings (backup folder, mirror, role, card topic) lift every family. A bad `--start` lifts only that start.
- **Nothing else moves:** no refusal or exit changes, no call, no page text, no bar, no date and no held timer.
