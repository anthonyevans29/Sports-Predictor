"""UNL SHADOW (ARCHITECT 2026-10-02): intl-elo-v2 (PASS, confirmation window)
as a greyed three-way shadow. Pins: it refuses without the registry's run
record + PASS; its multipliers are READ from the record (never refit); rows are
engine model_shadow, labelled "PASS — confirmation n/60", three-way, never in
the Prediction table; grading is the top pick vs the three-way close; the
confirmation set is competitive, after the verdict, the first n FIXTURES
whatever their status, frozen once (review on #248: a pending earlier fixture
leaves the read incomplete, never replaced by a later game); the intl-daily
chain syncs incrementally, then the venue step, then the export. The real
ledger is never touched (the registry is monkeypatched)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Odds, Prediction, Sport, Team
from src.walters import intl_elo as ie
from src.walters import intl_shadow as us
from src.walters import registry as reg

VERDICT_AT = datetime(2096, 1, 1)
NOW = datetime(2096, 3, 10, 12, 0)
ENTRY = {"id": "intl-elo-v2", "status": "confirming",
         "run": {"result": {"fit_c_mult": 2.0, "fit_k_mult": 1.25}},
         "verdict": {"verdict": "PASS", "at": "2096-01-01T00:00:00Z"},
         "confirmation_plan": {"n_games": 3, "metric": "log_loss", "bar": 1.0986, "must_beat_reference": True,
                               "reference": "naive - 0.010"}}


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        def comp(code):
            c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.SOCCER, code=code, name=code, area="I", type="INTL")
                s.add(c)
                s.flush()
            return c
        unl, fr = comp("UNL"), comp("FRIENDLIES_INT")
        t = [Team(sport=Sport.SOCCER, name=f"US Probe {i}") for i in range(4)]
        s.add_all(t)
        s.flush()

        def m(c, h, a, when, hs=None, as_=None, status=MatchStatus.FINISHED, season="2095/96"):
            x = Match(sport=Sport.SOCCER, competition_id=c.id, season=season, utc_date=when, status=status,
                      status_raw="FT" if status == MatchStatus.FINISHED else None, home_team_id=t[h].id,
                      away_team_id=t[a].id, home_score=hs, away_score=as_)
            s.add(x)
            s.flush()
            return x.id
        m(unl, 0, 1, datetime(2019, 6, 1), 1, 1, season="2018/19")   # the training stream (2018..2024-08)
        tn = m(unl, 2, 3, datetime(2019, 6, 2), 2, 1, season="2018/19")
        s.add(IntlMatchVenue(match_id=tn, venue_id=2, venue_country="Elsewhere", home_country="Probeland",
                             neutral_v3=True, rule="r"))                    # naive needs a neutral train game
        ids = {"after1": m(unl, 0, 1, datetime(2096, 2, 1), 2, 0), "after2": m(unl, 2, 3, datetime(2096, 2, 2), 1, 1),
               "friendly": m(fr, 0, 2, datetime(2096, 2, 3), 0, 0), "after3": m(unl, 1, 3, datetime(2096, 2, 4), 0, 1),
               "after4": m(unl, 3, 0, datetime(2096, 2, 5), 1, 0),
               # the #248 review's case: an EARLIER eligible fixture still unplayed (pending)
               "late": m(unl, 2, 0, datetime(2096, 2, 1, 12), status=MatchStatus.SCHEDULED),
               "up": m(unl, 0, 3, NOW + timedelta(hours=6), status=MatchStatus.SCHEDULED),
               "far": m(unl, 1, 2, NOW + timedelta(hours=60), status=MatchStatus.SCHEDULED)}
        s.add(IntlMatchVenue(match_id=ids["up"], venue_id=1, venue_country="Nowhere", home_country="Probeland",
                             neutral_v3=True, rule="r"))
        for bk in ("b1", "b2"):
            for sel, price in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)):
                s.add(Odds(match_id=ids["after1"], source="t", bookmaker=bk, market="1X2", selection=sel,
                           price_decimal=price, captured_at=datetime(2096, 1, 31, 12)))
        ids["teams"] = [x.id for x in t]
    return ids


@pytest.fixture
def frozen_ok(monkeypatch):
    monkeypatch.setattr(reg, "get", lambda eid, path=None: ENTRY if eid == "intl-elo-v2" else None)


def test_refuses_without_run_record_or_pass(monkeypatch):
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    with pytest.raises(us.ShadowRefused, match="no run record"):
        us.frozen()
    monkeypatch.setattr(reg, "get", lambda eid, path=None: {**ENTRY, "verdict": None})
    with pytest.raises(us.ShadowRefused, match="no PASS"):
        us.frozen()


def test_multipliers_are_read_from_the_record(frozen_ok):
    e, c, k = us.frozen()
    assert (c, k) == (2.0, 1.25)


def test_cohort_is_the_first_n_fixtures_whatever_their_status(world, frozen_ok):
    with session_scope() as s:
        co = us.cohort(ENTRY, s)
        s.rollback()
    # friendly out; the SCHEDULED "late" fixture is IN (result availability never enters); after3 is game n+1
    assert co["state"] == "provisional" and co["ids"] == [world["after1"], world["late"], world["after2"]]


def test_export_rows_are_three_way_shadow_labelled_and_never_predictions(world, frozen_ok, tmp_path):
    path, doc = us.export(now=NOW, out_dir=str(tmp_path))
    assert Path(path).name == "unl_shadow_2096-03-10_1200.json"
    assert (doc["engine"], doc["model_version"], doc["contains_predictions"]) == ("model_shadow", "intl_elo_v2", False)
    assert doc["gate_verdict"] == "PASS — confirmation 2/3"                     # cohort: 2 labelled, "late" pending
    rows = {r["match_id"]: r for r in doc["predictions"]}
    assert world["up"] in rows and world["far"] not in rows                     # the 36h window
    p = rows[world["up"]]["prediction"]
    assert p["home_win_prob"] + p["draw_prob"] + p["away_win_prob"] == pytest.approx(1.0, abs=1e-3)
    assert p["neutral_v3"] is True and p["home_adv_applied"] == 0.0             # v3 neutral -> no home term
    assert p["top_pick_prob"] == max(p["home_win_prob"], p["draw_prob"], p["away_win_prob"])
    assert rows[world["up"]]["gate_verdict"] == doc["gate_verdict"] and doc["fit"]["c_mult"] == 2.0
    with session_scope() as s:
        n = s.execute(select(func.count(Prediction.id)).where(Prediction.match_id.in_(list(rows)))).scalar()
    assert n == 0


def test_grade_is_top_pick_vs_the_three_way_close(world, frozen_ok, tmp_path):
    call = {"match_id": world["after1"], "utc_date": "2096-02-01T00:00:00",
            "prediction": {"top_pick": "home_win", "top_pick_prob": 0.55}}
    (tmp_path / "unl_shadow_2096-01-31_1200.json").write_text(json.dumps(
        {"engine": "model_shadow", "exported_at": "2096-01-31T12:00:00", "predictions": [call]}))
    r = us.grade(days=10_000, export_dir=str(tmp_path), now=NOW)
    inv = {k: 1 / v for k, v in {"HOME": 2.0, "DRAW": 3.4, "AWAY": 3.8}.items()}
    fair_h = inv["HOME"] / sum(inv.values())
    assert r["graded"] == 1 and r["priced"] == 1 and r["mean_clv_pp"] == round((0.55 - fair_h) * 100, 2)
    md = us.results_section(10_000, export_dir=str(tmp_path))
    assert md.startswith("## UNL — SHADOW, CONFIRMATION WINDOW") and "not a record" in md


def test_a_pending_cohort_fixture_leaves_the_read_incomplete_never_replaced(world, frozen_ok):
    """The #248 review's reproduction: game n+1 (after3) completes while an
    earlier eligible fixture is still SCHEDULED. The read stays 2/3 and
    incomplete; after3 is never admitted; when the result arrives the cohort
    is unchanged."""
    r = us.confirmation_read(now=NOW)
    assert (r["n"], r["cohort_size"], r["complete"]) == (2, 3, False)
    assert set(r["scored_ids"]) == {world["after1"], world["after2"]} and world["after3"] not in r["scored_ids"]
    assert r["pending"] == [{"id": world["late"], "status": "scheduled"}]
    assert r["first_game_at"] == "2096-02-01T00:00:00Z"
    assert r["reference_log_loss"] == pytest.approx(r["naive_log_loss"] - 0.010)
    with session_scope() as s:
        late = s.get(Match, world["late"])
        late.status, late.status_raw, late.home_score, late.away_score = MatchStatus.FINISHED, "FT", 1, 1
    try:
        r2 = us.confirmation_read(now=NOW)
        assert set(r2["scored_ids"]) == {world["after1"], world["late"], world["after2"]} and not r2["pending"]
        assert r2["complete"] is False                       # provisional: never recordable until frozen
    finally:
        with session_scope() as s:
            late = s.get(Match, world["late"])
            late.status, late.status_raw, late.home_score, late.away_score = MatchStatus.SCHEDULED, None, None, None


def test_frozen_cohort_binds_the_read_and_record_refuses_until_complete(world, monkeypatch, tmp_path):
    ids = [world["after1"], world["late"], world["after2"]]
    (tmp_path / "intl-elo-v2.cohort.txt").write_text("\n".join(str(i) for i in sorted(ids)) + "\n")
    e = {**ENTRY, "confirmation_cohort": {"n": 3, "ids_sha256": reg._ids_sha(ids),
                                          "ids_file": "docs/registry/ids/intl-elo-v2.cohort.txt"}}
    monkeypatch.setattr(reg, "get", lambda eid, path=None: e if eid == "intl-elo-v2" else None)
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path))
    r = us.confirmation_read(now=NOW)
    assert r["cohort_state"] == "frozen" and r["n"] == 2 and r["complete"] is False
    from click.testing import CliRunner
    from cli import cli
    out = CliRunner().invoke(cli, ["intl-elo-confirm", "--record", "--ruling", "ARCHITECT: x"])
    assert out.exit_code == 2 and "cohort fixture(s) lack a label" in out.output       # real clock: 2096 is pending
    out = CliRunner().invoke(cli, ["intl-elo-confirm", "--freeze-cohort"])
    assert out.exit_code == 2 and "already frozen" in out.output


def test_only_unscoreable_cohort_fixtures_are_released_next_after_the_cohort(world, monkeypatch, tmp_path):
    """ARCHITECT 2026-10-02: an UNSCOREABLE cohort fixture (CANC / ABD; AWD / WO
    — "unscoreable is the criterion, not the status label") is released and
    replaced by the next eligible fixture AFTER the cohort, the raw code as
    reason; a postponed fixture, or a FT row still waiting for its score, stays."""
    ids = [world["after1"], world["late"], world["after2"]]
    (tmp_path / "intl-elo-v2.cohort.txt").write_text("\n".join(str(i) for i in sorted(ids)) + "\n")
    e = {**ENTRY, "confirmation_cohort": {"n": 3, "ids_sha256": reg._ids_sha(ids),
                                          "ids_file": "docs/registry/ids/intl-elo-v2.cohort.txt"}}
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path))

    def set_row(mid, status, raw, hs=None, as_=None):
        with session_scope() as s:
            m = s.get(Match, mid)
            m.status, m.status_raw, m.home_score, m.away_score = status, raw, hs, as_

    def due():
        with session_scope() as s:
            out = us.substitutions_due(e, s)
            s.rollback()
        return [(d["released"]["id"], d["replacement"]["id"], d["reason"]) for d in out]
    try:
        set_row(world["late"], MatchStatus.POSTPONED, "PST")                   # postponed: stays
        set_row(world["after1"], MatchStatus.FINISHED, "FT")                   # FT, score not in yet: lag, stays
        assert due() == []
        set_row(world["after2"], MatchStatus.CANCELLED, "ABD")                 # abandoned: released
        assert due() == [(world["after2"], world["after3"], "ABD")]            # after3 = the 4th eligible (friendly out)
        # once recorded, the next unscoreable one takes the NEXT fixture (after4), never after3 again
        e["confirmation_cohort"]["substitutions"] = [{"released": world["after2"], "replacement": world["after3"]}]
        set_row(world["after1"], MatchStatus.FINISHED, "AWD", 3, 0)            # awarded: finished, unscoreable
        assert due() == [(world["after1"], world["after4"], "AWD")]
    finally:
        set_row(world["late"], MatchStatus.SCHEDULED, None)
        set_row(world["after2"], MatchStatus.FINISHED, "FT", 1, 1)
        set_row(world["after1"], MatchStatus.FINISHED, "FT", 2, 0)


def test_intl_daily_chain_and_cli_refusal(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import chains
    steps = chains.CHAINS["intl-daily"]["steps"]
    # the cups' daily schedule read after the intl steps (#707), each cup's sync-teams immediately before it (#728,
    # addendum 204 3(b)); then coverage --json, last (#805, addendum 225 item 5)
    assert [s[0] for s in steps] == (["intl-sync", "intl-venue-sync", "export-unl-predictions"]
                                     + ["sync-teams", "sync-matches"] * 4 + ["coverage"])
    assert [s[2] for s in steps[3:-1]] == ["EFL", "EFL", "CL", "CL", "UEL", "UEL", "FAC", "FAC"]
    assert steps[0][1:3] == ["--since", "{today}"] and "export-unl-predictions" in chains.UNMETERED
    from click.testing import CliRunner
    from cli import cli
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    out = CliRunner().invoke(cli, ["export-unl-predictions"])
    assert out.exit_code == 2 and "REFUSED" in out.output


def test_the_unl_shadow_file_carries_the_producing_git_sha_and_none_stays_none(world, frozen_ok, tmp_path,
                                                                               monkeypatch):
    """ARCHITECT 2026-11-04 (addendum 249 item 2): "the git_sha stamp goes on ALL FIVE exports (the NHL shadow, the
    UNL shadow, ...) — the same one-line header stamp, null when git has no SHA, nothing else in any file; the compare
    masks git_sha so no field difference appears across the deploy." tests/git_sha_stamp.py holds the checks."""
    from tests.git_sha_stamp import check_stamp
    check_stamp(lambda out, i: us.export(now=NOW, out_dir=out), tmp_path, monkeypatch)


# ------------------------------------------- intl-elo-confirm --db COPY (ARCHITECT 2026-11-11, addendum 346 item 1) --
# "NOTHING ELSE CHANGES: the computation, the frozen cohort, the plan, the bar, the refusals [...], and the behavior
# without `--db`, which a test pins byte for byte on the console. [...] Tests: the fence's refusals; the no-flag read on
# a copy equals the read on the same store through the app's engine; `--record --db` writes the two registry files and
# never touches the copy (its bytes' sha256 before and after); the default path unchanged."

# main's console (1ec357e4) for the no-flag read of this module's world at NOW, captured before the change. The one
# figure taken from the store is the eligible count: other modules' rows share the throwaway DB in a full run (7 when
# this file runs alone, 16 in the full suite); it is counted by eligible_fixtures, which this change does not touch.
def pin_no_flag() -> str:
    with session_scope() as s:
        n = len(us.eligible_fixtures(s, ENTRY))
        s.rollback()
    return ("INTL-ELO-V2 CONFIRMATION · cohort PROVISIONAL (3/3 fixtures; " + str(n) + " eligible stored) · 2/3 "
            "labelled · first 2096-02-01T00:00:00Z\n"
            "  pending 1: {'scheduled': 1}\n"
            "  so far: log-loss 1.0346 · naive 13.8155 · reference (naive − 0.010) 13.8055 · bar 1.0986 — not a "
            "verdict until the cohort is complete\n")


def _app_db_path() -> Path:
    from src.db.database import get_engine
    return Path(get_engine().url.database).resolve()


def _copy(tmp_path, name="copy.db") -> Path:
    """A .backup-API copy of the test store outside data/ (law 5: never a file copy, never under data/)."""
    import sqlite3
    dst = tmp_path / name
    src, out = sqlite3.connect(str(_app_db_path())), sqlite3.connect(str(dst))
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    assert not any(dst.with_name(dst.name + x).exists() for x in us.COPY_SIDECARS)
    return dst


def _run(args):
    from click.testing import CliRunner
    from cli import cli
    return CliRunner().invoke(cli, ["intl-elo-confirm", *args])


def test_346_the_no_flag_read_without_db_is_unchanged_byte_for_byte(world, frozen_ok, monkeypatch):
    monkeypatch.setattr(us, "utc_now_naive", lambda: NOW)
    out = _run([])
    assert out.exit_code == 0 and out.output == pin_no_flag()


def test_346_the_read_on_a_copy_equals_the_read_on_the_same_store(world, frozen_ok, monkeypatch, tmp_path):
    from src.walters import mlb_pitchers_gate as mp
    copy = _copy(tmp_path)
    app = us.confirmation_read(now=NOW)
    with mp.readonly_session(copy) as s:
        assert us.confirmation_read(now=NOW, s=s) == app
    monkeypatch.setattr(us, "utc_now_naive", lambda: NOW)
    out = _run(["--db", str(copy)])
    head, rest = out.output.split("\n", 1)
    assert out.exit_code == 0 and rest == pin_no_flag()                     # the same console, after one line
    assert head == (f"--db {copy.resolve()} · sha256 {us.copy_sha256(copy)} · a .backup copy, opened "
                    "mode=ro&immutable=1 (the app's database is not read)")


def test_346_the_fence_refuses_and_reads_nothing(world, frozen_ok, monkeypatch, tmp_path):
    from src.walters import registry as _reg
    import sqlite3
    data_dir = Path(_reg.ROOT) / "data"
    assert us.COPY_SIDECARS == ("-wal", "-shm", "-journal")
    sides = []
    for sfx in ("-wal", "-shm", "-journal"):
        side = _copy(tmp_path, f"side{sfx}.db")
        side.with_name(side.name + sfx).write_bytes(b"")
        sides.append((str(side), f"{sfx} sidecar"))
    junk = tmp_path / "junk.db"
    junk.write_text("not a database\n")
    bare = tmp_path / "bare.db"                                  # has matches, lacks the rest of what the read needs
    con = sqlite3.connect(str(bare))
    con.execute("CREATE TABLE matches (id INTEGER)")
    con.commit()
    con.close()
    cases = [(str(tmp_path / "missing.db"), "no file at"),
             (str(data_dir / "never-created.db"), "resolves under the repo's data/"),
             (str(_app_db_path()), "the app's configured database"),
             *sides,
             (str(junk), "cannot be read through a mode=ro + immutable=1 URI"),
             (str(bare), "the copy cannot be read for table competitions")]
    for db, why in cases:
        out = _run(["--db", db])
        assert out.exit_code == 2 and out.output.startswith("REFUSED: ") and why in out.output, (db, out.output)
        assert "INTL-ELO-V2 CONFIRMATION" not in out.output and "nothing read, nothing written" in out.output
    assert not (data_dir / "never-created.db").exists()                  # never created (law 5)


def test_346_freeze_and_substitute_are_refused_with_db(world, frozen_ok, tmp_path, monkeypatch):
    copy = _copy(tmp_path)
    called = []
    monkeypatch.setattr(us, "frozen", lambda: called.append(1))
    for flag in ("--freeze-cohort", "--substitute"):
        out = _run([flag, "--db", str(copy)])
        assert out.exit_code == 2 and out.output.startswith(f"REFUSED: --db reads a copy; {flag} is a registry "
                                                            "decision made on the writer of record's own store")
    assert called == []                                                   # nothing read


def test_346_record_on_a_copy_writes_the_two_registry_files_and_never_touches_the_copy(world, monkeypatch, tmp_path):
    """The read is the COPY's: the app's store is changed after the copy is taken (after3 back to SCHEDULED, so a read
    of it would be incomplete and refused), and the record still completes on the copy. The registry files are the
    ledger and ids/intl-elo-v2.confirm.txt (tmp paths here); the copy's bytes are the same before and after."""
    ids = sorted([world["after1"], world["after2"], world["after3"]])
    reg_dir = tmp_path / "registry"
    ids_dir = reg_dir / "ids"
    ids_dir.mkdir(parents=True)
    (ids_dir / "intl-elo-v2.cohort.txt").write_text("\n".join(str(i) for i in ids) + "\n")
    ledger = reg_dir / "experiments.json"
    e = {**ENTRY, "confirmation_cohort": {"n": 3, "ids_sha256": reg._ids_sha(ids),
                                          "ids_file": "docs/registry/ids/intl-elo-v2.cohort.txt"}}
    ledger.write_text(json.dumps([e], indent=2) + "\n")
    get0, record0 = reg.get, reg.record_confirmation
    monkeypatch.setattr(reg, "get", lambda eid, path=None: get0(eid, path=str(ledger)))
    monkeypatch.setattr(reg, "IDS_DIR", str(ids_dir))
    monkeypatch.setattr(reg, "record_confirmation",
                        lambda *a, **k: record0(*a, path=str(ledger), ids_dir=str(ids_dir), **k))
    monkeypatch.setattr(us, "utc_now_naive", lambda: NOW)
    real_confirm = Path(reg.ROOT) / "docs" / "registry" / "ids" / "intl-elo-v2.confirm.txt"
    real_confirm_was = us.copy_sha256(real_confirm) if real_confirm.exists() else None   # committed tomorrow, or not
    real_ledger_sha = us.copy_sha256(Path(reg.ROOT) / "docs" / "registry" / "experiments.json")
    copy = _copy(tmp_path)
    before = us.copy_sha256(copy)
    with session_scope() as s:                                           # the app's store moves on after the copy
        m = s.get(Match, world["after3"])
        m.status, m.status_raw, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None, None
    try:
        out = _run(["--record", "--ruling", "ARCHITECT: test ruling", "--db", str(copy)])
        assert out.exit_code == 0, out.output
        assert "3/3 labelled" in out.output and "  RECORDED: " in out.output
        assert (ids_dir / "intl-elo-v2.confirm.txt").read_text() == "\n".join(str(i) for i in ids) + "\n"
        rec = json.loads(ledger.read_text())[0]
        assert rec["confirmation"]["ruling"] == "ARCHITECT: test ruling" and rec["confirmation"]["n_scored"] == 3
        assert rec["status"] == {"CONFIRMED": "production", "NOT_CONFIRMED": "closed"}[rec["confirmation"]["outcome"]]
        assert us.copy_sha256(copy) == before                            # the copy is never touched
        assert not any(copy.with_name(copy.name + x).exists() for x in us.COPY_SIDECARS)
        assert (us.copy_sha256(real_confirm) if real_confirm.exists() else None) == real_confirm_was  # never written
        assert us.copy_sha256(Path(reg.ROOT) / "docs" / "registry" / "experiments.json") == real_ledger_sha
        assert _run(["--record", "--ruling", "ARCHITECT: x"]).exit_code == 2   # the app's store: incomplete, refused
    finally:
        with session_scope() as s:
            m = s.get(Match, world["after3"])
            m.status, m.status_raw, m.home_score, m.away_score = MatchStatus.FINISHED, "FT", 0, 1


_REG_GET0, _REG_RECORD0 = reg.get, reg.record_confirmation     # the real functions, before any test patches them


def _registry_on_tmp(monkeypatch, tmp_path, ids, frozen=True):
    """The registry on tmp paths (the ledger and ids/): reg.get, IDS_DIR and record_confirmation point there."""
    reg_dir = tmp_path / "registry"
    ids_dir = reg_dir / "ids"
    ids_dir.mkdir(parents=True)
    e = dict(ENTRY)
    if frozen:
        (ids_dir / "intl-elo-v2.cohort.txt").write_text("\n".join(str(i) for i in ids) + "\n")
        e["confirmation_cohort"] = {"n": len(ids), "ids_sha256": reg._ids_sha(ids),
                                    "ids_file": "docs/registry/ids/intl-elo-v2.cohort.txt"}
    ledger = reg_dir / "experiments.json"
    ledger.write_text(json.dumps([e], indent=2) + "\n")
    get0, record0 = _REG_GET0, _REG_RECORD0
    monkeypatch.setattr(reg, "get", lambda eid, path=None: get0(eid, path=str(ledger)))
    monkeypatch.setattr(reg, "IDS_DIR", str(ids_dir))
    monkeypatch.setattr(reg, "record_confirmation",
                        lambda *a, **k: record0(*a, path=str(ledger), ids_dir=str(ids_dir), **k))
    monkeypatch.setattr(us, "utc_now_naive", lambda: NOW)
    return ledger, ids_dir


def test_346_record_on_a_copy_still_refuses_an_incomplete_read(world, monkeypatch, tmp_path):
    """346 item 1: "`--record` still refuses a provisional cohort or a pending fixture" — with --db too. Nothing is
    written to the registry and the copy is unchanged."""
    def attempt(sub, frozen, ids, want):
        ledger, ids_dir = _registry_on_tmp(monkeypatch, tmp_path / sub, ids, frozen=frozen)
        before_ledger = ledger.read_text()
        copy = _copy(tmp_path / sub)
        sha = us.copy_sha256(copy)
        out = _run(["--record", "--ruling", "ARCHITECT: x", "--db", str(copy)])
        assert out.exit_code == 2 and "REFUSED: the read is incomplete — " + want in out.output, out.output
        assert not (ids_dir / "intl-elo-v2.confirm.txt").exists() and ledger.read_text() == before_ledger
        assert us.copy_sha256(copy) == sha
    for sub in ("a", "b"):
        (tmp_path / sub).mkdir()
    attempt("a", False, [], "the cohort is not frozen")                         # provisional
    attempt("b", True, sorted([world["after1"], world["late"], world["after2"]]), "1 cohort fixture(s) lack a label")


def test_346_a_copy_replaced_during_the_read_is_refused_and_nothing_recorded(world, monkeypatch, tmp_path):
    """The printed sha256 is the read's: the copy is hashed again after the read, before --record writes anything; a
    copy replaced in between (here, swapped for another copy before the read's first query) is REFUSED."""
    import os
    ids = sorted([world["after1"], world["after2"], world["after3"]])
    ledger, ids_dir = _registry_on_tmp(monkeypatch, tmp_path, ids)
    before_ledger = ledger.read_text()
    copy = _copy(tmp_path)
    with session_scope() as s:                                           # a second copy with different bytes
        m = s.get(Match, world["far"])
        m.status_raw = "NS"
    try:
        other = _copy(tmp_path, "other.db")
    finally:
        with session_scope() as s:
            s.get(Match, world["far"]).status_raw = None
    read0 = us.confirmation_read

    def swapped(now=None, s=None):
        os.replace(other, copy)
        return read0(now=now, s=s)
    monkeypatch.setattr(us, "confirmation_read", swapped)
    out = _run(["--record", "--ruling", "ARCHITECT: x", "--db", str(copy)])
    assert out.exit_code == 2 and "changed during the read" in out.output and "nothing recorded" in out.output
    assert "RECORDED" not in out.output
    assert not (ids_dir / "intl-elo-v2.confirm.txt").exists() and ledger.read_text() == before_ledger


def test_346_a_copy_deleted_or_given_a_sidecar_during_the_read_is_refused_and_nothing_recorded(world, monkeypatch,
                                                                                                tmp_path):
    """Codex P2s on #938: a copy that disappears mid-run is a REFUSED line, never a traceback; a -wal, -shm or -journal
    that appears during the read (committed pages immutable=1 ignored, the main file's sha256 unchanged) is REFUSED."""
    ids = sorted([world["after1"], world["after2"], world["after3"]])
    ledger, ids_dir = _registry_on_tmp(monkeypatch, tmp_path, ids)
    before_ledger = ledger.read_text()
    read0 = us.confirmation_read
    for i, (act, why) in enumerate([("delete", "could not be re-read after the read"),
                                    ("-wal", "-wal appeared beside it"), ("-shm", "-shm appeared beside it"),
                                    ("-journal", "-journal appeared beside it")]):
        copy = _copy(tmp_path, f"c{i}.db")

        def during(now=None, s=None, copy=copy, act=act):
            r = read0(now=now, s=s)
            if act == "delete":
                copy.unlink()
            else:
                copy.with_name(copy.name + act).write_bytes(b"")
            return r
        monkeypatch.setattr(us, "confirmation_read", during)
        out = _run(["--record", "--ruling", "ARCHITECT: x", "--db", str(copy)])
        assert out.exit_code == 2 and why in out.output and "nothing recorded" in out.output, (act, out.output)
        assert out.exception is None or isinstance(out.exception, SystemExit), out.exception
        assert "RECORDED" not in out.output
        assert not (ids_dir / "intl-elo-v2.confirm.txt").exists() and ledger.read_text() == before_ledger
