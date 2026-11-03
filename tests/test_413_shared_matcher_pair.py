"""#413, THE SHARED KALSHI MATCHER'S PAIR (ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 0(a)): "the pair comes from
the event's sibling markets as the soccer path does since 09-13; the yes-team fallback goes; a market whose pair cannot
be formed is REFUSED by the sentinel (never placed by one name)".

The placement is kalshi_match.place, the one placement of both sync paths since the switch (#461, #475). These pins
hold it on the shapes #413 and addendum 44 item 2 receipted, on each two-way series' ticker shape, with every market
titled "<Team> wins" as Kalshi writes them (so the old "A vs B" title fallback reads nothing there); the fallback's
own pins, as addendum 234 item 2 narrowed it, are below. Synthetic games and a throwaway DB only (tests/conftest.py)."""
import inspect

import pytest

from src.ingestion import kalshi_match as km
from tests.test_kalshi_matcher_day_rule import (CCAR_MRSH, FAMU_ALST, NDSU_UNLV, SCSTCHSO, UGA_ALA, UGAALA, UND_UNI,
                                                NDSUUNLV, UNDUNI, Z, _a54_comp, _a54_row, _a54_sync, event, game,
                                                placed, run)

# --- one shape per two-way series: two siblings place both sides; one sibling places nothing ---

SERIES_SHAPES = {
    # series: (stamp, (suffix, name) x2, the game (away, home, kickoff), a decoy game sharing the first name's word)
    "KXMLBGAME": ("26OCT011905STLCHC", [("STL", "St. Louis"), ("CHC", "Chicago C")],
                  ("St. Louis Cardinals", "Chicago Cubs", Z("2026-10-01T23:05")),
                  ("Detroit Tigers", "St. Louis Blues Nine", Z("2026-10-01T23:10"))),
    "KXNFLGAME": ("26NOV09KCDEN", [("KC", "Kansas City"), ("DEN", "Denver")],
                  ("Kansas City Chiefs", "Denver Broncos", Z("2026-11-09T18:00")),
                  ("Kansas City Comets", "Las Vegas Raiders", Z("2026-11-09T21:25"))),
    "KXNHLGAME": ("26NOV05BOSNYR", [("BOS", "Boston"), ("NYR", "New York R")],
                  ("Boston Bruins", "New York Rangers", Z("2026-11-06T00:00")),
                  ("Boston Legal", "Philadelphia Flyers", Z("2026-11-06T00:30"))),
    "KXNCAAFGAME": ("26OCT10UGAALA", [("UGA", "Georgia"), ("ALA", "Alabama")],
                    ("Georgia", "Alabama", Z("2026-10-10T23:30")),
                    ("Duke", "Georgia Tech", Z("2026-10-10T16:00"))),
}
NOW = {"KXMLBGAME": Z("2026-10-01T12:00"), "KXNFLGAME": Z("2026-11-09T12:00"), "KXNHLGAME": Z("2026-11-05T12:00"),
       "KXNCAAFGAME": Z("2026-10-10T11:52")}


def _shape(series, gid):
    stamp, legs, (away, home, ko), (d_away, d_home, d_ko) = SERIES_SHAPES[series]
    return (event(stamp, legs, series=series), game(gid, away, home, ko), game(gid + 1, d_away, d_home, d_ko))


@pytest.mark.parametrize("series", sorted(SERIES_SHAPES))
@pytest.mark.parametrize("reverse", [False, True])
def test_a_two_sibling_event_titled_team_wins_is_placed_on_its_game_by_both_names(series, reverse):
    gid = 41000 + 10 * sorted(SERIES_SHAPES).index(series)
    mks, own, decoy = _shape(series, gid)
    from src.adapters.kalshi import KalshiAdapter
    assert all(m["title"].endswith(" wins") for m in mks)
    assert all(KalshiAdapter.title_teams(m) is None for m in mks)          # "<Team> wins": no "A vs B" title
    games = [decoy, own][::-1] if reverse else [decoy, own]
    res = run(mks[::-1] if reverse else mks, games, now=NOW[series])
    sfx_a, sfx_h = mks[0]["ticker"].rsplit("-", 1)[1], mks[1]["ticker"].rsplit("-", 1)[1]
    assert placed(res) == {(gid, "AWAY"): sfx_a, (gid, "HOME"): sfx_h}, (res.refused, res.lines)
    assert not res.refused and res.matched_events == 1


@pytest.mark.parametrize("series", sorted(SERIES_SHAPES))
def test_an_event_with_one_sibling_is_refused_never_placed_by_one_name(series):
    """The yes-team fallback is gone: the one market's yes team fits its own game and the decoy alike by a word, and
    neither takes it. Refused as NO_PAIR, the reason the console prints."""
    gid = 42000 + 10 * sorted(SERIES_SHAPES).index(series)
    mks, own, decoy = _shape(series, gid)
    for one in (mks[:1], mks[1:]):
        res = run(one, [own, decoy], now=NOW[series])
        assert not res.placed and res.refused == {km.NO_PAIR: 1}, (series, res.refused)
        assert res.why == {one[0]["ticker"]: km.NO_PAIR}
        assert "       1  the event's markets do not name two teams" in km.console_lines(res)


@pytest.mark.parametrize("names,why", [
    (["Georgia", "Alabama", "Georgia Tech"], "three names: the siblings conflict"),
    (["Georgia", ""], "a sibling with no name: one name"),
    (["", ""], "no name at all"),
])
def test_a_pair_that_cannot_be_formed_from_the_siblings_is_refused(names, why):
    legs = [(f"S{i}", n) for i, n in enumerate(names)]
    mks = event("26OCT10UGAALA", legs)
    res = run(mks, [UGA_ALA, game(42101, "Duke", "Georgia Tech", Z("2026-10-10T16:00"))], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.NO_PAIR: len(mks)}, (why, res.refused)


# --- the "A vs B" title fallback, NARROWED (ARCHITECT 2026-11-03 13:05 ET, addendum 234 item 2) ---
# Verbatim: "THE "A vs B" TITLE FALLBACK — RULED: NARROWED, and it never overrides. Doctrine first (CLAUDE.md): an
# ambiguous match is refused by design; a title-derived pair that can override conflicting siblings is a guess dressed
# as a placement. So: (a) the fallback applies ONLY when the event's siblings name fewer than two teams; (b) the
# title's two names must be CONSISTENT with every sibling's yes-team (each sibling's yes-team is one of the two, or the
# sibling names none) — any inconsistency REFUSES the event with its own sentinel (TITLE_CONFLICT, named in the
# receipt), never a placement; (c) a single listed market with a two-name title places on those two names only under
# (b); (d) the override of conflicting siblings is REMOVED. The three tests pinning today's behaviour change to pin
# this; the receipt's AFTER column shows any stored leg the narrowing re-verdicts. Live runs are unchanged today (every
# live title reads "<Team> wins"); kalshi-history's API reads are where it bites, which is the paper close record of
# the market-only families — the record a wrong-game leg would quietly corrupt."

DUKE_GT_42101 = game(42101, "Duke", "Georgia Tech", Z("2026-10-10T16:00"))
NOW_UGA = Z("2026-10-10T11:52")


def _titled(mks, title):
    return [dict(m, title=title) for m in mks]


def test_title_fallback_one_market_with_a_consistent_a_vs_b_title_is_placed_on_the_title_s_two_names():
    """(c) under (b): the one market's yes team is one of the title's two names."""
    one = _titled(event("26OCT10UGAALA", [("UGA", "Georgia")]), "Georgia vs Alabama Winner?")
    res = run(one, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert placed(res) == {(32738, "AWAY"): "UGA"} and not res.refused, res.refused
    assert km._pair(one, one[0], lambda m: False) == (["Georgia", "Alabama"], None)       # two names, never one


def test_title_fallback_one_market_whose_yes_team_is_not_in_the_title_is_refused_title_conflict():
    """(b): the one market names Georgia Tech, the title Georgia vs Alabama: the event is refused under its own
    sentinel, never placed on either game, and the console counts it and names the event."""
    one = _titled(event("26OCT10UGAALA", [("GT", "Georgia Tech")]), "Georgia vs Alabama Winner?")
    res = run(one, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert not res.placed and res.refused == {km.TITLE_CONFLICT: 1}, res.refused
    assert res.why == {one[0]["ticker"]: km.TITLE_CONFLICT}
    assert km._pair(one, one[0], lambda m: False) == (["Georgia Tech"], km.TITLE_CONFLICT)
    out = km.console_lines(res)
    assert "       1  the title's two names do not agree with the event's markets" in out, out
    assert ("  ✗ KXNCAAFGAME-26OCT10UGAALA: the title reads Georgia vs Alabama; the markets name Georgia Tech: "
            "refused (the title's two names do not agree with the event's markets)") in out, out
    counts = km.legacy_counts(res)
    assert counts["ambiguous"] == 1 and counts["unmatched"] == 1 and counts["matched"] == 0, counts


def test_title_fallback_never_reads_for_two_siblings_and_a_team_wins_title_is_refused():
    mks = event("26OCT10UGAALA", [("UGA", "Georgia"), ("ALA", "Alabama")])
    titled = _titled(mks, "Duke vs Georgia Tech Winner?")      # a title naming another game: the siblings decide
    res = run(titled, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert placed(res) == {(32738, "AWAY"): "UGA", (32738, "HOME"): "ALA"} and not res.refused, res.refused
    res = run(mks[:1], [UGA_ALA], now=NOW_UGA)               # "<Team> wins": no title pair, refused NO_PAIR
    assert not res.placed and res.refused == {km.NO_PAIR: 1}


def test_title_fallback_never_reads_for_three_conflicting_siblings_refused_no_pair(monkeypatch):
    """(a), (d): three sibling names are refused NO_PAIR whatever the title says; the title is never read (the
    override of conflicting siblings is removed)."""
    from src.adapters.kalshi import KalshiAdapter
    mks = _titled(event("26OCT10UGAALA", [("GT", "Georgia Tech"), ("UGA", "Georgia"), ("ALA", "Alabama")]),
                  "Duke vs Georgia Tech Winner?")
    res = run(mks, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert not res.placed and res.refused == {km.NO_PAIR: 3}, res.refused
    read = []
    monkeypatch.setattr(KalshiAdapter, "title_teams",
                        staticmethod(lambda m: read.append(m) or ("Duke", "Georgia Tech")))
    for legs in ([("GT", "Georgia Tech"), ("UGA", "Georgia"), ("ALA", "Alabama")],
                 [("UGA", "Georgia"), ("ALA", "Alabama")]):
        mks = event("26OCT10UGAALA", legs)
        km.place(mks, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA, lo=NOW_UGA, hi=Z("2026-10-12T00:00"))
    assert read == [], "the title is read only where the siblings name fewer than two teams"


def test_title_fallback_a_sibling_with_no_name_and_a_consistent_title_is_placed():
    """(b): "or the sibling names none": a market with no yes team does not conflict; the named one is placed on the
    title's pair, and the unnamed one takes no side (refused YES_UNKNOWN, as place() refuses a yes team outside the
    pair)."""
    mks = _titled(event("26OCT10UGAALA", [("UGA", "Georgia"), ("X", "")]), "Georgia vs Alabama Winner?")
    res = run(mks, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert placed(res) == {(32738, "AWAY"): "UGA"}, res.refused
    assert res.refused == {km.YES_UNKNOWN: 1} and res.why == {mks[1]["ticker"]: km.YES_UNKNOWN}, res.refused


def test_title_fallback_a_draw_leg_names_none_beside_a_named_sibling():
    """A draw leg is a sibling naming none (b): beside one named sibling the title's pair is read, consistent by (b),
    and both legs are placed; a named sibling outside the title beside it is TITLE_CONFLICT for the whole event."""
    tie = lambda m: m["yes_sub_title"] == "Tie"                          # noqa: E731
    mks = _titled(event("26OCT10UGAALA", [("UGA", "Georgia"), ("TIE", "Tie")]), "Georgia vs Alabama Winner?")
    res = run(mks, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA, is_tie=tie)
    assert placed(res) == {(32738, "AWAY"): "UGA", (32738, "DRAW"): "TIE"} and not res.refused, res.refused
    gt = _titled(event("26OCT10UGAALA", [("GT", "Georgia Tech"), ("TIE", "Tie")]), "Georgia vs Alabama Winner?")
    res = run(gt, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA, is_tie=tie)
    assert not res.placed and res.refused == {km.TITLE_CONFLICT: 2}, res.refused


def test_title_fallback_no_sibling_names_a_team_the_title_is_read_and_consistent():
    """(a) with zero names: no sibling names a team, so the title is read, and every sibling "names none", so it is
    consistent by (b). A draw leg alone is placed DRAW on the title's game; one market with a blank name forms the
    title's pair and takes no side (YES_UNKNOWN), never placed."""
    tie = lambda m: m["yes_sub_title"] == "Tie"                          # noqa: E731
    draw = _titled(event("26OCT10UGAALA", [("TIE", "Tie")]), "Georgia vs Alabama Winner?")
    assert km._pair(draw, draw[0], tie) == (["Georgia", "Alabama"], None)
    res = run(draw, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA, is_tie=tie)
    assert placed(res) == {(32738, "DRAW"): "TIE"} and not res.refused, res.refused
    blank = _titled(event("26OCT10UGAALA", [("X", "")]), "Georgia vs Alabama Winner?")
    assert km._pair(blank, blank[0], lambda m: False) == (["Georgia", "Alabama"], None)
    res = run(blank, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert not res.placed and res.refused == {km.YES_UNKNOWN: 1}, res.refused


@pytest.mark.parametrize("title", ["Georgia vs Georgia Winner?", "Georgia vs georgia Winner?", " vs Alabama Winner?",
                                   "Georgia wins", "Georgia vs Alabama vs Auburn Winner?",
                                   "Georgia vs Alabama v. Auburn Winner?", "Georgia v Alabama vs. Auburn Winner?"])
def test_title_fallback_a_title_that_names_no_two_teams_is_no_pair(title):
    """(c) places only on a two-name title. A title that does not name exactly two teams (the same name twice, in any
    case; an empty name; a name that is itself "B vs C", as title_teams splits at the first separator only) or no
    "A vs B" title at all names no pair: NO_PAIR. Without the guard the first two shapes end NO_FIT (never placed);
    "Georgia vs Alabama vs Auburn" would be placed on Georgia @ Alabama, its second name being "Alabama vs Auburn"."""
    one = _titled(event("26OCT10UGAALA", [("UGA", "Georgia")]), title)
    res = run(one, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert not res.placed and res.refused == {km.NO_PAIR: 1}, (title, res.refused)


# --- the two Codex P2s on #812 (ARCHITECT 2026-11-03 14:35 ET, addendum 237 item 2), verbatim: "The two Codex P2s
# on #812 (question-form titles with a closed league-phrase set; the separator check lower-cased) ride the
# receipt-flags push, as Code has it; one push, one review round." ---

def _kept_leg(ticker):
    """A market of the kept historical page (the probe's payload of 2026-10-14), as the API wrote it."""
    import json
    from pathlib import Path
    page = json.loads((Path(__file__).parent / "fixtures" / "kalshi_history" / "historical_markets_page.json")
                      .read_text())
    return next(m for m in page["markets"] if m["ticker"] == ticker)


LAC_HOU = game(43001, "Los Angeles Chargers", "Houston Texans", Z("2026-08-14T00:00"))
LAR_DAL = game(43002, "Los Angeles Rams", "Dallas Cowboys", Z("2026-08-14T00:30"))       # a decoy of one word
NOW_LAC = Z("2026-08-13T12:00")


@pytest.mark.parametrize("sfx,side", [("LAC", "AWAY"), ("HOU", "HOME")])
def test_question_form_the_kept_page_s_single_listed_market_is_placed_on_its_own_side(sfx, side):
    """P2-A: the kept page titles each market "Will <Y> win the <A> vs <B> Pro Football game?". KalshiAdapter's
    reader splits it verbatim around "vs" (unchanged for its other callers), which is no two names; the matcher parses
    the question form, so a single listed market of either side is placed on its own game and side through
    kalshi-history's placement, never refused TITLE_CONFLICT, the one-word decoy never taking it."""
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_history as kh
    leg = _kept_leg(f"KXNFLGAME-26AUG13LACHOU-{sfx}")
    assert leg["title"].startswith("Will ") and leg["title"].endswith(" vs Houston Pro Football game?"), leg["title"]
    assert KalshiAdapter.title_teams(leg) == (f"Will {leg['yes_sub_title']} win the Los Angeles C",
                                              "Houston Pro Football game?")
    assert km._title_teams(leg) == ["Los Angeles C", "Houston"]
    assert km._pair([leg], leg, lambda m: False) == (["Los Angeles C", "Houston"], None)
    placed_, why, _lines = kh.place_events([leg], [LAC_HOU, LAR_DAL], lambda m: False)
    assert why == {} and placed_ == {leg["ticker"]: (LAC_HOU.id, LAC_HOU.utc_date, side)}, (placed_, why)
    res = run([leg], [LAC_HOU, LAR_DAL], now=NOW_LAC, implied_prob=lambda m: 0.5)
    assert placed(res) == {(LAC_HOU.id, side): sfx} and not res.refused, res.refused


def test_question_form_both_kept_legs_place_both_sides():
    """The kept event as listed (both legs): the siblings name the pair, the title never read; both sides placed."""
    from src.ingestion import kalshi_history as kh
    legs = [_kept_leg("KXNFLGAME-26AUG13LACHOU-LAC"), _kept_leg("KXNFLGAME-26AUG13LACHOU-HOU")]
    placed_, why, _lines = kh.place_events(legs, [LAC_HOU, LAR_DAL], lambda m: False)
    assert why == {} and {t: v[2] for t, v in placed_.items()} == {legs[0]["ticker"]: "AWAY",
                                                                    legs[1]["ticker"]: "HOME"}, (placed_, why)


@pytest.mark.parametrize("title", [
    "Will Los Angeles C win the Los Angeles C vs Houston Pro Hockey game?",        # a league phrase not in the set
    "Will Los Angeles C win the Los Angeles C vs Houston Football game?",
    "Will Los Angeles C win the Los Angeles C vs Houston game?",                   # no league phrase at all
    "Will Los Angeles C win the Los Angeles C vs Houston Pro Football match?",     # not the form
    "Will Los Angeles C win the Los Angeles C vs Houston Pro Football game",
    "Will Los Angeles C win?",
])
def test_question_form_a_title_outside_the_closed_form_is_no_pair_never_guessed(title):
    """P2-A: the league phrase is one of a CLOSED set (QUESTION_LEAGUES: "Pro Football", the only phrase the repo
    evidences); a question-form title outside it, or that does not parse whole, names no pair: NO_PAIR, labelled,
    never handed to the "A vs B" reader and never guessed."""
    assert km.QUESTION_LEAGUES == ("Pro Football",)
    one = [dict(_kept_leg("KXNFLGAME-26AUG13LACHOU-LAC"), title=title)]
    assert km._title_teams(one[0]) is None
    res = run(one, [LAC_HOU, LAR_DAL], now=NOW_LAC, implied_prob=lambda m: 0.5)
    assert not res.placed and res.refused == {km.NO_PAIR: 1}, (title, res.refused)


@pytest.mark.parametrize("title", ["Will Dallas win the Los Angeles C vs Houston Pro Football game?",
                                   "Will Los Angeles win the Los Angeles C vs Houston Pro Football game?"])
def test_question_form_whose_yes_team_is_neither_of_its_names_is_no_pair(title):
    """P2-A: <Y> must be <A> or <B> (case-folded); a title whose own team is neither names no pair: NO_PAIR."""
    one = [dict(_kept_leg("KXNFLGAME-26AUG13LACHOU-LAC"), title=title)]
    assert km._title_teams(one[0]) is None
    res = run(one, [LAC_HOU, LAR_DAL], now=NOW_LAC, implied_prob=lambda m: 0.5)
    assert not res.placed and res.refused == {km.NO_PAIR: 1}, (title, res.refused)


def test_question_form_reads_case_insensitively_and_its_conflict_line_prints_the_parsed_names():
    """The question form is read case-insensitively (its frame and its separator, as P2-B asks); a sibling's yes team
    outside its two names is TITLE_CONFLICT, and the console line prints the names the decision used, never the "A vs
    B" reader's verbatim split."""
    leg = _kept_leg("KXNFLGAME-26AUG13LACHOU-LAC")
    for title in ("will los angeles c win the Los Angeles C VS Houston PRO FOOTBALL GAME?",
                  "Will Los Angeles C win the Los Angeles C v. Houston Pro Football game?"):
        assert km._title_teams(dict(leg, title=title)) == ["Los Angeles C", "Houston"], title
    lar = [dict(leg, yes_sub_title="Los Angeles R")]
    res = run(lar, [LAC_HOU, LAR_DAL], now=NOW_LAC, implied_prob=lambda m: 0.5)
    assert not res.placed and res.refused == {km.TITLE_CONFLICT: 1}, res.refused
    assert ("  ✗ KXNFLGAME-26AUG13LACHOU: the title reads Los Angeles C vs Houston; the markets name Los Angeles R: "
            "refused (the title's two names do not agree with the event's markets)") in km.console_lines(res)


@pytest.mark.parametrize("sfx,own,other", [("LAC", "Los Angeles C", "Houston"), ("HOU", "Houston", "Los Angeles C")])
def test_question_form_whose_yes_team_is_not_the_market_s_own_is_refused_never_placed(sfx, own, other):
    """<Y> must be the market's own yes team (its non-empty yes_sub_title, case-folded), not only one of the title's
    two names: a kept leg whose title names the other team as YES is an inconsistency, TITLE_CONFLICT (addendum 234
    item 2(b): "any inconsistency REFUSES the event"), through place() and kalshi-history's placement alike, never
    placed on the side its title argues against (HEAD c20f2f9a refused it TITLE_CONFLICT too). Both mutations: the
    title's <Y> changed, and the yes_sub_title changed."""
    from src.ingestion import kalshi_history as kh
    leg = _kept_leg(f"KXNFLGAME-26AUG13LACHOU-{sfx}")
    assert (leg["yes_sub_title"] or "").strip() == own
    for mk in (dict(leg, title=f"Will {other} win the Los Angeles C vs Houston Pro Football game?"),
               dict(leg, yes_sub_title=other)):
        assert km._title_teams(mk) == ["Los Angeles C", "Houston"]
        assert km._pair([mk], mk, lambda m: False)[1] == km.TITLE_CONFLICT
        placed_, why, _lines = kh.place_events([mk], [LAC_HOU, LAR_DAL], lambda m: False)
        assert placed_ == {} and why, (placed_, why)
        res = run([mk], [LAC_HOU, LAR_DAL], now=NOW_LAC, implied_prob=lambda m: 0.5)
        assert not res.placed and res.refused == {km.TITLE_CONFLICT: 1}, res.refused
        yes, mine = (other, own) if mk["yes_sub_title"] == leg["yes_sub_title"] else (own, other)
        assert (f"  ✗ KXNFLGAME-26AUG13LACHOU: the title names {yes} as its yes team; the market's yes team is "
                f"{mine}: refused ({km.TITLE_CONFLICT})") in km.console_lines(res)
    blank = dict(leg, title=f"Will {own} win the Los Angeles C vs Houston Pro Football game?")
    assert km._pair([blank], blank, lambda m: False) == (["Los Angeles C", "Houston"], None)    # agrees: formed
    cased = dict(leg, title=f"Will {own.upper()} win the Los Angeles C vs Houston Pro Football game?")
    assert km._pair([cased], cased, lambda m: False) == (["Los Angeles C", "Houston"], None)    # case-folded


@pytest.mark.parametrize("title", [
    "Georgia vs Alabama VS Auburn Winner?", "Georgia vs Alabama Vs Auburn Winner?",
    "Georgia vs Alabama V. Auburn Winner?", "Georgia vs Alabama V Auburn Winner?", "Georgia v Alabama VS. Auburn Winner?",
    "Will Georgia win the Georgia VS Alabama vs Auburn Pro Football game?",
    "Will Georgia win the Georgia vs Alabama V. Auburn Pro Football game?",
])
def test_a_mixed_case_embedded_separator_is_two_teams_no_pair(title):
    """P2-B: the embedded-separator guard compares case-folded, so "Alabama VS Auburn" is two teams as "Alabama vs
    Auburn" is: NO_PAIR, never placed on Georgia @ Alabama (before the fix, the old form's second name passed)."""
    one = _titled(event("26OCT10UGAALA", [("UGA", "Georgia")]), title)
    res = run(one, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert not res.placed and res.refused == {km.NO_PAIR: 1}, (title, res.refused)


@pytest.mark.parametrize("title", ["Will Georgia win the Georgia vs Alabama vs Auburn Pro Football game?",
                                   "Will Alabama win the Georgia vs Alabama vs Auburn Pro Football game?",
                                   "Will Auburn win the Georgia vs Alabama vs Auburn Pro Football game?"])
def test_a_three_team_question_form_is_no_pair(title):
    one = _titled(event("26OCT10UGAALA", [("UGA", "Georgia")]), title)
    res = run(one, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert not res.placed and res.refused == {km.NO_PAIR: 1}, (title, res.refused)


@pytest.mark.parametrize("title", ["Georgia vs Alabama Winner?", "Georgia vs. Alabama Winner?",
                                   "Georgia v Alabama Winner?", "St. Louis vs Chicago C Winner?", "Georgia wins",
                                   "Georgia VS Alabama Winner?", "", None])
def test_the_a_vs_b_form_is_read_as_before(title):
    """The "A vs B Winner?" form is read by KalshiAdapter.title_teams, unchanged (its case-sensitive split included:
    "Georgia VS Alabama Winner?" gives no names, NO_PAIR as before); the placement of the old form is unchanged."""
    from src.adapters.kalshi import KalshiAdapter
    mk = {"title": title}
    tt = KalshiAdapter.title_teams(mk)
    assert km._title_teams(mk) == ([n.strip() for n in tt] if tt else None), title
    one = _titled(event("26OCT10UGAALA", [("UGA", "Georgia")]), "Georgia vs Alabama Winner?")
    res = run(one, [UGA_ALA, DUKE_GT_42101], now=NOW_UGA)
    assert placed(res) == {(32738, "AWAY"): "UGA"} and not res.refused, res.refused


def test_the_codex_p2s_quote_addendum_237_item_2_verbatim_at_the_change():
    ruling = ("The two Codex P2s on #812 (question-form titles with a closed league-phrase set; the separator check "
              "lower-cased) ride the receipt-flags push, as Code has it; one push, one review round.")
    assert ruling in " ".join(km._pair.__doc__.split())


def test_title_conflict_reads_through_kalshi_history_s_placement_of_a_settled_event():
    """kalshi-history's API reads are where the narrowing bites (addendum 234 item 2): kalshi_history.place_events
    places each settled event through kalshi_match.place, so a settled one-market event whose yes team is not in its
    title is refused TITLE_CONFLICT there, and a consistent one is placed. The replay (kalshi_replay) calls the same
    place()."""
    import inspect as _inspect

    from src.ingestion import kalshi_history as kh
    from src.ingestion import kalshi_replay
    bad = _titled(event("26OCT10UGAALA", [("GT", "Georgia Tech")]), "Georgia vs Alabama Winner?")
    good = _titled(event("26OCT10FAMUALST", [("FAMU", "Florida A&M")]), "Florida A&M vs Alabama St. Winner?")
    placed_, why, lines = kh.place_events(bad + good, [UGA_ALA, DUKE_GT_42101, FAMU_ALST], lambda m: False)
    assert why == {bad[0]["ticker"]: km.TITLE_CONFLICT}, why
    assert placed_ == {good[0]["ticker"]: (FAMU_ALST.id, FAMU_ALST.utc_date, "AWAY")}, placed_
    assert any("26OCT10UGAALA: the title reads Georgia vs Alabama" in ln for ln in lines), lines
    assert "km.place(" in _inspect.getsource(kalshi_replay)


def test_the_narrowed_fallback_quotes_addendum_234_item_2_verbatim_at_the_change():
    from tests.test_kalshi_pair_receipt import script
    assert script.RULING_234_2 in " ".join(km._pair.__doc__.split())
    assert km.TITLE_CONFLICT == "the title's two names do not agree with the event's markets"


def test_no_yes_team_reader_is_left_on_the_adapter_or_the_placement():
    """Addendum 230 item 0(a): "the yes-team fallback goes". The adapter's yes_team() had no caller since the switch;
    it is removed, and the placement reads the yes team only to tell the side inside the pair it formed."""
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_sync
    assert not hasattr(KalshiAdapter, "yes_team")
    for mod in (km, kalshi_sync):
        assert "yes_team(" not in inspect.getsource(mod)
    src = inspect.getsource(km._pair)
    assert "yes_sub_title" in src and "_title_teams(first)" in src     # siblings first; the narrowed title only
    assert "_pair(" in inspect.getsource(km._names) and "_pair(" in inspect.getsource(km.place)


# --- addendum 44 item 2's two new rows: 32749 and 32763, one name placing another game's event ---

DUKE_GT = game(32749, "Duke", "Georgia Tech", Z("2026-10-10T16:00"))
RICE_ECU = game(32763, "Rice", "East Carolina", Z("2026-10-10T16:00"))
SCST_CHSO = game(32817, "South Carolina State", "Charleston Southern", Z("2026-10-10T16:00"))


def test_32749_never_takes_ugaala_georgia_leg():
    """32749 Duke @ Georgia Tech held HOME from 26OCT10UGAALA-UGA: "Georgia" shares a word with Georgia Tech; "Alabama"
    fits neither Duke nor Georgia Tech, so the pair fits no game there. With its own game in the store it lands there,
    both sides; without it (the window, the load) it is refused, never on 32749 or 32810."""
    famu_moved = game(32810, "Florida A&M", "Alabama State", Z("2026-10-09T16:00"))
    res = run(UGAALA, [DUKE_GT, famu_moved], now=Z("2026-10-08T21:56:38"), hours=96)
    assert not res.placed and res.refused == {km.NO_FIT: 2}
    res = run(UGAALA, [DUKE_GT, famu_moved, UGA_ALA], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32738, "AWAY"): "UGA", (32738, "HOME"): "ALA"}, res.refused


def test_32763_never_takes_scstchso_south_carolina_state_leg():
    """32763 Rice @ East Carolina held HOME from 26OCT10SCSTCHSO-SCST ("Carolina" in both). One each: "Charleston
    Southern" fits neither Rice nor East Carolina."""
    res = run(SCSTCHSO, [RICE_ECU, CCAR_MRSH], now=Z("2026-10-10T11:52"))
    assert not res.placed and res.refused == {km.NO_FIT: 2}
    res = run(SCSTCHSO, [RICE_ECU, CCAR_MRSH, SCST_CHSO], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32817, "AWAY"): "SCST", (32817, "HOME"): "CHSO"}, res.refused


@pytest.mark.parametrize("reverse", [False, True])
def test_receipt_d_the_true_game_beyond_the_window_is_refused_not_stored_on_another(reverse):
    """#413 receipt D: "true game beyond the window — stored: North Dakota @ Northern Iowa AWAY 0.595 NDSUUNLV-NDSU".
    Now refused as outside the window; North Dakota @ Northern Iowa holds its own event only, either list order."""
    now = Z("2026-10-08T21:56:38")
    mks = NDSUUNLV + UNDUNI
    res = run(mks[::-1] if reverse else mks, [UND_UNI, NDSU_UNLV], now=now)
    assert placed(res) == {(32812, "AWAY"): "UND", (32812, "HOME"): "UNI"}, res.refused
    assert res.refused == {km.OUTSIDE_WINDOW: 2}
    assert all(res.why[m["ticker"]] == km.OUTSIDE_WINDOW for m in NDSUUNLV)


@pytest.mark.parametrize("reverse", [False, True])
def test_a_kickoff_moved_off_a_clock_ticker_s_date_is_refused_never_given_to_a_one_name_game(reverse):
    """A clock series (MLB): the pair's game moved to the next day. The ticker's own date gives the game (addendum 52
    item 4), so the event is refused as no game of the pair on the date; a game on the date that shares one name
    (Chicago White Sox) never takes it."""
    mks = event("26OCT011905STLCHC", [("STL", "St. Louis"), ("CHC", "Chicago C")], series="KXMLBGAME")
    moved = game(43001, "St. Louis Cardinals", "Chicago Cubs", Z("2026-10-02T23:05"))
    one_name = game(43002, "Detroit Tigers", "Chicago White Sox", Z("2026-10-01T23:10"))
    games = [one_name, moved][::-1] if reverse else [one_name, moved]
    res = run(mks[::-1] if reverse else mks, games, now=Z("2026-10-01T12:00"))
    assert not res.placed and res.refused == {km.NO_GAME_ON_DATE: 2}, res.refused
    assert any("no game of the pair on that date" in ln and "43001" in ln for ln in res.lines), res.lines


def test_a_date_only_kickoff_moved_six_hours_stays_on_its_own_game():
    """#413 receipt D: "true game's kickoff 6h off — stored: Coastal Carolina @ Marshall AWAY 0.675 SCSTCHSO-SCST".
    A date-only ticker: the pair's own game takes it, Coastal Carolina @ Marshall takes nothing of it."""
    res = run(SCSTCHSO, [CCAR_MRSH, SCST_CHSO], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32817, "AWAY"): "SCST", (32817, "HOME"): "CHSO"}
    assert not any(mid == 32772 for mid, _ in res.placed)


def test_famualst_and_ugaala_together_each_hold_their_own_game():
    """The UGAALA split: its Alabama leg sat on Florida A&M @ Alabama State (32810). With both events and both games
    in view, each event holds its own game, both names."""
    from tests.test_kalshi_matcher_day_rule import FAMUALST
    famu_moved = game(32810, "Florida A&M", "Alabama State", Z("2026-10-09T16:00"))
    res = run(UGAALA + FAMUALST, [famu_moved, UGA_ALA, DUKE_GT], now=Z("2026-10-09T10:00"), hours=72)
    assert placed(res) == {(32738, "AWAY"): "UGA", (32738, "HOME"): "ALA",
                           (32810, "AWAY"): "FAMU", (32810, "HOME"): "ALST"}, res.refused
    assert FAMU_ALST.id == 32810


# --- the sync's console: the refusal is counted and named, nothing stored, and the sentinel fires ---

def test_the_shared_sync_refuses_a_one_sibling_event_by_name_and_the_sentinel_fires(monkeypatch):
    code = "A413NFL"
    _a54_comp(code, "NFL")
    _a54_row(code, "NFL", f"Fox Fens {code}", f"Eel Elks {code}", Z("2026-10-14T23:00"))   # in the window, unstarted
    one = event("26OCT14EEFF", [("EE", f"Eel Elks {code}")], series=f"KX{code}GAME")
    r, lines = _a54_sync(monkeypatch, "shared", code, one)
    assert r["ok"] and r["stored"] == 0 and r["matched"] == 0 and r["refused"] == {km.NO_PAIR: 1}, r
    assert "       1  the event's markets do not name two teams" in lines, lines
    assert r["alarm"] and any(ln.startswith("  ⚠ MATCHED ZERO") for ln in lines), lines
    two = event("26OCT14EEFF", [("EE", f"Eel Elks {code}"), ("FF", f"Fox Fens {code}")], series=f"KX{code}GAME")
    r, lines = _a54_sync(monkeypatch, "shared", code, two)
    assert r["ok"] and r["stored"] == 2 and r["refused"] == {} and not r["alarm"], r
