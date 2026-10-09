"""
SOCCER VALUE SIDES AGAINST THE CLOSE — a READ-ONLY receipt (ARCHITECT 2026-10-09, addendum 21 item 6; Issue #383).
Not gate evidence and not a policy. The operator runs it; the receipt goes to docs/receipts by PR.

The declaration, verbatim (binding; no other cut is added):

  "The operator's question is whether the model's value sides pay against the close. The gate's run record holds the
  count only (512 hits on 1,281 picks at 5pp or more), not the prices. Declared now so that it is not fished later
  (the #354 pattern). No other cut is added after the fact.
  - Matches: the gate's 3,445 scored ids, priced by the candidate as gated (the run record's rho and elo_goal_coeff,
    the gate's own walk), against the stored fdcuk_close, de-vigged as market_side does.
  - The value outcome of a match is the outcome with the largest model probability minus close probability.
  - Rows: league (PD, SA, BL1, FL1, ELC, and pooled) by edge bucket (under 5pp; 5 to 10; 10 to 15; 15 and over; and
    5 and over as one row, which must reproduce the run record's cohorts: 79 of 212, 88 of 225, 115 of 266, 93 of
    205, 137 of 373) by whether the value outcome is the model's top pick.
  - One more table, for the 5-and-over row only: by the value outcome's kind (home, draw, away).
  - Columns: n, mean model p, mean close p, hit rate, hit minus close in pp with a seeded bootstrap 95% interval,
    flat-stake return at the close's fair price with its interval.
  - The same tables for PL 2024/25 and 2025/26 on a page of their own, for reference. PL's live read (#92) stands as
    declared and is not this.
  It is not gate evidence and not a policy. The operator runs it; the receipt goes to docs/receipts by PR."

How it reads (each reading is named where it is made):
- REFUSES unless the registry holds soccer-expansion-v1's run record (rho, elo_goal_coeff, per-league market cohorts)
  and its ids file (sha256 equal to the record's).
- FIDELITY (hard refusal, nothing written): the gate's own walk (soccer_backtest.run_soccer_backtest per league-season
  from a cold start, min_prior 40, regular-season rows, same-kickoff batching) at the run record's rho /
  elo_goal_coeff must score exactly the ids file's ids, and soccer_expansion.market_side on the re-walked rows must
  reproduce every league's recorded n_priced and >= +5pp cohort (n, hits) exactly and its model log-loss to 1e-9.
  A walk that does not reproduce the run is not the candidate as gated.
- COHORT CHECK (declared; flagged loudly, never hidden): each league's "5 and over" row, as one row (both top-pick
  splits together; hit = the value outcome happened), must equal the run record's cohort (n, hits). A mismatch is
  written as a banner at the top of the receipt with the decomposition, and the command exits 3: a finding for the
  architect (needs-ruling), never resolved here.
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
    (paired). A fresh generator per cell, so a cell's interval never depends on which cells ran before it."""
    import numpy as np
    n = len(ret)
    if n == 0:
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


def cohort_check(by_league: dict[str, list[dict]], record_per_league: dict) -> dict:
    """The declared check: each league's "5 and over" row AS ONE ROW (both top-pick splits; hit = the value outcome)
    against the run record's >= +5pp cohort (market_side: the model's TOP PICK with edge >= 5pp, hit = the top pick).
    ok iff n and hits are equal in every league. The decomposition names the difference: rows in the 5+ row whose
    value outcome is not the top pick, and cohort matches (top-pick edge >= 5) whose value outcome is another one."""
    per, ok = {}, True
    for c, g in record_per_league.items():
        coh = ((g or {}).get("market") or {}).get("edge_cohort") or {}
        rs = by_league.get(c) or []
        five = [r for r in rs if in_bucket(r["edge_pp"], 5.0, None)]
        five_top = [r for r in five if r["is_top"]]
        top_coh = [r for r in rs if r["top_edge_pp"] >= 5.0 - EPS]           # market_side's cohort, recomputed
        d = {"record": (coh.get("n"), coh.get("hits")),
             "five_plus": (len(five), sum(r["hit"] for r in five)),
             "five_plus_top": (len(five_top), sum(r["hit"] for r in five_top)),
             "five_plus_not_top": (len(five) - len(five_top), sum(r["hit"] for r in five if not r["is_top"])),
             "cohort_other_value": sum(1 for r in top_coh if not r["is_top"])}
        d["ok"] = d["five_plus"] == d["record"]
        ok = ok and d["ok"]
        per[c] = d
    rec = [v["record"] for v in per.values()]
    pooled = {"record": (sum(n or 0 for n, _ in rec), sum(h or 0 for _, h in rec)),
              "five_plus": (sum(v["five_plus"][0] for v in per.values()), sum(v["five_plus"][1] for v in per.values()))}
    return {"ok": ok, "per_league": per, "pooled": pooled}


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


def _declaration_md() -> list[str]:
    body = list(DECLARATION)
    body[0] = '"' + body[0]
    body[-1] = body[-1] + '"'
    return ["> " + ln for ln in body]


def _method_md(params: dict, boot: dict) -> list[str]:
    return [f"- Candidate as gated: production {params.get('production_version')}, rho {params['rho']}, "
            f"elo_goal_coeff {params['elo_goal_coeff']} (the run record's; never refit). The gate's own walk: "
            "run_soccer_backtest per league-season from a cold start, min_prior 40, regular-season rows (F3), "
            "same-kickoff fixtures predicted before any updates (F5).",
            "- Close: fdcuk_close 1X2, de-vigged proportionally (1/price over the three legs), as market_side does.",
            "- Value outcome: the largest model p minus close p (ties: first of home, draw, away). Top pick: the "
            "largest model p (same tie rule). Edge = the value outcome's model p minus close p, in pp; buckets are "
            f"lower-inclusive, upper-exclusive, at market_side's tolerance ({EPS:g}).",
            "- Hit: the value outcome happened (90-minute result as stored). Flat stake 1 on the value outcome at the "
            "close's fair decimal price 1/close p; return = mean profit per stake.",
            f"- Bootstrap: percentile 95% intervals, {boot['n']} resamples of the cell's matches (paired for both "
            f"columns), numpy default_rng, seed {boot['seed']} (fresh per cell)."]


def render_main(data: dict) -> str:
    chk, fid = data["check"], data["fidelity"]
    lines = [f"# Soccer value sides against the close — soccer-expansion-v1 scored ids", "",
             f"Read-only receipt (ARCHITECT 2026-10-09, addendum 21 item 6; Issue #383). Generated "
             f"{data['generated_at']}. **Not gate evidence and not a policy.**", ""]
    if not chk["ok"]:
        lines += ["> **COHORT CHECK FAILED — needs-ruling.** The declaration says the 5-and-over row must reproduce "
                  "the run record's cohorts; on this read it does not (decomposition below). These tables are NOT the "
                  "declared receipt until the architect rules.", ""]
    lines += ["## The declaration (verbatim)", ""] + _declaration_md() + ["", "## Method", ""] + _method_md(
        data["params"], data["boot"])
    lines += ["", "## Checks", "",
              f"- Fidelity (refuses on any miss): the walk scored {fid['walked']} ids, equal to the ids file "
              f"({fid['ids_file']}, {fid['n_ids']} ids, sha256 {fid['sha'][:12]}… = the run record's); market_side on "
              "the re-walked rows reproduces every league's n_priced, model log-loss and >= +5pp top-pick cohort: "
              "PASS.",
              f"- Cohort check (declared): the 5-and-over row as one row vs the run record's cohort, per league: "
              f"**{'PASS' if chk['ok'] else 'FAIL'}**.", "",
              "| league | run record cohort (hits / n) | 5-and-over row (hits / n) | of which value = top pick | "
              "of which value ≠ top pick | cohort matches whose value outcome is another | reproduces |",
              "|---|---|---|---|---|---|---|"]
    for c, d in chk["per_league"].items():
        lines.append(f"| {c} | {d['record'][1]} / {d['record'][0]} | {d['five_plus'][1]} / {d['five_plus'][0]} | "
                     f"{d['five_plus_top'][1]} / {d['five_plus_top'][0]} | {d['five_plus_not_top'][1]} / "
                     f"{d['five_plus_not_top'][0]} | {d['cohort_other_value']} | {'yes' if d['ok'] else 'NO'} |")
    p = chk["pooled"]
    lines.append(f"| pooled | {p['record'][1]} / {p['record'][0]} | {p['five_plus'][1]} / {p['five_plus'][0]} | | | "
                 f"| {'yes' if chk['ok'] else 'NO'} |")
    lines += ["", f"Priced {data['n_priced']} of {data['n_scored']} scored ids ({data['n_unpriced']} without a full "
              "fdcuk_close 1X2).", "", "## Tables"]
    lines += render_tables(data["tables"])
    lines += ["", f"The PL reference page: `{data.get('pl_path') or '—'}`.", ""]
    return "\n".join(lines)


def render_pl(data: dict) -> str:
    pl = data["pl"]
    lines = [f"# PL reference — value sides against the close, PL {' + '.join(PL_SEASONS)}", "",
             "For reference only: the page of its own the declaration names (ARCHITECT 2026-10-09, addendum 21 item 6; "
             "Issue #383). **PL's live read (#92) stands as declared and is not this.** Not gate evidence and not a "
             f"policy. Generated {data['generated_at']}.", "", "## Method", ""]
    lines += _method_md(data["params"], data["boot"])
    lines += [f"- PL rows: the same walk at the same params over PL {' and '.join(PL_SEASONS)} (each season from a "
              "cold start, pooled), every scored match; no cohort check (PL has no run record).", "",
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
    """Everything the two pages need; refuses (ReceiptRefused) before any table when the re-walk is not the gate's.
    Read-only."""
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters import soccer_expansion as sx

    seed = SEED if seed is None else seed
    n_boot = N_BOOT if n_boot is None else n_boot
    e, params, per_rec, ids, sha = _record()
    by_league, walked, n_unpriced, bad = {}, set(), 0, []
    for code, g in per_rec.items():
        res = _walk(code, sx.TEST_SEASONS, params)
        walked |= {r["match_id"] for r in res}
        res = [r for r in res if r["match_id"] in ids]
        closes = _closes([r["match_id"] for r in res])
        mk, rec = sx.market_side(res, closes) or {}, g.get("market") or {}
        ec, rc = mk.get("edge_cohort") or {}, rec.get("edge_cohort") or {}
        if (mk.get("n_priced"), ec.get("n"), ec.get("hits")) != (rec.get("n_priced"), rc.get("n"), rc.get("hits")) \
                or abs((mk.get("ll_model") or 0.0) - (rec.get("ll_model") or 0.0)) > 1e-9 or len(res) != g.get("n"):
            bad.append(f"{code}: re-walk n {len(res)} priced {mk.get('n_priced')} cohort {ec.get('hits')}/{ec.get('n')}"
                       f" ll {mk.get('ll_model')} vs record n {g.get('n')} priced {rec.get('n_priced')} cohort "
                       f"{rc.get('hits')}/{rc.get('n')} ll {rec.get('ll_model')}")
        by_league[code], unp = value_rows(res, closes, code)
        n_unpriced += unp
    if walked != set(ids):
        bad.insert(0, f"the walk scored {len(walked)} ids, the ids file holds {len(ids)} ({len(walked - set(ids))} "
                      f"not in the file, {len(set(ids) - walked)} in the file not scored)")
    if bad:
        raise ReceiptRefused("FIDELITY: the gate's walk at the run record's params does not reproduce the run, so "
                             "these are not the candidate as gated (the DB changed since the run?): " + "; ".join(bad))

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
    return {"generated_at": (now or utc_now_naive()).strftime("%Y-%m-%dT%H:%M:%SZ"), "params": params,
            "boot": {"seed": seed, "n": n_boot}, "fidelity": {"walked": len(walked), "n_ids": len(ids), "sha": sha,
                         "ids_file": (e["run"].get("ids_file") or "")},
            "n_scored": len(ids), "n_priced": sum(len(v) for v in by_league.values()), "n_unpriced": n_unpriced,
            "check": cohort_check(by_league, per_rec),
            "tables": tables(by_league, leagues, seed, n_boot),
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
