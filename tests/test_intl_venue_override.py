"""VENUE-COUNTRY OVERRIDE (ARCHITECT 2026-10-23, addendum 160 item 2), built from #276 on current main (ARCHITECT
2026-11-19, addenda 426 item 5, 427 item 3, 428 item 2(c) and 429 item 1; the 10-23 branch a reference, 287 item 3(B)).

160 item 2: "(a) a venue-country override, keyed by venue id, with the evidence line and the ruling date, applied by
the venue ingest when it derives neutral_v3 (never a hand edit of rows; the override is code, reviewed, and the
re-derivation is receipted per row changed) [...] (b) The receipt: every row whose neutral_v3 changes, by
competition-season, with the cohort fixtures among them named." 428 item 2(c): "RULED: THE ENTRY FOR 3989 IS SPAIN."

Pins, each on a throwaway DB of its own (the app's engine pointed at it):
- the table: 2618 -> Andorra (160 item 2, ruled 2026-10-23) and 3989 -> Spain (428 item 2(c), ruled 2026-11-19), each
  one line with its ruling, its date and its evidence; nothing else;
- derive(): Andorra at home at 2618 is home; at 3989 Spain's own game is home, Ukraine's and Finland's are neutral (428
  item 2(c)'s two changes); any other venue keeps the provider's country; the stored venue_country stays the provider's
  and the rule names the override;
- the one derivation: sync() (the host's daily ingest) and rederive() both call derive(); the FIRST change of a stored
  flag is --apply's alone (a daily run before it leaves the row as main derives it, counted override_pending_apply, and
  the dry run still receipts it with the stop), and after --apply the daily run never puts the provider's flag back
  (for a PLAYED fixture, 431 item 2(a)); a fixture still to come, and a new row, are derived under the table at once,
  counted on a line of their own (431 item 2(c)-(d)); derived_at moves only when a row does;
- the re-derivation: a dry run writes nothing; --apply writes; a second run changes nothing; the receipt lists every
  changed row with its flag before and after, by competition-season, the cohort fixtures named; STOP above two, and
  --apply refused then (and when the cohort cannot be read), nothing written; a lapsed override reverts;
- resolve() and intl_venue_resolved are untouched (429 item 1(d));
- the command: --db reads a .backup copy under 346's fence and leaves it byte for byte; --apply with --db is refused;
  the dry run reads the app's database mode=ro, and a missing database is refused, never created (dry run or --apply);
  --provider-check asks the provider by id and reads no database."""
import inspect
import json
import sqlite3
from datetime import datetime
from pathlib import Path

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
    return tmp_path / "fresh.db"


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


def _stamps(ids):
    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    with session_scope() as s:
        return {k: s.get(IntlMatchVenue, v).derived_at for k, v in ids.items()}


R = iv.NEUTRAL_V3_RULE
# 428 item 2(c)'s classes at 3989 (provider "Ukraine"): Spain's own game, Ukraine's, and a third nation's
AT_3989 = [("esp", "Spain", "Iceland", 3989, "Ukraine", True, R),
           ("ukr", "Ukraine", "Iceland", 3989, "Ukraine", False, R),
           ("fin", "Finland", "Wales", 3989, "Ukraine", True, R)]


# ---- the table and derive() ----------------------------------------------------------------------------------------

def test_the_table_is_the_two_ruled_entries_each_one_line_with_its_ruling_date_and_evidence():
    t = iv.VENUE_COUNTRY_OVERRIDES
    assert {v: o["country"] for v, o in t.items()} == {2618: "Andorra", 3989: "Spain"}
    assert (t[2618]["ruling"], t[2618]["ruled"]) == ("ARCHITECT 2026-10-23, addendum 160 item 2", "2026-10-23")
    assert (t[3989]["ruling"], t[3989]["ruled"]) == ("ARCHITECT 2026-11-19, addendum 428 item 2(c)", "2026-11-19")
    for vid, o in t.items():
        assert set(o) == {"country", "ruling", "ruled", "evidence"} and o["evidence"]
        assert len(f"{iv.NEUTRAL_V3_RULE} · {iv.override_note(vid)}") <= 512        # the rule column's width
        assert o["ruling"] in iv.override_note(vid) and o["ruled"] in iv.override_note(vid)


def test_derive_reads_the_override_and_keeps_the_provider_country_computable():
    flag, rule = iv.derive(2618, "Spain", "Andorra")
    assert flag is False and rule.startswith(R) and iv.OVERRIDE_TAG in rule and "venue 2618 -> Andorra" in rule
    assert "addendum 160 item 2" in rule
    assert iv.provider_flag("Spain", "Andorra") is True                        # the stored-flags side (161 item 2)
    assert iv.derive(2618, "Spain", "Faroe Islands")[0] is True                 # a visitor's home game there: neutral
    # 428 item 2(c): "two change, 45626 (Spain's own game) from neutral to home and 45714 (Ukraine's) from home to
    # neutral; nine stay neutral"
    assert iv.provider_flag("Ukraine", "Spain") is True and iv.derive(3989, "Ukraine", "Spain")[0] is False
    assert iv.provider_flag("Ukraine", "Ukraine") is False and iv.derive(3989, "Ukraine", "Ukraine")[0] is True
    assert iv.provider_flag("Ukraine", "Finland") is True and iv.derive(3989, "Ukraine", "Finland")[0] is True
    assert "venue 3989 -> Spain" in iv.derive(3989, "Ukraine", "Finland")[1]
    assert "addendum 428 item 2(c)" in iv.derive(3989, "Ukraine", "Finland")[1]
    assert iv.derive(3989, "Ukraine", None) == (None, iv.derive(3989, "Ukraine", "Spain")[1])   # unknown home: unknown
    assert iv.derive(77, "Hungary", "Israel") == (True, R)                      # no override: the provider's country
    assert iv.derive(None, None, "Israel") == (None, R)


# ---- the re-derivation ---------------------------------------------------------------------------------------------

def test_rederive_dry_run_apply_and_rerun(fresh_db):
    ids = _world([("and_home", "Andorra", "Latvia", 2618, "Spain", True, R),
                  ("and_cohort", "Andorra", "Moldova", 2618, "Spain", True, R),
                  *AT_3989,
                  ("other", "Israel", "Belgium", 77, "Hungary", True, R)])
    before, stamp0 = _v3(ids), _stamps(ids)
    r = iv.rederive(apply=False, cohort_ids={ids["and_cohort"]})
    assert _v3(ids) == before and _stamps(ids) == stamp0                       # a dry run writes nothing
    assert r["rows_read"] == 5 and r["unchanged"] == 0 and r["rule_only"] == 1 and r["applied"] is False
    assert len(r["flag_changed"]) == 4 and r["cohort_moving"] == 1
    text = "\n".join(iv.rederive_lines(r))
    assert "DRY RUN: nothing written" in text and "UNL 2026/27: 4" in text
    assert "neutral_v3 changes 4 · rule text only 1 · unchanged 0" in text
    assert f"match {ids['and_cohort']} " in text and text.count("COHORT FIXTURE") == 1
    assert "cohort fixtures among the changes 1" in text and "STOP" not in text
    assert "Andorra v Latvia · venue 2618 (provider: Spain) · home country Andorra · neutral_v3 neutral -> home" in text
    assert "Spain v Iceland · venue 3989 (provider: Ukraine) · home country Spain · neutral_v3 neutral -> home" in text
    assert "Ukraine v Iceland · venue 3989 (provider: Ukraine) · home country Ukraine · neutral_v3 home -> neutral" in text
    assert "Finland v Wales" not in text                                       # its flag stays neutral: not a change
    assert "venue 3989 -> Spain · ARCHITECT 2026-11-19, addendum 428 item 2(c) · ruled 2026-11-19" in text

    done = iv.rederive(apply=True, cohort_ids=set())
    assert done["applied"] is True
    got, stamp1 = _v3(ids), _stamps(ids)
    assert got["and_home"][0] is False and got["and_home"][1] == "Spain"       # the provider's country is kept
    assert got["esp"][0] is False and got["ukr"][0] is True and got["fin"][0] is True
    assert all(iv.OVERRIDE_TAG in got[k][2] for k in ("and_home", "and_cohort", "esp", "ukr", "fin"))
    assert got["other"] == before["other"] and stamp1["other"] == stamp0["other"]   # other venues untouched
    assert all(stamp1[k] > stamp0[k] for k in ("and_home", "esp", "ukr", "fin"))    # the flag's ingest time moved
    again = iv.rederive(apply=True, cohort_ids=set())
    assert again["flag_changed"] == [] and again["rule_only"] == 0 and again["unchanged"] == 5   # idempotent
    assert _stamps(ids) == stamp1


def test_more_than_two_cohort_fixtures_moving_says_stop_and_apply_is_refused_with_nothing_written(fresh_db):
    ids = _world([(f"a{i}", "Andorra", "Latvia", 2618, "Spain", True, R) for i in range(3)])
    before = _v3(ids)
    r = iv.rederive(apply=False, cohort_ids=set(ids.values()))
    assert "STOP: 3 cohort fixtures move (more than two)" in "\n".join(iv.rederive_lines(r))
    with pytest.raises(iv.OverrideRefused, match="3 cohort fixtures move") as e:
        iv.rederive(apply=True, cohort_ids=set(ids.values()))
    assert _v3(ids) == before and len(e.value.result["flag_changed"]) == 3    # the rows it would have changed
    two = iv.rederive(apply=True, cohort_ids={ids["a0"], ids["a1"]})          # two is within 160 item 3
    assert two["applied"] is True and _v3(ids)["a2"][0] is False


def test_an_unreadable_cohort_is_said_never_guessed_and_apply_is_refused(fresh_db, monkeypatch):
    ids = _world([("a", "Andorra", "Latvia", 2618, "Spain", True, R)])
    monkeypatch.setattr(iv, "_cohort_ids", lambda s: (None, "not read: RegistryError: no registry"))
    text = "\n".join(iv.rederive_lines(iv.rederive(apply=False)))
    assert "the confirmation cohort: not read: RegistryError: no registry" in text
    assert "cohort fixtures among the changes UNKNOWN (cohort not read)" in text
    with pytest.raises(iv.OverrideRefused, match="cohort could not be read"):
        iv.rederive(apply=True)
    assert _v3(ids)["a"][0] is True


def test_a_lapsed_override_is_rederived_from_the_provider_country(fresh_db, monkeypatch):
    ids = _world([("a", "Andorra", "Latvia", 2618, "Spain", True, R)])
    iv.rederive(apply=True, cohort_ids=set())
    monkeypatch.setattr(iv, "VENUE_COUNTRY_OVERRIDES", {})                     # the entry removed by a later PR
    r = iv.rederive(apply=True, cohort_ids=set())
    assert [x["after"] for x in r["flag_changed"]] == [True]
    assert _v3(ids)["a"][0] is True and _v3(ids)["a"][2] == R


def test_apply_with_a_session_is_refused_a_copy_is_never_written(fresh_db):
    from src.db.database import session_scope
    with session_scope() as s:
        with pytest.raises(iv.OverrideRefused, match="--apply with --db is refused"):
            iv.rederive(apply=True, s=s)


# ---- the one derivation: the daily ingest ----------------------------------------------------------------------------

def _sync_world(tmp_path, venue_files: dict, fixtures: list):
    save, vd = tmp_path / "save", tmp_path / "venues"
    save.mkdir(exist_ok=True)
    vd.mkdir(exist_ok=True)
    json.dump({"response": [{"fixture": {"id": fid, "venue": {"id": vid}}} for fid, vid in fixtures]},
              open(save / "fixtures_1.json", "w"))
    for country, served in venue_files.items():
        json.dump({"response": served}, open(vd / f"venues_{iv._slug(country)}.json", "w"))
    return str(save), str(vd)


def _new_match(home, away, i):
    """A stored match with NO intl_match_venue row yet (the ingest creates it)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "UNL")).scalars().first()
        teams = {t.area: t for t in s.execute(select(Team)).scalars()}
        for area in (home, away):
            if area not in teams:
                teams[area] = Team(sport=Sport.SOCCER, name=area, area=area)
                s.add(teams[area])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=datetime(2026, 11, 1 + i, 18),
                  status=MatchStatus.SCHEDULED, home_team_id=teams[home].id, away_team_id=teams[away].id,
                  external_ids={"api_football": str(890_000 + i)})
        s.add(m)
        s.flush()
        return m.id


# the shape the code reads on the host (#276, 428 item 2(e)): one dictionary across the saved country answers, the
# later country (alphabetically) writing last; venue 501 is an ordinary Spanish ground
HOST_ANSWERS = {"Andorra": [], "Iceland": [],
                "Spain": [{"id": 2618, "country": "Spain"}, {"id": 501, "country": "Spain"},
                          {"id": 3989, "country": "Spain"}],
                "Ukraine": [{"id": 3989, "country": "Ukraine"}]}


def test_the_daily_sync_never_moves_a_stored_flag_before_apply_and_never_puts_it_back_after(fresh_db, tmp_path):
    """160 item 2 ("the re-derivation is receipted per row changed"), 160 item 3 (the stop) and 426 item 5(b)
    ("--apply only by my block on the host after the tag") with 429 item 1(d) (the override inside sync(), derive()
    the one derivation): the host's daily intl-venue-sync, running before the architect's --apply, leaves every STORED
    row the override would move as main derives it, counted "override_pending_apply"; the receipted dry run still
    lists them, cohort fixtures named and the stop said; once --apply has written them, the daily run keeps them."""
    rows = [("and", "Andorra", "Spain", 2618, "Spain", True, R),
            ("esp", "Spain", "Andorra", 501, "Spain", False, R),
            ("esp3989", "Spain", "Iceland", 3989, "Ukraine", True, R),
            ("ukr3989", "Ukraine", "Iceland", 3989, "Ukraine", False, R)]
    ids = _world(rows)
    save, vd = _sync_world(tmp_path, HOST_ANSWERS, [(880_000 + i, r[3]) for i, r in enumerate(rows)])
    before, stamp0 = _v3(ids), _stamps(ids)
    r = iv.sync(save, venues_dir=vd)
    assert r["calls"] == 0 and r["neutral_v3"]["override_pending_apply"] == 3
    assert "venue_country_override" not in r["neutral_v3"]
    assert _v3(ids) == before and _stamps(ids) == stamp0                     # nothing moved before --apply
    cohort = {ids["and"], ids["esp3989"], ids["ukr3989"]}
    dry = iv.rederive(apply=False, cohort_ids=cohort)
    assert len(dry["flag_changed"]) == 3 and dry["cohort_moving"] == 3      # still receipted, the stop still said
    assert "STOP: 3 cohort fixtures move" in "\n".join(iv.rederive_lines(dry))
    with pytest.raises(iv.OverrideRefused):
        iv.rederive(apply=True, cohort_ids=cohort)
    assert _v3(ids) == before

    done = iv.rederive(apply=True, cohort_ids=set())                         # the architect's block
    assert done["applied"] is True and len(done["flag_changed"]) == 3
    got, stamp1 = _v3(ids), _stamps(ids)
    assert got["and"][0] is False and got["esp3989"][0] is False and got["ukr3989"][0] is True
    assert got["esp3989"][1] == "Ukraine"                                    # stored as served; derived as ruled
    assert got["esp"] == before["esp"]
    r = iv.sync(save, venues_dir=vd)                                         # the next morning's run
    assert r["neutral_v3"]["venue_country_override"] == 3 and "override_pending_apply" not in r["neutral_v3"]
    assert _v3(ids) == got and _stamps(ids) == stamp1                        # nothing put back, derived_at kept
    re = iv.rederive(apply=False, cohort_ids=set())                          # the one derivation: nothing to change
    assert re["flag_changed"] == [] and re["rule_only"] == 0 and re["unchanged"] == 3


@pytest.mark.parametrize("change", ["lapsed", "entry_edited", "venue_moved"])
def test_a_row_apply_wrote_keeps_its_flag_and_rule_through_the_daily_sync_until_the_next_apply(fresh_db, tmp_path,
                                                                                               monkeypatch, change):
    """After --apply, a later PR that removes or edits the entry, or the provider moving the fixture off the venue,
    never lets the daily run put the provider's flag back: the row keeps the flag and rule --apply wrote, counted
    override_pending_apply, and only the next receipted --apply moves it (the dry run lists it)."""
    rows = [("and", "Andorra", "Latvia", 2618, "Spain", True, R),
            ("esp", "Spain", "Andorra", 501, "Spain", False, R)]                # Spain at home: Spain's answer read
    ids = _world(rows)
    iv.rederive(apply=True, cohort_ids=set())
    applied, stamp = _v3(ids)["and"], _stamps(ids)["and"]
    assert applied[0] is False and iv.OVERRIDE_TAG in applied[2]
    venue = 2618
    if change == "lapsed":
        monkeypatch.setattr(iv, "VENUE_COUNTRY_OVERRIDES", {})
    elif change == "entry_edited":
        monkeypatch.setitem(iv.VENUE_COUNTRY_OVERRIDES, 2618, {**iv.VENUE_COUNTRY_OVERRIDES[2618], "ruled": "2027-01-01"})
    else:
        venue = 501
    save, vd = _sync_world(tmp_path, HOST_ANSWERS, [(880_000, venue), (880_001, 501)])
    r = iv.sync(save, venues_dir=vd)
    assert r["neutral_v3"]["override_pending_apply"] == 1
    got = _v3(ids)["and"]
    assert (got[0], got[2]) == (applied[0], applied[2])                     # the flag and rule --apply wrote
    dry = iv.rederive(apply=False, cohort_ids=set())
    assert dry["rows_read"] == 1 and dry["unchanged"] == 0                  # the next --apply receipts it
    # lapsed: the provider's Spain at 2618 is neutral for Andorra; moved: 501 is a Spanish ground, neutral for Andorra;
    # edited: the flag stays home and only the rule text changes
    expect = {"lapsed": True, "entry_edited": False, "venue_moved": True}[change]
    assert [x["after"] for x in dry["flag_changed"]] == ([] if expect is False else [expect])
    assert dry["rule_only"] == (1 if expect is False else 0)


CLOCK = datetime(2026, 11, 19, 12)                      # the run's clock in 431 item 2's tests


def _kickoff(mid, when):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        s.get(Match, mid).utc_date = when


def test_431_a_fixture_still_to_come_is_derived_at_once_and_a_played_one_waits_for_apply(fresh_db, tmp_path):
    """ARCHITECT 2026-11-19, addendum 431 item 2(c): "a stored row whose fixture has NOT kicked off (its stored kickoff
    after the run's clock) is derived by derive() at once in sync(), as a new row is, whatever its stored rule: no
    pending, no hand step [...] sync() counts those rows on a line of their own. A row with no stored kickoff is
    treated as played. For played rows nothing changes". 2(d): the architect's case of (b) (a future Andorra home
    fixture stored with no venue, --apply run, then the saved fixtures name 2618); a stored future row at 2618 under
    the provider's flag before any --apply; a played row beside it."""
    rows = [("b_case", "Andorra", "Malta", None, None, None, R),               # stored months ahead, no venue yet
            ("future", "Andorra", "Latvia", 2618, "Spain", True, R),           # the provider's flag, before --apply
            ("played", "Andorra", "Moldova", 2618, "Spain", True, R),
            ("esp", "Spain", "Andorra", 501, "Spain", False, R)]                # Spain at home: Spain's answer read
    ids = _world(rows)
    _kickoff(ids["b_case"], datetime(2026, 12, 1, 18))
    _kickoff(ids["future"], datetime(2026, 12, 2, 18))
    iv.rederive(apply=True, cohort_ids=set())                                  # --apply: the b-case has no venue yet
    assert _v3(ids)["b_case"] == (None, None, R)
    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    with session_scope() as s:                       # the two at 2618 stand as "before any --apply" (431 item 2(d))
        for k in ("future", "played"):
            v = s.get(IntlMatchVenue, ids[k])
            v.neutral_v3, v.rule = True, R
    save, vd = _sync_world(tmp_path, HOST_ANSWERS,
                           [(880_000, 2618), (880_001, 2618), (880_002, 2618), (880_003, 501)])
    r = iv.sync(save, venues_dir=vd, now=CLOCK)
    got = _v3(ids)
    assert got["b_case"][0] is False and iv.OVERRIDE_TAG in got["b_case"][2]   # (b): corrected by the daily run
    assert got["future"][0] is False and iv.OVERRIDE_TAG in got["future"][2]   # corrected by the daily run
    assert got["played"] == (True, "Spain", R)                                 # untouched until --apply
    assert r["override_to_come"] == 2 and r["neutral_v3"]["override_pending_apply"] == 1
    dry = iv.rederive(apply=False, cohort_ids=set())
    assert [x["match_id"] for x in dry["flag_changed"]] == [ids["played"]]     # the played row waits for --apply


def test_431_a_row_with_no_stored_kickoff_is_treated_as_played():
    """431 item 2(c): "A row with no stored kickoff is treated as played." The decision sync() takes per row."""
    assert iv._to_come(None, CLOCK) is False
    assert iv._to_come(CLOCK, CLOCK) is False                                   # kicked off at the run's clock
    assert iv._to_come(datetime(2026, 11, 19, 12, 1), CLOCK) is True
    assert iv._to_come(datetime(2026, 11, 19, 11, 59), CLOCK) is False


@pytest.mark.parametrize("stage", ["future", "played"])
def test_431_under_a_lapsed_entry_the_future_row_follows_the_table_at_once_and_the_played_row_waits(fresh_db,
                                                                                                    tmp_path,
                                                                                                    monkeypatch,
                                                                                                    stage):
    """431 item 2(d): "the same three for a lapsed entry". After --apply, the 2618 entry is removed: a fixture still
    to come is derived at once by the table as it now stands (the provider's country); a played one keeps what --apply
    wrote until the next --apply receipts it; a future fixture stored with no venue and then given 2618 takes the
    provider's flag as any ordinary venue does."""
    ids = _world([("row", "Andorra", "Latvia", 2618, "Spain", True, R),
                  ("b_case", "Andorra", "Malta", None, None, None, R),
                  ("esp", "Spain", "Andorra", 501, "Spain", False, R)])
    if stage == "future":
        _kickoff(ids["row"], datetime(2026, 12, 2, 18))
    _kickoff(ids["b_case"], datetime(2026, 12, 1, 18))
    iv.rederive(apply=True, cohort_ids=set())
    applied = _v3(ids)["row"]
    assert applied[0] is False and iv.OVERRIDE_TAG in applied[2]
    monkeypatch.setattr(iv, "VENUE_COUNTRY_OVERRIDES", {})                      # the entry lapses
    save, vd = _sync_world(tmp_path, HOST_ANSWERS, [(880_000, 2618), (880_001, 2618), (880_002, 501)])
    r = iv.sync(save, venues_dir=vd, now=CLOCK)
    got = _v3(ids)
    assert got["b_case"] == (True, "Spain", R)                                  # ordinary: the provider's flag
    if stage == "future":
        assert got["row"] == (True, "Spain", R) and r["override_to_come"] == 1
        assert "override_pending_apply" not in r["neutral_v3"]
    else:
        assert (got["row"][0], got["row"][2]) == (applied[0], applied[2]) and r["override_to_come"] == 0
        assert r["neutral_v3"]["override_pending_apply"] == 1


def test_431_the_daily_console_prints_the_rows_still_to_come_on_a_line_of_their_own(fresh_db, tmp_path, monkeypatch):
    from click.testing import CliRunner

    from cli import cli
    ids = _world([("future", "Andorra", "Latvia", 2618, "Spain", True, R),
                  ("esp", "Spain", "Andorra", 501, "Spain", False, R)])
    _kickoff(ids["future"], datetime(2099, 1, 1))
    save, vd = _sync_world(tmp_path, HOST_ANSWERS, [(880_000, 2618), (880_001, 501)])
    out = CliRunner().invoke(cli, ["intl-venue-sync", "--from-dir", save, "--venues-dir", vd])
    assert out.exit_code == 0, out.output
    assert ("  venue-country override, fixtures still to come derived under it at once (no --apply): 1"
            in out.output.splitlines())
    assert "  venue-country override, played fixtures pending intl-venue-override --apply: 0" in out.output.splitlines()


def test_431_the_daily_console_prints_both_counts_at_zero_too(fresh_db, tmp_path):
    """A run that counted none says 0 (law 2): it reads apart from a build without the count (my review, P2)."""
    from click.testing import CliRunner

    from cli import cli
    _world([("isr", "Israel", "Belgium", 77, "Hungary", True, R)])
    save, vd = _sync_world(tmp_path, {"Israel": [{"id": 77, "country": "Hungary"}]}, [(880_000, 77)])
    out = CliRunner().invoke(cli, ["intl-venue-sync", "--from-dir", save, "--venues-dir", vd])
    assert out.exit_code == 0, out.output
    lines = out.output.splitlines()
    assert "  venue-country override, fixtures still to come derived under it at once (no --apply): 0" in lines
    assert "  venue-country override, played fixtures pending intl-venue-override --apply: 0" in lines


@pytest.mark.parametrize("now, to_come", [(datetime(2026, 9, 1), True), (datetime(2100, 1, 1), False)])
def test_431_the_run_clock_alone_decides_through_sync(fresh_db, tmp_path, now, to_come):
    """The run's clock passed to sync() decides, never the wall clock (my review, P2): the same stored row, kickoff
    2026-10-02, is still to come at a clock of 2026-09-01 (corrected at once) and played at 2100-01-01 (pending)."""
    ids = _world([("row", "Andorra", "Latvia", 2618, "Spain", True, R),
                  ("esp", "Spain", "Andorra", 501, "Spain", False, R)])
    save, vd = _sync_world(tmp_path, HOST_ANSWERS, [(880_000, 2618), (880_001, 501)])
    r = iv.sync(save, venues_dir=vd, now=now)
    got = _v3(ids)["row"]
    if to_come:
        assert got[0] is False and r["override_to_come"] == 1 and "override_pending_apply" not in r["neutral_v3"]
    else:
        assert got == (True, "Spain", R) and r["override_to_come"] == 0
        assert r["neutral_v3"]["override_pending_apply"] == 1


def test_the_daily_sync_derives_a_new_row_at_an_overridden_venue_as_ruled(fresh_db, tmp_path):
    """A new row has no stored flag to move: the ingest derives it under the override at once (a fixture first stored
    after the tag; every cohort fixture already has its row, 427 item 2(a))."""
    ids = _world([("old", "Andorra", "Latvia", 2618, "Spain", True, R),
                  ("esp", "Spain", "Andorra", 501, "Spain", False, R)])    # Spain at home: Spain's answer is read
    new = _new_match("Andorra", "Malta", 0)
    save, vd = _sync_world(tmp_path, HOST_ANSWERS, [(880_000, 2618), (880_001, 501), (890_000, 2618)])
    r = iv.sync(save, venues_dir=vd)
    assert r["neutral_v3"]["override_pending_apply"] == 1 and r["neutral_v3"]["venue_country_override"] == 1
    got = _v3({**ids, "new": new})
    assert got["old"] == (True, "Spain", R)                                  # stored: pending --apply
    assert got["new"][0] is False and got["new"][1] == "Spain" and iv.OVERRIDE_TAG in got["new"][2]


def test_a_dry_run_or_apply_on_a_missing_database_refuses_and_creates_nothing(tmp_path, monkeypatch):
    """The dry run reads mode=ro (readonly_scope, #706): a missing file is refused, never created (law 5; the
    2026-10-06 incident); --apply checks the file before it opens a writer."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    missing = tmp_path / "sub" / "sports.db"
    eng = create_engine(f"sqlite:///{missing}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True))
    for apply in (False, True):
        with pytest.raises(iv.OverrideRefused, match="no DB file at .* never creates one; nothing read, nothing "
                                                     "written"):
            iv.rederive(apply=apply, cohort_ids=set())
    out = _run([])
    assert out.exit_code == 2 and out.output.startswith("REFUSED: no DB file at")
    assert not missing.exists() and not missing.parent.exists()


def test_sync_moves_derived_at_only_when_the_row_changes(fresh_db, tmp_path):
    ids = _world([("isr", "Israel", "Belgium", None, None, None, "v3")])
    save, vd = _sync_world(tmp_path, {"Israel": [{"id": 77, "country": "Hungary"}]}, [(880_000, 77)])
    iv.sync(save, venues_dir=vd)
    s1 = _stamps(ids)
    iv.sync(save, venues_dir=vd)
    assert _stamps(ids) == s1
    save, vd = _sync_world(tmp_path, {"Israel": [{"id": 77, "country": "Israel"}]}, [(880_000, 77)])
    iv.sync(save, venues_dir=vd)
    assert _stamps(ids)["isr"] > s1["isr"] and _v3(ids)["isr"][0] is False


def test_resolve_and_intl_venue_resolved_are_untouched():
    """429 item 1(d): "intl_venue_resolved untouched and resolve() left as it is"."""
    assert "VENUE_COUNTRY_OVERRIDES" not in inspect.getsource(iv.resolve)
    assert "derive(" not in inspect.getsource(iv.resolve)


# ---- the command ----------------------------------------------------------------------------------------------------

def _run(args):
    from click.testing import CliRunner
    from cli import cli
    return CliRunner().invoke(cli, ["intl-venue-override", *args])


def _copy(src: Path, tmp_path) -> Path:
    """A .backup-API copy outside data/ (law 5: never a file copy, never under data/)."""
    dst = tmp_path / "copy" / "sports.db"
    dst.parent.mkdir()
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    return dst


def test_the_command_dry_run_and_apply_on_the_app_database(fresh_db, monkeypatch):
    ids = _world([("a", "Andorra", "Latvia", 2618, "Spain", True, R)])
    monkeypatch.setattr(iv, "_cohort_ids", lambda s: (set(), "frozen (0 of 60)"))
    out = _run([])
    assert out.exit_code == 0, out.output
    assert out.output.startswith(f"INTL-VENUE-OVERRIDE ({iv.OVERRIDE_RULING}) · DRY RUN: nothing written · "
                                 "overrides 2:")
    assert "neutral_v3 neutral -> home" in out.output and _v3(ids)["a"][0] is True
    out = _run(["--apply"])
    assert out.exit_code == 0 and "DRY RUN" not in out.output and _v3(ids)["a"][0] is False


def test_the_command_refuses_apply_above_two_cohort_fixtures_and_prints_the_rows(fresh_db, monkeypatch):
    ids = _world([(f"a{i}", "Andorra", "Latvia", 2618, "Spain", True, R) for i in range(3)])
    monkeypatch.setattr(iv, "_cohort_ids", lambda s: (set(ids.values()), "frozen (3 of 60)"))
    out = _run(["--apply"])
    assert out.exit_code == 2 and "DRY RUN: nothing written" in out.output
    assert out.output.count("COHORT FIXTURE") == 3
    assert out.output.rstrip().endswith("REFUSED: 3 cohort fixtures move (more than two): to the architect before the "
                                        "read (addendum 160 item 3); nothing written")
    assert all(v[0] is True for v in _v3(ids).values())


def test_the_command_reads_a_copy_under_346s_fence_and_leaves_it_byte_for_byte(fresh_db, monkeypatch, tmp_path):
    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    ids = _world([("a", "Andorra", "Latvia", 2618, "Spain", True, R)])
    monkeypatch.setattr(iv, "_cohort_ids", lambda s: (set(), "frozen (0 of 60)"))
    copy = _copy(fresh_db, tmp_path)
    sha = us.copy_sha256(copy)
    out = _run(["--db", str(copy)])
    assert out.exit_code == 0, out.output
    head, rest = out.output.split("\n", 1)
    assert head == (f"--db {copy.resolve()} · sha256 {sha} · a .backup copy, opened "
                    f"{mp.COPY_URI_QUERY.lstrip('?')} (the app's database is not read)")
    assert rest == _run([]).output                                             # the same receipt as on the store
    assert us.copy_sha256(copy) == sha and not us.copy_sidecars(copy)          # untouched, no sidecar made
    out = _run(["--db", str(copy), "--apply"])
    assert out.exit_code == 2 and out.output.startswith("REFUSED: --apply writes the app's database and never a copy")
    assert us.copy_sha256(copy) == sha and _v3(ids)["a"][0] is True
    out = _run(["--db", str(tmp_path / "missing.db")])
    assert out.exit_code == 2 and out.output.startswith("REFUSED:") and not (tmp_path / "missing.db").exists()


def test_the_command_refuses_a_copy_with_a_sidecar_beside_it(fresh_db, monkeypatch, tmp_path):
    _world([("a", "Andorra", "Latvia", 2618, "Spain", True, R)])
    copy = _copy(fresh_db, tmp_path)
    copy.with_name(copy.name + "-wal").write_bytes(b"")
    out = _run(["--db", str(copy)])
    assert out.exit_code == 2 and out.output.startswith("REFUSED:") and "-wal" in out.output


def test_provider_check_asks_by_id_reads_no_database_and_saves_nothing(monkeypatch, tmp_path):
    import src.adapters.api_football as af
    calls = []

    class Fake:
        def __init__(self, *a, **k):
            pass

        def _get(self, path, params):
            calls.append((path, params))
            return {"response": [{"id": params["id"], "name": "N", "city": "C", "country": "X", "capacity": 1}]}

    monkeypatch.setattr(af, "APIFootballAdapter", Fake)
    monkeypatch.chdir(tmp_path)
    out = _run(["--provider-check"])
    assert out.exit_code == 0, out.output
    assert calls == [("venues", {"id": 2618}), ("venues", {"id": 3989})]
    assert out.output.splitlines() == [
        "PROVIDER /venues?id=2618 (as served, today; nothing saved): id 2618 · N · C · X · keys served: capacity, city, "
        "country, id, name",
        "PROVIDER /venues?id=3989 (as served, today; nothing saved): id 3989 · N · C · X · keys served: capacity, city, "
        "country, id, name"]
    assert list(tmp_path.iterdir()) == []
    for extra in (["--apply"], ["--db", "x.db"]):
        out = _run(["--provider-check", *extra])
        assert out.exit_code == 2 and out.output.startswith("REFUSED: --provider-check only asks the provider")
    assert len(calls) == 2
