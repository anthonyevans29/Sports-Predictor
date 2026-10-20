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
re-logging updates, never duplicates. [As built and amended: the key
is (sport, game, log_date, engine, call_type, pick, parlay slot); the
pick joined it by ARCHITECT 2026-10-20, addendum 145 item 3(b) R4:
"The unit of account is the position (the 2026-09-28 ruling on #49;
instKey already carries the pick), and a same-day pick flip is two
claims, never one". Stored calls keep their ids; the index is rebuilt
from the fields on every load (#431).]
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

**The order (#431 R16, ARCHITECT 2026-10-20, addendum 146 item 1(iv)).** "the
ledger stores the page's ORDERED size and limit beside the FILLED size and
entry".
- Every PLAY, LADDER and VENUE claim stores the page's order line copy-exact as
  `kalshi_order`: `{ticker, side, limit, contracts, unit}` (the limit in
  dollars, the contracts for the call's whole units), or `{why}` when the page
  wrote no order. A shadow and a ticket leg store null. A VENUE call stores the
  order only on a market-only row (the venue table's read); a VENUE call on a
  model row stores null.
- `claim_order` is frozen at the first capture. `exec_order` follows every
  re-log, as `exec_market_p` does, and **Execute now** locks it. On a claim from
  before R16 (no `kalshi_order` key) Execute now writes no `exec_order`, so the
  claim stays legacy (part of the legacy proposal, escalated, #632).
- They are written at claim, never at save. A claim from before R16 carries
  none and is never backfilled.
- Each stored closing page (`meta.closings`) keeps its orders by call key
  (`orders`) and the closing row's Kalshi legs (`legs`, the closing quote R17
  reads).

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
- A **Closing CLV** line follows the executed-position CLV block (#431 R17,
  ARCHITECT 2026-10-20, addendum 146 item 1(iv): "each position carries entry
  minus the closing ask on its pick (true CLV, in cents) and the P&L view sums
  it beside the P&L"; the sign CORRECTED by addendum 148 item 1(b): "ask minus
  entry, + = bought below the close"):
  `Closing CLV (close − entry; + = beat the close) (addendum 146 item 1(iv) R17, #431): P position(s), F fill(s) · sum ±S.Sc · mean ±M.Mc per position · graded G · open O — read against the closing page X, the slate page Y, outside any page Z · L legacy claim(s) carry no stored order (claimed before R16) · N with no stored closing page · A ambiguous · U on a contract the page does not quote (not priced) · Q with no closing quote stored · R16: K fill(s) above their page's limit (max +X.Xc) · V over the ordered size · W partial`.
  - Every segment, in that order. The L, N, A, U and Q segments print only
    when their count is above 0. "(max +X.Xc)" prints only when K is above 0.
    The sum and the mean read "none" when no position is priced. With no
    position (P = 0) the line ends after "mean none per position".
  - The figures are cents to one decimal, signed: rounded first, then "+" on
    zero and above, so a blend at the close prints +0.0c, never -0.0c (as
    clvLines prints a zero, "+0.00pp").
  - The legacy segment (L) is the builder's addition, outside the ruled shape:
    **proposed, escalated to the architect** (#632).
  - A position (addendum 148 item 1(d)) is a straight, VENUE or LADDER call,
    open or graded, marked or not, with a matched Kalshi CSV fill. Tickets,
    shadows, void calls and a manual Record fill (1(h)) are not positions.
  - Its CLV (1(c), 1(f)) is qty-weighted over its fills, in cents, pre-fee: the
    stored closing page's ask on the held contract (the leg whose ticker is the
    fill's; YES its ask, NO 1 − its bid) minus the fill's entry. It is null
    unless every fill prices.
  - The sum and the mean read the priced positions. A position is not priced
    when no stored closing page covers it, when two do ("ambiguous", never
    guessed, law 4), when a fill's contract is not on the page, or when the page
    was stored before its quotes were (1(i): no backfill). Each case is counted
    on the line.
  - Its order (1(e)) is the closing page's whenever one is stored for the call,
    else the slate's (`exec_order`), else none ("outside any page"). A claim
    from before R16 is counted as legacy, never as outside any page (part of
    the legacy proposal, escalated, #632).
  - R16's flags (1(g)) are counted, never left out of the CLV: fills above
    their page's limit (the largest excess in cents), positions over the
    ordered size, and partial positions.

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
