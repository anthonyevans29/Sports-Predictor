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


def test_cross_round_is_rejection_sampling_uniform_over_valid_matchings(monkeypatch):
    """Codex on #365 (P2), I5: a cross-conference round is a uniform random permutation paired consecutively,
    accepted iff no pair shares a conference; the first accepted draw of the seeded stream is the round. The
    earlier randomized greedy draw weighted matchings unequally."""
    import numpy as np
    from collections import Counter

    m = _load()
    conf = np.repeat(np.arange(m.N_CONF), m.CONF_SIZE)
    got = m.cross_round(np.random.default_rng(7), conf)
    rng = np.random.default_rng(7)                       # the definition, replayed on the same seed
    while True:
        perm = rng.permutation(m.N_TEAMS)
        a, b = perm[0::2], perm[1::2]
        if not np.any(conf[a] == conf[b]):
            break
    assert got == [(int(x), int(y)) for x, y in zip(a, b)]
    assert len(got) == 65 and all(conf[x] != conf[y] for x, y in got)
    # small instance: every valid matching about equally likely
    monkeypatch.setattr(m, "N_TEAMS", 8)
    small = np.array([0, 0, 0, 1, 1, 2, 2, 3])
    rng = np.random.default_rng(1)
    c = Counter(tuple(sorted(tuple(sorted(p)) for p in m.cross_round(rng, small))) for _ in range(20000))
    assert len(c) == 48 and max(c.values()) / min(c.values()) < 1.4


def test_cross_round_fails_loudly_when_no_valid_matching_is_drawn(monkeypatch):
    import numpy as np
    import pytest

    m = _load()
    monkeypatch.setattr(m, "N_TEAMS", 4)
    monkeypatch.setattr(m, "MAX_CROSS_ATTEMPTS", 50)
    with pytest.raises(RuntimeError, match="no valid matching in 50 attempts"):
        m.cross_round(np.random.default_rng(0), np.array([0, 0, 0, 1]))
