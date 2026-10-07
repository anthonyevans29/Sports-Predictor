"""
INTERNATIONALS PRODUCTION EXPORT — built DARK (ARCHITECT 2026-10-07, item 4):
"Build dark; nothing changes for anyone until registry.production_allowed("intl-elo-v2") is true."
"a. the production export path for senior competitive internationals: desk blocks ONLY when production_allowed is
true; rows carry market_divergence_pp and quarantine as the NFL export defines them; until then
export-unl-predictions stays the shadow, unchanged."

    export-intl-predictions  -> exports/intl_predictions_<YYYY-MM-DD_HHMM>.json   (REFUSED until CONFIRMED)

- REFUSES (writes nothing) unless registry.production_allowed("intl-elo-v2") is true: a PASS verdict AND a recorded
  CONFIRMED confirmation. Until then the UNL shadow (export-unl-predictions, src/walters/intl_shadow.py) is the only
  intl model file, and it is untouched by this module.
- The model is the shadow's, exactly: intl_shadow.build_rows (intl-elo-v2 as run, registry multipliers, neutral
  rule v3, walk-forward to now). This module only re-shapes its rows for the Desk.
- Each row carries, as the NFL export defines them (src/walters/nfl_predict.py):
    market_divergence_pp = (model HOME p − book fair HOME) × 100, 1 dp, from the 1X2 close; null when unpriced;
    quarantine           = |market_divergence_pp| >= 15.
  plus `competition` (the stream code: INTL v0 rule 4 calls UNL only) and `venue_flag` (neutral_v3: home / neutral /
  unknown; INTL v0 rule 3).
- The document is sport "intl", so the Desk reads POLICY["INTL"] (desk_policy.py). Desk blocks are attached the
  way every export attaches them (desk_policy.maybe_annotate).
- DATABASE (ARCHITECT 2026-10-07 addendum 3, item C, amended): "the production INTL export writes no predictions
  row, but it DOES append to prediction_history on every export (model version, three probabilities,
  computed_at), as the K-track rule requires of every model sport." One history row per exported fixture, through
  the shared append path (src/db/database.py append_prediction_history), computed_at = the export's `now`. The
  file is written inside the history transaction, so a failed write leaves no history. Before
  migrate_prediction_history.py the export REFUSES and writes nothing (Codex on #325: with no Prediction row, a
  file without history rows would be calls with no grading record); an append count different from the fixture
  count also refuses, rolled back, no file (the count is in the file: prediction_history_appended).
- GRADING (same ruling): "INTL calls are graded on the 90-MINUTE result, never on a score that includes extra time
  or penalties." `export-intl-results` (results() below) grades every production call on record (the last
  prediction_history row of this model version computed before kickoff) on intl_shadow.result_90 ONLY; a finished
  game without a 90-minute result (AET / PEN with no stored 90-minute score, or any other) is left UNGRADED and
  LISTED with its reason, never graded on the later score.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

EID = "intl-elo-v2"
MODEL_VERSION = "intl_elo_v2"   # the file's and the history's model_version (the shadow's MODEL_VERSION)
SPORT = "intl"
ENGINE = "model_edge"
FILE_PREFIX = "intl_predictions_"
QUARANTINE_PP = 15.0          # the NFL contract (nfl_predict.py: abs(divergence_pp) >= 15.0)
VENUE_FLAG = {True: "neutral", False: "home", None: "unknown"}


class IntlRefused(RuntimeError):
    pass


def allowed() -> tuple[bool, str]:
    from src.walters import registry as reg
    return reg.production_allowed(EID)


def divergence_pp(p_home: float, market: dict | None):
    """The NFL definition: model HOME p minus the 1X2 book fair HOME, in pp (1 dp); None when unpriced."""
    m = market or {}
    if m.get("fair_source") != "1X2":
        return None
    fair = (m.get("fair_prob") or {}).get("HOME")
    return None if fair is None else round((p_home - fair) * 100, 1)


def production_row(shadow_row: dict, competition: str) -> dict:
    """A shadow row (intl_shadow.build_rows) re-shaped for the Desk. Pure."""
    sp = shadow_row["prediction"]
    row = {k: v for k, v in shadow_row.items() if k not in ("engine", "gate_verdict", "prediction")}
    div = divergence_pp(sp["home_win_prob"], row.get("market"))
    row.update({
        "competition": competition,
        "engine": ENGINE,
        "prediction": {
            "model_version": shadow_row.get("model_version"),
            "probabilities": {"home_win": sp["home_win_prob"], "draw": sp["draw_prob"],
                              "away_win": sp["away_win_prob"]},
            "top_pick": sp["top_pick"], "top_pick_prob": sp["top_pick_prob"],
            "tier": None,                     # no intl tier rule is declared; the Desk does not need one
            "elo_home": sp.get("elo_home"), "elo_away": sp.get("elo_away"),
            "home_adv_applied": sp.get("home_adv_applied"), "neutral_v3": sp.get("neutral_v3"),
        },
        "venue_flag": VENUE_FLAG[sp.get("neutral_v3")],
        "market_divergence_pp": div,
        "quarantine": div is not None and abs(div) >= QUARANTINE_PP,
    })
    row.pop("model_version", None)
    return row


def build(now: datetime | None = None, hours: int | None = None) -> dict:
    ok, why = allowed()
    if not ok:
        raise IntlRefused(f"{EID} is not production-allowed ({why}); export-unl-predictions stays the shadow")
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import intl_shadow as us

    r = us.build_rows(now, us.WINDOW_HOURS if hours is None else hours)   # an explicit 0 stays empty (Codex on #325)
    with session_scope() as s:
        codes = {}
        for x in r["rows"]:
            m = s.get(Match, x["match_id"])
            codes[x["match_id"]] = m.competition.code if m is not None and m.competition else None
        s.rollback()
    rows = [production_row(x, codes[x["match_id"]]) for x in r["rows"]]
    return {"rows": rows, "fit": r["fit"], "now": r["now"], "why": why}


def export(now: datetime | None = None, hours: int | None = None, out_dir: str = "exports",
           desk: bool | None = None) -> tuple[str, dict]:
    from src.walters import desk_policy as dp

    from src.db.database import append_prediction_history, has_prediction_history, session_scope

    b = build(now, hours)
    now = b["now"]
    doc = {"sport": SPORT, "engine": ENGINE, "model_version": MODEL_VERSION, "production_allowed": b["why"],
           "exported_at": now.isoformat(), "count": len(b["rows"]), "fit": b["fit"], "predictions": b["rows"]}
    dp.maybe_annotate(doc, desk)
    with session_scope() as s:                 # history + file together: a failed write rolls the history back
        # Codex on #325: this path writes no Prediction row, so the history IS the durable grading record
        # (export-intl-results reads only prediction_history). No history, no actionable file.
        if not has_prediction_history(s.connection()):
            raise IntlRefused("prediction_history is missing (run migrate_prediction_history.py): an INTL "
                              "production file without its history rows could never be graded; nothing written")
        rows = history_rows(doc, now)
        n = append_prediction_history(s.connection(), rows)
        if n != len(rows) or n != len(doc["predictions"]):
            raise IntlRefused(f"prediction_history appended {n} row(s) for {len(doc['predictions'])} fixture(s): "
                              "rolled back; nothing written")
        doc["prediction_history_appended"] = n
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.json")
        with open(path, "w") as f:
            json.dump(doc, f, indent=2, default=str)
    return path, doc


def history_rows(doc: dict, computed_at: datetime) -> list[dict]:
    """One prediction_history row per exported fixture: model version, the three probabilities, computed_at."""
    out = []
    for r in doc["predictions"]:
        p = r["prediction"]["probabilities"]
        out.append({"match_id": r["match_id"], "model_version": MODEL_VERSION, "computed_at": computed_at,
                    "home_win_prob": p["home_win"], "draw_prob": p["draw"], "away_win_prob": p["away_win"]})
    return out


# ---------------------------------------------------------------------------
# RESULTS (ARCHITECT 2026-10-07 addendum 3, item C): "INTL calls are graded on the 90-MINUTE result, never on a
# score that includes extra time or penalties. The results path for an INTL call reads the stored 90-minute score;
# where a game went beyond 90 minutes and no 90-minute score is stored, the call is left ungraded and listed, never
# graded on the later score."
# ---------------------------------------------------------------------------
RESULTS_PREFIX = "intl_INTL_results_"
BEYOND_90 = ("AET", "PEN")     # API-Football status_raw: finished after extra time / on penalties
SIDES = ("HOME", "DRAW", "AWAY")
TOP = {"HOME": "home_win", "DRAW": "draw", "AWAY": "away_win"}
OUTCOME_SIDE = {"H": "HOME", "D": "DRAW", "A": "AWAY"}


def ungraded_reason(m) -> str:
    """Why a FINISHED match has no 90-minute result (intl_shadow.result_90 is None). Pure."""
    raw = (m.status_raw or "").upper()
    if raw in BEYOND_90:
        return f"went beyond 90 minutes ({raw}) and no 90-minute score is stored: never graded on the later score"
    if raw == "FT":
        return "finished FT, score not stored yet"
    return f"no 90-minute score stored (status_raw {raw or 'NULL'}): not graded"


def _calls(s, now: datetime) -> dict:
    """match_id -> (history row, match): the LAST prediction_history row of MODEL_VERSION computed before kickoff
    (only the production export writes this model version to the history; the shadow writes none)."""
    from sqlalchemy import select

    from src.db.schema import Match, PredictionHistory

    out = {}
    q = (select(PredictionHistory, Match).join(Match, Match.id == PredictionHistory.match_id)
         .where(PredictionHistory.model_version == MODEL_VERSION, Match.utc_date <= now,
                PredictionHistory.computed_at < Match.utc_date)
         .order_by(PredictionHistory.computed_at, PredictionHistory.id))
    for h, m in s.execute(q).all():
        out[m.id] = (h, m)
    return out


def results(now: datetime | None = None, days: int | None = None) -> dict:
    """Every production INTL call on record (or those kicking off in the last `days`), graded on the 90-minute
    result ONLY (intl_shadow.result_90: the stored 90-minute score; else the score of a FT row; else none).
    `rows` follow the NFL/soccer results-file grammar (predicted / actual / graded); `actual.home_score` /
    `away_score` ARE the 90-minute score, so the Cockpit's intake grades on 90 minutes. `ungraded`: finished calls
    without a 90-minute result, each with its reason, never graded on the later score. Read-only."""
    import math
    from datetime import timedelta

    from sqlalchemy import select

    from src.db.database import has_prediction_history, session_scope
    from src.db.schema import MatchStatus, Odds
    from src.timeutil import utc_now_naive
    from src.walters.close import close_block
    from src.walters.intl_shadow import result_90

    now = now or utc_now_naive()
    since = now - timedelta(days=days) if days is not None else None
    rows, ungraded = [], []
    with session_scope() as s:
        if not has_prediction_history(s.connection()):
            raise IntlRefused("prediction_history is missing (run migrate_prediction_history.py): "
                              "no INTL production calls are on record")
        for mid, (h, m) in sorted(_calls(s, now).items(), key=lambda kv: (kv[1][1].utc_date, kv[0])):
            if m.status != MatchStatus.FINISHED or (since is not None and m.utc_date < since):
                continue
            probs = {"HOME": h.home_win_prob, "DRAW": h.draw_prob, "AWAY": h.away_win_prob}
            pick = max(SIDES, key=lambda k: probs[k])
            base = {"match_id": m.id, "utc_date": m.utc_date.isoformat(),
                    "competition": m.competition.code if m.competition else None,
                    "home_team": m.home_team.name, "away_team": m.away_team.name,
                    "predicted": {"model_version": h.model_version, "computed_at": h.computed_at.isoformat(),
                                  "top_pick": TOP[pick], "top_pick_prob": round(probs[pick], 4),
                                  "home_win_prob": h.home_win_prob, "draw_prob": h.draw_prob,
                                  "away_win_prob": h.away_win_prob}}
            res = result_90(m)
            if res is None:
                ungraded.append({**base, "status_raw": m.status_raw, "reason": ungraded_reason(m)})
                continue
            if m.home_score_90 is not None and m.away_score_90 is not None:
                hg, ag, basis = m.home_score_90, m.away_score_90, "score_90"
            else:                                            # result_90's FT branch: a FT score IS the 90'
                hg, ag, basis = m.home_score, m.away_score, "FT score"
            side = OUTCOME_SIDE[res]
            odds = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            cb = close_block(odds, m.utc_date, m.sport)
            fair = cb["close_fair"]
            actual = {"home_score": hg, "away_score": ag, "result": res, "score_basis": basis,
                      "status_raw": m.status_raw}
            if (m.status_raw or "").upper() in BEYOND_90:    # shown for audit, never graded on
                actual["after_extra_time"] = {"home_score": m.home_score, "away_score": m.away_score}
            rows.append({**base, "actual": actual, "graded": {
                "top_pick_hit": pick == side, "push": False,
                "log_loss": round(-math.log(max(float(probs[side]), 1e-12)), 4),
                **cb,
                "clv": round(probs[pick] - fair[pick], 4) if fair and fair.get(pick) is not None else None}})
        s.rollback()
    return {"rows": rows, "ungraded": ungraded, "now": now,
            "window": {"kind": "all_production_calls"} if days is None else
            {"kind": "rolling", "days": days, "from": since.isoformat() + "Z"}}


def export_results(now: datetime | None = None, days: int | None = None,
                   out_dir: str = "exports") -> tuple[str, dict]:
    """exports/intl_INTL_results_<YYYY-MM-DD>.json (the NFL results-file grammar, sport "intl")."""
    r = results(now, days)
    now, rows = r["now"], r["rows"]
    doc = {"exported_at": now.isoformat() + "Z", "sport": SPORT, "model_version": MODEL_VERSION,
           "grading": "90-minute result only (ARCHITECT 2026-10-07 addendum 3, item C): a score including extra "
                      "time or penalties is never graded on; such a game without a stored 90-minute score is "
                      "listed under `ungraded`",
           "note": "record is variance, not signal — for the consumer to grade against",
           "window": r["window"],
           "record": {"games": len(rows), "hits": sum(1 for x in rows if x["graded"]["top_pick_hit"]),
                      "decided": len(rows), "ungraded": len(r["ungraded"])},
           "count": len(rows), "results": rows, "ungraded": r["ungraded"]}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(out_dir) / f"{RESULTS_PREFIX}{now.strftime('%Y-%m-%d')}.json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return path, doc
