"""
THE PL POSITIVE-EDGE RECEIPT (ARCHITECT addendum 162 item 2(a); the n=30 read of #92), READ-ONLY, files only:

"The positive-edge n=30 read (#92) is mine, on Saturday from the mirror's results exports once the 30th graded PL
prediction is in (Friday's Ipswich game grades in the morning block): cohort = top pick at least +5pp over the close
(the PL benchmark stays the book close, #615's ruling; stale stamps counted), each member with its ids, prediction
stamp, close stamp and age, injury inputs (counts both sides; the one-sided guard's state), result, and whether the
Desk's final call on it was PLAY, LADDER or PASS — the read says what the cohort did; a policy change, if any, is an
audit-backed version bump, never a knob. Code: a read-only script for that receipt (scripts/pl_positive_edge_receipt.py,
from the results exports and the closing files) so the read reproduces on either machine; small, by Monday."

WHAT IT READS (the keys are printed with the output; it never opens the database):
- THE RESULTS EXPORTS: <exports>/soccer_PL_results_*.json, as `export-results --sport soccer --competition PL` writes
  them (src/walters/export.py export_results). A file that is not JSON, or whose competition_code is not PL or whose
  sport is not soccer, is counted and named, never read. Several files may hold one match (a re-export, a re-dated
  game): one row per match_id, the newest file's (its exported_at, then its name), every dropped copy counted.
- per results row: match_id, date (the match's current start), home_team / away_team, predicted.top_pick ("home_win" |
  "draw" | "away_win") and the side's probability (predicted.home_win_prob / draw_prob / away_win_prob, else
  predicted.top_pick_prob), actual.home_score / away_score / result, graded.top_pick_hit, and the grading close
  (src/walters/close.py graded_block): graded.close_fair (per side HOME / DRAW / AWAY; null = unpriced), close_at,
  close_minutes_before_start (the age of our capture), close_book_stamp_age_h (the book quote's own stamp, hours
  before the start), close_books, close_reference, close_stale_unswitched / close_stale_book (printed where present),
  and "redated" (the export's void label).
- THE CLOSING FILES: <exports>/closing_*.json through src/walters/redated.closing_rows (the one reader; host/ is never
  read). The Desk's FINAL call on a game is exec_cohorts' selection: the newest run's row within the Desk clock drift
  (desk_policy.DESK_CLOCK_DRIFT) of the results row's date; with none within it, void when redated.void_label says so,
  else the newest run's row. A closing row whose teams are not the results row's is not that game's (match ids are
  machine-local): "no closing row (teams differ)". From that row: prediction.computed_at (the prediction stamp) and
  prediction.model_version, input_quality.injuries.{home,away}.count (what the one-sided guard reads; injuries.home_count
  / away_count otherwise), desk.call / desk.pass_kind / desk.pick, and the run start.
- THE ONE-SIDED GUARD (addendum 40 item 6): desk_policy.one_sided_injuries on the row as desk_policy.normalize reads it
  (fires: the empty side named; or not), beside the switch in code now (desk_policy.INJURIES_ONE_SIDED_RULE) and the
  Desk's own record at the run (desk.pass_kind "injuries_one_sided").

THE COHORT (each reading the conservative one, law 4):
- a graded PL results row (graded.top_pick_hit true or false) whose top pick's model p minus the close's fair p for the
  same side is at least --min-gap-pp (default 5, the ruled line; it is printed, and it is not a knob to tune). The gap
  is rounded to 9 places before the comparison (float noise only: exactly +5.00pp is in, 4.99pp is out).
- the close is the results row's book close (#615's ruling: the PL benchmark stays the book close). A row whose close is
  unpriced (close_fair null, or no fair for the pick's side) is "no close", named, never in the cohort. A close read
  from a Kalshi mid (close_reference kalshi_only / kalshi; a three-way board never takes one, close.close_from_kalshi)
  would not be the book close: named and left out. A stale stamp is counted (close_book_stamp_age_h over
  close.STALE_BOOK_H is printed "stale", never dropped).
- a re-dated row (the export's "redated" label, or void now by the closing files on disk, redated.void_label) is left
  out and counted, with its label. A row with no graded hit, or no top pick, is left out and counted.

No verdict, no p-value, no threshold judgment: the read says what the cohort did. Writes nothing.

    python3 scripts/pl_positive_edge_receipt.py [--exports DIR (default exports)] [--min-gap-pp 5]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.walters import desk_policy  # noqa: E402
from src.walters.close import KALSHI_SOURCES, STALE_BOOK_H  # noqa: E402
from src.walters.exec_cohorts import _within  # noqa: E402
from src.walters.redated import closing_rows, void_counts, void_label  # noqa: E402

RULING = ("The positive-edge n=30 read (#92) is mine, on Saturday from the mirror's results exports once the 30th "
          "graded PL prediction is in (Friday's Ipswich game grades in the morning block): cohort = top pick at least "
          "+5pp over the close (the PL benchmark stays the book close, #615's ruling; stale stamps counted), each "
          "member with its ids, prediction stamp, close stamp and age, injury inputs (counts both sides; the "
          "one-sided guard's state), result, and whether the Desk's final call on it was PLAY, LADDER or PASS — the "
          "read says what the cohort did; a policy change, if any, is an audit-backed version bump, never a knob.")
RESULTS_GLOB = "soccer_PL_results_*.json"      # cli.py export-results: exports/<sport>_<COMP>_results_<date>.json
MIN_GAP_PP = 5.0                               # the ruled cohort line (addendum 162 item 2(a)), not a knob
SIDE = {"home_win": "HOME", "draw": "DRAW", "away_win": "AWAY"}        # predicted.top_pick -> close_fair's key
PROB = {"home_win": "home_win_prob", "draw": "draw_prob", "away_win": "away_win_prob"}
CALLS = ("PLAY", "LADDER", "PASS")
NO_ROW, NO_DESK, TEAMS = "no closing row", "no desk block on the closing row", "no closing row (teams differ)"
KEYS = ("results row: match_id, date, home_team, away_team, predicted.top_pick + predicted.<side>_prob (else "
        "top_pick_prob), actual.home_score/away_score/result, graded.top_pick_hit, graded.close_fair[HOME|DRAW|AWAY], "
        "close_at, close_minutes_before_start, close_book_stamp_age_h, close_books, close_reference, "
        "close_stale_unswitched, close_stale_book, redated · closing row: prediction.computed_at, "
        "prediction.model_version, input_quality.injuries.{home,away}.count (else injuries.home_count/away_count), "
        "desk.call, desk.pass_kind, desk.pick, home_team, away_team, utc_date; the run start (closing.start)")


def _num(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def read_results(exports_dir) -> dict:
    """The PL results rows, one per match_id, the newest file's: {"rows": {match id: (file name, row)}, "files": [names
    read], "unreadable": [names], "not_pl": [names], "rows_read": n, "dupes": [(match id, kept file, dropped file)]}."""
    d = Path(exports_dir)
    docs, bad, not_pl = [], [], []
    for p in sorted(d.glob(RESULTS_GLOB)) if d.is_dir() else []:
        try:
            doc = json.loads(p.read_text())
            rows = [r for r in doc.get("results") or [] if isinstance(r, dict)]
        except (OSError, ValueError, AttributeError, TypeError):
            bad.append(p.name)
            continue
        if doc.get("competition_code") != "PL" or doc.get("sport") != "soccer":
            not_pl.append(p.name)
            continue
        docs.append((str(doc.get("exported_at") or ""), p.name, rows))
    docs.sort(key=lambda x: (x[0], x[1]))                  # oldest first: a newer file's row replaces an older one
    out: dict = {}
    dupes, n = [], 0
    for _, name, rows in docs:
        for r in rows:
            mid = r.get("match_id")
            if not isinstance(mid, int) or isinstance(mid, bool):
                continue
            n += 1
            if mid in out:
                dupes.append((mid, name, out[mid][0]))
            out[mid] = (name, r)
    return {"rows": out, "files": [x[1] for x in docs], "unreadable": bad, "not_pl": not_pl, "rows_read": n,
            "dupes": dupes}


def final_call(entries, date) -> tuple[tuple | None, str | None]:
    """exec_cohorts.tally's selection on a match's closing entries [(run start, family, row), ...] against the match's
    current start: (the entry, None), or (the newest entry, the void label) when none is within the drift and the
    rows are re-dated, or (None, None) with no entry."""
    if not entries:
        return None, None
    near = _within(entries, date)
    if near:
        return near[-1], None
    return entries[-1], void_label([(run, r.get("utc_date")) for run, _, r in entries], date)


def injuries(row: dict) -> dict:
    """The closing row's injury inputs and the one-sided guard's state on it."""
    iq = (row.get("input_quality") or {}).get("injuries") if isinstance(row.get("input_quality"), dict) else None
    if isinstance(iq, dict):
        h, a = ((iq.get(s) or {}).get("count") if isinstance(iq.get(s), dict) else None for s in ("home", "away"))
        src = "input_quality.injuries"
    else:
        inj = row.get("injuries") if isinstance(row.get("injuries"), dict) else {}
        h, a, src = inj.get("home_count"), inj.get("away_count"), "injuries (no per-side block: the guard reads none)"
    rs = desk_policy.normalize({"sport": "soccer", "predictions": [row]})
    if not desk_policy.INJURIES_ONE_SIDED_RULE["on"]:
        guard = "rule off in code"
    elif not rs:
        guard = "not evaluable (the Desk reads no probabilities on the row)"
    else:
        one = desk_policy.one_sided_injuries(rs[0])
        guard = (f"fires ({one[0]} lists no name, {one[1]} lists {one[2]})" if one else "does not fire")
    desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
    return {"home": h, "away": a, "source": src, "guard": guard,
            "desk_guard": desk.get("pass_kind") == desk_policy.INJURIES_ONE_SIDED_KIND}


def read(exports_dir, min_gap_pp: float = MIN_GAP_PP) -> dict:
    res = read_results(exports_dir)
    cr = closing_rows(exports_dir)
    members, below, no_close, not_book, void, ungraded, no_pick = [], [], [], [], [], [], []
    graded = 0
    for mid in sorted(res["rows"], key=lambda m: ((res["rows"][m][1].get("date") or ""), m)):
        fname, r = res["rows"][mid]
        held = cr["rows"].get(mid) or []
        teams = (r.get("home_team"), r.get("away_team"))
        entries = [x for x in held if (x[2].get("home_team"), x[2].get("away_team")) == teams]   # machine-local ids
        teams_differ = bool(held) and not entries
        e, lab = final_call(entries, r.get("date"))
        game = {"match_id": mid, "file": fname, "date": r.get("date"), "home": r.get("home_team"),
                "away": r.get("away_team")}
        if r.get("redated") or lab:
            void.append({**game, "label": r.get("redated") or lab,
                         "by": "the results export" if r.get("redated") else "the closing files on disk"})
            continue
        g = r.get("graded") if isinstance(r.get("graded"), dict) else {}
        hit = g.get("top_pick_hit")
        if not isinstance(hit, bool):
            ungraded.append(game)
            continue
        graded += 1
        pr = r.get("predicted") if isinstance(r.get("predicted"), dict) else {}
        pick = pr.get("top_pick")
        p = _num(pr.get(PROB.get(pick, ""))) if pick in PROB else None
        p = p if p is not None else (_num(pr.get("top_pick_prob")) if pick in PROB else None)
        if pick not in SIDE or p is None:
            no_pick.append(game)
            continue
        fair = g.get("close_fair") if isinstance(g.get("close_fair"), dict) else None
        q = _num(fair.get(SIDE[pick])) if fair else None
        if q is None:
            no_close.append({**game, "why": g.get("close_stale_book") or ("close_fair null" if not fair else
                                                                          f"no close fair for {SIDE[pick]}"),
                             "books": g.get("close_books")})
            continue
        if g.get("close_reference") in KALSHI_SOURCES:
            not_book.append({**game, "reference": g.get("close_reference")})
            continue
        gap = round((p - q) * 100, 9)
        if gap < min_gap_pp:
            below.append(game)
            continue
        act = r.get("actual") if isinstance(r.get("actual"), dict) else {}
        m = {**game, "pick": pick, "side": SIDE[pick], "p": p, "q": q, "gap_pp": gap, "hit": hit,
             "score": (act.get("home_score"), act.get("away_score")), "result": act.get("result"),
             "close_at": g.get("close_at"), "close_min": g.get("close_minutes_before_start"),
             "stamp_age_h": g.get("close_book_stamp_age_h"), "books": g.get("close_books"),
             "reference": g.get("close_reference"), "unswitched": g.get("close_stale_unswitched"),
             "run": None, "computed_at": None, "model_version": None, "inj": None, "desk_pick": None,
             "pass_kind": None}
        if teams_differ:
            m["call"] = TEAMS
        elif e is None:
            m["call"] = NO_ROW
        else:
            row = e[2]
            desk = row.get("desk") if isinstance(row.get("desk"), dict) else None
            prd = row.get("prediction") if isinstance(row.get("prediction"), dict) else {}
            m.update(run=e[0], computed_at=prd.get("computed_at"), model_version=prd.get("model_version"),
                     inj=injuries(row), call=(desk.get("call") or "no call on the desk block") if desk else NO_DESK,
                     desk_pick=desk.get("pick") if desk else None, pass_kind=desk.get("pass_kind") if desk else None)
        members.append(m)
    by_call: dict = {}
    for m in members:
        c = by_call.setdefault(m["call"], {"n": 0, "hits": 0})
        c["n"] += 1
        c["hits"] += m["hit"]
    return {"results": res, "closing": cr, "min_gap_pp": min_gap_pp, "graded": graded, "members": members,
            "below": below, "no_close": no_close, "not_book": not_book, "void": void, "ungraded": ungraded,
            "no_pick": no_pick, "hits": sum(m["hit"] for m in members), "by_call": by_call}


def _game(x: dict) -> str:
    return f"match {x['match_id']} {(x['date'] or '-').replace('T', ' ')[:16]} {x['away'] or '?'} @ {x['home'] or '?'}"


def _member(m: dict) -> list[str]:
    team = {"HOME": m["home"], "AWAY": m["away"]}.get(m["side"], "Draw")
    age = []
    if m["close_min"] is not None:
        age.append(f"captured {m['close_min']} min before the start")
    if m["stamp_age_h"] is not None:
        stale = " (stale: over %dh)" % STALE_BOOK_H if (_num(m["stamp_age_h"]) or 0) > STALE_BOOK_H else ""
        age.append(f"book stamp {m['stamp_age_h']}h before the start{stale}")
    if not age:
        age.append("no age on the row")
    if m["inj"]:
        i = m["inj"]
        inj = (f"injuries home {i['home'] if i['home'] is not None else '-'} / away "
               f"{i['away'] if i['away'] is not None else '-'} ({i['source']}) · one-sided guard: {i['guard']} "
               f"(rule {'on' if desk_policy.INJURIES_ONE_SIDED_RULE['on'] else 'off'} in code; the Desk at the run: "
               f"{'PASS injuries_one_sided' if i['desk_guard'] else 'not a one-sided PASS'})")
    else:
        inj = "injuries: not in the closing files"
    hs, as_ = m["score"]
    call = m["call"] + (f" ({m['pass_kind']})" if m["call"] == "PASS" and m["pass_kind"] else "")
    run = f" · closing run {m['run']:%Y-%m-%d %H:%M}Z" if m["run"] else (" · closing run: no start" if m["inj"] else "")
    return [f"- {_game(m)} · file {m['file']}",
            f"    pick {m['pick']} ({team}) · model p {m['p']:.4f} · close fair {m['q']:.4f} · gap "
            f"{m['gap_pp']:+.2f}pp",
            f"    prediction stamp {m['computed_at'] or 'not in the closing files'}"
            + (f" (model {m['model_version']})" if m["model_version"] else ""),
            f"    close stamp {m['close_at'] or '-'} · {' · '.join(age)} · books {m['books']} · reference "
            f"{m['reference'] or 'absent'}" + (f" · unswitched: {m['unswitched']}" if m["unswitched"] else ""),
            f"    {inj}",
            f"    result {'hit' if m['hit'] else 'miss'} · score {hs if hs is not None else '-'}-"
            f"{as_ if as_ is not None else '-'} (result {m['result'] or '-'})",
            f"    the Desk's final call: {call}{run}"
            + (f" · desk pick {m['desk_pick']}" if m["desk_pick"] and m["desk_pick"] != m["side"] else "")]


def report(exports_dir, min_gap_pp: float = MIN_GAP_PP, echo=print) -> dict:
    out = read(exports_dir, min_gap_pp)
    res, cr = out["results"], out["closing"]
    d = str(exports_dir).rstrip("/")
    echo("PL POSITIVE-EDGE RECEIPT (ARCHITECT addendum 162 item 2(a); #92): read-only, files only, no verdict")
    echo(f"ruling: \"{RULING}\"")
    echo(f"cohort line: top pick's model p minus the book close's fair p >= {min_gap_pp:+g}pp (--min-gap-pp; the ruled "
         "line, not a knob)")
    echo(f"keys: {KEYS}")
    echo(f"INPUTS: results files {d}/{RESULTS_GLOB}: {len(res['files'])} read"
         + (f" ({', '.join(res['files'])})" if res["files"] else "")
         + (f" · unreadable {len(res['unreadable'])}: {', '.join(res['unreadable'])}" if res["unreadable"] else "")
         + (f" · not PL soccer {len(res['not_pl'])}: {', '.join(res['not_pl'])}" if res["not_pl"] else ""))
    echo(f"  results rows {res['rows_read']} · matches {len(res['rows'])} · duplicate copies dropped "
         f"{len(res['dupes'])} (one row per match_id, the newest file's: exported_at, then the name)")
    for mid, kept, dropped in res["dupes"]:
        echo(f"    match {mid}: kept {kept}, dropped {dropped}")
    runs = (f"runs {cr['runs'][0]:%Y-%m-%d %H:%M}Z to {cr['runs'][1]:%Y-%m-%d %H:%M}Z" if cr["runs"] else "runs —")
    echo(f"  closing files {d}/closing_*.json (redated.closing_rows; host/ never read): {cr['files']} read, {runs}, "
         f"families {', '.join(cr['families']) or '-'}, matches {len(cr['rows'])}"
         + (f" · unreadable {len(cr['unreadable'])}: {', '.join(cr['unreadable'])}" if cr["unreadable"] else ""))
    echo(f"LEFT OUT: void {len(out['void'])} ({void_counts(x['label'] for x in out['void'])}) · ungraded "
         f"{len(out['ungraded'])} · no top pick {len(out['no_pick'])} · no close {len(out['no_close'])} · close not "
         f"the book close {len(out['not_book'])} · below the line {len(out['below'])}")
    for x in out["void"]:
        echo(f"  void: {_game(x)}: {x['label']} (by {x['by']})")
    for x in out["ungraded"]:
        echo(f"  ungraded: {_game(x)}")
    for x in out["no_pick"]:
        echo(f"  no top pick: {_game(x)}")
    for x in out["no_close"]:
        echo(f"  no close: {_game(x)}: {x['why']} (books {x['books']})")
    for x in out["not_book"]:
        echo(f"  close not the book close: {_game(x)}: close_reference {x['reference']}")
    echo(f"COHORT ({len(out['members'])} rows, by date)")
    for m in out["members"]:
        for line in _member(m):
            echo(line)
    calls = list(CALLS) + sorted(k for k in out["by_call"] if k not in CALLS)
    echo(f"SUMMARY: graded PL rows {out['graded']} · cohort {len(out['members'])} · cohort hits {out['hits']} of "
         f"{len(out['members'])} · by the Desk's final call: "
         + " · ".join(f"{k} {out['by_call'].get(k, {}).get('n', 0)} (hits {out['by_call'].get(k, {}).get('hits', 0)})"
                      for k in calls))
    echo("PL-POSITIVE-EDGE-RECEIPT " + json.dumps({
        "min_gap_pp": min_gap_pp, "results_files": len(res["files"]), "results_rows": res["rows_read"],
        "matches": len(res["rows"]), "dupes_dropped": len(res["dupes"]), "closing_files": cr["files"],
        "graded": out["graded"], "cohort": len(out["members"]), "hits": out["hits"],
        "by_call": {k: v["n"] for k, v in out["by_call"].items()}, "void": len(out["void"]),
        "ungraded": len(out["ungraded"]), "no_pick": len(out["no_pick"]), "no_close": len(out["no_close"]),
        "not_book": len(out["not_book"]), "below": len(out["below"])}, sort_keys=True))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 162 item 2(a): the PL positive-edge cohort, from the results "
                                             "exports and the closing files")
    ap.add_argument("--exports", default="exports", help="the exports directory (default exports)")
    ap.add_argument("--min-gap-pp", type=float, default=MIN_GAP_PP,
                    help="the cohort line in pp (default 5, the ruled line; not a knob to tune)")
    a = ap.parse_args(argv)
    report(a.exports, a.min_gap_pp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
