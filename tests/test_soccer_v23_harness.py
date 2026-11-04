"""soccer-v23's harness (src/walters/soccer_v23.py) on SYNTHETIC stores only (ARCHITECT 2026-11-04, addendum 248 item
2(b); addendum 230 item 1(d); addendum 216 items 1-4; addendum 243 item 4). Every database here is a throwaway SQLite
file under pytest's tmp_path; nothing reads data/ or a real database, and no run of v23 touches real data.

Pinned: the one prediction function's two builders give the same snapshot (sha included); the admission predicate;
the walk and live call the one builder at every instant (the memo answers bitwise what no memo computes); the ladder is elo.train's; the v22 arm equals the REAL
training._generate_predictions_soccer at the same instant (1e-12, both the >= 30 path and the backfill path, on stores
without an AET / PEN league row; with one, the documented 90-minute difference is pinned); a game still in play at the
instant (inside RESULT_LAG) enters neither path; v23 is
smooth across the league's 30th match where v22 steps; the availability term's inputs and classes (243 item 4) and the
receipt's verbatim categories; no number outside the design's own literals; the gate's refusals in order, the
reservation before any outcome, the record; the verdict at 0, 0.0049999 and 0.0050."""
from __future__ import annotations

import importlib.util
import io
import json
import math
import random
import sqlite3
import tokenize
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.walters import soccer_v23 as v

ROOT = Path(__file__).resolve().parent.parent
V22P = {"dixon_coles_rho": -0.10, "elo_goal_coeff": 0.0008}
PJ = v.canon_params(V22P, False)


# ------------------------------------------------------------------------------------------ the store --

def fresh(path, monkeypatch):
    """Bind src.db.database to a fresh SQLite file at `path` (tmp_path only) and create the tables."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return db


SEASONS = ("2023/24", "2024/25", "2025/26")


def build(db, seasons=SEASONS, n_teams=8, cur_rows=None, seed=248, extras=True, tied: int = 0) -> dict:
    """Two LEAGUE competitions (PL, ELC; two clubs move between them), a CUP (FAC), one round robin per season.
    `cur_rows`: how many rows of the LAST season are stored FINISHED (the rest SCHEDULED). Extras: an AWD row, an AET
    row with a 90-minute score, a cancelled row, a cup row. `tied`: when > 0, that many rows of a competition share
    each kickoff (a round played at one instant). Returns ids."""
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    rng = random.Random(seed)
    out = {"PL": [], "ELC": [], "scheduled": [], "teams": {}}
    with db.session_scope() as s:
        comps = {c: Competition(sport=Sport.SOCCER, code=c, name=c, area="England", type=t)
                 for c, t in (("PL", "LEAGUE"), ("ELC", "LEAGUE"), ("FAC", "CUP"))}
        teams = [Team(sport=Sport.SOCCER, name=f"T{i}") for i in range(2 * n_teams)]
        s.add_all([*comps.values(), *teams])
        s.flush()
        ids = [t.id for t in teams]
        strength = {t: rng.gauss(0, 0.3) for t in ids}
        for si, season in enumerate(seasons):
            members = {"PL": ids[:n_teams], "ELC": ids[n_teams:]}
            if si >= 1:                                   # one club up, one down
                members = {"PL": ids[1:n_teams] + [ids[n_teams]], "ELC": [ids[0]] + ids[n_teams + 1:]}
            for code in ("PL", "ELC"):
                pairs = [(h, a) for h in members[code] for a in members[code] if h != a]
                rng.shuffle(pairs)
                t0 = datetime(int(season[:4]), 8, 10, 12) + (timedelta(hours=3) if code == "ELC" else timedelta())
                for j, (h, a) in enumerate(pairs):
                    at = (t0 + timedelta(days=(j // tied) * 3) if tied else
                          t0 + timedelta(days=(j // 4) * 3, hours=j % 4))
                    last = si == len(seasons) - 1
                    finished = not last or cur_rows is None or j < cur_rows
                    lh = 1.5 * pow(2.718281828, strength[h] - strength[a] + 0.15)
                    la = 1.2 * pow(2.718281828, strength[a] - strength[h])
                    hs = min(6, int(rng.expovariate(1 / lh)))
                    as_ = min(6, int(rng.expovariate(1 / la)))
                    m = Match(sport=Sport.SOCCER, competition_id=comps[code].id, season=season, utc_date=at,
                              stage=f"Regular Season - {j // 4 + 1}", home_team_id=h, away_team_id=a,
                              status=MatchStatus.FINISHED if finished else MatchStatus.SCHEDULED,
                              status_raw="FT" if finished else "NS",
                              home_score=hs if finished else None, away_score=as_ if finished else None,
                              external_ids={"api_football": str(900000 + len(out["PL"]) + len(out["ELC"]))})
                    s.add(m)
                    s.flush()
                    (out[code] if finished else out["scheduled"]).append(m.id)
        if extras:
            t = datetime(2024, 1, 2, 20)
            for status, raw, hs, as_, h90, a90, code in ((MatchStatus.FINISHED, "AWD", 3, 0, None, None, "PL"),
                                                         (MatchStatus.FINISHED, "AET", 2, 1, 1, 1, "PL"),
                                                         (MatchStatus.CANCELLED, None, None, None, None, None, "PL"),
                                                         (MatchStatus.FINISHED, "FT", 4, 0, None, None, "FAC")):
                m = Match(sport=Sport.SOCCER, competition_id=comps[code].id, season="2023/24", utc_date=t,
                          stage="Regular Season - 99", home_team_id=ids[2], away_team_id=ids[3], status=status,
                          status_raw=raw, home_score=hs, away_score=as_, home_score_90=h90, away_score_90=a90)
                s.add(m)
                s.flush()
                out.setdefault("extras", {})[raw or "cancelled" if code != "FAC" else "cup"] = m.id
                t += timedelta(minutes=1)
        out["teams"] = ids
    return out


def rows_of(db):
    with db.session_scope() as s:
        return v.load_rows(s)


def rec_of(db):
    """The store's availability record through the adapter (the harness reads the same one live reads)."""
    with db.session_scope() as s:
        return v.availability_record(s)


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = fresh(tmp_path / "v23.db", monkeypatch)
    ids = build(db)
    return db, ids


# ------------------------------------------------------------------------------------ admission + builders --

def test_admission_one_predicate(store):
    db, ids = store
    rows = rows_of(db)
    by = {r.id: r for r in rows}
    ex = ids["extras"]
    assert ex["AWD"] not in by and ex["cancelled"] not in by and ex["cup"] not in by
    aet = by[ex["AET"]]
    assert (aet.home_goals, aet.away_goals) == (1, 1)                   # the 90-minute score
    assert {r.code for r in rows} == {"PL", "ELC"}
    assert rows == sorted(rows, key=v.Row.key)


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_the_two_builders_give_the_same_snapshot(store, rule):
    db, ids = store
    rows, rec = rows_of(db), rec_of(db)
    cache = v.Prefix(rows)
    for r in rows[::17]:
        a = v.snapshot_from_rows(rows, r.utc_date, PJ, rule, rec)
        with db.session_scope() as s:
            b = v.snapshot_from_session(s, r.utc_date, PJ, rule)
        c = cache.snapshot(r.utc_date, PJ, rule, rec)
        assert a == b == c and a.sha == b.sha == c.sha
        assert all(v.visible(x, r.utc_date, rule) for x in a.rows) and r not in a.rows


def test_the_snapshot_is_immutable_and_versioned(store):
    db, _ = store
    rows = rows_of(db)
    snap = v.snapshot_from_rows(rows, rows[-1].utc_date, PJ, "day")
    with pytest.raises(Exception):
        snap.rows = ()
    assert isinstance(snap.rows, tuple) and snap.version == v.SNAPSHOT_VERSION == "soccer-snapshot v2"
    assert isinstance(snap.elo_pre, tuple) and isinstance(snap.elo_state, tuple)
    with pytest.raises(Exception):
        snap.availability = None
    from dataclasses import replace
    other = replace(snap, version="soccer-snapshot v1")
    with pytest.raises(ValueError, match="version"):
        v.predict(other, v.Fixture.of(rows[-1]), "v22")


def test_predict_refuses_a_snapshot_that_is_not_the_fixtures(store):
    db, _ = store
    rows = rows_of(db)
    snap = v.snapshot_from_rows(rows, rows[-1].utc_date, PJ, "kickoff")
    with pytest.raises(ValueError, match="not the fixture"):
        v.predict(snap, v.Fixture.of(rows[100]), "soccer-v23")


# ----------------------------------------------------------------------------------- cache + ladder --

def test_cached_equals_uncached_bitwise(store):
    db, _ = store
    rows = rows_of(db)
    fx = v.scored_rows(rows, {"cut": "2026-10-30T15:00:00Z", "scope": "LEAGUE", "first_season": "score_under_prior"})
    a = v.walk(rows, fx, PJ, "day", use_cache=True)
    b = v.walk(rows, fx, PJ, "day", use_cache=False)
    assert a == b and len(a["v22"]) == len(fx) == len(a["soccer-v23"])


def test_a_cache_built_over_other_rows_is_refused(store):
    db, _ = store
    rows = rows_of(db)
    cache = v.Prefix(rows[1:])
    snap = v.snapshot_from_rows(rows, rows[-1].utc_date, PJ, "day")
    with pytest.raises(ValueError, match="cache"):
        v.predict(snap, v.Fixture.of(rows[-1]), "v22", cache)


def test_the_ladder_is_elo_train(store):
    from src.models.elo import TrainMatch, train
    db, _ = store
    rows = rows_of(db)
    _, state, _ = v.walk_ladder(rows)
    ref = train([TrainMatch(r.home_id, r.away_id, r.home_goals, r.away_goals, f"{r.code}:{r.season}") for r in rows])
    assert state.ratings == ref.ratings


# ------------------------------------------------------------------------- the v22 arm = production --

def _production(db, code, season, match_id):
    from sqlalchemy import select

    from src.db.schema import ModelVersion, Prediction
    from src.walters import training as tr
    version = tr._train_fresh_soccer(notes="soccer-v23 harness test").version
    with db.session_scope() as s:
        mv = s.execute(select(ModelVersion).where(ModelVersion.version == version)).scalar_one()
        mv.parameters = {**mv.parameters, "poisson": {**mv.parameters["poisson"], **V22P}}
    n = tr._generate_predictions_soccer(code, season, model_version=version, only_match_id=match_id)
    assert n == 1
    with db.session_scope() as s:
        p = s.execute(select(Prediction).where(Prediction.match_id == match_id)).scalar_one()
        return (p.home_win_prob, p.draw_prob, p.away_win_prob)


def _fixture(db, match_id):
    from src.db.schema import Competition, Match
    with db.session_scope() as s:
        m = s.get(Match, match_id)
        return v.Fixture(m.id, s.get(Competition, m.competition_id).code, m.season, m.utc_date, m.home_team_id,
                         m.away_team_id)


@pytest.mark.parametrize("cur_rows", [40, 12])           # >= 30: no backfill; < 30: the backfill path
def test_the_v22_arm_is_the_real_production_path_at_the_same_instant(tmp_path, monkeypatch, cur_rows):
    db = fresh(tmp_path / f"prod{cur_rows}.db", monkeypatch)
    ids = build(db, cur_rows=cur_rows, extras=False)
    from src.db.schema import Competition, Match
    with db.session_scope() as s:
        pl = s.query(Competition).filter_by(code="PL").one().id
        target = min((m for m in s.query(Match).filter(Match.id.in_(ids["scheduled"]), Match.competition_id == pl)),
                     key=lambda m: m.utc_date).id
    fx = _fixture(db, target)
    with db.session_scope() as s:                     # every FINISHED row kicks off before the fixture's date
        assert all(m.utc_date.date() < fx.utc_date.date() for m in s.query(Match).filter_by(home_score_90=None)
                   if m.home_score is not None)
    prod = _production(db, fx.code, fx.season, fx.id)
    from sqlalchemy import select

    from src.db.schema import ModelVersion
    with db.session_scope() as s:
        poisson = s.execute(select(ModelVersion)).scalars().first().parameters["poisson"]
        snap = v.snapshot_from_session(s, fx.utc_date, v.canon_params(poisson, False), "day")
    p = v.predict(snap, fx, "v22")
    assert max(abs(a - b) for a, b in zip(prod, (p["p_home"], p["p_draw"], p["p_away"]))) <= 1e-12
    assert p["info"]["backfilled"] == (cur_rows < v.V22_MIN_MATCHES)


def test_the_v22_arm_is_production_past_the_500_limit_with_tied_kickoffs(tmp_path, monkeypatch):
    """The backfill path where V22_BACKFILL_LIMIT binds: 5 earlier PL seasons of 132 rows (660 other-season rows), each
    round's 6 rows at one kickoff, so the 500th row falls inside a tie. Production's ORDER BY utc_date DESC LIMIT 500
    has no tie-break; SQLite returns ties in id-ascending order, and the arm takes them so (1e-12)."""
    seasons = ("2020/21", "2021/22", "2022/23", "2023/24", "2024/25", "2025/26")
    db = fresh(tmp_path / "prod_tied.db", monkeypatch)
    ids = build(db, seasons=seasons, n_teams=12, cur_rows=12, extras=False, tied=6)
    from src.db.schema import Competition, Match
    with db.session_scope() as s:
        pl = s.query(Competition).filter_by(code="PL").one().id
        other = s.query(Match).filter(Match.competition_id == pl, Match.season != seasons[-1]).count()
        target = min((m for m in s.query(Match).filter(Match.id.in_(ids["scheduled"]), Match.competition_id == pl)),
                     key=lambda m: m.utc_date).id
        kicks = sorted((m.utc_date for m in s.query(Match).filter(Match.competition_id == pl,
                                                                  Match.season != seasons[-1])), reverse=True)
    assert other > v.V22_BACKFILL_LIMIT and kicks[v.V22_BACKFILL_LIMIT - 1] == kicks[v.V22_BACKFILL_LIMIT]
    fx = _fixture(db, target)
    prod = _production(db, fx.code, fx.season, fx.id)
    from sqlalchemy import select

    from src.db.schema import ModelVersion
    with db.session_scope() as s:
        poisson = s.execute(select(ModelVersion)).scalars().first().parameters["poisson"]
        snap = v.snapshot_from_session(s, fx.utc_date, v.canon_params(poisson, False), "day")
    p = v.predict(snap, fx, "v22")
    assert p["info"]["backfilled"] is True and p["info"]["n_cur"] == 12
    assert max(abs(a - b) for a, b in zip(prod, (p["p_home"], p["p_draw"], p["p_away"]))) <= 1e-12


def _aet_only_store(tmp_path, monkeypatch, name, full_as_90: bool):
    """The tests' store with one extra left: the AET PL row (FINISHED, 2-1 full score, 1-1 at 90 minutes); the AWD,
    cancelled and cup extras deleted. full_as_90: the row's full score set to its 90-minute score (1-1)."""
    from src.db.schema import Match
    db = fresh(tmp_path / name, monkeypatch)
    ids = build(db, cur_rows=40, extras=True)
    with db.session_scope() as s:
        for k in ("AWD", "cancelled", "cup"):
            s.delete(s.get(Match, ids["extras"][k]))
        if full_as_90:
            m = s.get(Match, ids["extras"]["AET"])
            m.home_score, m.away_score = m.home_score_90, m.away_score_90
    return db, ids


def _arm_and_production(db, ids):
    from sqlalchemy import select

    from src.db.schema import Competition, Match, ModelVersion
    with db.session_scope() as s:
        pl = s.query(Competition).filter_by(code="PL").one().id
        target = min((m for m in s.query(Match).filter(Match.id.in_(ids["scheduled"]), Match.competition_id == pl)),
                     key=lambda m: m.utc_date).id
    fx = _fixture(db, target)
    prod = _production(db, fx.code, fx.season, fx.id)
    with db.session_scope() as s:
        poisson = s.execute(select(ModelVersion)).scalars().first().parameters["poisson"]
        snap = v.snapshot_from_session(s, fx.utc_date, v.canon_params(poisson, False), "day")
    p = v.predict(snap, fx, "v22")
    return prod, (p["p_home"], p["p_draw"], p["p_away"]), p["info"]["g"]


def test_the_v22_arm_on_an_aet_league_row_differs_from_live_v22_by_the_90_minute_score_alone(tmp_path, monkeypatch):
    """LABELLED (the ADMISSION docstring; spec §4; open question 22): on an AET / PEN row of a LEAGUE-type competition
    the v22 arm reads the stored 90-minute score (the confirmation_scoring convention, both arms alike) where live v22
    reads the full score with extra-time goals (training.py: the contexts, the strengths input and train_elo through
    _to_train). So the 1e-12 parity holds only on a store without such rows. Pinned both ways: on the store as it is
    the arm differs from the REAL production path (about 3.7e-4 here, g 1.1013 against 1.1046), and it equals at 1e-12
    the production run on the same store with that row's full score set to its 90-minute score, so the difference is
    the substitution and nothing else. The arm itself is the same on both stores (it reads the 90-minute score)."""
    db, ids = _aet_only_store(tmp_path, monkeypatch, "aet.db", full_as_90=False)
    prod_full, arm, g = _arm_and_production(db, ids)
    gap = max(abs(a - b) for a, b in zip(prod_full, arm))
    assert gap > 1e-5, gap
    db, ids = _aet_only_store(tmp_path, monkeypatch, "aet90.db", full_as_90=True)
    prod_90, arm_90, g_90 = _arm_and_production(db, ids)
    assert arm_90 == arm and g_90 == g
    assert max(abs(a - b) for a, b in zip(prod_90, arm)) <= 1e-12


def test_the_v22_constants_are_productions(store):
    src = (ROOT / "src" / "walters" / "training.py").read_text()
    assert f"MIN_MATCHES_FOR_STRENGTHS = {v.V22_MIN_MATCHES}" in src
    assert f".limit({v.V22_BACKFILL_LIMIT})  # roughly one PL season" in src
    assert "max(1.0, min(1.30, boost))" in src and v.V22_BOOST_CLAMP == (1.0, 1.30)


def test_the_v22_backfill_never_reads_a_later_season(store):
    """Production's backfill selects Match.season != season with no date bound (training.py:489-500): on a
    replay it would read later seasons. The arm reads only the snapshot's visible rows."""
    db, _ = store
    rows = rows_of(db)
    first_pl = next(r for r in rows if r.code == "PL" and r.season == "2024/25")
    snap = v.snapshot_from_rows(rows, first_pl.utc_date, PJ, "day")
    assert {x.season for x in snap.rows} <= {"2023/24", "2024/25"}
    assert all(x.utc_date < first_pl.utc_date for x in snap.rows)


# --------------------------------------------------------------- 251 item 2: the context gap, as-of in both --

LEAGUE_ALL = {"cut": "2026-10-30T15:00:00Z", "scope": "LEAGUE", "first_season": "score_under_prior"}
POISONED = {"avg_goals_per_team_per_match": 9.0, "home_field_goal_boost": 1.3}


def _probs(p):
    return (p["p_home"], p["p_draw"], p["p_away"])


def _picks(rows):
    """Fixtures across the shapes that matter: a competition's very first rows (no visible row: the default context's
    fallback and v23's first-season prior), each season's first PL and ELC row (S−1 only), a mid-season and the last."""
    sc = v.scored_rows(rows, LEAGUE_ALL)
    out = {sc[0].id: sc[0], sc[1].id: sc[1], sc[len(sc) // 2].id: sc[len(sc) // 2], sc[-1].id: sc[-1]}
    for code in ("PL", "ELC"):
        for season in SEASONS:
            r = min((x for x in sc if x.code == code and x.season == season), key=v.Row.key)
            out[r.id] = r
    return sorted(out.values(), key=v.Row.key)


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_harness_and_production_define_g_and_b_identically(store, rule):
    """251 item 2 (as-of in both): the harness's walk and the production path predict_live give the same g and b (the
    v22 arm's context), the same mu and h (soccer-v23's), the same context block and the same probabilities, bitwise,
    for the same fixture at the same instant, both arms. A stored trained context in the store's ModelVersion row
    (poisoned) is read by neither: it is fitted on the games a walk scores (the leak 251 item 2 names)."""
    db, _ = store
    from src.db.schema import ModelVersion, Sport
    with db.session_scope() as s:
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v22", status="production",
                           parameters={"poisson": dict(V22P), "contexts": {"PL": POISONED, "ELC": POISONED}},
                           train_size=0))
    rows = rows_of(db)
    picks = _picks(rows)
    w = v.walk(rows, picks, PJ, rule)
    assert [c["match_id"] for c in w["context"]] == [r.id for r in picks]
    seen_default = seen_first = False
    for i, r in enumerate(picks):
        fx = v.Fixture.of(r)
        with db.session_scope() as s:
            live = {arm: v.predict_live(s, fx, arm, PJ, rule) for arm in v.ARMS}
        for arm in v.ARMS:
            c = live[arm]["info"]["context"]
            assert c["definition"] == v.CONTEXT_DEFINITION
            assert w["context"][i][arm] == c                                  # g, b / mu, h, n_rows, through
            assert (w[arm][i]["p_home"], w[arm][i]["p_draw"], w[arm][i]["p_away"]) == _probs(live[arm])
        g22 = live["v22"]["info"]["context"]
        vis = [(x, None) for x in rows if x.code == fx.code and v.visible(x, fx.utc_date, rule)]
        ref = v.v22_context(vis)                                              # training.py:196-214's formulas, as-of
        assert (g22["g"], g22["b"]) == (ref.avg_goals_per_team_per_match, ref.home_field_goal_boost)
        assert g22["n_rows"] == len(vis) and g22["g"] != POISONED["avg_goals_per_team_per_match"]
        seen_default |= not vis
        c23 = live["soccer-v23"]["info"]
        assert (c23["context"]["mu"], c23["context"]["h"]) == (c23["mu"], c23["h"])
        g_imp = (math.exp(c23["mu"] + c23["h"]) + math.exp(c23["mu"])) / 2.0
        assert c23["context"]["g"] == g_imp and c23["context"]["b"] == math.exp(c23["mu"] + c23["h"]) / g_imp
        seen_first |= c23["first_season"]
    assert seen_default and seen_first                                        # the first rows were among the picks


def _after(rows, fx, rule):
    return [r for r in rows if not v.visible(r, fx.utc_date, rule)]


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_no_game_at_or_after_the_instant_enters_g_or_b(store, rule):
    """The leak test (251 item 2): at a fixture's instant t, every row not visible at t rewritten (7-0) and future rows
    of the fixture's own clubs added, in the rows (the harness, cached and uncached) and in the store (the production
    path), change nothing: g, b, mu, h and the probabilities are bitwise the same. The latest kickoff feeding them is
    strictly before the visibility bound. Positive control: one VISIBLE row changed moves g, mu and h."""
    from dataclasses import replace
    db, _ = store
    rows = rows_of(db)
    target = [r for r in rows if r.code == "PL" and r.season == "2025/26"][20]
    fx = v.Fixture.of(target)
    bound = v.visibility_bound(fx.utc_date, rule)
    assert target in _after(rows, fx, rule) and len(_after(rows, fx, rule)) > 50
    rec = rec_of(db)
    base = {arm: v.predict(v.snapshot_from_rows(rows, fx.utc_date, PJ, rule, rec), fx, arm) for arm in v.ARMS}
    for arm in v.ARMS:
        through = datetime.strptime(base[arm]["info"]["context"]["through"], "%Y-%m-%dT%H:%M:%S.%f")
        assert through < bound
    future = [v.Row(10 ** 7 + k, "PL", "2025/26", bound + timedelta(hours=k), fx.home_id, fx.away_id, 9, 0,
                    "Regular Season - 1", "FT") for k in range(12)]
    leaked = sorted([replace(r, home_goals=7, away_goals=0) if r in _after(rows, fx, rule) else r for r in rows]
                    + future, key=v.Row.key)
    snap = v.snapshot_from_rows(leaked, fx.utc_date, PJ, rule, rec)
    for arm in v.ARMS:
        assert v.predict(snap, fx, arm) == base[arm]
    for cached in (True, False):
        w = v.walk(leaked, [target], PJ, rule, use_cache=cached, record=rec)
        for arm in v.ARMS:
            assert w["context"][0][arm] == base[arm]["info"]["context"]
            assert (w[arm][0]["p_home"], w[arm][0]["p_draw"], w[arm][0]["p_away"]) == _probs(base[arm])
    # the production path: the store itself rewritten after t, and future FINISHED rows added
    from src.db.schema import Competition, Match, MatchStatus, Sport
    with db.session_scope() as s:
        live0 = {arm: v.predict_live(s, fx, arm, PJ, rule) for arm in v.ARMS}
    assert live0 == base
    with db.session_scope() as s:
        pl = s.query(Competition).filter_by(code="PL").one().id
        for m in s.query(Match).filter(Match.utc_date >= bound, Match.home_score.is_not(None)):
            m.home_score, m.away_score = 7, 0
        for k in range(12):
            s.add(Match(sport=Sport.SOCCER, competition_id=pl, season="2025/26", utc_date=bound + timedelta(hours=k),
                        stage="Regular Season - 1", home_team_id=fx.home_id, away_team_id=fx.away_id,
                        status=MatchStatus.FINISHED, status_raw="FT", home_score=9, away_score=0))
    with db.session_scope() as s:
        assert {arm: v.predict_live(s, fx, arm, PJ, rule) for arm in v.ARMS} == base
    # positive control: the latest VISIBLE PL row changed does move both arms' context
    last = max((r for r in rows if r.code == "PL" and v.visible(r, fx.utc_date, rule)), key=v.Row.key)
    moved = [replace(r, home_goals=r.home_goals + 6) if r == last else r for r in rows]
    snap = v.snapshot_from_rows(moved, fx.utc_date, PJ, rule)
    got = {arm: v.predict(snap, fx, arm)["info"]["context"] for arm in v.ARMS}
    assert got["v22"]["g"] != base["v22"]["info"]["context"]["g"]
    assert got["soccer-v23"]["mu"] != base["soccer-v23"]["info"]["context"]["mu"]
    assert got["soccer-v23"]["h"] != base["soccer-v23"]["info"]["context"]["h"]


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_a_game_still_in_play_at_the_instant_enters_neither_path(store, rule):
    """WHEN A RESULT IS KNOWN (review of the 251 follow-up): a row is visible at t only once its result is known, at
    kickoff + RESULT_LAG before t. A game that kicked off inside the lag (one hour before t under "kickoff"; 23:35 the
    previous evening for a fixture at 00:15 UTC under "day"), planted 9-0 between the fixture's own clubs in the rows
    (the harness: uncached, cached and the walk) and in the store (the production path, FINISHED), moves nothing:
    g, b, mu, h and the probabilities are bitwise the base. Positive control: the same game kicking off one second
    before the bound (its result known one second before t's bound) is visible and moves g and mu in both paths."""
    from dataclasses import replace

    from src.db.schema import Competition, Match, MatchStatus, Sport
    db, _ = store
    rows = rows_of(db)
    target = [r for r in rows if r.code == "PL" and r.season == "2025/26"][20]
    day0 = datetime(target.utc_date.year, target.utc_date.month, target.utc_date.day)
    t = target.utc_date if rule == "kickoff" else day0 + timedelta(minutes=15)
    fx = v.Fixture(target.id, target.code, target.season, t, target.home_id, target.away_id)
    bound = v.visibility_bound(t, rule)
    assert bound == (t - v.RESULT_LAG if rule == "kickoff" else min(day0, t - v.RESULT_LAG))
    inside = t - timedelta(hours=1) if rule == "kickoff" else day0 - timedelta(minutes=25)
    assert bound <= inside < t

    def planted(at):
        return v.Row(10 ** 7, "PL", "2025/26", at, fx.home_id, fx.away_id, 9, 0, "Regular Season - 1", "FT")

    rec = rec_of(db)

    def harness(extra):
        rs = sorted(rows + [extra], key=v.Row.key) if extra else rows
        out = {arm: v.predict(v.snapshot_from_rows(rs, t, PJ, rule, rec), fx, arm) for arm in v.ARMS}
        cache = v.Prefix(rs)
        for arm in v.ARMS:
            assert v.predict(cache.snapshot(t, PJ, rule, rec), fx, arm, cache) == out[arm]
        w = v.walk(rs, [replace(target, utc_date=t)], PJ, rule, record=rec)
        for arm in v.ARMS:
            assert w["context"][0][arm] == out[arm]["info"]["context"]
            assert (w[arm][0]["p_home"], w[arm][0]["p_draw"], w[arm][0]["p_away"]) == _probs(out[arm])
        return out

    def live(at):
        with db.session_scope() as s:
            if at is not None:
                pl = s.query(Competition).filter_by(code="PL").one().id
                s.add(Match(sport=Sport.SOCCER, competition_id=pl, season="2025/26", utc_date=at,
                            stage="Regular Season - 1", home_team_id=fx.home_id, away_team_id=fx.away_id,
                            status=MatchStatus.FINISHED, status_raw="FT", home_score=9, away_score=0))
        with db.session_scope() as s:
            got = {arm: v.predict_live(s, fx, arm, PJ, rule) for arm in v.ARMS}
        if at is not None:
            with db.session_scope() as s:
                s.query(Match).filter(Match.utc_date == at, Match.home_score == 9).delete()
        return got

    base = harness(None)
    assert live(None) == base
    assert not v.visible(planted(inside), t, rule) and not v.visible(planted(bound), t, rule)
    assert harness(planted(inside)) == base
    assert live(inside) == base
    edge = bound - timedelta(seconds=1)
    assert v.visible(planted(edge), t, rule)
    moved_h, moved_l = harness(planted(edge)), live(edge)
    assert moved_h == moved_l
    assert moved_h["v22"]["info"]["context"]["g"] != base["v22"]["info"]["context"]["g"]
    assert moved_h["soccer-v23"]["info"]["context"]["mu"] != base["soccer-v23"]["info"]["context"]["mu"]


# ------------------------------------------- 253 item 2(d): the five rows, identical BY CONSTRUCTION, both paths --
#
# ARCHITECT 2026-11-04 13:20 ET, addendum 253 item 2(d): "The v23 design PR shows, for each of the five rows (the
# context, the Elo state, the early-season history, the match factors, simultaneous kickoffs), how replay and live
# become identical BY CONSTRUCTION, not by test". The construction: one builder (snapshot_from_rows; live reaches it
# through snapshot_from_session, the walk by calling it at every instant; Prefix is only a memo) and one predict. Each test below perturbs the
# input the way the OLD v22 paths (soccer_backtest's walk and training._generate_predictions_soccer) diverge on it
# (#788's table; #828's pins) and shows the replay and live agree bitwise, every field of every prediction.

class _Record(v.AvailabilityRecord):
    """A SYNTHETIC availability record (tests only: 253 item 2(b), "Synthetic rows in the synthetic store are allowed
    — 216 item 4's 'historical injuries are never manufactured' governs a real backtest's inputs, not a test's
    fixtures"). Observations {source, id, recorded_at, facts}, read as 252 item 1 rules "As of T": the newest
    observation per source with the chosen clock <= T, and its assertions. `late` returns every fact (a broken reader);
    `clock` labels the read."""

    def __init__(self, observations, clock=v.RECORDED_CLOCK, late=False):
        self.obs, self.clock, self.late = observations, clock, late

    def at(self, as_of):
        if self.late:
            return v.AvailabilityAsOf(v.RECORD, "synthetic (broken)", self.clock,
                                      tuple(f for o in self.obs for f in o["facts"]))
        newest = {}
        for o in self.obs:
            if o["recorded_at"] <= as_of:
                cur = newest.get(o["source"])
                if cur is None or (o["recorded_at"], o["id"]) > (cur["recorded_at"], cur["id"]):
                    newest[o["source"]] = o
        if not newest:
            return v.AvailabilityAsOf(v.NO_RECORD, "synthetic: nothing recorded at or before the instant", self.clock)
        return v.AvailabilityAsOf(v.RECORD, "synthetic record (tests only)", self.clock,
                                  tuple(f for o in newest.values() for f in o["facts"]))


def _fact(obs, fx, team, recorded_at, status="Missing Fixture", kind=v.TERM_KIND, source_stamp=None, match=True,
          source="synthetic_injuries"):
    return v.Fact(obs, source, kind, team, fx.id if match else None, fx.utc_date if match else None,
                  f"P{obs}", status, "Attacker", source_stamp, recorded_at)


def _both_paths(db, picks, rule, params=PJ, rec=None):
    """THE ONE COMPARISON: live (predict_live_slate on the store; its record the store's own through the adapter when
    `rec` is None) against the replay (the one builder, its Prefix memo, predict, and the walk memo on and off,
    on the store's rows and the same record). Every snapshot equal field for field (sha included) at every instant,
    every prediction dict equal (probabilities, xG, over/under and every info value), the walk's rows equal to live's.
    Returns (live by arm and match id, the walk)."""
    rows = rows_of(db)
    fxs = [v.Fixture.of(r) for r in picks]
    with db.session_scope() as s:
        live = {arm: {p["match_id"]: p for p in v.predict_live_slate(s, fxs, arm, params, rule, rec)}
                for arm in v.ARMS}
        snaps = {t: v.snapshot_from_session(s, t, params, rule, rec) for t, _ in v.by_instant(fxs)}
    hrec = rec_of(db) if rec is None else rec
    cache = v.Prefix(rows)
    for t, group in v.by_instant(fxs):
        a, c = v.snapshot_from_rows(rows, t, params, rule, hrec), cache.snapshot(t, params, rule, hrec)
        assert a == c == snaps[t] and a.sha == c.sha == snaps[t].sha
        for fx in group:
            for arm in v.ARMS:
                assert v.predict(c, fx, arm, cache) == v.predict(a, fx, arm) == live[arm][fx.id]
    order = sorted(picks, key=v.Row.key)
    for cached in (True, False):
        w = v.walk(rows, picks, params, rule, use_cache=cached, record=hrec)
        for i, r in enumerate(order):
            for arm in v.ARMS:
                assert (w[arm][i]["p_home"], w[arm][i]["p_draw"], w[arm][i]["p_away"]) == _probs(live[arm][r.id])
                assert w["context"][i][arm] == live[arm][r.id]["info"]["context"]
            assert w["availability"][i]["term"] == live["soccer-v23"][r.id]["info"]["availability_term"]
    return live, w


def _moved(a, b) -> bool:
    return any(_probs(a[arm][k]) != _probs(b[arm][k]) for arm in v.ARMS for k in a[arm])


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_253_row_1_the_context_is_the_snapshots_rows_in_both_paths(store, rule):
    """ROW 1, THE CONTEXT. The old paths diverge on it: the gate's walk prices under CompetitionScoringContext()
    (soccer_backtest.py:200) and production under the stored trained context (training.py:514). Here both paths
    compute it from the snapshot's `rows` and nothing else: a stored context planted in the store's ModelVersion row
    (two poisoned values in turn) moves nothing, bitwise, in either path; a competition's first fixture reads the
    default (production's own fallback) in both; one visible row changed moves both paths together."""
    from src.db.schema import Match, ModelVersion, Sport
    from src.models.poisson import CompetitionScoringContext
    db, _ = store
    rows = rows_of(db)
    sc = v.scored_rows(rows, LEAGUE_ALL)
    first_pl = min((r for r in sc if r.code == "PL"), key=v.Row.key)
    mid = [r for r in sc if r.code == "PL" and r.season == "2025/26"][10]
    picks = [first_pl, mid]
    base, _ = _both_paths(db, picks, rule)
    assert base["v22"][first_pl.id]["info"]["context"]["n_rows"] == 0
    assert base["v22"][first_pl.id]["info"]["g"] == CompetitionScoringContext().avg_goals_per_team_per_match
    for poison in (POISONED, {"avg_goals_per_team_per_match": 0.5, "home_field_goal_boost": 1.0}):
        with db.session_scope() as s:
            s.query(ModelVersion).delete()
            s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v22",
                               status="production", train_size=0,
                               parameters={"poisson": dict(V22P), "contexts": {"PL": poison, "ELC": poison}}))
        got, _ = _both_paths(db, picks, rule)
        assert got == base
    last = max((r for r in rows if r.code == "PL" and v.visible(r, mid.utc_date, rule)), key=v.Row.key)
    with db.session_scope() as s:
        s.get(Match, last.id).home_score += 5
    moved, _ = _both_paths(db, picks, rule)
    assert moved["v22"][mid.id]["info"]["g"] != base["v22"][mid.id]["info"]["g"]
    assert moved["soccer-v23"][mid.id]["info"]["mu"] != base["soccer-v23"][mid.id]["info"]["mu"]


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_253_row_2_the_elo_state_carries_the_prior_season_in_both_paths(store, rule):
    """ROW 2, THE ELO STATE. The old paths diverge on it: production carries the regressed Elo across the season
    boundary (_train_fresh_soccer over every finished match); the gate's walk starts each season on a fresh EloState
    (run_soccer_backtest(code, season)). Here the snapshot carries `elo_pre` and `elo_state`, filled by walk_ladder
    over every visible row from the first (the per-team season regression included; it equals elo.train on the same
    rows), and both paths read them. A club promoted from ELC: its PRIOR-SEASON (2023/24, ELC) results changed in the
    store move its Elo and both arms' prices for its first PL 2025/26 fixture, in both paths together, bitwise."""
    from src.db.schema import Match
    from src.models.elo import EloConfig, TrainMatch, train
    db, ids = store
    rows = rows_of(db)
    up = ids["teams"][8]
    target = min((r for r in rows if r.code == "PL" and r.season == "2025/26" and up in (r.home_id, r.away_id)),
                 key=v.Row.key)
    base, _ = _both_paths(db, [target], rule)
    snap = v.snapshot_from_rows(rows, target.utc_date, PJ, rule, rec_of(db))
    ref = train([TrainMatch(r.home_id, r.away_id, r.home_goals, r.away_goals, f"{r.code}:{r.season}")
                 for r in snap.rows])
    assert {t: rating for t, rating, _ in snap.elo_state} == ref.ratings
    state = {t: (rating, k) for t, rating, k in snap.elo_state}
    assert state[up][0] != EloConfig().starting_rating and state[up][1] != "PL:2025/26"   # carried, regression pending
    with db.session_scope() as s:
        for m in s.query(Match).filter(Match.season == "2023/24", Match.home_score.is_not(None)):
            if up == m.home_team_id:
                m.home_score, m.away_score = 6, 0
            elif up == m.away_team_id:
                m.home_score, m.away_score = 0, 6
    moved, _ = _both_paths(db, [target], rule)
    for arm in v.ARMS:
        assert _probs(moved[arm][target.id]) != _probs(base[arm][target.id]), arm


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_253_row_3_the_early_season_history_is_the_same_as_of_rows(store, rule):
    """ROW 3, THE EARLY-SEASON HISTORY. The old paths diverge on it: production's backfill below 30 current-season
    rows selects Match.season != season with no date bound (training.py:489-500), so on a replay it reads LATER
    seasons; the gate's walk skips the first 40 matches. Here both paths read the snapshot's `rows`: an early 2025/26
    fixture (few visible season rows: the v22 arm backfills, soccer-v23 leans on S−1) is priced the same, bitwise, in
    both paths, and a whole LATER season of finished PL rows added to the store moves nothing in either."""
    from src.db.schema import Competition, Match, MatchStatus, Sport
    db, ids = store
    rows = rows_of(db)
    s_rows = sorted((r for r in rows if r.code == "PL" and r.season == "2025/26"), key=v.Row.key)
    target = next(r for r in s_rows if sum(1 for x in s_rows if v.visible(x, r.utc_date, rule)) >= 3)
    base, _ = _both_paths(db, [target], rule)
    info22, info23 = base["v22"][target.id]["info"], base["soccer-v23"][target.id]["info"]
    assert info22["backfilled"] is True and 3 <= info22["n_cur"] < v.V22_MIN_MATCHES
    assert info23["prev_season"] == "2024/25" and info23["n_cur"] == info22["n_cur"]
    with db.session_scope() as s:
        pl = s.query(Competition).filter_by(code="PL").one().id
        t0 = datetime(2026, 8, 10, 12)
        for j, (h, a) in enumerate((h, a) for h in ids["teams"][:4] for a in ids["teams"][:4] if h != a):
            s.add(Match(sport=Sport.SOCCER, competition_id=pl, season="2026/27", utc_date=t0 + timedelta(days=j),
                        stage="Regular Season - 1", home_team_id=h, away_team_id=a, status=MatchStatus.FINISHED,
                        status_raw="FT", home_score=7, away_score=0))
    got, _ = _both_paths(db, [target], rule)
    assert got == base


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_253_row_4_the_match_factors_come_only_from_the_record_in_both_paths(store, rule):
    """ROW 4, THE MATCH FACTORS. The old paths diverge on it: production composes the injury, lineup and XI
    multipliers into factor_adjustment from tables overwritten in place (injuries, lineups); the gate's walk reconstructs
    none. Here the only factor input is the snapshot's `availability` (addendum 252's record, read at the instant under
    the RECORDED clock), in both paths:
      (a) a synthetic injury row and lineup rows for the fixture planted in the store move nothing in either path;
      (b) no record (the tables absent: the adapter; or a record with nothing at the instant): the term is OFF in both
          paths, said per era; the slot off says so too;
      (c) a synthetic record with a "Missing Fixture" entry for this fixture recorded before the kickoff: the term is ON
          in both paths and moves soccer-v23's home xG by injury_adjustment's own multiplier, the v22 arm untouched;
      (d) a backfilled observation (its source_stamp before the kickoff, recorded after it) is not read by either path
          (the recorded clock); a reader returning it anyway, or reading the source clock, refuses in both paths;
      (e) THE DECISION INSTANT (Snapshot.decision = visibility_bound(t), the rows' own bound): a fact recorded after it
          and before the kickoff (a morning poll under "day", a T-60 poll under "kickoff"), or exactly at the kickoff,
          is read by neither path; one recorded exactly at the decision instant is read by both (252's "<= T"); a
          hand-made snapshot carrying a fact after its decision instant is refused by predict;
      (f) a BACKFILLED fact recorded BEFORE the decision instant (source_stamp 31 days before the kickoff, recorded a
          day before it: 252 item 1's first fetch of a season file) is excluded from both paths, counted in the notes
          and the per-era line; under a declared cadence it is excluded beyond the cadence and read within it."""
    from dataclasses import replace

    from src.db.schema import Injury, Lineup
    from src.models.factors import injury_adjustment
    db, _ = store
    rows = rows_of(db)
    target = [r for r in rows if r.code == "PL" and r.season == "2025/26"][20]
    early = [r for r in rows if r.code == "PL" and r.season == "2024/25"][5]
    fx = v.Fixture.of(target)
    on = v.canon_params(V22P, True)
    base, w = _both_paths(db, [early, target], rule, params=on)
    assert v.availability_lines(w["availability"]) == [
        v.availability_lines([])[0],
        f"    PL 2024/25: 1 fixture(s) term off: no record at the instant ({v.ABSENT_REASON})",
        f"    PL 2025/26: 1 fixture(s) term off: no record at the instant ({v.ABSENT_REASON})"]
    off, w_off = _both_paths(db, [early, target], rule)
    assert "term off: the slot availability_on is false" in "\n".join(v.availability_lines(w_off["availability"]))
    assert all(_probs(off[a][k]) == _probs(base[a][k]) for a in v.ARMS for k in base[a])
    # (a) the old paths' factor tables, planted: read by neither path
    with db.session_scope() as s:
        s.add(Injury(team_id=fx.home_id, player_name="Planted", player_position="Attacker", reason="Knee Injury",
                     type="Missing Fixture", fixture_source_id="900020"))
        for tid in (fx.home_id, fx.away_id):
            s.add(Lineup(match_id=fx.id, team_id=tid, kind="confirmed", is_starter=True, player_name=f"S{tid}",
                         player_position="Attacker"))
    planted, _ = _both_paths(db, [early, target], rule, params=on)
    assert planted == base
    # (b)-(c) the record: a Missing Fixture entry for this fixture, recorded a day before its kickoff
    t = target.utc_date
    obs1 = {"source": "synthetic_injuries", "id": 1, "recorded_at": t - timedelta(days=1),
            "facts": (_fact(1, fx, fx.home_id, t - timedelta(days=1)),
                      _fact(1, fx, None, t - timedelta(days=1)),                         # unmapped: kept, not counted
                      _fact(1, fx, fx.away_id, t - timedelta(days=1), kind="confirmed_starter"))}
    rec = _Record([obs1])
    got, w = _both_paths(db, [early, target], rule, params=on, rec=rec)
    i23 = got["soccer-v23"][target.id]["info"]
    assert i23["availability_term"] == "on" and i23["availability_record"] == v.RECORD
    ref = injury_adjustment(home_injuries=[_Inj("Attacker")], away_injuries=[])
    assert i23["availability"] == [ref.home_xg_multiplier, 1.0] and ref.home_xg_multiplier < 1.0
    assert got["soccer-v23"][target.id]["home_xg"] != base["soccer-v23"][target.id]["home_xg"]
    assert any("unmapped team" in n for n in i23["availability_notes"])
    assert any("1 fact(s) of other kinds" in n for n in i23["availability_notes"])
    assert _probs(got["v22"][target.id]) == _probs(base["v22"][target.id])
    assert got["v22"][target.id]["info"]["factors"] == v.V22_FACTORS
    assert got["soccer-v23"][early.id]["info"]["availability_term"] == "off: no record at the instant"
    era = "\n".join(v.availability_lines(w["availability"]))
    assert "PL 2024/25: 1 fixture(s) term off: no record at the instant" in era and "PL 2025/26: 1 fixture(s) term on" in era
    # (d) a backfilled observation: the source's stamp before the kickoff, our clock after it: read by neither path
    obs2 = {"source": "synthetic_injuries", "id": 2, "recorded_at": t + timedelta(hours=1),
            "facts": (_fact(2, fx, fx.away_id, t + timedelta(hours=1), source_stamp=t - timedelta(days=2)),)}
    got2, _ = _both_paths(db, [early, target], rule, params=on, rec=_Record([obs1, obs2]))
    assert got2 == got
    for bad, why in ((_Record([obs1, obs2], late=True), "recorded after the decision instant"),
                     (_Record([obs1], clock="source"), "'source' clock")):
        with pytest.raises(v.GateRefused, match=why):
            v.walk(rows, [target], on, rule, record=bad)
        with db.session_scope() as s, pytest.raises(v.GateRefused, match=why):
            v.predict_live(s, fx, "soccer-v23", on, rule, bad)
    # (e) the decision instant: the rows' bound is the facts' bound too, in both paths
    d = v.visibility_bound(t, rule)
    assert v.snapshot_from_rows(rows, t, on, rule, rec).decision == d < t
    late = [{"source": "synthetic_late", "id": 10 + k, "recorded_at": at,
             "facts": (_fact(10 + k, fx, fx.away_id, at, source="synthetic_late"),)}
            for k, at in enumerate((d + timedelta(minutes=1), t - timedelta(minutes=30), t))]
    for o in late:                                                     # after the decision instant: read by neither
        assert d < o["recorded_at"] <= t
        got_late, _ = _both_paths(db, [early, target], rule, params=on, rec=_Record([obs1, o]))
        assert got_late == got
    at_d = {"source": "synthetic_late", "id": 20, "recorded_at": d,
            "facts": (_fact(20, fx, fx.away_id, d, source="synthetic_late"),)}
    got_d, _ = _both_paths(db, [early, target], rule, params=on, rec=_Record([obs1, at_d]))
    assert got_d["soccer-v23"][target.id]["info"]["availability"] == [ref.home_xg_multiplier, ref.home_xg_multiplier]
    snap = v.snapshot_from_rows(rows, t, on, rule, rec)
    forged = replace(snap, availability=replace(snap.availability, facts=snap.availability.facts + late[0]["facts"]))
    with pytest.raises(ValueError, match="decision instant"):
        v.predict(forged, fx, "soccer-v23")
    # (f) a backfilled fact recorded BEFORE the decision instant: excluded in both paths, counted, never read
    bf_at = t - timedelta(days=1)
    assert bf_at <= d
    obs_bf = {"source": "synthetic_bf", "id": 30, "recorded_at": bf_at,
              "facts": (_fact(30, fx, fx.away_id, bf_at, source_stamp=t - timedelta(days=31), source="synthetic_bf"),)}
    assert v.backfill_reason(obs_bf["facts"][0]) is not None               # no cadence declared: a backfill unruled
    got_bf, w_bf = _both_paths(db, [early, target], rule, params=on, rec=_Record([obs1, obs_bf]))
    i_bf = got_bf["soccer-v23"][target.id]["info"]
    assert i_bf["availability"] == i23["availability"] and _probs(got_bf["soccer-v23"][target.id]) == _probs(
        got["soccer-v23"][target.id])
    assert any("1 backfilled fact(s) excluded" in n for n in i_bf["availability_notes"])
    assert "PL 2025/26: 1 fixture(s) term on" in "\n".join(v.availability_lines(w_bf["availability"]))
    assert "1 backfilled fact(s) excluded" in "\n".join(v.availability_lines(w_bf["availability"]))
    for cadence, read in ((24.0, False), (24.0 * 40, True)):            # a declared cadence: beyond it out, within it in
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(v.SOURCE_CADENCE_HOURS, "synthetic_bf", cadence)
            got_c, _ = _both_paths(db, [early, target], rule, params=on, rec=_Record([obs1, obs_bf]))
        mult = got_c["soccer-v23"][target.id]["info"]["availability"]
        assert mult == ([ref.home_xg_multiplier, ref.home_xg_multiplier] if read else i23["availability"]), cadence


def test_253_row_4_the_adapter_reads_no_record_while_the_tables_are_absent_and_refuses_otherwise(store, monkeypatch):
    """The adapter (availability_record): addendum 252's tables are not on main, so on today's store it answers "no
    record" (the term off everywhere, labelled); a store holding one table without the other, or both (whose reader is
    252 item 2's query function, not merged), refuses: never a guessed query. The inspector is faked here: no table is
    created by this design, in a test or anywhere."""
    import sqlalchemy
    db, _ = store
    rec = rec_of(db)
    assert isinstance(rec, v.NoRecord) and rec.at(datetime(2026, 1, 1)).reason == v.ABSENT_REASON
    real = sqlalchemy.inspect
    for present, why in ((("availability_observations",), "half present"), (v.RECORD_TABLES, "not merged")):
        class _Insp:
            def __init__(self, bind):
                self.real = real(bind)

            def has_table(self, name, *a, **k):
                return name in present or self.real.has_table(name, *a, **k)
        monkeypatch.setattr(sqlalchemy, "inspect", _Insp)
        with db.session_scope() as s, pytest.raises(v.GateRefused, match=why):
            v.availability_record(s)
        monkeypatch.setattr(sqlalchemy, "inspect", real)


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_253_row_5_simultaneous_kickoffs_share_one_snapshot_in_both_paths(tmp_path, monkeypatch, rule):
    """ROW 5, SIMULTANEOUS KICKOFFS. The old paths diverge on it: production prices a pair sharing a kickoff from
    the same state (at_instant hides every match at or after the target kickoff); the gate's walk with
    batch_same_kickoff=False updates between them, so the second row differs. Here the snapshot is a function of the
    instant: both fixtures of a pair are priced from ONE snapshot (the same object) in the walk and in
    predict_live_slate alike, and the pair's own results (one rewritten 9-0 in the store) move neither, in either
    path, bitwise."""
    from src.db.schema import Match
    db = fresh(tmp_path / "tied.db", monkeypatch)
    build(db, n_teams=8, extras=False, tied=2)
    rows = rows_of(db)
    s_rows = [r for r in rows if r.code == "PL" and r.season == "2025/26"]
    pair = next([a, b] for a, b in zip(s_rows[10:], s_rows[11:]) if a.utc_date == b.utc_date)
    seen: dict[int, list] = {}
    real = v.predict

    def spy(snap, fixture, arm, cache=None):
        seen.setdefault(fixture.id, []).append(id(snap))
        return real(snap, fixture, arm, cache)
    monkeypatch.setattr(v, "predict", spy)
    w = v.walk(rows, pair, PJ, rule, record=rec_of(db))
    assert len(w["v22"]) == 2 and len({x for f in pair for x in seen[f.id]}) == 1
    seen.clear()
    with db.session_scope() as s:
        v.predict_live_slate(s, [v.Fixture.of(r) for r in pair], "soccer-v23", PJ, rule)
    assert len({x for f in pair for x in seen[f.id]}) == 1
    monkeypatch.setattr(v, "predict", real)
    base, _ = _both_paths(db, pair, rule)
    with db.session_scope() as s:
        m = s.get(Match, pair[0].id)
        m.home_score, m.away_score = 9, 0
    got, _ = _both_paths(db, pair, rule)
    assert got == base


@pytest.mark.parametrize("rule", ["day", "kickoff"])
def test_the_walk_and_live_call_the_one_builder_at_every_instant(store, monkeypatch, rule):
    """253 item 2(d), BY CONSTRUCTION (the review of the five rows: the walk's cache assembled its snapshots itself,
    agreeing with live only because tests pinned the two equal). The walk, memo on and off, and predict_live_slate each
    call snapshot_from_rows once per kickoff instant, and Prefix keeps no builder of its own. The review's probe,
    reversed: one ingredient of the one builder perturbed (the ladder's final rating of the fixture's home club, + 1e-6)
    moves live and the walk (memo on and off) together, bitwise, away from the base."""
    db, _ = store
    rows = rows_of(db)
    picks = [r for r in rows if r.code == "PL" and r.season == "2025/26"][18:24]
    fxs = [v.Fixture.of(r) for r in picks]
    instants = [t for t, _ in v.by_instant(fxs)]
    real = v.snapshot_from_rows
    calls = []

    def spy(rows_, as_of, *a, **k):
        calls.append(as_of)
        return real(rows_, as_of, *a, **k)
    monkeypatch.setattr(v, "snapshot_from_rows", spy)
    for cached in (True, False):
        calls.clear()
        v.walk(rows, picks, PJ, rule, use_cache=cached)
        assert calls == instants, cached
    calls.clear()
    with db.session_scope() as s:
        v.predict_live_slate(s, fxs, "v22", PJ, rule)
    assert calls == instants
    calls.clear()
    assert v.Prefix(rows).snapshot(picks[0].utc_date, PJ, rule) == real(rows, picks[0].utc_date, PJ, rule)
    assert calls == [picks[0].utc_date]
    for gone in ("count", "elo_state", "hist", "pre", "by_code", "by_season", "keys"):
        assert not hasattr(v.Prefix(rows[:5]), gone), gone
    monkeypatch.setattr(v, "snapshot_from_rows", real)
    base, _ = _both_paths(db, picks[:1], rule)
    real_ladder = v.walk_ladder
    h = picks[0].home_id

    def bumped(rows_):
        pre, state, last = real_ladder(rows_)
        if h in state.ratings:
            state.ratings[h] = state.ratings[h] + 1e-6
        return pre, state, last
    monkeypatch.setattr(v, "walk_ladder", bumped)
    moved, _ = _both_paths(db, picks[:1], rule)
    assert _probs(moved["soccer-v23"][picks[0].id]) != _probs(base["soccer-v23"][picks[0].id])


def test_predict_live_reads_no_model_version(store, monkeypatch):
    """The production path reads the matches only (one SELECT bounded at the instant): a ModelVersion query would be a
    stored context or a stored state, and none is made."""
    db, _ = store
    rows = rows_of(db)
    fx = v.Fixture.of(rows[-1])
    seen = []
    from sqlalchemy import event
    eng = db._engine

    def spy(conn, cursor, statement, *a):
        seen.append(statement)
    event.listen(eng, "before_cursor_execute", spy)
    try:
        with db.session_scope() as s:
            for arm in v.ARMS:
                v.predict_live(s, fx, arm, PJ, "day")
    finally:
        event.remove(eng, "before_cursor_execute", spy)
    sel = [x for x in seen if x.lstrip().upper().startswith("SELECT")]
    assert len(sel) == 2 and not any("model_versions" in x for x in seen)


# ---------------------------------------------------------------------------- 216 item 2: continuity --

def test_smooth_across_the_leagues_30th_match_where_v22_steps(store):
    db, _ = store
    rows = rows_of(db)
    season = "2025/26"
    pl = [r for r in rows if r.code == "PL" and r.season == season]
    target = pl[-1]
    before = [r for r in pl if r.utc_date.date() < target.utc_date.date()]
    extra = next(r for r in before[29:] if not {r.home_id, r.away_id} & {target.home_id, target.away_id})
    base = [r for r in rows if not (r.code == "PL" and r.season == season)]
    s29 = sorted(base + before[:29], key=v.Row.key)
    s30 = sorted(s29 + [extra], key=v.Row.key)
    fx = v.Fixture.of(target)
    d = {}
    for arm in v.ARMS:
        a = v.predict(v.snapshot_from_rows(s29, fx.utc_date, PJ, "day"), fx, arm)
        b = v.predict(v.snapshot_from_rows(s30, fx.utc_date, PJ, "day"), fx, arm)
        d[arm] = max(abs(a[k] - b[k]) for k in ("p_home", "p_draw", "p_away"))
    assert d["soccer-v23"] < 0.01 and d["v22"] > 3 * d["soccer-v23"], d


def test_no_count_branch_in_the_model():
    """216 item 2: no league-wide switch. The model module holds no integer literal 30 and no count comparison."""
    src = (ROOT / "src" / "models" / "joint_poisson.py").read_text()
    nums = {t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.NUMBER}
    assert "30" not in nums and "40" not in nums


# ------------------------------------------------------------------- the harness builds v23's inputs --

def _early_fixture(rows, season="2025/26"):
    """A PL fixture of `season` with visible S rows (kickoff rule) whose home club's last row is another season's (the
    pending regression applies to it)."""
    cache = v.Prefix(rows)
    for r in (x for x in rows if x.code == "PL" and x.season == season):
        snap = cache.snapshot(r.utc_date, PJ, "kickoff")
        n_cur = sum(1 for x in snap.rows if x.code == "PL" and x.season == season)
        lk = cache.view(snap).team(r.home_id)[1]
        if n_cur >= 3 and lk is not None and lk != f"PL:{season}":
            return r, snap
    raise AssertionError("no early fixture in the synthetic store")


def test_the_window_holds_s_minus_1_in_prev_and_the_visible_s_rows_in_cur(store):
    db, _ = store
    rows = rows_of(db)
    r, snap = _early_fixture(rows)
    fx = v.Fixture.of(r)
    pre, _, _ = v.walk_ladder(snap.rows)
    crows = [(x, pre[i]) for i, x in enumerate(snap.rows) if x.code == "PL"]
    obs, sp = v.window_obs(crows, fx)
    assert sp == "2024/25"
    want_prev = [x for x, _ in crows if x.season == "2024/25"]
    want_cur = [x for x, _ in crows if x.season == "2025/26"]
    assert want_prev and want_cur
    assert [(o.home, o.away, o.home_goals, o.away_goals) for o in obs if o.slot == "prev"] == [
        (x.home_id, x.away_id, x.home_goals, x.away_goals) for x in want_prev]
    assert [(o.home, o.away) for o in obs if o.slot == "cur"] == [(x.home_id, x.away_id) for x in want_cur]
    assert len(obs) == len(want_prev) + len(want_cur)                    # S−2 is out
    for o, (x, (eh, ea)) in zip(obs, [c for c in crows if c[0].season in ("2024/25", "2025/26")]):
        assert o.elo_diff == eh - ea and o.home == x.home_id
    assert any(o.elo_diff != 0.0 for o in obs)


def test_predict_prices_the_fit_at_the_fixtures_regressed_elo_difference(store):
    """predict's λ = jp.rates(the window's fit, home, away, ΔE) with ΔE from the ladder plus the regression a walk
    applies at the fixture's kickoff (a club whose last row was another season's), built here independently."""
    from src.models import joint_poisson as jp
    from src.models.elo import EloConfig, EloState, regress_team
    db, _ = store
    rows = rows_of(db)
    r, snap = _early_fixture(rows)
    fx = v.Fixture.of(r)
    pre, state, last = v.walk_ladder(snap.rows)
    crows = [(x, pre[i]) for i, x in enumerate(snap.rows) if x.code == "PL"]
    obs = [jp.Obs(x.home_id, x.away_id, "prev" if x.season == "2024/25" else "cur", float(x.home_goals),
                  float(x.away_goals), eh - ea) for x, (eh, ea) in crows if x.season in ("2024/25", "2025/26")]
    rel, _ = v.window_arrivals(v._RowsList(snap.rows), "PL", "2025/26", "2024/25", crows)
    f = jp.fit(obs, relegated=rel)
    ratings = []
    for tid in (fx.home_id, fx.away_id):
        st = EloState(ratings={tid: state.ratings[tid]}, config=EloConfig())
        if last[tid] != "PL:2025/26":
            regress_team(st, tid)
        ratings.append(st.ratings[tid])
    assert ratings[0] != state.ratings[fx.home_id]                        # the regression bites on this fixture
    de = ratings[0] - ratings[1]
    assert de != 0.0 and f.beta != 0.0
    lh, la = jp.rates(f, fx.home_id, fx.away_id, de)
    p = v.predict(snap, fx, "soccer-v23")
    assert p["home_xg"] == pytest.approx(lh, abs=1e-12) and p["away_xg"] == pytest.approx(la, abs=1e-12)
    lh0, _ = jp.rates(f, fx.home_id, fx.away_id, 0.0)
    assert abs(lh0 - lh) > 1e-6                                           # ΔE moves the price


def test_the_relegated_and_promoted_clubs_are_told_apart_by_cause(store):
    """build(): from 2024/25 the first PL club plays in ELC (from a higher tier: relegated) and the first ELC club in
    PL (from a lower tier: promoted), on the declared pyramid."""
    db, ids = store
    rows = rows_of(db)
    down, up = ids["teams"][0], ids["teams"][8]
    view = v._RowsList(rows)
    crows_elc = [(x, (0.0, 0.0)) for x in rows if x.code == "ELC"]
    rel, bad = v.window_arrivals(view, "ELC", "2024/25", "2023/24", crows_elc)
    assert down in rel and not bad
    crows_pl = [(x, (0.0, 0.0)) for x in rows if x.code == "PL"]
    rel, bad = v.window_arrivals(view, "PL", "2024/25", "2023/24", crows_pl)
    assert up not in rel and not bad
    assert v.arrival_class("ELC", down, [x for x in rows if x.season == "2023/24"]) == ("relegated", ["PL"])
    assert v.arrival_class("PL", up, [x for x in rows if x.season == "2023/24"]) == ("promoted", ["ELC"])
    assert v.arrival_class("PL", 10 ** 6, rows) == ("promoted", [])                   # from outside the store
    assert v.arrival_refusals(rows) == []
    cache = v.Prefix(rows)
    fx_row = next(x for x in rows if x.code == "ELC" and x.season == "2024/25" and down in (x.home_id, x.away_id))
    snap = cache.snapshot(fx_row.utc_date, PJ, "kickoff")
    side = "home_source" if fx_row.home_id == down else "away_source"
    assert v.predict(snap, v.Fixture.of(fx_row), "soccer-v23", cache)["info"][side] == "relegated prior"


def test_an_arrival_off_the_pyramid_refuses_and_is_named():
    R = lambda i, c, se, d, h, a: v.Row(i, c, se, datetime(2020 + d // 400, 9, 1) + timedelta(days=d % 400), h, a,  # noqa
                                        1, 0, "Regular Season - 1")
    rows = [R(1, "BL1", "2020/21", 0, 7, 8), R(2, "PL", "2020/21", 0, 1, 2), R(3, "PL", "2020/21", 1, 2, 1),
            R(4, "PL", "2021/22", 400, 7, 1), R(5, "PL", "2021/22", 401, 1, 7)]
    got = v.arrival_refusals(rows)
    assert len(got) == 1 and "PL 2021/22: club 7 arrives from ['BL1']" in got[0]
    with pytest.raises(v.GateRefused, match="cannot place"):
        v.walk(rows, rows[-1:], PJ, "kickoff")


def _stage_rows():
    st = ["Regular Season - 1", None, "", "Apertura - 3", "1st Phase - 2", "Regular Season - 2"]
    return [v.Row(i + 1, "XX", "2025/26", datetime(2025, 9, 1 + i), 1 + i % 2, 2 - i % 2, 1, 0, s_)
            for i, s_ in enumerate(st)]


SLOTS = {"cut": "2026-10-30T15:00:00Z", "scope": "LEAGUE_REGULAR", "first_season": "score_under_prior",
         "visibility": "day", "availability_on": False}


def test_an_unplaceable_stage_label_refuses_never_a_silent_drop():
    """Under LEAGUE_REGULAR, soccer_expansion F3's rule: NULL, empty and any unmatched label refuse (named, with their
    counts); under LEAGUE no stage rule applies."""
    rows = _stage_rows()
    with pytest.raises(v.GateRefused, match="cannot be placed") as e:
        v.scored_rows(rows, v.RECOMMENDED)
    for lab in ("None 1", "'' 1", "'Apertura - 3' 1", "'1st Phase - 2' 1"):
        assert lab in str(e.value), lab
    assert v.stage_refusals(rows, v.RECOMMENDED) == [
        "XX 2025/26: None 1, '' 1, '1st Phase - 2' 1, 'Apertura - 3' 1"]
    assert [r.id for r in v.scored_rows(rows, {**SLOTS, "scope": "LEAGUE"})] == [1, 2, 3, 4, 5, 6]
    assert v.stage_refusals(rows, {**SLOTS, "scope": "LEAGUE"}) == []


def test_the_scope_and_first_season_slots_change_the_scored_set():
    rows = [v.Row(1, "XX", "2024/25", datetime(2024, 9, 1), 1, 2, 1, 0, "Regular Season - 1"),
            v.Row(2, "XX", "2024/25", datetime(2024, 9, 8), 2, 1, 1, 1, "Regular Season - 2"),
            v.Row(3, "XX", "2025/26", datetime(2025, 9, 1), 1, 2, 2, 0, "Regular Season - 1"),
            v.Row(4, "XX", "2025/26", datetime(2026, 5, 20), 1, 2, 0, 0, "Relegation Round - 1"),
            v.Row(5, "YY", "2025/26", datetime(2025, 9, 2), 3, 4, 0, 1, "Regular Season - 1")]
    ids = lambda sl: [r.id for r in v.scored_rows(rows, {**SLOTS, **sl})]     # noqa: E731
    assert ids({"scope": "LEAGUE"}) == [1, 2, 3, 5, 4]
    assert ids({}) == [1, 2, 3, 5]                                       # the play-off round out, by cause
    assert ids({"first_season": "exclude_as_warmup"}) == [3]             # XX 2024/25 and YY 2025/26: first seasons
    cen = v.stage_census(rows)[("XX", "2025/26")]
    assert cen == {"regular": 1, "playoff": {"Relegation Round - 1": 1}, "unplaced": {}}


def test_the_fingerprint_binds_every_slot():
    rows = _stage_rows()[:1]
    base = v.stream_fingerprint(rows, rows, dict(SLOTS), V22P)[0]
    for k, alt in (("visibility", "kickoff"), ("scope", "LEAGUE"), ("first_season", "exclude_as_warmup"),
                   ("availability_on", True), ("cut", "2026-10-29T15:00:00Z")):
        assert v.stream_fingerprint(rows, rows, {**SLOTS, k: alt}, V22P)[0] != base, k


def _first_season_rows(seed: int, n_teams: int = 10):
    import numpy as np
    rng, nprng = random.Random(seed), np.random.default_rng(seed)
    pairs = [(h, a) for h in range(1, n_teams + 1) for a in range(1, n_teams + 1) if h != a]
    rng.shuffle(pairs)
    return [v.Row(j + 1, "XX", "2020/21", datetime(2020, 8, 10, 12) + timedelta(days=j // 2, hours=j % 2), h, a,
                  int(nprng.poisson(1.5 * 1.15)), int(nprng.poisson(1.5 * 0.85)), "Regular Season - 1", "FT")
            for j, (h, a) in enumerate(pairs)]


def test_a_competitions_first_season_prices_bounded_probabilities():
    """The review's degeneracy, pinned: early in a competition's first season (fewer than 15 visible rows) β's weak
    prior keeps every price bounded (no 1X2 probability above 0.95; |β| within three prior sds)."""
    from src.models import joint_poisson as jp
    worst_p, worst_b = 0.0, 0.0
    for seed in range(8):
        rows = _first_season_rows(seed)
        w = v.walk(rows, rows[:15], PJ, "day")
        for p, st in zip(w["soccer-v23"], w["strata"]):
            worst_p = max(worst_p, p["p_home"], p["p_draw"], p["p_away"])
            worst_b = max(worst_b, abs(st["beta"]))
    assert worst_p < 0.95
    assert worst_b < 3 / math.sqrt(jp.BETA_PRIOR_PRECISION) / jp.ELO_SCALE


# ------------------------------------------------------------------------- availability (243 item 4) --

def _receipt():
    spec = importlib.util.spec_from_file_location("pl_injury_classification_receipt_v23",
                                                  ROOT / "scripts" / "pl_injury_classification_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_fixture_age_categories_and_text_are_the_receipts_verbatim():
    rc = _receipt()
    assert (v.THIS, v.EARLIER, v.LATER, v.NOT_STORED, v.NO_FIX_ID, v.FIX_AMBIG) == (
        rc.THIS, rc.EARLIER, rc.LATER, rc.NOT_STORED, rc.NO_FIX_ID, rc.FIX_AMBIG)
    here = datetime(2026, 10, 25, 14)
    by_fid = {"1": [(10, here, "PL")], "2": [(11, here - timedelta(days=3, hours=5), "UEL")],
              "3": [(12, here + timedelta(days=4), "PL")], "4": [(13, here, "PL"), (14, here, "PL")]}
    by_prev = {"5": [(15, here - timedelta(days=10), "PL")]}
    db = {"match": 10, "fixture": "1", "utc": here}
    for fid in ("1", "2", "3", "4", "5", "9", None, ""):
        assert v.fixture_age(fid, 10, "1", here, by_fid, by_prev) == rc.fixture_age(fid, db, by_fid, by_prev, here)
    assert v.fixture_age("2", 10, "1", here, by_fid)[1].startswith("an earlier fixture 3.2 d before (UEL, match 11)")


class _Inj:
    def __init__(self, pos):
        self.player_position, self.player_name = pos, "x"


def test_the_term_counts_only_a_missing_fixture_entry_for_this_fixture():
    from src.models.factors import injury_adjustment
    E = lambda t, age, team=1: v.Entry(team, "x", "Attacker", t, age, age)   # noqa: E731
    assert v.classify("Missing Fixture", v.THIS)[0] is True
    for t, age in (("Missing Fixture", v.EARLIER), ("Missing Fixture", v.LATER), ("Missing Fixture", v.NOT_STORED),
                   ("Missing Fixture", v.NO_FIX_ID), ("Missing Fixture", v.FIX_AMBIG), ("Questionable", v.THIS),
                   ("Questionable", v.EARLIER), ("Suspended", v.THIS), (None, v.THIS)):
        assert v.classify(t, age)[0] is False
        assert v.availability([E(t, age)], 1, 2, True)[:2] == (1.0, 1.0)
    assert v.classify("Suspended", v.THIS)[1] == v.TYPE_NOT_RULED
    mh, ma, _ = v.availability([E("Missing Fixture", v.THIS)], 1, 2, True)
    ref = injury_adjustment(home_injuries=[_Inj("Attacker")], away_injuries=[])
    assert (mh, ma) == (ref.home_xg_multiplier, ref.away_xg_multiplier) and mh < 1.0
    assert v.availability([E("Missing Fixture", v.THIS)], 1, 2, False)[:2] == (1.0, 1.0)


def test_on_the_pot_the_multiplier_is_exactly_one_and_the_walk_stops_otherwise(store, monkeypatch):
    db, _ = store
    rows = rows_of(db)
    fx = rows[-3:]
    w = v.walk(rows, fx, v.canon_params(V22P, True), "day")
    assert len(w["soccer-v23"]) == 3
    monkeypatch.setattr(v, "availability", lambda *a, **k: (0.9, 1.0, []))
    with pytest.raises(v.GateRefused, match="never manufactured|not 1.0"):
        v.walk(rows, fx, PJ, "day")


def test_no_number_outside_the_designs_own_literals():
    """243 item 4: no figure of the 243/244 receipt becomes a parameter. Every numeric literal in the two modules is
    one the design names (an allow-list: a new number fails here and needs the bar)."""
    allowed = {"0", "1", "2", "3", "5", "10", "24", "30", "60", "100", "500", "1000", "3600", "0.0", "1.0", "1.30",
               "1.15", "1.4", "0.85", "5.0", "100.0", "2.0", "0.5", "1e-12", "1e-9", "1.0", "16", "546", "0.0050",
               "0.005", "40", "0.25", "4"}                # "4": RESULT_LAG_HOURS (a declared design constant)
    for p in ("src/models/joint_poisson.py", "src/walters/soccer_v23.py"):
        src = (ROOT / p).read_text()
        nums = {t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.NUMBER}
        assert nums <= allowed, (p, sorted(nums - allowed))


# --------------------------------------------------------------------------------------------- the gate --

def test_the_real_registry_holds_no_soccer_v23_entry_and_the_run_refuses():
    from src.walters import registry as reg
    assert reg.get(v.EID, reg.LEDGER) is None
    with pytest.raises(v.GateRefused, match="must be declared"):
        v.run("word", "fp", db="/nonexistent")
    assert not Path(v.reservation_path()).exists()


def test_a_stray_one_row_season_fits_and_a_goalless_one_is_named(store):
    """The extras' 2023/24 rows: one admitted AET row (1-1) is a one-row S−1 the fit identifies (β fixed, labelled);
    a season with no away goal is named by the preflight census, and a window of only such rows refuses the fit."""
    from src.models import joint_poisson as jp
    f = jp.fit([jp.Obs(3, 4, jp.PREV, 1.0, 1.0, 4.5)])
    assert "beta_unidentified" in f.labels
    rows = [v.Row(1, "XX", "2020/21", datetime(2020, 9, 1), 1, 2, 2, 0), v.Row(2, "XX", "2020/21", datetime(2020, 9, 2),
                                                                         2, 1, 1, 0)]
    assert v.thin_seasons(rows) == ["XX 2020/21 (2 rows: no away goal)"]
    with pytest.raises(jp.FitRefused):
        jp.fit([jp.Obs(r.home_id, r.away_id, jp.PREV, r.home_goals, r.away_goals, 0.0) for r in rows])


def test_preflight_without_a_declaration_loads_nothing():
    L = v.preflight_lines(None, None)
    assert any("NOT DECLARED" in x for x in L) and "nothing loaded" in L[-1]


def test_the_command_is_registered():
    import cli
    assert "soccer-v23-gate" in cli.cli.commands


RECORDED = {"v22_recorded_log_loss": 1.0, "v22_recorded_source": "synthetic (tests only)"}


def test_slots_state():
    rec = {"scope": "LEAGUE_REGULAR", "first_season": "score_under_prior", "visibility": "day",
           "cut": "2026-10-30T15:00:00Z", "availability_on": False}
    good = {**rec, **RECORDED}
    assert v.slots_state({v.SLOTS_KEY: good}) == (good, None)
    for k in v.SLOT_KEYS:
        assert v.slots_state({v.SLOTS_KEY: {**good, k: None}})[1]
    for k, bad in (("scope", "ALL"), ("first_season", "skip40"), ("visibility", "close"), ("cut", "soon"),
                   ("availability_on", "no"), ("v22_recorded_log_loss", True), ("v22_recorded_log_loss", "1.0"),
                   ("v22_recorded_log_loss", 0.0), ("v22_recorded_log_loss", -1.0),
                   ("v22_recorded_log_loss", float("nan")), ("v22_recorded_log_loss", float("inf")),
                   ("v22_recorded_source", ""), ("v22_recorded_source", "  "), ("v22_recorded_source", 3)):
        assert v.slots_state({v.SLOTS_KEY: {**good, k: bad}})[1], (k, bad)
    assert v.slots_state({v.SLOTS_KEY: {**good, "skip": 40}})[1]
    assert v.slots_state({v.SLOTS_KEY: rec})[1]                       # 251 item 2: v22's record is required
    assert v.slots_state({})[1] and v.RECOMMENDED == rec               # no recommendation for v22's record
    assert set(v.UNRECOMMENDED) == set(RECORDED) == set(v.SLOT_KEYS) - set(v.RECOMMENDED)


def test_constants_and_bar_state():
    e = {"frozen_constants": v.code_constants(), "gate": v.BAR_TEXT}
    assert v.constants_state(e) is None and v.bar_state(e) is None
    assert v.constants_state({"frozen_constants": {**v.code_constants(), "K_PRIOR": 4.0}})
    assert v.constants_state({"frozen_constants": {k: x for k, x in v.code_constants().items() if k != "TOL"}})
    assert v.bar_state({"gate": v.BAR_TEXT + " "})


@pytest.mark.parametrize("delta, want", [(0.0, "REJECT"), (0.0049999, "REJECT"), (0.0050, "PASS")])
def test_the_bars_named_function_at_the_bar(delta, want):
    """BAR_TEXT names soccer_backtest.candidate_gate_verdict with training.DEFAULT_PROMOTION_DELTA; the run's own path
    is pinned below (test_the_run_decides_at_the_bar)."""
    from src.walters.soccer_backtest import candidate_gate_verdict
    from src.walters.training import DEFAULT_PROMOTION_DELTA
    assert DEFAULT_PROMOTION_DELTA == 0.005
    got, d = candidate_gate_verdict(delta, 0.0, DEFAULT_PROMOTION_DELTA)
    assert got == want and d == delta
    assert not hasattr(v, "verdict")                                   # no second, unused decision path


def _backup(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    a.backup(b)
    b.close()
    a.close()
    return dst


@pytest.fixture
def declared(tmp_path, monkeypatch):
    """A tmp copy of the real registry with a synthetic soccer-v23 entry; the reservation to tmp; a synthetic store
    with a v22 production row, and its .backup copy."""
    from src.walters import registry as reg
    p = tmp_path / "experiments.json"
    entries = json.loads((ROOT / "docs" / "registry" / "experiments.json").read_text())
    slots = {**v.RECOMMENDED, **RECORDED}
    entries.append({"id": v.EID, "status": "declared", "run": None, "verdict": None,
                    "test_set": "synthetic (tests only)", "gate": v.BAR_TEXT, "frozen_constants": v.code_constants(),
                    v.SLOTS_KEY: slots})
    p.write_text(json.dumps(entries, indent=2) + "\n")
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(v, "RESERVATION", str(tmp_path / f"{v.EID}.started.json"))
    db = fresh(tmp_path / "store.db", monkeypatch)
    build(db, seasons=SEASONS[1:], n_teams=6, extras=False)
    from src.db.schema import ModelVersion, Sport
    with db.session_scope() as s:
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v22", status="production",
                           parameters={"poisson": dict(V22P)}, train_size=0))
    copy = str(_backup(tmp_path / "store.db", tmp_path / "copies" / "copy.db"))
    return {"ledger": p, "copy": copy, "tmp": tmp_path}


def _fp(lines):
    assert lines[-1].startswith("STREAM FINGERPRINT ")
    return lines[-1].split()[2]


def test_preflight_fits_nothing_and_ends_with_the_fingerprint(declared, monkeypatch):
    from src.models import joint_poisson as jp
    from src.walters import registry as reg
    monkeypatch.setattr(jp, "fit", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fitted")))
    monkeypatch.setattr(v, "predict", lambda *a, **k: (_ for _ in ()).throw(AssertionError("priced")))
    L = v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"])
    assert any("fences at the cut: clear" in x for x in L) and any("'v22'" in x for x in L)
    assert any(v.CONTEXT_DEFINITION in x for x in L)
    assert any("v22's recorded figure" in x and "1.0 from 'synthetic (tests only)'" in x for x in L)
    assert len(_fp(L)) == 64 and not Path(v.reservation_path()).exists()


def _nothing(declared):
    from src.walters import registry as reg
    assert not Path(v.reservation_path()).exists() and reg.get(v.EID, reg.LEDGER)["run"] is None


def test_the_run_refuses_in_order_and_records_nothing(declared, monkeypatch):
    from src.walters import registry as reg
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))
    with pytest.raises(v.GateRefused, match="architect's word"):
        v.run("", fp, db=declared["copy"])
    with pytest.raises(v.GateRefused, match="--db"):
        v.run("w", fp, db=None)
    with pytest.raises(v.GateRefused, match="fingerprint"):
        v.run("w", "0" * 64, db=declared["copy"])
    entries = json.loads(declared["ledger"].read_text())
    e = next(x for x in entries if x["id"] == v.EID)
    e[v.SLOTS_KEY]["cut"] = "2026-11-03T00:00:00Z"                     # past the pl-availability window's opening
    declared["ledger"].write_text(json.dumps(entries))
    with pytest.raises(v.GateRefused, match="fence"):
        v.run("w", fp, db=declared["copy"])
    e[v.SLOTS_KEY]["cut"] = None
    declared["ledger"].write_text(json.dumps(entries))
    with pytest.raises(v.GateRefused, match="null"):
        v.run("w", fp, db=declared["copy"])
    e[v.SLOTS_KEY]["cut"] = v.RECOMMENDED["cut"]
    e[v.SLOTS_KEY]["v22_recorded_log_loss"] = None                     # 251 item 2: v22's record not yet filled
    declared["ledger"].write_text(json.dumps(entries))
    with pytest.raises(v.GateRefused, match="v22_recorded_log_loss.*null"):
        v.run("w", fp, db=declared["copy"])
    _nothing(declared)


def test_the_run_refuses_a_copy_whose_production_is_not_v22(declared, monkeypatch):
    from src.walters import registry as reg
    monkeypatch.setattr(v, "production_params", lambda s: ("v23", dict(V22P)))
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))
    with pytest.raises(v.GateRefused, match="not 'v22'"):
        v.run("w", fp, db=declared["copy"])
    _nothing(declared)


def test_the_one_run_reserves_before_any_outcome_then_records_once(declared, monkeypatch):
    from src.walters import registry as reg
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))
    seen = []
    real_walk = v.walk

    def spy(*a, **k):
        seen.append(Path(v.reservation_path()).exists())
        return real_walk(*a, **k)
    monkeypatch.setattr(v, "walk", spy)
    r = v.run("ARCHITECT test word", fp, db=declared["copy"])
    assert seen == [True]
    res = json.loads(Path(v.reservation_path()).read_text())
    assert res["architect_word"] == "ARCHITECT test word" and res["stream_fingerprint"] == fp
    assert r["compare"]["verdict"] in ("PASS", "REJECT") and r["compare"]["n"] == len(r["scored_ids"])
    assert any("VERDICT" in x for x in v.run_lines(r))
    e = v.record(r, "ARCHITECT test word")
    assert e["status"] == "run" and e["run"]["n_scored"] == len(r["scored_ids"])
    assert e["run"]["result"]["availability"] == v.availability_lines(r["walk"]["availability"])
    assert len(e["run"]["result"]["availability"]) >= 2               # the header and one era at least
    with pytest.raises(v.GateRefused):
        v.run("again", fp, db=declared["copy"])


def _arm(ids, q):
    return [{"match_id": i, "p_home": q, "p_draw": (1 - q) / 2, "p_away": (1 - q) / 2, "actual": "H"} for i in ids]


def _delta(ids, q):
    from src.walters.soccer_backtest import soccer_calibration
    return soccer_calibration(_arm(ids, q))["log_loss"] - soccer_calibration(_arm(ids, 0.5))["log_loss"]


def _q_rewalked(ids, d):
    """The v22 arm's probability q giving the re-walked difference `d` against soccer-v23's 0.5 (both by
    soccer_calibration): a number, "edge" (the smallest float difference at or above 0.0050 that q's float steps
    reach) or "under" (one float step of q below it)."""
    if not isinstance(d, str):
        return 0.5 * math.exp(-d)
    q = 0.5 * math.exp(-0.005)
    while _delta(ids, q) < 0.005:
        q = math.nextafter(q, 0.0)
    while _delta(ids, math.nextafter(q, 1.0)) >= 0.005:
        q = math.nextafter(q, 1.0)
    return q if d == "edge" else math.nextafter(q, 1.0)


def _recorded(v23_ll, d):
    """v22's recorded figure giving the recorded difference `d` against soccer-v23's log-loss: a number, "edge" (the
    smallest float with a difference at or above 0.0050) or "under" (the float just below it)."""
    if not isinstance(d, str):
        return v23_ll + d
    r = v23_ll + 0.005
    while r - v23_ll < 0.005:
        r = math.nextafter(r, math.inf)
    while math.nextafter(r, -math.inf) - v23_ll >= 0.005:
        r = math.nextafter(r, -math.inf)
    return r if d == "edge" else math.nextafter(r, -math.inf)


BAR_CASES = [  # (case, re-walked difference, recorded difference, verdict)
    ("below both by 0.0100", 0.01, 0.01, "PASS"),
    ("at the bar on both", "edge", "edge", "PASS"),
    ("below recorded, a tie on the re-walk", 0.0, 0.01, "REJECT"),
    ("below the re-walk, 0.0049999 from recorded", 0.01, 0.0049999, "REJECT"),
    ("a tie on recorded", 0.01, 0.0, "REJECT"),
    ("one float step under on the re-walk", "under", 0.01, "REJECT"),
    ("one float step under on recorded", 0.01, "under", "REJECT"),
]


def _set_slots(declared, **kw):
    entries = json.loads(declared["ledger"].read_text())
    e = next(x for x in entries if x["id"] == v.EID)
    e[v.SLOTS_KEY].update(kw)
    declared["ledger"].write_text(json.dumps(entries))
    return e[v.SLOTS_KEY]


@pytest.mark.parametrize("case, d_rw, d_rec, want", BAR_CASES, ids=[c[0] for c in BAR_CASES])
def test_the_run_decides_at_the_bar(declared, monkeypatch, case, d_rw, d_rec, want):
    """THE BAR's decision ON THE RUN PATH (251 item 2): run() itself, the walk replaced by synthetic arms (v22
    re-walked at q, soccer-v23 at 0.5) and v22's recorded figure set in its declaration slot, at each side of each
    comparison: PASS only when soccer-v23 is at least 0.0050 below BOTH; a tie, 0.0049999 or one float step under on
    EITHER rejects. The log-losses are soccer_calibration's; the min_delta run passes is DEFAULT_PROMOTION_DELTA."""
    from src.walters import registry as reg
    from src.walters.soccer_backtest import soccer_calibration
    from src.walters.training import DEFAULT_PROMOTION_DELTA
    _, _, _, rows, record = v._load(declared["copy"], reg.get(v.EID, reg.LEDGER)[v.SLOTS_KEY])
    assert record.at(rows[-1].utc_date).state == v.NO_RECORD           # no availability tables on the copy
    ids = [r.id for r in v.scored_rows(rows, reg.get(v.EID, reg.LEDGER)[v.SLOTS_KEY])]
    v23_ll = soccer_calibration(_arm(ids, 0.5))["log_loss"]
    q, recorded = _q_rewalked(ids, d_rw), _recorded(v23_ll, d_rec)
    _set_slots(declared, v22_recorded_log_loss=recorded, v22_recorded_source="synthetic record (tests only)")
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))

    def fake_walk(rows_, fixtures, params_json, rule, use_cache=True, record=v.ROWS_ONLY):
        assert [r.id for r in fixtures] == ids and record.at(fixtures[0].utc_date).reason == v.ABSENT_REASON
        return {"v22": _arm(ids, q), "soccer-v23": _arm(ids, 0.5), "strata": [], "context": [], "availability": []}
    monkeypatch.setattr(v, "walk", fake_walk)
    r = v.run("ARCHITECT test word", fp, db=declared["copy"])
    c = r["compare"]
    assert c["min_delta"] == DEFAULT_PROMOTION_DELTA == 0.005 and c["n"] >= 30
    assert c["v23_log_loss"] == v23_ll == c["cand_log_loss"]
    assert c["v22_rewalked_log_loss"] == soccer_calibration(_arm(ids, q))["log_loss"] == c["prod_log_loss"]
    assert c["v22_recorded_log_loss"] == recorded and c["v22_recorded_source"] == "synthetic record (tests only)"
    assert c["delta_rewalked"] == c["v22_rewalked_log_loss"] - v23_ll and c["delta_recorded"] == recorded - v23_ll
    assert c["verdict_rewalked"] == ("PASS" if c["delta_rewalked"] >= 0.005 else "REJECT")
    assert c["verdict_recorded"] == ("PASS" if c["delta_recorded"] >= 0.005 else "REJECT")
    assert c["verdict"] == want
    if d_rw == 0.0:
        assert c["delta_rewalked"] == 0.0
    if d_rec == 0.0:
        assert c["delta_recorded"] == 0.0
    for d, key in ((d_rw, "delta_rewalked"), (d_rec, "delta_recorded")):
        if isinstance(d, str):                                         # one float step from the bar
            assert abs(c[key] - 0.005) < 1e-14 and (c[key] >= 0.005) == (d == "edge")
    text = "\n".join(v.run_lines(r))
    assert "against v22 RE-WALKED on this harness" in text and "against v22 RECORDED (synthetic record" in text
    e = v.record(r, "ARCHITECT test word")
    res = e["run"]["result"]
    assert (res["v23_log_loss"], res["v22_rewalked_log_loss"], res["v22_recorded_log_loss"]) == (
        v23_ll, c["v22_rewalked_log_loss"], recorded) and res["verdict"] == want


def _cmp(prod, cand, n=40):
    from src.walters.soccer_backtest import candidate_gate_verdict
    vv, d = candidate_gate_verdict(prod, cand, 0.005)
    return {"verdict": vv, "delta": d, "min_delta": 0.005, "n": n, "prod_log_loss": prod, "cand_log_loss": cand,
            "prod_rps": 0.2, "cand_rps": 0.2, "prod_brier": 0.6, "cand_brier": 0.6}


@pytest.mark.parametrize("case, d_rw, d_rec, want", BAR_CASES, ids=[c[0] for c in BAR_CASES])
def test_decide_at_the_bar(case, d_rw, d_rec, want):
    """decide itself (the only decision path) on plain figures, soccer-v23 at 1.0: the same cases."""
    from src.walters.training import DEFAULT_PROMOTION_DELTA
    cand = 1.0

    def fig(d):
        return _recorded(cand, d)
    got = v.decide(_cmp(fig(d_rw), cand), fig(d_rec), "a record", DEFAULT_PROMOTION_DELTA)
    assert got["verdict"] == want
    assert (got["v22_rewalked_log_loss"], got["v22_recorded_log_loss"], got["v23_log_loss"]) == (fig(d_rw),
                                                                                                fig(d_rec), cand)


def test_an_invalid_comparison_stays_invalid_whatever_the_record(declared, monkeypatch):
    """Differing scored sets: INVALID, never a pass, even with v22's recorded figure far above soccer-v23's."""
    from src.walters import registry as reg
    _set_slots(declared, v22_recorded_log_loss=9.0)
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))

    real_walk = v.walk

    def fake_walk(rows_, fixtures, params_json, rule, use_cache=True, record=v.ROWS_ONLY):
        w = real_walk(rows_, fixtures, params_json, rule, use_cache=use_cache, record=record)   # the real walk ...
        ids = [r.id for r in fixtures]
        return {**w, "v22": _arm(ids, 0.4), "soccer-v23": _arm(ids[1:], 0.5)}   # ... its arms' sets made to differ
    monkeypatch.setattr(v, "walk", fake_walk)
    r = v.run("ARCHITECT test word", fp, db=declared["copy"])
    c = r["compare"]
    assert c["verdict"] == "INVALID" and c["v22_recorded_log_loss"] == 9.0
    # 253 item 2(d): the per-era availability line is printed on an INVALID verdict too (the review: it was dropped)
    lines = v.run_lines(r)
    era = v.availability_lines(r["walk"]["availability"])
    assert len(era) >= 2 and era[0] in lines and all(x in lines for x in era[1:])
    assert any(x.startswith("    PL ") and "term off: the slot availability_on is false" in x for x in lines)
    assert lines[-1].startswith("  VERDICT (computed; the architect rules): INVALID")
    assert v.decide({"verdict": "INVALID", "n": 0, "reason": "empty"}, 9.0, "r", 0.005)["verdict"] == "INVALID"


def test_an_unplaceable_stage_refuses_the_run_and_is_named_in_the_preflight(declared):
    """A NULL and an unmatched stage label on the copy: the preflight names both (with counts) and gives no
    fingerprint; the run refuses before the fingerprint and the reservation."""
    from src.walters import registry as reg
    con = sqlite3.connect(str(declared["tmp"] / "store.db"))
    ids = [r[0] for r in con.execute("SELECT id FROM matches WHERE home_score IS NOT NULL ORDER BY id LIMIT 2")]
    assert len(ids) == 2
    con.execute("UPDATE matches SET stage = NULL WHERE id = ?", (ids[0],))
    con.execute("UPDATE matches SET stage = 'Apertura - 3' WHERE id = ?", (ids[1],))
    con.commit()
    con.close()
    copy = str(_backup(declared["tmp"] / "store.db", declared["tmp"] / "copies" / "copy_stage.db"))
    L = v.preflight_lines(reg.get(v.EID, reg.LEDGER), copy)
    text = "\n".join(L)
    assert "CANNOT BE PLACED" in text and "None 1" in text and "'Apertura - 3' 1" in text
    assert not any(x.startswith("STREAM FINGERPRINT") for x in L) and "NO fingerprint" in L[-1]
    with pytest.raises(v.GateRefused, match="stage label cannot be placed"):
        v.run("w", "0" * 64, db=copy)
    _nothing(declared)


def test_a_failure_after_the_reservation_leaves_it_standing(declared, monkeypatch):
    from src.walters import registry as reg
    fp = _fp(v.preflight_lines(reg.get(v.EID, reg.LEDGER), declared["copy"]))
    monkeypatch.setattr(v, "walk", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("mid-walk")))
    with pytest.raises(RuntimeError):
        v.run("w", fp, db=declared["copy"])
    assert Path(v.reservation_path()).exists()                         # open question 13: kept, conservatively
