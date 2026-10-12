"""
THE KALSHI MATCHER: where a market is stored (ARCHITECT 2026-10-10, addendum 37 item 2; released with its day rule
by addendum 44 item 1, 2026-10-12). One placement, used by both paths (sync_kalshi_mlb's shared path and
sync_kalshi_soccer).

Addendum 37 item 2, verbatim: "A Kalshi market is stored on a game only when its event fits that game: the event's two
team names, taken from the event's own markets, fit the game's two teams, one each. One name alone never places a
market. Names decide before time: the fit is judged among the stored games of the series' own competition on the
event's day, and when the best fit is shared by games of two different pairs of teams the market is refused. The time
gate and the run's window then choose only among games of that one pair, and exactly one must pass. A worse-fitting
game never takes a market because the best one was outside the window or the gate. Two markets that claim the same
side of the same game in one run are both refused. Every refusal is counted by its reason."

Addendum 44 item 1, the day rule, verbatim: "The event's day is the date in its ticker, read as a US Eastern day. A
game is on the event's day when its stored kickoff, read in US Eastern, falls on that date or a day either side. On a
series whose ticker carries no clock time that is the whole time gate: occurrence_datetime is an expected expiration,
and there it places nothing and refuses nothing. Inside the one pair, a game on the ticker's own date takes the market
before a game a day off; where the date cannot separate two games of the pair, the event's markets are refused. Where
the ticker carries a clock time, the time gate stays as built, inside the one pair." Two stored rows of one pair on the
ticker's own date (a placeholder and a second row) refuse the event under a reason of their own, naming the rows
dedupe-matches has to merge.

Pure: no network, no database. place() takes the markets and the stored games (objects with id, utc_date (naive
UTC), home_team.name, away_team.name, status) and returns the placements and the refusals by reason.

Addendum 50 item 6(c), verbatim: "A row whose status is cancelled, postponed or stale orphan is not a game for the
matcher: it takes no market and is not counted among the rows of a pair." A row that has started or finished stays a
game: its markets are refused as in play, the true reason.

Addendum 50 item 6(b): main takes this module, its tests and a read-only replay (src/ingestion/kalshi_replay.py,
`cli.py kalshi-replay`) first and by itself; the two sync paths stay as they are until the switch PR, called on the
replay's console.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
# the date stamp right after the series prefix: -26OCT10 (date only) or -26OCT012000 (date + ET clock time)
_STAMP = re.compile(r"-(\d{2})(" + "|".join(_MONTHS) + r")(\d{2})(\d{4})?(?=[A-Z])")
MAX_START_DRIFT = timedelta(hours=5)     # the time gate as built: occurrence vs our kickoff
MAX_TICK_DRIFT = timedelta(hours=2)      # the time gate as built: the ticker's ET clock time vs our kickoff

# Refusal reasons (each counted; the console prints the counts by reason).
NOT_GAMES = frozenset({"cancelled", "postponed", "stale_orphan"})   # addendum 50 6(c): rows that are not games

NO_PRICE = "no price"
NO_DATE = "no date in the ticker"
NO_PAIR = "the event's markets do not name two teams"
NO_FIT = "no game of the competition on the event's day fits both names"
PAIR_TIE = "best fit shared by two pairs of teams"
TWO_ROWS = "two stored rows of the pair on the ticker's date"
DATE_TIE = "the date cannot separate two games of the pair"
TIME_GATE = "the time gate passes no game of the pair"
TIME_TIE = "the time gate passes two games of the pair"
OUTSIDE_WINDOW = "the pair's game is outside the run's window"
SIDE_TIE = "the names cannot tell home from away"
YES_UNKNOWN = "the market's yes team is neither of the event's names"
IN_PLAY = "in play (our kickoff has passed)"
WIDE_SPREAD = "spread wider than the guard"
TWO_CLAIMS = "two markets claim one side of one game"


def norm_tokens(name: str) -> set[str]:
    """The shared alias tokens, with "St." read as State (addendum 37 item 2: names before time, "St." = State).
    Applied to both sides, so it only ever adds a fit: 'Alabama St.' and 'Alabama State' share {alabama, state}."""
    from src.ingestion.team_aliases import norm_tokens as _base
    return {"state" if t == "st" else t for t in _base(name)}


def _initials(name: str) -> set[str]:
    return {w.lower() for w in (name or "").split() if len(w) == 1 and w.isalpha()}


def side_score(kalshi_name: str, team_name: str) -> float:
    """Word overlap, with an initial-letter tiebreak worth half a point ("Chicago C" -> Cubs)."""
    ttok = norm_tokens(team_name)
    score = float(len(norm_tokens(kalshi_name) & ttok))
    if any(any(t.startswith(i) for t in ttok) for i in _initials(kalshi_name)):
        score += 0.5
    return score


def _distinct_score(kalshi_name: str, team_name: str, shared: set[str]) -> float:
    """Against the team's distinctive tokens only (two-team cities share the city token), plus the short-acronym
    form ('WS' -> White Sox). The side tiebreak of the shared path, kept."""
    from src.ingestion.team_aliases import norm_token_list
    distinct = norm_tokens(team_name) - shared
    score = float(len(norm_tokens(kalshi_name) & distinct))
    if any(any(t.startswith(i) for t in distinct) for i in _initials(kalshi_name)):
        score += 0.5
    ordered = [("state" if w == "st" else w) for w in norm_token_list(team_name)]
    acronym = "".join(w[0] for w in ordered if w not in shared)
    if acronym and any(t == acronym for t in norm_tokens(kalshi_name) if 2 <= len(t) <= 3):
        score += 0.5
    return score


def fit(names: tuple[str, str], home: str, away: str) -> tuple[float, str | None] | None:
    """The event's two names against a game, one each: home with one name and away with the other, each scoring at
    least 1; the score is the better of the two ways. Returns (score, which name is home) or None (no fit). Which
    name is home is None when the two ways tie on the plain and on the distinctive scores alike."""
    a, b = names
    way1 = (side_score(a, home), side_score(b, away))      # a home, b away
    way2 = (side_score(b, home), side_score(a, away))      # b home, a away
    ok1, ok2 = min(way1) >= 1, min(way2) >= 1
    if not (ok1 or ok2):
        return None
    s1, s2 = (sum(way1) if ok1 else -1.0), (sum(way2) if ok2 else -1.0)
    if s1 != s2:
        return max(s1, s2), (a if s1 > s2 else b)
    shared = norm_tokens(home) & norm_tokens(away)
    d1 = _distinct_score(a, home, shared) + _distinct_score(b, away, shared)
    d2 = _distinct_score(b, home, shared) + _distinct_score(a, away, shared)
    if d1 == d2:
        return s1, None
    return s1, (a if d1 > d2 else b)


def event_of(market: dict) -> str:
    et = market.get("event_ticker")
    if et:
        return et
    t = market.get("ticker") or ""
    return t.rsplit("-", 1)[0] if "-" in t else t


def ticker_stamp(market: dict) -> tuple[date | None, datetime | None]:
    """(the ticker's date, the ticker's clock time as naive UTC or None). The date is read as a US Eastern day; the
    clock time, where the series writes one, is US Eastern (M13, 2026-08-25). Unparseable -> (None, None)."""
    m = _STAMP.search((event_of(market) or "") + "X") or _STAMP.search(market.get("ticker") or "")
    if not m:
        return None, None
    try:
        d = date(2000 + int(m.group(1)), _MONTHS.index(m.group(2)) + 1, int(m.group(3)))
    except ValueError:
        return None, None
    clock = None
    if m.group(4):
        hh, mm = int(m.group(4)[:2]), int(m.group(4)[2:])
        try:
            clock = (datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).astimezone(UTC).replace(tzinfo=None))
        except ValueError:
            return d, None
    return d, clock


def et_day(utc_naive: datetime) -> date:
    return utc_naive.replace(tzinfo=UTC).astimezone(ET).date()


def et_text(utc_naive: datetime | None) -> str:
    return "—" if utc_naive is None else utc_naive.replace(tzinfo=UTC).astimezone(ET).strftime("%Y-%m-%d %H:%M ET")


def is_game(g) -> bool:
    """Addendum 50 6(c): a cancelled, postponed or stale-orphan row is not a game for the matcher."""
    st = getattr(g, "status", None)
    return str(getattr(st, "value", st) or "").lower() not in NOT_GAMES


def occurrence(market: dict) -> datetime | None:
    from src.adapters.kalshi import KalshiAdapter
    return KalshiAdapter.occurrence(market)


@dataclass
class Result:
    placed: dict = field(default_factory=dict)        # (match_id, side) -> market
    refused: Counter = field(default_factory=Counter)  # reason -> markets refused for it
    lines: list = field(default_factory=list)          # console lines (time-gate and date refusals, two rows)
    matched_events: int = 0
    why: dict = field(default_factory=dict)            # market ticker -> the reason it was refused

    @property
    def in_play(self) -> int:
        return self.refused.get(IN_PLAY, 0)


def place(markets: list[dict], games: list, *, now: datetime, lo: datetime, hi: datetime,
          is_tie=None, implied_prob=None, spread=None, max_spread: float | None = None) -> Result:
    """Place the markets on the games. `games`: the stored games of the series' own competition (any window: the day
    rule picks the event's day; the run's window [lo, hi] is applied only inside the one pair). `is_tie(market)`
    marks a draw leg (soccer: placed as DRAW on the event's game). `implied_prob(market)` -> price or None (no price:
    refused). `spread(market)` with `max_spread`: the soccer spread guard."""
    from src.adapters.kalshi import KalshiAdapter
    is_tie = is_tie or (lambda m: False)
    implied_prob = implied_prob or KalshiAdapter.implied_prob
    res = Result()
    by_event: dict[str, list[dict]] = {}
    for mk in markets:
        by_event.setdefault(event_of(mk), []).append(mk)
    claims: dict[tuple[int, str], list[dict]] = {}

    def refuse(mks, reason, n=None):
        res.refused[reason] += len(mks) if n is None else n
        for mk in mks:
            res.why[mk.get("ticker")] = reason

    for ev, mks in by_event.items():
        live = []
        for mk in mks:
            if implied_prob(mk) is None:
                refuse([mk], NO_PRICE)
            elif max_spread is not None and spread is not None and (spread(mk) or 0) > max_spread:
                refuse([mk], WIDE_SPREAD)
            else:
                live.append(mk)
        if not live:
            continue
        # the event's two names, from the event's own markets (siblings: one name each); the old "A vs B" title is
        # the fallback for an old-format title. The yes team alone never places a market.
        names = []
        for mk in mks:
            if not is_tie(mk):
                nm = (mk.get("yes_sub_title") or "").strip()
                if nm and nm not in names:
                    names.append(nm)
        if len(names) != 2:
            tt = KalshiAdapter.title_teams(live[0])
            names = list(tt) if tt else names
        if len(names) != 2:
            refuse(live, NO_PAIR)
            continue
        day, clock = ticker_stamp(live[0])
        if day is None:
            refuse(live, NO_DATE)
            continue
        on_day = [g for g in games if g.utc_date and g.home_team and g.away_team and is_game(g)
                  and abs((et_day(g.utc_date) - day).days) <= 1]
        # names before time: the best fit among the competition's games on the event's day
        fits = []
        for g in on_day:
            f = fit((names[0], names[1]), g.home_team.name, g.away_team.name)
            if f is not None:
                fits.append((f[0], g, f[1]))
        if not fits:
            refuse(live, NO_FIT)
            continue
        best = max(s for s, _, _ in fits)
        top = [(g, home_name) for s, g, home_name in fits if s == best]
        pairs = {frozenset((g.home_team_id, g.away_team_id)) for g, _ in top}
        if len(pairs) > 1:
            refuse(live, PAIR_TIE)
            continue
        pair_games = sorted(top, key=lambda x: x[0].utc_date)
        # inside the one pair: the day rule (date-only tickers) or the time gate as built (clock tickers)
        if clock is None:
            own = [x for x in pair_games if et_day(x[0].utc_date) == day]
            if len(own) > 1:
                refuse(live, TWO_ROWS)
                res.lines.append(f"  ✗ {ev}: {len(own)} stored rows of one pair on {day} (ids "
                                 f"{', '.join(str(g.id) for g, _ in own)}): refused; dedupe-matches has to merge "
                                 f"them")
                continue
            chosen = own or pair_games
            if len(chosen) != 1:
                refuse(live, DATE_TIE)
                res.lines.append(f"  ✗ {ev}: ticker date {day}; our kickoffs "
                                 f"{'; '.join(f'{g.id} {et_text(g.utc_date)}' for g, _ in chosen)}: the date "
                                 f"cannot separate them, refused")
                continue
        else:
            # as built (M13, 2026-08-25): a game near either anchor, occurrence (5h) or the ticker's ET clock
            # time (2h); with no occurrence the clock filter applies only when it finds a game
            occ = occurrence(live[0])
            near_tick = [x for x in pair_games if abs(x[0].utc_date - clock) <= MAX_TICK_DRIFT]
            if occ is not None:
                chosen = [x for x in pair_games if x in near_tick or abs(x[0].utc_date - occ) <= MAX_START_DRIFT]
            else:
                chosen = near_tick or pair_games
            if len(chosen) > 1:                 # doubleheader: the event's G1/G2 suffix, earlier/later game
                mg = re.search(r"G(\d)$", ev or "") or re.search(r"G(\d)-", live[0].get("ticker") or "")
                if mg and 1 <= int(mg.group(1)) <= len(chosen):
                    chosen = [chosen[int(mg.group(1)) - 1]]
            if not chosen:
                refuse(live, TIME_GATE)
                res.lines.append(f"  ✗ {ev}: time gate: Kalshi {et_text(clock)} (occurrence {et_text(occ)}); ours "
                                 f"{'; '.join(f'{g.id} {et_text(g.utc_date)}' for g, _ in pair_games)}")
                continue
            if len(chosen) != 1:
                refuse(live, TIME_TIE)
                continue
        g, home_name = chosen[0]
        if not (lo <= g.utc_date <= hi):
            refuse(live, OUTSIDE_WINDOW)
            continue
        if home_name is None:
            refuse(live, SIDE_TIE)
            continue
        res.matched_events += 1
        for mk in live:
            if is_tie(mk):
                side = "DRAW"
            else:
                yes = (mk.get("yes_sub_title") or "").strip()
                if yes not in names:
                    refuse([mk], YES_UNKNOWN)
                    continue
                side = "HOME" if yes == home_name else "AWAY"
            if g.utc_date <= now:               # in play on OUR clock, never assumed pre-game
                refuse([mk], IN_PLAY)
                continue
            claims.setdefault((g.id, side), []).append(mk)
    for key, mks in claims.items():
        if len(mks) > 1:
            refuse(mks, TWO_CLAIMS)
        else:
            res.placed[key] = mks[0]
    return res


def legacy_counts(res: Result) -> dict:
    """The summary keys the consoles print today (matched / unmatched / ambiguous / in_play), from the reasons."""
    amb = sum(res.refused.get(r, 0) for r in (PAIR_TIE, TWO_ROWS, DATE_TIE, TIME_TIE, SIDE_TIE, TWO_CLAIMS))
    unmatched = sum(n for r, n in res.refused.items() if r not in (IN_PLAY, WIDE_SPREAD, NO_PRICE))
    return {"matched": len(res.placed), "unmatched": unmatched, "ambiguous": amb,
            "in_play": res.refused.get(IN_PLAY, 0), "refused": dict(res.refused)}


def day_span(markets: list[dict]) -> tuple[datetime, datetime] | None:
    """The UTC span that holds every game on any event's day (the ticker dates, a day either side, read in US
    Eastern), with margin: the games place() needs loaded. None when no ticker carries a date."""
    days = {ticker_stamp(mk)[0] for mk in markets} - {None}
    if not days:
        return None
    return (datetime.combine(min(days), datetime.min.time()) - timedelta(days=2),
            datetime.combine(max(days), datetime.min.time()) + timedelta(days=3))


def console_lines(res: Result) -> list[str]:
    """Every refusal counted by its reason, then the lines naming the refused events."""
    if not res.refused:
        return ["  refused: none"]
    out = ["  refused, by reason:"] + [f"    {n:>4}  {r}" for r, n in sorted(res.refused.items(), key=lambda x: (-x[1], x[0]))]
    return out + res.lines
