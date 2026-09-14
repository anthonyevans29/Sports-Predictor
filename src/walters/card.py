"""
Shared daily-card assembly — ONE source of truth for both the CLI `card`
command and the web /card page, so the two can never drift apart.

The card is a FACT ASSEMBLER, not a rationale generator. It surfaces the
numbers the model already computes and tags cautions by explicit, deterministic
rules. Crucially, market DISAGREEMENT is flagged as CAUTION, not EDGE — until
CLV proves the model beats the close, a disagreement is the anti-predictive
condition the blend corrects, not an opportunity. Interpretation stays
human-in-the-loop.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Sport, Match, Prediction, Odds, MatchStatus
from src.walters.value import MarketSnapshot
from src.web.preview import (classify_tier, expression_signal,
                             bullpen_swing_flag, close_game_flag)

# Thresholds for deterministic flags (kept here so both surfaces agree).
MARKET_DISAGREE_PP = 3.0       # |model - market| >= this → disagreement caution
BULLPEN_SWING_CAUTION = 1.5    # bullpen swing >= this → not a parlay anchor
BETTABLE_MIN_PROB = 0.525      # below this → prediction-only

# Minimum run gap (|model_total - market_total|) before a totals disagreement
# is treated as a bettable edge rather than noise. Cushion scales with line
# height: low lines (7.5) need a BIGGER gap because each run is a larger share
# of the total and one-run variance dominates. Derived from the 2026-06-28
# thin-under losses (BOS/NYY Under 8.0 had only a 0.23-run gap; CLE/SEA Under
# 7.5 only 0.36) — both lost, both ranked too high because the card read low
# over-prob as edge instead of the actual gap. These gate "is this worth
# tracking," NOT "is this +EV" — CLV still decides the latter."""
def _total_gap_cushion(line: float) -> float:
    if line >= 9.5:
        return 0.75
    if line >= 8.5:
        return 0.85
    if line >= 8.0:
        return 1.00
    return 1.20  # 7.5 and below


def build_card(target_date=None) -> dict:
    """
    Build the structured card for a given local date (default today).

    Returns {"date": date, "games": [ {...}, ... ]} where each game dict has:
      match, pick, side, prob, mkt_edge, score, proj_home, proj_away, tier,
      ou_line, over_prob, totals_available, stronger, model_total,
      market_total, total_gap, total_side, bettable_total_edge,
      bet_suitability, recommended_market, bp_swing, fb, flags.
    flags is a list of (level, message) with level in {"caution","note"}.
    Games are sorted by the deterministic sort score (NOT a probability).
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).astimezone().date()

    games = []
    with session_scope() as s:
        rows = s.execute(
            select(Prediction, Match)
            .join(Match, Match.id == Prediction.match_id)
            .where(Match.sport == Sport.MLB,
                   Match.status == MatchStatus.SCHEDULED)
            .order_by(Match.utc_date)
        ).all()

        for pred, m in rows:
            # m.utc_date is stored NAIVE in UTC. Mark it UTC, THEN convert to
            # local — otherwise .astimezone() wrongly assumes it's already local
            # and West-Coast night games (which roll past midnight UTC) get
            # bucketed to tomorrow and dropped.
            local_dt = m.utc_date.replace(tzinfo=timezone.utc).astimezone()
            if local_dt.date() != target_date:
                continue
            probs = {"home": pred.home_win_prob, "away": pred.away_win_prob}
            nn = {k: v for k, v in probs.items() if v is not None}
            if not nn:
                continue
            side = max(nn, key=nn.get)
            prob = nn[side]
            home_name = m.home_team.name if m.home_team else f"team{m.home_team_id}"
            away_name = m.away_team.name if m.away_team else f"team{m.away_team_id}"
            pick_name = home_name if side == "home" else away_name
            fb = pred.factor_breakdown or {}

            starter_known = (fb.get("home_starter_known", True) and
                             fb.get("away_starter_known", True))
            tier_info = classify_tier(prob, starter_known=starter_known)
            expr = expression_signal(prob, pred.over_prob)
            bp = bullpen_swing_flag(fb)
            cg = close_game_flag(prob, fb)
            max_swing = bp["max_swing"] if bp else 0.0

            # market edge on the model's pick (de-vigged consensus)
            odds = list(s.execute(
                select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")
            ).scalars())
            mkt_edge = None
            if odds:
                by_sel = {}
                for o in odds:
                    by_sel.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
                imp = MarketSnapshot(market="1X2", by_selection=by_sel).average_implied()
                over = sum(imp.values())
                sel = "HOME" if side == "home" else "AWAY"
                if over > 0 and sel in imp:
                    mkt_edge = (prob - imp[sel] / over) * 100

            flags = []
            if mkt_edge is not None and mkt_edge <= -MARKET_DISAGREE_PP:
                flags.append(("caution", f"model below market {mkt_edge:+.1f}pp "
                                         f"(disagreement — NOT a proven edge)"))
            elif mkt_edge is not None and mkt_edge >= MARKET_DISAGREE_PP:
                flags.append(("caution", f"model above market {mkt_edge:+.1f}pp "
                                         f"(disagreement — NOT a proven edge)"))
            if max_swing >= BULLPEN_SWING_CAUTION:
                flags.append(("caution", f"bullpen swing {max_swing:.2f} "
                                         f"(not a parlay anchor)"))
            if cg:
                flags.append(("note", "close-game flag (single only, not anchor)"))
            if tier_info.get("capped_by_starter"):
                flags.append(("note", "starter sample/uncertainty cap applied"))
            if prob < BETTABLE_MIN_PROB:
                flags.append(("note", "sub-52.5% — prediction-only, not bettable on its own"))

            # --- Bucket 1: explicit total-gap vs market line ---
            # Read the actual run gap against the line instead of inferring edge
            # from over-prob. This is what distinguishes a real totals lean from
            # a thin one that just happens to have low over-prob.
            model_total = None
            market_total = pred.over_under_line
            total_gap = None
            bettable_total_edge = False
            total_side = None  # "under" or "over" the model leans, by gap sign
            if (pred.expected_home_score is not None and
                    pred.expected_away_score is not None):
                model_total = pred.expected_home_score + pred.expected_away_score
            if model_total is not None and market_total is not None:
                total_gap = model_total - market_total      # negative → under lean
                cushion = _total_gap_cushion(market_total)
                bettable_total_edge = abs(total_gap) >= cushion
                total_side = "under" if total_gap < 0 else "over"
                # Flag a totals-driven game whose gap is too thin to be a real edge
                if expr and expr.get("stronger") == "total" and not bettable_total_edge:
                    flags.append(("caution",
                        f"thin total: {total_side} {market_total}, gap only "
                        f"{total_gap:+.2f} (needs ±{cushion:.2f}) — lean not edge"))
                # Fragile-under flag: an under lean with a high one-team-explosion
                # probability is exactly the trap that blew up 6/30 (Rays 10,
                # Marlins 14). Use the HIGHER single-team blowup prob, not the
                # combined — an under dies when ONE team explodes, and a low
                # combined number can hide a one-sided risk (7/4: Seattle under
                # lost 11-0; combined p_blowup was low because Toronto was quiet,
                # but Seattle's own blowup prob was high). p_*_blowup read off the
                # model's own score distribution.
                p_home_bl = fb.get("p_home_blowup")
                p_away_bl = fb.get("p_away_blowup")
                p_blowup = fb.get("p_blowup")
                # Prefer the max of the per-team probs; fall back to combined if
                # per-team fields are absent (older predictions).
                if p_home_bl is not None or p_away_bl is not None:
                    max_team_bl = max(p_home_bl or 0.0, p_away_bl or 0.0)
                    which = "home" if (p_home_bl or 0) >= (p_away_bl or 0) else "away"
                    if total_side == "under" and max_team_bl >= 0.30:
                        flags.append(("caution",
                            f"fragile under: P({which} team ≥7 runs) = "
                            f"{max_team_bl*100:.0f}% — one-sided blowup risk"))
                elif (total_side == "under" and p_blowup is not None
                        and p_blowup >= 0.45):
                    flags.append(("caution",
                        f"fragile under: P(either team ≥7 runs) = "
                        f"{p_blowup*100:.0f}% — one-team blowup risk"))

            # deterministic SORT score (not a probability; never feeds the model)
            score = prob
            if mkt_edge is not None and mkt_edge < 0:
                score += mkt_edge / 1000.0
            if max_swing >= BULLPEN_SWING_CAUTION:
                score -= 0.005
            if cg:
                score -= 0.003

            # --- Bucket 1: explicit bet-suitability metadata (item 10) ---
            # Expresses the conclusion the flags already imply, so "model likes
            # it" can't silently become "bet it". Purely derived from the
            # deterministic flags above — adds no new judgement.
            has_caution = any(lvl == "caution" for lvl, _ in flags)
            side_bettable = prob >= BETTABLE_MIN_PROB
            if expr and expr.get("stronger") == "total" and bettable_total_edge:
                recommended_market = f"total ({total_side} {market_total})"
                bet_suitability = "test" if has_caution else "cleaner"
            elif side_bettable and not has_caution:
                recommended_market = "side"
                bet_suitability = "cleaner"
            elif side_bettable and has_caution:
                recommended_market = "side (caution)"
                bet_suitability = "test-only"
            else:
                recommended_market = "pass"
                bet_suitability = "prediction-only"

            games.append({
                "match": f"{away_name} @ {home_name}",
                "match_id": m.id,
                "pick": pick_name, "side": side, "prob": prob,
                "mkt_edge": mkt_edge, "score": score,
                "proj_home": pred.expected_home_score,
                "proj_away": pred.expected_away_score,
                "tier": tier_info.get("tier"),
                "ou_line": pred.over_under_line, "over_prob": pred.over_prob,
                "totals_available": pred.over_under_line is not None,
                "stronger": expr["stronger"] if expr else "side",
                "model_total": model_total, "market_total": market_total,
                "total_gap": total_gap, "total_side": total_side,
                "bettable_total_edge": bettable_total_edge,
                "p_blowup": fb.get("p_blowup"),
                "bet_suitability": bet_suitability,
                "recommended_market": recommended_market,
                "bp_swing": max_swing,
                "fb": fb, "flags": flags,
            })

    games.sort(key=lambda g: g["score"], reverse=True)
    return {"date": target_date, "games": games}
