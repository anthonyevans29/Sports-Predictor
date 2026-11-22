"""Addendum 446 item 1 (Refs #1052), the PL injury duplicate receipt: read-only.

A throwaway SQLite world (never data/), closing files as a closing run writes them (modelled on
tests/test_pl_injury_classification_receipt.py's build_db / closing() / row() / world). Covers the fold rule, the
population (season, competition, one row per match, the bounds), the privacy rule (no player name in the output),
the copy's PRAGMA line with and without player_source_id, and the 198 item 6(ii) fence mirrored from #688's tests."""
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pl_injury_duplicate_receipt",
                                               ROOT / "scripts" / "pl_injury_duplicate_receipt.py")
dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dr)

STAMP = "2026-11-21T14:20:05.123456"
TEAMS = {"Chelsea": "49", "Arsenal": "42", "Everton": "45", "Leeds": "63", "Brentford": "55", "Fulham": "36",
         "Hull City": "64", "Wrexham": "1834"}

# invented names (no real player); the privacy test checks every one of them, and their surnames, is never printed
CHE = ["Renée Dufort", "Renee Dufort", "Marco Ruiz Lago", "Marco Ruiz", "Tim Aldous", "Ben Corrigan",
       "Sam Whitcombe"]                                                   # 7 entries, 2 pairs: distinct 5
ARS = ["Olu Pemberton", "Kai Ferro"]
EVE = ["Ana Belo Cruz", "Ana Belo", "Ana Cruz", "T. Aldermoor", "Tobias Aldermoor"]   # ambiguous + initial form
LEE = ["Renee Dufort"]                                                    # the home side's spelling on the other side
BRE = ["Ivo Castellanos", "Ivo Castellanós", "Pim Varga", "Lev Ostrander", "Ned Quill", "Abe Mordaunt",
       "Cy Holloway", "Rufus Tench"]                                      # 8 shown of 10: names cut
FUL = ["Dov Ashgrove", "Dov Ashgrove"]                                    # identical, twice
ALL_NAMES = CHE + ARS + EVE + LEE + BRE + FUL + ["Jules Marchetti", "Jules Marchettí"]


def _dt(v):
    return datetime.fromisoformat(v)


def build_db(path: Path) -> None:
    from src.db.schema import Base, Competition, Injury, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        pl = Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England", type="LEAGUE")
        s.add(pl)
        s.flush()
        t = {}
        for n, pid in TEAMS.items():
            t[n] = Team(sport=Sport.SOCCER, name=n, external_ids={"api_football": pid})
            s.add(t[n])
        s.flush()

        def match(mid, h, a, ko, fid):
            s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=pl.id, season="2026/27", utc_date=_dt(ko),
                        status=MatchStatus.SCHEDULED, home_team_id=t[h].id, away_team_id=t[a].id,
                        external_ids={"api_football": fid}))
        match(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", "2001")
        match(9501, "Everton", "Leeds", "2026-11-21T15:00:00", "2002")
        match(9502, "Brentford", "Fulham", "2026-11-21T17:30:00", "2003")
        s.flush()
        positions = ["Midfielder", "Midfielder", "Defender", "Defender", None, "Attacker", None]
        fixtures = ["2001", "1990", "2001", "1985", "2001", "2001", None]
        for n, pos, fx in zip(CHE, positions, fixtures):        # Chelsea's list, recoverable: stamp and count agree
            s.add(Injury(team_id=t["Chelsea"].id, player_name=n, player_position=pos, type="Missing Fixture",
                         reason="Knee Injury", fixture_source_id=fx, refreshed_at=_dt(STAMP)))
        for n in BRE[:2]:                                       # Brentford: stored count 2, the page's 10 (not recoverable)
            s.add(Injury(team_id=t["Brentford"].id, player_name=n, type="Missing Fixture", fixture_source_id="2003",
                         refreshed_at=_dt(STAMP)))
        s.commit()
    eng.dispose()


def row(mid, home, away, ko, hn, an, hc=None, ac=None, stamp=STAMP, season="2026/27", comp="PL", fb=None):
    hc = len(hn) if hc is None else hc
    ac = len(an) if ac is None else ac
    notes = ([f"home missing {hc} (-{min(25, 3 * hc)}% xG)"] if hc else []) + \
            ([f"away missing {ac} (-{min(25, 3 * ac)}% xG)"] if ac else [])
    return {"match_id": mid, "utc_date": ko, "competition": comp, "season": season, "home_team": home,
            "away_team": away,
            "injuries": {"home_count": hc, "away_count": ac, "home_names": hn[:8], "away_names": an[:8]},
            "input_quality": {"injuries_synced_at": stamp,
                              "injuries": {"home": {"count": hc, "synced_at": stamp if hc else None},
                                           "away": {"count": ac, "synced_at": stamp if ac else None}}},
            "prediction": {"factor_breakdown": fb if fb is not None else
                           {"home_injuries_count": hc, "away_injuries_count": ac, "factor_notes": notes}},
            "desk": {"call": "PASS", "pick": "HOME"}}


def closing(ex: Path, start: str, rows: list, fam="SOCCER", sha="841eba24deadbeef"):
    ex.mkdir(parents=True, exist_ok=True)
    st = datetime.fromisoformat(start)
    doc = {"exported_at": start + ".000001Z", "git_sha": sha, "sport": fam.lower(), "competition_code": "PL",
           "count": len(rows), "predictions": rows,
           "closing": {"family": fam, "start": start + "Z", "run_id": f"run-{st:%m%d%H%M}",
                       "match_ids": [r["match_id"] for r in rows], "called_off": []}}
    (ex / f"closing_{fam}_{st:%Y-%m-%dT%H%M}Z.json").write_text(json.dumps(doc))


def write_exports(ex: Path):
    # an earlier run of 9500 (a pair on it), then the later one that wins
    closing(ex, "2026-11-21T11:55:00", [row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", CHE[:2], [],
                                            stamp="2026-11-21T11:50:00")])
    closing(ex, "2026-11-21T14:25:00", [row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", CHE, ARS),
                                        row(9501, "Everton", "Leeds", "2026-11-21T15:00:00", EVE, LEE)])
    closing(ex, "2026-11-21T16:55:00", [row(9502, "Brentford", "Fulham", "2026-11-21T17:30:00", BRE, FUL, hc=10,
                                            fb={"home_injuries_count": 9, "away_injuries_count": 2,
                                                "factor_notes": ["home missing 9 (-25% xG)",
                                                                 "away missing 2 (-6% xG)"]})])
    # excluded: another season's PL row, a non-PL soccer row, another family's row (each carries a pair)
    pair = ["Jules Marchetti", "Jules Marchettí"]
    closing(ex, "2026-05-10T14:25:00", [row(8100, "Chelsea", "Arsenal", "2026-05-10T15:00:00", pair, [],
                                            season="2025/26")])
    closing(ex, "2026-11-22T13:25:00", [row(9600, "Hull City", "Wrexham", "2026-11-22T14:00:00", pair, [],
                                            comp="ELC")])
    closing(ex, "2026-11-21T16:55:00", [row(9999, "X", "Y", "2026-11-21T17:30:00", pair, [])], fam="MLB")


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "copy.db"
    build_db(db)
    ex = tmp_path / "exports"
    write_exports(ex)
    return {"db": db, "ex": ex, "tmp": tmp_path}


def run(w, *extra, ex=None, db=None):
    out = []
    code = dr.main(["--exports", str(ex or w["ex"]), "--db", str(db or w["db"]), *extra], echo=out.append)
    return code, out


def summary(out):
    assert out[-1].startswith(dr.TAG + " ")
    return json.loads(out[-1][len(dr.TAG) + 1:])


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- the fold rule --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("a, b, kind", [
    ("Renée Dufort", "Renee Dufort", dr.ACCENT),
    ("Marco Ruiz Lago", "Marco Ruiz", dr.DOUBLE),           # the short form keeps the first surname
    ("Marco Ruiz Lago", "Marco Lago", dr.DOUBLE),           # and the short form keeps the second (order kept)
    ("Marco Ruiz-Lago", "Marco Ruiz", dr.DOUBLE),           # a hyphen folds to a space (tokens())
    ("T. Aldermoor", "Tobias Aldermoor", dr.INITIAL),
    ("Dov Ashgrove", "Dov Ashgrove ", dr.IDENTICAL),
    ("Marco Ruiz", "Marco Lago", None),                     # equal lengths: not a sub-sequence
    ("Marco", "Marco Ruiz", None),                          # the shorter must hold 2 tokens
    ("Ruiz Lago", "Marco Ruiz Lago", None),                 # the first token must be shared
    ("Marco Lago Ruiz", "Marco Ruiz Lago", None),           # order kept: neither is the other's sub-sequence
    ("Tim Aldous", "Ben Corrigan", None),
])
def test_the_fold_rule_kinds(a, b, kind):
    assert dr.pair_kind(a, b) == kind and dr.pair_kind(b, a) == kind


def test_an_entry_that_pairs_with_two_is_ambiguous_never_paired():
    pairs, amb = dr.side_pairs(["Ana Belo Cruz", "Ana Belo", "Ana Cruz"])
    assert pairs == [] and amb == [1]
    pairs, amb = dr.side_pairs(EVE)
    assert pairs == [(4, 5, dr.INITIAL)] and amb == [1]


def test_pairs_carry_their_1_based_places_and_are_disjoint():
    pairs, amb = dr.side_pairs(CHE)
    assert pairs == [(1, 2, dr.ACCENT), (3, 4, dr.DOUBLE)] and amb == []


def test_a_seven_entry_side_with_two_pairs_reads_distinct_five(world):
    code, out = run(world)
    assert code == 0
    che = next(ln for ln in out if ln.startswith("  HOME Chelsea:"))
    assert "entries 7 (injuries.home_count 7, input_quality count 7) · names shown 7" in che
    assert "pairs accent 1 (entries 1 and 2) · double surname 1 (entries 3 and 4)" in che
    assert "distinct by fold 5" in che and "at most" not in che
    assert "factor_breakdown home_injuries_count 7, note 7 (-21% xG) · factor count vs page count: equal" in che


def test_no_pair_across_sides_or_rows(world):
    """Chelsea's 'Renee Dufort' spelling also stands alone on Leeds' side of another row: never a pair."""
    code, out = run(world)
    lee = next(ln for ln in out if ln.startswith("  AWAY Leeds:"))
    assert "pairs none · AMBIGUOUS none" in lee and "distinct by fold 1" in lee
    ars = next(ln for ln in out if ln.startswith("  AWAY Arsenal:"))
    assert "pairs none" in ars


def test_initial_form_is_apart_and_ambiguous_is_counted(world):
    code, out = run(world)
    eve = next(ln for ln in out if ln.startswith("  HOME Everton:"))
    assert "pairs initial form 1 (entries 4 and 5) · AMBIGUOUS entries 1" in eve
    # the initial form is never subtracted; the AMBIGUOUS group (entries 1-3) holds at least one duplicate (F3)
    assert "distinct by fold at most 4" in eve
    s = summary(out)
    assert s["pairs"] == {dr.ACCENT: 2, dr.DOUBLE: 1, dr.IDENTICAL: 1, dr.INITIAL: 1}
    assert s["ambiguous_entries"] == 1
    # the headline: Chelsea's row and side (accents, double surname) and Brentford's (an accent pair in the cut list)
    assert s["headline_rows"] == 2 and s["headline_sides"] == 2
    assert s["matches_with_headline_pair"] == [9500, 9502]


def test_identical_is_its_own_kind_measured(world):
    code, out = run(world)
    ful = next(ln for ln in out if ln.startswith("  AWAY Fulham:"))
    assert "pairs identical 1 (entries 1 and 2)" in ful and "distinct by fold 1" in ful


def test_a_side_above_eight_is_counted_cut_and_its_shown_pairs_labelled(world):
    code, out = run(world)
    bre = next(ln for ln in out if ln.startswith("  HOME Brentford:"))
    assert "entries 10 (injuries.home_count 10, input_quality count 10) · names shown 8" in bre
    assert "pairs accent 1 (entries 1 and 2)" in bre and "distinct by fold at most 9" in bre
    assert "names cut, not fully pairable (10 entries, 8 shown)" in bre
    assert "factor count vs page count: NOT EQUAL" in bre
    s = summary(out)
    assert s["sides_names_cut"] == 1 and s["rows_factor_differs"] == 1
    assert any("sides with names cut, not fully pairable 1 (of them carrying a headline pair among the shown names 1)"
               in ln for ln in out)


def test_a_side_of_exactly_eight_is_not_cut(world):
    ex = world["tmp"] / "eight"
    closing(ex, "2026-11-21T16:55:00", [row(9502, "Brentford", "Fulham", "2026-11-21T17:30:00", BRE, FUL)])
    code, out = run(world, ex=ex)
    bre = next(ln for ln in out if ln.startswith("  HOME Brentford:"))
    assert "entries 8 (injuries.home_count 8, input_quality count 8) · names shown 8" in bre
    assert "names cut" not in bre and "at most" not in bre and "distinct by fold 7" in bre
    assert summary(out)["sides_names_cut"] == 0


def test_a_names_list_longer_than_its_count_has_no_distinct_bound(world):
    ex = world["tmp"] / "longer"
    r = row(9500, "Everton", "Leeds", "2026-11-21T15:00:00", EVE, ["Lee One"])
    r["injuries"]["home_count"] = 1                                # five names on the page, a count of 1
    r["input_quality"]["injuries"]["home"]["count"] = 1
    closing(ex, "2026-11-21T14:25:00", [r])
    code, out = run(world, ex=ex)
    eve = next(ln for ln in out if ln.startswith("  HOME Everton:"))
    assert code == 0 and "names list longer than the count" in eve and "distinct by fold unknown" in eve
    assert "at most -" not in "\n".join(out) and "distinct by fold at most 0" not in eve


def test_entries_take_the_page_count_before_input_quality(world):
    ex = world["tmp"] / "counts"
    r = row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", CHE, ARS)
    r["input_quality"]["injuries"]["home"]["count"] = 6          # the page's injuries.home_count stays 7
    r2 = row(9501, "Everton", "Leeds", "2026-11-21T15:00:00", EVE, LEE)
    del r2["injuries"]["home_count"]                               # no page count: input_quality's 5 stands
    r2["input_quality"]["injuries"]["home"]["count"] = 4
    closing(ex, "2026-11-21T14:25:00", [r, r2])
    code, out = run(world, ex=ex)
    che = next(ln for ln in out if ln.startswith("  HOME Chelsea:"))
    assert "entries 7 (injuries.home_count 7, input_quality count 6)" in che and "distinct by fold 5" in che
    eve = next(ln for ln in out if ln.startswith("  HOME Everton:"))
    assert "entries 4 (injuries.home_count None, input_quality count 4)" in eve


def test_a_file_in_two_dated_folders_is_one_run_never_an_earlier_one(world):
    host = world["tmp"] / "mirror" / "host"
    closing(host / "2026-11-21", "2026-11-21T14:25:00", [row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00",
                                                              CHE, ARS)])
    f = host / "2026-11-21" / "closing_SOCCER_2026-11-21T1425Z.json"
    (host / "2026-11-22").mkdir()
    (host / "2026-11-22" / f.name).write_text(f.read_text())
    code, out = run(world, ex=host)
    assert code == 0
    s = summary(out)
    assert s["rows"] == 1 and s["earlier_runs"] == 0 and s["closing_files"] == 2
    head = next(ln for ln in out if ln.startswith("\n== kickoff 2026-11-21T15:00:00 UTC · match 9500"))
    assert head.endswith("earlier runs 0)")
    assert any(ln.startswith(f"closing-file names in more than one folder 1 (each copy read; one run): {f.name}")
               for ln in out)


def test_season_and_competition_filter(world):
    code, out = run(world)
    s = summary(out)
    assert s["rows"] == 3 and s["other_season_rows"] == 1
    joined = "\n".join(out)
    for mid in ("8100", "9600", "9999"):
        assert f"match {mid} " not in joined


def test_one_row_per_match_the_later_run_wins_earlier_counted(world):
    code, out = run(world)
    s = summary(out)
    assert s["earlier_runs"] == 1
    head = next(ln for ln in out if ln.startswith("\n== kickoff 2026-11-21T15:00:00 UTC · match 9500"))
    assert "file closing_SOCCER_2026-11-21T1425Z.json (git_sha 841eba24, exported_at 2026-11-21T14:25:00.000001Z, " \
           "run 2026-11-21T14:25Z, run_id run-11211425; earlier runs 1)" in head
    assert any("rows read (one per match) 3 · earlier runs not counted 1" in ln for ln in out)


def test_the_bounds(world):
    code, out = run(world, "--from", "2026-11-21T14:25:00Z", "--through", "2026-11-21T16:55:00Z")
    s = summary(out)
    assert code == 0 and s["rows"] == 2 and s["earlier_runs"] == 0          # 11:55 and 16:55 are outside
    assert s["bound"]["outside"] == 2 and s["bound"]["era"] == "window"
    code, out = run(world, "--from", "2026-11-21T16:55:00Z")
    assert summary(out)["rows"] == 1                                       # inclusive
    for args in (["--from", "2026-11-21"], ["--from", "2026-11-22T00:00:00Z", "--through", "2026-11-21T00:00:00Z"]):
        code, out = run(world, *args)
        assert code == 2 and len(out) == 1 and out[0].startswith("REFUSED: --from")


def test_no_player_name_appears_anywhere_in_the_output(world):
    code, out = run(world)
    joined = "\n".join(out)
    assert code == 0
    for n in ALL_NAMES:
        assert n not in joined
        for tok in n.split():
            if len(tok) > 3 and not tok.endswith("."):
                assert tok not in joined, tok


def test_the_rule_is_printed_before_any_result_line(world):
    code, out = run(world)
    rule = out.index(dr.RULE[0])
    first_result = next(i for i, ln in enumerate(out) if ln.startswith("SOURCE IDS") or ln.startswith("\n=="))
    assert rule < first_result
    assert out[rule:rule + len(dr.RULE)] == dr.RULE


def _out_of_scope(db: Path, with_id: bool) -> None:
    """Two teams outside PL 2026/27 with injuries rows: Hull City plays only a PL 2025/26 match (the season scope) and
    Wrexham only an ELC 2026/27 one (the competition scope); with the column, each row carries a player_source_id."""
    from src.db.schema import Competition, Injury, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{db}")
    with Session(eng) as s:
        elc = Competition(sport=Sport.SOCCER, code="ELC", name="Championship", area="England", type="LEAGUE")
        s.add(elc)
        s.flush()
        pl_id = s.execute(text("SELECT id FROM competitions WHERE code = 'PL'")).scalar()
        t = {n: s.execute(text("SELECT id FROM teams WHERE name = :n"), {"n": n}).scalar()
             for n in ("Hull City", "Wrexham", "Chelsea")}
        s.add(Match(id=9700, sport=Sport.SOCCER, competition_id=pl_id, season="2025/26",
                    utc_date=_dt("2026-03-01T15:00:00"), status=MatchStatus.FINISHED, home_team_id=t["Hull City"],
                    away_team_id=t["Chelsea"], external_ids={"api_football": "1700"}))
        s.add(Match(id=9701, sport=Sport.SOCCER, competition_id=elc.id, season="2026/27",
                    utc_date=_dt("2026-11-22T14:00:00"), status=MatchStatus.SCHEDULED, home_team_id=t["Wrexham"],
                    away_team_id=t["Wrexham"], external_ids={"api_football": "1701"}))
        for n in ("Hull City", "Wrexham"):
            s.add(Injury(team_id=t[n], player_name="Out Of Scope", type="Missing Fixture", refreshed_at=_dt(STAMP)))
        s.commit()
        if with_id:
            s.execute(text("UPDATE injuries SET player_source_id = '99' WHERE team_id IN (:a, :b)"),
                      {"a": t["Hull City"], "b": t["Wrexham"]})
            s.commit()
    eng.dispose()


def test_the_id_line_without_the_column(world):
    _out_of_scope(world["db"], with_id=False)
    code, out = run(world)
    ids = next(ln for ln in out if ln.startswith("SOURCE IDS"))
    assert "read UNKNOWN (no source id stored)" in ids
    assert "src/adapters/api_football.py:460-475" in ids and "src/ingestion/service.py:1571-1581" in ids
    assert "only src/adapters/api_american_football.py:529 (list_injuries at :441) supplies one" in ids
    assert "mlb_stats_api" not in ids
    assert "PRAGMA table_info(injuries) has NO player_source_id column; injuries rows of PL 2026/27 teams 9" in ids
    s = summary(out)
    assert s["player_source_id_column"] is False and s["pl_rows_with_id"] is None
    assert s["source_ids"] == "unknown (no source id stored)"
    assert s["pl_injury_rows"] == 9                         # Hull City's and Wrexham's rows are out of scope


def _add_id_column(db: Path) -> None:
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:                      # migrate_injury_player_source_id.py's own ALTER
        c.execute(text("ALTER TABLE injuries ADD COLUMN player_source_id VARCHAR(64)"))
    eng.dispose()


def test_the_id_line_with_the_column(world):
    _add_id_column(world["db"])
    _out_of_scope(world["db"], with_id=True)
    eng = create_engine(f"sqlite:///{world['db']}")
    with eng.begin() as c:
        c.execute(text("UPDATE injuries SET player_source_id = '7' WHERE id = 1"))
    eng.dispose()
    code, out = run(world)
    ids = next(ln for ln in out if ln.startswith("SOURCE IDS"))
    assert ("PRAGMA table_info(injuries) has player_source_id; injuries rows of PL 2026/27 teams 9, carrying a "
            "non-null player_source_id 1") in ids
    # the cause is measured: a PL row carries an id, so "no source id stored" would be false; the ids are read
    assert "no source id stored" not in ids and ids.startswith("SOURCE IDS: read per entry where the side is "
                                                                "recoverable")
    s = summary(out)
    assert s["pl_rows_with_id"] == 1 and s["pl_injury_rows"] == 9      # the out-of-scope rows' ids never counted
    assert s["source_ids"] == "read per entry on recoverable sides"
    # Chelsea's entry 1 carries the one id: both its pairs hold a NULL, so no side count by id
    assert s["pair_source_ids"][dr.ACCENT] == {"two ids": 0, "one id": 0, "unknown (a NULL)": 1, "unknown": 1}
    assert s["sides_distinct_by_id"] == 0
    che = next(ln for ln in out if ln.startswith("  HOME Chelsea:"))
    assert "distinct by id UNKNOWN (6 of 7 stored entries carry no player_source_id)" in che


def test_the_id_line_with_the_column_and_no_pl_id_reads_no_source_id_stored(world):
    _add_id_column(world["db"])
    _out_of_scope(world["db"], with_id=True)               # ids only on teams outside PL 2026/27
    code, out = run(world)
    ids = next(ln for ln in out if ln.startswith("SOURCE IDS"))
    assert "read UNKNOWN (no source id stored)" in ids and "carrying a non-null player_source_id 0" in ids
    s = summary(out)
    assert s["pl_rows_with_id"] == 0 and s["source_ids"] == "unknown (no source id stored)"


def test_recoverable_pairs_print_the_stored_fields_never_a_name(world):
    code, out = run(world)
    i = next(k for k, ln in enumerate(out) if ln.startswith("  HOME Chelsea:"))
    assert out[i + 1].startswith("    recoverable? yes (recoverable")
    assert out[i + 2] == ("    accent pair entries 1 and 2: entry 1: type 'Missing Fixture' · fixture_source_id "
                          "'2001' · position 'Midfielder' | entry 2: type 'Missing Fixture' · fixture_source_id "
                          "'1990' · position 'Midfielder' · source ids: unknown (no source id stored: no "
                          "player_source_id column)")
    assert out[i + 3].startswith("    double surname pair entries 3 and 4: entry 3: type 'Missing Fixture' · "
                                 "fixture_source_id '2001' · position 'Defender' | entry 4:")
    j = next(k for k, ln in enumerate(out) if ln.startswith("  HOME Brentford:"))
    assert out[j + 1] == "    recoverable? no (not recoverable (stored count 2, row count 10))"
    assert out[j + 2] == ("    accent pair entries 1 and 2: source ids: unknown (no source id stored: no "
                          "player_source_id column)")
    assert summary(out)["sides_with_pair_recoverable"] == 1


def test_every_row_is_printed_a_quiet_row_on_one_compact_line_with_both_sides(world):
    """F1 (Codex on #1076): 446 item 1 asks 'for every Premier League closing row ... each side's entries': a row with
    no pair and no ambiguity is printed too, one line carrying both sides' fields."""
    ex = world["tmp"] / "quiet"
    closing(ex, "2026-11-21T14:25:00", [row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", CHE[4:], ARS),
                                        row(9501, "Everton", "Leeds", "2026-11-21T15:00:00", EVE, LEE)])
    closing(ex, "2026-11-21T16:55:00", [row(9502, "Brentford", "Fulham", "2026-11-21T17:30:00", BRE[2:] + ["Al Ivo"],
                                            ["Dov Ashgrove"], hc=10)])
    code, out = run(world, ex=ex)
    assert code == 0
    q = [ln for ln in out if ln.startswith("-- kickoff")]
    assert len(q) == 2 and sum(1 for ln in out if ln.startswith("\n== kickoff")) == 1      # Everton's row is flagged
    assert q[0] == ("-- kickoff 2026-11-21T15:00:00 UTC · match 9500 Chelsea v Arsenal · file "
                    "closing_SOCCER_2026-11-21T1425Z.json (git_sha 841eba24, run 2026-11-21T14:25Z; earlier runs 0) · "
                    "no pair, no ambiguity | HOME Chelsea: entries 3 (injuries.home_count 3, input_quality count 3) · "
                    "names shown 3 · factor_breakdown home_injuries_count 3, note 3 (-9% xG) · factor count vs page "
                    "count: equal · distinct by fold 3 · distinct by id UNKNOWN (no source id stored: no "
                    "player_source_id column) | AWAY Arsenal: entries 2 (injuries.away_count 2, input_quality count "
                    "2) · names shown 2 · factor_breakdown away_injuries_count 2, note 2 (-6% xG) · factor count vs "
                    "page count: equal · distinct by fold 2 · distinct by id UNKNOWN (no source id stored: no "
                    "player_source_id column)")
    assert ("HOME Brentford: entries 10 (injuries.home_count 10, input_quality count 10) · names shown 7 · "
            "factor_breakdown home_injuries_count 10, note 10 (-25% xG) · factor count vs page count: equal · "
            "distinct by fold at most 10 · distinct by id UNKNOWN") in q[1]
    assert "names cut, not fully pairable (10 entries, 7 shown) | AWAY Fulham: entries 1" in q[1]
    assert any(ln.startswith("\nrows with no pair and no ambiguity: 2 (each printed above") for ln in out)
    joined = "\n".join(out)
    for n in CHE + ARS + BRE + FUL + ["Al Ivo"]:
        assert n not in joined
    assert summary(out)["headline_rows"] == 0


def _set_ids(db: Path, ids: dict) -> None:
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        for i, v in ids.items():
            c.execute(text("UPDATE injuries SET player_source_id = :v WHERE id = :i"), {"v": v, "i": i})
    eng.dispose()


def test_a_migrated_copy_reads_each_pair_two_ids_or_one_and_the_side_by_id(world):
    """F2 (Codex on #1076): on a recoverable side the copy's own player_source_id is read per paired entry (Chelsea's
    stored rows are ids 1-7 in CHE's order): entries 1 and 2 carry two ids, 3 and 4 one."""
    _add_id_column(world["db"])
    _set_ids(world["db"], {1: "101", 2: "102", 3: "103", 4: "103", 5: "105", 6: "106", 7: "107"})
    code, out = run(world)
    assert code == 0
    i = next(k for k, ln in enumerate(out) if ln.startswith("  HOME Chelsea:"))
    assert "distinct by fold 5 · distinct by id 6" in out[i]
    assert out[i + 2].startswith("    accent pair entries 1 and 2: entry 1:") and out[i + 2].endswith(" · source ids: "
                                                                                                     "two ids")
    assert out[i + 3].startswith("    double surname pair entries 3 and 4:") and out[i + 3].endswith(" · source ids: "
                                                                                                    "one id")
    s = summary(out)
    assert s["pair_source_ids"][dr.ACCENT] == {"two ids": 1, "one id": 0, "unknown (a NULL)": 0, "unknown": 1}
    assert s["pair_source_ids"][dr.DOUBLE] == {"two ids": 0, "one id": 1, "unknown (a NULL)": 0, "unknown": 0}
    assert s["sides_distinct_by_id"] == 1                   # only Chelsea's side is recoverable
    bre = next(k for k, ln in enumerate(out) if ln.startswith("  HOME Brentford:"))
    assert "distinct by id UNKNOWN (no stored list to read: not recoverable (stored count 2, row count 10))" in out[bre]
    assert out[bre + 2] == ("    accent pair entries 1 and 2: source ids: unknown (no stored list to read: not "
                            "recoverable (stored count 2, row count 10))")
    assert any(ln.startswith("  source ids, pairs by kind: accent: two ids 1, one id 0") for ln in out)
    joined = "\n".join(out)
    for n in ALL_NAMES:
        assert n not in joined


def test_a_migrated_copy_with_one_null_reads_the_pair_unknown_and_no_side_count(world):
    _add_id_column(world["db"])
    _set_ids(world["db"], {1: "101", 3: "103", 4: "103", 5: "105", 6: "106", 7: "107"})      # entry 2 NULL
    code, out = run(world)
    i = next(k for k, ln in enumerate(out) if ln.startswith("  HOME Chelsea:"))
    assert "distinct by id UNKNOWN (1 of 7 stored entries carry no player_source_id)" in out[i]
    assert out[i + 2].endswith(" · source ids: unknown (a NULL)") and out[i + 3].endswith(" · source ids: one id")
    s = summary(out)
    assert s["pair_source_ids"][dr.ACCENT]["unknown (a NULL)"] == 1 and s["sides_distinct_by_id"] == 0


def test_long_short_short_reads_at_most_two_never_three(world):
    """F3 (Codex on #1076): the long form pairs with both short forms, so it is AMBIGUOUS and no pair is formed; the
    three entries hold at least one duplicate under the fold: at most 2, never a definite 3."""
    names = ["Ana Belo Cruz", "Ana Belo", "Ana Cruz"]
    pairs, amb = dr.side_pairs(names)
    assert pairs == [] and amb == [1] and dr.amb_groups(names, amb) == 1
    ex = world["tmp"] / "lss"
    closing(ex, "2026-11-21T14:25:00", [row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", names, ARS)])
    code, out = run(world, ex=ex)
    che = next(ln for ln in out if ln.startswith("  HOME Chelsea:"))
    assert "AMBIGUOUS entries 1" in che and "distinct by fold at most 2 " in che and "distinct by fold 3" not in che


def test_ambiguity_groups_are_counted_once_each_and_an_initial_form_alone_subtracts_nothing():
    two = ["Ana Belo Cruz", "Ana Belo", "Ana Cruz", "Kit Rae Moss", "Kit Rae", "Kit Moss", "Lo Pim"]
    assert dr.amb_groups(two, dr.side_pairs(two)[1]) == 2
    initial_only = ["T. Aldermoor", "Tobias Aldermoor", "Theo Aldermoor"]     # ambiguous by initial form alone
    pairs, amb = dr.side_pairs(initial_only)
    assert amb == [1] and dr.amb_groups(initial_only, amb) == 0


def test_a_names_list_short_for_another_cause_is_counted_with_it(world):
    ex = world["tmp"] / "short"
    r = row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00", CHE[:4], ARS, hc=6)
    r2 = row(9501, "Everton", "Leeds", "2026-11-21T15:00:00", [], [], hc=3, ac=0)
    del r2["injuries"]["home_names"]
    closing(ex, "2026-11-21T14:25:00", [r, r2])
    code, out = run(world, ex=ex)
    s = summary(out)
    assert s["sides_short"] == {"names list shorter than the count (count <= 8; the cause is not on the page)": 1,
                                "no names list on the page": 1}
    che = next(ln for ln in out if ln.startswith("  HOME Chelsea:"))
    assert "distinct by fold at most 4" in che


# ---- the source folders ---------------------------------------------------------------------------------------------

def test_latest_is_refused_and_a_dated_tree_is_read(world):
    host = world["tmp"] / "mirror" / "host"
    closing(host / "2026-11-21", "2026-11-21T14:25:00", [row(9500, "Chelsea", "Arsenal", "2026-11-21T15:00:00",
                                                              CHE, ARS)])
    closing(host / "latest", "2026-11-21T14:25:00", [row(9501, "Everton", "Leeds", "2026-11-21T15:00:00", EVE, LEE)])
    code, out = run(world, ex=host)
    assert code == 0 and summary(out)["rows"] == 1 and summary(out)["dated_folders"] == 1
    code, out = run(world, ex=host / "latest")
    assert code == 2 and len(out) == 1 and out[0].startswith(f"REFUSED: --exports {host / 'latest'}: a latest/ folder")
    (host / "2026-11-22").symlink_to(host / "latest", target_is_directory=True)
    code, out = run(world, ex=host)
    assert code == 2 and "resolves to" in out[0] and "a latest/ folder; latest/ is never read; nothing read" in out[0]


@pytest.mark.parametrize("bad", ["missing", "file", "latest", "dated_link"])
def test_a_bad_exports_is_refused_before_the_copy_is_opened(world, monkeypatch, bad):
    """F4 (Codex on #1076): a bad --exports exits 2 'nothing read' with the copy never opened (no probe, no session)."""
    calls = []
    monkeypatch.setattr(dr.C, "probe_copy", lambda *a, **k: calls.append("probe_copy"))
    monkeypatch.setattr(dr.C, "open_db", lambda *a, **k: calls.append("open_db"))
    host = world["tmp"] / "mirror" / "host"
    (host / "latest").mkdir(parents=True)
    ex = {"missing": world["tmp"] / "nope", "latest": host / "latest", "dated_link": host}[bad] \
        if bad != "file" else world["tmp"] / "a_file.json"
    if bad == "file":
        ex.write_text("{}")
    if bad == "dated_link":
        (host / "2026-11-22").symlink_to(host / "latest", target_is_directory=True)
    code, out = run(world, ex=ex)
    assert code == 2 and len(out) == 1 and out[0].startswith(f"REFUSED: --exports {ex}") and "nothing read" in out[0]
    assert calls == []


def test_exports_not_a_directory_or_missing_is_refused(world):
    code, out = run(world, ex=world["tmp"] / "nope")
    assert code == 2 and out == [f"REFUSED: --exports {world['tmp'] / 'nope'}: not a directory; nothing read"]
    out = []
    assert dr.main(["--db", str(world["db"])], echo=out.append) == 2 and out[0].startswith("REFUSED: --exports is "
                                                                                             "required")


# ---- the 198 item 6(ii) fence (mirrored from #688's tests) ----------------------------------------------------------

def test_a_fresh_wal_backup_copy_opens_immutable_and_leaves_no_sidecar(world, tmp_path):
    live = tmp_path / "wal-live.db"
    with sqlite3.connect(world["db"]) as src, sqlite3.connect(live) as dst:
        src.backup(dst)
    with sqlite3.connect(live) as dst:
        dst.execute("PRAGMA journal_mode=WAL")
    d = tmp_path / "walcopy"
    d.mkdir()
    p = d / "sp.db"
    src = sqlite3.connect(live)
    bk = sqlite3.connect(p)
    src.backup(bk)
    bk.close()
    src.close()
    assert sorted(x.name for x in d.iterdir()) == ["sp.db"] and p.read_bytes()[18:20] == bytes([2, 2])
    before = _sha(p)
    code, out = run(world, db=p)
    assert code == 0 and "(mode=ro + immutable=1 URI, mode=ro&immutable=1" in out[0]
    assert sorted(x.name for x in d.iterdir()) == ["sp.db"] and _sha(p) == before


def test_the_db_copy_is_opened_read_only_bytes_unchanged(world):
    before = _sha(world["db"])
    code, out = run(world)
    assert code == 0 and _sha(world["db"]) == before
    assert f"database --db {world['db'].resolve()} (mode=ro + immutable=1 URI, mode=ro&immutable=1" in out[0]
    assert not (world["db"].parent / "copy.db-journal").exists()
    assert not (world["db"].parent / "copy.db-wal").exists()


@pytest.mark.parametrize("db", [None, "", "  "])
def test_db_missing_or_blank_is_refused_exit_2_nothing_read(world, monkeypatch, db):
    monkeypatch.setattr(dr, "population", lambda *a, **k: pytest.fail("a closing file was read"))
    out = []
    argv = ["--exports", str(world["ex"])] + ([] if db is None else ["--db", db])
    assert dr.main(argv, echo=out.append) == 2
    assert len(out) == 1 and out[0].startswith("REFUSED: --db is required")


def test_db_under_data_is_refused_exit_2_never_created(world, monkeypatch):
    monkeypatch.setattr(dr.C, "ROOT", world["tmp"])
    target = world["tmp"] / "data" / "sp_backup_test_446.db"
    code, out = run(world, db=target)
    assert code == 2 and out[0].startswith("REFUSED: --db") and "under data/" in out[0] and not target.exists()


def test_a_missing_db_is_refused_never_created(world):
    missing = world["tmp"] / "nope.db"
    code, out = run(world, db=missing)
    assert code == 2 and "REFUSED: no DB file" in out[0] and not missing.exists()


def test_a_copy_with_a_sidecar_is_refused(world):
    (world["db"].parent / "copy.db-wal").write_bytes(b"")
    code, out = run(world)
    assert code == 2 and out[0].startswith(f"REFUSED: --db {world['db'].resolve()} has a -wal sidecar")


@pytest.mark.parametrize("content", [b"not a sqlite file\n" * 64, b""], ids=["text", "empty"])
def test_a_db_that_is_not_sqlite_is_refused_exit_2_nothing_read(world, monkeypatch, content):
    bad = world["tmp"] / "not_a_copy.db"
    bad.write_bytes(content)
    monkeypatch.setattr(dr, "population", lambda *a, **k: pytest.fail("a closing file was read"))
    code, out = run(world, db=bad)
    assert code == 2 and len(out) == 1
    assert out[0].startswith(f"REFUSED: --db {bad.resolve()}: cannot be read through a mode=ro + immutable=1 URI (")
    assert bad.read_bytes() == content


def test_a_missing_column_is_refused(world):
    eng = create_engine(f"sqlite:///{world['db']}")
    with eng.begin() as c:
        c.execute(text("ALTER TABLE injuries DROP COLUMN fixture_source_id"))
    eng.dispose()
    code, out = run(world)
    assert code == 2 and out == ["REFUSED: columns fixture_source_id not in injuries (law 1)"]


def test_the_configured_database_path_is_absent_from_the_source():
    assert "readonly_scope" not in Path(dr.__file__).read_text()


def test_the_script_imports_no_src_db_module_at_import():
    code = ("import importlib.util, sys; sys.path.insert(0, %r); "
            "s = importlib.util.spec_from_file_location('m', %r); m = importlib.util.module_from_spec(s); "
            "s.loader.exec_module(m); print([k for k in sys.modules if k.startswith('src.db')])"
            % (str(ROOT), str(ROOT / "scripts" / "pl_injury_duplicate_receipt.py")))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


def test_no_provider_call_and_no_key_needed(world, monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.setattr(dr.C, "_probe_get", lambda: pytest.fail("a provider read was set up"))
    code, out = run(world)
    assert code == 0
