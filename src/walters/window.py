"""Next-24h window card (architect spec, 2026-09-27): WINDOW SERVICE.

Builds exports/window_24h.json: every game kicking off inside the window,
kickoff-sorted, across every competition in the DB. It is sport-agnostic by
construction, so adding a competition adds rows, not code.

NO MODEL RUNS HERE. Model fields come from the CANONICAL chain-slot exports
already on disk (their `predictions` rows, joined on match_id), so predictions
stay exactly what their chain slot produced. The card only reprices the
market side:
- book fair and Kalshi, via export._fixture_row (the fixtures grammar the
  Cockpit renders);
- the venue gap and the STALE-BOOK? flag, via venue.kalshi_home_prob and
  venue.venue_gap (the same math as the NFL export);
- edge = model top-pick prob minus the book fair for the same side, in pp.

The venue-edge CHARTER (>=4 books, two-sided, >=5pp) is Cockpit policy v1.1
and is NOT re-implemented here. The card carries its inputs, and the
Cockpit's venue engine decides eligibility. `engine` is model_edge when a
canonical model row exists, else market_only.
"""
from __future__ import annotations

import json
import os
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from src.timeutil import utc_now_naive, utc_naive_fromtimestamp

CARD_NAME = "window_24h.json"
_SKIP_PREFIXES = ("window_", "fixtures_")


def _norm_pick(p: str | None) -> str | None:
    return {"home_win": "HOME", "draw": "DRAW", "away_win": "AWAY"}.get(p or "", None)


def canonical_models(export_dir: str | os.PathLike) -> dict[int, dict]:
    """match_id -> the newest canonical model row across the exports on disk.
    Reads MLB/soccer (`prediction.probabilities`) and NFL
    (`prediction.home_win_prob`) row shapes. Unknown shapes are skipped,
    never guessed."""
    out: dict[int, dict] = {}
    d = Path(export_dir)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        if f.name.startswith(_SKIP_PREFIXES):
            continue
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("predictions"), list):
            continue
        stamp = doc.get("exported_at") or utc_naive_fromtimestamp(f.stat().st_mtime).isoformat()
        for r in doc["predictions"]:
            pred, mid = (r or {}).get("prediction"), (r or {}).get("match_id")
            if not pred or mid is None:
                continue
            probs = pred.get("probabilities") or {}
            p = {"HOME": probs.get("home_win", pred.get("home_win_prob")),
                 "DRAW": probs.get("draw"),
                 "AWAY": probs.get("away_win", pred.get("away_win_prob"))}
            top = _norm_pick(pred.get("top_pick"))
            row = {"model_version": pred.get("model_version"), "p": p, "top_pick": top,
                   "top_pick_prob": pred.get("top_pick_prob", p.get(top) if top else None),
                   "tier": pred.get("tier"), "quarantine": r.get("quarantine"),
                   "market_divergence_pp": r.get("market_divergence_pp"),
                   "source_file": f.name, "exported_at": stamp}
            if mid not in out or stamp >= out[mid]["exported_at"]:
                out[mid] = row
    return out


def build_card(now: datetime | None = None, hours: int = 24,
               export_dir: str = "exports") -> dict:
    """The window card payload (read-only against the DB)."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, OddsSnapshot
    from src.walters.export import _fixture_row
    from src.walters.provenance import git_sha as _git_sha
    from src.walters.line_move import _is_soccer, line_move_for_match
    from src.walters.venue import kalshi_home_prob, venue_gap

    now = now or utc_now_naive()
    hi = now + timedelta(hours=hours)
    models = canonical_models(export_dir)
    labels: Counter = Counter()
    counts = {"fixtures": 0, "with_books": 0, "with_spread_derived": 0,
              "kalshi_two_sided": 0, "kalshi_one_sided": 0, "kalshi_partial": 0,
              "kalshi_absent": 0}
    rows = []
    with session_scope() as s:
        q = (select(Match).where(Match.utc_date >= now, Match.utc_date < hi,
                                 Match.status != MatchStatus.FINISHED)
             .order_by(Match.utc_date, Match.id))
        for m in s.execute(q).scalars():
            comp = m.competition
            code = comp.code if comp else "?"
            row = _fixture_row(s, m, code, labels, counts)
            fair = ((row.get("market") or {}).get("fair_prob") or {})
            snaps = list(s.execute(select(OddsSnapshot).where(
                OddsSnapshot.match_id == m.id, OddsSnapshot.source == "kalshi")).scalars())
            kal = kalshi_home_prob(snaps, m.utc_date, three_way=_is_soccer(m))   # #117
            gap_pp, flag = venue_gap(fair.get("HOME"), kal["home"] if kal else None)
            # LINE-MOVE ALARM (ruling 2026-09-29): >= 6pp on either venue inside
            # T-3h marks the row "late-news?"; sp_window_page pages it and
            # requests freshen:<family>. Stored snapshots only, no provider calls.
            lm = line_move_for_match(s, m, now)
            model = models.get(m.id)
            edge = None
            if model and model["top_pick"] and model["top_pick_prob"] is not None \
                    and fair.get(model["top_pick"]) is not None:
                edge = round((model["top_pick_prob"] - fair[model["top_pick"]]) * 100, 1)
            sport = comp.sport.value if comp and hasattr(comp.sport, "value") else str(
                comp.sport if comp else "?")
            row.update({
                "sport": sport, "competition": code,
                "model": model, "edge_pp": edge,
                "tier": model["tier"] if model else None,
                "quarantine": bool(model and model.get("quarantine")),
                "kalshi_home_norm": round(kal["home"], 4) if kal else None,
                "venue_gap_pp": gap_pp, "venue_flag": flag,
                "line_move": lm, "late_news_flag": lm["flag"] if lm else None,
                "engine": "model_edge" if model else "market_only",
            })
            rows.append(row)
    counts["fixtures"] = len(rows)
    return {
        "exported_at": now.isoformat() + "Z",
        "git_sha": _git_sha(),
        "window": {"from": now.isoformat() + "Z", "to": hi.isoformat() + "Z", "hours": hours},
        "contains_predictions": any(r["model"] for r in rows),
        "note": ("Next-24h window card: book fair, Kalshi and venue flags repriced hourly; "
                 "model fields copied from the canonical chain-slot exports (no model re-runs). "
                 "engine=model_edge rows carry a model; market_only rows are for the "
                 "Cockpit venue engine (charter evaluated client-side, policy v1.1)."),
        "count": len(rows),
        "receipts": {**counts, "with_model": sum(1 for r in rows if r["model"]),
                     "stale_flags": sum(1 for r in rows if r["venue_flag"]),
                     "quarantined": sum(1 for r in rows if r["quarantine"]),
                     "late_news": sum(1 for r in rows if r["late_news_flag"])},
        "fixtures": rows,
    }


def write_card(payload: dict, export_dir: str = "exports") -> str:
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, CARD_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)  # readers never see a half-written card
    return path


def t90_signatures(match_ids, now: datetime | None = None, minutes: int = 90) -> dict:
    """Injury/lineup state for games kicking off within T-minutes, as
    comparable signatures: injuries per team (count + a digest of the rows'
    content, never the refresh time) and
    lineups per match (count, kinds). A change versus the previous run means
    news landed inside T-90."""
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Injury, Lineup, Match

    now = now or utc_now_naive()
    out: dict[str, str] = {}
    with session_scope() as s:
        for m in s.execute(select(Match).where(
                Match.id.in_(list(match_ids) or [-1]),
                Match.utc_date >= now,
                Match.utc_date < now + timedelta(minutes=minutes))).scalars():
            inj = []
            for tid in (m.home_team_id, m.away_team_id):
                # CONTENT, not refresh time (ruling 2026-09-29 on #65): the
                # imminent tier now re-syncs injuries every run (wipe and
                # re-insert), so a max(refreshed_at) signature would change
                # every run and fire freshens with no news.
                rows = sorted((i.player_name or "", i.player_position or "", i.type or "", i.reason or "")
                              for i in s.execute(select(Injury).where(Injury.team_id == tid)).scalars())
                digest = hashlib.sha1(repr(rows).encode()).hexdigest()[:12]
                inj.append(f"{tid}:{len(rows)}:{digest}")
            ln, kinds = s.execute(select(func.count(Lineup.id),
                                         func.group_concat(Lineup.kind.distinct()))
                                  .where(Lineup.match_id == m.id)).one()
            out[str(m.id)] = f"inj[{'|'.join(inj)}] lineup[{ln}:{kinds}]"
    return out
