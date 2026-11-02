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
(b/(2−b)). Beside them, the same quantities from the REAL code (src.models.poisson: estimate_strengths and
predict_match, called, never copied) on a synthetic average-team league at the stored g and b (20 teams, a double round
robin scored at the true means, Elo equal, no factors; the pre-shrinkage rating recovered exactly from the n/(n+5)
output), and the as-run figure at n = 38 (one PL season's shrinkage). The two must agree (to 1e-9); a disagreement
is printed as such, never hidden.

THE TEST BESIDE IT (tests/test_v22_normalisation_receipt.py): the review's league (its normalisation_diagnostic.py,
sha256 a91de689b0aa67cd4ef8548ef28bda62930ca871ca52cd2e4d9eee52bf44b677, citing training.py blob
c1bdcd4b4fd7b315ffe96f31f60aed6fc5681546 and poisson.py blob e9ccab21b640f0b5a051bdbd55d446f7426af717, origin/main's)
reproduces exactly through the real code: 3.000 in, 2.739407407407407 out (−8.6864%) at b = 1.2 with the n/(n+5)
shrinkage at n = 40 (2.673, −10.9%, before it). The addendum's "about −8% at b = 1.15" is the pre-shrinkage
average-team figure, −8.02%, which is what this line prints for b = 1.15.

READ-ONLY: --db is a .backup copy OUTSIDE data/ (refused under data/ and when missing), opened through SQLite's
mode=ro + immutable=1 URI (addendum 198 item 6(ii)): no row, no sidecar, nothing written. No network. Standard
library plus one repo import (src.models.poisson; numpy). Exit 0 on a complete read; 2 refused: no --db, a path under
data/, no file, not a database with model_versions, not exactly one production soccer_elo_poisson row, parameters not
a JSON object, no stored context for the competition, or a stored g or b that is not a positive number. Nothing in
v22 changes (item 1(c)). Last line `V22-NORMALISATION-RECEIPT {...}`.

Run:  python3 scripts/v22_normalisation_receipt.py --db PATH [--competition PL]
      PYTHONPATH=<checkout> python3 /tmp/v22_normalisation_receipt.py --db PATH [--competition PL]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_FILE = globals().get("__file__")
# run as a file inside a checkout: the checkout above scripts/; run as a copy elsewhere (/tmp, with PYTHONPATH naming
# the checkout) or from stdin: the working directory, which PYTHONPATH then backs
_HERE = Path(_FILE).resolve() if _FILE and Path(_FILE).is_file() else None
ROOT = _HERE.parents[1] if _HERE is not None and (_HERE.parents[1] / "src").is_dir() else Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))                         # after PYTHONPATH: a named checkout wins

TAG = "V22-NORMALISATION-RECEIPT"
FAMILY = "soccer_elo_poisson"
N_TEAMS = 20                                           # the synthetic league: one PL-sized double round robin
PER_TEAM = 2 * (N_TEAMS - 1)                           # 38 matches per team
AGREE_TOL = 1e-9
CLAMP = (1.0, 1.30)                                    # training.py:214


class Refused(Exception):
    """A refused read: exit 2, never read as empty."""


def _under_data(p: Path) -> bool:
    return "data" in p.parts or (ROOT / "data").resolve() in (p, *p.parents)


def open_ro(db: str | None) -> tuple[sqlite3.Connection, str]:
    if not db:
        raise Refused("REFUSED: no --db given: the read is on a .backup copy OUTSIDE data/ "
                      "(python3 scripts/v22_normalisation_receipt.py --db PATH)")
    path = Path(db).expanduser().resolve()
    if _under_data(path):
        raise Refused(f"REFUSED: --db {path} is under data/ (law 5): --db is a .backup copy OUTSIDE data/")
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


def expressions(g: float, b: float) -> dict:
    """The addendum's equations (item 1)."""
    r = (3 - b) / 2
    total = g * (1 + b) * r * r
    return {"rating": r, "total": total, "data_total": 2 * g, "deficit": total / (2 * g) - 1,
            "ratio_model": b, "ratio_data": b / (2 - b)}


def real_code(g: float, b: float) -> dict:
    """The same quantities from src.models.poisson on a synthetic average-team league at (g, b): every fixture of a
    double round robin scored home g·b and away g·(2−b); Elo 1500 both sides (multipliers exp(0) = 1); no factors.
    The pre-shrinkage rating is the real output with w = n/(n+5) undone exactly."""
    from src.models.poisson import (CompetitionScoringContext, PoissonConfig, TeamStrength, estimate_strengths,
                                    predict_match)
    matches = [{"home_team_id": h, "away_team_id": a, "home_score": g * b, "away_score": g * (2 - b)}
               for h in range(N_TEAMS) for a in range(N_TEAMS) if h != a]
    ctx = CompetitionScoringContext(avg_goals_per_team_per_match=g, home_field_goal_boost=b)
    st = estimate_strengths(matches, ctx)
    w = PER_TEAM / (PER_TEAM + 5)
    att, dfn = st[0].attack, st[0].defense
    raw = TeamStrength(attack=(att - (1 - w)) / w, defense=(dfn - (1 - w)) / w)
    p = predict_match(1500.0, 1500.0, raw, raw, ctx, PoissonConfig())
    p_run = predict_match(1500.0, 1500.0, st[0], st[1], ctx, PoissonConfig())
    total, run_total = p.home_xg + p.away_xg, p_run.home_xg + p_run.away_xg
    return {"rating": raw.attack, "rating_defense": raw.defense, "total": total, "deficit": total / (2 * g) - 1,
            "ratio_model": p.home_xg / p.away_xg, "as_run_rating": att, "as_run_total": run_total,
            "as_run_deficit": run_total / (2 * g) - 1, "uniform": len({round(s.attack, 12) for s in st.values()}) == 1}


def report(c: dict, form: str, echo=print) -> dict:
    g, b = c["g"], c["b"]
    e, r = expressions(g, b), real_code(g, b)
    agree = all(abs(e[k] - r[k]) <= AGREE_TOL for k in ("rating", "total", "deficit", "ratio_model")) \
        and abs(r["rating_defense"] - e["rating"]) <= AGREE_TOL and r["uniform"]
    at_clamp = " (AT THE CLAMP: the data's own ratio is beyond it)" if b in CLAMP else ""
    echo(f"read-only open: {form}")
    echo(f"production {FAMILY} {c['version']} (model_versions.id {c['row_id']}) · stored context "
         f"{c['competition']}: {json.dumps(c['stored'], sort_keys=True)}")
    echo(f"  g (avg_goals_per_team_per_match, as stored)  {g:.6f}   -> the data's total 2g = {e['data_total']:.4f}")
    echo(f"  b (home_field_goal_boost, as stored)         {b:.6f}{at_clamp}")
    echo(f"  implied average-team rating (3-b)/2          {e['rating']:.6f}   (before shrinkage)")
    echo(f"  forecast total g(1+b)((3-b)/2)^2             {e['total']:.4f}   vs 2g {e['data_total']:.4f}   "
         f"deficit {e['deficit'] * 100:+.2f}%")
    echo(f"  home/away ratio: the model expresses b       {e['ratio_model']:.4f}   the data's b/(2-b) "
         f"{e['ratio_data']:.4f}")
    echo(f"  the real code (src.models.poisson, average-team league at this g and b): rating {r['rating']:.6f} · "
         f"total {r['total']:.4f} ({r['deficit'] * 100:+.2f}%) · ratio {r['ratio_model']:.4f} · "
         f"{'AGREES with the expressions' if agree else 'DISAGREES with the expressions'} (tolerance {AGREE_TOL:g})")
    echo(f"  as run at n = {PER_TEAM} (one season's n/(n+5) shrinkage toward 1.0): rating {r['as_run_rating']:.6f} · "
         f"total {r['as_run_total']:.4f} ({r['as_run_deficit'] * 100:+.2f}%)")
    echo("  Nothing in v22 changes (addendum 216 item 1(c)); a reading, no verdict, no threshold.")
    summary = {"model_version": c["version"], "competition": c["competition"], "g": g, "b": b,
               "b_at_clamp": b in CLAMP, "rating": round(e["rating"], 6), "total": round(e["total"], 6),
               "data_total": round(e["data_total"], 6), "deficit_pct": round(e["deficit"] * 100, 3),
               "ratio_model": round(e["ratio_model"], 6), "ratio_data": round(e["ratio_data"], 6),
               "real_code_agrees": agree, "as_run_n": PER_TEAM, "as_run_total": round(r["as_run_total"], 6),
               "as_run_deficit_pct": round(r["as_run_deficit"] * 100, 3)}
    echo(f"{TAG} {json.dumps(summary, sort_keys=True)}")
    return summary


def main(argv=None, echo=print) -> int:
    ap = argparse.ArgumentParser(description="addendum 216 item 1(b): the v22 normalisation expressions on the "
                                             "production model's stored context (read-only)")
    ap.add_argument("--db", default=None, help="a .backup copy OUTSIDE data/, opened mode=ro + immutable=1")
    ap.add_argument("--competition", default="PL", help="the stored context's competition code (default PL)")
    a = ap.parse_args(argv)
    try:
        con, form = open_ro(a.db)
        try:
            c = stored_context(con, a.competition)
        finally:
            con.close()
        report(c, form, echo)
    except Refused as ex:
        echo(str(ex))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
