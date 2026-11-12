## 2026-11-12 (#000: 896-dollar-words — the bulletin guard's own dollar pattern widens to spelled-out figures (#896; ARCHITECT 2026-11-10 12:20 ET, addendum 320 item 1).)
- **Ruling (verbatim):** "the BULLETIN guard's own dollar pattern widens to number words beside a dollar word (one..ninety-nine, hundred, thousand, million; dollars, USD, bucks; `$` followed by a number word), refusing; `sp_common.redact` is UNCHANGED (its contract is the exports' unit redaction and every writer shares it); a small follow-up from #896, not blocking."
- **Built:** `src/privacy_patterns.USD_WORD` (the guard's `usd_word`) now also matches:
  - a number word (one … nineteen, twenty … ninety, hundred, thousand, million; a compound ends in one of them) beside USD, dollar(s) or bucks;
  - USD before a number word;
  - a dollar sign (ASCII, fullwidth or small) before or after a number word;
  - "bucks" beside a digit.

  A match refuses the write, as every guard pattern does.
- **Unchanged:** the shared #817 `DOLLAR` pattern (tests/test_no_raw_kalshi_rows.py reads it), `sp_common.redact`, and every other pattern.
