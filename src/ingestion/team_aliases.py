"""
Sport-generic team-name normalization + alias expansion.

External sources name teams differently than our DB (football-data.co.uk says
"Man City" / "Nott'm Forest"; Kalshi says "Sacramento" for the Athletics).
Rather than exact-match on strings, matchers here work on TOKEN SETS expanded
with known synonyms on BOTH sides — so it doesn't matter which form the DB
happens to hold.

Matching philosophy (same as the Kalshi matcher, our hardest-won lesson):
  * gate on DATE first,
  * require BOTH teams of a row/market to fit the same game,
  * REFUSE ambiguity — a wrong-game price silently poisons everything
    downstream; a missing one is just a gap that gets reported.
"""
from __future__ import annotations

import re

# token -> canonical token. Applied to every token on both sides before
# comparison. Keep entries lowercase.
TOKEN_SYNONYMS: dict[str, str] = {
    # --- soccer (football-data.co.uk / Kalshi style -> canonical) ---
    "man": "manchester",
    "utd": "united",
    "nott'm": "nottingham",
    "nottm": "nottingham",
    "spurs": "tottenham",
    "wolves": "wolverhampton",
    "wolverhampton": "wolverhampton",
    "sheff": "sheffield",
    "hull": "hull",
    "leeds": "leeds",
    "afc": "afc",
    # --- mlb (kalshi quirks) ---
    "sacramento": "athletics",   # A's temporary home; Kalshi titles by city
    "oakland": "athletics",
    "a's": "athletics",          # Kalshi's actual MLB title form (probed 2026-08-18)
    "st.": "st",
    "st": "st",
}

_PUNCT = re.compile(r"[^\w\s']")


def norm_tokens(name: str) -> set[str]:
    """Lowercase, strip punctuation, split, apply synonyms. Drops 1-char
    tokens (single letters are handled separately by callers that need
    initial-letter tiebreaks, e.g. the Kalshi MLB matcher)."""
    if not name:
        return set()
    cleaned = _PUNCT.sub(" ", name.lower())
    out = set()
    for w in cleaned.split():
        w = TOKEN_SYNONYMS.get(w, w)
        if len(w) > 1:
            out.add(w)
    return out


def team_match_score(external_name: str, db_name: str) -> int:
    """Synonym-expanded token overlap. 0 = no match."""
    return len(norm_tokens(external_name) & norm_tokens(db_name))


def norm_token_list(name: str) -> list[str]:
    """Like norm_tokens but ORDER-PRESERVING (for acronym checks: the
    initials of "White Sox" are 'ws' only in word order)."""
    if not name:
        return []
    cleaned = _PUNCT.sub(" ", name.lower())
    out = []
    for w in cleaned.split():
        w = TOKEN_SYNONYMS.get(w, w)
        if len(w) > 1 and w not in out:
            out.append(w)
    return out
