"""
NFL prediction path (phase 2b, 2026-09-09 — built the day the gate passed).

predict_nfl(): walks the full finished stream (preseason excluded) with the
gate-passed v1 Elo to current ratings, then writes win probabilities for
upcoming games. Match-only upsert (the S13 lesson: one row per match, ever).

export_nfl_predictions(): the LIVE file (nfl_elo_v1 live since Week 3,
2026-09-22; rehearsal=false) — fixtures, model probabilities, tier, the
market block with the quarantine contract, the STALE-BOOK? venue check, the
Elo/rest "why" fields, and an input_quality block with QB status front and
center.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Injury, Match, MatchStatus, Odds, OddsSnapshot, Prediction, Sport
from src.walters.nfl_backtest import (NFLEloConfig, _State, _expected_home, _update,
                                      nfl_scoped, scope_line)
from src.walters.provenance import git_sha as _git_sha
from src.walters.qb_audit import is_qb
from src.timeutil import utc_now_naive

log = logging.getLogger(__name__)

MODEL_VERSION = "nfl_elo_v1"


def _current_ratings(progress=None) -> _State:
    cfg = NFLEloConfig()
    st = _State()
    with session_scope() as s:
        games = list(s.execute(
            nfl_scoped(select(Match)).where(
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            ).order_by(Match.utc_date, Match.id)
        ).scalars())
        games = [m for m in games if "pre" not in (m.stage or "").lower()]
        if progress:
            progress(scope_line("ratings", games))
        for m in games:
            _update(cfg, st, m.home_team_id, m.away_team_id, m.season,
                    m.home_score, m.away_score)
    return st


def _fb_live() -> bool:
    """Spread fallback dark switch (acceptance FAILED; ships only on a vetted PASS)."""
    from src.walters import spread_fallback as _fb
    return _fb.FALLBACK_LIVE


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


def predict_nfl(days_ahead: int = 8, progress=None) -> int:
    cfg = NFLEloConfig()
    st = _current_ratings(progress)
    written = 0
    with session_scope() as s:
        now = utc_now_naive()
        upcoming = list(s.execute(
            nfl_scoped(select(Match)).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.utc_date >= now,
                Match.utc_date <= now + timedelta(days=days_ahead),
            ).order_by(Match.utc_date)
        ).scalars())
        if progress:
            progress(scope_line("prediction set", upcoming))
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
                computed_at=utc_now_naive(),
            ))
            written += 1
    log.info("Wrote %d NFL predictions using %s", written, MODEL_VERSION)
    return written


def _rest_days(s, m) -> dict[str, float | None]:
    """Days since each side's previous NFL game (any non-cancelled/postponed
    status, preseason included — rest is physical), from the schedule.
    None = no earlier game on record."""
    out = {}
    for side, tid in (("home", m.home_team_id), ("away", m.away_team_id)):
        prev = s.execute(
            nfl_scoped(select(Match.utc_date)).where(
                Match.utc_date < m.utc_date,
                Match.status.notin_([MatchStatus.CANCELLED, MatchStatus.POSTPONED]),
                (Match.home_team_id == tid) | (Match.away_team_id == tid),
            ).order_by(Match.utc_date.desc()).limit(1)
        ).scalar()
        out[side] = round((m.utc_date - prev).total_seconds() / 86400.0, 1) if prev else None
    return out


# A game in progress when predict-nfl ran can finish (and enter the rating
# walk) afterwards, so the drift window opens a game-length before the
# earliest prediction write.
_DRIFT_LOOKBACK = timedelta(hours=4)


def elo_drift_games(s, since) -> list:
    """NFL games FINISHED (by the ratings walk's rules) with kickoff in
    [since - lookback, now]: results that may have entered the Elo walk after
    the predictions were written, so export-time elo_* fields can lead the
    stored home_win_prob. Empty in the normal back-to-back chain."""
    if since is None:
        return []
    return [m for m in s.execute(
        nfl_scoped(select(Match)).where(
            Match.status == MatchStatus.FINISHED,
            Match.home_score.is_not(None),
            Match.utc_date >= since - _DRIFT_LOOKBACK,
            Match.utc_date <= utc_now_naive(),
        )).scalars() if "pre" not in (m.stage or "").lower()]


def export_nfl_predictions(days_ahead: int = 8, out_dir: str = "exports",
                           receipts: dict | None = None,
                           hours_ahead: float | None = None) -> str:
    # Export windowing (architect 2026-09-28): the FILE's rows are scoped to
    # kickoffs in [now, now + window]; predictions are generated and stored
    # exactly as before (early-week claims stay for CLV). hours_ahead wins
    # over days_ahead; the CLI defaults to the 36h current slate.
    # U2 "why" fields (2026-09-27): the ratings the model prices from — the
    # same _current_ratings() walk predict-nfl uses (finished NFL games,
    # preseason excluded), taken at export time.
    elo_cfg = NFLEloConfig()
    elo = _current_ratings()
    with session_scope() as s:
        now = utc_now_naive()
        hi = now + (timedelta(hours=hours_ahead) if hours_ahead is not None
                    else timedelta(days=days_ahead))
        if receipts is not None:
            receipts["window"] = {"from": now, "to": hi,
                                  "hours": round((hi - now).total_seconds() / 3600, 1)}
        q = (nfl_scoped(select(Prediction, Match)
                        .join(Match, Match.id == Prediction.match_id))
             .where(Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now,
                    Match.utc_date <= hi)
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
            elif _fb_live():
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
                qb = [i.player_name for i in team_inj if is_qb(i.player_position)]
                stamp = max((i.refreshed_at for i in team_inj), default=None)
                # positions_unresolved (additive, QB audit 2026-09-29): injured
                # players whose position never resolved — qb_listed cannot see
                # them, so an empty qb_listed beside these is NOT "no QB out".
                inj[side] = {"count": len(team_inj), "qb_listed": qb,
                             "positions_unresolved": [i.player_name for i in team_inj
                                                      if not i.player_position],
                             "synced_at": stamp.isoformat() if stamp else None}
            p_home = pred.home_win_prob
            _fair = ((market or {}).get("fair_prob") or {}
                     if (market or {}).get("fair_source") == "1X2" else {})
            divergence_pp = (round((p_home - _fair["HOME"]) * 100, 1)
                             if _fair.get("HOME") is not None else None)
            # Venue lie detector (2026-09-26): book fair vs Kalshi two-sided.
            # DISPLAY/WARNING ONLY — quarantine below still keys on the book
            # divergence exactly as ratified.
            from src.walters.venue import kalshi_exec, kalshi_home_prob, venue_gap
            kal = kalshi_home_prob(s.execute(select(OddsSnapshot).where(
                OddsSnapshot.match_id == m.id,
                OddsSnapshot.source == "kalshi")).scalars(), m.utc_date)
            gap_pp, venue_flag = venue_gap(_fair.get("HOME"),
                                           kal["home"] if kal else None)
            rows.append({
                "_computed_at": pred.computed_at,   # drift receipt only; popped
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
                # U2 "why" fields (additive, display only): elo_gap is the raw
                # rating difference; home_adv_applied is the Elo bonus the
                # home side gets inside the expectation (fixed config).
                "elo_home": round(elo.ratings.get(m.home_team_id, elo_cfg.default_rating), 1),
                "elo_away": round(elo.ratings.get(m.away_team_id, elo_cfg.default_rating), 1),
                "elo_gap": round(elo.ratings.get(m.home_team_id, elo_cfg.default_rating)
                                 - elo.ratings.get(m.away_team_id, elo_cfg.default_rating), 1),
                "home_adv_applied": elo_cfg.home_advantage,
                **{f"rest_days_{k}": v for k, v in _rest_days(s, m).items()},
                "kalshi_prob": round(kal["home"], 4) if kal else None,
                "kalshi_captured_at": (kal["captured_at"].isoformat()
                                       if kal and kal["captured_at"] else None),
                "venue_gap_pp": gap_pp,
                "venue_flag": venue_flag,
                # K-track (K1, additive): home-side Kalshi quotes + fee-adjusted
                # executable cost; only where Kalshi is two-sided.
                **(kalshi_exec(kal["home_bid"], kal["home_ask"]) if kal else
                   {"kalshi_bid": None, "kalshi_ask": None, "kalshi_exec_cost": None}),
                "input_quality": {
                    "book_odds": (market or {}).get("bookmaker_count", 0),
                    "injuries": inj,
                },
            })
        # U2 drift receipt (architect 2026-09-27): games that finished after
        # the earliest exported prediction was written.
        if receipts is not None:
            written = [r.get("_computed_at") for r in rows if r.get("_computed_at")]
            drift = elo_drift_games(s, min(written) if written else None)
            receipts["elo_drift_games"] = [f"{m.away_team.name} @ {m.home_team.name}"
                                           for m in drift]
    for r in rows:
        r.pop("_computed_at", None)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir,
                        f"nfl_predictions_{utc_now_naive().strftime('%Y-%m-%d')}.json")
    payload = {
        "exported_at": utc_now_naive().isoformat() + "Z",
        "git_sha": _git_sha(),
        "sport": "nfl",
        "model_version": MODEL_VERSION,
        "contains_predictions": True,
        "rehearsal": False,
        "live_since": "2026-09-22 (Week 3; ratified after two graded weeks)",
        "note": ("LIVE: gate-passed v1 Elo. CONTRACT RULE: rows with "
                 "market_divergence_pp >= 15 carry quarantine=true — "
                 "consumer treats them as watch-flagged, never straight "
                 "plays (rule earned 1-5 across Weeks 1-2). "
                 "venue_flag 'STALE-BOOK?' (|book fair - kalshi_prob| >= 8pp) "
                 "is a WARNING ONLY: it marks rows whose book reference — and "
                 "so their divergence/quarantine/edge — should be distrusted; "
                 "it does not change quarantine."),
        "count": len(rows),
        "predictions": rows,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


VALUE_FLOOR_PP = 4.0   # the Desk's NFL floor; the value-shadow cohort uses the same


def _book_anchor(s, m):
    """The value-side ANCHOR (architect 2026-09-29): the earliest pre-kickoff
    de-vigged 1X2 BOOK consensus snapshot (never Kalshi) — the claim-time
    analog, since a position is claimed at its first capture. Home prob
    normalized over that capture's selections, or None when the game has no
    book snapshot (games before sync-odds-football appended them). None is
    honest: the value side is then unknown, never guessed from the close.
    Returns (home_prob, captured_at) — the timestamp is recorded on every
    grade (ruling 2026-09-29) so "anchor == market at claim time" is
    visible, not asserted — or (None, None)."""
    snaps = list(s.execute(select(OddsSnapshot).where(
        OddsSnapshot.match_id == m.id, OddsSnapshot.market == "1X2",
        OddsSnapshot.source != "kalshi", OddsSnapshot.captured_at <= m.utc_date)
        .order_by(OddsSnapshot.captured_at)).scalars())
    if not snaps:
        return None, None
    at = snaps[0].captured_at
    first = [x for x in snaps if x.captured_at == at]
    tot = sum(x.devig_prob for x in first) or 0.0
    home = next((x.devig_prob for x in first if x.selection == "HOME"), None)
    return (home / tot, at) if home is not None and tot > 0 else (None, None)


def value_grade_for(s, m, pred, close_home) -> dict | None:
    """value_side_grade plus the anchor's provenance (ruling 2026-09-29 on
    #63 (b)): anchor_at, the prediction's computed_at, and whether the
    anchor preceded it (sync precedes predict in every chain, so it should)."""
    anchor_home, anchor_at = _book_anchor(s, m)
    vg = value_side_grade(pred.home_win_prob, anchor_home, close_home)
    if vg is not None:
        vg["anchor_at"] = anchor_at
        vg["prediction_at"] = pred.computed_at
        vg["anchor_before_prediction"] = (anchor_at <= pred.computed_at
                                          if anchor_at and pred.computed_at else None)
    return vg


def _hm(dt) -> str:
    return dt.strftime("%m-%d %H:%MZ") if dt else "—"


def value_side_grade(p_home: float, anchor_home: float | None, close_home: float | None) -> dict | None:
    """value_side_clv = model p − close p on the VALUE side: the side where
    model − market was positive at the anchor. Beside pick-vs-close (the
    model's top pick vs the close), never replacing it. shadow = the value
    side is not the top pick and cleared the floor at the anchor (the
    Cockpit's v1.2-candidate value_shadow cohort). None without an anchor
    and a close, or when the anchor edge is exactly zero."""
    if anchor_home is None or close_home is None:
        return None
    edge_home = p_home - anchor_home
    if edge_home == 0:
        return None
    v_home = edge_home > 0
    side_p = p_home if v_home else 1 - p_home
    side_close = close_home if v_home else 1 - close_home
    return {"side": "HOME" if v_home else "AWAY",
            "edge_at_anchor_pp": round(abs(edge_home) * 100, 1),
            "value_side_clv": side_p - side_close,
            "shadow": (v_home != (p_home >= 0.5)) and abs(edge_home) * 100 >= VALUE_FLOOR_PP}


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
        now = utc_now_naive()
        q = (nfl_scoped(select(Prediction, Match)
                        .join(Match, Match.id == Prediction.match_id))
             .where(Match.status == MatchStatus.FINISHED,
                    Match.utc_date >= now - timedelta(days=days_back))
             .order_by(Match.utc_date))
        hits = n = 0
        ll = 0.0
        clvs = []
        vclvs, vshadow = [], []
        anchor_after = 0
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
            vg = value_grade_for(s, m, pred, close_h)
            if vg:
                anchor_after += vg["anchor_before_prediction"] is False
                vclvs.append(vg["value_side_clv"])
                if vg["shadow"]:
                    vshadow.append(vg["value_side_clv"])
            report(f"  {m.away_team.name[:14]:14} @ {m.home_team.name[:15]:15} "
                   f"{m.away_score:>2}-{m.home_score:<2} model_H={p:.3f} "
                   f"close_H={'%.3f' % close_h if close_h is not None else '  — '} "
                   f"{'HIT ' if hit else 'miss'} "
                   f"clv={'%+.1fpp' % (clv*100) if clv is not None else '—'} "
                   f"value={(vg['side'] + ' %+.1fpp' % (vg['value_side_clv'] * 100) + (' [shadow]' if vg['shadow'] else '')) if vg else '— (no anchor)'}"
                   + (f" anchor={_hm(vg['anchor_at'])} pred={_hm(vg['prediction_at'])}"
                      + (" ⚠ ANCHOR AFTER PREDICTION" if vg["anchor_before_prediction"] is False else "")
                      if vg else ""))
        if n == 0:
            return {"ok": False, "reason": "no finished NFL games with predictions in window"}
        summary = {"ok": True, "games": n, "hits": hits,
                   "logloss": round(ll / n, 4),
                   "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
                   # value side (architect 2026-09-29) — beside, never replacing, pick-vs-close
                   "value_side_n": len(vclvs),
                   "mean_value_side_clv_pp": round(sum(vclvs) / len(vclvs) * 100, 2) if vclvs else None,
                   "value_shadow_n": len(vshadow),
                   "mean_value_shadow_clv_pp": round(sum(vshadow) / len(vshadow) * 100, 2) if vshadow else None,
                   "value_anchor_after_prediction_n": anchor_after}
        report(f"  ── sides {hits}/{n} · log-loss {summary['logloss']} · "
               f"mean CLV {summary['mean_clv_pp']}pp (n={len(clvs)} priced)")
        report(f"  ── value side vs close {summary['mean_value_side_clv_pp']}pp "
               f"(n={len(vclvs)} anchored; {n - len(vclvs)} unanchored — no pre-kickoff book snapshot) · "
               f"value-shadow cohort {summary['mean_value_shadow_clv_pp']}pp (n={len(vshadow)}) · "
               f"anchor after prediction: {anchor_after}/{len(vclvs)}")
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
        now = utc_now_naive()
        q = (nfl_scoped(select(Prediction, Match)
                        .join(Match, Match.id == Prediction.match_id))
             .where(Match.status == MatchStatus.FINISHED,
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
            vg = value_grade_for(s, m, pred, close_h)
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
                           "clv": round(clv, 4) if clv is not None else None,
                           # value side (additive, rulings 2026-09-29): null when unanchored
                           "value_side": vg["side"] if vg else None,
                           "value_side_clv": round(vg["value_side_clv"], 4) if vg else None,
                           "value_shadow": vg["shadow"] if vg else None,
                           "value_anchor_at": (vg["anchor_at"].isoformat()
                                               if vg and vg["anchor_at"] else None),
                           "value_prediction_at": (vg["prediction_at"].isoformat()
                                                   if vg and vg["prediction_at"] else None)},
            })
    _os.makedirs(out_dir, exist_ok=True)
    path = _os.path.join(out_dir, f"nfl_NFL_results_{utc_now_naive().strftime('%Y-%m-%d')}.json")
    with open(path, "w") as f:
        _json.dump({"exported_at": utc_now_naive().isoformat() + "Z",
                    "git_sha": _git_sha(),
                    "sport": "nfl",
                    "note": "record is variance, not signal — for the consumer to grade against",
                    "count": len(rows), "results": rows}, f, indent=2)
    return path
