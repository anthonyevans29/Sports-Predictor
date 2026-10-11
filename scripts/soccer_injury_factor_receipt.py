"""
SOCCER INJURY FACTOR RECEIPT (ARCHITECT 2026-10-11, addendum 40 item 6, #430; finding #425), READ-ONLY:

"THE RECEIPT, a script, read-only: scripts/soccer_injury_factor_receipt.py. For every graded PL prediction whose
factor_breakdown carries the injury counts: the stored probabilities, and the same game re-priced with the injury cut
taken back out of its expected goals. Log loss both ways: over all of them, by the difference in list length (0, 1 to
2, 3 to 5, 6 or more), and for the positive-edge cohort (edge of +5pp or more against the market) with how many of
those keep +5pp without the cut. The operator runs it on the laptop and the console goes on the Issue. No model change
rides it: what it shows decides whether a candidate goes to the gate."

How it re-prices (src/models/factors.injury_adjustment, src/models/poisson.predict_match, read from the code):
- A graded PL prediction: a predictions row of a FINISHED PL match with its scores, with a prediction_outcomes row,
  whose factor_breakdown carries home_injuries_count and away_injuries_count.
- The stored expected goals (expected_home_score / expected_away_score) already carry the cut. The cut is taken back
  out by dividing each side by (1 - its reduction). The reduction is min(0.25, 0.03 x the side's count): every name
  weighs the default 3%, because the stored rows carry no position (the finding). The factor's own note
  ("home missing N (-X% xG)") is checked against it; a side with names and no such note cannot agree.
- #437 RULED (ARCHITECT 2026-10-11, addendum 41 item 2): "Every aggregate of the receipt is taken over the rows it can
  stand behind: the stored 1X2 rebuilt to three decimals, and the factor's own note agreeing with the cut the receipt
  takes back. A row that fails either is left out of every aggregate, counted by reason and listed. The line over all
  rows stays, marked as such." No cut is taken back from the note's rounded percentage: a row whose note disagrees is
  left out, not adjusted.
- The 1X2 is rebuilt from the expected goals as predict_match builds it: independent Poisson to the model's
  max_goals, the Dixon-Coles correction at the model version's poisson.dixon_coles_rho, normalized. As a check, the
  stored expected goals (cut kept) are rebuilt the same way and compared with the stored probabilities: the count
  that reproduces to three decimals is printed.
- Log loss: -ln(p of the result). The market: THE grading close (src/walters/close.grading_close, the books' close,
  else the snapshot close, else the Kalshi-only mid). Edge = the stored pick's probability minus that side's fair
  probability, in pp; the positive-edge cohort is edge >= +5pp; "keeps +5pp" = the same side's re-priced edge is
  still >= +5pp. A game with no priced close is out of the cohort and counted.
- List-length difference = |home count - away count|.

Opens the database mode=ro (URI); where a copy refuses that, the plain path with PRAGMA query_only = ON, and says
which form it used (#421's rule). Writes nothing.

    python3 scripts/soccer_injury_factor_receipt.py [--competition PL] [--db PATH] [--list]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_IMPACT = 0.03            # src/models/factors.injury_adjustment: a name with no stored position
CAP = 0.25                       # ... "Cap at 25% reduction"
EDGE_PP = 5.0                    # the positive-edge cohort
BUCKETS = (("0", 0, 0), ("1-2", 1, 2), ("3-5", 3, 5), ("6+", 6, 10 ** 6))
NOTE = re.compile(r"^(home|away) missing (\d+) \(-(\d+)% xG\)$")
SIDES = ("HOME", "DRAW", "AWAY")
FAMILY = "soccer_elo_poisson"


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            url = os.getenv("DATABASE_URL")
        except ImportError:
            pass
    url = url or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the receipt is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_session(p: Path):
    """(session, form): mode=ro first; a copy that refuses it: the plain path with query_only set (#421)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    if not p.exists():
        raise SystemExit(f"no database at {p}")
    try:
        eng = create_engine(f"sqlite:///file:{p.resolve()}?mode=ro&uri=true")
        with eng.connect() as c:
            c.execute(text("SELECT 1 FROM predictions LIMIT 1"))
        return Session(eng), "mode=ro URI"
    except Exception:  # noqa: BLE001 - a copy that refuses mode=ro
        eng = query_only_engine(p)
        with eng.connect() as c:
            c.execute(text("SELECT 1 FROM predictions LIMIT 1"))
        return Session(eng), "plain path with PRAGMA query_only = ON (mode=ro refused)"


def query_only_engine(p: Path):
    """The fallback (#421): the plain path, every connection set PRAGMA query_only = ON (a write fails)."""
    from sqlalchemy import create_engine, event
    eng = create_engine(f"sqlite:///{p}")

    @event.listens_for(eng, "connect")
    def _ro(dbapi_con, _):
        dbapi_con.execute("PRAGMA query_only = ON")
    return eng


def poisson_as_of(params: dict, at) -> tuple[float, int]:
    """(rho, max_goals) as the prediction computed at `at` read them (Codex on #435): the version's current
    poisson block, with every audited set-soccer-config edit made after `at` walked back (manual_config_edits:
    {"ts", "field": "poisson.<name>", "from", "to"}; "(default)" = PoissonConfig's default)."""
    from src.models.poisson import PoissonConfig
    dflt = PoissonConfig()
    pz = dict((params or {}).get("poisson") or {})
    vals = {"dixon_coles_rho": pz.get("dixon_coles_rho", dflt.dixon_coles_rho),
            "max_goals": pz.get("max_goals", dflt.max_goals)}
    stamp = at.isoformat() if at is not None else None
    for e in sorted((params or {}).get("manual_config_edits") or [], key=lambda e: str(e.get("ts") or ""),
                    reverse=True):
        f = str(e.get("field") or "")
        if not f.startswith("poisson.") or f[8:] not in vals or stamp is None or str(e.get("ts") or "") <= stamp:
            continue
        old = e.get("from")
        vals[f[8:]] = getattr(dflt, f[8:]) if old in (None, "(default)") else old
    return float(vals["dixon_coles_rho"]), int(vals["max_goals"])


def reduction(count: int) -> float:
    """injury_adjustment's own arithmetic: the per-name impacts summed, then capped."""
    return min(CAP, sum([DEFAULT_IMPACT] * max(0, int(count))))


def one_x_two(hxg: float, axg: float, rho: float, max_k: int) -> dict:
    """predict_match's 1X2 from expected goals (Poisson, Dixon-Coles at rho, normalized)."""
    def pmf(lam):
        return [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(max_k + 1)]
    hp, ap = pmf(max(0.05, hxg)), pmf(max(0.05, axg))
    m = [[hp[i] * ap[j] for j in range(max_k + 1)] for i in range(max_k + 1)]
    if rho != 0.0 and max_k >= 1:
        lam, mu = max(0.05, hxg), max(0.05, axg)
        m[0][0] *= (1.0 - lam * mu * rho)
        m[1][0] *= (1.0 + mu * rho)
        m[0][1] *= (1.0 + lam * rho)
        m[1][1] *= (1.0 - rho)
        m = [[max(0.0, x) for x in r] for r in m]
    h = sum(m[i][j] for i in range(max_k + 1) for j in range(i))
    d = sum(m[i][i] for i in range(max_k + 1))
    a = sum(m[i][j] for i in range(max_k + 1) for j in range(i + 1, max_k + 1))
    t = h + d + a
    return {"HOME": h / t, "DRAW": d / t, "AWAY": a / t}


def result_of(hs: int, as_: int) -> str:
    return "HOME" if hs > as_ else "AWAY" if hs < as_ else "DRAW"


def ll(p: float) -> float:
    return -math.log(max(p, 1e-15))


def bucket(diff: int) -> str:
    return next(name for name, lo, hi in BUCKETS if lo <= diff <= hi)


def note_mismatch(fb: dict) -> list[str]:
    """The factor's own notes against the default-weight reduction: the sides that disagree. A side with names and no
    note cannot agree (#437 RULED: the note must agree with the cut the receipt takes back)."""
    out, noted = [], set()
    for n in fb.get("factor_notes") or []:
        m = NOTE.match(str(n))
        if m:
            side, cnt, pct = m.group(1), int(m.group(2)), int(m.group(3))
            noted.add(side)
            if cnt != fb.get(f"{side}_injuries_count") or pct != int(reduction(cnt) * 100):
                out.append(f"{side}: note '{n}'")
    for side in ("home", "away"):
        c = fb.get(f"{side}_injuries_count")
        if isinstance(c, int) and c > 0 and side not in noted:
            out.append(f"{side}: {c} name(s), no note")
    return out


LEFT_OUT = ("stored 1X2 not rebuilt to 3 decimals", "factor note disagrees with the cut taken back")


def left_out(x: dict) -> list[str]:
    """#437 RULED: the reasons a row is left out of every aggregate (empty: the receipt stands behind it)."""
    return ([LEFT_OUT[0]] if not x["reproduces"] else []) + ([LEFT_OUT[1]] if x["note_mismatch"] else [])


def rows(s, competition: str) -> tuple[list[dict], dict]:
    from sqlalchemy import select
    from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Prediction, PredictionOutcome, Sport
    from src.walters.close import grading_close, priced
    comp = s.execute(select(Competition).where(Competition.code == competition)).scalars().all()
    comp = [c for c in comp if str(getattr(c.sport, "value", c.sport)).lower() == "soccer"]
    if len(comp) != 1:
        raise SystemExit(f"REFUSED: {len(comp)} soccer competitions with code {competition}")
    q = (select(Prediction, Match).join(Match, Match.id == Prediction.match_id)
         .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
         .where(Match.competition_id == comp[0].id, Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None), Match.away_score.is_not(None))
         .order_by(Match.utc_date, Prediction.id))
    params: dict = {}
    closes: dict = {}
    out, skipped = [], {"no injury counts": 0, "no expected goals": 0}
    seen = set()
    for pred, m in s.execute(q).all():
        if pred.id in seen:
            continue
        seen.add(pred.id)
        fb = pred.factor_breakdown or {}
        hc, ac = fb.get("home_injuries_count"), fb.get("away_injuries_count")
        if not isinstance(hc, int) or not isinstance(ac, int):
            skipped["no injury counts"] += 1
            continue
        if pred.expected_home_score is None or pred.expected_away_score is None:
            skipped["no expected goals"] += 1
            continue
        if pred.model_version not in params:      # Codex on #435: the soccer Elo/Poisson row of that version only
            mv = s.execute(select(ModelVersion).where(
                ModelVersion.version == pred.model_version, ModelVersion.sport == Sport.SOCCER,
                ModelVersion.model_family == FAMILY)).scalars().first()
            params[pred.model_version] = ((mv.parameters or {}) if mv else None)
        known = params[pred.model_version] is not None
        rho, max_k = poisson_as_of(params[pred.model_version] or {}, pred.computed_at)
        stored = {"HOME": pred.home_win_prob, "DRAW": pred.draw_prob, "AWAY": pred.away_win_prob}
        hxg, axg = pred.expected_home_score, pred.expected_away_score
        rebuilt = one_x_two(hxg, axg, rho, max_k)
        bare = one_x_two(hxg / (1 - reduction(hc)), axg / (1 - reduction(ac)), rho, max_k)
        res = result_of(m.home_score, m.away_score)
        if m.id not in closes:
            cl = grading_close(s, m)
            closes[m.id] = cl["fair"] if priced(cl) else None
        fair = closes[m.id]
        pick = max(SIDES, key=lambda k: stored[k] or 0)
        edge = (stored[pick] - fair[pick]) * 100 if fair and fair.get(pick) is not None else None
        edge_bare = (bare[pick] - fair[pick]) * 100 if edge is not None else None
        out.append({"prediction_id": pred.id, "match_id": m.id, "game": f"{m.away_team.name} @ {m.home_team.name}",
                    "kickoff": m.utc_date.isoformat() if m.utc_date else None, "model_version": pred.model_version,
                    "counts": (hc, ac), "diff": abs(hc - ac), "result": res, "stored": stored, "bare": bare,
                    "reproduces": all(stored[k] is not None and abs(rebuilt[k] - stored[k]) < 5e-4 for k in SIDES),
                    "model_params_found": known, "ll_stored": ll(stored[res]), "ll_bare": ll(bare[res]),
                    "pick": pick, "edge_pp": edge, "edge_bare_pp": edge_bare, "note_mismatch": note_mismatch(fb)})
    return out, skipped


def summary(rs: list[dict]) -> dict:
    """#437 RULED: every aggregate over the rows the receipt stands behind; the all-rows line kept, marked."""
    def agg(xs):
        n = len(xs)
        return {"n": n, "ll_stored": round(sum(x["ll_stored"] for x in xs) / n, 4) if n else None,
                "ll_without_cut": round(sum(x["ll_bare"] for x in xs) / n, 4) if n else None}
    ok = [x for x in rs if not left_out(x)]
    coh = [x for x in ok if x["edge_pp"] is not None and x["edge_pp"] >= EDGE_PP]
    return {"all_rows_reference": agg(rs), "all": agg(ok),
            "by_diff": {name: agg([x for x in ok if bucket(x["diff"]) == name]) for name, _, _ in BUCKETS},
            "positive_edge": {**agg(coh), "keep_5pp_without_cut": sum(1 for x in coh if x["edge_bare_pp"] >= EDGE_PP)},
            "no_priced_close": sum(1 for x in ok if x["edge_pp"] is None),
            "left_out": {r: sum(1 for x in rs if r in left_out(x)) for r in LEFT_OUT},
            "left_out_rows": sum(1 for x in rs if left_out(x)),
            "reproduce_3dp": sum(1 for x in rs if x["reproduces"]),
            "note_mismatch": sum(1 for x in rs if x["note_mismatch"]),
            "model_params_missing": sum(1 for x in rs if not x["model_params_found"])}


def report(rs: list[dict], skipped: dict, competition: str, listing: bool, echo=print) -> dict:
    sm = summary(rs)
    echo(f"{competition}: graded predictions with injury counts {len(rs)} · distinct games "
         f"{len({x['match_id'] for x in rs})} · left out: " + ", ".join(f"{k} {v}" for k, v in skipped.items()))
    echo(f"  stored 1X2 rebuilt from the stored expected goals to 3 decimals: {sm['reproduce_3dp']}/{len(rs)}"
         f" · factor notes disagreeing with the default 3% weight: {sm['note_mismatch']}"
         f" · model version parameters not found (PoissonConfig defaults): {sm['model_params_missing']}"
         " · rho and max_goals as of each prediction (set-soccer-config edits walked back)")

    def line(label, a):
        if not a["n"]:
            return f"  {label:<26} n 0"
        d = a["ll_without_cut"] - a["ll_stored"]
        return (f"  {label:<26} n {a['n']:>4} · log loss stored {a['ll_stored']:.4f} · without the cut "
                f"{a['ll_without_cut']:.4f} · difference {d:+.4f}")
    echo(f"  left out of every aggregate (#437 RULED): {sm['left_out_rows']} row(s) · "
         + " · ".join(f"{r}: {n}" for r, n in sm["left_out"].items()))
    for x in rs:
        if left_out(x):
            echo(f"    LEFT OUT {x['prediction_id']} · {x['game']} {x['kickoff']} · {'; '.join(left_out(x))}"
                 + (f" · {'; '.join(x['note_mismatch'])}" if x["note_mismatch"] else ""))
    echo("LOG LOSS (lower is better; difference = without the cut minus stored; over the rows the receipt stands behind)")
    echo(line("ALL ROWS (reference)", sm["all_rows_reference"]) + "  ← every row, the left-out ones included")
    echo(line("all", sm["all"]))
    for name, _, _ in BUCKETS:
        echo(line(f"list-length diff {name}", sm["by_diff"][name]))
    pe = sm["positive_edge"]
    echo(line(f"edge >= +{EDGE_PP:g}pp vs the close", pe))
    echo(f"  of the positive-edge cohort, keep +{EDGE_PP:g}pp without the cut: {pe['keep_5pp_without_cut']}/{pe['n']}"
         f" · games with no priced close (out of the cohort): {sm['no_priced_close']}")
    if listing:
        echo("ROWS (prediction · game · counts home/away · result · stored H/D/A · without the cut H/D/A · pick edge "
             "stored / without)")
        for x in rs:
            f3 = lambda p: "/".join(f"{p[k]:.3f}" for k in SIDES)      # noqa: E731
            e = "-" if x["edge_pp"] is None else f"{x['edge_pp']:+.1f} / {x['edge_bare_pp']:+.1f}pp"
            echo(f"  {x['prediction_id']} · {x['game']} {x['kickoff']} · {x['counts'][0]}/{x['counts'][1]} · "
                 f"{x['result']} · {f3(x['stored'])} · {f3(x['bare'])} · {x['pick']} {e}"
                 + (f" · NOTE {'; '.join(x['note_mismatch'])}" if x["note_mismatch"] else ""))
    echo("SOCCER-INJURY-FACTOR " + json.dumps({"competition": competition, **sm}, sort_keys=True))
    return sm


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 40 item 6: the soccer injury factor, measured")
    ap.add_argument("--competition", default="PL")
    ap.add_argument("--db")
    ap.add_argument("--list", action="store_true", help="also print one line per prediction")
    a = ap.parse_args(argv)
    s, form = open_session(db_path(a.db))
    try:
        print(f"read-only open: {form}")
        rs, skipped = rows(s, a.competition)
        report(rs, skipped, a.competition, a.list)
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
