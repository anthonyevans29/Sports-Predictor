"""THE NO-DB PIN's scenario (ARCHITECT 2026-11-23, addendum 453 item 3(d): "Without --db nothing changes, pinned byte for
byte."). Not a test module (pytest collects test_*.py only): tests/test_soccer_expansion_confirm_db.py runs it in a
child process, and its golden files (tests/golden/soccer_expansion_confirm_no_db.json on Python 3.12, and
soccer_expansion_confirm_no_db_py310.json on Python 3.10, whose float sum() differs in the last digit) were captured
by running this same file against origin/main 93ff8119's code, before the --db change:

    DATABASE_URL=sqlite:///<tmp>/golden.db python tests/soccer_expansion_confirm_scenario.py <checkout root> <out.json>

The child process has its OWN fresh throwaway database (DATABASE_URL, set by the caller before this file imports
anything from the checkout), so every id is the same on every run, and its own tmp registry (reg.LEDGER, reg.IDS_DIR,
reg.get point there): the real docs/registry/ is never written and data/ is never touched. The clocks the registry
stamps (registry._now, the freeze's selected_at) are pinned. The steps use only flags main had (no --db).

Each step records the command's arguments, its exit code, its whole console and every registry file's bytes after
it; the shape mirrors addendum 453 item 1 (a cohort fixture CANCELLED under the raw code ABD, the cohort's last moved
later past fixtures outside the cohort, a FINISHED fixture before the moved last passed over by the substitution)."""
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

SEASON = "2150/51"
START = datetime(2150, 8, 1)
VERDICT_AT = START + timedelta(days=50)
NOW = datetime(2150, 12, 1)
NAIVES = {"PD": {"H": 0.46, "D": 0.26, "A": 0.28, "n": 380}, "BL1": {"H": 0.43, "D": 0.24, "A": 0.33, "n": 306}}
PLAN = {"n_games": 60, "metric": "log_loss", "bar": 1.0986, "must_beat_reference": True,
        "reference": "pooled naive (each surviving league's frozen 2023/24 H/D/A frequencies) on the same 60 games, "
                     "minus 0.010"}


def entry(eid):
    return {"id": eid, "sport": "soccer", "test_set": "x", "confirmation_window": "w", "confirmation_plan": PLAN,
            "status": "confirming",
            "run": {"run_at": "2150-09-01T00:00:00Z", "ids_file": f"docs/registry/ids/{eid}.txt",
                    "result": {"verdict": "PASS — surviving set PD, BL1", "surviving": ["PD", "BL1"],
                               "per_league": {c: {"naive_freq": NAIVES[c]} for c in NAIVES},
                               "production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}},
            "verdict": {"verdict": "PASS", "ruling": "ARCHITECT: pass", "at": VERDICT_AT.strftime("%Y-%m-%dT%H:%M:%SZ")}}


def build_world(s, rng):
    """PD and BL1 (surviving) and SA (not): 45 finished regular rows per surviving league before the verdict, then 35
    per league after it on shared kickoffs, all FINISHED FT; distractors after the verdict (a play-off row, an SA row,
    a stale orphan, a test-set id). A production soccer model row whose params differ from the run record's (the NOTE
    line). Returns (eligible ids in (kickoff, id) order, the test-set id)."""
    from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Sport, Team
    teams = {}
    for code in ("PD", "BL1", "SA"):
        c = Competition(sport=Sport.SOCCER, code=code, name=code, area="x", type="LEAGUE")
        s.add(c)
        s.flush()
        t = [Team(sport=Sport.SOCCER, name=f"SXD {code} {i}") for i in range(6)]
        s.add_all(t)
        s.flush()
        teams[code] = (c, t)

    def add(code, when, stage, status=MatchStatus.FINISHED, raw="FT", score=True):
        c, t = teams[code]
        h, a = rng.sample(range(6), 2)
        m = Match(sport=Sport.SOCCER, competition_id=c.id, season=SEASON, utc_date=when, status=status,
                  status_raw=raw, home_team_id=t[h].id, away_team_id=t[a].id,
                  home_score=rng.randint(0, 3) if score else None, away_score=rng.randint(0, 3) if score else None,
                  stage=stage)
        s.add(m)
        s.flush()
        return m
    for code in ("PD", "BL1"):
        for k in range(45):
            add(code, START + timedelta(days=k), f"Regular Season - {k + 1}")
    elig = []
    for k in range(35):
        for code in ("PD", "BL1"):
            m = add(code, VERDICT_AT + timedelta(days=1 + k, hours=15), f"Regular Season - {46 + k}")
            elig.append((m.utc_date, m.id))
    early = VERDICT_AT + timedelta(hours=3)
    add("PD", early, "Relegation Play-offs - Final")
    add("SA", early, "Regular Season - 1")
    add("PD", early, "Regular Season - 2", status=MatchStatus.STALE_ORPHAN, raw=None, score=False)
    test_id = add("PD", early, "Regular Season - 3").id
    s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v99", status="production",
                       parameters={"poisson": {"dixon_coles_rho": -0.05, "elo_goal_coeff": 0.0007}}))
    s.flush()
    return [i for _, i in sorted(elig)], test_id


def main(root: str, out: str) -> None:
    sys.path.insert(0, str(Path(root).resolve()))
    from click.testing import CliRunner

    import src.timeutil as tu
    from src.db.database import init_db, session_scope
    from src.db.schema import Match, MatchStatus
    from src.walters import registry as reg
    from src.walters import soccer_expansion as sx

    import cli

    init_db()
    reg_dir = Path(tempfile.mkdtemp(prefix="sx-golden-reg-", dir=os.getcwd()))   # under the caller's cwd (tmp_path)
    ids_dir = reg_dir / "ids"
    ids_dir.mkdir()
    led = reg_dir / "experiments.json"
    with session_scope() as s:
        ids, test_id = build_world(s, random.Random(453))
    (ids_dir / f"{sx.EID}.txt").write_text(f"{test_id}\n")
    led.write_text(json.dumps([entry(sx.EID)]))
    real_get = reg.get
    reg.LEDGER, reg.IDS_DIR = str(led), str(ids_dir)
    reg.get = lambda eid, path=None: real_get(eid, str(led))
    reg.cross_ref_guard = lambda eid, no_fetch=False, repo=None: f"cross-ref guard: test stub ({eid})"
    reg._now = lambda: "2150-12-01T00:00:00Z"
    tu.utc_now_naive = lambda: NOW
    sx.utc_now_naive = lambda: NOW

    def snap():
        files = {"experiments.json": led.read_text()}
        files.update({f"ids/{p.name}": p.read_text() for p in sorted(ids_dir.iterdir())})
        return {k: v.replace(str(reg_dir), "<REG>") for k, v in files.items()}

    steps = []

    def run(*args):
        r = CliRunner().invoke(cli.cli, ["soccer-expansion-confirm", *args])
        if r.exception is not None and not isinstance(r.exception, SystemExit):
            raise r.exception
        steps.append({"args": list(args), "exit_code": r.exit_code, "output": r.output, "registry": snap()})

    def put(mid, **kw):
        with session_scope() as s:
            m = s.get(Match, mid)
            for k, v in kw.items():
                setattr(m, k, v)

    run()                                                           # provisional
    run("--record", "--ruling", "ARCHITECT: x")                     # refused: not frozen
    run("--freeze-cohort", "--no-fetch")
    run()                                                           # frozen, complete
    run("--substitute")                                             # nothing released
    released, last, passed = ids[3], ids[59], ids[60]
    with session_scope() as s:
        moved = s.get(Match, ids[62]).utc_date + timedelta(hours=1)    # the cohort's last, moved past ids[60..63]
    put(released, status=MatchStatus.CANCELLED, status_raw="ABD", home_score=None, away_score=None)
    put(last, utc_date=moved, status=MatchStatus.SCHEDULED, status_raw="NS", home_score=None, away_score=None)
    assert passed not in ids[:60]
    run()                                                           # 1 unscoreable, 1 scheduled
    run("--substitute")                                             # 453 item 2(b): after the moved last
    run()
    run("--record", "--ruling", "ARCHITECT: x")                     # refused: the moved last is pending
    put(last, status=MatchStatus.FINISHED, status_raw="FT", home_score=1, away_score=1)
    run("--record")                                                 # refused: no --ruling
    run("--record", "--ruling", "ARCHITECT 2150: record it")
    run("--substitute")
    run("--freeze-cohort", "--no-fetch")                            # refused: already frozen
    Path(out).write_text(json.dumps({"ids": ids, "steps": steps}, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL", "").startswith("sqlite:///") or "/data/" in os.environ["DATABASE_URL"]:
        raise SystemExit("DATABASE_URL must name a throwaway SQLite file outside data/ (law 5)")
    main(sys.argv[1], sys.argv[2])
