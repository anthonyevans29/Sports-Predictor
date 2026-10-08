"""Design receipt for the ncaa-elo-v1r gate (ARCHITECT 2026-10-08, addendum 11,
item 3, PR A step (a)): a tiny run is deterministic, uses the repo's own
NCAAEloV1 and band rule, and never loads the DB layer."""
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ncaa_v1r_design_receipt.py"

_PROBE = r"""
import importlib.util, json, sys
sys.path.insert(0, %r)
spec = importlib.util.spec_from_file_location("rcpt", %r)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rows = m.run(2)
db_loaded = sorted(k for k in sys.modules if k.startswith("src.db") or k.startswith("sqlalchemy"))
print(json.dumps({"rows": rows, "db": db_loaded}))
"""


def _load():
    spec = importlib.util.spec_from_file_location("ncaa_v1r_design_receipt", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(tmp_path):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'must-not-exist.db'}"
    out = subprocess.run([sys.executable, "-c", _PROBE % (str(ROOT), str(SCRIPT))],
                         capture_output=True, text=True, check=True, cwd=str(tmp_path), env=env)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_tiny_run_is_deterministic_and_reads_no_db(tmp_path):
    a, b = _run(tmp_path), _run(tmp_path)
    assert a["rows"] == b["rows"]
    assert a["db"] == []                       # no DB module, no SQLAlchemy imported
    assert not (tmp_path / "must-not-exist.db").exists()
    assert not (tmp_path / "data").exists()
    assert len(a["rows"]) == 3
    for r in a["rows"]:
        assert r["seasons"] == 2
        assert r["mean_scored"] == 675.0       # 3*65 cross + 8*60 in-conference
        assert r["nonconverged"] == 0


def test_neutral_wrapper_prices_with_zero_home_advantage():
    m = _load()
    from src.walters.ncaa_backtest import Game
    w = m.NeutralAwareElo()
    g = Game(home_id=1, away_id=2, season="2026", utc_date=datetime(2026, 9, 1),
             home_score=7, away_score=3, neutral=True)
    assert w.predict(g) == 0.5
    assert w.m.cfg.home_advantage == 55.0      # restored; D1 constants untouched
    g2 = Game(home_id=3, away_id=4, season="2026", utc_date=datetime(2026, 9, 1),
              home_score=7, away_score=3, neutral=False)
    assert w.predict(g2) > 0.5


def test_logistic_slope_recovers_identity_on_calibrated_data():
    m = _load()
    import numpy as np
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, 20000)
    y = (rng.random(20000) < p).astype(int)
    a, b = m.logistic_slope(list(zip(p.tolist(), y.tolist())))
    assert b is not None and abs(b - 1.0) < 0.1 and abs(a) < 0.1
