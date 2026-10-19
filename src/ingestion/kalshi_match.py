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
dedupe-matches has to merge; where the ticker carries the game number (G1, G2) and the rows are at different minutes,
"two games of the pair that day; the G1/G2 suffix is not read (#478)" (ARCHITECT 2026-10-19, addendum 136 item 3:
no merge is suggested for a doubleheader). On a clock ticker with no game number (addendum 52 item 4, below) the line says instead
"two games of the pair that day; the clock does not separate them" (ARCHITECT 2026-10-17, addendum 104 item 2: a real
doubleheader, two rows hours apart, is two games); rows at one kickoff minute keep the dedupe words (one game stored
twice, addendum 105, #569), named in the same line when both hold.

Addendum 52 item 4 (2026-10-12), replacing the day rule's last sentence above: "Where the ticker carries a clock time
and no game number, the event's game is the one game of the pair whose stored kickoff, read in US Eastern, falls on
the ticker's own date. Nothing else is read there: not the clock, not occurrence_datetime, not a day either side."
An event with a game number (G1, G2) is admitted by its clock alone (addendum 51 item 3, lane #472).
occurrence_datetime places nothing and refuses nothing on any series.

Addendum 54 item 6 (2026-10-12, finding #476: a postponement inside a series put the next game's market on the
postponed game's row), beside addendum 52 item 4, which stands, verbatim: "On a series whose ticker carries a clock
time, the events of the same two names are read together. An event with no game number is out of step when no game of
its two teams is on its date, or when its date is before the day of the run. Dates are read in US Eastern, and a row
that is not a game is not one here. No event of the same two names dated after an event out of step is placed in that
run, with or without a game number: it is refused under a reason of its own, and its line names the earliest event out
of step and says why that one is. Events dated before the earliest one are placed as ruled." An event out of step is
refused already, under its own reason; it counts whether or not its markets carry a price. A date-only series is
outside the rule. Addendum 55 item 3: "The reason 'behind' and its line are for a market that would otherwise have
been placed. A market refused for a reason of its own keeps that reason, and no such line is printed for it."

Addendum 57 item 6 (2026-10-13, lane #479), the matcher's pins, verbatim: "In the Kalshi matcher, Penn is
Pennsylvania; University at Albany is UAlbany; LIU is Long Island University; PSG is Paris Saint Germain; Stade
Rennais is Rennes; M´gladbach, as Kalshi writes it with an acute accent (U+00B4), is Borussia Mönchengladbach. A pin
reads one of the event's two names whole, as the module takes them, and never a word of a name: Penn St. is not Penn.
Nothing else in the matcher changes: the event's two names still fit one game one each, and a tie is refused."
Addendum 59 item 2 (2026-10-13, #484), verbatim: "A pin names one stored team. A pinned name fits a team only where
the team's stored name reads as the pin's name: the same words under norm_tokens, no more and no fewer. Against every
other team a pinned name scores nothing, whatever word they share: PSG does not fit Paris FC, M´gladbach does not
fit Borussia Dortmund, LIU does not fit Rhode Island. Against its own team it scores what the pin's name scores on
#482's head. An event's name that is not pinned is read as before. One each, the best fit and the refused tie do not
change."
Addendum 66 item 4 (2026-10-14), verbatim: "the Kalshi name "Fenerbahce" pins to the stored club "Fenerbahçe"." The
pin's name is written as the club is stored, ç as U+00E7: norm_tokens folds no accent, so "Fenerbahce" alone shares
no word with it (the wide probe's refusal of KXUCLGAME-26OCT14AVLFEN and -26OCT20FENSLA for no fit).

Pure: no network, no database. place() takes the markets and the stored games (objects with id, utc_date (naive
UTC), home_team.name, away_team.name, status) and returns the placements and the refusals by reason.

Addendum 50 item 6(c), verbatim: "A row whose status is cancelled, postponed or stale orphan is not a game for the
matcher: it takes no market and is not counted among the rows of a pair." A row that has started or finished stays a
game: its markets are refused as in play, the true reason.

Addendum 50 item 6(b): main took this module, its tests and a read-only replay (src/ingestion/kalshi_replay.py,
`cli.py kalshi-replay`) first and by itself. The switch PR, called on the replay's console, puts both sync paths on
it (src/ingestion/kalshi_sync.py).
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
MAX_TICK_DRIFT = timedelta(hours=2)      # a numbered event's gate; elsewhere the threshold of the clock line

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
NO_GAME_ON_DATE = "no game of the pair on the ticker's date"
TIME_TIE = "the time gate passes two games of the pair"
OUTSIDE_WINDOW = "the pair's game is outside the run's window"
SIDE_TIE = "the names cannot tell home from away"
YES_UNKNOWN = "the market's yes team is neither of the event's names"
IN_PLAY = "in play (our kickoff has passed)"
WIDE_SPREAD = "spread wider than the guard"
TWO_CLAIMS = "two markets claim one side of one game"
BEHIND = "behind an event of the same two names out of step"


# Addendum 57 item 6: an event's name, whole as the module takes it (the market's yes_sub_title, stripped), -> the
# one stored team it names. Never a word of a name ("Penn St." is not "Penn"). Addendum 59 item 2: the pinned name
# fits that team alone (_as_scored).
PINS = {
    "Penn": "Pennsylvania",
    "University at Albany": "UAlbany",
    "LIU": "Long Island University",
    "PSG": "Paris Saint Germain",
    "Stade Rennais": "Rennes",
    "M\u00b4gladbach": "Borussia M\u00f6nchengladbach",
    "Fenerbahce": "Fenerbah\u00e7e",           # addendum 66 item 4; ç is U+00E7, as the club is stored
}


def norm_tokens(name: str) -> set[str]:
    """The shared alias tokens, with "St." read as State (addendum 37 item 2: names before time, "St." = State).
    Applied to both sides, so it only ever adds a fit: 'Alabama St.' and 'Alabama State' share {alabama, state}."""
    from src.ingestion.team_aliases import norm_tokens as _base
    return {"state" if t == "st" else t for t in _base(name)}


def _initials(name: str) -> set[str]:
    return {w.lower() for w in (name or "").split() if len(w) == 1 and w.isalpha()}


def _as_scored(kalshi_name: str, team_name: str) -> str | None:
    """The name scored against `team_name`. An unpinned name is itself, read as before. A pinned name is its pin's
    name against its own team, the one whose stored name has the same words as the pin's name under norm_tokens, no
    more and no fewer, and None (it scores nothing) against every other team, whatever word they share (addendum 59
    item 2)."""
    pin = PINS.get(kalshi_name)
    if pin is None:
        return kalshi_name
    return pin if norm_tokens(team_name) == norm_tokens(pin) else None


def side_score(kalshi_name: str, team_name: str) -> float:
    """Word overlap, with an initial-letter tiebreak worth half a point ("Chicago C" -> Cubs). A pinned name scores
    as its pin's name against its own team and 0 against any other (_as_scored)."""
    kalshi_name = _as_scored(kalshi_name, team_name)
    if kalshi_name is None:
        return 0.0
    ttok = norm_tokens(team_name)
    score = float(len(norm_tokens(kalshi_name) & ttok))
    if any(any(t.startswith(i) for t in ttok) for i in _initials(kalshi_name)):
        score += 0.5
    return score


def _distinct_score(kalshi_name: str, team_name: str, shared: set[str]) -> float:
    """Against the team's distinctive tokens only (two-team cities share the city token), plus the short-acronym
    form ('WS' -> White Sox). The side tiebreak of the shared path, kept. A pinned name as in side_score."""
    from src.ingestion.team_aliases import norm_token_list
    kalshi_name = _as_scored(kalshi_name, team_name)
    if kalshi_name is None:
        return 0.0
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
            return None, None           # a clock field that is no time: unparseable, refused (Codex on #461)
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
    lines: list = field(default_factory=list)          # console lines (gate and date refusals, two rows, a far clock)
    matched_events: int = 0
    why: dict = field(default_factory=dict)            # market ticker -> the reason it was refused

    @property
    def in_play(self) -> int:
        return self.refused.get(IN_PLAY, 0)


def _live(mks, implied_prob, spread, max_spread) -> list[dict]:
    """The event's markets with a price, inside the spread guard where one is set."""
    return [mk for mk in mks if implied_prob(mk) is not None
            and not (max_spread is not None and spread is not None and (spread(mk) or 0) > max_spread)]


def _names(mks, first, is_tie) -> list[str]:
    """The event's two names, from the event's own markets (siblings: one name each); the old "A vs B" title of
    `first` is the fallback for an old-format title. The yes team alone never places a market."""
    from src.adapters.kalshi import KalshiAdapter
    names = []
    for mk in mks:
        if not is_tie(mk):
            nm = (mk.get("yes_sub_title") or "").strip()
            if nm and nm not in names:
                names.append(nm)
    if len(names) != 2:
        tt = KalshiAdapter.title_teams(first)
        names = list(tt) if tt else names
    return names


def _best_fits(names, day, games) -> list:
    """Names before time: [(game, which name is home)] of the best fit among the competition's games on the event's
    day (the ticker's date, a day either side, US Eastern; rows that are not games left out). [] when none fits."""
    on_day = [g for g in games if g.utc_date and g.home_team and g.away_team and is_game(g)
              and abs((et_day(g.utc_date) - day).days) <= 1]
    # the pins (addendum 57 item 6, addendum 59 item 2): each name read whole by the scoring, a pinned one against its
    # own team only
    fits = []
    for g in on_day:
        f = fit((names[0], names[1]), g.home_team.name, g.away_team.name)
        if f is not None:
            fits.append((f[0], g, f[1]))
    if not fits:
        return []
    best = max(sc for sc, _, _ in fits)
    return [(g, home_name) for sc, g, home_name in fits if sc == best]


def _game_number(ev, market):
    """The event's game number (G1, G2), read as place() reads it."""
    return re.search(r"G(\d)$", ev or "") or re.search(r"G(\d)-", market.get("ticker") or "")


def behind_out_of_step(by_event: dict, games: list, *, now: datetime, is_tie, implied_prob, spread=None,
                       max_spread=None) -> dict:
    """Addendum 54 item 6: {event: its console line} for every clock-series event behind an event of the same two
    names out of step; place() refuses its markets as behind only where they would otherwise take their place on a
    game (addendum 55 item 3). Out of step (an event with no game number): no game of its two teams on its date (the
    pair place() would choose, the best fit on the event's day; no fit at all is no game), or its date before the
    day of the run (US Eastern). Every market of an event is read, priced or not. The names are the group: an event
    out of step may fit no stored game."""
    run_day = et_day(now)
    heads, out = [], {}
    for ev, mks in by_event.items():
        live = _live(mks, implied_prob, spread, max_spread)
        first = live[0] if live else mks[0]
        names = _names(mks, first, is_tie)
        day, clock = ticker_stamp(first)
        if len(names) != 2 or day is None or clock is None:      # a date-only series is outside the rule
            continue
        key = frozenset(n.lower() for n in names)
        heads.append((key, day, ev))
        if _game_number(ev, first):
            continue                                            # a numbered event is never out of step itself
        why = []
        if not any(et_day(g.utc_date) == day for g, _ in _best_fits(names, day, games)):
            why.append(f"no game of its two teams on its date {day}")
        if day < run_day:
            why.append(f"its date {day} is before the day of the run {run_day}")
        if why:
            out.setdefault(key, []).append((day, ev, why))
    lines = {}
    for key, day, ev in heads:
        if key not in out:
            continue
        d0, ev0, why0 = min(out[key], key=lambda x: (x[0], x[1]))       # the earliest event out of step
        if day > d0:
            lines[ev] = f"  ✗ {ev}: refused behind {ev0}, out of step: {' and '.join(why0)}"
    return lines


def _clock_rows_what(own, doubleheader="two games of the pair that day; the clock does not separate them") -> str:
    """The two-rows line's words on a clock ticker with no game number. ARCHITECT 2026-10-17, addendum 104 item 2: for
    a real doubleheader (two rows hours apart) it says "two games of the pair that day; the clock does not separate
    them", not dedupe. Rows at one kickoff minute are one game stored twice (addendum 105, #569), so they keep the
    dedupe words; where both hold, the line names each. `doubleheader`: the words for rows at different minutes
    (_date_rows_what's, on a date-only ticker with a game number)."""
    by_minute: dict = {}
    for g, _ in own:
        by_minute.setdefault(g.utc_date.replace(second=0, microsecond=0), []).append(g.id)
    twins = [ids for ids in by_minute.values() if len(ids) > 1]
    if not twins:
        return doubleheader
    dup = "; ".join(f"rows {', '.join(str(i) for i in ids)} share one kickoff minute: dedupe-matches has to merge them"
                    for ids in twins)
    return dup if len(by_minute) == 1 else f"{doubleheader}; {dup}"


def _date_rows_what(own, ev: str | None, ticker: str | None) -> str:
    """The two-rows line's words on a date-only ticker. ARCHITECT 2026-10-19, addendum 136 item 3: the suffix
    "dedupe-matches has to merge them" was printed on true doubleheaders (`KXMLBGAME-25JUL26CLEKCG2: 2 stored rows of
    one pair on 2025-07-26 (ids 8242, 8243)`, kickoffs 14:40 and 19:15 ET); "The suffix belongs ONLY where rows share
    a kickoff minute [...] A doubleheader reads "two games of the pair that day; the G1/G2 suffix is not read (#478)"
    and no merge is suggested." Read for a ticker that carries the game number (G1, G2: a doubleheader by the
    ticker's own word); a date-only ticker with none keeps the dedupe words, as built (a placeholder row beside the
    real one at another minute is one game stored twice, e.g. a college placeholder: no college doubleheader exists)."""
    if not (re.search(r"G\d$", ev or "") or re.search(r"G\d-", ticker or "")):
        return "dedupe-matches has to merge them"
    return _clock_rows_what(own, "two games of the pair that day; the G1/G2 suffix is not read (#478)")


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
    behind = behind_out_of_step(by_event, games, now=now, is_tie=is_tie, implied_prob=implied_prob, spread=spread,
                                max_spread=max_spread)

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
        names = _names(mks, live[0], is_tie)
        if len(names) != 2:
            refuse(live, NO_PAIR)
            continue
        day, clock = ticker_stamp(live[0])
        if day is None:
            refuse(live, NO_DATE)
            continue
        top = _best_fits(names, day, games)
        if not top:
            refuse(live, NO_FIT)
            continue
        pairs = {frozenset((g.home_team_id, g.away_team_id)) for g, _ in top}
        if len(pairs) > 1:
            refuse(live, PAIR_TIE)
            continue
        pair_games = sorted(top, key=lambda x: x[0].utc_date)

        def two_rows(own, what="dedupe-matches has to merge them"):
            refuse(live, TWO_ROWS)
            res.lines.append(f"  ✗ {ev}: {len(own)} stored rows of one pair on {day} (ids "
                             f"{', '.join(str(g.id) for g, _ in own)}): refused; {what}")
        # Inside the one pair the gate chooses first (addendum 51 item 4, as addendum 52 item 4 reads it): "the day
        # rule on a date-only ticker; on a clock ticker the ticker's own date, or the clock where the event carries a
        # game number."
        if clock is None:
            own = [x for x in pair_games if et_day(x[0].utc_date) == day]
            if len(own) > 1:
                two_rows(own, _date_rows_what(own, ev, live[0].get("ticker")))
                continue
            chosen = own or pair_games
            if len(chosen) != 1:
                refuse(live, DATE_TIE)
                res.lines.append(f"  ✗ {ev}: ticker date {day}; our kickoffs "
                                 f"{'; '.join(f'{g.id} {et_text(g.utc_date)}' for g, _ in chosen)}: the date "
                                 f"cannot separate them, refused")
                continue
        else:
            occ = occurrence(live[0])           # printed only: it places nothing and refuses nothing (addendum 52)
            mg = re.search(r"G(\d)$", ev or "") or re.search(r"G(\d)-", live[0].get("ticker") or "")
            if mg:
                # Addendum 51 item 3: "an event whose ticker carries a game number (G1, G2) is admitted by that clock
                # alone: a game of the pair passes only when its stored kickoff is within two hours of it. [...] Where
                # two games of the pair pass, G1 takes the earlier and G2 the later, as built." (lane #472)
                chosen = [x for x in pair_games if abs(x[0].utc_date - clock) <= MAX_TICK_DRIFT]
                if len(chosen) > 1 and 1 <= int(mg.group(1)) <= len(chosen):
                    chosen = [chosen[int(mg.group(1)) - 1]]
                if not chosen:
                    refuse(live, TIME_GATE)
                    res.lines.append(f"  ✗ {ev}: time gate: Kalshi {et_text(clock)} (occurrence {et_text(occ)}); "
                                     f"ours {'; '.join(f'{g.id} {et_text(g.utc_date)}' for g, _ in pair_games)}")
                    continue
                if len(chosen) != 1:
                    # addendum 51 item 4: a time-tie refusal prints its line, as the two-row refusal does
                    refuse(live, TIME_TIE)
                    res.lines.append(f"  ✗ {ev}: time gate passes {len(chosen)} games of the pair: Kalshi "
                                     f"{et_text(clock)} (occurrence {et_text(occ)}); passed "
                                     f"{'; '.join(f'{g.id} {et_text(g.utc_date)}' for g, _ in chosen)}: refused")
                    continue
            else:
                # Addendum 52 item 4: "Where the ticker carries a clock time and no game number, the event's game is
                # the one game of the pair whose stored kickoff, read in US Eastern, falls on the ticker's own date.
                # Nothing else is read there: not the clock, not occurrence_datetime, not a day either side. Two
                # games of the pair on that date refuse the event as two rows do on a date-only ticker, naming them.
                # No game of the pair on that date refuses the event under a reason of its own, and its line prints
                # the ticker's date and clock and our kickoffs of the pair in US Eastern. Where the date gives the
                # game and the clock is more than two hours from its kickoff, a line says so with both times,
                # whether or not the market is then placed."
                own = [x for x in pair_games if et_day(x[0].utc_date) == day]
                if len(own) > 1:
                    two_rows(own, _clock_rows_what(own))
                    continue
                if not own:
                    refuse(live, NO_GAME_ON_DATE)
                    res.lines.append(f"  ✗ {ev}: ticker date {day}, clock {et_text(clock)}; no game of the pair on "
                                     f"that date; our kickoffs "
                                     f"{'; '.join(f'{g.id} {et_text(g.utc_date)}' for g, _ in pair_games)}: refused")
                    continue
                chosen = own
                g0 = own[0][0]
                if abs(g0.utc_date - clock) > MAX_TICK_DRIFT:
                    hours = abs(g0.utc_date - clock).total_seconds() / 3600
                    res.lines.append(f"  ! {ev}: Kalshi's clock {et_text(clock)} is {hours:.1f}h from our kickoff "
                                     f"{et_text(g0.utc_date)} (match {g0.id}); the ticker's date gives the game")
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
            if ev in behind:
                # addendum 55 item 3: "The reason 'behind' and its line are for a market that would otherwise have
                # been placed. A market refused for a reason of its own keeps that reason, and no such line is
                # printed for it." So it is read here, where the market would take its place on a game.
                refuse([mk], BEHIND)
                if behind[ev] not in res.lines:
                    res.lines.append(behind[ev])
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
        return ["  refused: none"] + res.lines     # a line a placement carries (a far clock) is printed too
    out = ["  refused, by reason:"] + [f"    {n:>4}  {r}" for r, n in sorted(res.refused.items(), key=lambda x: (-x[1], x[0]))]
    return out + res.lines
