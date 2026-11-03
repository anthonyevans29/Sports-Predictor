"""#413's receipt (ARCHITECT 2026-11-03, addendum 230 item 0(a)): scripts/kalshi_pair_receipt.py, read-only.

The world is synthetic, in the shape of the laptop's college store of 2026-10-10 (addendum 44 item 2's receipt): the
wrong legs as the yes-team fallback stored them (32749 Duke @ Georgia Tech HOME from 26OCT10UGAALA-UGA, 32810 Florida
A&M @ Alabama State HOME from 26OCT10UGAALA-ALA, 32763 Rice @ East Carolina HOME from 26OCT10SCSTCHSO-SCST, 32747
Houston @ Kansas State HOME from 26OCT10KUUTAH-KU) beside right ones, the settled siblings kalshi-history keeps, a
throwaway SQLite copied by the .backup API (the copy the script reads). Pins: BEFORE prints each stored leg on the game
it sits on; AFTER places the UGAALA split and SCSTCHSO on their own games by both names and calls the stored legs on
other games what they are; an event with no settled row is "pair not formable from the store: refused"; an event whose
store names one team is refused by the matcher's own reason; the copy is unchanged, no sidecar is made; the refusals.
"""
import importlib.util
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("kalshi_pair_receipt", ROOT / "scripts" / "kalshi_pair_receipt.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

Z = datetime.fromisoformat
EV = "KXNCAAFGAME-26OCT10"
GAMES = (   # id, away, home, our kickoff (naive UTC)
    (32749, "Duke", "Georgia Tech", Z("2026-10-10T16:00")),
    (32763, "Rice", "East Carolina", Z("2026-10-10T16:00")),
    (32810, "Florida A&M", "Alabama State", Z("2026-10-09T16:00")),      # the storm move, ticker still 26OCT10
    (32738, "Georgia", "Alabama", Z("2026-10-10T23:30")),
    (32817, "South Carolina State", "Charleston Southern", Z("2026-10-10T16:00")),
    (32747, "Houston", "Kansas State", Z("2026-10-10T19:30")),
    (32748, "Kansas", "Utah", Z("2026-10-11T02:15")),
    (32823, "Bethune-Cookman", "Alabama A&M", Z("2026-10-10T17:00")),
)
LEGS = (    # match id, selection, ticker, capture
    (32749, "HOME", f"{EV}UGAALA-UGA", "2026-10-10 11:52:09.000000"),
    (32810, "HOME", f"{EV}UGAALA-ALA", "2026-10-08 21:56:38.000000"),
    (32763, "HOME", f"{EV}SCSTCHSO-SCST", "2026-10-10 11:52:09.000000"),
    (32817, "AWAY", f"{EV}SCSTCHSO-SCST", "2026-10-09 22:09:52.000000"),
    (32817, "HOME", f"{EV}SCSTCHSO-CHSO", "2026-10-09 22:09:52.000000"),
    (32747, "HOME", f"{EV}KUUTAH-KU", "2026-10-08 21:56:38.000000"),
    (32747, "HOME", f"{EV}KUUTAH-KU", "2026-10-10 11:52:09.000000"),
    (32747, "AWAY", f"{EV}HOUKSU-HOU", "2026-10-10 11:52:09.000000"),
    (32823, "HOME", f"{EV}COOKAAMU-AAMU", "2026-10-10 11:52:09.000000"),
)
SETTLED = (  # ticker, yes_sub_title, kalshi-history's match_id, side, notes
    (f"{EV}UGAALA-UGA", "Georgia", 32738, "AWAY", None),
    (f"{EV}UGAALA-ALA", "Alabama", 32738, "HOME", None),
    (f"{EV}SCSTCHSO-SCST", "South Carolina St.", 32817, "AWAY", None),
    (f"{EV}SCSTCHSO-CHSO", "Charleston Southern", 32817, "HOME", None),
    (f"{EV}HOUKSU-HOU", "Houston", 32747, "AWAY", None),
    (f"{EV}HOUKSU-KSU", "Kansas St.", 32747, "HOME", None),
    (f"{EV}COOKAAMU-AAMU", "Alabama A&M", None, None,
     "refused by the matcher: the event's markets do not name two teams"),         # its sibling never settled here
)


def _world(path: Path, settled=True, ticker_column=True):
    from src.db.schema import Base, Competition, KalshiSettledMarket, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    if ticker_column:
        with eng.begin() as c:
            c.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR"))
    with Session(eng) as s:
        c = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        s.add(c)
        s.flush()
        for mid, away, home, ko in GAMES:
            h, a = Team(sport=Sport.NFL, name=home), Team(sport=Sport.NFL, name=away)
            s.add_all([h, a])
            s.flush()
            s.add(Match(id=mid, sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=ko,
                        status=MatchStatus.FINISHED if ko < Z("2026-10-10T00:00") else MatchStatus.SCHEDULED,
                        home_team_id=h.id, away_team_id=a.id))
        if settled:
            for t, yst, mid, side, notes in SETTLED:
                s.add(KalshiSettledMarket(ticker=t, event_ticker=t.rsplit("-", 1)[0], series="KXNCAAFGAME",
                                          side=side, match_id=mid, yes_sub_title=yst, source="historical",
                                          fetched_at=Z("2026-10-15T12:00"), notes=notes))
        s.commit()
    with eng.begin() as con:
        for i, (mid, sel, tic, cap) in enumerate(LEGS, start=1):
            con.execute(text("INSERT INTO odds_snapshots (id, match_id, market, selection, devig_prob, n_books, "
                             "captured_at, source" + (", market_ticker" if ticker_column else "") + ") VALUES "
                             "(:i, :m, 'ML', :s, 0.5, 1, :c, 'kalshi'" + (", :t" if ticker_column else "") + ")"),
                        {"i": i, "m": mid, "s": sel, "c": cap, "t": tic})
    eng.dispose()


def _backup(src: Path, dst: Path) -> Path:
    """A .backup-API copy (sqlite3's online backup), as the operator's block takes it."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    a.backup(b)
    b.close()
    a.close()
    return dst


@pytest.fixture
def copy(tmp_path):
    _world(tmp_path / "world.db")
    return _backup(tmp_path / "world.db", tmp_path / "copy" / "sports.db")


def _run(capsys, *args):
    rc = script.main([str(a) for a in args])
    return rc, capsys.readouterr().out.splitlines()


def _block(out, ev):
    i = out.index(next(ln for ln in out if ln.startswith(f"EVENT {EV}{ev}")))
    j = next((k for k in range(i + 1, len(out)) if out[k].startswith("EVENT ") or out[k] == ""), len(out))
    return out[i:j]


def _summary(out):
    last = out[-1]
    assert last.startswith("KALSHI-PAIR-RECEIPT ")
    return json.loads(last[len("KALSHI-PAIR-RECEIPT "):])


def test_the_ugaala_split_before_and_after(copy, capsys):
    rc, out = _run(capsys, "--db", copy)
    assert rc == 0, out
    b = _block(out, "UGAALA")
    assert b[0] == f"EVENT {EV}UGAALA · SPLIT: its stored legs sit on 2 games"
    assert (f"    HOME {EV}UGAALA-UGA on match 32749 (Duke @ Georgia Tech · our kickoff 2026-10-10 16:00Z) · "
            "1 capture(s) 2026-10-10 11:52:09 .. 2026-10-10 11:52:09") in b, b
    assert any(ln.startswith(f"    HOME {EV}UGAALA-ALA on match 32810 (Florida A&M @ Alabama State") for ln in b), b
    assert "    the store's names: Georgia / Alabama" in b
    assert (f"    {EV}UGAALA-UGA (Georgia): placed on match 32738 AWAY (Georgia @ Alabama · our kickoff 2026-10-10 "
            "23:30Z) · kalshi-history stored: match 32738 AWAY") in b, b
    assert (f"    HOME {EV}UGAALA-UGA on match 32749: "
            "stored on ANOTHER game: placed on match 32738 AWAY on both names") in b
    assert (f"    HOME {EV}UGAALA-ALA on match 32810: "
            "stored on ANOTHER game: placed on match 32738 HOME on both names") in b


def test_32763_and_the_own_legs_of_scstchso(copy, capsys):
    rc, out = _run(capsys, "--db", copy)
    b = _block(out, "SCSTCHSO")
    assert b[0] == f"EVENT {EV}SCSTCHSO · SPLIT: its stored legs sit on 2 games"
    assert (f"    HOME {EV}SCSTCHSO-SCST on match 32763: "
            "stored on ANOTHER game: placed on match 32817 AWAY on both names") in b
    assert (f"    AWAY {EV}SCSTCHSO-SCST on match 32817: "
            "stored on its own game: placed here on both names") in b
    assert (f"    HOME {EV}SCSTCHSO-CHSO on match 32817: "
            "stored on its own game: placed here on both names") in b


def test_an_event_with_no_settled_row_is_not_formable_and_one_name_is_refused(copy, capsys):
    rc, out = _run(capsys, "--db", copy)
    k = _block(out, "KUUTAH")
    assert "    no settled row of this event: pair not formable from the store: refused" in k
    assert f"    HOME {EV}KUUTAH-KU on match 32747: pair not formable from the store: refused" in k
    assert any("2 capture(s) 2026-10-08 21:56:38 .. 2026-10-10 11:52:09" in ln for ln in k), k
    c = _block(out, "COOKAAMU")
    assert "    the store's names: Alabama A&M (1 name(s): the pair cannot be formed)" in c, c
    assert f"    HOME {EV}COOKAAMU-AAMU on match 32823: refused: the event's markets do not name two teams" in c
    s = _summary(out)
    assert s == {"another_game": 3, "events": 9, "events_pair_formed": 3, "events_with_legs": 5, "not_formable": 1,
                 "not_stored": 0, "own_game": 3, "own_game_wrong_side": 0, "refused": 1, "split_events": 2,
                 "stored_legs": 8, "title_conflict": 0, "title_fallback_candidates": 0}, s
    for ev in ("FAMUALST", "UNDUNI", "NDSUUNLV", "CCARMRSH"):
        assert f"EVENT {EV}{ev}: no stored leg in this copy" in out


def test_match_ids_are_machine_local_and_events_key_the_receipt(copy, capsys):
    rc, out = _run(capsys, "--db", copy, "--match-ids", "32749,47648", "--events", "")
    assert rc == 0, out
    assert "  match 47648: not in this copy" in out
    assert [ln for ln in out if ln.startswith("EVENT ")] == [f"EVENT {EV}UGAALA · SPLIT: its stored legs sit on 2 "
                                                              "games"]
    rc, out = _run(capsys, "--db", copy, "--match-ids", "", "--events", f"{EV}SCSTCHSO")
    assert [ln for ln in out if ln.startswith("EVENT ")] == [f"EVENT {EV}SCSTCHSO · SPLIT: its stored legs sit on 2 "
                                                              "games"]
    rc, out = _run(capsys, "--db", copy, "--match-ids", "32738", "--events", "")
    assert "  match 32738 (Georgia @ Alabama · our kickoff 2026-10-10 23:30Z): no tickered Kalshi leg in this copy" \
        in out


def _edit(copy, *sql):
    """One more fact in the copy's source world, then a fresh .backup copy beside it."""
    con = sqlite3.connect(str(copy))
    for q, args in sql:
        con.execute(q, args)
    con.commit()
    con.close()
    return _backup(copy, copy.parent.parent / "copy2" / "sports.db")


def test_a_leg_on_its_own_game_on_the_wrong_side_is_named_so(copy, capsys):
    """A stored leg on the right game and the wrong side is its own verdict and count, never 'ANOTHER game'
    (round-1 review)."""
    c2 = _edit(copy, ("UPDATE odds_snapshots SET selection = 'HOME' WHERE match_id = 32817 AND market_ticker = ?",
                      (f"{EV}SCSTCHSO-SCST",)),
               ("UPDATE odds_snapshots SET selection = 'AWAY' WHERE match_id = 32817 AND market_ticker = ?",
                (f"{EV}SCSTCHSO-CHSO",)))
    rc, out = _run(capsys, "--db", c2, "--match-ids", "", "--events", f"{EV}SCSTCHSO")
    assert rc == 0, out
    b = _block(out, "SCSTCHSO")
    assert (f"    HOME {EV}SCSTCHSO-SCST on match 32817: "
            "stored on its own game, WRONG SIDE: placed here AWAY on both names") in b, b
    assert (f"    AWAY {EV}SCSTCHSO-CHSO on match 32817: "
            "stored on its own game, WRONG SIDE: placed here HOME on both names") in b, b
    assert (f"    HOME {EV}SCSTCHSO-SCST on match 32763: "
            "stored on ANOTHER game: placed on match 32817 AWAY on both names") in b, b
    s = _summary(out)
    assert (s["own_game_wrong_side"], s["another_game"], s["own_game"]) == (2, 1, 0), s


def test_after_reads_every_settled_event_of_the_series_never_only_the_selection(copy, capsys):
    """The claims rule reads across every settled event of the series in the copy, as kalshi-history's run reads every
    event it knows of: a second event naming the same pair on the same day refuses both, whether or not it is selected
    (round-1 review: the verdict must not depend on --events)."""
    ins = ("INSERT INTO kalshi_settled_markets (ticker, event_ticker, series, yes_sub_title, source, fetched_at) "
           "VALUES (?, ?, 'KXNCAAFGAME', ?, 'historical', '2026-10-15 12:00:00')")
    c2 = _edit(copy, (ins, (f"{EV}ALAUGA-UGA", f"{EV}ALAUGA", "Georgia")),
               (ins, (f"{EV}ALAUGA-ALA", f"{EV}ALAUGA", "Alabama")))
    seen = []
    for events in (f"{EV}UGAALA", f"{EV}UGAALA,{EV}ALAUGA"):
        rc, out = _run(capsys, "--db", c2, "--match-ids", "", "--events", events)
        assert rc == 0, out
        b = _block(out, "UGAALA")
        seen.append([ln for ln in b if "VERDICT" in ln or ": refused" in ln or ": stored" in ln])
        assert (f"    HOME {EV}UGAALA-UGA on match 32749: refused: two markets claim one side of one game") in b, b
        assert any(ln.startswith("  after's scope, KXNCAAFGAME: every settled event of the series in this copy "
                                 "(5 events, 9 markets)") for ln in out), out
        assert any(ln.startswith("  ✗ match 32738 AWAY: 2 markets of 2 events claim it") for ln in out), out
    assert seen[0] == seen[1]


def test_a_row_placed_by_ruling_is_read_by_its_stored_side(copy, capsys):
    """A settled row placed by ruling (kalshi_history.RULED_NOTE) is read by its stored side, never placed by date, as
    the run reads it (place_events' `stored`)."""
    from src.ingestion import kalshi_history as kh
    c2 = _edit(copy, ("UPDATE kalshi_settled_markets SET match_id = 32823, side = 'HOME', notes = ? WHERE ticker = ?",
                      (kh.RULED_NOTE + "ARCHITECT test", f"{EV}COOKAAMU-AAMU")))
    rc, out = _run(capsys, "--db", c2, "--match-ids", "", "--events", f"{EV}COOKAAMU")
    assert rc == 0, out
    b = _block(out, "COOKAAMU")
    assert any(ln.startswith(f"    {EV}COOKAAMU-AAMU (Alabama A&M): placed by ruling on match 32823 HOME") for ln in b), b
    assert f"    HOME {EV}COOKAAMU-AAMU on match 32823: stored on its own game: placed here by ruling" in b, b
    assert any(ln.startswith(f"  {EV}COOKAAMU-AAMU · event {EV}COOKAAMU · the store's names: 1 (Alabama A&M) · ")
               and ln.endswith(" · placed by ruling") for ln in out), out        # flagged all the same (236 item 1)


@pytest.mark.parametrize("title,verdict,kind", [
    (("Duke", "Georgia Tech"), "refused TITLE_CONFLICT: the title's two names do not agree with the event's markets",
     "title_conflict"),
    (("Bethune-Cookman", "Alabama A&M"), "stored on its own game: placed here on both names", "own_game"),
])
def test_the_after_names_title_conflict_and_counts_it_apart(copy, capsys, monkeypatch, title, verdict, kind):
    """ARCHITECT 2026-11-03, addendum 234 item 2(b): "any inconsistency REFUSES the event with its own sentinel
    (TITLE_CONFLICT, named in the receipt), never a placement". The store holds no title; were one read (the adapter's
    title parse, stood in here for COOKAAMU, whose store names one team), the AFTER is the narrowed matcher's: a title
    that disagrees with the one settled row is named TITLE_CONFLICT and counted under its own key, one that agrees
    places on its two names."""
    from src.adapters.kalshi import KalshiAdapter
    monkeypatch.setattr(KalshiAdapter, "title_teams",
                        staticmethod(lambda m: title if "COOKAAMU" in (m.get("ticker") or "") else None))
    rc, out = _run(capsys, "--db", copy, "--match-ids", "", "--events", f"{EV}COOKAAMU")
    assert rc == 0, out
    b = _block(out, "COOKAAMU")
    assert f"    HOME {EV}COOKAAMU-AAMU on match 32823: {verdict}" in b, b
    s = _summary(out)
    assert s[kind] == 1 and s["refused"] == 0, s
    if kind == "title_conflict":
        assert any(ln.startswith(f"    {EV}COOKAAMU-AAMU (Alabama A&M): refused TITLE_CONFLICT: ") for ln in b), b
        assert any(ln.startswith(f"  ✗ {EV}COOKAAMU: the title reads Duke vs Georgia Tech; the markets name "
                                 "Alabama A&M: refused") for ln in out), out
    assert any(ln.startswith("  the title fallback as narrowed (addendum 234 item 2): read only where") for ln in out)
    assert any(ln.startswith("  THE LIMIT: the store holds no title, so this receipt CANNOT tell which stored legs "
                             "the narrowing re-verdicts") for ln in out), out


def _cand(out):
    """The TITLE-FALLBACK CANDIDATES section (addendum 236 item 1): its header line, then its lines."""
    i = next(k for k, ln in enumerate(out) if ln.startswith("TITLE-FALLBACK CANDIDATES (addendum 236 item 1): "))
    j = next((k for k in range(i + 1, len(out)) if not out[k].startswith("  ")), len(out))
    return out[i:j]


def test_a_two_name_event_is_never_a_title_fallback_candidate(copy, capsys):
    """ARCHITECT 2026-11-03, addendum 236 item 1: the flag is the events the store names by other than two teams; the
    two-name events of the 10-10 shape are not flagged, and COOKAAMU's one row, stored on no match, is counted beside
    the flag, never in it. THE LIMIT stays on the console."""
    rc, out = _run(capsys, "--db", copy)
    assert rc == 0, out
    cd = _cand(out)
    assert cd[0] == ("TITLE-FALLBACK CANDIDATES (addendum 236 item 1): 0 settled row(s) stored on a match, in 0 "
                     "event(s) the store names by other than two teams (the only rows the title fallback could ever "
                     "have placed); 0 with a stored leg verdicted \"other game\" or \"own game, WRONG SIDE\" (the "
                     "follow-up before the close)"), cd
    assert cd[1] == ("  scope: every settled event of KXMLBGAME, KXNFLGAME, KXNHLGAME, KXNCAAFGAME in this copy (4 "
                     "events), never only --events; the store's names: the distinct non-tie yes_sub_title across the "
                     "event's settled markets; 1 row(s) of such events stored on no match, not flagged (the fallback "
                     "placed none)"), cd
    assert cd[2].startswith("  each stored leg (odds_snapshots, by its ticker) is verdicted against kalshi-history's "
                            "stored match and side: ") and "the AFTER places no flagged row but one placed by ruling" \
        in cd[2] and "needs-ruling" in cd[2], cd
    assert cd[3] == ("  THE READING'S LIMIT: \"own game\" means only that the leg agrees with kalshi-history's stored "
                     "decision, not that the placement is right: that decision may itself be the title fallback's, so "
                     "a leg the live sync and kalshi-history both put on the same wrong game reads \"own game\" "
                     "here"), cd
    assert len(cd) == 4 and not any("UGAALA" in ln or "SCSTCHSO" in ln or "HOUKSU" in ln for ln in cd), cd
    assert _summary(out)["title_fallback_candidates"] == 0
    assert any(ln.startswith("  THE LIMIT: the store holds no title, so this receipt CANNOT tell which stored legs "
                             "the narrowing re-verdicts") and "TITLE_CONFLICT cannot show on a real copy" in ln
               for ln in out), out


@pytest.mark.parametrize("selection,verdict", [("HOME", "own game"), ("AWAY", "own game, WRONG SIDE")])
def test_a_one_name_event_stored_on_a_match_is_flagged(copy, capsys, selection, verdict):
    """Addendum 236 item 1: COOKAAMU's store names one team; kalshi-history's row stored on match 32823 HOME is a
    candidate (only the title fallback could have placed it), its stored leg verdicted against that match and side,
    whatever --events reads."""
    c2 = _edit(copy, ("UPDATE kalshi_settled_markets SET match_id = 32823, side = 'HOME', notes = NULL "
                      "WHERE ticker = ?", (f"{EV}COOKAAMU-AAMU",)),
               ("UPDATE odds_snapshots SET selection = ? WHERE market_ticker = ?", (selection, f"{EV}COOKAAMU-AAMU")))
    rc, out = _run(capsys, "--db", c2, "--match-ids", "", "--events", "")
    assert rc == 0, out
    cd = _cand(out)
    assert cd[0].startswith("TITLE-FALLBACK CANDIDATES (addendum 236 item 1): 1 settled row(s) stored on a match, in "
                            "1 event(s) the store names by other than two teams"), cd
    assert f"; {1 if verdict != 'own game' else 0} with a stored leg verdicted" in cd[0], cd
    assert cd[4:] == [
        f"  {EV}COOKAAMU-AAMU · event {EV}COOKAAMU · the store's names: 1 (Alabama A&M) · kalshi-history stored: "
        "match 32823 HOME (Bethune-Cookman @ Alabama A&M · our kickoff 2026-10-10 17:00Z)",
        f"    stored leg {selection} on match 32823 (Bethune-Cookman @ Alabama A&M · our kickoff 2026-10-10 "
        f"17:00Z) · 1 capture(s): {verdict}"], cd
    assert _summary(out)["title_fallback_candidates"] == 1


def test_a_three_name_event_stored_on_a_match_is_flagged(copy, capsys):
    """Addendum 236 item 1: an event the store names by three teams, two of its rows stored on a match, is flagged row
    by row; a stored leg on another game is "other game", a row with no leg says so, the row on no match is counted
    beside the flag; a one-name event of a series outside the four two-way ones is not read."""
    ins = ("INSERT INTO kalshi_settled_markets (ticker, event_ticker, series, yes_sub_title, match_id, side, source, "
           "fetched_at) VALUES (?, ?, ?, ?, ?, ?, 'historical', '2026-10-15 12:00:00')")
    k = f"{EV}KUUTAH"
    c2 = _edit(copy, (ins, (f"{k}-KU", k, "KXNCAAFGAME", "Kansas", 32748, "AWAY")),
               (ins, (f"{k}-UTAH", k, "KXNCAAFGAME", "Utah", 32748, "HOME")),
               (ins, (f"{k}-UTU", k, "KXNCAAFGAME", "Utah Tech", None, None)),
               (ins, ("KXEPLGAME-26OCT10ARSCHE-ARS", "KXEPLGAME-26OCT10ARSCHE", "KXEPLGAME", "Arsenal", 32738,
                      "HOME")))
    rc, out = _run(capsys, "--db", c2, "--match-ids", "", "--events", f"{EV}UGAALA")
    assert rc == 0, out
    cd = _cand(out)
    assert cd[0] == ("TITLE-FALLBACK CANDIDATES (addendum 236 item 1): 2 settled row(s) stored on a match, in 1 "
                     "event(s) the store names by other than two teams (the only rows the title fallback could ever "
                     "have placed); 1 with a stored leg verdicted \"other game\" or \"own game, WRONG SIDE\" (the "
                     "follow-up before the close)"), cd
    assert "(5 events)" in cd[1] and "; 2 row(s) of such events stored on no match" in cd[1], cd
    assert cd[4:] == [
        f"  {k}-KU · event {k} · the store's names: 3 (Kansas / Utah / Utah Tech) · kalshi-history stored: match "
        "32748 AWAY (Kansas @ Utah · our kickoff 2026-10-11 02:15Z)",
        "    stored leg HOME on match 32747 (Houston @ Kansas State · our kickoff 2026-10-10 19:30Z) · 2 capture(s): "
        "other game",
        f"  {k}-UTAH · event {k} · the store's names: 3 (Kansas / Utah / Utah Tech) · kalshi-history stored: match "
        "32748 HOME (Kansas @ Utah · our kickoff 2026-10-11 02:15Z)",
        "    no stored leg in odds_snapshots"], cd
    assert not any("KXEPLGAME" in ln for ln in cd), cd
    assert _summary(out)["title_fallback_candidates"] == 2


def test_a_copy_without_the_settled_table_forms_no_pair(tmp_path, capsys):
    """A copy where kalshi-history's table holds nothing: every event's pair is not formable from the store."""
    _world(tmp_path / "w.db", settled=False)
    copy = _backup(tmp_path / "w.db", tmp_path / "c" / "sports.db")
    rc, out = _run(capsys, "--db", copy)
    assert rc == 0, out
    s = _summary(out)
    assert s["not_formable"] == 8 and s["own_game"] == s["another_game"] == s["refused"] == 0, s


def test_a_copy_without_the_settled_table_flags_nothing_and_says_it_could_not_read(copy, capsys):
    """Addendum 236 item 1 under law 4: a copy with no kalshi_settled_markets table is never a clean read of zero; the
    candidate line says it could not read, and the JSON count is null."""
    c2 = _edit(copy, ("DROP TABLE kalshi_settled_markets", ()))
    rc, out = _run(capsys, "--db", c2)
    assert rc == 0, out
    assert _cand(out) == ["TITLE-FALLBACK CANDIDATES (addendum 236 item 1): NOT READ: kalshi_settled_markets is not in "
                          "this copy, so no settled row could be flagged; the count is unknown (null), not zero"], out
    assert _summary(out)["title_fallback_candidates"] is None


def test_read_only_the_copy_is_unchanged_and_no_sidecar_is_made(copy, capsys):
    before = copy.read_bytes()
    rc, _ = _run(capsys, "--db", copy)
    assert rc == 0
    assert copy.read_bytes() == before
    assert sorted(p.name for p in copy.parent.iterdir()) == ["sports.db"]


def test_refusals(copy, capsys, tmp_path):
    rc, out = _run(capsys)
    assert rc == 2 and out[0].startswith("REFUSED: --db PATH is required")
    missing = tmp_path / "nowhere" / "sports.db"
    rc, out = _run(capsys, "--db", missing)
    assert rc == 2 and "no file at" in out[0] and not missing.exists() and not missing.parent.exists()
    under = ROOT / "data" / "pair-receipt-never.db"
    rc, out = _run(capsys, "--db", under)
    assert rc == 2 and "resolves under the repo's data/" in out[0] and not under.exists()
    for sc in ("-wal", "-shm", "-journal"):
        side = copy.with_name("sports.db" + sc)
        side.write_bytes(b"")
        rc, out = _run(capsys, "--db", copy)
        assert rc == 2 and f"has a {sc} sidecar" in out[0], out
        side.unlink()
    rc, out = _run(capsys, "--db", copy, "--match-ids", "32749,x")
    assert rc == 2 and "--match-ids '32749,x': not a comma-separated list of integers" in out[0]
    rc, out = _run(capsys, "--db", copy, "--events", "UGAALA")
    assert rc == 2 and "--events: UGAALA is not an event ticker" in out[0]
    blank = tmp_path / "blank" / "x.db"
    blank.parent.mkdir()
    con = sqlite3.connect(str(blank))
    con.execute("create table t (x int)")
    con.commit()
    con.close()
    rc, out = _run(capsys, "--db", blank)
    assert rc == 2 and "cannot be read through a mode=ro + immutable=1 URI (no such table: matches)" in out[0], out
    _world(tmp_path / "nt.db", ticker_column=False)
    nt = _backup(tmp_path / "nt.db", tmp_path / "nt" / "sports.db")
    rc, out = _run(capsys, "--db", nt)
    assert rc == 2 and "odds_snapshots.market_ticker does not exist" in out[0] and len(out) == 1, out
    thin = tmp_path / "thin" / "x.db"                 # a matches table, not the schema the read needs
    thin.parent.mkdir()
    con = sqlite3.connect(str(thin))
    con.execute("create table matches (id int)")
    con.commit()
    con.close()
    rc, out = _run(capsys, "--db", thin)
    assert rc == 2 and out == [f"REFUSED: --db {thin}: odds_snapshots does not exist in this copy: no stored leg to "
                               "read; nothing read"], out
    con = sqlite3.connect(str(thin))
    con.execute("create table odds_snapshots (id int, market_ticker text)")
    con.commit()
    con.close()
    rc, out = _run(capsys, "--db", thin)
    assert rc == 2 and "cannot be read as the schema the receipt needs (OperationalError" in out[0], out
    assert len(out) == 1


def test_the_receipt_quotes_the_ruling_and_places_with_the_shared_module():
    import inspect
    assert script.RULING_230_0A in " ".join(script.__doc__.split())
    assert script.RULING_234_2 in " ".join(script.__doc__.split())          # addendum 234 item 2, verbatim
    assert script.RULING_236_1 in " ".join(script.__doc__.split())          # addendum 236 item 1, verbatim
    src = inspect.getsource(script.collect)
    assert "kh.place_events(" in src and "stored_games(" in src and "network" not in src
