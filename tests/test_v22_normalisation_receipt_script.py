"""ARCHITECT 2026-11-02 10:50 ET, addendum 216 item 1(b): the read-only line (scripts/v22_normalisation_receipt.py) on a
synthetic stored context. Throwaway SQLite files under tmp_path; never data/."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import v22_normalisation_receipt as vr  # noqa: E402


def _db(tmp_path, contexts=None, production_rows=1, params_raw=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
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
    assert s["ratio_model"] == 1.15 and round(s["data_ratio"], 4) == 1.3529
    assert s["clamped"] is False and s["clamp"] is None and s["data_ratio_bound"] is None
    assert s["real_code_agrees"] is True
    assert s["as_run_n"] == 38 and round(s["as_run_total"], 4) == 2.8117           # PL's default N
    assert any("as run at N = 38 games per team" in x for x in lines)
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


def test_the_upper_clamp_prints_a_bound_not_the_data_s_ratio(tmp_path):
    ctx = {"PL": {"avg_goals_per_team_per_match": 1.4, "home_field_goal_boost": 1.30}}
    rc, lines = _run(["--db", str(_db(tmp_path, contexts=ctx))])
    s = _summary(lines)
    assert rc == 0 and s["clamped"] is True and s["clamp"] == "upper"
    assert s["data_ratio"] is None and s["data_ratio_bound"] == {"op": ">=", "value": round(1.30 / 0.70, 6)}
    assert any("AT THE 1.30 CLAMP" in x for x in lines)
    assert any("≥ 1.857, b stored at the 1.30 clamp; the unclamped value is not stored" in x for x in lines)
    assert s["deficit_pct"] == pytest.approx((2.30 * 0.85 ** 2 / 2 - 1) * 100, abs=1e-3)   # the model's own figures
    assert s["real_code_agrees"] is True


def test_the_lower_clamp_prints_a_bound_not_the_data_s_ratio(tmp_path):
    ctx = {"PL": {"avg_goals_per_team_per_match": 1.4, "home_field_goal_boost": 1.0}}
    rc, lines = _run(["--db", str(_db(tmp_path, contexts=ctx))])
    s = _summary(lines)
    assert rc == 0 and s["clamped"] is True and s["clamp"] == "lower"
    assert s["data_ratio"] is None and s["data_ratio_bound"] == {"op": "<=", "value": 1.0}
    assert any("≤ 1.000 at the 1.0 clamp; the unclamped value is not stored" in x for x in lines)


@pytest.mark.parametrize("b, clamp", [(1.30 + 5e-13, "upper"), (1.0 - 5e-13, "lower"), (1.30 - 1e-9, None),
                                      (1.0 + 1e-9, None), (1.15, None)])
def test_the_clamp_compare_is_to_1e_12_and_the_interior_keeps_its_ratio(b, clamp):
    e = vr.expressions(1.5, b)
    assert e["clamp"] == clamp
    if clamp is None:
        assert e["data_ratio"] == pytest.approx(b / (2 - b)) and e["data_ratio_bound"] is None
    else:
        assert e["data_ratio"] is None and e["data_ratio_bound"] is not None


def test_the_clamp_bounds_are_training_s(tmp_path):
    src = (vr.ROOT / "src" / "walters" / "training.py").read_text()
    assert "home_field_goal_boost=max(1.0, min(1.30, boost))" in src
    assert (vr.CLAMP_LO, vr.CLAMP_HI) == (1.0, 1.30)


def test_another_competition_without_per_team_leaves_the_as_run_line_uncomputed(tmp_path):
    rc, lines = _run(["--db", str(_db(tmp_path)), "--competition", "BL1"])
    s = _summary(lines)
    assert rc == 0 and s["as_run_n"] is None and s["as_run_total"] is None and s["as_run_deficit_pct"] is None
    assert any("not computed (pass --per-team N: the games each team plays in one season" in x for x in lines)


def test_per_team_names_n_and_drives_the_real_shrinkage(tmp_path):
    rc, lines = _run(["--db", str(_db(tmp_path)), "--competition", "BL1", "--per-team", "34"])
    s = _summary(lines)
    w = 34 / 39
    r = w * 0.95 + (1 - w)                                    # b = 1.10: (3-b)/2 = 0.95, n/(n+5) toward 1.0
    assert rc == 0 and s["as_run_n"] == 34
    assert s["as_run_total"] == pytest.approx(1.6 * 2.10 * r * r, abs=1e-6)
    assert any("as run at N = 34 games per team" in x for x in lines)
    # PL with an explicit N overrides the 38 default
    rc, lines = _run(["--db", str(_db(tmp_path / "pl")), "--per-team", "40"])
    assert rc == 0 and _summary(lines)["as_run_n"] == 40


@pytest.mark.parametrize("n", ["0", "-2", "37"])
def test_per_team_must_be_even_and_positive(tmp_path, n):
    rc, lines = _run(["--db", str(_db(tmp_path)), "--per-team", n])
    assert rc == 2 and lines[-1].startswith("REFUSED") and "even number >= 2" in lines[-1]


def test_the_real_code_is_the_checkout_s(tmp_path):
    rc, lines = _run(["--db", str(_db(tmp_path))])
    s = _summary(lines)
    loaded = Path(s["poisson_file"])
    assert rc == 0 and loaded == (vr.ROOT / "src" / "models" / "poisson.py").resolve()
    assert vr.ROOT.resolve() in loaded.parents
    assert any(x.startswith("real code: src.models.poisson loaded from ") for x in lines)


def test_a_poisson_loaded_outside_the_checkout_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "ROOT", tmp_path / "elsewhere")
    rc, lines = _run(["--db", str(_db(tmp_path))])
    assert rc == 2 and "which is not the checkout's" in lines[-1]


def test_the_loaded_file_is_compared_exactly_not_by_ancestry(tmp_path, monkeypatch):
    """A module merely UNDER the checkout (a .venv/site-packages there, or a cwd that is an ancestor of one) never
    passes: the loaded file must BE ROOT/src/models/poisson.py. Here ROOT is set to the checkout's parent, which IS an
    ancestor of the loaded file (the old `ROOT in loaded.parents` check passed it) but not its root."""
    real = (vr.ROOT / "src" / "models" / "poisson.py").resolve()
    monkeypatch.setattr(vr, "ROOT", vr.ROOT.resolve().parent)
    assert vr.ROOT in real.parents
    rc, lines = _run(["--db", str(_db(tmp_path))])
    assert rc == 2 and "which is not the checkout's" in lines[-1]


def test_no_checkout_found_is_refused_before_any_import(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "ROOT", None)
    rc, lines = _run(["--db", str(_db(tmp_path))])
    assert rc == 2 and lines[-1].startswith("REFUSED: no checkout found")


def test_an_installed_src_never_shadows_the_checkout(tmp_path):
    """A top-level `src` package earlier on the path (PYTHONPATH here, site-packages in the finding) loses to the
    checkout: ROOT goes first on sys.path before any src.* import."""
    shadow = tmp_path / "shadow" / "src" / "models"
    shadow.mkdir(parents=True)
    (shadow.parent / "__init__.py").write_text("")
    (shadow / "__init__.py").write_text("")
    (shadow / "poisson.py").write_text("raise RuntimeError('the shadow src was imported')\n")
    db = _db(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "shadow")}
    out = subprocess.run([sys.executable, str(vr.ROOT / "scripts" / "v22_normalisation_receipt.py"), "--db", str(db)],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    s = _summary(lines)
    assert Path(s["poisson_file"]) == (vr.ROOT / "src" / "models" / "poisson.py").resolve()


def _fake_installed_src(site: Path) -> None:
    pkg = site / "src" / "models"
    pkg.mkdir(parents=True)
    (site / "src" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "poisson.py").write_text("print('FAKE INSTALLED src RAN')\nraise RuntimeError('the installed src ran')\n")


def _copy_env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE")}
    env.update(extra)
    return env


def test_a_copy_outside_a_checkout_from_a_cwd_without_src_is_refused(tmp_path):
    """The finding's case: a copy run outside any checkout, no PYTHONPATH, from a working directory with no src/ that
    is an ANCESTOR of a site-packages holding an installed top-level `src` (here the user site, PYTHONUSERBASE under
    the cwd; ~/.local or a venv under $HOME in the field). The cwd is not taken as the checkout, so the refusal comes
    before any import: exit 2, the installed module never runs."""
    copy = tmp_path / "copy"
    copy.mkdir()
    script = copy / "v22_normalisation_receipt.py"
    script.write_text((vr.ROOT / "scripts" / "v22_normalisation_receipt.py").read_text())
    db = _db(tmp_path / "db")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env = _copy_env(tmp_path, PYTHONUSERBASE=str(cwd / "ub"))
    user_site = subprocess.run([sys.executable, "-c", "import site; print(site.getusersitepackages())"], env=env,
                               cwd=cwd, capture_output=True, text=True, timeout=60).stdout.strip()
    _fake_installed_src(Path(user_site))
    out = subprocess.run([sys.executable, str(script), "--db", str(db)], cwd=cwd, env=env, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 2, out.stdout + out.stderr
    assert "FAKE INSTALLED src RAN" not in out.stdout and "the installed src ran" not in out.stderr
    assert out.stdout.splitlines()[-1].startswith("REFUSED: no checkout found")
    # the same copy with PYTHONPATH naming the checkout reads, and loads the checkout's own file
    env = _copy_env(tmp_path, PYTHONUSERBASE=str(cwd / "ub"), PYTHONPATH=str(vr.ROOT))
    out = subprocess.run([sys.executable, str(script), "--db", str(db)], cwd=cwd, env=env, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert Path(_summary(out.stdout.splitlines())["poisson_file"]) == \
        (vr.ROOT / "src" / "models" / "poisson.py").resolve()


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
    assert rc == 2 and "has a directory named data in it" in lines[-1]
    rc, lines = _run(["--db", str(tmp_path / "absent.db")])
    assert rc == 2 and "no DB file" in lines[-1]
    assert not (tmp_path / "absent.db").exists()
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all, just bytes" * 10)
    rc, lines = _run(["--db", str(junk)])
    assert rc == 2 and "not a database with model_versions" in lines[-1]


def test_any_directory_named_data_is_refused_deliberately(tmp_path):
    """Law 5, conservative and DELIBERATELY broader than the checkout's data/: a path with ANY directory named data in
    it is refused, even a real database outside the checkout."""
    rc, lines = _run(["--db", "/tmp/x/data/y.db"])
    assert rc == 2 and "a path with ANY directory named data in it is refused" in lines[-1]
    assert "deliberately broader than the checkout's data/, law 5" in lines[-1]
    real = _db(tmp_path / "x" / "data")
    assert real.is_file()
    rc, lines = _run(["--db", str(real)])
    assert rc == 2 and "has a directory named data in it" in lines[-1]


@pytest.mark.parametrize("spelling", ["DATA", "Data", "dAtA"])
def test_the_data_fence_matches_any_case(tmp_path, spelling):
    """A case-insensitive filesystem (macOS APFS's default) opens DATA/ or Data/ as data/, and Path.resolve() keeps
    the typed case there: the fence casefolds, so a real database under any spelling is refused."""
    rc, lines = _run(["--db", f"/tmp/x/{spelling}/y.db"])
    assert rc == 2 and "has a directory named data in it" in lines[-1]
    real = _db(tmp_path / "x" / spelling)
    rc, lines = _run(["--db", str(real)])
    assert rc == 2 and "has a directory named data in it" in lines[-1]
    # the checkout's own data/ in another case: refused before any existence check
    rc, lines = _run(["--db", str(vr.ROOT / spelling / "sports.db")])
    assert rc == 2 and "has a directory named data in it" in lines[-1]
