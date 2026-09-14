"""
Match identification across data sources.

MLB Stats API and API-Baseball don't share game IDs. When syncing odds
from API-Baseball, we need to find the corresponding Match row in our DB
(which was written from MLB Stats API).

Matching strategy:
  - (sport, date ± 6h, normalized team names)
  - Normalization: lowercase, strip city prefixes, strip "the", strip
    common suffixes ("FC", "AC", etc — soccer-relevant, harmless for MLB).

Stays defensive: if no match is found, returns None and the caller logs
+ skips. Never inserts orphan data.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.schema import Match, MatchStatus, Sport, Team


# MLB-specific known prefix/suffix variants. API-Baseball tends to use full
# city names ("New York Yankees") while MLB Stats API may return short forms
# ("Yankees"). We normalize aggressively from both sides and compare.
_MLB_CITY_PREFIXES = {
    # multi-word city prefixes that should collapse
    "new york": "ny",
    "los angeles": "la",
    "san francisco": "sf",
    "san diego": "sd",
    "kansas city": "kc",
    "st. louis": "st louis",
    "tampa bay": "tampa bay",
    "chicago": "chicago",
    "boston": "boston",
}


def normalize_team_name(name: str) -> str:
    """
    Canonical lowercase form for team-name comparison.

    Rules (in order):
      1. lowercase, strip leading/trailing whitespace
      2. remove punctuation
      3. collapse multi-word city prefixes to their abbreviations
      4. drop common suffixes ("fc", "ac", "club")
      5. dedupe whitespace
    """
    if not name:
        return ""
    s = name.strip().lower()
    # Replace periods with spaces so "St.Louis" and "St. Louis" normalize
    # to the same form. Then strip remaining quote-like punctuation.
    s = s.replace(".", " ")
    s = re.sub(r"[,'\"`]", "", s)
    # Multi-word city prefixes
    for long, short in _MLB_CITY_PREFIXES.items():
        if s.startswith(long + " "):
            s = short + " " + s[len(long) + 1:]
            break
    # Common suffixes
    for suffix in (" fc", " ac", " club", " baseball club"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_match(
    s: Session,
    sport: Sport,
    home_name: str,
    away_name: str,
    commence_time: datetime,
    tolerance_hours: int = 12,
) -> Match | None:
    """
    Find a Match by (sport, time window, normalized team names).

    Returns the Match if exactly one fits; None if zero or ambiguous.
    Ambiguous matches indicate a doubleheader or a data problem — the
    caller should log and skip rather than guess.

    Time tolerance defaults to 12h: same-day games for a pair of teams
    are essentially unique (the only exception is doubleheaders, which
    the ambiguity check below catches). A 6h window was too tight given
    that different upstream feeds occasionally report times that differ
    by half a day if one is local and the other UTC.
    """
    home_norm = normalize_team_name(home_name)
    away_norm = normalize_team_name(away_name)
    if not home_norm or not away_norm:
        return None

    window_start = commence_time - timedelta(hours=tolerance_hours)
    window_end = commence_time + timedelta(hours=tolerance_hours)

    # Get candidate matches in the window
    candidates = list(s.execute(
        select(Match)
        .where(
            Match.sport == sport,
            Match.utc_date >= window_start,
            Match.utc_date <= window_end,
            Match.status != MatchStatus.CANCELLED,
        )
    ).scalars())
    if not candidates:
        return None

    # Pre-fetch team names for those candidates
    team_ids = set()
    for m in candidates:
        team_ids.add(m.home_team_id)
        team_ids.add(m.away_team_id)
    teams = {
        t.id: normalize_team_name(t.name)
        for t in s.execute(select(Team).where(Team.id.in_(team_ids))).scalars()
    }

    matches: list[Match] = []
    for m in candidates:
        m_home = teams.get(m.home_team_id, "")
        m_away = teams.get(m.away_team_id, "")
        # Direct name match
        if m_home == home_norm and m_away == away_norm:
            matches.append(m)
            continue
        # Last-resort substring match — handle "Yankees" vs "New York Yankees"
        # by checking that one contains the other after city-prefix normalization
        if (home_norm in m_home or m_home in home_norm) and \
           (away_norm in m_away or m_away in away_norm):
            matches.append(m)

    if len(matches) == 1:
        return matches[0]
    if len(matches) >= 2:
        # Doubleheader (or duplicate feed rows): two games, same teams, same day.
        # Rather than give up (which leaves DH games with no odds), disambiguate
        # by START-TIME PROXIMITY — each DH game has a distinct utc_date and the
        # odds' commence_time is closest to the game it belongs to (game 1 ~1pm,
        # game 2 ~7pm). Only do this when the candidate start times are actually
        # distinguishable; if they're within an hour of each other we can't tell
        # them apart, so we still skip rather than risk mis-attaching a line.
        by_dist = sorted(
            matches,
            key=lambda m: abs((m.utc_date - commence_time).total_seconds())
        )
        nearest, second = by_dist[0], by_dist[1]
        gap_hours = abs((nearest.utc_date - second.utc_date).total_seconds()) / 3600.0
        nearest_dist = abs((nearest.utc_date - commence_time).total_seconds()) / 3600.0
        second_dist = abs((second.utc_date - commence_time).total_seconds()) / 3600.0
        # require the two games to be >1h apart AND the odds clearly closer to one
        if gap_hours >= 1.0 and (second_dist - nearest_dist) >= 1.0:
            return nearest
    # Truly ambiguous (indistinguishable times) or zero — skip rather than guess.
    return None
