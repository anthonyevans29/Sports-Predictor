#!/usr/bin/env python3
"""Window-card pager (architect spec 2026-09-27). It runs as the `window`
chain's post-step after a clean run. It is stdlib-only and reads the card
JSON only.

Delivery: the SECOND private ntfy topic, NTFY_CARD_TOPIC (read from .env).
It is DELTA-DRIVEN: it pushes only when the card changed since the previous
run. The delta classes:
    new_priced   a game in the window that now has a book fair or Kalshi
                 price, where it had none (or wasn't on the card) before
    tier         the canonical model tier changed (a new chain-slot export)
    quarantine   the quarantine flag flipped
    stale        the venue flag changed (STALE-BOOK? appeared or cleared)
    kickoff      the kickoff time moved, or the status moved to
                 POSTPONED / CANCELLED
    t90_news     injury/lineup state changed for a game inside T-90; the
                 window chain then triggers freshen:<family> (sp_run)
    line_move    LINE-MOVE ALARM (ruling 2026-09-29): the card row turned
                 "late-news?" (>= 6pp on book or Kalshi inside T-3h, from
                 stored snapshots); pages and triggers freshen:<family>
Quiet hours are 00:00-07:00 America/New_York: everything except the
quarantine-class deltas (quarantine flips and line moves, ruling 2026-09-29) is
suppressed there, and still receipted. Plus ONE fixed daily digest
on the first run at or after 08:00 ET. State lives in SP_WINDOW_STATE
(default <receipts dir>/window_state.json). Every run appends a receipt of
kind "window_page".
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

ET = ZoneInfo("America/New_York")
QUIET = (0, 7)          # [00:00, 07:00) ET
DIGEST_HOUR = 8         # first run at/after 08:00 ET
CLASSES = ("new_priced", "tier", "quarantine", "stale", "kickoff", "t90_news", "line_move")
FRESHEN_CLASSES = ("t90_news", "line_move")
URGENT = ("quarantine", "line_move")


def state_path() -> Path:
    return Path(c.setting("SP_WINDOW_STATE") or c.receipts_path().with_name("window_state.json"))


def snapshot(card: dict) -> dict:
    out = {}
    for r in card.get("fixtures", []):
        out[str(r["match_id"])] = {
            "label": f"{r.get('away_team')} @ {r.get('home_team')}",
            "sport": r.get("sport"), "competition": r.get("competition"),
            "utc_date": r.get("utc_date"), "status": r.get("status"),
            "priced": bool(r.get("market") or r.get("kalshi")),
            "tier": r.get("tier"), "quarantine": bool(r.get("quarantine")),
            "venue_flag": r.get("venue_flag"), "edge_pp": r.get("edge_pp"),
            "engine": r.get("engine"),
            "late_news": r.get("late_news_flag"), "line_move": _move_text(r.get("line_move"))}
    return out


def _move_text(lm) -> str | None:
    """'book 0.489->0.560 (+7.1pp)' for the venues that crossed the alarm."""
    if not lm:
        return None
    bits = [f"{k} {v['from']:.3f}->{v['to']:.3f} ({v['move_pp']:+.1f}pp)"
            for k, v in (lm.get("venues") or {}).items() if v.get("alarm")]
    return " · ".join(bits) or None


def deltas(prev: dict, cur: dict, prev_t90: dict, cur_t90: dict) -> list[dict]:
    out = []
    for mid, g in cur.items():
        p = prev.get(mid)
        if g["priced"] and (p is None or not p["priced"]):
            out.append({"cls": "new_priced", "id": mid, "g": g})
        if g.get("late_news") and (p is None or not p.get("late_news")):
            out.append({"cls": "line_move", "id": mid, "g": g})
        if p is None:
            continue
        if g["tier"] != p["tier"]:
            out.append({"cls": "tier", "id": mid, "g": g, "was": p["tier"]})
        if g["quarantine"] != p["quarantine"]:
            out.append({"cls": "quarantine", "id": mid, "g": g, "was": p["quarantine"]})
        if g["venue_flag"] != p["venue_flag"]:
            out.append({"cls": "stale", "id": mid, "g": g, "was": p["venue_flag"]})
        if g["utc_date"] != p["utc_date"] or (
                g["status"] != p["status"] and str(g["status"]).lower() in ("postponed", "cancelled")):
            out.append({"cls": "kickoff", "id": mid, "g": g, "was": p["utc_date"]})
    for mid, sig in cur_t90.items():
        if mid in prev_t90 and prev_t90[mid] != sig and mid in cur:
            out.append({"cls": "t90_news", "id": mid, "g": cur[mid]})
    return out


def _ko(g) -> str:
    try:
        return datetime.fromisoformat(g["utc_date"]).replace(tzinfo=ZoneInfo("UTC")) \
            .astimezone(ET).strftime("%a %H:%M ET")
    except (TypeError, ValueError):
        return "?"


def line(d: dict) -> str:
    g = d["g"]
    head = f"{_ko(g)} {str(g['sport']).upper()} {g['label']}"
    what = {"new_priced": "priced" + (f" (edge {g['edge_pp']:+.1f}pp)" if g["edge_pp"] is not None else ""),
            "tier": f"tier {d.get('was')} -> {g['tier']}",
            "quarantine": f"QUARANTINE {'ON' if g['quarantine'] else 'off'}",
            "stale": f"venue {d.get('was') or 'ok'} -> {g['venue_flag'] or 'ok'}",
            "kickoff": f"kickoff moved from {d.get('was')} (status {g['status']})",
            "t90_news": "injury/lineup news inside T-90: freshen triggered",
            "line_move": f"LINE MOVE inside T-3h: {g.get('line_move')}: {g.get('late_news')} freshen triggered"}[d["cls"]]
    return f"{head}: {what}"


def digest(cur: dict) -> str:
    games = sorted(cur.values(), key=lambda g: g["utc_date"] or "")
    lines = [f"{len(games)} games in the next 24h; "
             f"{sum(1 for g in games if g['engine'] == 'model_edge')} with a model, "
             f"{sum(1 for g in games if g['quarantine'])} quarantined, "
             f"{sum(1 for g in games if g['venue_flag'])} STALE-BOOK?"]
    for g in games[:15]:
        bits = [x for x in (g["tier"], f"edge {g['edge_pp']:+.1f}pp" if g["edge_pp"] is not None else None,
                            "QUARANTINE" if g["quarantine"] else None, g["venue_flag"]) if x]
        lines.append(f"{_ko(g)} {str(g['sport']).upper()} {g['label']}" + (f" [{', '.join(bits)}]" if bits else ""))
    if len(games) > 15:
        lines.append(f"... {len(games) - 15} more on the card")
    return "\n".join(lines)


def run(card_path: Path, now_utc: datetime | None = None) -> dict:
    import sp_notify
    now_utc = now_utc or c.utc_now()
    et = now_utc.astimezone(ET)
    try:
        card = json.loads(Path(card_path).read_text())
    except (OSError, ValueError) as e:
        rec = {"kind": "window_page", "exit": 1, "error": type(e).__name__}
        c.append_receipt(rec)
        return rec
    sp = state_path()
    try:
        state = json.loads(sp.read_text())
    except (OSError, ValueError):
        state = {}
    first_run = not state
    cur, cur_t90 = snapshot(card), card.get("t90_signatures") or {}
    ds = [] if first_run else deltas(state.get("games", {}), cur, state.get("t90", {}), cur_t90)
    quiet = QUIET[0] <= et.hour < QUIET[1]
    # QUARANTINE-CLASS (exempt from quiet hours, high priority): quarantine flips
    # and, by ruling 2026-09-29 on #65, line moves — early European kickoffs put
    # T-3h inside 00-07 ET, exactly when late news lands.
    send = [d for d in ds if not quiet or d["cls"] in URGENT]
    suppressed = len(ds) - len(send)
    paged = False
    if send:
        body = "\n".join(line(d) for d in send[:25])
        paged = sp_notify.deliver("card", f"Next 24h: {len(send)} change(s)", body,
                                  topic_var="NTFY_CARD_TOPIC",
                                  priority="high" if any(d["cls"] in URGENT for d in send)
                                  else "default")
    did_digest = False
    today = et.date().isoformat()
    if et.hour >= DIGEST_HOUR and state.get("last_digest") != today:
        did_digest = sp_notify.deliver("card", f"Next 24h digest {today}", digest(cur),
                                       topic_var="NTFY_CARD_TOPIC", priority="default")
        state["last_digest"] = today
    state.update({"games": cur, "t90": cur_t90, "updated": c.iso(now_utc)})
    sp.parent.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(sp)
    counts = {k: sum(1 for d in ds if d["cls"] == k) for k in CLASSES}
    rec = {"kind": "window_page", "exit": 0, "games": len(cur), "first_run": first_run,
           "deltas": counts, "quiet_hours": quiet, "suppressed": suppressed,
           "paged": paged, "digest": did_digest,
           "freshen_needed": [{"id": d["id"], "sport": d["g"]["sport"],
                               "competition": d["g"]["competition"], "reason": d["cls"]}
                              for d in ds if d["cls"] in FRESHEN_CLASSES]}
    c.append_receipt(rec)
    return rec


def main(argv=None) -> int:
    c.load_host_env()
    argv = sys.argv[1:] if argv is None else argv
    card = Path(argv[0]) if argv else c.REPO / "exports" / "window_24h.json"
    return run(card).get("exit", 1)


if __name__ == "__main__":
    sys.exit(main())
