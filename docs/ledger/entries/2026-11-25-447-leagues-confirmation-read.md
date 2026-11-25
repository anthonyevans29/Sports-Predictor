**2026-11-25 — the leagues' confirmation read, 447's PR 3: `leagues-confirmation-read` reads the first 60 games later than the run record's opening in the window's order, names as findings the games before the opening that the run record does not account for, records through registry.record_confirmation with the first game's id, and the cross-ref guard reads the confirmation's ids file and reservation (addendum 447 item 3 C1 and item 4; addendum 448 item 1(e)-(f); addendum 467 item 1(a); addendum 505 item 2(c); the five questions ruled by addendum 540 item 1; #322) (#1153).**
- **Ruling (447 item 3 C1), verbatim in part:**
  >    C1 RULED, WITH ONE CHANGE: the confirmation opens at the 60th member's PLACE IN THE WINDOW'S OWN
  >       ORDER, not at its kickoff alone. membership() orders by kickoff, then match id. The run record's
  >       confirmation_opens_after holds both: the 60th member's kickoff and its match id. The
  >       confirmation's games are the games later in that order: a later kickoff, or the same kickoff
  >       and a higher id. Its cohort is the first 60 of them that qualify by the window's own rules.
  >       (d) A 2026/27 game kicking off after declared_at and before the opening that is neither a member
  >           nor accounted for in the run record (a kickoff re-dated after the read) is in neither
  >           cohort. The confirmation reader counts it and names it as a FINDING; never a member, never
  >           silent.
- **Ruling (447 item 4), verbatim in part:**
  >    PR 3: leagues-confirmation-read. By 12-11; no confirmation can be read before January.
  >    None of the three changes a prediction output, and each says so.
- **Ruling (448 item 1(e)-(f)), verbatim:**
  >    (e) YOUR OPTION (record_confirmation refusing the ids the run record names as reached with no slot)
  >        is NOT TAKEN. A postponed game the loop passed may enter the confirmation by its real kickoff
  >        once it is re-dated after the opening (R4), so that list is not a refusal list. The reader
  >        holds the order; the registry is the backstop, as 447 says.
  >    (f) PR 3 extends _guard_paths to the confirmation's ids file and its reservation. Named now, as
  >        you did; it is a guard, not a policy, and rides in PR 3.
- **Ruling (467 item 1(a)), verbatim in part:**
  >    447's PR 3, the confirmation read, writes the first game's match id into its result beside
  >    first_game_at, and registry.record_confirmation, for an entry that holds an opening, refuses a
  >    first game AT the opening's kickoff whose id is not above the opening's match id. A test for the
  >    tie on each side of the id.
- **Ruling (505 item 2(c)), verbatim, stated in this PR's record (the PR body and these fragments; no key in the result, 540 item 1 Q2, ruled):**
  >    (c) SO, STANDING: no league leaves the shadow list for calls without its injury sync, or
  >        without an exemption that I rule by the league's name. The leagues' confirmation PR (447
  >        PR 3) says so in its record. Nothing changes for it today: the five leagues pass earlier
  >        as shadows.
- **What landed:** src/walters/leagues_confirm.py and its command; membership() takes the opening and the run record's account (with none, every output is byte-identical); record_confirmation's checks before the metric extracted as `confirmation_refusal` (a pure refactor); 467 item 1(a)'s tie refusal; the guard's two new kinds. The cohort, the refusals, the fingerprint, the reservation and the record are as the CHANGELOG fragment lists them.
- **Ruling (540 item 1, the five questions), verbatim in part (ARCHITECT 2026-11-25 14:44 ET):**
  >    YOUR INFERENCE STANDS: the day-after rule (447 B2(d)) holds on the confirmation's 60th
  >    member too. It is the more binding reading, and the gate text says "the day after the 60th game".
  >    Q1. ONE INVOCATION, as you read it, like the two confirm commands that exist. Two things with it:
  >        (i) NO WORD OF MINE ABOUT THE OUTCOME IS TAKEN IN ADVANCE. The outcome is the computed one.
  >            What I give beside the fingerprint is the addendum that orders the read, by number
  >            and date.
  >        (ii) A PREFLIGHT THAT COMPUTES NO FIGURE and reserves nothing: the refusals in order, the
  >             cohort's count, the pages digest, the first date the read is allowed.
  >    Q2. THE PR BODY AND THE TWO FRAGMENTS, the sentence of 505 item 2(c) verbatim. NO KEY in the
  >        confirmation result: a record is never rewritten, and a rule that may be amended does not
  >        belong in one. ONE ADDITION, console only and stored nowhere: a read whose outcome is
  >        CONFIRMED prints one line saying that production on a leagues entry turns on no call
  >        (220 item 3; 505 item 2(c)).
  >    Q3. THE READ REFUSES BEFORE ITS RESERVATION, NAMING THE GAME, as you read it. [...] It lifts only
  >        by my registry write naming the game (Q4's list); after that the game is out by its named
  >        cause and takes no slot.
  >    Q4. THE ENTRY'S ONE ruled_exclusions LIST, unchanged, and the refusal of 223 item 2(b) as you
  >        describe it. ONE CONDITION: an item added after the window's verdict must change nothing
  >        that the window's recorded fingerprint or any guard reads again.
  >    Q5. ALL THREE ARE RULED IN, in PR 3, each ONLY for an entry that holds an opening; every other
  >        entry keeps today's rule, and a test says so for each.
  >        (a) A missing ids file REFUSES the record. A file that is not there is not an empty set
  >            (law 4), and the scored-set check must not pass on nothing.
  >        (b) n_games EQUALS the plan's 60. "60 more" is a number, not a floor.
  >        (c) first_game_id is one of the confirmation's ids.
- **What 540 item 1 changed in this PR (ruled, not defaults):**
  - The sentence of 505 item 2(c), verbatim (540 item 1 Q2: in the PR body and the two fragments, in no result key): "no league leaves the shadow list for calls without its injury sync, or without an exemption that I rule by the league's name".
  - Q1: one invocation; `--ruling` is the addendum that orders the read, by number and date (never an outcome), in the help, the module docstring and docs/CLI.md; a `--architect-word` or `--ruling` naming CONFIRMED or NOT_CONFIRMED (any case, as a word) refuses, exit 2, before any load, nothing reserved. The preflight computes no figure (no score, aggregate, verdict or audit; no log-loss of either arm in any line) and writes no byte; it prints the cohort's count, the pages digest and the first allowed date, and refuses as the read refuses, in its order.
  - Q2: no key in the result holds a calls rule; on a recorded CONFIRMED the CLI prints `CONFIRMED_NOTE` (production on a leagues entry turns on no call; 220 item 3; 505 item 2(c)), console only: no result key, ledger field or file holds it.
  - Q3: a window member re-dated past the opening (its kickoff, cut to the whole second, in a later second than the opening's) refuses before the reservation, named; once the entry's `ruled_exclusions` names it (the architect's registry write), the confirmation's read excludes it by that cause wherever its loop reaches it, it takes no slot, and the audit and took_no_slot name it with that cause. The window's own read is unchanged: there the list never removes a member.
  - Q4: the one list, unchanged. The condition was checked in the code: what the window's recorded fingerprint and the guards read each holds a FROZEN COPY of the list as the window read it, and nothing re-reads or recomputes it after the verdict, so an item added later changes none of them. The run record stores `ruled_exclusions` as read; the window fingerprint hashes the items read and is recorded once, in the run record and the reservation, and recomputed by nothing after the verdict (the window read refuses a run entry first); `registry._guard_state` reads the ledger's `confirmation_cohort`/`test_cohort`, `run` and `confirmation` fields and the five files, so its "run record" kind compares that frozen run field, never the entry's live `ruled_exclusions`; the run's ids file holds only the 60 ids; `confirmation_basis`, `opening`, `fence_cutoff` and `confirmation_refusal` read no ruled item. A test pins the guard state, the stored run record, the run's ids file, the window's reservation, the fence, the opening, the account and the backstop unchanged by an item added after the verdict.
  - Q5: built in `registry._confirmation_checked` (so `confirmation_refusal`, the reader's backstop, catches each before the reservation), only past the opening's own checks for an entry holding a readable opening: (a) the window run's ids file missing refuses; (b) the count must equal plan.n_games; (c) `first_game_id` must be one of the confirmation's ids. An entry without an opening keeps today's rule on each, a test for each.
- **Named for the record:**
  - B2(d)'s day after is held on the 60th confirmation member (540 item 1: "YOUR INFERENCE STANDS").
  - "Before the opening" in C1(d) is read in the window's order, (kickoff, id) <= the opening: an unaccounted game tied at the opening's kickoff with a lower id is a finding. The finding is "a game before the opening in the window's order that the run record does not account for": re-dated, or (at sub-second precision) in the opening's second with an id not above the opening's. The console never calls it re-dated as a fact (its head reads "not accounted for by the run record"); the result keys `redated_findings` / `REDATED` keep their names, which state no re-dating.
  - A finding that is a regular game not final makes the read WAIT (the walk reads it), as built.
  - A took-no-slot game re-dated to a kickoff still at or before the opening is no finding (the run record accounts for it) and is in neither cohort; it prints on its own line and is kept in the result as `redated_no_slot`.
  - The backstop is not optional: whatever the registry would refuse is read before the reservation, so the read is never spent on a cohort record_confirmation must refuse.
  - The opening's resolution (447's PR 3, review P2): the opening is stored to the second, with the Z (448 item 1(d)), so every comparison with it (the cohort's "later", the account, the findings, the window members now after it, the backstop's place check) reads each game's kickoff CUT to the whole second, never rounded, against the opening as stored (`leagues_window.after_opening`). A game the run record accounts for (a window member, or a game its loop reached that took no slot) is after the opening only in a LATER second (re-dated past the opening's second): a member still in the opening's second is never after it, whatever its id (the verification's case: the 59th member 2700 at +200 ms, the 60th 2059 at +500 ms, the opening (that second, 2059); before this, 2700 landed in the members after the opening and Q3 refused permanently although nobody re-dated it). Every other game by its place (`leagues_window.place`): in the opening's second with a higher id it is after the opening, with a lower or equal id before it. At whole-second kickoffs nothing changes; the window's own read (no opening) is byte-identical. In the confirmation's read a ruled item's kickoff (to the second, with the Z) is compared with the game's kickoff cut to the second (`apply_ruled(..., cut=True)`), so an item copied from a refusal matches a sub-second kickoff; the window's read keeps its exact comparison, unchanged (pre-existing).
  - 540 item 1 Q3's order (review P2): a window member now later than the opening is read BEFORE the confirmation's state, in the read and the preflight (`leagues_confirm.moved_refusal`), so a member re-dated to a later second that is not final refuses naming the game and never makes the read WAIT.
  - The guard's "confirmation record" kind pairs the ledger's `confirmation` with its ids file, as "run record" pairs `run` with its file (a design choice). The guard is shared: today nothing holds either kind, so nothing changes; a soccer-expansion-v1 confirmation left on an unmerged laptop branch would refuse that entry's later guard calls until merged; its own `--record` path calls no guard, so 447 C2's PD morning order is unaffected.
  - The host's counts-only reader (scripts/leagues_window.py) has no confirmation mode; only the laptop preflight shows the confirmation accruing.
  - The confirmation reader goes through no fence: membership() consults none, and a test pins that the fence refuses another reader while the confirmation reads.
- **Tests:** tests/test_447_leagues_confirmation_read.py (62, new), tests/test_467_first_game_id.py (41, new), four in tests/test_registry_cross_ref_guard.py, and tests/test_447_leagues_policy.py's recording cases amended (467 item 1(a); 540 item 1 Q5). Nothing run on either machine. No bar moves; no prediction output changes.
