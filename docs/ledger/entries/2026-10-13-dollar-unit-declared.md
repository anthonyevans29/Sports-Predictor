**2026-10-13 — DECLARED + FINDING (ARCHITECT 2026-10-13 10:12 ET, addendum 59 item 4): the operator has declared a dollar unit; the Cockpit's units. Logged with #488.**
- **The unit:** the operator declared a dollar unit on 2026-10-13 at 09:46 ET.
  - The figure is the operator's. It goes into the laptop's .env in the operator's block of 2026-10-14, and into the host's env the same day, as `SP_UNIT_USD`.
  - It is written in no file of the repo, no Issue and no PR, and this entry does not carry it.
  - This answers BACKLOG's open line "SP_UNIT_USD stays unset (10 contracts per 1u) unless the operator declares a dollar unit".
- **Nothing is built for it:** `desk_policy.unit_size` reads it, the order line's count becomes floor(units x dollars / limit), and the executable cost is worked on that count.
- **Finding #487 (policy; the Cockpit lane takes it):** the Cockpit's fills organ reads units as contracts over ten (`FILL_UNIT_CONTRACTS=10` in tools/cockpit.html) and marks an outcome over the 1.25u cap on that figure. With a dollar unit the contracts in a unit move with the price, so contracts over ten is no longer units.
- **RULED, for when the Cockpit lane takes it (verbatim):** "With the unit declared in dollars, a fill's units are its entry cost in dollars, fees left out, over the dollars of one unit. The dollars of one unit are read from the file's own order lines, as desk_policy.file_unit_basis reads them; the Cockpit holds no figure of its own. Contracts over ten is the reading for a file whose order lines say 1u = 10 contracts, and for nothing else." Nothing in the Cockpit changes before the architect has read that PR, and the page is republished only on the operator's word.
- Refs #487.
