#!/usr/bin/env python3
"""Window-card pager (architect spec 2026-09-27). It runs as the `window`
chain's post-step after a clean run, or after a run where only `sync-` steps
failed and window-card ran (ARCHITECT 2026-10-16, addendum 84 item 2(b)). It
is stdlib-only and reads the card JSON only.

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
                 window; never one page per game. A player is keyed by his
                 provider id, the name is display only (#458, addendum 112 item
                 10); an item with no provider id is keyed by team and name as
                 before and its page line says "no provider id"
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
            # addendum 37 item 3: a mismatched Kalshi block carries no price, so it never makes a row priced
            "priced": bool(r.get("market") or (r.get("kalshi") and r["kalshi"].get("status") != "mismatched")),
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
            "qbs": _qbs(r.get("qb_news"))}
    return out


def _qbs(items) -> dict:
    """One game's QB news, keyed (ARCHITECT 2026-10-17, addendum 112 item 10, #458): "key by provider player id,
    name as display only". An item with a provider id is keyed `id:<id>`. An item with none (a row stored before
    migrate_injury_player_source_id.py, or an entry the feed listed with no id) is keyed `<team_id>|<name>`, the key
    every item had before, so a state written before this change reads the same. Items that share a key (only items
    with no id can: same team, same name) are never one overwriting the other (law 4): one entry holds all their
    statuses, sorted, and counts them (`n`), so a change in any of them is a change of the entry."""
    groups: dict = {}
    for q in items or []:
        name_key = f"{q.get('team_id')}|{q.get('player')}"
        pid = q.get("player_id")
        pid = str(pid) if pid is not None and str(pid).strip() else None
        groups.setdefault(f"id:{pid}" if pid else name_key, []).append((q, name_key, pid))
    out = {}
    for k, qs in groups.items():
        q, name_key, pid = qs[0]
        sts = sorted(x.get("status") or "" for x, _, _ in qs)
        out[k] = {"team": q.get("team"), "player": q.get("player"),
                  "status": sts[0] if len(sts) == 1 else " / ".join(v or "listed" for v in sts),
                  # `last`: the last item's status in the card's order, the one status the pager kept before #458
                  "statuses": sts, "last": qs[-1][0].get("status") or "",
                  "player_id": pid, "name_key": name_key, "n": len(qs)}
    return out


def _fold(side: dict, keys: list, name_key: str) -> dict:
    """#458: id-keyed entries of one team and name, folded into one name-level entry (every status, sorted), so a
    change across the key change is one line, never silent."""
    es = [side.pop(j) for j in keys]
    sts = sorted(st for e in es for st in (e.get("statuses") or [e.get("status") or ""]))
    return {"team": es[0].get("team"), "player": es[0].get("player"),
            "status": sts[0] if len(sts) == 1 else " / ".join(v or "listed" for v in sts), "statuses": sts,
            "player_id": ",".join(str(e.get("player_id")) for e in es), "name_key": name_key, "n": len(sts),
            "ids": set().union(*(e["ids"] for e in es)), "games": [g for e in es for g in e["games"]]}


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


def _rekey(was: dict, now: dict) -> dict:
    """#458, the key change, so that a key change is never news and a change is never hidden by it. Mutates `was`
    and `now`.
    - A player keyed by name on one side (a state written before this change, or a row stored with no provider
      id) and by provider id on the other is carried to his id key when exactly one id-keyed entry of that team
      and name is on the other side and no name-keyed one.
    - Two or more id-keyed entries of that team and name against one name-keyed entry (the case #458 names): the
      players cannot be told apart across the change. If their statuses are the name entry's (the same statuses,
      sorted; for a state written before this change, which kept one status, that status among theirs), it is a
      baseline: no delta this run, listed in the receipt's `qb_rekey`, and from the next run each is compared by
      his own id. Otherwise the ids are folded into one name-level entry and the change pages as one line.
    - A state written before this change (no `n`: one status, the last item's) against an entry that now holds two
      or more id-less items under the same key is a baseline when its status is the new entry's last item's: the
      exact case the pager before this change was silent on too. Otherwise it pages."""
    carried, baseline, skip = [], [], set()
    for a, b in ((was, now), (now, was)):
        ids_by_name: dict = {}
        for k, e in b.items():
            if k.startswith("id:"):
                ids_by_name.setdefault(e.get("name_key"), []).append(k)
        for k in [k for k in a if not k.startswith("id:")]:
            # the old state's one entry (no `n`) against a merged id-less entry: a baseline only where the pager
            # before this change was silent too (its status is the new last item's). Only (was, now) can match:
            # this code always writes `n`.
            if (k in b and "n" not in a[k] and (b[k].get("n") or 1) > 1
                    and (a[k].get("status") or "") == (b[k].get("last") or "")):
                skip.add(k)
                baseline.append(k)
                continue
            js = ids_by_name.get(k) or []
            if not js or k in b:
                continue
            if len(js) > 1:
                theirs = sorted((b[j].get("status") or "") for j in js)
                mine = a[k]
                same = (sorted(mine.get("statuses") or []) == theirs if "n" in mine
                        else (mine.get("status") or "") in theirs)
                if same:
                    skip.update([k, *js])
                    baseline.append(k)
                else:
                    b[k] = _fold(b, js, k)
            elif js[0] not in a:
                a[js[0]] = {**a.pop(k), "name_key": k}
                carried.append(k)
    return {"carried": carried, "baseline": baseline, "skip": skip}


def qb_rekey(prev: dict, cur: dict) -> dict:
    """The receipt of the key change (#458): how many players were carried from a name key to their provider id,
    and the names held as a baseline (see _rekey)."""
    if not any("qbs" in g for g in prev.values()):
        return {"carried": 0, "baseline": []}
    rk = _rekey(_players(prev), _players(cur))
    return {"carried": len(rk["carried"]), "baseline": sorted(rk["baseline"])}


def qb_deltas(prev: dict, cur: dict) -> list[dict]:
    """#192: one delta per PLAYER whose QB injury status appeared, changed or
    cleared, however many games his team has in the window. A change is news
    only on a game that was already on the card (a game entering or leaving
    the window is not news). Silent until the previous state carries QB data
    (no flood on the upgrade). #458: a player is his provider id (_qbs), and a
    change of key is not news (_rekey)."""
    if not any("qbs" in g for g in prev.values()):
        return []
    was, now = _players(prev), _players(cur)
    skip = _rekey(was, now)["skip"]
    out = []
    for k in sorted(set(was) | set(now)):
        if k in skip:
            continue
        a, b = was.get(k), now.get(k)
        if a and b and a["status"] == b["status"]:
            continue
        stayed = [mid for mid in (b or a)["ids"] if mid in prev and mid in cur]
        if not stayed:
            continue
        q = b or a
        out.append({"cls": "qb_news", "id": k, "g": cur[stayed[0]], "player": q["player"], "team": q["team"],
                    "by_name": not q.get("player_id"), "n": q.get("n") or 1,
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
        # #458: the name is display only; an item keyed by name says so (law 4: labelled), and so does one that
        # holds more than one entry
        tags = (["no provider id"] if d.get("by_name") else []) + ([f"{d['n']} entries"] if d.get("n", 1) > 1 else [])
        who = f"{d['team']} {d['player']}" + (f" ({', '.join(tags)})" if tags else "")
        head = f"QB NEWS {who}: {st(d['was'])} -> {st(d['now'])} · {len(d['games'])} game(s)"
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
    rekey = {"carried": 0, "baseline": []} if first_run else qb_rekey(state.get("games", {}), cur)   # #458
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
           "qb_rekey": rekey,
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
