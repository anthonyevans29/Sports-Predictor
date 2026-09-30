"""
NHL SHADOW (architect lane NHL-SHADOW, 2026-09-30): the FAILED v1 Elo as a
REFERENCE MODEL beside the market-only NHL launch. It is never a call.

    export-nhl-predictions   -> exports/nhl_shadow_<YYYY-MM-DD_HHMM>.json

- Every row is stamped: model_version "nhl_elo_v1", gate_verdict "FAILED
  0.6909 vs 0.6866 (Phase 2 closed 2026-09-25)", engine "model_shadow".
- The Cockpit renders them greyed under "reference model — failed gate".
  They never produce a Desk call, never feed the venue engine, and never
  log to the ledger.
- The window card skips engine "model_shadow" docs, so NHL rows stay
  market_only there.
- Grading records live CLV only, pick-vs-close and value-side, into a
  shadow section of RESULTS.md. No hit rate and no log-loss: this is not a
  record.

THE MODEL IS v1 EXACTLY AS GATED (law 3: nothing is tuned here):
- NHLEloConfig defaults (k 6.0, mov_base 2.2, regression 0.25).
- home_advantage from the TRAIN season's (2024) realized home rate — the
  gate's own derivation.
- The stream is the gate's (competition NHL, finished, both scores,
  preseason excluded by stage or by date, ties skipped), extended to the
  live season with its ruled opener (the nhl-daily season gate:
  2026-09-29, operator-confirmed).
- Walk-forward: ratings after every finished game before now, then the
  predictions.

GRADING READS THE ARTIFACTS, NOT THE DB'S PREDICTIONS: nothing is written to
the Prediction table (no NHL model exists by doctrine). A game's call is the
LAST shadow export row written before puck drop (the execute-at-close
default). Close = the stored 1X2 book consensus (nfl-grade's rule).
Value-side anchor = the earliest pre-kickoff book snapshot (never Kalshi);
without one the game is counted unanchored, never guessed (law 4).
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive

ENGINE = "model_shadow"
MODEL_VERSION = "nhl_elo_v1"
GATE_VERDICT = "FAILED 0.6909 vs 0.6866 (Phase 2 closed 2026-09-25)"
WINDOW_HOURS = 36
FILE_PREFIX = "nhl_shadow_"
# the live season's opener = the nhl-daily season gate (ruled 2026-09-29)
LIVE_SEASON_STARTS = {"2026": date(2026, 9, 29)}
NOTE = ("REFERENCE MODEL — FAILED GATE. nhl_elo_v1 failed the frozen Phase 2 gate "
        "(0.6909 vs the 0.6866 bar; the schedule-only floor is ~0.691). Shadow only: never a "
        "call, never a venue input, never logged to the ledger. NHL runs MARKET-ONLY. "
        "Graded on live CLV only.")


def _season_starts() -> dict:
    from src.walters import nhl_backtest as nb
    return {**nb.SEASON_STARTS, **LIVE_SEASON_STARTS}


def fit(games, now: datetime):
    """(model, receipt): v1 with the gate's home advantage, walked forward
    over every decided regular-season game before `now`."""
    from src.models.nhl_elo import NHLEloConfig, NHLEloV1, home_advantage_from_rate
    from src.walters import nhl_backtest as nb

    starts = _season_starts()
    train = [g for g in games if g.season == nb.TRAIN_SEASON and nb.preseason_reason(g, starts) is None
             and g.home_score != g.away_score]
    if not train:
        raise RuntimeError(f"no {nb.TRAIN_SEASON} NHL games: the gate's home advantage cannot be derived")
    home_rate = sum(g.home_win for g in train) / len(train)
    model = NHLEloV1(NHLEloConfig(home_advantage=home_advantage_from_rate(home_rate)))
    used = excluded = ties = 0
    for g in sorted(games, key=lambda x: x.utc_date):
        if g.utc_date >= now:
            continue
        if nb.preseason_reason(g, starts):
            excluded += 1
            continue
        if g.home_score == g.away_score:
            ties += 1
            continue
        model.update(g)
        used += 1
    return model, {"games_used": used, "preseason_excluded": excluded, "ties_skipped": ties,
                   "home_rate_train": round(home_rate, 4),
                   "home_advantage": round(model.cfg.home_advantage, 1)}


def build_rows(now: datetime | None = None, hours: int = WINDOW_HOURS) -> dict:
    from collections import Counter

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport
    from src.walters import nhl_backtest as nb
    from src.walters.export import _fixture_row

    now = now or utc_now_naive()
    model, rc = fit(nb.load_games(), now)
    starts = _season_starts()
    rows, skipped = [], Counter()
    with session_scope() as s:
        q = (select(Match).join(Competition, Match.competition_id == Competition.id)
             .where(Match.sport == Sport.NHL, Competition.code == "NHL",
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now, Match.utc_date < now + timedelta(hours=hours))
             .order_by(Match.utc_date, Match.id))
        for m in s.execute(q).scalars():
            g = nb.Game(m.home_team_id, m.away_team_id, m.season, m.utc_date, 0, 0, m.stage or "")
            why = nb.preseason_reason(g, starts)
            if why:
                skipped[f"preseason_{why}"] += 1
                continue
            p = model.predict(g)
            row = _fixture_row(s, m, "NHL", Counter(), Counter())
            pick_home = p >= 0.5
            row.update({
                "engine": ENGINE, "model_version": MODEL_VERSION, "gate_verdict": GATE_VERDICT,
                "prediction": {"home_win_prob": round(p, 4), "away_win_prob": round(1 - p, 4),
                               "top_pick": "home_win" if pick_home else "away_win",
                               "top_pick_prob": round(p if pick_home else 1 - p, 4),
                               "elo_home": round(model.rating(m.home_team_id), 1),
                               "elo_away": round(model.rating(m.away_team_id), 1),
                               "home_adv_applied": rc["home_advantage"]},
            })
            rows.append(row)
    return {"rows": rows, "fit": rc, "skipped": dict(skipped), "now": now}


def export(now: datetime | None = None, hours: int = WINDOW_HOURS, out_dir: str = "exports") -> tuple[str, dict]:
    r = build_rows(now, hours)
    now = r["now"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.json")
    doc = {"sport": "nhl", "engine": ENGINE, "model_version": MODEL_VERSION, "gate_verdict": GATE_VERDICT,
           "contains_predictions": False,   # nothing here is a live prediction (doctrine)
           "exported_at": now.isoformat(), "window_hours": hours, "note": NOTE,
           "fit": r["fit"], "skipped": r["skipped"], "count": len(r["rows"]), "predictions": r["rows"]}
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return path, doc


def last_calls(export_dir: str = "exports") -> dict[int, dict]:
    """match_id -> the LAST shadow row written before its puck drop."""
    out: dict[int, dict] = {}
    for f in sorted(Path(export_dir).glob(f"{FILE_PREFIX}*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("engine") != ENGINE:
            continue
        at = doc.get("exported_at") or ""
        for r in doc.get("predictions") or []:
            mid, ko = r.get("match_id"), r.get("utc_date") or ""
            if mid is None or not at or at >= ko:
                continue
            if mid not in out or at >= out[mid]["exported_at"]:
                out[mid] = {**r, "exported_at": at, "source_file": f.name}
    return out


def grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None, progress=None) -> dict:
    """Live CLV only (pick-vs-close + value-side) for finished NHL games
    whose call exists in a shadow export."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.nfl_predict import _book_anchor, value_side_grade
    from src.walters.value import MarketSnapshot

    now = now or utc_now_naive()
    calls = last_calls(export_dir)
    clvs, vclvs, lines = [], [], []
    graded = unpriced = unanchored = 0
    with session_scope() as s:
        for mid, c in sorted(calls.items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            graded += 1
            p = c["prediction"]["home_win_prob"]
            pick_home = p >= 0.5
            odds = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            close_h = None
            if odds:
                by = {}
                for o in odds:
                    by.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
                imp = MarketSnapshot(market="1X2", by_selection=by).average_implied()
                tot = sum(imp.values()) or 1.0
                close_h = imp.get("HOME", 0) / tot
            clv = None
            if close_h is not None:
                clv = (p if pick_home else 1 - p) - (close_h if pick_home else 1 - close_h)
                clvs.append(clv)
            else:
                unpriced += 1
            anchor_h, _ = _book_anchor(s, m)
            vg = value_side_grade(p, anchor_h, close_h)
            if vg:
                vclvs.append(vg["value_side_clv"])
            elif anchor_h is None:
                unanchored += 1
            line = (f"  {m.away_team.name[:14]:14} @ {m.home_team.name[:15]:15} shadow_H={p:.3f} "
                    f"close_H={'%.3f' % close_h if close_h is not None else '  — '} "
                    f"clv={'%+.1fpp' % (clv * 100) if clv is not None else '—'} "
                    f"value={(vg['side'] + ' %+.1fpp' % (vg['value_side_clv'] * 100)) if vg else '— (no anchor)'}")
            lines.append(line)
            if progress:
                progress(line)
    return {"graded": graded, "priced": len(clvs), "unpriced": unpriced,
            "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
            "value_side_n": len(vclvs), "unanchored": unanchored,
            "mean_value_side_clv_pp": round(sum(vclvs) / len(vclvs) * 100, 2) if vclvs else None,
            "calls_on_file": len(calls), "lines": lines}


def results_section(days: int, export_dir: str = "exports") -> str:
    r = grade(days=days, export_dir=export_dir)
    head = f"## NHL — REFERENCE MODEL, FAILED GATE (shadow · {MODEL_VERSION} · {GATE_VERDICT})\n\n"
    if not r["graded"]:
        return head + ("Live CLV only. No graded shadow calls in window "
                       f"({r['calls_on_file']} calls on file).\n")
    return head + (
        f"- Live CLV only; not a record. Graded calls: {r['graded']}\n"
        f"- Mean pick-vs-close: "
        + (f"{r['mean_clv_pp']:+.2f}pp (n={r['priced']} priced)" if r["mean_clv_pp"] is not None
           else f"— (no stored close; {r['unpriced']} unpriced)") + "\n"
        + "- Mean value-side-vs-close: "
        + (f"{r['mean_value_side_clv_pp']:+.2f}pp (n={r['value_side_n']} anchored)"
           if r["mean_value_side_clv_pp"] is not None
           else f"— ({r['unanchored']} unanchored: no pre-kickoff book snapshot)") + "\n")
