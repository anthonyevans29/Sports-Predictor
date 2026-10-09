**2026-10-08 — ncaa-elo-v1r PR B: the gate command (D3-D6) and the confirmation command (D7) are built. Not run: the run waits on the architect's word and the stream fingerprint it refers to.**
- **Ruling (verbatim, ARCHITECT 2026-10-08, addendum 11 item 3):** "PR B, after PR A: the gate command for D3 to D6 with --preflight, the reservation and the one recorded run, on the soccer-expansion-v1 pattern; then the confirmation command for D7 on the intl-elo-confirm pattern. #79's ncaa-backtest stays as it is."
- **`ncaa-v1r-gate`:**
  - `--preflight` scores nothing. It prints, per season, the stream by season_type, the neutral count, the coverage and the D4 baseline. Its last line is the stream fingerprint.
  - The one run refuses, exit 2 and nothing written, unless: declared and unrun; `--architect-word` given; `--stream-fingerprint` given; 2024 + 2025 covered; the loaded stream's fingerprint matches; the scored set numbers >= 500. Every check comes before the reservation.
  - The reservation follows the #329 cross-ref guard, carries the word and the fingerprint, and precedes the first game scored.
  - The scored ids are recorded, with the word and the fingerprint in the run record.
- **PR B's four choices, RULED (ARCHITECT 2026-10-08 18:56 ET, addendum 17, verbatim):**
  1. "The run takes my word as --architect-word, verbatim, and writes it into the reservation and the run record. There is no OPEN_ITEMS gate: one lock is enough, and this is the one that leaves my word in the record. What the word needs is to refer to one stream. --preflight ends with one line, a fingerprint of the 2024 and 2025 stream exactly as the gate would walk it: the games in order, with every label field the gate reads. The run takes that fingerprint as a required option and refuses, before the reservation, when the stream it is about to walk no longer matches. The fingerprint is recorded beside the word."
  2. "The scored set is known before any game is scored: the 2025 games whose season_type is exactly 'regular', less the level scores. If it numbers under 500 the run refuses before the reservation and records nothing; no game has been scored. That is #79's rule: not scored, re-run later, the bar does not move."
  3. "The walk ends after the last 2025 game: as built."
  4. "A confirmation fixture without a current label stays pending, never replaced: as built. The first 100 fixtures after an October verdict are all 2026 games, so the 2027 case cannot arise in this cohort."
- **Built on addendum 17:**
  - `OPEN_ITEMS` and its refusal are removed.
  - The fingerprint is a sha256 over the walked stream (every game up to the last 2025 game, in walk order). Each game carries match id, kickoff, label season, season_type, merged home and away ids, both scores, the neutral flag and the label source: every field the walk reads or orders by. Spec section 8 lists what reads each one.
  - Both refusals need the stream, so the run loads it before the reservation (the read `--preflight` makes; nothing scored). The reservation still precedes the first game scored.
  - The INVALID-is-recorded path is gone from the run. `run_gate` keeps the INVALID verdict as a pure-function backstop.
- **#375's two readings, RULED (ARCHITECT 2026-10-09, addendum 21 item 4, verbatim):**
  1. Accepted. "What D6 seals is the scoring of the test season: a game priced by the candidate and compared with its result. Loading the stream to fingerprint it and to count the scored set scores nothing and prints no figure across games; the preflight makes the same load. The reservation is written before any game is scored."
  2. "When 2024 has no non-neutral regular game, D4 is undefined and nothing can be scored: the run refuses before the reservation and records nothing, as it does under 500 games. It is not an INVALID run and the read is not spent."
- **Built on addendum 21 item 4:**
  - Reading (1), the stream loaded before the reservation (to fingerprint it and count the scored set; nothing scored), is accepted as built. No code change.
  - Reading (2): an undefined D4 baseline now refuses before the reservation (exit 2, nothing reserved or recorded), as under 500. The path that reserved and recorded an INVALID run with 0 scored ids is gone; `run_gate` raises the same refusal as a pure-function backstop.
- **`ncaa-v1r-confirm`:** follows the intl-elo-confirm pattern.
  - The freeze goes through `registry.freeze_confirmation_cohort`, which runs the guard.
  - Only a cancelled fixture is substituted. A finished fixture without a label stays pending.
  - It reuses the gate's replay. CONFIRMED iff log-loss <= 0.6931 and < the D4 baseline − 0.010 on the same games.
- **D5 (2)/(3):** one implementation in `ncaa_backtest`, imported by the design receipt. The receipt's output is identical before and after the extraction.
- **Finding for the architect, since ruled:** `ncaa-cfbd-coverage` printed the 2025 non-neutral home win rate. It became #368, RULED in addenda 14 and 15 and built on #365 (the test-season fence). `ncaa-v1r-gate --preflight` prints no 2025 outcome.
- **Codex on #375, round 1 (both verified and fixed):**
  - P2: a cancelled cohort fixture with a current label was scored and could complete the cohort. D7 ("A cancelled fixture is released and replaced by the next eligible one"): it is now never scored and stays pending until `--substitute`.
  - P2: `STALE_ORPHAN` rows (schema: "never deleted, never a fixture, never an odds target") entered the cohort and the replacement pool, where one could stay pending for ever. They are now never eligible. Reading: a stale orphan is not one of D7's "stored NCAA fixtures" (open to correction).
