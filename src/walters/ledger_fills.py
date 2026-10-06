"""Read the Cockpit's trading ledger export (bd_ledger_v1_*.json) — READ-ONLY.

The ledger lives in the Cockpit's browser storage; its "Export ledger (JSON)"
file is the only copy the repo can read. The export stores raw Kalshi fills but
NOT their classification (book / call_id), which the Cockpit recomputes on every
load. This is a line-for-line port of that classification and of the executed-
position CLV, so the K-track receipt (#87) reads the same numbers the Cockpit
shows. Sources (tools/cockpit.html): normTeam L974, dayDiff L1003, isShadow
L1036, heldContractFair L1075, executedPositions L1287, FAMILY_SPORTS L1552,
parseTicker L1595, titleTeams/titleParse/codeFits/tickerRole/resolveSide
L1611-1673, codesFit/sameTeam/gameFits/backedIn L1674-1693, matchFill L1694,
sideFields L1744, classifyFills L1809, FEE_M_BY_FAMILY/feeLegClass L1829.
The Cockpit's in-memory desk picks (deskPicks) are not in the export, so the
"system-pick, unlogged" book can read short here; system_matched never depends
on them.
"""
from __future__ import annotations

import re
import unicodedata

FAMILY_SPORTS = {"MLB": ["MLB"], "NFL": ["NFL"], "NCAAF": ["NCAA"], "NHL": ["NHL"],
                 "EPL": ["SOCCER", "PL"], "UCL": ["CL", "SOCCER"], "FACUP": ["FAC", "SOCCER"],
                 "UEFANL": ["UNL"]}
MONTHS = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}
FUN_SPORTS = {"NHL", "UNL"}
THREE_WAY_FAMILIES = {"EPL", "UCL", "FACUP", "UEFANL"}     # soccer 1X2: HOME / TIE / AWAY
FEE_M_BY_FAMILY = {"NFL": (1, 1), "NHL": (1, 1), "NCAAF": (1, 1), "EPL": (1, 1), "UCL": (1, 1),
                   "MLB": (0.5, 0.5)}
_STOP = {"fc", "afc", "cf", "sc", "the", "club"}


def norm_team(s) -> str:
    t = unicodedata.normalize("NFD", str(s or ""))
    t = "".join(ch for ch in t if not ("̀" <= ch <= "ͯ")).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t.replace("&", " and "))
    return " ".join(w for w in re.split(r"\s+", t) if w and w not in _STOP)


def day_diff(a: str | None, b: str | None) -> float:
    if not a or not b:
        return float("inf")
    from datetime import date
    try:
        da, db = date(int(a[0:4]), int(a[5:7]), int(a[8:10])), date(int(b[0:4]), int(b[5:7]), int(b[8:10]))
    except ValueError:
        return float("inf")
    return abs((da - db).days)


def is_shadow(c: dict) -> bool:
    return c.get("call_type") in ("quarantine_shadow", "value_shadow")


def parse_ticker(t) -> dict:
    t = str(t or "").strip().upper()
    if t.startswith("KXMVE"):
        return {"kind": "parlay", "family": t.split("-")[0], "category": "kalshi-native parlay (MVE combo)"}
    m = re.match(r"^KX([A-Z]+?)GAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})?([A-Z0-9]+)-([A-Z0-9]+)$", t)
    if not m or m.group(1) not in FAMILY_SPORTS or m.group(3) not in MONTHS:
        return {"kind": "non_sport", "category": "non-sport / unrecognised market"}
    return {"kind": "sport", "family": m.group(1), "sports": FAMILY_SPORTS[m.group(1)],
            "date": f"20{m.group(2)}-{MONTHS[m.group(3)]:02d}-{m.group(4)}",
            "teams": m.group(6), "sideCode": m.group(7),
            "start": _et_to_utc_iso(2000 + int(m.group(2)), MONTHS[m.group(3)], int(m.group(4)), m.group(5))}


def _et_to_utc_iso(y, mo, d, hhmm):
    """The ticker's HHMM is the scheduled start in US Eastern time (KalshiAdapter.ticker_start, M13).
    Naive UTC ISO to the second, like the Cockpit's etToUtcIso; None without a time."""
    if not hhmm:
        return None
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        et = datetime(y, mo, d, int(hhmm[:2]), int(hhmm[2:]), tzinfo=ZoneInfo("America/New_York"))
    except ValueError:
        return None
    return et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def title_teams(title):
    t = re.sub(r"winner\??", "", str(title or ""), flags=re.I).strip()
    for sep in (" vs ", " vs. ", " v ", " at ", " @ "):
        i = t.lower().find(sep)
        if i > 0:
            return [t[:i].strip(), t[i + len(sep):].strip()]
    return None


def title_parse(title):
    t = str(title or "").strip()
    parts = re.split(r"\s+[—–-]\s+", t)
    if len(parts) >= 2:
        m = re.match(r"^(.*?)\s+wins?\b", parts[0], flags=re.I)
        rest = " - ".join(parts[1:]).strip()
        pair = title_teams(rest)
        if m:
            backed = m.group(1).strip()
            if re.match(r"^(tie|draw)$", backed, flags=re.I):
                return {"backed": "Draw", "teams": pair}
            return {"backed": backed, "teams": pair or [backed, rest]}
    pair = title_teams(t)
    return {"backed": None, "teams": pair} if pair else None


def code_fits(code: str, name) -> int:
    w = [x for x in norm_team(name).split(" ") if x]
    if not w:
        return 0
    ini = "".join(x[0] for x in w)
    c = code.lower()
    if ini == c:
        return 3
    if "".join(w).startswith(c) or w[0].startswith(c):
        return 2
    if len(c) >= 2 and ini.startswith(c[:2]):
        return 1
    return 0


def ticker_role(p: dict) -> dict:
    T, S = p.get("teams") or "", p.get("sideCode") or ""
    if S == "TIE":
        return {"role": "DRAW", "codes": None}
    if not S or len(T) <= len(S):
        return {"role": None, "codes": None}
    e, b = T.endswith(S), T.startswith(S)
    if e and not b:
        return {"role": "HOME", "codes": {"away": T[:-len(S)], "home": S}}
    if b and not e:
        return {"role": "AWAY", "codes": {"away": S, "home": T[len(S):]}}
    return {"role": None, "codes": None}


def _tok_overlap(a, b) -> int:
    A = set(x for x in norm_team(a).split(" ") if x)
    return sum(1 for x in norm_team(b).split(" ") if x and x in A)


def same_team(a, b) -> bool:
    if not a or not b:
        return False
    if a == "Draw" or b == "Draw":
        return a == b
    return _tok_overlap(a, b) > 0


def resolve_side(p: dict, title, side) -> dict:
    tr, tp = ticker_role(p), title_parse(title)
    no = str(side or "yes").lower().startswith("n")
    r = {"role": tr["role"], "codes": tr["codes"], "teams": tp["teams"] if tp else None, "backed": None,
         "via": "ticker" if tr["role"] else None, "why": None}
    if tr["role"] == "DRAW":
        r["backed"] = "Draw"
    elif tr["role"] and r["teams"]:
        s = [code_fits(p.get("sideCode") or "", n) for n in r["teams"]]
        if s[0] != s[1] and max(s) > 0:
            r["backed"] = r["teams"][0] if s[0] > s[1] else r["teams"][1]
    if not tr["role"] and tp and tp["backed"]:
        r["backed"], r["via"] = tp["backed"], "title"
    if not tr["role"] and not r["backed"] and r["teams"] and p.get("sideCode"):
        s = [code_fits(p["sideCode"], n) for n in r["teams"]]
        if s[0] != s[1] and max(s) > 0:
            r["backed"], r["via"] = (r["teams"][0] if s[0] > s[1] else r["teams"][1]), "title"
    if not r["role"] and not r["backed"]:
        r["why"] = f"side {p.get('sideCode') or '?'} not resolvable from the ticker or the title"
        return r
    if no:
        if r["role"] == "DRAW" or r["backed"] == "Draw":
            return {**r, "role": None, "backed": None, "why": "NO on the tie leg (not a single outcome)"}
        # THREE-WAY NO = COMPOSITE (ARCHITECT 2026-10-06): two outcomes, never a single-side straight;
        # the held contract stays known for its closing fair
        if p.get("family") in THREE_WAY_FAMILIES and r["role"] in ("HOME", "AWAY"):
            return {**r, "role": None, "backed": None, "noOn": r["backed"] or r["role"], "noRole": r["role"],
                    "composite": True,
                    "why": f"NO on {r['backed'] or r['role']} in a three-way market (composite: two outcomes)"}
        flip = {"HOME": "AWAY", "AWAY": "HOME"}.get(r["role"])
        other = None
        if r["backed"] and r["teams"]:
            other = r["teams"][1] if same_team(r["backed"], r["teams"][0]) else r["teams"][0]
        return {**r, "role": flip, "backed": other, "noOn": r["backed"] or r["role"], "noRole": r["role"],
                "why": "NO on " + str(r["backed"] or r["role"])}
    return r


def side_fields(p: dict, title, side) -> dict:
    r = resolve_side(p, title, side)
    return {"backed": r["backed"], "backed_role": r["role"], "teams_title": r["teams"] or None,
            "resolve_note": r["why"], "resolved_via": r["via"],
            "no_on": r.get("noOn"), "no_on_role": r.get("noRole"), "composite": bool(r.get("composite"))}


def _codes_fit(T: str, c: dict) -> bool:
    for i in range(2, min(4, len(T) - 2) + 1):
        if code_fits(T[:i], c.get("away")) > 0 and code_fits(T[i:], c.get("home")) > 0:
            return True
    return False


def game_fits(fx: dict, g: dict) -> bool:
    """gameFits: the ticker's team codes decide when present (a one-word title overlap such as "United" is
    not team identity, Codex on #299); the title is used only when the ticker carries no codes."""
    if fx.get("teams"):
        return _codes_fit(fx["teams"], g)
    tt = fx.get("teams_title")
    return bool(tt) and all(same_team(t, g.get("home")) or same_team(t, g.get("away")) for t in tt)


def _backed_in(fx: dict, g: dict):
    return {"HOME": g.get("home"), "AWAY": g.get("away"), "DRAW": "Draw"}.get(fx.get("backed_role"), fx.get("backed"))


def _start_nearest(fx: dict, cands: list) -> list:
    """startNearest: with the ticker's start time, candidates within 3h of it, nearest first; otherwise
    (no time, or none within 3h) the candidates unchanged."""
    from datetime import datetime, timezone
    if not fx.get("start"):
        return cands
    t0 = datetime.fromisoformat(fx["start"]).replace(tzinfo=timezone.utc)

    def dist(c):
        k = c.get("kickoff")
        if not k:
            return float("inf")
        try:
            kt = datetime.fromisoformat(k[:-1] + "+00:00" if k.endswith(("Z", "z")) else k)
        except ValueError:
            return float("inf")
        kt = kt.replace(tzinfo=timezone.utc) if kt.tzinfo is None else kt
        return abs((kt - t0).total_seconds())
    within = [c for c in cands if dist(c) <= 3 * 3600]
    return sorted(within, key=dist) if within else cands


def match_fill(fx: dict, calls: list, picks: list) -> dict:
    if fx.get("kind") != "sport":
        return {"book": "fun", "category": fx.get("category")}

    def near(g):
        d = (g.get("kickoff") or g.get("log_date") or g.get("date") or "")[:10]
        return g.get("sport") in fx["sports"] and day_diff(d, fx["date"]) <= 1
    cands = [c for c in calls if c.get("call_type") != "parlay_leg" and near(c) and game_fits(fx, c)]
    if not cands and any(x in FUN_SPORTS for x in fx["sports"]):
        x = next(x for x in fx["sports"] if x in FUN_SPORTS)
        return {"book": "fun", "category": f"{x} single (market-only, no system call)"}
    if fx.get("composite"):
        return {"book": "off_book_sports",
                "category": f"composite contract ({fx.get('resolve_note') or 'three-way NO'}) — never a straight",
                "plausible": True}
    if not fx.get("backed") and not fx.get("backed_role"):
        return {"book": "off_book_sports", "category": f"side not resolvable ({fx.get('resolve_note') or '?'})",
                "plausible": True}

    def pick_name(c):
        return c.get("home") if c.get("pick") == "HOME" else c.get("away") if c.get("pick") == "AWAY" else "Draw"
    if not cands:
        ps = [g for g in (picks or []) if near(g) and game_fits(fx, g)]
        if not ps:
            return {"book": "off_book_sports", "category": "no logged call for this game"}
        agree = [g for g in ps if same_team(_backed_in(fx, g), pick_name(g))]
        if agree:
            return {"book": "system_pick_unlogged", "category": f"system-pick, unlogged ({agree[0].get('source')})"}
        return {"book": "off_book_sports", "category": "stored prediction exists but the side disagrees",
                "plausible": True}
    agree = [c for c in _start_nearest(fx, cands) if same_team(_backed_in(fx, c), pick_name(c))]
    real = [c for c in agree if c.get("call_type") != "quarantine_shadow" and (c.get("units") or 0) > 0]
    if real:
        c = real[0]
        out = {"book": "system_matched", "category": f"{c.get('engine')} · {c.get('tier')}",
               "engine": c.get("engine"), "tier": c.get("tier"), "call_id": c.get("id")}
        # PARITY: the Cockpit takes the first agreeing call, so the receipt does too (its numbers must
        # match the Cockpit's). When MORE THAN ONE real call fits (e.g. an MLB doubleheader, same teams
        # and day), the attribution is ambiguous: flagged and listed, never silent (Codex on #297).
        if len(real) > 1:
            out["ambiguous_calls"] = [x.get("id") for x in real]
        return out
    if agree:
        return {"book": "off_book_sports", "category": "matches a quarantine SHADOW (off-policy play)",
                "plausible": True}
    return {"book": "off_book_sports", "category": "logged call exists but the side disagrees", "plausible": True}


def fee_leg_class(fee, price, qty, fam, combo):
    if fee is None or price is None or not qty or price <= 0 or price >= 1:
        return None
    pq = qty * price * (1 - price)
    if combo:
        mt, mm = 1, None
    else:
        m = FEE_M_BY_FAMILY.get(fam)
        if not m:
            return None
        mt, mm = m
    taker = 0.07 * mt * pq
    maker = taker * 0.5 if combo else 0.0175 * mm * pq

    def near(v):
        return abs(fee - v) <= 0.01 + 1e-9
    t, mk = near(taker), near(maker)
    if t and mk:
        return "ambiguous"
    if t:
        return "taker"
    if mk:
        return "maker"
    if fam == "MLB" and not combo and near(0.07 * pq):
        return "taker_live"
    return "unknown"


def classify_fills(L: dict) -> list[dict]:
    """classifyFills: every fill re-derived (ticker + side) and booked; parlays are 'fun'."""
    calls, picks = L.get("calls") or [], L.get("system_picks") or []
    out = []
    for f in L.get("fills") or []:
        fx = {**f, **parse_ticker(f.get("ticker"))}
        if fx["kind"] == "sport":
            fx.update(side_fields(fx, fx.get("title"), fx.get("side")))
            # three-way NO resolves as COMPOSITE in resolve_side (fill matcher lane, ARCHITECT 2026-10-06)
            fx["composite_no"] = bool(fx.get("composite"))
        cls = {"book": "fun", "category": fx.get("category")} if fx["kind"] == "parlay" else \
            match_fill(fx, calls, picks)
        combo = fx["kind"] == "parlay"
        fam = None if combo else fx.get("family")
        out.append({**fx, **cls,
                    "fee_class_open": fee_leg_class(fx.get("open_fee"), fx.get("entry"), fx.get("qty"), fam, combo),
                    "fee_class_close": (fee_leg_class(fx.get("close_fee"), fx.get("exit"), fx.get("qty"), fam, combo)
                                        if (fx.get("close_fee") or 0) > 0 else None)})
    return out


def held_contract_fair(f: dict, c: dict, fair: dict):
    def role_of(n):
        if n is None:
            return None
        if n in ("HOME", "AWAY", "DRAW"):
            return n
        if n == "Draw":
            return "DRAW"
        return "HOME" if same_team(n, c.get("home")) else "AWAY" if same_team(n, c.get("away")) else None
    if f.get("no_on_role") or f.get("no_on"):
        r = f.get("no_on_role") or role_of(f.get("no_on"))
        return 1 - fair[r] if r and fair.get(r) is not None else None
    r = f.get("backed_role") or role_of(f.get("backed"))
    return fair[r] if r and fair.get(r) is not None else None


def executed_positions(L: dict, fills: list[dict] | None = None) -> dict:
    """executedPositions: per graded, non-shadow, non-parlay call with a close, qty-weighted over its
    system_matched fills: clv = close fair of the held contract − entry; fee_adj = clv − open fee/contract."""
    graded = {c.get("id"): c for c in (L.get("calls") or [])
              if c.get("status") == "graded" and c.get("close_ref") and not is_shadow(c)
              and c.get("call_type") != "parlay_leg"}
    by: dict = {}
    unpriced = set()
    for f in (fills if fills is not None else classify_fills(L)):
        if f.get("book") != "system_matched" or not f.get("call_id") or not (f.get("qty") or 0) > 0 \
                or f.get("entry") is None:
            continue
        c = graded.get(f["call_id"])
        if c is None:
            continue
        qf = held_contract_fair(f, c, (c["close_ref"] or {}).get("fair") or {})
        if qf is None:
            unpriced.add(c["id"])
            continue
        has_open = isinstance(f.get("open_fee"), (int, float)) and not isinstance(f.get("open_fee"), bool)
        a = by.setdefault(c["id"], {"c": c, "qty": 0, "clv": 0.0, "fee": 0.0, "feeOk": True, "combined": False,
                                    "fills": []})
        a["qty"] += f["qty"]
        a["clv"] += f["qty"] * (qf - f["entry"])
        a["fills"].append(f)
        if has_open:
            a["fee"] += f["open_fee"]
        else:
            a["feeOk"] = False
            if f.get("fees"):
                a["combined"] = True
    pos = [{"c": a["c"], "day": a["c"].get("graded_date") or a["c"].get("log_date"), "qty": a["qty"],
            "clv": a["clv"] / a["qty"], "fee_adj": (a["clv"] - a["fee"]) / a["qty"] if a["feeOk"] else None,
            "fee_status": "open_fee" if a["feeOk"] else "combined_only" if a["combined"] else "missing",
            "fills": a["fills"]} for a in by.values()]
    ids = [i for i in unpriced if i not in by]
    return {"pos": pos, "unpriced": len(ids), "unpriced_ids": ids}
