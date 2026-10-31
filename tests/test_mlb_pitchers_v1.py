"""mlb-pitchers-v1 (ARCHITECT 2026-10-31 11:45 ET, addendum 190; lane mlb-pitchers, #507): the harness, on synthetic
rows only. Throwaway SQLite files (tests/conftest.py's DATABASE_URL, or files under tmp_path); never data/, never the
real ledger (a tmp copy of docs/registry/experiments.json; the ids and the reservation in tmp).

  - OFF unchanged: run_backtest()'s default output equals a verbatim copy of the pre-change walk (`_ref_walk`), and
    the pitcher layer's p_home_off equals that walk's home probability per match id.
  - ON equals live: the ON arm's PitcherStats and p_home equal the live _generate_predictions_mlb's on a DB whose
    pitcher_season_stats / bullpen_season_stats rows equal the as-of sums.
  - The classification equals the receipt's; the cohort is the both-sides-on-a-path games.
  - The fence; the freeze and the run's refusals; INVALID; the verdict arithmetic; the entry.
"""
import hashlib
import importlib.util
import json
import math
import os
import sqlite3
from collections import Counter
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.db.database import init_db, session_scope
from src.db.schema import (Base, BullpenSeasonStats, Competition, Match, MatchParticipant, MatchStatus, ModelVersion,
                           PitcherAppearance, PitcherSeasonStats, Prediction, Sport, Team)
from src.models.baseball import BaseballConfig, PitcherStats, estimate_run_profiles, predict_game
from src.walters import backtest as bt
from src.walters import mlb_pitcher_asof as asof
from src.walters import mlb_pitchers_gate as mp
from src.walters import ncaa_backtest as nb
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parents[1]
SRC = asof.SOURCE


# ===================================================================================================== OFF unchanged --

def _ref_walk(season="2025", competition_code="MLB", shrink_frac_override=None, scope=None, pitchers=None, ons=None):
    """TODAY'S WALK, verbatim (src/walters/backtest.py run_backtest at origin/main 78566ff5, after its fences),
    extended only to carry m.id and p_home (`homes`), to take the session scope (default session_scope), and, given
    `pitchers` {match id: (home PitcherStats, away PitcherStats)}, to append the independent ON reference
    (m.id, the live shrink of predict_game(hp, ap, home_pitcher=home, away_pitcher=away)) to `ons`."""
    from src.walters.backtest import _load_production_config
    from src.db.schema import Match, MatchStatus, Competition
    results = []
    totals_rows = []  # richer rows for the totals-model head-to-head
    homes = []        # (m.id, pred.p_home): the extension
    with (scope or session_scope)() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return None
        cfg = _load_production_config(s)
        if shrink_frac_override is not None:
            import dataclasses
            cfg = dataclasses.replace(cfg, run_shrink_enabled=True,
                                      run_shrink_frac=shrink_frac_override)

        games = list(s.execute(
            select(Match).where(
                Match.competition_id == comp.id,
                Match.season == season,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
            ).order_by(Match.utc_date.asc())
        ).scalars())

        if not games:
            return None

        # incremental history: list of prior-game dicts, grown as we advance
        history: list[dict] = []
        # we must not leak SAME-DAY games either; process strictly by date, and
        # only add a game to history after it's been predicted.
        for m in games:
            # build profiles from history so far (games strictly before this one)
            if len(history) >= 40:  # need a minimum base to be meaningful
                profiles = estimate_run_profiles(history)
                hp = profiles.get(m.home_team_id)
                ap = profiles.get(m.away_team_id)
                if hp and ap:
                    pred = predict_game(hp, ap, home_pitcher=None,
                                        away_pitcher=None, config=cfg)
                    probs = {"home": pred.p_home, "away": pred.p_away}
                    side = max(probs, key=probs.get)
                    p = probs[side]
                    actual_home_won = m.home_score > m.away_score
                    won = 1 if ((side == "home") == actual_home_won) else 0
                    # projected total (home_xr+away_xr) vs actual — for the
                    # totals-bias confirmation (no market line needed; the
                    # projection-band bias read doesn't use one).
                    proj_total = (pred.home_xr or 0) + (pred.away_xr or 0)
                    actual_total = m.home_score + m.away_score
                    results.append((p, won, proj_total, actual_total))
                    homes.append((m.id, pred.p_home))
                    if pitchers is not None and m.id in pitchers:            # the extension: the ON reference
                        h_ps, a_ps = pitchers[m.id]
                        p_on = predict_game(hp, ap, home_pitcher=h_ps, away_pitcher=a_ps, config=cfg)
                        ons.append((m.id, asof.missing_starter_shrink(p_on.p_home, p_on.p_away, h_ps, a_ps)[0]))
                    # richer row for the totals-model head-to-head (leakage-free:
                    # run rates are point-in-time from prior games only)
                    totals_rows.append((
                        p, won, proj_total, actual_total,
                        hp.runs_scored_per_game, hp.runs_allowed_per_game,
                        ap.runs_scored_per_game, ap.runs_allowed_per_game,
                        cfg.league_runs_per_game, m.venue,
                    ))
            # now add this game to history for future predictions
            history.append({
                "home_team_id": m.home_team_id, "away_team_id": m.away_team_id,
                "home_score": m.home_score, "away_score": m.away_score,
                "utc_date": m.utc_date,
            })

    return results, totals_rows, homes


OFF_COMP, OFF_SEASON = "MLBPH", "2091"


def _off_season(s, comp_code=OFF_COMP, season=OFF_SEASON):
    """A synthetic season: 6 teams, 66 finished games (pairs at a shared kickoff, a tie, a postseason game, a game
    without scores, a scheduled game). Returns the finished game ids in kickoff order."""
    comp = s.execute(select(Competition).where(Competition.code == comp_code)).scalar_one_or_none()
    if comp is not None:
        return [m.id for m in s.execute(select(Match).where(Match.competition_id == comp.id,
                                                            Match.status == MatchStatus.FINISHED)
                                        .order_by(Match.utc_date, Match.id)).scalars()]
    comp = Competition(sport=Sport.MLB, code=comp_code, name=comp_code, area="US", type="LEAGUE")
    s.add(comp)
    s.flush()
    teams = [Team(sport=Sport.MLB, name=f"{comp_code} T{i}") for i in range(6)]
    s.add_all(teams)
    s.flush()
    t0 = datetime(int(season), 4, 1, 17, 5)
    ids = []
    for k in range(66):
        h, a = k % 6, (k + 1 + k // 6) % 6
        if h == a:
            a = (a + 1) % 6
        at = t0 + timedelta(hours=4 * (k // 2))           # two games share each kickoff
        hs, as_ = 1 + (k * 7) % 6, 1 + (k * 5) % 5
        if k == 50:
            hs = as_ = 4                                   # a tie (an away win in today's walk)
        m = Match(sport=Sport.MLB, competition_id=comp.id, season=season, utc_date=at, status=MatchStatus.FINISHED,
                  stage="F" if k == 65 else "R", home_team_id=teams[h].id, away_team_id=teams[a].id,
                  home_score=hs, away_score=as_)
        s.add(m)
        s.flush()
        ids.append(m.id)
    s.add(Match(sport=Sport.MLB, competition_id=comp.id, season=season, utc_date=t0 + timedelta(days=60),
                status=MatchStatus.FINISHED, stage="R", home_team_id=teams[0].id, away_team_id=teams[1].id))
    s.add(Match(sport=Sport.MLB, competition_id=comp.id, season=season, utc_date=t0 + timedelta(days=61),
                status=MatchStatus.SCHEDULED, stage="R", home_team_id=teams[2].id, away_team_id=teams[3].id))
    return ids


@pytest.fixture
def off_db():
    init_db()
    with session_scope() as s:
        return _off_season(s)


def test_off_default_output_is_byte_identical_to_todays_walk(off_db):
    res, tot, homes = _ref_walk(OFF_SEASON, OFF_COMP)
    assert len(res) == 66 - 40 and len(homes) == len(res)
    assert bt.run_backtest(season=OFF_SEASON, competition_code=OFF_COMP) == res
    assert bt.run_backtest(season=OFF_SEASON, competition_code=OFF_COMP, return_totals_rows=True) == tot
    res2, tot2, _ = _ref_walk(OFF_SEASON, OFF_COMP, shrink_frac_override=0.3)
    assert bt.run_backtest(season=OFF_SEASON, competition_code=OFF_COMP, shrink_frac_override=0.3) == res2
    assert repr(bt.run_backtest(season=OFF_SEASON, competition_code=OFF_COMP)) == repr(res)
    assert bt.run_backtest(season="1999", competition_code=OFF_COMP) is None
    assert bt.run_backtest(season=OFF_SEASON, competition_code="NO-SUCH") is None


def test_the_pitcher_layer_rows_carry_todays_home_probability_per_match_id(off_db):
    _, _, homes = _ref_walk(OFF_SEASON, OFF_COMP)
    ref = dict(homes)
    neutral = (PitcherStats("h", None, True), PitcherStats("a", None, True))       # multiplier 1, no shrink
    unknown = (PitcherStats("h", None, False), PitcherStats("a", None, False))     # both missing: 0.76
    warm = off_db[:5]                                                              # in the 40-game warm-up
    inputs = {mid: (neutral if i % 2 else unknown) for i, mid in enumerate(off_db[38:])}
    inputs.update({mid: neutral for mid in warm})
    rows = bt.run_backtest(season=OFF_SEASON, competition_code=OFF_COMP, pitcher_layer=True, pitcher_inputs=inputs)
    assert [r[0] for r in rows] == [mid for mid, _ in homes if mid in inputs]        # walk order, priced games only
    assert not set(warm) & {r[0] for r in rows}
    with session_scope() as s:
        ms = {m.id: m for m in s.execute(select(Match).where(Match.id.in_([r[0] for r in rows]))).scalars()}
        for mid, at, won, p_off, p_on in rows:
            assert p_off == ref[mid]
            assert at == ms[mid].utc_date and won == (ms[mid].home_score > ms[mid].away_score)
            if inputs[mid] is neutral:
                assert p_on == p_off
            else:
                ph, pa = 0.5 + (p_off - 0.5) * 0.76, 0.5 + ((1 - p_off) - 0.5) * 0.76
                assert p_on == pytest.approx(ph / (ph + pa), abs=1e-15)
    tie = [r for r in rows if ms[r[0]].home_score == ms[r[0]].away_score]
    assert tie and tie[0][2] is False                                              # a tie is not a home win
    # the default output is untouched by the flag's existence
    assert bt.run_backtest(season=OFF_SEASON, competition_code=OFF_COMP) == _ref_walk(OFF_SEASON, OFF_COMP)[0]


def test_the_walk_runs_on_a_given_read_only_session_with_the_copys_production_config(tmp_path, monkeypatch):
    p = tmp_path / "copy.db"
    eng = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        ids = _off_season(s, "MLB", "2026")
        s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_pythag_negbin", version="v2", status="production",
                           parameters={"baseball_config": {"run_shrink_enabled": True, "pitcher_damping": 0.5}}))
        s.commit()
    eng.dispose()
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    with mp.readonly_session(p) as s:
        assert bt._load_production_config(s).run_shrink_enabled is True
        res, _, homes = _ref_walk("2026", "MLB", scope=lambda: nullcontext(s))
        assert bt.run_backtest(season="2026", competition_code="MLB", session=s) == res
        inputs = {mid: (PitcherStats("h", 3.1, True), PitcherStats("a", None, False)) for mid in ids}
        held = tmp_path / "held.started.json"                   # the sealed read stands only on a reservation
        held.write_text("{}")
        monkeypatch.setattr(mp, "RESERVATION", str(held))
        rows = bt.run_backtest(season="2026", competition_code="MLB", pitcher_layer=True, pitcher_inputs=inputs,
                               session=s, sealed_read=True)
    assert [(r[0], r[3]) for r in rows] == homes and all(r[3] != r[4] for r in rows)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before                    # read-only: the copy is untouched


# ===================================================================================================== ON equals live --

LV_COMP, LV_SEASON = "MLBLV", "2094"
# the as-of sums per starter (outs, er, gs) and per team (season (outs, er), recent window (outs, er))
STARTERS = {"pA": (90, 12, 5), "pB": (12, 2, 0), "pD": (25, 7, 2), "pE": (40, 5, 1)}      # pB: an opener (GS 0)
BULLPENS = {0: ((150, 20), (30, 6)),        # the recent window at exactly 10 IP: weighted
            1: ((120, 15), (29, 3)),        # just under 10 IP: not weighted
            3: ((90, 10), None), 5: ((60, 9), None)}            # teams 2 and 4: no bullpen row
# (home team, home starter, away team, away starter); None = listed without a source id; "pC" = no prior appearance
LV_GAMES = [(0, "pA", 1, "pE"),            # blend with the recent window / blend, window just under, eff-IP capped
            (2, "pA", 3, "pB"),            # starter + league bullpen / opener: half-weighted bullpen
            (5, "pC", 4, "pC"),            # no-prior starter: half-weighted / neither: neutral (era None)
            (3, None, 2, "pD"),            # no source id: half-weighted / starter + league bullpen
            (4, "pE", 0, "pB")]            # starter + league bullpen / opener with the recent-window bullpen
CONFIGS = {"mlbpv1-default": {},
           "mlbpv1-variant": {"starter_eff_ip_enabled": True, "pitcher_anchor_mode": "league", "pitcher_damping": 0.5,
                              "league_era": 4.0, "run_shrink_enabled": True}}


def _side(team, psid):
    bp = BULLPENS.get(team)
    return {"name": psid or "", "starter": STARTERS.get(psid) if psid else None,
            "bullpen": bp[0] if bp else None, "recent": bp[1] if bp else None}


def _live_db():
    """The live path's DB: the stored rows equal the as-of sums (era = 27 er / outs, IP = outs / 3; the bullpen's
    recent_era only from 10 IP, as sync_bullpen_stats stores it). No odds, no venue (park factor 1), no blend."""
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == LV_COMP)).scalar_one_or_none()
        if comp is not None:
            return [m.id for m in s.execute(select(Match).where(Match.competition_id == comp.id,
                                                                Match.status == MatchStatus.SCHEDULED)
                                            .order_by(Match.utc_date)).scalars()]
        comp = Competition(sport=Sport.MLB, code=LV_COMP, name=LV_COMP, area="US", type="LEAGUE")
        s.add(comp)
        s.flush()
        teams = [Team(sport=Sport.MLB, name=f"{LV_COMP} T{i}") for i in range(6)]
        s.add_all(teams)
        s.flush()
        t0 = datetime(2094, 5, 1, 23, 5)
        for k in range(36):
            h, a = k % 6, (k + 1 + k // 6) % 6
            if h == a:
                a = (a + 1) % 6
            s.add(Match(sport=Sport.MLB, competition_id=comp.id, season=LV_SEASON, utc_date=t0 + timedelta(days=k),
                        status=MatchStatus.FINISHED, home_team_id=teams[h].id, away_team_id=teams[a].id,
                        home_score=1 + (k * 7) % 7, away_score=1 + (k * 3) % 5))
        out = []
        for i, (h, hp, a, ap) in enumerate(LV_GAMES):
            m = Match(sport=Sport.MLB, competition_id=comp.id, season=LV_SEASON,
                      utc_date=t0 + timedelta(days=40, hours=i), status=MatchStatus.SCHEDULED,
                      home_team_id=teams[h].id, away_team_id=teams[a].id)
            s.add(m)
            s.flush()
            out.append(m.id)
            for team, psid in ((teams[h], hp), (teams[a], ap)):
                s.add(MatchParticipant(match_id=m.id, team_id=team.id, role="starting_pitcher", kind="confirmed",
                                       player_source_id=psid, player_name=psid or "unknown"))
        for psid, (outs, er, gs) in STARTERS.items():
            s.add(PitcherSeasonStats(player_source_id=psid, player_name=psid, season=LV_SEASON, games_started=gs,
                                     innings_pitched=outs / 3, earned_runs=er, era=27 * er / outs))
        for t, ((outs, er), rc) in BULLPENS.items():
            rec = rc if rc and rc[0] / 3 >= asof.RECENT_MIN_IP else None
            s.add(BullpenSeasonStats(team_id=teams[t].id, season=LV_SEASON, innings_pitched=outs / 3, earned_runs=er,
                                     era=27 * er / outs, recent_era=27 * rec[1] / rec[0] if rec else None,
                                     recent_innings_pitched=rc[0] / 3 if rc else None))
        for v, c in CONFIGS.items():
            s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_pythag_negbin", version=v, status="candidate",
                               parameters={"baseball_config": c}))
    return out


@pytest.mark.parametrize("version", sorted(CONFIGS))
def test_the_on_arm_equals_the_live_path_on_rows_equal_to_the_as_of_sums(version, monkeypatch):
    import src.models.baseball as bb
    from src.walters.training import _generate_predictions_mlb

    ids = _live_db()
    calls = []
    real = bb.predict_game

    def spy(**kw):
        calls.append(kw)
        return real(**kw)
    monkeypatch.setattr(bb, "predict_game", spy)
    _generate_predictions_mlb(LV_COMP, LV_SEASON, model_version=version)
    monkeypatch.setattr(bb, "predict_game", real)
    assert len(calls) == len(LV_GAMES)
    cfg = BaseballConfig(**CONFIGS[version])
    paths = Counter()
    with session_scope() as s:
        for mid, (h, hp, a, ap), kw in zip(ids, LV_GAMES, calls):
            assert kw["config"] == cfg and kw["market_total_line"] is None
            assert kw["factor_adjustment"].home_xg_multiplier == 1.0 == kw["factor_adjustment"].away_xg_multiplier
            home_on, away_on = asof.pitcher_stats_asof(_side(h, hp), cfg), asof.pitcher_stats_asof(_side(a, ap), cfg)
            for live, on in ((kw["home_pitcher"], home_on), (kw["away_pitcher"], away_on)):
                assert (live.era, live.starter_known) == (on.era, on.starter_known)
                paths[("blend" if on.starter_known and on.era is not None else "half/neutral" if not on.starter_known
                       else "?")] += 1
            pred = real(kw["home_profile"], kw["away_profile"], home_on, away_on, cfg)
            p_on, _ = asof.missing_starter_shrink(pred.p_home, pred.p_away, home_on, away_on)
            row = s.execute(select(Prediction).where(Prediction.match_id == mid)).scalar_one()
            assert row.home_win_prob == p_on                                       # exact: the ON arm IS the live path
    assert paths["blend"] == 5 and paths["half/neutral"] == 5


def test_the_constructed_sides_cover_every_branch_of_the_live_construction():
    cfg = BaseballConfig()
    full = asof.pitcher_stats_asof(_side(0, "pA"), cfg)
    no_recent = asof.pitcher_stats_asof({**_side(0, "pA"), "recent": None}, cfg)
    assert full.starter_known and full.era != no_recent.era                        # the 10.0 IP window is weighted
    under = asof.pitcher_stats_asof(_side(1, "pA"), cfg)
    assert under.era == asof.pitcher_stats_asof({**_side(1, "pA"), "recent": None}, cfg).era    # 9.67 IP: not
    assert asof.pitcher_stats_asof(_side(2, "pA"), cfg).starter_known                         # starter + league pen
    opener = asof.pitcher_stats_asof(_side(3, "pB"), cfg)
    assert not opener.starter_known and opener.era is not None                     # GS 0: half-weighted bullpen
    neutral = asof.pitcher_stats_asof(_side(4, "pC"), cfg)
    assert (neutral.era, neutral.starter_known) == (None, False)
    capped = BaseballConfig(starter_eff_ip_enabled=True)
    assert (asof.pitcher_stats_asof(_side(1, "pE"), capped).era != asof.pitcher_stats_asof(_side(1, "pE"), cfg).era)
    # the shrink: none missing unchanged; one 0.88; two 0.76; renormalised
    k = PitcherStats("k", 3.0, True)
    u = PitcherStats("u", None, False)
    assert asof.missing_starter_shrink(0.6, 0.4, k, k) == (0.6, 0.4)
    assert asof.missing_starter_shrink(0.6, 0.4, k, u)[0] == pytest.approx(0.5 + 0.1 * 0.88)
    assert asof.missing_starter_shrink(0.6, 0.4, None, u)[0] == pytest.approx(0.5 + 0.1 * 0.76)


# ===================================================================================================== classification --

def _receipt_mod():
    spec = importlib.util.spec_from_file_location("mlb_pitcher_asof_receipt_t507",
                                                  ROOT / "tests" / "test_mlb_pitcher_asof_receipt.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _pregame_everywhere(p):
    """Every game gets both sides' starting_pitcher listed at kickoff (the boxscore starter's id where one exists)."""
    con = sqlite3.connect(p)
    for gid, kick, h, a in con.execute("SELECT id, utc_date, home_team_id, away_team_id FROM matches").fetchall():
        for team, pid in ((h, "p1"), (a, "p2")):
            con.execute("INSERT INTO match_participants (match_id, team_id, role, kind, player_name, player_source_id, "
                        "source, refreshed_at) VALUES (?, ?, 'starting_pitcher', 'confirmed', ?, ?, 'mlb_stats_api', ?)",
                        (gid, team, pid, pid, kick))
    con.commit()
    con.close()


def test_the_classification_is_the_receipts_and_the_cohort_is_both_sides_on_a_path(tmp_path):
    rt = _receipt_mod()
    p = tmp_path / "copy.db"
    rt.build(p)
    for variant in (False, True):
        if variant:
            _pregame_everywhere(p)
        con = sqlite3.connect(p)
        d = asof.load(con, "2025")
        con.close()
        cls = asof.classify(d, "2025")
        c = asof.reconstruct(d)
        assert cls["counts"] == c                                                  # the receipt's counts, unchanged
        per_side = Counter(g[side]["label"] for g in cls["games"].values() for side in asof.SIDES)
        assert per_side == Counter({k: v for k, v in c.items() if k.startswith("P ")})
        assert len(cls["games"]) == c["regular games read"] == 5
        one = {mid: Counter(g[side]["label"] for side in asof.SIDES) for mid, g in cls["games"].items()}
        want = sorted(mid for mid, o in one.items() if sum(o[k] for k in asof.PATHS) == 2)
        assert asof.cohort_ids(cls) == want
        for g in cls["games"].values():
            for side in asof.SIDES:
                x = g[side]
                if x["label"] not in asof.PATHS:
                    assert x["starter"] is None and x["bullpen"] is None and x["recent"] is None
                assert (x["starter"] is not None) == (x["label"] in (asof.PATHS[0], asof.PATHS[1]))
                assert (x["bullpen"] is not None) == (x["label"] in (asof.PATHS[0], asof.PATHS[2]))
        if not variant:
            assert want == []                                                      # no game has both sides on a path
        else:
            # g0..g4 at T0 + 0, 1, 2, 2, 3 days; every side listed at kickoff (p1 home, p2 away)
            assert len(want) == 1
            con = sqlite3.connect(p)
            g4 = con.execute("SELECT id FROM matches WHERE external_ids LIKE '%5004%'").fetchone()[0]
            con.close()
            g = cls["games"][g4]
            # g4 home: p1's prior g0 + g1 starts (36 outs, ER 4, GS 2) and H's g0 relief r1 (9 outs, ER 1)
            assert (g["home"]["label"], g["home"]["starter"], g["home"]["bullpen"], g["home"]["recent"]) == \
                (asof.PATHS[0], (36, 4, 2), (9, 1), None)
            # g4 away: p2's prior g0 has earned_runs NULL: not reconstructable, so g4 is not in the cohort
            assert g["away"]["label"].startswith("P not reconstructable") and g4 not in want


def test_the_recent_window_carries_its_earned_runs(tmp_path):
    p = tmp_path / "w.db"
    eng = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        h = Team(sport=Sport.MLB, name="Hawks", external_ids={SRC: "147"})
        a = Team(sport=Sport.MLB, name="Owls", external_ids={SRC: "111"})
        s.add_all([comp, h, a])
        s.flush()
        early = Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=datetime(2026, 6, 1, 17, 0),
                      status=MatchStatus.FINISHED, stage="R", home_team_id=h.id, away_team_id=a.id,
                      external_ids={SRC: "1"})
        late = Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=datetime(2026, 6, 11, 23, 0),
                     status=MatchStatus.FINISHED, stage="R", home_team_id=h.id, away_team_id=a.id,
                     external_ids={SRC: "2"})
        s.add_all([early, late])
        s.flush()
        for pid, outs, er in (("r1", 18, 2), ("r2", 12, 3)):
            s.add(PitcherAppearance(match_id=early.id, source_game_id="1", game_date=early.utc_date,
                                    team_source_id="147", pitcher_id=pid, outs=outs, is_starter=False, earned_runs=er))
        s.add(MatchParticipant(match_id=late.id, team_id=h.id, role="starting_pitcher", kind="confirmed",
                               player_name="new", player_source_id="new", refreshed_at=late.utc_date))
        late_id = late.id
        s.commit()
    eng.dispose()
    con = sqlite3.connect(p)
    cls = asof.classify(asof.load(con, "2026"), "2026")
    con.close()
    side = cls["games"][late_id]["home"]
    assert side == {"label": asof.PATHS[2], "name": "new", "starter": None, "bullpen": (30, 5), "recent": (30, 5)}
    ps = asof.pitcher_stats_asof(side, BaseballConfig())
    bp_era = 27 * 5 / 30
    eff = 0.7 * bp_era + 0.3 * bp_era
    w = 10 / (10 + 50)
    assert ps.starter_known is False and ps.era == pytest.approx(0.5 * (w * eff + (1 - w) * 4.2) + 0.5 * 4.2)


# ===================================================================================================== the ledger --

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A tmp copy of the real registry; the ids and the reservation in tmp (tests/test_ncaa_elo_v2.py's pattern)."""
    p = tmp_path / "experiments.json"
    p.write_text((ROOT / "docs" / "registry" / "experiments.json").read_text())
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(mp, "RESERVATION", str(tmp_path / "mlb-pitchers-v1.started.json"))
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: f"guard {eid}: stub")
    return p


def _edit(ledger, fn):
    entries = json.loads(Path(ledger).read_text())
    out = []
    for e in entries:
        if e["id"] == mp.EID:
            e = fn(e)
        if e is not None:
            out.append(e)
    Path(ledger).write_text(json.dumps(out, indent=2) + "\n")


# ===================================================================================================== the fence --

def test_the_fence_refuses_the_pitcher_layer_on_2026_while_declared_and_unrun_and_when_absent(ledger):
    for season in ("2026", None, " 2026 "):
        why = mp.fence_walk("MLB", season)
        assert why and mp.FENCE_TEXT in why and "declared and unrun" in why
        with pytest.raises(mp.PitcherFenceRefused) as ex:
            bt.run_backtest(season=season, competition_code="mlb", pitcher_layer=True, pitcher_inputs={})
        assert isinstance(ex.value, nb.FenceRefused) and "mlb-pitchers-gate" in str(ex.value)
    assert mp.fence_walk("MLB", "2025") is None and mp.fence_walk("NFL", "2026") is None
    bt.run_backtest(season="2026", competition_code="MLB")                         # OFF: never fenced
    bt.run_backtest(season="2025", competition_code="MLB", pitcher_layer=True, pitcher_inputs={})
    with pytest.raises(mp.PitcherFenceRefused) as ex:                              # Codex on #748 (P1): the flag
        bt.run_backtest(season="2026", competition_code="MLB", pitcher_layer=True, pitcher_inputs={},
                        sealed_read=True)                                          # alone, no reservation: refused
    assert "sealed_read without the gate's reservation" in str(ex.value) and mp.FENCE_TEXT in str(ex.value)
    assert not os.path.exists(mp.reservation_path())
    Path(mp.reservation_path()).write_text("{}")                                   # the gate's own walk, reserved
    bt.run_backtest(season="2026", competition_code="MLB", pitcher_layer=True, pitcher_inputs={},
                    sealed_read=True)
    assert mp.sealed_refusal("MLB", "2025") is None and mp.sealed_refusal("NFL", "2026") is None
    os.remove(mp.reservation_path())
    _edit(ledger, lambda e: None)                                                  # absent: fails closed
    assert "absent from the registry" in mp.fence_walk("MLB", "2026")
    with pytest.raises(mp.PitcherFenceRefused):
        bt.run_backtest(season="2026", competition_code="MLB", pitcher_layer=True, pitcher_inputs={})


def test_the_fence_lifts_once_the_run_is_recorded(ledger):
    reg.record_run(mp.EID, [1, 2, 3], {"verdict": "REJECT"}, reg.LEDGER, reg.IDS_DIR)
    assert mp.run_recorded() and mp.fence_walk("MLB", "2026") is None
    bt.run_backtest(season="2026", competition_code="MLB", pitcher_layer=True, pitcher_inputs={})


def test_a_fenced_walk_reaching_the_cli_is_refused_exit_2_never_a_traceback(ledger, monkeypatch):
    import cli
    real = bt.run_backtest
    monkeypatch.setattr(bt, "run_backtest", lambda **kw: real(pitcher_layer=True, pitcher_inputs={}, **kw))
    r = CliRunner().invoke(cli.cli, ["backtest", "--season", "2026", "--competition", "MLB"])
    assert r.exit_code == 2 and "REFUSED" in r.output and "Traceback" not in r.output
    assert "mlb-pitchers-v1" in r.output


# ===================================================================================================== the gate copy --

N_GAMES, FIRST_LISTED = 60, 45


def _gate_copy(path: Path, first_listed=FIRST_LISTED, production=True, config=None, rookie_away=()):
    """A 2026 copy: 6 teams (statsapi ids), 60 regular games (3 a day, two sharing a kickoff), each with both
    starters (a three-man rotation per team) and a relief appearance per side, earned runs complete; the
    starting_pitcher rows listed 3 hours before kickoff from game `first_listed` on (so the cohort is games 45-59:
    every side a blend); a production MLB model (baseball_config `config`, default {run_shrink_enabled: True}). A game
    index in `rookie_away` lists an away starter with no prior appearance (an asymmetric game: the away side's
    bullpen half-weighted, starter unknown; the shrink applies)."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        teams = [Team(sport=Sport.MLB, name=f"G T{i}", external_ids={SRC: str(100 + i)}) for i in range(6)]
        s.add_all([comp, *teams])
        s.flush()
        starts = Counter()
        t0 = datetime(2026, 5, 1, 17, 5)
        for k in range(N_GAMES):
            day, slot = divmod(k, 3)
            pairs = [(0, 1), (2, 3), (4, 5)] if day % 2 == 0 else [(1, 2), (3, 4), (5, 0)]
            h, a = pairs[slot] if day % 3 else pairs[slot][::-1]
            at = t0 + timedelta(days=day, hours=(0, 0, 3)[slot])
            m = Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=at, status=MatchStatus.FINISHED,
                      stage="R", home_team_id=teams[h].id, away_team_id=teams[a].id, home_score=1 + (k * 7) % 6,
                      away_score=1 + (k * 5) % 5, external_ids={SRC: str(9000 + k)})
            s.add(m)
            s.flush()
            for t in (h, a):
                sp = f"t{t}s{starts[t] % 3}"
                starts[t] += 1
                s.add(PitcherAppearance(match_id=m.id, source_game_id=str(9000 + k), game_date=at,
                                        team_source_id=str(100 + t), pitcher_id=sp, outs=15 + k % 4, is_starter=True,
                                        earned_runs=k % 4))
                s.add(PitcherAppearance(match_id=m.id, source_game_id=str(9000 + k), game_date=at,
                                        team_source_id=str(100 + t), pitcher_id=f"t{t}r{k % 2}", outs=9 + k % 3,
                                        is_starter=False, earned_runs=k % 3))
                if k >= first_listed:
                    lp = f"rookie{k}" if (t == a and k in rookie_away) else sp
                    s.add(MatchParticipant(match_id=m.id, team_id=teams[t].id, role="starting_pitcher",
                                           kind="confirmed", player_name=lp, player_source_id=lp,
                                           refreshed_at=at - timedelta(hours=3)))
        if production:
            s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_pythag_negbin", version="v2", status="production",
                               parameters={"baseball_config": config or {"run_shrink_enabled": True}}))
        s.commit()
    eng.dispose()
    return path


def _cohort_of(path):
    return asof.cohort_ids(mp.classify_copy(Path(path)))


@pytest.fixture
def gate(ledger, tmp_path, monkeypatch):
    p = _gate_copy(tmp_path / "copy.db")
    ids = _cohort_of(p)
    monkeypatch.setattr(mp, "COHORT_N", len(ids))
    return {"db": p, "ids": ids, "tmp": tmp_path}


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_the_synthetic_copy_has_a_fifteen_game_cohort_all_blends(gate):
    cls = mp.classify_copy(gate["db"])
    assert len(gate["ids"]) == N_GAMES - FIRST_LISTED
    assert {cls["games"][i][s]["label"] for i in gate["ids"] for s in asof.SIDES} == {asof.PATHS[0]}


def test_freeze_writes_the_cohort_file_and_test_cohort_then_the_run_scores_it_and_records_once(gate, monkeypatch):
    import cli
    before = _sha(gate["db"])
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-freeze", "--db", str(gate["db"])])
    assert r.exit_code == 0, r.output
    assert "cohort 15 (declared 15)" in r.output and "NOTHING SCORED" in r.output
    f = Path(reg.IDS_DIR) / "mlb-pitchers-v1.cohort.txt"
    assert f.read_text() == "\n".join(str(i) for i in gate["ids"]) + "\n"
    e = reg.get(mp.EID, reg.LEDGER)
    tc = e["test_cohort"]
    assert tc["n"] == 15 and tc["ids_sha256"] == reg._ids_sha(gate["ids"])
    assert tc["ids_file"] == "docs/registry/ids/mlb-pitchers-v1.cohort.txt" and "confirmation_cohort" not in e
    assert tc["basis"]["games_by_sides_on_a_path"] == {"both": 15, "one": 0, "neither": 45}
    assert sum(tc["basis"]["by_month"].values()) == 15 and tc["basis"]["rule"] == mp.COHORT_RULE
    fp = tc["fingerprint"]                                                         # addendum 193 item 1
    assert set(fp["parts"]) == {"games", "appearances", "starters", "config"} and fp["rule"] == mp.FINGERPRINT_RULE
    assert fp["parts"]["games"]["n"] == 60 and fp["parts"]["config"]["n"] == 1 and "fingerprint " in r.output
    assert e["status"] == "declared" and e["run"] is None
    assert not os.path.exists(mp.reservation_path())                               # the freeze reserves nothing
    calls = []
    real_rr = reg.record_run
    monkeypatch.setattr(reg, "record_run", lambda *a, **k: calls.append(a) or real_rr(*a, **k))
    real_bt = bt.run_backtest

    def walk(**kw):
        assert os.path.exists(mp.reservation_path())                               # reserved before the first read
        assert kw["sealed_read"] is True and kw["pitcher_layer"] is True and kw["season"] == "2026"
        return real_bt(**kw)
    monkeypatch.setattr(bt, "run_backtest", walk)
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-gate", "--db", str(gate["db"])])
    assert r.exit_code == 0, r.output
    assert "scored 15 (the cohort exactly)" in r.output and "VERDICT (computed; the architect rules): " in r.output
    assert len(calls) == 1 and calls[0][0] == mp.EID and sorted(calls[0][1]) == gate["ids"]
    e = reg.get(mp.EID, reg.LEDGER)
    assert e["status"] == "run" and e["run"]["n_scored"] == 15 and e["run"]["result"]["verdict"] in ("PASS", "REJECT")
    assert (Path(reg.IDS_DIR) / "mlb-pitchers-v1.txt").read_text() == f.read_text()
    res = e["run"]["result"]
    assert res["delta"] == res["ll_off"] - res["ll_on"] and res["production_version"] == "v2"
    assert res["baseball_config"]["run_shrink_enabled"] is True
    assert json.loads(Path(mp.reservation_path()).read_text())["cohort_sha256"] == tc["ids_sha256"]
    assert _sha(gate["db"]) == before                                              # the copy never written
    # recorded: the fence is lifted, and a second run refuses (declared and unrun no longer holds)
    assert mp.fence_walk("MLB", "2026") is None
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-gate", "--db", str(gate["db"])])
    assert r.exit_code == 2 and "REFUSED" in r.output and "read once" in r.output


# a production config pitcher_stats_asof reads (league_era, the effective-IP cap), so a default-config build shows
RICH_CONFIG = {"run_shrink_enabled": True, "league_era": 4.0, "starter_eff_ip_enabled": True, "pitcher_damping": 0.5}


@pytest.mark.parametrize("config,rookies", [(None, ()), (RICH_CONFIG, (50, 53))], ids=["default", "asymmetric-rich"])
def test_the_run_scores_both_arms_from_the_same_walk_as_the_reference(ledger, tmp_path, monkeypatch, config, rookies):
    """Both arms pinned to an independent reference: OFF to today's walk; ON to the same walk's profiles fed the
    inputs built HERE from the classification's home and away sides on the copy's production config (built here, not
    by the gate), home as home_pitcher, then the live shrink. The asymmetric copy (a half-weighted away side, the
    shrink applied) on a config pitcher_stats_asof reads makes a home/away swap or a default-config build visible."""
    db = _gate_copy(tmp_path / "copy.db", config=config, rookie_away=rookies)
    ids = _cohort_of(db)
    monkeypatch.setattr(mp, "COHORT_N", len(ids))
    mp.freeze(db)
    r = mp.run(db)
    cfg = BaseballConfig(**(config or {"run_shrink_enabled": True}))
    cls = mp.classify_copy(Path(db))
    inputs = {i: (asof.pitcher_stats_asof(cls["games"][i]["home"], cfg),
                  asof.pitcher_stats_asof(cls["games"][i]["away"], cfg)) for i in ids}
    ons = []
    with mp.readonly_session(Path(db)) as s:
        _, _, homes = _ref_walk("2026", "MLB", scope=lambda: nullcontext(s), pitchers=inputs, ons=ons)
    ref, ref_on = dict(homes), dict(ons)
    assert sorted(ref_on) == ids
    con = sqlite3.connect(db)
    won = {i: hs > as_ for i, hs, as_ in con.execute("SELECT id, home_score, away_score FROM matches")}
    con.close()
    n = len(ids)
    off = math.fsum(mp.ll_home(ref[i], won[i]) for i in ids) / n
    on = math.fsum(mp.ll_home(ref_on[i], won[i]) for i in ids) / n
    assert r["ll_off"] == off and r["ll_on"] == on and r["n"] == n                 # both arms, exactly
    assert r["verdict"] == mp.verdict(off, on) and r["baseball_config"] == cfg.as_dict()
    assert all(cls["games"][i]["home"]["starter"] for i in ids)
    if not rookies:
        assert r["paths"] == {"blend: starter and bullpen / blend: starter and bullpen": n}
        return
    half = [i for i in ids if not inputs[i][1].starter_known]
    assert len(half) == 2 and all(inputs[i][0].starter_known for i in half)
    assert r["paths"]["blend: starter and bullpen / bullpen half-weighted, starter unknown"] == 2
    # the pins bite: a swap of the sides, or the defaults, moves p_on on the asymmetric games
    for i in half:
        h_ps, a_ps = inputs[i]
        assert (asof.pitcher_stats_asof(cls["games"][i]["home"], BaseballConfig()).era != h_ps.era)
        swapped = [(m, (inputs[m][1], inputs[m][0]) if m == i else inputs[m]) for m in ids]
        ons_sw = []
        with mp.readonly_session(Path(db)) as s:
            _ref_walk("2026", "MLB", scope=lambda: nullcontext(s), pitchers=dict(swapped), ons=ons_sw)
        assert dict(ons_sw)[i] != ref_on[i]


def test_freeze_and_run_call_the_cross_ref_guard_and_a_refusal_writes_nothing(gate, monkeypatch):
    """#329 (RULED 2026-10-08): the guard runs before any write in freeze() and before the reservation in run(); a
    refusal names the ref and writes nothing (tests/test_soccer_expansion_confirm.py:206's pin)."""
    db = gate["db"]
    calls = []

    def refusing(eid, no_fetch=False, repo=None):
        calls.append((eid, no_fetch))
        raise reg.RegistryError("stale ref origin/laptop/x holds a different mlb-pitchers-v1.cohort.txt")

    def passing(eid, no_fetch=False, repo=None):
        calls.append((eid, no_fetch))
        return f"guard {eid}: stub"
    walked = []
    real_bt = bt.run_backtest
    monkeypatch.setattr(bt, "run_backtest", lambda **kw: walked.append(kw) or real_bt(**kw))
    cohort = Path(reg.IDS_DIR) / "mlb-pitchers-v1.cohort.txt"
    monkeypatch.setattr(reg, "cross_ref_guard", refusing)
    for nf in (True, False):
        with pytest.raises(mp.GateRefused, match="stale ref origin/laptop/x"):
            mp.freeze(db, no_fetch=nf)
    assert calls == [(mp.EID, True), (mp.EID, False)]
    assert not cohort.exists() and reg.get(mp.EID, reg.LEDGER)["test_cohort"] is None
    monkeypatch.setattr(reg, "cross_ref_guard", passing)
    seen = []
    r = mp.freeze(db, no_fetch=True, echo=seen.append)
    assert calls[-1] == (mp.EID, True) and seen == [f"guard {mp.EID}: stub"] and r["guard"] == seen[0]
    assert cohort.exists()
    monkeypatch.setattr(reg, "cross_ref_guard", refusing)
    with pytest.raises(mp.GateRefused, match="stale ref origin/laptop/x"):
        mp.run(db, no_fetch=True)
    assert calls[-1] == (mp.EID, True)
    assert not os.path.exists(mp.reservation_path()) and not walked                 # nothing reserved, nothing read
    e = reg.get(mp.EID, reg.LEDGER)
    assert e["status"] == "declared" and e["run"] is None
    monkeypatch.setattr(reg, "cross_ref_guard", passing)
    mp.run(db, no_fetch=False)
    assert calls[-1] == (mp.EID, False) and len(walked) == 1
    assert json.loads(Path(mp.reservation_path()).read_text())["guard"] == f"guard {mp.EID}: stub"


def test_a_hash_or_question_mark_in_the_copys_path_keeps_mode_ro_and_reads_that_file(gate):
    """readonly_session hands sqlite3 open_ro's percent-encoded URI: a '#' or '?' cannot cut the filename (opening or
    creating the shorter path read-write) or drop mode=ro."""
    for d in ("bk#1", "q?x"):
        cut = gate["tmp"] / d.split("#")[0].split("?")[0]
        decoy = _gate_copy(cut, config={"run_shrink_enabled": False})              # a database at the cut path
        with sqlite3.connect(decoy) as con:
            con.execute("UPDATE model_versions SET version = 'decoy'")
        decoy_sha = _sha(decoy)
        (gate["tmp"] / d).mkdir()
        p = gate["tmp"] / d / "copy.db"
        p.write_bytes(Path(gate["db"]).read_bytes())
        assert mp.check_db(p) == p.resolve()
        before = _sha(p)
        with mp.readonly_session(p) as s:
            version, cfg = mp.production_config(s)
            files = [row[2] for row in s.connection().exec_driver_sql("PRAGMA database_list")]
            with pytest.raises(Exception, match="readonly"):
                s.connection().exec_driver_sql("CREATE TABLE zz (x INTEGER)")
        assert version == "v2" and cfg.run_shrink_enabled is True and files == [str(p)]
        assert _sha(p) == before and _sha(decoy) == decoy_sha
    assert sorted(x.name for x in gate["tmp"].iterdir() if x.suffix == "" and x.is_file()) == ["bk", "q"]


def test_a_missing_copy_path_component_creates_nothing(gate):
    """No file is created at a cut path when nothing is there (the reproduction's empty 0-byte 'bk')."""
    (gate["tmp"] / "bk#2").mkdir()
    p = gate["tmp"] / "bk#2" / "copy.db"
    p.write_bytes(Path(gate["db"]).read_bytes())
    with mp.readonly_session(p) as s:
        assert mp.production_config(s)[0] == "v2"
    assert not (gate["tmp"] / "bk").exists()


def test_from_a_worktree_the_main_checkouts_data_and_hard_links_into_data_are_refused(gate, tmp_path, monkeypatch):
    """The fence keys on every data/: the code checkout's own (DATA_DIR here, elsewhere) and, from a git worktree, the
    main checkout's (git's common dir's parent); and on identity, so a hard link to a data/ file outside data/ is the
    same file."""
    import shutil
    import subprocess
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    main = tmp_path / "main"
    main.mkdir()
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "-C", str(main)]
    subprocess.run(g + ["init", "-q"], check=True)
    subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "init"], check=True)
    wt = main / ".claude" / "worktrees" / "wt"
    subprocess.run(g + ["worktree", "add", "-q", "--detach", str(wt)], check=True)
    (main / "data").mkdir()
    live = main / "data" / "sports.db"
    live.write_bytes(Path(gate["db"]).read_bytes())
    monkeypatch.setattr(reg, "ROOT", str(wt))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(mp, "DATA_DIR", str(elsewhere))
    assert mp._main_checkout_data() == (main / "data").resolve()
    for p in (live, wt / ".." / ".." / ".." / "data" / "sports.db"):
        with pytest.raises(mp.GateRefused, match="law 5"):
            mp.check_db(p)
    link = tmp_path / "hardlink.db"
    os.link(live, link)
    with pytest.raises(mp.GateRefused, match="hard link into the repo's data/"):
        mp.check_db(link)
    own = elsewhere / "sports.db"
    own.write_bytes(b"x")
    link2 = tmp_path / "hardlink2.db"
    os.link(own, link2)
    with pytest.raises(mp.GateRefused, match="hard link into the repo's data/"):
        mp.check_db(link2)
    copy = tmp_path / "copy_outside.db"
    copy.write_bytes(live.read_bytes())                                            # a real copy passes
    assert mp.check_db(copy) == copy.resolve()
    with pytest.raises(mp.GateRefused, match="law 5"):
        mp.freeze(live)
    assert reg.get(mp.EID, reg.LEDGER)["test_cohort"] is None


def test_an_unreadable_registry_or_a_failed_record_is_refused_exit_2_never_a_traceback(gate, monkeypatch):
    import cli
    db = gate["db"]
    good = Path(reg.LEDGER).read_text()
    Path(reg.LEDGER).write_text(good[: len(good) // 2])                            # truncated: JSONDecodeError
    with pytest.raises(mp.GateRefused, match="cannot be read"):
        mp.declared_unrun()
    why = mp.fence_walk("MLB", "2026")
    assert "cannot be read" in why and "fails closed" in why and mp.FENCE_TEXT in why
    with pytest.raises(mp.PitcherFenceRefused):
        bt.run_backtest(season="2026", competition_code="MLB", pitcher_layer=True, pitcher_inputs={})
    for cmd in ("mlb-pitchers-freeze", "mlb-pitchers-gate"):
        r = CliRunner().invoke(cli.cli, [cmd, "--db", str(db)])
        assert r.exit_code == 2 and "REFUSED: " in r.output and "cannot be read" in r.output, r.output
        assert "Traceback" not in r.output and isinstance(r.exception, SystemExit)
    Path(reg.LEDGER).write_text(good)
    mp.freeze(db)

    def broken(*a, **k):
        raise OSError("No space left on device")
    monkeypatch.setattr(reg, "record_run", broken)
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-gate", "--db", str(db)])
    assert r.exit_code == 2 and isinstance(r.exception, SystemExit), r.output
    assert "VERDICT (computed; the architect rules): " in r.output                 # the console printed first
    assert "REFUSED: run computed and reserved but not recorded: OSError: No space left on device" in r.output
    assert "Traceback" not in r.output and os.path.exists(mp.reservation_path())
    assert reg.get(mp.EID, reg.LEDGER)["run"] is None


def test_freeze_refusals(gate, monkeypatch):
    db = gate["db"]
    cohort = Path(reg.IDS_DIR) / "mlb-pitchers-v1.cohort.txt"
    for bad, says in ((None, "--db PATH is required"), (gate["tmp"] / "absent.db", "never creates one"),
                      (ROOT / "data" / "sports.db", "law 5")):
        with pytest.raises(mp.GateRefused, match=says):
            mp.freeze(bad)
    assert not (gate["tmp"] / "absent.db").exists()
    monkeypatch.setattr(mp, "COHORT_N", 16)
    with pytest.raises(mp.GateRefused, match="gives 15 cohort games, not the declared 16"):
        mp.freeze(db)
    assert not cohort.exists() and reg.get(mp.EID, reg.LEDGER)["test_cohort"] is None
    monkeypatch.setattr(mp, "COHORT_N", 15)
    mp.freeze(db)
    with pytest.raises(mp.GateRefused, match="already frozen"):
        mp.freeze(db)
    _edit(reg.LEDGER, lambda e: {**e, "test_cohort": None})
    with pytest.raises(mp.GateRefused, match="already exists without a frozen test_cohort"):
        mp.freeze(db)
    cohort.unlink()
    Path(mp.reservation_path()).write_text('{"started_at": "2026-11-06T15:00:00Z"}\n')
    with pytest.raises(mp.GateRefused, match="a run was started"):
        mp.freeze(db)
    os.unlink(mp.reservation_path())
    for state in ({"status": "run", "run": {"run_at": "x"}}, {"status": "closed"}):
        _edit(reg.LEDGER, lambda e, st=state: {**e, **st})
        with pytest.raises(mp.GateRefused, match="must be declared and unrun"):
            mp.freeze(db)
    _edit(reg.LEDGER, lambda e: None)
    with pytest.raises(mp.GateRefused, match="status absent"):
        mp.freeze(db)


def test_a_db_under_data_or_the_apps_own_database_is_refused_never_read(gate, monkeypatch):
    data = gate["tmp"] / "data"
    data.mkdir()
    under = data / "copy.db"
    under.write_bytes(Path(gate["db"]).read_bytes())
    monkeypatch.setattr(mp, "DATA_DIR", str(data))
    link = gate["tmp"] / "link.db"
    link.symlink_to(under)
    for p in (under, link, data):
        with pytest.raises(mp.GateRefused, match="law 5"):
            mp.check_db(p)
    from config import settings
    with pytest.raises(mp.GateRefused, match="the app's configured database"):
        mp.check_db(settings.database_url.replace("sqlite:///", ""))
    assert mp.check_db(gate["db"]) == Path(gate["db"]).resolve()


def test_run_refusals_before_any_read(gate, monkeypatch):
    import cli
    db = gate["db"]
    walked = []
    monkeypatch.setattr(bt, "run_backtest", lambda **kw: walked.append(kw))
    with pytest.raises(mp.GateRefused, match="no frozen test_cohort"):
        mp.run(db)
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-freeze"])
    assert r.exit_code == 2 and "REFUSED: --db PATH is required" in r.output and "Traceback" not in r.output
    mp.freeze(db)
    cohort = Path(reg.IDS_DIR) / "mlb-pitchers-v1.cohort.txt"
    good = cohort.read_text()
    # a tampered file (sha mismatch)
    ids = list(gate["ids"])
    cohort.write_text("\n".join(str(i) for i in ids[:-1] + [ids[-1] + 1000]) + "\n")
    with pytest.raises(mp.GateRefused, match="does not match its sha256/count"):
        mp.run(db)
    cohort.write_text(good)
    # a changed set, consistent file and sha: the copy's re-classification is not it
    other = ids[1:] + [ids[0] - 1]
    _edit(reg.LEDGER, lambda e: {**e, "test_cohort": {**e["test_cohort"], "ids_sha256": reg._ids_sha(other)}})
    cohort.write_text("\n".join(str(i) for i in sorted(other)) + "\n")
    with pytest.raises(mp.GateRefused, match="is not the frozen cohort: 1 frozen id"):
        mp.run(db)
    _edit(reg.LEDGER, lambda e: {**e, "test_cohort": {**e["test_cohort"], "ids_sha256": reg._ids_sha(ids)}})
    cohort.write_text(good)
    # the copy moved: one cohort game's starters no longer listed -> 14
    moved = gate["tmp"] / "moved.db"
    moved.write_bytes(Path(db).read_bytes())
    con = sqlite3.connect(moved)
    con.execute("DELETE FROM match_participants WHERE match_id = ?", (ids[3],))
    con.commit()
    con.close()
    with pytest.raises(mp.GateRefused, match="gives 14 cohort games, not 15"):
        mp.run(moved)
    # no production config on the copy
    noprod = _gate_copy(gate["tmp"] / "noprod.db", production=False)
    with pytest.raises(mp.GateRefused, match="no production MLB model"):
        mp.run(noprod)
    # Codex on #748 (P1): a newer production MLB row of another family would be the walk's row: refused
    other = gate["tmp"] / "otherfam.db"
    other.write_bytes(Path(db).read_bytes())
    con = sqlite3.connect(other)
    cols = [r[1] for r in con.execute("PRAGMA table_info(model_versions)")]
    row = dict(zip(cols, con.execute("SELECT * FROM model_versions WHERE status='production'").fetchone()))
    row.update(id=row["id"] + 100, model_family="mlb_other_family", version="x1",
               parameters=json.dumps({"baseball_config": {"run_shrink_enabled": False}}))
    con.execute(f"INSERT INTO model_versions ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    con.commit()
    con.close()
    with pytest.raises(mp.GateRefused, match="is not the live family's"):
        mp.run(other)
    # missing / under data
    for bad, says in ((None, "required"), (gate["tmp"] / "absent.db", "never creates one"),
                      (ROOT / "data" / "sports.db", "law 5")):
        with pytest.raises(mp.GateRefused, match=says):
            mp.run(bad)
    assert not walked and not os.path.exists(mp.reservation_path())                 # nothing reserved, nothing read
    # an existing reservation refuses
    Path(mp.reservation_path()).write_text('{"started_at": "2026-11-06T15:00:00Z"}\n')
    with pytest.raises(mp.GateRefused, match="a run was started at 2026-11-06T15:00:00Z"):
        mp.run(db)
    os.unlink(mp.reservation_path())
    # the CLI: REFUSED, exit 2, never a traceback
    for args in ([], ["--db", str(gate["tmp"] / "absent.db")]):
        r = CliRunner().invoke(cli.cli, ["mlb-pitchers-gate", *args])
        assert r.exit_code == 2 and "REFUSED: " in r.output and "Traceback" not in r.output
    _edit(reg.LEDGER, lambda e: {**e, "status": "closed"})
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-gate", "--db", str(db)])
    assert r.exit_code == 2 and "must be declared and unrun" in r.output
    assert not walked


def test_an_unpriceable_cohort_game_makes_the_run_invalid_printed_and_recorded(ledger, tmp_path, monkeypatch):
    import cli
    db = _gate_copy(tmp_path / "early.db", first_listed=0)           # every game listed: the warm-up is in the cohort
    ids = _cohort_of(db)
    monkeypatch.setattr(mp, "COHORT_N", len(ids))
    mp.freeze(db)
    r = CliRunner().invoke(cli.cli, ["mlb-pitchers-gate", "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "INVALID: " in r.output and "no figure of either arm is printed" in r.output and "log-loss" not in r.output
    e = reg.get(mp.EID, reg.LEDGER)
    res = e["run"]["result"]
    assert res["verdict"] == "INVALID" and res["unpriced_n"] >= 40 and "ll_off" not in res
    assert res["unpriced_ids"] == sorted(res["unpriced_ids"]) and set(res["unpriced_ids"]) <= set(ids)
    assert e["run"]["n_scored"] == len(ids)


def test_the_verdict_arithmetic_reads_the_bar_literally():
    assert mp.BAR == 0.0050
    assert mp.verdict(0.0050, 0.0) == "PASS"                                       # exactly at the bar
    assert mp.verdict(math.nextafter(0.0050, 0.0), 0.0) == "REJECT"                # just under
    assert mp.verdict(0.69, 0.69) == "REJECT"                                      # a tie of the arms
    assert mp.verdict(0.70, 0.69) == "PASS" and mp.verdict(0.69, 0.70) == "REJECT"
    rows = [(1, datetime(2026, 6, 1), True, 0.5, 0.6), (2, datetime(2026, 6, 2), False, 0.5, 0.45),
            (3, datetime(2026, 7, 1), True, 0.5, 1.0), (4, datetime(2026, 7, 2), False, 0.5, 1.0)]
    r = mp.score(rows, [1, 2, 3, 4])
    lls_on = [-math.log(0.6), -math.log(0.55), -math.log(1.0), -math.log(1e-12)]
    assert r["ll_off"] == pytest.approx(math.log(2)) and r["ll_on"] == pytest.approx(sum(lls_on) / 4)
    assert r["brier_on"] == pytest.approx((0.16 + 0.2025 + 0.0 + 1.0) / 4) and r["brier_off"] == pytest.approx(0.25)
    assert list(r["by_month"]) == ["2026-06", "2026-07"] and r["by_month"]["2026-06"]["n"] == 2
    assert r["verdict"] == "REJECT"                                                # a floored miss outweighs it
    r = mp.score(rows[:2], [1, 2])
    assert r["verdict"] == "PASS" and r["delta"] == r["ll_off"] - r["ll_on"]
    assert mp.score([(1, datetime(2026, 6, 1), True, 0.5, 0.5)], [1])["verdict"] == "REJECT"     # tie
    inv = mp.score(rows[:2], [1, 2, 9])
    assert inv["verdict"] == "INVALID" and inv["unpriced_ids"] == [9] and "ll_off" not in inv


@pytest.mark.parametrize("p_on,verdict", [(0.6, "PASS"), (0.4, "REJECT"), (0.5, "REJECT")])
def test_pass_reject_and_a_tie_end_to_end_on_constructed_rows(gate, monkeypatch, p_on, verdict):
    mp.freeze(gate["db"])
    monkeypatch.setattr(bt, "run_backtest", lambda **kw: [(i, datetime(2026, 6, 1), True, 0.5, p_on)
                                                          for i in kw["pitcher_inputs"]])
    r = mp.run(gate["db"])
    assert r["verdict"] == verdict and r["ll_off"] == pytest.approx(math.log(2))
    lines = mp.run_lines(r)
    assert any(line.startswith(f"  log-loss OFF {r['ll_off']!r}") for line in lines)        # unrounded, repr
    assert lines[-1].endswith(verdict)
    mp.record(r)
    assert reg.get(mp.EID, reg.LEDGER)["run"]["result"]["verdict"] == verdict


# ===================================================================================================== the entry --

# 190 item 3, verbatim, as declared (2026-10-31T15:45:00Z): the gate text never changes
DECLARED_GATE_SHA256 = "3d633bb4408d4f26eb7e5eca110bb39906cf0cac43deb975bcd1360502ec1030"


def test_the_entry_is_declared_unrun_with_the_verbatim_plan():
    e = reg.get(mp.EID)
    assert e is not None, "mlb-pitchers-v1 must be declared in docs/registry/experiments.json"
    assert (e["status"], e["run"], e["verdict"]) == ("declared", None, None)
    assert e["declared_at"] == "2026-10-31T15:45:00Z" and e["sport"] == "mlb"
    assert all(e.get(k) for k in reg.DECLARE_FIELDS)
    assert e["declaration"] == "docs/specs/mlb-pitchers-v1.md" and (ROOT / e["declaration"]).is_file()
    assert hashlib.sha256(e["gate"].encode()).hexdigest() == DECLARED_GATE_SHA256
    assert e["gate"].startswith("THE METRIC AND THE BAR: mean log-loss of the home-win probability over the 1553")
    assert mp.FENCE_TEXT in e["gate"]
    assert e["confirmation_plan"] is None and e["test_cohort"] is None and "confirmation_cohort" not in e
    assert e["cohort"] == {"n_declared": 1553, "rule": e["cohort"]["rule"], "counted_on": "the 10-31 console"}
    assert set(e["arms"]) == {"on", "off"} and e["arms"]["off"].endswith("(as src/walters/backtest.py runs today)")
    assert e["live_needs"].startswith("WHAT THE VERDICT DOES (live_needs): PASS")
    assert "#746" in e["snapshot_note"] and "no third arm is run" in e["snapshot_note"]
    assert e["ratified"].startswith("ARCHITECT 2026-10-31 11:45 ET, addendum 190 (pre-run, frozen")
    assert reg._retired_refusal(e["test_set"], e["id"]) is None and reg.prior_reads(e["test_set"], None, mp.EID) == []
    assert mp.COHORT_N == 1553 and mp.BAR == 0.0050 and mp.EID == e["id"]
    # the ledger stays registry.save's format (indent 2, a trailing newline)
    raw = (ROOT / "docs" / "registry" / "experiments.json").read_text()
    assert raw == json.dumps(json.loads(raw), indent=2) + "\n"
    assert reg.load()[-1]["id"] == mp.EID


def test_the_spec_holds_addendum_190_verbatim_and_the_readings():
    spec = (ROOT / "docs" / "specs" / "mlb-pitchers-v1.md").read_text()
    e = reg.get(mp.EID)
    assert e["gate"] in spec and e["live_needs"] in spec and e["arms"]["on"] in spec
    for r in ("(a)", "(b)", "(c)", "(d)", "(e)", "(f)", "(g)", "(h)"):
        assert f"**{r}" in spec


def test_no_confirmation_freeze_can_overwrite_the_test_cohort_file(gate):
    """Code's reading (a): the test cohort's file has the confirmation cohort's name; the registry's own
    freeze_confirmation_cohort refuses this entry (not confirming; after a PASS, no confirmation_plan)."""
    mp.freeze(gate["db"])
    f = Path(reg.IDS_DIR) / "mlb-pitchers-v1.cohort.txt"
    frozen = f.read_text()
    with pytest.raises(reg.RegistryError, match="not in a confirmation window"):
        reg.freeze_confirmation_cohort(mp.EID, [1], {}, reg.LEDGER, reg.IDS_DIR)
    reg.record_run(mp.EID, gate["ids"], {"verdict": "PASS"}, reg.LEDGER, reg.IDS_DIR)
    reg.record_verdict(mp.EID, "PASS", "test", reg.LEDGER)
    with pytest.raises(reg.RegistryError, match="no executable confirmation_plan"):
        reg.freeze_confirmation_cohort(mp.EID, [1], {}, reg.LEDGER, reg.IDS_DIR)
    assert f.read_text() == frozen and reg.frozen_cohort(reg.get(mp.EID, reg.LEDGER)) is None


# ============================================================================================ Codex on #748, round 1 --

def test_a_ledger_save_failure_removes_the_cohort_file_and_freezes_nothing(gate, monkeypatch):
    """Codex on #748 (P2): a freeze whose ledger save fails leaves no cohort file behind (a later freeze would refuse
    on it) and test_cohort null; the CLI reads REFUSED, exit 2."""
    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(reg, "save", boom)
    with pytest.raises(mp.GateRefused) as ex:
        mp.freeze(gate["db"], no_fetch=True)
    assert "could not be completed" in str(ex.value) and "nothing frozen" in str(ex.value)
    assert not os.path.exists(os.path.join(reg.IDS_DIR, mp.COHORT_FILE))
    assert mp._entry()[mp.COHORT_KEY] is None


def test_the_cross_ref_guard_holds_a_test_cohort_as_the_cohort_kind():
    """Codex on #748 (P2): the #329 guard's cohort kind reads test_cohort as well as confirmation_cohort, so a ref whose
    ledger froze mlb-pitchers-v1's test cohort without its file still holds a cohort (the guard refuses on it)."""
    tc = {"n": 3, "ids_sha256": "x", "ids_file": "docs/registry/ids/mlb-pitchers-v1.cohort.txt"}
    led = json.dumps([{"id": mp.EID, "test_cohort": tc, "run": None}]).encode()
    st = reg._guard_state(mp.EID, lambda rel: led if rel.endswith("experiments.json") else None)
    assert st["cohort"] is not None and st["run record"] is None and st["reservation"] is None
    bare = json.dumps([{"id": mp.EID, "test_cohort": None, "run": None}]).encode()
    assert reg._guard_state(mp.EID, lambda rel: bare if rel.endswith("experiments.json") else None)["cohort"] is None
    conf = json.dumps([{"id": "x", "confirmation_cohort": tc}]).encode()               # the confirmation kind as before
    assert reg._guard_state("x", lambda rel: conf if rel.endswith("experiments.json") else None)["cohort"] is not None


# ================================================================================ the fingerprint (addendum 193) --

def _swapped(gate, name, sql, *args):
    """A copy of the frozen copy with one row changed (the cohort ids unchanged)."""
    p = gate["tmp"] / name
    p.write_bytes(Path(gate["db"]).read_bytes())
    con = sqlite3.connect(p)
    con.execute(sql, args)
    con.commit()
    con.close()
    assert _cohort_of(p) == gate["ids"]                                             # the same 1553 (here 15) ids
    return p


def test_a_swapped_copy_with_the_same_ids_refuses_and_the_frozen_copy_passes(gate, monkeypatch):
    """Addendum 193 item 1 (and item 4's tests): the freeze records the copy's fingerprint; a copy with the same cohort
    ids and one changed score, one changed earned run or another production config is refused before the
    reservation, as a finding (never a re-freeze, never a run on the other copy); the frozen copy runs."""
    mp.freeze(gate["db"], no_fetch=True)
    frozen = mp._entry()[mp.COHORT_KEY]["fingerprint"]
    walked = []
    monkeypatch.setattr(bt, "run_backtest", lambda **kw: walked.append(kw) or [])
    cid = gate["ids"][4]
    score = _swapped(gate, "score.db", "UPDATE matches SET home_score = home_score + 1 WHERE id = ?", cid)
    er = _swapped(gate, "er.db", "UPDATE pitcher_appearances SET earned_runs = earned_runs + 1 WHERE id = "
                                 "(SELECT MIN(id) FROM pitcher_appearances WHERE match_id = ?)", cid)
    conf = _swapped(gate, "conf.db", "UPDATE model_versions SET parameters = ? WHERE status = 'production'",
                    json.dumps({"baseball_config": {"run_shrink_enabled": False}}))
    for p, part in ((score, "games"), (er, "appearances"), (conf, "config")):
        with pytest.raises(mp.GateRefused) as ex:
            mp.run(p, no_fetch=True)
        msg = str(ex.value)
        assert "the copy is not the frozen one" in msg and f"{part} (n " in msg and "#507" in msg
        assert "never a re-freeze" in msg and "nothing reserved" in msg
        assert mp.fingerprint_mismatch(frozen, mp.fingerprint(p, *_prod(p)))
    assert not walked and not os.path.exists(mp.reservation_path())                 # nothing reserved, nothing read
    assert mp.fingerprint_mismatch(frozen, mp.fingerprint(gate["db"], *_prod(gate["db"]))) is None
    r = mp.run(gate["db"], no_fetch=True)                                           # the frozen copy runs
    assert walked and os.path.exists(mp.reservation_path()) and r["fingerprint_sha256"] == frozen["sha256"]


def test_a_frozen_cohort_without_a_fingerprint_refuses_the_run(gate):
    mp.freeze(gate["db"], no_fetch=True)
    _edit(reg.LEDGER, lambda e: {**e, "test_cohort": {k: v for k, v in e["test_cohort"].items() if k != "fingerprint"}})
    with pytest.raises(mp.GateRefused, match="carries no fingerprint"):
        mp.run(gate["db"], no_fetch=True)
    assert not os.path.exists(mp.reservation_path())


def test_the_fingerprint_is_the_rows_not_their_order_or_the_file(gate, tmp_path):
    """The same rows in another file (a VACUUM INTO copy) give the same fingerprint; the read writes nothing."""
    before = _sha(gate["db"])
    a = mp.fingerprint(gate["db"], *_prod(gate["db"]))
    other = tmp_path / "vacuumed.db"
    con = sqlite3.connect(gate["db"])
    con.execute("VACUUM INTO ?", (str(other),))
    con.close()
    assert mp.fingerprint(other, *_prod(other)) == a and _sha(gate["db"]) == before


def _prod(p):
    with mp.readonly_session(Path(p)) as s:
        return mp.production_config(s)


# ============================================================================ #749 (addendum 194 item 2), items 1-3 --

def test_749_1_a_failed_reservation_write_removes_the_file_and_spends_nothing(gate, monkeypatch):
    """A write that fails after the exclusive create (a full disk) leaves no reservation: the one run is not spent,
    the refusal names it, and the next reservation goes through."""
    real = mp.json.dump

    def half(obj, f, *a, **k):
        f.write('{"id": "mlb-pi')
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(mp.json, "dump", half)
    with pytest.raises(mp.GateRefused) as ex:
        mp.reserve({"db": "x"}, no_fetch=True)
    assert "could not be written" in str(ex.value) and "not spent" in str(ex.value)
    assert not os.path.exists(mp.reservation_path())
    monkeypatch.setattr(mp.json, "dump", real)
    assert mp.reserve({"db": "x"}, no_fetch=True) == mp.reservation_path()
    assert json.loads(Path(mp.reservation_path()).read_text())["id"] == mp.EID


def test_749_2_a_non_numeric_cohort_token_refuses_naming_the_file(gate):
    mp.freeze(gate["db"], no_fetch=True)
    f = Path(reg.IDS_DIR) / mp.COHORT_FILE
    f.write_text(f.read_text() + "<<<<<<< HEAD\n")
    with pytest.raises(mp.GateRefused) as ex:
        mp.run(gate["db"], no_fetch=True)
    assert "docs/registry/ids/mlb-pitchers-v1.cohort.txt" in str(ex.value) and "not an id" in str(ex.value)
    assert not os.path.exists(mp.reservation_path())


@pytest.mark.parametrize("where", ["reload", "save-truncated"])
def test_749_3_any_failure_in_the_freeze_sequence_leaves_nothing(gate, monkeypatch, where):
    """One rollback around the whole sequence: a failure in the ledger's reload after the cohort file is written, or a
    save that truncates the ledger and then fails, removes the cohort file and puts the ledger's bytes back; the next
    freeze goes through."""
    before = Path(reg.LEDGER).read_bytes()
    cohort = Path(reg.IDS_DIR) / mp.COHORT_FILE
    if where == "reload":
        real = reg.load

        def flaky(*a, **k):                         # fails only inside the sequence, once the file is written
            if cohort.exists():
                raise OSError(5, "Input/output error")
            return real(*a, **k)
        monkeypatch.setattr(reg, "load", flaky)
        restore = ("load", real)
    else:
        real = reg.save

        def boom(entries, path=reg.LEDGER):
            with open(path, "w") as fh:
                fh.write('[{"id": "trunc')
            raise OSError(28, "No space left on device")
        monkeypatch.setattr(reg, "save", boom)
        restore = ("save", real)
    with pytest.raises(mp.GateRefused) as ex:
        mp.freeze(gate["db"], no_fetch=True)
    msg = str(ex.value)
    assert "could not be completed" in msg and "the cohort file is removed" in msg
    assert ("the ledger was not written" if where == "reload" else "the ledger is as it was") in msg
    assert not cohort.exists() and Path(reg.LEDGER).read_bytes() == before
    monkeypatch.setattr(reg, *restore)
    mp.freeze(gate["db"], no_fetch=True)                                            # the next freeze goes through
    assert cohort.exists() and mp._entry()[mp.COHORT_KEY]["n"] == len(gate["ids"])


def test_751_a_failure_before_the_save_never_overwrites_another_commands_ledger_update(gate, monkeypatch):
    """Codex on #751: the ledger changed by someone else after the snapshot, then this freeze fails before its own
    save: the rollback leaves that update in place (only this call's save is ever undone)."""
    cohort = Path(reg.IDS_DIR) / mp.COHORT_FILE
    real = reg.load

    def flaky(*a, **k):
        if cohort.exists():                         # another command's update lands, then the reload fails
            Path(reg.LEDGER).write_text(Path(reg.LEDGER).read_text().replace('"status": "declared"',
                                                                             '"status": "declared" ', 1))
            raise OSError(5, "Input/output error")
        return real(*a, **k)
    monkeypatch.setattr(reg, "load", flaky)
    with pytest.raises(mp.GateRefused, match="the ledger was not written"):
        mp.freeze(gate["db"], no_fetch=True)
    assert '"status": "declared" ' in Path(reg.LEDGER).read_text() and not cohort.exists()


def test_751_a_reservation_that_cannot_be_removed_says_so(gate, monkeypatch):
    """Codex on #751: when the cleanup of a half-written reservation fails too, the refusal says the file remains and
    must be removed by hand, never that the run is not spent."""
    def half(obj, f, *a, **k):
        f.write("{")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(mp.json, "dump", half)

    def no_rm(p):
        raise OSError(30, "Read-only file system")
    monkeypatch.setattr(mp.os, "remove", no_rm)
    with pytest.raises(mp.GateRefused) as ex:
        mp.reserve({"db": "x"}, no_fetch=True)
    assert "could NOT be removed" in str(ex.value) and "by hand" in str(ex.value)
    assert "not spent" not in str(ex.value)
