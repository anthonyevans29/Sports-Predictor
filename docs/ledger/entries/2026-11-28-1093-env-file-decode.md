**2026-11-28 — desk_policy._env_file reads a file it cannot decode as UTF-8 the way it reads one it cannot open: with strict (host.env) HOST_ENV_UNREADABLE, the role unknown and nothing after it read; without strict (the checkout's .env, the last source) {}; every caller of role_reading now answers a refusal where it raised (ARCHITECT 2026-11-23, addendum 464 item 4; #1093). The laptop routine's handler test is re-pinned as ruled (addendum 582 item 3).**
- **The ruling, verbatim (ARCHITECT 2026-11-23 13:48 ET, addendum 464 item 4):**

  > 4. DEV 1 — YOUR QUESTION 2, the host.env that is not valid UTF-8. A FINDING, and it gets its Issue
  >    today (track:ops, class:finding, sport:all, size:S). Today it fails closed: the reading raises, so
  >    no Desk call is made on that machine. YES, mended in its own small PR, money-path, read alone:
  >    _env_file with strict reads a file it cannot decode as HOST_ENV_UNREADABLE, the role unknown and
  >    nothing after it read; without strict, as {} (the checkout's .env, the last source). _env_file is a
  >    fence input, so if a pinned test fails on the change, name it to me before touching it. A
  >    reviewable head by Friday 2026-12-04. It does not hold the laptop routine.

- **The test's ruling, verbatim (ARCHITECT 2026-11-27 20:05 ET, addendum 582 item 3):**

  > 3. DEV 1 — Q1, #1093's PINNED TEST: YES, AS YOU PROPOSE, IN THIS PR. Thank you for naming it first.
  >    (a) The test's premise is the defect itself, so the pin moves with the mend. It is the routine's
  >        handler test (461 item 3(d)), not one of the fence's own pins; those stand untouched.
  >    (b) Your (a): the handler's case stays, the raise now made by a monkeypatch on the routine's own
  >        name, the bad file still making redact raise; the same refusal line, receipt and exit 2.
  >    (c) Your (b): the mended path with the real reader on the same file: exit 2, nothing run, the
  >        reason "the role is unknown (SP_EXPORTS_MIRROR_ROLE unset)", one receipt on a real run and none
  >        on a dry run. Pin too that this receipt carries no error key.
  >    (d) Your (c): the fixture's docstring corrected. The PR's body names the test and quotes this item.

- **What changed:**
  - `src/walters/desk_policy.py`, `_env_file`: `except (OSError, UnicodeDecodeError)`, where it caught `OSError` alone; the docstring says why (a decode error is a ValueError). The fence's read path is unchanged by name (tests/test_host_watch_after_flip.py READ_PATH: the builtin is not a module name).
  - `tests/test_env_file_decode.py`, new: strict and plain on an undecodable file; #1093's own case (the role line, then two bytes that are not UTF-8) on three environment roles, each reading (None, HOST_ENV_UNREADABLE), machine_role None, and both reasons "host.env exists but cannot be read: the role is unknown"; host_fenced with its switch on gives the unreadable reason; an undecodable checkout .env reads as the role unset.
  - `tests/test_laptop_routine.py` (582 item 3): the pinned test test_a_role_read_that_raises_while_redact_raises_is_still_refused_exit_2 keeps the handler's case, the raise made by a monkeypatch on the routine's own name, the same refusal line, receipt and exit 2; a new test pins the mended path with the real reader (exit 2, nothing run, the role unset, one receipt with no error key on a real run, none on a dry run); the bad_dotenv fixture's docstring is corrected.
- No Desk call, size or price changes: the fence reads an undecodable host.env as an unreadable one, which it already fenced; the switch is off on main.
