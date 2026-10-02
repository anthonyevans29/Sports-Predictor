"""#220 national-team history ingest: discovery by name (unmapped target and
adapter-id clash refused), the senior-team filter (excluded fixtures printed),
neutral_derived under the stated rule (NULL when a city is missing), the
dry run writing nothing, idempotent re-runs, the coverage receipt, and the
data/ refusal. Synthetic API-Football-shaped responses replayed from a
directory; the API is never reached."""
import json
import os
from datetime import date

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchNeutralDerived
from src.ingestion import intl_history as ih

SINCE = date(2018, 1, 1)


def league(lid, name, *years):
    return {"league": {"id": lid, "name": name, "type": "Cup"},
            "seasons": [{"year": y, "start": f"{y}-01-01", "end": f"{y}-12-31"} for y in years]}


def fx(fid, home, away, hg, ag, city, when="2071-06-07T18:45:00+00:00", short="FT", league_season=2071):
    names = {880001: "Probeland", 880002: "Testonia", 880003: "Mockovia", 880004: "Stubistan",
             880099: "Probe Regional XI"}
    return {"fixture": {"id": fid, "date": when, "status": {"short": short},
                        "venue": {"id": None, "name": f"{city} Arena" if city else None, "city": city}},
            "league": {"season": league_season, "round": "Group A - 1"},
            "teams": {"home": {"id": home, "name": names[home], "winner": hg > ag if hg is not None else None},
                      "away": {"id": away, "name": names[away], "winner": ag > hg if hg is not None else None}},
            "goals": {"home": hg, "away": ag},
            "score": {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": hg, "away": ag}}}


def team(tid, city):
    return {"team": {"id": tid, "name": {880001: "Probeland", 880002: "Testonia", 880003: "Mockovia",
                                         880004: "Stubistan", 880099: "Probe Regional XI"}[tid],
                     "code": None, "country": "X"},
            "venue": {"name": f"{city} Arena" if city else None, "city": city}}


GROUNDS = [team(880001, "Probe City"), team(880002, "Tëst Town"), team(880003, "Mockburg"), team(880004, None)]


def write_dir(d):
    lg = [league(5, "UEFA Nations League", 2071), league(32, "World Cup - Qualification Europe", 2071),
          league(960, "Euro Championship - Qualification", 2071), league(10, "Friendlies", 2016, 2071),
          league(8, "World Cup - Women", 2071)]
    files = {
        "leagues.json": {"response": lg},
        "fixtures_5_2071.json": {"response": [
            fx(9900001, 880001, 880002, 2, 1, "probe city"),            # home (case-insensitive)
            fx(9900002, 880002, 880003, 0, 0, "Test Town"),             # home (accents dropped)
            fx(9900003, 880003, 880001, 1, 3, "Lisbon")]},              # neutral (finals venue)
        "fixtures_32_2071.json": {"response": [fx(9900004, 880004, 880001, 0, 2, "Stubville")]},  # ground unknown
        "fixtures_960_2071.json": {"response": [fx(9900005, 880001, 880003, 1, 1, None)]},       # venue unknown
        "fixtures_10_2071.json": {"response": [fx(9900006, 880002, 880001, 1, 0, "Tëst Town"),
                                               fx(9900007, 880099, 880002, 0, 4, "Bilbao")]},    # excluded
    }
    for lid in (5, 32, 960, 10):
        files[f"teams_{lid}_2071.json"] = {"response": GROUNDS + ([team(880099, "Bilbao")] if lid == 10 else [])}
    for name, payload in files.items():
        with open(os.path.join(d, name), "w") as f:
            json.dump(payload, f)


def test_plan_maps_names_to_codes_and_cuts_seasons():
    p = ih.plan([league(5, "UEFA Nations League", 2018, 2020), league(10, "Friendlies", 2017, 2019),
                 league(960, "Euro Championship - Qualification", 2020), league(37, "World Cup - Qualification "
                 "Intercontinental Play-offs", 2022), league(8, "World Cup - Women", 2019)], SINCE)
    assert [(x["code"], x["year"]) for x in p] == [("FRIENDLIES_INT", 2019), ("UEFA_EURO_Q", 2020), ("UNL", 2018),
                                                    ("UNL", 2020), ("WCQ_IC", 2022)]


def test_plan_refuses_unmapped_target_and_adapter_id_clash():
    with pytest.raises(ih.IntlError, match="no code"):
        ih.plan([league(777, "Arab Nations League", 2020)], SINCE)
    with pytest.raises(ih.IntlError, match="adapter maps 5"):
        ih.plan([league(999, "UEFA Nations League", 2020)], SINCE)


def test_neutral_rule_and_unknowns():
    g = ih.grounds(GROUNDS)
    assert ih.derive_neutral(fx(1, 880001, 880002, 1, 0, " PROBE   city "), g)[0] is False
    assert ih.derive_neutral(fx(1, 880002, 880001, 1, 0, "Test Town"), g)[0] is False      # ë == e
    assert ih.derive_neutral(fx(1, 880001, 880002, 1, 0, "Lisbon"), g)[0] is True
    assert ih.derive_neutral(fx(1, 880004, 880001, 1, 0, "Stubville"), g) == (None, "Stubville", None)
    assert ih.derive_neutral(fx(1, 880001, 880002, 1, 0, None), g)[0] is None
    assert "never a provider fact" in ih.NEUTRAL_RULE


def _counts():
    with session_scope() as s:
        ids = [r for r in s.execute(select(Match.id).where(Match.season.in_(["2071", "2071/72"]))).scalars()]
        nd = s.execute(select(func.count()).select_from(MatchNeutralDerived)
                       .where(MatchNeutralDerived.match_id.in_(ids))).scalar()
        return len(ids), nd


def test_ingest_dry_run_then_real_then_idempotent(tmp_path):
    init_db()
    write_dir(tmp_path)
    r = ih.ingest(ih.Source(from_dir=str(tmp_path)), SINCE, dry_run=True)
    assert _counts() == (0, 0)                                    # the dry run wrote nothing
    assert r["senior_teams"] == 4 and r["excluded_total"] == 1
    assert dict(r["excluded_teams"]) == {"Probe Regional XI (id 880099)": 1}
    r = ih.ingest(ih.Source(from_dir=str(tmp_path)), SINCE)
    assert _counts() == (6, 6)
    assert r["neutral"] == {"home": 3, "neutral": 1, "unknown": 2}
    assert r["per_cs"][("FRIENDLIES_INT", 2071)]["kept"] == 1     # 2016 friendlies cut by --since
    with session_scope() as s:
        unl = s.execute(select(Match).where(Match.season == "2071/72")).scalars().all()
        assert len(unl) == 3                                      # UNL keeps the two-year season string
        row = s.get(MatchNeutralDerived, next(m.id for m in unl if (m.external_ids or {}).get("api_football")
                                              == "9900003"))
        assert row.neutral_derived is True and row.venue_city == "Lisbon" and row.home_ground_city == "Mockburg"
        assert row.rule == ih.NEUTRAL_RULE
        q = s.execute(select(Competition).where(Competition.code == "UEFA_EURO_Q")).scalar_one()
        assert q.external_ids == {"api_football": "960"} and q.type == "INTL"
    r2 = ih.ingest(ih.Source(from_dir=str(tmp_path)), SINCE)
    assert _counts() == (6, 6) and r2["matches"].startswith("created=0 updated=6")
    with session_scope() as s:
        rows = [x for x in ih.coverage_lines(ih.coverage(s)) if "2071" in x]
    assert any(x.split()[0] == "UNL" and x.split()[1] == "2071/72" for x in rows)


def test_cli_prints_exclusions_and_refuses_data_dir(tmp_path):
    from cli import cli
    init_db()
    write_dir(tmp_path)
    out = CliRunner().invoke(cli, ["intl-sync", "--from-dir", str(tmp_path), "--dry-run"]).output
    assert "EXCLUDED by the team filter: 1 fixtures" in out and "Probe Regional XI (id 880099)" in out
    assert "RULE: intl-neutral-v1" in out
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = CliRunner().invoke(cli, ["intl-sync", "--save", os.path.join(root, "data", "x"), "--dry-run"])
    assert res.exit_code == 2 and "under data/" in res.output
