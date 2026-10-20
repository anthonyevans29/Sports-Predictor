"""THE ANCHORED CHAIN, `kalshi-history place-chain` (ARCHITECT 2026-10-20 12:56 ET, addendum 148 item 2, on the design
of #630; #598's follow-up). The ruling's change to the design's center, verbatim: "a shift-capable check IS wanted,
because the shifted chain is the case the rule exists for (E17 on 50548 is the ALCS's own example, and every
rainout-then-doubleheader pattern is a shift). A member PLACES on the count's game when EITHER check passes, and a
result mismatch refuses under both: (a) the clock check as designed: |kickoff − ticker clock| ≤ MAX_TICK_DRIFT and no
other unused game within 2h; or (b) the settlement bracket: the row's settled_time is after the count's game's kickoff
and before the kickoff of the pair's next game in the list (or no next game within N1's window), the target is
FINISHED with a stored winner, and the leg's kalshi_result agrees with that winner. [...] A member that passes neither
stays held and the chain STOPs (Q3). The dry run prints which check placed each row ("by clock 0.1h" or "by settlement
+2.9h, before <next id> <ET>"). Tests gain: E17 placed on 50548 by settlement; a settlement after the next game's
kickoff stays held; a result mismatch refuses under (b); a SCHEDULED target never places under (b)."

The world is tests/test_kalshi_history_identity_hold.py's ALCS pair (synthetic markets, a throwaway DB per test): Game
3 (50546) on 10-15; 50550 played 10-17 20:08 ET (Game 4); 50548, the 10-16 game postponed to 10-18 21:08Z (Game 5). This
file adds Game 6, written here: 50551, Cleveland at Tampa Bay, 2026-10-19 20:08 ET (10-20 00:08Z), and its event
KXMLBGAME-26OCT192008CLETB, settled 2026-10-20 03:30Z (Game 6's real kickoff is not in the repo; this one is the
fixture's). E16 (26OCT161800TBCLE, out of step on 10-16) is the anchor, ruled onto 50550 by place-held; E17
(26OCT172000TBCLE, clock 10-18 00:00Z) is 0.1h from 50550 and 21.1h from 50548, the count's game; the results written
here (Tampa Bay wins Games 5 and 6) are the fixture's, not a record."""
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import inspect, text

from src.adapters.kalshi import KalshiAdapter
from src.ingestion import kalshi_history as kh
from src.ingestion import kalshi_match as km
from tests import test_kalshi_history_identity_hold as T
from tests.test_kalshi_history_identity_hold import (
    CLE, E16, E17, G4, G5, K4, K5, NOW, RULING, S, SETTLED15, SETTLED16, SETTLED17, TB, Fake, _backup, candles_at, event,
    go, hold, redate, rows, seed)

db, alcs, waits = T.db, T.alcs, T.waits                # the identity hold's fixtures, registered here by name

G6, K6 = 50551, datetime(2026, 10, 20, 0, 8)            # Game 6, Cleveland at Tampa Bay, 20:08 ET 10-19 (the fixture's)
E19 = f"{S}-26OCT192008CLETB"
SETTLED19 = event(E19, "yes", "2026-10-20T03:25:00Z", "2026-10-20T03:30:00Z")
AT = datetime(2026, 10, 20, 15, 0)
CAND = {f"{E17}-TB": candles_at(K5), f"{E17}-CLE": candles_at(K5, "0.54", "0.55"),
        f"{E19}-TB": candles_at(K6, "0.50", "0.52"), f"{E19}-CLE": candles_at(K6, "0.48", "0.50")}
CHAIN17 = f"placed by the chain of {E16} [1]: by settlement +3.6h, before {G6} 2026-10-19 20:08 ET"


def finish(gid, home, away):
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Result
    with session_scope() as s:
        g = s.get(Match, gid)
        g.status, g.home_score, g.away_score = MatchStatus.FINISHED, home, away
        g.full_time_result = Result.HOME if home > away else Result.AWAY if away > home else Result.DRAW


def set_status(gid, status, clear=False):
    """The game's stored status; `clear` drops its stored result (no winner stored)."""
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    with session_scope() as s:
        g = s.get(Match, gid)
        g.status = MatchStatus(status)
        if clear:
            g.home_score, g.away_score, g.full_time_result = None, None, None


def edit(ticker, **cols):
    from sqlalchemy import update

    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket as K
    with session_scope() as s:
        s.execute(update(K).where(K.ticker == ticker).values(**cols))


def add(ev, name, sfx, **cols):
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket as K
    with session_scope() as s:
        s.add(K(ticker=f"{ev}-{sfx}", event_ticker=ev, series=S, yes_sub_title=name, source="live", fetched_at=NOW,
                **cols))


def world(alcs):
    """Monday's pull and Game 6's (26OCT172000TBCLE and 26OCT192008CLETB held behind 26OCT161800TBCLE, out of step);
    26OCT161800TBCLE ruled onto 50550 by place-held, both legs (addendum 130 item 2(c)'s first two uses); Games 5 and
    6 finished, Tampa Bay winning both (the fixture's results)."""
    seed({G6: (CLE, TB, K6, "scheduled")})
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED19))
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E16}-{sfx}", G4, RULING, adapter=Fake(), echo=lambda s: None, now=datetime(2026, 10, 19, 15))
    finish(G5, 2, 5)                                   # 50548: Tampa Bay (away) 5, Cleveland 2
    finish(G6, 4, 1)                                   # 50551: Tampa Bay (home) 4, Cleveland 1
    got = rows()
    for ev in (E17, E19):
        for sfx in ("TB", "CLE"):
            assert got[f"{ev}-{sfx}"]["notes"].startswith(hold(E16, "out of step"))
    return got


def chain(*, dry_run=True, fake=None, ruling=RULING, anchor=E16, **kw):
    out = []
    res = kh.place_chain(anchor, ruling, dry_run=dry_run, adapter=fake or Fake(candles=CAND), echo=out.append, now=AT,
                         **kw)
    return res, out


def verdicts(res):
    return {t: v for ev in res["plan"]["events"] for t, v in ev["verdicts"].items()}


def placed_on(t):
    r = rows()[t]
    return r["match_id"], r["side"]


# ---- the ruling's example: E17 on 50548 by settlement; Game 6 by clock -----------------------------------------------

def test_e17_is_placed_on_50548_by_settlement_and_game_6_by_clock(alcs):
    """The ALCS's own example (addendum 148 item 2): E17's clock is 21.1h from 50548, the count's game (50550 is used by
    the anchor), so the clock check fails; it settled 2026-10-19 00:45Z, 3.6h after 50548's kickoff and before 50551's,
    50548 is FINISHED with Tampa Bay winning, and each leg's result agrees: placed BY SETTLEMENT. 26OCT192008CLETB is no
    shift: 0.0h from 50551, placed BY CLOCK. Each row is written as place-held writes it, its candles read then on the
    game's kickoff, its note in four parts."""
    before = world(alcs)
    res, out = chain(dry_run=False)
    got = rows()
    assert res["written"]
    assert (placed_on(f"{E17}-TB"), placed_on(f"{E17}-CLE")) == ((G5, "AWAY"), (G5, "HOME"))
    assert (placed_on(f"{E19}-TB"), placed_on(f"{E19}-CLE")) == ((G6, "HOME"), (G6, "AWAY"))
    tb = got[f"{E17}-TB"]
    assert (tb["last_ts"], tb["last_bid"], tb["last_ask"], tb["fetched_at"]) == (K5, 0.45, 0.46, AT)
    # the note's four parts: the stored notes, the anchor's ruling, the chain's own part, the candles' note (Q5)
    assert tb["notes"] == (f"{before[f'{E17}-TB']['notes']}; placed by ruling: {RULING}; {CHAIN17}; candles read at "
                           f"placement on match {G5}'s kickoff")
    assert got[f"{E19}-TB"]["notes"] == (f"{before[f'{E19}-TB']['notes']}; placed by ruling: {RULING}; placed by the "
                                         f"chain of {E16} [2]: by clock 0.0h; candles read at placement on match "
                                         f"{G6}'s kickoff")
    assert {t: r for t, r in got.items() if not t.startswith((E17, E19))} == \
        {t: r for t, r in before.items() if not t.startswith((E17, E19))}
    assert f"  [1] {E17} · clock 2026-10-17 20:00 ET · count's game {G5} 2026-10-18 17:08 ET finished · 21.1h" in out
    assert (f"    {E17}-TB · held, names {E16} out of step · result yes · winner AWAY · settled 2026-10-19 00:45:00Z "
            f"(+3.6h) · PLACE AWAY by settlement +3.6h, before {G6} 2026-10-19 20:08 ET") in out
    assert (f"    {E19}-TB · held, names {E16} out of step · result yes · winner HOME · settled 2026-10-20 03:30:00Z "
            "(+3.4h) · PLACE HOME by clock 0.0h") in out
    assert out[-6] == ("  chain: 2 event(s) · 2 member(s) · 4 row(s) to place · 0 stay held · games no event took: "
                       "none · calls 5 of 15")
    assert out[-5:] == [f"  ✓ placed: {E17}-CLE on match {G5} HOME (the chain of {E16} [1])",
                        f"  ✓ placed: {E17}-TB on match {G5} AWAY (the chain of {E16} [1])",
                        f"  ✓ placed: {E19}-CLE on match {G6} AWAY (the chain of {E16} [2])",
                        f"  ✓ placed: {E19}-TB on match {G6} HOME (the chain of {E16} [2])",
                        "  ✓ written: 4 row(s) of kalshi_settled_markets, in one transaction"]
    # a ruled row: a later pull leaves it alone (it has a match_id; it claims its stored side only)
    run, _ = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED19), now=datetime(2026, 10, 21, 12, 0))
    assert rows() == got and run.already == 8 and not run.replaced


def test_the_dry_run_prints_the_chain_writes_nothing_and_never_calls_the_guard(alcs):
    from src.db.database import get_engine
    world(alcs)
    eng = get_engine()

    def counts():
        with eng.connect() as c:
            return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in inspect(eng).get_table_names()}
    before, n0, guarded = rows(), counts(), []
    fake = Fake(candles=CAND)
    res, out = chain(fake=fake, guard=lambda: guarded.append(1))
    assert rows() == before and counts() == n0 and not guarded and not res["written"]
    assert out[0] == f"kalshi-history place-chain {E16} · DRY RUN: nothing is written · ruling: {RULING}"
    assert out[1] == (f"  anchor {E16} · clock 2026-10-16 18:00 ET · out of step: no game of its two teams on its date "
                      f"2026-10-16 · ruled on match {G4}: {TB} at {CLE} · kickoff 2026-10-18 00:08Z (2026-10-17 20:08 "
                      f"ET) · finished · {E16}-CLE HOME, {E16}-TB AWAY")
    assert out[2] == (f"  games after {E16}'s clock through 2026-10-27: {G4} 2026-10-17 20:08 ET finished [used by "
                      f"{E16}]; {G5} 2026-10-18 17:08 ET finished; {G6} 2026-10-19 20:08 ET finished")
    assert out[-1].endswith(" · calls 5 of 15 · DRY RUN: nothing written")
    # the candle reads at placement, as place-held's dry run makes them: the cutoff once, then one call per row placed
    assert [p for p, _ in fake.calls] == ["historical/cutoff"] + [
        f"series/{S}/markets/{t}/candlesticks" for t in (f"{E17}-CLE", f"{E17}-TB", f"{E19}-CLE", f"{E19}-TB")]
    assert [r["match_id"] for r in res["placed"]] == [G5, G5, G6, G6]
    # place-held's own lines under each row placed
    i = out.index(f"    {E17}-TB · held, names {E16} out of step · result yes · winner AWAY · settled 2026-10-19 "
                  f"00:45:00Z (+3.6h) · PLACE AWAY by settlement +3.6h, before {G6} 2026-10-19 20:08 ET")
    assert out[i + 1].startswith(f"      before: {E17}-TB · live · match - - · result yes")
    assert out[i + 2] == (f"      match {G5}: {TB} at {CLE} · kickoff 2026-10-18 21:08Z (2026-10-18 17:08 ET) · finished "
                          "· the event's names Tampa Bay / Cleveland fit it one each: Tampa Bay is AWAY")
    assert out[i + 3] == ("      cutoff market_settled_ts: 2026-08-15T00:00:00Z · settled 2026-10-19 00:45:00Z · candles "
                          "from live")
    assert out[i + 4].startswith(f"      candles: series/{S}/markets/{E17}-TB/candlesticks from 2026-10-18 15:08Z")
    assert out[i + 5].startswith(f"      after:  {E17}-TB · live · match {G5} AWAY")


# ---- the settlement bracket (b) --------------------------------------------------------------------------------------

def test_a_settlement_after_the_next_game_s_kickoff_stays_held_and_the_chain_stops(alcs):
    """E17 settled after 50551's kickoff: the bracket does not hold (it could be 50551's settlement), the clock is 21.1h
    off, so E17 stays held and the chain STOPs (Q3): Game 6's event, which would pass by clock, stays held behind it."""
    world(alcs)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", settled_time=datetime(2026, 10, 20, 1, 0))
    res, out = chain(dry_run=False)
    v = verdicts(res)
    assert v[f"{E17}-TB"] == ("stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: settled 2026-10-20 "
                              f"01:00:00Z, not before the next game {G6}'s kickoff 2026-10-19 20:08 ET; the chain stops")
    assert v[f"{E19}-TB"] == v[f"{E19}-CLE"] == "stays held: the chain stopped at [1]"
    assert f"  [2] {E19} · clock 2026-10-19 20:08 ET · not counted: the chain stopped at [1]" in out
    assert not res["written"] and all(kh.is_held(r["match_id"], r["notes"]) for t, r in rows().items()
                                      if t.startswith((E17, E19)))
    assert out[-1] == ("  chain: 2 event(s) · 2 member(s) · 0 row(s) to place · 4 stay held · games no event took: "
                       f"{G5}, {G6} · calls 0 of 3 · nothing to place: nothing written")


def test_with_no_next_game_in_the_list_the_bracket_is_the_kickoff_alone(alcs):
    """"(or no next game within N1's window)": with no Game 6 stored, 50548 is the list's last game; E17 settled after
    its kickoff and is placed by settlement, the note saying there was no next game."""
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17))
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E16}-{sfx}", G4, RULING, adapter=Fake(), echo=lambda s: None, now=AT)
    finish(G5, 2, 5)
    res, _ = chain(dry_run=False)
    how = "by settlement +3.6h, no next game of the pair through 2026-10-27"
    assert verdicts(res)[f"{E17}-TB"] == f"PLACE AWAY {how}"
    assert f"; placed by the chain of {E16} [1]: {how}; " in rows()[f"{E17}-TB"]["notes"]
    assert placed_on(f"{E17}-CLE") == (G5, "HOME")


def test_a_held_row_naming_the_anchor_whose_event_is_not_stored_whole_is_listed_not_read(alcs):
    world(alcs)
    lone = f"{S}-26OCT181900TBCLE"
    add(lone, "Tampa Bay", "TB", notes=f"{hold(E16, 'out of step')}; {kh.HOLD_NO_CANDLES}", kalshi_result="yes")
    res, out = chain()
    assert f"  held rows naming {E16} outside the chain: {lone}-TB (its stored rows are not two legs of a clock " \
           "event: not read (an event the table does not hold whole is invisible to the count))" in out
    assert len(res["placed"]) == 4


def test_a_settlement_before_the_game_s_kickoff_stays_held(alcs):
    world(alcs)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", settled_time=datetime(2026, 10, 18, 3, 20))       # 50550's settlement, not 50548's
    res, _ = chain()
    assert verdicts(res)[f"{E17}-CLE"].endswith(f"by settlement: settled 2026-10-18 03:20:00Z, not after game {G5}'s "
                                                "kickoff; the chain stops")
    assert not res["placed"]


@pytest.mark.parametrize("settled, why", [
    (K6, f"settled 2026-10-20 00:08:00Z, not before the next game {G6}'s kickoff 2026-10-19 20:08 ET"),
    (K5, f"settled 2026-10-18 21:08:00Z, not after game {G5}'s kickoff"),
], ids=["at-the-next-game-s-kickoff", "at-the-count-s-game-s-kickoff"])
def test_a_settlement_exactly_at_either_kickoff_stays_held(alcs, settled, why):
    """The bracket is open at both ends ("after the count's game's kickoff and before the kickoff of the pair's next
    game"): E17 settled at 50551's kickoff to the second, or at 50548's, is not inside it, and stays held."""
    world(alcs)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", settled_time=settled)
    res, _ = chain()
    assert verdicts(res)[f"{E17}-TB"] == (f"stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: {why}; "
                                          "the chain stops")
    assert not res["placed"]


def test_a_leg_with_no_stored_result_never_places_under_b(alcs):
    """(b) needs "the leg's kalshi_result agrees with that winner": a leg with no result stored cannot agree."""
    world(alcs)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", kalshi_result=None)
    res, _ = chain()
    assert verdicts(res)[f"{E17}-TB"] == ("stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: no result "
                                          "stored for the leg; the chain stops")
    assert not res["placed"]


def test_an_event_is_placed_on_all_its_legs_or_on_none(alcs):
    """Only E17-CLE fails (no result stored for it), E17-TB alone would pass by settlement: both legs stay held, the
    chain stops, and nothing is written."""
    world(alcs)
    edit(f"{E17}-CLE", kalshi_result=None)
    before = rows()
    res, _ = chain(dry_run=False)
    v = verdicts(res)
    assert v[f"{E17}-CLE"] == ("stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: no result stored for "
                               "the leg; the chain stops")
    assert v[f"{E17}-TB"] == "stays held: the event is placed on all its legs or on none; the chain stops"
    assert v[f"{E19}-TB"] == v[f"{E19}-CLE"] == "stays held: the chain stopped at [1]"
    assert not res["placed"] and not res["written"] and rows() == before


def test_a_stored_result_that_disagrees_with_the_scores_stores_no_winner(alcs):
    """50548's full_time_result says Cleveland (home) won while its scores say Tampa Bay 5-2: the two disagree, so no
    winner is stored (law 4), neither read alone, and (b) cannot place E17."""
    from src.db.database import session_scope
    from src.db.schema import Match, Result
    world(alcs)
    with session_scope() as s:
        s.get(Match, G5).full_time_result = Result.HOME
    res, out = chain()
    assert verdicts(res)[f"{E17}-TB"] == ("stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: no winner "
                                          f"stored for game {G5}; the chain stops")
    assert any(ln.startswith(f"    {E17}-TB · ") and " · winner not stored · " in ln for ln in out)
    assert not res["placed"]


def test_a_scheduled_target_never_places_under_b(alcs):
    """50548 still SCHEDULED (no winner stored): the bracket needs it FINISHED with a stored winner. E17 stays held."""
    world(alcs)
    set_status(G5, "scheduled", clear=True)
    res, _ = chain()
    assert verdicts(res)[f"{E17}-TB"] == ("stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: game "
                                          f"{G5} is scheduled, not finished; the chain stops")
    assert not res["placed"]


def test_a_finished_target_with_no_stored_winner_never_places_under_b(alcs):
    world(alcs)
    set_status(G5, "finished", clear=True)
    res, _ = chain()
    assert verdicts(res)[f"{E17}-TB"].endswith(f"by settlement: no winner stored for game {G5}; the chain stops")


def test_a_result_mismatch_refuses_under_b(alcs):
    """50548 stored as Cleveland's win while E17's legs say Tampa Bay won: the leg's result disagrees, E17 stays held."""
    world(alcs)
    finish(G5, 6, 1)
    res, _ = chain()
    v = verdicts(res)
    assert v[f"{E17}-TB"] == "stays held: result yes, AWAY lost; the chain stops"
    assert v[f"{E17}-CLE"] == "stays held: result no, HOME won; the chain stops"
    assert not res["placed"]


# ---- the clock check (a) ---------------------------------------------------------------------------------------------

def _e17_by_hand(alcs):
    """E17 ruled onto 50548 by hand (place-held, addendum 130 item 2(c)'s third use): counted, so Game 6's event is the
    first member, and a shift no longer stands in front of it."""
    world(alcs)
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E17}-{sfx}", G5, RULING, adapter=Fake(), echo=lambda s: None, now=AT)


def test_a_no_shift_member_is_placed_by_clock(alcs):
    """26OCT192008CLETB is 0.0h from 50551: placed by clock (with 50551 SCHEDULED too: (a) needs no stored winner)."""
    _e17_by_hand(alcs)
    set_status(G6, "scheduled", clear=True)
    res, out = chain(dry_run=False)
    v = verdicts(res)
    assert v[f"{E17}-TB"] == f"counted: ruled on {G5}; the count's game agrees"
    assert v[f"{E19}-TB"] == "PLACE HOME by clock 0.0h"
    assert (placed_on(f"{E19}-TB"), placed_on(f"{E19}-CLE")) == ((G6, "HOME"), (G6, "AWAY"))
    assert rows()[f"{E19}-TB"]["notes"].endswith(f"; placed by ruling: {RULING}; placed by the chain of {E16} [2]: by "
                                                 f"clock 0.0h; candles read at placement on match {G6}'s kickoff")
    assert (f"    {E19}-TB · held, names {E16} out of step · result yes · winner not stored · settled 2026-10-20 "
            "03:30:00Z (+3.4h) · PLACE HOME by clock 0.0h") in out


def test_a_result_mismatch_refuses_under_a(alcs):
    """The clock passes (0.0h) but 50551 is stored as Cleveland's win while 26OCT192008CLETB's legs say Tampa Bay won:
    a result mismatch refuses under both checks."""
    _e17_by_hand(alcs)
    finish(G6, 1, 4)
    res, _ = chain()
    v = verdicts(res)
    assert v[f"{E19}-TB"] == "stays held: result yes, HOME lost; the chain stops"
    assert v[f"{E19}-CLE"] == "stays held: result no, AWAY won; the chain stops"
    assert not res["placed"]


def test_a_drawn_game_is_checked_under_a(alcs):
    """50551 stored as a draw (full_time_result D, 2-2: a soccer TIE, or a tie): the draw is the stored outcome, so
    Tampa Bay's leg that settled yes is a result mismatch under (a) too, and the event stays held on all its legs."""
    _e17_by_hand(alcs)
    finish(G6, 2, 2)
    res, _ = chain()
    v = verdicts(res)
    assert v[f"{E19}-TB"] == "stays held: result yes, the game was drawn; the chain stops"
    assert v[f"{E19}-CLE"] == "stays held: the event is placed on all its legs or on none; the chain stops"
    assert not res["placed"]


def test_a_drawn_game_never_places_under_b(alcs):
    """50548 stored as a draw and both of E17's legs settled no (they agree with the draw): (b) reads a stored winner,
    and a draw is not one, so E17 stays held (whether a draw counts is the architect's; the build holds)."""
    world(alcs)
    finish(G5, 3, 3)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", kalshi_result="no")
    res, out = chain()
    assert verdicts(res)[f"{E17}-TB"] == (
        f"stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: a draw stored for game {G5}, not a "
        "winner (the ruling's (b) reads a stored winner); the chain stops")
    assert any(ln.startswith(f"    {E17}-TB · ") and " · winner DRAW · " in ln for ln in out)
    assert not res["placed"]


@pytest.mark.parametrize("result, home, away, outcome", [
    ("D", 2, 2, "DRAW"), (None, 1, 1, "DRAW"), ("D", 2, 1, None), ("H", 1, 1, None), ("A", 0, 3, "AWAY")])
def test_the_stored_outcome_reads_a_draw(result, home, away, outcome):
    """_as_game: a stored D or level scores read as DRAW; a result and scores that disagree store none (law 4)."""
    from types import SimpleNamespace
    g = SimpleNamespace(id=1, utc_date=AT, status="finished", full_time_result=result, home_score=home,
                        away_score=away)
    assert kh._as_game(g).winner == outcome


def test_the_time_tie_holds_a_member(alcs):
    """A second unused game of the pair within 2h of the event's clock (the time tie): the clock does not tell the two
    apart; the settlement falls after the second one's kickoff, so the bracket does not either."""
    _e17_by_hand(alcs)
    seed({50552: (CLE, TB, datetime(2026, 10, 20, 1, 30), "scheduled")})
    res, out = chain()
    assert verdicts(res)[f"{E19}-TB"] == (
        "stays held: by clock: the clock also fits 50552 2026-10-19 21:30 ET; by settlement: settled 2026-10-20 "
        "03:30:00Z, not before the next game 50552's kickoff 2026-10-19 21:30 ET; the chain stops")
    assert not res["placed"]


@pytest.mark.parametrize("off, places", [(timedelta(hours=2), True), (timedelta(hours=2, minutes=1), False)],
                         ids=["2h0m-places", "2h1m-holds"])
def test_max_tick_drift_is_inclusive(alcs, off, places):
    """Q4: MAX_TICK_DRIFT is 2h inclusive. 50551 moved to 2h0m after 26OCT192008CLETB's clock (and SCHEDULED, so (b)
    cannot place it): placed by clock; at 2h1m it stays held."""
    _e17_by_hand(alcs)
    set_status(G6, "scheduled", clear=True)
    redate(G6, K6 + off)
    res, _ = chain()
    v = verdicts(res)[f"{E19}-TB"]
    if places:
        assert v == "PLACE HOME by clock 2.0h"
        assert [r["match_id"] for r in res["placed"]] == [G6, G6]
    else:
        assert v.startswith("stays held: by clock ") and v.endswith(" > 2.0h (MAX_TICK_DRIFT); by settlement: game "
                                                                    f"{G6} is scheduled, not finished; the chain stops")
        assert not res["placed"]


def test_the_time_tie_is_inclusive_at_2h(alcs):
    """A second unused game exactly 2h0m from the event's clock ties ("no other unused game within 2h", inclusive as
    MAX_TICK_DRIFT): the clock check fails, and the settlement falls after that game's kickoff, so the event stays
    held."""
    _e17_by_hand(alcs)
    seed({50552: (CLE, TB, K6 + timedelta(hours=2), "scheduled")})
    res, _ = chain()
    assert verdicts(res)[f"{E19}-TB"] == (
        "stays held: by clock: the clock also fits 50552 2026-10-19 22:08 ET; by settlement: settled 2026-10-20 "
        "03:30:00Z, not before the next game 50552's kickoff 2026-10-19 22:08 ET; the chain stops")
    assert not res["placed"]


def _m_before_game_6(alcs):
    """The anchor's match 50550 moved to 2026-10-19 23:08Z, 1h before 50551: a USED game of the list (used by the
    anchor) between 50548 and 50551."""
    world(alcs)
    redate(G4, datetime(2026, 10, 19, 23, 8))


def test_the_time_tie_counts_unused_games_only(alcs):
    """50550, used by the anchor, is 1h from 26OCT192008CLETB's clock: a used game is no time tie, so the member is
    placed on 50551 by clock (counting it would hold the clock check and leave the bracket to place it)."""
    _m_before_game_6(alcs)
    res, out = chain()
    v = verdicts(res)
    assert v[f"{E19}-TB"] == "PLACE HOME by clock 0.0h"
    assert v[f"{E17}-TB"] == f"PLACE AWAY by settlement +3.6h, before {G4} 2026-10-19 19:08 ET"
    assert out[2] == (f"  games after {E16}'s clock through 2026-10-27: {G5} 2026-10-18 17:08 ET finished; {G4} "
                      f"2026-10-19 19:08 ET finished [used by {E16}]; {G6} 2026-10-19 20:08 ET finished")


def test_the_next_game_bounds_the_bracket_used_or_not(alcs):
    """"The pair's next game in the list" is the next by kickoff, used or not: E17 settled at 23:30Z, after 50550's
    kickoff (used by the anchor) and before 50551's. Its settlement could be 50550's, so it stays held."""
    _m_before_game_6(alcs)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", settled_time=datetime(2026, 10, 19, 23, 30))
    res, _ = chain()
    assert verdicts(res)[f"{E17}-TB"] == ("stays held: by clock 21.1h > 2.0h (MAX_TICK_DRIFT); by settlement: settled "
                                          f"2026-10-19 23:30:00Z, not before the next game {G4}'s kickoff 2026-10-19 "
                                          "19:08 ET; the chain stops")
    assert not res["placed"]


def test_a_live_target_stays_held(alcs):
    _e17_by_hand(alcs)
    set_status(G6, "live")
    res, _ = chain()
    assert verdicts(res)[f"{E19}-TB"] == f"stays held: game {G6} is live; the chain stops"


# ---- the count -------------------------------------------------------------------------------------------------------

def test_a_chain_with_no_member_prints_and_exits_0(alcs, tmp_path, monkeypatch):
    """Once E17 and Game 6's event are placed by hand, no held row names E16: the run prints the counted events, each
    on its own match and the count's game, and writes nothing (never a refusal)."""
    import cli
    _e17_by_hand(alcs)
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E19}-{sfx}", G6, RULING, adapter=Fake(), echo=lambda s: None, now=AT)
    before = rows()
    res, out = chain(dry_run=False, guard=lambda: (_ for _ in ()).throw(AssertionError("no guard: nothing to write")))
    v = verdicts(res)
    assert v[f"{E17}-TB"] == f"counted: ruled on {G5}; the count's game agrees"
    assert v[f"{E19}-CLE"] == f"counted: ruled on {G6}; the count's game agrees"
    assert out[-1] == ("  chain: 2 event(s) · 0 member(s) · 0 row(s) to place · 0 stay held · games no event took: none "
                       "· calls 0 of 3 · nothing to place: nothing written")
    assert rows() == before and not res["written"]
    fake = Fake()
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake._get(path, params))
    r = CliRunner().invoke(cli.cli, ["kalshi-history", "place-chain", "--anchor", E16, "--ruling", RULING, "--dry-run"])
    assert r.exit_code == 0, r.output
    assert f"counted: ruled on {G5}; the count's game agrees" in r.output and not fake.calls


def test_the_list_runs_from_the_anchor_s_clock_so_a_later_makeup_leaves_each_member_its_game(db):
    """Q1 ("after A's ticker clock, M used by A: yes"): A (09-01) rained out and ruled onto its makeup 60005, played
    09-05, after its members' own games. The list runs from A's clock, not from M's kickoff, so E2 (09-02) and E3
    (09-03) each take their own game by clock."""
    d2, d3, mk = datetime(2026, 9, 2, 23, 10), datetime(2026, 9, 3, 17, 10), datetime(2026, 9, 5, 23, 10)
    seed({60001: (TB, CLE, datetime(2026, 9, 1, 23, 10), "postponed"), 60002: (TB, CLE, d2, "finished"),
          60003: (TB, CLE, d3, "finished"), 60005: (TB, CLE, mk, "finished")})
    e1, e2, e3 = f"{S}-26SEP011910TBCLE", f"{S}-26SEP021910TBCLE", f"{S}-26SEP031310TBCLE"
    finish(60002, 1, 4)
    finish(60003, 5, 2)
    finish(60005, 0, 3)
    go(Fake(settled=event(e1, "yes", "2026-09-06T02:50:00Z", "2026-09-06T03:00:00Z")
            + event(e2, "yes", "2026-09-03T02:50:00Z", "2026-09-03T03:00:00Z")
            + event(e3, "no", "2026-09-03T20:20:00Z", "2026-09-03T20:30:00Z")), now=datetime(2026, 9, 7, 12))
    assert all(r["notes"].startswith(hold(e1, "out of step")) for t, r in rows().items() if t.startswith((e2, e3)))
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{e1}-{sfx}", 60005, RULING, adapter=Fake(), echo=lambda s: None, now=datetime(2026, 9, 7, 13))
    res, out = chain(anchor=e1, fake=Fake(candles={f"{e}-{x}": candles_at(k) for e, k in ((e2, d2), (e3, d3))
                                                   for x in ("TB", "CLE")}))
    v = verdicts(res)
    assert (v[f"{e2}-TB"], v[f"{e3}-CLE"]) == ("PLACE AWAY by clock 0.0h", "PLACE HOME by clock 0.0h")
    assert [(r["ticker"], r["match_id"]) for r in res["placed"]] == [
        (f"{e2}-CLE", 60002), (f"{e2}-TB", 60002), (f"{e3}-CLE", 60003), (f"{e3}-TB", 60003)]
    assert out[2] == (f"  games after {e1}'s clock through 2026-09-12: 60002 2026-09-02 19:10 ET finished; 60003 "
                      f"2026-09-03 13:10 ET finished; 60005 2026-09-05 19:10 ET finished [used by {e1}]")


@pytest.mark.parametrize("club, how", [
    (TB, "merge-teams first"),
    ("Tampa Bay Devil Rays", "another club's game fits the names (a namesake): rule the events by place-held")],
    ids=["a-second-row-of-one-club", "a-namesake-club"])
def test_a_second_team_row_of_one_club_in_the_list_refuses(alcs, club, how):
    """Game 6 stored under a second "Tampa Bay Rays" team row (team rows are keyed by provider; merge-teams exists for
    this), and E17 settled after Game 6's kickoff (its settlement could be Game 6's). The list is the games the
    anchor's two names fit one each (the design's section 2, kalshi_match.fit), so Game 6 is in it, and the fitted
    games are of two pairs of teams: the command refuses, as the matcher refuses PAIR_TIE, before any call and with
    nothing written. (By M's team ids Game 6 would be left out, and E17 placed on 50548 with no next game.)"""
    from src.db.database import session_scope
    from src.db.schema import Match, Sport, Team
    seed({G6: (CLE, TB, K6, "scheduled")})
    with session_scope() as s:
        dup = Team(sport=Sport["MLB"], name=club)
        s.add(dup)
        s.flush()
        s.get(Match, G6).home_team_id = dup.id
        tb, cle = s.get(Match, G4).away_team_id, s.get(Match, G4).home_team_id
        pairs = {tuple(sorted((tb, cle))): f"{G4} {TB} at {CLE}, {G5} {TB} at {CLE}",
                 tuple(sorted((cle, dup.id))): f"{G6} {CLE} at {club}"}
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED19))
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E16}-{sfx}", G4, RULING, adapter=Fake(), echo=lambda s: None, now=datetime(2026, 10, 19, 15))
    finish(G5, 2, 5)
    finish(G6, 4, 1)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", settled_time=datetime(2026, 10, 20, 1, 0))
    before, fake = rows(), Fake(candles=CAND)
    with pytest.raises(ValueError) as e:
        chain(dry_run=False, fake=fake)
    assert str(e.value) == ("REFUSED: the games the names Cleveland / Tampa Bay fit one each (kalshi_match.fit: match "
                            f"{G4}, the anchor's, and the list from its clock through 2026-10-27) are of 2 pairs of "
                            "teams (" + "; ".join(f"teams {a}/{b}: {gs}" for (a, b), gs in sorted(pairs.items()))
                            + f"): the matcher refuses such an event ({km.PAIR_TIE}); {how}; nothing is placed")
    assert rows() == before and not fake.calls
    assert placed_on(f"{E17}-TB") == (None, None)


def test_two_rows_on_one_side_of_one_game_refuse(alcs):
    """A member with a third held leg whose yes team repeats one of its two names (-TB2, Tampa Bay): -TB and -TB2 would
    both take 50548 AWAY. The write's own clash read does not see the first row's side in the same transaction, so the
    plan refuses: nothing read, nothing written."""
    world(alcs)
    r = rows()[f"{E17}-TB"]
    add(E17, "Tampa Bay", "TB2", notes=r["notes"], kalshi_result="yes", settled_time=r["settled_time"],
        close_time=r["close_time"])
    before, fake = rows(), Fake(candles=dict(CAND, **{f"{E17}-TB2": CAND[f"{E17}-TB"]}))
    with pytest.raises(ValueError) as e:
        chain(dry_run=False, fake=fake)
    assert str(e.value) == (f"REFUSED: match {G5} AWAY would be taken by 2 rows ({E17}-TB, {E17}-TB2): two settled "
                            "markets are never stored on one side of one game; nothing is placed")
    assert rows() == before and not fake.calls


def test_a_counted_event_off_the_count_s_game_stops_the_chain(alcs):
    """Q10: E17 ruled by hand onto 50551 (not the count's game, 50548): the chain stops there (law 4)."""
    world(alcs)
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E17}-{sfx}", G6, RULING, adapter=Fake(), echo=lambda s: None, now=AT)
    res, _ = chain()
    v = verdicts(res)
    assert v[f"{E17}-TB"] == f"counted: ruled on {G6}; the count's game is {G5}: the chain stops"
    assert v[f"{E19}-TB"] == "stays held: the chain stopped at [1]"
    assert not res["placed"]


def test_a_claimed_game_is_skipped_and_the_member_takes_the_next(alcs):
    """A game a stored row outside the chain holds is used by its holder. Here 26OCT181708TBCLE is IN STEP, placed by the
    ingest on 50548: it ENDs the chain, and 50548 is used by it, so E17's count's game is 50551, which neither check
    passes (48.1h; settled before 50551's kickoff): E17 stays held. Game 6's event, after the END, is not read."""
    world(alcs)
    e18 = f"{S}-26OCT181708TBCLE"
    add(e18, "Tampa Bay", "TB", match_id=G5, side="AWAY", kalshi_result="yes")
    add(e18, "Cleveland", "CLE", match_id=G5, side="HOME", kalshi_result="no")
    res, out = chain()
    assert f" {G5} 2026-10-18 17:08 ET finished [used by {e18}];" in out[2]
    assert f"  [1] {E17} · clock 2026-10-17 20:00 ET · count's game {G6} 2026-10-19 20:08 ET finished · 48.1h" in out
    assert verdicts(res)[f"{E17}-TB"] == ("stays held: by clock 48.1h > 2.0h (MAX_TICK_DRIFT); by settlement: settled "
                                          f"2026-10-19 00:45:00Z, not after game {G6}'s kickoff; the chain stops")
    assert f"  [2] {e18} · clock 2026-10-18 17:08 ET · END: in step (placed by the ingest on {G5})" in out
    assert f"  held rows naming {E16} outside the chain: {E19}-CLE, {E19}-TB (after the END at [2])" in out
    assert not res["placed"]


def test_a_side_another_chain_event_holds_keeps_the_member_held(alcs):
    """One event per game: E18, later in the chain and ruled by hand onto 50548, holds both its sides; E17, whose count's
    game is 50548, stays held on place-held's own refusal, and the chain stops."""
    world(alcs)
    e18 = f"{S}-26OCT181708TBCLE"
    add(e18, "Tampa Bay", "TB", match_id=G5, side="AWAY", notes=f"placed by ruling: {RULING}")
    add(e18, "Cleveland", "CLE", match_id=G5, side="HOME", notes=f"placed by ruling: {RULING}")
    res, _ = chain()
    assert verdicts(res)[f"{E17}-TB"] == (f"stays held: match {G5} AWAY is already held by {e18}-TB: two settled markets "
                                          "are never stored on one side of one game; the chain stops")
    assert not res["placed"]


# ---- the chain's ends ------------------------------------------------------------------------------------------------

def test_day_11_is_past_n1(alcs):
    """N1: only events 1-10 days after the anchor. A held row naming E16, eleven days on, is not read and is listed."""
    world(alcs)
    e27 = f"{S}-26OCT271800TBCLE"
    note = f"{hold(E16, 'out of step')}; {kh.HOLD_NO_CANDLES}"
    add(e27, "Tampa Bay", "TB", notes=note, kalshi_result="yes")
    add(e27, "Cleveland", "CLE", notes=note, kalshi_result="no")
    res, out = chain()
    assert {ev["event"] for ev in res["plan"]["events"]} == {E17, E19}
    assert f"  held rows naming {E16} outside the chain: {e27}-CLE, {e27}-TB (11 days after {E16}: past N1's 10)" in out
    assert len(res["placed"]) == 4 and not any(r["ticker"].startswith(e27) for r in res["placed"])


def test_day_10_is_inside_n1(alcs):
    """N1's edge: an event ten days after the anchor (10-26) is a chain event; its own game that evening places it by
    clock."""
    world(alcs)
    e26 = f"{S}-26OCT261800TBCLE"
    seed({50560: (TB, CLE, datetime(2026, 10, 26, 22, 0), "scheduled")})
    note = f"{hold(E16, 'out of step')}; {kh.HOLD_NO_CANDLES}"
    add(e26, "Tampa Bay", "TB", notes=note, kalshi_result="yes")
    add(e26, "Cleveland", "CLE", notes=note, kalshi_result="no")
    res, _ = chain()
    assert [ev["event"] for ev in res["plan"]["events"]] == [E17, E19, e26]
    assert verdicts(res)[f"{e26}-TB"] == "PLACE AWAY by clock 0.0h"
    assert [r["match_id"] for r in res["placed"]][-2:] == [50560, 50560]


def test_mixed_legs_end_the_chain(alcs):
    world(alcs)
    edit(f"{E17}-CLE", notes=f"refused by the matcher: {km.NO_GAME_ON_DATE}")
    res, out = chain()
    assert not res["plan"]["events"] and not res["placed"]
    assert f"  [1] {E17} · clock 2026-10-17 20:00 ET · END: mixed legs (held, refused)" in out
    assert any(ln.startswith(f"    {E17}-CLE · refused: {km.NO_GAME_ON_DATE} · ") and ln.endswith("END: mixed legs "
                                                                                                "(held, refused)")
               for ln in out)
    assert f"  held rows naming {E16} outside the chain: {E17}-TB (the END at [1]: mixed legs (held, refused)); " \
           f"{E19}-CLE, {E19}-TB (after the END at [1])" in out


def test_a_twin_on_the_anchor_s_date_is_read_and_ends_the_chain(alcs):
    """An event after the anchor on its own date (a doubleheader twin) is next in chain order; refused by the matcher
    (no game of the pair on 10-16), it ENDs the chain (Q6), and nothing after it is placed."""
    world(alcs)
    twin = f"{S}-26OCT162010TBCLE"
    for sfx, nm in (("TB", "Tampa Bay"), ("CLE", "Cleveland")):
        add(twin, nm, sfx, notes=f"refused by the matcher: {km.NO_GAME_ON_DATE}")
    res, out = chain()
    assert f"  [1] {twin} · clock 2026-10-16 20:10 ET · END: refused: {km.NO_GAME_ON_DATE}" in out
    assert not res["placed"] and res["plan"]["end"][1] == twin


def test_an_unsettled_note_naming_the_anchor_ends_the_chain_and_is_listed(alcs):
    """Q7: a member's hold reason is "out of step" only. E17 held naming E16 "unsettled" (a stale note: a row held again
    keeps its note) ENDs the chain and stays held, listed."""
    world(alcs)
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", notes=f"{hold(E16, 'unsettled')}; {kh.HOLD_NO_CANDLES}")
    res, out = chain()
    assert f"  [1] {E17} · clock 2026-10-17 20:00 ET · END: names {E16} unsettled" in out
    assert f"  held rows naming {E16} outside the chain: {E17}-CLE, {E17}-TB (the END at [1]: names {E16} " \
           f"unsettled); {E19}-CLE, {E19}-TB (after the END at [1])" in out
    assert not res["placed"]


def test_held_behind_another_event_ends_the_chain(alcs):
    world(alcs)
    other = f"{S}-26OCT151800TBCLE"
    for sfx in ("TB", "CLE"):
        edit(f"{E17}-{sfx}", notes=f"{hold(other, 'out of step')}; {kh.HOLD_NO_CANDLES}")
    res, out = chain()
    assert f"  [1] {E17} · clock 2026-10-17 20:00 ET · END: held behind {other} (out of step)" in out
    assert not res["placed"]


# ---- refusals: exit 2, nothing written -------------------------------------------------------------------------------

def _two_matches(alcs):
    world(alcs)
    edit(f"{E16}-CLE", match_id=G5)


def _no_ruling(alcs):
    world(alcs)
    edit(f"{E16}-CLE", match_id=None, side=None, notes=f"refused by the matcher: {km.NO_GAME_ON_DATE}")


def _in_step(alcs):
    world(alcs)
    seed({50547: (TB, CLE, datetime(2026, 10, 16, 22, 0), "finished")})   # a game of the pair on 10-16 after all


def _not_a_game(alcs):
    world(alcs)
    set_status(G4, "postponed")


def _one_minute(alcs):
    world(alcs)
    seed({50553: (TB, CLE, K5, "scheduled")})


@pytest.mark.parametrize("setup, anchor, ruling, msg", [
    (world, E16, "   ", "REFUSED: --ruling is empty"),
    (world, f"{S}-26OCT201600TBCLE", RULING, f"REFUSED: no row of kalshi_settled_markets is of event '{S}-26OCT201600TBCLE'"),
    (_no_ruling, E16, RULING, f"REFUSED: {E16} is not placed by ruling on every row ({E16}-CLE: refused: "),
    (_two_matches, E16, RULING, f"REFUSED: the rows of {E16} are ruled on 2 matches ({G5}, {G4})"),
    (world, E16, "ARCHITECT 2026-10-20, addendum 148 item 2", f"REFUSED: {E16}-CLE does not carry 'placed by ruling: "
                                                              f"ARCHITECT 2026-10-20, addendum 148 item 2' (its ruling: "
                                                              f"{RULING})"),
    (_in_step, E16, RULING, f"REFUSED: {E16} is not out of step on its own date"),
    (_not_a_game, E16, RULING, f"REFUSED: match {G4}, the anchor's, is postponed: not a game"),
    (_one_minute, E16, RULING, f"REFUSED: rows {G5}, 50553 share one kickoff minute: dedupe-matches has to merge them"),
], ids=["empty-ruling", "no-anchor-row", "anchor-not-ruled", "two-matches", "other-ruling", "anchor-in-step",
        "anchor-match-not-a-game", "one-kickoff-minute"])
def test_place_chain_refuses(alcs, setup, anchor, ruling, msg):
    setup(alcs)
    before = rows()
    fake = Fake(candles=CAND)
    with pytest.raises(ValueError) as e:
        chain(fake=fake, anchor=anchor, ruling=ruling)
    assert str(e.value).startswith(msg), str(e.value)
    assert rows() == before and not fake.calls


def test_a_candle_call_that_fails_for_now_on_row_2_writes_nothing(alcs):
    """All or nothing (addendum 132 item 3(a), extended to the chain): the first row's candles are read, the second's
    call fails for now (a 503): nothing of the chain is written, and the refusal names the call."""
    before = world(alcs)
    fake = Fake(candles=CAND, fail={f"{E17}-TB": 503})
    with pytest.raises(ValueError) as e:
        chain(dry_run=False, fake=fake)
    assert str(e.value).startswith(f"REFUSED: the candle call series/{S}/markets/{E17}-TB/candlesticks failed (status "
                                   "503; 429 retries: 0): nothing is written")
    assert rows() == before
    assert [p for p, _ in fake.calls][:2] == ["historical/cutoff", f"series/{S}/markets/{E17}-CLE/candlesticks"]


def test_the_write_reads_each_row_again_as_a_held_row_and_its_side(alcs):
    """Between the plan and the write: a row of the chain placed meanwhile (no longer held), or a side taken by another
    row of the series: the one transaction refuses and nothing of the chain is written."""
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    before = world(alcs)

    class Placed(Fake):
        def _get(self, path, params=None):
            if path.endswith(f"/{E19}-TB/candlesticks"):
                edit(f"{E19}-CLE", match_id=G6, side="AWAY", notes="placed meanwhile")
            return super()._get(path, params)
    with pytest.raises(ValueError, match=f"REFUSED: {E19}-CLE changed before the write \\(no longer a held row"):
        chain(dry_run=False, fake=Placed(candles=CAND))
    after = rows()
    assert {t: r for t, r in after.items() if t != f"{E19}-CLE"} == {t: r for t, r in before.items()
                                                                       if t != f"{E19}-CLE"}
    edit(f"{E19}-CLE", match_id=None, side=None, notes=before[f"{E19}-CLE"]["notes"])

    class Taken(Fake):
        def _get(self, path, params=None):
            if path.endswith(f"/{E19}-TB/candlesticks"):
                with session_scope() as s:
                    s.add(KalshiSettledMarket(ticker=f"{S}-26OCT191900CLETB-TB", event_ticker=f"{S}-26OCT191900CLETB",
                                              series=S, side="HOME", match_id=G6, yes_sub_title="Tampa Bay",
                                              source="live", fetched_at=NOW, notes="placed by ruling: test"))
            return super()._get(path, params)
    with pytest.raises(ValueError, match=f"REFUSED: match {G6} HOME was taken by {S}-26OCT191900CLETB-TB before the "
                                         "write"):
        chain(dry_run=False, fake=Taken(candles=CAND))
    assert {t: r for t, r in rows().items() if t.startswith((E17, E19))} == {t: r for t, r in before.items()
                                                                             if t.startswith((E17, E19))}


def test_the_notes_cap_refuses_before_anything_is_read(alcs):
    """The 2000-character cap (place-held's, KH): a ruling long enough that the anchor's notes fit and a member's,
    with the chain's part, would not: refused, nothing read, nothing written."""
    seed({G6: (CLE, TB, K6, "scheduled")})
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED19))
    n16 = max(len(r["notes"]) for t, r in rows().items() if t.startswith(E16))
    long = "R" * (2000 - 200 - n16 - len("; placed by ruling: "))
    for sfx in ("TB", "CLE"):
        kh.place_held(f"{E16}-{sfx}", G4, long, adapter=Fake(), echo=lambda s: None, now=AT)
    finish(G5, 2, 5)
    before, fake = rows(), Fake(candles=CAND)
    with pytest.raises(ValueError, match=f"REFUSED: the notes of {E17}-CLE would pass the column's 2000 characters"):
        chain(dry_run=False, fake=fake, ruling=long)
    assert rows() == before and not fake.calls


# ---- the listing -----------------------------------------------------------------------------------------------------

def test_the_listing_makes_no_network_call_and_writes_nothing(alcs):
    from src.db.database import get_engine
    world(alcs)
    eng = get_engine()
    with eng.connect() as c:
        n0 = c.execute(text("SELECT COUNT(*) FROM kalshi_settled_markets")).scalar()

    class NoNetwork(Fake):
        def _get(self, path, params=None):
            self.calls.append((path, params))     # recorded: Calls.get would swallow the raise below
            raise AssertionError(f"the listing called {path}")
    before, out, fake = rows(), [], NoNetwork()
    got = kh.list_chains(S, adapter=fake, echo=out.append)
    assert rows() == before and not fake.calls
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM kalshi_settled_markets")).scalar() == n0
    assert got == {"held_rows": 4, "held_events": 2, "named": {E16: "ruled"}}
    assert out[0] == f"kalshi-history place-chain --list {S} (MLB) · READ-ONLY: no network call, nothing written"
    assert out[1] == (f"  E0 {E16} · clock 2026-10-16 18:00 ET · ruled on {G4} ({E16}-CLE HOME, {E16}-TB AWAY) · placed "
                      f"by ruling: {RULING}")
    assert out[2] == (f"    held {E17} · clock 2026-10-17 20:00 ET · {E17}-CLE out of step result no settled 2026-10-19 "
                      f"00:45:00Z; {E17}-TB out of step result yes settled 2026-10-19 00:45:00Z")
    assert out[3] == (f"      the pair's games on its day: {G4} 2026-10-17 20:08 ET finished (+0.1h) · held by {E16}; "
                      f"{G5} 2026-10-18 17:08 ET finished (+21.1h)")
    assert out[-1] == ("  held rows: 4 in 2 event(s) · events they name: 1 (refused 0, ruled 1, placed 0, held 0, mixed "
                       "0, not stored 0) · READ-ONLY: nothing written")


def test_the_listing_names_a_refused_anchor_before_it_is_ruled(alcs):
    """Before place-held: the event the held rows name is refused (no game of the pair on its date): the listing is
    the read the anchor is ruled from."""
    seed({G6: (CLE, TB, K6, "scheduled")})
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED19))
    out = []
    got = kh.list_chains(S, adapter=Fake(), echo=out.append)
    assert got["named"] == {E16: "refused"}
    assert out[1] == f"  E0 {E16} · clock 2026-10-16 18:00 ET · refused: {km.NO_GAME_ON_DATE}"


# ---- the command -----------------------------------------------------------------------------------------------------

def test_the_command_needs_a_backup_to_write_and_takes_one(alcs, tmp_path, monkeypatch):
    import cli
    world(alcs)
    fake = Fake(candles=CAND)
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake._get(path, params))
    args = ["kalshi-history", "place-chain", "--anchor", E16, "--ruling", RULING]
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2 and "REFUSED [check: --backup given]" in res.output and not fake.calls
    dry = CliRunner().invoke(cli.cli, args + ["--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert dry.output.splitlines()[-1].endswith("DRY RUN: nothing written") and rows()[f"{E17}-TB"]["match_id"] is None
    good = _backup(str(alcs), str(tmp_path / "good.backup"))
    res = CliRunner().invoke(cli.cli, args + ["--backup", good])
    assert res.exit_code == 0, res.output
    assert "backup verified:" in res.output and "✓ written: 4 row(s) of kalshi_settled_markets" in res.output
    assert placed_on(f"{E17}-TB") == (G5, "AWAY")
    # a refusal: exit 2, its one line (the anchor's rows carry another ruling)
    bad = CliRunner().invoke(cli.cli, ["kalshi-history", "place-chain", "--anchor", E16, "--ruling", "other",
                                       "--dry-run"])
    assert bad.exit_code == 2 and bad.output.startswith(f"REFUSED: {E16}-CLE does not carry 'placed by ruling: other'")


def test_the_command_s_options(alcs, monkeypatch):
    import cli
    world(alcs)
    fake = Fake()
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake._get(path, params))
    run = CliRunner().invoke
    ok = run(cli.cli, ["kalshi-history", "place-chain", "--list", "--series", S])
    assert ok.exit_code == 0, ok.output
    assert ok.output.splitlines()[0].startswith(f"kalshi-history place-chain --list {S} (MLB) · READ-ONLY") and \
        not fake.calls
    for extra, words in ((["--list", "--series", S, "--anchor", E16], "--anchor do not go with --list"),
                         (["--list", "--series", S, "--dry-run"], "--dry-run do not go with --list"),
                         (["--list"], "--list needs --series S"),
                         (["--anchor", E16, "--ruling", RULING, "--series", S, "--dry-run"],
                          "--series goes with --list only"),
                         (["--anchor", E16, "--dry-run"], "place-chain needs --anchor EVENT and --ruling")):
        bad = run(cli.cli, ["kalshi-history", "place-chain", *extra])
        assert bad.exit_code == 2 and words in bad.output, (extra, bad.output)
    unknown = run(cli.cli, ["kalshi-history", "place-chain", "--list", "--series", "KXNOPE"])
    assert unknown.exit_code == 2 and "REFUSED: KXNOPE is not a series the syncs read" in unknown.output
    pulled = run(cli.cli, ["kalshi-history", "--series", S, "place-chain", "--list", "--series", S])
    assert pulled.exit_code == 2 and "--series belong to the pull" in pulled.output


# ---- place-held unchanged --------------------------------------------------------------------------------------------

def test_place_held_is_unchanged(alcs):
    """place-held's console and write, line for line as before the chain (its own tests stand in
    tests/test_kalshi_history_identity_hold.py): one row written, nothing else."""
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17))
    before, out = rows(), []
    res = kh.place_held(f"{E16}-TB", G4, RULING, adapter=Fake(candles={f"{E16}-TB": candles_at(K4)}), echo=out.append,
                        now=datetime(2026, 10, 18, 15, 0))
    assert res["written"]
    b = before[f"{E16}-TB"]
    assert out == [
        f"kalshi-history place-held {E16}-TB → match {G4} · writes this one row of kalshi_settled_markets · ruling: "
        f"{RULING}",
        f"  before: {kh.row_line(b)}",
        f"  match {G4}: {TB} at {CLE} · kickoff 2026-10-18 00:08Z (2026-10-17 20:08 ET) · finished · the event's names "
        "Tampa Bay / Cleveland fit it one each: Tampa Bay is AWAY",
        "  cutoff market_settled_ts: 2026-08-15T00:00:00Z · settled 2026-10-18 03:20:00Z · candles from live",
        f"  candles: series/{S}/markets/{E16}-TB/candlesticks from 2026-10-17 18:08Z to 2026-10-18 03:18Z: 5 candle(s) · "
        "429 retries: 0",
        f"  after:  {kh.row_line(res['after'])}",
        f"  ✓ placed: {E16}-TB on match {G4} AWAY (one row written)"]
    assert res["after"]["notes"] == f"{b['notes']}; placed by ruling: {RULING}; candles read at placement on match " \
                                    f"{G4}'s kickoff"
    got = rows()
    assert {t: r for t, r in got.items() if t != f"{E16}-TB"} == {t: r for t, r in before.items() if t != f"{E16}-TB"}
    with pytest.raises(ValueError, match=f"REFUSED: {E16}-TB is already placed on match {G4} AWAY"):
        kh.place_held(f"{E16}-TB", G4, RULING, adapter=Fake(), echo=out.append)
