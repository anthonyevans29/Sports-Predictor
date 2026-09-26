"""
NFL prediction path (phase 2b, 2026-09-09 — built the day the gate passed).

predict_nfl(): walks the full finished stream (preseason excluded) with the
gate-passed v1 Elo to current ratings, then writes win probabilities for
upcoming games. Match-only upsert (the S13 lesson: one row per match, ever).

export_nfl_predictions(): lean rehearsal-format file — fixtures, model
probabilities, tier, and an input_quality block with QB status front and
center. contains_predictions: true, model_version stamped, and a rehearsal
flag until the dress rehearsal passes.

NOTHING here ships to the GPT layer until the Week-2 rehearsal + dry read
pass, per the frozen sequence.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Injury, Match, MatchStatus, Odds, Prediction, Sport
from src.walters.nfl_backtest import NFLEloConfig, _State, _expected_home, _update

log = logging.getLogger(__name__)

MODEL_VERSION = "nfl_elo_v1"


def _current_ratings() -> _State:
    cfg = NFLEloConfig()
    st = _State()
    with session_scope() as s:
        games = list(s.execute(
            select(Match).where(
                Match.sport == Sport.NFL,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars())
        for m in games:
            if "pre" in (m.stage or "").lower():
                continue
            _update(cfg, st, m.home_team_id, m.away_team_id, m.season,
                    m.home_score, m.away_score)
    return st


def _tier(p: float) -> str:
    # NFL-SPECIFIC thresholds, FROZEN 2026-09-10 pre-Week-1-results (backlog:
    # tier pre-commitment). Elo's NFL distribution is wider than MLB's and
    # the backtest's 70-80% band leaned over-confident; MLB's 0.60 bar made
    # 11/16 of the shakedown slate "strong", which tells a consumer nothing.
    top = max(p, 1 - p)
    if top >= 0.68:
        return "strong"
    if top >= 0.57:
        return "lean"
    return "toss-up"


def predict_nfl(days_ahead: int = 8) -> int:
    cfg = NFLEloConfig()
    st = _current_ratings()
    written = 0
    with session_scope() as s:
        now = datetime.utcnow()
        upcoming = list(s.execute(
            select(Match).where(
                Match.sport == Sport.NFL,
                Match.status == MatchStatus.SCHEDULED,
                Match.utc_date >= now,
                Match.utc_date <= now + timedelta(days=days_ahead),
            ).order_by(Match.utc_date)
        ).scalars())
        for m in upcoming:
            p_home = _expected_home(cfg, st, m.home_team_id, m.away_team_id)
            # Match-only upsert (S13): one prediction row per match, ever.
            s.query(Prediction).filter(Prediction.match_id == m.id).delete()
            s.add(Prediction(
                match_id=m.id,
                model_version=MODEL_VERSION,
                home_win_prob=round(p_home, 4),
                away_win_prob=round(1 - p_home, 4),
                draw_prob=None,
                computed_at=datetime.utcnow(),
            ))
            written += 1
    log.info("Wrote %d NFL predictions using %s", written, MODEL_VERSION)
    return written


def export_nfl_predictions(days_ahead: int = 8, out_dir: str = "exports") -> str:
    with session_scope() as s:
        now = datetime.utcnow()
        q = (select(Prediction, Match)
             .join(Match, Match.id == Prediction.match_id)
             .where(Match.sport == Sport.NFL,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now,
                    Match.utc_date <= now + timedelta(days=days_ahead))
             .order_by(Match.utc_date))
        rows = []
        for pred, m in s.execute(q).all():
            # market block from stored book odds (1X2)
            odds_rows = list(s.execute(select(Odds).where(
                Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            market = None
            if odds_rows:
                from src.walters.value import MarketSnapshot
                by_sel: dict[str, list[tuple[str, float]]] = {}
                for o in odds_rows:
                    by_sel.setdefault(o.selection, []).append(
                        (o.bookmaker, o.price_decimal))
                implied = MarketSnapshot(market="1X2",
                                         by_selection=by_sel).average_implied()
                over = sum(implied.values()) or 1.0
                market = {
                    "bookmaker_count": len({o.bookmaker for o in odds_rows}),
                    "fair_prob": {k: round(v / over, 4) for k, v in implied.items()},
                    "fair_source": "1X2",
                }
            else:
                # Spread->win-prob fallback (2026-09-26): no 1X2 consensus but
                # SPREADS present -> labelled spread-derived fair (reference
                # only). NOT fed to market_divergence_pp / quarantine below:
                # that contract rule was earned on the 1X2 consensus.
                from src.walters import spread_fallback as _fb
                sp_rows = list(s.execute(select(Odds).where(
                    Odds.match_id == m.id,
                    Odds.market == _fb.SPREAD_MARKET)).scalars())
                if sp_rows:
                    sp = _fb.latest_pre_kickoff(sp_rows, m.utc_date,
                                                _fb.SPREAD_MARKET, with_line=True)
                    market = _fb.derive_spread_market(
                        sp.values(), m.competition.code if m.competition else "NFL")
            # QB status front and center: injuries for both teams
            inj = {}
            for side, tid in (("home", m.home_team_id), ("away", m.away_team_id)):
                team_inj = list(s.execute(select(Injury).where(
                    Injury.team_id == tid)).scalars())
                qb = [i.player_name for i in team_inj
                      if (i.player_position or "").upper() == "QB"]
                stamp = max((i.refreshed_at for i in team_inj), default=None)
                inj[side] = {"count": len(team_inj), "qb_listed": qb,
                             "synced_at": stamp.isoformat() if stamp else None}
            p_home = pred.home_win_prob
            _fair = ((market or {}).get("fair_prob") or {}
                     if (market or {}).get("fair_source") == "1X2" else {})
            divergence_pp = (round((p_home - _fair["HOME"]) * 100, 1)
                             if _fair.get("HOME") is not None else None)
            rows.append({
                "match_id": m.id,
                "utc_date": m.utc_date.isoformat(),
                "week": m.matchday,
                "stage": m.stage,
                "home_team": m.home_team.name,
                "away_team": m.away_team.name,
                "prediction": {
                    "model_version": pred.model_version,
                    "home_win_prob": p_home,
                    "away_win_prob": pred.away_win_prob,
                    "top_pick": "home_win" if p_home >= 0.5 else "away_win",
                    "tier": _tier(p_home),
                },
                "market": market,
                "market_divergence_pp": divergence_pp,
                "quarantine": (divergence_pp is not None and abs(divergence_pp) >= 15.0),
                "input_quality": {
                    "book_odds": (market or {}).get("bookmaker_count", 0),
                    "injuries": inj,
                },
            })
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir,
                        f"nfl_predictions_{datetime.utcnow().strftime('%Y-%m-%d')}.json")
    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "sport": "nfl",
        "model_version": MODEL_VERSION,
        "contains_predictions": True,
        "rehearsal": False,
        "live_since": "2026-09-22 (Week 3; ratified after two graded weeks)",
        "note": ("LIVE: gate-passed v1 Elo. CONTRACT RULE: rows with "
                 "market_divergence_pp >= 15 carry quarantine=true — "
                 "consumer treats them as watch-flagged, never straight "
                 "plays (rule earned 1-5 across Weeks 1-2)."),
        "count": len(rows),
        "predictions": rows,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def grade_nfl(days_back: int = 8, progress=None) -> dict:
    """
    NFL grading (2026-09-14, built for Week 1's first read): joins
    predictions vs finished games and the latest banked book consensus.
    READ-ONLY — prints the table; outcome persistence arrives with the
    full evaluate integration if the rehearsal is earned.
    """
    from datetime import datetime, timedelta
    import math

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds, Prediction, Sport
    from src.walters.value import MarketSnapshot

    def report(msg):
        if progress:
            progress(msg)

    with session_scope() as s:
        now = datetime.utcnow()
        q = (select(Prediction, Match)
             .join(Match, Match.id == Prediction.match_id)
             .where(Match.sport == Sport.NFL,
                    Match.status == MatchStatus.FINISHED,
                    Match.utc_date >= now - timedelta(days=days_back))
             .order_by(Match.utc_date))
        hits = n = 0
        ll = 0.0
        clvs = []
        for pred, m in s.execute(q).all():
            y = 1 if m.home_score > m.away_score else 0
            p = pred.home_win_prob
            pick_home = p >= 0.5
            hit = (pick_home and y == 1) or (not pick_home and y == 0)
            hits += hit
            n += 1
            ll += -(y * math.log(max(p, 1e-12))
                    + (1 - y) * math.log(max(1 - p, 1e-12)))
            close_h = None
            odds_rows = list(s.execute(select(Odds).where(
                Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            if odds_rows:
                by_sel = {}
                for o in odds_rows:
                    by_sel.setdefault(o.selection, []).append(
                        (o.bookmaker, o.price_decimal))
                implied = MarketSnapshot(market="1X2",
                                         by_selection=by_sel).average_implied()
                tot = sum(implied.values()) or 1.0
                close_h = implied.get("HOME", 0) / tot
            clv = None
            if close_h is not None:
                pick_p = p if pick_home else 1 - p
                close_p = close_h if pick_home else 1 - close_h
                clv = (pick_p - close_p)
                clvs.append(clv)
            report(f"  {m.away_team.name[:14]:14} @ {m.home_team.name[:15]:15} "
                   f"{m.away_score:>2}-{m.home_score:<2} model_H={p:.3f} "
                   f"close_H={'%.3f' % close_h if close_h is not None else '  — '} "
                   f"{'HIT ' if hit else 'miss'} "
                   f"clv={'%+.1fpp' % (clv*100) if clv is not None else '—'}")
        if n == 0:
            return {"ok": False, "reason": "no finished NFL games with predictions in window"}
        summary = {"ok": True, "games": n, "hits": hits,
                   "logloss": round(ll / n, 4),
                   "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None}
        report(f"  ── sides {hits}/{n} · log-loss {summary['logloss']} · "
               f"mean CLV {summary['mean_clv_pp']}pp (n={len(clvs)} priced)")
        return summary


def export_nfl_results(days_back: int = 8, out_dir: str = "exports") -> str:
    """Graded NFL results file for the consumer rhythm (2026-09-15)."""
    import json as _json
    import math
    import os as _os
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds, Prediction, Sport
    from src.walters.value import MarketSnapshot

    rows = []
    with session_scope() as s:
        now = datetime.utcnow()
        q = (select(Prediction, Match)
             .join(Match, Match.id == Prediction.match_id)
             .where(Match.sport == Sport.NFL,
                    Match.status == MatchStatus.FINISHED,
                    Match.utc_date >= now - timedelta(days=days_back))
             .order_by(Match.utc_date))
        for pred, m in s.execute(q).all():
            y = 1 if m.home_score > m.away_score else 0
            p = pred.home_win_prob
            pick_home = p >= 0.5
            close_h = None
            odds_rows = list(s.execute(select(Odds).where(
                Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            if odds_rows:
                by_sel = {}
                for o in odds_rows:
                    by_sel.setdefault(o.selection, []).append(
                        (o.bookmaker, o.price_decimal))
                imp = MarketSnapshot(market="1X2",
                                     by_selection=by_sel).average_implied()
                tot = sum(imp.values()) or 1.0
                close_h = imp.get("HOME", 0) / tot
            clv = None
            if close_h is not None:
                clv = (p if pick_home else 1 - p) - (close_h if pick_home else 1 - close_h)
            rows.append({
                "match_id": m.id, "utc_date": m.utc_date.isoformat(),
                "week": m.matchday,
                "home_team": m.home_team.name, "away_team": m.away_team.name,
                "predicted": {"model_version": pred.model_version,
                              "top_pick": "home_win" if pick_home else "away_win",
                              "top_pick_prob": round(p if pick_home else 1 - p, 4),
                              "home_win_prob": p},
                "actual": {"home_score": m.home_score, "away_score": m.away_score,
                           "result": "H" if y else "A"},
                "graded": {"top_pick_hit": (pick_home and y == 1) or (not pick_home and y == 0),
                           "log_loss": round(-(y * math.log(max(p, 1e-12))
                                               + (1 - y) * math.log(max(1 - p, 1e-12))), 4),
                           "close_home_prob": round(close_h, 4) if close_h is not None else None,
                           "clv": round(clv, 4) if clv is not None else None},
            })
    _os.makedirs(out_dir, exist_ok=True)
    path = _os.path.join(out_dir, f"nfl_NFL_results_{datetime.utcnow().strftime('%Y-%m-%d')}.json")
    with open(path, "w") as f:
        _json.dump({"exported_at": datetime.utcnow().isoformat() + "Z",
                    "sport": "nfl", "rehearsal": True,
                    "note": "record is variance, not signal — for the consumer to grade against",
                    "count": len(rows), "results": rows}, f, indent=2)
    return path
