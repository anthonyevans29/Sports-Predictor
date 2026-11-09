"""SCORES BY TEAM (ARCHITECT 2026-11-08, addendum 292 item 3; #876): the one shared helper both score writers call.

Item 3(a), verbatim: "ONE shared helper, scores BY TEAM: given the stored row's (home_team_id, away_team_id) and the
listing's (home_id, away_id): the same pair → exactly today's writes; the REVERSED pair → every score field written
swapped into the stored orientation (home/away, _ht, _90) and full_time_result H↔A (D unchanged), the kickoff and
status as served; NEITHER → the update REFUSED for that listing, the row untouched, counted (law 4)".
Item 3(d): "the stored orientation is NOT flipped by the sync — the venue disagreement is a listed finding, and a flip
of a stored row's home/away is a separate step on a ruling, never silent".
A reversed pair on a row of the SAME season is a reversal; across seasons it is a collision and never reaches the chain
(addendum 310 item 3(e)).

Callers (item 3(b)): src/ingestion/service.py `_upsert_match` (the update-by-id and re-key branches) and
src/ingestion/refresh_by_id.py. The create path never calls it: a new row takes the listing's own orientation.
This module decides and translates only; it writes nothing and imports no ORM session (no cycle: schema only): the
callers assign what with_orientation_key returns.
"""
from __future__ import annotations

from src.db.schema import Result

SAME = "same"
REVERSED = "reversed"
MISMATCH = "mismatch"

# Every home/away score pair the `matches` table holds (src/db/schema.py, read 2026-11-08): the score, the half-time
# score and soccer's 90-minute score. full_time_result is the one other score field.
SCORE_PAIRS = (("home_score", "away_score"), ("home_score_ht", "away_score_ht"), ("home_score_90", "away_score_90"))
RESULT_FIELD = "full_time_result"
_FLIP = {Result.HOME: Result.AWAY, Result.AWAY: Result.HOME, Result.DRAW: Result.DRAW}


def orientation(stored: tuple, listed: tuple) -> str:
    """SAME when the listing's (home, away) team ids are the stored row's, REVERSED when they are its reverse, else
    MISMATCH. An unresolved side (None) never matches, and a pair whose two sides are one team is never REVERSED."""
    sh, sa = stored
    lh, la = listed
    if None in (sh, sa, lh, la):
        return MISMATCH
    if (lh, la) == (sh, sa):
        return SAME
    if (lh, la) == (sa, sh) and sh != sa:
        return REVERSED
    return MISMATCH


def scores_by_team(stored: tuple, listed: tuple, values: dict) -> tuple[str, dict | None]:
    """(verdict, the values in the STORED orientation). `values` holds the incoming score fields by their column
    names (any subset of SCORE_PAIRS' fields and full_time_result); a field it leaves out stays out. SAME returns them
    unchanged; REVERSED returns each home/away pair swapped and full_time_result H<->A (D, and None, unchanged);
    MISMATCH returns None: the caller writes nothing to the row."""
    verdict = orientation(stored, listed)
    if verdict == MISMATCH:
        return verdict, None
    out = dict(values)
    if verdict == REVERSED:
        for h, a in SCORE_PAIRS:
            if h in values or a in values:
                out[h], out[a] = values.get(a), values.get(h)
        if out.get(RESULT_FIELD) is not None:
            out[RESULT_FIELD] = _FLIP[Result(out[RESULT_FIELD])]
    return verdict, out


# THE PRICE BELONGS TO THE TEAM (ARCHITECT 2026-11-08, addendum 295 item 5; #885). Item 5(a), verbatim: "When the
# listed pair is the stored row's reverse, the upsert writes `external_ids["provider_orientation"] = "reversed"`, and
# removes the key when the listing reads same; a mismatch writes nothing (the row untouched, as now). This is the one
# stored-state write I allow from the finding: it records what the provider's current listing says about our row, and
# it is what a later venue-flip ruling would read." Addendum 297 C(i)/(ii) amend it: refresh-by-id writes it too, and a
# mismatch writes `mismatch` (with_orientation_key below, the one place the value is decided). A re-key outside those
# two paths keeps the key tied to the provider id it describes (src/ingestion/match_dedupe.py: a merge takes the key
# of the id the keeper keeps, a relink to a same-pair live id removes it).
PROVIDER_ORIENTATION_KEY = "provider_orientation"
# Item 5(b), verbatim: "`sync_odds`, `sync_odds_nfl` and the MLB fallback's odds path, if it has one, swap HOME and AWAY
# selections into the stored orientation when the key is present, counted on the receipt with the match ids; the 1X2
# devig into odds_snapshots then follows the stored orientation." Only the two team selections swap: DRAW, OVER and
# UNDER name no team and stay as served; a SPREADS row's `line` is that selection's own handicap, so it travels with
# the price (the team it belongs to), never re-signed.
_SELECTION_SWAP = {"HOME": "AWAY", "AWAY": "HOME"}


def provider_reversed(external_ids) -> bool:
    """True when the stored row carries the upsert's record that the provider lists its pair reversed."""
    return (external_ids or {}).get(PROVIDER_ORIENTATION_KEY) == REVERSED


# THE KEY'S THREE VALUES AND ITS ONE WRITE (ARCHITECT 2026-11-08 13:05 ET, addendum 297 item C). C(i), verbatim: "The
# "one stored-state write" of 295 item 5(a) is the KEY, not the call site: every path that reads a listing against the
# stored pair may write it." C(ii), verbatim: "a MISMATCH writes the key's third value, `mismatch` (the key records
# what the provider's current listing says about our row: absent = same, `reversed`, `mismatch`), and the two odds
# writers REFUSE to price a row whose key reads `mismatch`". The callers: src/ingestion/service.py `_scores_by_team`
# (the upsert) and src/ingestion/refresh_by_id.py (refresh-by-id); each assigns what this returns, nothing else.
_KEY_VALUE = {SAME: None, REVERSED: REVERSED, MISMATCH: MISMATCH}


def with_orientation_key(external_ids, verdict: str) -> dict | None:
    """The row's external_ids after recording `verdict` under PROVIDER_ORIENTATION_KEY (SAME: the key removed;
    REVERSED: "reversed"; MISMATCH: "mismatch"), every other key as stored; None when the row already says so, so the
    caller reassigns nothing (a same-pair row without the key is never touched)."""
    ext = dict(external_ids or {})
    want = _KEY_VALUE[verdict]
    if want is None:
        if PROVIDER_ORIENTATION_KEY not in ext:
            return None
        ext.pop(PROVIDER_ORIENTATION_KEY)
        return ext
    if ext.get(PROVIDER_ORIENTATION_KEY) == want:
        return None
    ext[PROVIDER_ORIENTATION_KEY] = want
    return ext


def provider_mismatch(external_ids) -> bool:
    """True when the provider's last listing of the row's id named neither its pair nor the reverse (C(ii)): the odds
    writers refuse to price such a row, its stored prices untouched."""
    return (external_ids or {}).get(PROVIDER_ORIENTATION_KEY) == MISMATCH


def selection_by_team(selection: str, reversed_: bool) -> str:
    """The provider's selection in the STORED orientation: HOME <-> AWAY when the row is listed reversed, every other
    selection (DRAW, OVER, UNDER, anything unknown) as served."""
    return _SELECTION_SWAP.get(selection, selection) if reversed_ else selection
