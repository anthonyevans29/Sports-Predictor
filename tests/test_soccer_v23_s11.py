"""soccer-v23's §11 follow-up (ARCHITECT 2026-11-05 13:50 ET, addendum 264 item 3: "THE §11 FOLLOW-UP PR (one PR,
before 11-20, after #841 merges): 263's text and BAR_TEXT changes with the fingerprint re-pinned under 263; 2(a) and
2(b) above with their tests; 262 item 2's cadence read from the record's constant filtered to soccer; the record reader
calling record.as_of (263 item 23) and the refusal message rewritten; the finding Issue #827 cited."). SYNTHETIC stores
only, under pytest's tmp_path: nothing reads data/ or a real database, and nothing here runs the gate on real data (no
run before the declaration).

Each test was written first and seen failing on main 667dc25f (the PR body pastes the lines), then the code changed."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest

from src.availability import record as avr
from src.walters import soccer_v23 as v
from tests.test_soccer_v23_harness import (SLOTS, V22P, _backup, _fp, _nothing, build, declared,  # noqa: F401
                                           fresh)

REG = "Regular Season - 1"


def _row(i, code, season, at, h, a, hg, ag, stage=REG):
    return v.Row(i, code, season, at, h, a, hg, ag, stage)


# ------------------------------------------------------------------- 264 item 2(a): the first IN-SCOPE season --

def _first_season_out_of_scope():
    """XX's first stored season (2023/24) holds only play-off rows (out of scope under LEAGUE_REGULAR); its first
    IN-SCOPE season is 2024/25. YY is regular throughout (its first season 2024/25)."""
    t = datetime(2023, 9, 1, 15)
    rows = [_row(1, "XX", "2023/24", t, 1, 2, 2, 1, "Relegation Round - 1"),
            _row(2, "XX", "2023/24", t + timedelta(days=7), 2, 1, 0, 1, "Relegation Round - 2")]
    i = 10
    for season, y in (("2024/25", 2024), ("2025/26", 2025)):
        for d, (h, a, hg, ag) in enumerate(((1, 2, 2, 1), (3, 4, 1, 1), (2, 3, 0, 2), (4, 1, 3, 1))):
            for code in ("XX", "YY"):
                rows.append(_row(i, code, season, datetime(y, 9, 1 + d, 15), h, a, hg, ag))
                i += 1
    return sorted(rows, key=v.Row.key)


def test_264_2a_first_seasons_are_computed_after_the_stage_scope():
    """264 item 2(a), fail-first: "a competition whose first stored season holds only out-of-scope rows would have its
    first IN-SCOPE season read as a continuing one". first_seasons takes the scope (never the unscoped rows), and
    scored_rows under exclude_as_warmup leaves out XX's first IN-SCOPE season (2024/25), not its play-off-only 2023/24."""
    rows = _first_season_out_of_scope()
    assert v.first_seasons(rows, "LEAGUE_REGULAR") == {"XX": "2024/25", "YY": "2024/25"}
    assert v.first_seasons(rows, "LEAGUE") == {"XX": "2023/24", "YY": "2024/25"}
    warm = {**SLOTS, "scope": "LEAGUE_REGULAR", "first_season": "exclude_as_warmup"}
    got = v.scored_rows(rows, warm)
    assert {(r.code, r.season) for r in got} == {("XX", "2025/26"), ("YY", "2025/26")}


def test_264_2a_the_fit_s_weak_prior_was_already_scoped():
    """The positive pin beside the fix (it passes on 667dc25f too): the walk's fit reads the one builder's SCOPED rows
    (snapshot_from_rows applies in_scope), so under LEAGUE_REGULAR XX's first in-scope season is already priced under
    the weak prior (263 item 3) and its second is not. The defect of 264 item 2(a) reached scored_rows under
    exclude_as_warmup and the preflight's line, not the fit."""
    rows = _first_season_out_of_scope()
    xx = [r for r in rows if r.code == "XX" and r.stage == REG]
    first, second = xx[0], next(r for r in xx if r.season == "2025/26")
    pj = v.canon_params(V22P, False, "LEAGUE_REGULAR")
    for r, want in ((first, True), (second, False)):
        snap = v.snapshot_from_rows(rows, r.utc_date, pj, "day")
        assert v.predict(snap, v.Fixture.of(r), "soccer-v23")["info"]["first_season"] is want, r.season


def _add_matches(specs):
    """Add finished soccer rows to the bound store: (code, ctype, season, kickoff, home id, away id, hg, ag, stage);
    a code not in the store is created as a competition of `ctype`; a team id of None makes a new team."""
    import src.db.database as dbm
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    out = []
    with dbm.session_scope() as s:
        comps = {c.code: c for c in s.query(Competition).all()}
        made: dict = {}
        for code, ctype, season, at, h, a, hg, ag, stage in specs:
            if code not in comps:
                comps[code] = Competition(sport=Sport.SOCCER, code=code, name=code, area="Elsewhere", type=ctype)
                s.add(comps[code])
                s.flush()
            ids = []
            for t in (h, a):
                if not isinstance(t, int):
                    if t not in made:
                        made[t] = Team(sport=Sport.SOCCER, name=f"synthetic {t}")
                        s.add(made[t])
                        s.flush()
                    t = made[t].id
                ids.append(t)
            m = Match(sport=Sport.SOCCER, competition_id=comps[code].id, season=season, utc_date=at, stage=stage,
                      home_team_id=ids[0], away_team_id=ids[1], status=MatchStatus.FINISHED, status_raw="FT",
                      home_score=hg, away_score=ag)
            s.add(m)
            s.flush()
            out.append(m.id)
    return out


def test_264_2a_the_preflight_prints_the_in_scope_first_season(declared):
    """264 item 2(a), fail-first: "the preflight's per-competition first-season line printing the IN-SCOPE first
    season". The declared store's PL gains a 2023/24 of play-off rows only (out of scope under LEAGUE_REGULAR): the
    line names 2024/25, the first IN-SCOPE season."""
    from src.walters import registry as reg
    import src.db.database as dbm
    from src.db.schema import Competition, Match
    with dbm.session_scope() as s:
        pl = s.query(Competition).filter(Competition.code == "PL").one()
        m = s.query(Match).filter(Match.competition_id == pl.id).order_by(Match.utc_date).first()
        h, a = m.home_team_id, m.away_team_id
    _add_matches([("PL", "LEAGUE", "2023/24", datetime(2024, 5, 20, 15) + timedelta(days=k), h, a, 2, 1,
                   f"Relegation Round - {k + 1}") for k in range(2)])
    copy = str(_backup(declared["tmp"] / "store.db", declared["tmp"] / "copies" / "copy-fs.db"))
    L = v.preflight_lines(reg.get(v.EID, reg.LEDGER), copy)
    line = next(x for x in L if x.startswith("  PL: "))
    assert "2023/24 2" in line and line.endswith("first season in scope 2024/25"), line
    assert len(_fp(L)) == 64
    _nothing(declared)


# ------------------------------------------------------------ 264 item 2(b): FitRefused, a REFUSED line --

def test_264_2b_the_gate_command_prints_a_fit_refusal_as_its_refused_line(declared, monkeypatch):
    """264 item 2(b), fail-first (on 667dc25f the command died on a FitRefused traceback, exit 1): the fit refusing in
    the walk, after the reservation, prints the REFUSED line with its reason and exits 2; the reservation STANDS (263
    item 13: the one run is spent) and nothing is recorded."""
    from click.testing import CliRunner

    import cli
    from src.models import joint_poisson as jp
    from src.walters import registry as reg
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))

    def refuse(*a, **k):
        raise jp.FitRefused("synthetic: the line search stalled")
    monkeypatch.setattr(jp, "fit", refuse)
    res = CliRunner().invoke(cli.cli, ["soccer-v23-gate", "--architect-word", "ARCHITECT test word",
                                       "--stream-fingerprint", fp, "--db", declared["copy"], "--no-fetch"])
    assert isinstance(res.exception, SystemExit) and res.exit_code == 2, (res.exit_code, res.exception)
    refused = [x for x in res.output.splitlines() if x.startswith("REFUSED: ")]
    assert len(refused) == 1 and "synthetic: the line search stalled" in refused[0], res.output
    assert "after the reservation" in refused[0] and "the one run is spent" in refused[0]
    assert "Traceback" not in res.output
    assert Path(v.reservation_path()).exists()                         # 263 item 13: it stands
    assert reg.get(v.EID, reg.LEDGER)["run"] is None                   # nothing recorded


# ----------------------------------------------- 262 item 2: ONE cadence constant, filtered to soccer sources --

def _stamped(source: str, recorded: datetime, stamp: datetime) -> v.Fact:
    return v.Fact(1, source, v.TERM_KIND, 5, None, None, "A Player", "Missing Fixture", "F", stamp, recorded)


def test_262_2_the_cadence_is_the_record_s_constant_filtered_to_soccer_sources(monkeypatch):
    """262 item 2, fail-first: "soccer-v23 (#832) deletes its own empty copy and READS the record's constant FILTERED
    TO SOCCER SOURCES ... the fingerprint hashes that filtered view, so an entry for another sport (nflverse at 24, the
    NHL landing feed later) never moves v23's fingerprint"; BAR_TEXT names the soccer entries (today none)."""
    assert not hasattr(v, "SOURCE_CADENCE_HOURS")                      # its own copy deleted
    assert set(v.SOCCER_SOURCES) <= set(avr.SOURCES) and v.SOCCER_SOURCES == ()
    assert dict(avr.SOURCE_CADENCE_HOURS) == {"nflverse_depth_charts": 24}
    assert v.source_cadence_hours() == {} and v.code_constants()["SOURCE_CADENCE_HOURS"] == {}
    assert "no soccer source declared; every fact carrying a source_stamp is excluded, counted" in v.BAR_TEXT
    rows = [_row(1, "XX", "2025/26", datetime(2025, 9, 1, 15), 1, 2, 1, 0)]
    base = v.stream_fingerprint(rows, rows, dict(SLOTS), V22P, v.ROWS_ONLY)[0]
    nfl = _stamped("nflverse_depth_charts", datetime(2025, 9, 1), datetime(2025, 8, 31, 12))
    assert v.backfill_reason(nfl) is not None                          # nflverse's 24 h is not a soccer cadence
    # another sport's entry added to the record's constant: v23's view, constants and fingerprint do not move
    monkeypatch.setattr(avr, "SOURCE_CADENCE_HOURS", MappingProxyType({"nflverse_depth_charts": 24,
                                                                       "nhl_api_landing": 6}))
    assert v.source_cadence_hours() == {} and v.code_constants()["SOURCE_CADENCE_HOURS"] == {}
    assert v.stream_fingerprint(rows, rows, dict(SLOTS), V22P, v.ROWS_ONLY)[0] == base
    # the positive control: a source declared soccer's, with a cadence in the record, enters the view and the fingerprint
    monkeypatch.setattr(v, "SOCCER_SOURCES", ("sportsdataio_goalies",))
    monkeypatch.setattr(avr, "SOURCE_CADENCE_HOURS", MappingProxyType({"nflverse_depth_charts": 24,
                                                                       "sportsdataio_goalies": 12}))
    assert v.source_cadence_hours() == {"sportsdataio_goalies": 12}
    assert v.stream_fingerprint(rows, rows, dict(SLOTS), V22P, v.ROWS_ONLY)[0] != base
    fresh_ = _stamped("sportsdataio_goalies", datetime(2025, 9, 1), datetime(2025, 8, 31, 12))
    stale = _stamped("sportsdataio_goalies", datetime(2025, 9, 1), datetime(2025, 8, 30))
    assert v.backfill_reason(fresh_) is None and "beyond" in v.backfill_reason(stale)


# --------------------------------------------- 263 item 23: the record's reader is record.as_of (the one path) --

def _migrated(tmp_path, monkeypatch, name="rec.db"):
    """A store exactly as production builds one (#831's init_db creates both tables) and migrated
    (migrate_availability_record.py: its triggers and its marker)."""
    import migrate_availability_record as mig
    db = fresh(tmp_path / name, monkeypatch, record_tables=True)
    monkeypatch.chdir(tmp_path)
    assert mig.main() == 0
    return db


def test_263_23_a_migrated_record_is_read_through_record_as_of(tmp_path, monkeypatch):
    """263 item 23, fail-first (on 667dc25f a store holding both tables refused with "not merged"): the adapter reads a
    migrated record through record.as_of, the one path (soccer, the recorded clock, the decision instant); the record
    holding no soccer fact there is NO_RECORD with its reason, so the term is off (253 item 2(d)), labelled."""
    db = _migrated(tmp_path, monkeypatch)
    calls = []
    real = avr.as_of

    def spy(s, sport, instant, clock="recorded", **k):
        calls.append((getattr(sport, "value", sport), instant, clock, k))
        return real(s, sport, instant, clock, **k)
    monkeypatch.setattr(avr, "as_of", spy)
    d = datetime(2025, 9, 1)
    with db.session_scope() as s:
        rec = v.availability_record(s)
        got = v.read_availability(rec, d)
    assert calls == [("soccer", d, "recorded", {"kind": v.TERM_KIND})]          # 263 item 25: the term's one kind
    assert got.state == v.NO_RECORD and got.facts == () and "record.as_of" in got.reason
    assert got.reason == v.NO_SOCCER_FACT_REASON


def test_263_23_a_store_with_both_tables_and_no_marker_is_refused_never_read(tmp_path, monkeypatch):
    """The record's own reader (cli availability) refuses a store migrate_availability_record.py has not migrated;
    soccer-v23's adapter refuses it the same way, before any read (a record that exists and cannot be read is a stop,
    not an absence, 263 item 23)."""
    db = fresh(tmp_path / "unmigrated.db", monkeypatch, record_tables=True)
    with db.session_scope() as s, pytest.raises(v.GateRefused, match="migrate_availability_record.py has not run"):
        v.availability_record(s)


def test_263_23_a_soccer_fact_the_reader_cannot_map_refuses(tmp_path, monkeypatch):
    """263 item 25: "The soccer source and its attrs key are named by the soccer feed's adapter PR when one is declared
    (none today), and I rule the mapping with it." A soccer fact in force at the decision instant (written by the
    record's only writer) cannot be mapped to the term's entry, so the read refuses with its reason, never guessed; the
    same fact recorded after the instant is not read (the recorded clock)."""
    db = _migrated(tmp_path, monkeypatch)
    at = datetime(2025, 9, 1, 8)
    rcpt = avr.write_observation(
        {"sport": "soccer", "source": "sportsdataio_goalies", "endpoint": "https://example.invalid/injuries",
         "status": "complete", "fetched_at": at, "http_status": 200},
        [{"kind": "injury_status", "source_player_id": "p1", "player_name": "A Player", "source_team": "XX FC",
          "attrs": {"status": "Missing Fixture"}}])
    assert rcpt.written and rcpt.assertions == 1
    with db.session_scope() as s:
        rec = v.availability_record(s)
        with pytest.raises(v.GateRefused, match="sportsdataio_goalies.*injury_status.*cannot be mapped"):
            rec.at(at + timedelta(hours=1))
        assert rec.at(at - timedelta(hours=1)).state == v.NO_RECORD


def test_263_23_the_run_s_record_is_read_while_the_copy_is_open(declared, monkeypatch):
    """_load reads the copy's record at every decision instant its rows can need, while the copy is open (the reader
    holds no session past it), through record.as_of; an instant it did not read is refused, never guessed; the walk
    and the fingerprint read those answers."""
    import migrate_availability_record as mig
    from src.walters import registry as reg
    monkeypatch.chdir(declared["tmp"])
    assert mig.main() == 0
    copy = str(_backup(declared["tmp"] / "store.db", declared["tmp"] / "copies" / "copy-rec.db"))
    slots = reg.get(v.EID, reg.LEDGER)[v.SLOTS_KEY]
    _, _, _, rows, record = v._load(copy, slots)
    d = v.visibility_bound(rows[-1].utc_date, slots["visibility"])
    got = v.read_availability(record, d)
    assert got.state == v.NO_RECORD and got.reason == v.NO_SOCCER_FACT_REASON
    with pytest.raises(v.GateRefused, match="not read while the copy was open"):
        record.at(datetime(1999, 1, 1))
    L = v.preflight_lines(reg.get(v.EID, reg.LEDGER), copy)
    assert len(_fp(L)) == 64 and any(v.NO_SOCCER_FACT_REASON in x for x in L)
    _nothing(declared)


def test_263_23_the_stale_not_merged_text_is_gone():
    """264 item 2: "The stale "not merged" refusal message is the reader follow-up's to rewrite (263 item 23)"."""
    src = (Path(v.__file__)).read_text()
    assert "which is not merged" not in src and "schema PR is not merged" not in src
    assert "not merged" not in v.ABSENT_REASON and v.RECORD_TABLES == avr.TABLES


# ------------------------------------------------- 263 items 14 and 15: exclusion by cause, never a refusal --

def test_263_15_an_arrival_off_the_pyramid_takes_the_outside_the_store_prior():
    """263 item 15, fail-first: "An arrival OFF the declared pyramid is NOT a refusal: it takes the outside-the-store
    prior, is counted and labelled. The run never stops on a club's provenance." Club 7 arrives in PL 2021/22 from BL1
    (off the pyramid): the walk prices it, its fit centres club 7 on the promoted (outside-the-store) prior, and the
    census names it."""
    from src.models import joint_poisson as jp
    R = lambda i, c, se, d, h, a, hg=1, ag=1: _row(i, c, se, datetime(2020 + d // 400, 9, 1) + timedelta(  # noqa
        days=d % 400), h, a, hg, ag)
    rows = [R(1, "BL1", "2020/21", 0, 7, 8), R(2, "PL", "2020/21", 0, 1, 2, 2, 1), R(3, "PL", "2020/21", 1, 2, 1),
            R(4, "PL", "2021/22", 400, 7, 1, 0, 1), R(5, "PL", "2021/22", 401, 1, 7)]
    assert v.thin_season_keys(rows) == []                              # goals on both sides: item 14 is not in play
    got = v.off_pyramid_arrivals(rows, v.thin_season_keys(rows))
    assert len(got) == 1 and "PL 2021/22: club 7 arrives from ['BL1']" in got[0] and "outside-the-store" in got[0]
    w = v.walk(rows, rows[-1:], v.canon_params(V22P, False, "LEAGUE"), "kickoff")
    assert len(w["soccer-v23"]) == 1
    snap = v.snapshot_from_rows(rows, rows[-1].utc_date, v.canon_params(V22P, False, "LEAGUE"), "kickoff")
    info = v.predict(snap, v.Fixture.of(rows[-1]), "soccer-v23")["info"]
    assert info["arrivals_off_pyramid"] == {7: ["BL1"]}
    seen = []
    real = jp.fit
    jp_fit = lambda obs, relegated=frozenset(): seen.append(relegated) or real(obs, relegated=relegated)  # noqa
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(jp, "fit", jp_fit)
        v.predict(snap, v.Fixture.of(rows[-1]), "soccer-v23")
    assert seen and all(7 not in r for r in seen)                      # not relegated: the promoted prior


def _thin_and_off_store():
    """On the declared store: XL2, a LEAGUE competition with a 2024/25 holding no away goal (two rows, a thin season:
    263 item 14) and a 2025/26 with goals; and a PL club arriving in 2025/26 that also played in XL1, off the declared
    pyramid, in 2024/25 (263 item 15)."""
    import src.db.database as dbm
    from src.db.schema import Competition, Match
    with dbm.session_scope() as s:
        pl = s.query(Competition).filter(Competition.code == "PL").one()
        pl_24 = {t for m in s.query(Match).filter(Match.competition_id == pl.id, Match.season == "2024/25")
                 for t in (m.home_team_id, m.away_team_id)}
        pl_25 = {t for m in s.query(Match).filter(Match.competition_id == pl.id, Match.season == "2025/26")
                 for t in (m.home_team_id, m.away_team_id)}
    arriving = sorted(pl_25 - pl_24)[0]
    t = datetime(2024, 9, 3, 15)
    ids = _add_matches([("XL2", "LEAGUE", "2024/25", t, "a", "b", 1, 0, REG),
                        ("XL2", "LEAGUE", "2024/25", t + timedelta(days=7), "b", "a", 2, 0, REG),
                        ("XL1", "LEAGUE", "2024/25", t + timedelta(days=1), arriving, "c", 2, 1, REG)]
                       + [("XL2", "LEAGUE", "2025/26", datetime(2025, 9, 2 + 7 * k, 15), "a", "b", 1 + k % 2, 1, REG)
                          for k in range(3)])
    return arriving, ids


def test_263_14_15_thin_seasons_are_excluded_and_off_pyramid_arrivals_priced_never_refused(declared, monkeypatch):
    """263 items 14 and 15, fail-first (on 667dc25f the preflight REFUSED the arrival and gave no fingerprint, and a
    window of the thin season alone refused the fit after the reservation): the preflight names the thin season as
    excluded by cause BEFORE the reservation and the arrival as taking the outside-the-store prior, both counted, and
    gives the fingerprint; the run walks (the real walk), leaves the thin season's rows out of the scored set, and its
    record labels both counts."""
    from src.walters import registry as reg
    arriving, _ = _thin_and_off_store()
    copy = str(_backup(declared["tmp"] / "store.db", declared["tmp"] / "copies" / "copy-thin.db"))
    L = v.preflight_lines(reg.get(v.EID, reg.LEDGER), copy)
    text = "\n".join(L)
    assert "thin seasons excluded by cause (addendum 263 item 14): 1 competition-season(s), 2 row(s) — XL2 2024/25" \
           in text, text
    assert f"PL 2025/26: club {arriving} arrives from ['ELC', 'XL1']" in text and "outside-the-store" in text
    # XL2's first in-scope season is thin, so the walk prices 2025/26 as its first season: the line names that one
    xl2 = next(x for x in L if x.startswith("  XL2: "))
    assert xl2.endswith("first season in scope 2025/26 (XL2 2024/25 excluded by cause, addendum 263 item 14)"), xl2
    fp = _fp(L)
    r = v.run("ARCHITECT test word", fp, db=copy, no_fetch=True)
    scored = set(r["scored_ids"])
    import src.db.database as dbm
    from src.db.schema import Competition, Match
    with dbm.session_scope() as s:
        xl2 = s.query(Competition).filter(Competition.code == "XL2").one()
        thin = {m.id for m in s.query(Match).filter(Match.competition_id == xl2.id, Match.season == "2024/25")}
        later = {m.id for m in s.query(Match).filter(Match.competition_id == xl2.id, Match.season == "2025/26")}
    assert len(thin) == 2 and not (thin & scored) and later <= scored
    assert r["thin_excluded"] == [["XL2", "2024/25"]]
    labels = "\n".join(v.record_labels(r))
    assert "thin seasons excluded by cause (addendum 263 item 14): 1 competition-season(s), 2 row(s)" in labels
    assert "arrivals off the declared pyramid (addendum 263 item 15): 1" in labels
    e = v.record(r, "ARCHITECT test word")
    assert e["run"]["result"]["labels"] == v.record_labels(r)


def test_263_14_the_thin_set_is_frozen_in_the_params_and_drops_out_of_the_v23_window():
    """263 item 14: the exclusion set is the preflight's census of the walked history, carried in the snapshot's params
    (both paths read it from there); a window whose S−1 is excluded is a first season (the weak prior), so the fit that
    refused on the thin S−1 alone now prices; the v22 arm's history is not touched (v22 re-walked is not redefined)."""
    from src.models import joint_poisson as jp
    rows = [_row(1, "XX", "2020/21", datetime(2020, 9, 1), 1, 2, 2, 0),
            _row(2, "XX", "2020/21", datetime(2020, 9, 8), 2, 1, 1, 0),
            _row(3, "XX", "2021/22", datetime(2021, 9, 1, 15), 1, 2, 1, 1)]
    assert v.thin_season_keys(rows) == [("XX", "2020/21")]
    plain = v.canon_params(V22P, False, "LEAGUE")
    with pytest.raises(jp.FitRefused):
        v.walk(rows, rows[-1:], plain, "day")
    pj = v.canon_params(V22P, False, "LEAGUE", thin_excluded=v.thin_season_keys(rows))
    assert json.loads(pj)["thin_excluded"] == [["XX", "2020/21"]]
    w = v.walk(rows, rows[-1:], pj, "day")
    snap = v.snapshot_from_rows(rows, rows[-1].utc_date, pj, "day")
    info = v.predict(snap, v.Fixture.of(rows[-1]), "soccer-v23")["info"]
    assert info["first_season"] is True and info["prev_season"] is None
    assert v.predict(snap, v.Fixture.of(rows[-1]), "v22")["info"]["n_cur"] == 0
    assert len(w["v22"]) == len(w["soccer-v23"]) == 1
    v22_plain = v.predict(v.snapshot_from_rows(rows, rows[-1].utc_date, plain, "day"), v.Fixture.of(rows[-1]), "v22")
    assert v.predict(snap, v.Fixture.of(rows[-1]), "v22")["p_home"] == v22_plain["p_home"]


def test_263_17_the_tie_order_is_stated_in_the_record():
    """263 item 17: "SQLite's id-ascending, pinned, accepted as "v22's" for the bar and stated in the record"."""
    r = {"slots": {**SLOTS, "visibility": "day"}, "aet_pen": {"scored": 0, "history": 0}, "thin_excluded": [],
         "thin_rows": 0, "off_pyramid": []}
    assert any(v.V22_TIE_ORDER_LABEL in x for x in v.record_labels(r))
    assert "id-ascending" in v.V22_TIE_ORDER_LABEL and "addendum 263 item 17" in v.V22_TIE_ORDER_LABEL


# ----------------------------------- review round (pre-PR): the thin set reaches the census and the first seasons --

def _xx_rows(specs, others=()):
    """A synthetic LEAGUE_REGULAR history: XX's seasons from `specs` ((season, year, teams, thin)), each a double
    round-robin of `teams` (a thin season has no away goal: 263 item 14), plus `others` in the same form for other
    codes ((code, season, year, teams, thin))."""
    rows, i = [], 0
    for code, season, y, teams, thin in [("XX", *s) for s in specs] + list(others):
        pairs = [(h, a) for h in teams for a in teams if h != a]
        for j, (h, a) in enumerate(pairs):
            i += 1
            hg, ag = ((j % 3) + 1, 0) if thin else ((j % 3), (j + 1) % 2 + (j % 2))
            rows.append(_row(i, code, season, datetime(y, 9, 1, 15 if code == "XX" else 17) + timedelta(days=3 * j),
                             h, a, hg, ag, f"Regular Season - {j + 1}"))
    return sorted(rows, key=v.Row.key)


RSL = {**SLOTS, "scope": "LEAGUE_REGULAR", "first_season": "score_under_prior", "visibility": "day"}


def test_263_14_the_off_pyramid_census_follows_the_thin_set():
    """263 items 14 and 15 together (review, pre-PR): XX 2023/24 is thin, so XX 2024/25's window has no S−1 (a first
    season, the weak prior; window_obs) and club 9, arriving from SA (off the pyramid), is priced on the first-season
    prior, not the outside-the-store one. The census (printed by the preflight, written to the run record as
    "off_pyramid") must say what the walk does: no XX 2024/25 line, matching predict's arrivals_off_pyramid. SA 2024/25,
    whose S−1 is not thin, still names its off-pyramid arrival."""
    rows = _xx_rows([("2023/24", 2023, [1, 2, 3, 4], True), ("2024/25", 2024, [1, 2, 3, 9], False),
                     ("2025/26", 2025, [1, 2, 3, 9], False)],
                    [("SA", "2023/24", 2023, [9, 10, 11], False), ("SA", "2024/25", 2024, [4, 10, 11], False)])
    hist, thin, sc = v.the_pot(rows, RSL)
    assert thin == [("XX", "2023/24")]
    ar = v.off_pyramid_arrivals(hist, thin)
    assert not [a for a in ar if a.startswith("XX 2024/25")], ar
    assert [a for a in ar if a.startswith("SA 2024/25")] == [
        "SA 2024/25: club 4 arrives from ['XX'] (S−1 2023/24), off the declared pyramid: the outside-the-store prior"]
    pj = v.canon_params(V22P, False, "LEAGUE_REGULAR", thin_excluded=thin)
    r = next(x for x in sc if x.code == "XX" and x.season == "2024/25" and 9 in (x.home_id, x.away_id))
    info = v.predict(v.snapshot_from_rows(hist, r.utc_date, pj, "day"), v.Fixture.of(r), "soccer-v23")["info"]
    assert info["first_season"] is True and info["arrivals_off_pyramid"] == {}


def test_264_2a_263_14_a_thin_s_minus_1_is_a_first_season_in_the_census_and_the_preflight_line():
    """264 item 2(a) one layer up (review, pre-PR): the season the walk prices as a first season is the one the
    preflight names. A thin first in-scope season (XX 2023/24) makes 2024/25 the first season (first_seasons is
    computed over the in-scope history less the thin set); a thin season mid-history (YY 2024/25) makes the season
    after it a first season too, and first_season_windows names it. The walk's first_season flag agrees on every
    scored season."""
    rows = _xx_rows([("2023/24", 2023, [1, 2, 3, 4], True), ("2024/25", 2024, [1, 2, 3, 4], False),
                     ("2025/26", 2025, [1, 2, 3, 4], False)],
                    [("YY", "2023/24", 2023, [5, 6, 7], False), ("YY", "2024/25", 2024, [5, 6, 7], True),
                     ("YY", "2025/26", 2025, [5, 6, 7], False)])
    hist, thin, sc = v.the_pot(rows, RSL)
    assert thin == [("XX", "2023/24"), ("YY", "2024/25")]
    assert v.first_seasons(rows, "LEAGUE_REGULAR") == {"XX": "2024/25", "YY": "2023/24"}
    assert v.first_season_windows(rows, "LEAGUE_REGULAR") == {"XX": ["2024/25"], "YY": ["2023/24", "2025/26"]}
    w = v.walk(hist, sc, v.canon_params(V22P, False, "LEAGUE_REGULAR", thin_excluded=thin), "day")
    flags: dict = {}
    for r, st in zip(sc, w["strata"]):
        flags.setdefault((r.code, r.season), set()).add(st["first_season"])
    want = {(c, se) for c, ses in v.first_season_windows(rows, "LEAGUE_REGULAR").items() for se in ses}
    assert flags == {k: {k in want} for k in flags}, flags
    warm = {**RSL, "first_season": "exclude_as_warmup"}
    assert ("XX", "2024/25") not in {(r.code, r.season) for r in v.the_pot(rows, warm)[2]}


def test_263_25_a_soccer_fact_of_another_kind_is_no_input_and_never_refuses(tmp_path, monkeypatch):
    """263 item 25: "`injury_status` is one entry ..., the other kinds no input of v23". A soccer depth_rank or
    plays_for fact in force at the decision instant is not read by the term's reader (record.as_of with
    kind=TERM_KIND), so it neither refuses the run nor turns the term on: NO_RECORD with its reason. An injury_status
    fact in force still refuses (its mapping is the soccer feed's PR's)."""
    db = _migrated(tmp_path, monkeypatch)
    at = datetime(2025, 9, 1, 8)
    for kind, attrs in (("depth_rank", {"rank": 1, "position": "G"}), ("plays_for", {})):
        rcpt = avr.write_observation(
            {"sport": "soccer", "source": "sportsdataio_goalies", "endpoint": f"https://example.invalid/{kind}",
             "status": "complete", "fetched_at": at, "http_status": 200},
            [{"kind": kind, "source_player_id": "p1", "player_name": "A Player", "source_team": "XX FC",
              "attrs": attrs}])
        assert rcpt.written and rcpt.assertions == 1, (kind, rcpt)
    from src.db.schema import Sport
    with db.session_scope() as s:
        assert len(avr.as_of(s, Sport.SOCCER, at + timedelta(hours=1))) == 2           # both in force, both soccer
        got = v.availability_record(s).at(at + timedelta(hours=1))
    assert got.state == v.NO_RECORD and got.reason == v.NO_SOCCER_FACT_REASON
    avr.write_observation(
        {"sport": "soccer", "source": "sportsdataio_goalies", "endpoint": "https://example.invalid/injuries",
         "status": "complete", "fetched_at": at, "http_status": 200},
        [{"kind": "injury_status", "source_player_id": "p1", "player_name": "A Player", "source_team": "XX FC",
          "attrs": {"status": "Missing Fixture"}}])
    with db.session_scope() as s, pytest.raises(v.GateRefused, match=r"1 soccer injury_status fact\(s\) in force"):
        v.availability_record(s).at(at + timedelta(hours=1))
