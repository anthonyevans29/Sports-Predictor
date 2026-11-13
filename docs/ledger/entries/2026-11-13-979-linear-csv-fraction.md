**2026-11-13 — FIXED (#979; ARCHITECT 2026-11-13 09:00 ET, addendum 364 item 2): CSV_RUN (the shared #817 header-row pattern) and the bulletin guard's FRACTION backtracked quadratically (slow, never wrong). Both now read in linear time and match exactly what they matched before. THE CLASS IS CLOSED: one test holds every pattern in src/privacy_patterns.py to one bound.**
- **The quadratic reads:**
  - a long word (CSV_RUN: 11.6 s on 20,000 letters; 54.6 s through the guard);
  - a field and a run of tabs (CSV_RUN, found while building: 4.7 s on 20,000 tabs);
  - underscore runs (FRACTION: 3.5 s on 20,000).
- **Proof of the same strings:** CSV_RUN's runs are matched span for span against main's pattern, with `is_header`'s answer and FRACTION's match. The checks are exhaustive over every short line, seeded random lines, and curated lines.
- **The class:** `tests/test_privacy_patterns_linear.py` reads the module for its patterns, so a pattern added later is held to the bound without being named. Aliases of `re` fail it, and an exponential pattern fails at a per-read deadline instead of hanging. The scan after the fix found no pattern in the module super-linear on the 40 shapes. A wider scan (1,444 one- and two-character units under 16 prefixes) found none either.
