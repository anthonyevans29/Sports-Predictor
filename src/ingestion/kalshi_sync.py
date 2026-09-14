"""
Kalshi sync — pulls MLB game markets and stores each team's implied win prob as
an OddsSnapshot row with source="kalshi", parallel to the bookmaker de-vig
consensus (source="consensus"/book sources). This lets the disagreement read be
a clean self-join on odds_snapshots by (match, selection).

Matching Kalshi markets to our games is best-effort and REPORTED, not silent:
Kalshi titles/tickers encode the teams; we match on team name against the day's
scheduled matches. Unmatched markets are counted and surfaced so we can see
coverage rather than assume it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from src.adapters.kalshi import KalshiAdapter
from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return "".join(c for c in (s or "").lower() if c.isalnum())


def sync_kalshi_mlb(date_from=None, date_to=None, progress=None,
                   sport=None, series_override: str | None = None) -> dict:
    """
    Pull open Kalshi MLB game markets, match to scheduled MLB games in the
    window, store each side's implied prob as an OddsSnapshot(source="kalshi").
    Returns a summary dict. Does NOT devig (Kalshi yes/no is already ~a
    probability; for a two-sided game we store each team's yes-prob and also a
    normalized pair so the comparison is apples-to-apples with the book devig).
    """
    def report(m):
        if progress:
            progress(m)

    adapter = KalshiAdapter()

    # connectivity + discover the MLB series (never hardcode the ticker)
    report("Checking Kalshi status…")
    st = adapter.status()
    if not st.get("trading_active", False):
        report("Note: Kalshi trading not currently active (prices may be stale/closed).")

    report("Discovering MLB game series…")
    # optional: show what sports Kalshi exposes (helps debugging coverage)
    sf = adapter.sports_filters()
    if sf and sf.get("sport_ordering"):
        sports = sf.get("sport_ordering", [])
        report(f"  Kalshi sports available: {', '.join(sports[:12])}")

    # Target ONLY the daily game moneyline series — not all 200+ MLB series
    # (which trips the rate limit and is 99% props/awards/futures noise).
    # NFL phase 1c (2026-09-06): the two-sided matcher serves any US-team-
    # sport series — parameterized rather than copied. Non-MLB callers pass
    # their series ticker (KXNFLGAME); empty results report available sports.
    _series_label = series_override or adapter.GAME_SERIES
    report(f"  fetching game series {_series_label}…")
    all_markets = (adapter.open_markets_for_series(series_override)
                   if series_override else adapter.game_series_markets())
    if not all_markets:
        return {"ok": False, "reason": f"no open markets in {_series_label} "
                "(series ticker may have changed — check available series)",
                "sports_available": sf.get("sport_ordering", []) if sf else []}
    report(f"  {len(all_markets)} open game markets")
    # DIAGNOSTIC: show one raw market so we can see how teams/prices are encoded
    if all_markets:
        s0 = all_markets[0]
        report(f"  sample market keys: {sorted(s0.keys())}")
        report(f"  sample: ticker={s0.get('ticker')!r} title={s0.get('title')!r} "
               f"yes_sub_title={s0.get('yes_sub_title')!r} "
               f"yes_bid_dollars={s0.get('yes_bid_dollars')!r} "
               f"yes_ask_dollars={s0.get('yes_ask_dollars')!r} "
               f"last={s0.get('last_price_dollars')!r}")

    # load candidate scheduled games in the window
    now = datetime.utcnow()
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=2))
    matched, unmatched = 0, 0
    stored = 0
    with session_scope() as sess:
        games = list(sess.execute(
            select(Match).where(Match.sport == (sport or Sport.MLB),
                                Match.utc_date >= lo, Match.utc_date <= hi)
        ).scalars())
        # index games by BOTH teams' normalized name AND token sets, so we can
        # match Kalshi's naming ("Texas", "Los Angeles A") to ours ("Texas
        # Rangers", "Los Angeles Angels") by overlap rather than exact string.
        #
        # Matching is a three-stage gate, strict on purpose (a wrong-game price
        # is worse than a missing one — it silently poisons the disagreement
        # read):
        #   1. TIME: market's occurrence_datetime must be within a few hours of
        #      the game's first pitch. The game series lists several days of
        #      markets at once, so name-only matching pins e.g. Friday's
        #      Cardinals market onto tonight's Cardinals game.
        #   2. TEAMS: BOTH teams in the market title must overlap the game's
        #      two teams. This is what disambiguates shared city names — a
        #      lone "New York Y" ties against Yankees and Mets games, but
        #      "Seattle vs New York Y" only fits the game that also has
        #      Seattle in it.
        #   3. SIDE: yes_sub_title picks HOME/AWAY within the matched game.
        #      Kalshi's disambiguator for two-team cities is a single letter
        #      ("Chicago C" vs "Chicago W"), which full-word tokens drop, so
        #      single letters are kept as initial-of-nickname tiebreakers
        #      (c->Cubs, w->White Sox). Ties are REFUSED and counted, never
        #      guessed.
        def tokens(name):
            # team_aliases carries the synonym map (sacramento/oakland ->
            # athletics etc.), shared with the soccer matcher and the
            # football-data ingest — one alias mechanism, all sports.
            from src.ingestion.team_aliases import norm_tokens
            return norm_tokens(name)

        def initials(name):
            # single-letter words, e.g. the trailing 'C' in "Chicago C"
            return set(_norm(w) for w in (name or "").split() if len(w) == 1)

        MAX_START_DRIFT = timedelta(hours=5)  # occurrence vs our utc_date

        def side_score(kalshi_name, team_name):
            """Word overlap, with initial-letter tiebreak worth half a point."""
            ttok = tokens(team_name)
            score = float(len(tokens(kalshi_name) & ttok))
            if any(any(t.startswith(i) for t in ttok) for i in initials(kalshi_name)):
                score += 0.5
            return score

        matched_rows: dict[tuple[int, str], float] = {}  # (match_id, side) -> prob
        ambiguous = 0
        in_play = 0
        for mk in all_markets:
            prob = adapter.implied_prob(mk)
            if prob is None:
                continue

            # ---- gate 1: time
            occ = adapter.occurrence(mk)
            # Kalshi game markets stay OPEN during play; a price captured after
            # first pitch is an IN-GAME price (reflects the current score), not
            # a pre-game one. Storing it poisons every disagreement/CLV read
            # downstream. Pre-game prices only.
            if occ is not None and occ <= now:
                in_play += 1
                continue
            candidates = games
            if occ is not None:
                candidates = [g for g in games
                              if g.utc_date and abs(g.utc_date - occ) <= MAX_START_DRIFT]
            else:
                # M13 (2026-08-25): occurrence_datetime missing — the exact
                # condition under which same-city markets ("New York wins")
                # tie across two different games and get refused. The ticker
                # embeds the start stamp (…-26AUG242145CINSF-SF, ET); parse
                # it and apply the same time filter. Unparseable ticker →
                # no filter → today's refuse-safe behavior.
                import re as _re
                _mt = _re.search(
                    r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
                    r"(\d{2})(\d{2})(\d{2})[A-Z]", mk.get("ticker") or "")
                if _mt:
                    try:
                        from zoneinfo import ZoneInfo
                        _mon = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                "JUL", "AUG", "SEP", "OCT", "NOV",
                                "DEC"].index(_mt.group(2)) + 1
                        _tick_et = datetime(
                            2000 + int(_mt.group(1)), _mon,
                            int(_mt.group(3)), int(_mt.group(4)),
                            int(_mt.group(5)),
                            tzinfo=ZoneInfo("America/New_York"))
                        _tick_utc = _tick_et.astimezone(
                            ZoneInfo("UTC")).replace(tzinfo=None)
                        _filtered = [
                            g for g in games
                            if g.utc_date and
                            abs(g.utc_date - _tick_utc) <= timedelta(hours=2)]
                        if _filtered:
                            candidates = _filtered
                    except (ValueError, KeyError):
                        pass
            if not candidates:
                unmatched += 1
                continue

            # ---- gate 2: both title teams must fit the game
            tt = adapter.title_teams(mk)
            yes_team = adapter.yes_team(mk)
            best_g, best_score = None, 0.0
            tie = False
            gate2_scores: dict[int, float] = {}
            for g in candidates:
                if not (g.home_team and g.away_team):
                    continue
                if tt:
                    a, b = tt
                    # each title team must overlap a DIFFERENT side of the game
                    s1 = max(side_score(a, g.home_team.name), side_score(a, g.away_team.name))
                    s2 = max(side_score(b, g.home_team.name), side_score(b, g.away_team.name))
                    if s1 < 1 or s2 < 1:
                        continue
                    score = s1 + s2
                else:
                    # no parseable title — fall back to yes-team only
                    score = max(side_score(yes_team, g.home_team.name),
                                side_score(yes_team, g.away_team.name))
                    if score < 1:
                        continue
                if score > best_score:
                    best_score, best_g, tie = score, g, False
                    gate2_scores = {g.id: score}
                elif score == best_score and best_g is not None and g.id != best_g.id:
                    tie = True
                    gate2_scores[g.id] = score
            if tie and best_g is not None:
                # Doubleheader tiebreak: two same-team games on one day can
                # both pass the time gate and tie on titles. Kalshi's ticker
                # carries the disambiguator we'd otherwise refuse over — a
                # G1/G2 suffix on the event (e.g. ...STLCING1-STL). Map G1 to
                # the earlier game, G2 to the later. Anything else still
                # refuses: a wrong-game price is worse than a missing one.
                import re as _re
                mgnum = _re.search(r"G(\d)-", mk.get("ticker") or "")
                if mgnum:
                    tied = sorted(
                        (g for g in candidates
                         if g.home_team and g.away_team
                         and {g.home_team.name, g.away_team.name}
                         == {best_g.home_team.name, best_g.away_team.name}),
                        key=lambda g: g.utc_date)
                    idx = int(mgnum.group(1)) - 1
                    if 0 <= idx < len(tied):
                        best_g, tie = tied[idx], False
            if tie and best_g is not None:
                # M13 v2 (2026-08-27): SIMULTANEOUS city collisions ("New
                # York wins" with NYY and NYM both ~7pm) defeat every time
                # filter. The ticker's matchup segment names the OPPONENTS,
                # which always differ between tied games (…HOUNYY… vs
                # …MILNYM…). Score each tied candidate by how many of its
                # teams' name tokens carry a 3+-letter uppercase prefix
                # found in the segment; resolve ONLY on a strict unique
                # maximum > 0. Anything else falls through to refusal.
                import re as _re2
                _seg_m = _re2.search(r"-\d{2}[A-Z]{3}\d{4}([A-Z0-9]+)-",
                                     (mk.get("ticker") or "").upper())
                if _seg_m:
                    _seg = _seg_m.group(1)
                    _tied = [g for g in candidates
                             if g.home_team and g.away_team
                             and gate2_scores.get(g.id) == best_score]

                    def _seg_hits(g) -> int:
                        hits = 0
                        for _name in (g.home_team.name, g.away_team.name):
                            for _tok in _name.upper().split():
                                if len(_tok) >= 3 and _tok[:3] in _seg:
                                    hits += 1
                                    break
                        return hits

                    _ranked = sorted(((_seg_hits(g), g) for g in _tied),
                                     key=lambda x: -x[0])
                    if _ranked and _ranked[0][0] > 0 and (
                            len(_ranked) == 1
                            or _ranked[0][0] > _ranked[1][0]):
                        best_g, tie = _ranked[0][1], False
            if best_g is None or tie:
                unmatched += 1
                if tie:
                    ambiguous += 1
                continue

            # ---- gate 3: which side does 'yes' pay on?
            # Score against each team's DISTINCTIVE tokens only: two-team
            # cities share the city token, and an initial like the 'C' in
            # "Chicago C" starts BOTH 'cubs' and 'chicago' — the tiebreak
            # self-defeats exactly where it's needed. Dropping shared tokens
            # first ("Chicago Cubs"/"Chicago White Sox" -> {cubs}/{white,sox})
            # makes the derby resolve; a residual tie still refuses.
            h_tok = tokens(best_g.home_team.name)
            a_tok = tokens(best_g.away_team.name)
            shared = h_tok & a_tok

            from src.ingestion.team_aliases import norm_token_list

            def _side_score_distinct(kalshi_name, team_name, team_tokens):
                distinct = team_tokens - shared
                score = float(len(tokens(kalshi_name) & distinct))
                # single-letter initial: the 'C' in "Chicago C" -> cubs
                if any(any(t.startswith(i) for t in distinct)
                       for i in initials(kalshi_name)):
                    score += 0.5
                # short-token ACRONYM: the 'WS' in "Chicago WS" -> initials of
                # the team's distinctive words in order (White Sox -> 'ws').
                # Single-letter initials can't see multi-letter forms, and
                # full-token overlap can't either — probed 2026-08-18.
                distinct_ordered = [w for w in norm_token_list(team_name)
                                    if w not in shared]
                acronym = "".join(w[0] for w in distinct_ordered)
                if acronym and any(t == acronym for t in tokens(kalshi_name)
                                   if 2 <= len(t) <= 3):
                    score += 0.5
                return score

            hs = _side_score_distinct(yes_team, best_g.home_team.name, h_tok)
            as_ = _side_score_distinct(yes_team, best_g.away_team.name, a_tok)
            if hs == as_:
                unmatched += 1
                ambiguous += 1
                continue
            side = "HOME" if hs > as_ else "AWAY"

            key = (best_g.id, side)
            if key in matched_rows:
                # doubleheader leftovers / duplicate markets — keep first, count
                unmatched += 1
                continue
            matched_rows[key] = round(prob, 4)
            matched += 1

        for (match_id, side), prob in matched_rows.items():
            sess.add(OddsSnapshot(
                match_id=match_id, market="ML", selection=side,
                devig_prob=prob, line=None, n_books=1,
                captured_at=now, source="kalshi",
            ))
            stored += 1

    return {"ok": True, "series": _series_label,
            "markets": len(all_markets), "matched": matched,
            "unmatched": unmatched, "ambiguous": ambiguous,
            "in_play": in_play, "stored": stored}


def sync_kalshi_soccer(competition_code: str = "PL", date_from=None, date_to=None,
                       max_spread: float = 0.10, progress=None) -> dict:
    """
    Pull open Kalshi soccer game markets (3 legs per game: Home / Away / Tie)
    and store pre-game implied probs as OddsSnapshot(source="kalshi",
    market="1X2", selection HOME/AWAY/DRAW).

    Inherits every hard-won MLB gate, plus one soccer-specific requirement:

      * TIME gate — occurrence_datetime within a few hours of kickoff
      * IN-PLAY gate — prices captured after kickoff are refused (soccer
        markets stay open during play; weekend clusters make this constant)
      * BOTH-TEAMS gate — both title teams must fit the same fixture
        (full club names per the 2026-08-17 recon; alias-map fallback)
      * SPREAD GUARD (new) — far-out legs quote e.g. 0.03/0.81; a midpoint of
        that is noise, not a price. Legs with ask−bid > max_spread are
        skipped and counted, never stored. MLB never needed this (1-2c
        spreads); days-ahead weekend syncs do.
      * ambiguity REFUSED; one price per (match, selection) per run

    Per the 2026-08-17 Step-1 verdict: this is a COVERAGE source and plain
    instrumentation — no disagreement machinery beyond the export columns.
    """
    from src.ingestion.team_aliases import norm_tokens

    def report(m):
        if progress:
            progress(m)

    adapter = KalshiAdapter()
    report("Checking Kalshi status…")
    st = adapter.status()
    if not st.get("trading_active", False):
        report("Note: Kalshi trading not currently active (prices may be stale).")

    series = adapter.SOCCER_GAME_SERIES.get(competition_code)
    if not series:
        return {"ok": False, "reason": f"no Kalshi series mapped for {competition_code}"}
    report(f"  fetching game series {series}…")
    try:
        all_markets = adapter.open_markets_for_series(series)
    except Exception as e:
        return {"ok": False, "reason": f"market fetch failed: {e}"}
    if not all_markets:
        return {"ok": False, "reason": f"no open markets in {series}"}
    report(f"  {len(all_markets)} open game markets")

    now = datetime.utcnow()
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=7))   # weekend cadence: cover the matchweek

    matched = unmatched = ambiguous = in_play = wide_spread = stored = 0

    with session_scope() as sess:
        comp = sess.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return {"ok": False, "reason": f"competition {competition_code} not in DB"}
        games = [g for g in sess.execute(
            select(Match).where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.SCHEDULED,
                Match.utc_date >= lo, Match.utc_date <= hi)
        ).scalars() if g.utc_date]
        report(f"  {len(games)} scheduled {competition_code} games in window")

        def side_score(kalshi_name, team_name):
            return float(len(norm_tokens(kalshi_name) & norm_tokens(team_name)))

        MAX_START_DRIFT = timedelta(hours=5)
        matched_rows: dict[tuple[int, str], float] = {}

        # 2026-09-13: Kalshi changed market titles from "A vs B Winner?" to
        # single-side "A wins" — title_teams() returned None for every
        # market and the matcher went dark (matched 0 across two
        # matchweeks, masked by MW3's listing gap). Structural fix: a
        # game's three legs share an event_ticker, and the two non-Tie
        # legs' yes_sub_titles ARE the full club names. Derive the pairing
        # from sibling legs; keep the old title parse as fallback.
        event_teams: dict[str, list[str]] = {}
        for _mk in all_markets:
            et = _mk.get("event_ticker") or ""
            if not et:
                continue
            if not adapter.is_tie_market(_mk):
                nm = (_mk.get("yes_sub_title") or "").strip()
                if nm and nm not in event_teams.setdefault(et, []):
                    event_teams[et].append(nm)

        for mk in all_markets:
            prob = KalshiAdapter.implied_prob(mk)
            if prob is None:
                continue
            spread = adapter.spread_dollars(mk)
            if spread is not None and spread > max_spread:
                wide_spread += 1
                continue
            occ = KalshiAdapter.occurrence(mk)
            if occ is not None and occ <= now:
                in_play += 1
                continue
            candidates = games
            if occ is not None:
                candidates = [g for g in games
                              if abs(g.utc_date - occ) <= MAX_START_DRIFT]
            if not candidates:
                unmatched += 1
                continue

            _sibs = event_teams.get(mk.get("event_ticker") or "", [])
            tt = tuple(_sibs) if len(_sibs) == 2 else KalshiAdapter.title_teams(mk)
            best_g, best_score, tie = None, 0.0, False
            for g in candidates:
                if not (g.home_team and g.away_team):
                    continue
                if tt:
                    a, b = tt
                    s1 = max(side_score(a, g.home_team.name), side_score(a, g.away_team.name))
                    s2 = max(side_score(b, g.home_team.name), side_score(b, g.away_team.name))
                    if s1 < 1 or s2 < 1:
                        continue
                    score = s1 + s2
                else:
                    continue
                if score > best_score:
                    best_score, best_g, tie = score, g, False
                elif score == best_score and best_g is not None and g.id != best_g.id:
                    tie = True
            if best_g is None or tie:
                unmatched += 1
                if tie:
                    ambiguous += 1
                continue

            # which leg? Tie market -> DRAW; else side by yes team name
            if adapter.is_tie_market(mk):
                sel = "DRAW"
            else:
                yes_team = KalshiAdapter.yes_team(mk)
                hs = side_score(yes_team, best_g.home_team.name)
                as_ = side_score(yes_team, best_g.away_team.name)
                if hs == as_:
                    unmatched += 1
                    ambiguous += 1
                    continue
                sel = "HOME" if hs > as_ else "AWAY"

            # 2026-09-14 derby incident: Kalshi occurrence is a CLOSE time,
            # not kickoff — gate on OUR kickoff too, so in-play prices never
            # enter the snapshot table again.
            if best_g.utc_date <= now:
                in_play += 1
                continue
            key = (best_g.id, sel)
            if key in matched_rows:
                unmatched += 1
                continue
            matched_rows[key] = round(prob, 4)
            matched += 1

        for (match_id, sel), prob in matched_rows.items():
            sess.add(OddsSnapshot(
                match_id=match_id, market="1X2", selection=sel,
                devig_prob=prob, line=None, n_books=1,
                captured_at=now, source="kalshi",
            ))
            stored += 1

    # Sentinel (2026-09-14): two matchweeks went dark before anyone noticed —
    # zero matches with BOTH sides present is an alarm, not a statistic.
    if matched == 0 and games and all_markets:
        report("  ⚠ MATCHED ZERO with games AND markets present — matcher may "
               "be broken (see 2026-09-13 title-format incident). Probe the "
               "payload before trusting 'absent'.")
    return {"ok": True, "series": series, "markets": len(all_markets),
            "matched": matched, "unmatched": unmatched, "ambiguous": ambiguous,
            "in_play": in_play, "wide_spread": wide_spread, "stored": stored}
