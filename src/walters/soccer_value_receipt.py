"""
SOCCER VALUE SIDES AGAINST THE CLOSE — a READ-ONLY receipt (ARCHITECT 2026-10-09, addendum 21 item 6; Issue #383;
AMENDED before any read by addendum 23 item 2). Not gate evidence and not a policy. The operator runs it; the receipt
goes to docs/receipts by PR.

The declaration is quoted AS ISSUED (DECLARATION); its withdrawn sentence (addendum 23 (b)) is printed struck
through and marked withdrawn, never deleted. The amendment (AMENDMENT, (a) to (e), verbatim) is printed beside it.

How it reads (each reading is named where it is made):
- REFUSES (exit 2, nothing written) unless the registry holds soccer-expansion-v1's run record (rho, elo_goal_coeff,
  per-league market cohorts) and its ids file (sha256 equal to the record's).
- RECONCILIATION (amendment (b)): under market_side's own rule the gate's own walk (soccer_backtest.run_soccer_backtest
  per league-season from a cold start, min_prior 40, regular-season rows, same-kickoff batching) at the run record's
  rho / elo_goal_coeff must reproduce, per league, the run record's n_priced, BOTH log-losses (model and close) and the
  cohort's count, hits and mean edge (floats to 1e-9, counts exactly). Reading: the walk must also score exactly the
  ids file's ids and each league's recorded n; those are part of the same reproduction. If anything differs, the
  receipt prints the declaration, the amendment and the difference and STOPS: no table, no PL page, exit 2.
- Bootstrap (amendment (c)): percentile 95%; the unit is the match, resampled with replacement within the cell;
  10,000 resamples; seed 20261009; the return interval from the same draws; a cell of fewer than two matches prints
  no interval.
- Buckets and ties (amendment (d)): a bucket holds its lower edge at the gate's tolerance (5.0 is in 5 to 10); the
  value outcome's edge is never negative, so under 5 is 0 to 5; ties go to the first of home, draw, away.
- Nothing is written to the DB; the receipt is markdown at a path the operator gives (never under data/).
"""
from __future__ import annotations

import os
from pathlib import Path

#: the bootstrap is SEEDED (declared "seeded bootstrap 95% interval"); fixed here, printed in the receipt.
SEED = 20261009
N_BOOT = 10000
_CHUNK = 500
EPS = 1e-9                         # market_side's own cohort tolerance (edge >= 5 - 1e-9), used at every boundary

#: (label, lo, hi) in pp of the value outcome's edge; lo inclusive, hi exclusive (both at EPS, as market_side).
BUCKETS = (("under 5pp", None, 5.0), ("5 to 10", 5.0, 10.0), ("10 to 15", 10.0, 15.0), ("15 and over", 15.0, None),
           ("5 and over", 5.0, None))
FIVE_PLUS = "5 and over"
KINDS = (("H", "home"), ("D", "draw"), ("A", "away"))
POOLED = "pooled"
PL_CODE = "PL"
PL_SEASONS = ("2024/25", "2025/26")
DEFAULT_DIR = os.path.join("docs", "receipts")

_PK = {"H": "p_home", "D": "p_draw", "A": "p_away"}
_SEL = {"H": "HOME", "D": "DRAW", "A": "AWAY"}


class ReceiptRefused(RuntimeError):
    pass


# ------------------------------------------------------------------ pure --

def fair(prices: dict) -> dict | None:
    """De-vig exactly as soccer_expansion.market_side: proportional, 1/price over the three legs. None if a leg is
    missing."""
    if not prices or not {"HOME", "DRAW", "AWAY"} <= set(prices):
        return None
    inv = {k: 1.0 / prices[k] for k in ("HOME", "DRAW", "AWAY")}
    t = sum(inv.values())
    return {k: v / t for k, v in inv.items()}


def value_row(r: dict, fair_p: dict, league: str) -> dict:
    """One priced match. The value outcome = the largest model p minus close p (ties: the first of H, D, A, as
    market_side's max breaks them); the top pick = the largest model p (same tie rule)."""
    edges = {o: r[_PK[o]] - fair_p[_SEL[o]] for o in "HDA"}
    v = max("HDA", key=lambda o: edges[o])
    top = max("HDA", key=lambda o: r[_PK[o]])
    return {"match_id": r["match_id"], "league": league, "value": v, "edge_pp": edges[v] * 100.0,
            "p_model": r[_PK[v]], "p_close": fair_p[_SEL[v]], "hit": int(r["actual"] == v),
            "top": top, "is_top": v == top, "top_edge_pp": edges[top] * 100.0, "top_hit": int(r["actual"] == top)}


def value_rows(results: list[dict], closes: dict, league: str) -> tuple[list[dict], int]:
    """(priced value rows, n unpriced) over a league's scored rows."""
    out, unpriced = [], 0
    for r in results:
        f = fair(closes.get(r["match_id"]))
        if f is None:
            unpriced += 1
            continue
        out.append(value_row(r, f, league))
    return out, unpriced


def in_bucket(edge_pp: float, lo: float | None, hi: float | None) -> bool:
    return (lo is None or edge_pp >= lo - EPS) and (hi is None or edge_pp < hi - EPS)


def bucket_of(edge_pp: float) -> str:
    """The one exclusive bucket (of the first four) an edge falls in."""
    for label, lo, hi in BUCKETS[:4]:
        if in_bucket(edge_pp, lo, hi):
            return label
    return BUCKETS[0][0]           # unreachable: the four cover the line


def bootstrap(hit_minus_close: list[float], ret: list[float], seed: int = SEED, n_boot: int = N_BOOT):
    """Seeded percentile bootstrap (2.5, 97.5) of the two means, resampling MATCHES with the same draws for both
    (paired: the return interval comes from the same draws). A fresh generator per cell, so a cell's interval never
    depends on which cells ran before it. A cell of fewer than two matches has NO interval (amendment (c))."""
    import numpy as np
    n = len(ret)
    if n < 2:
        return None, None
    a, b = np.asarray(hit_minus_close, dtype=float), np.asarray(ret, dtype=float)
    rng = np.random.default_rng(seed)
    ma, mb, done = [], [], 0
    while done < n_boot:
        k = min(_CHUNK, n_boot - done)
        idx = rng.integers(0, n, size=(k, n))
        ma.append(a[idx].mean(axis=1))
        mb.append(b[idx].mean(axis=1))
        done += k
    ma, mb = np.concatenate(ma), np.concatenate(mb)
    return (tuple(float(x) for x in np.percentile(ma, [2.5, 97.5])),
            tuple(float(x) for x in np.percentile(mb, [2.5, 97.5])))


def cell(rows: list[dict], seed: int = SEED, n_boot: int = N_BOOT) -> dict:
    """The declared columns over a set of value rows. Flat stake 1 on the value outcome at the close's FAIR decimal
    price 1 / p_close: profit p_close^-1 - 1 on a hit, -1 otherwise; the return is the mean profit per stake."""
    n = len(rows)
    if not n:
        return {"n": 0}
    hmc = [(r["hit"] - r["p_close"]) * 100.0 for r in rows]
    ret = [(r["hit"] / r["p_close"]) - 1.0 for r in rows]
    ci_hmc, ci_ret = bootstrap(hmc, ret, seed, n_boot)
    return {"n": n, "hits": sum(r["hit"] for r in rows), "mean_model_p": sum(r["p_model"] for r in rows) / n,
            "mean_close_p": sum(r["p_close"] for r in rows) / n, "hit_rate": sum(r["hit"] for r in rows) / n,
            "hit_minus_close_pp": sum(hmc) / n, "hmc_ci": ci_hmc, "return": sum(ret) / n, "return_ci": ci_ret}


def tables(by_league: dict[str, list[dict]], leagues, seed: int = SEED, n_boot: int = N_BOOT,
           pooled: bool = True) -> dict:
    """{"main": {league: {(bucket, is_top): cell}}, "kind": {league: {kind: cell}}} — leagues in order, then pooled.
    main: every bucket (the four, and 5 and over as one row) split by whether the value outcome is the model's top
    pick. kind: the 5-and-over row only, by the value outcome's kind."""
    order = list(leagues) + ([POOLED] if pooled else [])
    rows_of = {c: list(by_league.get(c) or []) for c in leagues}
    if pooled:
        rows_of[POOLED] = [r for c in leagues for r in rows_of[c]]
    main, kind = {}, {}
    for c in order:
        rs = rows_of[c]
        main[c] = {(label, t): cell([r for r in rs if in_bucket(r["edge_pp"], lo, hi) and r["is_top"] == t],
                                    seed, n_boot)
                   for label, lo, hi in BUCKETS for t in (True, False)}
        five = [r for r in rs if in_bucket(r["edge_pp"], 5.0, None)]
        kind[c] = {k: cell([r for r in five if r["value"] == k], seed, n_boot) for k, _ in KINDS}
    return {"order": order, "main": main, "kind": kind}


TOL = 1e-9                         # a float of the run record is reproduced to 1e-9; a count exactly


def _same(walk, record, tol) -> bool:
    if walk is None or record is None:
        return walk is None and record is None
    return abs(walk - record) <= tol


def reconcile_league(code: str, n_walk: int, mk: dict | None, g: dict) -> dict:
    """Amendment (b): market_side on the re-walked rows against the run record's, for one league. Each field is
    (name, walk, record, equal). Reading: the league's scored n is compared with them (the same walk)."""
    mk, rec = mk or {}, (g or {}).get("market") or {}
    ec, rc = mk.get("edge_cohort") or {}, rec.get("edge_cohort") or {}
    spec = (("scored n", n_walk, (g or {}).get("n"), 0), ("n_priced", mk.get("n_priced"), rec.get("n_priced"), 0),
            ("model log-loss", mk.get("ll_model"), rec.get("ll_model"), TOL),
            ("close log-loss", mk.get("ll_market"), rec.get("ll_market"), TOL),
            ("cohort n", ec.get("n"), rc.get("n"), 0), ("cohort hits", ec.get("hits"), rc.get("hits"), 0),
            ("cohort mean edge pp", ec.get("mean_edge_pp"), rc.get("mean_edge_pp"), TOL))
    fields = [(name, w, r, _same(w, r, tol)) for name, w, r, tol in spec]
    return {"league": code, "fields": fields, "ok": all(f[3] for f in fields)}


def reconciliation(per_league: list[dict], walked: set, ids) -> dict:
    """The whole reconciliation: every league reproduces, and the walk scored exactly the ids file's ids."""
    ids = set(ids)
    id_check = {"walked": len(walked), "n_ids": len(ids), "not_in_file": len(walked - ids),
                "not_scored": len(ids - walked), "ok": walked == ids}
    return {"ok": id_check["ok"] and all(d["ok"] for d in per_league), "ids": id_check, "per_league": per_league}


# --------------------------------------------------------------- render --

def _pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def _ci(ci, scale=1.0, pct=False):
    if ci is None or ci[0] is None:
        return "—"
    f = (lambda v: f"{v * scale:+.1f}%") if pct else (lambda v: f"{v * scale:+.2f}")
    return f"[{f(ci[0])}, {f(ci[1])}]"


def _cell_md(c: dict) -> str:
    if not c.get("n"):
        return "0 | — | — | — | — | —"
    return (f"{c['n']} | {c['mean_model_p']:.3f} | {c['mean_close_p']:.3f} | {_pct(c['hit_rate'])} | "
            f"{c['hit_minus_close_pp']:+.2f} {_ci(c['hmc_ci'])} | "
            f"{c['return'] * 100:+.1f}% {_ci(c['return_ci'], 100.0, pct=True)}")


COLS = ("n | mean model p | mean close p | hit rate | hit − close pp [95% CI] | "
        "flat-stake return at the close's fair price [95% CI]")


def render_tables(t: dict, title_of=lambda c: c) -> list[str]:
    out = []
    for c in t["order"]:
        out += ["", f"### {title_of(c)}", "", f"| edge bucket | value = top pick | {COLS} |",
                "|---|---|---|---|---|---|---|---|"]
        for label, _, _ in BUCKETS:
            for top in (True, False):
                out.append(f"| {label} | {'yes' if top else 'no'} | {_cell_md(t['main'][c][(label, top)])} |")
    out += ["", "### The 5-and-over row by the value outcome's kind", "",
            f"| league | value outcome | {COLS} |", "|---|---|---|---|---|---|---|---|"]
    for c in t["order"]:
        for k, name in KINDS:
            out.append(f"| {title_of(c)} | {name} | {_cell_md(t['kind'][c][k])} |")
    return out


DECLARATION = (
    "The operator's question is whether the model's value sides pay against the close. The gate's run record holds "
    "the count only (512 hits on 1,281 picks at 5pp or more), not the prices. Declared now so that it is not fished "
    "later (the #354 pattern). No other cut is added after the fact.",
    "- Matches: the gate's 3,445 scored ids, priced by the candidate as gated (the run record's rho and "
    "elo_goal_coeff, the gate's own walk), against the stored fdcuk_close, de-vigged as market_side does.",
    "- The value outcome of a match is the outcome with the largest model probability minus close probability.",
    "- Rows: league (PD, SA, BL1, FL1, ELC, and pooled) by edge bucket (under 5pp; 5 to 10; 10 to 15; 15 and over; "
    "and 5 and over as one row, which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 of 266, 93 "
    "of 205, 137 of 373) by whether the value outcome is the model's top pick.",
    "- One more table, for the 5-and-over row only: by the value outcome's kind (home, draw, away).",
    "- Columns: n, mean model p, mean close p, hit rate, hit minus close in pp with a seeded bootstrap 95% interval, "
    "flat-stake return at the close's fair price with its interval.",
    "- The same tables for PL 2024/25 and 2025/26 on a page of their own, for reference. PL's live read (#92) stands "
    "as declared and is not this.",
    "It is not gate evidence and not a policy. The operator runs it; the receipt goes to docs/receipts by PR.",
)


#: addendum 23 (b): this fragment of the declaration is WITHDRAWN. It stays in DECLARATION as issued and is printed
#: struck through and marked; it is never deleted.
WITHDRAWN = ("which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 of 266, 93 of 205, 137 of "
             "373")
WITHDRAWN_MARK = "[WITHDRAWN, ARCHITECT 2026-10-09 addendum 23 (b)]"

#: ARCHITECT 2026-10-09, addendum 23 item 2: the amendment, verbatim, (a) to (e). It stands beside the declaration.
AMENDMENT = (
    "(a) What was known. For 'The gate's run record holds the count only (512 hits on 1,281 picks at 5pp or more), "
    "not the prices.' read: 'Known before this declaration, from the run record: per league, the model's top picks "
    "at 5pp or more over the close, with their count, hits and mean edge (PD 79 of 212 at 11.7pp, SA 88 of 225 at "
    "11.3pp, BL1 115 of 266 at 12.4pp, FL1 93 of 205 at 11.2pp, ELC 137 of 373 at 11.7pp), and the model's and the "
    "close's log-loss on the same games. Not known: any price, any single match, any figure for a side that is not "
    "the top pick, any figure under 5pp or by bucket. The buckets are round numbers, chosen knowing that this "
    "cohort's mean edge is near 12pp.'",
    "(b) The cohort sentence is WITHDRAWN: 'which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 "
    "of 266, 93 of 205, 137 of 373'. Those cohorts are the gate's own selection, the model's top pick at 5pp or more "
    "over the close (market_side). The value outcome is another selection, and it stays as declared. In its place, "
    "before any table: 'Reconciliation. Under market_side's own rule the receipt's walk reproduces, per league, the "
    "run record's n_priced, both log-losses, and the cohort's count, hits and mean edge. If it does not, the receipt "
    "prints the difference and stops: no table.'",
    "(c) The bootstrap. 'Percentile 95% interval. The unit is the match, resampled with replacement within the cell; "
    "10,000 resamples; seed 20261009. The return interval comes from the same draws. A cell of fewer than two "
    "matches prints no interval.'",
    "(d) Bucket edges and ties. 'A bucket holds its lower edge, at the gate's own tolerance: 5.0 is in 5 to 10. The "
    "value outcome's edge is never negative, so under 5 is 0 to 5. Where two outcomes tie for the largest edge, the "
    "first of home, draw, away is taken.'",
    "(e) How to read it. 'About seventy cells are printed, each with its own uncorrected interval. Some will exclude "
    "zero by chance. The receipt describes; it tests nothing.'",
)


def _declaration_md() -> list[str]:
    """The declaration as issued, its withdrawn fragment struck through and marked (never deleted)."""
    body = [ln.replace(WITHDRAWN, f"~~{WITHDRAWN}~~ {WITHDRAWN_MARK}") for ln in DECLARATION]
    body[0] = '"' + body[0]
    body[-1] = body[-1] + '"'
    return ["> " + ln for ln in body]


def _amendment_md() -> list[str]:
    body = list(AMENDMENT)
    body[0] = '"' + body[0]
    body[-1] = body[-1] + '"'
    return ["> " + ln for ln in body]


def _num(v, tol) -> str:
    if v is None:
        return "none"
    return f"{v:.10f}" if tol else f"{v}"


def _reconciliation_md(rc: dict) -> list[str]:
    """Amendment (b), printed before any table: every compared figure, the walk's beside the run record's."""
    ids = rc["ids"]
    out = ["## Reconciliation", "",
           "Under market_side's own rule the receipt's walk must reproduce, per league, the run record's n_priced, "
           "both log-losses, and the cohort's count, hits and mean edge (amendment (b); floats to "
           f"{TOL:g}, counts exactly). Reading: the walk must also score exactly the ids file's ids and each league's "
           "recorded n.", "",
           f"- Scored ids: the walk scored {ids['walked']}, the ids file holds {ids['n_ids']} "
           f"({ids['not_in_file']} not in the file, {ids['not_scored']} in the file not scored): "
           f"{'reproduces' if ids['ok'] else 'DIFFERS'}."]
    float_fields = {"model log-loss", "close log-loss", "cohort mean edge pp"}
    for d in rc["per_league"]:
        parts = []
        for name, w, r, eq in d["fields"]:
            tol = name in float_fields
            if eq:
                parts.append(f"{name} {_num(w, tol)}")
            else:
                delta = f", walk − record {w - r:+g}" if (w is not None and r is not None) else ""
                parts.append(f"**{name}: walk {_num(w, tol)} vs record {_num(r, tol)}{delta} — DIFFERS**")
        out.append(f"- {d['league']}: " + "; ".join(parts) + f": {'reproduces' if d['ok'] else 'DOES NOT REPRODUCE'}.")
    out += ["", f"**Reconciliation: {'PASS' if rc['ok'] else 'FAIL'}.**"]
    if not rc["ok"]:
        out += ["", "The walk does not reproduce the run record, so it is not the candidate as gated. The receipt "
                    "prints the difference and stops: no table (amendment (b))."]
    return out


def _method_md(params: dict, boot: dict) -> list[str]:
    return [f"- Candidate as gated: production {params.get('production_version')}, rho {params['rho']}, "
            f"elo_goal_coeff {params['elo_goal_coeff']} (the run record's; never refit). The gate's own walk: "
            "run_soccer_backtest per league-season from a cold start, min_prior 40, regular-season rows (F3), "
            "same-kickoff fixtures predicted before any updates (F5).",
            "- Close: fdcuk_close 1X2, de-vigged proportionally (1/price over the three legs), as market_side does.",
            "- Value outcome: the largest model p minus close p (ties: first of home, draw, away). Top pick: the "
            "largest model p (same tie rule). Edge = the value outcome's model p minus close p, in pp; a bucket holds "
            f"its lower edge at market_side's tolerance ({EPS:g}): 5.0 is in 5 to 10; the value edge is never "
            "negative, so under 5 is 0 to 5.",
            "- Hit: the value outcome happened (90-minute result as stored). Flat stake 1 on the value outcome at the "
            "close's fair decimal price 1/close p; return = mean profit per stake.",
            "- Bootstrap: percentile 95% intervals; the unit is the match, resampled with replacement within the "
            f"cell; {boot['n']} resamples; numpy default_rng, seed {boot['seed']} (fresh per cell); the return "
            "interval comes from the same draws. A cell of fewer than two matches prints no interval (—)."]


def _head(data: dict) -> list[str]:
    return ["# Soccer value sides against the close — soccer-expansion-v1 scored ids", "",
            "Read-only receipt (ARCHITECT 2026-10-09, addendum 21 item 6, amended by addendum 23 item 2; Issue #383). "
            f"Generated {data['generated_at']}. **Not gate evidence and not a policy.**", "",
            "## The declaration (as issued; the withdrawn sentence struck through, not deleted)", ""] + \
        _declaration_md() + ["", "## The amendment (ARCHITECT 2026-10-09, addendum 23 item 2, verbatim)", ""] + \
        _amendment_md() + [""]


def render_main(data: dict) -> str:
    rc = data["reconciliation"]
    lines = _head(data) + _reconciliation_md(rc)
    if not rc["ok"]:
        return "\n".join(lines + [""])
    lines += ["", "## Method", ""] + _method_md(data["params"], data["boot"])
    lines += ["", f"Priced {data['n_priced']} of {data['n_scored']} scored ids ({data['n_unpriced']} without a full "
              "fdcuk_close 1X2).", "", "## Tables"]
    lines += render_tables(data["tables"])
    lines += ["", f"The PL reference page: `{data.get('pl_path') or '—'}`.", ""]
    return "\n".join(lines)


def render_pl(data: dict) -> str:
    pl = data["pl"]
    lines = [f"# PL reference — value sides against the close, PL {' + '.join(PL_SEASONS)}", "",
             "For reference only: the page of its own the declaration names (ARCHITECT 2026-10-09, addendum 21 item 6, "
             "amended by addendum 23 item 2; Issue #383). The declaration, the amendment and the reconciliation are on "
             "the receipt's main page. **PL's live read (#92) stands as declared and is not this.** Not gate "
             f"evidence and not a policy. Generated {data['generated_at']}.", "", "## Method", ""]
    lines += _method_md(data["params"], data["boot"])
    lines += [f"- PL rows: the same walk at the same params over PL {' and '.join(PL_SEASONS)} (each season from a "
              "cold start, pooled over its two seasons as each league is), every scored match; no reconciliation (PL "
              "has no run record).", "",
              f"Scored {pl['n_scored']} · priced {pl['n_priced']} ({pl['n_unpriced']} without a full fdcuk_close "
              "1X2).", "", "## Tables"]
    lines += render_tables(pl["tables"])
    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------- the DB --

def _record():
    """(entry, params, per_league, ids) — refusing unless the registry holds the run record and its ids file."""
    from src.walters import registry as reg
    from src.walters import soccer_expansion as sx
    ledger, ids_dir = sx._reg_paths()
    e = reg.get(sx.EID, ledger)
    if e is None or not e.get("run"):
        raise ReceiptRefused(f"{sx.EID} has no run record in docs/registry: this receipt reads the gate's scored ids")
    run = e["run"]
    res = run.get("result") or {}
    if res.get("rho") is None or res.get("elo_goal_coeff") is None:
        raise ReceiptRefused(f"{sx.EID}'s run record lacks rho / elo_goal_coeff: the candidate as gated is unknown")
    per = res.get("per_league") or {}
    missing = [c for c in sx.LEAGUES if c not in (res.get("dropped_before_run") or {})
               and not (((per.get(c) or {}).get("market") or {}).get("edge_cohort"))]
    if missing or not per:
        raise ReceiptRefused(f"{sx.EID}'s run record holds no >= +5pp cohort for {missing or 'any league'}")
    ids = reg._ids_of(e, ids_dir)
    if not ids:
        raise ReceiptRefused(f"{sx.EID}'s ids file ({run.get('ids_file')}) is not stored: the scored ids are unknown")
    sha = reg._ids_sha(sorted(ids))
    if run.get("ids_sha256") and sha != run["ids_sha256"]:
        raise ReceiptRefused(f"{sx.EID}'s ids file sha256 {sha[:12]}… differs from the run record's "
                             f"{run['ids_sha256'][:12]}…")
    if run.get("n_scored") is not None and run["n_scored"] != len(ids):
        raise ReceiptRefused(f"{sx.EID}'s ids file holds {len(ids)} ids, the run record {run['n_scored']}")
    params = {"production_version": res.get("production_version"), "rho": float(res["rho"]),
              "elo_goal_coeff": float(res["elo_goal_coeff"])}
    leagues = [c for c in sx.LEAGUES if c in per]
    return e, params, {c: per[c] for c in leagues}, ids, sha


def _walk(code: str, seasons, params: dict) -> list[dict]:
    """The gate's own walk (soccer_expansion.run's call, exactly), per season from a cold start, pooled."""
    from src.walters import soccer_expansion as sx
    from src.walters.soccer_backtest import run_soccer_backtest
    out = []
    for season in seasons:
        out += run_soccer_backtest(code, season, sx.MIN_PRIOR, dixon_coles_rho=params["rho"],
                                   elo_goal_coeff=params["elo_goal_coeff"], stage_filter=sx.is_regular,
                                   batch_same_kickoff=sx.BATCH_SAME_KICKOFF) or []
    return out


def _closes(ids) -> dict:
    from src.db.database import session_scope
    from src.walters import soccer_expansion as sx
    with session_scope() as s:
        out = sx._closes(s, ids)
        s.rollback()
    return out


def build(seed: int | None = None, n_boot: int | None = None, now=None) -> dict:
    """Everything the two pages need. Refuses (ReceiptRefused) before any walk without the run record or its ids file.
    When the reconciliation (amendment (b)) fails it returns the head only (reconciliation ok False): no tables, no PL
    walk. Read-only."""
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters import soccer_expansion as sx

    seed = SEED if seed is None else seed
    n_boot = N_BOOT if n_boot is None else n_boot
    e, params, per_rec, ids, sha = _record()
    by_league, walked, n_unpriced, recon = {}, set(), 0, []
    for code, g in per_rec.items():
        res = _walk(code, sx.TEST_SEASONS, params)
        walked |= {r["match_id"] for r in res}
        res = [r for r in res if r["match_id"] in ids]
        closes = _closes([r["match_id"] for r in res])
        recon.append(reconcile_league(code, len(res), sx.market_side(res, closes), g))
        by_league[code], unp = value_rows(res, closes, code)
        n_unpriced += unp
    rc = reconciliation(recon, walked, ids)
    head = {"generated_at": (now or utc_now_naive()).strftime("%Y-%m-%dT%H:%M:%SZ"), "params": params,
            "boot": {"seed": seed, "n": n_boot}, "reconciliation": rc,
            "fidelity": {"walked": len(walked), "n_ids": len(ids), "sha": sha,
                         "ids_file": (e["run"].get("ids_file") or "")}}
    if not rc["ok"]:
        return head                    # amendment (b): the difference, and stop: no table

    # PL reference page: same walk, same params; an unplaceable stage label is never guessed
    with session_scope() as s:
        unpl = [f"{PL_CODE} {se} {lab!r} ({n})" for se in PL_SEASONS
                for lab, n, pl in sx.stage_census(s, PL_CODE, se) if pl is None]
        s.rollback()
    if unpl:
        raise ReceiptRefused("PL stage / round labels the code cannot place (never guessed): " + "; ".join(unpl))
    pl_res = _walk(PL_CODE, PL_SEASONS, params)
    if not pl_res:
        raise ReceiptRefused(f"PL {' / '.join(PL_SEASONS)}: the walk scored nothing (not stored, or the season string "
                             "differs from the stored one)")
    pl_rows, pl_unp = value_rows(pl_res, _closes([r["match_id"] for r in pl_res]), PL_CODE)

    leagues = list(per_rec)
    return {**head, "n_scored": len(ids), "n_priced": sum(len(v) for v in by_league.values()),
            "n_unpriced": n_unpriced, "tables": tables(by_league, leagues, seed, n_boot),
            "pl": {"n_scored": len(pl_res), "n_priced": len(pl_rows), "n_unpriced": pl_unp,
                   "tables": tables({PL_CODE: pl_rows}, [PL_CODE], seed, n_boot, pooled=False)}}


def out_paths(out: str | None, today: str) -> tuple[str, str]:
    """(receipt, PL page). Default docs/receipts/soccer-value-sides-<date>.md; the PL page is <stem>-pl-reference.md
    beside it. Refuses a path under the repo's data/ (law 5)."""
    from src.walters import registry as reg
    root = Path(reg.ROOT).resolve()
    p = Path(out) if out else root / DEFAULT_DIR / f"soccer-value-sides-{today}.md"
    pl = p.with_name(p.stem + "-pl-reference" + (p.suffix or ".md"))
    data = (root / "data").resolve()
    for q in (p, pl):
        rq = q.resolve()
        if rq == data or data in rq.parents:
            raise ReceiptRefused(f"{q}: never under data/ (law 5)")
    return str(p), str(pl)
