**2026-11-21 — The by-id receipt's two classes (addendum 437 item 2; #1058; #1062).**
- **Ruling (437 item 2(a)-(b), in part):** "A stored venue id that is not a positive integer is NEVER ASKED [...] its own class ("stored id is not a provider id") [...] An answer in which the provider REFUSES THE ID (its errors block, as here) is that id's answer: kept as served, counted as its own class with the provider's words, and the run goes on. A transport failure or a rate limit still stops the run as today, resumable."
- **Why:** the first run stopped at its first call, on venue 0, and a re-run would ask venue 0 first again (437 item 1).
- **What landed:** the two classes, the refusal kept as served, and every other errors block still a stop. Seven tests. Nothing else of #1058 is taken (items 2 and 3 stay open).
- **Law 1:** a stored 0 is the provider's own `"id": 0` in a saved fixture. The one writer is src/ingestion/intl_venues.py:124 (from :55), and no code writes 0 for a missing id.
- **Next:** one review round, green CI and the architect's read; it merges by his block, and the receipt runs again into the same folder.
