## 2026-11-24 (#0000: 992-inferred-layer-design — the inferred data layer and the host-only store, the design PR, nothing built behind it (lane inferred-layer, #992; addenda 375, 376, 496 item 4(d), 501))
- **docs/specs/inferred-layer.md (new): the design only.** No code, store, timer, key, prompt, folder or row exists for anything in it. The architect rules on it on 2026-12-03.
  - **The rulings, quoted word for word:**
    - 375 items 1 and 2 and 376 items 1 and 2, from #992;
    - 368 items 3 and 5, 375 item 4 and 376 item 3, from addendum 501;
    - 379 item 2, 385 item 3(c), 428 item 5(b) and 496 item 4.
  - **The design itself** is Dev 2's proposal of 11-14, written as 375 and 376 declared the layer: the host-only store, the two tiers, the plugs and their destroy path, the reader, the bench, the score and gate, what leaves the host, the graph, the cost in tokens and calls, and the NBA report.
  - **What changed since 11-14:**
    - every repository fact the proposal cites is re-read on main `822ff041`, and ten are corrected, listed in §13. Among them: install.sh runs only in enabling blocks; the graph unit masks data/ read-only; the NBA probe's `--out` rule; host.env's own comment on keys, and the eleven units that load the file; `sp_migrate pack` as a carrier;
    - two inconsistencies inside the proposal are fixed: the lead-time buckets, and a landing baseline that does not exist before T-120;
    - 428 item 5(b)'s reading of the landing listing sits beside its baseline;
    - "series" is renamed "lineage".
  - **496 item 4(d)'s one paragraph (§7.6):** what the NHL pilot would measure now that no NHL model input waits on it. It sets out four readings and chooses none.
  - **My adversarial review** (two critics, two skeptics each): 18 findings held, all fixed. Among them: the calls ledger that the daily caps count (the review's P1); 496's closure stated no wider than it rules; the key's value kept in host.env; the bench's forward-only rule; a side's truth with two goalies in net; the destroy leaving the graph's rebuild to its own unit.
  - **§12 lists twelve points for the ruling of 12-03.**

  Nothing is built and nothing is run. No bar, date or held timer moves.
