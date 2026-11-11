"""THE PERFECT-XI PRICE RECEIPT (ARCHITECT 2026-11-05 08:35 ET, addendum 256 item 3; 2026-11-11 14:10 ET, addendum 343
items 4-5; lane cups, #106): the report-only history XI in training._generate_predictions_soccer, the receipt
(src/walters/cup_perfect_xi.py) and `cup-exam --with-history-xi --db COPY`, on throwaway SQLite files.

EVERY ROW IS SYNTHETIC: clubs "PL0".."ELC5", players "P0-3", fair prices made up. No real lineup, price or fixture.
256 item 3: "a test pins that the flag changes nothing when no history lineup exists".
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.walters import cup_perfect_xi as px
from src.walters.cup_exam import score_exam

REPO = Path(__file__).resolve().parents[1]
SEASON = "2026/27"
NEW_KEYS = ("home_history_xi", "away_history_xi", "home_xi_baseline", "away_xi_baseline", "home_xi_mults",
            "away_xi_mults")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A throwaway file DB: PL (6 clubs, Elo 1650) and ELC (6 clubs, 1450) league seasons, an EFL cup round of 12
    finished ties (2nd Round), a production v22; PL0 holds a 16-man squad with season stats (11 scorers, 5 not)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import (Competition, Match, MatchStatus, ModelVersion, Player, PlayerSeasonStats, Sport,
                               Team)
    path = tmp_path / "world.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    out = {"path": path}
    with db.session_scope() as s:
        comps = {c: Competition(sport=Sport.SOCCER, code=c, name=c, area="England", type=t)
                 for c, t in (("PL", "LEAGUE"), ("ELC", "LEAGUE"), ("EFL", "CUP"))}
        s.add_all(comps.values())
        pl = [Team(sport=Sport.SOCCER, name=f"PL{i}") for i in range(6)]
        elc = [Team(sport=Sport.SOCCER, name=f"ELC{i}") for i in range(6)]
        s.add_all(pl + elc)
        s.flush()
        t0 = datetime(2026, 8, 9, 15)
        for code, teams in (("PL", pl), ("ELC", elc)):
            for rd in range(5):
                for i in range(0, 6, 2):
                    h, a = teams[(i + rd) % 6], teams[(i + 1 + rd) % 6]
                    s.add(Match(sport=Sport.SOCCER, competition_id=comps[code].id, season=SEASON,
                                utc_date=t0 + timedelta(days=7 * rd), status=MatchStatus.FINISHED,
                                home_team_id=h.id, away_team_id=a.id, home_score=(i + rd) % 3,
                                away_score=(i * rd) % 2))
        cup = []
        for j in range(12):
            h, a = (pl[j % 6], elc[(j + 1) % 6]) if j % 2 == 0 else (elc[j % 6], pl[(j + 2) % 6])
            m = Match(sport=Sport.SOCCER, competition_id=comps["EFL"].id, season=SEASON, stage="2nd Round",
                      utc_date=datetime(2026, 9, 16, 18) + timedelta(hours=j), status=MatchStatus.FINISHED,
                      home_team_id=h.id, away_team_id=a.id, home_score=j % 3, away_score=(j + 1) % 2)
            s.add(m)
            cup.append(m)
        s.flush()
        for k in range(16):                                   # PL0's squad: 11 scorers, then 5 who never score
            p = Player(sport=Sport.SOCCER, name=f"P0-{k}", position="Attacker", team_id=pl[0].id)
            s.add(p)
            s.flush()
            good = k < 11
            s.add(PlayerSeasonStats(player_id=p.id, team_id=pl[0].id, season=SEASON, competition_code="PL",
                                    appearances=10, lineups=10, minutes=900, goals=9 if good else 0,
                                    assists=4 if good else 0, shots=35 if good else 2,
                                    shots_on_target=18 if good else 0, key_passes=20 if good else 1))
        ratings = {t.id: 1650 for t in pl} | {t.id: 1450 for t in elc}
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v22",
                           status="production", parameters={
                               "elo": {"league": {"ratings": ratings},
                                       "cup": {"ratings": {t: 1500 for t in ratings}}},
                               "team_to_league": {t.id: "PL" for t in pl} | {t.id: "ELC" for t in elc},
                               "contexts": {}, "poisson": {"elo_goal_coeff": 0.0008, "dixon_coles_rho": -0.10}}))
        out["cup"] = [(m.id, m.home_team_id, m.away_team_id) for m in cup]
        out["pl0"] = pl[0].id
    yield out
    eng.dispose()
    assert not (tmp_path / "data").exists() and not list(tmp_path.rglob("data"))


def _history(match_id, team_id, names, kind="history"):
    from src.db.database import session_scope
    from src.db.schema import Lineup
    with session_scope() as s:
        for n in names:
            s.add(Lineup(match_id=match_id, team_id=team_id, kind=kind, is_starter=True, player_name=n,
                         player_position="Attacker", source="api_football"))


def _price(**kw):
    from src.walters.training import _generate_predictions_soccer
    return {r["match_id"]: r for r in _generate_predictions_soccer("EFL", SEASON, include_finished=True, **kw)}


def _probs(r):
    return (r["p_home"], r["p_draw"], r["p_away"])


ROTATED = [f"P0-{k}" for k in (0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 15)]   # 5 non-scorers in: a weaker XI


def _pl0_home_tie(world):
    return next((mid, h, a) for mid, h, a in world["cup"] if h == world["pl0"])


# ---- the training path: refused outside report-only; nothing changes without history rows -----------------------------

def test_history_xi_is_refused_outside_report_only_and_names_its_readings(world):
    from src.walters.training import HISTORY_XI_READINGS, _generate_predictions_soccer
    assert HISTORY_XI_READINGS == {"confirmed": "confirmed", "as_it_stands": "history"}
    with pytest.raises(ValueError, match="report-only"):
        _generate_predictions_soccer("EFL", SEASON, history_xi="confirmed")
    with pytest.raises(ValueError, match="is not one of"):
        _generate_predictions_soccer("EFL", SEASON, include_finished=True, history_xi="perfect")


def test_256_the_flag_changes_nothing_when_no_history_lineup_exists(world):
    """256 item 3, verbatim: "a test pins that the flag changes nothing when no history lineup exists". The prices are
    equal, and every key of the default report row is equal; only the receipt's own keys are added."""
    base = _price()
    for reading in px.READINGS:
        hx = _price(history_xi=reading)
        assert set(hx) == set(base) and len(base) == 12
        for mid, r in base.items():
            assert _probs(hx[mid]) == _probs(r)
            assert {k: v for k, v in hx[mid].items() if k not in NEW_KEYS} == r
            assert not hx[mid]["home_history_xi"] and not hx[mid]["away_history_xi"]
    assert not any(k in r for r in base.values() for k in NEW_KEYS)      # the default report row is unchanged


def test_the_default_paths_never_read_a_history_row(world):
    """#541 / addendum 75 item 2 unchanged: with history rows stored, the report-only path without the flag prices as
    before they existed."""
    before = _price()
    mid, h, _ = _pl0_home_tie(world)
    _history(mid, h, ROTATED)
    assert _price() == before


def test_the_history_xi_moves_the_price_through_the_existing_multipliers_at_the_readings_confidence(world):
    mid, h, _ = _pl0_home_tie(world)
    base = _price()
    _history(mid, h, ROTATED)
    conf, stand = _price(history_xi="confirmed"), _price(history_xi="as_it_stands")
    r = conf[mid]
    assert r["home_history_xi"] and not r["away_history_xi"] and r["home_xi_baseline"]
    assert r["home_xi_mults"] != (1.0, 1.0) and r["away_xi_mults"] == (1.0, 1.0)
    assert r["p_home"] < base[mid]["p_home"]                    # a weaker XI: the home side's price falls
    assert stand[mid]["p_home"] != r["p_home"]                  # 0.3 against 0.7: the reading's confidence
    assert abs(stand[mid]["p_home"] - base[mid]["p_home"]) < abs(r["p_home"] - base[mid]["p_home"])
    for other in set(base) - {mid}:                              # no other fixture moves
        assert _probs(conf[other]) == _probs(base[other])


def test_a_side_with_live_rows_and_history_rows_is_priced_with_the_history_xi(world):
    mid, h, _ = _pl0_home_tie(world)
    _history(mid, h, [f"P0-{k}" for k in range(11)], kind="confirmed")   # a live XI: the regulars
    live = _price()
    _history(mid, h, ROTATED)
    assert _price(history_xi="confirmed")[mid]["p_home"] < live[mid]["p_home"]


# ---- the receipt (pure) -------------------------------------------------------------------------------------------------

def _key(mid, fh, comp="EFL", date="2026-09-16"):
    return {"match_id": mid, "date": date, "comp": comp, "stage": "2nd Round", "home": f"H{mid}", "away": f"A{mid}",
            "fair_home": fh, "fair_draw": 0.25, "fair_away": 0.75 - fh}


def _row(p, hist=(False, False), stats=(False, False), mults=((1.0, 1.0), (1.0, 1.0))):
    return {"p_home": p, "p_draw": 0.25, "p_away": 0.75 - p, "home_history_xi": hist[0], "away_history_xi": hist[1],
            "home_xi_baseline": stats[0], "away_xi_baseline": stats[1], "home_xi_mults": mults[0],
            "away_xi_mults": mults[1]}


def test_the_receipt_scores_three_readings_unchanged_counts_coverage_and_the_subset():
    key = [_key(1, 0.50), _key(2, 0.40), _key(3, 0.30)]
    known = {1, 2, 3}
    base = {1: _row(0.60), 2: _row(0.55), 3: _row(0.45)}
    conf = {1: _row(0.52, (True, True), (True, False), ((0.95, 1.02), (1.0, 1.0))),
            2: _row(0.55, (True, False), (False, False)),
            3: _row(0.45)}
    stand = {1: _row(0.56, (True, True), (True, False)), 2: _row(0.55, (True, False)), 3: _row(0.45)}
    rc = px.receipt(key, known, base, {"confirmed": conf, "as_it_stands": stand})
    assert rc["figures"]["fix_v2"] == px.figures(score_exam(key, base, known))       # cup_exam's own scoring
    assert rc["figures"]["confirmed"]["mae_home_pp"] == pytest.approx((2 + 15 + 15) / 3)
    assert rc["coverage"] == {"both": 1, "one": 1, "absent": 1, "sides_with_xi": 3, "no_effect_no_stats": 2,
                              "no_effect_other": 0, "effective_sides": 1, "with_stats": [1]}
    assert rc["subset_n"] == 1 and rc["subset"]["confirmed"]["mae_home_pp"] == pytest.approx(2.0)
    assert [d["hist"] for d in rc["deltas"]] == ["HA", "H-", "--"] and rc["deltas"][0]["stats"] == "H-"
    text = "\n".join(px.lines(rc, db="/copy.db", coeff_mode="tuned", seconds=12.0))
    assert "<- the figure OF RECORD" in text and "as it stands, information only" in text
    assert "SUBSET, information only (not a second verdict)" in text and "judges nothing" in text
    assert "absent 1 (law 4" in text and "do nothing on 2 (no player-season stats)" in text
    for word in ("DECLARE", "CLOSED", "PASS", "FAIL"):                   # it prints figures; it judges nothing
        assert word not in text


def test_the_receipt_keeps_the_invalid_rules_unchanged():
    key = [_key(i, 0.5) for i in range(1, 5)]
    rc = px.receipt(key, {1}, {1: _row(0.5)}, {"confirmed": {1: _row(0.5)}, "as_it_stands": {1: _row(0.5)}})
    f = rc["figures"]["confirmed"]
    assert f["invalid"] and f["under_coverage"] and f["missing"] == 3
    assert "INVALID: > 2 key rows missing" in px._fmt(f) and "INVALID: < 45 scored" in px._fmt(f)


# ---- the --db copy: mode=ro + immutable=1 -------------------------------------------------------------------------------

def _backup(src: Path, dst: Path) -> Path:
    """A .backup-API copy in WAL mode (the host's and the laptop's copies are), sidecars none."""
    con = sqlite3.connect(src)
    con.execute("PRAGMA journal_mode=WAL")
    out = sqlite3.connect(dst)
    con.backup(out)
    out.close()
    con.close()
    for sfx in ("-wal", "-shm"):
        Path(str(dst) + sfx).unlink(missing_ok=True)
    return dst


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_copy_binding_reads_mode_ro_immutable_creates_no_sidecar_refuses_a_write_and_restores(world, tmp_path):
    import src.db.database as db
    from sqlalchemy import text
    copy = _backup(world["path"], tmp_path / "copy.db")
    sha = _sha(copy)
    saved = (db._engine, db.SessionLocal)
    with px.copy_binding(str(copy)) as p:
        assert p == copy.resolve()
        with db.session_scope() as s:
            assert s.execute(text("SELECT COUNT(*) FROM matches WHERE competition_id IN (SELECT id FROM competitions "
                                  "WHERE code = 'EFL')")).scalar() == 12
        with pytest.raises(Exception, match="readonly|read-only|attempt to write"):
            with db.session_scope() as s:
                s.execute(text("DELETE FROM lineups"))
    assert (db._engine, db.SessionLocal) == saved
    assert _sha(copy) == sha and not Path(str(copy) + "-wal").exists() and not Path(str(copy) + "-shm").exists()


def test_the_copy_binding_refuses_a_missing_file_and_creates_none(tmp_path):
    missing = tmp_path / "nope" / "copy.db"
    with pytest.raises(px.Refused, match="no file at"):
        with px.copy_binding(str(missing)):
            pass
    with pytest.raises(px.Refused, match="required"):
        with px.copy_binding(None):
            pass
    assert not missing.parent.exists()


# ---- the command --------------------------------------------------------------------------------------------------------

def test_the_command_prints_the_exam_then_the_receipt_on_the_copy_and_writes_nothing(world, tmp_path):
    from cli import cli
    mid, h, _ = _pl0_home_tie(world)
    _history(mid, h, ROTATED)
    key = tmp_path / "key.csv"
    lines = ["match_id,date,comp,stage,home,away,score,result,fair_home,fair_draw,fair_away,books"]
    for i, (m, _, _) in enumerate(world["cup"]):
        lines.append(f"{m},2026-09-16,EFL,2nd Round,H{m},A{m},1-0,H,{0.40 + i / 100:.2f},0.25,"
                     f"{0.35 - i / 100:.2f},3")
    key.write_text("\n".join(lines) + "\n")
    copy = _backup(world["path"], tmp_path / "copy.db")
    sha = _sha(copy)
    res = CliRunner().invoke(cli, ["cup-exam", "--key", str(key), "--cup-coeffs", "base", "--with-history-xi",
                                   "--db", str(copy)])
    assert res.exit_code == 0, res.output
    out = res.output
    assert out.index("VERDICT:") < out.index("THE PERFECT-XI PRICE")          # the exam as today, then the receipt
    assert "priced EFL 2026/27 with the history XI (confirmed): 12 fixtures (report-only)" in out
    assert "<- the figure OF RECORD" in out and "both sides 0 · one side 1 · absent 11" in out
    assert "runtime" in out and f"--db {copy}" in out
    assert _sha(copy) == sha and not Path(str(copy) + "-wal").exists()
    refused = CliRunner().invoke(cli, ["cup-exam", "--key", str(key), "--with-history-xi"])
    assert refused.exit_code == 2 and "pass --db PATH" in refused.output
