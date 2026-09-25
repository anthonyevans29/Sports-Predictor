"""
Cup acceptance exam: the report-only pricing mode never writes, the default
path still does, and the frozen verdict logic scores as specified.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.db.database import get_engine, init_db, session_scope
from src.db.schema import (Base, Competition, Match, MatchStatus, ModelVersion,
                           Prediction, Sport, Team)
from src.walters import cup_exam
from src.walters.training import _generate_predictions_soccer

SEASON = "2026/27"


@pytest.fixture(scope="module")
def cup_db():
    """Tiny EFL-cup world in the throwaway test DB: 4 clubs across two
    leagues, 6 finished fixtures (one already carrying a Prediction row),
    1 scheduled, and a production soccer model."""
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="EFL", name="EFL Cup",
                           area="England", type="CUP")
        s.add(comp)
        teams = [Team(sport=Sport.SOCCER, name=n) for n in ("Arsenal", "Chelsea", "Wrexham", "Barnet")]
        s.add_all(teams)
        s.flush()
        a, c, w, b = (t.id for t in teams)
        t0 = datetime(2026, 8, 12, 19, 0)
        results = [(a, w, 3, 0), (c, b, 2, 1), (w, c, 1, 1), (b, a, 0, 2), (a, c, 1, 2), (w, b, 2, 0)]
        finished = []
        for i, (h, aw, hs, as_) in enumerate(results):
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                      stage="2nd Round", utc_date=t0 + timedelta(days=7 * i),
                      status=MatchStatus.FINISHED, home_team_id=h, away_team_id=aw,
                      home_score=hs, away_score=as_)
            s.add(m)
            finished.append(m)
        sched = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                      stage="3rd Round", utc_date=datetime(2026, 10, 28, 19, 45),
                      status=MatchStatus.SCHEDULED, home_team_id=c, away_team_id=w)
        s.add(sched)
        s.flush()
        s.add(Prediction(match_id=finished[0].id, model_version="v-test",
                         home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15))
        s.add(ModelVersion(
            sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v-test",
            status="production",
            parameters={
                "elo": {"league": {"ratings": {a: 1650, c: 1620, w: 1450, b: 1420}},
                        "cup": {"ratings": {a: 1600, c: 1600, w: 1500, b: 1480}}},
                "team_to_league": {a: "PL", c: "PL", w: "ELC", b: "EL2"},
                "contexts": {}, "poisson": {},
            },
        ))
        # Domestic league-seasons (cup fix 2026-09-25: cup strengths borrow
        # from these, as-of-date). Each league has a filler club; matches sit
        # both before and after the cup games so as-of cuts are exercised.
        leagues = {}
        for code, name in (("PL", "Premier League"), ("ELC", "Championship"), ("EL2", "League Two")):
            leagues[code] = Competition(sport=Sport.SOCCER, code=code, name=name,
                                        area="England", type="LEAGUE")
        s.add_all(leagues.values())
        fillers = {code: Team(sport=Sport.SOCCER, name=f"{code} Filler") for code in leagues}
        s.add_all(fillers.values())
        s.flush()
        members = {"PL": [a, c], "ELC": [w], "EL2": [b]}
        league_ids = []
        for code, tids in members.items():
            f = fillers[code].id
            for j, tid in enumerate(tids):
                for k, (day, hs, as_) in enumerate([(2, 2, 0), (9, 1, 1), (40, 3, 1)]):
                    home, away = (tid, f) if k % 2 == 0 else (f, tid)
                    lm = Match(sport=Sport.SOCCER, competition_id=leagues[code].id, season=SEASON,
                               utc_date=datetime(2026, 8, 1, 15) + timedelta(days=day + j),
                               status=MatchStatus.FINISHED, home_team_id=home, away_team_id=away,
                               home_score=hs + j, away_score=as_)
                    s.add(lm)
                    league_ids.append(lm)
        s.flush()
        ids = {"finished": [m.id for m in finished], "scheduled": sched.id,
               "league": [m.id for m in league_ids],
               "teams": {"Arsenal": a, "Chelsea": c, "Wrexham": w, "Barnet": b}}
    yield ids
    Base.metadata.drop_all(get_engine())


def _row_counts():
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


def test_report_only_mode_writes_nothing(cup_db):
    before = _row_counts()
    rows = _generate_predictions_soccer("EFL", SEASON, include_finished=True)
    after = _row_counts()
    assert after == before  # every table, Prediction included
    priced = {r["match_id"] for r in rows}
    assert set(cup_db["finished"]) <= priced  # FINISHED fixtures are priced
    # the pre-existing Prediction on a played game survives untouched
    with session_scope() as s:
        p = s.execute(select(Prediction).where(
            Prediction.match_id == cup_db["finished"][0])).scalar_one()
        assert (p.model_version, p.home_win_prob) == ("v-test", 0.6)


def test_default_path_still_writes(cup_db):
    """Regression twin: the production path is untouched and persists."""
    n = _generate_predictions_soccer("EFL", SEASON)
    assert n == 1  # SCHEDULED only
    with session_scope() as s:
        written = s.execute(select(Prediction).where(
            Prediction.match_id == cup_db["scheduled"])).scalars().all()
        assert len(written) == 1
        finished_preds = s.execute(select(func.count()).select_from(Prediction).where(
            Prediction.match_id.in_(cup_db["finished"]))).scalar_one()
        assert finished_preds == 1  # still only the seeded row


def test_report_mode_prices_identically_to_production(cup_db):
    """The exam must test what we ship: same numbers as the persisted path."""
    rows = {r["match_id"]: r for r in
            _generate_predictions_soccer("EFL", SEASON, include_finished=True)}
    with session_scope() as s:
        p = s.execute(select(Prediction).where(
            Prediction.match_id == cup_db["scheduled"])).scalar_one()
        r = rows[cup_db["scheduled"]]
        assert (r["p_home"], r["p_draw"], r["p_away"]) == \
            (p.home_win_prob, p.draw_prob, p.away_win_prob)


# --- frozen verdict logic (pure) ----------------------------------------------

def _key(mid, comp="EFL", stage="2nd Round", date="2026-09-16", fh=0.5, fd=0.25, fa=0.25):
    return {"match_id": mid, "comp": comp, "stage": stage, "date": date,
            "home": f"H{mid}", "away": f"A{mid}", "fair_home": fh, "fair_draw": fd, "fair_away": fa}


def _priced(ph, pd=0.25, pa=None):
    return {"p_home": ph, "p_draw": pd, "p_away": 1 - ph - pd if pa is None else pa}


def _world(n=10, delta=0.0, stages=("1st Round", "2nd Round")):
    key = [_key(i, stage=stages[i % len(stages)]) for i in range(n)]
    priced = {i: _priced(0.5 + delta) for i in range(n)}
    return key, priced, set(range(n))


def test_pass_when_close_to_market():
    r = cup_exam.score_exam(*_world(delta=0.02), min_scored=0)
    assert r.verdict == "PASS" and r.mae_home_pp == pytest.approx(2.0)
    assert r.sign_selector == "stage" and r.sign_share == 1.0


def test_mae_bar_is_inclusive_at_8pp():
    assert cup_exam.score_exam(*_world(delta=0.08)).mae_pass
    assert not cup_exam.score_exam(*_world(delta=0.081)).mae_pass


def test_over_count_bar_13():
    key = [_key(i) for i in range(55)]
    ok = {i: _priced(0.5 + (0.09 if i < 13 else 0.0)) for i in range(55)}
    bad = {i: _priced(0.5 + (0.09 if i < 14 else 0.0)) for i in range(55)}
    assert cup_exam.score_exam(key, ok, set(range(55))).n_over == 13
    assert cup_exam.score_exam(key, ok, set(range(55))).over_pass
    assert not cup_exam.score_exam(key, bad, set(range(55))).over_pass


def test_systematic_inversion_fails_regardless_of_mae():
    # market favors home slightly; model favors away slightly: small MAE, flipped sign
    key = [_key(i, fh=0.40, fd=0.25, fa=0.35) for i in range(10)]
    priced = {i: _priced(0.36, 0.25, 0.39) for i in range(10)}
    r = cup_exam.score_exam(key, priced, set(range(10)), min_scored=0)
    assert r.mae_pass and r.inversion
    assert r.verdict.startswith("FAIL — systematic sign inversion")
    assert all("SIGN" in row["flag"] for row in r.rows)


def test_sign_check_between_50_and_80_fails():
    key = [_key(i, fh=0.40, fd=0.25, fa=0.35) for i in range(10)]
    priced = {i: (_priced(0.42, 0.25, 0.33) if i < 7 else _priced(0.36, 0.25, 0.39)) for i in range(10)}
    r = cup_exam.score_exam(key, priced, set(range(10)), min_scored=0)
    assert r.sign_share == pytest.approx(0.7) and not r.inversion and not r.sign_pass
    assert r.verdict == "FAIL — sign check"


def test_date_fallback_when_stages_do_not_distinguish():
    key = [_key(0, stage="", date="2026-09-16"), _key(1, stage="", date="2026-08-12")]
    r = cup_exam.score_exam(key, {0: _priced(0.5), 1: _priced(0.5)}, {0, 1})
    assert r.sign_selector.startswith("date-fallback") and r.sign_n == 1


def test_unmatched_excluded_and_more_than_two_invalidates():
    key, priced, known = _world(n=10)
    two_gone = known - {0, 1}
    r = cup_exam.score_exam(key, priced, two_gone)
    assert r.n_scored == 8 and not r.invalid
    assert {m["why"] for m in r.missing} == {"UNMATCHED"}
    r = cup_exam.score_exam(key, priced, known - {0, 1, 2})
    assert r.invalid and r.verdict.startswith("INVALID")


def test_unpriced_counts_toward_missing():
    key, priced, known = _world(n=10)
    for i in (0, 1, 2):
        priced.pop(i)
    r = cup_exam.score_exam(key, priced, known)
    assert r.invalid and {m["why"] for m in r.missing} == {"UNPRICED"}


def test_non_efl_rows_do_not_enter_sign_check():
    key = [_key(0, comp="CL", stage="League Stage - 1"), _key(1)]
    r = cup_exam.score_exam(key, {0: _priced(0.5), 1: _priced(0.5)}, {0, 1})
    assert r.sign_n == 1


# --- cup-exam --detail (diagnostics only; architect spec 2026-09-25) ---------

def test_report_rows_carry_detail_inputs(cup_db):
    rows = _generate_predictions_soccer("EFL", SEASON, include_finished=True)
    r = rows[0]
    for k in cup_exam.DETAIL_KEYS:
        assert k in r, k
    assert r["default_elo"] == 1500.0
    assert r["home_in_pot"] and r["away_in_pot"]  # fixture teams all carry ratings


def test_unrated_team_is_market_only_ruling_b(cup_db):
    """Ruling B: a club with no trained Elo rating is never priced — its cup
    fixture comes back as a market-only row and nothing is written."""
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "EFL")).scalar_one()
        minnow = Team(sport=Sport.SOCCER, name="Sabah FC")
        s.add(minnow)
        s.flush()
        arsenal = cup_db["teams"]["Arsenal"]
        played = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                       stage="2nd Round", utc_date=datetime(2026, 9, 17, 19, 45),
                       status=MatchStatus.FINISHED, home_team_id=arsenal,
                       away_team_id=minnow.id, home_score=5, away_score=0)
        upcoming = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                         stage="3rd Round", utc_date=datetime(2026, 10, 29, 19, 45),
                         status=MatchStatus.SCHEDULED, home_team_id=minnow.id,
                         away_team_id=arsenal)
        s.add_all([played, upcoming])
        s.flush()
        pid, uid, tid = played.id, upcoming.id, minnow.id
    try:
        before = _row_counts()
        rows = {r["match_id"]: r for r in
                _generate_predictions_soccer("EFL", SEASON, include_finished=True)}
        assert _row_counts() == before
        assert rows[pid]["market_only"] == "away team unrated (no trained Elo)"
        assert "p_home" not in rows[pid]
        _generate_predictions_soccer("EFL", SEASON)          # live path
        with session_scope() as s:
            assert s.execute(select(func.count()).select_from(Prediction).where(
                Prediction.match_id == uid)).scalar_one() == 0
    finally:
        with session_scope() as s:
            for mid in (pid, uid):
                s.delete(s.get(Match, mid))
            s.delete(s.get(Team, tid))


def _drow(mid, delta, hl="PL", al="PL", hin=True, ain=True, hle=1600.0, ale=1550.0):
    return {"match_id": mid, "home": f"H{mid}", "away": f"A{mid}", "delta_pp": delta,
            "home_league": hl, "away_league": al, "home_in_pot": hin, "away_in_pot": ain,
            "home_league_elo": hle, "away_league_elo": ale, "default_elo": 1500.0}


def test_tier_of():
    assert cup_exam.tier_of(_drow(0, 0, "PL", "PL")) == "same-tier"
    assert cup_exam.tier_of(_drow(0, 0, "PL", "ELC")) == "cross-tier"
    assert cup_exam.tier_of(_drow(0, 0, "PL", None)) == "unmapped"


def test_detail_splits():
    res = cup_exam.ExamResult(rows=[
        _drow(0, -10.0),                                            # in-pot, same-tier
        _drow(1, 20.0, al="ELC"),                                   # in-pot, cross-tier
        _drow(2, 30.0, al=None, ain=False, ale=1500.0),             # out-of-pot, unmapped
        _drow(3, -40.0, hl=None, hin=False, hle=1500.0, al=None, ain=False, ale=1500.0),
    ])
    sp = cup_exam.detail_splits(res)
    assert sp["pot"]["in-pot"] == (2, pytest.approx(15.0))
    assert sp["pot"]["out-of-pot"] == (2, pytest.approx(35.0))
    assert sp["tier"] == {"cross-tier": (1, 20.0), "same-tier": (1, 10.0),
                          "unmapped": (2, pytest.approx(35.0))}
    assert sp["default_elo_teams"] == ["A2", "A3", "H3"]


def test_detail_flag_leaves_default_output_unchanged(cup_db, tmp_path):
    """--detail only appends; the plain exam output (and verdict) is identical."""
    from click.testing import CliRunner
    from cli import cli

    with session_scope() as s:
        ms = s.execute(select(Match).where(Match.id.in_(cup_db["finished"]))).scalars().all()
        lines = ["match_id,date,comp,stage,home,away,score,result,fair_home,fair_draw,fair_away,books"]
        for m in ms:
            lines.append(f"{m.id},{m.utc_date.date()},EFL,{m.stage},H,A,0-0,DRAW,0.45,0.27,0.28,5")
    key = tmp_path / "key.csv"
    key.write_text("\n".join(lines) + "\n")

    runner = CliRunner()
    before = _row_counts()
    plain = runner.invoke(cli, ["cup-exam", "--key", str(key)])
    det = runner.invoke(cli, ["cup-exam", "--key", str(key), "--detail"])
    assert plain.exit_code == 0 and det.exit_code == 0, (plain.output, det.output)
    assert _row_counts() == before
    assert "DETAIL" not in plain.output and "DETAIL SPLITS" in det.output
    # everything before the DETAIL block is identical, and so is the verdict
    head = det.output.split("\nDETAIL ")[0]
    assert plain.output.startswith(head)
    verdict = lambda out: [l for l in out.splitlines() if l.startswith("VERDICT")]
    assert verdict(plain.output) == verdict(det.output)


# --- strength-fit receipts (architect hypothesis check) --------------------------

def _set_score(mid, hs, as_):
    with session_scope() as s:
        m = s.get(Match, mid)
        m.home_score, m.away_score = hs, as_


def test_leave_self_out_a_fixture_cannot_move_its_own_price(cup_db):
    """Exam honesty: the priced match and every LATER match never enter any
    fit — rewriting their results leaves the price identical."""
    target = cup_db["finished"][3]                     # 4th cup game (day 21)
    later_cup = cup_db["finished"][4:]
    price = lambda: {r["match_id"]: (r["p_home"], r["p_draw"], r["p_away"])
                     for r in _generate_predictions_soccer("EFL", SEASON, include_finished=True)
                     if "p_home" in r}[target]
    with session_scope() as s:
        saved = {mid: (s.get(Match, mid).home_score, s.get(Match, mid).away_score)
                 for mid in [target, *later_cup, *cup_db["league"]]}
        target_date = s.get(Match, target).utc_date
        later_league = [mid for mid in cup_db["league"] if s.get(Match, mid).utc_date >= target_date]
    assert later_league                                # the fixture has later league games too
    p0 = price()
    try:
        for mid in [target, *later_cup, *later_league]:
            _set_score(mid, 9, 0)                      # rewrite own + future results
        assert price() == p0
        _set_score(cup_db["finished"][0], 0, 7)        # an EARLIER cup result does move it
        assert price() != p0
    finally:
        for mid, (hs, as_) in saved.items():
            _set_score(mid, hs, as_)
        _set_score(cup_db["finished"][0], 3, 0)


def test_cup_receipts_domestic_borrow_and_no_self_fit(cup_db):
    from src.models.cup_strengths import CUP_CONFIDENCE_K
    from src.models.poisson import CompetitionScoringContext, TeamStrength, estimate_strengths

    rows = {r["match_id"]: r for r in
            _generate_predictions_soccer("EFL", SEASON, include_finished=True)}
    first = rows[cup_db["finished"][0]]                # Arsenal v Wrexham, day 0
    assert first["self_in_fit"] is False
    assert first["fit_pool_n"] == 0 and first["strengths_backfilled"] is False
    assert (first["home_fit_n"], first["away_fit_n"]) == (0, 0)   # no cup games yet
    assert (first["home_dom_league"], first["away_dom_league"]) == ("PL", "ELC")
    assert first["home_cup_w"] == 0.0
    # cup n = 0 -> pure domestic: Arsenal's PL fit as of the fixture date
    with session_scope() as s:
        kick = s.get(Match, cup_db["finished"][0]).utc_date
        pl = [s.get(Match, mid) for mid in cup_db["league"]]
        pl = [m for m in pl if m.competition.code == "PL" and m.utc_date < kick]
        fit = estimate_strengths([{"home_team_id": m.home_team_id, "away_team_id": m.away_team_id,
                                   "home_score": m.home_score, "away_score": m.away_score}
                                  for m in pl], CompetitionScoringContext())
    ars = cup_db["teams"]["Arsenal"]
    assert first["home_dom_n"] == sum(ars in (m.home_team_id, m.away_team_id) for m in pl) == 2
    assert first["home_attack"] == round(fit[ars].attack, 3)
    assert first["home_defense"] == round(fit[ars].defense, 3)
    # later fixture: cup n > 0 -> confidence weight n/(n+5)
    later = rows[cup_db["finished"][4]]                # Arsenal v Chelsea, day 28
    assert later["home_fit_n"] == 2 and later["home_cup_w"] == round(2 / (2 + CUP_CONFIDENCE_K), 3)
    assert all(r.get("self_in_fit") is False for r in rows.values() if "p_home" in r)


def test_league_competitions_never_take_the_cup_branch(cup_db):
    """League pricing is untouched: PL strengths are still the whole
    competition-season pool fit (no as-of, no domestic borrow)."""
    from src.models.poisson import CompetitionScoringContext, estimate_strengths

    rows = _generate_predictions_soccer("PL", SEASON, include_finished=True)
    with session_scope() as s:
        pl = [s.get(Match, mid) for mid in cup_db["league"]]
        pl = [m for m in pl if m.competition.code == "PL"]
        fit = estimate_strengths([{"home_team_id": m.home_team_id, "away_team_id": m.away_team_id,
                                   "home_score": m.home_score, "away_score": m.away_score}
                                  for m in pl], CompetitionScoringContext())
        by_id = {m.id: m for m in pl}
    assert rows and all("home_dom_league" not in r for r in rows)
    for r in rows:
        m = by_id[r["match_id"]]
        assert r["home_attack"] == round(fit[m.home_team_id].attack, 3)
        assert r["away_defense"] == round(fit[m.away_team_id].defense, 3)


def test_fit_summary_buckets():
    res = cup_exam.ExamResult(rows=[
        {"comp": "EFL", "home": "A", "away": "B", "home_fit_n": 1, "away_fit_n": 2,
         "self_in_fit": True, "fit_pool_n": 36, "strengths_backfilled": False,
         "home_strengths_source": "matches", "away_strengths_source": "matches",
         "elo_goal_coeff": 0.0008},
        {"comp": "CL", "home": "C", "away": "D", "home_fit_n": 0, "away_fit_n": 7,
         "self_in_fit": False, "fit_pool_n": 500, "strengths_backfilled": True,
         "home_strengths_source": "promoted_default", "away_strengths_source": "matches",
         "elo_goal_coeff": 0.0008},
    ])
    fs = cup_exam.fit_summary(res)
    assert fs["team_fit_n_buckets"] == {"0": 1, "1": 1, "2": 1, "3-5": 0, "6+": 1}
    assert fs["self_in_fit"] == 1 and fs["backfilled_rows"] == 1
    assert fs["promoted_default_sides"] == 1
    assert fs["pools"] == [("CL", 500, True), ("EFL", 36, False)]
    assert fs["elo_goal_coeff"] == [0.0008]


def test_market_only_rows_are_reported_not_scored_not_invalid():
    key = [_key(i) for i in range(6)]
    priced = {i: _priced(0.5) for i in range(6)}
    for i in (0, 1, 2, 3):                      # four ruling-B exclusions
        priced[i] = {"market_only": "away team unrated (no trained Elo)"}
    r = cup_exam.score_exam(key, priced, set(range(6)))
    assert r.n_scored == 2 and not r.invalid and not r.missing
    assert len(r.market_only) == 4 and r.market_only[0]["why"].startswith("MARKET-ONLY (ruling B)")


# --- coverage floor (architect amendment 2026-09-25) --------------------------

def _n_world(n_scored, n_market_only):
    key = [_key(i) for i in range(n_scored + n_market_only)]
    priced = {i: _priced(0.52) for i in range(n_scored)}
    for i in range(n_scored, n_scored + n_market_only):
        priced[i] = {"market_only": "away team unrated (no trained Elo)"}
    return key, priced, set(range(len(key)))


def test_coverage_floor_45_is_inclusive():
    assert cup_exam.MIN_SCORED == 45
    r = cup_exam.score_exam(*_n_world(45, 10))           # 45 of 55 scored: exam valid
    assert not r.under_coverage and r.verdict == "PASS"
    r = cup_exam.score_exam(*_n_world(44, 11))           # ruling B ate one too many
    assert r.under_coverage and not r.invalid
    assert r.verdict.startswith("INVALID — insufficient coverage: 44 fixtures scored (< 45)")


def test_known_five_out_of_pot_rows_leave_the_exam_valid():
    r = cup_exam.score_exam(*_n_world(50, 5))
    assert r.n_scored == 50 and len(r.market_only) == 5 and not r.under_coverage


def test_drift_invalid_takes_precedence_over_coverage():
    key, priced, known = _n_world(40, 0)
    r = cup_exam.score_exam(key, priced, known - {0, 1, 2})   # 3 unmatched AND < 45
    assert r.invalid and r.under_coverage
    assert r.verdict.startswith("INVALID — 3 key rows unmatched/unpriced")
