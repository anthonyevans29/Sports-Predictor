# COCKPIT v0.4 — THE P&L / SELF-GRADING ORGAN

Spec committed verbatim from the architect's consolidated rulings
(2026-09-26). Extended by the full-loop venue-edge ruling (BACKLOG
2026-09-26, PR #30). Policy version: v1.1.

---

COCKPIT v0.4 — THE P&L / SELF-GRADING ORGAN
1. PERSISTENCE: localStorage (per-viewer, try/catch-guarded),
schema key bd_ledger_v1: {meta:{policy_version}, calls:[{id,
log_date, sport, game, home, away, pick, tier, engine
(model_edge|venue_edge), call_type (straight|ladder|parlay_leg),
parlay_id?, units, model_p, market_p, venue_hint (books|kalshi),
quarantine, status (open|graded), result? (win|loss|push|void),
units_returned?, graded_date?}]}. MANDATORY Export/Import ledger
buttons (JSON). Idempotency: keyed on (sport, game, log_date) —
re-logging updates, never duplicates.
2. CAPTURE: "Log today's calls" on the Desk tab snapshots every
PLAY and LADDER row plus parlay tickets (legs share parlay_id) at
displayed units/prices. SHADOW ENTRIES: NFL quarantine PASSes log
at units 0, call_type "quarantine_shadow" — graded like real
calls, funding the counterfactual column. VENUE-EDGE calls (per
the #30 ruling: >=4 books + two-sided kalshi + |book−kalshi| >=
5.0pp, fixed 0.25u, tier shadow, single-venue/in-play never,
parlays model_edge-only) log through the same button with
engine=venue_edge, reusing src/walters/venue.py's math
client-side.
3. GRADING: results files and finished-status fixtures drop into
the SAME intake; grader matches open calls on (sport, home, away,
date±1), exact-first then normalized; unmatched stays open,
listed. Straight: pick vs winner (soccer draw loses a side pick).
Ladder/DC: pick-side or draw wins. Parlay: all legs win; void leg
drops from ticket. Returns at FAIR odds from stored market_p
(decimal = 1/market_p), labeled "fair-odds P&L, pre-fee".
4. OUTPUTS (third tab, "Ledger"): totals + by-engine / by-sport /
by-tier / by-call-type tables — n, staked, returned, net, ROI%,
hit rate; rolling equity line (SVG); quarantine counterfactual
line; TWO FEEDBACK STREAMS: "Copy P&L block" (plaintext weekly
income statement for the architect) and per-rule attribution for
policy v1.1 proposals.
5. NON-CLAIMS (footer): fair-odds pre-fee P&L is an EV-realization
proxy, not cash; venue-edge grades against stored kalshi prob
until the K-track delivers executable bid/ask + fees; first 50
graded calls per engine before any sizing proposal; policy changes
only via audit-backed version bump.

---

## Policy v1.1 addendum — EXECUTION TIMING (architect, 2026-09-28)

A position carries TWO timestamps.

**claim_at: the first prediction that created the position.**
- `claim_market_p` and `claim_model_p` are frozen at that capture.

**executed_at: the freshen at which the operator placed it.**
- `exec_mode: "close_default"`, the doctrine default, means *execute at close*.
  Every re-log before kickoff moves `executed_at` and `exec_market_p`, so they
  end at the last freshen before kickoff.
- `exec_mode: "operator_early"` is set by the operator's explicit **Execute now**
  (Ledger → Open calls). It is recorded with
  `early_inputs {edge_pp, qb_listed, quarantine}`, and it LOCKS: later
  freshens update the price context (`market_p`) but not the execution.
- A parlay ticket executes as a whole.
- Quarantine shadows are never executed; they are not placed.

**Doctrine.** Claim early, execute at close. The one exception is an operator
who explicitly executes early on a large, input-stable edge (no QB listed),
recorded as such. The Cockpit flags an early execution on a QB-listed game as
"outside the doctrine's input-stable condition (recorded as such)". **No sizing
changes.**

**Grading.**
- Returns settle at the EXECUTION price: `exec_market_p`, falling back to
  `market_p` for a position logged before this rule.
- The claim-price counterfactual is booked alongside, as
  `claim_units_returned` / `claim_shadow_returned`.

**P&L block.**
- A new **"claim vs exec"** column on the engine lines shows net@exec − net@claim
  over bets whose claim is known, as `+x.xx/k`.
- A new **EXECUTION TIMING** section breaks this down per mode (close_default,
  operator_early): n, average claim p, average exec p, drift pp,
  net@claim, net@exec, and exec − claim.
- Over time this measures whether early or late execution earns more.

**Pre-rule positions.** These carry no claim. They stay null and are labelled
("claim unknown … excluded, never backfilled"; law 4).

**Rulings (architect, 2026-09-28).**
1. **"Large edge": RECORD, DON'T ENFORCE, for now.** The instrument exists to
   learn where the threshold belongs. A provisional **8pp marker** is written
   into each early execution's record: `early_inputs.marker_pp: 8`, and
   `below_marker: true|false` (null when the edge is unknown). An execution
   below it is flagged "below the provisional 8pp marker (recorded, not
   enforced)". The P&L block tallies
   `Early executions: n position(s) · below the provisional 8pp marker: k ·
   threshold revisit at 50 executed positions (n/50)`. **Revisit the
   threshold after 50 executed positions**, with a parlay ticket counting as
   one.
2. **Early execution on a parlay leg applies to the whole ticket:
   RATIFIED.** A ticket is one position.
3. **Quarantine shadows cannot be executed: RATIFIED.** By contract they
   are never placed.
