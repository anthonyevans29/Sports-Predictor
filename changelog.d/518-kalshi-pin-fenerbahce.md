## 2026-10-14 (#518: kalshi-pin-fenerbahce — ARCHITECT addendum 66 item 4)
- src/ingestion/kalshi_match.py: a pin, "Fenerbahce" (as Kalshi writes it) is the stored club "Fenerbahçe".
  - The pin's name is written with ç as U+00E7, the NFC form the host's window card prints.
  - Its norm tokens equal the stored name's, as the other pins' do. norm_tokens folds no accent, so "Fenerbahce" alone shares no word with the stored name. That is why the laptop's wide probe refused KXUCLGAME-26OCT14AVLFEN and -26OCT20FENSLA for no fit.
  - Nothing else in the matcher changes: one each, the best fit, a tie refused, a pinned name fitting its own team and no other.
- Tests: tests/test_kalshi_matcher_day_rule.py (5 new):
  - the pin's tokens equal the stored name's, and the two spellings share no word unpinned;
  - the true case: Fenerbahçe @ Aston Villa places on its game with the Tie as DRAW, and is refused for no fit without the pin;
  - a stored name with one word more (Fenerbahçe SK), or with ç decomposed (c + U+0327), is not the pin's team and is refused;
  - the club's own game against another side, with Aston Villa absent, is refused as today.
