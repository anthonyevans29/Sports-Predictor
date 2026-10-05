**2026-10-04 — BUILT (ARCHITECT lane 3, #211 B-track): fills-based exposure and cash-at-risk per team-outcome, beside the units cap.**
- **What:** the Cockpit's Realized card adds a per-game table built from the imported Kalshi CSV: gross stake, fees, hedge offset (only contracts that pay on every outcome; a soccer tie leaves home+away unhedged), cash at risk, and per team-outcome contracts ≈ units at 10/1u beside the 1.25u cap. Undecidable contract roles are excluded and counted.
- **Doctrine:** diagnostic only. Cap and sizing are unchanged, and nothing feeds a call. Fills are realized positions (exposure as executed, not a live book).
- **Review fix (2026-10-05):** grouping by the full settlement event ticker (doubleheaders are two events; no cross-event hedge; ambiguous event identity excluded and counted).
- **Open on #211:** load-order invariance (resolve by as_of) and the ticket "independence estimate" label stay queued; #211 stays open.
