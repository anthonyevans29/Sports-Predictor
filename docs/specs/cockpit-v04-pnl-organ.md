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
