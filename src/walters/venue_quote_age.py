"""VENUE-EDGE: QUOTE AGE receipts (ARCHITECT 2026-10-07, addendum 4 E, gate-class) — READ-ONLY.

Build steps (3) and (4): "(3) A receipt over every VENUE call on file since 2026-10-02: the consensus at the call
and at each later pre-kickoff capture, and whether it ever moved. (4) Report, do not change: how old the book
quotes behind MODEL-sport references are at decision time (MLB, NFL, PL). That is the next ruling."

ON FILE = every JSON under the exports directory (recursive, so exports/host/ — the host's pulled copies — is
read too) that carries `desk_meta` (written with --desk), plus the Cockpit's ledger export when given. Fixtures
files are named per competition per UTC date (fixtures_<CODE>_<date>.json) and each run overwrites the day's file,
so only the LAST desk run of each day per machine is on file; earlier runs are not recoverable from exports/.

MATCH IDENTITY (Codex on #340): an export row's match_id is MACHINE-LOCAL (docs/specs/hosting-h1.md: the comparator
keys on (kickoff, home, away), never match_id). A row from a MIRRORED file (a path under <exports>/host/) is resolved
by stable identity only: exact home/away team names + kickoff within ±12h. A row from the laptop's own files uses its
match_id only after the DB row's teams and kickoff are verified against the exported home/away/utc_date; on a
mismatch it falls back to identity. Ambiguous or none -> unresolved, reported, never guessed.

THE CONSENSUS = a BOOK capture session in odds_snapshots: one (source, captured_at) stamp, market 1X2, every
outcome of the sport present (two-way HOME/AWAY; soccer HOME/DRAW/AWAY), source != "kalshi"; fair = devig_prob
normalised over the outcomes (src/walters/close.close_from_snapshots' rule); books = max n_books. "MOVED" = any
outcome's fair differs at FOUR DECIMALS (round(p, 4)) from the anchor's. Captures are OUR fetch times: a
consensus that does not move across fetches is the staleness signal; no quote time is stored (the provider's
own quote time is the probe's question, scripts/odds_payload_probe.py).

Nothing here writes: SELECTs only. Percentiles are nearest-rank on the sorted list, index round(q·(n−1)).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

SINCE_DEFAULT = datetime(2026, 10, 2)            # naive UTC: "every VENUE call on file since 2026-10-02"
DP = 4                                           # "unchanged to four decimals"
MODEL_SPORTS = ("MLB", "NFL", "PL")              # build step (4): the live model sports
MIRROR_DIR = "host"                              # <exports>/host/: deploy/hosting/pull_exports.py's destination
WINDOW = timedelta(hours=12)                     # identity match: exact team names, kickoff within ±12h
PROXY_LABEL = ("capture-based PROXIES (our fetch times), NOT quote age: no quote time is stored; the provider "
               "can serve an old quote on a fresh fetch (ARCHITECT 2026-10-07)")


# ------------------------------------------------------------------ parsing --

def parse_ts(v) -> datetime | None:
    """ISO text -> naive UTC (the DB's convention); naive input is UTC (#178). None / unparseable -> None."""
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


def iter_desk_docs(root: str) -> tuple[list[tuple[str, dict]], dict]:
    """Every JSON under `root` (recursive) whose top level carries desk_meta.as_of. Returns (docs, counts);
    counts["mirrored"] = the desk files under <root>/host/ (the host's pulled copies: foreign match_ids)."""
    docs, counts = [], {"json_files": 0, "unreadable": 0, "desk_files": 0, "mirrored": []}
    if not os.path.isdir(root):
        return docs, counts
    for d, _, files in sorted(os.walk(root)):
        for n in sorted(files):
            if not n.endswith(".json"):
                continue
            p = os.path.join(d, n)
            counts["json_files"] += 1
            try:
                with open(p) as f:
                    doc = json.load(f)
            except (OSError, ValueError):
                counts["unreadable"] += 1
                continue
            if isinstance(doc, dict) and isinstance(doc.get("desk_meta"), dict) and doc["desk_meta"].get("as_of"):
                docs.append((p, doc))
                counts["desk_files"] += 1
                if os.path.relpath(p, root).split(os.sep)[0] == MIRROR_DIR:
                    counts["mirrored"].append(p)
    return docs, counts


def _r4(fair: dict | None) -> dict | None:
    return None if not fair else {k: round(float(v), DP) for k, v in fair.items() if v is not None}


# ------------------------------------------------------------- the calls --

def _sec(t: datetime | None) -> datetime | None:
    return None if t is None else t.replace(microsecond=0)


def file_venue_calls(docs, since: datetime, mirrored=()) -> list[dict]:
    """Every fixtures row whose desk call is VENUE (engine venue_edge) at a desk as_of >= since. One call per
    (sport, home, away, kickoff, as_of, side) — stable identity, never the machine-local match_id: the same run
    found in two files (a copy) is one call with both paths. `match_id` is kept only from a LOCAL (non-mirrored)
    file, as a candidate that resolve_match verifies; a mirrored file's id is recorded as foreign, never used."""
    mirrored = set(mirrored or ())
    by_key: dict = {}
    for path, doc in docs:
        if not isinstance(doc.get("fixtures"), list):
            continue
        as_of = parse_ts(doc["desk_meta"].get("as_of"))
        if as_of is None or as_of < since:
            continue
        sport = str(doc.get("competition_code") or doc.get("competition") or doc.get("sport") or "?").upper()
        for f in doc["fixtures"]:
            d = (f or {}).get("desk") or {}
            if d.get("engine") != "venue_edge" or d.get("call") != "VENUE":
                continue
            mk = f.get("market") or {}
            foreign = path in mirrored
            kick = parse_ts(f.get("utc_date"))
            key = (sport, f.get("home_team"), f.get("away_team"), kick, as_of, d.get("side"))
            if key in by_key:
                c = by_key[key]
                c["files"].append(path)
                if foreign:
                    c["foreign_ids"].append(f.get("match_id"))
                elif c["match_id"] is None:
                    c["match_id"] = f.get("match_id")
                continue
            by_key[key] = {
                "origin": "file", "files": [path], "in_ledger": False, "as_of": as_of, "sport": sport,
                "match_id": None if foreign else f.get("match_id"),
                "foreign_ids": [f.get("match_id")] if foreign else [], "reprices": [], "claim_basis": None,
                "home": f.get("home_team"), "away": f.get("away_team"),
                "kickoff": kick, "side": d.get("side"), "units": d.get("units"),
                "div_pp": d.get("div_pp"), "book_p": d.get("book_p"), "kalshi_p": d.get("kalshi_p"),
                "file_fair": _r4(mk.get("fair_prob")), "file_books": mk.get("bookmaker_count"),
                "file_captured_at": parse_ts(mk.get("captured_at")), "fair_source": mk.get("fair_source")}
    return sorted(by_key.values(), key=lambda c: (c["as_of"], c["sport"], str(c["home"])))


def claim_time(c: dict) -> tuple[datetime | None, str]:
    """The FROZEN claim time of a ledger position. The Cockpit's upsertCalls() re-log merges {...cur, ...fresh}:
    top-level claim_as_of / captured_at become the NEWEST file's, while stampTiming() keeps the first capture in
    claim_at (set once, isNew) and appends every capture to reprices[]. So claim_at first; a position logged
    before the timing rule has no claim_at, and its claim_as_of / captured_at is used, labelled."""
    t = parse_ts(c.get("claim_at"))
    if t is not None:
        return t, "claim_at (frozen first claim)"
    t = parse_ts(c.get("claim_as_of"))
    if t is not None:
        return t, "claim_as_of (no claim_at: the latest log's, unfrozen)"
    t = parse_ts(c.get("captured_at"))
    return t, ("captured_at (no claim_at: the latest log's, unfrozen)" if t is not None else "no claim time")


def ledger_venue_calls(L: dict, since: datetime) -> list[dict]:
    """The Cockpit ledger's venue_edge claims (snapshotCalls logs only eligible VENUE rows) at claim time >= since.
    Claim time = claim_time() (claim_at, the frozen first claim; else claim_as_of / captured_at, labelled). One
    position is ONE call: its later re-logs (reprices[] after the claim) are reported on it, never counted as
    separate calls."""
    out = []
    for c in (L or {}).get("calls") or []:
        if not isinstance(c, dict) or c.get("engine") != "venue_edge":
            continue
        t, basis = claim_time(c)
        if t is None or t < since:
            continue
        reps = [x for x in (parse_ts(r.get("at")) for r in (c.get("reprices") or []) if isinstance(r, dict))
                if x is not None and _sec(x) != _sec(t)]
        out.append({"origin": "ledger", "files": [], "in_ledger": True, "as_of": t, "claim_basis": basis,
                    "reprices": sorted(reps), "foreign_ids": [],
                    "sport": str(c.get("sport") or "?").upper(), "match_id": None, "home": c.get("home"),
                    "away": c.get("away"), "kickoff": parse_ts(c.get("kickoff")), "side": c.get("pick"),
                    "units": c.get("units"), "div_pp": c.get("divergence_pp"), "book_p": c.get("model_p"),
                    "kalshi_p": c.get("kalshi_p", c.get("market_p")), "file_fair": None, "file_books": None,
                    "file_captured_at": None, "fair_source": None})
    return out


def merge_calls(file_calls: list[dict], ledger_calls: list[dict]) -> list[dict]:
    """A ledger claim of a call already on file marks it in_ledger and carries the claim's reprices; a ledger claim
    with no file on disk is its own row. Match first on (sport, teams, kickoff, side, as_of — the claim's FROZEN
    time, to the second): an auto-claim's clock is the file's desk_meta.as_of. A MANUAL claim ("Log today's
    calls") is stamped at the button click, never a file's as_of, so it falls back to the position's identity
    (sport, teams, kickoff, side — the Cockpit's instKey): the file it was logged from is the latest file call of
    that position at or before the click. No such file call: its own row (never guessed onto a later file)."""
    def ident(c):
        return (c["sport"], c["home"], c["away"], _sec(c["kickoff"]), c["side"])

    def key(c):
        return ident(c) + (_sec(c["as_of"]),)
    idx = {key(c): c for c in file_calls}
    by_pos: dict = {}
    for c in file_calls:
        by_pos.setdefault(ident(c), []).append(c)
    extra = []
    for c in ledger_calls:
        hit = idx.get(key(c))
        basis = c.get("claim_basis")
        if hit is None:
            prior = [f for f in by_pos.get(ident(c), []) if f["as_of"] <= c["as_of"] and not f["in_ledger"]]
            if prior:
                hit = max(prior, key=lambda f: f["as_of"])
                basis = f"{basis}; matched by position identity (manual claim at {_z(c['as_of'])})"
        if hit is not None:
            hit["in_ledger"] = True
            hit["reprices"] = c.get("reprices") or []
            hit["claim_basis"] = basis
        else:
            extra.append(c)
    return sorted(file_calls + extra, key=lambda c: (c["as_of"], c["sport"], str(c["home"])))


# ---------------------------------------------------------- the captures --

def sessions_from_snapshots(snaps, outcomes: tuple[str, ...]) -> list[dict]:
    """BOOK consensus sessions, oldest first: [{source, t, fair (normalised), fair4, books}]. A session missing an
    outcome is not a price (the #207 contract) and is skipped."""
    by: dict = {}
    for x in snaps:
        if (getattr(x, "source", None) == "kalshi" or x.market != "1X2" or x.captured_at is None
                or x.devig_prob is None):
            continue
        by.setdefault((x.source, x.captured_at), {})[x.selection] = x
    out = []
    for (src, t), legs in by.items():
        if not all(k in legs for k in outcomes):
            continue
        tot = sum(legs[k].devig_prob for k in outcomes)
        if tot <= 0:
            continue
        fair = {k: legs[k].devig_prob / tot for k in outcomes}
        out.append({"source": src, "t": t, "fair": fair, "fair4": _r4(fair),
                    "books": max((legs[k].n_books or 0) for k in outcomes)})
    return sorted(out, key=lambda x: (x["t"], str(x["source"])))


def unchanged_run(sessions: list[dict], ref: dict) -> tuple[dict, int, bool]:
    """Walking back from `ref` through the SAME source's sessions while fair4 is identical: (earliest identical
    session, sessions in the run, censored = the run reaches the first capture on file)."""
    same = [x for x in sessions if x["source"] == ref["source"] and x["t"] <= ref["t"]]
    first, n = ref, 0
    for x in reversed(same):
        if x["fair4"] != ref["fair4"]:
            return first, n, False
        first, n = x, n + 1
    return first, n, True


def anchor_for(sessions: list[dict], call: dict) -> tuple[dict | None, str]:
    """The capture behind a call. File call with a captured_at: the session AT that stamp (preferring the one whose
    fair4 equals the file's), else the last one before it. Ledger-only call: the last session at or before the
    claim time. Captures at/after kickoff never count."""
    pre = [x for x in sessions if call["kickoff"] is None or x["t"] < call["kickoff"]]
    cap = call.get("file_captured_at")
    if cap is not None:
        exact = [x for x in pre if x["t"] == cap]
        if exact:
            same = [x for x in exact if call.get("file_fair") and x["fair4"] == call["file_fair"]]
            return (same or exact)[-1], "the capture at the file's captured_at"
        before = [x for x in pre if x["t"] <= cap]
        return (before[-1], "last capture before the file's captured_at (no capture at that stamp)") if before \
            else (None, "no book capture at or before the file's captured_at")
    before = [x for x in pre if x["t"] <= call["as_of"]]
    return (before[-1], "last capture at or before the call time (the call carries no captured_at)") if before \
        else (None, "no book capture at or before the call time")


def receipt_row(call: dict, sessions: list[dict]) -> dict:
    a, basis = anchor_for(sessions, call)
    row = {**call, "anchor": a, "anchor_basis": basis, "later": [], "moved": None, "verdict": None,
           "file_matches_anchor": None, "unchanged_since": None, "run_n": 0, "run_censored": None}
    if a is None:
        row["verdict"] = "NO ANCHOR"
        return row
    if call.get("file_fair"):
        row["file_matches_anchor"] = all(a["fair4"].get(k) == v for k, v in call["file_fair"].items())
    first, n, cens = unchanged_run(sessions, a)
    row.update(unchanged_since=first["t"], run_n=n, run_censored=cens)
    later = [x for x in sessions if x["source"] == a["source"] and x["t"] > a["t"]
             and (call["kickoff"] is None or x["t"] < call["kickoff"])]
    row["later"] = [{**x, "moved": x["fair4"] != a["fair4"]} for x in later]
    if not later:
        row["verdict"] = "NO LATER CAPTURE"
    else:
        row["moved"] = any(x["moved"] for x in row["later"])
        row["verdict"] = "MOVED" if row["moved"] else "NEVER MOVED"
    return row


def _outcomes(match) -> tuple[str, ...]:
    from src.walters.close import outcomes_for
    return outcomes_for(match.sport)


def _identity_ok(m, call: dict) -> bool:
    """The DB row IS the exported game: exact home/away names and kickoff within ±12h."""
    return bool(m.home_team is not None and m.away_team is not None and m.utc_date is not None
                and call.get("kickoff") is not None and m.home_team.name == call.get("home")
                and m.away_team.name == call.get("away") and abs(m.utc_date - call["kickoff"]) <= WINDOW)


def resolve_match(s, call: dict):
    """The DB match of a call or export row, by STABLE identity (match_id is machine-local):
      - a LOCAL match_id is used only when the DB row's teams + kickoff equal the exported home/away/utc_date;
      - otherwise (mirrored file, id missing from the DB, or an id naming another game) by exact team names with
        kickoff within ±12h.
    Returns (match, how): how = "match_id (verified …)" / "identity (…)"; ambiguous or none -> (None, reason):
    never guessed."""
    from sqlalchemy import select
    from src.db.schema import Match, Team
    why = ("mirrored file: foreign match_id never used" if call.get("foreign_ids") and call.get("match_id") is None
           else "no match_id")
    if call.get("match_id") is not None:
        m = s.get(Match, call["match_id"])
        if m is not None and _identity_ok(m, call):
            return m, "match_id (verified: teams + kickoff)"
        why = (f"match_id {call['match_id']} not in the DB" if m is None else
               f"match_id {call['match_id']} is a different game in this DB")
    if not (call.get("home") and call.get("away") and call.get("kickoff")):
        return None, f"{why}; no teams/kickoff to resolve by identity — not guessed"
    hid = [t.id for t in s.execute(select(Team).where(Team.name == call["home"])).scalars()]
    aid = [t.id for t in s.execute(select(Team).where(Team.name == call["away"])).scalars()]
    ms = list(s.execute(select(Match).where(
        Match.home_team_id.in_(hid or [-1]), Match.away_team_id.in_(aid or [-1]),
        Match.utc_date >= call["kickoff"] - WINDOW,
        Match.utc_date <= call["kickoff"] + WINDOW)).scalars())
    if len(ms) != 1:
        return None, f"{why}; {len(ms)} DB matches for {call['away']} @ {call['home']} ±12h — not guessed"
    return ms[0], f"identity (team names + kickoff ±12h; {why})"


def match_sessions(s, match) -> list[dict]:
    from sqlalchemy import select
    from src.db.schema import OddsSnapshot
    snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == match.id,
                                                      OddsSnapshot.market == "1X2")).scalars())
    return sessions_from_snapshots(snaps, _outcomes(match))


def venue_receipt(s, calls: list[dict]) -> dict:
    rows = []
    for c in calls:
        m, how = resolve_match(s, c)
        if m is None:
            rows.append({**c, "export_match_id": c.get("match_id"), "match_id": None, "resolved_by": None,
                         "anchor": None, "anchor_basis": how, "later": [], "moved": None,
                         "verdict": "NO DB MATCH", "file_matches_anchor": None, "unchanged_since": None,
                         "run_n": 0, "run_censored": None})
            continue
        c = {**c, "export_match_id": c.get("match_id"), "match_id": m.id, "resolved_by": how,
             "kickoff": c["kickoff"] or m.utc_date}
        rows.append(receipt_row(c, match_sessions(s, m)))
    tot = {"calls": len(rows)}
    for v in ("NEVER MOVED", "MOVED", "NO LATER CAPTURE", "NO ANCHOR", "NO DB MATCH"):
        tot[v] = sum(1 for r in rows if r["verdict"] == v)
    tested = tot["NEVER MOVED"] + tot["MOVED"]
    tot["tested"] = tested
    tot["never_moved_share_of_tested"] = (tot["NEVER MOVED"] / tested) if tested else None
    tot["never_moved_share_of_calls"] = (tot["NEVER MOVED"] / len(rows)) if rows else None
    tot["repriced_positions"] = sum(1 for r in rows if r.get("reprices"))
    tot["reprices"] = sum(len(r.get("reprices") or []) for r in rows)
    return {"rows": rows, "totals": tot}


# ------------------------------------------------------------ formatting --

def _z(t) -> str:
    return "—" if t is None else t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _f4(fair) -> str:
    if not fair:
        return "—"
    order = [k for k in ("HOME", "DRAW", "AWAY") if k in fair]
    return " / ".join(f"{k} {fair[k]:.4f}" for k in order)


def _share(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def format_venue_receipt(res: dict, since: datetime, sources: list[str]) -> list[str]:
    t = res["totals"]
    out = [f"VENUE CALLS RECEIPT (ARCHITECT 2026-10-07, venue-edge quote age) · VENUE calls on file since "
           f"{_z(since)} · READ-ONLY",
           "on file: " + ("; ".join(sources) or "nothing"),
           f"consensus = book capture session (odds_snapshots, 1X2, every outcome, source != kalshi), compared at "
           f"{DP} decimals; captures are OUR fetch times, not quote times"]
    for r in res["rows"]:
        out.append("")
        out.append(f"{r['sport']} · {r['away']} @ {r['home']} · KO {_z(r['kickoff'])} · VENUE {r['units']}u on "
                   f"{r['side']} · call as_of {_z(r['as_of'])} · "
                   f"div {'—' if r['div_pp'] is None else format(r['div_pp'], '+.2f')}pp · book "
                   f"{'—' if r['book_p'] is None else format(r['book_p'], '.4f')} vs Kalshi "
                   f"{'—' if r['kalshi_p'] is None else format(r['kalshi_p'], '.4f')}")
        out.append(f"  source: {'; '.join(r['files']) or 'ledger only'}" + (" · in ledger" if r["in_ledger"]
                                                                             and r["files"] else ""))
        out.append(f"  DB match: {r['match_id'] if r['match_id'] is not None else '—'} via "
                   f"{r.get('resolved_by') or 'unresolved'}"
                   + (f" · foreign (host) id(s) {r['foreign_ids']} not used" if r.get("foreign_ids") else ""))
        if r.get("claim_basis"):
            out.append(f"  ledger claim time: {r['claim_basis']}")
        if r.get("reprices"):
            out.append(f"  re-logged {len(r['reprices'])} time(s) after the claim (one position, not extra calls): "
                       + ", ".join(_z(x) for x in r["reprices"][:10]) + (" …" if len(r["reprices"]) > 10 else ""))
        if r.get("file_fair"):
            out.append(f"  AT THE CALL (file): {_f4(r['file_fair'])} · books {r['file_books']} · captured_at "
                       f"{_z(r['file_captured_at'])} · fair_source {r['fair_source']}")
        a = r["anchor"]
        if a is None:
            out.append(f"  ANCHOR: none — {r['anchor_basis']} · VERDICT {r['verdict']}")
            continue
        out.append(f"  ANCHOR ({r['anchor_basis']}): {_z(a['t'])} · {a['source']} · {_f4(a['fair4'])} · books "
                   f"{a['books']}" + ("" if r["file_matches_anchor"] is None else
                                      f" · file == anchor at {DP}dp: {'yes' if r['file_matches_anchor'] else 'NO'}"))
        out.append(f"  identical at {DP}dp since {_z(r['unchanged_since'])} ({r['run_n']} capture(s)"
                   + (", reaches the first capture on file" if r["run_censored"] else "") + ")")
        for x in r["later"]:
            out.append(f"    later {_z(x['t'])} · {_f4(x['fair4'])} · books {x['books']} · "
                       f"{'MOVED' if x['moved'] else 'unchanged'}")
        out.append(f"  VERDICT: {r['verdict']} ({len(r['later'])} later pre-kickoff capture(s))")
    out.append("")
    out.append(f"TOTALS · calls {t['calls']} · tested (>= 1 later pre-kickoff capture) {t['tested']} · NEVER MOVED "
               f"{t['NEVER MOVED']} ({_share(t['never_moved_share_of_tested'])} of tested, "
               f"{_share(t['never_moved_share_of_calls'])} of calls) · MOVED {t['MOVED']} · no later capture "
               f"{t['NO LATER CAPTURE']} · no anchor {t['NO ANCHOR']} · no DB match {t['NO DB MATCH']}")
    out.append(f"  (re-logged ledger positions {t['repriced_positions']}, {t['reprices']} re-log(s): counted once "
               f"each, at the frozen claim)")
    return out


# --------------------------------------------- (4) model-sport reference age --

def pct(xs: list[float], q: float):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def _row_sport(doc: dict, row: dict) -> str:
    return str(row.get("competition") or doc.get("competition_code") or doc.get("sport") or "?").upper()


def _row_fair(row: dict) -> dict | None:
    mk = row.get("market") or {}
    if isinstance(mk.get("selections"), dict) and mk["selections"]:
        return _r4({k: (v or {}).get("fair_prob") for k, v in mk["selections"].items()
                    if (v or {}).get("fair_prob") is not None})
    if isinstance(mk.get("fair_prob"), dict) and mk.get("fair_source", "1X2") == "1X2":
        return _r4(mk["fair_prob"])
    return None


def model_reference_rows(docs, since: datetime, mirrored=()) -> list[dict]:
    """Every --desk prediction-export row of MLB/NFL/PL whose desk decided against a BOOK reference
    (desk.reference == "books"), excluding started rows (no decision). One per (sport, home, away, kickoff,
    as_of) — stable identity; a mirrored file's match_id is foreign and kept only for the record."""
    mirrored = set(mirrored or ())
    seen, out = set(), []
    for path, doc in docs:
        if not isinstance(doc.get("predictions"), list):
            continue
        as_of = parse_ts(doc["desk_meta"].get("as_of"))
        if as_of is None or as_of < since:
            continue
        for r in doc["predictions"]:
            d = (r or {}).get("desk") or {}
            sport = _row_sport(doc, r)
            if (sport not in MODEL_SPORTS or d.get("engine") != "model_edge" or d.get("reference") != "books"
                    or d.get("pass_kind") == "started"):
                continue
            kick = parse_ts(r.get("utc_date"))
            k = (sport, r.get("home_team"), r.get("away_team"), kick, as_of)
            if k in seen:
                continue
            seen.add(k)
            foreign = path in mirrored
            out.append({"sport": sport, "match_id": None if foreign else r.get("match_id"),
                        "foreign_ids": [r.get("match_id")] if foreign else [], "home": r.get("home_team"),
                        "away": r.get("away_team"), "as_of": as_of, "file": path,
                        "kickoff": kick, "file_fair": _row_fair(r), "call": d.get("call")})
    return out


def age_row(row: dict, sessions: list[dict]) -> dict:
    pre = [x for x in sessions if x["t"] <= row["as_of"] and (row["kickoff"] is None or x["t"] < row["kickoff"])]
    if not pre:
        return {**row, "ref": None}
    ref = pre[-1]
    first, n, cens = unchanged_run(sessions, ref)
    return {**row, "ref": ref, "capture_age_h": (row["as_of"] - ref["t"]).total_seconds() / 3600,
            "unchanged_age_h": (row["as_of"] - first["t"]).total_seconds() / 3600, "run_n": n, "censored": cens,
            "file_matches": (None if not row["file_fair"] else
                             all(ref["fair4"].get(k) == v for k, v in row["file_fair"].items()))}


def exclusion(x: dict) -> str | None:
    """Why a row stays OUT of the age statistics (None = it enters). Only a row whose reference session is
    VERIFIED (the file's fair equals the selected capture at 4dp) is measured; an unverified session may not be
    the one behind the Desk's reference (multi-source history, an NFL spread_derived reference, …)."""
    if x.get("ref") is None:
        return x.get("why") or "no book capture at or before as_of"
    if x.get("file_matches") is None:
        return "session unverified: the file carries no 1X2 fair to compare"
    if x["file_matches"] is False:
        return f"session unverified: file fair != the selected capture at {DP}dp"
    return None


def age_report(s, docs, since: datetime, mirrored=()) -> dict:
    rows = []
    for r in model_reference_rows(docs, since, mirrored):
        m, how = resolve_match(s, r)
        if m is None:
            rows.append({**r, "export_match_id": r.get("match_id"), "match_id": None, "resolved_by": None,
                         "ref": None, "why": f"no DB match: {how}"})
            continue
        r = {**r, "export_match_id": r.get("match_id"), "match_id": m.id, "resolved_by": how,
             "kickoff": r["kickoff"] or m.utc_date}
        rows.append(age_row(r, match_sessions(s, m)))
    for x in rows:
        x["excluded"] = exclusion(x)
    by = {}
    for sp in MODEL_SPORTS:
        rs = [x for x in rows if x["sport"] == sp]
        ok = [x for x in rs if x.get("ref") is not None]
        ver = [x for x in rs if x["excluded"] is None]                 # only VERIFIED sessions are measured
        ca, ua = [x["capture_age_h"] for x in ver], [x["unchanged_age_h"] for x in ver]
        by[sp] = {"rows": len(rs), "with_capture": len(ok), "measured": len(ver),
                  "excluded": len(rs) - len(ver),
                  "file_matches": sum(1 for x in ok if x["file_matches"]),
                  "file_mismatch": sum(1 for x in ok if x["file_matches"] is False),
                  "file_unverifiable": sum(1 for x in ok if x["file_matches"] is None),
                  "capture_age_h": {"median": pct(ca, 0.5), "p90": pct(ca, 0.9), "max": max(ca) if ca else None},
                  "unchanged_age_h": {"median": pct(ua, 0.5), "p90": pct(ua, 0.9), "max": max(ua) if ua else None},
                  "censored": sum(1 for x in ver if x["censored"]),
                  "unchanged_ge_3h": sum(1 for x in ua if x > 3)}
    return {"rows": rows, "by_sport": by}


def _h(x) -> str:
    return "—" if x is None else f"{x:.2f}h"


def format_age_report(rep: dict, since: datetime, sources: list[str]) -> list[str]:
    out = [f"MODEL-SPORT REFERENCE AGE (ARCHITECT 2026-10-07 build step 4: report, do not change) · --desk "
           f"prediction exports since {_z(since)} · READ-ONLY",
           f"LABEL: {PROXY_LABEL}",
           "on file: " + ("; ".join(sources) or "nothing"),
           "rows = desk.engine model_edge with reference 'books', started rows excluded, one per (match, as_of)",
           "capture age   = desk as_of − the last book capture session (odds_snapshots) at or before as_of",
           f"unchanged age = desk as_of − the earliest capture of the run of consecutive same-source captures "
           f"identical at {DP}dp ending at that session (censored = the run reaches the first capture on file)",
           f"measured = rows whose selected session is VERIFIED (file fair == capture at {DP}dp); every other row is "
           f"excluded from median/p90/max and listed with its reason",
           "match identity: a local match_id only after teams + kickoff verify; mirrored (host) files by team names "
           "+ kickoff ±12h (match_id is machine-local)"]
    for sp, b in rep["by_sport"].items():
        ca, ua = b["capture_age_h"], b["unchanged_age_h"]
        out.append(f"{sp}: rows {b['rows']} · with a capture {b['with_capture']} · measured (verified) "
                   f"{b['measured']} · excluded {b['excluded']} · file fair == capture at {DP}dp "
                   f"{b['file_matches']} (mismatch {b['file_mismatch']}, no file fair {b['file_unverifiable']})")
        out.append(f"  capture age   median {_h(ca['median'])} · p90 {_h(ca['p90'])} · max {_h(ca['max'])}")
        out.append(f"  unchanged age median {_h(ua['median'])} · p90 {_h(ua['p90'])} · max {_h(ua['max'])} · "
                   f"> 3h {b['unchanged_ge_3h']} · censored {b['censored']}")
    exc = [x for x in rep["rows"] if x.get("excluded")]
    if exc:
        out.append(f"EXCLUDED from the statistics: {len(exc)}")
        for x in exc[:50]:
            out.append(f"  {x['sport']} · {x.get('away')} @ {x.get('home')} · KO {_z(x.get('kickoff'))} · as_of "
                       f"{_z(x['as_of'])} · {x['excluded']}")
        if len(exc) > 50:
            out.append(f"  … {len(exc) - 50} more")
    return out
