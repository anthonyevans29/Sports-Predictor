"""VENUE-COUNTRY OVERRIDE (ARCHITECT 2026-10-23, addendum 160 item 2): "(a) a venue-country override, keyed by venue
id, with the evidence line and the ruling date, applied by the venue ingest when it derives neutral_v3 (never a hand
edit of rows; the override is code, reviewed, and the re-derivation is receipted per row changed); the first entries:
2618 → Andorra (ruled here); 3989 → unknown (set neutral_v3 NULL [...]). (b) The receipt: every row whose neutral_v3
changes, by competition-season, with the cohort fixtures among them named." Pins, on a throwaway DB of its own:
- derive(): 2618 reads Andorra (Andorra at home is home, not neutral), 3989 reads unknown, any other venue the
  provider's country; the stored venue_country stays the provider's and the rule names the override;
- intl-venue-sync applies it on ingest; intl-venue-resolve never resolves an overridden-unknown venue back;
- the re-derivation: a dry run writes nothing; --apply writes the flags; a second run changes nothing; the receipt
  lists every changed row by competition-season, names the cohort fixtures, and says STOP above two."""
import json
from datetime import datetime

import pytest
from sqlalchemy import select

from src.ingestion import intl_venues as iv


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return eng


def _world(rows, code="UNL", season="2026/27"):
    """rows: (key, home area, away area, venue id, provider venue country, stored neutral_v3, rule)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team
    ids = {}
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=code, name=code, area="I", type="INTL")
        s.add(comp)
        s.flush()
        teams = {}
        for i, (key, home, away, vid, vc, flag, rule) in enumerate(rows):
            for area in (home, away):
                if area not in teams:
                    teams[area] = Team(sport=Sport.SOCCER, name=area, area=area)
                    s.add(teams[area])
            s.flush()
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season=season, utc_date=datetime(2026, 10, 2 + i, 18),
                      status=MatchStatus.SCHEDULED, home_team_id=teams[home].id, away_team_id=teams[away].id,
                      external_ids={"api_football": str(880_000 + i)})
            s.add(m)
            s.flush()
            ids[key] = m.id
            s.add(IntlMatchVenue(match_id=m.id, venue_id=vid, venue_country=vc, home_country=home, neutral_v3=flag,
                                 rule=rule))
    return ids


def _v3(ids):
    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    with session_scope() as s:
        got = {r.match_id: (r.neutral_v3, r.venue_country, r.rule) for r in s.execute(select(IntlMatchVenue)).scalars()}
    return {k: got[v] for k, v in ids.items()}


def test_derive_reads_the_override_and_keeps_the_provider_country_computable():
    flag, rule = iv.derive(2618, "Spain", "Andorra")
    assert flag is False and iv.OVERRIDE_TAG in rule and "venue 2618 -> Andorra" in rule and rule.startswith(
        iv.NEUTRAL_V3_RULE)
    assert iv.provider_flag("Spain", "Andorra") is True                       # the stored-flags side (item 3)
    assert iv.derive(2618, "Spain", "Faroe Islands")[0] is True                # a visitor's home game there: neutral
    flag, rule = iv.derive(3989, "Ukraine", "Finland")
    assert flag is None and "venue 3989 -> unknown (neutral_v3 NULL)" in rule
    assert iv.derive(77, "Hungary", "Israel") == (True, iv.NEUTRAL_V3_RULE)    # no override: the provider's country
    assert iv.derive(None, None, "Israel") == (None, iv.NEUTRAL_V3_RULE)
    for o in iv.VENUE_COUNTRY_OVERRIDES.values():                              # the evidence line and the ruling date
        assert o["evidence"] and o["ruled"] == "2026-10-23"
    assert len(iv.override_note(2618)) + len(iv.NEUTRAL_V3_RULE) + 3 <= 512    # the rule column's width


def test_rederive_dry_run_apply_and_rerun(fresh_db):
    ids = _world([("and_home", "Andorra", "Latvia", 2618, "Spain", True, iv.NEUTRAL_V3_RULE),
                  ("and_cohort", "Andorra", "Moldova", 2618, "Spain", True, iv.NEUTRAL_V3_RULE),
                  ("fin", "Finland", "Wales", 3989, "Ukraine", True, iv.NEUTRAL_V3_RULE),
                  ("other", "Israel", "Belgium", 77, "Hungary", True, iv.NEUTRAL_V3_RULE)])
    before = _v3(ids)
    r = iv.rederive(apply=False, cohort_ids={ids["and_cohort"]})
    assert _v3(ids) == before                                                  # a dry run writes nothing
    assert r["rows_read"] == 3 and len(r["flag_changed"]) == 3 and r["unchanged"] == 0
    text = "\n".join(iv.rederive_lines(r))
    assert "DRY RUN: nothing written" in text and "UNL 2026/27: 3" in text
    assert f"match {ids['and_cohort']} " in text and text.count("COHORT FIXTURE") == 1
    assert "cohort fixtures among the changes 1" in text and "STOP" not in text
    assert "Andorra v Latvia · venue 2618 (provider: Spain) · home country Andorra · neutral_v3 neutral -> home" in text
    assert "venue 3989 (provider: Ukraine) · home country Finland · neutral_v3 neutral -> unknown" in text

    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    with session_scope() as s:
        stamp0 = {m: s.get(IntlMatchVenue, m).derived_at for m in ids.values()}
    iv.rederive(apply=True, cohort_ids=set())
    with session_scope() as s:                                                 # the flag's ingest time moves with it
        stamp1 = {m: s.get(IntlMatchVenue, m).derived_at for m in ids.values()}
    assert stamp1[ids["and_home"]] > stamp0[ids["and_home"]] and stamp1[ids["other"]] == stamp0[ids["other"]]
    got = _v3(ids)
    assert got["and_home"][0] is False and got["and_home"][1] == "Spain"       # the provider's country is kept
    assert iv.OVERRIDE_TAG in got["and_home"][2]
    assert got["fin"][0] is None and got["other"] == before["other"]           # other venues untouched
    again = iv.rederive(apply=True, cohort_ids=set())
    assert again["flag_changed"] == [] and again["unchanged"] == 3            # idempotent


def test_more_than_two_cohort_fixtures_moving_says_stop(fresh_db):
    ids = _world([(f"a{i}", "Andorra", "Latvia", 2618, "Spain", True, iv.NEUTRAL_V3_RULE) for i in range(3)])
    r = iv.rederive(apply=False, cohort_ids=set(ids.values()))
    assert "STOP: 3 cohort fixtures move (more than two)" in "\n".join(iv.rederive_lines(r))


def test_an_unreadable_cohort_is_said_never_guessed(fresh_db, monkeypatch):
    _world([("a", "Andorra", "Latvia", 2618, "Spain", True, iv.NEUTRAL_V3_RULE)])
    monkeypatch.setattr(iv, "_cohort_ids", lambda s: (None, "not read: RegistryError: no registry"))
    text = "\n".join(iv.rederive_lines(iv.rederive(apply=False)))
    assert "the confirmation cohort: not read: RegistryError: no registry" in text
    assert "cohort fixtures among the changes UNKNOWN (cohort not read)" in text


def test_a_lapsed_override_is_rederived_from_the_provider_country(fresh_db, monkeypatch):
    ids = _world([("a", "Andorra", "Latvia", 2618, "Spain", True, iv.NEUTRAL_V3_RULE)])
    iv.rederive(apply=True, cohort_ids=set())
    monkeypatch.setattr(iv, "VENUE_COUNTRY_OVERRIDES", {})                      # the entry removed by a later PR
    r = iv.rederive(apply=True, cohort_ids=set())
    assert [x["after"] for x in r["flag_changed"]] == [True]
    assert _v3(ids)["a"][0] is True and _v3(ids)["a"][2] == iv.NEUTRAL_V3_RULE


def test_sync_applies_the_override_on_ingest(fresh_db, tmp_path):
    ids = _world([("and", "Andorra", "Spain", None, None, None, "v3"),
                  ("esp", "Spain", "Andorra", None, None, None, "v3")])
    save, vd = tmp_path / "save", tmp_path / "venues"
    save.mkdir()
    vd.mkdir()
    json.dump({"response": [{"fixture": {"id": 880_000, "venue": {"id": 2618}}},
                            {"fixture": {"id": 880_001, "venue": {"id": 501}}}]}, open(save / "fixtures_1.json", "w"))
    json.dump({"response": []}, open(vd / "venues_andorra.json", "w"))
    json.dump({"response": [{"id": 2618, "country": "Spain"}, {"id": 501, "country": "Spain"}]},
              open(vd / "venues_spain.json", "w"))
    r = iv.sync(str(save), venues_dir=str(vd))
    assert r["calls"] == 0 and r["neutral_v3"]["venue_country_override"] == 1
    got = _v3(ids)
    assert got["and"][0] is False and got["and"][1] == "Spain" and iv.OVERRIDE_TAG in got["and"][2]
    assert got["esp"] == (False, "Spain", iv.NEUTRAL_V3_RULE)


def test_resolve_never_resolves_an_overridden_unknown_venue(fresh_db, tmp_path):
    from src.db.database import session_scope
    from src.db.schema import IntlVenueResolved
    ids = _world([("fin", "Finland", "Wales", 3989, "Ukraine", None, iv.NEUTRAL_V3_RULE)])
    save, vd = tmp_path / "save", tmp_path / "venues"
    save.mkdir()
    vd.mkdir()
    json.dump({"response": [{"fixture": {"id": 880_000, "venue": {"id": 3989}}}]}, open(save / "fixtures_1.json", "w"))
    json.dump({"response": [{"id": 3989, "country": "Ukraine", "city": "Kyiv", "name": "X"}]},
              open(vd / "venues_ukraine.json", "w"))

    class NoCalls:
        def _get(self, *a, **k):
            raise AssertionError("an overridden venue is never fetched")

    r = iv.resolve(str(save), str(vd), client=NoCalls())
    assert r["plan"]["route_a_calls"] == 0
    with session_scope() as s:
        row = s.get(IntlVenueResolved, ids["fin"])
        assert row.neutral_resolved is None and row.country_source == "override"
        assert row.reason.startswith("venue-country override: host unverified")
