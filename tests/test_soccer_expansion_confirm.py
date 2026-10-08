"""soccer-expansion-confirm (ARCHITECT 2026-10-08, addendum 11, item 4: "By Tuesday: soccer-expansion-confirm (freeze,
substitute, progress, record) on the intl-elo-confirm pattern."). Pins, on synthetic leagues in the throwaway test DB
and a TMP registry (the real docs/registry/ is never written): refused before a run + PASS verdict with a surviving
set; the freeze takes the first 60 eligible fixtures by (kickoff, id) from the surviving leagues only, regular season
only, after the verdict, never a test-set id, and calls the cross-ref guard first (a refusal writes nothing); only
unscoreable cohort fixtures are substituted, a FT row still waiting for its score stays pending; progress prints the
pooled and per-league lines; the outcome is computed by registry.record_confirmation per the plan (bar inclusive,
the reference strict: ties fail)."""
import json
import math
import random
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.walters import registry as reg
from src.walters import soccer_expansion as sx

SEASON = "2150/51"
START = datetime(2150, 8, 1)
VERDICT_AT = START + timedelta(days=50)
NAIVES = {"PD": {"H": 0.46, "D": 0.26, "A": 0.28, "n": 380}, "BL1": {"H": 0.43, "D": 0.24, "A": 0.33, "n": 306}}
PLAN = {"n_games": 60, "metric": "log_loss", "bar": 1.0986, "must_beat_reference": True,
        "reference": "pooled naive (each surviving league's frozen 2023/24 H/D/A frequencies) on the same 60 games, "
                     "minus 0.010"}


def _comp(s, code):
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.SOCCER, code=code, name=code, area="x", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


@pytest.fixture(scope="module")
def world():
    """PD and BL1 (surviving) + SA (not surviving), season 2150/51. Per surviving league: 45 finished regular rows
    before the verdict (the walk's min_prior is met), then 35 FINISHED regular rows after it, PD and BL1 sharing each
    kickoff (so (kickoff, id) ordering is exercised). Distractors after the verdict: a PD play-off row, an SA regular
    row, a PD stale orphan, a PD row whose id is in the scored test set."""
    init_db()
    rng = random.Random(11)
    out = {"eligible": [], "distractors": {}}
    with session_scope() as s:
        pre_existing = set(s.execute(select(Competition.code).where(
            Competition.code.in_(("PD", "BL1", "SA")))).scalars())
        teams = {}
        for code in ("PD", "BL1", "SA"):
            c = _comp(s, code)
            t = [Team(sport=Sport.SOCCER, name=f"SXC {code} {i}") for i in range(6)]
            s.add_all(t)
            s.flush()
            teams[code] = (c, t)

        def add(code, when, stage, status=MatchStatus.FINISHED, raw="FT", score=True):
            c, t = teams[code]
            h, a = rng.sample(range(6), 2)
            m = Match(sport=Sport.SOCCER, competition_id=c.id, season=SEASON, utc_date=when, status=status,
                      status_raw=raw, home_team_id=t[h].id, away_team_id=t[a].id,
                      home_score=rng.randint(0, 3) if score else None, away_score=rng.randint(0, 3) if score else None,
                      stage=stage)
            s.add(m)
            s.flush()
            return m
        for code in ("PD", "BL1"):
            for k in range(45):
                add(code, START + timedelta(days=k), f"Regular Season - {k + 1}")
        for k in range(35):
            for code in ("PD", "BL1"):
                m = add(code, VERDICT_AT + timedelta(days=1 + k, hours=15), f"Regular Season - {46 + k}")
                out["eligible"].append((m.utc_date, m.id))
        early = VERDICT_AT + timedelta(hours=3)
        out["distractors"]["playoff"] = add("PD", early, "Relegation Play-offs - Final").id
        out["distractors"]["sa"] = add("SA", early, "Regular Season - 1").id
        out["distractors"]["orphan"] = add("PD", early, "Regular Season - 2", status=MatchStatus.STALE_ORPHAN,
                                           raw=None, score=False).id
        out["distractors"]["test_set"] = add("PD", early, "Regular Season - 3").id
        out["distractors"]["before"] = add("PD", VERDICT_AT - timedelta(hours=1), "Regular Season - 4").id
    out["eligible"].sort()
    out["ids"] = [i for _, i in out["eligible"]]
    yield out
    # teardown (throwaway test DB only): this module's rows, teams and the competitions it created leave no trace for
    # later modules (test_soccer_expansion's shadow test counts which leagues are stored)
    from sqlalchemy import delete
    with session_scope() as s:
        s.execute(delete(Match).where(Match.season == SEASON))
        s.execute(delete(Team).where(Team.name.like("SXC %")))
        s.execute(delete(Competition).where(Competition.code.in_(("PD", "BL1", "SA")),
                                            Competition.code.notin_(pre_existing)))


def _entry(**over):
    e = {"id": sx.EID, "sport": "soccer", "test_set": "x", "confirmation_window": "w", "confirmation_plan": PLAN,
         "status": "confirming",
         "run": {"run_at": "2150-09-01T00:00:00Z", "ids_file": f"docs/registry/ids/{sx.EID}.txt",
                 "result": {"verdict": "PASS — surviving set PD, BL1", "surviving": ["PD", "BL1"],
                            "per_league": {c: {"naive_freq": NAIVES[c]} for c in NAIVES},
                            "production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}},
         "verdict": {"verdict": "PASS", "ruling": "ARCHITECT: pass", "at": VERDICT_AT.strftime("%Y-%m-%dT%H:%M:%SZ")}}
    e.update(over)
    return e


@pytest.fixture
def ledger(world, monkeypatch, tmp_path):
    """A TMP registry holding the entry; reg.LEDGER / reg.IDS_DIR / reg.get point at it."""
    led, ids = tmp_path / "experiments.json", tmp_path / "ids"
    ids.mkdir()
    (ids / f"{sx.EID}.txt").write_text(f"{world['distractors']['test_set']}\n")
    real_get = reg.get
    monkeypatch.setattr(reg, "LEDGER", str(led))
    monkeypatch.setattr(reg, "IDS_DIR", str(ids))
    monkeypatch.setattr(reg, "get", lambda eid, path=None: real_get(eid, str(led)))

    def put(entry):
        led.write_text(json.dumps([entry]))
    put(_entry())
    return {"led": led, "ids": ids, "put": put, "load": lambda: json.loads(led.read_text())[0]}


def _cli(*args):
    import cli
    return CliRunner().invoke(cli.cli, ["soccer-expansion-confirm", *args])


def _set(mid, status, raw, hs=None, as_=None, hs90=None, as90=None):
    with session_scope() as s:
        m = s.get(Match, mid)
        old = (m.status, m.status_raw, m.home_score, m.away_score, m.home_score_90, m.away_score_90)
        m.status, m.status_raw, m.home_score, m.away_score = status, raw, hs, as_
        m.home_score_90, m.away_score_90 = hs90, as90
    return old


def _restore(mid, old):
    with session_scope() as s:
        m = s.get(Match, mid)
        m.status, m.status_raw, m.home_score, m.away_score, m.home_score_90, m.away_score_90 = old


# ------------------------------------------------------------------ refusals --

@pytest.mark.parametrize("entry,why", [
    ({"run": None, "status": "declared", "verdict": None}, "no run record"),
    ({"verdict": None, "status": "run"}, "no PASS verdict"),
    ({"verdict": {"verdict": "FAIL", "ruling": "x", "at": "2150-09-20T00:00:00Z"}, "status": "closed"},
     "no PASS verdict"),
])
def test_refused_before_a_pass_verdict(ledger, entry, why):
    ledger["put"](_entry(**entry))
    for args in ((), ("--freeze-cohort",), ("--substitute",), ("--record", "--ruling", "x")):
        r = _cli(*args)
        assert r.exit_code == 2 and "REFUSED" in r.output and why in r.output, (args, r.output)
    assert not (ledger["ids"] / f"{sx.EID}.cohort.txt").exists()


def test_refused_when_the_run_names_no_surviving_league(ledger):
    e = _entry()
    e["run"]["result"].update(verdict="FAIL — no league survives", surviving=[])
    ledger["put"](e)
    r = _cli("--freeze-cohort")
    assert r.exit_code == 2 and "names no surviving league" in r.output


def test_the_real_registry_entry_is_declared_with_the_plan_this_command_executes():
    e = reg.load()
    e = next(x for x in e if x["id"] == sx.EID)
    assert e["confirmation_plan"] == PLAN
    assert e["confirmation_window"].startswith("the first 60 league games of the surviving set kicking off after the "
                                               "verdict, pooled, cohort frozen by fixture id")


# --------------------------------------------------------------------- freeze --

def test_freeze_takes_the_first_60_eligible_by_kickoff_then_id(ledger, world, monkeypatch):
    seen = {}
    real = reg.freeze_confirmation_cohort

    def spy(eid, ids, basis, **kw):
        seen.update(kw)
        return real(eid, ids, basis, **kw)
    monkeypatch.setattr(reg, "freeze_confirmation_cohort", spy)
    r = _cli("--freeze-cohort", "--no-fetch")
    monkeypatch.setattr(reg, "freeze_confirmation_cohort", real)
    assert r.exit_code == 0, r.output
    assert "FROZEN: 60 fixtures" in r.output and "cross-ref guard: test stub" in r.output
    assert seen["no_fetch"] is True and seen["path"] == str(ledger["led"]) and seen["ids_dir"] == str(ledger["ids"])
    want = sorted(world["ids"][:60])
    got = [int(x) for x in (ledger["ids"] / f"{sx.EID}.cohort.txt").read_text().split()]
    assert got == want
    assert not set(world["distractors"].values()) & set(got)        # play-off, SA, orphan, test set, pre-verdict
    c = ledger["load"]()["confirmation_cohort"]
    assert c["n"] == 60 and c["ids_sha256"] == reg._ids_sha(want)
    assert c["basis"]["by_code"] == {"PD": 30, "BL1": 30} and c["basis"]["surviving"] == ["PD", "BL1"]
    assert c["basis"]["eligible_stored"] == 70 and c["basis"]["rule"] == sx.CONFIRM_RULE
    r = _cli("--freeze-cohort")
    assert r.exit_code == 2 and "already frozen" in r.output


def test_freeze_calls_the_guard_and_a_refusal_writes_nothing(ledger, monkeypatch):
    before = ledger["led"].read_text()

    def refuse(eid, no_fetch=False, repo=None):
        raise reg.CrossRefRefused(f"{eid}: a cohort on ref remotes/origin/laptop/x at commit deadbeef")
    monkeypatch.setattr(reg, "cross_ref_guard", refuse)
    r = _cli("--freeze-cohort")
    assert r.exit_code == 2 and "laptop/x at commit deadbeef" in r.output
    assert ledger["led"].read_text() == before and not (ledger["ids"] / f"{sx.EID}.cohort.txt").exists()


def test_freeze_refuses_short_schedules_and_unplaced_labels(ledger, world, monkeypatch):
    e = _entry()
    e["verdict"]["at"] = (VERDICT_AT + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")     # only ~30 left
    ledger["put"](e)
    r = _cli("--freeze-cohort")
    assert r.exit_code == 2 and "< 60" in r.output and "sync-matches for PD, BL1" in r.output
    ledger["put"](_entry())
    with session_scope() as s:
        m = s.get(Match, world["ids"][10])
        old, m.stage = m.stage, "Matchday Special"
    try:
        r = _cli("--freeze-cohort")
        assert r.exit_code == 2 and "cannot place" in r.output and "Matchday Special" in r.output
        assert not (ledger["ids"] / f"{sx.EID}.cohort.txt").exists()
    finally:
        with session_scope() as s:
            s.get(Match, world["ids"][10]).stage = old


# ----------------------------------------------------------------- substitute --

def _freeze(ledger):
    r = _cli("--freeze-cohort", "--no-fetch")
    assert r.exit_code == 0, r.output


def test_only_unscoreable_fixtures_are_substituted_next_after_the_cohort(ledger, world):
    _freeze(ledger)
    ids = world["ids"]
    canc, awd, pst, lag, aet90 = ids[3], ids[7], ids[11], ids[15], ids[19]
    olds = {canc: _set(canc, MatchStatus.CANCELLED, "CANC"),
            awd: _set(awd, MatchStatus.FINISHED, "AWD", 3, 0),                 # awarded, no 90' score: unscoreable
            pst: _set(pst, MatchStatus.POSTPONED, "PST"),                       # postponed: stays
            lag: _set(lag, MatchStatus.FINISHED, "FT"),                         # FT, score not in yet: stays pending
            aet90: _set(aet90, MatchStatus.FINISHED, "AET", 2, 1, 1, 1)}        # AET with a 90' score: scoreable
    try:
        r = _cli()
        assert "pending 4" in r.output and "2 unscoreable: run --substitute" in r.output, r.output
        r = _cli("--substitute")
        assert r.exit_code == 0, r.output
        subs = ledger["load"]()["confirmation_cohort"]["substitutions"]
        assert [(x["released"], x["replacement"], x["reason"]) for x in subs] == [
            (canc, ids[60], "CANC"), (awd, ids[61], "AWD")]
        assert subs[0]["evidence"]["status"] == "cancelled" and subs[1]["evidence"]["status_raw"] == "AWD"
        r = _cli("--substitute")
        assert "nothing released" in r.output
        eff = reg.frozen_cohort(ledger["load"](), str(ledger["ids"]))
        assert pst in eff and lag in eff and aet90 in eff and canc not in eff and ids[61] in eff
        rd = sx.confirmation_read()
        pend = {p["id"]: p["status"] for p in rd["pending"]}
        assert pend == {pst: "postponed", lag: "finished"} and rd["release_due"] == 0 and not rd["complete"]
    finally:
        for mid, old in olds.items():
            _restore(mid, old)


# ------------------------------------------------------------ progress / read --

def _manual(world, cohort_ids):
    """The gate's walk re-run by hand on the two league-seasons, scored on the cohort with the record's naives."""
    from src.walters.soccer_backtest import run_soccer_backtest
    key = {"H": "p_home", "D": "p_draw", "A": "p_away"}
    with session_scope() as s:
        code_of = {m.id: m.competition.code for m in s.execute(select(Match).where(Match.id.in_(cohort_ids))).scalars()}
    per, tot = {}, [0.0, 0.0, 0]
    for code in ("PD", "BL1"):
        for r in run_soccer_backtest(code, SEASON, 40, dixon_coles_rho=-0.1, elo_goal_coeff=0.0008,
                                     stage_filter=sx.is_regular, batch_same_kickoff=True):
            if r["match_id"] in cohort_ids:
                m, n = -math.log(r[key[r["actual"]]]), -math.log(NAIVES[code_of[r["match_id"]]][r["actual"]])
                d = per.setdefault(code, [0.0, 0.0, 0])
                d[0], d[1], d[2] = d[0] + m, d[1] + n, d[2] + 1
                tot[0], tot[1], tot[2] = tot[0] + m, tot[1] + n, tot[2] + 1
    return per, tot


def test_progress_reads_the_cohort_with_the_gates_walk_pooled_and_per_league(ledger, world, monkeypatch):
    r = _cli()
    assert r.exit_code == 0 and "cohort PROVISIONAL (60/60 fixtures; 70 eligible stored)" in r.output
    _freeze(ledger)
    calls = []
    import src.walters.soccer_backtest as sb
    real = sb.run_soccer_backtest
    monkeypatch.setattr(sb, "run_soccer_backtest", lambda *a, **k: calls.append((a, k)) or real(*a, **k))
    rd = sx.confirmation_read()
    assert rd["n"] == 60 and rd["complete"] and rd["cohort_state"] == "frozen"
    assert all(k["stage_filter"] is sx.is_regular and k["batch_same_kickoff"] is True and k["dixon_coles_rho"] == -0.1
               and k["elo_goal_coeff"] == 0.0008 and a[2] == sx.MIN_PRIOR for a, k in calls)
    assert sorted(a[:2] for a, _ in calls) == [("BL1", SEASON), ("PD", SEASON)]
    per, tot = _manual(world, set(world["ids"][:60]))
    assert tot[2] == 60
    assert rd["log_loss"] == pytest.approx(tot[0] / 60) and rd["naive_log_loss"] == pytest.approx(tot[1] / 60)
    assert rd["reference_log_loss"] == pytest.approx(tot[1] / 60 - 0.010)
    for code in ("PD", "BL1"):
        d = rd["per_league"][code]
        assert d["n"] == per[code][2] == 30 and d["ll_model"] == pytest.approx(per[code][0] / 30)
        assert d["ll_naive"] == pytest.approx(per[code][1] / 30)
    assert rd["naive_source"] == {"PD": sx.NAIVE_FROM_RECORD, "BL1": sx.NAIVE_FROM_RECORD}
    assert rd["first_game_at"] == world["eligible"][0][0].strftime("%Y-%m-%dT%H:%M:%SZ")
    out = _cli().output
    assert "cohort FROZEN (60/60" in out and "60/60 labelled" in out and "so far (pooled)" in out
    assert "PD: n 30" in out and "BL1: n 30" in out and "reported, not gated" in out
    assert f"naive PD: H 0.4600 / D 0.2600 / A 0.2800 · source {sx.NAIVE_FROM_RECORD}" in out


def test_naive_is_recomputed_with_naive_for_only_when_the_record_lacks_it(ledger, monkeypatch):
    e = _entry()
    del e["run"]["result"]["per_league"]["BL1"]["naive_freq"]
    ledger["put"](e)
    monkeypatch.setattr(sx, "naive_for", lambda s, c: {"H": 0.5, "D": 0.25, "A": 0.25, "n": 9})
    rd = sx.confirmation_read()
    assert rd["naive_source"] == {"PD": sx.NAIVE_FROM_RECORD, "BL1": sx.NAIVE_RECOMPUTED}
    assert rd["naive"]["BL1"] == {"H": 0.5, "D": 0.25, "A": 0.25}
    monkeypatch.setattr(sx, "naive_for", lambda s, c: None)
    with pytest.raises(sx.ExpansionRefused, match="naive undefined"):
        sx.confirmation_read()


def test_a_pending_cohort_fixture_leaves_the_read_incomplete_and_record_refuses(ledger, world):
    r = _cli("--record", "--ruling", "ARCHITECT: x")
    assert r.exit_code == 2 and "the cohort is not frozen" in r.output
    _freeze(ledger)
    mid = world["ids"][5]
    old = _set(mid, MatchStatus.SCHEDULED, "NS")
    try:
        rd = sx.confirmation_read()
        assert rd["n"] == 59 and not rd["complete"] and rd["pending"] == [{"id": mid, "status": "scheduled"}]
        assert world["ids"][60] not in rd["scored_ids"]                    # game 61 is never admitted
        r = _cli("--record", "--ruling", "ARCHITECT: x")
        assert r.exit_code == 2 and "1 cohort fixture(s) lack a label" in r.output
        assert "confirmation" not in ledger["load"]()
    finally:
        _restore(mid, old)
    r = _cli("--record")
    assert r.exit_code == 2 and "needs --ruling" in r.output


# --------------------------------------------------------------------- record --

@pytest.mark.parametrize("ll,ref,outcome", [
    (1.0500, 1.0600, "CONFIRMED"),
    (1.0986, 1.1100, "CONFIRMED"),                  # the bar is inclusive (<= ln 3, registry plan bar 1.0986)
    (1.0987, 1.1100, "NOT_CONFIRMED"),              # above the bar
    (1.0500, 1.0500, "NOT_CONFIRMED"),              # a tie with the reference fails (strict <)
    (1.0600, 1.0500, "NOT_CONFIRMED"),              # worse than the reference
])
def test_record_computes_the_outcome_per_the_plan(ledger, world, monkeypatch, ll, ref, outcome):
    _freeze(ledger)
    rd = sx.confirmation_read()
    rd.update(log_loss=ll, reference_log_loss=ref, naive_log_loss=ref + 0.010)
    monkeypatch.setattr(sx, "confirmation_read", lambda: rd)
    r = _cli("--record", "--ruling", "ARCHITECT 2150: record it")
    assert r.exit_code == 0 and f"RECORDED: {outcome}" in r.output, r.output
    e = ledger["load"]()
    c = e["confirmation"]
    assert c["outcome"] == outcome and c["n_scored"] == 60 and c["ruling"] == "ARCHITECT 2150: record it"
    assert e["status"] == ("production" if outcome == "CONFIRMED" else "closed")
    assert set(c["result"]["per_league"]) == {"PD", "BL1"} and c["result"]["naive_source"]["PD"] == sx.NAIVE_FROM_RECORD
    assert c["result"]["params"] == {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}
    assert (ledger["ids"] / f"{sx.EID}.confirm.txt").exists()


# ------------------------------------------------- AET / PEN: the 90' score (Codex P1 on #373) --

def test_an_aet_cohort_fixture_is_scored_and_walked_on_its_90_minute_score(ledger, world):
    """A cohort fixture drawn 1-1 at 90' and won 2-1 after extra time is scored as a DRAW, and every later prediction
    equals a hand replay with the row stored as a 1-1 FT: the extra-time goals never touch Elo or the strengths. The
    gate's default walk is unchanged (it still reads the after-extra-time score)."""
    from src.walters.soccer_backtest import run_soccer_backtest
    _freeze(ledger)
    mid = world["ids"][4]
    with session_scope() as s:
        code = s.get(Match, mid).competition.code
    old = _set(mid, MatchStatus.FINISHED, "AET", 2, 1, 1, 1)
    try:
        aet = sx.confirmation_read()
        _set(mid, MatchStatus.FINISHED, "FT", 1, 1)               # the hand replay: the row as a 1-1 FT
        ft = sx.confirmation_read()
        assert aet["n"] == 60 and ft["scored_ids"] == aet["scored_ids"] and mid in aet["scored_ids"]
        assert aet["log_loss"] == ft["log_loss"] and aet["naive_log_loss"] == ft["naive_log_loss"]
        assert aet["per_league"] == ft["per_league"]
        _set(mid, MatchStatus.FINISHED, "AET", 2, 1, 1, 1)
        out = _cli().output
        assert "extra-time" in out and f"{mid}" in out and "AET" in out, out
        kw = dict(dixon_coles_rho=-0.1, elo_goal_coeff=0.0008, stage_filter=sx.is_regular, batch_same_kickoff=True)
        default = {r["match_id"]: r for r in run_soccer_backtest(code, SEASON, 40, **kw)}
        assert default[mid]["actual"] == "H"                      # default off: the gate's walk is unchanged
        opt = {r["match_id"]: r for r in run_soccer_backtest(code, SEASON, 40, confirmation_scoring=True, **kw)}
        assert opt[mid]["actual"] == "D"
    finally:
        _restore(mid, old)


def test_a_released_awd_fixture_is_neither_scored_nor_walked(ledger, world):
    """Codex P1 (round 2) on #373: an AWD row with provider goals and no 90' score is released by the substitution
    rule; the read's walk must not let it update Elo or the prior either. Every later cohort prediction equals a hand
    replay without the row (the same fixture as CANC: never walked). One predicate serves both (sx.unscoreable). The
    gate's default walk still reads it (unchanged)."""
    from src.walters.soccer_backtest import run_soccer_backtest
    _freeze(ledger)
    mid = world["ids"][8]
    with session_scope() as s:
        code = s.get(Match, mid).competition.code
    old = _set(mid, MatchStatus.FINISHED, "AWD", 3, 0)
    try:
        r = _cli("--substitute")
        assert r.exit_code == 0 and f"SUBSTITUTED: {mid} (AWD" in r.output, r.output
        awd = sx.confirmation_read()
        assert awd["n"] == 60 and awd["complete"] and mid not in awd["scored_ids"]
        assert world["ids"][60] in awd["scored_ids"]
        _set(mid, MatchStatus.CANCELLED, "CANC")                  # the hand replay: the row never walked
        gone = sx.confirmation_read()
        assert gone["scored_ids"] == awd["scored_ids"]
        assert awd["log_loss"] == gone["log_loss"] and awd["per_league"] == gone["per_league"]
        _set(mid, MatchStatus.FINISHED, "AWD", 3, 0)
        out = _cli().output
        assert "DATA NOTE" in out and f"{mid} AWD" in out, out
        kw = dict(dixon_coles_rho=-0.1, elo_goal_coeff=0.0008, stage_filter=sx.is_regular, batch_same_kickoff=True)
        assert mid in {x["match_id"] for x in run_soccer_backtest(code, SEASON, 40, **kw)}          # default: unchanged
        assert mid not in {x["match_id"] for x in run_soccer_backtest(code, SEASON, 40, confirmation_scoring=True,
                                                                      **kw)}
    finally:
        _restore(mid, old)
