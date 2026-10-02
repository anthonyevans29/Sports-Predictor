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


def test_only_cancelled_cohort_fixtures_are_released_next_after_the_cohort(world, monkeypatch, tmp_path):
    """ARCHITECT 2026-10-02 (2): a CANCELLED (CANC) or ABANDONED (ABD) cohort
    fixture is released and replaced by the next eligible fixture AFTER the
    cohort; a postponed or scheduled one stays."""
    ids = [world["after1"], world["late"], world["after2"]]
    (tmp_path / "intl-elo-v2.cohort.txt").write_text("\n".join(str(i) for i in sorted(ids)) + "\n")
    e = {**ENTRY, "confirmation_cohort": {"n": 3, "ids_sha256": reg._ids_sha(ids),
                                          "ids_file": "docs/registry/ids/intl-elo-v2.cohort.txt"}}
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path))

    def set_status(mid, status, raw):
        with session_scope() as s:
            m = s.get(Match, mid)
            m.status, m.status_raw = status, raw
    try:
        set_status(world["late"], MatchStatus.POSTPONED, "PST")                # postponed: stays
        with session_scope() as s:
            assert us.substitutions_due(e, s) == []
            s.rollback()
        set_status(world["after2"], MatchStatus.CANCELLED, "ABD")              # abandoned: released
        with session_scope() as s:
            due = us.substitutions_due(e, s)
            s.rollback()
        assert [(d["released"]["id"], d["replacement"]["id"], d["reason"]) for d in due] == \
            [(world["after2"], world["after3"], "abandoned")]                     # after3 = the 4th eligible (friendly out)
        # once recorded, the next cancellation takes the NEXT one (after4), never after3 again
        e["confirmation_cohort"]["substitutions"] = [{"released": world["after2"], "replacement": world["after3"]}]
        set_status(world["after1"], MatchStatus.CANCELLED, "CANC")
        with session_scope() as s:
            due = us.substitutions_due(e, s)
            s.rollback()
        assert [(d["released"]["id"], d["replacement"]["id"], d["reason"]) for d in due] == \
            [(world["after1"], world["after4"], "cancelled")]
    finally:
        set_status(world["late"], MatchStatus.SCHEDULED, None)
        set_status(world["after2"], MatchStatus.FINISHED, "FT")
        set_status(world["after1"], MatchStatus.FINISHED, "FT")


def test_intl_daily_chain_and_cli_refusal(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import chains
    steps = chains.CHAINS["intl-daily"]["steps"]
    assert [s[0] for s in steps] == ["intl-sync", "intl-venue-sync", "export-unl-predictions"]
    assert steps[0][1:3] == ["--since", "{today}"] and "export-unl-predictions" in chains.UNMETERED
    from click.testing import CliRunner
    from cli import cli
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    out = CliRunner().invoke(cli, ["export-unl-predictions"])
    assert out.exit_code == 2 and "REFUSED" in out.output
