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
    model        model updated: the canonical pick, its probability (to 0.1%)
                 or the model version changed (card page, 2026-10-01)
    call         call changed: the Desk's call or units in the file changed
                 (F1 desk on the export; 2026-10-01)
    qb_news      an injured QB's status changed (#192, ruling 2026-10-01): ONE
                 news item PER PLAYER, listing every game that team plays in the
                 window; never one page per game
PAGE CONTENT (architect 2026-10-01, F2 slice 1): every page line and digest
row reads "competition · away @ home · kickoff ET · model pick prob (tier) ·
reference (books, or Kalshi when kalshi-only) · edge · Desk call/units when the
file carries desk · flags"; market-only rows say so. A delta adds one "↳" line
with the change. Lines stay near 100 characters for the phone. The digest lists
the Desk's calls first.
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
CLASSES = ("new_priced", "tier", "quarantine", "stale", "kickoff", "t90_news", "line_move", "model", "call",
           "qb_news")
FRESHEN_CLASSES = ("t90_news", "line_move")
URGENT = ("quarantine", "line_move")


def state_path() -> Path:
    return Path(c.setting("SP_WINDOW_STATE") or c.receipts_path().with_name("window_state.json"))


def snapshot(card: dict) -> dict:
    out = {}
    for r in card.get("fixtures", []):
        model = r.get("model") or {}
        desk = model.get("desk") or {}
        fair = (r.get("market") or {}).get("fair_prob") or {}
        pick = model.get("top_pick")
        kal_only = desk.get("reference") == "kalshi_only"
        out[str(r["match_id"])] = {
            "label": f"{r.get('away_team')} @ {r.get('home_team')}",
            "home": r.get("home_short") or r.get("home_team"), "away": r.get("away_short") or r.get("away_team"),
            "sport": r.get("sport"), "competition": r.get("competition"),
            "utc_date": r.get("utc_date"), "status": r.get("status"),
            "priced": bool(r.get("market") or r.get("kalshi")),
            "tier": r.get("tier"), "quarantine": bool(r.get("quarantine")),
            "venue_flag": r.get("venue_flag"), "edge_pp": r.get("edge_pp"),
            "engine": r.get("engine"),
            "late_news": r.get("late_news_flag"), "line_move": _move_text(r.get("line_move")),
            "time_flag": r.get("time_flag"),
            # card page (2026-10-01)
            "pick": pick, "prob": model.get("top_pick_prob"), "model_version": model.get("model_version"),
            "ref_src": "kalshi" if kal_only else "books",
            # with a Desk call, the reference the call was made on; else the card's repriced books
            "ref_p": desk.get("market_ref") if desk else (fair.get(pick) if pick else None),
            "desk_edge": desk.get("edge_pp") if desk else None,
            "call": desk.get("call"), "units": desk.get("units"), "pass_kind": desk.get("pass_kind"),
            "fair": fair or None, "kalshi_home": r.get("kalshi_home_norm"),
            "qbs": {f"{q.get('team_id')}|{q.get('player')}": {"team": q.get("team"), "player": q.get("player"),
                                                              "status": q.get("status") or ""}
                    for q in (r.get("qb_news") or [])}}
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
        if "prob" in p and (g.get("pick") != p.get("pick") or g.get("model_version") != p.get("model_version")
                            or _r3(g.get("prob")) != _r3(p.get("prob"))) and g.get("prob") is not None:
            out.append({"cls": "model", "id": mid, "g": g, "was": p})
        if "call" in p and (g.get("call"), g.get("units")) != (p.get("call"), p.get("units")) and g.get("call"):
            out.append({"cls": "call", "id": mid, "g": g, "was": p})
        if g["utc_date"] != p["utc_date"] or (
                g["status"] != p["status"] and str(g["status"]).lower() in ("postponed", "cancelled")):
            out.append({"cls": "kickoff", "id": mid, "g": g, "was": p["utc_date"]})
    out += qb_deltas(prev, cur)
    for mid, sig in cur_t90.items():
        if mid in prev_t90 and prev_t90[mid] != sig and mid in cur:
            out.append({"cls": "t90_news", "id": mid, "g": cur[mid]})
    return out


def _players(games: dict) -> dict:
    """player key -> {team, player, status, ids: {match ids}, games: [snapshots]} across the window."""
    out = {}
    for mid, g in games.items():
        for k, q in (g.get("qbs") or {}).items():
            e = out.setdefault(k, {**q, "ids": set(), "games": []})
            e["ids"].add(mid)
            e["games"].append(g)
    return out


def qb_deltas(prev: dict, cur: dict) -> list[dict]:
    """#192: one delta per PLAYER whose QB injury status appeared, changed or
    cleared, however many games his team has in the window. A change is news
    only on a game that was already on the card (a game entering or leaving
    the window is not news). Silent until the previous state carries QB data
    (no flood on the upgrade)."""
    if not any("qbs" in g for g in prev.values()):
        return []
    was, now = _players(prev), _players(cur)
    out = []
    for k in sorted(set(was) | set(now)):
        a, b = was.get(k), now.get(k)
        if a and b and a["status"] == b["status"]:
            continue
        stayed = [mid for mid in (b or a)["ids"] if mid in prev and mid in cur]
        if not stayed:
            continue
        q = b or a
        out.append({"cls": "qb_news", "id": k, "g": cur[stayed[0]], "player": q["player"], "team": q["team"],
                    "was": a["status"] if a else None, "now": b["status"] if b else None,
                    "games": [cur[mid] for mid in sorted(stayed)]})
    return out


def _r3(v):
    return None if v is None else round(v, 3)


def _ko(g) -> str:
    """'Thu 8:15p' on the ET clock."""
    try:
        t = datetime.fromisoformat(g["utc_date"]).replace(tzinfo=ZoneInfo("UTC")).astimezone(ET)
    except (TypeError, ValueError):
        return "?"
    return f"{t:%a} {t.hour % 12 or 12}:{t:%M}{'a' if t.hour < 12 else 'p'}"


def _side(g, k) -> str:
    return g.get("home") if k == "HOME" else g.get("away") if k == "AWAY" else "Draw" if k == "DRAW" else "?"


def _call_text(g) -> str | None:
    if not g.get("call"):
        return None
    if g["call"] == "PASS":
        return "PASS" + {"noref": " no-ref", "floor": " floor"}.get(g.get("pass_kind") or "", "")
    u = g.get("units")
    return f"{g['call']} {u:g}u" if isinstance(u, (int, float)) else g["call"]


def _market_text(g) -> str:
    fair = g.get("fair") or {}
    if fair:
        k = max(fair, key=lambda x: fair[x] if fair[x] is not None else -1)
        if fair[k] is not None:
            return f"books {_side(g, k)} {fair[k] * 100:.0f}%"
    kh = g.get("kalshi_home")
    if kh is not None:
        return f"kalshi {g.get('home')} {kh * 100:.0f}%" if kh >= 0.5 else f"kalshi {g.get('away')} {(1 - kh) * 100:.0f}%"
    return "unpriced"


def row_text(g) -> str:
    """One card row for the phone (architect 2026-10-01): competition, teams,
    kickoff ET, model pick/prob/tier, reference, edge, Desk call, flags."""
    parts = [f"{_ko(g)} {g.get('competition') or str(g.get('sport')).upper()} {g.get('away')} @ {g.get('home')}"]
    if g.get("engine") == "model_edge" and g.get("pick"):
        prob = g.get("prob")
        parts.append(f"model {_side(g, g['pick'])} " + (f"{prob * 100:.1f}%" if prob is not None else "?")
                     + (f" ({g['tier']})" if g.get("tier") else ""))
        ref = g.get("ref_p")
        parts.append(f"{g.get('ref_src') or 'books'} " + (f"{ref * 100:.1f}%" if ref is not None else "—"))
        edge = g.get("desk_edge") if g.get("desk_edge") is not None else g.get("edge_pp")
        if edge is not None and ref is not None:
            parts.append(f"{edge:+.1f}pp")
        if (c := _call_text(g)):
            parts.append(c)
    else:
        parts += ["market-only", _market_text(g)]
    flags = [x for x in ("QUARANTINE" if g.get("quarantine") else None, g.get("venue_flag"),
                         g.get("late_news"), "⚠ time unconfirmed" if g.get("time_flag") else None) if x]
    return " · ".join(parts + flags)


def _pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "?"


def line(d: dict) -> str:
    g, was, cls = d["g"], d.get("was"), d["cls"]
    if cls == "new_priced":
        what = "newly priced"
    elif cls == "tier":
        what = f"tier {was} -> {g['tier']}"
    elif cls == "quarantine":
        what = f"QUARANTINE {'ON' if g['quarantine'] else 'off'}"
    elif cls == "stale":
        what = f"venue {was or 'ok'} -> {g['venue_flag'] or 'ok'}"
    elif cls == "kickoff":
        what = f"kickoff moved from {_ko({'utc_date': was})} (status {g['status']})"
    elif cls == "t90_news":
        what = "injury/lineup news inside T-90: freshen triggered"
    elif cls == "line_move":
        what = f"LINE MOVE inside T-3h: {g.get('line_move')}: {g.get('late_news')} freshen triggered"
    elif cls == "qb_news":
        st = lambda v: "off the list" if v is None else (v or "listed")
        head = f"QB NEWS {d['team']} {d['player']}: {st(d['was'])} -> {st(d['now'])} · {len(d['games'])} game(s)"
        return head + "".join(f"\n  ↳ {row_text(x)}" for x in d["games"])
    elif cls == "model":
        p = was or {}
        what = (f"model updated: {_side(p, p.get('pick'))} {_pct(p.get('prob'))} -> "
                f"{_side(g, g.get('pick'))} {_pct(g.get('prob'))}")
    else:                                                    # call
        what = f"call changed: {_call_text(was or {}) or 'none'} -> {_call_text(g)}"
    return f"{row_text(g)}\n  ↳ {what}"


def _is_call(g) -> bool:
    return g.get("call") in ("PLAY", "LADDER")


def digest(cur: dict) -> str:
    games = sorted(cur.values(), key=lambda g: (not _is_call(g), g["utc_date"] or ""))   # calls first
    calls = sum(1 for g in games if _is_call(g))
    lines = [f"{len(games)} games in the next 24h; "
             f"{sum(1 for g in games if g['engine'] == 'model_edge')} with a model, "
             + (f"{calls} Desk call(s), " if any(g.get("call") for g in games) else "")
             + f"{sum(1 for g in games if g['quarantine'])} quarantined, "
             f"{sum(1 for g in games if g['venue_flag'])} STALE-BOOK?"]
    for g in games[:15]:
        lines.append(row_text(g))
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
