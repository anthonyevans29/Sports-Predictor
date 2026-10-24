"""Read the Cockpit's trading ledger export (bd_ledger_v1_*.json) — READ-ONLY.

The ledger lives in the Cockpit's browser storage; its "Export ledger (JSON)"
file is the only copy the repo can read. The export stores raw Kalshi fills but
NOT their classification (book / call_id), which the Cockpit recomputes on every
load. This is a line-for-line port of that classification and of the executed-
position CLV, so the K-track receipt (#87) reads the same numbers the Cockpit
shows. Sources (tools/cockpit.html): normTeam L974, dayDiff L1003, isShadow
L1036, heldContractFair L1075, executedPositions L1287, FAMILY_SPORTS L1552,
parseTicker L1595, titleTeams/titleParse/codeFits/tickerRole/resolveSide
L1611-1673, codesFit/sameTeam/gameFits L1674-1693, matchFill L1694,
sideFields L1744, classifyFills L1809, FEE_M_BY_FAMILY/feeLegClass L1829;
#431 R16/R17's closingPositions with sameGame/closingIndex/coverOf, by name
(closing_positions; ARCHITECT 2026-10-20, addendum 146 item 1(iv), addendum
148 item 1). The Cockpit's in-memory desk picks (deskPicks) are not in the export, so the
"system-pick, unlogged" book can read short here; system_matched never depends
on them.
"""
from __future__ import annotations

import re
import unicodedata

FAMILY_SPORTS = {"MLB": ["MLB"], "NFL": ["NFL"], "NCAAF": ["NCAA"], "NHL": ["NHL"],
                 "EPL": ["SOCCER", "PL"], "UCL": ["CL", "SOCCER"], "FACUP": ["FAC", "SOCCER"],
                 "UEFANL": ["UNL", "INTL"]}   # INTL: the production intl calls (Codex on #325)
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


def not_executed_closing(c: dict) -> str:
    """The closing that marked a call not executed (#431, ARCHITECT 2026-10-20, addendum 145 item 3(b) R13), as the
    receipts print it: "closing <family> <start>: <the page's words>". The mark is the Cockpit's contract
    {flag, closing: {family, start, run_id, as_of, file}, closing_call: {text, calls}}; a key it lacks reads "?",
    and a mark of another shape reads the same way, never a crash."""
    m = c.get("not_executed")
    m = m if isinstance(m, dict) else {}
    cl = m["closing"] if isinstance(m.get("closing"), dict) else {}
    cc = m["closing_call"] if isinstance(m.get("closing_call"), dict) else {}
    return f"closing {cl.get('family') or '?'} {cl.get('start') or '?'}: {cc.get('text') or '?'}"


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
            # NO on the TIE of a three-way market is HOME-or-AWAY: composite too (Codex on #299)
            if p.get("family") in THREE_WAY_FAMILIES:
                return {**r, "role": None, "backed": None, "noOn": "Draw", "noRole": "DRAW", "composite": True,
                        "why": "NO on the draw in a three-way market (composite: two outcomes)"}
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


def _tok_prefix_subset(a, b) -> bool:
    """Every word of a is a prefix of some word of b."""
    A = [w for w in norm_team(a).split(" ") if w]
    B = [w for w in norm_team(b).split(" ") if w]
    return bool(A) and bool(B) and all(any(x.startswith(w) for x in B) for w in A)


def _title_by_side(fx: dict):
    """The title's teams BOUND TO SIDES (Codex on #299): "X wins — Y" puts X on the contract's (ticker) side and Y
    on the other; the legacy "A vs B Winner?" grammar is AWAY vs HOME (BUFKC = "Buffalo vs Kansas City")."""
    tp = title_parse(fx.get("title"))
    if not tp or not tp.get("teams") or len(tp["teams"]) != 2:
        return None
    role = fx.get("no_on_role") or fx.get("backed_role")
    if tp.get("backed") and tp["backed"] != "Draw":
        if role not in ("HOME", "AWAY"):
            return None
        other = tp["teams"][1] if tp["teams"][0] == tp["backed"] else tp["teams"][0]
        return {"home": tp["backed"], "away": other} if role == "HOME" else {"away": tp["backed"], "home": other}
    if not tp.get("backed"):
        return {"away": tp["teams"][0], "home": tp["teams"][1]}
    return None


def _codes_fit(T: str, c: dict, tt=None, by_side=None) -> bool:
    """Both codes fit. A WEAK fit (two-letter initials only) is a same-city collision unless a title team
    confirms that side word by word: NYG ~ "New York Jets" is rejected by "New York G", while KC ~ "Kansas City"
    and MCI ~ "Man City" are confirmed (Codex post-merge on #297 and on #299)."""
    def ini(n):
        return "".join(w[0] for w in norm_team(n).split(" ") if w)

    def ok(sc, code, name, side):
        # the WHOLE code prefixing the initials (KC ~ "kcc", SF ~ "sf4") is identity; a weak fit (NYG ~ "nyj") is
        # confirmed only by the title team on the SAME side, never by the opposite team (Codex on #299)
        return sc >= 2 or (sc == 1 and (ini(name).startswith(code.lower())
                                        or (bool(by_side) and bool(by_side.get(side))
                                            and _tok_prefix_subset(by_side[side], name))))
    for i in range(2, min(4, len(T) - 2) + 1):
        a, h = code_fits(T[:i], c.get("away")), code_fits(T[i:], c.get("home"))
        if ok(a, T[:i], c.get("away"), "away") and ok(h, T[i:], c.get("home"), "home"):
            return True
    return False


def _tok_subset(a, b) -> bool:
    A = [w for w in norm_team(a).split(" ") if w]
    B = [w for w in norm_team(b).split(" ") if w]
    if not A or not B:
        return False
    x, y = (A, set(B)) if len(A) <= len(B) else (B, set(A))
    return all(w in y for w in x)


def _title_fits_strict(tt, g: dict) -> bool:
    """Two title teams on two DIFFERENT sides, each a whole-word subset of its side's name."""
    if not tt or len(tt) != 2:
        return False
    return ((_tok_subset(tt[0], g.get("home")) and _tok_subset(tt[1], g.get("away")))
            or (_tok_subset(tt[0], g.get("away")) and _tok_subset(tt[1], g.get("home"))))


def _contract_oriented(fx: dict, g: dict) -> bool:
    """The unordered title fallback must hold the CONTRACT's team (the title's "X wins" team, else the
    code-resolved name) on the ticker's side of THIS call: a reversed home/away call never fits (Codex on #299).
    A tie contract has no side; an unknown name cannot be oriented, so it does not fit."""
    role = fx.get("no_on_role") or fx.get("backed_role")
    if role not in ("HOME", "AWAY"):
        return True
    tp = title_parse(fx.get("title"))
    name = tp["backed"] if tp and tp.get("backed") and tp["backed"] != "Draw" else (
        fx.get("no_on") if fx.get("no_on_role") else fx.get("backed"))
    if name and name not in ("HOME", "AWAY") and _tok_subset(name, g.get("home") if role == "HOME" else g.get("away")):
        return True
    # a legacy "A vs B" title is AWAY vs HOME: both teams on their own sides orients it (two non-prefix codes too)
    bs = _title_by_side(fx)
    if (bs and not (tp or {}).get("backed") and _tok_subset(bs["away"], g.get("away"))
            and _tok_subset(bs["home"], g.get("home"))):
        return True
    # no usable name (legacy "A vs B Winner?" titles): the OTHER code fits the call's opposite side strongly
    codes = ticker_role(fx)["codes"]
    opp = "away" if role == "HOME" else "home"
    return bool(codes) and code_fits(codes[opp], g.get(opp)) >= 2


def game_fits(fx: dict, g: dict) -> bool:
    """gameFits: with ticker codes, the codes fit OR a strict two-team title fit (one shared word such as
    "United" is never identity; a standard non-prefix code such as JAX or BHA still matches through the
    title, Codex on #299). Tickers without codes keep the original title rule."""
    if fx.get("teams"):
        return _codes_fit(fx["teams"], g, fx.get("teams_title"), _title_by_side(fx)) or (_title_fits_strict(fx.get("teams_title"), g)
                                              and _contract_oriented(fx, g))
    tt = fx.get("teams_title")
    if tt and len(tt) == 2:          # one-to-one: two DIFFERENT sides (Codex post-merge on #297)
        return ((same_team(tt[0], g.get("home")) and same_team(tt[1], g.get("away")))
                or (same_team(tt[0], g.get("away")) and same_team(tt[1], g.get("home"))))
    return bool(tt) and all(same_team(t, g.get("home")) or same_team(t, g.get("away")) for t in tt)


def _start_nearest(fx: dict, cands: list) -> list:
    """startNearest: with the ticker's start time, the candidates of the NEAREST start within 3h (ties kept);
    otherwise (no time, or none within 3h) the candidates unchanged."""
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
    if not within:
        return cands
    # Codex on #299: resolve the GAME first (nearest start; ties stay together and are flagged ambiguous),
    # then test the pick, so a disagreeing exact-time game never hands the fill to a later one
    m = min(dist(c) for c in within)
    return [c for c in within if dist(c) == m]


# The Cockpit's REDATED_DRIFT_MS (tools/cockpit.html; desk_policy.DESK_CLOCK_DRIFT, 1 h, inclusive) in seconds: R2's
# one game (ARCHITECT 2026-10-20, addendum 145 item 3(b)), read by _unmarked_first
REDATED_DRIFT_S = 3600


def _kickoff_ts(c: dict):
    """A call's kickoff as epoch seconds (UTC when it names no zone), as _start_nearest reads it; None when absent or
    unreadable."""
    from datetime import datetime, timezone
    k = c.get("kickoff")
    if not k:
        return None
    try:
        kt = datetime.fromisoformat(k[:-1] + "+00:00" if k.endswith(("Z", "z")) else k)
    except ValueError:
        return None
    return (kt.replace(tzinfo=timezone.utc) if kt.tzinfo is None else kt).timestamp()


def _unmarked_first(fx: dict, cands: list, group: list, keep) -> list:
    """unmarkedFirst (#431 R7 under R2, verify_ports #1): R2 counts kickoffs within DESK_CLOCK_DRIFT (REDATED_DRIFT_S,
    inclusive) as one game, so "an unmarked call of the same game and side" can sit minutes off the nearest start.
    The group the nearest start chose (the calls the fill would take) keeps its unmarked calls first; when every one is
    marked, the unmarked calls passing `keep` among the candidates within _start_nearest's 3h whose kickoff is within
    the hour of one of the group's take the fill instead. The 3h doubleheader rule and the tie flag (the chosen group,
    listed whole) stand as they were. A line-for-line port: the Cockpit's matchFill moves with it."""
    from datetime import datetime, timezone
    u = [c for c in group if not c.get("not_executed")]
    if u or not group:
        return u or group
    if not fx.get("start"):
        return group
    t0 = datetime.fromisoformat(fx["start"]).replace(tzinfo=timezone.utc).timestamp()
    ks = [k for k in (_kickoff_ts(c) for c in group) if k is not None]
    same = [c for c in cands if not c.get("not_executed") and keep(c) and (k := _kickoff_ts(c)) is not None
            and abs(k - t0) <= 3 * 3600 and any(abs(k - x) <= REDATED_DRIFT_S for x in ks)]
    return same or group


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
        # a LADDER is executed as NO on the other side (desk order line: AWAY ladder = NO on HOME = X2): a
        # composite NO matches a real ladder call whose pick is the opposite side, never a straight (Codex on #299)
        opp = {"HOME": "AWAY", "AWAY": "HOME"}.get(fx.get("no_on_role"))

        def is_lad(c):
            return c.get("call_type") == "ladder" and c.get("pick") == opp and (c.get("units") or 0) > 0
        # R7 (ARCHITECT 2026-10-20, addendum 145 item 3(b), #431): an unmarked ladder of the game (R2's hour) first, as
        # for the straight below
        lad = _unmarked_first(fx, cands, [c for c in _start_nearest(fx, cands) if is_lad(c)], is_lad)
        if lad:
            c = lad[0]
            out = {"book": "system_matched", "category": f"{c.get('engine')} · {c.get('tier')} (ladder: NO on "
                   f"{fx.get('no_on')})", "engine": c.get("engine"), "tier": c.get("tier"), "call_id": c.get("id")}
            if len(lad) > 1:
                out["ambiguous_calls"] = [x.get("id") for x in lad]
            return out
        return {"book": "off_book_sports",
                "category": f"composite contract ({fx.get('resolve_note') or 'three-way NO'}) — never a straight",
                "plausible": True}
    if not fx.get("backed") and not fx.get("backed_role"):
        return {"book": "off_book_sports", "category": f"side not resolvable ({fx.get('resolve_note') or '?'})",
                "plausible": True}

    def pick_name(c):
        return c.get("home") if c.get("pick") == "HOME" else c.get("away") if c.get("pick") == "AWAY" else "Draw"

    def side_agrees(g):
        # ARCHITECT 2026-10-06 (matcher bug): the TICKER SUFFIX names the side, so a resolved role is
        # compared to the pick exactly (GB/TB once "agreed" through the shared word "Bay"); without a
        # role, whole-name subsets only
        if fx.get("backed_role"):
            return fx["backed_role"] == g.get("pick")
        b, p = fx.get("backed"), pick_name(g)
        if not b or not p:
            return False
        if b == "Draw" or p == "Draw":
            return b == p
        return _tok_subset(b, p)
    if not cands:
        ps = [g for g in (picks or []) if near(g) and game_fits(fx, g)]
        if not ps:
            return {"book": "off_book_sports", "category": "no logged call for this game"}
        agree = [g for g in ps if side_agrees(g)]
        if agree:
            return {"book": "system_pick_unlogged", "category": f"system-pick, unlogged ({agree[0].get('source')})"}
        return {"book": "off_book_sports", "category": "stored prediction exists but the side disagrees",
                "plausible": True}
    agree = [c for c in _start_nearest(fx, cands) if side_agrees(c)]

    def is_real(c):
        return c.get("call_type") != "quarantine_shadow" and (c.get("units") or 0) > 0
    # R7 (ARCHITECT 2026-10-20, addendum 145 item 3(b), #431): a call a closing page did not repeat
    # (not_executed) yields the fill to an unmarked call of the same game (R2's hour) and side; a marked call alone
    # keeps it
    real = _unmarked_first(fx, cands, [c for c in agree if is_real(c)], lambda c: side_agrees(c) and is_real(c))
    if real:
        c = real[0]
        out = {"book": "system_matched", "category": f"{c.get('engine')} · {c.get('tier')}",
               "engine": c.get("engine"), "tier": c.get("tier"), "call_id": c.get("id")}
        # PARITY: the Cockpit takes the first agreeing call, so the receipt does too (its numbers must
        # match the Cockpit's). When MORE THAN ONE real call fits (e.g. an MLB doubleheader, same teams
        # and day), the attribution is ambiguous: flagged and listed, never silent (Codex on #297).
        # The list covers only the group the fill went to (R7): a marked claim beside the unmarked call
        # that took the fill is no tie, in the ladder branch above as here.
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
    system_matched fills: clv = close fair of the held contract − entry; fee_adj = clv − open fee/contract.
    A call the Cockpit voided as re-dated (void_redated, ARCHITECT 2026-10-17, addendum 106 item 4) is never one.
    A call a closing page did not repeat (not_executed, #431) still is: addendum 145 item 3(b) R10 keeps it in
    executedPositions and clvLines, the claim-against-close read."""
    graded = {c.get("id"): c for c in (L.get("calls") or [])
              if c.get("status") == "graded" and c.get("close_ref") and not is_shadow(c)
              and c.get("call_type") != "parlay_leg" and not c.get("void_redated")}
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


# ---- #431 R16/R17: the closing CLV (closingPositions) ----------------------------------------------------------------
# ARCHITECT 2026-10-20, addendum 146 item 1(iv), verbatim: "R16 the ledger stores the page's ORDERED size and limit
# beside the FILLED size and entry; R17 each position carries entry minus the closing ask on its pick (true CLV, in
# cents) and the P&L view sums it beside the P&L". The sign as CORRECTED (addendum 148 item 1(b)): "ask minus entry,
# + = bought below the close, the direction the page's existing CLV lines already use". The port follows the page as
# the mark's ports do (R13: "parity ships with the mark"); scripts/ledger_fills_parity_verify.py compares every field.

def _js_truthy(x) -> bool:
    """JavaScript truthiness: an object or an array is true even when empty (Python's {} and [] are not)."""
    if isinstance(x, (dict, list)):
        return True
    if isinstance(x, float) and x != x:
        return False
    return bool(x)


def _js_num(x) -> float:
    """`+x` for a stored leg's bid or ask: a number as it is, a decimal string as JS coerces it ("" is 0), else NaN."""
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str) and re.fullmatch(r"\s*([+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?)?\s*", x):
        return float(x.strip() or 0)
    return float("nan")


def _js_join(*xs) -> str:
    """[a, b, c].join("|"): null and undefined join as ""."""
    from src.walters.desk_policy import js_str
    return "|".join("" if x is None else js_str(x) for x in xs)


def _utc_s(s):
    """utcMs in seconds: None for an empty value (the page's NaN), else the value read as _kickoff_ts reads a kickoff
    (a naive date-time is UTC)."""
    return None if not s else _kickoff_ts({"kickoff": str(s)})


def same_game(a: dict, b: dict) -> bool:
    """sameGame (R2, addendum 145 item 3(b)): one game by sport, home and away, kickoffs within DESK_CLOCK_DRIFT
    (REDATED_DRIFT_S), inclusive."""
    x, y = _utc_s(a.get("kickoff")), _utc_s(b.get("kickoff"))
    return (a.get("sport") == b.get("sport") and a.get("home") == b.get("home") and a.get("away") == b.get("away")
            and x is not None and y is not None and abs(x - y) <= REDATED_DRIFT_S)


def closing_index(closings) -> dict:
    """closingIndex: the stored games (L.meta.closings, the Cockpit's putPage records) by sport, home and away, in the
    stored order: {"<sport>|<home>|<away>": [{"k", "p", "g"}, ...]}."""
    ix: dict = {}
    for k, p in (closings or {}).items():
        for g in ((p.get("games") if isinstance(p, dict) else None) or {}).values():
            if isinstance(g, dict):
                ix.setdefault(_js_join(g.get("sport"), g.get("home"), g.get("away")), []).append(
                    {"k": k, "p": p, "g": g})
    return ix


def cover_of(ix: dict, c: dict) -> list:
    """coverOf: a call's covering stored games, those of its sport, home and away that same_game keeps."""
    return [h for h in ix.get(_js_join(c.get("sport"), c.get("home"), c.get("away")), []) if same_game(c, h["g"])]


def closing_positions(L: dict, fills: list[dict] | None = None) -> list[dict]:
    """closingPositions (#431 R16/R17, tools/cockpit.html), line for line. Addendum 148 item 1, each default accepted:
    (c) per position, qty-weighted; (d) every filled straight, VENUE or LADDER position matched to a call, open
    included (tickets and parlays are not positions, R5; shadows are never filled); (e) the closing page's order
    whenever one is stored for the game, else the slate's; (f) the held contract's ask, by the fill's ticker and side,
    and a fill on a contract the page does not quote counted, not priced; (g) over the ordered size, above the limit,
    outside any page: flagged and counted, never left out of the CLV; (h) a manual Record fill is not a position; (i)
    no backfill: a stored page with no closing quote is counted, never priced from anything else.

    One entry per call (graded or open, not a shadow, not a parlay leg, not void as re-dated; marked or not: a mark is
    R10's business) with a system_matched fill (qty > 0, entry known), in the order of its first fill:
      id, c, status;
      cover   "page" (one stored game covers the call), "none", or "ambiguous" (two: never guessed, law 4; neither
              page's order nor quote is read);
      page    "closing" (the covering page's order for the call's "<engine>|<call_type>|<pick>"), "slate" (the
              call's exec_order: the page it last followed) or None (outside any page);
      legacy  no order read and the call has no exec_order key (claimed before R16 stored one);
      ordered the order read ({ticker, side, limit, contracts, unit} or {why}), or None;
      filled  {contracts: sum qty, entry: qty-weighted (dollars), fills: n};
      asks    per fill, the held contract's closing ask: the stored leg whose ticker is the fill's (trimmed, upper
              case); YES its ask, NO 1 - its bid at 4 dp (desk_policy.order_line prices NO so); else None;
      quote   "priced", "unpriced" (a fill on a contract the page does not quote), "no_quote" (the stored game has no
              legs: a page stored before R17), "no_page" or "ambiguous";
      clv_c   sum qty*(ask - entry) / sum qty * 100: cents, close - entry, pre-fee; None unless EVERY fill prices
              (fee_adj's all-or-nothing);
      above_limit_c, above_fills  the largest entry - limit in cents (each at 4 dp, toFixed) above 0, and how many;
      over_size, partial          sum qty above / below the order's contracts.
    The limit and the contracts are read only when they are numbers. `fills` defaults to classify_fills(L)."""
    from src.walters.desk_policy import js_fixed, js_str
    ix = closing_index((L.get("meta") or {}).get("closings"))
    calls = {c.get("id"): c for c in (L.get("calls") or [])
             if not is_shadow(c) and c.get("call_type") != "parlay_leg" and not c.get("void_redated")
             and c.get("status") in ("graded", "open")}
    by: dict = {}
    for f in (fills if fills is not None else classify_fills(L)):
        if f.get("book") != "system_matched" or not f.get("call_id") or not (f.get("qty") or 0) > 0 \
                or f.get("entry") is None:
            continue
        c = calls.get(f["call_id"])
        if c is None:
            continue
        by.setdefault(c.get("id"), {"c": c, "fills": []})["fills"].append(f)

    def T(t):
        return ("" if t is None else js_str(t)).strip().upper()

    def cents(x):
        return float(js_fixed(x * 100, 4))

    def num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)
    out = []
    for a in by.values():
        c, fs = a["c"], a["fills"]
        hits = cover_of(ix, c)
        g = hits[0]["g"] if len(hits) == 1 else None
        cover = "page" if g is not None else "ambiguous" if hits else "none"
        orders = g.get("orders") if g is not None else None
        key = "|".join(js_str(c.get(k)) if k in c else "undefined" for k in ("engine", "call_type", "pick"))
        po = orders.get(key) if isinstance(orders, dict) else None
        eo = c.get("exec_order")
        legacy = not _js_truthy(po) and cover != "ambiguous" and "exec_order" not in c
        ordered = None if cover == "ambiguous" else po if _js_truthy(po) else eo if _js_truthy(eo) else None
        page = None if cover == "ambiguous" else "closing" if _js_truthy(po) else "slate" if _js_truthy(eo) else None
        qty = 0
        for f in fs:
            qty += f["qty"]
        s = 0
        for f in fs:
            s += f["qty"] * f["entry"]
        entry = s / qty
        lg = g.get("legs") if g is not None else None
        legs = list(lg.values()) if isinstance(lg, dict) else list(lg) if isinstance(lg, list) else None
        asks = []
        for f in fs:
            leg = None if legs is None else next(
                (x for x in legs if isinstance(x, dict) and _js_truthy(x.get("ticker"))
                 and T(x["ticker"]) == T(f.get("ticker"))), None)
            sd = ("" if not _js_truthy(f.get("side")) else js_str(f["side"])).lower()
            if leg is None or sd not in ("yes", "no"):
                asks.append(None)
            elif sd == "yes":
                asks.append(None if leg.get("ask") is None else _js_num(leg["ask"]))
            else:
                asks.append(None if leg.get("bid") is None else float(js_fixed(1 - _js_num(leg["bid"]), 4)))
        quote = (("no_page" if cover == "none" else "ambiguous") if cover != "page" else "no_quote" if legs is None
                 else "unpriced" if any(x is None for x in asks) else "priced")
        clv_c = None
        if quote == "priced":
            s = 0
            for f, x in zip(fs, asks):
                s += f["qty"] * (x - f["entry"])
            clv_c = s / qty * 100
        lim = ordered.get("limit") if isinstance(ordered, dict) and num(ordered.get("limit")) else None
        over = [] if lim is None else [x for x in (cents(f["entry"] - lim) for f in fs) if x > 0]
        n = ordered.get("contracts") if isinstance(ordered, dict) and num(ordered.get("contracts")) else None
        out.append({"id": c.get("id"), "c": c, "status": c.get("status"), "cover": cover, "page": page,
                    "legacy": legacy, "ordered": ordered, "filled": {"contracts": qty, "entry": entry, "fills": len(fs)},
                    "asks": asks, "quote": quote, "clv_c": clv_c, "above_limit_c": max(over) if over else None,
                    "above_fills": len(over), "over_size": n is not None and qty > n,
                    "partial": n is not None and qty < n})
    return out
