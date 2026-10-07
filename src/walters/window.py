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
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from src.timeutil import utc_now_naive, utc_naive_fromtimestamp

CARD_NAME = "window_24h.json"
_SKIP_PREFIXES = ("window_", "fixtures_")


_QUAR_SHADOW_TAG = re.compile(r"^quarantine .*\(shadow\)$")


def desk_quarantined(dk: dict | None) -> bool:
    """The row's own Desk block records a quarantine shadow — the Cockpit's fileQuar predicate: call PASS,
    shadow_units > 0, a "quarantine … (shadow)" tag. MLB >8pp (ARCHITECT 2026-10-07) lives ONLY here: the export
    row's own `quarantine` field stays false for MLB (Codex on #328)."""
    dk = dk or {}
    return bool(dk.get("call") == "PASS" and (dk.get("shadow_units") or 0) > 0
                and any(isinstance(t, str) and _QUAR_SHADOW_TAG.match(t) for t in (dk.get("tags") or [])))


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
        if doc.get("engine") == "model_shadow":
            continue   # NHL shadow (failed gate): never a model on the card
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
            dk = r.get("desk") or {}
            row = {"model_version": pred.get("model_version"), "p": p, "top_pick": top,
                   "top_pick_prob": pred.get("top_pick_prob", p.get(top) if top else None),
                   "tier": pred.get("tier"),
                   # the export field OR the row's Desk quarantine shadow (MLB >8pp, Codex on #328)
                   "quarantine": True if desk_quarantined(dk) else r.get("quarantine"),
                   "market_divergence_pp": r.get("market_divergence_pp"),
                   "source_file": f.name, "exported_at": stamp,
                   # F1: the Desk's call when the export carries it (--desk); else None
                   "desk": ({k: dk.get(k) for k in ("call", "units", "pass_kind", "reference",
                                                    "market_ref", "edge_pp")}
                            if dk.get("engine") == "model_edge" else None)}
            if mid not in out or stamp >= out[mid]["exported_at"]:
                out[mid] = row
    return out


def short_name(team) -> str | None:
    """The phone card's team label: the three-letter code, else the short
    name, else the club's last word for long names (card page, 2026-10-01)."""
    if team is None:
        return None
    if team.tla:
        return team.tla
    if team.short_name and len(team.short_name) <= 14:
        return team.short_name
    words = (team.name or "?").split()
    if len(words) == 1:
        return words[0]
    return " ".join(words[-2:]) if len(words[-1]) <= 4 else words[-1]   # "Red Sox", "Blue Jays"; "Braves"


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
    from src.ingestion.mlb_apisports import time_unconfirmed
    from src.db.schema import Injury
    from src.walters.qb_audit import is_qb

    now = now or utc_now_naive()
    hi = now + timedelta(hours=hours)
    models = canonical_models(export_dir)
    labels: Counter = Counter()
    counts = {"fixtures": 0, "with_books": 0, "with_spread_derived": 0, "close_unpriced": 0,
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
                "home_short": short_name(m.home_team), "away_short": short_name(m.away_team),
                "model": model, "edge_pp": edge,
                "tier": model["tier"] if model else None,
                "quarantine": bool(model and model.get("quarantine")),
                "kalshi_home_norm": round(kal["home"], 4) if kal else None,
                "venue_gap_pp": gap_pp, "venue_flag": flag,
                "line_move": lm, "late_news_flag": lm["flag"] if lm else None,
                "engine": "model_edge" if model else "market_only",
                # MLB start time not confirmed by statsapi (finding 2026-10-01: api-sports
                # placeholder times for TBD postseason starts); None = confirmed
                "time_flag": time_unconfirmed(m) if code.upper() == "MLB" else None,
                # #192 (ruling 2026-10-01): injured QBs on either side, so the pager can
                # page ONE news item per player across every game that team plays
                "qb_news": [{"team_id": i.team_id, "team": short_name(t), "player": i.player_name,
                             "status": i.type or ""}
                            for t in (m.home_team, m.away_team) if t is not None
                            for i in s.execute(select(Injury).where(Injury.team_id == t.id)).scalars()
                            if is_qb(i.player_position)],
            })
            # F1c (#191): the venue verdict comes from the Python Desk (the
            # Cockpit no longer computes policy) — same inputs the card's
            # JS read before: book fair, books, Kalshi two-sided, kickoff.
            from src.walters import desk_policy as _dp
            row["desk_venue"] = _dp.window_venue(
                row, float((now - datetime(1970, 1, 1)) // timedelta(milliseconds=1)))
            rows.append(row)
    counts["fixtures"] = len(rows)
    return {
        "exported_at": now.isoformat() + "Z",
        "git_sha": _git_sha(),
        "window": {"from": now.isoformat() + "Z", "to": hi.isoformat() + "Z", "hours": hours},
        "contains_predictions": any(r["model"] for r in rows),
        "note": ("Next-24h window card: book fair, Kalshi and venue flags repriced hourly; "
                 "model fields copied from the canonical chain-slot exports (no model re-runs). "
                 "engine=model_edge rows carry a model; every row carries desk_venue, the "
                 "venue verdict from the Python Desk as of exported_at (F1c: the Cockpit renders it)."),
        "count": len(rows),
        "receipts": {**counts, "with_model": sum(1 for r in rows if r["model"]),
                     "stale_flags": sum(1 for r in rows if r["venue_flag"]),
                     "quarantined": sum(1 for r in rows if r["quarantine"]),
                     "late_news": sum(1 for r in rows if r["late_news_flag"]),
                     "time_unconfirmed": sum(1 for r in rows if r["time_flag"])},
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
