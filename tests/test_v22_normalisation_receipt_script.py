"""ARCHITECT 2026-11-02 10:50 ET, addendum 216 item 1(b): the read-only line (scripts/v22_normalisation_receipt.py) on a
synthetic stored context. Throwaway SQLite files under tmp_path; never data/."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import v22_normalisation_receipt as vr  # noqa: E402


def _db(tmp_path, contexts=None, production_rows=1, params_raw=None):
    p = tmp_path / "copy.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE model_versions (id INTEGER PRIMARY KEY, sport TEXT, model_family TEXT, version TEXT, "
                "status TEXT, parameters TEXT)")
    if contexts is None:
        contexts = {"PL": {"avg_goals_per_team_per_match": 1.5, "home_field_goal_boost": 1.15},
                    "BL1": {"avg_goals_per_team_per_match": 1.6, "home_field_goal_boost": 1.10}}
    params = params_raw if params_raw is not None else json.dumps({"contexts": contexts, "poisson": {}})
    for i in range(production_rows):
        con.execute("INSERT INTO model_versions VALUES (?, 'SOCCER', 'soccer_elo_poisson', ?, 'production', ?)",
                    (i + 1, f"v2{2 + i}", params))
    con.execute("INSERT INTO model_versions VALUES (50, 'SOCCER', 'soccer_elo_poisson', 'v23', 'candidate', ?)",
                (json.dumps({"contexts": {"PL": {"avg_goals_per_team_per_match": 9.0,
                                                  "home_field_goal_boost": 1.0}}}),))
    con.execute("INSERT INTO model_versions VALUES (51, 'MLB', 'soccer_elo_poisson', 'x', 'production', '{}')")
    con.commit()
    con.close()
    return p


def _run(argv):
    lines = []
    rc = vr.main(argv, echo=lines.append)
    return rc, lines


def _summary(lines):
    last = lines[-1]
    assert last.startswith(vr.TAG + " ")
    return json.loads(last[len(vr.TAG) + 1:])


def test_the_stored_pl_context_read_and_evaluated(tmp_path):
    p = _db(tmp_path)
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    rc, lines = _run(["--db", str(p)])
    print("\n" + "\n".join(lines))
    assert rc == 0
    s = _summary(lines)
    assert s["model_version"] == "v22" and s["competition"] == "PL"               # the production row, not v23
    assert (s["g"], s["b"]) == (1.5, 1.15)
    assert s["rating"] == 0.925
    assert round(s["total"], 4) == 2.7594 and s["data_total"] == 3.0
    assert round(s["deficit_pct"], 2) == -8.02
    assert s["ratio_model"] == 1.15 and round(s["ratio_data"], 4) == 1.3529
    assert s["real_code_agrees"] is True and s["b_at_clamp"] is False
    assert s["as_run_n"] == 38 and round(s["as_run_total"], 4) == 2.8117
    assert any("mode=ro + immutable=1" in x for x in lines)
    assert any("AGREES with the expressions" in x for x in lines)
    # writes nothing: the file's bytes are unchanged and no sidecar appears
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["copy.db"]


def test_another_competition_s_stored_context(tmp_path):
    rc, lines = _run(["--db", str(_db(tmp_path)), "--competition", "BL1"])
    s = _summary(lines)
    assert rc == 0 and (s["g"], s["b"]) == (1.6, 1.10)
    assert s["rating"] == pytest.approx(0.95) and s["total"] == pytest.approx(1.6 * 2.10 * 0.95 ** 2)
    assert s["real_code_agrees"] is True


def test_a_b_at_the_clamp_is_said(tmp_path):
    ctx = {"PL": {"avg_goals_per_team_per_match": 1.4, "home_field_goal_boost": 1.30}}
    rc, lines = _run(["--db", str(_db(tmp_path, contexts=ctx))])
    s = _summary(lines)
    assert rc == 0 and s["b_at_clamp"] is True
    assert any("AT THE CLAMP" in x for x in lines)
    assert s["deficit_pct"] == pytest.approx((2.30 * 0.85 ** 2 / 2 - 1) * 100, abs=1e-3)


@pytest.mark.parametrize("kw, needle", [
    ({"production_rows": 0}, "0 production soccer_elo_poisson rows"),
    ({"production_rows": 2}, "2 production soccer_elo_poisson rows"),
    ({"contexts": {"BL1": {"avg_goals_per_team_per_match": 1.6, "home_field_goal_boost": 1.1}}},
     "stores no context for 'PL'"),
    ({"contexts": {"PL": {"avg_goals_per_team_per_match": 0, "home_field_goal_boost": 1.1}}}, "not a positive number"),
    ({"contexts": {"PL": {"avg_goals_per_team_per_match": 1.5}}}, "home_field_goal_boost = None"),
    ({"params_raw": "not json"}, "parameters is not a JSON object"),
])
def test_refusals_on_the_stored_row(tmp_path, kw, needle):
    rc, lines = _run(["--db", str(_db(tmp_path, **kw))])
    assert rc == 2 and lines[-1].startswith("REFUSED") and needle in lines[-1]


def test_refused_without_db_under_data_missing_or_not_a_database(tmp_path):
    rc, lines = _run([])
    assert rc == 2 and "no --db given" in lines[-1]
    # under the checkout's data/: refused before any existence check (nothing is created there)
    rc, lines = _run(["--db", str(vr.ROOT / "data" / "sports.db.backup")])
    assert rc == 2 and "under data/" in lines[-1]
    rc, lines = _run(["--db", str(tmp_path / "absent.db")])
    assert rc == 2 and "no DB file" in lines[-1]
    assert not (tmp_path / "absent.db").exists()
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all, just bytes" * 10)
    rc, lines = _run(["--db", str(junk)])
    assert rc == 2 and "not a database with model_versions" in lines[-1]
