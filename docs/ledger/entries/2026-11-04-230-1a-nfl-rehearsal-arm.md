**2026-11-04 — BUILT (ARCHITECT 2026-11-03, addendum 230 item 1(a), as ruled by ARCHITECT 2026-11-04, addendum 247 items 2-3): nfl-elo-v2's rehearsal arm. nfl_elo_v2's probabilities ride the NFL slate and closing rows as a second arm under a separate rehearsal_* prefix, and the grader carries them as its second arm. The arm is host-only and dormant unless the registry reads the architect's PASS, status `rehearsal` and a window covering the game's kickoff. The Desk reads nothing from it, and the compare masks it under its own line. Gate-class: an export contract, no model change.**
- **Ruling (verbatim, ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 1(a)):** "(a) nfl-v2's REHEARSAL (lane nfl-v2, the 11-23 step: "on PASS: the rehearsal on the host's pages from the next tag, weeks 10 and 11, 11-12 through 11-23") — PR BY 11-09, on a tag by 11-11: nfl_elo_v2's probabilities as a SECOND ARM on the NFL slate and closing pages beside v1's record-only would-be (the pl-availability shadow's shape: two probability sets, the grader's second arm, the arm labelled with the entry and its verdict stamp), written only while the entry's verdict reads PASS and its rehearsal window is open (registry state 'rehearsal', 11-12 to 11-23); the Desk reads nothing from it (market-only stands until my live ruling of 11-26); the results export carries both arms' log-loss against the close and Brier per week; a FAIL on 11-06 leaves every line of it dormant. Gate-class (an export contract): the PR body shows a synthetic page with both arms and the pin that the Desk's call never reads the second arm."
- **Ruling (verbatim, ARCHITECT 2026-11-04 09:55 ET, addendum 247 items 2-3):**
  - "2. THE REHEARSAL ARM (230 item 1(a)), the six, RULED:"
  - "(1) WHO WRITES THE STATE, AND THE INSTANTS: after Friday's run, Code's verdict-record PR (the one that writes the run record and verdict into the entry, by my verdict addendum) ALSO writes, on PASS only, `status: "rehearsal"` and `rehearsal_window: {"opens_at": "2026-11-12T00:00:00Z", "closes_at": "2026-11-24T06:00:00Z"}` — week 10's Thursday through week 11's Monday night INCLUDED (the MNF of 11-23 ET kicks off 2026-11-24T01:15Z and is week 11's last game; 215's "11-12 through 11-23" is ET dates). On FAIL nothing is written and the arm is dormant for the season. The shape the code reads is exactly that; a test pins it."
  - "(2) THE COMPARE: a SEPARATE key prefix `rehearsal_*` (rehearsal_version, rehearsal_probabilities, rehearsal_reason…), host-only, masked by compare_exports.py under its own line "rehearsal-arm keys (host-only, nfl-elo-v2)" beside the pl-availability line — #735's pattern, in the SAME PR (a compare that would fail the tag on its own arm is a defect, not a question). Never the `candidate_*` keys: those are pl-availability-v1's line and its count."
  - "(3) WHAT OPENS THE WINDOW PER ROW: the GAME'S KICKOFF inside the window (as recommended); a row written before the window for a game inside it carries the arm; a row for a game outside it never does, whenever written."
  - "(4) AFTER THE WINDOW CLOSES: the export STOPS WRITING the arm (no new rows) but the results export KEEPS READING every stored arm row — the 11-24 dry read reads them. Written once, read for the record always."
  - "(5) TIES: each figure keeps the rule it already has, stated on its line — the log-loss treats a tie as the gate's protocol does (walk_protocol's own rule, unchanged: the rehearsal's log-loss must be the gate's arithmetic), the W-L-P and the vs-close figure treat a tie as a push, as results-tally does. "Per week" = the NFL game week as nfl_predict assigns it (weeks 10 and 11), never the calendar week."
  - "(6) THE LIVE WALK: the same games as nfl_elo_v1's live walk (2024 to date, every non-preseason FINISHED game, in order), with the declared term for the whole walk — the gate's walk continued into 2026, so the arm's 2025 probabilities EQUAL the gate run's scored 2025 probabilities game for game: a parity test pins it (the gate's run record will hold them after Friday; before that, the test walks the synthetic stream both ways). Never the gate's cold start re-run on the host."
  - "3. The Desk reads nothing from the arm (a byte-identical pin, as planned); the arm labels every row with the entry id, the term and "rehearsal — not a call"; the phone page carries no arm line (the summary block and receipt do, as 223 item 3 ruled for the would-be line)."
- **(1) The state is read, never written.** `nfl_rehearsal.read_gate` / `state` read the `nfl-elo-v2` entry at call time. The arm is on only when all of these hold:
  - this is the host;
  - `verdict.verdict == "PASS"`, with its `at` (the architect's record, never the computed run text);
  - `status == "rehearsal"`;
  - `rehearsal_window` is exactly `{"opens_at": "<instant>Z", "closes_at": "<instant>Z"}`, opens before closes;
  - the declared term and the frozen constants price.

  Every other reading is dormant, with its reason. The instants are read from the entry and never defaulted. A test pins 247's ruled `{"opens_at": "2026-11-12T00:00:00Z", "closes_at": "2026-11-24T06:00:00Z"}` and that a different window is followed.

  This PR writes no registry field: the verdict-record PR after Friday writes the state, on PASS only. The real registry reads dormant today.
- **(2) The compare.**
  - The slate and closing rows carry `rehearsal_version`, `rehearsal_probabilities`, `rehearsal_term`, `rehearsal_verdict_stamp`, `rehearsal_label` and `rehearsal_reason`.
  - The results row and the record carry `rehearsal_arm`.
  - compare_exports never compares or prints a `rehearsal_*` key at any depth. It counts them on `rehearsal-arm keys (host-only, nfl-elo-v2): N`, right after the pl-availability line.
  - No `candidate_*` key is used, and the pl-availability line and its count are unchanged.
- **(3) The window opens per game, by kickoff.** The kickoff must fall in [opens_at, closes_at). The week-11 MNF at 2026-11-24T01:15Z is inside, and 06:00Z is outside. A row predicted before the window for a game inside it carries the arm (pinned); a game outside it never does.
- **(4) After the window.**
  - The export writes no new arm row: no covered game is upcoming once closes_at has passed (pinned with a closed window: nothing stored, every file equal to the stubbed code's).
  - On the host, export-nfl-results reads every stored arm, whatever the registry reads later (pinned with the window closed, the status `production`, a FAIL, and no entry).
  - Off the host, nothing is read.
- **(5) Ties and weeks.** Each figure's rule is stated on its line (`record.rehearsal_arm.rules`):
  - The log-loss is walk_protocol's arithmetic: a tie counts as a home loss, and the mean is accumulated as the gate accumulates it. It is pinned equal to `ll_model` to the bit.
  - The Brier is (p - y)^2 on the same y.
  - The W-L-P and vs-close treat a tie as a push.
  - Per week means by the row's `week` (matches.matchday).
- **(6) The live walk.** v1's `_current_ratings` runs under the declared term for the whole walk. A parity test on the synthetic stream, walked both ways, finds the 2025 probabilities equal to the gate's scored ones, game for game.
- **(3 of 247) The Desk pin.** Bare, armed and loud docs give byte-identical output for:
  - `desk_meta` and the desk blocks;
  - `closing.desk_rows` (with `would_be_for`);
  - `exec_cohorts.would_be_play`;
  - `closing.page_text`.

  No Desk code names the keys. The arm labels each row with the entry id, the term, the verdict stamp and "rehearsal — not a call". The closing summary block and the run receipt carry one arm line; the phone page carries none, as 223 item 3 placed the would-be line.
- **For the architect (not acted on):**
  - The gate's run record will hold the scored ids, `ll_model` and the band means, not per-game probabilities. The post-Friday parity can compare the arm's 2025 log-loss and band means with them; no reader is built here.
  - A `rehearsal` status meets five places that know only today's statuses, and the verdict-record PR meets them:
    - `registry.record_verdict` writes `confirming`;
    - `registry.record_confirmation` reads it;
    - coverage_map's lane/registry disagreement check;
    - roadmap STATES has no `rehearsal`;
    - tests/test_leagues_declaration_220.py pins every real entry's status to the five statuses in use today.
  - v1's live walk has no season floor. "2024 to date" holds while no NFL game before 2024 is stored FINISHED. Code has no database and did not read the host's seasons; the #608 receipt lists 2023 from the provider only ("not stored, not walked"). If a pre-2024 NFL game were stored as FINISHED, the arm would still follow v1's games as ruled, and its 2025 probabilities would no longer equal the gate's.
  - `walk_protocol`'s tie rule is inline, not a function, so there is no function to call. The rehearsal uses the same expression, pinned by its text and by its value, rather than refactor the frozen gate's code before its one run.
- No constant, bar, gate threshold, roadmap date or registry value moved. The market is a reference, never a model feature.
- **Tracked:** lane Issue #783; docs/specs/nfl-rehearsal-arm.md; tests/test_nfl_rehearsal_arm.py.
