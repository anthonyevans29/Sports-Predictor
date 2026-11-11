"""
THE PERFECT-XI PRICE RECEIPT (ARCHITECT 2026-11-05 08:35 ET, addendum 256 item 3; 2026-11-11 14:10 ET, addendum 343
items 4-5; lane cups, #106; roadmap step due 2026-11-20). READ-ONLY: `cup-exam --with-history-xi --db COPY`.

256 item 3, verbatim: "THE BOUNDED PROBE (read-only; Code; due 11-20; no model change, no table written): "THE
PERFECT-XI PRICE" — the exam set priced exactly as cup-exam prices it, with ONE addition: each fixture's ACTUAL XI (the
stored `history` lineups of #538 — post hoc, never an as-of feature, which is exactly why it is allowed here as a bound
and nowhere as an input) applied through production's EXISTING XI/lineup multipliers in factor_adjustment, nothing
fitted, nothing new. It answers: if a rotation term predicted the XI PERFECTLY, what would the exam read? Receipt: the
same four exam figures beside fix-v2's (mean |Δ_HOME|, rows over 8pp, the sign share, the scored count — INVALID rules
unchanged: > 2 key rows missing or < 45 scored), the per-fixture deltas, and a line counting fixtures whose stored XI
is absent (law 4: those price as today and are counted, never imputed). A cup-exam flag `--with-history-xi` on the
report-only path, refused outside report-only; a test pins that the flag changes nothing when no history lineup
exists."

343 item 4, verbatim: "the receipt's figure OF RECORD prices the history XI as `confirmed` (0.7). [...] The fallback
reading (0.3) is printed beside it, labelled "as it stands, information only", and decides nothing: 256 item 3's
threshold (mean |Δ_HOME| <= 6.0pp, <= 13 rows over 8pp, sign share >= 80%) is read on the `confirmed` figure alone. The
receipt also counts the sides whose XI multipliers do nothing (no player-season stats) and prints the figure on the
subset where at least one side has stats, labelled as a subset — information, not a second verdict. The default path
byte-identical and the no-history test as you planned; cup_exam's gate untouched."

343 item 5: the run is the architect's block, on the laptop, "on a .backup copy opened mode=ro + immutable=1".

WHAT THIS MODULE DOES: the --db copy binding (every session of the run on the copy, mode=ro + immutable=1, the standing
fence of addendum 198 item 6(ii); the path fence is mlb_pitchers_gate.check_db's: required, an existing file, never
under data/, never the configured database), and the receipt's lines, pure functions over the three pricings
cup-exam makes (fix-v2 as today; the history XI as `confirmed`, OF RECORD; the history XI as it stands, information
only), each scored by cup_exam.score_exam UNCHANGED. It prints the figures and judges nothing: the threshold and the
declaration-or-close are the architect's (the 11-21 step). Nothing is written anywhere.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from src.walters.cup_exam import MAX_MISSING, MIN_SCORED, ROW_BAR_PP, score_exam

RULING = "ARCHITECT 2026-11-05 08:35 ET, addendum 256 item 3; 2026-11-11 14:10 ET, addendum 343 item 4"
READINGS = ("confirmed", "as_it_stands")                 # training.HISTORY_XI_READINGS' keys, OF RECORD first
COPY_QUERY = "mode=ro&immutable=1&uri=true"


class Refused(Exception):
    pass


# ---- the copy binding ---------------------------------------------------------------------------------------------------

@contextmanager
def copy_binding(db):
    """EVERY session of the block on the --db copy, opened mode=ro + immutable=1 (addendum 198 item 6(ii): "every `--db`
    on a copy opens it with `immutable=1` beside `mode=ro`"): the module's engine and SessionLocal are rebound for the
    block (database.readonly_binding's pattern) and restored on exit, whatever happens. SQLite itself refuses a write;
    no sidecar is created. The path fence is mlb_pitchers_gate.check_db's (required; an existing file; never under
    data/, by path or by identity; never the configured database). Yields the resolved path."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import src.db.database as database
    from src.walters.mlb_pitchers_gate import GateRefused, check_db
    try:
        path = check_db(db)
    except GateRefused as e:
        raise Refused(str(e).replace("the gate", "cup-exam")) from None
    if any(c in str(path) for c in "?#%"):
        raise Refused(f"--db {db}: a path holding '?', '#' or '%' cannot be opened through a URI safely; copy it to a "
                      "plain path")
    eng = create_engine(f"sqlite:///file:{path.as_posix()}?{COPY_QUERY}", poolclass=NullPool,
                        connect_args={"uri": True, "check_same_thread": False})
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1 FROM matches LIMIT 1"))
    except Exception as e:  # noqa: BLE001 - an unreadable copy is a refusal, nothing read
        eng.dispose()
        raise Refused(f"--db {path}: cannot be read through a mode=ro + immutable=1 URI ({type(e).__name__}); nothing "
                      "read") from None
    saved = (database._engine, database.SessionLocal)
    database._engine = eng
    database.SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                         expire_on_commit=False)
    try:
        yield path
    finally:
        database._engine, database.SessionLocal = saved
        eng.dispose()


# ---- the receipt (pure) ---------------------------------------------------------------------------------------------------

def figures(res) -> dict:
    """The four exam figures (256 item 3) of one cup_exam.ExamResult, and its INVALID flags (rules unchanged)."""
    return {"mae_home_pp": res.mae_home_pp, "n_over": res.n_over, "sign_agree": res.sign_agree, "sign_n": res.sign_n,
            "sign_share": res.sign_share, "n_scored": res.n_scored, "missing": len(res.missing),
            "invalid": res.invalid, "under_coverage": res.under_coverage}


def _fmt(f: dict) -> str:
    mae = "—" if f["mae_home_pp"] is None else f"{f['mae_home_pp']:.2f}pp"
    share = "—" if f["sign_share"] is None else f"{f['sign_share']:.0%}"
    flags = [w for w, on in (("INVALID: > %d key rows missing" % MAX_MISSING, f["invalid"]),
                             ("INVALID: < %d scored" % MIN_SCORED, f["under_coverage"])) if on]
    return (f"mean |Δ_HOME| {mae} · rows over {ROW_BAR_PP:g}pp {f['n_over']} · sign {f['sign_agree']}/{f['sign_n']} "
            f"= {share} · scored {f['n_scored']}" + (f" · {'; '.join(flags)}" if flags else ""))


def _no_effect(row: dict, side: str) -> bool:
    return tuple(row.get(f"{side}_xi_mults") or (1.0, 1.0)) == (1.0, 1.0)


def coverage(scored_ids: list[int], hx: dict[int, dict]) -> dict:
    """Over the fixtures scored under the figure of record: how many hold a history XI on both sides, one, none (the
    absent: priced as today, counted, never imputed); and the history-XI sides whose XI multipliers do nothing, split by
    why (no player-season stats baseline; a baseline but no change); the fixtures with at least one side's stats."""
    out = {"both": 0, "one": 0, "absent": 0, "sides_with_xi": 0, "no_effect_no_stats": 0, "no_effect_other": 0,
           "effective_sides": 0, "with_stats": []}
    for mid in scored_ids:
        r = hx.get(mid) or {}
        n = sum(bool(r.get(f"{s}_history_xi")) for s in ("home", "away"))
        out[("absent", "one", "both")[n]] += 1
        for s in ("home", "away"):
            if not r.get(f"{s}_history_xi"):
                continue
            out["sides_with_xi"] += 1
            if not r.get(f"{s}_xi_baseline"):
                out["no_effect_no_stats"] += 1
            elif _no_effect(r, s):
                out["no_effect_other"] += 1
            else:
                out["effective_sides"] += 1
        if r.get("home_xi_baseline") or r.get("away_xi_baseline"):
            out["with_stats"].append(mid)
    return out


def receipt(key: list[dict], known: set[int], base: dict[int, dict], hx: dict[str, dict[int, dict]]) -> dict:
    """The three readings scored by cup_exam.score_exam (unchanged), the coverage of the figure of record, the subset
    figures (at least one side with stats; information), and the per-fixture deltas."""
    res = {"fix_v2": score_exam(key, base, known)}
    for reading in READINGS:
        res[reading] = score_exam(key, hx[reading], known)
    of_record = res["confirmed"]
    scored_ids = [r["match_id"] for r in of_record.rows]
    cov = coverage(scored_ids, hx["confirmed"])
    sub_ids = set(cov["with_stats"])
    sub_key = [k for k in key if k["match_id"] in sub_ids]
    subset = {"fix_v2": score_exam(sub_key, base, known, min_scored=0),
              "confirmed": score_exam(sub_key, hx["confirmed"], known, min_scored=0)} if sub_key else {}
    by_b = {r["match_id"]: r for r in res["fix_v2"].rows}
    by_s = {r["match_id"]: r for r in res["as_it_stands"].rows}
    deltas = []
    for r in of_record.rows:
        b, s_ = by_b.get(r["match_id"]), by_s.get(r["match_id"])
        h = hx["confirmed"].get(r["match_id"]) or {}
        deltas.append({**{k: r[k] for k in ("match_id", "date", "comp", "home", "away", "fair_H")},
                       "fix_v2_H": b["model_H"] if b else None, "fix_v2_pp": b["delta_pp"] if b else None,
                       "xi_H": r["model_H"], "xi_pp": r["delta_pp"],
                       "stand_pp": s_["delta_pp"] if s_ else None,
                       "hist": "".join(c if h.get(f"{s}_history_xi") else "-" for s, c in (("home", "H"),
                                                                                           ("away", "A"))),
                       "stats": "".join(c if h.get(f"{s}_xi_baseline") else "-" for s, c in (("home", "H"),
                                                                                             ("away", "A")))})
    return {"figures": {k: figures(v) for k, v in res.items()}, "coverage": cov, "deltas": deltas,
            "subset": {k: figures(v) for k, v in subset.items()}, "subset_n": len(sub_ids)}


def lines(rc: dict, *, db: str, coeff_mode: str, seconds: float | None = None) -> list[str]:
    f, cov = rc["figures"], rc["coverage"]
    out = ["", f"THE PERFECT-XI PRICE ({RULING}) · --db {db} (mode=ro + immutable=1) · cup coeffs {coeff_mode} · "
               "read-only, nothing written",
           f"  fix-v2 (as today, no history XI)           {_fmt(f['fix_v2'])}",
           f"  PERFECT-XI, history XI as `confirmed` (0.7) {_fmt(f['confirmed'])}   <- the figure OF RECORD",
           f"  history XI as it stands (fallback, 0.3)     {_fmt(f['as_it_stands'])}   <- as it stands, information "
           "only",
           f"  history XI coverage over the {sum(cov[k] for k in ('both', 'one', 'absent'))} fixtures scored: both "
           f"sides {cov['both']} · one side {cov['one']} · absent {cov['absent']} (law 4: an absent side prices as "
           "today, counted, never imputed)",
           f"  history-XI sides {cov['sides_with_xi']}: XI multipliers do nothing on {cov['no_effect_no_stats']} (no "
           f"player-season stats) + {cov['no_effect_other']} (stats, no change); effective on "
           f"{cov['effective_sides']}"]
    if rc["subset"]:
        out += [f"  SUBSET, information only (not a second verdict): the {rc['subset_n']} fixtures with at least one "
                "side's stats",
                f"    fix-v2      {_fmt(rc['subset']['fix_v2'])}",
                f"    PERFECT-XI  {_fmt(rc['subset']['confirmed'])}"]
    else:
        out.append("  SUBSET, information only: no scored fixture holds a side with player-season stats")
    hdr = (f"  {'date':<10} {'comp':<4} {'home':<20} {'away':<20} {'fair_H':>6} {'v2_H':>6} {'v2_pp':>6} {'xi_H':>6} "
           f"{'xi_pp':>6} {'Δpp':>5} {'0.3_pp':>6} hist stats")
    out += ["", "  PER-FIXTURE (the figure of record beside fix-v2; Δpp = xi_pp - v2_pp; hist/stats: H home, A away)",
            hdr, "  " + "-" * (len(hdr) - 2)]
    num = (lambda v, w, p: f"{v:>{w}.{p}f}" if v is not None else f"{'—':>{w}}")
    for d in rc["deltas"]:
        moved = None if d["fix_v2_pp"] is None else d["xi_pp"] - d["fix_v2_pp"]
        out.append(f"  {d['date']:<10} {d['comp']:<4} {d['home'][:20]:<20} {d['away'][:20]:<20} "
                   f"{d['fair_H']:>6.3f} {num(d['fix_v2_H'], 6, 3)} {num(d['fix_v2_pp'], 6, 1)} {d['xi_H']:>6.3f} "
                   f"{d['xi_pp']:>+6.1f} {num(moved, 5, 1)} {num(d['stand_pp'], 6, 1)} {d['hist']:>4} {d['stats']:>5}")
    out.append("  (the threshold and the declaration-or-close are the architect's, 256 item 3 / the 11-21 step; this "
               "receipt judges nothing)")
    if seconds is not None:
        out.append(f"  runtime {seconds:.0f} s")
    return out
