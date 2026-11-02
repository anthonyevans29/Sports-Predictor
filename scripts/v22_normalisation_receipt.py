"""
THE v22 NORMALISATION RECEIPT, THE READ-ONLY LINE (ARCHITECT 2026-11-02 10:50 ET, addendum 216 item 1(b)), READ-ONLY.

THE RULING, item 1(b) verbatim: "(b) Code's receipt PR, read-only: one test that drives the REAL estimate_strengths and
the real forecast with the review's synthetic league and pins the −8.7% total (the review's script is the receipt's
citation, not repository code — it reimplements the equations), plus a read-only line that evaluates the same
expressions on the production model's stored PL context (g and b as stored) and prints the implied average-team
rating, total and home/away ratio; posted on the Issue; (c) NO change to v22: the fix is a candidate through the frozen
gate, never a patch to a live model."

WHERE THE CONTEXT IS STORED (law 1, read from the code): the production soccer model is the single model_versions row
with sport SOCCER, model_family soccer_elo_poisson and status production (training._current_production_version takes
exactly one; more or none refuses here, exit 2). Its parameters JSON holds "contexts", one per competition code
(training.py:250, written by _train_fresh_soccer at training.py:195-217 over every finished match of that code, all
seasons: g = avg_goals_per_team_per_match = total goals / (2 × matches), b = home_field_goal_boost = home mean / g,
clamped to [1.0, 1.30]). The live path reads it back at training.py:456-459 and takes the competition's at
training.py:514 (a code with no stored context falls back to CompetitionScoringContext(): g 1.4, b 1.15). A third
reader: the improve gate's holdout scorer, _score_model_on_holdout_soccer (training.py:2053-2120; contexts read at
:2073-2074, per competition at :2082), so the stored g and b reach the improve gate's score too.

WHAT IT PRINTS (the addendum's expressions, item 1, on the stored g and b): g and b as stored; the implied
average-team rating (3−b)/2 before shrinkage; the forecast total for a league of average teams g·(1+b)·((3−b)/2)²
against the data's 2g, and the % deficit; the home/away goal ratio the model expresses (b) against the data's
(b/(2−b)). A b AT A CLAMP (training.py:214, max(1.0, min(1.30, boost)); compared to 1e-12) is not the data's boost
and the unclamped value is not stored, so the data's ratio is printed as a BOUND only: "≥ 1.857" at the 1.30 clamp,
"≤ 1.000" at the 1.0 clamp (the JSON: data_ratio null, data_ratio_bound {op, value}, clamped true); an interior b
prints the ratio itself (data_ratio, data_ratio_bound null, clamped false). Beside them, the same quantities from the
REAL code (src.models.poisson: estimate_strengths and predict_match, called, never copied) on a synthetic
average-team league at the stored g and b (20 teams, a double round robin scored at the true means, Elo equal, no
factors; the pre-shrinkage rating recovered exactly from the n/(n+5) output, n = 38 in that league). The two must
agree (to 1e-9); a disagreement is printed as such, never hidden. Then the as-run figure at N games per team
(--per-team N, even: two average teams meeting N/2 times at each venue, the real estimate_strengths' n/(n+5) at
n = N): N defaults to 38 for PL ONLY (20 clubs, a double round robin); for any other --competition without
--per-team the as-run line prints "not computed" and the JSON's as_run_* are null. The label names N.

WHICH CODE (law 1): the checkout's root goes FIRST on sys.path before any src.* import (the checkout above scripts/;
for a copy run elsewhere, the first PYTHONPATH entry holding src/models/poisson.py; else the working directory, only
when it holds src/models/poisson.py), so an installed top-level `src` package never shadows it; the receipt prints the
file src.models.poisson was loaded from and refuses (exit 2) unless it IS that checkout's src/models/poisson.py
(compared exactly: a site-packages or .venv under the checkout or the working directory never passes), and refuses
when no checkout is found.

THE TEST BESIDE IT (tests/test_v22_normalisation_receipt.py): the review's league (its normalisation_diagnostic.py,
sha256 a91de689b0aa67cd4ef8548ef28bda62930ca871ca52cd2e4d9eee52bf44b677, citing training.py blob
c1bdcd4b4fd7b315ffe96f31f60aed6fc5681546 and poisson.py blob e9ccab21b640f0b5a051bdbd55d446f7426af717, origin/main's)
reproduces exactly through the real code: 3.000 in, 2.739407407407407 out (−8.6864%) at b = 1.2 with the n/(n+5)
shrinkage at n = 40 (2.673, −10.9%, before it). The addendum's "about −8% at b = 1.15" is the pre-shrinkage
average-team figure, −8.02%, which is what this line prints for b = 1.15.

READ-ONLY: --db is a .backup copy, opened through SQLite's mode=ro + immutable=1 URI (addendum 198 item 6(ii)): no row,
no sidecar, nothing written. A path with ANY directory named data in it, in any case (DATA, Data: a case-insensitive
filesystem opens them as data/), is refused (deliberately broader than the checkout's data/, law 5): a copy is never
read from any directory named data; the operator's .backup copies live outside one. No network. Standard library plus
one repo import (src.models.poisson; numpy). Exit 0 on a complete read; 2 refused: no --db, a path with a directory
named data in it, no file, not a database with model_versions, not exactly one production soccer_elo_poisson row,
parameters not a JSON object, no stored context for the competition, a stored g or b that is not a positive number, a
--per-team that is not an even number >= 2, no checkout found, or src.models.poisson not loaded from the checkout's own
file. Nothing in v22 changes (item 1(c)). Last line `V22-NORMALISATION-RECEIPT {...}`.

Run:  python3 scripts/v22_normalisation_receipt.py --db PATH [--competition PL] [--per-team N]
      PYTHONPATH=<checkout> python3 /tmp/v22_normalisation_receipt.py --db PATH [--competition PL] [--per-team N]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

_FILE = globals().get("__file__")
_HERE = Path(_FILE).resolve() if _FILE and Path(_FILE).is_file() else None
_POISSON = Path("src") / "models" / "poisson.py"


def _checkout_root() -> Path | None:
    """The checkout whose src.models.poisson is the real code: the one above scripts/ when run as a file inside a
    checkout (scripts/ beside src/models/poisson.py); for a copy run elsewhere (/tmp) or from stdin, the first
    PYTHONPATH entry holding src/models/poisson.py; else the working directory, ONLY when it holds
    src/models/poisson.py. None otherwise: load_poisson refuses (exit 2), never importing whatever `src` the path
    happens to hold (a cwd that is an ancestor of a site-packages would otherwise pass an installed `src`)."""
    if _HERE is not None and _HERE.parent.name == "scripts" and (_HERE.parents[1] / _POISSON).is_file():
        return _HERE.parents[1]
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if entry and (Path(entry) / _POISSON).is_file():
            return Path(entry).resolve()
    cwd = Path.cwd().resolve()
    return cwd if (cwd / _POISSON).is_file() else None


ROOT = _checkout_root()
# FIRST on sys.path, before any src.* import: an installed top-level `src` in site-packages (or any other path entry)
# never shadows the checkout's; the module actually loaded is printed and refused unless it IS
# ROOT/src/models/poisson.py
if ROOT is not None and (not sys.path or sys.path[0] != str(ROOT)):
    sys.path.insert(0, str(ROOT))

TAG = "V22-NORMALISATION-RECEIPT"
FAMILY = "soccer_elo_poisson"
N_TEAMS = 20                                           # the synthetic league: one PL-sized double round robin
SYNTH_N = 2 * (N_TEAMS - 1)                            # 38 matches per team in the synthetic league
AGREE_TOL = 1e-9
CLAMP_LO, CLAMP_HI = 1.0, 1.30                         # src/walters/training.py:214, max(1.0, min(1.30, boost))
CLAMP_TOL = 1e-12
DEFAULT_PER_TEAM = {"PL": 38}                          # 20 clubs, a double round robin; no other code assumed


class Refused(Exception):
    """A refused read: exit 2, never read as empty."""


def _under_data(p: Path) -> bool:
    # DELIBERATELY BROADER than the checkout's data/ (law 5): a path with ANY part named data in it, in ANY case, is
    # refused (a case-insensitive filesystem, macOS APFS's default, opens DATA/ or Data/ as data/, and Path.resolve()
    # keeps the typed case there); the checkout's own data/ is matched resolved (a symlinked data/), also casefolded
    if any(part.casefold() == "data" for part in p.parts):
        return True
    if ROOT is None:
        return False
    d = str((ROOT / "data").resolve()).casefold()
    return any(str(x).casefold() == d for x in (p, *p.parents))


def open_ro(db: str | None) -> tuple[sqlite3.Connection, str]:
    if not db:
        raise Refused("REFUSED: no --db given: the read is on a .backup copy outside any directory named data "
                      "(python3 scripts/v22_normalisation_receipt.py --db PATH)")
    path = Path(db).expanduser().resolve()
    if _under_data(path):
        raise Refused(f"REFUSED: --db {path} has a directory named data in it: a path with ANY directory named data "
                      "in it is refused (any case; deliberately broader than the checkout's data/, law 5); --db is a "
                      ".backup copy outside any directory named data")
    if not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path}: a read-only read never creates one")
    # ADDENDUM 198 item 6(ii): every --db on a copy opens with immutable=1 beside mode=ro (no sidecar is created)
    con = sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        con.execute("SELECT 1 FROM model_versions LIMIT 1")
    except sqlite3.DatabaseError as e:
        con.close()
        raise Refused(f"REFUSED: {path} is not a database with model_versions ({type(e).__name__}: {e})") from None
    return con, f"--db {path} (mode=ro + immutable=1 URI: a copy nothing else writes; no sidecar created)"


def stored_context(con: sqlite3.Connection, competition: str) -> dict:
    rows = con.execute("SELECT id, version, parameters FROM model_versions WHERE lower(sport) = 'soccer' "
                       "AND model_family = ? AND status = 'production'", (FAMILY,)).fetchall()
    if len(rows) != 1:
        raise Refused(f"REFUSED: {len(rows)} production {FAMILY} rows (exactly one is the production model)"
                      + (": " + ", ".join(str(r[1]) for r in rows) if rows else ""))
    row_id, version, raw = rows[0]
    try:
        params = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except ValueError:
        params = None
    if not isinstance(params, dict):
        raise Refused(f"REFUSED: production {FAMILY} {version}: parameters is not a JSON object")
    contexts = params.get("contexts")
    if not isinstance(contexts, dict) or not isinstance(contexts.get(competition), dict):
        have = ", ".join(sorted(contexts)) if isinstance(contexts, dict) else "none"
        raise Refused(f"REFUSED: production {FAMILY} {version} stores no context for {competition!r} (stored: "
                      f"{have}); the live path would fall back to CompetitionScoringContext() (training.py:514), "
                      "which is not a stored context")
    ctx = contexts[competition]
    g, b = ctx.get("avg_goals_per_team_per_match"), ctx.get("home_field_goal_boost")
    for name, v in (("avg_goals_per_team_per_match", g), ("home_field_goal_boost", b)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0:
            raise Refused(f"REFUSED: production {FAMILY} {version} context {competition}: {name} = {v!r} is not a "
                          "positive number (law 4: never filled)")
    return {"row_id": row_id, "version": version, "competition": competition, "g": float(g), "b": float(b),
            "stored": ctx}




def clamp_state(b: float) -> str | None:
    """'upper' / 'lower' when the stored b sits at training.py:214's clamp (to 1e-12), else None (interior)."""
    if abs(b - CLAMP_HI) <= CLAMP_TOL:
        return "upper"
    if abs(b - CLAMP_LO) <= CLAMP_TOL:
        return "lower"
    return None


def expressions(g: float, b: float) -> dict:
    """The addendum's equations (item 1). The data's home/away ratio b/(2−b) is the data's only when b is interior:
    at a clamp the stored b is not the data's boost (the unclamped value is not stored), so only a bound is known
    (b/(2−b) is increasing in b: at the 1.30 clamp the data's ratio is ≥ 1.30/0.70, at the 1.0 clamp ≤ 1.0)."""
    r = (3 - b) / 2
    total = g * (1 + b) * r * r
    clamp = clamp_state(b)
    out = {"rating": r, "total": total, "data_total": 2 * g, "deficit": total / (2 * g) - 1, "ratio_model": b,
           "clamp": clamp, "data_ratio": None, "data_ratio_bound": None}
    if clamp == "upper":
        out["data_ratio_bound"] = {"op": ">=", "value": CLAMP_HI / (2 - CLAMP_HI)}
    elif clamp == "lower":
        out["data_ratio_bound"] = {"op": "<=", "value": CLAMP_LO / (2 - CLAMP_LO)}
    else:
        out["data_ratio"] = b / (2 - b)
    return out


def load_poisson():
    """src.models.poisson, refused unless the file actually loaded IS ROOT/src/models/poisson.py, compared exactly
    (law 1: the real code is the checkout's, never an installed package of the same name, and never a site-packages
    or .venv that merely sits under the checkout or the working directory). No checkout found: refused before any
    import."""
    if ROOT is None:
        raise Refused("REFUSED: no checkout found (no scripts/ beside src/models/poisson.py, no PYTHONPATH entry "
                      "holding it, and the working directory holds none): run inside a checkout or set "
                      "PYTHONPATH=<checkout>; the real code is the checkout's, never another package named src")
    expected = (ROOT / _POISSON).resolve()
    try:
        import src.models.poisson as poisson
    except ImportError as e:
        raise Refused(f"REFUSED: src.models.poisson does not import from the checkout {ROOT} "
                      f"({type(e).__name__}: {e})") from None
    loaded = Path(poisson.__file__).resolve()
    if loaded != expected:
        raise Refused(f"REFUSED: src.models.poisson was loaded from {loaded}, which is not the checkout's {expected}: "
                      "the real code is the checkout's, never another package named src")
    return poisson, loaded


def real_code(g: float, b: float, per_team: int | None, poisson) -> dict:
    """The same quantities from src.models.poisson on a synthetic average-team league at (g, b): every fixture of a
    double round robin of 20 teams scored home g·b and away g·(2−b); Elo 1500 both sides (multipliers exp(0) = 1); no
    factors. The pre-shrinkage rating is the real output with w = n/(n+5) undone exactly (n = 38 in this league).
    The as-run figure (per_team = N, not None): the real estimate_strengths on two average teams that meet N/2 times
    at each venue (N games each, the real n/(n+5) shrinkage at n = N), then the real predict_match."""
    matches = [{"home_team_id": h, "away_team_id": a, "home_score": g * b, "away_score": g * (2 - b)}
               for h in range(N_TEAMS) for a in range(N_TEAMS) if h != a]
    ctx = poisson.CompetitionScoringContext(avg_goals_per_team_per_match=g, home_field_goal_boost=b)
    st = poisson.estimate_strengths(matches, ctx)
    w = SYNTH_N / (SYNTH_N + 5)
    att, dfn = st[0].attack, st[0].defense
    raw = poisson.TeamStrength(attack=(att - (1 - w)) / w, defense=(dfn - (1 - w)) / w)
    p = poisson.predict_match(1500.0, 1500.0, raw, raw, ctx, poisson.PoissonConfig())
    total = p.home_xg + p.away_xg
    out = {"rating": raw.attack, "rating_defense": raw.defense, "total": total, "deficit": total / (2 * g) - 1,
           "ratio_model": p.home_xg / p.away_xg, "uniform": len({round(s.attack, 12) for s in st.values()}) == 1,
           "as_run_rating": None, "as_run_total": None, "as_run_deficit": None}
    if per_team is not None:
        half = per_team // 2
        pair = ([{"home_team_id": 0, "away_team_id": 1, "home_score": g * b, "away_score": g * (2 - b)}] * half
                + [{"home_team_id": 1, "away_team_id": 0, "home_score": g * b, "away_score": g * (2 - b)}] * half)
        sr = poisson.estimate_strengths(pair, ctx)
        pr = poisson.predict_match(1500.0, 1500.0, sr[0], sr[1], ctx, poisson.PoissonConfig())
        run_total = pr.home_xg + pr.away_xg
        out.update(as_run_rating=sr[0].attack, as_run_total=run_total, as_run_deficit=run_total / (2 * g) - 1)
    return out


def _r(v, nd=6):
    return None if v is None else round(v, nd)


def report(c: dict, form: str, per_team: int | None = None, echo=print) -> dict:
    g, b = c["g"], c["b"]
    poisson, loaded = load_poisson()
    e, r = expressions(g, b), real_code(g, b, per_team, poisson)
    agree = all(abs(e[k] - r[k]) <= AGREE_TOL for k in ("rating", "total", "deficit", "ratio_model")) \
        and abs(r["rating_defense"] - e["rating"]) <= AGREE_TOL and r["uniform"]
    clamp = e["clamp"]
    at_clamp = {"upper": f" (AT THE {CLAMP_HI:.2f} CLAMP: the data's own boost is at or above it; the unclamped "
                         "value is not stored)",
                "lower": f" (AT THE {CLAMP_LO:.1f} CLAMP: the data's own boost is at or below it; the unclamped "
                         "value is not stored)"}.get(clamp, "")
    if clamp == "upper":
        data_ratio = (f"≥ {e['data_ratio_bound']['value']:.3f}, b stored at the {CLAMP_HI:.2f} clamp; "
                      "the unclamped value is not stored")
    elif clamp == "lower":
        data_ratio = (f"≤ {e['data_ratio_bound']['value']:.3f} at the {CLAMP_LO:.1f} clamp; "
                      "the unclamped value is not stored")
    else:
        data_ratio = f"{e['data_ratio']:.4f}"
    echo(f"read-only open: {form}")
    echo(f"real code: src.models.poisson loaded from {loaded} (the checkout {ROOT}'s own)")
    echo(f"production {FAMILY} {c['version']} (model_versions.id {c['row_id']}) · stored context "
         f"{c['competition']}: {json.dumps(c['stored'], sort_keys=True)}")
    echo(f"  g (avg_goals_per_team_per_match, as stored)  {g:.6f}   -> the data's total 2g = {e['data_total']:.4f}")
    echo(f"  b (home_field_goal_boost, as stored)         {b:.6f}{at_clamp}")
    echo(f"  implied average-team rating (3-b)/2          {e['rating']:.6f}   (before shrinkage)")
    echo(f"  forecast total g(1+b)((3-b)/2)^2             {e['total']:.4f}   vs 2g {e['data_total']:.4f}   "
         f"deficit {e['deficit'] * 100:+.2f}%")
    echo(f"  home/away ratio: the model expresses b       {e['ratio_model']:.4f}   the data's b/(2-b) {data_ratio}")
    echo(f"  the real code (src.models.poisson, average-team league at this g and b): rating {r['rating']:.6f} · "
         f"total {r['total']:.4f} ({r['deficit'] * 100:+.2f}%) · ratio {r['ratio_model']:.4f} · "
         f"{'AGREES with the expressions' if agree else 'DISAGREES with the expressions'} (tolerance {AGREE_TOL:g})")
    if per_team is None:
        echo("  as run (one season's n/(n+5) shrinkage toward 1.0): not computed (pass --per-team N: the games each "
             f"team plays in one season; only PL defaults, to {DEFAULT_PER_TEAM['PL']})")
    else:
        echo(f"  as run at N = {per_team} games per team (one season's n/(n+5) shrinkage toward 1.0): rating "
             f"{r['as_run_rating']:.6f} · total {r['as_run_total']:.4f} ({r['as_run_deficit'] * 100:+.2f}%)")
    echo("  Nothing in v22 changes (addendum 216 item 1(c)); a reading, no verdict, no threshold.")
    bound = e["data_ratio_bound"]
    summary = {"model_version": c["version"], "competition": c["competition"], "g": g, "b": b,
               "clamped": clamp is not None, "clamp": clamp,
               "rating": round(e["rating"], 6), "total": round(e["total"], 6),
               "data_total": round(e["data_total"], 6), "deficit_pct": round(e["deficit"] * 100, 3),
               "ratio_model": round(e["ratio_model"], 6), "data_ratio": _r(e["data_ratio"]),
               "data_ratio_bound": None if bound is None else {"op": bound["op"], "value": round(bound["value"], 6)},
               "real_code_agrees": agree, "poisson_file": str(loaded),
               "as_run_n": per_team, "as_run_total": _r(r["as_run_total"]),
               "as_run_deficit_pct": _r(None if r["as_run_deficit"] is None else r["as_run_deficit"] * 100, 3)}
    echo(f"{TAG} {json.dumps(summary, sort_keys=True)}")
    return summary


def main(argv=None, echo=print) -> int:
    ap = argparse.ArgumentParser(description="addendum 216 item 1(b): the v22 normalisation expressions on the "
                                             "production model's stored context (read-only)")
    ap.add_argument("--db", default=None,
                    help="a .backup copy, opened mode=ro + immutable=1; a path with ANY directory named data in it "
                         "(any case) is refused (deliberately broader than the checkout's data/, law 5)")
    ap.add_argument("--competition", default="PL", help="the stored context's competition code (default PL)")
    ap.add_argument("--per-team", type=int, default=None, metavar="N",
                    help="games each team plays in one season, for the as-run line (an even number: N/2 at each "
                         "venue); default 38 for PL only, otherwise the as-run line is not computed")
    a = ap.parse_args(argv)
    per_team = a.per_team if a.per_team is not None else DEFAULT_PER_TEAM.get(a.competition)
    try:
        if per_team is not None and (per_team < 2 or per_team % 2):
            raise Refused(f"REFUSED: --per-team {per_team}: N must be an even number >= 2 (the as-run league plays "
                          "N/2 games at each venue, equal home and away games per team)")
        con, form = open_ro(a.db)
        try:
            c = stored_context(con, a.competition)
        finally:
            con.close()
        report(c, form, per_team, echo)
    except Refused as ex:
        echo(str(ex))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
