**2026-11-23 — desk_policy.not_laptop_reason() built beside not_host_reason() and on its pattern (addendum 461 item 2(d)); it ships first as its own small PR, the function and its tests, nothing else (461 item 2(e)); not a fence input: host_fenced never reads it.**
- **Addendum 461 item 2 (ARCHITECT 2026-11-23 12:45 ET), verbatim:**

  > 2. THE LAPTOP ROUTINE, YOUR TWO FAILING TESTS (your report on #1067, 17:27Z). You were right to stop.
  >    NEITHER TEST IS TOUCHED AND NEITHER PIN IS WIDENED. Both failures come from my own text in 451, and I
  >    amend 451, not the tests.
  >    (a) tests/test_mlb_retire_orphans.py, test_never_inside_the_watch. The pin says no file under
  >        deploy/hosting names the command, and it stands as written. 451 item 3(d) step 2 LEAVES THE
  >        ROUTINE. The dry run stays in my block, by hand, after the routine returns. The daily list is 16
  >        steps: renumber them, in the same order. 451 item 3(f) 7 is amended to match: five MLB steps stay
  >        in the routine through the off-season, and the sixth is mine.
  >    (b) tests/test_host_watch_after_flip.py, the fence's inputs. The pin says no production file outside
  >        desk_policy references a fence input, and it stands as written. 451 item 3(b) named
  >        desk_policy.machine_role(), which is a fence input; that was my error. The routine does not call
  >        it and does not name it, in code or in a string.
  >    (c) closing.mirror_role() is NOT the substitute. It reads the environment first, so a routine typed
  >        by hand on the host could be answered by the checkout's .env, which on the host says laptop
  >        (role_reading's own docstring, the #410 review). The refusal must rest on the fence's reading.
  >    (d) WHAT IS BUILT: desk_policy.not_laptop_reason(), beside not_host_reason() and on its pattern (178
  >        R6). None on the laptop; otherwise why this machine is not the laptop, by role_reading, read only:
  >        the role is host, unset, a value that is neither, or host.env exists and cannot be read. Its
  >        docstring says, as not_host_reason's does, that it is not a fence input: host_fenced never reads
  >        it. The routine calls it, prints the reason and exits 2 with nothing run when it is not None.
  >    (e) THAT FUNCTION SHIPS FIRST, AS ITS OWN SMALL PR: the function and its tests, nothing else.
  >        desk_policy is money-path code and is read alone; by the stop rule its P2s after round two are
  >        listed for me. A reviewable head by Tuesday 2026-11-24. The routine's PR follows on it and stays
  >        ops tooling. If either pinned test still fails with (a) and (d) built, name it to me before
  >        touching it, as before.
- **What landed:** `not_laptop_reason()` in src/walters/desk_policy.py, directly after `not_host_reason()`: None on the laptop; otherwise "this machine's role is host", "the role '<value>' is not host or laptop", "the role is unknown (SP_EXPORTS_MIRROR_ROLE unset)", or "host.env exists but cannot be read: the role is unknown", by role_reading (host.env first), read only. No other line of desk_policy changes.
- **Tests:** tests/test_not_laptop_reason.py (11): each of the four answers and None on the laptop; host.env first (the #410 case); an unreadable host.env never answered by the .env; host_fenced and the fence's read path never name it; rebinding it changes no fence answer. tests/test_host_watch_after_flip.py is not touched and its pins pass.
- **Next:** the laptop routine's PR (451 item 3, ops tooling) follows on this one and calls the function (461 item 2(d)-(e)).
- Nothing here moves a bar, a date or a held timer. Nothing changes a prediction output.
