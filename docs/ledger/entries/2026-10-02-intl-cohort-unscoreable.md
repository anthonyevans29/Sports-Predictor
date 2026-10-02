**2026-10-02 — intl-elo-v2 cohort: AWD/WO RULED — unscoreable fixtures are released and substituted, the raw code recorded as reason.**
- **Ruling (verbatim):** "AWD/WO (forfeit, walkover) games are RELEASED and substituted exactly like cancelled/abandoned — unscoreable is the criterion, not the status label; record the raw code as reason."
- This answers the open question left in #248's entry: AWD / WO store as FINISHED with no 90-minute score, so they were neither cancelled nor scoreable.
- **Built:**
  - `intl_shadow._unscoreable`: a fixture is unscoreable if it is cancelled (CANC / ABD), or finished under a non-FT code without a 90-minute score. That covers AWD / WO, and by the same criterion AET / PEN rows missing the 90-minute split (the stream's own rule in `ie.load` can never admit them).
  - A FT row whose score has not arrived is data lag, not unscoreable: it stays pending.
  - The substitution's reason is the raw provider code (e.g. `ABD`, `AWD`); its evidence is `{status, status_raw, unscoreable: true, kickoffs}`.
  - Replacements are never unscoreable themselves.
