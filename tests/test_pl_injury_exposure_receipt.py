"""Addendum 196 item 2 (#754), the PL injury exposure receipt (ARCHITECT 2026-11-01 09:00 ET): read-only.

A throwaway SQLite world (never data/), closing files as a closing run writes them, and a fake provider (no network).
Part (a) `exposure`: every bucket, the model's reduction equal to factors.injury_adjustment's, the rule count and the
undecidable count, the census, the Saturday matching (found, reversed, ambiguous, not found), the consumed-list test.
Part (b) `lineups`: started / bench / absent / AMBIGUOUS / unread (a failed read, no team id, a side not read in full),
the hidden count, the four-call cap, a cached re-run, the refusals. The DB bytes unchanged, and the stdin (embedded)
form."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pl_injury_exposure_receipt.py"
_spec = importlib.util.spec_from_file_location("pl_injury_exposure_receipt", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

NOW = "2026-11-01T12:00:00"
S_SAT = "2026-10-31T13:55:00.123456"           # the Saturday closing's sync stamp (both sides)
S_LATER = "2026-11-01T08:00:00"                # a later sync (Bournemouth's list overwritten since)
TEAMS = {"Bournemouth": "35", "Leeds": "63", "Manchester City": "50", "Brighton": "51", "Tottenham": "47",
         "Crystal Palace": None, "Aston Villa": "66", "Fulham": "36", "Arsenal": "42", "Coventry": "1346"}
PL_TEAMS = ("Bournemouth", "Leeds", "Manchester City", "Brighton", "Tottenham", "Crystal Palace", "Aston Villa",
            "Fulham", "Arsenal")

# Bournemouth: one entry per bucket (name, position, type, fixture)
BOU = [("E. J. Kroupi", "Attacker", "Questionable", "2001"),       # past (Saturday)
       ("A. Past", "Midfielder", "Missing Fixture", "2001"),       # past
       ("B. Next", "Attacker", "Missing Fixture", "3001"),         # next -> rule
       ("C. Cup", "Defender", "Missing Fixture", "4001"),          # upcoming, before the next PL match (a cup tie)
       ("D. Later", "Goalkeeper", "Missing Fixture", "3002"),      # later -> rule
       ("E. NoId", "Midfielder", "Missing Fixture", None),         # no fixture id -> undecidable
       ("F. NotStored", None, "Missing Fixture", "99999"),         # fixture not stored -> undecidable
       ("G. Dup", "Defender", "Missing Fixture", "5555"),          # held by 2+ -> undecidable
       ("H. Prev", "Defender", "Missing Fixture", "old3001"),      # next, through api_football_prev -> rule
       ("I. Quest", "Attacker", "Questionable", "3001"),           # next but Questionable -> no
       ("J. NoType", "Midfielder", None, "3001")]                  # next, no type -> no
LEE = [("D. James", "Attacker", "Missing Fixture", "2001"),
       ("N. Elvedi", "Defender", "Questionable", "2001"),
       ("A. Stach", "Midfielder", "Missing Fixture", "3003"),
       ("Z. Gone", "Defender", "Missing Fixture", "2001")]


def _dt(v):
    return datetime.fromisoformat(v)


def build_db(path: Path) -> None:
    from src.db.schema import (Base, Competition, CompetitionTeam, Injury, Match, MatchStatus, Sport, Team)
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        pl = Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England", type="LEAGUE")
        fac = Competition(sport=Sport.SOCCER, code="FAC", name="FA Cup", area="England", type="CUP")
        s.add_all([pl, fac])
        s.flush()
        t = {}
        for n, pid in TEAMS.items():
            t[n] = Team(sport=Sport.SOCCER, name=n, external_ids={"api_football": pid} if pid else {})
            s.add(t[n])
        s.flush()
        for n in PL_TEAMS:
            s.add(CompetitionTeam(competition_id=pl.id, team_id=t[n].id, season="2026/27"))
        s.add(CompetitionTeam(competition_id=pl.id, team_id=t["Coventry"].id, season="2025/26"))   # another season

        def match(mid, h, a, ko, ext, comp=pl, status=MatchStatus.SCHEDULED, score=(None, None)):
            s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=_dt(ko),
                        status=status, home_team_id=t[h].id, away_team_id=t[a].id, home_score=score[0],
                        away_score=score[1], external_ids=ext))
        fin = MatchStatus.FINISHED
        match(101, "Bournemouth", "Leeds", "2026-10-31T15:00:00", {"api_football": "2001"}, status=fin, score=(1, 2))
        match(102, "Manchester City", "Brighton", "2026-10-31T15:00:00", {"api_football": "2002"}, status=fin,
              score=(2, 2))
        match(103, "Crystal Palace", "Tottenham", "2026-10-31T17:30:00", {"api_football": "2003"}, status=fin,
              score=(0, 1))                                                     # Spurs–Palace, reversed
        match(104, "Aston Villa", "Fulham", "2026-10-31T12:30:00", {}, status=fin, score=(3, 1))   # no fixture id
        match(110, "Arsenal", "Leeds", "2026-10-31T20:00:00", {"api_football": "2010"}, comp=fac)  # not PL
        match(201, "Arsenal", "Bournemouth", "2026-11-08T14:00:00",
              {"api_football": "3001", "api_football_prev": ["old3001"]})
        match(202, "Bournemouth", "Brighton", "2026-11-22T15:00:00", {"api_football": "3002"})
        match(203, "Leeds", "Manchester City", "2026-11-09T16:30:00", {"api_football": "3003"})
        match(301, "Bournemouth", "Coventry", "2026-11-04T19:45:00", {"api_football": "4001"}, comp=fac)
        match(302, "Fulham", "Coventry", "2026-11-05T19:45:00", {"api_football": "4002"}, comp=fac)
        match(401, "Tottenham", "Coventry", "2026-09-01T19:45:00", {"api_football": "5555"}, comp=fac)
        match(402, "Brighton", "Coventry", "2026-09-02T19:45:00", {"api_football": "5555"}, comp=fac)
        s.flush()

        def inj(team, rows, stamp):
            for name, pos, typ, fid in rows:
                s.add(Injury(team_id=t[team].id, player_name=name, player_position=pos, type=typ,
                             reason="Knee Injury", fixture_source_id=fid, refreshed_at=_dt(stamp)))
        inj("Bournemouth", BOU, S_LATER)
        inj("Leeds", LEE, S_SAT)
        inj("Fulham", [("K. Cupman", "Attacker", "Missing Fixture", "4002"),     # upcoming, no next PL -> undecid.
                       ("L. Odd", "Attacker", "Doubtful", "4002")], S_SAT)          # another type word: never ruled
        s.commit()
    eng.dispose()


def row(mid, home, away, ko, hn, an, hc, ac, stamp, notes=None):
    return {"match_id": mid, "utc_date": ko, "competition": "PL", "season": "2026/27", "home_team": home,
            "away_team": away,
            "injuries": {"home_count": hc, "away_count": ac, "home_names": hn[:8], "away_names": an[:8]},
            "input_quality": {"lineups": "none", "injuries_synced_at": stamp,
                              "injuries": {"home": {"count": hc, "synced_at": stamp if hc else None},
                                           "away": {"count": ac, "synced_at": stamp if ac else None}}},
            "prediction": {"factor_breakdown": {"home_injuries_count": hc, "away_injuries_count": ac,
                                                "factor_notes": notes if notes is not None else [],
                                                "lineup_kind": None}}}


def closing(ex: Path, start: str, rows: list, fam="SOCCER"):
    ex.mkdir(parents=True, exist_ok=True)
    st = datetime.fromisoformat(start)
    doc = {"exported_at": start + "Z", "git_sha": "0d3e84df", "sport": fam.lower(), "competition_code": "PL",
           "count": len(rows), "predictions": rows,
           "closing": {"family": fam, "start": start + "Z", "run_id": f"run-{st:%m%d%H%M}",
                       "match_ids": [r["match_id"] for r in rows], "called_off": []}}
    (ex / f"closing_{fam}_{st:%Y-%m-%dT%H%M}Z.json").write_text(json.dumps(doc))


BOU_NAMES = [n for n, *_ in BOU][:8]
LEE_NAMES = [n for n, *_ in LEE]
NOTES = ["home missing 9 (-25% xG)", "away missing 4 (-15% xG)"]


def write_exports(ex: Path, ids=(101, 102, 103, 104)):
    """The Saturday's closing files; `ids` are the writing machine's match ids."""
    closing(ex, "2026-10-31T12:00:00", [row(ids[3], "Aston Villa", "Fulham", "2026-10-31T12:30:00", [],
                                            ["K. Cupman"], 0, 1, S_SAT)])
    closing(ex, "2026-10-31T14:00:00", [row(ids[0], "Bournemouth", "Leeds", "2026-10-31T15:00:00", BOU_NAMES,
                                            LEE_NAMES, 7, 4, "2026-10-31T12:00:00")])     # an earlier run
    closing(ex, "2026-10-31T14:30:00", [row(ids[0], "Bournemouth", "Leeds", "2026-10-31T15:00:00", BOU_NAMES,
                                            LEE_NAMES, 9, 4, S_SAT, NOTES),
                                        row(ids[1], "Manchester City", "Brighton", "2026-10-31T15:00:00",
                                            ["R. Dias"], ["S. March"], 1, 1, S_SAT)])
    closing(ex, "2026-10-31T17:00:00", [row(ids[2], "Crystal Palace", "Tottenham", "2026-10-31T17:30:00",
                                            ["E. Nketiah"], ["P. Porro", "X. Simons", "J. Maddison"], 1, 3, S_SAT)])
    closing(ex, "2026-10-31T14:30:00", [row(9999, "X", "Y", "2026-10-31T15:00:00", [], [], 0, 0, None)], fam="MLB")


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "copy.db"
    build_db(db)
    ex = tmp_path / "exports"
    write_exports(ex)
    host = tmp_path / "laptop_exports" / "host"
    write_exports(host, ids=(70101, 70102, 70103, 70104))          # the host's ids: never the laptop's
    return {"db": db, "ex": ex, "host": host, "save": tmp_path / "payloads", "tmp": tmp_path}


def exposure(w, *extra):
    out = []
    code = rc.main(["exposure", "--db", str(w["db"]), "--now", NOW, "--exports", str(w["ex"]), *extra],
                   echo=out.append)
    return code, out


def summary(out, tag=rc.TAG):
    assert out[-1].startswith(tag + " ")
    return json.loads(out[-1][len(tag) + 1:])


def line(out, frag):
    hits = [ln for ln in out if frag in ln]
    assert hits, frag
    return hits[0]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _db_write(w, fn):
    """A test-only change to the throwaway world (never data/)."""
    eng = create_engine(f"sqlite:///{w['db']}")
    with Session(eng) as s:
        fn(s)
        s.commit()
    eng.dispose()


# ---- part (a): exposure ---------------------------------------------------------------------------------------------

def test_exposure_header_census_first_and_teams(world):
    code, out = exposure(world)
    assert code == 0
    assert out[0].startswith("PL INJURY EXPOSURE RECEIPT") and "now 2026-11-01T12:00:00Z" in out[0]
    assert f"database --db {world['db'].resolve()} (mode=ro URI)" in out[0]
    assert "PL 2026/27: 9 team(s)" in out[0]                                     # Coventry's 2025/26 row left out
    assert any(ln.startswith("WHAT THE MODEL COUNTS") for ln in out)
    assert any('"Missing Fixture" AND the fixture it names is this fixture or a later one' in ln for ln in out)
    assert "Nothing is changed in the model" in "\n".join(out)
    census = [i for i, ln in enumerate(out) if ln.startswith("CENSUS")]
    blocks = [i for i, ln in enumerate(out) if ln.startswith("\n== ")]
    assert census and blocks and census[0] < blocks[0]
    c = out[census[0]]
    assert ("'(no type stored)' 1 · 'Doubtful' 1 · 'Missing Fixture' 12 · 'Questionable' 3" in c)
    sm = summary(out)
    assert sm["teams"] == 9 and sm["entries"] == 17
    assert sm["types"] == {"Missing Fixture": 12, "Questionable": 3, "(no type stored)": 1, "Doubtful": 1}


def test_exposure_every_bucket(world):
    _, out = exposure(world)
    want = {"E. J. Kroupi": "past (PL match 101", "A. Past": "past (PL match 101",
            "B. Next": "next (PL match 201 2026-11-08 14:00Z, +7.1 d)",
            "C. Cup": "upcoming, before the next PL match (FAC match 301",
            "D. Later": "later (PL match 202", "E. NoId": "no fixture id stored",
            "F. NotStored": "fixture not stored (provider fixture 99999)",
            "G. Dup": "fixture id held by 2+ stored matches (provider fixture 5555: matches 401, 402)",
            "H. Prev": "next (PL match 201 2026-11-08 14:00Z, +7.1 d (a previous provider id of the match))",
            "K. Cupman": "upcoming, no next PL match stored (FAC match 302"}
    for name, frag in want.items():
        assert frag in line(out, f"    {name} ·"), name
    assert "-0.9 d" in line(out, "    A. Past ·")
    assert "position (none) · type 'Missing Fixture'" in line(out, "    F. NotStored ·")
    assert "type (no type stored)" in line(out, "    J. NoType ·")
    assert "next PL match: match 201 away v Arsenal 2026-11-08 14:00Z (+7.1 d" in line(out, "== Bournemouth")
    assert "next PL match: none stored" in line(out, "== Fulham")
    assert "Arsenal (team" in line(out, "== Arsenal") and "no stored row for the team" in "\n".join(out)
    sm = summary(out)
    assert sm["buckets"] == {"past": 5, "next": 5, "upcoming, before the next PL match": 1, "later": 1,
                             "no fixture id stored": 1, "fixture not stored": 1,
                             "fixture id held by 2+ stored matches": 1, "upcoming, no next PL match stored": 2}


def test_exposure_model_reduction_is_the_factors_and_the_rule_and_undecidable(world):
    from types import SimpleNamespace

    from src.models.factors import injury_adjustment

    def red(rows):
        return 1 - injury_adjustment(home_injuries=[SimpleNamespace(player_position=p, player_name=n)
                                                    for n, p, _t, _f in rows]).home_xg_multiplier
    _, out = exposure(world)
    sm = summary(out)
    b = sm["per_team"]["Bournemouth"]
    assert b["model"] == 11 and b["model_reduction"] == round(red(BOU), 4) == 0.25           # at the cap
    rule = [x for x in BOU if x[0] in ("B. Next", "D. Later", "H. Prev")]
    und = [x for x in BOU if x[0] in ("E. NoId", "F. NotStored", "G. Dup")]
    assert b["rule"] == 3 and b["rule_reduction"] == round(red(rule), 4)
    assert b["undecidable"] == 3
    hdr = line(out, "  MODEL 11 (reduction 25.0%)")
    assert f"RULE 3 (reduction {red(rule) * 100:.1f}%)" in hdr
    assert f"+3 undecidable (at most 6, reduction {red(rule + und) * 100:.1f}%)" in hdr
    for n, r in (("B. Next", "yes"), ("C. Cup", "no"), ("E. NoId", "undecidable"), ("I. Quest", "no"),
                 ("J. NoType", "no"), ("A. Past", "no")):
        assert line(out, f"    {n} ·").endswith(f"model yes · rule {r}"), n
    lee = sm["per_team"]["Leeds"]
    assert lee["model"] == 4 and lee["rule"] == 1 and lee["undecidable"] == 0
    ful = sm["per_team"]["Fulham"]
    assert ful["model"] == 2 and ful["rule"] == 0 and ful["undecidable"] == 1     # "Doubtful" never counted
    assert line(out, "    L. Odd ·").endswith("rule no")
    assert sm["model"] == 17 and sm["rule"] == 4 and sm["undecidable"] == 4
    assert sm["at_cap_model"] == 1 and sm["at_cap_rule"] == 0
    assert "type x bucket: '(no type stored)': next 1 | 'Missing Fixture': past 1 · next 2" in \
        line(out, "  type x bucket: '(no type stored)'")


def test_exposure_totals_and_the_difference_sorted(world):
    _, out = exposure(world)
    tot = line(out, "\nTOTALS:")
    assert "teams 9 · entries 17 · model count 17 · rule count 4 · undecidable 4" in tot
    assert "at the 25% cap under the model 1: Bournemouth · under the rule 0: none" in \
        line(out, "at the 25% cap")
    i = out.index("  reduction difference per team (model - rule), largest first:")
    assert [ln.split(":")[0].strip() for ln in out[i + 1:i + 4]] == ["Fulham", "Bournemouth", "Leeds"]
    assert out[i + 2].startswith("    Bournemouth: +11.5 pp (model 25.0% [11] · rule 13.5% [3] · +3 undecidable")


def test_exposure_saturday_found_reversed_and_the_consumed_test(world):
    _, out = exposure(world)
    assert "match 101 Bournemouth v Leeds 2026-10-31 15:00Z status finished score 1-2 · api_football fixture 2001" \
        in line(out, "  match 101 Bournemouth v Leeds")
    assert "match 110" not in "\n".join(ln for ln in out if ln.startswith("  match "))          # FAC: not PL
    assert "Spurs–Palace (tot-cry): match 103 home Crystal Palace v away Tottenham" in line(out, "Spurs–Palace (tot")
    assert "closing row: run 2026-10-31 14:30Z (latest of 2)" in line(out, "closing row: run 2026-10-31 14:30Z")
    home = line(out, "    HOME Bournemouth: injuries.home_count 9")
    assert "home_names ['E. J. Kroupi'" in home and f"synced_at {S_SAT}" in home
    i = out.index(home)
    assert out[i + 1] == ("      the stored list is a later (or different) sync: refreshed_at "
                          "2026-11-01T08:00:00.000000 vs consumed 2026-10-31T13:55:00.123456; count 11 vs 9")
    j = out.index(line(out, "    AWAY Leeds: injuries.away_count 4"))
    assert out[j + 1] == ("      the stored list is the one the closing row consumed (the per-entry types above ARE "
                          "Saturday's)")
    assert "empty as consumed (count 0) and no stored row now: nothing to compare" in \
        out[out.index(line(out, "    HOME Aston Villa: injuries.home_count 0")) + 1]
    # both conditions: Fulham's one stamp equals synced_at, but 2 stored rows against the row's 1
    k = out.index(line(out, "    AWAY Fulham: injuries.away_count 1"))
    assert out[k + 1] == ("      the stored list is a later (or different) sync: refreshed_at "
                          "2026-10-31T13:55:00.123456 vs consumed 2026-10-31T13:55:00.123456; count 2 vs 1")
    sat = summary(out)["saturday"]
    assert sat["bou-lee"]["match"] == 101 and sat["tot-cry"]["fixture"] == "2003"
    assert sat["avl-ful"]["fixture"] is None
    assert "no closing row" not in line(out, "Villa–Fulham (avl-ful)")


def test_exposure_consumed_needs_the_stamp_as_well_as_the_count(world, tmp_path):
    """Bournemouth's 11 stored rows against a row counting 11 but consumed at another stamp: not the consumed list."""
    ex = tmp_path / "count_equal"
    closing(ex, "2026-10-31T14:30:00", [row(101, "Bournemouth", "Leeds", "2026-10-31T15:00:00", BOU_NAMES,
                                            LEE_NAMES, 11, 4, S_SAT)])
    _, out = exposure(world, "--exports", str(ex))
    i = out.index(line(out, "    HOME Bournemouth: injuries.home_count 11"))
    assert out[i + 1] == ("      the stored list is a later (or different) sync: refreshed_at "
                          "2026-11-01T08:00:00.000000 vs consumed 2026-10-31T13:55:00.123456; count 11 vs 11")
    assert rc.consumed([{"refreshed_at": S_SAT}], 1, S_SAT).startswith("the stored list is the one")
    assert rc.consumed([{"refreshed_at": S_SAT}], 2, S_SAT).startswith("the stored list is a later")
    assert rc.consumed([{"refreshed_at": S_LATER}], 1, S_SAT).startswith("the stored list is a later")


def test_exposure_next_is_never_a_row_that_cannot_be_played(world):
    """Law 4: a stale_orphan PL row with a future date is passed over (and printed), never the team's NEXT."""
    from src.db.schema import Match, MatchStatus

    def change(s):
        s.get(Match, 201).status = MatchStatus.STALE_ORPHAN
    _db_write(world, change)
    _, out = exposure(world)
    hdr = line(out, "== Bournemouth")
    assert "next PL match: match 202 home v Brighton 2026-11-22 15:00Z" in hdr
    assert "passed over (status not scheduled or live): match 201 2026-11-08 14:00Z status stale_orphan" in hdr
    assert "next PL match: none stored" in line(out, "== Arsenal") and "match 201" in line(out, "== Arsenal")
    assert ("upcoming, before the next PL match (PL match 201 2026-11-08 14:00Z, +7.1 d, status stale_orphan)"
            in line(out, "    B. Next ·")) and line(out, "    B. Next ·").endswith("rule no")
    assert "next (PL match 202" in line(out, "    D. Later ·") and line(out, "    D. Later ·").endswith("rule yes")


def test_exposure_a_fixture_of_a_match_the_team_is_not_in_is_undecidable(world):
    from src.db.schema import Injury, Team

    def change(s):
        lee = s.query(Team).filter_by(name="Leeds").one()
        s.add(Injury(team_id=lee.id, player_name="M. Elsewhere", player_position="Attacker", type="Missing Fixture",
                     reason="Knee Injury", fixture_source_id="4002", refreshed_at=_dt(S_SAT)))
    _db_write(world, change)
    _, out = exposure(world)
    ln = line(out, "    M. Elsewhere ·")
    assert ("fixture held by a match the team is not in (FAC match 302 2026-11-05 19:45Z, +4.3 d; provider fixture "
            "4002)") in ln and ln.endswith("rule undecidable")
    lee = summary(out)["per_team"]["Leeds"]
    assert lee["model"] == 5 and lee["rule"] == 1 and lee["undecidable"] == 1


def test_exposure_the_configured_db_goes_through_readonly_scope(world, monkeypatch):
    """The host block's likeliest form (no --db): the configured file through database.readonly_scope (#688's test)."""
    from src.db import database
    eng = create_engine(f"sqlite:///{world['db']}", future=True)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(database, "_engine", eng)
    called = []
    real = database.readonly_scope

    def spy():
        called.append(1)
        return real()
    monkeypatch.setattr(database, "readonly_scope", spy)
    before = _sha(world["db"])
    out = []
    code = rc.main(["exposure", "--now", NOW, "--exports", str(world["ex"])], echo=out.append)
    eng.dispose()
    assert code == 0 and called == [1] and _sha(world["db"]) == before
    assert "(database.readonly_scope: mode=ro URI)" in out[0]
    assert summary(out)["rule"] == 4


def test_exposure_the_configured_db_missing_is_refused(world, monkeypatch):
    from src.db import database
    missing = world["tmp"] / "absent.db"
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{missing}")))
    out = []
    code = rc.main(["exposure", "--now", NOW, "--exports", str(world["ex"])], echo=out.append)
    assert code == 2 and "REFUSED: no DB file" in out[0] and not missing.exists()


def test_exposure_saturday_not_found_and_ambiguous(world):
    from src.db.schema import Match, MatchStatus, Sport

    def change(s):
        s.get(Match, 102).utc_date = _dt("2026-11-30T15:00:00")                 # Man City–Brighton moved away
        m = s.get(Match, 104)
        s.add(Match(id=105, sport=Sport.SOCCER, competition_id=m.competition_id, season="2026/27",
                    utc_date=_dt("2026-10-31T19:00:00"), status=MatchStatus.FINISHED, home_team_id=m.away_team_id,
                    away_team_id=m.home_team_id, external_ids={}))              # a second Villa–Fulham that day
    _db_write(world, change)
    _, out = exposure(world)
    assert line(out, "Man City–Brighton (mci-bri)").endswith("not found among the PL matches on 2026-10-31")
    amb = line(out, "Villa–Fulham (avl-ful)")
    assert "AMBIGUOUS, 2 candidates: match 104 Aston Villa v Fulham; match 105 Fulham v Aston Villa" in amb
    sat = summary(out)["saturday"]
    assert sat["mci-bri"] == "not found" and sat["avl-ful"] == "AMBIGUOUS"


def test_exposure_no_closing_row_and_a_missing_exports_dir_are_never_fatal(world):
    code, out = exposure(world, "--exports", str(world["tmp"] / "nope"))
    assert code == 0
    assert "the exports directory" in line(out, "closing files: the exports directory") and "is missing" in \
        line(out, "closing files: the exports directory")
    (world["tmp"] / "empty").mkdir()
    code, out = exposure(world, "--exports", str(world["tmp"] / "empty"))
    assert code == 0 and "    no closing row for match 101 in" in line(out, "no closing row for match 101")


def test_exposure_a_row_of_other_teams_is_never_used(world, tmp_path):
    ex = tmp_path / "other"
    closing(ex, "2026-10-31T14:30:00", [row(101, "Someone", "Else", "2026-10-31T15:00:00", [], [], 0, 0, None)])
    _, out = exposure(world, "--exports", str(ex))
    assert "the row's teams are not the stored match's: the row is not used" in "\n".join(out)


def test_exposure_refusals(world, monkeypatch, tmp_path):
    out = []
    code = rc.main(["exposure", "--db", str(world["db"]), "--now", NOW, "--season", "1999/00"], echo=out.append)
    assert code == 2 and out[0].startswith("REFUSED: no team in competition_teams for PL '1999/00'")
    out = []
    code = rc.main(["exposure", "--db", str(tmp_path / "missing.db"), "--now", NOW], echo=out.append)
    assert code == 2 and "REFUSED: no DB file" in out[0] and not (tmp_path / "missing.db").exists()
    monkeypatch.setattr(rc, "ROOT", tmp_path)                                   # a broken refusal never touches data/
    out = []
    target = tmp_path / "data" / "sp.db"
    code = rc.main(["exposure", "--db", str(target), "--now", NOW], echo=out.append)
    assert code == 2 and out[0].startswith("REFUSED: --db") and "under data/" in out[0] and not target.exists()


def test_exposure_a_missing_column_is_refused(world):
    from sqlalchemy import text
    eng = create_engine(f"sqlite:///{world['db']}")
    with eng.begin() as c:
        c.execute(text("ALTER TABLE injuries DROP COLUMN fixture_source_id"))
    eng.dispose()
    code, out = exposure(world)
    assert code == 2 and out == ["REFUSED: columns fixture_source_id not in injuries (law 1)"]


def test_exposure_db_bytes_unchanged(world):
    before = _sha(world["db"])
    code, _ = exposure(world)
    assert code == 0 and _sha(world["db"]) == before


def test_exposure_bad_now_is_argparses_exit_2(world):
    with pytest.raises(SystemExit) as e:
        exposure(world, "--now", "2026-13-45T00:00")
    assert e.value.code == 2


def test_exposure_embedded_from_stdin(world):
    """The host block's form: the script's text on stdin, run in a checkout root."""
    before = _sha(world["db"])
    r = subprocess.run([sys.executable, "-", "exposure", "--db", str(world["db"]), "--now", NOW, "--exports",
                        str(world["ex"])], input=SCRIPT.read_text(), cwd=str(ROOT), capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    out = r.stdout.splitlines()
    assert out[0].startswith("PL INJURY EXPOSURE RECEIPT") and out[-1].startswith(rc.TAG + " ")
    assert json.loads(out[-1][len(rc.TAG) + 1:])["rule"] == 4
    assert _sha(world["db"]) == before


def test_exposure_imports_only_what_v161_holds():
    """Part (a) runs on the host at tag v1.6.1: no import of #688's script (not on v1.6.1) at module load, and only
    src.walters.redated, src.db.*, src.models.factors from src when exposure runs."""
    text = SCRIPT.read_text()
    srcs = sorted({ln.strip() for ln in text.splitlines() if ln.strip().startswith(("from src", "import src"))})
    assert srcs == ["from src.db import database", "from src.db.schema import Competition, CompetitionTeam, Injury, "
                    "Match, Sport, Team", "from src.db.schema import Match, Sport, Team",
                    "from src.ingestion.team_merge import source_ids",
                    "from src.models.factors import injury_adjustment",
                    "from src.walters import redated  # noqa: E402   (on v1.6.1; imports no src.db module)"]
    # team_merge is read by part (b) only (inside db_lookup); #688's script is loaded by part (b) only
    assert text.count('_load("pl_injury_classification_receipt")') == 1


# ---- part (b): lineups ----------------------------------------------------------------------------------------------

def slot(pid, name):
    return {"player": {"id": pid, "name": name, "number": 1, "pos": "M", "grid": None}}


def team(n, pid):
    return {"id": pid, "name": n, "logo": ""}


def xi(base, *slots):
    """An XI of eleven named starters: the given slots, then fillers no listed name matches."""
    return [*slots, *(slot(base + k, f"Filler Zz{base + k}") for k in range(11 - len(slots)))]


def bench(base, *slots):
    return [*slots, slot(base + 50, f"Benchman Qq{base}")]


def answers():
    return {
        ("fixtures/lineups", "2001"): (200, {}, [                       # the away block first; a provider name unlike
            {"team": team("Leeds", 63), "formation": "3-5-2", "coach": {},    # the DB's: sides by provider team id
             "startXI": xi(110, slot(10, "Daniel James"), slot(11, "Nico Elvedi")),
             "substitutes": bench(110, slot(12, "Anton Stach"))},
            {"team": team("AFC Bournemouth", 35), "formation": "4-2-3-1", "coach": {},
             "startXI": xi(100, slot(1, "Adam Past"), slot(2, "Carl Cup")),
             "substitutes": bench(100, slot(3, "Eli Junior Kroupi"), slot(4, "Chris Cup"))}]),
        ("fixtures/lineups", "2002"): (500, {}, []),                                            # FAILED
        ("fixtures/lineups", "2003"): (200, {}, [
            {"team": team("Crystal Palace", 52), "startXI": xi(200, slot(20, "Dean Henderson")),
             "substitutes": bench(200)},
            {"team": team("Tottenham", 47), "startXI": xi(300, slot(30, "Pedro Porro")),
             "substitutes": [None, slot(31, "Xavi Simons")]}]),                                 # a member malformed
        ("fixtures/lineups", "2004"): (200, {}, [
            {"team": team("Aston Villa", 66), "startXI": xi(400, slot(40, "Emiliano Martinez")),
             "substitutes": bench(400)},
            {"team": team("Fulham", 36), "startXI": xi(500, slot(50, "Bernd Leno")), "substitutes": bench(500)}]),
    }


class FakeGet:
    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, path, **params):
        self.calls.append((path, params))
        return self.table.get((path, str(params.get("fixture"))), (404, {"x": "not in the fake"}, []))


def lineups(w, *extra, table=None, get=None):
    out = []
    g = get or FakeGet(table if table is not None else answers())
    code = rc.main(["lineups", "--exports", str(w["host"]), "--db", str(w["db"]), "--save", str(w["save"]), *extra],
                   echo=out.append, get=g)
    return code, out, g


def test_lineups_classes_and_header(world):
    code, out, g = lineups(world)
    assert code == 0
    sm = summary(out, rc.TAG_LINEUPS)
    assert [c[1]["fixture"] for c in g.calls] == ["2001", "2002", "2003"]       # Villa–Fulham: no fixture id, no call
    assert sm["calls"] == {"made": 3, "cached": 0, "failed": 1, "empty": 0, "cap": 4}
    assert out[1].startswith("PROVIDER: calls made 3 · cached answers 0 · failed 1 · empty 0 · call cap 4")
    assert "(5 read;" in out[0]                                               # the MLB file read, never used
    # law 1: the keys printed before any field
    i = out.index("PROVIDER KEYS (law 1, printed from the first real answer before any field is read):")
    assert out[i + 1] == "  first real answer: fixture 2001 (Bournemouth–Leeds)"   # response[0] is Leeds' block
    assert out[i + 2] == "  response[0] keys ['coach', 'formation', 'startXI', 'substitutes', 'team']"
    assert out[i + 3] == "  startXI[0] keys ['player']"
    assert out[i + 4] == "  startXI[0][\"player\"] keys ['grid', 'id', 'name', 'number', 'pos']"
    # the classes
    assert line(out, "    E. J. Kroupi:").startswith("    E. J. Kroupi: bench — Eli Junior Kroupi (initial form")
    assert line(out, "    A. Past:").startswith("    A. Past: started — Adam Past")
    assert line(out, "    B. Next:") == ("    B. Next: absent — no name in the side's XI or bench matches; a name form "
                                         "the match cannot see is possible")
    assert line(out, "    C. Cup:") == "    C. Cup: AMBIGUOUS — AMBIGUOUS: Carl Cup (xi) | Chris Cup (bench)"
    assert line(out, "    D. James:").startswith("    D. James: started — Daniel James")
    assert line(out, "    N. Elvedi:").startswith("    N. Elvedi: started — Nico Elvedi")
    assert line(out, "    A. Stach:").startswith("    A. Stach: bench — Anton Stach")
    assert line(out, "    Z. Gone:").startswith("    Z. Gone: absent")
    # the failed read: unread, never classed
    assert line(out, "    R. Dias:") == "    R. Dias: unread — the read FAILED"
    assert "  FAILED fixture 2002 lineups: HTTP 500" in out
    # no provider team id: unread, and the answer's team names still printed
    assert line(out, "    E. Nketiah:") == ("    E. Nketiah: unread — no provider team id (team 6 'Crystal Palace' "
                                           "stores no api_football id)")
    assert "  the answer's teams: Crystal Palace (team id 52), Tottenham (team id 47)" in out
    # a side not read in full: a found name classes, a not-found one is unread
    assert line(out, "    P. Porro:").startswith("    P. Porro: started — Pedro Porro (initial form")
    assert line(out, "    X. Simons:").startswith("    X. Simons: bench")
    assert line(out, "    J. Maddison:").startswith("    J. Maddison: unread — not found, and the side is not listed "
                                                      "in full")
    assert "NOT READ IN FULL" in line(out, "    bench (1): Xavi Simons")
    assert "substitutes[0]: not a slot with a named player" in line(out, "NOT THE PROVIDER'S SHAPE 1")
    assert sm["games"]["bou-lee"] == {"started": 3, "bench": 2, "absent": 6, "AMBIGUOUS": 1, "hidden": 1,
                                      "count_unknown_sides": 0}
    assert sm["games"]["mci-bri"] == {"unread": 2, "hidden": 0, "count_unknown_sides": 0}
    assert sm["games"]["avl-ful"] == {"unread": 1, "hidden": 0, "count_unknown_sides": 0}
    assert "  the answer's teams: Leeds (team id 63), AFC Bournemouth (team id 35)" in out
    assert "fixture id unread: re-run with --fixture avl-ful=ID (the host block prints it)" in \
        line(out, "fixture id unread")


def test_lineups_fixture_and_rows_by_name_never_by_host_id(world):
    _, out, _ = lineups(world)
    assert "closing row: match 70101 (host id) Bournemouth v Leeds" in line(out, "closing row: match 70101")
    assert "latest of 2" in line(out, "closing row: match 70101")
    assert "provider fixture 2001 (from the laptop DB (match 101, external_ids['api_football']))" in \
        line(out, "provider fixture 2001")


def test_lineups_hidden_count_and_factor_notes(world):
    _, out, _ = lineups(world)
    assert "    1 entries the export does not name (count 9, 8 names kept)" in out
    assert ("  factor_notes (prediction.factor_breakdown.factor_notes, verbatim): "
            "['home missing 9 (-25% xG)', 'away missing 4 (-15% xG)']") in out
    sm = summary(out, rc.TAG_LINEUPS)
    assert sm["hidden"] == 1 and sm["count_unknown_sides"] == 0
    # per game too (spec item 7): the body's game totals, the TOTALS line per game, the summary's games
    assert line(out, "  game totals: started 3").endswith("· entries the export does not name 1")
    assert line(out, "  Bournemouth–Leeds: started 3").endswith("· entries the export does not name 1")
    assert line(out, "  Spurs–Palace: ").endswith("· entries the export does not name 0")
    assert sm["games"]["bou-lee"]["hidden"] == 1 and sm["games"]["tot-cry"]["hidden"] == 0


def test_lineups_a_missing_count_is_unknown_never_0(world, tmp_path):
    ex = tmp_path / "nocount"
    r = row(1, "Bournemouth", "Leeds", "2026-10-31T15:00:00", BOU_NAMES, LEE_NAMES, 9, 4, S_SAT)
    del r["injuries"]["home_count"]
    closing(ex, "2026-10-31T14:30:00", [r])
    out = []
    rc.main(["lineups", "--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])],
            echo=out.append, get=FakeGet(answers()))
    assert "injuries.home_count UNKNOWN" in line(out, "  HOME Bournemouth")
    assert "count UNKNOWN" in line(out, "    count UNKNOWN")
    sm = summary(out, rc.TAG_LINEUPS)
    assert sm["count_unknown_sides"] == 1 and sm["games"]["bou-lee"]["count_unknown_sides"] == 1
    assert "· sides with count UNKNOWN 1" in line(out, "  Bournemouth–Leeds: ")


def test_lineups_fixture_override_makes_the_fourth_call(world):
    code, out, g = lineups(world, "--fixture", "avl-ful=2004")
    assert code == 0 and len(g.calls) == 4
    assert "provider fixture 2004 (from --fixture)" in line(out, "provider fixture 2004")
    assert line(out, "    K. Cupman:").startswith("    K. Cupman: absent")


def test_lineups_the_cap_and_more_than_four_refused(world):
    code, out, g = lineups(world, "--max-calls", "2")
    assert code == 0 and len(g.calls) == 2
    sm = summary(out, rc.TAG_LINEUPS)
    assert sm["incomplete"] is True and "INCOMPLETE: the cap stopped 1 read(s)" in out[1]
    assert line(out, "    P. Porro:") == "    P. Porro: unread — capped (the call cap stopped the read)"
    for n in ("5", "-1"):
        code, out, g = lineups(world, "--max-calls", n)
        assert code == 2 and out[0].startswith(f"REFUSED: --max-calls {n}") and g.calls == []


def test_lineups_a_cached_rerun_makes_no_call(world, monkeypatch):
    t = dict(answers())
    t[("fixtures/lineups", "2002")] = (200, {}, [{"team": team("Manchester City", 50), "startXI": [slot(60, "Rúben Dias")],
                                                 "substitutes": []}])
    code, _out, g = lineups(world, "--fixture", "avl-ful=2004", table=t)
    assert code == 0 and len(g.calls) == 4
    assert sorted(p.relative_to(world["save"]).as_posix() for p in world["save"].rglob("*.json")) == \
        ["2001/lineups.json", "2002/lineups.json", "2003/lineups.json", "2004/lineups.json"]
    code, out, g2 = lineups(world, "--fixture", "avl-ful=2004", table=t)
    assert code == 0 and g2.calls == []
    assert summary(out, rc.TAG_LINEUPS)["calls"]["cached"] == 4
    assert line(out, "    R. Dias:").startswith("    R. Dias: started — Rúben Dias")
    # a cached re-run needs no key: a missing key refuses only when a call is needed (and a regression that asks
    # anyway fails here, never reaching the provider)
    def never(*_a, **_k):
        raise AssertionError("a cached re-run called the provider")
    monkeypatch.setattr(rc, "_probe_get", lambda: (never, "dummy-key"))
    out = []
    code = rc.main(["lineups", "--exports", str(world["host"]), "--db", str(world["db"]), "--save",
                    str(world["save"]), "--fixture", "avl-ful=2004"], echo=out.append)
    assert code == 0


def test_lineups_no_key_is_refused_before_any_call(world, monkeypatch):
    monkeypatch.setattr(rc, "_probe_get", lambda: (None, ""))
    out = []
    code = rc.main(["lineups", "--exports", str(world["host"]), "--db", str(world["db"]), "--save",
                    str(world["save"])], echo=out.append)
    assert code == 2 and out == ["REFUSED: no API_FOOTBALL_KEY (environment or .env)"]


def test_lineups_no_closing_row_and_ambiguous_make_no_call(world, tmp_path):
    code, out, g = lineups(world, "--date", "2026-11-07")
    assert code == 0 and g.calls == []
    assert line(out, "== Bournemouth–Leeds") and f"  no closing row in {world['host']}: no call" in out
    ex = tmp_path / "amb"
    closing(ex, "2026-10-31T14:30:00", [row(1, "Bournemouth", "Leeds", "2026-10-31T15:00:00", [], [], 0, 0, None),
                                        row(2, "Leeds", "Bournemouth", "2026-10-31T19:00:00", [], [], 0, 0, None)])
    out = []
    g = FakeGet(answers())
    rc.main(["lineups", "--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])],
            echo=out.append, get=g)
    assert g.calls == [] and "  AMBIGUOUS: match 1 Bournemouth v Leeds; match 2 Leeds v Bournemouth: no call" in out


def test_lineups_a_failed_read_is_not_kept_and_asked_again(world):
    lineups(world)
    assert not (world["save"] / "2002").exists()
    _, _out, g = lineups(world)
    assert [c[1]["fixture"] for c in g.calls] == ["2002"]


def test_lineups_save_and_db_under_data_refused(world, monkeypatch):
    monkeypatch.setattr(rc, "ROOT", world["tmp"])
    target = world["tmp"] / "data" / "lineups_test"
    out = []
    code = rc.main(["lineups", "--exports", str(world["host"]), "--db", str(world["db"]), "--save", str(target)],
                   echo=out.append, get=FakeGet(answers()))
    assert code == 2 and out[0].startswith("REFUSED: --save") and "under data/" in out[0] and not target.exists()
    dbt = world["tmp"] / "data" / "laptop.db"
    out = []
    code = rc.main(["lineups", "--exports", str(world["host"]), "--db", str(dbt), "--save", str(world["save"])],
                   echo=out.append, get=FakeGet(answers()))
    assert code == 2 and out[0].startswith("REFUSED: --db") and not dbt.exists()


def test_lineups_db_bytes_unchanged(world):
    before = _sha(world["db"])
    code, _out, _g = lineups(world)
    assert code == 0 and _sha(world["db"]) == before


def test_lineups_bad_fixture_arg_is_argparses_exit_2(world):
    with pytest.raises(SystemExit) as e:
        lineups(world, "--fixture", "nope=1")
    assert e.value.code == 2


def test_lineups_an_xi_not_listed_in_full_is_unread_never_absent(world):
    """Law 4: an empty XI and bench (a lineup the provider did not post), or an XI short of eleven, is not a side read
    in full: a listed name not found there is unread, never absent."""
    t = dict(answers())
    code, blocks, rows = t[("fixtures/lineups", "2001")]
    t[("fixtures/lineups", "2001")] = (code, blocks, [{**rows[0], "startXI": [], "substitutes": []}, rows[1]])
    _, out, _ = lineups(world, table=t)
    for n in ("D. James", "N. Elvedi", "A. Stach", "Z. Gone"):
        assert line(out, f"    {n}:").startswith(f"    {n}: unread — not found, and the side is not listed in full"), n
    assert "NOT READ IN FULL" in line(out, "    bench (0): none")
    shape = line(out, "NOT THE PROVIDER'S SHAPE")
    assert "Bournemouth–Leeds (fixture 2001) away startXI: 0 named starter(s), not 11" in shape
    assert "Bournemouth–Leeds (fixture 2001) away substitutes: empty" in shape
    assert summary(out, rc.TAG_LINEUPS)["games"]["bou-lee"].get("absent") == 5     # Bournemouth's, read in full
    # an XI of ten named starters: a not-found name is unread
    t[("fixtures/lineups", "2001")] = (code, blocks, [{**rows[0], "startXI": rows[0]["startXI"][:10]}, rows[1]])
    _, out, _ = lineups(world, "--save", str(world["tmp"] / "p2"), table=t)
    assert line(out, "    Z. Gone:").startswith("    Z. Gone: unread")
    assert line(out, "    D. James:").startswith("    D. James: started")
    assert "away startXI: 10 named starter(s), not 11" in line(out, "NOT THE PROVIDER'S SHAPE")


def test_lineups_a_row_name_that_is_not_a_name_is_counted_never_classed(world, tmp_path):
    ex = tmp_path / "badnames"
    r = row(1, "Bournemouth", "Leeds", "2026-10-31T15:00:00", ["E. J. Kroupi", None, "  "], LEE_NAMES, 3, 4, S_SAT)
    closing(ex, "2026-10-31T14:30:00", [r])
    out = []
    rc.main(["lineups", "--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])],
            echo=out.append, get=FakeGet(answers()))
    assert not [ln for ln in out if ln.startswith(("    None:", "    :", "      :"))]
    shape = line(out, "NOT THE PROVIDER'S SHAPE")
    assert "closing row injuries.home_names[1]: None is not a name (never classed)" in shape
    assert "closing row injuries.home_names[2]: '  ' is not a name (never classed)" in shape
    sm = summary(out, rc.TAG_LINEUPS)
    # five names classed (Kroupi, and Leeds' four); the two members that are not names, never
    assert sm["games"]["bou-lee"] == {"started": 2, "bench": 2, "absent": 1, "hidden": 2, "count_unknown_sides": 0}


def test_lineups_sides_by_provider_team_id_never_by_name_or_position(world):
    """2001's answer lists the away side first under another name (answers()); a side whose id no block holds is
    unread, the answer's names printed."""
    _, out, _ = lineups(world)
    assert line(out, "    A. Past:").startswith("    A. Past: started — Adam Past")         # Bournemouth's XI
    assert line(out, "    D. James:").startswith("    D. James: started — Daniel James")    # Leeds' XI
    t = dict(answers())
    code, errs, rows = t[("fixtures/lineups", "2004")]
    t[("fixtures/lineups", "2004")] = (code, errs, [rows[0], {**rows[1], "team": team("Fulham", 999)}])
    _, out, _ = lineups(world, "--fixture", "avl-ful=2004", "--save", str(world["tmp"] / "p3"), table=t)
    assert line(out, "    K. Cupman:") == ("    K. Cupman: unread — the answer holds no block for the side's provider "
                                          "ids ['36']")
    assert "  the answer's teams: Aston Villa (team id 66), Fulham (team id 999)" in out


def test_lineups_an_empty_answer_is_unread_counted_and_not_kept(world):
    t = dict(answers())
    t[("fixtures/lineups", "2004")] = (200, {}, [])
    _, out, g = lineups(world, "--fixture", "avl-ful=2004", table=t)
    sm = summary(out, rc.TAG_LINEUPS)
    assert sm["calls"]["empty"] == 1 and "  NO ROWS fixture 2004 lineups" in out
    assert line(out, "    K. Cupman:") == "    K. Cupman: unread — answered with no rows"
    assert "provider fixture 2004 (from --fixture) · read: answered with no rows" in line(out, "provider fixture 2004")
    assert not (world["save"] / "2004").exists()
    _, _out, g2 = lineups(world, "--fixture", "avl-ful=2004", table=t)
    assert "2004" in [c[1]["fixture"] for c in g2.calls]


def test_lineups_embedded_from_stdin(world):
    """The laptop block's form: the script's text on stdin in a checkout root, #688's script and the probe loaded from
    <checkout>/scripts; with every answer kept, no key is needed and no call is made."""
    t = dict(answers())
    t[("fixtures/lineups", "2002")] = (200, {}, [{"team": team("Manchester City", 50),
                                                  "startXI": xi(600, slot(60, "Rúben Dias")),
                                                  "substitutes": bench(600)}])
    code, _out, g = lineups(world, "--fixture", "avl-ful=2004", table=t)
    assert code == 0 and len(g.calls) == 4
    env = {k: v for k, v in os.environ.items() if k != "API_FOOTBALL_KEY"}
    r = subprocess.run([sys.executable, "-", "lineups", "--exports", str(world["host"]), "--db", str(world["db"]),
                        "--save", str(world["save"]), "--fixture", "avl-ful=2004"], input=SCRIPT.read_text(),
                       cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout.splitlines()
    assert out[1].startswith("PROVIDER: calls made 0 · cached answers 4")
    sm = json.loads(out[-1][len(rc.TAG_LINEUPS) + 1:])
    assert sm["calls"]["made"] == 0 and sm["calls"]["cached"] == 4
    assert sm["classes"] == {"started": 5, "bench": 3, "absent": 7, "AMBIGUOUS": 1, "unread": 3}
