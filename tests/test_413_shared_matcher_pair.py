"""#413, THE SHARED KALSHI MATCHER'S PAIR (ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 0(a)): "the pair comes from
the event's sibling markets as the soccer path does since 09-13; the yes-team fallback goes; a market whose pair cannot
be formed is REFUSED by the sentinel (never placed by one name)".

The placement is kalshi_match.place, the one placement of both sync paths since the switch (#461, #475). These pins
hold it on the shapes #413 and addendum 44 item 2 receipted, on each two-way series' ticker shape, with every market
titled "<Team> wins" as Kalshi writes them (so the old "A vs B" title fallback reads nothing there); the fallback's
own pins, as it reads today, are below. Synthetic games and a throwaway DB only (tests/conftest.py)."""
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


# --- the old two-name title fallback (kalshi_match._names), KEPT and pinned as it reads: the open question ---
# The soccer path's 09-13 repair, which addendum 230 item 0(a) names as the model, kept it ("keep the old title parse as
# fallback"; at 081d9fa: `tuple(_sibs) if len(_sibs) == 2 else KalshiAdapter.title_teams(mk)`), and _names carries it
# unchanged. It never places by one name: where the siblings do not name two teams and the event's first priced market
# carries an "A vs B" title, the title's two names are the pair. Whether that stands where the siblings conflict (three
# names) is put to the architect on the PR (round-1 review); these pins hold today's reading so that a ruling changes
# them visibly, never silently.

def _titled(mks, title):
    return [dict(m, title=title) for m in mks]


def test_title_fallback_one_market_with_an_a_vs_b_title_is_placed_on_the_title_s_two_names():
    one = _titled(event("26OCT10UGAALA", [("UGA", "Georgia")]), "Georgia vs Alabama Winner?")
    res = run(one, [UGA_ALA, game(42101, "Duke", "Georgia Tech", Z("2026-10-10T16:00"))], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32738, "AWAY"): "UGA"} and not res.refused, res.refused
    assert km._names(one, one[0], lambda m: False) == ["Georgia", "Alabama"]          # two names, never one


def test_title_fallback_never_reads_for_two_siblings_and_a_team_wins_title_is_refused():
    mks = event("26OCT10UGAALA", [("UGA", "Georgia"), ("ALA", "Alabama")])
    titled = _titled(mks, "Duke vs Georgia Tech Winner?")      # a title naming another game: the siblings decide
    res = run(titled, [UGA_ALA, game(42101, "Duke", "Georgia Tech", Z("2026-10-10T16:00"))], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(32738, "AWAY"): "UGA", (32738, "HOME"): "ALA"}, res.refused
    res = run(mks[:1], [UGA_ALA], now=Z("2026-10-10T11:52"))  # "<Team> wins": no title pair, refused NO_PAIR
    assert not res.placed and res.refused == {km.NO_PAIR: 1}


def test_title_fallback_on_three_conflicting_siblings_today_reads_the_title_the_open_question():
    """Today's reading, pinned (the open question for the architect): three sibling names do not form the pair, and an
    "A vs B" title on the event's first priced market then gives it. The markets whose yes team is neither title name
    are refused YES_UNKNOWN; one that is a title name is placed on the title's game."""
    mks = _titled(event("26OCT10UGAALA", [("GT", "Georgia Tech"), ("UGA", "Georgia"), ("ALA", "Alabama")]),
                  "Duke vs Georgia Tech Winner?")
    duke_gt = game(42101, "Duke", "Georgia Tech", Z("2026-10-10T16:00"))
    res = run(mks, [UGA_ALA, duke_gt], now=Z("2026-10-10T11:52"))
    assert placed(res) == {(42101, "HOME"): "GT"}, res.refused
    assert res.refused == {km.YES_UNKNOWN: 2}, res.refused


def test_no_yes_team_reader_is_left_on_the_adapter_or_the_placement():
    """Addendum 230 item 0(a): "the yes-team fallback goes". The adapter's yes_team() had no caller since the switch;
    it is removed, and the placement reads the yes team only to tell the side inside the pair it formed."""
    from src.adapters.kalshi import KalshiAdapter
    from src.ingestion import kalshi_sync
    assert not hasattr(KalshiAdapter, "yes_team")
    for mod in (km, kalshi_sync):
        assert "yes_team(" not in inspect.getsource(mod)
    src = inspect.getsource(km._names)
    assert "yes_sub_title" in src and "title_teams(first)" in src      # siblings first; the old two-name title only


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
