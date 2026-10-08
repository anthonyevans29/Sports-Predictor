"""ARCHITECT 2026-10-08, addendum 12 (soccer closing-odds names), PINS, verbatim: "In the football-data closing-odds
ingest, Ath Bilbao is Athletic Club; Espanol is Espanyol; M'gladbach is Borussia Mönchengladbach; Hamburg is Hamburger
SV; Brest is Stade Brestois 29. Nothing else in the matcher changes: the date gate, both teams fitting the same game,
the best score winning, a tie refused."
Guards: (1) ath / borussia / stade are never synonyms; (2) the closes ingest normalizes both names to NFC.
Synthetic rows only (year 2097, own competition codes); the architect's hard cases."""
import unicodedata
from datetime import datetime

import pytest
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.ingestion import soccer_odds_history as soh
from src.ingestion.team_aliases import TOKEN_SYNONYMS

HDR = "Div,Date,HomeTeam,AwayTeam,PSCH,PSCD,PSCA\n"


def _world(code, fixtures):
    """fixtures: [(day, home_name, away_name)] -> {(home, away): match_id}."""
    init_db()
    out = {}
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=code, name=code, area="T", type="LEAGUE")
        s.add(comp)
        s.flush()
        teams = {}
        for _, h, a in fixtures:
            for n in (h, a):
                if n not in teams:
                    teams[n] = Team(sport=Sport.SOCCER, name=n)
                    s.add(teams[n])
        s.flush()
        for day, h, a in fixtures:
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2097/98",
                      utc_date=datetime(2097, 9, day, 15), status=MatchStatus.FINISHED,
                      home_team_id=teams[h].id, away_team_id=teams[a].id, home_score=1, away_score=0)
            s.add(m)
            s.flush()
            out[(h, a)] = m.id
    return out


def _csv(tmp_path, rows, name):
    p = tmp_path / f"{name}.csv"
    p.write_text(HDR + "".join(f"T,{d:02d}/09/2097,{h},{a},2.1,3.3,3.6\n" for d, h, a in rows), encoding="utf-8")
    return str(p)


def _stored(mid):
    with session_scope() as s:
        return s.execute(select(func.count()).select_from(Odds).where(
            Odds.match_id == mid, Odds.bookmaker == soh.BOOKMAKER, Odds.market == "1X2")).scalar()


def test_the_five_pins_land_every_hard_case_on_its_own_game_and_a_rerun_stores_nothing(tmp_path):
    PD = _world("ZPD12", [(1, "Athletic Club", "Atletico Madrid"), (1, "Real Madrid", "Espanyol"),
                          (8, "Espanyol", "Athletic Club")])
    BL = _world("ZBL12", [(2, "Borussia Mönchengladbach", "Borussia Dortmund"),
                          (9, "Borussia Mönchengladbach", "Hamburger SV"),
                          (16, "Hamburger SV", "FC St. Pauli"), (23, "1. FC Köln", "Hamburger SV")])
    FL = _world("ZFL12", [(3, "Stade Brestois 29", "Paris FC"), (10, "Paris Saint-Germain", "Stade Brestois 29"),
                          (17, "Stade Brestois 29", "Stade de Reims")])
    cases = [
        ("ZPD12", PD, [(1, "Ath Bilbao", "Ath Madrid"), (1, "Real Madrid", "Espanol"), (8, "Espanol", "Ath Bilbao")]),
        ("ZBL12", BL, [(2, "M'gladbach", "Dortmund"), (9, "M'gladbach", "Hamburg"), (16, "Hamburg", "St Pauli"),
                       (23, "FC Koln", "Hamburg")]),
        ("ZFL12", FL, [(3, "Brest", "Paris FC"), (10, "Paris SG", "Brest"), (17, "Brest", "Reims")]),
    ]
    for code, ids, rows in cases:
        r = soh.sync_soccer_closing_odds(competition_code=code, csv_path=_csv(tmp_path, rows, code))
        assert r["ok"] and r["unmatched"] == 0 and r["ambiguous"] == 0, r
        assert r["stored_games"] == len(rows)
        for mid in ids.values():
            assert _stored(mid) == 3                         # HOME / DRAW / AWAY on its own game, nowhere else
        again = soh.sync_soccer_closing_odds(competition_code=code, csv_path=_csv(tmp_path, rows, code + "b"))
        assert again["stored_games"] == 0 and again["skipped_existing"] == len(rows)


def test_an_nfd_stored_monchengladbach_still_matches(tmp_path):
    nfd = unicodedata.normalize("NFD", "Borussia Mönchengladbach")
    assert nfd != "Borussia Mönchengladbach"                 # the decomposed form really is stored
    ids = _world("ZNF12", [(4, nfd, "Borussia Dortmund")])
    r = soh.sync_soccer_closing_odds(competition_code="ZNF12",
                                     csv_path=_csv(tmp_path, [(4, "M'gladbach", "Dortmund")], "nfd"))
    assert r["stored_games"] == 1 and r["unmatched"] == 0
    assert _stored(ids[(nfd, "Borussia Dortmund")]) == 3


def test_guard_ath_borussia_stade_are_never_synonyms():
    for t in ("ath", "borussia", "stade"):
        assert t not in TOKEN_SYNONYMS
    assert {k: TOKEN_SYNONYMS[k] for k in ("bilbao", "espanol", "m'gladbach", "hamburg", "brest")} == {
        "bilbao": "athletic", "espanol": "espanyol", "m'gladbach": unicodedata.normalize("NFC", "mönchengladbach"),
        "hamburg": "hamburger", "brest": "brestois"}


def test_nothing_else_in_the_matcher_changes_a_tie_is_still_refused(tmp_path):
    # two same-day games that fit "Brest v Paris FC" with the same score (1 + 2): the tie is refused, never guessed
    _world("ZTI12", [(5, "Stade Brestois 29", "Paris FC"), (5, "Brestois Reserve", "Paris FC Two")])
    r = soh.sync_soccer_closing_odds(competition_code="ZTI12",
                                     csv_path=_csv(tmp_path, [(5, "Brest", "Paris FC")], "tie"))
    assert (r["stored_games"], r["unmatched"], r["ambiguous"]) == (0, 1, 1)
