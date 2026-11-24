"""THE TRUE-STARTER CEILING, A PROBE, ONE RUN (ARCHITECT 2026-11-24 08:05 ET, addendum 491). Item 9(c), verbatim: "tests
on synthetic rows only: the leave-one-out sums leave out exactly the game's own appearance; the refusals of item 3 print
no log-loss; the registry is not touched; a declaration naming the 2025 set is still refused".

Every database here is a throwaway file built by the test (a stand-in for a .backup copy); the committed registry is
only read. No figure of the probe is computed on real rows (491 item 8)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models import nhl_goalie as ng
from src.models.nhl_elo import NHLEloConfig, NHLEloV1, NHLEloV5, home_advantage_from_rate
from src.walters import nhl_backtest as nb
from src.walters import nhl_ceiling as nc
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "registry" / "experiments.json"
IDS_DIR = ROOT / "docs" / "registry" / "ids"


def A(mid, season, goalie, shots, saves, side="home"):
    return ng.SeasonAppearance(mid, season, side, goalie, shots, saves)


# ------------------------------------------------------------------------- item 5: the hindsight rate --

def _apps():
    """Season 2025: goalie 7 in matches 1, 2, 3 (30 shots each; saves 28, 25, 29); goalie 8 the other side of each and
    relief for 7 in match 3; season 2024: goalie 7 once, hot (40/40), which must not reach 2025."""
    return [A(1, "2025", 7, 30, 28), A(1, "2025", 8, 32, 29, "away"),
            A(2, "2025", 7, 30, 25), A(2, "2025", 8, 28, 26, "away"),
            A(3, "2025", 7, 30, 29), A(3, "2025", 8, 31, 27, "away"),
            A(3, "2025", 9, 4, 4, "away"),                                        # relief, counted as v5 counted it
            A(10, "2024", 7, 40, 40), A(10, "2024", 8, 30, 27, "away")]


def test_491_5_the_league_figures_are_the_seasons_own_whole_and_without_a_boot_prior():
    t = ng.HindsightTracker(_apps())
    shots = 30 + 32 + 30 + 28 + 30 + 31 + 4
    saves = 28 + 29 + 25 + 26 + 29 + 27 + 4
    m, spg, gpg = t.league("2025")
    assert m == pytest.approx(saves / shots) and spg == pytest.approx(shots / 6)          # 6 team-games (3 x 2 sides)
    assert gpg == pytest.approx((shots - saves) / 6)
    assert t.league("2024") == pytest.approx((67 / 70, 70 / 2, 3 / 2))
    t2 = ng.HindsightTracker(_apps(), leave_one_out=False)
    assert t2.league("2025") == t.league("2025")                       # leave-one-out never touches the league figures


def test_491_5b_the_leave_one_out_sums_leave_out_exactly_the_games_own_appearance():
    t, leak = ng.HindsightTracker(_apps()), ng.HindsightTracker(_apps(), leave_one_out=False)
    m = t.league("2025")[0]
    full_shots, full_g = 90, (28 - m * 30) + (25 - m * 30) + (29 - m * 30)
    for mid, (sh, sv) in ((1, (30, 28)), (2, (30, 25)), (3, (30, 29))):
        want = (full_g - (sv - m * sh)) / (full_shots - sh + ng.PRIOR_SHOTS)
        assert t.rate(7, mid) == pytest.approx(want, abs=1e-15)
        assert leak.rate(7, mid) == pytest.approx(full_g / (full_shots + ng.PRIOR_SHOTS), abs=1e-15)
    assert t.rate(7, 1) != t.rate(7, 2)                               # each game leaves out its own appearance only
    m24 = t.league("2024")[0]
    assert t.rate(7, 10) == 0.0 and leak.rate(7, 10) == pytest.approx((40 - m24 * 40) / (40 + ng.PRIOR_SHOTS))
    # the relief goalie's own appearance leaves only his own sums; goalie 8 in match 3 keeps 9's out of his
    assert t.rate(9, 3) == 0.0
    g8 = (29 - m * 32) + (26 - m * 28)
    assert t.rate(8, 3) == pytest.approx(g8 / (32 + 28 + ng.PRIOR_SHOTS), abs=1e-15)


def test_491_5c_the_elo_points_are_v5s_conversion_on_the_seasons_own_figures():
    t = ng.HindsightTracker(_apps())
    m, spg, gpg = t.league("2025")
    want = ng.ELO_PER_LOGIT * ng.PYTH_EXP / gpg * (t.rate(7, 2) * spg)
    assert t.elo_adjustment(7, datetime(2025, 11, 1), match_id=2) == pytest.approx(want, abs=1e-12)
    assert t.elo_adjustment(None, datetime(2025, 11, 1), match_id=2) == 0.0
    assert t.elo_adjustment(12345, datetime(2025, 11, 1), match_id=2) == 0.0       # no appearance in S: the prior
    with pytest.raises(ValueError, match="cannot be placed in a season"):
        t.elo_adjustment(7, datetime(2025, 11, 1))                                  # no match id: never priced
    with pytest.raises(ValueError):
        t.elo_adjustment(7, datetime(2025, 11, 1), match_id=999)
    assert t.advance_to(datetime(2025, 11, 1)) is None                             # GoalieTracker's interface


def test_491_5_two_appearances_of_one_goalie_in_one_game_or_one_game_in_two_seasons_refuse():
    with pytest.raises(ValueError, match="two appearances"):
        ng.HindsightTracker([A(1, "2025", 7, 30, 28), A(1, "2025", 7, 2, 2)])
    with pytest.raises(ValueError, match="two seasons"):
        ng.HindsightTracker([A(1, "2025", 7, 30, 28), A(1, "2024", 8, 30, 28, "away")])


def test_491_4_the_model_is_v5_and_only_the_tracker_and_the_match_id_change():
    class Spy:
        calls = []

        def advance_to(self, t):
            pass

        def elo_adjustment(self, gid, t, match_id=None):
            self.calls.append((gid, match_id))
            return 0.0
    g = nb.Game(1, 2, "2025", datetime(2025, 10, 20, 19), 3, 2, match_id=55, home_goalie=7, away_goalie=8)
    cfg = NHLEloConfig(home_advantage=40.0)
    m = nc.NHLEloHindsight(cfg, tracker=Spy())
    assert isinstance(m, NHLEloV5)
    p = m.predict(g)
    assert Spy.calls == [(7, 55), (8, 55)]
    assert p == pytest.approx(NHLEloV1(cfg).predict(g), abs=1e-12)     # a zero goalie term is v1 exactly (v5's form)
    m.update(g)
    assert Spy.calls[-2:] == [(7, 55), (8, 55)]                        # the update prices the same term (v5's form)


# ------------------------------------------------------------------- item 3 and the command, on a file DB --

def _copy(tmp_path, n_per_season=30, drop_starter=None):
    """A throwaway file database (a stand-in for a .backup copy): NHL 2024 and 2025 finished games after each opener,
    two starters per game linked by match id, one relief appearance; a 2023-24 appearance linked to no match."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.db.schema import Base, Competition, Match, MatchStatus, NHLGoalieAppearance, Sport, Team
    path = tmp_path / "copy" / "sports.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        teams = [Team(sport=Sport.NHL, name=f"Probe {i}") for i in range(4)]
        s.add_all(teams)
        s.flush()
        gid, k = 500000, 0
        for season, start in (("2024", datetime(2024, 10, 9, 23)), ("2025", datetime(2025, 10, 8, 23))):
            for i in range(n_per_season):
                h, a = teams[i % 4], teams[(i + 1 + i // 4) % 4]
                if h is a:
                    a = teams[(i + 2) % 4]
                when = start + timedelta(days=i)
                hs, as_ = (4, 2) if (i * 7) % 5 < 3 else (1, 3)
                m = Match(sport=Sport.NHL, competition_id=comp.id, season=season, utc_date=when,
                          status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs,
                          away_score=as_, stage="Regular Season")
                s.add(m)
                s.flush()
                gid += 1
                for sd, goalie, saves in (("home", 7000 + teams.index(h), 26 + (i * 3) % 5),
                                          ("away", 7000 + teams.index(a), 25 + (i * 2) % 6)):
                    starter = not (drop_starter == (season, i, sd))
                    s.add(NHLGoalieAppearance(nhl_game_id=gid, match_id=m.id, game_start=when, side=sd,
                                              goalie_id=goalie, is_starter=starter, shots_against=30, saves=saves))
                if i == 3:
                    s.add(NHLGoalieAppearance(nhl_game_id=gid, match_id=m.id, game_start=when, side="home",
                                              goalie_id=7100, is_starter=False, shots_against=5, saves=4))
                k += 1
        s.add(NHLGoalieAppearance(nhl_game_id=1, match_id=None, game_start=datetime(2024, 1, 5), side="home",
                                  goalie_id=7000, is_starter=True, shots_against=30, saves=10))   # 2023-24: nothing
        s.commit()
    eng.dispose()
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry_state():
    return LEDGER.read_bytes(), sorted(p.name for p in IDS_DIR.iterdir())


def _stream_on(path):
    with nc.copy_binding(path):
        games = nb.attach_goalies(nb.load_games())
    st = nb.build_stream(games, dict(nb.SEASON_STARTS))
    return st, nb.baselines(st)


def _identity_of(path, monkeypatch):
    st, _ = _stream_on(path)
    ids = [g.match_id for g in st.test]
    monkeypatch.setattr(nc, "IDENTITY", (len(ids), reg._ids_sha(ids)))
    return st


def _no_loss(out):
    low = out.lower()
    return "log-loss" not in low.replace("printing no log-loss", "") and "logloss" not in low


def test_491_3a_a_stream_that_is_not_the_recorded_set_refuses_and_prints_no_log_loss(tmp_path, capsys):
    path = _copy(tmp_path)
    before, reg_before = _sha(path), _registry_state()
    lines = []
    assert nc.run(str(path), out=lines.append) == 2
    out = "\n".join(lines)
    assert "REFUSED: INVALID (491 item 3(a))" in out and "not 1394 with ab890242" in out
    assert _no_loss(out) and "ITEM 6" not in out and "ITEM 7" not in out
    assert _sha(path) == before and _registry_state() == reg_before
    assert not any(path.parent.glob("sports.db-*"))                         # no sidecar created


def test_491_3a_the_registrys_three_entries_hold_the_declared_set():
    for eid in nc.RECORDED_RUNS:
        run = reg.get(eid)["run"]
        assert (run["n_scored"], run["ids_sha256"]) == (nc.EXPECTED_N, nc.EXPECTED_SHA) == (1394, nc.IDENTITY[1])
    ids = [int(x) for x in (IDS_DIR / "nhl-v6.txt").read_text().split()]
    assert reg._ids_sha(ids) == nc.EXPECTED_SHA == "ab890242fe22077580cdb7495e90f58c519a2ddae96445de508f04b99b4de229"


def test_491_3b_an_unknown_starter_on_a_scored_game_refuses_and_prints_no_log_loss(tmp_path, monkeypatch):
    path = _copy(tmp_path, drop_starter=("2025", 5, "away"))
    _identity_of(path, monkeypatch)
    lines = []
    assert nc.run(str(path), out=lines.append) == 2
    out = "\n".join(lines)
    assert "REFUSED: INVALID (491 item 3(b)): both starters are known on 29 of 30 scored games" in out
    assert _no_loss(out) and "(a) scored games 30" not in out          # a refusal prints no check line after it either


def test_491_3c_v1_not_reading_0_6909_refuses_and_prints_neither_figure(tmp_path, monkeypatch):
    path = _copy(tmp_path)
    _identity_of(path, monkeypatch)
    lines = []
    assert nc.run(str(path), out=lines.append) == 2
    out = "\n".join(lines)
    assert "REFUSED: INVALID (491 item 3(c))" in out and _no_loss(out)
    st, base = _stream_on(path)
    v1 = nb.run_gate(st, NHLEloV1(NHLEloConfig(home_advantage=home_advantage_from_rate(base.home_rate))))
    assert f"{v1.ll_model:.4f}" not in out and f"{base.ll_home - nb.LL_MARGIN:.4f}" not in out


def _full_run(tmp_path, monkeypatch, **kw):
    path = _copy(tmp_path, **kw)
    st = _identity_of(path, monkeypatch)
    base = nb.baselines(st)
    v1 = nb.run_gate(st, NHLEloV1(NHLEloConfig(home_advantage=home_advantage_from_rate(base.home_rate))))
    monkeypatch.setattr(nc, "EXPECTED_V1", f"{v1.ll_model:.4f}")
    monkeypatch.setattr(nc, "EXPECTED_BAR", f"{base.ll_home - nb.LL_MARGIN:.4f}")
    return path


def test_491_the_one_run_prints_items_3_to_7_in_order_and_writes_nothing(tmp_path, monkeypatch):
    import src.db.database as database
    path = _full_run(tmp_path, monkeypatch)
    monkeypatch.setattr(reg, "record_run", lambda *a, **k: pytest.fail("record_run called"))
    monkeypatch.setattr(reg, "declare", lambda *a, **k: pytest.fail("declare called"))
    monkeypatch.setattr(reg, "save", lambda *a, **k: pytest.fail("registry save called"))
    before, reg_before, app = _sha(path), _registry_state(), database.SessionLocal
    lines = []
    assert nc.run(str(path), out=lines.append) == 0
    out = "\n".join(lines)
    order = [out.index(k) for k in ("--db ", "ITEM 3", "(a) scored games 30", "(b) both starters known", "(c) v1 on",
                                    "ITEM 4", "ITEM 5", "ITEM 6", "ITEM 7", "ONE RUN")]
    assert order == sorted(order)
    assert f"--db {path.resolve()} · sha256 {before}" in out and "mode=ro&immutable=1" in out
    assert "beats_margin(leave-one-out log-loss" in out and ("= TRUE" in out or "= FALSE" in out)
    assert ("THE ROUTE STAYS OPEN" in out) != ("THE GOALIE TERM IN THIS FORM IS CLOSED" in out)
    assert "LEAKED (the game's own appearance left in" in out and "v5 (as-of) on the same stream" in out
    assert "leave-one-out less v1:" in out
    assert sum(1 for x in lines if x.strip().startswith("nhl-v")) == 8 and "nhl-v1: log-loss 0.6909" in out
    assert "nhl-v8: log-loss 0.6963" in out
    assert "warm-up sides with no known starter (priced at zero, as in v5): 0" in out
    assert "2024: appearances linked to the stream's games 61" in out           # 2 x 30 + 1 relief; 2023-24 none
    assert _sha(path) == before and _registry_state() == reg_before and database.SessionLocal is app
    assert not any(path.parent.glob("sports.db-*"))


def test_491_the_verdict_is_the_gates_own_function_on_the_leave_one_out_figure(tmp_path, monkeypatch):
    path = _full_run(tmp_path, monkeypatch)
    seen = []
    real = nb.beats_margin
    monkeypatch.setattr(nb, "beats_margin", lambda m, h: seen.append((m, h)) or real(m, h))
    lines = []
    assert nc.run(str(path), out=lines.append) == 0
    out = "\n".join(lines)
    m, h = seen[-1]                                                     # run_gate's own calls come first; the line's last
    assert f"beats_margin(leave-one-out log-loss {m:.4f}, home-rate baseline {h:.4f})" in out
    assert ("= TRUE" in out) == real(m, h)


def test_491_a_warm_up_side_with_no_known_starter_prices_at_zero_and_is_counted(tmp_path, monkeypatch):
    path = _full_run(tmp_path, monkeypatch, drop_starter=("2024", 4, "home"))
    lines = []
    assert nc.run(str(path), out=lines.append) == 0
    assert any("warm-up sides with no known starter (priced at zero, as in v5): 1" in x for x in lines)


# ------------------------------------------------------------------------- the fence and the registry --

def test_491_the_copy_fence_refuses_the_configured_database_a_missing_file_and_a_sidecar(tmp_path):
    import os
    app = os.environ["DATABASE_URL"].split("sqlite:///", 1)[1]                # tests/conftest.py's throwaway file
    lines = []
    assert nc.run(app, out=lines.append) == 2 and lines[0].startswith("REFUSED: ")
    lines = []
    assert nc.run(str(tmp_path / "none.db"), out=lines.append) == 2 and lines[0].startswith("REFUSED: ")
    path = _copy(tmp_path)
    (path.parent / "sports.db-wal").write_bytes(b"")
    lines = []
    assert nc.run(str(path), out=lines.append) == 2 and "a sidecar is beside the copy (sports.db-wal)" in lines[0]


def test_491_9c_a_declaration_naming_the_2025_set_is_still_refused(tmp_path):
    p = tmp_path / "x.json"
    entry = {"id": "nhl-ceiling-probe", "sport": "nhl", "lane": "#105", "candidate": "c", "declaration": "d",
             "training_cutoff": "t", "test_set": nc.TEST_SET, "gate": "g", "confirmation_window": "w",
             "confirmation_plan": {"n_games": 600, "metric": "log_loss", "bar": 0.6866, "must_beat_reference": False,
                                   "reference": None}}
    with pytest.raises(reg.RegistryError, match="RETIRED as a test set"):
        reg.declare(entry, path=str(p))
    assert not p.exists()
    assert nc.TEST_SET in reg.RETIRED_TEST_SETS and reg.RETIRED_TEST_SETS[nc.TEST_SET][0] == "nhl-v8"
    assert json.loads(LEDGER.read_text())                                    # the committed ledger, read only


def test_491_the_probe_module_never_names_a_registry_write():
    src = (ROOT / "src" / "walters" / "nhl_ceiling.py").read_text()
    for w in ("record_run(", "declare(", "record_verdict(", "record_confirmation(", "reg.save(", "init_db("):
        assert w not in src, w
